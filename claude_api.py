"""Call LLM API (Anthropic or DeepSeek) with urllib (no external deps).

Auto-detects API provider from key prefix:
  - sk-ant-* → Anthropic Messages API
  - sk-d*     → DeepSeek (OpenAI-compatible) API
"""
import json
import os
import urllib.request
import urllib.error

def _load_api_key():
    """Load API key from env var or local file."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".anthropic_key")
    try:
        with open(key_file, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

ANTHROPIC_API_KEY = _load_api_key()
MAX_TOKENS = 16384


def _detect_provider(api_key: str):
    """Return ('anthropic'|'deepseek', base_url, model)."""
    if api_key.startswith("sk-ant"):
        return "anthropic", "https://api.anthropic.com/v1/messages", "claude-sonnet-4-6"
    else:
        return "deepseek", "https://api.deepseek.com/v1/chat/completions", "deepseek-v4-pro"


def _load_system_prompt():
    """Load the agent system prompt from the project agent definition."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, ".claude", "agents", "bazi-multi-system-reader.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        content += "\n\n## 输出格式强制要求\n"
        content += "- 所有统计数据、对比信息、评分汇总、运势时间线、十神分布、五行计数、大运流年表、七维评分等，必须使用 Markdown 表格呈现\n"
        content += "- 表格格式：\n"
        content += "  | 列1 | 列2 | ... |\n"
        content += "  |---|---|...|\n"
        content += "  | 值1 | 值2 | ... |\n"
        content += "- 禁止用纯文本逐行罗列统计数据，表格可读性远优于文字描述\n"
        content += "- 报告中至少包含 3 张表格（如：旺衰打分表、大运流年表、七维评分汇总表）\n"
        return content
    except FileNotFoundError:
        return "You are a Chinese metaphysics (八字/紫微斗数) expert assistant."


def _build_anthropic_payload(system_prompt, chart_json, user_message, model):
    messages = [{"role": "user", "content": user_message}]
    chart_block = (
        "\n\n## Current Chart Data (JSON)\n```json\n"
        + json.dumps(chart_json, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt + chart_block,
        "messages": messages,
        "stream": True,
    }


def _build_deepseek_payload(system_prompt, chart_json, user_message, model):
    chart_block = (
        "\n\n## Current Chart Data (JSON)\n```json\n"
        + json.dumps(chart_json, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    messages = [
        {"role": "system", "content": system_prompt + chart_block},
        {"role": "user", "content": user_message},
    ]
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": messages,
        "stream": True,
    }


def _parse_anthropic_event(event: dict) -> dict:
    evt_type = event.get("type", "")
    if evt_type == "content_block_delta":
        return {"type": "text_delta", "text": event.get("delta", {}).get("text", "")}
    elif evt_type == "message_delta":
        return {"type": "message_delta", "stop_reason": event.get("delta", {}).get("stop_reason", "")}
    return {"type": evt_type}


def _parse_deepseek_event(event: dict) -> dict:
    choices = event.get("choices", [])
    if not choices:
        return {"type": "unknown"}
    delta = choices[0].get("delta", {})
    content = delta.get("content", "")
    finish = choices[0].get("finish_reason", "")
    if finish:
        return {"type": "message_delta", "stop_reason": finish}
    return {"type": "text_delta", "text": content}


def stream_chat(chart_json: dict, user_message: str, conversation_history: list = None,
                api_key: str = "", model: str = ""):
    """Generator: yields simplified SSE dicts from Anthropic or DeepSeek API."""
    key = api_key or ANTHROPIC_API_KEY
    if not key:
        yield {"type": "error", "text": "未配置 ANTHROPIC_API_KEY。请在项目根目录创建 .anthropic_key 文件。\n\n获取方式: https://console.anthropic.com/"}
        return

    provider, url, default_model = _detect_provider(key)
    mdl = model or default_model
    system = _load_system_prompt()

    if provider == "anthropic":
        payload = _build_anthropic_payload(system, chart_json, user_message, mdl)
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        parser = _parse_anthropic_event
    else:
        payload = _build_deepseek_payload(system, chart_json, user_message, mdl)
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        parser = _parse_deepseek_event

    for attempt in range(2):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                buffer = b""
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith(b"data: "):
                            data_str = line[6:].decode("utf-8", errors="replace")
                            if data_str == "[DONE]":
                                return
                            try:
                                event = json.loads(data_str)
                                yield parser(event)
                            except json.JSONDecodeError:
                                continue
            return
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            if e.code == 429 and attempt == 0:
                import time
                time.sleep(2)
                continue
            yield {"type": "error", "text": f"API 错误 {e.code}: {body}"}
            return
        except (OSError, Exception) as e:
            if attempt == 0:
                import time
                time.sleep(1)
                continue
            yield {"type": "error", "text": f"连接错误: {str(e)[:300]}"}
            return
