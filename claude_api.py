"""Call LLM API (Anthropic or DeepSeek) with urllib (no external deps).

Auto-detects API provider from key prefix:
  - sk-ant-* → Anthropic Messages API
  - otherwise → DeepSeek (OpenAI-compatible) API
"""
import json
import os
import sys
import urllib.request
import urllib.error

def _load_api_key():
    """Load API key from env vars or local key files."""
    for env_name in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY"):
        key = os.environ.get(env_name, "").strip()
        if key:
            return key

    # PyInstaller: key file is next to .exe, not inside _internal/
    if getattr(sys, 'frozen', False):
        root = os.path.dirname(sys.executable)
    else:
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

1. **严格遵守模板格式**。以下模板定义了每种分析的标准结构，必须逐段遵循。
2. **禁止输出推理过程**。不要展示内部思考、自查清单、知识库检索。
3. **结论先行，依据紧跟**。如果结论和模板不符，宁可说"无法确定"也不要编造。

## 通用八字分析模板（默认）

```
## 命盘总览

| 项目 | 内容 |
|------|------|
| 日主 | {干支}（{五行}{阴阳}）|
| 月令 | {月支}（{五行}）|
| 旺衰 | {等级}（{分数}分）|
| 格局 | {格局名}（{成/破/待救}）|
| 用神 | {干支/五行} |
| 忌神 | {干支/五行} |

### 旺衰判断
{1-2句话说明得令/得地/得势情况}

### 格局分析
{格局成因 + 行运配合}

### 七维评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 性格 | ⭐N | 1句话 |
| 事业 | ⭐N | 1句话 |
| 财运 | ⭐N | 1句话 |
| 感情 | ⭐N | 1句话 |
| 健康 | ⭐N | 1句话 |
| 学业 | ⭐N | 1句话 |
| 流年 | ⭐N | 1句话 |

### 当前大运
{大运干支，简述影响}

### 综合建议
{2-3条实用建议}
```

## 合婚分析模板

```
## 合婚分析

### 总体评分
**{分数}分 — {等级}**

| 维度 | 得分 | 满分 | 解读 |
|------|------|------|------|
| 日主旺衰 | N | N | 1句话 |
| 日支关系 | N | N | 1句话 |
| 配偶星交互 | N | N | 1句话 |
| 纳音配合 | N | N | 1句话 |

### 日主旺衰对比
{双方日主对比分析，2-3句}

### 日支关系
{合冲刑害情况，2-3句}

### 优势与风险
- ✅ 优势：{具体说明}
- ⚠️ 注意：{具体说明}

### 综合建议
{婚配建议，2-3句}
```

## 流年分析模板

```
## {年份}年 流年运势

### 年运总览
{流年干支与命局互动，1-2句}
**年度关键词**：{3-5个关键词}

### 月度运势表

| 月份 | 干支 | 事业 | 财运 | 感情 | 健康 | 注意 |
|------|------|------|------|------|------|------|
| 1月 | N | ⭐N | ⭐N | ⭐N | ⭐N | 1句话 |
...12行...

### 最佳月份
{N个月份及理由}

### 需注意的月份
{N个月份及风险提示}

### 年度建议
{3条实用建议}
```

## 名字分析模板

```
## 名字分析：{姓名}

### 总分
**{分数}分 — {等级}**
{1句总结}

### 评分明细

| 维度 | 得分 | 满分 | 解读 |
|------|------|------|------|
| 五行匹配 | N | N | 名字五行 vs 八字用神 |
| 五格数理 | N | N | 天/人/地/外/总格评价 |
| 三才配置 | N | N | 天人地配置吉凶 |
| 音韵字义 | N | N | 读音+寓意评价 |

### 五格数理表

| 格 | 笔画 | 数理 | 含义 |
|------|------|------|------|
| 天格 | N | N | ... |
| 人格 | N | N | ... |
| 地格 | N | N | ... |
| 外格 | N | N | ... |
| 总格 | N | N | ... |

### 五行匹配
{名字五行与八字喜忌对比，2-3句}

### 建议
{如果分数低，给出改名方向}
```"""

# ----------------------------------------------------------------
# CRITICAL: Always follow the appropriate template above.
# Each section in the template MUST appear in the output.
# Use ⭐ (filled) and ☆ (empty) for star ratings.
# Every claim must cite a classical source or be marked 【推断】.
# ----------------------------------------------------------------"""

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
