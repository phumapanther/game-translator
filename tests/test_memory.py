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


def test_system_prompt_keeps_curated_terms_when_glossary_is_capped():
    m = Memory(tmp_path('m5'))
    m.add_terms('g', [{'en': f'Auto term {i:04d}', 'th': 'อัตโนมัติ'} for i in range(1600)])
    m.add_terms('g', [{'en': 'Zebra Pete', 'th': 'ซีบรา พีท', 'category': 'character'}])
    prompt = m.system_prompt('g', 'Game')
    assert 'Zebra Pete => ซีบรา พีท' in prompt and prompt.count('=> อัตโนมัติ') == 1499


def test_system_prompt_is_stable_and_has_glossary():
    m = Memory(tmp_path('m4'))
    m.add_terms('g', [{'en': 'Truth Quest', 'th': '', 'category': 'item', 'dnt': True}])
    a, b = m.system_prompt('g', 'Game'), m.system_prompt('g', 'Game')
    assert a == b and 'Truth Quest => Truth Quest' in a and 'keep English' in a
