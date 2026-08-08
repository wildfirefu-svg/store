"""Call LLM API (Anthropic, DeepSeek, Kimi, GLM, Qwen) with urllib (no external deps).

Auto-detects API provider from key prefix or env var:
  - sk-ant-* → Anthropic Messages API
  - sk-* with DEEPSEEK_API_KEY → DeepSeek (OpenAI-compatible) API
  - sk-* with KIMI_API_KEY → Kimi/Moonshot (OpenAI-compatible) API
  - * with GLM_API_KEY → GLM/Zhipu (OpenAI-compatible) API
  - sk-* with QWEN_API_KEY → Qwen/DashScope (OpenAI-compatible) API
"""
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    ANTHROPIC_MODEL,
    API_RETRIES,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_THINKING,
    DEFAULT_TEMPERATURE,
    GLM_BASE_URL,
    GLM_MODEL,
    KIMI_BASE_URL,
    KIMI_MODEL,
    LOG_FILE,
    LOG_LEVEL,
    MAX_TOKENS,
    QWEN_BASE_URL,
    QWEN_MODEL,
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename=LOG_FILE or None,
)
logger = logging.getLogger('claude')

def _load_dotenv():
    """Lightweight .env loader (no external dep). Reads KEY=VALUE pairs from
    project-root/.env into os.environ without overriding existing values.
    Lines starting with '#' are ignored. Quoted values are unquoted."""
    if getattr(sys, 'frozen', False):
        root = os.path.dirname(sys.executable)
    else:
        root = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(root, ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except (FileNotFoundError, OSError):
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _load_api_key():
    """Load API key from env vars (loaded by _load_dotenv). Returns '' if not configured."""
    # Priority: deepseek > anthropic > kimi > glm > qwen
    for env_name in (
        "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "KIMI_API_KEY", "GLM_API_KEY", "QWEN_API_KEY"
    ):
        key = os.environ.get(env_name, "").strip()
        if key:
            return key
    return ""


ANTHROPIC_API_KEY = _load_api_key()


def _detect_provider(api_key: str):
    """Return (provider_name, base_url, default_model)."""
    if not api_key:
        return "deepseek", DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    if api_key.startswith("sk-ant"):
        return "anthropic", ANTHROPIC_BASE_URL, ANTHROPIC_MODEL
    # Check which env var matched by comparing against os.environ values
    # Priority: kimi > glm > qwen > deepseek (for sk- prefixed keys)
    env_key_map = [
        ("KIMI_API_KEY", "kimi", KIMI_BASE_URL, KIMI_MODEL),
        ("GLM_API_KEY", "glm", GLM_BASE_URL, GLM_MODEL),
        ("QWEN_API_KEY", "qwen", QWEN_BASE_URL, QWEN_MODEL),
        ("DEEPSEEK_API_KEY", "deepseek", DEEPSEEK_BASE_URL, DEEPSEEK_MODEL),
    ]
    for env_name, provider_name, base_url, default_model in env_key_map:
        env_val = os.environ.get(env_name, "").strip()
        if env_val and api_key == env_val:
            return provider_name, base_url, default_model
    # Fallback for unknown sk- keys: assume deepseek
    if api_key.startswith("sk-"):
        return "deepseek", DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    return "deepseek", DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


def _log_ai_config():
    """Emit a one-shot startup banner so operators can see which AI provider
    and model are actually loaded, and surface obvious key issues."""
    key = ANTHROPIC_API_KEY
    if not key:
        logger.warning("AI key not configured — set DEEPSEEK_API_KEY/ANTHROPIC_API_KEY/KIMI_API_KEY/GLM_API_KEY/QWEN_API_KEY or add to .env")
        return
    provider, _, model = _detect_provider(key)
    logger.info("AI configured: provider=%s model=%s", provider, model)
    if not key.startswith("sk-") and provider not in ("glm",):
        logger.warning("AI key does not start with 'sk-'; this looks suspicious")
    elif provider == "deepseek" and len(key) < 32:
        logger.warning("DeepSeek key looks unusually short; verify it is the full key")


def get_ai_config():
    provider, _, model = _detect_provider(ANTHROPIC_API_KEY or "")
    return {
        "provider": provider,
        "model": model,
        "key_configured": bool(ANTHROPIC_API_KEY),
    }


class TruncatedResponseError(RuntimeError):
    """Model call succeeded (HTTP 200) but the response was truncated.

    Indicates finish_reason != 'stop' (e.g. 'length', 'content_filter', 'tool_calls'
    when only text was expected).  Raised as a RuntimeError with a 'truncated_response'
    prefix so retry ledgers can distinguish it from network errors.
    """


def call_model_messages_sync(messages, provider=None, model=None, system_prompt=None, timeout=180, temperature=None, thinking_mode=None):
    """同步调用模型补全接口，支持 multi-turn messages。返回纯文本。"""
    text, _ = call_model_messages_sync_with_meta(
        messages, provider=provider, model=model, system_prompt=system_prompt,
        timeout=timeout, temperature=temperature, thinking_mode=thinking_mode)
    return text


def call_model_messages_sync_with_meta(messages, provider=None, model=None, system_prompt=None, timeout=180, temperature=None, thinking_mode=None):
    """同步调用模型补全接口，返回 (text, meta_dict)。

    meta 包含 finish_reason / usage / response_id / latency_ms / provider / model /
    requested_model / response_model / thinking_mode / http_status。
    仅当 finish_reason 明确不是正常终止时，text 仍取 message content（可能被截断），
    由调用方决定是否触发重试。
    """
    detected_provider, detected_url, default_model = _detect_provider(ANTHROPIC_API_KEY or "")
    provider = provider or detected_provider
    model = model or default_model
    sys_text = system_prompt if system_prompt is not None else ""

    if thinking_mode is not None and provider != "deepseek":
        raise ValueError("thinking_mode is only supported for deepseek")
    if provider == "deepseek" and thinking_mode is not None and thinking_mode != "disabled":
        raise ValueError(f"unsupported deepseek thinking_mode: {thinking_mode}")

    # 统一使用 ANTHROPIC_API_KEY（_load_api_key 加载的当前激活 key，非 Anthropic 专属）。
    # url 取 _detect_provider 返回的 detected_url（基于 key 前缀匹配 provider 对应的 base_url）。
    key = ANTHROPIC_API_KEY
    url = detected_url
    if not key:
        raise RuntimeError(f"AI key not configured for provider: {provider}")

    if provider == "anthropic":
        payload = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "system": sys_text,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        endpoint = url
    else:
        # OpenAI-compatible providers: deepseek, kimi, glm, qwen
        chat_messages = []
        if sys_text:
            chat_messages.append({"role": "system", "content": sys_text})
        chat_messages.extend({"role": m["role"], "content": m["content"]} for m in messages)
        payload = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "messages": chat_messages,
            "stream": False,
        }
        if temperature is not None:
            _t = float(temperature)
            if provider == "kimi":
                _t = 1.0
            payload["temperature"] = _t
        if provider == "deepseek" and thinking_mode is not None:
            payload["thinking"] = {"type": thinking_mode}
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        # Append /chat/completions for OpenAI-compatible endpoints
        endpoint = url
        if not endpoint.endswith("/chat/completions"):
            endpoint = endpoint.rstrip("/") + "/chat/completions"

    meta = {
        "provider": provider,
        "model": model,
        "requested_model": model,
        "response_model": None,
        "thinking_mode": thinking_mode,
        "http_status": None,
        "latency_ms": None,
        "finish_reason": None,
        "usage": None,
        "response_id": None,
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            meta["http_status"] = getattr(resp, "status", None) or getattr(resp, "getcode", lambda: None)()
    finally:
        meta["latency_ms"] = int((time.monotonic() - t0) * 1000)

    data = json.loads(body)
    if provider == "anthropic":
        meta["finish_reason"] = data.get("stop_reason")
        meta["usage"] = data.get("usage")
        meta["response_id"] = data.get("id")
        text = ""
        for block in data.get("content", []) or []:
            if block.get("type") == "text":
                text += block.get("text", "")
        return text, meta
    choices = data.get("choices", []) or []
    meta["response_model"] = data.get("model")
    meta["finish_reason"] = choices[0].get("finish_reason") if choices else None
    meta["usage"] = data.get("usage")
    meta["response_id"] = data.get("id")
    if not choices:
        return "", meta
    text = choices[0].get("message", {}).get("content", "") or ""
    return text, meta


_log_ai_config()


_SYSTEM_PROMPT_CACHE = None
_GEJUE_CACHE = None


def _get_data_dir():
    """Get directory for data files — works for dev and PyInstaller onedir bundle."""
    if getattr(sys, 'frozen', False):
        # sys._MEIPASS = _internal/ dir in onedir mode
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _load_gejue_from_disk():
    """Load and filter gejue_core.json. Returns gejue string or empty string."""
    data_dir = _get_data_dir()
    gejue_path = os.path.join(data_dir, 'knowledge-base', 'gejue_core.json')
    try:
        with open(gejue_path, 'r', encoding='utf-8') as f:
            gejue_data = json.load(f)
        entries = gejue_data.get('entries', [])

        health_kw = ['疾病', '健康', '寿元', '身体', '病', '伤']
        family_kw = ['婚姻', '夫妻', '子女', '家庭', '感情', '配偶', '桃花']
        selected = []
        for g in entries:
            tags = ' '.join(g.get('tags', [])) + ' ' + g.get('category', '') + ' ' + g.get('text', '')
            if any(kw in tags for kw in health_kw + family_kw):
                txt = g.get('baihua', '') or g.get('text', '')
                if len(txt) > 20:
                    selected.append(txt[:200])
                if len(selected) >= 20:
                    break

        if selected:
            result = "\n\n## 经典歌诀参考（内化使用，不要逐条编号引用）\n\n"
            for s in selected:
                result += f"- {s}\n"
            return result
    except Exception:
        pass
    return ""


def _load_system_prompt():
    """Load the system prompt for API calls, with gejue injection. Cached after first load."""
    global _SYSTEM_PROMPT_CACHE, _GEJUE_CACHE
    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE

    data_dir = _get_data_dir()
    prompts_dir = os.path.join(data_dir, 'prompts')

    parts = []
    file_order = ['core_rules.md', 'mode1_general.md', 'mode2_hehun.md',
                  'mode3_liunian.md', 'mode4_name.md', 'conclusion.md']

    for fname in file_order:
        fpath = os.path.join(prompts_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                parts.append(f.read())
        except FileNotFoundError:
            pass

    base = '\n\n---\n\n'.join(parts)

    # Inject gejue (cached after first load)
    if _GEJUE_CACHE is None:
        _GEJUE_CACHE = _load_gejue_from_disk()
    if _GEJUE_CACHE:
        base += _GEJUE_CACHE

    _SYSTEM_PROMPT_CACHE = base
    return base


def _build_anthropic_payload(system_prompt, chart_json, user_message, model):
    messages = [{"role": "user", "content": user_message}]
    chart_block = (
        "\n\n## Current Chart Data (JSON)\n```json\n"
        + json.dumps(chart_json, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    temperature = float(os.environ.get("ANTHROPIC_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt + chart_block,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }


def _slim_chart(chart_json):
    """Extract essential fields only to reduce token usage and noise."""
    fp = chart_json.get('four_pillars', {})
    dm = chart_json.get('day_master', {})
    ws = chart_json.get('wuxing_stats', {})
    ss = chart_json.get('shishen_stats', {})
    dy = chart_json.get('da_yun', [])
    ds = chart_json.get('dayun_summary', {})
    ziwei = chart_json.get('ziwei', {})
    shensha = chart_json.get('shensha', [])

    # Filter shensha to named ones only (skip empty meanings)
    shensha_names = list(set(
        s['name'] for s in shensha if s.get('meaning', '').strip()
    )) if isinstance(shensha, list) else []

    return {
        'four_pillars': {
            k: {'gan': v.get('gan'), 'zhi': v.get('zhi'),
                'gan_wuxing': v.get('gan_wuxing'), 'zhi_wuxing': v.get('zhi_wuxing'),
                'shi_shen_gan': v.get('shi_shen_gan'), 'nayin': v.get('nayin'),
                'cang_gan': v.get('cang_gan')}
            for k, v in fp.items()
        },
        'day_master': {'gan': dm.get('gan'), 'wuxing': dm.get('wuxing'), 'yinyang': dm.get('yinyang')},
        'wuxing_stats': ws,
        'shishen_stats': ss,
        'dayun_summary': ds,
        'da_yun': [{'gan': d.get('gan'), 'zhi': d.get('zhi'), 'start_age': d.get('start_age'),
                     'end_age': d.get('end_age'), 'is_current': d.get('is_current'),
                     'shi_shen_gan': d.get('shi_shen_gan')} for d in dy[:5]],
        'liu_nian': chart_json.get('liu_nian', [])[:3],
        'shensha': shensha_names[:20],
        'ziwei': {
            'ming_gong': ziwei.get('basic_info', {}).get('ming_gong_gan_zhi'),
            'shen_gong': ziwei.get('basic_info', {}).get('shen_gong_position'),
            'si_hua': ziwei.get('si_hua'),
            'ming_zhu': ziwei.get('basic_info', {}).get('ming_zhu'),
            'shen_zhu': ziwei.get('basic_info', {}).get('shen_zhu'),
        } if ziwei else {},
        'birth_info': chart_json.get('birth_info', {}),
        'tai_yuan': chart_json.get('tai_yuan'),
        'ming_gong': chart_json.get('ming_gong'),
        'shen_gong': chart_json.get('shen_gong'),
        'nayin_wuxing': chart_json.get('nayin_wuxing'),
    }


def _build_deepseek_payload(system_prompt, chart_json, user_message, model):
    slim = _slim_chart(chart_json) if chart_json else {}
    chart_block = (
        "\n\n## 命盘数据\n```json\n"
        + json.dumps(slim, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    messages = [
        {"role": "system", "content": system_prompt + chart_block},
        {"role": "user", "content": user_message},
    ]
    temperature = float(os.environ.get("DEEPSEEK_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    payload = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }
    thinking = os.environ.get("DEEPSEEK_THINKING", DEEPSEEK_THINKING).strip().lower()
    if thinking in ("enabled", "disabled"):
        payload["thinking"] = {"type": thinking}
        if thinking == "enabled":
            payload["reasoning_effort"] = os.environ.get("DEEPSEEK_REASONING_EFFORT", "high")
    return payload


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
    content = delta.get("content")
    reasoning = delta.get("reasoning_content")
    finish = choices[0].get("finish_reason", "")
    if finish:
        return {"type": "message_delta", "stop_reason": finish}
    if reasoning:
        return {"type": "reasoning_delta", "text": reasoning}
    if content is None:
        return {"type": "empty_delta"}
    return {"type": "text_delta", "text": content}


def stream_chat(chart_json: dict, user_message: str, conversation_history: list = None,
                api_key: str = "", model: str = "", system_prompt: str = None):
    """Generator: yields simplified SSE dicts from Anthropic or DeepSeek API."""
    key = api_key or ANTHROPIC_API_KEY
    if not key:
        yield {"type": "error", "text": "未配置 AI API Key。请设置 DEEPSEEK_API_KEY，或在项目根目录创建 .deepseek_key / .anthropic_key 文件。"}
        return

    provider, url, default_model = _detect_provider(key)
    mdl = model or default_model
    system = system_prompt if system_prompt is not None else _load_system_prompt()

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

    attempts = max(1, API_RETRIES)
    for attempt in range(attempts):
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
            body = e.read().decode("utf-8", errors="replace")[:1000]
            if e.code == 429 and attempt == 0 and attempts > 1:
                import time
                logger.warning("API rate limited (429), retrying after 2s...")
                time.sleep(2)
                continue
            logger.error(f"API HTTP {e.code}: {body}")
            yield {"type": "error", "text": f"API 错误 {e.code}: {body}"}
            return
        except (OSError, Exception) as e:
            if attempt == 0 and attempts > 1:
                import time
                logger.warning(f"Connection error, retrying: {e}")
                time.sleep(1)
                continue
            logger.error(f"Connection failed after retries: {e}")
            yield {"type": "error", "text": f"连接错误: {str(e)[:1000]}"}
            return
