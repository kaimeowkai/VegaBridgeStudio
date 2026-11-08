"""Native source-debugging sessions using external CodeLLDB and Linux lldb-server.

Only a session-owned developer program is launched; no global ptrace/sandbox
settings are changed and existing apps are never attached implicitly.
"""
import json
import os
import re
import shlex
import struct
import subprocess
import threading
import time
import uuid
from pathlib import Path
from .dap import DapClient
from .devices import LocalBridge
from .native_build import compile_source
from .project import inside,tool_path
from .process import Runner,Cancelled
from .storage import user_dir
from .workspace_tools import elf_architecture


def prepare_server(source,destination,arch):
    source,destination=Path(source),Path(destination)
    if elf_architecture(source)!=arch:raise ValueError('Debug server architecture must match the program')
    data=bytearray(source.read_bytes())
    if len(data)>64*1024*1024:raise ValueError('Debug server exceeds 64 MiB')
    # Standard Linux x64 tools expect /lib64; Vega keeps this loader in /lib.
    # Adapt a private copy only. No proprietary SDK or original tool is changed.
    if arch=='x86_64':
        offset=struct.unpack_from('<Q',data,32)[0]
        size,count=struct.unpack_from('<HH',data,54)
        if size<56 or count>1000 or offset+size*count>len(data):raise ValueError('Invalid ELF program headers')
        for i in range(count):
            at=offset+i*size
            if struct.unpack_from('<I',data,at)[0]!=3:continue
            start=struct.unpack_from('<Q',data,at+8)[0]
            length=struct.unpack_from('<Q',data,at+32)[0]
            if start+length>len(data):raise ValueError('Invalid ELF interpreter')
            if bytes(data[start:start+length]).rstrip(b'\0')==b'/lib64/ld-linux-x86-64.so.2':
                data[start:start+length]=b'/lib/ld-linux-x86-64.so.2\0'.ljust(length,b'\0')
    destination.write_bytes(data)


class NativeDebugSession:
    def __init__(self,project,binary,settings,serial,event=lambda msg:None):
        self.project=Path(project).resolve()
        self.binary=inside(self.project,Path(binary).resolve())
        if not self.binary.is_file():raise ValueError('Choose a compiled native executable in this project')
        self.arch=elf_architecture(self.binary)
        self.settings=dict(settings)
        self.event=event
        self.cancelled=threading.Event()
        self.runner=Runner(cancelled=self.cancelled)
        self.bridge=LocalBridge(settings,self.runner,serial)
        self.id=uuid.uuid4().hex
        self.remote='/tmp/vegabridge-debug-'+self.id
        self.local=user_dir()/'debug-sessions'/self.id
        self.dap=None
        self.channel=None
        self.forward=None
        self.pids={}
        self.server_text=''
        self.thread_id=None
        self.cleanup_lock=threading.Lock()

    def _event(self,msg):
        if msg.get('event')=='stopped':self.thread_id=msg.get('body',{}).get('threadId')
        self.event(dict(msg,sessionId=self.id))

    def start(self,breakpoints):
        try:
            self.runner.check()
            adapter=tool_path(self.settings.get('debug_adapter',''),'codelldb.exe')
            server=Path(self.settings.get('debug_server',''))
            if not server.is_file():raise ValueError('Configure a matching Linux lldb-server in Settings → Native debugger')
            self.local.mkdir(parents=True)
            prepare_server(server,self.local/'server',self.arch)
            pause=self.local/'pause.c'
            pause.write_text('#include <signal.h>\n__attribute__((constructor)) static void vb_pause(void){raise(SIGSTOP);}\n')
            compile_source(pause,self.local/'pause.so',self.settings,self.runner,self.arch,True,True)
            self.bridge.shell('mkdir -m 700 '+shlex.quote(self.remote))
            for src,name in [(self.binary,'program'),(self.local/'server','server'),(self.local/'pause.so','pause.so')]:
                self.bridge.push(src,self.remote+'/'+name)
            self.bridge.shell('chmod 700 '+self.remote+'/program '+self.remote+'/server '+self.remote+'/pause.so')
            port=32768+(int(self.id[:8],16)%30000)
            command=('echo __VB_SERVER__$$; LD_PRELOAD='+self.remote+'/pause.so '+self.remote+'/program >'+self.remote+'/output 2>&1 & '
                'vb_pid=$!; echo __VB_TARGET__$vb_pid; exec '+self.remote+'/server gdbserver 127.0.0.1:'+str(port)+' --attach "$vb_pid"')
            self.runner.check()
            self.channel=subprocess.Popen([self.bridge.adb,'-P',str(self.bridge.port),'-s',self.bridge.serial,'shell','-x',command],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            ready=threading.Event()
            def read_server():
                for line in iter(self.channel.stdout.readline,b''):
                    text=line.decode('utf8','replace').strip()
                    self.server_text=(self.server_text+'\n'+text)[-16000:]
                    for tag in ('SERVER','TARGET'):
                        match=re.fullmatch('__VB_'+tag+'__([0-9]+)',text)
                        if match:self.pids[tag]=int(match[1])
                    if 'Attached to process' in text:ready.set()
            threading.Thread(target=read_server,daemon=True).start()
            end=time.monotonic()+10
            while not ready.wait(.1):
                self.runner.check()
                if self.channel.poll() is not None or time.monotonic()>end:
                    raise RuntimeError('Native debug server did not attach: '+self.server_text[-3000:])
            self.forward=self.bridge.call(['forward','tcp:0','tcp:'+str(port)]).strip()
            if not self.forward.isdigit():raise RuntimeError('Bridge did not allocate a debugger port')
            self.runner.check()
            self.dap=DapClient(adapter,self._event)
            self.dap.request('initialize',{'clientID':'vegabridge','adapterID':'lldb','pathFormat':'path',
                'linesStartAt1':True,'columnsStartAt1':True,'supportsRunInTerminalRequest':False})
            launch=self.dap.send('launch',{'name':'Vega native source debugging','type':'lldb','request':'launch',
                'program':str(self.binary),'cwd':str(self.project),'stopOnEntry':True,'terminal':'console',
                'initCommands':['platform select remote-linux'],
                'processCreateCommands':['gdb-remote 127.0.0.1:'+self.forward],
                'postRunCommands':['process handle SIGSTOP --stop false --notify false --pass false']})
            self.dap.wait_event('initialized')
            resolved=[]
            for source,lines in breakpoints.items():resolved+=self.set_breakpoints(source,lines)
            self.dap.request('configurationDone')
            self.dap.response(launch)
            return {'architecture':self.arch,'breakpoints':resolved,'session':self.id}
        except Exception:
            self.close()
            raise

    def set_breakpoints(self,source,lines):
        path=inside(self.project,Path(source).resolve())
        lines=sorted(set(lines))
        if any(type(line)!=int or not 1<=line<=1000000 for line in lines):raise ValueError('Invalid breakpoint line')
        return self.dap.request('setBreakpoints',{'source':{'path':str(path)},
            'breakpoints':[{'line':line} for line in lines],'sourceModified':False}).get('breakpoints',[])

    def snapshot(self):
        if not self.thread_id:
            threads=self.dap.request('threads').get('threads',[])
            if not threads:return {'frames':[],'variables':[]}
            self.thread_id=threads[0]['id']
        frames=self.dap.request('stackTrace',{'threadId':self.thread_id,'startFrame':0,'levels':100}).get('stackFrames',[])
        return {'frames':frames,'variables':self.variables_for_frame(frames[0]['id']) if frames else []}

    def variables_for_frame(self,frame):
        scopes=self.dap.request('scopes',{'frameId':frame}).get('scopes',[])
        return [{'scope':scope['name'],'items':self.variables(scope['variablesReference'])} for scope in scopes if not scope.get('expensive')]

    def variables(self,reference):
        return self.dap.request('variables',{'variablesReference':reference,'start':0,'count':200}).get('variables',[])[:200]

    def source_for_frame(self,frame):
        reference=frame.get('source',{}).get('sourceReference')
        if not reference:return ''
        return self.dap.request('source',{'sourceReference':reference}).get('content','')[:1000000]

    def control(self,command):
        if command not in {'continue','pause','next','stepIn','stepOut'}:raise ValueError('Unknown debug control')
        if not self.thread_id:raise ValueError('Wait for a stopped thread before controlling the debugger')
        return self.dap.request(command,{'threadId':self.thread_id})

    def close(self):
        self.cancelled.set()
        with self.cleanup_lock:
            if self.dap:
                try:self.dap.request('disconnect',{'terminateDebuggee':True},timeout=2)
                except Exception:pass
                self.dap.close()
            # A separate cancellation-free bridge cleans only exact session-owned
            # process identities and forwarding rules, never another app or VM.
            cleanup=LocalBridge(self.settings,Runner(),self.bridge.serial)
            for tag,name in [('TARGET','program'),('SERVER','server')]:
                pid=self.pids.get(tag)
                if pid:
                    try:cleanup.shell('if grep -Fq '+shlex.quote(self.remote+'/'+name)+' /proc/'+str(pid)+'/cmdline 2>/dev/null; then kill '+str(pid)+'; fi',timeout=3)
                    except Exception:pass
            if self.channel and self.channel.poll() is None:
                self.channel.terminate()
                try:self.channel.wait(timeout=2)
                except subprocess.TimeoutExpired:self.channel.kill();self.channel.wait(timeout=2)
            if self.forward:
                try:
                    mapping=cleanup.call(['forward','--list'],selected=False)
                    if any(line.split()==[self.bridge.serial,'tcp:'+self.forward,'tcp:'+str(32768+(int(self.id[:8],16)%30000))] for line in mapping.splitlines()):
                        cleanup.call(['forward','--remove','tcp:'+self.forward])
                except Exception:pass
            if re.fullmatch('/tmp/vegabridge-debug-[a-f0-9]{32}',self.remote):
                try:cleanup.shell('rm -rf '+self.remote,timeout=3)
                except Exception:pass
