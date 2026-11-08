import hashlib
import json
import zipfile
from pathlib import Path
import httpx
import pytest
from vegabridge.updates import (REPOSITORY,API,choose_release,check_updates,extract_update,verify_install,
    download_file,prepare_update,version_tuple)
from vegabridge.update_apply import apply_plan
from vegabridge.process import Runner,Cancelled


def installation(folder,version):
    folder.mkdir(parents=True)
    files={}
    for name in ['VegaBridgeStudio.exe','VegaBridgeCLI.exe','VegaBridgeUpdater.exe']:
        data=b'MZ synthetic test fixture '+version.encode()
        (folder/name).write_bytes(data);files[name]=hashlib.sha256(data).hexdigest()
    (folder/'Install-Manifest.json').write_text(json.dumps({'version':version,'files':files}),encoding='utf-8')
    return folder


def archive_install(folder,path):
    with zipfile.ZipFile(path,'w') as archive:
        for file in folder.iterdir():archive.write(file,'VegaBridgeStudio/'+file.name)
    return path


def release(version='0.5.1',digest='a'*64,size=100,preview=True):
    name=f'VegaBridgeStudio-{version}-windows-x64.zip'
    assets=[{'name':name,'state':'uploaded','digest':'sha256:'+digest,'size':size,
             'browser_download_url':REPOSITORY+'/releases/download/v'+version+'/'+name},
            {'name':'SHA256SUMS.txt','state':'uploaded','browser_download_url':REPOSITORY+'/releases/download/v'+version+'/SHA256SUMS.txt'}]
    return {'tag_name':'v'+version,'html_url':REPOSITORY+'/releases/tag/v'+version,'draft':False,'prerelease':preview,'assets':assets,'body':'Synthetic release notes'}


def test_release_selection_has_explicit_preview_channel_no_downgrade_or_foreign_urls():
    row=release()
    assert choose_release([row],'0.5.0')['version']=='0.5.1'
    assert choose_release([row],'0.5.0',False) is None
    assert choose_release([row],'0.5.1') is None
    row['assets'][0]['browser_download_url']='https://example.com/other.zip'
    assert choose_release([row],'0.5.0') is None
    row=release();row['draft']=True
    assert choose_release([row],'0.5.0') is None
    with pytest.raises(ValueError):version_tuple('v0.5.1/../../other')


def test_public_check_has_no_account_credentials_and_handles_preview_only_repository():
    def serve(request):
        assert str(request.url)==API
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        return httpx.Response(200,json=[release()])
    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        assert check_updates('0.5.0',client=client)['version']=='0.5.1'


def test_download_rejects_redirect_outside_github_before_request(tmp_path):
    urls=[]
    def serve(request):
        urls.append(str(request.url))
        return httpx.Response(302,headers={'location':'https://example.com/private'})
    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        with pytest.raises(ValueError,match='permitted GitHub'):
            download_file(client,REPOSITORY+'/releases/download/v0.5.1/app.zip',tmp_path/'update.zip',100,Runner())
    assert len(urls)==1
    assert not (tmp_path/'update.zip').exists()


@pytest.mark.parametrize('member',['VegaBridgeStudio/../../escape','/absolute','VegaBridgeStudio/NUL.txt','VegaBridgeStudio/x:secret','VegaBridgeStudio/path\\escape'])
def test_update_archive_refuses_windows_escape_paths(tmp_path,member):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as output:
        raw=zipfile.ZipInfo();raw.filename=member
        output.writestr(raw,b'bad');output.writestr('VegaBridgeStudio/a',b'a');output.writestr('VegaBridgeStudio/b',b'b')
    with pytest.raises(ValueError):extract_update(archive,tmp_path/'stage','0.5.1')
    assert not (tmp_path/'stage').exists()
    assert not (tmp_path/'escape').exists()


def test_archive_case_collisions_and_tampering_are_refused(tmp_path):
    folder=installation(tmp_path/'new','0.5.1');archive=archive_install(folder,tmp_path/'new.zip')
    with zipfile.ZipFile(archive,'a') as output:output.writestr('VegaBridgeStudio/vegabridgestudio.EXE',b'MZduplicate')
    with pytest.raises(ValueError,match='duplicate'):extract_update(archive,tmp_path/'stage','0.5.1')
    (folder/'VegaBridgeStudio.exe').write_bytes(b'MZtampered')
    with pytest.raises(ValueError,match='verification failed'):verify_install(folder)


def test_added_user_files_block_update_replacement_and_remain_untouched(tmp_path):
    folder=installation(tmp_path/'installed','0.5.0')
    original=folder/'MyProject.txt';original.write_text('Keep this original',encoding='utf-8')
    with pytest.raises(ValueError,match='added files'):verify_install(folder)
    assert original.read_text()=='Keep this original'


def test_download_staging_verifies_both_digests_and_leaves_current_installation(tmp_path,monkeypatch):
    import vegabridge.updates as updates
    current=installation(tmp_path/'installed','0.5.0');new=installation(tmp_path/'new','0.5.1')
    archive=archive_install(new,tmp_path/'new.zip');data=archive.read_bytes();digest=hashlib.sha256(data).hexdigest()
    info=choose_release([release(digest=digest,size=len(data))],'0.5.0')
    state=tmp_path/'state';state.mkdir();monkeypatch.setattr(updates,'user_dir',lambda:state)
    def serve(request):
        if str(request.url)==info['checksums']:return httpx.Response(200,text=digest+'  '+info['asset']+'\n')
        assert str(request.url)==info['download']
        return httpx.Response(200,content=data)
    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        plan=Path(prepare_update(info,Runner(),current,client))
    doc=json.loads(plan.read_text())
    assert verify_install(Path(doc['stage']))['version']=='0.5.1'
    assert verify_install(current)['version']=='0.5.0'
    assert updates.ready_update(current,'0.5.0')==str(plan)
    assert updates.ready_update(current,'0.5.1') is None
    assert updates.ready_update(tmp_path/'other','0.5.0') is None


def plan_for(tmp_path):
    current=installation(tmp_path/'installed','0.5.0')
    new=installation(tmp_path/'.vegabridge-update-fixture','0.5.1')
    path=tmp_path/'plan.json'
    path.write_text(json.dumps({'schema':1,'target':str(current),'stage':str(new),
        'backup':str(tmp_path/'installed.previous-fixture'),'version':'0.5.1','previousVersion':'0.5.0','pid':0}),encoding='utf-8')
    return path,current,new


def test_portable_swap_retains_verified_previous_version(tmp_path):
    plan,current,new=plan_for(tmp_path)
    receipt=apply_plan(plan,wait=False,restart=False)
    assert receipt['installed'] and not receipt['oldInstallationDeleted']
    assert verify_install(current)['version']=='0.5.1'
    assert verify_install(Path(receipt['rollback']))['version']=='0.5.0'
    assert not new.exists()


def test_failed_swap_rolls_back_without_deleting_old_installation(tmp_path,monkeypatch):
    plan,current,new=plan_for(tmp_path);rename=Path.rename
    def fail_second(self,target):
        if self==new:raise OSError('Synthetic replacement failure')
        return rename(self,target)
    monkeypatch.setattr(Path,'rename',fail_second)
    with pytest.raises(OSError):apply_plan(plan,wait=False,restart=False)
    assert verify_install(current)['version']=='0.5.0'
    assert verify_install(new)['version']=='0.5.1'


def test_apply_refuses_unrelated_staging_folder(tmp_path):
    plan,current,new=plan_for(tmp_path);doc=json.loads(plan.read_text());doc['stage']=str(tmp_path/'unrelated')
    plan.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='folder layout'):apply_plan(plan,wait=False,restart=False)
    assert verify_install(current)['version']=='0.5.0'
