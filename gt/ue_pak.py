"""Unreal Engine .pak files: read data from v3-v9, list file names from v10+, write v5.

ponytail: no AES, no Oodle, no frozen (v9) index - those raise PakError with the reason.
"""
import hashlib
import struct
import zlib

MAGIC = 0x5A6F12E1


class PakError(Exception):
    pass


class _Buf:
    def __init__(self, data):
        self.b, self.o = data, 0

    def take(self, n):
        if self.o + n > len(self.b):
            raise PakError('truncated pak index')
        v = self.b[self.o:self.o + n]
        self.o += n
        return v

    def u8(self):
        return self.take(1)[0]

    def i32(self):
        return struct.unpack('<i', self.take(4))[0]

    def u32(self):
        return struct.unpack('<I', self.take(4))[0]

    def i64(self):
        return struct.unpack('<q', self.take(8))[0]

    def fstr(self):
        n = self.i32()
        if n == 0:
            return ''
        if n < 0:
            return self.take(-2 * n).decode('utf-16-le').rstrip('\0')
        return self.take(n).decode('utf-8', 'replace').rstrip('\0')


class Pak:
    """Pak(path).names() -> ['../../../Game/Content/...', ...]; .read(name) -> bytes."""

    def __init__(self, path):
        self.path = str(path)
        self._cm_u8 = False
        with open(self.path, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 300))
            tail = f.read()
            p = tail.rfind(struct.pack('<I', MAGIC))
            if p < 1:
                raise PakError('not an Unreal pak file')
            self.version, index_offset, index_size = struct.unpack_from('<Iqq', tail, p + 4)
            if self.version >= 4 and tail[p - 1] == 1:
                raise PakError('pak index is encrypted (AES key needed)')
            if self.version == 9 and tail[p + 44]:
                raise PakError('frozen pak index is not supported')
            names_at = p + 44 + (1 if self.version == 9 else 0)
            raw = tail[names_at:] if self.version >= 8 else b''
            self.methods = [None] + [raw[i * 32:(i + 1) * 32].split(b'\0')[0].decode('ascii', 'replace').lower() or None
                                     for i in range(len(raw) // 32)]
            f.seek(index_offset)
            index = f.read(index_size)
            if self.version >= 10:
                self.entries = None
                self._names = self._names_v10(f, index)
            else:
                self.entries = self._index_legacy(index)
                self._names = list(self.entries)

    def names(self):
        return list(self._names)

    def read(self, name):
        if self.entries is None:
            raise PakError(f'pak v{self.version}: reading file data is not supported (file names only)')
        e = self.entries[name]
        if e['encrypted']:
            raise PakError(f'{name} is encrypted')
        method = self._method(e['cm'])
        with open(self.path, 'rb') as f:
            if method is None:
                f.seek(e['offset'] + self._header_len(e))
                return f.read(e['size'])
            if method != 'zlib':
                raise PakError(f'{name}: unsupported compression {method}')
            out = bytearray()
            for start, end in e['blocks']:
                f.seek(e['offset'] + start if self.version >= 5 else start)
                out += zlib.decompress(f.read(end - start))
            return bytes(out)

    def _method(self, cm):
        if cm == 0:
            return None
        if self.version < 8:
            return 'zlib' if cm == 1 else f'flags{cm}'
        return (self.methods[cm] if cm < len(self.methods) else None) or f'#{cm}'

    def _header_len(self, e):
        blocks = 4 + 16 * len(e['blocks']) if e['cm'] else 0
        return 24 + (1 if self._cm_u8 else 4) + 20 + blocks + 1 + 4

    def _index_legacy(self, index):
        # UE4.22 wrote pak v8 with a 1-byte compression index, 4.23+ with 4 bytes: try both.
        for cm_u8 in ((False, True) if self.version == 8 else (False,)):
            self._cm_u8 = cm_u8
            try:
                b = _Buf(index)
                self.mount = b.fstr()
                out = {}
                for _ in range(b.i32()):
                    name = b.fstr()
                    out[self.mount + name] = self._entry(b)
                if b.o == len(index):
                    return out
            except (PakError, struct.error, UnicodeDecodeError):
                pass
        raise PakError('cannot parse pak index')

    def _entry(self, b):
        offset, size, usize = b.i64(), b.i64(), b.i64()
        cm = b.u8() if self._cm_u8 else b.u32()
        b.take(20)  # sha1
        blocks = [(b.i64(), b.i64()) for _ in range(b.i32())] if cm else []
        encrypted = b.u8()
        b.u32()  # compression block size
        return {'offset': offset, 'size': size, 'usize': usize, 'cm': cm, 'blocks': blocks, 'encrypted': encrypted}

    def _names_v10(self, f, index):
        b = _Buf(index)
        self.mount = b.fstr()
        b.i32()  # entry count
        b.take(8)  # path hash seed
        if b.u32():  # has path-hash index
            b.take(8 + 8 + 20)
        if not b.u32():
            raise PakError('pak has no full directory index')
        offset, size = b.i64(), b.i64()
        f.seek(offset)
        d = _Buf(f.read(size))
        names = []
        for _ in range(d.i32()):
            folder = d.fstr()
            folder = '' if folder == '/' else folder
            for _ in range(d.i32()):
                names.append(self.mount + folder + d.fstr())
                d.i32()  # encoded entry offset
        return names


def write_pak(path, mount, files):
    """files: {name relative to mount: bytes}. Writes an uncompressed v5 pak (loads in UE4.2x and UE5)."""
    def fstr(s):
        raw = s.encode('utf-8') + b'\0'
        return struct.pack('<i', len(raw)) + raw

    def entry(offset, data):
        return (struct.pack('<qqqi', offset, len(data), len(data), 0) + hashlib.sha1(data).digest()
                + b'\0' + struct.pack('<I', 0))

    body, index = bytearray(), bytearray()
    for name, data in files.items():
        offset = len(body)
        body += entry(0, data) + data
        index += fstr(name) + entry(offset, data)
    index = fstr(mount) + struct.pack('<i', len(files)) + bytes(index)
    footer = b'\0' + struct.pack('<IIqq', MAGIC, 5, len(body), len(index)) + hashlib.sha1(index).digest()
    with open(path, 'wb') as f:
        f.write(bytes(body) + index + footer)
