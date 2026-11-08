import hashlib
import json
import httpx
import pytest
from vegabridge.agent import stream_agent,validate_arguments
from vegabridge.agent_workspace import AgentWorkspace,project_destination
from vegabridge.process import Runner
from vegabridge.storage import SecretStore


def event_response(output,status='completed'):
    event={'type':'response.completed','response':{'status':status,'output':output}}
    return httpx.Response(200,text='data: '+json.dumps(event)+'\n\n')


def test_tool_loop_preserves_calls_reasoning_and_executes_only_complete_output(tmp_path):
    workspace=AgentWorkspace(tmp_path,SecretStore(tmp_path.parent/'private-test-secrets'))
    requests=[];checkpoints=[]
    def server(request):
        body=json.loads(request.content);requests.append(body)
        if len(requests)==1:
            assert body['parallel_tool_calls'] is False and body['store'] is False
            return event_response([{'type':'reasoning','id':'r1','summary':[],'encrypted_content':'synthetic-encrypted'},
                {'type':'function_call','id':'f1','call_id':'call1','name':'write_file','arguments':json.dumps({'path':'index.js','content':'// synthetic app\n','expected_sha256':''})}])
        assert body['input'][-1]['type']=='function_call_output'
        assert body['input'][-2]['call_id']=='call1'
        assert any(item.get('encrypted_content')=='synthetic-encrypted' for item in body['input'])
        assert json.loads(body['input'][-1]['output'])['ok']
        return event_response([{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Created.'}]}])
    settings={'endpoint':'https://api.openai.com/v1','model':'example','protocol':'Responses'}
    result=stream_agent(settings,'synthetic-test-token',[{'role':'user','content':'Make an app'}],Runner(lambda _:None),lambda _:None,
        lambda name,args,runner:workspace.write(args['path'],args['content'],args['expected_sha256']),checkpoints.append,httpx.MockTransport(server))
    assert (tmp_path/'index.js').read_text()=='// synthetic app\n'
    assert len(requests)==2 and len(checkpoints)==2
    assert result['history'][-1]['role']=='assistant'


def test_incomplete_function_call_does_not_execute():
    invoked=[]
    transport=httpx.MockTransport(lambda request:event_response([{'type':'function_call','name':'build_project','call_id':'c','arguments':'{}'}],status='incomplete'))
    with pytest.raises(RuntimeError,match='completed'):
        stream_agent({'endpoint':'https://api.openai.com/v1','model':'example','protocol':'Responses'},'synthetic',[],Runner(lambda _:None),lambda _:None,lambda *args:invoked.append(args),transport=transport)
    assert not invoked


def test_stale_edits_private_paths_and_undo(tmp_path):
    store=SecretStore(tmp_path.parent/'private-undo-test')
    workspace=AgentWorkspace(tmp_path,store)
    original='export const count=1;\n'
    (tmp_path/'index.js').write_text(original)
    read=workspace.read('index.js')
    workspace.write('index.js','export const count=2;\n',read['sha256'])
    assert original.encode() not in store.path(workspace.backup_name).read_bytes()
    with pytest.raises(ValueError,match='changed'):workspace.write('index.js','overwrite',read['sha256'])
    workspace.undo()
    assert (tmp_path/'index.js').read_text()==original
    for relative in ['../outside.js','.git/config.json','private/settings.json','.env.json','secrets.json','C:/escape.js']:
        with pytest.raises(ValueError):workspace.path(relative)
    workspace.write('new.js','// new','')
    workspace.undo();assert not (tmp_path/'new.js').exists()


def test_schema_and_project_folder_validation(tmp_path):
    for args in [{'key':'KEY_DELETE'}, {'key':'KEY_ENTER','extra':'bad'}]:
        with pytest.raises(ValueError):validate_arguments('send_remote_key',args)
    for folder in ['../bad','C:/bad','CON','two/folders']:
        with pytest.raises(ValueError):project_destination(tmp_path,folder)
    assert project_destination(tmp_path,'GardenClock')==tmp_path/'GardenClock'


def test_worker_tools_execute_on_the_gui_thread(tmp_path,monkeypatch):
    import time
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication
    from vegabridge import app as workbench
    from vegabridge.conversations import ConversationStore
    from vegabridge.storage import DEFAULTS
    monkeypatch.setattr(workbench,'load_settings',lambda:dict(DEFAULTS))
    monkeypatch.setattr(workbench,'save_settings',lambda _:None)
    monkeypatch.setattr(workbench,'ConversationStore',lambda:ConversationStore(tmp_path/'private-test'))
    qt=QApplication.instance() or QApplication([])
    window=workbench.Studio();seen=[];results=[]
    def action(name,args):
        seen.append(QThread.currentThread()==qt.thread())
        return {'guiThread':seen[-1]}
    window.agent_action=action
    job=workbench.Job(lambda runner,delta:window.invoke_agent_tool('get_workspace',{},runner))
    job.result.connect(results.append);job.start()
    deadline=time.monotonic()+5
    while job.isRunning() and time.monotonic()<deadline:
        qt.processEvents();time.sleep(.01)
    job.wait(1000);qt.processEvents()
    assert seen==[True] and results==[{'guiThread':True}]
    window.close();qt.processEvents()
