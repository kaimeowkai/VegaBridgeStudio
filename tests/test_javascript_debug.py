import json
import queue
import re
import sys
import threading
from pathlib import Path
import pytest
from vegabridge.cdp import CdpClient,local_url
from vegabridge.source_maps import SourceMap,vlq
from vegabridge.devices import LocalBridge
from vegabridge.installed_debug import InstalledAppDebugSession
from vegabridge.project import create_project


def test_source_map_shows_original_positions_and_detects_stale_source(tmp_path):
    source=tmp_path/'index.tsx';source.write_text('one\ntwo\nthree\n')
    mapping=SourceMap({'version':3,'sources':['index.tsx'],'sourcesContent':['one\ntwo\nthree\n'],'names':[],'mappings':'AAAA;AACA;AACA'},tmp_path)
    assert mapping.original(1,9)=={'path':str(source),'line':2,'column':1}
    assert mapping.generated(source,3)=={'lineNumber':2,'columnNumber':0}
    mapping.verify_source(source);source.write_text('edited')
    with pytest.raises(ValueError,match='differs'):mapping.verify_source(source)


def test_indexed_source_maps_respect_offsets_unmapped_spans_and_boundaries(tmp_path):
    basic={'version':3,'sources':['index.js','../private.js','node_modules/vendor.js'],'mappings':'AAAA,C'}
    result=SourceMap({'version':3,'sections':[{'offset':{'line':10,'column':4},'map':basic}]},tmp_path)
    assert result.original(10,3) is None
    assert result.original(10,4)['line']==1
    assert result.original(10,5) is None
    assert result.generated(tmp_path/'index.js',1)=={'lineNumber':10,'columnNumber':4}
    assert result.source_path('../private.js') is None
    assert result.source_path('node_modules/vendor.js') is None
    assert result.source_path('https://example.test/source.js') is None


@pytest.mark.parametrize('value',['g','!','gggggggggB'])
def test_invalid_source_map_values_are_refused(value):
    with pytest.raises(ValueError):vlq(value)


@pytest.mark.parametrize('url',['ws://example.test:8081/','ws://127.0.0.1:8082/','wss://127.0.0.1:8081/','ws://user@127.0.0.1:8081/','ws://127.0.0.1.evil:8081/'])
def test_inspector_cannot_connect_to_an_external_or_other_port(url):
    with pytest.raises(ValueError):local_url(url,8081,True)


def test_cdp_async_evaluation_does_not_block_breakpoint_controls(monkeypatch):
    from vegabridge import cdp
    class Socket:
        def __init__(self):self.incoming=queue.Queue();self.closed=False
        def settimeout(self,value):pass
        def send(self,text):
            request=json.loads(text)
            if request['method']=='Runtime.evaluate':
                self.evaluation=request['id'];self.incoming.put(json.dumps({'method':'Debugger.paused','params':{'reason':'other'}}))
            elif request['method']=='Debugger.resume':
                self.incoming.put(json.dumps({'id':request['id'],'result':{}}));self.incoming.put(json.dumps({'id':self.evaluation,'result':{'result':{'type':'number','value':24}}}))
        def recv(self):return self.incoming.get(timeout=3)
        def close(self,**kwargs):self.closed=True;self.incoming.put('')
    transport=Socket();monkeypatch.setattr(cdp.websocket,'create_connection',lambda *a,**k:transport)
    events=[];received=threading.Event()
    def event(value):
        events.append(value)
        if value.get('method')=='VegaBridge.evaluationResult':received.set()
    client=CdpClient('ws://127.0.0.1:8081/inspector/debug',event)
    try:
        client.send('Runtime.evaluate',{'expression':'calculate(7)'},asynchronous=True)
        client.wait_event('Debugger.paused')
        assert client.request('Debugger.resume')=={}
        # Inspect the received asynchronous response after the reader processes it.
        assert received.wait(2)
        assert any(event.get('method')=='VegaBridge.evaluationResult' for event in events)
    finally:client.close()


def test_component_shell_keeps_identity_and_checks_remote_exit_status():
    class Runner:
        def run(self,args,**kwargs):
            assert args[-5:-1]==['shell','-x','component-id','com.example.app.main']
            marker=re.search('__VEGABRIDGE_RC_[a-f0-9]+__',args[-1]).group()
            return 'component result\r\r\n'+marker+'0\r\r\n'
    bridge=LocalBridge({'adb':sys.executable,'bridge_port':5048},Runner(),'emulator-test')
    assert bridge.component_shell('com.example.app.main','id')=='component result'
    for component in ['com.amazon.system.main','com.example.app;bad','../../other']:
        with pytest.raises(ValueError):bridge.component_shell(component,'id')


def test_installed_attach_refuses_other_project_symbols_and_system_components(tmp_path):
    root=create_project(tmp_path/'app','Attach Test','com.example.attachtest')
    with pytest.raises(ValueError):InstalledAppDebugSession(root,tmp_path/'outside.so',{},'target')
    system=create_project(tmp_path/'system','System','com.amazon.system')
    with pytest.raises(ValueError,match='own current-project'):InstalledAppDebugSession(system,'',{},'target')


def test_installed_attach_rejects_idle_lifecycle_entries():
    from vegabridge.installed_debug import component_process
    class Bridge:
        def shell(self,*args,**kwargs):return 'com.example.app.main I 0 9 IDLE PERMANENT n/a'
    with pytest.raises(RuntimeError,match='no running process'):component_process(Bridge(),'com.example.app.main')


def test_installed_detach_does_not_terminate_app_or_remove_other_forwarding(tmp_path,monkeypatch):
    from vegabridge import installed_debug
    root=create_project(tmp_path/'app','Attach Test','com.example.attachtest');commands=[]
    class Bridge:
        serial='selected';port=5048
        def __init__(self,*a):pass
        def shell(self,command,**kwargs):return 'com.example.attachtest.main I 44 9 VISIBLE PERMANENT n/a'
        def component_shell(self,component,command,**kwargs):
            commands.append(command)
            return '2 (stem-init) S '+'0 '*18+'77 0' if command.startswith('cat /proc/') else ''
        def call(self,args,**kwargs):
            commands.append(args)
            if args==['forward','--list']:return 'selected tcp:48000 tcp:49000\nother tcp:48001 tcp:49001'
            return ''
    monkeypatch.setattr(installed_debug,'LocalBridge',Bridge)
    session=InstalledAppDebugSession(root,'',{},'selected');session.owner={'pid':44,'instance':'9'};session.target_pid=2
    session.process_stamp='2 (stem-init) S '+'0 '*18+'77 0';session.forward='48000';session.port=49000
    class Dap:
        def request(self,command,params,**kwargs):assert command=='disconnect' and params=={'terminateDebuggee':False}
        def close(self):pass
    session.dap=Dap();session.close()
    assert ['forward','--remove','tcp:48000'] in commands
    assert 'kill -CONT 2' in commands
    assert not any('terminate-app' in str(command) or 'kill -9' in str(command) or '48001' in str(command) for command in commands)


def test_metro_uses_a_free_host_port_and_preserves_existing_listener(tmp_path):
    import socket
    from vegabridge.metro import available_port,MetroSession
    with socket.socket() as external:
        external.bind(('127.0.0.1',0));external.listen();port=external.getsockname()[1]
        assert available_port(port)!=port
        session=MetroSession(tmp_path,{'adb':sys.executable,'bridge_port':5048},'target',port)
        with pytest.raises(RuntimeError,match='another process'):session.start(None)
        assert external.getsockname()[1]==port


def test_device_source_maps_remap_only_the_declared_loopback_ports():
    from vegabridge.javascript_debug import map_host_url,canonical_script
    assert map_host_url('http://127.0.0.1:8081/index.map?platform=kepler',49123)=='http://127.0.0.1:49123/index.map?platform=kepler'
    for url in ['http://127.0.0.1:9000/index.map','http://example.test:8081/index.map']:
        with pytest.raises(ValueError):map_host_url(url,49123)
    assert canonical_script('var n=1;\r\n//# sourceURL=http://127.0.0.1:8081/index.js\n')=='var n=1;'


def test_metro_output_uses_window_lifetime_sink_and_removes_terminal_escapes(tmp_path):
    import io
    from types import SimpleNamespace
    from vegabridge.metro import MetroSession
    lines=[]
    session=MetroSession(tmp_path,{'adb':sys.executable,'bridge_port':5048},'target',emit=lines.append)
    session.process=SimpleNamespace(stdout=io.BytesIO(b'\x1b[32mMetro ready\x1b[0m\r\nLater request\n'))
    session._read_output(session.emit)
    assert lines==['Metro ready','Later request']


def test_owned_metro_restores_only_its_component_debug_launch_settings(tmp_path):
    from vegabridge.metro import MetroSession
    session=MetroSession(tmp_path,{'adb':sys.executable,'bridge_port':5048},'target');commands=[]
    class Bridge:
        def shell(self,command):commands.append(command)
    session.bridge=Bridge();session.timeout_component='com.example.app.main'
    session.close();session.close()
    assert commands==['vlcm debug com.example.app.main --clear']
    assert session.timeout_component is None


def test_metro_restore_failure_keeps_component_for_explicit_retry(tmp_path):
    from vegabridge.metro import MetroSession
    session=MetroSession(tmp_path,{'adb':sys.executable,'bridge_port':5048},'target')
    class Bridge:
        def shell(self,command):raise RuntimeError('Device offline')
    session.bridge=Bridge();session.timeout_component='com.example.app.main'
    with pytest.raises(RuntimeError,match='after reconnecting'):session.close()
    assert session.timeout_component=='com.example.app.main'


def test_development_pack_is_separate_from_release_and_keeps_same_identity(tmp_path):
    from vegabridge.package import pack,package_files
    root=create_project(tmp_path/'app','Debug Build','com.example.debugbuild');bundle=root/'stage/bundle';bundle.mkdir(parents=True)
    (bundle/'index.bundle').write_bytes(b'34588b5946dc99c968dd')
    release=Path(pack(root,lambda value:None,identity_base=tmp_path/'identity'));original=release.read_bytes()
    debug=Path(pack(root,lambda value:None,identity_base=tmp_path/'identity',development=True))
    a,_=package_files(release);b,_=package_files(debug)
    assert debug!=release and release.read_bytes()==original
    assert not json.loads(a['assets/raw/keplerscript-app-config.json'])['developmentEnabled']
    assert json.loads(b['assets/raw/keplerscript-app-config.json'])['developmentEnabled']
    assert (root/'build/Build-Receipt.json').exists() and (root/'build/Debug-Build-Receipt.json').exists()
