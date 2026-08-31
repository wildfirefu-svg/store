"""Deterministic sampling for the classic-texts manual acceptance (design
v4.6.1, Approved LOCAL_ONLY; section 4 initial sampling, section 6.3 expansion).

Subcommands:
    sample   initial sample manifest: per-stratum random samples + mandatory
             boundary items (all rules/MCQs of the boundary chapters)
    expand   (added later) expansion-round manifest for (book, type) pairs a
             decision report marked EXPAND

Deterministic: sha256 over length-prefixed fields with the frozen SEED;
identical inputs produce byte-identical manifests (LF JSON). k is always
derived from the frozen formula (never a hand-listed table). Production mode
runs the section 12.1 frozen-input lock; fake mode marks test_only=true.
LOCAL_ONLY tooling: no model API, no Phase 8, no formal gate, no remote.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import classic_acceptance_common as c

SAMPLING_ALGO_VERSION = "1.0"
GENERATOR_PATH = "scripts/classic_acceptance_sampling.py"
SAMPLE_FLAGS = {"chapter-manifest", "out", "candidate-commit", "data-root"}
EXPAND_FLAGS = {"sample-manifest", "decision-report", "chapter-manifest", "out",
                "candidate-commit", "data-root",
                "primary", "second", "arbitration"}


def stratum_of(book, chapter_index):
    if book != "sanmingtonghui":
        return 1
    for index, lo, hi in c.SANMING_STRATA:
        if lo <= chapter_index <= hi:
            return index
    raise RuntimeError(f"chapter {chapter_index!r} outside sanmingtonghui strata")


def load_chapter_manifest(path):
    data = c.lf_bytes(Path(path).read_bytes())
    man = json.loads(data.decode("utf-8"))
    chapters = man.get("chapters")
    c.require(isinstance(chapters, list) and chapters,
              "chapter manifest: chapters[] missing/empty")
    seen_ci, seen_rule, seen_mcq = set(), set(), set()
    for ch in chapters:
        ci = ch.get("chapter_index")
        c.require(isinstance(ci, int), f"chapter_index not int: {ci!r}")
        c.require(ci not in seen_ci, f"duplicate chapter_index {ci}")
        seen_ci.add(ci)
        c.require(ch.get("raw_source_path"), f"chapter {ci}: raw_source_path missing")
        for key in ("rule_ids", "mcq_ids"):
            c.require(isinstance(ch.get(key), list), f"chapter {ci}: {key} not a list")
        for rid in ch["rule_ids"]:
            c.require(rid not in seen_rule, f"rule {rid} mapped to multiple chapters")
            seen_rule.add(rid)
        for mid in ch["mcq_ids"]:
            c.require(mid not in seen_mcq, f"mcq {mid} mapped to multiple chapters")
            seen_mcq.add(mid)
    return man, c.sha256_bytes(data)


def load_universe(chapter_manifest, source):
    universe = {}
    file_shas = {}
    sm_rules, sm_mcqs = {}, {}
    for ch in chapter_manifest["chapters"]:
        for rid in ch["rule_ids"]:
            sm_rules[rid] = ch["chapter_index"]
        for mid in ch["mcq_ids"]:
            sm_mcqs[mid] = ch["chapter_index"]
    universe[("sanmingtonghui", "rule")] = sm_rules
    universe[("sanmingtonghui", "mcq")] = sm_mcqs
    for book in c.BOOKS:
        rules_rel = f"{c.BOOK_ROOT}/{book}/all_rules.json"
        mcq_rel = f"{c.BOOK_ROOT}/{book}/all_mcq.jsonl"
        rules_bytes = source.read_bytes(rules_rel)
        file_shas[rules_rel] = c.sha256_bytes(c.lf_bytes(rules_bytes))
        file_shas[mcq_rel] = c.sha256_bytes(c.lf_bytes(source.read_bytes(mcq_rel)))
        rule_ids = [r["id"] for r in json.loads(rules_bytes.decode("utf-8"))]
        mcq_ids = [m["id"] for m in c.load_jsonl(source, mcq_rel)]
        c.require(len(rule_ids) == len(set(rule_ids)), f"{book}: duplicate rule ids")
        c.require(len(mcq_ids) == len(set(mcq_ids)), f"{book}: duplicate mcq ids")
        if book == "sanmingtonghui":
            c.require(set(rule_ids) == set(sm_rules),
                      "sanmingtonghui: all_rules.json ids != chapter manifest rule_ids")
            c.require(set(mcq_ids) == set(sm_mcqs),
                      "sanmingtonghui: all_mcq.jsonl ids != chapter manifest mcq_ids")
        else:
            universe[(book, "rule")] = {iid: None for iid in rule_ids}
            universe[(book, "mcq")] = {iid: None for iid in mcq_ids}
    return universe, file_shas


def boundary_items(chapter_manifest):
    out = {"rule": [], "mcq": []}
    for ch in chapter_manifest["chapters"]:
        if ch["chapter_index"] in c.BOUNDARY_CHAPTERS:
            out["rule"].extend(ch["rule_ids"])
            out["mcq"].extend(ch["mcq_ids"])
    return {"rule": sorted(out["rule"]), "mcq": sorted(out["mcq"])}


def compute_k_table(book, item_type, population):
    pops = defaultdict(int)
    for iid, chapter in population.items():
        pops[stratum_of(book, chapter)] += 1
    pct = c.K_RULE_PCT if item_type == "rule" else c.K_MCQ_PCT
    return {s: c.compute_k(n, pct) for s, n in sorted(pops.items())}


def take_random_sample(book, item_type, population, exclude, k_table):
    eligible = defaultdict(list)
    for iid, chapter in population.items():
        if iid not in exclude:
            eligible[stratum_of(book, chapter)].append(iid)
    samples = {}
    for stratum in sorted(eligible):
        ranked = sorted(eligible[stratum],
                        key=lambda iid: (c.sample_score(book, item_type, stratum, iid), iid))
        k = k_table[stratum]
        c.require(len(ranked) >= k,
                  f"{book}/{item_type} stratum {stratum}: only {len(ranked)} non-boundary for k={k}")
        samples[stratum] = sorted(ranked[:k])
    return samples


def generator_identity():
    data = c.lf_bytes(Path(__file__).read_bytes())
    result = subprocess.run(
        ["git", "-C", str(Path(__file__).resolve().parents[1]), "hash-object", "--stdin"],
        input=data, capture_output=True)
    c.require(result.returncode == 0, "git hash-object failed")
    return {"path": GENERATOR_PATH, "sha256_lf": c.sha256_bytes(data),
            "blob_oid": result.stdout.decode("utf-8").strip(),
            "algorithm_version": SAMPLING_ALGO_VERSION}


def build_sample_manifest(chapter_manifest, source, source_desc, chman_sha):
    universe, file_shas = load_universe(chapter_manifest, source)
    boundary = boundary_items(chapter_manifest)
    samples, k_table, strata_info = {}, {}, {}
    for book in c.BOOKS:
        samples[book] = {}
        k_table[book] = {}
        populations = {}
        for item_type in ("rule", "mcq"):
            population = universe[(book, item_type)]
            pops = defaultdict(int)
            for iid, chapter in population.items():
                pops[stratum_of(book, chapter)] += 1
            populations[item_type] = pops
            kt = compute_k_table(book, item_type, population)
            k_table[book][item_type] = {str(s): k for s, k in kt.items()}
            exclude = set(boundary["rule"] if item_type == "rule" else boundary["mcq"])
            picked = take_random_sample(book, item_type, population, exclude, kt)
            samples[book][item_type] = {str(s): ids for s, ids in picked.items()}
        strata_info[book] = [
            {"index": s,
             "population": {"rule": populations["rule"].get(s, 0),
                            "mcq": populations["mcq"].get(s, 0)}}
            for s in sorted(set(populations["rule"]) | set(populations["mcq"]))]
    totals = {}
    for item_type in ("rule", "mcq"):
        random_total = sum(len(ids) for book in c.BOOKS
                           for ids in samples[book][item_type].values())
        totals[item_type] = {"random": random_total, "boundary": len(boundary[item_type]),
                             "total": random_total + len(boundary[item_type])}
    boundary_by_book = {book: {"rule": [], "mcq": []} for book in c.BOOKS}
    boundary_by_book["sanmingtonghui"] = boundary
    return {
        "schema_version": "1.0",
        "kind": "sample_manifest_v1",
        "algorithm_version": SAMPLING_ALGO_VERSION,
        "seed": {"hex": c.SEED_BYTES.hex(), "decimal": c.SEED_DECIMAL},
        "data_source": source_desc,
        "test_only": bool(source_desc.get("test_only")),
        "chapter_manifest_sha256": chman_sha,
        "data_file_sha256_lf": file_shas,
        "generator": generator_identity(),
        "normalization": {
            "module": "scripts/classic_acceptance_common.py",
            "function": "normalize_for_source_match",
            "sha256_lf": c.sha256_bytes(c.lf_bytes(
                (Path(__file__).parent / "classic_acceptance_common.py").read_bytes())),
        },
        "strata": strata_info,
        "k_table": k_table,
        "boundary_chapters": c.BOUNDARY_CHAPTERS,
        "samples": samples,
        "boundary_samples": boundary_by_book,
        "totals": totals,
    }


# ---- F19: reconstruct-and-compare manifest validators (fail-closed) ----
#
# Shape-only checks are NOT sufficient: a hand-crafted or cross-mode-retagged
# manifest can have the right keys with bogus k/ids/totals/SHAs. The validators
# live in this module because they must rebuild the expected manifest from the
# SAME code path that generates it, then compare canonical serialized bytes.
# Every field is thus covered: k recomputation, sample ids/counts, the full
# boundary set, dedup, totals, data-file SHAs, and the current-generator
# identity. Production passes the frozen chapter-manifest SHA; fake mode passes
# the LF SHA of the fake chapter manifest actually used.

def validate_sample_manifest(sample, chapter_manifest, source, source_desc,
                             chman_sha, expected_test_only):
    """F19: fully validate a sample_manifest_v1 by reconstruct-and-compare.

    The caller passes the SAME (chapter_manifest, source, source_desc,
    chman_sha) it resolved for the run: production resolves them through the
    F18 frozen lock (so chman_sha IS the frozen chapter-manifest LF SHA); fake
    mode resolves the --data-root DirSource and the fake chapter manifest
    (so chman_sha is the ACTUAL fake chapter-manifest LF SHA, not the frozen
    one). expected_test_only is True for fake and False for production."""
    c.require(isinstance(sample, dict), "sample manifest: not an object")
    test_only = sample.get("test_only")
    c.require(isinstance(test_only, bool), "sample manifest: test_only missing/not bool")
    c.require(test_only is expected_test_only,
              f"sample manifest test_only={test_only} not allowed in "
              f"{'fake' if expected_test_only else 'production'} mode (cross-mode rejection)")
    c.require(sample.get("kind") == "sample_manifest_v1", "sample manifest: wrong kind")
    if not expected_test_only:
        c.require(chman_sha == c.FROZEN_CHAPTER_MANIFEST_SHA,
                  "sample manifest: chapter manifest is not the frozen chapter manifest")
    c.require(sample.get("chapter_manifest_sha256") == chman_sha,
              "sample manifest: chapter_manifest_sha256 does not match the supplied chapter manifest")
    expected = build_sample_manifest(chapter_manifest, source, source_desc, chman_sha)
    c.require(c.serialize_json(sample) == c.serialize_json(expected),
              "sample manifest: does not match the manifest reconstructed from "
              "the current chapter manifest/source (k_table, sample ids, "
              "boundary set, totals, data-file SHAs, or generator identity differ)")


def cmd_sample(argv):
    flags, _ = c.parse_flags(argv, allowed=SAMPLE_FLAGS)
    chman_path = c.flag1(flags, "chapter-manifest")
    out_dir = Path(c.flag1(flags, "out"))
    # F18: build_source runs verify_frozen_inputs (incl. CLI chapter-manifest
    # SHA check) BEFORE any data read. expected_test_only is derived from mode.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = load_chapter_manifest(chman_path)
    manifest = build_sample_manifest(chapter_manifest, source, source_desc, chman_sha)
    # F19: self-validate the produced manifest against the resolved mode by
    # reconstructing from the SAME chapter manifest/source and comparing bytes.
    # In fake mode chman_sha is the fake chapter manifest's actual LF SHA.
    validate_sample_manifest(manifest, chapter_manifest, source, source_desc,
                             chman_sha, expected_test_only=is_fake)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = c.serialize_json(manifest)
    path = out_dir / "sample_manifest_v1.json"
    path.write_bytes(payload)
    print("sample manifest:", path)
    print("sha256:", c.sha256_bytes(payload))
    print("test_only:", manifest["test_only"], "totals:", manifest["totals"])


def build_expansion_manifest(sample_manifest, pending, round_no, chapter_manifest,
                             source, source_desc, sm_sha, report_sha):
    """Deterministic expansion for the given (book, type) pairs: per stratum
    added_s = min(k_s, remaining_s), ranked by expand_score, disjoint from the
    initial random sample and the boundary set."""
    universe, _ = load_universe(chapter_manifest, source)
    boundary = boundary_items(chapter_manifest)
    expansions = {}
    totals = {}
    for pair in pending:
        book, item_type = pair["book"], pair["type"]
        population = universe[(book, item_type)]
        k_table = compute_k_table(book, item_type, population)
        bset = set(boundary["rule"] if item_type == "rule" else boundary["mcq"])
        initial = set()
        for ids in sample_manifest["samples"][book][item_type].values():
            initial.update(ids)
        chapter_of = {}
        if book == "sanmingtonghui":
            for ch in chapter_manifest["chapters"]:
                for iid in ch["rule_ids"] + ch["mcq_ids"]:
                    chapter_of[iid] = ch["chapter_index"]
        remaining = defaultdict(list)
        for iid, chapter in population.items():
            if iid not in bset and iid not in initial:
                remaining[stratum_of(book, chapter)].append(iid)
        pops = defaultdict(int)
        for iid, chapter in population.items():
            pops[stratum_of(book, chapter)] += 1
        per_stratum = {}
        added_total = 0
        for stratum in sorted(set(pops) | set(remaining)):
            ranked = sorted(remaining.get(stratum, []),
                            key=lambda iid: (c.expand_score(book, item_type, stratum, iid), iid))
            k = k_table.get(stratum, 0)
            added = min(k, len(ranked))
            # P0: boundary ids are sanmingtonghui-only (boundary chapters are
            # sanmingtonghui chapters). For a non-sanmingtonghui book chapter_of
            # is empty and stratum_of(book, None) would short-circuit to 1,
            # wrongly counting every boundary id as stratum 1. Guard by
            # membership so non-sanmingtonghui books report boundary = 0.
            b_in_stratum = sum(1 for iid in bset
                               if iid in chapter_of
                               and stratum_of(book, chapter_of[iid]) == stratum)
            per_stratum[str(stratum)] = {
                "population": pops.get(stratum, 0),
                "initial_random": len(sample_manifest["samples"][book][item_type]
                                      .get(str(stratum), [])),
                "boundary": b_in_stratum,
                "k": k,
                "added": added,
                "new_ids": sorted(ranked[:added]),
            }
            added_total += added
        selected = [iid for info in per_stratum.values() for iid in info["new_ids"]]
        c.require(not (set(selected) & (initial | bset)),
                  f"expansion overlap with initial sample/boundary for {book}/{item_type}")
        expansions.setdefault(book, {})[item_type] = per_stratum
        totals.setdefault(book, {})[item_type] = added_total
    return {
        "schema_version": "1.0",
        "kind": "expansion_manifest_v1",
        "algorithm_version": SAMPLING_ALGO_VERSION,
        "test_only": bool(source_desc.get("test_only")),
        "data_source": source_desc,
        "round": round_no,
        "sample_manifest_sha256": sm_sha,
        "decision_report_sha256": report_sha,
        "expanded_pairs": pending,
        "generator": generator_identity(),
        "expansions": expansions,
        "totals": totals,
    }


def validate_expansion_manifest(expansion, sample_manifest, chapter_manifest,
                                source, source_desc, sm_sha, expected_test_only,
                                report, report_sha):
    """F19/P0: fully validate an expansion_manifest_v1 and PROVE it was
    authorized by a producing decision report.

    The producing report is MANDATORY: an expansion without a verified
    EXPAND verdict from the state machine is rejected even if its internal
    fields are self-consistent (this blocks `build_expansion_manifest()`
    crafted for an arbitrary unauthorized pair). Checks:
      - report is a decision_report_v1 for the same mode, binds THIS sample
        manifest by raw SHA, and has verdict == "EXPAND";
      - expansion binds the report by raw SHA (report_sha);
      - expansion.expanded_pairs == report.pending_expands exactly, and
        round == 1 + len(report.expansion_manifests_sha256);
      - report's primary/second/arbitration and any prior expansion SHAs
        bind the same artifacts the caller passed (provenance chain);
      - the expansion body itself is reconstructed via
        build_expansion_manifest and compared byte-for-byte.
    report_sha is the raw on-disk SHA of the report file the caller holds.
    """
    c.require(isinstance(report, dict),
              "expansion manifest: producing decision report is required (no report -> no authorization)")
    c.require(report.get("kind") == "decision_report_v1",
              "expansion manifest: producing decision report has wrong kind")
    c.require(isinstance(report.get("test_only"), bool),
              "expansion manifest: producing decision report test_only missing")
    c.require(report.get("test_only") is expected_test_only,
              "expansion manifest: producing decision report cross-mode rejected")
    c.require(report.get("sample_manifest_sha256") == sm_sha,
              "expansion manifest: producing decision report does not bind this sample manifest")
    c.require(report.get("verdict") == "EXPAND",
              f"expansion manifest: producing decision report verdict is "
              f"{report.get('verdict')!r}, not EXPAND; expansion only follows "
              f"an EXPAND verdict")
    c.require(report.get("decision_report_sha256") is None,
              "expansion manifest: producing report must not itself reference a decision report")

    c.require(isinstance(expansion, dict), "expansion manifest: not an object")
    test_only = expansion.get("test_only")
    c.require(isinstance(test_only, bool), "expansion manifest: test_only missing/not bool")
    c.require(test_only is expected_test_only,
              "expansion manifest: cross-mode test_only rejected")
    c.require(expansion.get("kind") == "expansion_manifest_v1",
              "expansion manifest: wrong kind")
    c.require(expansion.get("algorithm_version") == SAMPLING_ALGO_VERSION,
              "expansion manifest: algorithm_version mismatch")
    c.require(expansion.get("sample_manifest_sha256") == sm_sha,
              "expansion manifest: does not bind the current sample manifest")
    c.require(expansion.get("decision_report_sha256") == report_sha,
              "expansion manifest: does not bind the producing decision report (raw SHA)")
    pairs = expansion.get("expanded_pairs") or []
    c.require(isinstance(pairs, list) and pairs
              and all(isinstance(p, dict) and {"book", "type"} <= set(p)
                      for p in pairs),
              "expansion manifest: expanded_pairs invalid")
    c.require(pairs == (report.get("pending_expands") or []),
              "expansion manifest: expanded_pairs != decision report pending_expands "
              "(pair not authorized by the state machine)")
    round_no = expansion.get("round")
    c.require(isinstance(round_no, int) and round_no >= 1,
              "expansion manifest: round missing/invalid")
    prior = report.get("expansion_manifests_sha256") or []
    c.require(round_no == 1 + len(prior),
              "expansion manifest: round does not follow the producing decision report")
    expected = build_expansion_manifest(sample_manifest, pairs, round_no,
                                        chapter_manifest, source, source_desc,
                                        sm_sha, report_sha)
    c.require(c.serialize_json(expansion) == c.serialize_json(expected),
              "expansion manifest: does not match the manifest reconstructed "
              "from the current sample manifest/chapter manifest/source "
              "(new ids, added, k, population, totals, data_source, or "
              "generator identity differ)")


def cmd_expand(argv):
    flags, _ = c.parse_flags(argv, allowed=EXPAND_FLAGS)
    sm_path = c.flag1(flags, "sample-manifest")
    report_path = c.flag1(flags, "decision-report")
    chman_path = c.flag1(flags, "chapter-manifest")
    primary_path = c.flag1(flags, "primary")
    out_dir = Path(c.flag1(flags, "out"))
    second_path = c.flag_opt(flags, "second")
    arbitration_path = c.flag_opt(flags, "arbitration")
    # F18/F19: verify frozen inputs FIRST, then validate input manifests.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    validate_sample_manifest(sample_manifest, chapter_manifest, source,
                             source_desc, chman_sha, expected_test_only=is_fake)
    # P0: the producing report is verified via the SAME shared
    # verify_producing_report the consumers use (F22 gate + RAW on-disk byte
    # equality against the recomputed verdict), so cmd_expand and cmd_decide /
    # packet / next-round decide are byte-for-byte the same code path.
    import classic_acceptance_review as review
    # P0-3: reuse the (report, report_sha) pinned to ONE raw read; do NOT
    # re-read the report path for its SHA.
    report, report_sha = review.verify_producing_report(
        report_path, sample_manifest, sm_sha,
        chapter_manifest, source, source_desc, is_fake,
        primary_path, second_path, arbitration_path)
    pending = report["pending_expands"]
    manifest = build_expansion_manifest(sample_manifest, pending, 1,
                                        chapter_manifest, source, source_desc,
                                        sm_sha, report_sha)
    # F19: self-validate the produced manifest against the (recomputed and
    # verified) producing decision report.
    validate_expansion_manifest(manifest, sample_manifest, chapter_manifest,
                                source, source_desc, sm_sha,
                                expected_test_only=is_fake,
                                report=report, report_sha=report_sha)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = c.serialize_json(manifest)
    path = out_dir / "expansion_manifest_v1.json"
    path.write_bytes(payload)
    print("expansion manifest:", path)
    print("sha256:", c.sha256_bytes(payload), "totals:", manifest["totals"],
          "test_only:", manifest["test_only"])


def main(argv):
    c.require(argv, "usage: classic_acceptance_sampling.py <sample|expand> [flags]")
    cmd = argv[0]
    try:
        if cmd == "sample":
            cmd_sample(argv[1:])
        elif cmd == "expand":
            cmd_expand(argv[1:])
        else:
            raise RuntimeError(f"unknown subcommand: {cmd!r} (expected sample|expand)")
    except RuntimeError as e:
        print(f"{cmd} FAILED: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))