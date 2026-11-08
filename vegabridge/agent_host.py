"""Thread-safe GUI integration for the bounded coding assistant."""
import threading
from pathlib import Path
from PySide6.QtWidgets import QApplication
from .agent_workspace import AgentWorkspace, project_destination
from .editor import CodeEditor
from .project import create_project, metadata, build, inside
from .storage import save_settings
from .devices import LocalBridge


class AgentHost:
    def invoke_agent_tool(self,name,args,runner):
        request={'name':name,'args':args,'event':threading.Event(),'cancelled':runner.cancelled}
        self.agent_requested.emit(request)
        while not request['event'].wait(.1):runner.check()
        if 'error' in request:raise ValueError(request['error'])
        action=request['action']
        return action(runner) if callable(action) else action

    def prepare_agent_tool(self,request):
        try:
            if request['cancelled'].is_set():raise ValueError('Assistant stopped before this action began.')
            request['action']=self.agent_action(request['name'],request['args'])
        except Exception as error:request['error']=str(error)
        finally:request['event'].set()

    def agent_checkpoint(self,history):
        self.history=history
        self.save_conversation()

    def agent_refresh_file(self,path):
        path=Path(path)
        for index in range(self.editors.count()):
            editor=self.editors.widget(index)
            if isinstance(editor,CodeEditor) and editor.path==path:
                if path.is_file():
                    cursor=editor.textCursor()
                    cursor.select(cursor.SelectionType.Document)
                    cursor.insertText(path.read_text(encoding='utf-8-sig'))
                    editor.document().setModified(False)
                else:self.editors.removeTab(index);editor.deleteLater()
                return

    def agent_action(self,name,args):
        from .gallery import entries
        from .theme import apply_theme
        from .native_vm import managed_vm_command
        if name=='get_workspace':
            return {'project':str(self.project) if self.project else None,
                    'metadata':metadata(self.project) if self.project else None,
                    'unsavedFiles':[str(self.editors.widget(i).path.relative_to(self.project)) for i in range(self.editors.count()) if isinstance(self.editors.widget(i),CodeEditor) and self.editors.widget(i).document().isModified()],
                    'selectedTarget':self.target.currentData(),
                    'projectsFolder':self.settings['projects_folder'],
                    'theme':self.settings['theme'],'nativeTools':{key:bool(self.settings.get(key)) for key in ['node','adb','qemu','clang','sdk_root','hermes','openssl']}}
        if name=='list_templates':return entries()
        if name=='set_theme':
            self.settings['theme']=args['theme'];save_settings(self.settings)
            apply_theme(QApplication.instance(),args['theme'])
            return {'theme':args['theme']}
        if name=='create_project':
            if any(isinstance(self.editors.widget(i),CodeEditor) and self.editors.widget(i).document().isModified() for i in range(self.editors.count())):
                raise ValueError('There are unsaved source edits. Ask the user to save or discard them before switching projects.')
            root=project_destination(self.settings['projects_folder'],args['folder'])
            create_project(root,args['title'],args['identifier'],args['template'],args['language'])
            self.open_project(root,allow_agent=True)
            if self.project!=root:raise RuntimeError('The project could not be selected. Finish other active tasks first.')
            return {'project':str(root),'metadata':metadata(root),'planningConversationPreserved':True}
        settings=dict(self.settings)
        if name=='list_devices':return lambda runner:LocalBridge(settings,runner).devices()
        if name=='select_device':
            serial=args['serial']
            def select(runner):
                found=LocalBridge(settings,runner).devices()
                if not any(item['serial']==serial and item['state']=='device' for item in found):raise ValueError('Target is not online and authorized.')
                self.agent_ui_effect.emit(lambda:self.set_devices(found,prefer=serial))
                return {'selected':serial}
            return select
        if name=='connect_emulator':
            serial='127.0.0.1:'+str(settings['vm_port'])
            def connect(runner):
                bridge=LocalBridge(settings,runner);bridge.connect(serial)
                found=bridge.devices()
                self.agent_ui_effect.emit(lambda:self.set_devices(found,prefer=serial))
                return {'selected':serial,'devices':found}
            return connect
        if name=='start_emulator':
            # Start button owns the singleton VM job; startup is asynchronous.
            self.start_native_vm()
            return {'requested':True,'next':'Wait for the ready screen, then connect_emulator. Only one owned VM is allowed.'}
        if name=='stop_emulator':return lambda runner:managed_vm_command('quit')
        if name in {'send_remote_key','type_device_text'}:
            snapshot=self.target_snapshot()
            if name=='type_device_text':return lambda runner:self.bridge(snapshot,runner).type_text(args['text'])
            return lambda runner:self.bridge(snapshot,runner).shell('inputd-cli button_press '+args['key'])
        if not self.project:raise ValueError('Create or open a project first.')
        root=self.project;workspace=AgentWorkspace(root)
        if name in {'write_file','undo_last_edit'}:
            relative=args['path'] if name=='write_file' else None
            for index in range(self.editors.count()):
                editor=self.editors.widget(index)
                if isinstance(editor,CodeEditor) and editor.document().isModified() and (relative is None or editor.path==workspace.path(relative)):
                    raise ValueError('This file has unsaved editor changes. Ask the user to save it before applying an assistant edit.')
            result=workspace.write(relative,args['content'],args['expected_sha256']) if name=='write_file' else workspace.undo()
            self.agent_refresh_file(root/result['path'])
            self.output.appendPlainText('Assistant edited: '+result['path']+' (encrypted local undo available)')
            return result
        if name=='list_files':return lambda runner:workspace.files()
        if name=='read_file':return lambda runner:workspace.read(args['path'])
        if name=='search_files':
            def search(runner):
                results=[]
                if not args['query']:return results
                for relative in workspace.files():
                    runner.check()
                    try:text=workspace.read(relative)['content']
                    except (ValueError,OSError,UnicodeError):continue
                    for number,line in enumerate(text.splitlines(),1):
                        if args['query'].casefold() in line.casefold():
                            results.append({'path':relative,'line':number,'text':line[:300]})
                            if len(results)>=100:return results
                return results
            return search
        if name=='open_file':
            path=workspace.path(args['path']);self.open_file(path)
            return {'opened':args['path']}
        if name=='compile_native':
            from .native_build import compile_source
            source=workspace.path(args['path'])
            shared=args['artifact']=='Shared library'
            destination=inside(root,root/'build/native'/(source.stem+'-'+args['architecture']+('.so' if shared else '.elf')))
            return lambda runner:{'nativeArtifact':compile_source(source,destination,settings,runner,args['architecture'],shared),'appIntegrationVerified':False}
        if name=='generate_native_module':
            import uuid
            from .codegen import generate_module
            source=workspace.path(args['path'])
            destination=inside(root,root/'native-generated'/(source.stem+'-'+uuid.uuid4().hex[:8]))
            return lambda runner:generate_module(source,destination,settings,runner,args['namespace'])
        if name=='compile_bytecode':
            from .codegen import compile_bytecode
            source=inside(root,root/'stage/bundle/index.bundle');destination=inside(root,root/'build/index.hbc')
            return lambda runner:compile_bytecode(source,destination,settings,runner)
        if name in {'build_project','run_project'}:
            if any(isinstance(self.editors.widget(i),CodeEditor) and self.editors.widget(i).document().isModified() for i in range(self.editors.count())):
                raise ValueError('Save source edits before building; the assistant will not discard unsaved buffers.')
            snapshot=self.target_snapshot() if name=='run_project' else None
            info=metadata(root)
            def execute(runner):
                package=build(root,settings,runner)
                self.agent_ui_effect.emit(lambda:setattr(self,'last_package',Path(package)))
                result={'package':str(package),'buildSucceeded':True}
                if snapshot:
                    bridge=self.bridge(snapshot,runner);bridge.install(package);bridge.launch(info['component'])
                    result['runtime']=bridge.wait_for_app(info['component'])
                    result['installed']=True
                return result
            return execute
        raise ValueError('Unknown Studio action.')
