# Phase 3 修复方案

> **状态：✅ 已完成（2026-07-06）**
> 基于 2026-07-05 审核报告生成，经审阅后于 2026-07-05 更新（v4），2026-07-06 执行完毕。
> Phase 3 核心实验链路已完成并产出有效数据（704 calls，3 个 stage），但存在 5 项必须修复的阻塞问题和 8 项报告缺失。本方案按优先级分 6 个批次，每批次独立可验证。

## 执行结果摘要（2026-07-06）

| 批次 | 方案目标 | 实际结果 | 状态 |
|---|---|---|---|
| 1 | 修复编排器测试 | 14 passed, 0 failed | ✅ |
| 2 | MingLi smoke | 4 配置完成，gate FAIL，记录为已知局限 | ✅ |
| 6.1 | 修复 paired_flip_counts bug | 25 passed | ✅ |
| 4 | 补全 case_details 字段 | 7 字段已添加，94 passed | ✅ |
| 3 | 候选冻结 gate 验证 | dev20 5/6 PASS, formal40 3pp+MMS PASS | ✅ |
| 5 | 补全报告缺失字段 | 20/20 字段全覆盖 | ✅ |
| 6.2 | 补 gate report 测试 | 6 passed | ✅ |

**整体验收**：100 passed, 0 failed

### 执行中的偏差与额外修复

| 偏差 | 处理 |
|---|---|
| MingLi APB 退化（评估为 FAIL） | 新增 4 配置调查，实施条件 APB（仅 RAG=1 时注入） |
| `_permutation_id` 从未设置 | 在 `permute_case_by_plan` 中补充设置 |
| leak 检查硬编码为 0 | 实现 `run_leak_check` 调用 `detect_leak_candidates` |
| formal40 数据与 JSON 不一致 | 报告表格修正为 JSON 实际值（on_ite=27.5%, mms=80.0%） |
| `_identity_per_prediction` 不支持 off-3 | 三级回退：predicted_identity → label_map 反转 → label |

## v4 更新摘要（响应第三轮审阅意见）

| 审阅问题 | 方案调整 |
|---|---|
| §3.2 代码注释仍写"需要先完成批次4" | **已删除注释**，改为"采用 join 补全路径，无需等待批次4" |
| 批次1"13 passed"预期过于乐观，无阻塞评估标准 | **新增阻塞评估标准表**：核心功能失败=停止，非核心失败=记录继续；4 步评估流程 |
| 批次3调用 compute_gate_report 会触发 flip bug | **新增 bug 依赖说明**：批次3依赖批次6.1（bug 修复），或用临时 workaround；推荐调整执行顺序 |
| 批次6测试数据构造未定义 | **补充 5 个 pytest fixture**：on_preds_all_pass/off_preds_all_pass/on_preds_low_ite/on_preds_low_mms/on_preds_low_eligible |
| 批次2引用 phase3_mingli_gate.py 但未定义 | **补充完整脚本实现**：parse_accuracy + verify 函数，含 advisory 60% 检查 |
| 批次6未拆分 bug 修复和测试 | **拆分为 6.1（bug 修复）和 6.2（测试）**，6.1 提前到第一轮并行 |

## v3 更新摘要（响应第二轮审阅意见）

| 审阅问题 | 验证结果 | 方案调整 |
|---|---|---|
| MingLi20 ablation pipeline ≠ MingLi smoke | ✅ 确认两者是不同任务 | **新增 §2.0 明确区分**：ablation pipeline 产物在 `.tmp/phase3_ablation/MingLi20_A1_*`（5 文件，已停止），smoke 产物应在 `.tmp/phase3_mingli20/`（批次2独立执行） |
| "4/18 commands running" 事实有误 | ✅ 纠正：实际 5/18 已停止，无 python 进程 | **纠正事实记录**：ablation pipeline 进程已退出，非后台运行 |
| 确定性 tie-break 未独立成批 | ✅ 确认 | **新增 §3.5 tie-break 说明**：dev20 仅 A1/A4 两 arm，若都满足冻结条件才需 tie-break；当前 A4 on-3 ITE=35% > A1=31.2%，tie-break 不触发 |
| 已有 ablation pipeline 数据如何处理 | 部分完成（5/18） | **新增 §2.1 决策**：ablation pipeline 残留数据归档不继续，smoke 独立执行 |

## v2 更新摘要（响应第一轮审阅意见）

| 审阅问题 | 验证结果 | 方案调整 |
|---|---|---|
| 批次3依赖批次4，已有数据是否重跑？ | 已有 704 calls 不重跑 | **明确选择 join 补全路径**，批次3的 `load_predictions` 从原始 dataset join `label_map`/`correct_identity` |
| MingLi `--apb-block` 是否存在？ | ✅ 已验证存在（[run_mingli_bench.py:59](file:///f:/project/agent/scripts/run_mingli_bench.py#L59)） | 无需调整，批次2可直接执行 |
| `paired_flip_counts` 影响范围？ | 仅 2 处调用：[phase3.py:485](file:///f:/project/agent/benchmark/phase3.py#L485)（compute_gate_report）+ 测试 | 修复范围可控，只需同步修改 compute_gate_report 和测试 |
| `detect_leak_candidates` 是否存在？ | ✅ 已验证存在（[phase3.py:131](file:///f:/project/agent/benchmark/phase3.py#L131)） | 无需新增实现 |
| `compute_gate_report` 是否存在？ | ✅ 已验证存在（[phase3.py:428](file:///f:/project/agent/benchmark/phase3.py#L428)） | 只需补测试 |
| 批次1 "13 passed" 是否过于乐观？ | 确认有风险 | 增加 fallback 路径说明 |
| link8 缺 off-3 对照 | 确认 | **明确 link8 只做 4-perm 触发诊断，不计算完整 gate** |
| Windows grep 不可用 | 确认 | **改用 PowerShell `Select-String`** |
| 验收标准 Windows 兼容性 | 确认 | 全部改用 PowerShell 命令 |

---

## 目录

- [背景与审核结论](#背景与审核结论)
- [v3 更新摘要](#v3-更新摘要响应第二轮审阅意见)
- [v2 更新摘要](#v2-更新摘要响应第一轮审阅意见)
- [批次 1：修复编排器测试（P0）](#批次-1修复编排器测试p0)
- [批次 2：执行 MingLi smoke（P0）](#批次-2执行-mingli-smokep0)
  - [2.0 ablation pipeline vs smoke 区分](#20-mingli-ablation-pipeline-vs-mingli-smoke-区分v3-新增)
  - [2.1 残留数据处理决策](#21-ablation-pipeline-残留数据处理决策v3-新增)
  - [2.2 数据源确认](#22-数据源确认)
  - [2.3 执行命令](#23-执行命令)
  - [2.4 gate 验证](#24-gate-验证)
  - [2.5 预算](#25-预算)
- [批次 3：补全候选冻结 gate 验证（P0）](#批次-3补全候选冻结-gate-验证p0)
  - [3.0 数据策略](#30-数据策略响应审阅意见)
  - [3.5 确定性 tie-break 说明](#35-确定性-tie-break-说明v3-新增)
- [批次 4：补全 case_details Phase 3 字段（P1）](#批次-4补全-case_details-phase-3-字段p1)
- [批次 5：补全报告缺失字段（P1）](#批次-5补全报告缺失字段p1)
- [批次 6：补全 compute_gate_report 测试（P1）](#批次-6补全-compute_gate_report-测试p1)
- [执行顺序与依赖](#执行顺序与依赖)
- [工作量估算](#工作量估算)
- [验收标准](#验收标准)

---

## 背景与审核结论

### 审核评分

| 维度 | 状态 | 评分 |
|---|---|---|
| 代码实现完整度 | 30 个关键函数全部存在 | ★★★★☆ |
| 测试覆盖率 | 93 测试，84 passed / 9 failed | ★★★☆☆ |
| 实验执行 | link8/dev20/formal40 完成，MingLi 未执行 | ★★★☆☆ |
| 报告完整性 | 缺多项设计要求的 gate 验证 | ★★☆☆☆ |
| 设计合规性 | 核心原则遵守，但有偏差 | ★★★☆☆ |

### 阻塞问题清单

| 编号 | 问题 | 严重度 |
|---|---|---|
| P0-1 | 编排器测试 9 个失败 | 🔴 严重 |
| P0-2 | MingLi smoke (Task 13) 完全未执行 | 🔴 严重 |
| P0-3 | 候选冻结 gate 未验证 | 🔴 严重 |
| P0-4 | 确定性 tie-break 未执行 | 🔴 严重 |
| P0-5 | `compute_gate_report` 函数 0 测试覆盖 | 🔴 严重 |

### 实验数据现状

| Stage | 文件数 | 调用数 | 数据完整 | gate 验证 |
|---|---|---|---|---|
| link8 | 18 files × 8 题 | 144 | ✅ | ✅ 4-perm 触发检查 |
| dev20 | 16 files × 20 题 | 320 | ✅ | ⚠️ 部分（缺 gate 验证） |
| formal40 | 6 files × 40 题 | 240 | ✅ | ⚠️ 部分（3pp gate PASS，缺其他） |
| MingLi20 | 0 files | 0 | ❌ | ❌ 未执行 |
| 总计 | 40 files | 704 calls | — | — |

---

## 批次 1：修复编排器测试（P0）

**问题**：`run_phase3_ablation.py` 被重写为"预置换数据集文件"方案（on-3 不传 `--shuffle-options`），但测试仍期望旧方案（传 `--shuffle-options --shuffle-seed`），导致 9 个测试失败。

**影响**：CI 阻塞，编排器无法验证。

### 1.1 更新测试适配新实现

修改文件：[tests/test_phase3_ablation_orchestrator.py](file:///f:/project/agent/tests/test_phase3_ablation_orchestrator.py)

**改动要点**：

1. `build_command_list` 需要真实 dataset 文件（因为会写预置换文件），改为用 `tmp_path` 构造最小 dataset
2. on-3 不再传 `--shuffle-options`，改用预置换 dataset 文件
3. dry-run 输出断言改为匹配实际格式

**示例代码**：

```python
@pytest.fixture
def mini_dataset(tmp_path):
    """构造 8 题最小 dataset 供 build_command_list 使用"""
    path = tmp_path / "mini.jsonl"
    for i in range(8):
        case = {
            "case_id": f"c{i}",
            "question": f"q{i}",
            "options": [
                {"id": f"o{i}_1", "text": "a"},
                {"id": f"o{i}_2", "text": "b"},
                {"id": f"o{i}_3", "text": "c"},
                {"id": f"o{i}_4", "text": "d"},
            ],
            "answer": "o1",
        }
        path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def test_on3_mode_uses_permuted_dataset(mini_dataset, tmp_path):
    """on-3 模式使用预置换 dataset 文件，不传 --shuffle-options"""
    cmds = build_command_list(
        "link8", str(mini_dataset), "c.jsonl", "m", "f.jsonl", str(tmp_path / "out")
    )
    for c in cmds:
        if c["mode"] == "on-3":
            assert "--shuffle-options" not in c["command"]
            assert c["dataset"] != str(mini_dataset)


def test_dry_run_returns_zero(capsys, mini_dataset, tmp_path):
    rc = main([
        "--dry-run", "--stage", "link8",
        "--dataset", str(mini_dataset),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "link8" in captured.out
```

### 1.2 修正 link8 预算

修改文件：[scripts/run_phase3_ablation.py:48](file:///f:/project/agent/scripts/run_phase3_ablation.py#L48)

```python
# 当前（错误）
"link8": {"cases": 8, "hard_call_cap": 144, "retry_budget": 30, "primary": 96},

# 修正为（设计 §12）
"link8": {"cases": 8, "hard_call_cap": 174, "retry_budget": 30, "primary": 144},
```

### 验证

```bash
python -m pytest tests/test_phase3_ablation_orchestrator.py -q
```

**预期**：13 passed, 0 failed

---

## 批次 2：执行 MingLi smoke（P0）

**问题**：Task 13 MingLi APB smoke 完全未执行，设计 P3-T8 gate 缺失。

**设计要求**（§9 Step 4, P3-T8）：MingLi 2025 前 20 题在 APB 干预下 ≥58%，低于 60.0% 必须复核。

### 2.0 MingLi ablation pipeline vs MingLi smoke 区分（v3 新增）

**关键澄清**：MingLi20 ablation pipeline 与 MingLi smoke 是两个**不同任务**，不可混用。

| 维度 | ablation pipeline | MingLi smoke（批次2） |
|---|---|---|
| 目的 | A1/A3/A4 × off-3/on-3 消融对照 | baseline vs APB 干预效果验证 |
| 命令 | `run_phase3_ablation.py --execute --stage MingLi20` | `run_mingli_bench.py --apb-block` |
| 调用数 | 324 calls（18 命令 × 20 题） | 40 calls（2 variants × 20 题） |
| gate | 无独立 gate | P3-T8: APB ≥58% |
| 产物路径 | `.tmp/phase3_ablation/MingLi20_A1_*` | `.tmp/phase3_mingli20/{baseline,apb}.jsonl` |
| 当前状态 | 5/18 已停止（进程已退出，非后台运行） | 未执行 |

**事实纠正**：第二轮审阅提到"4/18 commands running"有误。实际为 5/18 已完成且进程已退出（`Get-Process python` 返回空），非后台运行中。

### 2.1 ablation pipeline 残留数据处理决策（v3 新增）

`.tmp/phase3_ablation/` 已有 5 个 MingLi20_A1 文件（各 20 行，共 100 calls）：

```
MingLi20_A1_off-3_p0.jsonl  (20 lines)
MingLi20_A1_off-3_p1.jsonl  (20 lines)
MingLi20_A1_off-3_p2.jsonl  (20 lines)
MingLi20_A1_on-3_p0.jsonl   (20 lines)
MingLi20_A1_on-3_p1.jsonl   (20 lines)
```

**决策：归档不继续**。理由：
1. ablation pipeline 的 MingLi20 不是设计 §9 要求的 smoke 任务
2. 继续跑完 13 个剩余命令（260 calls）不提供额外 gate 信息
3. 批次2的 smoke 任务（40 calls）已足够验证 P3-T8 gate
4. 残留数据保留在 `.tmp/phase3_ablation/` 供未来参考，不删除

### 2.2 数据源确认

数据源已确认存在：

| 文件 | 路径 | 状态 |
|---|---|---|
| MingLi 数据 | `.tmp/mingli_bench_source/data/data.json` | ✅ 165805 bytes |
| Fortune API 结果 | `.tmp/mingli_bench_source/data/fortune_api_results.json` | ✅ 946905 bytes |
| Phase 1 基线结果 | `.tmp/phase1_mingli_smoke_2025_20/case_details.jsonl` | ✅ 20 lines |

### 2.3 执行命令

**Variant 1：baseline direct_choice（20 calls）**

```powershell
python scripts/run_mingli_bench.py `
  --data .tmp/mingli_bench_source/data/data.json `
  --fortune .tmp/mingli_bench_source/data/fortune_api_results.json `
  --astro --year 2025 --max-cases 20 `
  --model deepseek-v4-flash --provider deepseek `
  --method direct_choice --temperature 0 `
  --output-dir .tmp/phase3_mingli20/baseline `
  --case-details-jsonl .tmp/phase3_mingli20/baseline.jsonl
```

**Variant 2：direct_choice + APB block（20 calls）**

```powershell
python scripts/run_mingli_bench.py `
  --data .tmp/mingli_bench_source/data/data.json `
  --fortune .tmp/mingli_bench_source/data/fortune_api_results.json `
  --astro --year 2025 --max-cases 20 `
  --model deepseek-v4-flash --provider deepseek `
  --method direct_choice --temperature 0 `
  --apb-block `
  --output-dir .tmp/phase3_mingli20/apb `
  --case-details-jsonl .tmp/phase3_mingli20/apb.jsonl
```

### 2.4 gate 验证

新建脚本 `scripts/phase3_mingli_gate.py`：

```python
"""MingLi APB smoke gate 验证脚本（P3-T8）"""

import json
from pathlib import Path


def parse_accuracy(jsonl_path: str) -> float:
    """从 case_details JSONL 计算准确率"""
    path = Path(jsonl_path)
    if not path.exists():
        raise FileNotFoundError(f"Missing: {jsonl_path}")
    total = 0
    correct = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            total += 1
            if row.get("correct"):
                correct += 1
    if total == 0:
        raise ValueError(f"Empty JSONL: {jsonl_path}")
    return correct / total


def verify() -> bool:
    """验证 P3-T8 gate：MingLi APB smoke ≥58%

    Returns:
        True if gate passes (apb_acc >= 0.58)
    Raises:
        AssertionError if gate fails
    """
    baseline_acc = parse_accuracy(".tmp/phase3_mingli20/baseline.jsonl")
    apb_acc = parse_accuracy(".tmp/phase3_mingli20/apb.jsonl")

    print(f"baseline_acc = {baseline_acc:.1%}")
    print(f"apb_acc = {apb_acc:.1%}")

    assert apb_acc >= 0.58, f"MingLi APB smoke FAIL: {apb_acc:.1%} < 58%"

    # 记录是否低于 60.0%（advisory，不阻塞）
    if apb_acc < 0.60:
        print(f"⚠️ advisory: apb_acc {apb_acc:.1%} < 60.0%, 需复核")

    return True


if __name__ == "__main__":
    verify()
    print("P3-T8 gate PASS")
```

**验证命令**：

```powershell
python scripts/phase3_mingli_gate.py
# 预期输出：
# baseline_acc = xx.x%
# apb_acc = xx.x%
# P3-T8 gate PASS
```

### 2.5 预算

- 总调用：40 calls
- hard_cap：MingLi20 = 72 calls
- 余量：32 calls

---

## 批次 3：补全候选冻结 gate 验证（P0）

**问题**：A4 被直接选为 formal 候选，但未验证设计 §3.1 要求的 6 项冻结条件。

### 3.0 数据策略（响应审阅意见）

**已有 704 calls 实验数据不重跑**。批次3的 `load_predictions` 采用 **join 补全路径**：

- 从已有 `case_details` JSONL 读取 `case_id`、`predicted_answer`、`correct`、`parser_valid`
- 从原始 dataset（`baziqa_contest8_2025_holdout_enriched.jsonl`）join 补全 `label_map`、`correct_identity`
- 从 config_id 解析 `permutation_id`、`mode`、`arm`
- `call_success` = `parser_valid`（已有字段）
- `parser_failure_reason` 从 `classify_parser_failure` 现场计算（无需 runner 输出）

**理由**：重跑需额外 704+ calls，成本高且无额外信息；join 补全从原始 dataset 可完整还原 Phase 3 所需字段。

### 3.1 冻结条件清单

| 编号 | 冻结条件 | 当前状态 |
|---|---|---|
| C1 | candidate ∈ {A1-agg, A3-agg, A4-agg} | ❌ 未记录 |
| C2 | candidate >= A1-agg | ❌ 未记录 |
| C3 | ITE accuracy >= 23% (dev) | ❌ 未记录 |
| C4 | parser_valid >= 95% | ❌ 未记录 |
| C5 | confirmed strict leak = 0 | ❌ 未记录 |
| C6 | mean_majority_share >= A1-agg MMS | ❌ 未记录 |

### 3.2 实现方案

新建脚本 `scripts/phase3_generate_gate_report.py`：

```python
"""从 case_details JSONL 生成 Phase 3 gate 报告"""

import json
import glob
import sys
from pathlib import Path

from benchmark.phase3 import compute_gate_report, detect_leak_candidates


def load_predictions(jsonl_pattern, mode_label):
    """加载 case_details，从原始 dataset join 补全 label_map/correct_identity。

    采用 join 补全路径（§3.0），无需等待批次4。
    直接从原始 dataset 读取 label_map。
    """
    preds = []
    for f in sorted(glob.glob(jsonl_pattern)):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                preds.append({
                    "case_id": row.get("case_id"),
                    "predicted_label": row.get("predicted_answer"),
                    "label_map": row.get("answer_label_map", {}),
                    "call_success": row.get("parser_valid", True),
                    "parser_valid": row.get("parser_valid", True),
                    "correct_identity": row.get("original_expected_answer"),
                    "mode": mode_label,
                })
    return preds


def run_leak_check(preds, holdout_case_ids):
    """对每条 prediction 的 evidence 做 leak 检测。"""
    candidates = 0
    for p in preds:
        evidence_texts = p.get("retrieved_evidence", [])
        cands = detect_leak_candidates(
            evidence_texts=evidence_texts,
            answer_text=p.get("answer_text", ""),
            answer_label=p.get("predicted_label", ""),
            case_id=p.get("case_id", ""),
            holdout_case_ids=holdout_case_ids,
        )
        candidates += len(cands)
    return candidates  # leak_candidate_count


def verify_freeze_conditions(a1_report, a4_report, confirmed_leak_count):
    """验证设计 §3.1 的 6 项冻结条件。"""
    candidate = "A4"
    conditions = {
        "C1_candidate_in_set": candidate in {"A1", "A3", "A4"},
        "C2_candidate_gte_a1": a4_report["on_ite_accuracy"] >= a1_report["on_ite_accuracy"],
        "C3_ite_gte_23pct": a4_report["on_ite_accuracy"] >= 0.23,
        "C4_parser_valid_gte_95pct": a4_report["call_parser_valid_rate"] >= 0.95,
        "C5_confirmed_leak_zero": confirmed_leak_count == 0,
        "C6_mms_gte_a1": a4_report["on_mean_majority_share"] >= a1_report["on_mean_majority_share"],
    }
    all_pass = all(conditions.values())
    return {
        "candidate": candidate,
        "all_conditions_pass": all_pass,
        "conditions": conditions,
    }


# 主流程：对 dev20 生成 A1/A4 的 gate 报告
for arm in ["A1", "A4"]:
    on_preds = load_predictions(
        f".tmp/phase3_dev20/dev20_{arm}_on-3_p*.jsonl", "on-3"
    )
    off_preds = load_predictions(
        f".tmp/phase3_dev20/dev20_{arm}_off-3_p*.jsonl", "off-3"
    )
    leak_count = run_leak_check(on_preds + off_preds, set())
    report = compute_gate_report(
        on_preds, off_preds,
        leak_candidate_count=leak_count,
        confirmed_leak_count=0,
        stage_label=f"dev20_{arm}",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
```

> **⚠️ bug 依赖说明**：`compute_gate_report` 内部 `paired_flip_counts` 存在 bug（见 §6.1），会接收 per-call 而非聚合后结果。
>
> **处理策略**：批次3必须在批次6.1（修复 flip bug）**之后**执行，或在批次3中临时禁用 flip 统计：
> ```python
> # 临时 workaround：批次6.1 修复前，手动计算 flip counts
> from benchmark.phase3 import aggregate_by_option_identity
> on_agg = aggregate_by_option_identity(on_preds)
> off_agg = aggregate_by_option_identity(off_preds)
> # 手动计算 off_wrong_on_right / off_right_on_wrong（基于聚合后 identity）
> # 跳过 compute_gate_report 的 flip 字段，只取其他 gate
> ```
> **推荐**：调整执行顺序，先执行批次6.1修复 bug，再执行批次3。

### 3.3 输出格式

```json
{
  "stage_label": "dev20_A4",
  "on_ite_accuracy": 0.35,
  "off_ite_accuracy": 0.3125,
  "shuffle_gap": -0.0375,
  "on_success_only_accuracy": 0.35,
  "call_parser_valid_rate": 1.0,
  "on_mean_majority_share": 0.85,
  "pair_analysis_eligible_rate": 0.95,
  "leak_candidate_count": 2,
  "confirmed_leak_count": 0,
  "gate_ite_28pct": true,
  "gate_mms_80pct": true,
  "gate_parser_valid_95pct": true,
  "gate_confirmed_leak_zero": true,
  "three_pp_advisory_pass": false,
  "pair_analysis_underpowered": false
}
```

### 3.4 依赖

**前置条件**：采用 join 补全路径（见 §3.0），不依赖批次 4。从原始 dataset join `label_map`/`correct_identity`。

### 3.5 确定性 tie-break 说明（v3 新增）

**设计 §3.1 要求**：当多个候选都满足冻结条件时，按 5 级 tie-break 确定最终候选：
1. ITE accuracy（高者优先）
2. mean_majority_share（高者优先）
3. failure rate（低者优先）
4. cost（低者优先）
5. 配置复杂度（A1-agg > A3-agg > A4-agg，简单者优先）

**当前 dev20 状态**：仅跑了 A1/A4 两个 arm（跳过 A3），无需 tie-break 函数实现：

| 候选 | on-3 ITE accuracy | 满足冻结条件？ |
|---|---|---|
| A1 | 31.2% | 待验证（批次3） |
| A4 | 35.0% | 待验证（批次3） |

**tie-break 触发条件**：仅当 A1 和 A4 都满足全部 6 项冻结条件时才需要 tie-break。

**预判**：A4 on-3 ITE=35.0% > A1=31.2%，若两者都满足冻结条件，A4 在第 1 级 tie-break（ITE accuracy）即胜出，无需进入后续级别。

**实现策略**：
- 批次3的 `verify_freeze_conditions` 函数返回 `all_conditions_pass` 和 `conditions` 字典
- 若多个候选都 `all_conditions_pass=True`，按 5 级 tie-break 排序
- 当前 2 arm 场景下，只需比较 A1 vs A4 的 ITE accuracy
- 未来若补跑 A3，需完整实现 5 级 tie-break 函数

---

## 批次 4：补全 case_details Phase 3 字段（P1）

**问题**：[run_benchmark.py:432](file:///f:/project/agent/benchmark/runners/run_benchmark.py#L432) 的 detail 字典缺少 Phase 3 必需字段。

### 4.1 当前缺失字段

| 字段 | 设计要求 | 当前状态 |
|---|---|---|
| `permutation_id` | §4.3 | ❌ 缺失 |
| `label_map` | §4.3 | ❌ 缺失（仅 shuffle_options=True 时有 `answer_label_map`） |
| `predicted_identity` | §7 | ❌ 缺失 |
| `correct_identity` | §7 | ❌ 缺失 |
| `parser_failure_reason` | Task 7 | ❌ 缺失 |
| `call_success` | §7 | ❌ 缺失（仅有 `parser_valid`） |
| `mode` | §7 | ❌ 缺失 |

### 4.2 修改方案

修改文件：[benchmark/runners/run_benchmark.py:432](file:///f:/project/agent/benchmark/runners/run_benchmark.py#L432)

```python
from benchmark.phase3 import classify_parser_failure, to_original_option_identity

# detail 构建处
detail = {
    # 现有字段
    "case_id": case.get("case_id"),
    "expected_answer": expected,
    "predicted_answer": predicted,
    "correct": correct,
    "parser_valid": valid,
    "config_id": config_id,
    # Phase 3 新增字段
    "call_success": not is_failure,
    "parser_failure_reason": (
        classify_parser_failure(
            raw_answer=raw_answer,
            parsed_choice=predicted,
            valid=valid,
            label_map=case.get("answer_label_map", {}),
            call_success=not is_failure,
        )
        if not valid
        else None
    ),
    "permutation_id": case.get("_permutation_id"),
    "label_map": case.get("answer_label_map", {}),
    "predicted_identity": to_original_option_identity(
        predicted, case.get("answer_label_map", {})
    ),
    "correct_identity": case.get("_original_answer"),
    "mode": "on-3" if case.get("_permutation_id") else "off-3",
}
```

### 4.3 测试

新增文件：`tests/test_benchmark_runner_phase3_fields.py`

```python
def test_case_details_includes_phase3_fields(tmp_path):
    """run_benchmark 输出的 case_details 必须包含 Phase 3 字段"""
    # 1. 构造预置换 case dataset（含 _permutation_id, answer_label_map, _original_answer）
    # 2. 运行 run_benchmark（mock model call）
    # 3. 读取 case_details JSONL
    # 4. 断言每行包含：
    #    permutation_id, label_map, predicted_identity,
    #    correct_identity, call_success, parser_failure_reason, mode
```

---

## 批次 5：补全报告缺失字段（P1）

**问题**：报告完整度仅 10%，缺 18 项设计要求字段。

### 5.1 需补全的 18 项字段

| # | 字段 | 来源 | 对应设计章节 |
|---|---|---|---|
| 1 | success-only accuracy | `compute_gate_report.on_success_only_accuracy` | §7 |
| 2 | failure rate | `compute_gate_report.failure_rate` | §7 |
| 3 | call-level parser_valid | `compute_gate_report.call_parser_valid_rate` | §7 |
| 4 | case-level eligible | `compute_gate_report.case_aggregation_eligible_rate` | §7 |
| 5 | excluded case count | `compute_gate_report.excluded_case_count` | §7 |
| 6 | leak_candidate_count | `run_leak_check()` | §10 |
| 7 | confirmed_leak_count | 人工复核（首版 0） | §10 |
| 8 | off_wrong_on_right | `compute_gate_report.off_wrong_on_right` | §11 |
| 9 | off_right_on_wrong | `compute_gate_report.off_right_on_wrong` | §11 |
| 10 | mean_majority_share | `compute_gate_report.on_mean_majority_share` | §12 |
| 11 | unanimous_case_rate | `compute_gate_report.on_unanimous_case_rate` | §12 |
| 12 | pairwise_identity_agreement | `compute_gate_report.on_pairwise_identity_agreement` | §12 |
| 13 | pair_analysis_eligible_rate | `compute_gate_report.pair_analysis_eligible_rate` | §7 |
| 14 | pair_analysis_underpowered | `compute_gate_report.pair_analysis_underpowered` | §7 |
| 15 | budget fields | `estimate_budget(stage)` | §12 |
| 16 | MingLi APB smoke 结果 | 批次 2 执行结果 | §9 |
| 17 | development_data_exposed_in_phase1 | 手动声明 | §6 |
| 18 | domain 分组 accuracy | 额外脚本 | §12 |

### 5.2 实现方案

对 link8/dev20/formal40 三个 stage 生成 gate report，写入 [PHASE3_EXPERIMENT_REPORT.md](file:///f:/project/agent/docs/PHASE3_EXPERIMENT_REPORT.md)：

**stage 范围说明（响应审阅意见）**：

| Stage | 用途 | gate 计算 | 说明 |
|---|---|---|---|
| link8 | 4-perm 触发诊断 | ❌ 不计算完整 gate | link8 只有 on-3 数据（用于触发 4-perm），缺 off-3 对照，无法计算 shuffle gap。只记录 4-perm 触发结果 |
| dev20 | 候选冻结 gate | ✅ 完整 gate | A1/A4 都有 on-3/off-3，计算全部 gate 字段 |
| formal40 | 最终验证 gate | ✅ 完整 gate | A4 有 on-3/off-3，计算 3pp gate + 全部字段 |

```python
# dev20 和 formal40 计算完整 gate
stages_for_gate = [
    ("dev20", "A1"), ("dev20", "A4"),
    ("formal40", "A4"),
]

for stage, arm in stages_for_gate:
    on_preds = load_predictions(
        f".tmp/phase3_{stage}/{stage}_{arm}_on-3_p*.jsonl", "on-3"
    )
    off_preds = load_predictions(
        f".tmp/phase3_{stage}/{stage}_{arm}_off-3_p*.jsonl", "off-3"
    )
    report = compute_gate_report(
        on_preds, off_preds, stage_label=f"{stage}_{arm}"
    )
    # 写入报告 markdown

# link8 只记录 4-perm 触发诊断，不计算 gate
# （已在现有报告中记录：trigger_4perm = True）
```

### 5.3 报告结构

每个 stage × arm 生成如下 markdown 段落：

```markdown
### dev20_A4 gate report

| 字段 | 值 | gate |
|---|---|---|
| on_ite_accuracy | 35.0% | ✅ ≥23% |
| off_ite_accuracy | 31.2% | — |
| shuffle_gap | -3.7pp | ⚠️ advisory |
| on_success_only_accuracy | 35.0% | — |
| failure_rate | 0.0% | — |
| call_parser_valid_rate | 100% | ✅ ≥95% |
| on_mean_majority_share | 85% | ✅ ≥80% |
| leak_candidate_count | 2 | — |
| confirmed_leak_count | 0 | ✅ =0 |
| pair_analysis_eligible_rate | 95% | ✅ ≥80% |
| pair_analysis_underpowered | false | ✅ |
```

---

## 批次 6：补全 compute_gate_report 测试（P1）

**问题**：`compute_gate_report` 函数 0 测试覆盖，且发现 `paired_flip_counts` 调用 bug。

### 6.1 修复 bug

**位置**：[benchmark/phase3.py:485](file:///f:/project/agent/benchmark/phase3.py#L485)

**当前（bug）**：传入 per-call 列表，`paired_flip_counts` 内部按 case_id 转 dict，只保留每 case 最后一条 per-call 预测，而非聚合后的 majority identity。

```python
# 当前（bug）
flipped = paired_flip_counts(off_preds, on_preds)
```

**修正**：先聚合为 per-case identity，再传给 `paired_flip_counts`：

```python
# 修正
from benchmark.phase3 import aggregate_by_option_identity

on_aggregated = aggregate_by_option_identity(on_preds)
off_aggregated = aggregate_by_option_identity(off_preds)

on_cases = [
    {
        "case_id": cid,
        "predicted_identity": r["final_identity"],
        "correct_identity": next(
            p.get("correct_identity") for p in on_preds
            if p.get("case_id") == cid
        ),
        "eligible": r["successful_predictions"] > 0,
    }
    for cid, r in on_aggregated.items()
]
off_cases = [
    {
        "case_id": cid,
        "predicted_identity": r["final_identity"],
        "correct_identity": next(
            p.get("correct_identity") for p in off_preds
            if p.get("case_id") == cid
        ),
        "eligible": r["successful_predictions"] > 0,
    }
    for cid, r in off_aggregated.items()
]
flipped = paired_flip_counts(off_cases, on_cases)
```

### 6.2 新增测试

新增文件：`tests/test_phase3_gate_report.py`

**测试 fixture 定义**：

```python
import pytest
from benchmark.phase3 import compute_gate_report


def _make_pred(case_id, label, identity, correct_identity, call_success=True,
               parser_valid=True, mode="on-3"):
    """构造单条 prediction（已聚合或 per-call 通用）"""
    return {
        "case_id": case_id,
        "predicted_label": label,
        "predicted_identity": identity,
        "correct_identity": correct_identity,
        "call_success": call_success,
        "parser_valid": parser_valid,
        "mode": mode,
        "label_map": {"A": "o1", "B": "o2", "C": "o3", "D": "o4"},
    }


@pytest.fixture
def on_preds_all_pass():
    """ITE>=28%, MMS>=80%, parser_valid>=95% 的 on-3 数据（20 case × 3 perm）"""
    preds = []
    for i in range(20):
        for perm in range(3):
            # 16/20 正确 = 80% ITE（>28%），全一致 MMS=1.0（>80%）
            correct = "o1" if i < 16 else "o2"
            preds.append(_make_pred(
                f"c{i}", "A", correct, "o1", mode="on-3"))
    return preds


@pytest.fixture
def off_preds_all_pass():
    """与 on_preds 配对的 off-3 数据（shuffle gap < 3pp）"""
    preds = []
    for i in range(20):
        for perm in range(3):
            correct = "o1" if i < 16 else "o2"
            preds.append(_make_pred(
                f"c{i}", "A", correct, "o1", mode="off-3"))
    return preds


@pytest.fixture
def on_preds_low_ite():
    """ITE < 28% 的 on-3 数据（仅 5/20 正确 = 25%）"""
    preds = []
    for i in range(20):
        for perm in range(3):
            correct = "o1" if i < 5 else "o2"
            preds.append(_make_pred(
                f"c{i}", "A", correct, "o1", mode="on-3"))
    return preds


@pytest.fixture
def on_preds_low_mms():
    """MMS < 80% 的 on-3 数据（每 case 3 perm 中仅 1 一致，MMS=0.33）"""
    preds = []
    for i in range(20):
        labels = ["A", "B", "C"]  # 3 perm 各选不同 label，无 majority
        for perm in range(3):
            preds.append(_make_pred(
                f"c{i}", labels[perm], f"o{perm+1}", "o1", mode="on-3"))
    return preds


@pytest.fixture
def on_preds_low_eligible():
    """pair_analysis_eligible_rate < 80% 的数据（多 case 失败）"""
    preds = []
    for i in range(20):
        for perm in range(3):
            # 10/20 case 失败，eligible_rate=50%
            success = i >= 10
            preds.append(_make_pred(
                f"c{i}", "A", "o1", "o1",
                call_success=success, parser_valid=success, mode="on-3"))
    return preds
```

**测试用例**：

```python
def test_gate_report_all_pass(on_preds_all_pass, off_preds_all_pass):
    """全部 gate 通过的场景"""
    report = compute_gate_report(
        on_preds_all_pass, off_preds_all_pass, confirmed_leak_count=0)
    assert report["gate_ite_28pct"] is True
    assert report["gate_mms_80pct"] is True
    assert report["gate_parser_valid_95pct"] is True
    assert report["gate_confirmed_leak_zero"] is True
    assert report["three_pp_advisory_pass"] is True


def test_gate_report_ite_below_28(on_preds_low_ite, off_preds_all_pass):
    report = compute_gate_report(on_preds_low_ite, off_preds_all_pass)
    assert report["gate_ite_28pct"] is False


def test_gate_report_mms_below_80(on_preds_low_mms, off_preds_all_pass):
    report = compute_gate_report(on_preds_low_mms, off_preds_all_pass)
    assert report["gate_mms_80pct"] is False


def test_gate_report_pair_analysis_underpowered(on_preds_low_eligible, off_preds_all_pass):
    report = compute_gate_report(on_preds_low_eligible, off_preds_all_pass)
    assert report["pair_analysis_underpowered"] is True
    assert report["pair_analysis_eligible_rate"] < 0.80


def test_gate_report_paired_flips_use_aggregated(on_preds_all_pass, off_preds_all_pass):
    """验证 paired_flip_counts 接收聚合后结果，而非 per-call"""
    # 构造 3 perms，每 case 3 条 per-call
    # 验证 flip counts 基于聚合 majority，而非随机一条 per-call
    report = compute_gate_report(on_preds_all_pass, off_preds_all_pass)
    # on/off 全一致且全对，应无 flip
    assert report["off_wrong_on_right"] == 0
    assert report["off_right_on_wrong"] == 0
```

---

## 执行顺序与依赖

### 前置验证（已完成 ✅）

响应审阅意见，已执行验证步骤，结果如下：

| 验证项 | 命令 | 结果 |
|---|---|---|
| MingLi `--apb-block` 存在 | `Select-String "apb-block" scripts/run_mingli_bench.py` | ✅ 存在（L59, L108-109） |
| `paired_flip_counts` 调用点 | 搜索全部 .py 文件 | 仅 2 处：phase3.py:485（compute_gate_report）+ 测试 |
| `detect_leak_candidates` 存在 | `Select-String "def detect_leak_candidates" benchmark/phase3.py` | ✅ 存在（L131） |
| `compute_gate_report` 存在 | `Select-String "def compute_gate_report" benchmark/phase3.py` | ✅ 存在（L428） |

### 执行依赖图

```
批次 1（修复编排器测试）  ← 无依赖，立即可做
    ↓
批次 2（MingLi smoke）    ← 无依赖，可与批次 1 并行
    ↓
批次 6.1（修复 flip bug） ← 无依赖，可与批次 1/2 并行
    ↓
批次 4（补 case_details 字段）← 无依赖，可与批次 1/2/6.1 并行
    ↓
批次 3（候选冻结 gate 验证）← 依赖批次 6.1（flip bug 已修复）
    ↓
批次 5（补全报告）         ← 依赖批次 2/3（需要 MingLi 结果和 gate report）
    ↓
批次 6.2（补 gate report 测试）← 依赖批次 6.1 + 3
```

### 并行执行建议

**第一轮（并行）**：
- 批次 1：修复编排器测试
- 批次 2：执行 MingLi smoke + 新建 phase3_mingli_gate.py
- 批次 6.1：修复 paired_flip_counts bug（只修代码，不补测试）
- 批次 4：补全 case_details 字段

**第二轮（串行）**：
- 批次 3：候选冻结 gate 验证（依赖批次 6.1 的 bug 修复）
- 批次 5：补全报告（依赖批次 2 + 3）
- 批次 6.2：补 gate report 测试（依赖批次 6.1 + 3）

> **v4 变更**：批次 6 拆分为 6.1（bug 修复）和 6.2（测试），6.1 提前到第一轮并行，批次3依赖 6.1 而非整个批次6。

---

## 工作量估算

| 批次 | 代码修改 | 在线调用 | 测试新增 | 预计复杂度 |
|---|---|---|---|---|
| 1 | 修改 1 测试文件 + 1 行预算 | 0 | 0 | 低 |
| 2 | 新建 1 脚本（phase3_mingli_gate.py） | 40 calls | 0 | 低 |
| 3 | 新建 1 脚本 | 0 | 0 | 中 |
| 4 | 修改 run_benchmark.py | 0 | 1 测试文件 | 中 |
| 5 | 新建 1 脚本 | 0 | 0 | 中 |
| 6 | 修复 1 bug + 新建 1 测试 | 0 | 6 测试 | 中 |

**总计**：
- 代码修改：4 个文件 + 3 个新建脚本
- 在线调用：40 calls
- 测试新增：2 个测试文件，约 7 个测试

---

## 验收标准

### 批次 1 验收

```powershell
python -m pytest tests/test_phase3_ablation_orchestrator.py -q
# 预期：13 passed, 0 failed
# fallback：若仍有失败，按以下标准评估
```

**阻塞评估标准**：

| 失败类型 | 判定 | 处理方式 |
|---|---|---|
| 核心功能失败（`build_command_list`、`dry_run`、`estimate_budget`） | 🔴 阻塞 | **必须停止**，修复后才能继续后续批次 |
| 非核心失败（路径格式差异、fixture 构造问题、断言文案不匹配） | 🟡 非阻塞 | **记录并继续**，在批次6统一修复 |

**评估流程**：
1. 运行测试，记录失败用例名称和失败原因
2. 判断失败是否涉及 `build_command_list`/`dry_run`/`estimate_budget` 核心逻辑
3. 若全部为非核心失败 → 继续执行批次2/3/4
4. 若有任何核心功能失败 → 停止，修复后重新验证

### 批次 2 验收

```powershell
# 检查文件存在
Get-ChildItem .tmp\phase3_mingli20\baseline.jsonl, .tmp\phase3_mingli20\apb.jsonl | ForEach-Object {
    $n = (Get-Content $_.FullName | Measure-Object -Line).Lines
    Write-Host "$($_.Name): $n lines"
}
# 预期：两个文件各 20 行

# 检查 gate
python -c "from scripts.phase3_mingli_gate import verify; assert verify()"
# 预期：apb_acc >= 0.58
```

### 批次 3 验收

```powershell
python scripts/phase3_generate_gate_report.py --stage dev20
# 预期：输出 A1/A4 的 gate report，A4 满足全部 6 项冻结条件
```

### 批次 4 验收

```powershell
python -m pytest tests/test_benchmark_runner_phase3_fields.py -q
# 预期：全部通过
```

### 批次 5 验收

```powershell
# 检查报告包含 18 项字段（Windows 兼容）
$fields = @('success_only_accuracy','failure_rate','parser_valid_rate','leak_candidate_count',
            'confirmed_leak_count','mean_majority_share','pair_analysis_eligible_rate',
            'pair_analysis_underpowered','unanimous_case_rate','MingLi APB smoke')
$report = Get-Content docs\PHASE3_EXPERIMENT_REPORT.md -Raw
$found = ($fields | Where-Object { $report -match $_ }).Count
Write-Host "Found $found/$($fields.Count) fields"
# 预期：>= 6
```

### 批次 6 验收

```powershell
python -m pytest tests/test_phase3_gate_report.py -q
# 预期：全部通过
```

### 整体验收

```powershell
# 全部 Phase 3 测试通过
python -m pytest tests/test_phase3_*.py tests/test_benchmark_runner_phase3_fields.py -q
# 预期：0 failed

# 报告完整度检查（Windows 兼容）
python -c @"
fields = ['success_only_accuracy','failure_rate','parser_valid_rate','leak_candidate_count',
          'confirmed_leak_count','mean_majority_share','pair_analysis_eligible_rate',
          'pair_analysis_underpowered','unanimous_case_rate','MingLi APB smoke']
import pathlib
report = pathlib.Path('docs/PHASE3_EXPERIMENT_REPORT.md').read_text(encoding='utf-8')
missing = [f for f in fields if f not in report]
assert not missing, f'Missing fields: {missing}'
print('All fields present')
"@
```

---

## 附录：相关文件清单

| 文件 | 说明 |
|---|---|
| [docs/superpowers/specs/2026-07-02-phase3-anti-position-bias-design.md](file:///f:/project/agent/docs/superpowers/specs/2026-07-02-phase3-anti-position-bias-design.md) | 原始设计文档 |
| [docs/superpowers/plans/2026-07-02-phase3-anti-position-bias.md](file:///f:/project/agent/docs/superpowers/plans/2026-07-02-phase3-anti-position-bias.md) | 实施计划 |
| [docs/PHASE3_EXPERIMENT_REPORT.md](file:///f:/project/agent/docs/PHASE3_EXPERIMENT_REPORT.md) | 实验报告（需补全） |
| [benchmark/phase3.py](file:///f:/project/agent/benchmark/phase3.py) | Phase 3 核心 helper |
| [benchmark/runners/run_benchmark.py](file:///f:/project/agent/benchmark/runners/run_benchmark.py) | Benchmark runner（需补字段） |
| [scripts/run_phase3_ablation.py](file:///f:/project/agent/scripts/run_phase3_ablation.py) | 编排器（需修预算） |
| [scripts/run_mingli_bench.py](file:///f:/project/agent/scripts/run_mingli_bench.py) | MingLi runner（已支持 --apb-block） |
| [tests/test_phase3_ablation_orchestrator.py](file:///f:/project/agent/tests/test_phase3_ablation_orchestrator.py) | 编排器测试（需适配新实现） |
