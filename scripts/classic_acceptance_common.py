"""Shared constants and helpers for the classic-texts manual-acceptance
tooling (design v4.6.1, Approved LOCAL_ONLY).

Implements: section 2.3 source-match normalization, section 4.1 deterministic
length-prefixed hash sampling keys, section 4.2 k formula (3% rules / 2% MCQ,
min 5, round_half_up), the frozen section 6.2 thresholds, strict CLI flag
parsing (section 12.4), and production-mode frozen-input locking
(section 12.1, fail-closed). LOCAL_ONLY tooling: no model API, no Phase 8, no
formal gate, no remote publication.

k-table errata (v4.6.1 approved): design v4.6 recorded k_mcq(stratum 8)=8,
contradicting the frozen formula (367*2% = 7.34 -> round_half_up -> 7). The
FORMULA is authoritative: k_mcq(stratum 8)=7, MCQ totals random 188 (cross-book
128+42+13+5) + boundary 194 = 382. Rules stay 609.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BOOKS = ["sanmingtonghui", "qiongtongbaojian", "ditiansui", "zipingzhenquan"]
BOOK_ROOT = "knowledge_base/classic_texts"
BOUNDARY_CHAPTERS = [1, 80, 81, 90, 163, 185, 245, 305, 347, 368, 383]
SANMING_STRATA = [
    (1, 1, 80), (2, 81, 89), (3, 90, 162), (4, 163, 184), (5, 185, 244),
    (6, 245, 304), (7, 305, 346), (8, 347, 367), (9, 368, 383),
]
DRIFT_FILES = [
    f"{BOOK_ROOT}/qiongtongbaojian/all_rules.json",
    f"{BOOK_ROOT}/qiongtongbaojian/quarantine_rules.jsonl",
    f"{BOOK_ROOT}/sanmingtonghui/all_rules.json",
]
SEED = 0xA5C0DE20260820
SEED_BYTES = SEED.to_bytes(8, "big")
SEED_DECIMAL = 46655431411894304
EXPAND_TAG = bytes([0x45, 0x58, 0x50])
K_RULE_PCT = 3
K_MCQ_PCT = 2
K_MIN = 5
STRATUM_CASCADE_PCT = 8
REJECT_PCT = 5
EXPAND_LOW_PCT = 2
MINOR_REJECT_PCT = 15

CRITICAL_CATEGORIES = {"distortion", "answer_wrong", "unsupported",
                       "hallucination", "source_mismatch"}
MINOR_CATEGORIES = {"wording", "condition_omission", "option_noise", "citation_bias"}
VERDICTS = {"PASS", "PASS_WITH_MINOR", "FAIL"}

# Design section 12.1 frozen-input constants (the ONLY accepted values for
# production runs). Source: docs/superpowers/specs/2026-08-20-classic-texts-
# freeze-anchor-record.json (LOCAL_ONLY, implementer-maintained, not an
# approval) plus the two frozen manifests. The acceptance tool must fail
# closed if any of these drift.
FROZEN_CANDIDATE_COMMIT = "80bc630396f31c6b6c122e49ef97f6d912e6f636"
FROZEN_CHAPTER_MANIFEST_SHA = "ba8ab35e7b98e3a0578f7b62f758e2faff1bbe73d480e153c25b6c74b497d1cf"
FROZEN_IDENTITY_MANIFEST_SHA = "0279e30b92f70f8b7cce9c786070fc201cfc3fac86826ef6403b15ad90c5aad2"
FROZEN_FREEZE_TAG = "CLASSIC_ACCEPTANCE_FREEZE_V2"
FROZEN_GENERATOR_PATH = "scripts/generate_acceptance_manifests.py"
ANCHOR_RECORD_PATH = ("docs/superpowers/specs/"
                      "2026-08-20-classic-texts-freeze-anchor-record.json")
EXPECTED_ANCHOR_OVERALL_STATE = "LOCAL_FREEZE_VERIFIED / FORMAL_GATE_BLOCKED"
CHAPTER_MANIFEST_NAME = "2026-08-20-classic-texts-chapter-identity-manifest.json"
IDENTITY_MANIFEST_NAME = "2026-08-20-classic-texts-candidate-identity-manifest.json"


def require(cond, msg):
    if not cond:
        raise RuntimeError(msg)


def length_prefixed(data: bytes) -> bytes:
    return len(data).to_bytes(4, "big") + data


def _lp(value: str) -> bytes:
    return length_prefixed(value.encode("utf-8"))


def sample_score(book, item_type, stratum_index, item_id):
    key = (length_prefixed(SEED_BYTES) + _lp(book) + _lp(item_type)
           + _lp(str(stratum_index)) + _lp(item_id))
    return hashlib.sha256(key).hexdigest()


def expand_score(book, item_type, stratum_index, item_id):
    key = (length_prefixed(SEED_BYTES) + length_prefixed(EXPAND_TAG) + _lp(book)
           + _lp(item_type) + _lp(str(stratum_index)) + _lp(item_id))
    return hashlib.sha256(key).hexdigest()


_WS_RE = re.compile(r"\s+", re.UNICODE)


def normalize_for_source_match(text: str) -> str:
    return _WS_RE.sub("", text)


def round_half_up_int(numerator: int, denominator: int) -> int:
    require(denominator > 0, "round_half_up_int: denominator must be positive")
    return (2 * numerator + denominator) // (2 * denominator)


def compute_k(population: int, pct: int) -> int:
    return max(K_MIN, round_half_up_int(population * pct, 100))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lf_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def sha256_file_lf(path) -> str:
    """LF-normalized SHA, ONLY for manifests whose frozen identity is defined
    in LF bytes (chapter/identity manifests). Review receipts use
    sha256_file_raw instead (F20)."""
    return sha256_bytes(lf_bytes(Path(path).read_bytes()))


def sha256_file_raw(path) -> str:
    """Raw on-disk byte SHA for review receipts (primary/second/arbitration/
    decision report). No LF normalization, so CRLF tampering changes the
    binding SHA (F20, design section 12.5)."""
    return sha256_bytes(Path(path).read_bytes())


def load_json_with_sha(path):
    """F20/P0: read a review artifact's raw on-disk bytes exactly ONCE and
    return (object, raw-byte SHA-256) so the parsed object and its binding
    SHA can never diverge (no TOCTOU re-read window). Callers pin both and
    never re-open the path."""
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-8")), sha256_bytes(raw)


def serialize_json(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")



def publish_new_file(path, data):
    """Design section 8 publication primitive: atomically create `path` with
    `data`, failing closed if `path` already exists -- a frozen artifact is
    never overwritten in place, even by concurrent publishers.

    The bytes are fully written to a SAME-DIRECTORY temporary file, fsynced,
    and read back for verification first, so the final path is only ever made
    visible via an atomic create-if-absent link (os.link raises FileExistsError
    when the target already exists on BOTH POSIX and Windows; empirically
    verified on win32). This avoids the two failure modes of `open(path, 'xb')`:
    a mid-write crash cannot leave a half-written file at the frozen path that
    would permanently block retries, and two concurrent publishers cannot both
    observe absence and both write. Each publisher cleans up its own temp file;
    a pre-existing final path is never touched (its bytes remain the first
    complete publication)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                    dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if tmp.read_bytes() != data:
            raise RuntimeError(f"publish: temporary file verification failed for {path}")
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise RuntimeError(
                f"publish: {path} already exists; a frozen artifact must not be "
                f"overwritten in place (design section 8). Publish a correction "
                f"as a new version (new output directory / versioned filename).")
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass

def load_json(source, rel: str):
    return json.loads(lf_bytes(source.read_bytes(rel)).decode("utf-8"))


def load_jsonl(source, rel: str):
    lines = lf_bytes(source.read_bytes(rel)).decode("utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def parse_flags(argv, allowed, repeatable=()):
    """Strict CLI parser (design section 12.4): unknown flags, missing values,
    and unexpected positional arguments are all rejected. Returns
    ({name: [values...]}, [positional...])."""
    allowed = set(allowed) | set(repeatable)
    flags = {}
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--"):
            name = arg[2:]
            require(name in allowed, f"unknown flag: --{name}")
            require(i + 1 < len(argv) and not argv[i + 1].startswith("--"),
                    f"--{name} requires a value")
            flags.setdefault(name, []).append(argv[i + 1])
            i += 2
        else:
            positional.append(arg)
            i += 1
    require(not positional, f"unexpected positional arguments: {positional}")
    return flags, positional


def flag1(flags, name):
    values = flags.get(name) or []
    require(len(values) == 1, f"--{name} must be given exactly once (got {len(values)})")
    require(bool(values[0]), f"--{name} requires a value")
    return values[0]


def flag_opt(flags, name):
    values = flags.get(name) or []
    require(len(values) <= 1, f"--{name} may be given at most once")
    return values[0] if values and values[0] else None


def flagn(flags, name):
    return [v for v in (flags.get(name) or []) if v]


class DirSource:
    kind = "dir"

    def __init__(self, root):
        self.root = Path(root)

    def read_bytes(self, rel: str) -> bytes:
        path = self.root / rel
        if not path.is_file():
            raise RuntimeError(f"data source missing path: {rel}")
        return path.read_bytes()

    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()


class GitSource:
    kind = "git"

    def __init__(self, repo_root, commit: str):
        self.repo = Path(repo_root)
        require(re.fullmatch(r"[0-9a-f]{40}", commit),
                "GitSource commit must be a full 40-hex sha")
        self.commit = commit

    def _git(self, args, check=True):
        result = subprocess.run(["git", "-C", str(self.repo)] + args, capture_output=True)
        if check and result.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed: "
                f"{result.stderr.decode('utf-8', 'replace')[:300]}")
        return result

    def read_bytes(self, rel: str) -> bytes:
        return self._git(["show", f"{self.commit}:{rel}"]).stdout

    def exists(self, rel: str) -> bool:
        result = self._git(["cat-file", "-t", f"{self.commit}:{rel}"], check=False)
        return result.returncode == 0 and result.stdout.decode("utf-8").strip() == "blob"


def _read_anchor_record(repo_root):
    path = Path(repo_root) / ANCHOR_RECORD_PATH
    require(path.is_file(), f"anchor record not found: {ANCHOR_RECORD_PATH}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_frozen_inputs(candidate_commit, chapter_manifest_path):
    """Production-mode fail-closed frozen-input verification (design section
    12.1, F13/F14/F18). Runs BEFORE any candidate data or chapter-manifest
    read. Verifies the exact candidate commit, that the CLI-provided chapter
    manifest equals the frozen one (LF SHA), both frozen manifest SHAs from
    their fixed repo paths, the anchor-record honesty fields (including the
    absence/pinning of independent_approval), and the full three-object
    freeze chain via generate_acceptance_manifests.py --check. Returns the
    anchor record on success; raises RuntimeError otherwise."""
    require(isinstance(candidate_commit, str)
            and candidate_commit == FROZEN_CANDIDATE_COMMIT,
            f"production mode requires candidate_commit {FROZEN_CANDIDATE_COMMIT} "
            f"(got {candidate_commit!r})")

    repo_root = Path(__file__).resolve().parents[1]
    # F18: the CLI --chapter-manifest must itself be the frozen chapter manifest
    cli_ch_sha = sha256_file_lf(chapter_manifest_path)
    require(cli_ch_sha == FROZEN_CHAPTER_MANIFEST_SHA,
            f"--chapter-manifest LF SHA {cli_ch_sha[:16]} != frozen "
            f"{FROZEN_CHAPTER_MANIFEST_SHA[:16]}; production mode only accepts "
            f"the frozen chapter manifest")
    chapter_manifest_path = repo_root / "docs" / "superpowers" / "specs" / CHAPTER_MANIFEST_NAME
    identity_manifest_path = repo_root / "docs" / "superpowers" / "specs" / IDENTITY_MANIFEST_NAME
    ch_sha = sha256_file_lf(chapter_manifest_path)
    require(ch_sha == FROZEN_CHAPTER_MANIFEST_SHA,
            f"chapter manifest SHA {ch_sha[:16]} != frozen {FROZEN_CHAPTER_MANIFEST_SHA[:16]}")
    id_sha = sha256_file_lf(identity_manifest_path)
    require(id_sha == FROZEN_IDENTITY_MANIFEST_SHA,
            f"identity manifest SHA {id_sha[:16]} != frozen {FROZEN_IDENTITY_MANIFEST_SHA[:16]}")

    anchor = _read_anchor_record(repo_root)
    require(anchor.get("record_type") == "freeze-anchor-record",
            "anchor record record_type != freeze-anchor-record")
    require(anchor.get("status") == "LOCAL_ONLY",
            "anchor record status != LOCAL_ONLY")
    require(anchor.get("overall_state") == EXPECTED_ANCHOR_OVERALL_STATE,
            f"anchor record overall_state != {EXPECTED_ANCHOR_OVERALL_STATE!r}")
    require("independent_approval" not in anchor,
            "anchor record must NOT have a top-level independent_approval key "
            "(only an explicit re-freeze approval may add one)")
    provenance = anchor.get("provenance")
    require(isinstance(provenance, dict), "anchor record provenance missing/not an object")
    require(provenance.get("independent_approval") == "none",
            'anchor record provenance.independent_approval must == "none" '
            '(a non-"none" value is a false approval claim and fails closed)')
    require(anchor.get("candidate_commit") == FROZEN_CANDIDATE_COMMIT,
            "anchor record candidate_commit mismatch")
    require(anchor["manifests"].get(CHAPTER_MANIFEST_NAME) == FROZEN_CHAPTER_MANIFEST_SHA,
            "anchor record chapter manifest SHA mismatch")
    require(anchor["manifests"].get(IDENTITY_MANIFEST_NAME) == FROZEN_IDENTITY_MANIFEST_SHA,
            "anchor record identity manifest SHA mismatch")

    identity = json.loads(Path(identity_manifest_path).read_text(encoding="utf-8"))
    for f in identity["groups"]["output_files"]:
        require(f["candidate_commit"] == FROZEN_CANDIDATE_COMMIT,
                f"output file {f['path']} candidate_commit mismatch")
        require(re.fullmatch(r"[0-9a-f]{64}", f["sha256_lf"]),
                f"output file {f['path']} sha256_lf invalid")

    expected_oid = anchor.get("expected_tag_oid")
    require(re.fullmatch(r"[0-9a-f]{40}", expected_oid or ""),
            "anchor record expected_tag_oid missing/invalid")
    result = subprocess.run(
        [sys.executable, str(repo_root / FROZEN_GENERATOR_PATH), "--check",
         "--freeze-ref", FROZEN_FREEZE_TAG, "--expected-freeze-tag-oid", expected_oid],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    require(result.returncode == 0,
            f"frozen chain --check failed (exit {result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}")
    return anchor


_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def _check_iso8601(value, what):
    """Require an ISO-8601 timestamp with a real date/time AND a non-empty
    timezone offset. Shape-only regex is not enough: 2026-99-99T99:99:99+99:99
    matches the regex but is not a valid instant. Use datetime.fromisoformat
    for semantic parsing; normalize trailing Z to +00:00 first."""
    require(isinstance(value, str) and _ISO8601_RE.match(value),
            f"{what} must be an ISO-8601 timestamp with timezone (got {value!r})")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        require(False, f"{what} is not a valid ISO-8601 timestamp: {value!r}")
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            f"{what} must include a timezone offset: {value!r}")


def build_source(flags, expected_test_only=None):
    """Exactly one of --candidate-commit <40-hex> (production, locked) or
    --data-root <dir> (fake/test only). F18: production runs the full frozen
    lock, including validating the CLI-provided --chapter-manifest, BEFORE any
    data is read. Returns (source, source_desc). When expected_test_only is
    given, callers can additionally assert the resolved mode matches (used by
    the strict CLI entry points)."""
    commit = flag_opt(flags, "candidate-commit")
    data_root = flag_opt(flags, "data-root")
    require(bool(commit) != bool(data_root),
            "exactly one of --candidate-commit <40-hex> or --data-root <dir> is required")
    if commit:
        ch_path = Path(flag1(flags, "chapter-manifest"))
        verify_frozen_inputs(commit, ch_path)
        require(re.fullmatch(r"[0-9a-f]{40}", commit),
                "--candidate-commit must be a full 40-hex sha")
        require(commit == FROZEN_CANDIDATE_COMMIT,
                f"production mode requires candidate_commit {FROZEN_CANDIDATE_COMMIT}")
        if expected_test_only is not None:
            require(expected_test_only is False, "candidate-commit is production, not fake")
        repo_root = Path(__file__).resolve().parents[1]
        return (GitSource(repo_root, commit),
                {"kind": "git", "candidate_commit": commit, "test_only": False})
    if expected_test_only is not None:
        require(expected_test_only is True, "data-root is fake, not production")
    return DirSource(data_root), {"kind": "dir", "root": str(Path(data_root).resolve()),
                                 "test_only": True}