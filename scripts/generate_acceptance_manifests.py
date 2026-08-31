"""Generate the candidate-acceptance identity + chapter manifests from a frozen
candidate commit. Committed so the manifests are independently reproducible.

Usage:
    python scripts/generate_acceptance_manifests.py [candidate_commit]
    python scripts/generate_acceptance_manifests.py --check \
        --freeze-ref CLASSIC_ACCEPTANCE_FREEZE_V2 \
        --expected-freeze-tag-oid <40-hex-tag-object-oid>

Modes:
  (default)  Write both manifests to docs/superpowers/specs/ with LF line
             endings (newline="\\n"); print the LF-canonical SHA-256 of each.
  --check    Generate in memory only (no writes); verify the three-object
             freeze. BOTH --freeze-ref <annotated-tag> and
             --expected-freeze-tag-oid <40-hex> are MANDATORY: the tag NAME
             alone is a mutable reference, so the verifier pins the expected
             tag object OID (supplied from the independent approval record /
             protected remote) and compares it with the resolved ref. Verified
             layers, all fail-closed:
               0a) the ref exists and is an annotated tag object
               0b) resolved tag object OID == expected OID (re-pointing the
                   tag name to a new self-consistent freeze is caught here)
               0c) receipt read ONLY from the freeze commit the tag points at
                   (never from HEAD, never from the payload commit)
               0d) receipt.freeze_tag / candidate_commit / payload / generator
                   record are present and well-formed
               0e) tooling_payload_commit is an ancestor of the freeze commit
               0f) the freeze commit differs from the payload ONLY in the
                   receipt path (git diff --name-only)
               1)  committed manifests at the payload commit == frozen SHAs
               1b) the generator exists at the payload commit and its blob
                   OID + LF SHA == the frozen generator record
               2)  regenerated manifests (from candidate data) == frozen SHAs
               3)  the running script's blob/sha256_lf == frozen generator
             Exit 0 only if every layer matches; any drift exits non-zero.

Three-object model (v2.0 freeze):
  candidate_commit          = data-only commit read via git show
  tooling_payload_commit    = commit holding generator + manifests + design
                              (its own receipt is a PENDING placeholder; the
                              verifier NEVER reads the receipt from payload/HEAD)
  freeze_commit             = commit the annotated freeze tag points at, holding
                              the finalized receipt; differs from the payload
                              only in the receipt. Its identity is anchored
                              externally by the pinned tag object OID.

All Git reads are fail-closed: check=True everywhere, commit must resolve to a
full 40-char commit, every path must be a blob, fixed counts must match exactly,
and integrity failures raise (never a silent empty record).
"""
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIT = ["git", "-C", str(ROOT)]
BOOK = "knowledge_base/classic_texts/sanmingtonghui"
SNAP_SHA = "b4e9be580dbecd3e233d3adbe163299f06c6ca5174309dc83e8f14433796aaa2"
SNAP = f"{BOOK}/formal/source_snapshots/{SNAP_SHA}"
ALGO_VERSION = "1.4"
COMMIT_DEFAULT = "80bc630396f31c6b6c122e49ef97f6d912e6f636"
FREEZE_TAG = "CLASSIC_ACCEPTANCE_FREEZE_V2"
GENERATOR_PATH = "scripts/generate_acceptance_manifests.py"
EXPECTED_COUNTS = {
    "output_files": 8,
    "phase8_drift_files": 3,
    "snapshot_identity": 3,
    "authoritative_raw_texts_extracted_383": 383,
    "derived_root_raw_303": 303,
    "chapters": 383,
    "rules": 8043,
    "mcq": 6103,
    "legacy_chapters": 80,
    "legacy_unique_titles": 80,
    "title_map": 383,
}
OUT_NAMES = [
    "2026-08-20-classic-texts-candidate-identity-manifest.json",
    "2026-08-20-classic-texts-chapter-identity-manifest.json",
]
FREEZE_RECEIPT = "docs/superpowers/specs/2026-08-20-classic-texts-acceptance-freeze.json"


def _git(args, *, check=True, input_bytes=None):
    r = subprocess.run(GIT + args, capture_output=True, input=input_bytes)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.decode('utf-8', 'replace')[:300]}")
    return r


def resolve_commit(commit):
    r = _git(["rev-parse", "--verify", f"{commit}^{{commit}}"])
    full = r.stdout.decode("utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", full):
        raise RuntimeError(f"commit {commit!r} does not resolve to a 40-char commit")
    return full


def git_show(rel, commit):
    r = _git(["show", f"{commit}:{rel}"])
    return r.stdout  # LF bytes of the blob at candidate commit


def assert_blob(rel, commit):
    r = _git(["cat-file", "-t", f"{commit}:{rel}"])
    if r.stdout.decode("utf-8").strip() != "blob":
        raise RuntimeError(f"path is not a blob: {rel}")


def blob_oid(rel, commit):
    r = _git(["rev-parse", "--verify", f"{commit}:{rel}"])
    oid = r.stdout.decode("utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", oid):
        raise RuntimeError(f"path did not yield a 40-char blob oid: {rel}")
    return oid


def blob_info(rel, commit):
    assert_blob(rel, commit)
    b = git_show(rel, commit)
    return {
        "path": rel,
        "candidate_commit": commit,
        "blob_oid": blob_oid(rel, commit),
        "sha256_lf": hashlib.sha256(b).hexdigest(),
        "size_bytes": len(b),
    }


def script_sha256():
    data = Path(__file__).resolve().read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def script_blob_oid():
    lf = Path(__file__).resolve().read_bytes().replace(b"\r\n", b"\n")
    r = _git(["hash-object", "--stdin"], input_bytes=lf)
    return r.stdout.decode("utf-8").strip()


def require(cond, msg):
    if not cond:
        raise RuntimeError(msg)


def build_manifests(commit):
    commit = resolve_commit(commit)
    outputs = [
        f"{BOOK}/all_rules.json",
        f"{BOOK}/all_mcq.jsonl",
        f"{BOOK.replace('sanmingtonghui', 'qiongtongbaojian')}/all_rules.json",
        f"{BOOK.replace('sanmingtonghui', 'qiongtongbaojian')}/all_mcq.jsonl",
        f"{BOOK.replace('sanmingtonghui', 'ditiansui')}/all_rules.json",
        f"{BOOK.replace('sanmingtonghui', 'ditiansui')}/all_mcq.jsonl",
        f"{BOOK.replace('sanmingtonghui', 'zipingzhenquan')}/all_rules.json",
        f"{BOOK.replace('sanmingtonghui', 'zipingzhenquan')}/all_mcq.jsonl",
    ]
    drift = [
        f"{BOOK.replace('sanmingtonghui', 'qiongtongbaojian')}/all_rules.json",
        f"{BOOK.replace('sanmingtonghui', 'qiongtongbaojian')}/quarantine_rules.jsonl",
        f"{BOOK}/all_rules.json",
    ]
    snap_ids = [
        f"{BOOK}/formal/active_source_snapshot.json",
        f"{SNAP}/source_manifest.json",
        f"{SNAP}/RESPONSE_ARCHIVE_POINTER.json",
    ]
    tree = _git(["ls-tree", "-r", "--name-only", commit, BOOK + "/"]).stdout.decode("utf-8").splitlines()
    root_raw = [t for t in tree if t.startswith(BOOK + "/raw_") and t.split("/")[-1].startswith("raw_") and t.endswith(".txt")]
    extracted = [t for t in tree if t.startswith(SNAP + "/extracted/") and t.endswith(".txt")]
    require(len(root_raw) == EXPECTED_COUNTS["derived_root_raw_303"], f"root_raw count {len(root_raw)} != {EXPECTED_COUNTS['derived_root_raw_303']}")
    require(len(extracted) == EXPECTED_COUNTS["authoritative_raw_texts_extracted_383"], f"extracted count {len(extracted)} != {EXPECTED_COUNTS['authoritative_raw_texts_extracted_383']}")

    gen = {"path": GENERATOR_PATH, "sha256_lf": script_sha256(), "blob_oid": script_blob_oid(), "algorithm_version": ALGO_VERSION, "candidate_commit": commit}
    identity = {
        "schema_version": "1.0",
        "candidate_commit": commit,
        "algorithm_version": ALGO_VERSION,
        "generator": gen,
        "generated_at": "2026-08-20",
        "identity_domain": "LF bytes at candidate commit (git show). Worktree CRLF SHAs are NOT identity.",
        "groups": {
            "output_files": [blob_info(p, commit) for p in outputs],
            "phase8_drift_files": [blob_info(p, commit) for p in drift],
            "snapshot_identity": [blob_info(p, commit) for p in snap_ids],
            "authoritative_raw_texts_extracted_383": [blob_info(p, commit) for p in sorted(extracted)],
        },
        "derived_root_raw_303": [blob_info(p, commit) for p in sorted(root_raw)],
        "counts": {
            "output_files": len(outputs),
            "phase8_drift_files": len(drift),
            "snapshot_identity": len(snap_ids),
            "authoritative_raw_texts_extracted_383": len(extracted),
            "derived_root_raw_303": len(root_raw),
        },
        "note": "Authoritative review source = formal snapshot extracted/raw_NNN.txt (383). Root-dir numeric raw_081..383.txt (303) are DERIVED copies. provenance.raw_text_shas has basename-only keys and cannot disambiguate the two path sets; it is NOT used to verify 686 paths.",
    }

    # ---- chapter identity ----
    rules = json.loads(git_show(f"{BOOK}/all_rules.json", commit).decode("utf-8"))
    mcq_lines = git_show(f"{BOOK}/all_mcq.jsonl", commit).decode("utf-8").splitlines()
    mcqs = [json.loads(l) for l in mcq_lines if l.strip()]
    man = json.loads(git_show(f"{SNAP}/source_manifest.json", commit).decode("utf-8"))
    title_to_index = {c["title"]: c["chapter_index"] for c in man["chapters"] if c.get("title")}
    require(len(title_to_index) == EXPECTED_COUNTS["title_map"], f"title_map {len(title_to_index)} != {EXPECTED_COUNTS['title_map']}")
    # NOTE: legacy rule titles are resolved via title_to_index (manifest titles).
    # The candidate commit has NO legacy-named raw files (raw_0NN_卷X_title.txt are
    # worktree-only materialization, not committed), so no raw-file cross-check exists.

    def ch_of_rule(r):
        sc = str(r.get("source_chapter", "")).strip()
        return int(sc) if sc.isdigit() else title_to_index.get(sc)

    rule_ch = {r["id"]: ch_of_rule(r) for r in rules}
    bad = [rid for rid, c in rule_ch.items() if c is None]
    require(not bad, f"unmapped rules: {bad[:10]}")
    rule_by_ch = defaultdict(list)
    for r in rules:
        rule_by_ch[rule_ch[r["id"]]].append(r["id"])
    mcq_by_ch = defaultdict(list)
    for m in mcqs:
        c = rule_ch.get(m.get("source_rule_id"))
        require(c is not None, f"unmapped mcq: {m.get('id')}")
        mcq_by_ch[c].append(m["id"])

    ext_idx = {}
    for e in extracted:
        m = re.search(r"raw_(\d{3})\.txt$", e)
        require(m, f"extracted path lacks raw_NNN.txt: {e}")
        ext_idx[int(m.group(1))] = e

    chapters = []
    for c in man["chapters"]:
        ci = c["chapter_index"]
        chapters.append({
            "chapter_index": ci,
            "title": c.get("title"),
            "is_legacy": ci <= 80,
            "raw_source_path": ext_idx.get(ci),
            "rule_ids": sorted(rule_by_ch.get(ci, [])),
            "mcq_ids": sorted(mcq_by_ch.get(ci, [])),
            "rule_count": len(rule_by_ch.get(ci, [])),
            "mcq_count": len(mcq_by_ch.get(ci, [])),
            "zero_rule": ci not in rule_by_ch,
            "zero_mcq": ci not in mcq_by_ch,
        })
    require(len(chapters) == EXPECTED_COUNTS["chapters"], f"chapters {len(chapters)} != {EXPECTED_COUNTS['chapters']}")
    require(ext_idx.keys() == set(range(1, 384)), "extracted raw indices must cover 1..383 exactly once")
    all_rules = [i for ch in chapters for i in ch["rule_ids"]]
    all_mcqs = [i for ch in chapters for i in ch["mcq_ids"]]
    require(len(all_rules) == len(set(all_rules)) == len(rules), f"rules exactly-once violated: {len(all_rules)}/{len(set(all_rules))}/{len(rules)}")
    require(len(all_mcqs) == len(set(all_mcqs)) == len(mcqs), f"mcq exactly-once violated: {len(all_mcqs)}/{len(set(all_mcqs))}/{len(mcqs)}")
    legacy_ch = [c for c in chapters if c["is_legacy"]]
    legacy_unique_titles = {c["title"] for c in legacy_ch if c.get("title")}
    require(len(legacy_ch) == EXPECTED_COUNTS["legacy_chapters"], f"legacy chapters {len(legacy_ch)} != {EXPECTED_COUNTS['legacy_chapters']}")
    require(len(legacy_unique_titles) == EXPECTED_COUNTS["legacy_unique_titles"], f"legacy titles {len(legacy_unique_titles)} != {EXPECTED_COUNTS['legacy_unique_titles']}")

    chman = {
        "schema_version": "1.0",
        "candidate_commit": commit,
        "algorithm_version": ALGO_VERSION,
        "generator": gen,
        "caliber": "source_chapter (NOT G7; G7 compares chapter_list vs progress.done)",
        "chapter_count": len(chapters),
        "legacy_chapter_count": len(legacy_ch),
        "legacy_unique_title_count": len(legacy_unique_titles),
        "source_chapter_title_to_index": {k: v for k, v in sorted(title_to_index.items())},
        "source_chapter_title_map_count": len(title_to_index),
        "exactly_once_assertion": {"rules": len(all_rules), "mcq": len(all_mcqs), "ok": True},
        "zero_rule_chapters": sorted(ci for ci in range(1, 384) if ci not in rule_by_ch),
        "zero_mcq_chapters": sorted(ci for ci in range(1, 384) if ci not in mcq_by_ch),
        "chapters": chapters,
    }
    return identity, chman


def _serialize(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _parse_args(argv):
    """Parse CLI flags. Never raises; validation happens in main()."""
    check = False
    freeze_ref = None
    expected_tag_oid = None
    positional = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--check":
            check = True
            i += 1
        elif a == "--freeze-ref":
            freeze_ref = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
        elif a == "--expected-freeze-tag-oid":
            expected_tag_oid = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
        else:
            positional.append(a)
            i += 1
    return check, freeze_ref, expected_tag_oid, positional


def verify_freeze(freeze_ref, expected_tag_oid, candidate_commit):
    """Fail-closed three-object freeze verification with a pinned tag anchor.

    Reads the finalized receipt ONLY from the fixed annotated freeze tag
    (never from HEAD, never from the payload commit) and requires the caller
    to pin the expected tag object OID: the tag name alone is a mutable
    reference. Raises RuntimeError on ANY drift."""
    require(isinstance(expected_tag_oid, str) and re.fullmatch(r"[0-9a-f]{40}", expected_tag_oid),
            "--expected-freeze-tag-oid must be a 40-hex tag object OID")
    tag = f"refs/tags/{freeze_ref}"
    # Layer 0a: the ref must exist and be an annotated tag object.
    typ = _git(["cat-file", "-t", tag]).stdout.decode("utf-8").strip()
    require(typ == "tag", f"{freeze_ref!r} is not an annotated tag (type={typ!r}); freeze tag must exist")
    # Layer 0b: the resolved tag object must be the pinned anchor. Re-pointing
    # the tag name to a new self-consistent freeze is rejected here.
    resolved_oid = _git(["rev-parse", "--verify", tag]).stdout.decode("utf-8").strip()
    require(resolved_oid == expected_tag_oid,
            f"tag object OID mismatch: refs/tags/{freeze_ref} resolved to {resolved_oid} but expected {expected_tag_oid}")
    freeze_commit = _git(["rev-parse", "--verify", f"{tag}^{{commit}}"]).stdout.decode("utf-8").strip()
    require(re.fullmatch(r"[0-9a-f]{40}", freeze_commit), f"{freeze_ref!r} does not resolve to a 40-char commit")

    # Layer 0c: the frozen expected values come ONLY from the freeze commit
    # (via the tag). A re-freeze at HEAD cannot influence this read.
    receipt = json.loads(git_show(FREEZE_RECEIPT, freeze_commit).decode("utf-8"))
    require(receipt.get("freeze_tag") == freeze_ref, f"receipt.freeze_tag {receipt.get('freeze_tag')!r} != {freeze_ref!r}")
    require(receipt.get("candidate_commit") == candidate_commit, "receipt.candidate_commit != requested candidate commit")
    payload = receipt.get("tooling_payload_commit")
    require(isinstance(payload, str) and re.fullmatch(r"[0-9a-f]{40}", payload), "receipt.tooling_payload_commit missing/not a 40-char commit")
    frozen_gen = receipt.get("generator") or {}
    gen_path = frozen_gen.get("path")
    require(gen_path == GENERATOR_PATH, f"receipt.generator.path {gen_path!r} != {GENERATOR_PATH!r}")
    req_gen_blob = frozen_gen.get("blob_oid")
    req_gen_sha = frozen_gen.get("sha256_lf")
    require(isinstance(req_gen_blob, str) and re.fullmatch(r"[0-9a-f]{40}", req_gen_blob), "receipt.generator.blob_oid missing/invalid")
    require(isinstance(req_gen_sha, str) and re.fullmatch(r"[0-9a-f]{64}", req_gen_sha), "receipt.generator.sha256_lf missing/invalid")
    frozen_shas = {}
    for name in OUT_NAMES:
        v = receipt.get("manifests", {}).get(name)
        require(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v), f"{name}: frozen SHA missing/invalid in receipt")
        frozen_shas[name] = v

    # Layer 0e: the payload must be an ancestor of the freeze commit.
    anc = _git(["merge-base", "--is-ancestor", payload, freeze_commit], check=False)
    require(anc.returncode == 0,
            f"tooling_payload_commit {payload[:16]} is not an ancestor of freeze commit {freeze_commit[:16]}")
    # Layer 0f: the freeze commit must differ from the payload ONLY in the receipt.
    diff = _git(["diff", "--name-only", "--no-renames", payload, freeze_commit]).stdout.decode("utf-8")
    changed = [l.strip() for l in diff.splitlines() if l.strip()]
    require(changed == [FREEZE_RECEIPT],
            f"freeze commit must change only the receipt ({FREEZE_RECEIPT}); changed: {changed}")

    # Layer 1: committed manifests at the payload commit must equal the frozen SHAs.
    for name in OUT_NAMES:
        try:
            b = git_show(f"docs/superpowers/specs/{name}", payload)
        except RuntimeError:
            raise RuntimeError(f"payload commit {payload[:16]} is missing manifest {name}")
        cs = hashlib.sha256(b).hexdigest()
        require(cs == frozen_shas[name],
                f"{name}: committed-at-payload {cs[:16]} != frozen {frozen_shas[name][:16]}")

    # Layer 1b: the frozen generator must exist at the payload commit itself.
    try:
        assert_blob(gen_path, payload)
        payload_gen_bytes = git_show(gen_path, payload)
    except RuntimeError:
        raise RuntimeError(f"payload commit {payload[:16]} is missing the generator blob at {gen_path}")
    payload_gen_oid = blob_oid(gen_path, payload)
    payload_gen_sha = hashlib.sha256(payload_gen_bytes).hexdigest()
    require(payload_gen_oid == req_gen_blob,
            f"generator at payload {payload_gen_oid[:16]} != frozen {req_gen_blob[:16]}")
    require(payload_gen_sha == req_gen_sha,
            f"generator sha256_lf at payload {payload_gen_sha[:16]} != frozen {req_gen_sha[:16]}")

    # Layer 2: regenerated manifests (from candidate data) must equal the frozen SHAs.
    identity, chman = build_manifests(candidate_commit)
    regen_shas = {name: hashlib.sha256(_serialize(obj)).hexdigest() for name, obj in zip(OUT_NAMES, (identity, chman))}

    print(f"freeze tag {freeze_ref} -> tag object {resolved_oid[:16]} -> {freeze_commit[:16]} (payload {payload[:16]}, candidate {candidate_commit[:16]})")
    for name in OUT_NAMES:
        require(regen_shas[name] == frozen_shas[name],
                f"{name}: regenerated {regen_shas[name][:16]} != frozen {frozen_shas[name][:16]}")
        print(f"{name}: regenerated==committed==frozen ({regen_shas[name][:16]})")

    # Layer 3: the running script must BE the frozen generator.
    cur_blob = script_blob_oid()
    cur_sha = script_sha256()
    require(cur_blob == req_gen_blob and cur_sha == req_gen_sha,
            f"running generator blob {cur_blob[:16]}/sha {cur_sha[:16]} != frozen {req_gen_blob[:16]}/{req_gen_sha[:16]}")
    print(f"generator blob==frozen ({cur_blob[:16]})")
    print("freeze check OK")


def main():
    check, freeze_ref, expected_tag_oid, positional = _parse_args(sys.argv[1:])
    if check:
        try:
            require(len(positional) <= 1, f"unexpected positional args: {positional}")
            require(freeze_ref, "--check requires --freeze-ref <annotated-tag>; defaulting to HEAD is forbidden")
            require(expected_tag_oid,
                    "--check requires --expected-freeze-tag-oid <40-hex>; the tag name alone is a mutable reference")
            commit = positional[0] if positional else COMMIT_DEFAULT
            verify_freeze(freeze_ref, expected_tag_oid, commit)
        except RuntimeError as e:
            print(f"freeze check FAILED: {e}")
            sys.exit(1)
        sys.exit(0)
    require(len(positional) <= 1, f"unexpected positional args: {positional}")
    commit = positional[0] if positional else COMMIT_DEFAULT
    identity, chman = build_manifests(commit)
    blobs = [_serialize(identity), _serialize(chman)]
    shas = [hashlib.sha256(b).hexdigest() for b in blobs]
    specs = ROOT / "docs/superpowers/specs"
    for name, b in zip(OUT_NAMES, blobs):
        (specs / name).write_bytes(b)  # already LF bytes; no CRLF translation
    print("identity:", OUT_NAMES[0], shas[0])
    print("chapter :", OUT_NAMES[1], shas[1])
    print("root_raw:", identity["counts"]["derived_root_raw_303"], "extracted:", identity["counts"]["authoritative_raw_texts_extracted_383"],
          "legacy_ch:", chman["legacy_chapter_count"], "legacy_titles:", chman["legacy_unique_title_count"], "title_map:", chman["source_chapter_title_map_count"])
    print("zero_rule:", chman["zero_rule_chapters"], "zero_mcq:", chman["zero_mcq_chapters"])


if __name__ == "__main__":
    main()
