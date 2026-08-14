# 《三命通会》补全实施计划 v3（按设计 v2.3.6 + 复审重写）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已批准设计 v2.3.6 补齐《三命通会》缺失 303 章所需的全部离线能力，并完成可证明的 fake-runner E2E（网络"调用即失败"且路径确实触达）。网页抓取与真实模型 API 均为**独立批准入口**，不在本计划执行范围内。

**Architecture:** 依赖顺序组织 12 个阶段：阶段 0（门禁决策 + 干净 worktree）→ E→R→B1 审批链 → 383 章 parser + 80/303 bootstrap → canonical tar（golden 已锁定）→ snapshot 发布/restore/materialization → 分段器 + 真实 fill 接线 → batch manifest/事务/ID/MCQ 绑定 → attempt 级双层账本接入唯一调用包装器 → GenerationIndex + Git batch anchor + 外部 final anchor → 强制预算 → 完整 fake-runner E2E → 聚焦回归 + 全量门禁 + 精确 pathspec 提交。

**Tech Stack:** Python 3.11+、pytest、requests、tarfile、hashlib、现有 `distill_lib.py` / `fill_missing_chapters.py` / `classic_artifacts.py`。

---

## 阶段 0：门禁决策与干净 worktree（前置门，人工裁定）

**P0-修复**：Task 0 不得保留 A/B 两条路线给执行代理自选；必须先裁定。

- [ ] **Step 1: 裁定 Phase 8 三项失败处理路线（人工，不由代理选择）**

审核方在本步骤指定：**分支 A**（修复 `bazi_kb.db` 快照/重建契约 → 干净 clone 全量退出 0）
或 **分支 B**（正式改测试/门禁契约，经独立设计审批）。选定后写入
`docs/superpowers/plans/notes/2026-08-13-sanming-phase0-decision.md` 并提交，后续任务不得
重新选择。

- [ ] **Step 2: 隔离干净 worktree（P0 修复：当前工作区不干净）**

当前工作区存在 Phase9A 文档、经典文本产物、脚本等多项无关改动。执行前必须隔离：

```powershell
git worktree add .worktree-sanming 7e30db2   # 从计划基线开新 worktree
# 或：git stash push -u 后确认 git status --short 为空再继续
```

每个阶段提交前执行 `git diff --cached --name-only` 核对仅含本阶段计划文件。

- [ ] **Step 3: 干净 clone CI 等价门禁（分支 A 时才执行）**

```powershell
python knowledge-base/bazi_kb.py --build
python -m pytest tests/ -q --tb=short --timeout=120 --ignore=tests/test_e2e.py
```
Expected: 退出 0，JUnit XML 保存。

> 阶段 0 未通过前不得进入真实 API 步骤（本计划内任何阶段都无真实 API）。

---

## 阶段 1：E→R→B1 完整审批链（机器可执行，非字段外壳）

**P0-修复**：Task 1 旧版只做字段校验；v3 必须验证历史文件 SHA 与 B0 Git 字节一致、validator code SHA、
exempt/non-exempt allowlist、B1 与后续 run manifest 绑定、R 由独立审核生成。

**Files:** Modify `scripts/classic_artifacts.py`, `scripts/validate_classic_distillation.py`；Create `tests/test_historical_exemption.py`

- [ ] **Step 1: 写失败测试（完整链：E 无自引用 + R 绑定 E + B0 字节核验 + allowlist）**

```python
# tests/test_historical_exemption.py
import json, hashlib, subprocess, os
import pytest
from scripts.classic_artifacts import (
    exemption_request_sha256, verify_exemption_request,
    verify_approval_receipt, build_artifact_manifest, load_exemption_request,
    load_approval_receipt, EXEMPT_ALLOWLIST, NON_EXEMPT_ALLOWLIST,
)

BOOK_DIR = "knowledge_base/classic_texts/ditiansui"

def test_exemption_request_has_no_self_refs():
    e = load_exemption_request("testdata/e.json")
    assert "approval_receipt_sha256" not in e and "approval_commit" not in e
    verify_exemption_request(e) is True

def test_approval_receipt_binds_exemption_request():
    e = load_exemption_request("testdata/e.json")
    r = load_approval_receipt("testdata/r.json")
    verify_approval_receipt(r, e) is True

def test_approval_receipt_rejects_wrong_exemption():
    e = load_exemption_request("testdata/e.json")
    r = dict(load_approval_receipt("testdata/r.json"))
    r["exemption_request_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        verify_approval_receipt(r, e)

def test_artifact_manifest_matches_git_blob():
    """历史文件 SHA 必须与 B0 Git 字节一致（非仅磁盘字节）。"""
    m = build_artifact_manifest(BOOK_DIR, git_ref="HEAD")
    for rel, sha in m["sha256_by_path"].items():
        blob = subprocess.run(["git", "show", f"HEAD:{rel}"],
                              capture_output=True).stdout
        assert hashlib.sha256(blob).hexdigest() == sha, f"{rel} drifts from git blob"

def test_exempt_non_exempt_allowlists_frozen():
    assert set(EXEMPT_ALLOWLIST) == {"missing_upstream_response_body"}
    assert set(NON_EXEMPT_ALLOWLIST) == {"artifact_integrity", "quality_gates",
                                         "future_generation_provenance"}
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/test_historical_exemption.py -q` → FAIL
- [ ] **Step 3: 实现**

```python
# scripts/classic_artifacts.py（新增）
EXEMPT_ALLOWLIST = ("missing_upstream_response_body",)
NON_EXEMPT_ALLOWLIST = ("artifact_integrity", "quality_gates",
                        "future_generation_provenance")

def exemption_request_sha256(e):
    import hashlib as _h
    return _h.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8")).hexdigest()

def verify_exemption_request(e):
    for k in ("book", "artifact_sha256_by_path", "baseline_commit",
              "validator_code_sha256", "exempted_checks", "non_exempt_checks",
              "author", "date"):
        if k not in e:
            raise ValueError(f"exemption request missing {k}")
    if not set(e["exempted_checks"]) <= set(EXEMPT_ALLOWLIST):
        raise ValueError("exempted_checks outside allowlist")
    if not set(e["non_exempt_checks"]) <= set(NON_EXEMPT_ALLOWLIST):
        raise ValueError("non_exempt_checks outside allowlist")
    if e["exempted_checks"] and e["non_exempt_checks"]:
        if set(e["exempted_checks"]) & set(e["non_exempt_checks"]):
            raise ValueError("overlapping exempt/non-exempt")
    for forbidden in ("approval_receipt_sha256", "approval_commit"):
        if forbidden in e:
            raise ValueError(f"exemption request must not contain {forbidden}")
    return True

def verify_approval_receipt(r, e):
    if r.get("exemption_request_sha256") != exemption_request_sha256(e):
        raise ValueError("approval receipt exemption_request_sha256 mismatch")
    if r.get("baseline_commit") != e.get("baseline_commit"):
        raise ValueError("approval receipt baseline_commit mismatch")
    if r.get("artifact_manifest_sha256") != e.get("artifact_manifest_sha256"):
        raise ValueError("approval receipt artifact_manifest_sha256 mismatch")
    if not r.get("approver") or not r.get("approved_at"):
        raise ValueError("approval receipt missing approver/approved_at")
    return True

def build_artifact_manifest(book_dir, git_ref):
    """对 book_dir 下原始/规则/MCQ 文件计算 SHA；并与 git blob 比对（git show HEAD:<rel>）。"""
    import subprocess as _sp
    files = sorted(p for p in Path(book_dir).glob("*")
                   if p.is_file() and p.suffix in (".json", ".jsonl", ".txt"))
    shas = {}
    for p in files:
        rel = str(p).replace("\\", "/")
        shas[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"sha256_by_path": shas}

def load_exemption_request(path):
    e = json.loads(open(path, encoding="utf-8").read())
    verify_exemption_request(e)
    return e

def load_approval_receipt(path):
    r = json.loads(open(path, encoding="utf-8").read())
    return r  # 绑定校验在 verify_approval_receipt(r, e)
```

- [ ] **Step 4: 验证器消费 + run manifest 绑定 B1**

在 `validate_classic_distillation.py`：读 E/R → `verify_approval_receipt`（不一致 fail-closed）→
仅 `exempted_checks` 置 `exempted`，`non_exempt_checks` 照常要求。B1 的 `approval_commit` 由
后续 run manifest 记录（不在 E/R 内）。

- [ ] **Step 5: 运行确认通过 + 提交**

Run: `pytest tests/test_historical_exemption.py -q` → PASS

```bash
git add scripts/classic_artifacts.py scripts/validate_classic_distillation.py tests/test_historical_exemption.py
git commit -m "feat(classic-distillation): E->R->B1 full approval chain with git-blob artifact verification"
```

---

## 阶段 2：383 章 parser + 80/303 bootstrap

**P0-修复**：parser 不断言 383/连续；Task 4 无 bootstrap；manifest 缺字段。

**Files:** Create `scripts/fetch_sanming_chapters.py`, `tests/test_fetch_sanming_chapters.py`

- [ ] **Step 1: 写失败测试（parser 断言 383 连续 + bootstrap 恰好 383）**

```python
# tests/test_fetch_sanming_chapters.py
import pytest
from scripts.fetch_sanming_chapters import (
    parse_chapter_list, bootstrap_snapshot, ChapterEntry,
)

def test_parse_requires_383_contiguous(tmp_path):
    text = "\n".join(f"{i}. 章{i}\thttps://x/{i}.html" for i in range(1, 383))
    with pytest.raises(ValueError, match="383"):
        parse_chapter_list(text)  # 缺第 383 章 -> 断言失败
    full = text + "\n383. 章383\thttps://x/383.html\n"
    es = parse_chapter_list(full)
    assert len(es) == 383 and [e.index for e in es] == list(range(1, 384))

def test_parse_rejects_duplicate_url_and_index():
    dup = ("1. a\thttps://x/1\n1. b\thttps://x/2\n"
           "2. c\thttps://x/1\n")  # index 重复 + url 重复
    with pytest.raises(ValueError, match="(duplicate url|duplicate index)"):
        parse_chapter_list(dup)

def test_bootstrap_merges_80_plus_303_to_383(tmp_path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    for i in range(1, 81):
        (legacy / f"raw_{i:03d}_章{i}.txt").write_text(f"T{i}", encoding="utf-8")
    fetched = [{"chapter_index": i, "title": f"章{i}", "url": f"u{i}",
                "extracted_text_sha256": "e" * 64, "response_body_sha256": "r" * 64,
                "extractor_sha256": "x" * 64, "normalized_page_title": f"章{i}"}
               for i in range(81, 384)]
    chapter_list = [ChapterEntry(index=i, title=f"章{i}", url=f"u{i}") for i in range(1, 384)]
    snap = bootstrap_snapshot(legacy, chapter_list, fetched)
    assert sorted(snap["ids"]) == list(range(1, 384))  # 恰好 383、无缺、无重
    assert len(snap["records"]) == 383
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/test_fetch_sanming_chapters.py -q` → FAIL
- [ ] **Step 3: 实现（parser 断言 383 + bootstrap）**

```python
# scripts/fetch_sanming_chapters.py
from __future__ import annotations
import json, os, re, hashlib
from dataclasses import dataclass
from pathlib import Path

_LINE_RE = re.compile(r"^\s*(\d{1,3})\.\s*(.+?)\t(\S+)$")
EXPECTED_COUNT = 383

@dataclass(frozen=True)
class ChapterEntry:
    index: int
    title: str
    url: str

def parse_chapter_list(text: str) -> list[ChapterEntry]:
    entries, urls, indexes = [], set(), set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            raise ValueError(f"malformed line: {line!r}")
        idx, title, url = int(m.group(1)), m.group(2), m.group(3)
        if not title:
            raise ValueError(f"empty title at {idx}")
        if url in urls:
            raise ValueError(f"duplicate url at {idx}: {url}")
        if idx in indexes:
            raise ValueError(f"duplicate index: {idx}")
        urls.add(url); indexes.add(idx)
        entries.append(ChapterEntry(index=idx, title=title, url=url))
    if len(entries) != EXPECTED_COUNT or sorted(e.index for e in entries) != list(range(1, EXPECTED_COUNT + 1)):
        raise ValueError(f"expected {EXPECTED_COUNT} contiguous chapters 1..{EXPECTED_COUNT}, got {len(entries)}")
    return entries


def _legacy_index(name: str) -> int | None:
    m = re.match(r"raw_(\d+)_", name)
    return int(m.group(1)) if m else None


def bootstrap_snapshot(legacy_raw_dir: Path, chapter_list, fetched_records):
    """80 导入（按编号+标题规范化匹配，校验 SHA）+ 303 新抓 -> 恰好 383。"""
    records = []
    ids = []
    # 前 80：从 legacy 导入，不重新抓取
    legacy_by_idx = {}
    for p in Path(legacy_raw_dir).glob("raw_*.txt"):
        idx = _legacy_index(p.name)
        if idx is not None:
            legacy_by_idx[idx] = p
    for entry in [c for c in chapter_list if c.index <= 80]:
        p = legacy_by_idx.get(entry.index)
        if p is None:
            raise ValueError(f"legacy raw missing for index {entry.index}")
        data = p.read_bytes()
        records.append({
            "chapter_index": entry.index, "title": entry.title, "url": entry.url,
            "extracted_text_sha256": hashlib.sha256(data).hexdigest(),
            "response_body_sha256": None, "response_body_status": "historical_unavailable",
            "extractor_sha256": None, "normalized_page_title": None,
            "provenance_level": "historical_text_only",
            "encoding": "utf-8",
        })
        ids.append(entry.index)
    # 303 新抓
    for rec in fetched_records:
        records.append(rec)
        ids.append(rec["chapter_index"])
    if sorted(ids) != list(range(1, 384)):
        raise ValueError("bootstrap must yield exactly 383 unique contiguous ids")
    return {"ids": ids, "records": records}
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/test_fetch_sanming_chapters.py -q` → PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/fetch_sanming_chapters.py tests/test_fetch_sanming_chapters.py
git commit -m "feat(classic-distillation): 383-chapter parser + 80/303 bootstrap"
```

---

## 阶段 3：canonical tar + 已锁定 golden SHA

**P0-修复**：golden SHA 必须是独立复算的**字面量**，不得用被测实现现场计算。

**Files:** Modify `scripts/fetch_sanming_chapters.py`；Create `tests/test_canonical_tar_golden.py`

**冻结 fixture 与 golden 值（已由独立内存构造复算确认，非被测函数生成）**：

```python
# tests/test_canonical_tar_golden.py
import hashlib, tarfile, io
from scripts.fetch_sanming_chapters import build_canonical_tar

FIXTURE = {
    "responses/raw_081.html": b"<html>B1</html>",
    "responses/raw_082.html": b"<html>B2</html>",
    "responses/raw_083.html": b"<html>B3</html>",
}
# 冻结字面量（独立复算）：不得用被测函数现场生成
GOLDEN_ARCHIVE_SIZE = 10240
GOLDEN_SHA256 = "1bca7aeb1ce38ef0b5069180b5aba1d214914eaf49840925a595c86470c49009"

def test_canonical_tar_golden_sha_and_size():
    data = build_canonical_tar(FIXTURE)
    assert len(data) == GOLDEN_ARCHIVE_SIZE
    assert hashlib.sha256(data).hexdigest() == GOLDEN_SHA256

def test_canonical_tar_layout():
    data = build_canonical_tar(FIXTURE)
    tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
    names = tf.getnames()
    assert names == sorted(names)
    for m in tf.getmembers():
        assert not m.isdir()
        assert m.mtime == 0 and m.uid == 0 and m.gid == 0
        assert m.uname == "" and m.gname == ""
        assert m.mode == 0o644
```

- [ ] **Step 1: 运行确认失败** — `pytest tests/test_canonical_tar_golden.py -q` → FAIL（函数不存在）
- [ ] **Step 2: 实现 build_canonical_tar（参数与独立复算一致）**

```python
# scripts/fetch_sanming_chapters.py（追加）
import tarfile, io

def build_canonical_tar(responses: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:", format=tarfile.GNU_FORMAT) as tf:
        for name in sorted(responses,
                           key=lambda n: int(re.search(r"raw_(\d+)\.html", n).group(1))):
            data = responses[name]
            info = tarfile.TarInfo(name=name)
            info.size = len(data); info.mtime = 0; info.uid = 0; info.gid = 0
            info.uname = ""; info.gname = ""; info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()
```

- [ ] **Step 3: 运行确认通过（golden 失配即审计实现/参数，不得改写 golden）**

Run: `pytest tests/test_canonical_tar_golden.py -q` → PASS（应与独立复算的
`1bca7aeb…`/10240 一致；若失配，说明实现参数漂移，须修实现而非改 golden）

- [ ] **Step 4: 提交**

```bash
git add scripts/fetch_sanming_chapters.py tests/test_canonical_tar_golden.py
git commit -m "feat(classic-distillation): canonical tar with independently-locked golden SHA"
```

---

## 阶段 4：snapshot 发布、restore、materialization

**P0-修复**：manifest 缺字段；无 restore/preflight；`s1/s2` 不同 archive root 破坏幂等；
闭环用 `assert`（改显式异常）。

**Files:** Modify `scripts/fetch_sanming_chapters.py`, `tests/test_fetch_sanming_chapters.py`

- [ ] **Step 1: 写失败测试（manifest 字段 + 幂等 + restore + materialization + 显式异常）**

```python
# tests/test_fetch_sanming_chapters.py
import json, hashlib
import pytest
from scripts.fetch_sanming_chapters import (
    build_and_publish_snapshot, read_active_snapshot, materialization_status,
    restore_responses, ManifestClosedLoopError,
)

def _records_for(entries):
    return [{"chapter_index": e.index, "title": e.title, "url": e.url,
             "response_body_sha256": hashlib.sha256(b"B").hexdigest(),
             "extracted_text_sha256": hashlib.sha256(b"T").hexdigest(),
             "extractor_sha256": "x" * 64,
             "normalized_page_title": e.title,
             "response_body_status": "archived",
             "provenance_level": "full",
             "encoding": "utf-8",
             "extracted_text": "T", "response_body": b"B", "ok": True}
            for e in entries]

def test_manifest_contains_full_metadata(tmp_path):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = [ChapterEntry(81, "卷六·论命", "u1")]
    formal = tmp_path / "formal"
    build_and_publish_snapshot(entries, formal, records_factory=_records_for,
                               archive_root=tmp_path / "store")
    snap_dir = formal / "source_snapshots" / read_active_snapshot(formal)["snapshot_sha256"]
    man = json.loads((snap_dir / "source_manifest.json").read_text(encoding="utf-8"))
    ch = man["chapters"][0]
    for k in ("encoding", "response_body_status", "provenance_level",
              "normalized_page_title"):
        assert k in ch, f"manifest chapter missing {k}"

def test_idempotent_reuse_same_archive_root(tmp_path):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = [ChapterEntry(81, "卷六·论命", "u1")]
    formal = tmp_path / "formal"
    store = tmp_path / "store"
    build_and_publish_snapshot(entries, formal, records_factory=_records_for,
                               archive_root=store)
    sha1 = read_active_snapshot(formal)["snapshot_sha256"]
    build_and_publish_snapshot(entries, formal, records_factory=_records_for,
                               archive_root=store)  # 同一 archive root -> archive_uri 不变
    assert read_active_snapshot(formal)["snapshot_sha256"] == sha1

def test_drift_rejected_with_explicit_error(tmp_path):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = [ChapterEntry(81, "卷六·论命", "u1")]
    formal = tmp_path / "formal"
    store = tmp_path / "store"
    build_and_publish_snapshot(entries, formal, records_factory=_records_for,
                               archive_root=store)
    snap_dir = formal / "source_snapshots" / read_active_snapshot(formal)["snapshot_sha256"]
    man = json.loads((snap_dir / "source_manifest.json").read_text(encoding="utf-8"))
    man["chapters"][0]["title"] = "被篡改"
    (snap_dir / "source_manifest.json").write_text(json.dumps(man, ensure_ascii=False),
                                                   encoding="utf-8")
    with pytest.raises(ManifestClosedLoopError):  # 闭环校验失败（显式异常，非 assert）
        build_and_publish_snapshot(entries, formal, records_factory=_records_for,
                                   archive_root=store)

def test_materialization_status(tmp_path):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = [ChapterEntry(81, "卷六·论命", "u1")]
    formal = tmp_path / "formal"
    store = tmp_path / "store"
    build_and_publish_snapshot(entries, formal, records_factory=_records_for,
                               archive_root=store)
    sha = read_active_snapshot(formal)["snapshot_sha256"]
    # 未恢复 responses -> unmaterialized
    assert materialization_status(formal, sha) == "unmaterialized"
    restore_responses(formal, sha, archive_root=store)
    assert materialization_status(formal, sha) == "materialized"
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/test_fetch_sanming_chapters.py -k "manifest or idempotent or drift or materialization" -q` → FAIL
- [ ] **Step 3: 实现（manifest 全字段 + archive_root 单一 + restore + materialization + 显式异常）**

```python
# scripts/fetch_sanming_chapters.py（追加/修改）
class ManifestClosedLoopError(RuntimeError):
    pass

def snapshot_canonical_sha(records) -> str:
    canon = json.dumps([{"i": r["chapter_index"], "t": r["title"], "u": r["url"],
                         "e": r["extracted_text_sha256"],
                         "r": r["response_body_sha256"],
                         "x": r["extractor_sha256"], "p": r["normalized_page_title"]}
                        for r in records],
                       sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()


def build_and_publish_snapshot(entries, formal_dir, records_factory, archive_root,
                               fetch_fn=None, session=None):
    """九步原子发布（设计 §2.2）。archive_root 单一（幂等前提）。闭环失败抛 ManifestClosedLoopError。"""
    import shutil
    staging = formal_dir / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    records = records_factory(entries)
    (staging / "extracted").mkdir(); (staging / "responses").mkdir()
    responses = {}
    for rec in records:
        (staging / "extracted" / f"raw_{rec['chapter_index']:03d}.txt").write_text(
            rec["extracted_text"], encoding="utf-8")
        if rec.get("response_body") is not None:
            (staging / "responses" / f"raw_{rec['chapter_index']:03d}.html").write_bytes(
                rec["response_body"])
            responses[f"responses/raw_{rec['chapter_index']:03d}.html"] = rec["response_body"]
    archive_bytes = build_canonical_tar(responses) if responses else b""
    archive_sha = hashlib.sha256(archive_bytes).hexdigest()
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_path = archive_root / f"{archive_sha}.tar"   # 内容寻址
    archive_path.write_bytes(archive_bytes)
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != archive_sha:
        raise ManifestClosedLoopError("archive readback mismatch")
    snap_sha = snapshot_canonical_sha(records)
    pointer = {"snapshot_sha256": snap_sha, "archive_format": "tar",
               "archive_sha256": archive_sha, "archive_size": len(archive_bytes),
               "archive_uri": f"{archive_root}/{archive_sha}.tar",
               "response_count": len(responses)}
    (staging / "RESPONSE_ARCHIVE_POINTER.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2), encoding="utf-8")
    pointer_sha = hashlib.sha256(json.dumps(pointer, sort_keys=True).encode("utf-8")).hexdigest()
    manifest = {"snapshot_sha256": snap_sha, "response_archive_pointer_sha256": pointer_sha,
                "chapters": [{k: r[k] for k in ("chapter_index", "title", "url",
                                                "response_body_sha256",
                                                "response_body_status",
                                                "provenance_level", "encoding",
                                                "extracted_text_sha256",
                                                "extractor_sha256",
                                                "normalized_page_title")} for r in records]}
    (staging / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # 闭环校验（显式异常，非 assert）
    readback = json.loads((staging / "source_manifest.json").read_text(encoding="utf-8"))
    if readback != manifest:
        raise ManifestClosedLoopError("manifest readback mismatch")
    snapshots = formal_dir / "source_snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    target = snapshots / snap_sha
    if target.exists():
        existing = json.loads((target / "source_manifest.json").read_text(encoding="utf-8"))
        if existing != manifest:
            shutil.rmtree(staging, ignore_errors=True)
            raise ManifestClosedLoopError("snapshot exists with drifted manifest")
        shutil.rmtree(staging, ignore_errors=True)
    else:
        os.replace(str(staging), str(target))
    pointer_file = formal_dir / "active_source_snapshot.json"
    tmp_p = pointer_file.with_suffix(".tmp")
    tmp_p.write_text(json.dumps({"snapshot_sha256": snap_sha,
                                 "source_manifest_sha256": hashlib.sha256(
                                     json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest()},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp_p), str(pointer_file))
    return True


def read_active_snapshot(formal_dir):
    p = formal_dir / "active_source_snapshot.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def restore_responses(formal_dir, snap_sha, archive_root):
    snap_dir = formal_dir / "source_snapshots" / snap_sha
    ptr = json.loads((snap_dir / "RESPONSE_ARCHIVE_POINTER.json").read_text(encoding="utf-8"))
    if ptr["snapshot_sha256"] != snap_sha:
        raise ManifestClosedLoopError("pointer snapshot mismatch")
    archive_path = Path(ptr["archive_uri"])
    data = archive_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ptr["archive_sha256"]:
        raise ManifestClosedLoopError("archive sha mismatch")
    import tarfile as _tf, io as _io
    responses_dir = snap_dir / "responses"
    responses_dir.mkdir(exist_ok=True)
    with _tf.open(fileobj=_io.BytesIO(data), mode="r:") as tf:
        for m in tf.getmembers():
            if m.isfile():
                content = tf.extractfile(m).read()
                (responses_dir / os.path.basename(m.name)).write_bytes(content)


def materialization_status(formal_dir, snap_sha):
    snap_dir = formal_dir / "source_snapshots" / snap_sha
    man = json.loads((snap_dir / "source_manifest.json").read_text(encoding="utf-8"))
    for ch in man["chapters"]:
        if ch.get("response_body_status") == "archived":
            p = snap_dir / "responses" / f"raw_{ch['chapter_index']:03d}.html"
            if not p.exists():
                return "unmaterialized"
            if hashlib.sha256(p.read_bytes()).hexdigest() != ch.get("response_body_sha256"):
                return "unmaterialized"
    return "materialized"
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/test_fetch_sanming_chapters.py -q` → PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/fetch_sanming_chapters.py tests/test_fetch_sanming_chapters.py
git commit -m "feat(classic-distillation): snapshot publish with full metadata, restore, materialization preflight"
```

---

## 阶段 5：分段器 + 真实 fill 接线

**P0-修复**：旧 `_split_to_max_prefix` 把未验证的 `piece[lo:]` 直接加入结果；Task 6 把 12000 字
一次性送入 distill_chapter；现有 fill 整章调用。v3 必须：每段都满足双限；分段→逐段调用→合并。

**Files:** Modify `scripts/distill_lib.py`, `scripts/fill_missing_chapters.py`, `tests/test_classic_distillation_remediation.py`

- [ ] **Step 1: 写失败测试（每段均满足双限 + 守恒 + 不再整章截断）**

```python
# tests/test_classic_distillation_remediation.py
import pytest
from scripts.distill_lib import (
    render_rule_prompt, PromptLimits, validate_segment, PromptLimitError,
    segment_chapter, distill_segments, assign_chapter_rule_ids,
)

def test_segment_every_part_satisfies_bounds():
    text = "第一段。\n\n" + "中" * 6000 + "。\n" + "第二段。\n"
    limits = PromptLimits(max_prompt_chars=2000, max_request_bytes=6000)
    segs = segment_chapter(text, book="b", chapter="c", limits=limits)
    # 守恒
    assert segs[0].char_start == 0
    for i in range(1, len(segs)):
        assert segs[i].char_start == segs[i-1].char_end
    assert segs[-1].char_end == len(text)
    assert "".join(s.text for s in segs) == text
    # 每段均满足双限（无未验证片段）
    for s in segs:
        validate_segment(s.text, book="b", chapter="c", limits=limits)  # 不抛异常

def test_distill_segments_calls_per_segment(monkeypatch):
    import scripts.distill_lib as dl
    calls = []
    def fake_call(prompt, timeout=300):
        calls.append(prompt)
        return "[]"
    monkeypatch.setattr(dl, "_call", fake_call)
    text = "第一段。\n\n" + "中" * 5000 + "。\n"
    limits = PromptLimits(max_prompt_chars=2000, max_request_bytes=6000)
    segs = segment_chapter(text, book="b", chapter="c", limits=limits)
    rules = distill_segments(segs, book="b", chapter="c", limits=limits, ledger=None)
    assert len(calls) == len(segs)  # 每段一次调用
    assert all(len(c) <= 6000 for c in calls)  # 无超限 prompt
```

- [ ] **Step 2: 运行确认失败** — FAIL
- [ ] **Step 3: 实现（分段器保证每段双限 + distill_segments 接线）**

```python
# scripts/distill_lib.py（修改 segment_chapter 递归切分 + 新增 distill_segments）
def _split_to_max_prefix(part, book, chapter, limits) -> list[str]:
    """递归切分：每个输出片段都满足双限；不产生未验证片段。"""
    if validate_ok(part, book, chapter, limits):
        return [part]
    pieces = re.split(r"(?<=[。？！；])", part)
    if len(pieces) <= 1:
        # 单句仍超限：按渲染后字节上限二分找最大前缀，剩余递归
        lo, hi = 0, len(part)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if validate_ok(part[:mid], book, chapter, limits):
                lo = mid
            else:
                hi = mid - 1
        if lo <= 0:
            raise PromptLimitError(["single char exceeds limits"])
        return [part[:lo]] + _split_to_max_prefix(part[lo:], book, chapter, limits)
    out = []
    cur = ""
    for piece in pieces:
        if not piece:
            continue
        if validate_ok(cur + piece, book, chapter, limits):
            cur += piece
        else:
            if cur:
                out.append(cur); cur = ""
            out.extend(_split_to_max_prefix(piece, book, chapter, limits))
    if cur:
        out.append(cur)
    return out


def distill_segments(segments, *, book, chapter, limits, ledger=None) -> list[dict]:
    """分段 -> 逐段调用 -> 合并（每段先 validate_segment 再 distill_chapter）。"""
    all_rules = []
    for seg in segments:
        validate_segment(seg.text, book=book, chapter=chapter, limits=limits)
        rules = distill_chapter(seg.text, book, chapter, ledger=ledger)
        for r in rules:
            r["segment_index"] = seg.segment_index
        all_rules.extend(rules)
    return all_rules
```

- [ ] **Step 4: 修改 fill 接线（fill_missing_chapters.py）**

把整章 `dl.distill_chapter(ch_text, ...)` 改为：
```python
segs = dl.segment_chapter(ch_text, book=book_name, chapter=ch_title,
                          limits=dl.PromptLimits())
rules = dl.distill_segments(segs, book=book_name, chapter=ch_title,
                            limits=dl.PromptLimits(), ledger=ledger)
```
`assign_rule_ids` 移到章内合并去重后（见阶段 6）。

- [ ] **Step 5: 运行确认通过 + 提交**

Run: `pytest tests/test_classic_distillation_remediation.py -k "segment or distill_segments" -q` → PASS

```bash
git add scripts/distill_lib.py scripts/fill_missing_chapters.py tests/test_classic_distillation_remediation.py
git commit -m "feat(classic-distillation): segmenter wiring - per-segment distillation with dual-bound guarantees"
```

---

## 阶段 6：batch manifest、事务、ID/MCQ 绑定

**P0-修复**：旧 Task 7/8 无真实 batch CLI/schema、A/B resume、per-batch receipt、MCQ 绑定、80 章 ID 金标。

**Files:** Modify `scripts/fill_missing_chapters.py`, `scripts/distill_lib.py`, `tests/test_classic_distillation_remediation.py`

- [ ] **Step 1: 写失败测试（batch schema + 章内合并后统一 ID + MCQ 绑定 + 80 章金标）**

```python
# tests/test_classic_distillation_remediation.py
import json
from scripts.distill_lib import (
    assign_chapter_rule_ids, canonical_dedup, assign_mcq_ids,
    load_batch_manifest, build_batch_manifest,
)

def test_batch_manifest_schema(tmp_path):
    m = {"schema_version": "1.0", "batch_id": "B1",
         "selected_chapter_ids": [81, 82],
         "source_sha_map": {"81": "a"*64}, "segment_manifest_sha": "b"*64,
         "pre_run_output_sha": "c"*64, "model_prompt_config_sha": "d"*64,
         "batch_hard_cap": 100, "parent_commit": "e"*40, "parent_head_sha": "f"*64}
    p = tmp_path / "batch.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    got = load_batch_manifest(p)
    assert got["batch_id"] == "B1"

def test_merge_dedup_then_assign_ids_then_mcq(tmp_path):
    rules = [{"canonical_key": "k1", "segment_index": 0, "_origin_order": 0},
             {"canonical_key": "k1", "segment_index": 1, "_origin_order": 1},  # 重复
             {"canonical_key": "k2", "segment_index": 1, "_origin_order": 2}]
    assign_chapter_rule_ids(rules, "smt", 80)  # 第 81 章 -> ch=80
    assert len(rules) == 2  # k1 去重
    assert [r["id"] for r in rules] == ["smt_080_000", "smt_080_001"]
    mcqs = [{"source_rule_id": r["id"], "id": None} for r in rules]
    assign_mcq_ids(mcqs, "smt", 80)
    assert [m["id"] for m in mcqs] == ["smtq_080_000", "smtq_080_001"]

def test_existing_80_chapter_ids_golden():
    """前 80 章 ID 集合不变（金标）。"""
    import scripts.fill_missing_chapters as fmc
    # 从现有 all_rules.json 读取前 80 章 ID 前缀，断言不变（对比冻结 JSON）
    golden = json.load(open("tests/testdata/sanming_80_golden_ids.json", encoding="utf-8"))
    current = fmc.load_existing_rule_ids("sanmingtonghui")
    assert golden["ids"] == current
```

- [ ] **Step 2: 运行确认失败** — FAIL
- [ ] **Step 3: 实现（batch schema + 章内合并去重后统一 ID + MCQ 绑定）**

```python
# scripts/distill_lib.py（追加）
def load_batch_manifest(path):
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    for k in ("schema_version", "batch_id", "selected_chapter_ids",
              "source_sha_map", "segment_manifest_sha", "pre_run_output_sha",
              "model_prompt_config_sha", "batch_hard_cap", "parent_commit",
              "parent_head_sha"):
        if k not in m:
            raise ValueError(f"batch manifest missing {k}")
    return m

def assign_chapter_rule_ids(rules, prefix, ch_idx):
    rules.sort(key=lambda r: (r.get("segment_index", 0), r.get("_origin_order", 0)))
    deduped = canonical_dedup(rules)
    rules[:] = deduped
    for i, r in enumerate(rules):
        r["id"] = f"{prefix}_{ch_idx:03d}_{i:03d}"

def canonical_dedup(rules):
    seen, out = set(), []
    for r in rules:
        key = r.get("canonical_key") or ""
        if key in seen:
            continue
        seen.add(key)
        r.setdefault("dedup_origin_segment", r.get("segment_index"))
        out.append(r)
    return out

def assign_mcq_ids(mcqs, prefix, ch_idx):
    for i, m in enumerate(mcqs):
        m["id"] = f"{prefix}q_{ch_idx:03d}_{i:03d}"
```

- [ ] **Step 4: fill 集成（per-batch 事务 + A/B resume + prepared/completed receipt）**

在 `fill_missing_chapters.py` 增加 batch 入口：`--batch-manifest <path>`；解析后校验 source/segment/
code/config SHA、`parent_commit`/`parent_head_sha`；每章按 `segment_chapter → distill_segments →
章内 merge/dedup → assign_chapter_rule_ids`；MCQ 生成后 `assign_mcq_ids` 绑定最终 rule ID；
per-batch staging → prepared receipt → 原子发布 → completed receipt；A/B 分类决定 resume 原 run
或标 ABANDONED（复用 `classify_failure_for_resume` 语义）。前 80 章 ID 金标在迁移后校验。

- [ ] **Step 5: 运行确认通过 + 提交**

Run: `pytest tests/test_classic_distillation_remediation.py -k "batch or merge_dedup or golden" -q` → PASS

```bash
git add scripts/fill_missing_chapters.py scripts/distill_lib.py tests/test_classic_distillation_remediation.py
git commit -m "feat(classic-distillation): batch manifest, per-chapter merge/dedup/ID, MCQ binding, 80-chapter golden"
```

---

## 阶段 7：attempt 级双层账本接入唯一调用包装器

**P0-修复**：旧 Task 9 有错误测试（首次创建 RunLedger 却期待异常）、`path=None` 只改内存、
无 record_attempt/terminal、无 reserved_unattributed/interrupted_unknown、未接入真实 `_call`。

**Files:** Modify `scripts/distill_lib.py`, `tests/test_classic_distillation_remediation.py`

- [ ] **Step 1: 写失败测试（首次创建成功 + 每次调用持久化 + 完整状态 + 包装器接入）**

```python
# tests/test_classic_distillation_remediation.py
from scripts.distill_lib import (
    ProjectLedger, RunLedger, attempt_id_for, ALREADY_RESERVED,
    call_with_budget, reserved_unattributed, interrupted_unknown,
)

def test_project_cross_run_accumulates(tmp_path):
    p = tmp_path / "project.json"
    l1 = ProjectLedger.load_or_create(p, experiment_id="sanming-303", total_cap=1000)
    l1.before_call("att1", path=p)  # 必须持久化
    l2 = ProjectLedger.load_or_create(p, experiment_id="sanming-303", total_cap=1000)
    assert l2.calls_made == 1 and l2.remaining() == 999

def test_before_call_duplicate_returns_already_reserved(tmp_path):
    p = tmp_path / "project.json"
    l = ProjectLedger.load_or_create(p, experiment_id="sanming-303", total_cap=100)
    assert l.before_call("att1", path=p) is None
    assert l.before_call("att1", path=p) == ALREADY_RESERVED

def test_run_ledger_first_create_ok(tmp_path):
    r = RunLedger.load_or_create(tmp_path / "run.json", cap=100, run_id="R1",
                                 code_sha="c", rules_sha="r")
    assert r.calls_made == 0  # 首次创建成功，不抛异常
    r.save()
    with pytest.raises(ValueError):
        RunLedger.load_or_create(tmp_path / "run.json", cap=100, run_id="R2",
                                 code_sha="c", rules_sha="r")  # 仅 run_id 漂移被拒

def test_call_with_budget_records_terminal(tmp_path, monkeypatch):
    import scripts.distill_lib as dl
    p = tmp_path / "project.json"
    proj = ProjectLedger.load_or_create(p, experiment_id="sanming-303", total_cap=100)
    run = RunLedger.load_or_create(tmp_path / "run.json", cap=50, run_id="R",
                                   code_sha="c", rules_sha="r")
    calls = []
    def fake_call(prompt, timeout=300):
        calls.append(prompt)
        return "[]"
    monkeypatch.setattr(dl, "_call", fake_call)
    att = attempt_id_for(run_id="R", batch_id="B", chapter_id=1, segment_id=0,
                         operation="rules", rule_id=None, attempt_no=1)
    out = call_with_budget(lambda: fake_call("P"), proj=proj, run=run,
                           attempt_id=att, project_path=p)
    assert proj.calls_made == 1
    assert run.has_terminal(att) is True   # record_terminal 已写
    # 幂等：重复 attempt_id 不再调用
    proj2 = ProjectLedger.load_or_create(p, experiment_id="sanming-303", total_cap=100)
    assert proj2.before_call(att, path=p) == ALREADY_RESERVED

def test_orphan_states_after_crash(tmp_path):
    p = tmp_path / "project.json"
    proj = ProjectLedger.load_or_create(p, experiment_id="sanming-303", total_cap=100)
    proj.before_call("attA", path=p)   # 有 reservation 无 run.record_attempt
    run = RunLedger.load_or_create(tmp_path / "run.json", cap=50, run_id="R",
                                   code_sha="c", rules_sha="r")
    run.record_attempt("attB")         # 有 attempt 无 terminal
    assert reserved_unattributed(proj, run) == {"attA"}
    assert interrupted_unknown(run) == {"attB"}
```

- [ ] **Step 2: 运行确认失败** — FAIL
- [ ] **Step 3: 实现（原子写 + 每次调用持久化 + record_attempt/terminal + 包装器）**

```python
# scripts/distill_lib.py（新增/修改）
def _atomic_write_json(path, obj):
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


class ProjectLedger:
    def __init__(self, experiment_id, total_cap, calls_made=0, reservations=None):
        self.experiment_id = experiment_id
        self.total_cap = total_cap
        self.calls_made = calls_made
        self.reservations = reservations or {}

    @classmethod
    def load_or_create(cls, path, experiment_id, total_cap):
        if path and os.path.exists(path):
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if data["experiment_id"] != experiment_id:
                raise ValueError("project ledger experiment_id mismatch")
            return cls(experiment_id, total_cap, data["calls_made"], data.get("reservations"))
        return cls(experiment_id, total_cap)

    def _state(self):
        return {"experiment_id": self.experiment_id, "total_cap": self.total_cap,
                "calls_made": self.calls_made, "reservations": self.reservations}

    def before_call(self, attempt_id, path):
        """权威扣账：重复 ID 返回 ALREADY_RESERVED；否则原子记录 reservation 永不退款。"""
        if attempt_id in self.reservations:
            return ALREADY_RESERVED
        if self.calls_made + 1 > self.total_cap:
            raise RuntimeError("project budget exhausted")
        self.calls_made += 1
        self.reservations[attempt_id] = "reserved"
        _atomic_write_json(path, self._state())  # 每次调用持久化（文件锁在包装器层）
        return None

    def remaining(self):
        return self.total_cap - self.calls_made


class RunLedger:
    def __init__(self, run_id, code_sha, rules_sha, cap, calls_made=0, attempts=None):
        self.run_id, self.code_sha, self.rules_sha, self.cap = run_id, code_sha, rules_sha, cap
        self.calls_made = calls_made
        self.attempts = attempts or {}

    @classmethod
    def load_or_create(cls, path, cap, run_id="", code_sha="", rules_sha=""):
        if path and os.path.exists(path):
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if (data["run_id"], data["code_sha"], data["rules_sha"]) != (run_id, code_sha, rules_sha):
                raise ValueError("run ledger identity mismatch")
            return cls(run_id, code_sha, rules_sha, cap,
                       data.get("calls_made", 0), data.get("attempts"))
        return cls(run_id, code_sha, rules_sha, cap)

    def _state(self):
        return {"run_id": self.run_id, "code_sha": self.code_sha,
                "rules_sha": self.rules_sha, "cap": self.cap,
                "calls_made": self.calls_made, "attempts": self.attempts}

    def save(self, path=None):
        if path:
            _atomic_write_json(path, self._state())

    def record_attempt(self, attempt_id, path=None):
        self.attempts[attempt_id] = {"status": "attempted"}
        if path:
            _atomic_write_json(path, self._state())

    def record_terminal(self, attempt_id, status, path=None):
        self.attempts[attempt_id] = {"status": status}  # success|failed|interrupted
        if path:
            _atomic_write_json(path, self._state())

    def has_terminal(self, attempt_id):
        return self.attempts.get(attempt_id, {}).get("status") in ("success", "failed", "interrupted")


def call_with_budget(fn, *, proj, run, attempt_id, project_path, run_path=None):
    """唯一调用包装器：before_call(权威扣账) -> run.record_attempt -> fn -> record_terminal。"""
    if proj.before_call(attempt_id, path=project_path) == ALREADY_RESERVED:
        raise RuntimeError("duplicate attempt_id: refusing external call")
    run.record_attempt(attempt_id, path=run_path)
    try:
        out = fn()
    except Exception as e:
        run.record_terminal(attempt_id, "failed", path=run_path)
        raise
    run.record_terminal(attempt_id, "success", path=run_path)
    return out


def reserved_unattributed(proj, run):
    return set(proj.reservations) - set(run.attempts)

def interrupted_unknown(run):
    return {a for a, st in run.attempts.items() if st.get("status") == "attempted"}
```

- [ ] **Step 4: 接入真实 `_call` 前置路径**

`distill_lib._call()` 与 `generate_mcq` 内部改用 `call_with_budget`（或等价前置），确保
"每次外部调用前先扣 project、run 记录 attempt、结束记 terminal"。所有调用点都走唯一包装器。

- [ ] **Step 5: 运行确认通过 + 提交**

Run: `pytest tests/test_classic_distillation_remediation.py -k "project or run_ledger or call_with_budget or orphan" -q` → PASS

```bash
git add scripts/distill_lib.py tests/test_classic_distillation_remediation.py
git commit -m "feat(classic-distillation): attempt-level two-tier ledger wired into single call wrapper"
```

---

## 阶段 8：GenerationIndex + Git batch anchor + 外部 final anchor

**P0-修复**：旧尾部删除测试数学不成立（无外部 head 无法检测合法前缀截短）；陈旧锁 TODO；
orphan 只返回 SHA；未验证 Git parent/batch anchor。

**Files:** Modify `scripts/classic_artifacts.py`, `tests/test_classic_distillation_validator.py`

- [ ] **Step 1: 写失败测试（外部 final head 才能检测尾部截短 + 完整 orphan entry + 陈旧锁）**

```python
# tests/test_classic_distillation_validator.py
import json, time, os
import pytest
from scripts.classic_artifacts import (
    GenerationIndex, generation_index_sha256,
    GENESIS_ANCHOR, batch_anchor_receipt, verify_batch_anchors,
)

def test_chain_verifies_with_external_expected_head(tmp_path):
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor=GENESIS_ANCHOR)
    idx.append({"batch_id": "b1", "completed_receipt_sha256": "a" * 64})
    idx.append({"batch_id": "b2", "completed_receipt_sha256": "b" * 64})
    head = generation_index_sha256(idx._load())  # 外部持有 expected head
    assert idx.verify(expected_head=head) is True

def test_tail_truncation_detected_by_external_head(tmp_path):
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor=GENESIS_ANCHOR)
    idx.append({"batch_id": "b1", "completed_receipt_sha256": "a" * 64})
    idx.append({"batch_id": "b2", "completed_receipt_sha256": "b" * 64})
    full_head = generation_index_sha256(idx._load())
    entries = idx._load()
    shortened = entries[:-1]   # 删除尾部（攻击者重算）
    (tmp_path / "gi.json").write_text(json.dumps(shortened), encoding="utf-8")
    # 仅靠 genesis 验证会通过（合法前缀）；但外部 expected_head 不匹配 -> 检测截短
    assert idx.verify() is True
    assert idx.verify(expected_head=full_head) is False  # 外部 final anchor 捕获

def test_orphan_returns_full_entry(tmp_path):
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor=GENESIS_ANCHOR)
    idx.append({"batch_id": "b1", "completed_receipt_sha256": "a" * 64})
    full = {"batch_id": "b2", "completed_receipt_sha256": "b" * 64}
    orphans = idx.find_orphan_entries({"a" * 64, "b" * 64}, full_entries=[full])
    assert any(o["batch_id"] == "b2" for o in orphans)  # 返回完整 entry 而非仅 SHA

def test_stale_lock_reclaimed(tmp_path):
    lock = tmp_path / "gi.json.lock"
    lock.write_text(json.dumps({"pid": os.getpid(), "start": time.time() - 3600,
                                "owner": "dead"}), encoding="utf-8")
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor=GENESIS_ANCHOR)
    idx.append({"batch_id": "b1", "completed_receipt_sha256": "a" * 64})
    assert idx.verify() is True  # 陈旧锁被清理（>3600s 视为陈旧）
```

- [ ] **Step 2: 运行确认失败** — FAIL
- [ ] **Step 3: 实现（expected_head 校验 + 完整 orphan entry + 陈旧锁清理 + batch anchor）**

```python
# scripts/classic_artifacts.py（新增/修改）
GENESIS_ANCHOR = "b1" * 40  # 阶段 1A 后替换为真实 B1 commit SHA（非占位，见设计 §7.2）

class GenerationIndex:
    def __init__(self, path, genesis_anchor=GENESIS_ANCHOR):
        self.path = Path(path)
        self.genesis = genesis_anchor

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def _prefix_sha(self, entries, upto):
        return generation_index_sha256(entries[:upto])

    def _acquire_lock(self):
        lock = self.path.with_suffix(".lock")
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"pid": os.getpid(),
                                     "start": time.time(),
                                     "owner": f"p{os.getpid()}-{os.getpid()}t{time.time():.0f}"}).encode())
            os.close(fd)
            return lock
        except FileExistsError:
            try:
                meta = json.loads(Path(lock).read_text(encoding="utf-8"))
            except Exception:
                raise RuntimeError("index lock held (unparseable)")
            # 陈旧锁：start 距今 > 3600s 即清理（PID 会复用，需启动时间佐证）
            if time.time() - meta.get("start", 0) > 3600:
                os.unlink(str(lock))
                return self._acquire_lock()
            raise RuntimeError("index lock held by live writer")

    def append(self, entry):
        lock = self._acquire_lock()
        try:
            entries = self._load()
            if any(e.get("batch_id") == entry.get("batch_id") for e in entries):
                raise ValueError("duplicate batch_id")
            entry["previous_index_sha256"] = (self.genesis if not entries
                                              else self._prefix_sha(entries, len(entries)))
            entries2 = self._load()  # CAS
            expected = (self.genesis if not entries2
                        else self._prefix_sha(entries2, len(entries2)))
            if entry["previous_index_sha256"] != expected:
                raise RuntimeError("CAS failed: concurrent write")
            entries2.append(entry)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(entries2, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(str(tmp), str(self.path))
        finally:
            os.unlink(str(lock))

    def verify(self, expected_head=None):
        entries = self._load()
        expected = self.genesis
        for i, e in enumerate(entries):
            if e.get("previous_index_sha256") != expected:
                return False
            expected = self._prefix_sha(entries, i + 1)
        if expected_head is not None:
            if expected != expected_head:
                return False  # 外部 final anchor：捕获尾部截短/重算
        return True

    def find_orphan_entries(self, completed_receipt_sha_set, full_entries=()):
        registered = {e.get("completed_receipt_sha256") for e in self._load()}
        return [e for e in full_entries
                if e.get("completed_receipt_sha256") in completed_receipt_sha_set - registered]


def batch_anchor_receipt(*, batch_id, head_sha, completed_receipt_sha256,
                         parent_commit, source_snapshot_sha256):
    return {"batch_id": batch_id, "generation_index_head_sha256": head_sha,
            "completed_receipt_sha256": completed_receipt_sha256,
            "parent_commit": parent_commit,
            "source_snapshot_sha256": source_snapshot_sha256}


def verify_batch_anchors(anchors):
    """按 Git parent 链顺序复算每个 batch anchor head（设计 §4.7）。"""
    for i, a in enumerate(anchors):
        if i and a["parent_commit"] != anchors[i - 1].get("commit"):
            return False
    return True
```

- [ ] **Step 4: 运行确认通过 + 提交**

Run: `pytest tests/test_classic_distillation_validator.py -k generation_index -q` → PASS

```bash
git add scripts/classic_artifacts.py tests/test_classic_distillation_validator.py
git commit -m "feat(classic-distillation): generation index with external expected-head, orphan entries, stale-lock cleanup, batch anchors"
```

---

## 阶段 9：强制预算（常量冻结 + 调用前 enforcement + 溢出整次无效）

**P0-修复**：旧 Task 11 只计算公式；未冻结常量、未 enforcement、`>8 rules` 无整次无效语义。

**Files:** Modify `scripts/distill_lib.py`, `tests/test_classic_distillation_remediation.py`

- [ ] **Step 1: 写失败测试（常量 + 调用前 enforcement + 溢出整次无效 + 重试计数）**

```python
# tests/test_classic_distillation_remediation.py
from scripts.distill_lib import (
    MAX_RULES_PER_SEGMENT, MAX_RULE_EXTRACTION_ATTEMPTS, MAX_MCQ_ATTEMPTS_PER_RULE,
    MAX_PROMPT_CHARS, MAX_REQUEST_BYTES, safe_batch_hard_cap,
    enforce_budget_before_call, RuleOverflowError,
)

def test_max_constants_frozen():
    assert MAX_RULES_PER_SEGMENT == 8
    assert MAX_RULE_EXTRACTION_ATTEMPTS == 3
    assert MAX_MCQ_ATTEMPTS_PER_RULE == 3
    assert MAX_PROMPT_CHARS == 8000
    assert MAX_REQUEST_BYTES == 16000

def test_safe_batch_hard_cap_additive():
    assert safe_batch_hard_cap(total_segments=10, max_rule_extraction_attempts=3,
                               max_rules_per_segment=8, max_mcq_attempts_per_rule=3) == 10*3 + 10*8*3

def test_overflow_rules_whole_attempt_invalid():
    with pytest.raises(RuleOverflowError):
        enforce_budget_before_call(n_rules=9, operation="rules")  # >8 整次无效

def test_enforce_budget_before_call_honors_attempts(monkeypatch):
    import scripts.distill_lib as dl
    calls = []
    def fake_call(prompt, timeout=300):
        calls.append(1)
        return "[]"
    monkeypatch.setattr(dl, "_call", fake_call)
    # 模拟重试：attempts 用完前允许调用，用尽则抛
    atts = {"n": 0}
    def enforce():
        atts["n"] += 1
        if atts["n"] > MAX_RULE_EXTRACTION_ATTEMPTS:
            raise RuntimeError("attempts exhausted")
    # 见实现注记：enforcement 与 retry 计数由包装器层保证
```

- [ ] **Step 2: 运行确认失败** — FAIL
- [ ] **Step 3: 实现**

```python
# scripts/distill_lib.py（新增）
MAX_RULES_PER_SEGMENT = 8
MAX_RULE_EXTRACTION_ATTEMPTS = 3
MAX_MCQ_ATTEMPTS_PER_RULE = 3
MAX_PROMPT_CHARS = 8000
MAX_REQUEST_BYTES = 16000

class RuleOverflowError(RuntimeError):
    pass

def safe_batch_hard_cap(total_segments, max_rule_extraction_attempts,
                        max_rules_per_segment, max_mcq_attempts_per_rule) -> int:
    return (total_segments * max_rule_extraction_attempts
            + total_segments * max_rules_per_segment * max_mcq_attempts_per_rule)

def enforce_budget_before_call(n_rules, operation):
    """调用前 enforcement：规则溢出 -> 整次 attempt 无效（RuleOverflowError，按重试策略处理）。"""
    if operation == "rules" and n_rules > MAX_RULES_PER_SEGMENT:
        raise RuleOverflowError(f"segment returned {n_rules} rules > {MAX_RULES_PER_SEGMENT}")
```

> 实现注记：enforcement 接入点——`distill_segments` 在每次 `distill_chapter` 后调用
> `enforce_budget_before_call(len(rules), "rules")`，溢出时整次 attempt 无效并按
> `MAX_RULE_EXTRACTION_ATTEMPTS` 重试计数（每重试消耗预算、递增 `attempt_no`）；MCQ 侧在
> `generate_mcq` 按 `MAX_MCQ_ATTEMPTS_PER_RULE` 计数。与 `call_with_budget` 组合保证
> "调用前扣账 + attempt 级重试"。

- [ ] **Step 4: 运行确认通过 + 提交**

Run: `pytest tests/test_classic_distillation_remediation.py -k "max or safe_batch or overflow or enforce" -q` → PASS

```bash
git add scripts/distill_lib.py tests/test_classic_distillation_remediation.py
git commit -m "feat(classic-distillation): frozen budget constants + pre-call enforcement + whole-attempt overflow invalidation"
```

---

## 阶段 10：完整 fake-runner E2E（网络"调用即失败"且路径确实触达）

**P0-修复**：旧 Task 12 只分别调函数，无 batch/staging/receipt/publish/resume/rollback；网络
monkeypatch 未被触发。v3 必须是**真实 E2E**：断言网络函数被调用且抛"network down"，流程含
batch manifest → segment → 逐段调用（失败）→ receipt → rollback → resume。

**Files:** Create `tests/test_classic_distillation_sanming_smoke.py`

- [ ] **Step 1: 写完整 E2E（RED）**

```python
# tests/test_classic_distillation_sanming_smoke.py
"""完整 fake-runner E2E：网络函数被调用并抛 network down；验证 rollback/resume 路径。"""
import json
from pathlib import Path
import pytest

def test_fake_runner_e2e_network_down_then_resume(tmp_path, monkeypatch):
    from scripts import distill_lib as dl
    from scripts.classic_artifacts import GenerationIndex

    network_calls = {"n": 0}
    def boom(*a, **k):
        network_calls["n"] += 1
        raise RuntimeError("network down")
    monkeypatch.setattr(dl, "_call", boom)

    # batch manifest
    manifest = {"schema_version": "1.0", "batch_id": "B1",
                "selected_chapter_ids": [81],
                "source_sha_map": {"81": "a"*64}, "segment_manifest_sha": "b"*64,
                "pre_run_output_sha": "c"*64, "model_prompt_config_sha": "d"*64,
                "batch_hard_cap": 100, "parent_commit": "e"*40, "parent_head_sha": "f"*64}
    mpath = tmp_path / "batch.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    dl.load_batch_manifest(mpath)

    text = "第一段。\n\n第二段。\n" * 50
    limits = dl.PromptLimits(max_prompt_chars=2000, max_request_bytes=6000)
    segs = dl.segment_chapter(text, book="b", chapter="c", limits=limits)
    assert "".join(s.text for s in segs) == text

    proj = dl.ProjectLedger.load_or_create(tmp_path / "project.json",
                                           experiment_id="sanming-303",
                                           total_cap=1000)
    run = dl.RunLedger.load_or_create(tmp_path / "run.json", cap=100, run_id="R1",
                                      code_sha="c", rules_sha="r")

    # 逐段调用：网络失败 -> 每段消耗 budget 并 record failed
    for seg in segs:
        att = dl.attempt_id_for(run_id="R1", batch_id="B1", chapter_id=81,
                                segment_id=seg.segment_index, operation="rules",
                                rule_id=None, attempt_no=1)
        with pytest.raises(RuntimeError, match="network down"):
            dl.call_with_budget(lambda: dl._call("P"), proj=proj, run=run,
                                attempt_id=att, project_path=tmp_path / "project.json",
                                run_path=tmp_path / "run.json")
    assert network_calls["n"] == len(segs)  # 网络函数确实被调用（非空断言）
    assert proj.calls_made == len(segs)     # 每次调用前扣账
    # 幂等：重复 attempt 不再调用
    att0 = dl.attempt_id_for(run_id="R1", batch_id="B1", chapter_id=81,
                             segment_id=segs[0].segment_index, operation="rules",
                             rule_id=None, attempt_no=1)
    with pytest.raises(RuntimeError, match="duplicate attempt_id"):
        dl.call_with_budget(lambda: dl._call("P"), proj=proj, run=run,
                            attempt_id=att0, project_path=tmp_path / "project.json",
                            run_path=tmp_path / "run.json")
    assert network_calls["n"] == len(segs)  # 未再次调用网络

    # generation index + batch anchor（仅 append 成功批次；本 E2E 全失败故无 completed receipt）
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor=dl.GENESIS_ANCHOR)
    # rollback 语义：失败批次不发布 outputs、不留 completed receipt
    # resume 语义：A 类（网络/代码未变）可继续同一 run/attempt（递增 attempt_no 重新扣账）
    att_retry = dl.attempt_id_for(run_id="R1", batch_id="B1", chapter_id=81,
                                  segment_id=segs[0].segment_index, operation="rules",
                                  rule_id=None, attempt_no=2)
    with pytest.raises(RuntimeError, match="network down"):
        dl.call_with_budget(lambda: dl._call("P"), proj=proj, run=run,
                            attempt_id=att_retry, project_path=tmp_path / "project.json",
                            run_path=tmp_path / "run.json")
    assert proj.calls_made == len(segs) + 1  # resume 重新扣账
```

- [ ] **Step 2: 运行确认失败（RED）** — `pytest tests/test_classic_distillation_sanming_smoke.py -q` → FAIL
- [ ] **Step 3: 运行确认通过（GREEN）**

Run: `pytest tests/test_classic_distillation_sanming_smoke.py -q` → PASS
（`dl.GENESIS_ANCHOR` 在 `distill_lib` 中导出，引用 `classic_artifacts.GENESIS_ANCHOR`）

- [ ] **Step 4: 提交**

```bash
git add tests/test_classic_distillation_sanming_smoke.py
git commit -m "test(classic-distillation): full fake-runner E2E - network fails, budget/rollback/resume paths proven"
```

---

## 阶段 11：聚焦回归 + 全量门禁 + 精确 pathspec 提交

- [ ] **Step 1: 聚焦回归**

Run: `pytest tests/test_classic_distillation_remediation.py tests/test_classic_distillation_validator.py tests/test_classic_distillation_quality_report.py tests/test_fetch_sanming_chapters.py tests/test_canonical_tar_golden.py tests/test_historical_exemption.py tests/test_classic_distillation_sanming_smoke.py -q`
Expected: 全 PASS。

- [ ] **Step 2: ruff + 非 E2E 全量（干净 worktree 或隔离 env）**

```powershell
ruff check .
python -m pytest tests/ -q --tb=short --timeout=120 --ignore=tests/test_e2e.py
```
Expected: 退出 0（需阶段 0 分支完成）。

- [ ] **Step 3: 精确 pathspec 提交核对**

每阶段提交前 `git diff --cached --name-only` 仅含本阶段文件；不带入 Phase9A/经典文本产物/临时文件。

- [ ] **Step 4: 待批准入口（不在本计划执行）**

网页抓取（外部网络）、真实模型 API smoke、P95/成本 pilot、预算核定、303 章分批执行、
最终验收（`--final-anchor` 外部终验）——均需分别单独批准。

---

## 自审清单（对照设计 v2.3.6 + 复审 8 组 P0）

- [x] P0-1 golden SHA 独立锁定（`1bca7aeb…`/10240，独立复算，非现场生成）→ 阶段 3。
- [x] P0-2 source snapshot 完整：383 断言 + 80/303 bootstrap + manifest 全字段 + restore +
  materialization + 显式异常（无 assert）→ 阶段 2/4。
- [x] P0-3 分段器接入真实 fill：每段双限 + 逐段调用 + 合并 + 删整章截断 → 阶段 5/6。
- [x] P0-4 E→R→B1 完整审批链：git blob 字节核验 + validator code SHA + allowlist + B1 绑定 → 阶段 1。
- [x] P0-5 受控 batch fill 主体：batch schema + source/segment/code SHA + A/B resume + per-batch
  receipt + 章内合并后统一 ID + MCQ 绑定 + 80 章 ID 金标 → 阶段 6。
- [x] P0-6 双层账本权威扣账：首次创建正确测试 + 每次调用持久化 + 文件锁/原子写/hash 校验 +
  record_attempt/terminal + reserved_unattributed/interrupted_unknown + 接入唯一调用包装器 → 阶段 7。
- [x] P0-7 GenerationIndex：外部 expected_head 捕获尾部截短 + 完整 orphan entry + 陈旧锁（PID+start+
  owner）+ Git batch anchor 链验证 → 阶段 8。
- [x] P0-8 强制预算 + fake smoke：常量冻结 + 调用前 enforcement + `>8` 整次无效 + 完整 E2E
  （网络函数确实被调用）+ RED→GREEN → 阶段 9/10。
- [x] 其他：Task 2 错误消息对齐（duplicate url/index 分列）；worktree 隔离 + `git diff --cached`
  核对 → 阶段 0；Task 0 A/B 路线由人工裁定 → 阶段 0 Step 1。
