from gt.validate import is_ok, problems


def test_good_translation_passes():
    assert problems('Press {0} to <highlight>BITE</>.\r\n', 'กด {0} เพื่อ <highlight>กัด</>\r\n') == []


def test_missing_tag_is_hard():
    assert not is_ok('<highlight>BITE</>', 'กัด')


def test_missing_placeholder_is_hard():
    assert not is_ok('Kill {0} Apex', 'ฆ่าเอเพ็กซ์')


def test_line_breaks_must_match():
    assert not is_ok('A\r\nB', 'ก ข')


def test_edge_spaces_must_match():
    assert not is_ok(' Wish Sewer Here ', 'ต้องการท่อระบายน้ำที่นี่')


def test_english_kept_on_purpose_is_ok():
    assert is_ok('NE', 'NE') and is_ok('Maneater', 'Maneater')


def test_english_changed_without_thai_is_hard():
    assert not is_ok('Shark', 'Sharky')


def test_long_unspaced_thai_is_soft():
    p = problems('The shark is hurt and needs self-care right now.',
                 'ฉลามได้รับบาดเจ็บและจำเป็นต้องดูแลตนเองเดี๋ยวนี้เลยทันทีทันใดนะ')
    assert p and all(sev == 'soft' for sev, _ in p)


def test_glossary_term_must_be_used():
    g = [{'en': 'Grotto', 'th': 'ถ้ำใต้น้ำ', 'category': 'location'}]
    assert problems('Find the Grotto', 'หาถ้ำใต้น้ำ', g) == []
    assert problems('Find the Grotto', 'หาถ้ำ', g) == [('soft', 'glossary: "Grotto" must be "ถ้ำใต้น้ำ"')]


def test_other_category_is_not_enforced():
    g = [{'en': 'Back', 'th': 'กลับ', 'category': 'other'}]
    assert problems('Go back home', 'ไปบ้าน', g) == []


def test_dnt_term_must_stay_english():
    g = [{'en': 'Truth Quest', 'th': '', 'category': 'item', 'dnt': True}]
    assert problems('Requires Truth Quest', 'ต้องมี Truth Quest', g) == []
    assert problems('Requires Truth Quest', 'ต้องมีภารกิจความจริง', g)[0][0] == 'soft'
