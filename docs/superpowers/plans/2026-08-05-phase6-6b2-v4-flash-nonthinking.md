# Phase 6 6B2 DeepSeek-V4-Flash Non-Thinking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Phase 6 6B2 的 dev → reuse → final_2023 实验链冻结为 `deepseek/deepseek-v4-flash/disabled`，并让请求、恢复、归档、跨阶段准入和报告使用同一可审计协议。

**Architecture:** 由 `phase6_6b2_orchestrator.py` 持有冻结协议并在零 API 调用前校验；runner 只通过显式 `--thinking-mode disabled` 接收该协议；`claude_api.py` 保持默认行为不变，仅在显式参数存在时写入 DeepSeek payload。`run_context.json` 约束整条 run，slice manifest 约束单次恢复，audit/receipt 约束跨阶段证据链。

**Tech Stack:** Python 3.11+、argparse、urllib、JSON/JSONL、SHA-256、pytest、monkeypatch、PowerShell。

---

## 实施边界与基线

设计依据：`docs/superpowers/specs/2026-08-05-phase6-6b2-v4-flash-nonthinking-design.md`。

只修改以下生产文件：

- `claude_api.py`
- `benchmark/runners/run_benchmark.py`
- `scripts/phase6_6b2_orchestrator.py`
- `scripts/phase6_6b2_sealed_workflow.py`

只修改以下测试文件：

- `tests/test_claude_api.py`
- `tests/phase6_helpers.py`
- `tests/test_phase6_resume.py`
- `tests/test_phase6_retry_budget.py`
- `tests/test_phase6_6b2.py`

不修改 `config.py` 的全局 DeepSeek 默认值，不修改 streaming API，不迁移或重写旧 V4-Pro 产物，不修改题集、arm、repeat、预算、gate 阈值或 2023 密封规则。

本计划是已合入 6B2 v18 编排骨架之后的协议硬化增量；先保留 v18 的 schedule、smoke、预算、归档和密封执行顺序，再在其外层增加 V4-Flash non-thinking 约束，不重做 v18 已完成任务。

准确率门槛继续使用现有 `dual_merged_acc >= 0.325`（32.5%）及既有 delta/min-year 判定；协议切换不得改动 `compute_gate()` 的任何阈值。

跨实验影响声明：`RESUME_MANIFEST_FIELDS` 是 Phase 6 共用字段集。加入 `thinking_mode` 后，6A0/6A1/6B1 时代缺少该字段的旧 manifest 会在 resume 时以 `<MISSING>` fail-closed。这是预期保护行为；仍在运行的旧实验必须使用冻结代码继续，不能用本计划实施后的 runner 续跑，也不能补写旧 manifest。

2026-08-05 已复跑基线：

```powershell
python -m pytest tests/test_phase6_6b2.py tests/test_phase6_profiles.py tests/test_dual_system_reasoning.py -q --basetemp .tmp/pytest-plan-baseline-20260805
```

结果：`148 passed, 1 warning`。

Phase 6 广泛基线：

```powershell
$files = (Get-ChildItem tests -Filter 'test_phase6_*.py').FullName
python -m pytest $files tests/test_dual_system_reasoning.py tests/test_claude_api.py -q --basetemp .tmp/pytest-plan-phase6-baseline-20260805
```

结果：`657 passed, 1 failed, 2 warnings`。唯一既有失败为 `tests/test_phase6_6b1d_integration.py::TestFromSliceAudit::test_from_slice_with_completed_skipped_passes`，原因是当前 Windows 沙箱内 6B1D archive 临时目录原子改名返回 `WinError 5`。实施后不得新增失败；最终交付必须如实分别报告 6B2 定向结果和广泛结果。

### 审核修订映射

| 审核项 | 计划落点 |
|---|---|
| B1 `_Resp` 同名冲突 | Task 2 使用 `_JsonResp`，明确保留既有 `_Resp` |
| M1 既有测试连带失败 | Task 1/4/5/6 分别列出公共入口、slice、report、archive/receipt 夹具更新清单 |
| M2 旧 manifest 影响 | 实施边界声明 6A0/6A1/6B1 旧 manifest fail-closed |
| L1 环境变量覆盖 | Task 1 `test_environment_cannot_override_frozen_protocol` |
| L2 slice status 响应模型 | Task 4 从 call_meta 聚合并写 `response_model` |
| L3 重复原子写/父目录 | Task 5 复用既有 `_atomic_write_json` 并先创建 `runs/` 父目录 |
| L4 报错文案漂移 | Task 5 固定 `run_context.json missing: refusing legacy run migration` |
| L5 fake runner 无骨架 | Task 8 提供 detail/events/manifest fake subprocess 完整骨架 |
| L6 测试类名 | Task 6 使用真实 `TestCodeFingerprintCriticalCoverage` |
| L7 32.5% 阈值 | 实施边界明确锚定 `dual_merged_acc >= 0.325` |
| L8 v18 顺序 | 实施边界声明本计划是 v18 后置协议硬化增量 |

## Task 1: 冻结 6B2 协议并建立零调用入口门禁

**Files:**

- Modify: `scripts/phase6_6b2_orchestrator.py:23-45`
- Modify: `scripts/phase6_6b2_orchestrator.py:1244-1465`
- Test: `tests/test_phase6_6b2.py:986-1005`
- Test: `tests/test_phase6_6b2.py:1594-1643`

- [ ] **Step 1: 写冻结常量与入口拒绝测试**

在 `tests/test_phase6_6b2.py` 新增 `TestFrozenV4FlashProtocol`：

```python
class TestFrozenV4FlashProtocol:
    def test_constants_are_exact(self):
        import scripts.phase6_6b2_orchestrator as m
        assert m.FROZEN_PROVIDER == "deepseek"
        assert m.FROZEN_MODEL == "deepseek-v4-flash"
        assert m.FROZEN_THINKING_MODE == "disabled"
        assert m.MODEL_LABEL == "DeepSeek-V4-Flash non-thinking"

    @pytest.mark.parametrize("provider,model", [
        ("anthropic", "deepseek-v4-flash"),
        ("deepseek", "deepseek-v4-pro"),
        ("deepseek", "deepseek-chat"),
        ("DeepSeek", "deepseek-v4-flash"),
    ])
    def test_protocol_drift_is_rejected(self, provider, model):
        import scripts.phase6_6b2_orchestrator as m
        with pytest.raises(SystemExit, match="6B2 frozen protocol mismatch"):
            m._validate_frozen_protocol(provider, model)

    def test_valid_protocol_returns_frozen_values(self):
        import scripts.phase6_6b2_orchestrator as m
        assert m._validate_frozen_protocol(
            "deepseek", "deepseek-v4-flash"
        ) == {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "thinking_mode": "disabled",
            "model_label": "DeepSeek-V4-Flash non-thinking",
        }

    def test_environment_cannot_override_frozen_protocol(self, monkeypatch):
        import scripts.phase6_6b2_orchestrator as m
        monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")
        assert m._validate_frozen_protocol(
            "deepseek", "deepseek-v4-flash"
        ) == {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "thinking_mode": "disabled",
            "model_label": "DeepSeek-V4-Flash non-thinking",
        }
```

- [ ] **Step 2: 运行红灯测试**

```powershell
python -m pytest tests/test_phase6_6b2.py::TestFrozenV4FlashProtocol -q --basetemp .tmp/pytest-6b2-task1-red
```

预期：因四个常量与 `_validate_frozen_protocol` 尚不存在而失败。

- [ ] **Step 3: 实现单一事实源与门禁**

在 orchestrator 常量区增加：

```python
FROZEN_PROVIDER = "deepseek"
FROZEN_MODEL = "deepseek-v4-flash"
FROZEN_THINKING_MODE = "disabled"
MODEL_LABEL = "DeepSeek-V4-Flash non-thinking"


def _validate_frozen_protocol(provider, model):
    protocol = {
        "provider": FROZEN_PROVIDER,
        "model": FROZEN_MODEL,
        "thinking_mode": FROZEN_THINKING_MODE,
        "model_label": MODEL_LABEL,
    }
    if provider != FROZEN_PROVIDER or model != FROZEN_MODEL:
        raise SystemExit(
            "6B2 frozen protocol mismatch: "
            f"requested={provider}/{model}, "
            f"required={FROZEN_PROVIDER}/{FROZEN_MODEL}/"
            f"{FROZEN_THINKING_MODE}"
        )
    return protocol
```

让 `run_dev`、`run_reuse`、`run_2023_final` 的第一条有副作用语句之前调用该函数。调用顺序必须是：冻结协议校验 → run_id 校验 → run context 校验/创建 → 目录锁/数据读取/API 调用。

- [ ] **Step 4: 锁定零调用、零产物行为**

新增测试，monkeypatch `OutputDirLock.acquire` 为抛错探针，并传入错误模型；断言只出现 frozen protocol `SystemExit`，且 `tmp_path / "runs"` 不存在。三个公共入口各覆盖一次。

同一步显式更新下列既有入口夹具的 provider/model 为 `deepseek` / `deepseek-v4-flash`，这是冻结门禁引起的必要机械改动：

- `TestRunDirIsolation.test_run_dev_uses_runs_runid_subdir`；
- `TestValidateRunId.test_run_dev_rejects_none_run_id`；
- `TestSmokeOnlyInDev.test_reuse_does_not_run_smoke`；
- `TestSmokeOnlyInDev.test_2023_final_does_not_run_smoke`；
- `TestSmokeOnlyInDev.test_dev_runs_single_smoke`。

不得继续用 `("p", "m")` 或 `("deepseek", "deepseek-chat")` 作为 6B2 公共入口的“任意合法协议”夹具。

- [ ] **Step 5: 运行绿灯测试与原 6B2 入口测试**

```powershell
python -m pytest tests/test_phase6_6b2.py -k "FrozenV4FlashProtocol or ValidateRunId or CLIRunIdParam" -q --basetemp .tmp/pytest-6b2-task1-green
```

预期：全部通过。

- [ ] **Step 6: 提交**

```powershell
git add scripts/phase6_6b2_orchestrator.py tests/test_phase6_6b2.py
git commit -m "feat(6b2): freeze V4 Flash experiment protocol"
```

## Task 2: 为同步 DeepSeek 调用增加显式 non-thinking payload 与响应模型元数据

**Files:**

- Modify: `claude_api.py:136-250`
- Test: `tests/test_claude_api.py:90-126`

- [ ] **Step 1: 写四条 API 契约测试**

扩展测试响应夹具，使响应 JSON 可配置 `model`。新增：

```python
class _JsonResp:
    def __init__(self, response):
        self.response = response
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.response).encode("utf-8")


def _capture_sync_request(monkeypatch, response=None):
    captured = {}
    response = response or {
        "id": "resp-default",
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": "A"},
        }],
    }

    def fake_urlopen(req, timeout=180):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _JsonResp(response)

    monkeypatch.setattr(claude_api.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        claude_api,
        "ANTHROPIC_API_KEY",
        "sk-test-deepseek-key-1234567890",
    )
    return captured


def test_sync_deepseek_explicitly_disables_thinking(monkeypatch):
    captured = _capture_sync_request(
        monkeypatch,
        response={
            "id": "resp-1",
            "model": "deepseek-v4-flash",
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": "A"},
            }],
        },
    )
    text, meta = claude_api.call_model_messages_sync_with_meta(
        [{"role": "user", "content": "只回答A"}],
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_mode="disabled",
        temperature=0.0,
    )
    assert text == "A"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert meta["requested_model"] == "deepseek-v4-flash"
    assert meta["response_model"] == "deepseek-v4-flash"


def test_sync_call_without_thinking_mode_preserves_payload(monkeypatch):
    captured = _capture_sync_request(monkeypatch)
    claude_api.call_model_messages_sync(
        [{"role": "user", "content": "A"}],
        provider="deepseek",
        model="deepseek-v4-pro",
    )
    assert "thinking" not in captured["payload"]


def test_non_deepseek_rejects_thinking_mode_before_network(monkeypatch):
    called = False

    def fail_urlopen(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not be called")

    monkeypatch.setattr(claude_api.urllib.request, "urlopen", fail_urlopen)
    with pytest.raises(ValueError, match="thinking_mode is only supported for deepseek"):
        claude_api.call_model_messages_sync_with_meta(
            [{"role": "user", "content": "A"}],
            provider="anthropic",
            model="claude-test",
            thinking_mode="disabled",
        )
    assert called is False


def test_response_model_is_missing_not_invented(monkeypatch):
    _capture_sync_request(monkeypatch, response={
        "choices": [{"finish_reason": "stop", "message": {"content": "A"}}],
    })
    _, meta = claude_api.call_model_messages_sync_with_meta(
        [{"role": "user", "content": "A"}],
        provider="deepseek",
        model="deepseek-v4-flash",
        thinking_mode="disabled",
    )
    assert meta["requested_model"] == "deepseek-v4-flash"
    assert meta["response_model"] is None
```

`_capture_sync_request` 必须是真实调用 `urllib.request.Request` 的本地 fake，不访问网络；不得直接测试私有 payload 字典而绕开同步入口。

`_JsonResp` 使用独立名称。保留 `tests/test_claude_api.py:91-103` 既有 `_Resp` 及 `test_call_model_messages_sync_sends_temperature` 的硬编码响应契约不变，禁止在文件后部重定义 `_Resp`。

- [ ] **Step 2: 运行红灯测试**

```powershell
python -m pytest tests/test_claude_api.py -k "sync_deepseek_explicitly or without_thinking_mode or non_deepseek_rejects or response_model_is_missing" -q --basetemp .tmp/pytest-6b2-task2-red
```

预期：接口不接受 `thinking_mode`，响应元数据也无 `requested_model`/`response_model`，测试失败。

- [ ] **Step 3: 最小实现，保持默认路径不变**

给两个同步入口都增加尾部可选参数 `thinking_mode=None`，包装入口原样转发。在 `_with_meta` 中、任何网络调用之前加入：

```python
if thinking_mode is not None and provider != "deepseek":
    raise ValueError("thinking_mode is only supported for deepseek")
if provider == "deepseek" and thinking_mode is not None:
    if thinking_mode != "disabled":
        raise ValueError(f"unsupported deepseek thinking_mode: {thinking_mode}")
    payload["thinking"] = {"type": thinking_mode}
```

元数据必须区分请求与响应：

```python
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
```

解析 OpenAI-compatible 响应后只执行 `meta["response_model"] = data.get("model")`。保留既有 `meta["model"]` 作为请求模型兼容字段，禁止用请求值填充 `response_model`。

- [ ] **Step 4: 运行同步 API 全文件测试**

```powershell
python -m pytest tests/test_claude_api.py -q --basetemp .tmp/pytest-6b2-task2-green
```

预期：全部通过，既有 streaming thinking 测试保持原行为。

- [ ] **Step 5: 提交**

```powershell
git add claude_api.py tests/test_claude_api.py
git commit -m "feat(api): support explicit DeepSeek non-thinking calls"
```

## Task 3: 将 thinking mode 沿 runner 调用链传递并拒绝响应模型漂移

**Files:**

- Modify: `benchmark/runners/run_benchmark.py:254-360`
- Modify: `benchmark/runners/run_benchmark.py:386-430`
- Modify: `benchmark/runners/run_benchmark.py:640-690`
- Modify: `benchmark/runners/run_benchmark.py:1748-1898`
- Modify: `tests/phase6_helpers.py:RunnerEnv.run`
- Test: `tests/test_phase6_retry_budget.py`
- Test: `tests/test_phase6_resume.py`

- [ ] **Step 1: 写 runner 传递和模型漂移测试**

给 `RunnerEnv.run()` 增加 `thinking_mode: str | None = None`；仅在非 `None` 时追加 `--thinking-mode`。给 fake meta 默认补 `requested_model`、`response_model=None`、`thinking_mode`，保证非 6B2 测试不被伪造的响应模型阻断。

新增测试：

```python
def test_runner_passes_explicit_thinking_mode(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    seen = []

    def fake_call(messages, provider=None, model=None, system_prompt=None,
                  timeout=180, temperature=None, thinking_mode=None):
        seen.append(thinking_mode)
        return "A", {
            "provider": provider,
            "model": model,
            "requested_model": model,
            "response_model": "deepseek-v4-flash",
            "thinking_mode": thinking_mode,
            "finish_reason": "stop",
        }

    monkeypatch.setattr(
        "claude_api.call_model_messages_sync_with_meta", fake_call
    )
    assert env.run(
        model="deepseek-v4-flash",
        profile="baziqa_xjz_direct",
        thinking_mode="disabled",
    ) == 0
    assert seen == ["disabled"]


def test_response_model_mismatch_is_not_retried(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    calls = 0

    def fake_call(messages, provider=None, model=None, system_prompt=None,
                  timeout=180, temperature=None, thinking_mode=None):
        nonlocal calls
        calls += 1
        return "A", {
            "provider": provider,
            "model": model,
            "requested_model": model,
            "response_model": "deepseek-v4-pro",
            "thinking_mode": thinking_mode,
            "finish_reason": "stop",
        }

    monkeypatch.setattr(
        "claude_api.call_model_messages_sync_with_meta", fake_call
    )
    with pytest.raises(RuntimeError, match="response_model_mismatch"):
        env.run(
            model="deepseek-v4-flash",
            profile="baziqa_xjz_direct",
            thinking_mode="disabled",
        )
    assert calls == 1
    assert env.read_events("call_meta")[0]["response_model"] == "deepseek-v4-pro"
```

再新增缺失响应模型测试：`response_model=None` 时调用成功且 event 保留 `None`。

- [ ] **Step 2: 运行红灯测试**

```powershell
python -m pytest tests/test_phase6_retry_budget.py tests/test_phase6_resume.py -k "thinking_mode or response_model" -q --basetemp .tmp/pytest-6b2-task3-red
```

预期：CLI、Phase6Context 和 event 尚未支持字段，测试失败。

- [ ] **Step 3: 实现 runner 协议传递**

在 runner parser 增加：

```python
parser.add_argument(
    "--thinking-mode",
    choices=("disabled",),
    default=None,
    help="Explicit DeepSeek thinking protocol for controlled experiments",
)
```

给 `Phase6Context.__init__` 增加 `thinking_mode` 并保存。`_call_once_messages()` 调用 `call_model_messages_sync_with_meta` 时传：

```python
thinking_mode=(
    _PHASE6_CTX.thinking_mode if _PHASE6_CTX is not None else None
),
```

在 `_attempt_with_ledger` 得到成功 meta 后：

1. 先 `record_call_meta`；
2. 当 `ctx.thinking_mode == "disabled"` 且 `response_model` 非空、大小写敏感地不等于 `ctx.model` 时，抛出 `RuntimeError(f"response_model_mismatch: {response_model} != {ctx.model}")`；
3. 该异常不得进入网络重试预算。

`record_call_meta()` 与 `enrich_row()` 增加 `requested_model`、`response_model`、`thinking_mode`。在 runner 初始化 `Phase6Context` 的现有调用点增加具名参数 `thinking_mode=args.thinking_mode`。

- [ ] **Step 4: 运行 runner 相关测试**

```powershell
python -m pytest tests/test_phase6_retry_budget.py tests/test_phase6_resume.py -q --basetemp .tmp/pytest-6b2-task3-green
```

预期：全部通过；网络异常仍保留原三次重试预算，截断仍保留独立一次重试，response model mismatch 只调用一次。

- [ ] **Step 5: 提交**

```powershell
git add benchmark/runners/run_benchmark.py tests/phase6_helpers.py tests/test_phase6_retry_budget.py tests/test_phase6_resume.py
git commit -m "feat(runner): audit 6B2 thinking and response model"
```

## Task 4: 将 thinking mode 写入 slice、argv、manifest、status 并保持同源

**Files:**

- Modify: `benchmark/runners/run_benchmark.py:153-232`
- Modify: `scripts/phase6_6b2_orchestrator.py:45-120`
- Modify: `scripts/phase6_6b2_orchestrator.py:188-270`
- Modify: `scripts/phase6_6b2_orchestrator.py:429-500`
- Test: `tests/test_phase6_resume.py:48-138`
- Test: `tests/test_phase6_6b2.py:197-307`
- Test: `tests/test_phase6_6b2.py:949-969`

- [ ] **Step 1: 写 manifest 与同源性红灯测试**

新增或扩展断言：

```python
def test_resume_manifest_records_thinking_mode(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    assert env.run(
        model="deepseek-v4-flash",
        profile="baziqa_xjz_direct",
        thinking_mode="disabled",
    ) == 0
    manifest = json.loads(
        (tmp_path / "detail.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["thinking_mode"] == "disabled"


def test_manifest_rejects_thinking_mode_drift(tmp_path, monkeypatch):
    env = RunnerEnv(tmp_path, monkeypatch, n_cases=1)
    env.model_returns("A")
    env.run(
        model="deepseek-v4-flash",
        profile="baziqa_xjz_direct",
        thinking_mode="disabled",
    )
    path = tmp_path / "detail.manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["thinking_mode"] = "enabled"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit):
        env.run(
            resume=True,
            model="deepseek-v4-flash",
            profile="baziqa_xjz_direct",
            thinking_mode="disabled",
        )
```

在 `TestTask11RunnerCmd` 断言命令包含连续参数 `--thinking-mode disabled`；在 `TestManifestHomology` 解析真实 argv 后，先执行 `reconstructed = _slice_runner_args(slice_info, "deepseek", "deepseek-v4-flash")`，再断言 `build_resume_manifest(argv_namespace, profile) == build_resume_manifest(reconstructed, profile)`。

显式更新 `TestTask11RunnerCmd` 的 5 个手写 slice dict 和 `TestManifestHomology.test_slice_runner_args_reconstructs_namespace` 的 slice dict，统一补：

```python
"thinking_mode": "disabled",
```

这些夹具继续使用其现有 case IDs、路径、caps 和 method；只把 runner command/manifest 调用中的模型值由 `deepseek-chat` 改为 `deepseek-v4-flash`。

- [ ] **Step 2: 运行红灯测试**

```powershell
python -m pytest tests/test_phase6_resume.py tests/test_phase6_6b2.py -k "thinking_mode or RunnerCmd or ManifestHomology" -q --basetemp .tmp/pytest-6b2-task4-red
```

预期：manifest 字段、slice 字段和命令参数缺失而失败。

- [ ] **Step 3: 最小实现**

完成以下同源链：

- `RESUME_MANIFEST_FIELDS` 加 `thinking_mode`；
- `build_resume_manifest()` 写 `getattr(args, "thinking_mode", None)`；
- `_build_schedule()` 与 `_build_smoke_slices()` 每个 slice 写 `thinking_mode=FROZEN_THINKING_MODE`；
- `_build_runner_cmd()` 只读 `slice_info["thinking_mode"]` 并追加 CLI 参数；
- `_slice_runner_args()` 只读同一 slice 字段；
- `slice_status.json` 写 provider、requested_model、thinking_mode；
- `_run_slice()` 从 `details.events.jsonl` 的 `call_meta` 行收集非空 `response_model`；若唯一值存在则在 `slice_status.json` 写该字符串，全部缺失则写 `null`，若出现多个不同值则 fail-closed；
- `_SCHED_HASH_SLICE_KEYS` 加 `thinking_mode`，使协议变化改变 schedule hash。

禁止在 `_build_runner_cmd` 和 `_slice_runner_args` 中分别硬编码 `disabled`。

状态聚合使用以下精确逻辑：

```python
response_models = {
    row.get("response_model")
    for row in _load_events(str(events_path))
    if row.get("kind") == "call_meta" and row.get("response_model")
}
if len(response_models) > 1:
    raise SystemExit(
        f"slice {slice_info['slice_id']} response_model drift: "
        f"{sorted(response_models)}"
    )
response_model = next(iter(response_models), None)
```

`slice_status.json` 写 `"response_model": response_model`。测试分别覆盖唯一值、全部缺失和多个值拒绝。

- [ ] **Step 4: 运行绿灯测试**

```powershell
python -m pytest tests/test_phase6_resume.py tests/test_phase6_6b2.py -k "thinking_mode or RunnerCmd or ManifestHomology or ScheduleHash" -q --basetemp .tmp/pytest-6b2-task4-green
```

预期：全部通过。

- [ ] **Step 5: 提交**

```powershell
git add benchmark/runners/run_benchmark.py scripts/phase6_6b2_orchestrator.py tests/test_phase6_resume.py tests/test_phase6_6b2.py
git commit -m "feat(6b2): bind thinking mode to slice manifests"
```

## Task 5: 原子创建 run context，并只允许显式安全恢复

**Files:**

- Modify: `scripts/phase6_6b2_orchestrator.py:1200-1465`
- Test: `tests/test_phase6_6b2.py:1272-1447`
- Test: `tests/test_phase6_6b2.py:1594-1764`

- [ ] **Step 1: 写 run context 状态机测试**

新增 `TestRunContext`，覆盖：

1. fresh dev 在不存在的 `runs/{run_id}` 原子创建 context；
2. fresh dev 遇到已存在目录时拒绝且不改目录；
3. `--resume` 遇到缺 context 的旧目录时拒绝且不补写；
4. context 任一冻结字段或 code fingerprint 漂移时拒绝；
5. 合法 context + `resume=True` 允许继续未完成 dev；
6. dev receipt 已发布后拒绝 dev 重跑；
7. reuse 必须 `resume=True`、dev receipt 已发布且 reuse receipt 尚未发布；
8. final_2023 必须 `resume=True`、reuse receipt 已发布且 final receipt 尚未发布；
9. context 创建后的拒绝原因追加到 `run_failures.jsonl`；
10. 错误 provider/model 在 context 创建前拒绝且不产生文件。

核心测试使用真实文件系统，不 mock `_prepare_run_context`：

```python
def test_existing_run_without_context_is_rejected_without_migration(tmp_path):
    import scripts.phase6_6b2_orchestrator as m
    runs_root = tmp_path / "runs" / "legacy-v4-pro"
    runs_root.mkdir(parents=True)
    legacy = runs_root / "legacy.events.jsonl"
    legacy.write_text('{"usage":{"reasoning_tokens":12}}\n', encoding="utf-8")
    before = legacy.read_bytes()

    with pytest.raises(SystemExit, match="run_context.json missing"):
        m._prepare_run_context(
            output_dir=tmp_path,
            run_id="legacy-v4-pro",
            stage="dev",
            resume=True,
            protocol=m._validate_frozen_protocol(
                "deepseek", "deepseek-v4-flash"
            ),
            code_fingerprint="a" * 64,
        )

    assert not (runs_root / "run_context.json").exists()
    assert legacy.read_bytes() == before
```

- [ ] **Step 2: 运行红灯测试**

```powershell
python -m pytest tests/test_phase6_6b2.py -k "RunContext" -q --basetemp .tmp/pytest-6b2-task5-red
```

预期：`_prepare_run_context` 与 `--resume` 尚不存在而失败。

- [ ] **Step 3: 实现原子 run context**

复用 orchestrator 现有 `_atomic_write_json(path, data)`（当前位于 `scripts/phase6_6b2_orchestrator.py:981-988`），不得再定义第二个同名函数。只新增必填字段常量：

```python
RUN_CONTEXT_REQUIRED_FIELDS = (
    "provider",
    "model",
    "thinking_mode",
    "model_label",
    "code_fingerprint",
    "created_at",
)
```

`_prepare_run_context(output_dir, run_id, stage, resume, protocol, code_fingerprint)` 必须：

- fresh 仅允许 `stage == "dev"` 且 run 根目录不存在；
- 先执行 `runs_root.parent.mkdir(parents=True, exist_ok=True)`，再用 `os.mkdir(runs_root)` 独占创建 run 根目录，随后调用既有 `_atomic_write_json` 写 context；
- resume 要求根目录和 context 已存在且字段精确一致；
- 不从 events、manifest、目录名推断或补写 context；
- 按阶段检查 gates 下已发布 receipt，拒绝重复执行完成阶段；
- 返回 `runs_root` 与已验证 context。

缺失 context 的报错文案是测试和旧 run 审核命令共同依赖的冻结契约，必须精确实现：

```python
if resume and not context_path.exists():
    raise SystemExit("run_context.json missing: refusing legacy run migration")
```

新增 `_record_run_failure(runs_root, stage, reason)`，以单行 JSON 追加 `run_failures.jsonl`。三个公共入口在 context 成功创建/验证后，用 `except (Exception, SystemExit)` 记录拒绝原因后原样抛出；不得捕获或记录 `KeyboardInterrupt`。

给三个公共入口增加 `resume=False` 参数；CLI 三个子命令统一增加 `--resume`。fresh dev 不传，dev 中断恢复、reuse 和 final_2023 必须显式传入。

- [ ] **Step 4: 更新现有入口测试调用语义**

现有直接调用 `run_reuse`/`run_2023_final` 的测试传 `resume=True`，并通过真实 `_prepare_run_context` helper 创建一致 context。禁止把 `_prepare_run_context` 全局 monkeypatch 成无操作，否则无法覆盖协议链。

`TestRunDirIsolation` 内的 `fake_report` 签名同步增加具名参数 `run_id`，并断言它等于当前 user run ID；不得用无约束的 `**kwargs` 吞掉新契约。

- [ ] **Step 5: 运行 run 状态测试**

```powershell
python -m pytest tests/test_phase6_6b2.py -k "RunContext or RunDirIsolation or ReceiptChain or SmokeOnlyInDev or CLIRunIdParam" -q --basetemp .tmp/pytest-6b2-task5-green
```

预期：全部通过。

- [ ] **Step 6: 提交**

```powershell
git add scripts/phase6_6b2_orchestrator.py tests/test_phase6_6b2.py
git commit -m "feat(6b2): require atomic run context for resume"
```

## Task 6: 将协议绑定到 archive、receipt 与跨阶段 gate

**Files:**

- Modify: `scripts/phase6_6b2_orchestrator.py:881-1090`
- Modify: `scripts/phase6_6b2_sealed_workflow.py:35-130`
- Test: `tests/test_phase6_6b2.py:648-923`
- Test: `tests/test_phase6_6b2.py:1347-1590`
- Test: `tests/test_phase6_6b2.py:1777-1905`

- [ ] **Step 1: 写 audit/receipt 必填与漂移测试**

扩展 `TestTask15SealedWorkflow._make_minimal_receipt` 和 `TestReceiptChain._place_receipt`，使合法夹具总是同时在 audit 与 receipt 写：

```python
"provider": "deepseek",
"model": "deepseek-v4-flash",
"thinking_mode": "disabled",
"model_label": "DeepSeek-V4-Flash non-thinking",
```

两个 helper 的默认 provider/model 同步改为 `deepseek` / `deepseek-v4-flash`。`TestSmokeOnlyInDev._patch_all` 和 `TestRunDirIsolation` 内生成 fake receipt/audit 的代码也补齐 `thinking_mode`、`model_label`，保证它们继续代表合法新协议产物，而不是绕过 gate 的旧格式。

增加参数化负向测试，分别篡改 receipt 或 audit 的 `thinking_mode`、`model_label`；增加跨阶段 dev/reuse thinking mode 不一致测试；增加当前冻结协议与 receipt 不一致测试。

同一步把以下既有 archive 测试调用的 provider/model 机械更新为冻结值：

- `TestTask16GenerateArchive` 的 incomplete、blocked 和 creates-audit 三条路径；
- `TestArchiveMergedFiles.test_archive_produces_merged_files`；
- `TestAtomicArchive` 的成功和失败清理路径；
- `TestSmokeAttemptedInAudit.test_smoke_attempted_in_audit_and_receipt`；
- `TestDash6b2UserRunId.test_user_run_id_persisted_in_archive_audit_and_receipt`。

这些测试不得再向 `generate_archive()` 传 `("p", "m")` 或 `("deepseek", "deepseek-chat")`。测试 fixture 中用于构造 attempt key 的历史 model 字符串不参与入口门禁时可保持原值；只有传入 6B2 公共函数的协议参数必须冻结。

- [ ] **Step 2: 运行红灯测试**

```powershell
python -m pytest tests/test_phase6_6b2.py -k "SealedWorkflow or ReceiptChain or GenerateArchive or AtomicArchive or SmokeAttemptedInAudit" -q --basetemp .tmp/pytest-6b2-task6-red
```

预期：现有 archive/receipt 缺少字段，漂移未被 gate 拒绝，测试失败。

- [ ] **Step 3: 实现 archive 与 receipt 字段**

`generate_archive()` 不接受调用方自由传入 thinking/label；它使用冻结常量，并在入口调用 `_validate_frozen_protocol(provider, model)`。audit 和 receipt 都写 `thinking_mode` 与 `model_label`。

`RECEIPT_REQUIRED_FIELDS` 加入两个字段。`check_stage_gate` 签名增加：

```python
def check_stage_gate(
    stage,
    gate_root="docs/phase6/6b2",
    provider=None,
    model=None,
    thinking_mode=None,
    model_label=None,
    current_code_fingerprint=None,
    expected_user_run_id=None,
):
```

校验顺序：必填字段 → stage/verdict → user_run_id → archive/audit SHA → audit/receipt 全字段交叉 → 当前 protocol → code fingerprint → final_2023 的 dev/reuse 跨阶段一致性。

三个 orchestrator 阶段调用 `check_stage_gate` 时显式传冻结 thinking mode 与 label。

- [ ] **Step 4: 确认 code fingerprint 覆盖新增承重函数**

扩展 `TestCodeFingerprintCriticalCoverage.CRITICAL_FUNCTIONS`，至少包含 `_validate_frozen_protocol`、`_prepare_run_context`、`_record_run_failure`。保留 runner `_code_fingerprint` 与 sealed workflow fail-closed 导入测试。

- [ ] **Step 5: 运行绿灯测试**

```powershell
python -m pytest tests/test_phase6_6b2.py -k "SealedWorkflow or ReceiptChain or GenerateArchive or AtomicArchive or FingerprintCriticalCoverage or SmokeAttemptedInAudit" -q --basetemp .tmp/pytest-6b2-task6-green
```

预期：全部通过。

- [ ] **Step 6: 提交**

```powershell
git add scripts/phase6_6b2_orchestrator.py scripts/phase6_6b2_sealed_workflow.py tests/test_phase6_6b2.py
git commit -m "feat(6b2): seal protocol in receipts and stage gates"
```

## Task 7: 固定报告口径并证明 B1-c 不参与 gate

**Files:**

- Modify: `scripts/phase6_6b2_orchestrator.py:650-770`
- Modify: `scripts/phase6_6b2_orchestrator.py:1244-1415`
- Test: `tests/test_phase6_6b2.py:480-575`
- Test: `tests/test_phase6_6b2.py:970-985`

- [ ] **Step 1: 写报告字段与 gate 隔离测试**

新增：

```python
def test_report_labels_v4_flash_nonthinking(tmp_path):
    import types
    from scripts.phase6_6b2_orchestrator import generate_report

    gate = {"verdict": "PROMOTE_CANDIDATE", "stage": "dev"}
    schedule = {"slices": [], "total_scheduled_calls": 0}
    ledger = types.SimpleNamespace(total_attempted=0, hard_cap=1060)
    report = generate_report(
        gate,
        [],
        schedule,
        ledger,
        {"count": 1, "sha256": "a" * 64},
        str(tmp_path),
        run_id="phase6-6b2-v4flash-nt-20260805-r1",
    )
    assert report["model_protocol"] == "DeepSeek-V4-Flash non-thinking"
    assert report["provider"] == "deepseek"
    assert report["requested_model"] == "deepseek-v4-flash"
    assert report["thinking_mode"] == "disabled"
    assert report["run_id"] == "phase6-6b2-v4flash-nt-20260805-r1"
    assert report["primary_comparison"] == "concurrent b1a_prime vs dual"
    assert report["b1c_advisory"]["gate_inclusion"] is False


def test_b1c_values_cannot_change_gate(tmp_path):
    import inspect
    import types
    from scripts.phase6_6b2_orchestrator import compute_gate, generate_report

    advisory_a = {"count": 1, "sha256": "a" * 64}
    advisory_b = {"count": 9999, "sha256": "b" * 64}
    assert advisory_a != advisory_b
    assert "b1c_advisory" not in inspect.signature(compute_gate).parameters
    gate = {"verdict": "PROMOTE_CANDIDATE", "stage": "dev"}
    schedule = {"slices": [], "total_scheduled_calls": 0}
    ledger = types.SimpleNamespace(total_attempted=0, hard_cap=1060)
    report_a = generate_report(
        gate,
        [],
        schedule,
        ledger,
        advisory_a,
        str(tmp_path / "report-a"),
        run_id="r-a",
    )
    report_b = generate_report(
        gate,
        [],
        schedule,
        ledger,
        advisory_b,
        str(tmp_path / "report-b"),
        run_id="r-b",
    )
    assert report_a["gate"] == report_b["gate"] == gate
```

第二条测试必须直接证明 `compute_gate` 的函数签名和输入不包含 advisory；不得通过 mock `compute_gate` 得出结论。

- [ ] **Step 2: 运行红灯测试**

```powershell
python -m pytest tests/test_phase6_6b2.py -k "report_labels_v4 or b1c_values_cannot_change_gate or B1CAdvisory or ComputeGate" -q --basetemp .tmp/pytest-6b2-task7-red
```

预期：报告缺固定协议字段而失败；既有 gate 测试继续通过。

- [ ] **Step 3: 实现报告契约**

给 `generate_report` 增加 `run_id` 参数，并从冻结常量写顶层字段：

```python
"model_protocol": MODEL_LABEL,
"provider": FROZEN_PROVIDER,
"requested_model": FROZEN_MODEL,
"thinking_mode": FROZEN_THINKING_MODE,
"run_id": run_id,
"primary_comparison": "concurrent b1a_prime vs dual",
```

`b1c_advisory` 写：

```python
"gate_inclusion": False,
"note": "historical deepseek-chat advisory only; excluded from all gates",
```

Markdown 报告逐行显示同样口径。三个阶段都把当前 `run_id` 作为 `generate_report` 的具名参数传入。不得改 `compute_gate` 签名或把 advisory 传入 gate。

- [ ] **Step 4: 运行绿灯测试**

```powershell
python -m pytest tests/test_phase6_6b2.py -k "report or B1CAdvisory or ComputeGate" -q --basetemp .tmp/pytest-6b2-task7-green
```

预期：全部通过。

- [ ] **Step 5: 提交**

```powershell
git add scripts/phase6_6b2_orchestrator.py tests/test_phase6_6b2.py
git commit -m "docs(6b2): label V4 Flash non-thinking evidence"
```

## Task 8: 用 fake runner 闭合 dev → reuse → final_2023 协议链

**Files:**

- Modify: `tests/test_phase6_6b2.py:1272-1764`
- Modify: `scripts/phase6_6b2_orchestrator.py:1244-1465` only if integration test exposes a production defect
- Modify: `scripts/phase6_6b2_sealed_workflow.py:60-130` only if integration test exposes a production defect

- [ ] **Step 1: 写完整链路集成测试**

新增 `TestV4FlashNonThinkingChain`，使用 40 题临时 JSONL、fake subprocess runner 和真实文件落盘。fake runner 必须解析 `_build_runner_cmd` 的 argv，并生成与真实 runner 同名的 detail/events/manifest/status；禁止直接 mock `generate_archive`、`check_stage_gate` 或 `_prepare_run_context`。

先在 `tests/test_phase6_6b2.py` 增加以下可执行骨架；`_run_slice` 仍负责写 `slice_status.json`，fake subprocess 只复刻 runner 负责的 detail/events/manifest 三件套：

```python
def _cmd_value(cmd, name, default=None):
    if name not in cmd:
        return default
    return cmd[cmd.index(name) + 1]


def _write_6b2_dataset(path, year):
    rows = [
        {
            "case_id": f"{year}-Q{i:02d}",
            "question": f"case {i}",
            "options": ["A. one", "B. two", "C. three", "D. four"],
            "answer": "A",
        }
        for i in range(40)
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _fake_runner_subprocess(cmd, capture_output, text, timeout, cwd):
    from types import SimpleNamespace
    from benchmark.runners.profiles import resolve_profile
    from benchmark.runners.run_benchmark import build_resume_manifest

    detail_path = Path(_cmd_value(cmd, "--case-details-jsonl"))
    events_path = Path(str(detail_path).replace(".jsonl", ".events.jsonl"))
    manifest_path = Path(str(detail_path).replace(".jsonl", ".manifest.json"))
    case_ids = json.loads(
        Path(_cmd_value(cmd, "--case-ids-file")).read_text(encoding="utf-8")
    )
    dataset_path = _cmd_value(cmd, "--dataset")
    dataset_id = Path(dataset_path).stem
    arm = _cmd_value(cmd, "--arm")
    requested_model = _cmd_value(cmd, "--model")
    provider = _cmd_value(cmd, "--provider")
    thinking_mode = _cmd_value(cmd, "--thinking-mode")
    repeat_idx = int(_cmd_value(cmd, "--repeat-idx"))
    profile_id = _cmd_value(cmd, "--profile")
    chart_schema = _cmd_value(cmd, "--chart-schema-version")
    profile = resolve_profile(profile_id, chart_schema)
    detail_rows = []
    event_rows = []

    for case_id in case_ids:
        case_index = int(case_id.rsplit("Q", 1)[1])
        if arm == "b1a_prime":
            stages = ("main",)
            predicted = "A" if case_index < 13 else "B"
        else:
            stages = ("bazi", "ziwei")
            predicted = "A" if case_index < 15 else "B"
        for stage in stages:
            attempt_key = [
                dataset_id,
                profile_id,
                arm,
                stage,
                provider,
                requested_model,
                case_id,
                repeat_idx,
                0,
                "p0",
            ]
            detail_rows.append({
                "attempt_key": attempt_key,
                "case_id": case_id,
                "expected_answer": "A",
                "predicted_answer": predicted,
                "correct": predicted == "A",
                "terminal_state": "parsed",
            })
            event_rows.extend((
                {"kind": "call_attempt", "attempt_key": attempt_key},
                {
                    "kind": "call_meta",
                    "attempt_key": attempt_key,
                    "provider": provider,
                    "requested_model": requested_model,
                    "response_model": "deepseek-v4-flash",
                    "thinking_mode": thinking_mode,
                    "finish_reason": "stop",
                },
            ))

    detail_path.parent.mkdir(parents=True, exist_ok=True)
    detail_path.write_text(
        "".join(json.dumps(row) + "\n" for row in detail_rows),
        encoding="utf-8",
    )
    events_path.write_text(
        "".join(json.dumps(row) + "\n" for row in event_rows),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        dataset=dataset_path,
        case_ids_file=_cmd_value(cmd, "--case-ids-file"),
        arm=arm,
        ziwei_arm=_cmd_value(cmd, "--ziwei-arm"),
        attempt_stage=_cmd_value(cmd, "--attempt-stage"),
        repeat_idx=repeat_idx,
        provider=provider,
        model=requested_model,
        thinking_mode=thinking_mode,
        temperature=float(_cmd_value(cmd, "--temperature")),
        sample_temperature=0.4,
        n_samples=1,
        aggregate="majority",
        method=_cmd_value(cmd, "--method"),
        scheduled_calls=int(_cmd_value(cmd, "--scheduled-calls")),
        hard_cap=int(_cmd_value(cmd, "--hard-cap")),
        as_of_date=_cmd_value(cmd, "--as-of-date"),
    )
    manifest_path.write_text(
        json.dumps(build_resume_manifest(args, profile)),
        encoding="utf-8",
    )
    return SimpleNamespace(returncode=0, stdout="", stderr="")
```

测试 monkeypatch `scripts.phase6_6b2_orchestrator.subprocess.run` 为该函数。四件套中的 status 必须由真实 `_run_slice` 根据 fake 三件套生成并接受完整性检查，不能由 fake 直接伪造。

测试为 2021-2025 分别创建 `tmp_path / f"baziqa_contest8_{year}_holdout_enriched.jsonl"`，逐个调用 `_write_6b2_dataset`，确保 `_year_from_dataset_id()` 仍走真实命名契约。2023 的 `verify_2023_raw_data`、`enrich_year` 和 lock 写入只替换为确定性的本地 fixture；schedule、gate、archive、receipt 和 run context 保持真实实现。

测试顺序：

1. 用冻结 provider/model、临时 output 目录、固定测试 run ID 调用 `run_dev`，并传 `resume=False`；
2. 断言 context、slice manifest、event、audit、receipt、report 全部是冻结协议；
3. 用 dev receipt 的精确路径调用 `run_reuse`，并传 `resume=True`；
4. 断言 dev receipt 通过真实 gate 且 reuse receipt 同协议；
5. monkeypatch 2023 数据 SHA/enrichment 为本地 deterministic fixture；
6. 用 reuse receipt 的精确路径调用 `run_2023_final`，并传 `resume=True`；
7. 断言 final receipt 与 dev/reuse 同协议；
8. 全链 fake API 调用数符合现有预算夹具，不访问网络。

- [ ] **Step 2: 写三条链路负向测试**

- dev receipt thinking mode 篡改后 reuse 零调用拒绝；
- reuse receipt model label 篡改后 final_2023 在读取密封数据前拒绝；
- fake API 返回 `DeepSeek-V4-Flash` 时 dev smoke 被阻断，正式 slice 未启动。

第三条必须断言大小写敏感，不接受展示名作为响应模型标识。

第三条使用独立 fake subprocess：第一次 smoke 调用返回 `returncode=1`、`stderr="response_model_mismatch: DeepSeek-V4-Flash != deepseek-v4-flash"`，同时记录调用命令；断言调用列表长度为 1，且该命令的 output-dir 含 `smoke_`，证明未进入正式 slice。response-model 单调用行为本身仍由 Task 3 的真实 runner 单元测试证明。

- [ ] **Step 3: 运行红灯测试**

```powershell
python -m pytest tests/test_phase6_6b2.py -k "V4FlashNonThinkingChain" -q --basetemp .tmp/pytest-6b2-task8-red
```

预期：首次运行暴露仍未贯通的字段或 fixture 契约；不得通过放宽断言解决。

- [ ] **Step 4: 只修复集成测试证明的生产缺口**

每次只改导致当前红灯的最小生产路径，重复运行同一测试，直到完整链和三条负向链全部通过。不要重构预算、smoke 或 gate 计算。

- [ ] **Step 5: 运行完整 6B2 文件**

```powershell
python -m pytest tests/test_phase6_6b2.py -q --basetemp .tmp/pytest-6b2-task8-green
```

预期：全部通过。

- [ ] **Step 6: 提交**

```powershell
git add scripts/phase6_6b2_orchestrator.py scripts/phase6_6b2_sealed_workflow.py tests/test_phase6_6b2.py
git commit -m "test(6b2): close V4 Flash protocol chain"
```

## Task 9: 旧 V4-Pro run 拒收、回归验收与真实 smoke 前置闸

**Files:**

- Verify only: `docs/phase6/6b2/runs/phase6-6b2-final-2023/`
- Verify: all files modified in Tasks 1-8

- [ ] **Step 1: 非破坏性核验旧 run 保持原状**

先记录旧目录文件清单和 SHA：

```powershell
$legacy = 'docs/phase6/6b2/runs/phase6-6b2-final-2023'
Get-ChildItem $legacy -Recurse -File | Sort-Object FullName | Get-FileHash -Algorithm SHA256 | ConvertTo-Json -Depth 3 | Set-Content .tmp/6b2-legacy-v4pro-before.json
```

调用 `_prepare_run_context`，参数使用该旧 run_id、`stage="dev"`、`resume=True`、冻结 protocol 和当前 code fingerprint；预期 `run_context.json missing`，且不得创建 context。随后再生成 after hash 并比较：

```powershell
@'
from scripts.phase6_6b2_orchestrator import (
    _compute_experiment_code_fingerprint,
    _prepare_run_context,
    _validate_frozen_protocol,
)

try:
    _prepare_run_context(
        output_dir="docs/phase6/6b2",
        run_id="phase6-6b2-final-2023",
        stage="dev",
        resume=True,
        protocol=_validate_frozen_protocol(
            "deepseek", "deepseek-v4-flash"
        ),
        code_fingerprint=_compute_experiment_code_fingerprint(),
    )
except SystemExit as exc:
    if "run_context.json missing" not in str(exc):
        raise
else:
    raise SystemExit("legacy V4-Pro run was incorrectly accepted")
'@ | python -
```

再生成 after hash 并比较：

```powershell
Get-ChildItem $legacy -Recurse -File | Sort-Object FullName | Get-FileHash -Algorithm SHA256 | ConvertTo-Json -Depth 3 | Set-Content .tmp/6b2-legacy-v4pro-after.json
Compare-Object (Get-Content .tmp/6b2-legacy-v4pro-before.json) (Get-Content .tmp/6b2-legacy-v4pro-after.json)
```

预期：无差异；旧 run 只保留审计，不进入新证据链。

- [ ] **Step 2: 运行 6B2 定向回归**

```powershell
python -m pytest tests/test_claude_api.py tests/test_phase6_retry_budget.py tests/test_phase6_resume.py tests/test_phase6_6b2.py tests/test_phase6_profiles.py tests/test_dual_system_reasoning.py -q --basetemp .tmp/pytest-6b2-final-targeted
```

预期：全部通过，不访问网络。

- [ ] **Step 3: 运行 Phase 6 广泛回归**

```powershell
$files = (Get-ChildItem tests -Filter 'test_phase6_*.py').FullName
python -m pytest $files tests/test_dual_system_reasoning.py tests/test_claude_api.py -q --basetemp .tmp/pytest-6b2-final-phase6
```

预期：无新增失败。若既有 6B1D `WinError 5` 仍出现，单独记录该失败及 `657 passed, 1 failed` 基线对照；不得写“全绿”。若它在正常权限环境通过，则记录新的完整通过数。

- [ ] **Step 4: 编译与 CLI 契约检查**

```powershell
python -m py_compile claude_api.py benchmark/runners/run_benchmark.py scripts/phase6_6b2_orchestrator.py scripts/phase6_6b2_sealed_workflow.py
python scripts/phase6_6b2_orchestrator.py run_dev --help
```

确认 help 显示 `--resume`；orchestrator 不暴露自由 `--thinking-mode`；runner help 显示内部 `--thinking-mode {disabled}`：

```powershell
python -m benchmark.runners.run_benchmark --help
```

- [ ] **Step 5: 确认 Git 范围**

```powershell
git status --short
git diff --check
git diff -- claude_api.py benchmark/runners/run_benchmark.py scripts/phase6_6b2_orchestrator.py scripts/phase6_6b2_sealed_workflow.py tests/test_claude_api.py tests/phase6_helpers.py tests/test_phase6_resume.py tests/test_phase6_retry_budget.py tests/test_phase6_6b2.py
```

只允许本计划列出的文件出现实施 diff；保留用户原有无关改动，不暂存它们。

- [ ] **Step 6: 提交最终验收修正**

仅当 Task 9 产生必要修正时提交：

```powershell
git add claude_api.py benchmark/runners/run_benchmark.py scripts/phase6_6b2_orchestrator.py scripts/phase6_6b2_sealed_workflow.py tests/test_claude_api.py tests/phase6_helpers.py tests/test_phase6_resume.py tests/test_phase6_retry_budget.py tests/test_phase6_6b2.py
git commit -m "fix(6b2): close V4 Flash smoke preconditions"
```

- [ ] **Step 7: 停在真实 API 调用之前，输出准入报告**

准入报告必须逐项确认：

- 冻结协议门禁通过；
- fake API payload 实测含 `thinking.type=disabled`；
- response model mismatch 会阻断 smoke；
- fresh/resume/完成阶段状态机通过；
- manifest/context/audit/receipt/report 字段一致；
- 旧 V4-Pro run 未变化且被拒收；
- B1-c 不参与 gate；
- 定向回归通过；
- 广泛回归无新增失败；
- 实施代码、设计与计划均已进入 Git。

未获得用户明确批准前，不启动真实 smoke。

- [ ] **Step 8: 获批后使用全新 run_id 启动 dev smoke**

固定命令：

```powershell
python scripts/phase6_6b2_orchestrator.py run_dev --provider deepseek --model deepseek-v4-flash --output-dir docs/phase6/6b2 --run-id phase6-6b2-v4flash-nt-20260805-r1
```

该 run_id 从未被 V4-Pro、其他模型或其他 thinking mode 使用。若命令中断，只能用同一协议显式恢复：

```powershell
python scripts/phase6_6b2_orchestrator.py run_dev --provider deepseek --model deepseek-v4-flash --output-dir docs/phase6/6b2 --run-id phase6-6b2-v4flash-nt-20260805-r1 --resume
```

不得续跑 `phase6-6b2-final-2023`，不得删除旧 manifest 来强行恢复，不得用 `deepseek-v4-pro` 或 `deepseek-chat` 替代。

## 完成定义

实现只有在以下条件全部满足时才算完成：

- 四个冻结常量是 orchestrator 的唯一 6B2 协议源；
- 仅显式 6B2 同步调用发送 non-thinking payload，其他调用行为不变；
- requested model 与 response model 分字段审计；
- response model 明确漂移时单次失败且阻断 smoke；
- manifest、slice status、events、run context、audit、receipt、report 全链字段一致；
- fresh run、显式 resume、完成阶段拒绝、旧目录拒收都有真实文件测试；
- dev → reuse → final_2023 fake 链通过；
- B1-c 只作历史 advisory；
- 6B2 定向回归全部通过，Phase 6 广泛回归无新增失败；
- 真实 smoke 在单独批准前保持未启动。
