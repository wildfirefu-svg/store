# Agent 工作流增强实施计划（Harness 五维优化）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按设计 v2 终稿落地 quality-gate Skill、3 条 Rules、2 个 Hook 脚本与注册、3 个 Custom Agents、AGENTS.md §14 Memory 运营行。

**Architecture:** 全部为 `.qoder/` 面的声明式资产 + 两个纯标准库 Python Hook 脚本；Hook 脚本走 TDD（stdin JSON → exit code/stderr 断言）；声明式资产用轻量结构测试守护（frontmatter 字段、禁改清单单一事实源一致性）；新增 Skill 同步 `.reasonix/skills/` 镜像。

**Tech Stack:** Python 3.11 标准库、pytest、Markdown frontmatter、Qoder settings JSON。

**Spec:** `docs/superpowers/specs/2026-08-07-agent-workflow-enhancement-design.md`（v2 终稿，7 条变更记录）

**关键平台事实（写死，执行时不得偏离）：**

- Qoder Hook 工具名：`Write`、`Edit`、`Bash`；阻断协议为 `exit 2` + **stderr** 原因；`exit 0` + stdout deny JSON 是另一套协议，本计划不使用。
- `scripts/affected_tests.py --run` 命中 `full_suite` 时立即启动全量 pytest（无确认点），因此 quality-gate 第 3 段必须先干跑再批准。
- Qoder Rules 平台优先级高于 AGENTS.md：规则只可复述 AGENTS.md，不可放宽。
- `.qoder/settings.json` 当前仓库不存在：实施时新建，回退时删除（见 spec §7）。
- Hook 保护范围承诺：阻止直接文件工具（Write/Edit）和**显式** Bash 命令触碰禁改文件；动态拼接路径不覆盖。
- Windows PowerShell 环境：语句分隔用 `;` 不用 `&&`；Python 解释器统一用 `.venv\Scripts\python.exe`。

---

## 文件结构

**Create：**

| 路径 | 职责 |
|---|---|
| `.qoder/skills/quality-gate/SKILL.md` | 一键门禁链 Skill（权威面） |
| `.reasonix/skills/quality-gate.md` | 上述 Skill 的字节级镜像 |
| `.qoder/rules/core-boundary.md` | Always Apply：核心边界 + 禁改清单 + §9 入口表复述 |
| `.qoder/rules/scripts-safety.md` | Specific Files `scripts/**`：脚本域安全约束 |
| `.qoder/rules/benchmark-conventions.md` | Specific Files `benchmark/**`：benchmark 模块约定 |
| `.qoder/hooks/guard_data_artifacts.py` | PreToolUse 硬拦截（Write/Edit/Bash） |
| `.qoder/hooks/remind_affected_tests.py` | PostToolUse 提示（Write/Edit） |
| `.qoder/settings.json` | Hook 注册（新建） |
| `.qoder/agents/bench-runner.md` | 评测执行代理（Read, Bash） |
| `.qoder/agents/core-guard.md` | 核心变更审查代理（只读：Read, Grep, Glob） |
| `.qoder/agents/rag-debugger.md` | RAG 诊断代理（Read, Bash, Grep） |
| `tests/harness_asset_helpers.py` | 测试共用 frontmatter 解析辅助 |
| `tests/test_qoder_workflow_assets.py` | Rules/Skill/settings/agents/AGENTS.md 行结构守护测试 |
| `tests/test_qoder_hooks.py` | Hook 脚本行为测试 |

**Modify：** `AGENTS.md`（§14 追加一行）

**不改：** 既有 4 个 Skill、核心代码、CI 配置、`scripts/affected_tests.py`。

---

### Task 1: quality-gate Skill + 镜像同步

**Files:**
- Create: `.qoder/skills/quality-gate/SKILL.md`
- Create: `.reasonix/skills/quality-gate.md`（字节级镜像）

- [ ] **Step 1: 写 SKILL.md（权威面）**

`.qoder/skills/quality-gate/SKILL.md`：

```markdown
---
name: quality-gate
description: 一键运行完整提交前门禁链（ruff → mypy → affected_tests → smoke）
trigger: 用户要求运行完整门禁、提交前检查、或需要一次性验证所有静态检查与聚焦测试时使用；单文件快速迭代优先用 test-suite skill
output: 门禁链逐段结果（每段 pass/fail + 关键输出），任一失败即停止并给出失败段的具体信息与修复方向
validation: 四段命令退出码均为 0；失败时输出具体失败项（lint 规则号 / 类型错误 / 断言信息），不输出笼统报错
---
# Quality Gate Skill — 玄机子

依次运行完整提交前门禁链，任一段失败即停止并报告。与 CI `test` 作业及 `.pre-commit-config.yaml` 对齐。

## Steps

1. Lint：`ruff check .`（基线 E9/F821，配置见 `ruff.toml`）。失败时输出具体规则号与文件位置。
2. Type check：`mypy`（增量白名单，配置见 `mypy.ini`）。失败时输出具体类型错误。
3. 受影响测试（两阶段流程，不得直接 `--run`）：
   1. 干跑：`python scripts/affected_tests.py`，只读测试映射。
   2. 若 stdout 含 `FULL_SUITE`：告知触发原因（tests/ 或 pytest.ini / requirements*.txt 变更）与预计范围（全量套件），等待用户明确批准；批准后执行 `python scripts/affected_tests.py --run`。无人值守或用户未回复：停在本段，不得默认为批准。
   3. 否则：直接执行 `python scripts/affected_tests.py --run`。
4. Smoke：`python scripts/verify_smoke.py`。

## 边界

- 与 test-suite skill 的分工：test-suite 按变更面选择测试范围；quality-gate 负责完整静态 + 动态门禁链。
- 不跳过任何段；不为"看起来对"省略第 3 段的用户批准。
```

- [ ] **Step 2: 复制镜像并验证字节级一致**

```powershell
Copy-Item ".qoder\skills\quality-gate\SKILL.md" ".reasonix\skills\quality-gate.md"
.venv\Scripts\python.exe scripts\verify_skill_sync.py
```

Expected: `skill sync check OK: 5 skill(s) identical on both surfaces`，exit 0。

- [ ] **Step 3: Commit**

```powershell
git add .qoder/skills/quality-gate/SKILL.md .reasonix/skills/quality-gate.md
git commit -m "feat(skills): add quality-gate skill for full pre-commit gate chain"
```

---

### Task 2: 结构守护测试 + 3 条 Rules

**Files:**
- Create: `tests/harness_asset_helpers.py`
- Create: `tests/test_qoder_workflow_assets.py`
- Create: `.qoder/rules/core-boundary.md`、`.qoder/rules/scripts-safety.md`、`.qoder/rules/benchmark-conventions.md`

- [ ] **Step 1: 写共用辅助 `tests/harness_asset_helpers.py`**

```python
"""Shared helpers for structural tests of .qoder agent assets."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_frontmatter(path: Path) -> dict:
    """Parse simple one-level `key: value` YAML frontmatter (no nesting)."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"missing frontmatter in {path}"
    end = text.index("---", 3)
    fields: dict = {}
    for line in text[3:end].splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields
```

- [ ] **Step 2: 写失败测试 `tests/test_qoder_workflow_assets.py`**

```python
"""Structural guards for .qoder workflow assets (design 2026-08-07 v2)."""
import json

from tests.harness_asset_helpers import PROJECT_ROOT, parse_frontmatter

RULES = ["core-boundary.md", "scripts-safety.md", "benchmark-conventions.md"]


def test_rules_exist_with_type_and_consistency_clause():
    for name in RULES:
        path = PROJECT_ROOT / ".qoder" / "rules" / name
        assert path.is_file(), f"missing rule: {name}"
        fm = parse_frontmatter(path)
        assert fm.get("type") in {"always_apply", "specific_files"}, name
        body = path.read_text(encoding="utf-8")
        assert "不引入新豁免" in body, f"{name} 缺少一致性声明"


def test_core_boundary_selects_entry_not_mandatory_all():
    body = (PROJECT_ROOT / ".qoder" / "rules" / "core-boundary.md").read_text(
        encoding="utf-8"
    )
    assert "按要验证的声明选择对应验证入口" in body
    assert "必跑" not in body, "Rules 优先级高于 AGENTS.md，不得新增全局必跑约束"


def test_quality_gate_skill_structure():
    fm = parse_frontmatter(
        PROJECT_ROOT / ".qoder" / "skills" / "quality-gate" / "SKILL.md"
    )
    for key in ("name", "description", "trigger", "output", "validation"):
        assert fm.get(key), key
    mirror = PROJECT_ROOT / ".reasonix" / "skills" / "quality-gate.md"
    source = PROJECT_ROOT / ".qoder" / "skills" / "quality-gate" / "SKILL.md"
    assert mirror.read_bytes() == source.read_bytes(), "mirror drift"


def test_hook_settings_shape():
    settings = json.loads(
        (PROJECT_ROOT / ".qoder" / "settings.json").read_text(encoding="utf-8")
    )
    hooks = settings["hooks"]
    pre = hooks["PreToolUse"]
    post = hooks["PostToolUse"]
    assert pre[0]["matcher"] == "Write|Edit|Bash"
    assert post[0]["matcher"] == "Write|Edit"
    for entry in pre + post:
        for hook in entry["hooks"]:
            assert hook["type"] == "command"
            assert hook["command"].endswith(".py")


def test_agents_frontmatter_and_tool_scope():
    expected = {
        "bench-runner.md": {"Read", "Bash"},
        "core-guard.md": {"Read", "Grep", "Glob"},
        "rag-debugger.md": {"Read", "Bash", "Grep"},
    }
    for name, tools in expected.items():
        fm = parse_frontmatter(PROJECT_ROOT / ".qoder" / "agents" / name)
        assert fm.get("name") == name[:-3]
        assert fm.get("description"), name
        got = {t.strip() for t in fm["tools"].split(",")}
        assert got == tools, f"{name}: {got}"
        if name == "core-guard.md":
            assert "Write" not in got and "Edit" not in got


def test_forbidden_patterns_single_source_of_truth():
    """Hook 脚本清单必须与 core-boundary 规则一致（AGENTS.md §4 复述）。"""
    script = (PROJECT_ROOT / ".qoder" / "hooks" / "guard_data_artifacts.py").read_text(
        encoding="utf-8"
    )
    rule = (PROJECT_ROOT / ".qoder" / "rules" / "core-boundary.md").read_text(
        encoding="utf-8"
    )
    for pattern in (
        "knowledge-base/*.json",
        "tests/case_db.json",
        "data/*.json",
        "benchmark/datasets/*.jsonl",
    ):
        assert pattern in script, f"hook 缺模式: {pattern}"
        assert pattern in rule, f"规则缺模式: {pattern}"


def test_agents_md_memory_operation_line():
    body = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "总是用 UpdateMemory 沉淀经验" in body
```

- [ ] **Step 3: 运行测试确认失败**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_workflow_assets.py -q
```

Expected: FAIL（规则/脚本/settings/agents 文件均不存在，多个断言报 missing）。

- [ ] **Step 4: 写 `.qoder/rules/core-boundary.md`**

```markdown
---
name: core-boundary
type: always_apply
description: 玄机子核心代码边界、禁改数据产物与验证入口选择规则
---

本规则复述 AGENTS.md §4 / §9 的约束，不引入新豁免。规则与 AGENTS.md 不一致时，以删除或修正本规则为准，不得放宽 AGENTS.md。

## 核心代码边界

`bazi_calculator.py` 是排盘核心引擎，`scripts/` 含验证与门禁脚本；两者变更受核心代码边界约束，动手前先读对应文件与调用方。

## 禁改清单（被跟踪的数据产物，与 AGENTS.md §4 同步）

- `knowledge-base/*.json`
- `tests/case_db.json`
- `data/*.json`
- `benchmark/datasets/*.jsonl`

## 验证入口选择（与 AGENTS.md §9 入口表同步）

改动后按要验证的声明选择对应验证入口，不要求每次改动运行全部脚本：

| 要验证的声明 | 入口 |
|---|---|
| focused smoke tests passed | `python scripts/verify_smoke.py` |
| CI workflow configuration | `python scripts/verify_ci.py` |
| runtime behavior | `python scripts/verify_runtime.py` |
| 变更范围的最小测试集 | `python scripts/affected_tests.py`（先干跑；FULL_SUITE 需用户批准后再 `--run`） |
```

- [ ] **Step 5: 写 `.qoder/rules/scripts-safety.md`**

```markdown
---
name: scripts-safety
type: specific_files
globs: scripts/**
description: scripts/ 目录的安全与契约约束
---

本规则复述并细化 AGENTS.md 对 `scripts/` 的约束，不引入新豁免。

- 门禁与验证脚本（verify_smoke / verify_ci / verify_runtime / affected_tests）只增能力，不破坏既有 CLI 契约与退出码语义。
- 运行评测/编排脚本（phase6_*、run_*）前先确认预算参数（题集、repeat、模型）；不确定就先干跑或问。
- 实验指纹范围文件（_CODE_SCOPE 等）缺失时必须 fail-closed 抛异常终止，不得静默降级。
- `scripts/` 下的运行产物（日志、中间 JSON）不进 git 跟踪。
```

- [ ] **Step 6: 写 `.qoder/rules/benchmark-conventions.md`**

```markdown
---
name: benchmark-conventions
type: specific_files
globs: benchmark/**
description: benchmark/ 模块职责边界与运行产物约束
---

本规则复述并细化 AGENTS.md 对 `benchmark/` 的约束，不引入新豁免。

- 模块职责：`runners/` 负责执行与 resume/ledger，`formatters/` 负责输入构造，`scorers/` 负责评分；改动跨模块时先读各模块既有入口。
- resume/ledger 子系统入口在 `benchmark/runners/resume_ledger.py`；断点恢复逻辑不得绕过 ledger 直写。
- `benchmark/outputs/` 是运行产物目录，不得手改其中文件；评测结论以 report/gate 产物为证。
- `benchmark/datasets/*.jsonl` 是被跟踪的数据产物，禁改（与 AGENTS.md §4 同步）。
```

- [ ] **Step 7: 只跑 rules 相关测试确认转绿（其余任务的文件尚不存在，仍会红）**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_workflow_assets.py::test_rules_exist_with_type_and_consistency_clause tests\test_qoder_workflow_assets.py::test_core_boundary_selects_entry_not_mandatory_all -q
```

Expected: 2 passed。

- [ ] **Step 8: Commit**

```powershell
git add tests/harness_asset_helpers.py tests/test_qoder_workflow_assets.py .qoder/rules/
git commit -m "feat(rules): add three boundary rules with consistency guards"
```

---

### Task 3: guard_data_artifacts.py（TDD）

**Files:**
- Create: `tests/test_qoder_hooks.py`
- Create: `.qoder/hooks/guard_data_artifacts.py`

- [ ] **Step 1: 写失败测试 `tests/test_qoder_hooks.py`**

```python
"""Behavior tests for .qoder/hooks guard scripts (design 2026-08-07 v2).

Protocol under test: block == exit 2 + reason on stderr; allow == exit 0.
"""
import json
import subprocess
import sys

from tests.harness_asset_helpers import PROJECT_ROOT

GUARD = PROJECT_ROOT / ".qoder" / "hooks" / "guard_data_artifacts.py"
REMIND = PROJECT_ROOT / ".qoder" / "hooks" / "remind_affected_tests.py"


def run_hook(script, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )


def write_payload(path):
    return {"tool_name": "Write", "tool_input": {"file_path": path}}


def bash_payload(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def test_guard_write_forbidden_json_denied():
    proc = run_hook(GUARD, write_payload("knowledge-base/ziping.md.json"))
    assert proc.returncode == 2
    assert "禁改" in proc.stderr.decode("utf-8")


def test_guard_write_forbidden_dataset_denied():
    proc = run_hook(GUARD, write_payload("benchmark/datasets/mingli_bench.jsonl"))
    assert proc.returncode == 2


def test_guard_edit_forbidden_data_denied():
    proc = run_hook(
        GUARD, {"tool_name": "Edit", "tool_input": {"file_path": "data/charts/1.json"}}
    )
    assert proc.returncode == 2


def test_guard_write_allowed_file_passes():
    proc = run_hook(GUARD, write_payload("api_server.py"))
    assert proc.returncode == 0


def test_guard_write_unrelated_json_passes():
    proc = run_hook(GUARD, write_payload("docs/notes.json"))
    assert proc.returncode == 0


def test_guard_bash_explicit_delete_denied():
    proc = run_hook(
        GUARD, bash_payload("Remove-Item knowledge-base/ziping.md.json")
    )
    assert proc.returncode == 2
    assert "禁改" in proc.stderr.decode("utf-8")


def test_guard_bash_redirect_write_denied():
    proc = run_hook(GUARD, bash_payload("echo [] > data/cases_real_db.json"))
    assert proc.returncode == 2


def test_guard_bash_read_only_passes():
    proc = run_hook(GUARD, bash_payload("cat knowledge-base/ziping.md.json"))
    assert proc.returncode == 0


def test_guard_bash_dynamic_path_is_known_gap_passes():
    # 动态拼接路径不在保护承诺内（spec §4.3 如实表述），当前放行。
    proc = run_hook(GUARD, bash_payload('Remove-Item "$KB_DIR/$NAME.json"'))
    assert proc.returncode == 0


def test_guard_unknown_tool_passes():
    proc = run_hook(GUARD, {"tool_name": "Read", "tool_input": {}})
    assert proc.returncode == 0


def test_guard_malformed_json_passes_open():
    # fail-open：stdin 不是合法 JSON 时放行（守护脚本不得阻塞会话）。
    proc = subprocess.run(
        [sys.executable, str(GUARD)], input=b"not-json", capture_output=True, timeout=30
    )
    assert proc.returncode == 0


def test_remind_scripts_edit_emits_hint():
    proc = run_hook(REMIND, write_payload("scripts/verify_smoke.py"))
    assert proc.returncode == 0
    assert "affected_tests" in proc.stdout.decode("utf-8")


def test_remind_benchmark_edit_emits_hint():
    proc = run_hook(REMIND, write_payload("benchmark/runners/profiles.py"))
    assert proc.returncode == 0
    assert "affected_tests" in proc.stdout.decode("utf-8")


def test_remind_unrelated_edit_silent():
    proc = run_hook(REMIND, write_payload("api_server.py"))
    assert proc.returncode == 0
    assert proc.stdout == b""
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_hooks.py -q
```

Expected: 全部 FAIL（脚本不存在，`FileNotFoundError` 或 returncode 不匹配）。

- [ ] **Step 3: 实现 `.qoder/hooks/guard_data_artifacts.py`**

```python
#!/usr/bin/env python3
"""PreToolUse hook: block writes to tracked data artifacts.

Blocks direct file tools (Write/Edit) and explicit Bash commands that
write, move, or delete forbidden paths. Dynamically assembled paths are
NOT covered -- see spec 2026-08-07-agent-workflow-enhancement-design.md
section 4.3 for the honest protection boundary.

Protocol (Qoder Hooks, docs.qoder.com/extensions/hooks):
  block  -> reason on stderr + exit 2
  allow  -> exit 0
The exit-0 + stdout deny-JSON protocol is deliberately not used.

Reads one JSON event from stdin: {"tool_name": ..., "tool_input": {...}}
Stdlib only; never echoes prompts, env values, or suspected secrets.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 与 AGENTS.md §4 同步（单一事实源；同步检查见
# tests/test_qoder_workflow_assets.py::test_forbidden_patterns_single_source_of_truth）
FORBIDDEN_PATTERNS = (
    "knowledge-base/*.json",
    "tests/case_db.json",
    "data/*.json",
    "benchmark/datasets/*.jsonl",
)

_WRITE_HINTS = re.compile(
    r"(>>?|mv\b|move\b|rm\b|del\b|erase\b|remove-item\b|git\s+rm\b|git\s+checkout\s+--)",
    re.IGNORECASE,
)


def _normalize(path_str: str) -> str:
    """Normalize a tool file_path to a project-root-anchored posix path."""
    p = Path(os.path.normpath(path_str))
    if p.is_absolute():
        try:
            p = p.relative_to(PROJECT_ROOT)
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def _forbidden(posix_path: str) -> bool:
    return any(PurePosixPath(posix_path).match(pat) for pat in FORBIDDEN_PATTERNS)


def _bash_hits(command: str) -> bool:
    if not _WRITE_HINTS.search(command):
        return False
    return any(
        pat.rstrip("*").rstrip("/") in command.replace("\\", "/")
        for pat in FORBIDDEN_PATTERNS
    )


def _deny(reason: str) -> int:
    print(reason, file=sys.stderr)
    return 2


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except (ValueError, OSError):
        return 0  # fail-open: guard must not block the session on bad input
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if tool in ("Write", "Edit"):
        path = _normalize(str(tool_input.get("file_path") or ""))
        if _forbidden(path):
            return _deny(
                f"denied: {path} is a tracked data artifact (AGENTS.md §4 禁改清单)"
            )
    elif tool == "Bash":
        command = str(tool_input.get("command") or "")
        if _bash_hits(command):
            return _deny(
                "denied: explicit Bash write/move/delete targets a forbidden "
                "data artifact path (AGENTS.md §4 禁改清单)"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行 guard 相关测试确认转绿**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_hooks.py -k guard -q
```

Expected: 11 passed。

- [ ] **Step 5: Commit**

```powershell
git add .qoder/hooks/guard_data_artifacts.py tests/test_qoder_hooks.py
git commit -m "feat(hooks): add PreToolUse guard for tracked data artifacts"
```

---

### Task 4: remind_affected_tests.py（TDD）

**Files:**
- Create: `.qoder/hooks/remind_affected_tests.py`
- Test: `tests/test_qoder_hooks.py`（Task 3 已含 remind 测试，此时应红）

- [ ] **Step 1: 确认 remind 测试当前失败**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_hooks.py -k remind -q
```

Expected: 3 FAIL（脚本不存在）。

- [ ] **Step 2: 实现 `.qoder/hooks/remind_affected_tests.py`**

```python
#!/usr/bin/env python3
"""PostToolUse hook: remind to run affected tests after editing scripts/benchmark.

Never blocks (always exit 0). Reads one JSON event from stdin.
Stdlib only; never echoes prompts, env values, or suspected secrets.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WATCHED_PREFIXES = ("scripts/", "benchmark/")


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except (ValueError, OSError):
        return 0
    if event.get("tool_name") not in ("Write", "Edit"):
        return 0
    path = str((event.get("tool_input") or {}).get("file_path") or "")
    p = Path(os.path.normpath(path))
    if p.is_absolute():
        try:
            p = p.relative_to(PROJECT_ROOT)
        except ValueError:
            return 0
    posix = p.as_posix()
    if posix.startswith(WATCHED_PREFIXES):
        print(
            f"{posix} changed; consider: python scripts/affected_tests.py"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 运行全部 hook 测试确认转绿**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_hooks.py -q
```

Expected: 14 passed。

- [ ] **Step 4: Commit**

```powershell
git add .qoder/hooks/remind_affected_tests.py
git commit -m "feat(hooks): add PostToolUse affected-tests reminder"
```

---

### Task 5: Hook 注册 `.qoder/settings.json`

**Files:**
- Create: `.qoder/settings.json`（当前不存在，属新建；回退时删除，见 spec §7）

- [ ] **Step 1: 确认现状**

```powershell
Test-Path .qoder\settings.json
```

Expected: `False`（若为 True：先保存原内容到 `.tmp/settings.json.snapshot`，回退时恢复）。

- [ ] **Step 2: 写 `.qoder/settings.json`**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python .qoder/hooks/guard_data_artifacts.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python .qoder/hooks/remind_affected_tests.py"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: 运行 settings 结构测试确认转绿**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_workflow_assets.py::test_hook_settings_shape tests\test_qoder_workflow_assets.py::test_forbidden_patterns_single_source_of_truth -q
```

Expected: 2 passed。

- [ ] **Step 4: Commit**

```powershell
git add .qoder/settings.json
git commit -m "feat(hooks): register guard and reminder hooks in project settings"
```

---

### Task 6: 3 个 Custom Agents

**Files:**
- Create: `.qoder/agents/bench-runner.md`、`.qoder/agents/core-guard.md`、`.qoder/agents/rag-debugger.md`

- [ ] **Step 1: 确认 agents 测试当前失败**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_workflow_assets.py::test_agents_frontmatter_and_tool_scope -q
```

Expected: FAIL（文件不存在）。

- [ ] **Step 2: 写 `.qoder/agents/bench-runner.md`**

```markdown
---
name: bench-runner
description: 运行 MingLi-Bench / phase 评测脚本并汇总准确率对比的执行专家
tools: Read, Bash
---

你是玄机子评测执行专家，负责运行 benchmark/ 与 scripts/phase6_* 评测并汇总结果。

工作方式：
1. 先确认运行参数（题集、arm、repeat、模型协议、预算）；参数不明确时先问，不用默认值偷跑。
2. 优先干跑或 smoke 切片确认可运行，再进入正式运行。
3. 运行后读取 report/gate 产物给出准确率对比与结论；不口头断言分数，一切以产物为证。

边界：
- 只写 .tmp/ 与 benchmark/outputs/ 下的运行产物；不改 knowledge-base/、data/、benchmark/datasets/ 与任何被跟踪数据产物。
- 不修改评测脚本逻辑；发现脚本问题只报告，不顺手改。
```

- [ ] **Step 3: 写 `.qoder/agents/core-guard.md`**

```markdown
---
name: core-guard
description: 核心文件变更影响面审查专家（只读），输出最小影响链与验证建议
tools: Read, Grep, Glob
---

你是玄机子核心变更审查专家，只做只读分析，不做任何修改。

工作方式：
1. 对给定变更，沿调用链找出最小影响链：触发 → 边界/决策 → 失败/恢复 → 结果。
2. 对照 AGENTS.md §4 核心边界与被跟踪数据产物禁改清单，标记越界风险。
3. 输出：受影响文件清单、调用方、建议的验证入口（按 AGENTS.md §9 入口表选择，不要求全跑）。

边界：
- 只读代理：不写任何文件，不执行有副作用命令。
- 结论必须给出证据（文件 + 行号或调用关系）；没有证据的猜测明确标注。
```

- [ ] **Step 4: 写 `.qoder/agents/rag-debugger.md`**

```markdown
---
name: rag-debugger
description: RAG 检索问题诊断专家：检索日志、命中分析、漏检/错检归因
tools: Read, Bash, Grep
---

你是玄机子 RAG 检索诊断专家，负责定位"为什么这个 case 检索不到正确条文"类问题。

工作方式：
1. 复现：用最小命令重放该 case 的检索请求（hybrid_retrieval / case_index / case_dense_index 入口）。
2. 归因：分别检查召回（候选集是否含目标条文）、排序（reranker 打分）、截断（top-k 与长度）三段。
3. 结论：给出失败段与证据（日志/分数），以及最小修复建议；不直接改检索实现。

边界：
- 诊断产物只写 .tmp/；不改 knowledge-base/ 与任何被跟踪数据产物。
- 涉及重建索引的命令先说明成本再执行。
```

- [ ] **Step 5: 运行 agents 测试确认转绿**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_workflow_assets.py::test_agents_frontmatter_and_tool_scope -q
```

Expected: 1 passed。

- [ ] **Step 6: Commit**

```powershell
git add .qoder/agents/
git commit -m "feat(agents): add bench-runner, core-guard, rag-debugger subagents"
```

---

### Task 7: AGENTS.md §14 Memory 运营行

**Files:**
- Modify: `AGENTS.md`（§14 Project Learnings，追加一行；回退动作：删除该行）

- [ ] **Step 1: 记录原始状态**

确认 `AGENTS.md` §14 当前为 `- （空）`（用 `Select-String -Pattern "Project Learnings" -Context 0,4 AGENTS.md` 查看）。

- [ ] **Step 2: 追加运营行**

将 §14 的 `- （空）` 替换为：

```markdown
- 总是用 UpdateMemory 沉淀已验证的项目经验（环境配置、核心边界约束、评测基线、踩坑教训）；只记具体可执行规则，密钥与凭据永不入库。
```

- [ ] **Step 3: 运行对应测试确认转绿**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_workflow_assets.py::test_agents_md_memory_operation_line -q
```

Expected: 1 passed。

- [ ] **Step 4: Commit**

```powershell
git add AGENTS.md
git commit -m "docs(agents): add memory-capture operating rule to project learnings"
```

- [ ] **Step 5: 创建首批项目 Memory（验收前提，非本测试守护）**

本计划执行过程中产生的已验证结论（如 Hook 协议、affected_tests 两阶段流程）用 UpdateMemory 创建至少一条项目级 Memory。真实验收标准是"Qoder Memory 面实际出现至少一条经审核记录（后续会话可被 SearchMemory 检索）"，仅完成本文件的行追加不算通过。

---

### Task 8: 最终回归

**Files:** 无新增。

- [ ] **Step 1: 全量结构测试**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_qoder_workflow_assets.py tests\test_qoder_hooks.py -q
```

Expected: 全部 passed（assets 7 项 + hooks 14 项）。

- [ ] **Step 2: smoke 门禁**

```powershell
.venv\Scripts\python.exe scripts\verify_smoke.py
```

Expected: exit 0。

- [ ] **Step 3: 受影响测试两阶段流程**

```powershell
.venv\Scripts\python.exe scripts\affected_tests.py
```

Expected: 输出 `FULL_SUITE`（本计划改动命中 `tests/`）。按 quality-gate 流程：告知用户触发原因与全量范围，**等待明确批准**后再执行：

```powershell
.venv\Scripts\python.exe scripts\affected_tests.py --run
```

用户未批准则停在本步。Expected（批准后）：全量套件通过，新增 21 项测试全绿，无既有失败。

- [ ] **Step 4: skill 同步终检**

```powershell
.venv\Scripts\python.exe scripts\verify_skill_sync.py
```

Expected: `skill sync check OK: 5 skill(s) identical on both surfaces`。

---

## 自审记录（spec 覆盖核对）

| Spec 条目 | 对应任务 |
|---|---|
| §4.1 quality-gate（含两阶段 FULL_SUITE 流程） | Task 1；Task 8 Step 3 按该流程执行 |
| §4.2 三条 Rules + 生成期一致性约束 + 不写"必跑" | Task 2（含 test_core_boundary_selects_entry_not_mandatory_all 守护） |
| §4.3 冻结 Hook 契约（Write\|Edit\|Bash / exit 2 + stderr / Bash 显式拦截 / 保护范围如实） | Task 3-4 测试逐条覆盖；动态拼接 gap 有专门测试固化 |
| §4.3 禁改清单与 AGENTS.md §4 单一事实源 | test_forbidden_patterns_single_source_of_truth |
| §4.4 三个 Custom Agents + 最小工具权限 | Task 6（core-guard 无 Write/Edit/Bash 由测试守护） |
| §4.5 Memory 运营行 + 验收收紧 | Task 7（含 Step 5 真实 Memory 创建） |
| §6 验收标准 | Task 8 全量回归；IDE 侧触发验证（Rules/Hooks/Agents 运行时生效）需人工在会话中确认，非脚本可测 |
| §7 回退 | settings.json 新建/删除（Task 5 Step 1 快照检查）；AGENTS.md 行可删（Task 7 Step 1 记录原状） |
