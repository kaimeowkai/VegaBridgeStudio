"""In-IDE view of the single managed Vega VM; capture and input stay local."""
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QSizePolicy, QDialog
from .native_vm import NativeVm
from .devices import LocalBridge
from .storage import user_dir


REMOTE_KEYS = {'Left':'KEY_LEFT','Right':'KEY_RIGHT','Up':'KEY_UP','Down':'KEY_DOWN',
               'OK':'KEY_ENTER','Back':'KEY_BACK','Home':'KEY_HOMEPAGE','Wake':'KEY_WAKEUP'}


def capture_managed_frame(settings):
    vm = NativeVm.attach_managed(settings)
    state = vm.command('query-status')
    # No archive of preview frames; temporary data is removed after each read.
    with tempfile.TemporaryDirectory(prefix='vm-preview-',dir=user_dir()) as folder:
        image = Path(folder)/'frame.png'
        vm.screenshot(image)
        return {'png':image.read_bytes(),'state':state['status'],'name':vm.display_name,
                'serial':'127.0.0.1:'+str(vm.device_port)}


def send_managed_key(settings, runner, key):
    if key not in REMOTE_KEYS:
        raise ValueError('Unknown emulator remote key')
    vm = NativeVm.attach_managed(settings)
    if not vm.command('query-status').get('running'):
        raise RuntimeError('Resume the VM before sending remote input.')
    bridge = LocalBridge(settings,runner,'127.0.0.1:'+str(vm.device_port))
    bridge.shell('inputd-cli button_press '+REMOTE_KEYS[key],timeout=8)


class FrameJob(QThread):
    frame = Signal(object)
    failed = Signal(str)
    def __init__(self, settings):
        super().__init__()
        self.settings = dict(settings)
    def run(self):
        try:
            self.frame.emit(capture_managed_frame(self.settings))
        except FileNotFoundError:
            self.failed.emit('No managed VM is running. Choose Start / attach.')
        except OSError:
            self.failed.emit('The VM monitor is unavailable. Start or attach the VM and retry when boot completes.')
        except Exception as error:
            self.failed.emit(str(error))


class VmScreen(QLabel):
    remote = Signal(str)
    def __init__(self):
        super().__init__('Start or attach to your managed Vega VM to preview its display.')
        self.image = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320,180)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet('background:#080c12; color:#9db0c3; border:1px solid #516980;')
        self.setToolTip('Click to focus. Arrow keys navigate; Enter selects; Escape goes back. Mouse buttons below act as a TV remote.')
    def display(self, data):
        image = QPixmap()
        if not image.loadFromData(data,'PNG'):
            raise RuntimeError('VM preview is not a valid PNG')
        self.image = image
        self.resize_image()
    def resize_image(self):
        if not self.image.isNull():
            self.setPixmap(self.image.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.resize_image()
    def keyPressEvent(self,event):
        mapping = {Qt.Key.Key_Left:'Left',Qt.Key.Key_Right:'Right',Qt.Key.Key_Up:'Up',Qt.Key.Key_Down:'Down',
                   Qt.Key.Key_Return:'OK',Qt.Key.Key_Enter:'OK',Qt.Key.Key_Escape:'Back',Qt.Key.Key_Backspace:'Back',Qt.Key.Key_Home:'Home'}
        if event.key() in mapping and not event.modifiers() and not event.isAutoRepeat():
            self.remote.emit(mapping[event.key()]);event.accept()
        else:
            super().keyPressEvent(event)


class EmulatorPane(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.frame_job = None
        self.input_job = None
        self.closing = False
        self.failures = 0
        self.live_pending = False
        self.stream_job = None
        self.popup = None
        self.root_layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel('VEGABRIDGE EMULATOR'))
        header.addStretch()
        self.popout_button = QPushButton('Pop out emulator')
        self.popout_button.clicked.connect(self.toggle_popout)
        header.addWidget(self.popout_button)
        self.root_layout.addLayout(header)
        self.placeholder = QLabel('The emulator panel is open in its pop-out window. Use Dock emulator to bring it back.')
        self.placeholder.setWordWrap(True);self.placeholder.hide()
        self.root_layout.addWidget(self.placeholder)
        self.controls = QWidget()
        layout = QVBoxLayout(self.controls)
        self.root_layout.addWidget(self.controls)
        self.status = QLabel('VM status: not checked')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        for text,fn in [('Start / attach',studio.start_native_vm),('Connect when ready',studio.connect_native_vm),
                        ('Pause',lambda:self.control('stop')),('Resume',lambda:self.control('cont')),('Stop VM',studio.stop_native_vm)]:
            button = QPushButton(text);button.clicked.connect(fn);row.addWidget(button)
        layout.addLayout(row)
        self.screen = VmScreen()
        self.screen.remote.connect(self.send_key)
        layout.addWidget(self.screen,1)
        self.view_layout = layout
        self.live_view = QCheckBox('Live emulator display (Windows • up to 10 updates/s)')
        self.live_view.setToolTip('Mirrors only the managed QEMU GPU window into this panel. Frames stay in memory. The same VM is shown in the IDE and pop-out; no second VM starts.')
        self.live_view.toggled.connect(self.set_live_view)
        layout.addWidget(self.live_view)
        refresh = QHBoxLayout()
        self.preview = QCheckBox('Refresh preview every 2 seconds')
        self.preview.setChecked(True)
        self.preview.toggled.connect(lambda checked:self.refresh() if checked else None)
        refresh.addWidget(self.preview)
        self.refresh_button = QPushButton('Refresh now');self.refresh_button.clicked.connect(self.refresh);refresh.addWidget(self.refresh_button)
        layout.addLayout(refresh)
        remote = QHBoxLayout()
        for key in ['Home','Back','Left','Up','OK','Down','Right','Wake']:
            button = QPushButton(key);button.clicked.connect(lambda checked=False,key=key:self.send_key(key));remote.addWidget(button)
        layout.addLayout(remote)
        self.hint = QLabel('Click the preview to use arrow keys / Enter / Escape. Preview and input always target the managed VM, independently of the toolbar device. This is a refreshed display, not a video stream.')
        self.hint.setWordWrap(True);layout.addWidget(self.hint)
        self.timer = QTimer(self);self.timer.setInterval(2000)
        self.timer.timeout.connect(self.tick);self.timer.start()

    def tick(self):
        if not self.live_view.isChecked() and self.preview.isChecked() and (self.isVisible() or (self.popup and self.popup.isVisible())):
            self.refresh()

    def set_live_view(self, checked):
        if checked:
            if self.frame_job:
                self.live_pending = True
                self.preview.setChecked(False)
                self.status.setText('Finishing preview capture before attaching the live display…')
                self.live_view.blockSignals(True);self.live_view.setChecked(False);self.live_view.blockSignals(False)
                return
            if self.stream_job:
                self.live_view.blockSignals(True);self.live_view.setChecked(False);self.live_view.blockSignals(False)
                self.status.setText('The previous live display is stopping. Enable it again in a moment.');return
            from .vm_stream import VmStream
            self.stream_job = VmStream(self.studio.settings)
            self.stream_job.frame.connect(self.show_live_frame)
            self.stream_job.status.connect(self.status.setText)
            self.stream_job.failed.connect(self.live_failed)
            self.stream_job.finished.connect(self.live_finished)
            self.stream_job.start()
            self.preview.setEnabled(False);self.refresh_button.setEnabled(False)
            self.hint.setText('Live view of the same managed VM. Click the display and use arrows / Enter / Escape, or use the TV remote buttons. Frames stay local and are not saved or sent to the assistant.')
        else:
            if self.stream_job:self.stream_job.cancelled.set()
            self.preview.setEnabled(True);self.refresh_button.setEnabled(True)
            self.hint.setText('Click the preview to use arrow keys / Enter / Escape. Remote controls always target this managed VM. This mode refreshes an image every 2 seconds.')
            self.screen.show();self.refresh()

    def detach_live(self):
        self.live_pending = False
        self.live_view.blockSignals(True);self.live_view.setChecked(False);self.live_view.blockSignals(False)
        if self.stream_job:self.stream_job.cancelled.set()
        self.screen.show()
        self.preview.setEnabled(True);self.refresh_button.setEnabled(True)

    def show_live_frame(self,image):
        job=self.stream_job
        try:
            if not self.closing and self.live_view.isChecked():
                self.screen.image=QPixmap.fromImage(image);self.screen.resize_image()
        finally:
            if job:job.mailbox.acknowledge()

    def live_failed(self,error):
        self.live_view.blockSignals(True);self.live_view.setChecked(False);self.live_view.blockSignals(False)
        self.preview.setEnabled(True);self.refresh_button.setEnabled(True)
        self.status.setText('Live display unavailable: '+error+' Use Refresh now for a still capture.')

    def live_finished(self):
        job=self.stream_job;self.stream_job=None
        if job:job.deleteLater()

    def toggle_popout(self):
        if self.popup:
            self.popup.close()
            return
        owner = self
        class PreviewWindow(QDialog):
            def closeEvent(self,event):
                self.layout().removeWidget(owner.controls)
                owner.controls.setParent(owner)
                owner.root_layout.addWidget(owner.controls)
                owner.controls.show()
                owner.placeholder.hide()
                owner.popout_button.setText('Pop out emulator')
                owner.popup = None
                event.accept()
        self.popup = PreviewWindow(self.studio)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.popup.setWindowTitle('VegaBridge Emulator — same managed VM')
        self.popup.resize(1024,760)
        layout = QVBoxLayout(self.popup)
        dock = QPushButton('Dock emulator back into Studio')
        dock.clicked.connect(self.popup.close)
        layout.addWidget(dock)
        self.root_layout.removeWidget(self.controls)
        layout.addWidget(self.controls)
        self.placeholder.show()
        self.popout_button.setText('Dock emulator')
        self.popup.show()
        self.controls.show()
        self.refresh()

    def showEvent(self,event):
        super().showEvent(event)
        if self.preview.isChecked():self.refresh()

    def refresh(self):
        if self.closing or self.frame_job or self.live_view.isChecked():return
        self.frame_job = FrameJob(self.studio.settings)
        self.frame_job.frame.connect(self.show_frame)
        self.frame_job.failed.connect(self.failed)
        self.frame_job.finished.connect(self.frame_finished)
        self.frame_job.start()

    def show_frame(self,frame):
        self.failures = 0
        self.screen.display(frame['png'])
        self.status.setText(f"{frame['name']} • {frame['state']} • {frame['serial']} • local display")

    def failed(self,error):
        self.failures += 1
        self.status.setText('Preview unavailable: '+error)
        if self.failures>=3:
            self.preview.setChecked(False)
            self.status.setText('Preview paused after 3 failed captures. '+error)

    def frame_finished(self):
        job = self.frame_job;self.frame_job = None
        if job:job.deleteLater()
        if self.live_pending and not self.closing:
            self.live_pending = False
            self.live_view.setChecked(True)

    def control(self,command):
        settings = dict(self.studio.settings)
        def work(runner,delta):
            vm = NativeVm.attach_managed(settings)
            vm.command(command)
            return vm.command('query-status')
        self.studio.start_job('Pause VM' if command=='stop' else 'Resume VM',work,lambda _:self.refresh())

    def send_key(self,key):
        if self.input_job:
            return
        settings = dict(self.studio.settings)
        self.input_job = self.studio.start_job('VM remote '+key,lambda runner,delta:send_managed_key(settings,runner,key),lambda _:self.refresh())
        self.input_job.finished.connect(lambda:setattr(self,'input_job',None))

    def shutdown(self):
        self.closing = True
        self.timer.stop()
        self.detach_live()
        if self.popup:
            self.popup.close()
        if self.stream_job and not self.stream_job.wait(12000):
            self.closing=False
            raise RuntimeError('Live display is still stopping. Close again in a moment.')
        if self.frame_job and not self.frame_job.wait(12000):
            self.closing = False
            raise RuntimeError('VM preview capture is still finishing. Close again in a moment.')
