"""Local, encrypted conversation persistence, independent of project creation."""
import datetime as dt
import hashlib
import json
import uuid
from pathlib import Path
from .storage import user_dir, atomic_write, dpapi

INTRO = "VegaBridge assistant ready. Plan an app, create a project, edit code and run it here. Conversations are saved locally with Windows encryption."


class ConversationStore:
    def __init__(self, folder=None):
        self.folder=Path(folder) if folder else user_dir()/'conversations'
        self.folder.mkdir(parents=True,exist_ok=True)

    @staticmethod
    def project_key(root):
        return 'project-'+hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:24]

    def path(self,key):
        if not key or not key.replace('-','').isalnum():
            raise ValueError('Invalid conversation identifier')
        return self.folder/(key+'.dpapi')

    def load(self,key):
        path=self.path(key)
        if not path.exists():
            return {'key':key,'label':'Planning' if key=='planning' else 'Project conversation','history':[],'display':INTRO,'draft':'','project':''}
        return json.loads(dpapi(path.read_bytes(),True).decode('utf-8'))

    def save(self,key,label,history,display,draft='',project=''):
        data={'schemaVersion':1,'key':key,'label':label,'history':history,'display':display,'draft':draft,'project':project,'updatedAt':dt.datetime.now(dt.timezone.utc).isoformat()}
        encoded=json.dumps(data,ensure_ascii=False).encode('utf-8')
        if len(encoded)>8*1024*1024:
            raise ValueError('Conversation exceeded 8 MiB. Start a new conversation; the existing archive remains saved.')
        atomic_write(self.path(key),dpapi(encoded))

    def archive(self,key):
        data=self.load(key)
        if not data['history'] and not data.get('draft'):
            return
        archive='archive-'+uuid.uuid4().hex
        self.save(archive,data['label']+' · archived',data['history'],data['display'],data.get('draft',''),data.get('project',''))
        return archive

    def list(self):
        result=[]
        for path in self.folder.glob('*.dpapi'):
            try:
                data=self.load(path.stem)
                result.append({k:data.get(k,'') for k in ['key','label','project','updatedAt']})
            except (OSError,ValueError):
                continue
        return sorted(result,key=lambda x:x['updatedAt'],reverse=True)
