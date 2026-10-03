"""Check, line by line, that the Thai pak installed in a game kept every translation of an original mod.

    python -m gt.compare <original mod .pak> <game folder>
"""
import re
import sys
from collections import Counter

from gt import locres
from gt.scan import scan
from gt.ue_pak import Pak

THAI = re.compile('[฀-๿]')
SPELLING_FIXES = {'ครีป': 'ครีบ', 'โพลอเวอร์': 'โพลเวอร์'}  # deliberate typo fixes in the Maneater mod (2026-10-03)
LABELS = {
    'kept': 'คำแปลของม็อดเดิม — เหมือนเดิมทุกตัวอักษร',
    'spelling_fix': 'คำแปลของม็อดเดิม — ต่างแค่คำสะกดที่ตั้งใจแก้',
    'changed': 'คำแปลของม็อดเดิม — ถูกเปลี่ยน (ควรตรวจ)',
    'added': 'เดิมเป็นอังกฤษ — แปลเพิ่มแล้ว',
    'still_english': 'เดิมเป็นอังกฤษ — ยังเป็นอังกฤษ',
    'missing': 'บรรทัดที่ไม่มีในเกมแล้ว',
}


def compare(original_mod_pak, game_dir):
    """-> (Counter of LABELS keys, [((ns, key), original, installed)] for original translations that changed)."""
    s = scan(game_dir)
    if not s.mod_pak:
        raise ValueError('ไม่พบม็อดไทยที่ติดตั้งในเกมนี้')
    rel = f'{s.project}/Content/Localization/Game/en/Game.locres'
    pak = Pak(original_mod_pak)
    original = locres.read(pak.read(next(n for n in pak.names() if n.endswith(rel))))[1]
    installed = {(line.ns, line.key): line.mod_text or line.en for line in s.lines}
    english = {(line.ns, line.key): line.en for line in s.lines}
    counts, changed = Counter(), []
    for e in original:
        k = (e.ns, e.key)
        if k not in installed:
            counts['missing'] += 1
            continue
        old, new = e.text, installed[k]
        by_mod = bool(THAI.search(old)) or bool(english[k] and old != english[k])
        if not by_mod:
            counts['added' if THAI.search(new) else 'still_english'] += 1
        elif new == old:
            counts['kept'] += 1
        elif _fix(old) == new:
            counts['spelling_fix'] += 1
        else:
            counts['changed'] += 1
            changed.append((k, old, new))
    return counts, changed


def _fix(text):
    for wrong, right in SPELLING_FIXES.items():
        text = text.replace(wrong, right)
    return text


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    counts, changed = compare(sys.argv[1], sys.argv[2])
    for key, label in LABELS.items():
        if counts[key]:
            print(f'{counts[key]:7,}  {label}')
    for k, old, new in changed[:50]:
        print(f'  {k[0]}/{k[1]}\n    เดิม: {old}\n    ตอนนี้: {new}')
    print('ผล: คำแปลของม็อดเดิมอยู่ครบ' if not changed else f'ผล: มี {len(changed)} บรรทัดที่ต่างจากม็อดเดิม')
