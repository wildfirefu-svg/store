"""Call LLM API (Anthropic or DeepSeek) with urllib (no external deps).

Auto-detects API provider from key prefix:
  - sk-ant-* → Anthropic Messages API
  - otherwise → DeepSeek (OpenAI-compatible) API
"""
import json
import os
import urllib.request
import urllib.error

def _load_api_key():
    """Load API key from env vars or local key files."""
    for env_name in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY"):
        key = os.environ.get(env_name, "").strip()
        if key:
            return key

    root = os.path.dirname(os.path.abspath(__file__))
    for filename in (".deepseek_key", ".anthropic_key"):
        key_file = os.path.join(root, filename)
        try:
            with open(key_file, "r") as f:
                key = f.read().strip()
            if key:
                return key
        except FileNotFoundError:
            pass
    return ""

ANTHROPIC_API_KEY = _load_api_key()
MAX_TOKENS = 16384


def _detect_provider(api_key: str):
    """Return ('anthropic'|'deepseek', base_url, model)."""
    if api_key.startswith("sk-ant"):
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        return "anthropic", "https://api.anthropic.com/v1/messages", model
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
    return "deepseek", "https://api.deepseek.com/chat/completions", model


def _load_system_prompt():
    """Load the system prompt for API calls, with gejue injection."""
    base = """你是一位精通中国古典命理学的玄学专家，擅长子平真诠、滴天髓、紫微斗数、盲派等多种分析体系。

## 核心规则

1. **直接给出结论，不要展示推理过程**。用户只关心分析结果，不需要看到你的内部思考。
2. **禁止在回复中输出**：知识库检索过程、工具调用信息、陷阱自查、校验清单、"现在我需要…"等自言自语。
3. **简洁精炼**：结论先行，依据简要附后。每个判断控制在 2-3 句话。
4. **诚实直接**：格局不好就说不好，不要刻意美化。

## 输出格式

- 每条核心结论标注置信度：【高】【中】【低】
- 不确定的结论明确说"无法确定"，不要模糊带过
- 统计数据使用 Markdown 表格呈现
- 使用 ⭐ 评分（1-5星）标注各维度
- 健康、家庭婚姻判断必须引用歌诀或经典依据"""

    # Inject relevant gejue as domain knowledge
    script_dir = os.path.dirname(os.path.abspath(__file__))
    gejue_path = os.path.join(script_dir, 'knowledge-base', 'gejue_core.json')
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
            base += "\n\n## 经典歌诀参考（内化使用，不要逐条编号引用）\n\n"
            for i, s in enumerate(selected):
                base += f"- {s}\n"
    except Exception:
        pass

    return base


def _build_anthropic_payload(system_prompt, chart_json, user_message, model):
    messages = [{"role": "user", "content": user_message}]
    chart_block = (
        "\n\n## Current Chart Data (JSON)\n```json\n"
        + json.dumps(chart_json, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    temperature = float(os.environ.get("ANTHROPIC_TEMPERATURE", "0.3"))
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
    temperature = float(os.environ.get("DEEPSEEK_TEMPERATURE", "0.3"))
    payload = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
    }
    thinking = os.environ.get("DEEPSEEK_THINKING", "disabled").strip().lower()
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
                api_key: str = "", model: str = ""):
    """Generator: yields simplified SSE dicts from Anthropic or DeepSeek API."""
    key = api_key or ANTHROPIC_API_KEY
    if not key:
        yield {"type": "error", "text": "未配置 AI API Key。请设置 DEEPSEEK_API_KEY，或在项目根目录创建 .deepseek_key / .anthropic_key 文件。"}
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
