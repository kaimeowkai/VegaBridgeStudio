"""Bounded Debug Adapter Protocol transport for an external Windows adapter."""
import json
import os
import socket
import subprocess
import threading
import time

LIMIT=8*1024*1024


def read_message(stream):
    headers={}
    total=0
    while True:
        line=stream.readline(4097)
        if not line:raise EOFError('Debug adapter disconnected')
        total+=len(line)
        if total>16384 or len(line)>4096:raise ValueError('Oversized debug protocol header')
        if line in {b'\r\n',b'\n'}:break
        key,sep,value=line.partition(b':')
        if not sep:raise ValueError('Invalid debug protocol header')
        key=key.strip().lower()
        if key in headers:raise ValueError('Duplicate debug protocol header')
        headers[key]=value.strip()
    try:size=int(headers[b'content-length'])
    except (KeyError,ValueError):raise ValueError('Missing debug message length') from None
    if not 0<size<=LIMIT:raise ValueError('Invalid debug message size')
    data=bytearray()
    while len(data)<size:
        block=stream.read(size-len(data))
        if not block:raise EOFError('Incomplete debug message')
        data.extend(block)
    message=json.loads(data)
    if not isinstance(message,dict):raise ValueError('Invalid debug protocol message')
    return message


class DapClient:
    def __init__(self, executable, event=lambda message:None):
        self.event=event
        self.condition=threading.Condition()
        self.write_lock=threading.Lock()
        self.seq=0
        self.responses={}
        self.events=[]
        self.closed=False
        self.error=''
        self.sock=None
        self.proc=None
        listener=socket.socket()
        listener.bind(('127.0.0.1',0))
        listener.listen(1)
        listener.settimeout(12)
        try:
            self.proc=subprocess.Popen([str(executable),'--connect',str(listener.getsockname()[1])],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.sock,_=listener.accept()
            self.sock.settimeout(None)
        except Exception:
            self.close()
            raise
        finally:listener.close()
        self.thread=threading.Thread(target=self._read,daemon=True)
        self.thread.start()

    def _read(self):
        try:
            with self.sock.makefile('rb') as stream:
                while not self.closed:
                    msg=read_message(stream)
                    if msg.get('type')=='response':
                        with self.condition:
                            self.responses[msg.get('request_seq')]=msg
                            self.condition.notify_all()
                    elif msg.get('type')=='event':
                        with self.condition:
                            self.events.append(msg)
                            self.events=self.events[-300:]
                            self.condition.notify_all()
                        self.event(msg)
                    elif msg.get('type')=='request':
                        # Terminal launches and arbitrary client commands are unsupported.
                        self._write({'seq':0,'type':'response','request_seq':msg['seq'],
                            'command':msg.get('command'),'success':False,'message':'Client request unsupported'})
        except Exception as error:
            with self.condition:
                self.error=str(error)
                self.closed=True
                self.condition.notify_all()

    def _write(self,msg):
        data=json.dumps(msg,ensure_ascii=False).encode('utf8')
        if len(data)>LIMIT:raise ValueError('Debug request is too large')
        with self.write_lock:self.sock.sendall(b'Content-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data)

    def send(self,command,arguments=None):
        with self.condition:
            if self.closed:raise RuntimeError(self.error or 'Debugger is closed')
            self.seq+=1
            seq=self.seq
        self._write({'seq':seq,'type':'request','command':command,'arguments':arguments or {}})
        return seq

    def response(self,seq,timeout=15):
        end=time.monotonic()+timeout
        with self.condition:
            while seq not in self.responses:
                if self.closed:raise RuntimeError(self.error or 'Debugger disconnected')
                left=end-time.monotonic()
                if left<=0:raise TimeoutError('Debug adapter did not respond in time')
                self.condition.wait(left)
            msg=self.responses.pop(seq)
        if not msg.get('success'):raise RuntimeError(msg.get('message','Debug request failed'))
        return msg.get('body',{})

    def request(self,command,arguments=None,timeout=15):
        return self.response(self.send(command,arguments),timeout)

    def wait_event(self,name,timeout=15,after_seq=0):
        end=time.monotonic()+timeout
        with self.condition:
            while True:
                self.events[:]=[msg for msg in self.events if msg.get('event')!=name or msg.get('seq',0)>after_seq]
                for i,msg in enumerate(self.events):
                    if msg.get('event')==name:return self.events.pop(i)
                if self.closed:raise RuntimeError(self.error or 'Debugger disconnected')
                left=end-time.monotonic()
                if left<=0:raise TimeoutError('Debugger did not report '+name)
                self.condition.wait(left)

    def close(self):
        with self.condition:
            self.closed=True
            self.condition.notify_all()
        if self.sock:
            try:self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            self.sock.close()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=3)
