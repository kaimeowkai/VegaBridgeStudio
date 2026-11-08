"""Windows host compatibility for an owner's external APMF IDL compiler.

No SDK classes or generated SDK bindings are distributed with Studio. A private
copy changes one host shell path; signed or unexpected SDK JARs are refused.
"""
import hashlib
import json
import os
import re
import shlex
import struct
import sys
import tempfile
import zipfile
from pathlib import Path
from .project import tool_path
from .storage import user_dir,atomic_write


def replace_shell_path(data,shell):
    if data[:4]!=b'\xca\xfe\xba\xbe':raise ValueError('Invalid Java class')
    count=struct.unpack_from('>H',data,8)[0]
    parts=[data[:10]];pos=10;index=1;changed=0
    sizes={3:4,4:4,5:8,6:8,7:2,8:2,9:4,10:4,11:4,12:4,15:3,16:2,17:4,18:4,19:2,20:2}
    try:
        while index<count:
            start=pos;tag=data[pos];pos+=1
            if tag==1:
                length=struct.unpack_from('>H',data,pos)[0]
                value=data[pos+2:pos+2+length];pos+=2+length
                if len(value)!=length:raise ValueError('Truncated Java class')
                if value==b'/bin/sh':value=Path(shell).as_posix().encode('utf8');changed+=1
                if len(value)>65535:raise ValueError('Shell path is too long')
                parts.append(bytes([tag])+struct.pack('>H',len(value))+value)
            else:
                pos+=sizes[tag];parts.append(data[start:pos]);index+=tag in (5,6)
            if pos>len(data):raise ValueError('Truncated Java class')
            index+=1
    except (KeyError,IndexError,struct.error) as error:
        raise ValueError('Unsupported Java constant pool') from error
    if changed!=1:raise ValueError('Unsupported APMF compiler: expected exactly one host shell path')
    parts.append(data[pos:])
    return b''.join(parts)


def host_jar(source,shell,cache=None):
    source=Path(source).resolve();shell=Path(shell).resolve()
    if not source.is_file() or source.stat().st_size>256*1024*1024:raise ValueError('Choose an APMF compiler JAR under 256 MiB')
    if not shell.is_file():raise ValueError('Configure Git for Windows sh.exe in SDK tools')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    key=hashlib.sha256((digest+'\0'+str(shell)).encode()).hexdigest()
    folder=Path(cache or user_dir()/'sdk-host-cache')/key
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/'apmfc-windows.jar'
    # Recreate from the original each time, so a cached file cannot silently drift.
    with zipfile.ZipFile(source) as archive:
        entries=archive.infolist()
        if sum(item.file_size for item in entries)>512*1024*1024:raise ValueError('APMF JAR contents exceed 512 MiB')
        if any(item.filename.upper().endswith(('.SF','.RSA','.DSA','.EC')) for item in entries):
            raise ValueError('Signed SDK JARs are preserved; Windows host adaptation is unavailable for this compiler')
        if len({item.filename for item in entries})!=len(entries):raise ValueError('Duplicate JAR entries')
        fd,name=tempfile.mkstemp(dir=folder,suffix='.jar');os.close(fd)
        changed=0
        try:
            with zipfile.ZipFile(name,'w',zipfile.ZIP_DEFLATED) as output:
                for item in entries:
                    data=archive.read(item)
                    if item.filename=='com/amazon/apmf/FsUtil.class':
                        data=replace_shell_path(data,shell);changed+=1
                    output.writestr(item,data)
            if changed!=1:raise ValueError('Unsupported APMF compiler: host utility class is missing')
            os.replace(name,target)
        finally:Path(name).unlink(missing_ok=True)
    atomic_write(folder/'receipt.json',json.dumps({'originalSha256':digest,
        'hostCopySha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'adaptation':'Single host shell path; original preserved; no SDK redistribution'},indent=2).encode())
    return target


def normalize_dependencies(data):
    # The SDK dependency reader expects LF and POSIX separators. Preserve Make
    # escapes for spaces, #, $, backslashes and continuations.
    return re.sub(rb'\\(?![ #$\\\n])',b'/',data.replace(b'\r\n',b'\n'))


def preprocess(clang,arguments,runner):
    result=runner.run([clang,*arguments],binary=True,quiet=True,timeout=60)
    for index,arg in enumerate(arguments):
        name=arguments[index+1] if arg=='-MF' and index+1<len(arguments) else arg[3:] if arg.startswith('-MF') else ''
        if name:
            path=Path(name)
            if path.stat().st_size>8*1024*1024:raise ValueError('Dependency file exceeds 8 MiB')
            path.write_bytes(normalize_dependencies(path.read_bytes()))
    return result


def generate_api(destination,packages,settings,runner,arch='x86_64'):
    if arch not in {'armv7','aarch64','x86_64'}:raise ValueError('Choose a supported architecture')
    if not packages or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+',p) for p in packages):
        raise ValueError('Use IDL package names such as com.amazon.apmf')
    destination=Path(destination).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Choose a new or empty generated-code folder; existing files are preserved')
    java=tool_path(settings.get('java',''),'java.exe')
    shell=tool_path(settings.get('git_sh',''),'sh.exe')
    compiler=Path(tool_path(settings.get('clang',''),'clang++.exe')).with_name('clang.exe')
    if not compiler.is_file():raise ValueError('The Windows LLVM installation must include clang.exe')
    api=Path(settings.get('api_root') or '.')/arch/'include'
    if not api.is_dir():raise ValueError('Configure the external platform API root before generating bindings')
    original=Path(settings.get('apmfc',''))
    jar=host_jar(original,shell)
    if getattr(sys,'frozen',False):
        cli=Path(sys.executable).with_name('VegaBridgeCLI.exe')
        if not cli.is_file():raise ValueError('Keep VegaBridgeCLI.exe beside Studio for IDL preprocessing')
        command=[str(cli),'_idl-preprocess',str(compiler)]
    else:command=[sys.executable,str(Path(__file__).resolve().parents[1]/'run_cli.py'),'_idl-preprocess',str(compiler)]
    preprocessor=' '.join(shlex.quote(Path(p).as_posix()) for p in command)
    # Native Java / Windows Clang / Git for Windows shell only. No Linux host.
    env=dict(os.environ,TMPDIR=tempfile.gettempdir(),MSYS_NO_PATHCONV='1')
    destination.mkdir(parents=True,exist_ok=True)
    runner.run([java,'-jar',jar,'compile-idl','--no-symlink-resources','--no-fsync','-l','cpp',
        '--c-preprocessor='+preprocessor,'-I',api,'-o',destination,*packages],env=env,timeout=180)
    files=[p for p in destination.rglob('*') if p.is_file()]
    if not any(p.suffix=='.h' for p in files):raise RuntimeError('APMF compiler did not produce C++ headers')
    return {'output':str(destination),'includeDirectory':str(destination/'include'),'files':len(files),
        'architecture':arch,'compiled':False,'runtimeVerified':False,
        'note':'Compile and test the generated bindings with the matching SDK runtime and declared app contracts.'}
