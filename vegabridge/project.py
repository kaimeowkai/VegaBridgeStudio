import json
import os
import re
import shutil
import tomllib
from pathlib import Path
from .storage import atomic_write

RESOURCES = Path(__file__).parent / "resources"
SKIP = {"node_modules", ".git", ".vegabridge", "build", "stage", ".venv", "__pycache__", "private"}
TEXT_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".md", ".txt", ".css", ".html", ".xml", ".yml", ".yaml", ".c", ".cpp", ".h", ".py"}


def package_id(value):
    if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}", value):
        raise ValueError("Use a package ID such as com.example.myapp (lowercase letters, digits, underscores).")
    return value


def inside(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("Path must be a file inside the project.")
    return path


def create_project(folder, title, identifier):
    package_id(identifier)
    dest = Path(folder).resolve()
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("Choose an empty folder. Existing projects are never overwritten.")
    if not title.strip() or len(title) > 100:
        raise ValueError("Enter an app title of 1–100 characters.")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(RESOURCES / "template", dest, dirs_exist_ok=True)
    old = "com.brutalgamestudios.windowsnativehello"
    for name in ["index.js", "app.json", "manifest.toml"]:
        path = dest / name
        text = path.read_text(encoding="utf-8").replace(old, identifier)
        if name == "app.json":
            data = json.loads(text)
            data["displayName"] = title.strip()
            text = json.dumps(data, indent=2)
        if name == "manifest.toml":
            text = re.sub(r'^title = .*$', "title = " + json.dumps(title.strip()), text, flags=re.M)
            text = re.sub(r'^build-number = .*$', "build-number = 1", text, flags=re.M)
        atomic_write(path, text.encode())
    (dest / ".gitignore").write_text("node_modules/\nstage/\nbuild/\n.vegabridge/\n.env*\n*.key\n*.dpapi\n", encoding="utf-8")
    (dest / "vegabridge.json").write_text(json.dumps({"schemaVersion": 1, "template": "kepler4-js", "target": "armv7"}, indent=2), encoding="utf-8")
    return dest


def metadata(root):
    doc = tomllib.loads((Path(root) / "manifest.toml").read_text(encoding="utf-8"))
    pkg = doc["package"]
    package_id(pkg["id"])
    component = doc["components"]["interactive"][0]["id"]
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", component):
        raise ValueError("Invalid launch component ID")
    return pkg | {"component": component}


def safe_context(root, path, text):
    path = inside(root, path)
    if any(part in SKIP for part in path.relative_to(root).parts) or path.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError("Select a source/text file; private and generated folders cannot be attached.")
    if path.name.startswith(".env") or any(x in path.name.lower() for x in ("secret", "credential", "token", "privatekey")):
        raise ValueError("Credential files cannot be attached to chat.")
    if len(text.encode("utf-8")) > 120_000:
        raise ValueError("Select a smaller excerpt (maximum 120 KB).")
    if re.search(r"-----BEGIN .*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{16,}|(?i:api[_-]?key|password|access[_-]?token)\s*[:=]\s*[\"'][^\"']{8,}", text):
        raise ValueError("Possible credential found. Remove it before sharing this context.")
    return f"File: {path.relative_to(root).as_posix()}\n```\n{text}\n```"


def tool_path(configured, name):
    found = configured or shutil.which(name)
    if not found or not Path(found).is_file():
        raise ValueError(f"Configure the path to {name} in Settings.")
    return str(Path(found).resolve())


def build(root, settings, runner):
    from .package import pack
    root = Path(root).resolve()
    cfg = json.loads((root / "vegabridge.json").read_text(encoding="utf-8"))
    if cfg.get("template") != "kepler4-js":
        raise ValueError("Native Windows build supports the kepler4-js template only. Use Amazon's SDK for custom native modules.")
    metadata(root)
    node = Path(tool_path(settings["node"], "node.exe"))
    npm = node.parent / "node_modules/npm/bin/npm-cli.js"
    if not npm.is_file():
        raise ValueError("Choose node.exe from a complete official Node.js installation with npm.")
    env = dict(os.environ)
    env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "")
    env["CI"] = "1"
    # Existing user projects may contain npm scripts. Explicit build is the execution boundary.
    runner.run([node, npm, "ci", "--no-audit", "--no-fund"], cwd=root, env=env, timeout=900)
    runner.run([node, RESOURCES / "patch-node-paths.cjs", root], cwd=root, env=env)
    stage = root / "stage"
    if stage.exists():
        resolved = inside(root, stage)
        if resolved != root / "stage" or stage.is_symlink() or stage.is_junction():
            raise ValueError("Refusing to clean a linked staging directory.")
        shutil.rmtree(resolved)
    (stage / "bundle").mkdir(parents=True)
    runner.run([node, npm, "run", "bundle"], cwd=root, env=env, timeout=900)
    runner.check()
    return pack(root, runner.emit)
