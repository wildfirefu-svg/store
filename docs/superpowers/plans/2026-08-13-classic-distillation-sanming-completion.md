# 《三命通会》补全实施计划 v3.12.3（局部修订，6 个 P0 逐组闭合）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 补齐《三命通会》缺失 303 章所需的全部离线能力，并完成 fake-runner E2E。网页抓取与真实模型 API 均为独立批准入口，不在本计划执行范围内。

**唯一权威**：本文件是唯一可执行来源。每个阶段内联完整实现与测试，所有符号在使用前定义或导入。

**Tech Stack:** Python 3.11+、pytest、requests、tarfile、hashlib、`remediate_classic_distillation.py`（`rc._publish` / `rc._rollback_from_backup` 既有实现）。

**执行环境硬约束**：所有命令 PowerShell 可执行语法；不使用 `python - <<'PY'`。

---

## 版本说明（v3.12.2 → v3.12.3）

1. **P0-1（Phase 7 helper 块缺导入）**：helper 块顶部显式导入 `hashlib/json/subprocess/shutil/pytest`、`from pathlib import Path`、`import scripts.distill_lib as dl`；`_mk_batch_manifest` 用 `dl.EXPERIMENT_ID`。
2. **P0-2（progress 对真实数据 int() 异常）**：`_update_progress` 的 `done` 从既有 `prog["done"]` 合并本批 `selected_chapters` 的规范标题，不从 rules 反推（避免真实 `source_chapter` 是标题非数字导致 ValueError）。
3. **P0-3（backfill 未接线）**：`_backfill_staging_keys` 在生产 `run_sanming_batch` 的 `_seed_staging_from_existing` 之后调用；`backfill_canonical_keys` 原子写（tmp+os.replace）；provenance receipt 记录 input/output SHA、规则数、ID 集 SHA。
4. **P0-4（generation index 被当可信 JSON）**：completed 幂等检查经 `GenerationIndex(...).verify()` 验证完整 hash chain + genesis，再精确匹配 `(batch_id, completed_receipt_sha256)` 与 entry schema。
5. **P0-5（legacy hard cap 非权威门禁）**：新增锁内原子 `before_legacy_call()`（cap 检查 + 计数同锁，无 TOCTOU）；`distill_chapter`/`generate_mcq` legacy 路径改用之；`record_call` 降级为兼容桩。
6. **P0-6（restore 未验证 active pointer 闭环）**：`restore_responses` 先验证 active pointer（snapshot_sha256 + manifest 文件字节 SHA）；成员集负向测试同步更新 active pointer 使上游身份门通过。
- **中优**：版本号 v3.12.3；`cleanup_pending.json` 成功清理后删除（cleanup-completed 协议）；幂等测试 genesis 用 fake repo 实际 base commit（不再 `"0"*40`）；backfill 测试加规则数/顺序守恒断言；阶段 0 commit 消息改 v3.12.2；新增 `test_legacy_hard_cap_enforced` 与 `test_restore_rejects_active_pointer_drift`。
- **复审修订（5 个 P0 追加闭合）**：
  1. **P0-1（restore active pointer 校验旁路）**：闭环校验（active pointer → manifest 文件字节 SHA → archive pointer 文件字节 SHA → archive bytes SHA/size）整体移到幂等返回之前；新增"已物化后篡改 active pointer，再次 restore 必须拒绝"测试 `test_restore_rejects_active_pointer_drift_after_materialized`。
  2. **P0-2（legacy MCQ 双扣）**：删除 `generate_mcq` 循环外预扣；每个真实 attempt 只在紧邻 `_call` 前经 `before_legacy_call()` 原子扣账一次；新增断言"单次成功调用只增加 `legacy_calls=1`"。
  3. **P0-3（progress 静默迁移）**：`_update_progress` 重建内嵌数组作为**受控 reconcile**，经 `_record_progress_reconcile` 在 `remediation_meta.json` 显式记录输入/输出 SHA、旧/新数量与 ID 命名空间说明（`smth_0001` vs `smth_000_000`）。
  4. **P0-4（backfill 守恒断言无效）**：`test_backfill_front80_keeps_ids` 改为保存原始对象序列、逐项断言仅允许新增 `{canonical_key, source_book, source_chapter, category}`、既有字段与原始顺序完全不变。
  5. **P0-5（GenerationIndex entry schema 门禁）**：新增 `validate_generation_index_entry`（冻结字段集合/类型/64-hex SHA 格式），`verify_generation_index_entries` 与 `GenerationIndex.verify()` 共用；缺字段但自洽的 index 一律拒绝。
  - **中优追加**：`_fill_real_shas`/`_run` 改用 `ROOT`（不再 `Path(".")`）；`_retry_pending_cleanup` 在 completed 幂等入口重试未完成 cleanup，成功才清除 `cleanup_pending.json`；阶段 0 commit 消息与自审清单版本号统一为 v3.12.3。
- **复审修订 2（3 个 P0 确定性阻断 + 中优闭合）**：
  1. **P0-1（GenerationIndex 40/64 契约自相矛盾）**：拆分首条/后续 entry schema——`genesis_commit` 恒为 40-hex Git SHA；首条 `previous_index_sha256=None`，后续才为 64-hex 链前缀 SHA。`validate_generation_index_entry(e, *, is_first=...)` 与 `verify_generation_index_entries` 共用；`GenerationIndex.append` 首条填 `None`。真实 40-hex genesis 首条可通过 `verify()`。
  2. **P0-2（cleanup receipt 可任意目录递归删除）**：`_retry_pending_cleanup` 改为仅在 completed receipt 身份校验后调用，并校验 cleanup receipt 的 batch/genesis，backup 解析为绝对路径、必须位于冻结的 backup root（out_dir）内、目录名匹配 `^\.publish_backup_\d+_\d+$`，全部通过才 rmtree。新增路径逃逸/绝对路径/错误 batch 负向测试。
  3. **P0-3（fake-flow 未跑真实生产链）**：临时证明模块内联计划版完整生产链（阶段 5/6/7/8 + `rc._publish`），fake_flow 直接调用计划版 `run_sanming_batch()`，验证 manifest、双账本、staging publish、completed receipt、cleanup、GenerationIndex finalize 组合链，不再平行简化。
  - **中优追加 2**：`validate_generation_index_entry` 精确断言 `set(e) == FROZEN_ENTRY_FIELDS`（拒绝额外字段）；progress reconcile 产出逐记录 `mapped`/`conflicts`/`unmappable` + 各自 canonical SHA；cleanup 新逻辑进入临时证明模块；验证命令显式冻结可写 `--basetemp`。
- **复审修订 3（3 个 P0 逐字同源 + 实时数据核验闭合）**：
  1. **P0-1（计划版幂等仍拒绝首条 entry）**：`run_sanming_batch` 的 completed 幂等匹配删除手写 `previous_index_sha256` 长度条件——`idx.verify()` 已校验完整 hash chain + entry schema（首条 previous=None、genesis_commit 40-hex），此处只精确匹配 `(batch_id, completed_receipt_sha256, genesis_commit)`；proof 与计划逐字同源（AST 对比通过）。
  2. **P0-2（progress 历史 ID 不唯一）**：真实数据 1727 条规则 / 92 个唯一旧 ID / 79 个 ID 重复（`smth_0001` 对应 78 个不同 canonical key）。废弃 `dict[old_id]`，改为逐记录映射：`mapped`（唯一对应）/`conflicts`（一对多）/`unmappable`（缺失/无对应）+ 三类列表 canonical SHA，且 `mapped+conflicts+unmappable == len(old_rules)` 守恒；新增真实前 80 章副本守恒测试（1727）。
  3. **P0-3（备份目录非 batch 专属）**：把 `backup_dir` + 内容指纹（成员集 SHA + 成员内容 SHA 映射）冻结进 **completed receipt**（收进 `completed_receipt_sha256`，被 generation index 认证）；cleanup 只在 index 认证 completed receipt 之后的 completed_idempotent 分支重试，删除目标与指纹取自已认证 receipt 冻结值、忽略可变的 `cleanup_pending.json` 路径/指纹——篡改 pending 指向另一 batch 的合法备份目录也无法删除。未 finalize 分支不做 cleanup。新增"篡改 pending 指向另一 batch"负向测试 + 内容指纹不匹配负向测试；`cleanup_pending.output_shas` 不再承担权威校验（output_shas 由 completed receipt 身份校验承担）。
- **复审修订 4（cleanup 错误静默吞掉 → fail-closed 显式状态）**：
  1. **P0（cleanup 身份错误被静默吞掉）**：`_retry_pending_cleanup` 由"静默 return/pass"改为**显式返回清理状态** `"noop"`（无 pending）/`"cleaned"`（清理完成）/`"blocked"`（身份/路径/指纹/解析/文件系统失败，pending 与备份目录均保留）；JSON 解析失败、batch/genesis 不匹配、路径逃逸、名称非法、指纹不匹配、`rmtree` 失败（含部分删除后指纹不再匹配）一律返回 `"blocked"`，不再吞错误。调用方 `run_sanming_batch` 只在 `noop`/`cleaned` 时返回 `completed_idempotent`，`blocked` 时返回 **`completed_cleanup_blocked`**（保留 pending 与备份目录）。新增完整链负向测试：finalize 后篡改备份内容（磁盘指纹 != 冻结指纹）→ 不调用 API、不删除目录、不得返回 `completed_idempotent`；另增 pending 解析失败与 `rmtree` 失败 blocked 测试。

---

## 阶段 0：门禁决策与干净 worktree

- [ ] 审核方指定分支 A（修复 `bazi_kb.db` 快照/重建契约）或分支 B（正式改测试/门禁契约）。写入 `docs/superpowers/plans/notes/2026-08-13-sanming-phase0-decision.md` 并提交。

```powershell
git add docs/superpowers/plans/2026-08-13-classic-distillation-sanming-completion.md
git diff --cached --name-only
git commit -m "docs(classic-distillation): plan v3.12.3 - close 11 blockers" -m "P0 逐组闭合：restore active-pointer 闭环先于幂等返回、legacy MCQ 单次原子扣账、progress 显式迁移记录、backfill 守恒断言、GenerationIndex entry schema 门禁；中优 cleanup 幂等重试 / ROOT 路径 / commit 消息版本号。"
$B3_12 = git rev-parse HEAD
git worktree add -b codex/sanming-completion G:\project\agent-sanming $B3_12
```

---

## 阶段 1：E→R→B1 + EXPERIMENT_ID 常量

### 1.1 `scripts/classic_artifacts.py`

```python
from __future__ import annotations
import json, hashlib
from pathlib import Path

EXPERIMENT_ID = "sanming-303-completion"
EXEMPT_ALLOWLIST = ("missing_upstream_response_body",)
NON_EXEMPT_ALLOWLIST = ("artifact_integrity", "quality_gates", "future_generation_provenance")

class HistoricalArtifactDriftError(ValueError):
    pass

def exemption_request_sha256(e: dict) -> str:
    return hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

def verify_exemption_request(e: dict) -> bool:
    for k in ("book", "artifact_manifest_sha256", "baseline_commit", "validator_code_sha256", "exempted_checks", "non_exempt_checks", "author", "date"):
        if k not in e: raise ValueError(f"exemption request missing {k}")
    if not set(e["exempted_checks"]) <= set(EXEMPT_ALLOWLIST): raise ValueError("exempted_checks outside allowlist")
    if not set(e["non_exempt_checks"]) <= set(NON_EXEMPT_ALLOWLIST): raise ValueError("non_exempt_checks outside allowlist")
    if set(e["exempted_checks"]) & set(e["non_exempt_checks"]): raise ValueError("overlapping exempt/non-exempt")
    for forbidden in ("approval_receipt_sha256", "approval_commit"):
        if forbidden in e: raise ValueError(f"exemption request must not contain {forbidden}")
    return True

def verify_approval_receipt(r: dict, e: dict) -> bool:
    if r.get("exemption_request_sha256") != exemption_request_sha256(e): raise ValueError("approval receipt exemption_request_sha256 mismatch")
    if r.get("baseline_commit") != e.get("baseline_commit"): raise ValueError("approval receipt baseline_commit mismatch")
    if r.get("artifact_manifest_sha256") != e.get("artifact_manifest_sha256"): raise ValueError("approval receipt artifact_manifest_sha256 mismatch")
    if not r.get("approver") or not r.get("approved_at"): raise ValueError("approval receipt missing approver/approved_at")
    return True

def build_artifact_manifest(book_dir, *, git_ref, git_root):
    import subprocess as _sp
    files = sorted(p for p in Path(book_dir).iterdir() if p.is_file() and p.suffix in (".json", ".jsonl", ".txt"))
    shas = {}
    for p in files: shas[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    for name, sha in shas.items():
        rel = str(Path(book_dir).resolve().relative_to(Path(git_root).resolve()) / name).replace("\\", "/")
        blob = _sp.run(["git", "-C", str(git_root), "show", f"{git_ref}:{rel}"], capture_output=True).stdout
        if hashlib.sha256(blob).hexdigest() != sha: raise HistoricalArtifactDriftError(f"{rel} drifts from git blob at {git_ref}")
    return {"sha256_by_path": shas, "git_ref": git_ref, "git_verified": True}

def load_exemption_request(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
```

### 1.2 `scripts/make_historical_exemption.py`

```python
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.classic_artifacts import build_artifact_manifest, verify_exemption_request

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True); ap.add_argument("--baseline", required=True); ap.add_argument("--out", required=True); ap.add_argument("--git-root", default=str(ROOT))
    a = ap.parse_args(argv)
    git_root = Path(a.git_root)
    book_dir = git_root / "knowledge_base" / "classic_texts" / a.book
    man = build_artifact_manifest(book_dir, git_ref=a.baseline, git_root=git_root)
    manifest_sha = hashlib.sha256(json.dumps(man, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    val_sha = hashlib.sha256((git_root / "scripts/validate_classic_distillation.py").read_bytes()).hexdigest()
    e = {"schema_version": "1.0", "book": a.book, "baseline_commit": a.baseline, "artifact_manifest_sha256": manifest_sha, "validator_code_sha256": val_sha, "exempted_checks": ["missing_upstream_response_body"], "non_exempt_checks": ["artifact_integrity", "quality_gates", "future_generation_provenance"], "author": "implementing-agent", "date": "2026-08-13", "reason": "80 章为历史导入无上游 response body，豁免缺失上游链；内容完整性与质量门不豁免"}
    verify_exemption_request(e)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__": raise SystemExit(main())
```

### 1.3 `scripts/validate_classic_distillation.py`

```python
from scripts.classic_artifacts import verify_exemption_request

def apply_exemption(issues: dict, exemption_request: dict) -> dict:
    verify_exemption_request(exemption_request)
    out = dict(issues)
    for check in exemption_request["exempted_checks"]:
        if check in out: out[check] = "exempted"
    return out
```

### 1.4 `scripts/run_manifest.py`

```python
from __future__ import annotations
import json, subprocess
from pathlib import Path

def build_run_manifest(*, run_id, approval_commit, schedule_hash="", raw_dataset_sha="", enriched_dataset_sha=""):
    return {"schema_version": "1.0", "run_id": run_id, "approval_commit": approval_commit, "schedule_hash": schedule_hash, "raw_dataset_sha": raw_dataset_sha, "enriched_dataset_sha": enriched_dataset_sha}

def verify_run_manifest(m, *, expected_approval_commit):
    for k in ("schema_version", "run_id", "approval_commit"):
        if k not in m: raise ValueError(f"run manifest missing {k}")
    if m["approval_commit"] != expected_approval_commit: raise ValueError("run manifest approval_commit mismatch")
    if len(m["approval_commit"]) != 40: raise ValueError("run manifest approval_commit not a 40-char commit")

def _git(git_root, *args):
    import subprocess as _sp; return _sp.run(["git", "-C", str(git_root), *args], capture_output=True, text=True)

def verify_approval_commit_reachable(commit, git_root):
    if _git(git_root, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0: raise ValueError(f"approval_commit {commit} is not an existing commit object")
    if _git(git_root, "merge-base", "--is-ancestor", commit, "HEAD").returncode != 0: raise ValueError(f"approval_commit {commit} is not reachable from HEAD (dangling)")
```

### 1.5 测试

`tests/test_historical_exemption.py`：

```python
import json, hashlib, subprocess
from pathlib import Path
import pytest
from scripts.classic_artifacts import (
    EXPERIMENT_ID, exemption_request_sha256, verify_exemption_request, verify_approval_receipt,
    build_artifact_manifest, EXEMPT_ALLOWLIST, NON_EXEMPT_ALLOWLIST, HistoricalArtifactDriftError, load_exemption_request,
)
ROOT = Path(__file__).resolve().parent.parent

def _b1():
    p = ROOT / "docs/superpowers/plans/notes/2026-08-13-sanming-b1-commit.md"
    assert p.exists(), "B1 not recorded: Phase 1 not complete"
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.startswith("B1="):
            v = ln.split("=", 1)[1].strip(); assert len(v) == 40 and v != "b1" * 40; return v
    raise AssertionError("B1= missing in notes")

def test_experiment_id_frozen(): assert EXPERIMENT_ID == "sanming-303-completion"
def test_allowlists_frozen():
    assert set(EXEMPT_ALLOWLIST) == {"missing_upstream_response_body"}
    assert set(NON_EXEMPT_ALLOWLIST) == {"artifact_integrity", "quality_gates", "future_generation_provenance"}
def test_exemption_request_rejects_self_refs():
    e = {"book": "ditiansui", "baseline_commit": "a"*40, "artifact_manifest_sha256": "b"*64, "validator_code_sha256": "c"*64, "exempted_checks": ["missing_upstream_response_body"], "non_exempt_checks": ["artifact_integrity"], "author": "r", "date": "2026-08-13", "approval_receipt_sha256": "0"*64}
    with pytest.raises(ValueError, match="approval_receipt_sha256"): verify_exemption_request(e)
def test_verify_approval_receipt_binds_exemption():
    e = {"book": "ditiansui", "baseline_commit": "a"*40, "artifact_manifest_sha256": "b"*64, "validator_code_sha256": "c"*64, "exempted_checks": ["missing_upstream_response_body"], "non_exempt_checks": ["artifact_integrity"], "author": "r", "date": "2026-08-13"}
    r = {"exemption_request_sha256": exemption_request_sha256(e), "baseline_commit": "a"*40, "artifact_manifest_sha256": "b"*64, "approver": "lead", "approved_at": "2026-08-13T00:00:00Z"}
    assert verify_approval_receipt(r, e) is True
    r2 = dict(r); r2["exemption_request_sha256"] = "0"*64
    with pytest.raises(ValueError, match="exemption_request_sha256 mismatch"): verify_approval_receipt(r2, e)
def test_artifact_manifest_verifies_git_blob(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    book = repo / "book"; book.mkdir(); f = book / "all_rules.json"; f.write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "b0"], check=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    assert build_artifact_manifest(book, git_ref=head, git_root=repo)["git_verified"] is True
    f.write_text('{"tampered": true}', encoding="utf-8")
    with pytest.raises(HistoricalArtifactDriftError): build_artifact_manifest(book, git_ref=head, git_root=repo)
def test_make_e_never_writes_receipt(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "scripts").mkdir(parents=True); (repo / "scripts/validate_classic_distillation.py").write_text("# validator", encoding="utf-8")
    book = repo / "knowledge_base" / "classic_texts" / "ditiansui"; book.mkdir(parents=True); (book / "all_rules.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "b0"], check=True)
    b0 = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    out = tmp_path / "e.json"
    subprocess.run(["python", "scripts/make_historical_exemption.py", "--book", "ditiansui", "--baseline", b0, "--out", str(out), "--git-root", str(repo)], check=True, cwd=ROOT)
    e = load_exemption_request(out); assert "approval_receipt_sha256" not in e and "approval_commit" not in e; assert not (tmp_path / "r.json").exists()
def test_real_e_has_no_self_refs(): assert "approval_receipt_sha256" not in load_exemption_request(ROOT / "tests/testdata/e.json")
def test_real_r_binds_real_e():
    e = load_exemption_request(ROOT / "tests/testdata/e.json"); r = json.loads((ROOT / "tests/testdata/r.json").read_text(encoding="utf-8")); assert verify_approval_receipt(r, e) is True
@pytest.mark.slow
def test_production_b1_reachable_in_real_repo():
    from scripts.run_manifest import verify_approval_commit_reachable
    verify_approval_commit_reachable(_b1(), git_root=ROOT)
```

`tests/test_make_historical_exemption.py`、`tests/test_classic_distillation_validator.py`：`apply_exemption`、run manifest、B1 可达/悬空。运行 `pytest ... -q -m "not slow"` → PASS → 提交 → 人工审批门（E 交付审核，执行代理不写 R）→ 一次性提交 E+R → B1 记录 → run manifest 写入。

---

## 阶段 2：383 章 parser + 80/303 bootstrap

`scripts/fetch_sanming_chapters.py`：

```python
from __future__ import annotations
import json, os, re, hashlib
from dataclasses import dataclass
from pathlib import Path

_LINE_RE = re.compile(r"^\s*(\d{1,3})\.\s*(.+?)\t(\S+)$")
EXPECTED_COUNT = 383

@dataclass(frozen=True)
class ChapterEntry:
    index: int; title: str; url: str

def parse_chapter_list(text: str) -> list[ChapterEntry]:
    entries, urls, indexes = [], set(), set()
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        m = _LINE_RE.match(line)
        if not m: raise ValueError(f"malformed line: {line!r}")
        idx, title, url = int(m.group(1)), m.group(2), m.group(3)
        if not title: raise ValueError(f"empty title at {idx}")
        if url in urls: raise ValueError(f"duplicate url at {idx}: {url}")
        if idx in indexes: raise ValueError(f"duplicate index: {idx}")
        urls.add(url); indexes.add(idx)
        entries.append(ChapterEntry(index=idx, title=title, url=url))
    if len(entries) != EXPECTED_COUNT or sorted(e.index for e in entries) != list(range(1, EXPECTED_COUNT + 1)):
        raise ValueError(f"expected {EXPECTED_COUNT} contiguous chapters 1..{EXPECTED_COUNT}, got {len(entries)}")
    return entries

def _legacy_index(name: str) -> int | None:
    m = re.match(r"raw_(\d+)_", name); return int(m.group(1)) if m else None

def bootstrap_snapshot(legacy_raw_dir: Path, chapter_list, fetched_records):
    records, ids = [], []
    legacy_by_idx = {}
    for p in Path(legacy_raw_dir).glob("raw_*.txt"):
        idx = _legacy_index(p.name)
        if idx is not None: legacy_by_idx[idx] = p
    for entry in [c for c in chapter_list if c.index <= 80]:
        p = legacy_by_idx.get(entry.index)
        if p is None: raise ValueError(f"legacy raw missing for index {entry.index}")
        data = p.read_bytes()
        records.append({"chapter_index": entry.index, "title": entry.title, "url": entry.url, "extracted_text_sha256": hashlib.sha256(data).hexdigest(), "response_body_sha256": None, "response_body_status": "historical_unavailable", "extractor_sha256": None, "normalized_page_title": None, "provenance_level": "historical_text_only", "encoding": "utf-8"})
        ids.append(entry.index)
    for rec in fetched_records:
        for k in ("response_body_status", "provenance_level", "encoding"):
            if k not in rec: raise ValueError(f"fetched record missing manifest field {k}")
        records.append(rec); ids.append(rec["chapter_index"])
    if sorted(ids) != list(range(1, 384)): raise ValueError("bootstrap must yield exactly 383 unique contiguous ids")
    return {"ids": ids, "records": records}
```

`tests/test_fetch_sanming_chapters.py`：

```python
import pytest
from scripts.fetch_sanming_chapters import parse_chapter_list, bootstrap_snapshot, ChapterEntry

def test_parse_requires_383_contiguous():
    text = "\n".join(f"{i}. 章{i}\thttps://x/{i}.html" for i in range(1, 383))
    with pytest.raises(ValueError, match="383"): parse_chapter_list(text)
    full = text + "\n383. 章383\thttps://x/383.html\n"
    es = parse_chapter_list(full)
    assert len(es) == 383 and [e.index for e in es] == list(range(1, 384))
def test_parse_rejects_duplicate_url_and_index():
    dup = "1. a\thttps://x/1\n1. b\thttps://x/2\n2. c\thttps://x/1\n"
    with pytest.raises(ValueError, match="(duplicate url|duplicate index)"): parse_chapter_list(dup)
def test_bootstrap_merges_80_plus_303_to_383(tmp_path):
    legacy = tmp_path / "legacy"; legacy.mkdir()
    for i in range(1, 81): (legacy / f"raw_{i:03d}_章{i}.txt").write_text(f"T{i}", encoding="utf-8")
    fetched = [{"chapter_index": i, "title": f"章{i}", "url": f"u{i}", "extracted_text_sha256": "e"*64, "response_body_sha256": "r"*64, "extractor_sha256": "x"*64, "normalized_page_title": f"章{i}", "response_body_status": "archived", "provenance_level": "full", "encoding": "utf-8"} for i in range(81, 384)]
    chapter_list = [ChapterEntry(index=i, title=f"章{i}", url=f"u{i}") for i in range(1, 384)]
    snap = bootstrap_snapshot(legacy, chapter_list, fetched)
    assert sorted(snap["ids"]) == list(range(1, 384)) and len(snap["records"]) == 383
    for r in snap["records"]:
        for k in ("encoding", "response_body_status", "provenance_level", "extracted_text_sha256"): assert k in r
```

RED → GREEN → 提交。

---

## 阶段 3：canonical tar + golden SHA

```python
# scripts/fetch_sanming_chapters.py（追加）
import tarfile, io

def build_canonical_tar(responses: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:", format=tarfile.GNU_FORMAT) as tf:
        for name in sorted(responses, key=lambda n: int(re.search(r"raw_(\d+)\.html", n).group(1))):
            data = responses[name]
            info = tarfile.TarInfo(name=name)
            info.size = len(data); info.mtime = 0; info.uid = 0; info.gid = 0; info.uname = ""; info.gname = ""; info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()
```

`tests/test_canonical_tar_golden.py`：

```python
import hashlib, tarfile, io
from scripts.fetch_sanming_chapters import build_canonical_tar

FIXTURE = {"responses/raw_081.html": b"<html>B1</html>", "responses/raw_082.html": b"<html>B2</html>", "responses/raw_083.html": b"<html>B3</html>"}
GOLDEN_ARCHIVE_SIZE = 10240
GOLDEN_SHA256 = "1bca7aeb1ce38ef0b5069180b5aba1d214914eaf49840925a595c86470c49009"

def test_canonical_tar_golden_sha_and_size():
    data = build_canonical_tar(FIXTURE)
    assert len(data) == GOLDEN_ARCHIVE_SIZE
    assert hashlib.sha256(data).hexdigest() == GOLDEN_SHA256
def test_canonical_tar_layout():
    data = build_canonical_tar(FIXTURE)
    tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
    names = tf.getnames(); assert names == sorted(names)
    for m in tf.getmembers():
        assert not m.isdir() and m.mtime == 0 and m.uid == 0 and m.gid == 0 and m.uname == "" and m.gname == "" and m.mode == 0o644
```

RED → GREEN → 提交。

---

## 阶段 4：snapshot 发布/restore/materialization

```python
# scripts/fetch_sanming_chapters.py（追加）
class ManifestClosedLoopError(RuntimeError): pass

def snapshot_canonical_sha(records) -> str:
    canon = json.dumps([{"i": r["chapter_index"], "t": r["title"], "u": r["url"], "e": r["extracted_text_sha256"], "r": r["response_body_sha256"], "x": r["extractor_sha256"], "p": r["normalized_page_title"], "enc": r.get("encoding"), "rbs": r.get("response_body_status"), "pl": r.get("provenance_level")} for r in records], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()

def _file_sha256(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def _safe_member_name(name: str) -> str:
    if "\\" in name or name.startswith("/"): raise ManifestClosedLoopError(f"unsafe tar member: {name!r}")
    parts = name.split("/")
    if len(parts) != 2 or parts[0] != "responses" or not parts[1] or ".." in parts: raise ManifestClosedLoopError(f"tar member outside responses/: {name!r}")
    return parts[1]

def build_and_publish_snapshot(entries, formal_dir, records_factory, archive_root):
    import shutil
    staging = formal_dir / ".staging"
    if staging.exists(): shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    records = records_factory(entries)
    (staging / "extracted").mkdir()
    responses = {}
    for rec in records:
        t = rec["extracted_text"]; b = rec.get("response_body")
        tex = t.encode("utf-8")
        if hashlib.sha256(tex).hexdigest() != rec.get("extracted_text_sha256"): raise ManifestClosedLoopError(f"extracted_text_sha256 mismatch (actual bytes) for chapter {rec['chapter_index']}")
        if b is not None and hashlib.sha256(b).hexdigest() != rec.get("response_body_sha256"): raise ManifestClosedLoopError(f"response_body_sha256 mismatch (actual bytes) for chapter {rec['chapter_index']}")
        out = staging / "extracted" / f"raw_{rec['chapter_index']:03d}.txt"; out.write_bytes(tex)
        if hashlib.sha256(out.read_bytes()).hexdigest() != rec.get("extracted_text_sha256"): raise ManifestClosedLoopError(f"extracted file bytes drift after write for chapter {rec['chapter_index']}")
        if b is not None: responses[f"responses/raw_{rec['chapter_index']:03d}.html"] = b
    archive_bytes = build_canonical_tar(responses) if responses else b""
    archive_sha = hashlib.sha256(archive_bytes).hexdigest()
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_path = archive_root / f"{archive_sha}.tar"; archive_path.write_bytes(archive_bytes)
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != archive_sha: raise ManifestClosedLoopError("archive readback mismatch")
    snap_sha = snapshot_canonical_sha(records)
    pointer = {"snapshot_sha256": snap_sha, "archive_format": "tar", "archive_sha256": archive_sha, "archive_size": len(archive_bytes), "archive_uri": f"{archive_root}/{archive_sha}.tar", "response_count": len(responses)}
    ptr_file = staging / "RESPONSE_ARCHIVE_POINTER.json"; ptr_file.write_text(json.dumps(pointer, ensure_ascii=False, indent=2), encoding="utf-8")
    pointer_sha = _file_sha256(ptr_file)
    manifest = {"snapshot_sha256": snap_sha, "response_archive_pointer_sha256": pointer_sha, "chapters": [{k: r[k] for k in ("chapter_index", "title", "url", "response_body_sha256", "response_body_status", "provenance_level", "encoding", "extracted_text_sha256", "extractor_sha256", "normalized_page_title")} for r in records]}
    man_file = staging / "source_manifest.json"; man_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if json.loads(man_file.read_text(encoding="utf-8")) != manifest: raise ManifestClosedLoopError("manifest readback mismatch")
    snapshots = formal_dir / "source_snapshots"; snapshots.mkdir(parents=True, exist_ok=True)
    target = snapshots / snap_sha
    if target.exists():
        existing = json.loads((target / "source_manifest.json").read_text(encoding="utf-8"))
        if existing != manifest: shutil.rmtree(staging, ignore_errors=True); raise ManifestClosedLoopError("snapshot exists with drifted manifest")
        if _file_sha256(target / "RESPONSE_ARCHIVE_POINTER.json") != pointer_sha: shutil.rmtree(staging, ignore_errors=True); raise ManifestClosedLoopError("snapshot exists with drifted pointer file bytes")
        shutil.rmtree(staging, ignore_errors=True)
    else: os.replace(str(staging), str(target))
    manifest_sha = _file_sha256(target / "source_manifest.json")
    pointer_file = formal_dir / "active_source_snapshot.json"
    tmp_p = pointer_file.with_suffix(".tmp")
    tmp_p.write_text(json.dumps({"snapshot_sha256": snap_sha, "source_manifest_sha256": manifest_sha}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp_p), str(pointer_file))
    return True

def read_active_snapshot(formal_dir):
    p = formal_dir / "active_source_snapshot.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

def restore_responses(formal_dir, snap_sha, archive_root):
    import shutil
    snap_dir = formal_dir / "source_snapshots" / snap_sha
    # P0-6/P0-1：先验证 active pointer 闭环（放在幂等 return 之前，已物化也不能绕过）：
    # active.snapshot_sha256 -> manifest 文件字节 SHA -> archive pointer 文件字节 SHA -> archive bytes SHA/size
    act = read_active_snapshot(formal_dir)
    if not act or act.get("snapshot_sha256") != snap_sha: raise ManifestClosedLoopError("active pointer snapshot_sha256 mismatch")
    if _file_sha256(snap_dir / "source_manifest.json") != act.get("source_manifest_sha256"): raise ManifestClosedLoopError("active pointer source_manifest_sha256 != manifest file bytes SHA")
    man_file = snap_dir / "source_manifest.json"; man = json.loads(man_file.read_text(encoding="utf-8"))
    ptr_file = snap_dir / "RESPONSE_ARCHIVE_POINTER.json"
    if _file_sha256(ptr_file) != man.get("response_archive_pointer_sha256"): raise ManifestClosedLoopError("pointer file bytes SHA mismatch with manifest")
    ptr = json.loads(ptr_file.read_text(encoding="utf-8"))
    if ptr["snapshot_sha256"] != snap_sha: raise ManifestClosedLoopError("pointer snapshot mismatch")
    data = Path(ptr["archive_uri"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != ptr["archive_sha256"]: raise ManifestClosedLoopError("archive sha mismatch")
    if len(data) != ptr["archive_size"]: raise ManifestClosedLoopError("archive size mismatch")
    # 幂等：已存在且与 manifest 一致则跳过；不一致则拒绝，避免 Windows 重复 os.replace 失败
    responses_dir = snap_dir / "responses"
    if responses_dir.exists():
        if materialization_status(formal_dir, snap_sha) == "materialized": return
        raise ManifestClosedLoopError("responses/ exists but not consistent with manifest (refuse)")
    by_idx = {c["chapter_index"]: c for c in man["chapters"]}
    expected = {"responses/raw_%03d.html" % c["chapter_index"] for c in man["chapters"] if c.get("response_body_status") == "archived"}
    tmp_dir = snap_dir / "responses.tmp"
    if tmp_dir.exists(): shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
            members = tf.getmembers()
            actual = set(m.name for m in members)
            if actual != expected: raise ManifestClosedLoopError(f"archive member set mismatch: got {actual - expected} extra / {expected - actual} missing")
            if len(members) != ptr["response_count"]: raise ManifestClosedLoopError(f"archive member count {len(members)} != {ptr['response_count']}")
            for m in members:
                if not m.isfile(): raise ManifestClosedLoopError(f"archive member not a file: {m.name}")
                base = _safe_member_name(m.name)
                if not re.fullmatch(r"raw_\d{3}\.html", base): raise ManifestClosedLoopError(f"member name not raw_<3digits>.html: {base!r}")
                idx = int(base[4:7]); ch = by_idx.get(idx)
                if ch is None or ch.get("response_body_status") != "archived": raise ManifestClosedLoopError(f"member {m.name} not an archived chapter")
                content = tf.extractfile(m).read()
                if hashlib.sha256(content).hexdigest() != ch.get("response_body_sha256"): raise ManifestClosedLoopError(f"member {m.name} sha mismatch")
                (tmp_dir / base).write_bytes(content)
        os.replace(str(tmp_dir), str(snap_dir / "responses"))
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True); raise

def materialization_status(formal_dir, snap_sha):
    snap_dir = formal_dir / "source_snapshots" / snap_sha
    if not (snap_dir / "source_manifest.json").exists(): return "unmaterialized"
    man = json.loads((snap_dir / "source_manifest.json").read_text(encoding="utf-8"))
    for ch in man["chapters"]:
        if ch.get("response_body_status") == "archived":
            p = snap_dir / "responses" / f"raw_{ch['chapter_index']:03d}.html"
            if not p.exists(): return "unmaterialized"
            if hashlib.sha256(p.read_bytes()).hexdigest() != ch.get("response_body_sha256"): return "unmaterialized"
    return "materialized"
```

`tests/test_fetch_sanming_chapters.py`（阶段 4 追加；fixture 用 closure 捕获 text/body）：

```python
def _records_for(entries, status="archived", prov="full", text="T", body=b"B"):
    return [{"chapter_index": e.index, "title": e.title, "url": e.url, "response_body_sha256": hashlib.sha256(body).hexdigest(), "extracted_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "extractor_sha256": "x"*64, "normalized_page_title": e.title, "response_body_status": status, "provenance_level": prov, "encoding": "utf-8", "extracted_text": text, "response_body": body, "ok": True} for e in entries]

def _publish_one(tmp_path, entries=None, text="T", body=b"B"):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = entries or [ChapterEntry(81, "卷六·论命", "u1")]
    def factory(entries): return _records_for(entries, text=text, body=body)
    formal = tmp_path / "formal"; store = tmp_path / "store"
    build_and_publish_snapshot(entries, formal, records_factory=factory, archive_root=store)
    return formal, store, read_active_snapshot(formal)["snapshot_sha256"]

def test_publish_writes_exact_bytes_and_verifies(tmp_path):
    text = "第一段。\n第二段。\n"; formal, store, sha = _publish_one(tmp_path, text=text)
    f = formal / "source_snapshots" / sha / "extracted" / "raw_081.txt"
    assert f.read_bytes() == text.encode("utf-8")
def test_publish_recomputes_hashes_from_actual_bytes(tmp_path):
    from scripts.fetch_sanming_chapters import ChapterEntry
    e = ChapterEntry(81, "卷六·论命", "u1")
    def bad(entries, **kw): recs = _records_for(entries, text="T", body=b"B"); recs[0]["extracted_text_sha256"] = "0"*64; return recs
    with pytest.raises(ManifestClosedLoopError, match="extracted"): build_and_publish_snapshot([e], tmp_path / "f", records_factory=bad, archive_root=tmp_path / "s")
def test_publish_leaves_unmaterialized_then_restore_materializes(tmp_path):
    formal, store, sha = _publish_one(tmp_path)
    assert materialization_status(formal, sha) == "unmaterialized"
    restore_responses(formal, sha, archive_root=store)
    assert materialization_status(formal, sha) == "materialized"
def test_pointer_and_manifest_sha_are_file_bytes(tmp_path):
    formal, store, sha = _publish_one(tmp_path)
    man = json.loads((formal / "source_snapshots" / sha / "source_manifest.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((formal / "source_snapshots" / sha / "RESPONSE_ARCHIVE_POINTER.json").read_bytes()).hexdigest() == man["response_archive_pointer_sha256"]
    act = json.loads((formal / "active_source_snapshot.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((formal / "source_snapshots" / sha / "source_manifest.json").read_bytes()).hexdigest() == act["source_manifest_sha256"]
def test_idempotent_reuse_verifies_all_identity_fields(tmp_path):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = [ChapterEntry(81, "卷六·论命", "u1")]
    formal = tmp_path / "formal"; store = tmp_path / "store"
    build_and_publish_snapshot(entries, formal, records_factory=lambda e: _records_for(e), archive_root=store)
    sha1 = read_active_snapshot(formal)["snapshot_sha256"]
    ptr_file = formal / "source_snapshots" / sha1 / "RESPONSE_ARCHIVE_POINTER.json"
    ptr_file.write_text('{"snapshot_sha256": "0"*64}', encoding="utf-8")
    with pytest.raises(ManifestClosedLoopError, match="pointer"): build_and_publish_snapshot(entries, formal, records_factory=lambda e: _records_for(e), archive_root=store)
def test_restore_requires_exact_member_set(tmp_path):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = [ChapterEntry(81, "卷六·论命", "u1"), ChapterEntry(82, "卷六·论人", "u2")]
    formal = tmp_path / "formal"; store = tmp_path / "store"
    build_and_publish_snapshot(entries, formal, records_factory=lambda e: _records_for(e), archive_root=store)
    sha = read_active_snapshot(formal)["snapshot_sha256"]
    snap_dir = formal / "source_snapshots" / sha
    # P0-1：构造真正多余成员（raw_083.html 不在 manifest），并同步更新 pointer/manifest 及 active pointer 的 SHA，
    # 确保上游身份门（active pointer -> manifest SHA -> archive pointer SHA）全部通过，member set 校验失败
    data = build_canonical_tar({"responses/raw_081.html": b"B", "responses/raw_082.html": b"B", "responses/raw_083.html": b"B"})
    tampered_uri = str(store / f"tampered_{hashlib.sha256(data).hexdigest()[:8]}.tar")
    Path(tampered_uri).write_bytes(data)
    ptr = json.loads((snap_dir / "RESPONSE_ARCHIVE_POINTER.json").read_text(encoding="utf-8"))
    ptr["archive_sha256"] = hashlib.sha256(data).hexdigest(); ptr["archive_size"] = len(data); ptr["response_count"] = 3; ptr["archive_uri"] = tampered_uri
    (snap_dir / "RESPONSE_ARCHIVE_POINTER.json").write_text(json.dumps(ptr, ensure_ascii=False, indent=2), encoding="utf-8")
    man = json.loads((snap_dir / "source_manifest.json").read_text(encoding="utf-8"))
    man["response_archive_pointer_sha256"] = hashlib.sha256((snap_dir / "RESPONSE_ARCHIVE_POINTER.json").read_bytes()).hexdigest()
    (snap_dir / "source_manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    # P0-6：同步更新 active pointer 的 manifest SHA，使上游身份门通过
    (formal / "active_source_snapshot.json").write_text(json.dumps({"snapshot_sha256": sha, "source_manifest_sha256": hashlib.sha256((snap_dir / "source_manifest.json").read_bytes()).hexdigest()}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ManifestClosedLoopError, match="member set"): restore_responses(formal, sha, archive_root=store)
def test_restore_idempotent_skip_when_consistent(tmp_path):
    # 中优：restore 幂等——已一致则跳过，重复调用不失败
    formal, store, sha = _publish_one(tmp_path)
    restore_responses(formal, sha, archive_root=store)
    assert materialization_status(formal, sha) == "materialized"
    restore_responses(formal, sha, archive_root=store)
    assert materialization_status(formal, sha) == "materialized"
def test_restore_rejects_active_pointer_drift(tmp_path):
    # P0-6：active pointer 的 manifest SHA 漂移 -> 拒绝（上游身份门）
    formal, store, sha = _publish_one(tmp_path)
    act = json.loads((formal / "active_source_snapshot.json").read_text(encoding="utf-8"))
    act["source_manifest_sha256"] = "0" * 64
    (formal / "active_source_snapshot.json").write_text(json.dumps(act, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ManifestClosedLoopError, match="active pointer"): restore_responses(formal, sha, archive_root=store)
def test_restore_rejects_active_pointer_drift_after_materialized(tmp_path):
    # P0-1：已物化后篡改 active pointer，再次 restore 也必须拒绝（闭环校验在幂等 return 之前）
    formal, store, sha = _publish_one(tmp_path)
    restore_responses(formal, sha, archive_root=store)
    assert materialization_status(formal, sha) == "materialized"
    act = json.loads((formal / "active_source_snapshot.json").read_text(encoding="utf-8"))
    act["source_manifest_sha256"] = "0" * 64
    (formal / "active_source_snapshot.json").write_text(json.dumps(act, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ManifestClosedLoopError, match="active pointer"): restore_responses(formal, sha, archive_root=store)
def test_restore_atomic_no_partial_on_failure(tmp_path, monkeypatch):
    formal, store, sha = _publish_one(tmp_path)
    snap_dir = formal / "source_snapshots" / sha
    def _boom(*a, **k): raise OSError("disk full")
    monkeypatch.setattr("scripts.fetch_sanming_chapters.os.replace", _boom)
    with pytest.raises(OSError): restore_responses(formal, sha, archive_root=store)
    assert not (snap_dir / "responses").exists() and not (snap_dir / "responses.tmp").exists()
def test_restore_rejects_unsafe_member(tmp_path):
    from scripts.fetch_sanming_chapters import _safe_member_name
    for bad in ("../evil", "responses/../evil", "/abs", "responses\\raw.html", "other/x"):
        with pytest.raises(ManifestClosedLoopError): _safe_member_name(bad)
    assert _safe_member_name("responses/raw_081.html") == "raw_081.html"
```

RED → GREEN → 提交。

---

## 阶段 5：双层账本 + BudgetCtx + 完整持久化/校验（完整实现）

`scripts/distill_lib.py`：

```python
from __future__ import annotations
import dataclasses, json, os, hashlib, time, subprocess as _subprocess
from pathlib import Path
from scripts.classic_artifacts import EXPERIMENT_ID

def _pid_alive(pid) -> bool:
    if pid is None or pid <= 0: return False
    if os.name == "nt":
        r = _subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
        return "No tasks" not in r.stdout
    try: os.kill(pid, 0); return True
    except OSError: return False

class FileLock:
    def __init__(self, path, lease=3600): self.path = Path(path); self.lease = lease; self._held = False
    def __enter__(self):
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "start": time.time(), "owner": f"p{os.getpid()}t{time.time():.0f}"}).encode())
                os.close(fd); self._held = True; return self
            except FileExistsError:
                if self._stale(): os.unlink(str(self.path)); continue
                raise RuntimeError(f"lock held by live writer: {self.path}")
    def __exit__(self, *a):
        if self._held: os.unlink(str(self.path)); self._held = False
    def _stale(self) -> bool:
        try: meta = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: return False
        return time.time() - meta.get("start", 0) > self.lease and not _pid_alive(meta.get("pid", -1)) and str(meta.get("owner", "")).startswith("p")

@dataclasses.dataclass(frozen=True)
class BudgetCtx:
    run_id: str; batch_id: str; proj: "ProjectLedger"; run: "BudgetLedger"; proj_path: Path; run_path: Path

def attempt_base_id(*, run_id, batch_id, chapter_id, segment_id, operation, rule_id) -> str:
    return hashlib.sha256(json.dumps({"run_id": run_id, "batch_id": batch_id, "chapter_id": chapter_id, "segment_id": segment_id, "operation": operation, "rule_id": rule_id}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

def attempt_id_for(*, run_id, batch_id, chapter_id, segment_id, operation, rule_id, attempt_no) -> str:
    return hashlib.sha256(json.dumps({"run_id": run_id, "batch_id": batch_id, "chapter_id": chapter_id, "segment_id": segment_id, "operation": operation, "rule_id": rule_id, "attempt_no": attempt_no}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

def next_attempt_no(run, *, base_id, proj=None):
    """P0-4：跳过 project 已 reservation 的 attempt number，防止 orphan 死锁。"""
    run_used = max((st.get("attempt_no", 0) for st in run.attempts.values() if st.get("base_id") == base_id), default=0)
    if proj is None: return run_used + 1
    proj_used = 0
    for r in proj.reservations.values():
        m = r.get("metadata") or {}
        if not isinstance(m, dict): continue
        try:
            b = attempt_base_id(run_id=m["run_id"], batch_id=m["batch_id"], chapter_id=m["chapter_id"], segment_id=m["segment_id"], operation=m["operation"], rule_id=m["rule_id"])
        except Exception:
            continue
        if b == base_id:
            proj_used = max(proj_used, int(m.get("attempt_no", 0)))
    return max(run_used, proj_used) + 1

ALREADY_RESERVED = object()
_TERMINAL_STATES = ("success", "failed", "interrupted")
_ATTEMPT_STATUSES = ("attempted",) + _TERMINAL_STATES

def _ledger_hash(state: dict) -> str:
    s = dict(state); s.pop("ledger_hash", None)
    return hashlib.sha256(json.dumps(s, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

def _validate_ledger_state(data) -> None:
    if not isinstance(data, dict): raise LedgerCorruptionError("ledger not a dict")
    if data.get("ledger_hash") != _ledger_hash(data): raise LedgerCorruptionError("ledger hash mismatch (self-consistent tamper detected)")

def _atomic_write_json(path, obj):
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))

def _validate_attempt_metadata(m) -> None:
    if not isinstance(m, dict): raise LedgerCorruptionError("attempt metadata not a dict")
    # P0-2：metadata 必须持久化 run_id/batch_id，project 层才能逐条复算 attempt_id
    for k in ("operation", "chapter_id", "segment_id", "rule_id", "attempt_no", "run_id", "batch_id"):
        if k not in m: raise LedgerCorruptionError(f"attempt metadata missing {k}")
    if not isinstance(m["attempt_no"], int) or m["attempt_no"] < 1: raise LedgerCorruptionError("attempt metadata attempt_no invalid")

def _verify_attempt_id(run_id, batch_id, attempt_id, metadata) -> None:
    recomputed = attempt_id_for(run_id=run_id, batch_id=batch_id, chapter_id=metadata["chapter_id"], segment_id=metadata["segment_id"], operation=metadata["operation"], rule_id=metadata["rule_id"], attempt_no=metadata["attempt_no"])
    if recomputed != attempt_id: raise LedgerCorruptionError(f"attempt_id {attempt_id} does not bind metadata (expected {recomputed})")

def _validate_run_attempts(run_id, attempts) -> None:
    if not isinstance(attempts, dict): raise LedgerCorruptionError("attempts not a dict")
    for att_id, st in attempts.items():
        if not isinstance(st, dict): raise LedgerCorruptionError(f"attempt {att_id} not a dict")
        if st.get("status") not in _ATTEMPT_STATUSES: raise LedgerCorruptionError(f"attempt {att_id} invalid status {st.get('status')!r}")
        if not isinstance(st.get("attempt_no"), int) or st.get("attempt_no", 0) < 1: raise LedgerCorruptionError(f"attempt {att_id} invalid attempt_no")
        if not isinstance(st.get("base_id"), str) or len(st.get("base_id", "")) != 64: raise LedgerCorruptionError(f"attempt {att_id} invalid base_id")
        meta = st.get("metadata")
        if meta is None: raise LedgerCorruptionError(f"attempt {att_id} metadata must not be None")
        _validate_attempt_metadata(meta)
        _verify_attempt_id(run_id, st.get("batch_id", ""), att_id, meta)
        recomputed_base = attempt_base_id(run_id=run_id, batch_id=st.get("batch_id", ""), chapter_id=meta["chapter_id"], segment_id=meta["segment_id"], operation=meta["operation"], rule_id=meta["rule_id"])
        if recomputed_base != st.get("base_id"): raise LedgerCorruptionError(f"attempt {att_id} base_id does not bind metadata")

def verify_attempt_metadata_consistency(proj, run, attempt_id) -> None:
    pr = proj.reservations.get(attempt_id); ra = run.attempts.get(attempt_id)
    if pr is None or ra is None: return
    _validate_attempt_metadata(pr.get("metadata")); _validate_attempt_metadata(ra.get("metadata"))
    if pr.get("metadata") != ra.get("metadata"): raise LedgerCorruptionError(f"attempt metadata mismatch for {attempt_id}")

class LedgerCorruptionError(RuntimeError):
    pass

class ProjectLedger:
    def __init__(self, experiment_id, total_cap, calls_made=0, reservations=None):
        self.experiment_id = experiment_id; self.total_cap = total_cap; self.calls_made = calls_made; self.reservations = reservations or {}

    @classmethod
    def load_or_create(cls, path, experiment_id, total_cap):
        if path and os.path.exists(path):
            try: data = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception as e: raise LedgerCorruptionError(f"project ledger JSON unparseable: {e}") from e
            _validate_ledger_state(data)
            if data.get("experiment_id") != experiment_id: raise ValueError("project ledger experiment_id mismatch")
            if data.get("total_cap") != total_cap: raise LedgerCorruptionError(f"project ledger cap mismatch: stored={data.get('total_cap')}, requested={total_cap}")
            if not isinstance(data.get("calls_made"), int) or data["calls_made"] < 0: raise LedgerCorruptionError("project calls_made invalid")
            if not isinstance(data.get("reservations"), dict): raise LedgerCorruptionError("project reservations not a dict")
            if data["calls_made"] != len(data["reservations"]): raise LedgerCorruptionError("project calls_made != len(reservations)")
            for att_id, r in data["reservations"].items():
                if not isinstance(r, dict): raise LedgerCorruptionError(f"reservation {att_id} not a dict")
                if r.get("metadata") is None: raise LedgerCorruptionError(f"reservation {att_id} metadata must not be None")
                _validate_attempt_metadata(r.get("metadata"))
                # P0-2：逐条复算 attempt_id（metadata 内含 run_id/batch_id），ID 不匹配即 corruption
                _verify_attempt_id(r.get("metadata")["run_id"], r.get("metadata")["batch_id"], att_id, r.get("metadata"))
            return cls(experiment_id, total_cap, data["calls_made"], data.get("reservations"))
        return cls(experiment_id, total_cap)

    def _state(self): return {"experiment_id": self.experiment_id, "total_cap": self.total_cap, "calls_made": self.calls_made, "reservations": self.reservations}
    def _persist(self, path): state = self._state(); state["ledger_hash"] = _ledger_hash(state); _atomic_write_json(path, state)

    def before_call(self, attempt_id, path, metadata=None):
        if metadata is None: raise LedgerCorruptionError("project metadata must not be None")
        _validate_attempt_metadata(metadata)
        # P0-2：复算 attempt_id 并校验（metadata 内含 run_id/batch_id），防篡改 reservation key 复用
        _verify_attempt_id(metadata["run_id"], metadata["batch_id"], attempt_id, metadata)
        with FileLock(str(path) + ".lock"):
            fresh = self.load_or_create(path, self.experiment_id, self.total_cap)
            existing = fresh.reservations.get(attempt_id)
            if existing is not None:
                if existing.get("metadata") != metadata: raise LedgerCorruptionError(f"project duplicate attempt metadata mismatch for {attempt_id}")
                return ALREADY_RESERVED
            if fresh.calls_made + 1 > fresh.total_cap: raise RuntimeError("project budget exhausted")
            fresh.calls_made += 1
            fresh.reservations[attempt_id] = {"status": "reserved", "metadata": metadata}
            fresh._persist(path); self.__dict__.update(fresh.__dict__); return None

    def remaining(self): return self.total_cap - self.calls_made

class BudgetLedger:
    def __init__(self, global_hard_cap, persist_path=None, run_id="", code_sha="", rules_sha="", attempts=None):
        self.global_hard_cap = global_hard_cap
        self.persist_path = Path(persist_path) if persist_path else None
        self.run_id = run_id; self.code_sha = code_sha; self.rules_sha = rules_sha
        self.calls_made = 0; self.accepted = 0; self.skipped = 0; self.exhausted = 0
        # P0-3：budget-ctx 调用只经 before_call（attempts 与 calls_made 同步原子递增）；
        # legacy 路径只经 record_call（仅累加 legacy_calls），二者不混，守恒校验才可成立。
        self.legacy_calls = 0
        self.attempts = attempts or {}

    def _state(self):
        return {"global_hard_cap": self.global_hard_cap, "calls_made": self.calls_made, "accepted": self.accepted, "skipped": self.skipped, "exhausted": self.exhausted, "run_id": self.run_id, "code_sha": self.code_sha, "rules_sha": self.rules_sha, "legacy_calls": self.legacy_calls, "attempts": self.attempts}

    @classmethod
    def load_or_create(cls, path, global_hard_cap, run_id="", code_sha="", rules_sha=""):
        if path and os.path.exists(path):
            try: data = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception as e: raise LedgerCorruptionError(f"run ledger JSON unparseable: {e}") from e
            _validate_ledger_state(data)
            if data["run_id"] != run_id or data["code_sha"] != code_sha or data["rules_sha"] != rules_sha: raise LedgerCorruptionError("run ledger identity drift")
            if data["global_hard_cap"] != global_hard_cap: raise LedgerCorruptionError("run ledger cap mismatch")
            if not isinstance(data["calls_made"], int) or data["calls_made"] < 0: raise LedgerCorruptionError("run calls_made invalid")
            for k in ("accepted", "skipped", "exhausted", "legacy_calls"):
                if not isinstance(data.get(k, 0), int) or data.get(k, 0) < 0: raise LedgerCorruptionError(f"run {k} invalid")
            attempts = data.get("attempts", {})
            _validate_run_attempts(run_id, attempts)
            if data["calls_made"] != len(attempts): raise LedgerCorruptionError("run calls_made != len(attempts)")
            led = cls(global_hard_cap, persist_path=path, run_id=run_id, code_sha=code_sha, rules_sha=rules_sha, attempts=attempts)
            led.calls_made = data["calls_made"]; led.accepted = data.get("accepted", 0); led.skipped = data.get("skipped", 0); led.exhausted = data.get("exhausted", 0); led.legacy_calls = data.get("legacy_calls", 0)
            return led
        return cls(global_hard_cap, persist_path=path, run_id=run_id, code_sha=code_sha, rules_sha=rules_sha)

    def save(self):
        if self.persist_path is None: return
        data = self._state(); data["ledger_hash"] = _ledger_hash(data)
        tmp = self.persist_path.parent / f".{self.persist_path.name}.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try: tmp.replace(self.persist_path)
        except Exception: tmp.unlink(missing_ok=True); raise

    def _locked_mutate(self, path, mutate):
        with FileLock(str(path or self.persist_path) + ".lock"):
            fresh = BudgetLedger.load_or_create(path or self.persist_path, self.global_hard_cap, self.run_id, self.code_sha, self.rules_sha)
            mutate(fresh)
            if path: data = fresh._state(); data["ledger_hash"] = _ledger_hash(data); _atomic_write_json(path, data)
            else: fresh.save()
            self.__dict__.update(fresh.__dict__)

    def record_attempt(self, attempt_id, path=None, base_id=None, attempt_no=None, metadata=None, batch_id=""):
        # P0-3：run 侧唯一注册入口（合并原 before_call）——原子登记 attempt + 累加 calls_made + hard-cap 检查（含 legacy_calls）
        if metadata is None: raise LedgerCorruptionError("run metadata must not be None")
        _validate_attempt_metadata(metadata); _verify_attempt_id(self.run_id, batch_id, attempt_id, metadata)
        def _m(fresh):
            existing = fresh.attempts.get(attempt_id)
            if existing is not None:
                if existing.get("status") in _TERMINAL_STATES: raise LedgerCorruptionError(f"record_attempt after terminal for {attempt_id}")
                if existing.get("metadata") != metadata: raise LedgerCorruptionError(f"run record_attempt metadata mismatch for {attempt_id}")
                return   # 幂等：同 metadata 且未 terminal，不再重复计数
            if fresh.calls_made + fresh.legacy_calls + 1 > fresh.global_hard_cap: raise RuntimeError("run budget exhausted")
            fresh.attempts[attempt_id] = {"status": "attempted", "base_id": base_id, "batch_id": batch_id, "attempt_no": attempt_no, "metadata": metadata}
            fresh.calls_made += 1
        self._locked_mutate(path, _m)

    def record_terminal(self, attempt_id, status, path=None):
        if status not in _TERMINAL_STATES: raise LedgerCorruptionError(f"invalid terminal status {status!r}")
        def _m(fresh):
            existing = fresh.attempts.get(attempt_id)
            if existing is None: raise LedgerCorruptionError(f"terminal for missing attempt {attempt_id}")
            if existing.get("status") in _TERMINAL_STATES: raise LedgerCorruptionError(f"terminal re-transition for {attempt_id}: {existing['status']} -> {status}")
            existing["status"] = status; fresh.attempts[attempt_id] = existing
        self._locked_mutate(path, _m)

    def record_call(self, path=None):
        """P0-5：legacy 路径弃用——改用 before_legacy_call 锁内原子 cap 检查。保留为兼容桩，新代码不用。"""
        self.before_legacy_call(path=path)

    def before_legacy_call(self, path=None):
        """P0-5：legacy 路径原子 cap 检查 + 计数（同一锁内，无 TOCTOU）。"""
        def _m(fresh):
            if fresh.calls_made + fresh.legacy_calls + 1 > fresh.global_hard_cap: raise RuntimeError("run budget exhausted")
            fresh.legacy_calls += 1
        self._locked_mutate(path, _m)
    # P0-2：单一 can_call，合并 budget-ctx 与 legacy 计数
    def can_call(self): return self.calls_made + self.legacy_calls < self.global_hard_cap

    def record_accept(self, path=None):
        def _m(fresh): fresh.accepted += 1
        self._locked_mutate(path, _m)
    def record_skip(self, path=None):
        def _m(fresh): fresh.skipped += 1
        self._locked_mutate(path, _m)
    def has_terminal(self, attempt_id): return self.attempts.get(attempt_id, {}).get("status") in _TERMINAL_STATES

def call_with_budget(fn, *, proj, run, attempt_id, project_path, run_path=None, base_id=None, attempt_no=None, metadata=None, batch_id=""):
    if metadata is None: raise LedgerCorruptionError("metadata must not be None")
    _validate_attempt_metadata(metadata)
    # P0-3：run 侧统一走 record_attempt（原子登记 + cap 检查），不再单列 before_call
    if proj.before_call(attempt_id, path=project_path, metadata=metadata) == ALREADY_RESERVED: raise RuntimeError("duplicate attempt_id: refusing external call")
    run.record_attempt(attempt_id, path=run_path, base_id=base_id, attempt_no=attempt_no, metadata=metadata, batch_id=batch_id)
    try: out = fn()
    except Exception as e: run.record_terminal(attempt_id, "failed", path=run_path); raise
    run.record_terminal(attempt_id, "success", path=run_path)
    return out

def reserved_unattributed(proj, run): return set(proj.reservations) - set(run.attempts)
def interrupted_unknown(run): return {a for a, st in run.attempts.items() if st.get("status") == "attempted"}
```

阶段 5 测试（`tests/test_classic_distillation_remediation.py`）：`_meta`/`_att` helper、EXPERIMENT_ID 冻结、attempt ID canonical SHA、cap drift、metadata 完整保留、duplicate 一致/不一致、tamper、run record_attempt 原子/cap/duplicate、record_attempt 前/后 terminal、terminal 状态机、hard cap 包装器、metadata 一致性、跨进程恢复、锁并发/陈旧、orphan、self-consistent tamper（用 `attempt_id_for`/`attempt_base_id`）、metadata None 拒绝（run.record_attempt/project.before_call/load_or_create）。新增：

```python
# P0-2：project 层逐条复算 attempt_id，伪造 reservation key + 自洽 hash -> corruption
def test_project_recomputes_attempt_id_on_load(tmp_path):
    p = tmp_path / "project.json"
    proj = ProjectLedger.load_or_create(p, experiment_id=EXPERIMENT_ID, total_cap=100)
    m = _meta(attempt_no=1)
    m.update({"run_id": "R", "batch_id": "B"})
    att = attempt_id_for(run_id="R", batch_id="B", chapter_id=1, segment_id=0, operation="rules", rule_id=None, attempt_no=1)
    proj.before_call(att, path=p, metadata=m)
    data = json.loads(p.read_text(encoding="utf-8"))
    data["reservations"]["forged"] = data["reservations"].pop(att)   # 篡改 key
    data["ledger_hash"] = _ledger_hash(data)                          # 重算自洽 hash
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(LedgerCorruptionError): ProjectLedger.load_or_create(p, experiment_id=EXPERIMENT_ID, total_cap=100)

# P0-3：legacy record_call 只累加 legacy_calls，不破坏 calls_made == len(attempts) 守恒
def test_legacy_record_call_does_not_break_conservation(tmp_path):
    r = BudgetLedger.load_or_create(tmp_path / "run.json", global_hard_cap=100, run_id="R", code_sha="c", rules_sha="r")
    r.record_call(path=tmp_path / "run.json"); r.record_call(path=tmp_path / "run.json")
    r2 = BudgetLedger.load_or_create(tmp_path / "run.json", global_hard_cap=100, run_id="R", code_sha="c", rules_sha="r")
    assert r2.legacy_calls == 2 and r2.calls_made == 0 and len(r2.attempts) == 0
    assert r2.can_call() is True   # 合并计数仍受 hard cap 约束（global_hard_cap=100）

# P0-5：legacy hard cap 临界值——锁内原子 before_legacy_call 是权威门禁
def test_legacy_hard_cap_enforced(tmp_path):
    r = BudgetLedger.load_or_create(tmp_path / "run.json", global_hard_cap=2, run_id="R", code_sha="c", rules_sha="r")
    r.before_legacy_call(path=tmp_path / "run.json"); r.before_legacy_call(path=tmp_path / "run.json")
    with pytest.raises(RuntimeError, match="budget exhausted"):
        r.before_legacy_call(path=tmp_path / "run.json")
    assert r.legacy_calls == 2
```

RED → GREEN → 提交。

---

## 阶段 6：常量 + retry + 可重试解析 + 分段器 + generate_mcq（完整实现）

`scripts/distill_lib.py` 追加：

```python
MAX_RULES_PER_SEGMENT = 8; MAX_RULE_EXTRACTION_ATTEMPTS = 3; MAX_MCQ_ATTEMPTS_PER_RULE = 3; MAX_PROMPT_CHARS = 8000; MAX_REQUEST_BYTES = 16000

class RuleOverflowError(RuntimeError): pass
class RetryableModelOutputError(RuntimeError): pass

class RetryExhaustedError(RuntimeError):
    """retry 耗尽，保留原始 cause chain；classify_failure_for_resume 遍历 cause 链判断可重试。"""
    def __init__(self, message, cause=None):
        super().__init__(message)
        self.cause = cause

def sha256_bytes(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

def safe_batch_hard_cap(total_segments, max_rule_extraction_attempts, max_rules_per_segment, max_mcq_attempts_per_rule) -> int:
    return total_segments * max_rule_extraction_attempts + total_segments * max_rules_per_segment * max_mcq_attempts_per_rule

def enforce_budget_before_call(n_rules, operation):
    if operation == "rules" and n_rules > MAX_RULES_PER_SEGMENT: raise RuleOverflowError(f"segment returned {n_rules} rules > {MAX_RULES_PER_SEGMENT}")

def _parse_rules_retryable(response):
    try: data = json.loads(response) if isinstance(response, str) else None
    except Exception as e: raise RetryableModelOutputError(f"rules JSON unparseable: {e}") from e
    if not isinstance(data, list): raise RetryableModelOutputError("rules output not a list")
    if not data: raise RetryableModelOutputError("rules output empty")
    if len(data) > MAX_RULES_PER_SEGMENT: raise RetryableModelOutputError(f"rules count {len(data)} > {MAX_RULES_PER_SEGMENT}")
    for i, r in enumerate(data):
        if not isinstance(r, dict): raise RetryableModelOutputError(f"rule {i} not a dict")
        for k in ("rule", "condition", "subject", "original_text"):
            v = r.get(k)
            if not isinstance(v, str) or not v.strip(): raise RetryableModelOutputError(f"rule {i} field {k} must be non-empty string")
    return data

def _parse_mcq_retryable(response):
    try: obj = json.loads(response) if isinstance(response, str) else None
    except Exception as e: raise RetryableModelOutputError(f"mcq JSON unparseable: {e}") from e
    if not isinstance(obj, dict): raise RetryableModelOutputError("mcq output not a dict")
    if not isinstance(obj.get("question"), str) or not obj["question"].strip(): raise RetryableModelOutputError("mcq question must be non-empty string")
    opts = obj.get("options")
    if not isinstance(opts, dict): raise RetryableModelOutputError("mcq options must be an object")
    if set(opts.keys()) != {"A", "B", "C", "D"}: raise RetryableModelOutputError("mcq options must be exactly A/B/C/D")
    for k in ("A", "B", "C", "D"):
        if not isinstance(opts.get(k), str) or not opts[k].strip(): raise RetryableModelOutputError(f"mcq option {k} must be non-empty string")
    answer = obj.get("answer")
    if answer not in ("A", "B", "C", "D"): raise RetryableModelOutputError("mcq answer must be A/B/C/D")
    if not isinstance(obj.get("explanation"), str) or not obj["explanation"].strip(): raise RetryableModelOutputError("mcq explanation must be non-empty string")
    return obj

def is_retryable_error(e) -> bool:
    if isinstance(e, RetryableModelOutputError): return True
    if isinstance(e, (ConnectionError, TimeoutError)): return True
    msg = str(e).lower()
    return "network down" in msg or "timeout" in msg or "rate limit" in msg or "429" in msg or "temporarily unavailable" in msg or "connection" in msg

def retry_call_with_budget(fn, *, proj, run, run_id, batch_id, chapter_id, segment_id, operation, rule_id, base_id, max_attempts, project_path, run_path=None):
    start = next_attempt_no(run, base_id=base_id, proj=proj)   # P0-4：跳过 project 已 reservation 的 attempt number
    if start > max_attempts: raise RetryExhaustedError("attempts exhausted")
    last = None
    for attempt_no in range(start, max_attempts + 1):
        att = attempt_id_for(run_id=run_id, batch_id=batch_id, chapter_id=chapter_id, segment_id=segment_id, operation=operation, rule_id=rule_id, attempt_no=attempt_no)
        # P0-2：metadata 持久化 run_id/batch_id，project 层才能复算 attempt_id
        meta = {"operation": operation, "chapter_id": chapter_id, "segment_id": segment_id, "rule_id": rule_id, "attempt_no": attempt_no, "run_id": run_id, "batch_id": batch_id}
        try:
            return call_with_budget(fn, proj=proj, run=run, attempt_id=att, project_path=project_path, run_path=run_path, base_id=base_id, batch_id=batch_id, attempt_no=attempt_no, metadata=meta)
        except Exception as e:
            if not is_retryable_error(e): raise
            if attempt_no >= max_attempts: raise RetryExhaustedError("attempts exhausted") from e
            last = e
    raise RetryExhaustedError("attempts exhausted") from last

import dataclasses, re

@dataclasses.dataclass(frozen=True)
class PromptLimits:
    max_prompt_chars: int = MAX_PROMPT_CHARS
    max_request_bytes: int = MAX_REQUEST_BYTES

class PromptLimitError(RuntimeError): pass

@dataclasses.dataclass(frozen=True)
class Segment:
    text: str; char_start: int; char_end: int; segment_index: int

def render_rule_prompt(text, book, chapter):
    return (RULE_PROMPT.replace("__BOOK__", book).replace("__CH__", chapter).replace("__TEXT__", text))

def validate_segment(text, *, book, chapter, limits):
    prompt = render_rule_prompt(text, book, chapter)
    if len(text) > limits.max_prompt_chars: raise PromptLimitError(f"segment text {len(text)} > {limits.max_prompt_chars} chars")
    if len(prompt) > limits.max_prompt_chars: raise PromptLimitError(f"prompt {len(prompt)} > {limits.max_prompt_chars} chars")
    if len(prompt.encode("utf-8")) > limits.max_request_bytes: raise PromptLimitError(f"prompt bytes {len(prompt.encode('utf-8'))} > {limits.max_request_bytes}")

def _validate_ok(text, book, chapter, limits):
    try: validate_segment(text, book=book, chapter=chapter, limits=limits); return True
    except PromptLimitError: return False

def _split_to_max_prefix(part, book, chapter, limits) -> list[str]:
    if _validate_ok(part, book, chapter, limits): return [part]
    pieces = re.split(r"(?<=[。？！；])", part)
    if len(pieces) <= 1:
        lo, hi = 0, len(part)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _validate_ok(part[:mid], book, chapter, limits): lo = mid
            else: hi = mid - 1
        if lo <= 0: raise PromptLimitError("single char exceeds limits")
        return [part[:lo]] + _split_to_max_prefix(part[lo:], book, chapter, limits)
    out, cur = [], ""
    for piece in pieces:
        if not piece: continue
        if _validate_ok(cur + piece, book, chapter, limits): cur += piece
        else:
            if cur: out.append(cur); cur = ""
            out.extend(_split_to_max_prefix(piece, book, chapter, limits))
    if cur: out.append(cur)
    return out

def segment_chapter(text, *, book, chapter, limits):
    parts = _split_to_max_prefix(text, book, chapter, limits)
    segs, start = [], 0
    for i, part in enumerate(parts):
        segs.append(Segment(text=part, char_start=start, char_end=start + len(part), segment_index=i)); start += len(part)
    if start != len(text) or "".join(s.text for s in segs) != text: raise PromptLimitError("segmentation conservation violated")
    return segs

def distill_segments(segments, *, book, chapter, limits, ledger=None, budget_ctx=None, chapter_id=0):
    all_rules = []
    for seg in segments:
        validate_segment(seg.text, book=book, chapter=chapter, limits=limits)
        rules = distill_chapter(seg.text, book, chapter, ledger=ledger, budget_ctx=budget_ctx, segment_id=seg.segment_index, chapter_id=chapter_id)
        enforce_budget_before_call(len(rules), "rules")
        for r in rules: r["segment_index"] = seg.segment_index
        all_rules.extend(rules)
    return all_rules

def distill_chapter(text, book, chapter, ledger=None, *, budget_ctx=None, segment_id=0, chapter_id=0):
    prompt = render_rule_prompt(text, book, chapter)
    if budget_ctx is None:
        if ledger is not None:
            try: ledger.before_legacy_call()   # P0-5：锁内原子 cap 检查 + 计数
            except RuntimeError: return []
        try: rules = _parse_rules_retryable(_call(prompt))
        except RetryableModelOutputError: return []
    else:
        rules = retry_call_with_budget(
            lambda: _parse_rules_retryable(_call(prompt)),
            proj=budget_ctx.proj, run=budget_ctx.run, run_id=budget_ctx.run_id, batch_id=budget_ctx.batch_id,
            chapter_id=chapter_id, segment_id=segment_id, operation="rules", rule_id=None,
            base_id=attempt_base_id(run_id=budget_ctx.run_id, batch_id=budget_ctx.batch_id, chapter_id=chapter_id, segment_id=segment_id, operation="rules", rule_id=None),
            max_attempts=MAX_RULE_EXTRACTION_ATTEMPTS, project_path=budget_ctx.proj_path, run_path=budget_ctx.run_path)
    for r in rules:
        r.setdefault("source_book", book); r.setdefault("source_chapter", chapter); r.setdefault("category", "classic"); r.pop("id", None)
    return rules

def generate_mcq(rules, book, chapter, max_calls=100, max_retries=2, stats=None, ledger=None, *, budget_ctx=None, chapter_id=0):
    if not rules: return [], []
    verified, unaudited = [], []
    calls_made, skipped = 0, 0
    max_calls_hit = False
    for r in rules:
        rid = r.get("id", "")
        if not rid: continue
        rule_payload = json.dumps({"subject": r.get("subject", ""), "condition": r.get("condition", ""), "rule": r.get("rule", ""), "original_text": r.get("original_text", "")}, ensure_ascii=False, indent=2)
        prompt = PER_RULE_MCQ_PROMPT.replace("__RULE__", rule_payload)
        obj: dict | None = None
        if budget_ctx is not None:
            base = attempt_base_id(run_id=budget_ctx.run_id, batch_id=budget_ctx.batch_id, chapter_id=chapter_id, segment_id=-1, operation="mcq", rule_id=rid)
            try:
                obj = retry_call_with_budget(lambda _p=prompt: _parse_mcq_retryable(_call(_p, timeout=120)), proj=budget_ctx.proj, run=budget_ctx.run, run_id=budget_ctx.run_id, batch_id=budget_ctx.batch_id, chapter_id=chapter_id, segment_id=-1, operation="mcq", rule_id=rid, base_id=base, max_attempts=MAX_MCQ_ATTEMPTS_PER_RULE, project_path=budget_ctx.proj_path, run_path=budget_ctx.run_path)
            except RetryExhaustedError as e:
                raise RetryableModelOutputError(f"mcq attempts exhausted for rule {rid}") from e
        else:
            # P0-2：不预扣——每个真实 attempt 只在紧邻 _call 前原子扣账一次（before_legacy_call）
            if ledger is None and calls_made >= max_calls: max_calls_hit = True; skipped += 1; continue
            last_err = None
            for _attempt_i in range(max_retries + 1):
                if ledger is not None:
                    try: ledger.before_legacy_call()
                    except RuntimeError: max_calls_hit = True; break
                else:
                    if calls_made >= max_calls: max_calls_hit = True; break
                    calls_made += 1
                try:
                    obj = _parse_mcq_retryable(_call(prompt, timeout=120)); last_err = None; break
                except Exception as e:
                    last_err = e
                    if not is_retryable_error(e): break
                    continue
            if last_err is not None:
                skipped += 1
                if ledger is not None: ledger.record_skip()
                continue
        if obj is None: skipped += 1; continue
        if not _mcq_prefilter(obj, r): skipped += 1; continue
        obj["source_rule_id"] = rid; obj.pop("id", None)
        if _mcq_strict_consistency(obj, r):
            obj["_consistency_verified"] = True; verified.append(obj)
        else:
            obj["_consistency_verified"] = False; obj["_audit_reason"] = "semantic_unaudited"; unaudited.append(obj)
    if stats is not None:
        stats["calls_made"] = calls_made if ledger is None else ledger.calls_made
        stats["accepted"] = len(verified); stats["unaudited"] = len(unaudited); stats["skipped"] = skipped; stats["max_calls_hit"] = max_calls_hit
    return verified, unaudited
```

> 注：`RULE_PROMPT`/`PER_RULE_MCQ_PROMPT`/`MCQ_PROMPT`/`_call`/`_mcq_prefilter`/`_mcq_strict_consistency` 均为 `distill_lib.py` 既有实现（本计划不重写）。`sha256_file`/`ledger_code_files`/`assign_mcq_ids` 亦为既有实现。

阶段 6 测试：max 常量冻结、safe_batch_hard_cap、overflow、分段守恒、prompt 字符上限、非静默截断、rules/mcq 可重试解析、is_retryable_error、retry 最后不可重试原样抛、generate_mcq 耗尽阻断、legacy max_retries 输出失败重试、legacy 网络错误重试。新增 P0-4：

```python
# P0-4：retry 耗尽抛 RetryExhaustedError 且保留 cause chain，classify_failure_for_resume 识别为 resume
def test_retry_exhaustion_classified_as_resume(tmp_path, monkeypatch):
    import scripts.distill_lib as dl
    def boom(*a, **k): raise ConnectionError("refused")
    monkeypatch.setattr(dl, "_call", boom)
    proj = ProjectLedger.load_or_create(tmp_path / "p.json", experiment_id=EXPERIMENT_ID, total_cap=100)
    run = BudgetLedger.load_or_create(tmp_path / "r.json", global_hard_cap=50, run_id="R", code_sha="c", rules_sha="r")
    base = attempt_base_id(run_id="R", batch_id="B", chapter_id=1, segment_id=0, operation="rules", rule_id=None)
    with pytest.raises(RetryExhaustedError) as ei:
        retry_call_with_budget(lambda: dl._call("P"), proj=proj, run=run, run_id="R", batch_id="B", chapter_id=1, segment_id=0, operation="rules", rule_id=None, base_id=base, max_attempts=MAX_RULE_EXTRACTION_ATTEMPTS, project_path=tmp_path / "p.json", run_path=tmp_path / "r.json")
    # 中优：对实际捕获的 RetryExhaustedError 执行分类（其 __cause__ 为 ConnectionError -> resume）
    assert classify_failure_for_resume(ei.value, code_sha_before="a"*64, code_sha_now="a"*64) == "resume"
    assert is_retryable_error(ei.value.__cause__) is True

# P0-2：legacy MCQ 单次成功调用只扣账一次（无循环外预扣）
def test_legacy_mcq_single_success_charges_once(tmp_path, monkeypatch):
    import scripts.distill_lib as dl
    ok = {"question": "甲木喜什么？", "options": {"A": "喜水滋润", "B": "火", "C": "土", "D": "金"}, "answer": "A", "explanation": "甲木喜水"}
    monkeypatch.setattr(dl, "_call", lambda *a, **k: json.dumps(ok, ensure_ascii=False))
    run = BudgetLedger.load_or_create(tmp_path / "run.json", global_hard_cap=50, run_id="R", code_sha="c", rules_sha="r")
    rules = [{"id": "smth_080_000", "subject": "甲木", "condition": "生于寅月", "rule": "甲木日主喜水", "original_text": "甲木喜水", "source_book": "sanmingtonghui", "source_chapter": "81", "category": "classic"}]
    verified, _ = dl.generate_mcq(rules, "sanmingtonghui", "81", ledger=run)
    run2 = BudgetLedger.load_or_create(tmp_path / "run.json", global_hard_cap=50, run_id="R", code_sha="c", rules_sha="r")
    assert len(verified) == 1 and run2.legacy_calls == 1   # 单次成功只扣一次
```

RED → GREEN → 提交。

---

## 阶段 7：batch 入口（完整实现 + progress 更新 + 不可回滚）

`scripts/distill_lib.py` 追加（manifest/ID/分类）：

```python
def load_batch_manifest(path):
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    for k in ("schema_version", "batch_id", "selected_chapter_ids", "source_sha_map", "segment_manifest_sha", "pre_run_output_sha", "model_prompt_config_sha", "batch_hard_cap", "parent_commit", "parent_head_sha", "code_sha", "rules_sha", "source_snapshot_sha256", "source_manifest_sha256", "source_archive_pointer_sha256", "experiment_id"):
        if k not in m: raise ValueError(f"batch manifest missing {k}")
    return m

def build_batch_manifest(*, batch_id, selected_chapter_ids, source_sha_map, segment_manifest_sha, pre_run_output_sha, model_prompt_config_sha, batch_hard_cap, parent_commit, parent_head_sha, code_sha, rules_sha, source_snapshot_sha256, source_manifest_sha256, source_archive_pointer_sha256, experiment_id=EXPERIMENT_ID):
    return {"schema_version": "1.0", "batch_id": batch_id, "selected_chapter_ids": selected_chapter_ids, "source_sha_map": source_sha_map, "segment_manifest_sha": segment_manifest_sha, "pre_run_output_sha": pre_run_output_sha, "model_prompt_config_sha": model_prompt_config_sha, "batch_hard_cap": batch_hard_cap, "parent_commit": parent_commit, "parent_head_sha": parent_head_sha, "code_sha": code_sha, "rules_sha": rules_sha, "source_snapshot_sha256": source_snapshot_sha256, "source_manifest_sha256": source_manifest_sha256, "source_archive_pointer_sha256": source_archive_pointer_sha256, "experiment_id": experiment_id}

def _canonical_key(r):
    # P0-5：按已批准设计 sha256(canonical_json({source_book,source_chapter,category,subject,condition,rule,original_text}))，
    # 缺字段 fail-closed（禁止空 key 吞并全部新规则）
    parts = {}
    for k in ("source_book", "source_chapter", "category", "subject", "condition", "rule", "original_text"):
        v = r.get(k)
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"rule missing canonical field {k} (fail-closed, no empty key)")
        parts[k] = v.strip()
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

def canonical_dedup(rules):
    seen, out = set(), []
    for r in rules:
        key = _canonical_key(r)
        r["canonical_key"] = key          # P0-5：key 写回规则
        if key in seen: continue
        seen.add(key); r.setdefault("dedup_origin_segment", r.get("segment_index")); out.append(r)
    return out

def dedup_then_assign_rule_ids(rules, prefix, ch_idx):
    rules.sort(key=lambda r: (r.get("segment_index", 0), r.get("_origin_order", 0)))
    rules[:] = canonical_dedup(rules)
    assign_rule_ids(rules, prefix, ch_idx)   # 复用既有 distill_lib.assign_rule_ids

def backfill_canonical_keys(book_dir: Path) -> None:
    """P0-5：为既有规则补写 canonical_key（不改 ID/顺序/其它字段）。
    legacy 规则缺 source_book/source_chapter/category 时按冻结默认派生：
    source_book='sanmingtonghui'、category='classic'、source_chapter 由 id 推导（0-based ch_idx -> 1-based）。"""
    p = book_dir / "all_rules.json"
    rules = json.loads(p.read_text(encoding="utf-8"))
    for r in rules:
        rid = r.get("id", "")
        if not rid or not re.fullmatch(r"smth_\d{3}_\d{3}", rid): raise ValueError(f"legacy rule missing valid id (fail-closed): {rid!r}")
        r.setdefault("source_book", "sanmingtonghui")
        r.setdefault("source_chapter", str(int(rid.split("_")[1]) + 1))
        r.setdefault("category", "classic")
        r["canonical_key"] = _canonical_key(r)
    tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8"); os.replace(str(tmp), str(p))   # P0-3：原子替换

def classify_failure_for_resume(error, *, code_sha_before, code_sha_now):
    if code_sha_before != code_sha_now: return "abandon"
    if is_retryable_error(error): return "resume"
    # P0-4：遍历 cause chain（RetryExhaustedError.cause 或 __cause__），识别网络故障
    cause = getattr(error, "cause", None) or getattr(error, "__cause__", None)
    seen = 0
    while cause is not None and seen < 5:
        if is_retryable_error(cause): return "resume"
        cause = getattr(cause, "cause", None) or getattr(cause, "__cause__", None); seen += 1
    return "abandon"
```

`scripts/fill_missing_chapters.py`：

```python
from __future__ import annotations
import json, os, re, shutil, hashlib, time
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import distill_lib as dl
import scripts.remediate_classic_distillation as rc
from scripts.distill_lib import _atomic_write_json, EXPERIMENT_ID, sha256_file, sha256_bytes
from scripts.fetch_sanming_chapters import materialization_status, _file_sha256

BASE = ROOT / "knowledge_base" / "classic_texts"
_RECEIPT_OUTPUT_NAMES = ("all_rules.json", "all_mcq.jsonl", "quarantine_mcq.jsonl", "remediation_meta.json", "progress.json")

def load_existing_rule_ids(dir_key: str) -> list[str]:
    p = BASE / dir_key / "all_rules.json"
    if not p.exists(): return []
    return sorted(r.get("id", "") for r in json.loads(p.read_text(encoding="utf-8")) if r.get("id"))

def _output_shas(out_dir: Path) -> dict:
    return {name: sha256_file(out_dir / name) for name in _RECEIPT_OUTPUT_NAMES if (out_dir / name).exists()}

def _seed_staging_from_existing(staging: Path, out_dir: Path) -> None:
    for name in _RECEIPT_OUTPUT_NAMES:
        src = out_dir / name
        if src.exists(): shutil.copy2(src, staging / name)

def _append_rules(staging: Path, rules: list[dict]) -> None:
    p = staging / "all_rules.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    data.extend(rules); p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _append_mcqs(staging: Path, mcqs: list[dict], quarantine: bool = False) -> None:
    name = "quarantine_mcq.jsonl" if quarantine else "all_mcq.jsonl"
    with (staging / name).open("a", encoding="utf-8") as f:
        for m in mcqs: f.write(json.dumps(m, ensure_ascii=False) + "\n")

def _segment_manifest_sha(segs_by_chapter: dict) -> str:
    canon = json.dumps([{"chapter": ch, "segs": [(s.char_start, s.char_end) for s in segs]} for ch, segs in sorted(segs_by_chapter.items())], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256_bytes(canon.encode("utf-8"))

def _model_prompt_config_sha() -> str:
    canon = dl.RULE_PROMPT + "\0" + dl.PER_RULE_MCQ_PROMPT + "\0" + dl.MCQ_PROMPT + f"\0{dl.MAX_PROMPT_CHARS}:{dl.MAX_REQUEST_BYTES}"
    return sha256_bytes(canon.encode("utf-8"))

def _code_sha_now(scripts_dir: Path, root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(dl.ledger_code_files(scripts_dir, root)): h.update(f.read_bytes()); h.update(b"\0")
    return h.hexdigest()

def _git(git_root: Path, *args):
    import subprocess as _sp; return _sp.run(["git", "-C", str(git_root), *args], capture_output=True, text=True)

def _validate_manifest_bindings(m, *, snapshot_dir, out_dir, scripts_dir, root, git_root):
    if m["experiment_id"] != EXPERIMENT_ID: raise ValueError(f"experiment_id mismatch: {m['experiment_id']}")
    for ch in m["selected_chapter_ids"]:
        src = snapshot_dir / f"raw_{ch:03d}.txt"
        if not src.exists(): raise ValueError(f"missing raw for chapter {ch}")
        if sha256_file(src) != m["source_sha_map"].get(str(ch)): raise ValueError(f"source_sha_map mismatch for chapter {ch}")
    if sha256_bytes(json.dumps(_output_shas(out_dir), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) != m["pre_run_output_sha"]: raise ValueError("pre_run_output_sha mismatch")
    r = _git(git_root, "rev-parse", "HEAD")
    if r.returncode != 0 or r.stdout.strip() != m["parent_head_sha"]: raise ValueError("parent_head_sha != git HEAD")
    if _git(git_root, "cat-file", "-e", m["parent_commit"]).returncode != 0: raise ValueError("parent_commit not an existing commit")
    if _code_sha_now(scripts_dir, root) != m["code_sha"]: raise ValueError("code_sha drift vs manifest")

def _validate_snapshot_bindings(m, *, formal_dir, snapshot_dir, snapshot_sha):
    act = json.loads((formal_dir / "active_source_snapshot.json").read_text(encoding="utf-8")) if (formal_dir / "active_source_snapshot.json").exists() else None
    if not act or not act.get("snapshot_sha256") or not act.get("source_manifest_sha256"): raise ValueError("active_source_snapshot.json incomplete")
    if act["snapshot_sha256"] != m["source_snapshot_sha256"]: raise ValueError("active pointer snapshot_sha256 != manifest.source_snapshot_sha256")
    if snapshot_sha != m["source_snapshot_sha256"]: raise ValueError("snapshot_sha param != manifest.source_snapshot_sha256")
    snap_dir = formal_dir / "source_snapshots" / m["source_snapshot_sha256"]
    if not snap_dir.is_dir(): raise ValueError(f"snapshot dir missing: {snap_dir}")
    if _file_sha256(snap_dir / "source_manifest.json") != act["source_manifest_sha256"]: raise ValueError("active pointer source_manifest_sha256 != actual manifest file bytes SHA")
    if _file_sha256(snap_dir / "source_manifest.json") != m["source_manifest_sha256"]: raise ValueError("actual manifest file bytes SHA != manifest.source_manifest_sha256")
    if _file_sha256(snap_dir / "RESPONSE_ARCHIVE_POINTER.json") != m["source_archive_pointer_sha256"]: raise ValueError("source_archive_pointer_sha256 mismatch")
    if snapshot_dir.resolve() != (snap_dir / "extracted").resolve(): raise ValueError("snapshot_dir does not resolve to frozen snapshot extracted/ dir")

def _write_receipt(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); _atomic_write_json(path, obj)

def _rollback_staging(staging: Path) -> None:
    if staging.exists(): shutil.rmtree(staging, ignore_errors=True)

_BACKUP_DIR_RE = re.compile(r"^\.publish_backup_\d+_\d+$")

def _backup_fingerprint(backup_dir: Path) -> dict:
    """P0-3：备份目录内容指纹——成员集 SHA + 各成员内容 SHA 映射 SHA。

    用于把 backup 目录绑定到本 batch：发布时冻结进 completed receipt（收进 completed_receipt_sha256 被 index 认证），
    cleanup 删除前必须与已认证 receipt 冻结的指纹一致，否则合法目录名但属于另一 batch 的备份也会被拒绝。
    """
    if not backup_dir.is_dir():
        return {"member_set_sha256": None, "member_shas_sha256": None, "member_count": 0}
    names = sorted(p.name for p in backup_dir.iterdir())
    member_set_sha = sha256_bytes(json.dumps(names, ensure_ascii=False).encode("utf-8"))
    member_shas = {p.name: sha256_file(p) for p in backup_dir.iterdir() if p.is_file()}
    member_shas_sha = sha256_bytes(json.dumps(member_shas, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return {"member_set_sha256": member_set_sha, "member_shas_sha256": member_shas_sha, "member_count": len(names)}

def _retry_pending_cleanup(receipt_dir: Path, out_dir: Path, *, batch_id: str, genesis_anchor: str,
                           frozen_backup_dir: Path | None, frozen_fingerprint: dict | None) -> str:
    """P0-3：completed_idempotent 入口重试未完成的 cleanup——只删除"已认证 completed receipt 冻结"的备份目录。

    返回清理状态（fail-closed，任何身份/路径/指纹/解析/文件系统失败都不吞掉、不进入 completed_idempotent）：
    - "noop"：无 cleanup_pending（无需清理）；
    - "cleaned"：pending 存在且清理完成（备份已删除 / 或删除目标已不存在），pending 标记已清除；
    - "blocked"：身份/路径/指纹/解析/文件系统失败——pending 与备份目录均保留，调用方必须返回
      completed_cleanup_blocked 而非 completed_idempotent（含 rmtree 部分删除后失败：指纹将不再匹配，
      不可被静默吞成 completed）。

    安全约束（防 cleanup_pending.json 驱动的任意目录递归删除 / 跨 batch 删除）：
    1. 仅在 completed receipt 被 generation index 认证之后调用（bytes SHA == 索引 entry，
       backup_dir/backup_fingerprint 因此收进 completed_receipt_sha256；篡改任何字段都会使索引匹配失败 -> fail-closed）；
    2. cleanup_pending.json 必须匹配本 batch 的 batch_id 与 genesis_commit，否则 blocked（防御性复核）；
    3. 删除目标 = completed receipt 冻结的 frozen_backup_dir（不信任可变 cleanup_pending 的 backup_dir 字段）；
    4. 路径解析为绝对路径，必须严格位于 out_dir 内且目录名匹配确定性模式 .publish_backup_<pid>_<ts>；
    5. 磁盘上的内容指纹（成员集 SHA + 成员内容 SHA 映射）必须与冻结的 frozen_fingerprint 一致，
       否则视为"合法目录名但属于另一 batch 的备份"，blocked；
    6. 全部通过才 rmtree；成功才清除 pending 标记。任何失败返回 blocked 并保留 pending。
    """
    cp = receipt_dir / "cleanup_pending.json"
    if not cp.exists(): return "noop"
    if frozen_backup_dir is None or frozen_fingerprint is None: return "blocked"   # 无可认证删除目标
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
    except Exception:
        return "blocked"   # pending 解析失败，保留 pending
    if data.get("batch_id") != batch_id or data.get("genesis_commit") != genesis_anchor: return "blocked"   # 错误 batch
    try:
        resolved = Path(frozen_backup_dir).resolve()
        root = out_dir.resolve()
        try: rel = resolved.relative_to(root)
        except ValueError: return "blocked"   # 逃逸出 backup root
        if ".." in rel.parts or not _BACKUP_DIR_RE.fullmatch(rel.name): return "blocked"   # 非确定性目录名
    except Exception:
        return "blocked"
    if not resolved.exists():
        cp.unlink(missing_ok=True); return "cleaned"   # 删除目标已不存在，本 batch 身份已对齐，清除 pending
    fp = _backup_fingerprint(resolved)
    if fp["member_set_sha256"] != frozen_fingerprint.get("member_set_sha256") or fp["member_shas_sha256"] != frozen_fingerprint.get("member_shas_sha256"):
        return "blocked"   # 内容指纹不匹配（可能是另一 batch 的备份）
    try:
        shutil.rmtree(resolved)
    except Exception:
        return "blocked"   # rmtree 失败（含部分删除）：保留 pending，调用方必须显式处理，不可静默成 completed
    cp.unlink(missing_ok=True)
    return "cleaned"


def _build_rule_id_map(old_rules, new_rules) -> dict:
    """P0-3 中优：把历史 progress 规则逐记录映射到当前 all_rules.json 规则。

    真实数据中旧 ID 不唯一（1727 条记录 / 92 个唯一旧 ID，smth_0001 出现 78 次），
    因此不能用 dict[old_id]（会被覆盖）。改为逐记录映射，并以 canonical_key 为发生身份：

    - mapped：old canonical_key 唯一对应一个 new_id；
    - conflicts：old canonical_key 对应多个不同 new_id（一对多，无法唯一确定）；
    - unmappable：缺 canonical 字段或 new 中无对应规则。

    返回 {mapped, conflicts, unmappable, mapped_sha256, conflicts_sha256, unmappable_sha256}，
    且 len(mapped) + len(conflicts) + len(unmappable) == len(old_rules)（逐记录守恒）。
    """
    new_by_key = {}
    for r in new_rules:
        try: k = r.get("canonical_key") or dl._canonical_key(r)
        except ValueError: continue
        new_by_key.setdefault(k, set()).add(r.get("id"))
    mapped, conflicts, unmappable = [], [], []
    for r in old_rules:
        oid = r.get("id")
        record = {"old_id": oid, "old_record_sha256": sha256_bytes(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8"))}
        try: k = dl._canonical_key(r)
        except ValueError:
            record["reason"] = "missing_canonical_field"; unmappable.append(record); continue
        nids = [i for i in (new_by_key.get(k) or set()) if i]
        record["canonical_key"] = k
        if not nids:
            record["reason"] = "no_new_rule"; unmappable.append(record)
        elif len(nids) == 1:
            record["new_id"] = nids[0]; mapped.append(record)
        else:
            record["new_ids"] = sorted(nids); conflicts.append(record)
    def _sha(items):
        return sha256_bytes(json.dumps(items, sort_keys=True, ensure_ascii=False).encode("utf-8")) if items else None
    return {"mapped": mapped, "conflicts": conflicts, "unmappable": unmappable,
            "mapped_sha256": _sha(mapped), "conflicts_sha256": _sha(conflicts), "unmappable_sha256": _sha(unmappable)}

def _update_progress(staging: Path, *, run_id, batch_id, genesis_anchor, titles=None, selected_chapters=None):
    # P0-3：progress 内嵌数组由 staged outputs 重建，属于**受控 reconcile**（显式记录迁移），不是静默改写。
    # 真实数据中 progress.all_rules(1727)!=all_rules.json(1542)、ID 命名空间也不同（smth_0001 vs smth_000_000），
    # 因此必须在 remediation_meta 记录输入/输出 SHA、数量差异、逐条 ID 映射与不可映射清单。
    p = staging / "progress.json"
    prog = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    input_sha = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    titles = titles or {}; selected_chapters = selected_chapters or []
    done = set(prog.get("done", []))
    for ch in selected_chapters:
        done.add(titles.get(ch, str(ch)))
    done = sorted(done)
    rules_p = staging / "all_rules.json"
    rules = json.loads(rules_p.read_text(encoding="utf-8")) if rules_p.exists() else []
    mcq_p = staging / "all_mcq.jsonl"
    mcqs = [json.loads(l) for l in mcq_p.read_text(encoding="utf-8").splitlines()] if mcq_p.exists() else []
    old_counts = {"all_rules": len(prog.get("all_rules", [])), "all_mcqs": len(prog.get("all_mcqs", []))}
    # P0-3 中优：旧/新规则逐记录 ID 映射（旧 smth_0001 命名空间 -> 新 smth_000_000），按 canonical key 匹配
    recon = _build_rule_id_map(prog.get("all_rules", []), rules)
    prog.update({"run_id": run_id, "batch_id": batch_id, "status": "published", "genesis_commit": genesis_anchor, "updated_at": time.time(),
                 "done": done, "total_rules": len(rules), "total_mcqs": len(mcqs),
                 "all_rules": rules, "all_mcqs": mcqs})
    tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8"); os.replace(str(tmp), str(p))
    output_sha = hashlib.sha256(p.read_bytes()).hexdigest()
    _record_progress_reconcile(staging, run_id=run_id, batch_id=batch_id, genesis_anchor=genesis_anchor,
                               input_sha=input_sha, output_sha=output_sha, old_counts=old_counts,
                               new_counts={"all_rules": len(rules), "all_mcqs": len(mcqs)},
                               mapped=recon["mapped"], mapped_sha256=recon["mapped_sha256"],
                               conflicts=recon["conflicts"], conflicts_sha256=recon["conflicts_sha256"],
                               unmappable=recon["unmappable"], unmappable_sha256=recon["unmappable_sha256"])

def _record_progress_reconcile(staging: Path, *, run_id, batch_id, genesis_anchor, input_sha, output_sha, old_counts, new_counts,
                               mapped=None, mapped_sha256=None, conflicts=None, conflicts_sha256=None,
                               unmappable=None, unmappable_sha256=None) -> None:
    """P0-3：把 progress 重建作为显式迁移记入 remediation_meta（输入/输出 SHA、数量差异、逐记录映射/冲突/不可映射清单）。"""
    p = staging / "remediation_meta.json"
    meta = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"actions": []}
    meta.setdefault("actions", []).append({"type": "progress_reconcile", "batch_id": batch_id, "run_id": run_id, "genesis_commit": genesis_anchor,
                                           "input_progress_sha256": input_sha, "output_progress_sha256": output_sha,
                                           "old_counts": old_counts, "new_counts": new_counts,
                                           "mapped": mapped or [], "mapped_sha256": mapped_sha256,
                                           "conflicts": conflicts or [], "conflicts_sha256": conflicts_sha256,
                                           "unmappable": unmappable or [], "unmappable_sha256": unmappable_sha256,
                                           "note": "progress 内嵌数组由当前 all_rules.json/all_mcq.jsonl 重建；历史 ID 命名空间 smth_0001 与现行 smth_000_000 的逐记录映射见 mapped（canonical key 匹配），一对多冲突见 conflicts，无法映射见 unmappable；mapped+conflicts+unmappable==old 记录数守恒"})
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

def _update_remediation_meta(staging: Path, *, run_id, batch_id, chapters, genesis_anchor):
    p = staging / "remediation_meta.json"
    meta = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"actions": []}
    meta.setdefault("actions", []).append({"type": "distill_append", "batch_id": batch_id, "run_id": run_id, "chapters": chapters, "genesis_commit": genesis_anchor})
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

def _backfill_staging_keys(staging: Path, *, run_id, batch_id, genesis_anchor) -> None:
    """P0-3：对 staging 中已 seed 的既有规则做原子 canonical key 补写，并写入 provenance receipt。"""
    p = staging / "all_rules.json"
    if not p.exists(): return
    input_sha = hashlib.sha256(p.read_bytes()).hexdigest()
    rules = json.loads(p.read_text(encoding="utf-8"))
    id_set_sha = dl.sha256_bytes(json.dumps(sorted(r.get("id", "") for r in rules), ensure_ascii=False).encode("utf-8"))
    count = len(rules)
    dl.backfill_canonical_keys(staging)          # 原子补写（tmp + os.replace）
    output_sha = hashlib.sha256(p.read_bytes()).hexdigest()
    meta = {"type": "canonical_key_backfill", "batch_id": batch_id, "run_id": run_id, "genesis_commit": genesis_anchor,
            "input_sha256": input_sha, "output_sha256": output_sha, "rules_count": count, "id_set_sha256": id_set_sha}
    rem_p = staging / "remediation_meta.json"
    rem = json.loads(rem_p.read_text(encoding="utf-8")) if rem_p.exists() else {"actions": []}
    rem.setdefault("actions", []).append(meta)
    rem_p.write_text(json.dumps(rem, ensure_ascii=False, indent=2), encoding="utf-8")

def run_sanming_batch(manifest_path: Path, *, snapshot_dir: Path, out_dir: Path, formal_dir: Path, snapshot_sha: str, proj_ledger_path: Path, run_ledger_path: Path, run_id: str, project_total_cap: int, scripts_dir: Path, root: Path, git_root: Path, genesis_anchor: str, limits=None, generation_index_path: Path | None = None) -> dict:
    m = dl.load_batch_manifest(manifest_path); batch_id = m["batch_id"]
    staging = out_dir / ".batch_staging" / batch_id; receipt_dir = out_dir / ".batch" / batch_id; backup_dir = None
    # P0-7/P0-8：已完成 batch 的幂等入口——先检查 completed receipt
    completed_receipt_path = receipt_dir / "completed_receipt.json"
    if completed_receipt_path.exists():
        rec = json.loads(completed_receipt_path.read_text(encoding="utf-8"))
        for k in ("batch_id", "status", "genesis_commit", "source_snapshot_sha256", "manifest_sha", "code_sha", "rules_sha", "run_id", "output_shas", "backup_dir", "backup_fingerprint"):
            if k not in rec: raise ValueError("completed receipt missing field (fail-closed, no re-call)")
        if rec.get("status") != "published": raise ValueError("completed receipt status not published (fail-closed, no re-call)")
        if (rec.get("batch_id") != batch_id or rec.get("genesis_commit") != genesis_anchor
                or rec.get("manifest_sha") != _file_sha256(manifest_path)
                or rec.get("source_snapshot_sha256") != m["source_snapshot_sha256"]
                or rec.get("code_sha") != m["code_sha"] or rec.get("rules_sha") != m["rules_sha"]
                or rec.get("run_id") != run_id): raise ValueError("completed receipt identity drift (fail-closed, no re-call)")
        if _output_shas(out_dir) != rec.get("output_shas"): raise ValueError("completed receipt output SHA mismatch (fail-closed, no re-call)")
        # P0-8：区分"已入 generation index"与"尚未 finalize"
        if generation_index_path is not None and Path(generation_index_path).exists():
            from scripts.classic_artifacts import GenerationIndex
            idx = GenerationIndex(Path(generation_index_path), genesis_anchor=genesis_anchor)
            if not idx.verify(): raise ValueError("generation index hash chain invalid (fail-closed, no re-call)")   # P0-4：验证完整链
            receipt_sha = hashlib.sha256(completed_receipt_path.read_bytes()).hexdigest()
            # P0-4/P0-1：idx.verify() 已校验完整 hash chain + entry schema（首条 previous=None、genesis_commit 40-hex）；
            # 此处只精确匹配 (batch_id, completed_receipt_sha256, genesis_commit)，不再手写 previous_index_sha256 长度条件
            matches = [e for e in idx._load() if e.get("batch_id") == batch_id and e.get("completed_receipt_sha256") == receipt_sha
                       and e.get("genesis_commit") == genesis_anchor]
            if matches:
                # P0-3：仅在此处（completed receipt 已被 index 认证：bytes SHA == 索引 entry）才重试 cleanup。
                # 备份目标与内容指纹取自已认证的 completed receipt（backup_dir/backup_fingerprint 已收进
                # completed_receipt_sha256），不信任可变的 cleanup_pending.json；指纹/路径不匹配即拒绝，绝不吞掉身份校验错误。
                cleanup_state = _retry_pending_cleanup(receipt_dir, out_dir, batch_id=batch_id, genesis_anchor=genesis_anchor,
                                                       frozen_backup_dir=Path(rec["backup_dir"]) if rec.get("backup_dir") else None,
                                                       frozen_fingerprint=rec.get("backup_fingerprint"))
                # P0-3：只允许"无 pending（noop）"或"清理成功（cleaned）"进入 completed_idempotent；
                # 身份/路径/指纹/解析/文件系统失败（blocked）-> completed_cleanup_blocked，pending 与备份目录保留。
                if cleanup_state == "blocked":
                    return {"status": "completed_cleanup_blocked", "batch_id": batch_id, "completed_receipt": str(completed_receipt_path)}
                return {"status": "completed_idempotent", "batch_id": batch_id, "completed_receipt": str(completed_receipt_path)}
            raise ValueError("completed receipt exists but generation index has no matching entry (fail-closed, no re-call)")
        # 未 finalize：completed receipt 尚未被 index 认证，不做 cleanup 重试（避免可变 pending/未认证 receipt 驱动的删除）
        return {"status": "published_pending_finalize", "batch_id": batch_id, "completed_receipt": str(completed_receipt_path)}
    published = False; backup_cleanup_pending = False
    try:
        if materialization_status(formal_dir, snapshot_sha) != "materialized": raise RuntimeError("snapshot unmaterialized: distillation requires materialized responses")
        _validate_snapshot_bindings(m, formal_dir=formal_dir, snapshot_dir=snapshot_dir, snapshot_sha=snapshot_sha)
        snap_dir_path = formal_dir / "source_snapshots" / m["source_snapshot_sha256"]
        src_man = json.loads((snap_dir_path / "source_manifest.json").read_text(encoding="utf-8"))
        titles = {c["chapter_index"]: c["title"] for c in src_man["chapters"]}   # P0-6：规范章节标题
        _validate_manifest_bindings(m, snapshot_dir=snapshot_dir, out_dir=out_dir, scripts_dir=scripts_dir, root=root, git_root=git_root)
        proj = dl.ProjectLedger.load_or_create(proj_ledger_path, experiment_id=EXPERIMENT_ID, total_cap=project_total_cap)
        run = dl.BudgetLedger.load_or_create(run_ledger_path, global_hard_cap=m["batch_hard_cap"], run_id=run_id, code_sha=m["code_sha"], rules_sha=m["rules_sha"])
        if staging.exists(): shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True); receipt_dir.mkdir(parents=True, exist_ok=True)
        _seed_staging_from_existing(staging, out_dir)
        _backfill_staging_keys(staging, run_id=run_id, batch_id=batch_id, genesis_anchor=genesis_anchor)   # P0-3：生产接线
        calls_before = run.calls_made; proj_before = proj.calls_made
        ctx = dl.BudgetCtx(run_id=run_id, batch_id=batch_id, proj=proj, run=run, proj_path=proj_ledger_path, run_path=run_ledger_path)
        segs_by_chapter = {}
        for ch_idx in m["selected_chapter_ids"]:
            src = snapshot_dir / f"raw_{ch_idx:03d}.txt"
            segs_by_chapter[ch_idx] = dl.segment_chapter(src.read_text(encoding="utf-8"), book="sanmingtonghui", chapter=str(ch_idx), limits=limits or dl.PromptLimits())
        if _segment_manifest_sha(segs_by_chapter) != m["segment_manifest_sha"]: raise ValueError("segment_manifest_sha mismatch")
        if _model_prompt_config_sha() != m["model_prompt_config_sha"]: raise ValueError("model_prompt_config_sha mismatch")
        rules_added = mcqs_added = quarantine_added = 0
        for ch_idx, segs in segs_by_chapter.items():
            ch0 = ch_idx - 1   # P0-5：ID 用 0-based ch_idx（章 81 -> smth_080_000）
            rules = dl.distill_segments(segs, book="sanmingtonghui", chapter=str(ch_idx), limits=limits or dl.PromptLimits(), ledger=run, budget_ctx=ctx, chapter_id=ch0)
            dl.dedup_then_assign_rule_ids(rules, "smth", ch0)
            mcqs_ok, mcqs_q = dl.generate_mcq(rules, "sanmingtonghui", str(ch_idx), ledger=run, budget_ctx=ctx, chapter_id=ch0)
            dl.assign_mcq_ids(mcqs_ok, "smth", ch0, 0); dl.assign_mcq_ids(mcqs_q, "smth", ch0, len(mcqs_ok))
            _append_rules(staging, rules); _append_mcqs(staging, mcqs_ok); _append_mcqs(staging, mcqs_q, quarantine=True)
            rules_added += len(rules); mcqs_added += len(mcqs_ok); quarantine_added += len(mcqs_q)
        _update_progress(staging, run_id=run_id, batch_id=batch_id, genesis_anchor=genesis_anchor, titles=titles, selected_chapters=m["selected_chapter_ids"])
        _update_remediation_meta(staging, run_id=run_id, batch_id=batch_id, chapters=m["selected_chapter_ids"], genesis_anchor=genesis_anchor)
        prepared = {"batch_id": batch_id, "status": "prepared", "manifest_sha": _file_sha256(manifest_path), "pre_run_output_sha": m["pre_run_output_sha"], "calls_made_before": calls_before, "proj_calls_made_before": proj_before, "staging_output_shas": _output_shas(staging)}
        _write_receipt(receipt_dir / "prepared_receipt.json", prepared)
        expected_staging_shas = _output_shas(staging)
        backup_dir = rc._publish(staging, out_dir, list(_RECEIPT_OUTPUT_NAMES))
        for name, sha in expected_staging_shas.items():
            if _file_sha256(out_dir / name) != sha: raise ValueError(f"publish verification failed for {name}")
        completed = {"batch_id": batch_id, "status": "published", "genesis_commit": genesis_anchor, "source_snapshot_sha256": m["source_snapshot_sha256"], "manifest_sha": _file_sha256(manifest_path), "code_sha": m["code_sha"], "rules_sha": m["rules_sha"], "run_id": run_id, "calls_made_after": run.calls_made, "output_shas": _output_shas(out_dir), "backup_dir": str(backup_dir) if backup_dir else None, "backup_fingerprint": _backup_fingerprint(backup_dir) if backup_dir else None}
        _write_receipt(receipt_dir / "completed_receipt.json", completed)
        published = True  # P0-6：进入不可回滚状态
        try:
            if backup_dir is not None and backup_dir.exists():
                shutil.rmtree(backup_dir)
                cp = receipt_dir / "cleanup_pending.json"
                if cp.exists(): cp.unlink(missing_ok=True)   # 中优：cleanup 完成即清除 pending 状态
                backup_dir = None
        except Exception:
            backup_cleanup_pending = True
            # P0-3：cleanup 状态持久化为独立 receipt（仅作标记；权威 backup_dir/内容指纹已在 completed receipt 冻结）
            _write_receipt(receipt_dir / "cleanup_pending.json", {"batch_id": batch_id, "status": "cleanup_pending", "genesis_commit": genesis_anchor, "backup_dir": str(backup_dir) if backup_dir else None})
        return {"status": "published", "batch_id": batch_id, "prepared_receipt": str(receipt_dir / "prepared_receipt.json"), "completed_receipt": str(receipt_dir / "completed_receipt.json"), "backup_cleanup_pending": backup_cleanup_pending}
    except Exception as e:
        if backup_dir is not None and not published:  # P0-6：published 后不再回滚
            rc._rollback_from_backup(out_dir, backup_dir, list(_RECEIPT_OUTPUT_NAMES))
        _rollback_staging(staging)
        verdict = dl.classify_failure_for_resume(e, code_sha_before=m["code_sha"], code_sha_now=_code_sha_now(scripts_dir, root))
        return {"status": verdict, "batch_id": batch_id, "error": repr(e), "prepared_receipt": str(receipt_dir / "prepared_receipt.json")}
```

阶段 7 测试：`_dispatch_fake`（稳定中文分流 + 规则"甲木日主喜水"/MCQ A="喜水滋润"）、manifest schema、merge_dedup/ID 赋值、classify_failure、append 辅助、segment SHA 确定性、正向 published（断言 receipt["genesis_commit"]==genesis 且 staging 含 progress.json/remediation_meta.json）、experiment_id 拒绝、跨批守恒、identity loop 关闭、network failure rollback、code drift abandon。新增 P0-5 / P0-7：

```python
# 自包含 helper（内联定义，供下方内联测试直接运行；P0-1：显式模块级导入）
import hashlib, json, subprocess, shutil, pytest
from pathlib import Path
import scripts.distill_lib as dl
ROOT = Path(__file__).resolve().parent.parent

def _dispatch_fake(prompt, timeout=300):
    if "提取结构化命理规则" in prompt: return '[{"rule":"甲木日主喜水","condition":"甲木生于寅月","subject":"甲木","original_text":"甲木喜水"}]'
    if "生成一道四选一选择题" in prompt: return '{"question":"甲木喜什么？","options":{"A":"喜水滋润","B":"火","C":"土","D":"金"},"answer":"A","explanation":"甲木喜水"}'
    return "[]"

def _materialized_snapshot(tmp_path, chapters=(81, 82)):
    from scripts.fetch_sanming_chapters import ChapterEntry, build_and_publish_snapshot, read_active_snapshot, materialization_status, restore_responses
    body = b"B"
    def text(c): return f"第{c}章正文。\n\n第二段。\n" * 40
    def factory(entries):
        return [{"chapter_index": e.index, "title": f"章{e.index}", "url": f"u{e.index}", "response_body_sha256": hashlib.sha256(body).hexdigest(), "extracted_text_sha256": hashlib.sha256(text(e.index).encode("utf-8")).hexdigest(), "extractor_sha256": "x"*64, "normalized_page_title": f"章{e.index}", "response_body_status": "archived", "provenance_level": "full", "encoding": "utf-8", "extracted_text": text(e.index), "response_body": body, "ok": True} for e in entries]
    formal = tmp_path / "formal"
    build_and_publish_snapshot([ChapterEntry(c, f"章{c}", f"u{c}") for c in chapters], formal, records_factory=factory, archive_root=tmp_path / "store")
    act = read_active_snapshot(formal); sha = act["snapshot_sha256"]
    restore_responses(formal, sha, archive_root=tmp_path / "store")
    assert materialization_status(formal, sha) == "materialized"
    return formal / "source_snapshots" / sha / "extracted", act, formal

def _setup_batch(tmp_path):
    import subprocess as sp
    snap, act, formal = _materialized_snapshot(tmp_path)
    out = tmp_path / "book"; out.mkdir()
    repo = tmp_path / "repo"; repo.mkdir()
    sp.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    sp.run(["git", "-C", str(repo), "add", "."], check=True); sp.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    head = sp.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    return snap, out, repo, head, formal, act

def _mk_batch_manifest(tmp_path, batch_id, snap_dir, head, parent, pre_run_sha, chs=(81,)):
    import hashlib as _h
    src_sha = {str(c): _h.sha256((snap_dir / f"raw_{c:03d}.txt").read_bytes()).hexdigest() for c in chs}
    m = {"schema_version": "1.0", "batch_id": batch_id, "selected_chapter_ids": list(chs), "source_sha_map": src_sha, "segment_manifest_sha": "0"*64, "pre_run_output_sha": pre_run_sha, "model_prompt_config_sha": "0"*64, "batch_hard_cap": 100, "parent_commit": parent, "parent_head_sha": head, "code_sha": "0"*64, "rules_sha": "0"*64, "source_snapshot_sha256": "0"*64, "source_manifest_sha256": "0"*64, "source_archive_pointer_sha256": "0"*64, "experiment_id": dl.EXPERIMENT_ID}
    p = tmp_path / f"{batch_id}.json"; p.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8"); return p, m

def _fill_real_shas(mp, m, snap, formal, act):
    from scripts.fetch_sanming_chapters import _file_sha256
    from scripts.fill_missing_chapters import _segment_manifest_sha, _model_prompt_config_sha, _code_sha_now
    chs = m["selected_chapter_ids"]
    segs = {c: dl.segment_chapter((snap / f"raw_{c:03d}.txt").read_text(encoding="utf-8"), book="sanmingtonghui", chapter=str(c), limits=dl.PromptLimits()) for c in chs}
    m["segment_manifest_sha"] = _segment_manifest_sha(segs)
    m["model_prompt_config_sha"] = _model_prompt_config_sha()
    m["code_sha"] = _code_sha_now(ROOT / "scripts", ROOT)
    m["source_snapshot_sha256"] = act["snapshot_sha256"]
    m["source_manifest_sha256"] = act["source_manifest_sha256"]
    snap_dir = formal / "source_snapshots" / act["snapshot_sha256"]
    m["source_archive_pointer_sha256"] = _file_sha256(snap_dir / "RESPONSE_ARCHIVE_POINTER.json")
    mp.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")

def _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, fake_call, generation_index_path=None, genesis_anchor="0"*40):
    from scripts.fill_missing_chapters import run_sanming_batch
    monkeypatch.setattr(dl, "_call", fake_call)
    return run_sanming_batch(mp, snapshot_dir=snap, out_dir=out, formal_dir=formal, snapshot_sha=act["snapshot_sha256"], proj_ledger_path=tmp_path / "proj.json", run_ledger_path=tmp_path / "run.json", run_id="R1", project_total_cap=1000, scripts_dir=ROOT / "scripts", root=ROOT, git_root=repo, genesis_anchor=genesis_anchor, generation_index_path=generation_index_path)
```

```python
# P0-5：章 81 用 0-based ch_idx=80 -> smth_080_000 / smth_080_mcq_0000 金标（规则含 canonical 7 字段）
def test_chapter81_uses_zerobased_index_80():
    rules = [{"source_book": "sanmingtonghui", "source_chapter": "81", "category": "classic", "subject": "甲木", "condition": "生于寅月", "rule": "甲木日主喜水", "original_text": "甲木喜水", "segment_index": 0}]
    dl.dedup_then_assign_rule_ids(rules, "smth", 80)
    assert rules[0]["id"] == "smth_080_000"
    mcqs = [{"source_rule_id": rules[0]["id"]}]
    dl.assign_mcq_ids(mcqs, "smth", 80, 0)
    assert mcqs[0]["id"] == "smth_080_mcq_0000"

# P0-5：canonical key 字面量 golden SHA + 写回 + 不同规则不吞并
def test_canonical_key_golden_sha():
    r = {"source_book": "sanmingtonghui", "source_chapter": "81", "category": "classic", "subject": "甲木", "condition": "生于寅月", "rule": "甲木日主喜水", "original_text": "甲木喜水"}
    assert dl._canonical_key(r) == "e3f0663582b9334eaa681fe6e702b67c68d33d1c18a686868758aa50f9f62630"
    out = dl.canonical_dedup([r, dict(r, condition="生于卯月")])
    assert len(out) == 2 and out[0]["canonical_key"] == "e3f0663582b9334eaa681fe6e702b67c68d33d1c18a686868758aa50f9f62630"

# P0-5：前 80 章 canonical key 补写后守恒（用临时副本，不改真实数据）
# 冻结决策：backfill 只允许新增 {canonical_key, source_book, source_chapter, category} 这 4 个字段
# （canonical_key 必加；其余 3 个仅当缺失时按冻结派生默认补上）；任何其它字段改动、顺序变化或数量变化都会导致测试失败。
def test_backfill_front80_keeps_ids(tmp_path):
    import shutil
    src = ROOT / "knowledge_base/classic_texts/sanmingtonghui"
    book = tmp_path / "book"; book.mkdir()
    shutil.copy2(src / "all_rules.json", book / "all_rules.json")
    before = json.loads((book / "all_rules.json").read_text(encoding="utf-8"))
    dl.backfill_canonical_keys(book)
    after = json.loads((book / "all_rules.json").read_text(encoding="utf-8"))
    assert len(after) == len(before)   # 集合守恒
    allowed_added = {"canonical_key", "source_book", "source_chapter", "category"}
    for b, a in zip(before, after):
        extra = set(a) - set(b)
        assert extra <= allowed_added, f"unexpected added fields: {extra}"
        assert {k: b[k] for k in b} == {k: a[k] for k in b}   # 既有字段完全不变
        assert isinstance(a.get("canonical_key"), str) and len(a["canonical_key"]) == 64
    assert [b.get("id") for b in before] == [a.get("id") for a in after]   # 原始顺序保留（未排序）

# P0-5：canonical dedup 缺字段 fail-closed，禁止空 key 吞并
def test_canonical_dedup_fails_closed_on_missing_field():
    with pytest.raises(ValueError, match="canonical field"):
        dl.canonical_dedup([{"rule": "r", "condition": "c", "subject": "s"}])  # 缺 original_text 等

# P0-7/P0-8：已完成 batch 幂等——未入 index 返回 published_pending_finalize，已入 index 返回 completed_idempotent，均不重新调用
def test_completed_batch_idempotent_returns_completed(tmp_path, monkeypatch):
    import scripts.distill_lib as dl
    from scripts.classic_artifacts import finalize_batch
    snap, out, repo, head, formal, act = _setup_batch(tmp_path)
    pre_run_sha = hashlib.sha256(json.dumps({}, sort_keys=True).encode()).hexdigest()
    mp, m = _mk_batch_manifest(tmp_path, "B1", snap_dir=snap, head=head, parent=head, pre_run_sha=pre_run_sha)
    _fill_real_shas(mp, m, snap, formal, act)
    monkeypatch.setattr(dl, "_call", _dispatch_fake)
    res1 = _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, _dispatch_fake, genesis_anchor=head)
    assert res1["status"] == "published"
    calls = {"n": 0}
    def fake(*a, **k): calls["n"] += 1; raise AssertionError("must not re-call")
    # 未入 generation index -> published_pending_finalize
    res2 = _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, fake, genesis_anchor=head)
    assert res2["status"] == "published_pending_finalize" and calls["n"] == 0
    # 已入 generation index（匹配 batch_id + completed_receipt_sha256）-> completed_idempotent
    receipt = out / ".batch" / "B1" / "completed_receipt.json"
    gi = tmp_path / "gi.json"
    finalize_batch(batch_id="B1", completed_receipt_path=receipt, index_path=gi, genesis_anchor=head)
    res3 = _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, fake, generation_index_path=gi, genesis_anchor=head)
    assert res3["status"] == "completed_idempotent" and calls["n"] == 0

# P0-3（复审 4）完整链负向：finalize 后备份内容被篡改（磁盘指纹 != 冻结指纹）——不调 API、不删目录、非 completed_idempotent
def test_fake_flow_cleanup_blocked_after_finalize(tmp_path, monkeypatch):
    import scripts.distill_lib as dl
    from scripts.classic_artifacts import finalize_batch
    snap, out, repo, head, formal, act = _setup_batch(tmp_path)
    pre_run_sha = hashlib.sha256(json.dumps({}, sort_keys=True).encode()).hexdigest()
    mp, m = _mk_batch_manifest(tmp_path, "B1", snap_dir=snap, head=head, parent=head, pre_run_sha=pre_run_sha)
    _fill_real_shas(mp, m, snap, formal, act)
    monkeypatch.setattr(dl, "_call", _dispatch_fake)
    # 首次 cleanup 失败 -> pending + 备份保留 + completed receipt 冻结指纹
    real_rmtree = shutil.rmtree
    def failing_rmtree(path, *a, **k):
        if isinstance(path, (str, Path)) and Path(path).name.startswith(".publish_backup_"):
            raise PermissionError("simulated cleanup failure")
        return real_rmtree(path, *a, **k)
    monkeypatch.setattr(shutil, "rmtree", failing_rmtree)
    res1 = _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, _dispatch_fake, genesis_anchor=head)
    monkeypatch.setattr(shutil, "rmtree", real_rmtree)
    assert res1["status"] == "published"
    cp_path = out / ".batch" / "B1" / "cleanup_pending.json"
    assert cp_path.exists()
    rec = json.loads((out / ".batch" / "B1" / "completed_receipt.json").read_text(encoding="utf-8"))
    backup_dir = Path(rec["backup_dir"])
    assert backup_dir.exists() and _backup_fingerprint(backup_dir) == rec["backup_fingerprint"]
    # finalize：completed receipt 被 index 认证
    receipt = out / ".batch" / "B1" / "completed_receipt.json"
    gi = tmp_path / "gi.json"
    finalize_batch(batch_id="B1", completed_receipt_path=receipt, index_path=gi, genesis_anchor=head)
    # 篡改备份目录内容（磁盘指纹 != 冻结指纹）
    (backup_dir / "tamper.txt").write_text("tampered", encoding="utf-8")
    assert _backup_fingerprint(backup_dir) != rec["backup_fingerprint"]
    # 幂等调用：不调用 API、不删除目录、不得返回 completed_idempotent
    calls = {"n": 0}
    def fake(*a, **k): calls["n"] += 1; raise AssertionError("must not re-call")
    res2 = _run(tmp_path, monkeypatch, mp, snap, out, repo, head, formal, act, fake, generation_index_path=gi, genesis_anchor=head)
    assert calls["n"] == 0
    assert res2["status"] == "completed_cleanup_blocked"   # 身份/指纹校验失败，不吞错误、不进入 completed_idempotent
    assert backup_dir.exists() and cp_path.exists()   # 备份与 pending 均保留

# P0-3：cleanup 安全（复审 4）——显式状态返回，任何校验失败返回 "blocked"，不吞错误、不进入 completed_idempotent
def test_retry_pending_cleanup_rejects_path_escape(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    victim = tmp_path / "victim"; victim.mkdir(); (victim / "f").write_text("x", encoding="utf-8")
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(victim)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=victim, frozen_fingerprint=_backup_fingerprint(victim))
    assert st == "blocked" and victim.exists() and cp.exists()   # 逃逸出 out_dir，blocked

def test_retry_pending_cleanup_rejects_absolute_nonpattern(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    bad = out / "something_else"; bad.mkdir(); (bad / "f").write_text("x", encoding="utf-8")
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(bad)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=bad, frozen_fingerprint=_backup_fingerprint(bad))
    assert st == "blocked" and bad.exists() and cp.exists()   # 目录名不匹配确定性模式，blocked

def test_retry_pending_cleanup_rejects_wrong_batch(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    target = out / ".publish_backup_1_1"; target.mkdir(); (target / "f").write_text("x", encoding="utf-8")
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "OTHER", "genesis_commit": "a" * 40, "backup_dir": str(target)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=target, frozen_fingerprint=_backup_fingerprint(target))
    assert st == "blocked" and target.exists() and cp.exists()   # pending 声明 batch 不匹配，blocked

def test_retry_pending_cleanup_deletes_matching_frozen(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    target = out / ".publish_backup_123_456"; target.mkdir(); (target / "f").write_text("x", encoding="utf-8")
    fp = _backup_fingerprint(target)
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(target)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=target, frozen_fingerprint=fp)
    assert st == "cleaned" and not target.exists() and not cp.exists()   # 冻结指纹匹配 -> 删除并清除 pending

def test_retry_pending_cleanup_noop_without_pending(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=None, frozen_fingerprint=None)
    assert st == "noop"   # 无 pending，无需清理

def test_retry_pending_cleanup_rejects_missing_frozen(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    target = out / ".publish_backup_123_456"; target.mkdir(); (target / "f").write_text("x", encoding="utf-8")
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(target)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=None, frozen_fingerprint=None)   # 无可认证删除目标
    assert st == "blocked" and target.exists() and cp.exists()

def test_retry_pending_cleanup_rejects_unparseable_pending(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    target = out / ".publish_backup_123_456"; target.mkdir(); (target / "f").write_text("x", encoding="utf-8")
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text("{not valid json", encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=target, frozen_fingerprint=_backup_fingerprint(target))
    assert st == "blocked" and target.exists() and cp.exists()   # pending 解析失败，blocked

def test_retry_pending_cleanup_rejects_frozen_fingerprint_mismatch(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    # 冻结路径上的备份内容已被替换为另一 batch 的内容（合法目录名但内容非本 batch）
    target = out / ".publish_backup_111_222"; target.mkdir(); (target / "all_rules.json").write_text('["B2-rules"]', encoding="utf-8")
    frozen_fp = _backup_fingerprint(out / ".publish_backup_111_222")
    (target / "all_rules.json").write_text('["B2-rules-CHANGED"]', encoding="utf-8")   # 与冻结指纹不一致
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(target)}, ensure_ascii=False), encoding="utf-8")
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=target, frozen_fingerprint=frozen_fp)
    assert st == "blocked" and target.exists() and cp.exists()   # 内容指纹不匹配（属于另一 batch），blocked

def test_retry_pending_cleanup_rmtree_failure_blocked(tmp_path, monkeypatch):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    target = out / ".publish_backup_123_456"; target.mkdir(); (target / "f").write_text("x", encoding="utf-8")
    fp = _backup_fingerprint(target)
    cp = receipt_dir / "cleanup_pending.json"
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(target)}, ensure_ascii=False), encoding="utf-8")
    def failing_rmtree(path, *a, **k): raise PermissionError("simulated rmtree failure")
    monkeypatch.setattr(shutil, "rmtree", failing_rmtree)
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=target, frozen_fingerprint=fp)
    monkeypatch.setattr(shutil, "rmtree", shutil.rmtree)
    assert st == "blocked" and target.exists() and cp.exists()   # rmtree 失败（含部分删除）：blocked，不吞错误

# P0-3：攻击者篡改可变 cleanup_pending 指向另一 batch 的合法备份目录——pending 的路径/指纹被忽略，另一 batch 不被删除
def test_retry_pending_cleanup_ignores_tampered_pending_path(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    receipt_dir = out / ".batch" / "B1"; receipt_dir.mkdir(parents=True)
    own = out / ".publish_backup_111_222"; own.mkdir(); (own / "all_rules.json").write_text('["B1-rules"]', encoding="utf-8")
    other = out / ".publish_backup_333_444"; other.mkdir(); (other / "all_rules.json").write_text('["B2-rules"]', encoding="utf-8")
    own_fp = _backup_fingerprint(own)
    cp = receipt_dir / "cleanup_pending.json"
    # 攻击者篡改可变 cleanup_pending：backup_dir 指向另一 batch 的合法备份目录（目录名合法），并伪造其指纹
    cp.write_text(json.dumps({"batch_id": "B1", "genesis_commit": "a" * 40, "backup_dir": str(other),
                              "backup_fingerprint": _backup_fingerprint(other)}, ensure_ascii=False), encoding="utf-8")
    # 删除目标与指纹取自已认证 completed receipt 冻结值（own），pending 的路径/指纹被忽略 -> other 不被删除
    st = _retry_pending_cleanup(receipt_dir, out, batch_id="B1", genesis_anchor="a" * 40,
                                frozen_backup_dir=own, frozen_fingerprint=own_fp)
    assert st == "cleaned" and other.exists()   # 另一 batch 的合法备份未被删除（pending 篡改无效）
    assert not own.exists() and not cp.exists()   # 只清理已认证 receipt 冻结的本 batch 备份

# P0-3 中优：progress reconcile 逐记录映射——旧 ID 不唯一时不再被 dict 覆盖
def test_progress_reconcile_per_record_mapping(tmp_path):
    staging = tmp_path / "staging"; staging.mkdir()
    base = {"subject": "甲木", "condition": "生于寅月", "rule": "甲木日主喜水", "original_text": "甲木喜水", "source_book": "sanmingtonghui", "source_chapter": "81", "category": "classic"}
    old_progress = {"done": [], "all_rules": [
        dict(base, id="smth_0001"),
        dict(base, id="smth_0001"),          # 同 old_id 的另一条记录（内容相同）
        dict(base, condition="生于卯月", id="smth_0002"),
    ], "all_mcqs": []}
    (staging / "progress.json").write_text(json.dumps(old_progress, ensure_ascii=False), encoding="utf-8")
    new_rules = [
        dict(base, id="smth_000_000", canonical_key=dl._canonical_key(base)),
        dict(base, condition="生于卯月", id="smth_000_001", canonical_key=dl._canonical_key(dict(base, condition="生于卯月"))),
    ]
    (staging / "all_rules.json").write_text(json.dumps(new_rules, ensure_ascii=False), encoding="utf-8")
    (staging / "all_mcq.jsonl").write_text("", encoding="utf-8")
    _update_progress(staging, run_id="R1", batch_id="B1", genesis_anchor="a" * 40)
    rem = json.loads((staging / "remediation_meta.json").read_text(encoding="utf-8"))
    act = [a for a in rem["actions"] if a["type"] == "progress_reconcile"][0]
    assert len(act["mapped"]) + len(act["conflicts"]) + len(act["unmappable"]) == 3   # 逐记录守恒
    # 同 old_id 的两条记录各自独立映射（不覆盖）
    assert len(act["mapped"]) == 3
    assert all(m["new_id"] == "smth_000_000" for m in act["mapped"] if m["old_id"] == "smth_0001")

# P0-3 中优：真实前 80 章副本——逐记录总数守恒（mapped + conflicts + unmappable == old 记录数）
def test_progress_reconcile_total_conservation_real(tmp_path):
    src = ROOT / "knowledge_base/classic_texts/sanmingtonghui"
    old_rules = json.loads((src / "progress.json").read_text(encoding="utf-8"))["all_rules"]
    new_rules = json.loads((src / "all_rules.json").read_text(encoding="utf-8"))
    for r in new_rules:
        if "canonical_key" not in r: r["canonical_key"] = dl._canonical_key(r)
    recon = _build_rule_id_map(old_rules, new_rules)
    assert len(recon["mapped"]) + len(recon["conflicts"]) + len(recon["unmappable"]) == len(old_rules)   # 1727 逐记录守恒
    for rec in recon["mapped"]:
        assert rec.get("old_id") and rec.get("new_id") and len(rec["old_record_sha256"]) == 64
    for rec in recon["conflicts"]:
        assert len(rec.get("new_ids", [])) >= 2
    for rec in recon["unmappable"]:
        assert rec.get("old_id") and len(rec["old_record_sha256"]) == 64
```

RED → GREEN → 提交。

---

## 阶段 8：Git 历史锚定 batch anchor + final-anchor 全链（完整实现）

`scripts/classic_artifacts.py` 追加：

```python
def generation_index_sha256(entries) -> str:
    return hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

FROZEN_ENTRY_FIELDS = ("batch_id", "completed_receipt_sha256", "genesis_commit", "previous_index_sha256")

def _is_40hex(v) -> bool: return isinstance(v, str) and len(v) == 40 and all(c in "0123456789abcdef" for c in v)
def _is_64hex(v) -> bool: return isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)

def validate_generation_index_entry(e, *, is_first=False) -> None:
    # P0-5：冻结 entry schema——精确字段集合（拒绝缺失/额外字段）、类型、SHA 格式。
    # 40/64 契约：genesis_commit 恒为 40-hex Git SHA；首条 entry previous_index_sha256=None，
    # 后续 entry previous_index_sha256 为 64-hex 链前缀 SHA。GenerationIndex.verify 与 final verifier 共用。
    if not isinstance(e, dict): raise ValueError("generation index entry not a dict")
    if set(e) != set(FROZEN_ENTRY_FIELDS): raise ValueError(f"generation index entry fields must be exactly {set(FROZEN_ENTRY_FIELDS)}")
    if not isinstance(e["batch_id"], str) or not e["batch_id"]: raise ValueError("generation index batch_id must be non-empty str")
    if not _is_64hex(e["completed_receipt_sha256"]): raise ValueError("generation index completed_receipt_sha256 must be 64-hex")
    if not _is_40hex(e["genesis_commit"]): raise ValueError("generation index genesis_commit must be 40-hex Git SHA")
    if is_first:
        if e["previous_index_sha256"] is not None: raise ValueError("generation index first entry previous_index_sha256 must be None")
    elif not _is_64hex(e["previous_index_sha256"]):
        raise ValueError("generation index subsequent entry previous_index_sha256 must be 64-hex")

def verify_generation_index_entries(entries, genesis_anchor, expected_head) -> bool:
    expected = genesis_anchor
    for i, e in enumerate(entries):
        try: validate_generation_index_entry(e, is_first=(i == 0))
        except ValueError: return False   # P0-5：schema 门禁，自洽但缺/多字段的 index 也会拒绝
        if e.get("genesis_commit") != genesis_anchor: return False   # 每条约 genesis 锚定
        if i > 0 and e.get("previous_index_sha256") != expected: return False
        expected = generation_index_sha256(entries[:i + 1])
    if expected_head is not None and expected != expected_head: return False
    return True

def repository_identity(git_root) -> str:
    import subprocess as _sp
    r = _sp.run(["git", "-C", str(git_root), "remote", "get-url", "origin"], capture_output=True)
    if r.returncode != 0 or not r.stdout.strip(): raise ValueError("repository has no origin remote; cannot derive repository_identity")
    url = r.stdout.decode("utf-8").strip()
    url = url.replace("git@", "", 1)
    if "://" in url: url = url.split("://", 1)[1]
    if ":" in url and "/" not in url.split(":", 1)[0]: url = url.replace(":", "/", 1)
    if "@" in url: url = url.split("@", 1)[1]
    if url.endswith(".git"): url = url[:-4]
    return url

def _git(git_root, *args):
    import subprocess as _sp; return _sp.run(["git", "-C", str(git_root), *args], capture_output=True)
def _try_git_show(git_root, commit, rel):
    r = _git(git_root, "show", f"{commit}:{rel}")
    return r.stdout if r.returncode == 0 else None
def _git_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
def _is_ancestor(git_root, ancestor, descendant) -> bool:
    return _git(git_root, "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0

def _find_batch_commit(git_root, parent_commit, final_commit, anchor):
    r = _git(git_root, "rev-list", final_commit, "--reverse", "--ancestry-path", "--first-parent", "--not", parent_commit)
    if r.returncode != 0: return None
    for c in r.stdout.decode().split():
        blob = _try_git_show(git_root, c, anchor.get("index_rel"))
        if blob is None: continue
        try: entries = json.loads(blob.decode("utf-8"))
        except Exception: continue
        if generation_index_sha256(entries) != anchor.get("head_sha"): continue
        ab = _try_git_show(git_root, c, anchor.get("anchor_rel"))
        if ab is None: continue
        try: committed_anchor = json.loads(ab.decode("utf-8"))
        except Exception: continue
        if committed_anchor != anchor: continue
        return c
    return None

class GenerationIndex:
    def __init__(self, path, genesis_anchor):
        if not _is_40hex(genesis_anchor) or genesis_anchor == "b1" * 40: raise ValueError("genesis_anchor must be a 40-hex anchor SHA (required, no placeholder)")
        self.path = Path(path); self.genesis = genesis_anchor
    def _load(self): return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []
    def _prefix_sha(self, entries, upto): return generation_index_sha256(entries[:upto])
    def _acquire_lock(self):
        lock = Path(str(self.path) + ".lock")
        while True:
            try:
                fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "start": time.time(), "owner": f"p{os.getpid()}t{time.time():.0f}"}).encode())
                os.close(fd); return lock
            except FileExistsError:
                try: meta = json.loads(Path(lock).read_text(encoding="utf-8"))
                except Exception: raise RuntimeError("index lock held (unparseable)")
                stale = time.time() - meta.get("start", 0) > 3600 and not _pid_alive(meta.get("pid", -1)) and str(meta.get("owner", "")).startswith("p")
                if stale: os.unlink(str(lock)); continue
                raise RuntimeError("index lock held by live writer")
    def append(self, entry):
        lock = self._acquire_lock()
        try:
            entries = self._load()
            if any(e.get("batch_id") == entry.get("batch_id") for e in entries): raise ValueError("duplicate batch_id")
            # P0-1：40/64 契约——每条约 genesis_commit；首条 previous_index_sha256=None，后续为 64-hex 链前缀
            entry["genesis_commit"] = self.genesis
            entry["previous_index_sha256"] = None if not entries else self._prefix_sha(entries, len(entries))
            entries2 = self._load()
            expected = None if not entries2 else self._prefix_sha(entries2, len(entries2))
            if entry["previous_index_sha256"] != expected: raise RuntimeError("CAS failed: concurrent write")
            entries2.append(entry)
            tmp = Path(str(self.path) + ".tmp"); tmp.write_text(json.dumps(entries2, ensure_ascii=False, indent=2), encoding="utf-8"); os.replace(str(tmp), str(self.path))
        finally: os.unlink(str(lock))
    def verify(self, expected_head=None): return verify_generation_index_entries(self._load(), self.genesis, expected_head)
    def find_orphan_entries(self, completed_receipt_sha_set, full_entries=()):
        registered = {e.get("completed_receipt_sha256") for e in self._load()}
        return [e for e in full_entries if e.get("completed_receipt_sha256") in completed_receipt_sha_set - registered]

def finalize_batch(*, batch_id, completed_receipt_path, index_path, genesis_anchor):
    idx = GenerationIndex(index_path, genesis_anchor=genesis_anchor)
    receipt_sha = hashlib.sha256(Path(completed_receipt_path).read_bytes()).hexdigest()
    idx.append({"batch_id": batch_id, "completed_receipt_sha256": receipt_sha})
    entries = idx._load()
    return {"head_sha": generation_index_sha256(entries), "index_entries": entries, "completed_receipt_sha256": receipt_sha}

def batch_anchor_receipt(*, batch_id, parent_commit, head_sha, index_rel, anchor_rel, completed_receipt_rel, completed_receipt_sha256, source_snapshot_sha256, source_snapshot_rel):
    return {"batch_id": batch_id, "parent_commit": parent_commit, "head_sha": head_sha, "index_rel": index_rel, "anchor_rel": anchor_rel, "completed_receipt_rel": completed_receipt_rel, "completed_receipt_sha256": completed_receipt_sha256, "source_snapshot_sha256": source_snapshot_sha256, "source_snapshot_rel": source_snapshot_rel}

def verify_batch_anchors(anchors, git_root, genesis_commit, final_commit=None):
    if not isinstance(anchors, list) or not anchors: return False
    if final_commit is None: final_commit = _git(git_root, "rev-parse", "HEAD").stdout.decode().strip()
    if _git(git_root, "cat-file", "-e", f"{final_commit}^{{commit}}").returncode != 0: return False
    parent = genesis_commit
    for a in anchors:
        if a.get("parent_commit") != parent: return False
        if not _is_ancestor(git_root, genesis_commit, a["parent_commit"]): return False
        if not a.get("anchor_rel"): return False
        c = _find_batch_commit(git_root, a["parent_commit"], final_commit, a)
        if c is None: return False
        if a.get("completed_receipt_rel") and a.get("completed_receipt_sha256"):
            blob = _try_git_show(git_root, c, a["completed_receipt_rel"])
            if blob is None or hashlib.sha256(blob).hexdigest() != a["completed_receipt_sha256"]: return False
        if not a.get("source_snapshot_rel"): return False
        if a.get("source_snapshot_sha256"):
            blob = _try_git_show(git_root, c, a["source_snapshot_rel"])
            if blob is None: return False
            man = json.loads(blob.decode("utf-8")) if blob else {}
            if man.get("snapshot_sha256") != a["source_snapshot_sha256"]: return False
        parent = c
    return _is_ancestor(git_root, parent, final_commit)
```

`scripts/verify_final_anchor.py`（CLI：`--final-anchor --index-rel --audit-rel --git-root --genesis --anchors`，无 `--experiment-id`）：

```python
from __future__ import annotations
import argparse, json, hashlib, subprocess
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.classic_artifacts import (
    EXPERIMENT_ID, generation_index_sha256, _git, _try_git_show,
    verify_batch_anchors, verify_generation_index_entries, repository_identity,
)
_FINAL_ANCHOR_FIELDS = ("schema_version", "final_commit", "generation_index_head_sha256", "final_audit_receipt_sha256", "approver", "approved_at", "batch_count", "last_batch_anchor_sha256", "experiment_id", "repository_identity")

def _git_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

def build_final_anchor_receipt(*, final_commit, generation_index_head_sha256, final_audit_receipt_sha256, approver, approved_at, batch_count, last_batch_anchor_sha256, experiment_id, repository_identity):
    return {"schema_version": "1.0", "final_commit": final_commit, "generation_index_head_sha256": generation_index_head_sha256, "final_audit_receipt_sha256": final_audit_receipt_sha256, "approver": approver, "approved_at": approved_at, "batch_count": batch_count, "last_batch_anchor_sha256": last_batch_anchor_sha256, "experiment_id": experiment_id, "repository_identity": repository_identity}

def verify_final_anchor(receipt_path, *, index_rel, audit_rel, genesis_anchor, git_root, anchors_path):
    rec = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    for k in _FINAL_ANCHOR_FIELDS:
        if k not in rec: raise ValueError(f"final anchor receipt missing {k}")
    if rec["experiment_id"] != EXPERIMENT_ID: raise ValueError("final anchor experiment_id mismatch with frozen EXPERIMENT_ID")
    repo_id = repository_identity(git_root)
    if rec["repository_identity"] != repo_id: raise ValueError("final anchor repository_identity mismatch with current repository")
    final_commit = rec["final_commit"]
    if _git(git_root, "cat-file", "-e", f"{final_commit}^{{commit}}").returncode != 0: raise ValueError("final_commit not an existing reachable commit")
    anchors = json.loads(Path(anchors_path).read_text(encoding="utf-8"))
    if not isinstance(anchors, list) or not anchors: raise ValueError("final anchor anchors must be a non-empty list")
    if not verify_batch_anchors(anchors, git_root, genesis_commit=genesis_anchor, final_commit=final_commit): raise ValueError("final anchor batch anchor chain verification failed")
    blob = _try_git_show(git_root, final_commit, index_rel)
    if blob is None: raise ValueError(f"index blob missing at {final_commit}:{index_rel}")
    entries = json.loads(blob.decode("utf-8")) if blob else []
    if not verify_generation_index_entries(entries, genesis_anchor, rec["generation_index_head_sha256"]): raise ValueError("final anchor index chain verification failed")
    if len(entries) != rec["batch_count"]: raise ValueError(f"final anchor batch_count {rec['batch_count']} != index entries {len(entries)}")
    if _git_sha256(anchors[-1]) != rec["last_batch_anchor_sha256"]: raise ValueError("final anchor last batch anchor SHA mismatch")
    audit_blob = _try_git_show(git_root, final_commit, audit_rel)
    if audit_blob is None: raise ValueError(f"audit blob missing at {final_commit}:{audit_rel}")
    if hashlib.sha256(audit_blob).hexdigest() != rec["final_audit_receipt_sha256"]: raise ValueError("final anchor audit receipt SHA mismatch")
    if not rec.get("approver") or not rec.get("approved_at"): raise ValueError("final anchor missing approver/approved_at")
    return True

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final-anchor", required=True); ap.add_argument("--index-rel", required=True); ap.add_argument("--audit-rel", required=True); ap.add_argument("--git-root", required=True); ap.add_argument("--genesis", required=True); ap.add_argument("--anchors", required=True)
    a = ap.parse_args(argv)
    verify_final_anchor(a.final_anchor, index_rel=a.index_rel, audit_rel=a.audit_rel, genesis_anchor=a.genesis, git_root=a.git_root, anchors_path=a.anchors)
    print("final anchor verified"); return 0

if __name__ == "__main__": raise SystemExit(main())
```

`tests/test_classic_distillation_validator.py`（阶段 8 追加；`_build_chain` 用实际 base commit 作 genesis）：

```python
def _tmp_git(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    return repo
def _repo_rel(repo, path): return str(Path(path).resolve().relative_to(Path(repo).resolve())).replace("\\", "/")
def _git(repo, *args): return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()

def test_repository_identity_normalizes_host_path(tmp_path):
    repo = _tmp_git(tmp_path)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/example/sanming.git"], check=True)
    assert repository_identity(repo) == "github.com/example/sanming"
    subprocess.run(["git", "-C", str(repo), "remote", "set-url", "origin", "git@github.com:example/sanming.git"], check=True)
    assert repository_identity(repo) == "github.com/example/sanming"
    subprocess.run(["git", "-C", str(repo), "remote", "set-url", "origin", "ssh://git@gitlab.com/other/sanming.git"], check=True)
    assert repository_identity(repo) == "gitlab.com/other/sanming"
    subprocess.run(["git", "-C", str(repo), "remote", "set-url", "origin", "https://github.com/example/sanming.git"], check=True)
    gh = repository_identity(repo)
    subprocess.run(["git", "-C", str(repo), "remote", "set-url", "origin", "https://gitlab.com/other/sanming.git"], check=True)
    gl = repository_identity(repo)
    assert gh != gl and gh.endswith("/sanming") and gl.endswith("/sanming")
    with pytest.raises(ValueError, match="origin"): repository_identity(_tmp_git(tmp_path))

def test_verify_generation_index_entries_rejects_internal_chain_break():
    genesis = "0" * 40
    good = [{"batch_id": "b1", "completed_receipt_sha256": "a" * 64, "genesis_commit": genesis, "previous_index_sha256": None}]
    assert verify_generation_index_entries(good, genesis, generation_index_sha256(good)) is True
    tampered = [dict(good[0], previous_index_sha256="f" * 64)]
    assert verify_generation_index_entries(tampered, genesis, generation_index_sha256(tampered)) is False
    # P0-1：缺字段/多字段、genesis_commit 漂移、首条 previous 非 None 均拒绝
    missing = [dict(good[0], previous_index_sha256=None)]
    missing[0].pop("genesis_commit")
    assert verify_generation_index_entries(missing, genesis, None) is False
    drift = [dict(good[0], genesis_commit="f" * 40)]
    assert verify_generation_index_entries(drift, genesis, None) is False
    first_prev = [dict(good[0], previous_index_sha256="a" * 64)]
    assert verify_generation_index_entries(first_prev, genesis, None) is False

def _build_chain(tmp_path):
    repo = _tmp_git(tmp_path)
    genesis = _git(repo, "rev-parse", "HEAD")
    idx_path = repo / "gi.json"
    idx = GenerationIndex(idx_path, genesis_anchor=genesis)
    idx.append({"batch_id": "b1", "completed_receipt_sha256": hashlib.sha256(b"receipt-1").hexdigest()})
    head = generation_index_sha256(idx._load())
    (repo / "out").mkdir()
    (repo / "out" / "completed_receipt.json").write_bytes(b"receipt-1")
    (repo / "out" / "source_manifest.json").write_text(json.dumps({"snapshot_sha256": "s"*64}), encoding="utf-8")
    anchor = batch_anchor_receipt(batch_id="b1", parent_commit=genesis, head_sha=head, index_rel=_repo_rel(repo, idx_path), anchor_rel="out/batch_anchor.json", completed_receipt_rel="out/completed_receipt.json", completed_receipt_sha256=hashlib.sha256(b"receipt-1").hexdigest(), source_snapshot_sha256="s"*64, source_snapshot_rel="out/source_manifest.json")
    (repo / "out" / "batch_anchor.json").write_text(json.dumps(anchor, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "batch Cn"], check=True)
    return repo, genesis, _git(repo, "rev-parse", "HEAD"), idx_path, anchor, head

def test_verify_batch_anchors_git_history_located(tmp_path):
    repo, genesis, cn, idx_path, anchor, head = _build_chain(tmp_path)
    assert verify_batch_anchors([anchor], git_root=repo, genesis_commit=genesis, final_commit=cn) is True
    bad = dict(anchor); bad["parent_commit"] = "0" * 40
    assert verify_batch_anchors([bad], git_root=repo, genesis_commit=genesis, final_commit=cn) is False
    assert verify_batch_anchors([], git_root=repo, genesis_commit=genesis, final_commit=cn) is False

def test_final_anchor_full_chain_verify(tmp_path):
    repo, genesis, cn, idx_path, anchor, head = _build_chain(tmp_path)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/example/sanming.git"], check=True)
    (repo / "audit.txt").write_bytes(b"audit")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "final"], check=True)
    final_commit = _git(repo, "rev-parse", "HEAD")
    rec = build_final_anchor_receipt(final_commit=final_commit, generation_index_head_sha256=head, final_audit_receipt_sha256=hashlib.sha256(b"audit").hexdigest(), approver="lead", approved_at="2026-08-13T00:00:00Z", batch_count=1, last_batch_anchor_sha256=_git_sha256(anchor), experiment_id=EXPERIMENT_ID, repository_identity=repository_identity(repo))
    rec_path = tmp_path / "rec.json"; rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    anchors_path = tmp_path / "anchors.json"; anchors_path.write_text(json.dumps([anchor], ensure_ascii=False), encoding="utf-8")
    verify_final_anchor(rec_path, index_rel="gi.json", audit_rel="audit.txt", genesis_anchor=genesis, git_root=repo, anchors_path=anchors_path)
    bad = dict(rec); bad["experiment_id"] = "other"
    bp = tmp_path / "bad.json"; bp.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="experiment_id"): verify_final_anchor(bp, index_rel="gi.json", audit_rel="audit.txt", genesis_anchor=genesis, git_root=repo, anchors_path=anchors_path)
    bad2 = dict(rec); bad2["generation_index_head_sha256"] = "0" * 64
    bp2 = tmp_path / "bad2.json"; bp2.write_text(json.dumps(bad2), encoding="utf-8")
    with pytest.raises(ValueError, match="head"): verify_final_anchor(bp2, index_rel="gi.json", audit_rel="audit.txt", genesis_anchor=genesis, git_root=repo, anchors_path=anchors_path)
    empty_anchors = tmp_path / "empty.json"; empty_anchors.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"): verify_final_anchor(rec_path, index_rel="gi.json", audit_rel="audit.txt", genesis_anchor=genesis, git_root=repo, anchors_path=empty_anchors)
```

RED → GREEN → 提交。

---

## 阶段 9：完整协议 fake-runner E2E（完整内联 + 修正断言）

`tests/test_classic_distillation_sanming_smoke.py`：

```python
"""完整协议 fake-runner E2E：snapshot -> restore -> 崩溃(attempt1 无 terminal) -> 恢复(published) -> finalize_batch -> git commit -> verify_batch_anchors -> verify_final_anchor。末行断言：receipt["genesis_commit"]==genesis、idx.genesis==genesis、rec["final_commit"]==final_commit。"""
import json, subprocess, hashlib
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parent.parent

def _git_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

def _dispatch_fake(prompt, timeout=300):
    if "提取结构化命理规则" in prompt: return '[{"rule":"甲木日主喜水","condition":"甲木生于寅月","subject":"甲木","original_text":"甲木喜水"}]'
    if "生成一道四选一选择题" in prompt: return '{"question":"甲木喜什么？","options":{"A":"喜水滋润","B":"火","C":"土","D":"金"},"answer":"A","explanation":"甲木喜水"}'
    return "[]"

def _mk_snapshot(tmp_path, text="第一段。\n\n第二段。\n" * 40):
    from scripts.fetch_sanming_chapters import ChapterEntry, build_and_publish_snapshot, read_active_snapshot, materialization_status, restore_responses
    body = b"B"
    def factory(entries):
        return [{"chapter_index": e.index, "title": e.title, "url": e.url, "response_body_sha256": hashlib.sha256(body).hexdigest(), "extracted_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "extractor_sha256": "x"*64, "normalized_page_title": e.title, "response_body_status": "archived", "provenance_level": "full", "encoding": "utf-8", "extracted_text": text, "response_body": body, "ok": True} for e in entries]
    formal = tmp_path / "formal"
    build_and_publish_snapshot([ChapterEntry(81, "卷六·论命", "u1")], formal, records_factory=factory, archive_root=tmp_path / "store")
    act = read_active_snapshot(formal); sha = act["snapshot_sha256"]
    restore_responses(formal, sha, archive_root=tmp_path / "store")
    assert materialization_status(formal, sha) == "materialized"
    return formal / "source_snapshots" / sha / "extracted", act, formal

def _mk_manifest(tmp_path, batch_id, snapshot_dir, out_dir, repo, head, seg_sha, cfg_sha, code_sha, pre_run_sha, parent, snap_shas):
    from scripts.distill_lib import EXPERIMENT_ID
    m = {"schema_version": "1.0", "batch_id": batch_id, "selected_chapter_ids": [81], "source_sha_map": {"81": hashlib.sha256((snapshot_dir / "raw_081.txt").read_bytes()).hexdigest()}, "segment_manifest_sha": seg_sha, "pre_run_output_sha": pre_run_sha, "model_prompt_config_sha": cfg_sha, "batch_hard_cap": 100, "parent_commit": parent, "parent_head_sha": head, "code_sha": code_sha, "rules_sha": "0"*64, "source_snapshot_sha256": snap_shas["snapshot"], "source_manifest_sha256": snap_shas["manifest"], "source_archive_pointer_sha256": snap_shas["pointer"], "experiment_id": EXPERIMENT_ID}
    p = tmp_path / f"{batch_id}.json"; p.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8"); return p

def _run_batch(tmp_path, monkeypatch, mp, snap_dir, out, repo, formal, act, fake_call, genesis_anchor="0"*40, generation_index_path=None):
    import scripts.distill_lib as dl
    from scripts.fill_missing_chapters import run_sanming_batch
    monkeypatch.setattr(dl, "_call", fake_call)
    return run_sanming_batch(mp, snapshot_dir=snap_dir, out_dir=out, formal_dir=formal, snapshot_sha=act["snapshot_sha256"], proj_ledger_path=tmp_path / "project.json", run_ledger_path=tmp_path / "run.json", run_id="R1", project_total_cap=1000, scripts_dir=Path("scripts"), root=ROOT, git_root=repo, genesis_anchor=genesis_anchor, generation_index_path=generation_index_path)

def _git(repo, *args): return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()

def test_e2e_full_protocol_crash_then_resume(tmp_path, monkeypatch):
    import scripts.distill_lib as dl
    from scripts.fetch_sanming_chapters import _file_sha256
    from scripts.fill_missing_chapters import _segment_manifest_sha, _model_prompt_config_sha, _code_sha_now
    from scripts.classic_artifacts import GenerationIndex, generation_index_sha256, finalize_batch, batch_anchor_receipt, verify_batch_anchors, repository_identity
    from scripts.verify_final_anchor import build_final_anchor_receipt, verify_final_anchor
    snap_dir, act, formal = _mk_snapshot(tmp_path)
    out = tmp_path / "book"; out.mkdir()
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/example/sanming.git"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    genesis = _git(repo, "rev-parse", "HEAD")
    segs = {81: dl.segment_chapter((snap_dir / "raw_081.txt").read_text(encoding="utf-8"), book="sanmingtonghui", chapter="81", limits=dl.PromptLimits())}
    code_sha = _code_sha_now(Path("scripts"), ROOT)
    pre_run_sha = hashlib.sha256(json.dumps({}, sort_keys=True).encode()).hexdigest()
    snap_dir_path = formal / "source_snapshots" / act["snapshot_sha256"]
    snap_shas = {"snapshot": act["snapshot_sha256"], "manifest": act["source_manifest_sha256"], "pointer": _file_sha256(snap_dir_path / "RESPONSE_ARCHIVE_POINTER.json")}
    mp = _mk_manifest(tmp_path, "B1", snap_dir, out, repo, genesis, seg_sha=_segment_manifest_sha(segs), cfg_sha=_model_prompt_config_sha(), code_sha=code_sha, pre_run_sha=pre_run_sha, parent=genesis, snap_shas=snap_shas)
    # 运行 1：KeyboardInterrupt 崩溃
    def kbi(*a, **k): raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt): _run_batch(tmp_path, monkeypatch, mp, snap_dir, out, repo, formal, act, kbi, genesis_anchor=genesis)
    from scripts.distill_lib import attempt_base_id, next_attempt_no, attempt_id_for
    proj1 = dl.ProjectLedger.load_or_create(tmp_path / "project.json", experiment_id=dl.EXPERIMENT_ID, total_cap=1000)
    run1 = dl.BudgetLedger.load_or_create(tmp_path / "run.json", global_hard_cap=100, run_id="R1", code_sha=code_sha, rules_sha="0"*64)
    base = attempt_base_id(run_id="R1", batch_id="B1", chapter_id=80, segment_id=0, operation="rules", rule_id=None)
    att1 = attempt_id_for(run_id="R1", batch_id="B1", chapter_id=80, segment_id=0, operation="rules", rule_id=None, attempt_no=1)
    assert proj1.calls_made == 1 and run1.calls_made == 1
    assert run1.attempts[att1]["status"] == "attempted"
    assert next_attempt_no(run1, base_id=base) == 2
    # 运行 2：恢复，从 attempt2 起成功
    res2 = _run_batch(tmp_path, monkeypatch, mp, snap_dir, out, repo, formal, act, _dispatch_fake, genesis_anchor=genesis)
    assert res2["status"] == "published"
    run2 = dl.BudgetLedger.load_or_create(tmp_path / "run.json", global_hard_cap=100, run_id="R1", code_sha=code_sha, rules_sha="0"*64)
    proj2 = dl.ProjectLedger.load_or_create(tmp_path / "project.json", experiment_id=dl.EXPERIMENT_ID, total_cap=1000)
    assert proj2.calls_made == run2.calls_made
    att2 = attempt_id_for(run_id="R1", batch_id="B1", chapter_id=80, segment_id=0, operation="rules", rule_id=None, attempt_no=2)
    assert run2.attempts[att2]["status"] == "success"
    # finalize + anchor + final-anchor
    gi = tmp_path / "gi.json"
    idx = GenerationIndex(gi, genesis_anchor=genesis)
    receipt = out / ".batch" / "B1" / "completed_receipt.json"
    fin = finalize_batch(batch_id="B1", completed_receipt_path=receipt, index_path=gi, genesis_anchor=genesis)
    (repo / "out").mkdir(exist_ok=True)
    (repo / "out" / "all_rules.json").write_bytes((out / "all_rules.json").read_bytes())
    (repo / "out" / "completed_receipt.json").write_bytes(receipt.read_bytes())
    (repo / "gi.json").write_bytes(gi.read_bytes())
    (repo / "out" / "source_manifest.json").write_bytes((snap_dir_path / "source_manifest.json").read_bytes())
    anchor = batch_anchor_receipt(batch_id="B1", parent_commit=genesis, head_sha=fin["head_sha"], index_rel="gi.json", anchor_rel="out/batch_anchor.json", completed_receipt_rel="out/completed_receipt.json", completed_receipt_sha256=fin["completed_receipt_sha256"], source_snapshot_sha256=act["snapshot_sha256"], source_snapshot_rel="out/source_manifest.json")
    (repo / "out" / "batch_anchor.json").write_text(json.dumps(anchor, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "batch Cn"], check=True)
    cn = _git(repo, "rev-parse", "HEAD")
    assert verify_batch_anchors([anchor], git_root=repo, genesis_commit=genesis, final_commit=cn) is True
    assert idx.verify() is True
    full_head = generation_index_sha256(idx._load())
    assert idx.verify(expected_head=full_head) is True
    audit = repo / "audit.txt"; audit.write_bytes(b"audit")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "final"], check=True)
    final_commit = _git(repo, "rev-parse", "HEAD")
    repo_identity = repository_identity(repo)
    from scripts.classic_artifacts import EXPERIMENT_ID
    rec = build_final_anchor_receipt(final_commit=final_commit, generation_index_head_sha256=full_head, final_audit_receipt_sha256=hashlib.sha256(b"audit").hexdigest(), approver="lead", approved_at="2026-08-13T00:00:00Z", batch_count=1, last_batch_anchor_sha256=_git_sha256(anchor), experiment_id=EXPERIMENT_ID, repository_identity=repo_identity)
    rec_path = tmp_path / "rec.json"; rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    anchors_path = tmp_path / "anchors.json"; anchors_path.write_text(json.dumps([anchor], ensure_ascii=False), encoding="utf-8")
    verify_final_anchor(rec_path, index_rel="gi.json", audit_rel="audit.txt", genesis_anchor=genesis, git_root=repo, anchors_path=anchors_path)
    # P0-3：三条独立断言
    assert json.loads(receipt.read_text(encoding="utf-8"))["genesis_commit"] == genesis
    assert idx.genesis == genesis
    assert rec["final_commit"] == final_commit

def test_e2e_always_down_never_publishes(tmp_path, monkeypatch):
    import scripts.distill_lib as dl
    from scripts.fetch_sanming_chapters import _file_sha256
    from scripts.fill_missing_chapters import _segment_manifest_sha, _model_prompt_config_sha, _code_sha_now
    snap_dir, act, formal = _mk_snapshot(tmp_path)
    out = tmp_path / "book"; out.mkdir()
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True); subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    head0 = _git(repo, "rev-parse", "HEAD")
    segs = {81: dl.segment_chapter((snap_dir / "raw_081.txt").read_text(encoding="utf-8"), book="sanmingtonghui", chapter="81", limits=dl.PromptLimits())}
    pre_run_sha = hashlib.sha256(json.dumps({}, sort_keys=True).encode()).hexdigest()
    snap_dir_path = formal / "source_snapshots" / act["snapshot_sha256"]
    snap_shas = {"snapshot": act["snapshot_sha256"], "manifest": act["source_manifest_sha256"], "pointer": _file_sha256(snap_dir_path / "RESPONSE_ARCHIVE_POINTER.json")}
    mp = _mk_manifest(tmp_path, "B2", snap_dir, out, repo, head0, seg_sha=_segment_manifest_sha(segs), cfg_sha=_model_prompt_config_sha(), code_sha=_code_sha_now(Path("scripts"), ROOT), pre_run_sha=pre_run_sha, parent=head0, snap_shas=snap_shas)
    def boom(*a, **k): raise RuntimeError("network down")
    res = _run_batch(tmp_path, monkeypatch, mp, snap_dir, out, repo, formal, act, boom, genesis_anchor=head0)
    assert res["status"] == "resume"
    assert not (out / "all_rules.json").exists()
    assert not (out / ".batch_staging" / "B2").exists()
```

RED → GREEN → 提交。

---

## 阶段 10：聚焦回归 + 全量门禁

`pytest tests/test_classic_distillation_remediation.py tests/test_classic_distillation_validator.py tests/test_fetch_sanming_chapters.py tests/test_canonical_tar_golden.py tests/test_historical_exemption.py tests/test_make_historical_exemption.py tests/test_classic_distillation_sanming_smoke.py -q` → 全 PASS。

`ruff check . ; python -m pytest tests/ -q --tb=short --timeout=120 --ignore=tests/test_e2e.py` → 退出 0。

### 临时证明模块验证（可复现，显式冻结可写 `--basetemp`）

本计划的 5 个 P0 修复在生产代码落地前，由自包含临时模块 `.tmp/sanming_p0_proof/test_sanming_p0_fixes.py`（内联完整生产链，fake_flow 直接调用计划版 `run_sanming_batch()`）证明可执行。命令显式冻结项目内可写 `--basetemp`，避免默认 pytest 临时目录权限问题：

```powershell
.venv\Scripts\python.exe -m pytest .tmp\sanming_p0_proof\test_sanming_p0_fixes.py --collect-only -q
.venv\Scripts\python.exe -m pytest .tmp\sanming_p0_proof\test_sanming_p0_fixes.py -k "restore or legacy or progress or backfill or generation_index or cleanup" -q --basetemp .tmp\sanming_p0_proof\basetemp
.venv\Scripts\python.exe -m pytest .tmp\sanming_p0_proof\test_sanming_p0_fixes.py -k "fake_flow" -q --basetemp .tmp\sanming_p0_proof\basetemp_fake
```

当前基线：29 collected 全 PASS（含真实前 80 章 1727 条守恒、逐记录映射、一对多冲突、cleanup 篡改 pending 指向另一 batch 负向、finalize 后篡改指纹 -> completed_cleanup_blocked 完整链负向、fake_flow 全生命周期）。临时模块属 `.tmp/` 运行产物，不提交、不进入最终仓库。

---

## 自审清单（v3.12.3）

- [x] **P0-1**：Phase 7 helper 块顶部显式导入全部依赖（`hashlib/json/subprocess/shutil/pytest`、`Path`、`dl`）。
- [x] **P0-2**：`_update_progress` 的 `done` = 既有 ∪ 本批章节标题；不从 rules 反推，真实标题 `source_chapter` 不再触发 int() 异常。
- [x] **P0-3**：`_backfill_staging_keys` 生产接线（seed 之后、生成新规则之前）；`backfill_canonical_keys` 原子写；provenance receipt 记录 input/output SHA、规则数、ID 集 SHA。
- [x] **P0-4**：completed 幂等经 `GenerationIndex.verify()` 验证完整 hash chain + genesis，再匹配 `(batch_id, completed_receipt_sha256)` 与 entry schema。
- [x] **P0-5**：`before_legacy_call()` 锁内原子 cap 检查 + 计数；legacy 调用方（distill_chapter/generate_mcq）改用；`record_call` 降为兼容桩。
- [x] **P0-6**：`restore_responses` 先验证 active pointer（snapshot_sha256 + manifest 文件字节 SHA）；成员集负向测试同步 active pointer 到上游自洽。
- [x] **中优**：cleanup 成功删除 cleanup_pending.json；幂等测试 genesis 用 fake repo 实际 base commit；backfill 测试加规则数/顺序守恒；阶段 0 commit 消息 v3.12.3；新增 legacy hard cap 临界值测试与 active pointer 漂移负向测试。
- [x] **复审 P0-1**：restore active pointer 闭环校验先于幂等返回；新增"已物化后篡改 active pointer 拒绝"测试。
- [x] **复审 P0-2**：`generate_mcq` 删除循环外预扣；每个真实 attempt 仅紧邻 `_call` 前经 `before_legacy_call()` 原子扣账一次；断言单次成功调用 `legacy_calls=1`。
- [x] **复审 P0-3**：progress 重建经 `_record_progress_reconcile` 在 `remediation_meta.json` 显式记录输入/输出 SHA、数量差异与 ID 命名空间说明。
- [x] **复审 P0-4**：`test_backfill_front80_keeps_ids` 按原始对象序列逐项断言仅允许新增 4 字段、既有字段与顺序不变。
- [x] **复审 P0-5**：`validate_generation_index_entry` 冻结 entry schema，`verify_generation_index_entries` 与 `GenerationIndex.verify()` 共用。
- [x] **复审中优**：`_fill_real_shas`/`_run` 改用 `ROOT`；`_retry_pending_cleanup` 幂等入口重试未完成 cleanup；版本号统一 v3.12.3。
- [x] **复审 2 P0-1**：GenerationIndex 40/64 契约拆分——`genesis_commit` 恒 40-hex；首条 `previous_index_sha256=None`；`validate_generation_index_entry(e, *, is_first=...)` 共用；真实 40-hex genesis 首条通过 `verify()`。
- [x] **复审 2 P0-2**：`_retry_pending_cleanup` 移到 completed receipt 身份校验后，校验 batch/genesis、绝对路径落在 out_dir 内、目录名匹配 `^\.publish_backup_\d+_\d+$` 才删除；新增路径逃逸/绝对路径/错误 batch 负向测试。
- [x] **复审 2 P0-3**：临时证明模块内联计划版完整生产链，fake_flow 直接调用 `run_sanming_batch()`（manifest/双账本/staging publish/completed receipt/cleanup/GenerationIndex finalize），不再平行简化。
- [x] **复审 2 中优**：entry schema 精确断言 `set(e) == FROZEN_ENTRY_FIELDS`；progress reconcile 产出逐记录 `mapped`/`conflicts`/`unmappable` + 各自 canonical SHA；cleanup 新逻辑进入临时证明模块；验证命令显式冻结可写 `--basetemp`。
- [x] **复审 3 P0-1**：completed 幂等匹配删除手写 `previous_index_sha256` 长度条件，只精确匹配 `(batch_id, completed_receipt_sha256, genesis_commit)`；proof 与计划逐字同源（AST 对比通过）。
- [x] **复审 3 P0-2**：progress 逐记录映射（mapped/conflicts/unmappable + canonical SHA），`mapped+conflicts+unmappable == len(old_rules)` 守恒；真实前 80 章副本守恒测试断言 1727。
- [x] **复审 3 P0-3**：`backup_dir` + 内容指纹冻结进 completed receipt（收进 `completed_receipt_sha256`，index 认证）；cleanup 只在 completed_idempotent（index 认证后）分支重试，目标与指纹取自已认证 receipt 冻结值、忽略可变 `cleanup_pending.json`；未 finalize 不做 cleanup；新增"篡改 pending 指向另一 batch"与"内容指纹不匹配"负向测试；`cleanup_pending.output_shas` 不再承担权威校验。
- [x] **复审 4 P0**：`_retry_pending_cleanup` 显式返回 `noop`/`cleaned`/`blocked`，任何身份/路径/指纹/解析/文件系统失败（含 `rmtree` 部分删除后失败）都返回 `blocked` 不再静默吞掉；`run_sanming_batch` 只在 `noop`/`cleaned` 返回 `completed_idempotent`，`blocked` 返回 `completed_cleanup_blocked`（pending 与备份保留）。新增完整链负向测试：finalize 后篡改备份内容 -> 不调 API、不删目录、非 completed_idempotent；另增 pending 解析失败与 `rmtree` 失败 blocked 测试。proof 与计划逐字同源（AST 对比通过）。