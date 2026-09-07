"""Fail-closed tests for scripts/generate_acceptance_integration_closure.py.

The closure is a review gate: these tests pin the recomputed state
(aggregate counts, per-path blobs, group conservation, exclusion set,
touch-list classification, full-SHA pin identity) and prove every drift
class the reviewer named flips verify/--check non-zero. They also prove
the EXECUTABLE candidate gates: the overlay tree (full base tree + 698
candidate blobs) passes all four gates and the narrow tree (698 paths
only, which would delete the rest of main) is rejected. The no-legacy
tooling pin is an external frozen input: both generate and --check
demand --tooling-pin-commit and never read it back from the artifacts.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import generate_acceptance_integration_closure as gic


@pytest.fixture(scope="module")
def closure():
    return gic.build_closure(
        candidate_commit=gic.OLD_CANDIDATE,
        base_commit=gic.MERGE_BASE,
        use_legacy=False,
        tooling_pin=gic.TOOLING_PIN_COMMIT,
    )


def verify_current(value):
    return gic.verify(
        value,
        candidate_commit=gic.OLD_CANDIDATE,
        base_commit=gic.MERGE_BASE,
        use_legacy=False,
        tooling_pin=gic.TOOLING_PIN_COMMIT,
    )


@pytest.fixture(scope="module")
def gate_material(closure):
    base = gic.ls_tree(gic.MERGE_BASE)
    entries = gic.overlay_entries(closure["candidate_data_paths"],
                                  gic.ls_tree(gic.OLD_CANDIDATE), True)
    expected = {e["path"]: e["oid"] for e in entries}
    overlay = gic.build_candidate_overlay_tree(entries, gic.MERGE_BASE)
    narrow = gic.build_narrow_candidate_tree(entries)
    return {"base_tree": base, "entries": entries, "expected": expected,
            "overlay": overlay, "narrow": narrow}


def test_recomputed_closure_verifies_clean(closure):
    assert verify_current(closure) == []


def test_check_passes_on_current_artifacts():
    r = subprocess.run(
        [sys.executable, str(gic.ROOT / "scripts" /
                             "generate_acceptance_integration_closure.py"), "--check",
         "--no-legacy", "--candidate-commit", gic.OLD_CANDIDATE,
         "--base-commit", gic.MERGE_BASE,
         "--tooling-pin-commit", gic.TOOLING_PIN_COMMIT],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_verify_flags_missing_path(closure):
    d = json.loads(json.dumps(closure))
    d["candidate_data_paths"] = d["candidate_data_paths"][1:]
    assert any("missing candidate path" in e for e in verify_current(d))


def test_verify_flags_blob_drift(closure):
    d = json.loads(json.dumps(closure))
    d["candidate_data_paths"][0]["data_blob_oid"] = "0" * 40
    assert any("blob drift" in e or "gate2" in e for e in verify_current(d))


def test_verify_flags_duplicate_path(closure):
    d = json.loads(json.dumps(closure))
    d["candidate_data_paths"].append(dict(d["candidate_data_paths"][0]))
    assert any("duplicate candidate path" in e for e in verify_current(d))


def test_verify_flags_group_imbalance(closure):
    d = json.loads(json.dumps(closure))
    d["candidate_data_paths"][0]["group"] = "other"
    assert any("group" in e for e in verify_current(d))


def test_verify_flags_exclusion_drift(closure):
    d = json.loads(json.dumps(closure))
    over = d["excluded_paths"]["oversized"][0]
    d["candidate_data_paths"].append({
        "path": over["path"],
        "data_blob_oid": over["blob_oid"],
        "size": over["size"],
        "group": "other",
        "refs": 1,
        "present_on_flags_base": False,
        "same_blob_on_flags_base": False,
    })
    assert any("exclusion drift" in e or "gate4" in e for e in verify_current(d))


def test_verify_flags_tooling_blob_drift(closure):
    d = json.loads(json.dumps(closure))
    d["tooling_paths"][0]["tooling_blob_oid"] = "0" * 40
    assert any("tooling blob drift" in e for e in verify_current(d))


def test_nolegacy_tooling_drift_is_rejected(closure):
    """Post-migration mode compares all 17 tooling blobs against HEAD; a
    tampered tooling OID must be rejected (with a valid candidate present)."""
    base = gic.ls_tree(gic.MERGE_BASE)
    entries = gic.overlay_entries(closure["candidate_data_paths"],
                                  gic.ls_tree(gic.OLD_CANDIDATE), True)
    c2 = _make_overlay_commit(entries, gic.MERGE_BASE)
    cl = gic.build_closure(candidate_commit=c2, base_commit=gic.MERGE_BASE,
                           use_legacy=False)
    cl["tooling_paths"][0]["tooling_blob_oid"] = "0" * 40
    errors = gic.verify(cl, candidate_commit=c2, base_commit=gic.MERGE_BASE,
                        use_legacy=False)
    assert any("tooling blob drift" in e for e in errors), errors


def _make_overlay_commit(entries, base):
    """Plumbing-build a real C2-style overlay commit (full base tree +
    candidate blobs) for the executable new-chain production-path test."""
    tree = gic.build_candidate_overlay_tree(entries, base)
    r = subprocess.run(
        ["git", "-C", str(gic.ROOT), "commit-tree", tree, "-p", base, "-m",
         "test overlay C2"],
        capture_output=True, text=True,
        env={**__import__("os").environ,
             "GIT_AUTHOR_NAME": "pytest-scratch",
             "GIT_AUTHOR_EMAIL": "pytest-scratch@example.invalid",
             "GIT_COMMITTER_NAME": "pytest-scratch",
             "GIT_COMMITTER_EMAIL": "pytest-scratch@example.invalid"})
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_nolegacy_closure_self_verifies(closure):
    """The executable step-6b production path: build a real overlay commit
    (the C2 blueprint), regenerate the closure in new-chain mode (candidate
    data from that commit, tooling/infra from HEAD), and verify() must
    pass - including the real-C2 tree gates against the actual commit."""
    base = gic.ls_tree(gic.MERGE_BASE)
    entries = gic.overlay_entries(closure["candidate_data_paths"],
                                  gic.ls_tree(gic.OLD_CANDIDATE), True)
    c2 = _make_overlay_commit(entries, gic.MERGE_BASE)
    cl = gic.build_closure(candidate_commit=c2, base_commit=gic.MERGE_BASE,
                          use_legacy=False)
    assert cl["chain_mode"] == "new_chain"
    assert cl["source"]["tooling_blob_pin_commit"] == gic.resolve_commit("HEAD")
    assert cl["candidate_commit"] == c2
    errors = gic.verify(cl, candidate_commit=c2, base_commit=gic.MERGE_BASE,
                        use_legacy=False)
    assert errors == [], errors


def test_nolegacy_cli_end_to_end(closure, tmp_path, monkeypatch):
    """Real main() end-to-end on TEMP artifact paths (the review-named test
    gap): generate --no-legacy from a plumbing-built overlay C2, --check
    green, a tampered identity field makes --check non-zero, and a simulated
    phase-B artifact-only commit (same tree, new commit SHA) stays green -
    the pin is validated by tree content, never by HEAD equality. A pin
    swap to a content-identical commit must not validate: without an
    explicit pin the check is a usage error (the pin is never read back
    from the disk JSON); with the true phase-A pin the drift is reported."""
    import os
    entries = gic.overlay_entries(closure["candidate_data_paths"],
                                  gic.ls_tree(gic.OLD_CANDIDATE), True)
    c2 = _make_overlay_commit(entries, gic.MERGE_BASE)
    jp = tmp_path / "closure.json"
    mp = tmp_path / "closure.md"
    monkeypatch.setattr(gic, "JSON_PATH", jp)
    monkeypatch.setattr(gic, "MD_PATH", mp)
    phase_a_pin = gic.resolve_commit("HEAD")
    argv_nopin = ["--no-legacy", "--candidate-commit", c2, "--base-commit", gic.MERGE_BASE]
    argv = [*argv_nopin, "--tooling-pin-commit", phase_a_pin]
    assert gic.main(["generate", *argv]) == 0
    assert jp.exists() and mp.exists()
    cl = json.loads(jp.read_text(encoding="utf-8"))
    assert cl["chain_mode"] == "new_chain"
    assert cl["candidate_commit"] == c2
    assert cl["source"]["tooling_blob_pin_commit"] == phase_a_pin
    # step 1/2: the freshly generated artifacts pass --check --no-legacy
    assert gic.main(["--check", *argv]) == 0
    # step 3: tampering an identity field must fail the check (the check
    # recomputes from Git; the disk JSON is never the expected state)
    bad = json.loads(jp.read_text(encoding="utf-8"))
    bad["chain_mode"] = "legacy"
    jp.write_text(gic._canonical(bad), encoding="utf-8")
    assert gic.main(["--check", *argv]) != 0
    # step 4: simulate a phase-B artifact-only commit via plumbing (same
    # tree, new commit SHA) and make "HEAD" resolve to it; the check must
    # stay green because pin != HEAD-commit is allowed while the tooling
    # blobs are three-way identical (pin tree / recorded / HEAD tree).
    jp.write_text(gic._canonical(cl), encoding="utf-8")
    tree = subprocess.run(
        ["git", "-C", str(gic.ROOT), "rev-parse", "HEAD^{tree}"],
        capture_output=True, text=True, check=True).stdout.strip()
    pb = subprocess.run(
        ["git", "-C", str(gic.ROOT), "commit-tree", tree, "-p", "HEAD", "-m",
         "simulated phase-B artifact-only commit"],
        capture_output=True, text=True, check=True,
        env={**os.environ,
             "GIT_AUTHOR_NAME": "pytest-scratch",
             "GIT_AUTHOR_EMAIL": "pytest-scratch@example.invalid",
             "GIT_COMMITTER_NAME": "pytest-scratch",
             "GIT_COMMITTER_EMAIL": "pytest-scratch@example.invalid"}).stdout.strip()
    assert pb != phase_a_pin
    orig_ls = gic.ls_tree

    def wrapped(rev, *a, **k):
        return orig_ls(pb if rev == "HEAD" else rev, *a, **k)

    monkeypatch.setattr(gic, "ls_tree", wrapped)
    assert gic.main(["--check", *argv]) == 0
    # P0 negative: swapping the recorded pin (and every tooling_ref) to a
    # content-identical commit (same tooling tree, different SHA) must
    # never validate. Without an explicit pin the check is a usage error -
    # the pin is never read back from the disk JSON; with the true
    # phase-A pin the drift is reported.
    attack = json.loads(gic._canonical(cl))
    attack["source"]["tooling_blob_pin_commit"] = pb
    for e in attack["tooling_paths"]:
        e["tooling_ref"] = pb
    jp.write_text(gic._canonical(attack), encoding="utf-8")
    assert gic.main(["--check", *argv_nopin]) == 2
    assert gic.main(["--check", *argv]) != 0


def test_nolegacy_requires_explicit_tooling_pin(tmp_path, monkeypatch):
    """P0: in no-legacy mode the tooling pin is an external frozen input.
    Neither generate nor --check may bootstrap it from the disk JSON or
    the runtime HEAD; a missing --tooling-pin-commit is a usage error (2),
    raised before any candidate/pin existence check."""
    jp = tmp_path / "closure.json"
    mp = tmp_path / "closure.md"
    monkeypatch.setattr(gic, "JSON_PATH", jp)
    monkeypatch.setattr(gic, "MD_PATH", mp)
    argv = ["--no-legacy", "--candidate-commit", "0" * 40,
            "--base-commit", gic.MERGE_BASE]
    assert gic.main(["generate", *argv]) == 2
    assert gic.main(["--check", *argv]) == 2


def test_nolegacy_pin_tree_mismatch_is_rejected(closure):
    """A pin whose tree does not carry the recorded tooling blobs is
    rejected even though it is a valid, resolvable commit."""
    entries = gic.overlay_entries(closure["candidate_data_paths"],
                                  gic.ls_tree(gic.OLD_CANDIDATE), True)
    c2 = _make_overlay_commit(entries, gic.MERGE_BASE)
    cl = gic.build_closure(candidate_commit=c2, base_commit=gic.MERGE_BASE,
                           use_legacy=False)
    cl["source"]["tooling_blob_pin_commit"] = gic.MERGE_BASE
    errors = gic.verify(cl, candidate_commit=c2, base_commit=gic.MERGE_BASE,
                        use_legacy=False, tooling_pin=gic.MERGE_BASE)
    assert any(("pin" in e and ("absent" in e or "drift" in e)) for e in errors), errors


def test_nolegacy_missing_pin_commit_is_rejected(closure):
    """A well-formed but absent tooling pin commit is an error, not a skip."""
    entries = gic.overlay_entries(closure["candidate_data_paths"],
                                  gic.ls_tree(gic.OLD_CANDIDATE), True)
    c2 = _make_overlay_commit(entries, gic.MERGE_BASE)
    cl = gic.build_closure(candidate_commit=c2, base_commit=gic.MERGE_BASE,
                           use_legacy=False)
    cl["source"]["tooling_blob_pin_commit"] = "0" * 40
    errors = gic.verify(cl, candidate_commit=c2, base_commit=gic.MERGE_BASE,
                        use_legacy=False, tooling_pin="0" * 40)
    assert any("tooling pin commit missing" in e for e in errors), errors


def test_nolegacy_missing_candidate_generate_raises():
    with pytest.raises(RuntimeError):
        gic.build_closure(candidate_commit="0" * 40,
                          base_commit=gic.MERGE_BASE, use_legacy=False)


def test_nolegacy_missing_base_generate_raises():
    with pytest.raises(RuntimeError):
        gic.build_closure(candidate_commit=gic.OLD_CANDIDATE,
                          base_commit="1" * 40, use_legacy=False)


def test_tooling_pin_commit_is_full_sha_roundtripped():
    assert len(gic.TOOLING_PIN_COMMIT) == 40
    assert gic.resolve_commit(gic.TOOLING_PIN_COMMIT) == gic.TOOLING_PIN_COMMIT


def test_infrastructure_layer_is_migrated(closure):
    layer = closure["integration_infrastructure_layer"]
    assert sorted(e["path"] for e in layer["source_files"]) == sorted(gic.INFRA_SOURCE_PATHS)
    assert sorted(e["path"] for e in layer["generated_artifacts"]) == sorted(gic.GENERATED_OUTPUTS)
    assert closure["migration_total"]["total_paths"] == 17 + 698 + 4


def test_overlay_tree_passes_all_four_gates(gate_material):
    errors = gic.verify_candidate_tree(
        gate_material["entries"], gate_material["expected"],
        gate_material["base_tree"], gic.MERGE_BASE, gate_material["overlay"])
    assert errors == []


def test_overlay_tree_is_deterministic(gate_material):
    again = gic.build_candidate_overlay_tree(gate_material["entries"], gic.MERGE_BASE)
    assert again == gate_material["overlay"]


def test_narrow_tree_is_rejected(gate_material):
    _, deletions, _ = gic._tree_changed_paths(
        gic.MERGE_BASE, gate_material["narrow"])
    assert len(deletions) == 3686
    errors = gic.verify_candidate_tree(
        gate_material["entries"], gate_material["expected"],
        gate_material["base_tree"], gic.MERGE_BASE, gate_material["narrow"])
    assert errors, "narrow (698-only) tree must be rejected"
    assert any("gate1" in e for e in errors)
    assert any("deletes" in e for e in errors)


def test_nolegacy_missing_candidate_is_fail_closed():
    r = subprocess.run(
        [sys.executable, str(gic.ROOT / "scripts" /
                             "generate_acceptance_integration_closure.py"),
         "--check", "--no-legacy",
         "--candidate-commit", "0" * 40,
         "--base-commit", gic.MERGE_BASE,
         "--tooling-pin-commit", gic.TOOLING_PIN_COMMIT],
        capture_output=True, text=True)
    assert r.returncode != 0
    assert ("candidate commit missing" in r.stderr
            or "does not exist" in r.stderr)


def test_missing_flag_value_returns_usage_error():
    r = subprocess.run(
        [sys.executable, str(gic.ROOT / "scripts" /
                             "generate_acceptance_integration_closure.py"),
         "--check", "--candidate-commit"],
        capture_output=True, text=True)
    assert r.returncode == 2
    assert "requires a value" in r.stderr


def test_short_sha_classification_recorded(closure):
    tl = closure["code_freeze_touch_list"]
    assert tl["short_sha_only"] == []
    assert len(tl["binding_full_sha"]) == 13
    assert "tests/test_classic_acceptance_sampling.py" not in [
        e["path"] for e in tl["binding_full_sha"]]


def test_review_e_receipts_are_explicit_touch_scan_outputs(closure):
    receipt = (
        "docs/superpowers/"
        "2026-08-31-classic-texts-review-e-superseding-receipt.md"
    )
    assert gic.touch_scan_excluded(receipt)
    assert not gic.touch_scan_excluded("docs/superpowers/unrelated-receipt.md")
    assert receipt not in [
        e["path"] for e in closure["code_freeze_touch_list"]["binding_full_sha"]
    ]
    assert closure["code_freeze_touch_list"]["audit_output_exclusion_glob"] == (
        "docs/superpowers/*classic-texts-review-e*-receipt.md"
    )


def test_ci_checkouts_fetch_frozen_history_and_tags():
    workflow = (gic.ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert workflow.count("fetch-depth: 0") == 2
    assert workflow.count("fetch-tags: true") == 2
