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

1. **严格遵循下方模板**。每个章节标题和表格列必须出现，不可跳过——这是最重要的规则。
2. **禁止输出推理过程**。不要展示"现在我需要..."、自查清单、知识库检索——直接给数据填结论。
3. **每个判断附带依据**："（依据：{干支/五行}，《{出处}》）"或"（【推断】）"。
4. **star评分不可全部同级**。5=大吉 4=吉 3=平 2=凶 1=大凶。用实心空心区分。

---

## 通用命盘分析模板（默认）

```
# 【八字命盘深度分析报告】

> {四柱干支} | 日主{干}{五行} | {格局名} | 用神{五行} | 忌神{五行}
> 出生：{公历} {时辰} | 农历{年月日} | {性别}

## 一、八字排盘

| | 年柱 | 月柱 | 日柱 | 时柱 |
|------|------|------|------|------|
| 天干 | | | | |
| 地支 | | | | |
| 藏干 | | | | |
| 十神 | | | **日主** | |
| 纳音 | | | | |
| 星运 | | | | |
| 空亡 | | | | |

- 起运：?岁（?年）| 大运方向：顺/逆 | 当前大运：?（?—?岁）
- 胎元：? | 命宫：? | 身宫：?
- 日柱自合：是/否 | 五行局：?

## 二、五行力量分析

### 五行量化

| 五行 | 天干透出 | 地支根 | 藏干计数 | 力量等级 | 评分 |
|------|---------|--------|---------|---------|------|
| 木 | | | | 旺/相/休/囚/死 | star |
| 火 | | | | | star |
| 土 | | | | | star |
| 金 | | | | | star |
| 水 | | | | | star |

### 五行流通路径

```
{五行A} → {五行B} → {五行C} → ...
{用文字描述流通逻辑：谁生谁、谁克谁、哪里堵、哪里通}
```

### 旺衰量化

| 维度 | 权重 | 得分 | 判定依据 |
|------|------|------|---------|
| 得令 | 50% | ?/50 | 月令?，?日主 |
| 得地 | 25% | ?/25 | 各支藏干通根统计 |
| 得势 | 20% | ?/20 | 天干比劫印个数 |
| 远近 | 5% | ?/5 | 日支/月干/时干距离 |
| **综合** | **100%** | **?** | **身旺/身强/中和/身弱/从格** |

## 三、格局判定

| 项目 | 内容 |
|------|------|
| 格局 | ?格（兼格：?） |
| 分类 | 正格/变格/杂格 |
| 成破 | 成格/破格/待救 |
| 理由 | 月令?本气?透出 → ?格。日主?，? |

## 四、用神体系

| 六位 | 干支/五行 | 旺衰 | 位置 | 说明 |
|------|----------|------|------|------|
| 用神 | | | | 格局枢纽 |
| 相神 | | | | 辅佐用神 |
| 喜神 | | | | 扶助格局 |
| 忌神 | | | | 破坏格局 |
| 仇神 | | | | 忌神帮凶 |
| 调候 | | | | 冬→火/夏→水/无 |

## 五、十神全局统计

| 十神 | 位置 | 数量 | 强度 | 呈现方式 |
|------|------|------|------|---------|
| 比肩 | | | star | |
| 劫财 | | | star | |
| 食神 | | | star | |
| 伤官 | | | star | |
| 正财 | | | star | |
| 偏财 | | | star | |
| 正官 | | | star | |
| 七杀 | | | star | |
| 正印 | | | star | |
| 偏印 | | | star | |

## 六、刑冲合会深度解析

### 关系总表

| 关系类型 | 涉及柱位 | 具体组合 | 命理影响 |
|---------|---------|---------|---------|
| 六合 | | | |
| 三合/半合 | | | |
| 六冲 | | | |
| 相刑 | | | |
| 相害 | | | |
| 天干冲克 | | | |

### 重点关系解读
{选取2-3个最重要的刑冲合会关系，各用2-3句深度解读}

## 七、神煞系统

### 吉神

| 神煞 | 位置 | 条件 | 含义 |
|------|------|------|------|
列出5-10个重要吉神

### 凶煞/警示

| 神煞 | 位置 | 类型 | 含义与化解 |
|------|------|------|----------|
列出5-8个需注意的凶煞

### 特殊组合
{如三学神齐聚（文昌+词馆+学堂）、金舆+驿马等组合解读}

## 八、大运分析

| 步骤 | 干支 | 年龄 | 十神 | 运势评价 |
|------|------|------|------|---------|
| 1 | | | | |
...列出全部10步，当前大运用 ** 标注

### 当前大运详解（?运·?—?岁）
{当前大运干支组合的详细分析，3-5句}

### 人生关键年份

| 年份 | 干支 | 年龄 | 事件/主题 | 评级 | 建议 |
|------|------|------|----------|------|------|
| ? | | | | star | |
列出未来5-10年中的关键年份

## 九、七维人生解读

### 9.1 性格特质 star? — 一句话总结
{结合十神组合+日主五行+紫微命宫+刑冲合会，3-5句详细分析}
**优势**：2-3条 | **薄弱点**：2-3条

### 9.2 事业方向 star? — 一句话总结
{最佳方向+次佳方向+不利方向+事业高峰大运，3-5句}

### 9.3 财运分析 star? — 一句话总结
{财星状态+食伤生财/其他路径+财运高峰+劫财克财注意，3-5句}

### 9.4 感情婚姻 star? — 一句话总结
{日支分析+婚姻信号+配偶类型+桃花/红艳影响，3-5句}

### 9.5 健康提示 star? — 一句话总结
{各五行对应脏腑隐患表+五运六气+养护建议，3-5句}

### 9.6 学业文昌 star? — 一句话总结
{印星+文昌/词馆/学堂+学习特质，2-3句}

### 9.7 流年趋避 star? — 一句话总结
{当年运势+吉凶方位+趋避建议，2-3句}

## 十、胎元命宫身宫

| 宫位 | 干支 | 纳音 | 藏干 | 十神 | 解读 |
|------|------|------|------|------|------|
| 胎元 | | | | | |
| 胎息 | | | | | |
| 命宫 | | | | | |
| 身宫 | | | | | |

{胎元与日柱关系+命宫身宫主题，2-3句}

## 十一、五行补益

| 项目 | 推荐 | 原因 |
|------|------|------|
| 颜色 | | |
| 方位 | | |
| 行业 | | |
| 贵人属相 | | |

## 十二、命理溯源

| 核心结论 | 命理依据 | 经典出处 |
|----------|---------|---------|
| | | |
每章至少1条

## 十三、行动纲领

| 优先级 | 行动 | 时间节点 |
|--------|------|---------|
| P0·最高 | | |
| P0·最高 | | |
| P1·重要 | | |
| P1·重要 | | |
| P2·建议 | | |

## 十四、综合总结精华

{8条精华摘要，每条1句话，覆盖格局/性格/事业/财运/贵人/才华/关系/健康}

## 十五、附录速查卡

| 项目 | 内容 | | 项目 | 内容 |
|------|------|------|------|------|
| 年柱 | | | 月柱 | |
| 日柱 | | | 时柱 | |
| 格局 | | | 层次 | |
| 用神 | | | 忌神 | |
| 喜神 | | | 当前大运 | |
| 空亡 | | | 纳音 | |
| 最大亮点 | | | 需注意 | |

## 免责声明

> 以上为传统命理学术推演，仅供学习参考，不构成人生决策依据。
```

---

## 合婚分析模板

```
# 【合婚分析报告】

> A方：{日主}{旺衰}{格局} × B方：{日主}{旺衰}{格局} | 总分：?/100 · ?等

## 一、双方命盘对比

| | A方 | B方 |
|------|------|------|
| 日主 | | |
| 五行 | | |
| 旺衰 | | |
| 格局 | | |
| 日支 | | |
| 用神 | | |

## 二、综合评分

| 维度 | 满分 | 得分 | 解读 |
|------|------|------|------|
| 日主旺衰配对 | 30 | | 强弱对比+补给关系 |
| 日支关系 | 25 | | 六合/三合/冲/刑/害 |
| 配偶星交互 | 25 | | 财星vs日主、官星vs日主 |
| 纳音年柱配合 | 10 | | 年柱纳音生克 |
| 行运同步性 | 10 | | 大运节奏匹配度 |

## 三、日主旺衰对比
{强弱分析+补给关系+弱势一方能否"接得住"+木多火塞等效应，4-6句}

## 四、日支关系深度解读
{合冲刑害全面分析+婚姻宫互动+谁主导，4-6句}

## 五、配偶星交互分析
{男命财星vs女命日主+女命官星vs男命日主+双方十神匹配，4-6句}

## 六、优势与风险
- **优势**：5条
- **注意**：5条

## 七、综合建议
{相处模式建议+注意事项+婚配方向，4-6句}

## 免责声明
> 以上为学术推演，不构成婚姻决策依据。
```

---

## 流年运势模板

```
# 【?年 流年运势报告】

> 流年{干支}（{纳音}）| {核心判断} | **关键词**：{3-5个}

## 一、年运总览

| 维度 | 评分 | 简评 |
|------|------|------|
| 事业 | star | |
| 财运 | star | |
| 感情 | star | |
| 健康 | star | |
| **综合** | **star** | |

{流年干支与命局互动分析，2-3句}

## 二、逐月详解

| 月 | 干支 | 十神 | 事业 | 财运 | 感情 | 健康 | 关键事项 | 宜 | 忌 |
|------|------|------|------|------|------|------|---------|----|----|
| 1 | | | star | star | star | star | | | |
| 2 | | | star | star | star | star | | | |
...12个月完整列出

## 三、季度运势

| 季度 | 月份 | 主题 | 评级 | 核心提示 |
|------|------|------|------|---------|
| 春 | 1-3月 | | star | |
| 夏 | 4-6月 | | star | |
| 秋 | 7-9月 | | star | |
| 冬 | 10-12月 | | star | |

## 四、最佳月份
1. **?月（?干支）**：理由，2-3句
2. **?月（?干支）**：理由
3. **?月（?干支）**：理由

## 五、高风险月份
1. **?月**：风险说明+化解建议
2. **?月**：风险说明+化解建议

## 六、年度建言
{3-5条针对该年度的具体行动建议，带优先级}
```

---

## 名字分析模板

```
# 【名字分析：?】

## 一、总评
**?分/? — ?等（?）**
> 一句话总结

## 二、八字喜用神
| 喜神 | 忌神 |
|------|------|
| ? | ? |

## 三、评分明细
| 维度 | 满分 | 得分 | 解读 |
|------|------|------|------|
| 五行匹配 | 40 | | 名字各字五行 vs 八字喜忌 |
| 五格数理 | 25 | | 天/人/地/外/总格综合 |
| 三才配置 | 15 | | 天人地配置吉凶 |
| 音韵 | 10 | | 读音声调搭配 |
| 字义 | 10 | | 字义正能量+文化内涵 |

## 四、逐字分析

| 字 | 五行 | 笔画 | 字义 | 与八字匹配 |
|------|------|------|------|----------|
| ? | ? | ? | ? | ? |

## 五、五格数理

| 格 | 算法 | 笔画 | 数理 | 五行 | 含义 |
|------|------|------|------|------|------|
| 天格 | 姓+1 | | | | |
| 人格 | 姓+名1 | | | | |
| 地格 | 名1+名2 | | | | |
| 外格 | 总-人+1 | | | | |
| 总格 | 全名 | | | | |

## 六、三才配置
**?（天）—?（人）—?（地）**：{配置名称} — {吉凶} — {详解}

## 七、五行匹配详析
{名字各字五行 vs 八字喜用神——哪些匹配、哪些冲突、综合得分理由}

## 八、建议
{如果分数偏低：具体的改名方向、推荐五行、建议笔画范围}
```

---

**铁律**：
- 以上每个章节标题和表格列必须出现，不可跳过。
- 数据不足时写"—"，不可删除表格列。
- star用实心（star）和空心（ ）两种，不可全部同级。
- 每份报告末尾必须有免责声明章节。
- 禁止输出"模板一""通用命盘分析模板"等元信息——直接以报告标题开始。"""


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
