"""
fill_missing_chapters.py
Fill missing chapters for zpzq (34) and qtbj (11) using corrected distill_lib.
Reads the full raw text, splits by chapter heading, distills missing chapters only,
appends to all_rules.json + all_mcq.jsonl, updates progress.json.

Usage: python scripts/fill_missing_chapters.py [book_dir_key ...]
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sys
import time
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

# Files whose SHAs a prepared/completed book receipt binds (P0-2). These are the
# outputs the run actually rewrites; they must exist in staging (prepared) and
# in the published book dir (completed) so a resume can re-verify them.
_RECEIPT_OUTPUT_NAMES = (
    "all_rules.json", "all_mcq.jsonl", "quarantine_mcq.jsonl",
    "remediation_meta.json", "progress.json",
)

# Code files whose SHA-256 fingerprints a fill run's ledger identity (P0-1).
# A single canonical scope shared with regen and the validator so code_sha can
# be independently re-derived (P0-3).
_LEDGER_CODE_FILES = dl.ledger_code_files(SCRIPTS_DIR, ROOT)

# Chinese numeral map for zpzq chapter headings
CN_NUM = "一二三四五六七八九十"
def _cn_to_int(s: str) -> int:
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + _cn_to_int(s[1:])
    if s.endswith("十"):
        return _cn_to_int(s[:-1]) * 10
    if "十" in s:
        a, b = s.split("十")
        return _cn_to_int(a) * 10 + _cn_to_int(b)
    return CN_NUM.index(s) + 1 if s in CN_NUM else 0


def _split_by_titles(text: str, titles: list[str]) -> dict[str, str]:
    """Split text by known titles: find each title in text, extract until next title."""
    positions = []
    for t in titles:
        idx = text.find(t)
        if idx >= 0:
            positions.append((idx, t))
    positions.sort()
    chapters = {}
    for i, (idx, t) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        chapters[t] = text[idx:end].strip()
    return chapters


def split_zpzq(text: str, titles: list[str]) -> dict[str, str]:
    return _split_by_titles(text, titles)


def split_qtbj(text: str, titles: list[str]) -> dict[str, str]:
    return _split_by_titles(text, titles)


def fill_book(dir_key: str, global_budget: int = 5000,
              ledger_path: Path | None = None,
              git_root: Path | None = None,
              run_id: str = "",
              code_sha: str = "",
              rules_sha: str = "",
              manifest_path: Path | None = None) -> dict:
    if dir_key == "zipingzhenquan":
        name, prefix, book_name = "子平真诠", "zpzq", "子平真诠"
        full_raw = BASE / dir_key / "raw_full.txt"
        if not full_raw.exists():
            return {"book": name, "error": "raw_full.txt not found"}
        text = full_raw.read_text(encoding="utf-8")
        ch_list = (BASE / dir_key / "chapter_list.txt").read_text(encoding="utf-8").splitlines()
        wanted = []
        for line in ch_list:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\d+\.\s*(.+)", line)
            if m:
                wanted.append(m.group(1).strip())
        chapters = split_zpzq(text, wanted)
    elif dir_key == "qiongtongbaojian":
        name, prefix, book_name = "穷通宝鉴", "qtbj", "穷通宝鉴"
        full_raw = BASE / dir_key / "raw_full.txt"
        if not full_raw.exists():
            return {"book": name, "error": "raw_full.txt not found"}
        text = full_raw.read_text(encoding="utf-8")
        sec_list = (BASE / dir_key / "section_list.txt").read_text(encoding="utf-8").splitlines()
        wanted = []
        for line in sec_list:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\d+\.\s*(.+)", line)
            if m:
                wanted.append(m.group(1).strip())
        chapters = split_qtbj(text, wanted)
    else:
        return {"error": f"unsupported book {dir_key}"}

    prog = json.loads((BASE / dir_key / "progress.json").read_text(encoding="utf-8"))
    done = set(prog.get("done", []))

    # find missing
    missing = []
    for w in wanted:
        if w not in done and w in chapters:
            missing.append(w)
    print(f"[{name}] {len(missing)} missing chapters to fill", flush=True)

    # P0-4: nothing to fill -> skip. Do NOT publish (which would rewrite
    # provenance) and do NOT create an api_generation record attributing the
    # existing MCQs to this zero-call run.
    if not missing:
        print(f"[{name}] nothing to fill (all chapters present)")
        return {"book": name, "skipped": True, "missing": 0}

    # load existing
    rules_path = BASE / dir_key / "all_rules.json"
    mcq_path = BASE / dir_key / "all_mcq.jsonl"
    existing_rules = json.loads(rules_path.read_text(encoding="utf-8"))
    existing_mcqs = [json.loads(l) for l in mcq_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    # determine ch_idx offset (max existing chapter index + 1)
    ch_indices = []
    for r in existing_rules:
        rid = r.get("id", "")
        m = re.search(rf"^{prefix}_(\d{{3}})_", rid)
        if m:
            ch_indices.append(int(m.group(1)))
    next_ch_idx = max(ch_indices) + 1 if ch_indices else 0

    # determine mcq seq offset
    mcq_seqs = []
    for m in existing_mcqs:
        mid = m.get("id", "")
        mt = re.search(r"mcq_(\d{4})$", mid)
        if mt:
            mcq_seqs.append(int(mt.group(1)))
    next_mcq_seq = max(mcq_seqs) + 1 if mcq_seqs else 0

    # P0-1/P0-2: Run-level shared budget ledger with frozen global hard cap AND
    # a frozen run identity (run_id/code_sha/rules_sha) computed once at the
    # CLI level. All books in one run share one ledger file and budget; a
    # different run is rejected (fail-closed) rather than silently reusing the
    # old ledger's budget.
    ledger = dl.BudgetLedger.load_or_create(
        ledger_path, global_budget,
        run_id=run_id, code_sha=code_sha, rules_sha=rules_sha)
    # Medium: snapshot the SHARED ledger so api_generation records THIS book's
    # call delta, not the cross-book cumulative total.
    _calls_before = ledger.legacy_calls
    _accepted_before = ledger.accepted
    _skipped_before = ledger.skipped
    new_rules_total = []
    new_mcqs_total = []
    new_mcq_quarantine: list[dict] = []
    chapters_done: list[str] = []
    # P0-2: defer raw_*.txt writes until chapter is confirmed complete.
    # Previously raw_*.txt was written BEFORE the completeness check, so a
    # fail-closed run still left raw files on disk ("files NOT written" was
    # false). Now we buffer (ch_title -> ch_text) and write only on success.
    pending_raw_writes: list[tuple[int, str, str]] = []
    incomplete = False

    for ch_title in missing:
        ch_text = chapters[ch_title]
        print(f"  [{next_ch_idx}] {ch_title[:25]}...", flush=True)
        try:
            rules = dl.distill_chapter(ch_text, book_name, ch_title, ledger=ledger)
        except Exception as e:
            print(f"    DISTILL ERROR: {e}")
            rules = []
        dl.assign_rule_ids(rules, prefix, next_ch_idx)
        # P0-2: do NOT write raw_*.txt here -- defer until chapter confirmed complete.

        # P0-3: empty rules -> fail-closed. An empty result means either
        # distill_failed (API error) or parser_invalid (unparseable output).
        # Both are failures, not "chapter has zero rules". The chapter must
        # NOT be marked done, and raw/progress must NOT be written.
        if not rules:
            print(f"    EMPTY RULES for chapter '{ch_title}' -- marking incomplete "
                  f"(distill_failed or parser_invalid)")
            incomplete = True
            break

        try:
            verified, unaudited = dl.generate_mcq(
                rules, book_name, ch_title, ledger=ledger)
            linked, unlinked = dl.link_mcq_to_rules(verified, rules)
        except Exception as e:
            print(f"    MCQ ERROR: {e}")
            linked, unlinked, unaudited = [], [], []
        next_mcq_seq = dl.assign_mcq_ids(linked, prefix, next_ch_idx, next_mcq_seq)

        new_rules_total.extend(rules)
        new_mcqs_total.extend(linked)
        new_mcq_quarantine.extend(unlinked)
        new_mcq_quarantine.extend(unaudited)

        # P0-2: fail-closed checks -- do NOT mark chapter as done if incomplete
        if ledger.exhausted:
            print(f"    BUDGET EXHAUSTED after chapter '{ch_title}' -- stopping")
            incomplete = True
            break
        if len(linked) < len(rules):
            print(f"    INCOMPLETE: {len(linked)}/{len(rules)} MCQs verified -- marking incomplete")
            incomplete = True
            break

        # Chapter confirmed complete -- safe to schedule raw write.
        pending_raw_writes.append((next_ch_idx, ch_title, ch_text))
        chapters_done.append(ch_title)
        next_ch_idx += 1
        time.sleep(0.3)

    # P0-2: fail-closed -- do NOT write files or update progress if incomplete
    if incomplete:
        print(f"[{name}] FAIL-CLOSED: budget exhausted or MCQs incomplete.")
        print(f"  Ledger: {ledger.summary()}")
        print(f"  Chapters processed: {len(chapters_done)}/{len(missing)}")
        print(f"  Progress NOT updated, rules/MCQ/raw files NOT written.")
        return {"book": name, "error": "fail_closed",
                "ledger": ledger.summary(),
                "chapters_done": len(chapters_done),
                "chapters_missing": len(missing)}

    # All chapters succeeded -- now safe to publish. P0-2/P0-3: write all files
    # (raw + rules + mcq + quarantine + progress + provenance + meta) to a
    # staging dir, then publish TRANSACTIONALLY via the same backup + per-file
    # replace + rollback + SHA-verify path that remediation/regen use. A
    # mid-publish failure fully restores the previous state instead of leaving
    # a half-updated directory.
    book_dir = BASE / dir_key

    # P0-3 finalization: refresh meta and recompute provenance so it does not
    # go stale after the rules/MCQ/raw files are replaced.
    meta_path = book_dir / "remediation_meta.json"
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    if not isinstance(meta, dict):
        meta = {}
    meta["needs_mcq_regen"] = False
    meta["fill"] = {
        "added_rules": len(new_rules_total),
        "added_mcq": len(new_mcqs_total),
        "chapters": chapters_done,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "run_id": run_id,
    }

    raw_names = [f"raw_{ch_idx:03d}_{ch_title[:10]}.txt"
                 for ch_idx, ch_title, _ in pending_raw_writes]
    output_names = (
        "all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
        "quarantine_mcq.jsonl", "remediation_meta.json", "provenance.json",
        "progress.json",
    ) + tuple(raw_names)

    staging = book_dir / f".fill_staging_{os.getpid()}"
    staging.mkdir(parents=True, exist_ok=True)
    backup_dir: Path | None = None
    try:
        for ch_idx, ch_title, ch_text in pending_raw_writes:
            (staging / f"raw_{ch_idx:03d}_{ch_title[:10]}.txt").write_text(
                ch_text, encoding="utf-8")

        done.update(chapters_done)
        all_rules = existing_rules + new_rules_total
        all_mcqs = existing_mcqs + new_mcqs_total
        dl.rotate_answers(all_mcqs)

        (staging / "all_rules.json").write_text(
            json.dumps(all_rules, ensure_ascii=False, indent=2), encoding="utf-8")
        (staging / "all_mcq.jsonl").write_text(
            "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in all_mcqs),
            encoding="utf-8")
        # Copy unchanged quarantine_rules.jsonl into staging so provenance
        # file_shas cover the FULL output set.
        qr_src = book_dir / "quarantine_rules.jsonl"
        if qr_src.exists():
            shutil.copy2(qr_src, staging / "quarantine_rules.jsonl")
        if new_mcq_quarantine:
            q_f = book_dir / "quarantine_mcq.jsonl"
            existing_q = []
            if q_f.exists():
                existing_q = [json.loads(l) for l in q_f.read_text(encoding="utf-8").splitlines() if l.strip()]
            new_q = [m for m in new_mcq_quarantine
                     if all(m.get("question") != x.get("question") for x in existing_q)]
            merged_q = existing_q + new_q
            (staging / "quarantine_mcq.jsonl").write_text(
                "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in merged_q),
                encoding="utf-8")
        else:
            q_src = book_dir / "quarantine_mcq.jsonl"
            if q_src.exists():
                shutil.copy2(q_src, staging / "quarantine_mcq.jsonl")
        prog["done"] = list(done)
        prog["total_rules"] = len(all_rules)
        prog["total_mcqs"] = len(all_mcqs)
        (staging / "progress.json").write_text(
            json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")
        (staging / "remediation_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        provenance = rc._compute_provenance(
            staging, book_dir, meta, git_root=git_root, no_api=False)
        # P0-2/P0-4: bind the CURRENT MCQ output to THIS run's API generation
        # chain. rules_input_sha hashes the rules ACTUALLY sent to the model
        # this run (new_rules_total) -- NOT the pre-run all_rules.json. Also
        # record the final rules output SHA. If no new rules/MCQs and no API
        # calls happened, no api_generation record is created (nothing new to
        # attribute to this run).
        if new_mcqs_total or ledger.calls_made > 0:
            mcq_out = (staging / "all_mcq.jsonl").read_bytes()
            rules_input_payload = json.dumps(
                new_rules_total, sort_keys=True, ensure_ascii=False,
                separators=(",", ":")).encode("utf-8")
            rules_output = json.loads((staging / "all_rules.json").read_text(encoding="utf-8"))
            rules_output_payload = json.dumps(
                rules_output, sort_keys=True, ensure_ascii=False,
                separators=(",", ":")).encode("utf-8")
            provenance["api_generation"] = {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "run_id": run_id,
                "code_sha": code_sha,
                "rules_sha": rules_sha,
                "rules_input_sha": hashlib.sha256(rules_input_payload).hexdigest(),
                # P0-4: persist the actual rule set sent to the model so the
                # validator can independently recompute rules_input_sha instead
                # of trusting a 64-char string.
                "rules_input_snapshot": new_rules_total,
                "rules_output_sha": hashlib.sha256(rules_output_payload).hexdigest(),
                "rules_added": len(new_rules_total),
                "mcq_output_sha": hashlib.sha256(mcq_out).hexdigest(),
                "mcq_output_bytes": len(mcq_out),
                # P0-4: prove WHICH MCQs this run generated via per-ID canonical
                # record hashes (not just id membership) so a reviewer can verify
                # that all_mcq.jsonl's attributed records came from this chain
                # and were not replaced / re-used from a prior run. fill preserves
                # pre-existing MCQs, so the generated ids must be disjoint from
                # the frozen pre-run id set (P0-3).
                "generated_mcq_sha256_by_id": {
                    m.get("id"): mcq_record_sha256(m)
                    for m in new_mcqs_total if isinstance(m, dict) and m.get("id")
                },
                # P0-8: pre-run MCQ id set MUST equal the value frozen in the
                # archived run manifest (provenance is not the source of truth).
                "pre_run_mcq_ids": dl.pre_run_mcq_ids(book_dir / "all_mcq.jsonl"),
                "operation": "fill",
                "preserves_existing_mcqs": True,
                "prompt_sha256": dl.canonical_prompt_sha256(),
                "config_sha256": dl.canonical_config_sha256(),
                "script_sha256": hashlib.sha256(
                    (SCRIPTS_DIR / "distill_lib.py").read_bytes()).hexdigest(),
                "provider": dl.FROZEN_MODEL_CONFIG["provider"],
                "model": dl.FROZEN_MODEL_CONFIG["model"],
                "thinking_mode": dl.FROZEN_MODEL_CONFIG["thinking_mode"],
                "temperature": dl.FROZEN_MODEL_CONFIG["temperature"],
                # Medium: per-book call deltas, not cross-book cumulative totals.
                "calls_made": ledger.legacy_calls - _calls_before,
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
        backup_dir = rc._publish(staging, book_dir, list(output_names))

        # P0-3/P0-x: re-validate provenance on the PUBLISHED state with the
        # REAL git_root (no gate bypass). New raw files added by fill are
        # anchored via provenance `raw_sources` derivation entries (see
        # _compute_provenance) so the baseline full-coverage gate is satisfied
        # honestly rather than disabled. Any post-publish failure -- validation
        # returning False OR raising -- rolls back from backup; only validation
        # success deletes the backup.
        try:
            prov_ok, prov_issues = validate_provenance(book_dir, SCRIPTS_DIR, git_root=git_root)
            if not prov_ok:
                raise ConservationError(
                    f"fill provenance validation failed after publish: "
                    f"{'; '.join(prov_issues)}")
            # Success: discard backup.
            shutil.rmtree(backup_dir, ignore_errors=True)
            backup_dir = None
        except BaseException as exc:
            if backup_dir is not None:
                try:
                    rc._rollback_after_failure(
                        book_dir, backup_dir, list(output_names), repr(exc))
                    backup_dir = None
                except Exception as rb:
                    raise ConservationError(
                        f"post-publish failure {exc!r}; rollback ALSO failed: {rb!r}; "
                        f"backup preserved at {backup_dir}"
                    ) from exc
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print(f"[{name}] added {len(new_rules_total)} rules, {len(new_mcqs_total)} MCQ")
    print(f"  Ledger: {ledger.summary()}")
    return {"book": name, "added_rules": len(new_rules_total), "added_mcq": len(new_mcqs_total),
            "total_rules": len(all_rules), "total_mcq": len(all_mcqs),
            "ledger": ledger.summary()}


def _build_run_manifest(targets: list[str]) -> dict:
    """Build the canonical pre-run manifest (P0-1/P0-2/P0-4).

    Split into immutable vs mutable:
      - immutable: the run's INTENT -- ordered targets, frozen prompt/config
        SHA, and SHAs of inputs fill does NOT modify (raw_full.txt,
        chapter_list.txt, section_list.txt).
      - mutable: the pre-run state of files fill itself rewrites
        (progress.json, all_rules.json, all_mcq.jsonl) -- allowed to change on
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
        d = BASE / k
        imm_entry: dict = {}
        for fname in ("raw_full.txt", "chapter_list.txt", "section_list.txt"):
            f = d / fname
            if f.exists():
                raw = f.read_bytes()
                imm_entry[fname + "_sha256"] = hashlib.sha256(raw).hexdigest()
                imm_entry[fname + "_bytes"] = len(raw)
        mut_entry: dict = {}
        for fname in ("progress.json", "all_rules.json", "all_mcq.jsonl"):
            f = d / fname
            if f.exists():
                raw = f.read_bytes()
                mut_entry[fname + "_sha256"] = hashlib.sha256(raw).hexdigest()
                mut_entry[fname + "_bytes"] = len(raw)
        # P0-8: freeze the pre-run MCQ id set so the validator can prove no old
        # MCQ was retroactively claimed as generated (immutable intent).
        imm_entry["pre_run_mcq_ids"] = dl.pre_run_mcq_ids(d / "all_mcq.jsonl")
        # P0-9: freeze the operation/mode so the validator is driven by the
        # immutable intent, not the unauthenticated provenance flag.
        imm_entry["operation"] = "fill"
        imm_entry["preserves_existing_mcqs"] = True
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
    fill_targets = dl.VALID_TARGETS_BY_OPERATION["fill"]
    requested = sys.argv[1:]
    # P0: distinguish "no args" (default: all) from "invalid explicit args"
    # (fail-closed, return 2). A typo must never expand into a full API run.
    if not requested:
        targets = list(fill_targets)
    else:
        invalid = [t for t in requested if t not in fill_targets]
        if invalid:
            print(f"ERROR: invalid targets: {invalid}", flush=True)
            return 2
        targets = requested
    # Medium: duplicate targets would double-execute books but collapse to one
    # manifest key -- reject them outright.
    if len(targets) != len(set(targets)):
        print(f"ERROR: duplicate targets not allowed: {targets}", flush=True)
        return 2
    # P0-2: single shared ledger across ALL books in this CLI run, so the
    # total API budget is enforced run-wide (not per-book). The ledger is
    # persisted to a single file so crash-restart does not reset the budget.
    ledger_path = BASE / ".fill_ledger.json"
    # P0-1: freeze the immutable run manifest BEFORE any book is processed, so
    # a run that modifies its own inputs can still resume after a crash with
    # the same identity. Resume verifies the frozen immutable intent.
    manifest_path = BASE / ".fill_run_manifest.json"
    run_id, code_sha, rules_sha, book_state = _compute_run_bindings(targets, manifest_path)
    # P0-2: run only books still pending -- a completed book is NEVER re-run on
    # resume, regardless of the explicit targets in this argv.
    pending = [t for t in targets if book_state.get(t) != "completed"]
    # P0-2: non-zero exit code if ANY book fails (budget exhausted or incomplete).
    any_error = False
    for k in pending:
        r = fill_book(k, ledger_path=ledger_path, git_root=ROOT,
                      run_id=run_id, code_sha=code_sha, rules_sha=rules_sha,
                      manifest_path=manifest_path)
        if r.get("error"):
            any_error = True
        else:
            # P0-2: consume the prepared receipt (verifies published bytes match
            # the prepared SHA) rather than re-hashing whatever currently exists.
            dl.complete_prepared_receipt(manifest_path, k, BASE / k)
    # P0-1/P0-3: a fully successful run clears manifest + ledger; the identity
    # is archived into each book's provenance before the work-copy is removed.
    if not any_error:
        dl.clear_run_manifest(manifest_path, ledger_path)
    return 1 if any_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
