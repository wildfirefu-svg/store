"""Fake-data end-to-end tests for the classic-texts manual acceptance (design
v4.6.1). The fake dataset reproduces the EXACT real stratum populations,
boundary chapter counts and zero-output chapters, so e2e asserts the real
frozen totals (609 rules + 382 MCQ) and every section 6.2 decision path.
Fully offline: no model API, no Phase 8, no network; fake outputs are
test_only=true and finalize refuses them.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import classic_acceptance_common as c
import classic_acceptance_fixtures as fixtures


@pytest.fixture(scope="module")
def big():
    base = fixtures.tmp_dir("acceptance_e2e")
    data, chman_path = fixtures.build_fake_dataset(base / "data")
    yield base, data, chman_path
    fixtures.rmtree_force(base)


def _sample(big, run_name):
    base, data, chman_path = big
    run = base / run_name
    run.mkdir(parents=True, exist_ok=True)
    fixtures.run_cli("classic_acceptance_sampling.py", "sample",
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(run))
    return run / "sample_manifest_v1.json"


def _packet(big, run, sm_path, expansion=None, producing_report=None,
            producing_primary=None, producing_second=None,
            producing_arbitration=None):
    base, data, chman_path = big
    args = ["classic_acceptance_review.py", "packet", "--sample-manifest", str(sm_path)]
    if expansion:
        args += ["--expansion-manifest", str(expansion)]
        # P0/F19: an expansion must carry its producing EXPAND decision report
        # AND the full R1 evidence bundle (report is recomputed from them).
        args += ["--decision-report", str(producing_report)]
        args += ["--producing-primary", str(producing_primary)]
        if producing_second:
            args += ["--producing-second", str(producing_second)]
        if producing_arbitration:
            args += ["--producing-arbitration", str(producing_arbitration)]
    args += ["--chapter-manifest", str(chman_path), "--data-root", str(data),
             "--out", str(run)]
    fixtures.run_cli(*args)
    return run / "review_packet_v1.json"


def _decide(big, run, primary, sm_path, second=None, arbitration=None,
            expansion=None, producing_report=None, producing_primary=None,
            producing_second=None, producing_arbitration=None):
    base, data, chman_path = big
    args = ["classic_acceptance_review.py", "decide", "--primary", str(primary)]
    if second:
        args += ["--second", str(second)]
    if arbitration:
        args += ["--arbitration", str(arbitration)]
    if expansion:
        args += ["--expansion-manifest", str(expansion)]
        args += ["--decision-report", str(producing_report)]
        args += ["--producing-primary", str(producing_primary)]
        if producing_second:
            args += ["--producing-second", str(producing_second)]
        if producing_arbitration:
            args += ["--producing-arbitration", str(producing_arbitration)]
    args += ["--sample-manifest", str(sm_path), "--chapter-manifest", str(chman_path),
             "--data-root", str(data), "--out", str(run)]
    fixtures.run_cli(*args)
    return fixtures.read_json(run / "decision_report_v1.json")


def test_e2e_sample_totals(big):
    sm_path = _sample(big, "run_totals")
    sm = fixtures.read_json(sm_path)
    assert sm["totals"] == {"rule": {"random": 342, "boundary": 267, "total": 609},
                            "mcq": {"random": 188, "boundary": 194, "total": 382}}
    assert sm["k_table"]["sanmingtonghui"]["mcq"]["8"] == 7


def test_e2e_accept(big):
    run = big[0] / "run_accept"
    sm_path = _sample(big, "run_accept")
    packet = _packet(big, run, sm_path)
    assert len(fixtures.read_json(packet)["items"]) == 991
    primary = fixtures.make_primary(packet, run / "primary_review_package_v1.json")
    report = _decide(big, run, primary, sm_path)
    assert report["verdict"] == "ACCEPT"
    assert report["fired_rules"] == []
    assert report["second_review_sha256"] is None
    assert report["test_only"] is True
    assert report["metrics"]["zipingzhenquan"]["rule"]["critical_rate"] == "0/5"


def test_e2e_boundary_critical_reject(big):
    run = big[0] / "run_boundary"
    sm_path = _sample(big, "run_boundary")
    sm = fixtures.read_json(sm_path)
    bid = sm["boundary_samples"]["sanmingtonghui"]["rule"][0]
    packet = _packet(big, run, sm_path)
    primary = fixtures.make_primary(
        packet, run / "primary_review_package_v1.json",
        {("sanmingtonghui", "rule", bid): ("FAIL", [fixtures.critical()])})
    second = fixtures.make_second(primary, run / "second_review_receipt_v1.json")
    report = _decide(big, run, primary, sm_path, second=second)
    assert report["verdict"] == "REJECT"
    assert report["fired_rules"] == ["BOUNDARY"]


def test_e2e_boundary_arbitration(big):
    run = big[0] / "run_arbitration"
    sm_path = _sample(big, "run_arbitration")
    sm = fixtures.read_json(sm_path)
    bid = sm["boundary_samples"]["sanmingtonghui"]["rule"][0]
    ref = ("sanmingtonghui", "rule", bid, 0)
    packet = _packet(big, run, sm_path)
    primary = fixtures.make_primary(
        packet, run / "primary_review_package_v1.json",
        {("sanmingtonghui", "rule", bid): ("FAIL", [fixtures.critical()])})
    second = fixtures.make_second(primary, run / "second_review_receipt_v1.json",
                                  agree={ref: False})
    arb = fixtures.make_arbitration(primary, second, run / "arbitration_receipt_v1.json")
    report = _decide(big, run, primary, sm_path, second=second, arbitration=arb)
    assert report["verdict"] == "REJECT" and report["fired_rules"] == ["BOUNDARY"]
    arb2 = fixtures.make_arbitration(primary, second, run / "arbitration_receipt_v2.json",
                                     decisions={ref: "non_critical"})
    report2 = _decide(big, run, primary, sm_path, second=second, arbitration=arb2)
    # F3: finding deleted, no critical/minor numerator; sanmingtonghui rule
    # denominator is random rules (244) + boundary rules (267) = 511 (NOT 609,
    # which is the four-book rule total; P0-7 correction).
    assert report2["verdict"] == "ACCEPT"
    assert report2["metrics"]["sanmingtonghui"]["rule"]["critical_items"] == 0
    assert report2["metrics"]["sanmingtonghui"]["rule"]["minor_only_items"] == 0
    assert report2["metrics"]["sanmingtonghui"]["rule"]["reviewed"] == 511


def test_e2e_stratum_cascade_reject(big):
    run = big[0] / "run_cascade"
    sm_path = _sample(big, "run_cascade")
    sm = fixtures.read_json(sm_path)
    iid = sm["samples"]["sanmingtonghui"]["rule"]["2"][0]
    packet = _packet(big, run, sm_path)
    primary = fixtures.make_primary(
        packet, run / "primary_review_package_v1.json",
        {("sanmingtonghui", "rule", iid): ("FAIL", [fixtures.critical()])})
    second = fixtures.make_second(primary, run / "second_review_receipt_v1.json")
    report = _decide(big, run, primary, sm_path, second=second)
    assert report["verdict"] == "REJECT"
    assert report["fired_rules"] == ["STRATUM_CASCADE"]


def test_e2e_reject_gate(big):
    run = big[0] / "run_gate"
    sm_path = _sample(big, "run_gate")
    sm = fixtures.read_json(sm_path)
    mid = sm["samples"]["zipingzhenquan"]["mcq"]["1"][0]
    packet = _packet(big, run, sm_path)
    primary = fixtures.make_primary(
        packet, run / "primary_review_package_v1.json",
        {("zipingzhenquan", "mcq", mid): ("FAIL", [fixtures.critical()])})
    second = fixtures.make_second(primary, run / "second_review_receipt_v1.json")
    report = _decide(big, run, primary, sm_path, second=second)
    assert report["verdict"] == "REJECT"
    assert report["fired_rules"] == ["REJECT_GATE"]


def test_e2e_minor_gate_reject(big):
    run = big[0] / "run_minor"
    sm_path = _sample(big, "run_minor")
    sm = fixtures.read_json(sm_path)
    mid = sm["samples"]["zipingzhenquan"]["mcq"]["1"][0]
    packet = _packet(big, run, sm_path)
    primary = fixtures.make_primary(
        packet, run / "primary_review_package_v1.json",
        {("zipingzhenquan", "mcq", mid): ("PASS_WITH_MINOR", [fixtures.minor()])})
    report = _decide(big, run, primary, sm_path)
    assert report["verdict"] == "REJECT"
    assert report["fired_rules"] == ["REJECT_GATE"]


def _expand_setup(big, run_name):
    base, data, chman_path = big
    r1 = base / run_name
    sm_path = _sample(big, run_name)
    sm = fixtures.read_json(sm_path)
    verdicts = {}
    for s, n in (("1", 4), ("5", 6), ("6", 5)):
        for iid in sm["samples"]["sanmingtonghui"]["rule"][s][:n]:
            verdicts[("sanmingtonghui", "rule", iid)] = ("FAIL", [fixtures.critical()])
    packet = _packet(big, r1, sm_path)
    primary = fixtures.make_primary(packet, r1 / "primary_review_package_v1.json", verdicts)
    second = fixtures.make_second(primary, r1 / "second_review_receipt_v1.json")
    report = _decide(big, r1, primary, sm_path, second=second)
    assert report["verdict"] == "EXPAND"
    fixtures.run_cli("classic_acceptance_sampling.py", "expand",
                     "--sample-manifest", str(sm_path),
                     "--decision-report", str(r1 / "decision_report_v1.json"),
                     "--primary", str(primary), "--second", str(second),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(r1))
    return base, data, chman_path, r1, sm_path, sm, packet, primary, second, verdicts


def test_e2e_expand_then_accept(big):
    base, data, chman_path = big
    base, data, chman_path, r1, sm_path, sm, packet, primary, second, verdicts = \
        _expand_setup(big, "run_expand_r1")
    assert fixtures.read_json(r1 / "decision_report_v1.json")["pending_expands"] == \
        [{"book": "sanmingtonghui", "type": "rule"}]
    rep1 = fixtures.read_json(r1 / "decision_report_v1.json")
    assert rep1["metrics"]["sanmingtonghui"]["rule"]["critical_rate"] == "15/511"
    exp_path = r1 / "expansion_manifest_v1.json"
    exp = fixtures.read_json(exp_path)
    assert sum(info["added"] for info in
               exp["expansions"]["sanmingtonghui"]["rule"].values()) == 244
    old_ids = set()
    for ids in sm["samples"]["sanmingtonghui"]["rule"].values():
        old_ids.update(ids)
    old_ids.update(sm["boundary_samples"]["sanmingtonghui"]["rule"])
    new_ids = set()
    for info in exp["expansions"]["sanmingtonghui"]["rule"].values():
        new_ids.update(info["new_ids"])
    assert not (new_ids & old_ids)
    r2 = base / "run_expand_r2"
    r1_report = r1 / "decision_report_v1.json"
    packet2 = _packet(big, r2, sm_path, expansion=exp_path,
                      producing_report=r1_report,
                      producing_primary=primary, producing_second=second)
    assert len(fixtures.read_json(packet2)["items"]) == 1235
    primary2 = fixtures.make_primary(packet2, r2 / "primary_review_package_v1.json", verdicts)
    second2 = fixtures.make_second(primary2, r2 / "second_review_receipt_v1.json")
    report2 = _decide(big, r2, primary2, sm_path, second=second2,
                      expansion=exp_path, producing_report=r1_report,
                      producing_primary=primary, producing_second=second)
    assert report2["verdict"] == "ACCEPT"
    assert report2["expanded_pairs"] == [{"book": "sanmingtonghui", "type": "rule"}]
    assert report2["metrics"]["sanmingtonghui"]["rule"]["critical_rate"] == "15/755"


def test_e2e_expanded_pair_fail_closed(big):
    base, data, chman_path, r1, sm_path, sm, packet, primary, second, verdicts = \
        _expand_setup(big, "run_fc_r1")
    exp_path = r1 / "expansion_manifest_v1.json"
    exp = fixtures.read_json(exp_path)
    new_by_stratum = exp["expansions"]["sanmingtonghui"]["rule"]
    picks = (new_by_stratum["3"]["new_ids"][:2] + new_by_stratum["7"]["new_ids"][:3]
             + new_by_stratum["9"]["new_ids"][:11])
    assert len(picks) == 16
    for iid in picks:
        verdicts[("sanmingtonghui", "rule", iid)] = ("FAIL", [fixtures.critical()])
    r2 = base / "run_fc_r2"
    r1_report = r1 / "decision_report_v1.json"
    packet2 = _packet(big, r2, sm_path, expansion=exp_path,
                      producing_report=r1_report,
                      producing_primary=primary, producing_second=second)
    primary2 = fixtures.make_primary(packet2, r2 / "primary_review_package_v1.json", verdicts)
    second2 = fixtures.make_second(primary2, r2 / "second_review_receipt_v1.json")
    report2 = _decide(big, r2, primary2, sm_path, second=second2,
                      expansion=exp_path, producing_report=r1_report,
                      producing_primary=primary, producing_second=second)
    assert report2["verdict"] == "REJECT"
    assert report2["fired_rules"] == ["EXPAND_GATE"]
    assert report2["metrics"]["sanmingtonghui"]["rule"]["critical_rate"] == "31/755"


def test_e2e_producing_report_byte_tampering_rejected(big):
    # P0-2: the producing EXPAND report must match the recomputed verdict at
    # the RAW on-disk byte level. CRLF, trailing whitespace, reordered keys
    # and duplicate JSON keys all survive a parse round-trip but must be
    # rejected by both the consumer (packet) and the producer (expand).
    import json as _json
    base, data, chman_path = big
    r1 = base / "run_byte_tamper"
    sm_path = _sample(big, "run_byte_tamper")
    sm = fixtures.read_json(sm_path)
    verdicts = {}
    for s, n in (("1", 4), ("5", 6), ("6", 5)):
        for iid in sm["samples"]["sanmingtonghui"]["rule"][s][:n]:
            verdicts[("sanmingtonghui", "rule", iid)] = ("FAIL", [fixtures.critical()])
    packet = _packet(big, r1, sm_path)
    primary = fixtures.make_primary(packet, r1 / "primary_review_package_v1.json", verdicts)
    second = fixtures.make_second(primary, r1 / "second_review_receipt_v1.json")
    report = _decide(big, r1, primary, sm_path, second=second)
    assert report["verdict"] == "EXPAND"
    real_path = r1 / "decision_report_v1.json"
    canonical = real_path.read_bytes()

    def expect_reject(label, payload, subcmd):
        tampered = r1 / f"report_{label}.json"
        tampered.write_bytes(payload)
        if subcmd == "packet":
            cmd = ["classic_acceptance_review.py", "packet",
                   "--sample-manifest", str(sm_path),
                   "--chapter-manifest", str(chman_path),
                   "--data-root", str(data), "--out", str(r1 / f"pkt_{label}"),
                   "--expansion-manifest", str(r1 / "expansion_manifest_v1.json"),
                   "--decision-report", str(tampered),
                   "--producing-primary", str(primary),
                   "--producing-second", str(second)]
        else:
            cmd = ["classic_acceptance_sampling.py", "expand",
                   "--sample-manifest", str(sm_path),
                   "--decision-report", str(tampered),
                   "--primary", str(primary), "--second", str(second),
                   "--chapter-manifest", str(chman_path),
                   "--data-root", str(data), "--out", str(r1 / f"exp_{label}")]
        r = fixtures.run_cli_result(cmd[0], *cmd[1:])
        assert not r.timed_out and r.returncode != 0, f"{label}/{subcmd} unexpectedly passed"
        assert "bytes do not match" in r.stdout + r.stderr, (label, r.stdout, r.stderr)

    # a genuine expansion manifest must exist for the packet consumer path
    fixtures.run_cli("classic_acceptance_sampling.py", "expand",
                     "--sample-manifest", str(sm_path),
                     "--decision-report", str(real_path),
                     "--primary", str(primary), "--second", str(second),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(r1))
    reordered = _json.dumps(
        {k: report[k] for k in reversed(list(report.keys()))},
        indent=2, ensure_ascii=False).encode("utf-8")
    cases = {
        "crlf": canonical.replace(b"\n", b"\r\n"),
        "trailing_ws": canonical + b"\n",
        "reordered": reordered,
        "dup_key": canonical.replace(b'"verdict": "EXPAND"',
                                     b'"verdict": "ACCEPT", "verdict": "EXPAND"', 1),
    }
    for label, payload in cases.items():
        expect_reject(label, payload, "packet")
        expect_reject(label, payload, "expand")


def _r2_primary_covering_expansion(sm, exp, sm_path, exp_path, chman, out_path):
    # Build an all-PASS round-2 primary that covers BOTH the original sample
    # and every expansion new_id, binds the sample manifest SHA and the
    # expansion manifest raw-byte SHA. The chapter manifest maps every
    # sanmingtonghui id to its source chapter (expansion new_ids carry the
    # smth_ prefix, not the tiny_ prefix, so the chapter cannot be parsed from
    # the id alone).
    chapter_of = {}
    for ch in chman["chapters"]:
        for iid in ch["rule_ids"] + ch["mcq_ids"]:
            chapter_of[iid] = ch["chapter_index"]
    items = []

    def add(book, item_type, iid):
        sc = chapter_of.get(iid, 1) if book == "sanmingtonghui" else 1
        items.append({"item": {"book": book, "type": item_type, "id": iid,
                               "source_chapter": sc},
                      "verdict": "PASS", "findings": []})

    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    add(book, item_type, iid)
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            add("sanmingtonghui", item_type, iid)
    for book, types in exp["expansions"].items():
        for item_type, strata in types.items():
            for info in strata.values():
                for iid in info["new_ids"]:
                    add(book, item_type, iid)
    primary = {"schema_version": "1.0", "kind": "primary_review_package",
               "sample_manifest_sha256": fixtures.sha256_file(sm_path),
               "expansion_manifests_sha256": [fixtures.sha256_file(exp_path)],
               "items": items, "overall_stats": {}, "zero_output_report": [],
               "reviewer_list": ["e2e-r1"]}
    fixtures.write_json(out_path, primary)
    return out_path


def test_e2e_validate_primary_expansion_genuine_then_tamper(big):
    # P0/F19: validate-primary runs the SAME producing-evidence authorization
    # chain as decide/finalize. Genuine path: a real R1 EXPAND bundle -> genuine
    # expansion -> a round-2 primary that covers the expansion and binds its
    # SHA -> validate-primary exits 0. Then the SAME expansion body is hand-
    # forged (a new_id swapped) while keeping the genuine producing report;
    # validate-primary must reject via the reconstruct-and-compare gate. This
    # proves expansion validation is actually exercised, not just earlier
    # flag/evidence gates.
    import copy
    base, data, chman_path = big
    r1 = base / "run_vp_exp"
    sm_path = _sample(big, "run_vp_exp")
    sm = fixtures.read_json(sm_path)
    verdicts = {}
    for s, n in (("1", 4), ("5", 6), ("6", 5)):
        for iid in sm["samples"]["sanmingtonghui"]["rule"][s][:n]:
            verdicts[("sanmingtonghui", "rule", iid)] = ("FAIL", [fixtures.critical()])
    packet = _packet(big, r1, sm_path)
    primary = fixtures.make_primary(packet, r1 / "primary_review_package_v1.json", verdicts)
    second = fixtures.make_second(primary, r1 / "second_review_receipt_v1.json")
    report = _decide(big, r1, primary, sm_path, second=second)
    assert report["verdict"] == "EXPAND"
    report_path = r1 / "decision_report_v1.json"
    fixtures.run_cli("classic_acceptance_sampling.py", "expand",
                     "--sample-manifest", str(sm_path),
                     "--decision-report", str(report_path),
                     "--primary", str(primary), "--second", str(second),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data), "--out", str(r1))
    exp_path = r1 / "expansion_manifest_v1.json"
    exp = fixtures.read_json(exp_path)
    chman = fixtures.read_json(chman_path)
    r2_primary = _r2_primary_covering_expansion(
        sm, exp, sm_path, exp_path, chman, r1 / "r2_primary.json")
    common = [sys.executable, str(fixtures.SCRIPTS / "classic_acceptance_review.py"),
              "validate-primary", "--primary", str(r2_primary),
              "--sample-manifest", str(sm_path), "--chapter-manifest", str(chman_path),
              "--data-root", str(data),
              "--expansion-manifest", None,
              "--decision-report", str(report_path),
              "--producing-primary", str(primary),
              "--producing-second", str(second)]
    # genuine expansion -> exit 0
    ok_cmd = list(common)
    ok_cmd[ok_cmd.index(None)] = str(exp_path)
    ok = fixtures.run_argv_result(ok_cmd)
    assert not ok.timed_out and ok.returncode == 0, ok.stdout + ok.stderr
    assert "primary review package OK" in ok.stdout
    # tampered expansion (swap a new_id for an unsampled id) -> rejected by
    # reconstruct-and-compare; the producing report remains genuine, so the
    # failure is proven to come from expansion body validation.
    forged = copy.deepcopy(exp)
    strata = forged["expansions"]["sanmingtonghui"]["rule"]
    target_key = next(k for k, info in strata.items() if info["new_ids"])
    swapped = strata[target_key]["new_ids"][0]
    strata[target_key]["new_ids"][0] = "smth_999_r999"
    forged_path = r1 / "forged_expansion.json"
    fixtures.write_json(forged_path, forged)
    bad_cmd = list(common)
    bad_cmd[bad_cmd.index(None)] = str(forged_path)
    bad = fixtures.run_argv_result(bad_cmd)
    assert not bad.timed_out and bad.returncode != 0
    assert "does not match the manifest reconstructed" in (bad.stdout + bad.stderr)
    assert swapped != "smth_999_r999"


def _decide_paths(run, primary, sm_path, chman_path, data_root):
    fixtures.run_cli("classic_acceptance_review.py", "decide", "--primary", str(primary),
                     "--sample-manifest", str(sm_path),
                     "--chapter-manifest", str(chman_path),
                     "--data-root", str(data_root), "--out", str(run))
    return fixtures.read_json(run / "decision_report_v1.json")


def test_e2e_integrity_reject(big):
    base, data, chman_path = big
    for name, rel in (("raw", f"{fixtures.FAKE_SNAP}/extracted/raw_025.txt"),
                      ("drift", "knowledge_base/classic_texts/qiongtongbaojian/quarantine_rules.jsonl")):
        cop = fixtures.tmp_dir(f"acceptance_e2e_integrity_{name}")
        shutil.copytree(data, cop / "data")
        (cop / "data" / rel).unlink()
        run = cop / "run"
        run.mkdir(parents=True, exist_ok=True)
        fixtures.run_cli("classic_acceptance_sampling.py", "sample",
                         "--chapter-manifest", str(chman_path),
                         "--data-root", str(cop / "data"), "--out", str(run))
        sm_path = run / "sample_manifest_v1.json"
        args = ["classic_acceptance_review.py", "packet", "--sample-manifest", str(sm_path),
                "--chapter-manifest", str(chman_path), "--data-root", str(cop / "data"),
                "--out", str(run)]
        fixtures.run_cli(*args)
        primary = fixtures.make_primary(run / "review_packet_v1.json",
                                        run / "primary_review_package_v1.json")
        report = _decide_paths(run, primary, sm_path, chman_path, cop / "data")
        assert report["verdict"] == "REJECT"
        assert report["fired_rules"] == ["INTEGRITY"]
        assert report["integrity"]["source_missing_chapters"] == ([25] if name == "raw" else [])
        assert report["integrity"]["missing_drift_files"] == (
            [] if name == "raw" else
            ["knowledge_base/classic_texts/qiongtongbaojian/quarantine_rules.jsonl"])
        fixtures.rmtree_force(cop)
