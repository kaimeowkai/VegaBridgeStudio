"""Hermes CDP debugging of an installed development app through local Metro."""
import json
import re
import threading
import uuid
from pathlib import Path
from urllib.parse import urljoin,urlsplit,urlunsplit
import httpx
from .cdp import CdpClient,local_url
from .source_maps import SourceMap
from .project import metadata,inside


def metro_bytes(port,path):
    if type(port)!=int or not 1024<=port<=65535:raise ValueError('Choose an unprivileged Metro port')
    url=local_url(urljoin('http://127.0.0.1:'+str(port)+'/',path),port)
    with httpx.Client(trust_env=False,follow_redirects=False,timeout=12) as client:
        with client.stream('GET',url) as response:
            response.raise_for_status();data=bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data)>16*1024*1024:raise ValueError('Metro response exceeds 16 MiB')
    return bytes(data)


def metro_json(port,path):return json.loads(metro_bytes(port,path))


def canonical_script(source):
    return re.sub(r'^\s*//#\s*source(?:Mapping)?URL=.*$', '',source.replace('\r\n','\n'),flags=re.M).strip()


def map_host_url(url,port):
    # Hermes describes device-local 8081, which may be reversed to a different
    # Windows host port. No non-loopback or unrelated-port URL is accepted.
    parsed=urlsplit(url);local_url(url)
    if parsed.port not in {8081,port}:raise ValueError('Source map does not belong to the selected Metro connection')
    return urlunsplit(('http','127.0.0.1:'+str(port),parsed.path,parsed.query,''))


class JavaScriptDebugSession:
    def __init__(self,project,port,event=lambda message:None,settings=None,serial=''):
        self.project=Path(project).resolve();self.port=int(port);self.package=metadata(self.project)['id']
        self.event=event;self.id=uuid.uuid4().hex;self.client=None;self.scripts={};self.maps={};self.points={};self.breakpoints={};self.paused={}
        self.lock=threading.RLock();self.closed=False
        self.settings=dict(settings) if settings else None;self.serial=serial

    def emit(self,name,body=None):self.event({'sessionId':self.id,'event':name,'body':body or {}})

    def _event(self,value):
        method=value.get('method');params=value.get('params',{})
        if method=='Debugger.scriptParsed':
            with self.lock:
                for identifier,old in list(self.scripts.items()):
                    if identifier!=params['scriptId'] and params.get('url') and old.get('url')==params['url']:
                        self.scripts.pop(identifier,None);self.maps.pop(identifier,None)
                self.scripts[params['scriptId']]=params
        elif method=='Debugger.paused':
            with self.lock:self.paused=params
            self.emit('stopped',{'reason':params.get('reason','pause')})
        elif method=='Debugger.resumed':
            with self.lock:self.paused={}
            self.emit('continued')
        elif method=='Runtime.consoleAPICalled':
            text=' '.join(str(arg.get('value',arg.get('description',arg.get('type','')))) for arg in params.get('args',[]))
            self.emit('output',{'output':params.get('type','log')+': '+text})
        elif method=='Runtime.exceptionThrown':self.emit('output',{'output':'JavaScript exception: '+json.dumps(params.get('exceptionDetails',{}),ensure_ascii=False)[:5000]})
        elif method=='VegaBridge.evaluationResult':
            result=value.get('result',{})
            self.emit('output',{'output':'Console: '+json.dumps(value.get('error') or result.get('exceptionDetails') or result.get('result',{}),ensure_ascii=False)[:5000]})
        elif method=='VegaBridge.disconnected' and not self.closed:self.emit('terminated',{'reason':params.get('reason')})

    def start(self,breakpoints):
        try:
            if self.settings:
                from .devices import LocalBridge
                from .process import Runner
                from .installed_debug import component_process
                bridge=LocalBridge(self.settings,Runner(),self.serial);component_process(bridge,metadata(self.project)['component'])
                mappings=bridge.call(['reverse','--list'])
                if not any(len(row.split())>=3 and row.split()[-2:]==['tcp:8081','tcp:'+str(self.port)] for row in mappings.splitlines()):
                    raise RuntimeError('The selected target has no reverse connection to this Metro port. Use Build + run development app or configure its reverse mapping first.')
            candidates=[item for item in metro_json(self.port,'/json/list') if item.get('appId')==self.package]
            if len(candidates)!=1:raise RuntimeError('Expected one connected Hermes runtime for '+self.package+'. Build/run its development package and start the matching Metro project first.')
            target=candidates[0];url=local_url(target['webSocketDebuggerUrl'],self.port,True)
            if self.closed:raise RuntimeError('JavaScript attach was cancelled')
            self.client=CdpClient(url,self._event)
            if self.closed:raise RuntimeError('JavaScript attach was cancelled')
            self.client.request('Runtime.enable');self.client.request('Debugger.enable')
            self.client.request('Debugger.setPauseOnExceptions',{'state':'uncaught'})
            self.refresh_sources();resolved=[]
            for source,lines in breakpoints.items():resolved+=self.set_breakpoints(source,lines)
            return {'breakpoints':resolved,'session':self.id,'runtime':target.get('title',self.package)}
        except Exception:self.close();raise

    def refresh_sources(self):
        with self.lock:scripts=dict(self.scripts)
        for script_id,script in scripts.items():
            if script_id in self.maps or not script.get('sourceMapURL'):continue
            # Fetch only source maps from this selected loopback Metro instance.
            source_map_url=map_host_url(script['sourceMapURL'],self.port)
            if '.map?' not in source_map_url and not source_map_url.endswith('.map'):raise ValueError('Expected a Metro .map source-map endpoint')
            bundle_url=source_map_url.replace('.map?','.bundle?',1)
            if bundle_url.endswith('.map'):bundle_url=bundle_url[:-4]+'.bundle'
            running=self.client.request('Debugger.getScriptSource',{'scriptId':script_id}).get('scriptSource','')
            served=metro_bytes(self.port,bundle_url).decode('utf8')
            if canonical_script(running)!=canonical_script(served):
                raise ValueError('Metro source differs from the code running in the installed app. Build + run the development app again before attaching; source positions would otherwise be wrong.')
            data=metro_json(self.port,source_map_url);self.maps[script_id]=SourceMap(data,self.project)
        return {'mappedScripts':len(self.maps),'originalFiles':sorted({str(path.relative_to(self.project)) for source_map in self.maps.values() for path in source_map.reverse})}

    def set_breakpoints(self,source,lines):
        path=inside(self.project,Path(source).resolve())
        if path.suffix.lower() not in {'.js','.jsx','.ts','.tsx'}:return []
        if any(type(line)!=int or not 1<=line<=1000000 for line in lines):raise ValueError('Invalid breakpoint line')
        for identifier in self.breakpoints.pop(str(path),[]):
            try:self.client.request('Debugger.removeBreakpoint',{'breakpointId':identifier})
            except RuntimeError:pass
        self.points[str(path)]=list(lines);resolved=[];identifiers=[]
        self.refresh_sources()
        for line in sorted(set(lines)):
            match=None
            for script_id,source_map in self.maps.items():
                location=source_map.generated(path,line)
                if location:
                    source_map.verify_source(path)
                    result=self.client.request('Debugger.setBreakpoint',{'location':dict(location,scriptId=script_id)})
                    identifiers.append(result['breakpointId']);actual=result.get('actualLocation',location)
                    original=source_map.original(actual['lineNumber'],actual.get('columnNumber',0))
                    match={'verified':True,'line':original['line'] if original else line,'source':str(path)};break
            resolved.append(match or {'verified':False,'line':line,'message':'No original-source mapping. Reload/refresh the development bundle.'})
        self.breakpoints[str(path)]=identifiers
        return resolved

    def snapshot(self):
        with self.lock:frames=list(self.paused.get('callFrames',[]))
        self.refresh_sources();result=[]
        for frame in frames[:100]:
            location=frame['location'];source_map=self.maps.get(location['scriptId']);original=source_map.original(location['lineNumber'],location.get('columnNumber',0)) if source_map else None
            result.append({'id':frame['callFrameId'],'name':frame.get('functionName') or '(anonymous)',
                'source':{'path':original['path']} if original else {},'line':original['line'] if original else 0,
                'generatedLocation':location})
        return {'frames':result,'variables':self.variables_for_frame(result[0]['id']) if result else []}

    def variables_for_frame(self,identifier):
        with self.lock:frame=next((frame for frame in self.paused.get('callFrames',[]) if frame['callFrameId']==identifier),None)
        if not frame:return []
        return [{'scope':scope.get('name') or scope['type'],'items':self.variables(scope['object']['objectId'])}
            for scope in frame.get('scopeChain',[]) if scope['type'] in {'local','closure','block','catch','script'} and scope.get('object',{}).get('objectId')][:10]

    def variables(self,reference):
        result=self.client.request('Runtime.getProperties',{'objectId':str(reference),'ownProperties':True,'generatePreview':False})
        values=[]
        for prop in result.get('result',[])[:200]:
            value=prop.get('value',{})
            display=json.dumps(value['value'],ensure_ascii=False) if 'value' in value else value.get('unserializableValue',value.get('description','(accessor)' if 'get' in prop else value.get('type','')))
            values.append({'name':prop['name'],'value':str(display)[:2000],
                'type':value.get('type','accessor'),'variablesReference':value.get('objectId',0)})
        return values

    def evaluate(self,expression):
        if not expression or len(expression)>12000:raise ValueError('Enter a JavaScript expression under 12000 characters')
        with self.lock:frames=self.paused.get('callFrames',[])
        params={'expression':expression,'returnByValue':False,'generatePreview':False}
        if frames:return self.client.send('Debugger.evaluateOnCallFrame',dict(params,callFrameId=frames[0]['callFrameId']),asynchronous=True)
        return self.client.send('Runtime.evaluate',params,asynchronous=True)

    def control(self,command):
        methods={'continue':'Debugger.resume','pause':'Debugger.pause','next':'Debugger.stepOver','stepIn':'Debugger.stepInto','stepOut':'Debugger.stepOut'}
        if command not in methods:raise ValueError('Unknown JavaScript debugger control')
        return self.client.request(methods[command])

    def close(self):
        self.closed=True
        if self.client:
            try:
                # Always let the installed app continue when detaching.
                if self.paused:self.client.request('Debugger.resume',timeout=2)
                self.client.request('Debugger.disable',timeout=2)
            except Exception:pass
            self.client.close()
