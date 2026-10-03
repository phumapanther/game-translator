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
