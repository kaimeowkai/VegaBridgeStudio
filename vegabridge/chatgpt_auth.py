"""Official public-client SIWC flow. No borrowed client IDs, secrets or tokens.

Credentials are exclusively app-owned CurrentUser-DPAPI records. Browser consent
is completed by the user. OAuth URLs, callbacks and token bodies are never logged.
"""
import contextlib
import hashlib
import json
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
import httpx
import jwt
from .storage import SecretStore, atomic_write, user_dir

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
_lock = threading.Lock()


@contextlib.contextmanager
def account_lock():
    # Serialize rotating refresh tokens across threads and Studio processes.
    import msvcrt
    with _lock, (user_dir() / "chatgpt-session.lock").open("a+b") as file:
        file.seek(0)
        if not file.read(1):
            file.write(b"0")
            file.flush()
        until = time.monotonic() + 35
        while True:
            file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() > until:
                    raise RuntimeError("Another Studio process is updating this ChatGPT session. Try again.")
                time.sleep(.1)
        try:
            yield
        finally:
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)


def host_id():
    with account_lock():
        path = user_dir() / "chatgpt-host.json"
        if path.exists():
            value = json.loads(path.read_text())["id"]
            uuid.UUID(value.removeprefix("urn:uuid:"))
            return value
        value = "urn:uuid:" + str(uuid.uuid4())
        atomic_write(path, json.dumps({"id": value}).encode())
        return value


def read_accounts():
    text = SecretStore().get("chatgpt-accounts")
    return json.loads(text) if text else {}


def write_accounts(accounts):
    SecretStore().set("chatgpt-accounts", json.dumps(accounts))


def list_accounts():
    with account_lock():
        return [{"key": key, "label": value.get("email") or value["subject"],
                 "clientSuffix": value["client_id"][-8:], "connected": bool(value.get("access_token"))}
                for key, value in read_accounts().items()]


def _json(response):
    if response.status_code != 200:
        raise RuntimeError(f"OpenAI sign-in request failed (HTTP {response.status_code}). Retry sign-in; no credentials were logged.")
    if len(response.content) > 1024 * 1024:
        raise RuntimeError("OpenAI authentication response exceeded the size limit")
    return response.json()


def discovery(client):
    doc = _json(client.get(ISSUER + "/.well-known/openid-configuration"))
    if doc.get("issuer") != ISSUER:
        raise RuntimeError("Unexpected OpenAI authentication issuer")
    for name in ["authorization_endpoint", "token_endpoint", "jwks_uri", "revocation_endpoint"]:
        value = urlsplit(doc.get(name, ""))
        if value.scheme != "https" or value.netloc != "auth.openai.com" or value.query or value.fragment:
            raise RuntimeError("Unexpected OpenAI authentication endpoint")
    return doc


def validate_identity(client, doc, token, client_id, nonce=None, expected_subject=None):
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in {"RS256", "ES256"}:
            raise ValueError("algorithm")
        keys = _json(client.get(doc["jwks_uri"]))["keys"]
        matches = [key for key in keys if key.get("kid") == header.get("kid")]
        if len(matches) != 1:
            raise ValueError("key")
        key = jwt.PyJWK.from_dict(matches[0], algorithm=header["alg"])
        claims = jwt.decode(token, key.key, algorithms=[header["alg"]], audience=client_id,
                            issuer=ISSUER, leeway=5, options={"require": ["sub", "exp", "iat"]})
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise ValueError("subject")
        if nonce is not None and not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise ValueError("nonce")
        if expected_subject and claims["sub"] != expected_subject:
            raise ValueError("account changed")
        return claims
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise RuntimeError("OpenAI identity validation failed. No account was changed.") from None


def token_record(tokens, claims, client_id, host, previous=None):
    if tokens.get("token_type", "").lower() != "bearer" or not tokens.get("access_token"):
        raise RuntimeError("OpenAI did not return a usable bearer token")
    previous = previous or {}
    scopes = tokens.get("scope")
    scopes = scopes.split() if isinstance(scopes, str) else previous.get("scopes", [])
    if not isinstance(tokens.get("expires_in"), (int, float)) or tokens["expires_in"] <= 0:
        raise RuntimeError("OpenAI did not return a valid token expiry")
    return dict(previous, subject=claims["sub"], email=claims.get("email", previous.get("email", "")),
                issuer=ISSUER, client_id=client_id, ext_agent_host_id=host,
                access_token=tokens["access_token"], refresh_token=tokens.get("refresh_token", previous.get("refresh_token", "")),
                id_token=tokens.get("id_token", previous.get("id_token", "")), scopes=scopes,
                expires_at=time.time() + tokens["expires_in"], token_type="Bearer")


class CallbackServer(HTTPServer):
    allow_reuse_address = False

    def get_request(self):
        connection,address=super().get_request()
        connection.settimeout(2)
        return connection,address

    def __init__(self, state):
        self.state, self.result = state, None
        super().__init__(("127.0.0.1", 0), CallbackHandler)
        self.timeout = .4
        self.redirect_uri = f"http://127.0.0.1:{self.server_port}/auth/callback"


class CallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query, keep_blank_values=True)
        valid = (parsed.path == "/auth/callback" and self.server.result is None
                 and len(self.path) < 8192 and all(len(v) == 1 for v in params.values())
                 and secrets.compare_digest(params.get("state", [""])[0], self.server.state))
        if not valid:
            self.send_error(400, "Invalid or expired sign-in callback")
            return
        self.server.result = {k: v[0] for k, v in params.items()}
        body = b"<!doctype html><title>VegaBridge Studio</title><h1>Return to VegaBridge Studio</h1><p>The app is verifying your sign-in. You may close this tab.</p>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)


def sign_in(runner, open_browser, account_key="", transport=None):
    host = host_id()
    with account_lock():
        previous = read_accounts().get(account_key)
    client_id = previous["client_id"] if previous else "dynamic_agent_client"
    state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
    import base64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with httpx.Client(timeout=20, follow_redirects=False, transport=transport) as client, CallbackServer(state) as server:
        doc = discovery(client)
        params = dict(client_id=client_id, ext_agent_host_id=host, response_type="code",
                      redirect_uri=server.redirect_uri, scope=SCOPES, resource=RESOURCE,
                      state=state, nonce=nonce, code_challenge_method="S256", code_challenge=challenge)
        if not previous:
            params["agent_name_hint"] = "VegaBridge Studio"
        # No token hints in URLs: returning users choose their account in OpenAI's browser UI.
        open_browser(doc["authorization_endpoint"] + "?" + urlencode(params))
        deadline = time.monotonic() + 300
        while server.result is None:
            runner.check()
            if time.monotonic() > deadline:
                raise TimeoutError("ChatGPT sign-in expired. Choose Continue with ChatGPT to try again.")
            server.handle_request()
        result = server.result
        if result.get("error"):
            raise RuntimeError("ChatGPT sign-in was declined or unavailable. Your existing account is unchanged.")
        issued = result.get("client_id", client_id if previous else "")
        if not issued.startswith("oaiapp_") or (previous and issued != client_id) or not result.get("code"):
            raise RuntimeError("ChatGPT registration was incomplete or returned a different client. Existing accounts are unchanged.")
        tokens = _json(client.post(doc["token_endpoint"], data=dict(grant_type="authorization_code", client_id=issued,
                        code=result["code"], code_verifier=verifier, redirect_uri=server.redirect_uri, resource=RESOURCE)))
        claims = validate_identity(client, doc, tokens.get("id_token", ""), issued, nonce,
                                   previous["subject"] if previous else None)
        record = token_record(tokens, claims, issued, host, previous)
        key = hashlib.sha256((issued + "\n" + claims["sub"]).encode()).hexdigest()[:32]
        with account_lock():
            accounts = read_accounts()
            accounts[key] = record
            write_accounts(accounts)
        return {"key": key, "label": record["email"] or record["subject"],
                "planEnabled": "chatgpt.tokens.use.direct" in record["scopes"],
                "welcome": not record.get("welcome_seen", False)}


def access_token(account_key, transport=None):
    with account_lock(), httpx.Client(timeout=20, follow_redirects=False, transport=transport) as client:
        accounts = read_accounts()
        record = accounts.get(account_key)
        if not record or not record.get("access_token"):
            raise RuntimeError("Continue with ChatGPT before using your ChatGPT plan.")
        if record["expires_at"] < time.time() + 90:
            if not record.get("refresh_token"):
                raise RuntimeError("ChatGPT session expired. Sign in again.")
            doc = discovery(client)
            tokens = _json(client.post(doc["token_endpoint"], data=dict(grant_type="refresh_token", client_id=record["client_id"],
                           refresh_token=record["refresh_token"], resource=RESOURCE)))
            claims = validate_identity(client, doc, tokens["id_token"], record["client_id"], expected_subject=record["subject"]) if tokens.get("id_token") else {"sub": record["subject"]}
            record = token_record(tokens, claims, record["client_id"], record["ext_agent_host_id"], record)
            accounts[account_key] = record
            write_accounts(accounts)
        if "chatgpt.tokens.use.direct" not in record["scopes"] or "resource.invoke" not in record["scopes"]:
            raise RuntimeError("ChatGPT plan use was not authorized. Continue with ChatGPT to enable it, or select API key / local model.")
        return record["access_token"]


def available_models(account_key, transport=None):
    token = access_token(account_key, transport)
    with httpx.Client(timeout=20, follow_redirects=False, transport=transport) as client:
        doc = _json(client.get(RESOURCE + "/models", headers={"Authorization": "Bearer " + token}))
    return [{"slug": item["slug"], "name": item.get("display_name", item["slug"])}
            for item in doc.get("models", []) if item.get("visibility") == "list" and item.get("slug")]


def welcome_seen(account_key):
    with account_lock():
        accounts = read_accounts()
        accounts[account_key]["welcome_seen"] = True
        write_accounts(accounts)


def sign_out(account_key, transport=None):
    confirmed = True
    with account_lock(), httpx.Client(timeout=15, follow_redirects=False, transport=transport) as client:
        accounts = read_accounts()
        record = accounts.get(account_key)
        if not record:
            return True
        if record.get("refresh_token"):
            confirmed = False
            try:
                endpoint = discovery(client)["revocation_endpoint"]
                for delay in [0, .5, 1]:
                    time.sleep(delay)
                    response = client.post(endpoint, data=dict(token=record["refresh_token"], token_type_hint="refresh_token", client_id=record["client_id"]))
                    if response.status_code == 200:
                        confirmed = True
                        break
                    if response.status_code < 500:
                        break
            except (httpx.HTTPError, RuntimeError):
                pass
        for name in ["access_token", "refresh_token", "id_token"]:
            record.pop(name, None)
        accounts[account_key] = record
        write_accounts(accounts)
    return confirmed
