# 6B1-D 代码骨架位置（审核通过后实现）

## 0. 文件清单（必须全部修改）

| 文件 | 需修改位置 | 功能 |
|---|---|---|
| `benchmark/formatters/chart_context.py` | `render_reasoned_context()` (line 281) | 新增 2 个 ziwei_arm |
| `benchmark/runners/run_benchmark.py` | CLI --ziwei-arm choices (line 1477) | 扩展 CLI 可接受值 |
| `benchmark/runners/run_benchmark.py` | `_REASONED_ARM_MAP` 字典 (line 1497) | 认识新 arm 名称（字典扩展，非 allowlist） |
| `benchmark/runners/profiles.py` | visibility matrix (line 103) | 新 arm 的 required/forbidden 字段 |
| `scripts/phase6_6b1d_orchestrator.py` | 新文件（基于 6B1 复制） | 主 orchestrator |
| `tests/test_chart_context.py` | 新增 4 组测试 | 新 arm 的单元测试 |
| `tests/test_phase6_6b1d.py` | 新文件 | orchestrator 集成测试 |

---

## 1. chart_context.py（新增 2 个 ziwei_arm）

**文件**: `benchmark/formatters/chart_context.py`

**函数**: `render_reasoned_context()` (line 281)

**修改前的有效可接受值**：`none`, `only`, `combined`

**6B1-D 新增**：

```python
# 现有选项（保持不变，与 6B1 逐字节等价）:
# - "none" -> b1a_prime（八字基线，legacy_v0）
# - "only" -> b1b（仅紫微）
# - "combined" -> b1c（八字+紫微联合）

# 6B1-D 新增选项（审核后实现）:
# - "ziwei_mini"  -> b2b（精简紫微）
# - "sequential"  -> b2c（顺序推理）

# 实现位置：line 319 之后新增分支
if ziwei_arm == "ziwei_mini":
    # 精简紫微上下文（冻结输出 schema）
    # 数据来源：chart_input.ziwei.twelve_palaces[]（真实 BaziQA enriched schema）
    # - 固定段标：【紫微斗数·精简】
    # - 固定子段标：【命宫】、【身宫】、【主星】
    # - 命宫：palace["name"] == "命宫"，输出格式: 【命宫】星名（亮度）
    # - 身宫：palace["is_shengong"] is True，输出格式: 【身宫】星名（亮度）
    # - 命宫与身宫重合时：输出一次，标注"命身同宫"
    # - 缺失身宫时：输出"【身宫】未标注"
    # - 主星：palace["main_stars"]（每颗含 name, brightness）
    # - 排除：auxiliary_stars、daxian、si_hua 和其他宫位
    # - visibility required 检查：【紫微斗数·精简】、【命宫】、【身宫】、【主星】
    pass
elif ziwei_arm == "sequential":
    # 顺序推理上下文
    # - 第一部分：八字完整排盘（format_birth_line(case)）
    # - 显式分隔线："--- 八字分析结束 ---"
    # - 第二部分：紫微完整排盘（_render_ziwei(ziwei_data)）
    # - 显式推理指令：
    #   "请先基于八字信息进行初步分析，"
    #   "再基于紫微斗数信息进行补充判断，"
    #   "综合两者得出结论。"
    pass

# 注意：修改 docstring 中的 Raises 部分，加入新值
```

---

## 2. run_benchmark.py（CLI 和映射）

**文件**: `benchmark/runners/run_benchmark.py`

### 2.1 CLI choices 扩展（line 1477）

```python
# 当前代码：
# choices=["none", "only", "combined"]

# 6B1-D 修改为：
choices=["none", "only", "combined", "ziwei_mini", "sequential"]
```

### 2.2 `_REASONED_ARM_MAP` 字典扩展（line 1497）

**关键**：真实 runner 使用字典取值 `expected_ziwei = _REASONED_ARM_MAP[args.arm]`，不是简单 allowlist。必须扩展字典本身：

```python
# 当前代码（line 1497-1501）：
_REASONED_ARM_MAP = {
    "b1a_prime": "none",
    "b1b": "only",
    "b1c": "combined",
}

# 6B1-D 修改为：
_REASONED_ARM_MAP = {
    "b1a_prime": "none",
    "b1b": "only",
    "b1c": "combined",
    "b2b": "ziwei_mini",
    "b2c": "sequential",
}
```

这样 `args.arm not in _REASONED_ARM_MAP` 检查和 `expected_ziwei = _REASONED_ARM_MAP[args.arm]` 取值都会正确工作。

---

## 3. profiles.py（visibility matrix）

**文件**: `benchmark/runners/profiles.py` (line 103)

**为每个新 arm 定义 required/forbidden 字段**：

```python
# b2b (ziwei_mini):
#   required: 固定段标【紫微斗数·精简】、【命宫】、【身宫】、【主星】
#   forbidden: 八字四柱关键词 + 真实裸名宫位（不含"宫"后缀）：
#     父母、福德、田宅、官禄、仆役、迁移、疾厄、财帛、子女、夫妻、兄弟
#   必须继续包含通用 _DENYLIST_MARKERS（与现有 arm 一致）
#   命身同宫时仍必须输出【命宫】、【身宫】、【主星】三个 required 标记

# b2c (sequential):
#   required: 身份头、完整八字、完整紫微、"--- 八字分析结束 ---"分隔线、顺序推理指令
#   forbidden: 不能为空，至少应与 combined 臂一样禁止 _DENYLIST_MARKERS
#   （即继承 combined 臂的 forbidden 集合，而非空集合）

# 必须 fail-closed：任何未在 visibility matrix 中明确定义的
# arm 必须立即 raise NotImplementedError（库函数层）
# runner 层捕获后转换为 SystemExit(2)（CLI层）
# 分别测试两层契约
```

---

## 4. phase6_6b1d_orchestrator.py（新文件）

**基于**：`phase6_6b1_orchestrator.py` 复制后全面修改

**必须逐项检查并修改的硬编码**：

### 4.1 常量冻结（与 6B1 一致的部分）

```python
REASONED_PROFILE = "baziqa_xjz_reasoned"
CHART_SCHEMA = "legacy_v0"   # 与 6B1 相同，非 approved_v1

YEAR_DATASETS = {
    "2024": "benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl",
    "2025": "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl",
}
```

### 4.2 ARM_ZIWEI_MAP 扩展（5 臂）

```python
ARM_ZIWEI_MAP = {
    "b1a_prime": "none",
    "b1b": "only",
    "b1c": "combined",
    "b2b": "ziwei_mini",
    "b2c": "sequential",
}
ARMS = list(ARM_ZIWEI_MAP.keys())
YEARS = ["2024", "2025"]
REPEATS = [0, 1, 2]
QUESTIONS_PER_CELL = 40
```

### 4.3 5 组 × 8 题布局

```python
# 原 6B1: SLICE_LAYOUT = [13, 14, 13]（3 组）
# 6B1-D: 5 组，每组 8 题
SLICE_LAYOUT = [8, 8, 8, 8, 8]
GROUPS_PER_CELL = 5
SLICE_SIZE = 8
```

### 4.4 5×5 Latin Square（替换原 3×3）

```python
# 原 6B1: 3×3 Latin square
# 6B1-D: 5×5 Latin square
LATIN_SQUARE = {
    0: {0: "b1a_prime", 1: "b1b",      2: "b1c",   3: "b2b",   4: "b2c"},
    1: {0: "b1c",       1: "b2b",      2: "b2c",   3: "b1a_prime", 4: "b1b"},
    2: {0: "b2b",       1: "b2c",      2: "b1a_prime", 3: "b1b",  4: "b1c"},
    3: {0: "b2c",       1: "b1a_prime", 2: "b1b",   3: "b1c",   4: "b2b"},
    4: {0: "b1b",       1: "b1c",      2: "b2b",   3: "b2c",   4: "b1a_prime"},
}
```

#### 4.4.1 generate_schedule() 嵌套循环顺序（冻结）

```python
# schedule 生成顺序（冻结，保证五 smoke ID 稳定）：
# position (0-4) → year (2024, 2025) → repeat (0-2) → group (0-4)
#
# 前 5 个 slice 正好是五个 smoke：
# slice 0: position 0, year 2024, repeat 0, group 0 → b1a_prime
# slice 1: position 0, year 2024, repeat 0, group 1 → b1b
# slice 2: position 0, year 2024, repeat 0, group 2 → b1c
# slice 3: position 0, year 2024, repeat 0, group 3 → b2b
# slice 4: position 0, year 2024, repeat 0, group 4 → b2c
#
# --from-slice 5 可一次性跳过全部 smoke，且顺序稳定。
# 必须测试：前 5 个 slice ID 正好是上述五个 arm
```

### 4.5 预算执行模型（动态 effective cap，真实可实现）

**架构约束**：orchestrator 只能在 slice 启动前和完成后更新 ledger，无法逐调用控制子进程。runner 负责创建和校验 manifest，orchestrator 不能预先写一个不完整的 slice manifest。

**持久化所有权（冻结）**：`effective_cap` 的分配值由 orchestrator 写入独立的 `budget_ledger.json`，**不写入 slice manifest**（slice manifest 由 runner 创建）。

```python
# 冻结的启动顺序：
# 1. orchestrator 在 budget_ledger.json 中原子持久化 allocated_cap_by_slice[slice_id]
# 2. orchestrator 调用 runner，传入 --hard-cap effective_cap
# 3. runner 正常创建 manifest，hard_cap 字段即分配值
# 4. resume 时必须同时验证：
#    a. ledger 中的 allocated_cap_by_slice[slice_id]
#    b. runner manifest 中的 hard_cap
#    c. 两者必须一致，否则 fail-closed
# 5. ledger 有分配但 runner 无任何产物时，允许使用原分配首跑
# 6. runner manifest 存在但 ledger 分配缺失时，fail-closed
# 7. resume 预算检查使用：
#    total_attempted + (effective_cap - already_attempted_for_slice) <= 1320

SLICE_BASE_CALLS = 8          # 每 slice scheduled 调用数
SLICE_RESERVE = 2             # 本地重试空间
SLICE_MAX_CAP = SLICE_BASE_CALLS + SLICE_RESERVE  # 10
GLOBAL_LEDGER_CAP = 1320     # 全局硬上限

def compute_effective_cap(slice_id, ledger, already_attempted_for_slice):
    """首次启动分配 cap，写入 BudgetLedger._data["allocated_cap_by_slice"]。
    resume 从 ledger 读取，不重新分配，但必须执行全局预算公式检查。
    
    统一使用 BudgetLedger 对象，不引入第二套 ledger_db/atomic_write_ledger 接口。
    
    already_attempted_for_slice: 必须显式传入，无默认值。
    来源：ledger._data["calls_attempted_by_slice"][slice_id]（经 events reconciliation 后的值）。
    resume 前必须先完成 events -> ledger reconciliation，再计算预算。
    """
    # 0. 验证 already_attempted_for_slice 已显式传入且合法（fresh/resume 之前统一检查）
    if already_attempted_for_slice is None:
        raise SystemExit(2)  # 调用者必须显式传入
    if already_attempted_for_slice < 0:
        raise SystemExit(2)  # 非法值
    
    cumulative_calls = ledger._data["total_calls_attempted"]
    allocations = ledger._data.setdefault("allocated_cap_by_slice", {})
    
    # 1. 检查 budget_ledger 是否已有分配（resume 路径）
    if slice_id in allocations:
        effective_cap = allocations[slice_id]
        # 1.1 验证 already_attempted 不超过 cap
        if already_attempted_for_slice > effective_cap:
            raise SystemExit(2)  # 超出 cap
        # 1.2 执行冻结的 resume 预算公式：
        #     total_attempted + (effective_cap - already_attempted_for_slice) <= 1320
        remaining_budget = cumulative_calls + (effective_cap - already_attempted_for_slice)
        if remaining_budget > GLOBAL_LEDGER_CAP:
            print(json.dumps({"status": "BLOCKED_BUDGET_EXHAUSTED",
                             "slice_id": slice_id,
                             "cumulative_calls": cumulative_calls,
                             "effective_cap": effective_cap,
                             "already_attempted": already_attempted_for_slice,
                             "projected_total": remaining_budget}))
            raise SystemExit(2)
        return effective_cap   # resume 沿用历史分配
    
    # 2. 首次分配
    global_remaining = GLOBAL_LEDGER_CAP - cumulative_calls
    effective_cap = min(SLICE_MAX_CAP, global_remaining)
    
    if effective_cap < SLICE_BASE_CALLS:
        # 无法保证基础调用数，耗尽终止
        print(json.dumps({"status": "BLOCKED_BUDGET_EXHAUSTED",
                         "slice_id": slice_id,
                         "cumulative_calls": cumulative_calls,
                         "remaining": global_remaining}))
        raise SystemExit(2)
    
    # 3. 原子写入 BudgetLedger（使用现有 _save，不引入 atomic_write_ledger）
    allocations[slice_id] = effective_cap
    ledger._save()
    return effective_cap

# BudgetLedger schema 扩展（冻结）：
# 在默认 schema 和加载校验中正式加入 "allocated_cap_by_slice": {}
# 加载校验规则：
# - 必须是 dict
# - key 必须属于 schedule 中的 slice_id
# - cap 必须是 8..10 的整数
# - completed/resume slice 的 allocation 与 manifest hard_cap 一致

# 冻结调用点（orchestrator main loop 中，无循环依赖）：
# 完整顺序见下方 reconcile_partial_events 之后的"冻结的 resume 调用顺序"段落。
# 这里仅声明：集成测试必须验证 main/fake-runner 路径确实调用了 compute_effective_cap。
# 禁止使用旧的"effective_cap -> reconcile -> compute_effective_cap"循环顺序。

def verify_cap_consistency_on_resume(slice_id, runner_manifest, ledger):
    """resume 时验证 ledger 分配值与 runner manifest hard_cap 一致。
    
    统一使用 BudgetLedger 对象，不引入第二套 ledger_db 接口。
    """
    ledger_cap = ledger._data.get("allocated_cap_by_slice", {}).get(slice_id)
    manifest_cap = runner_manifest.get("hard_cap")
    
    if ledger_cap is None and manifest_cap is None:
        return  # 两者都无，首跑
    if ledger_cap is None and manifest_cap is not None:
        raise SystemExit(2)  # runner manifest 存在但 ledger 缺失 -> fail-closed
    if ledger_cap is not None and manifest_cap is None:
        return  # ledger 有分配但 runner 无产物 -> 允许首跑
    if ledger_cap != manifest_cap:
        raise SystemExit(2)  # 两者不一致 -> fail-closed
    return ledger_cap  # 返回已分配的 cap，供后续步骤使用
```

**重要声明（冻结）**：总 reserve 只有 120，不能保证 150 个 slice 都有完整 2 次重试。动态分配保证先启动的 slice 有重试空间，预算耗尽时优雅终止。不声称"每个 slice 都至少有 2 次重试"。

### 4.6 预算数字

```python
TOTAL_SCHEDULED_CALLS = 1200   # 5 arms × 5 groups × 2 years × 3 repeats × 8
TOTAL_SLICES = 150              # 5 × 5 × 2 × 3
```

### 4.7 Experiment/Run/Archive ID

```python
# 必须完全独立于 6B1
ARCHIVE_ROOT = "docs/phase6/6b1d"  # 非 6b1
EXPERIMENT_ID_PREFIX = "6b1d"
# experiment_id: 6b1d-2026-07-22-deepseek-deepseek-chat-<fingerprint>
# 必须写测试确认不会写入或读取 6B1 归档目录
```

### 4.8 Schedule/Context/Code Fingerprint

```python
# CHART_SCHEMA = "legacy_v0"（不变）
# PROMPT_TEMPLATE_SHA256：reasoned_choice 模板未变，与 6B1 相同

# CODE_FINGERPRINT：必须重新计算，且 scope 必须包含新 orchestrator 自身
# 冻结 scope 列表：
FINGERPRINT_SCOPE = [
    "scripts/phase6_6b1d_orchestrator.py",   # 自身（不是 6b1）
    "benchmark/runners/run_benchmark.py",
    "benchmark/formatters/chart_context.py",
    "benchmark/formatters/baziqa_prompt.py",
    "benchmark/runners/profiles.py",
]

# 必须测试：
# 1. 仅修改 phase6_6b1d_orchestrator.py 也会改变 code fingerprint
# 2. 修改任意 scope 内文件都会改变 fingerprint
# 3. b1a'/b1b/b1c 的 context 与 6B1 逐字节等价
# 4. fingerprint 不匹配时 resume 被拒绝
```

### 4.9 Token 统计（冻结）

```python
# Token 计数优先级：
# 1. 优先使用 provider 返回的 usage 字段（DeepSeek API response）
# 2. 若 provider 未返回且 tiktoken 已安装，使用 tiktoken cl100k_base 离线估算
# 3. tiktoken 版本冻结：tiktoken==0.5.2
# 4. tiktoken 必须加入 requirements-dev.txt（不是 pyproject.toml dev extras）
# 5. 若 tiktoken 未安装，跳过离线估算，报告中标注 "NOT_AVAILABLE"
# 6. 缺少 provider usage 且未安装 tiktoken 时，token 对比结论只能标为 NOT_AVAILABLE，
#    不能算作实验指标完成
# 7. 输出报告包含：五臂平均输入 token、输出 token、总 token
# 8. 仅作描述性统计，不做 token 显著度检验
```

---

### 4.10 Manifest 验证

```python
# verify_slice_manifest() 必须覆盖所有 5 个 arm
# - scheduled_calls：必须与 slice size 一致（每 slice 8），字段名与 runner manifest 和 RESUME_MANIFEST_FIELDS 一致
# - fingerprint 漂移检测：拒绝执行 fingerprint 不匹配的 resume
# - resume drift 检测：expected-set 必须与已完成的精确匹配
# - effective_cap 从 budget_ledger.json 读取（权威来源）
# - manifest 的 hard_cap 仅作一致性交叉验证，不是权威来源
# - ledger allocated_cap 与 manifest hard_cap 不一致时 fail-closed
```

### 4.11 Integrity Expected-Set

```python
# integrity_check() 的 expected_count = 1200
# 按五臂验证：每臂 240 records（5 groups × 2 years × 3 repeats × 8）
```

### 4.12 Report 输出

```python
# compute_gate()：改为 generate_comparison_table()
# - 五臂准确率排序
# - 两两差值表
# - Bootstrap CI（seed=42, 10k draws, year×question 聚类）
# - 所有表述必须为描述性，不含"显著"、"确认"等词
```

### 4.13 Smoke 配置（五臂 smoke 完整状态机）

**关键改动**：现有 6B1 orchestrator 是单 smoke 结构（`schedule["slices"][0]`），6B1-D 必须改为**五 smoke 结构**。

#### 4.13.1 五 smoke 选择与固定顺序

```python
# 从 schedule 中选取每臂第一个 slice 作为 smoke
# 固定顺序：b1a' -> b1b -> b1c -> b2b -> b2c
SMOKE_ARMS_ORDER = ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]

# smoke slice ID 集合（不是固定索引）
SMOKE_SLICE_IDS = set()
for arm in SMOKE_ARMS_ORDER:
    for sl in schedule["slices"]:
        if sl["arm"] == arm:
            SMOKE_SLICE_IDS.add(sl["slice_id"])
            break
```

#### 4.13.2 五 smoke 状态机

**状态集合（冻结）**：`fresh`、`resume`、`completed`、`blocked_corrupt`

**注意**：schedule slice 本身没有 `status` 字段。状态由 ledger + manifest + events + details 联合判定，复用 6B1 现有证据链。**runner manifest 没有 `records_expected`/`records_actual` 字段，禁止使用这两个字段判断 completed。**

```python
# 直接复用 6B1 已批准的状态机实现（scripts/phase6_6b1_orchestrator.py:1540）
# 不另写一套近似状态机

# 终态字段：terminal_state（不是 is_terminal）
# 终态集合：{"parsed", "invalid", "unresolved", "call_failed"}
TERMINAL_STATES = {"parsed", "invalid", "unresolved", "call_failed"}

def determine_smoke_state(smoke_sl):
    """直接复用 6B1 五状态判定逻辑。
    
    路径来源：schedule 中已冻结的 smoke_sl["detail_path"]/events_path/manifest_path
    （不自行拼接 smoke_<arm> 路径）
    """
    smoke_detail = Path(smoke_sl["detail_path"])
    smoke_manifest = Path(smoke_sl["manifest_path"])
    smoke_events = Path(smoke_sl["events_path"])
    
    detail_exists = smoke_detail.exists()
    manifest_exists = smoke_manifest.exists()
    events_exists = smoke_events.exists()
    
    # 1. 无任何产物 -> fresh
    if not detail_exists and not manifest_exists and not events_exists:
        return "fresh"
    
    # 2. detail + manifest 都存在 -> 检查终态数量
    if detail_exists and manifest_exists:
        rows = load_jsonl(str(smoke_detail))
        # 使用 terminal_state 字段（不是 is_terminal）
        terminal_count = sum(
            1 for r in rows
            if r.get("terminal_state") in TERMINAL_STATES
        )
        if terminal_count >= smoke_sl["size"]:
            return "completed"
        else:
            return "resume"
    
    # 3. manifest 存在但 detail 不存在 -> 合法 resume
    # （runner 会在首次模型调用前先写 manifest，这是合法可恢复状态）
    if manifest_exists and not detail_exists:
        return "resume"
    
    # 4. detail 存在但 manifest 不存在 -> blocked_corrupt
    if detail_exists and not manifest_exists:
        return "blocked_corrupt"
    
    # 5. 其他情况 -> blocked_corrupt
    return "blocked_corrupt"

def verify_smoke_completed(smoke_sl, args, ledger):
    """completed 状态的完整验证，直接复用 6B1 完整验证路径
    （scripts/phase6_6b1_orchestrator.py:1575-1634）。
    
    不只检查 events 和 ledger，必须验证全部 7 项证据。
    验证成功后执行原子 ledger reconciliation。
    """
    smoke_detail = Path(smoke_sl["detail_path"])
    smoke_manifest = Path(smoke_sl["manifest_path"])
    smoke_events = Path(smoke_sl["events_path"])
    
    # 1. events 必须存在
    if not smoke_events.exists():
        return False, "completed state but events file missing"
    
    # 2. verify_slice_manifest 全字段指纹（复用 6B1 函数）
    ok, diff = verify_slice_manifest(smoke_sl, args.provider, args.model)
    if not ok:
        return False, f"smoke manifest 与当前配置不一致: {diff}"
    
    # 3. expected attempt-key 集合完全相等（复用 6B1 build_expected_key）
    rows = load_jsonl(str(smoke_detail))
    detail_keys = [tuple(r.get("attempt_key", [])) for r in rows]
    completed_keys = set(detail_keys)
    dataset_id = os.path.splitext(os.path.basename(smoke_sl["dataset"]))[0]
    expected_keys = set()
    for case_id in smoke_sl["case_ids"]:
        expected_keys.add(build_expected_key(
            dataset_id, REASONED_PROFILE, smoke_sl["arm"],
            case_id, smoke_sl["repeat"], args.provider, args.model,
        ))
    
    # 4. details 数量 == expected 数量
    if len(detail_keys) != len(expected_keys):
        return False, f"details 数量不匹配: expected={len(expected_keys)} got={len(detail_keys)}"
    
    # 5. 无重复 attempt key
    if len(completed_keys) != len(detail_keys):
        return False, "存在重复 attempt key"
    
    # 6. completed keys == expected keys（防止错误题目的产物）
    if completed_keys != expected_keys:
        return False, "completed keys != expected keys"
    
    # 7. parser rate（8 题 -> 必须 8/8 = 100%）
    parse_ok = sum(1 for r in rows if r.get("terminal_state") == "parsed")
    parser_rate = parse_ok / len(rows) if rows else 0
    if parser_rate < SMOKE_PARSER_RATE_THRESHOLD:
        return False, f"parser_rate={parser_rate} < {SMOKE_PARSER_RATE_THRESHOLD}"
    
    # 8. events 可解析 + 调用数 ∈ [scheduled, hard_cap]（复用 _validate_events）
    ev_ok, calls, ev_reason = _validate_events(
        str(smoke_events), smoke_sl["size"], smoke_sl["hard_cap"])
    if not ev_ok:
        return False, f"events validation failed: {ev_reason}"
    
    # 9. 事务式 ledger reconciliation（先在副本上验证，全部通过后一次性提交）
    # 9.1 在副本上重算（不修改原 ledger 内存）
    new_calls_by_slice = dict(ledger._data["calls_attempted_by_slice"])
    new_calls_by_slice[smoke_sl["slice_id"]] = calls
    new_total = sum(new_calls_by_slice.values())
    # 9.2 预算检查：reconciliation 后的总数不超过 hard_cap
    if new_total > ledger.hard_cap:
        return False, f"BUDGET_EXCEEDED after reconciliation: total={new_total}"
    # 9.3 验证 total == 各 slice 之和（副本上验证）
    if new_total != sum(new_calls_by_slice.values()):
        return False, f"ledger total mismatch: new_total={new_total}"
    # 9.4 全部验证通过，一次性替换内存状态
    ledger._data["calls_attempted_by_slice"] = new_calls_by_slice
    ledger._data["total_calls_attempted"] = new_total
    # 9.5 记录 slice 为 completed（slices_completed 是 list，带去重判断）
    if smoke_sl["slice_id"] not in ledger._data["slices_completed"]:
        ledger._data["slices_completed"].append(smoke_sl["slice_id"])
    # 9.6 原子保存（BudgetLedger._save() 已调用 atomic_write_json）
    ledger._save()
    
    return True, "ok"

def reconcile_partial_events(sl, ledger, allocated_cap):
    """Partial resume 的证据回算 helper。
    
    用于崩溃后已产生部分调用的 slice（smoke 或普通 slice）。
    与 verify_smoke_completed 不同，本函数：
    - 允许调用数小于 scheduled_calls；
    - 不要求 details 完整、expected keys 完全相等、parser 8/8；
    - 不标记 slice 为 completed；
    - 只按 events 中的 call_attempt 回算 ledger。
    
    参数 allocated_cap：从 ledger._data["allocated_cap_by_slice"] 读取的历史分配值
    （不是 compute_effective_cap 的返回值，避免循环依赖）。
    
    复用 6B1 的 _validate_partial_events 语义。
    
    Manifest-only 状态处理（events 不存在）：
    - events 不存在时，不调用 _validate_partial_events（避免 events file missing 阻断）
    - 仅真正 manifest-only（manifest 存在、details 不存在、ledger 历史调用数为 0）时返回 0
    - 若 details 已存在或 ledger 历史调用数非零，说明调用证据丢失，BLOCKED_EVIDENCE_LOST
    """
    events_path = sl["events_path"]
    events_exists = os.path.exists(events_path)
    
    # 1. Manifest-only 状态严格判定（events 不存在）
    if not events_exists:
        details_exists = os.path.exists(sl["detail_path"])
        ledger_calls = ledger._data["calls_attempted_by_slice"].get(sl["slice_id"], 0)
        
        # 仅当 manifest 存在、details 不存在、ledger 历史调用数为 0 时才是合法 manifest-only
        # 否则说明调用证据丢失，必须 fail-closed
        if details_exists or ledger_calls != 0:
            print(json.dumps({"status": "BLOCKED_EVIDENCE_LOST",
                             "slice_id": sl["slice_id"],
                             "reason": "events missing but details exists or ledger_calls non-zero",
                             "details_exists": details_exists,
                             "ledger_calls": ledger_calls}, ensure_ascii=False))
            raise SystemExit(2)
        
        # 真正的 manifest-only：无证据可回算，already_attempted = 0
        return 0
    
    # 2. events 存在：解析，只统计 kind == "call_attempt"，允许 calls < scheduled_calls
    #    拒绝损坏 JSON 和调用数超过 allocated_cap
    ok, calls, reason = _validate_partial_events(events_path, allocated_cap)
    if not ok:
        print(json.dumps({"status": "BLOCKED_PARTIAL_EVENTS_CORRUPT",
                         "slice_id": sl["slice_id"],
                         "reason": reason}, ensure_ascii=False))
        raise SystemExit(2)
    
    # 3. 事务式 ledger 回算（先在副本上验证，全部通过后一次性提交）
    new_calls_by_slice = dict(ledger._data["calls_attempted_by_slice"])
    new_calls_by_slice[sl["slice_id"]] = calls
    new_total = sum(new_calls_by_slice.values())
    
    # 4. 预算检查：回算后的总数不超过 hard_cap
    if new_total > ledger.hard_cap:
        print(json.dumps({"status": "BUDGET_EXCEEDED",
                         "slice_id": sl["slice_id"],
                         "new_total": new_total}, ensure_ascii=False))
        raise SystemExit(2)
    
    # 5. 全部验证通过，一次性替换内存状态（不加入 slices_completed）
    ledger._data["calls_attempted_by_slice"] = new_calls_by_slice
    ledger._data["total_calls_attempted"] = new_total
    ledger._save()
    
    return calls

# 冻结的 resume 调用顺序（orchestrator main loop，无循环依赖）：
# 1. determine_smoke_state(sl) -> 判断状态
# 2. 若 completed:
#    a. verify_smoke_completed(sl, args, ledger) -> 完整验证 + reconciliation
#    b. effective_cap = ledger._data["allocated_cap_by_slice"][sl["slice_id"]]
#    c. 跳过该 slice
# 3. 若 resume（partial 或 manifest-only）:
#    a. allocated_cap = ledger._data["allocated_cap_by_slice"].get(sl["slice_id"])
#       （从 ledger 读取历史分配，不依赖 compute_effective_cap）
#    b. 若 runner manifest 存在:
#       verify_cap_consistency_on_resume(sl["slice_id"], runner_manifest, ledger)
#       -> 校验 allocated_cap 与 manifest hard_cap 一致
#    c. already_attempted = reconcile_partial_events(sl, ledger, allocated_cap)
#       （events 存在则回算；manifest-only 时返回 0）
#    d. effective_cap = compute_effective_cap(sl["slice_id"], ledger, already_attempted)
#       （执行全局预算公式验证，返回 allocated_cap）
#    e. 传入 --hard-cap effective_cap 启动 runner
# 4. 若 fresh:
#    a. already_attempted = 0（显式传入）
#    b. effective_cap = compute_effective_cap(sl["slice_id"], ledger, already_attempted)
#    c. 传入 --hard-cap effective_cap 启动 runner

# 五 smoke 逐个执行处理分支（与 6B1 一致）：
# - fresh: 执行 smoke run
# - resume: 执行 resume 恢复（合法，包括 manifest-only 状态）
# - completed: 二次验证后跳过
# - blocked_corrupt: SystemExit(2)，拒绝继续
# - 任一 smoke 失败 -> fail-closed，不进入主循环

# smoke gate 阈值（8 题）：
# 8 题的 parser rate 只能是 0%, 12.5%, ..., 87.5%, 100%
# "≥ 95%" 实际等于 100%（8/8）
# 冻结为：每臂 8/8 parsed，五臂聚合 40/40
SMOKE_PARSER_RATE_THRESHOLD = 1.0   # 100%
```

#### 4.13.3 五 smoke ledger 记账

```python
# 五 smoke 的调用计入全局 ledger
# smoke 成功后，该 slice 标记为 completed，主循环跳过
# smoke 失败的调用消耗 budget，但不产生有效终态记录
# smoke 状态不写入 runner manifest（runner 独占 slice manifest）
# 状态每次从 ledger + manifest + details + events 重新推导
# 若需持久化 smoke 状态，只能写入 orchestrator 自有的 budget_ledger.json
#   的 smoke_states[slice_id] 字段，并纳入 fingerprint
```

#### 4.13.4 主循环跳过 smoke ID 集合

```python
# 原 6B1: 主循环从 schedule[1:] 开始
# 6B1-D: 主循环遍历所有 slice，跳过 SMOKE_SLICE_IDS 集合
for sl in schedule["slices"]:
    if sl["slice_id"] in SMOKE_SLICE_IDS:
        # 从 ledger + manifest + details + events 重新推导状态
        # 签名一致：determine_smoke_state(sl) 只接收 smoke_sl
        state = determine_smoke_state(sl)
        if state == "completed":
            # 完整验证（复用 6B1 完整路径，传入 ledger 用于原子 reconciliation）
            ok, reason = verify_smoke_completed(sl, args, ledger)
            if not ok:
                raise SystemExit(2)  # 验证失败
            continue  # 跳过已完成的 smoke
        else:
            raise SystemExit(2)  # smoke 未完成
    # ... 执行主循环 slice
```

#### 4.13.5 `--from-slice` 审计

```python
# 原 6B1: --from-slice 假设只跳过一个 smoke (index 0)
# 6B1-D: --from-slice N 跳过前 N 个 slice，但必须审计：
# 1. 被跳过的 slice 中，smoke slice 必须是 completed
# 2. 被跳过的非 smoke slice 必须通过 manifest 验证
# 3. SMOKE_SLICE_IDS 集合必须全部在跳过范围内（即 N >= 5）
```

#### 4.13.6 五 smoke 归档

```python
# 原 6B1: archive 只复制一个 smoke/ 目录
# 6B1-D: archive 复制五个 smoke 子目录：
# archive/smoke_b1a_prime/
# archive/smoke_b1b/
# archive/smoke_b1c/
# archive/smoke_b2b/
# archive/smoke_b2c/
# 每个子目录含 details.jsonl, details.events.jsonl, details.manifest.json
# audit_index.json 中记录五个 smoke 的哈希
# 必须测试：--archive 时所有五个 smoke 目录都被复制并检查哈希
```

#### 4.13.7 五 smoke fail-closed 行为

```python
# 任一 smoke 失败时：
# 1. 不进入主循环
# 2. 不生成 archive
# 3. 输出 BLOCKED_SMOKE_<arm> 状态
# 4. exit code 2
# 5. 已完成的 smoke slice 保留产物，供调试
```

### 4.14 标签 manifest 集成

```python
# 运行前生成 labels.jsonl（独立文件）
# 固定路径：docs/phase6/6b1d/labels.jsonl
# 每行 JSON schema（三维分别标注和裁决）：
# {
#   "case_id": "case_id_str",
#   "annotator_1_id": "annotator_id_str",
#   "annotator_1": {
#     "question_complexity": 1|2|3,
#     "ziwei_info_richness": 1|2|3,
#     "bazi_info_richness": 1|2|3
#   },
#   "annotator_2_id": "annotator_id_str",
#   "annotator_2": { same structure },
#   "adjudicator": "annotator_id_str",
#   "final": {
#     "question_complexity": 1|2|3,
#     "ziwei_info_richness": 1|2|3,
#     "bazi_info_richness": 1|2|3
#   }
# }
# 80 个 case ID 完整覆盖、唯一性检查
# 值域只能为 1/2/3
# 缺失或额外 case 时 preflight 阻断
# 计算 SHA-256 并写入 run manifest
# 加入 resume fingerprint（标签变更则拒绝 resume）
# 加入归档审计索引
```

---

## 5. 测试计划（必须全部实现）

### 5.1 chart_context 单元测试（tests/test_chart_context.py）

```python
# Test 1: b2b (ziwei_mini) 内容检查
# - 包含固定段标【紫微斗数·精简】
# - 包含【命宫】、【身宫】、【主星】
# - 不包含真实裸名宫位（直接复用 _DENYLIST_MARKERS，不另维护带"宫"后缀名单）：
#   父母、福德、田宅、官禄、仆役、迁移、疾厄、财帛、子女、夫妻、兄弟
# - 不包含八字关键词："四柱"、"日主"等
# - 命身同宫时输出"命身同宫"
# - 缺失身宫时输出"【身宫】未标注"

# Test 2: b2c (sequential) 结构检查
# - 包含八字完整部分
# - 包含紫微完整部分
# - 包含"--- 八字分析结束 ---"分隔线
# - 包含顺序推理指令
# - 顺序：八字 -> 分隔 -> 紫微 -> 指令

# Test 3: 字节等价性验证（关键！）
# - Golden fixture 来源（全部冻结，禁止重新渲染或从 details 提取）：
#   * 归档目录：docs/phase6/6b1/6b1-2026-07-17-deepseek-deepseek-chat-78481de6
#   * 归档指纹：78481de6（与 6B1 code fingerprint 一致）
#   * 9 个哈希来源：直接复制 audit_index.json 的 context_fingerprints 字段
#     - context_fingerprints.case_ids（3 个 case ID）
#     - context_fingerprints.arms（3 个 arm：b1a_prime, b1b, b1c）
#     - context_fingerprints.fingerprints（9 个 SHA-256，3 case × 3 arm）
#   * 禁止从 details.jsonl/merged_details.jsonl 提取（这些文件不含 prompt 字段）
#   * 禁止用当前 renderer 重新生成（避免同源自证）
# - golden fixture 路径：tests/fixtures/6b1d_golden_prompts.json（只读）
# - fixture 元数据文件：tests/fixtures/6b1d_golden_prompts.meta.json
#   * 记录归档目录、归档指纹、audit_index.json 的 SHA-256、生成时间
# - 新实现与 golden fixture 中的 9 个指纹比较
# - 避免同源自证

# Test 4: invalid ziwei_arm fail-closed
# - 传入未知值必须 raise ValueError（库函数层）
# - runner 捕获后转换为 SystemExit(2)（CLI层）
# - 分别验证库函数和 CLI 的契约
```

### 5.2 orchestrator 集成测试（tests/test_phase6_6b1d.py）

```python
# Test 1: CLI choices fail-closed
# - 无效的 --ziwei-arm 必须 SystemExit(2)
# - 无效的 --arm 必须 SystemExit(2)

# Test 2: _REASONED_ARM_MAP 字典完整性
# - b2b -> ziwei_mini
# - b2c -> sequential
# - 未知 arm 在字典查询前被拦截

# Test 3: 5-arm visibility required/forbidden
# - 每个 arm 都必须通过 visibility gate
# - forbidden 字段存在时必须 SystemExit(2)

# Test 4: b1a'/b1b/b1c prompt 字节等价于 6B1
# - 逐字节比较

# Test 5: 5×5 Latin 调度正确性
# - 每个 arm × year × repeat 组合出现 5 个 slice（覆盖 G0-G4）
# - 5 个 slice 合计 40 个唯一 case ID，无重无漏
# - slice size 正确：全部为 8
# - total slices = 150
# - 前 5 个 slice ID 正好是五个 smoke 臂：b1a', b1b, b1c, b2b, b2c

# Test 6: 逐 slice hard cap 正确性（动态 effective_cap）
# - effective_cap 首次分配写入 budget_ledger.json（不是 slice manifest）
# - resume 时从 budget_ledger.json 读取相同值，不重新分配
# - runner manifest 的 hard_cap 必须与 ledger allocated_cap 一致
# - global_remaining < SLICE_BASE_CALLS 时 SystemExit(2)
# - 所有 slice local cap 默认 = 10
# - effective_cap 永远不会超过 SLICE_MAX_CAP
# - resume 预算公式检查：total_attempted + (effective_cap - already_attempted) <= 1320
# - 接近 1320 上限时恢复 slice 的测试（剩余预算不足时 BLOCKED_BUDGET_EXHAUSTED）

# Test 7: 预算和完整性集合正确
# - Total expected = 1200
# - 每臂 expected = 240

# Test 8: Fingerprint 漂移和 resume 拒绝
# - 仅修改 phase6_6b1d_orchestrator.py 也会改变 code fingerprint
# - 修改任意 scope 内文件都会改变 fingerprint
# - Code fingerprint 必须与 manifest 中的期望值匹配
# - fingerprint 不匹配时 resume 被拒绝

# Test 9: Archive/Run ID 不污染 6B1
# - 所有文件写入 docs/phase6/6b1d/
# - 不得访问 docs/phase6/6b1/

# Test 10: 五臂 smoke 完整状态机
# - fresh: 执行 smoke run
# - resume: 崩溃后 partial records 正确恢复
# - completed: 验证 manifest 后跳过
# - corrupt: SystemExit(2)
# - 任一 smoke 失败 -> 不进入主循环
# - 主循环跳过 SMOKE_SLICE_IDS 集合
# - --from-slice 审计 smoke slice 必须是 completed
# - archive 含五个 smoke 子目录及哈希
# - smoke parser rate 阈值 = 100%（8/8）

# Test 11: 标签 manifest 集成
# - labels.jsonl 生成并计算 SHA-256
# - 80 个 case ID 完整覆盖、唯一性检查
# - 值域只能为 1/2/3
# - 缺失或额外 case 时 preflight 阻断
# - 哈希写入 run manifest
# - 标签变更后 resume 被拒绝

# Test 12: Fake runner 驱动的 non-dry-run main()
# - 完整 150 slices fake run
# - 五 smoke 全部通过
# - 所有 manifest 和 events 正确生成
# - Integrity check passes（1200 records）
# - 报告生成成功（描述性表述，不含禁词）

# Test 13: effective_cap 持久化与 resume
# - 首次运行分配 effective_cap 并写入 budget_ledger.json（不是 slice manifest）
# - 中断后 resume 读取相同值，不重新分配
# - 不同 slice 有不同的 effective_cap

# Test 14: hard_cap 一致性验证
# - runner manifest 的 hard_cap 必须与 budget_ledger 的 allocated_cap 一致
# - 不一致时 resume 被拒绝（SystemExit(2)）
# - runner manifest 存在但 ledger 缺失时 fail-closed
# - ledger 有分配但 runner 无产物时允许首跑

# Test 15: 标签分布检查
# - 运行前输出三个维度（question_complexity, ziwei_info_richness, bazi_info_richness）的分布
# - 任意一层样本数 < 5 -> 自动跳过该层的分层分析
# - ziwei_info_richness 在真实 80 题上的预期分布：0星≈20、1星≈45、2星≈15

# Test 16: ledger reconciliation（原子回算）
# - completed artifacts + ledger 调用数偏低 -> reconciliation 向上修正
# - completed artifacts + ledger 调用数偏高 -> reconciliation 向下修正
# - reconciliation 后 total_calls_attempted == 各 slice calls_attempted_by_slice 之和
# - reconciliation 后 slice 被标为 completed
# - reconciliation 后原子保存 ledger

# Test 17: resume 预算公式执行
# - resume 路径必须执行 total_attempted + (effective_cap - already_attempted) <= 1320
# - already_attempted < 0 时 SystemExit(2)
# - already_attempted > effective_cap 时 SystemExit(2)
# - already_attempted is None 时 SystemExit(2)（禁止静默默认）
# - projected_total > 1320 时 BLOCKED_BUDGET_EXHAUSTED
# - 接近 1320 上限时恢复 slice 的测试（剩余预算不足时阻断）

# Test 18: compute_effective_cap 调用点集成验证
# - main/fake-runner 路径必须调用 compute_effective_cap
# - resume 前必须先完成 events -> ledger reconciliation
# - already_attempted 必须来自 ledger._data["calls_attempted_by_slice"]
# - 首次运行时显式传 0（不能省略参数）
# - 缺少第 3 个参数时 TypeError（强制显式传入，函数共 3 个参数）

# Test 19: reconcile_partial_events（partial resume 回算）
# - 崩溃后部分调用（calls < scheduled_calls）正确回算 ledger
# - 损坏 JSONL 时 SystemExit(2)
# - calls > allocated_cap 时 SystemExit(2)
# - 回算后不标记 slice 为 completed
# - 回算后 total == 各 slice 之和
# - 回算后原子保存 ledger
# - 回算后 already_attempted 可正确读取

# Test 19b: manifest-only resume 严格判定（events 不存在）
# - manifest-only + details 不存在 + ledger=0 -> 合法，返回 0
# - manifest + partial details + events 缺失 -> BLOCKED_EVIDENCE_LOST
# - manifest-only + ledger 非零 -> BLOCKED_EVIDENCE_LOST
# - events 文件曾存在后被删除（details 存在或 ledger 非零）-> BLOCKED_EVIDENCE_LOST
# - 合法 manifest-only 时 already_attempted = 0，继续 resume
# - 不被 events file missing 阻断（仅限真正 manifest-only）

# Test 20: BudgetLedger schema 扩展校验
# - allocated_cap_by_slice 必须是 dict
# - key 必须属于 schedule 中的 slice_id
# - cap 必须是 8..10 的整数
# - completed/resume slice 的 allocation 与 manifest hard_cap 一致
```

---

**状态**: `APPROVED`（已通过终审，进入实施阶段）

**审核通过前**：不写任何实际代码，保持 draft 状态。
**审核通过后**：按上述骨架位置逐项实现，每一步都要有测试。立即加入 Git，防止再次丢失。

按 TDD 顺序开始实现：
1. BudgetLedger schema 扩展（allocated_cap_by_slice）+ 加载校验单测
2. resume/Smoke 单测（determine_smoke_state、verify_smoke_completed、reconcile_partial_events、compute_effective_cap、verify_cap_consistency_on_resume）
3. chart_context.py 新增 b2b/b2c renderer + golden fixture 字节等价测试
4. run_benchmark.py CLI choices + _REASONED_ARM_MAP 字典扩展
5. profiles.py visibility matrix（裸名宫位 + _DENYLIST_MARKERS）
6. phase6_6b1d_orchestrator.py（5×5 Latin、150 slices、五 smoke 状态机、事务式 reconciliation）
7. fake runner 驱动的 non-dry-run main() 集成测试
8. 正式实验执行
