"""Translate lines with Claude: batching, structured output, one fix round, resume, cost, lesson proposals."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

try:  # the transport anthropic is built on (ships with it): a connection drop mid-stream surfaces as its error
    import httpx2 as httpx
except ImportError:
    import httpx

from gt.validate import is_ok, problems

MODELS = {  # id: (Thai label, $/1M input, output, cache read, cache write)
    'claude-opus-5-5': ('Claude Opus 5.5 (แนะนำ)', 4.0, 20.0, 0.20, 5.0),
    'claude-sonnet-5-5': ('Claude Sonnet 5.5 (ถูกกว่า)', 2.0, 10.0, 0.20, 2.5),
    'claude-haiku-4-5': ('Claude Haiku 4.5 (ถูกสุด)', 1.0, 5.0, 0.10, 1.25),
    'claude-fable-5-1': ('Claude Fable 5.1 (เก่งสุด แพงสุด)', 10.0, 50.0, 0.25, 12.5),
}
FALLBACK_MODELS = {'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-fable-5-1'}
TYPES = ['dialogue', 'description', 'document', 'ui', 'other']
BATCH_ITEMS, BATCH_CHARS, WORKERS = 150, 12000, 4

ITEMS_SCHEMA = {
    'type': 'object',
    'properties': {'items': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'id': {'type': 'integer'}, 'th': {'type': 'string'},
                       'type': {'type': 'string', 'enum': TYPES}},
        'required': ['id', 'th', 'type'], 'additionalProperties': False}}},
    'required': ['items'], 'additionalProperties': False,
}
LESSONS_SCHEMA = {
    'type': 'object',
    'properties': {'lessons': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'target': {'type': 'string', 'enum': ['style', 'lessons']}, 'text': {'type': 'string'}},
        'required': ['target', 'text'], 'additionalProperties': False}}},
    'required': ['lessons'], 'additionalProperties': False,
}


class TranslateError(Exception):
    """Thai message for the UI."""


def make_batches(items, max_items=BATCH_ITEMS, max_chars=BATCH_CHARS):
    batches, cur, size = [], [], 0
    for it in items:
        if cur and (len(cur) >= max_items or size + len(it['en']) > max_chars):
            batches.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += len(it['en'])
    if cur:
        batches.append(cur)
    return batches


def estimate_usd(items, model, system_chars):
    """Rough pre-run estimate. ponytail: chars/4 tokens in, 0.9 token per English char out (Thai + thinking)."""
    _, p_in, p_out, p_read, p_write = MODELS[model]
    chars = sum(len(i['en']) for i in items)
    n = len(make_batches(items))
    sys_tokens = system_chars / 3
    return (sys_tokens * p_write + sys_tokens * p_read * max(0, n - 1) + chars / 4 * p_in + chars * 0.9 * p_out) / 1e6


def usage_usd(usage, model):
    _, p_in, p_out, p_read, p_write = MODELS[model]
    return ((usage.input_tokens or 0) * p_in + (usage.output_tokens or 0) * p_out
            + (getattr(usage, 'cache_read_input_tokens', 0) or 0) * p_read
            + (getattr(usage, 'cache_creation_input_tokens', 0) or 0) * p_write) / 1e6


def split_tm(scan, memory):
    """-> (items to send to Claude, {line n: Thai} reused from the translation memory)."""
    items, hits = [], {}
    for line in scan.todo():
        th = memory.tm_get(line.en)
        if th:
            hits[line.n] = th
        else:
            items.append({'id': line.n, 'en': line.en})
    return items, hits


def load_done(work_dir):
    """-> {n: {'th','type','en'}}. A half-written last line (app closed mid-write) is skipped, not fatal."""
    p = Path(work_dir) / 'done.jsonl'
    out = {}
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            out[r['n']] = {'th': r['th'], 'type': r['type'], 'en': r.get('en')}
    return out


class Translator:
    """Validated results are appended to work_dir/done.jsonl as each batch finishes, so a stopped or
    crashed run resumes without paying twice. Lines that fail validation are not saved (retried next run)."""

    def __init__(self, api_key, model, memory, game_id, game_name, work_dir, log=print, client=None):
        self.model, self.memory, self.game_id, self.game_name = model, memory, game_id, game_name
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.client = client or anthropic.Anthropic(api_key=api_key, max_retries=4)
        self.cost = 0.0
        self.issues = []  # {'en','th','problems'} left after the fix round - input for propose_lessons
        self._lock = threading.Lock()

    def done(self):
        return load_done(self.work_dir)

    def run(self, items, stop=None, progress=None):
        """items: [{'id': n, 'en': str}]. stop: threading.Event. progress(finished, total, cost_usd)."""
        stop = stop or threading.Event()
        want = {it['id']: it['en'] for it in items}
        # a saved row only counts for a current line whose English still matches (the game may have been updated)
        done = {n: r for n, r in self.done().items() if n in want and r['en'] in (None, want[n])}
        todo = [it for it in items if it['id'] not in done]
        total, finished = len(items), len(items) - len(todo)
        system = self.memory.system_prompt(self.game_id, self.game_name)
        glossary = self.memory.glossary(self.game_id)

        def work(batch):
            nonlocal finished
            if stop.is_set():
                return
            try:
                res = self._translate_batch(system, glossary, batch)
            except TranslateError:
                stop.set()
                raise
            self._save(res)
            with self._lock:
                done.update(res)
                finished += len(batch)
                if progress:
                    progress(finished, total, self.cost)

        batches = make_batches(todo)
        if batches:
            work(batches[0])  # alone first, so the system prompt is cached before the parallel batches
            with ThreadPoolExecutor(WORKERS) as pool:
                list(pool.map(work, batches[1:]))
        return done

    def propose_lessons(self, teachings, samples):
        """-> [{'target': 'style'|'lessons', 'text': Thai}]. Nothing is saved here - the user picks."""
        system = ('You maintain the long-term memory of a tool that translates video games from English to Thai. '
                  'From this finished job, propose 3-10 short, general lessons written in Thai that will improve '
                  'FUTURE games. target "style" = Thai writing rules; target "lessons" = technical/process facts. '
                  'Skip anything that only applies to one sentence, and do not repeat what memory already says.\n\n'
                  f'<current_style>\n{self.memory.text("style_th.md")}\n</current_style>\n'
                  f'<current_lessons>\n{self.memory.text("lessons.md")}\n</current_lessons>')
        payload = {'game': self.game_name, 'validator_issues': self.issues[:80], 'user_teachings': teachings,
                   'sample_translations': [{'en': a, 'th': b} for a, b in samples[:40]]}
        result, _ = self._request(system, payload, LESSONS_SCHEMA, max_tokens=8000)
        return (result or {}).get('lessons', [])

    # --- internals --------------------------------------------------------
    def _translate_batch(self, system, glossary, batch):
        by_id = {it['id']: it for it in batch}
        result, status = self._request(system, {
            'instruction': 'Translate "en" of every item to Thai. Return every id.',
            'items': [{'id': it['id'], 'en': it['en']} for it in batch]}, ITEMS_SCHEMA)
        if status == 'max_tokens' and len(batch) > 1:
            half = len(batch) // 2
            return {**self._translate_batch(system, glossary, batch[:half]),
                    **self._translate_batch(system, glossary, batch[half:])}
        got = {r['id']: r for r in (result or {}).get('items', []) if r['id'] in by_id}
        if status == 'refusal':
            self.log(f'Claude ปฏิเสธชุดนี้ ({len(batch)} ข้อความ) — คงภาษาอังกฤษไว้')
        else:
            fix = []
            for n, it in by_id.items():
                r = got.get(n)
                if r is None:
                    fix.append({'id': n, 'en': it['en'], 'problems': ['missing from your previous answer']})
                elif problems(it['en'], r['th'], glossary):
                    fix.append({'id': n, 'en': it['en'], 'previous': r['th'],
                                'problems': [m for _, m in problems(it['en'], r['th'], glossary)]})
            if fix:
                fixed, _ = self._request(system, {
                    'instruction': 'Your previous Thai translations of these items had problems. '
                                   'Return a corrected translation for every id in "fix".',
                    'fix': fix}, ITEMS_SCHEMA)
                for r in (fixed or {}).get('items', []):
                    if r['id'] in by_id and is_ok(by_id[r['id']]['en'], r['th'], glossary):
                        got[r['id']] = r
        out = {}
        for n, it in by_id.items():
            r = got.get(n)
            if r and is_ok(it['en'], r['th'], glossary):
                out[n] = {'th': r['th'], 'type': r['type'], 'en': it['en']}
                left = problems(it['en'], r['th'], glossary)
            else:
                left = problems(it['en'], r['th'], glossary) if r else [('hard', 'missing')]
            if left:
                self.issues.append({'en': it['en'], 'th': r['th'] if r else '', 'problems': [m for _, m in left]})
        return out

    def _request(self, system, payload, schema, max_tokens=32000):
        """-> (parsed JSON dict or None, 'ok' | 'refusal' | 'max_tokens')."""
        output_config = {'format': {'type': 'json_schema', 'schema': schema}}
        if self.model != 'claude-haiku-4-5':
            output_config['effort'] = 'medium'
        kwargs = dict(
            model=self.model, max_tokens=max_tokens,
            system=[{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
            messages=[{'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            output_config=output_config,
        )
        try:
            if self.model in FALLBACK_MODELS:
                stream = self.client.beta.messages.stream(
                    betas=['server-side-fallback-2026-07-01'], extra_body={'fallbacks': 'default'}, **kwargs)
            else:
                stream = self.client.messages.stream(**kwargs)
            with stream as s:
                msg = s.get_final_message()
        except anthropic.AuthenticationError:
            raise TranslateError('API key ไม่ถูกต้อง — ตรวจ key แล้วลองใหม่')
        except anthropic.PermissionDeniedError:
            raise TranslateError(f'API key นี้ไม่มีสิทธิ์ใช้รุ่น {self.model}')
        except anthropic.NotFoundError:
            raise TranslateError(f'ไม่พบรุ่น {self.model}')
        except anthropic.RateLimitError:
            raise TranslateError('ถูกจำกัดความถี่การเรียก (rate limit) — รอสักครู่แล้วกดแปลต่อ งานที่เสร็จแล้วถูกบันทึกไว้')
        except (anthropic.APIConnectionError, httpx.TransportError):
            raise TranslateError('ต่ออินเทอร์เน็ตไม่ได้ — งานที่เสร็จแล้วถูกบันทึกไว้ กดแปลต่อได้')
        except anthropic.APIStatusError as e:
            raise TranslateError(f'Claude API ผิดพลาด ({e.status_code}) — กดแปลต่อได้ งานที่เสร็จแล้วถูกบันทึกไว้')
        with self._lock:
            self.cost += usage_usd(msg.usage, self.model)
        if msg.stop_reason in ('refusal', 'max_tokens'):
            return None, msg.stop_reason
        text = next(b.text for b in msg.content if b.type == 'text')
        return json.loads(text), 'ok'

    def _save(self, res):
        with self._lock, open(self.work_dir / 'done.jsonl', 'a', encoding='utf-8') as f:
            for n, r in res.items():
                f.write(json.dumps({'n': n, 'th': r['th'], 'type': r['type'], 'en': r['en']}, ensure_ascii=False) + '\n')
