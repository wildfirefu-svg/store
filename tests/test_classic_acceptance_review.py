"""Tests for the classic-texts manual-acceptance review tooling (design v4.6.1).

Packet, schema validation, adjudication (F3: non_critical finding deleted but
item stays in denominator), decision state machine, final package, and the
section 12 identity/CLI/finalize hard contracts. Unit tests on tiny synthetic
fixtures; the real-packet test reads the frozen candidate commit offline.
"""
import json
import os
import subprocess
import sys
import datetime
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import classic_acceptance_common as c
import classic_acceptance_fixtures as fixtures
import classic_acceptance_sampling as sampling
import classic_acceptance_review as review

_REAL_KILL = os.kill
_REAL_KILLPG = getattr(os, "killpg", None)


def _force_reap_tree(pid):
    """Reap a possibly-leaked CLI tree by its KNOWN root pid, independent of
    the pids JSON and of any monkeypatched fixtures helper. On POSIX the CLI
    runs under start_new_session, so `pid` is also the process GROUP id:
    killpg reaches the whole group (including a surviving grandchild) even
    after the group leader has exited. On Windows taskkill /T walks the child
    tree. Uses the REAL primitives captured at import, so neither an injected
    taskkill nor an injected killpg failure can disable this fallback. Never
    raises (tool timeouts and missing tools are caught), so it is safe to
    call unconditionally in a finally. The bool return is informational
    only; mechanical proof of reaping is a follow-up liveness check."""
    if not pid:
        return False
    if sys.platform == "win32":
        try:
            r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, timeout=10)
            return r.returncode == 0
        except (subprocess.SubprocessError, OSError):
            # TimeoutExpired (hung taskkill), FileNotFoundError (missing
            # taskkill) and other spawn-level OS errors: best effort only.
            return False
    import signal
    reaped = False
    if _REAL_KILLPG is not None:
        try:
            _REAL_KILLPG(int(pid), signal.SIGKILL)
            reaped = True
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        _REAL_KILL(int(pid), signal.SIGKILL)
        reaped = True
    except (ProcessLookupError, PermissionError, OSError):
        pass
    return reaped

@pytest.fixture(scope="module")
def tiny():
    base = fixtures.tmp_dir("acceptance_review_tiny")
    data, chman_path = fixtures.build_tiny_dataset(base)
    man, chman_sha = sampling.load_chapter_manifest(chman_path)
    source = c.DirSource(data)
    sm = sampling.build_sample_manifest(
        man, source, {"kind": "dir", "root": str(data), "test_only": True}, chman_sha)
    yield base, data, chman_path, man, source, sm
    fixtures.rmtree_force(base)


def test_packet_tiny(tiny):
    base, data, chman_path, man, source, sm = tiny
    sm_sha = c.sha256_bytes(c.serialize_json(sm))
    packet = review.build_packet(sm, [], man, source, sm_sha, [],
                                 {"kind": "dir", "root": str(data), "test_only": True})
    assert packet["test_only"] is True
    assert packet["sample_manifest_sha256"] == sm_sha
    assert packet["expansion_manifests_sha256"] == []
    assert len(packet["items"]) == 54
    expected_keys = set()
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                expected_keys.update((book, item_type, i) for i in ids)
    for item_type in ("rule", "mcq"):
        expected_keys.update(("sanmingtonghui", item_type, i)
                             for i in sm["boundary_samples"]["sanmingtonghui"][item_type])
    assert {(e["book"], e["type"], e["id"]) for e in packet["items"]} == expected_keys
    mcq_entries = [e for e in packet["items"] if e["type"] == "mcq"]
    assert all("source_rule" in e for e in mcq_entries)
    assert all(e["source_rule"]["id"] == e["content"]["source_rule_id"] for e in mcq_entries)
    sm_entries = [e for e in packet["items"] if e["book"] == "sanmingtonghui"]
    assert all(e["source_chapter"] in (1, 2, 3, 85) for e in sm_entries)
    assert all(e["boundary"] == (e["source_chapter"] == 1) for e in sm_entries)
    assert set(packet["chapters"]) == {"1", "2", "3", "85"}
    assert packet["chapters"]["1"]["raw_text"].startswith("第1章")
    sm_all = [e for e in packet["items"] if e["book"] == "sanmingtonghui"]
    assert all(e["original_text_in_raw"] for e in sm_all)
    assert packet["integrity"]["source_missing_chapters"] == []
    assert packet["integrity"]["missing_drift_files"] == []
    again = review.build_packet(sm, [], man, source, sm_sha, [],
                                {"kind": "dir", "root": str(data), "test_only": True})
    assert c.serialize_json(again) == c.serialize_json(packet)


def test_packet_cli_tiny(tiny):
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    out = base / "packet_out"
    fixtures.run_cli("classic_acceptance_review.py", "packet",
                     "--sample-manifest", str(sm_path),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(out))
    packet = fixtures.read_json(out / "review_packet_v1.json")
    assert len(packet["items"]) == 54
    assert packet["test_only"] is True
    assert packet["sample_manifest_sha256"] == fixtures.sha256_file(sm_path)


@pytest.fixture(scope="module")
def real_packet():
    man, chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
    sm = sampling.build_sample_manifest(
        man, source, {"kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False},
        chman_sha)
    packet = review.build_packet(
        sm, [], man, source, c.sha256_bytes(c.serialize_json(sm)), [],
        {"kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False})
    return packet, sm


def test_real_packet(real_packet):
    packet, sm = real_packet
    assert packet["test_only"] is False
    assert len(packet["items"]) == 991
    assert [z["chapter_index"] for z in packet["integrity"]["zero_output_chapters"]] == \
        [25, 26, 56, 72, 112]
    assert all(z["raw_exists"] for z in packet["integrity"]["zero_output_chapters"])
    assert packet["integrity"]["source_missing_chapters"] == []
    assert packet["integrity"]["missing_drift_files"] == []
    for e in packet["items"]:
        assert e["content"]["id"] == e["id"]
        if e["type"] == "mcq":
            assert e["source_rule"]["id"] == e["content"]["source_rule_id"]
        if e["book"] == "sanmingtonghui":
            assert packet["chapters"][str(e["source_chapter"])]["raw_text"] is not None
            assert isinstance(e["original_text_in_raw"], bool)
    assert all(ch["raw_text"] is not None for ch in packet["chapters"].values())


def _mini_sample_manifest():
    return {
        "schema_version": "1.0", "kind": "sample_manifest_v1",
        "samples": {
            "sanmingtonghui": {"rule": {"1": ["a", "b"]}, "mcq": {"1": ["m1"]}},
            "qiongtongbaojian": {"rule": {"1": ["q1"]}, "mcq": {"1": []}},
            "ditiansui": {"rule": {"1": []}, "mcq": {"1": []}},
            "zipingzhenquan": {"rule": {"1": []}, "mcq": {"1": []}},
        },
        "boundary_samples": {
            "sanmingtonghui": {"rule": ["x"], "mcq": []},
            "qiongtongbaojian": {"rule": [], "mcq": []},
            "ditiansui": {"rule": [], "mcq": []},
            "zipingzhenquan": {"rule": [], "mcq": []},
        },
    }


def _primary_entry(book, type_, iid, verdict="PASS", findings=None, reviewer="reviewer-1"):
    fs = []
    for f in findings or []:
        f = dict(f)
        # assign (not setdefault): the caller's reviewer must win even when the
        # finding fixture already carries one (F15 outsider rejection test).
        f["reviewer"] = reviewer
        f.setdefault("reviewed_at", "2026-08-23T00:00:00+08:00")
        fs.append(f)
    return {"item": {"book": book, "type": type_, "id": iid, "source_chapter": 1},
            "verdict": verdict, "findings": fs}


def _mini_primary():
    items = [_primary_entry("sanmingtonghui", "rule", "a"),
             _primary_entry("sanmingtonghui", "rule", "b"),
             _primary_entry("sanmingtonghui", "rule", "x"),
             _primary_entry("sanmingtonghui", "mcq", "m1"),
             _primary_entry("qiongtongbaojian", "rule", "q1")]
    return {"schema_version": "1.0", "kind": "primary_review_package",
            "sample_manifest_sha256": "0" * 64, "expansion_manifests_sha256": [],
            "items": items, "overall_stats": {}, "zero_output_report": [],
            "reviewer_list": ["reviewer-1"]}


def _mini_chapter_manifest():
    # Every mini sample id lives in chapter 1 (matches _primary_entry's
    # source_chapter=1); used to exercise the source_chapter identity check.
    return {"schema_version": "1.0",
            "chapters": [{"chapter_index": 1, "rule_ids": ["a", "b", "x"],
                          "mcq_ids": ["m1"]}]}


def test_validate_primary_ok():
    review.validate_primary(_mini_primary(), _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_sha_binding():
    p = _mini_primary()
    p["sample_manifest_sha256"] = "1" * 64
    with pytest.raises(RuntimeError, match="sample manifest"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_coverage_missing_and_extra():
    p = _mini_primary()
    p["items"] = p["items"][:-1]
    with pytest.raises(RuntimeError, match="coverage"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p = _mini_primary()
    p["items"].append(_primary_entry("qiongtongbaojian", "rule", "ghost"))
    with pytest.raises(RuntimeError, match="coverage"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p = _mini_primary()
    p["items"].append(_primary_entry("sanmingtonghui", "rule", "a"))
    with pytest.raises(RuntimeError, match="duplicate"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_verdict_consistency():
    p = _mini_primary()
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "PASS_WITH_MINOR",
                                   [fixtures.minor(), fixtures.minor()])
    review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "PASS", [fixtures.minor()])
    with pytest.raises(RuntimeError, match="inconsistent"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "PASS",
                                   [fixtures.critical()])
    with pytest.raises(RuntimeError, match="inconsistent"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [fixtures.critical(), fixtures.minor()])
    review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_category_and_field_enums():
    p = _mini_primary()
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [{"severity": "critical", "category": "wording",
                                     "evidence_text": "e"}])
    with pytest.raises(RuntimeError, match="critical category"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "MAYBE")
    with pytest.raises(RuntimeError, match="invalid verdict"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [{"severity": "critical", "category": "distortion",
                                     "evidence_text": "  "}])
    with pytest.raises(RuntimeError, match="evidence_text"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [fixtures.critical()])
    p.pop("reviewer_list")
    with pytest.raises(RuntimeError, match="reviewer_list"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_finding_reviewer_must_be_in_list():
    p = _mini_primary()
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [fixtures.critical()], reviewer="outsider")
    with pytest.raises(RuntimeError, match="reviewer"):
        review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_finding_reviewed_at_must_be_iso8601():
    # P0-2: primary finding reviewed_at must be a timezone-qualified ISO-8601
    # timestamp (same standard as second/arbitration); bare non-empty strings
    # like "t" or "yesterday" must fail.
    for bad in ("t", "yesterday", "2026-08-23T00:00:00", "2026-99-99T99:99:99+99:99"):
        p = _mini_primary()
        f = fixtures.critical()
        f["reviewed_at"] = bad
        p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL", [f])
        with pytest.raises(RuntimeError, match="ISO-8601|timezone|valid"):
            review.validate_primary(p, _mini_sample_manifest(), [], "0" * 64, [], _mini_chapter_manifest())


def test_validate_primary_source_chapter_ok_and_tamper():
    # P0: the chapter manifest is MANDATORY (no None/empty bypass), and with
    # it supplied every sanmingtonghui item must carry the SAME source_chapter
    # the manifest assigns to their id; swapping it to another chapter fails
    # closed. Missing or empty chapter manifests are themselves rejected.
    chm = _mini_chapter_manifest()
    review.validate_primary(_mini_primary(), _mini_sample_manifest(),
                            [], "0" * 64, [], chm)
    with pytest.raises(RuntimeError, match="chapter manifest is required"):
        review.validate_primary(_mini_primary(), _mini_sample_manifest(),
                                [], "0" * 64, [], None)
    with pytest.raises(RuntimeError, match="chapter manifest is required"):
        review.validate_primary(_mini_primary(), _mini_sample_manifest(),
                                [], "0" * 64, [], {"chapters": []})
    bad = _mini_primary()
    bad["items"][0]["item"]["source_chapter"] = 2
    with pytest.raises(RuntimeError, match="source_chapter"):
        review.validate_primary(bad, _mini_sample_manifest(), [], "0" * 64, [], chm)


def test_validate_primary_cli_strict(tiny):
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    primary = _mini_primary()
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    entry = _primary_entry(book, item_type, iid)
                    # keep the REAL chapter (id embeds the chapter number);
                    # source_chapter=1 would fail the new identity check.
                    if book == "sanmingtonghui":
                        entry["item"]["source_chapter"] = int(iid.split("_")[1])
                    items.append(entry)
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            entry = _primary_entry("sanmingtonghui", item_type, iid)
            entry["item"]["source_chapter"] = int(iid.split("_")[1])
            items.append(entry)
    primary["items"] = items
    p_path = base / "primary_review_package_v1.json"
    fixtures.write_json(p_path, primary)
    # F18: validate-primary runs the frozen/fake source lock and sample
    # validation, exactly like packet/decide/finalize. Fake happy path:
    fixtures.run_cli("classic_acceptance_review.py", "validate-primary",
                     "--primary", str(p_path), "--sample-manifest", str(sm_path),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data))
    # Missing the mode flag is rejected (exactly one of candidate-commit/data-root):
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "validate-primary",
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(chman_path))
    assert not r.timed_out and r.returncode != 0
    assert "exactly one" in r.stdout + r.stderr


def test_validate_primary_cli_rejects_nonfrozen_chapter_manifest():
    # P0-2 / F18: validate-primary runs the production frozen lock. To prove
    # the lock is the ONLY thing stopping a NON-frozen --chapter-manifest,
    # build the three forged files from the REAL frozen GitSource (same
    # candidate commit the CLI will resolve in production), so they are
    # production-mode self-consistent if the frozen SHA gate were removed:
    # tamper the real chapter manifest (append an empty chapter), rebuild the
    # sample from the tampered manifest against GitSource(COMMIT) (so its
    # chapter_manifest_sha256 and data_file SHAs match), and rebuild the
    # primary to cover that sample with real source chapters. The frozen
    # chapter-manifest SHA gate in verify_frozen_inputs runs before any of
    # that is read, so production still rejects.
    import copy as _copy
    base = fixtures.tmp_dir("vp_nonfrozen_chman")
    try:
        real_man, _ = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
        source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
        git_desc = {"kind": "git", "candidate_commit": fixtures.COMMIT,
                    "test_only": False}
        tampered = _copy.deepcopy(real_man)
        tampered["chapters"] = list(tampered["chapters"]) + [{
            "chapter_index": 9999, "title": "forged", "is_legacy": False,
            "raw_source_path": "forged.txt", "rule_ids": [], "mcq_ids": [],
            "rule_count": 0, "mcq_count": 0, "zero_rule": True, "zero_mcq": True}]
        tampered_chman = base / "tampered_chapter_manifest.json"
        tampered_chman.write_bytes(c.serialize_json(tampered))
        tampered_sha = c.sha256_file_lf(tampered_chman)
        rebuilt_sm = sampling.build_sample_manifest(
            tampered, source, git_desc, tampered_sha)
        sm_path = base / "sample_manifest_forged.json"
        sm_path.write_bytes(c.serialize_json(rebuilt_sm))
        assert rebuilt_sm["chapter_manifest_sha256"] == tampered_sha
        # real source chapters for every sanmingtonghui id in the sample
        chapter_of = {}
        for ch in tampered["chapters"]:
            for iid in ch["rule_ids"] + ch["mcq_ids"]:
                chapter_of[iid] = ch["chapter_index"]
        primary = _mini_primary()
        primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
        items = []
        for book in c.BOOKS:
            for item_type in ("rule", "mcq"):
                for ids in rebuilt_sm["samples"][book][item_type].values():
                    for iid in ids:
                        entry = _primary_entry(book, item_type, iid)
                        if book == "sanmingtonghui":
                            entry["item"]["source_chapter"] = chapter_of[iid]
                        items.append(entry)
        for item_type in ("rule", "mcq"):
            for iid in rebuilt_sm["boundary_samples"]["sanmingtonghui"][item_type]:
                entry = _primary_entry("sanmingtonghui", item_type, iid)
                entry["item"]["source_chapter"] = chapter_of[iid]
                items.append(entry)
        primary["items"] = items
        p_path = base / "primary_forged.json"
        fixtures.write_json(p_path, primary)
        r = fixtures.run_cli_result(
            "classic_acceptance_review.py", "validate-primary",
            "--primary", str(p_path),
            "--sample-manifest", str(sm_path),
            "--chapter-manifest", str(tampered_chman),
            "--candidate-commit", fixtures.COMMIT)
        assert not r.timed_out and r.returncode != 0
        out = r.stdout + r.stderr
        assert "frozen" in out.lower() and "chapter manifest" in out.lower()
    finally:
        fixtures.rmtree_force(base)


def _primary_with_criticals():
    p = _mini_primary()
    p["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                   [fixtures.critical(), fixtures.critical()])
    return p


def _second_receipt(agree0=True, agree1=True, reviewer="reviewer-2"):
    return {"schema_version": "1.0", "kind": "second_review_receipt_v1",
            "primary_sha256": "0" * 64, "reviewer": reviewer,
            "reviewed_at": "2026-08-23T00:00:00+08:00",
            "entries": [
                {"book": "sanmingtonghui", "type": "rule", "id": "a",
                 "finding_index": 0, "first_severity": "critical",
                 "first_category": "distortion", "agree": agree0,
                 "evidence_text": "e", "reviewer": reviewer,
                 "reviewed_at": "2026-08-23T00:00:00+08:00"},
                {"book": "sanmingtonghui", "type": "rule", "id": "a",
                 "finding_index": 1, "first_severity": "critical",
                 "first_category": "distortion", "agree": agree1,
                 "evidence_text": "e", "reviewer": reviewer,
                 "reviewed_at": "2026-08-23T00:00:00+08:00"},
            ]}


def _arb_receipt(decisions, arbitrator="reviewer-3", second_reviewer="reviewer-2",
                 first_reviewer="reviewer-1"):
    return {"schema_version": "1.0", "kind": "arbitration_receipt_v1",
            "primary_sha256": "0" * 64, "second_review_sha256": "1" * 64,
            "reviewer_first": first_reviewer, "reviewer_second": second_reviewer,
            "arbitrator": arbitrator, "reviewed_at": "2026-08-23T00:00:00+08:00",
            "entries": [
                {"book": "sanmingtonghui", "type": "rule", "id": "a",
                 "finding_index": idx, "reviewer_first": first_reviewer,
                 "decision": d, "reasoning": "why", "arbitrator": arbitrator,
                 "reviewed_at": "2026-08-23T00:00:00+08:00"}
                for idx, d in decisions.items()]}


def test_validate_second_ok_and_failures():
    review.validate_second(_second_receipt(), _primary_with_criticals(), "0" * 64)
    bad = _second_receipt()
    bad["primary_sha256"] = "9" * 64
    with pytest.raises(RuntimeError, match="bind the primary"):
        review.validate_second(bad, _primary_with_criticals(), "0" * 64)
    missing = _second_receipt()
    missing["entries"] = missing["entries"][:1]
    with pytest.raises(RuntimeError, match="cover exactly all critical"):
        review.validate_second(missing, _primary_with_criticals(), "0" * 64)
    extra = _second_receipt()
    extra["entries"].append(dict(extra["entries"][0], finding_index=7))
    with pytest.raises(RuntimeError, match="cover exactly all critical"):
        review.validate_second(extra, _primary_with_criticals(), "0" * 64)
    noagree = _second_receipt()
    noagree["entries"][0].pop("agree")
    with pytest.raises(RuntimeError, match="agree"):
        review.validate_second(noagree, _primary_with_criticals(), "0" * 64)
    # second reviewer must differ from every first reviewer (F15)
    same = _second_receipt(reviewer="reviewer-1")
    with pytest.raises(RuntimeError, match="second reviewer"):
        review.validate_second(same, _primary_with_criticals(), "0" * 64)
    review.validate_second({"schema_version": "1.0", "kind": "second_review_receipt_v1",
                            "primary_sha256": "0" * 64, "entries": [],
                            "reviewer": "reviewer-2",
                            "reviewed_at": "2026-08-23T00:00:00+08:00"},
                           _mini_primary(), "0" * 64)
    # reviewed_at must be a timezone-qualified ISO-8601 timestamp (P0-3)
    bad_ts = _second_receipt()
    bad_ts["reviewed_at"] = "t"
    with pytest.raises(RuntimeError, match="ISO-8601"):
        review.validate_second(bad_ts, _primary_with_criticals(), "0" * 64)


def test_validate_arbitration_ok_and_failures():
    second = _second_receipt(agree0=True, agree1=False)
    review.validate_arbitration(_arb_receipt({1: "critical"}),
                                _primary_with_criticals(), second, "0" * 64, "1" * 64)
    review.validate_arbitration(_arb_receipt({1: "non_critical"}),
                                _primary_with_criticals(), second, "0" * 64, "1" * 64)
    bad_bind = _arb_receipt({1: "critical"})
    bad_bind["second_review_sha256"] = "2" * 64
    with pytest.raises(RuntimeError, match="second review"):
        review.validate_arbitration(bad_bind, _primary_with_criticals(), second,
                                     "0" * 64, "1" * 64)
    with pytest.raises(RuntimeError, match="cover exactly all"):
        review.validate_arbitration(_arb_receipt({}), _primary_with_criticals(),
                                     second, "0" * 64, "1" * 64)
    with pytest.raises(RuntimeError, match="decision"):
        review.validate_arbitration(_arb_receipt({1: "maybe"}),
                                     _primary_with_criticals(), second, "0" * 64, "1" * 64)
    # arbitrator must NOT be in primary reviewer_list (global independence, F15)
    bad_arb = _arb_receipt({1: "critical"}, arbitrator="reviewer-1")
    with pytest.raises(RuntimeError, match="arbitrator"):
        review.validate_arbitration(bad_arb, _primary_with_criticals(), second,
                                     "0" * 64, "1" * 64)
    # arbitrator must differ from second reviewer
    bad_arb2 = _arb_receipt({1: "critical"}, arbitrator="reviewer-2")
    with pytest.raises(RuntimeError, match="arbitrator"):
        review.validate_arbitration(bad_arb2, _primary_with_criticals(), second,
                                     "0" * 64, "1" * 64)
    # entry reviewer_first must equal the primary finding's reviewer
    bad_first = _arb_receipt({1: "critical"}, first_reviewer="someone-else")
    with pytest.raises(RuntimeError, match="reviewer_first"):
        review.validate_arbitration(bad_first, _primary_with_criticals(), second,
                                     "0" * 64, "1" * 64)


def test_validate_arbitration_binds_per_finding_reviewer():
    # F21: one item with TWO critical findings reviewed by DIFFERENT first
    # reviewers; arbitration must bind each entry to its own finding's reviewer.
    p = _mini_primary()
    # Build the entry directly (NOT via _primary_entry): that helper forces a
    # single reviewer onto every finding, but F21 needs two findings with
    # DIFFERENT per-finding reviewers to survive.
    p["items"][0] = {"item": {"book": "sanmingtonghui", "type": "rule", "id": "a",
                              "source_chapter": 1},
                     "verdict": "FAIL", "findings": [
                         {"severity": "critical", "category": "distortion",
                          "evidence_text": "e", "reviewer": "r1",
                          "reviewed_at": "2026-08-23T00:00:00+08:00"},
                         {"severity": "critical", "category": "distortion",
                          "evidence_text": "e", "reviewer": "r2",
                          "reviewed_at": "2026-08-23T00:00:00+08:00"}]}
    p["reviewer_list"] = ["r1", "r2"]
    second = {"schema_version": "1.0", "kind": "second_review_receipt_v1",
              "primary_sha256": "0" * 64, "reviewer": "r3",
              "reviewed_at": "2026-08-23T00:00:00+08:00",
              "entries": [
                  {"book": "sanmingtonghui", "type": "rule", "id": "a",
                   "finding_index": 0, "agree": False, "evidence_text": "e",
                   "reviewer": "r3", "reviewed_at": "2026-08-23T00:00:00+08:00"},
                  {"book": "sanmingtonghui", "type": "rule", "id": "a",
                   "finding_index": 1, "agree": False, "evidence_text": "e",
                   "reviewer": "r3", "reviewed_at": "2026-08-23T00:00:00+08:00"}]}
    arb = {"schema_version": "1.0", "kind": "arbitration_receipt_v1",
           "primary_sha256": "0" * 64, "second_review_sha256": "1" * 64,
           "reviewer_second": "r3", "arbitrator": "r4",
           "reviewed_at": "2026-08-23T00:00:00+08:00",
           "entries": [
               {"book": "sanmingtonghui", "type": "rule", "id": "a",
                "finding_index": 0, "reviewer_first": "r1",
                "decision": "critical", "reasoning": "why", "arbitrator": "r4",
                "reviewed_at": "2026-08-23T00:00:00+08:00"},
               {"book": "sanmingtonghui", "type": "rule", "id": "a",
                "finding_index": 1, "reviewer_first": "r2",
                "decision": "non_critical", "reasoning": "why", "arbitrator": "r4",
                "reviewed_at": "2026-08-23T00:00:00+08:00"}]}
    review.validate_arbitration(arb, p, second, "0" * 64, "1" * 64)  # passes
    # if entry 1 wrongly claims reviewer r1 (instead of its actual r2), fail
    arb["entries"][1]["reviewer_first"] = "r1"
    with pytest.raises(RuntimeError, match="reviewer_first"):
        review.validate_arbitration(arb, p, second, "0" * 64, "1" * 64)


def test_validate_arbitration_rejects_bad_timestamp():
    second = _second_receipt(agree0=False, agree1=True)
    bad = _arb_receipt({0: "critical"})
    bad["reviewed_at"] = "not-a-timestamp"
    with pytest.raises(RuntimeError, match="ISO-8601"):
        review.validate_arbitration(bad, _primary_with_criticals(), second,
                                     "0" * 64, "1" * 64)


def test_critical_and_disagreement_refs():
    assert review.critical_refs(_primary_with_criticals()) == {
        ("sanmingtonghui", "rule", "a", 0), ("sanmingtonghui", "rule", "a", 1)}
    assert review.critical_refs(_mini_primary()) == set()
    second = _second_receipt(agree0=True, agree1=False)
    assert review.disagreement_refs(second) == {("sanmingtonghui", "rule", "a", 1)}


def test_validate_arbitration_rejects_arbitrator_in_reviewer_list_without_findings():
    # P0-1: design section 12.3 requires the arbitrator to be absent from the
    # ENTIRE primary.reviewer_list, even if that reviewer produced no finding.
    p = _primary_with_criticals()
    p["reviewer_list"] = ["reviewer-1", "reviewer-3"]  # reviewer-3 never reviews
    second = _second_receipt(agree0=True, agree1=False)
    bad = _arb_receipt({1: "critical"}, arbitrator="reviewer-3")
    with pytest.raises(RuntimeError, match="arbitrator"):
        review.validate_arbitration(bad, p, second, "0" * 64, "1" * 64)


def test_validate_second_cli_fake_ok(tiny):
    base, data, chman_path, man, source, sm = tiny
    p = _primary_with_criticals()
    p_path = base / "primary.json"
    fixtures.write_json(p_path, p)
    s = _second_receipt()
    s["primary_sha256"] = fixtures.sha256_file(p_path)
    s_path = base / "second.json"
    fixtures.write_json(s_path, s)
    fixtures.run_cli("classic_acceptance_review.py", "validate-second",
                     "--second", str(s_path), "--primary", str(p_path),
                     "--data-root", str(data))


def test_validate_arbitration_cli_fake_ok(tiny):
    base, data, chman_path, man, source, sm = tiny
    p = _primary_with_criticals()
    p_path = base / "primary.json"
    fixtures.write_json(p_path, p)
    s = _second_receipt(agree0=True, agree1=False)
    s["primary_sha256"] = fixtures.sha256_file(p_path)
    s_path = base / "second.json"
    fixtures.write_json(s_path, s)
    a = _arb_receipt({1: "critical"})
    a["primary_sha256"] = fixtures.sha256_file(p_path)
    a["second_review_sha256"] = fixtures.sha256_file(s_path)
    a_path = base / "arbitration.json"
    fixtures.write_json(a_path, a)
    fixtures.run_cli("classic_acceptance_review.py", "validate-arbitration",
                     "--arbitration", str(a_path), "--primary", str(p_path),
                     "--second", str(s_path), "--data-root", str(data))


def test_validate_second_cli_rejects_nonfrozen_chapter_manifest():
    # P0-2/F18: validate-second runs the production frozen lock BEFORE reading
    # any receipt. Use NONEXISTENT receipts: the frozen chapter-manifest error
    # must still surface first, proving lock-then-read ordering.
    import copy as _copy
    base = fixtures.tmp_dir("vs_nonfrozen_chman")
    try:
        real_man, _ = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
        tampered = _copy.deepcopy(real_man)
        tampered["chapters"] = list(tampered["chapters"]) + [{
            "chapter_index": 9999, "title": "forged", "is_legacy": False,
            "raw_source_path": "forged.txt", "rule_ids": [], "mcq_ids": [],
            "rule_count": 0, "mcq_count": 0, "zero_rule": True, "zero_mcq": True}]
        tampered_chman = base / "tampered_chapter_manifest.json"
        tampered_chman.write_bytes(c.serialize_json(tampered))
        # Point --second/--primary at NONEXISTENT files: if the implementation
        # read receipts before the frozen lock, a file-not-found error would
        # surface instead; the frozen chapter-manifest error must come first.
        missing = base / "missing.json"
        r = fixtures.run_cli_result(
            "classic_acceptance_review.py", "validate-second",
            "--second", str(missing), "--primary", str(missing),
            "--chapter-manifest", str(tampered_chman),
            "--candidate-commit", fixtures.COMMIT)
        assert not r.timed_out and r.returncode != 0
        out = r.stdout + r.stderr
        assert "frozen" in out.lower() and "chapter manifest" in out.lower()
        assert "No such file" not in out and "FileNotFoundError" not in out
    finally:
        fixtures.rmtree_force(base)


def test_validate_arbitration_cli_rejects_nonfrozen_chapter_manifest():
    # P0-2/F18: validate-arbitration runs the production frozen lock BEFORE
    # reading any receipt/primary. Use NONEXISTENT receipts: the frozen
    # chapter-manifest error must still surface first (lock-then-read order).
    import copy as _copy
    base = fixtures.tmp_dir("va_nonfrozen_chman")
    try:
        real_man, _ = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
        tampered = _copy.deepcopy(real_man)
        tampered["chapters"] = list(tampered["chapters"]) + [{
            "chapter_index": 9999, "title": "forged", "is_legacy": False,
            "raw_source_path": "forged.txt", "rule_ids": [], "mcq_ids": [],
            "rule_count": 0, "mcq_count": 0, "zero_rule": True, "zero_mcq": True}]
        tampered_chman = base / "tampered_chapter_manifest.json"
        tampered_chman.write_bytes(c.serialize_json(tampered))
        # Point --arbitration/--primary/--second at NONEXISTENT files: if the
        # implementation read receipts before the frozen lock, a file-not-found
        # error would surface instead; frozen chapter-manifest error comes first.
        missing = base / "missing.json"
        r = fixtures.run_cli_result(
            "classic_acceptance_review.py", "validate-arbitration",
            "--arbitration", str(missing),
            "--primary", str(missing), "--second", str(missing),
            "--chapter-manifest", str(tampered_chman),
            "--candidate-commit", fixtures.COMMIT)
        assert not r.timed_out and r.returncode != 0
        out = r.stdout + r.stderr
        assert "frozen" in out.lower() and "chapter manifest" in out.lower()
        assert "No such file" not in out and "FileNotFoundError" not in out
    finally:
        fixtures.rmtree_force(base)


def test_validate_second_cli_rejects_unknown_flag(tiny):
    base, data, chman_path, man, source, sm = tiny
    p = _primary_with_criticals()
    p_path = base / "primary.json"
    fixtures.write_json(p_path, p)
    s = _second_receipt()
    s["primary_sha256"] = fixtures.sha256_file(p_path)
    s_path = base / "second.json"
    fixtures.write_json(s_path, s)
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "validate-second",
        "--second", str(s_path), "--primary", str(p_path),
        "--data-root", str(data), "--bogus", "x")
    assert not r.timed_out and r.returncode != 0
    assert "unknown flag" in r.stdout + r.stderr


def test_validate_arbitration_cli_rejects_unknown_flag(tiny):
    base, data, chman_path, man, source, sm = tiny
    p = _primary_with_criticals()
    p_path = base / "primary.json"
    fixtures.write_json(p_path, p)
    s = _second_receipt(agree0=True, agree1=False)
    s["primary_sha256"] = fixtures.sha256_file(p_path)
    s_path = base / "second.json"
    fixtures.write_json(s_path, s)
    a = _arb_receipt({1: "critical"})
    a["primary_sha256"] = fixtures.sha256_file(p_path)
    a["second_review_sha256"] = fixtures.sha256_file(s_path)
    a_path = base / "arbitration.json"
    fixtures.write_json(a_path, a)
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "validate-arbitration",
        "--arbitration", str(a_path),
        "--primary", str(p_path), "--second", str(s_path),
        "--data-root", str(data), "--bogus", "x")
    assert not r.timed_out and r.returncode != 0
    assert "unknown flag" in r.stdout + r.stderr


def test_canonicalize_deletes_noncritical_keeps_item_in_denominator():
    primary = _mini_primary()
    primary["items"][0] = _primary_entry(
        "sanmingtonghui", "rule", "a", "FAIL",
        [fixtures.critical(), fixtures.critical(), fixtures.minor()])
    second = _second_receipt(agree0=True, agree1=False)
    arb = _arb_receipt({1: "non_critical"})
    canonical = review.canonicalize(primary, second, arb)
    a_findings = [f for f in canonical
                  if (f["book"], f["type"], f["id"]) == ("sanmingtonghui", "rule", "a")]
    # finding 0 stays critical; finding 1 DELETED (not retagged minor); finding 2 minor
    assert {f["finding_index"] for f in a_findings} == {0, 2}
    assert a_findings[0]["severity"] == "critical"
    assert a_findings[0]["state"] == "ADJUDICATED_CRITICAL"
    assert a_findings[1]["severity"] == "minor"
    assert a_findings[1]["state"] == "PRIMARY_MINOR"
    # item still FAIL because finding 0 remains critical
    verdicts = review.item_verdicts(canonical)
    assert verdicts[("sanmingtonghui", "rule", "a")] == "FAIL"


def test_canonicalize_downgraded_solo_finding_becomes_pass():
    primary = _mini_primary()
    primary["items"][0] = _primary_entry("sanmingtonghui", "rule", "a", "FAIL",
                                         [fixtures.critical()])
    second = _second_receipt(agree0=False, agree1=False)
    arb = _arb_receipt({0: "non_critical"})
    canonical = review.canonicalize(primary, second, arb)
    assert canonical == []                       # deleted, no remaining findings
    verdicts = review.item_verdicts(canonical)
    assert ("sanmingtonghui", "rule", "a") not in verdicts   # no FAIL, no minor-only
    # BUT the item remains in the reviewed denominator (F3)
    # (compute_metrics counts all reviewed items, not just verdict keys)


def test_canonicalize_missing_receipts_fail_closed():
    primary = _primary_with_criticals()
    with pytest.raises(RuntimeError, match="lacks a second-review entry"):
        review.canonicalize(primary, None, None)
    second = _second_receipt(agree0=False, agree1=False)
    with pytest.raises(RuntimeError, match="lacks an arbitration entry"):
        review.canonicalize(primary, second, None)


def test_item_meta_map_and_metrics_keeps_deleted_finding_in_denominator():
    sm = _mini_sample_manifest()
    chman = {"chapters": [
        {"chapter_index": 1, "rule_ids": ["x"], "mcq_ids": []},
        {"chapter_index": 2, "rule_ids": ["a", "b"], "mcq_ids": ["m1"]},
    ]}
    meta = review.item_meta_map(sm, [], chman)
    assert meta[("sanmingtonghui", "rule", "x")] == {"stratum": 1, "boundary": True}
    # item 'a' has a deleted critical (no verdict key) -> PASS, but still reviewed
    verdicts = {("sanmingtonghui", "mcq", "m1"): "PASS_WITH_MINOR"}
    metrics, stratum_rule, boundary_crit = review.compute_metrics(verdicts, meta)
    assert metrics[("sanmingtonghui", "rule")] == {
        "reviewed": 3, "critical_items": 0, "minor_only_items": 0}  # denominator 3 kept
    assert metrics[("sanmingtonghui", "mcq")] == {
        "reviewed": 1, "critical_items": 0, "minor_only_items": 1}
    assert stratum_rule[("sanmingtonghui", 1)] == {"reviewed": 3, "critical_items": 0}


def test_integrity_check():
    base = fixtures.tmp_dir("acceptance_integrity")
    try:
        man = {"chapters": [
            {"chapter_index": 25, "rule_ids": [], "mcq_ids": [],
             "raw_source_path": "raw/25.txt", "zero_rule": True, "zero_mcq": True},
            {"chapter_index": 26, "rule_ids": ["r1"], "mcq_ids": [],
             "raw_source_path": "raw/26.txt", "zero_rule": False, "zero_mcq": True},
        ]}
        (base / "raw").mkdir(parents=True)
        for ci in (25, 26):
            (base / "raw" / f"{ci}.txt").write_text("原文", encoding="utf-8")
        for p in c.DRIFT_FILES:
            q = base / p
            q.parent.mkdir(parents=True, exist_ok=True)
            q.write_text("{}", encoding="utf-8")
        src = c.DirSource(base)
        res = review.integrity_check(man, src)
        assert res["source_missing_chapters"] == []
        assert res["missing_drift_files"] == []
        (base / "raw" / "25.txt").unlink()
        res = review.integrity_check(man, src)
        assert res["source_missing_chapters"] == [25]
        (base / c.DRIFT_FILES[1]).unlink()
        res = review.integrity_check(man, src)
        assert res["missing_drift_files"] == [c.DRIFT_FILES[1]]
    finally:
        fixtures.rmtree_force(base)


def _m(reviewed, critical, minor=0):
    return {"reviewed": reviewed, "critical_items": critical, "minor_only_items": minor}


CLEAN = {"source_missing_chapters": [], "missing_drift_files": []}


def test_decide_state_edges():
    s = review.decide_state({("b", "rule"): _m(100, 2)}, {}, {}, CLEAN, [])
    assert s["verdict"] == "ACCEPT"
    s = review.decide_state({("b", "rule"): _m(100, 3)}, {}, {}, CLEAN, [])
    assert s["verdict"] == "EXPAND"
    assert s["pending_expands"] == [{"book": "b", "type": "rule"}]
    s = review.decide_state({("b", "rule"): _m(100, 5)}, {}, {}, CLEAN, [])
    assert s["verdict"] == "EXPAND"
    s = review.decide_state({("b", "rule"): _m(100, 6)}, {}, {}, CLEAN, [])
    assert s["verdict"] == "REJECT" and s["fired_rules"] == ["REJECT_GATE"]
    s = review.decide_state({("b", "rule"): _m(100, 3)}, {}, {}, CLEAN,
                            [{"book": "b", "type": "rule"}])
    assert s["verdict"] == "REJECT" and s["fired_rules"] == ["EXPAND_GATE"]
    s = review.decide_state({("b", "rule"): _m(200, 4)}, {}, {}, CLEAN,
                            [{"book": "b", "type": "rule"}])
    assert s["verdict"] == "ACCEPT"


def test_decide_state_priority_order():
    s = review.decide_state({("b", "rule"): _m(100, 50)},
                            {("b", 2): {"reviewed": 7, "critical_items": 1}},
                            {("b", "rule"): 1}, CLEAN, [])
    assert s["fired_rules"] == ["BOUNDARY"]
    s = review.decide_state({("b", "rule"): _m(100, 1)},
                            {("b", 2): {"reviewed": 7, "critical_items": 1}},
                            {}, CLEAN, [])
    assert s["fired_rules"] == ["STRATUM_CASCADE"]
    s = review.decide_state({("b", "rule"): _m(100, 50)},
                            {("b", 2): {"reviewed": 7, "critical_items": 1}},
                            {("b", "rule"): 3},
                            {"source_missing_chapters": [25],
                             "missing_drift_files": []}, [])
    assert s["fired_rules"] == ["INTEGRITY"]


def test_check_receipt_requirements_gate():
    # F22: no criticals -> no receipts allowed
    assert review.check_receipt_requirements(False, False, False, False) == (False, False)
    with pytest.raises(RuntimeError, match="not allowed"):
        review.check_receipt_requirements(False, False, True, False)
    with pytest.raises(RuntimeError, match="not allowed"):
        review.check_receipt_requirements(False, False, False, True)
    # criticals but second missing -> required
    with pytest.raises(RuntimeError, match="required"):
        review.check_receipt_requirements(True, False, False, False)
    # criticals, no disagreement -> second required, arbitration forbidden
    assert review.check_receipt_requirements(True, False, True, False) == (True, False)
    with pytest.raises(RuntimeError, match="not allowed"):
        review.check_receipt_requirements(True, False, True, True)
    # criticals, disagreement -> both required
    assert review.check_receipt_requirements(True, True, True, True) == (True, True)
    with pytest.raises(RuntimeError, match="required"):
        review.check_receipt_requirements(True, True, True, False)


def _tiny_all_pass_primary(sm):
    # all-PASS primary over the full tiny sample. sanmingtonghui items must
    # carry their REAL chapter (the id embeds the chapter number) so the new
    # source_chapter identity check in validate_primary passes; _primary_entry
    # defaults to 1, which would fail once chapter 2/3/85 items are checked.
    primary = _mini_primary()
    items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    entry = _primary_entry(book, item_type, iid)
                    if book == "sanmingtonghui":
                        entry["item"]["source_chapter"] = int(iid.split("_")[1])
                    items.append(entry)
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            entry = _primary_entry("sanmingtonghui", item_type, iid)
            entry["item"]["source_chapter"] = int(iid.split("_")[1])
            items.append(entry)
    primary["items"] = items
    return primary


def test_validate_decision_inputs_shared_path_and_f22_gate(tiny):
    # P0-2: the shared helper both computes the verdict and enforces the F22
    # receipt gate; cmd_decide and cmd_expand call the SAME function.
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = base / "primary.json"
    fixtures.write_json(p_path, primary)
    ch_manifest, _ = sampling.load_chapter_manifest(chman_path)
    # all-PASS -> ACCEPT
    _, _, _, report = review.validate_decision_inputs(
        sm, [], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [], True,
        p_path, None, None)
    assert report["verdict"] == "ACCEPT"
    # P0-2: decision report must carry its data-source identity (design §12.2)
    assert report["data_source"] == desc
    # an unrequired arbitration receipt is rejected by the F22 gate even
    # though arbitration validation would otherwise accept it
    arb = _arb_receipt({}, arbitrator="r3")
    arb_path = base / "arb.json"
    fixtures.write_json(arb_path, arb)
    with pytest.raises(RuntimeError, match="not allowed"):
        review.validate_decision_inputs(
            sm, [], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [], True,
            p_path, None, arb_path)


def test_verify_producing_report_rejects_handcrafted_expand(tiny):
    # P0-1: an expansion consumer recomputes the producing verdict from the
    # R1 primary/second/arbitration; a hand-crafted EXPAND report for an
    # all-PASS primary (real verdict ACCEPT) is rejected.
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = base / "primary.json"
    fixtures.write_json(p_path, primary)
    ch_manifest, _ = sampling.load_chapter_manifest(chman_path)
    _, _, _, real = review.validate_decision_inputs(
        sm, [], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [], True,
        p_path, None, None)
    assert real["verdict"] == "ACCEPT"
    # forged report: binds the real primary/sample but claims EXPAND
    forged = dict(real, verdict="EXPAND", fired_rules=["EXPAND_GATE"],
                  pending_expands=[{"book": "sanmingtonghui", "type": "rule"}])
    r_path = base / "forged_report.json"
    fixtures.write_json(r_path, forged)
    with pytest.raises(RuntimeError, match="recomputed"):
        review.verify_producing_report(
            r_path, sm, fixtures.sha256_file(sm_path), ch_manifest, source, desc, True,
            p_path, None, None)
    # the genuine ACCEPT report is also rejected (verdict is not EXPAND)
    real_path = base / "real_report.json"
    fixtures.write_json(real_path, real)
    with pytest.raises(RuntimeError, match="not EXPAND"):
        review.verify_producing_report(
            real_path, sm, fixtures.sha256_file(sm_path), ch_manifest, source, desc, True,
            p_path, None, None)


def test_verify_producing_report_reads_report_once(tiny, monkeypatch):
    # P0-3: verify_producing_report must read the report path exactly ONCE.
    # Simulate an in-place file swap on a second read: if the implementation
    # re-read for the parsed object/SHA, the swapped bytes would be used and
    # the byte-equality verdict would rest on a different file version.
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = base / "primary.json"
    fixtures.write_json(p_path, primary)
    ch_manifest, _ = sampling.load_chapter_manifest(chman_path)
    _, _, _, real = review.validate_decision_inputs(
        sm, [], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [], True,
        p_path, None, None)
    forged = dict(real, verdict="EXPAND", fired_rules=["EXPAND_GATE"],
                  pending_expands=[{"book": "sanmingtonghui", "type": "rule"}])
    r_path = base / "forged_report.json"
    fixtures.write_json(r_path, forged)
    reads = []
    orig_read_bytes = Path.read_bytes

    def counting_read(self, *a, **k):
        if str(self) == str(r_path):
            reads.append(1)
            if len(reads) >= 2:
                return b'{"kind": "swapped"}'   # simulate a mid-check file swap
        return orig_read_bytes(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", counting_read)
    with pytest.raises(RuntimeError, match="recomputed"):
        review.verify_producing_report(
            r_path, sm, fixtures.sha256_file(sm_path), ch_manifest, source, desc, True,
            p_path, None, None)
    assert len(reads) == 1   # exactly one read of the report path


def _real_all_pass_primary(sm, sm_path, chapter_manifest):
    # Generic all-PASS primary over a real/frozen sample: sanmingtonghui items
    # keep their REAL chapter from the chapter manifest (real ids do NOT embed
    # the chapter number, so we cannot parse it from the id).
    chapter_of = {}
    for ch in chapter_manifest["chapters"]:
        for iid in ch["rule_ids"] + ch["mcq_ids"]:
            chapter_of[iid] = ch["chapter_index"]
    items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    sc = chapter_of[iid] if book == "sanmingtonghui" else 1
                    items.append({"item": {"book": book, "type": item_type, "id": iid,
                                           "source_chapter": sc},
                                  "verdict": "PASS", "findings": []})
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            items.append({"item": {"book": "sanmingtonghui", "type": item_type,
                                   "id": iid, "source_chapter": chapter_of[iid]},
                          "verdict": "PASS", "findings": []})
    return {"schema_version": "1.0", "kind": "primary_review_package",
            "sample_manifest_sha256": c.sha256_file_raw(sm_path),
            "expansion_manifests_sha256": [], "items": items,
            "overall_stats": {}, "zero_output_report": [],
            "reviewer_list": ["r1"]}


def test_verify_producing_report_success_returns_pinned_sha(tiny, monkeypatch):
    # P0: SUCCESS path -- a genuine EXPAND report must return (report, report_sha)
    # where report_sha is the SHA of the FIRST read's raw bytes, and the report
    # path is read exactly ONCE (a swapped file on a second read is never seen).
    base, data, chman_path, man, source, sm = tiny
    # custom sample: qiongtongbaojian rule with 40 reviewed items -> 2/40 = 5%
    # critical rate lands in the EXPAND band (2%, 5%]; no other category matters.
    custom_sm = {
        "schema_version": "1.0", "kind": "sample_manifest_v1",
        "samples": {
            "sanmingtonghui": {"rule": {"1": []}, "mcq": {"1": []}},
            "qiongtongbaojian": {"rule": {"1": [f"q{i:03d}" for i in range(40)]},
                                 "mcq": {"1": []}},
            "ditiansui": {"rule": {"1": []}, "mcq": {"1": []}},
            "zipingzhenquan": {"rule": {"1": []}, "mcq": {"1": []}},
        },
        "boundary_samples": {
            "sanmingtonghui": {"rule": [], "mcq": []},
            "qiongtongbaojian": {"rule": [], "mcq": []},
            "ditiansui": {"rule": [], "mcq": []},
            "zipingzhenquan": {"rule": [], "mcq": []},
        },
    }
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(custom_sm))
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    primary = {"schema_version": "1.0", "kind": "primary_review_package",
               "sample_manifest_sha256": fixtures.sha256_file(sm_path),
               "expansion_manifests_sha256": [],
               "overall_stats": {}, "zero_output_report": [],
               "reviewer_list": ["reviewer-1"],
               "items": [
                   {"item": {"book": "qiongtongbaojian", "type": "rule", "id": f"q{i:03d}",
                             "source_chapter": 1},
                    "verdict": ("FAIL" if i < 2 else "PASS"),
                    "findings": ([fixtures.critical()] if i < 2 else [])}
                   for i in range(40)]}
    p_path = base / "primary.json"
    fixtures.write_json(p_path, primary)
    second = {"schema_version": "1.0", "kind": "second_review_receipt_v1",
              "primary_sha256": fixtures.sha256_file(p_path),
              "reviewer": "reviewer-2",
              "reviewed_at": "2026-08-23T00:00:00+08:00",
              "entries": [
                  {"book": "qiongtongbaojian", "type": "rule", "id": f"q{i:03d}",
                   "finding_index": 0, "agree": True, "evidence_text": "e",
                   "reviewer": "reviewer-2",
                   "reviewed_at": "2026-08-23T00:00:00+08:00"}
                  for i in range(2)]}
    s_path = base / "second.json"
    fixtures.write_json(s_path, second)
    ch_manifest, _ = sampling.load_chapter_manifest(chman_path)
    _, _, _, report = review.validate_decision_inputs(
        custom_sm, [], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [], True,
        p_path, s_path, None)
    assert report["verdict"] == "EXPAND"
    r_path = base / "expand_report.json"
    fixtures.write_json(r_path, report)
    original_bytes = Path(r_path).read_bytes()
    expected_sha = c.sha256_bytes(original_bytes)
    reads = []
    orig_read_bytes = Path.read_bytes

    def counting_read(self, *a, **k):
        if str(self) == str(r_path):
            reads.append(1)
            if len(reads) >= 2:
                return b'{"kind": "swapped"}'
        return orig_read_bytes(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", counting_read)
    rep, rep_sha = review.verify_producing_report(
        r_path, custom_sm, fixtures.sha256_file(sm_path), ch_manifest, source, desc, True,
        p_path, s_path, None)
    assert rep["verdict"] == "EXPAND"
    assert rep["kind"] == "decision_report_v1"
    assert rep_sha == expected_sha        # SHA pinned to the first read's bytes
    assert reads == [1]                    # success path reads the report once


def test_decide_production_report_data_source():
    # P0-2 (production): a production decision report carries test_only=False
    # and the git data-source identity (design section 12.2).
    base = fixtures.tmp_dir("decide_prod_ds")
    try:
        man, chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
        source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
        git_desc = {"kind": "git", "candidate_commit": fixtures.COMMIT,
                    "test_only": False}
        sm = sampling.build_sample_manifest(man, source, git_desc, chman_sha)
        sm_path = base / "sample_manifest_v1.json"
        sm_path.write_bytes(c.serialize_json(sm))
        primary = _real_all_pass_primary(sm, sm_path, man)
        p_path = base / "primary.json"
        fixtures.write_json(p_path, primary)
        _, _, _, report = review.validate_decision_inputs(
            sm, [], man, source, git_desc, fixtures.sha256_file(sm_path), [], False,
            p_path, None, None)
        assert report["verdict"] == "ACCEPT"
        assert report["test_only"] is False
        assert report["data_source"] == {
            "kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False}
    finally:
        fixtures.rmtree_force(base)


def test_validate_decision_inputs_uses_pinned_expansion_sha(tiny):
    # P0: validate_decision_inputs receives expansion_shas (pinned by the
    # caller's single read) and NEVER re-opens the expansion file; the report
    # binds exactly those pinned SHAs, and a tampered pinned sha fails closed.
    base, data, chman_path, man, source, sm = tiny
    custom_sm = {
        "schema_version": "1.0", "kind": "sample_manifest_v1",
        "samples": {
            "sanmingtonghui": {"rule": {"1": []}, "mcq": {"1": []}},
            "qiongtongbaojian": {"rule": {"1": [f"q{i:03d}" for i in range(40)]},
                                 "mcq": {"1": []}},
            "ditiansui": {"rule": {"1": []}, "mcq": {"1": []}},
            "zipingzhenquan": {"rule": {"1": []}, "mcq": {"1": []}},
        },
        "boundary_samples": {
            "sanmingtonghui": {"rule": [], "mcq": []},
            "qiongtongbaojian": {"rule": [], "mcq": []},
            "ditiansui": {"rule": [], "mcq": []},
            "zipingzhenquan": {"rule": [], "mcq": []},
        },
    }
    em = {"schema_version": "1.0", "kind": "expansion_manifest_v1",
          "round": 1, "expanded_pairs": [{"book": "qiongtongbaojian", "type": "rule"}],
          "expansions": {"qiongtongbaojian": {"rule": {
              "1": {"new_ids": ["q040", "q041"]}}}},
          "totals": {"qiongtongbaojian": {"rule": 2}}}
    em_bytes = c.serialize_json(em)
    em_sha = c.sha256_bytes(em_bytes)
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(custom_sm))
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    primary = {"schema_version": "1.0", "kind": "primary_review_package",
               "sample_manifest_sha256": fixtures.sha256_file(sm_path),
               "expansion_manifests_sha256": [em_sha],
               "overall_stats": {}, "zero_output_report": [],
               "reviewer_list": ["reviewer-1"],
               "items": [
                   {"item": {"book": "qiongtongbaojian", "type": "rule",
                             "id": f"q{i:03d}", "source_chapter": 1},
                    "verdict": "PASS", "findings": []}
                   for i in range(42)]}
    p_path = base / "primary.json"
    fixtures.write_json(p_path, primary)
    ch_manifest, _ = sampling.load_chapter_manifest(chman_path)
    _, _, _, report = review.validate_decision_inputs(
        custom_sm, [em], ch_manifest, source, desc, fixtures.sha256_file(sm_path), [em_sha], True,
        p_path, None, None)
    # the report binds the PINNED sha; no expansion file was ever re-opened
    assert report["expansion_manifests_sha256"] == [em_sha]
    # a tampered pinned sha is rejected by the binding check (proves the
    # pinned value is authoritative, not a re-read)
    with pytest.raises(RuntimeError, match="expansion_manifests_sha256 mismatch"):
        review.validate_decision_inputs(
            custom_sm, [em], ch_manifest, source, desc, fixtures.sha256_file(sm_path), ["0" * 64], True,
            p_path, None, None)


def _vp_base_cmd(tiny, run_name):
    # Shared happy-path base (fake source, valid sample + all-PASS primary)
    # for the validate-primary expansion-authorization CLI gate tests. These
    # never reach producing-report recomputation or expansion reconstruction,
    # so the expansion/evidence paths may point at dummy files.
    base, data, chman_path, man, source, sm = tiny
    run = base / run_name
    run.mkdir(parents=True, exist_ok=True)
    sm_path = run / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = run / "primary.json"
    fixtures.write_json(p_path, primary)
    dummy = run / "dummy.json"
    fixtures.write_json(dummy, {"kind": "whatever"})
    return [sys.executable, str(fixtures.SCRIPTS / "classic_acceptance_review.py"),
            "validate-primary",
            "--primary", str(p_path), "--sample-manifest", str(sm_path),
            "--chapter-manifest", str(chman_path), "--data-root", str(data)], dummy


def test_validate_primary_cli_rejects_expansion_without_producing_evidence(tiny):
    # P0/F19: --expansion-manifest requires the R1 evidence bundle
    # (--decision-report + --producing-primary); without it the expansion is
    # rejected by check_producing_evidence_presence, not silently accepted.
    cmd, dummy = _vp_base_cmd(tiny, "vp_no_evidence")
    result = fixtures.run_cli_result(
        Path(cmd[1]).name, *cmd[2:], "--expansion-manifest", str(dummy))
    assert not result.timed_out and result.returncode != 0
    assert "requires --decision-report" in (result.stdout + result.stderr)


def test_validate_primary_cli_rejects_duplicate_expansion(tiny):
    # P0/F19: at most one expansion is allowed (only one parallel expansion
    # round exists); a second --expansion-manifest is rejected by the strict
    # flag parser before any data is read.
    cmd, dummy = _vp_base_cmd(tiny, "vp_dup_exp")
    result = fixtures.run_cli_result(
        Path(cmd[1]).name, *cmd[2:],
        "--expansion-manifest", str(dummy), "--expansion-manifest", str(dummy))
    assert not result.timed_out and result.returncode != 0
    assert "at most once" in (result.stdout + result.stderr)


def test_validate_primary_cli_rejects_orphaned_producing_evidence(tiny):
    # Medium/F19: producing-evidence flags without --expansion-manifest are
    # orphaned (they would otherwise be silently ignored); rejected.
    cmd, dummy = _vp_base_cmd(tiny, "vp_orphan")
    result = fixtures.run_cli_result(
        Path(cmd[1]).name, *cmd[2:],
        "--decision-report", str(dummy), "--producing-primary", str(dummy))
    assert not result.timed_out and result.returncode != 0
    out = result.stdout + result.stderr
    assert "require --expansion-manifest" in out


def _expand_evidence_chain(arbitrate=False):
    # Build a self-contained fake dataset with a large qiongtongbaojian rule
    # universe so the R1 state machine lands in the EXPAND band. Runs the
    # REAL decide (R1) + expand CLIs in-process, then builds an all-pass R2
    # primary over sample+expansion ids. When arbitrate=True the R1 second
    # review DISAGREES and an arbitration receipt adjudicates (keeping the
    # critical), exercising the arbitration branch. Returns every path the
    # single-read consumer tests need.
    base = fixtures.tmp_dir("acceptance_expand_chain")
    data, chman_path = fixtures.build_tiny_dataset(base)
    # widen qiongtongbaojian rule universe to 700: compute_k(700,3)=21, and
    # 1 critical / 21 reviewed = 4.76% -> EXPAND (below 8% stratum cascade,
    # above 2% EXPAND_LOW, <= 5% REJECT). Do NOT overwrite all_rules.json
    # (that orphans the MCQ source_rule_id foreign keys); append new qx ids.
    qdir = data / "knowledge_base" / "classic_texts" / "qiongtongbaojian"
    existing_rules = fixtures.read_json(qdir / "all_rules.json")
    extra_rules = [{"id": f"qx{i:03d}", "category": "测试", "subject": "测试",
                    "condition": "测试", "rule": f"qx规则{i}。",
                    "original_text": f"qx原文{i}", "source_book": "qiongtongbaojian",
                    "source_chapter": f"一、qiongtong节{i}"} for i in range(700)]
    fixtures.write_json(qdir / "all_rules.json", existing_rules + extra_rules)
    man, chman_sha = sampling.load_chapter_manifest(chman_path)
    source = c.DirSource(data)
    desc = {"kind": "dir", "root": str(data), "test_only": True}
    sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))

    def item(book, item_type, iid, verdict="PASS", findings=None):
        sc = int(iid.split("_")[1]) if book == "sanmingtonghui" else 1
        return {"item": {"book": book, "type": item_type, "id": iid,
                         "source_chapter": sc},
                "verdict": verdict, "findings": findings or []}

    # R1 primary: exactly one critical FAIL on a qiongtongbaojian rule.
    crit_id = sorted(sm["samples"]["qiongtongbaojian"]["rule"]["1"])[0]
    r1_items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    if (book, item_type, iid) == ("qiongtongbaojian", "rule", crit_id):
                        r1_items.append(item(book, item_type, iid, "FAIL",
                                             [fixtures.critical()]))
                    else:
                        r1_items.append(item(book, item_type, iid))
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            r1_items.append(item("sanmingtonghui", item_type, iid))
    r1_primary = {"schema_version": "1.0", "kind": "primary_review_package",
                  "sample_manifest_sha256": c.sha256_file_raw(sm_path),
                  "expansion_manifests_sha256": [],
                  "overall_stats": {}, "zero_output_report": [],
                  "reviewer_list": ["reviewer-1"], "items": r1_items}
    r1_p_path = base / "r1_primary.json"
    fixtures.write_json(r1_p_path, r1_primary)

    # second review: agrees (no arbitration) or disagrees (arbitrate=True).
    second = {"schema_version": "1.0", "kind": "second_review_receipt_v1",
              "primary_sha256": c.sha256_file_raw(r1_p_path),
              "reviewer": "reviewer-2", "reviewed_at": "2026-08-23T00:00:00+08:00",
              "entries": [{"book": "qiongtongbaojian", "type": "rule",
                           "id": crit_id, "finding_index": 0,
                           "agree": not arbitrate,
                           "evidence_text": "e", "reviewer": "reviewer-2",
                           "reviewed_at": "2026-08-23T00:00:00+08:00"}]}
    r1_s_path = base / "r1_second.json"
    fixtures.write_json(r1_s_path, second)

    # arbitration receipt only when the second review disagrees (F22).
    r1_a_path = None
    if arbitrate:
        arbitration = {"schema_version": "1.0", "kind": "arbitration_receipt_v1",
                       "primary_sha256": c.sha256_file_raw(r1_p_path),
                       "second_review_sha256": c.sha256_file_raw(r1_s_path),
                       "reviewer_second": "reviewer-2", "arbitrator": "reviewer-3",
                       "reviewed_at": "2026-08-23T00:00:00+08:00",
                       "entries": [{"book": "qiongtongbaojian", "type": "rule",
                                    "id": crit_id, "finding_index": 0,
                                    "reviewer_first": "reviewer-1",
                                    "decision": "critical", "reasoning": "why",
                                    "arbitrator": "reviewer-3",
                                    "reviewed_at": "2026-08-23T00:00:00+08:00"}]}
        r1_a_path = base / "r1_arbitration.json"
        fixtures.write_json(r1_a_path, arbitration)

    # produce the R1 EXPAND report through the REAL decide code path.
    _, _, _, r1_report = review.validate_decision_inputs(
        sm, [], man, source, desc, fixtures.sha256_file(sm_path), [], True,
        r1_p_path, r1_s_path, r1_a_path)
    assert r1_report["verdict"] == "EXPAND", \
        f"fixture drift: R1 verdict is {r1_report['verdict']!r}, not EXPAND"
    assert r1_report["pending_expands"] == [{"book": "qiongtongbaojian", "type": "rule"}]
    r1_report_path = base / "r1_report.json"
    fixtures.write_json(r1_report_path, r1_report)

    # produce the expansion manifest through the REAL expand CLI.
    expand_args = [
        "--sample-manifest", str(sm_path), "--decision-report", str(r1_report_path),
        "--primary", str(r1_p_path), "--second", str(r1_s_path),
        "--chapter-manifest", str(chman_path), "--data-root", str(data),
        "--out", str(base / "exp")]
    if arbitrate:
        expand_args += ["--arbitration", str(r1_a_path)]
    review.sampling.cmd_expand(expand_args)
    exp_path = base / "exp" / "expansion_manifest_v1.json"
    em = fixtures.read_json(exp_path)

    # R2 primary: all-pass over sample ids + expansion new ids, binds em_sha.
    em_sha = c.sha256_bytes(exp_path.read_bytes())
    r2_items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    r2_items.append(item(book, item_type, iid))
    for item_type, strata in em["expansions"]["qiongtongbaojian"].items():
        for info in strata.values():
            for iid in info["new_ids"]:
                r2_items.append(item("qiongtongbaojian", item_type, iid))
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            r2_items.append(item("sanmingtonghui", item_type, iid))
    r2_primary = {"schema_version": "1.0", "kind": "primary_review_package",
                  "sample_manifest_sha256": c.sha256_file_raw(sm_path),
                  "expansion_manifests_sha256": [em_sha],
                  "overall_stats": {}, "zero_output_report": [],
                  "reviewer_list": ["reviewer-1"], "items": r2_items}
    r2_p_path = base / "r2_primary.json"
    fixtures.write_json(r2_p_path, r2_primary)

    return {"base": base, "data": data, "chman_path": chman_path, "man": man,
            "source": source, "desc": desc, "sm": sm, "sm_path": sm_path,
            "r1_p_path": r1_p_path, "r1_s_path": r1_s_path,
            "r1_a_path": r1_a_path,
            "r1_report_path": r1_report_path, "exp_path": exp_path, "em": em,
            "em_sha": em_sha, "r2_p_path": r2_p_path}


def _expansion_read_sentinel(monkeypatch, exp_path):
    # Count reads of exp_path; a SECOND read returns swapped bytes so any
    # double-read / SHA recompute fails closed (TOCTOU). Other paths read
    # normally.
    reads = []
    orig = Path.read_bytes

    def sentinel(self, *a, **k):
        if str(self) == str(exp_path):
            reads.append(1)
            if len(reads) >= 2:
                return b'{"kind": "swapped"}'
        return orig(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", sentinel)
    return reads


def test_packet_expansion_reads_manifest_once(monkeypatch):
    chain = _expand_evidence_chain()
    try:
        out = chain["base"] / "pkg"
        reads = _expansion_read_sentinel(monkeypatch, chain["exp_path"])
        review.cmd_packet([
            "--sample-manifest", str(chain["sm_path"]),
            "--chapter-manifest", str(chain["chman_path"]),
            "--data-root", str(chain["data"]), "--out", str(out),
            "--expansion-manifest", str(chain["exp_path"]),
            "--decision-report", str(chain["r1_report_path"]),
            "--producing-primary", str(chain["r1_p_path"]),
            "--producing-second", str(chain["r1_s_path"])])
        assert reads == [1]
        packet = fixtures.read_json(out / "review_packet_v1.json")
        # em_sha is pinned by the helper BEFORE the sentinel exists; reading
        # exp_path here would itself be the second read (returns swapped).
        assert packet["expansion_manifests_sha256"] == [chain["em_sha"]]
    finally:
        fixtures.rmtree_force(chain["base"])


def test_decide_expansion_reads_manifest_once(monkeypatch):
    chain = _expand_evidence_chain()
    try:
        out = chain["base"] / "dec"
        reads = _expansion_read_sentinel(monkeypatch, chain["exp_path"])
        review.cmd_decide([
            "--primary", str(chain["r2_p_path"]),
            "--sample-manifest", str(chain["sm_path"]),
            "--chapter-manifest", str(chain["chman_path"]),
            "--data-root", str(chain["data"]), "--out", str(out),
            "--expansion-manifest", str(chain["exp_path"]),
            "--decision-report", str(chain["r1_report_path"]),
            "--producing-primary", str(chain["r1_p_path"]),
            "--producing-second", str(chain["r1_s_path"])])
        assert reads == [1]
        report = fixtures.read_json(out / "decision_report_v1.json")
        assert report["expansion_manifests_sha256"] == [chain["em_sha"]]
        # R2 is all-pass over sample+expansion -> terminal ACCEPT
        assert report["verdict"] == "ACCEPT"
    finally:
        fixtures.rmtree_force(chain["base"])


def _multi_read_sentinel(monkeypatch, paths):
    # Count reads of each tracked path; a SECOND read of any tracked path
    # returns swapped bytes so a double-read / SHA recompute fails closed
    # (TOCTOU). Other paths read normally.
    reads = {p: [] for p in paths}
    orig = Path.read_bytes

    def sentinel(self, *a, **k):
        key = str(self)
        if key in reads:
            reads[key].append(1)
            if len(reads[key]) >= 2:
                return b'{"kind": "swapped"}'
        return orig(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", sentinel)
    return reads


def test_producing_evidence_chain_reads_each_artifact_once(monkeypatch):
    # P0 (TOCTOU): every artifact in the producing-evidence chain is read
    # exactly ONCE (sample, producing primary, producing second, producing
    # report, expansion). A second read of any tracked path returns swapped
    # bytes, so a double-read / SHA recompute fails closed.
    chain = _expand_evidence_chain()
    try:
        out = chain["base"] / "pkg"
        tracked = [str(chain["sm_path"]), str(chain["r1_p_path"]),
                   str(chain["r1_s_path"]), str(chain["r1_report_path"]),
                   str(chain["exp_path"])]
        reads = _multi_read_sentinel(monkeypatch, tracked)
        review.cmd_packet([
            "--sample-manifest", str(chain["sm_path"]),
            "--chapter-manifest", str(chain["chman_path"]),
            "--data-root", str(chain["data"]), "--out", str(out),
            "--expansion-manifest", str(chain["exp_path"]),
            "--decision-report", str(chain["r1_report_path"]),
            "--producing-primary", str(chain["r1_p_path"]),
            "--producing-second", str(chain["r1_s_path"])])
        for p in tracked:
            assert reads[p] == [1], f"{p} read {len(reads[p])} times, expected once"
    finally:
        fixtures.rmtree_force(chain["base"])


def test_producing_evidence_chain_arbitration_reads_once(monkeypatch):
    # P0 (TOCTOU), arbitration branch: with a disagreeing second review the
    # producing chain reads the arbitration receipt ONCE too.
    chain = _expand_evidence_chain(arbitrate=True)
    try:
        out = chain["base"] / "pkg"
        tracked = [str(chain["sm_path"]), str(chain["r1_p_path"]),
                   str(chain["r1_s_path"]), str(chain["r1_a_path"]),
                   str(chain["r1_report_path"]), str(chain["exp_path"])]
        reads = _multi_read_sentinel(monkeypatch, tracked)
        review.cmd_packet([
            "--sample-manifest", str(chain["sm_path"]),
            "--chapter-manifest", str(chain["chman_path"]),
            "--data-root", str(chain["data"]), "--out", str(out),
            "--expansion-manifest", str(chain["exp_path"]),
            "--decision-report", str(chain["r1_report_path"]),
            "--producing-primary", str(chain["r1_p_path"]),
            "--producing-second", str(chain["r1_s_path"]),
            "--producing-arbitration", str(chain["r1_a_path"])])
        for p in tracked:
            assert reads[p] == [1], f"{p} read {len(reads[p])} times, expected once"
    finally:
        fixtures.rmtree_force(chain["base"])


def test_check_finalize_terminal_verdict():
    report = {"kind": "decision_report_v1", "verdict": "EXPAND",
              "primary_sha256": "0" * 64, "sample_manifest_sha256": "1" * 64,
              "second_review_sha256": None, "arbitration_sha256": None,
              "expansion_manifests_sha256": []}
    with pytest.raises(RuntimeError, match="terminal verdict"):
        review.check_finalize(report)


def test_finalize_build_package_pure():
    # P0-1: finalize must refuse fake products, so the happy-path packaging is
    # covered by the pure assembler build_final_package() (no frozen chain, no
    # fake-refusal gate involved) plus a production CLI test below.
    # P0: use a NON-EMPTY expansion SHA so the test proves the pinned em_sha
    # actually flows into the final package (an empty list would trivially
    # pass even if build_final_package dropped the expansion binding).
    exp_sha = "d" * 64
    report = {"kind": "decision_report_v1", "verdict": "ACCEPT",
              "primary_sha256": "a" * 64, "sample_manifest_sha256": "b" * 64,
              "second_review_sha256": None, "arbitration_sha256": None,
              "expansion_manifests_sha256": [exp_sha]}
    primary = {"reviewer_list": ["reviewer-1"]}
    # P0: file identity must be the REAL consumed basenames (here deliberately
    # non-canonical/versioned), not hardcoded canonical names.
    artifact_files = {
        "decision_report": "decision_report_round2_v2.json",
        "primary_review": "primary_review_2026-08-25.json",
        "sample_manifest": "sample_manifest_v3.json",
    }
    package = review.build_final_package(
        report, primary, "c" * 64, [exp_sha], artifact_files,
        exp_files=["expansion_round1.json"], today=datetime.date(2026, 8, 25))
    assert package["kind"] == "final_acceptance_package_v1"
    assert package["final_verdict"] == "ACCEPT"
    assert package["decision_report_sha256"] == "c" * 64
    assert package["primary_sha256"] == "a" * 64
    assert package["sample_manifest_sha256"] == "b" * 64
    assert package["second_review_sha256"] is None
    assert package["arbitration_sha256"] is None
    assert package["expansion_manifests_sha256"] == [exp_sha]
    assert package["reviewer_list"] == ["reviewer-1"]
    assert package["generated_at"] == "2026-08-25"
    # design section 8: explicit per-artifact identity = the REAL consumed
    # (non-canonical, versioned) basename + its content SHA.
    arts = {a["role"]: a for a in package["artifacts"]}
    assert len(package["artifacts"]) == 4
    assert arts["decision_report"] == {
        "role": "decision_report", "file": "decision_report_round2_v2.json",
        "sha256": "c" * 64}
    assert arts["primary_review"]["file"] == "primary_review_2026-08-25.json"
    assert arts["primary_review"]["sha256"] == "a" * 64
    assert arts["sample_manifest"]["file"] == "sample_manifest_v3.json"
    assert arts["sample_manifest"]["sha256"] == "b" * 64
    assert arts["expansion_manifest"]["sha256"] == exp_sha
    assert arts["expansion_manifest"]["file"] == "expansion_round1.json"
    assert "second_review" not in arts
    assert "arbitration" not in arts


def test_finalize_package_requires_consumed_file_identity():
    # The assembler must NOT fabricate a filename: a missing consumed-file
    # identity fails closed instead of defaulting to a canonical name.
    exp_sha = "d" * 64
    report = {"kind": "decision_report_v1", "verdict": "ACCEPT",
              "primary_sha256": "a" * 64, "sample_manifest_sha256": "b" * 64,
              "second_review_sha256": None, "arbitration_sha256": None,
              "expansion_manifests_sha256": [exp_sha]}
    with pytest.raises(RuntimeError, match="missing consumed-file identity"):
        review.build_final_package(report, {"reviewer_list": ["r"]}, "c" * 64,
                                   [exp_sha], {"decision_report": "r.json",
                                               "primary_review": "p.json"})
    with pytest.raises(RuntimeError, match="missing consumed-file identity for expansion"):
        review.build_final_package(report, {"reviewer_list": ["r"]}, "c" * 64,
                                   [exp_sha], {"decision_report": "r.json",
                                               "primary_review": "p.json",
                                               "sample_manifest": "s.json"})


def _production_primary(real_packet):
    packet, sm = real_packet
    items = []
    for e in packet["items"]:
        entry = _primary_entry(e["book"], e["type"], e["id"])
        # P0: keep the REAL source_chapter from the packet (design section 8.1
        # schema); _primary_entry defaults to 1, which would silently move
        # every sanmingtonghui item to chapter 1 and break the per-entry
        # chapter identity / evidence traceability (boundary/stratum metrics
        # themselves come from the frozen sample/chapter metadata, not this
        # field, but the forged ownership must not validate).
        entry["item"]["source_chapter"] = e.get("source_chapter")
        items.append(entry)
    primary = _mini_primary()
    primary["items"] = items
    primary["zero_output_report"] = packet["integrity"]["zero_output_chapters"]
    return primary, sm


def _production_inputs(real_packet, tmp_path, run_name):
    """Build a real all-PASS primary + sample manifest in `tmp_path/run_name`.
    Returns (run_dir, p_path, sm_path, man, source, git_desc) wired to the REAL
    frozen data (production mode, test_only=False). The primary keeps the REAL
    per-item source_chapter (design section 8.1) so it cross-validates."""
    primary, sm = _production_primary(real_packet)
    run = tmp_path / run_name
    run.mkdir(parents=True, exist_ok=True)
    sm_path = run / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = run / "primary_ok.json"
    fixtures.write_json(p_path, primary)
    man, _chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
    git_desc = {"kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False}
    return run, p_path, sm_path, primary, man, source, git_desc


def _decide_production_inprocess(p_path, sm_path, out_dir, man, source, git_desc):
    """P0 (CI per-test 120s gate): produce the production decision report by
    calling the SAME validation/compute path `cmd_decide` runs, but IN PROCESS.
    Only the CLI entry point `build_source` spawns the ~73s frozen-input lock
    subprocess; calling validate_decision_inputs directly over a real GitSource
    still validates against the REAL frozen data (and enforces F18 reads from
    the pinned commit) without that second freeze-chain run. This keeps each
    production test to AT MOST ONE freeze-chain subprocess (a real `finalize`).
    Writes decision_report_v1.json into out_dir and returns (report, report_path)."""
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      git_desc, chman_sha, expected_test_only=False)
    _, _, _, report = review.validate_decision_inputs(
        sample_manifest, [], chapter_manifest, source, git_desc, sm_sha, [], False,
        p_path, None, None)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "decision_report_v1.json"
    report_path.write_bytes(c.serialize_json(report))
    return report, report_path


def test_finalize_production_happy_path(tmp_path, real_packet):
    # P0-1: the real finalize positive path runs against the REAL frozen data
    # (production mode, test_only=False). The ACCEPT decision report is
    # produced IN PROCESS (same compute path as `decide`, no extra freeze-chain
    # subprocess); exactly ONE production `finalize` subprocess assembles the
    # package, so this test stays under the CI per-test 120s gate while still
    # exercising the real CLI finalize + F17/F22 receipt gate + artifacts.
    run, p_path, sm_path, _primary, man, source, git_desc = _production_inputs(
        real_packet, tmp_path, "prod_happy")
    report, report_path = _decide_production_inprocess(
        p_path, sm_path, run, man, source, git_desc)
    assert report["verdict"] == "ACCEPT"
    assert report["test_only"] is False
    out = tmp_path / "prod_out"
    fixtures.run_cli("classic_acceptance_review.py", "finalize",
                     "--decision-report", str(report_path), "--primary", str(p_path),
                     "--sample-manifest", str(sm_path),
                     "--chapter-manifest", fixtures.CHAPTER_MANIFEST,
                     "--candidate-commit", fixtures.COMMIT, "--out", str(out))
    final = fixtures.read_json(out / "final_acceptance_package_v1.json")
    assert final["final_verdict"] == "ACCEPT"
    assert final["primary_sha256"] == fixtures.sha256_file(p_path)
    assert final["decision_report_sha256"] == fixtures.sha256_file(report_path)
    assert final["sample_manifest_sha256"] == fixtures.sha256_file(sm_path)
    assert final["second_review_sha256"] is None
    assert final["arbitration_sha256"] is None
    assert final["reviewer_list"] == ["reviewer-1"]
    prod_arts = {a["role"]: a for a in final["artifacts"]}
    # file identity = basename of the file ACTUALLY consumed (the primary was
    # passed as primary_ok.json; the package must not claim a canonical name).
    assert prod_arts["decision_report"]["file"] == Path(report_path).name
    assert prod_arts["decision_report"]["sha256"] == fixtures.sha256_file(report_path)
    assert prod_arts["primary_review"]["file"] == Path(p_path).name == "primary_ok.json"
    assert prod_arts["primary_review"]["sha256"] == fixtures.sha256_file(p_path)
    assert prod_arts["sample_manifest"]["file"] == Path(sm_path).name
    assert prod_arts["sample_manifest"]["sha256"] == fixtures.sha256_file(sm_path)
    assert "second_review" not in prod_arts
    assert "arbitration" not in prod_arts


def test_finalize_production_rejects_stray_second(tmp_path, real_packet):
    # F17/F22: a receipt that the state machine does not require (a second
    # review over a no-critical-findings primary) is rejected by the finalize
    # gate even in production. Exactly ONE production finalize subprocess
    # (freeze chain runs once); the report is produced in process.
    run, p_path, sm_path, _primary, man, source, git_desc = _production_inputs(
        real_packet, tmp_path, "prod_stray")
    _report, report_path = _decide_production_inprocess(
        p_path, sm_path, run, man, source, git_desc)
    other_second = run / "stray_second.json"
    fixtures.write_json(other_second, {"kind": "second_review_receipt_v1"})
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(report_path),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(fixtures.CHAPTER_MANIFEST),
        "--candidate-commit", fixtures.COMMIT,
        "--second", str(other_second), "--out", str(run / "finalize_stray"))
    assert not r.timed_out and r.returncode != 0
    assert "not allowed" in r.stdout + r.stderr


def test_decide_production_rejects_tampered_source_chapter(tmp_path, real_packet):
    # P0: a tampered source_chapter on a real sanmingtonghui item fails closed
    # in production decide. validate_primary receives the frozen chapter
    # manifest and cross-checks every sanmingtonghui item's source_chapter;
    # run IN PROCESS over the real GitSource so this exercises the real
    # production cross-check without a second freeze-chain subprocess.
    import copy
    run, p_path, sm_path, primary, man, source, git_desc = _production_inputs(
        real_packet, tmp_path, "prod_tamper")
    tampered = copy.deepcopy(primary)
    for entry in tampered["items"]:
        if entry["item"]["book"] == "sanmingtonghui":
            real_ch = entry["item"]["source_chapter"]
            entry["item"]["source_chapter"] = 1 if real_ch != 1 else 2
            break
    tampered_path = run / "primary_tampered.json"
    fixtures.write_json(tampered_path, tampered)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    chapter_manifest, _ = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    with pytest.raises(RuntimeError, match="source_chapter"):
        review.validate_decision_inputs(
            sample_manifest, [], chapter_manifest, source, git_desc, sm_sha, [],
            False, tampered_path, None, None)


def test_finalize_production_no_overwrite_leaves_frozen_package(tmp_path, real_packet):
    # P0 (design section 8 no-overwrite): a finalize whose target final-package
    # path already exists must fail closed and leave the already-published
    # frozen bytes untouched. A correction is published by re-running finalize
    # into a NEW --out directory (the toolchain's "_v2"); the sealed package is
    # never modified in place. The package slot is pre-seeded with a sentinel
    # so this needs only ONE production finalize subprocess (freeze chain
    # runs once); it must fail at the atomic create-if-absent publish step and
    # the sentinel bytes must survive unchanged.
    run, p_path, sm_path, _primary, man, source, git_desc = _production_inputs(
        real_packet, tmp_path, "prod_no_overwrite")
    _report, report_path = _decide_production_inprocess(
        p_path, sm_path, run, man, source, git_desc)
    out = tmp_path / "prod_no_overwrite_out"
    out.mkdir(parents=True, exist_ok=True)
    pkg_path = out / "final_acceptance_package_v1.json"
    sentinel = b'{"sentinel": "frozen-must-not-be-touched"}\n'
    pkg_path.write_bytes(sentinel)
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(report_path),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(fixtures.CHAPTER_MANIFEST),
        "--candidate-commit", fixtures.COMMIT, "--out", str(out))
    assert not r.timed_out and r.returncode != 0
    assert "already exists" in r.stdout + r.stderr
    assert pkg_path.read_bytes() == sentinel


def test_run_cli_result_timeout_kills_whole_process_tree(tmp_path):
    # P1: a wedged CLI must be killed WITH every descendant it spawned, and the
    # bounded timeout must fire BEFORE pytest's --timeout=120 aborts the test.
    # The hang script spawns a grandchild (mirroring a CLI that itself spawns
    # the ~73s frozen-chain checker) and records BOTH pids to a file; after the
    # short timeout both pids must be gone, proving _kill_process_tree reaps the
    # whole tree rather than just the direct child.
    import time
    hang = tmp_path / "hang_cli.py"
    pid_file = tmp_path / "pids.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "if os.name == 'nt':\n"
        "    kw = dict(creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))\n"
        "    child = [sys.executable, '-c', 'import time; time.sleep(3600)']\n"
        "else:\n"
        "    # inherit the CLI's process group: the POSIX cleanup kills the\n"
        "    # whole GROUP, so a grandchild escaping into its own session\n"
        "    # would be outside the killpg contract.\n"
        "    kw = {}\n"
        "    child = ['sleep', '3600']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")
    t0 = time.time()
    res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
    call_elapsed = time.time() - t0
    assert res.timed_out, "run_cli_result should report a timeout for the hung CLI"
    assert res.cleanup_ok is True, "real taskkill on a live tree must prove the reap"
    assert call_elapsed < 5 + fixtures.CLEANUP_TIMEOUT_SECONDS + 10, (
        f"run_cli_result returned in {call_elapsed:.1f}s after a 5s timeout; "
        f"cleanup must stay bounded to beat the 120s pytest gate")
    pids = fixtures.read_json(pid_file)
    parent_pid, child_pid = pids["parent"], pids["child"]
    # the helper reaps the whole tree before returning; a short poll only
    # covers OS scheduling jitter, not unbounded cleanup.
    deadline = time.time() + 3
    while time.time() < deadline and (fixtures._pid_alive(parent_pid)
                                      or fixtures._pid_alive(child_pid)):
        time.sleep(0.1)
    assert not fixtures._pid_alive(parent_pid), "hung CLI parent survived the timeout kill"
    assert not fixtures._pid_alive(child_pid), "hung CLI grandchild survived the process-tree kill"


def test_run_cli_result_cleanup_returns_well_before_pytest_gate(tmp_path):
    # P0: not only must the timeout fire before pytest's --timeout=120, the
    # cleanup that follows (tree-kill + output drain) must ALSO be bounded so
    # the helper returns with comfortable margin. Measure the wall time of
    # run_argv_result itself around a hung CLI that spawns a grandchild, with a
    # short timeout: it must return within timeout + CLEANUP budget (a small
    # scheduling slack), proving taskkill/drain cannot block unbounded and push
    # the worst case (CLI_TIMEOUT_SECONDS + cleanup) past the 120s gate.
    import time
    hang = tmp_path / "hang_cli_bounded.py"
    pid_file = tmp_path / "pids_b.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "if os.name == 'nt':\n"
        "    kw = dict(creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))\n"
        "    child = [sys.executable, '-c', 'import time; time.sleep(3600)']\n"
        "else:\n"
        "    # inherit the CLI's process group: the POSIX cleanup kills the\n"
        "    # whole GROUP, so a grandchild escaping into its own session\n"
        "    # would be outside the killpg contract.\n"
        "    kw = {}\n"
        "    child = ['sleep', '3600']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")
    timeout = 5
    t0 = time.time()
    res = fixtures.run_argv_result(
        [sys.executable, str(hang), str(pid_file)], timeout=timeout)
    elapsed = time.time() - t0
    assert res.timed_out
    assert res.cleanup_ok is True, "real taskkill on a live tree must prove the reap"
    # bounded cleanup: the helper (timeout + bounded tree-kill/drain) must
    # return within timeout + cleanup budget + small scheduling slack.
    assert elapsed < timeout + fixtures.CLEANUP_TIMEOUT_SECONDS + 10, (
        f"cleanup path took {elapsed:.1f}s after a {timeout}s timeout -- "
        f"unbounded; at production timeout this could cross the 120s gate")
    pids = fixtures.read_json(pid_file)
    # by the time the helper returns the tree must already be reaped (the
    # helper kills the whole tree before returning), with no external polling.
    assert not fixtures._pid_alive(pids["parent"]), "parent not reaped on return"
    assert not fixtures._pid_alive(pids["child"]), "grandchild not reaped on return"


def test_pid_alive_fails_closed_when_probe_cannot_decide(monkeypatch):
    # P0: _pid_alive must NEVER report "dead" from an inconclusive probe. A
    # tasklist timeout (None), a nonzero exit, or a spawn failure is
    # UNCERTAIN and must be treated as ALIVE; only a successful (exit 0)
    # probe whose output lacks the pid proves death (verified on Windows:
    # "no tasks running" is exit 0, so rc != 0 really is a failure).
    if sys.platform != "win32":
        pytest.skip("tasklist fail-closed contract is Windows-specific")
    import types
    for broken in (None,
                   types.SimpleNamespace(returncode=1, stdout="", stderr=""),
                   types.SimpleNamespace(returncode=5, stdout="err", stderr="")):
        monkeypatch.setattr(fixtures, "_bounded_subprocess",
                            lambda argv, timeout, r=broken: r)
        assert fixtures._pid_alive(499999) is True, (
            f"probe result {broken!r} is uncertain and must fail closed as alive")
    ok_absent = types.SimpleNamespace(
        returncode=0, stdout="INFO: No tasks are running which match the specified criteria.\r\n",
        stderr="")
    monkeypatch.setattr(fixtures, "_bounded_subprocess",
                        lambda argv, timeout, r=ok_absent: r)
    assert fixtures._pid_alive(499999) is False


@pytest.mark.skipif(sys.platform != "win32",
                     reason="Windows taskkill fail-closed contract")
@pytest.mark.parametrize("failure", [
    pytest.param(None, id="taskkill-times-out"),
    pytest.param(1, id="taskkill-nonzero-exit"),
])
def test_run_cli_result_reports_uncertain_cleanup_when_taskkill_fails(
        tmp_path, monkeypatch, failure):
    # P0 (Windows-only: the POSIX cleanup path never calls taskkill; its
    # mirror is the killpg test below): when the tree-kill tool itself fails
    # (timeout -> None, or a nonzero exit), the helper must NOT claim the
    # tree was reaped: cleanup_ok fails closed to False. The direct child is
    # still reaped by the proc.kill()
    # last resort and the return stays wall-clock bounded (shared deadline);
    # the grandchild may legitimately survive -- exactly the uncertain state
    # being reported -- so it is reaped with the REAL taskkill afterwards.
    import time
    import types
    hang = tmp_path / "hang_cli_uncertain.py"
    pid_file = tmp_path / "pids_u.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "if os.name == 'nt':\n"
        "    kw = dict(creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))\n"
        "    child = [sys.executable, '-c', 'import time; time.sleep(3600)']\n"
        "else:\n"
        "    # inherit the CLI's process group: the POSIX cleanup kills the\n"
        "    # whole GROUP, so a grandchild escaping into its own session\n"
        "    # would be outside the killpg contract.\n"
        "    kw = {}\n"
        "    child = ['sleep', '3600']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")
    real_bounded = fixtures._bounded_subprocess

    def fake_bounded(argv, timeout):
        if argv and argv[0] == "taskkill":
            if failure is None:
                return None
            return types.SimpleNamespace(returncode=failure, stdout="", stderr="")
        return real_bounded(argv, timeout)

    monkeypatch.setattr(fixtures, "_bounded_subprocess", fake_bounded)
    t0 = time.time()
    res = None
    child_pid = None
    try:
        res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
        elapsed = time.time() - t0
        assert res.timed_out
        assert res.cleanup_ok is False, (
            "a failed/uncertain taskkill must fail closed, not claim a reaped tree")
        assert elapsed < 5 + fixtures.CLEANUP_TIMEOUT_SECONDS + 10
        pids = fixtures.read_json(pid_file)
        # the direct child is reaped by the proc.kill() last resort; a short
        # poll only covers OS scheduling jitter.
        deadline = time.time() + 3
        while time.time() < deadline and fixtures._pid_alive(pids["parent"]):
            time.sleep(0.1)
        assert not fixtures._pid_alive(pids["parent"]), (
            "proc.kill() last resort must still reap the direct child")
    finally:
        # EVERY assertion above is inside this try, so a failure cannot skip
        # the reap. res.pid covers a still-alive leader. If read_json failed,
        # recover the grandchild identity from a RAW pid-file read (bypassing
        # any injected fixtures.read_json): taskkill /T on the already-dead
        # parent cannot reach an orphaned grandchild on Windows, so without
        # this the child would leak. A failing test never leaks a 3600s
        # process.
        if res is not None:
            _force_reap_tree(res.pid)
        if child_pid is None:
            try:
                child_pid = json.loads(
                    Path(pid_file).read_text(encoding="utf-8"))["child"]
            except Exception:
                child_pid = None
        if child_pid is not None:
            _force_reap_tree(child_pid)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX killpg fail-closed contract")
def test_run_cli_result_reports_uncertain_cleanup_when_killpg_fails(
        tmp_path, monkeypatch):
    # P0 (POSIX mirror of the taskkill test): when the group kill cannot be
    # delivered (os.killpg raises PermissionError), cleanup_ok must fail
    # closed to False; the direct child is still reaped by the proc.kill()
    # last resort and the return stays wall-clock bounded (shared deadline).
    # The grandchild may legitimately survive -- exactly the uncertain state
    # being reported -- so it is reaped with POSIX signals only (never
    # taskkill, which does not exist on Ubuntu CI).
    import os
    import time
    hang = tmp_path / "hang_cli_posix_fail.py"
    pid_file = tmp_path / "pids_kp.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "kw = {}\n"
        "child = ['sleep', '3600']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")

    def fake_killpg(pgid, sig):
        raise PermissionError(f"simulated killpg failure for pgid {pgid}")

    monkeypatch.setattr(os, "killpg", fake_killpg)
    t0 = time.time()
    res = None
    try:
        res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
        elapsed = time.time() - t0
        assert res.timed_out
        assert res.cleanup_ok is False, (
            "a failed/uncertain killpg must fail closed, not claim a reaped tree")
        assert elapsed < 5 + fixtures.CLEANUP_TIMEOUT_SECONDS + 10
        pids = fixtures.read_json(pid_file)
        # the direct child is reaped by the proc.kill() last resort; a short
        # poll only covers OS scheduling jitter.
        deadline = time.time() + 3
        while time.time() < deadline and fixtures._pid_alive(pids["parent"]):
            time.sleep(0.1)
        assert not fixtures._pid_alive(pids["parent"]), (
            "proc.kill() last resort must still reap the direct child")
    finally:
        # EVERY assertion above is inside this try, so a failure cannot skip
        # the reap. res.pid is the process GROUP id (start_new_session), so
        # this test-side REAL killpg reaps the whole group (including a
        # surviving grandchild) WITHOUT reading the pids JSON. It uses the
        # saved REAL killpg, unaffected by the fake killpg monkeypatch above.
        if res is not None:
            _force_reap_tree(res.pid)



@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX group-kill race (known pgid)")
def test_run_cli_result_reaps_descendant_after_group_leader_exits(tmp_path):
    # P0: the POSIX group kill must use the KNOWN pgid (== proc.pid, since
    # start_new_session=True), not getpgid(proc.pid). Here the CLI (group
    # leader) spawns a grandchild that inherits its stdout + process group and
    # then exits immediately; the grandchild keeps the pipe open, so
    # communicate() times out. On cleanup the leader is gone but the group
    # (and its remaining member) still exists -- getpgid(proc.pid) would raise
    # ProcessLookupError and report a false-green. killpg(proc.pid) must kill
    # the surviving grandchild and report cleanup_ok=True.
    import time
    hang = tmp_path / "hang_cli_leader_exits.py"
    pid_file = tmp_path / "pids_le.json"
    hang.write_text(
        "import json, os, subprocess, sys\n"
        "# grandchild inherits the CLI stdout (holding run_argv_result's pipe\n"
        "# open) and its process group; the leader then exits immediately.\n"
        "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3600)'])\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n",
        encoding="utf-8")
    res = None
    try:
        res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
        assert res.timed_out
        assert res.cleanup_ok is True, (
            "killpg(proc.pid) must prove the whole group reaped even though the "
            "leader had already exited")
        pids = fixtures.read_json(pid_file)
        # the grandchild held the pipe; after killpg it must be gone (a brief
        # poll only covers zombie-reap scheduler jitter, not unbounded cleanup).
        deadline = time.time() + 3
        while time.time() < deadline and fixtures._pid_alive(pids["child"]):
            time.sleep(0.1)
        assert not fixtures._pid_alive(pids["child"]), (
            "surviving grandchild in the departed leader's group was not reaped")
    finally:
        # If the cleanup_ok assertion failed, the production helper did NOT
        # reap the orphaned group; fall back to the test-side REAL killpg by
        # the known group id (res.pid) so a 3600s grandchild is never leaked.
        if res is not None:
            _force_reap_tree(res.pid)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX group-kill fallback proves json-free reaping")
def test_cleanup_finally_reaps_when_read_json_fails(tmp_path, monkeypatch):
    # P1: the finally fallback must not depend on the pids JSON. Inject a
    # read_json failure alongside a production killpg failure (so the
    # grandchild genuinely survives), then prove the group is still reaped by
    # the KNOWN group id (res.pid) -- mechanically, no leak remains.
    import os
    import time
    hang = tmp_path / "hang_cli_readjson_fail.py"
    pid_file = tmp_path / "pids_rij.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "kw = {}\n"
        "child = ['sleep', '3600']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")

    def fake_killpg(pgid, sig):
        raise PermissionError(f"simulated killpg failure for pgid {pgid}")
    monkeypatch.setattr(os, "killpg", fake_killpg)

    def fail_read_json(path):
        raise OSError("simulated read_json failure")
    monkeypatch.setattr(fixtures, "read_json", fail_read_json)

    res = None
    try:
        res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
        assert res.timed_out
        assert res.cleanup_ok is False, (
            "a failed/uncertain killpg must fail closed")
    finally:
        if res is not None:
            _force_reap_tree(res.pid)
    # After the finally reaped the group by res.pid, read the raw pids directly
    # (fixtures.read_json is still monkeypatched-broken) and prove no leak.
    raw = json.loads(Path(pid_file).read_text(encoding="utf-8"))
    deadline = time.time() + 3
    while time.time() < deadline and fixtures._pid_alive(raw["child"]):
        time.sleep(0.1)
    assert not fixtures._pid_alive(raw["child"]), (
        "json-free finally fallback leaked the grandchild")


@pytest.mark.skipif(sys.platform != "win32",
                    reason="Windows taskkill/json-failure fallback contract")
def test_cleanup_finally_reaps_when_read_json_fails_windows(
        tmp_path, monkeypatch):
    # Windows mirror of the POSIX read_json test: with BOTH the tree-kill
    # (taskkill -> None) and fixtures.read_json failing, the finally must
    # still reap the orphaned grandchild by RAW-reading the pid file (the
    # parent is already dead, so taskkill /T on res.pid cannot reach it) --
    # mechanically, no leak remains on the Windows CI path either.
    import time
    hang = tmp_path / "hang_cli_readjson_fail_win.py"
    pid_file = tmp_path / "pids_rijw.json"
    hang.write_text(
        "import json, os, subprocess, sys, time\n"
        "kw = dict(creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))\n"
        "child = [sys.executable, '-c', 'import time; time.sleep(3600)']\n"
        "g = subprocess.Popen(child, stdout=subprocess.DEVNULL,\n"
        "                     stderr=subprocess.DEVNULL, **kw)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(\n"
        "    json.dumps({'parent': os.getpid(), 'child': g.pid}))\n"
        "time.sleep(3600)\n",
        encoding="utf-8")
    real_bounded = fixtures._bounded_subprocess

    def fake_bounded(argv, timeout):
        if argv and argv[0] == "taskkill":
            return None
        return real_bounded(argv, timeout)

    def fail_read_json(path):
        raise OSError("simulated read_json failure")

    monkeypatch.setattr(fixtures, "_bounded_subprocess", fake_bounded)
    monkeypatch.setattr(fixtures, "read_json", fail_read_json)
    res = None
    try:
        res = fixtures.run_cli_result(hang, str(pid_file), timeout=5)
        assert res.timed_out
        assert res.cleanup_ok is False, (
            "a failed/uncertain taskkill must fail closed")
    finally:
        # the RAW read bypasses the injected fixtures.read_json failure and
        # recovers the grandchild identity the dead parent can no longer
        # provide to taskkill /T.
        if res is not None:
            _force_reap_tree(res.pid)
        child = None
        try:
            child = json.loads(
                Path(pid_file).read_text(encoding="utf-8"))["child"]
        except Exception:
            child = None
        if child is not None:
            _force_reap_tree(child)
    # after the finally reaped the grandchild, prove no leak (raw read again:
    # fixtures.read_json is still monkeypatched-broken).
    raw = json.loads(Path(pid_file).read_text(encoding="utf-8"))
    deadline = time.time() + 3
    while time.time() < deadline and fixtures._pid_alive(raw["child"]):
        time.sleep(0.1)
    assert not fixtures._pid_alive(raw["child"]), (
        "Windows json-free finally fallback leaked the grandchild")


def test_finalize_rejects_handcrafted_accept_report(tiny):
    # P0-1: a hand-crafted report with verdict=ACCEPT and self-consistent
    # on-disk SHAs must NOT finalize; finalize recomputes the terminal verdict
    # from the receipts and requires RAW on-disk byte equality.
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    p_path = base / "primary_ok.json"
    fixtures.write_json(p_path, primary)
    out = base / "finalize_forged"
    fixtures.run_cli("classic_acceptance_review.py", "decide",
                     "--primary", str(p_path), "--sample-manifest", str(sm_path),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(out))
    real_report_path = out / "decision_report_v1.json"
    real = fixtures.read_json(real_report_path)
    assert real["verdict"] == "ACCEPT"
    # Tamper with the on-disk report: re-serialize with CRLF (semantically the
    # same JSON, F20 raw bytes differ) -> finalize must reject on byte equality.
    crlf_path = out / "report_crlf.json"
    crlf_path.write_bytes(c.serialize_json(real).replace(b"\n", b"\r\n"))
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(crlf_path),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(chman_path),
        "--data-root", str(data), "--out", str(out / "pkg_crlf"))
    assert not r.timed_out and r.returncode != 0
    assert "bytes do not match" in r.stdout + r.stderr
    # Hand-craft a verdict flip to ACCEPT over an EXPAND-producing primary is
    # covered by the recompute path; here flip a field on the genuine ACCEPT
    # report (generated_at) while keeping every bound SHA identical -> rejected.
    tampered = dict(real, generated_at="1999-01-01T00:00:00+00:00")
    tampered_path = out / "report_tampered.json"
    fixtures.write_json(tampered_path, tampered)
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(tampered_path),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(chman_path),
        "--data-root", str(data), "--out", str(out / "pkg_tampered"))
    assert not r.timed_out and r.returncode != 0
    assert "bytes do not match" in r.stdout + r.stderr
    # A completely fabricated verdict=ACCEPT report with correct disk SHAs but
    # a wrong metrics payload is also rejected (recompute mismatch).
    forged = dict(real, fired_rules=["FORGED"], verdict="ACCEPT")
    forged_path = out / "report_forged.json"
    fixtures.write_json(forged_path, forged)
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(forged_path),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(chman_path),
        "--data-root", str(data), "--out", str(out / "pkg_forged"))
    assert not r.timed_out and r.returncode != 0
    assert "bytes do not match" in r.stdout + r.stderr


def test_finalize_refuses_test_only(tiny):
    base, data, chman_path, man, source, sm = tiny
    sm_path = base / "sample_manifest_v1.json"
    sm_path.write_bytes(c.serialize_json(sm))
    p_path = base / "primary_ok.json"
    primary = _tiny_all_pass_primary(sm)
    primary["sample_manifest_sha256"] = fixtures.sha256_file(sm_path)
    fixtures.write_json(p_path, primary)
    out = base / "finalize_fake"
    fixtures.run_cli("classic_acceptance_review.py", "decide",
                     "--primary", str(p_path), "--sample-manifest", str(sm_path),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(out))
    r = fixtures.run_cli_result(
        "classic_acceptance_review.py", "finalize",
        "--decision-report", str(out / "decision_report_v1.json"),
        "--primary", str(p_path), "--sample-manifest", str(sm_path),
        "--chapter-manifest", str(chman_path),
        "--data-root", str(data), "--out", str(out))
    assert not r.timed_out and r.returncode != 0
    assert "fake" in (r.stdout + r.stderr).lower()


def test_finalize_expansion_reads_manifest_once(monkeypatch):
    # P0 (TOCTOU) for finalize: the expansion manifest is read exactly ONCE.
    # finalize refuses fake (test_only) products via check_finalize, so this
    # test runs the fake expansion chain and asserts the fake-refusal
    # RuntimeError fires AFTER the expansion path was read exactly once --
    # the single-read property is proven even though finalize does not seal a
    # fake package. The happy-path package SHA binding is covered separately by
    # test_finalize_build_package_pure (build_final_package assembler) and the
    # production CLI finalize test.
    chain = _expand_evidence_chain()
    try:
        dec_out = chain["base"] / "dec"
        review.cmd_decide([
            "--primary", str(chain["r2_p_path"]),
            "--sample-manifest", str(chain["sm_path"]),
            "--chapter-manifest", str(chain["chman_path"]),
            "--data-root", str(chain["data"]), "--out", str(dec_out),
            "--expansion-manifest", str(chain["exp_path"]),
            "--decision-report", str(chain["r1_report_path"]),
            "--producing-primary", str(chain["r1_p_path"]),
            "--producing-second", str(chain["r1_s_path"])])
        report_path = dec_out / "decision_report_v1.json"
        reads = []
        orig = Path.read_bytes

        def sentinel(self, *a, **k):
            if str(self) == str(chain["exp_path"]):
                reads.append(1)
                if len(reads) >= 2:
                    return b'{"kind": "swapped"}'
            return orig(self, *a, **k)

        monkeypatch.setattr(Path, "read_bytes", sentinel)
        fin_out = chain["base"] / "fin"
        with pytest.raises(RuntimeError, match="fake"):
            review.cmd_finalize([
                "--decision-report", str(report_path),
                "--primary", str(chain["r2_p_path"]),
                "--sample-manifest", str(chain["sm_path"]),
                "--chapter-manifest", str(chain["chman_path"]),
                "--data-root", str(chain["data"]), "--out", str(fin_out),
                "--expansion-manifest", str(chain["exp_path"]),
                "--decision-report-r1", str(chain["r1_report_path"]),
                "--producing-primary", str(chain["r1_p_path"]),
                "--producing-second", str(chain["r1_s_path"])])
        # expansion read exactly once before the fake-refusal gate fired
        assert reads == [1]
        # no package is sealed for a fake product
        assert not (fin_out / "final_acceptance_package_v1.json").exists()
    finally:
        fixtures.rmtree_force(chain["base"])



def test_publish_new_file_two_writers_one_wins(tmp_path):
    # P0 (concurrent publication): exists()+write_bytes() is check-then-write;
    # two concurrent publishers can both observe absence and both write the
    # frozen path (overwrite / mixed-partial publication). The atomic
    # publish_new_file primitive must let EXACTLY ONE writer win, make every
    # loser fail closed, leave the sealed bytes equal to one complete canonical
    # payload, and clean up every temporary file (no half-file left behind to
    # block retries).
    target_dir = tmp_path / "pub"
    target_dir.mkdir()
    sealed = target_dir / "final_acceptance_package_v1.json"
    payload = c.serialize_json({"kind": "final_acceptance_package_v1",
                                "final_verdict": "ACCEPT"})
    winners = []
    losers = []

    def publisher(i):
        try:
            c.publish_new_file(sealed, payload)
            winners.append(i)
        except RuntimeError:
            losers.append(i)

    threads = [threading.Thread(target=publisher, args=(i,)) for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(winners) == 1, f"exactly one publisher must win, got {winners}"
    assert len(losers) == 7, f"all other publishers must fail closed, got {losers}"
    assert sealed.read_bytes() == payload
    leftovers = [p.name for p in target_dir.iterdir() if p.suffix == ".tmp"]
    assert leftovers == [], "temporary files must be cleaned up (no half-file)"


def test_publish_new_file_sequential_rejects_existing(tmp_path):
    # Sequential re-publication also fails closed and leaves the original bytes
    # untouched (the order-independent counterpart to the concurrent test).
    sealed = tmp_path / "final_acceptance_package_v1.json"
    first = c.serialize_json({"v": 1})
    c.publish_new_file(sealed, first)
    before = sealed.read_bytes()
    with pytest.raises(RuntimeError, match="already exists"):
        c.publish_new_file(sealed, c.serialize_json({"v": 2}))
    assert sealed.read_bytes() == before
