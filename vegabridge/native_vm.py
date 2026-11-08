"""Native Windows Vega VM launch: QEMU + owner-supplied images + private COW disk."""
import json
import socket
import uuid
from pathlib import Path
from .emulator_disk import CompositeDisk, ReadOnlyNbd
from .project import tool_path
from .storage import user_dir, atomic_write


def qmp_command(port, command, arguments=None):
    with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
        sock.settimeout(3)
        stream = sock.makefile("rwb", buffering=0)
        hello = json.loads(stream.readline())
        if "QMP" not in hello:
            raise RuntimeError("VM monitor handshake failed")
        for method in ["qmp_capabilities", command]:
            message = {"execute": method}
            if method == command and arguments:
                message["arguments"] = arguments
            stream.write(json.dumps(message).encode() + b"\n")
            while True:
                reply = json.loads(stream.readline())
                if "return" in reply:
                    break
                if "error" in reply:
                    raise RuntimeError("VM monitor rejected " + method + ": " + str(reply["error"].get("desc", "Unknown error")))
        return reply["return"]


def qmp_quit(port):
    return qmp_command(port, "quit")


class NativeVm:
    def __init__(self, settings):
        self.settings = dict(settings)
        self.monitor_port = None
        self.pid = None
        self.display_name = "VegaBridge " + uuid.uuid4().hex[:8] + " — Vega OS"
        self.window_title = "QEMU (" + self.display_name + ")"

    def screenshot(self, destination):
        if not self.monitor_port:
            raise RuntimeError("The VM display is not ready yet.")
        destination = Path(destination).resolve()
        try:
            qmp_command(self.monitor_port, "screendump", {"filename": str(destination), "format": "png"})
        except RuntimeError as error:
            if "no surface" not in str(error):
                raise
            from .window_capture import capture_vm_window
            capture_vm_window(self.pid, self.window_title, destination)
        except OSError as error:
            raise RuntimeError("The VM display is not ready. Wait for boot, then capture again.") from error
        if not destination.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("VM display capture did not produce a complete PNG")
        return str(destination)

    def run(self, runner):
        qemu = Path(tool_path(self.settings["qemu"], "qemu-system-x86_64.exe"))
        qimg = qemu.with_name("qemu-img.exe")
        if not qimg.is_file():
            raise ValueError("Select qemu-system-x86_64.exe from a complete Windows QEMU distribution.")
        images = Path(self.settings["vega_images"]).resolve()
        for name in ["bzImage", "initramfs.cpio.gz", "kvd-manifest.json"]:
            if not (images / name).is_file():
                raise ValueError("Select the image_files folder from your Vega Virtual Device distribution.")
        folder = Path(self.settings["vm_folder"]).resolve() if self.settings["vm_folder"] else user_dir() / "emulators/default"
        if folder == images or folder.is_relative_to(images):
            raise ValueError("Keep the writable VM folder separate from SDK source images.")
        folder.mkdir(parents=True, exist_ok=True)
        overlay = folder / "userdata.qcow2"
        receipt = folder / "Image-Source.json"
        inventory = {path.name: {"bytes": path.stat().st_size, "mtimeNs": path.stat().st_mtime_ns} for path in images.iterdir() if path.is_file()}
        source = {"images": str(images), "inventory": inventory}
        if overlay.exists() and (not receipt.exists() or json.loads(receipt.read_text()) != source):
            raise ValueError("This VM disk belongs to a different or changed image set. Choose a new VM folder to preserve existing data.")
        port = int(self.settings["vm_port"])
        if not 1024 <= port <= 65535:
            raise ValueError("VM device port must be 1024–65535")
        # Reject occupied device ports. Never attach to or stop another program's VM.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            monitor_port = probe.getsockname()[1]
        self.monitor_port = monitor_port
        disk = CompositeDisk.from_vega_images(images)
        nbd = ReadOnlyNbd(disk)
        url = f"nbd://127.0.0.1:{nbd.port}"
        try:
            if not overlay.exists():
                runner.run([qimg, "create", "-f", "qcow2", "-F", "raw", "-b", url, overlay])
                atomic_write(receipt, json.dumps(source, indent=2).encode())
            else:
                # Base image layout is validated above. Update only the private
                # loopback port for this launch; the original images remain read-only.
                runner.run([qimg, "rebase", "-u", "-f", "qcow2", "-F", "raw", "-b", url, overlay])
            accel = self.settings["vm_accel"]
            if accel not in {"whpx", "tcg"}:
                raise ValueError("Choose WHPX or software TCG acceleration.")
            args = [qemu, "-name", self.display_name, "-machine", "q35", "-accel", accel,
                    "-m", "4096", "-smp", "2", "-kernel", images / "bzImage", "-initrd", images / "initramfs.cpio.gz",
                    "-append", "console=ttyS0 loglevel=4 boot.root_rw=y androidboot.slot_suffix=_a video=Virtual-1:1920x1080@60",
                    "-drive", "file=" + str(overlay).replace(",", ",,") + ",format=qcow2,if=virtio",
                    "-device", "virtio-vga-gl,xres=1920,yres=1080", "-display", "gtk,gl=on",
                    "-serial", "stdio", "-monitor", "none", "-qmp", f"tcp:127.0.0.1:{monitor_port},server=on,wait=off",
                    "-nic", f"user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:{port}-:5555"]
            runner.emit("Starting a native Windows Vega VM. Source images are read-only; guest writes go to " + str(overlay))
            runner.emit(f"After its ready screen appears, connect Device Lab to 127.0.0.1:{port}. First boot may restart during setup.")
            runner.run(args, timeout=86400, stop=lambda: qmp_quit(monitor_port), started=lambda pid: setattr(self, "pid", pid))
        finally:
            nbd.close()
            if nbd.error:
                runner.emit("Virtual disk service error: " + nbd.error)
