"""Per-user preferences and Windows CurrentUser DPAPI secrets."""
import ctypes
import json
import os
import tempfile
from ctypes import wintypes
from pathlib import Path


def user_dir():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    path = base / "VegaBridgeStudio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def dpapi(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("This review build stores secrets with Windows DPAPI and requires Windows.")
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    protect = crypt.CryptProtectData
    protect.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.POINTER(Blob), ctypes.c_void_p,
                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    unprotect = crypt.CryptUnprotectData
    unprotect.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p,
                          ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    protect.restype = unprotect.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    out = Blob()
    fn = unprotect if decrypt else protect
    # CRYPTPROTECT_UI_FORBIDDEN; never show an OS credential prompt from a worker.
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


class SecretStore:
    def __init__(self, root=None):
        self.root = Path(root) if root else user_dir() / "secrets"

    def path(self, name):
        if not name.replace("-", "").isalnum():
            raise ValueError("Invalid secret name")
        return self.root / (name + ".dpapi")

    def get(self, name):
        path = self.path(name)
        return dpapi(path.read_bytes(), True).decode() if path.exists() else ""

    def set(self, name, value):
        atomic_write(self.path(name), dpapi(value.encode()))

    def remove(self, name):
        self.path(name).unlink(missing_ok=True)


DEFAULTS = {"adb": "", "node": "", "bridge_port": 5048, "endpoint": "https://api.openai.com/v1",
            "model": "gpt-6.1-sol", "protocol": "Responses", "ssh_host": "", "ssh_port": 22,
            "ssh_key": "", "vega_cli": "vega", "emulator_serial": "emulator-5554",
            "qemu": "", "vega_images": "", "vm_folder": "", "vm_port": 5573,
            "vm_accel": "whpx", "theme": "Harbor Dark", "auth_mode": "API key / local model", "auth_account": "",
            "hermes": "", "clang": "", "sysroot": "", "sdk_root": "", "openssl": "", "codegen":"",
            "chat_active":"planning", "agent_mode":"Workspace agent", "projects_folder":str(Path.home()/'VegaProjects')}


def load_settings():
    path = user_dir() / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DEFAULTS | {k: v for k, v in data.items() if k in DEFAULTS}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(data):
    atomic_write(user_dir() / "settings.json", json.dumps({k: data[k] for k in DEFAULTS}, indent=2).encode())
