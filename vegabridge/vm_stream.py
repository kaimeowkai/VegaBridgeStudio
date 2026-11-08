"""Bounded, local GPU-window mirror for the identity-checked Vega VM.

Only the owned QEMU window is captured. Frames stay in memory; a latest-frame
mailbox and GUI acknowledgement prevent an unbounded queued-image backlog.
"""
import ctypes
import threading
import time
from ctypes import wintypes
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
from .native_vm import NativeVm
from .window_capture import owned_window


def client_crop(hwnd):
    """Client area relative to DWM's captured frame, excluding engine chrome."""
    api=ctypes.WinDLL('user32',use_last_error=True)
    api.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    api.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
    rect=wintypes.RECT();origin=wintypes.POINT()
    if not api.GetClientRect(hwnd,ctypes.byref(rect)) or not api.ClientToScreen(hwnd,ctypes.byref(origin)):
        raise ctypes.WinError(ctypes.get_last_error())
    bounds=wintypes.RECT()
    dwm=ctypes.WinDLL('dwmapi')
    dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    result=dwm.DwmGetWindowAttribute(hwnd,9,ctypes.byref(bounds),ctypes.sizeof(bounds))
    if result:raise RuntimeError('Could not identify the VM display client area')
    return origin.x-bounds.left,origin.y-bounds.top,rect.right,rect.bottom


def frame_image(frame,crop):
    x,y,width,height=crop
    if min(x,y)<0 or min(width,height)<64 or x+width>frame.width or y+height>frame.height:
        raise RuntimeError('VM capture dimensions changed. Restart its live display after resizing the engine window.')
    data=frame.frame_buffer[y:y+height,x:x+width,:].copy()
    return QImage(data.data,width,height,int(data.strides[0]),QImage.Format.Format_ARGB32).copy()


class FrameMailbox:
    def __init__(self):
        self.lock=threading.Lock()
        self.latest=None
        self.in_flight=False
    def put(self,frame):
        with self.lock:self.latest=frame
    def take(self):
        with self.lock:
            if self.in_flight or self.latest is None:return None
            frame=self.latest;self.latest=None;self.in_flight=True
            return frame
    def acknowledge(self):
        with self.lock:self.in_flight=False


class VmStream(QThread):
    frame=Signal(object)
    status=Signal(str)
    failed=Signal(str)
    def __init__(self,settings,capture_factory=None,crop_reader=client_crop):
        super().__init__()
        self.settings=dict(settings)
        self.cancelled=threading.Event()
        self.mailbox=FrameMailbox()
        self.capture_factory=capture_factory
        self.crop_reader=crop_reader
    def run(self):
        control=None
        try:
            vm=NativeVm.attach_managed(self.settings)
            vm.command('query-status')
            hwnd=owned_window(vm.pid,vm.window_title)
            factory=self.capture_factory
            if factory is None:
                from windows_capture import WindowsCapture
                factory=WindowsCapture
            capture=factory(cursor_capture=False,draw_border=None,monitor_index=None,window_hwnd=hwnd,minimum_update_interval=100)
            closed=threading.Event();errors=[]
            last=[0.0]
            @capture.event
            def on_frame_arrived(frame,capture_control):
                if self.cancelled.is_set():capture_control.stop();return
                now=time.monotonic()
                if now-last[0]<.095:return
                last[0]=now
                try:self.mailbox.put(frame_image(frame,self.crop_reader(hwnd)))
                except Exception as error:
                    errors.append(error);closed.set();capture_control.stop()
            @capture.event
            def on_closed():closed.set()
            control=capture.start_free_threaded()
            check=0;received=False;started=time.monotonic()
            while not self.cancelled.wait(.05):
                if errors:raise errors[0]
                if closed.is_set() or control.is_finished():
                    raise RuntimeError('The VM display closed. Start or attach it again.')
                image=self.mailbox.take()
                if image is not None:
                    received=True;self.frame.emit(image)
                if not received and time.monotonic()-started>8:
                    raise TimeoutError('The VM is not producing display frames. Restore its engine window or use Refresh now.')
                if time.monotonic()>check:
                    state=vm.command('query-status')
                    self.status.emit(vm.display_name+' • '+state['status']+' • local live display (up to 10 updates/s)')
                    check=time.monotonic()+2
        except FileNotFoundError:
            self.failed.emit('No managed VM is running. Choose Start / attach.')
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            if control:
                control.stop();control.wait()
