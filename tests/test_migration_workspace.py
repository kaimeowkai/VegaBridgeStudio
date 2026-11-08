import json
import threading
import time
from pathlib import Path
import pytest
from vegabridge.migration_workspace import fingerprint,prepare_import,create_workspace,destination_path
from vegabridge.android_adapters import adapter_rows,validate_rows
from vegabridge.android_runtime_probe import parse_observations,summarize,collect_runtime,COMMAND


def source(root):
    root.mkdir();(root/'AndroidManifest.xml').write_text('<manifest/>')
    (root/'Logic.java').write_text('class Logic {int answer(){return 24;}}')
    (root/'Screen.java').write_text('import android.view.View; import android.content.SharedPreferences; class Screen {}')
    return root


def test_workspace_writes_only_planning_files_and_preserves_original_including_signing_files(tmp_path):
    root=source(tmp_path/'original');(root/'owner.keystore').write_bytes(b'synthetic signing-file preservation sentinel')
    before=fingerprint(root);prepared=prepare_import(root);rows=adapter_rows(prepared['assessment'])
    row=next(row for row in rows if row['id']=='android-storage');row['adapter']='preserve-data-format';row['status']='planned';row['notes']='Use shared storage tests'
    destination=tmp_path/'separate/plan';result=create_workspace(prepared,destination,rows)
    assert fingerprint(root)==before and result['preservation']['sourceCopied'] is False
    assert result['preservation']['conversionPerformed'] is False and result['preservation']['appInstalled'] is False
    assert {p.name for p in destination.iterdir()}=={'assessment.json','adapter-map.json','source-baseline.json','migration-plan.md','runtime-research.json','preservation-receipt.json','workspace.json'}
    assert all(b'synthetic signing-file preservation sentinel' not in p.read_bytes() for p in destination.iterdir())
    saved=json.loads((destination/'adapter-map.json').read_text())
    assert any(item['adapter']=='preserve-data-format' and item['status']=='planned' for item in saved['adapters'])
    assert saved['implementationsVerified'] is False


@pytest.mark.parametrize('relation',['same','inside','ancestor'])
def test_overlapping_workspace_paths_are_refused_before_any_write(tmp_path,relation):
    root=source(tmp_path/'original');prepared=prepare_import(root)
    destination={'same':root,'inside':root/'plan','ancestor':tmp_path}[relation]
    with pytest.raises(ValueError,match='separate'):create_workspace(prepared,destination,adapter_rows(prepared['assessment']))
    assert not (root/'plan').exists()


def test_source_changes_and_existing_workspace_are_refused(tmp_path):
    root=source(tmp_path/'original');prepared=prepare_import(root);rows=adapter_rows(prepared['assessment'])
    (root/'Logic.java').write_text('changed externally')
    with pytest.raises(RuntimeError,match='changed since'):create_workspace(prepared,tmp_path/'plan',rows)
    assert not (tmp_path/'plan').exists()
    prepared=prepare_import(root);destination=tmp_path/'existing';destination.mkdir();(destination/'keep').write_text('owner data')
    with pytest.raises(FileExistsError):create_workspace(prepared,destination,adapter_rows(prepared['assessment']))
    assert (destination/'keep').read_text()=='owner data'


def test_cancel_rolls_back_only_owned_output_and_never_changes_source(tmp_path):
    from vegabridge.process import Cancelled
    root=source(tmp_path/'original');prepared=prepare_import(root);before=fingerprint(root);destination=tmp_path/'plan'
    def check():
        if (destination/'assessment.json').exists():raise Cancelled('test cancellation')
    with pytest.raises(Cancelled):create_workspace(prepared,destination,adapter_rows(prepared['assessment']),check=check)
    assert not destination.exists() and fingerprint(root)==before


def test_missing_coverage_or_fake_verified_adapter_is_not_accepted(tmp_path):
    root=source(tmp_path/'original');report=prepare_import(root)['assessment'];rows=adapter_rows(report)
    with pytest.raises(ValueError,match='coverage'):validate_rows(report,rows[:-1])
    rows[0]['implementationVerified']=True
    assert validate_rows(report,rows)[0]['implementationVerified'] is False
    rows[0]['status']='implemented'
    with pytest.raises(ValueError):validate_rows(report,rows)


def test_generated_directories_excluded_but_original_configuration_inventoried(tmp_path):
    root=source(tmp_path/'original');(root/'build').mkdir();(root/'build/generated').write_text('cache')
    (root/'local.properties').write_text('synthetic local config');baseline=fingerprint(root)
    assert 'local.properties' in baseline['files'] and 'build/generated' not in baseline['files']
    assert 'build' in baseline['excludedDirectories']


def test_runtime_probe_distinguishes_observation_from_execution_and_preserves_scope():
    text='MACHINE=x86_64\nLONG_BIT=64\nMEM_TOTAL_KB=4096000\nNODE=/dev/kvm:missing\nNODE=/dev/binder:missing\nCAP_EFF=0000\nAPP_PROCESS=not-on-PATH\n'
    parsed=parse_observations(text,'Developer shell');report=summarize([parsed])
    assert report['apkExecutionTested'] is False and report['allAndroidAppsSupported'] is False
    assert len(report['unresolvedPrerequisites'])==2
    assert '\n' not in COMMAND and 'mount ' not in COMMAND and 'chmod ' not in COMMAND
    class Bridge:
        def shell(self,*a,**k):return text
        def component_shell(self,*a,**k):raise RuntimeError('unavailable')
    result=collect_runtime(Bridge(),'com.example.app.main')
    assert len(result['observations'])==1 and result['contextLimitations']


def test_gui_review_preserves_choices_creates_workspace_and_never_enables_conversion(tmp_path,monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication,QWidget,QComboBox
    from vegabridge.android_import import AndroidImportDialog
    root=source(tmp_path/'original');before=fingerprint(root)
    app=QApplication.instance() or QApplication([])
    class Host(QWidget):
        settings={};project=None
        def __init__(self):super().__init__();self.target=QComboBox();self.target.addItem('No target',None)
    host=Host();dialog=AndroidImportDialog(host);dialog.source.setText(str(root));dialog.destination.setText(str(tmp_path/'workspace'));dialog.show();dialog.scan()
    def wait():
        deadline=time.monotonic()+8
        while dialog.worker and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
        assert dialog.worker is None
    wait();assert dialog.prepared and dialog.save.isEnabled()
    row=next(i for i,value in enumerate(dialog.rows) if value['id']=='android-storage')
    dialog.mapping.selectRow(row);app.processEvents()
    choices=dialog.mapping.cellWidget(row,2);choices.setCurrentIndex(choices.findData('preserve-data-format'))
    state=dialog.mapping.cellWidget(row,3);state.setCurrentIndex(state.findData('planned'));dialog.notes.setPlainText('Shared implementation, no app rewrite')
    dialog.save_workspace();wait()
    assert dialog.created and fingerprint(root)==before and not dialog.save.isEnabled()
    mappings=json.loads((tmp_path/'workspace/adapter-map.json').read_text())['adapters']
    assert any(value['adapter']=='preserve-data-format' and value['notes']=='Shared implementation, no app rewrite' for value in mappings)
    assert json.loads((tmp_path/'workspace/workspace.json').read_text())['conversionEnabled'] is False
    dialog.close();host.close();app.processEvents()
