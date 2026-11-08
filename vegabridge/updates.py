"""Public-repository update discovery, bounded downloads and portable staging."""
import hashlib
import json
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urljoin
import httpx
from .storage import atomic_write, user_dir

REPOSITORY='https://github.com/kaimeowkai/VegaBridgeStudio'
API='https://api.github.com/repos/kaimeowkai/VegaBridgeStudio/releases?per_page=20'
DOWNLOAD_HOSTS={'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}
MAX_ZIP=512*1024*1024
MAX_EXTRACTED=1500*1024*1024


def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'v?(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})',value):
        raise ValueError('Unsupported release version')
    return tuple(int(piece) for piece in value.removeprefix('v').split('.'))


def choose_release(rows,current,include_preview=True):
    installed=version_tuple(current)
    candidates=[]
    if not isinstance(rows,list):raise ValueError('Invalid release response')
    for release in rows[:20]:
        try:
            if release.get('draft') or (release.get('prerelease') and not include_preview):continue
            tag=release['tag_name'];version=version_tuple(tag)
            if version<=installed:continue
            normal='.'.join(map(str,version));expected=f'VegaBridgeStudio-{normal}-windows-x64.zip'
            url=REPOSITORY+'/releases/tag/'+tag
            if release['html_url']!=url:continue
            assets=release.get('assets',[])
            found=[asset for asset in assets if asset['name']==expected and asset.get('state')=='uploaded']
            sums=[asset for asset in assets if asset['name']=='SHA256SUMS.txt' and asset.get('state')=='uploaded']
            if len(found)!=1 or len(sums)!=1:continue
            asset=found[0];digest=asset.get('digest','')
            if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}',digest or ''):continue
            for item in [asset,sums[0]]:
                wanted=REPOSITORY+'/releases/download/'+tag+'/'+item['name']
                if item['browser_download_url']!=wanted:raise ValueError('Unexpected release download URL')
            size=asset['size']
            if not isinstance(size,int) or not 1<=size<=MAX_ZIP:continue
            candidates.append({'version':normal,'tag':tag,'url':url,'asset':expected,
                'download':asset['browser_download_url'],'size':size,'sha256':digest[7:].lower(),
                'checksums':sums[0]['browser_download_url'],'notes':str(release.get('body') or '')[:40000]})
        except (ValueError,KeyError,TypeError):continue
    return max(candidates,key=lambda row:version_tuple(row['version'])) if candidates else None


def check_updates(current,include_preview=True,client=None):
    owned=client is None
    client=client or httpx.Client(timeout=httpx.Timeout(20,connect=8),headers={'User-Agent':'VegaBridgeStudio/'+current,'Accept':'application/vnd.github+json'})
    try:
        with client.stream('GET',API) as response:
            response.raise_for_status();data=bytearray()
            for block in response.iter_bytes():
                data.extend(block)
                if len(data)>2*1024*1024:raise ValueError('Release response exceeded 2 MiB')
        return choose_release(json.loads(data),current,include_preview)
    finally:
        if owned:client.close()


def trusted_download_url(value):
    parsed=urlsplit(value)
    if parsed.scheme!='https' or parsed.hostname not in DOWNLOAD_HOSTS or parsed.username or parsed.password or parsed.port not in {None,443}:
        raise ValueError('Update download left the permitted GitHub hosts')
    return value


def download_file(client,url,path,limit,runner,expected_size=None):
    url=trusted_download_url(url)
    for _ in range(6):
        with client.stream('GET',url,follow_redirects=False) as response:
            if response.is_redirect:
                url=trusted_download_url(urljoin(url,response.headers['location']));continue
            response.raise_for_status();total=0;digest=hashlib.sha256()
            with Path(path).open('xb') as output:
                for block in response.iter_bytes(1024*1024):
                    runner.check();total+=len(block)
                    if total>limit:raise ValueError('Update download exceeded its size bound')
                    output.write(block);digest.update(block)
            if expected_size is not None and total!=expected_size:raise ValueError('Update download is incomplete')
            return digest.hexdigest()
    raise ValueError('Too many update download redirects')


def safe_member(name):
    path=PurePosixPath(name)
    if not name or '\\' in name or path.is_absolute() or '..' in path.parts or len(path.parts)<2 or path.parts[0]!='VegaBridgeStudio':
        raise ValueError('Update archive contains an unsafe path')
    for part in path.parts:
        if part in {'.','..'} or part.endswith((' ','.')) or ':' in part or any(ord(char)<32 for char in part):
            raise ValueError('Update archive contains an unsafe filename')
        if part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
            raise ValueError('Update archive contains a reserved filename')
    return path


def verify_install(folder, reject_extra=True):
    folder=Path(folder).resolve()
    manifest_path=folder/'Install-Manifest.json'
    if not manifest_path.is_file() or manifest_path.is_symlink():raise ValueError('Installation manifest is missing or linked')
    if manifest_path.stat().st_size>2*1024*1024:raise ValueError('Invalid installation manifest')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    version_tuple(manifest['version'])
    files=manifest['files']
    if not isinstance(files,dict) or not 3<=len(files)<=10000:raise ValueError('Invalid installation manifest inventory')
    expected={'Install-Manifest.json'}
    for relative,digest in files.items():
        member=safe_member('VegaBridgeStudio/'+relative)
        path=folder.joinpath(*member.parts[1:])
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(folder):raise ValueError('Linked installation files cannot be updated')
        if not re.fullmatch('[a-f0-9]{64}',digest) or not path.is_file() or hashlib.file_digest(path.open('rb'),'sha256').hexdigest()!=digest:
            raise ValueError('Installation file verification failed: '+relative)
        expected.add(relative)
    for name in ['VegaBridgeStudio.exe','VegaBridgeCLI.exe','VegaBridgeUpdater.exe']:
        if name not in files or (folder/name).read_bytes()[:2]!=b'MZ':raise ValueError('Update is missing its Windows executables')
    if reject_extra:
        # Refuse to sweep unrelated user files into an installation replacement.
        actual=set()
        for path in folder.rglob('*'):
            if path.is_symlink() or path.is_junction():raise ValueError('Installation includes a linked folder or file')
            if path.is_file():actual.add(path.relative_to(folder).as_posix())
        if actual!=expected:raise ValueError('Installation contains added files. Move projects or custom files outside the app folder before updating.')
    return manifest


def extract_update(archive,destination,version):
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Update staging folder already exists')
    with zipfile.ZipFile(archive) as source:
        members=[item for item in source.infolist() if not item.is_dir()]
        if not 3<=len(members)<=10000 or sum(item.file_size for item in members)>MAX_EXTRACTED:
            raise ValueError('Update archive exceeds extraction bounds')
        seen=set()
        for item in members:
            path=safe_member(item.orig_filename)
            if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('Update archive contains a link')
            key=str(path).casefold()
            if key in seen:raise ValueError('Update archive contains duplicate Windows paths')
            seen.add(key)
        destination.mkdir()
        try:
            for item in members:
                path=safe_member(item.orig_filename)
                output=destination.joinpath(*path.parts[1:])
                output.parent.mkdir(parents=True,exist_ok=True)
                with source.open(item) as src, output.open('xb') as dst:shutil.copyfileobj(src,dst)
            manifest=verify_install(destination)
            if version_tuple(manifest['version'])!=version_tuple(version):raise ValueError('Update version does not match the verified release')
        except Exception:
            # destination was created exclusively by this call; never remove an existing installation.
            if destination.is_dir() and not destination.is_symlink() and destination.resolve()==destination:
                shutil.rmtree(destination)
            raise
    return destination


def prepare_update(release,runner,installation=None,client=None):
    from . import __version__
    if version_tuple(release['version'])<=version_tuple(__version__):raise ValueError('Refusing an update downgrade')
    if release['download']!=REPOSITORY+'/releases/download/'+release['tag']+'/'+release['asset']:
        raise ValueError('Update does not belong to the configured repository')
    if installation is None:
        if not getattr(sys,'frozen',False):raise ValueError('Automatic installation is available in the packaged Windows app. Source checkouts should update through Git.')
        installation=Path(sys.executable).parent
    target=Path(installation).resolve()
    current=verify_install(target)
    if version_tuple(release['version'])<=version_tuple(current['version']):raise ValueError('Refusing an installation downgrade')
    updates=user_dir()/'updates';updates.mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='download-',dir=updates))
    stage=target.parent/('.vegabridge-update-'+uuid.uuid4().hex)
    owned=client is None
    client=client or httpx.Client(timeout=httpx.Timeout(40,connect=10),headers={'User-Agent':'VegaBridgeStudio/'+__version__})
    try:
        runner.emit('Downloading VegaBridge Studio '+release['version']+' from the public project release…')
        checksum=work/'SHA256SUMS.txt'
        download_file(client,release['checksums'],checksum,65536,runner)
        expected=[line.split()[0].lower() for line in checksum.read_text(encoding='utf-8').splitlines() if len(line.split())==2 and line.split()[1]==release['asset']]
        if expected!=[release['sha256']]:raise ValueError('GitHub asset digest and release checksum disagree')
        archive=work/'release.zip'
        digest=download_file(client,release['download'],archive,MAX_ZIP,runner,release['size'])
        if digest!=release['sha256']:raise ValueError('Downloaded update failed SHA-256 verification')
        runner.check();extract_update(archive,stage,release['version'])
        plan={'schema':1,'target':str(target),'stage':str(stage),'backup':str(target.with_name(target.name+'.previous-'+uuid.uuid4().hex)),
              'version':release['version'],'previousVersion':current['version'],'pid':__import__('os').getpid(),'zipSha256':digest}
        path=work/'Update-Plan.json';atomic_write(path,json.dumps(plan,indent=2).encode('utf-8'))
        atomic_write(updates/'ready.json',json.dumps({'plan':str(path)}).encode('utf-8'))
        return str(path)
    finally:
        if owned:client.close()


def ready_update(installation,current):
    """Recover a prepared update across restarts; the worker re-verifies payloads."""
    try:
        updates=(user_dir()/'updates').resolve()
        pointer=updates/'ready.json'
        if pointer.stat().st_size>4096:return None
        path=Path(json.loads(pointer.read_text(encoding='utf-8'))['plan']).resolve()
        if not path.is_relative_to(updates) or path.name!='Update-Plan.json' or path.stat().st_size>16384:return None
        plan=json.loads(path.read_text(encoding='utf-8'))
        target=Path(installation).resolve();stage=Path(plan['stage'])
        if Path(plan['target']).resolve()!=target or stage.is_symlink() or stage.is_junction() or not stage.is_dir():return None
        if stage.resolve().parent!=target.parent or not stage.name.startswith('.vegabridge-update-'):return None
        if version_tuple(plan['version'])<=version_tuple(current):return None
        return str(path)
    except (OSError,ValueError,TypeError,KeyError):return None
