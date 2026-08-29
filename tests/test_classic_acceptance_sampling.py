"""Tests for the classic-texts manual-acceptance tooling (design v4.6.1,
Approved LOCAL_ONLY). Layer 1: shared common module (frozen SEED encoding,
k formula, section 2.3 normalization, data sources, strict CLI parsing,
production frozen-input locking). Later tasks append sampling/review tests.
Everything runs offline; real-data tests read the frozen candidate commit
51eb92b via `git show` (no model API, no Phase 8).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import classic_acceptance_common as c
import classic_acceptance_fixtures as fixtures
import classic_acceptance_sampling as sampling


def test_length_prefixed_no_delimiter_ambiguity():
    assert (c.length_prefixed(b"ab") + c.length_prefixed(b"c")
            != c.length_prefixed(b"a") + c.length_prefixed(b"bc"))


def test_seed_matches_design():
    assert c.SEED_BYTES == bytes.fromhex("00a5c0de20260820")
    assert int.from_bytes(c.SEED_BYTES, "big") == c.SEED == 46655431411894304


def test_score_golden_vectors():
    assert c.sample_score("sanmingtonghui", "rule", 1, "smth_001_r0000") == \
        "c54f87a08f89fee93cc4f33b66f480b8c6e0c7601b100a1c306483aa2a2b2a73"
    assert c.expand_score("sanmingtonghui", "rule", 1, "smth_001_r0000") == \
        "4eb4053ed0c04a01b5d63d5f99aa6f95911f2c0add7410524607c32514781f0a"


def test_score_stable_and_distinct():
    args = ("sanmingtonghui", "rule", 1, "smth_001_r0001")
    assert c.sample_score(*args) == c.sample_score(*args)
    assert c.sample_score(*args) != c.sample_score("sanmingtonghui", "rule", 2, "smth_001_r0001")
    assert c.sample_score(*args) != c.sample_score("qiongtongbaojian", "rule", 1, "smth_001_r0001")
    assert c.sample_score(*args) != c.sample_score("sanmingtonghui", "mcq", 1, "smth_001_r0001")
    assert c.sample_score(*args) != c.expand_score(*args)


def test_round_half_up_and_compute_k():
    assert c.round_half_up_int(734, 100) == 7       # 7.34 -> 7 (F1 errata)
    assert c.round_half_up_int(1554, 100) == 16     # 15.54 -> 16
    assert c.round_half_up_int(242, 100) == 2
    assert c.compute_k(1542, 3) == 46
    assert c.compute_k(74, 3) == 5
    assert c.compute_k(367, 2) == 7                 # errata: NOT 8
    assert c.compute_k(155, 2) == 5


def test_normalize_for_source_match():
    assert c.normalize_for_source_match("甲己 合\r\n而不 合\t") == "甲己合而不合"
    assert c.normalize_for_source_match("，。；") == "，。；"


def test_dir_source_read_and_exists():
    base = fixtures.tmp_dir("acceptance_common")
    try:
        (base / "sub").mkdir()
        (base / "sub" / "f.txt").write_bytes("内容\n".encode("utf-8"))
        src = c.DirSource(base)
        assert src.read_bytes("sub/f.txt") == "内容\n".encode("utf-8")
        assert src.exists("sub/f.txt")
        assert not src.exists("sub/missing.txt")
        with pytest.raises(RuntimeError, match="missing path"):
            src.read_bytes("sub/missing.txt")
    finally:
        fixtures.rmtree_force(base)


def test_git_source_rejects_short_commit():
    with pytest.raises(RuntimeError, match="40-hex"):
        c.GitSource(Path("."), "51eb92b")


def test_git_source_reads_frozen_candidate():
    src = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
    blob = src.read_bytes("knowledge_base/classic_texts/zipingzhenquan/all_rules.json")
    assert blob.startswith(b"[")
    assert src.exists("knowledge_base/classic_texts/zipingzhenquan/all_rules.json")
    assert not src.exists("knowledge_base/classic_texts/zipingzhenquan/NOPE.json")


# ---- strict CLI parsing (F16) ----

def test_parse_flags_unknown_flag_rejected():
    with pytest.raises(RuntimeError, match="unknown flag"):
        c.parse_flags(["--bogus", "x"], allowed={"out"})


def test_parse_flags_missing_value_rejected():
    with pytest.raises(RuntimeError, match="requires a value"):
        c.parse_flags(["--out"], allowed={"out"})


def test_parse_flags_unexpected_positional_rejected():
    with pytest.raises(RuntimeError, match="unexpected positional"):
        c.parse_flags(["leftover"], allowed={"out"})


def test_parse_flags_repeatable_and_required():
    flags, positional = c.parse_flags(
        ["--out", "o", "--exp", "a", "--exp", "b"],
        allowed={"out"}, repeatable={"exp"})
    assert positional == []
    assert flags["out"] == ["o"]
    assert flags["exp"] == ["a", "b"]
    with pytest.raises(RuntimeError, match="exactly once"):
        c.flag1(flags, "missing")
    # a repeatable flag must not be passed via single-value helpers
    with pytest.raises(RuntimeError, match="at most once"):
        c.flag_opt(flags, "exp")


def test_build_source_git_locks_to_frozen_commit():
    # GitSource rejects non-40-hex at construction; build_source only accepts
    # the frozen candidate commit (verified by verify_frozen_inputs).
    with pytest.raises(RuntimeError, match="40-hex"):
        c.GitSource(fixtures.ROOT, "51eb92b")
    # exactly-one-mode is enforced before any commit check
    with pytest.raises(RuntimeError, match="exactly one"):
        c.build_source({})
    with pytest.raises(RuntimeError, match="exactly one"):
        c.build_source({"candidate-commit": [fixtures.COMMIT],
                        "data-root": [str(fixtures.ROOT)]})


# ---- production frozen-input locking (F13/F14) ----

def test_verify_frozen_inputs_passes_against_real_chain():
    # reads the real anchor record + runs the real --check (may take ~1 min)
    ch_path = fixtures.REPO_ROOT / "docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json"
    anchor = c.verify_frozen_inputs(fixtures.COMMIT, ch_path)
    assert anchor["expected_tag_oid"]
    assert anchor["overall_state"] == "LOCAL_FREEZE_VERIFIED / FORMAL_GATE_BLOCKED"


def test_verify_frozen_inputs_rejects_wrong_commit():
    ch_path = fixtures.REPO_ROOT / "docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json"
    with pytest.raises(RuntimeError, match="candidate_commit"):
        c.verify_frozen_inputs("0" * 40, ch_path)


def test_verify_frozen_inputs_rejects_nonfrozen_chapter_manifest():
    # F18: a CLI --chapter-manifest that is not the frozen one is rejected
    # before any data read.
    base = fixtures.tmp_dir("acceptance_frozen_ch")
    try:
        real = fixtures.CHAPTER_MANIFEST
        tampered = base / "ch.json"
        data = bytearray(real.read_bytes())
        data[len(data) // 2] ^= 0x01
        tampered.write_bytes(bytes(data))
        with pytest.raises(RuntimeError, match="chapter-manifest LF SHA"):
            c.verify_frozen_inputs(fixtures.COMMIT, tampered)
    finally:
        fixtures.rmtree_force(base)


def test_check_iso8601_accepts_timezone_and_rejects_bad_values():
    # timezone-qualified valid timestamps accepted (Z and offsets)
    c._check_iso8601("2026-08-23T00:00:00+08:00", "x")
    c._check_iso8601("2026-08-23T00:00:00Z", "x")
    c._check_iso8601("2026-08-23T12:34:56.789-05:00", "x")
    # bare timestamp without timezone rejected
    with pytest.raises(RuntimeError, match="timezone"):
        c._check_iso8601("2026-08-23T00:00:00", "x")
    # shape-valid but semantically impossible date/time/timezone rejected
    for bad in ("t", "yesterday", "2026-99-99T99:99:99+99:99",
                "2026-13-01T00:00:00+08:00", "not-a-timestamp"):
        with pytest.raises(RuntimeError):
            c._check_iso8601(bad, "x")


def test_sha256_file_raw_distinguishes_crlf(tmp_path=None):
    # F20: receipt SHA uses raw bytes; CRLF tampering changes the SHA.
    base = fixtures.tmp_dir("acceptance_raw_sha")
    try:
        p = base / "receipt.json"
        p.write_bytes(b'{"a": 1}\n')
        lf = c.sha256_file_raw(p)
        p.write_bytes(b'{"a": 1}\r\n')
        crlf = c.sha256_file_raw(p)
        assert lf != crlf
    finally:
        fixtures.rmtree_force(base)

def test_tiny_sample_totals_and_disjoint():
    base = fixtures.tmp_dir("acceptance_tiny")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        manifest = sampling.build_sample_manifest(
            man, source, {"kind": "dir", "root": str(data), "test_only": True}, chman_sha)
        assert manifest["test_only"] is True
        assert manifest["totals"] == {"rule": {"random": 25, "boundary": 2, "total": 27},
                                      "mcq": {"random": 25, "boundary": 2, "total": 27}}
        assert manifest["k_table"]["sanmingtonghui"] == {"rule": {"1": 5, "2": 5},
                                                         "mcq": {"1": 5, "2": 5}}
        assert manifest["boundary_samples"]["sanmingtonghui"]["rule"] == \
            ["tiny_001_r000", "tiny_001_r001"]
        bset = (set(manifest["boundary_samples"]["sanmingtonghui"]["rule"])
                | set(manifest["boundary_samples"]["sanmingtonghui"]["mcq"]))
        for book in c.BOOKS:
            for item_type in ("rule", "mcq"):
                for ids in manifest["samples"][book][item_type].values():
                    assert not (set(ids) & bset)
        again = sampling.build_sample_manifest(
            man, source, {"kind": "dir", "root": str(data), "test_only": True}, chman_sha)
        assert c.serialize_json(again) == c.serialize_json(manifest)
        eligible = [f"tiny_002_r{i:03d}" for i in range(6)] + \
                   [f"tiny_003_r{i:03d}" for i in range(6)]
        expected = sorted(sorted(eligible,
                                 key=lambda i: (c.sample_score("sanmingtonghui", "rule", 1, i), i))[:5])
        assert manifest["samples"]["sanmingtonghui"]["rule"]["1"] == expected
        assert manifest["chapter_manifest_sha256"] == fixtures.sha256_file(chman_path)
        assert manifest["normalization"]["function"] == "normalize_for_source_match"
    finally:
        fixtures.rmtree_force(base)


def test_load_chapter_manifest_rejects_bad_structures():
    base = fixtures.tmp_dir("acceptance_chman")
    try:
        bad_dup = {"chapters": [
            {"chapter_index": 1, "raw_source_path": "a.txt", "rule_ids": ["r1"], "mcq_ids": []},
            {"chapter_index": 1, "raw_source_path": "a.txt", "rule_ids": [], "mcq_ids": []}]}
        p = base / "dup.json"
        fixtures.write_json(p, bad_dup)
        with pytest.raises(RuntimeError, match="duplicate chapter_index"):
            sampling.load_chapter_manifest(p)
        bad_twice = {"chapters": [
            {"chapter_index": 1, "raw_source_path": "a.txt", "rule_ids": ["r1"], "mcq_ids": []},
            {"chapter_index": 2, "raw_source_path": "b.txt", "rule_ids": ["r1"], "mcq_ids": []}]}
        p2 = base / "twice.json"
        fixtures.write_json(p2, bad_twice)
        with pytest.raises(RuntimeError, match="multiple chapters"):
            sampling.load_chapter_manifest(p2)
    finally:
        fixtures.rmtree_force(base)


def test_tiny_cli_sample_strict_flags():
    base = fixtures.tmp_dir("acceptance_tiny_cli")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        out = base / "out"
        # unknown flag rejected
        r = fixtures.run_cli_result(
            "classic_acceptance_sampling.py", "sample", "--bogus", "x",
            "--chapter-manifest", str(chman_path),
            "--data-root", str(data), "--out", str(out))
        assert not r.timed_out and r.returncode != 0
        assert "unknown flag" in r.stdout + r.stderr
        # missing value rejected
        r = fixtures.run_cli_result(
            "classic_acceptance_sampling.py", "sample", "--chapter-manifest",
            "--data-root", str(data), "--out", str(out))
        assert not r.timed_out and r.returncode != 0
        assert "requires a value" in r.stdout + r.stderr
        # positional rejected
        r = fixtures.run_cli_result(
            "classic_acceptance_sampling.py", "sample", "positional",
            "--chapter-manifest", str(chman_path),
            "--data-root", str(data), "--out", str(out))
        assert not r.timed_out and r.returncode != 0
        assert "unexpected positional" in r.stdout + r.stderr
        # happy path
        fixtures.run_cli("classic_acceptance_sampling.py", "sample",
                         "--chapter-manifest", str(chman_path),
                         "--data-root", str(data), "--out", str(out))
        manifest = fixtures.read_json(out / "sample_manifest_v1.json")
        assert manifest["totals"]["rule"]["total"] == 27
        assert manifest["test_only"] is True
        assert manifest["generator"]["path"] == "scripts/classic_acceptance_sampling.py"
        assert len(manifest["generator"]["sha256_lf"]) == 64
        assert len(manifest["generator"]["blob_oid"]) == 40
        assert manifest["seed"] == {"hex": "00a5c0de20260820", "decimal": 46655431411894304}
    finally:
        fixtures.rmtree_force(base)


@pytest.fixture(scope="module")
def real_manifest():
    man, chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
    desc = {"kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False}
    return sampling.build_sample_manifest(man, source, desc, chman_sha), chman_sha


def test_real_totals_and_k(real_manifest):
    manifest, _ = real_manifest
    assert manifest["totals"] == {"rule": {"random": 342, "boundary": 267, "total": 609},
                                  "mcq": {"random": 188, "boundary": 194, "total": 382}}
    assert manifest["k_table"]["sanmingtonghui"]["rule"] == {
        "1": 46, "2": 5, "3": 21, "4": 9, "5": 40, "6": 38, "7": 33, "8": 15, "9": 37}
    assert manifest["k_table"]["sanmingtonghui"]["mcq"] == {
        "1": 16, "2": 5, "3": 12, "4": 5, "5": 25, "6": 24, "7": 17, "8": 7, "9": 17}
    assert manifest["k_table"]["qiongtongbaojian"] == {"rule": {"1": 69}, "mcq": {"1": 42}}
    assert manifest["k_table"]["ditiansui"] == {"rule": {"1": 24}, "mcq": {"1": 13}}
    assert manifest["k_table"]["zipingzhenquan"] == {"rule": {"1": 5}, "mcq": {"1": 5}}
    assert manifest["test_only"] is False


def test_real_boundary_and_disjoint(real_manifest):
    manifest, _ = real_manifest
    chman = json.loads(c.lf_bytes(fixtures.CHAPTER_MANIFEST.read_bytes()).decode("utf-8"))
    expected = {"rule": [], "mcq": []}
    for ch in chman["chapters"]:
        if ch["chapter_index"] in c.BOUNDARY_CHAPTERS:
            expected["rule"].extend(ch["rule_ids"])
            expected["mcq"].extend(ch["mcq_ids"])
    assert manifest["boundary_samples"]["sanmingtonghui"] == {
        "rule": sorted(expected["rule"]), "mcq": sorted(expected["mcq"])}
    bset = set(expected["rule"]) | set(expected["mcq"])
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in manifest["samples"][book][item_type].values():
                assert not (set(ids) & bset)


def test_real_bindings_to_frozen_chain(real_manifest):
    manifest, chman_sha = real_manifest
    anchor = json.loads(fixtures.ANCHOR_RECORD.read_text(encoding="utf-8"))
    assert chman_sha == anchor["manifests"]["2026-08-20-classic-texts-chapter-identity-manifest.json"]
    identity_sha = c.sha256_bytes(c.lf_bytes(fixtures.IDENTITY_MANIFEST.read_bytes()))
    assert identity_sha == anchor["manifests"]["2026-08-20-classic-texts-candidate-identity-manifest.json"]
    identity = json.loads(fixtures.IDENTITY_MANIFEST.read_text(encoding="utf-8"))
    frozen = {f["path"]: f["sha256_lf"] for f in identity["groups"]["output_files"]}
    assert manifest["data_file_sha256_lf"] == frozen
    common_path = fixtures.SCRIPTS / "classic_acceptance_common.py"
    assert manifest["normalization"]["sha256_lf"] == c.sha256_bytes(c.lf_bytes(common_path.read_bytes()))


def test_real_determinism(real_manifest):
    manifest, _ = real_manifest
    man, chman_sha = sampling.load_chapter_manifest(fixtures.CHAPTER_MANIFEST)
    source = c.GitSource(fixtures.ROOT, fixtures.COMMIT)
    again = sampling.build_sample_manifest(
        man, source, {"kind": "git", "candidate_commit": fixtures.COMMIT, "test_only": False}, chman_sha)
    assert c.serialize_json(again) == c.serialize_json(manifest)


def test_validate_sample_manifest_roundtrip_cross_mode_and_tamper():
    # F19 reconstruct-and-compare: only a manifest the current code would
    # produce from THIS chapter manifest/source validates; right-shaped
    # hand-crafted or tampered manifests fail closed.
    import copy
    base = fixtures.tmp_dir("acceptance_val_sm")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        desc = {"kind": "dir", "root": str(data), "test_only": True}
        sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
        # roundtrip: the manifest just built validates in fake mode (fake mode
        # binds the fake chapter manifest's ACTUAL LF SHA, P0-1)
        sampling.validate_sample_manifest(sm, man, source, desc, chman_sha,
                                          expected_test_only=True)
        # cross-mode: retagged test_only=False rejected in fake mode
        with pytest.raises(RuntimeError, match="cross-mode"):
            sampling.validate_sample_manifest(dict(sm, test_only=False), man,
                                              source, desc, chman_sha,
                                              expected_test_only=True)
        # fake artifacts cannot enter production mode even when retagged
        # test_only=False: production requires the FROZEN chapter manifest,
        # and the fake chapter manifest's SHA is not it (P0-1)
        with pytest.raises(RuntimeError, match="frozen chapter manifest"):
            sampling.validate_sample_manifest(dict(sm, test_only=False), man,
                                              source, desc, chman_sha,
                                              expected_test_only=False)
        # a right-shaped hand-crafted manifest (empty k_table/samples, as the
        # old shape-only validator accepted) does NOT validate
        hand = {"schema_version": "1.0", "kind": "sample_manifest_v1",
                "algorithm_version": "1.0",
                "seed": {"hex": c.SEED_BYTES.hex(), "decimal": c.SEED_DECIMAL},
                "data_source": desc, "test_only": True,
                "chapter_manifest_sha256": chman_sha,
                "data_file_sha256_lf": {},
                "generator": sm["generator"],
                "normalization": sm["normalization"],
                "strata": [], "k_table": {b: {} for b in c.BOOKS},
                "boundary_chapters": c.BOUNDARY_CHAPTERS,
                "samples": {b: {} for b in c.BOOKS},
                "boundary_samples": {b: {"rule": [], "mcq": []} for b in c.BOOKS},
                "totals": {}}
        with pytest.raises(RuntimeError, match="reconstructed"):
            sampling.validate_sample_manifest(hand, man, source, desc, chman_sha,
                                              expected_test_only=True)
        # every tampered field is rejected: k_table, sample ids, totals,
        # boundary set, data-file SHA, generator identity, chapter SHA
        for mutate in (
            lambda m: m["k_table"]["sanmingtonghui"]["rule"].__setitem__("1", 4),
            lambda m: m["samples"]["sanmingtonghui"]["rule"]["1"].append("tiny_002_r005"),
            lambda m: m["totals"]["rule"].__setitem__("total", 26),
            lambda m: m["boundary_samples"]["sanmingtonghui"]["rule"].append("tiny_001_r000"),
            lambda m: m["data_file_sha256_lf"].__setitem__("x", "0" * 64),
            lambda m: m["generator"].__setitem__("sha256_lf", "a" * 64),
            lambda m: m.__setitem__("chapter_manifest_sha256", "0" * 64),
        ):
            bad = copy.deepcopy(sm)
            mutate(bad)
            with pytest.raises(RuntimeError):
                sampling.validate_sample_manifest(bad, man, source, desc, chman_sha,
                                                  expected_test_only=True)
    finally:
        fixtures.rmtree_force(base)


def test_expand_formula_min_and_disjoint():
    # The per-stratum formula added=min(k, remaining), disjointness, and the
    # expansion body are pure functions of the sample manifest; test them
    # directly (the CLI authorization/recomputation path is tested below).
    base = fixtures.tmp_dir("acceptance_expand")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        desc = {"kind": "dir", "root": str(data), "test_only": True}
        sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
        s1_all = [f"tiny_002_r{i:03d}" for i in range(6)] + \
                 [f"tiny_003_r{i:03d}" for i in range(6)]
        s2_all = [f"tiny_085_r{i:03d}" for i in range(6)]
        sampled_s1 = sm["samples"]["sanmingtonghui"]["rule"]["1"]
        sampled_s2 = sm["samples"]["sanmingtonghui"]["rule"]["2"]
        report_sha = "1" * 64
        em = sampling.build_expansion_manifest(
            sm, [{"book": "sanmingtonghui", "type": "rule"}], 1,
            man, source, desc, c.sha256_bytes(c.serialize_json(sm)), report_sha)
        assert em["kind"] == "expansion_manifest_v1"
        assert em["round"] == 1
        rule_exp = em["expansions"]["sanmingtonghui"]["rule"]
        # stratum 1 (chapters 1,2,3): full_population includes the boundary
        # chapter 1 (design 6.3), so population = 2+6+6 = 14; remaining =
        # 14 - 2 boundary - 5 initial = 7 -> added = min(5, 7) = 5
        assert rule_exp["1"]["population"] == 14
        assert rule_exp["1"]["initial_random"] == 5
        assert rule_exp["1"]["boundary"] == 2
        assert rule_exp["1"]["k"] == 5
        assert rule_exp["1"]["added"] == 5
        # new_ids = the expand_score-ranked top-`added` of the 7 remaining
        # ids (NOT all 7: added caps the pick at k=5).
        remaining_s1 = sorted(set(s1_all) - set(sampled_s1))
        ranked_s1 = sorted(
            remaining_s1,
            key=lambda iid: (c.expand_score("sanmingtonghui", "rule", 1, iid), iid))
        assert rule_exp["1"]["new_ids"] == sorted(ranked_s1[:rule_exp["1"]["added"]])
        # stratum 2: population 6, initial random 5, remaining 1
        # -> added = min(k=5, remaining=1) = 1 (the min-formula branch)
        assert rule_exp["2"]["population"] == 6
        assert rule_exp["2"]["initial_random"] == 5
        assert rule_exp["2"]["boundary"] == 0
        assert rule_exp["2"]["k"] == 5
        assert rule_exp["2"]["added"] == 1
        assert rule_exp["2"]["new_ids"] == sorted(set(s2_all) - set(sampled_s2))
        assert em["totals"]["sanmingtonghui"]["rule"] == 6
        old_ids = set()
        for ids in sm["samples"]["sanmingtonghui"]["rule"].values():
            old_ids.update(ids)
        old_ids.update(sm["boundary_samples"]["sanmingtonghui"]["rule"])
        new_ids = set()
        for info in em["expansions"]["sanmingtonghui"]["rule"].values():
            new_ids.update(info["new_ids"])
        assert not (new_ids & old_ids)
    finally:
        fixtures.rmtree_force(base)


def _all_pass_primary(sm, sm_path):
    items = []
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sm["samples"][book][item_type].values():
                for iid in ids:
                    sc = int(iid.split("_")[1]) if book == "sanmingtonghui" else 1
                    items.append({"item": {"book": book, "type": item_type, "id": iid,
                                           "source_chapter": sc},
                                  "verdict": "PASS", "findings": []})
    for item_type in ("rule", "mcq"):
        for iid in sm["boundary_samples"]["sanmingtonghui"][item_type]:
            items.append({"item": {"book": "sanmingtonghui", "type": item_type,
                                   "id": iid,
                                   "source_chapter": int(iid.split("_")[1])},
                          "verdict": "PASS", "findings": []})
    return {"schema_version": "1.0", "kind": "primary_review_package",
            "sample_manifest_sha256": c.sha256_file_raw(sm_path),
            "expansion_manifests_sha256": [], "items": items,
            "overall_stats": {}, "zero_output_report": [],
            "reviewer_list": ["r1"]}


def test_expand_cli_rejects_handcrafted_expand_report():
    # P0: a hand-crafted decision report claiming verdict=EXPAND (but produced
    # from an all-PASS primary, whose real verdict is ACCEPT) must be rejected
    # by cmd_expand's verdict RECOMPUTATION, not just shape checks.
    base = fixtures.tmp_dir("acceptance_expand_authz")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        desc = {"kind": "dir", "root": str(data), "test_only": True}
        sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
        sm_path = base / "sample_manifest_v1.json"
        sm_path.write_bytes(c.serialize_json(sm))
        primary = _all_pass_primary(sm, sm_path)
        p_path = base / "primary.json"
        p_path.write_bytes(c.serialize_json(primary))
        forged = {"schema_version": "1.0", "kind": "decision_report_v1",
                  "test_only": True,
                  "primary_sha256": c.sha256_file_raw(p_path),
                  "second_review_sha256": None, "arbitration_sha256": None,
                  "sample_manifest_sha256": c.sha256_file_raw(sm_path),
                  "expansion_manifests_sha256": [], "expanded_pairs": [],
                  "adjudication": {"canonical_findings": [],
                                   "second_review_entries": 0,
                                   "arbitration_entries": 0},
                  "metrics": {}, "stratum_rule_metrics": {},
                  "boundary_critical_items": {},
                  "integrity": {"source_missing_chapters": [],
                                "missing_drift_files": []},
                  "fired_rules": ["EXPAND_GATE"], "verdict": "EXPAND",
                  "pending_expands": [{"book": "sanmingtonghui", "type": "rule"}]}
        r_path = base / "decision_report_v1.json"
        r_path.write_bytes(c.serialize_json(forged))
        result = fixtures.run_cli_result(
            "classic_acceptance_sampling.py", "expand",
            "--sample-manifest", str(sm_path),
            "--decision-report", str(r_path), "--primary", str(p_path),
            "--chapter-manifest", str(chman_path),
            "--data-root", str(data), "--out", str(base / "out"))
        assert not result.timed_out and result.returncode != 0
        out = result.stdout + result.stderr
        assert "recomput" in out or "does not match" in out
    finally:
        fixtures.rmtree_force(base)


def test_expand_cli_requires_primary_flag():
    # P0: --primary is now mandatory for recomputation; missing it is rejected
    # by the strict CLI parser (F16) rather than silently trusting the report.
    base = fixtures.tmp_dir("acceptance_expand_flags")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        desc = {"kind": "dir", "root": str(data), "test_only": True}
        sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
        sm_path = base / "sample_manifest_v1.json"
        sm_path.write_bytes(c.serialize_json(sm))
        r_path = base / "decision_report_v1.json"
        r_path.write_bytes(c.serialize_json({"kind": "decision_report_v1"}))
        result = fixtures.run_cli_result(
            "classic_acceptance_sampling.py", "expand",
            "--sample-manifest", str(sm_path),
            "--decision-report", str(r_path),
            "--chapter-manifest", str(chman_path),
            "--data-root", str(data), "--out", str(base / "out"))
        assert not result.timed_out and result.returncode != 0
        assert "exactly once" in (result.stdout + result.stderr) or \
               "requires" in (result.stdout + result.stderr)
    finally:
        fixtures.rmtree_force(base)


def test_validate_expansion_manifest_requires_expand_authorization():
    # P0: even a self-consistent expansion body is rejected without a producing
    # EXPAND report; a report with verdict != EXPAND or a pair not in
    # pending_expands is rejected; packet/decide must supply that report.
    import copy
    base = fixtures.tmp_dir("acceptance_val_exp_authz")
    try:
        data, chman_path = fixtures.build_tiny_dataset(base)
        man, chman_sha = sampling.load_chapter_manifest(chman_path)
        source = c.DirSource(data)
        desc = {"kind": "dir", "root": str(data), "test_only": True}
        sm = sampling.build_sample_manifest(man, source, desc, chman_sha)
        sm_sha = c.sha256_bytes(c.serialize_json(sm))
        pairs = [{"book": "sanmingtonghui", "type": "rule"}]
        report = {"schema_version": "1.0", "kind": "decision_report_v1",
                  "test_only": True, "sample_manifest_sha256": sm_sha,
                  "expansion_manifests_sha256": [], "expanded_pairs": [],
                  "verdict": "EXPAND", "pending_expands": pairs,
                  "decision_report_sha256": None}
        report_sha = c.sha256_bytes(c.serialize_json(report))
        em = sampling.build_expansion_manifest(sm, pairs, 1, man, source,
                                               desc, sm_sha, report_sha)
        # happy path: authorized EXPAND report
        sampling.validate_expansion_manifest(em, sm, man, source, desc, sm_sha,
                                             expected_test_only=True,
                                             report=report, report_sha=report_sha)
        # no report at all -> rejected
        with pytest.raises(RuntimeError, match="producing decision report is required"):
            sampling.validate_expansion_manifest(
                copy.deepcopy(em), sm, man, source, desc, sm_sha,
                expected_test_only=True, report=None, report_sha=None)
        # verdict ACCEPT -> rejected (not an EXPAND authorization)
        acc = dict(report, verdict="ACCEPT", pending_expands=[])
        with pytest.raises(RuntimeError, match="not EXPAND"):
            sampling.validate_expansion_manifest(
                copy.deepcopy(em), sm, man, source, desc, sm_sha,
                expected_test_only=True, report=acc,
                report_sha=c.sha256_bytes(c.serialize_json(acc)))
        # expansion declares a pair the producing report did NOT authorize ->
        # rejected (unauthorized pair). Keep the SAME report (and report_sha)
        # so the rejected check is the pair mismatch, not the report binding.
        em_other_pair = sampling.build_expansion_manifest(
            sm, [{"book": "ditiansui", "type": "rule"}], 1, man, source,
            desc, sm_sha, report_sha)
        with pytest.raises(RuntimeError, match="pending_expands"):
            sampling.validate_expansion_manifest(
                em_other_pair, sm, man, source, desc, sm_sha,
                expected_test_only=True, report=report, report_sha=report_sha)
        # expansion bound to a different sample manifest -> rejected (tamper
        # the expansion's OWN binding; the report still binds the real one).
        bad_sm = copy.deepcopy(em)
        bad_sm["sample_manifest_sha256"] = "0" * 64
        with pytest.raises(RuntimeError, match="does not bind the current sample"):
            sampling.validate_expansion_manifest(
                bad_sm, sm, man, source, desc, sm_sha,
                expected_test_only=True, report=report, report_sha=report_sha)
    finally:
        fixtures.rmtree_force(base)
