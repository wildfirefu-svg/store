"""
regen_mcq.py
Regenerate MCQ for books flagged needs_mcq_regen, using corrected distill_lib.
Reads existing re-IDed all_rules.json, regenerates MCQ per chapter with proper
source_rule_id linkage + deterministic answer rotation.

Usage: python scripts/regen_mcq.py [book_dir_key ...]
Default: all books with remediation_meta.needs_mcq_regen == True
"""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import distill_lib as dl
import scripts.remediate_classic_distillation as rc
from scripts.classic_artifacts import (  # noqa: E402
    ConservationError,
    mcq_record_sha256,
    validate_provenance,
)

BASE = ROOT / "knowledge_base" / "classic_texts"
SCRIPTS_DIR = Path(__file__).resolve().parent

# Code files whose SHA-256 fingerprints a regen run's ledger identity (P0-1).
# A single canonical scope shared with fill and the validator so code_sha can
# be independently re-derived (P0-3).
_LEDGER_CODE_FILES = dl.ledger_code_files(SCRIPTS_DIR, ROOT)
# Files whose SHAs a prepared/completed book receipt binds (P0-2). These are the
# outputs the run actually rewrites; they must exist in staging (prepared) and
# in the published book dir (completed) so a resume can re-verify them.
_RECEIPT_OUTPUT_NAMES = ("all_mcq.jsonl", "quarantine_mcq.jsonl", "remediation_meta.json")
BOOKS = {
    "zipingzhenquan": ("子平真诠", "zpzq"),
    "sanmingtonghui": ("三命通会", "smth"),
    "qiongtongbaojian": ("穷通宝鉴", "qtbj"),
    "ditiansui": ("滴天髓", "dts"),
}


def regen_book(dir_key: str, global_budget: int = 10000,
               ledger_path: Path | None = None,
               git_root: Path | None = None,
               run_id: str = "",
               code_sha: str = "",
               rules_sha: str = "",
               manifest_path: Path | None = None) -> dict:
    name, prefix = BOOKS[dir_key]
    p = BASE / dir_key
    meta_f = p / "remediation_meta.json"
    # P0-2: skip is decided by the run manifest's per-book state (main() only
    # calls pending books). As a defense-in-depth here, a book whose MCQs are
    # already complete is never re-generated -- the old sys.argv.count()
    # heuristic is gone because an explicit-target resume must not re-run a
    # completed book.
    if meta_f.exists():
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
        if not meta.get("needs_mcq_regen", False):
            print(f"[{name}] skip (already clean)")
            return {"book": name, "skipped": True}

    rules = json.loads((p / "all_rules.json").read_text(encoding="utf-8"))
    ch_groups: dict[str, list[dict]] = defaultdict(list)
    ch_order: list[str] = []
    for r in rules:
        ch = r.get("source_chapter", "_unknown_")
        if ch not in ch_groups:
            ch_order.append(ch)
        ch_groups[ch].append(r)

    # P0-1/P0-2: Run-level shared budget ledger with frozen global hard cap AND
    # a frozen run identity (run_id/code_sha/rules_sha). The identity is
    # computed ONCE at the CLI (main) level over all target books, so all books
    # in one run share the SAME ledger file and budget. A resume of the SAME
    # run reuses the budget while a different run is rejected (fail-closed).
    ledger = dl.BudgetLedger.load_or_create(
        ledger_path, global_budget,
        run_id=run_id, code_sha=code_sha, rules_sha=rules_sha)
    # Medium: snapshot the SHARED ledger so api_generation records THIS book's
    # call delta, not the cross-book cumulative total.
    _calls_before = ledger.calls_made
    _accepted_before = ledger.accepted
    _skipped_before = ledger.skipped
    all_mcqs: list[dict] = []
    quarantined: list[dict] = []
    total_ch = len(ch_order)
    incomplete = False
    ci = -1  # so the fail-closed branch works even if ch_order is empty

    for ci, ch in enumerate(ch_order):
        ch_rules = ch_groups[ch]
        print(f"[{name}] {ci+1}/{total_ch} {ch[:20]} -> mcq...", flush=True)
        try:
            verified, unaudited = dl.generate_mcq(ch_rules, name, ch, ledger=ledger)
            linked, unlinked = dl.link_mcq_to_rules(verified, ch_rules)
        except Exception as e:
            print(f"  ERROR: {e}")
            linked, unlinked, unaudited = [], [], []
        all_mcqs.extend(linked)
        quarantined.extend(unlinked)
        quarantined.extend(unaudited)

        if ledger.exhausted:
            print(f"  BUDGET EXHAUSTED after chapter '{ch}' -- stopping")
            incomplete = True
            break
        # P0-2: completeness gate -- if not every rule got a verified MCQ,
        # the result is incomplete. Do NOT publish partial MCQ sets.
        if len(linked) < len(ch_rules):
            print(f"  INCOMPLETE: {len(linked)}/{len(ch_rules)} MCQs verified "
                  f"for chapter '{ch}' -- marking incomplete")
            incomplete = True
            break
        time.sleep(0.3)

    # P0-2: fail-closed -- do NOT write files if incomplete
    if incomplete:
        print(f"[{name}] FAIL-CLOSED: budget exhausted or MCQs incomplete.")
        print(f"  Ledger: {ledger.summary()}")
        print(f"  Chapters processed: {ci+1}/{total_ch}")
        print(f"  MCQ files NOT written.")
        return {"book": name, "error": "fail_closed",
                "ledger": ledger.summary(),
                "chapters_done": ci + 1, "chapters_total": total_ch}

    dl.rotate_answers(all_mcqs)
    seq = 0
    for ci, ch in enumerate(ch_order):
        ch_mcqs = [m for m in all_mcqs if m.get("source_rule_id", "").startswith(f"{prefix}_{ci:03d}_")]
        seq = dl.assign_mcq_ids(ch_mcqs, prefix, ci, seq)

    # P0-3 finalization: refresh remediation_meta (needs_mcq_regen=False) and
    # recompute provenance so it does NOT go stale after all_mcq.jsonl is
    # replaced. All linked files are then published TRANSACTIONALLY via the
    # same backup + per-file replace + rollback + SHA-verify path that
    # remediation uses (P0-2), so a mid-publish failure fully restores the
    # previous state instead of leaving a half-updated directory.
    meta_path = p / "remediation_meta.json"
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    if not isinstance(meta, dict):
        meta = {}
    meta["needs_mcq_regen"] = False
    meta["regen"] = {
        "mcq_count": len(all_mcqs),
        "quarantined": len(quarantined),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "run_id": run_id,
    }

    output_names = (
        "all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
        "quarantine_mcq.jsonl", "remediation_meta.json", "provenance.json",
    )
    staging = p / f".regen_staging_{os.getpid()}"
    staging.mkdir(parents=True, exist_ok=True)
    backup_dir: Path | None = None
    try:
        # Copy unchanged output files into staging so provenance file_shas
        # cover the FULL output set (not just the files regen rewrites).
        for name in ("all_rules.json", "quarantine_rules.jsonl"):
            src = p / name
            if src.exists():
                shutil.copy2(src, staging / name)
        (staging / "all_mcq.jsonl").write_text(
            "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in all_mcqs),
            encoding="utf-8")
        if quarantined:
            q_f = p / "quarantine_mcq.jsonl"
            existing = []
            if q_f.exists():
                existing = [json.loads(l) for l in q_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            new_q = [m for m in quarantined
                     if all(m.get("question") != x.get("question") for x in existing)]
            merged_q = existing + new_q
            (staging / "quarantine_mcq.jsonl").write_text(
                "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in merged_q),
                encoding="utf-8")
        else:
            # Not rewriting quarantine_mcq -- carry the existing file through so
            # provenance file_shas cover the FULL output set.
            q_src = p / "quarantine_mcq.jsonl"
            if q_src.exists():
                shutil.copy2(q_src, staging / "quarantine_mcq.jsonl")
        (staging / "remediation_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        provenance = rc._compute_provenance(
            staging, p, meta, git_root=git_root, no_api=False)
        # P0-2: bind the CURRENT MCQ output to THIS run's API generation chain.
        # The preserved upstream_provenance layer only proves the OLD commit's
        # bytes; it cannot prove what generated the NEW all_mcq.jsonl. The
        # api_generation layer records the run's identity, inputs, outputs,
        # prompt/config/script SHAs and call stats so a reviewer can verify the
        # current MCQs came from this run with this exact model config.
        mcq_out = (staging / "all_mcq.jsonl").read_bytes()
        # P0-4: the rules ACTUALLY consumed to generate this run's MCQs. regen
        # does not add rules, so input == output == the all_rules.json rules.
        rules_input_payload = json.dumps(
            rules, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        rules_output = json.loads((staging / "all_rules.json").read_text(encoding="utf-8"))
        rules_output_payload = json.dumps(
            rules_output, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        provenance["api_generation"] = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "run_id": run_id,
            "code_sha": code_sha,
            "rules_sha": rules_sha,
            "rules_input_sha": hashlib.sha256(rules_input_payload).hexdigest(),
            "rules_output_sha": hashlib.sha256(rules_output_payload).hexdigest(),
            "rules_added": 0,
            "mcq_output_sha": hashlib.sha256(mcq_out).hexdigest(),
            "mcq_output_bytes": len(mcq_out),
            # P0-4: prove WHICH MCQs this run generated via per-ID canonical
            # record hashes (not just id membership) so a reviewer can verify
            # that all_mcq.jsonl's attributed records came from this chain and
            # that their content was not replaced. regen replaces the whole
            # file, so it does not preserve pre-existing MCQs (P0-3 disjointness
            # does not apply).
            "generated_mcq_sha256_by_id": {
                m.get("id"): mcq_record_sha256(m)
                for m in all_mcqs if isinstance(m, dict) and m.get("id")
            },
            # P0-8: pre-run MCQ id set MUST equal the value frozen in the
            # archived run manifest (provenance is not the source of truth).
            "pre_run_mcq_ids": dl.pre_run_mcq_ids(p / "all_mcq.jsonl"),
            "operation": "regen",
            "preserves_existing_mcqs": False,
            "prompt_sha256": dl.canonical_prompt_sha256(),
            "config_sha256": dl.canonical_config_sha256(),
            "script_sha256": hashlib.sha256(
                (SCRIPTS_DIR / "distill_lib.py").read_bytes()).hexdigest(),
            "provider": dl.FROZEN_MODEL_CONFIG["provider"],
            "model": dl.FROZEN_MODEL_CONFIG["model"],
            "thinking_mode": dl.FROZEN_MODEL_CONFIG["thinking_mode"],
            "temperature": dl.FROZEN_MODEL_CONFIG["temperature"],
            # Medium: per-book call deltas, not cross-book cumulative totals.
            "calls_made": ledger.calls_made - _calls_before,
            "accepted": ledger.accepted - _accepted_before,
            "skipped": ledger.skipped - _skipped_before,
            "verification_level": "partial",  # corrected below if manifest archived
            "completed": True,
        }
        # P0-3: archive the frozen run manifest (FULL file: identity + intent)
        # INTO provenance so run_id/code_sha/rules_sha have a persistent
        # cross-check even after main() clears the work-copy manifest + ledger.
        if manifest_path is not None and manifest_path.exists():
            try:
                _mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
                provenance["run_manifest"] = _mdata
                provenance["run_manifest_sha256"] = _mdata.get("manifest_sha256", "")
                # Medium: with an archived manifest the identity can be
                # re-derived -> full verification.
                provenance["api_generation"]["verification_level"] = "full"
            except Exception:
                pass
        (staging / "provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")

        # P0-2: write the PREPARED receipt bound to the staging output SHAs
        # right before publish. If the process crashes between here and the
        # completed receipt in main(), a resume resolves this prepared state.
        if manifest_path is not None:
            dl.append_book_receipt(
                manifest_path, dir_key, "prepared",
                book_dir=staging, output_names=_RECEIPT_OUTPUT_NAMES)

        # Transactional publish with backup + rollback (P0-2).
        backup_dir = rc._publish(staging, p, list(output_names))

        # P0-x: any post-publish failure -- validate_provenance returning
        # (False, ...) OR raising (I/O, permission, malformed field) -- rolls
        # the published files back from backup. Only validation success deletes
        # the backup.
        try:
            prov_ok, prov_issues = validate_provenance(p, SCRIPTS_DIR, git_root=git_root)
            if not prov_ok:
                raise ConservationError(
                    f"regen provenance validation failed after publish: "
                    f"{'; '.join(prov_issues)}")
            # Success: discard backup.
            shutil.rmtree(backup_dir, ignore_errors=True)
            backup_dir = None
        except BaseException as exc:
            if backup_dir is not None:
                try:
                    rc._rollback_after_failure(
                        p, backup_dir, list(output_names), repr(exc))
                    backup_dir = None
                except Exception as rb:
                    raise ConservationError(
                        f"post-publish failure {exc!r}; rollback ALSO failed: {rb!r}; "
                        f"backup preserved at {backup_dir}"
                    ) from exc
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"[{name}] wrote {len(all_mcqs)} MCQ (+{len(quarantined)} quarantined)")
    print(f"  Ledger: {ledger.summary()}")
    return {"book": name, "mcq_count": len(all_mcqs),
            "ledger": ledger.summary()}


def _build_run_manifest(targets: list[str]) -> dict:
    """Build the canonical pre-run manifest (P0-1/P0-2/P0-4).

    Split into immutable vs mutable:
      - immutable: the run's INTENT -- ordered targets, frozen prompt/config
        SHA, and SHAs of input files regen does NOT modify (all_rules.json,
        quarantine_rules.jsonl). These must NEVER drift on resume.
      - mutable: the pre-run state of files regen itself rewrites
        (remediation_meta.json, quarantine_mcq.jsonl) -- allowed to change on
        resume because the run modifies them.
    """
    immutable: dict = {
        "targets": list(targets),  # order-preserving: reordering changes identity
        "frozen_config_sha256": dl.canonical_config_sha256(),
        "frozen_prompt_sha256": dl.canonical_prompt_sha256(),
        "input_files": {},
    }
    mutable: dict = {}
    for k in targets:
        imm_entry: dict = {}
        for fname in ("all_rules.json", "quarantine_rules.jsonl"):
            f = BASE / k / fname
            if f.exists():
                raw = f.read_bytes()
                imm_entry[fname + "_sha256"] = hashlib.sha256(raw).hexdigest()
                imm_entry[fname + "_bytes"] = len(raw)
        mut_entry: dict = {}
        for fname in ("remediation_meta.json", "quarantine_mcq.jsonl"):
            f = BASE / k / fname
            if f.exists():
                raw = f.read_bytes()
                mut_entry[fname + "_sha256"] = hashlib.sha256(raw).hexdigest()
                mut_entry[fname + "_bytes"] = len(raw)
        # P0-8: freeze the pre-run MCQ id set (regen replaces the whole file, so
        # this is the id set being superseded; still frozen for cross-checking).
        imm_entry["pre_run_mcq_ids"] = dl.pre_run_mcq_ids(BASE / k / "all_mcq.jsonl")
        # P0-9: freeze the operation/mode so the validator is driven by the
        # immutable intent, not the unauthenticated provenance flag.
        imm_entry["operation"] = "regen"
        imm_entry["preserves_existing_mcqs"] = False
        immutable["input_files"][k] = imm_entry
        mutable[k] = mut_entry
    return {"immutable": immutable, "mutable": mutable}


def _compute_run_bindings(targets: list[str],
                          manifest_path: Path | None = None) -> tuple[str, str, str, dict]:
    """Freeze (or reload) the immutable run manifest and return the run identity.

    When manifest_path is given, the identity comes from the frozen manifest
    (create if absent, reload+verify immutable intent if present). Without a
    path (tests), the identity is computed directly from the current manifest.
    Returns (run_id, code_sha, rules_sha, book_state).
    """
    manifest = _build_run_manifest(targets)
    if manifest_path is not None:
        return dl.freeze_run_manifest(
            manifest_path, manifest, _LEDGER_CODE_FILES, mutable_root=BASE)
    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    run_id, code_sha, rules_sha = dl.compute_run_bindings(payload, _LEDGER_CODE_FILES)
    return run_id, code_sha, rules_sha, {}


def main() -> int:
    # P0-14: the CLI allowlist comes from the SINGLE shared authoritative
    # mapping (same source the validator enforces), intersected with BOOKS
    # so the display metadata stays in sync. BOOKS alone must NOT be the
    # authority -- a drift there would otherwise let the producer accept a
    # run the validator is guaranteed to reject.
    allowed = dl.VALID_TARGETS_BY_OPERATION["regen"]
    requested = sys.argv[1:]
    # P0: distinguish "no args" (default: all) from "invalid explicit args"
    # (fail-closed, return 2). A typo must never expand into a full API run.
    if not requested:
        targets = list(allowed)
    else:
        invalid = [t for t in requested if t not in allowed]
        if invalid:
            print(f"ERROR: invalid targets: {invalid}", flush=True)
            return 2
        targets = requested
    # P0: if the shared allowlist drifts from BOOKS metadata, reject outright
    # instead of filtering-and-continuing (the validator would reject anyway).
    missing_metadata = [t for t in targets if t not in BOOKS]
    if missing_metadata:
        print(f"ERROR: targets missing in BOOKS metadata: {missing_metadata}", flush=True)
        return 2
    # Medium: duplicate targets would double-execute books but collapse to one
    # manifest key -- reject them outright.
    if len(targets) != len(set(targets)):
        print(f"ERROR: duplicate targets not allowed: {targets}", flush=True)
        return 2
    # P0-2: single shared ledger across ALL books in this CLI run, so the
    # total API budget is enforced run-wide (not per-book). The ledger is
    # persisted to a single file so crash-restart does not reset the budget.
    ledger_path = BASE / ".regen_ledger.json"
    # P0-1: freeze the immutable run manifest BEFORE any book is processed, so
    # a run that modifies its own inputs can still resume after a crash with
    # the same identity (same shared ledger). Resume also verifies the frozen
    # immutable intent (targets/code/prompt/config) against the invocation.
    manifest_path = BASE / ".regen_run_manifest.json"
    run_id, code_sha, rules_sha, book_state = _compute_run_bindings(targets, manifest_path)
    # P0-2: run only books still pending -- a completed book is NEVER re-run on
    # resume, regardless of the explicit targets in this argv.
    pending = [t for t in targets if book_state.get(t) != "completed"]
    # P0-2: non-zero exit code if ANY book fails (budget exhausted or incomplete).
    # Production callers (CI) rely on exit code to gate downstream steps.
    any_error = False
    for k in pending:
        r = regen_book(k, ledger_path=ledger_path, git_root=ROOT,
                       run_id=run_id, code_sha=code_sha, rules_sha=rules_sha,
                       manifest_path=manifest_path)
        if r.get("error"):
            any_error = True
        else:
            # P0-2: consume the prepared receipt (verifies published bytes match
            # the prepared SHA) rather than re-hashing whatever currently exists.
            dl.complete_prepared_receipt(manifest_path, k, BASE / k)
    # P0-1/P0-3: a fully successful run has nothing to resume -- clear the
    # frozen manifest (and ledger) so the next invocation starts a genuinely
    # new run. The manifest's identity is archived into each book's provenance
    # before the work-copy manifest is removed. A failed/crashed run keeps both.
    if not any_error:
        dl.clear_run_manifest(manifest_path, ledger_path)
    return 1 if any_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
