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
