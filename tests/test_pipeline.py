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


def test_build_lines_ignores_results_for_a_different_english():
    s = _maneater_base()
    line = s.todo()[0]
    lines = build_lines(s, {line.n: {'th': 'ผิดบรรทัด', 'type': 'ui', 'en': 'something else'}}, {})
    assert lines[line.n - 1]['status'] == 'english' and lines[line.n - 1]['th'] == line.en


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
