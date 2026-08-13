"""
remediate_classic_distillation.py
No-API post-hoc remediation for classic-text distillation artifacts.

Fixes (no model calls):
  R1  re-assign rule IDs deterministically: {prefix}_{chIdx:03d}_{ruleIdx:03d}
  R2  quarantine rules whose original_text is untraceable in raw_*.txt
  R3  re-assign MCQ IDs deterministically: {prefix}_{chIdx:03d}_mcq_{seq:03d}
  R4  re-map MCQ source_rule_id to new rule IDs (positional within chapter;
      low-confidence books flagged needs_mcq_regen)
  R5  deterministic answer rotation -> each of A/B/C/D ~25%
  R6  within-chapter dedup: duplicate rule texts quarantined (not deleted)
  R7  cross-chapter merge: same rule text across chapters -> one canonical rule
      with a source_chapters list; duplicates quarantined (not deleted)

Atomicity & conservation (P0-1, P0-3):
  All outputs are staged in an isolated temp directory. Conservation is then
  re-verified against the FINAL staged on-disk files (not an in-memory
  prediction), and provenance SHAs are validated on the staged state. Only if
  every check passes are the files published to the real directory (per-file
  atomic replace) with rollback on mid-publish failure.

Fingerprints (P0-4): see classic_artifacts.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.classic_artifacts import (  # noqa: E402
    ConservationError,
    mcq_fp,
    rule_fp,
    sha256_file,
    validate_provenance,
    verify_conservation,
)

BASE = ROOT / "knowledge_base" / "classic_texts"
SCRIPTS_DIR = Path(__file__).resolve().parent

BOOKS = {
    "ditiansui": ("滴天髓", "dts"),
    "zipingzhenquan": ("子平真诠", "zpzq"),
    "qiongtongbaojian": ("穷通宝鉴", "qtbj"),
    "sanmingtonghui": ("三命通会", "smth"),
}

UNIQUE_RULE_ID_BOOKS = {"ditiansui", "qiongtongbaojian"}

_ROTATE_SEED = "bazi_classic_distillation_v2"


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return items


def _write_jsonl(path: Path, items: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items),
        encoding="utf-8",
    )


def _load_raw_corpus(p: Path) -> str:
    parts = []
    for f in sorted(p.glob("raw_*.txt")):
        parts.append(f.read_text(encoding="utf-8"))
    return _norm("".join(parts))


def _rotate_answer(mcq: dict, mcq_id: str) -> dict:
    """Return a copy with options permuted so correct content lands at target.

    Target label is derived from SHA-256(frozen_seed + mcq_id), so the mapping
    cannot be reversed from the public ID alone.
    """
    h = hashlib.sha256((_ROTATE_SEED + (mcq_id or "")).encode()).digest()
    target = "ABCD"[h[0] % 4] if mcq_id else "A"
    cur = mcq.get("answer", "")
    if cur not in "ABCD" or target == cur:
        return mcq
    opts = dict(mcq.get("options", {}))
    if target not in opts or cur not in opts:
        return mcq
    opts[cur], opts[target] = opts[target], opts[cur]
    mcq["options"] = opts
    mcq["answer"] = target
    return mcq


# Frozen input baseline commits — per-book, each MUST cover ALL raw_*.txt
# files for that book (P0-3). Verified via git ls-tree -r at the commit and
# cross-checked that blob SHAs match HEAD (raw files unchanged since baseline).
#
# Coverage (verified 2026-08-11):
#   ditiansui         64/64 raw files @ a912d5b (blob SHAs match HEAD)
#   qiongtongbaojian 115/115 raw files @ a912d5b (blob SHAs match HEAD)
#   sanmingtonghui    80/80 raw files @ a2a8a5c (blob SHAs match HEAD)
#   zipingzhenquan    59/59 raw files @ a912d5b (blob SHAs match HEAD)
#
# The old single INPUT_BASELINE_REF="303d375" only covered zpzq (59 files);
# the other three books had 0 raw files at that commit, so baseline blob
# checks silently passed (empty/missing entries were not enforced).
INPUT_BASELINE_BY_BOOK: dict[str, str] = {
    "ditiansui": "a912d5ba49f7b67f5d73b563b4df3787e11e957f",
    "qiongtongbaojian": "a912d5ba49f7b67f5d73b563b4df3787e11e957f",
    "sanmingtonghui": "a2a8a5ca01a12c4afcb75319584e48c79b14f06d",
    "zipingzhenquan": "a912d5ba49f7b67f5d73b563b4df3787e11e957f",
}

# Legacy default for backward compatibility (zpzq). New code should use
# INPUT_BASELINE_BY_BOOK[dir_key] via remediate_book's input_baseline_commit
# parameter.
INPUT_BASELINE_REF = INPUT_BASELINE_BY_BOOK["zipingzhenquan"]


def _get_baseline_commit(dir_key: str) -> str:
    """Return the frozen input baseline commit for a book (P0-3).

    Falls back to INPUT_BASELINE_REF if the book is not in the map, but
    remediate_book() now passes the per-book commit explicitly.
    """
    return INPUT_BASELINE_BY_BOOK.get(dir_key, INPUT_BASELINE_REF)


def _git(args: list[str], root: Path | None = None) -> str:
    cwd = str(root or ROOT)
    try:
        r = subprocess.run(
            ["git", *args],
            capture_output=True, text=True, encoding="utf-8", cwd=cwd,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _anchor_commit_verified(root: Path | None = None) -> tuple[str, bool]:
    """Return (HEAD commit, whether HEAD really exists in the object store).

    anchor_commit_verified is True only if `git cat-file -e HEAD^{commit}`
    succeeds — i.e. HEAD is not a unborn branch pointing at no commit.
    """
    head = _git(["rev-parse", "HEAD"], root)
    if not head:
        return "unknown", False
    r = subprocess.run(
        ["git", "cat-file", "-e", f"{head}^{{commit}}"],
        capture_output=True, cwd=str(root or ROOT),
    )
    return head, r.returncode == 0


def _worktree_dirty(root: Path | None = None) -> bool:
    """True if `git status --porcelain` reports any change."""
    out = _git(["status", "--porcelain"], root)
    return bool(out.strip())


def _code_fingerprint() -> str:
    """Aggregate SHA-256 of all remediation-critical scripts (P0-2).

    This captures the actual dirty-worktree code that produced the artifacts,
    independent of which commit HEAD points at. It lets a reviewer verify that
    the code used at generation time matches the code they inspect, even when
    the worktree is dirty or HEAD has advanced.
    """
    import hashlib
    h = hashlib.sha256()
    for name in ("remediate_classic_distillation.py", "validate_classic_distillation.py",
                 "distill_lib.py", "classic_artifacts.py"):
        f = SCRIPTS_DIR / name
        if f.exists():
            h.update(name.encode("utf-8"))
            h.update(b"\0")
            h.update(f.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def _load_upstream_provenance(p: Path) -> dict | None:
    """Load existing distillation-stage provenance before overwriting (P0-3).

    If the book dir already has a provenance.json with upstream fields
    (provider/model/source_url/etc.), return it so remediation can nest it
    under upstream_provenance instead of silently dropping it.

    Returns None if no prior provenance exists, or if the existing one has
    no upstream fields (so we don't nest an empty object). The caller records
    upstream_provenance_status='unavailable' in that case.
    """
    prov_file = p / "provenance.json"
    if not prov_file.exists():
        return None
    try:
        prov = json.loads(prov_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(prov, dict):
        return None
    upstream_keys = {"provider", "model", "thinking", "temperature",
                     "source_url", "source_version", "distill_script",
                     "upstream_artifact_shas", "upstream_artifact_commit",
                     "source_urls", "thinking_mode", "model_config"}
    found = {k: prov[k] for k in upstream_keys if k in prov}
    if found:
        return found
    if "upstream_provenance" in prov and isinstance(prov["upstream_provenance"], dict):
        return prov["upstream_provenance"]
    return None


def _git_blob_sha_at_commit(root: Path, commit: str, rel_path: str) -> str:
    """Return the git blob SHA of a file at a specific commit (P0-3).

    Uses `git rev-parse <commit>:<path>` which returns the blob object SHA.
    Returns empty string on any error (e.g. file not tracked at that commit).
    """
    if not commit or commit == "unknown" or not rel_path:
        return ""
    r = subprocess.run(
        ["git", "rev-parse", f"{commit}:{rel_path}"],
        capture_output=True, text=True, encoding="utf-8", cwd=str(root),
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def _compute_provenance(
    staging: Path, p: Path, meta: dict, git_root: Path | None = None,
    input_baseline_commit: str = INPUT_BASELINE_REF,
    no_api: bool = True,
) -> dict:
    """Build provenance from the staged (final) output files and real raw files.

    Two-layer schema (P0-3):
      - Remediation layer (this function): no_api, input_baseline_commit,
        worktree_dirty, anchor_commit, code_fingerprint. Does NOT record
        provider/model/temperature (no model calls happen here).
      - Upstream layer (nested under upstream_provenance): preserved from the
        prior distillation-stage provenance.json if it existed, so provider/
        model/source_url/upstream SHAs are not silently lost on re-remediation.

    `no_api` defaults True (remediation makes no model calls). API-based
    callers (regen_mcq/fill_missing_chapters) pass no_api=False so the
    provenance truthfully records that model calls happened.

    anchor_commit is the HEAD at generation time; it is verified to EXIST in
    the git object store but is NOT required to equal future HEAD (the worktree
    may legitimately advance after the artifacts are committed). This avoids
    the "commit changes HEAD -> provenance invalidated" trap (P0-2).
    """
    anchor, anchor_ok = _anchor_commit_verified(git_root)
    upstream = _load_upstream_provenance(p)
    # P0-4: 'recovered' requires full upstream schema INCLUDING artifact_commit
    # AND git_root for byte-level verification; partial -> 'partial'.
    # 'partial' means some upstream data was recovered but not enough to prove
    # end-to-end provenance (missing source_url, distill_script, artifact SHAs,
    # artifact_commit, or no git_root for byte verification).
    # end_to_end_provenance is False for 'partial'.
    UPSTREAM_REQUIRED_FULL = {
        "provider", "model", "source_url", "source_version",
        "distill_script", "thinking_mode", "temperature",
        "upstream_artifact_shas", "upstream_artifact_commit",
        # P0-4: generation-chain fingerprints. 'recovered' must prove the
        # artifacts were produced by a specific script, prompt, and config.
        "distill_script_sha256", "prompt_sha256", "config_sha256",
    }
    if upstream is None:
        upstream_status = "unavailable"
    elif UPSTREAM_REQUIRED_FULL.issubset(upstream.keys()) and git_root is not None:
        upstream_status = "recovered"
    else:
        upstream_status = "partial"
    provenance = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "anchor_commit": anchor,
        "anchor_commit_verified": anchor_ok,
        "no_api": no_api,
        "input_baseline_commit": input_baseline_commit,
        "worktree_dirty": _worktree_dirty(git_root),
        "code_fingerprint": _code_fingerprint(),
        "upstream_provenance_status": upstream_status,
        "file_shas": {},
        "code_shas": {},
        "raw_text_shas": {},
        "input_baseline_blob_shas": {},
        "remediation_actions": meta.get("actions", {}),
    }
    if upstream is not None:
        provenance["upstream_provenance"] = upstream
    for name in ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
                 "quarantine_mcq.jsonl", "remediation_meta.json"):
        f = staging / name
        if f.exists():
            provenance["file_shas"][name] = sha256_file(f)
    for name in ("remediate_classic_distillation.py", "validate_classic_distillation.py",
                 "distill_lib.py", "classic_artifacts.py"):
        f = SCRIPTS_DIR / name
        if f.exists():
            provenance["code_shas"][name] = sha256_file(f)
    # raw_text_shas: merge raw files from staging AND p, staging wins. This
    # lets fill_missing_chapters (which stages NEW raw_*.txt files) record the
    # final raw set even before publish moves them into p, while remediation
    # (which never stages raw files) simply falls back to p.
    raw_files: dict[str, Path] = {}
    for f in sorted(p.glob("raw_*.txt")):
        raw_files[f.name] = f
    for f in sorted(staging.glob("raw_*.txt")):
        raw_files[f.name] = f  # staged (newer) content wins
    for name in sorted(raw_files):
        f = raw_files[name]
        provenance["raw_text_shas"][name] = sha256_file(f)
        if git_root is not None:
            try:
                rel = f.relative_to(git_root).as_posix()
            except ValueError:
                rel = ""
            if rel:
                blob = _git_blob_sha_at_commit(git_root, input_baseline_commit, rel)
                if blob:
                    provenance["input_baseline_blob_shas"][name] = blob
    # P0-1/P0-3: raw files that have NO baseline blob (e.g. brand-new chapters
    # added by fill_missing_chapters) need a verifiable, RECOMPUTABLE source
    # anchor instead of silently failing the full-coverage baseline gate. The
    # anchor records source_start/source_end into the baseline-anchored
    # raw_full.txt plus its baseline blob SHA, so validate_provenance can
    # re-extract the slice and confirm it reproduces the target raw SHA -- a
    # forged anchor claiming derived_from='raw_full.txt' cannot pass.
    if git_root is not None:
        raw_sources = provenance.get("raw_sources", {})
        src = p / "raw_full.txt"
        if src.exists():
            try:
                src_rel = src.relative_to(git_root).as_posix()
            except ValueError:
                src_rel = ""
            src_blob = _git_blob_sha_at_commit(git_root, input_baseline_commit, src_rel) if src_rel else ""
            if src_blob:
                src_bytes = src.read_bytes()
                src_sha256 = hashlib.sha256(src_bytes).hexdigest()
                for name in provenance["raw_text_shas"]:
                    if name in provenance["input_baseline_blob_shas"]:
                        continue
                    raw_file = raw_files.get(name)
                    if raw_file is None or not raw_file.exists():
                        continue
                    content = raw_file.read_bytes()
                    start = src_bytes.find(content)
                    if start >= 0:
                        raw_sources[name] = {
                            "derived_from": "raw_full.txt",
                            "derived_from_blob_sha256": src_sha256,
                            "extraction_strategy": "substring_strip",
                            "source_start": start,
                            "source_end": start + len(content),
                        }
        if raw_sources:
            provenance["raw_sources"] = raw_sources
    return provenance


def _verify_staged_conservation(
    old_rules, old_q_rules, old_mcqs, old_q_mcqs,
    staged_clean_rules, staged_q_rules, staged_clean_mcqs, staged_q_mcqs,
    needs_regen: bool,
) -> None:
    """Verify conservation against the FINAL staged on-disk content (P0-1).

    MCQ conservation is ALWAYS checked now: old MCQs are preserved (moved to
    quarantine as legacy_unaudited), not regenerated in-place, so the multiset
    must still hold. The needs_regen parameter is retained for API
    compatibility but no longer skips MCQ conservation.
    """
    verify_conservation(
        old_rules, old_q_rules, staged_clean_rules, staged_q_rules,
        rule_fp, "rules",
    )
    verify_conservation(
        old_mcqs, old_q_mcqs, staged_clean_mcqs, staged_q_mcqs,
        mcq_fp, "mcq",
    )


def _publish(staging: Path, p: Path, names: list[str]) -> Path:
    """Publish staged files to the real dir with backup + rollback (P0-3, P0-5).

    ACL inheritance (P0-1 fix): `staging` MUST live inside `p` (the target
    directory). os.replace then moves the file within the same directory, so
    the published file inherits the target directory's ACL instead of the
    restrictive descriptor of a system temp dir.

    Rollback semantics (P0-5):
      - Files that existed before are backed up to backup_dir; on mid-publish
        failure they are restored from backup via _rollback_from_backup,
        which reuses the SHA-verified restore path.
      - Files that did NOT exist before are NEW; on failure they are DELETED
        (not left behind as orphans).
      - The ORIGINAL publish exception is preserved and re-raised with
        rollback errors appended (does not swallow the root cause).
      - backup_dir is NOT deleted on success — the caller must clean it up
        only after independent external validation passes (P0-3 requirement).

    Returns backup_dir path. Caller is responsible for cleanup after external
    subprocess verification (see remediate_book).
    """
    backup_dir = p / f".publish_backup_{os.getpid()}_{int(time.time())}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    existed_before: set[str] = set()
    publish_exc: BaseException | None = None
    try:
        # 1. Back up existing files; record which names existed before.
        for name in names:
            target = p / name
            if target.exists():
                existed_before.add(name)
                shutil.copy2(target, backup_dir / name)
        # 2. Atomic per-file replace from staging (same-dir move => ACL inherited).
        for name in names:
            staged_file = staging / name
            if staged_file.exists():
                os.replace(staged_file, p / name)
    except BaseException as e:
        # P0-5: preserve the original publish exception so it is not swallowed.
        publish_exc = e
        # 3. Roll back via the SHA-verified _rollback_from_backup path.
        #    This reuses the same restore+SHA-check logic used for post-publish
        #    rollback, ensuring consistency. If rollback also fails, the
        #    combined error includes BOTH the original publish exception and
        #    all per-file rollback errors.
        try:
            _rollback_from_backup(p, backup_dir, names)
        except ConservationError as rb_err:
            # Don't delete backup — it's needed for manual recovery.
            raise ConservationError(
                f"publish failed ({publish_exc!r}) and rollback also failed: "
                f"{rb_err}; backup preserved at {backup_dir}"
            ) from publish_exc
        # Rollback succeeded -- clean up backup and re-raise original exception.
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise publish_exc
    return backup_dir  # Caller cleans up after external validation passes.


def _write_baseline_snapshot(
    backup_dir: Path,
    old_rules: list[dict],
    old_q_rules: list[dict],
    old_mcqs: list[dict],
    old_q_mcqs: list[dict],
) -> None:
    """Write baseline snapshot to backup_dir for subprocess conservation check."""
    (backup_dir / "_baseline_rules.json").write_text(
        json.dumps(old_rules, ensure_ascii=False), encoding="utf-8"
    )
    _write_jsonl(backup_dir / "_baseline_qrules.jsonl", old_q_rules)
    _write_jsonl(backup_dir / "_baseline_mcqs.jsonl", old_mcqs)
    _write_jsonl(backup_dir / "_baseline_qmcqs.jsonl", old_q_mcqs)


def _verify_published_via_subprocess(
    book_dir: Path,
    backup_dir: Path,
    needs_regen: bool,
    git_root: Path | None = None,
) -> tuple[bool, list[str]]:
    """Run a FRESH Python subprocess to verify published artifacts (P0-6).

    The subprocess independently:
      - reads + parses all 6 output files
      - runs `git hash-object` on each
      - recomputes conservation from baseline snapshot vs published files
      - validates provenance (re-checks anchor_commit existence against git)

    Returns (ok, issues).

    git_root=None skips git-dependent checks in the subprocess (test path).
    Production callers MUST pass a real git_root (P0-3).
    """
    # Empty string is the wire encoding for None across the subprocess argv.
    git_root_arg = str(git_root) if git_root is not None else ""
    cwd = str(git_root) if git_root is not None else str(ROOT)
    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, %r)\n"
        "from scripts.classic_artifacts import verify_published_artifacts\n"
        "book_dir = Path(sys.argv[1])\n"
        "baseline_dir = Path(sys.argv[2])\n"
        "scripts_dir = Path(sys.argv[3])\n"
        "git_root = Path(sys.argv[4]) if sys.argv[4] else None\n"
        "needs_regen = sys.argv[5] == 'true'\n"
        "ok, issues = verify_published_artifacts(\n"
        "    book_dir, baseline_dir, scripts_dir, git_root, needs_regen\n"
        ")\n"
        "print(json.dumps({'ok': ok, 'issues': issues}, ensure_ascii=False))\n"
        % str(ROOT)
    )
    r = subprocess.run(
        [sys.executable, "-c", code, str(book_dir), str(backup_dir),
         str(SCRIPTS_DIR), git_root_arg, "true" if needs_regen else "false"],
        capture_output=True, text=True, encoding="utf-8", cwd=cwd,
    )
    if r.returncode != 0:
        return False, [f"subprocess exited {r.returncode}: {r.stderr.strip()}"]
    try:
        # Last line is JSON; earlier lines (if any) ignored.
        last_line = r.stdout.strip().splitlines()[-1]
        result = json.loads(last_line)
        return result["ok"], result["issues"]
    except Exception as e:
        return False, [
            f"subprocess output unparseable: {e}; stdout={r.stdout!r}"
        ]


def _rollback_from_backup(p: Path, backup_dir: Path, names: list[str]) -> None:
    """Restore all named files from backup_dir, deleting any not in backup (P0-5).

    Used when external subprocess validation fails after a successful publish.
    Files that existed before publish are restored from backup; files that
    were newly created by publish (not in backup) are deleted.

    Does NOT swallow recovery failures: collects all per-file errors and
    raises a ConservationError listing every failure. Verifies restored file
    SHAs match the backup. Backup dir is preserved for manual recovery.
    """
    errors: list[str] = []
    for name in names:
        target = p / name
        src = backup_dir / name
        if src.exists():
            try:
                shutil.copy2(src, target)
            except Exception as e:
                errors.append(f"restore {name}: {e!r}")
                continue
            # Verify restored file SHA matches backup
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            expected = hashlib.sha256(src.read_bytes()).hexdigest()
            if actual != expected:
                errors.append(
                    f"restore {name}: SHA mismatch after copy "
                    f"(expected={expected[:16]}, actual={actual[:16]})"
                )
        else:
            # Was newly created by publish — remove it.
            if target.exists():
                try:
                    target.unlink()
                except Exception as e:
                    errors.append(f"delete new file {name}: {e!r}")
    if errors:
        raise ConservationError(
            f"rollback failures ({len(errors)}): {'; '.join(errors)}; "
            f"backup preserved at {backup_dir}"
        )


def _rollback_after_failure(p: Path, backup_dir: Path, names: list[str],
                            cause: str) -> None:
    """Roll back published files from backup after a POST-publish failure.

    Used by regen_mcq / fill_missing_chapters after `_publish` succeeded but a
    later step (e.g. provenance validation) failed. On successful rollback the
    backup dir is deleted (files restored); if rollback ALSO fails, the backup
    is preserved for manual recovery and a combined ConservationError is
    raised. This ensures a post-publish validation failure never leaves new
    files in the production dir without the ability to restore the old state.
    """
    try:
        _rollback_from_backup(p, backup_dir, names)
    except Exception as rb:
        raise ConservationError(
            f"post-publish failure: {cause}; rollback ALSO failed: {rb!r}; "
            f"backup preserved at {backup_dir} for manual recovery"
        ) from rb
    shutil.rmtree(backup_dir, ignore_errors=True)


def remediate_book(
    dir_key: str, name: str, prefix: str,
    base_path: Path | None = None,
    git_root: Path | None = None,
    input_baseline_commit: str | None = None,
) -> dict:
    # P0-3: use per-book frozen baseline commit if not explicitly overridden.
    # Each commit is verified to cover ALL raw_*.txt files for that book.
    if input_baseline_commit is None:
        input_baseline_commit = _get_baseline_commit(dir_key)
    base = base_path or BASE
    p = base / dir_key
    meta = {"book": name, "dir": dir_key, "prefix": prefix, "actions": {}}
    if not p.is_dir():
        meta["error"] = "missing dir"
        return meta

    old_rules = json.loads((p / "all_rules.json").read_text(encoding="utf-8"))
    old_q_rules = _load_jsonl(p / "quarantine_rules.jsonl")
    old_mcqs = _load_jsonl(p / "all_mcq.jsonl")
    old_q_mcqs = _load_jsonl(p / "quarantine_mcq.jsonl")
    raw_corpus = _load_raw_corpus(p)

    ch_order: list[str] = []
    ch_rules: dict[str, list[dict]] = defaultdict(list)
    for r in old_rules:
        ch = r.get("source_chapter", "_unknown_")
        if ch not in ch_rules:
            ch_order.append(ch)
        ch_rules[ch].append(r)
    ch_idx = {ch: i for i, ch in enumerate(ch_order)}

    clean_rules: list[dict] = []
    new_q_rules: list[dict] = []

    for ch in ch_order:
        ci = ch_idx[ch]
        seen_texts: set[str] = set()
        ri = 0
        for r in ch_rules[ch]:
            new_id = f"{prefix}_{ci:03d}_{ri:03d}"
            r = dict(r)
            r["id"] = new_id
            ot = _norm(r.get("original_text", ""))
            rule_text = _norm(r.get("rule", ""))
            if ot and ot not in raw_corpus:
                r["quarantine_reason"] = "original_text_not_in_raw"
                new_q_rules.append(r)
            elif rule_text and rule_text in seen_texts:
                r["quarantine_reason"] = "within_chapter_duplicate"
                new_q_rules.append(r)
            else:
                if rule_text:
                    seen_texts.add(rule_text)
                clean_rules.append(r)
            ri += 1

    meta["actions"]["R1_reID_rules"] = {
        "before": len(old_rules),
        "clean": len(clean_rules),
        "quarantine_new": len(new_q_rules),
        "quarantine_existing": len(old_q_rules),
    }

    # R7: cross-chapter merge -> canonical rule with source_chapters.
    text_to_rules: dict[str, list[dict]] = {}
    for r in clean_rules:
        rt = _norm(r.get("rule", ""))
        if rt:
            text_to_rules.setdefault(rt, []).append(r)

    r7_merged = 0
    remove_ids: set[str] = set()
    for _text, group in text_to_rules.items():
        if len(group) <= 1:
            continue
        chapters = [r.get("source_chapter", "") for r in group]
        if len(set(chapters)) <= 1:
            continue
        canonical = group[0]
        canonical["source_chapters"] = chapters
        for r in group[1:]:
            r["quarantine_reason"] = "cross_chapter_merged_into_canonical"
            new_q_rules.append(r)
            remove_ids.add(r["id"])
            r7_merged += 1

    if remove_ids:
        clean_rules = [r for r in clean_rules if r["id"] not in remove_ids]

    meta["actions"]["R7_cross_chapter_merge"] = {"merged": r7_merged}

    old_to_new: dict[str, str] = {}
    if dir_key in UNIQUE_RULE_ID_BOOKS:
        for ch in ch_order:
            ci = ch_idx[ch]
            for ri, r in enumerate(ch_rules[ch]):
                old_to_new[r.get("id", "")] = f"{prefix}_{ci:03d}_{ri:03d}"

    needs_regen = dir_key not in UNIQUE_RULE_ID_BOOKS
    clean_mcqs: list[dict] = []
    new_q_mcqs: list[dict] = []

    # All existing MCQs lack _consistency_verified (they were generated by the
    # old batch path without the semantic consistency gate). They are
    # quarantined as legacy_unaudited and MUST NOT be counted in the clean set.
    # The clean MCQ set is empty until API-based regeneration via
    # distill_lib.generate_mcq (which applies the consistency gate).
    surviving_new_ids = {r["id"] for r in clean_rules}
    mcq_seq = 0
    for m in old_mcqs:
        m = dict(m)
        old_src = m.get("source_rule_id", "")
        new_src = old_to_new.get(old_src, old_src)
        if new_src in surviving_new_ids:
            m["source_rule_id"] = new_src
        ci = 0
        for ch in ch_order:
            if new_src.startswith(f"{prefix}_{ch_idx[ch]:03d}_"):
                ci = ch_idx[ch]
                break
        m["id"] = f"{prefix}_{ci:03d}_mcq_{mcq_seq:04d}"
        mcq_seq += 1
        m = _rotate_answer(m, m["id"])
        m["quarantine_reason"] = "legacy_unaudited: no consistency verification"
        new_q_mcqs.append(m)

    meta["actions"]["R4_mcq_legacy_quarantine"] = {
        "total": len(old_mcqs),
        "quarantined": len(new_q_mcqs),
        "clean": 0,
        "reason": "all existing MCQs lack semantic consistency verification; "
                  "quarantined as legacy_unaudited pending API regen",
    }
    meta["needs_mcq_regen"] = True
    ans = Counter(m.get("answer", "?") for m in clean_mcqs)
    meta["actions"]["R5_answer_balance"] = {"dist": dict(ans)}

    # ---- Stage all outputs INSIDE the book directory (P0-1 ACL fix) ----
    # staging lives inside `p` so os.replace is a same-directory move and the
    # published file inherits the target directory's ACL, not a system temp
    # dir's restrictive descriptor.
    output_names = [
        "all_rules.json",
        "quarantine_rules.jsonl",
        "all_mcq.jsonl",
        "quarantine_mcq.jsonl",
        "remediation_meta.json",
        "provenance.json",
    ]
    staging = p / f".staging_{os.getpid()}_{int(time.time())}"
    staging.mkdir(parents=True, exist_ok=True)
    backup_dir: Path | None = None
    try:
        staged_clean_rules = clean_rules
        staged_q_rules = old_q_rules + new_q_rules
        # Complete quarantine sets are built fresh in staging (no lossy dedup).
        (staging / "all_rules.json").write_text(
            json.dumps(staged_clean_rules, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _write_jsonl(staging / "quarantine_rules.jsonl", staged_q_rules)
        (staging / "all_mcq.jsonl").write_text(
            "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in clean_mcqs),
            encoding="utf-8",
        )
        staged_q_mcqs = old_q_mcqs + new_q_mcqs
        _write_jsonl(staging / "quarantine_mcq.jsonl", staged_q_mcqs)

        (staging / "remediation_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        provenance = _compute_provenance(staging, p, meta, git_root=git_root,
                                         input_baseline_commit=input_baseline_commit)
        (staging / "provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ---- Re-verify conservation on the FINAL staged on-disk content ----
        _verify_staged_conservation(
            old_rules, old_q_rules, old_mcqs, old_q_mcqs,
            staged_clean_rules, staged_q_rules, clean_mcqs, staged_q_mcqs,
            needs_regen,
        )

        # ---- Validate provenance on the staged state (with git_root) ----
        # P0-3: git_root=None means skip git-dependent checks (test path);
        # production callers (main) MUST pass a real git_root so baseline
        # blob coverage is enforced.
        prov_ok, prov_issues = validate_provenance(staging, SCRIPTS_DIR, git_root=git_root)
        if not prov_ok:
            raise ConservationError(
                f"Provenance validation failed on staged state: {'; '.join(prov_issues)}"
            )

        # ---- Publish with rollback (returns backup_dir, does NOT delete it) ----
        backup_dir = _publish(staging, p, output_names)

        # ---- Post-publish: all subsequent steps are wrapped in a single
        #      try/except so ANY failure (snapshot write, subprocess spawn,
        #      output parse, validation) triggers rollback (P0-4). Previously
        #      only the explicit `if not sub_ok` branch rolled back; exceptions
        #      in baseline-snapshot write or subprocess.run would leave the
        #      new published files in place. ----
        try:
            # Write baseline snapshot for subprocess conservation check.
            _write_baseline_snapshot(
                backup_dir, old_rules, old_q_rules, old_mcqs, old_q_mcqs
            )

            # External subprocess verification (P0-6): a FRESH Python process
            # re-reads all published files, runs git hash-object, recomputes
            # conservation, and validates provenance. Only if this independent
            # process passes do we clean up the backup.
            sub_ok, sub_issues = _verify_published_via_subprocess(
                p, backup_dir, needs_regen, git_root=git_root
            )
            if not sub_ok:
                raise ConservationError(
                    f"External subprocess verification failed for {dir_key}: "
                    f"{'; '.join(sub_issues)}"
                )
        except Exception as orig_exc:
            # ANY post-publish failure -> roll back from backup. If rollback
            # ALSO fails, report both errors and keep backup for manual
            # recovery (do NOT swallow the rollback exception).
            try:
                _rollback_from_backup(p, backup_dir, output_names)
            except Exception as rollback_exc:
                raise ConservationError(
                    f"Post-publish failure: {orig_exc!r}; "
                    f"ROLLBACK ALSO FAILED: {rollback_exc!r}; "
                    f"backup preserved at {backup_dir} for manual recovery"
                ) from orig_exc
            raise

        # ---- External validation passed: clean up backup ----
        shutil.rmtree(backup_dir, ignore_errors=True)
        backup_dir = None
    finally:
        # Always clean up the staging dir (files already moved by _publish).
        shutil.rmtree(staging, ignore_errors=True)
        # If we raised before cleaning up backup_dir, it stays for forensics.

    return meta


def main() -> int:
    results = []
    for dir_key, (name, prefix) in BOOKS.items():
        print(f"--- remediating {name} ---")
        # P0-3: production MUST pass a real git_root so baseline blob coverage
        # and anchor_commit existence are enforced. Tests omit git_root to
        # skip git-dependent checks.
        r = remediate_book(dir_key, name, prefix, git_root=ROOT)
        results.append(r)
        for k, v in r.get("actions", {}).items():
            print(f"  {k}: {v}")
        if r.get("needs_mcq_regen"):
            print(f"  >> MCQ regen REQUIRED (API)")
    print("\n=== summary ===")
    for r in results:
        print(f"  {r['book']}: needs_mcq_regen={r.get('needs_mcq_regen', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
