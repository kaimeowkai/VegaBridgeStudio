"""Native Qt debugger controls and read-only SDK discovery."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from PySide6.QtCore import Qt,Signal,Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,
    QComboBox,QFileDialog,QSplitter,QTreeWidget,QTreeWidgetItem,QPlainTextEdit,QTabWidget)
from .native_debug import NativeDebugSession
from .native_build import compile_source
from .sdk_catalog import catalog_sdk
from .process import Runner
from .project import inside
from .editor import CodeEditor


class NativeDebugPane(QWidget):
    completed=Signal(object)
    debugEvent=Signal(object)

    def __init__(self,studio,javascript=False):
        super().__init__(studio)
        self.studio=studio
        self.javascript=javascript
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='VegaDebug')
        self.session=None
        self.busy=False
        self.pending_stop=False
        self.running=False
        self.exited=False
        self.closed=False
        self.stopping=False
        self.completed.connect(self._completed)
        self.debugEvent.connect(self._event)
        layout=QVBoxLayout(self)
        self.intro=QLabel('Native C/C++ source debugging • Launch a developer executable or attach to this project’s installed app. Global device security settings remain unchanged.')
        self.intro.setWordWrap(True);layout.addWidget(self.intro)
        self.mode=QComboBox();self.mode.addItems(['Launch developer executable','Attach installed project app'])
        if not javascript:layout.addWidget(self.mode)
        else:self.mode.hide()
        row=QHBoxLayout();self.binary=QLineEdit();self.binary.setPlaceholderText('Native executable inside the current project');row.addWidget(self.binary)
        self.browse=QPushButton('Choose executable…');self.browse.clicked.connect(self.choose_binary);row.addWidget(self.browse);layout.addLayout(row)
        row=QHBoxLayout();self.arch=QComboBox();self.arch.addItems(['x86_64','armv7','aarch64']);row.addWidget(self.arch)
        self.compile=QPushButton('Compile current C/C++ with symbols');self.compile.clicked.connect(self.compile_current);row.addWidget(self.compile)
        toggle=QPushButton('Toggle cursor breakpoint');toggle.clicked.connect(self.toggle_breakpoint);row.addWidget(toggle);layout.addLayout(row)
        row=QHBoxLayout();self.launch=QPushButton('Start native debugger');self.launch.clicked.connect(self.start);row.addWidget(self.launch)
        self.controls={}
        for text,command in [('Continue','continue'),('Pause','pause'),('Step over','next'),('Step into','stepIn'),('Step out','stepOut')]:
            control=QPushButton(text);control.clicked.connect(lambda checked=False,c=command:self.control(c));row.addWidget(control);self.controls[command]=control
        self.stop=QPushButton('Stop debugger');self.stop.clicked.connect(self.stop_session);row.addWidget(self.stop);layout.addLayout(row)
        self.status=QLabel('Configure Windows CodeLLDB and matching Linux lldb-server under Settings → Native debugger. Debug builds keep source symbols; release builds retain optimization.')
        self.status.setWordWrap(True);layout.addWidget(self.status)
        self.source_title=QLabel('Source appears here when stopped in a project file.');layout.addWidget(self.source_title)
        panels=QSplitter(Qt.Orientation.Vertical);self.source=CodeEditor();self.source.setReadOnly(True);self.source.gutter.setEnabled(False);panels.addWidget(self.source)
        split=QSplitter();self.stack=QTreeWidget();self.stack.setHeaderLabels(['Call stack','Source']);self.stack.setColumnWidth(0,210);self.stack.itemClicked.connect(self.select_frame);split.addWidget(self.stack)
        self.locals=QTreeWidget();self.locals.setHeaderLabels(['Variable','Value','Type']);self.locals.setColumnWidth(0,170);self.locals.itemExpanded.connect(self.expand_variable);split.addWidget(self.locals);panels.addWidget(split);panels.setSizes([210,170]);layout.addWidget(panels)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setMaximumBlockCount(3000);self.output.setMaximumHeight(95);layout.addWidget(self.output)
        self.sdk=SdkPane(studio,self.pool) if not javascript else None
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.refresh_controls()

    def mode_changed(self,index):
        if self.javascript:return
        self.binary.clear();attached=index==1
        self.binary.setPlaceholderText('Optional matching project library/executable with native symbols' if attached else 'Native executable inside the current project')
        self.browse.setText('Optional symbols…' if attached else 'Choose executable…')
        self.launch.setText('Attach installed app' if attached else 'Start native debugger')
        self.stop.setText('Detach; keep app running' if attached else 'Stop debugger')
        self.compile.setVisible(not attached);self.arch.setVisible(not attached)
        self.status.setText('Install/run this project’s app first. Detaching resumes the app; matching unstripped symbols enable native source breakpoints.' if attached else 'Compile the current source with symbols, then launch its native executable.')

    def task(self,fn,done,allow_busy=False):
        if self.busy and not allow_busy:return
        self.busy=True;self.refresh_controls()
        def work():
            try:message=(done,fn(),None)
            except Exception as error:message=(done,None,str(error))
            if not self.closed:self.completed.emit(message)
        self.pool.submit(work)

    @Slot(object)
    def _completed(self,message):
        done,result,error=message
        self.busy=False
        if self.stopping and done!=self._stop_done:
            self.refresh_controls()
            return
        if error:self.status.setText(error)
        else:done(result)
        self.refresh_controls()
        if self.pending_stop and self.session and not self.busy and not self.stopping and not self.exited:
            self.pending_stop=False
            self.task(self.session.snapshot,self.show_snapshot)

    def refresh_controls(self):
        active=self.session is not None
        self.launch.setEnabled(not active and not self.busy)
        self.compile.setEnabled(not active and not self.busy)
        self.binary.setReadOnly(active or self.busy);self.arch.setEnabled(not active and not self.busy)
        self.mode.setEnabled(not active and not self.busy)
        self.stop.setEnabled(active and not self.stopping)
        for name,control in self.controls.items():
            control.setEnabled(active and not self.busy and not self.stopping and not self.exited and (self.running if name=='pause' else not self.running))

    def choose_binary(self):
        name,_=QFileDialog.getOpenFileName(self,'Choose native executable',str(self.studio.project or Path.home()))
        if name:self.binary.setText(name)

    def compile_current(self):
        editor=self.studio.current_editor()
        if not editor or not self.studio.project or editor.path.suffix not in {'.c','.cpp','.cc','.cxx'}:
            self.status.setText('Open a C or C++ source file in the current project first.');return
        if not self.studio.save_all():return
        arch=self.arch.currentText();output=self.studio.project/'build/native-debug'/arch/editor.path.stem
        settings=dict(self.studio.settings);source=editor.path
        def compiled(path):
            self.binary.setText(path);self.status.setText('Compiled with debug symbols. Set source breakpoints, then start the debugger. Recompile after editing source.')
        self.task(lambda:compile_source(source,output,settings,Runner(),arch,debug=True),compiled)

    def toggle_breakpoint(self):
        editor=self.studio.current_editor()
        if editor:editor.toggle_breakpoint()

    def breakpoints_changed(self,editor):
        if self.session and not self.busy and editor.path and (self.javascript or editor.path.suffix in {'.c','.cpp','.cc','.cxx','.h','.hpp'}):
            path=editor.path;lines=sorted(editor.breakpoints)
            self.task(lambda:self.session.set_breakpoints(path,lines),lambda r:self.status.setText('Breakpoints: '+json.dumps(r)))

    def start(self):
        if not self.studio.project or not self.studio.target.currentData():
            self.status.setText('Open a project and select its online developer target first.');return
        if not self.studio.save_all():return
        self.output.clear();self.exited=False
        target=self.studio.target.currentData()
        # Native debugger uses the selected local USB/TCP bridge, not SSH VVD.
        if isinstance(target,(tuple,list)):
            if target[0]!='local':self.status.setText('Choose a local USB/TCP target.');return
            serial=target[1]
        elif isinstance(target,dict):
            serial=target.get('serial','')
            if target.get('kind')=='Remote VVD':self.status.setText('Choose a local USB/TCP target for native debugging.');return
        else:serial=target
        try:
            from .installed_debug import InstalledAppDebugSession
            session_type=InstalledAppDebugSession if self.mode.currentIndex()==1 else NativeDebugSession
            self.session=session_type(self.studio.project,self.binary.text(),self.studio.settings,serial,self.debugEvent.emit)
        except Exception as error:self.status.setText(str(error));return
        points={}
        for i in range(self.studio.editors.count()):
            e=self.studio.editors.widget(i)
            if getattr(e,'path',None) and e.path.suffix in {'.c','.cpp','.cc','.cxx','.h','.hpp'} and getattr(e,'breakpoints',None):points[str(e.path)]=sorted(e.breakpoints)
        session=self.session
        def started(result):
            unresolved=sum(not point.get('verified',False) for point in result['breakpoints'])
            self.status.setText('Debugger connected. Continue to a breakpoint.'+(' '+str(unresolved)+' breakpoint(s) could not be resolved; check debug symbols and source lines.' if unresolved else ''))
            self.pending_stop=True
        def launch():
            try:return session.start(points)
            except Exception:self.session=None;raise
        self.task(launch,started)

    @Slot(object)
    def _event(self,msg):
        if not self.session or msg.get('sessionId')!=self.session.id or self.stopping:return
        name=msg.get('event');body=msg.get('body',{})
        if name=='output':self.output.appendPlainText(body.get('output','').rstrip())
        elif name=='stopped':
            self.running=False
            self.status.setText('Stopped: '+str(body.get('description',body.get('reason',''))))
            if self.busy:self.pending_stop=True
            else:self.task(self.session.snapshot,self.show_snapshot)
        elif name=='continued':
            self.running=True;self.pending_stop=False;self.stack.clear();self.locals.clear();self.clear_position()
        elif name in {'exited','terminated'}:
            self.running=False;self.exited=True;self.pending_stop=False;self.clear_position();self.status.setText('Debuggee exited'+(' with code '+str(body['exitCode']) if 'exitCode' in body else '')+'. Stop debugger to clean up the session.')
        self.refresh_controls()

    def control(self,command):
        session=self.session
        if session and not self.exited and not self.stopping:self.task(lambda:session.control(command),lambda r:None)

    def show_snapshot(self,result):
        self.stack.clear();self.locals.clear()
        for frame in result['frames']:
            source=frame.get('source',{}).get('path','');line=frame.get('line',0)
            item=QTreeWidgetItem([frame['name'],Path(source).name+':'+str(line) if source else 'No local source'])
            item.setData(0,Qt.ItemDataRole.UserRole,frame);self.stack.addTopLevelItem(item)
        if self.stack.topLevelItemCount():
            self.stack.setCurrentItem(self.stack.topLevelItem(0));self.show_source(result['frames'][0])
        self.show_variables(result['variables'])

    def show_variables(self,scopes):
        self.locals.clear()
        for scope in scopes:
            parent=QTreeWidgetItem([scope['scope']]);self.locals.addTopLevelItem(parent)
            self.add_variables(parent,scope['items']);parent.setExpanded(True)

    def add_variables(self,parent,items):
        for value in items:
            item=QTreeWidgetItem([value['name'],str(value.get('value',''))[:2000],value.get('type','')]);parent.addChild(item)
            if value.get('variablesReference'):
                item.setData(0,Qt.ItemDataRole.UserRole,value['variablesReference']);item.addChild(QTreeWidgetItem(['Expand to inspect']))

    def expand_variable(self,item):
        ref=item.data(0,Qt.ItemDataRole.UserRole)
        if ref and self.session and not self.busy:
            def show(values):
                item.takeChildren();item.setData(0,Qt.ItemDataRole.UserRole,None);self.add_variables(item,values)
            self.task(lambda:self.session.variables(ref),show)

    def select_frame(self,item,column):
        frame=item.data(0,Qt.ItemDataRole.UserRole)
        if frame and self.session and not self.busy:
            self.show_source(frame);self.task(lambda:self.session.variables_for_frame(frame['id']),self.show_variables)

    def clear_position(self):
        self.source.set_debug_line(None)
        for i in range(self.studio.editors.count()):
            editor=self.studio.editors.widget(i)
            if hasattr(editor,'set_debug_line'):editor.set_debug_line(None)

    def show_source(self,frame):
        source=frame.get('source',{}).get('path')
        if not source:
            self.clear_position();self.source.clear();self.source.breakpoints=set();self.source_title.setText(frame.get('name','Frame')+' · no mapped project source. Add matching symbols or step back to project code.')
            reference=frame.get('source',{}).get('sourceReference')
            if reference and self.session and hasattr(self.session,'source_for_frame') and not self.busy:
                session=self.session
                self.task(lambda:session.source_for_frame(frame),lambda text:self.source.setPlainText(text))
            return
        try:path=inside(self.studio.project,Path(source))
        except ValueError:return
        self.studio.open_file(path)
        editor=self.studio.current_editor()
        if editor and editor.path==path:
            line=frame.get('line',1);self.clear_position();editor.set_debug_line(line)
            cursor=editor.textCursor();cursor.setPosition(editor.document().findBlockByNumber(max(0,line-1)).position());editor.setTextCursor(cursor);editor.centerCursor()
            self.source.setPlainText(editor.toPlainText());self.source.breakpoints=set(editor.breakpoints);self.source.set_debug_line(line)
            cursor=self.source.textCursor();cursor.setPosition(self.source.document().findBlockByNumber(max(0,min(line-1,self.source.blockCount()-1))).position());self.source.setTextCursor(cursor);self.source.centerCursor()
            self.source_title.setText(path.relative_to(self.studio.project).as_posix()+':'+str(line)+' · '+frame.get('name',''))

    def stop_session(self):
        session=self.session
        if not session or self.stopping:return
        self.stopping=True
        self.pending_stop=False
        self.task(session.close,self._stop_done,allow_busy=True)

    def _stop_done(self,_):
        self.session=None;self.running=False;self.stopping=False;self.clear_position();self.stack.clear();self.locals.clear();self.status.setText('Detached; installed app resumed. Owned debugger resources cleaned up.' if self.mode.currentIndex()==1 else 'Debugger stopped; session-owned processes and bridge forwarding cleaned up.')

    def shutdown(self):
        self.closed=True
        if self.session:self.session.close()
        self.pool.shutdown(wait=False,cancel_futures=True)


class SdkPane(QWidget):
    completed=Signal(object)
    def __init__(self,studio,pool):
        super().__init__(studio);self.studio=studio;self.pool=pool;self.completed.connect(self.finished)
        layout=QVBoxLayout(self);row=QHBoxLayout();self.arch=QComboBox();self.arch.addItems(['x86_64','armv7','aarch64']);row.addWidget(self.arch)
        self.query=QLineEdit();self.query.setPlaceholderText('Find an SDK header, namespace, contract path or link library');self.query.returnPressed.connect(self.search);row.addWidget(self.query)
        self.refresh=QPushButton('Search SDK');self.refresh.clicked.connect(self.search);row.addWidget(self.refresh);layout.addLayout(row)
        self.note=QLabel('Read-only SDK browser. Header/library presence does not establish API availability, privileges, manifest contracts or runtime compatibility. SDK files stay external.');self.note.setWordWrap(True);layout.addWidget(self.note)
        split=QSplitter();self.results=QTreeWidget();self.results.setHeaderLabels(['Kind','SDK path']);self.results.itemClicked.connect(self.show_item);split.addWidget(self.results)
        self.preview=QPlainTextEdit();self.preview.setReadOnly(True);split.addWidget(self.preview);layout.addWidget(split)

    def search(self):
        self.refresh.setEnabled(False);root=self.studio.settings.get('sdk_root','');api=self.studio.settings.get('api_root','');arch=self.arch.currentText();query=self.query.text()
        def done(result):
            self.refresh.setEnabled(True);self.results.clear();self.note.setText(str(result['matches'])+' matches'+(' (first 500 shown)' if result['truncated'] else '')+'. '+result['note'])
            for entry in result['items']:
                item=QTreeWidgetItem([entry['kind'],entry['relative']]);item.setData(0,Qt.ItemDataRole.UserRole,entry);self.results.addTopLevelItem(item)
        def work():
            try:self.completed.emit((done,catalog_sdk(root,arch,query,api_root=api),None))
            except Exception as error:self.completed.emit((done,None,str(error)))
        self.pool.submit(work)

    @Slot(object)
    def finished(self,message):
        done,result,error=message;self.refresh.setEnabled(True)
        if error:self.note.setText(error)
        else:done(result)

    def show_item(self,item,column):
        entry=item.data(0,Qt.ItemDataRole.UserRole)
        if not entry:return
        if entry['kind']!='Library' and entry['bytes']<=500000:
            self.preview.setPlainText(Path(entry['path']).read_text(encoding='utf8',errors='replace'))
        else:self.preview.setPlainText(entry['path']+'\n\n'+str(entry['bytes'])+' bytes. Use Native build library options to link SDK libraries; no binary contents are displayed.')
