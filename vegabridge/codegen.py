"""Run the official JavaScript TurboModule generator directly on Windows."""
import re
from pathlib import Path
from .project import tool_path


def generate_module(source,destination,settings,runner,namespace='MyModule'):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if source.suffix!='.ts' or not source.is_file():raise ValueError('Choose a TypeScript NativeModule interface.')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',namespace):raise ValueError('Use a valid C++ namespace identifier.')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Choose a new or empty generated-code folder; existing implementations are preserved.')
    node=tool_path(settings.get('node',''),'node.exe')
    generator=tool_path(settings.get('codegen',''),'cli.js')
    destination.mkdir(parents=True,exist_ok=True)
    runner.run([node,generator,'codegen',source,'--new','--outputPath',destination,'--namespace',namespace],timeout=120)
    files=sorted(path.relative_to(destination).as_posix() for path in destination.rglob('*') if path.is_file())
    if not any(path.endswith('Spec.h') for path in files) or not any(path.endswith('Spec.cpp') for path in files):
        raise RuntimeError('Codegen did not produce the expected native spec files.')
    return {'output':str(destination),'files':files,'compiled':False,'note':'Implement and integrate the generated C++ against your SDK contracts before device use.'}


def compile_bytecode(source,destination,settings,runner):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if source==destination:raise ValueError('Keep the JavaScript source; choose a separate bytecode output file.')
    compiler=tool_path(settings.get('hermes',''),'hermesc.exe')
    destination.parent.mkdir(parents=True,exist_ok=True)
    runner.run([compiler,'-emit-binary','-O','-out',destination,source],timeout=120)
    if not destination.is_file() or destination.stat().st_size<32:raise RuntimeError('Hermes did not produce a bytecode bundle.')
    return {'bytecode':str(destination),'bytes':destination.stat().st_size,'runtimeCompatibilityVerified':False}
