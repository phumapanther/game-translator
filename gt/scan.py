"""Find a UE game's text: base English locres, an existing Thai mod, fonts, pak signing."""
import re
from dataclasses import dataclass, field
from pathlib import Path

from gt import locres
from gt.ue_pak import Pak, PakError

LOCRES_EN = 'Content/Localization/Game/en/Game.locres'
THAI = re.compile('[฀-๿]')
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
    base_paks.sort(key=lambda p: p.stat().st_size, reverse=True)
    base_pak = base_paks[0]
    notes, fonts, readable = [], [], []
    for p in base_paks:  # chunked games (pakchunk0/1/...) spread text and fonts over several paks
        try:
            pak = Pak(p)
        except PakError as e:  # e.g. AES-encrypted index: names unknown, the manual Game.locres path still works
            notes.append(f'อ่านไฟล์ {p.name} ไม่ได้: {e}')
            continue
        readable.append(pak)
        fonts += [_rel(n) for n in pak.names() if _is_font(_rel(n))]
    fonts = list(dict.fromkeys(fonts))

    base_version, base_entries, mode = None, None, None
    if manual_locres:
        try:
            base_version, base_entries = locres.read(Path(manual_locres).read_bytes())
        except (OSError, locres.LocresError) as e:
            raise ScanError(f'อ่านไฟล์ locres ที่เลือกไม่ได้: {e}')
        mode = 'manual'
    else:
        holder = next(((pak, name) for pak in readable for name in [_find(pak, rel_locres)] if name), None)
        if holder is None:
            notes.append('ไม่พบ Game.locres ภาษาอังกฤษใน pak หลัก')
        else:
            pak, name = holder
            base_pak = Path(pak.path)
            try:
                base_version, base_entries = locres.read(pak.read(name))
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
