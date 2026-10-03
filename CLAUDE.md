# Game Translator — โปรแกรมแปลเกม Steam เป็นภาษาไทยด้วย Claude

## เริ่มงานทุกครั้ง
- สเปก: `docs/superpowers/specs/2026-10-03-game-translator-design.md`
- แผน: `docs/superpowers/plans/2026-10-03-game-translator.md`
- ความคืบหน้าของแผน: `.superpowers/sdd/2026-10-03-game-translator/progress.md` (บรรทัด `Task N: complete` = เสร็จแล้ว ห้ามทำซ้ำ)

## โครงสร้าง
- `gt/` logic ทั้งหมด (ue_pak, locres, validate, memory, scan, translate, book, install, steam)
- `app.pyw` หน้าต่าง Tkinter (แค่ต่อปุ่มเข้ากับ gt/)
- `tests/` เทสต์แบบ assert + `tests/run.py` (ไม่ใช้ pytest) ใช้ไฟล์เกมจริงในเครื่องเป็น fixture
- `tools/seed_memory.py` สร้างความจำเริ่มต้นจากงาน Maneater/JIM
- ไม่อยู่ใน git: `memory/` (ความจำ), `books/`, `work/`, `settings.json` (มี API key — ห้าม commit)

## คำสั่ง
- เทสต์ทั้งหมด: `python tests/run.py` · เฉพาะไฟล์: `python tests/run.py test_scan` · เฉพาะข้อ: `python tests/run.py test_scan.test_skip_rules`
- เปิดโปรแกรม: `run.bat` หรือ `python app.pyw`
- สร้างความจำใหม่: `python tools/seed_memory.py --force`
- คำสั่ง Claude Code: `/next` ทำงานถัดไปในแผน · `/test` รันเทสต์ · `/new-feature <สิ่งที่อยากเพิ่ม>` ออกแบบฟีเจอร์ใหม่

## กฎ
- Python 3.12 + `anthropic` เท่านั้น ไม่เพิ่ม dependency อื่น
- รุ่น Claude: `claude-opus-5-5` (ค่าเริ่มต้น), `claude-sonnet-5-5`, `claude-haiku-4-5`, `claude-fable-5-1`
- ข้อความที่ผู้ใช้เห็นเป็นภาษาไทยทั้งหมด
- เกมมาจาก Steam เท่านั้น · รองรับ Unreal Engine · Unity = โปรเจกต์ย่อย 3
- ห้ามทับไฟล์ในโฟลเดอร์เกมโดยไม่สำรอง (`install.py` สำรองให้ที่ `work/<game>/backup/`)
- เกมทดสอบในเครื่อง: Maneater (UE4.25 — ต้องเปิดด้วย affinity F เพราะ Denuvo กับ CPU Core Ultra), Junji Ito Maniac/JIM (UE5, Oodle, ต้องมี sig bypass)

## โปรเจกต์ย่อยถัดไป
- 2: ชั้นหนังสือ — เว็บบนเครื่องสำหรับอ่าน/แก้คำแปลทีละบรรทัดจาก `books/<game>.json`
- 3: Unity — แนวทาง XUnity.AutoTranslator
