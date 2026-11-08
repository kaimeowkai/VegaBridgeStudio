"""Separate planning workspaces with before/after source preservation gates."""
import hashlib
import json
import os
import stat
from pathlib import Path
from .android_migration import assess_android,render_plan
from .android_adapters import REGISTRY_VERSION,validate_rows

EXCLUDED={'.git','.gradle','.idea','.venv','node_modules','build','dist','stage','__pycache__','.cxx','.externalNativeBuild'}
MAX_FILES=50000
MAX_BYTES=2*1024*1024*1024


def fingerprint(source,check=lambda:None):
    source=Path(source)
    if source.is_symlink() or source.is_junction():raise ValueError('Select the actual source path, not a link')
    source=source.resolve()
    if not source.exists():raise ValueError('Source does not exist')
    files={};total=0
    def record(path,relative):
        nonlocal total
        check()
        if len(files)>=MAX_FILES:raise ValueError('Source preservation inventory exceeds 50,000 files')
        before=path.lstat()
        if path.is_symlink() or path.is_junction():
            files[relative]={'link':True,'sha256':hashlib.sha256(os.readlink(path).encode()).hexdigest()};return
        if not stat.S_ISREG(before.st_mode):raise ValueError('Source contains a special file; preservation cannot be established')
        if not path.resolve().is_relative_to(source if source.is_dir() else source.parent):raise ValueError('Source file escapes the selected input')
        total+=before.st_size
        if total>MAX_BYTES:raise ValueError('Source preservation inventory exceeds 2 GiB; choose a smaller project')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            while block:=stream.read(1024*1024):check();digest.update(block)
        after=path.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('Source changed while being inventoried; scan again')
        files[relative]={'sha256':digest.hexdigest(),'bytes':after.st_size,'mtimeNs':after.st_mtime_ns}
    def failed(error):raise RuntimeError('An input directory could not be read; preservation cannot be established') from error
    if source.is_file():record(source,source.name)
    else:
        for directory,dirs,names in os.walk(source,followlinks=False,onerror=failed):
            check();folder=Path(directory);retained=[]
            for name in sorted(dirs):
                if name in EXCLUDED:continue
                path=folder/name
                if path.is_symlink() or path.is_junction():record(path,path.relative_to(source).as_posix())
                else:retained.append(name)
            dirs[:]=retained
            for name in sorted(names):record(folder/name,(folder/name).relative_to(source).as_posix())
    canonical=json.dumps(files,sort_keys=True,separators=(',',':')).encode()
    return {'files':files,'fileCount':len(files),'bytesHashed':total,'inventorySha256':hashlib.sha256(canonical).hexdigest(),'excludedDirectories':sorted(EXCLUDED)}


def unchanged(expected,current):
    if expected['inventorySha256']!=current['inventorySha256']:
        raise RuntimeError('Original input changed since assessment. No conversion is allowed; assess it again.')


def prepare_import(source,check=lambda:None):
    source=Path(source)
    before=fingerprint(source,check);check();report=assess_android(source);check();after=fingerprint(source,check)
    unchanged(before,after)
    return {'sourcePath':str(source.resolve()),'assessment':report,'baseline':before,'sourcePreserved':True,'conversionPerformed':False}


def destination_path(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination==source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('The planning workspace must be separate from the original input, with no overlapping folders')
    if destination.exists():raise FileExistsError('Choose a new planning workspace; existing folders are never overwritten')
    return destination


def create_workspace(prepared,destination,rows,runtime=None,check=lambda:None):
    source=Path(prepared['sourcePath']);destination=destination_path(source,destination)
    mappings=validate_rows(prepared['assessment'],rows);unchanged(prepared['baseline'],fingerprint(source,check));check()
    destination.parent.mkdir(parents=True,exist_ok=True);destination.mkdir() # Exclusive creation; never adopt another folder.
    written=[]
    try:
        def save(name,value):
            check();path=destination/name
            with path.open('x',encoding='utf8') as output:
                written.append(path);output.write(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')
        save('assessment.json',prepared['assessment'])
        save('adapter-map.json',{'registryVersion':REGISTRY_VERSION,'kind':'Shared adapter plans','adapters':mappings,'implementationsVerified':False})
        save('source-baseline.json',prepared['baseline'])
        save('migration-plan.md',render_plan(prepared['assessment'])+'\n## Shared adapter review\n\n'+''.join('- '+row['id']+': '+row['adapter']+'; '+row['status']+'\n' for row in mappings))
        save('runtime-research.json',runtime or {'status':'Not checked','androidRuntimeImplemented':False,'apkExecutionTested':False})
        after=fingerprint(source,check);unchanged(prepared['baseline'],after);check()
        receipt={'sourcePreserved':True,'filesVerified':after['fileCount'],'inventorySha256':after['inventorySha256'],
            'scope':'All input files except the listed generated/VCS directories; links are inventoried without following them.',
            'excludedDirectories':after['excludedDirectories'],'sourceCopied':False,'conversionPerformed':False,'appBuilt':False,'appInstalled':False}
        save('preservation-receipt.json',receipt)
        save('workspace.json',{'schemaVersion':1,'sourcePath':str(source),'stage':'Planning only','conversionEnabled':False,'sourceInventorySha256':after['inventorySha256']})
        return {'workspace':str(destination),'preservation':receipt,'adapterCount':len(mappings)}
    except Exception:
        # Delete only exact files created here, never recurse or follow links.
        if destination.resolve()!=destination or destination.is_symlink() or destination.is_junction():raise
        for path in reversed(written):
            if path.parent==destination and path.is_file() and not path.is_symlink():path.unlink()
        try:destination.rmdir()
        except OSError:pass
        raise
