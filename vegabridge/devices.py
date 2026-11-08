"""Local USB/TCP ADB bridge and official VVD on a separate Ubuntu/macOS SSH host."""
import re
import shlex
import uuid
from pathlib import Path
from .project import tool_path, package_id


class DeviceCommandError(RuntimeError):
    def __init__(self, code, output):
        super().__init__("Device command exited with status " + str(code) + ". See output above.")
        self.output = output


def endpoint(text):
    value = text.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*(?::[0-9]{1,5})?", value):
        raise ValueError("Enter a hostname or IPv4 address, optionally followed by :port.")
    host, sep, port = value.partition(":")
    if sep and not 1 <= int(port) <= 65535:
        raise ValueError("Port must be 1–65535")
    return value if sep else value + ":5555"


def parse_devices(text):
    found = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] in {"device", "offline", "unauthorized"}:
            serial = parts[0]
            kind = "Emulator" if serial.startswith("emulator-") else "Wireless" if ":" in serial else "USB"
            found.append({"serial": serial, "state": parts[1], "kind": kind})
    return found


class LocalBridge:
    def __init__(self, settings, runner, serial=""):
        self.runner, self.serial = runner, serial
        self.adb = tool_path(settings["adb"], "adb.exe")
        self.port = int(settings["bridge_port"])
        if not 1024 <= self.port <= 65535:
            raise ValueError("Choose an unprivileged bridge port (1024–65535)")

    def call(self, args, selected=True, **kwargs):
        prefix = [self.adb, "-P", str(self.port)]
        if selected:
            if not self.serial or self.serial.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_.:-]+", self.serial):
                raise ValueError("Select an authorized online target device.")
            prefix += ["-s", self.serial]
        return self.runner.run(prefix + list(args), **kwargs)

    def devices(self):
        return parse_devices(self.call(["devices", "-l"], selected=False))

    def connect(self, address):
        text = self.call(["connect", endpoint(address)], selected=False, timeout=30)
        if "connected to" not in text.lower():
            raise RuntimeError("Device connection was not confirmed. Check Developer Mode, connection mode, network and IP.")
        return text

    def shell(self, command, **kwargs):
        # SDK virtual images use legacy shell service naming. An explicit status
        # marker restores remote exit-code checking when shell v2 is disabled.
        marker = "__VEGABRIDGE_RC_" + uuid.uuid4().hex + "__"
        wrapped = "( " + command + "\n); vb_rc=$?; printf '\\n" + marker + "%s\\n' \"$vb_rc\""
        self.runner.emit("› Device: " + command)
        kwargs.setdefault("quiet", True)
        text = self.call(["shell", "-x", wrapped], **kwargs)
        match = re.search(r"\r?\n" + re.escape(marker) + r"([0-9]+)\r?\n?\s*$", text)
        if not match:
            raise RuntimeError("Device shell ended without a remote exit status. Its result is unknown.")
        if int(match[1]):
            raise DeviceCommandError(match[1], text[:match.start()])
        return text[:match.start()]

    def push(self, local, remote):
        return self.call(["push", str(local), remote], timeout=180)

    def pull(self, remote, local):
        return self.call(["pull", remote, str(local)], timeout=180)

    def install(self, path):
        remote = "/tmp/vegabridge-" + uuid.uuid4().hex + ".vpkg"
        self.push(path, remote)
        result = self.shell("vpm install " + shlex.quote(remote), timeout=180)
        if "success" not in result.lower() or re.search(r"\b(fail(?:ed|ure)?|error)\b", result, re.I):
            raise RuntimeError("Vega installer did not confirm success")
        self.runner.emit("INSTALL VERIFIED by Vega package manager.")
        return result

    def launch(self, component):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", component):
            raise ValueError("Invalid component ID")
        self.shell("vmsgr send " + shlex.quote("pkg://" + component))
        self.runner.emit("Launch requested. Inspect lifecycle and screen to verify the app is running.")

    def stop(self, identifier):
        return self.shell("vlcm terminate-app --pkg-id " + shlex.quote(package_id(identifier)) + " --force")

    def screenshot(self, destination):
        for attempt in range(3):
            remote = "/tmp/vegabridge-" + uuid.uuid4().hex + ".png"
            try:
                self.shell("gwsi-tool-screenshooter " + remote, timeout=60)
                self.pull(remote, destination)
                if not Path(destination).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                    raise RuntimeError("Screenshot transfer was not a complete PNG")
                return str(destination)
            except DeviceCommandError as error:
                if attempt == 2 or "atomic commit failed" not in error.output.lower():
                    raise
                self.runner.emit("Display is changing; retrying screenshot…")
                self.runner.cancelled.wait(.5)
                self.runner.check()
            finally:
                try:
                    self.shell("rm -f " + remote, timeout=5)
                except Exception:
                    pass


class RemoteEmulator(LocalBridge):
    """Uses the actual Amazon SDK installed by the owner on a supported host.

    No image, Amazon SDK, SSH identity, host authentication bypass, or VM is bundled.
    A real virtual device is controlled using VDA on that host, not simulated UI.
    """
    def __init__(self, settings, runner, serial=None):
        self.settings, self.runner = settings, runner
        self.serial = serial or settings["emulator_serial"]
        self.host = settings["ssh_host"].strip()
        if not re.fullmatch(r"(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9][A-Za-z0-9.-]*", self.host):
            raise ValueError("Configure an SSH host (user@hostname) in Emulator settings.")
        self.cli = settings["vega_cli"]
        if not self.cli or "\n" in self.cli:
            raise ValueError("Configure the absolute Vega CLI path on the supported host.")
        self.ssh = tool_path("", "ssh.exe")
        self.scp = tool_path("", "scp.exe")

    def ssh_args(self):
        args = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10", "-p", str(int(self.settings["ssh_port"]))]
        key = self.settings["ssh_key"]
        if key:
            if not Path(key).is_file():
                raise ValueError("SSH key file does not exist")
            args += ["-i", key]
        return args

    def host_command(self, args, **kwargs):
        return self.runner.run([self.ssh] + self.ssh_args() + [self.host, shlex.join([str(a) for a in args])], **kwargs)

    def manage(self, action):
        if action not in {"start", "status", "stop"}:
            raise ValueError("Invalid emulator action")
        return self.host_command([self.cli, "virtual-device", action], timeout=180)

    def shell(self, command, **kwargs):
        return self.call(["shell", command], **kwargs)

    def call(self, args, selected=True, **kwargs):
        prefix = [self.cli, "exec", "vda"]
        if selected:
            if not re.fullmatch(r"emulator-[0-9]+", self.serial):
                raise ValueError("Select an emulator-PORT target returned by the supported host.")
            prefix += ["-s", self.serial]
        return self.host_command(prefix + list(args), **kwargs)

    def _copy(self, source, destination):
        args = self.ssh_args()
        args[args.index("-p")] = "-P"
        return self.runner.run([self.scp] + args + [source, destination], timeout=180)

    def push(self, local, remote):
        hostfile = "/tmp/vegabridge-" + uuid.uuid4().hex + Path(local).suffix
        self._copy(str(local), self.host + ":" + hostfile)
        try:
            return self.call(["push", hostfile, remote], timeout=180)
        finally:
            self.host_command(["rm", "-f", "--", hostfile])

    def pull(self, remote, local):
        hostfile = "/tmp/vegabridge-" + uuid.uuid4().hex + Path(local).suffix
        self.call(["pull", remote, hostfile], timeout=180)
        try:
            return self._copy(self.host + ":" + hostfile, str(local))
        finally:
            self.host_command(["rm", "-f", "--", hostfile])
