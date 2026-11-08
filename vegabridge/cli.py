"""Native Windows command-line companion to the graphical workbench."""
import argparse
import json
import sys
from pathlib import Path
from .storage import load_settings
from .process import Runner


def main(argv=None):
    parser=argparse.ArgumentParser(prog='VegaBridgeCLI', description='Windows-native Vega project, build, package and device tools')
    parser.add_argument('--json', action='store_true')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('templates')
    sub.add_parser('doctor')
    sub.add_parser('devices')
    emulator=sub.add_parser('emulator')
    emulator.add_argument('action',choices=['start','status','stop'])
    create=sub.add_parser('create')
    create.add_argument('folder',type=Path)
    create.add_argument('--title',required=True)
    create.add_argument('--id',required=True)
    create.add_argument('--template',default='')
    create.add_argument('--language',choices=['JavaScript','TypeScript'],default='JavaScript')
    build=sub.add_parser('build');build.add_argument('folder',type=Path)
    check=sub.add_parser('validate');check.add_argument('package',type=Path)
    install=sub.add_parser('install');install.add_argument('package',type=Path);install.add_argument('--device',required=True);install.add_argument('--launch',default='')
    run=sub.add_parser('run');run.add_argument('component');run.add_argument('--device',required=True)
    wake=sub.add_parser('keep-awake');wake.add_argument('--device',required=True);wake.add_argument('--minutes',type=int,default=30)
    compile=sub.add_parser('compile');compile.add_argument('source',type=Path);compile.add_argument('-o','--output',type=Path,required=True);compile.add_argument('--arch',choices=['armv7','aarch64','x86_64'],default='armv7');compile.add_argument('--shared',action='store_true')
    codegen=sub.add_parser('codegen');codegen.add_argument('source',type=Path);codegen.add_argument('-o','--output',type=Path,required=True);codegen.add_argument('--namespace',default='MyModule')
    bytecode=sub.add_parser('bytecode');bytecode.add_argument('source',type=Path);bytecode.add_argument('-o','--output',type=Path,required=True)
    args=parser.parse_args(argv)
    runner=Runner(lambda text:print(text,file=sys.stderr if args.json else sys.stdout))
    settings=load_settings()
    try:
        if args.command=='templates':
            from .gallery import entries
            result=entries()
        elif args.command=='create':
            from .project import create_project
            result={'project':str(create_project(args.folder,args.title,args.id,args.template,args.language))}
        elif args.command=='build':
            from .project import build
            result={'package':build(args.folder,settings,runner)}
        elif args.command=='devices':
            from .devices import LocalBridge
            result=LocalBridge(settings,runner).devices()
        elif args.command=='doctor':
            from .workspace_tools import doctor
            result=doctor(settings,runner)
        elif args.command=='validate':
            from .package import verify_package
            result=verify_package(args.package,settings,runner)
        elif args.command=='compile':
            from .native_build import compile_source
            result={'nativeArtifact':compile_source(args.source,args.output,settings,runner,args.arch,args.shared)}
        elif args.command=='codegen':
            from .codegen import generate_module
            result=generate_module(args.source,args.output,settings,runner,args.namespace)
        elif args.command=='bytecode':
            from .codegen import compile_bytecode
            result=compile_bytecode(args.source,args.output,settings,runner)
        elif args.command=='emulator':
            from .native_vm import NativeVm, managed_vm_command
            if args.action=='start':
                NativeVm(settings).run(runner)
                result={'emulatorStopped':True}
            else:
                result=managed_vm_command('query-status' if args.action=='status' else 'quit')
        elif args.command=='install':
            from .devices import LocalBridge
            bridge=LocalBridge(settings,runner,args.device)
            bridge.install(args.package)
            if args.launch:bridge.launch(args.launch)
            result={'installationVerified':True,'launchRequested':bool(args.launch),'runtimeVerified':False}
        elif args.command=='run':
            from .devices import LocalBridge
            bridge=LocalBridge(settings,runner,args.device)
            bridge.launch(args.component)
            result=bridge.wait_for_app(args.component)
        elif args.command=='keep-awake':
            from .devices import LocalBridge
            result=LocalBridge(settings,runner,args.device).keep_awake(args.minutes)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
