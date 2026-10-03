"""Seed memory/ with the lessons from 2026-10-03 (Maneater + Junji Ito Maniac). Run once:
    python tools/seed_memory.py          (python tools/seed_memory.py --force to rebuild)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')
from gt import locres  # noqa: E402
from gt.memory import Memory  # noqa: E402
from gt.ue_pak import Pak  # noqa: E402
from gt.validate import THAI  # noqa: E402

PAKS = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Maneater\Maneater\Content\Paks')
LOC = '../../../Maneater/Content/Localization/Game/en/Game.locres'

STYLE = """# กฎสไตล์การแปลเกมเป็นภาษาไทย

## ห้ามพัง (ตัวตรวจจะปฏิเสธ)
- คงแท็กทุกตัวแบบตรงทุกตัวอักษร: <highlight>, <Highlight>, <HIGHLIGHT>, </>, <k>, <i>, <img id="..."/> ฯลฯ แปลเฉพาะข้อความระหว่างแท็ก จำนวนแท็กต้องเท่าเดิม
- คงตัวแปรทุกตัว: {0}, {Name}, %s, %d, %% และไวยากรณ์ plural ของ UE เช่น {0}|plural(one=X,other=Y) แปลเฉพาะคำ X/Y
- จำนวนการขึ้นบรรทัด (\\r\\n) ต้องเท่าเดิม และช่องว่างหน้า/ท้ายข้อความต้องเหมือนต้นฉบับ
- ตัวเลข หน่วย และค่าสถานะต้องตรง (+23% คงเดิม, 40 meters → 40 เมตร, lb → ปอนด์)

## การตัดบรรทัด
- Unreal ตัดบรรทัดได้เฉพาะที่ช่องว่าง: เว้นวรรคระหว่างวลี/อนุประโยคแบบภาษาไทยปกติ อย่างน้อยทุก ~25–35 ตัวอักษร
- ข้อความ UI สั้นๆ ไม่ต้องเว้นวรรคเพิ่ม

## น้ำเสียง
- แปลให้เป็นธรรมชาติแบบคนไทยพูด ไม่แปลคำต่อคำ มุก/คำเล่นคำ ให้ยังขำในภาษาไทย
- ผู้บรรยายแนวสารคดี: ใช้คำลงท้ายเช่น นะ/ล่ะ/ซะแล้ว ได้
- NPC ชาวบ้าน/โจร/ลูกเรือ: ภาษาพูด หยาบได้ถ้าต้นฉบับหยาบ
- ข้อความ UI: สั้น กระชับ ตรงความหมาย
- ภาษาอังกฤษตัวพิมพ์ใหญ่ทั้งหมด → ภาษาไทยปกติ

## ชื่อเฉพาะ
- ใช้อภิธานศัพท์ของเกมเสมอ
- ชื่อคน/เรือ/ร้าน/สถานที่ที่ไม่มีในอภิธานศัพท์: ทับศัพท์เป็นอักษรไทยอย่างเป็นธรรมชาติ (Cajun Queen → เคจัน ควีน) หรือแปลถ้าเป็นชื่อเชิงบรรยาย (Sunken House → บ้านจมน้ำ)
- ชื่อผลิตภัณฑ์/DLC คงภาษาอังกฤษ (เช่น Truth Quest)

## ไม่ต้องแปล (คืนข้อความเดิมทุกตัวอักษร)
- รายชื่อทีมงานในเครดิต ชื่อบริษัท บรรทัดลิขสิทธิ์ ©
- ข้อความดีบัก/ทดสอบ/placeholder และชื่อตัวแปรภายใน
- ตัวย่อทิศ (NE, SW) และชื่อปุ่ม ([Enter], Numpad)
"""

LESSONS = """# บทเรียนเทคนิค

## Unreal Engine
- ข้อความเกมอยู่ใน <Project>/Content/Localization/Game/<ภาษา>/Game.locres ม็อดไทยทับไฟล์ภาษา en แล้วใส่ใน pak ชื่อลงท้าย _P.pak ในโฟลเดอร์ Content/Paks
- locres v2 (UE4) / v3 (UE5): คง hash เดิม เปลี่ยนเฉพาะข้อความ
- pak v3/v5 รุ่นเก่าโหลดได้ทั้ง UE4.25 และ UE5
- UE5 มักบีบอัด pak หลักแบบ Oodle → แตกเองไม่ได้ ต้องใช้ FModel
- เกมที่มีไฟล์ .sig ต้องติดตั้งตัวข้ามลายเซ็น (dsound.dll + UniversalSigBypasser.asi ใน Binaries/Win64)
- ฟอนต์เกมไม่มีอักษรไทย ต้องทับ .ufont (ไฟล์ TTF ดิบ) ด้วยฟอนต์ไทยที่มีอักษรละตินด้วย (Sarabun/Boon/Pridi) — Noto Sans Thai ไม่มีละติน
- เครื่องนี้ (Core Ultra 258V): เกมเก่าที่มี Denuvo ต้องใส่ Launch Options: cmd /c start "" /affinity F %command%

## เกมที่ทำแล้ว
- Maneater (UE4.25): ม็อดเดิม Ni TouchzZ แปล 2,536/6,655 → เติมครบ 6,324 (2026-10-03) ฟอนต์ Boon + MN WALNUTS
- Junji Ito Maniac (UE5): ม็อด MisterTime แปล 1,225/1,442 ฟอนต์ Pridi ทับทุกฟอนต์ + sig bypass

## ไว้ทำต่อ (ยังไม่ทดสอบ)
- Zero-width space (U+200B) + PyThaiNLP ตัดคำ แทนการเว้นวรรค — ต้องทดสอบว่า UE ตัดบรรทัดที่ ZWSP และฟอนต์ไม่แสดงเป็นกล่อง
- Unity: XUnity.AutoTranslator (ไฟล์ English=ไทย), AssetStudio · RPG Maker/Ren'Py: Translator++ · Ren'Py มีระบบแปลในตัว
"""

CURATED = [
    {'en': 'Grotto', 'th': 'ถ้ำใต้น้ำ', 'category': 'location'},
    {'en': 'Apex Predator', 'th': 'นักล่าเจ้าถิ่น', 'category': 'term'},
    {'en': 'Apex', 'th': 'เอเพ็กซ์', 'category': 'other', 'note': 'ฉลาม/สัตว์เจ้าถิ่นของแต่ละภูมิภาค'},
    {'en': 'Infamy', 'th': 'นักล่าฉลาม', 'category': 'term', 'note': 'ระบบความฉาว/ค่าหัวของฉลาม'},
    {'en': 'Bounty Hunter', 'th': 'นักล่าเงินรางวัล', 'category': 'character'},
    {'en': 'Evolution', 'th': 'วิวัฒนาการ', 'category': 'term'},
    {'en': 'Nutrient Cache', 'th': 'ขุมทรัพย์สารอาหาร', 'category': 'item'},
    {'en': 'Landmark', 'th': 'สถานที่สำคัญ', 'category': 'location'},
    {'en': 'Mutagen', 'th': 'สารกลายพันธุ์', 'category': 'item'},
    {'en': 'Orca', 'th': 'วาฬเพชฌฆาต', 'category': 'creature'},
    {'en': 'bull shark', 'th': 'ฉลามหัวบาตร', 'category': 'creature'},
    {'en': 'Scaly Pete', 'th': 'สเกลลี่ พีท', 'category': 'character', 'tone': 'นักล่าฉลามเคจัน พูดหยาบ ภาษาพูด'},
    {'en': 'Kyle', 'th': 'ไคล์', 'category': 'character'},
    {'en': 'Truth Quest', 'th': '', 'category': 'item', 'dnt': True, 'note': 'ชื่อ DLC'},
    {'en': 'Fawtick Bayou', 'th': 'ลุ่มแม่น้ำฟอว์ทิค', 'category': 'location'},
    {'en': 'Dead Horse Lake', 'th': 'ทะเลสาบเดดฮอร์ส', 'category': 'location'},
    {'en': 'Golden Shores', 'th': 'ชายหาดโกลเด้น', 'category': 'location'},
    {'en': 'Sapphire Bay', 'th': 'อ่าวแซฟไฟร์', 'category': 'location'},
    {'en': 'Caviar Key', 'th': 'คาเวียร์คีย์', 'category': 'location'},
    {'en': 'Prosperity Sands', 'th': 'พรอสเพอริตี้ แซนด์', 'category': 'location'},
    {'en': 'The Gulf', 'th': 'อ่าวกัลฟ์', 'category': 'location'},
    {'en': 'Plover Island', 'th': 'เกาะโพลเวอร์', 'category': 'location'},
    {'en': 'Crawfish Bay', 'th': 'อ่าวครอว์ฟิช', 'category': 'location'},
]


def main(force):
    mem_dir = ROOT / 'memory'
    if (mem_dir / 'style_th.md').exists() and not force:
        print('memory/ already seeded - use --force to rebuild')
        return
    for name in ('style_th.md', 'lessons.md', 'tm.jsonl', 'glossary/maneater.json'):
        (mem_dir / name).unlink(missing_ok=True)
    mem = Memory(mem_dir)
    (mem_dir / 'style_th.md').write_text(STYLE, encoding='utf-8')
    (mem_dir / 'lessons.md').write_text(LESSONS, encoding='utf-8')
    base = next(p for p in PAKS.glob('*.pak') if not p.stem.endswith('_P'))
    mod = next(p for p in PAKS.glob('*_P.pak'))
    _, en = locres.read(Pak(base).read(LOC))
    _, th = locres.read(Pak(mod).read(LOC))
    th_by_key = {(e.ns, e.key): e.text for e in th}
    pairs = [(e.text, th_by_key[(e.ns, e.key)]) for e in en
             if THAI.search(th_by_key.get((e.ns, e.key), ''))]
    mem.tm_add(pairs, 'maneater', 'mod+claude-opus-5-5')
    mem.add_terms('maneater', CURATED, overwrite=True)
    added = mem.add_terms('maneater', [{'en': a, 'th': b} for a, b in pairs if len(a) <= 40])
    print(f'seeded: TM {len(pairs)} pairs, glossary {len(CURATED)} curated + {added} from the mod')


if __name__ == '__main__':
    main('--force' in sys.argv)
