"""Bounded project search, environment checks and target ABI inspection."""
import os
import struct
from pathlib import Path
from .project import SKIP, TEXT_SUFFIXES, tool_path


def search_project(root, query, case_sensitive=False):
    root = Path(root).resolve()
    if not query:
        return []
    results, scanned = [], 0
    needle = query if case_sensitive else query.casefold()
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in sorted(dirs) if d not in SKIP and not d.startswith('.') and not (Path(folder)/d).is_symlink() and not (Path(folder)/d).is_junction()]
        for name in sorted(files):
            path = Path(folder) / name
            if path.suffix.lower() not in TEXT_SUFFIXES or path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root) or path.stat().st_size > 1024*1024:
                continue
            scanned += 1
            if scanned > 5000:
                return results
            try:
                for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                    if needle in (line if case_sensitive else line.casefold()):
                        results.append({'path':str(path), 'relative':path.relative_to(root).as_posix(), 'line':number, 'text':line.strip()[:300]})
                        if len(results) >= 1000:
                            return results
            except (OSError, UnicodeError):
                continue
    return results


def doctor(settings, runner):
    results=[]
    for name,key,binary,flag in [('Node/npm','node','node.exe','--version'),('Device bridge','adb','adb.exe','version'),('Windows QEMU','qemu','qemu-system-x86_64.exe','--version'),('Native compiler','clang','clang++.exe','--version'),('Hermes compiler','hermes','hermesc.exe','-version'),('CMS verifier','openssl','openssl.exe','version')]:
        try:
            path=tool_path(settings.get(key,''),binary)
            version=runner.run([path,flag],timeout=10,quiet=True).splitlines()[0]
            results.append({'tool':name,'ready':True,'detail':version})
        except Exception as e:
            results.append({'tool':name,'ready':False,'detail':str(e)})
    for arch in ['armv7','aarch64','x86_64']:
        root=Path(settings.get('sdk_root') or '.') / ('sysroot-'+arch)
        ready=(root/'usr/include').is_dir() and (root/'usr/lib').is_dir()
        results.append({'tool':'Vega '+arch+' target libraries','ready':ready,'detail':str(root) if ready else 'Import/configure this architecture’s owner-supplied SDK headers and libraries.'})
    return results


def elf_architecture(path):
    header=Path(path).read_bytes()[:64]
    if len(header)<52 or header[:4]!=b'\x7fELF' or header[5]!=1:
        raise ValueError('Expected a little-endian ELF binary, not a Windows PE or Android package')
    machine=struct.unpack_from('<H',header,18)[0]
    expected={40:('armv7',1),183:('aarch64',2),62:('x86_64',2)}
    if machine not in expected or header[4]!=expected[machine][1]:
        raise ValueError('Unsupported or inconsistent ELF target architecture')
    return expected[machine][0]
