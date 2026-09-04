"""Generate and statically validate the classic-texts historical freeze/evidence
artifacts (design §2/§3/§4).

Single generator with two subcommands:
  freeze    -- produce the cross-book frozen set (14 present / 2 absent files)
  evidence  -- produce the generation-evidence file (needs the freeze file)
  check     -- statically validate a freeze or evidence artifact

Static checks (evidence_static_check + freeze validator) only touch Git blob/HEAD
facts: schema, identity, frozen fields, record counts, record_set_binding and
HEAD blob SHAs. They never touch the external tar and never produce BLOCKED.
The `evidence --out` production path (design §10-④(1)) subprocesses the phase-③
verifier (scripts/verify_sanming_source_chain.py) with the frozen argv, classifies
its rc × schema output and takes the verifier identity from HEAD; the phase-①
zero fixtures remain only for module-function-level unit-test injection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 冻结基点（数据来源 Git 提交，§3/§4.1）
BASE_COMMIT = "c5cff699fdb547bd9270acbebe1f485380848751"

# 四书精确有序集（§2）
BOOKS = ("ditiansui", "qiongtongbaojian", "sanmingtonghui", "zipingzhenquan")

# 每书 4 kinds（§3 books/kinds 精确集）
KINDS = ("all_rules", "all_mcq", "quarantine_rules", "quarantine_mcq")

KIND_FILENAME = {
    "all_rules": "all_rules.json",
    "all_mcq": "all_mcq.jsonl",
    "quarantine_rules": "quarantine_rules.jsonl",
    "quarantine_mcq": "quarantine_mcq.jsonl",
}

# §4.1 source_chain 精确路径与身份（全长）
SNAP = "knowledge_base/classic_texts/sanmingtonghui/formal/source_snapshots/b4e9be580dbecd3e233d3adbe163299f06c6ca5174309dc83e8f14433796aaa2"
POINTER_REL = f"{SNAP}/RESPONSE_ARCHIVE_POINTER.json"
MANIFEST_REL = f"{SNAP}/source_manifest.json"
PARSER_REL = "scripts/fetch_sanming_chapters.py"
CHAPTER_LIST_REL = "knowledge_base/classic_texts/sanmingtonghui/chapter_list.txt"
EXTRACTOR_COMMIT = "f64a25ddd8ef43aef9ad75e189e72a4f9d373938"
EXTRACTOR_REL = "scripts/fetch_sanming_full.py"

# §4.1 未证事实完整 JSON 字面量（逐字符串冻结）
UNPROVEN_FACTS = [
    "四书聚合工件集（all_rules/all_mcq/quarantine_rules/quarantine_mcq）背后没有满足正式契约的归档模型 run manifest（正式契约要求：manifest_sha256 存在，manifest.immutable 为满足冻结字段契约的对象，api_generation.verification_level 等于 full）。",
    "本豁免仅覆盖上述历史生成运行缺正式 run manifest 这一事实，不延伸到任何未来生成运行。",
    "三本完成书（ditiansui/zipingzhenquan/qiongtongbaojian）的原始文本获取过程不被本证据证明（见设计 §8=S）。",
]

# 稳定错误码（§5 优先级：GENERATOR → FROZEN → FREEZE_STATIC → EVIDENCE_STATIC）
GENERATOR_IDENTITY_MISMATCH = "GENERATOR_IDENTITY_MISMATCH"
FROZEN_AT_COMMIT_MISMATCH = "FROZEN_AT_COMMIT_MISMATCH"
FREEZE_STATIC_MISMATCH = "FREEZE_STATIC_MISMATCH"
EVIDENCE_STATIC_MISMATCH = "EVIDENCE_STATIC_MISMATCH"

# §10-④(1) verifier 调用稳定错误码（stderr 单行 ERROR_CODE[:reason]，BLOCKED 必附 reason）
SOURCE_REPLAY_FAILED = "SOURCE_REPLAY_FAILED"
SOURCE_CHAIN_BLOCKED = "SOURCE_CHAIN_BLOCKED"
SOURCE_REPLAY_INVALID = "SOURCE_REPLAY_INVALID"

FREEZE_TOP_FIELDS = {
    "schema_version",
    "frozen_at_commit",
    "generator_blob_oid",
    "books",
    "counts",
}

EVIDENCE_TOP_FIELDS = {
    "schema_version",
    "frozen_at_commit",
    "generator_blob_oid",
    "generator_sha256",
    "artifact_files",
    "record_set_binding",
    "source_chain",
    "unproven_facts",
}

SOURCE_CHAIN_FIELDS = {
    "pointer_file_sha256",
    "pointer_blob_oid",
    "tar_sha256",
    "tar_size",
    "tar_relative_path",
    "manifest_file_sha256",
    "manifest_blob_oid",
    "extractor_blob_oid",
    "extractor_sha256",
    "parser_blob_oid",
    "chapter_list_blob_oid",
    "verifier_blob_oid",
    "verifier_sha256",
    "replay",
}


class CheckError(Exception):
    """A static-check failure carrying the stable error code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class VerifierCallError(Exception):
    """§10-④(1) verifier 调用/输出失败：稳定错误码 + 退出码 + 可选 BLOCKED reason。"""

    def __init__(self, code: str, exit_code: int, reason: str = "") -> None:
        self.code = code
        self.exit_code = exit_code
        self.reason = reason
        super().__init__(f"{code}:{reason}" if reason else code)


def _is_40hex(v) -> bool:
    return isinstance(v, str) and len(v) == 40 and all(c in "0123456789abcdef" for c in v)


def _is_64hex(v) -> bool:
    return isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)


def _canonical(obj) -> str:
    """§3 canonical_record_sha256 序列化（sort_keys，紧凑分隔）。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _serialize(obj) -> str:
    """§3 文件序列化（sort_keys，indent=2，末尾换行）。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def _loads_strict(text: str):
    """§3 严格 JSON 解析：拒绝重复 JSON 键（object_pairs_hook），其余同 json.loads。"""
    def _pairs(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise CheckError(FREEZE_STATIC_MISMATCH, f"duplicate JSON key: {k!r}")
            obj[k] = v
        return obj

    return json.loads(text, object_pairs_hook=_pairs)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _run_git(git_root: Path, args, check: bool = True):
    p = subprocess.run(["git", "-C", str(git_root), *args], capture_output=True)
    if check and p.returncode != 0:
        raise CheckError(
            EVIDENCE_STATIC_MISMATCH,
            f"git {' '.join(args)} failed: {p.stderr.decode('utf-8', 'replace').strip()}",
        )
    return p


def _git_blob_bytes(git_root: Path, commit: str, rel: str) -> bytes:
    return _run_git(git_root, ["show", f"{commit}:{rel}"]).stdout


def _git_blob_oid(git_root: Path, commit: str, rel: str) -> str:
    return _run_git(git_root, ["rev-parse", f"{commit}:{rel}"]).stdout.decode().strip()


def _git_blob_size(git_root: Path, commit: str, rel: str) -> int:
    return int(_run_git(git_root, ["cat-file", "-s", f"{commit}:{rel}"]).stdout.decode().strip())


def _git_blob_exists(git_root: Path, commit: str, rel: str) -> bool:
    p = _run_git(git_root, ["cat-file", "-e", f"{commit}:{rel}"], check=False)
    return p.returncode == 0


def _git_hash_object(git_root: Path, path: Path) -> str:
    return _run_git(git_root, ["hash-object", str(path)]).stdout.decode().strip()


def _book_rel(book: str, kind: str) -> str:
    return f"knowledge_base/classic_texts/{book}/{KIND_FILENAME[kind]}"


def _parse_records(blob: bytes, kind: str):
    """Parse a present artifact into its record list.

    .json -> JSON array of objects; .jsonl -> one object per non-empty line.
    Each record must be a dict with a non-empty string `id` (design §3).
    """
    text = blob.decode("utf-8")
    if KIND_FILENAME[kind].endswith(".json"):
        arr = _loads_strict(text)
        if not isinstance(arr, list):
            raise CheckError(FREEZE_STATIC_MISMATCH, f"{KIND_FILENAME[kind]} top-level not a list")
        records = arr
    else:
        records = [_loads_strict(line) for line in text.splitlines() if line.strip()]
    for r in records:
        if not isinstance(r, dict):
            raise CheckError(FREEZE_STATIC_MISMATCH, f"record not an object in {KIND_FILENAME[kind]}")
        if "id" not in r or not isinstance(r["id"], str) or not r["id"]:
            raise CheckError(FREEZE_STATIC_MISMATCH, f"record missing/non-string id in {KIND_FILENAME[kind]}")
    return records


def _record_entry(record: dict) -> dict:
    return {"id": record["id"], "sha256": _sha256_bytes(_canonical(record).encode("utf-8"))}


def build_freeze(git_root: Path, *, generator_blob_oid: str) -> dict:
    """Build the cross-book frozen set from BASE_COMMIT blobs (design §3)."""
    books: dict = {}
    counts: dict = {}
    for book in BOOKS:
        books[book] = {}
        counts[book] = {}
        for kind in KINDS:
            rel = _book_rel(book, kind)
            if _git_blob_exists(git_root, BASE_COMMIT, rel):
                blob = _git_blob_bytes(git_root, BASE_COMMIT, rel)
                records = [_record_entry(r) for r in _parse_records(blob, kind)]
                # v27 多重集合：同一文件允许同名 id 多条，按 (id,sha256) 排序保留重复次数
                records.sort(key=lambda e: (e["id"], e["sha256"]))
                books[book][kind] = {
                    "present": True,
                    "blob_oid": _git_blob_oid(git_root, BASE_COMMIT, rel),
                    "byte_size": _git_blob_size(git_root, BASE_COMMIT, rel),
                    "records": records,
                }
                counts[book][kind] = len(records)
            else:
                books[book][kind] = {
                    "present": False,
                    "blob_oid": None,
                    "byte_size": None,
                    "records": [],
                }
                counts[book][kind] = 0
    return {
        "schema_version": "1.0",
        "frozen_at_commit": BASE_COMMIT,
        "generator_blob_oid": generator_blob_oid,
        "books": books,
        "counts": counts,
    }


def _validate_freeze_static(freeze: dict) -> None:
    """All freeze static checks except frozen_at_commit (§3). Raises CheckError(FREEZE_STATIC_MISMATCH)."""
    if not isinstance(freeze, dict):
        raise CheckError(FREEZE_STATIC_MISMATCH, "freeze not an object")
    if set(freeze) != FREEZE_TOP_FIELDS:
        raise CheckError(FREEZE_STATIC_MISMATCH, f"freeze fields must be exactly {sorted(FREEZE_TOP_FIELDS)}")
    if freeze["schema_version"] != "1.0":
        raise CheckError(FREEZE_STATIC_MISMATCH, "freeze schema_version != 1.0")
    if not _is_40hex(freeze["generator_blob_oid"]):
        raise CheckError(FREEZE_STATIC_MISMATCH, "freeze generator_blob_oid not 40-hex")
    books = freeze["books"]
    if not isinstance(books, dict) or set(books) != set(BOOKS):
        raise CheckError(FREEZE_STATIC_MISMATCH, f"freeze books keys must be exactly {sorted(BOOKS)}")
    counts = freeze["counts"]
    if not isinstance(counts, dict) or set(counts) != set(BOOKS):
        raise CheckError(FREEZE_STATIC_MISMATCH, "freeze counts keys must be exactly the four books")
    for book in BOOKS:
        if not isinstance(books[book], dict) or set(books[book]) != set(KINDS):
            raise CheckError(FREEZE_STATIC_MISMATCH, f"freeze books[{book}] kinds must be exactly {sorted(KINDS)}")
        if not isinstance(counts[book], dict) or set(counts[book]) != set(KINDS):
            raise CheckError(FREEZE_STATIC_MISMATCH, f"freeze counts[{book}] kinds must be exactly {sorted(KINDS)}")
        for kind in KINDS:
            entry = books[book][kind]
            _validate_file_entry(entry, kind)
            if counts[book][kind] != len(entry["records"]):
                raise CheckError(FREEZE_STATIC_MISMATCH, f"counts mismatch for {book}/{kind}")
            recs = entry["records"]
            for e in recs:
                if (
                    not isinstance(e, dict)
                    or set(e) != {"id", "sha256"}
                    or not isinstance(e["id"], str)
                    or not e["id"]
                    or not _is_64hex(e["sha256"])
                ):
                    raise CheckError(FREEZE_STATIC_MISMATCH, f"bad record entry in {book}/{kind}")
            keys = [(e["id"], e["sha256"]) for e in recs]
            if keys != sorted(keys):
                raise CheckError(FREEZE_STATIC_MISMATCH, f"records not sorted by (id,sha256) for {book}/{kind}")


def _validate_file_entry(entry, kind: str) -> None:
    """Validate one freeze file entry: state-consistent schema (§3)."""
    if not isinstance(entry, dict):
        raise CheckError(FREEZE_STATIC_MISMATCH, f"file entry not an object for {kind}")
    if set(entry) != {"present", "blob_oid", "byte_size", "records"}:
        raise CheckError(FREEZE_STATIC_MISMATCH, f"file entry fields wrong for {kind}")
    if entry["present"] is True:
        if not _is_40hex(entry["blob_oid"]) or not isinstance(entry["byte_size"], int) or entry["byte_size"] < 0:
            raise CheckError(FREEZE_STATIC_MISMATCH, f"present entry bad blob/byte_size for {kind}")
        if not isinstance(entry["records"], list):
            raise CheckError(FREEZE_STATIC_MISMATCH, f"present entry records not a list for {kind}")
    elif entry["present"] is False:
        if entry["blob_oid"] is not None or entry["byte_size"] is not None or entry["records"] != []:
            raise CheckError(FREEZE_STATIC_MISMATCH, f"absent entry must be all-null/empty for {kind}")
    else:
        raise CheckError(FREEZE_STATIC_MISMATCH, f"present must be bool for {kind}")


def validate_freeze(freeze: dict) -> None:
    """Validate freeze: frozen_at_commit first, then static schema (§3/§5)."""
    if not isinstance(freeze, dict) or freeze.get("frozen_at_commit") != BASE_COMMIT:
        raise CheckError(FROZEN_AT_COMMIT_MISMATCH, "freeze frozen_at_commit != BASE")
    _validate_freeze_static(freeze)


def check_freeze_bytes(data: bytes, git_root: Path, *, expected_generator_blob_oid: str) -> None:
    """§3 `freeze --check` 全等重算契约（v27.1 P0）。

    解析 freeze 原始字节 → 静态校验（validate_freeze）→ 从冻结基点 16 个聚合
    blob 重建完整期望 freeze 对象（含每文件 blob_oid/byte_size/records 的
    (id,sha256) 多重集合、counts 与顶层字段，算法同生成路径；generator_blob_oid
    回填为 expected_generator_blob_oid）→ 与磁盘文件解析后的 canonical 序列化
    字节全等比对。纯静态自洽不足以通过；任一差异——合法 SHA 替换、增删同 id
    记录、改变重复次数、篡改 blob_oid/byte_size——一律拒绝
    （FREEZE_STATIC_MISMATCH）。
    """
    try:
        freeze = _loads_strict(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CheckError(FREEZE_STATIC_MISMATCH, f"invalid freeze JSON: {exc}") from exc
    validate_freeze(freeze)
    expected = build_freeze(git_root, generator_blob_oid=expected_generator_blob_oid)
    if data != _serialize(expected).encode("utf-8"):
        raise CheckError(FREEZE_STATIC_MISMATCH, "freeze bytes do not match BASE rebuild")


def freeze_full_equality_check(freeze: dict, git_root: Path) -> None:
    """§3 `freeze --check` 全等重算入口（freeze 对象 → 委托 check_freeze_bytes）。"""
    check_freeze_bytes(
        _serialize(freeze).encode("utf-8"),
        git_root,
        expected_generator_blob_oid=_git_hash_object(git_root, Path(__file__)),
    )


def build_evidence(
    freeze: dict,
    git_root: Path,
    *,
    generator_blob_oid: str,
    generator_sha256: str,
    verifier_blob_oid: str,
    verifier_sha256: str,
    replay: dict,
) -> dict:
    """Build the generation-evidence file (design §4).

    verifier_blob_oid / verifier_sha256 / replay are injected: the real verifier
    is implemented in phase ③, so phase ① supplies a frozen fixture (design §10-①).
    """
    validate_freeze(freeze)

    pointer_blob = _git_blob_bytes(git_root, BASE_COMMIT, POINTER_REL)
    pointer = json.loads(pointer_blob.decode("utf-8"))

    artifact_files: dict = {}
    for book in BOOKS:
        artifact_files[book] = {}
        for kind in KINDS:
            fz = freeze["books"][book][kind]
            if fz["present"]:
                blob = _git_blob_bytes(git_root, BASE_COMMIT, _book_rel(book, kind))
                artifact_files[book][kind] = {
                    "present": True,
                    "blob_oid": fz["blob_oid"],
                    "byte_size": fz["byte_size"],
                    "file_sha256": _sha256_bytes(blob),
                    "record_count": len(fz["records"]),
                }
            else:
                artifact_files[book][kind] = {
                    "present": False,
                    "blob_oid": None,
                    "byte_size": None,
                    "file_sha256": None,
                    "record_count": 0,
                }

    source_chain = {
        "sanmingtonghui": {
            "pointer_file_sha256": _sha256_bytes(pointer_blob),
            "pointer_blob_oid": _git_blob_oid(git_root, BASE_COMMIT, POINTER_REL),
            "tar_sha256": pointer["archive_sha256"],
            "tar_size": pointer["archive_size"],
            "tar_relative_path": pointer["archive_uri"],
            "manifest_file_sha256": _sha256_bytes(_git_blob_bytes(git_root, BASE_COMMIT, MANIFEST_REL)),
            "manifest_blob_oid": _git_blob_oid(git_root, BASE_COMMIT, MANIFEST_REL),
            "extractor_blob_oid": _git_blob_oid(git_root, EXTRACTOR_COMMIT, EXTRACTOR_REL),
            "extractor_sha256": _sha256_bytes(_git_blob_bytes(git_root, EXTRACTOR_COMMIT, EXTRACTOR_REL)),
            "parser_blob_oid": _git_blob_oid(git_root, BASE_COMMIT, PARSER_REL),
            "chapter_list_blob_oid": _git_blob_oid(git_root, BASE_COMMIT, CHAPTER_LIST_REL),
            "verifier_blob_oid": verifier_blob_oid,
            "verifier_sha256": verifier_sha256,
            "replay": replay,
        }
    }

    return {
        "schema_version": "1.0",
        "frozen_at_commit": BASE_COMMIT,
        "generator_blob_oid": generator_blob_oid,
        "generator_sha256": generator_sha256,
        "artifact_files": artifact_files,
        "record_set_binding": {
            "frozen_manifest_file_sha256": _sha256_bytes(_serialize(freeze).encode("utf-8")),
            "counts": freeze["counts"],
        },
        "source_chain": source_chain,
        "unproven_facts": list(UNPROVEN_FACTS),
    }


def _validate_evidence_static(
    evidence: dict,
    freeze: dict,
    git_root: Path,
    *,
    expected_generator_blob_oid: str,
    expected_generator_sha256: str,
    expected_verifier_blob_oid: str,
    expected_verifier_sha256: str,
) -> None:
    """evidence_static_check: Git blob/HEAD facts only (design §4). Raises CheckError."""
    if not isinstance(evidence, dict):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "evidence not an object")
    if set(evidence) != EVIDENCE_TOP_FIELDS:
        raise CheckError(EVIDENCE_STATIC_MISMATCH, f"evidence fields must be exactly {sorted(EVIDENCE_TOP_FIELDS)}")
    if evidence["schema_version"] != "1.0":
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "evidence schema_version != 1.0")

    # 六向身份（§4）：blob_oid 链 + sha256 链
    if evidence["generator_blob_oid"] != freeze["generator_blob_oid"]:
        raise CheckError(GENERATOR_IDENTITY_MISMATCH, "evidence.generator_blob_oid != freeze.generator_blob_oid")
    if evidence["generator_blob_oid"] != expected_generator_blob_oid:
        raise CheckError(GENERATOR_IDENTITY_MISMATCH, "generator_blob_oid != HEAD/worktree generator blob")
    if evidence["generator_sha256"] != expected_generator_sha256:
        raise CheckError(GENERATOR_IDENTITY_MISMATCH, "generator_sha256 != generator file bytes sha256")

    # 第 2 级 frozen_at_commit（§4）
    if evidence["frozen_at_commit"] != freeze["frozen_at_commit"]:
        raise CheckError(FROZEN_AT_COMMIT_MISMATCH, "evidence.frozen_at_commit != freeze.frozen_at_commit")
    if evidence["frozen_at_commit"] != BASE_COMMIT:
        raise CheckError(FROZEN_AT_COMMIT_MISMATCH, "evidence.frozen_at_commit != BASE")

    # artifact_files 与 freeze 逐项一致（§4）
    af = evidence["artifact_files"]
    if not isinstance(af, dict) or set(af) != set(BOOKS):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "artifact_files keys must be exactly the four books")
    for book in BOOKS:
        if not isinstance(af[book], dict) or set(af[book]) != set(KINDS):
            raise CheckError(EVIDENCE_STATIC_MISMATCH, f"artifact_files[{book}] kinds wrong")
        for kind in KINDS:
            fz = freeze["books"][book][kind]
            e = af[book][kind]
            if not isinstance(e, dict) or set(e) != {"present", "blob_oid", "byte_size", "file_sha256", "record_count"}:
                raise CheckError(EVIDENCE_STATIC_MISMATCH, f"artifact_files[{book}][{kind}] fields wrong")
            if e["present"] is True:
                if e["blob_oid"] != fz["blob_oid"] or e["byte_size"] != fz["byte_size"]:
                    raise CheckError(EVIDENCE_STATIC_MISMATCH, f"artifact_files[{book}][{kind}] blob/byte_size drift")
                expected_file_sha256 = _sha256_bytes(
                    _git_blob_bytes(git_root, BASE_COMMIT, _book_rel(book, kind))
                )
                if e["file_sha256"] != expected_file_sha256:
                    raise CheckError(EVIDENCE_STATIC_MISMATCH, f"artifact_files[{book}][{kind}] file_sha256 drift")
                if e["record_count"] != len(fz["records"]):
                    raise CheckError(EVIDENCE_STATIC_MISMATCH, f"artifact_files[{book}][{kind}] record_count mismatch")
            elif e["present"] is False:
                if e["blob_oid"] is not None or e["byte_size"] is not None or e["file_sha256"] is not None or e["record_count"] != 0:
                    raise CheckError(EVIDENCE_STATIC_MISMATCH, f"artifact_files[{book}][{kind}] absent entry non-null")
            else:
                raise CheckError(EVIDENCE_STATIC_MISMATCH, f"artifact_files[{book}][{kind}] present not bool")

    # record_set_binding（§4）
    rsb = evidence["record_set_binding"]
    if not isinstance(rsb, dict) or set(rsb) != {"frozen_manifest_file_sha256", "counts"}:
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "record_set_binding fields wrong")
    if rsb["frozen_manifest_file_sha256"] != _sha256_bytes(_serialize(freeze).encode("utf-8")):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "record_set_binding.frozen_manifest_file_sha256 != freeze bytes sha256")
    if rsb["counts"] != freeze["counts"]:
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "record_set_binding.counts != freeze.counts")

    # source_chain（§4）：sanmingtonghui 精确字段集 + 静态 SHA/身份 vs HEAD blob
    sc = evidence["source_chain"]
    if not isinstance(sc, dict) or set(sc) != {"sanmingtonghui"}:
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain keys must be exactly {sanmingtonghui}")
    sch = sc["sanmingtonghui"]
    if not isinstance(sch, dict) or set(sch) != SOURCE_CHAIN_FIELDS:
        raise CheckError(EVIDENCE_STATIC_MISMATCH, f"source_chain.sanmingtonghui fields must be exactly {sorted(SOURCE_CHAIN_FIELDS)}")
    if sch["pointer_blob_oid"] != _git_blob_oid(git_root, BASE_COMMIT, POINTER_REL):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain pointer_blob_oid drift")
    if sch["pointer_file_sha256"] != _sha256_bytes(_git_blob_bytes(git_root, BASE_COMMIT, POINTER_REL)):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain pointer_file_sha256 drift")
    if sch["manifest_blob_oid"] != _git_blob_oid(git_root, BASE_COMMIT, MANIFEST_REL):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain manifest_blob_oid drift")
    if sch["manifest_file_sha256"] != _sha256_bytes(_git_blob_bytes(git_root, BASE_COMMIT, MANIFEST_REL)):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain manifest_file_sha256 drift")
    if sch["extractor_blob_oid"] != _git_blob_oid(git_root, EXTRACTOR_COMMIT, EXTRACTOR_REL):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain extractor_blob_oid drift")
    if sch["extractor_sha256"] != _sha256_bytes(_git_blob_bytes(git_root, EXTRACTOR_COMMIT, EXTRACTOR_REL)):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain extractor_sha256 drift")
    if sch["parser_blob_oid"] != _git_blob_oid(git_root, BASE_COMMIT, PARSER_REL):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain parser_blob_oid drift")
    if sch["chapter_list_blob_oid"] != _git_blob_oid(git_root, BASE_COMMIT, CHAPTER_LIST_REL):
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain chapter_list_blob_oid drift")
    # verifier 静态比对：记录值 vs 注入期望（阶段 ③ 后由真实 HEAD blob 提供期望值）
    if sch["verifier_blob_oid"] != expected_verifier_blob_oid:
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain verifier_blob_oid != expected verifier blob")
    if sch["verifier_sha256"] != expected_verifier_sha256:
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "source_chain verifier_sha256 != expected verifier sha256")

    # unproven_facts 逐字符串相等（§4）
    if evidence["unproven_facts"] != UNPROVEN_FACTS:
        raise CheckError(EVIDENCE_STATIC_MISMATCH, "unproven_facts not equal to frozen literal")


def evidence_static_check(
    evidence: dict,
    freeze: dict,
    git_root: Path,
    *,
    expected_generator_blob_oid: str,
    expected_generator_sha256: str,
    expected_verifier_blob_oid: str,
    expected_verifier_sha256: str,
) -> None:
    """Full evidence static check: identity → frozen_at_commit → static schema (§4/§5)."""
    validate_freeze(freeze)
    _validate_evidence_static(
        evidence,
        freeze,
        git_root,
        expected_generator_blob_oid=expected_generator_blob_oid,
        expected_generator_sha256=expected_generator_sha256,
        expected_verifier_blob_oid=expected_verifier_blob_oid,
        expected_verifier_sha256=expected_verifier_sha256,
    )


# ---------------------------------------------------------------------------
# 阶段 ① 注入 fixture：verifier 未实现前的冻结占位身份 + 重放样本（§10-①）。
# 阶段 ④（§10-④(1)）起 CLI 生产路径以 HEAD 的 verify_sanming_source_chain.py
# 身份与真实重放替代；fixture 仅保留于模块函数级单测注入，不进 CLI 生产路径。
# ---------------------------------------------------------------------------
VERIFIER_FIXTURE_BLOB_OID = "0" * 40
VERIFIER_FIXTURE_SHA256 = "0" * 64
REPLAY_FIXTURE = {"chapters_expected": 303, "c1_pass": 0, "c2_pass": 0, "c3_pass": 0, "failures": []}

# ---------------------------------------------------------------------------
# §10-④(1) C-evidence-wiring：verifier 子进程调用与输出全状态分类
# ---------------------------------------------------------------------------
_VERIFIER_RUN = subprocess.run  # 注入点：测试捕获 argv / 模拟输出；生产路径为 subprocess.run

_VERIFIER_OUTPUT_KEYS = {"schema_version", "status", "chapters_expected", "c1_pass", "c2_pass", "c3_pass", "failures"}
_VERIFIER_BLOCKED_KEYS = {"schema_version", "status", "reason"}
_FAILURE_ENTRY_KEYS = {"chapter", "check", "code", "detail"}
_VERIFIER_FAILURE_CODES = frozenset({
    "ARCHIVE_MEMBER_MISSING",
    "C1_SHA_MISMATCH",
    "C2_HEADING_NOT_FOUND",
    "C2_NO_BODY",
    "C2_EXTRACTION_ERROR",
    "C2_SHA_MISMATCH",
    "C3_SHA_MISMATCH",
})
_VERIFIER_BLOCKED_REASONS = frozenset({
    "archive_missing",
    "archive_sha_mismatch",
    "archive_size_mismatch",
    "verifier_identity_mismatch",
    "archive_root_missing",
})


def _is_nonbool_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _loads_verifier_stdout(raw: bytes):
    """严格解析 verifier stdout：拒绝重复 JSON 键（§10-④(1)）。"""

    def _pairs(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError(f"duplicate JSON key: {k!r}")
            obj[k] = v
        return obj

    return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)


def _verifier_counts_in_range(out: dict) -> bool:
    """四计数非 bool int 且 ∈ [0,303]，chapters_expected==303（成功/failures 分支共用量程判据）。"""
    for key in ("chapters_expected", "c1_pass", "c2_pass", "c3_pass"):
        v = out[key]
        if not _is_nonbool_int(v) or not 0 <= v <= 303:
            return False
    return out["chapters_expected"] == 303


def _verifier_failures_schema_ok(out: dict) -> bool:
    """rc==1 分支特有判据：failures 非空列表 + 条目精确键集/类型/枚举 + (chapter,check,code,detail) 排序。"""
    failures = out["failures"]
    if not isinstance(failures, list) or not failures:
        return False
    prev = None
    for entry in failures:
        if not isinstance(entry, dict) or set(entry) != _FAILURE_ENTRY_KEYS:
            return False
        if not _is_nonbool_int(entry["chapter"]):
            return False
        if entry["check"] not in ("C1", "C2", "C3"):
            return False
        if entry["code"] not in _VERIFIER_FAILURE_CODES:
            return False
        if not isinstance(entry["detail"], str):
            return False
        key = (entry["chapter"], entry["check"], entry["code"], entry["detail"])
        if prev is not None and key < prev:
            return False
        prev = key
    return True


def _classify_verifier_output(proc) -> dict:
    """§10-④(1) verifier 输出全状态分类（v27.7–v27.10 冻结）。

    先严格解析 stdout（拒绝重复键），再按退出码 × schema 联合判断；
    成功返回五字段 replay，失败抛 VerifierCallError，禁止其他映射。
    """
    try:
        out = _loads_verifier_stdout(proc.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
    if not isinstance(out, dict):
        raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)

    if proc.returncode == 0:
        if set(out) != _VERIFIER_OUTPUT_KEYS:
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        if out["schema_version"] != "1.0" or out["status"] != "OK":
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        if not _verifier_counts_in_range(out):
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        if out["c1_pass"] != 303 or out["c2_pass"] != 303 or out["c3_pass"] != 303:
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        if out["failures"] != []:
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        return {k: out[k] for k in ("chapters_expected", "c1_pass", "c2_pass", "c3_pass", "failures")}

    if proc.returncode == 1:
        # 复用成功分支的顶层键集合、schema_version、status、字段类型及取值范围判据；
        # 分支特有判据为 c1/c2/c3 可小于 303 且 failures 非空（v27.10）。
        if set(out) != _VERIFIER_OUTPUT_KEYS:
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        if out["schema_version"] != "1.0" or out["status"] != "OK":
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        if not _verifier_counts_in_range(out):
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        if not _verifier_failures_schema_ok(out):
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        raise VerifierCallError(SOURCE_REPLAY_FAILED, 1)

    if proc.returncode == 3:
        if set(out) != _VERIFIER_BLOCKED_KEYS:
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        if out["schema_version"] != "1.0" or out["status"] != "BLOCKED":
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        if out["reason"] not in _VERIFIER_BLOCKED_REASONS:
            raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
        raise VerifierCallError(SOURCE_CHAIN_BLOCKED, 3, reason=out["reason"])

    raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)


def _run_verifier(git_root: Path, archive_root: Path):
    """verifier 调用契约（§10-④(1) fail-closed）：argv 逐字冻结，不经 shell。"""
    argv = [
        sys.executable,
        str(git_root / "scripts" / "verify_sanming_source_chain.py"),
        "--git-root",
        str(git_root),
        "--archive-root",
        str(archive_root),
    ]
    return _VERIFIER_RUN(argv, capture_output=True)


def _current_verifier_identity(git_root: Path):
    """verifier 身份取自 HEAD blob（§10-④(1)：生成与 --check 均用 HEAD 身份）。"""
    rel = "scripts/verify_sanming_source_chain.py"
    blob_oid = _run_git(git_root, ["rev-parse", f"HEAD:{rel}"]).stdout.decode().strip()
    sha256 = _sha256_bytes(_run_git(git_root, ["show", f"HEAD:{rel}"]).stdout)
    return blob_oid, sha256


def _write_evidence_atomically(out_path: Path, data: bytes) -> None:
    """写出契约 ⑤–⑦（§10-④(1)）：同目录临时文件 → 读回校验字节 → os.replace。

    任意失败时目标路径不存在则保持不存在、已存在则字节完全不变；临时文件在
    异常路径 try/finally 清理，清理失败仅记录，不改变原目标文件、不掩盖原错误。
    """
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(out_path.parent), prefix=out_path.name + ".", suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if Path(tmp_path).read_bytes() != data:
            raise CheckError(EVIDENCE_STATIC_MISMATCH, "evidence temp read-back mismatch")
        os.replace(tmp_path, out_path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass  # 清理失败仅记录：不改变目标文件、不抛出掩盖原错误


def generate_evidence_file(freeze_path, out_path, git_root: Path, archive_root) -> None:
    """§10-④(1) 正式 evidence 生产入口（v27.7 冻结顺序链 ①–⑦）。

    ① verifier 成功 → ② 内存构造 candidate → ③ evidence_static_check（六向身份与
    frozen_at_commit 第 2 级随本步执行）→ ④ canonical 序列化 → ⑤⑥⑦ 临时文件原子写出。
    """
    try:
        proc = _run_verifier(git_root, Path(archive_root))
    except OSError:
        raise VerifierCallError(SOURCE_REPLAY_INVALID, 1)
    replay = _classify_verifier_output(proc)
    freeze = _loads_strict(Path(freeze_path).read_text(encoding="utf-8"))
    gen_oid = _git_hash_object(git_root, Path(__file__))
    gen_sha = _sha256_bytes(Path(__file__).read_bytes())
    ver_oid, ver_sha = _current_verifier_identity(git_root)
    evidence = build_evidence(
        freeze,
        git_root,
        generator_blob_oid=gen_oid,
        generator_sha256=gen_sha,
        verifier_blob_oid=ver_oid,
        verifier_sha256=ver_sha,
        replay=replay,
    )
    evidence_static_check(
        evidence,
        freeze,
        git_root,
        expected_generator_blob_oid=gen_oid,
        expected_generator_sha256=gen_sha,
        expected_verifier_blob_oid=ver_oid,
        expected_verifier_sha256=ver_sha,
    )
    _write_evidence_atomically(Path(out_path), _serialize(evidence).encode("utf-8"))


def _current_generator_identity(git_root: Path):
    """Generator identity from HEAD blob (used by check); phase ① tests inject
    the worktree file identity instead since the generator is not yet committed."""
    blob_oid = _run_git(git_root, ["rev-parse", f"HEAD:scripts/generate_classic_historical_freeze.py"]).stdout.decode().strip()
    sha256 = _sha256_bytes(_run_git(git_root, ["show", f"HEAD:scripts/generate_classic_historical_freeze.py"]).stdout)
    return blob_oid, sha256


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="generate_classic_historical_freeze")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_freeze = sub.add_parser("freeze")
    freeze_mode = p_freeze.add_mutually_exclusive_group(required=True)
    freeze_mode.add_argument("--out")
    freeze_mode.add_argument("--check", metavar="PATH")
    p_freeze.add_argument("--git-root", default=str(ROOT))

    p_evidence = sub.add_parser("evidence")
    p_evidence.add_argument("--freeze", required=True)
    evidence_mode = p_evidence.add_mutually_exclusive_group(required=True)
    evidence_mode.add_argument("--out")
    evidence_mode.add_argument("--check", metavar="PATH")
    p_evidence.add_argument("--git-root", default=str(ROOT))
    p_evidence.add_argument("--archive-root")

    a = ap.parse_args(argv)
    git_root = Path(a.git_root)
    try:
        if a.cmd == "freeze":
            gen_oid = _git_hash_object(git_root, Path(__file__))
            if a.check:
                check_freeze_bytes(Path(a.check).read_bytes(), git_root, expected_generator_blob_oid=gen_oid)
            else:
                freeze = build_freeze(git_root, generator_blob_oid=gen_oid)
                data = _serialize(freeze).encode("utf-8")
                check_freeze_bytes(data, git_root, expected_generator_blob_oid=gen_oid)
                Path(a.out).write_bytes(data)
        elif a.cmd == "evidence":
            # 参数模式契约（§10-④(1)）：--out 必填 --archive-root；--check 必须拒绝该参数
            if a.check is not None and a.archive_root is not None:
                print(SOURCE_REPLAY_INVALID, file=sys.stderr)
                return 1
            if a.out is not None and a.archive_root is None:
                print(SOURCE_REPLAY_INVALID, file=sys.stderr)
                return 1
            if a.check:
                # --check 只执行静态身份校验：不调用 verifier、不访问归档（§10-④(1)）
                freeze = _loads_strict(Path(a.freeze).read_text(encoding="utf-8"))
                evidence = _loads_strict(Path(a.check).read_text(encoding="utf-8"))
                gen_oid, gen_sha = _current_generator_identity(git_root)
                ver_oid, ver_sha = _current_verifier_identity(git_root)
                evidence_static_check(
                    evidence,
                    freeze,
                    git_root,
                    expected_generator_blob_oid=gen_oid,
                    expected_generator_sha256=gen_sha,
                    expected_verifier_blob_oid=ver_oid,
                    expected_verifier_sha256=ver_sha,
                )
            else:
                generate_evidence_file(a.freeze, a.out, git_root, a.archive_root)
        return 0
    except CheckError as e:
        print(e.code, file=sys.stderr)
        return 1
    except VerifierCallError as e:
        print(f"{e.code}:{e.reason}" if e.reason else e.code, file=sys.stderr)
        return e.exit_code
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"{EVIDENCE_STATIC_MISMATCH}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
