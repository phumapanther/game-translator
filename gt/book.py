"""Book file = one game's translations line by line. Contract with the bookshelf web app (sub-project 2)."""
import json
from datetime import date
from pathlib import Path


def build_lines(scan, results, tm_hits):
    """results: {n: {'th','type'}} from Claude; tm_hits: {n: th} -> one dict per locres line, in file order."""
    out = []
    for line in scan.lines:
        r = results.get(line.n)
        if r and r.get('en') in (None, line.en):  # a result saved for different English is stale: ignore it
            th, typ, status = r['th'], r['type'], 'claude'
        elif line.n in tm_hits:
            th, typ, status = tm_hits[line.n], 'other', 'tm'
        elif line.mod_text:
            th, typ, status = line.mod_text, 'other', 'mod'
        else:
            th, typ, status = line.en, 'other', 'english'
        out.append({'n': line.n, 'ns': line.ns, 'key': line.key, 'en': line.en, 'th': th, 'type': typ,
                    'group': line.ns or '(ไม่มีหมวด)', 'status': status})
    return out


def save_book(books_dir, scan, lines, model):
    path = Path(books_dir) / f'{scan.game_id}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    book = {'game': scan.project, 'game_id': scan.game_id, 'engine': f'UE locres v{scan.locres_version}',
            'source': scan.mode, 'model': model, 'updated': date.today().isoformat(), 'lines': lines}
    path.write_text(json.dumps(book, ensure_ascii=False, indent=0), encoding='utf-8')
    return path
