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
