"""External portable updater: wait for Studio, verify, swap, retain rollback."""
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from .updates import verify_install,version_tuple


def wait_for_studio(pid,expected_exe,timeout=180):
    if os.name!='nt':raise RuntimeError('The automatic updater requires Windows')
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    api.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    handle=api.OpenProcess(0x100000|0x1000,False,pid)
    if not handle:
        if ctypes.get_last_error()==87:return
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        length=wintypes.DWORD(32768);name=ctypes.create_unicode_buffer(length.value)
        if not api.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        if Path(name.value).resolve()!=Path(expected_exe).resolve():raise RuntimeError('The update process identity changed')
        if api.WaitForSingleObject(handle,int(timeout*1000))!=0:
            raise TimeoutError('Studio did not exit; its installation was preserved')
    finally:api.CloseHandle(handle)


def apply_plan(path,wait=True,restart=True):
    path=Path(path).resolve()
    if path.stat().st_size>16384:raise ValueError('Invalid update plan')
    plan=json.loads(path.read_text(encoding='utf-8'))
    if plan.get('schema')!=1:raise ValueError('Unsupported update plan')
    target,stage,backup=(Path(plan[key]) for key in ['target','stage','backup'])
    for folder in [target,stage,backup]:
        if not folder.is_absolute() or folder.is_symlink() or folder.is_junction():raise ValueError('Update folders must be ordinary absolute directories')
    target,stage,backup=(folder.resolve() for folder in [target,stage,backup])
    if stage.parent!=target.parent or backup.parent!=target.parent or not stage.name.startswith('.vegabridge-update-') or not backup.name.startswith(target.name+'.previous-'):
        raise ValueError('Invalid portable update folder layout')
    if backup.exists():raise ValueError('Rollback folder already exists')
    if wait:wait_for_studio(int(plan['pid']),target/'VegaBridgeStudio.exe')
    previous=verify_install(target);incoming=verify_install(stage)
    if previous['version']!=plan['previousVersion'] or incoming['version']!=plan['version'] or version_tuple(incoming['version'])<=version_tuple(previous['version']):
        raise ValueError('Update versions changed; installation was preserved')
    moved=False
    try:
        # Retry only this known directory rename if an antivirus file scan holds a handle.
        for attempt in range(20):
            try:target.rename(backup);moved=True;break
            except PermissionError:
                if attempt==19:raise
                time.sleep(.25)
        stage.rename(target)
    except Exception:
        if moved and not target.exists():backup.rename(target)
        raise
    receipt={'installed':True,'version':incoming['version'],'previousVersion':previous['version'],
             'target':str(target),'rollback':str(backup),'personalDataTouched':False,'oldInstallationDeleted':False}
    (path.parent/'Update-Receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    if restart:
        subprocess.Popen([str(target/'VegaBridgeStudio.exe')],cwd=str(target),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    return receipt


def main():
    import argparse
    parser=argparse.ArgumentParser(description='VegaBridge portable update worker')
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--no-restart',action='store_true')
    args=parser.parse_args()
    try:apply_plan(args.plan,restart=not args.no_restart)
    except Exception as error:
        failure={'installed':False,'error':str(error),'oldInstallationDeleted':False}
        try:(args.plan.parent/'Update-Receipt.json').write_text(json.dumps(failure,indent=2)+'\n',encoding='utf-8')
        except OSError:pass
        return 1
    return 0
