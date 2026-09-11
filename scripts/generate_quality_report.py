"""
generate_quality_report.py
Generate a SHA-stamped quality report for classic-text distillation artifacts.

Fail-closed: returns non-zero exit code if ANY book has failed blocking gates
or missing provenance. The report is written atomically and includes the
validator code SHA and input artifact SHAs for reproducibility.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "knowledge_base" / "classic_texts"

BOOKS = {
    "ditiansui": "滴天髓",
    "zipingzhenquan": "子平真诠",
    "qiongtongbaojian": "穷通宝鉴",
    "sanmingtonghui": "三命通会",
}

sys.path.insert(0, str(ROOT))
val_mod = importlib.import_module("scripts.validate_classic_distillation")
from scripts.classic_artifacts import (  # noqa: E402
    recompute_artifact_manifest_sha256,
    recompute_validator_code_sha256,
    validate_provenance,
    verify_approval_receipt,
    verify_exemption_request,
)
from scripts.generate_classic_historical_freeze import (  # noqa: E402
    BOOKS as FREEZE_BOOKS,
    KINDS,
    CheckError,
    _book_rel,
    _canonical,
    _loads_strict,
    _parse_records,
    _record_entry,
    check_freeze_bytes,
    evidence_static_check,
)
from scripts.verify_sanming_source_chain import verify_source_chain  # noqa: E402

SCRIPTS_DIR = ROOT / "scripts"



# ---------------------------------------------------------------------------
# §10-⑦ B3：历史 provenance 豁免链消费（设计 §5/§7）
# ---------------------------------------------------------------------------
BASELINE_COMMIT = "c5cff699fdb547bd9270acbebe1f485380848751"
FREEZE_REL = "docs/superpowers/specs/2026-09-02-classic-texts-historical-record-freeze.json"
EVIDENCE_REL = "docs/superpowers/specs/2026-09-02-classic-texts-historical-generation-evidence.json"
GENERATOR_REL = "scripts/generate_classic_historical_freeze.py"
VERIFIER_REL = "scripts/verify_sanming_source_chain.py"

# §5.1 B3 常量：四书 B2 完整 SHA（冻结于四笔 B2 提交之后；报告不接受任何 CLI SHA）
APPROVAL_B2_BY_BOOK = {
    "ditiansui": "d59461c4ba4159c640bc523107af1342e8841c05",
    "qiongtongbaojian": "22e988ced5ef6411862ea81f2ca4afa9c6f11f5f",
    "sanmingtonghui": "ccb833a46977c8274c0fb8c8c79c1b2f5d494c5e",
    "zipingzhenquan": "45004f44304241018a51d755c6f88a24f536905c",
}

# §5-R 修订溯源双轨契约（设计 v29.3；批准锚点见设计 §0）
from scripts.verify_sanming_source_chain import SNAP  # noqa: E402

# 空链规范值 == GENESIS_SHA 的确定 64-hex 字面量（设计 5-R.6 首批路径要求
# REVISION_ANCHOR_HEAD@HEAD == genesis_sha）。P0-2 复审：不得用裸名
# GENESIS_SHA 初始化——fixture 替换器只接受 `NAME = "<64位hex>"` 形态，
# 首次 R/V 常量替换才能命中；两行不得带行尾注释（保持替换器正则
# `^NAME = "[0-9a-f]{64}"$` 精确匹配）；字面量由 Task 3 Step 1 的
# test_trust_roots_start_at_genesis 重算验证。
REVISION_ANCHOR_HEAD = "da56658f061d2487877ef7819a18ef548fdb4eff5aa546609abe3a64141c48c0"
TOOLCHAIN_REGISTRY_HEAD = "da56658f061d2487877ef7819a18ef548fdb4eff5aa546609abe3a64141c48c0"
REVISION_ANCHOR_REL = ("docs/superpowers/plans/notes/approvals/revisions/"
                       "sanmingtonghui/accepted_anchors.jsonl")
REVISION_REGISTRY_REL = ("docs/superpowers/plans/notes/approvals/revisions/"
                         "sanmingtonghui/toolchain_registry.jsonl")
FIRST_BATCH_BASELINE = "03c02bb571dec9e2da1f7d503a292da229415d8f"
REVISION_MANIFEST_REL = ("knowledge_base/classic_texts/sanmingtonghui/"
                         "revision_manifest.json")
REVISION_ALLOWED_RED_ITEMS = {  # 允许红项上界（附录 A.3；仅 sanmingtonghui.G7）
    "sanmingtonghui": {"G7_chapter_complete.missing_count": 303},
}


_POINTER_FIELDS = frozenset({
    "schema_version", "baseline_commit", "book", "b1_commit",
    "e_path", "e_sha256", "r_path", "r_sha256",
})


def _approvals_rel(book: str, kind: str) -> str:
    return (f"docs/superpowers/plans/notes/approvals/"
            f"2026-09-02-classic-texts-provenance-exemption-{book}-{kind}")


def _git(root: Path, *args: str) -> bytes:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.decode(errors='replace')}")
    return r.stdout


def _git_rev_parse(root: Path, rev: str) -> str:
    return _git(root, "rev-parse", rev).decode().strip()


def _git_show_blob(root: Path, rev: str, rel: str) -> bytes:
    return _git(root, "show", f"{rev}:{rel}")


def _git_head_blob(root: Path, rel: str) -> bytes:
    return _git_show_blob(root, "HEAD", rel)


def _is_ancestor(root: Path, a: str, b: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", a, b],
        capture_output=True,
    ).returncode == 0


def validate_approval_b2_constant(git_root, constant=None) -> None:
    """§5.1 B3 常量验证：键集合 == 四书精确集（缺书/多书拒绝）；值匹配
    ^[0-9a-f]{40}$（占位符/全零拒绝）；四值互异；HEAD 是每个 B2 的后代。
    任一违反 → ValueError（报告 fail-closed）。"""
    c = dict(constant) if constant is not None else dict(APPROVAL_B2_BY_BOOK)
    if set(c) != set(FREEZE_BOOKS):
        raise ValueError(f"APPROVAL_B2_BY_BOOK keys must be exactly {sorted(FREEZE_BOOKS)}")
    for k, v in c.items():
        if not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{40}", v) or v == "0" * 40:
            raise ValueError(f"APPROVAL_B2_BY_BOOK[{k!r}] must be a non-zero 40-hex SHA")
    if len(set(c.values())) != len(c):
        raise ValueError("APPROVAL_B2_BY_BOOK values must be mutually distinct")
    if git_root is not None:
        head = _git_rev_parse(git_root, "HEAD")
        for book, b2 in c.items():
            if not _is_ancestor(git_root, b2, head):
                raise ValueError(f"HEAD is not a descendant of B2 for {book}: {b2}")


def _e0_static_check(git_root: Path) -> dict:
    """§5-E0 三步静态校验（每次正式报告重算；优先级短路：生成器身份 →
    frozen_at_commit → freeze 结构 → evidence 静态；单输入单错误码）。"""
    try:
        freeze_blob = _git_head_blob(git_root, FREEZE_REL)
    except RuntimeError:
        return {"ok": False, "error_code": "FREEZE_STATIC_MISMATCH"}
    try:
        evidence_blob = _git_head_blob(git_root, EVIDENCE_REL)
    except RuntimeError:
        return {"ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}
    try:
        freeze = _loads_strict(freeze_blob.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, CheckError):
        return {"ok": False, "error_code": "FREEZE_STATIC_MISMATCH"}
    if not isinstance(freeze, dict):
        return {"ok": False, "error_code": "FREEZE_STATIC_MISMATCH"}
    try:
        evidence = _loads_strict(evidence_blob.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, CheckError):
        return {"ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}
    if not isinstance(evidence, dict):
        return {"ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}
    # ① 生成器身份六向全等（错 → GENERATOR_IDENTITY_MISMATCH，最优先）
    try:
        gen_oid_head = _git_rev_parse(git_root, f"HEAD:{GENERATOR_REL}")
        gen_sha_head = hashlib.sha256(
            _git_show_blob(git_root, "HEAD", GENERATOR_REL)).hexdigest()
        gen_file = git_root / GENERATOR_REL
        gen_oid_worktree = _git(git_root, "hash-object", str(gen_file)).decode().strip()
        gen_sha_worktree = hashlib.sha256(gen_file.read_bytes()).hexdigest()
    except (RuntimeError, OSError):
        return {"ok": False, "error_code": "GENERATOR_IDENTITY_MISMATCH"}
    if not (
        freeze.get("generator_blob_oid") == evidence.get("generator_blob_oid")
        == gen_oid_head == gen_oid_worktree
        and evidence.get("generator_sha256") == gen_sha_head == gen_sha_worktree
    ):
        return {"ok": False, "error_code": "GENERATOR_IDENTITY_MISMATCH"}
    # ② 对 HEAD blob 执行 freeze 全等重算（基点错优先于结构错）
    try:
        check_freeze_bytes(freeze_blob, git_root, expected_generator_blob_oid=gen_oid_worktree)
    except CheckError as e:
        return {"ok": False, "error_code": e.code}
    # ③ 对 HEAD blob 执行 evidence_static_check
    try:
        ver_oid = _git_rev_parse(git_root, f"HEAD:{VERIFIER_REL}")
        ver_sha = hashlib.sha256(_git_show_blob(git_root, "HEAD", VERIFIER_REL)).hexdigest()
        evidence_static_check(
            evidence, freeze, git_root,
            expected_generator_blob_oid=gen_oid_head,
            expected_generator_sha256=gen_sha_head,
            expected_verifier_blob_oid=ver_oid,
            expected_verifier_sha256=ver_sha,
        )
    except CheckError as e:
        return {"ok": False, "error_code": e.code}
    except (RuntimeError, OSError):
        return {"ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}
    return {"ok": True, "error_code": None}


def _e1_artifact_chain(git_root: Path, book: str, freeze: dict, evidence: dict) -> dict:
    """§5-E1 工件链 (a)–(j)；(j) 六方 baseline 最后执行；成功时附带 E/R 对象
    供 E2 权威重算消费。"""
    def _fail():
        return {"ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}

    if book not in APPROVAL_B2_BY_BOOK:
        return _fail()
    try:
        validate_approval_b2_constant(git_root)
    except (ValueError, RuntimeError):
        return _fail()
    b2 = APPROVAL_B2_BY_BOOK[book]
    ptr_rel = _approvals_rel(book, "b2-pointer.json")
    e_rel = _approvals_rel(book, "request.json")
    r_rel = _approvals_rel(book, "receipt.json")
    try:  # (a) B2 树指针字节 == 当前 HEAD 指针 blob
        ptr_b2 = _git_show_blob(git_root, b2, ptr_rel)
        ptr_head = _git_head_blob(git_root, ptr_rel)
    except RuntimeError:
        return _fail()
    if ptr_b2 != ptr_head:
        return _fail()
    try:
        ptr = _loads_strict(ptr_b2.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, CheckError):
        return _fail()
    # (b) 指针自身校验：精确 8 字段 + book 三方一致 + 规范路径逐字相等
    if (not isinstance(ptr, dict) or set(ptr) != _POINTER_FIELDS
            or ptr["schema_version"] != "1.0" or ptr["book"] != book
            or ptr["e_path"] != e_rel or ptr["r_path"] != r_rel):
        return _fail()
    b1 = ptr["b1_commit"]
    try:
        e_blob = _git_show_blob(git_root, b1, e_rel)
        r_blob = _git_show_blob(git_root, b1, r_rel)
        e_obj = _loads_strict(e_blob.decode("utf-8"))
        r_obj = _loads_strict(r_blob.decode("utf-8"))
    except (RuntimeError, json.JSONDecodeError, UnicodeDecodeError, CheckError):
        return _fail()
    if not isinstance(e_obj, dict) or e_obj.get("book") != book:
        return _fail()
    # (g) E/R 通过 v2.0 校验（canonical E sha 绑定由 verify_approval_receipt 复核）
    if e_obj.get("schema_version") != "2.0":
        return _fail()
    try:
        verify_exemption_request(e_obj)
        verify_approval_receipt(r_obj, e_obj)
    except ValueError:
        return _fail()
    try:
        b1_parent = _git_rev_parse(git_root, f"{b1}^")
        b2_parents = _git(git_root, "rev-list", "--parents", "-n", "1", b2).decode().split()
        b1_diff = sorted(
            _git(git_root, "diff-tree", "--no-commit-id", "--name-only", "-r", b1)
            .decode().splitlines())
        b2_diff = sorted(
            _git(git_root, "diff-tree", "--no-commit-id", "--name-only", "-r", b2)
            .decode().splitlines())
    except RuntimeError:
        return _fail()
    # (c) parent_commit 三方一致（E == R == B1 实际父提交）
    if e_obj.get("parent_commit") != b1_parent or r_obj.get("parent_commit") != b1_parent:
        return _fail()
    # (d) B2 的唯一父提交 == pointer.b1_commit
    if len(b2_parents) != 2 or b2_parents[1] != b1:
        return _fail()
    # (e) B1/B2 相对父提交的 diff 文件集恰为该书规范路径
    if b1_diff != sorted([e_rel, r_rel]) or b2_diff != [ptr_rel]:
        return _fail()
    # (f) E/R 文件字节 sha256 == 指针 e_sha256/r_sha256
    if (hashlib.sha256(e_blob).hexdigest() != ptr["e_sha256"]
            or hashlib.sha256(r_blob).hexdigest() != ptr["r_sha256"]):
        return _fail()
    # (h) 祖先链 BASE → B1 → B2
    if not (_is_ancestor(git_root, BASELINE_COMMIT, b1) and _is_ancestor(git_root, b1, b2)):
        return _fail()
    # (i) E 登记的冻结集/证据 SHA == B2 树与 HEAD 树 blob 字节 sha256（双树一致）
    for reg, rel in ((e_obj.get("historical_record_freeze_sha256"), FREEZE_REL),
                     (e_obj.get("historical_generation_evidence_sha256"), EVIDENCE_REL)):
        try:
            b2_sha = hashlib.sha256(_git_show_blob(git_root, b2, rel)).hexdigest()
            head_sha = hashlib.sha256(_git_head_blob(git_root, rel)).hexdigest()
        except RuntimeError:
            return _fail()
        if reg != b2_sha or reg != head_sha:
            return _fail()
    # (j) baseline 六方一致（最后执行）
    six = (ptr["baseline_commit"], e_obj.get("baseline_commit"),
           r_obj.get("baseline_commit"), freeze.get("frozen_at_commit"),
           evidence.get("frozen_at_commit"), BASELINE_COMMIT)
    if len(set(six)) != 1:
        return {"ok": False, "error_code": "BASELINE_COMMIT_MISMATCH"}
    return {"ok": True, "error_code": None, "e_obj": e_obj, "r_obj": r_obj}


def _e2_recompute(git_root: Path, book: str, e_obj: dict, r_obj: dict) -> dict:
    """§5-E2 权威重算（E/R 不得自证）：Git 对象重算与 E/R 三方全等。"""
    try:
        man = recompute_artifact_manifest_sha256(git_root, BASELINE_COMMIT, book)
        val = recompute_validator_code_sha256(git_root, BASELINE_COMMIT)
    except Exception:
        return {"ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}
    if (e_obj.get("artifact_manifest_sha256") != man
            or r_obj.get("artifact_manifest_sha256") != man
            or e_obj.get("validator_code_sha256") != val
            or r_obj.get("validator_code_sha256") != val):
        return {"ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}
    return {"ok": True, "error_code": None}


def _git_show_optional(git_root: Path, rel: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(git_root), "show", f"HEAD:{rel}"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def _git_show_optional_at(git_root: Path, rev: str, rel: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(git_root), "show", f"{rev}:{rel}"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def _git_rev_parse_optional(git_root: Path, rev: str) -> str | None:
    r = subprocess.run(["git", "-C", str(git_root), "rev-parse", rev],
                       capture_output=True)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def _rail_manifest_bytes(git_root: Path) -> bytes | None:
    return _git_show_optional(git_root, REVISION_MANIFEST_REL)


def _rail_anchor_entries(git_root: Path) -> list[dict] | None:
    """@HEAD 锚文件条目；文件不存在 → None；存在（含零行）→ 条目列表。"""
    from scripts.classic_artifacts import RevisionArtifactError, parse_jsonl_line
    raw = _git_show_optional(git_root, REVISION_ANCHOR_REL)
    if raw is None:
        return None
    entries = []
    for line in raw.splitlines(keepends=True):
        if not line.strip():
            raise RevisionArtifactError("blank anchor line")
        entries.append(parse_jsonl_line(line))
    return entries


def evaluate_revision_rail(git_root: Path, book: str,
                           freeze: dict, evidence: dict, *,
                           candidate_batch_id: str | None = None) -> dict:
    """§5-R.5 唯一执行入口：①-⑦ 管线，顺序即错误优先级，单次读取 HEAD。

    返回 {ok, revision_state, error_code, e3_ok, partition_detail?}。
    无 manifest 且无锚 → NONE（沿现行 E3 语义，⑤ 退化为 HEAD==freeze）。
    """
    from scripts.classic_artifacts import (
        GENESIS_SHA, RevisionArtifactError, chain_head,
        validate_revision_manifest)

    def _fail(code: str, **extra) -> dict:
        return {"ok": False, "revision_state": "FAILED", "error_code": code,
                "e3_ok": False, **extra}

    raw = None
    if book == "sanmingtonghui":
        raw = _rail_manifest_bytes(git_root)
    elif _git_show_optional(
            git_root,
            f"knowledge_base/classic_texts/{book}/revision_manifest.json"
            ) is not None:
        return _fail("REVISION_SOURCE_UNVERIFIABLE")

    if raw is None:
        # 执行复审 P0：锚文件与信任根常量仅属三命通会——其他书只做本书
        # 历史分区校验（合法 NONE），不读三命通会锚、不套用其常量规则。
        anchors = None
        if book == "sanmingtonghui":
            try:
                anchors = _rail_anchor_entries(git_root)
            except RevisionArtifactError:
                # 执行复审 P0-3：锚文件畸形行 → 稳定错误码，不抛未处理异常
                return _fail("REVISION_CHAIN_STALE")
            if anchors:  # manifest 抹除但锚存在 → 已验收修订被整体移除
                return _fail("REVISION_CHAIN_STALE")
        e3 = _partition_equation(git_root, book, freeze, manifest_recs=[])
        if not e3["ok"]:
            return _fail("REVISION_PARTITION_MISMATCH",
                         partition_detail=e3["detail"])
        # 执行复审 P0-2：缺失（None）与空（[]）同样必须核对信任根
        if (book == "sanmingtonghui" and not anchors
                and chain_head([], GENESIS_SHA) != REVISION_ANCHOR_HEAD):
            return _fail("REVISION_CHAIN_STALE")
        return {"ok": True, "revision_state": "NONE", "error_code": None,
                "e3_ok": True}

    # ① 解析（strict JSON；BOM/尾随内容拒绝）
    try:
        obj = _loads_strict(raw.decode("utf-8"))
    except Exception:
        return _fail("REVISION_MANIFEST_MALFORMED")
    # ② schema/记录身份/与 freeze 交集
    try:
        validate_revision_manifest(obj)
    except RevisionArtifactError:
        return _fail("REVISION_MANIFEST_MALFORMED")
    freeze_ids = set(_freeze_identities(freeze, book))
    for b in obj["batches"]:
        for r in b["records"]:
            if (r["id"], r["sha256"]) in freeze_ids:
                return _fail("REVISION_MANIFEST_MALFORMED",
                             reason="record double-listed with freeze")
    # ③ 锚链（执行复审 P1：锚解析在阶段①②之后，双重损坏按①报告；
    # 逐条链哈希 + 链头==常量@HEAD）
    try:
        anchors = _rail_anchor_entries(git_root)
    except RevisionArtifactError:
        return _fail("REVISION_CHAIN_STALE")
    try:
        head = chain_head(anchors or [], GENESIS_SHA)
    except RevisionArtifactError:
        return _fail("REVISION_CHAIN_STALE")
    if head != REVISION_ANCHOR_HEAD:
        return _fail("REVISION_CHAIN_STALE")
    # ④ HEAD manifest vs 已验收基线（默认/候选模式）
    if candidate_batch_id is not None:
        drift = _candidate_compare(git_root, obj, anchors or [],
                                   candidate_batch_id)
    else:
        drift = _baseline_compare(git_root, obj, anchors or [])
    if drift is not None:
        return _fail(drift)
    # ⑤ 分区等式（全 KINDS；Counter 计数，禁 set）
    manifest_recs = [r for b in obj["batches"] for r in b["records"]]
    e3 = _partition_equation(git_root, book, freeze, manifest_recs)
    if not e3["ok"]:
        return _fail("REVISION_PARTITION_MISMATCH", partition_detail=e3["detail"])
    # ⑥⑦ 源身份 + 内容检查（Task 4 实现；本任务接线占位通过）
    src = _source_identity_and_content(git_root, book, evidence, manifest_recs)
    if src is not None:
        return _fail(src)
    state = "PENDING_ACCEPTANCE" if candidate_batch_id is not None else "ACCEPTED"
    return {"ok": True, "revision_state": state, "error_code": None,
            "e3_ok": True}


def _freeze_identities(freeze: dict, book: str) -> list[tuple[str, str]]:
    return [(rec["id"], rec["sha256"])
            for kind in KINDS
            for rec in freeze["books"][book][kind]["records"]]


def _partition_equation(git_root: Path, book: str, freeze: dict,
                        manifest_recs: list[dict]) -> dict:
    """⑤ Counter(HEAD) == Counter(freeze) + Counter(manifest)（全 KINDS）。

    三分类明细：legacy_mutated / unmanifested_extra / manifest_orphan。
    manifest_recs 为空时退化为现行 E3（HEAD == freeze）。
    """
    from collections import Counter
    kind_map = {"rule": "all_rules", "mcq": "all_mcq"}
    head_c, base_c, mani_c = Counter(), Counter(), Counter()
    for kind in KINDS:
        rel = _book_rel(book, kind)
        # 执行复审 P0-1：缺席 KIND 的 baseline Counter 为空而非忽略 HEAD——
        # freeze 无记录但 HEAD 新增文件仍须被检出（unmanifested_extra）。
        for rec in freeze["books"][book][kind]["records"]:
            base_c[(kind, rec["id"], rec["sha256"])] += 1
        data = _git_show_optional(git_root, rel)  # 文件缺失 → None → 空记录
        if data is None:
            continue
        try:
            # JSON 数组（all_rules.json）与 JSONL（*_mcq.jsonl 等）经
            # _parse_records 按扩展名分派；_loads_strict 直读 JSONL 会失败。
            records = _parse_records(data, kind)
        except Exception:
            return {"ok": False, "detail": {"parse_error": rel}}
        for rec in records:
            e = _record_entry(rec)
            head_c[(kind, e["id"], e["sha256"])] += 1
    for r in manifest_recs:
        mani_c[(kind_map[r["kind"]], r["id"], r["sha256"])] += 1
    if head_c == base_c + mani_c:
        return {"ok": True, "detail": {}}
    expected = base_c + mani_c
    detail = {"legacy_mutated": 0, "unmanifested_extra": 0, "manifest_orphan": 0}
    for key in set(head_c) | set(expected):
        h, e = head_c.get(key, 0), expected.get(key, 0)
        b, m = base_c.get(key, 0), mani_c.get(key, 0)
        if h > e:
            detail["unmanifested_extra"] += h - e
        elif h < e:
            missing = e - h
            from_base = min(b, missing)
            detail["legacy_mutated"] += from_base
            detail["manifest_orphan"] += missing - from_base
    return {"ok": False, "detail": detail}


def _baseline_compare(git_root: Path, head_manifest: dict,
                      anchors: list[dict]) -> str | None:
    """④ 默认模式（canonical 层比较）。返回错误码或 None（通过）。

    - 锚空 → 基线 = 空基线 manifest 字面量；
    - HEAD == 基线 → 通过；HEAD == 基线+1 全新批次 → UNACCEPTED；
    - HEAD 批次集 ⊂ 基线（删批）→ CHAIN_STALE；其余 → HISTORY_DRIFT。
    """
    from scripts.classic_artifacts import EMPTY_BASELINE_MANIFEST
    if anchors:
        c_oid = anchors[-1]["content_commit"]
        r = subprocess.run(["git", "-C", str(git_root), "show",
                            f"{c_oid}:{REVISION_MANIFEST_REL}"],
                           capture_output=True)
        if r.returncode != 0:
            return "REVISION_CHAIN_STALE"
        base = _loads_strict(r.stdout.decode("utf-8"))
    else:
        base = EMPTY_BASELINE_MANIFEST
    hb, bb = head_manifest["batches"], base["batches"]
    if _canonical(hb) == _canonical(bb):
        return None
    if (len(hb) == len(bb) + 1
            and _canonical(hb[:len(bb)]) == _canonical(bb)
            and hb[-1]["batch_id"] not in {b["batch_id"] for b in bb}):
        return "REVISION_UNACCEPTED"
    if {b["batch_id"] for b in hb} < {b["batch_id"] for b in bb}:
        return "REVISION_CHAIN_STALE"
    return "REVISION_HISTORY_DRIFT"


_WS_RE = re.compile(r"\s+")


def _find_head_record(git_root: Path, book: str, rec: dict) -> dict | None:
    """按 (id, sha256) 在 HEAD 对应聚合中找回完整记录 dict（聚合缺失 → None）。"""
    kind_map = {"rule": "all_rules", "mcq": "all_mcq"}
    kind = kind_map[rec["kind"]]
    data = _git_show_optional_at(git_root, "HEAD", _book_rel(book, kind))
    if data is None:
        return None
    try:
        arr = _parse_records(data, kind)
    except Exception:
        return None
    for r in arr:
        e = _record_entry(r)
        if e["id"] == rec["id"] and e["sha256"] == rec["sha256"]:
            return r
    return None


def _source_identity_and_content(git_root: Path, book: str, evidence: dict,
                                 manifest_recs: list[dict]) -> str | None:
    """⑥⑦ 源身份锚定链 + 内容检查（设计 5-R.8）。返回错误码或 None。

    ⑥ 锚点来自 evidence@HEAD.source_chain.{book}（E1 已验证双树一致）：
       ⑥-1 rev-parse HEAD:<SNAP>/source_manifest.json == manifest_blob_oid
       ⑥-2 sha256(blob 原始字节) == manifest_file_sha256
       逐章：sha256(HEAD:<SNAP>/extracted/raw_{NNN}.txt) ==
             source_manifest.chapters[NNN-1].extracted_text_sha256
       （任一源文件缺失/畸形 → REVISION_SOURCE_UNVERIFIABLE，异常不冒泡）
    historical_basis（恢复类记录，设计 5-R.2）：从 git show <commit>:<path>
    重算，按 source_chapter 过滤后与 record_content_sha256（该历史记录
    _canonical 序列化字节 SHA-256）匹配必须恰好 1 条；不信任 match_count。
    ⑦ 每条 manifest 记录：snapshot_path 与章序一致 ∧ snapshot_sha256 ==
       对应章 blob sha；rule.original_text 去空白 ⊆ 该章文本去空白（缺失/
       非字符串/去空白为空拒绝）；mcq 外键指向 HEAD 存在规则 ∧ G8 形态
       （options 含 ABCD ∧ answer 为字符串 ∈ ABCD）。
    """
    sc = (evidence.get("source_chain") or {}).get(book)
    if not isinstance(sc, dict):
        return "REVISION_SOURCE_UNVERIFIABLE"
    sm_oid = _git_rev_parse_optional(
        git_root, f"HEAD:{SNAP}/source_manifest.json")
    if sm_oid is None or sm_oid != sc["manifest_blob_oid"]:
        return "REVISION_SOURCE_UNVERIFIABLE"
    sm_bytes = _git_show_optional_at(git_root, "HEAD",
                                     f"{SNAP}/source_manifest.json")
    if sm_bytes is None or hashlib.sha256(sm_bytes).hexdigest() != \
            sc["manifest_file_sha256"]:
        return "REVISION_SOURCE_UNVERIFIABLE"
    try:
        sm = _loads_strict(sm_bytes.decode("utf-8"))
        chapters = sm["chapters"]  # 列表序 == 章序（NNN-1 索引）
    except Exception:
        return "REVISION_SOURCE_UNVERIFIABLE"
    chap_blob: dict[str, tuple[int, bytes]] = {}
    for r in manifest_recs:
        nnn = next((i for i, c in enumerate(chapters, 1)
                    if c["title"] == r["source_chapter"]), None)
        if nnn is None:
            return "REVISION_SOURCE_UNVERIFIABLE"  # chapter_list 反解失败（错章）
        rel = f"{SNAP}/extracted/raw_{nnn:03d}.txt"
        if rel != r["snapshot_path"]:
            return "REVISION_SOURCE_UNVERIFIABLE"  # 路径与章不匹配
        if r["source_chapter"] not in chap_blob:
            blob = _git_show_optional_at(git_root, "HEAD", rel)
            if blob is None or hashlib.sha256(blob).hexdigest() != \
                    chapters[nnn - 1]["extracted_text_sha256"]:
                return "REVISION_SOURCE_UNVERIFIABLE"
            chap_blob[r["source_chapter"]] = (nnn, blob)
        _, blob = chap_blob[r["source_chapter"]]
        if hashlib.sha256(blob).hexdigest() != r["snapshot_sha256"]:
            return "REVISION_SOURCE_UNVERIFIABLE"
        hb = r.get("historical_basis")
        if hb is not None and not _historical_basis_ok(git_root, hb):
            return "REVISION_SOURCE_UNVERIFIABLE"
    # ⑦ 内容检查
    rules_data = _git_show_optional_at(git_root, "HEAD",
                                       _book_rel(book, "all_rules"))
    if rules_data is None:
        return "REVISION_SOURCE_UNVERIFIABLE"
    try:
        head_rule_ids = {_record_entry(rr)["id"] for rr in
                         _parse_records(rules_data, "all_rules")}
    except Exception:
        return "REVISION_SOURCE_UNVERIFIABLE"
    for r in manifest_recs:
        rec = _find_head_record(git_root, book, r)
        if rec is None:
            return "REVISION_SOURCE_UNVERIFIABLE"
        _, blob = chap_blob[r["source_chapter"]]
        chap_ws = _WS_RE.sub("", blob.decode("utf-8", "replace"))
        if r["kind"] == "rule":
            ot = rec.get("original_text")
            if (not isinstance(ot, str) or not _WS_RE.sub("", ot)
                    or _WS_RE.sub("", ot) not in chap_ws):
                return "REVISION_SOURCE_UNVERIFIABLE"
        else:
            if rec.get("source_rule_id") not in head_rule_ids:
                return "REVISION_SOURCE_UNVERIFIABLE"
            opts, ans = rec.get("options"), rec.get("answer")
            if (not isinstance(opts, dict) or not set("ABCD").issubset(opts)
                    or not isinstance(ans, str) or ans not in "ABCD"):
                return "REVISION_SOURCE_UNVERIFIABLE"
    return None


def _historical_basis_ok(git_root: Path, hb: dict) -> bool:
    """P0-1：消费 historical_basis（设计 5-R.2）。

    从 git show <commit>:<path> 重算：按 hb.source_chapter 过滤后，与
    record_content_sha256（该历史记录 _canonical 序列化字节 SHA-256）匹配
    的记录必须恰好 1 条。commit/path 不存在、解析失败、零/多匹配均拒绝；
    不得只信任 match_count 字段，也不得用 id 定位。
    """
    data = _git_show_optional_at(git_root, hb["commit"], hb["path"])
    if data is None:
        return False
    try:
        text = data.decode("utf-8")
        if hb["path"].endswith(".jsonl"):
            records = [_loads_strict(line)
                       for line in text.splitlines() if line.strip()]
        else:
            arr = _loads_strict(text)
            if not isinstance(arr, list):
                return False
            records = arr
    except Exception:
        return False
    n = 0
    for rec in records:
        if not isinstance(rec, dict) or \
                rec.get("source_chapter") != hb["source_chapter"]:
            continue
        if hashlib.sha256(
                _canonical(rec).encode("utf-8")).hexdigest() == \
                hb["record_content_sha256"]:
            n += 1
    return n == 1


def evaluate_provenance_admissibility(book_dir: Path, git_root: Path | None,
                                      *, candidate_batch_id: str | None = None
                                      ) -> dict:
    """§5 三态判定 + E0 静态校验 + MISSING 下的 E1/E2/E3 豁免链（阶段顺序短路）。

    不接 archive_root、不调用 source checker（§7 参数链：两条同级链）。"""
    book = book_dir.name
    provenance_f = book_dir / "provenance.json"
    if provenance_f.exists():
        prov_ok, _ = validate_provenance(book_dir, SCRIPTS_DIR, git_root=git_root)
        state = "VALID" if prov_ok else "INVALID"
    else:
        state = "MISSING"
    res = {
        "provenance_state": state,
        "E0_ok": False, "E1_ok": None, "E2_ok": None, "E3_ok": None,
        "historical_exemption_valid": False,
        "provenance_admissible": False,
        "exemption_error_code": None,
        "revision_state": None,
        "revision_provenance_valid": False,
    }
    # E0 无论 provenance_state 为何都执行（git_root 不可用 → fail-closed）
    if git_root is None:
        res["E0_ok"] = False
    else:
        e0 = _e0_static_check(git_root)
        res["E0_ok"] = e0["ok"]
        if not e0["ok"]:
            res["exemption_error_code"] = e0["error_code"]
    if state == "VALID":
        # 5-R.10：VALID × manifest 存在（任一形态）→ UNSUPPORTED_STATE——
        # VALID 书的 provenance.json 证明的是未修订内容，聚合被修订即与其
        # 断言矛盾（对现行唯一的行为修改）；不进 E1。
        if git_root is not None and _git_show_optional(
                git_root,
                f"knowledge_base/classic_texts/{book}/revision_manifest.json"
                ) is not None:
            res["exemption_error_code"] = "REVISION_UNSUPPORTED_STATE"
            return res
        # E0 失败不得改写 VALID 的 admissible=true（三态公式闭合）
        res["provenance_admissible"] = True
        return res
    if state == "INVALID":
        # 正式 provenance 失败，豁免链不被咨询
        return res
    # MISSING：historical_exemption_valid = E0 ∧ E1 ∧ E2 ∧ E3
    if not res["E0_ok"]:
        return res
    try:
        freeze = _loads_strict(_git_head_blob(git_root, FREEZE_REL).decode("utf-8"))
        evidence = _loads_strict(_git_head_blob(git_root, EVIDENCE_REL).decode("utf-8"))
    except (RuntimeError, CheckError, json.JSONDecodeError, UnicodeDecodeError):
        res["exemption_error_code"] = "EVIDENCE_STATIC_MISMATCH"
        return res
    e1 = _e1_artifact_chain(git_root, book, freeze, evidence)
    res["E1_ok"] = e1["ok"]
    if not e1["ok"]:
        res["exemption_error_code"] = e1["error_code"]
        return res
    e2 = _e2_recompute(git_root, book, e1["e_obj"], e1["r_obj"])
    res["E2_ok"] = e2["ok"]
    if not e2["ok"]:
        res["exemption_error_code"] = e2["error_code"]
        return res
    # §5-R.5：E3 已并入 rail——evaluate_provenance_admissibility 调用一次、
    # 只消费结果（rail 输出即 E3 结果）；错误码沿 exemption_error_code 透出。
    rail = evaluate_revision_rail(git_root, book, freeze, evidence,
                                  candidate_batch_id=candidate_batch_id)
    res["E3_ok"] = rail["e3_ok"]
    res["revision_state"] = rail["revision_state"]
    res["revision_provenance_valid"] = rail["revision_state"] == "ACCEPTED"
    if not rail["ok"]:
        res["exemption_error_code"] = rail["error_code"]
        return res
    res["historical_exemption_valid"] = True
    res["provenance_admissible"] = True
    return res


# ---------------------------------------------------------------------------
# §5-R.8 基线重跑引擎：REPORT_FIELD_SCHEMA（附录 A 同构机器可读表）+
# 退化比较 + 报告结构校验 + 合格基线判定 + rc 联合分类
# ---------------------------------------------------------------------------
_REPORT_GATES = (
    "G1_rule_id_unique", "G2_mcq_id_unique", "G3_schema",
    "G4_source_rule_id", "G5_traceability", "G6_answer_dist",
    "G7_chapter_complete", "G8_mcq_well_formed", "G9_content_dedup")

# §4.2 source BLOCKED reason 五值
_REPORT_BLOCKED_REASONS = {
    "verifier_identity_mismatch", "archive_root_missing", "archive_missing",
    "archive_sha_mismatch", "archive_size_mismatch",
}

REPORT_FIELD_SCHEMA = {
    "schema_version": "1.0",
    # 流程阶段字段（v29.2 P0）：退出通用退化比较，按运行模式校验（exit-4 判定承担）
    "process_stage_fields": ("revision_state", "revision_provenance_valid"),
    # 附录 A.0：随内容/运行合法变化，不参与劣化比较
    "non_gate_fields": ("generated_at", "validator_code_sha256",
                        "remediation_pass", "end_to_end_pass"),
    "top_level": [
        {"name": "status", "type": "enum",
         "values": ["PASS", "FAIL", "BLOCKED"], "candidate_accept": ["FAIL"]},
        {"name": "overall_pass", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [False]},
        {"name": "content_gates_pass", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [False]},
        {"name": "provenance_admissible_all", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [True]},
        {"name": "approval_b2_constant_valid", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [True]},
        {"name": "source_e2e_pass", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [False]},
        {"name": "validator_ran_live", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [True]},
        {"name": "revision_state", "type": "enum",
         "values": ["NONE", "ACCEPTED", "PENDING_ACCEPTANCE", "FAILED"],
         "candidate_accept": ["PENDING_ACCEPTANCE"]},
        {"name": "revision_provenance_valid", "type": "bool",
         "candidate_accept": [False]},
    ],
    "book_gates": [  # A.2：九门布尔
        {"name": g, "type": "bool", "direction": "pass_to_fail_bad"}
        for g in _REPORT_GATES
    ],
    "book_gate_details": [  # A.3：计数字段（direction/分母/上限/通过值）
        {"name": "G1_rule_id_unique.total", "type": "int", "direction": "size"},
        {"name": "G1_rule_id_unique.duplicates", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G2_mcq_id_unique.total", "type": "int", "direction": "size"},
        {"name": "G2_mcq_id_unique.duplicates", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G3_schema.bad_rules", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G3_schema.bad_mcq", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G3_schema.parse_errors", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G4_source_rule_id.total_refs", "type": "int",
         "direction": "size"},
        {"name": "G4_source_rule_id.bad", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G4_source_rule_id.ambiguous_rule_ids", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G5_traceability.total", "type": "int", "direction": "size"},
        {"name": "G5_traceability.untraceable", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G5_traceability.rate", "type": "float",
         "direction": "decrease_bad", "pass_value": 1.0},
        {"name": "G6_answer_dist.invalid_answers", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G6_answer_dist.out_of_band", "type": "list",
         "direction": "nonempty_bad", "pass_value": []},
        {"name": "G6_answer_dist.dist_pct", "type": "dist_pct_map",
         "band": [0.18, 0.32]},  # 合法域 [0,1]，通过区间冻结常量
        {"name": "G7_chapter_complete.expected", "type": "int",
         "direction": "size"},  # 规范化章节集合大小（非原始 len）
        {"name": "G7_chapter_complete.done", "type": "int",
         "direction": "decrease_bad"},
        {"name": "G7_chapter_complete.missing_count", "type": "int",
         "direction": "increase_bad", "pass_value": 0,
         "upper_bound": {"sanmingtonghui": 303}},  # §5-R.8 允许红项冻结上限
        {"name": "G7_chapter_complete.extra_count", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G8_mcq_well_formed.malformed", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G9_content_dedup.rule_text_duplicate_groups", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G9_content_dedup.rule_text_duplicate_count", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
        {"name": "G9_content_dedup.mcq_question_duplicates", "type": "int",
         "direction": "increase_bad", "pass_value": 0},
    ],
    "book_fields": [  # A.4：逐书 provenance/exemption/source 字段（复审 P0-2 纳入比较）
        {"name": "provenance_state", "type": "enum",
         "values": ["VALID", "INVALID", "MISSING"],
         "degrade_bad": "INVALID"},  # 退化为 INVALID 拒（A.4 方向列）
        {"name": "provenance_admissible", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [True]},
        {"name": "historical_exemption_valid", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [True]},
        {"name": "exemption_stages.E0_ok", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [True]},
        {"name": "exemption_stages.E1_ok", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [True]},
        {"name": "exemption_stages.E2_ok", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [True]},
        {"name": "exemption_stages.E3_ok", "type": "bool",
         "direction": "true_to_false_bad", "candidate_accept": [True]},
        {"name": "exemption_error_code", "type": "enum_or_null",
         "values": ["GENERATOR_IDENTITY_MISMATCH", "FROZEN_AT_COMMIT_MISMATCH",
                    "FREEZE_STATIC_MISMATCH", "EVIDENCE_STATIC_MISMATCH",
                    "BASELINE_COMMIT_MISMATCH"], "null_ok": True,
         "candidate_accept": [None], "null_to_non_null_bad": True},
        {"name": "source_e2e_status", "type": "enum",
         "values": ["PASS", "FAIL", "BLOCKED"],
         "candidate_accept": {"sanmingtonghui": ["PASS"], "*": ["FAIL"]},
         "degrade_from": "PASS", "degrade_to": ["FAIL", "BLOCKED"]},
        {"name": "source_blocked_reason", "type": "enum_or_null",
         "values": ["archive_missing", "archive_sha_mismatch",
                    "archive_size_mismatch", "verifier_identity_mismatch",
                    "archive_root_missing"], "null_ok": True,
         "candidate_accept": [None], "null_to_non_null_bad": True},
    ],
}


_MISSING = object()  # 哨兵：区分"字段缺失"与"值为 None"（P0-2）


def _spec_type_ok(spec: dict, v) -> bool:
    """按 schema 类型列校验值（P0-2 类型/语义校验；A.0：同名字段改类型拒）。"""
    t = spec["type"]
    if t == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "bool":
        return isinstance(v, bool)
    if t == "float":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "list":
        return isinstance(v, list)
    if t == "enum":
        return v in spec["values"]
    if t == "enum_or_null":
        return v is None or v in spec["values"]
    if t == "dist_pct_map":
        return isinstance(v, dict)
    return True


def _book_field_value(entry: dict, dotted: str):
    """嵌套取值：'exemption_stages.E0_ok' → entry['exemption_stages']['E0_ok']；
    缺路径返回 _MISSING。"""
    cur = entry
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def compare_gate_fields(baseline: dict, candidate: dict, *,
                        mode: str) -> list[str]:
    """按 REPORT_FIELD_SCHEMA 键集做 B/N 三分类退化比较（设计 5-R.8）。

    B∩N：布尔 true→false 拒、计数按 direction、列表空→非空拒；
    N−B：按 candidate_accept / upper_bound 校验（允许红项改善向下不设限、
    超上限拒绝）；B−N：一律拒绝（removed）。
    process_stage_fields 与 non_gate_fields 跳过（流程阶段字段由运行模式
    校验承担，不进通用退化比较）。返回违规清单（空 = 零退化）。
    """
    bad: list[str] = []
    skip = set(REPORT_FIELD_SCHEMA["process_stage_fields"]) | set(
        REPORT_FIELD_SCHEMA["non_gate_fields"])
    # 顶层 B∩N / B−N / N−B
    for f in REPORT_FIELD_SCHEMA["top_level"]:
        name = f["name"]
        if name in skip:
            continue
        in_b, in_n = name in baseline, name in candidate
        if in_b and not in_n:
            bad.append(f"{name}: removed")
        elif in_b and in_n:
            if not _spec_type_ok(f, candidate[name]):
                bad.append(f"{name}: type-changed")
            elif (f["type"] == "bool"
                    and f.get("direction") == "true_to_false_bad"
                    and baseline[name] is True and candidate[name] is False):
                bad.append(f"{name}: PASS->FAIL")
        elif in_n and not in_b:
            accept = f.get("candidate_accept")
            if accept is not None and candidate[name] not in accept:
                bad.append(f"{name}: new-invalid")
    # 逐书 gates / gate_details
    b_books = baseline.get("books") or {}
    n_books = candidate.get("books") or {}
    gate_names = [g["name"] for g in REPORT_FIELD_SCHEMA["book_gates"]]
    for book, b_entry in b_books.items():
        n_entry = n_books.get(book)
        if n_entry is None:
            bad.append(f"{book}: removed")
            continue
        b_gates = b_entry.get("gates") or {}
        n_gates = n_entry.get("gates") or {}
        for g in gate_names:
            if g in b_gates and g not in n_gates:
                bad.append(f"{book}.{g}: removed")
            elif g not in b_gates and g in n_gates:
                # P0-2：新增布尔须严格为 True（0/"FAIL"/None 等非布尔也拒）
                if n_gates[g] is not True:
                    bad.append(f"{book}.{g}: new-invalid")
            elif g in b_gates and g in n_gates:
                if not isinstance(n_gates[g], bool):
                    # P0-2：共有门先验类型，再比较退化（0/"FAIL" 等同态绕过拒）
                    bad.append(f"{book}.{g}: type-changed")
                elif b_gates[g] is True and n_gates[g] is False:
                    bad.append(f"{book}.{g}: PASS->FAIL")
        b_det = b_entry.get("gate_details") or {}
        n_det = n_entry.get("gate_details") or {}
        for spec in REPORT_FIELD_SCHEMA["book_gate_details"]:
            fname = spec["name"]
            gate, key = fname.split(".", 1)
            b_g = b_det.get(gate) if isinstance(b_det, dict) else None
            n_g = n_det.get(gate) if isinstance(n_det, dict) else None
            bv = b_g.get(key) if isinstance(b_g, dict) and key in b_g else _MISSING
            nv = n_g.get(key) if isinstance(n_g, dict) and key in n_g else _MISSING
            if bv is _MISSING and nv is _MISSING:
                continue
            if bv is not _MISSING and nv is _MISSING:
                bad.append(f"{book}.{fname}: removed")
                continue
            if bv is _MISSING and nv is not _MISSING:
                if not _spec_type_ok(spec, nv):
                    bad.append(f"{book}.{fname}: type-changed")
                else:
                    cap = (spec.get("upper_bound") or {}).get(book)
                    if cap is not None:
                        if nv > cap:
                            bad.append(f"{book}.{fname}: {nv}>{cap}")
                    elif "pass_value" in spec and nv != spec["pass_value"]:
                        # P0-1：新增错误计数须满足通过值（允许红项字段无此约束）
                        bad.append(f"{book}.{fname}: new-invalid")
                continue
            if not _spec_type_ok(spec, nv):
                bad.append(f"{book}.{fname}: type-changed")
                continue
            if spec.get("direction") in ("size", None) \
                    or spec["type"] == "dist_pct_map":
                continue
            if spec["type"] == "int":
                cap = (spec.get("upper_bound") or {}).get(book)
                if cap is not None:
                    # P0-1：允许红项须同时满足冻结上限与"不高于基线"
                    if nv > cap:
                        bad.append(f"{book}.{fname}: {nv}>{cap}")
                    elif nv > bv:
                        bad.append(f"{book}.{fname}: {nv}>{bv}")
                elif spec.get("direction") == "increase_bad" and nv > bv:
                    bad.append(f"{book}.{fname}: {nv}>{bv}")
                elif spec.get("direction") == "decrease_bad" and nv < bv:
                    bad.append(f"{book}.{fname}: {nv}<{bv}")
            elif spec["type"] == "float":
                if spec.get("direction") == "decrease_bad" and nv < bv:
                    bad.append(f"{book}.{fname}: {nv}<{bv}")
            elif spec["type"] == "list":
                if not bv and nv:
                    bad.append(f"{book}.{fname}: empty->nonempty")
        # A.4 逐书 provenance/exemption/source 字段（复审 P0-2）
        for spec in REPORT_FIELD_SCHEMA["book_fields"]:
            name = spec["name"]
            bv = _book_field_value(b_entry, name)
            nv = _book_field_value(n_entry, name)
            if bv is _MISSING and nv is _MISSING:
                continue
            if bv is not _MISSING and nv is _MISSING:
                bad.append(f"{book}.{name}: removed")
                continue
            if bv is _MISSING and nv is not _MISSING:
                accept = spec.get("candidate_accept")
                if isinstance(accept, dict):
                    accept = accept.get(book, accept.get("*"))
                if not _spec_type_ok(spec, nv):
                    bad.append(f"{book}.{name}: type-changed")
                elif accept is not None and nv not in accept:
                    bad.append(f"{book}.{name}: new-invalid")
                continue
            if not _spec_type_ok(spec, nv):
                bad.append(f"{book}.{name}: type-changed")
            elif spec.get("null_to_non_null_bad") \
                    and bv is None and nv is not None:
                bad.append(f"{book}.{name}: null->non-null")
            elif (spec.get("degrade_bad") is not None
                    and bv != spec["degrade_bad"] and nv == spec["degrade_bad"]):
                bad.append(f"{book}.{name}: {bv}->{nv}")
            elif (spec.get("degrade_from")
                    and bv == spec["degrade_from"]
                    and nv in (spec.get("degrade_to") or ())):
                bad.append(f"{book}.{name}: {bv}->{nv}")
            elif spec["type"] == "bool" and bv is True and nv is False:
                bad.append(f"{book}.{name}: PASS->FAIL")
    return bad


def _gate_consistent(gates: dict, gate_details: dict) -> bool:
    """P0-4：gates 布尔与 gate_details 推导一致（A.3 判据）；任一门不一致
    → False（明细失败却声明 PASS 不得通过）。"""
    d = gate_details

    def z(gate, *keys):
        return all((d.get(gate) or {}).get(k) == 0 for k in keys)

    checks = {
        "G1_rule_id_unique": z("G1_rule_id_unique", "duplicates"),
        "G2_mcq_id_unique": z("G2_mcq_id_unique", "duplicates"),
        "G3_schema": z("G3_schema", "bad_rules", "bad_mcq", "parse_errors"),
        "G4_source_rule_id": z("G4_source_rule_id", "bad",
                               "ambiguous_rule_ids"),
        "G5_traceability": z("G5_traceability", "untraceable"),
        "G6_answer_dist": ((d.get("G6_answer_dist") or {}).get("out_of_band") == []
                           and z("G6_answer_dist", "invalid_answers")),
        "G7_chapter_complete": (
            "missing_count" not in (d.get("G7_chapter_complete") or {})
            or z("G7_chapter_complete", "missing_count", "extra_count")),
        "G8_mcq_well_formed": z("G8_mcq_well_formed", "malformed"),
        "G9_content_dedup": z("G9_content_dedup",
                              "rule_text_duplicate_groups",
                              "rule_text_duplicate_count",
                              "mcq_question_duplicates"),
    }
    return all(gates.get(g) == derived for g, derived in checks.items())


def _qualified_baseline_report(rc: int, report: dict, *,
                               first_batch: bool) -> bool:
    """设计 5-R.8 合格基线判据（只接收 rc∈{0,1}；rc==3 由
    _classify_baseline_rc 先行联合分类；复审 P0-3：统一先验报告结构再验策略）。

    先验 _report_structure_ok（表单/类型/聚合一致），再依次：
    ① 非首批须 revision_state==ACCEPTED ∧ revision_provenance_valid==true
      （两者齐备；首批例外：缺失不判不合格）；
    ② 逐书 E0/E1/E2 全 true；③ approval_b2_constant_valid；④
      validator_ran_live ∧ 逐书九门 gates/gate_details 键集齐备 ∧ 布尔与
      明细推导一致（_gate_consistent）；
    ⑤ source 政策（A.4 候选可接纳值）：sanmingtonghui source_e2e_status
      ==PASS、其余三书 ==FAIL，且逐书 source_blocked_reason 为 None；
    ⑥ 允许计数上限：逐书 gate_details 中 upper_bound 字段不得超上限
      （仅 sanmingtonghui.G7 missing_count ≤ 303）；
    rc==0 须 status==PASS ∧ overall_pass；rc==1 须 status==FAIL ∧ 失败门
      ⊆ 允许红项（仅 sanmingtonghui.G7_chapter_complete）。rc 与状态不一致
      → False。
    """
    if rc not in (0, 1) or not isinstance(report, dict):
        return False
    if not _report_structure_ok(report):
        return False
    books = report["books"]
    if not first_batch and (
            report.get("revision_state") != "ACCEPTED"
            or report.get("revision_provenance_valid") is not True):
        return False
    if report.get("approval_b2_constant_valid") is not True:
        return False
    if report.get("validator_ran_live") is not True:
        return False
    # A.1 候选可接纳值：provenance_admissible_all 必须 true
    if report.get("provenance_admissible_all") is not True:
        return False
    for book, entry in books.items():
        gates = entry["gates"]
        details = entry["gate_details"]
        stages = entry["exemption_stages"]
        if not all(stages.get(k) is True
                   for k in ("E0_ok", "E1_ok", "E2_ok")):
            return False
        if not _gate_consistent(gates, details):
            return False
        # A.4 候选可接纳值：逐书 provenance_admissible 必须 true
        if entry["provenance_admissible"] is not True:
            return False
        # ⑤ source 政策（A.4）：sm PASS、三书 FAIL；BLOCKED 走 rc==3 路径
        expect_src = "PASS" if book == "sanmingtonghui" else "FAIL"
        if entry["source_e2e_status"] != expect_src \
                or entry["source_blocked_reason"] is not None:
            return False
        # ⑥ 允许计数上限（upper_bound 字段，仅 sm.G7 missing_count ≤ 303）
        for spec in REPORT_FIELD_SCHEMA["book_gate_details"]:
            cap = (spec.get("upper_bound") or {}).get(book)
            if cap is None:
                continue
            gate, key = spec["name"].split(".", 1)
            val = (details.get(gate) or {}).get(key)
            if val is not None and val > cap:
                return False
    if rc == 0:
        return (report.get("status") == "PASS"
                and report.get("overall_pass") is True)
    if report.get("status") != "FAIL":
        return False
    allowed = {("sanmingtonghui", "G7_chapter_complete")}
    for book, entry in books.items():
        for g, ok in (entry.get("gates") or {}).items():
            if ok is False and (book, g) not in allowed:
                return False
    return True


def _report_structure_ok(report: dict) -> bool:
    """round-5 P0 报告结构校验层（run_baseline 读完整质量报告的前置形态
    判定）。只验形态不验门禁通过——红门/红计数/红 source 不拒。键集判据以
    03c02bb 自带脚本 generate_report 重跑产出实测为准（与 HEAD 生成器同构；
    修订字段随模式在顶层出现，按"必需键齐备"而非精确键集判定）。"""
    if not isinstance(report, dict):
        return False
    top_bools = ("validator_ran_live", "remediation_pass", "end_to_end_pass",
                 "content_gates_pass", "provenance_admissible_all",
                 "approval_b2_constant_valid", "source_e2e_pass",
                 "overall_pass")
    required_top = ("generated_at", "validator", "validator_code_sha256",
                    "known_limitations", "source_e2e_status", "status",
                    "books") + top_bools
    if not set(required_top) <= set(report):
        return False
    if not isinstance(report["generated_at"], str) \
            or not isinstance(report["validator"], str) \
            or not isinstance(report["validator_code_sha256"], str) \
            or not re.fullmatch(r"[0-9a-f]{64}", report["validator_code_sha256"]) \
            or not isinstance(report["known_limitations"], list) \
            or report["source_e2e_status"] not in ("PASS", "FAIL", "BLOCKED") \
            or report["status"] not in ("PASS", "FAIL", "BLOCKED") \
            or not all(report[k] is True or report[k] is False
                       for k in top_bools):
        return False
    books = report["books"]
    if not isinstance(books, dict) or set(books) != set(FREEZE_BOOKS):
        return False
    book_bools = ("all_gates_pass", "provenance_missing", "provenance_ok",
                  "historical_exemption_valid", "provenance_admissible",
                  "end_to_end_provenance")
    for book, entry in books.items():
        required_book = ("name", "dir", "gates", "gate_details",
                         "provenance_state", "exemption_stages",
                         "exemption_error_code", "source_e2e_status",
                         "source_blocked_reason") + book_bools
        if not isinstance(entry, dict) \
                or not set(required_book) <= set(entry) \
                or not isinstance(entry["name"], str) \
                or not isinstance(entry["provenance_state"], str) \
                or entry["provenance_state"] not in ("VALID", "INVALID", "MISSING") \
                or entry["dir"] != book \
                or not all(entry[k] is True or entry[k] is False
                           for k in book_bools):
            return False
        gates = entry["gates"]
        details = entry["gate_details"]
        if (not isinstance(gates, dict) or set(gates) != set(_REPORT_GATES)
                or not all(v is True or v is False for v in gates.values())):
            return False
        if (not isinstance(details, dict)
                or set(details) != set(_REPORT_GATES)
                or not all(isinstance(v, dict) for v in details.values())):
            return False
        # P0-2：明细子键完整性/类型/取值域（按 schema A.3 逐字段校验；
        # 缺键、改类型、计数为负一律结构层拒绝，不得抛异常）
        for spec in REPORT_FIELD_SCHEMA["book_gate_details"]:
            gate, key = spec["name"].split(".", 1)
            g = details.get(gate)
            if not isinstance(g, dict):
                return False
            # G7 形态按冻结适用条件（仅 sanmingtonghui 有 chapter_list）：
            # 非 sm 书严格简化形态 {pass is True, reason=no chapter_list}
            # 且无任何计数/诊断键；sm 书必须完整计数字段（缺 expected 即拒绝，
            # 不得跳过）。
            if gate == "G7_chapter_complete" and book != "sanmingtonghui":
                if (g.get("reason") != "no chapter_list"
                        or g.get("pass") is not True
                        or any(k in g for k in ("expected", "done", "missing",
                                                "missing_count", "extra",
                                                "extra_count"))):
                    return False
                continue
            if key not in g:
                return False
            val = g[key]
            if not _spec_type_ok(spec, val):
                return False
            if spec["type"] == "int" and val < 0:
                return False
            # P0-1：比例/分布合法域（附录 A.3）——有限且 ∈ [0,1]；
            # 越 [0.18,0.32] 通过区间是质量失败（记入 out_of_band），非 schema 错误
            if spec["type"] == "float" and (not math.isfinite(val)
                                            or not (0 <= val <= 1)):
                return False
            if spec["type"] == "dist_pct_map":
                for k, v in val.items():
                    if k not in ("A", "B", "C", "D"):
                        return False
                    if (not isinstance(v, (int, float))
                            or isinstance(v, bool)
                            or not math.isfinite(v)
                            or not (0 <= v <= 1)):
                        return False
        stages = entry["exemption_stages"]
        if (not isinstance(stages, dict)
                or not all(stages.get(k) is True or stages.get(k) is False
                           for k in ("E0_ok", "E1_ok", "E2_ok", "E3_ok"))):
            return False
        ec = entry["exemption_error_code"]
        if ec is not None and not isinstance(ec, str):
            return False
        if entry["source_e2e_status"] not in ("PASS", "FAIL", "BLOCKED"):
            return False
        reason = entry["source_blocked_reason"]
        if reason is not None and reason not in _REPORT_BLOCKED_REASONS:
            return False
        # _run_source_chain_check 实测耦合：BLOCKED ⇒ reason 五值；
        # PASS/FAIL ⇒ reason is None
        if entry["source_e2e_status"] == "BLOCKED" \
                and reason not in _REPORT_BLOCKED_REASONS:
            return False
        if entry["source_e2e_status"] in ("PASS", "FAIL") and reason is not None:
            return False
    # 聚合一致性（生产 §7 实测）
    statuses = [e["source_e2e_status"] for e in books.values()]
    aggregate = ("BLOCKED" if "BLOCKED" in statuses
                 else ("FAIL" if "FAIL" in statuses else "PASS"))
    if report["source_e2e_status"] != aggregate:
        return False
    if report["source_e2e_pass"] != (aggregate == "PASS"):
        return False
    if "BLOCKED" in statuses:
        if report["status"] != "BLOCKED" or report["overall_pass"] is not False:
            return False
    else:
        expect = "PASS" if report["overall_pass"] else "FAIL"
        if report["status"] != expect:
            return False
    conj = (report["content_gates_pass"] and report["provenance_admissible_all"]
            and report["source_e2e_pass"] and report["approval_b2_constant_valid"])
    if report["overall_pass"] != conj:
        return False
    return True


def _classify_baseline_rc(rc: int, report: dict, *,
                          first_batch: bool) -> str:
    """rc × 合法报告状态联合分类（round-4 P0-1/P0-3 + round-5 P0 + 复审
    P0-3：统一先验报告结构再分派）。

    任何分支先 _report_structure_ok（表单/类型/聚合一致）→ 不过一律
    "INVALID"。rc==3：结构过 ∧ 顶层 BLOCKED ∧ overall False ∧ 存在书
    source BLOCKED 且 reason ∈ §4.2 五值 → "BLOCKED"（调用方上抛 exit 3）；
    否则 "INVALID"。rc∈{0,1}：交 _qualified_baseline_report（其内再验
    模式/source 政策/允许失败集合/计数上限）。first_batch 由调用方显式
    传入，不从报告缺字段推断。verifier CLI 三字段对象不得冒充质量报告。
    """
    if not _report_structure_ok(report):
        return "INVALID"
    if rc == 3:
        blocked_book = any(
            (e or {}).get("source_e2e_status") == "BLOCKED"
            and (e or {}).get("source_blocked_reason") in _REPORT_BLOCKED_REASONS
            for e in report["books"].values())
        if (report.get("status") == "BLOCKED"
                and report.get("source_e2e_status") == "BLOCKED"
                and report.get("overall_pass") is False
                and blocked_book):
            return "BLOCKED"
        return "INVALID"
    if rc in (0, 1):
        qualified = _qualified_baseline_report(rc, report,
                                               first_batch=first_batch)
        return "QUALIFIED" if qualified else "INVALID"
    return "INVALID"


def _run_report_in_worktree(tmp: Path, archive_root: Path) -> tuple[int, bytes]:
    """在基线 worktree 内运行报告 CLI（基线提交自带脚本；--archive-root
    必传，缺失 → sanmingtonghui source BLOCKED → exit 3）。真实 subprocess，
    返回 (rc, stdout)；测试可 monkeypatch 注入。"""
    r = subprocess.run(
        [sys.executable, "scripts/generate_quality_report.py",
         "--archive-root", str(archive_root)],
        cwd=tmp, capture_output=True)
    return r.returncode, r.stdout


def run_baseline(baseline_commit: str, git_root: Path, archive_root: Path,
                 *, first_batch: bool) -> tuple[int, dict]:
    """基线重跑引擎（设计 5-R.8）：在基线提交干净 worktree 以基线自带脚本
    重跑 QUALITY_REPORT.json，返回 (rc, report)。

    新生成守卫（P0-3）：先删基线跟踪的旧报告（删前断言存在、删后断言不
    在），运行后报告缺失即证明本次未产出 → (rc, {})（调用方判 INVALID，
    旧报告不会被误收）。基线重跑在基线提交 worktree、以基线自带脚本运行，
    不得修改历史脚本来迎合计划。"""
    tmp = Path(tempfile.mkdtemp(prefix="rail-baseline-"))
    rep_rel = "knowledge_base/classic_texts/QUALITY_REPORT.json"
    try:
        _git(git_root, "worktree", "add", "--detach", str(tmp),
             baseline_commit)
        rep_path = tmp / rep_rel
        assert rep_path.exists(), "baseline lacks tracked QUALITY_REPORT.json"
        rep_path.unlink()
        assert not rep_path.exists()
        rc, _stdout = _run_report_in_worktree(tmp, archive_root)
        if not rep_path.exists():
            return rc, {}
        report = _loads_strict(rep_path.read_text(encoding="utf-8"))
        return rc, report
    finally:
        subprocess.run(["git", "-C", str(git_root), "worktree", "remove",
                        "--force", str(tmp)], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def _run_source_chain_check(git_root: Path | None, archive_root) -> dict:
    """§7 source_chain_check 执行体（仅三命通会调用）。archive_root 缺失 →
    BLOCKED(archive_root_missing)，fail-closed；即便 provenance/E0 失败，
    本链仍由 generate_report 无条件独立执行。"""
    if archive_root is None:
        return {"status": "BLOCKED", "reason": "archive_root_missing"}
    if git_root is None:
        return {"status": "BLOCKED", "reason": "verifier_identity_mismatch"}
    out, code = verify_source_chain(
        git_root, Path(archive_root), verifier_path=git_root / VERIFIER_REL)
    if out.get("status") == "BLOCKED":
        return {"status": "BLOCKED", "reason": out.get("reason")}
    if code == 0:
        return {"status": "PASS", "reason": None}
    return {"status": "FAIL", "reason": None}


def _find_git_root(start: Path | None = None) -> Path | None:
    """Walk up from start (default: module ROOT) to find the git repository
    root (P0-4). Recognizes both normal checkouts (.git directory) and
    linked worktrees (.git file pointing at the real gitdir)."""
    p = start if start is not None else ROOT
    while p != p.parent:
        if (p / ".git").is_dir() or (p / ".git").is_file():
            return p
        p = p.parent
    return None


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(content, encoding="utf-8")
    try:
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def generate_report(
    base_path: Path | None = None,
    books: dict[str, str] | None = None,
    archive_root=None,
    *,
    candidate_batch_id: str | None = None,
) -> tuple[dict, int]:
    """Generate quality report. Returns (report_dict, exit_code).

    exit_code: 3 if any book's source_e2e_status is BLOCKED (§7 top-level
    state machine); 1 if overall_pass is false; 0 only if all books pass all
    gates AND provenance is admissible AND source e2e passes.
    """
    base = base_path or BASE
    book_map = books or BOOKS
    git_root = _find_git_root()
    # §5.1 fail-closed：B2 常量校验失败（含 git_root 缺失无法校验）→ 报告不得 PASS
    approval_b2_valid = False
    if git_root is not None:
        try:
            validate_approval_b2_constant(git_root)
            approval_b2_valid = True
        except (ValueError, RuntimeError):
            approval_b2_valid = False

    val_results = []
    for dir_key, name in book_map.items():
        r = val_mod.validate_book(dir_key, name, base_path=base)
        val_results.append(r)

    validator_path = ROOT / "scripts" / "validate_classic_distillation.py"
    validator_sha = _sha256_file(validator_path) if validator_path.exists() else "missing"

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "validator": "scripts/validate_classic_distillation.py",
        "validator_code_sha256": validator_sha,
        "validator_ran_live": True,
        "books": {},
        "known_limitations": [],
    }

    remediation_pass = True
    end_to_end_pass = True
    adm_by_book: dict[str, dict] = {}

    for dir_key, name in book_map.items():
        p = base / dir_key
        entry = {"name": name, "dir": dir_key}

        rules_f = p / "all_rules.json"
        mcq_f = p / "all_mcq.jsonl"
        q_rules_f = p / "quarantine_rules.jsonl"
        q_mcq_f = p / "quarantine_mcq.jsonl"
        provenance_f = p / "provenance.json"

        if rules_f.exists():
            rules = json.loads(rules_f.read_text(encoding="utf-8"))
            entry["rules"] = {"count": len(rules), "sha256": _sha256_file(rules_f)}
            cats = Counter(r.get("category", "?") for r in rules)
            entry["rules"]["categories"] = dict(cats.most_common())
        if mcq_f.exists():
            mcqs = [json.loads(l) for l in mcq_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            entry["mcq"] = {"count": len(mcqs), "sha256": _sha256_file(mcq_f)}
            ans = Counter(m.get("answer", "?") for m in mcqs)
            entry["mcq"]["answer_dist"] = dict(ans)
            valid = sum(v for k, v in ans.items() if k in "ABCD")
            entry["mcq"]["answer_pct"] = {k: round(v / max(1, valid), 4) for k, v in ans.items() if k in "ABCD"}
        if q_rules_f.exists():
            qr = [l for l in q_rules_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            entry["quarantine_rules"] = {"count": len(qr), "sha256": _sha256_file(q_rules_f)}
        else:
            entry["quarantine_rules"] = {"count": 0}
        if q_mcq_f.exists():
            qm = [l for l in q_mcq_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            entry["quarantine_mcq"] = {"count": len(qm), "sha256": _sha256_file(q_mcq_f)}
        else:
            entry["quarantine_mcq"] = {"count": 0}

        provenance_ok = False
        end_to_end_provenance = False
        prov_issues: list[str] = []
        if provenance_f.exists():
            # P0-4: pass git_root so anchor_commit existence and baseline blob
            # checks actually run.
            prov_ok, prov_issues = validate_provenance(p, SCRIPTS_DIR, git_root=git_root)
            if prov_ok:
                prov_data = json.loads(provenance_f.read_text(encoding="utf-8"))
                entry["provenance"] = prov_data
                provenance_ok = True
                upstream_status = prov_data.get("upstream_provenance_status", "unavailable")
                # P0-4: only 'recovered' (full upstream schema validated) gives
                # end_to_end_provenance=True. 'partial' and 'unavailable' both
                # mean end-to-end is not proven.
                end_to_end_provenance = (upstream_status == "recovered")
                if not end_to_end_provenance:
                    end_to_end_pass = False
                    report["known_limitations"].append(
                        f"end-to-end provenance incomplete for {name} ({dir_key}): "
                        f"upstream_provenance_status={upstream_status}"
                    )
                # Round-7 Medium: a formal quality gate must NOT treat a partial
                # API generation chain (no archived run_manifest) as a verified
                # chain. Only verification_level=='full' counts. This degrades
                # provenance_ok and forces the remediation gate to fail.
                api_gen = (prov_data.get("api_generation") or {})
                api_vlevel = api_gen.get("verification_level")
                # Round-7/P0: whenever an api_generation chain exists, require
                # verification_level to be EXACTLY 'full' for the formal quality
                # gate. A missing value (None) must also degrade -- the old
                # `is not None` guard let an omitted verification_level bypass it.
                if api_gen and api_vlevel != "full":
                    provenance_ok = False
                    entry["provenance_partial"] = True
                    entry["provenance_issues"] = entry.get("provenance_issues", []) + [
                        f"api_generation.verification_level={api_vlevel!r} is not 'full' "
                        f"(no archived run_manifest); treated as unverified"]
                    remediation_pass = False
                    end_to_end_pass = False
                    report["known_limitations"].append(
                        f"api_generation chain for {name} ({dir_key}) is only "
                        f"{api_vlevel!r}, not 'full' -- not a verified generation chain"
                    )
            else:
                entry["provenance"] = json.loads(provenance_f.read_text(encoding="utf-8"))
                entry["provenance_issues"] = prov_issues
                entry["provenance_invalid"] = True
                remediation_pass = False
                end_to_end_pass = False
        else:
            entry["provenance"] = None
            entry["provenance_missing"] = True
            remediation_pass = False
            end_to_end_pass = False

        for v in val_results:
            if v.get("dir") == dir_key:
                entry["gates"] = {k: g.get("pass") for k, g in v.get("gates", {}).items()}
                entry["all_gates_pass"] = v.get("passed", False)
                entry["gate_details"] = v.get("gates", {})
                if not v.get("passed", False):
                    remediation_pass = False
                    end_to_end_pass = False
                break

        entry["provenance_ok"] = provenance_ok
        entry["end_to_end_provenance"] = end_to_end_provenance

        # §5/§7：三态判定 + E0/E1/E2/E3 豁免链（不接 archive_root）
        adm = evaluate_provenance_admissibility(p, git_root,
                                                candidate_batch_id=candidate_batch_id)
        entry["provenance_state"] = adm["provenance_state"]
        entry["historical_exemption_valid"] = adm["historical_exemption_valid"]
        entry["provenance_admissible"] = adm["provenance_admissible"]
        entry["exemption_error_code"] = adm["exemption_error_code"]
        entry["revision_state"] = adm["revision_state"]
        entry["revision_provenance_valid"] = adm["revision_provenance_valid"]
        adm_by_book[dir_key] = adm
        entry["exemption_stages"] = {
            "E0_ok": adm["E0_ok"], "E1_ok": adm["E1_ok"],
            "E2_ok": adm["E2_ok"], "E3_ok": adm["E3_ok"],
        }
        if adm["provenance_state"] == "MISSING" and adm["historical_exemption_valid"]:
            report["known_limitations"].append(
                f"historical exemption applied for {name} ({dir_key}): "
                f"missing formal model run manifest (design §4.1)")
        # §7：source 链与 provenance 链同级，无条件独立执行（不得提前 return）
        if dir_key == "sanmingtonghui":
            src = _run_source_chain_check(git_root, archive_root)
            entry["source_e2e_status"] = src["status"]
            entry["source_blocked_reason"] = src.get("reason")
        else:
            entry["source_e2e_status"] = "FAIL"  # §8 已确认 S 口径
            entry["source_blocked_reason"] = None
            report["known_limitations"].append(
                f"source e2e not proven for {name} ({dir_key}) (S scope, design §8)")

        report["books"][dir_key] = entry

    # P0-4: split remediation_pass (gates + provenance valid) from
    # end_to_end_pass (remediation + upstream recovered). overall_pass is
    # kept for backward compatibility but is now end_to_end_pass.
    report["remediation_pass"] = remediation_pass
    report["end_to_end_pass"] = end_to_end_pass
    # §7 顶层状态机（source BLOCKED 独立且上限；豁免链静态错误仅影响 admissible 布尔）
    statuses = [e.get("source_e2e_status") for e in report["books"].values()]
    report["source_e2e_status"] = (
        "BLOCKED" if "BLOCKED" in statuses
        else ("FAIL" if "FAIL" in statuses else "PASS"))
    report["source_e2e_pass"] = report["source_e2e_status"] == "PASS"
    report["content_gates_pass"] = all(
        e.get("all_gates_pass") is True for e in report["books"].values())
    report["provenance_admissible_all"] = all(
        e.get("provenance_admissible") is True for e in report["books"].values())
    # 5-R.9/A.1：顶层修订字段从已计算的三命通会结果派生（不再次调用 rail）。
    # rail 未评（E0/E1/E2 提前失败或 VALID/INVALID 短路 → revision_state 为
    # None）时 fail-closed 写 FAILED——顶层枚举仅允许 {NONE, ACCEPTED,
    # PENDING_ACCEPTANCE, FAILED}，不得写 None。
    sm_adm = adm_by_book.get("sanmingtonghui")
    sm_state = sm_adm["revision_state"] if sm_adm is not None else None
    report["revision_state"] = sm_state if sm_state is not None else "FAILED"
    report["revision_provenance_valid"] = report["revision_state"] == "ACCEPTED"
    report["approval_b2_constant_valid"] = approval_b2_valid
    report["overall_pass"] = (
        report["content_gates_pass"]
        and report["provenance_admissible_all"]
        and report["source_e2e_pass"]
        and approval_b2_valid)
    if "BLOCKED" in statuses:
        report["status"] = "BLOCKED"
        report["overall_pass"] = False
    elif report["overall_pass"]:
        report["status"] = "PASS"
    else:
        report["status"] = "FAIL"
    if report["status"] == "BLOCKED":
        exit_code = 3
    elif report["overall_pass"]:
        exit_code = 0
    else:
        exit_code = 1
    return report, exit_code


def _registry_entries(git_root: Path) -> list[dict] | None:
    """@HEAD 登记文件逐行严格解析；文件不存在 → None。"""
    from scripts.classic_artifacts import parse_jsonl_line
    raw = _git_show_optional(git_root, REVISION_REGISTRY_REL)
    if raw is None:
        return None
    entries = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        entries.append(parse_jsonl_line(line))
    return entries


def _registry_head(git_root: Path) -> str:
    """@HEAD 登记链头（空/缺失 → chain_head([], genesis)）。"""
    from scripts.classic_artifacts import (
        GENESIS_SHA, REVISION_REGISTRY_FIELDS, chain_head)
    return chain_head(_registry_entries(git_root) or [], GENESIS_SHA,
                      prev_field="prev_registry_sha256",
                      fields=REVISION_REGISTRY_FIELDS)


def _registry_head_at(git_root: Path, rev: str) -> str:
    from scripts.classic_artifacts import (
        GENESIS_SHA, REVISION_REGISTRY_FIELDS, chain_head, parse_jsonl_line)
    raw = _git_show_optional_at(git_root, rev, REVISION_REGISTRY_REL)
    entries = []
    if raw is not None:
        for line in raw.splitlines():
            if line.strip():
                entries.append(parse_jsonl_line(line))
    return chain_head(entries, GENESIS_SHA, prev_field="prev_registry_sha256",
                      fields=REVISION_REGISTRY_FIELDS)


def _anchor_entries(git_root: Path) -> list[dict]:
    """@HEAD 锚文件条目；文件不存在/零行 → []. 畸形行上抛 RevisionArtifactError。"""
    from scripts.classic_artifacts import RevisionArtifactError, parse_jsonl_line
    raw = _git_show_optional(git_root, REVISION_ANCHOR_REL)
    entries = []
    if raw is not None:
        for line in raw.splitlines():
            if not line.strip():
                raise RevisionArtifactError("blank anchor line")
            entries.append(parse_jsonl_line(line))
    return entries


def _accepted_manifest(git_root: Path, anchors: list[dict]) -> dict:
    """已验收基线 manifest：锚空 → 空基线字面量；否则锚末 content_commit 的 manifest。"""
    from scripts.classic_artifacts import EMPTY_BASELINE_MANIFEST
    if anchors:
        c_oid = anchors[-1]["content_commit"]
        r = subprocess.run(["git", "-C", str(git_root), "show",
                            f"{c_oid}:{REVISION_MANIFEST_REL}"],
                           capture_output=True)
        if r.returncode != 0:
            raise ValueError("accepted content_commit missing")
        return _loads_strict(r.stdout.decode("utf-8"))
    return EMPTY_BASELINE_MANIFEST


def _candidate_compare(git_root: Path, head_manifest: dict,
                       anchors: list[dict], candidate_batch_id: str) -> str | None:
    """④ 候选分支（设计 5-R.6/5-R.8）：n=len(accepted.batches)，要求
    len(candidate.batches)==n+1 ∧ 前缀逐对象 canonical 相等 ∧ 新 batch_id==参数
    ∧ 全新；违者删批→CHAIN_STALE、多批→UNACCEPTED、其余→HISTORY_DRIFT。"""
    try:
        base = _accepted_manifest(git_root, anchors)
    except Exception:
        return "REVISION_CHAIN_STALE"
    hb, bb = head_manifest["batches"], base["batches"]
    n = len(bb)
    if (len(hb) == n + 1
            and _canonical(hb[:n]) == _canonical(bb)
            and hb[n]["batch_id"] == candidate_batch_id
            and hb[n]["batch_id"] not in {b["batch_id"] for b in bb}):
        return None
    if {b["batch_id"] for b in hb} < {b["batch_id"] for b in bb}:
        return "REVISION_CHAIN_STALE"
    if len(hb) > n + 1:
        return "REVISION_UNACCEPTED"
    return "REVISION_HISTORY_DRIFT"


def _extract_constant(script_bytes: bytes, name: str) -> str | None:
    m = re.search(rf'^{name} = "([0-9a-f]{{64}})"$',
                  script_bytes.decode("utf-8", "replace"), re.M)
    return m.group(1) if m else None


def _normalized_script_diff(a: bytes, b: bytes) -> tuple[bool, set[str]]:
    """5-R.11：仅 REVISION_ANCHOR_HEAD / TOOLCHAIN_REGISTRY_HEAD 两常量的
    值部分可变，其余完整原始字节（含行尾/末尾换行）必须全等。先把两侧常量
    值替换为占位符，再比较替换后的完整字节串。返回 (是否仅允许差异, 差异集)。"""
    const_re = re.compile(
        rb'^(REVISION_ANCHOR_HEAD|TOOLCHAIN_REGISTRY_HEAD) = "([0-9a-f]{64})"(?=\r?$)',
        re.M)

    def norm(blob: bytes) -> tuple[bytes, dict]:
        vals: dict[str, bytes] = {}

        def repl(m):
            vals[m.group(1).decode()] = m.group(2)
            return m.group(1) + b' = "<NORM>"'

        return const_re.sub(repl, blob), vals

    na, va = norm(a)
    nb, vb = norm(b)
    if na != nb:
        return False, set()
    diff_names = {name for name in ("REVISION_ANCHOR_HEAD",
                                    "TOOLCHAIN_REGISTRY_HEAD")
                  if va.get(name) != vb.get(name)}
    return True, diff_names


def validate_v_structure(git_root, v, *,
                         require_head_consistency: bool = True) -> str | None:
    """5-R.7 七项定点验证；任一失败返回 "REVISION_CHAIN_STALE"，全过 None。"""
    from scripts.classic_artifacts import (
        GENESIS_SHA, RevisionArtifactError, chain_head, parse_jsonl_line)
    # 1) 唯一父
    rev = _git(git_root, "rev-list", "--parents", "-n", "1", v).decode().strip().split()
    if len(rev) != 2:
        return "REVISION_CHAIN_STALE"
    parent = rev[1]
    # 2) diff 路径 == {锚文件, 脚本}
    diff = _git(git_root, "diff", "--name-only", parent, v).decode().strip()
    paths = set(diff.splitlines()) if diff else set()
    if paths != {REVISION_ANCHOR_REL, "scripts/generate_quality_report.py"}:
        return "REVISION_CHAIN_STALE"
    # 3) 锚增量：@P 行集为 @V 真前缀，新行 @V 末条
    anchor_p = _git_show_optional_at(git_root, parent, REVISION_ANCHOR_REL)
    anchor_v = _git_show_optional_at(git_root, v, REVISION_ANCHOR_REL)
    if anchor_v is None:
        return "REVISION_CHAIN_STALE"
    try:
        entries_v = [parse_jsonl_line(l) for l in anchor_v.splitlines() if l.strip()]
        entries_p = ([] if anchor_p is None else
                     [parse_jsonl_line(l) for l in anchor_p.splitlines() if l.strip()])
    except RevisionArtifactError:
        return "REVISION_CHAIN_STALE"
    p_canon = [_canonical(e).encode("utf-8") for e in entries_p]
    v_canon = [_canonical(e).encode("utf-8") for e in entries_v]
    if len(v_canon) != len(p_canon) + 1 or v_canon[:len(p_canon)] != p_canon:
        return "REVISION_CHAIN_STALE"
    new_anchor = entries_v[-1]
    # 4) 常量增量 + 链头核验
    script_p = _git_show_optional_at(git_root, parent, "scripts/generate_quality_report.py")
    script_v = _git_show_optional_at(git_root, v, "scripts/generate_quality_report.py")
    if script_p is None or script_v is None:
        return "REVISION_CHAIN_STALE"
    ok, diff_names = _normalized_script_diff(script_p, script_v)
    if not ok or diff_names != {"REVISION_ANCHOR_HEAD"}:
        return "REVISION_CHAIN_STALE"
    anchor_head_v = chain_head(entries_v, GENESIS_SHA)
    anchor_head_p = chain_head(entries_p, GENESIS_SHA)
    if _extract_constant(script_v, "REVISION_ANCHOR_HEAD") != anchor_head_v:
        return "REVISION_CHAIN_STALE"
    if _extract_constant(script_p, "REVISION_ANCHOR_HEAD") != anchor_head_p:
        return "REVISION_CHAIN_STALE"
    # 5) C 绑定
    c_oid = new_anchor["content_commit"]
    if _git_rev_parse_optional(git_root, c_oid) is None:
        return "REVISION_CHAIN_STALE"
    if not _is_ancestor(git_root, c_oid, v):
        return "REVISION_CHAIN_STALE"
    manifest_c = _git_show_optional_at(git_root, c_oid, REVISION_MANIFEST_REL)
    if manifest_c is None:
        return "REVISION_CHAIN_STALE"
    try:
        mobj = _loads_strict(manifest_c.decode("utf-8"))
    except Exception:
        return "REVISION_CHAIN_STALE"
    if hashlib.sha256(_canonical(mobj).encode("utf-8")).hexdigest() != \
            new_anchor["manifest_sha256_after"]:
        return "REVISION_CHAIN_STALE"
    # 6) P 的工具链身份
    t_v = new_anchor.get("toolchain_commit")
    if not isinstance(t_v, str):
        return "REVISION_CHAIN_STALE"
    script_t = _git_show_optional_at(git_root, t_v, "scripts/generate_quality_report.py")
    ca_p = _git_show_optional_at(git_root, parent, "scripts/classic_artifacts.py")
    ca_t = _git_show_optional_at(git_root, t_v, "scripts/classic_artifacts.py")
    if script_t is None or ca_p is None or ca_t is None:
        return "REVISION_CHAIN_STALE"
    ok2, _ = _normalized_script_diff(script_t, script_p)
    if not ok2:
        return "REVISION_CHAIN_STALE"
    if ca_t != ca_p:
        return "REVISION_CHAIN_STALE"
    if _extract_constant(script_p, "TOOLCHAIN_REGISTRY_HEAD") != \
            _registry_head_at(git_root, parent):
        return "REVISION_CHAIN_STALE"
    # 7) V 与 HEAD 状态一致：锚文件一致 + 验收头常量一致；不比整个脚本
    #（后续合法 R 只改 TOOLCHAIN_REGISTRY_HEAD，不得误拒历史 V）
    if require_head_consistency:
        if _git_show_optional_at(git_root, "HEAD", REVISION_ANCHOR_REL) != anchor_v:
            return "REVISION_CHAIN_STALE"
        script_head = _git_show_optional_at(
            git_root, "HEAD", "scripts/generate_quality_report.py")
        if script_head is None:
            return "REVISION_CHAIN_STALE"
        if (_extract_constant(script_head, "REVISION_ANCHOR_HEAD")
                != _extract_constant(script_v, "REVISION_ANCHOR_HEAD")):
            return "REVISION_CHAIN_STALE"
    return None


def _candidate_mode(git_root, batch_id, baseline_commit, toolchain_commit,
                    archive_root) -> int:
    """候选模式（5-R.6）：T 准入 → 执行来源核验 → 首批/非首批路径 → 候选门禁
    → 基线重跑/分类/退化比较 → 输出候选报告 exit 4。"""
    from scripts.classic_artifacts import (
        GENESIS_SHA, RevisionArtifactError, REVISION_REGISTRY_FIELDS,
        chain_head, parse_jsonl_line)

    def _fail1(code: str) -> int:
        print(code, file=sys.stderr)
        return 1

    # 1) T 准入
    try:
        reg_entries = _registry_entries(git_root)
        if reg_entries is None:
            return _fail1("REVISION_TOOLCHAIN_INVALID")
        reg_head = chain_head(reg_entries, GENESIS_SHA,
                              prev_field="prev_registry_sha256",
                              fields=REVISION_REGISTRY_FIELDS)
    except RevisionArtifactError:
        return _fail1("REVISION_TOOLCHAIN_INVALID")
    if reg_head != TOOLCHAIN_REGISTRY_HEAD:
        return _fail1("REVISION_TOOLCHAIN_INVALID")
    if toolchain_commit not in {e["toolchain_commit"] for e in reg_entries}:
        return _fail1("REVISION_TOOLCHAIN_INVALID")
    # 2) 执行来源核验（磁盘 == HEAD 逐字节；磁盘 vs @T 双常量规范化）
    disk = (git_root / "scripts" / "generate_quality_report.py").read_bytes()
    disk_ca = (git_root / "scripts" / "classic_artifacts.py").read_bytes()
    head_script = _git_show_optional(git_root, "scripts/generate_quality_report.py")
    head_ca = _git_show_optional(git_root, "scripts/classic_artifacts.py")
    t_script = _git_show_optional_at(git_root, toolchain_commit,
                                     "scripts/generate_quality_report.py")
    t_ca = _git_show_optional_at(git_root, toolchain_commit,
                                 "scripts/classic_artifacts.py")
    if (head_script is None or head_ca is None or t_script is None or t_ca is None):
        return _fail1("REVISION_TOOLCHAIN_INVALID")
    if disk != head_script or disk_ca != head_ca:
        return _fail1("REVISION_TOOLCHAIN_INVALID")
    ok, _ = _normalized_script_diff(t_script, disk)
    if not ok or t_ca != disk_ca:
        return _fail1("REVISION_TOOLCHAIN_INVALID")
    # 3) 首批/非首批路径判定
    try:
        anchor_entries = _anchor_entries(git_root)
    except RevisionArtifactError:
        return _fail1("REVISION_CHAIN_STALE")
    first_batch = (not anchor_entries) and (REVISION_ANCHOR_HEAD == GENESIS_SHA)
    if first_batch:
        if (baseline_commit != FIRST_BATCH_BASELINE
                or toolchain_commit != reg_entries[0]["toolchain_commit"]):
            print("REVISION_CLI_USAGE", file=sys.stderr)
            return 2
    else:
        if baseline_commit == FIRST_BATCH_BASELINE:
            print("REVISION_CLI_USAGE", file=sys.stderr)
            return 2
        if _git_rev_parse_optional(git_root, baseline_commit) is None:
            return _fail1("REVISION_BASELINE_INVALID")
        if not _is_ancestor(git_root, baseline_commit, "HEAD"):
            return _fail1("REVISION_BASELINE_INVALID")
        if validate_v_structure(git_root, baseline_commit) is not None:
            return _fail1("REVISION_BASELINE_INVALID")
    # 4) 候选门禁：rail 候选 + E0-E2 + B2 + G1-G9 实际执行
    report, report_rc = generate_report(archive_root=archive_root,
                                        candidate_batch_id=batch_id)
    sm = report.get("books", {}).get("sanmingtonghui", {})
    # 5) source BLOCKED → exit 3
    if report_rc == 3 or report.get("status") == "BLOCKED":
        reason = sm.get("source_blocked_reason") or "unknown"
        print(f"SOURCE_CHAIN_BLOCKED:{reason}", file=sys.stderr)
        return 3
    # 6) 修订链/E0-E2/B2 失败 → exit 1
    if sm.get("revision_state") != "PENDING_ACCEPTANCE":
        return _fail1(sm.get("exemption_error_code") or "REVISION_BASELINE_INVALID")
    stages = sm.get("exemption_stages") or {}
    if not all(stages.get(k) is True for k in ("E0_ok", "E1_ok", "E2_ok")):
        return _fail1(sm.get("exemption_error_code") or "REVISION_BASELINE_INVALID")
    if report.get("approval_b2_constant_valid") is not True:
        return _fail1("REVISION_BASELINE_INVALID")
    # 7) 基线重跑 + 分类 + 退化比较
    rc, base_report = run_baseline(baseline_commit, git_root, archive_root,
                                   first_batch=first_batch)
    cls = _classify_baseline_rc(rc, base_report, first_batch=first_batch)
    if cls == "BLOCKED":
        reason = None
        for e in (base_report.get("books") or {}).values():
            if e.get("source_e2e_status") == "BLOCKED":
                reason = e.get("source_blocked_reason")
        print(f"SOURCE_CHAIN_BLOCKED:{reason}", file=sys.stderr)
        return 3
    if cls == "INVALID":
        return _fail1("REVISION_BASELINE_INVALID")
    bad = compare_gate_fields(base_report, report, mode="candidate")
    if bad:
        return _fail1(bad[0])
    # 8) 输出候选报告 + exit 4
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 4


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="generate_quality_report")
    ap.add_argument("--archive-root", default=None,
                    help="archive root for the sanmingtonghui source_chain_check")
    ap.add_argument("--pending-batch", default=None)
    ap.add_argument("--baseline-commit", default=None)
    ap.add_argument("--toolchain-commit", default=None)
    a = ap.parse_args(argv)
    candidate_args = (a.pending_batch, a.baseline_commit, a.toolchain_commit)
    if any(x is not None for x in candidate_args):
        if (not all(x is not None for x in candidate_args)
                or a.archive_root is None):
            print("REVISION_CLI_USAGE", file=sys.stderr)
            return 2
        return _candidate_mode(ROOT, a.pending_batch, a.baseline_commit,
                               a.toolchain_commit, a.archive_root)
    print("Re-running validator for fresh gate results...")
    report, exit_code = generate_report(archive_root=a.archive_root)

    out = BASE / "QUALITY_REPORT.json"
    _atomic_write(out, json.dumps(report, ensure_ascii=False, indent=2))

    print(f"Quality report written to {out}")
    print(f"\n=== Summary ===")
    total_rules = 0
    total_mcq = 0
    total_q_rules = 0
    total_q_mcq = 0
    for dir_key, e in report["books"].items():
        r = e.get("rules", {}).get("count", 0)
        m = e.get("mcq", {}).get("count", 0)
        qr = e.get("quarantine_rules", {}).get("count", 0)
        qm = e.get("quarantine_mcq", {}).get("count", 0)
        passed = "PASS" if e.get("all_gates_pass") else "FAIL"
        prov = "OK" if e.get("provenance_ok") else "MISSING"
        e2e = "OK" if e.get("end_to_end_provenance") else "GAP"
        total_rules += r
        total_mcq += m
        total_q_rules += qr
        total_q_mcq += qm
        print(f"  {e['name']:<8} gates={passed:<4} prov={prov:<7} e2e={e2e:<3} rules={r:<5} mcq={m:<5} q_rules={qr:<3} q_mcq={qm:<3}")
    print(f"  {'TOTAL':<8} {'':<24} rules={total_rules:<5} mcq={total_mcq:<5} q_rules={total_q_rules:<3} q_mcq={total_q_mcq:<3}")
    print(f"\nKnown limitations: {len(report['known_limitations'])}")
    for lim in report["known_limitations"]:
        print(f"  - {lim}")
    print(f"Source e2e:  {report.get('source_e2e_status')}")
    print(f"Remediation: {'PASS' if report.get('remediation_pass') else 'FAIL'}")
    print(f"End-to-end:  {'PASS' if report.get('end_to_end_pass') else 'FAIL'}")
    print(f"Status:      {report.get('status')}")
    print(f"OVERALL:     {'PASS' if exit_code == 0 else 'FAIL'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
