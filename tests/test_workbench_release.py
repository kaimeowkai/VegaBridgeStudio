import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import threading
import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication
from vegabridge.editor import CodeEditor
from vegabridge.navigation import project_files, match_score, Picker
from vegabridge.device_profiles import DeviceProfiles, connection_guidance
from vegabridge.devices import LocalBridge
from vegabridge.native_vm import NativeVm
from vegabridge.process import Runner, Cancelled


@pytest.fixture
def qt():
    return QApplication.instance() or QApplication([])


def test_quick_open_excludes_private_generated_and_linked_files(tmp_path):
    for name in ['src/App.tsx','src/control.cpp','private/note.js','node_modules/lib/index.js','.env','file.key','.git/config','build/a.js']:
        path = tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('x')
    assert project_files(tmp_path)==['src/App.tsx','src/control.cpp']
    assert match_score('sapp','src/App.tsx') is not None
    assert match_score('zzz','src/App.tsx') is None
    assert match_score('App','App.tsx') > match_score('app','a/path/p')


def test_picker_keeps_payload_after_sorting_and_filtering(qt):
    picker = Picker('Commands',[('Zulu','',0),('Alpha','Ctrl+P',1)])
    picker.query.setText('alpha')
    picker.choose()
    assert picker.chosen==1
    picker.close()


def test_editor_multiline_comment_indent_and_single_undo(qt,tmp_path):
    editor = CodeEditor(tmp_path/'App.tsx')
    editor.setPlainText('  first();\n  second();\nthird();')
    cursor = editor.textCursor()
    cursor.setPosition(0);cursor.setPosition(editor.document().findBlockByNumber(2).position(),QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor);editor.toggle_comment()
    assert editor.toPlainText()=='  // first();\n  // second();\nthird();'
    editor.undo()
    assert editor.toPlainText()=='  first();\n  second();\nthird();'
    editor.selectAll();editor.indent_selection();editor.indent_selection(outdent=True)
    assert editor.toPlainText()=='  first();\n  second();\nthird();'
    editor.go_to_line(3)
    assert editor.textCursor().blockNumber()==2
    with pytest.raises(ValueError):editor.go_to_line(4)
    editor.close()


def test_replace_does_not_reprocess_its_own_replacement_and_undo_is_one_step(qt,tmp_path):
    editor=CodeEditor(tmp_path/'App.tsx')
    editor.setPlainText('cat Cat category cat')
    assert editor.replace_all('cat','catcat',True,True)==2
    assert editor.toPlainText()=='catcat Cat category catcat'
    editor.undo()
    assert editor.toPlainText()=='cat Cat category cat'
    assert editor.replace_all('Cat','dog',False,True)==3
    assert editor.toPlainText()=='dog dog category dog'
    editor.close()


def test_comment_selection_preserves_utf16_positions_for_emoji_source(qt,tmp_path):
    editor=CodeEditor(tmp_path/'App.tsx');editor.setPlainText('const icon = "🚀";\nnext();')
    editor.selectAll();editor.toggle_comment()
    assert editor.textCursor().selectedText().replace('\u2029','\n')==editor.toPlainText()
    editor.close()


def test_connection_bookmarks_validate_and_replace_same_target(tmp_path):
    store=DeviceProfiles(tmp_path/'profiles.json')
    store.save('Living room','192.168.1.2','Wireless')
    store.save('Test target','192.168.1.2:5555','Wireless')
    store.save('USB test','USB123','USB')
    assert len(store.list())==2
    assert store.list()[0]['name']=='Test target'
    with pytest.raises(ValueError):store.save('x','host;echo unsafe','Wireless')
    with pytest.raises(ValueError):store.save('x','-s','USB')
    assert 'approve' in connection_guidance('unauthorized','USB')
    store.remove('USB123')
    assert len(store.list())==1


def test_reconnect_only_disconnects_requested_wireless_target(monkeypatch):
    import vegabridge.devices as devices
    monkeypatch.setattr(devices,'tool_path',lambda configured,name:name)
    class Recording:
        def __init__(self):self.calls=[]
        def run(self,args,**kwargs):
            self.calls.append(args)
            return '192.168.1.2:5555 device' if 'devices' in args else 'connected to 192.168.1.2:5555'
        def emit(self,text):pass
    runner=Recording()
    bridge=LocalBridge({'adb':'adb.exe','bridge_port':5048},runner,'192.168.1.2:5555')
    assert bridge.reconnect()[0]['state']=='device'
    assert runner.calls[0][-2:]==['disconnect','192.168.1.2:5555']
    assert all('kill-server' not in args and 'tcpip' not in args for args in runner.calls)
    bridge.serial='USB123'
    with pytest.raises(ValueError):bridge.reconnect()


def test_readiness_requires_vega_service_not_just_adb_online(monkeypatch):
    import vegabridge.devices as devices
    monkeypatch.setattr(devices,'tool_path',lambda configured,name:name)
    seen=[]
    monkeypatch.setattr(devices.LocalBridge,'shell',lambda self,command,**kw:seen.append((self.serial,command)) or '')
    bridge=LocalBridge({'adb':'adb.exe','bridge_port':5048},Runner(),'127.0.0.1:5573')
    monkeypatch.setattr(bridge,'connect',lambda address,**kw:None)
    monkeypatch.setattr(bridge,'devices',lambda:[{'serial':'127.0.0.1:5573','state':'device','kind':'Wireless'}])
    assert bridge.wait_until_ready('127.0.0.1:5573',timeout=1)[0]['state']=='device'
    assert seen==[('127.0.0.1:5573','vpm list packages >/dev/null')]
    cancelled=threading.Event();cancelled.set();bridge.runner=Runner(cancelled=cancelled)
    with pytest.raises(Cancelled):bridge.wait_until_ready('127.0.0.1:5573',timeout=1)


def test_vm_commands_refuse_reused_monitor_identity(monkeypatch,tmp_path):
    import vegabridge.native_vm as native
    calls=[]
    def command(port,method,args=None):
        calls.append(method)
        return {'name':'Other VM'}
    monkeypatch.setattr(native,'qmp_command',command)
    vm=NativeVm({'vm_port':5573});vm.monitor_port=50000
    with pytest.raises(RuntimeError,match='identity changed'):vm.command('stop')
    assert calls==['query-name']
    with pytest.raises(ValueError):vm.command('system_reset')


def test_vm_remote_ignores_toolbar_target_and_refuses_paused_guest(monkeypatch):
    import vegabridge.emulator_panel as panel
    class Vm:
        device_port=5573
        running=True
        def command(self,cmd):return {'running':self.running}
    vm=Vm();calls=[]
    monkeypatch.setattr(panel.NativeVm,'attach_managed',lambda settings:vm)
    class Bridge:
        def __init__(self,settings,runner,serial):self.serial=serial
        def shell(self,cmd,**kwargs):calls.append((self.serial,cmd))
    monkeypatch.setattr(panel,'LocalBridge',Bridge)
    panel.send_managed_key({},Runner(),'OK')
    assert calls==[('127.0.0.1:5573','inputd-cli button_press KEY_ENTER')]
    vm.running=False
    with pytest.raises(RuntimeError):panel.send_managed_key({},Runner(),'OK')
    assert len(calls)==1


def test_popout_moves_one_panel_and_docks_it_back(qt,tmp_path,monkeypatch):
    from vegabridge import app as workbench
    from vegabridge import emulator_panel
    from vegabridge.conversations import ConversationStore
    monkeypatch.setattr(workbench,'ConversationStore',lambda:ConversationStore(tmp_path/'chats'))
    monkeypatch.setattr(workbench,'save_settings',lambda _:None)
    monkeypatch.setattr(emulator_panel.EmulatorPane,'refresh',lambda self:None)
    window=workbench.Studio()
    pane=window.emulator_pane;controls=pane.controls;screen=pane.screen
    pane.toggle_popout();qt.processEvents()
    assert pane.popup is not None
    assert controls.parent() is pane.popup
    assert pane.screen is screen
    pane.popup.close();qt.processEvents()
    assert pane.popup is None and controls.parent() is pane
    assert pane.screen is screen
    window.close();qt.processEvents()


def test_live_frame_mailbox_drops_old_frames_and_bounds_gui_queue():
    from vegabridge.vm_stream import FrameMailbox
    mailbox=FrameMailbox()
    mailbox.put('first');mailbox.put('latest')
    assert mailbox.take()=='latest'
    mailbox.put('newer')
    assert mailbox.take() is None
    mailbox.acknowledge()
    assert mailbox.take()=='newer'


def test_live_capture_only_selects_owned_window_crops_chrome_and_stops(monkeypatch,qt):
    import numpy as np
    from types import SimpleNamespace
    import vegabridge.vm_stream as stream
    seen={}
    class Vm:
        pid=123;window_title='QEMU (VegaBridge test)';display_name='VegaBridge test'
        def command(self,command):return {'status':'running'}
    monkeypatch.setattr(stream.NativeVm,'attach_managed',lambda settings:Vm())
    monkeypatch.setattr(stream,'owned_window',lambda pid,title:999)
    pixels=np.zeros((100,100,4),dtype=np.uint8);pixels[:]=[255,10,5,255]
    frame=SimpleNamespace(frame_buffer=pixels,width=100,height=100)
    class Control:
        def is_finished(self):return False
        def stop(self):seen['stopped']=True
        def wait(self):pass
    class Capture:
        def __init__(self,**kwargs):seen.update(kwargs)
        def event(self,fn):setattr(self,fn.__name__,fn);return fn
        def start_free_threaded(self):
            self.on_frame_arrived(frame,Control());return Control()
    worker=stream.VmStream({},Capture,lambda hwnd:(10,20,80,64))
    images=[]
    worker.frame.connect(lambda image:(images.append(image),worker.cancelled.set()))
    worker.run()
    assert seen['window_hwnd']==999 and seen['monitor_index'] is None
    assert seen['stopped'] and len(images)==1
    pixels[:]=0
    assert images[0].width()==80 and images[0].height()==64
    assert images[0].pixelColor(0,0).red()==5
    with pytest.raises(RuntimeError):stream.frame_image(frame,(50,50,80,64))
