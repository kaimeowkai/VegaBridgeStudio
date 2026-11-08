from pathlib import Path
import json
import os
import pytest
from vegabridge.gallery import entries
from vegabridge.project import create_project, metadata
from vegabridge.workspace_tools import search_project,elf_architecture
from vegabridge.theme import stylesheet,apply_theme


def test_gallery_creates_standalone_typed_project_and_unique_twenty(tmp_path):
    catalog=entries()
    assert len(catalog)==20 and len({x['id'] for x in catalog})==20
    assert sum(x['category']=='Game' for x in catalog)==5
    root=create_project(tmp_path/'sample','A new original project','com.example.original','focus-harbor','TypeScript')
    assert metadata(root)['component']=='com.example.original.main'
    assert (root/'index.tsx').exists() and not (root/'index.js').exists()
    assert 'index.tsx' in json.loads((root/'package.json').read_text())['scripts']['bundle']
    assert (root/'assets/image/hello.png').read_bytes().startswith(b'\x89PNG')
    assert json.loads((root/'SAMPLE-INFO.json').read_text())['requiresNetwork'] is False


def test_search_excludes_generated_files_and_navigable_line_numbers(tmp_path):
    (tmp_path/'src').mkdir();(tmp_path/'node_modules').mkdir()
    (tmp_path/'src/view.tsx').write_text('first\nconst Focus = 1;\n')
    (tmp_path/'node_modules/ignored.js').write_text('Focus')
    hits=search_project(tmp_path,'focus')
    assert len(hits)==1 and hits[0]['line']==2 and hits[0]['relative']=='src/view.tsx'
    assert search_project(tmp_path,'focus',True)==[]


def test_themes_include_green_black_and_editor_palette():
    from PySide6.QtWidgets import QApplication
    from vegabridge import theme
    from vegabridge.editor import CodeEditor
    app=QApplication.instance() or QApplication([])
    editor=CodeEditor();editor.setPlainText('const neon = 1;')
    apply_theme(app,'Matrix')
    assert '#000000' in app.styleSheet() and '#00ff66' in app.styleSheet()
    assert theme.editor_color('keyword','wrong')=='#00ff66'
    apply_theme(app,'Daylight');assert theme.editor_color('background','wrong')=='#ffffff'
    apply_theme(app,'Harbor Dark');editor.deleteLater()


def test_single_instance_does_not_open_second_listener(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from vegabridge import instance
    monkeypatch.setattr(instance,'user_dir',lambda:tmp_path)
    app=QApplication.instance() or QApplication([])
    first=instance.SingleInstance();second=instance.SingleInstance()
    assert first.acquire()
    assert not second.acquire()
    app.processEvents()
    first.close()


def test_elf_inspector_refuses_windows_and_unknown_targets(tmp_path):
    path=tmp_path/'binary'
    path.write_bytes(b'MZ'+b'\0'*62)
    with pytest.raises(ValueError):elf_architecture(path)
    data=bytearray(64);data[:6]=b'\x7fELF\x02\x01';data[18:20]=(62).to_bytes(2,'little');path.write_bytes(data)
    assert elf_architecture(path)=='x86_64'
