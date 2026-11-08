import json
from PySide6.QtWidgets import QApplication
from vegabridge.conversations import ConversationStore
from vegabridge.storage import DEFAULTS
from vegabridge.project import create_project


def test_private_discussion_is_encrypted_and_stays_outside_projects(tmp_path):
    store=ConversationStore(tmp_path/'private-state')
    text='Synthetic private planning example, not an owner transcript'
    history=[{'role':'user','content':text}]
    store.save('planning','Planning',history,text,'Draft')
    assert text.encode() not in store.path('planning').read_bytes()
    assert store.load('planning')['history']==history
    assert store.load('planning')['draft']=='Draft'
    assert store.list()[0]['label']=='Planning'


def test_new_project_and_restart_keep_planning_history(tmp_path,monkeypatch):
    from vegabridge import app as workbench
    monkeypatch.setattr(workbench,'ConversationStore',lambda:ConversationStore(tmp_path/'private-state'))
    state=dict(DEFAULTS)
    monkeypatch.setattr(workbench,'load_settings',lambda:dict(state))
    monkeypatch.setattr(workbench,'save_settings',lambda value:state.update(value))
    qt=QApplication.instance() or QApplication([])
    window=workbench.Studio()
    original=[{'role':'user','content':'Synthetic plan: make a garden clock.'},{'role':'assistant','content':'We will use the green layout.'}]
    window.history=list(original)
    window.chat.setPlainText('Synthetic planning discussion')
    root=create_project(tmp_path/'new-project','Garden clock','com.example.gardenclock')
    window.open_project(root,carry_conversation=True)
    assert window.history==original
    assert 'Synthetic planning discussion' in window.chat.toPlainText()
    assert not list(root.rglob('*.dpapi'))
    key=window.chat_key
    window.close();qt.processEvents()
    reopened=workbench.Studio(root)
    assert reopened.chat_key==key and reopened.history==original
    reopened.clear_chat()
    assert reopened.history==[]
    assert reopened.conversations.load(key)['history']==original
    reopened.close();qt.processEvents()
