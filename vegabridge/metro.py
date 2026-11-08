"""Own one loopback Metro child and only this session's reverse mapping."""
import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path
import httpx
from .devices import LocalBridge
from .project import tool_path,metadata
from .process import Runner


def available_port(preferred):
    try:
        with socket.create_connection(('127.0.0.1',preferred),timeout=.2):pass
    except OSError:return preferred
    with socket.socket() as candidate:
        candidate.bind(('127.0.0.1',0));return candidate.getsockname()[1]


class MetroSession:
    def __init__(self,project,settings,serial,port=8081,emit=None):
        self.project=Path(project).resolve();self.settings=dict(settings);self.port=int(port)
        if not 1024<=self.port<=65535:raise ValueError('Choose an unprivileged Metro port')
        self.bridge=LocalBridge(settings,Runner(),serial);self.process=None;self.reverse_owned=False;self.lock=threading.Lock();self.closed=False
        self.emit=emit
        self.timeout_component=None

    def _read_output(self,emit):
        for line in iter(self.process.stdout.readline,b''):
            text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line.decode('utf8','replace').rstrip())
            try:emit(text)
            except RuntimeError:
                # A closing Qt window can dispose its signal while the child exits.
                if not self.closed:raise

    def start(self,runner):
        # Refuse to take over any pre-existing server, regardless of its origin.
        try:
            with socket.create_connection(('127.0.0.1',self.port),timeout=.2):pass
        except OSError:pass
        else:raise RuntimeError('Metro host port is already served by another process; choose a free host port')
        with socket.socket() as check:
            try:check.bind(('127.0.0.1',self.port))
            except OSError as error:raise RuntimeError('Metro port '+str(self.port)+' is already in use. Attach to its current project, stop that server, or select another host port.') from error
        node=Path(tool_path(self.settings.get('node',''),'node.exe'));cli=self.project/'node_modules/react-native/cli.js'
        if not cli.is_file():raise ValueError('Build the project dependencies before starting Metro')
        mappings=self.bridge.call(['reverse','--list'])
        existing=[row.split() for row in mappings.splitlines() if len(row.split())>=3 and row.split()[-2]=='tcp:8081']
        if existing and existing[0][-1]!='tcp:'+str(self.port):raise RuntimeError('The selected device already forwards app Metro port 8081 to another host port; its mapping was preserved')
        env=dict(os.environ,PATH=str(node.parent)+os.pathsep+os.environ.get('PATH',''),CI='1')
        self.process=subprocess.Popen([str(node),str(cli),'start','--host','127.0.0.1','--port',str(self.port),'--max-workers','4','--no-interactive'],
            cwd=self.project,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        threading.Thread(target=self._read_output,args=(self.emit or runner.emit,),daemon=True).start()
        try:
            deadline=time.monotonic()+90;last_status='No HTTP response'
            with httpx.Client(trust_env=False,timeout=1) as client:
                while time.monotonic()<deadline:
                    runner.check()
                    if self.closed or self.process.poll() is not None:raise RuntimeError('The owned Metro server stopped before becoming ready')
                    try:
                        response=client.get('http://127.0.0.1:'+str(self.port)+'/status');last_status=str(response.status_code)+' '+repr(response.text[:120])
                        if response.text.strip()=='packager-status:running':break
                    except httpx.HTTPError as error:last_status=type(error).__name__+': '+str(error)
                    runner.cancelled.wait(.15)
                else:raise TimeoutError('The owned Metro server did not become ready in 90 seconds. Last health check: '+last_status)
            if not existing:
                self.bridge.call(['reverse','--no-rebind','tcp:8081','tcp:'+str(self.port)]);self.reverse_owned=True
            component=metadata(self.project)['component']
            if component.startswith('com.amazon.'):raise ValueError('Development launch is limited to your own project component')
            if '--disable-app-timeout' not in self.bridge.shell('vlcm --help'):
                raise RuntimeError('This Vega image cannot protect paused apps from lifecycle timeouts. Update the image before source debugging.')
            self.bridge.shell('vlcm debug '+component+' --disable-app-timeout')
            self.timeout_component=component
            return {'port':self.port,'processId':self.process.pid,'reverseCreated':self.reverse_owned}
        except Exception:self.close();raise

    def close(self):
        self.closed=True
        with self.lock:
            restore_error=None
            if self.timeout_component:
                component=self.timeout_component
                try:
                    self.bridge.shell('vlcm debug '+component+' --clear')
                    self.timeout_component=None
                except Exception as error:restore_error=error
            if self.process and self.process.poll() is None:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                        timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
                else:self.process.terminate()
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
            if self.reverse_owned:
                try:
                    mappings=self.bridge.call(['reverse','--list'])
                    if any(len(row.split())>=3 and row.split()[-2:]==['tcp:8081','tcp:'+str(self.port)] for row in mappings.splitlines()):
                        self.bridge.call(['reverse','--remove','tcp:8081'])
                except Exception:pass
                self.reverse_owned=False
            if restore_error:raise RuntimeError('Metro stopped, but restore app debug-launch settings after reconnecting: vlcm debug '+self.timeout_component+' --clear') from restore_error
