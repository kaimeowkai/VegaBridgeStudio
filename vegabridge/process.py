"""Cancellable child processes; no host shell, no global bridge/server shutdown."""
import os
import queue
import re
import subprocess
import threading
import time


class Cancelled(RuntimeError):
    pass


class Runner:
    def __init__(self, emit=lambda text: None, cancelled=None):
        self.emit = emit
        self.cancelled = cancelled or threading.Event()

    def check(self):
        if self.cancelled.is_set():
            raise Cancelled("Operation cancelled")

    def run(self, argv, cwd=None, env=None, timeout=60, binary=False, quiet=False, stop=None, started=None):
        self.check()
        args = [str(a) for a in argv]
        if not quiet:
            self.emit("› " + subprocess.list2cmdline(args))
        proc = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if started:
            started(proc.pid)
        lines = queue.Queue()
        def read():
            try:
                if binary:
                    while block := proc.stdout.read(65536):
                        lines.put(block)
                else:
                    for line in iter(proc.stdout.readline, b""):
                        lines.put(line)
            finally:
                lines.put(None)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        start = time.monotonic()
        result = bytearray()
        ended = False
        try:
            while not ended:
                self.check()
                if time.monotonic() - start > timeout:
                    raise TimeoutError(f"Command exceeded {timeout}s; only its own process tree will be stopped.")
                try:
                    block = lines.get(timeout=.1)
                except queue.Empty:
                    continue
                if block is None:
                    ended = True
                else:
                    result.extend(block)
                    if len(result) > 32 * 1024 * 1024:
                        raise RuntimeError("Command output exceeded 32 MiB; stop or filter the log.")
                    if not binary:
                        line = block.decode("utf-8", "replace").rstrip()
                        if not re.fullmatch(r"__VEGABRIDGE_RC_[a-f0-9]+__[0-9]+", line):
                            self.emit(re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line))
            code = proc.wait(timeout=3)
            if code:
                raise RuntimeError(f"Command exited with status {code}. See output above.")
            return bytes(result) if binary else result.decode("utf-8", "replace")
        finally:
            if proc.poll() is None:
                if stop:
                    try:
                        stop()
                        proc.wait(timeout=8)
                    except Exception:
                        pass
            if proc.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
                else:
                    proc.terminate()
                proc.wait(timeout=10)
            proc.stdout.close()
