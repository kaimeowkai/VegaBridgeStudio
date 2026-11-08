import json
import time
from urllib.parse import urlsplit, parse_qs, urlencode
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from vegabridge import chatgpt_auth as auth
from vegabridge.storage import SecretStore
from vegabridge.process import Runner


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, 'user_dir', lambda: tmp_path)
    monkeypatch.setattr(auth, 'SecretStore', lambda: SecretStore(tmp_path / 'secrets'))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {'kid':'test-key','alg':'RS256'}
    context = {'key':key, 'jwk':jwk, 'scope':auth.SCOPES, 'requests':[]}
    def handle(request):
        context['requests'].append(request)
        if request.url.path.endswith('openid-configuration'):
            return httpx.Response(200, json={'issuer':auth.ISSUER,'authorization_endpoint':auth.ISSUER+'/authorize','token_endpoint':auth.ISSUER+'/token','jwks_uri':auth.ISSUER+'/jwks','revocation_endpoint':auth.ISSUER+'/revoke'})
        if request.url.path=='/jwks':
            return httpx.Response(200, json={'keys':[jwk]})
        if request.url.path=='/token':
            data = parse_qs(request.content.decode())
            assert data['client_id']==['oaiapp_vega_test']
            assert data['resource']==[auth.RESOURCE]
            if data['grant_type']==['authorization_code']:
                assert len(data['code_verifier'][0]) >= 43
                assert data['redirect_uri']==[context['redirect_uri']]
            now=int(time.time())
            claims={'iss':auth.ISSUER,'sub':'test-user','aud':'oaiapp_vega_test','iat':now,'exp':now+300,'nonce':context['nonce'],'email':'test@example.invalid'}
            claims.update(context.get('bad_claims',{}))
            token=jwt.encode(claims,key,algorithm='RS256',headers={'kid':'test-key'})
            return httpx.Response(200,json={'access_token':'test-access','refresh_token':'test-refresh-rotated','id_token':token,'scope':context['scope'],'token_type':'Bearer','expires_in':3600})
        if request.url.path=='/v1/models':
            assert request.headers['Authorization']=='Bearer test-access'
            return httpx.Response(200,json={'models':[{'slug':'visible-model','display_name':'Visible','visibility':'list'},{'slug':'hidden','visibility':'hidden'}]})
        if request.url.path=='/revoke':
            return httpx.Response(200)
        raise AssertionError(str(request.url))
    context['transport']=httpx.MockTransport(handle)
    def browser(url):
        p=parse_qs(urlsplit(url).query)
        assert p['code_challenge_method']==['S256']
        assert 'id_token_hint' not in p
        context['nonce']=p['nonce'][0]
        context['redirect_uri']=p['redirect_uri'][0]
        context['authorize']=p
        params={'state':p['state'][0],'client_id':'oaiapp_vega_test','code':'one-time-test-code'} | context.get('callback',{})
        # Callback listener is already bound. Issue request from another thread
        # because its accept loop starts after the browser callback returns.
        import threading
        def callback():
            httpx.get(context['redirect_uri']+'?'+urlencode(params),timeout=4)
        thread=threading.Thread(target=callback)
        thread.start()
    context['browser']=browser
    return context


def test_registration_persists_host_validates_identity_and_refreshes(provider):
    p=provider
    result=auth.sign_in(Runner(),p['browser'],transport=p['transport'])
    assert result['planEnabled'] and result['label']=='test@example.invalid'
    key=result['key']
    assert auth.access_token(key,p['transport'])=='test-access'
    assert auth.available_models(key,p['transport'])==[{'slug':'visible-model','name':'Visible'}]
    accounts=auth.read_accounts(); accounts[key]['expires_at']=0
    auth.write_accounts(accounts)
    assert auth.access_token(key,p['transport'])=='test-access'
    assert auth.read_accounts()[key]['refresh_token']=='test-refresh-rotated'
    first_host=p['authorize']['ext_agent_host_id']
    auth.sign_in(Runner(),p['browser'],key,transport=p['transport'])
    assert p['authorize']['client_id']==['oaiapp_vega_test']
    assert p['authorize']['ext_agent_host_id']==first_host
    assert 'agent_name_hint' not in p['authorize']
    assert auth.sign_out(key,p['transport'])
    assert not auth.list_accounts()[0]['connected']
    assert not {'id_token','access_token','refresh_token'} & auth.read_accounts()[key].keys()


@pytest.mark.parametrize('claims',[{'nonce':'wrong'},{'aud':'other-client'},{'iss':'https://other.invalid'},{'exp':1}])
def test_invalid_identity_never_saved(provider,claims):
    provider['bad_claims']=claims
    with pytest.raises(RuntimeError,match='identity validation'):
        auth.sign_in(Runner(),provider['browser'],transport=provider['transport'])
    assert auth.list_accounts()==[]


def test_declined_consent_and_missing_plan_grant(provider):
    p=provider; p['callback']={'error':'access_denied'}
    with pytest.raises(RuntimeError,match='declined'):
        auth.sign_in(Runner(),p['browser'],transport=p['transport'])
    assert not any(r.url.path=='/token' for r in p['requests'])
    p['callback']={};p['scope']='openid profile email'
    result=auth.sign_in(Runner(),p['browser'],transport=p['transport'])
    assert not result['planEnabled']
    with pytest.raises(RuntimeError,match='not authorized'):
        auth.access_token(result['key'],p['transport'])


def test_wrong_state_callback_is_not_consumed():
    import threading
    with auth.CallbackServer('expected') as server:
        thread=threading.Thread(target=server.handle_request)
        thread.start()
        response=httpx.get(server.redirect_uri+'?state=wrong&code=bad')
        thread.join()
        assert response.status_code==400 and server.result is None
