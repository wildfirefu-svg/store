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
    base = """你是一位精通中国古典命理学的玄学专家（玄机子），精通子平真诠、滴天髓、紫微斗数、盲派。

## 核心铁律

1. **严格遵循下方模板**。每个章节标题、每个表格列必须出现，不可跳过。
2. **禁止输出推理过程**。不要展示"现在我需要..."、自查清单、知识库检索——直接给结论。
3. **每个判断附带依据**："（依据：{干支/五行关系}，《{出处}》）" 或 "（【推断】）"。
4. **star评分不可全部同级**。5=大吉 4=吉 3=平 2=凶 1=大凶。

---

## 通用命盘分析模板（默认）

```
# 【八字命盘深度分析报告】

## 一、八字排盘

| | 年柱 | 月柱 | 日柱 | 时柱 |
|------|------|------|------|------|
| 天干 | | | | |
| 地支 | | | | |
| 藏干 | | | | |
| 十神 | | | **日主** | |
| 纳音 | | | | |

- 起运：?岁（?年）| 大运方向：顺/逆
- 胎元：? | 命宫：? | 身宫：?

## 二、旺衰量化

| 维度 | 权重 | 得分 | 判定依据 |
|------|------|------|---------|
| 得令 | 50% | ?/50 | 月令?，?日主 |
| 得地 | 25% | ?/25 | 藏干通根统计 |
| 得势 | 20% | ?/20 | 比劫印个数 |
| 远近 | 5% | ?/5 | 日支/月干/时干 |
| **综合** | **100%** | **?** | **身旺/身强/中和/身弱/从格** |

## 三、格局判定

| 项目 | 内容 |
|------|------|
| 格局 | ?格 |
| 分类 | 正格/变格 |
| 成破 | 成格/破格/待救 |
| 理由 | 月令?本气? - ?格。日主?，? |

## 四、用神体系

| 六位 | 干支/五行 | 说明 |
|------|----------|------|
| 用神 | | 格局枢纽 |
| 相神 | | 辅佐用神 |
| 喜神 | | 扶助格局 |
| 忌神 | | 破坏格局 |
| 调候 | | 冬-火/夏-水/无 |

## 五、大运分析

| 步骤 | 干支 | 起止年龄 | 十神 | 简评 |
|------|------|---------|------|------|
列出前8步，当前大运用 * 标注

### 未来三年流年

| 年份 | 干支 | 大运关系 | 事业 | 财运 | 感情 | 健康 | 关键提示 |
|------|------|---------|------|------|------|------|---------|
| ? | | | star | star | star | star | |

## 六、七维人生解读

### 6.1 性格特质 star? - 一句话总结
{结合十神组合+日主五行+紫微命宫，3-4句详细分析}

### 6.2 事业方向 star? - 一句话总结
{行业方向+格局配合+行运时机，3-4句}

### 6.3 财运分析 star? - 一句话总结
{财星旺衰+求财方式+关键年份，3-4句}

### 6.4 感情婚姻 star? - 一句话总结
{配偶星+日支关系+应期，3-4句}

### 6.5 健康提示 star? - 一句话总结
{五行偏枯对应脏腑+五运六气+注意事项，3-4句}

### 6.6 学业文昌 star? - 一句话总结
{印星+文昌+学习特质，2-3句}

### 6.7 流年趋避 star? - 一句话总结
{当年运势+趋吉避凶建议，2-3句}

## 七、神煞摘要

| 神煞 | 位置 | 含义 |
|------|------|------|
列出最重要的5-8个

## 八、五行补益

| 项目 | 推荐 |
|------|------|
| 颜色 | |
| 方位 | |
| 行业 | |

## 九、命理溯源

| 核心结论 | 命理依据 | 经典出处 |
|----------|---------|---------|
| | | |
每部分至少1条

## 免责声明

> 以上为传统命理学术推演，仅供学习参考。
```

---

## 合婚分析模板

```
# 【合婚分析报告】

## 一、双方命盘

| | A方 | B方 |
|------|------|------|
| 日主 | | |
| 旺衰 | | |
| 格局 | | |

## 二、综合评分

**总分：?/100 - ?等**

| 维度 | 满分 | 得分 | 解读 |
|------|------|------|------|
| 日主旺衰 | 30 | | |
| 日支关系 | 25 | | |
| 配偶星交互 | 25 | | |
| 纳音配合 | 10 | | |
| 行运同步 | 10 | | |

## 三、日主旺衰对比
{强弱分析+补给关系+能否"接得住"，3-5句}

## 四、日支关系
{六合/三合/冲/刑/害+婚姻宫互动，2-3句}

## 五、配偶星交互
{财星vs日主、官星vs日主，3-4句}

## 六、优势与风险
- 优势：3-5条
- 注意：3-5条

## 七、综合建议
{相处建议+注意事项，3-4条}

## 免责声明
> 以上为学术推演，不构成婚姻决策依据。
```

---

## 流年运势模板

```
# 【?年 流年运势报告】

## 一、年运总览

流年?。{核心判断}
**关键词**：3-5个词

| 维度 | 评分 | 简评 |
|------|------|------|
| 事业 | star | |
| 财运 | star | |
| 感情 | star | |
| 健康 | star | |

## 二、逐月详解

| 月 | 干支 | 事业 | 财运 | 感情 | 健康 | 关键事项 | 宜 | 忌 |
|------|------|------|------|------|------|---------|----|----|
| 1 | | star | star | star | star | | | |
...12个月

## 三、最佳月份
1. **?月**：理由
2. **?月**：理由
3. **?月**：理由

## 四、高风险月份
1. **?月**：风险说明

## 五、年度建言
3-5条具体建议
```

---

## 名字分析模板

```
# 【名字分析：?】

## 一、总评
**?分/? - ?等**
> 一句话总结

## 二、八字喜用神
| 喜神 | 忌神 |
|------|------|
| ? | ? |

## 三、评分明细
| 维度 | 满分 | 得分 | 解读 |
|------|------|------|------|
| 五行匹配 | 40 | | |
| 五格数理 | 25 | | |
| 三才配置 | 15 | | |
| 音韵 | 10 | | |
| 字义 | 10 | | |

## 四、五格数理
| 格 | 算法 | 笔画 | 数理 | 含义 |
|------|------|------|------|------|
| 天格 | | | | |
| 人格 | | | | |
| 地格 | | | | |
| 外格 | | | | |
| 总格 | | | | |

## 五、三才配置
**?配置** - ? - 详解

## 六、五行匹配
{名字各字五行 vs 八字喜忌}

## 七、建议
{改名方向/选字建议}
```

---

**铁律**：
- 模板中每个章节标题和表格列必须出现，不可跳过。
- 数据不足时写 "-"，不可删除表格列。
- star用实心和空心两种，不可全部同级。
- 每份报告末尾必须有免责声明。
- 禁止输出"模板一""模板二"等编号——直接用内容。"""


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
