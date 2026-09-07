"""Generate and verify the classic-texts acceptance integration closure.

Tracked, re-runnable source of docs/superpowers/specs/
2026-08-29-classic-texts-acceptance-integration-closure.{json,md}:

    python scripts/generate_acceptance_integration_closure.py generate
    python scripts/generate_acceptance_integration_closure.py --check
    python scripts/generate_acceptance_integration_closure.py generate --no-legacy \
        --candidate-commit <C2> --base-commit <base> --tooling-pin-commit <phaseA>
    python scripts/generate_acceptance_integration_closure.py --check --no-legacy \
        --candidate-commit <C2> --base-commit <base> --tooling-pin-commit <phaseA>

In no-legacy mode the tooling pin is an EXTERNAL frozen input: BOTH
generate and --check require --tooling-pin-commit (a full 40-hex phase-A
SHA) and exit 2 without it. The pin is never bootstrapped from the disk
JSON or from runtime HEAD, and build_closure records the pin it actually
used, so swapping the recorded pin for another commit with identical
tooling content cannot self-validate.

`generate` rewrites the canonical artifacts and refuses to write when the
recomputed closure fails verification. In BOTH --check modes the
authoritative closure object is RECOMPUTED from Git via build_closure();
the artifacts on disk are then compared against that recomputation
byte-for-byte (canonical JSON / rendered MD). The disk JSON is never used
as the expected state. Any drift exits non-zero.

The closure gates are EXECUTABLE, not textual: build_candidate_overlay_tree()
materialises the C2 tree into a per-run temporary git index (GIT_INDEX_FILE)
via `git read-tree <base>` plus one `git update-index --cacheinfo` per
candidate blob, and verify_candidate_tree() then enforces, against the
resulting tree (or any C2 commit/tree): zero deletions vs the base, exact
candidate blobs for every closure path, the changed-path set equal to the
695 paths whose blobs differ from the base, and byte-identity for every
path outside the closure. The narrow-tree error (only the 698 paths, which
would delete the rest of main) is built by build_narrow_candidate_tree() and
MUST be rejected by the same verifier (negative test).

Post-migration on the clean branch the closure artifacts and this generator
are part of the migrated infrastructure layer; `--check --candidate-commit
<C2> --base-commit <base> --no-legacy` re-runs every gate with no
dependency on the unpushed old-candidate object: recorded blob OIDs come
from the committed closure JSON (existence checked via cat-file -e), tooling
blobs are compared against HEAD, and the overlay tree is built from the
recorded OIDs.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "docs" / "superpowers" / "specs"
JSON_PATH = SPECS / "2026-08-29-classic-texts-acceptance-integration-closure.json"
MD_PATH = SPECS / "2026-08-29-classic-texts-acceptance-integration-closure.md"
GENERATED_OUTPUTS = [JSON_PATH.relative_to(ROOT).as_posix(),
                     MD_PATH.relative_to(ROOT).as_posix()]
AUDIT_OUTPUT_EXCLUSION_GLOB = (
    "docs/superpowers/*classic-texts-review-e*-receipt.md"
)
OLD_CANDIDATE = "80bc630396f31c6b6c122e49ef97f6d912e6f636"
MERGE_BASE = "3d3b41cf65af487b03ca5233a109fee14191b88c"
TOOLING_PIN_COMMIT = "ed5493a94d0268b88f2dca448f963880e7cc1ad5"
TOOLING_PIN_SUBJECT = "Finalize v5.0 freeze anchor record: pin CLASSIC_ACCEPTANCE_FREEZE_V2 tag OID"
MANIFESTS = (
    "2026-08-20-classic-texts-chapter-identity-manifest.json",
    "2026-08-20-classic-texts-candidate-identity-manifest.json",
)

INFRA_SOURCE_PATHS = [
    "scripts/generate_acceptance_integration_closure.py",
    "tests/test_generate_acceptance_integration_closure.py",
]

TOOLING = [
    ("scripts/classic_acceptance_common.py", "code"),
    ("scripts/classic_acceptance_sampling.py", "code"),
    ("scripts/classic_acceptance_review.py", "code"),
    ("scripts/generate_acceptance_manifests.py", "generator"),
    ("tests/classic_acceptance_fixtures.py", "test"),
    ("tests/test_classic_acceptance_review.py", "test"),
    ("tests/test_classic_acceptance_sampling.py", "test"),
    ("tests/test_classic_acceptance_e2e.py", "test"),
    ("tests/test_generate_acceptance_manifests.py", "test"),
    ("docs/superpowers/specs/2026-08-20-classic-texts-chapter-identity-manifest.json", "freeze_payload"),
    ("docs/superpowers/specs/2026-08-20-classic-texts-candidate-identity-manifest.json", "freeze_payload"),
    ("docs/superpowers/specs/2026-08-20-classic-texts-acceptance-freeze.json", "freeze_payload"),
    ("docs/superpowers/specs/2026-08-20-classic-texts-freeze-anchor-record.json", "freeze_payload"),
    ("docs/superpowers/specs/2026-08-20-classic-texts-candidate-acceptance-design.md", "freeze_payload"),
    ("docs/superpowers/plans/2026-08-23-classic-texts-manual-acceptance-tooling.md", "doc"),
    ("docs/superpowers/2026-08-29-classic-texts-posix-cleanup-verification-receipt.md", "doc"),
    (".gitignore", "config"),
]

OVERSIZED = [
    ("knowledge_base/classic_texts/QUALITY_REPORT.json",
     "51ec7648e191a5709c00a12765ec131b5bea814e", 354001243, "16c72b4"),
    ("knowledge_base/classic_texts/sanmingtonghui/provenance.json",
     "65a627ae8fbfe2f72cead578388ee9a4019f7a7e", 314130603, "16c72b4"),
    ("knowledge_base/classic_texts/sanmingtonghui/remediation_meta.json",
     "f6649813f1e550afdd69428738ba7f71f869458a", 312701489, "f64a25d"),
]

EXCLUDED_TRACK = {
    "distillation_track_tooling": [
        "scripts/distill_lib.py",
        "scripts/fetch_sanming_chapters.py",
        "scripts/fill_missing_chapters.py",
        "scripts/fetch_sanming_full.py",
        "scripts/recover_deleted_to_quarantine.py",
        "scripts/run_sanming_production.py",
        "tests/test_classic_distillation_sanming.py",
        "docs/superpowers/plans/2026-08-15-phase9a-gold-acquisition.md",
        "docs/superpowers/specs/2026-08-14-phase9a-gold-data-spec.md",
        "docs/superpowers/specs/2026-08-16-classic-distillation-parameter-expansion-design.md",
    ],
    "phase8_evidence": [
        "docs/phase8/marriage-capability/non_e2e_gate_junit.xml",
        "docs/phase8/marriage-capability/non_e2e_gate_receipt.json",
    ],
}

EXPECTED = {
    "refs": 1085,
    "unique": 699,
    "kb_unique": 698,
    "kb_bytes": 14997976,
    "tooling_count": 17,
    "tooling_bytes": 1594169,
    "groups": {"derived_root_raw": 303, "extracted_raw": 383, "quarantine": 1,
               "rules_mcq_output": 8, "snapshot_identity": 3},
    "data_overlap_with_main": 9,
    "data_same_blob_on_main": 3,
    "data_changed_vs_main": 695,
    "tooling_overlap_with_main": 1,
    "touch_binding_files": 13,
    "touch_short_only_files": 0,
}

EXPECTED_NON_KB_UNIQUE = ["scripts/generate_acceptance_manifests.py"]

PATH_RE = re.compile(r"^(knowledge_base|docs|scripts|tests|data|benchmark)/\S+$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
FULL_NEEDLE = OLD_CANDIDATE.encode("ascii")
SHORT_NEEDLE = FULL_NEEDLE[:7]  # git default abbreviated prefix length
SKIP_DIRS = {".git", ".venv", ".tmp", ".cache", ".chromadb_case_index",
             ".better-harness", "__pycache__", "node_modules", ".idea",
             ".qoder", ".reasonix", ".trae"}


def git(args, check=True, env=None):
    r = subprocess.run(["git", "-C", str(ROOT), "-c", "core.quotePath=false", *args],
                       capture_output=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace"))
    return r


def object_exists(oid):
    return git(["cat-file", "-e", oid], check=False).returncode == 0


def rev_exists(rev):
    return git(["rev-parse", "--verify", f"{rev}^{{commit}}"], check=False).returncode == 0


def resolve_commit(rev):
    return git(["rev-parse", "--verify", f"{rev}^{{commit}}"]).stdout.decode().strip()


def ls_tree(rev):
    r = git(["ls-tree", "-r", "-l", rev], check=False)
    if r.returncode != 0:
        return None
    tree = {}
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if parts[1] == "blob":
            tree[path] = (parts[2], int(parts[3]))
    return tree


def _walk(node, refs):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and PATH_RE.match(k):
                refs.append(k)
            _walk(v, refs)
    elif isinstance(node, list):
        for v in node:
            _walk(v, refs)
    elif isinstance(node, str):
        if PATH_RE.match(node):
            refs.append(node)


def collect_refs():
    refs = []
    for name in MANIFESTS:
        doc = json.loads((SPECS / name).read_text(encoding="utf-8"))
        _walk(doc, refs)
    return refs


def group_of(p):
    if re.search(r"all_rules\.json$", p) or re.search(r"all_mcq\.jsonl$", p):
        return "rules_mcq_output"
    if re.search(r"quarantine_[a-z]+\.jsonl?$", p):
        return "quarantine"
    if "/source_snapshots/" in p and "/extracted/raw_" in p:
        return "extracted_raw"
    if "snapshot" in p.lower():
        return "snapshot_identity"
    if re.search(r"/raw_[^/]*\.txt$", p):
        return "derived_root_raw"
    return "other"


def touch_scan_excluded(rel):
    return rel in GENERATED_OUTPUTS or fnmatch.fnmatchcase(
        rel, AUDIT_OUTPUT_EXCLUSION_GLOB
    )


def scan_touch_list():
    binding, short_only = [], []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            try:
                if fp.stat().st_size > 5 * 1024 * 1024:
                    continue
                data = fp.read_bytes()
            except OSError:
                continue
            short_n = data.count(SHORT_NEEDLE)
            if not short_n:
                continue
            rel = fp.relative_to(ROOT).as_posix()
            if touch_scan_excluded(rel):
                continue
            full_n = data.count(FULL_NEEDLE)
            if full_n:
                kind = ("closure infrastructure constant (OLD_CANDIDATE); this "
                        "generator stays in the migration and supports the new C2 "
                        "via --candidate-commit, so its own constant is patched to "
                        "C2 at re-freeze step 2"
                        if rel in INFRA_SOURCE_PATHS else
                        "full 40-hex candidate SHA binding or chain record; "
                        "updated or regenerated at re-freeze")
                binding.append({"path": rel, "full_sha_occurrences": full_n,
                                "short_prefix_occurrences": short_n,
                                "classification": kind})
            else:
                short_only.append({
                    "path": rel, "short_prefix_occurrences": short_n,
                    "classification": ("short-SHA mention only (docstring or "
                                       "abbreviated-SHA rejection test); not a "
                                       "production freeze binding; no update "
                                       "required at re-freeze")})
    binding.sort(key=lambda e: e["path"])
    short_only.sort(key=lambda e: e["path"])
    return binding, short_only


def kb_remainder_paths(data_paths):
    out = git(["diff", "--name-status", "origin/main...HEAD", "--", "knowledge_base"])
    changed = [ln.split("\t", 1)[1] for ln in out.stdout.decode("utf-8", "replace").splitlines()
               if ln.strip()]
    over = {o[0] for o in OVERSIZED}
    return sorted(p for p in changed if p not in set(data_paths) and p not in over)


def _temp_index_tree(index_file, base_read, entries):
    """Build a tree in a per-run temp index: one read-tree (--empty or the
    full base tree) plus a SINGLE batched update-index --index-info for all
    entries (avoids ~700 subprocess calls)."""
    env = {**os.environ, "GIT_INDEX_FILE": str(index_file)}

    def run(args, input_bytes=None):
        r = subprocess.run(["git", "-C", str(ROOT), "-c", "core.quotePath=false", *args],
                           capture_output=True, input=input_bytes, env=env)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", "replace"))
        return r

    run(["read-tree"] + ([base_read] if base_read else ["--empty"]))
    info = "".join(f"100644 {e['oid']} 0\t{e['path']}\n" for e in entries)
    if info:
        run(["update-index", "--index-info"], input_bytes=info.encode("utf-8"))
    return run(["write-tree"]).stdout.decode().strip()


def build_candidate_overlay_tree(entries, base_commit):
    """Overlay C2 tree: full base tree + candidate blobs via temp index.

    entries: [{path, oid, size}] carrying the 698 candidate blob OIDs.
    The index starts from the FULL base tree (read-tree) and each closure
    path is overlaid, so nothing outside the closure can be deleted.
    Returns the tree OID.
    """
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="closure_index_", dir=str(ROOT / ".tmp")) as d:
        return _temp_index_tree(Path(d) / "index", base_commit, entries)


def build_narrow_candidate_tree(entries):
    """The wrong tree: only the 698 closure paths, nothing from base.

    Reproduces the v2 policy that deleted every other main file;
    verify_candidate_tree must reject it.
    """
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="closure_index_", dir=str(ROOT / ".tmp")) as d:
        return _temp_index_tree(Path(d) / "index", None, entries)


def _tree_changed_paths(base_ref, tree_ref):
    out = git(["diff", "--name-status", "--no-renames",
               f"{base_ref}^{{tree}}", tree_ref])
    adds, dels, mods = set(), set(), set()
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        st, path = line.split("\t", 1)
        if st.startswith("A"):
            adds.add(path)
        elif st.startswith("D"):
            dels.add(path)
        else:
            mods.add(path)
    return adds, dels, mods


def verify_candidate_tree(entries, expected_oids, base_tree, base_ref, tree_ref):
    """Executable gate. entries: closure paths; expected_oids: path->oid
    the tree MUST carry; base_tree: ls_tree of the base; base_ref/tree_ref:
    git refs (commits or tree OIDs). Returns error strings."""
    errors = []
    c2_tree = ls_tree(tree_ref)
    if c2_tree is None:
        return [f"cannot read tree {tree_ref}"]
    adds, dels, mods = _tree_changed_paths(base_ref, tree_ref)
    expected_paths = set(expected_oids)
    expected_changed = {p for p in expected_paths
                        if expected_oids[p] != base_tree.get(p, (None,))[0]}
    if dels:
        errors.append(f"gate1 zero-deletions: tree deletes {len(dels)} base paths "
                      f"(first 10: {sorted(dels)[:10]})")
    blob_bad = sorted(p for p in expected_paths
                      if c2_tree.get(p, (None,))[0] != expected_oids.get(p))
    if blob_bad:
        errors.append(f"gate2 candidate-blob-match: {len(blob_bad)} closure paths "
                      f"fail blob identity (first 10: {blob_bad[:10]})")
    actual_changed = adds | mods
    if actual_changed != expected_changed:
        extra = sorted(actual_changed - expected_changed)[:10]
        missing = sorted(expected_changed - actual_changed)[:10]
        errors.append(f"gate3 diff-set: changed={len(actual_changed)} "
                      f"expected={len(expected_changed)} extra={extra} missing={missing}")
    outside_drift = sorted(p for p, meta in c2_tree.items()
                           if p not in expected_paths and base_tree.get(p) != meta)
    if outside_drift:
        errors.append(f"gate4 outside-closure identity: {len(outside_drift)} non-closure "
                      f"paths changed (first 10: {outside_drift[:10]})")
    return errors


def overlay_entries(data_entries, candidate_tree, use_legacy):
    entries = []
    for e in data_entries:
        oid = e["data_blob_oid"]
        if use_legacy:
            if candidate_tree is None or e["path"] not in candidate_tree \
                    or candidate_tree[e["path"]][0] != oid:
                raise RuntimeError(f"legacy candidate mismatch at {e['path']}")
        elif not object_exists(oid):
            raise RuntimeError(f"candidate blob {oid[:12]} ({e['path']}) missing from object store")
        entries.append({"path": e["path"], "oid": oid, "size": e["size"]})
    return entries


def build_closure(candidate_commit=OLD_CANDIDATE, base_commit=MERGE_BASE,
                  use_legacy=True, tooling_pin=None):
    """Build the closure dict.

    legacy (pre-migration, `generate` on acceptance/task1): candidate data
    blobs are read from the OLD_CANDIDATE tree, tooling blobs from the
    reviewed TOOLING_PIN_COMMIT, origin/main used for presence/same flags.

    no-legacy (`generate --no-legacy --candidate-commit C2 --base-commit
    base --tooling-pin-commit P` on the clean branch): candidate data
    blobs are read from the C2 tree; tooling blobs are read from the
    EXPLICIT phase-A tooling pin commit P (the CLI demands the flag; the
    HEAD fallback below serves only direct library calls, e.g. the tests)
    and P is recorded verbatim in source.tooling_blob_pin_commit;
    infrastructure blobs from HEAD; the base tree is used for
    presence/same flags. This is the executable step-6b production path
    that freezes the NEW chain's OID table. Requires C2 and the pin commit
    to exist.
    """
    if not use_legacy and not rev_exists(candidate_commit):
        raise RuntimeError(f"candidate commit {candidate_commit} does not exist; "
                           "cannot generate a new-chain closure from a missing C2")
    data_ref = OLD_CANDIDATE if use_legacy else candidate_commit
    if use_legacy:
        tooling_ref = TOOLING_PIN_COMMIT
    else:
        tooling_ref = tooling_pin if tooling_pin else resolve_commit("HEAD")
        if not SHA40_RE.match(tooling_ref) or not rev_exists(tooling_ref):
            raise RuntimeError(f"tooling pin commit {tooling_ref} is missing "
                               "or not a full 40-hex SHA")
    flags_ref = "origin/main" if use_legacy else base_commit
    cand = ls_tree(data_ref)
    if cand is None:
        raise RuntimeError(f"data source tree {data_ref} not in object store")
    flags_tree = ls_tree(flags_ref)
    if flags_tree is None:
        raise RuntimeError(f"flags base reference {flags_ref} not in object store")
    pin_tree = ls_tree(tooling_ref)
    if pin_tree is None:
        raise RuntimeError(f"tooling reference {tooling_ref} not in object store")
    refs = collect_refs()
    counter = Counter(refs)
    unique = sorted(counter)
    kb = [p for p in unique if p.startswith("knowledge_base/")]
    data_entries = []
    for p in kb:
        oid, size = cand[p]
        data_entries.append({
            "path": p,
            "data_blob_oid": oid,
            "size": size,
            "group": group_of(p),
            "refs": counter[p],
            "data_source_ref": data_ref,
            "present_on_flags_base": p in flags_tree,
            "same_blob_on_flags_base": flags_tree.get(p, (None,))[0] == oid,
        })
    tooling_entries = []
    for p, g in TOOLING:
        oid, size = pin_tree[p]
        tooling_entries.append({
            "path": p,
            "tooling_blob_oid": oid,
            "size": size,
            "group": g,
            "tooling_ref": tooling_ref,
            "present_on_flags_base": p in flags_tree,
        })
    head_tree = ls_tree("HEAD")
    infra_entries = []
    for p in INFRA_SOURCE_PATHS:
        if p not in head_tree:
            continue
        oid, size = head_tree[p]
        infra_entries.append({
            "path": p,
            "blob_oid_at_infrastructure_commit": oid,
            "size": size,
            "group": "infrastructure_source",
            "migrated": True,
        })
    generated_entries = [
        {"path": GENERATED_OUTPUTS[0], "group": "infrastructure_generated",
         "migrated": True, "note": "regenerated on the clean branch via generate/--check"},
        {"path": GENERATED_OUTPUTS[1], "group": "infrastructure_generated",
         "migrated": True, "note": "regenerated on the clean branch via generate/--check"},
    ]
    binding, short_only = scan_touch_list()
    remainder = kb_remainder_paths({e["path"] for e in data_entries})
    chain_mode = "legacy" if use_legacy else "new_chain"
    return {
        "schema_version": "2.3",
        "kind": "classic_texts_acceptance_integration_closure",
        "date": "2026-08-29",
        "chain_mode": chain_mode,
        "source": {
            "branch": "acceptance/task1" if use_legacy else "clean integration branch",
            "tooling_blob_pin_commit": TOOLING_PIN_COMMIT if use_legacy
            else tooling_ref,
            "tooling_blob_pin_subject": TOOLING_PIN_SUBJECT if use_legacy
            else "tooling blobs pinned at the explicit phase-A tooling pin commit (frozen OID table)",
            "tooling_blob_pin_note": ("the 17 tooling blobs are pinned at this reviewed "
                                      "commit (full 40-hex, rev-parse round-tripped)"
                                      if use_legacy else
                                      "the 17 tooling blobs are pinned at the EXPLICIT "
                                      "--tooling-pin-commit (external frozen input, full "
                                      "40-hex, rev-parse round-tripped); a phase-B "
                                      "artifact-only commit never changes it"),
            "candidate_data_ref": data_ref,
            "flags_base_ref": flags_ref,
        },
        "merge_base": MERGE_BASE if use_legacy else base_commit,
        "candidate_commit": data_ref,
        "old_candidate_commit": OLD_CANDIDATE,
        "tooling_paths": tooling_entries,
        "candidate_data_paths": data_entries,
        "integration_infrastructure_layer": {
            "note": ("closure infrastructure is part of the migrated chain, not "
                     "retired: the clean branch carries the generator, its tests "
                     "and the generated artifacts so every gate is re-runnable in "
                     "CI; post-migration invocation: --check --candidate-commit "
                     "<C2> --base-commit <base> --no-legacy (no dependency on the "
                     "unpushed old candidate object)"),
            "source_files": infra_entries,
            "generated_artifacts": generated_entries,
            "migrated_path_count": len(INFRA_SOURCE_PATHS) + len(generated_entries),
        },
        "migration_total": {
            "tooling_paths": len(tooling_entries),
            "candidate_data_paths": len(data_entries),
            "infrastructure_paths": len(INFRA_SOURCE_PATHS) + len(generated_entries),
            "total_paths": (len(tooling_entries) + len(data_entries)
                            + len(INFRA_SOURCE_PATHS) + len(generated_entries)),
            "note": ("candidate data lands in overlay commit C2 (698 paths); tooling "
                     "and infrastructure land as normal commits on top"),
        },
        "excluded_paths": {
            "oversized": [{"path": p, "blob_oid": oid, "size": size,
                           "introduced_by": intro} for p, oid, size, intro in OVERSIZED],
            "distillation_track_tooling": EXCLUDED_TRACK["distillation_track_tooling"],
            "phase8_evidence": EXCLUDED_TRACK["phase8_evidence"],
            "knowledge_base_remainder": {
                "count": len(remainder),
                "paths": remainder,
                "note": ("changed knowledge_base paths outside the manifest read closure "
                         "and the oversized list (ledger archives, progress/distill "
                         "logs, validation reports)"),
            },
        },
        "freeze_anchors": {
            "freeze_tag": "CLASSIC_ACCEPTANCE_FREEZE_V2",
            "expected_tag_oid": "98c7cb90b0f0d1b8d3f512c657c3a1614303cdf7",
            "freeze_commit": "d7922bb932e8d572cd3c55d0aeca04442d7dd5f7",
            "tooling_payload_commit": "ba7cc51423e27502c8fc19fbdaa31bfe77807491",
            "candidate_commit": OLD_CANDIDATE,
            "generator_blob_oid": "9fa0fdc6b190316a9804e6cdd2be6a87bae92ff4",
            "manifest_sha256_lf": {
                "2026-08-20-classic-texts-candidate-identity-manifest.json":
                    "0279e30b92f70f8b7cce9c786070fc201cfc3fac86826ef6403b15ad90c5aad2",
                "2026-08-20-classic-texts-chapter-identity-manifest.json":
                    "ba8ab35e7b98e3a0578f7b62f758e2faff1bbe73d480e153c25b6c74b497d1cf",
            },
            "review_e_code_identity_blobs": {
                "tests/test_classic_acceptance_review.py":
                    "09760df093604a67adc7023f26edceffb272c0bd",
                "tests/classic_acceptance_fixtures.py":
                    "e393cdd67b830d3c0d8cc29b3311c9312776abc3",
                "scripts/classic_acceptance_common.py":
                    "2761e8589bb44b471d493323edb09a5fe26d449d",
                "scripts/classic_acceptance_sampling.py":
                    "703b44cf5d47354d3dbf9f670d46c5fa0d6be20f",
                "scripts/classic_acceptance_review.py":
                    "9e91a8e4a856e92f86311db4f5b9b486fadf7546",
            },
        },
        "code_freeze_touch_list": {
            "binding_full_sha": binding,
            "short_sha_only": short_only,
            "audit_output_exclusion_glob": AUDIT_OUTPUT_EXCLUSION_GLOB,
            "generated_outputs_excluded_from_scan": [
                {"path": GENERATED_OUTPUTS[0],
                 "note": ("generated artifact; carries the full candidate SHA twice "
                          "(old_candidate_commit, freeze_anchors.candidate_commit), "
                          "both derived from anchors")},
                {"path": GENERATED_OUTPUTS[1],
                 "note": ("generated artifact; renders old_candidate_commit "
                          "truncated to 12 chars (short prefix on disk)")},
            ],
            "scan_note": ("needle is the 8-hex prefix 80bc630; scope is repository INPUT "
                          "files - the two generated artifacts and the explicit Review E "
                          "audit-receipt family are excluded because "
                          "their candidate-SHA content is derived from the anchors and "
                          "including them makes the scan self-referentially unstable. "
                          "Files containing the full 40-hex SHA are binding or chain-"
                          "record files and are updated or regenerated at re-freeze "
                          "(including this generator, whose OLD_CANDIDATE constant is "
                          "patched to C2); the current chain has no short-prefix-only "
                          "files. Historical short-prefix mentions remain historical "
                          "evidence and are not represented as a new-chain binding"),
        },
        "new_candidate_construction_policy": (
            "No history cherry-pick from the 129 unpushed commits. C2 is an OVERLAY "
            "commit: start from the FULL origin/main tree and replace/add exactly the "
            "698 candidate data paths with their recorded old-candidate blobs; every "
            "other origin/main path stays byte-identical; parent = the integration "
            "branch base so C2 stays reachable and pushable. The construction is "
            "performed and checked by build_candidate_overlay_tree() and "
            "verify_candidate_tree() in the tracked generator, NOT by manual steps. "
            "The 17 tooling paths and the 4 infrastructure paths land as normal "
            "commits on top; the code-side binding files are patched to C2 first "
            "(re-freeze order step 2)."
        ),
        "new_candidate_gates": [
            "gate1 executable verify_candidate_tree: C2 vs base deletions == 0",
            "gate2 all 698 candidate data paths carry the exact old-candidate blob OIDs and sizes",
            "gate3 C2 vs base changed path set == 695 paths (698 minus 3 same-blob)",
            "gate4 every base path outside the closure is byte-identical in C2",
            "negative control: the narrow tree (698 paths only, no base) MUST be rejected (gate1 + gate3)",
        ],
        "re_freeze_order": [
            "1. construct C2 via build_candidate_overlay_tree(entries, base) and REQUIRE verify_candidate_tree(...) == [] before committing; the narrow-tree negative control must fail",
            "2. patch the code-side binding files to reference C2: classic_acceptance_common.py FROZEN_CANDIDATE_COMMIT, classic_acceptance_fixtures.py COMMIT, generate_acceptance_manifests.py COMMIT_DEFAULT, test_generate_acceptance_manifests.py COMMIT, AND scripts/generate_acceptance_integration_closure.py OLD_CANDIDATE",
            "3. migrate the integration infrastructure layer (generator + tests + regenerated closure artifacts) so the clean branch self-verifies",
            "4. regenerate both identity manifests from C2 with the patched generator (its blob CHANGES; record the new generator blob OID in the regenerated freeze receipt); diff against frozen manifests - only candidate-commit- and generator-derived fields may differ",
            "5. update acceptance-freeze.json + freeze-anchor-record.json + design doc anchors to the new chain (C2, new generator blob, new payload commit, new tag OID)",
            "6. commit tooling + infrastructure; create tooling payload commit; finalize receipt in the freeze commit; tag new freeze tag",
            "6b. on the clean branch regenerate the closure artifacts so the tooling OID table and infra blobs record THIS chain's committed blobs: python scripts/generate_acceptance_integration_closure.py generate --no-legacy --candidate-commit <C2> --base-commit <base> --tooling-pin-commit <phase-A tooling commit>; the recorded pin is the phase-A commit and NEVER has to equal HEAD (a phase-B artifact-only commit keeps the check green), then commit the artifacts as a separate commit",
            "7. on the clean branch/CI run: python scripts/generate_acceptance_integration_closure.py --check --candidate-commit <C2> --base-commit <base> --no-legacy --tooling-pin-commit <phase-A tooling commit full 40-hex SHA>; the full phase-A pin SHA is an external frozen input carried by the CI command and the superseding receipt; then generate_acceptance_manifests.py --check against the new tag (Windows + Ubuntu)",
            "8. run the four-file bounded regression on Windows and the three POSIX tests on Ubuntu",
            "9. publish the superseding Review E receipt (it must record the full phase-A tooling pin SHA), then push and run official CI",
        ],
        "review_e_supersession_policy": (
            "Review E receipt db54345 pins five code blobs at 430191e. Mechanical "
            "scan shows exactly four code-side files carry the full candidate SHA "
            "(classic_acceptance_common.py, classic_acceptance_fixtures.py, "
            "generate_acceptance_manifests.py, test_generate_acceptance_manifests.py); "
            "the closure generator is a fifth code-side constant patched at the same "
            "step. Their blobs CHANGE at re-freeze. "
            "The new chain has no short-prefix-only binding; the old sampling-test "
            "prefix is historical evidence and is not carried as a new-chain "
            "binding. classic_acceptance_sampling.py, classic_acceptance_review.py "
            "and the remaining test files carry no SHA literal, so those pinned "
            "blobs stay identical. The superseding receipt must list old vs new "
            "blob for every touched file and re-run evidence: Windows focused "
            "cleanup tests + full four-file regression, and the three POSIX tests "
            "on ubuntu-latest. The old receipt remains valid as historical evidence "
            "for the old chain; the new receipt supersedes it for the new chain. "
            "No silent SHA reuse."
        ),
    }


def verify(cl, candidate_commit=OLD_CANDIDATE, base_commit=MERGE_BASE,
           use_legacy=True, tooling_pin=None):
    errors = []
    if not SHA40_RE.match(TOOLING_PIN_COMMIT):
        errors.append("tooling pin commit must be full 40-hex")
    elif use_legacy and rev_exists(TOOLING_PIN_COMMIT) \
            and resolve_commit(TOOLING_PIN_COMMIT) != TOOLING_PIN_COMMIT:
        errors.append("tooling pin commit rev-parse round-trip failed")
    if not SHA40_RE.match(base_commit):
        errors.append("base commit must be full 40-hex")
    if not SHA40_RE.match(candidate_commit):
        errors.append("candidate commit must be full 40-hex")
    base_tree = ls_tree(base_commit)
    if base_tree is None:
        errors.append(f"base commit {base_commit[:12]} not in object store")
        return errors
    flags_ref = "origin/main" if use_legacy else base_commit
    flags_tree = ls_tree(flags_ref)
    src = cl.get("source", {})
    recorded_pin = src.get("tooling_blob_pin_commit")
    if use_legacy:
        tooling_ref = TOOLING_PIN_COMMIT
        if recorded_pin != TOOLING_PIN_COMMIT:
            errors.append("source.tooling_blob_pin_commit mismatch vs pin constant")
        if src.get("candidate_data_ref") != OLD_CANDIDATE:
            errors.append("source.candidate_data_ref mismatch")
        if src.get("flags_base_ref") != "origin/main":
            errors.append("source.flags_base_ref mismatch")
    else:
        # P0-2: the pin names the phase-A tooling commit. It must exist and
        # round-trip; its tree, the recorded OIDs and the CURRENT HEAD tree
        # must all carry identical tooling blobs. The pin never has to equal
        # the current HEAD commit (an artifact-only phase-B commit changes
        # HEAD but not the tooling blobs).
        tooling_ref = tooling_pin if tooling_pin else recorded_pin
        if not isinstance(tooling_ref, str) or not SHA40_RE.match(tooling_ref):
            errors.append("tooling pin commit must be full 40-hex")
            tooling_ref = None
        elif not rev_exists(tooling_ref):
            errors.append(f"tooling pin commit missing: {tooling_ref}")
            tooling_ref = None
        elif resolve_commit(tooling_ref) != tooling_ref:
            errors.append("tooling pin commit rev-parse round-trip failed")
        if src.get("candidate_data_ref") != candidate_commit:
            errors.append("source.candidate_data_ref mismatch vs candidate commit")
        if src.get("flags_base_ref") != base_commit:
            errors.append("source.flags_base_ref mismatch vs base commit")
        if tooling_pin is not None and recorded_pin != tooling_pin:
            errors.append("source.tooling_blob_pin_commit mismatch vs requested tooling pin")
    pin_tree = ls_tree(tooling_ref) if tooling_ref else None
    if pin_tree is None:
        if tooling_ref is not None:
            errors.append(f"tooling reference {tooling_ref} not in object store")
        pin_tree = {}
    candidate_tree = ls_tree(candidate_commit)
    if candidate_tree is None:
        if use_legacy:
            errors.append(f"legacy candidate {candidate_commit[:12]} not in object store")
        else:
            errors.append(f"candidate commit missing: {candidate_commit} "
                          f"(real C2 verification cannot be skipped)")
    refs = collect_refs()
    counter = Counter(refs)
    unique = sorted(counter)
    kb = [p for p in unique if p.startswith("knowledge_base/")]
    non_kb = sorted(p for p in unique if not p.startswith("knowledge_base/"))
    if len(refs) != EXPECTED["refs"]:
        errors.append(f"refs drift: {len(refs)} != {EXPECTED['refs']}")
    if len(unique) != EXPECTED["unique"]:
        errors.append(f"unique paths drift: {len(unique)} != {EXPECTED['unique']}")
    if len(kb) != EXPECTED["kb_unique"]:
        errors.append(f"kb paths drift: {len(kb)} != {EXPECTED['kb_unique']}")
    if non_kb != EXPECTED_NON_KB_UNIQUE:
        errors.append(f"non-kb unique paths drift: {non_kb} != {EXPECTED_NON_KB_UNIQUE}")
    entries = cl.get("candidate_data_paths", [])
    by_path = {}
    for e in entries:
        p = e.get("path")
        if p in by_path:
            errors.append(f"duplicate candidate path: {p}")
            continue
        by_path[p] = e
    for p in kb:
        if p not in by_path:
            errors.append(f"missing candidate path: {p}")
    for p, e in by_path.items():
        oid = e.get("data_blob_oid")
        if candidate_tree is not None:
            if p not in candidate_tree:
                errors.append(f"path absent from candidate tree: {p}")
                continue
            if oid != candidate_tree[p][0] or e.get("size") != candidate_tree[p][1]:
                errors.append(f"blob drift: {p}")
        elif not object_exists(oid):
            errors.append(f"candidate blob missing from object store: {p}")
        if e.get("group") != group_of(p):
            errors.append(f"group mislabel: {p}")
        if e.get("refs") != counter.get(p, 0):
            errors.append(f"refs drift: {p}")
        if e.get("present_on_flags_base") != (p in flags_tree):
            errors.append(f"flags-base presence drift: {p}")
        if p in flags_tree and e.get("same_blob_on_flags_base") != (flags_tree[p][0] == oid):
            errors.append(f"flags-base blob relation drift: {p}")
    group_counts = Counter(group_of(e["path"]) for e in entries)
    for g, n in EXPECTED["groups"].items():
        if group_counts.get(g, 0) != n:
            errors.append(f"group drift: {g} {group_counts.get(g, 0)} != {n}")
    if group_counts.get("other", 0):
        errors.append(f"group conservation: {group_counts['other']} entries outside expected groups")
    total = sum(e.get("size", 0) for e in entries)
    if total != EXPECTED["kb_bytes"]:
        errors.append(f"candidate bytes drift: {total} != {EXPECTED['kb_bytes']}")
    over_paths = {o[0] for o in OVERSIZED}
    if over_paths & set(by_path):
        errors.append(f"exclusion drift: oversized inside candidate set: {sorted(over_paths & set(by_path))}")
    recorded = sorted((o.get("path"), o.get("blob_oid"), o.get("size"))
                      for o in cl.get("excluded_paths", {}).get("oversized", []))
    expected_over = sorted((p, oid, size) for p, oid, size, _ in OVERSIZED)
    if recorded != expected_over:
        errors.append("exclusion drift: oversized record mismatch")
    remainder = kb_remainder_paths(set(by_path))
    rec_rem = cl.get("excluded_paths", {}).get("knowledge_base_remainder", {})
    if rec_rem.get("count") != len(remainder):
        errors.append(f"exclusion drift: kb remainder {rec_rem.get('count')} != {len(remainder)}")
    elif rec_rem.get("paths") != remainder:
        errors.append("exclusion drift: kb remainder path list mismatch")
    tooling = cl.get("tooling_paths", [])
    if len(tooling) != EXPECTED["tooling_count"]:
        errors.append(f"tooling count drift: {len(tooling)} != {EXPECTED['tooling_count']}")
    head_tree_tooling = ls_tree("HEAD") if not use_legacy else None
    tbytes = 0
    for e in tooling:
        p = e.get("path")
        if p not in pin_tree:
            errors.append(f"tooling path absent from pin tree: {p}")
            continue
        # Recorded OID/size must match the pin tree (legacy: the reviewed pin
        # commit; no-legacy: the phase-A tooling commit) AND, in no-legacy
        # mode, the CURRENT HEAD tree - pin/recorded/HEAD three-way identity
        # without ever requiring pin == HEAD commit.
        if e.get("tooling_blob_oid") != pin_tree[p][0]:
            errors.append(f"tooling blob drift vs pin: {p}")
        elif e.get("size") != pin_tree[p][1]:
            errors.append(f"tooling size drift vs pin: {p}")
        if head_tree_tooling is not None:
            if p not in head_tree_tooling:
                errors.append(f"tooling path absent from HEAD: {p}")
            elif e.get("tooling_blob_oid") != head_tree_tooling[p][0]:
                errors.append(f"tooling blob drift vs HEAD: {p}")
        tbytes += e.get("size", 0)
    ref_tbytes = sum(pin_tree.get(e.get("path"), (None, 0))[1] for e in tooling)
    if use_legacy and tbytes != EXPECTED["tooling_bytes"]:
        errors.append(f"tooling bytes drift: {tbytes} != {EXPECTED['tooling_bytes']}")
    elif not use_legacy and tbytes != ref_tbytes:
        errors.append(f"tooling bytes drift vs HEAD: recorded {tbytes} != {ref_tbytes}")
    data_overlap = sum(1 for e in entries if e.get("present_on_flags_base"))
    data_same = sum(1 for e in entries if e.get("same_blob_on_flags_base"))
    data_changed = sum(1 for e in entries if not e.get("same_blob_on_flags_base"))
    if (data_overlap, data_same, data_changed) != (
            EXPECTED["data_overlap_with_main"], EXPECTED["data_same_blob_on_main"],
            EXPECTED["data_changed_vs_main"]):
        errors.append("flags-base relation drift: overlap/same/changed mismatch")
    tool_overlap = sum(1 for e in tooling if e.get("path") in flags_tree)
    if tool_overlap != EXPECTED["tooling_overlap_with_main"]:
        errors.append(f"tooling overlap drift: {tool_overlap} != {EXPECTED['tooling_overlap_with_main']}")
    binding, short_only = scan_touch_list()
    tl = cl.get("code_freeze_touch_list", {})
    if sorted(e["path"] for e in tl.get("binding_full_sha", [])) != [e["path"] for e in binding]:
        errors.append("touch-list drift: binding file set mismatch")
    elif tl.get("binding_full_sha") != binding:
        errors.append("touch-list drift: binding occurrence counts mismatch")
    if tl.get("short_sha_only") != short_only:
        errors.append("touch-list drift: short-SHA-only file set mismatch")
    if tl.get("audit_output_exclusion_glob") != AUDIT_OUTPUT_EXCLUSION_GLOB:
        errors.append("touch-list drift: audit output exclusion policy mismatch")
    if len(binding) != EXPECTED["touch_binding_files"]:
        errors.append(f"touch-list drift: binding files {len(binding)} != {EXPECTED['touch_binding_files']}")
    if len(short_only) != EXPECTED["touch_short_only_files"]:
        errors.append(f"touch-list drift: short-only files {len(short_only)} != {EXPECTED['touch_short_only_files']}")
    infra = cl.get("integration_infrastructure_layer", {})
    src_paths = sorted(e["path"] for e in infra.get("source_files", []))
    if src_paths != sorted(INFRA_SOURCE_PATHS):
        errors.append(f"infrastructure layer source drift: {src_paths}")
    # P0-2: recorded infra source blobs/sizes are verified against the actual
    # commit tree, not just the path set (these blobs land in the same commit
    # as the artifacts, so artifacts are regenerated after the code commit).
    head_tree = ls_tree("HEAD") or {}
    for e in infra.get("source_files", []):
        p = e.get("path")
        if p not in head_tree:
            errors.append(f"infrastructure source absent from HEAD: {p}")
            continue
        if e.get("blob_oid_at_infrastructure_commit") != head_tree[p][0]:
            errors.append(f"infrastructure source blob stale vs HEAD: {p}")
        elif e.get("size") != head_tree[p][1]:
            errors.append(f"infrastructure source size drift: {p}")
    gen_paths = sorted(e["path"] for e in infra.get("generated_artifacts", []))
    if gen_paths != sorted(GENERATED_OUTPUTS):
        errors.append(f"infrastructure layer artifacts drift: {gen_paths}")
    mt = cl.get("migration_total", {})
    if mt.get("total_paths") != EXPECTED["tooling_count"] + EXPECTED["kb_unique"] + 4:
        errors.append("migration_total drift")
    try:
        gate_entries = []
        oid_errors = []
        for e in entries:
            oid = e.get("data_blob_oid")
            if candidate_tree is not None:
                if e["path"] not in candidate_tree:
                    oid_errors.append(f"path absent from candidate tree: {e['path']}")
                    continue
                if candidate_tree[e["path"]][0] != oid:
                    oid_errors.append(f"gate2 candidate-blob-match: blob drift at {e['path']}")
            elif not object_exists(oid):
                oid_errors.append(f"gate2 candidate-blob-match: blob {oid[:12]} missing "
                                  f"from object store ({e['path']})")
                continue
            gate_entries.append({"path": e["path"], "oid": oid, "size": e["size"]})
        errors.extend(oid_errors)
        expected_oids = {e["path"]: e["oid"] for e in gate_entries}
        overlay_oid = build_candidate_overlay_tree(gate_entries, base_commit)
        errors.extend(verify_candidate_tree(gate_entries, expected_oids, base_tree,
                                            base_commit, overlay_oid))
        narrow_oid = build_narrow_candidate_tree(gate_entries)
        narrow_errors = verify_candidate_tree(gate_entries, expected_oids, base_tree,
                                              base_commit, narrow_oid)
        if not narrow_errors:
            errors.append("negative control failed: narrow (698-only) tree was accepted")
        elif not any("gate1" in e for e in narrow_errors):
            errors.append("negative control weak: narrow tree not caught by gate1")
        if not use_legacy:
            # P0-1 fail-closed: in no-legacy (post-migration) mode the real C2
            # candidate commit MUST exist and MUST itself pass every gate; a
            # well-formed but absent 40-hex SHA is an error, never a skip.
            # (Legacy mode has no C2 yet: the ideal overlay tree above is the
            # construction blueprint, and is already fully gated.)
            if not rev_exists(candidate_commit):
                errors.append(f"candidate commit missing: {candidate_commit} "
                              f"(real C2 verification cannot be skipped)")
            else:
                real_errors = verify_candidate_tree(gate_entries, expected_oids, base_tree,
                                                    base_commit, candidate_commit)
                errors.extend(f"real C2: {e}" for e in real_errors)
    except RuntimeError as exc:
        errors.append(f"overlay gate construction failed: {exc}")
    return errors


def _canonical(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def render_md(cl):
    data = cl["candidate_data_paths"]
    tooling = cl["tooling_paths"]
    over = cl["excluded_paths"]["oversized"]
    remainder = cl["excluded_paths"]["knowledge_base_remainder"]
    groups = Counter(e["group"] for e in data)
    data_bytes = sum(e["size"] for e in data)
    tooling_bytes = sum(e["size"] for e in tooling)
    same_main = sum(1 for e in data if e["same_blob_on_flags_base"])
    present_main = sum(1 for e in data if e["present_on_flags_base"])
    lines = []
    lines.append("# Acceptance 集成闭包 v3.1（可执行门禁 + 基础设施迁移层）\n")
    lines.append("> 日期：2026-08-29 ｜ 由 `scripts/generate_acceptance_integration_closure.py` 生成（勿手改）")
    lines.append("> 复跑：`generate` 重算重写；`--check` 零写入核验；干净分支/CI 用 "
                 "`--check --candidate-commit <C2> --base-commit <base> --no-legacy "
                 "--tooling-pin-commit <phase-A 完整 SHA>`\n")
    lines.append("## 0. 本轮修订\n")
    lines.append("- **P0-1（门禁可执行化）**：四条门禁不再是字符串。`build_candidate_overlay_tree()` "
                 "在临时 index（GIT_INDEX_FILE）中以 `read-tree <base>` + 698 次 `update-index --cacheinfo` "
                 "真实构造 C2 覆盖树；`verify_candidate_tree()` 对树执行四条断言（零删除 / blob 全匹配 / "
                 "diff 恰 695 / 闭包外逐字节不变）。负对照 `build_narrow_candidate_tree()` 构造“仅 698 路径”"
                 "的错误树，验证器必须拒绝（gate1 + gate3），并有专项测试。\n")
    lines.append("- **P0-2（基础设施随链迁移）**：生成器、测试与两个产物组成 integration-infrastructure 层"
                 "（4 路径），计入 `migration_total`，与 17 工具、698 数据同属迁移链；生成器不退役——"
                 "`--candidate-commit/--base-commit/--no-legacy` 使其在干净分支与 CI 上无需旧候选对象即可复跑全部门禁。\n")
    lines.append("- **P1（完整钉值）**：工具钉值提交为完整 40 位 `" + TOOLING_PIN_COMMIT + "`，"
                 "`verify()` 以 `rev-parse <full>^{commit}` 往返校验；base/candidate 参数同样要求完整 40 位。\n")
    lines.append("- **P0（pin 外部信任根）**：no-legacy 模式下 `--tooling-pin-commit` 为强制参数——`generate` 与 `--check` "
                 "缺失即用法错误（退出码 2）；验证器绝不从磁盘 JSON 或运行时 HEAD 自举 pin，`build_closure` 如实记录其"
                 "实际使用的 pin，`verify()` 交叉核对记录 pin 与请求 pin——把记录 pin 换成内容相同的其他提交无法自证；"
                 "重冻结步骤 7、CI 命令与 superseding receipt 显式携带完整 phase-A SHA。\n")
    lines.append("## 1. 闭包总量\n")
    lines.append("| 层 | 路径数 | 字节 |")
    lines.append("|---|---:|---:|")
    lines.append(f"| 工具/测试/冻结文档（钉值 blob） | {len(tooling)} | {tooling_bytes} |")
    lines.append(f"| 候选数据（覆盖进 C2） | {len(data)} | {data_bytes} |")
    lines.append("| 闭包基础设施（生成器/测试/产物，随链迁移） | 4 | — |")
    lines.append(f"| **迁移总计** | **{cl['migration_total']['total_paths']}** | **{tooling_bytes + data_bytes}** |")
    lines.append("")
    lines.append(f"- 分组：{', '.join(f'{k}={v}' for k, v in sorted(groups.items()))}。")
    flags_label = cl["source"].get("flags_base_ref", "origin/main")
    lines.append(f"- 与 `{flags_label}`：数据 overlap={present_main}（同 blob {same_main}）、变更 695；工具 overlap=1。\n")
    lines.append("## 2. 排除集\n")
    lines.append("- 3 个超大 blob（不在读取闭包内）：" +
                 "、".join(f"`{o['path'].split('/')[-1]}`（{o['size']}）" for o in over))
    lines.append(f"- 蒸馏轨道 {len(cl['excluded_paths']['distillation_track_tooling'])} 路径、"
                 f"Phase 8 证据 {len(cl['excluded_paths']['phase8_evidence'])} 路径（单独任务）")
    lines.append(f"- `knowledge_base` 其余变更 {remainder['count']} 个\n")
    lines.append("## 3. 构造政策与可执行门禁\n")
    lines.append(cl["new_candidate_construction_policy"])
    lines.append("")
    for g in cl["new_candidate_gates"]:
        lines.append(f"- [gate] {g}")
    lines.append("")
    lines.append("## 4. 复跑方式\n")
    lines.append("```")
    lines.append("python scripts/generate_acceptance_integration_closure.py generate")
    lines.append("python scripts/generate_acceptance_integration_closure.py --check")
    lines.append("# step 6b on the clean branch: regenerate artifacts for the NEW chain")
    lines.append("python scripts/generate_acceptance_integration_closure.py generate --no-legacy --candidate-commit <C2> --base-commit <base> --tooling-pin-commit <phaseA>")
    lines.append("# post-migration verification on the clean branch / CI (no old-candidate object needed):")
    lines.append("python scripts/generate_acceptance_integration_closure.py --check --candidate-commit <C2> --base-commit <base> --no-legacy --tooling-pin-commit <phaseA>")
    lines.append("python -m pytest tests/test_generate_acceptance_integration_closure.py -q --timeout=120")
    lines.append("```")
    lines.append("`--check` 每次运行都真实构造覆盖树与窄树并执行门禁断言；另覆盖引用计数、698 路径逐条 blob、"
                 "分组守恒、排除集、工具 blob、origin/main 关系、触点清单（11 绑定 + 1 短前缀 + 2 产物豁免）、"
                 "基础设施层完整性与钉值完整 SHA 往返；任一漂移非零退出。\n")
    lines.append("## 5. 重冻结顺序（摘要）\n")
    for step in cl["re_freeze_order"]:
        lines.append(step)
    lines.append("")
    lines.append("Review E supersession 政策见 JSON：5 个代码侧常量文件 blob 必变（含本生成器的 OLD_CANDIDATE），"
                 "新链 short-prefix-only 集合为空，其余钉值 blob 不变；需 Windows 四文件回归 + Ubuntu 三个 "
                 "POSIX 测试的复跑证据与 superseding receipt。")
    return "\n".join(lines) + "\n"


def main(argv):
    candidate = OLD_CANDIDATE
    base = MERGE_BASE
    tooling_pin = None
    use_legacy = True
    mode = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("generate", "--check"):
            mode = a
        elif a in ("--candidate-commit", "--base-commit", "--tooling-pin-commit"):
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                print(f"{a} requires a value", file=sys.stderr)
                return 2
            if a == "--candidate-commit":
                candidate = argv[i + 1]
            elif a == "--base-commit":
                base = argv[i + 1]
            else:
                tooling_pin = argv[i + 1]
            i += 1
        elif a == "--no-legacy":
            use_legacy = False
        else:
            print(f"unknown argument: {a}", file=sys.stderr)
            return 2
        i += 1
    if mode is None:
        print("usage: generate | --check [--candidate-commit C] [--base-commit B] "
              "[--tooling-pin-commit P] [--no-legacy]", file=sys.stderr)
        return 2
    if not SHA40_RE.match(candidate) or not SHA40_RE.match(base):
        print("--candidate-commit/--base-commit must be full 40-hex SHAs", file=sys.stderr)
        return 2
    if tooling_pin is not None and not SHA40_RE.match(tooling_pin):
        print("--tooling-pin-commit must be a full 40-hex SHA", file=sys.stderr)
        return 2
    if not use_legacy and tooling_pin is None:
        print("--no-legacy requires --tooling-pin-commit <phase-A full SHA>; the pin "
              "is an external frozen input and is never read from the disk JSON",
              file=sys.stderr)
        return 2
    (ROOT / ".tmp").mkdir(exist_ok=True)

    # P0-1: in BOTH --check modes the authoritative closure object is
    # RECOMPUTED from Git; the artifacts on disk are then compared against
    # the recomputation. The disk JSON is never used as the expected state.
    if mode == "generate":
        try:
            if use_legacy:
                cl = build_closure()
                errors = verify(cl, candidate_commit=candidate, base_commit=base,
                                use_legacy=True, tooling_pin=None)
            else:
                pin = tooling_pin
                cl = build_closure(candidate_commit=candidate, base_commit=base,
                                   use_legacy=False, tooling_pin=pin)
                errors = verify(cl, candidate_commit=candidate, base_commit=base,
                                use_legacy=False, tooling_pin=pin)
        except RuntimeError as exc:
            print(f"GENERATE FAILED: {exc}", file=sys.stderr)
            return 1
        if errors:
            for e in errors:
                print(f"VERIFY FAIL: {e}", file=sys.stderr)
            print("refusing to write inconsistent closure artifacts", file=sys.stderr)
            return 1
        JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_bytes(_canonical(cl).encode("utf-8"))
        MD_PATH.write_text(render_md(cl), encoding="utf-8", newline="\n")
        print(f"wrote {JSON_PATH}")
        print(f"wrote {MD_PATH}")
        return 0

    disk_json = None
    if JSON_PATH.exists():
        try:
            disk_json = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"unreadable closure JSON: {exc}", file=sys.stderr)
            return 1
    try:
        if use_legacy:
            cl = build_closure()
            pin = None
        else:
            pin = tooling_pin
            cl = build_closure(candidate_commit=candidate, base_commit=base,
                               use_legacy=False, tooling_pin=pin)
        errors = verify(cl, candidate_commit=candidate, base_commit=base,
                        use_legacy=use_legacy, tooling_pin=pin)
    except RuntimeError as exc:
        print(f"CHECK FAILED: {exc}", file=sys.stderr)
        return 1
    disk_errors = []
    if not JSON_PATH.exists():
        disk_errors.append(f"missing artifact: {JSON_PATH}")
    elif disk_json is None or _canonical(disk_json) != _canonical(cl):
        disk_errors.append("closure JSON drifted from recomputed state")
    if not MD_PATH.exists():
        disk_errors.append(f"missing artifact: {MD_PATH}")
    elif MD_PATH.read_text(encoding="utf-8").replace("\r\n", "\n") != render_md(cl).replace("\r\n", "\n"):
        disk_errors.append("closure MD drifted from recomputed state")
    for e in errors + disk_errors:
        print(f"DRIFT: {e}", file=sys.stderr)
    return 0 if not errors and not disk_errors else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
