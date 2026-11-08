"""Read-only virtual GPT disk for owner-supplied Vega development images.

The native Windows QEMU guest writes to its own QCOW overlay. SDK source images
are never modified. No Amazon image is bundled or downloaded by this module.
"""
import bisect
import collections
import errno
import socket
import struct
import threading
import uuid
import zlib
from pathlib import Path

MiB = 1024 * 1024


class RawImage:
    def __init__(self, path):
        self.path = Path(path)
        self.file = self.path.open("rb")
        self.size = self.path.stat().st_size

    def read(self, offset, length):
        self.file.seek(offset)
        return self.file.read(length)

    def close(self):
        self.file.close()


class QcowImage(RawImage):
    """Bounded read-only QCOW2 v2/v3 reader for the SDK's sparse userdata image."""
    def __init__(self, path):
        super().__init__(path)
        header = self.file.read(104)
        if header[:4] != b"QFI\xfb" or struct.unpack_from(">I", header, 4)[0] not in {2, 3}:
            raise ValueError("Expected a QCOW2 v2/v3 userdata image")
        if struct.unpack_from(">Q", header, 8)[0] or struct.unpack_from(">I", header, 32)[0]:
            raise ValueError("External backing files and encrypted QCOW images are unsupported")
        bits = struct.unpack_from(">I", header, 20)[0]
        if not 9 <= bits <= 21:
            raise ValueError("Unsupported QCOW cluster size")
        self.cluster = 1 << bits
        self.size = struct.unpack_from(">Q", header, 24)[0]
        count, table = struct.unpack_from(">IQ", header, 36)
        if count > 1_000_000:
            raise ValueError("QCOW table exceeds limits")
        self.file.seek(table)
        self.l1 = struct.unpack(">" + "Q" * count, self.file.read(count * 8))
        self.tables = collections.OrderedDict()

    def read(self, offset, length):
        if offset < 0 or offset + length > self.size:
            raise ValueError("QCOW read outside virtual disk")
        out = bytearray()
        mask = 0x00FFFFFFFFFFFE00
        per_table = self.cluster // 8
        while length:
            cluster_index, within = divmod(offset, self.cluster)
            first, second = divmod(cluster_index, per_table)
            amount = min(length, self.cluster - within)
            if first >= len(self.l1):
                raise ValueError("QCOW virtual size exceeds L1 mapping")
            table_offset = self.l1[first] & mask
            entry = 0
            if table_offset:
                if table_offset not in self.tables:
                    self.file.seek(table_offset)
                    self.tables[table_offset] = self.file.read(self.cluster)
                    if len(self.tables) > 32:
                        self.tables.popitem(last=False)
                entry = struct.unpack_from(">Q", self.tables[table_offset], second * 8)[0]
            if entry & (1 << 62):
                raise ValueError("Compressed QCOW clusters are unsupported")
            data_offset = entry & mask
            if not data_offset or entry & 1:
                out.extend(bytes(amount))
            else:
                self.file.seek(data_offset + within)
                chunk = self.file.read(amount)
                if len(chunk) != amount:
                    raise ValueError("Truncated QCOW data cluster")
                out.extend(chunk)
            offset += amount
            length -= amount
        return bytes(out)


class BytesImage:
    def __init__(self, data):
        self.data, self.size = data, len(data)

    def read(self, offset, length):
        return self.data[offset:offset + length]

    def close(self):
        pass


class CompositeDisk:
    def __init__(self, sources, disk_id=None):
        """sources = [(GPT partition name, RawImage/QcowImage), ...]."""
        self.images = [image for _, image in sources]
        disk_uuid = disk_id or uuid.uuid4()
        self.regions = []
        self.partitions = []
        entries = bytearray(128 * 128)
        offset = MiB
        kind = uuid.UUID("0fc63daf-8483-4772-8e79-3d69d8477de4").bytes_le
        for index, (name, image) in enumerate(sources):
            if index >= 128 or len(name.encode("utf-16le")) > 72:
                raise ValueError("Too many partitions or oversized GPT label")
            size = (image.size + MiB - 1) // MiB * MiB
            self.partitions.append({"name": name, "start": offset, "bytes": size})
            self.regions.append((offset, offset + image.size, image))
            entries[index*128:(index+1)*128] = struct.pack("<16s16sQQQ72s", kind, uuid.uuid5(disk_uuid, name).bytes_le, offset//512, (offset+size)//512-1, 0, name.encode("utf-16le"))
            offset += size
        self.size = offset + MiB
        sectors = self.size // 512
        guid, entries_crc = disk_uuid.bytes_le, zlib.crc32(entries)
        def header(current, backup, table):
            data = struct.pack("<8sIIIIQQQQ16sQIII", b"EFI PART", 0x10000, 92, 0, 0, current, backup, 34, sectors-34, guid, table, 128, 128, entries_crc)
            data = data[:16] + struct.pack("<I", zlib.crc32(data)) + data[20:]
            return data + bytes(512 - len(data))
        mbr = bytearray(512)
        mbr[446:462] = struct.pack("<B3sB3sII", 0, b"\0\2\0", 0xee, b"\xff\xff\xff", 1, min(sectors-1, 0xffffffff))
        mbr[510:512] = b"\x55\xaa"
        initial = bytes(mbr) + header(1, sectors-1, 2) + bytes(entries)
        self.regions += [(0, len(initial), BytesImage(initial)), ((sectors-33)*512, (sectors-1)*512, BytesImage(bytes(entries))), ((sectors-1)*512, sectors*512, BytesImage(header(sectors-1, 1, sectors-33)))]
        self.regions.sort(key=lambda item: item[0])
        self.starts = [start for start, end, image in self.regions]

    @classmethod
    def from_vega_images(cls, folder):
        folder = Path(folder).resolve()
        mapping = [("bootloader", "bootloader"), ("system_a", "system.ext4"), ("vendor_a", "vendor.ext4"), ("userdata", "userdata.ext4.qcow2"), ("cache", "cache.ext4"), ("idme", "idme.img"), ("keys", "keys.ext4"), ("misc", "misc.img")]
        sources = []
        try:
            for label, name in mapping:
                path = folder / name
                if path.is_symlink() or not path.resolve().is_relative_to(folder):
                    raise ValueError("Linked images are not imported")
                sources.append((label, QcowImage(path) if name.endswith(".qcow2") else RawImage(path)))
            return cls(sources, uuid.uuid5(uuid.NAMESPACE_URL, folder.as_uri()))
        except Exception:
            for _, image in sources:
                image.close()
            raise

    def read(self, offset, length):
        if offset < 0 or length < 0 or offset + length > self.size or length > 16 * MiB:
            raise ValueError("Read outside composite disk or oversized request")
        result = bytearray(length)
        for start, end, image in self.regions:
            a, b = max(offset, start), min(offset + length, end)
            if b > a:
                result[a-offset:b-offset] = image.read(a-start, b-a)
        return bytes(result)

    def close(self):
        for image in self.images:
            image.close()


def receive(sock, length):
    parts = bytearray()
    while len(parts) < length:
        data = sock.recv(length - len(parts))
        if not data:
            raise EOFError()
        parts.extend(data)
    return bytes(parts)


class ReadOnlyNbd:
    """Private loopback legacy NBD export. Only this VM's QEMU should connect."""
    def __init__(self, disk, port=0):
        self.disk = disk
        self.stop = threading.Event()
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", port))
        self.socket.listen(1)
        self.socket.settimeout(.25)
        self.port = self.socket.getsockname()[1]
        self.client = None
        self.error = None
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        try:
            while not self.stop.is_set():
                try:
                    client, _ = self.socket.accept()
                except socket.timeout:
                    continue
                self.client = client
                try:
                    with client:
                        # Old-style NBD is supported by QEMU; flags HAS_FLAGS | READ_ONLY.
                        client.sendall(struct.pack(">QQQI", 0x4e42444d41474943, 0x0000420281861253, self.disk.size, 3) + bytes(124))
                        while not self.stop.is_set():
                            magic, flags, kind, handle, offset, length = struct.unpack(">IHHQQI", receive(client, 28))
                            if magic != 0x25609513 or length > 16 * MiB:
                                raise ValueError("Invalid or oversized NBD request")
                            if kind == 2:
                                break
                            error, data = 0, b""
                            if kind == 0:
                                try:
                                    data = self.disk.read(offset, length)
                                except ValueError:
                                    error = errno.EINVAL
                            elif kind == 1:
                                receive(client, length)
                                error = errno.EROFS
                            elif kind != 3:
                                error = errno.EROFS
                            client.sendall(struct.pack(">IIQ", 0x67446698, error, handle) + data)
                except (EOFError, ConnectionError, OSError):
                    pass
                finally:
                    self.client = None
        except OSError as error:
            if not self.stop.is_set():
                self.error = str(error)
        except Exception as error:
            self.error = str(error)

    def close(self):
        self.stop.set()
        self.socket.close()
        if self.client:
            try:
                self.client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.thread.join(timeout=3)
        self.disk.close()
