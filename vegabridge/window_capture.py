"""Product capture feature: target only the Studio-launched QEMU child window.

Never selects a desktop monitor or another application's window. Windows Graphics
Capture reads the target's own GPU surface even when other apps overlap it.
"""
import ctypes
import threading
from ctypes import wintypes


def owned_window(pid, title):
    if not isinstance(pid, int) or pid <= 0 or not title.startswith("QEMU (VegaBridge"):
        raise ValueError("Capture requires this Studio session's VM process and title")
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowTextW.restype = ctypes.c_int
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsWindowVisible.restype = wintypes.BOOL
    found = []
    @callback_type
    def visit(hwnd, param):
        actual = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(actual))
        if actual.value == pid and user.IsWindowVisible(hwnd):
            text = ctypes.create_unicode_buffer(1024)
            user.GetWindowTextW(hwnd, text, len(text))
            if text.value in {title, title + ' - Press Ctrl+Alt+G to release grab'}:
                found.append(hwnd)
        return True
    user.EnumWindows(visit, 0)
    if len(found) != 1:
        raise RuntimeError("Open or restore this VM's display window before capturing it.")
    return found[0]


def capture_vm_window(pid, title, destination, capture_factory=None):
    hwnd = owned_window(pid, title)
    if capture_factory is None:
        from windows_capture import WindowsCapture
        capture_factory = WindowsCapture
    capture = capture_factory(cursor_capture=False, draw_border=None, monitor_index=None, window_hwnd=hwnd)
    done, errors = threading.Event(), []
    @capture.event
    def on_frame_arrived(frame, capture_control):
        try:
            if frame.width < 64 or frame.height < 64:
                raise RuntimeError("The VM display is too small or minimized. Restore it, then capture again.")
            frame.save_as_image(str(destination))
        except Exception as error:
            errors.append(error)
        finally:
            capture_control.stop()
            done.set()
    @capture.event
    def on_closed():
        done.set()
    control = capture.start_free_threaded()
    if not done.wait(8):
        control.stop()
        raise TimeoutError("The VM window did not produce a frame. Restore it, then capture again.")
    control.wait()
    if errors:
        raise RuntimeError("Could not capture this VM's display: " + str(errors[0]))
