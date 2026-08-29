"""Tests for scripts/generate_acceptance_manifests.py (fail-closed generator).

Covers: invalid commit, missing path, non-blob path, LF-only output bytes,
manifest invariants (counts, exactly-once, zero-output), and the three-object
freeze verification (--check --freeze-ref --expected-freeze-tag-oid): pinned
tag anchor from the LOCAL_ONLY anchor record, payload self-containment
(manifests + generator), ancestor and receipt-only constraints, and
layer-specific negative tests. The anchor record is an implementer-maintained
artifact, NOT an approval (test_anchor_record_honest_about_local_only pins
that status); consistency checks guard against accidental drift only.

Scratch commits/tags are built with git plumbing inside an isolated --shared
clone under .tmp/ (gitignored run-products dir, avoids pytest temp-dir
permission issues on locked-down sandboxes), so the main repository's object
database and refs are never written to. The scratch payload is always derived
from the FROZEN payload tree and the scratch receipt always binds THAT scratch
payload, so every negative test reaches its claimed verification layer
regardless of where HEAD has moved. build_manifests is cached once per module
to keep git traffic low.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import generate_acceptance_manifests as gam

ROOT = Path(__file__).resolve().parents[1]
GIT = ["git", "-C", str(ROOT)]
COMMIT = "51eb92b5e332fd425e241c940ec4c45c243db6ed"

SPECS = "docs/superpowers/specs"
RECEIPT_NAME = "2026-08-20-classic-texts-acceptance-freeze.json"
RECEIPT_PATH = f"{SPECS}/{RECEIPT_NAME}"
GENERATOR_PATH = "scripts/generate_acceptance_manifests.py"
DESIGN_PATH = f"{SPECS}/2026-08-20-classic-texts-candidate-acceptance-design.md"
# Freeze anchor record (LOCAL_ONLY, implementer-maintained — NOT an approval):
# the pinned tag object OID lives here instead of a hidden test constant. Tests
# below machine-check anchor record <-> real tag <-> design anchor consistency
# (guards against accidental drift only, not collusion). Update on re-freeze.
ANCHOR_RECORD_PATH = f"{SPECS}/2026-08-20-classic-texts-freeze-anchor-record.json"


def _anchor():
    """The pinned freeze anchor from the anchor record."""
    return json.loads((ROOT / ANCHOR_RECORD_PATH).read_text(encoding="utf-8"))


# Deterministic identity for scratch commits/tags created inside the sandbox.
_SCRATCH_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "pytest-scratch",
    "GIT_AUTHOR_EMAIL": "pytest-scratch@example.invalid",
    "GIT_COMMITTER_NAME": "pytest-scratch",
    "GIT_COMMITTER_EMAIL": "pytest-scratch@example.invalid",
}


def _git(args):
    r = subprocess.run(GIT + args, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace"))
    return r


@pytest.fixture(scope="module")
def manifests():
    return gam.build_manifests(COMMIT)


def test_resolve_commit_rejects_invalid():
    with pytest.raises(RuntimeError):
        gam.resolve_commit("definitely-not-a-commit")


def test_resolve_commit_accepts_full_commit():
    assert gam.resolve_commit(COMMIT) == COMMIT


def test_blob_info_missing_path_raises():
    with pytest.raises(RuntimeError):
        gam.blob_info("knowledge_base/classic_texts/sanmingtonghui/DOES_NOT_EXIST.json", COMMIT)


def test_blob_info_non_blob_path_raises():
    with pytest.raises(RuntimeError):
        gam.blob_info("knowledge_base/classic_texts/sanmingtonghui", COMMIT)


def test_serialize_is_lf_only(manifests):
    identity, chman = manifests
    for obj in (identity, chman):
        assert b"\r\n" not in gam._serialize(obj), "serialized manifest must be LF-only"


def test_build_manifests_invariants(manifests):
    identity, chman = manifests
    assert identity["counts"]["output_files"] == 8
    assert identity["counts"]["phase8_drift_files"] == 3
    assert identity["counts"]["snapshot_identity"] == 3
    assert identity["counts"]["authoritative_raw_texts_extracted_383"] == 383
    assert identity["counts"]["derived_root_raw_303"] == 303
    assert chman["chapter_count"] == 383
    assert chman["legacy_chapter_count"] == 80
    assert chman["legacy_unique_title_count"] == 80
    assert chman["source_chapter_title_map_count"] == 383
    assert chman["exactly_once_assertion"] == {"rules": 8043, "mcq": 6103, "ok": True}
    assert chman["zero_rule_chapters"] == [25, 56, 72]
    assert chman["zero_mcq_chapters"] == [25, 26, 56, 72, 112]
    for m in (identity, chman):
        g = m["generator"]
        assert g["path"].endswith("generate_acceptance_manifests.py")
        assert len(g["sha256_lf"]) == 64
        assert len(g["blob_oid"]) == 40
        assert g["candidate_commit"] == COMMIT


def test_check_mode_matches_committed(manifests):
    identity, chman = manifests
    for name, obj in zip(gam.OUT_NAMES, (identity, chman)):
        expected = hashlib.sha256(gam._serialize(obj)).hexdigest()
        committed = _git(["show", f"HEAD:docs/superpowers/specs/{name}"]).stdout
        assert hashlib.sha256(committed).hexdigest() == expected, f"{name} drifted from regenerated"


def test_serialize_drift_detects_any_byte_change(manifests):
    identity, _ = manifests
    b = bytearray(gam._serialize(identity))
    base = hashlib.sha256(bytes(b)).hexdigest()
    b[len(b) // 2] ^= 0x01
    assert hashlib.sha256(bytes(b)).hexdigest() != base


def test_cli_check_does_not_modify_manifests():
    """--check with the pinned anchor must exit 0 and leave both manifest files
    byte- and mtime-identical."""
    specs = ROOT / "docs/superpowers/specs"
    paths = [specs / n for n in gam.OUT_NAMES]
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in paths}
    r = subprocess.run(
        [sys.executable, str(ROOT / GENERATOR_PATH),
         "--check", "--freeze-ref", gam.FREEZE_TAG,
         "--expected-freeze-tag-oid", _anchor()["expected_tag_oid"]],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in paths}
    for p in paths:
        assert before[p][0] == after[p][0], f"{p.name} mtime changed by --check"
        assert before[p][1] == after[p][1], f"{p.name} bytes changed by --check"


# ---- anchor-record consistency (fast, main repo, read-only) ----

def test_anchor_record_honest_about_local_only():
    """The record must not claim to be an approval: implementer-created,
    LOCAL_ONLY, no independent approval, formal gate blocked."""
    rec = _anchor()
    assert rec["record_type"] == "freeze-anchor-record"
    assert rec["status"] == "LOCAL_ONLY"
    assert rec["provenance"]["record_created_by"] == "implementer"
    assert rec["provenance"]["independent_approval"] == "none"
    assert rec["overall_state"] == "LOCAL_FREEZE_VERIFIED / FORMAL_GATE_BLOCKED"


def test_anchor_record_matches_real_tag():
    """The pinned OID in the anchor record must equal the real tag object."""
    anchor = _anchor()
    assert anchor["freeze_tag"] == gam.FREEZE_TAG
    oid = _git(["rev-parse", f"refs/tags/{gam.FREEZE_TAG}"]).stdout.decode().strip()
    assert oid == anchor["expected_tag_oid"]


def test_anchor_record_matches_design_doc():
    """The design-doc anchor line must pin the same tag object OID."""
    doc = (ROOT / DESIGN_PATH).read_text(encoding="utf-8")
    assert _anchor()["expected_tag_oid"] in doc, \
        "design doc anchor line must pin the anchor record's tag object OID"


def test_anchor_record_matches_freeze_chain():
    """Every frozen value in the anchor record must equal the tag-pointed
    receipt: freeze commit, payload, candidate, generator, manifest SHAs."""
    anchor = _anchor()
    tag_commit = _git(["rev-parse", f"refs/tags/{gam.FREEZE_TAG}^{{commit}}"]).stdout.decode().strip()
    receipt = json.loads(_git(["show", f"{tag_commit}:{RECEIPT_PATH}"]).stdout.decode("utf-8"))
    assert anchor["freeze_commit"] == tag_commit
    assert anchor["tooling_payload_commit"] == receipt["tooling_payload_commit"]
    assert anchor["candidate_commit"] == receipt["candidate_commit"]
    assert anchor["generator"]["blob_oid"] == receipt["generator"]["blob_oid"]
    assert anchor["generator"]["sha256_lf"] == receipt["generator"]["sha256_lf"]
    assert anchor["manifests"] == receipt["manifests"]


# ---- CLI gating (fast, main repo, read-only) ----

def _run_check_main(*extra):
    return subprocess.run(
        [sys.executable, str(ROOT / GENERATOR_PATH), "--check", *extra],
        capture_output=True, text=True)


def test_cli_check_requires_freeze_ref():
    r = _run_check_main()
    assert r.returncode != 0
    assert "--freeze-ref" in r.stdout + r.stderr


def test_cli_check_requires_expected_tag_oid():
    r = _run_check_main("--freeze-ref", gam.FREEZE_TAG)
    assert r.returncode != 0
    assert "--expected-freeze-tag-oid" in r.stdout + r.stderr


def test_cli_check_missing_tag():
    r = _run_check_main("--freeze-ref", "__missing_freeze_tag__",
                        "--expected-freeze-tag-oid", "0" * 40)
    assert r.returncode != 0
    assert "freeze check FAILED" in r.stdout + r.stderr


def test_freeze_tag_oid_mismatch_rejected():
    r = _run_check_main("--freeze-ref", gam.FREEZE_TAG,
                        "--expected-freeze-tag-oid", "1" * 40)
    assert r.returncode != 0
    assert "tag object OID mismatch" in r.stdout + r.stderr


# ---- sandbox: isolated clone for scratch freeze objects ----

def _rmtree_force(path):
    """rmtree that retries read-only files (git pack files are read-only on
    Windows); failures are still swallowed (leftovers live in gitignored
    .tmp/)."""
    def _chmod_retry(func, p, _exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_chmod_retry)


@pytest.fixture(scope="module")
def sandbox():
    """An isolated --shared --no-checkout clone with only the generator script
    checked out, placed under .tmp/ (gitignored run products) so a locked-down
    environment without a writable pytest temp dir still works. Scratch
    commits/tags live here; the main repository's object database and refs are
    never written to. core.longpaths is enabled because the clone path plus
    the deep candidate paths can exceed Windows MAX_PATH (git show rev:path
    stats the literal string as a candidate filename)."""
    base = ROOT / ".tmp" / f"acceptance_freeze_sandbox_{uuid.uuid4().hex[:8]}"
    clone = base / "wt"
    clone.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            ["git", "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(clone)],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        r = subprocess.run(
            ["git", "-C", str(clone), "config", "core.longpaths", "true"],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        r = subprocess.run(
            ["git", "-C", str(clone), "checkout", "--quiet", "HEAD", "--", GENERATOR_PATH],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        yield clone
    finally:
        _rmtree_force(base)


def _sb(sandbox, args, input_bytes=None):
    r = subprocess.run(["git", "-C", str(sandbox)] + args, capture_output=True,
                       input=input_bytes, env=_SCRATCH_ENV)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace"))
    return r.stdout


def _run_check_in(sandbox, *extra):
    return subprocess.run(
        [sys.executable, str(Path(sandbox) / GENERATOR_PATH), "--check", *extra],
        capture_output=True, text=True)


def _out(r):
    return r.stdout + r.stderr


def _new_tag_name():
    return "__test_freeze_" + uuid.uuid4().hex[:8]


def _hash_blob(sandbox, data):
    return _sb(sandbox, ["hash-object", "-w", "--stdin"], input_bytes=data).decode().strip()


def _mktree(sandbox, entries):
    text = "\n".join(f"{m} {t} {s}\t{n}" for m, t, s, n in entries) + "\n"
    return _sb(sandbox, ["mktree"], input_bytes=text.encode("utf-8")).decode().strip()


def _rebuild(sandbox, tree_sha, prefix, overrides, removes):
    """New tree sha for `tree_sha` (entries under `prefix`, '' = root) after
    applying overrides {full_path: bytes} / removes {full_path}. Only subtrees
    on an affected path are rewritten; core.quotePath is disabled so non-ASCII
    names stay raw UTF-8 (git mktree does not unquote)."""
    affected = set(overrides) | set(removes)
    lines = _sb(sandbox, ["-c", "core.quotePath=false", "ls-tree", tree_sha]).decode("utf-8").splitlines()
    entries = []
    for line in lines:
        mode, typ, sha, name = line.split(maxsplit=3)
        full = prefix + name
        if full in removes:
            continue
        if full in overrides:
            entries.append(("100644", "blob", _hash_blob(sandbox, overrides[full]), name))
        elif typ == "tree" and any(p.startswith(full + "/") for p in affected):
            entries.append((mode, "tree", _rebuild(sandbox, sha, full + "/", overrides, removes), name))
        else:
            entries.append((mode, typ, sha, name))
    return _mktree(sandbox, entries)


def _commit_tree(sandbox, tree, parents):
    args = ["commit-tree", tree]
    for p in parents:
        args += ["-p", p]
    return _sb(sandbox, args, input_bytes=b"test scratch freeze\n").decode().strip()


def _freeze_commit(sandbox):
    return _sb(sandbox, ["rev-parse", f"refs/tags/{gam.FREEZE_TAG}^{{commit}}"]).decode().strip()


def _real_receipt(sandbox):
    """The authoritative receipt, read from the freeze commit the real tag
    points at (never from HEAD)."""
    return json.loads(_sb(sandbox, ["show", f"{_freeze_commit(sandbox)}:{RECEIPT_PATH}"]).decode("utf-8"))


def _real_payload(sandbox):
    return _real_receipt(sandbox)["tooling_payload_commit"]


def _receipt_for(sandbox, name, payload):
    """Copy of the real receipt with freeze_tag=name, ALWAYS binding the given
    scratch payload commit (never the real payload), so the receipt-only and
    ancestor constraints hold by construction and each test hits its layer."""
    real = _real_receipt(sandbox)
    receipt = dict(real)
    receipt["manifests"] = dict(real["manifests"])
    receipt["generator"] = dict(real["generator"])
    receipt["freeze_tag"] = name
    receipt["tooling_payload_commit"] = payload
    return receipt


def _scratch_freeze(sandbox, receipt_fn, payload_overrides=None, payload_removes=None,
                    freeze_overrides=None, freeze_parent=None):
    """Build (payload, freeze) scratch commits derived from the FROZEN payload
    tree (NOT from HEAD, which may have drifted past the freeze): the scratch
    payload is a child of the real payload commit with optional file
    overrides/removals; the freeze commit's tree differs from the payload ONLY
    in the receipt (plus optional extra freeze_overrides for negative tests)
    and its parent defaults to the payload. receipt_fn(payload_sha) builds the
    receipt dict."""
    base = _real_payload(sandbox)
    base_tree = _sb(sandbox, ["rev-parse", f"{base}^{{tree}}"]).decode().strip()
    payload_tree = _rebuild(sandbox, base_tree, "", payload_overrides or {}, set(payload_removes or ()))
    payload = _commit_tree(sandbox, payload_tree, [base])
    receipt_bytes = (json.dumps(receipt_fn(payload), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fo = dict(freeze_overrides or {})
    fo[RECEIPT_PATH] = receipt_bytes
    freeze_tree = _rebuild(sandbox, payload_tree, "", fo, set())
    freeze = _commit_tree(sandbox, freeze_tree, [freeze_parent or payload])
    return payload, freeze


def _tag(sandbox, commit, name):
    _sb(sandbox, ["tag", "-a", name, commit, "-m", "test scratch freeze"])
    return _sb(sandbox, ["rev-parse", f"refs/tags/{name}"]).decode().strip()


def _drop_tag(sandbox, name):
    _sb(sandbox, ["update-ref", "-d", f"refs/tags/{name}"])


def test_cli_check_rejects_lightweight_tag(sandbox):
    name = _new_tag_name()
    head = _sb(sandbox, ["rev-parse", "HEAD"]).decode().strip()
    _sb(sandbox, ["update-ref", f"refs/tags/{name}", head])
    try:
        r = _run_check_in(sandbox, "--freeze-ref", name, "--expected-freeze-tag-oid", head)
        assert r.returncode != 0
        assert "not an annotated tag" in _out(r)
    finally:
        _drop_tag(sandbox, name)


def test_freeze_tampered_receipt_rejected(sandbox):
    """Frozen manifest SHA modified in the scratch receipt -> the
    committed-at-payload layer fails (not a tag-name or receipt-only
    mismatch)."""
    name = _new_tag_name()

    def build(payload):
        receipt = _receipt_for(sandbox, name, payload)
        sha = receipt["manifests"][gam.OUT_NAMES[0]]
        receipt["manifests"][gam.OUT_NAMES[0]] = ("0" if sha[0] != "0" else "1") + sha[1:]
        return receipt

    _, freeze = _scratch_freeze(sandbox, build)
    oid = _tag(sandbox, freeze, name)
    try:
        r = _run_check_in(sandbox, "--freeze-ref", name, "--expected-freeze-tag-oid", oid)
        assert r.returncode != 0
        assert "committed-at-payload" in _out(r)
    finally:
        _drop_tag(sandbox, name)


def test_freeze_payload_missing_manifest_rejected(sandbox):
    name = _new_tag_name()
    _, freeze = _scratch_freeze(
        sandbox,
        lambda p: _receipt_for(sandbox, name, p),
        payload_removes={f"{SPECS}/{n}" for n in gam.OUT_NAMES})
    oid = _tag(sandbox, freeze, name)
    try:
        r = _run_check_in(sandbox, "--freeze-ref", name, "--expected-freeze-tag-oid", oid)
        assert r.returncode != 0
        assert "is missing manifest" in _out(r)
    finally:
        _drop_tag(sandbox, name)


def test_freeze_generator_missing_at_payload_rejected(sandbox):
    name = _new_tag_name()
    _, freeze = _scratch_freeze(
        sandbox,
        lambda p: _receipt_for(sandbox, name, p),
        payload_removes={GENERATOR_PATH})
    oid = _tag(sandbox, freeze, name)
    try:
        r = _run_check_in(sandbox, "--freeze-ref", name, "--expected-freeze-tag-oid", oid)
        assert r.returncode != 0
        assert "missing the generator blob" in _out(r)
    finally:
        _drop_tag(sandbox, name)


def test_freeze_generator_replaced_at_payload_rejected(sandbox):
    name = _new_tag_name()
    _, freeze = _scratch_freeze(
        sandbox,
        lambda p: _receipt_for(sandbox, name, p),
        payload_overrides={GENERATOR_PATH: b"# tampered generator\n"})
    oid = _tag(sandbox, freeze, name)
    try:
        r = _run_check_in(sandbox, "--freeze-ref", name, "--expected-freeze-tag-oid", oid)
        assert r.returncode != 0
        assert "generator at payload" in _out(r)
    finally:
        _drop_tag(sandbox, name)


def test_freeze_receipt_only_violation_rejected(sandbox):
    """The freeze commit changes the design doc in addition to the receipt ->
    fails the receipt-only constraint. The scratch chain is otherwise fully
    valid, so this genuinely exercises the layer (no false positive)."""
    name = _new_tag_name()
    _, freeze = _scratch_freeze(
        sandbox,
        lambda p: _receipt_for(sandbox, name, p),
        freeze_overrides={DESIGN_PATH: b"tampered\n"})
    oid = _tag(sandbox, freeze, name)
    try:
        # Sanity: without the injected design change the same construction
        # must verify OK end-to-end (proves the failure below is caused by
        # the injected change, not by construction artifacts).
        _, clean_freeze = _scratch_freeze(sandbox, lambda p: _receipt_for(sandbox, name + "b", p))
        clean_name = name + "b"
        clean_oid = _tag(sandbox, clean_freeze, clean_name)
        try:
            r0 = _run_check_in(sandbox, "--freeze-ref", clean_name, "--expected-freeze-tag-oid", clean_oid)
            assert r0.returncode == 0, _out(r0)
            assert "must change only the receipt" not in _out(r0)
        finally:
            _drop_tag(sandbox, clean_name)
        r = _run_check_in(sandbox, "--freeze-ref", name, "--expected-freeze-tag-oid", oid)
        assert r.returncode != 0
        assert "must change only the receipt" in _out(r)
    finally:
        _drop_tag(sandbox, name)


def test_freeze_ancestor_violation_rejected(sandbox):
    name = _new_tag_name()
    # The freeze commit's parent is the real payload, so the scratch payload
    # referenced by the receipt is NOT an ancestor of the freeze commit.
    _, freeze = _scratch_freeze(
        sandbox,
        lambda p: _receipt_for(sandbox, name, p),
        freeze_parent=_real_payload(sandbox))
    oid = _tag(sandbox, freeze, name)
    try:
        r = _run_check_in(sandbox, "--freeze-ref", name, "--expected-freeze-tag-oid", oid)
        assert r.returncode != 0
        assert "is not an ancestor" in _out(r)
    finally:
        _drop_tag(sandbox, name)


def _tampered_manifest(sandbox):
    head = _sb(sandbox, ["rev-parse", "HEAD"]).decode().strip()
    orig = _sb(sandbox, ["show", f"{head}:{SPECS}/{gam.OUT_NAMES[0]}"])
    flipped = bytearray(orig)
    flipped[10] ^= 0x01
    return bytes(flipped)


def test_freeze_simultaneous_tamper_rejected(sandbox):
    """Self-consistent re-freeze (tampered manifest at the payload, receipt
    freezes its SHA, attacker supplies the new tag OID): still rejected at the
    regeneration layer."""
    name = _new_tag_name()
    tm = _tampered_manifest(sandbox)

    def build(payload):
        receipt = _receipt_for(sandbox, name, payload)
        receipt["manifests"][gam.OUT_NAMES[0]] = hashlib.sha256(tm).hexdigest()
        return receipt

    _, freeze = _scratch_freeze(sandbox, build, payload_overrides={f"{SPECS}/{gam.OUT_NAMES[0]}": tm})
    oid = _tag(sandbox, freeze, name)
    try:
        r = _run_check_in(sandbox, "--freeze-ref", name, "--expected-freeze-tag-oid", oid)
        assert r.returncode != 0
        assert "regenerated" in _out(r)
        assert "!= frozen" in _out(r)
    finally:
        _drop_tag(sandbox, name)


def test_freeze_repointed_tag_rejected_by_pinned_oid(sandbox):
    """The same self-consistent re-freeze, verified with the PINNED anchor from
    the LOCAL_ONLY anchor record: the re-pointed tag is rejected at the
    tag-anchor layer."""
    name = _new_tag_name()
    tm = _tampered_manifest(sandbox)

    def build(payload):
        receipt = _receipt_for(sandbox, name, payload)
        receipt["manifests"][gam.OUT_NAMES[0]] = hashlib.sha256(tm).hexdigest()
        return receipt

    _, freeze = _scratch_freeze(sandbox, build, payload_overrides={f"{SPECS}/{gam.OUT_NAMES[0]}": tm})
    _tag(sandbox, freeze, name)
    try:
        r = _run_check_in(sandbox, "--freeze-ref", name,
                          "--expected-freeze-tag-oid", _anchor()["expected_tag_oid"])
        assert r.returncode != 0
        assert "tag object OID mismatch" in _out(r)
    finally:
        _drop_tag(sandbox, name)


def test_freeze_running_generator_mismatch_rejected(sandbox):
    """Attacker payload carries a modified generator and the receipt freezes
    IT: manifests stay consistent, so only the running-generator layer catches
    the attack."""
    name = _new_tag_name()
    evil = b"# tampered generator\n"
    evil_oid = _hash_blob(sandbox, evil)

    def build(payload):
        receipt = _receipt_for(sandbox, name, payload)
        receipt["generator"]["blob_oid"] = evil_oid
        receipt["generator"]["sha256_lf"] = hashlib.sha256(evil).hexdigest()
        return receipt

    _, freeze = _scratch_freeze(sandbox, build, payload_overrides={GENERATOR_PATH: evil})
    oid = _tag(sandbox, freeze, name)
    try:
        r = _run_check_in(sandbox, "--freeze-ref", name, "--expected-freeze-tag-oid", oid)
        assert r.returncode != 0
        assert "running generator" in _out(r)
    finally:
        _drop_tag(sandbox, name)


def test_check_ignores_tampered_head_receipt(sandbox):
    """P0-2(v4.2) regression: with sandbox HEAD detached at a scratch freeze
    commit carrying a tampered receipt, the real freeze tag still verifies OK
    (the verifier never reads HEAD), while the scratch ref itself is rejected
    at the committed-at-payload layer."""
    name = _new_tag_name()

    def build(payload):
        receipt = _receipt_for(sandbox, name, payload)
        receipt["manifests"][gam.OUT_NAMES[0]] = "0" * 64
        return receipt

    _, freeze = _scratch_freeze(sandbox, build)
    oid = _tag(sandbox, freeze, name)
    try:
        _sb(sandbox, ["update-ref", "--no-deref", "HEAD", freeze])
        r = _run_check_in(sandbox, "--freeze-ref", gam.FREEZE_TAG,
                          "--expected-freeze-tag-oid", _anchor()["expected_tag_oid"])
        assert r.returncode == 0, _out(r)
        r2 = _run_check_in(sandbox, "--freeze-ref", name, "--expected-freeze-tag-oid", oid)
        assert r2.returncode != 0
        assert "committed-at-payload" in _out(r2)
    finally:
        _sb(sandbox, ["symbolic-ref", "HEAD", "refs/heads/main"])
        _drop_tag(sandbox, name)
