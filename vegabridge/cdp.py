"""Bounded Chrome DevTools Protocol connection to a local Metro inspector."""
import json
import threading
import time
from urllib.parse import urlsplit
import websocket

LIMIT=16*1024*1024


def local_url(url,port=None,web_socket=False):
    parsed=urlsplit(url)
    if (parsed.scheme!=('ws' if web_socket else 'http') or parsed.hostname not in {'127.0.0.1','localhost'}
            or parsed.username or parsed.password or parsed.fragment or not parsed.port
            or (port is not None and parsed.port!=port)):
        raise ValueError('Debugger endpoints must use the selected loopback Metro port')
    return url


class CdpClient:
    def __init__(self,url,event=lambda value:None):
        local_url(url,web_socket=True)
        self.event=event;self.condition=threading.Condition();self.write_lock=threading.Lock()
        self.seq=0;self.event_seq=0;self.responses={};self.events=[];self.pending=set();self.asynchronous=set();self.closed=False;self.error=''
        self.socket=websocket.create_connection(url,timeout=8,http_no_proxy=['127.0.0.1','localhost'],redirect_limit=0,enable_multithread=True)
        self.socket.settimeout(None)
        self.reader=threading.Thread(target=self._read,daemon=True,name='VegaJavaScript');self.reader.start()

    def _read(self):
        try:
            while not self.closed:
                raw=self.socket.recv()
                if not raw:raise EOFError('JavaScript inspector disconnected')
                if len(raw)>LIMIT:raise ValueError('JavaScript inspector message exceeds 16 MiB')
                value=json.loads(raw)
                if not isinstance(value,dict):raise ValueError('Invalid inspector message')
                if 'id' in value:
                    with self.condition:
                        identifier=value['id']
                        if identifier in self.asynchronous:
                            self.asynchronous.remove(identifier);self.pending.discard(identifier)
                            dispatch=dict(value,method='VegaBridge.evaluationResult')
                        else:
                            if identifier in self.pending:self.responses[identifier]=value
                            dispatch=None
                        self.condition.notify_all()
                    if dispatch:self.event(dispatch)
                elif 'method' in value:
                    with self.condition:
                        self.event_seq+=1;value['_eventSeq']=self.event_seq;self.events.append(value);self.events=self.events[-300:];self.condition.notify_all()
                    self.event(value)
        except Exception as error:
            with self.condition:
                self.error=str(error);self.closed=True;self.condition.notify_all()
            self.event({'method':'VegaBridge.disconnected','params':{'reason':str(error)}})

    def send(self,method,params=None,asynchronous=False):
        with self.condition:
            if self.closed:raise RuntimeError(self.error or 'JavaScript debugger is closed')
            if len(self.pending)>=100:raise RuntimeError('Too many outstanding inspector requests')
            self.seq+=1;identifier=self.seq;self.pending.add(identifier)
            if asynchronous:self.asynchronous.add(identifier)
        body=json.dumps({'id':identifier,'method':method,'params':params or {}})
        if len(body.encode())>LIMIT:raise ValueError('Inspector request is too large')
        with self.write_lock:self.socket.send(body)
        return identifier

    def response(self,identifier,timeout=10):
        deadline=time.monotonic()+timeout
        try:
            with self.condition:
                while identifier not in self.responses:
                    if self.closed:raise RuntimeError(self.error or 'JavaScript inspector disconnected')
                    left=deadline-time.monotonic()
                    if left<=0:raise TimeoutError('JavaScript inspector did not respond; a breakpoint may be pausing the request')
                    self.condition.wait(left)
                result=self.responses.pop(identifier)
            if 'error' in result:raise RuntimeError(result['error'].get('message','Inspector request failed'))
            return result.get('result',{})
        finally:
            with self.condition:self.pending.discard(identifier)

    def request(self,method,params=None,timeout=10):
        return self.response(self.send(method,params),timeout)

    def wait_event(self,method,timeout=10,after_seq=0):
        deadline=time.monotonic()+timeout
        with self.condition:
            while True:
                for index,event in enumerate(self.events):
                    if event['method']==method and event['_eventSeq']>after_seq:return self.events.pop(index)
                if self.closed:raise RuntimeError(self.error or 'Inspector disconnected')
                left=deadline-time.monotonic()
                if left<=0:raise TimeoutError('Inspector did not report '+method)
                self.condition.wait(left)

    def close(self):
        self.closed=True
        with self.condition:self.condition.notify_all()
        try:self.socket.close(timeout=1)
        except Exception:pass
