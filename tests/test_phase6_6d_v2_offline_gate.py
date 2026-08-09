"""Phase 6 6D-v2 offline gate tests - authoritative phase1 receipt."""
import hashlib
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts import phase6_6d_v2_offline_gate as gate

_RECEIPT = os.path.join(PROJECT_ROOT, "docs/phase6/6d-v2/phase1_receipt.json")
_MANIFEST = os.path.join(
    PROJECT_ROOT, "docs/phase6/6d-v2/temporal_routed_cases.json")

_V1_REQUIRED_FIELDS = (
    "status", "n_routed", "temporal_routed_cases_sha256",
    "dataset_sha256_by_year", "dataset_set_sha256",
)
_V2_CHECK_FIELDS = (
    "on_limited_no_relations", "arm_fail_closed_ok", "off_reuse_precheck_ok",
)


def _load_receipt():
    with open(_RECEIPT, encoding="utf-8") as f:
        return json.load(f)


def test_receipt_pass_and_n31():
    receipt = _load_receipt()
    assert receipt["status"] == "PASS"
    assert receipt["n_routed"] == 31


def test_receipt_keeps_v1_validated_fields():
    receipt = _load_receipt()
    for f in _V1_REQUIRED_FIELDS:
        assert f in receipt, f"receipt missing v1-validated field: {f}"
    with open(_MANIFEST, encoding="utf-8") as f:
        entries = json.load(f)
    # 字段 6：n_routed == manifest entries 数
    assert receipt["n_routed"] == len(entries)
    # temporal_routed_cases_sha256 == manifest canonical SHA
    sha = hashlib.sha256(
        json.dumps(entries, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    assert receipt["temporal_routed_cases_sha256"] == sha
    # dataset_set_sha256 == canonical(dataset_sha256_by_year)
    set_sha = hashlib.sha256(
        json.dumps(receipt["dataset_sha256_by_year"], sort_keys=True,
                   ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    assert receipt["dataset_set_sha256"] == set_sha


def test_receipt_has_v2_check_fields():
    receipt = _load_receipt()
    for f in _V2_CHECK_FIELDS:
        assert receipt.get(f) is True, f"v2 check field missing/not True: {f}"


def test_receipt_passes_v1_validation():
    # run_dev 用同一强校验；v2 receipt 必须不被拒启
    from scripts.phase6_6d_orchestrator import _validate_phase1_receipt
    _validate_phase1_receipt(_RECEIPT, _MANIFEST)


def test_blocked_branch_does_not_overwrite_manifest(tmp_path):
    # N < 20 → BLOCKED 且不覆盖写 manifest；v2 检查项字段仍在 receipt 中
    ds_dir = tmp_path / "datasets"
    ds_dir.mkdir()
    case = {"case_id": "x1", "question": "2024年运势如何？",
            "options": ["A. 好", "B. 坏"], "birth_year": 1990, "domain": "x"}
    for year in ("2024", "2025"):
        (ds_dir / f"baziqa_contest8_{year}_holdout_enriched.jsonl").write_text(
            json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    out = tmp_path / "out" / "temporal_routed_cases.json"
    rc = gate.main([
        "--datasets", "2024,2025",
        "--datasets-dir", str(ds_dir),
        "--output", str(out),
        "--v1-archive-dir", str(tmp_path / "no-archive"),
        "--v1-runs-dir", str(tmp_path / "no-runs"),
    ])
    assert rc == 1
    assert not out.exists(), "BLOCKED must not overwrite the manifest"
    receipt_path = tmp_path / "out" / "phase1_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "BLOCKED"
    assert receipt["n_routed"] < 20
    for f in _V1_REQUIRED_FIELDS + _V2_CHECK_FIELDS:
        assert f in receipt, f"BLOCKED receipt missing field: {f}"
