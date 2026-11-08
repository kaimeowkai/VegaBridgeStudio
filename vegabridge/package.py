"""Experimental JS-only VPKG packaging, proven on Vega OS 2.0 ARMv7.

Development signing is not Amazon Appstore approval or production signing.
"""
import datetime as dt
import hashlib
import io
import json
import tarfile
import tempfile
import tomllib
from pathlib import Path, PurePosixPath
import flatbuffers
import zstandard
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID
from .storage import atomic_write, dpapi, user_dir
from .project import metadata, tool_path


def asset_index(names):
    builder = flatbuffers.Builder(256)
    entries = []
    for name in sorted(names):
        if not name.startswith("assets/") or name.count("/") < 2:
            continue
        rel = name[len("assets/"):]
        cat = builder.CreateString(rel.split("/")[0])
        path = builder.CreateString(rel)
        builder.StartObject(3)
        builder.PrependUOffsetTRelativeSlot(0, cat, 0)
        builder.PrependUOffsetTRelativeSlot(2, path, 0)
        entries.append(builder.EndObject())
    builder.StartVector(4, len(entries), 4)
    for entry in reversed(entries):
        builder.PrependUOffsetTRelative(entry)
    vector = builder.EndVector()
    builder.StartObject(1)
    builder.PrependUOffsetTRelativeSlot(0, vector, 0)
    root = builder.EndObject()
    builder.Finish(root)
    return bytes(builder.Output())


def identity(identifier, base=None):
    folder = (Path(base) if base else user_dir() / "signing") / identifier
    keyfile, certfile = folder / "development.dpapi", folder / "certificate.pem"
    if keyfile.exists() or certfile.exists():
        if not (keyfile.exists() and certfile.exists()):
            raise RuntimeError("Incomplete signing identity. Restore its matching key/certificate; do not silently replace it.")
        key = serialization.load_pem_private_key(dpapi(keyfile.read_bytes(), True), password=None)
        cert = x509.load_pem_x509_certificate(certfile.read_bytes())
        if key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo):
            raise RuntimeError("Signing key and certificate do not match")
    else:
        key = ec.generate_private_key(ec.SECP384R1())
        now = dt.datetime.now(dt.timezone.utc)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "VegaBridge Development " + identifier)])
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
                .not_valid_after(now + dt.timedelta(days=3650)).sign(key, hashes.SHA384()))
        atomic_write(keyfile, dpapi(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())))
        atomic_write(certfile, cert.public_bytes(serialization.Encoding.PEM))
    return key, cert


def add_folder(files, folder, prefix):
    folder = Path(folder)
    if not folder.is_dir():
        return
    root = folder.resolve()
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root):
            raise ValueError("Linked asset/bundle files are not packaged.")
        if path.is_file():
            rel = path.relative_to(folder)
            if any(p.startswith(".") or p.lower() in {"private", "secrets", "credentials", "node_modules"} for p in rel.parts) or path.suffix.lower() in {".pem", ".key", ".dpapi", ".pfx", ".p12"}:
                raise ValueError(f"Private/generated asset path refused: {rel}")
            if path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("Individual asset exceeds 64 MiB in this preview packer")
            files[prefix + rel.as_posix()] = path.read_bytes()


def write_package(files, key, cert, destination):
    entries = {name: {"digest": hashlib.sha384(data).hexdigest(), "stub": name in {"manifest.toml", "meta-info/build-info.json"}} for name, data in files.items()}
    digest = json.dumps({"version": 1, "data": {"algorithm": "sha384", "entries": entries}}, separators=(",", ":")).encode()
    legacy = "".join("sha384: " + entry["digest"] + "\n" for entry in entries.values()).encode()
    for name, data in [("digest.json", digest), ("digest", legacy)]:
        files["meta-info/signature/" + name] = data
        files["meta-info/signature/" + name + ".sig"] = pkcs7.PKCS7SignatureBuilder().set_data(data).add_signer(cert, key, hashes.SHA384()).sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary])
    destination = Path(destination)
    temp = destination.with_suffix(".vpkg.part")
    try:
        with temp.open("wb") as raw, zstandard.ZstdCompressor(level=9).stream_writer(raw) as compressed, tarfile.open(fileobj=compressed, mode="w|", format=tarfile.USTAR_FORMAT) as archive:
            for name, data in files.items():
                header = tarfile.TarInfo(name)
                header.size, header.mode, header.mtime = len(data), 0o100644, 0
                archive.addfile(header, io.BytesIO(data))
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)


def pack(root, emit=print, identity_base=None):
    root = Path(root)
    pkg = metadata(root)
    files = {"manifest.toml": (root / "manifest.toml").read_bytes()}
    add_folder(files, root / "stage/bundle", "bundle/")
    add_folder(files, root / "assets", "assets/")
    if "bundle/index.bundle" not in files or b"34588b5946dc99c968dd" not in files["bundle/index.bundle"]:
        raise ValueError("Kepler 4 system module ID is missing. Verify the Windows Metro path patch before packaging.")
    files["bundle/assets/app.json"] = (root / "app.json").read_bytes()
    config = {"schemaVersion": 1, "mainBundle": "index.bundle", "developmentEnabled": False, "linkLaunch": [], "linkDynamic": [], "appLibraries": [], "runtimeFeatures": {}, "systemBundles": {"common": ["index.amzn__react-native-kepler-4.hermes.bundle"]}}
    files["assets/raw/keplerscript-app-config.json"] = json.dumps(config, separators=(",", ":")).encode()
    files["assets/kepler-sdk-version"] = b"2.0.13986"
    files["assets/asset-index.bin"] = asset_index(files)
    files["meta-info/build-info.json"] = json.dumps({"data": {"build-number": pkg["build-number"], "version": pkg["version"], "size": sum(map(len, files.values()))}, "os_version_registry": {"contract_package_version": "1.0.4482.0", "os_versions": ["1.2", "2.0"]}, "version": 1}, separators=(",", ":")).encode()
    key, cert = identity(pkg["id"], identity_base)
    out = root / "build"
    out.mkdir(exist_ok=True)
    destination = out / (pkg["id"] + "-armv7.vpkg")
    write_package(files, key, cert, destination)
    result = inspect_package(destination)
    receipt = {"createdUtc": dt.datetime.now(dt.timezone.utc).isoformat(), "packageId": pkg["id"], "component": pkg["component"], "version": pkg["version"], "buildNumber": pkg["build-number"], "certificateSha256": cert.fingerprint(hashes.SHA256()).hex(), "vpkgSha256": result["sha256"], "experimentalJsOnly": True, "deviceInstallVerified": False, "physicalLaunchVerified": False, "customNativeModulesSupported": False}
    atomic_write(out / "Build-Receipt.json", json.dumps(receipt, indent=2).encode())
    emit("Package built and digest checked: " + str(destination))
    emit("Development signature; device testing and Appstore validation are separate steps.")
    return str(destination)


def package_files(path):
    files, total = {}, 0
    with open(path, "rb") as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream, tarfile.open(fileobj=stream, mode="r|") as archive:
        for entry in archive:
            name = entry.name
            pure = PurePosixPath(name)
            if not entry.isfile() or pure.is_absolute() or ".." in pure.parts or "\\" in name or ":" in name or name in files:
                raise ValueError("Unsafe or duplicate VPKG entry")
            total += entry.size
            if total > 128 * 1024 * 1024 or len(files) >= 10000:
                raise ValueError("Package exceeds preview inspector limit (128 MiB / 10000 files)")
            files[name] = archive.extractfile(entry).read()
    return files, total


def inspect_package(path):
    files, total = package_files(path)
    digest = json.loads(files["meta-info/signature/digest.json"])
    entries = digest["data"]["entries"]
    if digest["data"]["algorithm"] != "sha384":
        raise ValueError("Unsupported package digest algorithm")
    payload = {name for name in files if not name.startswith("meta-info/signature/")}
    if set(entries) != payload:
        raise ValueError("Digest inventory does not cover the exact package payload")
    for name, entry in entries.items():
        if hashlib.sha384(files[name]).hexdigest() != entry["digest"]:
            raise ValueError("Package digest mismatch: " + name)
    certs = pkcs7.load_der_pkcs7_certificates(files["meta-info/signature/digest.json.sig"])
    if not certs:
        raise ValueError("Package has no CMS signing certificate")
    return {"sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(), "files": sorted(files), "payloadBytes": total, "digestVerified": True, "cmsCertificateSha256": certs[0].fingerprint(hashes.SHA256()).hex(), "cmsCryptographicVerification": "Not performed by inspector; device installer verifies signature", "deviceInstallVerified": False}


def verify_package(path, settings, runner):
    """Verify CMS math and inventory; never imply Amazon signer trust/approval."""
    result = inspect_package(path)
    files, _ = package_files(path)
    openssl = tool_path(settings.get('openssl', ''), 'openssl.exe')
    with tempfile.TemporaryDirectory(prefix='vegabridge-cms-') as folder:
        folder = Path(folder)
        for name in ['digest.json', 'digest']:
            payload = folder / name
            signature = folder / (name + '.sig')
            payload.write_bytes(files['meta-info/signature/' + name])
            signature.write_bytes(files['meta-info/signature/' + name + '.sig'])
            runner.run([openssl, 'cms', '-verify', '-binary', '-inform', 'DER', '-noverify',
                        '-in', signature, '-content', payload, '-out', 'NUL'], timeout=20)
    manifest = tomllib.loads(files['manifest.toml'].decode('utf-8'))
    pkg = manifest['package']
    if not all(pkg.get(key) for key in ['id', 'title', 'version', 'build-number', 'icon']):
        raise ValueError('Manifest is missing required package metadata')
    interactive = manifest.get('components', {}).get('interactive', [])
    if not any('com.amazon.category.main' in item.get('categories', []) for item in interactive):
        raise ValueError('Manifest has no main-category interactive component')
    icon = pkg['icon']
    if icon.startswith('@') and 'assets/' + icon[1:] not in files:
        raise ValueError('Manifest icon is absent from the package')
    from .workspace_tools import elf_architecture
    native = []
    for name, data in files.items():
        if name.startswith(('lib/', 'bin/', 'shared/lib/')):
            with tempfile.NamedTemporaryFile(prefix='vegabridge-elf-', delete=False) as f:
                f.write(data)
                temp = Path(f.name)
            try:
                native.append({'file': name, 'architecture': elf_architecture(temp)})
            finally:
                temp.unlink(missing_ok=True)
    result.update(cmsCryptographicVerification='verified for both detached digest signatures', cmsSignatureVerified=True,
                  signerTrust='Not established by this check; Amazon and device policy decide trusted signing identities',
                  manifestChecked=True, nativeArchitectures=native, appstoreApproved=False)
    return result
