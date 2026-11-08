import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import threading
from pathlib import Path
import httpx
import pytest
import zstandard
from cryptography.hazmat.primitives import serialization
from vegabridge.storage import dpapi, SecretStore
from vegabridge.project import create_project, metadata, safe_context, inside
from vegabridge.devices import endpoint, parse_devices, LocalBridge, RemoteEmulator
from vegabridge.assistant import events, stream_chat, validate_url
from vegabridge.process import Runner, Cancelled
from vegabridge.package import pack, inspect_package, identity


def test_dpapi_and_secret_store(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows DPAPI")
    plain = b"test-only-credential-not-a-real-key"
    encrypted = dpapi(plain)
    assert plain not in encrypted
    assert dpapi(encrypted, True) == plain
    store = SecretStore(tmp_path)
    store.set("test-key", plain.decode())
    assert store.get("test-key") == plain.decode()
    store.remove("test-key")
    assert not store.get("test-key")
    with pytest.raises(ValueError):
        store.path("../escape")


def test_create_project_and_no_overwrite(tmp_path):
    folder = create_project(tmp_path / "new", 'Title "quoted"', "com.example.test")
    assert metadata(folder)["title"] == 'Title "quoted"'
    assert metadata(folder)["component"] == "com.example.test.main"
    assert "com.example.test.main" in (folder / "index.js").read_text()
    assert (folder / "package-lock.json").exists()
    with pytest.raises(ValueError):
        create_project(folder, "Other", "com.example.other")
    with pytest.raises(ValueError):
        create_project(tmp_path / "bad", "Bad", "com.x;rm")


@pytest.mark.parametrize("name,text", [(".env", "whatever"), ("private/source.js", "x"), ("source.js", "sk-" + "A"*30), ("source.js", 'password = "not-for-sharing"')])
def test_context_rejects_private_files(tmp_path, name, text):
    path = tmp_path / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    with pytest.raises(ValueError):
        safe_context(tmp_path, path, text)


def test_context_relative_path_and_selection(tmp_path):
    path = tmp_path / "index.js"
    path.write_text("let n = 1;")
    assert safe_context(tmp_path, path, "let n = 1;").startswith("File: index.js")
    with pytest.raises(ValueError):
        inside(tmp_path, tmp_path.parent / "escape")


@pytest.mark.parametrize("invalid", ["-host", "host:99999", "host;rm -rf", "host:0", "http://host"])
def test_wireless_endpoint_validation(invalid):
    with pytest.raises(ValueError):
        endpoint(invalid)


def test_devices_parse_usb_wireless_and_unauthorized():
    parsed = parse_devices("List of devices attached\nUSB123 device usb:1\n192.168.1.2:5555 device\nemulator-5554 offline\nUSB456 unauthorized")
    assert [d["kind"] for d in parsed] == ["USB", "Wireless", "Emulator", "USB"]
    assert parsed[-1]["state"] == "unauthorized"
    assert endpoint("192.168.1.2") == "192.168.1.2:5555"


def test_legacy_shell_preserves_remote_exit_status(monkeypatch):
    import re
    import vegabridge.devices as devices
    monkeypatch.setattr(devices, "tool_path", lambda configured, name: name)
    class Fake:
        code = 0
        def emit(self, text):
            pass
        def run(self, args, **kwargs):
            assert "-x" in args
            marker = re.search(r"__VEGABRIDGE_RC_[a-f0-9]+__", args[-1])[0]
            return "device output\n" + marker + str(self.code) + "\n"
    runner = Fake()
    bridge = LocalBridge({"adb": "adb.exe", "bridge_port": 5048}, runner, "DEVICE123")
    assert bridge.shell("uname -a") == "device output"
    runner.code = 7
    with pytest.raises(RuntimeError, match="status 7"):
        bridge.shell("false")


def test_screenshot_retries_transient_display_commit(tmp_path):
    from vegabridge.devices import DeviceCommandError
    class CaptureBridge(LocalBridge):
        def __init__(self):
            self.runner = Runner()
            self.attempts = 0
        def shell(self, command, **kwargs):
            if "gwsi-tool-screenshooter" in command:
                self.attempts += 1
                if self.attempts == 1:
                    raise DeviceCommandError(1, "Screenshot error: drm: atomic commit failed")
            return ""
        def pull(self, remote, local):
            Path(local).write_bytes(b"\x89PNG\r\n\x1a\n" + b"test-payload")
    bridge = CaptureBridge()
    assert bridge.screenshot(tmp_path / "capture.png").endswith("capture.png")
    assert bridge.attempts == 2


def test_stream_events_multi_line_and_terminal():
    assert list(events(['data: {"type":', 'data: "response.completed"}', '', 'data: [DONE]', ''])) == [{"type": "response.completed"}, {"type": "done"}]


def test_response_stream_waits_for_completion():
    seen = []
    def handle(request):
        body = json.loads(request.content)
        assert body["store"] is False and body["stream"] is True
        assert request.headers["Authorization"] == "Bearer unit-test-key"
        assert "tools" not in body
        seen.append(request)
        return httpx.Response(200, text='data: {"type":"response.output_text.delta","delta":"Hello"}\n\ndata: {"type":"response.completed"}\n\n')
    deltas = []
    settings = {"endpoint": "https://api.openai.com/v1", "protocol": "Responses", "model": "unit-model"}
    assert stream_chat(settings, "unit-test-key", [{"role": "user", "content": "hello"}], Runner(), deltas.append, httpx.MockTransport(handle)) == "Hello"
    assert deltas == ["Hello"] and len(seen) == 1


@pytest.mark.parametrize("ending", ["", 'data: {"type":"response.failed"}\n\n', 'data: {"type":"response.incomplete"}\n\n'])
def test_incomplete_response_rejected(ending):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text='data: {"type":"response.output_text.delta","delta":"partial"}\n\n' + ending))
    with pytest.raises(RuntimeError):
        stream_chat({"endpoint": "http://127.0.0.1:9999/v1", "protocol": "Responses", "model": "test"}, "", [], Runner(), lambda _: None, transport)


def test_compatible_model_protocol_and_status_error_redaction():
    settings = {"endpoint": "http://localhost:9999/v1", "protocol": "Chat Completions", "model": "local"}
    data = 'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":null}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    assert stream_chat(settings, "", [], Runner(), lambda _: None, httpx.MockTransport(lambda request: httpx.Response(200, text=data))) == "OK"
    with pytest.raises(RuntimeError) as error:
        stream_chat(settings, "", [], Runner(), lambda _: None, httpx.MockTransport(lambda request: httpx.Response(401, text="secret-reflected-value")))
    assert "secret-reflected-value" not in str(error.value)
    for value in ["http://public.example/v1", "https://key@host/v1", "https://host/v1?key=oops"]:
        with pytest.raises(ValueError):
            validate_url(value)


def test_runner_timeout_and_cancel():
    with pytest.raises(TimeoutError):
        Runner().run([sys.executable, "-c", "import time;time.sleep(30)"], timeout=.25)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(Cancelled):
        Runner(cancelled=cancelled).run([sys.executable, "-c", "print('must not run')"])


def test_package_hashes_and_identity_reuse(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows development signer")
    root = create_project(tmp_path / "project", "Package test", "com.example.packtest")
    (root / "stage/bundle").mkdir(parents=True)
    (root / "stage/bundle/index.bundle").write_bytes(b"// system module 34588b5946dc99c968dd\n")
    dest = pack(root, lambda _: None, tmp_path / "signing")
    result = inspect_package(dest)
    assert result["digestVerified"] and result["deviceInstallVerified"] is False
    assert "assets/asset-index.bin" in result["files"]
    assert not any("private" in f or f.endswith(".dpapi") for f in result["files"])
    k1, c1 = identity("com.example.packtest", tmp_path / "signing")
    k2, c2 = identity("com.example.packtest", tmp_path / "signing")
    assert c1.public_bytes(serialization.Encoding.DER) == c2.public_bytes(serialization.Encoding.DER)
    assert k1.private_numbers() == k2.private_numbers()
    # Rebuild archive with one changed payload byte: inspector must reject it.
    with open(dest, "rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream, tarfile.open(fileobj=stream, mode="r|") as tf:
        files = [(e.name, tf.extractfile(e).read()) for e in tf]
    tampered = tmp_path / "tampered.vpkg"
    with tampered.open("wb") as raw, zstandard.ZstdCompressor().stream_writer(raw) as out, tarfile.open(fileobj=out, mode="w|") as tf:
        for name, data in files:
            data = data + b"tampered" if name == "bundle/index.bundle" else data
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            tf.addfile(entry, io.BytesIO(data))
    with pytest.raises(ValueError, match="mismatch"):
        inspect_package(tampered)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/absolute", "safe\\escape"])
def test_package_inspector_never_extracts_unsafe_paths(tmp_path, name):
    path = tmp_path / "bad.vpkg"
    with path.open("wb") as raw, zstandard.ZstdCompressor().stream_writer(raw) as out, tarfile.open(fileobj=out, mode="w|") as tf:
        entry = tarfile.TarInfo(name)
        entry.size = 1
        tf.addfile(entry, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="Unsafe"):
        inspect_package(path)


def test_remote_host_command_is_quoted_and_strict(tmp_path, monkeypatch):
    import vegabridge.devices as devices
    monkeypatch.setattr(devices, "tool_path", lambda configured, name: name)
    class Capture:
        def run(self, args, **kwargs):
            self.args = args
            return ""
    runner = Capture()
    emulator = RemoteEmulator({"ssh_host": "dev@ubuntu", "ssh_port": 22, "ssh_key": "", "vega_cli": "/home/dev/vega/bin/vega", "emulator_serial": "emulator-5554"}, runner)
    emulator.shell("uname -a")
    assert "StrictHostKeyChecking=yes" in runner.args
    assert runner.args[-1].endswith("shell 'uname -a'")
