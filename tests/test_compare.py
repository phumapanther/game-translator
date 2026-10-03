from gt import locres
from gt.compare import compare
from gt.ue_pak import write_pak
from tests.paths import MANEATER, MANEATER_MOD_V1, need, tmp_path

LOC = 'G/Content/Localization/Game/en/Game.locres'


def _locres(*texts):
    return locres.write(2, [locres.Entry(1, '', i, f'k{i}', i, t) for i, t in enumerate(texts)])


def test_detects_kept_changed_and_added_lines():
    game = tmp_path('cmp-game')
    paks = game / 'G' / 'Content' / 'Paks'
    paks.mkdir(parents=True)
    write_pak(paks / 'G-Windows.pak', '../../../', {LOC: _locres('Hello', 'Shark', 'Boat')})
    write_pak(paks / 'G_Thai_P.pak', '../../../', {LOC: _locres('สวัสดี', 'ปลา', 'เรือ')})
    original = tmp_path('cmp-original_P.pak')
    write_pak(original, '../../../', {LOC: _locres('สวัสดี', 'ฉลาม', 'Boat')})
    counts, changed = compare(original, game)
    assert counts == {'kept': 1, 'changed': 1, 'added': 1}
    assert changed == [(('', 'k1'), 'ฉลาม', 'ปลา')]


def test_installed_maneater_keeps_every_original_mod_translation():
    need(MANEATER, MANEATER_MOD_V1)
    counts, changed = compare(MANEATER_MOD_V1, MANEATER)
    assert changed == [] and counts['kept'] + counts['spelling_fix'] == 2538 and counts['added'] > 3000
