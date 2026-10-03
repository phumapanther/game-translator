"""Translate a game through Claude Code (your Claude plan, no API key). The /translate-game command drives this.

    python -m gt.cc prepare "<game folder or Steam name>" [--limit N] [--locres FILE]
    python -m gt.cc check   "<game>" <batch number>   (translator agents: problems in their output files)
    python -m gt.cc apply   "<game>"                  (validate + save; writes fix.json for one fix round)
    python -m gt.cc install "<game>"
    python -m gt.cc teach   "<game>" "Infamy = ค่าหัว"
    python -m gt.cc lesson  style|lessons "<text>" "<game name>"

Shares memory/, work/<game>/main/done.jsonl and books/ with the desktop app, so the two can be mixed.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from gt.book import build_lines, save_book
from gt.install import InstallError
from gt.install import install as install_pak
from gt.memory import Memory
from gt.scan import ScanError, scan
from gt.steam import installed_games
from gt.translate import TYPES, append_done, load_done, make_batches, remember, split_tm
from gt.validate import is_ok, problems

ROOT = Path(__file__).resolve().parent.parent
MODEL = 'claude-code'
MODE = {'mod': 'ต่อยอดม็อดไทยที่มีอยู่', 'base': 'ข้อความอังกฤษจากไฟล์เกม', 'manual': 'ไฟล์ Game.locres ที่เลือกเอง'}

OUTPUT_RULES = """

---
# งานของผู้ช่วยแปล (อ่านให้จบก่อนเริ่ม)
- ไฟล์ต้นฉบับ: `batchNN.json` ในโฟลเดอร์นี้ = รายการ `{{"id": int, "en": str}}`
- แปล `en` ทุกรายการเป็นภาษาไทยตามกฎด้านบน แล้วเขียนผลด้วย Write tool เป็น `batchNN.th.part1.json`, `batchNN.th.part2.json`, … (เช่น `batch00.th.part1.json`)
  (ไม่เกิน ~70 รายการต่อไฟล์) รูปแบบ: `{{"items": [{{"id": 12, "th": "...", "type": "dialogue"}}]}}`
- `type` ต้องเป็นหนึ่งใน: {types}
- ต้องมีทุก id ห้ามข้าม ห้ามรวม ข้อความที่ไม่ควรแปล (ชื่อทีมงาน ดีบัก ตัวย่อ) ให้คืนภาษาอังกฤษเดิมทุกตัวอักษร
- แปลเองอย่างเป็นธรรมชาติ ห้ามใช้สคริปต์หรือบริการแปลอัตโนมัติ
- ตรวจงานตัวเองก่อนจบ: `python -m gt.cc check "{game}" NN` (NN = เลขชุด) ต้องไม่เหลือปัญหา ถ้ามีให้แก้ไฟล์แล้วตรวจซ้ำ
"""


def resolve_game(game):
    """A game folder path, or (part of) a Steam game name."""
    p = Path(game)
    if p.is_dir():
        return p
    hits = [(name, path) for name, path, _ in installed_games() if game.lower() in name.lower()]
    if len(hits) == 1:
        return hits[0][1]
    if not hits:
        raise ScanError(f'ไม่พบเกม "{game}" — ใส่ path โฟลเดอร์เกม หรือชื่อเกมที่ติดตั้งใน Steam')
    raise ScanError(f'ชื่อ "{game}" ตรงกับหลายเกม: ' + ', '.join(name for name, _ in hits) + ' — พิมพ์ชื่อให้ชัดขึ้น')


def _ctx(game, root, locres_file=None):
    """-> (scan, memory, work dir, manual locres used). A --locres given to prepare is remembered for later steps."""
    game_dir = resolve_game(game)
    root = Path(root)
    if locres_file is None:
        for source in (root / 'work').glob('*/cc/source.json'):
            info = json.loads(source.read_text(encoding='utf-8'))
            if Path(info['game_dir']) == game_dir.resolve():
                locres_file = info['locres']
    s = scan(game_dir, manual_locres=locres_file)
    return s, Memory(root / 'memory'), root / 'work' / s.game_id, locres_file


def prepare(game, root=ROOT, limit=None, locres_file=None):
    s, mem, work, used_locres = _ctx(game, root, locres_file)
    cc = work / 'cc'
    shutil.rmtree(cc, ignore_errors=True)
    cc.mkdir(parents=True)
    if used_locres:
        (cc / 'source.json').write_text(json.dumps({'game_dir': str(resolve_game(game).resolve()),
                                                    'locres': str(used_locres)}, ensure_ascii=False), encoding='utf-8')
    items, hits = split_tm(s, mem)
    done = load_done(work / 'main')
    items = [it for it in items if not (it['id'] in done and done[it['id']]['en'] in (None, it['en']))]
    items = items[:limit] if limit else items
    batches = make_batches(items)
    for i, batch in enumerate(batches):
        (cc / f'batch{i:02d}.json').write_text(json.dumps(batch, ensure_ascii=False, indent=0), encoding='utf-8')
    brief = mem.system_prompt(s.game_id, s.project) + OUTPUT_RULES.format(types=', '.join(TYPES), game=game)
    (cc / 'BRIEF.md').write_text(brief, encoding='utf-8')
    return {'game': s.project, 'mode': s.mode, 'lines': len(s.lines),
            'mod': sum(1 for line in s.lines if line.mod_text), 'skipped': sum(1 for line in s.lines if line.skip),
            'tm': len(hits), 'todo': len(items), 'batches': len(batches), 'dir': str(cc), 'notes': s.notes}


def check(game, batch_no, root=ROOT):
    """-> Thai problem lines for one batch's output files ([] = all good)."""
    s, mem, work, _ = _ctx(game, root)
    cc = work / 'cc'
    wanted = {it['id']: it['en'] for it in json.loads((cc / f'batch{int(batch_no):02d}.json').read_text(encoding='utf-8'))}
    got, errors = _outputs(cc, f'batch{int(batch_no):02d}')
    glossary = mem.glossary(s.game_id)
    out = list(errors)
    for n, en in wanted.items():
        if n not in got:
            out.append(f'id {n}: ขาดหาย (ยังไม่ได้แปล)')
        else:
            out += [f'id {n}: {msg}' for _, msg in problems(en, got[n]['th'], glossary)]
    out += [f'id {n}: ไม่มีในชุดนี้ (ลบออก)' for n in got if n not in wanted]
    return out


def apply(game, root=ROOT):
    """Validate every output file, save what passes (done.jsonl + TM + glossary + book).
    First run writes fix.json (missing / problem lines) for ONE fix round; agents answer in fix.th*.json."""
    s, mem, work, _ = _ctx(game, root)
    cc = work / 'cc'
    glossary = mem.glossary(s.game_id)
    wanted = {}
    for f in sorted(cc.glob('batch??.json')):
        wanted.update({it['id']: it['en'] for it in json.loads(f.read_text(encoding='utf-8'))})
    got, errors = _outputs(cc, 'batch??')
    fixed, fix_errors = _outputs(cc, 'fix')
    errors += fix_errors
    accepted, fix = {}, []
    for n, en in wanted.items():
        chosen = next((c for c in (fixed.get(n), got.get(n)) if c and is_ok(en, c['th'], glossary)), None)
        if chosen:
            accepted[n] = {'th': chosen['th'], 'type': chosen['type'], 'en': en}
        first = got.get(n)
        if not chosen or (first and problems(en, first['th'], glossary)):
            fix.append({'id': n, 'en': en, 'previous': first['th'] if first else '',
                        'problems': [m for _, m in problems(en, first['th'], glossary)] if first else ['missing']})
    done = load_done(work / 'main')
    (work / 'main').mkdir(parents=True, exist_ok=True)
    append_done(work / 'main', {n: r for n, r in accepted.items()
                                if done.get(n, {}).get('th') != r['th'] or done[n].get('en') != r['en']})
    remember(mem, s, accepted, MODEL)
    _, hits = split_tm(s, mem)
    book = save_book(Path(root) / 'books', s, build_lines(s, load_done(work / 'main'), hits), MODEL)
    fix_file = None
    if fix and not fixed:  # exactly one fix round
        fix_file = cc / 'fix.json'
        fix_file.write_text(json.dumps(fix, ensure_ascii=False, indent=0), encoding='utf-8')
    failed = sorted(n for n in wanted if n not in accepted)
    return {'wanted': len(wanted), 'accepted': len(accepted), 'failed': failed, 'fix_file': fix_file and str(fix_file),
            'errors': errors, 'book': str(book)}


def install_game(game, root=ROOT):
    s, mem, work, _ = _ctx(game, root)
    _, hits = split_tm(s, mem)
    lines = build_lines(s, load_done(work / 'main'), hits)
    target = install_pak(s, lines, work)
    save_book(Path(root) / 'books', s, lines, MODEL)
    return target, s.notes


def _outputs(cc, prefix):
    """Read prefix.th*.json files. Accepts {"items":[...]}, a bare list, or {"id": "th"} -> ({id: {th,type}}, errors)."""
    got, errors = {}, []
    for f in sorted(cc.glob(f'{prefix}.th*.json')):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if isinstance(data, dict) and 'items' in data:
                data = data['items']
            if isinstance(data, dict):
                data = [{'id': k, **(v if isinstance(v, dict) else {'th': v})} for k, v in data.items()]
            for r in data:
                got[int(r['id'])] = {'th': r['th'], 'type': r.get('type') if r.get('type') in TYPES else 'other'}
        except (ValueError, KeyError, TypeError) as e:
            errors.append(f'{f.name}: อ่านไม่ได้ ({e})')
    return got, errors


def main(argv):
    p = argparse.ArgumentParser(prog='python -m gt.cc')
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('prepare')
    a.add_argument('game')
    a.add_argument('--limit', type=int)
    a.add_argument('--locres')
    a = sub.add_parser('check')
    a.add_argument('game')
    a.add_argument('batch', type=int)
    for name in ('apply', 'install'):
        sub.add_parser(name).add_argument('game')
    a = sub.add_parser('teach')
    a.add_argument('game')
    a.add_argument('text')
    a = sub.add_parser('lesson')
    a.add_argument('target', choices=['style', 'lessons'])
    a.add_argument('text')
    a.add_argument('game_name')
    args = p.parse_args(argv)
    try:
        if args.cmd == 'prepare':
            r = prepare(args.game, limit=args.limit, locres_file=args.locres)
            print(f"เกม: {r['game']}   แหล่งข้อความ: {MODE[r['mode']]}\n"
                  f"ทั้งหมด {r['lines']:,} · ม็อดแปลแล้ว {r['mod']:,} · ข้าม {r['skipped']:,} · "
                  f"ใช้คลังคำแปลเดิม {r['tm']:,} · ต้องแปล {r['todo']:,} ({r['batches']} ชุด)\n"
                  f"โฟลเดอร์งาน: {r['dir']}")
            for note in r['notes']:
                print('⚠ ' + note)
        elif args.cmd == 'check':
            problems_ = check(args.game, args.batch)
            print('\n'.join(problems_) if problems_ else 'ผ่านทุกรายการ')
        elif args.cmd == 'apply':
            r = apply(args.game)
            print(f"ผ่านตัวตรวจ {r['accepted']:,}/{r['wanted']:,} · ยังไม่ผ่าน {len(r['failed'])} (คงภาษาอังกฤษ)\n"
                  f"หนังสือ: {r['book']}")
            if r['fix_file']:
                print(f"ต้องแก้ 1 รอบ: {r['fix_file']}  → ตอบใน fix.th.json แล้วรัน apply อีกครั้ง")
            for e in r['errors']:
                print('⚠ ' + e)
        elif args.cmd == 'install':
            target, notes = install_game(args.game)
            print(f'ติดตั้งแล้ว: {target}  (ไฟล์เดิมสำรองไว้ใน work/<เกม>/backup)')
            for note in notes:
                print('⚠ ' + note)
        elif args.cmd == 'teach':
            s, mem, _, _ = _ctx(args.game, ROOT)
            print(mem.teach(s.game_id, args.text))
        elif args.cmd == 'lesson':
            Memory(ROOT / 'memory').append('style_th.md' if args.target == 'style' else 'lessons.md',
                                           [args.text], f'บทเรียนจาก {args.game_name}')
            print('บันทึกบทเรียนแล้ว')
    except (ScanError, InstallError) as e:
        print(f'ผิดพลาด: {e}')
        return 1
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main(sys.argv[1:]))
