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
import re
import subprocess
import sys
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


def _e3_multiset_check(git_root: Path, freeze: dict) -> dict:
    """§5-E3：唯一读取当前 HEAD 聚合 blob 的阶段（E1/E2 之后执行）；
    与 BASE freeze 按 (id, sha256) 多重集合严格相等（保留重复次数）。"""
    fail = {"ok": False, "error_code": "EVIDENCE_STATIC_MISMATCH"}
    for book in FREEZE_BOOKS:
        for kind in KINDS:
            fz = freeze["books"][book][kind]
            if not fz["present"]:
                continue
            rel = _book_rel(book, kind)
            try:
                blob = _git_head_blob(git_root, rel)
                records = [_record_entry(r) for r in _parse_records(blob, kind)]
            except (RuntimeError, CheckError, json.JSONDecodeError, UnicodeDecodeError):
                return fail
            head_ms = sorted((e["id"], e["sha256"]) for e in records)
            fz_ms = sorted((e["id"], e["sha256"]) for e in fz["records"])
            if head_ms != fz_ms:
                return fail
    return {"ok": True, "error_code": None}


def _git_show_optional(git_root: Path, rel: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(git_root), "show", f"HEAD:{rel}"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


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
                           freeze: dict, evidence: dict) -> dict:
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
    # ④ HEAD manifest vs 已验收基线（默认模式）
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
    return {"ok": True, "revision_state": "ACCEPTED", "error_code": None,
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


def _source_identity_and_content(git_root: Path, book: str, evidence: dict,
                                 manifest_recs: list[dict]) -> str | None:
    """⑥⑦ 占位（Task 4 实现完整锚定链）。"""
    return None


def evaluate_provenance_admissibility(book_dir: Path, git_root: Path | None) -> dict:
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
    e3 = _e3_multiset_check(git_root, freeze)
    res["E3_ok"] = e3["ok"]
    if not e3["ok"]:
        res["exemption_error_code"] = e3["error_code"]
        return res
    res["historical_exemption_valid"] = True
    res["provenance_admissible"] = True
    return res


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
        adm = evaluate_provenance_admissibility(p, git_root)
        entry["provenance_state"] = adm["provenance_state"]
        entry["historical_exemption_valid"] = adm["historical_exemption_valid"]
        entry["provenance_admissible"] = adm["provenance_admissible"]
        entry["exemption_error_code"] = adm["exemption_error_code"]
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="generate_quality_report")
    ap.add_argument("--archive-root", default=None,
                    help="archive root for the sanmingtonghui source_chain_check")
    a = ap.parse_args(argv)
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
