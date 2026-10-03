import json
from pathlib import Path

from gt import cc, locres
from gt.memory import Memory
from gt.translate import load_done
from gt.ue_pak import Pak, write_pak
from tests.paths import MANEATER, need, tmp_path

LOC = 'G/Content/Localization/Game/en/Game.locres'
EN = ['Hello there', 'Press {0} to <highlight>BITE</>', 'The shark swims', '42%', 'Find the Grotto']


def _locres_bytes():
    return locres.write(2, [locres.Entry(1, '', i, f'k{i}', i, t) for i, t in enumerate(EN)])


def _game(name, files=None):
    game = tmp_path(name)
    paks = game / 'G' / 'Content' / 'Paks'
    paks.mkdir(parents=True)
    write_pak(paks / 'G-Windows.pak', '../../../', files or {LOC: _locres_bytes()})
    return game


def _write(d, name, rows):
    (d / name).write_text(json.dumps({'items': rows}, ensure_ascii=False), encoding='utf-8')


def test_prepare_writes_batches_and_brief():
    game, root = _game('cc1'), tmp_path('cc1-root')
    info = cc.prepare(str(game), root=root)
    assert info['todo'] == 4 and info['batches'] == 1
    d = Path(info['dir'])
    assert [i['id'] for i in json.loads((d / 'batch00.json').read_text(encoding='utf-8'))] == [1, 2, 3, 5]
    brief = (d / 'BRIEF.md').read_text(encoding='utf-8')
    assert 'batch00.th.part1.json' in brief and 'gt.cc check' in brief


def test_prepare_limit():
    game, root = _game('cc1b'), tmp_path('cc1b-root')
    assert cc.prepare(str(game), root=root, limit=2)['todo'] == 2


def test_check_reports_problems_for_one_batch():
    game, root = _game('cc2'), tmp_path('cc2-root')
    d = Path(cc.prepare(str(game), root=root)['dir'])
    _write(d, 'batch00.th.part1.json', [{'id': 1, 'th': 'สวัสดี', 'type': 'dialogue'},
                                        {'id': 2, 'th': 'พัง', 'type': 'ui'}])
    out = cc.check(str(game), 0, root=root)
    assert any(line.startswith('id 2:') and 'markup' in line for line in out)
    assert any(line.startswith('id 3:') and 'ขาด' in line for line in out)


def test_apply_saves_valid_and_asks_to_fix_the_rest():
    game, root = _game('cc3'), tmp_path('cc3-root')
    d = Path(cc.prepare(str(game), root=root)['dir'])
    _write(d, 'batch00.th.part1.json', [
        {'id': 1, 'th': 'สวัสดี', 'type': 'dialogue'},
        {'id': 2, 'th': 'กดเพื่อกัด', 'type': 'ui'},              # lost {0} and the tag
        {'id': 3, 'th': 'ฉลามว่ายน้ำ', 'type': 'description'}])  # id 5 missing
    r = cc.apply(str(game), root=root)
    assert r['accepted'] == 2 and sorted(r['failed']) == [2, 5]
    assert {f['id'] for f in json.loads((d / 'fix.json').read_text(encoding='utf-8'))} == {2, 5}
    assert Memory(root / 'memory').tm_get('Hello there') == 'สวัสดี'
    assert load_done(root / 'work' / 'g' / 'main')[1]['th'] == 'สวัสดี'


def test_fix_round_answers_win_and_install_ships_them():
    game, root = _game('cc4'), tmp_path('cc4-root')
    d = Path(cc.prepare(str(game), root=root)['dir'])
    _write(d, 'batch00.th.part1.json', [{'id': 1, 'th': 'สวัสดี', 'type': 'dialogue'},
                                        {'id': 2, 'th': 'พัง', 'type': 'ui'}])
    cc.apply(str(game), root=root)
    _write(d, 'fix.th.json', [{'id': 2, 'th': 'กด {0} เพื่อ <highlight>กัด</>', 'type': 'ui'},
                              {'id': 3, 'th': 'ฉลามว่ายน้ำ', 'type': 'description'},
                              {'id': 5, 'th': 'หาถ้ำใต้น้ำ', 'type': 'ui'}])
    r = cc.apply(str(game), root=root)
    assert r['accepted'] == 4 and r['failed'] == [] and r['fix_file'] is None
    target, _ = cc.install_game(str(game), root=root)
    texts = [e.text for e in locres.read(Pak(target).read('../../../' + LOC))[1]]
    assert texts == ['สวัสดี', 'กด {0} เพื่อ <highlight>กัด</>', 'ฉลามว่ายน้ำ', '42%', 'หาถ้ำใต้น้ำ']


def test_manual_locres_is_remembered_between_steps():
    game = _game('cc5', {'G/Content/x.uasset': b'x'})
    loc = tmp_path('cc5.locres')
    loc.write_bytes(_locres_bytes())
    root = tmp_path('cc5-root')
    d = Path(cc.prepare(str(game), root=root, locres_file=str(loc))['dir'])
    _write(d, 'batch00.th.part1.json', [{'id': 1, 'th': 'สวัสดี', 'type': 'dialogue'}])
    assert cc.apply(str(game), root=root)['accepted'] == 1


def test_resolve_game_by_steam_name():
    need(MANEATER)
    assert cc.resolve_game('maneater') == MANEATER.resolve()
