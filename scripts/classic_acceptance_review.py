"""Review tooling for the classic-texts manual acceptance (design v4.6.1,
Approved LOCAL_ONLY; section 5 findings, section 6 decision state machine,
section 8 receipt chain, section 12 hard contracts).

Subcommands:
    packet               generate the human-review packet
    validate-primary     validate primary_review_package_v1.json
    validate-second      validate second_review_receipt_v1.json
    validate-arbitration validate arbitration_receipt_v1.json
    decide               adjudicate + run the frozen state machine
    finalize             assemble final_acceptance_package_v1.json

Integer cross-multiplication only (no floats). LF-deterministic JSON to
--out. Production mode runs the section 12.1 lock; fake mode outputs
test_only=true and finalize refuses to close. LOCAL_ONLY: no model API, no
Phase 8, no formal gate, no remote publication, no audit tag.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import classic_acceptance_common as c
import classic_acceptance_sampling as sampling

REVIEW_ALGO_VERSION = "1.0"
REVIEW_GENERATOR_PATH = "scripts/classic_acceptance_review.py"
PACKET_FLAGS = {"sample-manifest", "chapter-manifest", "out",
                "candidate-commit", "data-root",
                "expansion-manifest", "decision-report",
                "producing-primary", "producing-second", "producing-arbitration"}


def load_json_file(path):
    # F20: parse raw on-disk bytes (no LF normalization) for review artifacts
    return json.loads(Path(path).read_bytes().decode("utf-8"))


def review_generator_identity():
    data = c.lf_bytes(Path(__file__).read_bytes())
    result = subprocess.run(
        ["git", "-C", str(Path(__file__).resolve().parents[1]), "hash-object", "--stdin"],
        input=data, capture_output=True)
    c.require(result.returncode == 0, "git hash-object failed")
    return {"path": REVIEW_GENERATOR_PATH, "sha256_lf": c.sha256_bytes(data),
            "blob_oid": result.stdout.decode("utf-8").strip(),
            "algorithm_version": REVIEW_ALGO_VERSION}


def integrity_check(chapter_manifest, source):
    zero_chs = [ch for ch in chapter_manifest["chapters"]
                if ch.get("zero_rule") or ch.get("zero_mcq")]
    return {
        "zero_output_chapters": [
            {"chapter_index": ch["chapter_index"],
             "raw_source_path": ch["raw_source_path"],
             "raw_exists": source.exists(ch["raw_source_path"]),
             "zero_rule": bool(ch.get("zero_rule")),
             "zero_mcq": bool(ch.get("zero_mcq"))}
            for ch in zero_chs],
        "source_missing_chapters": [ch["chapter_index"] for ch in zero_chs
                                    if not source.exists(ch["raw_source_path"])],
        "drift_files": [{"path": p, "exists": source.exists(p)} for p in c.DRIFT_FILES],
        "missing_drift_files": [p for p in c.DRIFT_FILES if not source.exists(p)],
    }


def build_packet(sample_manifest, expansion_manifests, chapter_manifest, source,
                 sample_manifest_sha, expansion_shas, source_desc):
    rules_by_book, mcqs_by_book = {}, {}
    for book in c.BOOKS:
        rules_by_book[book] = {r["id"]: r for r in
                               c.load_json(source, f"{c.BOOK_ROOT}/{book}/all_rules.json")}
        mcqs_by_book[book] = {m["id"]: m for m in
                              c.load_jsonl(source, f"{c.BOOK_ROOT}/{book}/all_mcq.jsonl")}
    chapter_of = {}
    for ch in chapter_manifest["chapters"]:
        for iid in ch["rule_ids"] + ch["mcq_ids"]:
            chapter_of[iid] = ch["chapter_index"]

    entries = []

    def add(book, item_type, iid, stratum, boundary, rnd):
        if item_type == "rule":
            content = rules_by_book[book].get(iid)
            c.require(content is not None, f"{book}: rule {iid} missing from all_rules.json")
        else:
            content = mcqs_by_book[book].get(iid)
            c.require(content is not None, f"{book}: mcq {iid} missing from all_mcq.jsonl")
        entry = {"book": book, "type": item_type, "id": iid, "stratum": stratum,
                 "boundary": boundary, "round": rnd, "content": content}
        if item_type == "mcq":
            srid = content.get("source_rule_id")
            srule = rules_by_book[book].get(srid)
            c.require(srule is not None,
                      f"{book}: mcq {iid} source_rule_id {srid!r} not found")
            entry["source_rule"] = srule
        if book == "sanmingtonghui":
            ci = chapter_of.get(iid)
            c.require(ci is not None, f"sanmingtonghui item {iid} not in chapter manifest")
            entry["source_chapter"] = ci
        entries.append(entry)

    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for s, ids in sample_manifest["samples"][book][item_type].items():
                for iid in ids:
                    add(book, item_type, iid, int(s), False, 1)
    for item_type in ("rule", "mcq"):
        for iid in sample_manifest["boundary_samples"]["sanmingtonghui"][item_type]:
            add("sanmingtonghui", item_type, iid,
                sampling.stratum_of("sanmingtonghui", chapter_of[iid]), True, 1)
    for em in expansion_manifests:
        for book, types in em["expansions"].items():
            for item_type, strata in types.items():
                for s, info in strata.items():
                    for iid in info["new_ids"]:
                        add(book, item_type, iid, int(s), False, em["round"])

    entries.sort(key=lambda e: (e["book"], e["type"], e["id"]))
    needed = {e["source_chapter"] for e in entries if e["book"] == "sanmingtonghui"}
    zero_ci = {ch["chapter_index"] for ch in chapter_manifest["chapters"]
               if ch.get("zero_rule") or ch.get("zero_mcq")}
    chapters = {}
    for ch in chapter_manifest["chapters"]:
        ci = ch["chapter_index"]
        if ci not in needed and ci not in zero_ci:
            continue
        exists_ = source.exists(ch["raw_source_path"])
        chapters[str(ci)] = {
            "title": ch.get("title"),
            "raw_source_path": ch["raw_source_path"],
            "raw_exists": exists_,
            "raw_text": (source.read_bytes(ch["raw_source_path"]).decode("utf-8")
                         if exists_ else None),
        }
    for e in entries:
        if e["book"] != "sanmingtonghui":
            continue
        raw = chapters[str(e["source_chapter"])]["raw_text"] or ""
        base_text = (e["source_rule"]["original_text"] if e["type"] == "mcq"
                     else e["content"].get("original_text", ""))
        e["original_text_in_raw"] = (c.normalize_for_source_match(base_text)
                                     in c.normalize_for_source_match(raw))
    return {
        "schema_version": "1.0",
        "kind": "review_packet_v1",
        "test_only": bool(source_desc.get("test_only")),
        "data_source": source_desc,
        "sample_manifest_sha256": sample_manifest_sha,
        "expansion_manifests_sha256": expansion_shas,
        "generator": review_generator_identity(),
        "chapters": chapters,
        "items": entries,
        "integrity": integrity_check(chapter_manifest, source),
    }


def required_item_keys(sample_manifest, expansion_manifests):
    refs = set()
    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for ids in sample_manifest["samples"][book][item_type].values():
                refs.update((book, item_type, iid) for iid in ids)
    for item_type in ("rule", "mcq"):
        refs.update(("sanmingtonghui", item_type, iid)
                    for iid in sample_manifest["boundary_samples"]["sanmingtonghui"][item_type])
    for em in expansion_manifests:
        for book, types in em["expansions"].items():
            for item_type, strata in types.items():
                for info in strata.values():
                    refs.update((book, item_type, iid) for iid in info["new_ids"])
    return refs


def validate_primary(primary, sample_manifest, expansions, sample_manifest_sha,
                     expansion_shas, chapter_manifest):
    c.require(primary.get("schema_version") == "1.0", "primary: schema_version != 1.0")
    c.require(primary.get("kind") == "primary_review_package", "primary: wrong kind")
    c.require(primary.get("sample_manifest_sha256") == sample_manifest_sha,
              "primary does not bind the sample manifest (SHA mismatch)")
    c.require((primary.get("expansion_manifests_sha256") or []) == expansion_shas,
              "primary expansion_manifests_sha256 mismatch")
    reviewer_list = primary.get("reviewer_list")
    c.require(isinstance(reviewer_list, list) and reviewer_list
              and all(isinstance(r, str) and r for r in reviewer_list),
              "primary reviewer_list missing/empty/invalid")
    reviewer_set = set(reviewer_list)
    # F20/source-chapter identity (design section 8.1 schema): for
    # sanmingtonghui items the primary must declare the SAME source_chapter
    # the chapter manifest assigns to that id. The chapter manifest is
    # mandatory (no None/empty bypass) because a swapped chapter breaks the
    # audit trail and evidence traceability for that review entry; it does
    # not by itself change the decision metrics (boundary/stratum come from
    # the frozen sample/chapter metadata via item_meta_map), but a forged
    # chapter ownership must not validate.
    c.require(isinstance(chapter_manifest, dict)
              and isinstance(chapter_manifest.get("chapters"), list)
              and chapter_manifest["chapters"],
              "validate_primary: a non-empty chapter manifest is required")
    chapter_of = {}
    for ch in chapter_manifest["chapters"]:
        for iid in ch["rule_ids"] + ch["mcq_ids"]:
            chapter_of[iid] = ch["chapter_index"]
    required = required_item_keys(sample_manifest, expansions)
    actual = set()
    for entry in primary.get("items", []):
        item = entry.get("item") or {}
        key = (item.get("book"), item.get("type"), item.get("id"))
        c.require(all(isinstance(x, str) and x for x in key),
                  f"primary item missing book/type/id: {item}")
        c.require(key not in actual, f"primary duplicate item: {key}")
        actual.add(key)
        if item.get("book") == "sanmingtonghui":
            expected_ch = chapter_of.get(item["id"])
            c.require(expected_ch is not None,
                      f"{key}: sanmingtonghui item not found in chapter manifest")
            c.require(item.get("source_chapter") == expected_ch,
                      f"{key}: primary source_chapter {item.get('source_chapter')!r} "
                      f"!= chapter manifest {expected_ch!r} (chapter tampering)")
        verdict = entry.get("verdict")
        c.require(verdict in c.VERDICTS, f"{key}: invalid verdict {verdict!r}")
        findings = entry.get("findings")
        c.require(isinstance(findings, list), f"{key}: findings not a list")
        n_crit = n_min = 0
        for f in findings:
            sev, cat = f.get("severity"), f.get("category")
            c.require(sev in ("critical", "minor"), f"{key}: invalid severity {sev!r}")
            c.require(isinstance(f.get("evidence_text"), str) and f["evidence_text"].strip(),
                      f"{key}: evidence_text missing/empty")
            f_reviewer = f.get("reviewer")
            c.require(f_reviewer in reviewer_set,
                      f"{key}: finding reviewer {f_reviewer!r} not in reviewer_list (F15)")
            c._check_iso8601(f.get("reviewed_at"), f"{key} finding reviewed_at")
            if sev == "critical":
                c.require(cat in c.CRITICAL_CATEGORIES,
                          f"{key}: invalid critical category {cat!r}")
                n_crit += 1
            else:
                c.require(cat in c.MINOR_CATEGORIES,
                          f"{key}: invalid minor category {cat!r}")
                n_min += 1
        expected_verdict = "FAIL" if n_crit else ("PASS_WITH_MINOR" if n_min else "PASS")
        c.require(verdict == expected_verdict,
                  f"{key}: verdict {verdict} inconsistent with findings "
                  f"({n_crit} critical, {n_min} minor)")
    c.require(actual == required,
              f"primary item coverage mismatch: missing={sorted(required - actual)[:5]} "
              f"extra={sorted(actual - required)[:5]}")
    c.require(isinstance(primary.get("zero_output_report"), list),
              "primary zero_output_report missing")
    c.require(isinstance(primary.get("overall_stats"), dict), "primary overall_stats missing")


VALIDATE_PRIMARY_FLAGS = {
    "primary", "sample-manifest", "chapter-manifest",
    "candidate-commit", "data-root",
    "expansion-manifest", "decision-report",
    "producing-primary", "producing-second", "producing-arbitration",
}


def cmd_validate_primary(argv):
    # F18/F19: frozen/fake source lock first, then the SAME producing-evidence
    # authorization chain decide/finalize use. validate-primary is not a
    # trusted "is this JSON self-consistent" linter; an expansion can only
    # extend coverage if its producing EXPAND report is recomputed from the R1
    # receipts and its body is rebuilt against that report. At most one
    # expansion is allowed (only one parallel expansion round exists).
    flags, _ = c.parse_flags(argv, allowed=VALIDATE_PRIMARY_FLAGS)
    primary_path = c.flag1(flags, "primary")
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    expansion_path = c.flag_opt(flags, "expansion-manifest")
    producing_report_path = c.flag_opt(flags, "decision-report")
    pp_path = c.flag_opt(flags, "producing-primary")
    ps_path = c.flag_opt(flags, "producing-second")
    pa_path = c.flag_opt(flags, "producing-arbitration")
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    check_producing_evidence_presence(
        bool(expansion_path), producing_report_path, pp_path, ps_path, pa_path,
        "validate-primary")
    expansions = []
    expansion_shas = []
    if expansion_path:
        # P0-2/TOCTOU: read each artifact's raw bytes ONCE; pin the SHA and
        # parsed object from that same read. verify_producing_report returns
        # the verified report object (it itself compares on-disk bytes against
        # the recomputed verdict internally), and we reuse it rather than re-
        # reading the report path after validation.
        report, report_sha = verify_producing_report(
            producing_report_path, sample_manifest, sm_sha,
            chapter_manifest, source, source_desc, is_fake,
            pp_path, ps_path, pa_path)
        em_bytes = Path(expansion_path).read_bytes()
        em_sha = c.sha256_bytes(em_bytes)
        em = json.loads(em_bytes.decode("utf-8"))
        sampling.validate_expansion_manifest(
            em, sample_manifest, chapter_manifest, source, source_desc,
            sm_sha, expected_test_only=is_fake,
            report=report, report_sha=report_sha)
        expansions = [em]
        expansion_shas = [em_sha]
    primary = load_json_file(primary_path)
    validate_primary(primary, sample_manifest, expansions,
                     sm_sha, expansion_shas, chapter_manifest)
    print("primary review package OK:", primary_path)




def critical_refs(primary):
    out = set()
    for entry in primary["items"]:
        item = entry["item"]
        for idx, f in enumerate(entry.get("findings", [])):
            if f.get("severity") == "critical":
                out.add((item["book"], item["type"], item["id"], idx))
    return out


def _primary_reviewer_of(primary, book, item_type, iid, finding_index):
    """F21: return the reviewer of the SPECIFIC finding at finding_index for
    the primary item (book, type, id). One item may carry multiple findings
    with different reviewers; we must NOT require them all to share one."""
    for entry in primary["items"]:
        item = entry["item"]
        if (item["book"], item["type"], item["id"]) == (book, item_type, iid):
            findings = entry.get("findings", [])
            c.require(0 <= finding_index < len(findings),
                      f"primary item {(book, item_type, iid)} has no finding index "
                      f"{finding_index} (has {len(findings)})")
            reviewer = findings[finding_index].get("reviewer")
            c.require(isinstance(reviewer, str) and reviewer,
                      f"primary finding {finding_index} reviewer missing")
            return reviewer
    raise RuntimeError(f"primary item not found: {(book, item_type, iid)}")


def validate_second(second, primary, primary_sha):
    c.require(second.get("schema_version") == "1.0",
              "second review receipt: schema_version != 1.0")
    c.require(second.get("kind") == "second_review_receipt_v1",
              "second review receipt: wrong kind")
    c.require(second.get("primary_sha256") == primary_sha,
              "second review receipt does not bind the primary package (SHA mismatch)")
    reviewer = second.get("reviewer")
    c.require(isinstance(reviewer, str) and reviewer,
              "second review receipt: top-level reviewer missing")
    primary_reviewers = set()
    for entry in primary["items"]:
        for f in entry.get("findings", []):
            primary_reviewers.add(f.get("reviewer"))
    c.require(reviewer not in primary_reviewers,
              f"second reviewer {reviewer!r} must differ from every first reviewer (F15)")
    c._check_iso8601(second.get("reviewed_at"), "second receipt reviewed_at")
    required = critical_refs(primary)
    seen = set()
    for e in second.get("entries", []):
        ref = (e.get("book"), e.get("type"), e.get("id"), e.get("finding_index"))
        c.require(ref not in seen, f"second review duplicate entry: {ref}")
        seen.add(ref)
        c.require(isinstance(e.get("agree"), bool),
                  f"second review entry missing agree bool: {ref}")
        c.require(isinstance(e.get("evidence_text"), str) and e["evidence_text"].strip(),
                  f"second review entry missing evidence_text: {ref}")
        c.require(e.get("reviewer") == reviewer,
                  f"second review entry reviewer != top-level reviewer: {ref}")
        c._check_iso8601(e.get("reviewed_at"), f"second review entry {ref} reviewed_at")
    c.require(seen == required,
              f"second review must cover exactly all critical findings: "
              f"missing={sorted(required - seen)[:5]} extra={sorted(seen - required)[:5]}")


def disagreement_refs(second):
    return {(e["book"], e["type"], e["id"], e["finding_index"])
            for e in second.get("entries", []) if not e["agree"]}


def validate_arbitration(arbitration, primary, second, primary_sha, second_sha):
    c.require(arbitration.get("schema_version") == "1.0",
              "arbitration receipt: schema_version != 1.0")
    c.require(arbitration.get("kind") == "arbitration_receipt_v1",
              "arbitration receipt: wrong kind")
    c.require(arbitration.get("primary_sha256") == primary_sha,
              "arbitration receipt does not bind the primary package (SHA mismatch)")
    c.require(arbitration.get("second_review_sha256") == second_sha,
              "arbitration receipt does not bind the second review receipt (SHA mismatch)")
    # F21: top-level identity + ISO-8601 timestamp
    c._check_iso8601(arbitration.get("reviewed_at"), "arbitration receipt reviewed_at")
    reviewer_second = arbitration.get("reviewer_second")
    arbitrator = arbitration.get("arbitrator")
    c.require(reviewer_second == second.get("reviewer"),
              "arbitration reviewer_second != second receipt reviewer")
    c.require(isinstance(arbitrator, str) and arbitrator,
              "arbitration: arbitrator missing")
    # P0-1: global independence (design section 12.3) is against the ENTIRE
    # primary.reviewer_list, not just reviewers who produced a finding.
    primary_reviewer_list = set(primary.get("reviewer_list") or [])
    c.require(arbitrator not in primary_reviewer_list,
              f"arbitrator {arbitrator!r} must not be any primary reviewer (F15 global)")
    c.require(arbitrator != reviewer_second,
              f"arbitrator {arbitrator!r} must differ from second reviewer (F15)")
    required = disagreement_refs(second)
    seen = set()
    for e in arbitration.get("entries", []):
        ref = (e.get("book"), e.get("type"), e.get("id"), e.get("finding_index"))
        c.require(ref not in seen, f"arbitration duplicate entry: {ref}")
        seen.add(ref)
        c.require(e.get("decision") in ("critical", "non_critical"),
                  f"arbitration invalid decision {e.get('decision')!r}: {ref}")
        c.require(isinstance(e.get("reasoning"), str) and e["reasoning"].strip(),
                  f"arbitration entry missing reasoning: {ref}")
        c.require(e.get("arbitrator") == arbitrator,
                  f"arbitration entry arbitrator != top-level: {ref}")
        c._check_iso8601(e.get("reviewed_at"), f"arbitration entry {ref} reviewed_at")
        # F21: reviewer_first binds the SPECIFIC finding at finding_index
        first = e.get("reviewer_first")
        actual_first = _primary_reviewer_of(primary, *ref)
        c.require(first == actual_first,
                  f"arbitration reviewer_first {first!r} != primary finding[{ref[3]}] "
                  f"reviewer {actual_first!r}: {ref}")
        c.require(first in primary_reviewer_list,
                  f"arbitration reviewer_first {first!r} not in primary reviewer_list")
        c.require(first not in (reviewer_second, arbitrator),
                  f"arbitration entry identities not pairwise distinct: {ref}")
    c.require(seen == required,
              f"arbitration must cover exactly all second-review disagreements: "
              f"missing={sorted(required - seen)[:5]} extra={sorted(seen - required)[:5]}")


VALIDATE_SECOND_FLAGS = {"second", "primary", "candidate-commit", "data-root",
                         "chapter-manifest"}
VALIDATE_ARBITRATION_FLAGS = {"arbitration", "primary", "second",
                              "candidate-commit", "data-root", "chapter-manifest"}


def cmd_validate_second(argv):
    # F18: run the frozen/fake source lock BEFORE reading any receipt/primary.
    flags, _ = c.parse_flags(argv, allowed=VALIDATE_SECOND_FLAGS)
    second_path = c.flag1(flags, "second")
    primary_path = c.flag1(flags, "primary")
    is_fake = "data-root" in flags
    c.build_source(flags, expected_test_only=(True if is_fake else False))
    second = load_json_file(second_path)
    primary, primary_sha = c.load_json_with_sha(primary_path)
    validate_second(second, primary, primary_sha)
    print("second review receipt OK:", second_path)


def cmd_validate_arbitration(argv):
    # F18: run the frozen/fake source lock BEFORE reading any receipt/primary.
    flags, _ = c.parse_flags(argv, allowed=VALIDATE_ARBITRATION_FLAGS)
    arbitration_path = c.flag1(flags, "arbitration")
    primary_path = c.flag1(flags, "primary")
    second_path = c.flag1(flags, "second")
    is_fake = "data-root" in flags
    c.build_source(flags, expected_test_only=(True if is_fake else False))
    arbitration = load_json_file(arbitration_path)
    primary, primary_sha = c.load_json_with_sha(primary_path)
    second, second_sha = c.load_json_with_sha(second_path)
    validate_arbitration(arbitration, primary, second, primary_sha, second_sha)
    print("arbitration receipt OK:", arbitration_path)




def canonicalize(primary, second, arbitration):
    """Design section 6.4 ADJUDICATION (v4.6.1, F3): every critical finding
    resolves to ADJUDICATED_CRITICAL (second agrees or arbitration upholds)
    or is DELETED when arbitration says non_critical. A DELETED finding
    contributes to neither the critical nor the minor-only numerator, but its
    item REMAINS in the reviewed denominator (compute_metrics counts every
    reviewed item). Minor primary findings pass through as PRIMARY_MINOR.
    Item verdict is recomputed from the remaining findings; an item with no
    remaining findings is absent from the verdict map (treated as PASS, still
    counted as reviewed)."""
    second_by_ref = {(e["book"], e["type"], e["id"], e["finding_index"]): e
                     for e in (second or {}).get("entries", [])}
    arb_by_ref = {(e["book"], e["type"], e["id"], e["finding_index"]): e
                  for e in (arbitration or {}).get("entries", [])}
    canonical = []
    for entry in primary["items"]:
        item = entry["item"]
        for idx, f in enumerate(entry.get("findings", [])):
            base = {"book": item["book"], "type": item["type"], "id": item["id"],
                    "finding_index": idx, "category": f.get("category")}
            if f.get("severity") != "critical":
                canonical.append({**base, "severity": "minor", "state": "PRIMARY_MINOR"})
                continue
            ref = (item["book"], item["type"], item["id"], idx)
            e = second_by_ref.get(ref)
            c.require(e is not None, f"critical finding {ref} lacks a second-review entry")
            if e["agree"]:
                canonical.append({**base, "severity": "critical",
                                  "state": "ADJUDICATED_CRITICAL"})
                continue
            a = arb_by_ref.get(ref)
            c.require(a is not None,
                      f"disputed critical finding {ref} lacks an arbitration entry")
            if a["decision"] == "critical":
                canonical.append({**base, "severity": "critical",
                                  "state": "ADJUDICATED_CRITICAL"})
            # decision == "non_critical": finding DELETED (F3), not appended.
    return canonical


def item_verdicts(canonical):
    crit, minor = defaultdict(int), defaultdict(int)
    for f in canonical:
        key = (f["book"], f["type"], f["id"])
        if f["severity"] == "critical":
            crit[key] += 1
        else:
            minor[key] += 1
    return {key: ("FAIL" if crit[key] else "PASS_WITH_MINOR")
            for key in set(crit) | set(minor)}


def item_meta_map(sample_manifest, expansions, chapter_manifest):
    meta = {}

    def put(key, stratum, boundary):
        c.require(key not in meta, f"duplicate reviewed item key: {key}")
        meta[key] = {"stratum": stratum, "boundary": boundary}

    for book in c.BOOKS:
        for item_type in ("rule", "mcq"):
            for s, ids in sample_manifest["samples"][book][item_type].items():
                for iid in ids:
                    put((book, item_type, iid), int(s), False)
    chapter_of = {}
    for ch in chapter_manifest["chapters"]:
        for iid in ch["rule_ids"] + ch["mcq_ids"]:
            chapter_of[iid] = ch["chapter_index"]
    for item_type in ("rule", "mcq"):
        for iid in sample_manifest["boundary_samples"]["sanmingtonghui"][item_type]:
            put(("sanmingtonghui", item_type, iid),
                sampling.stratum_of("sanmingtonghui", chapter_of[iid]), True)
    for em in expansions:
        for book, types in em["expansions"].items():
            for item_type, strata in types.items():
                for s, info in strata.items():
                    for iid in info["new_ids"]:
                        put((book, item_type, iid), int(s), False)
    return meta


def compute_metrics(verdicts, meta):
    metrics = defaultdict(lambda: {"reviewed": 0, "critical_items": 0, "minor_only_items": 0})
    stratum_rule = defaultdict(lambda: {"reviewed": 0, "critical_items": 0})
    boundary_crit = defaultdict(int)
    for key, m in meta.items():
        book, item_type, _iid = key
        verdict = verdicts.get(key, "PASS")   # absent => no FAIL/minor finding, but reviewed
        mm = metrics[(book, item_type)]
        mm["reviewed"] += 1                   # F3: denominator counts every reviewed item
        if verdict == "FAIL":
            mm["critical_items"] += 1
            if m["boundary"]:
                boundary_crit[(book, item_type)] += 1
            if item_type == "rule":
                stratum_rule[(book, m["stratum"])]["critical_items"] += 1
        elif verdict == "PASS_WITH_MINOR":
            mm["minor_only_items"] += 1
        if item_type == "rule":
            stratum_rule[(book, m["stratum"])]["reviewed"] += 1
    return metrics, stratum_rule, boundary_crit


def decide_state(metrics, stratum_rule, boundary_crit, integrity, expanded_pairs):
    if integrity["source_missing_chapters"] or integrity["missing_drift_files"]:
        return {"verdict": "REJECT", "fired_rules": ["INTEGRITY"], "pending_expands": []}
    for (_book, _item_type), n in sorted(boundary_crit.items()):
        if n > 0:
            return {"verdict": "REJECT", "fired_rules": ["BOUNDARY"], "pending_expands": []}
    for (_book, _stratum), m in sorted(stratum_rule.items()):
        if m["critical_items"] * 100 > c.STRATUM_CASCADE_PCT * m["reviewed"]:
            return {"verdict": "REJECT", "fired_rules": ["STRATUM_CASCADE"],
                    "pending_expands": []}
    for (_book, _item_type), m in sorted(metrics.items()):
        if m["critical_items"] * 100 > c.REJECT_PCT * m["reviewed"]:
            return {"verdict": "REJECT", "fired_rules": ["REJECT_GATE"], "pending_expands": []}
        if m["minor_only_items"] * 100 > c.MINOR_REJECT_PCT * m["reviewed"]:
            return {"verdict": "REJECT", "fired_rules": ["REJECT_GATE"], "pending_expands": []}
    pending = []
    for (book, item_type), m in sorted(metrics.items()):
        in_band = (m["critical_items"] * 100 > c.EXPAND_LOW_PCT * m["reviewed"]
                   and m["critical_items"] * 100 <= c.REJECT_PCT * m["reviewed"])
        if not in_band:
            continue
        if {"book": book, "type": item_type} in expanded_pairs:
            return {"verdict": "REJECT", "fired_rules": ["EXPAND_GATE"], "pending_expands": []}
        pending.append({"book": book, "type": item_type})
    if pending:
        return {"verdict": "EXPAND", "fired_rules": ["EXPAND_GATE"], "pending_expands": pending}
    return {"verdict": "ACCEPT", "fired_rules": [], "pending_expands": []}


def _serialize_book_type_metrics(metrics):
    out = {}
    for (book, item_type), m in sorted(metrics.items()):
        out.setdefault(book, {})[item_type] = {
            "reviewed": m["reviewed"], "critical_items": m["critical_items"],
            "critical_rate": f"{m['critical_items']}/{m['reviewed']}",
            "minor_only_items": m["minor_only_items"],
            "minor_rate": f"{m['minor_only_items']}/{m['reviewed']}"}
    return out


def _serialize_stratum_metrics(stratum_rule):
    out = {}
    for (book, stratum), m in sorted(stratum_rule.items()):
        out.setdefault(book, {})[str(stratum)] = {
            "reviewed": m["reviewed"], "critical_items": m["critical_items"],
            "critical_rate": f"{m['critical_items']}/{m['reviewed']}"}
    return out


DECIDE_FLAGS = {"primary", "sample-manifest", "chapter-manifest", "out",
                "candidate-commit", "data-root",
                "second", "arbitration",
                "expansion-manifest", "decision-report",
                "producing-primary", "producing-second", "producing-arbitration"}


def check_receipt_requirements(has_criticals, has_disagreement,
                               second_provided, arbitration_provided):
    """F22: pure state-machine gate on which receipts the CLI may pass.
    Raises if a receipt is provided when not required (or required when
    missing). Returns (need_second, need_arbitration)."""
    if not has_criticals:
        c.require(not second_provided,
                  "--second is not allowed: primary has no critical findings (F22)")
        c.require(not arbitration_provided,
                  "--arbitration is not allowed without critical findings (F22)")
        return False, False
    c.require(second_provided,
              "primary has critical findings: --second <receipt> is required")
    if not has_disagreement:
        c.require(not arbitration_provided,
                  "--arbitration is not allowed: second review has no "
                  "disagreements (F22)")
        return True, False
    c.require(arbitration_provided,
              "second review disagrees on criticals: --arbitration <receipt> is required")
    return True, True


def compute_decision(primary, second, arbitration, sample_manifest, expansions,
                     chapter_manifest, source, source_desc, expansion_shas,
                     primary_sha, second_sha, arbitration_sha, sm_sha):
    """Run the full adjudication + section-6.2 state machine from the raw
    receipts and frozen data, and return the decision report dict. This is the
    SAME code path for both `decide` (producer) and `expand` (which must
    recompute the verdict rather than trust a hand-crafted report). All SHAs
    are pinned by the caller (raw on-disk bytes, F20): this function NEVER
    re-opens any artifact path (no TOCTOU). The caller is responsible for
    validating the manifests and receipts before calling this."""
    canonical = canonicalize(primary, second, arbitration)
    verdicts = item_verdicts(canonical)
    integrity = integrity_check(chapter_manifest, source)
    meta = item_meta_map(sample_manifest, expansions, chapter_manifest)
    metrics, stratum_rule, boundary_crit = compute_metrics(verdicts, meta)
    expanded_pairs = []
    for em in expansions:
        for pair in em.get("expanded_pairs", []):
            if pair not in expanded_pairs:
                expanded_pairs.append(pair)
    state = decide_state(metrics, stratum_rule, boundary_crit, integrity, expanded_pairs)
    return {
        "schema_version": "1.0",
        "kind": "decision_report_v1",
        "test_only": bool(source_desc.get("test_only")),
        # P0-2: design section 12.2 requires the decision product to carry its
        # data-source identity (fake/production provenance).
        "data_source": source_desc,
        "primary_sha256": primary_sha,
        "second_review_sha256": second_sha,
        "arbitration_sha256": arbitration_sha,
        "sample_manifest_sha256": sm_sha,
        # P0: expansion SHAs are pre-pinned by the caller's single read; the
        # decision report never re-opens the expansion file (no TOCTOU).
        "expansion_manifests_sha256": expansion_shas,
        "expanded_pairs": expanded_pairs,
        "adjudication": {
            "canonical_findings": canonical,
            "second_review_entries": len(second["entries"]) if second else 0,
            "arbitration_entries": len(arbitration["entries"]) if arbitration else 0,
        },
        "metrics": _serialize_book_type_metrics(metrics),
        "stratum_rule_metrics": _serialize_stratum_metrics(stratum_rule),
        "boundary_critical_items": {f"{book}/{item_type}": n
                                    for (book, item_type), n in sorted(boundary_crit.items())},
        "integrity": integrity,
        "fired_rules": state["fired_rules"],
        "verdict": state["verdict"],
        "pending_expands": state["pending_expands"],
    }


def validate_decision_inputs(sample_manifest, expansions, chapter_manifest,
                             source, source_desc, sm_sha, expansion_shas,
                             expected_test_only,
                             primary_path, second_path, arbitration_path):
    """Shared single-round decision validation used by `decide` (producer),
    `expand` (which must recompute the producing verdict), and the expansion
    consumers. Reads primary/second/arbitration receipts ONCE each (object +
    raw-byte SHA pinned from the same bytes); sample_manifest and sm_sha are
    pinned by the caller (single read). Enforces the F22 receipt gate,
    validates second/arbitration exactly when the state machine requires, then
    runs compute_decision with the pinned SHAs. Returns
    (primary, second, arbitration, report)."""
    # P0: read each receipt ONCE; its object and raw-byte SHA come from the
    # same bytes and are passed downstream (never re-open a path).
    primary, primary_sha = c.load_json_with_sha(primary_path)
    # P0: expansion_shas are the caller's pinned SHAs from a single read;
    # never re-open the expansion files here.
    validate_primary(primary, sample_manifest, expansions, sm_sha,
                     expansion_shas, chapter_manifest)
    criticals = critical_refs(primary)
    second = second_sha = None
    arbitration = arbitration_sha = None
    has_disagreement = False
    if criticals:
        c.require(second_path,
                  "primary has critical findings: --second <receipt> is required")
        second, second_sha = c.load_json_with_sha(second_path)
        validate_second(second, primary, primary_sha)
        has_disagreement = bool(disagreement_refs(second))
    check_receipt_requirements(bool(criticals), has_disagreement,
                               bool(second_path), bool(arbitration_path))
    if has_disagreement:
        arbitration, arbitration_sha = c.load_json_with_sha(arbitration_path)
        validate_arbitration(arbitration, primary, second, primary_sha, second_sha)
    report = compute_decision(primary, second, arbitration, sample_manifest,
                              expansions, chapter_manifest, source, source_desc,
                              expansion_shas, primary_sha, second_sha,
                              arbitration_sha, sm_sha)
    return primary, second, arbitration, report


def verify_producing_report(report_path, sample_manifest, sm_sha,
                            chapter_manifest, source, source_desc,
                            expected_test_only, producing_primary_path,
                            producing_second_path, producing_arbitration_path):
    """P0: verify an expansion's producing decision report was actually
    produced by the state machine, not hand-crafted. Reads the report as RAW
    on-disk bytes (F20: CRLF, extra whitespace, reordered/duplicate JSON keys
    all change the bytes and are rejected), parses it for field checks, then
    RECOMPUTES the verdict from the producing primary/second/arbitration (via
    validate_decision_inputs with expansions=[]) and requires the on-disk
    bytes to be byte-identical to the recomputed canonical bytes and verdict
    == EXPAND. Returns (report, report_sha): the verified report dict plus the
    raw on-disk byte SHA pinned to the single read, which consumers reuse
    (never re-read the report path). The producing artifacts are the R1 round
    (no expansions)."""
    # P0-3: read the report path ONCE; the parsed object and its pinned SHA
    # both come from those exact bytes (no TOCTOU re-read window). Task 7
    # consumers reuse the returned (report, report_sha) and never re-read.
    actual_bytes = Path(report_path).read_bytes()
    report = json.loads(actual_bytes.decode("utf-8"))
    report_sha = c.sha256_bytes(actual_bytes)
    c.require(isinstance(report, dict), "producing decision report: not an object")
    c.require(report.get("kind") == "decision_report_v1",
              "producing decision report: wrong kind")
    c.require(isinstance(report.get("test_only"), bool),
              "producing decision report: test_only missing")
    c.require(report.get("test_only") is expected_test_only,
              "producing decision report: cross-mode test_only rejected")
    c.require(report.get("sample_manifest_sha256") == sm_sha,
              "producing decision report does not bind this sample manifest")
    c.require(report.get("expansion_manifests_sha256") == [],
              "producing decision report must reference no prior expansions (round 1)")
    c.require(report.get("decision_report_sha256") is None,
              "producing decision report must not reference another decision report")
    # Recompute the verdict from the R1 receipts via the SAME code path
    # `decide` uses (F22 receipt gate included); compare the RAW on-disk bytes
    # to the canonical recomputed bytes so CRLF/whitespace/key-order/duplicate
    # key tampering is rejected.
    _, _, _, recomputed = validate_decision_inputs(
        sample_manifest, [], chapter_manifest, source, source_desc, sm_sha, [],
        expected_test_only, producing_primary_path,
        producing_second_path, producing_arbitration_path)
    expected_bytes = c.serialize_json(recomputed)
    c.require(actual_bytes == expected_bytes,
              "producing decision report bytes do not match the verdict recomputed "
              "from its primary/second/arbitration (hand-crafted or re-serialized "
              "report rejected)")
    c.require(recomputed["verdict"] == "EXPAND" and recomputed["pending_expands"],
              f"producing decision verdict is {recomputed['verdict']!r}, "
              f"not EXPAND; expansion not authorized")
    return report, report_sha


def check_producing_evidence_presence(has_expansion, producing_report_path,
                                      pp_path, ps_path, pa_path, who):
    """Medium: the producing-evidence flags only make sense with an expansion.
    Require them all-or-nothing with --expansion-manifest so a caller cannot
    pass (and then silently ignore) a producing report/evidence bundle when no
    expansion is consumed."""
    if has_expansion:
        c.require(producing_report_path and pp_path,
                  f"{who}: --expansion-manifest requires --decision-report and "
                  f"--producing-primary (the R1 evidence bundle)")
    else:
        stray = [n for n, v in
                 (("--decision-report", producing_report_path),
                  ("--producing-primary", pp_path),
                  ("--producing-second", ps_path),
                  ("--producing-arbitration", pa_path)) if v]
        c.require(not stray,
                  f"{who}: producing-evidence flags {stray} require "
                  f"--expansion-manifest (passed without an expansion; ignored otherwise)")


def cmd_decide(argv):
    flags, _ = c.parse_flags(argv, allowed=DECIDE_FLAGS)
    primary_path = c.flag1(flags, "primary")
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    out_dir = Path(c.flag1(flags, "out"))
    expansion_path = c.flag_opt(flags, "expansion-manifest")
    producing_report_path = c.flag_opt(flags, "decision-report")
    second_path = c.flag_opt(flags, "second")
    arbitration_path = c.flag_opt(flags, "arbitration")
    pp_path = c.flag_opt(flags, "producing-primary")
    ps_path = c.flag_opt(flags, "producing-second")
    pa_path = c.flag_opt(flags, "producing-arbitration")
    # F18/F19: frozen lock first, then full manifest validation before any read.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    check_producing_evidence_presence(
        bool(expansion_path), producing_report_path, pp_path, ps_path, pa_path, "decide")
    expansions = []
    expansion_shas = []
    if expansion_path:
        # P0-3: verify_producing_report reads the R1 report ONCE and returns
        # (report, report_sha); BOTH are reused here, never re-read.
        # P0: read the expansion ONCE too -- object and pinned SHA come from
        # the same bytes and are passed to validate_decision_inputs.
        em_bytes = Path(expansion_path).read_bytes()
        em_sha = c.sha256_bytes(em_bytes)
        em = json.loads(em_bytes.decode("utf-8"))
        rep, rep_sha = verify_producing_report(
            producing_report_path, sample_manifest, sm_sha,
            chapter_manifest, source, source_desc, is_fake,
            pp_path, ps_path, pa_path)
        sampling.validate_expansion_manifest(
            em, sample_manifest, chapter_manifest, source, source_desc,
            sm_sha, expected_test_only=is_fake,
            report=rep, report_sha=rep_sha)
        expansions = [em]
        expansion_shas = [em_sha]
    # F22 receipt gate + primary/second/arbitration validation + verdict
    # computation are all in the shared helper (same path as `expand`).
    _primary, _second, _arbitration, report = validate_decision_inputs(
        sample_manifest, expansions, chapter_manifest, source, source_desc,
        sm_sha, expansion_shas, is_fake, primary_path, second_path,
        arbitration_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decision_report_v1.json").write_bytes(c.serialize_json(report))
    print("verdict:", report["verdict"], "| fired:", report["fired_rules"],
          "| pending_expands:", report["pending_expands"],
          "| test_only:", report["test_only"])


def cmd_packet(argv):
    flags, _ = c.parse_flags(argv, allowed=PACKET_FLAGS)
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    out_dir = Path(c.flag1(flags, "out"))
    expansion_path = c.flag_opt(flags, "expansion-manifest")
    producing_report_path = c.flag_opt(flags, "decision-report")
    pp_path = c.flag_opt(flags, "producing-primary")
    ps_path = c.flag_opt(flags, "producing-second")
    pa_path = c.flag_opt(flags, "producing-arbitration")
    # F18/F19: frozen lock first, then full manifest validation before any read.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    check_producing_evidence_presence(
        bool(expansion_path), producing_report_path, pp_path, ps_path, pa_path, "packet")
    expansions = []
    expansion_shas = []
    if expansion_path:
        # P0-3: verify_producing_report reads the R1 report ONCE and returns
        # (report, report_sha); BOTH are reused here, never re-read.
        # P0: read the expansion ONCE too -- object and pinned SHA come from
        # the same bytes and are reused for the packet binding below.
        em_bytes = Path(expansion_path).read_bytes()
        em_sha = c.sha256_bytes(em_bytes)
        em = json.loads(em_bytes.decode("utf-8"))
        rep, rep_sha = verify_producing_report(
            producing_report_path, sample_manifest, sm_sha,
            chapter_manifest, source, source_desc, is_fake,
            pp_path, ps_path, pa_path)
        sampling.validate_expansion_manifest(
            em, sample_manifest, chapter_manifest, source, source_desc,
            sm_sha, expected_test_only=is_fake,
            report=rep, report_sha=rep_sha)
        expansions = [em]
        expansion_shas = [em_sha]
    # F20: packet binds sample/expansion manifests by RAW on-disk byte SHA.
    packet = build_packet(sample_manifest, expansions, chapter_manifest, source,
                          sm_sha, expansion_shas, source_desc)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "review_packet_v1.json").write_bytes(c.serialize_json(packet))
    print("review packet:", out_dir / "review_packet_v1.json")
    print("items:", len(packet["items"]), "chapters:", len(packet["chapters"]),
          "test_only:", packet["test_only"])


def check_finalize(report):
    c.require(report.get("kind") == "decision_report_v1",
              "finalize: not a decision report")
    c.require(report.get("verdict") in ("ACCEPT", "REJECT"),
              f"finalize requires a terminal verdict (ACCEPT|REJECT), got {report.get('verdict')!r}")
    c.require(not report.get("test_only"),
              "finalize refuses test_only=fake decision reports (F13/F17); "
              "fake products must not enter final acceptance")


def build_final_package(report, primary, report_sha, exp_shas, artifact_files,
                        exp_files=None, today=None):
    """Pure assembler for final_acceptance_package_v1. `report` is the
    already-verified (recomputed + byte-equal + terminal) decision report and
    `primary` the verified primary package; all SHAs are raw on-disk values.
    Split out so the assembly logic is unit-testable without the frozen
    production chain or the fake-refusal gate.

    `artifact_files` maps each consumed role -> the BASENAME of the file the
    caller actually passed on the CLI (e.g. {"primary_review": "primary_ok.json",
    ...}); `exp_files` is the parallel basename list for `exp_shas`. The
    assembler NEVER fabricates a canonical filename: the recorded file identity
    is the real consumed input (design section 8 "记录所用版本与各自 SHA" -- the
    version is identified by the actually-consumed file plus its content SHA;
    within one package each role is unique and expansion entries carry an
    index, and the content-address SHA disambiguates same-named files from
    different directories). A missing identity fails closed rather than
    defaulting to a name that could be false. Optional receipts (second /
    arbitration / expansions) are listed only when actually consumed."""
    import datetime

    def file_of(role):
        name = artifact_files.get(role)
        c.require(isinstance(name, str) and name,
                  f"finalize: missing consumed-file identity for artifact {role!r}")
        return name

    artifacts = [
        {"role": "decision_report", "file": file_of("decision_report"),
         "sha256": report_sha},
        {"role": "primary_review", "file": file_of("primary_review"),
         "sha256": report["primary_sha256"]},
        {"role": "sample_manifest", "file": file_of("sample_manifest"),
         "sha256": report["sample_manifest_sha256"]},
    ]
    if report.get("second_review_sha256"):
        artifacts.append({"role": "second_review", "file": file_of("second_review"),
                          "sha256": report["second_review_sha256"]})
    if report.get("arbitration_sha256"):
        artifacts.append({"role": "arbitration", "file": file_of("arbitration"),
                          "sha256": report["arbitration_sha256"]})
    exp_files = exp_files or []
    for i, s in enumerate(exp_shas):
        name = exp_files[i] if i < len(exp_files) else None
        c.require(isinstance(name, str) and name,
                  f"finalize: missing consumed-file identity for expansion[{i}]")
        artifacts.append({"role": "expansion_manifest", "index": i,
                          "file": name, "sha256": s})
    return {
        "schema_version": "1.0",
        "kind": "final_acceptance_package_v1",
        "final_verdict": report["verdict"],
        "decision_report_sha256": report_sha,
        "primary_sha256": report["primary_sha256"],
        "second_review_sha256": report.get("second_review_sha256"),
        "arbitration_sha256": report.get("arbitration_sha256"),
        "sample_manifest_sha256": report["sample_manifest_sha256"],
        "expansion_manifests_sha256": exp_shas,
        "artifacts": artifacts,
        "reviewer_list": primary.get("reviewer_list"),
        "generated_at": (today or datetime.date.today()).isoformat(),
    }


FINALIZE_FLAGS = {"decision-report", "primary", "sample-manifest",
                  "chapter-manifest", "out", "candidate-commit", "data-root",
                  "second", "arbitration", "expansion-manifest",
                  "decision-report-r1", "producing-primary",
                  "producing-second", "producing-arbitration"}


def cmd_finalize(argv):
    flags, _ = c.parse_flags(argv, allowed=FINALIZE_FLAGS)
    report_path = c.flag1(flags, "decision-report")
    primary_path = c.flag1(flags, "primary")
    sm_path = c.flag1(flags, "sample-manifest")
    chman_path = c.flag1(flags, "chapter-manifest")
    out_dir = Path(c.flag1(flags, "out"))
    second_path = c.flag_opt(flags, "second")
    arbitration_path = c.flag_opt(flags, "arbitration")
    # Only one parallel expansion round exists (F19): at most one expansion,
    # and when present it must carry the R1 producing report + evidence bundle.
    expansion_path = c.flag_opt(flags, "expansion-manifest")
    r1_report_path = c.flag_opt(flags, "decision-report-r1")
    pp_path = c.flag_opt(flags, "producing-primary")
    ps_path = c.flag_opt(flags, "producing-second")
    pa_path = c.flag_opt(flags, "producing-arbitration")
    # P0-1: finalize must NOT trust report fields. Re-run the EXACT chain the
    # producer/consumers run. Order matters: recompute -> RAW on-disk byte
    # equality -> check_finalize (terminal verdict + fake refusal) -> package.
    # The byte-equality gate runs BEFORE check_finalize so a tampered fake
    # report is rejected for byte mismatch (the real failure mode), while a
    # canonical fake report is still rejected by the fake-refusal gate.
    is_fake = "data-root" in flags
    source, source_desc = c.build_source(flags, expected_test_only=(True if is_fake else False))
    chapter_manifest, chman_sha = sampling.load_chapter_manifest(chman_path)
    sample_manifest, sm_sha = c.load_json_with_sha(sm_path)
    sampling.validate_sample_manifest(sample_manifest, chapter_manifest, source,
                                      source_desc, chman_sha,
                                      expected_test_only=is_fake)
    check_producing_evidence_presence(
        bool(expansion_path), r1_report_path, pp_path, ps_path, pa_path, "finalize")
    expansions = []
    expansion_shas = []
    if expansion_path:
        # P0: read the expansion ONCE -- object and pinned SHA come from the
        # same bytes and are reused for validation AND the final-package SHA
        # binding (no re-read, no TOCTOU window).
        em_bytes = Path(expansion_path).read_bytes()
        em_sha = c.sha256_bytes(em_bytes)
        em = json.loads(em_bytes.decode("utf-8"))
        rep, rep_sha = verify_producing_report(
            r1_report_path, sample_manifest, sm_sha,
            chapter_manifest, source, source_desc, is_fake,
            pp_path, ps_path, pa_path)
        sampling.validate_expansion_manifest(
            em, sample_manifest, chapter_manifest, source, source_desc,
            sm_sha, expected_test_only=is_fake,
            report=rep, report_sha=rep_sha)
        expansions = [em]
        expansion_shas = [em_sha]
    _primary, _second, _arbitration, recomputed = validate_decision_inputs(
        sample_manifest, expansions, chapter_manifest, source, source_desc,
        sm_sha, expansion_shas,
        is_fake, primary_path, second_path, arbitration_path)
    # P0-2 / F20: the on-disk decision report must be byte-identical to the
    # verdict recomputed from the receipts (CRLF / whitespace / key reorder /
    # duplicate keys all rejected). Runs BEFORE the terminal/fake gate.
    actual_bytes = Path(report_path).read_bytes()
    expected_bytes = c.serialize_json(recomputed)
    c.require(actual_bytes == expected_bytes,
              "finalize: on-disk decision report bytes do not match the verdict "
              "recomputed from the receipts and frozen data (hand-crafted or "
              "re-serialized report rejected)")
    check_finalize(recomputed)
    # design section 8: record the REAL consumed-file identity (basename of
    # each validated CLI input) -- never a fabricated canonical name -- bound
    # to its content SHA.
    artifact_files = {
        "decision_report": Path(report_path).name,
        "primary_review": Path(primary_path).name,
        "sample_manifest": Path(sm_path).name,
    }
    if second_path:
        artifact_files["second_review"] = Path(second_path).name
    if arbitration_path:
        artifact_files["arbitration"] = Path(arbitration_path).name
    exp_files = [Path(expansion_path).name] if expansion_path else []
    package = build_final_package(recomputed, _primary,
                                  c.sha256_bytes(actual_bytes), expansion_shas,
                                  artifact_files, exp_files)
    # P0 (design section 8): publish through the atomic create-if-absent
    # primitive (temp file -> fsync -> read-back verify -> os.link). Both
    # sequential re-runs and CONCURRENT finalize processes fail closed: the
    # sealed final path is created exactly once, never partially written and
    # never overwritten. A correction is published by re-running finalize into
    # a NEW --out directory (the toolchain's "_v2" new-version publication).
    c.publish_new_file(out_dir / "final_acceptance_package_v1.json",
                       c.serialize_json(package))
    print("final acceptance package:", out_dir / "final_acceptance_package_v1.json")
    print("final verdict:", package["final_verdict"])


def main(argv):
    c.require(argv, "usage: classic_acceptance_review.py "
                     "<packet|validate-primary|validate-second|validate-arbitration|decide|finalize> [flags]")
    cmd = argv[0]
    try:
        if cmd == "packet":
            cmd_packet(argv[1:])
        elif cmd == "validate-primary":
            cmd_validate_primary(argv[1:])
        elif cmd == "validate-second":
            cmd_validate_second(argv[1:])
        elif cmd == "validate-arbitration":
            cmd_validate_arbitration(argv[1:])
        elif cmd == "decide":
            cmd_decide(argv[1:])
        elif cmd == "finalize":
            cmd_finalize(argv[1:])
        else:
            raise RuntimeError(f"unknown subcommand: {cmd!r}")
    except RuntimeError as e:
        print(f"{cmd} FAILED: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))