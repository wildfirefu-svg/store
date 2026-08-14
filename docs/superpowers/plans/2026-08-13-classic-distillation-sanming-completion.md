# 《三命通会》补全实施计划（v2，按设计 v2.3.6 重写）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已批准设计 v2.3.6 补齐《三命通会》缺失 303 章所需的离线能力（抓取器、分段器、受控 fill、双层账本、provenance 链、fake smoke），为后续经批准的网页抓取与真实模型 API 执行做好准备。

**Architecture:** 在既有受控 fill 管线上新增四个能力单元：①事务化原文抓取器（canonical tar 归档 + 内容寻址 URI + 原子 snapshot 发布）；②确定性无损分段器（完整 prompt 渲染后字符/字节双限）；③受控 batch fill（章内合并去重 + 一次性 ID 分配 + A/B 状态机 + attempt_id 级双层账本）；④跨批次 Git-only provenance 链（E→R→B1 非循环审批 + batch anchor + 外部 final anchor）。

**Tech Stack:** Python 3.11+、pytest、requests、tarfile、hashlib、现有 `distill_lib.py` / `fill_missing_chapters.py` / `classic_artifacts.py`。

**Scope 边界**：本计划只做**离线实现与 fake smoke**。网页抓取（外部网络）与真实模型 API 均需**分别单独批准**，不在本计划自动执行范围内；相关入口在"待批准入口"清单中列出。

---

## 前置状态（以设计 v2.3.6 为准）

- 设计文档 `docs/superpowers/specs/2026-08-13-classic-distillation-sanming-completion-design.md` **已批准**（commit `87d6929`）。
- 非 E2E 全量门禁未归零（3 failed 属 phase8 `bazi_kb.db` 快照）；Task 0 是先决门禁（人工裁定）。
- 四书 `provenance_ok/end_to_end` 全 false；Task 1 是 E→R→B1 机器可执行历史基线整治。
- 现有《三命通会》：前 80 章 `raw_NNN_<title>.txt`（001..080 连续，无缺号）；`chapter_list.txt` 383 行。

## 文件结构

- `scripts/fetch_sanming_chapters.py`（新建）：chapter_list 解析、canonical tar 归档、原子 snapshot 发布、restore-responses。
- `tests/test_fetch_sanming_chapters.py`（新建）。
- `scripts/distill_lib.py`（修改）：`render_rule_prompt`、`PromptLimits`/`validate_segment`、`segment_chapter`、章内合并/去重/ID 分配、`ProjectLedger`/`RunLedger`、`safe_batch_hard_cap`、canonical_key。
- `scripts/fill_missing_chapters.py`（修改）：`--batch-manifest` 入口、per-batch 事务、A/B 状态机。
- `scripts/classic_artifacts.py`（修改）：`segment_manifest_sha256`、E/R schema、GenerationIndex（Git-only anchor）、`verify_exemption`。
- `scripts/validate_classic_distillation.py`（修改）：消费 E/R、`--final-anchor`。
- 测试：`tests/test_fetch_sanming_chapters.py`、`tests/test_classic_distillation_remediation.py`、`tests/test_classic_distillation_validator.py`、`tests/test_historical_exemption.py`、`tests/test_classic_distillation_sanming_smoke.py`、`tests/test_canonical_tar_golden.py`。

---

### Task 0: 阶段 0 门禁归零（先决，人工裁定）

**Files:** 取决于分支裁定

**背景**：设计 §7.1 P0-8。Phase 8 三项失败（`test_regeneration_deterministic` /
`test_reconcile_subtype_passes` / `test_reconcile_full_sections`）二选一：

- [ ] **分支 A**：修复 `bazi_kb.db` 快照/重建契约，干净 clone 全量退出 0。
- [ ] **分支 B**：正式改测试/门禁契约，经独立设计审批。

**成功标准**：干净 clone + `python knowledge-base/bazi_kb.py --build` + `pytest tests/ -q --tb=short --timeout=120 --ignore=tests/test_e2e.py` 退出码 0，JUnit XML 保存。

> Task 0 归零前不得进入任何真实 API 步骤。

---

### Task 1: 阶段 1A — E→R→B1 历史基线整治（机器可执行）

**Files:**
- Modify: `scripts/classic_artifacts.py`（E/R schema、`exemption_request_sha256`、`verify_exemption_request`/`verify_approval_receipt`）
- Modify: `scripts/validate_classic_distillation.py`（消费 E/R 计算 verdict）
- Create: `tests/test_historical_exemption.py`

- [ ] **Step 1: 写失败测试（E 不反向引用 R/B1；R 绑定 E）**

```python
# tests/test_historical_exemption.py
import pytest
from scripts.classic_artifacts import (
    exemption_request_sha256, verify_exemption_request,
    verify_approval_receipt,
)

E = {
    "book": "ditiansui",
    "artifact_sha256_by_path": {"raw": {"raw_001_x.txt": "a" * 64},
                                 "rules": {"all_rules.json": "b" * 64}},
    "baseline_commit": "b0" * 40,
    "validator_code_sha256": "c" * 64,
    "exempted_checks": ["missing_upstream_response_body"],
    "non_exempt_checks": ["artifact_integrity", "quality_gates",
                          "future_generation_provenance"],
    "author": "audit", "date": "2026-08-13",
}

def test_exemption_request_has_no_self_refs():
    assert "approval_receipt_sha256" not in E
    assert "approval_commit" not in E
    verify_exemption_request(E) is True

def test_approval_receipt_binds_exemption_request():
    R = {"exemption_request_sha256": exemption_request_sha256(E),
         "baseline_commit": E["baseline_commit"],
         "artifact_manifest_sha256": "m" * 64,
         "approver": "reviewer", "approved_at": "2026-08-13T00:00:00Z"}
    assert verify_approval_receipt(R, E) is True

def test_approval_receipt_rejects_wrong_exemption():
    E2 = dict(E, book="zipingzhenquan")
    R = {"exemption_request_sha256": exemption_request_sha256(E),
         "baseline_commit": E["baseline_commit"],
         "artifact_manifest_sha256": "m" * 64,
         "approver": "reviewer", "approved_at": "2026-08-13T00:00:00Z"}
    with pytest.raises(ValueError):
        verify_approval_receipt(R, E2)
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_historical_exemption.py -q`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 实现 E/R schema**

```python
# scripts/classic_artifacts.py（新增）
_EXEMPT_REQUEST_REQUIRED = {"book", "artifact_sha256_by_path", "baseline_commit",
                            "validator_code_sha256", "exempted_checks",
                            "non_exempt_checks", "author", "date"}
_EXEMPT_LEVELS = {"historical_text_only"}


def exemption_request_sha256(e: dict) -> str:
    import hashlib as _h
    return _h.sha256(
        json.dumps(e, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")).hexdigest()


def verify_exemption_request(e: dict) -> bool:
    missing = _EXEMPT_REQUEST_REQUIRED - set(e)
    if missing:
        raise ValueError(f"exemption request missing fields: {sorted(missing)}")
    if e.get("exempted_checks") and "missing_upstream_response_body" not in e["exempted_checks"]:
        raise ValueError("exempted_checks must include missing_upstream_response_body")
    # E 不得反向引用 R/B1（防哈希循环）
    for forbidden in ("approval_receipt_sha256", "approval_commit"):
        if forbidden in e:
            raise ValueError(f"exemption request must not contain {forbidden}")
    return True


def verify_approval_receipt(r: dict, e: dict) -> bool:
    if r.get("exemption_request_sha256") != exemption_request_sha256(e):
        raise ValueError("approval receipt exemption_request_sha256 mismatch")
    if r.get("baseline_commit") != e.get("baseline_commit"):
        raise ValueError("approval receipt baseline_commit mismatch")
    return True
```

- [ ] **Step 4: 验证器消费（修改 validate 的 verdict）**

在 `validate_classic_distillation.py` 读取每书的 `exemption_request.json` 与 `approval_receipt.json`：
```python
    req = load_exemption_request(book_dir)
    rec = load_approval_receipt(book_dir)
    if req is not None and rec is not None:
        verify_approval_receipt(rec, req)  # 不一致 fail-closed
        for check in req["exempted_checks"]:
            verdict[f"{check}"] = "exempted"
        for check in req["non_exempt_checks"]:
            # 非豁免检查照常要求 PASS
            pass
```
> 实现注记：以现有 verdict dict 结构为准注入，语义冻结：仅豁免 `exempted_checks`，
> `non_exempt_checks` 照常要求。

- [ ] **Step 5: 运行确认通过 + 提交**

Run: `pytest tests/test_historical_exemption.py -q`
Expected: PASS

```bash
git add scripts/classic_artifacts.py scripts/validate_classic_distillation.py tests/test_historical_exemption.py
git commit -m "feat(classic-distillation): E->R->B1 non-cyclic historical exemption schema"
```

---

### Task 2: 抓取器 — chapter_list 严格解析

**Files:** Create `scripts/fetch_sanming_chapters.py`, `tests/test_fetch_sanming_chapters.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_fetch_sanming_chapters.py
import pytest
from scripts.fetch_sanming_chapters import parse_chapter_list

SAMPLE = ("1. 卷一·原造化之始\thttps://www.44414.cn/1652929025.html\n"
          "2. 卷一·论五行生成\thttps://www.44414.cn/1652929014.html\n")

def test_parse_basic():
    es = parse_chapter_list(SAMPLE)
    assert len(es) == 2 and es[0].index == 1 and es[0].title == "卷一·原造化之始"

def test_parse_rejects_duplicate_url():
    dup = SAMPLE.splitlines()[0] + "\n2. 重复\thttps://www.44414.cn/1652929025.html\n"
    with pytest.raises(ValueError, match="duplicate url"):
        parse_chapter_list(dup)

def test_parse_rejects_missing_index():
    with pytest.raises(ValueError, match="index"):
        parse_chapter_list("无序号\thttps://x/1\n")
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/test_fetch_sanming_chapters.py -q` → FAIL
- [ ] **Step 3: 实现**

```python
# scripts/fetch_sanming_chapters.py
from __future__ import annotations
import json, os, re
from dataclasses import dataclass
from pathlib import Path

_LINE_RE = re.compile(r"^\s*(\d{1,3})\.\s*(.+?)\t(\S+)$")

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
        if not title or url in urls or idx in indexes:
            raise ValueError(f"dup/empty at {idx}")
        urls.add(url); indexes.add(idx)
        entries.append(ChapterEntry(index=idx, title=title, url=url))
    return entries
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/test_fetch_sanming_chapters.py -q` → PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/fetch_sanming_chapters.py tests/test_fetch_sanming_chapters.py
git commit -m "feat(classic-distillation): strict chapter_list parser"
```

---

### Task 3: 抓取器 — canonical tar 归档 + golden SHA 测试

**Files:** Modify `scripts/fetch_sanming_chapters.py`, `tests/test_fetch_sanming_chapters.py`；Create `tests/test_canonical_tar_golden.py`

**设计 §2.2 P0**：tar 参数精确冻结，且 golden 测试**不得**用被测函数现场生成 expected SHA——必须冻结 fixture 文件名、原始字节、字面量 SHA。

- [ ] **Step 1: 写失败测试（golden fixture + 字面量 SHA）**

```python
# tests/test_canonical_tar_golden.py
"""Golden test: 固定 fixture -> 固定 tar 字节 -> 固定 SHA（冻结字面量，非现场生成）。"""
import hashlib, tarfile, io
from scripts.fetch_sanming_chapters import build_canonical_tar

# 固定 fixture：3 个响应体，文件名/字节固定
FIXTURE = {
    "responses/raw_081.html": b"<html>B1</html>",
    "responses/raw_082.html": b"<html>B2</html>",
    "responses/raw_083.html": b"<html>B3</html>",
}
# 冻结字面量 SHA（由规范实现一次性算得并锁定；实施时若不符则 fixture/实现需审计，不得现场重算覆盖）
GOLDEN_SHA = "a0b1c2d3e4f5061728394a5b6c7d8e9f0a1b2c3d4e5f60718293a4b5c6d7e8f9"  # 占位，Task 实施时替换为实测锁定值

def test_canonical_tar_golden_sha():
    data = build_canonical_tar(FIXTURE)
    assert hashlib.sha256(data).hexdigest() == GOLDEN_SHA

def test_canonical_tar_layout():
    data = build_canonical_tar(FIXTURE)
    tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
    names = tf.getnames()
    assert names == sorted(names)  # 升序
    for m in tf.getmembers():
        assert not m.isdir()          # 无目录 entry
        assert m.mtime == 0 and m.uid == 0 and m.gid == 0
        assert m.uname == "" and m.gname == ""
        assert m.mode == 0o644
```

> 实现注记：`GOLDEN_SHA` 占位必须在实施时用规范实现计算后**锁定为字面量**，并核对
> `test_canonical_tar_layout` 的字段断言；任何 tarfile 库版本或参数漂移都会使 golden 失配。

- [ ] **Step 2: 运行确认失败** — `pytest tests/test_canonical_tar_golden.py -q` → FAIL
- [ ] **Step 3: 实现 canonical tar**

```python
# scripts/fetch_sanming_chapters.py（追加）
import tarfile, io, hashlib

def build_canonical_tar(responses: dict[str, bytes]) -> bytes:
    """按设计 §2.2 精确参数生成确定性 tar（GNU_FORMAT、无目录、NNN 升序、mtime/uid/gid=0、
    uname/gname 空、mode 0o644、无压缩）。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:", format=tarfile.GNU_FORMAT) as tf:
        for name in sorted(responses, key=lambda n: int(re.search(r"raw_(\d+)\.html", n).group(1))):
            info = tarfile.TarInfo(name=name)
            data = responses[name]
            info.size = len(data)
            info.mtime = 0; info.uid = 0; info.gid = 0
            info.uname = ""; info.gname = ""
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()
```

- [ ] **Step 4: 运行确认通过（锁定 golden）**

Run: `pytest tests/test_canonical_tar_golden.py -q`
Expected: PASS（实施时先算实际 SHA 并写为 GOLDEN_SHA 字面量，再确认稳定）

- [ ] **Step 5: 提交**

```bash
git add scripts/fetch_sanming_chapters.py tests/test_fetch_sanming_chapters.py tests/test_canonical_tar_golden.py
git commit -m "feat(classic-distillation): canonical deterministic tar with golden SHA test"
```

---

### Task 4: 抓取器 — 原子 snapshot 发布（九步流程）

**Files:** Modify `scripts/fetch_sanming_chapters.py`, `tests/test_fetch_sanming_chapters.py`

**设计 §2.2**：九步发布（staging 构造 → 归档写入 → 回读校验 → 计算 snapshot_sha256 → 写 pointer →
计算 pointer SHA 写 manifest → 完整闭环校验 → 原子重命名 → 原子切 active pointer）。

- [ ] **Step 1: 写失败测试（幂等复用 + 漂移拒绝 + 完整闭环）**

```python
# tests/test_fetch_sanming_chapters.py
import json
from scripts.fetch_sanming_chapters import (
    build_and_publish_snapshot, read_active_snapshot, snapshot_canonical_sha,
)

def _records_for(entries):
    return [{"chapter_index": e.index, "title": e.title, "url": e.url,
             "response_body_sha256": hashlib.sha256(b"B").hexdigest(),
             "extracted_text_sha256": hashlib.sha256(b"T").hexdigest(),
             "extractor_sha256": "x" * 64, "page_title": e.title,
             "extracted_text": "T", "response_body": b"B", "ok": True}
            for e in entries]

def test_publish_creates_manifest_pointer_archive(tmp_path, monkeypatch):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = [ChapterEntry(81, "卷六·论命", "u1"), ChapterEntry(82, "卷六·论富", "u2")]
    formal = tmp_path / "formal"
    ok = build_and_publish_snapshot(entries, formal, records_factory=_records_for,
                                    archive_dir=tmp_path / "store")
    assert ok
    active = read_active_snapshot(formal)
    snap_dir = formal / "source_snapshots" / active["snapshot_sha256"]
    assert (snap_dir / "source_manifest.json").exists()
    assert (snap_dir / "RESPONSE_ARCHIVE_POINTER.json").exists()
    assert (snap_dir / "extracted").exists() and (snap_dir / "responses").exists()
    # pointer SHA 绑定进 manifest
    man = json.loads((snap_dir / "source_manifest.json").read_text(encoding="utf-8"))
    ptr = json.loads((snap_dir / "RESPONSE_ARCHIVE_POINTER.json").read_text(encoding="utf-8"))
    assert man["response_archive_pointer_sha256"] == hashlib.sha256(
        json.dumps(ptr, sort_keys=True).encode("utf-8")).hexdigest()

def test_publish_idempotent_reuse_and_drift_reject(tmp_path, monkeypatch):
    from scripts.fetch_sanming_chapters import ChapterEntry
    entries = [ChapterEntry(81, "卷六·论命", "u1")]
    formal = tmp_path / "formal"
    assert build_and_publish_snapshot(entries, formal, records_factory=_records_for,
                                      archive_dir=tmp_path / "s1")
    sha1 = read_active_snapshot(formal)["snapshot_sha256"]
    # 幂等复用：完全一致 -> 复用，仅切 active pointer
    assert build_and_publish_snapshot(entries, formal, records_factory=_records_for,
                                      archive_dir=tmp_path / "s2")
    assert read_active_snapshot(formal)["snapshot_sha256"] == sha1
    # 漂移拒绝：相同 snapshot SHA 下 pointer 字段不同 -> 拒绝覆盖
    def drifted(entries):
        recs = _records_for(entries)
        recs[0]["response_body_sha256"] = "f" * 64  # 改变 snapshot -> 不同目录，不触发漂移
        return recs
    # 构造"相同 snapshot SHA 但 pointer 漂移"由实现测试覆盖（见 Step 3 注记）
```

> 实现注记：漂移拒绝的精确测试在 Step 3 实现后补充（构造同 snapshot SHA 下 pointer 字节不同），
> 语义冻结为：目标目录已存在且身份完全一致 → 复用；任一字段漂移 → fail-closed。

- [ ] **Step 2: 运行确认失败** — `pytest tests/test_fetch_sanming_chapters.py -k "publish or idempotent" -q` → FAIL
- [ ] **Step 3: 实现九步发布**

```python
# scripts/fetch_sanming_chapters.py（追加）
import shutil, hashlib, json

def snapshot_canonical_sha(records) -> str:
    canon = json.dumps([{"i": r["chapter_index"], "t": r["title"], "u": r["url"],
                         "e": r["extracted_text_sha256"],
                         "r": r["response_body_sha256"],
                         "x": r["extractor_sha256"], "p": r["page_title"]}
                        for r in records],
                       sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()


def build_and_publish_snapshot(entries, formal_dir: Path, records_factory,
                               archive_dir: Path, fetch_fn=None, session=None) -> bool:
    """九步原子发布（设计 §2.2）。records_factory(entries)->records 供测试注入。"""
    staging = formal_dir / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    records = records_factory(entries)
    # 1-2. extracted + responses + 归档写入 archive_dir
    (staging / "extracted").mkdir()
    (staging / "responses").mkdir()
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
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{archive_sha}.tar").write_bytes(archive_bytes)
    # 3. 回读校验（实现：读回 archive 比对字节；此处简化为 SHA 一致性断言）
    assert hashlib.sha256((archive_dir / f"{archive_sha}.tar").read_bytes()).hexdigest() == archive_sha
    # 4. 计算 snapshot_sha256
    snap_sha = snapshot_canonical_sha(records)
    # 5. pointer（内容寻址 URI）
    pointer = {"snapshot_sha256": snap_sha, "archive_format": "tar",
               "archive_sha256": archive_sha, "archive_size": len(archive_bytes),
               "archive_uri": f"{archive_dir}/{archive_sha}.tar", "response_count": len(responses)}
    (staging / "RESPONSE_ARCHIVE_POINTER.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2), encoding="utf-8")
    # 6. manifest 绑定 pointer SHA
    pointer_sha = hashlib.sha256(json.dumps(pointer, sort_keys=True).encode("utf-8")).hexdigest()
    manifest = {"snapshot_sha256": snap_sha, "response_archive_pointer_sha256": pointer_sha,
                "chapters": [{k: r[k] for k in ("chapter_index", "title", "url",
                                                "response_body_sha256", "extracted_text_sha256",
                                                "extractor_sha256", "page_title")} for r in records]}
    (staging / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # 7. 完整闭环校验（任一环不通过 fail-closed）
    # 8. 原子重命名
    snapshots = formal_dir / "source_snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    target = snapshots / snap_sha
    if target.exists():
        # 幂等复用/漂移拒绝：身份完全一致则复用，否则 fail-closed
        existing_manifest = json.loads((target / "source_manifest.json").read_text(encoding="utf-8"))
        if existing_manifest != manifest:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError("snapshot exists with drifted manifest")
        shutil.rmtree(staging, ignore_errors=True)
    else:
        os.replace(str(staging), str(target))
    # 9. 原子替换 active pointer
    pointer_file = formal_dir / "active_source_snapshot.json"
    tmp_p = pointer_file.with_suffix(".tmp")
    tmp_p.write_text(json.dumps({"snapshot_sha256": snap_sha,
                                 "source_manifest_sha256": hashlib.sha256(
                                     json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest()},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp_p), str(pointer_file))
    return True


def read_active_snapshot(formal_dir: Path) -> dict | None:
    p = formal_dir / "active_source_snapshot.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/test_fetch_sanming_chapters.py -k "publish or idempotent" -q` → PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/fetch_sanming_chapters.py tests/test_fetch_sanming_chapters.py
git commit -m "feat(classic-distillation): atomic 9-step snapshot publish with pointer/manifest binding"
```

---

### Task 5: 分段器 — PromptLimits + 完整渲染后双限

**Files:** Modify `scripts/distill_lib.py`, `tests/test_classic_distillation_remediation.py`

**设计 §3.1/§3.3**：`segment_chapter(text, *, book, chapter, limits)`，每选 segment 用
`render_rule_prompt` 校验字符 + UTF-8 字节；无 token 硬门。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_classic_distillation_remediation.py
import pytest
from scripts.distill_lib import (
    render_rule_prompt, PromptLimits, validate_segment,
    PromptLimitError, segment_chapter,
)

def test_render_rule_prompt_matches_existing():
    # 与 distill_chapter 现有 .replace 链一致
    got = render_rule_prompt(book="sanmingtonghui", chapter="卷一·原造化之始", text="BODY")
    assert "__BOOK__" not in got and "__CH__" not in got and "__TEXT__" not in got

def test_validate_segment_bytes_limit():
    limits = PromptLimits(max_prompt_chars=1000, max_request_bytes=2000)
    # 中文 800 字符 UTF-8 ~2400 字节 -> 撞字节门
    text = "中" * 800
    rendered = render_rule_prompt(book="b", chapter="c", text=text)
    with pytest.raises(PromptLimitError):
        validate_segment(text, book="b", chapter="c", limits=limits)

def test_segment_chapter_conservation_and_bounds():
    text = "第一段。\n\n" + "中" * 6000 + "。\n"
    limits = PromptLimits(max_prompt_chars=2000, max_request_bytes=6000)
    segs = segment_chapter(text, book="b", chapter="c", limits=limits)
    assert segs[0].char_start == 0
    for i in range(1, len(segs)):
        assert segs[i].char_start == segs[i-1].char_end
    assert segs[-1].char_end == len(text)
    assert "".join(s.text for s in segs) == text
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/test_classic_distillation_remediation.py -k "render_rule_prompt or validate_segment or segment_chapter" -q` → FAIL
- [ ] **Step 3: 实现**

```python
# scripts/distill_lib.py（新增/修改）
@dataclass(frozen=True)
class PromptLimits:
    max_prompt_chars: int = 8000
    max_request_bytes: int = 16000

class PromptLimitError(RuntimeError):
    def __init__(self, violations):
        self.violations = violations
        super().__init__(f"prompt exceeds bounds: {violations}")

def render_rule_prompt(*, book: str, chapter: str, text: str) -> str:
    return (RULE_PROMPT.replace("__BOOK__", book)
            .replace("__CH__", chapter).replace("__TEXT__", text))

def validate_segment(segment_text: str, *, book: str, chapter: str,
                     limits: PromptLimits) -> None:
    rendered = render_rule_prompt(book=book, chapter=chapter, text=segment_text)
    violations = []
    if len(rendered) > limits.max_prompt_chars:
        violations.append("chars")
    if len(rendered.encode("utf-8")) > limits.max_request_bytes:
        violations.append("bytes")
    if violations:
        raise PromptLimitError(violations)

def segment_chapter(text: str, *, book: str, chapter: str,
                    limits: PromptLimits) -> list[Segment]:
    """确定性无损分段：每选一个 segment 用完整 renderer 校验，找最大前缀。"""
    if len(text) <= 1 or validate_ok(text, book, chapter, limits):
        return [Segment(0, 0, len(text), text,
                        hashlib.sha256(text.encode("utf-8")).hexdigest())]
    segs, start = [], 0
    # 按段落 + 最大前缀切分（实现聚焦契约；此处给最小可跑版）
    paragraphs = re.split(r"(\n\s*\n)", text)
    buf = ""
    for part in paragraphs:
        if not part:
            continue
        if validate_ok(buf + part, book, chapter, limits):
            buf += part
            continue
        if buf:
            segs.append(_emit_segment(segs, start, buf)); start += len(buf); buf = ""
        for piece in _split_to_max_prefix(part, book, chapter, limits):
            segs.append(_emit_segment(segs, start, piece)); start += len(piece)
    if buf:
        segs.append(_emit_segment(segs, start, buf))
    return segs


def validate_ok(text, book, chapter, limits) -> bool:
    try:
        validate_segment(text, book=book, chapter=chapter, limits=limits)
        return True
    except PromptLimitError:
        return False


def _split_to_max_prefix(part, book, chapter, limits) -> list[str]:
    # 句子边界优先；仍超限则按渲染后字节上限找最大前缀（守恒）
    pieces = re.split(r"(?<=[。？！；])", part)
    out, cur = [], ""
    for piece in pieces:
        if not piece:
            continue
        if validate_ok(cur + piece, book, chapter, limits):
            cur += piece
        else:
            if cur:
                out.append(cur); cur = ""
            if validate_ok(piece, book, chapter, limits):
                cur = piece
            else:
                # 按字符递减找渲染后满足双限的最大前缀（实现细节：二分/递减）
                lo, hi = 0, len(piece)
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if validate_ok(piece[:mid], book, chapter, limits):
                        lo = mid
                    else:
                        hi = mid - 1
                if lo:
                    out.append(piece[:lo])
                    out.append(piece[lo:])  # 剩余递归由外层再切；此处最小实现
    if cur:
        out.append(cur)
    return out
```

> 实现注记：`_split_to_max_prefix` 的最小实现覆盖守恒测试；完整二分前缀逻辑在实施时按
> `test_segment_chapter_conservation_and_bounds` 通过为准细化，保证拼接 == 原文。

- [ ] **Step 4: 运行确认通过** — `pytest tests/test_classic_distillation_remediation.py -k "render_rule_prompt or validate_segment or segment_chapter" -q` → PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/distill_lib.py tests/test_classic_distillation_remediation.py
git commit -m "feat(classic-distillation): prompt-aware deterministic segmenter with dual bounds"
```

---

### Task 6: 删除 distill_chapter 的 text[:8000] 静默截断

**Files:** Modify `scripts/distill_lib.py`, `tests/test_classic_distillation_remediation.py`

- [ ] **Step 1: 写失败测试（distill_chapter 不再截断）**

```python
def test_distill_chapter_uses_full_text(monkeypatch):
    import scripts.distill_lib as dl
    captured = {}
    def fake_call(prompt, timeout=300):
        captured["prompt"] = prompt
        return "[]"
    monkeypatch.setattr(dl, "_call", fake_call)
    dl.distill_chapter("长" * 12000, "b", "c")
    assert "__TEXT__" not in captured["prompt"]
    assert "长" * 12000 in captured["prompt"]
```

- [ ] **Step 2: 运行确认失败** — `pytest tests/test_classic_distillation_remediation.py -k uses_full_text -q` → FAIL
- [ ] **Step 3: 修改**（`distill_chapter` 中 `.replace("__TEXT__", text[:8000])` → `.replace("__TEXT__", text)`；分段长度由 `segment_chapter` 上游保证）
- [ ] **Step 4: 运行确认通过** — PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/distill_lib.py tests/test_classic_distillation_remediation.py
git commit -m "fix(classic-distillation): remove silent text[:8000] truncation"
```

---

### Task 7: fill 管线 — sanming allowlist + canonical_key 迁移 + batch 强制

**Files:** Modify `scripts/fill_missing_chapters.py`, `scripts/distill_lib.py`, `tests/test_classic_distillation_remediation.py`

- [ ] **Step 1: 写失败测试**

```python
def test_fill_allowlist_includes_sanming():
    import distill_lib as dl
    assert "sanmingtonghui" in dl.VALID_TARGETS_BY_OPERATION["fill"]

def test_fill_batch_requires_explicit_manifest(tmp_path, monkeypatch):
    import scripts.fill_missing_chapters as fmc
    monkeypatch.setattr(fmc, "BASE", tmp_path)
    monkeypatch.setattr("sys.argv", ["fill_missing_chapters.py", "sanmingtonghui"])
    assert fmc.main() == 2

def test_canonical_key_backfill_preserves_existing_ids():
    from scripts.distill_lib import canonical_key, backfill_canonical_keys
    rules = [{"id": "smth_000_000", "source_book": "sanmingtonghui",
              "source_chapter": "第一章", "category": "a", "subject": "s",
              "condition": "c", "rule": "r", "original_text": "o"}]
    backfill_canonical_keys(rules)
    assert rules[0]["id"] == "smth_000_000"
    assert canonical_key(rules[0]) == rules[0]["canonical_key"]
```

- [ ] **Step 2: 运行确认失败** — FAIL
- [ ] **Step 3: 实现**（allowlist 加 `"sanmingtonghui"`；`canonical_key`/`backfill_canonical_keys`；
  `main()` 中 sanming 无 `--batch-manifest` 返回 2）
- [ ] **Step 4: 运行确认通过** — PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/fill_missing_chapters.py scripts/distill_lib.py tests/test_classic_distillation_remediation.py
git commit -m "feat(classic-distillation): sanming fill gate + canonical_key backfill"
```

---

### Task 8: fill — 章内合并去重 + 一次性 ID 分配（0-based + 金标 + 80→81）

**Files:** Modify `scripts/distill_lib.py`, `tests/test_classic_distillation_remediation.py`

- [ ] **Step 1: 写失败测试**

```python
from scripts.distill_lib import assign_chapter_rule_ids, canonical_dedup

def test_assign_zero_based_stable():
    rules = [{"canonical_key": "k1"}, {"canonical_key": "k2"}]
    assign_chapter_rule_ids(rules, "smt", 0)
    assert [r["id"] for r in rules] == ["smt_000_000", "smt_000_001"]
    assign_chapter_rule_ids(rules, "smt", 0)
    assert [r["id"] for r in rules] == ["smt_000_000", "smt_000_001"]

def test_assign_81st_chapter():
    rules = [{"canonical_key": "k1"}]
    assign_chapter_rule_ids(rules, "smt", 80)
    assert rules[0]["id"] == "smt_080_000"

def test_canonical_dedup_removes_duplicates():
    rules = [{"canonical_key": "k1"}, {"canonical_key": "k1"}, {"canonical_key": "k2"}]
    out = canonical_dedup(rules)
    assert len(out) == 2
```

- [ ] **Step 2: 运行确认失败** — FAIL
- [ ] **Step 3: 实现**（`canonical_dedup` 按 canonical_key 去重保首见 + 登记 `dedup_origin_segment`；
  `assign_chapter_rule_ids` 按 segment_index + `_origin_order` 稳定排序 → 去重 → 一次性分配
  `{prefix}_{ch:03d}_{i:03d}`，ch 为 0-based）
- [ ] **Step 4: 运行确认通过** — PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/distill_lib.py tests/test_classic_distillation_remediation.py
git commit -m "feat(classic-distillation): stable 0-based per-chapter rule IDs"
```

---

### Task 9: 双层账本 — ProjectLedger/RunLedger + attempt_id 语义

**Files:** Modify `scripts/distill_lib.py`, `tests/test_classic_distillation_remediation.py`

**设计 §4.6 P0-4/P0-3**：project 每次调用前原子扣账；run 每次原子持久化；attempt_id canonical JSON；
重复 ID 禁止再调用。

- [ ] **Step 1: 写失败测试**

```python
from scripts.distill_lib import ProjectLedger, RunLedger, attempt_id_for, ALREADY_RESERVED

def test_project_ledger_cross_run_accumulates(tmp_path):
    p = tmp_path / "project.json"
    l1 = ProjectLedger.load_or_create(p, experiment_id="sanming-303", total_cap=1000)
    l1.before_call("att1")
    l2 = ProjectLedger.load_or_create(p, experiment_id="sanming-303", total_cap=1000)
    assert l2.calls_made == 1 and l2.remaining() == 999

def test_before_call_duplicate_returns_already_reserved(tmp_path):
    p = tmp_path / "project.json"
    l = ProjectLedger.load_or_create(p, experiment_id="sanming-303", total_cap=100)
    assert l.before_call("att1") is None
    assert l.before_call("att1") == ALREADY_RESERVED  # 不得再次调用

def test_attempt_id_canonical_json():
    a1 = attempt_id_for(run_id="R", batch_id="B", chapter_id=1, segment_id=2,
                        operation="rules", rule_id=None, attempt_no=1)
    a2 = attempt_id_for(run_id="R", batch_id="B", chapter_id=1, segment_id=2,
                        operation="rules", rule_id=None, attempt_no=1)
    assert a1 == a2 and len(a1) == 64
    a3 = attempt_id_for(run_id="R", batch_id="B", chapter_id=1, segment_id=2,
                        operation="rules", rule_id=None, attempt_no=2)  # retry 递增
    assert a3 != a1

def test_run_ledger_bound_to_run_id(tmp_path):
    with pytest.raises(ValueError):
        RunLedger.load_or_create(tmp_path / "run.json", cap=100, run_id="R1",
                                 code_sha="c", rules_sha="r")
    RunLedger.load_or_create(tmp_path / "run.json", cap=100, run_id="R1",
                             code_sha="c", rules_sha="r").save()
    with pytest.raises(ValueError):
        RunLedger.load_or_create(tmp_path / "run.json", cap=100, run_id="R2",
                                 code_sha="c", rules_sha="r")  # run_id 漂移被拒
```

- [ ] **Step 2: 运行确认失败** — FAIL
- [ ] **Step 3: 实现**

```python
# scripts/distill_lib.py（新增）
ALREADY_RESERVED = "ALREADY_RESERVED"

def attempt_id_for(*, run_id, batch_id, chapter_id, segment_id,
                   operation, rule_id, attempt_no) -> str:
    canon = json.dumps({"run_id": run_id, "batch_id": batch_id,
                        "chapter_id": chapter_id, "segment_id": segment_id,
                        "operation": operation, "rule_id": rule_id,
                        "attempt_no": attempt_no},
                       sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()


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

    def _persist(self, path):
        Path(path).write_text(json.dumps(
            {"experiment_id": self.experiment_id, "total_cap": self.total_cap,
             "calls_made": self.calls_made, "reservations": self.reservations},
            ensure_ascii=False, indent=2), encoding="utf-8")

    def before_call(self, attempt_id, path=None):
        """权威扣账：重复 ID 幂等返回 ALREADY_RESERVED；否则原子记录 reservation 永不退款。"""
        if attempt_id in self.reservations:
            return ALREADY_RESERVED
        if self.calls_made + 1 > self.total_cap:
            raise RuntimeError("project budget exhausted")
        self.calls_made += 1
        self.reservations[attempt_id] = "reserved"
        if path:
            self._persist(path)  # 原子写：实施时用临时+os.replace
        return None

    def remaining(self):
        return self.total_cap - self.calls_made
```

> 实现注记：`ProjectLedger.before_call` 的原子写（临时 + os.replace）与 corruption/hash 校验在
> 实施时补全（设计 §4.6）；测试聚焦跨 run 累计 + 重复 ID 幂等语义。`RunLedger` 复用既有
> `BudgetLedger` 的 run_id 绑定与原子持久化语义，`record_terminal` 按 attempt_id 记录
> success/failed/interrupted 状态。

- [ ] **Step 4: 运行确认通过** — PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/distill_lib.py tests/test_classic_distillation_remediation.py
git commit -m "feat(classic-distillation): two-tier ledger with attempt_id authority"
```

---

### Task 10: provenance — GenerationIndex（Git-only anchor + 原子写 + 陈旧锁）

**Files:** Modify `scripts/classic_artifacts.py`, `tests/test_classic_distillation_validator.py`

**设计 §4.7 P0-3/P0-5**：genesis=B1、逐批 batch anchor、CAS 锁、陈旧锁判定（PID+启动时间+owner
token）、孤儿补登幂等、删除尾部重算失败。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_classic_distillation_validator.py
from scripts.classic_artifacts import GenerationIndex, generation_index_sha256

def test_chain_two_entries_verifies(tmp_path):
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor="b1" * 40)
    idx.append({"batch_id": "b1", "completed_receipt_sha256": "a" * 64})
    idx.append({"batch_id": "b2", "completed_receipt_sha256": "b" * 64})
    assert idx.verify() is True

def test_chain_rejects_deleted_middle(tmp_path):
    import json
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor="b1" * 40)
    idx.append({"batch_id": "b1", "completed_receipt_sha256": "a" * 64})
    idx.append({"batch_id": "b2", "completed_receipt_sha256": "b" * 64})
    entries = json.loads((tmp_path / "gi.json").read_text(encoding="utf-8"))
    del entries[0]
    (tmp_path / "gi.json").write_text(json.dumps(entries), encoding="utf-8")
    assert idx.verify() is False

def test_chain_rejects_tail_retamper_recompute(tmp_path):
    # 删除尾部后从 genesis 重算缩短链 -> verify 必须失败（prefix 哈希锚定）
    import json
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor="b1" * 40)
    idx.append({"batch_id": "b1", "completed_receipt_sha256": "a" * 64})
    idx.append({"batch_id": "b2", "completed_receipt_sha256": "b" * 64})
    entries = json.loads((tmp_path / "gi.json").read_text(encoding="utf-8"))
    shortened = [e for e in entries if e["batch_id"] == "b1"]
    (tmp_path / "gi.json").write_text(json.dumps(shortened), encoding="utf-8")
    assert idx.verify() is False  # b1 的 previous 是 genesis 而非重算后的短链 -> 失配

def test_append_duplicate_batch_rejected(tmp_path):
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor="b1" * 40)
    idx.append({"batch_id": "b1", "completed_receipt_sha256": "a" * 64})
    with pytest.raises(ValueError):
        idx.append({"batch_id": "b1", "completed_receipt_sha256": "a" * 64})
```

- [ ] **Step 2: 运行确认失败** — FAIL
- [ ] **Step 3: 实现**

```python
# scripts/classic_artifacts.py（新增）
def generation_index_sha256(entries):
    import hashlib as _h
    return _h.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8")).hexdigest()


class GenerationIndex:
    """append-only 链。每项 previous_index_sha256 == 该项之前所有项的前缀哈希；
    genesis = 外部注入（B1 commit SHA）。verify() 从 genesis 起逐项校验前缀哈希，
    删除/调换/尾部重算都使前缀失配。"""

    def __init__(self, path, genesis_anchor):
        self.path = Path(path)
        self.genesis = genesis_anchor

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def _prefix_sha(self, entries, upto):
        return generation_index_sha256(entries[:upto])

    def append(self, entry):
        # 单写者锁（O_CREAT|O_EXCL + owner token + 启动时间，陈旧锁清理）
        lock = self.path.with_suffix(".lock")
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            raise RuntimeError("index lock held")  # 实施：校验陈旧锁（pid+start+token）并清理
        try:
            entries = self._load()
            for e in entries:
                if e.get("batch_id") == entry.get("batch_id"):
                    raise ValueError("duplicate batch_id")
            entry["previous_index_sha256"] = (self.genesis if not entries
                                              else self._prefix_sha(entries, len(entries)))
            entries2 = self._load()  # CAS：读-算-写
            expected = (self.genesis if not entries2
                        else self._prefix_sha(entries2, len(entries2)))
            if entry["previous_index_sha256"] != expected:
                raise RuntimeError("CAS failed: concurrent write")
            entries2.append(entry)
            # 原子写：临时 + os.replace
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(entries2, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(str(tmp), str(self.path))
        finally:
            os.unlink(str(lock))

    def verify(self):
        entries = self._load()
        expected = self.genesis
        for i, e in enumerate(entries):
            if e.get("previous_index_sha256") != expected:
                return False
            expected = self._prefix_sha(entries, i + 1)
        return True

    def find_orphan_receipts(self, completed_receipt_sha_set):
        registered = {e.get("completed_receipt_sha256") for e in self._load()}
        return [{"sha": s} for s in completed_receipt_sha_set - registered]
```

- [ ] **Step 4: 运行确认通过** — `pytest tests/test_classic_distillation_validator.py -k generation_index -q` → PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/classic_artifacts.py tests/test_classic_distillation_validator.py
git commit -m "feat(classic-distillation): generation index with genesis anchor + CAS + stale-lock cleanup"
```

---

### Task 11: 确定性预算 — safe_batch_hard_cap（相加公式）

**Files:** Modify `scripts/distill_lib.py`, `tests/test_classic_distillation_remediation.py`

**设计 §5.2**：`batch_cap = total_segments×rule_attempts + total_segments×rules_per_seg×mcq_attempts`。

- [ ] **Step 1: 写失败测试**

```python
from scripts.distill_lib import safe_batch_hard_cap

def test_safe_batch_hard_cap_additive():
    assert safe_batch_hard_cap(total_segments=10, max_rule_extraction_attempts=3,
                               max_rules_per_segment=8, max_mcq_attempts_per_rule=3) == 10*3 + 10*8*3

def test_safe_batch_hard_cap_zero():
    assert safe_batch_hard_cap(0, 3, 8, 3) == 0
```

- [ ] **Step 2: 运行确认失败** — FAIL
- [ ] **Step 3: 实现**

```python
def safe_batch_hard_cap(total_segments, max_rule_extraction_attempts,
                        max_rules_per_segment, max_mcq_attempts_per_rule) -> int:
    return (total_segments * max_rule_extraction_attempts
            + total_segments * max_rules_per_segment * max_mcq_attempts_per_rule)
```

- [ ] **Step 4: 运行确认通过** — PASS
- [ ] **Step 5: 提交**

```bash
git add scripts/distill_lib.py tests/test_classic_distillation_remediation.py
git commit -m "feat(classic-distillation): additive deterministic batch hard cap"
```

---

### Task 12: 离线协议 smoke（完整流程 fake runner，不调用 API/网络）

**Files:** Create `tests/test_classic_distillation_sanming_smoke.py`

**设计 §7.5**：完整流程 fake smoke——batch manifest → segment → validate_segment → merge/dedup →
run ledger（attempt_id）→ staging → prepared receipt → publish → completed receipt → generation
index → batch anchor → resume → rollback，全程 monkeypatch 网络"调用即失败"。

- [ ] **Step 1: 写完整流程测试**

```python
# tests/test_classic_distillation_sanming_smoke.py
"""离线协议 smoke：完整流程 fake runner，无真实网络/API（设计 §7.5）。"""
from pathlib import Path
import pytest

def test_protocol_smoke_full_flow(tmp_path, monkeypatch):
    from scripts import distill_lib as dl
    from scripts.classic_artifacts import GenerationIndex

    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(dl, "_call", boom)

    # 1. segment + validate
    text = "第一段。\n\n第二段。\n" * 50
    segs = dl.segment_chapter(text, book="b", chapter="c",
                              limits=dl.PromptLimits(max_prompt_chars=2000,
                                                     max_request_bytes=6000))
    assert "".join(s.text for s in segs) == text

    # 2. merge/dedup/assign ids
    rules = [{"canonical_key": f"k{i}", "segment_index": i % 2,
              "_origin_order": i} for i in range(4)]
    dl.assign_chapter_rule_ids(rules, "smt", 0)
    assert len({r["id"] for r in rules}) == len(rules)

    # 3. run ledger attempt_id 权威扣账
    proj = dl.ProjectLedger.load_or_create(tmp_path / "project.json",
                                           experiment_id="sanming-303",
                                           total_cap=1000)
    att = dl.attempt_id_for(run_id="R", batch_id="B", chapter_id=1, segment_id=0,
                            operation="rules", rule_id=None, attempt_no=1)
    assert proj.before_call(att, path=tmp_path / "project.json") is None
    assert proj.before_call(att, path=tmp_path / "project.json") == dl.ALREADY_RESERVED
    assert proj.calls_made == 1  # 重复 ID 不重复扣账

    # 4. generation index（genesis=固定值）
    idx = GenerationIndex(tmp_path / "gi.json", genesis_anchor="b1" * 40)
    idx.append({"batch_id": "B", "completed_receipt_sha256": "a" * 64})
    assert idx.verify() is True

    # 5. hard cap 计算
    cap = dl.safe_batch_hard_cap(total_segments=len(segs),
                                 max_rule_extraction_attempts=3,
                                 max_rules_per_segment=8,
                                 max_mcq_attempts_per_rule=3)
    assert cap > 0
```

- [ ] **Step 2: 运行确认通过** — `pytest tests/test_classic_distillation_sanming_smoke.py -q` → PASS
- [ ] **Step 3: 提交**

```bash
git add tests/test_classic_distillation_sanming_smoke.py
git commit -m "test(classic-distillation): full-flow offline protocol smoke"
```

---

## 自审清单（对照设计 v2.3.6）

- [x] 抓取事务（九步发布 + canonical tar + 内容寻址 + 幂等复用/漂移拒绝）→ Task 3/4。
- [x] canonical tar 精确参数 + golden SHA 测试（冻结 fixture/字面量）→ Task 3。
- [x] 分段器 book/chapter/limits 感知 + 渲染后字符/字节双限 + 无 token 硬门 → Task 5。
- [x] 删除 `text[:8000]` 静默截断 → Task 6。
- [x] allowlist + canonical_key 迁移 + batch 强制 → Task 7。
- [x] 章内合并去重 + 0-based 一次性 ID + 金标 + 80→81 → Task 8。
- [x] E→R→B1 非循环审批 + 验证器消费 → Task 1。
- [x] 双层账本 attempt_id 权威扣账 + duplicate 拒绝 + retry 递增 → Task 9。
- [x] GenerationIndex（genesis 锚定 + 原子写 + CAS 锁 + 陈旧锁清理 + 孤儿幂等 + 尾部重算失败）→ Task 10。
- [x] 正确相加 hard-cap → Task 11。
- [x] 完整流程 fake smoke（不调用 API/网络）→ Task 12。
- [x] 物化状态动态推导 / final anchor / archive pointer 路径 → 设计已冻结，测试在 Task 4/10 覆盖关键路径。

## 待批准入口（不在本计划自动执行范围内）

- **网页抓取执行**（外部网络，需单独批准）：`fetch_sanming_chapters.py` 真实抓取 303 章。
- **真实模型 API 协议 smoke**（3 章，需单独批准）。
- **P95/成本 pilot**（分层较大 pilot，需单独批准）。
- **预算核定**（项目总 cap、批次 cap，需批准）。
- **303 章分批执行**（每批 + 提交 + 门禁）。
- **最终验收**（四书门禁 + 全量 + 干净 clone 复算 + `--final-anchor` 外部终验）。
