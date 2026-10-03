from gt import locres
from gt.ue_pak import Pak
from tests.paths import JIM_MOD_PAK, MANEATER_BASE_PAK, need


def _maneater_en():
    need(MANEATER_BASE_PAK)
    return Pak(MANEATER_BASE_PAK).read('../../../Maneater/Content/Localization/Game/en/Game.locres')


def test_v2_roundtrip_is_byte_identical():
    data = _maneater_en()
    version, entries = locres.read(data)
    assert version == 2 and len(entries) == 6655
    assert locres.write(version, entries) == data


def test_v3_roundtrip_keeps_entries():
    need(JIM_MOD_PAK)
    data = Pak(JIM_MOD_PAK).read('../../../JIM/Content/Localization/Game/en/Game.locres')
    version, entries = locres.read(data)
    assert version == 3 and len(entries) == 1442
    assert locres.read(locres.write(version, entries)) == (version, entries)


def test_thai_text_survives_write():
    version, entries = locres.read(_maneater_en())
    entries[0].text = 'สวัสดี <highlight>ฉลาม</> {0}\r\n'
    again = locres.read(locres.write(version, entries))[1]
    assert again[0].text == entries[0].text and again[1] == entries[1]


def test_rejects_garbage():
    try:
        locres.read(b'not a locres file at all')
        assert False, 'garbage must be rejected'
    except locres.LocresError:
        pass
