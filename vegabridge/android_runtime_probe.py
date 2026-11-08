"""Non-mutating observations for Android runtime research, not APK execution."""
import re

NODES=['/dev/kvm','/dev/binder','/dev/hwbinder','/dev/vndbinder','/dev/binderfs/binder','/dev/ashmem','/dev/dri/renderD128']
KERNEL_KEYS={'CONFIG_USER_NS':'USER_NS','CONFIG_ANDROID_BINDERFS':'BINDERFS',
             'CONFIG_ANDROID_BINDER_IPC':'BINDER_IPC','CONFIG_MEMFD_CREATE':'MEMFD','CONFIG_KVM':'KVM'}
COMMAND=(
 "printf 'MACHINE='; uname -m; printf 'KERNEL_RELEASE='; uname -r; printf 'LONG_BIT='; getconf LONG_BIT 2>/dev/null || printf 'unknown\\n'; "
 "awk '/^MemTotal:/ {print \"MEM_TOTAL_KB=\"$2} /^MemAvailable:/ {print \"MEM_AVAILABLE_KB=\"$2}' /proc/meminfo; "
 "awk '/^CapEff:/ {print \"CAP_EFF=\"$2} /^Seccomp:/ {print \"SECCOMP=\"$2} /^NoNewPrivs:/ {print \"NO_NEW_PRIVS=\"$2}' /proc/self/status; "
 "printf 'UID='; id -u; "
 "for vb_node in "+' '.join(NODES)+"; do vb_state=missing; if [ -e \"$vb_node\" ]; then vb_state=present; "
 "if [ -r \"$vb_node\" ] && [ -w \"$vb_node\" ]; then vb_state=read-write-permissions; fi; fi; printf 'NODE=%s:%s\\n' \"$vb_node\" \"$vb_state\"; done; "
 "if grep -q binder /proc/filesystems 2>/dev/null; then printf 'BINDER_FS=listed\\n'; else printf 'BINDER_FS=not-listed\\n'; fi; "
 "if command -v app_process >/dev/null 2>&1; then printf 'APP_PROCESS=on-PATH\\n'; else printf 'APP_PROCESS=not-on-PATH\\n'; fi; "
 "if [ -r /proc/sys/user/max_user_namespaces ]; then printf 'MAX_USER_NAMESPACES='; cat /proc/sys/user/max_user_namespaces; fi; "
 "if [ -r /proc/config.gz ] && command -v zcat >/dev/null 2>&1; then zcat /proc/config.gz 2>/dev/null | "
 "awk 'BEGIN {FS=\"=\"} "
 + ' '.join('/^'+key+'=/ {print "KERNEL_'+value+'="$2} /^# '+key+' is not set$/ {print "KERNEL_'+value+'=n"}' for key,value in KERNEL_KEYS.items())
 + "'; fi"
)


def parse_observations(text,scope):
    values={};nodes={}
    for line in text.splitlines():
        key,sep,value=line.strip().partition('=')
        if not sep:continue
        if key=='NODE':
            name,_,state=value.partition(':')
            if name in NODES and state in {'missing','present','read-write-permissions'}:nodes[name]=state
        elif key in {'MACHINE','KERNEL_RELEASE','LONG_BIT','MEM_TOTAL_KB','MEM_AVAILABLE_KB','CAP_EFF','SECCOMP','NO_NEW_PRIVS',
                     'UID','BINDER_FS','APP_PROCESS','MAX_USER_NAMESPACES'} | {'KERNEL_'+name for name in KERNEL_KEYS.values()}:
            if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',value):values[key]=value
    if 'MACHINE' not in values:raise RuntimeError('Runtime probe returned no recognizable machine observation')
    return {'scope':scope,'values':values,'nodes':nodes,'actualAppRuntimeTested':False,
        'limits':['Node visibility and read/write mode are not successful ioctl, mount, GPU, virtualization or Android boot tests.',
                  'Developer shells can differ from a published application context. Missing nodes are not exposed in this context; kernel support is not proven absent.']}


def summarize(observations):
    notes=[]
    for item in observations:
        nodes=item['nodes'];scope=item['scope']
        if nodes.get('/dev/kvm')=='missing':notes.append(scope+': KVM device is not exposed. Software emulation remains a separate untested option.')
        if not any(nodes.get(name) in {'present','read-write-permissions'} for name in NODES if 'binder' in name):
            notes.append(scope+': Android Binder devices are not exposed; a container runtime has an unresolved prerequisite.')
        if item['values'].get('KERNEL_BINDERFS')=='n':
            notes.append(scope+': The exposed kernel configuration disables binderfs. The conventional private-Binder container route is blocked in this configuration; existing Vega Binder devices must not be repurposed.')
        if item['values'].get('KERNEL_USER_NS')=='n' or item['values'].get('MAX_USER_NAMESPACES')=='0':
            notes.append(scope+': Unprivileged user namespaces are disabled. A container design relying on them has an unresolved isolation prerequisite.')
    return {'schemaVersion':1,'status':'Capability observations only','androidRuntimeImplemented':False,'apkExecutionTested':False,
        'observations':observations,'unresolvedPrerequisites':notes,
        'researchTracks':{'container':'Requires Android kernel/services/graphics integration; not demonstrated.',
                          'virtualMachine':'Requires an Android guest, emulator backend, graphics/input/audio and resource qualification; not demonstrated.'},
        'allAndroidAppsSupported':False,
        'namespaceSyscallsTested':False,
        'containerReady':False,
        'kernelConfigurationIsNotPermissionProof':True}


def collect_runtime(bridge,component=''):
    observations=[parse_observations(bridge.shell(COMMAND,timeout=15),'Developer shell')]
    errors=[]
    if component:
        try:observations.append(parse_observations(bridge.component_shell(component,COMMAND,timeout=15),'Developer component shell'))
        except Exception:errors.append('Developer component context was unavailable; no application-context capability claim was made.')
    report=summarize(observations);report['contextLimitations']=errors
    return report
