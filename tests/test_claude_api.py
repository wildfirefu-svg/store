import os

import claude_api


def test_detects_deepseek_for_non_anthropic_key():
    provider, url, model = claude_api._detect_provider("sk-test")
    assert provider == "deepseek"
    assert url == "https://api.deepseek.com/chat/completions"
    assert model == os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")


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
