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