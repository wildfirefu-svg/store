# Phase 6 6A1 严格 ≥3/5 投票同源配对基线（含 temp-0 锚定）实施计划 v1

> 状态：**DRAFT（待评审）**
> 设计依据：`docs/superpowers/specs/2026-07-17-phase6-dual-system-accuracy-design.md` v6 §5（6A1 协议）、§8（预算双列）、§10（顺序与阻塞规则）、§12（风险如实声明）。
> 前置事实（已核验）：6A0 全部完成并收口（`8645f87`）；6A0 dev gate = **ROLLBACK**（Δ=−5.0pp），按设计 §10 回退规则，**6A1 全部臂上下文锁定 `legacy_v0`**；2021/2024 enriched 产物在位（Task 3，40/40）；评测设施（attempt key/resume manifest/重试账本/BudgetLedger/截断守卫）已在 6A0 落地并有真实运行验证。
> 纪律：每 Task TDD（先失败测试）；`git add` 只列精确路径；每任务提交前 4 组回归（`.tmp/g{1..4}.txt`）全绿；执行偏离逐条写入 commit 信息。

---

## 0. 设计 v6 §5 协议 → 本计划落点映射

| §5.2 协议条 | 落点 |
| --- | --- |
| 1. 每题同温度 T 采样 5 次，T 冻结 0.4 | runner `emit_samples` 模式（Task 2）；编排器采样臂切片（Task 3） |
| 2. 多样性试测（stage=`diversity_probe`，10 题，<60% → T=1.0，样本作废） | 编排器 probe 阶段 + `diversity_rate()` 纯函数（Task 3） |
| 3. 锚定臂（stage=`anchor`，single@T=0，同时间窗） | `--attempt-stage anchor`（Task 2）+ AB/BA 交错调度（Task 3） |
| 4. `strict_majority()` ≥3 票当选、unresolved 计错、invalid 占 attempt、分母恒 5、禁止破平局 | `benchmark/runners/self_consistency.py::strict_majority`（Task 1，**不复用 `majority_vote`**） |
| 5. 同源配对：single@T=第 1 次采样；vote5=同 5 次聚合；single@0 独立同期；manifest 记调用顺序与原始响应路径 | 编排器聚合纯函数（Task 3）；detail 行 `raw_response_path`（已有）+ slice manifest（已有） |
| 6. repeats 聚合：vote5 仅 repeat 内聚合；报每 repeat、三轮均值、逐题明细；禁止 15 次再投票 | `evaluate_vote()` 按 (case_id, repeat_idx) 分组聚合（Task 3，测试锁定不跨 repeat） |
| 7. 首类指标：准确率、unresolved 率、配对四格表 ×2、成本比（trimmed mean 附列） | `write_report()`（Task 3）；trimmed mean 复用 Task 8 `accuracy_stats` |

§5.3 gate → Task 3 `verdict()` 纯函数 + Task 4/5 真实执行；§8 预算 → 下文预算表 + `build_schedule` cap 和断言。

## 1. 计划期决策记录（冻结；设计未规定处的补白，均不发明、不放宽）

1. **上下文基线**：全部臂 `--chart-schema-version legacy_v0`（6A0 ROLLBACK 结论；设计 §10「增强臂失败回退上一稳定基线」）。
2. **臂/stage 命名**（attempt key 无温度字段——probe 两轮温度不同必须靠 arm 区分，否则键碰撞）：
   - 采样臂：`arm=vote5_samples`，`attempt_stage=main`，`sample_idx∈0..4`，`repeat_idx∈0..2`；
   - 锚定臂：`arm=anchor_single0`，`attempt_stage=anchor`，`sample_idx=0`；
   - 试测：`arm=probe_r1`（T=0.4）/ `arm=probe_r2`（T=1.0），`attempt_stage=diversity_probe`，`repeat_idx=-1`（与 smoke 同例，不进主指标）。
3. **single@T = `sample_idx=0`**：emit 循环按 sample_idx 升序串行调用，调用顺序即样本顺序，「同组 5 次的第 1 次」= sample_idx 0 行。
4. **T 冻结链**（设计 §5.2.2 只规定一次切换；第三次温度属发明，禁止）：
   - probe_r1（T=0.4）多样性 ≥ 60% → 冻结 T=0.4，probe_r2 不运行（0 调用）；
   - < 60% → 运行 probe_r2（T=1.0）；≥ 60% → 冻结 T=1.0；
   - probe_r2 仍 < 60% → **冻结 T=1.0 继续**，并在报告与 stage manifest 记录「低多样性（T=1.0 仍 <60%）」为预注册限制（设计 §12.1 已预见低多样性抬高 unresolved 率，unresolved 率首类指标兜底）。
5. **锚定臂禁止复用 6A0 `ctx_legacy` 旧 run**：设计 §5.2.3 要求同时间窗；跨时段比较只能 advisory（§12.5）。6A0 旧数据一字不读。
6. **聚合全部离线**：runner 只负责逐样本调用/记账/明细（`emit_samples`），不做任何投票；`strict_majority` 与 Δ 计算在编排器纯函数，测试全覆盖。
7. **`RESUME_MANIFEST_FIELDS` 不新增 `attempt_stage`**：全部 stage 已由 arm 区分（probe_r1/probe_r2/vote5_samples/anchor_single0），无碰撞面；新增字段会使既有 manifest 校验语义变动（旧 run 缺字段 fail-closed），无收益。
8. **probe 选题**：`split_ab_ba(case_ids, seed=20260717)` 的 `group_a[:10]`（复用 6A0 同一种子与函数，确定性、预注册）。
9. **审计索引工具扩展**：`scripts/build_phase6_audit_index.py` 增加 `--arms a,b`（默认原值不变），供 6A1 归档复算两臂（Task 3 内小改 + 测试）。
10. **emit 行字段集**：与 6A0 detail 行同构 + `sample_idx`/`n_samples`/`aggregate="emit_samples"`；每样本独立 `correct`（样本级诊断），vote5/single@T 的 case 级 correct 由编排器派生，不回写 runner。

## 2. 预算（设计 §8 双列；reserve = scheduled 10% 向上取整到 10）

### dev 2024：scheduled 820 / hard_cap 910

| 切片 | arm/stage | 调用数 scheduled | hard_cap |
| --- | --- | ---: | ---: |
| probe_r1（10 题 × 5，T=0.4） | probe_r1/diversity_probe | 50 | 55 |
| probe_r2（条件运行，T=1.0） | probe_r2/diversity_probe | 50 | 55 |
| 采样臂 ×3 repeats × 2 组（20 题 × 5） | vote5_samples/main | 100 × 6 = 600 | 110 × 6 = 660 |
| 锚定臂 ×3 repeats × 2 组（20 题 × 1） | anchor_single0/anchor | 20 × 6 = 120 | caps 和 = 140 |
| **合计** | | **820** | **910** |

锚定 6 切片 cap 分配 `(24, 23, 23, 23, 23, 24)`（和 140）；probe_r2 不运行时实际硬顶 855 ≤ 910（储备不用即不支出）。

### 2021 复核（仅 dev gate 判 PROMOTE_CANDIDATE 时触发）：scheduled 720 / hard_cap 800

| 切片 | 调用数 scheduled | hard_cap |
| --- | ---: | ---: |
| 采样臂 100 × 6 | 600 | 110 × 6 = 660 |
| 锚定臂 20 × 6 | 120 | caps 和 = 140（同上分配） |
| **合计** | **720** | **800** |

无 probe（T 已由 dev 冻结，从 dev stage manifest 读取并记录来源）。

### 调度顺序（同时间窗 + AB/BA）

```text
probe_r1 → [probe_r2 条件]
每 repeat r∈{0,1,2}：sample(r, group_a) → anchor(r, group_a) → anchor(r, group_b) → sample(r, group_b)
```

锚定臂与同组采样臂背靠背（A 组采样先行、B 组锚定先行，镜像平衡顺序效应）。

---

## Task 1：`strict_majority()` 严格投票纯函数

**文件**：`benchmark/runners/self_consistency.py`（追加，不动 `majority_vote`/`sample_answers`）；`tests/test_strict_vote.py`（新增）。

- [ ] **Step 1：写失败测试 `tests/test_strict_vote.py`（完整代码）**

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.runners.self_consistency import strict_majority


class TestStrictMajority:
    """设计 §5.2.4：≥3 票当选；无 3 票 → None（unresolved 计错）；
    None/invalid 票留在分母（len(votes) 恒 5）；禁止任何形式破平局。"""

    def test_three_of_five_wins(self):
        assert strict_majority(["A", "A", "A", "B", "C"]) == "A"      # 3/1/1

    def test_two_two_one_unresolved(self):
        assert strict_majority(["A", "A", "B", "B", "C"]) is None     # 2/2/1 无破平局

    def test_two_one_one_one_unresolved(self):
        assert strict_majority(["A", "A", "B", "C", "D"]) is None     # 2/1/1/1 不取相对多数

    def test_none_votes_stay_in_denominator(self):
        # 3 有效 A + 2 invalid(None) → 仍 3/5 当选（分母恒 5）
        assert strict_majority(["A", "A", "A", None, None]) == "A"
        # 2 有效 A + 3 invalid → 2/5 < 3 → unresolved
        assert strict_majority(["A", "A", None, None, None]) is None

    def test_all_none_unresolved(self):
        assert strict_majority([None, None, None, None, None]) is None

    def test_exact_threshold_boundary(self):
        assert strict_majority(["B", "B", "B", "A", "A"]) == "B"      # 恰好 3 票当选

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            strict_majority([])

    def test_custom_threshold(self):
        # threshold 参数化（默认 3）；双达阈值并存只可能 n>5，此时返回 None 不任选
        assert strict_majority(["A", "A", "B", "B"], threshold=2) is None
        assert strict_majority(["A", "A", "A", "A"], threshold=4) == "A"
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_strict_vote.py -q` → `ImportError`。

- [ ] **Step 3：实现（追加到 `benchmark/runners/self_consistency.py` 末尾，完整代码）**

```python
def strict_majority(votes: Sequence[Optional[str]], threshold: int = 3) -> Optional[str]:
    """严格多数投票（Phase 6 6A1，设计 §5.2.4）。

    与 majority_vote 的区别：majority_vote 取相对多数并按首次出现破平局
    （2/1/1/1 会选出 2 票选项），不满足严格协议，故新增且**不复用**。

    - 任一选项票数 >= threshold 且唯一 → 该选项；
    - 否则（含双达阈值、无达阈值、全 None）→ None（unresolved，按错误计入分母）；
    - None 票（invalid/call_failed）不参与计票但留在 votes 长度内——分母恒为采样次数；
    - 禁止任何形式的破平局。
    """
    if len(votes) == 0:
        raise ValueError("strict_majority requires at least one vote")
    counts: dict = {}
    for vote in votes:
        if vote is None:
            continue
        counts[vote] = counts.get(vote, 0) + 1
    winners = [label for label, n in counts.items() if n >= threshold]
    return winners[0] if len(winners) == 1 else None
```

- [ ] **Step 4：运行确认全绿 + 回归**（本文件为纯函数追加，跑 Task 文件 + g2 组即可；g1/g3/g4 提交前全跑）。

- [ ] **Step 5：提交（精确路径）**

```powershell
git add benchmark/runners/self_consistency.py tests/test_strict_vote.py
git commit -m "feat(phase6): strict_majority 严格 ≥3/5 投票（6A1，不复用 majority_vote）"
```

---

## Task 2：runner `emit_samples` 逐样本模式 + `--attempt-stage`

**文件**：`benchmark/runners/run_benchmark.py`（6 处外科手术修改）；`tests/phase6_helpers.py`（测试设施增补）；`tests/test_phase6_emit_samples.py`（新增）。

**修改清单**（全部为追加/参数透传，不改既有 `majority` 路径行为）：

| # | 位置锚点 | 修改 |
| --- | --- | --- |
| 1 | argparse L1332 | `--aggregate` choices 增加 `"emit_samples"`；新增 `--attempt-stage`（default `"main"`） |
| 2 | L1408 ctx 初始化 | `attempt_stage="main"` → `attempt_stage=args.attempt_stage` |
| 3 | `Phase6Context.enrich_row` L263 | attempt key 取 `sample_idx=int(row.get("sample_idx") or 0)` |
| 4 | `_attempt_with_ledger`/`_call_with_optional_ledger`/`call_model_sync` | 各加 `sample_idx=0` 透传 |
| 5 | main() L1440-1443 resume 过滤 | emit 模式跳过 case 级预过滤，completed 集传入 `run_model_benchmark(completed_keys=...)` 按样本跳过 |
| 6 | `run_model_benchmark` per-case 循环 L957 前 | emit 分支：逐样本调用（temperature=sample_temperature）/记账/明细/失败行/续跑 |

- [ ] **Step 0：测试设施增补（`tests/phase6_helpers.py`，精确追加）**

```python
# RunnerEnv.__init__ 内追加（self.received 下一行）：
        self.received_kw: list = []       # 每次模型调用的 **kw（temperature 等），按调用顺序

# RunnerEnv._fake_call 替换为：
    def _fake_call(self, messages, **kw):
        self.received.append(messages)
        self.received_kw.append(kw)
        action, payload = self._script.pop(0)
        if action in ("fail", "crash"):
            raise payload
        return payload

# RunnerEnv 增补方法（model_succeeds_then_crash 之后）：
    def model_sequence(self, texts: list) -> None:
        """按序返回不同响应（emit_samples 逐样本差异化用）；耗尽后恒返回 "A"。"""
        self._script = [("ok", t) for t in texts] + [("ok", "A")] * 1000
```

- [ ] **Step 1：写失败测试 `tests/test_phase6_emit_samples.py`（完整代码）**

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tests.phase6_helpers import RunnerEnv

EMIT = ["--n-samples", "5", "--aggregate", "emit_samples",
        "--profile", "baziqa_xjz_direct", "--chart-schema-version", "legacy_v0",
        "--arm", "vote5_samples", "--sample-temperature", "0.4"]


def _keys(rows):
    return {tuple(r["attempt_key"]) for r in rows}


class TestEmitSamples:
    def test_emit_writes_per_sample_rows(self, tmp_path, monkeypatch):
        """每 case 写 5 行；attempt key 10 字段且 sample_idx 0..4 互异；行带 emit 标记。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        rows = env.read_detail()
        assert len(rows) == 10
        for r in rows:
            assert r["aggregate"] == "emit_samples" and r["n_samples"] == 5
            assert r["sample_idx"] in range(5)
            assert r["attempt_key"][3] == "main"               # 默认 attempt_stage
        per_case = {}
        for r in rows:
            per_case.setdefault(r["case_id"], set()).add(r["attempt_key"][8])
        assert per_case == {"c0": {0, 1, 2, 3, 4}, "c1": {0, 1, 2, 3, 4}}

    def test_emit_uses_sample_temperature(self, tmp_path, monkeypatch):
        """5 个样本全部以 sample_temperature=0.4 发起（非 --temperature 0.0）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        temps = [kw.get("temperature") for kw in env.received_kw]
        assert temps == [0.4] * 5

    def test_attempt_stage_param_flows_to_keys(self, tmp_path, monkeypatch):
        """--attempt-stage anchor → 全部行 attempt_key[3] == 'anchor'。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT + ["--attempt-stage", "anchor"]) == 0
        assert {r["attempt_key"][3] for r in env.read_detail()} == {"anchor"}

    def test_emit_resume_per_sample(self, tmp_path, monkeypatch):
        """7 次成功后崩溃（c0 5 + c1 头 2）；resume 只补 c1 余 3 样本；
        最终键集合 == 一次性运行（续跑幂等）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_succeeds_then_crash("A", successes=7)
        env.run_expect_crash(extra_argv=EMIT)
        env.model_returns("A")
        assert env.run(resume=True, extra_argv=EMIT) == 0
        rows = env.read_detail()
        assert len(rows) == 10 and len(_keys(rows)) == 10     # 无重复键

    def test_emit_case_level_prefilter_not_applied(self, tmp_path, monkeypatch):
        """全量后删掉 c0 的 sample 1-4 行（留 sample 0）→ resume 恰好补 4 次调用；
        若错误沿用 case 级预过滤（sample_idx=0 键已完成），c0 会被整体跳过（0 次）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        kept = [r for r in env.read_detail()
                if not (r["case_id"] == "c0" and r["sample_idx"] != 0)]
        env.detail.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                      for r in kept), encoding="utf-8")
        before = len(env.received)
        assert env.run(resume=True, extra_argv=EMIT) == 0
        assert len(env.received) - before == 4                 # 只补 c0 样本 1-4
        rows = env.read_detail()
        assert len(rows) == 10 and len(_keys(rows)) == 10

    def test_emit_sample_failure_row_and_budget(self, tmp_path, monkeypatch):
        """头 3 次网络失败 → c0/sample0 重试耗尽写 call_failed 行（占分母），
        后续样本继续；总调用 3 + 9 = 12；重试账本只记 sample0。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_fails(times=3)
        assert env.run(extra_argv=EMIT) == 0
        rows = env.read_detail()
        assert len(rows) == 10
        failed = [r for r in rows if r["terminal_state"] == "call_failed"]
        assert len(failed) == 1 and failed[0]["case_id"] == "c0" \
            and failed[0]["sample_idx"] == 0
        assert len(env.read_events("call_attempt")) == 12
        assert len(env.read_events("model_call_failed")) == 3
        assert {tuple(e["attempt_key"]) for e in env.read_events("model_call_failed")} \
            == {tuple(failed[0]["attempt_key"])}

    def test_emit_hard_cap_exit3_and_blocked_resume(self, tmp_path, monkeypatch):
        """hard_cap=3 → exit 3（BLOCKED_INCOMPLETE）；manifest 锁 cap，同 cap resume 仍 3
        且不新增调用（设计 §12.6：追加预算须新开 run/slice 目录，不得改 cap 续跑）。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=2)
        env.model_returns("A")
        assert env.run(scheduled_calls=10, hard_cap=3, extra_argv=EMIT) == 3
        assert len(env.read_events("call_attempt")) == 3
        assert env.run(resume=True, scheduled_calls=10, hard_cap=3, extra_argv=EMIT) == 3
        assert len(env.read_events("call_attempt")) == 3

    def test_emit_requires_profile_and_n_samples(self, tmp_path, monkeypatch):
        """emit_samples 无 profile → ValueError；n_samples=1 → ValueError。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        with pytest.raises(ValueError, match="emit_samples"):
            env.run(extra_argv=["--n-samples", "5", "--aggregate", "emit_samples"])
        with pytest.raises(ValueError, match="emit_samples"):
            env.run(extra_argv=["--n-samples", "1", "--aggregate", "emit_samples",
                                "--profile", "baziqa_xjz_direct",
                                "--chart-schema-version", "legacy_v0"])

    def test_emit_manifest_records_vote_fields(self, tmp_path, monkeypatch):
        """manifest 记录 aggregate/n_samples/sample_temperature/attempt 相关字段。"""
        env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
        env.model_returns("A")
        assert env.run(extra_argv=EMIT) == 0
        m = json.loads((tmp_path / "detail.manifest.json").read_text(encoding="utf-8"))
        assert m["aggregate"] == "emit_samples" and m["n_samples"] == 5
        assert m["sample_temperature"] == 0.4 and m["temperature"] == 0.0
```

- [ ] **Step 2：运行确认失败** `python -m pytest tests/test_phase6_emit_samples.py -q`（argparse 拒绝 `--aggregate emit_samples` / `ValueError` 缺失等）。

- [ ] **Step 3：实现（6 处，完整代码）**

**(1) argparse（L1332 附近）**

```python
    parser.add_argument('--aggregate', default='majority', choices=['majority', 'emit_samples'],
                        help='Aggregation strategy; emit_samples = Phase 6 6A1 逐样本明细（聚合离线）')
    parser.add_argument('--attempt-stage', default='main',
                        help='Phase 6 attempt key 的 attempt_stage（main/anchor/diversity_probe/...）')
```

**(2) ctx 初始化（L1408）**

```python
            arm=args.arm, attempt_stage=args.attempt_stage,
```

**(3) `enrich_row`（L263-266，sample_idx 从行取）**

```python
    def enrich_row(self, row):
        key = self.attempt_key_for({"case_id": row.get("case_id"),
                                    "_permutation_id": row.get("permutation_id")},
                                   sample_idx=int(row.get("sample_idx") or 0))
        row["attempt_key"] = list(key)
        ...  # 其余不变
```

**(4) sample_idx 透传（3 个函数，签名与一行调用）**

```python
def _attempt_with_ledger(case, call_once, sample_idx=0):
    ...
    key = ctx.attempt_key_for(case or {}, sample_idx=sample_idx)
    ...

def _call_with_optional_ledger(messages, provider, model, case, temperature, timeout,
                               rag_k, retrieval_mode, option_evidence_k,
                               suppress_rag, suppress_apb, sample_idx=0):
    call_once = lambda: _call_once_messages(...)
    if _PHASE6_CTX is None:
        ...
    return _attempt_with_ledger(case, call_once, sample_idx=sample_idx)

def call_model_sync(prompt, provider, model, case=None, temperature=None, timeout=300,
                    rag_k=2, retrieval_mode='legacy', option_evidence_k=2,
                    suppress_rag=False, suppress_apb=False, sample_idx=0):
    messages = [{"role": "user", "content": prompt}]
    return _call_with_optional_ledger(
        messages, provider, model, case, temperature, timeout,
        rag_k, retrieval_mode, option_evidence_k, suppress_rag, suppress_apb,
        sample_idx=sample_idx)
```

**(5) main() resume 过滤（L1440-1443 替换）**

```python
    completed_keys = None
    if args.profile and args.resume:
        completed = load_completed_keys(os.path.abspath(args.case_details_jsonl))
        ctx = _PHASE6_CTX
        if args.aggregate == "emit_samples":
            completed_keys = completed      # emit：case 级预过滤会误丢部分完成 case，改按样本跳过
        else:
            cases = [c for c in cases if ctx.attempt_key_for(c) not in completed]
```

`run_model_benchmark(...)` 调用处加 `completed_keys=completed_keys`；函数签名加 `completed_keys=None`。

**(6) emit 分支（`run_model_benchmark` 校验段 + per-case 循环内 prompt 构造之后、既有 `try:`（L957）之前插入）**

校验段（L675-678 之后追加）：

```python
    if aggregate == "emit_samples":
        if not isinstance(n_samples, int) or n_samples < 2:
            raise ValueError("emit_samples 需要 n_samples > 1（6A1 逐样本模式）")
        if _PHASE6_CTX is None:
            raise ValueError("emit_samples 仅支持 Phase 6 profile 模式（需 attempt 账本/续跑/manifest）")
```

循环分支（完整代码；`_HardCapExhausted` 非 RuntimeError 自然冒泡 → main 映射 exit 3）：

```python
        if aggregate == "emit_samples":
            # 6A1（设计 §5.2）：逐样本独立调用/记账/明细；聚合完全离线（编排器 strict_majority）。
            # 每样本：sample_idx 入 attempt key（独立终态/重试账本/续跑），
            # temperature=sample_temperature；失败样本写 call_failed 行（占分母）后继续。
            ctx = _PHASE6_CTX
            pending = [i for i in range(n_samples)
                       if not completed_keys
                       or ctx.attempt_key_for(case, sample_idx=i) not in completed_keys]
            if not pending:
                continue                    # resume：该 case 5 样本全部完成
            for sample_idx in pending:
                try:
                    raw = call_model_sync(
                        prompt, provider, model, case=case,
                        temperature=sample_temperature, sample_idx=sample_idx,
                        **_retrieval_call_kwargs(rag_k, retrieval_mode, option_evidence_k),
                    )
                    meta = extract_choice_with_meta(raw)
                    s_pred = meta["choice"]
                    ev = score_case_evidence(case, raw)
                    sf = score_safety(raw)
                    s_detail = {
                        "case_id": case_id, "domain": case.get("domain", "unknown"),
                        "question": case.get("question", "")[:50],
                        "expected_answer": expected, "predicted_answer": s_pred,
                        "raw_answer": raw, "correct": s_pred == expected,
                        "evidence_coverage": ev.get("coverage", 0.0),
                        "safety_score": sf.get("score", 0.0),
                        "parser_source": meta.get("source"), "parser_valid": meta.get("valid"),
                        "rag_k": rag_k, "retrieval_mode": retrieval_mode,
                        "rag_trace": [], "option_evidence": {}, "option_evidence_coverage": {},
                        "retrieved_answer_leak": False, "config_id": config_id,
                        "call_success": True,
                        "permutation_id": case.get("_permutation_id"),
                        "label_map": case.get("answer_label_map") or {},
                        "predicted_identity": s_pred,
                        "correct_identity": case.get("_original_answer"),
                        "mode": "off-3",
                        "parser_failure_reason": classify_parser_failure(
                            raw_answer=raw, parsed_choice=s_pred,
                            valid=meta.get("valid", False),
                            label_map=case.get("answer_label_map") or {}, call_success=True),
                        "sample_idx": sample_idx, "n_samples": n_samples,
                        "aggregate": aggregate,
                    }
                except RuntimeError as e:
                    if not str(e).startswith("model_call_failed"):
                        raise   # 崩溃类冒泡（Policy A）
                    s_detail = {
                        "case_id": case_id, "domain": case.get("domain", "unknown"),
                        "question": case.get("question", "")[:50],
                        "expected_answer": expected, "predicted_answer": None,
                        "raw_answer": "", "correct": False,
                        "error": str(e)[:120],
                        "evidence_coverage": 0.0, "safety_score": 0.0,
                        "parser_source": None, "parser_valid": False,
                        "rag_k": rag_k, "retrieval_mode": retrieval_mode,
                        "rag_trace": [], "option_evidence": {}, "option_evidence_coverage": {},
                        "retrieved_answer_leak": False, "config_id": config_id,
                        "call_success": False,
                        "permutation_id": case.get("_permutation_id"),
                        "label_map": case.get("answer_label_map") or {},
                        "predicted_identity": None,
                        "correct_identity": case.get("_original_answer"),
                        "mode": "off-3",
                        "parser_failure_reason": "model_call_failed",
                        "sample_idx": sample_idx, "n_samples": n_samples,
                        "aggregate": aggregate,
                    }
                case_details.append(s_detail)
                _append_jsonl(case_details_jsonl, s_detail)
                time.sleep(1)
            predictions[case_id] = s_detail.get("raw_answer") or ""
            continue
```

（`expected = extract_choice(case.get("answer"))` 与 `prompt` 在分支前已按既有代码求得；若现有位置在分支之后，则在分支首行补 `expected = extract_choice(case.get('answer'))`，实施时以当前文件锚点为准并在 commit 中登记。）

- [ ] **Step 4：运行确认全绿 + 4 组回归**。

- [ ] **Step 5：提交（精确路径）**

```powershell
git add benchmark/runners/run_benchmark.py tests/phase6_helpers.py tests/test_phase6_emit_samples.py
git commit -m "feat(phase6): runner emit_samples 逐样本模式 + --attempt-stage（6A1）"
```

---

## Task 3：6A1 编排器 `scripts/run_phase6_6a1_vote.py`

**职责**：离线 gate（legacy_v0 可见性 + 泄漏）、probe 多样性试测与 T 冻结、AB/BA 12 切片调度、阶段预算（复用 6A0 `BudgetLedger`）、严格聚合与 Δ1/Δ2、配对四格表、unresolved 率、成本代理、verdict、报告与 manifest。
**测试**：`tests/test_phase6_6a1_vote.py`。**辅助扩展**：`scripts/build_phase6_audit_index.py` 加 `--arms`（决策 9）。

- [ ] **Step 1：写失败测试 `tests/test_phase6_6a1_vote.py`（完整代码）**

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase6_6a1_ablation import (
    ANCHOR_CAPS,
    PROFILE_ID,
    VoteConfig,
    aggregate_metrics,
    build_main_schedule,
    diversity_rate,
    evaluate_t_switch,
    gate_verdict,
    run_vote,
    strict_rows_complete,
)
from tests.phase6_helpers import RunnerSpy

CASE_IDS = [f"c{i}" for i in range(40)]


def fake_vote_config(**overrides):
    base = dict(run_id="t", year=2024, root=Path(".tmp/x"), enriched_path=Path("e.jsonl"))
    base.update(overrides)
    return VoteConfig(**base)


def srow(case_id, repeat, sample_idx, letter, arm="vote5_samples", terminal="parsed"):
    """构造采样/锚定行（真实行形状：臂/repeat/sample 在 attempt_key 内）。"""
    stage = {"vote5_samples": "main", "anchor_single0": "anchor"}[arm]
    return {"case_id": case_id, "correct": letter == "B",
            "expected_answer": "B", "predicted_answer": letter,
            "terminal_state": terminal,
            "attempt_key": ["ds", PROFILE_ID, arm, stage, "deepseek", "deepseek-chat",
                            case_id, repeat, sample_idx, "p0"]}


class TestDiversity:
    def test_rate_and_switch_decision(self):
        # 6/10 题 ≥2 个不同选项 → 0.6 → 冻结 0.4，不跑 r2
        rows = []
        for i in range(10):
            letters = ["A", "A", "B", "A", "A"] if i < 6 else ["A"] * 5
            for j, L in enumerate(letters):
                rows.append(srow(f"c{i}", -1, j, L, arm="vote5_samples"))
        rate = diversity_rate(rows)
        assert rate == 0.6
        assert evaluate_t_switch(0.6, None) == ("freeze", 0.4)
        # 5/10 → 切换；r2 达标 → 冻结 1.0；r2 仍低 → 冻结 1.0 + 限制标记
        assert evaluate_t_switch(0.5, None) == ("probe_r2", 0.4)
        assert evaluate_t_switch(0.5, 0.7) == ("freeze", 1.0)
        assert evaluate_t_switch(0.5, 0.4) == ("freeze_low_diversity", 1.0)


class TestSchedule:
    def test_main_schedule_order_and_caps(self):
        cfg = fake_vote_config()
        sched = build_main_schedule(cfg, CASE_IDS)
        assert len(sched) == 12
        seq = [(s.arm, s.group) for s in sched[:4]]
        assert seq == [("vote5_samples", "group_a"), ("anchor_single0", "group_a"),
                       ("anchor_single0", "group_b"), ("vote5_samples", "group_b")]
        assert sum(s.hard_cap for s in sched) == 660 + sum(ANCHOR_CAPS)
        assert sum(s.scheduled_calls for s in sched) == 720
        sample = [s for s in sched if s.arm == "vote5_samples"][0]
        anchor = [s for s in sched if s.arm == "anchor_single0"][0]
        assert (sample.n_samples, sample.temperature) == (5, 0.4)
        assert (anchor.n_samples, anchor.temperature) == (1, 0.0)
        assert sample.stage == "main" and anchor.stage == "anchor"

    def test_schedule_requires_40(self):
        with pytest.raises(ValueError):
            build_main_schedule(fake_vote_config(), CASE_IDS[:39])


def _full_rows(per_repeat_correct_v5, per_repeat_correct_s0):
    """构造 40 题 × 3 repeats：采样臂每题 5 行（3B2A → vote5 恒 B）+ 锚定行。"""
    rows = []
    for rep in range(3):
        for i in range(40):
            cid = f"c{i}"
            v5_win = i < per_repeat_correct_v5[rep]
            letters = ["B", "B", "B", "A", "A"] if v5_win else ["A", "A", "A", "B", "B"]
            for j, L in enumerate(letters):
                rows.append(srow(cid, rep, j, L))
            rows.append(srow(cid, rep, 0, "B" if i < per_repeat_correct_s0[rep] else "A",
                             arm="anchor_single0"))
    return rows


class TestAggregate:
    def test_metrics_and_verdict_promote(self):
        # vote5 40/40；single@T=sample0=B → 40/40 → Δ1=0；锚定 35/40 → Δ2=+5
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        m = aggregate_metrics(rows, repeats=3)
        assert m["acc"]["vote5"] == [1.0, 1.0, 1.0]
        assert m["acc"]["single_t"] == [1.0, 1.0, 1.0]
        assert m["acc"]["anchor"] == [0.875, 0.875, 0.875]
        assert m["delta1_pp"] == 0.0 and m["delta2_pp"] == 12.5   # 100% − 87.5%
        assert m["unresolved_rate"] == 0.0
        assert gate_verdict(3.0, 0.0) == "PROMOTE_CANDIDATE"
        assert gate_verdict(3.0, -0.5) == "AGGREGATION_EFFECT_ONLY"
        assert gate_verdict(2.9, 5.0) == "NON_INFERIOR"
        assert gate_verdict(-3.0, 0.0) == "ROLLBACK"
        assert gate_verdict(0.0, 5.0) == "NON_INFERIOR"

    def test_unresolved_counts_wrong_and_rate(self):
        # 每题 2B/2A/1C → strict 无 3 票 → unresolved → 计错且计入 unresolved 率
        rows = []
        for rep in range(3):
            for i in range(40):
                for j, L in enumerate(["B", "B", "A", "A", "C"]):
                    rows.append(srow(f"c{i}", rep, j, L))
                rows.append(srow(f"c{i}", rep, 0, "B", arm="anchor_single0"))
        m = aggregate_metrics(rows, repeats=3)
        assert m["acc"]["vote5"] == [0.0, 0.0, 0.0]
        assert m["unresolved_rate"] == 1.0
        # single@T = sample0 = B → 全对；Δ1 = 0 - 100 = -100
        assert m["delta1_pp"] == -100.0

    def test_no_cross_repeat_aggregation(self):
        """repeat 间永不混合：r0 全对 r1/r2 全错 → per-repeat [100,0,0] 而非均值污染。"""
        rows = []
        for rep in range(3):
            win = rep == 0
            for i in range(40):
                letters = ["B", "B", "B", "A", "A"] if win else ["A", "A", "A", "B", "B"]
                for j, L in enumerate(letters):
                    rows.append(srow(f"c{i}", rep, j, L))
                rows.append(srow(f"c{i}", rep, 0, "B" if win else "A", arm="anchor_single0"))
        m = aggregate_metrics(rows, repeats=3)
        assert m["acc"]["vote5"] == [1.0, 0.0, 0.0]
        # r0 单样本（sample0=B）对、r1/r2（sample0=A）错 → 每 repeat Δ1 各自独立为 0
        assert m["per_repeat_delta1"] == [0.0, 0.0, 0.0]
        assert m["delta1_pp"] == 0.0

    def test_incomplete_case_repeat_raises(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows = [r for r in rows
                if not (r["case_id"] == "c0" and r["attempt_key"][7] == 0
                        and r["attempt_key"][8] == 4)]          # 删 c0/r0/sample4
        with pytest.raises(ValueError, match="不完整"):
            strict_rows_complete(rows, repeats=3)

    def test_four_grid(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        m = aggregate_metrics(rows, repeats=3)
        g = m["four_grid_vote5_vs_anchor"]      # vote5 全对；锚定 35 对 5 错
        assert g == {"both": 105, "vote5_only": 15, "anchor_only": 0, "neither": 0}


class TestRunVote:
    def test_slices_in_order_and_ledger(self, tmp_path):
        spy = RunnerSpy()
        cfg = fake_vote_config(root=tmp_path)
        sched = build_main_schedule(cfg, CASE_IDS)
        result = run_vote(cfg, sched, slice_runner=spy)
        assert result["status"] == "OK"
        assert len(spy.calls) == 12
        # 幂等：同 schedule 再跑（spy 报 0 新调用）不触发溢出
        result2 = run_vote(cfg, sched, slice_runner=spy)
        assert result2["status"] == "OK"

    def test_blocked_incomplete_on_exit3(self, tmp_path):
        class Spy3(RunnerSpy):
            def __call__(self, slice_run, **kw):
                super().__call__(slice_run, **kw)
                return type("R", (), {"exit_code": 3, "records": [], "calls_attempted": 0})
        cfg = fake_vote_config(root=tmp_path)
        result = run_vote(cfg, build_main_schedule(cfg, CASE_IDS), slice_runner=Spy3())
        assert result["status"] == "BLOCKED_INCOMPLETE"
```

- [ ] **Step 2：运行确认失败** → `ModuleNotFoundError`。

- [ ] **Step 3：实现（完整代码）**

**(a) `scripts/build_phase6_audit_index.py` 微改（决策 9）**：`main()` 加 `parser.add_argument("--arms", default="ctx_approved,ctx_legacy")`；`recompute_accuracy(run["detail_rows"], arms=tuple(args.arms.split(",")))`；`recompute_accuracy` 签名改 `(detail_rows, arms=("ctx_approved","ctx_legacy"), repeats=3)`，函数体内两臂引用参数化。加一条测试到 `tests/test_phase6_6a1_vote.py`：

```python
    def test_audit_arms_param(self):
        from scripts.build_phase6_audit_index import recompute_accuracy
        rows = []
        for rep in range(3):
            for i in range(4):
                rows.append({"attempt_key": ["d", "p", "vote5_samples", "m", "p", "m",
                                             f"c{i}", rep, 0, "p0"], "correct": True})
                rows.append({"attempt_key": ["d", "p", "anchor_single0", "a", "p", "m",
                                             f"c{i}", rep, 0, "p0"], "correct": False})
        out = recompute_accuracy(rows, arms=("vote5_samples", "anchor_single0"))
        assert out["delta_dev_pp"] == 100.0
```

**(b) `scripts/run_phase6_6a1_ablation.py`（新文件，完整代码）**

```python
"""Phase 6 6A1 编排器：严格 ≥3/5 投票同源配对 + temp-0 锚定（设计 v6 §5）。

probe 多样性试测（T 冻结链）→ AB/BA 12 切片（采样臂 emit_samples + 锚定臂 single@0）
→ 离线严格聚合（strict_majority，不跨 repeat）→ Δ1/Δ2 + 四格表 + unresolved 率 → verdict。
决策逻辑均为无网络纯函数；真实模型调用仅经 run_slice 子进程边界发起。
上下文基线 legacy_v0（6A0 ROLLBACK，设计 §10）。预算复用 6A0 BudgetLedger。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.formatters.baziqa_prompt import format_direct_choice_prompt
from benchmark.formatters.chart_context import render_chart_context
from benchmark.formatters.leak_scan import scan_prompt_for_leaks
from benchmark.runners.profiles import assert_visibility, resolve_profile
from benchmark.runners.self_consistency import strict_majority
from scripts.build_phase6_audit_index import sha256_file
from scripts.enrich_baziqa_chart_input import load_jsonl
from scripts.run_phase6_6a0_ablation import (
    BudgetLedger,
    BudgetLedgerCorrupt,
    cost_proxy,
    split_ab_ba,
    _git_head,
)

PROFILE_ID = "baziqa_xjz_direct"
SCHEMA = "legacy_v0"                      # 6A0 ROLLBACK 锁定（设计 §10）
EXPECTED_CASES = 40
N_SAMPLES = 5
PROBE_CASES = 10
DIVERSITY_THRESHOLD = 0.6
DEFAULT_T = 0.4
FALLBACK_T = 1.0
ARM_SAMPLE = "vote5_samples"
ARM_ANCHOR = "anchor_single0"
ANCHOR_CAPS = (24, 23, 23, 23, 23, 24)    # 和 140
SAMPLE_CAPS = (110,) * 6                  # 和 660
PROBE_CAP = 55


@dataclass(frozen=True)
class VoteConfig:
    run_id: str
    year: int
    root: Path
    enriched_path: Path
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    repeats: int = 3
    seed: int = 20260717
    stage_hard_cap: int = 910               # 2021 复核：800
    resume: bool = True


@dataclass(frozen=True)
class VoteSlice:
    purpose: str                            # "probe" | "main"
    repeat_idx: int                         # probe 固定 -1
    arm: str
    stage: str
    group: str
    case_ids: tuple
    n_samples: int
    temperature: float                      # 采样臂=sample_temperature；锚定=0.0
    scheduled_calls: int
    hard_cap: int


# ---------- 纯函数：probe 多样性 ----------

def diversity_rate(rows: list) -> float:
    """每题 ≥2 个不同 predicted_answer 的比例（不查看答案正确性——设计 §5.2.2）。"""
    per_case = {}
    for r in rows:
        per_case.setdefault(r["case_id"], set()).add(r.get("predicted_answer"))
    if not per_case:
        return 0.0
    diverse = sum(1 for s in per_case.values() if len(s) >= 2)
    return round(diverse / len(per_case), 4)


def evaluate_t_switch(rate_r1: float, rate_r2) -> tuple:
    """T 冻结链（计划决策 4）：返回 (action, T)。r2 未运行传 None。"""
    if rate_r1 >= DIVERSITY_THRESHOLD:
        return ("freeze", DEFAULT_T)
    if rate_r2 is None:
        return ("probe_r2", DEFAULT_T)
    if rate_r2 >= DIVERSITY_THRESHOLD:
        return ("freeze", FALLBACK_T)
    return ("freeze_low_diversity", FALLBACK_T)


# ---------- 纯函数：调度 ----------

def build_probe_slice(config: VoteConfig, case_ids: list, arm: str,
                      temperature: float) -> VoteSlice:
    return VoteSlice("probe", -1, arm, "diversity_probe", "probe",
                     tuple(case_ids[:PROBE_CASES]), N_SAMPLES, temperature,
                     PROBE_CASES * N_SAMPLES, PROBE_CAP)


def build_main_schedule(config: VoteConfig, case_ids: list,
                        sample_temperature: float = DEFAULT_T) -> list:
    if len(case_ids) != EXPECTED_CASES:
        raise ValueError(f"6A1 要求 {EXPECTED_CASES} 题，实得 {len(case_ids)}")
    group_a, group_b = split_ab_ba(case_ids, config.seed)
    groups = {"group_a": group_a, "group_b": group_b}
    schedule = []
    sample_count = 0
    anchor_count = 0
    for rep in range(config.repeats):
        for arm, stage, group, n, temp, sched in (
                (ARM_SAMPLE, "main", "group_a", N_SAMPLES, sample_temperature, 100),
                (ARM_ANCHOR, "anchor", "group_a", 1, 0.0, 20),
                (ARM_ANCHOR, "anchor", "group_b", 1, 0.0, 20),
                (ARM_SAMPLE, "main", "group_b", N_SAMPLES, sample_temperature, 100)):
            if arm == ARM_SAMPLE:
                cap = SAMPLE_CAPS[sample_count]
                sample_count += 1
            else:
                cap = ANCHOR_CAPS[anchor_count]
                anchor_count += 1
            schedule.append(VoteSlice("main", rep, arm, stage, group, groups[group],
                                      n, temp, sched, cap))
    if sum(s.hard_cap for s in schedule) != 660 + sum(ANCHOR_CAPS):
        raise ValueError("cap 和异常")
    return schedule


# ---------- 纯函数：严格聚合与指标 ----------

def _arm_repeat(r, arm, repeat):
    ak = r.get("attempt_key") or [None] * 10
    return ak[2] == arm and ak[7] == repeat


def strict_rows_complete(rows: list, repeats: int) -> None:
    """每 (case, repeat) 采样臂恰好 5 行 + 锚定 1 行；否则数据不完整（不得进入决策）。"""
    samples, anchors = {}, {}
    for r in rows:
        ak = r.get("attempt_key") or [None] * 10
        if ak[2] == ARM_SAMPLE:
            samples.setdefault((r["case_id"], ak[7]), set()).add(ak[8])
        elif ak[2] == ARM_ANCHOR:
            anchors.setdefault((r["case_id"], ak[7]), set()).add(ak[8])
    for key, idxs in samples.items():
        if idxs != {0, 1, 2, 3, 4}:
            raise ValueError(f"不完整：{key} 采样行 sample_idx={sorted(idxs)}")
    for key, idxs in anchors.items():
        if idxs != {0}:
            raise ValueError(f"不完整：{key} 锚定行 sample_idx={sorted(idxs)}")


def aggregate_metrics(rows: list, repeats: int) -> dict:
    """按 (case, repeat) 聚合：vote5=strict_majority(5 样本)；single@T=sample_idx 0；
    锚定=anchor 行。unresolved/invalid/call_failed 计错；禁止跨 repeat（§5.2.6）。"""
    strict_rows_complete(rows, repeats)
    acc = {"vote5": [], "single_t": [], "anchor": []}
    per_repeat_delta1, per_repeat_delta2 = [], []
    unresolved = 0
    grid_t = {"both": 0, "vote5_only": 0, "single_t_only": 0, "neither": 0}
    grid_a = {"both": 0, "vote5_only": 0, "anchor_only": 0, "neither": 0}
    for rep in range(repeats):
        cases = sorted({r["case_id"] for r in rows if _arm_repeat(r, ARM_SAMPLE, rep)})
        n_v5 = n_st = n_an = 0
        for cid in cases:
            srows = sorted((r for r in rows
                            if r["case_id"] == cid and _arm_repeat(r, ARM_SAMPLE, rep)),
                           key=lambda r: r["attempt_key"][8])
            arow = next(r for r in rows
                        if r["case_id"] == cid and _arm_repeat(r, ARM_ANCHOR, rep))
            votes = [r["predicted_answer"] if r["terminal_state"] == "parsed" else None
                     for r in srows]
            v5 = strict_majority(votes)
            if v5 is None:
                unresolved += 1
            exp = srows[0]["expected_answer"]
            ok_v5 = v5 is not None and v5 == exp
            ok_st = (srows[0]["terminal_state"] == "parsed"
                     and srows[0]["predicted_answer"] == exp)
            ok_an = (arow["terminal_state"] == "parsed"
                     and arow["predicted_answer"] == exp)
            n_v5 += ok_v5; n_st += ok_st; n_an += ok_an
            grid_t["both" if ok_v5 and ok_st else
                   "vote5_only" if ok_v5 else
                   "single_t_only" if ok_st else "neither"] += 1
            grid_a["both" if ok_v5 and ok_an else
                   "vote5_only" if ok_v5 else
                   "anchor_only" if ok_an else "neither"] += 1
        n = len(cases)
        acc["vote5"].append(round(n_v5 / n, 4))
        acc["single_t"].append(round(n_st / n, 4))
        acc["anchor"].append(round(n_an / n, 4))
        per_repeat_delta1.append(round((n_v5 - n_st) / n * 100, 2))
        per_repeat_delta2.append(round((n_v5 - n_an) / n * 100, 2))
    total = sum(len({r["case_id"] for r in rows if _arm_repeat(r, ARM_SAMPLE, rep)})
                for rep in range(repeats))
    return {
        "acc": acc,
        "per_repeat_delta1": per_repeat_delta1,
        "per_repeat_delta2": per_repeat_delta2,
        "delta1_pp": round(sum(per_repeat_delta1) / repeats, 2),
        "delta2_pp": round(sum(per_repeat_delta2) / repeats, 2),
        "unresolved_rate": round(unresolved / max(total, 1), 4),
        "four_grid_vote5_vs_single_t": grid_t,
        "four_grid_vote5_vs_anchor": grid_a,
        "call_failed": sum(1 for r in rows if r.get("terminal_state") == "call_failed"),
    }


def gate_verdict(delta1_pp: float, delta2_pp: float) -> str:
    """设计 §5.3 dev gate。"""
    if delta1_pp >= 3.0:
        return "PROMOTE_CANDIDATE" if delta2_pp >= 0.0 else "AGGREGATION_EFFECT_ONLY"
    if delta1_pp <= -3.0:
        return "ROLLBACK"
    return "NON_INFERIOR"


def recheck_verdict(delta1_year: float, delta2_year: float) -> str:
    """设计 §5.3 复核（仅 2021）：双条件通过方确认。"""
    return "PROMOTE_CONFIRMED" if delta1_year >= 2.0 and delta2_year >= 0.0 \
        else "RECHECK_FAILED"


# ---------- 离线 gate / 真实边界 ----------

def offline_gate(config: VoteConfig) -> list:
    """legacy_v0 单上下文：可见性矩阵 + 泄漏扫描（无网络）。"""
    failures = []
    if not config.enriched_path.exists():
        return [f"enriched 文件缺失: {config.enriched_path}"]
    profile = resolve_profile(PROFILE_ID, SCHEMA)
    for row in load_jsonl(config.enriched_path):
        cid = row.get("case_id")
        rendered = render_chart_context(row, SCHEMA)
        for v in assert_visibility(rendered, profile, SCHEMA):
            failures.append(f"{cid}: {v}")
        prompt = format_direct_choice_prompt(row, chart_context_text=rendered)
        for hit in scan_prompt_for_leaks(prompt, row):
            failures.append(f"{cid}: leak {hit.kind} {hit.detail}")
    return failures


def run_slice(slice_run: VoteSlice, config: VoteConfig, **kwargs) -> object:
    """真实边界：子进程调用 runner（emit_samples / 单轮锚定）。--repeat-idx 原样透传。"""
    run_dir = (config.root / slice_run.arm / "runs" / config.run_id
               / f"slice_{slice_run.purpose}_{slice_run.repeat_idx}_{slice_run.group}")
    run_dir.mkdir(parents=True, exist_ok=True)
    ids_file = run_dir / "case_ids.json"
    ids_file.write_text(json.dumps(list(slice_run.case_ids), ensure_ascii=False),
                        encoding="utf-8")
    argv = [
        sys.executable, "-m", "benchmark.runners.run_benchmark",
        "--dataset", str(config.enriched_path),
        "--model-runner", "--provider", config.provider, "--model", config.model,
        "--profile", PROFILE_ID, "--chart-schema-version", SCHEMA,
        "--arm", slice_run.arm, "--attempt-stage", slice_run.stage,
        "--repeat-idx", str(slice_run.repeat_idx),
        "--case-ids-file", str(ids_file),
        "--case-details-jsonl", str(run_dir / "detail.jsonl"),
        "--output-dir", str(run_dir),
        "--scheduled-calls", str(slice_run.scheduled_calls),
        "--hard-cap", str(slice_run.hard_cap),
        "--temperature", "0.0",
        "--n-samples", str(slice_run.n_samples),
        "--sample-temperature", str(slice_run.temperature),
    ]
    if slice_run.n_samples > 1:
        argv += ["--aggregate", "emit_samples"]
    if config.resume:
        argv.append("--resume")
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=PROJECT_ROOT)
    calls_attempted = 0
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        try:
            calls_attempted = int(json.loads(summary_path.read_text(encoding="utf-8"))
                                  .get("calls_attempted") or 0)
        except Exception:
            calls_attempted = 0
    if not calls_attempted:
        events_path = run_dir / "detail.events.jsonl"
        if events_path.exists():
            calls_attempted = sum(
                1 for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line).get("kind") == "call_attempt")
    return type("SliceResult", (), {"exit_code": proc.returncode, "records": [],
                                    "calls_attempted": calls_attempted,
                                    "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]})


def run_vote(config: VoteConfig, schedule: list, slice_runner=None) -> dict:
    """与 6A0 run_ablation 同语义：schedule 调用方传入；BudgetLedger 按 slice_id 幂等。"""
    runner = slice_runner or (lambda s, **kw: run_slice(s, config, **kw))
    ledger = BudgetLedger(config.root / "budget" / f"{config.run_id}.jsonl")
    for s in schedule:
        slice_id = f"{s.purpose}_{s.repeat_idx}_{s.arm}_{s.group}"
        try:
            attempted = ledger.attempted_for(slice_id)
            overflow = (ledger.total_attempted() + (s.hard_cap - attempted)
                        > config.stage_hard_cap)
        except BudgetLedgerCorrupt as exc:
            return {"status": "BLOCKED_INCOMPLETE", "reason": f"budget ledger corrupt: {exc}"}
        if attempted > s.hard_cap:
            return {"status": "BLOCKED_INCOMPLETE",
                    "reason": f"budget ledger inconsistent: {slice_id}"}
        if overflow:
            return {"status": "FAILED",
                    "reason": f"stage budget overflow at {slice_id}",
                    "abort_at": {"arm": s.arm, "repeat_idx": s.repeat_idx, "group": s.group}}
        result = runner(s, scheduled_calls=s.scheduled_calls, hard_cap=s.hard_cap)
        try:
            ledger.record(slice_id, s.hard_cap, getattr(result, "calls_attempted", 0) or 0)
        except BudgetLedgerCorrupt as exc:
            return {"status": "BLOCKED_INCOMPLETE", "reason": f"budget ledger corrupt: {exc}"}
        if result.exit_code == 3:
            return {"status": "BLOCKED_INCOMPLETE",
                    "abort_at": {"arm": s.arm, "repeat_idx": s.repeat_idx, "group": s.group}}
        if result.exit_code != 0:
            return {"status": "FAILED", "exit_code": result.exit_code,
                    "abort_at": {"arm": s.arm, "repeat_idx": s.repeat_idx}}
    return {"status": "OK"}


def _load_run_rows(config: VoteConfig) -> list:
    rows = []
    for arm in (ARM_SAMPLE, ARM_ANCHOR):
        runs_dir = config.root / arm / "runs" / config.run_id
        if not runs_dir.exists():
            continue
        for detail in sorted(runs_dir.glob("slice_main_*/detail.jsonl")):
            for line in detail.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def write_report(config: VoteConfig, case_ids: list, temperature: float,
                 probe_info: dict, recheck: bool = False) -> dict:
    rows = _load_run_rows(config)
    m = aggregate_metrics(rows, config.repeats)
    verdict = (recheck_verdict(m["delta1_pp"], m["delta2_pp"]) if recheck
               else gate_verdict(m["delta1_pp"], m["delta2_pp"]))
    pollution = m["call_failed"] > len(case_ids) * 0.05
    out_dir = PROJECT_ROOT / "docs" / "phase6" / config.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"run_id": config.run_id, "year": config.year, "status": "OK",
               "sample_temperature": temperature, "recheck": recheck, **m,
               "verdict": verdict, "pollution_flag": pollution,
               "stage_hard_cap": config.stage_hard_cap}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    manifest = {
        "run_id": config.run_id, "seed": config.seed, "profile_id": PROFILE_ID,
        "chart_schema_version": SCHEMA, "sample_temperature": temperature,
        "temperature_freeze": probe_info,
        "dataset_sha256": sha256_file(config.enriched_path),
        "provider": config.provider, "model": config.model, "code_hash": _git_head(),
        "reproducibility_note": "请求不携带 seed；复现依赖 detail 行 raw_answer 与调用顺序",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    lines = [
        f"# 6A1 严格投票报告（{config.run_id}，{config.year}{'，2021 复核' if recheck else ''}）",
        "",
        f"- T = {temperature}（冻结链：{json.dumps(probe_info, ensure_ascii=False)}）",
        f"- Δ1（vote5−single@T，同源）= {m['delta1_pp']}pp（每 repeat：{m['per_repeat_delta1']}）",
        f"- Δ2（vote5−single@0，锚定）= {m['delta2_pp']}pp（每 repeat：{m['per_repeat_delta2']}）",
        f"- 准确率 vote5/single@T/anchor：{m['acc']['vote5']} / {m['acc']['single_t']} / {m['acc']['anchor']}",
        f"- unresolved 率：{m['unresolved_rate']}（>20% 为显著发现，不否决）",
        f"- 四格 vote5×single@T：{json.dumps(m['four_grid_vote5_vs_single_t'], ensure_ascii=False)}",
        f"- 四格 vote5×anchor：{json.dumps(m['four_grid_vote5_vs_anchor'], ensure_ascii=False)}",
        f"- call_failed：{m['call_failed']}（污染标注：{'是' if pollution else '否'}）",
        f"- 判定：**{verdict}**",
        "",
        "如实声明：API 未返回 token usage；采样不可由 seed 复现；40 题样本，2 题即 5pp，禁止过度表述。",
    ]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 6A1 严格投票编排器")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--root", type=Path, default=Path(".tmp/phase6"))
    parser.add_argument("--recheck", action="store_true",
                        help="2021 复核模式：无 probe，--sample-temperature 必填")
    parser.add_argument("--sample-temperature", type=float, default=None)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    enriched = args.root / "datasets" / f"baziqa_contest8_{args.year}_holdout_enriched.jsonl"
    hard_cap = 800 if args.recheck else 910
    config = VoteConfig(run_id=args.run_id, year=args.year, root=args.root,
                        enriched_path=enriched, provider=args.provider,
                        model=args.model, stage_hard_cap=hard_cap)
    failures = offline_gate(config)
    if failures:
        print(json.dumps({"status": "OFFLINE_GATE_FAILED", "failures": failures[:20]},
                         ensure_ascii=False))
        return 1
    case_ids = [str(r["case_id"]) for r in load_jsonl(enriched)]
    group_a, _ = split_ab_ba(case_ids, config.seed)

    probe_info = {"mode": "recheck" if args.recheck else "dev"}
    if args.recheck:
        if args.sample_temperature is None:
            print("复核模式必须显式 --sample-temperature（取 dev stage manifest 冻结值）")
            return 2
        temperature = args.sample_temperature
        probe_info["t_source"] = "dev manifest（人工转录并核对）"
    else:
        # probe_r1 → 多样性评估 → 条件 probe_r2 → T 冻结（计划决策 4）
        r1 = build_probe_slice(config, group_a, "probe_r1", DEFAULT_T)
        print(f"probe_r1：{r1.scheduled_calls} 次调用（cap {r1.hard_cap}）")
        if not args.yes:
            print("加 --yes 确认预算后执行")
            return 0
        result = run_vote(config, [r1])
        if result["status"] != "OK":
            print(json.dumps(result, ensure_ascii=False))
            return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
        r1_rows = []
        for detail in (config.root / "probe_r1" / "runs" / config.run_id
                       ).glob("slice_probe_*/detail.jsonl"):
            r1_rows += [json.loads(x) for x in
                        detail.read_text(encoding="utf-8").splitlines() if x.strip()]
        rate1 = diversity_rate(r1_rows)
        action, temperature = evaluate_t_switch(rate1, None)
        probe_info.update({"rate_r1": rate1, "action_r1": action})
        if action == "probe_r2":
            r2 = build_probe_slice(config, group_a, "probe_r2", FALLBACK_T)
            result = run_vote(config, [r2])
            if result["status"] != "OK":
                print(json.dumps(result, ensure_ascii=False))
                return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
            r2_rows = []
            for detail in (config.root / "probe_r2" / "runs" / config.run_id
                           ).glob("slice_probe_*/detail.jsonl"):
                r2_rows += [json.loads(x) for x in
                            detail.read_text(encoding="utf-8").splitlines() if x.strip()]
            rate2 = diversity_rate(r2_rows)
            action, temperature = evaluate_t_switch(rate1, rate2)
            probe_info.update({"rate_r2": rate2, "action_r2": action})
        print(f"T 冻结为 {temperature}（{probe_info}）")

    schedule = build_main_schedule(config, case_ids, sample_temperature=temperature)
    total = sum(s.scheduled_calls for s in schedule)
    print(f"主实验：{total} 次调用（cap {sum(s.hard_cap for s in schedule)}），"
          f"切片 {len(schedule)}，T={temperature}")
    if not args.yes:
        print("加 --yes 确认预算后执行")
        return 0
    result = run_vote(config, schedule)
    if result["status"] != "OK":
        print(json.dumps(result, ensure_ascii=False))
        return 3 if result["status"] == "BLOCKED_INCOMPLETE" else 2
    summary = write_report(config, case_ids, temperature, probe_info,
                           recheck=args.recheck)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

注意 `build_main_schedule` 里采样臂 cap 取法：按已排采样切片数索引 `SAMPLE_CAPS`（0..5）；锚定臂按序取 `ANCHOR_CAPS`。测试 `test_main_schedule_order_and_caps` 锁定 cap 和 = 660+140。

- [ ] **Step 4：运行确认全绿 + 4 组回归**。

- [ ] **Step 5：提交（精确路径）**

```powershell
git add scripts/run_phase6_6a1_ablation.py scripts/build_phase6_audit_index.py tests/test_phase6_6a1_vote.py
git commit -m "feat(phase6): 6A1 编排器（probe T 冻结 + AB/BA + 严格聚合 + Δ1/Δ2 + verdict）"
```

---

## Task 4：真实执行——dev 2024（scheduled ≤820 / hard_cap 910）

**前置核对（全部满足才执行）**：Task 1–3 合入且 4 组回归全绿；`.env` 含 `DEEPSEEK_API_KEY`；`.tmp/phase6/datasets/baziqa_contest8_2024_holdout_enriched.jsonl` 在位（40 题）；工作区状态已知。

- [ ] **Step 1：probe（50 次真实调用，可先无 --yes 干跑看预算）**

```powershell
python scripts/run_phase6_6a1_ablation.py --run-id 6a1-2024-001 --year 2024 --yes
```

预期：离线 gate 通过；probe_r1 完成；打印 T 冻结结果（`rate_r1` 与 action；若触发 probe_r2 再 50 次）。

- [ ] **Step 2：主实验（720 次真实调用，接续同一命令自动完成；中断重跑同一命令即可，resume 幂等）**

预期产物：`docs/phase6/6a1-2024-001/{report.md, summary.json, manifest.json}`。

- [ ] **Step 3：审计索引归档**

```powershell
python scripts/build_phase6_audit_index.py --run-id 6a1-2024-001 --year 2024 --arms vote5_samples,anchor_single0
git add docs/phase6/6a1-2024-001
git commit -m "docs(phase6): 6A1 2024 dev gate 运行结果（verdict=<实际判定>，T=<冻结值>）"
```

- [ ] **Step 4：判读（设计 §5.3）**

- `PROMOTE_CANDIDATE` → 进入 Task 5（2021 复核）；
- `AGGREGATION_EFFECT_ONLY` / `NON_INFERIOR` / `ROLLBACK` → 不进入 Task 5，protocol=single 写入结论，6B1 以 single 继续（设计 §10 不整体停工）。

## Task 5（条件触发）：2021 复核（scheduled 720 / hard_cap 800）

**仅当 Task 4 判 PROMOTE_CANDIDATE 才执行。** 温度取 dev manifest 的 `sample_temperature`（人工核对后显式传入）。

- [ ] **Step 1：复核运行**

```powershell
python scripts/run_phase6_6a1_ablation.py --run-id 6a1-2021-001 --year 2021 --recheck --sample-temperature <dev 冻结值> --yes
```

- [ ] **Step 2：归档与判读**

```powershell
python scripts/build_phase6_audit_index.py --run-id 6a1-2021-001 --year 2021 --arms vote5_samples,anchor_single0
git add docs/phase6/6a1-2021-001
git commit -m "docs(phase6): 6A1 2021 复核结果（verdict=<实际判定>）"
```

- `PROMOTE_CONFIRMED`（Δ1_year ≥ +2pp 且 Δ2_year ≥ 0）→ vote5 成为后续臂默认协议；
- `RECHECK_FAILED` → 不设默认，结论如实记录，6B1 以 protocol=single 继续。
- **2022 不在本阶段打开**（设计 §5.3：杜绝选择性验证）。

---

## 设计 gate 映射表（设计 v6 ↔ 本计划任务 ↔ 验证）

| 设计条目 | 位置 | 任务 | 验证 |
| --- | --- | --- | --- |
| T 冻结 0.4 / 多样性试测 / 切换 1.0 | §5.2.1-2 | Task 3 | `diversity_rate`/`evaluate_t_switch` 单测 + 真实 probe |
| 锚定臂同时间窗 single@0 | §5.2.3 | Task 2/3 | `--attempt-stage` 键测试 + AB/BA 顺序测试 |
| strict_majority ≥3/5、无破平局、invalid 占分母 | §5.2.4 | Task 1 | 8 条边界单测（3/1/1、2/2/1、2/1/1/1、None 分母等） |
| 同源配对 single@T=sample0；原始响应持久化 | §5.2.5 | Task 2/3 | emit 行 sample_idx 测试；`raw_response_path` 沿用 |
| repeats 内聚合、禁止 15 次再投票 | §5.2.6 | Task 3 | `test_no_cross_repeat_aggregation` |
| 首类指标四件套 + trimmed mean 附列 | §5.2.7 / §2.1 | Task 3 | 四格表/unresolved/成本代理测试；报告字段 |
| dev gate 四分支 verdict | §5.3 | Task 3/4 | `gate_verdict` 边界（+3/−3、Δ2 符号） |
| 2021 复核双条件、2022 不打开 | §5.3 | Task 5 | `recheck_verdict` 单测；计划硬性条件触发 |
| 预算双列 820/910、720/800 | §8 | Task 3 | `build_main_schedule` cap 和断言 + BudgetLedger 幂等测试 |
| BLOCKED_INCOMPLETE 不得决策 | §4.4.2 / §10 | Task 3 | exit 3 → BLOCKED 测试；判读步骤明示 |
| unresolved >20% 显著发现不否决 | §5.3 | Task 3 | 报告字段 + 测试 |
| 审计索引（dataset/slice/detail SHA、复算） | 6A0 收口延展 | Task 4/5 | `--arms` 复算与归档一致 |

## 执行纪律（与 6A0 计划同款，执行代理必读）

1. **TDD**：每任务先写失败测试并运行确认失败，再实现；不回改测试迁就实现。
2. **git 纪律**：`git add` 只列该任务精确路径；禁止 `git add -A` / `git add tests/` / `git add .`。
3. **回归**：每任务提交前 4 组（`.tmp/g{1..4}.txt`）`-m "not e2e"` 全绿；`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`。
4. **不伪造运行结果**：`docs/phase6/<run_id>/` 与 `.tmp/phase6/**` 由真实运行生成；实现阶段只写代码与测试。
5. **设计缺口处理**：第三次温度切换、RESUME_MANIFEST 加 stage、probe 选题规则等——按计划 §1 决策记录呈现，不发明、不静默放宽。
6. **真实调用纪律**：Task 4/5 涉及真实 API 费用；先 probe 小步验证再主实验；中断重跑同一命令（resume 幂等）；任何 BLOCKED_INCOMPLETE 排查后续跑，不得进入决策。
7. **密钥纪律**：`DEEPSEEK_API_KEY` 只读 `.env`；日志/报告/manifest 不得出现密钥。
