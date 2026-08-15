"""
distill_lib.py
Unified, corrected distillation library for classical bazi texts.

Root-cause fixes vs original batch scripts:
  - IDs assigned POST-HOC by code (model never generates IDs) -> no collisions
  - source_rule_id set by code from the rule it was generated from -> always valid
  - Deterministic answer rotation built into MCQ generation -> ~25% per letter
  - Relative paths via Path(__file__) -> portable
  - Provenance manifest (URL/SHA/model config) written per run

MCQ mapping proof (P0-1 redesign):
  source_rule_id is an ORCHESTRATOR-ESTABLISHED MAPPING, not a model echo.
  The orchestrator sends one rule per API call and stamps source_rule_id
  with the rule it sent. This does NOT prove the model's response semantically
  corresponds to the rule.

  Semantic proof is two-tiered:
    1. _mcq_prefilter: low-cost 2-char substring overlap. Drops obviously
       unrelated MCQs. NOT a proof -- cannot set _consistency_verified=True.
    2. _mcq_strict_consistency: checks subject matching (rule's subject must
       appear in MCQ question) and polarity contradiction (喜 vs 忌, 吉 vs 凶,
       宜 vs 不宜). Only passing BOTH tiers sets _consistency_verified=True.

  MCQs that pass prefilter but fail strict check are NOT dropped -- they enter
  semantic_unaudited quarantine for human review. MCQs that fail prefilter are
  dropped entirely. Old MCQs without _consistency_verified are legacy_unaudited.

  BudgetLedger provides run-level global API call tracking across multiple
  generate_mcq invocations (P0-2). Callers MUST create a ledger with a frozen
  hard cap and pass it to every generate_mcq call. When the ledger is
  exhausted or MCQs are incomplete, callers MUST fail-closed (not update
  progress, not publish partial results).

Public API:
  distill_chapter(text, book, chapter) -> list[dict]
  generate_mcq(rules, book, chapter, ..., ledger=None) -> (verified, unaudited)
  link_mcq_to_rules(mcqs, rules) -> (linked, unlinked)
  BudgetLedger(global_hard_cap) -> ledger
  assign_rule_ids(rules, prefix, ch_idx) -> None
  rotate_answers(mcqs) -> None
  write_provenance(out_dir, cfg) -> None
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import subprocess as _subprocess
import sys
import time
from pathlib import Path
from scripts.classic_artifacts import EXPERIMENT_ID

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Frozen seed shared with remediate_classic_distillation.py so the answer-rotation
# protocol is uniform across newly-generated and post-hoc-remediated MCQs.
ROTATE_SEED = "bazi_classic_distillation_v2"

RULE_PROMPT = (
    "你是八字命理知识工程师。从以下古文段落中提取结构化命理规则，输出JSON数组。\n"
    "每条规则格式（id 由系统赋值，你不要填 id 字段）：\n"
    '{"category":"天干|地支|五行|十神|格局|用神|大运|流年|六亲|性情|疾病|其他",'
    '"subject":"主体","condition":"条件","rule":"白话规则(<=100字)",'
    '"original_text":"古文引用(<=50字)","source_book":"__BOOK__","source_chapter":"__CH__"}\n\n'
    "古文（__BOOK__·__CH__）：\n__TEXT__\n\n"
    "注意：只提取有明确命理含义的规则。无规则则返回[]。只输出JSON数组。"
)

MCQ_PROMPT = (
    "你是八字命理考试出题专家。根据以下规则生成四选一选择题，每条规则一题。\n"
    "输出JSON数组，每题格式（id 由系统赋值）：\n"
    '{"source_rule_id":"该题依据的规则id(必须取自下方规则列表中的id)","question":"题干(含命理背景)",'
    '"options":{"A":"...","B":"...","C":"...","D":"..."},'
    '"answer":"正确字母","explanation":"解析","difficulty":"基础|中级|高级",'
    '"category":"天干|地支|五行|十神|格局|用神|其他"}\n\n'
    "规则：\n__RULES__\n\n"
    "注意：每条规则恰好生成一题，source_rule_id 必须精确取自下方规则的 id 字段，不要编造。只输出JSON数组。"
)

# Per-rule MCQ prompt (P0-1). Each rule is sent in its own API call. The
# orchestrator stamps source_rule_id after receiving the response -- this is
# an orchestrator mapping, NOT a model echo proof. The real proof that the
# MCQ corresponds to the rule is the two-tiered consistency check
# (_mcq_prefilter + _mcq_strict_consistency), applied after generation.
PER_RULE_MCQ_PROMPT = (
    "你是八字命理考试出题专家。根据下方【唯一】规则生成一道四选一选择题。\n"
    "输出JSON对象（不要输出数组，只输出单个对象）：\n"
    '{"question":"题干(含命理背景)",'
    '"options":{"A":"...","B":"...","C":"...","D":"..."},'
    '"answer":"正确字母","explanation":"解析","difficulty":"基础|中级|高级",'
    '"category":"天干|地支|五行|十神|格局|用神|其他"}\n\n'
    "规则：\n__RULE__\n\n"
    "注意：只输出JSON对象，不要输出其他内容。题干和解析必须与上方规则内容直接相关。"
)


def _get_api_key() -> str:
    env = os.environ.get("DEEPSEEK_API_KEY")
    if env:
        return env
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("DEEPSEEK_API_KEY not found in env or .env")


# Single authoritative frozen model configuration (P0-3). _call() builds the
# API payload from this constant, canonical_config_sha256() hashes it, and the
# provenance validator imports the SAME constant -- there is exactly one copy,
# so a change to the actual model config is always reflected in the canonical
# fingerprint and validation.
FROZEN_MODEL_CONFIG = {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "thinking_mode": "disabled",
    "temperature": 0.0,
}

# Authoritative mapping of which classic-text books each canonical producer may
# operate on (P0-14). Shared by the producers (fill/regen) and the provenance
# validator so the frozen run's targets are checked against the SAME single
# source of truth -- a field-complete but unknown target cannot enter a run.
# Tuple order is the canonical default target order (run identity is
# order-sensitive, and frozenset iteration order is not stable across
# processes due to string hash randomization).
VALID_TARGETS_BY_OPERATION = {
    "fill": ("zipingzhenquan", "qiongtongbaojian"),
    "regen": ("zipingzhenquan", "qiongtongbaojian",
              "sanmingtonghui", "ditiansui"),
}


def _call(prompt: str, timeout: int = 300) -> str:
    from claude_api import call_model_messages_sync_with_meta
    resp, _ = call_model_messages_sync_with_meta(
        [{"role": "user", "content": prompt}],
        provider=FROZEN_MODEL_CONFIG["provider"],
        model=FROZEN_MODEL_CONFIG["model"],
        thinking_mode=FROZEN_MODEL_CONFIG["thinking_mode"],
        temperature=FROZEN_MODEL_CONFIG["temperature"],
        timeout=timeout,
    )
    return resp


def _parse_json_array(s: str) -> list[dict]:
    s = s.strip()
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return []


def _parse_json_object(s: str) -> dict | None:
    """Parse a single JSON object from a model response (P0-5 per-rule path)."""
    s = s.strip()
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            try:
                v = json.loads(m.group())
                return v if isinstance(v, dict) else None
            except json.JSONDecodeError:
                pass
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def compute_code_sha(code_files: list[Path]) -> str:
    """SHA-256 fingerprint of the code files that drive a run (P0-1).

    Includes each file's name as a boundary so two identically-sized files in
    different order cannot collide. Missing files are skipped.
    """
    h = hashlib.sha256()
    for f in code_files:
        h.update(f.name.encode("utf-8"))
        h.update(b"\0")
        if f.exists():
            h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def compute_run_bindings(
    rules_payload: str | bytes,
    code_files: list[Path],
) -> tuple[str, str, str]:
    """Compute (run_id, code_sha, rules_sha) freezing a distillation run's identity.

    P0-1: the three binding fields uniquely identify a run. A resume of the
    SAME run (same code + same rules input) reuses the budget; any drift in
    code or input rules produces a different run_id, so a stale ledger from a
    different run is rejected (fail-closed) rather than silently reused.
    """
    if isinstance(rules_payload, str):
        rules_payload = rules_payload.encode("utf-8")
    rules_sha = hashlib.sha256(rules_payload).hexdigest()
    code_sha = compute_code_sha(code_files)
    run_id = hashlib.sha256((code_sha + ":" + rules_sha).encode("utf-8")).hexdigest()[:16]
    return run_id, code_sha, rules_sha


def ledger_code_files(scripts_dir: Path, root: Path) -> list[Path]:
    """Canonical code-file scope whose SHA-256 fingerprints every classic
    distillation run's ledger identity (P0-1/P0-3).

    A single shared scope is used by fill, regen, AND the provenance validator
    so the validator can independently re-derive code_sha without trusting a
    scope recorded in provenance.
    """
    return [
        scripts_dir / "distill_lib.py",
        scripts_dir / "classic_artifacts.py",
        scripts_dir / "remediate_classic_distillation.py",
        scripts_dir / "fill_missing_chapters.py",
        scripts_dir / "regen_mcq.py",
        root / "claude_api.py",
    ]


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pre_run_mcq_ids(mcq_path: Path) -> list[str]:
    """Canonical ordered, de-duplicated list of MCQ ids in a pre-run
    all_mcq.jsonl (P0-8).

    This is the authoritative source of "which MCQs existed before this run".
    It is frozen into the immutable run manifest at freeze time, and the
    provenance's api_generation.pre_run_mcq_ids must equal it so the validator
    can prove no old MCQ was retroactively claimed as generated.
    """
    if not mcq_path.exists():
        return []
    ids: list[str] = []
    for l in mcq_path.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        try:
            rid = json.loads(l).get("id")
        except Exception:
            continue
        if isinstance(rid, str) and rid and rid not in ids:
            ids.append(rid)
    return ids


def _receipt_sha(prev_sha: str, run_id: str, target: str, status: str,
                 output_shas: dict, prepared_sha: str | None = None) -> str:
    """SHA-256 of a book completion receipt's canonical content (P0-1).

    `prepared_sha` (the sha of the prepared receipt a completed receipt is
    consuming) is included when present so a completed receipt explicitly and
    immutably references the prepared state it finalizes.
    """
    content = {
        "prev_sha": prev_sha, "run_id": run_id, "target": target,
        "status": status, "output_shas": output_shas,
    }
    if prepared_sha is not None:
        content["prepared_sha"] = prepared_sha
    payload = json.dumps(
        content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verify_book_receipts(receipts: list, run_id: str, manifest_sha: str) -> dict:
    """Verify the hash-chained book_receipts list anchored to manifest_sha.

    Each receipt binds (prev_sha, run_id, target, status, output_shas) so a
    receipt from a different run cannot be transplanted and the chain anchors
    to manifest_sha so receipts cannot be prepended. NOTE: this is a plain
    SHA chain -- it detects accidental corruption and *inconsistent* tampering,
    but it is NOT unforgeable against a writer who recomputes the chain. It is
    an integrity/consistency guard, not a signature or an external immutable
    anchor. Returns {target: status}.
    """
    prev = manifest_sha
    statuses: dict[str, str] = {}
    for r in receipts:
        if not isinstance(r, dict):
            raise LedgerCorruptionError(f"book receipt not an object: {r!r}")
        target = r.get("target")
        status = r.get("status")
        output_shas = r.get("output_shas", {})
        if r.get("prev_sha") != prev:
            raise LedgerCorruptionError(
                f"book_receipts chain break for {target!r}: prev_sha mismatch"
            )
        expected = _receipt_sha(prev, run_id, target, status, output_shas,
                                r.get("prepared_sha"))
        if expected != r.get("sha"):
            raise LedgerCorruptionError(
                f"book_receipts sha mismatch for {target!r} (forged receipt)"
            )
        # A "prepared" or "completed" receipt with no output_shas proves nothing
        # -- an attacker could forge it (valid sha, empty outputs) to skip a
        # book or to fake a prepared state. Both must bind real artifacts that
        # a resume can re-verify.
        if status in ("prepared", "completed") and not output_shas:
            raise LedgerCorruptionError(
                f"book_receipts {status} receipt for {target!r} has no output_shas "
                f"(cannot prove a real state)"
            )
        prev = r.get("sha")
        if isinstance(target, str):
            statuses[target] = status
    return statuses


def _write_manifest_atomic(manifest_path: Path, data: dict) -> None:
    """Atomically persist the run manifest dict (tmp + os.replace)."""
    tmp = manifest_path.parent / f".{manifest_path.name}.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp.replace(manifest_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _resolve_prepared_receipt(data: dict, receipt: dict, frozen_mutable: dict,
                              mutable_root: Path) -> tuple[bool, str]:
    """Resolve a prepared receipt at resume time.

    A prepared receipt is written right before publish (bound to the expected
    staging output SHAs). At resume the current published bytes are compared:
      - current == expected  -> publish completed; return (True, 'completed')
      - current == old frozen mutable -> publish never happened; 'pending'
      - neither -> 'blocked' (BLOCKED)
    Returns (is_handled, resolved_status). is_handled is False only when the
    caller should fall through to the normal pending-drift check.
    """
    target = receipt.get("target")
    expected = receipt.get("output_shas", {})
    old = frozen_mutable.get(target, {}) or {}
    old_shas = {k[: -len("_sha256")]: v for k, v in old.items() if k.endswith("_sha256")}
    cur_expected: dict[str, str | None] = {}
    for fname in expected:
        cur = mutable_root / target / fname
        cur_expected[fname] = _sha256_file(cur) if cur.exists() else None
    match_expected = all(
        cur_expected.get(fname) == fsha for fname, fsha in expected.items())
    match_old = False
    if old_shas:
        match_old = all(
            (mutable_root / target / fname).exists()
            and _sha256_file(mutable_root / target / fname) == fsha
            for fname, fsha in old_shas.items())
    if match_expected:
        return True, "completed"
    if match_old:
        return True, "pending"
    return True, "blocked"


def freeze_run_manifest(
    manifest_path: Path,
    manifest: dict,
    code_files: list[Path],
    mutable_root: Path | None = None,
) -> tuple[str, str, str, dict]:
    """Freeze (or reload) the immutable run manifest and return the run identity.

    `manifest` MUST have the shape {"immutable": {...}, "mutable": {...}}:
      - immutable: fields that define the run's INTENT and must never drift on
        resume -- ordered targets, frozen prompt/config SHA, and the SHAs of
        input files the run does NOT modify.
      - mutable: the pre-run state of files the run ITSELF modifies
        (remediation_meta.json, quarantine_mcq.jsonl, progress.json,
        all_rules.json, all_mcq.jsonl, ...).

    P0-1: written atomically BEFORE any book is processed. On resume the
    frozen manifest is reloaded, its SHA verified, and the IMMUTABLE fields
    are compared against the current invocation:
      - current ordered targets must equal the frozen targets;
      - current code SHA must equal the frozen code SHA;
      - current frozen prompt/config SHA must equal the frozen values.
    Any drift is rejected (LedgerCorruptionError) -- a stale manifest cannot
    vouch for a different target set or new code. Only the run-modified
    (mutable) inputs may differ on resume.

    Returns (run_id, code_sha, rules_sha, book_state). book_state is
    {target: "pending"|"completed"} persisted across resume so a restarted run
    only processes books not yet completed (P0-2).
    """
    immutable = manifest.get("immutable", {})
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise LedgerCorruptionError(
                f"run manifest unparseable: {manifest_path}: {e}"
            ) from e
        if not isinstance(data, dict) or not {"manifest", "manifest_sha256",
                                              "run_id", "code_sha", "rules_sha"} <= set(data.keys()):
            raise LedgerCorruptionError(f"run manifest missing required fields: {manifest_path}")
        payload = json.dumps(data["manifest"], ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        actual_sha = hashlib.sha256(payload).hexdigest()
        if actual_sha != data["manifest_sha256"]:
            raise LedgerCorruptionError(
                f"run manifest tampered (sha mismatch): {manifest_path}"
            )
        # P0-1: re-derive the identity from the integrity-protected manifest +
        # current code; reject any forged value stored outside the hash.
        # rules_sha IS the manifest sha (compute_run_bindings hashes the same
        # canonical manifest payload), so it must equal the re-derived sha.
        if data.get("rules_sha") != actual_sha:
            raise LedgerCorruptionError(
                f"run manifest rules_sha does not match manifest sha "
                f"(forged identity): {manifest_path}"
            )
        actual_code_sha = compute_code_sha(code_files)
        if actual_code_sha != data["code_sha"]:
            raise LedgerCorruptionError(
                f"run manifest code drift: current code SHA != frozen code SHA "
                f"-- refusing to resume with changed code"
            )
        expected_run_id = hashlib.sha256(
            (actual_code_sha + ":" + actual_sha).encode("utf-8")).hexdigest()[:16]
        if expected_run_id != data["run_id"]:
            raise LedgerCorruptionError(
                f"run manifest run_id does not match re-derived value "
                f"(forged identity): {manifest_path}"
            )
        # P0-1: the immutable intent must match the current invocation.
        frozen_immutable = data["manifest"].get("immutable", {})
        if immutable != frozen_immutable:
            raise LedgerCorruptionError(
                f"run manifest immutable intent mismatch: current {immutable!r} "
                f"vs frozen {frozen_immutable!r} -- refusing to reuse a ledger "
                f"from a different target set / model config"
            )
        # P0-1: verify the hash-chained book_receipts (book_state integrity).
        receipts = data.get("book_receipts", [])
        book_state = _verify_book_receipts(receipts, data["run_id"], actual_sha)
        # P0-2: recoverable transaction protocol + drift rejection.
        if mutable_root is not None:
            frozen_mutable = data["manifest"].get("mutable", {})
            # Resolve prepared receipts. P0-1: only the LATEST prepared per
            # target is active -- a retry that wrote a newer prepared receipt
            # supersedes any earlier one, so historical prepared receipts never
            # participate in recovery (otherwise the old expected SHA could
            # falsely BLOCK a valid newer publication). This may append a
            # completed receipt or reclassify a book as pending; a book whose
            # outputs match neither old nor expected is BLOCKED.
            completed_targets = {
                r.get("target") for r in receipts
                if isinstance(r, dict) and r.get("status") == "completed"}
            latest_prepared: dict[str, dict] = {}
            for r in receipts:
                if (isinstance(r, dict) and r.get("status") == "prepared"
                        and r.get("target") not in completed_targets):
                    latest_prepared[r.get("target")] = r
            changed = False
            for target, receipt in latest_prepared.items():
                handled, resolved = _resolve_prepared_receipt(
                    receipt, receipt, frozen_mutable, mutable_root)
                if resolved == "blocked":
                    raise LedgerCorruptionError(
                        f"prepared book {target} output neither old nor expected "
                        f"(BLOCKED -- cannot recover safely)")
                if resolved == "completed":
                    # Append to the GLOBAL chain tail and immutably reference the
                    # prepared receipt being consumed -- never fork from the
                    # prepared's own sha if it is not the chain tail.
                    prev = receipts[-1]["sha"]
                    expected = receipt.get("output_shas", {})
                    prepared_sha = receipt["sha"]
                    csha = _receipt_sha(prev, data["run_id"], target, "completed",
                                        expected, prepared_sha)
                    receipts.append({"target": target, "status": "completed",
                                     "output_shas": expected, "prepared_sha": prepared_sha,
                                     "prev_sha": prev, "sha": csha})
                    completed_targets.add(target)
                    book_state[target] = "completed"
                    changed = True
                else:  # pending -> re-execute
                    book_state[target] = "pending"
            if changed:
                _write_manifest_atomic(manifest_path, data)
            # Per-target verification: completed must match receipt output_shas
            # AND the files must exist; pending must match frozen mutable SHAs
            # AND the files must exist. A missing file is a hard failure (P0-1).
            for target in frozen_immutable.get("targets", []):
                if book_state.get(target) == "completed":
                    receipt = next((r for r in receipts if isinstance(r, dict)
                                    and r.get("target") == target
                                    and r.get("status") == "completed"), None)
                    if receipt is not None:
                        for fname, fsha in receipt.get("output_shas", {}).items():
                            cur = mutable_root / target / fname
                            if not cur.exists():
                                raise LedgerCorruptionError(
                                    f"completed book {target} output missing: {fname}")
                            if _sha256_file(cur) != fsha:
                                raise LedgerCorruptionError(
                                    f"completed book {target} output drift: "
                                    f"{fname} changed after publish"
                                )
                else:
                    frozen_entry = frozen_mutable.get(target, {})
                    for key, fsha in frozen_entry.items():
                        if not key.endswith("_sha256"):
                            continue
                        fname = key[: -len("_sha256")]
                        cur = mutable_root / target / fname
                        if not cur.exists():
                            raise LedgerCorruptionError(
                                f"pending book {target} mutable input missing: {fname}")
                        if _sha256_file(cur) != fsha:
                            raise LedgerCorruptionError(
                                f"pending book {target} mutable input drift: "
                                f"{fname} changed before this run processed it"
                            )
        return (data["run_id"], data["code_sha"], data["rules_sha"], book_state)

    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    run_id, code_sha, rules_sha = compute_run_bindings(payload, code_files)
    data = {
        "manifest": manifest,
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
        "run_id": run_id,
        "code_sha": code_sha,
        "rules_sha": rules_sha,
        "book_receipts": [],
    }
    tmp = manifest_path.parent / f".{manifest_path.name}.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp.replace(manifest_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return run_id, code_sha, rules_sha, {}


def append_book_receipt(manifest_path: Path, target: str, status: str,
                        book_dir: Path | None = None,
                        output_names: tuple[str, ...] = ()) -> None:
    """Append a hash-chained receipt for a book (P0-1/P0-2).

    status is "prepared" (bound to expected staging output SHAs, written right
    before publish) or "completed" (written after publish). Both record output
    file SHAs so a resume can re-verify the published bytes. For "prepared" or
    "completed", every output_names file MUST exist in book_dir -- a missing
    file is a hard error (P0-1) because a receipt that silently skips missing
    outputs could be forged to bypass verification.
    """
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise LedgerCorruptionError(f"run manifest unreadable: {manifest_path}: {e}") from e
    if not isinstance(data, dict):
        raise LedgerCorruptionError(f"run manifest not an object: {manifest_path}")
    run_id = data.get("run_id", "")
    manifest_sha = data.get("manifest_sha256", "")
    receipts = data.setdefault("book_receipts", [])
    prev_sha = receipts[-1]["sha"] if receipts else manifest_sha
    output_shas: dict[str, str] = {}
    if status in ("prepared", "completed"):
        if book_dir is None or not output_names:
            raise LedgerCorruptionError(
                f"{status} receipt requires book_dir + output_names")
        for name in output_names:
            f = Path(book_dir) / name
            if not f.exists():
                raise LedgerCorruptionError(
                    f"cannot write {status} receipt: output missing {name!r} "
                    f"for {target!r} in {book_dir}")
            output_shas[name] = _sha256_file(f)
    sha = _receipt_sha(prev_sha, run_id, target, status, output_shas)
    receipts.append({"target": target, "status": status,
                     "output_shas": output_shas, "prev_sha": prev_sha, "sha": sha})
    _write_manifest_atomic(manifest_path, data)


def complete_prepared_receipt(manifest_path: Path, target: str,
                              book_dir: Path) -> None:
    """Finalize a prepared book by consuming its latest prepared receipt (P0-2).

    The successful path must NOT re-hash whatever currently exists: a mutation
    between publish and receipt could otherwise be blessed as the new accepted
    state. Instead we:
      - require the latest receipt for `target` to be a prepared receipt;
      - require every prepared output file to exist and match the prepared
        expected SHA exactly (else BLOCKED);
      - write a completed receipt that COPIES the prepared output_shas
        (never re-defines the expected content) and appends to the global chain
        tail, immutably referencing the consumed prepared receipt.
    """
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise LedgerCorruptionError(f"run manifest unreadable: {manifest_path}: {e}") from e
    if not isinstance(data, dict):
        raise LedgerCorruptionError(f"run manifest not an object: {manifest_path}")
    run_id = data.get("run_id", "")
    receipts = data.setdefault("book_receipts", [])
    # Latest receipt for this target.
    latest = None
    for r in receipts:
        if isinstance(r, dict) and r.get("target") == target:
            latest = r
    if latest is None or latest.get("status") != "prepared":
        raise LedgerCorruptionError(
            f"cannot complete {target!r}: latest receipt is not 'prepared'")
    expected = latest.get("output_shas", {})
    if not expected:
        raise LedgerCorruptionError(
            f"cannot complete {target!r}: prepared receipt has no output_shas")
    # Verify current published files exist and match the prepared expected SHA.
    for fname, fsha in expected.items():
        f = Path(book_dir) / fname
        if not f.exists():
            raise LedgerCorruptionError(
                f"cannot complete {target!r}: output missing {fname!r}")
        if _sha256_file(f) != fsha:
            raise LedgerCorruptionError(
                f"cannot complete {target!r}: {fname!r} does not match prepared "
                f"SHA (BLOCKED -- content changed since prepared)")
    # Append completed to the GLOBAL chain tail, copying prepared's SHA set and
    # referencing the prepared receipt it consumes.
    prev = receipts[-1]["sha"]
    prepared_sha = latest["sha"]
    csha = _receipt_sha(prev, run_id, target, "completed", expected, prepared_sha)
    receipts.append({"target": target, "status": "completed",
                     "output_shas": expected, "prepared_sha": prepared_sha,
                     "prev_sha": prev, "sha": csha})
    _write_manifest_atomic(manifest_path, data)


def clear_run_manifest(manifest_path: Path, ledger_path: Path | None = None) -> None:
    """Clear a finished run's manifest (and ledger) so the next run is fresh.

    Called after a FULLY successful run. The ledger is removed FIRST (Medium):
    if the manifest deletion then fails, the next run finds the stale manifest,
    re-derives its identity, and resumes fail-closed with a fresh ledger
    (calls_made=0). Removing the manifest first would leave an orphaned ledger
    whose stale identity mismatches the next run and blocks it; ledger-first
    avoids that deadlock without weakening fail-closed guarantees.
    """
    if ledger_path is not None:
        ledger_path.unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)


# Canonical upstream generation-chain fingerprints (P0-4). 'recovered'
# upstream provenance must prove the artifacts were produced by the frozen
# prompts and config below, so these SHAs are recomputed here rather than
# trusted from the provenance record.
_CANONICAL_PROMPT_SOURCE = (
    RULE_PROMPT + "\0" + MCQ_PROMPT + "\0" + PER_RULE_MCQ_PROMPT
)


def canonical_prompt_sha256() -> str:
    """SHA-256 of the frozen canonical distillation prompts (P0-4)."""
    return hashlib.sha256(_CANONICAL_PROMPT_SOURCE.encode("utf-8")).hexdigest()


def canonical_config_sha256() -> str:
    """SHA-256 of the frozen canonical model config (P0-3/P0-4).

    Hashes FROZEN_MODEL_CONFIG -- the SAME constant _call() uses to build the
    API payload -- so the fingerprint always matches what is actually sent.
    """
    canonical = json.dumps(
        FROZEN_MODEL_CONFIG, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _pid_alive(pid) -> bool:
    if pid is None or pid <= 0: return False
    if os.name == "nt":
        r = _subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
        return "No tasks" not in r.stdout
    try: os.kill(pid, 0); return True
    except OSError: return False


class FileLock:
    def __init__(self, path, lease=3600): self.path = Path(path); self.lease = lease; self._held = False
    def __enter__(self):
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"pid": os.getpid(), "start": time.time(), "owner": f"p{os.getpid()}t{time.time():.0f}"}).encode())
                os.close(fd); self._held = True; return self
            except FileExistsError:
                if self._stale(): os.unlink(str(self.path)); continue
                raise RuntimeError(f"lock held by live writer: {self.path}")
    def __exit__(self, *a):
        if self._held: os.unlink(str(self.path)); self._held = False
    def _stale(self) -> bool:
        try: meta = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: return False
        return time.time() - meta.get("start", 0) > self.lease and not _pid_alive(meta.get("pid", -1)) and str(meta.get("owner", "")).startswith("p")


@dataclasses.dataclass(frozen=True)
class BudgetCtx:
    run_id: str; batch_id: str; proj: "ProjectLedger"; run: "BudgetLedger"; proj_path: Path; run_path: Path


def attempt_base_id(*, run_id, batch_id, chapter_id, segment_id, operation, rule_id) -> str:
    return hashlib.sha256(json.dumps({"run_id": run_id, "batch_id": batch_id, "chapter_id": chapter_id, "segment_id": segment_id, "operation": operation, "rule_id": rule_id}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def attempt_id_for(*, run_id, batch_id, chapter_id, segment_id, operation, rule_id, attempt_no) -> str:
    return hashlib.sha256(json.dumps({"run_id": run_id, "batch_id": batch_id, "chapter_id": chapter_id, "segment_id": segment_id, "operation": operation, "rule_id": rule_id, "attempt_no": attempt_no}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def next_attempt_no(run, *, base_id, proj=None):
    """P0-4：跳过 project 已 reservation 的 attempt number，防止 orphan 死锁。"""
    run_used = max((st.get("attempt_no", 0) for st in run.attempts.values() if st.get("base_id") == base_id), default=0)
    if proj is None: return run_used + 1
    proj_used = 0
    for r in proj.reservations.values():
        m = r.get("metadata") or {}
        if not isinstance(m, dict): continue
        try:
            b = attempt_base_id(run_id=m["run_id"], batch_id=m["batch_id"], chapter_id=m["chapter_id"], segment_id=m["segment_id"], operation=m["operation"], rule_id=m["rule_id"])
        except Exception:
            continue
        if b == base_id:
            proj_used = max(proj_used, int(m.get("attempt_no", 0)))
    return max(run_used, proj_used) + 1


ALREADY_RESERVED = object()
_TERMINAL_STATES = ("success", "failed", "interrupted")
_ATTEMPT_STATUSES = ("attempted",) + _TERMINAL_STATES


def _ledger_hash(state: dict) -> str:
    s = dict(state); s.pop("ledger_hash", None)
    return hashlib.sha256(json.dumps(s, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate_ledger_state(data) -> None:
    if not isinstance(data, dict): raise LedgerCorruptionError("ledger not a dict")
    if data.get("ledger_hash") != _ledger_hash(data): raise LedgerCorruptionError("ledger hash mismatch (self-consistent tamper detected)")


def _atomic_write_json(path, obj):
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _validate_attempt_metadata(m) -> None:
    if not isinstance(m, dict): raise LedgerCorruptionError("attempt metadata not a dict")
    for k in ("operation", "chapter_id", "segment_id", "rule_id", "attempt_no", "run_id", "batch_id"):
        if k not in m: raise LedgerCorruptionError(f"attempt metadata missing {k}")
    if not isinstance(m["attempt_no"], int) or m["attempt_no"] < 1: raise LedgerCorruptionError("attempt metadata attempt_no invalid")


def _verify_attempt_id(run_id, batch_id, attempt_id, metadata) -> None:
    recomputed = attempt_id_for(run_id=run_id, batch_id=batch_id, chapter_id=metadata["chapter_id"], segment_id=metadata["segment_id"], operation=metadata["operation"], rule_id=metadata["rule_id"], attempt_no=metadata["attempt_no"])
    if recomputed != attempt_id: raise LedgerCorruptionError(f"attempt_id {attempt_id} does not bind metadata (expected {recomputed})")


def _validate_run_attempts(run_id, attempts) -> None:
    if not isinstance(attempts, dict): raise LedgerCorruptionError("attempts not a dict")
    for att_id, st in attempts.items():
        if not isinstance(st, dict): raise LedgerCorruptionError(f"attempt {att_id} not a dict")
        if st.get("status") not in _ATTEMPT_STATUSES: raise LedgerCorruptionError(f"attempt {att_id} invalid status {st.get('status')!r}")
        if not isinstance(st.get("attempt_no"), int) or st.get("attempt_no", 0) < 1: raise LedgerCorruptionError(f"attempt {att_id} invalid attempt_no")
        if not isinstance(st.get("base_id"), str) or len(st.get("base_id", "")) != 64: raise LedgerCorruptionError(f"attempt {att_id} invalid base_id")
        meta = st.get("metadata")
        if meta is None: raise LedgerCorruptionError(f"attempt {att_id} metadata must not be None")
        _validate_attempt_metadata(meta)
        _verify_attempt_id(run_id, st.get("batch_id", ""), att_id, meta)
        recomputed_base = attempt_base_id(run_id=run_id, batch_id=st.get("batch_id", ""), chapter_id=meta["chapter_id"], segment_id=meta["segment_id"], operation=meta["operation"], rule_id=meta["rule_id"])
        if recomputed_base != st.get("base_id"): raise LedgerCorruptionError(f"attempt {att_id} base_id does not bind metadata")


def verify_attempt_metadata_consistency(proj, run, attempt_id) -> None:
    pr = proj.reservations.get(attempt_id); ra = run.attempts.get(attempt_id)
    if pr is None or ra is None: return
    _validate_attempt_metadata(pr.get("metadata")); _validate_attempt_metadata(ra.get("metadata"))
    if pr.get("metadata") != ra.get("metadata"): raise LedgerCorruptionError(f"attempt metadata mismatch for {attempt_id}")


class LedgerCorruptionError(RuntimeError):
    pass


class ProjectLedger:
    def __init__(self, experiment_id, total_cap, calls_made=0, reservations=None):
        self.experiment_id = experiment_id; self.total_cap = total_cap; self.calls_made = calls_made; self.reservations = reservations or {}

    @classmethod
    def load_or_create(cls, path, experiment_id, total_cap):
        if path and os.path.exists(path):
            try: data = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception as e: raise LedgerCorruptionError(f"project ledger JSON unparseable: {e}") from e
            _validate_ledger_state(data)
            if data.get("experiment_id") != experiment_id: raise ValueError("project ledger experiment_id mismatch")
            if data.get("total_cap") != total_cap: raise LedgerCorruptionError(f"project ledger cap mismatch: stored={data.get('total_cap')}, requested={total_cap}")
            if not isinstance(data.get("calls_made"), int) or data["calls_made"] < 0: raise LedgerCorruptionError("project calls_made invalid")
            if not isinstance(data.get("reservations"), dict): raise LedgerCorruptionError("project reservations not a dict")
            if data["calls_made"] != len(data["reservations"]): raise LedgerCorruptionError("project calls_made != len(reservations)")
            for att_id, r in data["reservations"].items():
                if not isinstance(r, dict): raise LedgerCorruptionError(f"reservation {att_id} not a dict")
                if r.get("metadata") is None: raise LedgerCorruptionError(f"reservation {att_id} metadata must not be None")
                _validate_attempt_metadata(r.get("metadata"))
                _verify_attempt_id(r.get("metadata")["run_id"], r.get("metadata")["batch_id"], att_id, r.get("metadata"))
            return cls(experiment_id, total_cap, data["calls_made"], data.get("reservations"))
        return cls(experiment_id, total_cap)

    def _state(self): return {"experiment_id": self.experiment_id, "total_cap": self.total_cap, "calls_made": self.calls_made, "reservations": self.reservations}
    def _persist(self, path): state = self._state(); state["ledger_hash"] = _ledger_hash(state); _atomic_write_json(path, state)

    def before_call(self, attempt_id, path, metadata=None):
        if metadata is None: raise LedgerCorruptionError("project metadata must not be None")
        _validate_attempt_metadata(metadata)
        _verify_attempt_id(metadata["run_id"], metadata["batch_id"], attempt_id, metadata)
        with FileLock(str(path) + ".lock"):
            fresh = self.load_or_create(path, self.experiment_id, self.total_cap)
            existing = fresh.reservations.get(attempt_id)
            if existing is not None:
                if existing.get("metadata") != metadata: raise LedgerCorruptionError(f"project duplicate attempt metadata mismatch for {attempt_id}")
                return ALREADY_RESERVED
            if fresh.calls_made + 1 > fresh.total_cap: raise RuntimeError("project budget exhausted")
            fresh.calls_made += 1
            fresh.reservations[attempt_id] = {"status": "reserved", "metadata": metadata}
            fresh._persist(path); self.__dict__.update(fresh.__dict__); return None

    def remaining(self): return self.total_cap - self.calls_made


class BudgetLedger:
    """Run-level API budget ledger (new stage-5 schema) merged with the legacy
    interface (summary()/exhausted/in-memory record_call) so regen_mcq.py and
    the existing remediation test suite keep working while run_sanming_batch uses
    the new attempts/legacy_calls budget-ctx path."""

    def __init__(self, global_hard_cap, persist_path=None, run_id="", code_sha="", rules_sha="", attempts=None):
        self.global_hard_cap = global_hard_cap
        self.persist_path = Path(persist_path) if persist_path else None
        self.run_id = run_id; self.code_sha = code_sha; self.rules_sha = rules_sha
        self.calls_made = 0; self.accepted = 0; self.skipped = 0; self.exhausted = 0
        self.legacy_calls = 0
        self.attempts = attempts or {}

    def _state(self):
        return {"global_hard_cap": self.global_hard_cap, "calls_made": self.calls_made, "accepted": self.accepted,
                "skipped": self.skipped, "exhausted": self.exhausted, "run_id": self.run_id, "code_sha": self.code_sha,
                "rules_sha": self.rules_sha, "legacy_calls": self.legacy_calls, "attempts": self.attempts}

    @classmethod
    def load_or_create(cls, path, global_hard_cap, run_id="", code_sha="", rules_sha=""):
        if path and os.path.exists(path):
            try: data = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception as e: raise LedgerCorruptionError(f"run ledger JSON unparseable: {e}") from e
            _validate_ledger_state(data)
            for k in ("run_id", "code_sha", "rules_sha"):
                if not data.get(k): raise LedgerCorruptionError(f"run ledger missing binding field {k}")
            if data["run_id"] != run_id or data["code_sha"] != code_sha or data["rules_sha"] != rules_sha:
                raise LedgerCorruptionError("run ledger identity drift")
            if data["global_hard_cap"] != global_hard_cap: raise LedgerCorruptionError("run ledger cap mismatch")
            if not isinstance(data["calls_made"], int) or data["calls_made"] < 0: raise LedgerCorruptionError("run calls_made invalid")
            for k in ("accepted", "skipped", "exhausted", "legacy_calls"):
                if not isinstance(data.get(k, 0), int) or data.get(k, 0) < 0: raise LedgerCorruptionError(f"run {k} invalid")
            attempts = data.get("attempts", {})
            _validate_run_attempts(run_id, attempts)
            if data["calls_made"] != len(attempts): raise LedgerCorruptionError("run calls_made != len(attempts)")
            led = cls(global_hard_cap, persist_path=path, run_id=run_id, code_sha=code_sha, rules_sha=rules_sha, attempts=attempts)
            led.calls_made = data["calls_made"]; led.accepted = data.get("accepted", 0); led.skipped = data.get("skipped", 0)
            led.exhausted = data.get("exhausted", 0); led.legacy_calls = data.get("legacy_calls", 0)
            return led
        # P0-1（向后兼容合并）：新建持久化账本必须冻结身份，缺绑定即拒绝
        if path is not None:
            for k in ("run_id", "code_sha", "rules_sha"):
                if not locals().get(k):
                    raise LedgerCorruptionError(f"ledger binding field {k!r} must be provided when persisting to {path} (refusing a ledger without a frozen identity)")
        return cls(global_hard_cap, persist_path=path, run_id=run_id, code_sha=code_sha, rules_sha=rules_sha)

    def save(self):
        if self.persist_path is None: return
        data = self._state(); data["ledger_hash"] = _ledger_hash(data)
        tmp = self.persist_path.parent / f".{self.persist_path.name}.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try: tmp.replace(self.persist_path)
        except Exception: tmp.unlink(missing_ok=True); raise

    def _locked_mutate(self, path, mutate):
        if not (path or self.persist_path):
            mutate(self)  # 内存态（无持久化），兼容旧用法
            return
        with FileLock(str(path or self.persist_path) + ".lock"):
            fresh = BudgetLedger.load_or_create(path or self.persist_path, self.global_hard_cap, self.run_id, self.code_sha, self.rules_sha)
            mutate(fresh)
            if path:
                data = fresh._state(); data["ledger_hash"] = _ledger_hash(data); _atomic_write_json(path, data)
            else:
                fresh.save()
            self.__dict__.update(fresh.__dict__)

    def record_attempt(self, attempt_id, path=None, base_id=None, attempt_no=None, metadata=None, batch_id=""):
        if metadata is None: raise LedgerCorruptionError("run metadata must not be None")
        _validate_attempt_metadata(metadata); _verify_attempt_id(self.run_id, batch_id, attempt_id, metadata)
        def _m(fresh):
            existing = fresh.attempts.get(attempt_id)
            if existing is not None:
                if existing.get("status") in _TERMINAL_STATES: raise LedgerCorruptionError(f"record_attempt after terminal for {attempt_id}")
                if existing.get("metadata") != metadata: raise LedgerCorruptionError(f"run record_attempt metadata mismatch for {attempt_id}")
                return
            if fresh.calls_made + fresh.legacy_calls + 1 > fresh.global_hard_cap: raise RuntimeError("run budget exhausted")
            fresh.attempts[attempt_id] = {"status": "attempted", "base_id": base_id, "batch_id": batch_id, "attempt_no": attempt_no, "metadata": metadata}
            fresh.calls_made += 1
        self._locked_mutate(path, _m)

    def record_terminal(self, attempt_id, status, path=None):
        if status not in _TERMINAL_STATES: raise LedgerCorruptionError(f"invalid terminal status {status!r}")
        def _m(fresh):
            existing = fresh.attempts.get(attempt_id)
            if existing is None: raise LedgerCorruptionError(f"terminal for missing attempt {attempt_id}")
            if existing.get("status") in _TERMINAL_STATES: raise LedgerCorruptionError(f"terminal re-transition for {attempt_id}: {existing['status']} -> {status}")
            existing["status"] = status; fresh.attempts[attempt_id] = existing
        self._locked_mutate(path, _m)

    def record_call(self, path=None):
        """P0-5：legacy 路径弃用——改用 before_legacy_call 锁内原子 cap 检查。保留为兼容桩，新代码不用。"""
        self.before_legacy_call(path=path)

    def before_legacy_call(self, path=None):
        """P0-5：legacy 路径原子 cap 检查 + 计数（同一锁内，无 TOCTOU）。"""
        def _m(fresh):
            if fresh.calls_made + fresh.legacy_calls + 1 > fresh.global_hard_cap: raise RuntimeError("run budget exhausted")
            fresh.legacy_calls += 1
        self._locked_mutate(path, _m)

    def can_call(self):
        ok = self.calls_made + self.legacy_calls < self.global_hard_cap
        if not ok: self.exhausted = True
        return ok

    def record_accept(self, path=None):
        def _m(fresh): fresh.accepted += 1
        self._locked_mutate(path, _m)
    def record_skip(self, path=None):
        def _m(fresh): fresh.skipped += 1
        self._locked_mutate(path, _m)
    def has_terminal(self, attempt_id): return self.attempts.get(attempt_id, {}).get("status") in _TERMINAL_STATES

    def summary(self) -> dict:
        return {"calls_made": self.calls_made, "accepted": self.accepted, "skipped": self.skipped,
                "exhausted": self.exhausted, "remaining": max(0, self.global_hard_cap - (self.calls_made + self.legacy_calls)),
                "legacy_calls": self.legacy_calls, "attempts": len(self.attempts), "run_id": self.run_id}


def call_with_budget(fn, *, proj, run, attempt_id, project_path, run_path=None, base_id=None, attempt_no=None, metadata=None, batch_id=""):
    if metadata is None: raise LedgerCorruptionError("metadata must not be None")
    _validate_attempt_metadata(metadata)
    if proj.before_call(attempt_id, path=project_path, metadata=metadata) == ALREADY_RESERVED: raise RuntimeError("duplicate attempt_id: refusing external call")
    run.record_attempt(attempt_id, path=run_path, base_id=base_id, attempt_no=attempt_no, metadata=metadata, batch_id=batch_id)
    try: out = fn()
    except Exception as e: run.record_terminal(attempt_id, "failed", path=run_path); raise
    run.record_terminal(attempt_id, "success", path=run_path)
    return out


def reserved_unattributed(proj, run): return set(proj.reservations) - set(run.attempts)
def interrupted_unknown(run): return {a for a, st in run.attempts.items() if st.get("status") == "attempted"}
_POLARITY_PAIRS = [
    ("喜", "忌"),
    ("吉", "凶"),
    ("宜", "不宜"),
    ("有利", "不利"),
    ("为吉", "为凶"),
    ("主吉", "主凶"),
]

# Bazi subject characters for polarity-target binding extraction.
_BAZI_TARGET_CHARS = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥金木水火土"


def _extract_polarity_bindings(text: str) -> list[tuple[str, str]]:
    """Extract polarity-target bindings from text (P0-1).

    Returns [(polarity_marker, target_char), ...].

    For example "甲木喜水滋养，忌金克" ->
        [("喜", "水"), ("忌", "金")]

    This binds polarity to a SPECIFIC target, not just "polarity appears
    anywhere". The strict check then verifies the answer option does not
    bind the OPPOSITE polarity to the SAME target.
    """
    bindings: list[tuple[str, str]] = []
    for pos, neg in _POLARITY_PAIRS:
        for marker in (pos, neg):
            for m in re.finditer(marker + f"([{_BAZI_TARGET_CHARS}])", text):
                bindings.append((marker, m.group(1)))
    return bindings


def _polarity_opposite(marker: str) -> str | None:
    """Return the opposite polarity marker, or None if not a polarity."""
    for pos, neg in _POLARITY_PAIRS:
        if marker == pos:
            return neg
        if marker == neg:
            return pos
    return None


def _mcq_prefilter(mcq: dict, rule: dict) -> bool:
    """Low-cost prefilter: 2-char substring overlap (P0-1).

    This is NOT a semantic proof. It only filters out obviously unrelated
    MCQs. MCQs that pass this prefilter must still pass _mcq_strict_consistency
    to enter the clean set. MCQs that fail the prefilter are dropped entirely.

    Returns True if overlap is found (or if the rule has no checkable content,
    letting the strict check handle it). Returns False if the MCQ is obviously
    unrelated.
    """
    rule_text = _norm(
        " ".join(str(rule.get(f, "")) for f in
                 ("subject", "condition", "rule", "original_text"))
    )
    if len(rule_text) < 2:
        return True

    mcq_text = _norm(
        str(mcq.get("question", "")) + str(mcq.get("explanation", ""))
    )
    if len(mcq_text) < 2:
        return False

    for i in range(len(rule_text) - 1):
        if rule_text[i:i + 2] in mcq_text:
            return True
    return False


def _mcq_strict_consistency(mcq: dict, rule: dict) -> bool:
    """Strict semantic consistency check (P0-1).

    Returns True only if ALL checks pass:
      1. Subject present and matches question. Subject missing or too short
         -> returns False (MCQ enters semantic_unaudited, NOT auto-pass).
      2. Answer option exists and its text is checked against rule polarity.
      3. Polarity-target binding: if rule says "喜水", answer option must not
         say "忌水" (opposite polarity bound to same target).
      4. Global polarity contradiction (fallback): if rule has 喜 but not 忌,
         MCQ (question+explanation+answer_option) must not have 忌 without 喜.
      5. Answer-option support: the answer option text must share at least
         one bazi target char or polarity binding with the rule. An answer
         unrelated to the rule (e.g. "甲木性刚" when rule says "甲木喜水")
         cannot be proven correct -> semantic_unaudited.
      6. Explanation support: the explanation must share at least one
         content token (2-char substring) with the answer option text,
         proving the explanation actually supports the chosen answer.

    Returns False if any check fails or cannot be verified (conservative).
    MCQs failing this check enter semantic_unaudited quarantine, NOT the
    clean set.
    """
    rule_text = _norm(
        " ".join(str(rule.get(f, "")) for f in
                 ("subject", "condition", "rule", "original_text"))
    )
    question = _norm(str(mcq.get("question", "")))
    explanation = _norm(str(mcq.get("explanation", "")))

    # Cannot verify -> conservative False
    if len(rule_text) < 2:
        return False
    if len(question) < 2:
        return False

    # Check 1: Subject must be present and match question.
    # subject 缺失时不能自动通过，判 semantic_unaudited。
    subject = _norm(str(rule.get("subject", "")))
    if not subject or len(subject) < 2:
        return False
    found = any(subject[i:i + 2] in question for i in range(len(subject) - 1))
    if not found:
        return False  # Subject mismatch

    # Check 2: Answer option must exist; its text is the primary semantic
    # payload and must be polarity-consistent with the rule.
    answer = mcq.get("answer", "")
    options = mcq.get("options", {})
    if not isinstance(options, dict) or answer not in options:
        return False
    answer_text = _norm(str(options[answer]))
    if not answer_text:
        return False

    # Check 3: Polarity-target binding contradiction across the FULL MCQ.
    # If rule says "喜水", NO part of the MCQ (question, explanation, or
    # answer option) may say "忌水" (opposite polarity bound to same target).
    # This is stricter than the global check: it binds polarity to a specific
    # bazi target character, and checks ALL MCQ text, not just the answer
    # option -- otherwise a question that contradicts the rule could pass
    # when the answer option happens to be correct.
    rule_bindings = _extract_polarity_bindings(rule_text)
    mcq_bindings = (
        _extract_polarity_bindings(question)
        + _extract_polarity_bindings(explanation)
        + _extract_polarity_bindings(answer_text)
    )
    for r_marker, r_target in rule_bindings:
        r_opposite = _polarity_opposite(r_marker)
        if r_opposite is None:
            continue
        for m_marker, m_target in mcq_bindings:
            if m_marker == r_opposite and m_target == r_target:
                return False  # opposite polarity on same target

    # Check 4: Global polarity contradiction (fallback, covers cases where
    # binding extraction misses a pattern). Uses answer_text (not just
    # question+explanation) so a wrong answer option is caught.
    mcq_full = question + explanation + answer_text
    for pos, neg in _POLARITY_PAIRS:
        rule_pos = pos in rule_text
        rule_neg = neg in rule_text
        mcq_pos = pos in mcq_full
        mcq_neg = neg in mcq_full
        # Rule positive-only, MCQ negative-only -> contradiction
        if rule_pos and not rule_neg and mcq_neg and not mcq_pos:
            return False
        # Rule negative-only, MCQ positive-only -> contradiction
        if rule_neg and not rule_pos and mcq_pos and not mcq_neg:
            return False

    # Check 5 (P0-1): Answer-option support. The answer option must be
    # traceable to the rule via shared bazi target chars or shared polarity
    # bindings. Without this, an unrelated answer ("甲木性刚" when rule is
    # "甲木喜水") passes just because it does not contradict.
    if not _answer_supported_by_rule(answer_text, rule_text, rule_bindings, subject):
        return False

    # Check 6 (P0-1): Explanation support. The explanation must share at
    # least one 2-char content token with the answer option text, proving
    # the explanation actually addresses the chosen answer (not just the
    # topic in general).
    if not _explanation_supports_answer(explanation, answer_text):
        return False

    return True


def _answer_supported_by_rule(
    answer_text: str,
    rule_text: str,
    rule_bindings: list[tuple[str, str]],
    subject: str = "",
) -> bool:
    """Check 5 helper: answer option must be supported by the rule (P0-1).

    Support is established if ANY of:
      a) answer shares a polarity binding target with the rule
         (e.g. rule "喜水", answer "喜水" -> shared target 水);
      b) answer contains a bazi char that is a polarity TARGET in the rule
         (not just any bazi char -- the subject chars alone don't count,
         e.g. "甲木" is subject, "水" is the rule's claim);
      c) answer shares any 2-char substring with the rule text that is NOT
         entirely contained in the subject (fallback for rules without
         explicit polarity targets).

    Returns False if no support relation can be established.
    """
    if not answer_text or not rule_text:
        return False

    # (a) Shared polarity binding target
    answer_bindings = _extract_polarity_bindings(answer_text)
    rule_targets = {t for _, t in rule_bindings}
    answer_targets = {t for _, t in answer_bindings}
    if rule_targets & answer_targets:
        return True

    # (b) Answer contains a bazi char that is a polarity target in the rule.
    # This is stricter than "any shared bazi char" -- it requires the answer
    # to address the specific target the rule makes a claim about.
    if rule_targets:
        answer_bazi = {c for c in answer_text if c in _BAZI_TARGET_CHARS}
        if rule_targets & answer_bazi:
            return True

    # (c) Fallback: 2-char substring overlap, excluding substrings that are
    # entirely within the subject (subject chars alone don't prove the answer
    # addresses the rule's claim).
    subj = _norm(subject)
    for i in range(len(rule_text) - 1):
        sub = rule_text[i:i + 2]
        if sub in answer_text:
            # Skip if this 2-char substring is part of the subject
            if subj and sub in subj:
                continue
            return True

    return False


def _explanation_supports_answer(explanation: str, answer_text: str) -> bool:
    """Check 6 helper: explanation must support the answer option (P0-1).

    The explanation must share at least one 2-char content token with the
    answer option text. This proves the explanation actually addresses the
    chosen answer, not just the general topic.

    Returns False if no support relation can be established.
    """
    if not explanation or not answer_text:
        return False
    if len(explanation) < 2 or len(answer_text) < 2:
        return False
    for i in range(len(explanation) - 1):
        if explanation[i:i + 2] in answer_text:
            return True
    for i in range(len(answer_text) - 1):
        if answer_text[i:i + 2] in explanation:
            return True
    return False


MAX_RULES_PER_SEGMENT = 8; MAX_RULE_EXTRACTION_ATTEMPTS = 3; MAX_MCQ_ATTEMPTS_PER_RULE = 3; MAX_PROMPT_CHARS = 8000; MAX_REQUEST_BYTES = 16000

class RuleOverflowError(RuntimeError): pass
class RetryableModelOutputError(RuntimeError): pass

class RetryExhaustedError(RuntimeError):
    """retry 耗尽，保留原始 cause chain；classify_failure_for_resume 遍历 cause 链判断可重试。"""
    def __init__(self, message, cause=None):
        super().__init__(message)
        self.cause = cause

def sha256_bytes(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

def safe_batch_hard_cap(total_segments, max_rule_extraction_attempts, max_rules_per_segment, max_mcq_attempts_per_rule) -> int:
    return total_segments * max_rule_extraction_attempts + total_segments * max_rules_per_segment * max_mcq_attempts_per_rule

def enforce_budget_before_call(n_rules, operation):
    if operation == "rules" and n_rules > MAX_RULES_PER_SEGMENT: raise RuleOverflowError(f"segment returned {n_rules} rules > {MAX_RULES_PER_SEGMENT}")

def _parse_rules_retryable(response):
    try: data = json.loads(response) if isinstance(response, str) else None
    except Exception as e: raise RetryableModelOutputError(f"rules JSON unparseable: {e}") from e
    if not isinstance(data, list): raise RetryableModelOutputError("rules output not a list")
    if not data: raise RetryableModelOutputError("rules output empty")
    if len(data) > MAX_RULES_PER_SEGMENT: raise RetryableModelOutputError(f"rules count {len(data)} > {MAX_RULES_PER_SEGMENT}")
    for i, r in enumerate(data):
        if not isinstance(r, dict): raise RetryableModelOutputError(f"rule {i} not a dict")
        for k in ("rule", "condition", "subject", "original_text"):
            v = r.get(k)
            if not isinstance(v, str) or not v.strip(): raise RetryableModelOutputError(f"rule {i} field {k} must be non-empty string")
    return data

def _parse_mcq_retryable(response):
    try: obj = json.loads(response) if isinstance(response, str) else None
    except Exception as e: raise RetryableModelOutputError(f"mcq JSON unparseable: {e}") from e
    if not isinstance(obj, dict): raise RetryableModelOutputError("mcq output not a dict")
    if not isinstance(obj.get("question"), str) or not obj["question"].strip(): raise RetryableModelOutputError("mcq question must be non-empty string")
    opts = obj.get("options")
    if not isinstance(opts, dict): raise RetryableModelOutputError("mcq options must be an object")
    if set(opts.keys()) != {"A", "B", "C", "D"}: raise RetryableModelOutputError("mcq options must be exactly A/B/C/D")
    for k in ("A", "B", "C", "D"):
        if not isinstance(opts.get(k), str) or not opts[k].strip(): raise RetryableModelOutputError(f"mcq option {k} must be non-empty string")
    answer = obj.get("answer")
    if answer not in ("A", "B", "C", "D"): raise RetryableModelOutputError("mcq answer must be A/B/C/D")
    if not isinstance(obj.get("explanation"), str) or not obj["explanation"].strip(): raise RetryableModelOutputError("mcq explanation must be non-empty string")
    return obj

def is_retryable_error(e) -> bool:
    if isinstance(e, RetryableModelOutputError): return True
    if isinstance(e, (ConnectionError, TimeoutError)): return True
    msg = str(e).lower()
    return "network down" in msg or "timeout" in msg or "rate limit" in msg or "429" in msg or "temporarily unavailable" in msg or "connection" in msg

def retry_call_with_budget(fn, *, proj, run, run_id, batch_id, chapter_id, segment_id, operation, rule_id, base_id, max_attempts, project_path, run_path=None):
    start = next_attempt_no(run, base_id=base_id, proj=proj)   # P0-4：跳过 project 已 reservation 的 attempt number
    if start > max_attempts: raise RetryExhaustedError("attempts exhausted")
    last = None
    for attempt_no in range(start, max_attempts + 1):
        att = attempt_id_for(run_id=run_id, batch_id=batch_id, chapter_id=chapter_id, segment_id=segment_id, operation=operation, rule_id=rule_id, attempt_no=attempt_no)
        # P0-2：metadata 持久化 run_id/batch_id，project 层才能复算 attempt_id
        meta = {"operation": operation, "chapter_id": chapter_id, "segment_id": segment_id, "rule_id": rule_id, "attempt_no": attempt_no, "run_id": run_id, "batch_id": batch_id}
        try:
            return call_with_budget(fn, proj=proj, run=run, attempt_id=att, project_path=project_path, run_path=run_path, base_id=base_id, batch_id=batch_id, attempt_no=attempt_no, metadata=meta)
        except Exception as e:
            if not is_retryable_error(e): raise
            if attempt_no >= max_attempts: raise RetryExhaustedError("attempts exhausted") from e
            last = e
    raise RetryExhaustedError("attempts exhausted") from last


@dataclasses.dataclass(frozen=True)
class PromptLimits:
    max_prompt_chars: int = MAX_PROMPT_CHARS
    max_request_bytes: int = MAX_REQUEST_BYTES

class PromptLimitError(RuntimeError): pass

@dataclasses.dataclass(frozen=True)
class Segment:
    text: str; char_start: int; char_end: int; segment_index: int

def render_rule_prompt(text, book, chapter):
    return (RULE_PROMPT.replace("__BOOK__", book).replace("__CH__", chapter).replace("__TEXT__", text))

def validate_segment(text, *, book, chapter, limits):
    prompt = render_rule_prompt(text, book, chapter)
    if len(text) > limits.max_prompt_chars: raise PromptLimitError(f"segment text {len(text)} > {limits.max_prompt_chars} chars")
    if len(prompt) > limits.max_prompt_chars: raise PromptLimitError(f"prompt {len(prompt)} > {limits.max_prompt_chars} chars")
    if len(prompt.encode("utf-8")) > limits.max_request_bytes: raise PromptLimitError(f"prompt bytes {len(prompt.encode('utf-8'))} > {limits.max_request_bytes}")

def _validate_ok(text, book, chapter, limits):
    try: validate_segment(text, book=book, chapter=chapter, limits=limits); return True
    except PromptLimitError: return False

def _split_to_max_prefix(part, book, chapter, limits) -> list[str]:
    if _validate_ok(part, book, chapter, limits): return [part]
    pieces = re.split(r"(?<=[。？！；])", part)
    if len(pieces) <= 1:
        lo, hi = 0, len(part)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _validate_ok(part[:mid], book, chapter, limits): lo = mid
            else: hi = mid - 1
        if lo <= 0: raise PromptLimitError("single char exceeds limits")
        return [part[:lo]] + _split_to_max_prefix(part[lo:], book, chapter, limits)
    out, cur = [], ""
    for piece in pieces:
        if not piece: continue
        if _validate_ok(cur + piece, book, chapter, limits): cur += piece
        else:
            if cur: out.append(cur); cur = ""
            out.extend(_split_to_max_prefix(piece, book, chapter, limits))
    if cur: out.append(cur)
    return out

def segment_chapter(text, *, book, chapter, limits):
    parts = _split_to_max_prefix(text, book, chapter, limits)
    segs, start = [], 0
    for i, part in enumerate(parts):
        segs.append(Segment(text=part, char_start=start, char_end=start + len(part), segment_index=i)); start += len(part)
    if start != len(text) or "".join(s.text for s in segs) != text: raise PromptLimitError("segmentation conservation violated")
    return segs

def distill_segments(segments, *, book, chapter, limits, ledger=None, budget_ctx=None, chapter_id=0):
    all_rules = []
    for seg in segments:
        validate_segment(seg.text, book=book, chapter=chapter, limits=limits)
        rules = distill_chapter(seg.text, book, chapter, ledger=ledger, budget_ctx=budget_ctx, segment_id=seg.segment_index, chapter_id=chapter_id)
        enforce_budget_before_call(len(rules), "rules")
        for r in rules: r["segment_index"] = seg.segment_index
        all_rules.extend(rules)
    return all_rules

def distill_chapter(text, book, chapter, ledger=None, *, budget_ctx=None, segment_id=0, chapter_id=0):
    prompt = render_rule_prompt(text, book, chapter)
    if budget_ctx is None:
        if ledger is not None:
            try: ledger.before_legacy_call()   # P0-5：锁内原子 cap 检查 + 计数
            except RuntimeError: return []
        try: rules = _parse_rules_retryable(_call(prompt))
        except RetryableModelOutputError: return []
    else:
        rules = retry_call_with_budget(
            lambda: _parse_rules_retryable(_call(prompt)),
            proj=budget_ctx.proj, run=budget_ctx.run, run_id=budget_ctx.run_id, batch_id=budget_ctx.batch_id,
            chapter_id=chapter_id, segment_id=segment_id, operation="rules", rule_id=None,
            base_id=attempt_base_id(run_id=budget_ctx.run_id, batch_id=budget_ctx.batch_id, chapter_id=chapter_id, segment_id=segment_id, operation="rules", rule_id=None),
            max_attempts=MAX_RULE_EXTRACTION_ATTEMPTS, project_path=budget_ctx.proj_path, run_path=budget_ctx.run_path)
    for r in rules:
        r.setdefault("source_book", book); r.setdefault("source_chapter", chapter); r.setdefault("category", "classic"); r.pop("id", None)
    return rules

def classify_failure_for_resume(error, *, code_sha_before, code_sha_now):
    if code_sha_before != code_sha_now: return "abandon"
    if is_retryable_error(error): return "resume"
    # P0-4：遍历 cause chain（RetryExhaustedError.cause 或 __cause__），识别网络故障
    cause = getattr(error, "cause", None) or getattr(error, "__cause__", None)
    seen = 0
    while cause is not None and seen < 5:
        if is_retryable_error(cause): return "resume"
        cause = getattr(cause, "cause", None) or getattr(cause, "__cause__", None); seen += 1
    return "abandon"


def generate_mcq(rules, book, chapter, max_calls=100, max_retries=2, stats=None, ledger=None, *, budget_ctx=None, chapter_id=0):
    if not rules: return [], []
    verified, unaudited = [], []
    calls_made, skipped = 0, 0
    max_calls_hit = False
    for r in rules:
        rid = r.get("id", "")
        if not rid: continue
        rule_payload = json.dumps({"subject": r.get("subject", ""), "condition": r.get("condition", ""), "rule": r.get("rule", ""), "original_text": r.get("original_text", "")}, ensure_ascii=False, indent=2)
        prompt = PER_RULE_MCQ_PROMPT.replace("__RULE__", rule_payload)
        obj: dict | None = None
        if budget_ctx is not None:
            base = attempt_base_id(run_id=budget_ctx.run_id, batch_id=budget_ctx.batch_id, chapter_id=chapter_id, segment_id=-1, operation="mcq", rule_id=rid)
            try:
                obj = retry_call_with_budget(lambda _p=prompt: _parse_mcq_retryable(_call(_p, timeout=120)), proj=budget_ctx.proj, run=budget_ctx.run, run_id=budget_ctx.run_id, batch_id=budget_ctx.batch_id, chapter_id=chapter_id, segment_id=-1, operation="mcq", rule_id=rid, base_id=base, max_attempts=MAX_MCQ_ATTEMPTS_PER_RULE, project_path=budget_ctx.proj_path, run_path=budget_ctx.run_path)
            except RetryExhaustedError as e:
                raise RetryableModelOutputError(f"mcq attempts exhausted for rule {rid}") from e
        else:
            # P0-2：不预扣——每个真实 attempt 只在紧邻 _call 前原子扣账一次（before_legacy_call）
            if ledger is None and calls_made >= max_calls: max_calls_hit = True; skipped += 1; continue
            last_err = None
            for _attempt_i in range(max_retries + 1):
                if ledger is not None:
                    try: ledger.before_legacy_call()
                    except RuntimeError: max_calls_hit = True; break
                else:
                    if calls_made >= max_calls: max_calls_hit = True; break
                    calls_made += 1
                try:
                    obj = _parse_mcq_retryable(_call(prompt, timeout=120)); last_err = None; break
                except Exception as e:
                    last_err = e
                    if not is_retryable_error(e): break
                    continue
            if last_err is not None:
                skipped += 1
                if ledger is not None: ledger.record_skip()
                continue
        if obj is None:
            skipped += 1
            if ledger is not None: ledger.record_skip()   # 兼容：legacy 路径记录 skip（regen/fill 依赖 ledger.accepted 差值）
            continue
        if not _mcq_prefilter(obj, r):
            skipped += 1
            if ledger is not None: ledger.record_skip()   # 兼容：legacy 路径记录 skip
            continue
        obj["source_rule_id"] = rid; obj.pop("id", None)
        if _mcq_strict_consistency(obj, r):
            obj["_consistency_verified"] = True; verified.append(obj)
            if ledger is not None: ledger.record_accept()   # 兼容：legacy 路径记录 accept
        else:
            obj["_consistency_verified"] = False; obj["_audit_reason"] = "semantic_unaudited"; unaudited.append(obj)
            if ledger is not None: ledger.record_skip()   # 兼容：legacy 路径记录 skip
    if stats is not None:
        stats["calls_made"] = calls_made if ledger is None else ledger.calls_made
        stats["accepted"] = len(verified); stats["unaudited"] = len(unaudited); stats["skipped"] = skipped; stats["max_calls_hit"] = max_calls_hit
    return verified, unaudited

def assign_rule_ids(rules: list[dict], prefix: str, ch_idx: int) -> None:
    for i, r in enumerate(rules):
        r["id"] = f"{prefix}_{ch_idx:03d}_{i:03d}"


def link_mcq_to_rules(mcqs: list[dict], rules: list[dict]) -> tuple[list[dict], list[dict]]:
    """Link MCQs to rules with strict consistency gate (P0-1).

    An MCQ is linked (counted in the clean set) only if ALL:
      1. source_rule_id matches a known rule id (existence check)
      2. _consistency_verified is True (strict gate was applied at generation)
      3. Re-run of _mcq_strict_consistency passes (defense-in-depth)

    MCQs without _consistency_verified are NOT linked:
      - legacy_unaudited: old batch-path MCQs without the flag
      - semantic_unaudited: new MCQs that failed strict check (has _audit_reason)
    """
    rule_map = {r["id"]: r for r in rules if isinstance(r, dict) and r.get("id")}
    linked: list[dict] = []
    unlinked: list[dict] = []
    for m in mcqs:
        src = m.get("source_rule_id", "")
        rule = rule_map.get(src)
        if rule is None:
            m["quarantine_reason"] = f"invalid_or_missing_source_rule_id: {src!r}"
            unlinked.append(m)
            continue
        if not m.get("_consistency_verified"):
            reason = m.get("_audit_reason", "legacy_unaudited: no consistency verification")
            m["quarantine_reason"] = reason
            unlinked.append(m)
            continue
        if not _mcq_strict_consistency(m, rule):
            m["quarantine_reason"] = f"semantic_consistency_failed: rule={src!r}"
            unlinked.append(m)
            continue
        linked.append(m)
    return linked, unlinked


def rotate_answers(mcqs: list[dict]) -> None:
    """Deterministic rotation using SHA-256(frozen_seed + mcq_id) (P0-5).

    The frozen seed means the permutation cannot be reversed from the public
    MCQ id alone, unlike a bare MD5 of the id.
    """
    import hashlib
    for m in mcqs:
        mid = m.get("id", "")
        if not mid:
            continue
        h = hashlib.sha256((ROTATE_SEED + mid).encode()).digest()
        target = "ABCD"[h[0] % 4]
        cur = m.get("answer", "")
        if cur not in "ABCD" or target == cur:
            continue
        opts = m.get("options", {})
        if target in opts and cur in opts:
            opts[cur], opts[target] = opts[target], opts[cur]
            m["answer"] = target


def assign_mcq_ids(mcqs: list[dict], prefix: str, ch_idx: int, start_seq: int) -> int:
    for m in mcqs:
        m["id"] = f"{prefix}_{ch_idx:03d}_mcq_{start_seq:04d}"
        start_seq += 1
    return start_seq


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_provenance(out_dir: Path, cfg: dict) -> None:
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": cfg.get("model", "deepseek-v4-flash"),
        "provider": "deepseek",
        "thinking_mode": "disabled",
        "temperature": 0.0,
        "source_urls": cfg.get("source_urls", {}),
        "file_shas": {},
    }
    for name in ("all_rules.json", "all_mcq.jsonl"):
        f = out_dir / name
        if f.exists():
            manifest["file_shas"][name] = sha256_file(f)
    (out_dir / "provenance.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
