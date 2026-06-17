import os

import claude_api


def test_detects_deepseek_for_non_anthropic_key():
    provider, url, model = claude_api._detect_provider("sk-test")
    assert provider == "deepseek"
    assert url == "https://api.deepseek.com/chat/completions"
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
