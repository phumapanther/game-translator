"""UE .locres read/write, versions 2 (UE4.2x) and 3 (UE5).

ponytail: namespace/key/source hashes are copied from the source file, never recomputed -
the game only needs them unchanged.
"""
import struct
from dataclasses import dataclass

MAGIC = bytes.fromhex('0E147475674A03FC4A15909DC3377F1B')


class LocresError(Exception):
    pass


@dataclass
class Entry:
    ns_hash: int
    ns: str
    key_hash: int
    key: str
    src_hash: int
    text: str


class _R:
    def __init__(self, b):
        self.b, self.o = b, 0

    def take(self, n):
        v = self.b[self.o:self.o + n]
        if len(v) < n:
            raise LocresError('truncated locres file')
        self.o += n
        return v

    def u8(self):
        return self.take(1)[0]

    def u32(self):
        return struct.unpack('<I', self.take(4))[0]

    def i32(self):
        return struct.unpack('<i', self.take(4))[0]

    def i64(self):
        return struct.unpack('<q', self.take(8))[0]

    def fstr(self):
        n = self.i32()
        if n == 0:
            return ''
        if n < 0:
            return self.take(-2 * n).decode('utf-16-le')[:-1]
        return self.take(n).decode('latin-1')[:-1]


def read(data):
    """bytes -> (version, [Entry]) in file order."""
    r = _R(data)
    if r.take(16) != MAGIC:
        raise LocresError('not a locres file (or the unsupported legacy v0 format)')
    version = r.u8()
    if version not in (2, 3):
        raise LocresError(f'locres version {version} is not supported')
    strings_at = r.i64()
    body_at = r.o
    r.o = strings_at
    strings = []
    for _ in range(r.i32()):
        strings.append(r.fstr())
        r.i32()  # refcount
    r.o = body_at
    r.u32()  # entry count
    entries = []
    for _ in range(r.u32()):
        ns_hash, ns = r.u32(), r.fstr()
        for _ in range(r.u32()):
            key_hash, key, src_hash = r.u32(), r.fstr(), r.u32()
            entries.append(Entry(ns_hash, ns, key_hash, key, src_hash, strings[r.i32()]))
    return version, entries


def _fstr(s):
    s += '\0'
    try:
        raw = s.encode('ascii')
        return struct.pack('<i', len(raw)) + raw
    except UnicodeEncodeError:
        raw = s.encode('utf-16-le')
        return struct.pack('<i', -(len(raw) // 2)) + raw


def write(version, entries):
    """(version, [Entry]) -> bytes. Byte-identical to Unreal's own output for an unmodified file."""
    index, strings, refs = {}, [], []
    for e in entries:
        if e.text not in index:
            index[e.text] = len(strings)
            strings.append(e.text)
            refs.append(0)
        refs[index[e.text]] += 1
    groups = {}
    for e in entries:
        groups.setdefault((e.ns_hash, e.ns), []).append(e)
    body = bytearray(struct.pack('<II', len(entries), len(groups)))
    for (ns_hash, ns), items in groups.items():
        body += struct.pack('<I', ns_hash) + _fstr(ns) + struct.pack('<I', len(items))
        for e in items:
            body += struct.pack('<I', e.key_hash) + _fstr(e.key) + struct.pack('<Ii', e.src_hash, index[e.text])
    tail = bytearray(struct.pack('<i', len(strings)))
    for s, n in zip(strings, refs):
        tail += _fstr(s) + struct.pack('<i', n)
    head = MAGIC + bytes([version]) + struct.pack('<q', 16 + 1 + 8 + len(body))
    return head + bytes(body) + bytes(tail)
