import hashlib
import struct
import zipfile
from pathlib import Path
import pytest
from vegabridge.apmf_codegen import host_jar,normalize_dependencies,replace_shell_path,generate_api


def fake_class(value=b'/bin/sh'):
    return b'\xca\xfe\xba\xbe\x00\x00\x00\x34'+struct.pack('>H',2)+b'\x01'+struct.pack('>H',len(value))+value+b'\x00\x01'


def test_host_adaptation_preserves_original_and_other_resources(tmp_path):
    source=tmp_path/'sdk.jar';shell=tmp_path/'Git with spaces/sh.exe';shell.parent.mkdir();shell.write_bytes(b'host')
    with zipfile.ZipFile(source,'w') as out:
        out.writestr('com/amazon/apmf/FsUtil.class',fake_class());out.writestr('resource.txt',b'original')
    before=source.read_bytes()
    target=host_jar(source,shell,tmp_path/'cache')
    assert source.read_bytes()==before and target!=source
    with zipfile.ZipFile(target) as out:
        assert out.read('resource.txt')==b'original'
        assert shell.as_posix().encode() in out.read('com/amazon/apmf/FsUtil.class')
    target.write_bytes(b'damaged cache')
    assert zipfile.is_zipfile(host_jar(source,shell,tmp_path/'cache'))


def test_signed_or_unexpected_sdk_is_not_modified(tmp_path):
    source=tmp_path/'sdk.jar';shell=tmp_path/'sh.exe';shell.write_bytes(b'host')
    with zipfile.ZipFile(source,'w') as out:
        out.writestr('META-INF/vendor.SF','signed');out.writestr('com/amazon/apmf/FsUtil.class',fake_class())
    before=source.read_bytes()
    with pytest.raises(ValueError,match='Signed SDK'):host_jar(source,shell,tmp_path/'cache')
    assert source.read_bytes()==before
    with pytest.raises(ValueError,match='exactly one'):replace_shell_path(fake_class(b'other'),shell)
    with pytest.raises(ValueError):replace_shell_path(b'not a class',shell)


def test_windows_make_dependencies_keep_escaped_spaces_and_continuations():
    data=b'idl: \\\r\n  C:\\SDK\\My\\ File\\api.idl\r\n'
    assert normalize_dependencies(data)==b'idl: \\\n  C:/SDK/My\\ File/api.idl\n'


def test_api_codegen_refuses_invalid_packages_and_existing_output(tmp_path):
    for packages in [[],['--options'],['com.amazon.apmf;danger']]:
        with pytest.raises(ValueError,match='IDL package'):generate_api(tmp_path/'out',packages,{},None)
    output=tmp_path/'out';output.mkdir();(output/'implementation.cpp').write_text('keep')
    with pytest.raises(ValueError,match='existing files'):generate_api(output,['com.amazon.apmf'],{},None)
    assert (output/'implementation.cpp').read_text()=='keep'
