"""Check a Thai translation against its English source.

hard problems -> the translation is rejected (English is kept);
soft problems -> Claude is asked to fix once, the translation is accepted if they remain.
"""
import re
from collections import Counter

THAI = re.compile('[฀-๿]')
TOKEN = re.compile(r'<[^<>]*>|\{[^{}]*\}|%[a-zA-Z%]?')
LONG_RUN = 45  # Thai chars without a space: Unreal can't wrap such a line


def _tokens(s):
    return Counter(TOKEN.findall(s))


def problems(en, th, glossary=()):
    """-> [(severity, message)]; severity is 'hard' or 'soft'. glossary: term dicts (see gt.memory)."""
    out = []
    if _tokens(en) != _tokens(th):
        out.append(('hard', f'markup/placeholders must be exactly {sorted(_tokens(en).elements())}'))
    if en.count('\n') != th.count('\n'):
        out.append(('hard', f'must have exactly {en.count(chr(10))} line breaks'))
    if (en[:1].isspace(), en[-1:].isspace()) != (th[:1].isspace(), th[-1:].isspace()):
        out.append(('hard', 'leading/trailing spaces must match the English'))
    if th != en and re.search('[A-Za-z]{2,}', en) and not THAI.search(th):
        out.append(('hard', 'no Thai text'))
    for seg in re.split(r'\s+', TOKEN.sub(' ', th)):
        if len(seg) > LONG_RUN and THAI.search(seg):
            out.append(('soft', f'add spaces between phrases: "{seg[:20]}…" runs {len(seg)} chars without a space'))
            break
    for term in glossary:
        if _uses_term(en, term) and not _honours_term(th, term):
            want = term['en'] if term.get('dnt') else term['th']
            out.append(('soft', f'glossary: "{term["en"]}" must be "{want}"'))
    return out


def is_ok(en, th, glossary=()):
    return not any(sev == 'hard' for sev, _ in problems(en, th, glossary))


def _uses_term(en, term):
    if term.get('category', 'other') == 'other' or len(term['en']) < 3:
        return False
    return re.search(r'\b' + re.escape(term['en']) + r'\b', en, re.I) is not None


def _honours_term(th, term):
    want = term['en'] if term.get('dnt') else term['th']
    return want.lower() in th.lower()
