"""Current-project file tools with stale-write protection and private undo."""
import hashlib
import json
import re
import os
from pathlib import Path
from .project import inside, safe_context, SKIP
from .storage import SecretStore, atomic_write


class AgentWorkspace:
    def __init__(self, root, secrets=None):
        self.root=Path(root).resolve()
        self.secrets=secrets or SecretStore()
        self.backup_name='agent-undo-'+hashlib.sha256(str(self.root).casefold().encode()).hexdigest()[:24]

    def path(self, relative):
        if not relative or Path(relative).is_absolute() or ':' in relative or '\\' in relative:
            raise ValueError('Use a project-relative path with forward slashes.')
        path=inside(self.root,self.root/relative)
        safe_context(self.root,path,'')
        # A linked ancestor must never redirect an edit out of the selected source tree.
        current=self.root/relative
        while current!=self.root:
            if current.is_symlink() or current.is_junction():raise ValueError('Linked source paths are not available to the assistant.')
            current=current.parent
        return path

    def files(self):
        result=[]
        for base,folders,names in os.walk(self.root,followlinks=False):
            folders[:]=[name for name in folders if name not in SKIP and not (Path(base)/name).is_symlink() and not (Path(base)/name).is_junction()]
            for name in names:
                path=Path(base)/name
                try:self.path(path.relative_to(self.root).as_posix())
                except ValueError:continue
                result.append(path.relative_to(self.root).as_posix())
                if len(result)>=1000:return result
        return result

    def read(self,relative):
        path=self.path(relative)
        if path.stat().st_size>120_000:raise ValueError('Source file exceeds 120 KB; use search or split the file.')
        raw=path.read_bytes();text=raw.decode('utf-8-sig')
        safe_context(self.root,path,text)
        return {'path':relative,'sha256':hashlib.sha256(raw).hexdigest(),'content':text}

    def write(self,relative,content,expected):
        path=self.path(relative)
        safe_context(self.root,path,content)
        before=path.read_bytes() if path.exists() else None
        actual=hashlib.sha256(before).hexdigest() if before is not None else ''
        if actual!=expected:raise ValueError('File changed or already exists. Read its current content and hash before editing.')
        if before is not None and len(before)>120_000:raise ValueError('Existing source file exceeds the edit limit.')
        after=content.encode('utf-8');after_hash=hashlib.sha256(after).hexdigest()
        # DPAPI backup stays outside the project, source export and public repository.
        self.secrets.set(self.backup_name,json.dumps({'path':relative,'before':before.decode('utf-8') if before is not None else None,'after':after_hash}))
        path.parent.mkdir(parents=True,exist_ok=True)
        atomic_write(path,after)
        return {'path':relative,'sha256':after_hash,'bytes':len(after),'undoAvailable':True}

    def undo(self):
        raw=self.secrets.get(self.backup_name)
        if not raw:raise ValueError('There is no assistant edit to undo in this project.')
        data=json.loads(raw);path=self.path(data['path'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=data['after']:
            raise ValueError('The edited file changed again. Undo refused to preserve the newer changes.')
        if data['before'] is None:path.unlink()
        else:atomic_write(path,data['before'].encode('utf-8'))
        self.secrets.remove(self.backup_name)
        return {'path':data['path'],'restored':True}


def project_destination(parent,folder):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',folder):
        raise ValueError('New project folder must be a single name containing letters, numbers, hyphens or underscores.')
    if folder.upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        raise ValueError('This folder name is reserved by Windows.')
    parent=Path(parent).resolve();dest=parent/folder
    if dest.exists():raise ValueError('This project folder already exists. Choose a new name.')
    return dest
