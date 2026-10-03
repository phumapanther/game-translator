"""A stand-in for anthropic.Anthropic used by tests: no network, deterministic 'Thai'."""
import json
import re
from types import SimpleNamespace

_TOKEN = re.compile(r'(<[^<>]*>|\{[^{}]*\}|%[a-zA-Z%]?)')


def thaiify(en):
    """Fake Thai that keeps markup, placeholders, line breaks and edge spaces."""
    return ''.join(p if _TOKEN.fullmatch(p) else re.sub(r'[A-Za-z]+', 'ไทย', p) for p in _TOKEN.split(en))


def message(obj, stop_reason='end_turn'):
    return SimpleNamespace(
        content=[SimpleNamespace(type='text', text=json.dumps(obj, ensure_ascii=False))],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=2000,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0))


def default_responder(payload, kwargs):
    rows = payload.get('items') or payload.get('fix') or []
    return message({'items': [{'id': r['id'], 'th': thaiify(r['en']), 'type': 'dialogue'} for r in rows]})


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    """responder(payload_dict, kwargs) -> message(...) or an Exception to raise. Calls are recorded."""

    def __init__(self, responder=None):
        self.calls = []
        self.responder = responder or default_responder
        self.messages = SimpleNamespace(stream=self._stream)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        payload = json.loads(kwargs['messages'][0]['content'])
        self.calls.append((payload, kwargs))
        result = self.responder(payload, kwargs)
        if isinstance(result, Exception):
            raise result
        return _Stream(result)
