from gt.ue_pak import Pak, PakError, write_pak
from tests.paths import JIM_BASE_PAK, JIM_MOD_PAK, MANEATER_BASE_PAK, MANEATER_MOD_V1, need, tmp_path

LOCRES_MAGIC4 = bytes.fromhex('0E147475')


def test_reads_zlib_v9_base_pak():
    need(MANEATER_BASE_PAK)
    pak = Pak(MANEATER_BASE_PAK)
    assert pak.version == 9 and pak.methods[1] == 'zlib'
    data = pak.read('../../../Maneater/Content/Localization/Game/en/Game.locres')
    assert len(data) == 858117 and data[:4] == LOCRES_MAGIC4


def test_reads_v5_and_v3_mod_paks():
    need(MANEATER_MOD_V1, JIM_MOD_PAK)
    assert Pak(MANEATER_MOD_V1).version == 5
    jim = Pak(JIM_MOD_PAK)
    assert jim.version == 3 and len(jim.names()) == 37
    assert len(jim.read('../../../JIM/Content/Localization/Game/en/Game.locres')) == 159417


def test_v11_lists_names_but_refuses_data():
    need(JIM_BASE_PAK)
    pak = Pak(JIM_BASE_PAK)
    names = pak.names()
    assert pak.version == 11 and len(names) == 4493
    assert '../../../JIM/Content/Art/GUI/GUI_Library/GUI_Font/EN/NotoSerif-Regular.ufont' in names
    try:
        pak.read(names[0])
        assert False, 'v11 data must be refused'
    except PakError:
        pass


def test_write_then_read_back():
    files = {'Maneater/Content/a.txt': b'hello', 'Engine/b.bin': bytes(range(256)) * 10}
    out = tmp_path('roundtrip.pak')
    write_pak(out, '../../../', files)
    pak = Pak(out)
    assert pak.version == 5 and sorted(pak.names()) == sorted('../../../' + n for n in files)
    for name, data in files.items():
        assert pak.read('../../../' + name) == data


def test_rejects_non_pak():
    out = tmp_path('junk.pak')
    out.write_bytes(b'x' * 1000)
    try:
        Pak(out)
        assert False, 'junk must be rejected'
    except PakError:
        pass
