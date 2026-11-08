"""Local USB/TCP ADB bridge and official VVD on a separate Ubuntu/macOS SSH host."""
import re
import shlex
import uuid
import time
from pathlib import Path
from .project import tool_path, package_id


class DeviceCommandError(RuntimeError):
    def __init__(self, code, output):
        super().__init__("Device command exited with status " + str(code) + ". See output above.")
        self.output = output
        self.code = int(code)


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

    def connect(self, address, timeout=30):
        text = self.call(["connect", endpoint(address)], selected=False, timeout=timeout)
        if "connected to" not in text.lower():
            raise RuntimeError("Device connection was not confirmed. Check Developer Mode, connection mode, network and IP.")
        return text

    def reconnect(self):
        """Reconnect exactly this network target, never reset the shared ADB server."""
        address = endpoint(self.serial)
        if ':' not in self.serial:
            raise ValueError('USB targets must be reconnected with their data cable; no connection mode is changed.')
        self.call(['disconnect',address],selected=False,timeout=10)
        self.connect(address,timeout=15)
        found = self.devices()
        if not any(row['serial']==address and row['state']=='device' for row in found):
            raise RuntimeError('This target is still offline or unauthorized. Check Developer Mode and approve debugging on the device.')
        return found

    def diagnostics(self):
        found = self.devices()
        state = next((row['state'] for row in found if row['serial']==self.serial),'not found')
        report = {'serial':self.serial,'state':state,'bridgePort':self.port,'changedSettings':False}
        if state == 'device':
            report['system'] = self.shell('uname -sm; id -u; df -k /data; printf "\\nVega package service: "; command -v vpm',timeout=12).strip()
        return report

    def wait_until_ready(self, address, timeout=180):
        address = endpoint(address)
        deadline = time.monotonic()+timeout
        self.runner.emit('Waiting for the managed VM bridge and Vega package service…')
        last = 'Device has not connected yet'
        while time.monotonic()<deadline:
            self.runner.check()
            try:
                self.connect(address,timeout=min(8,max(1,deadline-time.monotonic())))
                rows = self.devices()
                if any(row['serial']==address and row['state']=='unauthorized' for row in rows):
                    raise PermissionError('VM debugging needs authorization on its screen.')
                if any(row['serial']==address and row['state']=='device' for row in rows):
                    selected = LocalBridge({'adb':self.adb,'bridge_port':self.port},self.runner,address)
                    selected.shell('vpm list packages >/dev/null',timeout=8)
                    self.runner.emit('VM READY: authorized device bridge and Vega package service responded.')
                    return rows
            except PermissionError:
                raise
            except (RuntimeError,OSError,TimeoutError) as error:
                self.runner.check()
                last = str(error)
            self.runner.cancelled.wait(min(2,max(0,deadline-time.monotonic())))
        raise TimeoutError('VM did not become ready within the connection window. Its data is preserved; retry Connect when boot completes. Last check: '+last)

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

    def component_shell(self,component,command,**kwargs):
        if not re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-zA-Z0-9_]+){2,}',component) or component.startswith('com.amazon.'):
            raise ValueError('Choose your own installed developer component, not an Amazon system component')
        marker='__VEGABRIDGE_RC_'+uuid.uuid4().hex+'__'
        if '\n' in command or '\r' in command:raise ValueError('Component commands must fit on one shell line')
        wrapped='( '+command+' ); vb_rc=$?; printf "\\n'+marker+'%s\\n" "$vb_rc"'
        text=self.call(['shell','-x','component-id',component,wrapped],quiet=True,**kwargs)
        match=re.search(r'\r*\n'+re.escape(marker)+r'([0-9]+)\r*\n?\s*$',text)
        if not match:raise RuntimeError('Component shell returned no exit status; result is unknown')
        if int(match[1]):raise DeviceCommandError(match[1],text[:match.start()])
        return text[:match.start()]

    def pull(self, remote, local):
        return self.call(["pull", remote, str(local)], timeout=180)

    def install(self, path):
        remote = "/tmp/vegabridge-" + uuid.uuid4().hex + ".vpkg"
        try:
            self.push(path, remote)
            result = self.shell("vpm install " + shlex.quote(remote), timeout=180)
            if "success" not in result.lower() or re.search(r"\b(fail(?:ed|ure)?|error)\b", result, re.I):
                raise RuntimeError("Vega installer did not confirm success")
            self.runner.emit("INSTALL VERIFIED by Vega package manager.")
            return result
        finally:
            # Only this operation's UUID upload; never remove installed data.
            try:
                self.shell('rm -f '+shlex.quote(remote),timeout=5)
            except Exception:
                self.runner.emit('Temporary package cleanup could not be confirmed: '+remote)

    def launch(self, component):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", component):
            raise ValueError("Invalid component ID")
        self.shell("vmsgr send " + shlex.quote("pkg://" + component))
        self.runner.emit("Launch requested. Inspect lifecycle and screen to verify the app is running.")

    def wait_for_app(self, component, timeout=20):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", component):
            raise ValueError('Invalid component ID')
        end=time.monotonic()+timeout
        last=''
        while time.monotonic()<end:
            self.runner.check()
            last=self.shell('vlcm list --app-id '+shlex.quote(component),timeout=8)
            for line in last.splitlines():
                parts=line.split()
                if parts and parts[0]==component and 'VISIBLE' in parts:
                    self.runner.emit('RUNNING VERIFIED: '+component+' is VISIBLE in Vega lifecycle.')
                    return {'component':component,'state':'VISIBLE','lifecycle':line.strip()}
            self.runner.cancelled.wait(.5)
        raise TimeoutError('The package installed, but Vega did not report the app VISIBLE. Check Device Lab, the active Fire TV profile/display and device logs. Launch requests alone are not runtime verification.')

    def stop(self, identifier):
        return self.shell("vlcm terminate-app --pkg-id " + shlex.quote(package_id(identifier)) + " --force")

    def type_text(self, text):
        if not text or len(text)>1024 or '\x00' in text:
            raise ValueError('Enter 1–1024 characters without NUL bytes')
        import copy
        from .process import Runner
        private=copy.copy(self)
        private.runner=Runner(cancelled=self.runner.cancelled)
        private.shell('inputd-cli send_text '+shlex.quote(text),timeout=180)
        return 'Text sent to the selected device. Content was omitted from task logs.'

    def keep_awake(self, minutes=30):
        if not 1<=minutes<=120:
            raise ValueError('Choose a test session of 1–120 minutes')
        self.runner.emit('Developer test wake signals active. This is input injection, not a production app wake-lock API. Stop the session or close Studio to end it.')
        deadline=time.monotonic()+minutes*60
        count=0
        while time.monotonic()<deadline:
            self.runner.check()
            self.shell('inputd-cli button_press KEY_WAKEUP',timeout=10)
            count+=1
            self.runner.cancelled.wait(min(45,max(0,deadline-time.monotonic())))
        return {'wakeSignals':count,'sessionMinutes':minutes,'changedDeviceSettings':False}

    def screenshot(self, destination):
        for attempt in range(3):
            remote = "/tmp/vegabridge-" + uuid.uuid4().hex + ".png"
            try:
                # Bound execution on the target too, so cancelling the Windows
                # client cannot strand an indefinitely waiting capture process.
                self.shell("timeout -k 2 15 gwsi-tool-screenshooter " + remote, timeout=25)
                self.pull(remote, destination)
                if not Path(destination).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                    raise RuntimeError("Screenshot transfer was not a complete PNG")
                return str(destination)
            except DeviceCommandError as error:
                if error.code in {124, 137}:
                    raise TimeoutError("The device did not produce a display capture within 15 seconds. Wake the Fire TV and check its active display/input, then try again.") from None
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
