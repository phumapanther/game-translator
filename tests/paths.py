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
