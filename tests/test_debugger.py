import io
import json
import socket
import threading
from pathlib import Path
import pytest
from vegabridge.dap import read_message,DapClient
from vegabridge.sdk_catalog import catalog_sdk
from vegabridge.native_debug import NativeDebugSession,prepare_server


def packet(value):
    body=json.dumps(value,ensure_ascii=False).encode('utf8')
    return b'Content-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body


def test_dap_handles_utf8_fragments_and_sequential_frames():
    class Fragmented(io.BytesIO):
        def read(self,n=-1):return super().read(min(n,2))
    stream=Fragmented(packet({'value':'变量'})+packet({'event':'stopped'}))
    assert read_message(stream)=={'value':'变量'}
    assert read_message(stream)=={'event':'stopped'}


@pytest.mark.parametrize('data',[b'Content-Length: -1\r\n\r\n',b'Content-Length: 999999999\r\n\r\n',
    b'Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}',b'Content-Length: 5\r\n\r\n{}'])
def test_dap_rejects_invalid_or_truncated_messages(data):
    with pytest.raises((ValueError,EOFError)):read_message(io.BytesIO(data))


def test_dap_request_event_ordering_and_disconnect(monkeypatch):
    from vegabridge import dap
    peers=[]
    class Process:
        def __init__(self,args,**kw):
            self.dead=False
            def serve():
                with socket.create_connection(('127.0.0.1',int(args[-1]))) as peer:
                    peers.append(peer)
                    with peer.makefile('rb') as stream:
                        req=read_message(stream)
                        peer.sendall(packet({'seq':1,'type':'event','event':'stopped'}))
                        peer.sendall(packet({'seq':2,'type':'response','request_seq':req['seq'],'success':True,'body':{'ok':True}}))
                        peer.sendall(packet({'seq':3,'type':'event','event':'continued'}))
                        peer.sendall(packet({'seq':4,'type':'event','event':'stopped','body':{'reason':'breakpoint'}}))
                        try:read_message(stream)
                        except EOFError:pass
            self.thread=threading.Thread(target=serve,daemon=True);self.thread.start()
        def poll(self):return 0 if self.dead else None
        def terminate(self):self.dead=True
        def wait(self,timeout=None):self.thread.join(timeout);return 0
    monkeypatch.setattr(dap.subprocess,'Popen',Process)
    client=DapClient('external-adapter')
    try:
        assert client.request('initialize')=={'ok':True}
        event=client.wait_event('continued')
        assert client.wait_event('stopped',after_seq=event['seq'])['body']['reason']=='breakpoint'
    finally:client.close()
    with pytest.raises(RuntimeError):client.send('continue')


def test_sdk_catalog_covers_external_contracts_and_excludes_symlinks(tmp_path):
    include=tmp_path/'sdk/sysroot-x86_64/usr/include';include.mkdir(parents=True)
    (include/'clock.h').write_text('clock')
    api=tmp_path/'apis/x86_64/include/apmf';api.mkdir(parents=True)
    (api/'device_config.idl').write_text('interface DeviceConfig {}')
    result=catalog_sdk(tmp_path/'sdk',query='device_config',api_root=tmp_path/'apis')
    assert result['matches']==1 and result['items'][0]['kind']=='API header / contract'
    result=catalog_sdk(tmp_path/'sdk',limit=1,api_root=tmp_path/'apis')
    assert result['matches']==2 and result['truncated']
    with pytest.raises(ValueError):catalog_sdk(tmp_path/'sdk',arch='../outside')


def test_native_session_refuses_binary_outside_project(tmp_path):
    project=tmp_path/'project';project.mkdir()
    with pytest.raises(ValueError):NativeDebugSession(project,tmp_path/'private','', 'target')


def test_gutter_breakpoints_and_stopped_highlight_preserve_source():
    from PySide6.QtWidgets import QApplication
    from vegabridge.editor import CodeEditor
    app=QApplication.instance() or QApplication([])
    editor=CodeEditor();editor.setPlainText('int main(){\n  return 0;\n}\n');before=editor.toPlainText()
    changes=[];editor.breakpointsChanged.connect(changes.append)
    editor.toggle_breakpoint(2);editor.set_debug_line(2)
    assert editor.breakpoints=={2} and len(editor.extraSelections())==2
    editor.set_debug_line(None);editor.toggle_breakpoint(2)
    assert changes==[[2],[]] and editor.toPlainText()==before and len(editor.extraSelections())==1
    editor.deleteLater()
