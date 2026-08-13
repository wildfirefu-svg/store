"""
classic_artifacts.py
Shared content-fingerprint and provenance utilities for classic-text distillation
artifacts. Single source of truth for the conservation contract used by both the
remediation script and the quality-report generator.

Fingerprint design (P0-4):
  - Rule fingerprint covers the FULL canonical record (rule, original_text,
    condition, subject, category, source_book, ...) EXCEPT the explicitly allowed
    varying fields: id, source_chapter (mergeable cross-chapter), source_chapters,
    and quarantine bookkeeping keys. Tampering original_text/condition/subject
    therefore breaks conservation.
  - MCQ fingerprint covers question, the multiset of option BODY values (so label
    re-arrangement by answer rotation stays invariant but option-body tampering is
    caught), explanation, difficulty, category, and a content token of the source
    rule (stable across rule-ID remapping).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Callable

# Keys that legitimately vary during remediation and must be excluded from the
# immutable content fingerprint.
RULE_IGNORE_KEYS = {
    "id",
    "source_chapter",  # cross-chapter merge operates on rule text
    "source_chapters",
    "quarantine_reason",
    "_quarantine_reason",
    "_content_fingerprint",
    "_recovered_from",
}
MCQ_IGNORE_KEYS = {
    "id",
    "answer",  # changed by answer rotation
    "source_rule_id",  # remapped during remediation; source covered via content token
    "quarantine_reason",
    "_quarantine_reason",
    "_content_fingerprint",
    "_recovered_from",
}

# Legal closed mapping from a run's frozen operation to its preservation mode.
# The validator enforces that a run manifest's frozen (operation,
# preserves_existing_mcqs) pair is one of these, so a self-consistent but
# illegal pair cannot disable the pre-run MCQ disjointness check (P0-10).
VALID_MODES = {
    "fill": True,
    "regen": False,
}


class ConservationError(Exception):
    """Raised when data conservation is violated."""


def _norm(s: object) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _canonical(obj) -> str:
    """Deterministic canonical JSON serialization (sorted keys, no spaces)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _clean_dict(d: dict, ignore: set[str]) -> dict:
    out = {}
    for k, v in d.items():
        if k in ignore:
            continue
        if isinstance(v, (dict, list)):
            out[k] = v  # nested kept as-is; rule fields are scalars in practice
        else:
            out[k] = _norm(v)
    return out


def rule_fp(rule: dict) -> str:
    """Immutable content fingerprint for a rule (full canonical record)."""
    keep = _clean_dict(rule, RULE_IGNORE_KEYS)
    return _sha256(_canonical(keep))


def mcq_fp(mcq: dict) -> str:
    """Immutable content fingerprint for an MCQ.

    Covers question + sorted option BODY values + explanation + difficulty +
    category. It is invariant to id renumbering and answer rotation (which only
    permutes option labels, preserving the multiset of option bodies), but
    sensitive to option-body / question / explanation tampering.

    `answer` and `source_rule_id` are intentionally NOT part of the conservation
    fingerprint: the answer label legitimately changes under rotation, and
    source_rule_id is legitimately remapped during remediation (rule IDs are
    renumbered and cross-chapter rules merged). Source-rule linkage is validated
    separately (remediation remap + validator G4), not via the conservation
    multiset, so that conservation remains robust to re-runs.
    """
    opts = mcq.get("options")
    if isinstance(opts, dict):
        bodies = sorted(_norm(v) for v in opts.values())
    else:
        bodies = []
    parts = [
        _norm(mcq.get("question", "")),
        "|".join(bodies),
        _norm(mcq.get("explanation", "")),
        _norm(mcq.get("difficulty", "")),
        _norm(mcq.get("category", "")),
    ]
    return _sha256("||".join(parts))


def build_rule_content_map(rules: list[dict]) -> dict[str, str]:
    """Map rule.id -> content token (rule_fp). For resolving MCQ source_rule_id."""
    return {r.get("id", ""): rule_fp(r) for r in rules if isinstance(r, dict)}


def mcq_record_sha256(mcq: dict) -> str:
    """SHA-256 of a MCQ's FULL canonical record (id, question, options, answer,
    explanation, category, difficulty, and any audit flags).

    Unlike mcq_fp (which deliberately ignores id/answer/source_rule_id so that
    conservation stays rotation/remap-robust), this is the exact record hash.
    It is used to prove which MCQs a run actually generated: replacing an MCQ's
    content under the same id (or reusing an old id) changes this hash.
    """
    return _sha256(_canonical(mcq))


def verify_conservation(
    old_clean: list[dict],
    old_q: list[dict],
    new_clean: list[dict],
    new_q: list[dict],
    fp_fn: Callable[[dict], str],
    label: str = "items",
) -> None:
    """Verify multiset conservation: old_clean + old_q == new_clean + new_q.

    Raises ConservationError if any item is lost or gained.
    """
    old = {}
    new = {}
    for item in old_clean + old_q:
        k = fp_fn(item)
        old[k] = old.get(k, 0) + 1
    for item in new_clean + new_q:
        k = fp_fn(item)
        new[k] = new.get(k, 0) + 1
    if old != new:
        missing = sum(old.get(k, 0) - new.get(k, 0) for k in old if old[k] > new.get(k, 0))
        gained = sum(new.get(k, 0) - old.get(k, 0) for k in new if new[k] > old.get(k, 0))
        raise ConservationError(
            f"Conservation violated ({label}): {missing} items lost, {gained} items gained."
        )


# ---------------------------------------------------------------------------
# Provenance validation (P0-2, P0-3)
# ---------------------------------------------------------------------------

# Two-layer provenance schema (P0-3 decision):
#   - remediation provenance: no-API post-hoc fix-up. Records no_api=true,
#     input_baseline_commit, worktree_dirty, anchor_commit_verified. Does NOT
#     record provider/model/temperature (no model calls happen here).
#   - distillation provenance (distill_lib.py, separate): records provider,
#     model, thinking, temperature. Out of scope for this module.

# P0-3: there is exactly ONE authoritative frozen model config, defined in
# distill_lib.py (where _call() builds the real API payload). validate_provenance
# imports that same constant -- a 'recovered' upstream provenance must declare
# EXACTLY these values, and the config fingerprint is recomputed from this
# constant, never from the provenance's own provider/model/thinking fields.

PROVENANCE_REQUIRED_FIELDS = {
    "generated_at",
    "file_shas",
    "code_shas",
    "raw_text_shas",
    "anchor_commit",
    "anchor_commit_verified",
    "no_api",
    "input_baseline_commit",
    "worktree_dirty",
    "code_fingerprint",
    "upstream_provenance_status",    # "recovered" or "unavailable" (P0-3)
    "input_baseline_blob_shas",      # git blob SHAs of raw files at baseline (P0-3)
}

# Optional field: only present after the artifacts themselves have been
# committed. Never required at generation time (you cannot know the future
# commit hash before committing).
PROVENANCE_OPTIONAL_FIELDS = {
    "artifact_commit",               # commit that contains the published artifacts
    "upstream_provenance",           # nested distillation-stage provenance (P0-3)
}

OUTPUT_FILE_NAMES = (
    "all_rules.json",
    "all_mcq.jsonl",
    "quarantine_rules.jsonl",
    "quarantine_mcq.jsonl",
    "remediation_meta.json",
)

CODE_FILE_NAMES = (
    "remediate_classic_distillation.py",
    "validate_classic_distillation.py",
    "distill_lib.py",
    "classic_artifacts.py",
)


def _git_commit_exists(root: Path, commit: str) -> bool:
    """Return True if `commit` is a real object in the git repo at `root`."""
    if not commit or commit == "unknown":
        return False
    import subprocess
    try:
        r = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            capture_output=True, cwd=str(root),
        )
        return r.returncode == 0
    except Exception:
        return False


def _is_relative_to(p: Path, root: Path) -> bool:
    """Check if p is inside root (Python 3.9+ has Path.is_relative_to)."""
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def _git_blob_sha256_at_commit(
    root: Path, commit: str, book_rel: str, artifact_name: str
) -> str | None:
    """Return SHA-256 of the file content at <commit>:<book_rel>/<artifact_name>.

    Uses `git cat-file -p` to read the blob content, then computes SHA-256.
    Returns None if the blob cannot be read (e.g. file not tracked at commit).

    P0-4: this verifies that recorded upstream_artifact_shas match the actual
    bytes in git history, not just the format of the SHA string.
    """
    if not commit or not book_rel or not artifact_name:
        return None
    import subprocess
    blob_path = f"{book_rel}/{artifact_name}"
    try:
        r = subprocess.run(
            ["git", "cat-file", "-p", f"{commit}:{blob_path}"],
            capture_output=True, cwd=str(root),
        )
        if r.returncode != 0:
            return None
        return hashlib.sha256(r.stdout).hexdigest()
    except Exception:
        return None


def _git_blob_bytes_at_commit(root: Path, commit: str, rel_path: str) -> bytes | None:
    """Return raw bytes of a file at <commit>:<rel_path> (P0-1 raw_sources).

    Returns None on any error (commit/path missing or not readable). Used by
    validate_provenance to re-extract a derived raw file from its baseline
    source so the derivation anchor is recomputable rather than trusted.
    """
    if not commit or not rel_path:
        return None
    import subprocess
    try:
        r = subprocess.run(
            ["git", "cat-file", "-p", f"{commit}:{rel_path}"],
            capture_output=True, cwd=str(root),
        )
        if r.returncode != 0:
            return None
        return r.stdout
    except Exception:
        return None


def _verify_derivation_anchor(
    name: str,
    anchor: object,
    source_blob_sha256: str,
    source_bytes: bytes,
    target_sha256: str,
) -> str | None:
    """Verify a raw_sources derivation anchor is recomputable from the source.

    Returns None if the anchor is verified, otherwise an issue string. This is
    a PURE function (no git) so it can be unit-tested directly.

    P0-1: an anchor is only trusted if ALL hold:
      - derived_from_blob_sha256 equals the source's actual baseline blob SHA;
      - the extraction is deterministic (substring_strip with source_start/end);
      - re-extracting source_bytes[start:end].strip() reproduces the target
        raw file's SHA-256. A forged anchor that just claims
        derived_from='raw_full.txt' cannot pass because the slice will not
        reproduce the recorded raw SHA.
    """
    if not isinstance(anchor, dict):
        return f"raw_sources[{name!r}] must be an object"
    derived = anchor.get("derived_from", "")
    recorded_blob = anchor.get("derived_from_blob_sha256", "")
    if not derived or not recorded_blob:
        return f"raw_sources[{name!r}] missing derived_from/derived_from_blob_sha256"
    if recorded_blob != source_blob_sha256:
        return (
            f"raw_sources[{name!r}] derived_from_blob_sha256 mismatch: "
            f"recorded={recorded_blob[:16]}, actual_source={source_blob_sha256[:16]}"
        )
    strategy = anchor.get("extraction_strategy", "")
    if strategy == "substring_strip":
        start = anchor.get("source_start")
        end = anchor.get("source_end")
        if not (isinstance(start, int) and isinstance(end, int)
                and 0 <= start <= end <= len(source_bytes)):
            return f"raw_sources[{name!r}] invalid source_start/source_end"
        derived_sha = hashlib.sha256(source_bytes[start:end].strip()).hexdigest()
        if derived_sha != target_sha256:
            return (
                f"raw_sources[{name!r}] re-extraction mismatch: "
                f"derived={derived_sha[:16]}, target={target_sha256[:16]}"
            )
        return None
    return f"raw_sources[{name!r}] unsupported extraction_strategy {strategy!r}"


def _git_hash_object(root: Path, file_path: Path) -> str:
    """Return the git blob SHA of a file via `git hash-object` (P0-3).

    This gives the same SHA as `git rev-parse <commit>:<path>` for the same
    file content, enabling comparison between the current file and the file
    at a historical commit.
    """
    import subprocess
    try:
        r = subprocess.run(
            ["git", "hash-object", str(file_path)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(root),
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def validate_provenance(
    p: Path,
    scripts_dir: Path,
    git_root: Path | None = None,
) -> tuple[bool, list[str]]:
    """Validate provenance.json against actual on-disk files.

    Returns (ok, issues). 'ok' is True only if:
      - provenance.json exists and parses
      - all required fields present (incl. P0-3 fields)
      - every file_sha matches the actual file
      - every code_sha matches the actual script
      - every raw_text_sha matches the actual raw file
      - anchor_commit_verified is True (generator pre-verified the commit)
      - if git_root is given: anchor_commit really exists in the git object
        store (existence check only, NOT compared to current HEAD -- the
        worktree may legitimately advance after artifacts are committed)
      - if input_baseline_blob_shas present and git_root given: each raw
        file's git blob SHA matches the blob at the baseline commit (proves
        input files were not tampered with since baseline)

    `git_root` is optional for backward compatibility with callers that only
    need the SHA-match checks. Remediation and quality-report pass the repo
    root so the anchor_commit existence and input_baseline_blob checks run.
    """
    issues: list[str] = []
    prov_file = p / "provenance.json"
    if not prov_file.exists():
        return False, ["provenance.json missing"]
    try:
        prov = json.loads(prov_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, [f"provenance.json unparseable: {e}"]

    if not isinstance(prov, dict):
        return False, ["provenance.json is not an object"]

    missing_fields = PROVENANCE_REQUIRED_FIELDS - set(prov.keys())
    if missing_fields:
        issues.append(f"missing required fields: {sorted(missing_fields)}")

    # anchor_commit_verified must be True (generator ran the check).
    if prov.get("anchor_commit_verified") is not True:
        issues.append(
            f"anchor_commit_verified is not True (got {prov.get('anchor_commit_verified')!r})"
        )

    # If git_root provided, re-verify anchor_commit really exists in the object
    # store. We deliberately do NOT compare it to current HEAD: the worktree
    # may have advanced (e.g. after committing the artifacts) and that is a
    # legitimate state. Existence is enough to prove the recorded commit is
    # not fabricated.
    if git_root is not None:
        anchor = prov.get("anchor_commit", "")
        if not _git_commit_exists(git_root, anchor):
            issues.append(f"anchor_commit {anchor!r} does not exist in git repo")
        # input_baseline_commit must also exist (it is the frozen input ref).
        input_baseline = prov.get("input_baseline_commit", "")
        if input_baseline and not _git_commit_exists(git_root, input_baseline):
            issues.append(
                f"input_baseline_commit {input_baseline!r} does not exist in git repo"
            )

    # code_fingerprint must be a 64-char hex SHA-256.
    cf = prov.get("code_fingerprint", "")
    if not (isinstance(cf, str) and len(cf) == 64):
        issues.append(f"code_fingerprint invalid (got {cf!r})")

    file_shas = prov.get("file_shas", {}) or {}
    for name in OUTPUT_FILE_NAMES:
        f = p / name
        if not f.exists():
            issues.append(f"output file missing: {name}")
            continue
        actual = sha256_file(f)
        recorded = file_shas.get(name)
        if recorded != actual:
            issues.append(
                f"file_sha mismatch for {name}: recorded={recorded}, actual={actual}"
            )

    code_shas = prov.get("code_shas", {}) or {}
    for name in CODE_FILE_NAMES:
        f = scripts_dir / name
        if not f.exists():
            continue
        actual = sha256_file(f)
        recorded = code_shas.get(name)
        if recorded != actual:
            issues.append(
                f"code_sha mismatch for {name}: recorded={recorded}, actual={actual}"
            )

    raw_shas = prov.get("raw_text_shas", {}) or {}
    for f in sorted(p.glob("raw_*.txt")):
        actual = sha256_file(f)
        recorded = raw_shas.get(f.name)
        if recorded != actual:
            issues.append(
                f"raw_sha mismatch for {f.name}: recorded={recorded}, actual={actual}"
            )

    # input_baseline_blob_shas: FAIL-CLOSED full-coverage check (P0-3).
    # Only enforced when git_root is available (can't verify blobs without git).
    # When git_root is None, the entire check is skipped.
    # When git_root is provided:
    #   - Requires input_baseline_blob_shas.keys() == raw_text_shas.keys()
    #   - In the PUBLISHED state (raw files present in p): missing file, git
    #     hash-object failure, or blob mismatch are hard failures.
    #   - In the STAGED state (raw files live in the book dir, not staging):
    #     per-file blob SHA comparison is skipped because the raw files are not
    #     in `p`. The keys-must-match check still runs. The published-state
    #     subprocess verification re-runs the full per-file blob check against
    #     the real raw files, so skipping here does not weaken the contract.
    if git_root is not None:
        baseline_blobs = prov.get("input_baseline_blob_shas", {})
        if not isinstance(baseline_blobs, dict):
            baseline_blobs = {}
        raw_names = set(raw_shas.keys())
        blob_names = set(baseline_blobs.keys())
        # P0-3: a raw file missing a baseline blob is acceptable ONLY if it has
        # a verifiable derivation anchor in `raw_sources` whose source file IS
        # itself baseline-anchored. This is how fill_missing_chapters anchors
        # brand-new raw files without disabling the gate.
        raw_sources = prov.get("raw_sources", {})
        if not isinstance(raw_sources, dict):
            raw_sources = {}
        input_baseline = prov.get("input_baseline_commit", "")
        anchored_new_files = set()
        for name in (raw_names - blob_names):
            anchor = raw_sources.get(name)
            derived = anchor.get("derived_from", "") if isinstance(anchor, dict) else ""
            if derived not in blob_names:
                continue  # source not baseline-anchored -> not acceptable
            # Fetch the source's ACTUAL baseline bytes + blob SHA-256 so the
            # derivation can be RECOMPUTED (P0-1) rather than trusted.
            source_blob = ""
            source_bytes = b""
            if _is_relative_to(p, git_root) and input_baseline:
                try:
                    source_rel = (p / derived).relative_to(git_root).as_posix()
                except ValueError:
                    source_rel = ""
                if source_rel:
                    raw = _git_blob_bytes_at_commit(git_root, input_baseline, source_rel)
                    if raw is not None:
                        source_bytes = raw
                        source_blob = hashlib.sha256(raw).hexdigest()
            err = _verify_derivation_anchor(
                name, anchor, source_blob, source_bytes, raw_shas[name])
            if err is None:
                anchored_new_files.add(name)
            else:
                issues.append(err)
        if raw_names != blob_names:
            missing_blobs = raw_names - blob_names - anchored_new_files
            extra_blobs = blob_names - raw_names
            if missing_blobs:
                issues.append(
                    f"input_baseline_blob_shas missing entries for: "
                    f"{sorted(missing_blobs)} (must cover all raw_text_shas keys "
                    f"or have a verified raw_sources derivation anchor)"
                )
            if extra_blobs:
                issues.append(
                    f"input_baseline_blob_shas has extra entries: "
                    f"{sorted(extra_blobs)} (must match raw_text_shas keys exactly)"
                )
        # Per-file blob SHA comparison only when raw files are actually
        # present in p (published state). In staged state the raw files are
        # still in the book dir, not staging, so we cannot compare here; the
        # post-publish subprocess verification covers it.
        raw_files_present = any((p / fname).exists() for fname in baseline_blobs)
        if raw_files_present:
            for fname, expected_blob in baseline_blobs.items():
                f = p / fname
                if not f.exists():
                    issues.append(
                        f"input_baseline_blob check: raw file {fname!r} does not exist"
                    )
                    continue
                actual_blob = _git_hash_object(git_root, f)
                if not actual_blob:
                    issues.append(
                        f"input_baseline_blob check: git hash-object failed for {fname!r}"
                    )
                elif actual_blob != expected_blob:
                    issues.append(
                        f"input_baseline_blob mismatch for {fname}: "
                        f"recorded={expected_blob}, actual={actual_blob}"
                    )

    # upstream_provenance_status validation (P0-3/P0-4)
    # P0-4: 'recovered' must prove full upstream schema AND verify actual
    # bytes, not just check field presence and SHA string format.
    # Required: provider, model, source_url, source_version, distill_script,
    # thinking_mode, temperature, upstream_artifact_shas, upstream_artifact_commit.
    # upstream_artifact_shas must contain at least all_rules.json and all_mcq.jsonl
    # SHA-256 entries, AND each SHA must be verified against the actual git
    # blob content at upstream_artifact_commit.
    UPSTREAM_REQUIRED_FULL = {
        "provider", "model", "source_url", "source_version",
        "distill_script", "thinking_mode", "temperature",
        "upstream_artifact_shas", "upstream_artifact_commit",
        # P0-4: generation-chain fingerprints. 'recovered' must prove the
        # artifacts were produced by a specific script, prompt, and config --
        # not merely that the bytes exist at some commit.
        "distill_script_sha256", "prompt_sha256", "config_sha256",
    }
    UPSTREAM_ARTIFACT_REQUIRED = {"all_rules.json", "all_mcq.jsonl"}

    upstream_status = prov.get("upstream_provenance_status", "")
    if upstream_status == "recovered":
        upstream = prov.get("upstream_provenance")
        if not isinstance(upstream, dict) or not upstream:
            issues.append(
                "upstream_provenance_status='recovered' but upstream_provenance "
                "is missing or empty"
            )
        else:
            missing_up = UPSTREAM_REQUIRED_FULL - set(upstream.keys())
            if missing_up:
                issues.append(
                    f"upstream_provenance missing required keys: {sorted(missing_up)}"
                )
            # upstream_artifact_shas must be a dict with required artifact entries.
            up_shas = upstream.get("upstream_artifact_shas")
            if not isinstance(up_shas, dict):
                issues.append(
                    "upstream_provenance.upstream_artifact_shas must be a dict"
                )
                up_shas = {}  # normalize so the later .items() loop does not crash
            else:
                missing_artifacts = UPSTREAM_ARTIFACT_REQUIRED - set(up_shas.keys())
                if missing_artifacts:
                    issues.append(
                        f"upstream_artifact_shas missing entries: "
                        f"{sorted(missing_artifacts)}"
                    )
                # Each SHA must be a 64-char hex string (SHA-256).
                for name, sha in up_shas.items():
                    if not (isinstance(sha, str) and len(sha) == 64):
                        issues.append(
                            f"upstream_artifact_shas[{name!r}] is not a valid "
                            f"SHA-256 (got {sha!r})"
                        )
            # P0-4: generation-chain fingerprints must be present, well-formed,
            # AND recomputable from the frozen canonical prompt / config /
            # script. A recorded SHA that does not match the frozen canonical is
            # a failure -- the artifacts cannot be proven to come from the
            # declared generation chain.
            recorded_prompt = upstream.get("prompt_sha256", "")
            recorded_config = upstream.get("config_sha256", "")
            recorded_script = upstream.get("distill_script_sha256", "")
            expected_prompt = expected_config = ""
            try:
                from scripts.distill_lib import (
                    canonical_prompt_sha256,
                    canonical_config_sha256,
                )
                expected_prompt = canonical_prompt_sha256()
                # P0-3: the config fingerprint is recomputed ONLY from the
                # frozen constants -- never from provenance-declared params,
                # which an attacker could change alongside config_sha256.
                expected_config = canonical_config_sha256()
            except Exception as e:
                issues.append(
                    f"could not recompute canonical prompt/config SHA: {e!r} -- "
                    f"generation chain not fully provable"
                )
            # P0-3: the provenance-declared model config must equal the frozen
            # constants actually used by distill_lib._call(). The constant is
            # imported from distill_lib (single authoritative copy), never
            # redefined here.
            frozen_cfg = {}
            try:
                from scripts.distill_lib import FROZEN_MODEL_CONFIG as _FMC
                frozen_cfg = _FMC
            except Exception as e:
                issues.append(
                    f"could not import frozen model config: {e!r} -- "
                    f"generation chain not fully provable"
                )
            cfg_bad = [
                f"{k}={upstream.get(k)!r} (expected {v!r})"
                for k, v in frozen_cfg.items()
                if upstream.get(k) != v
            ]
            if cfg_bad:
                issues.append(
                    "upstream_provenance model config not frozen: " + "; ".join(cfg_bad)
                )
            for fk, fv in (
                ("distill_script_sha256", recorded_script),
                ("prompt_sha256", recorded_prompt),
                ("config_sha256", recorded_config),
            ):
                if not (isinstance(fv, str) and len(fv) == 64):
                    issues.append(
                        f"upstream_provenance.{fk} must be a 64-char SHA-256 "
                        f"(got {fv!r}) -- generation chain not fully provable"
                    )
            if expected_prompt and recorded_prompt and recorded_prompt != expected_prompt:
                issues.append(
                    f"upstream_provenance.prompt_sha256 mismatch: "
                    f"recorded={recorded_prompt[:16]}, "
                    f"canonical={expected_prompt[:16]} (prompt not frozen)"
                )
            if expected_config and recorded_config and recorded_config != expected_config:
                issues.append(
                    f"upstream_provenance.config_sha256 mismatch: "
                    f"recorded={recorded_config[:16]}, "
                    f"canonical={expected_config[:16]} (config not frozen)"
                )
            # distill_script must be a CANONICAL RELATIVE path to a real file
            # inside the allowed scripts dir (fail-closed). Path traversal
            # (absolute path, '..', drive) is rejected outright -- it must not
            # be silently normalized to a basename.
            dscript = upstream.get("distill_script", "")
            if isinstance(dscript, str) and dscript.strip():
                script_rel = Path(dscript)
                if script_rel.is_absolute() or any(p == ".." for p in script_rel.parts):
                    issues.append(
                        f"upstream_provenance.distill_script {dscript!r} contains "
                        f"path traversal -- rejected"
                    )
                else:
                    script_file = (scripts_dir / script_rel).resolve()
                    allowed = scripts_dir.resolve()
                    if not (_is_relative_to(script_file, allowed) and script_file.is_file()):
                        issues.append(
                            f"upstream_provenance.distill_script {dscript!r} not found "
                            f"in allowed scripts dir {scripts_dir} -- chain not provable"
                        )
                    else:
                        actual_script_sha = hashlib.sha256(script_file.read_bytes()).hexdigest()
                        if recorded_script and actual_script_sha != recorded_script:
                            issues.append(
                                f"distill_script_sha256 mismatch for {dscript!r}: "
                                f"recorded={recorded_script}, actual={actual_script_sha}"
                            )
            else:
                issues.append(
                    "upstream_provenance.distill_script must be a non-empty string"
                )
            # P0-4: verify upstream_artifact_shas against actual git blob bytes.
            # 'recovered' requires that the recorded SHAs match the actual
            # file content at upstream_artifact_commit. Without this, any
            # 64-char string would pass -- a false positive.
            up_commit = upstream.get("upstream_artifact_commit", "")
            if up_commit and git_root is not None:
                if not _git_commit_exists(git_root, up_commit):
                    issues.append(
                        f"upstream_artifact_commit {up_commit!r} does not exist "
                        f"in git object store"
                    )
                else:
                    # Verify each upstream artifact SHA against git blob content.
                    book_rel = str(p.relative_to(git_root).as_posix()) if _is_relative_to(p, git_root) else ""
                    for name, expected_sha in up_shas.items():
                        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
                            continue  # already reported above
                        actual_sha = _git_blob_sha256_at_commit(
                            git_root, up_commit, book_rel, name
                        )
                        if actual_sha is None:
                            issues.append(
                                f"upstream_artifact_shas[{name!r}]: could not "
                                f"read blob at {up_commit[:12]}:{book_rel}/{name}"
                            )
                        elif actual_sha != expected_sha:
                            issues.append(
                                f"upstream_artifact_shas[{name!r}] mismatch: "
                                f"recorded={expected_sha}, "
                                f"actual_git_blob={actual_sha}"
                            )
            elif up_commit and git_root is None:
                issues.append(
                    "upstream_artifact_commit provided but git_root is None -- "
                    "cannot verify upstream artifact SHAs against git bytes; "
                    "status should be 'partial' not 'recovered'"
                )
            else:
                issues.append(
                    "upstream_provenance_status='recovered' requires "
                    "upstream_artifact_commit for byte-level verification"
                )
    elif upstream_status == "unavailable":
        # Valid -- upstream data could not be recovered. Report must not
        # claim end-to-end provenance completeness.
        pass
    elif upstream_status == "partial":
        # P0-4: partial means some upstream data was recovered but not enough
        # to prove end-to-end provenance. Valid status but end_to_end_pass
        # must be False. upstream_provenance may or may not be present.
        pass
    elif upstream_status:
        issues.append(
            f"upstream_provenance_status must be 'recovered', 'partial', or "
            f"'unavailable', got {upstream_status!r}"
        )

    # P0-2: api_generation layer -- binds the CURRENT MCQ output to the run's
    # API generation chain. The preserved upstream_provenance layer only proves
    # the OLD commit's artifact bytes; it cannot attribute the CURRENT
    # all_mcq.jsonl. If all_mcq.jsonl contains clean MCQs, there MUST be an
    # api_generation record whose mcq_output_sha matches the file; otherwise
    # the MCQs are not provably bound to any verified generation chain.
    mcq_f = p / "all_mcq.jsonl"
    mcq_lines: list[str] = []
    if mcq_f.exists():
        try:
            mcq_lines = [l for l in mcq_f.read_text(encoding="utf-8").splitlines() if l.strip()]
        except Exception:
            mcq_lines = []
    api_gen = prov.get("api_generation")
    if mcq_lines and not api_gen:
        issues.append(
            "all_mcq.jsonl has clean MCQs but provenance has no api_generation "
            "record -- current MCQs are not bound to a verified API generation chain"
        )
    elif api_gen is not None:
        if not isinstance(api_gen, dict):
            issues.append("provenance.api_generation must be an object")
        else:
            actual_mcq_sha = sha256_file(mcq_f) if mcq_f.exists() else ""
            recorded_mcq = api_gen.get("mcq_output_sha", "")
            if recorded_mcq != actual_mcq_sha:
                issues.append(
                    f"api_generation.mcq_output_sha mismatch: "
                    f"recorded={str(recorded_mcq)[:16]}, actual={actual_mcq_sha[:16]} "
                    f"(current MCQs not generated by this chain)"
                )
            # P0-3/P0-4: prompt/config/script must equal the frozen canonical
            # values, and the run identity must be re-derived from canonical
            # sources. The distill_lib import is fail-closed: an inability to
            # import the canonical constants means provenance cannot be verified
            # at all, so we return issues immediately rather than falling back
            # to empty values (which would let forged SHAs pass).
            try:
                from scripts.distill_lib import (
                    canonical_prompt_sha256,
                    canonical_config_sha256,
                    FROZEN_MODEL_CONFIG as _FMC2,
                    VALID_TARGETS_BY_OPERATION as _VALID_TARGETS,
                    compute_code_sha,
                    ledger_code_files,
                )
            except Exception as e:
                issues.append(
                    f"cannot import canonical provenance constants from distill_lib: {e!r}"
                )
                return False, issues
            if api_gen.get("prompt_sha256") != canonical_prompt_sha256():
                issues.append(
                    "api_generation.prompt_sha256 mismatch: not the frozen canonical prompt"
                )
            if api_gen.get("config_sha256") != canonical_config_sha256():
                issues.append(
                    "api_generation.config_sha256 mismatch: not the frozen canonical config"
                )
            dl_script = scripts_dir / "distill_lib.py"
            if dl_script.exists():
                if api_gen.get("script_sha256") != hashlib.sha256(dl_script.read_bytes()).hexdigest():
                    issues.append(
                        "api_generation.script_sha256 mismatch: not the current distill_lib.py"
                    )
            # P0-3: re-derive code_sha from the canonical code scope (shared
            # with fill/regen) so it is authenticated, not trusted.
            rederived_code_sha = compute_code_sha(
                ledger_code_files(scripts_dir, scripts_dir.parent))
            # P0-4: rules output must match the published all_rules.json; rules
            # input must be consistent with whether rules were added.
            rules_f = p / "all_rules.json"
            if rules_f.exists():
                try:
                    rules_out = json.loads(rules_f.read_text(encoding="utf-8"))
                    rules_out_payload = json.dumps(
                        rules_out, sort_keys=True, ensure_ascii=False,
                        separators=(",", ":")).encode("utf-8")
                    expected_rules_out = hashlib.sha256(rules_out_payload).hexdigest()
                    if api_gen.get("rules_output_sha") != expected_rules_out:
                        issues.append(
                            "api_generation.rules_output_sha mismatch: not the current all_rules.json"
                        )
                    rules_input = api_gen.get("rules_input_sha", "")
                    if not (isinstance(rules_input, str) and len(rules_input) == 64):
                        issues.append("api_generation.rules_input_sha must be a 64-char SHA-256")
                    if api_gen.get("rules_added", 0) == 0 and rules_input != expected_rules_out:
                        issues.append(
                            "api_generation.rules_input_sha must equal rules_output_sha "
                            "when no rules were added"
                        )
                    # P0-4: when rules were added, rules_input_sha must be
                    # independently recomputable from the persisted
                    # rules_input_snapshot -- a bare 64-char string no longer
                    # suffices.
                    if api_gen.get("rules_added", 0) > 0:
                        snapshot = api_gen.get("rules_input_snapshot")
                        if not isinstance(snapshot, list):
                            issues.append(
                                "api_generation.rules_input_snapshot must be a list "
                                "when rules_added > 0"
                            )
                        else:
                            snap_payload = json.dumps(
                                snapshot, sort_keys=True, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8")
                            if hashlib.sha256(snap_payload).hexdigest() != rules_input:
                                issues.append(
                                    "api_generation.rules_input_sha does not match "
                                    "rules_input_snapshot (forged input SHA)"
                                )
                except Exception as e:
                    issues.append(f"could not verify api_generation rules SHAs: {e!r}")
            # P0-4: prove WHICH MCQs this run generated via per-ID canonical
            # record hashes. ID membership alone cannot distinguish a truly
            # generated MCQ from a pre-existing or content-replaced record with
            # the same id, so we require the exact canonical record SHA.
            gen_map = api_gen.get("generated_mcq_sha256_by_id")
            if gen_map is None:
                issues.append(
                    "api_generation.generated_mcq_sha256_by_id must be present")
            elif not isinstance(gen_map, dict):
                issues.append(
                    "api_generation.generated_mcq_sha256_by_id must be an object "
                    "(id -> canonical record SHA)")
            else:
                ids = list(gen_map)
                if not ids:
                    issues.append(
                        "api_generation.generated_mcq_sha256_by_id must be non-empty")
                empty_ids = [i for i in ids if not (isinstance(i, str) and i)]
                if empty_ids:
                    issues.append(
                        "api_generation.generated_mcq_sha256_by_id has empty/non-string ids")
                # dict keys are unique by construction; non-empty is enforced above.
                if api_gen.get("accepted", 0) != len(ids):
                    issues.append(
                        "api_generation.generated_mcq_sha256_by_id count != accepted")
                if mcq_lines:
                    # Scan the final file: reject any empty/missing id and any
                    # duplicate id (setdefault would silently hide duplicates).
                    by_id: dict = {}
                    empty_id_seen = False
                    dup_ids: list[str] = []
                    for l in mcq_lines:
                        if not l.strip():
                            continue
                        try:
                            rec = json.loads(l)
                        except Exception:
                            continue
                        if not isinstance(rec, dict):
                            continue
                        rid = rec.get("id")
                        if not (isinstance(rid, str) and rid):
                            empty_id_seen = True
                            continue
                        if rid in by_id:
                            dup_ids.append(rid)
                        else:
                            by_id[rid] = rec
                    if empty_id_seen:
                        issues.append(
                            "all_mcq.jsonl contains a record with empty/missing id")
                    if dup_ids:
                        issues.append(
                            f"all_mcq.jsonl contains duplicate ids: "
                            f"{sorted(set(dup_ids))[:5]}")
                    # P0-8/P0-9: pre-run checks must be driven by the FROZEN
                    # operation/mode in the archived run manifest, NOT by the
                    # unauthenticated api_generation.preserves_existing_mcqs flag
                    # (an attacker could flip it to False to skip the checks).
                    # The equality of api_generation.pre_run_mcq_ids vs the
                    # frozen set is ALWAYS enforced; whether the disjointness
                    # check runs is decided ONLY by the frozen operation.
                    rm = prov.get("run_manifest")
                    has_frozen = isinstance(rm, dict) and bool(rm.get("manifest_sha256"))
                    frozen_pre_run: object = None
                    frozen_op: object = None
                    frozen_preserves: object = None
                    if has_frozen:
                        rm_manifest = rm.get("manifest", {})
                        targets: object = None
                        input_files: object = None
                        if isinstance(rm_manifest, dict):
                            imm = rm_manifest.get("immutable", {})
                            if isinstance(imm, dict):
                                targets = imm.get("targets")
                                input_files = imm.get("input_files")
                        # A) Fail-closed: prove THIS book is an authorized target
                        # of the frozen run BEFORE trusting any book-level entry.
                        # A self-consistent archive that omits the current book
                        # from targets (or lists an un-authorized set) must not
                        # validate -- otherwise p.name is not bound to this run.
                        targets_ok = False
                        if not isinstance(targets, list):
                            issues.append(
                                "run_manifest.immutable.targets must be a list in "
                                "the archived run manifest")
                        elif not all(isinstance(t, str) and t for t in targets):
                            issues.append(
                                "run_manifest.immutable.targets entries must be "
                                "non-empty strings in the archived run manifest")
                        elif len(targets) != len(set(targets)):
                            issues.append(
                                "run_manifest.immutable.targets contains duplicates "
                                "in the archived run manifest")
                        elif p.name not in targets:
                            issues.append(
                                f"{p.name} is not listed in the frozen "
                                f"immutable.targets -- not an authorized target of "
                                f"this run")
                        elif not isinstance(input_files, dict) or \
                                set(input_files) != set(targets):
                            issues.append(
                                "run_manifest.immutable.input_files keys must "
                                "exactly match immutable.targets in the archived "
                                "run manifest")
                        else:
                            # A2) Validate EVERY frozen target entry, not just the
                            # current book. All targets participate in the run_id
                            # computation, so an empty / malformed / illegal entry
                            # on any other target must fail-closed (P0-13). The
                            # canonical producer writes pre_run_mcq_ids + a legal
                            # (operation, preserves) pair for EVERY target.
                            all_entries_ok = True
                            seen_modes: set = set()
                            for target in targets:
                                entry0 = input_files.get(target)
                                if not isinstance(entry0, dict):
                                    all_entries_ok = False
                                    issues.append(
                                        f"frozen immutable.input_files.{target} must "
                                        f"be an object in the archived run manifest")
                                    continue
                                if not isinstance(entry0.get("pre_run_mcq_ids"), list):
                                    all_entries_ok = False
                                    issues.append(
                                        f"frozen immutable.input_files.{target}.pre_run_mcq_ids "
                                        f"must be a list in the archived run manifest")
                                op0 = entry0.get("operation")
                                pr0 = entry0.get("preserves_existing_mcqs")
                                if op0 not in VALID_MODES:
                                    all_entries_ok = False
                                    issues.append(
                                        f"frozen operation {op0!r} for target {target!r} "
                                        f"must be one of {sorted(VALID_MODES)} in the "
                                        f"archived run manifest")
                                elif pr0 is not VALID_MODES[op0]:
                                    all_entries_ok = False
                                    issues.append(
                                        f"frozen preserves_existing_mcqs={pr0!r} for target "
                                        f"{target!r} does not match the legal mode for "
                                        f"operation={op0!r} in the archived run manifest")
                                if op0 in VALID_MODES:
                                    seen_modes.add(op0)
                                # Capture the current book's entry for the checks
                                # below (pre-run equality / overlap / provenance).
                                if target == p.name:
                                    frozen_pre_run = entry0.get("pre_run_mcq_ids")
                                    frozen_op = op0
                                    frozen_preserves = pr0
                            # A3) A single canonical run comes from exactly ONE
                            # producer, so every target must use the SAME
                            # (operation, preserves) mode. Mixed fill/regen
                            # manifests are forged and rejected.
                            if len(seen_modes) > 1:
                                all_entries_ok = False
                                issues.append(
                                    f"frozen targets mix incompatible operations "
                                    f"{sorted(seen_modes)} -- a single canonical run "
                                    f"must use one operation for all targets")
                            # A4) Every target must belong to the ALLOWED target
                            # set for the unified operation (P0-14). A field-complete
                            # but unknown target must not enter a frozen run.
                            _uni_op = frozen_op if frozen_op in VALID_MODES else None
                            if _uni_op is not None:
                                _allowed = _VALID_TARGETS.get(_uni_op, ())
                                for target in targets:
                                    if target not in _allowed:
                                        all_entries_ok = False
                                        issues.append(
                                            f"target {target!r} is not an allowed "
                                            f"target for operation {_uni_op!r} "
                                            f"(valid targets: {sorted(_allowed)})")
                            if all_entries_ok:
                                targets_ok = True
                        if targets_ok:
                            if not isinstance(frozen_pre_run, list):
                                issues.append(
                                    "archived run_manifest has no frozen "
                                    f"immutable.input_files.{p.name}.pre_run_mcq_ids list "
                                    "-- cannot prove the pre-run MCQ id set")
                            # B) The frozen (operation, preserves) pair must itself
                            # be a legal closed mode. A self-consistent illegal pair
                            # must be rejected even if provenance matches it exactly.
                            if frozen_op not in VALID_MODES:
                                issues.append(
                                    f"frozen operation {frozen_op!r} must be one of "
                                    f"{sorted(VALID_MODES)} in the archived run manifest "
                                    f"(missing or invalid frozen operation)")
                            elif frozen_preserves is not VALID_MODES[frozen_op]:
                                issues.append(
                                    f"frozen preserves_existing_mcqs={frozen_preserves!r} "
                                    f"does not match the legal mode for operation="
                                    f"{frozen_op!r} in the archived run manifest")
                            if isinstance(frozen_pre_run, list):
                                # C) ALWAYS: provenance pre-run ids == frozen set.
                                ag_ids = api_gen.get("pre_run_mcq_ids")
                                if not isinstance(ag_ids, list):
                                    issues.append(
                                        "api_generation.pre_run_mcq_ids must be a list")
                                elif ag_ids != frozen_pre_run:
                                    issues.append(
                                        "api_generation.pre_run_mcq_ids does not equal "
                                        "the frozen pre-run MCQ id set in the archived "
                                        "run manifest (forged/omitted pre-run ids)")
                                # D) Provenance operation/mode must match frozen.
                                if frozen_op is not None and api_gen.get("operation") != frozen_op:
                                    issues.append(
                                        "api_generation.operation does not equal the "
                                        "frozen operation in the archived run manifest "
                                        "(forged mode flag)")
                                if frozen_preserves is not None and \
                                        api_gen.get("preserves_existing_mcqs") != frozen_preserves:
                                    issues.append(
                                        "api_generation.preserves_existing_mcqs does not "
                                        "equal the frozen operation mode in the archived "
                                        "run manifest (forged mode flag)")
                                # E) Disjointness driven ONLY by the frozen operation.
                                if frozen_op == "fill":
                                    overlap = [i for i in gen_map if i in frozen_pre_run]
                                    if overlap:
                                        issues.append(
                                            f"generated_mcq_sha256_by_id overlaps frozen "
                                            f"pre-run mcq ids: {overlap[:5]} (reused old MCQ)")
                    for i, rec_sha in gen_map.items():
                        if not (isinstance(rec_sha, str) and len(rec_sha) == 64):
                            issues.append(
                                f"generated_mcq_sha256_by_id[{i!r}] not a 64-char SHA")
                        elif i not in by_id:
                            issues.append(
                                f"generated MCQ id {i!r} not found in all_mcq.jsonl")
                        elif mcq_record_sha256(by_id[i]) != rec_sha:
                            issues.append(
                                f"generated MCQ id {i!r} content does not match "
                                f"canonical record (replaced or reused with different content)")
            # P0-3: cross-check the run identity against the archived frozen run
            # manifest, RE-DERIVING rules_sha/code_sha/run_id from canonical
            # sources so a self-consistent tampering of both the archived
            # identity and api_generation is still detected.
            run_manifest = prov.get("run_manifest")
            vlevel = api_gen.get("verification_level")
            if isinstance(run_manifest, dict) and run_manifest.get("manifest_sha256"):
                # Formal artifact: an archived run manifest lets the identity be
                # independently re-derived, so verification_level must be "full".
                if vlevel != "full":
                    issues.append(
                        "api_generation.verification_level must be 'full' when "
                        "an archived run_manifest is present")
                rm_payload = json.dumps(
                    run_manifest.get("manifest", {}), ensure_ascii=False,
                    separators=(",", ":")).encode("utf-8")
                rm_actual_sha = hashlib.sha256(rm_payload).hexdigest()
                if rm_actual_sha != run_manifest.get("manifest_sha256"):
                    issues.append("provenance.run_manifest tampered (archived sha mismatch)")
                else:
                    # manifest authentic -> rules_sha == manifest sha; code_sha
                    # from the canonical code scope; run_id from the formula.
                    rederived_rules_sha = rm_actual_sha
                    rederived_run_id = hashlib.sha256(
                        (rederived_code_sha + ":" + rederived_rules_sha).encode("utf-8")
                    ).hexdigest()[:16]
                    # P0-14: the manifest's own frozen prompt/config SHAs are part
                    # of the run identity and must equal the canonical values AND
                    # the api_generation fields. Faking them and re-hashing the
                    # manifest must not pass.
                    _rm_imm = run_manifest.get("manifest", {}).get("immutable", {})
                    if isinstance(_rm_imm, dict):
                        _fp = _rm_imm.get("frozen_prompt_sha256")
                        _fc = _rm_imm.get("frozen_config_sha256")
                        if _fp != canonical_prompt_sha256():
                            issues.append(
                                "run_manifest.immutable.frozen_prompt_sha256 does not "
                                "match canonical prompt SHA (forged frozen prompt)")
                        if _fc != canonical_config_sha256():
                            issues.append(
                                "run_manifest.immutable.frozen_config_sha256 does not "
                                "match canonical config SHA (forged frozen config)")
                        if _fp != api_gen.get("prompt_sha256"):
                            issues.append(
                                "run_manifest.immutable.frozen_prompt_sha256 does not "
                                "match api_generation.prompt_sha256")
                        if _fc != api_gen.get("config_sha256"):
                            issues.append(
                                "run_manifest.immutable.frozen_config_sha256 does not "
                                "match api_generation.config_sha256")
                    else:
                        issues.append(
                            "run_manifest.immutable must be an object to cross-check "
                            "frozen prompt/config SHAs")
                    for fld, rval in (("rules_sha", rederived_rules_sha),
                                      ("code_sha", rederived_code_sha),
                                      ("run_id", rederived_run_id)):
                        if run_manifest.get(fld) != rval:
                            issues.append(
                                f"run_manifest.{fld} does not match re-derived value "
                                f"(forged archived identity)"
                            )
                        if api_gen.get(fld) != rval:
                            issues.append(
                                f"api_generation.{fld} does not match re-derived value"
                            )
            else:
                # No archived manifest: rule-input identity cannot be independently
                # re-derived. This is only acceptable as a PARTIAL verification
                # chain (direct function-call path); claiming "full" without a
                # manifest is a forged claim and fails fail-closed (Medium).
                if vlevel == "full":
                    issues.append(
                        "api_generation.verification_level='full' but no archived "
                        "run_manifest -- rule-input identity cannot be re-derived")
                elif vlevel != "partial":
                    issues.append(
                        "api_generation.verification_level must be 'partial' when "
                        "no archived run_manifest is present (missing or invalid "
                        "verification level)")
                # code_sha is still re-derived from the canonical code scope, and
                # run_id must be bound to it via the binding formula (P0-3).
                ag_rules_sha = api_gen.get("rules_sha", "")
                if not (isinstance(ag_rules_sha, str) and len(ag_rules_sha) == 64):
                    issues.append("api_generation.rules_sha must be a 64-char SHA-256")
                else:
                    expected_rid = hashlib.sha256(
                        (rederived_code_sha + ":" + ag_rules_sha).encode("utf-8")
                    ).hexdigest()[:16]
                    if api_gen.get("code_sha") != rederived_code_sha:
                        issues.append(
                            "api_generation.code_sha does not match re-derived canonical code_sha"
                        )
                    if api_gen.get("run_id") != expected_rid:
                        issues.append(
                            'api_generation.run_id does not match SHA(code_sha + ":" + rules_sha)'
                        )
            for k, v in _FMC2.items():
                if api_gen.get(k) != v:
                    issues.append(
                        f"api_generation.{k} not frozen: got {api_gen.get(k)!r}, "
                        f"expected {v!r}"
                    )
            if api_gen.get("completed") is not True:
                issues.append("api_generation.completed must be True")

    return (len(issues) == 0), issues


def verify_published_artifacts(
    book_dir: Path,
    baseline_dir: Path,
    scripts_dir: Path,
    git_root: Path | None,
    needs_regen: bool,
) -> tuple[bool, list[str]]:
    """Independent verification of published artifacts (P0-2, P0-3, P0-6).

    Designed to be called from a FRESH subprocess so that file readability,
    git-hashability, conservation, and provenance are all confirmed by a
    process that did not create the files.

    baseline_dir must contain _baseline_rules.json, _baseline_qrules.jsonl,
    _baseline_mcqs.jsonl, _baseline_qmcqs.jsonl written by the caller before
    spawning the subprocess.

    git_root=None skips git-dependent checks (git hash-object, baseline blob
    verification). This is the path used by tests that do not operate inside
    a real git repo. Production callers MUST pass a real git_root (P0-3).

    Returns (ok, issues).
    """
    import subprocess

    issues: list[str] = []
    names = (
        "all_rules.json", "quarantine_rules.jsonl", "all_mcq.jsonl",
        "quarantine_mcq.jsonl", "remediation_meta.json", "provenance.json",
    )

    # 1. Readable + JSON/JSONL parseable from this fresh process.
    for name in names:
        f = book_dir / name
        if not f.exists():
            issues.append(f"missing: {name}")
            continue
        try:
            data = f.read_bytes()
            if name.endswith(".json"):
                json.loads(data.decode("utf-8"))
            elif name.endswith(".jsonl"):
                for line in data.decode("utf-8").splitlines():
                    if line.strip():
                        json.loads(line)
        except Exception as e:
            issues.append(f"unreadable {name}: {e}")

    # 2. git hash-object succeeds for each file (Git can hash the published bytes).
    #    Skipped when git_root is None (non-git test environments).
    if git_root is not None:
        for name in names:
            f = book_dir / name
            if not f.exists():
                continue
            r = subprocess.run(
                ["git", "hash-object", str(f)],
                capture_output=True, text=True, encoding="utf-8", cwd=str(git_root),
            )
            if r.returncode != 0:
                issues.append(f"git hash-object failed {name}: {r.stderr.strip()}")

    # 3. Conservation: baseline (from baseline_dir) == published (from book_dir).
    try:
        old_rules = json.loads(
            (baseline_dir / "_baseline_rules.json").read_text(encoding="utf-8")
        )
        old_q_rules = [
            json.loads(l) for l in
            (baseline_dir / "_baseline_qrules.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        new_rules = json.loads((book_dir / "all_rules.json").read_text(encoding="utf-8"))
        new_q_rules = [
            json.loads(l) for l in
            (book_dir / "quarantine_rules.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        verify_conservation(old_rules, old_q_rules, new_rules, new_q_rules, rule_fp, "rules")
        # MCQ conservation is ALWAYS checked now: old MCQs are preserved
        # (moved to quarantine as legacy_unaudited), not regenerated in-place.
        old_mcqs = [
            json.loads(l) for l in
            (baseline_dir / "_baseline_mcqs.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        old_q_mcqs = [
            json.loads(l) for l in
            (baseline_dir / "_baseline_qmcqs.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        new_mcqs = [
            json.loads(l) for l in
            (book_dir / "all_mcq.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        new_q_mcqs = [
            json.loads(l) for l in
            (book_dir / "quarantine_mcq.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        verify_conservation(old_mcqs, old_q_mcqs, new_mcqs, new_q_mcqs, mcq_fp, "mcq")
    except ConservationError as e:
        issues.append(f"conservation: {e}")
    except Exception as e:
        issues.append(f"conservation: {e}")

    # 4. Provenance validates (with git_root so anchor_commit is re-checked).
    try:
        ok, prov_issues = validate_provenance(book_dir, scripts_dir, git_root=git_root)
        if not ok:
            issues.extend(prov_issues)
    except Exception as e:
        issues.append(f"provenance: {e}")

    return (len(issues) == 0), issues

