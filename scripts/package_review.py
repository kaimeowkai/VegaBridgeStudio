"""Create allowlisted review artifacts; never crawl arbitrary workspaces."""
import hashlib
import importlib.metadata as md
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist"
APP = DIST / "VegaBridgeStudio"
VERSION = "0.4.0"


def notices():
    folder = APP / "licenses"
    folder.mkdir(exist_ok=True)
    names = ["PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "cryptography", "cffi", "pycparser", "zstandard", "flatbuffers", "httpx", "httpcore", "anyio", "h11", "idna", "certifi", "typing_extensions", "pyinstaller", "windows-capture", "numpy", "opencv-python", "PyJWT", "websocket-client"]
    manifest = []
    for name in names:
        dist = md.distribution(name)
        dest = folder / name
        dest.mkdir(exist_ok=True)
        files = []
        for file in dist.files or []:
            parts = Path(str(file)).parts
            if any("license" in part.lower() or "copying" in part.lower() or "notice" in part.lower() for part in parts):
                path = Path(dist.locate_file(file))
                if path.is_file():
                    safe = "__".join(parts).replace(":", "_")
                    shutil.copy2(path, dest / safe)
                    files.append(safe)
        manifest.append({"name": name, "version": dist.version, "licenseFiles": files, "projectUrls": dist.metadata.get_all("Project-URL", []), "homePage": dist.metadata.get("Home-page", "")})
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, folder / "Python-LICENSE.txt")
    (folder / "inventory.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for name in ["README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "SECURITY.md", "CHANGELOG.md"]:
        shutil.copy2(ROOT / name, APP / name)
    shutil.copytree(ROOT / "docs", APP / "docs", dirs_exist_ok=True)


def source_files():
    files = []
    for name in ["README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "pyproject.toml", "requirements-build.lock", "run_studio.py", "run_cli.py", "VegaBridgeStudio.spec", "version-info.txt", ".gitignore"]:
        files.append(ROOT / name)
    for name in ["vegabridge", "scripts", "tests", ".github", "docs", "examples"]:
        for file in (ROOT / name).rglob("*"):
            denied_dirs={'__pycache__','node_modules','.git','.venv','.vegabridge','stage','build','private','secrets','conversations','captures'}
            denied_names={'settings.json','chatgpt-host.json','chatgpt-accounts.json','auth.json','credentials.json'}
            if (file.is_file() and not denied_dirs.intersection(file.relative_to(ROOT).parts)
                    and file.name not in denied_names and not file.name.startswith(('.env','qa-'))
                    and file.suffix not in {".pyc", ".dpapi", ".pem", ".key", ".vpkg", ".pfx", ".p12", ".log"}):
                files.append(file)
    return sorted(files)


def make_zip(path, files, base):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as out:
        for file in files:
            out.write(file, file.relative_to(base).as_posix())


def main():
    notices()
    portable = DIST / f"VegaBridgeStudio-{VERSION}-windows-x64.zip"
    source = DIST / f"VegaBridgeStudio-{VERSION}-source.zip"
    make_zip(portable, sorted(file for file in APP.rglob("*") if file.is_file()), DIST)
    sources = source_files()
    make_zip(source, sources, ROOT)
    receipts = []
    for file in [portable, source, APP / "VegaBridgeStudio.exe", APP / "VegaBridgeCLI.exe"]:
        receipts.append({"file": file.relative_to(DIST).as_posix(), "bytes": file.stat().st_size, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
    (DIST / "SHA256SUMS.txt").write_text("".join(item["sha256"] + "  " + item["file"] + "\n" for item in receipts), encoding="utf-8")
    (DIST / "Build-Receipt.json").write_text(json.dumps({"version": VERSION, "platform": "Windows x64", "publiclyPublished": False, "authenticodeSigned": False, "sourceFiles": len(sources), "artifacts": receipts}, indent=2), encoding="utf-8")
    print(json.dumps(receipts, indent=2))


if __name__ == "__main__":
    main()
