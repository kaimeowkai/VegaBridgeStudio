import json
import zipfile
from pathlib import Path
import pytest
from vegabridge.android_migration import assess_android,render_plan,write_plan


def put(root,name,text):
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf8');return path


def test_native_source_separates_android_work_from_logic_candidates(tmp_path):
    root=tmp_path/'android'
    put(root,'app/src/main/AndroidManifest.xml','<manifest xmlns:android="http://schemas.android.com/apk/res/android"><uses-permission android:name="android.permission.INTERNET"/></manifest>')
    put(root,'app/src/main/Calculator.kt','fun answer(seed: Int) = (seed + 5) * 2')
    put(root,'app/src/main/Screen.kt','import androidx.compose.runtime.*\nimport android.content.SharedPreferences\nclass Screen')
    before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    report=assess_android(root)
    assert report['recommendedPath']=='Native Android source migration'
    assert {item['id'] for item in report['findings']}=={'android-ui','android-storage','android-platform-api'}
    assert report['logicReviewCandidates']==['app/src/main/Calculator.kt']
    assert report['manifestPermissions']==['android.permission.INTERNET']
    assert before=={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert report['directApkExecutionSupported'] is False


def test_react_native_detection_never_executes_scripts_or_exports_dependency_urls(tmp_path):
    root=tmp_path/'rn'
    put(root,'package.json',json.dumps({'dependencies':{'react-native':'0.83','custom-module':'https://user:secret@example.invalid/private'},'scripts':{'preinstall':'THIS MUST NEVER RUN'}}))
    put(root,'App.tsx','export function App() {return null;}')
    put(root,'node_modules/vendor/Bad.java','import android.app.Activity;')
    put(root,'build/Bad.kt','import android.widget.TextView')
    report=assess_android(root);serialized=json.dumps(report)
    assert report['recommendedPath']=='React Native source migration'
    assert report['findings']==[]
    assert 'secret' not in serialized and 'THIS MUST NEVER RUN' not in serialized
    assert report['dependencyNames']==['custom-module','react-native']


def test_gradle_and_catalog_dependency_names_are_inventory_not_executed_builds(tmp_path):
    put(tmp_path,'build.gradle.kts','dependencies { implementation("androidx.core:core-ktx:1.0"); api("org.example:math:2.0") }')
    put(tmp_path,'gradle/libs.versions.toml','[libraries]\ncompose = { module = "androidx.compose.ui:ui", version = "1" }\nmath = {group = "org.example", name = "math"}\n')
    report=assess_android(tmp_path)
    assert report['dependencyNames']==['androidx.compose.ui:ui','androidx.core:core-ktx','org.example:math']


def test_generic_android_import_is_not_labelled_as_a_logic_candidate(tmp_path):
    put(tmp_path,'Device.java','import android.os.Build; class Device {String model=Build.MODEL;}')
    report=assess_android(tmp_path)
    assert report['logicCandidateCount']==0
    assert 'android-platform-api' in {item['id'] for item in report['findings']}


@pytest.mark.parametrize('source,expected',[
 ('import androidx.media3.exoplayer.ExoPlayer','android-media'),
 ('import com.android.billingclient.api.BillingClient','android-purchases-licensing'),
 ('import com.google.android.gms.auth.GoogleSignIn','google-services'),
 ('import androidx.work.WorkManager','android-background'),
 ('import android.bluetooth.BluetoothAdapter','android-connectivity'),
 ('#include <jni.h>','android-native-abi'),
 ('import android.webkit.WebView','webview-bridge'),
 ('boolean onTouchEvent(MotionEvent e)','touch-input'),
])
def test_platform_indicators_produce_review_tasks(tmp_path,source,expected):
    put(tmp_path,'Main.java',source)
    assert expected in {item['id'] for item in assess_android(tmp_path)['findings']}


def test_apk_inventory_does_not_extract_execute_or_claim_binary_manifest_decoding(tmp_path):
    apk=tmp_path/'test.apk'
    with zipfile.ZipFile(apk,'w') as archive:
        archive.writestr('AndroidManifest.xml',b'\x03\0\x08\0binary manifest')
        archive.writestr('classes.dex',b'dex\n035\0')
        archive.writestr('lib/arm64-v8a/libsample.so',b'not executed')
    before=apk.read_bytes();report=assess_android(apk)
    assert report['dexFiles']==1 and report['nativeAbis']==['arm64-v8a']
    assert report['manifestPermissions']==[] and 'not decoded' in report['manifestStatus']
    assert list(tmp_path.iterdir())==[apk] and apk.read_bytes()==before
    assert 'No DEX decompilation' in render_plan(report)


def test_unsafe_apk_names_are_refused(tmp_path):
    apk=tmp_path/'bad.apk'
    with zipfile.ZipFile(apk,'w') as archive:
        archive.writestr('AndroidManifest.xml','<manifest/>');archive.writestr('../outside','no')
    with pytest.raises(ValueError,match='Unsafe'):assess_android(apk)


def test_plan_is_separate_and_existing_reports_are_never_overwritten(tmp_path):
    root=tmp_path/'source';put(root,'Main.java','class Main {}');report=assess_android(root)
    with pytest.raises(ValueError,match='outside'):write_plan(report,root,root/'plan.md')
    destination=tmp_path/'reports/plan.md';write_plan(report,root,destination)
    assert 'Working methodology' in destination.read_text() and 'not a compatibility score' in destination.read_text()
    with pytest.raises(FileExistsError):write_plan(report,root,destination)


def test_scan_limits_are_explicit_and_private_sources_are_pruned(tmp_path,monkeypatch):
    from vegabridge import android_migration
    monkeypatch.setattr(android_migration,'MAX_FILES',2)
    for index in range(4):put(tmp_path,f'Logic{index}.kt','fun count() = 1')
    put(tmp_path,'secrets/Private.kt','import android.app.Activity;')
    report=assess_android(tmp_path)
    assert report['scanLimited'] and report['filesConsidered']==2
    assert all('Private.kt' not in str(item) for item in report['findings'])


def test_cli_assessment_reports_json_without_running_a_build(tmp_path,capsys):
    from vegabridge.cli import main
    put(tmp_path,'Logic.java','class Logic { int answer() {return 24;} }')
    assert main(['--json','assess-android',str(tmp_path)])==0
    report=json.loads(capsys.readouterr().out)
    assert report['readOnly'] and report['logicCandidateCount']==1
