import os

import pytest

import claude_api
from config import DEEPSEEK_BASE_URL


def test_detects_deepseek_for_non_anthropic_key():
    provider, url, model = claude_api._detect_provider("sk-test")
    assert provider == "deepseek"
    assert url == DEEPSEEK_BASE_URL
    assert model == os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")


def test_get_ai_config_exposes_safe_metadata():
    cfg = claude_api.get_ai_config()
    assert "provider" in cfg
    assert "model" in cfg
    assert "key_configured" in cfg
    assert "key" not in cfg


def test_deepseek_payload_disables_thinking_by_default(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_THINKING", raising=False)
    payload = claude_api._build_deepseek_payload("system", {"chart": "data"}, "hello", "deepseek-v4-pro")
    assert payload["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in payload


def test_deepseek_payload_can_enable_thinking(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")
    monkeypatch.setenv("DEEPSEEK_REASONING_EFFORT", "high")
    payload = claude_api._build_deepseek_payload("system", {"chart": "data"}, "hello", "deepseek-v4-pro")
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "high"


def test_deepseek_parser_ignores_null_content():
    event = {"choices": [{"delta": {"content": None}, "finish_reason": None}]}
    assert claude_api._parse_deepseek_event(event) == {"type": "empty_delta"}


def test_deepseek_parser_handles_reasoning_content():
    event = {"choices": [{"delta": {"reasoning_content": "thinking"}, "finish_reason": None}]}
    assert claude_api._parse_deepseek_event(event) == {"type": "reasoning_delta", "text": "thinking"}


def test_deepseek_parser_handles_text_content():
    event = {"choices": [{"delta": {"content": "答案"}, "finish_reason": None}]}
    assert claude_api._parse_deepseek_event(event) == {"type": "text_delta", "text": "答案"}


def test_stream_chat_accepts_system_prompt_without_api_key(monkeypatch):
    monkeypatch.setattr(claude_api, "ANTHROPIC_API_KEY", "")
    events = list(claude_api.stream_chat({}, "hello", system_prompt="custom system"))
    assert events
    assert events[0]["type"] == "error"


def test_anthropic_payload_uses_custom_system_prompt():
    payload = claude_api._build_anthropic_payload("custom system", {"chart": "data"}, "hello", "claude-test")
    assert payload["system"].startswith("custom system")
    assert payload["messages"] == [{"role": "user", "content": "hello"}]



def test_stream_chat_yields_error_when_retries_zero(monkeypatch):
    import urllib.error

    import claude_api

    monkeypatch.setattr(claude_api, 'ANTHROPIC_API_KEY', 'sk-fake-99999999')
    monkeypatch.setattr(claude_api, 'API_RETRIES', 0)

    def fake_urlopen(*args, **kwargs):
        raise urllib.error.HTTPError('https://x', 401, 'Unauthorized', None, _fp_for_message())

    def _fp_for_message():
        from io import BytesIO
        return BytesIO(b'invalid api key')

    monkeypatch.setattr(claude_api.urllib.request, 'urlopen', fake_urlopen)

    events = list(claude_api.stream_chat({}, 'hi'))
    assert events, 'expected at least one event when retries=0'
    assert events[-1]['type'] == 'error'
    assert '401' in events[-1]['text']


import json
import urllib.request


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b'{"choices":[{"message":{"content":"A"}}]}'


def test_call_model_messages_sync_sends_temperature(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=180):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _Resp(captured["payload"])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(claude_api, "ANTHROPIC_API_KEY", "sk-test-deepseek-key-1234567890")

    out = claude_api.call_model_messages_sync(
        [{"role": "user", "content": "只回答A"}],
        provider="deepseek",
        model="deepseek-v4-pro",
        system_prompt="system",
        temperature=0.0,
    )

    assert out == "A"
    assert captured["payload"]["temperature"] == 0.0


class _JsonResp:
    def __init__(self, response):
        self.response = response
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.response).encode("utf-8")


def _capture_sync_request(monkeypatch, response=None):
    captured = {}
    response = response or {
        "id": "resp-default",
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": "A"},
        }],
    }

    def fake_urlopen(req, timeout=180):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _JsonResp(response)

    monkeypatch.setattr(claude_api.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        claude_api,
        "ANTHROPIC_API_KEY",
        "sk-test-deepseek-key-1234567890",
    )
    return captured


def test_sync_deepseek_explicitly_disables_thinking(monkeypatch):
    captured = _capture_sync_request(
        monkeypatch,
        response={
            "id": "resp-1",
            "model": "deepseek-v4-flash",
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": "A"},
            }],
        },
    )
    text, meta = claude_api.call_model_messages_sync_with_meta(
        [{"role": "user", "content": "只回答A"}],
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_mode="disabled",
        temperature=0.0,
    )
    assert text == "A"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert meta["requested_model"] == "deepseek-v4-flash"
    assert meta["response_model"] == "deepseek-v4-flash"


def test_sync_call_without_thinking_mode_preserves_payload(monkeypatch):
    captured = _capture_sync_request(monkeypatch)
    claude_api.call_model_messages_sync(
        [{"role": "user", "content": "A"}],
        provider="deepseek",
        model="deepseek-v4-pro",
    )
    assert "thinking" not in captured["payload"]


def test_non_deepseek_rejects_thinking_mode_before_network(monkeypatch):
    called = False

    def fail_urlopen(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not be called")

    monkeypatch.setattr(claude_api.urllib.request, "urlopen", fail_urlopen)
    with pytest.raises(ValueError, match="thinking_mode is only supported for deepseek"):
        claude_api.call_model_messages_sync_with_meta(
            [{"role": "user", "content": "A"}],
            provider="anthropic",
            model="claude-test",
            thinking_mode="disabled",
        )
    assert called is False


def test_response_model_is_missing_not_invented(monkeypatch):
    _capture_sync_request(monkeypatch, response={
        "choices": [{"finish_reason": "stop", "message": {"content": "A"}}],
    })
    _, meta = claude_api.call_model_messages_sync_with_meta(
        [{"role": "user", "content": "A"}],
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_mode="disabled",
    )
    assert meta["requested_model"] == "deepseek-v4-flash"
    assert meta["response_model"] is None
