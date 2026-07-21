# Phase 6 6B1 — 本命紫微上下文信号消融：实施计划

**plan_id**: `phase6-6b1-v9`
**状态**: `APPROVED`
**父设计**: `docs/superpowers/specs/2026-07-17-phase6-dual-system-accuracy-design.md` §6
**前置结论**: 6A0 ROLLBACK（legacy_v0）；6A1 ROLLBACK（single@T=0）
**阻塞语义**: 6A0/6A1 失败不阻塞 6B1；6B1 未过 gate 则阻止 6B2

---

## 1. 实验目标

判断**在 legacy_v0 八字上下文之上追加本命紫微上下文**是否带来 BaziQA 评测准确率信号。

三臂消融：

| 实验臂 `--arm` | 渲染 `--ziwei-arm` | 上下文 | 动机 |
|---|---|---|---|
| `b1a_prime` | `none` | legacy_v0 身份 + 八字 | 控制臂（6A0/6A1 锁定） |
| `b1b` | `only` | 身份头 + 本命紫微 | 诊断臂（仅描述性，不进 gate） |
| `b1c` | `combined` | legacy_v0 身份 + 八字 + 本命紫微 | 信号臂（唯一进 gate 臂） |

`--arm` = 实验臂标签（入 attempt key、summary、report）；`--ziwei-arm` = 渲染模式（控制 formatter 和 visibility gate 行为）。两者独立、一一映射。

控制臂锁定 `legacy_v0`（非 approved_v1）。若使用 approved_v1，会同时改变上下文版本和紫微注入两个变量，实验不可解释。

---

## 2. 基础协议

| 维度 | 冻结值 |
|---|---|
| 输出协议 | reasoned_choice（三臂统一） |
| 采样 | single@T=0 |
| 数据集 | 仅 2024/2025 enriched holdout，各 40 题 |
| repeats | 3 |
| 调度 | Latin square，确定性串行 |
| 全局 scheduled | 720（40 × 3 arms × 2 years × 3 repeats） |
| 全局 hard cap | 800（有效上限 792，剩余 8 次不可挪用） |
| gate | Δ_dev = mean(Δ_2024, Δ_2025) ≥ +2pp 且 min(Δ_2024, Δ_2025) ≥ -2pp |
| 推进条件 | gate 通过 → 设计 6B2；未通过 → 紫微路线 STOP |

Δ 定义（总设计 §6）：
```
Δ(year, repeat) = accuracy_b1c(year, repeat) - accuracy_b1a(year, repeat)
Δ_year = mean(3 repeats)
Δ_dev  = mean(Δ_2024, Δ_2025)
```

---

## 3. reasoned_choice 输出协议

### 3.1 prompt 格式

```
你是一位严谨的八字命理评测助手。

请根据命主信息，通过推理分析后回答四选一题。

## 命主信息
{context}

## 问题
{question}

## 选项
A. ...
B. ...
C. ...
D. ...

## 输出要求
请先进行推理分析，然后给出最终答案。最后一行必须严格为：
最终答案：X
其中 X 为 A、B、C 或 D 之一。
```

### 3.2 答案提取

```python
def extract_reasoned_choice_answer(raw):
    """仅匹配独立最终答案行；不 fallback 到正文。"""
    matches = re.findall(
        r"(?m)^\s*最终答案\s*[:：]\s*([A-Da-d])\s*[。.]?\s*$",
        str(raw or ""),
    )
    return matches[-1].upper() if matches else None
```

兼容中英文冒号、大小写、前后空白、句尾标点。多行锚定确保不匹配正文中出现的 `最终答案：C` 片段。

### 3.3 终态与准确性语义

| raw_answer | 解析结果 | terminal_state | correct | 是否计入分母 |
|---|---|---|---|---|
| 含 `最终答案：X` | X = expected | `parsed` | True | 是 |
| 含 `最终答案：X` | X ≠ expected | `parsed` | False | 是 |
| 含 `最终答案` 但非法选项 | — | `invalid` | False | 是 |
| 不含任何 `最终答案` 行 | — | `invalid` | False | 是 |
| API 调用失败 | — | `call_failed` | False | 是 |

**每个 (year, repeat, arm) 的 accuracy 固定为 `correct / 40`。** 解析失败和调用失败均保留在分母中。不允许不同臂因解析失败率不同而使用不同的有效分母。

语义沿用 `score_choice_answers()` 现有行为：`total` 先递增再检查 `predicted is None`→`continue`，即 missing 已计入分母（`choice_accuracy.py:102-108`）。

### 3.4 runner summary 与 detail 解析一致性（关键）

当前 runner 在 `run_model_benchmark()` 第 1127 行存储：
```python
predictions[case_id] = answer   # raw 原始文本
```

随后 `main()` 第 1606 行调用：
```python
score_choice_answers(model_cases, predictions)
```

`score_choice_answers()` 第 105 行使用 `extract_choice()`（通用解析器）从 raw 文本重新提取答案。对于 reasoned profile，`extract_choice()` 可能从推理文本中抓取第一个 A/B/C/D（例如推理中引用了某个选项标签），而非最后的 `最终答案：X`，导致 **detail.correct ≠ runner summary accuracy**。

**更严重的问题**：当前 runner 第 1138-1140 行对**所有 profile** 执行：
```python
meta = extract_choice_with_meta(answer)
if predicted is None:
    predicted = meta['choice']
```

当 reasoned extractor 返回 `None`（模型没有合法 `最终答案：X` 行）时，通用解析器 `extract_choice_with_meta` 仍可能从推理正文抓出 A/B/C/D，将本应为 `invalid` 的结果变成 `parsed`。这直接破坏 reasoned 协议的设计意图——极端情况下，20/40 题无最终答案行时，通用提取器仍能抓出 15 题，parser rate 虚高至 87.5%（实际 reasoned 有效率为 50%），并产生匹配正确的幻觉。

**修正**：reasoned profile 下必须**完全替换**整个解析块，禁止通用解析器作为 fallback：

```python
expected = extract_choice(case.get('answer'))

if profile_formatter == 'format_reasoned_choice_prompt':
    # reasoned 分支：仅使用 reasoned extractor，禁止回退到通用解析器
    from benchmark.formatters.chart_context import extract_reasoned_choice_answer
    predicted = extract_reasoned_choice_answer(answer)
    meta = {
        "choice": predicted,
        "source": "reasoned_final_answer",
        "valid": predicted is not None,
    }
    predictions[case_id] = predicted
else:
    # 现有行为不变
    meta = extract_choice_with_meta(answer)
    if predicted is None:
        predicted = meta['choice']
    predictions[case_id] = answer
```

reasoned 分支中**禁止**执行以下任一语句：
```python
predicted = extract_choice_with_meta(answer)["choice"]      # 禁止
predicted = extract_choice(answer)                           # 禁止
```

测试必须覆盖：
- 正文出现 A/B/C/D，但没有 `最终答案：X` 行 → `predicted = None` → terminal_state `invalid`
- 最终答案行非法选项（如 `最终答案：E`），正文含合法选项字母 → `predicted = None` → terminal_state `invalid`
- 最终答案行存在 → `meta["source"] = "reasoned_final_answer"`
- `detail.parser_valid`、`detail.terminal_state`、runner summary 三者一致

同时需要在测试矩阵中增加"detail accuracy == runner summary accuracy"验证。

---

## 4. 共享上下文渲染函数

### 4.1 核心方案

格式化器构造 prompt 和可见性门禁扫描 gate_text 必须调用同一个函数，消除"实际 prompt ≠ 门禁扫描文本"分叉。

```python
# benchmark/formatters/chart_context.py 新增

def render_reasoned_context(case, chart_schema_version, ziwei_arm):
    """本命紫微信号消融——格式化器与可见性门禁的唯一上下文入口。

    三臂冻结输出：
      - none:     legacy_v0（身份头 + 四柱行 + 日主行）
      - only:     身份头 + _render_ziwei()
      - combined: legacy_v0 + '\\n\\n' + _render_ziwei()

    身份头复用现有 _identity_header()（line 114）——不重新实现数据字段读取。
    _render_ziwei() 复用现有实现（line 238）——直接读取 case["chart_input"]["ziwei"]。
    """
    if ziwei_arm == "none":
        return format_birth_line(case)  # 身份头 + 四柱行 + 日主行

    ziwei = case["chart_input"]["ziwei"]
    identity = _identity_header(case)   # 现有实现（line 114）：format_birth_line 前 4 行
    ziwei_text = _render_ziwei(ziwei)   # 现有实现（line 238）

    if ziwei_arm == "only":
        return identity + "\n\n" + ziwei_text

    if ziwei_arm == "combined":
        return format_birth_line(case) + "\n\n" + ziwei_text

    raise ValueError(f"未知 ziwei_arm: {ziwei_arm!r}（合法值: none, only, combined）")
```

**显式拒绝非法模式**：`none` 分支不读取 `case["chart_input"]["ziwei"]`（控制臂保持紫微字段无依赖）；`only`/`combined` 分支读取；末尾 `raise ValueError` 替代隐式 `None` 返回。

**关键**：`_identity_header()` 和 `_render_ziwei()` **复用 `chart_context.py` 现有实现**（line 114 和 line 238），不写新版本。现有 `_identity_header()` 的正确实现是：
```python
def _identity_header(case: dict) -> str:
    return "\n".join(format_birth_line(case).split("\n")[:4])
```

真实 enriched 数据结构为：
```json
case.person.name = "1980年广东出生女性",
case.person.birth.place = "广东，中国",
case.chart_input.birth_info = {"year": 1980, "gender": "female", "location": "广东，中国"}
```

即 `name` 在 `person.name`，地点键在 `person.birth.place`，而 `chart_input.birth_info` 使用键 `location`（非 `place`）——从 `chart_input.birth_info` 按 `name`/`place` 键读取会在真实数据上直接 `KeyError`。

避免 `chart_context.py` 和 `baziqa_prompt.py` 互相导入私有函数造成循环依赖——所有需共享的辅助函数已收敛于 `chart_context.py`。`format_birth_line` 是已存在的公开导入（line 10）。

### 4.2 接线点

| 调用处 | 变更 |
|---|---|
| `build_benchmark_prompt()` reasoned 分支 | `context = render_reasoned_context(case, chart_schema_version, ziwei_arm)` |
| `_phase6_visibility_filter()` | `gate_text = render_reasoned_context(case, profile.chart_schema_version, ziwei_arm)` |
| B1-b 隔离断言 | 对 `render_reasoned_context(case, "legacy_v0", "only")` 的输出扫描 forbidden 标记 |

---

## 5. profile 与 runner 接线

### 5.1 profile

```python
EvalProfile(
    "baziqa_xjz_reasoned",    # profile_id
    "baziqa",                 # dataset
    "xjz_reasoned",           # prompt_style
    "direct",                 # interaction_mode → derive_method="direct_choice"
    "legacy_v0",              # chart_schema_version
    "baziqa_macro",           # scoring_profile
)
```

### 5.2 formatter 映射

```python
_FORMATTER_MAP 新增:
    ("baziqa", "xjz_reasoned", "direct"): "format_reasoned_choice_prompt",
```

### 5.3 prompt 构建路由

`build_benchmark_prompt()` 签名新增 `ziwei_arm=None`：

```python
def build_benchmark_prompt(case, method='direct_choice', phase4_exp_a=False,
                           chart_schema_version=None, profile_formatter=None,
                           ziwei_arm=None):
    # ... existing official_cot / two_stage / structured_reasoning branches unchanged ...
    if profile_formatter == 'format_reasoned_choice_prompt':
        from benchmark.formatters.chart_context import render_reasoned_context
        context = render_reasoned_context(case, chart_schema_version, ziwei_arm)
        return _assemble_reasoned_choice_prompt(case, context)
    if method in ('direct_choice', 'multi_turn'):
        # ... 现有逻辑不变 ...
```

### 5.4 `ziwei_arm` 三层穿透（关键）

当前调用链：

```text
main()                                    # 已有 --arm
  → run_model_benchmark(...)              # line 671, 无 ziwei_arm 参数
    → build_benchmark_prompt(...)         # line 330, 无 ziwei_arm 参数
```

必须逐层穿透（三处签名修改）：

**修改点 1** — `build_benchmark_prompt()`（line 330）：
```python
def build_benchmark_prompt(case, method='direct_choice', phase4_exp_a=False,
                           chart_schema_version=None, profile_formatter=None,
                           ziwei_arm=None):   # 新增
```

**修改点 2** — `run_model_benchmark()`（line 671）：
```python
def run_model_benchmark(cases, provider, model, prompt_version, max_cases=20,
                        method='direct_choice', ...,
                        ziwei_arm=None):       # 新增
```

在 `run_model_benchmark` 主体内，将 `ziwei_arm` 传入 `build_benchmark_prompt`：
```python
# line 725 附近
prompt = build_benchmark_prompt(case, method=method, phase4_exp_a=phase4_exp_a,
                                chart_schema_version=chart_schema_version,
                                profile_formatter=profile_formatter,
                                ziwei_arm=ziwei_arm)     # 新增穿透
```

**修改点 3** — `main()` 调用 `run_model_benchmark()`（line 1556）：
```python
model_result = run_model_benchmark(
    ...,
    ziwei_arm=getattr(args, 'ziwei_arm', None),   # 新增穿透
)
```

**测试要求**：对三层穿透分别写单元测试——传入 `ziwei_arm="only"` 时 `render_reasoned_context` 收到相同参数。

### 5.5 答案提取接线（禁止通用解析器 fallback）

runner 循环内，`profile_formatter == "format_reasoned_choice_prompt"` 时（§3.4）执行完整替换块：

```python
expected = extract_choice(case.get('answer'))

if profile_formatter == 'format_reasoned_choice_prompt':
    from benchmark.formatters.chart_context import extract_reasoned_choice_answer
    predicted = extract_reasoned_choice_answer(answer)
    meta = {
        "choice": predicted,
        "source": "reasoned_final_answer",
        "valid": predicted is not None,
    }
    predictions[case_id] = predicted
else:
    meta = extract_choice_with_meta(answer)
    if predicted is None:
        predicted = meta['choice']
    predictions[case_id] = answer
```

**关键约束**：reasoned 分支中 `predictions[case_id] = predicted`（非 `answer`），且 **不执行** `extract_choice_with_meta(answer)`。如果 `predicted is None`，`detail.predicted_answer` 为 `None`，`terminal_state` 为 `invalid`——通用解析器绝不被调用。

### 5.6 prompt_fingerprint() 增加 reasoned formatter 分支

当前 `prompt_fingerprint()` 对未知 formatter 落入 `else` 分支即 `format_multi_turn`（`profiles.py:157`）。新增 reasoned profile 后应显式加入：

```python
elif formatter == "format_reasoned_choice_prompt":
    from benchmark.formatters import chart_context as cc
    parts += [
        inspect.getsource(cc.render_reasoned_context),
        inspect.getsource(
            baziqa_prompt._assemble_reasoned_choice_prompt
        ),
        inspect.getsource(cc.extract_reasoned_choice_answer),
    ]
```

`code_sha256` 虽提供兜底，但 prompt 指纹本身应准确表达 reasoned 协议的实际源码。

### 5.7 CLI 新增参数

```python
parser.add_argument("--ziwei-arm", default=None,
                    choices=["none", "only", "combined"],
                    help="紫微消融臂渲染模式")
```

不新增 `--method reasoned_choice`。

### 5.8 resume manifest（字段清单 + 内容同时修改）

`RESUME_MANIFEST_FIELDS` 新增 `"ziwei_arm"`（`run_benchmark.py:121-127`）：

```python
RESUME_MANIFEST_FIELDS: tuple = (
    "dataset_sha256", "case_ids_sha256", "profile_id", "chart_schema_version",
    "arm", "attempt_stage", "repeat_idx", "provider", "model",
    "temperature", "sample_temperature", "n_samples", "aggregate", "method",
    "prompt_template_sha256", "code_sha256", "scheduled_calls", "hard_cap",
    "as_of_date",
    "ziwei_arm",                               # 新增：6B1 消融臂
)
```

`build_resume_manifest()` 返回字典同步新增（`run_benchmark.py:169-196`）：

```python
def build_resume_manifest(args, profile) -> dict:
    return {
        ...
        "as_of_date": getattr(args, "as_of_date", ""),
        "ziwei_arm": getattr(args, "ziwei_arm", None),    # 新增
    }
```

**测试要求**：
- 首次 manifest 含 `ziwei_arm` 字段
- 相同 `ziwei_arm` 允许 resume
- `none → combined` 必须拒绝 resume（`check_resume_manifest` 检测 diff → SystemExit(2)）

---

## 6. 可见性门禁（ziwei_arm 扩展）

### 6.1 api（保留向后兼容）

所有函数新增 `ziwei_arm=None` 默认参数，不破坏现有两参数/三参数调用：

```python
def visibility_requirements(
    profile,
    chart_schema_version,
    ziwei_arm=None,                    # 新增，默认向后兼容
):
    _DENYLIST_MARKERS = frozenset({...})  # 现有 denylist 不变

    if ziwei_arm is None:
        # 旧行为不变：直接 fall through 至现有 logic（profiles.py:98-110）
        # 注：不存在 _existing_visibility_requirements() 独立函数。
        # 原有逻辑就在 visibility_requirements() 函数体内，
        # ziwei_arm is None 时直接执行 chart_schema_version 分支即可。
        pass
    elif ziwei_arm == "none":
        # legacy_v0 行为：无 required marker，forbidden = approved + denylist
        return frozenset(), _APPROVED_ONLY_MARKERS | _DENYLIST_MARKERS
    elif ziwei_arm == "only":
        required = frozenset({"【紫微斗数·本命】"})
        forbidden = frozenset({
            "【四柱】", "【日主】", "【大运】", "【神煞】",
            "【胎元／命宫／身宫】", "【真太阳时校正】",
            "【纳音五行】", "【五行统计】", "【十神统计】",
            "【地支关系】",
        }) | _DENYLIST_MARKERS
        return required, forbidden
    elif ziwei_arm == "combined":
        required = frozenset({"【紫微斗数·本命】"})
        forbidden = _DENYLIST_MARKERS
        return required, forbidden
    else:
        raise ValueError(f"未知 ziwei_arm: {ziwei_arm!r}")

    # ziwei_arm is None → 现有逻辑（profiles.py:98-110）
    if chart_schema_version == "legacy_v0":
        return frozenset(), _APPROVED_ONLY_MARKERS | _DENYLIST_MARKERS
    if chart_schema_version == "approved_v1":
        if profile.profile_id == "mingli_official_cot_astro":
            return _OFFICIAL_ASTRO_MARKERS, _DENYLIST_MARKERS
        if profile.dataset == "mingli":
            return _MINGLI_BAZI_CORE_MARKERS | _ZIWEI_MARKERS, _DENYLIST_MARKERS
        return _APPROVED_BAZI_MARKERS, _DENYLIST_MARKERS
    raise SystemExit(f"未知 chart_schema_version: {chart_schema_version!r}")


def assert_visibility(
    rendered_text,
    profile,
    chart_schema_version,
    ziwei_arm=None,                    # 新增，默认向后兼容
):
    required, forbidden = visibility_requirements(
        profile, chart_schema_version, ziwei_arm=ziwei_arm,
    )
    violations = [f"required 缺失: {m}" for m in sorted(required) if m not in rendered_text]
    violations += [f"forbidden 命中: {m}" for m in sorted(forbidden) if m in rendered_text]
    return violations
```

**关键**：不存在名为 `_existing_visibility_requirements()` 的独立函数（v6 误称）。现有逻辑直接位于 `visibility_requirements()` 函数体内（`profiles.py:95-110`）。当 `ziwei_arm is None` 时，直接 fall through 到现有 `chart_schema_version` 分支——不引入不必要的抽象层。

### 6.2 现有调用点兼容性验证

| 调用点 | 当前签名 | ziwei_arm=None 兼容？ |
|---|---|---|
| `profiles.py:117` → `visibility_requirements(profile, chart_schema_version)` | 2 参数 | 是（默认 None → fall through 旧分支） |
| `profiles.py:128` → `assert_visibility(rendered_text, profile, chart_schema_version)` | 3 参数 | 是（默认 None → fall through 旧分支） |
| `run_phase6_6a0_ablation.py:137` → `assert_visibility(rendered, arm_profile, schema)` | 3 参数 | 是 |
| `run_phase6_6a1_ablation.py:523` → `assert_visibility(rendered, profile, version)` | 3 参数 | 是 |
| `test_phase6_profiles.py:91` → `visibility_requirements(profile, version)` | 2 参数 | 是 |

测试矩阵新增"旧双参数调用行为不变"验证。

### 6.3 runner 内 fail-closed 映射检查

编排器和 runner **两层都检查** arm↔ziwei_arm 映射，防止 CLI 漏传参数时产生 `None` 上下文：

```python
EXPECTED_ZIWEI_ARM = {
    "b1a_prime": "none",
    "b1b": "only",
    "b1c": "combined",
}

# runner 侧：build_resume_manifest 前检查（main 启动阶段）
if profile.profile_id == "baziqa_xjz_reasoned":
    expected = EXPECTED_ZIWEI_ARM.get(args.arm) if args.arm else None
    if expected is None or args.ziwei_arm != expected:
        print(json.dumps(
            {"status": "ARM_ZIWEI_ARM_MISMATCH",
             "arm": args.arm, "ziwei_arm": args.ziwei_arm,
             "expected": expected},
            ensure_ascii=False))
        raise SystemExit(2)
```

编排器侧在构造 subprocess 命令时同样验证映射一致性。

### 6.4 调用处变更

```python
# _phase6_visibility_filter()
if profile_formatter == 'format_reasoned_choice_prompt':
    gate_text = render_reasoned_context(case, profile.chart_schema_version,
                                         ziwei_arm=args.ziwei_arm)
elif profile_formatter == 'format_official_cot_prompt':
    gate_text = format_official_cot_prompt(case)
else:
    gate_text = render_chart_context(case, profile.chart_schema_version)

violations = assert_visibility(gate_text, profile, profile.chart_schema_version,
                                ziwei_arm=args.ziwei_arm)
```

---

## 7. B1-b 隔离断言

### 7.1 扫描对象

只扫描 `render_reasoned_context(case, "legacy_v0", "only")` 的输出（上下文片段），不扫描问题和选项。

### 7.2 禁止标记

```python
_BAZI_SECTION_MARKERS_B1B_FORBIDDEN = frozenset({
    "四柱：", "日主：",
    "【四柱】", "【日主】", "【大运】", "【神煞】",
    "【十神统计】", "【五行统计】", "【纳音五行】",
    "【地支关系】", "【胎元／命宫／身宫】", "【真太阳时校正】",
})
```

不禁止一般干支组合（如"戊子"）、五行术语、宫位干支。断言在 `build_benchmark_prompt()` 的 reasoned 分支中，完成 `render_reasoned_context()` 后、调用 `_assemble_reasoned_choice_prompt()` 前执行，ziwei_arm="only" 时命中任一标记 → `raise RuntimeError`（不得产生模型调用）。

---

## 8. 编排调度

### 8.1 Latin square

```
3 groups: G0 (case 1-13), G1 (case 14-27), G2 (case 28-40)
3 positions per repeat (arm shift):
  Position 0: G0→b1a_prime, G1→b1b, G2→b1c
  Position 1: G0→b1c, G1→b1a_prime, G2→b1b
  Position 2: G0→b1b, G1→b1c, G2→b1a_prime

总计: 2 years × 3 repeats × 3 positions = 18 position 行
每个 position 3 个 (group, arm) pair = 54 slices
```

分组顺序、case-id 列表写入 `audit_index.json`，记录数据哈希和分组种子。

### 8.2 调度记录

每条记录含年度字段（**关键**：slice_id 和产物目录必须有年度维度，否则 2024/2025 输出目录互相冲突）：

```json
{
  "year": "2024", "repeat": 0, "position": 0, "group": 0,
  "arm": "b1a_prime", "ziwei_arm": "none",
  "case_ids": ["C001", ..., "C013"],
  "scheduled_calls": 13, "hard_cap": 14
}
```

slice_id 必须包含年度：

```python
slice_id = (
    f"{record['year']}_{record['arm']}_"
    f"R{record['repeat']}_P{record['position']}_G{record['group']}"
)
# 示例: "2024_b1a_prime_R0_P0_G0"
```

BudgetLedger key、crash 日志路径同样使用含年度的 `slice_id`。

验证：每个 `(year, repeat, case_id, arm)` 在 54 条记录中恰好出现一次（编排器自检）。

### 8.3 每切片 hard cap 固定分配

13-case slice: scheduled=13, hard_cap=14（+1 retry reserve）
14-case slice: scheduled=14, hard_cap=16（+2 retry reserve）

36 × 14 + 18 × 16 = 504 + 288 = 792 ≤ 800

**本实验有效硬上限为 792，剩余 8 次不可动态挪用**（设计意图：800 为全局预算上限，792 为固定分配总和，差值为安全 margin）。

### 8.4 subprocess 调用

```bash
python -m benchmark.runners.run_benchmark \
  --dataset "<enriched_jsonl_path>" \
  --profile baziqa_xjz_reasoned \
  --chart-schema-version legacy_v0 \
  --arm <b1a_prime|b1b|b1c> \
  --ziwei-arm <none|only|combined> \
  --case-ids-file <case_ids_path> \
  --repeat-idx <R> \
  --n-samples 1 \
  --temperature 0 \
  --provider deepseek \
  --model deepseek-chat \
  --attempt-stage main \
  --as-of-date 2026-07-17 \
  --scheduled-calls <N> \
  --hard-cap <M> \
  --output-dir <slice_dir> \
  --case-details-jsonl <slice_dir>/details.jsonl \
  <--resume>
```

`--arm` 和 `--ziwei-arm` 独立传递。`--arm` 入 attempt key，`--ziwei-arm` 控制 formatter 和 visibility gate。

`--output-dir` 和 `--case-details-jsonl` 必须 per-slice 独立路径（`<slice_dir>/details.jsonl`），否则 54 个切片互相覆盖默认产物。

### 8.5 resume 策略（基于真实 runner 退出码）

真实 runner 在 hard cap 耗尽时返回 `3`（`run_benchmark.py:1588`），确定性问题（`MANIFEST_MISMATCH`/`ARTIFACT_EXISTS`/`MANIFEST_MISSING`）返回 `2`（`run_benchmark.py:1481`/`1488`/`1493`），正常完成返回 `0`。

| return code | 真实含义 | 编排器动作 |
|---|---|---|
| `0` | 正常完成 | 继续下一 slice |
| `2` | 确定性错误（manifest/artifact/argparse） | 立即停止阶段，不 resume |
| `3` | `BLOCKED_INCOMPLETE`（hard cap 耗尽→`_HardCapExhausted`） | 立即停止阶段，禁止 resume |
| 非预期（如 `1`、Windows 终止码） | 子进程崩溃（OOM/超时/系统异常） | 该 slice 的 `details.events.jsonl` 和 `details.manifest.json` 均存在且有效时，允许一次 `--resume` 重跑 |

**关键**：`BLOCKED_INCOMPLETE`（code 3）不得被当作"崩溃"而错误 resume。同样，code 2（确定性错误）不得 resume——继续运行只会重复失败。

第二次失败后必须保留原始 return code、stdout、stderr 到 slice 审计产物（`slices/<slice_id>/crash_retry.{returncode,stdout.log,stderr.log}`）。

### 8.6 环境变量清理

subprocess env 删除：

```text
BAZI_RAG
BAZI_RAG_CORPUS
BAZI_FEWSHOT_FILE
BAZI_APB_BLOCK
```

C2 由 CLI 保障：不传 `--phase4-exp-c2`、`--phase4-direct-c2`。

### 8.7 阶段预算账本（复用现有公式）

复用现有 `BudgetLedger`（`scripts/run_phase6_6a0_ablation.py:199`）的幂等与 fail-closed 语义。54 个独立输出目录并存时，仅依赖静态 cap 加总不足以审计实际已发起调用数（尤其 smoke、崩溃 resume 场景）。

**冻结现有 6A0 的精确公式**（`run_phase6_6a0_ablation.py:278`）：

```python
ledger.total_attempted() + (slice_run.hard_cap - already_attempted_for_slice) > stage_hard_cap
```

即只对当前 slice 按"剩余额度"预占（`hard_cap - 已消耗`），而非重复计完整 hard_cap。resume 时该公式自动适用——已完成 slice 的 `hard_cap - attempted ≈ 0`。

编排器按 slice 完成状态向 `BudgetLedger` 记账，smoke 的 13 次调用同样入账。**记账必须在 parser gate 判断之前执行**（见 §9.5），即使 smoke 因 parser rate 不足而 BLOCKED，已发起的调用也必须记录。

---

## 9. 离线阻断门禁（smoke gate）

正式实验前执行，不消耗额外 API 预算。

### 9.1 数据完整性检查

编排器启动时：
1. 2024/2025 enriched 各 40 题存在且 `chart_input.ziwei` 覆盖率 = 40/40
2. 每题 `ziwei.basic_info` 含 `ming_gong_gan_zhi`、`shen_gong_position`、`wu_xing_ju`、`ming_zhu`、`shen_zhu`
3. `ziwei.twelve_palaces` 长度为 12，`palace["name"]` 唯一
4. 每题 `ziwei.si_hua` 存在（可为空 object）

任何一项失败 → `BLOCKED_PRECONDITION`，不启动任何 runner slice。

### 9.2 上下文指纹记录（非阻断门禁）

对 3 题 × 3 arm 生成上下文并计算 SHA-256，写入 `audit_index.json` 作为"上下文指纹"而非"稳定性门禁"。变更时编排器警告但不断开——允许合法 prompt 迭代后重跑。不维护 golden snapshot hash。

**上下文一致性保证**：manifest 中已有 `dataset_sha256`、`case_ids_sha256`、`code_sha256`、`prompt_template_sha256`、`ziwei_arm` 五个字段联合冻结本次运行的上下文环境。resume 时 `check_resume_manifest()` 强制这五项与首次运行时完全一致。不再新增独立的 `context_sha256` 字段——上述五项组合已足以保证无上下文漂移。

### 9.3 B1-b 隔离预检

所有 80 题的 `render_reasoned_context(case, "legacy_v0", "only")` 不得含任何 `_BAZI_SECTION_MARKERS_B1B_FORBIDDEN` 子串。命中 → 打印违规 marker 和 case_id → `BLOCKED_B1B_CONTAMINATION`。

### 9.4 B1-a′ 隔离预检

所有 80 题的 `render_reasoned_context(case, "legacy_v0", "none")` 不得含 `【紫微斗数·本命】`。命中 → `BLOCKED_B1A_ZIWEI_LEAK`。

### 9.5 解析器 smoke（五状态机 + 退出码保护 + 预算先记账）

**关键**：runner 根据 `--case-details-jsonl <smoke>/details.jsonl` 生成的实际文件名为 `details.manifest.json` 和 `details.events.jsonl`（`run_benchmark.py:1462-1467`：`manifest_path = detail_abs[:-6] + ".manifest.json"`，`events_abs = detail_abs[:-6] + ".events.jsonl"`）。**不可另写一个同名 `manifest.json` 代替 runner 的 resume manifest。**

```python
# 路径定义（与 runner 生成规则一致）
detail_path   = smoke_dir / "details.jsonl"
manifest_path = smoke_dir / "details.manifest.json"     # runner --case-details-jsonl 派生
events_path   = smoke_dir / "details.events.jsonl"      # runner --case-details-jsonl 派生

first_record = schedule[0]
expected_smoke_keys = expected_attempt_keys_for(first_record)  # 从 schedule 精确生成

# ------ 五状态烟雾门（含 runner 退出码处理） ------

artifacts_exist = (detail_path.exists() or manifest_path.exists()
                   or events_path.exists())

if not artifacts_exist:
    # 状态 A：完全无产物 → 首次执行
    result = run_slice(first_record, output_dir=smoke_dir,
                       case_details_jsonl=str(detail_path))

elif not manifest_path.exists():
    # 状态 B：detail/events 存在但 manifest 缺失 → fail-closed
    # runner 已明文禁止（run_benchmark.py:1485-1493），编排器必须同步
    return {"status": "BLOCKED_SMOKE_ARTIFACT_CORRUPT",
            "reason": "smoke detail/events 存在但 manifest 缺失"}

elif not manifest_matches(manifest_path, first_record):
    # 状态 C：manifest 存在但与当前 first_record 不一致 → fail-closed
    return {"status": "BLOCKED_SMOKE_MANIFEST_MISMATCH",
            "reason": "smoke manifest 与当前 schedule[0] 不匹配"}

else:
    # 状态 D：manifest 匹配 → 检查 detail 完整性
    observed_smoke_keys = load_completed_keys(detail_path) if detail_path.exists() else set()

    if observed_smoke_keys == expected_smoke_keys:
        # D1：完整 → 不调用，跳过到 parser rate 重建
        result = None   # 无 subprocess 调用
    elif observed_smoke_keys < expected_smoke_keys:
        # D2：严格真子集（合法中断） → --resume 续跑
        result = run_slice(first_record, output_dir=smoke_dir,
                           case_details_jsonl=str(detail_path), resume=True)
    else:
        # D3：含额外/错误 key → fail-closed
        return {"status": "BLOCKED_SMOKE_KEY_MISMATCH",
                "reason": "observed keys 含 expected 之外的 key"}

# ------ 记账（必须在 parser gate 之前；已发起调用的次数必须入账，无论退出码） ------

calls_attempted = (
    count_call_attempts(events_path) if events_path.exists() else 0
)
ledger.record(slice_id_of(first_record), first_record["hard_cap"], calls_attempted)

# ------ runner 退出码判决（必须在 parser gate 之前） ------

if result is not None:
    if result.returncode == 2:
        # 确定性错误（manifest/artifact/argparse）——已记账，停止
        return {"status": "BLOCKED_SMOKE_RUNNER_CONFIG"}

    if result.returncode == 3:
        # hard cap 耗尽 → 已记账，停止
        return {"status": "BLOCKED_INCOMPLETE"}

    if result.returncode != 0:
        # 非预期退出（code 1、Windows 终止码等）→ 已记账，停止
        return {"status": "BLOCKED_SMOKE_CRASH"}
    # only code 0 reaches here

# ------ parser gate（仅 code 0 或无 subprocess 调用时进入） ------

details = load_jsonl(detail_path)

# 完整性验证：行数 + 无重复 key + 集合对等
detail_keys = [tuple(r["attempt_key"]) for r in details]
completed_keys = set(detail_keys)

if len(details) != len(expected_smoke_keys):
    return {
        "status": "BLOCKED_SMOKE_INCOMPLETE",
        "reason": (
            f"expected {len(expected_smoke_keys)} rows, "
            f"got {len(details)}"
        ),
    }

if len(completed_keys) != len(detail_keys):
    return {"status": "BLOCKED_SMOKE_DUPLICATE_KEY"}

if completed_keys != expected_smoke_keys:
    return {"status": "BLOCKED_SMOKE_INCOMPLETE"}

parser_rate = count_parser_valid(details) / len(expected_smoke_keys)

if parser_rate < 0.95:
    # 注意：此时 BudgetLedger 已记录实际调用次数（约 13~14 次）
    return {"status": "BLOCKED_PARSER_SMOKE", "parser_rate": parser_rate,
            "reason": f"parser 有效率不足 95%（{parser_rate:.2%}）"}

# smoke 已标记完成，标记 schedule[0] 已完成
mark_schedule_completed(first_record)

# ------ 主循环从 schedule[1:] 开始（smoke 不重复执行） ------
for record in schedule[1:]:
    run_slice(record)
```

**不重复执行**：smoke 通过后标记 schedule[0] 为已完成，主循环从 `schedule[1:]` 开始。

**失败不标记 completed**：`mark_smoke_failed()` 不能把失败的 smoke 标记成可继续的"completed"——resume 时状态机重新进入五状态判断。

**退出码语义**（与 §8.5 一致）：
- code 0：正常完成 → 进入 parser gate
- code 2：确定性错误 → BLOCKED_SMOKE_RUNNER_CONFIG，不得读取 parser rate
- code 3：hard cap 耗尽 → BLOCKED_INCOMPLETE，不得读取 parser rate
- code 1 / 其他：崩溃 → BLOCKED_SMOKE_CRASH
- 所有非零退出码路径均已通过 `ledger.record()` 入账

**is_parser_valid 定义**：`terminal_state == "parsed"`（即 `extract_reasoned_choice_answer` 返回非 None 且 `predicted` 未被设为 None）。

**合并**：
```text
smoke/details.jsonl          # 13 rows
+ remaining 53 slices         # 707 rows
= 720 rows total
```

smoke 调用计入全局 792 cap（13 calls 计入 BudgetLedger），在最终报告中标注为 smoke。

---

## 10. 完整性门禁

### 10.1 expected attempt key 生成

从 `schedule.json` 生成精确 expected attempt key 集合。`attempt key` 真实顺序（`run_benchmark.py:44-45`）：

| 下标 | 字段 |
|---|---|
| 0 | dataset_id |
| 1 | profile_id |
| 2 | arm |
| 3 | attempt_stage |
| 4 | provider |
| 5 | model |
| 6 | case_id |
| 7 | repeat_idx |
| 8 | sample_idx |
| 9 | permutation_id |

`dataset_id` 从 enrichment manifest 冻结（`baziqa_contest8_2024_holdout_enriched` / `baziqa_contest8_2025_holdout_enriched`）。

### 10.2 检查项

**关键**：`observed_keys` 必须初始化为 `set[tuple]`（非 `list`），因为后续使用 `-` 集合差集运算。同时通过 `add()` 捕获重复行。

```python
def gate_integrity(rows, schedule):
    # 0. 从 schedule 生成 expected attempt keys
    expected_keys: set[tuple] = generate_expected_attempt_keys(schedule)

    # 1. 解析 attempt_key 元组（解构存储所有命名字段，消除所有数字下标依赖）
    observed_keys: set[tuple] = set()
    observed = []
    for r in rows:
        key = tuple(r["attempt_key"])
        if key in observed_keys:
            return f"DUPLICATE_ATTEMPT_KEY: {key}"
        observed_keys.add(key)
        (dataset_id, profile_id, arm, attempt_stage, provider, model,
         case_id, repeat_idx, sample_idx, permutation_id) = key
        observed.append({
            "dataset_id": dataset_id,
            "profile_id": profile_id,
            "arm": arm,
            "attempt_stage": attempt_stage,
            "provider": provider,
            "model": model,
            "case_id": case_id,
            "repeat_idx": repeat_idx,
            "sample_idx": sample_idx,
            "permutation_id": permutation_id,
            "terminal_state": r.get("terminal_state"),
        })

    # 2. 总条数 = 720（先于集合比较，简化错误诊断）
    if len(observed) != 720:
        return f"COUNT_MISMATCH: expected=720, got={len(observed)}"

    # 3. 去重检查（observed_keys 为 set，重复行已在上方捕获）
    if len(observed_keys) != 720:
        return f"UNIQUE_KEY_MISMATCH: expected=720 unique keys, got={len(observed_keys)}"

    # 4. observed == expected（精确集合匹配）
    if observed_keys != expected_keys:
        missing = expected_keys - observed_keys
        extra = observed_keys - expected_keys
        return f"KEY_MISMATCH: missing={len(missing)}, extra={len(extra)}"

    # 5. arm 合法（实验臂，非渲染模式）
    VALID_ARMS = {"b1a_prime", "b1b", "b1c"}
    for a in observed:
        if a["arm"] not in VALID_ARMS:
            return f"INVALID_ARM: {a['arm']}"

    # 6. terminal_state 合法（代码 TERMINAL_STATES 枚举值）
    VALID_STATES = {"parsed", "invalid", "call_failed"}
    for a in observed:
        if a["terminal_state"] not in VALID_STATES:
            return f"INVALID_TERMINAL_STATE: {a['terminal_state']}"

    # 7. repeat/sample/permutation 合法（使用命名字段，不依赖 tuple 下标）
    for a in observed:
        if a["repeat_idx"] not in range(3):
            return f"INVALID_REPEAT: {a['repeat_idx']}"
        if a["sample_idx"] != 0:
            return f"INVALID_SAMPLE: {a['sample_idx']}"
        if a["permutation_id"] != "p0":
            return f"INVALID_PERMUTATION: {a['permutation_id']}"

    # 8. attempt_stage 合法（所有行均为 "main"）
    for a in observed:
        if a["attempt_stage"] != "main":
            return f"INVALID_ATTEMPT_STAGE: {a['attempt_stage']}"

    # 9. 年度分布（精确 dataset_id 子串匹配）
    d2024 = sum(1 for a in observed
                if "2024_holdout_enriched" in a["dataset_id"])
    d2025 = sum(1 for a in observed
                if "2025_holdout_enriched" in a["dataset_id"])
    if d2024 != 360 or d2025 != 360:
        return f"YEAR_DIST_MISMATCH: 2024={d2024}, 2025={d2025}"

    return "PASS"
```

**注意**：
- `observed_keys` 类型为 `set[tuple]`（非 `list`），使用 `.add()` 而非 `.append()`——确保 `missing = expected_keys - observed_keys` 和重复行检测均可执行
- `valid_arms` = `{b1a_prime, b1b, b1c}`（实验臂），不是 `{none, only, combined}`（渲染模式）
- `terminal_state` 有效集合 = `{parsed, invalid, call_failed}`（代码 `TERMINAL_STATES` at line 48 枚举值）
- **所有字段检查使用解构后命名字段**（如 `a["attempt_stage"]`、`a["repeat_idx"]`），消除 `key[6]`/`key[7]` 等数字下标依赖——`observed` 字典完整保存 `dataset_id`、`profile_id`、`attempt_stage`、`provider`、`model` 等所有解构字段
- 年度判断基于精确 enriched dataset_id 子串，不靠 `"2024" in dataset_id` 近似匹配

任何检查失败 → `BLOCKED_INCOMPLETE`，不计算 gate 或输出 PROMOTE/ROLLBACK。

---

## 11. gate 计算

```
for each year in [2024, 2025]:
  for each repeat in [0, 1, 2]:
    acc_b1a = count(correct and arm='b1a_prime') / 40   # 固定分母
    acc_b1c = count(correct and arm='b1c') / 40
    Δ(year, repeat) = acc_b1c - acc_b1a

  Δ_year = mean(Δ(year, 0), Δ(year, 1), Δ(year, 2))

Δ_dev = mean(Δ_2024, Δ_2025)
worst = min(Δ_2024, Δ_2025)

if Δ_dev >= 0.02 and worst >= -0.02:
    verdict = "PROMOTE_CANDIDATE"
else:
    verdict = "ROLLBACK"
```

B1-b accuracy 仅描述性上报。

---

## 12. 产物目录

**关键**：slice 目录必须包含年度维度（`<YYYY>_` 前缀）。2024 和 2025 使用相同的 arm/repeat/position/group，无年度前缀会导致第二年度 runner 命中第一年度已有产物 → `ARTIFACT_EXISTS` 或 `MANIFEST_MISMATCH`。

```
docs/phase6/6b1/<run_id>/
  audit_index.json          # 数据哈希、分组种子、排序规则、上下文指纹
  schedule.json             # 54 条调度记录
  budget/
    <run_id>.jsonl          # BudgetLedger 幂等账本（复用 6A0 模式，key 含年度）
  smoke/                    # smoke slice 产物（13 rows，合并入最终汇总）
    details.jsonl           # runner --case-details-jsonl 写入（13 rows）
    details.manifest.json   # runner 自动生成（--case-details-jsonl 派生）
    details.events.jsonl    # runner 自动生成（--case-details-jsonl 派生）
  slices/<YYYY>_<arm>_R<N>_P<p>_G<g>/    # 年度前缀防止两年度冲突
    details.jsonl           # runner --case-details-jsonl 写入
    details.manifest.json   # runner 自动生成（resume manifest）
    details.events.jsonl    # runner 自动生成（事件流）
    crash_retry.returncode  # 崩溃 resume 的原始 return code（仅重试路径）
    crash_retry.stdout.log  # 崩溃 resume 的 stdout（仅重试路径）
    crash_retry.stderr.log  # 崩溃 resume 的 stderr（仅重试路径）
  merged_details.jsonl      # 合并 720 条 detail（smoke + 53 slices）
  merged_events.jsonl       # 合并所有 events
  report.md                 # gate 计算 + accuracy 表 + 裁决
```

**路径一致性验证**：54 个 `slice_id` 全部唯一；2024/2025 任意同 arm/repeat/position/group 的输出目录不同。

---

## 13. Task 分解

| Task | 内容 | 依赖 |
|---|---|---|
| T1 | `render_reasoned_context()` → `chart_context.py`（复用现有 `_identity_header` + `_render_ziwei`；未知 arm → `ValueError`） | 无 |
| T2 | `visibility_requirements(profile, version, ziwei_arm=None)` + `assert_visibility(..., ziwei_arm=None)` 三臂 + 向后兼容 → `profiles.py`（`ziwei_arm is None` 时 fall through 到现有分支，不引入新函数） | 无 |
| T3 | `EvalProfile("baziqa_xjz_reasoned", ...)` + `_FORMATTER_MAP` 扩展 | 无 |
| T4 | `build_benchmark_prompt()` reasoned 路由 + `_assemble_reasoned_choice_prompt()` → `baziqa_prompt.py` | T1, T3 |
| T5 | `ziwei_arm` 三层穿透：`build_benchmark_prompt()` + `run_model_benchmark()` + `main()` 签名 | T1, T3 |
| T6 | `_phase6_visibility_filter()` 改用 `render_reasoned_context()` + 传 `ziwei_arm` | T1, T2 |
| T7 | CLI `--ziwei-arm` + `RESUME_MANIFEST_FIELDS` 新增 + `build_resume_manifest()` 新增 + reasoned answer extractor 接线（禁止 fallback 到通用解析器）+ `predictions[case_id]` 一致性 + arm↔ziwei_arm runner 侧 fail-closed 映射 + `prompt_fingerprint()` reasoned 分支 | T4, T5, T6 |
| T8 | B1-b 隔离断言（context 扫描） | T1 |
| T9 | B1-b/B1-a′ 隔离预检（离线 smoke gate §9.3-9.4） | T8 |
| T10 | smoke gate 数据完整性检查（§9.1）+ 上下文指纹（§9.2）+ 解析器 smoke（五状态机 + runner 退出码保护 + 先记账后 gate，§9.5） | T1, T7, T9 |
| T11 | `scripts/phase6_6b1_orchestrator.py`（调度含年度 slice_id、BudgetLedger 复用 6A0 公式、integrity、gate、report） | T1-T10 |

---

## 14. 测试矩阵

| 测试 | 验证对象 |
|---|---|
| `render_reasoned_context(none)` = `format_birth_line()` | T1 |
| `render_reasoned_context(only)` 含 `【紫微斗数·本命】` 且不含八字标记 | T1 |
| `render_reasoned_context(combined)` 含两者 | T1 |
| `render_reasoned_context(invalid_arm)` → `ValueError` | T1 |
| `visibility_requirements(profile, version)` 双参数调用行为不变 | T2 |
| `assert_visibility(text, profile, version)` 三参数调用行为不变 | T2 |
| `visibility_requirements(profile, version, ziwei_arm="only")` require ziwei + forbid bazi markers | T2 |
| `visibility_requirements(profile, version, ziwei_arm="combined")` require ziwei + approve both | T2 |
| reasoned extractor 正确匹配最后一条答案行 | T1 |
| reasoned extractor 兼容中英文冒号、大小写 | T1 |
| reasoned extractor 无匹配返回 None | T1 |
| `ziwei_arm` 三层穿透：传入 `"only"` → `render_reasoned_context` 收到 `"only"` | T5 |
| reasoned profile 下 reasoned extractor 提取后存入 `predictions[case_id]`（不存 raw answer） | T7 |
| reasoned profile 下正文含 A/B/C/D 但无最终答案行 → `predicted = None` → terminal_state `invalid` | T7 |
| reasoned profile 下最终答案行非法选项 + 正文含合法选项字母 → `predicted = None` → terminal_state `invalid` | T7 |
| reasoned profile 下最终答案行存在 → `meta["source"] = "reasoned_final_answer"` | T7 |
| reasoned profile 下 **禁止**执行 `extract_choice_with_meta(answer)` 或 `extract_choice(answer)` | T7 |
| detail accuracy == runner summary accuracy（同解析器，非通用 fallback） | T7 |
| `profile = resolve_profile("baziqa_xjz_reasoned"); fingerprint = prompt_fingerprint(profile)` 含 reasoned 源码指纹（`_assemble_reasoned_choice_prompt`、`render_reasoned_context`、`extract_reasoned_choice_answer`） | T7 |
| `build_resume_manifest` 含 `ziwei_arm`；resume 同值通过、异值拒绝 | T7 |
| arm↔ziwei_arm 映射：`b1b`+`ziwei_arm="combined"` → SystemExit(2) | T7 |
| `--ziwei-arm` 未传时 runner 内 reasoned profile → SystemExit(2) | T7 |
| B1-b 上下文不含 forbidden bazi markers（单题） | T8 |
| B1-a′ 上下文不含 `【紫微斗数·本命】`（单题） | T9 |
| schedule 54 slice_id 全部唯一（含年度维度） | T11 |
| 2024/2025 任意同 arm/repeat/position/group → slice_id 不同、输出目录不同 | T11 |
| integrity expected==observed；重复 key → DUPLICATE；缺失 key → KEY_MISMATCH | T11 |
| smoke gate: 数据完整性通过真实 enriched 40 题 | T10 |
| smoke gate: parser ≥ 95% 通过 | T10 |
| smoke: 完全无产物 → 首次执行 | T10 |
| smoke: detail/events 存在但 manifest 缺失 → BLOCKED_SMOKE_ARTIFACT_CORRUPT | T10 |
| smoke: manifest 存在但 keys 为 expected 严格子集 → --resume 续跑 | T10 |
| smoke: manifest 存在且 keys 完整匹配 → 跳过调用、重建 rate | T10 |
| smoke: manifest 存在但 observed keys 含 extra → BLOCKED_SMOKE_KEY_MISMATCH | T10 |
| smoke parser < 95% 时 BudgetLedger 仍记录已发起调用次数 | T10 |
| smoke code 2 → 记账后 BLOCKED_SMOKE_RUNNER_CONFIG（不读取 parser rate） | T10 |
| smoke code 3 → 记账后 BLOCKED_INCOMPLETE（不读取 parser rate） | T10 |
| smoke code 1 / 非零 → 记账后 BLOCKED_SMOKE_CRASH | T10 |
| smoke detail 含重复 attempt key → BLOCKED_SMOKE_DUPLICATE_KEY（不计算 parser rate） | T10 |
| smoke code 0 但 detail keys 不完整 → BLOCKED_SMOKE_INCOMPLETE（不得计算 parser rate） | T10 |
| subprocess 退出码 3 → BLOCKED_INCOMPLETE 停止（不 resume） | T11 |
| subprocess 退出码 2 → 立即停止（不 resume） | T11 |
| BudgetLedger resume 公式：`total + (hard_cap - attempted) <= 792` | T11 |

---

## 15. 变更清单 vs v7

| # | v7 问题 | v8 修正 |
|---|---|---|
| 1 | reasoned parser 接线中 `predicted = extract_reasoned_choice_answer(answer)` 后，runner 仍执行 `meta = extract_choice_with_meta(answer)` followed by `if predicted is None: predicted = meta['choice']` → 通用解析器从推理正文抓出选项字母，将 `invalid` 变成 `parsed` | reasoned 分支完全替换解析块：`if profile_formatter == 'format_reasoned_choice_prompt': predicted = extract_reasoned_choice_answer(answer); meta = {"choice": predicted, "source": "reasoned_final_answer", "valid": predicted is not None}; predictions[case_id] = predicted` — **禁止**执行 `extract_choice_with_meta` 或 `extract_choice`。测试覆盖：正文有选项无最终答案行→`invalid`；最终答案行非法但正文含选项→`invalid`；最终答案行存在→`source="reasoned_final_answer"` |
| 2 | smoke `run_slice()` 调用后未检查退出码 → code 2/3/1 时仍继续加载 detail、计算 parser rate，可能除零或产生错误结论 | 在记账后、parser gate 前插入退出码判决：code 2→BLOCKED_SMOKE_RUNNER_CONFIG；code 3→BLOCKED_INCOMPLETE；code≠0→BLOCKED_SMOKE_CRASH。只有 code 0（或 D1 无 subprocess）才进入 parser rate。code 0 后增加 keys 完整性验证（不完整→BLOCKED_SMOKE_INCOMPLETE）。所有路径均已先执行 `ledger.record()` |
| 3 | `prompt_fingerprint()` 对 reasoned formatter 无显式分支 → 落入 `else` 分支即 `format_multi_turn` 源码指纹（`profiles.py:157`） | 新增 `elif formatter == "format_reasoned_choice_prompt"` 分支，含 `render_reasoned_context`、`_assemble_reasoned_choice_prompt`、`extract_reasoned_choice_answer` 三个函数的源码指纹。测试：`profile = resolve_profile("baziqa_xjz_reasoned"); fingerprint = prompt_fingerprint(profile)` 返回 reasoned 源码指纹 |

## 16. 变更清单 vs v8

| # | v8 问题 | v9 修正 |
|---|---|---|
| 1 | `prompt_fingerprint()` 分支引用 `baziqa_prompt.format_reasoned_choice_prompt`，但实际创建的函数是 `_assemble_reasoned_choice_prompt` → 运行期 `AttributeError` | 改为 `inspect.getsource(baziqa_prompt._assemble_reasoned_choice_prompt)`。§7.2 断言位置描述同步更新为 `build_benchmark_prompt()` reasoned 分支中执行。测试：`profile = resolve_profile("baziqa_xjz_reasoned"); fingerprint = prompt_fingerprint(profile)` |
| 2 | smoke 完整性验证仅比较 key 集合，不检测行数与重复 key → 14 行含 1 个重复 key 时 `len(completed_keys)=13=len(expected_smoke_keys)` 通过，随后 `parser_rate/13` 可能 >100% | 三步验证：行数 `len(details)` 对等 → `len(completed_keys)==len(detail_keys)` 检测重复 → 集合对等。新增 `BLOCKED_SMOKE_DUPLICATE_KEY` 状态。分母改用 `len(expected_smoke_keys)` 防除零。测试：smoke detail 含重复 attempt key→BLOCKED_SMOKE_DUPLICATE_KEY，不计算 parser rate |
