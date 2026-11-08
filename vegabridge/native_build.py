"""Windows LLVM cross-compilation against owner-supplied Vega target sysroots.

This builds native executables/libraries; adding platform APIs still requires
their SDK headers/libraries and the application's C++/IDL integration.
"""
from pathlib import Path
from .project import tool_path
from .workspace_tools import elf_architecture

TARGETS={'armv7':'armv7a-linux-gnueabihf','aarch64':'aarch64-linux-gnu','x86_64':'x86_64-linux-gnu'}


def compile_source(source, destination, settings, runner, arch='armv7', shared=False):
    if arch not in TARGETS:
        raise ValueError('Choose armv7, aarch64 or x86_64')
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if source.suffix not in {'.c','.cpp','.cc','.cxx'}:
        raise ValueError('Select a C or C++ source file')
    compiler=Path(tool_path(settings.get('clang',''),'clang++.exe'))
    if source.suffix=='.c':
        compiler=compiler.with_name('clang.exe')
        if not compiler.is_file():
            raise ValueError('The Windows LLVM distribution must also include clang.exe for C compilation')
    sysroot=Path(settings.get('sdk_root') or '.')/('sysroot-'+arch)
    if not (sysroot/'usr/include').is_dir():
        raise ValueError('Configure the imported Vega SDK sysroots in Settings')
    destination.parent.mkdir(parents=True,exist_ok=True)
    prefix={'armv7':'arm-oe-linux-gnueabi','aarch64':'aarch64-oe-linux','x86_64':'x86_64-oe-linux'}[arch]
    gcc_dirs=list((sysroot/'usr/lib'/prefix).glob('11.*'))
    if len(gcc_dirs)!=1:
        raise ValueError('The Vega sysroot is missing its matching GCC startup objects and runtime libraries')
    args=[compiler,'--target='+TARGETS[arch],'--sysroot='+str(sysroot),'--gcc-install-dir='+str(gcc_dirs[0]),
          '-fuse-ld=lld','-rtlib=libgcc','-unwindlib=libgcc','-O2','-fPIC','-B'+str(sysroot/'usr/lib')]
    if not shared:
        args+=['-no-pie']
        if arch=='x86_64':
            # Vega's x64 guest keeps its loader in /lib, unlike Clang's
            # generic Linux default /lib64. The latter builds but cannot run.
            args+=['-Wl,--dynamic-linker=/lib/ld-linux-x86-64.so.2']
    if source.suffix!='.c':
        args+=['-stdlib=libc++','-nostdlib++','-fno-sized-deallocation','-std=c++17','-isystem',sysroot/'usr/include/c++/v1']
    if shared:
        args+=['-shared','-Wl,--no-undefined']
    args += [source]
    if source.suffix!='.c':
        # App namespaces do not expose the host's private libc++ SONAME. Link
        # the SDK's libc++/ABI archives into our own artifact rather than assume
        # an undeclared system library will be visible at runtime.
        args += ['-Wl,--start-group',sysroot/'usr/lib/libc++.a',sysroot/'usr/lib/libc++abi.a',
                 '-Wl,--end-group','-pthread','-ldl']
    args += ['-o',destination]
    runner.run(args,timeout=180)
    actual=elf_architecture(destination)
    if actual!=arch:
        raise RuntimeError('Compiler produced a different architecture; refusing this artifact')
    runner.emit('Native '+arch+' ELF verified: '+str(destination))
    return str(destination)
