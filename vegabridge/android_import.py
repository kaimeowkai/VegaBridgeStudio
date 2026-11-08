"""Planning GUI for reusable Android conversion and runtime research."""
import uuid
from pathlib import Path
from PySide6.QtCore import Qt,Slot
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,
    QFileDialog,QComboBox,QTabWidget,QPlainTextEdit,QTableWidget,QAbstractItemView,QTableWidgetItem,QHeaderView,QProgressBar)
from .android_adapters import REGISTRY,STATES,adapter_rows
from .android_migration import render_plan
from .migration_workspace import prepare_import,create_workspace
from .android_runtime_probe import collect_runtime
from .storage import user_dir
from .devices import LocalBridge
from .process import Runner


class AndroidImportDialog(QDialog):
    def __init__(self,studio):
        super().__init__(studio);self.studio=studio;self.settings=dict(studio.settings)
        self.prepared=None;self.rows=[];self.runtime=None;self.worker=None;self.selected_row=None;self.created=None
        self.setWindowTitle('Android compatibility workbench');self.resize(1120,800);self.setMinimumSize(900,650)
        layout=QVBoxLayout(self)
        title=QLabel('Import and assess Android apps');title.setObjectName('eyebrow');layout.addWidget(title)
        intro=QLabel('Plan reusable conversion adapters and unchanged-APK runtime research in a separate workspace. This workflow does not convert, build or install an app.');intro.setWordWrap(True);layout.addWidget(intro)
        form=QFormLayout();self.kind=QComboBox();self.kind.addItems(['Source project folder','APK inventory']);form.addRow('Input type',self.kind)
        self.source=QLineEdit();self.source.setObjectName('migration-source');self.source.setPlaceholderText('Original Android project; read-only')
        self.browse_source=QPushButton('Browse input…');self.browse_source.clicked.connect(self.choose_source)
        row=QHBoxLayout();row.addWidget(self.source);row.addWidget(self.browse_source);form.addRow('Original input',row)
        self.destination=QLineEdit();self.destination.setObjectName('migration-workspace');self.destination.setPlaceholderText('New planning folder outside the original project')
        self.browse_destination=QPushButton('Choose parent…');self.browse_destination.clicked.connect(self.choose_destination)
        row=QHBoxLayout();row.addWidget(self.destination);row.addWidget(self.browse_destination);form.addRow('New workspace',row);layout.addLayout(form)
        self.assess=QPushButton('Assess input and verify preservation');self.assess.clicked.connect(self.scan);layout.addWidget(self.assess)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.summary=self.text_page('Select the original input. Assessment inventories source files before and after the scan; generated/cache directories are listed separately. No original source is copied or edited.')
        self.tabs.addTab(self.summary,'Assessment')
        from PySide6.QtWidgets import QWidget
        mapping_page=QWidget();mapping_layout=QVBoxLayout(mapping_page)
        self.mapping=QTableWidget(0,4);self.mapping.setHorizontalHeaderLabels(['Feature','Evidence','Shared mapping plan','Review state']);self.mapping.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.mapping.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.mapping.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mapping.setColumnWidth(0,225);self.mapping.setColumnWidth(1,80);self.mapping.setColumnWidth(2,350);self.mapping.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        self.mapping.currentCellChanged.connect(self.select_mapping);mapping_layout.addWidget(self.mapping,1)
        self.detail=self.text_page('Select a mapping to review its evidence. These are shared registry plans, not implemented or verified adapters.');self.detail.setMaximumHeight(135);mapping_layout.addWidget(self.detail)
        mapping_layout.addWidget(QLabel('Review notes for selected mapping'))
        self.notes=QPlainTextEdit();self.notes.setMaximumHeight(75)
        self.notes.textChanged.connect(self.note_changed);mapping_layout.addWidget(self.notes);self.tabs.addTab(mapping_page,'Shared adapters')
        runtime_page=QWidget();runtime_layout=QVBoxLayout(runtime_page)
        message=QLabel('Read-only checks of the selected Vega target. Device-node visibility is not proof of Android compatibility, and developer shells can differ from published apps.');message.setWordWrap(True);runtime_layout.addWidget(message)
        row=QHBoxLayout();self.target=QComboBox();self.target.setMinimumWidth(250);row.addWidget(self.target,1)
        self.refresh_targets=QPushButton('Refresh targets');self.refresh_targets.clicked.connect(self.find_targets);row.addWidget(self.refresh_targets)
        self.probe=QPushButton('Inspect runtime prerequisites');self.probe.clicked.connect(self.inspect_runtime);row.addWidget(self.probe);runtime_layout.addLayout(row)
        self.component=QLineEdit();self.component.setPlaceholderText('Optional own developer component for a second context check')
        if studio.project:
            try:
                from .project import metadata
                self.component.setText(metadata(studio.project)['component'])
            except (OSError,ValueError,KeyError):pass
        runtime_layout.addWidget(self.component)
        self.runtime_text=self.text_page('No target inspected. Container and VM Android-runtime routes remain research tasks. No APK execution is implemented.');runtime_layout.addWidget(self.runtime_text,1);self.tabs.addTab(runtime_page,'Runtime research')
        self.preview=self.text_page('The assessment and chosen shared mappings will appear here.');self.tabs.addTab(self.preview,'Plan preview');self.tabs.currentChanged.connect(self.refresh_preview)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.hide();layout.addWidget(self.progress)
        self.status=QLabel('Planning only. The original app, signing identity and installed applications stay untouched.');self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();self.save=QPushButton('Create planning workspace');self.save.clicked.connect(self.save_workspace);self.save.setEnabled(False);row.addWidget(self.save);row.addStretch()
        self.close_button=QPushButton('Close');self.close_button.clicked.connect(self.reject);row.addWidget(self.close_button);layout.addLayout(row)
        self.source.textChanged.connect(self.invalidate);self.kind.currentIndexChanged.connect(self.invalidate)
        devices=[]
        for index in range(studio.target.count()):
            target=studio.target.itemData(index)
            if isinstance(target,dict) and target.get('state')=='device':devices.append(target)
        self.set_targets(devices)

    @staticmethod
    def text_page(text):
        widget=QPlainTextEdit();widget.setReadOnly(True);widget.setPlainText(text);return widget

    def choose_source(self):
        if self.kind.currentIndex()==0:value=QFileDialog.getExistingDirectory(self,'Choose original Android source project')
        else:value,_=QFileDialog.getOpenFileName(self,'Choose Android APK','','Android packages (*.apk)')
        if value:
            self.source.setText(value)
            if not self.destination.text():self.destination.setText(str(user_dir()/'android-imports'/(Path(value).stem+'-'+uuid.uuid4().hex[:8])))

    def choose_destination(self):
        parent=QFileDialog.getExistingDirectory(self,'Choose parent for a new planning workspace')
        if parent:self.destination.setText(str(Path(parent)/(Path(self.source.text()).stem+'-'+uuid.uuid4().hex[:8])))

    def invalidate(self,*args):
        self.prepared=None;self.created=None;self.rows=[];self.selected_row=None;self.mapping.setRowCount(0);self.save.setEnabled(False)
        self.status.setText('Input changed. Assess again before creating a planning workspace.')

    def run_task(self,fn,done):
        if self.worker:return
        from .app import Job
        self.worker=Job(lambda runner,delta:fn(runner));self._done=done
        self.worker.result.connect(self.task_done);self.worker.failed.connect(self.task_failed);self.worker.finished.connect(self.task_finished)
        self.set_busy(True);self.worker.start()

    @Slot(object)
    def task_done(self,result):self._done(result)

    @Slot(str)
    def task_failed(self,error):self.status.setText(error)

    @Slot()
    def task_finished(self):
        worker=self.worker;self.worker=None;worker.deleteLater();self.set_busy(False)

    def set_busy(self,busy):
        self.progress.setVisible(busy)
        for widget in [self.source,self.kind,self.destination,self.browse_source,self.browse_destination,self.assess,self.mapping,self.notes,self.refresh_targets,self.probe,self.component,self.target]:widget.setEnabled(not busy)
        self.save.setEnabled(not busy and self.prepared is not None and self.created is None)
        self.mapping.setEnabled(not busy and self.created is None);self.notes.setEnabled(not busy and self.created is None)
        self.close_button.setText('Cancel task' if busy else 'Close')

    def scan(self):
        source=self.source.text().strip()
        if not source:self.status.setText('Choose an Android source folder or APK.');return
        self.prepared=None;self.created=None;self.save.setEnabled(False);self.status.setText('Inventorying and assessing input. No original files are written.')
        self.run_task(lambda runner:prepare_import(source,runner.check),self.assessed)

    def assessed(self,prepared):
        self.prepared=prepared;report=prepared['assessment'];baseline=prepared['baseline'];self.rows=adapter_rows(report)
        self.summary.setPlainText('Original input: '+prepared['sourcePath']+'\n\nPreservation check: PASSED\n'+str(baseline['fileCount'])+' files/links inventoried before and after assessment.\nInput copied: no\nConversion performed: no\n\nRoute: '+report['recommendedPath']+'\nShared mapping plans: '+str(len(self.rows))+'\nLogic review candidates: '+str(report.get('logicCandidateCount',0))+'\n\nExcluded generated/VCS directories: '+', '.join(baseline['excludedDirectories'])+'\n\nAssessment limitations:\n'+'\n'.join(report['limitations']))
        self.selected_row=None;self.mapping.setRowCount(len(self.rows))
        for index,row in enumerate(self.rows):
            self.mapping.setItem(index,0,QTableWidgetItem(row['feature']));self.mapping.setItem(index,1,QTableWidgetItem(str(row['evidenceCount'])))
            choices=QComboBox()
            for value in REGISTRY[row['id']][1]:choices.addItem(value.replace('-',' '),value)
            choices.setCurrentIndex(choices.findData(row['adapter']));choices.currentIndexChanged.connect(lambda unused,r=index,c=choices:self.mapping_changed(r,'adapter',c.currentData()));self.mapping.setCellWidget(index,2,choices)
            state=QComboBox()
            for key,label in STATES.items():state.addItem(label,key)
            state.currentIndexChanged.connect(lambda unused,r=index,c=state:self.mapping_changed(r,'status',c.currentData()));self.mapping.setCellWidget(index,3,state)
        if self.rows:self.mapping.selectRow(0)
        self.tabs.setCurrentIndex(0);self.refresh_preview();self.status.setText('Preservation verified. Review the shared mappings and create a separate planning workspace. No conversion is enabled.')

    def mapping_changed(self,index,key,value):
        if 0<=index<len(self.rows):self.rows[index][key]=value;self.refresh_preview()

    def select_mapping(self,row,*args):
        self.selected_row=row if 0<=row<len(self.rows) else None
        self.notes.blockSignals(True)
        if self.selected_row is not None:
            value=self.rows[row];self.notes.setPlainText(value['notes']);self.detail.setPlainText(value['description']+'\n\nImplementation verified: no\nEvidence ('+str(value['evidenceCount'])+' files):\n'+'\n'.join(value['evidence']))
        else:self.notes.clear()
        self.notes.blockSignals(False)

    def note_changed(self):
        if self.selected_row is not None:self.rows[self.selected_row]['notes']=self.notes.toPlainText()

    def refresh_preview(self,*args):
        if not self.prepared:return
        self.preview.setPlainText(render_plan(self.prepared['assessment'])+'\nShared registry plans (implementations unverified):\n'+'\n'.join(row['feature']+': '+row['adapter']+'; '+STATES[row['status']] for row in self.rows))

    def set_targets(self,devices):
        previous=self.target.currentData();self.target.clear();self.target.addItem('Choose a local Vega target',None)
        for device in devices:
            if device.get('state')=='device':self.target.addItem(device['serial'],device['serial'])
        current=self.studio.target.currentData();preferred=previous or (current.get('serial') if isinstance(current,dict) else None)
        if preferred and self.target.findData(preferred)>=0:self.target.setCurrentIndex(self.target.findData(preferred))

    def find_targets(self):
        settings=dict(self.settings)
        self.run_task(lambda runner:LocalBridge(settings,runner).devices(),self.set_targets)

    def inspect_runtime(self):
        serial=self.target.currentData();component=self.component.text().strip();settings=dict(self.settings)
        if not serial:self.status.setText('Select a target in Runtime research; use Refresh targets if needed.');return
        self.status.setText('Reading runtime prerequisites only; no packages, permissions or device settings are changed.')
        self.run_task(lambda runner:collect_runtime(LocalBridge(settings,runner,serial),component),self.runtime_ready)

    def runtime_ready(self,report):
        import json
        self.runtime=report;self.runtime_text.setPlainText(json.dumps(report,indent=2));self.status.setText('Runtime observations saved in this review. Android boot, APK execution and production permissions remain untested.')

    def save_workspace(self):
        if not self.prepared:return
        destination=self.destination.text().strip()
        if not destination:self.status.setText('Choose a new planning folder outside the original input.');return
        import copy
        prepared=copy.deepcopy(self.prepared);rows=copy.deepcopy(self.rows);runtime=copy.deepcopy(self.runtime)
        self.status.setText('Rechecking the original input before creating separate planning files…')
        self.run_task(lambda runner:create_workspace(prepared,destination,rows,runtime,runner.check),self.saved)

    def saved(self,result):
        self.created=result;self.status.setText('Created: '+result['workspace']+' — '+str(result['preservation']['filesVerified'])+' original files/links verified unchanged. Planning only; no conversion, build or install.')

    def reject(self):
        if self.worker:
            self.worker.cancelled.set();self.status.setText('Stopping the task; close again after cleanup finishes.');return
        super().reject()

    def closeEvent(self,event):
        if self.worker:self.worker.cancelled.set();event.ignore();return
        super().closeEvent(event)
