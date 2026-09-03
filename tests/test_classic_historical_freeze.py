"""Tests for the classic-texts historical freeze/evidence generator (design §10-①).

Covers both subcommands and all rejection cases for the static checks only
(evidence_static_check + freeze validator). source_chain_check BLOCKED behavior
is intentionally NOT tested here -- it depends on the phase-③ verifier.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.generate_classic_historical_freeze as generator
from scripts.generate_classic_historical_freeze import (
    BASE_COMMIT,
    BOOKS,
    KINDS,
    GENERATOR_IDENTITY_MISMATCH,
    FROZEN_AT_COMMIT_MISMATCH,
    FREEZE_STATIC_MISMATCH,
    EVIDENCE_STATIC_MISMATCH,
    REPLAY_FIXTURE,
    VERIFIER_FIXTURE_BLOB_OID,
    VERIFIER_FIXTURE_SHA256,
    CheckError,
    build_evidence,
    build_freeze,
    check_freeze_bytes,
    evidence_static_check,
    validate_freeze,
)

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "scripts" / "generate_classic_historical_freeze.py"


def _gen_blob_oid() -> str:
    p = subprocess.run(["git", "-C", str(ROOT), "hash-object", str(GEN)], capture_output=True, text=True, check=True)
    return p.stdout.strip()


def _gen_sha256() -> str:
    return hashlib.sha256(GEN.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def freeze():
    return build_freeze(ROOT, generator_blob_oid=_gen_blob_oid())


@pytest.fixture(scope="module")
def evidence(freeze):
    return build_evidence(
        freeze,
        ROOT,
        generator_blob_oid=_gen_blob_oid(),
        generator_sha256=_gen_sha256(),
        verifier_blob_oid=VERIFIER_FIXTURE_BLOB_OID,
        verifier_sha256=VERIFIER_FIXTURE_SHA256,
        replay=REPLAY_FIXTURE,
    )


def _assert_code(excinfo, code: str) -> None:
    assert excinfo.value.code == code


# ---------------------------------------------------------------------------
# freeze 生成正确性
# ---------------------------------------------------------------------------

def test_freeze_top_fields_and_books(freeze):
    assert freeze["schema_version"] == "1.0"
    assert freeze["frozen_at_commit"] == BASE_COMMIT
    assert set(freeze["books"]) == set(BOOKS)
    assert set(freeze["counts"]) == set(BOOKS)
    for book in BOOKS:
        assert set(freeze["books"][book]) == set(KINDS)
        assert set(freeze["counts"][book]) == set(KINDS)


def test_freeze_absent_set_is_exactly_two(freeze):
    absent = []
    for book in BOOKS:
        for kind in KINDS:
            if freeze["books"][book][kind]["present"] is False:
                absent.append((book, kind))
    assert sorted(absent) == [
        ("sanmingtonghui", "quarantine_mcq"),
        ("zipingzhenquan", "quarantine_mcq"),
    ]


def test_freeze_validate_ok(freeze):
    validate_freeze(freeze)


def test_freeze_preserves_duplicate_ids_as_multiset(freeze):
    records = freeze["books"]["qiongtongbaojian"]["quarantine_rules"]["records"]
    duplicate = [record for record in records if record["id"] == "qtbj_001_038"]
    assert len(duplicate) == 2
    assert duplicate[0]["sha256"] != duplicate[1]["sha256"]
    assert records == sorted(records, key=lambda record: (record["id"], record["sha256"]))


def test_freeze_validator_allows_same_id_with_different_sha(freeze):
    f = copy.deepcopy(freeze)
    records = f["books"]["ditiansui"]["all_rules"]["records"]
    duplicate = {"id": records[0]["id"], "sha256": "f" * 64}
    records.append(duplicate)
    records.sort(key=lambda record: (record["id"], record["sha256"]))
    f["counts"]["ditiansui"]["all_rules"] += 1
    validate_freeze(f)


# ---------------------------------------------------------------------------
# freeze 校验拒绝项（freeze 静态 / 基点）
# ---------------------------------------------------------------------------

def test_freeze_wrong_base_rejected(freeze):
    f = copy.deepcopy(freeze)
    f["frozen_at_commit"] = "0" * 40
    with pytest.raises(CheckError) as e:
        validate_freeze(f)
    _assert_code(e, FROZEN_AT_COMMIT_MISMATCH)


def test_freeze_extra_top_field_rejected(freeze):
    f = copy.deepcopy(freeze)
    f["bogus"] = 1
    with pytest.raises(CheckError) as e:
        validate_freeze(f)
    _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_freeze_missing_book_rejected(freeze):
    f = copy.deepcopy(freeze)
    del f["books"]["ditiansui"]
    del f["counts"]["ditiansui"]
    with pytest.raises(CheckError) as e:
        validate_freeze(f)
    _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_freeze_extra_book_rejected(freeze):
    f = copy.deepcopy(freeze)
    f["books"]["hacker"] = f["books"]["ditiansui"]
    f["counts"]["hacker"] = f["counts"]["ditiansui"]
    with pytest.raises(CheckError) as e:
        validate_freeze(f)
    _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_freeze_missing_kind_rejected(freeze):
    f = copy.deepcopy(freeze)
    del f["books"]["ditiansui"]["all_rules"]
    del f["counts"]["ditiansui"]["all_rules"]
    with pytest.raises(CheckError) as e:
        validate_freeze(f)
    _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_freeze_cross_state_rejected(freeze):
    # absent entry must be all-null/empty
    f = copy.deepcopy(freeze)
    entry = f["books"]["sanmingtonghui"]["quarantine_mcq"]
    entry["blob_oid"] = "a" * 40
    with pytest.raises(CheckError) as e:
        validate_freeze(f)
    _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_freeze_count_mismatch_rejected(freeze):
    f = copy.deepcopy(freeze)
    f["counts"]["ditiansui"]["all_rules"] += 1
    with pytest.raises(CheckError) as e:
        validate_freeze(f)
    _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_freeze_unsorted_records_rejected(freeze):
    # v27：records 按 (id,sha256) 排序；交换两个不同记录破坏排序 → FREEZE_STATIC_MISMATCH
    f = copy.deepcopy(freeze)
    target = None
    for book in BOOKS:
        for kind in KINDS:
            recs = f["books"][book][kind]["records"]
            if len(recs) >= 2 and (recs[0]["id"], recs[0]["sha256"]) != (recs[1]["id"], recs[1]["sha256"]):
                target = (book, kind)
                break
        if target:
            break
    assert target is not None
    recs = f["books"][target[0]][target[1]]["records"]
    recs[0], recs[1] = recs[1], recs[0]
    with pytest.raises(CheckError) as e:
        validate_freeze(f)
    _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_freeze_same_id_different_sha_allowed(freeze):
    # v27 多重集合：同一文件允许同名 id 多条（不同 sha256），(id,sha256) 排序后冻结校验通过
    f = copy.deepcopy(freeze)
    target = None
    for book in BOOKS:
        for kind in KINDS:
            if f["books"][book][kind]["present"] and f["books"][book][kind]["records"]:
                target = (book, kind)
                break
        if target:
            break
    assert target is not None
    book, kind = target
    recs = f["books"][book][kind]["records"]
    base = recs[-1]
    dup = {"id": base["id"], "sha256": "f" * 64 if base["sha256"] != "f" * 64 else "e" * 64}
    recs.append(dup)
    recs.sort(key=lambda e: (e["id"], e["sha256"]))
    f["counts"][book][kind] += 1
    validate_freeze(f)  # 不应抛异常


def test_freeze_same_id_sha_order_rejected(freeze):
    f = copy.deepcopy(freeze)
    records = f["books"]["qiongtongbaojian"]["quarantine_rules"]["records"]
    indexes = [index for index, record in enumerate(records) if record["id"] == "qtbj_001_038"]
    assert len(indexes) == 2
    left, right = indexes
    records[left], records[right] = records[right], records[left]
    with pytest.raises(CheckError) as e:
        validate_freeze(f)
    _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_freeze_bad_record_sha_rejected(freeze):
    f = copy.deepcopy(freeze)
    f["books"]["ditiansui"]["all_rules"]["records"][0]["sha256"] = "not-a-sha"
    with pytest.raises(CheckError) as e:
        validate_freeze(f)
    _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_source_record_duplicate_json_key_rejected():
    blob = b'{"id":"first","id":"second"}\n'
    with pytest.raises(CheckError) as e:
        generator._parse_records(blob, "all_mcq")
    _assert_code(e, FREEZE_STATIC_MISMATCH)


@pytest.mark.parametrize("mutation", ("sha", "remove", "duplicate", "blob_oid", "byte_size"))
def test_freeze_check_rebuilds_from_base_and_rejects_self_consistent_drift(freeze, mutation):
    f = copy.deepcopy(freeze)
    entry = f["books"]["qiongtongbaojian"]["quarantine_rules"]
    if mutation == "sha":
        entry["records"][0]["sha256"] = "f" * 64
        entry["records"].sort(key=lambda record: (record["id"], record["sha256"]))
    elif mutation == "remove":
        entry["records"].pop()
        f["counts"]["qiongtongbaojian"]["quarantine_rules"] -= 1
    elif mutation == "duplicate":
        entry["records"].append(copy.deepcopy(entry["records"][-1]))
        entry["records"].sort(key=lambda record: (record["id"], record["sha256"]))
        f["counts"]["qiongtongbaojian"]["quarantine_rules"] += 1
    elif mutation == "blob_oid":
        entry["blob_oid"] = "f" * 40
    else:
        entry["byte_size"] += 1
    data = (json.dumps(f, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    with pytest.raises(CheckError) as e:
        check_freeze_bytes(data, ROOT, expected_generator_blob_oid=_gen_blob_oid())
    _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_freeze_cli_generate_and_check(tmp_path):
    path = tmp_path / "freeze.json"
    assert generator.main(["freeze", "--out", str(path), "--git-root", str(ROOT)]) == 0
    assert path.read_bytes().endswith(b"\n")
    assert generator.main(["freeze", "--check", str(path), "--git-root", str(ROOT)]) == 0


def test_freeze_cli_check_rejects_noncanonical_bytes(tmp_path, freeze, capsys):
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(freeze, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    assert generator.main(["freeze", "--check", str(path), "--git-root", str(ROOT)]) == 1
    assert FREEZE_STATIC_MISMATCH in capsys.readouterr().err


def test_freeze_record_missing_id_rejected(freeze):
    f = copy.deepcopy(freeze)
    recs = f["books"]["ditiansui"]["all_rules"]["records"]
    if recs:
        del recs[0]["id"]
        with pytest.raises(CheckError) as e:
            validate_freeze(f)
        _assert_code(e, FREEZE_STATIC_MISMATCH)


def test_freeze_record_nonstring_id_rejected(freeze):
    f = copy.deepcopy(freeze)
    recs = f["books"]["ditiansui"]["all_rules"]["records"]
    if recs:
        recs[0]["id"] = 123
        with pytest.raises(CheckError) as e:
            validate_freeze(f)
        _assert_code(e, FREEZE_STATIC_MISMATCH)


# ---------------------------------------------------------------------------
# freeze --check 全等重算（v27.1 P0，§3/§10-①）：CLI 子进程路径
# 从 BASE 16 聚合 blob 重建期望对象并字节全等；纯静态自洽不足以通过。
# ---------------------------------------------------------------------------

def _cli_check_freeze(path: Path):
    p = subprocess.run(
        [sys.executable, str(GEN), "freeze", "--check", str(path), "--git-root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stderr.strip()


def _write_freeze_file(tmp_path, freeze) -> Path:
    path = tmp_path / "freeze.json"
    data = (json.dumps(freeze, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    path.write_bytes(data)
    return path


def _tamper_target(freeze):
    """返回第一个含 records 的 (book, kind)。"""
    for book in BOOKS:
        for kind in KINDS:
            if freeze["books"][book][kind]["records"]:
                return book, kind
    raise AssertionError("no present file with records in fixture")


def test_freeze_check_full_equality_ok(tmp_path, freeze):
    path = _write_freeze_file(tmp_path, freeze)
    rc, err = _cli_check_freeze(path)
    assert rc == 0, err


def test_freeze_check_sha256_swap_rejected(tmp_path, freeze):
    # 合法 64 位 SHA 替换某 record sha256（保持排序与 counts 自洽）→ BASE 重建不等 → 拒绝
    f = copy.deepcopy(freeze)
    book, kind = _tamper_target(f)
    recs = f["books"][book][kind]["records"]
    recs[0]["sha256"] = "f" * 64 if recs[0]["sha256"] != "f" * 64 else "e" * 64
    recs.sort(key=lambda e: (e["id"], e["sha256"]))
    path = _write_freeze_file(tmp_path, f)
    rc, err = _cli_check_freeze(path)
    assert rc != 0
    assert err == FREEZE_STATIC_MISMATCH


def test_freeze_check_duplicate_added_rejected(tmp_path, freeze):
    # 增删同 id 记录 / 改变重复次数 → BASE 重建 records 多重集合不等 → 拒绝
    f = copy.deepcopy(freeze)
    book, kind = _tamper_target(f)
    recs = f["books"][book][kind]["records"]
    recs.append(copy.deepcopy(recs[-1]))
    recs.sort(key=lambda e: (e["id"], e["sha256"]))
    f["counts"][book][kind] += 1
    path = _write_freeze_file(tmp_path, f)
    rc, err = _cli_check_freeze(path)
    assert rc != 0
    assert err == FREEZE_STATIC_MISMATCH


def test_freeze_check_blob_oid_tamper_rejected(tmp_path, freeze):
    f = copy.deepcopy(freeze)
    for book in BOOKS:
        for kind in KINDS:
            if f["books"][book][kind]["present"]:
                f["books"][book][kind]["blob_oid"] = "a" * 40
                break
        else:
            continue
        break
    path = _write_freeze_file(tmp_path, f)
    rc, err = _cli_check_freeze(path)
    assert rc != 0
    assert err == FREEZE_STATIC_MISMATCH


def test_freeze_check_byte_size_tamper_rejected(tmp_path, freeze):
    f = copy.deepcopy(freeze)
    for book in BOOKS:
        for kind in KINDS:
            if f["books"][book][kind]["present"]:
                f["books"][book][kind]["byte_size"] += 1
                break
        else:
            continue
        break
    path = _write_freeze_file(tmp_path, f)
    rc, err = _cli_check_freeze(path)
    assert rc != 0
    assert err == FREEZE_STATIC_MISMATCH


# ---------------------------------------------------------------------------
# evidence 生成正确性
# ---------------------------------------------------------------------------

def test_evidence_top_fields(evidence):
    assert set(evidence) == {
        "schema_version",
        "frozen_at_commit",
        "generator_blob_oid",
        "generator_sha256",
        "artifact_files",
        "record_set_binding",
        "source_chain",
        "unproven_facts",
    }
    assert evidence["frozen_at_commit"] == BASE_COMMIT
    assert set(evidence["artifact_files"]) == set(BOOKS)
    assert set(evidence["source_chain"]) == {"sanmingtonghui"}


def test_evidence_static_check_ok(freeze, evidence):
    evidence_static_check(
        evidence,
        freeze,
        ROOT,
        expected_generator_blob_oid=_gen_blob_oid(),
        expected_generator_sha256=_gen_sha256(),
        expected_verifier_blob_oid=VERIFIER_FIXTURE_BLOB_OID,
        expected_verifier_sha256=VERIFIER_FIXTURE_SHA256,
    )


# ---------------------------------------------------------------------------
# evidence 校验拒绝项（六向身份 / 基点 / 静态）
# ---------------------------------------------------------------------------

def _check(evidence, freeze, **overrides):
    kw = dict(
        expected_generator_blob_oid=_gen_blob_oid(),
        expected_generator_sha256=_gen_sha256(),
        expected_verifier_blob_oid=VERIFIER_FIXTURE_BLOB_OID,
        expected_verifier_sha256=VERIFIER_FIXTURE_SHA256,
    )
    kw.update(overrides)
    evidence_static_check(evidence, freeze, ROOT, **kw)


def test_evidence_wrong_base_rejected(freeze, evidence):
    ev = copy.deepcopy(evidence)
    ev["frozen_at_commit"] = "0" * 40
    with pytest.raises(CheckError) as e:
        _check(ev, freeze)
    _assert_code(e, FROZEN_AT_COMMIT_MISMATCH)


def test_evidence_generator_sha_tampered_rejected(freeze, evidence):
    ev = copy.deepcopy(evidence)
    ev["generator_sha256"] = "0" * 64
    with pytest.raises(CheckError) as e:
        _check(ev, freeze)
    _assert_code(e, GENERATOR_IDENTITY_MISMATCH)


def test_evidence_generator_blob_tampered_rejected(freeze, evidence):
    ev = copy.deepcopy(evidence)
    ev["generator_blob_oid"] = "0" * 40
    with pytest.raises(CheckError) as e:
        _check(ev, freeze)
    _assert_code(e, GENERATOR_IDENTITY_MISMATCH)


def test_evidence_freeze_generator_drift_rejected(freeze, evidence):
    # freeze.generator_blob_oid 与 evidence.generator_blob_oid 不一致
    f = copy.deepcopy(freeze)
    f["generator_blob_oid"] = "0" * 40
    with pytest.raises(CheckError) as e:
        _check(evidence, f)
    _assert_code(e, GENERATOR_IDENTITY_MISMATCH)


def test_evidence_file_sha_tampered_rejected(freeze, evidence):
    ev = copy.deepcopy(evidence)
    ev["artifact_files"]["ditiansui"]["all_rules"]["file_sha256"] = "0" * 64
    with pytest.raises(CheckError) as e:
        _check(ev, freeze)
    _assert_code(e, EVIDENCE_STATIC_MISMATCH)


def test_evidence_record_count_mismatch_rejected(freeze, evidence):
    ev = copy.deepcopy(evidence)
    ev["artifact_files"]["ditiansui"]["all_rules"]["record_count"] += 1
    with pytest.raises(CheckError) as e:
        _check(ev, freeze)
    _assert_code(e, EVIDENCE_STATIC_MISMATCH)


def test_evidence_record_set_binding_tampered_rejected(freeze, evidence):
    ev = copy.deepcopy(evidence)
    ev["record_set_binding"]["counts"]["ditiansui"]["all_rules"] += 1
    with pytest.raises(CheckError) as e:
        _check(ev, freeze)
    _assert_code(e, EVIDENCE_STATIC_MISMATCH)


def test_evidence_verifier_blob_mismatch_rejected(freeze, evidence):
    ev = copy.deepcopy(evidence)
    ev["source_chain"]["sanmingtonghui"]["verifier_blob_oid"] = "1" * 40
    with pytest.raises(CheckError) as e:
        _check(ev, freeze)
    _assert_code(e, EVIDENCE_STATIC_MISMATCH)


def test_evidence_verifier_sha_mismatch_rejected(freeze, evidence):
    ev = copy.deepcopy(evidence)
    ev["source_chain"]["sanmingtonghui"]["verifier_sha256"] = "1" * 64
    with pytest.raises(CheckError) as e:
        _check(ev, freeze)
    _assert_code(e, EVIDENCE_STATIC_MISMATCH)


def test_evidence_unproven_facts_tampered_rejected(freeze, evidence):
    ev = copy.deepcopy(evidence)
    ev["unproven_facts"][0] = "tampered"
    with pytest.raises(CheckError) as e:
        _check(ev, freeze)
    _assert_code(e, EVIDENCE_STATIC_MISMATCH)
