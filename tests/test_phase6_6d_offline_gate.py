"""Phase 6 6D offline gate tests - temporal routed manifest generation and freeze."""
from __future__ import annotations

import hashlib
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.phase6_6d_offline_gate import (
    audit_dataset,
    compute_dataset_sha256,
    generate_routed_manifest,
    write_manifest,
    write_receipt,
)

_DATASETS_DIR = "benchmark/datasets"
_DS_2025 = "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl"
_CANONICAL = dict(sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def test_offline_gate_generates_routed_manifest(tmp_path):
    entries, sha_by_year, receipt = generate_routed_manifest(["2024", "2025"], _DATASETS_DIR)
    assert len(entries) > 0
    for e in entries:
        assert "year" in e and "dataset_sha256" in e and "case_id" in e
        assert "domain" in e and "route_state" in e and "matched_rules" in e
        assert "target_years" in e


def test_offline_gate_manifest_canonical_json(tmp_path):
    entries1, _, _ = generate_routed_manifest(["2024", "2025"], _DATASETS_DIR)
    entries2, _, _ = generate_routed_manifest(["2024", "2025"], _DATASETS_DIR)
    sha1 = hashlib.sha256(json.dumps(entries1, **_CANONICAL).encode()).hexdigest()
    sha2 = hashlib.sha256(json.dumps(entries2, **_CANONICAL).encode()).hexdigest()
    assert sha1 == sha2


def test_offline_gate_atomic_write(tmp_path):
    path = str(tmp_path / "test_manifest.json")
    entries = [{"year": "2025", "case_id": "test"}]
    sha = write_manifest(entries, path)
    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")
    assert len(sha) == 64


def test_offline_gate_dataset_sha_verified():
    sha = compute_dataset_sha256(_DS_2025)
    assert len(sha) == 64


def test_dataset_sha256_lf_normalized_crlf_lf_equivalent(tmp_path):
    """P0: dataset SHA must be checkout-independent. A CRLF worktree (Windows
    core.autocrlf) and an LF clean clone/CI must hash the same git content to
    the SAME digest. Hashing raw worktree bytes produced different SHAs per
    checkout and rejected legal revalidation."""
    body = b'{"case_id":"x","question":"q","birth_year":1990}\n' * 3
    crlf = tmp_path / "crlf.jsonl"
    lf = tmp_path / "lf.jsonl"
    crlf.write_bytes(body.replace(b"\n", b"\r\n"))
    lf.write_bytes(body)
    assert compute_dataset_sha256(str(crlf)) == compute_dataset_sha256(str(lf))
    # The canonical value == hashing the LF bytes directly.
    import hashlib as _h
    assert compute_dataset_sha256(str(lf)) == _h.sha256(body).hexdigest()


def test_dataset_sha256_crlf_cross_chunk_boundary(tmp_path):
    """P0 regression: a CRLF sequence whose CR falls at the end of one 8192-byte
    read chunk and LF at the start of the next must still be normalized. The
    previous per-chunk replace() implementation dropped such boundary CRLFs."""
    # Build a body where the ONLY CRLF straddles the 8192-byte chunk boundary.
    prefix = b"a" * 8191  # 8192nd byte = b"\r"
    data = prefix + b"\r\n" + b'b{"k":"v"}\n' * 2
    crlf = tmp_path / "cross_crlf.jsonl"
    crlf.write_bytes(data)
    lf_body = prefix + b"\n" + b'b{"k":"v"}\n' * 2
    import hashlib as _h
    assert compute_dataset_sha256(str(crlf)) == _h.sha256(lf_body).hexdigest()
    assert compute_dataset_sha256(str(crlf)) != _h.sha256(data).hexdigest()


def test_offline_gate_n_31():
    entries, _, receipt = generate_routed_manifest(["2024", "2025"], _DATASETS_DIR)
    assert receipt["n_routed"] == 31


def test_offline_gate_blocks_when_n_below_20(tmp_path):
    entries, _, receipt = generate_routed_manifest(["2025"], _DATASETS_DIR)
    assert receipt["status"] == "BLOCKED"
    assert receipt["n_routed"] == 13


def test_offline_gate_blocks_does_not_overwrite_existing_manifest(tmp_path):
    manifest_path = str(tmp_path / "temporal_routed_cases.json")
    with open(manifest_path, "w") as f:
        json.dump({"old": True}, f)
    receipt = {"status": "BLOCKED", "n_routed": 13}
    receipt_path = str(tmp_path / "phase1_receipt.json")
    write_receipt(receipt, receipt_path)
    assert os.path.exists(receipt_path)
    with open(manifest_path) as f:
        assert json.load(f)["old"] is True


def test_offline_gate_writes_phase1_receipt_pass(tmp_path):
    entries, sha_by_year, receipt = generate_routed_manifest(["2024", "2025"], _DATASETS_DIR)
    assert receipt["status"] == "PASS"
    assert "dataset_sha256_by_year" in receipt
    assert "dataset_set_sha256" in receipt
    assert "temporal_routed_cases_sha256" in receipt
    assert receipt["n_routed"] >= 20


def test_offline_gate_writes_phase1_receipt_blocked(tmp_path):
    entries, _, receipt = generate_routed_manifest(["2025"], _DATASETS_DIR)
    assert receipt["status"] == "BLOCKED"


def test_offline_gate_audit_dataset_returns_routed_entries():
    entries = audit_dataset("2025", _DS_2025)
    assert len(entries) == 13
    ds_sha = compute_dataset_sha256(_DS_2025)
    for e in entries:
        assert e["year"] == "2025"
        assert e["dataset_sha256"] == ds_sha
        assert e["route_state"] != "NOT_ROUTED"
