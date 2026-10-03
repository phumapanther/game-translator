import threading

import anthropic

from gt.memory import Memory
from gt.translate import TranslateError, Translator, estimate_usd, make_batches
from tests.fake_claude import FakeClient, message, thaiify
from tests.paths import tmp_path

try:
    import httpx2 as httpx
except ImportError:
    import httpx

ITEMS = [{'id': i, 'en': f'Shark number {i} eats <highlight>{{0}}</> people.'} for i in range(1, 401)]
REQ = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')


def _tr(name, client, model='claude-opus-5-5'):
    mem = Memory(tmp_path(name + '-mem'))
    return Translator('sk-test', model, mem, 'g', 'Game', tmp_path(name + '-work'), log=lambda *_: None, client=client)


def test_batches_respect_limits():
    b = make_batches(ITEMS, max_items=150, max_chars=12000)
    assert sum(map(len, b)) == 400 and all(len(x) <= 150 for x in b)
    assert all(sum(len(i['en']) for i in x) <= 12000 for x in b)


def test_translates_everything_and_resumes_for_free():
    c = FakeClient()
    out = _tr('t1', c).run(ITEMS)
    assert len(out) == 400 and out[1]['th'] == thaiify(ITEMS[0]['en']) and out[1]['type'] == 'dialogue'
    c2 = FakeClient()
    assert len(_tr('t1', c2).run(ITEMS)) == 400 and c2.calls == []


def test_uses_cache_control_and_fallbacks():
    c = FakeClient()
    _tr('t2', c).run(ITEMS[:5])
    payload, kw = c.calls[0]
    assert kw['system'][0]['cache_control'] == {'type': 'ephemeral'}
    assert kw['betas'] == ['server-side-fallback-2026-07-01'] and kw['extra_body'] == {'fallbacks': 'default'}
    assert kw['output_config']['effort'] == 'medium' and kw['model'] == 'claude-opus-5-5'


def test_haiku_has_no_effort_or_fallback():
    c = FakeClient()
    _tr('t3', c, 'claude-haiku-4-5').run(ITEMS[:5])
    kw = c.calls[0][1]
    assert 'effort' not in kw['output_config'] and 'betas' not in kw


def test_missing_and_broken_items_get_one_fix_round():
    def responder(payload, kw):
        if 'items' in payload:  # first answer: drop id 2, break the markup of id 3
            rows = [r for r in payload['items'] if r['id'] != 2]
            return message({'items': [{'id': r['id'], 'th': 'พัง' if r['id'] == 3 else thaiify(r['en']), 'type': 'ui'}
                                      for r in rows]})
        return message({'items': [{'id': r['id'], 'th': thaiify(r['en']), 'type': 'ui'} for r in payload['fix']]})
    c = FakeClient(responder)
    out = _tr('t4', c).run(ITEMS[:5])
    assert len(c.calls) == 2 and {r['id'] for r in c.calls[1][0]['fix']} == {2, 3}
    assert out[2]['th'] == thaiify(ITEMS[1]['en']) and out[3]['th'] == thaiify(ITEMS[2]['en'])


def test_still_broken_after_fix_is_not_saved():
    def responder(payload, kw):
        rows = payload.get('items') or payload.get('fix')
        return message({'items': [{'id': r['id'], 'th': 'พัง', 'type': 'ui'} for r in rows]})
    t = _tr('t5', FakeClient(responder))
    assert t.run(ITEMS[:3]) == {} and len(t.issues) == 3


def test_max_tokens_splits_batch():
    def responder(payload, kw):
        rows = payload['items']
        if len(rows) > 2:
            return message({'items': []}, stop_reason='max_tokens')
        return message({'items': [{'id': r['id'], 'th': thaiify(r['en']), 'type': 'ui'} for r in rows]})
    assert len(_tr('t6', FakeClient(responder)).run(ITEMS[:4])) == 4


def test_refusal_keeps_english_without_fix_round():
    c = FakeClient(lambda p, kw: message({'items': []}, stop_reason='refusal'))
    assert _tr('t7', c).run(ITEMS[:3]) == {} and len(c.calls) == 1


def test_bad_key_raises_thai_error_and_saves_nothing():
    err = anthropic.AuthenticationError('bad key', response=httpx.Response(401, request=REQ), body=None)
    t = _tr('t8', FakeClient(lambda p, kw: err))
    try:
        t.run(ITEMS[:3])
        assert False, 'must raise'
    except TranslateError as e:
        assert 'API key' in str(e)
    assert t.done() == {}


def test_connection_error_is_thai():
    t = _tr('t8b', FakeClient(lambda p, kw: anthropic.APIConnectionError(request=REQ)))
    try:
        t.run(ITEMS[:3])
        assert False, 'must raise'
    except TranslateError as e:
        assert 'อินเทอร์เน็ต' in str(e)


def test_stop_event_halts_before_next_batch():
    stop = threading.Event()
    stop.set()
    c = FakeClient()
    assert _tr('t9', c).run(ITEMS, stop=stop) == {} and c.calls == []


def test_estimate_scales_with_model():
    assert estimate_usd(ITEMS, 'claude-fable-5-1', 20000) > estimate_usd(ITEMS, 'claude-haiku-4-5', 20000) > 0


def test_propose_lessons_returns_items():
    c = FakeClient(lambda p, kw: message({'lessons': [{'target': 'style', 'text': 'เว้นวรรคระหว่างวลี'}]}))
    lessons = _tr('t10', c).propose_lessons(['Infamy = ค่าหัว'], [('Back', 'กลับ')])
    assert lessons == [{'target': 'style', 'text': 'เว้นวรรคระหว่างวลี'}]
    assert c.calls[0][0]['user_teachings'] == ['Infamy = ค่าหัว']
