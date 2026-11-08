import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from vegabridge.app import Studio, SettingsDialog
from vegabridge.project import create_project


def test_native_workbench_opens_source_saves_and_displays_device_types(tmp_path,monkeypatch):
    from vegabridge import app as workbench
    from vegabridge.conversations import ConversationStore
    monkeypatch.setattr(workbench,'ConversationStore',lambda:ConversationStore(tmp_path/'chats'))
    monkeypatch.setattr(workbench,'save_settings',lambda _:None)
    app = QApplication.instance() or QApplication([])
    root = create_project(tmp_path / "app", "GUI Test", "com.example.guitest")
    window = Studio(root)
    window.show()
    app.processEvents()
    assert window.project == root
    assert window.editors.count() == 2
    editor = window.current_editor()
    editor.insertPlainText("// GUI test\n")
    assert editor.document().isModified()
    assert window.save_all()
    assert (root / "index.js").read_text().startswith("// GUI test")
    window.set_devices([{"kind": "USB", "serial": "USBTEST", "state": "device"}, {"kind": "Wireless", "serial": "127.0.0.1:5555", "state": "unauthorized"}])
    assert window.target.currentData()["serial"] == "USBTEST"
    assert window.target.itemData(2) is None
    window.set_devices([{"kind": "USB", "serial": "USBTEST", "state": "device"}, {"kind": "Wireless", "serial": "127.0.0.1:5573", "state": "device"}], prefer="127.0.0.1:5573")
    assert window.target.currentData()["serial"] == "127.0.0.1:5573"
    window.set_devices([{"kind":"USB","serial":"DIFFERENT-TARGET","state":"device"}])
    assert window.target.currentData() is None  # Never silently redirect a dropped target.
    settings = SettingsDialog(window.settings, window)
    assert settings.fields["model"].text()
    settings.reject()
    from PySide6.QtWidgets import QDockWidget
    assistant=window.findChild(QDockWidget,'assistant-dock');assistant.hide();window.show_assistant()
    assert not assistant.isHidden()
    editor=window.editors.widget(0)
    frame={'name':'App','source':{'path':str(root/'index.js')},'line':1}
    window.javascript_debugger.show_source(frame)
    assert window.javascript_debugger.source.toPlainText()==editor.toPlainText()
    window.close()
    app.processEvents()
