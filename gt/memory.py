"""Translator memory on disk: style rules, lessons, per-game glossary, translation memory (TM)."""
import json
import os
import re
import threading
from datetime import date
from pathlib import Path

CATEGORIES = ('character', 'location', 'item', 'skill', 'creature', 'ui', 'term', 'other')
MAX_GLOSSARY = 1500
TEACH_TERM = re.compile(r'\s*(.+?)\s*(?:=>|->|→|=)\s*(.+?)\s*$')


class Memory:
    def __init__(self, root):
        self.root = Path(root)
        (self.root / 'glossary').mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._tm = {}
        tm = self.root / 'tm.jsonl'
        if tm.exists():
            for line in tm.read_text(encoding='utf-8').splitlines():
                try:
                    row = json.loads(line)
                except ValueError:  # blank, or half-written when the app was closed mid-write
                    continue
                self._tm[row['en']] = row['th']  # later rows win

    # --- style rules & lessons (markdown files) -------------------------
    def text(self, name):
        p = self.root / name
        return p.read_text(encoding='utf-8') if p.exists() else ''

    def append(self, name, lines, heading):
        with self._lock, open(self.root / name, 'a', encoding='utf-8') as f:
            f.write(f'\n## {heading} ({date.today().isoformat()})\n' + ''.join(f'- {x}\n' for x in lines))

    # --- glossary --------------------------------------------------------
    def glossary(self, game_id):
        p = self.root / 'glossary' / f'{game_id}.json'
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []

    def add_terms(self, game_id, terms, overwrite=False):
        """terms: [{'en','th', optional category/tone/note/dnt}]. -> number added or changed."""
        with self._lock:
            current = {t['en'].lower(): t for t in self.glossary(game_id)}
            changed = 0
            for t in terms:
                key = t['en'].strip().lower()
                if not key or (key in current and not overwrite):
                    continue
                current[key] = {'en': t['en'].strip(), 'th': t.get('th', '').strip(),
                                'category': t.get('category', 'other'), 'tone': t.get('tone', ''),
                                'note': t.get('note', ''), 'dnt': bool(t.get('dnt', False))}
                changed += 1
            p = self.root / 'glossary' / f'{game_id}.json'
            tmp = p.with_suffix('.tmp')  # write aside then swap: a write cut short never leaves a broken glossary
            tmp.write_text(json.dumps(sorted(current.values(), key=lambda t: t['en'].lower()),
                                      ensure_ascii=False, indent=1), encoding='utf-8')
            os.replace(tmp, p)
            return changed

    def teach(self, game_id, text):
        """A tip typed by the user. 'X = Y' (or =>, ->, →) becomes an enforced glossary term,
        anything else becomes a style rule. -> Thai confirmation."""
        m = TEACH_TERM.match(text)
        if m:
            self.add_terms(game_id, [{'en': m.group(1), 'th': m.group(2), 'category': 'term'}], overwrite=True)
            return f'บันทึกคำศัพท์: {m.group(1)} → {m.group(2)}'
        self.append('style_th.md', [text.strip()], 'คำสอนจากผู้ใช้')
        return 'บันทึกเป็นกฎสไตล์แล้ว'

    # --- translation memory ---------------------------------------------
    def tm_get(self, en):
        return self._tm.get(en)

    def tm_add(self, pairs, game_id, model):
        today = date.today().isoformat()
        with self._lock, open(self.root / 'tm.jsonl', 'a', encoding='utf-8') as f:
            for en, th in pairs:
                self._tm[en] = th
                f.write(json.dumps({'en': en, 'th': th, 'game': game_id, 'model': model, 'date': today},
                                   ensure_ascii=False) + '\n')

    # --- prompt ----------------------------------------------------------
    def system_prompt(self, game_id, game_name):
        """Deterministic (no dates, stable order) so prompt caching hits on every batch."""
        lines = []
        terms = self.glossary(game_id)
        terms = [t for t in terms if t['category'] != 'other'] + [t for t in terms if t['category'] == 'other']
        for t in terms[:MAX_GLOSSARY]:  # curated/taught terms first so the cap only drops auto-collected ones
            extra = ', '.join(x for x in (t['category'] if t['category'] != 'other' else '', t['tone'], t['note'],
                                          'keep English' if t['dnt'] else '') if x)
            lines.append(f"{t['en']} => {t['en'] if t['dnt'] else t['th']}" + (f'  [{extra}]' if extra else ''))
        return (
            f'You translate the video game "{game_name}" from English to Thai for a fan localization mod.\n'
            'Follow the style rules and lessons, use the glossary for every term it covers, and return every id.\n\n'
            f'<style_rules>\n{self.text("style_th.md")}\n</style_rules>\n\n'
            f'<lessons>\n{self.text("lessons.md")}\n</lessons>\n\n'
            f'<glossary game="{game_name}">\n' + '\n'.join(lines) + '\n</glossary>\n\n'
            'Also classify each item "type": dialogue (a spoken line), description (narration, item/skill/place '
            'text, tips), document (letters, notes, books, legal text), ui (menus, buttons, labels, short system '
            'text), other.'
        )
