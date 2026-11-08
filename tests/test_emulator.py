import errno
import socket
import struct
import uuid
import zlib
import pytest
from vegabridge.emulator_disk import BytesImage, CompositeDisk, QcowImage, ReadOnlyNbd, receive
from vegabridge.native_vm import qmp_command


def test_gpt_partition_layout_and_crc():
    disk = CompositeDisk([("system_a", BytesImage(b"SYSTEM")), ("userdata", BytesImage(b"USER"))], uuid.UUID(int=1))
    header = bytearray(disk.read(512, 92))
    expected = struct.unpack_from("<I", header, 16)[0]
    header[16:20] = bytes(4)
    assert zlib.crc32(header) == expected
    assert disk.read(510, 2) == b"\x55\xaa"
    entries = disk.read(1024, 128*128)
    assert zlib.crc32(entries) == struct.unpack_from("<I", header, 88)[0]
    assert entries[56:56+16].decode("utf-16le") == "system_a"
    assert disk.read(1024*1024-2, 8) == b"\0\0SYSTEM"
    assert disk.read(disk.size-512, 8) == b"EFI PART"
    with pytest.raises(ValueError):
        disk.read(disk.size-1, 2)


def test_read_only_nbd_exports_disk_and_rejects_writes():
    disk = CompositeDisk([("system_a", BytesImage(b"ORIGINAL"))])
    server = ReadOnlyNbd(disk)
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=2) as client:
            client.settimeout(2)
            magic, _, size, flags = struct.unpack(">QQQI", receive(client, 28))
            receive(client, 124)
            assert magic == 0x4e42444d41474943 and size == disk.size and flags & 2
            client.sendall(struct.pack(">IHHQQI", 0x25609513, 0, 0, 1, 1024*1024, 8))
            assert struct.unpack(">IIQ", receive(client, 16)) == (0x67446698, 0, 1)
            assert receive(client, 8) == b"ORIGINAL"
            client.sendall(struct.pack(">IHHQQI", 0x25609513, 0, 1, 2, 1024*1024, 8) + b"MODIFIED")
            assert struct.unpack(">IIQ", receive(client, 16))[1] == errno.EROFS
            client.sendall(struct.pack(">IHHQQI", 0x25609513, 0, 0, 3, disk.size, 512))
            assert struct.unpack(">IIQ", receive(client, 16))[1] == errno.EINVAL
            assert disk.read(1024*1024, 8) == b"ORIGINAL"
            client.sendall(struct.pack(">IHHQQI", 0x25609513, 0, 2, 4, 0, 0))
    finally:
        server.close()
    assert server.error is None


def test_sparse_qcow_read_and_zero_cluster(tmp_path):
    path = tmp_path / "userdata.qcow2"
    cluster = 65536
    data = bytearray(cluster * 4)
    data[:4] = b"QFI\xfb"
    struct.pack_into(">I", data, 4, 3)
    struct.pack_into(">I", data, 20, 16)
    struct.pack_into(">Q", data, 24, cluster*2)
    struct.pack_into(">IQ", data, 36, 1, cluster)
    struct.pack_into(">Q", data, cluster, (1<<63) | cluster*2)
    struct.pack_into(">Q", data, cluster*2, (1<<63) | cluster*3)
    data[cluster*3:] = b"Z" * cluster
    path.write_bytes(data)
    image = QcowImage(path)
    try:
        assert image.read(0, 4) == b"ZZZZ"
        assert image.read(cluster-2, 4) == b"ZZ\0\0"
        assert image.read(cluster, 4) == bytes(4)
        with pytest.raises(ValueError):
            image.read(cluster*2, 1)
    finally:
        image.close()


def test_qmp_protocol_sends_capabilities_and_arguments():
    import json
    import threading
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    requests = []
    def serve():
        with server:
            client, _ = server.accept()
            with client:
                stream = client.makefile("rwb", buffering=0)
                stream.write(b'{"QMP":{"version":{}}}\n')
                for _ in range(2):
                    requests.append(json.loads(stream.readline()))
                    stream.write(b'{"return":{}}\n')
    worker = threading.Thread(target=serve)
    worker.start()
    qmp_command(server.getsockname()[1], "screendump", {"filename": "example.png", "format": "png"})
    worker.join(timeout=3)
    assert requests == [{"execute": "qmp_capabilities"}, {"execute": "screendump", "arguments": {"filename": "example.png", "format": "png"}}]


def test_vm_capture_never_selects_a_desktop_monitor(tmp_path, monkeypatch):
    import vegabridge.window_capture as module
    monkeypatch.setattr(module, "owned_window", lambda pid, title: 1234)
    seen = {}
    class Frame:
        width, height = 640, 480
        def save_as_image(self, path):
            seen["path"] = path
    class Control:
        def stop(self):
            pass
        def wait(self):
            pass
    class Capture:
        def __init__(self, **kwargs):
            seen.update(kwargs)
        def event(self, fn):
            setattr(self, fn.__name__, fn)
            return fn
        def start_free_threaded(self):
            control = Control()
            self.on_frame_arrived(Frame(), control)
            return control
    module.capture_vm_window(99, "QEMU (VegaBridge test)", tmp_path / "capture.png", Capture)
    assert seen["window_hwnd"] == 1234 and seen["monitor_index"] is None
    assert seen["draw_border"] is None
