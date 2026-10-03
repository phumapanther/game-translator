# Game Translator (sub-project 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows desktop app (Tkinter, Thai UI) that translates Unreal Engine games to Thai with the Claude API, installs the result as a `_P.pak` mod, and keeps a growing memory (style, lessons, per-game glossary, translation memory) across games.

**Architecture:** `app.pyw` is a thin Tkinter shell; all logic lives in small modules under `gt/` (pak I/O, locres I/O, scan, validate, memory, translate, book, install). Each module is testable without the network: Claude is injected as a client object and replaced by a fake in tests. Tests are plain `assert` functions run by a 30-line runner (`python tests/run.py`) against real game files already on this PC (Maneater, Junji Ito Maniac/JIM); tests that need a missing file print SKIP.

**Tech Stack:** Python 3.12 (Microsoft Store install, `python` on PATH), Tkinter, `anthropic` Python SDK (only external dependency), git.

**Spec:** `docs/superpowers/specs/2026-10-03-game-translator-design.md`

## Global Constraints

- Project root: `C:\Users\watch\game-translator`. Run every command from there.
- Games come from Steam only (any Steam library folder). Unreal Engine is supported; Unity games are detected and refused with a Thai explanation (Unity is sub-project 3).
- Python: `python` (3.12). External dependency: `anthropic` only (`python -m pip install --user anthropic`). No pytest; tests are `def test_*()` with `assert`, run by `python tests/run.py [module[.test]]`.
- Console output must survive Thai: `tests/run.py` reconfigures stdout to UTF-8.
- Model IDs exactly: `claude-opus-5-5` (default), `claude-sonnet-5-5`, `claude-haiku-4-5`, `claude-fable-5-1`. Never add date suffixes.
- Prices $/1M tokens (input, output, cache read, cache write): Opus 5.5 (4, 20, 0.20, 5.0) · Sonnet 5.5 (2, 10, 0.20, 2.5) · Haiku 4.5 (1, 5, 0.10, 1.25) · Fable 5.1 (10, 50, 0.25, 12.5).
- Claude calls: `max_tokens=32000`, streaming + `get_final_message()`, `output_config.format` JSON schema, `output_config.effort="medium"` except Haiku 4.5 (no effort param), system prompt as one text block with `cache_control: {"type": "ephemeral"}`. For Opus 5.5 / Sonnet 5.5 / Fable 5.1 use `client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"}, ...)`.
- Batches: ≤150 items and ≤12,000 English chars; first batch alone (writes the prompt cache), then 4 in parallel.
- Pak output: uncompressed pak **v5**, mount `../../../`, locres keeps every original hash.
- Fonts: Sarabun (OFL) — `fonts/Sarabun-Regular.ttf`, `fonts/Sarabun-Bold.ttf`, `fonts/OFL.txt`. Font names matching `bold|black|heavy` (case-insensitive) get Bold.
- Glossary term fields: `en, th, category, tone, note, dnt`; categories `character, location, item, skill, creature, ui, term, other`. `other` = auto-collected, not enforced by the validator; every other category is enforced (soft).
- Never commit: `settings.json` (may hold the API key), `work/`, `books/`, `memory/`.
- All user-facing messages are Thai. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Game still running during install** → pak file locked → expect a Thai "close the game first" error, the old pak backed up and untouched. Pinned in Task 7 (`test_install_reports_locked_target`).
2. **Wrong API key / no internet mid-run** → expect a Thai error, finished batches kept, nothing re-billed on the next run. Pinned in Task 6 (`test_bad_key_raises_thai_error_and_saves_nothing`, `test_connection_error_is_thai`, `test_translates_everything_and_resumes_for_free`).
3. **Claude drops or mangles items** (missing id, broken `<tag>`/`{0}`) → expect one fix round, never a broken string in the game. Pinned in Task 6 (`test_missing_and_broken_items_get_one_fix_round`, `test_still_broken_after_fix_is_not_saved`).
4. **User presses Stop / closes the app** → expect completed batches saved and resume to skip them. Pinned in Task 6 (`test_stop_event_halts_before_next_batch`, resume test).
5. **Folder isn't an Unreal game (e.g. a Unity game), or a UE5/Oodle game without a mod** → expect a Thai explanation (and the "pick Game.locres" dialog), not a traceback. Pinned in Task 5 (`test_not_a_game_folder`, `test_unity_folder_is_explained`, `test_jim_without_mod_needs_manual_locres`).

---

### Task 1: Project scaffold, test runner, pak reader/writer

**Files:**
- Create: `.gitignore`, `gt/__init__.py`, `gt/ue_pak.py`, `tests/__init__.py`, `tests/run.py`, `tests/paths.py`, `tests/test_ue_pak.py`

**Interfaces:**
- Produces: `gt.ue_pak.Pak(path)` with `.version:int`, `.mount:str`, `.methods:list`, `.names()->list[str]` (full names incl. mount, e.g. `'../../../Maneater/Content/...'`), `.read(name)->bytes` (v3–v9 only; raises `PakError` otherwise); `gt.ue_pak.write_pak(path, mount:str, files:dict[str,bytes])`; `gt.ue_pak.PakError`.
- Produces (tests): `tests.paths.need(*paths)`, `tests.paths.tmp_path(name)->Path`, `tests.paths.SkipTest`, path constants `ROOT, MANEATER, MANEATER_BASE_PAK, MANEATER_MOD_V1, JIM, JIM_BASE_PAK, JIM_MOD_PAK`.

- [ ] **Step 1: Create scaffold files**

`.gitignore`:
```
settings.json
work/
books/
memory/
__pycache__/
```

`gt/__init__.py` and `tests/__init__.py`: empty files.

`tests/paths.py`:
```python
"""Real game files on this PC used as test fixtures (never copied into the repo)."""
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEAM = Path(r'C:\Program Files (x86)\Steam\steamapps\common')
MANEATER = STEAM / 'Maneater'
MANEATER_BASE_PAK = MANEATER / 'Maneater/Content/Paks/Maneater-WindowsNoEditor.pak'
MANEATER_MOD_V1 = Path(r'C:\Users\watch\Downloads\Mod Thai Maneater V.1.0.1-6-1-0-1-1658761829 (1)'
                       r'\Mod Thai Maneater\Maneater\Content\Paks\Maneater-WindowsNoEditor_Mod_Thai_P.pak')
JIM = STEAM / 'JIM'
JIM_BASE_PAK = JIM / 'JIM/Content/Paks/JIM-Windows.pak'
JIM_MOD_PAK = JIM / 'JIM/Content/Paks/JIMTH_MisterTime_P.pak'

_TMP = Path(tempfile.mkdtemp(prefix='gt-tests-'))


class SkipTest(Exception):
    pass


def need(*paths):
    for p in paths:
        if not Path(p).exists():
            raise SkipTest(f'missing {p}')


def tmp_path(name):
    return _TMP / name
```

`tests/run.py`:
```python
"""Tiny test runner. python tests/run.py [module | module.test ...]  (ponytail: no pytest, asserts only)"""
import importlib
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')
from tests.paths import SkipTest  # noqa: E402


def main(args):
    targets = args or sorted(p.stem for p in (ROOT / 'tests').glob('test_*.py'))
    failed = 0
    for target in targets:
        module_name, _, only = target.partition('.')
        mod = importlib.import_module(f'tests.{module_name}')
        for name in sorted(n for n in dir(mod) if n.startswith('test_') and (not only or n == only)):
            try:
                getattr(mod, name)()
                print(f'PASS {module_name}.{name}')
            except SkipTest as e:
                print(f'SKIP {module_name}.{name}: {e}')
            except Exception:
                failed += 1
                print(f'FAIL {module_name}.{name}')
                traceback.print_exc()
    print('OK' if not failed else f'FAILED: {failed}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Write the failing tests** — `tests/test_ue_pak.py`:
```python
from gt.ue_pak import Pak, PakError, write_pak
from tests.paths import JIM_BASE_PAK, JIM_MOD_PAK, MANEATER_BASE_PAK, MANEATER_MOD_V1, need, tmp_path

LOCRES_MAGIC4 = bytes.fromhex('0E147475')


def test_reads_zlib_v9_base_pak():
    need(MANEATER_BASE_PAK)
    pak = Pak(MANEATER_BASE_PAK)
    assert pak.version == 9 and pak.methods[1] == 'zlib'
    data = pak.read('../../../Maneater/Content/Localization/Game/en/Game.locres')
    assert len(data) == 858117 and data[:4] == LOCRES_MAGIC4


def test_reads_v5_and_v3_mod_paks():
    need(MANEATER_MOD_V1, JIM_MOD_PAK)
    assert Pak(MANEATER_MOD_V1).version == 5
    jim = Pak(JIM_MOD_PAK)
    assert jim.version == 3 and len(jim.names()) == 37
    assert len(jim.read('../../../JIM/Content/Localization/Game/en/Game.locres')) == 159417


def test_v11_lists_names_but_refuses_data():
    need(JIM_BASE_PAK)
    pak = Pak(JIM_BASE_PAK)
    names = pak.names()
    assert pak.version == 11 and len(names) == 4493
    assert '../../../JIM/Content/Art/GUI/GUI_Library/GUI_Font/EN/NotoSerif-Regular.ufont' in names
    try:
        pak.read(names[0])
        assert False, 'v11 data must be refused'
    except PakError:
        pass


def test_write_then_read_back():
    files = {'Maneater/Content/a.txt': b'hello', 'Engine/b.bin': bytes(range(256)) * 10}
    out = tmp_path('roundtrip.pak')
    write_pak(out, '../../../', files)
    pak = Pak(out)
    assert pak.version == 5 and sorted(pak.names()) == sorted('../../../' + n for n in files)
    for name, data in files.items():
        assert pak.read('../../../' + name) == data


def test_rejects_non_pak():
    out = tmp_path('junk.pak')
    out.write_bytes(b'x' * 1000)
    try:
        Pak(out)
        assert False, 'junk must be rejected'
    except PakError:
        pass
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python tests/run.py test_ue_pak`
Expected: ImportError / `ModuleNotFoundError: No module named 'gt.ue_pak'`.

- [ ] **Step 4: Implement `gt/ue_pak.py`**
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python tests/run.py test_ue_pak`
Expected: 5 × PASS, `OK` (Maneater base pak index takes a few seconds).

- [ ] **Step 6: Commit**
```bash
git add .gitignore gt tests
git commit -m "feat: pak reader (v3-v9 data, v10+ names) and v5 writer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: locres read/write

**Files:**
- Create: `gt/locres.py`, `tests/test_locres.py`

**Interfaces:**
- Consumes: `gt.ue_pak.Pak` (tests only).
- Produces: `gt.locres.Entry(ns_hash:int, ns:str, key_hash:int, key:str, src_hash:int, text:str)` (dataclass, mutable), `gt.locres.read(data:bytes) -> (version:int, list[Entry])`, `gt.locres.write(version:int, entries:list[Entry]) -> bytes`, `gt.locres.LocresError`.

- [ ] **Step 1: Write the failing tests** — `tests/test_locres.py`:
```python
from gt import locres
from gt.ue_pak import Pak
from tests.paths import JIM_MOD_PAK, MANEATER_BASE_PAK, need


def _maneater_en():
    need(MANEATER_BASE_PAK)
    return Pak(MANEATER_BASE_PAK).read('../../../Maneater/Content/Localization/Game/en/Game.locres')


def test_v2_roundtrip_is_byte_identical():
    data = _maneater_en()
    version, entries = locres.read(data)
    assert version == 2 and len(entries) == 6655
    assert locres.write(version, entries) == data


def test_v3_roundtrip_keeps_entries():
    need(JIM_MOD_PAK)
    data = Pak(JIM_MOD_PAK).read('../../../JIM/Content/Localization/Game/en/Game.locres')
    version, entries = locres.read(data)
    assert version == 3 and len(entries) == 1442
    assert locres.read(locres.write(version, entries)) == (version, entries)


def test_thai_text_survives_write():
    version, entries = locres.read(_maneater_en())
    entries[0].text = 'สวัสดี <highlight>ฉลาม</> {0}\r\n'
    again = locres.read(locres.write(version, entries))[1]
    assert again[0].text == entries[0].text and again[1] == entries[1]


def test_rejects_garbage():
    try:
        locres.read(b'not a locres file at all')
        assert False, 'garbage must be rejected'
    except locres.LocresError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python tests/run.py test_locres`
Expected: `ModuleNotFoundError: No module named 'gt.locres'`.

- [ ] **Step 3: Implement `gt/locres.py`**
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python tests/run.py test_locres`
Expected: 4 × PASS, `OK`.

- [ ] **Step 5: Commit**
```bash
git add gt/locres.py tests/test_locres.py
git commit -m "feat: locres v2/v3 reader and byte-exact writer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Translation validator

**Files:**
- Create: `gt/validate.py`, `tests/test_validate.py`

**Interfaces:**
- Produces: `gt.validate.problems(en:str, th:str, glossary:list[dict]=()) -> list[tuple[str, str]]` (severity `'hard'|'soft'`, English message that is sent back to Claude), `gt.validate.is_ok(en, th, glossary=()) -> bool` (no hard problems), constants `THAI`, `TOKEN` (compiled regexes).

- [ ] **Step 1: Write the failing tests** — `tests/test_validate.py`:
```python
from gt.validate import is_ok, problems


def test_good_translation_passes():
    assert problems('Press {0} to <highlight>BITE</>.\r\n', 'กด {0} เพื่อ <highlight>กัด</>\r\n') == []


def test_missing_tag_is_hard():
    assert not is_ok('<highlight>BITE</>', 'กัด')


def test_missing_placeholder_is_hard():
    assert not is_ok('Kill {0} Apex', 'ฆ่าเอเพ็กซ์')


def test_line_breaks_must_match():
    assert not is_ok('A\r\nB', 'ก ข')


def test_edge_spaces_must_match():
    assert not is_ok(' Wish Sewer Here ', 'ต้องการท่อระบายน้ำที่นี่')


def test_english_kept_on_purpose_is_ok():
    assert is_ok('NE', 'NE') and is_ok('Maneater', 'Maneater')


def test_english_changed_without_thai_is_hard():
    assert not is_ok('Shark', 'Sharky')


def test_long_unspaced_thai_is_soft():
    p = problems('The shark is hurt and needs self-care right now.',
                 'ฉลามได้รับบาดเจ็บและจำเป็นต้องดูแลตนเองเดี๋ยวนี้เลยทันทีทันใดนะ')
    assert p and all(sev == 'soft' for sev, _ in p)


def test_glossary_term_must_be_used():
    g = [{'en': 'Grotto', 'th': 'ถ้ำใต้น้ำ', 'category': 'location'}]
    assert problems('Find the Grotto', 'หาถ้ำใต้น้ำ', g) == []
    assert problems('Find the Grotto', 'หาถ้ำ', g) == [('soft', 'glossary: "Grotto" must be "ถ้ำใต้น้ำ"')]


def test_other_category_is_not_enforced():
    g = [{'en': 'Back', 'th': 'กลับ', 'category': 'other'}]
    assert problems('Go back home', 'ไปบ้าน', g) == []


def test_dnt_term_must_stay_english():
    g = [{'en': 'Truth Quest', 'th': '', 'category': 'item', 'dnt': True}]
    assert problems('Requires Truth Quest', 'ต้องมี Truth Quest', g) == []
    assert problems('Requires Truth Quest', 'ต้องมีภารกิจความจริง', g)[0][0] == 'soft'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python tests/run.py test_validate`
Expected: `ModuleNotFoundError: No module named 'gt.validate'`.

- [ ] **Step 3: Implement `gt/validate.py`**
```python
"""Check a Thai translation against its English source.

hard problems -> the translation is rejected (English is kept);
soft problems -> Claude is asked to fix once, the translation is accepted if they remain.
"""
import re
from collections import Counter

THAI = re.compile('[\u0E00-\u0E7F]')
TOKEN = re.compile(r'<[^<>]*>|\{[^{}]*\}|%[a-zA-Z%]?')
LONG_RUN = 45  # Thai chars without a space: Unreal can't wrap such a line


def _tokens(s):
    return Counter(TOKEN.findall(s))


def problems(en, th, glossary=()):
    """-> [(severity, message)]; severity is 'hard' or 'soft'. glossary: term dicts (see gt.memory)."""
    out = []
    if _tokens(en) != _tokens(th):
        out.append(('hard', f'markup/placeholders must be exactly {sorted(_tokens(en).elements())}'))
    if en.count('\n') != th.count('\n'):
        out.append(('hard', f'must have exactly {en.count(chr(10))} line breaks'))
    if (en[:1].isspace(), en[-1:].isspace()) != (th[:1].isspace(), th[-1:].isspace()):
        out.append(('hard', 'leading/trailing spaces must match the English'))
    if th != en and re.search('[A-Za-z]{2,}', en) and not THAI.search(th):
        out.append(('hard', 'no Thai text'))
    for seg in re.split(r'\s+', TOKEN.sub(' ', th)):
        if len(seg) > LONG_RUN and THAI.search(seg):
            out.append(('soft', f'add spaces between phrases: "{seg[:20]}…" runs {len(seg)} chars without a space'))
            break
    for term in glossary:
        if _uses_term(en, term) and not _honours_term(th, term):
            want = term['en'] if term.get('dnt') else term['th']
            out.append(('soft', f'glossary: "{term["en"]}" must be "{want}"'))
    return out


def is_ok(en, th, glossary=()):
    return not any(sev == 'hard' for sev, _ in problems(en, th, glossary))


def _uses_term(en, term):
    if term.get('category', 'other') == 'other' or len(term['en']) < 3:
        return False
    return re.search(r'\b' + re.escape(term['en']) + r'\b', en, re.I) is not None


def _honours_term(th, term):
    want = term['en'] if term.get('dnt') else term['th']
    return want.lower() in th.lower()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python tests/run.py test_validate`
Expected: 11 × PASS, `OK`.

- [ ] **Step 5: Commit**
```bash
git add gt/validate.py tests/test_validate.py
git commit -m "feat: translation validator (markup, line breaks, spacing, glossary)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Memory store + seed from today's Maneater work

**Files:**
- Create: `gt/memory.py`, `tests/test_memory.py`, `tools/seed_memory.py`
- Creates at run time (git-ignored): `memory/style_th.md`, `memory/lessons.md`, `memory/glossary/maneater.json`, `memory/tm.jsonl`

**Interfaces:**
- Consumes: `gt.ue_pak.Pak`, `gt.locres.read`, `gt.validate.THAI` (seed tool only).
- Produces: `gt.memory.Memory(root)` with `.text(name)->str`, `.append(name, lines:list[str], heading:str)`, `.glossary(game_id)->list[dict]`, `.add_terms(game_id, terms, overwrite=False)->int`, `.teach(game_id, text)->str` (Thai confirmation), `.tm_get(en)->str|None`, `.tm_add(pairs:list[tuple[str,str]], game_id, model)`, `.system_prompt(game_id, game_name)->str` (deterministic). Constant `CATEGORIES`.

- [ ] **Step 1: Write the failing tests** — `tests/test_memory.py`:
```python
from gt.memory import Memory
from tests.paths import tmp_path


def test_glossary_add_and_no_overwrite():
    m = Memory(tmp_path('m1'))
    assert m.add_terms('g', [{'en': 'Grotto', 'th': 'ถ้ำใต้น้ำ', 'category': 'location'}]) == 1
    assert m.add_terms('g', [{'en': 'grotto', 'th': 'ถ้ำ'}]) == 0
    assert m.glossary('g')[0]['th'] == 'ถ้ำใต้น้ำ'


def test_teach_term_and_style():
    m = Memory(tmp_path('m2'))
    assert 'Infamy' in m.teach('g', 'Infamy = ค่าหัว')
    t = m.glossary('g')[0]
    assert (t['en'], t['th'], t['category']) == ('Infamy', 'ค่าหัว', 'term')
    m.teach('g', 'พีทพูดหยาบ ใช้ กู/มึง')
    assert 'พีทพูดหยาบ' in m.text('style_th.md')


def test_tm_persists_and_reloads():
    root = tmp_path('m3')
    Memory(root).tm_add([('Back', 'กลับ')], 'g', 'claude-opus-5-5')
    assert Memory(root).tm_get('Back') == 'กลับ'


def test_system_prompt_is_stable_and_has_glossary():
    m = Memory(tmp_path('m4'))
    m.add_terms('g', [{'en': 'Truth Quest', 'th': '', 'category': 'item', 'dnt': True}])
    a, b = m.system_prompt('g', 'Game'), m.system_prompt('g', 'Game')
    assert a == b and 'Truth Quest => Truth Quest' in a and 'keep English' in a
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python tests/run.py test_memory`
Expected: `ModuleNotFoundError: No module named 'gt.memory'`.

- [ ] **Step 3: Implement `gt/memory.py`**
```python
"""Translator memory on disk: style rules, lessons, per-game glossary, translation memory (TM)."""
import json
import re
import threading
from datetime import date
from pathlib import Path

CATEGORIES = ('character', 'location', 'item', 'skill', 'creature', 'ui', 'term', 'other')
MAX_GLOSSARY = 1500
TEACH_TERM = re.compile(r'\s*(.+?)\s*(?:=>|->|→|=)\s*(.+?)\s*$')


class Memory:
    def __init__(self, root):
        self.root = Path(root)
        (self.root / 'glossary').mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._tm = {}
        tm = self.root / 'tm.jsonl'
        if tm.exists():
            for line in tm.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._tm[row['en']] = row['th']  # later rows win

    # --- style rules & lessons (markdown files) -------------------------
    def text(self, name):
        p = self.root / name
        return p.read_text(encoding='utf-8') if p.exists() else ''

    def append(self, name, lines, heading):
        with self._lock, open(self.root / name, 'a', encoding='utf-8') as f:
            f.write(f'\n## {heading} ({date.today().isoformat()})\n' + ''.join(f'- {x}\n' for x in lines))

    # --- glossary --------------------------------------------------------
    def glossary(self, game_id):
        p = self.root / 'glossary' / f'{game_id}.json'
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []

    def add_terms(self, game_id, terms, overwrite=False):
        """terms: [{'en','th', optional category/tone/note/dnt}]. -> number added or changed."""
        with self._lock:
            current = {t['en'].lower(): t for t in self.glossary(game_id)}
            changed = 0
            for t in terms:
                key = t['en'].strip().lower()
                if not key or (key in current and not overwrite):
                    continue
                current[key] = {'en': t['en'].strip(), 'th': t.get('th', '').strip(),
                                'category': t.get('category', 'other'), 'tone': t.get('tone', ''),
                                'note': t.get('note', ''), 'dnt': bool(t.get('dnt', False))}
                changed += 1
            p = self.root / 'glossary' / f'{game_id}.json'
            p.write_text(json.dumps(sorted(current.values(), key=lambda t: t['en'].lower()),
                                    ensure_ascii=False, indent=1), encoding='utf-8')
            return changed

    def teach(self, game_id, text):
        """A tip typed by the user. 'X = Y' (or =>, ->, →) becomes an enforced glossary term,
        anything else becomes a style rule. -> Thai confirmation."""
        m = TEACH_TERM.match(text)
        if m:
            self.add_terms(game_id, [{'en': m.group(1), 'th': m.group(2), 'category': 'term'}], overwrite=True)
            return f'บันทึกคำศัพท์: {m.group(1)} → {m.group(2)}'
        self.append('style_th.md', [text.strip()], 'คำสอนจากผู้ใช้')
        return 'บันทึกเป็นกฎสไตล์แล้ว'

    # --- translation memory ---------------------------------------------
    def tm_get(self, en):
        return self._tm.get(en)

    def tm_add(self, pairs, game_id, model):
        today = date.today().isoformat()
        with self._lock, open(self.root / 'tm.jsonl', 'a', encoding='utf-8') as f:
            for en, th in pairs:
                self._tm[en] = th
                f.write(json.dumps({'en': en, 'th': th, 'game': game_id, 'model': model, 'date': today},
                                   ensure_ascii=False) + '\n')

    # --- prompt ----------------------------------------------------------
    def system_prompt(self, game_id, game_name):
        """Deterministic (no dates, stable order) so prompt caching hits on every batch."""
        lines = []
        for t in self.glossary(game_id)[:MAX_GLOSSARY]:
            extra = ', '.join(x for x in (t['category'] if t['category'] != 'other' else '', t['tone'], t['note'],
                                          'keep English' if t['dnt'] else '') if x)
            lines.append(f"{t['en']} => {t['en'] if t['dnt'] else t['th']}" + (f'  [{extra}]' if extra else ''))
        return (
            f'You translate the video game "{game_name}" from English to Thai for a fan localization mod.\n'
            'Follow the style rules and lessons, use the glossary for every term it covers, and return every id.\n\n'
            f'<style_rules>\n{self.text("style_th.md")}\n</style_rules>\n\n'
            f'<lessons>\n{self.text("lessons.md")}\n</lessons>\n\n'
            f'<glossary game="{game_name}">\n' + '\n'.join(lines) + '\n</glossary>\n\n'
            'Also classify each item "type": dialogue (a spoken line), description (narration, item/skill/place '
            'text, tips), document (letters, notes, books, legal text), ui (menus, buttons, labels, short system '
            'text), other.'
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python tests/run.py test_memory`
Expected: 4 × PASS, `OK`.

- [ ] **Step 5: Write `tools/seed_memory.py`** (one-time seed from Maneater + JIM lessons; refuses to overwrite unless `--force`)
```python
"""Seed memory/ with the lessons from 2026-10-03 (Maneater + Junji Ito Maniac). Run once:
    python tools/seed_memory.py          (python tools/seed_memory.py --force to rebuild)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')
from gt import locres  # noqa: E402
from gt.memory import Memory  # noqa: E402
from gt.ue_pak import Pak  # noqa: E402
from gt.validate import THAI  # noqa: E402

PAKS = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Maneater\Maneater\Content\Paks')
LOC = '../../../Maneater/Content/Localization/Game/en/Game.locres'

STYLE = """# กฎสไตล์การแปลเกมเป็นภาษาไทย

## ห้ามพัง (ตัวตรวจจะปฏิเสธ)
- คงแท็กทุกตัวแบบตรงทุกตัวอักษร: <highlight>, <Highlight>, <HIGHLIGHT>, </>, <k>, <i>, <img id="..."/> ฯลฯ แปลเฉพาะข้อความระหว่างแท็ก จำนวนแท็กต้องเท่าเดิม
- คงตัวแปรทุกตัว: {0}, {Name}, %s, %d, %% และไวยากรณ์ plural ของ UE เช่น {0}|plural(one=X,other=Y) แปลเฉพาะคำ X/Y
- จำนวนการขึ้นบรรทัด (\\r\\n) ต้องเท่าเดิม และช่องว่างหน้า/ท้ายข้อความต้องเหมือนต้นฉบับ
- ตัวเลข หน่วย และค่าสถานะต้องตรง (+23% คงเดิม, 40 meters → 40 เมตร, lb → ปอนด์)

## การตัดบรรทัด
- Unreal ตัดบรรทัดได้เฉพาะที่ช่องว่าง: เว้นวรรคระหว่างวลี/อนุประโยคแบบภาษาไทยปกติ อย่างน้อยทุก ~25–35 ตัวอักษร
- ข้อความ UI สั้นๆ ไม่ต้องเว้นวรรคเพิ่ม

## น้ำเสียง
- แปลให้เป็นธรรมชาติแบบคนไทยพูด ไม่แปลคำต่อคำ มุก/คำเล่นคำ ให้ยังขำในภาษาไทย
- ผู้บรรยายแนวสารคดี: ใช้คำลงท้ายเช่น นะ/ล่ะ/ซะแล้ว ได้
- NPC ชาวบ้าน/โจร/ลูกเรือ: ภาษาพูด หยาบได้ถ้าต้นฉบับหยาบ
- ข้อความ UI: สั้น กระชับ ตรงความหมาย
- ภาษาอังกฤษตัวพิมพ์ใหญ่ทั้งหมด → ภาษาไทยปกติ

## ชื่อเฉพาะ
- ใช้อภิธานศัพท์ของเกมเสมอ
- ชื่อคน/เรือ/ร้าน/สถานที่ที่ไม่มีในอภิธานศัพท์: ทับศัพท์เป็นอักษรไทยอย่างเป็นธรรมชาติ (Cajun Queen → เคจัน ควีน) หรือแปลถ้าเป็นชื่อเชิงบรรยาย (Sunken House → บ้านจมน้ำ)
- ชื่อผลิตภัณฑ์/DLC คงภาษาอังกฤษ (เช่น Truth Quest)

## ไม่ต้องแปล (คืนข้อความเดิมทุกตัวอักษร)
- รายชื่อทีมงานในเครดิต ชื่อบริษัท บรรทัดลิขสิทธิ์ ©
- ข้อความดีบัก/ทดสอบ/placeholder และชื่อตัวแปรภายใน
- ตัวย่อทิศ (NE, SW) และชื่อปุ่ม ([Enter], Numpad)
"""

LESSONS = """# บทเรียนเทคนิค

## Unreal Engine
- ข้อความเกมอยู่ใน <Project>/Content/Localization/Game/<ภาษา>/Game.locres ม็อดไทยทับไฟล์ภาษา en แล้วใส่ใน pak ชื่อลงท้าย _P.pak ในโฟลเดอร์ Content/Paks
- locres v2 (UE4) / v3 (UE5): คง hash เดิม เปลี่ยนเฉพาะข้อความ
- pak v3/v5 รุ่นเก่าโหลดได้ทั้ง UE4.25 และ UE5
- UE5 มักบีบอัด pak หลักแบบ Oodle → แตกเองไม่ได้ ต้องใช้ FModel
- เกมที่มีไฟล์ .sig ต้องติดตั้งตัวข้ามลายเซ็น (dsound.dll + UniversalSigBypasser.asi ใน Binaries/Win64)
- ฟอนต์เกมไม่มีอักษรไทย ต้องทับ .ufont (ไฟล์ TTF ดิบ) ด้วยฟอนต์ไทยที่มีอักษรละตินด้วย (Sarabun/Boon/Pridi) — Noto Sans Thai ไม่มีละติน
- เครื่องนี้ (Core Ultra 258V): เกมเก่าที่มี Denuvo ต้องใส่ Launch Options: cmd /c start "" /affinity F %command%

## เกมที่ทำแล้ว
- Maneater (UE4.25): ม็อดเดิม Ni TouchzZ แปล 2,536/6,655 → เติมครบ 6,324 (2026-10-03) ฟอนต์ Boon + MN WALNUTS
- Junji Ito Maniac (UE5): ม็อด MisterTime แปล 1,225/1,442 ฟอนต์ Pridi ทับทุกฟอนต์ + sig bypass

## ไว้ทำต่อ (ยังไม่ทดสอบ)
- Zero-width space (U+200B) + PyThaiNLP ตัดคำ แทนการเว้นวรรค — ต้องทดสอบว่า UE ตัดบรรทัดที่ ZWSP และฟอนต์ไม่แสดงเป็นกล่อง
- Unity: XUnity.AutoTranslator (ไฟล์ English=ไทย), AssetStudio · RPG Maker/Ren'Py: Translator++ · Ren'Py มีระบบแปลในตัว
"""

CURATED = [
    {'en': 'Grotto', 'th': 'ถ้ำใต้น้ำ', 'category': 'location'},
    {'en': 'Apex Predator', 'th': 'นักล่าเจ้าถิ่น', 'category': 'term'},
    {'en': 'Apex', 'th': 'เอเพ็กซ์', 'category': 'other', 'note': 'ฉลาม/สัตว์เจ้าถิ่นของแต่ละภูมิภาค'},
    {'en': 'Infamy', 'th': 'นักล่าฉลาม', 'category': 'term', 'note': 'ระบบความฉาว/ค่าหัวของฉลาม'},
    {'en': 'Bounty Hunter', 'th': 'นักล่าเงินรางวัล', 'category': 'character'},
    {'en': 'Evolution', 'th': 'วิวัฒนาการ', 'category': 'term'},
    {'en': 'Nutrient Cache', 'th': 'ขุมทรัพย์สารอาหาร', 'category': 'item'},
    {'en': 'Landmark', 'th': 'สถานที่สำคัญ', 'category': 'location'},
    {'en': 'Mutagen', 'th': 'สารกลายพันธุ์', 'category': 'item'},
    {'en': 'Orca', 'th': 'วาฬเพชฌฆาต', 'category': 'creature'},
    {'en': 'bull shark', 'th': 'ฉลามหัวบาตร', 'category': 'creature'},
    {'en': 'Scaly Pete', 'th': 'สเกลลี่ พีท', 'category': 'character', 'tone': 'นักล่าฉลามเคจัน พูดหยาบ ภาษาพูด'},
    {'en': 'Kyle', 'th': 'ไคล์', 'category': 'character'},
    {'en': 'Truth Quest', 'th': '', 'category': 'item', 'dnt': True, 'note': 'ชื่อ DLC'},
    {'en': 'Fawtick Bayou', 'th': 'ลุ่มแม่น้ำฟอว์ทิค', 'category': 'location'},
    {'en': 'Dead Horse Lake', 'th': 'ทะเลสาบเดดฮอร์ส', 'category': 'location'},
    {'en': 'Golden Shores', 'th': 'ชายหาดโกลเด้น', 'category': 'location'},
    {'en': 'Sapphire Bay', 'th': 'อ่าวแซฟไฟร์', 'category': 'location'},
    {'en': 'Caviar Key', 'th': 'คาเวียร์คีย์', 'category': 'location'},
    {'en': 'Prosperity Sands', 'th': 'พรอสเพอริตี้ แซนด์', 'category': 'location'},
    {'en': 'The Gulf', 'th': 'อ่าวกัลฟ์', 'category': 'location'},
    {'en': 'Plover Island', 'th': 'เกาะโพลเวอร์', 'category': 'location'},
    {'en': 'Crawfish Bay', 'th': 'อ่าวครอว์ฟิช', 'category': 'location'},
]


def main(force):
    mem_dir = ROOT / 'memory'
    if (mem_dir / 'style_th.md').exists() and not force:
        print('memory/ already seeded - use --force to rebuild')
        return
    for name in ('style_th.md', 'lessons.md', 'tm.jsonl', 'glossary/maneater.json'):
        (mem_dir / name).unlink(missing_ok=True)
    mem = Memory(mem_dir)
    (mem_dir / 'style_th.md').write_text(STYLE, encoding='utf-8')
    (mem_dir / 'lessons.md').write_text(LESSONS, encoding='utf-8')
    base = next(p for p in PAKS.glob('*.pak') if not p.stem.endswith('_P'))
    mod = next(p for p in PAKS.glob('*_P.pak'))
    _, en = locres.read(Pak(base).read(LOC))
    _, th = locres.read(Pak(mod).read(LOC))
    th_by_key = {(e.ns, e.key): e.text for e in th}
    pairs = [(e.text, th_by_key[(e.ns, e.key)]) for e in en
             if THAI.search(th_by_key.get((e.ns, e.key), ''))]
    mem.tm_add(pairs, 'maneater', 'mod+claude-opus-5-5')
    mem.add_terms('maneater', CURATED, overwrite=True)
    added = mem.add_terms('maneater', [{'en': a, 'th': b} for a, b in pairs if len(a) <= 40])
    print(f'seeded: TM {len(pairs)} pairs, glossary {len(CURATED)} curated + {added} from the mod')


if __name__ == '__main__':
    main('--force' in sys.argv)
```

- [ ] **Step 6: Run the seed and check it**

Run: `python tools/seed_memory.py`
Expected: `seeded: TM 6324 pairs, glossary 23 curated + <~900> from the mod` (TM count may differ by a few if the installed mod changed).
Run: `python -c "import json;g=json.load(open('memory/glossary/maneater.json',encoding='utf-8'));print(len(g), [t for t in g if t['en']=='Scaly Pete'])"`
Expected: a count near 950 and the Scaly Pete term with its tone.

- [ ] **Step 7: Commit**
```bash
git add gt/memory.py tests/test_memory.py tools/seed_memory.py
git commit -m "feat: memory store (style, lessons, glossary, TM) and seed tool" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Scan a game folder

**Files:**
- Create: `gt/scan.py`, `tests/test_scan.py`

**Interfaces:**
- Consumes: `gt.ue_pak.Pak/PakError`, `gt.locres.read/LocresError/Entry`.
- Produces: `gt.scan.scan(game_dir, manual_locres=None, ignore_mod=False) -> Scan`; `gt.scan.Scan` dataclass fields `game_dir, project, game_id, paks_dir, base_pak, mod_pak, mode ('mod'|'base'|'manual'), locres_version, entries (list[Entry]), lines (list[Line]), fonts (list[str] relative like 'Engine/Content/...'), mod_files (dict rel->bytes, every non-locres file of the mod pak), signed (bool), notes (list[str] Thai)` and method `.todo() -> list[Line]`; `gt.scan.Line(n, ns, key, en, mod_text, skip)`; `gt.scan.skip_reason(ns, en) -> str` (Thai reason or ''); `gt.scan.engine_of(game_dir) -> 'unreal'|'unity'|'?'`; `gt.scan.ScanError`, `gt.scan.NeedLocres(ScanError)`; constant `LOCRES_EN = 'Content/Localization/Game/en/Game.locres'`.

- [ ] **Step 1: Write the failing tests** — `tests/test_scan.py`:
```python
from gt.scan import NeedLocres, ScanError, engine_of, scan, skip_reason
from gt.ue_pak import Pak
from tests.paths import JIM, JIM_MOD_PAK, MANEATER, need, tmp_path


def test_engine_detection():
    need(MANEATER)
    assert engine_of(MANEATER) == 'unreal'
    d = tmp_path('UnityGame')
    (d / 'Game_Data').mkdir(parents=True)
    (d / 'UnityPlayer.dll').write_bytes(b'')
    assert engine_of(d) == 'unity'


def test_unity_folder_is_explained():
    d = tmp_path('UnityGame2')
    (d / 'Game_Data').mkdir(parents=True)
    (d / 'UnityPlayer.dll').write_bytes(b'')
    try:
        scan(d)
        assert False, 'must refuse'
    except ScanError as e:
        assert 'Unity' in str(e)


def test_maneater_with_installed_mod():
    need(MANEATER)
    s = scan(MANEATER)
    assert s.mode == 'mod' and s.project == 'Maneater' and s.game_id == 'maneater'
    assert len(s.lines) == 6655 and s.locres_version == 2
    assert sum(1 for line in s.lines if line.mod_text) > 6000
    assert any(name.endswith('.ufont') for name in s.mod_files)


def test_maneater_ignoring_mod_translates_from_base():
    need(MANEATER)
    s = scan(MANEATER, ignore_mod=True)
    assert s.mode == 'base' and not any(line.mod_text for line in s.lines)
    assert 5000 < len(s.todo()) < 6655
    assert 'Maneater/Content/UI/Fonts/NotoFont/NotoSans-Regular.ufont' in s.fonts


def test_jim_mod_without_readable_base():
    need(JIM)
    s = scan(JIM)
    assert s.mode == 'mod' and s.signed and s.locres_version == 3 and len(s.lines) == 1442
    assert all(line.en == '' for line in s.lines if line.mod_text)
    assert 'JIM/Content/Art/GUI/GUI_Library/GUI_Font/EN/NotoSerif-Regular.ufont' in s.fonts
    assert any('ลายเซ็น' in n for n in s.notes)


def test_jim_without_mod_needs_manual_locres():
    need(JIM)
    try:
        scan(JIM, ignore_mod=True)
        assert False, 'must ask for a Game.locres'
    except NeedLocres as e:
        assert 'FModel' in str(e)


def test_manual_locres():
    need(JIM, JIM_MOD_PAK)
    path = tmp_path('Game.locres')
    path.write_bytes(Pak(JIM_MOD_PAK).read('../../../JIM/Content/Localization/Game/en/Game.locres'))
    s = scan(JIM, manual_locres=path, ignore_mod=True)
    assert s.mode == 'manual' and len(s.lines) == 1442


def test_not_a_game_folder():
    d = tmp_path('empty-folder')
    d.mkdir()
    try:
        scan(d)
        assert False, 'must refuse'
    except ScanError as e:
        assert 'Unreal' in str(e)


def test_skip_rules():
    assert skip_reason('', '12%') and skip_reason('ManeaterEditor', 'Spawn here')
    assert skip_reason('', 'Blood_Consume_Splash_05')
    assert skip_reason('', '<COMPANYHEADING>X</>\r\n<SUBTITLE>Y</>\r\n<DEFAULT>Z</>')
    assert skip_reason('', 'Find the Grotto') == ''
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python tests/run.py test_scan`
Expected: `ModuleNotFoundError: No module named 'gt.scan'`.

- [ ] **Step 3: Implement `gt/scan.py`**
```python
"""Find a UE game's text: base English locres, an existing Thai mod, fonts, pak signing."""
import re
from dataclasses import dataclass, field
from pathlib import Path

from gt import locres
from gt.ue_pak import Pak, PakError

LOCRES_EN = 'Content/Localization/Game/en/Game.locres'
THAI = re.compile('[\u0E00-\u0E7F]')
EDITOR_NS = {'Engine.BufferVisualizationMaterials', 'StaticMeshLODSettings', 'KismetSchema',
             'EnvQueryGenerator', 'EnvQueryTest', 'UMG', 'GameplayStatics'}
DEV = re.compile(r'placeholder|lorem ipsum|^#|^\(Progress Info|^<Slot Name>$|^test\b', re.I)
IDENT = re.compile(r'[A-Za-z0-9_.\-]+')


class ScanError(Exception):
    """The message is Thai and shown to the user as-is."""


class NeedLocres(ScanError):
    """Base text can't be extracted: the user must pick an extracted Game.locres."""


@dataclass
class Line:
    n: int          # 1-based line number = position in the locres file
    ns: str
    key: str
    en: str         # '' when unknown (mod-only scan with an unreadable base pak)
    mod_text: str   # text from an existing mod that must be kept, '' if none
    skip: str       # Thai reason this line is never sent to Claude, '' if it should be translated


@dataclass
class Scan:
    game_dir: Path
    project: str
    game_id: str
    paks_dir: Path
    base_pak: Path
    mod_pak: Path | None
    mode: str
    locres_version: int
    entries: list
    lines: list
    fonts: list
    mod_files: dict = field(default_factory=dict)
    signed: bool = False
    notes: list = field(default_factory=list)

    def todo(self):
        return [line for line in self.lines if not line.mod_text and not line.skip]


def skip_reason(ns, en):
    if not re.search('[A-Za-z]{2,}', en):
        return 'ไม่มีตัวอักษร'
    if ns in EDITOR_NS or ns.endswith('Editor'):
        return 'ข้อความเอดิเตอร์'
    if '<COMPANYHEADING>' in en or ('<SUBTITLE>' in en and '<DEFAULT>' in en):
        return 'เครดิต'
    if DEV.search(en):
        return 'ดีบัก/placeholder'
    if IDENT.fullmatch(en.strip()) and '_' in en:
        return 'ชื่อตัวแปร'
    return ''


def scan(game_dir, manual_locres=None, ignore_mod=False):
    game_dir = Path(game_dir)
    paks_dir = _find_paks(game_dir)
    project = paks_dir.parent.parent.name
    rel_locres = f'{project}/{LOCRES_EN}'
    paks = sorted(paks_dir.rglob('*.pak'))
    base_paks = [p for p in paks if not p.stem.endswith('_P')]
    if not base_paks:
        raise ScanError('ไม่พบไฟล์ pak หลักของเกมในโฟลเดอร์ Content/Paks')
    base_pak = max(base_paks, key=lambda p: p.stat().st_size)
    try:
        base = Pak(base_pak)
    except PakError as e:
        raise ScanError(f'อ่านไฟล์ {base_pak.name} ไม่ได้: {e}')
    notes = []
    fonts = [_rel(n) for n in base.names() if _is_font(_rel(n))]

    base_version, base_entries, mode = None, None, None
    if manual_locres:
        try:
            base_version, base_entries = locres.read(Path(manual_locres).read_bytes())
        except (OSError, locres.LocresError) as e:
            raise ScanError(f'อ่านไฟล์ locres ที่เลือกไม่ได้: {e}')
        mode = 'manual'
    else:
        name = _find(base, rel_locres)
        if name is None:
            notes.append('ไม่พบ Game.locres ภาษาอังกฤษใน pak หลัก')
        else:
            try:
                base_version, base_entries = locres.read(base.read(name))
                mode = 'base'
            except (PakError, locres.LocresError) as e:
                notes.append(f'แตกข้อความอังกฤษจาก pak หลักไม่ได้ ({e})')

    mod_pak, mod_version, mod_entries, mod_files = (None, None, None, {}) if ignore_mod else _find_mod(paks, rel_locres)
    if mod_pak:
        mode = 'mod'
    if base_entries is None and mod_entries is None:
        raise NeedLocres(f'แตกข้อความจากเกมนี้เองไม่ได้ (pak รุ่นใหม่หรือบีบอัดแบบ Oodle) — '
                         f'ใช้ FModel แตกไฟล์ {rel_locres} แล้วเลือกไฟล์นั้น')
    entries = base_entries or mod_entries
    mod_by_key = {(e.ns, e.key): e.text for e in mod_entries or []}
    lines = []
    for n, e in enumerate(entries, 1):
        m = mod_by_key.get((e.ns, e.key), '')
        keep = bool(THAI.search(m)) or bool(base_entries and m and m != e.text)
        mod_text = m if keep else ''
        en = e.text if base_entries else ('' if mod_text else e.text)
        lines.append(Line(n, e.ns, e.key, en, mod_text, '' if mod_text else skip_reason(e.ns, en)))

    signed = any(paks_dir.glob('*.sig'))
    if signed:
        has_asi = any((paks_dir.parent.parent / 'Binaries' / 'Win64').glob('*.asi'))
        notes.append('เกมนี้ตรวจลายเซ็นไฟล์ (.sig) — ' + (
            'พบตัวข้ามลายเซ็น (.asi) แล้ว' if has_asi else
            'ต้องติดตั้งตัวข้ามลายเซ็น (เช่น dsound.dll + UniversalSigBypasser.asi ใน Binaries/Win64) ม็อดถึงจะโหลด'))
    game_id = re.sub(r'[^a-z0-9]+', '-', project.lower()).strip('-')
    return Scan(game_dir, project, game_id, paks_dir, base_pak, mod_pak, mode, base_version or mod_version,
                entries, lines, fonts, mod_files, signed, notes)


def _find_paks(game_dir):
    if not game_dir.is_dir():
        raise ScanError(f'ไม่พบโฟลเดอร์ {game_dir}')
    if game_dir.name.lower() == 'paks':
        return game_dir
    for cand in [game_dir / 'Content' / 'Paks', *sorted(game_dir.glob('*/Content/Paks'))]:
        if cand.is_dir() and cand.parent.parent.name != 'Engine':
            return cand
    if engine_of(game_dir) == 'unity':
        raise ScanError('เกมนี้สร้างด้วย Unity — รอบนี้รองรับเฉพาะ Unreal Engine (การแปลเกม Unity อยู่ในแผนถัดไป)')
    raise ScanError('ไม่ใช่เกม Unreal Engine (ไม่พบโฟลเดอร์ <ชื่อเกม>/Content/Paks)')


def engine_of(game_dir):
    """'unreal' | 'unity' | '?' judged from the install folder layout."""
    d = Path(game_dir)
    if (d / 'Content' / 'Paks').is_dir() or any(p.is_dir() for p in d.glob('*/Content/Paks')):
        return 'unreal'
    if (d / 'UnityPlayer.dll').exists() or any(d.glob('*_Data/globalgamemanagers')) or any(d.glob('*_Data/data.unity3d')):
        return 'unity'
    return '?'


def _find_mod(paks, rel_locres):
    for p in paks:
        if not p.stem.endswith('_P'):
            continue
        try:
            pak = Pak(p)
            name = _find(pak, rel_locres)
            if name is None:
                continue
            version, entries = locres.read(pak.read(name))
            if any(THAI.search(e.text) for e in entries):
                files = {_rel(x): pak.read(x) for x in pak.names() if x != name}
                return p, version, entries, files
        except (PakError, locres.LocresError, KeyError):
            continue
    return None, None, None, {}


def _find(pak, rel):
    return next((n for n in pak.names() if _rel(n) == rel), None)


def _rel(name):
    while name.startswith('../'):
        name = name[3:]
    return name


def _is_font(rel):
    return rel.endswith('.ufont') or (rel.startswith('Engine/Content/Slate/Fonts/') and rel.endswith(('.ttf', '.otf')))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python tests/run.py test_scan`
Expected: 9 × PASS, `OK` (Maneater scans take a few seconds each).

- [ ] **Step 5: Commit**
```bash
git add gt/scan.py tests/test_scan.py
git commit -m "feat: scan UE game folder (base text, existing mod, fonts, signing)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Claude translator (batching, fix round, resume, cost, lessons)

**Files:**
- Create: `gt/translate.py`, `tests/fake_claude.py`, `tests/test_translate.py`

**Interfaces:**
- Consumes: `gt.validate.problems/is_ok`, `gt.memory.Memory` (`system_prompt`, `glossary`, `text`, `tm_get`), `gt.scan.Scan.todo()`.
- Produces: `gt.translate.MODELS` (`{id: (thai_label, in, out, cache_read, cache_write)}`), `make_batches(items, max_items=150, max_chars=12000)`, `estimate_usd(items, model, system_chars) -> float`, `split_tm(scan, memory) -> (items:list[{'id','en'}], hits:dict[n,str])`, `load_done(work_dir) -> dict[n, {'th','type'}]`, `Translator(api_key, model, memory, game_id, game_name, work_dir, log=print, client=None)` with `.run(items, stop=None, progress=None) -> dict[n, {'th','type'}]`, `.propose_lessons(teachings:list[str], samples:list[tuple]) -> list[{'target','text'}]`, attributes `.cost:float`, `.issues:list[dict]`; `TranslateError` (Thai message).
- Produces (tests): `tests.fake_claude.FakeClient(responder=None)` with `.calls` list of `(payload, kwargs)`, `message(obj, stop_reason='end_turn')`, `thaiify(en) -> str`.

- [ ] **Step 1: Install the SDK and check the parameters this plan relies on**

Run: `python -m pip install --user anthropic`
Run:
```
python -c "import anthropic,inspect;c=anthropic.Anthropic(api_key='x');print(anthropic.__version__);print([p for p in ('output_config','betas','extra_body','system') if p in inspect.signature(c.beta.messages.stream).parameters]);print([p for p in ('output_config','extra_body') if p in inspect.signature(c.messages.stream).parameters])"
```
Expected: a version number, then `['output_config', 'betas', 'extra_body', 'system']` and `['output_config', 'extra_body']`. **If `output_config` is missing from either list**, in Step 4 move `output_config` from `kwargs` into `extra_body` for that call path (`extra_body={'output_config': ..., ...}`) instead.
Also run: `python -c "import httpx2" || python -c "import httpx"` — note which import works (the test file below handles both).

- [ ] **Step 2: Write the fake client** — `tests/fake_claude.py`:
```python
"""A stand-in for anthropic.Anthropic used by tests: no network, deterministic 'Thai'."""
import json
import re
from types import SimpleNamespace

_TOKEN = re.compile(r'(<[^<>]*>|\{[^{}]*\}|%[a-zA-Z%]?)')


def thaiify(en):
    """Fake Thai that keeps markup, placeholders, line breaks and edge spaces."""
    return ''.join(p if _TOKEN.fullmatch(p) else re.sub(r'[A-Za-z]+', 'ไทย', p) for p in _TOKEN.split(en))


def message(obj, stop_reason='end_turn'):
    return SimpleNamespace(
        content=[SimpleNamespace(type='text', text=json.dumps(obj, ensure_ascii=False))],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=2000,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0))


def default_responder(payload, kwargs):
    rows = payload.get('items') or payload.get('fix') or []
    return message({'items': [{'id': r['id'], 'th': thaiify(r['en']), 'type': 'dialogue'} for r in rows]})


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    """responder(payload_dict, kwargs) -> message(...) or an Exception to raise. Calls are recorded."""

    def __init__(self, responder=None):
        self.calls = []
        self.responder = responder or default_responder
        self.messages = SimpleNamespace(stream=self._stream)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        payload = json.loads(kwargs['messages'][0]['content'])
        self.calls.append((payload, kwargs))
        result = self.responder(payload, kwargs)
        if isinstance(result, Exception):
            raise result
        return _Stream(result)
```

- [ ] **Step 3: Write the failing tests** — `tests/test_translate.py`:
```python
import threading

import anthropic

from gt.memory import Memory
from gt.translate import TranslateError, Translator, estimate_usd, make_batches
from tests.fake_claude import FakeClient, message, thaiify
from tests.paths import tmp_path

try:
    import httpx2 as httpx
except ImportError:
    import httpx

ITEMS = [{'id': i, 'en': f'Shark number {i} eats <highlight>{{0}}</> people.'} for i in range(1, 401)]
REQ = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')


def _tr(name, client, model='claude-opus-5-5'):
    mem = Memory(tmp_path(name + '-mem'))
    return Translator('sk-test', model, mem, 'g', 'Game', tmp_path(name + '-work'), log=lambda *_: None, client=client)


def test_batches_respect_limits():
    b = make_batches(ITEMS, max_items=150, max_chars=12000)
    assert sum(map(len, b)) == 400 and all(len(x) <= 150 for x in b)
    assert all(sum(len(i['en']) for i in x) <= 12000 for x in b)


def test_translates_everything_and_resumes_for_free():
    c = FakeClient()
    out = _tr('t1', c).run(ITEMS)
    assert len(out) == 400 and out[1]['th'] == thaiify(ITEMS[0]['en']) and out[1]['type'] == 'dialogue'
    c2 = FakeClient()
    assert len(_tr('t1', c2).run(ITEMS)) == 400 and c2.calls == []


def test_uses_cache_control_and_fallbacks():
    c = FakeClient()
    _tr('t2', c).run(ITEMS[:5])
    payload, kw = c.calls[0]
    assert kw['system'][0]['cache_control'] == {'type': 'ephemeral'}
    assert kw['betas'] == ['server-side-fallback-2026-07-01'] and kw['extra_body'] == {'fallbacks': 'default'}
    assert kw['output_config']['effort'] == 'medium' and kw['model'] == 'claude-opus-5-5'


def test_haiku_has_no_effort_or_fallback():
    c = FakeClient()
    _tr('t3', c, 'claude-haiku-4-5').run(ITEMS[:5])
    kw = c.calls[0][1]
    assert 'effort' not in kw['output_config'] and 'betas' not in kw


def test_missing_and_broken_items_get_one_fix_round():
    def responder(payload, kw):
        if 'items' in payload:  # first answer: drop id 2, break the markup of id 3
            rows = [r for r in payload['items'] if r['id'] != 2]
            return message({'items': [{'id': r['id'], 'th': 'พัง' if r['id'] == 3 else thaiify(r['en']), 'type': 'ui'}
                                      for r in rows]})
        return message({'items': [{'id': r['id'], 'th': thaiify(r['en']), 'type': 'ui'} for r in payload['fix']]})
    c = FakeClient(responder)
    out = _tr('t4', c).run(ITEMS[:5])
    assert len(c.calls) == 2 and {r['id'] for r in c.calls[1][0]['fix']} == {2, 3}
    assert out[2]['th'] == thaiify(ITEMS[1]['en']) and out[3]['th'] == thaiify(ITEMS[2]['en'])


def test_still_broken_after_fix_is_not_saved():
    def responder(payload, kw):
        rows = payload.get('items') or payload.get('fix')
        return message({'items': [{'id': r['id'], 'th': 'พัง', 'type': 'ui'} for r in rows]})
    t = _tr('t5', FakeClient(responder))
    assert t.run(ITEMS[:3]) == {} and len(t.issues) == 3


def test_max_tokens_splits_batch():
    def responder(payload, kw):
        rows = payload['items']
        if len(rows) > 2:
            return message({'items': []}, stop_reason='max_tokens')
        return message({'items': [{'id': r['id'], 'th': thaiify(r['en']), 'type': 'ui'} for r in rows]})
    assert len(_tr('t6', FakeClient(responder)).run(ITEMS[:4])) == 4


def test_refusal_keeps_english_without_fix_round():
    c = FakeClient(lambda p, kw: message({'items': []}, stop_reason='refusal'))
    assert _tr('t7', c).run(ITEMS[:3]) == {} and len(c.calls) == 1


def test_bad_key_raises_thai_error_and_saves_nothing():
    err = anthropic.AuthenticationError('bad key', response=httpx.Response(401, request=REQ), body=None)
    t = _tr('t8', FakeClient(lambda p, kw: err))
    try:
        t.run(ITEMS[:3])
        assert False, 'must raise'
    except TranslateError as e:
        assert 'API key' in str(e)
    assert t.done() == {}


def test_connection_error_is_thai():
    t = _tr('t8b', FakeClient(lambda p, kw: anthropic.APIConnectionError(request=REQ)))
    try:
        t.run(ITEMS[:3])
        assert False, 'must raise'
    except TranslateError as e:
        assert 'อินเทอร์เน็ต' in str(e)


def test_stop_event_halts_before_next_batch():
    stop = threading.Event()
    stop.set()
    c = FakeClient()
    assert _tr('t9', c).run(ITEMS, stop=stop) == {} and c.calls == []


def test_estimate_scales_with_model():
    assert estimate_usd(ITEMS, 'claude-fable-5-1', 20000) > estimate_usd(ITEMS, 'claude-haiku-4-5', 20000) > 0


def test_propose_lessons_returns_items():
    c = FakeClient(lambda p, kw: message({'lessons': [{'target': 'style', 'text': 'เว้นวรรคระหว่างวลี'}]}))
    lessons = _tr('t10', c).propose_lessons(['Infamy = ค่าหัว'], [('Back', 'กลับ')])
    assert lessons == [{'target': 'style', 'text': 'เว้นวรรคระหว่างวลี'}]
    assert c.calls[0][0]['user_teachings'] == ['Infamy = ค่าหัว']
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python tests/run.py test_translate`
Expected: `ModuleNotFoundError: No module named 'gt.translate'`.

- [ ] **Step 5: Implement `gt/translate.py`**
```python
"""Translate lines with Claude: batching, structured output, one fix round, resume, cost, lesson proposals."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from gt.validate import is_ok, problems

MODELS = {  # id: (Thai label, $/1M input, output, cache read, cache write)
    'claude-opus-5-5': ('Claude Opus 5.5 (แนะนำ)', 4.0, 20.0, 0.20, 5.0),
    'claude-sonnet-5-5': ('Claude Sonnet 5.5 (ถูกกว่า)', 2.0, 10.0, 0.20, 2.5),
    'claude-haiku-4-5': ('Claude Haiku 4.5 (ถูกสุด)', 1.0, 5.0, 0.10, 1.25),
    'claude-fable-5-1': ('Claude Fable 5.1 (เก่งสุด แพงสุด)', 10.0, 50.0, 0.25, 12.5),
}
FALLBACK_MODELS = {'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-fable-5-1'}
TYPES = ['dialogue', 'description', 'document', 'ui', 'other']
BATCH_ITEMS, BATCH_CHARS, WORKERS = 150, 12000, 4

ITEMS_SCHEMA = {
    'type': 'object',
    'properties': {'items': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'id': {'type': 'integer'}, 'th': {'type': 'string'},
                       'type': {'type': 'string', 'enum': TYPES}},
        'required': ['id', 'th', 'type'], 'additionalProperties': False}}},
    'required': ['items'], 'additionalProperties': False,
}
LESSONS_SCHEMA = {
    'type': 'object',
    'properties': {'lessons': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'target': {'type': 'string', 'enum': ['style', 'lessons']}, 'text': {'type': 'string'}},
        'required': ['target', 'text'], 'additionalProperties': False}}},
    'required': ['lessons'], 'additionalProperties': False,
}


class TranslateError(Exception):
    """Thai message for the UI."""


def make_batches(items, max_items=BATCH_ITEMS, max_chars=BATCH_CHARS):
    batches, cur, size = [], [], 0
    for it in items:
        if cur and (len(cur) >= max_items or size + len(it['en']) > max_chars):
            batches.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += len(it['en'])
    if cur:
        batches.append(cur)
    return batches


def estimate_usd(items, model, system_chars):
    """Rough pre-run estimate. ponytail: chars/4 tokens in, 0.9 token per English char out (Thai + thinking)."""
    _, p_in, p_out, p_read, p_write = MODELS[model]
    chars = sum(len(i['en']) for i in items)
    n = len(make_batches(items))
    sys_tokens = system_chars / 3
    return (sys_tokens * p_write + sys_tokens * p_read * max(0, n - 1) + chars / 4 * p_in + chars * 0.9 * p_out) / 1e6


def usage_usd(usage, model):
    _, p_in, p_out, p_read, p_write = MODELS[model]
    return ((usage.input_tokens or 0) * p_in + (usage.output_tokens or 0) * p_out
            + (getattr(usage, 'cache_read_input_tokens', 0) or 0) * p_read
            + (getattr(usage, 'cache_creation_input_tokens', 0) or 0) * p_write) / 1e6


def split_tm(scan, memory):
    """-> (items to send to Claude, {line n: Thai} reused from the translation memory)."""
    items, hits = [], {}
    for line in scan.todo():
        th = memory.tm_get(line.en)
        if th:
            hits[line.n] = th
        else:
            items.append({'id': line.n, 'en': line.en})
    return items, hits


def load_done(work_dir):
    p = Path(work_dir) / 'done.jsonl'
    out = {}
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            if line.strip():
                r = json.loads(line)
                out[r['n']] = {'th': r['th'], 'type': r['type']}
    return out


class Translator:
    """Validated results are appended to work_dir/done.jsonl as each batch finishes, so a stopped or
    crashed run resumes without paying twice. Lines that fail validation are not saved (retried next run)."""

    def __init__(self, api_key, model, memory, game_id, game_name, work_dir, log=print, client=None):
        self.model, self.memory, self.game_id, self.game_name = model, memory, game_id, game_name
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.client = client or anthropic.Anthropic(api_key=api_key, max_retries=4)
        self.cost = 0.0
        self.issues = []  # {'en','th','problems'} left after the fix round - input for propose_lessons
        self._lock = threading.Lock()

    def done(self):
        return load_done(self.work_dir)

    def run(self, items, stop=None, progress=None):
        """items: [{'id': n, 'en': str}]. stop: threading.Event. progress(finished, total, cost_usd)."""
        stop = stop or threading.Event()
        done = self.done()
        todo = [it for it in items if it['id'] not in done]
        total, finished = len(items), len(items) - len(todo)
        system = self.memory.system_prompt(self.game_id, self.game_name)
        glossary = self.memory.glossary(self.game_id)

        def work(batch):
            nonlocal finished
            if stop.is_set():
                return
            try:
                res = self._translate_batch(system, glossary, batch)
            except TranslateError:
                stop.set()
                raise
            self._save(res)
            with self._lock:
                done.update(res)
                finished += len(batch)
                if progress:
                    progress(finished, total, self.cost)

        batches = make_batches(todo)
        if batches:
            work(batches[0])  # alone first, so the system prompt is cached before the parallel batches
            with ThreadPoolExecutor(WORKERS) as pool:
                list(pool.map(work, batches[1:]))
        return done

    def propose_lessons(self, teachings, samples):
        """-> [{'target': 'style'|'lessons', 'text': Thai}]. Nothing is saved here - the user picks."""
        system = ('You maintain the long-term memory of a tool that translates video games from English to Thai. '
                  'From this finished job, propose 3-10 short, general lessons written in Thai that will improve '
                  'FUTURE games. target "style" = Thai writing rules; target "lessons" = technical/process facts. '
                  'Skip anything that only applies to one sentence, and do not repeat what memory already says.\n\n'
                  f'<current_style>\n{self.memory.text("style_th.md")}\n</current_style>\n'
                  f'<current_lessons>\n{self.memory.text("lessons.md")}\n</current_lessons>')
        payload = {'game': self.game_name, 'validator_issues': self.issues[:80], 'user_teachings': teachings,
                   'sample_translations': [{'en': a, 'th': b} for a, b in samples[:40]]}
        result, _ = self._request(system, payload, LESSONS_SCHEMA, max_tokens=8000)
        return (result or {}).get('lessons', [])

    # --- internals --------------------------------------------------------
    def _translate_batch(self, system, glossary, batch):
        by_id = {it['id']: it for it in batch}
        result, status = self._request(system, {
            'instruction': 'Translate "en" of every item to Thai. Return every id.',
            'items': [{'id': it['id'], 'en': it['en']} for it in batch]}, ITEMS_SCHEMA)
        if status == 'max_tokens' and len(batch) > 1:
            half = len(batch) // 2
            return {**self._translate_batch(system, glossary, batch[:half]),
                    **self._translate_batch(system, glossary, batch[half:])}
        got = {r['id']: r for r in (result or {}).get('items', []) if r['id'] in by_id}
        if status == 'refusal':
            self.log(f'Claude ปฏิเสธชุดนี้ ({len(batch)} ข้อความ) — คงภาษาอังกฤษไว้')
        else:
            fix = []
            for n, it in by_id.items():
                r = got.get(n)
                if r is None:
                    fix.append({'id': n, 'en': it['en'], 'problems': ['missing from your previous answer']})
                elif problems(it['en'], r['th'], glossary):
                    fix.append({'id': n, 'en': it['en'], 'previous': r['th'],
                                'problems': [m for _, m in problems(it['en'], r['th'], glossary)]})
            if fix:
                fixed, _ = self._request(system, {
                    'instruction': 'Your previous Thai translations of these items had problems. '
                                   'Return a corrected translation for every id in "fix".',
                    'fix': fix}, ITEMS_SCHEMA)
                for r in (fixed or {}).get('items', []):
                    if r['id'] in by_id and is_ok(by_id[r['id']]['en'], r['th'], glossary):
                        got[r['id']] = r
        out = {}
        for n, it in by_id.items():
            r = got.get(n)
            if r and is_ok(it['en'], r['th'], glossary):
                out[n] = {'th': r['th'], 'type': r['type']}
                left = problems(it['en'], r['th'], glossary)
            else:
                left = problems(it['en'], r['th'], glossary) if r else [('hard', 'missing')]
            if left:
                self.issues.append({'en': it['en'], 'th': r['th'] if r else '', 'problems': [m for _, m in left]})
        return out

    def _request(self, system, payload, schema, max_tokens=32000):
        """-> (parsed JSON dict or None, 'ok' | 'refusal' | 'max_tokens')."""
        output_config = {'format': {'type': 'json_schema', 'schema': schema}}
        if self.model != 'claude-haiku-4-5':
            output_config['effort'] = 'medium'
        kwargs = dict(
            model=self.model, max_tokens=max_tokens,
            system=[{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
            messages=[{'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            output_config=output_config,
        )
        try:
            if self.model in FALLBACK_MODELS:
                stream = self.client.beta.messages.stream(
                    betas=['server-side-fallback-2026-07-01'], extra_body={'fallbacks': 'default'}, **kwargs)
            else:
                stream = self.client.messages.stream(**kwargs)
            with stream as s:
                msg = s.get_final_message()
        except anthropic.AuthenticationError:
            raise TranslateError('API key ไม่ถูกต้อง — ตรวจ key แล้วลองใหม่')
        except anthropic.PermissionDeniedError:
            raise TranslateError(f'API key นี้ไม่มีสิทธิ์ใช้รุ่น {self.model}')
        except anthropic.NotFoundError:
            raise TranslateError(f'ไม่พบรุ่น {self.model}')
        except anthropic.RateLimitError:
            raise TranslateError('ถูกจำกัดความถี่การเรียก (rate limit) — รอสักครู่แล้วกดแปลต่อ งานที่เสร็จแล้วถูกบันทึกไว้')
        except anthropic.APIConnectionError:
            raise TranslateError('ต่ออินเทอร์เน็ตไม่ได้ — งานที่เสร็จแล้วถูกบันทึกไว้ กดแปลต่อได้')
        except anthropic.APIStatusError as e:
            raise TranslateError(f'Claude API ผิดพลาด ({e.status_code}) — กดแปลต่อได้ งานที่เสร็จแล้วถูกบันทึกไว้')
        with self._lock:
            self.cost += usage_usd(msg.usage, self.model)
        if msg.stop_reason in ('refusal', 'max_tokens'):
            return None, msg.stop_reason
        text = next(b.text for b in msg.content if b.type == 'text')
        return json.loads(text), 'ok'

    def _save(self, res):
        with self._lock, open(self.work_dir / 'done.jsonl', 'a', encoding='utf-8') as f:
            for n, r in res.items():
                f.write(json.dumps({'n': n, 'th': r['th'], 'type': r['type']}, ensure_ascii=False) + '\n')
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python tests/run.py test_translate`
Expected: 14 × PASS, `OK`.

- [ ] **Step 7: Commit**
```bash
git add gt/translate.py tests/fake_claude.py tests/test_translate.py
git commit -m "feat: Claude translator with fix round, resume, cost and lesson proposals" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Book file + install (pak with fonts) + pipeline test

**Files:**
- Create: `gt/book.py`, `gt/install.py`, `fonts/Sarabun-Regular.ttf`, `fonts/Sarabun-Bold.ttf`, `fonts/OFL.txt`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `gt.scan.Scan`, `gt.locres.Entry/write`, `gt.ue_pak.write_pak/Pak`, `gt.translate.split_tm/Translator`, `tests.fake_claude`.
- Produces: `gt.book.build_lines(scan, results:dict, tm_hits:dict) -> list[dict]` (keys `n, ns, key, en, th, type, group, status` with status `claude|tm|mod|english`), `gt.book.save_book(books_dir, scan, lines, model) -> Path`; `gt.install.install(scan, lines, work_dir, paks_dir=None, font_dir=FONT_DIR) -> Path`, `gt.install.build_locres(scan, lines) -> bytes`, `gt.install.font_files(scan, font_dir=FONT_DIR) -> dict`, `gt.install.pak_name(scan) -> str`, `gt.install.InstallError`, `gt.install.FONT_DIR`.

- [ ] **Step 1: Download the fonts (OFL)**
```powershell
New-Item -ItemType Directory -Force fonts | Out-Null
foreach($f in 'Sarabun-Regular.ttf','Sarabun-Bold.ttf','OFL.txt'){ Invoke-WebRequest "https://raw.githubusercontent.com/google/fonts/main/ofl/sarabun/$f" -OutFile "fonts/$f" -UseBasicParsing }
Get-ChildItem fonts | Select Name,Length
```
Expected: Sarabun-Regular.ttf ≈ 90 KB, Sarabun-Bold.ttf ≈ 90 KB, OFL.txt ≈ 4 KB.

- [ ] **Step 2: Write the failing tests** — `tests/test_pipeline.py`:
```python
import json
import shutil

from gt import locres
from gt.book import build_lines, save_book
from gt.install import FONT_DIR, InstallError, install
from gt.memory import Memory
from gt.scan import scan
from gt.translate import Translator, split_tm
from gt.ue_pak import Pak
from tests.fake_claude import FakeClient, thaiify
from tests.paths import MANEATER, need, tmp_path

_SCAN = {}


def _maneater_base():
    need(MANEATER)
    if 'base' not in _SCAN:
        _SCAN['base'] = scan(MANEATER, ignore_mod=True)
    return _SCAN['base']


def test_maneater_end_to_end_with_fake_claude():
    s = _maneater_base()
    mem = Memory(tmp_path('p-mem'))
    items, hits = split_tm(s, mem)
    assert hits == {} and len(items) == len(s.todo())
    t = Translator('k', 'claude-opus-5-5', mem, s.game_id, s.project, tmp_path('p-work'),
                   log=lambda *_: None, client=FakeClient())
    results = t.run(items[:300])
    lines = build_lines(s, results, hits)
    book = save_book(tmp_path('p-books'), s, lines, 'claude-opus-5-5')
    paks = tmp_path('p-paks')
    paks.mkdir()
    target = install(s, lines, tmp_path('p-out'), paks_dir=paks)
    assert target.name == 'Maneater_Thai_P.pak'
    pak = Pak(target)
    _, entries = locres.read(pak.read('../../../Maneater/Content/Localization/Game/en/Game.locres'))
    first = items[0]['id']
    assert len(entries) == 6655 and entries[first - 1].text == thaiify(items[0]['en'])
    fonts = [n for n in pak.names() if n.endswith('.ufont')]
    regular = (FONT_DIR / 'Sarabun-Regular.ttf').read_bytes()
    assert fonts and pak.read(fonts[0]) in (regular, (FONT_DIR / 'Sarabun-Bold.ttf').read_bytes())
    data = json.loads(book.read_text(encoding='utf-8'))
    assert len(data['lines']) == 6655 and data['lines'][first - 1]['status'] == 'claude'
    assert data['lines'][first - 1]['n'] == first


def test_install_twice_backs_up():
    s = _maneater_base()
    lines = build_lines(s, {}, {})
    paks = tmp_path('b-paks')
    paks.mkdir()
    install(s, lines, tmp_path('b-out'), paks_dir=paks)
    install(s, lines, tmp_path('b-out'), paks_dir=paks)
    assert len(list((tmp_path('b-out') / 'backup').glob('*.pak'))) == 1


def test_install_reports_locked_target():
    s = _maneater_base()
    lines = build_lines(s, {}, {})
    paks = tmp_path('l-paks')
    paks.mkdir()
    original = shutil.copy2

    def locked(src, dst, *a, **k):
        if str(dst).startswith(str(paks)):
            raise PermissionError('in use')
        return original(src, dst, *a, **k)
    shutil.copy2 = locked
    try:
        install(s, lines, tmp_path('l-out'), paks_dir=paks)
        assert False, 'must raise'
    except InstallError as e:
        assert 'ปิดเกม' in str(e)
    finally:
        shutil.copy2 = original
    assert not any(paks.iterdir())
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python tests/run.py test_pipeline`
Expected: `ModuleNotFoundError: No module named 'gt.book'`.

- [ ] **Step 4: Implement `gt/book.py`**
```python
"""Book file = one game's translations line by line. Contract with the bookshelf web app (sub-project 2)."""
import json
from datetime import date
from pathlib import Path


def build_lines(scan, results, tm_hits):
    """results: {n: {'th','type'}} from Claude; tm_hits: {n: th} -> one dict per locres line, in file order."""
    out = []
    for line in scan.lines:
        if line.n in results:
            th, typ, status = results[line.n]['th'], results[line.n]['type'], 'claude'
        elif line.n in tm_hits:
            th, typ, status = tm_hits[line.n], 'other', 'tm'
        elif line.mod_text:
            th, typ, status = line.mod_text, 'other', 'mod'
        else:
            th, typ, status = line.en, 'other', 'english'
        out.append({'n': line.n, 'ns': line.ns, 'key': line.key, 'en': line.en, 'th': th, 'type': typ,
                    'group': line.ns or '(ไม่มีหมวด)', 'status': status})
    return out


def save_book(books_dir, scan, lines, model):
    path = Path(books_dir) / f'{scan.game_id}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    book = {'game': scan.project, 'game_id': scan.game_id, 'engine': f'UE locres v{scan.locres_version}',
            'source': scan.mode, 'model': model, 'updated': date.today().isoformat(), 'lines': lines}
    path.write_text(json.dumps(book, ensure_ascii=False, indent=0), encoding='utf-8')
    return path
```

- [ ] **Step 5: Implement `gt/install.py`**
```python
"""Build the Thai pak (locres + fonts) and copy it into the game, backing up what it replaces."""
import re
import shutil
from datetime import datetime
from pathlib import Path

from gt import locres
from gt.ue_pak import write_pak

FONT_DIR = Path(__file__).resolve().parent.parent / 'fonts'
BOLD = re.compile(r'bold|black|heavy', re.I)


class InstallError(Exception):
    """Thai message for the UI."""


def build_locres(scan, lines):
    entries = [locres.Entry(e.ns_hash, e.ns, e.key_hash, e.key, e.src_hash, line['th'])
               for e, line in zip(scan.entries, lines)]
    return locres.write(scan.locres_version, entries)


def font_files(scan, font_dir=FONT_DIR):
    """The existing mod's own files (fonts) if continuing a mod, else Sarabun over every game font."""
    if scan.mod_files:
        return dict(scan.mod_files)
    regular = (Path(font_dir) / 'Sarabun-Regular.ttf').read_bytes()
    bold = (Path(font_dir) / 'Sarabun-Bold.ttf').read_bytes()
    return {name: bold if BOLD.search(Path(name).name) else regular for name in scan.fonts}


def pak_name(scan):
    return scan.mod_pak.name if scan.mod_pak else f'{scan.project}_Thai_P.pak'


def install(scan, lines, work_dir, paks_dir=None, font_dir=FONT_DIR):
    """Writes the pak into work_dir, backs up the pak it replaces, copies it into the game. -> installed path."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    paks_dir = Path(paks_dir or scan.paks_dir)
    files = font_files(scan, font_dir)
    files[f'{scan.project}/Content/Localization/Game/en/Game.locres'] = build_locres(scan, lines)
    built = work_dir / pak_name(scan)
    write_pak(built, '../../../', files)
    target = paks_dir / built.name
    try:
        if target.exists():
            backup = work_dir / 'backup'
            backup.mkdir(exist_ok=True)
            shutil.copy2(target, backup / f'{target.stem}.{datetime.now():%Y%m%d-%H%M%S}.pak')
        shutil.copy2(built, target)
    except PermissionError:
        raise InstallError('คัดลอกลงโฟลเดอร์เกมไม่ได้ — ปิดเกมก่อนแล้วกดติดตั้งอีกครั้ง')
    return target
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python tests/run.py test_pipeline`
Expected: 3 × PASS, `OK`.
Run the whole suite: `python tests/run.py`
Expected: all PASS (no FAIL), `OK`.

- [ ] **Step 7: Commit**
```bash
git add gt/book.py gt/install.py fonts tests/test_pipeline.py
git commit -m "feat: book file, pak install with Sarabun fonts, end-to-end test" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Installed Steam games list

**Files:**
- Create: `gt/steam.py`, `tests/test_steam.py`

**Interfaces:**
- Consumes: `gt.scan.engine_of`.
- Produces: `gt.steam.steam_root() -> Path` (registry `HKCU\Software\Valve\Steam\SteamPath`, default `C:\Program Files (x86)\Steam`), `gt.steam.installed_games(root=None) -> list[tuple[str, Path, str]]` = `(name, resolved game_dir, engine)` sorted by name, one row per install folder across every library in `steamapps/libraryfolders.vdf`.

- [ ] **Step 1: Write the failing tests** — `tests/test_steam.py`:
```python
from gt.steam import installed_games
from tests.paths import JIM, MANEATER, need, tmp_path


def test_lists_installed_games_with_engine():
    need(MANEATER, JIM)
    rows = installed_games()
    games = {name: (path, engine) for name, path, engine in rows}
    assert games['Maneater'] == (MANEATER.resolve(), 'unreal')
    assert games['Junji Ito Maniac: An Infinite Gaol'] == (JIM.resolve(), 'unreal')
    assert [name for name, _, _ in rows].count('Maneater') == 1


def test_reads_extra_library_folders():
    root, lib = tmp_path('steam-root'), tmp_path('steam-lib2')
    (root / 'steamapps').mkdir(parents=True)
    game = lib / 'steamapps' / 'common' / 'Foo'
    (game / 'Foo_Data').mkdir(parents=True)
    (game / 'UnityPlayer.dll').write_bytes(b'')
    vdf_path = str(lib).replace('\\', '\\\\')
    (root / 'steamapps' / 'libraryfolders.vdf').write_text(
        '"libraryfolders"\n{\n "1"\n {\n  "path"  "' + vdf_path + '"\n }\n}\n', encoding='utf-8')
    (lib / 'steamapps' / 'appmanifest_1.acf').write_text(
        '"AppState"\n{\n "name" "Foo Game"\n "installdir" "Foo"\n}\n', encoding='utf-8')
    assert installed_games(root) == [('Foo Game', game.resolve(), 'unity')]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python tests/run.py test_steam`
Expected: `ModuleNotFoundError: No module named 'gt.steam'`.

- [ ] **Step 3: Implement `gt/steam.py`**
```python
"""Games installed through Steam, across every Steam library folder."""
import re
import winreg
from pathlib import Path

from gt.scan import engine_of

DEFAULT_ROOT = Path(r'C:\Program Files (x86)\Steam')


def steam_root():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            return Path(winreg.QueryValueEx(key, 'SteamPath')[0])
    except OSError:
        return DEFAULT_ROOT


def installed_games(root=None):
    """-> [(name, game_dir, engine)] sorted by name; engine is 'unreal' | 'unity' | '?'."""
    root = Path(root or steam_root())
    libraries = [root]
    vdf = root / 'steamapps' / 'libraryfolders.vdf'
    if vdf.exists():
        text = vdf.read_text(encoding='utf-8', errors='replace')
        libraries += [Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    games = {}
    for lib in libraries:
        for acf in (lib / 'steamapps').glob('appmanifest_*.acf'):
            text = acf.read_text(encoding='utf-8', errors='replace')
            name = re.search(r'"name"\s+"([^"]+)"', text)
            folder = re.search(r'"installdir"\s+"([^"]+)"', text)
            if name and folder:
                game_dir = (lib / 'steamapps' / 'common' / folder.group(1)).resolve()
                if game_dir.is_dir():
                    games[str(game_dir).lower()] = (name.group(1), game_dir, engine_of(game_dir))
    return sorted(games.values(), key=lambda g: g[0].lower())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python tests/run.py test_steam`
Expected: 2 × PASS, `OK`.

- [ ] **Step 5: Commit**
```bash
git add gt/steam.py tests/test_steam.py
git commit -m "feat: list installed Steam games with their engine" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Desktop window (Tkinter) + launcher + README

**Files:**
- Create: `app.pyw`, `run.bat`, `README.md`, `tests/test_app.py`

**Interfaces:**
- Consumes: everything above — `scan/NeedLocres/ScanError`, `split_tm/estimate_usd/load_done/Translator/TranslateError/MODELS`, `build_lines/save_book`, `install/InstallError`, `Memory`, `installed_games/steam_root`.
- Produces: `App(root)` with `.buttons` dict keyed by Thai button text.

- [ ] **Step 1: Write the failing smoke test** — `tests/test_app.py`:
```python
import importlib.machinery
import importlib.util
import tkinter as tk

from tests.paths import ROOT


def test_window_builds_and_closes():
    loader = importlib.machinery.SourceFileLoader('app', str(ROOT / 'app.pyw'))
    spec = importlib.util.spec_from_loader('app', loader)
    app_mod = importlib.util.module_from_spec(spec)
    loader.exec_module(app_mod)
    root = tk.Tk()
    try:
        app = app_mod.App(root)
        root.update()
        assert set(app.buttons) == {'ลองแปล 10 ข้อความ', 'แปลทั้งหมด', 'หยุด', 'ติดตั้งลงเกม', 'สรุปบทเรียน'}
        assert app.model_id() in app_mod.MODELS
        assert any(label.startswith('Maneater') for label in app.steam_games) or not app.steam_games
    finally:
        root.destroy()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/run.py test_app`
Expected: FAIL with `FileNotFoundError` for `app.pyw`.

- [ ] **Step 3: Implement `app.pyw`**
```python
"""โปรแกรมแปลเกมด้วย Claude — หน้าต่างหลัก. Logic lives in gt/; this file only wires buttons to it."""
import json
import queue
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from gt.book import build_lines, save_book
from gt.install import InstallError, install
from gt.memory import Memory
from gt.scan import NeedLocres, ScanError, scan
from gt.steam import installed_games, steam_root
from gt.translate import MODELS, TranslateError, Translator, estimate_usd, load_done, split_tm

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / 'settings.json'
MODE = {'mod': 'ต่อยอดม็อดไทยที่มีอยู่', 'base': 'ข้อความอังกฤษจากไฟล์เกม', 'manual': 'ไฟล์ Game.locres ที่เลือกเอง'}
ENGINE = {'unreal': 'Unreal', 'unity': 'Unity — ยังไม่รองรับ', '?': 'ไม่ทราบเอนจิน'}


class App:
    def __init__(self, root):
        self.root = root
        root.title('แปลเกมด้วย Claude')
        root.geometry('960x720')
        self.memory = Memory(ROOT / 'memory')
        self.q = queue.Queue()
        self.scan = None
        self.manual_locres = None
        self.lines = []
        self.teachings = []
        self.last_translator = None
        self.stop = threading.Event()
        s = self._load_settings()

        f = ttk.Frame(root, padding=10)
        f.pack(fill='both', expand=True)
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text='API key').grid(row=0, column=0, sticky='w')
        self.key = tk.StringVar(value=s.get('api_key', ''))
        ttk.Entry(f, textvariable=self.key, show='•').grid(row=0, column=1, sticky='ew')
        self.remember = tk.BooleanVar(value=bool(s.get('api_key')))
        ttk.Checkbutton(f, text='จำไว้ในเครื่องนี้', variable=self.remember).grid(row=0, column=2, columnspan=2, sticky='w')

        ttk.Label(f, text='รุ่น Claude').grid(row=1, column=0, sticky='w')
        self.labels = {v[0]: k for k, v in MODELS.items()}
        self.model = tk.StringVar(value=MODELS[s.get('model', 'claude-opus-5-5')][0])
        ttk.Combobox(f, textvariable=self.model, values=list(self.labels), state='readonly').grid(row=1, column=1, sticky='ew')

        ttk.Label(f, text='เกมใน Steam').grid(row=2, column=0, sticky='w')
        self.steam_games = {f'{name}  ({ENGINE[engine]})': str(path) for name, path, engine in installed_games()}
        self.steam_pick = tk.StringVar()
        pick = ttk.Combobox(f, textvariable=self.steam_pick, values=list(self.steam_games), state='readonly')
        pick.grid(row=2, column=1, sticky='ew')
        pick.bind('<<ComboboxSelected>>', lambda _e: self._use_game(self.steam_games[self.steam_pick.get()]))

        ttk.Label(f, text='โฟลเดอร์เกม').grid(row=3, column=0, sticky='w')
        self.game = tk.StringVar(value=s.get('game_dir', ''))
        ttk.Entry(f, textvariable=self.game).grid(row=3, column=1, sticky='ew')
        ttk.Button(f, text='เลือก…', command=self.pick_game).grid(row=3, column=2)
        ttk.Button(f, text='สแกน', command=self.do_scan).grid(row=3, column=3)

        self.summary = tk.StringVar(value='เลือกเกมใน Steam (หรือโฟลเดอร์เกม) แล้วกด "สแกน"')
        ttk.Label(f, textvariable=self.summary, justify='left').grid(row=4, column=0, columnspan=4, sticky='w', pady=6)

        bar = ttk.Frame(f)
        bar.grid(row=5, column=0, columnspan=4, sticky='w')
        self.buttons = {}
        for text, cmd in [('ลองแปล 10 ข้อความ', lambda: self.do_translate(trial=True)),
                          ('แปลทั้งหมด', self.do_translate), ('หยุด', self.stop.set),
                          ('ติดตั้งลงเกม', self.do_install), ('สรุปบทเรียน', self.do_lessons)]:
            b = ttk.Button(bar, text=text, command=cmd)
            b.pack(side='left', padx=2)
            self.buttons[text] = b

        self.progress = ttk.Progressbar(f, maximum=1)
        self.progress.grid(row=6, column=0, columnspan=4, sticky='ew', pady=4)
        self.cost = tk.StringVar(value='ค่าใช้จ่าย: $0.00')
        ttk.Label(f, textvariable=self.cost).grid(row=7, column=0, columnspan=4, sticky='w')

        ttk.Label(f, text='สอนเพิ่ม').grid(row=8, column=0, sticky='w')
        self.tip = tk.StringVar()
        ttk.Entry(f, textvariable=self.tip).grid(row=8, column=1, columnspan=2, sticky='ew')
        ttk.Button(f, text='สอน', command=self.do_teach).grid(row=8, column=3)
        ttk.Label(f, text='เช่น "Infamy = ค่าหัว" (คำศัพท์) หรือ "พีทพูดหยาบ ใช้ กู/มึง" (กฎสไตล์)',
                  foreground='gray').grid(row=9, column=1, columnspan=3, sticky='w')

        self.log_box = ScrolledText(f, height=18)
        self.log_box.grid(row=10, column=0, columnspan=4, sticky='nsew', pady=6)
        f.rowconfigure(10, weight=1)
        root.after(100, self._poll)

    # --- plumbing -----------------------------------------------------------
    def model_id(self):
        return self.labels[self.model.get()]

    def log(self, text):
        self.q.put(('log', text))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == 'log':
                    self.log_box.insert('end', val + '\n')
                    self.log_box.see('end')
                elif kind == 'summary':
                    self.summary.set(val)
                elif kind == 'progress':
                    done, total, cost = val
                    self.progress.configure(maximum=max(total, 1), value=done)
                    self.cost.set(f'ค่าใช้จ่าย: ${cost:.2f}   ({done:,}/{total:,} ข้อความ)')
                elif kind == 'error':
                    messagebox.showerror('ผิดพลาด', val)
                elif kind == 'ask_locres':
                    self._ask_locres()
                elif kind == 'lessons':
                    self._show_lessons(val)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _bg(self, fn):
        def run():
            try:
                fn()
            except (ScanError, TranslateError, InstallError) as e:
                self.q.put(('error', str(e)))
            except Exception as e:  # last resort: never die silently in a worker thread
                self.q.put(('error', f'เกิดข้อผิดพลาดที่ไม่คาดคิด: {e!r}'))
        threading.Thread(target=run, daemon=True).start()

    def _load_settings(self):
        try:
            return json.loads(SETTINGS.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def _save_settings(self):
        s = {'model': self.model_id(), 'game_dir': self.game.get().strip()}
        if self.remember.get():
            s['api_key'] = self.key.get().strip()
        SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding='utf-8')

    # --- actions --------------------------------------------------------------
    def _use_game(self, path):
        self.game.set(path)
        self.manual_locres = None

    def pick_game(self):
        path = filedialog.askdirectory(initialdir=str(steam_root() / 'steamapps' / 'common'), title='เลือกโฟลเดอร์เกม')
        if path:
            self._use_game(path)

    def do_scan(self):
        game, model = self.game.get().strip(), self.model_id()
        self._save_settings()

        def work():
            try:
                s = scan(game, manual_locres=self.manual_locres)
            except NeedLocres as e:
                self.log(str(e))
                self.q.put(('ask_locres', None))
                return
            self.scan = s
            items, hits = split_tm(s, self.memory)
            usd = estimate_usd(items, model, len(self.memory.system_prompt(s.game_id, s.project)))
            skipped = sum(1 for line in s.lines if line.skip)
            modded = sum(1 for line in s.lines if line.mod_text)
            self.q.put(('summary',
                        f'เกม: {s.project}   แหล่งข้อความ: {MODE[s.mode]}\n'
                        f'ทั้งหมด {len(s.lines):,} · แปลแล้ว (ม็อด) {modded:,} · ข้าม {skipped:,} · '
                        f'ใช้คลังคำแปลเดิม {len(hits):,} · ต้องแปล {len(items):,}\n'
                        f'ค่าใช้จ่ายประมาณ ${usd:.2f} ด้วย {MODELS[model][0]}'))
            for note in s.notes:
                self.log('⚠ ' + note)
        self._bg(work)

    def _ask_locres(self):
        path = filedialog.askopenfilename(title='เลือกไฟล์ Game.locres (ภาษา en) ที่แตกด้วย FModel',
                                          filetypes=[('Unreal locres', '*.locres')])
        if path:
            self.manual_locres = path
            self.do_scan()

    def do_translate(self, trial=False):
        if not self.scan:
            return messagebox.showinfo('', 'กดสแกนก่อน')
        key = self.key.get().strip()
        if not key:
            return messagebox.showinfo('', 'ใส่ API key ก่อน')
        self._save_settings()
        self.stop.clear()
        s, model = self.scan, self.model_id()

        def work():
            items, hits = split_tm(s, self.memory)
            if trial:
                work_dir = ROOT / 'work' / s.game_id / 'trial'
                shutil.rmtree(work_dir, ignore_errors=True)
                t = Translator(key, model, self.memory, s.game_id, s.project, work_dir, log=self.log)
                res = t.run(items[:10])
                for it in items[:10]:
                    self.log(f"{it['en']}\n   → {res.get(it['id'], {}).get('th', '(ไม่ผ่านตัวตรวจ)')}")
                self.log(f'ลองแปลเสร็จ ค่าใช้จ่าย ${t.cost:.3f}')
                return
            t = Translator(key, model, self.memory, s.game_id, s.project, ROOT / 'work' / s.game_id / 'main',
                           log=self.log)
            self.last_translator = t
            res = t.run(items, stop=self.stop, progress=lambda d, n, c: self.q.put(('progress', (d, n, c))))
            self._finish(s, model, res, hits)
            if self.stop.is_set():
                self.log('หยุดแล้ว — กด "แปลทั้งหมด" อีกครั้งเพื่อทำต่อ (ส่วนที่เสร็จแล้วไม่เสียเงินซ้ำ)')
            else:
                self.log(f'แปลเสร็จ {len(res):,}/{len(items):,} ข้อความ · ไม่ผ่านตัวตรวจ {len(t.issues)} '
                         f'(คงอังกฤษ จะลองใหม่ตอนกดแปลรอบหน้า) · ค่าใช้จ่ายรอบนี้ ${t.cost:.2f}')
        self._bg(work)

    def _finish(self, s, model, res, hits):
        by_n = {line.n: line for line in s.lines}
        pairs = [(by_n[n].en, r['th']) for n, r in res.items() if r['th'] != by_n[n].en]
        self.memory.tm_add([p for p in pairs if self.memory.tm_get(p[0]) != p[1]], s.game_id, model)
        self.memory.add_terms(s.game_id, [{'en': en, 'th': th} for en, th in pairs if len(en) <= 40])
        self.lines = build_lines(s, res, hits)
        self.log(f'บันทึกหนังสือ: {save_book(ROOT / "books", s, self.lines, model)}')

    def do_install(self):
        if not self.scan:
            return messagebox.showinfo('', 'กดสแกนก่อน')
        s, model = self.scan, self.model_id()

        def work():
            _, hits = split_tm(s, self.memory)
            lines = build_lines(s, load_done(ROOT / 'work' / s.game_id / 'main'), hits)
            target = install(s, lines, ROOT / 'work' / s.game_id)
            save_book(ROOT / 'books', s, lines, model)
            self.log(f'ติดตั้งแล้ว: {target}  (ไฟล์เดิมสำรองไว้ที่ work/{s.game_id}/backup)')
            if s.signed:
                self.log('⚠ เกมนี้ตรวจลายเซ็นไฟล์ — ต้องมีตัวข้ามลายเซ็น ม็อดถึงจะโหลด')
        self._bg(work)

    def do_teach(self):
        tip = self.tip.get().strip()
        if not tip:
            return
        if not self.scan:
            return messagebox.showinfo('', 'สแกนเกมก่อน (คำศัพท์จะถูกเก็บแยกตามเกม)')
        self.log(self.memory.teach(self.scan.game_id, tip))
        self.teachings.append(tip)
        self.tip.set('')

    def do_lessons(self):
        t = self.last_translator
        if not t:
            return messagebox.showinfo('', 'กด "แปลทั้งหมด" ก่อน แล้วค่อยสรุปบทเรียน')
        samples = [(line['en'], line['th']) for line in self.lines if line['status'] == 'claude'][:40]
        self._bg(lambda: self.q.put(('lessons', t.propose_lessons(self.teachings, samples))))

    def _show_lessons(self, lessons):
        if not lessons:
            return messagebox.showinfo('', 'Claude ไม่มีบทเรียนใหม่จากรอบนี้')
        win = tk.Toplevel(self.root)
        win.title('บทเรียนใหม่ — ติ๊กข้อที่ต้องการบันทึก')
        chosen = []
        for lesson in lessons:
            v = tk.BooleanVar(value=False)
            chosen.append((v, lesson))
            label = 'สไตล์' if lesson['target'] == 'style' else 'เทคนิค'
            ttk.Checkbutton(win, text=f"[{label}] {lesson['text']}", variable=v).pack(anchor='w', padx=8, pady=2)

        def save():
            picked = [lesson for v, lesson in chosen if v.get()]
            for target, name in (('style', 'style_th.md'), ('lessons', 'lessons.md')):
                texts = [lesson['text'] for lesson in picked if lesson['target'] == target]
                if texts:
                    self.memory.append(name, texts, f'บทเรียนจาก {self.scan.project}')
            self.log(f'บันทึกบทเรียน {len(picked)} ข้อ')
            win.destroy()
        ttk.Button(win, text='บันทึกข้อที่ติ๊ก', command=save).pack(pady=8)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/run.py test_app`
Expected: PASS (a window flashes briefly), `OK`.

- [ ] **Step 5: Launcher, README, desktop shortcut**

`run.bat`:
```bat
@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw app.pyw) || (python app.pyw)
```

`README.md`:
```markdown
# แปลเกมด้วย Claude

แปลเกม Unreal Engine เป็นภาษาไทยด้วย Claude API แล้วติดตั้งเป็นม็อด `_P.pak`

## ใช้งาน
1. ดับเบิลคลิก `run.bat` (หรือไอคอน "แปลเกม" บนเดสก์ท็อป)
2. ใส่ API key (ติ๊ก "จำไว้ในเครื่องนี้" ถ้าไม่อยากพิมพ์ซ้ำ — key เก็บใน settings.json บนเครื่องนี้เท่านั้น)
3. เลือกโฟลเดอร์เกม → สแกน → ดูจำนวนข้อความและราคาประมาณ
4. "ลองแปล 10 ข้อความ" เพื่อเช็คสไตล์ → "แปลทั้งหมด" → "ติดตั้งลงเกม"
5. หลังแปลเสร็จ กด "สรุปบทเรียน" แล้วติ๊กบทเรียนที่ต้องการให้จำ

## ความจำ (โฟลเดอร์ memory/)
- `style_th.md` กฎสไตล์ · `lessons.md` บทเรียนเทคนิค · `glossary/<เกม>.json` คำศัพท์ · `tm.jsonl` คลังคำแปล
- แก้ไฟล์เหล่านี้ด้วยมือได้ · สร้างใหม่จากศูนย์: `python tools/seed_memory.py --force`

## ทดสอบ
`python tests/run.py`

## ฟอนต์
Sarabun © Cadson Demak — SIL Open Font License (fonts/OFL.txt)
```

Desktop shortcut (PowerShell):
```powershell
$s=(New-Object -ComObject WScript.Shell).CreateShortcut("$env:USERPROFILE\Desktop\แปลเกม.lnk")
$s.TargetPath="C:\Users\watch\game-translator\run.bat"; $s.WorkingDirectory="C:\Users\watch\game-translator"; $s.Save()
```
If the Desktop is redirected to OneDrive, use `[Environment]::GetFolderPath('Desktop')` instead of `$env:USERPROFILE\Desktop`.

- [ ] **Step 6: Run the whole suite**

Run: `python tests/run.py`
Expected: every test PASS (SKIP only if a game folder is missing), `OK`.

- [ ] **Step 7: Commit**
```bash
git add app.pyw run.bat README.md tests/test_app.py
git commit -m "feat: Thai desktop window, launcher and README" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Live checks (needs the user)

**Files:** none (verification only)

- [ ] **Step 1: Real API smoke test (user's key, < $0.10)**

Ask the user to open the app (`run.bat`), paste their API key, choose **Maneater (Unreal)** in "เกมใน Steam", press **สแกน**, then **ลองแปล 10 ข้อความ**.
Expected in the log: 10 lines `English → ไทย`, then `ลองแปลเสร็จ ค่าใช้จ่าย $0.0xx`. If an error dialog appears, read its Thai message and fix the cause (wrong key → re-enter; `output_config` TypeError → apply the Task 6 Step 1 fallback).

- [ ] **Step 2: Install round-trip in the real game**

Press **ติดตั้งลงเกม** (Maneater is in "mod" mode, so the existing mod pak is rebuilt and the old one backed up under `work/maneater/backup/`).
Launch the game with P-cores only and capture the window:
```powershell
$env:SteamAppId='629820'; $env:SteamGameId='629820'
cmd /c "start `"`" /affinity F `"C:\Program Files (x86)\Steam\steamapps\common\Maneater\Maneater.exe`""
```
Expected: the game reaches the title screen with Thai text ("เริ่ม") and Thai loading-screen tips; close the game afterwards.

- [ ] **Step 3: Record the outcome**

Append one line to `memory/lessons.md` via the app's **สอนเพิ่ม** box only if something new was learned; report results to the user.
```

## Self-Review notes (filled in by the plan author)

- Spec coverage: §1 Steam-only + Unity detection → Tasks 5 (engine_of), 8 (Steam list), 9 (picker); §2 UI steps 1-6 → Task 9; §3 structure → Tasks 1-9; §4 data flow → Tasks 5-7; §5 Claude calls → Task 6; §6 memory/learning → Tasks 4, 6 (propose_lessons), 9 (teach, lesson picker); §7 book → Task 7; §8 tests → every task + Task 10; Sarabun fonts → Task 7.
- Types checked: `Line.mod_text` (scan) is used by `book.build_lines` and `Scan.todo`; `load_done` returns `{n: {'th','type'}}`, the same shape `Translator.run` returns and `build_lines` consumes; `install(scan, lines, work_dir, paks_dir=...)` is called with book lines everywhere.
