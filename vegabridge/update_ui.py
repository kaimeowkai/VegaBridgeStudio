"""Update UX; application state remains outside the portable installation."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QPlainTextEdit,QMessageBox
from . import __version__
from .storage import user_dir,atomic_write
from .updates import check_updates,prepare_update,ready_update,REPOSITORY


class UpdateController(QObject):
    def __init__(self,studio):
        super().__init__(studio)
        self.studio=studio;self.release=None;self.plan=None;self.job=None
        self.dialog=None;self.install_requested=False;self.worker_launched=False
        self.message='Installed version '+__version__+'. Updates use the public VegaBridge GitHub repository.'
        if getattr(sys,'frozen',False):
            self.plan=ready_update(Path(sys.executable).parent,__version__)
            if self.plan:self.message='A previously verified update is ready for installation on the next clean exit.'
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(10000)
        self.timer.timeout.connect(self.automatic_check);self.timer.start()

    def automatic_check(self):
        if not self.studio.isVisible() or not self.studio.settings['check_updates']:return
        try:
            state=json.loads((user_dir()/'update-check.json').read_text(encoding='utf-8'))
            if 0<=time.time()-float(state['checkedAt'])<8*3600:return
        except (OSError,ValueError,KeyError,TypeError):pass
        self.check()

    def show(self):
        if self.dialog:
            self.dialog.show();self.dialog.raise_();return
        dialog=QDialog(self.studio);self.dialog=dialog
        dialog.setWindowTitle('VegaBridge Studio updates');dialog.resize(700,460)
        layout=QVBoxLayout(dialog)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.notes=QPlainTextEdit();self.notes.setReadOnly(True);layout.addWidget(self.notes,1)
        row=QHBoxLayout()
        self.buttons={}
        for title,fn in [('Check now',self.check),('Release notes',self.open_notes),('Download update',self.download),('Restart and install',self.restart)]:
            button=QPushButton(title);button.clicked.connect(lambda checked=False,fn=fn:fn());row.addWidget(button)
            self.buttons[title]=button
        layout.addLayout(row)
        info=QLabel('Automatic download/install is optional in Settings → Updates. Installation occurs on a clean exit; the previous app folder is retained. Projects, encrypted chats and credentials are outside this package.')
        info.setWordWrap(True);layout.addWidget(info)
        close=QPushButton('Close');close.clicked.connect(dialog.close);layout.addWidget(close)
        dialog.finished.connect(lambda _:setattr(self,'dialog',None))
        self.refresh();dialog.show();self.check()

    def refresh(self):
        if self.dialog:
            self.status.setText(self.message)
            self.notes.setPlainText(self.release['notes'] if self.release else 'No newer eligible release has been found.')
            self.buttons['Check now'].setEnabled(self.job is None)
            self.buttons['Download update'].setEnabled(bool(self.release) and self.job is None and bool(getattr(sys,'frozen',False)))
            self.buttons['Restart and install'].setEnabled(bool(self.plan) and self.job is None)

    def finished(self):
        self.job=None;self.refresh()

    def check(self):
        if self.job:return
        self.message='Checking the public VegaBridge GitHub releases…';self.refresh()
        include=self.studio.settings['update_channel']=='Preview'
        def done(release):
            self.release=release
            atomic_write(user_dir()/'update-check.json',json.dumps({'checkedAt':time.time(),'installedVersion':__version__}).encode())
            self.message=('Version '+release['version']+' is available. Installed: '+__version__+'.') if release else 'You are up to date for the selected channel ('+__version__+').'
            if self.plan:self.message='A verified update is ready. Finish active work, then Restart and install.'
            self.refresh()
            if release:
                self.studio.statusBar().showMessage('VegaBridge '+release['version']+' available — Help → Check for updates',15000)
                if self.studio.settings['auto_update'] and getattr(sys,'frozen',False):QTimer.singleShot(0,self.download)
        self.job=self.studio.start_job('Check for VegaBridge updates',lambda runner,delta:check_updates(__version__,include),done,background=True)
        self.job.failed.connect(self.failed)
        self.job.finished.connect(self.finished)

    def failed(self,message):
        self.message='Update not completed: '+message;self.refresh()

    def open_notes(self):
        QDesktopServices.openUrl(QUrl(self.release['url'] if self.release else REPOSITORY+'/releases'))

    def download(self):
        if self.job:return
        if self.plan:
            self.message='A verified update is already ready. Use Restart and install after finishing active work.';self.refresh();return
        if not self.release:
            self.message='Check for a newer release first.';self.refresh();return
        release=dict(self.release)
        def done(plan):
            self.plan=plan
            self.message='Verified update '+release['version']+' is ready. Finish builds/debugging and stop the managed VM, then Restart and install. Automatic mode installs on your next clean exit.'
            self.refresh();self.studio.statusBar().showMessage('Verified VegaBridge update is ready for the next restart.',15000)
        self.job=self.studio.start_job('Download and verify VegaBridge update',lambda runner,delta:prepare_update(release,runner),done,background=True)
        self.job.failed.connect(self.failed)
        self.job.finished.connect(self.finished)

    def restart(self):
        if not self.plan:
            self.message='Download and verify an update before restarting.';self.refresh();return
        if self.studio.jobs or self.studio.debugger.session or self.studio.javascript_debugger.session:
            QMessageBox.information(self.studio,'Work is still active','Finish builds, stop the managed VM, and detach debugger sessions before restarting. Your update remains ready.')
            return
        self.install_requested=True
        if self.dialog:self.dialog.close()
        self.studio.close()

    def launch_on_close(self):
        self.timer.stop()
        if self.worker_launched or not self.plan or not (self.install_requested or self.studio.settings['auto_update']):return
        if not getattr(sys,'frozen',False):raise RuntimeError('Update installation requires the packaged Windows app')
        folder=Path(sys.executable).resolve().parent
        source=folder/'VegaBridgeUpdater.exe'
        if not source.is_file():raise RuntimeError('Portable updater is missing; use the complete Windows ZIP')
        plan=json.loads(Path(self.plan).read_text(encoding='utf-8'))
        if Path(plan['target']).resolve()!=folder:raise RuntimeError('The prepared update belongs to a different installation')
        plan['pid']=os.getpid()
        atomic_write(self.plan,json.dumps(plan,indent=2).encode('utf-8'))
        work=Path(tempfile.mkdtemp(prefix='worker-',dir=user_dir()/'updates'))
        worker=work/'VegaBridgeUpdater.exe';shutil.copy2(source,worker)
        subprocess.Popen([str(worker),'--plan',self.plan],cwd=str(work),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.worker_launched=True
