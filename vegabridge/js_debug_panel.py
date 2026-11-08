"""Native Studio controls for Hermes debugging and an owned Metro server."""
from pathlib import Path
from PySide6.QtCore import Signal,Slot
from PySide6.QtWidgets import QHBoxLayout,QLineEdit,QPushButton,QLabel
from .debug_panel import NativeDebugPane
from .javascript_debug import JavaScriptDebugSession
from .metro import MetroSession,available_port
from .project import build,metadata
from .devices import LocalBridge,DeviceCommandError


def target_serial(studio):
    target=studio.target.currentData()
    if not isinstance(target,dict) or target.get('kind')=='Remote VVD' or not target.get('serial'):
        raise ValueError('Select an online local USB/TCP Vega target first')
    return target['serial']


class JavaScriptDebugPane(NativeDebugPane):
    metroOutput=Signal(str)
    def __init__(self,studio):
        super().__init__(studio,javascript=True);self.metro=None
        self.metroOutput.connect(self.log_metro)
        self.intro.setText('JavaScript / TypeScript / JSX source debugging in the installed Vega app. Original project files are shown through Metro source maps; execution stays in Hermes on the target.')
        self.binary.setText('8081');self.binary.setPlaceholderText('Local Metro host port');self.binary.setMaximumWidth(150)
        self.browse.setText('Refresh source mappings');self.arch.hide();self.compile.setText('Build + run development app')
        self.launch.setText('Attach JavaScript debugger');self.stop.setText('Detach; keep app running')
        self.status.setText('Build/run a development package with the matching Metro project, then attach. Release packages keep debugging disabled.')
        row=QHBoxLayout();row.addWidget(QLabel('Console'));self.expression=QLineEdit();self.expression.setPlaceholderText('Evaluate JavaScript in the selected Vega app');self.expression.returnPressed.connect(self.evaluate);row.addWidget(self.expression)
        self.evaluate_button=QPushButton('Evaluate');self.evaluate_button.clicked.connect(self.evaluate);row.addWidget(self.evaluate_button)
        stop_metro=QPushButton('Stop owned Metro');stop_metro.clicked.connect(self.stop_metro);row.addWidget(stop_metro);self.layout().insertLayout(4,row)

    @Slot(str)
    def log_metro(self,text):
        self.studio.output.appendPlainText(text)

    def port(self):
        value=int(self.binary.text())
        if not 1024<=value<=65535:raise ValueError('Choose a Metro host port between 1024 and 65535')
        return value

    def choose_binary(self):
        if not self.session:self.status.setText('Attach to the running development app first.');return
        session=self.session
        def refresh():
            result=session.refresh_sources()
            for path,lines in dict(session.points).items():session.set_breakpoints(path,lines)
            return result
        self.task(refresh,lambda value:self.status.setText('Mapped original files: '+', '.join(value['originalFiles'])))

    def compile_current(self):
        if not self.studio.project:return
        if any(not job.background for job in self.studio.jobs):self.status.setText('Finish or cancel the current build task first.');return
        if self.session:self.status.setText('Detach the JavaScript debugger before rebuilding the app.');return
        if not self.studio.save_all():return
        try:serial=target_serial(self.studio);port=self.port()
        except Exception as error:self.status.setText(str(error));return
        root=self.studio.project;settings=dict(self.studio.settings);old=self.metro;self.metro=None
        def prepare(runner,delta):
            if old:old.close()
            selected=available_port(port)
            if selected!=port:runner.emit('Metro host port '+str(port)+' is in use; selected free loopback port '+str(selected)+'. The target still uses its standard port 8081.')
            package=build(root,settings,runner,debug=True);metro=MetroSession(root,settings,serial,selected,emit=self.metroOutput.emit)
            try:
                metro.start(runner);bridge=LocalBridge(settings,runner,serial);bridge.install(package)
                try:bridge.stop(metadata(root)['id'])
                except DeviceCommandError:pass
                bridge.launch(metadata(root)['component']);bridge.wait_for_app(metadata(root)['component'])
                return metro
            except Exception:metro.close();raise
        def ready(metro):
            self.metro=metro;self.binary.setText(str(metro.port));self.status.setText('Development app is running with breakpoint timeout protection and owned Metro on port '+str(metro.port)+'. Stop owned Metro restores normal debug-launch settings.')
        self.compile.setEnabled(False);self.launch.setEnabled(False)
        job=self.studio.start_job('Build and run JavaScript development app',prepare,ready)
        job.finished.connect(self.refresh_controls)

    def start(self):
        if self.session or self.busy:return
        if not self.studio.project or not self.studio.save_all():return
        try:
            serial=target_serial(self.studio)
            self.session=JavaScriptDebugSession(self.studio.project,self.port(),self.debugEvent.emit,self.studio.settings,serial)
        except Exception as error:self.status.setText(str(error));return
        self.output.clear();self.exited=False;self.running=True
        points={}
        for index in range(self.studio.editors.count()):
            editor=self.studio.editors.widget(index)
            if getattr(editor,'path',None) and editor.path.suffix in {'.js','.jsx','.ts','.tsx'} and editor.breakpoints:points[str(editor.path)]=sorted(editor.breakpoints)
        session=self.session
        def connect():
            try:return session.start(points)
            except Exception:self.session=None;raise
        def connected(result):
            self.running=not bool(session.paused);self.pending_stop=bool(session.paused)
            unresolved=sum(not point.get('verified') for point in result['breakpoints'])
            self.status.setText('Attached to '+result['runtime']+'. Original source mappings ready.'+(' '+str(unresolved)+' breakpoint(s) have no executable mapping.' if unresolved else ''))
        self.task(connect,connected)

    def breakpoints_changed(self,editor):
        if editor.path and editor.path.suffix in {'.js','.jsx','.ts','.tsx'}:super().breakpoints_changed(editor)

    def evaluate(self):
        if not self.session or self.busy or self.exited:return
        expression=self.expression.text();session=self.session
        self.task(lambda:session.evaluate(expression),lambda value:self.expression.clear())

    def _stop_done(self,result):
        super()._stop_done(result);self.status.setText('JavaScript debugger detached; the app continues running. Stop owned Metro separately when finished.')

    def stop_metro(self):
        if self.session:self.status.setText('Detach the JavaScript debugger before stopping its Metro server.');return
        metro=self.metro
        if not metro:self.status.setText('Studio does not own a Metro server in this session. External servers were preserved.');return
        def stopped(value):
            self.metro=None;self.status.setText('Owned Metro server stopped and normal app debug-launch settings restored. Relaunch the app normally to use normal timeouts.')
        self.task(metro.close,stopped)

    def shutdown(self):
        if self.metro:self.metro.close();self.metro=None
        super().shutdown()
