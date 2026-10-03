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
