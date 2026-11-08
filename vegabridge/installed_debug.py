"""Native attachment inside an explicitly selected project's app namespace.

Detaching resumes the installed app. Only the debugger server, temporary
scratch directory, adapter and bridge forwarding belong to this session.
"""
import re
import os
import json
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path
from .native_debug import NativeDebugSession,prepare_server
from .devices import LocalBridge
from .dap import DapClient
from .process import Runner
from .project import metadata,inside,tool_path
from .storage import user_dir
from .workspace_tools import elf_architecture


def component_process(bridge,component):
    if component.startswith('com.amazon.'):raise ValueError('System components cannot be attached through project debugging')
    rows=bridge.shell('vlcm list --app-id '+shlex.quote(component),timeout=8)
    matches=[line.split() for line in rows.splitlines() if line.split() and line.split()[0]==component]
    if len(matches)!=1 or len(matches[0])<6 or not matches[0][2].isdigit():
        raise RuntimeError('The current project app is not running. Install/run its development build before attaching.')
    parts=matches[0]
    if int(parts[2])<=0 or parts[4] in {'IDLE','STOPPED'}:
        raise RuntimeError('The current project app has no running process. Launch its development build before attaching.')
    return {'component':component,'pid':int(parts[2]),'state':parts[4],'instance':parts[3]}


class InstalledAppDebugSession(NativeDebugSession):
    def __init__(self,project,symbols,settings,serial,event=lambda message:None):
        self.project=Path(project).resolve();self.package=metadata(self.project)['id'];self.component=metadata(self.project)['component']
        if self.package.startswith('com.amazon.') or not self.component.startswith(self.package+'.'):
            raise ValueError('Attach only to your own current-project component')
        self.symbols=inside(self.project,Path(symbols).resolve()) if symbols else None
        if self.symbols and not self.symbols.is_file():raise ValueError('Choose an existing project ELF with debug symbols, or leave symbols empty')
        self.settings=dict(settings);self.event=event;self.cancelled=threading.Event();self.runner=Runner(cancelled=self.cancelled)
        self.bridge=LocalBridge(settings,self.runner,serial);self.id=uuid.uuid4().hex
        self.remote='/scratch/vegabridge-attach-'+self.id;self.outer='/tmp/scratch/'+self.package+'/vegabridge-attach-'+self.id
        self.local=user_dir()/'debug-sessions'/self.id;self.dap=None;self.channel=None;self.forward=None;self.pids={};self.server_text='';self.thread_id=None
        self.cleanup_lock=threading.Lock();self.owner=None;self.process_stamp='';self.target_pid=None

    def shell(self,command,timeout=8):return self.bridge.component_shell(self.component,command,timeout=timeout)

    def start(self,breakpoints):
        try:
            self.owner=component_process(self.bridge,self.component);adapter=tool_path(self.settings.get('debug_adapter',''),'codelldb.exe')
            processes=self.shell('ps -A -o pid,comm')
            candidates=[row.split()[0] for row in processes.splitlines() if len(row.split())==2 and row.split()[1]=='stem-init' and row.split()[0].isdigit()]
            if len(candidates)!=1:raise RuntimeError('Expected exactly one app stem in the selected component namespace')
            self.target_pid=int(candidates[0]);self.process_stamp=self.shell('cat /proc/'+str(self.target_pid)+'/stat').strip()
            self.local.mkdir(parents=True);self.shell('mkdir -m 700 '+self.remote)
            self.shell('cp /proc/'+str(self.target_pid)+'/exe '+self.remote+'/stem-init')
            self.bridge.pull(self.outer+'/stem-init',self.local/'stem-init');self.binary=self.local/'stem-init';self.arch=elf_architecture(self.binary)
            prepare_server(self.settings.get('debug_server',''),self.local/'server',self.arch)
            if self.symbols and elf_architecture(self.symbols)!=self.arch:raise ValueError('Symbol ELF architecture differs from the installed app')
            self.bridge.push(self.local/'server',self.outer+'/server');self.shell('chmod 700 '+self.remote+'/server')
            self.port=32768+(int(self.id[:8],16)%30000)
            command='echo __VB_SERVER__$$; exec '+self.remote+'/server gdbserver 127.0.0.1:'+str(self.port)+' --attach '+str(self.target_pid)
            self.channel=subprocess.Popen([self.bridge.adb,'-P',str(self.bridge.port),'-s',self.bridge.serial,'shell','-x','component-id',self.component,command],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            ready=threading.Event()
            def read_server():
                for line in iter(self.channel.stdout.readline,b''):
                    text=line.decode('utf8','replace').strip();self.server_text=(self.server_text+'\n'+text)[-16000:]
                    match=re.fullmatch('__VB_SERVER__([0-9]+)',text)
                    if match:self.pids['SERVER']=int(match[1])
                    if 'Attached to process' in text:ready.set()
            threading.Thread(target=read_server,daemon=True).start();end=time.monotonic()+12
            while not ready.wait(.1):
                self.runner.check()
                if self.channel.poll() is not None or time.monotonic()>end:raise RuntimeError('Installed-app native attach failed: '+self.server_text[-3000:])
            current=component_process(self.bridge,self.component)
            if current['pid']!=self.owner['pid'] or current['instance']!=self.owner['instance']:raise RuntimeError('The selected app restarted during attachment')
            self.forward=self.bridge.call(['forward','tcp:0','tcp:'+str(self.port)]).strip()
            if not self.forward.isdigit():raise RuntimeError('Bridge did not allocate an attach port')
            self.dap=DapClient(adapter,self._event);self.dap.request('initialize',{'clientID':'vegabridge','adapterID':'lldb','pathFormat':'path','linesStartAt1':True,'columnsStartAt1':True,'supportsRunInTerminalRequest':False})
            commands=['platform select remote-linux']
            symbol_commands=['target symbols add --shlib '+json.dumps(self.symbols.name)+' '+json.dumps(str(self.symbols))] if self.symbols else []
            launch=self.dap.send('launch',{'name':'Attach installed Vega component','request':'launch','type':'lldb','program':str(self.binary),
                'cwd':str(self.project),'stopOnEntry':True,'terminal':'console','initCommands':commands,
                'processCreateCommands':['gdb-remote 127.0.0.1:'+self.forward],'postRunCommands':symbol_commands})
            self.dap.wait_event('initialized');resolved=[]
            for source,lines in breakpoints.items():resolved+=self.set_breakpoints(source,lines)
            self.dap.request('configurationDone');self.dap.response(launch)
            return {'architecture':self.arch,'breakpoints':resolved,'session':self.id,'component':self.component,'outerPid':self.owner['pid'],'namespacePid':self.target_pid}
        except Exception:self.close();raise

    def close(self):
        self.cancelled.set()
        with self.cleanup_lock:
            if self.dap:
                try:self.dap.request('disconnect',{'terminateDebuggee':False},timeout=3)
                except Exception:pass
                self.dap.close()
            cleanup=LocalBridge(self.settings,Runner(),self.bridge.serial)
            try:
                pid=self.pids.get('SERVER')
                if pid:cleanup.component_shell(self.component,'if grep -Fq '+shlex.quote(self.remote+'/server')+' /proc/'+str(pid)+'/cmdline 2>/dev/null; then kill '+str(pid)+'; fi',timeout=3)
            except Exception:pass
            if self.channel and self.channel.poll() is None:
                self.channel.terminate()
                try:self.channel.wait(timeout=3)
                except subprocess.TimeoutExpired:self.channel.kill();self.channel.wait(timeout=2)
            # A failed connection must not leave the original app stopped. Verify
            # outer identity and namespace process start-time before SIGCONT.
            try:
                current=component_process(cleanup,self.component)
                if self.owner and current['pid']==self.owner['pid'] and current['instance']==self.owner['instance']:
                    stamp=cleanup.component_shell(self.component,'cat /proc/'+str(self.target_pid)+'/stat',timeout=3).strip()
                    def start_time(value):return value[value.rfind(')')+2:].split()[19]
                    if start_time(stamp)==start_time(self.process_stamp):cleanup.component_shell(self.component,'kill -CONT '+str(self.target_pid),timeout=3)
            except Exception:pass
            if self.forward:
                try:
                    mappings=cleanup.call(['forward','--list'],selected=False)
                    if any(row.split()==[self.bridge.serial,'tcp:'+self.forward,'tcp:'+str(self.port)] for row in mappings.splitlines()):cleanup.call(['forward','--remove','tcp:'+self.forward])
                except Exception:pass
            if re.fullmatch('/scratch/vegabridge-attach-[a-f0-9]{32}',self.remote):
                try:cleanup.component_shell(self.component,'rm -rf '+self.remote,timeout=3)
                except Exception:pass
