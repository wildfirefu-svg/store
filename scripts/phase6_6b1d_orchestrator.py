#!/usr/bin/env python3
"""Phase 6 6B1-D orchestrator - 紫微斗数与子平八字的干扰机制探索.

协议摘要（与 6b1d plan 一致）：
  - 纯探索性研究，非正式 6B2
  - 双年度: 2024 holdout + 2025 holdout, 各 40 题
  - 5 arms × 5 groups × 2 years × 3 repeats = 150 slices
  - 每 slice 8 题, local cap 10, 全局 hard cap 1320 (1200 + 120 reserve)
  - 5×5 Latin square 全程交错
  - 动态 effective_cap, BudgetLedger.allocated_cap_by_slice 权威
  - 五 smoke 状态机 (fresh/resume/completed/blocked_corrupt)
  - 全描述性分析，不作显著性宣称

用法:
  python scripts/phase6_6b1d_orchestrator.py --provider deepseek --model deepseek-chat \
    --output-dir benchmark/outputs/phase6_6b1d --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:  # pragma: no cover
    _HAS_NUMPY = False

try:
    import tiktoken
    _HAS_TIKTOKEN = True
except ImportError:  # pragma: no cover
    _HAS_TIKTOKEN = False

# Ensure project root on sys.path for benchmark.* imports
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ---- P0: output-dir exclusive lock (concurrent orchestrator guard) ----

def _probe_pid(pid: int) -> str:
    """跨平台探测 PID 状态，返回 "alive" / "dead" / "unknown"。

    探测不确定时返回 "unknown"，调用方必须 fail-closed（按存活处理），不得按死亡接管。

    Windows: os.kill(pid, 0) 对活进程会 segfault（已知问题），改用
    ctypes.windll.kernel32.OpenProcess 探测（死 PID 返回 NULL handle）。
    Unix: os.kill(pid, 0) 稳定，进程不存在 -> ProcessLookupError，
    存在但无权限 -> PermissionError，存在且有权限 -> 无异常。
    """
    if pid <= 0:
        return "dead"
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return "alive"
            # OpenProcess 返回 NULL：可能是 PID 不存在，也可能是权限不足。
            # 区分：GetLastError() == 5 (ACCESS_DENIED) 说明进程存在但无权限。
            err = kernel32.GetLastError()
            if err == 5:  # ERROR_ACCESS_DENIED
                return "alive"
            return "dead"
        except Exception:
            return "unknown"   # ctypes 异常 -> 探测失败，fail-closed
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        return "alive"
    except OSError:
        return "unknown"      # 其它 OSError -> 探测失败，fail-closed
    return "alive"


class OutputDirLock:
    """以 output-dir 为粒度的原子独占锁。

    防止两个 orchestrator 进程并发写同一目录（r2 事故根因：并发导致每 case 双调用、
    detail 重复、verify 竞态、ledger 超 hard_cap 仍标记 completed）。

    锁文件格式：``<pid>\\n<owner_token>``。owner_token 为 uuid4 不可复用随机串，
    release 时必须验证 token 匹配才删除锁文件，防止旧锁对象/atexit 回调误删新持有者的锁。

    acquire 流程：
    1. os.open(O_CREAT | O_EXCL) 原子创建。成功 -> 写 pid+token，返回锁对象。
    2. FileExistsError -> 读持有者 PID。_probe_pid 返回 "alive"/"unknown" -> fail-closed (None)。
       返回 "dead" -> 接管：删除旧锁后重新原子创建（新 token）。
    3. 任何删除/创建竞态 -> fail-closed (None)。

    release 流程：
    1. 读锁文件，解析 token。
    2. token 匹配当前锁对象 -> 删除锁文件。
    3. token 不匹配（锁已被接管）-> 不删除（保护新持有者）。
    4. 锁文件不存在/读失败 -> 无操作（幂等）。
    """

    LOCK_FILENAME = ".orchestrator.lock"

    def __init__(self, lock_path: str, owner_token: str):
        self._lock_path = lock_path
        self._owner_token = owner_token
        self._released = False

    @property
    def lock_path(self) -> str:
        return self._lock_path

    @property
    def owner_token(self) -> str:
        return self._owner_token

    @staticmethod
    def _read_lock_file(lock_path: str) -> tuple[int, str] | None:
        """读锁文件，返回 (pid, token)；损坏/不存在返回 None。"""
        try:
            with open(lock_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except OSError:
            return None
        parts = content.split("\n", 1)
        if len(parts) != 2:
            return None
        try:
            pid = int(parts[0].strip() or "0")
        except ValueError:
            return None
        token = parts[1].strip()
        if not token:
            return None
        return pid, token

    @classmethod
    def acquire(cls, output_dir: str) -> "OutputDirLock | None":
        """尝试获取 output-dir 独占锁。成功返回锁对象，失败（被持有）返回 None。"""
        os.makedirs(output_dir, exist_ok=True)
        lock_path = os.path.join(output_dir, cls.LOCK_FILENAME)
        pid = os.getpid()
        import uuid
        token = uuid.uuid4().hex
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # 锁已存在：判断持有者是否存活
            parsed = cls._read_lock_file(lock_path)
            if parsed is None:
                # 锁文件损坏/读失败 -> fail-closed，不接管
                return None
            holder_pid, _holder_token = parsed
            state = _probe_pid(holder_pid)
            if state != "dead":
                # alive 或 unknown -> fail-closed
                return None
            # stale lock：持有者已死，接管
            try:
                os.remove(lock_path)
            except OSError:
                return None  # 删除失败（权限/竞态）-> fail-closed
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return None  # 删除后被其他进程抢走
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{pid}\n{token}")
        lock = cls(lock_path, token)
        import atexit
        atexit.register(lock.release)
        return lock

    def release(self) -> None:
        """释放锁：验证 owner_token 匹配后删除锁文件。

        若锁已被接管（token 不匹配），不删除以保护新持有者。幂等。
        """
        if self._released:
            return
        self._released = True
        parsed = self._read_lock_file(self._lock_path)
        if parsed is None:
            return  # 锁文件不存在/损坏，无操作
        _pid, token = parsed
        if token != self._owner_token:
            return  # 锁已被接管，不删除新持有者的锁
        try:
            os.remove(self._lock_path)
        except OSError:
            pass


# ---- constants ----

REASONED_PROFILE = "baziqa_xjz_reasoned"
CHART_SCHEMA = "legacy_v0"

YEAR_DATASETS = {
    "2024": "benchmark/datasets/baziqa_contest8_2024_holdout_enriched.jsonl",
    "2025": "benchmark/datasets/baziqa_contest8_2025_holdout_enriched.jsonl",
}

# arm -> ziwei_arm (6B1-D 5 arms)
ARM_ZIWEI_MAP = {
    "b1a_prime": "none",
    "b1b": "only",
    "b1c": "combined",
    "b2b": "ziwei_mini",
    "b2c": "sequential",
}

ARMS = list(ARM_ZIWEI_MAP.keys())
YEARS = ["2024", "2025"]
REPEATS = [0, 1, 2]
QUESTIONS_PER_CELL = 40

# 每 cell 拆 5 组, 每组 8 题
SLICE_LAYOUT = [8, 8, 8, 8, 8]
GROUPS_PER_CELL = 5
SLICE_SIZE = 8

# 5×5 Latin square: position -> group -> arm
LATIN_SQUARE = {
    0: {0: "b1a_prime", 1: "b1b",      2: "b1c",   3: "b2b",   4: "b2c"},
    1: {0: "b1c",       1: "b2b",      2: "b2c",   3: "b1a_prime", 4: "b1b"},
    2: {0: "b2b",       1: "b2c",      2: "b1a_prime", 3: "b1b",  4: "b1c"},
    3: {0: "b2c",       1: "b1a_prime", 2: "b1b",   3: "b1c",   4: "b2b"},
    4: {0: "b1b",       1: "b1c",      2: "b2b",   3: "b2c",   4: "b1a_prime"},
}

# Frozen experiment date
FROZEN_DATE = "2026-07-22"

# Env vars to strip from subprocess
ENV_CLEANUP = ["BAZI_RAG", "BAZI_RAG_CORPUS", "BAZI_FEWSHOT_FILE", "BAZI_APB_BLOCK"]

# Budget constants
SLICE_BASE_CALLS = 8
SLICE_RESERVE = 2
SLICE_MAX_CAP = SLICE_BASE_CALLS + SLICE_RESERVE  # 10
GLOBAL_LEDGER_CAP = 1320   # 1200 scheduled + 120 reserve
TOTAL_SCHEDULED_CALLS = 1200
TOTAL_SLICES = 150         # 5 × 5 × 2 × 3

# Smoke constants
SMOKE_ARMS_ORDER = ["b1a_prime", "b1b", "b1c", "b2b", "b2c"]
SMOKE_PARSER_RATE_THRESHOLD = 1.0   # 100% (8/8)

# Bootstrap CI constants (plan §4.12: seed=42, 10k draws, year×question 聚类)
BOOTSTRAP_SEED = 42
BOOTSTRAP_DRAWS = 10000
BOOTSTRAP_CLUSTERS = "year_x_question"

# Descriptive report forbidden words (plan §4.12: 不含"显著"、"确认"等词)
FORBIDDEN_WORDS = ("显著", "确认", "significance", "significant", "confirm")

# Terminal states (复用 6B1)
TERMINAL_STATES = {"parsed", "invalid", "unresolved", "call_failed"}

# Bootstrap fingerprint scope
FINGERPRINT_SCOPE = [
    "scripts/phase6_6b1d_orchestrator.py",
    "benchmark/runners/run_benchmark.py",
    "benchmark/formatters/chart_context.py",
    "benchmark/formatters/baziqa_prompt.py",
    "benchmark/runners/profiles.py",
]

ARCHIVE_ROOT = "docs/phase6/6b1d"
EXPERIMENT_ID_PREFIX = "6b1d"

# Labels constants (plan §4.14, §5.2)
LABEL_DIMENSIONS = ("question_complexity", "ziwei_info_richness", "bazi_info_richness")
LABEL_VALUES = (1, 2, 3)
LABELS_DEFAULT_PATH = os.path.join(ARCHIVE_ROOT, "labels.jsonl")
LABEL_MIN_LAYER_SIZE = 5


def atomic_write_json(path: str, data: dict) -> None:
    """Atomically write JSON to disk (write temp + rename)."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Windows: os.replace may fail with PermissionError if another
        # process (e.g. antivirus) briefly holds the file; retry a few times
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_jsonl(path: str) -> list:
    """Load JSONL file, return list of records."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


# ---- experiment-level code fingerprint (P0 #1) ----

def _compute_experiment_code_fingerprint(root: str | None = None,
                                         scope: tuple | list | None = None) -> str:
    """Hash all experiment-scope source files in FINGERPRINT_SCOPE.

    Includes orchestrator, runner, formatters, prompt builder, profiles.
    Any change to these files produces a different fingerprint, causing
    resume to be rejected via run manifest verification.

    root:  repo root containing the scope files (default: parent of this script's dir).
    scope: iterable of repo-relative paths to hash (default: FINGERPRINT_SCOPE).
           Tests pass a tmp root + copied scope to avoid rewriting production source.

    Returns the FULL 64-hex-char SHA-256 (plan §4.14: 实验级指纹保存完整 SHA-256).
    """
    if root is None:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if scope is None:
        scope = FINGERPRINT_SCOPE
    h = hashlib.sha256()
    for rel in scope:
        h.update(rel.encode())
        path = os.path.join(root, rel)
        if os.path.exists(path):
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        else:
            h.update(b"<missing>")
        h.update(b"\x00")
    return h.hexdigest()


def _sha256_file(path: str) -> str:
    """SHA-256 of a file, returned as hex string."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_run_manifest(provider: str, model: str,
                       labels_sha256: str | None = None) -> dict:
    """Build experiment-level run manifest for resume verification.

    Contains the experiment code fingerprint (FINGERPRINT_SCOPE) which
    includes the orchestrator itself. On resume, if any scope file has
    changed, the fingerprint will not match and resume is rejected.
    """
    return {
        "experiment_id": EXPERIMENT_ID_PREFIX,
        "frozen_date": FROZEN_DATE,
        "provider": provider,
        "model": model,
        "experiment_code_fingerprint": _compute_experiment_code_fingerprint(),
        "fingerprint_scope": list(FINGERPRINT_SCOPE),
        "labels_sha256": labels_sha256,
        "created_at": time.strftime('%Y-%m-%dT%H:%M:%S'),
    }


def verify_run_manifest(output_dir: Path, provider: str, model: str,
                        labels_sha256: str | None = None) -> tuple:
    """Verify run manifest on resume. Returns (ok, reason).

    Checks:
    1. run_manifest.json exists (resume scenario)
    2. experiment_code_fingerprint matches current code
    3. provider and model match
    4. labels_sha256 matches (if labels are provided)
    """
    manifest_path = output_dir / "run_manifest.json"
    if not manifest_path.exists():
        return True, "no existing run manifest (fresh start)"

    try:
        with open(str(manifest_path), "r", encoding="utf-8") as f:
            stored = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"run manifest corrupt: {e}"

    current_fp = _compute_experiment_code_fingerprint()
    stored_fp = stored.get("experiment_code_fingerprint")
    if stored_fp != current_fp:
        return False, (f"experiment code fingerprint drift: "
                       f"stored={stored_fp} current={current_fp}")

    if stored.get("provider") != provider:
        return False, (f"provider mismatch: stored={stored.get('provider')} "
                       f"current={provider}")

    if stored.get("model") != model:
        return False, (f"model mismatch: stored={stored.get('model')} "
                       f"current={model}")

    if labels_sha256 is not None:
        stored_labels = stored.get("labels_sha256")
        if stored_labels != labels_sha256:
            return False, (f"labels SHA-256 mismatch: "
                           f"stored={stored_labels} current={labels_sha256}")

    return True, "ok"


def write_run_manifest(output_dir: Path, provider: str, model: str,
                       labels_sha256: str | None = None) -> str:
    """Write run manifest to output_dir/run_manifest.json."""
    manifest = build_run_manifest(provider, model, labels_sha256)
    path = str(output_dir / "run_manifest.json")
    atomic_write_json(path, manifest)
    return path


# ---- labels preflight (P0 #3a/b/c) ----

def _collect_all_case_ids() -> set:
    """Collect all 80 unique case IDs from both year datasets."""
    case_ids = set()
    for year, path in YEAR_DATASETS.items():
        if os.path.exists(path):
            for row in load_jsonl(path):
                cid = row.get("case_id")
                if cid:
                    case_ids.add(cid)
    return case_ids


def _validate_label_block(row: dict, block_field: str, cid) -> bool:
    """Validate a 3-dimension label block (annotator_1/annotator_2/final).

    Returns True if valid; prints nothing. Caller formats the error reason.
    """
    block = row.get(block_field)
    if not isinstance(block, dict):
        return False
    for dim in LABEL_DIMENSIONS:
        if block.get(dim) not in LABEL_VALUES:
            return False
    return True


def validate_labels(labels_path: str) -> tuple:
    """Preflight validation of labels.jsonl (plan §4.14, §5.2).

    Checks:
    1. File exists and is parseable
    2. 80 case IDs (complete coverage of both year datasets)
    3. No duplicate case IDs (uniqueness)
    4. No extra/missing case IDs
    5. Full dual-annotator schema per row (fail-closed):
       - annotator_1_id / annotator_2_id present, non-empty, and distinct
       - annotator_1 / annotator_2 dicts with all 3 dimensions in {1, 2, 3}
       - adjudicator present, non-empty, and distinct from both annotator IDs
         (a genuine third person, plan §5.2: 分歧由第 3 人裁决)
       - final dict with all 3 dimensions in {1, 2, 3}
       - when the two annotators agree on a dimension, final MUST equal their
         common label (only disagreements may be adjudicated)

    Returns (ok, labels_sha256, labels_data, reason).
    """
    if not os.path.exists(labels_path):
        return False, None, None, f"labels file not found: {labels_path}"

    try:
        labels_data = load_jsonl(labels_path)
    except (json.JSONDecodeError, OSError) as e:
        return False, None, None, f"labels file corrupt: {e}"

    if not labels_data:
        return False, None, None, "labels file is empty"

    # Collect case IDs from labels
    label_case_ids = []
    for row in labels_data:
        cid = row.get("case_id")
        if cid is None:
            return False, None, None, "row missing case_id"
        label_case_ids.append(cid)

    # Uniqueness check
    if len(label_case_ids) != len(set(label_case_ids)):
        dupes = [cid for cid in label_case_ids if label_case_ids.count(cid) > 1]
        return False, None, None, f"duplicate case IDs: {set(dupes)}"

    # Coverage check: all expected case IDs present, no extras
    expected_ids = _collect_all_case_ids()
    label_id_set = set(label_case_ids)
    missing = expected_ids - label_id_set
    extra = label_id_set - expected_ids
    if missing:
        return False, None, None, f"missing {len(missing)} case IDs (e.g. {sorted(missing)[:3]})"
    if extra:
        return False, None, None, f"extra {len(extra)} case IDs (e.g. {sorted(extra)[:3]})"

    # Full dual-annotator schema validation (fail-closed, plan §4.14)
    for row in labels_data:
        cid = row.get("case_id")

        a1_id = row.get("annotator_1_id")
        a2_id = row.get("annotator_2_id")
        if not a1_id or not isinstance(a1_id, str):
            return False, None, None, f"case {cid}: annotator_1_id missing/empty"
        if not a2_id or not isinstance(a2_id, str):
            return False, None, None, f"case {cid}: annotator_2_id missing/empty"
        if a1_id == a2_id:
            return False, None, None, (f"case {cid}: annotator_1_id == annotator_2_id "
                                       f"({a1_id}), must be two independent annotators")

        if not _validate_label_block(row, "annotator_1", cid):
            return False, None, None, (f"case {cid}: annotator_1 missing a dimension or "
                                       f"value not in {LABEL_VALUES}")
        if not _validate_label_block(row, "annotator_2", cid):
            return False, None, None, (f"case {cid}: annotator_2 missing a dimension or "
                                       f"value not in {LABEL_VALUES}")

        adjudicator = row.get("adjudicator")
        if not adjudicator or not isinstance(adjudicator, str):
            return False, None, None, f"case {cid}: adjudicator missing/empty"
        if adjudicator == a1_id or adjudicator == a2_id:
            return False, None, None, (f"case {cid}: adjudicator ({adjudicator}) must be a "
                                       f"third person distinct from both annotators "
                                       f"({a1_id}, {a2_id})")

        if not _validate_label_block(row, "final", cid):
            return False, None, None, (f"case {cid}: final missing a dimension or "
                                       f"value not in {LABEL_VALUES}")

        # Adjudication protocol (plan §5.2: 分歧由第 3 人裁决):
        # when the two annotators agree on a dimension, the adjudicated final
        # MUST equal their common label. Only disagreements may be adjudicated.
        a1_block = row.get("annotator_1") or {}
        a2_block = row.get("annotator_2") or {}
        final_block = row.get("final") or {}
        for dim in LABEL_DIMENSIONS:
            a1v = a1_block.get(dim)
            a2v = a2_block.get(dim)
            if a1v == a2v and a1v in LABEL_VALUES:
                if final_block.get(dim) != a1v:
                    return False, None, None, (f"case {cid}: annotators agree on "
                                               f"{dim}={a1v} but final="
                                               f"{final_block.get(dim)} (must match)")

    # Compute SHA-256
    labels_sha256 = _sha256_file(labels_path)
    return True, labels_sha256, labels_data, "ok"


def compute_label_distribution(labels_data: list) -> dict:
    """Compute 3-dimensional label distribution (plan §5.2, §5.3).

    Returns {dimension: {value: count}} for each of the 3 dimensions.
    Also returns layers_to_skip: dimensions+values with < LABEL_MIN_LAYER_SIZE.
    """
    dist = {dim: {1: 0, 2: 0, 3: 0} for dim in LABEL_DIMENSIONS}
    for row in labels_data:
        final = row.get("final", {})
        for dim in LABEL_DIMENSIONS:
            val = final.get(dim)
            if val in LABEL_VALUES:
                dist[dim][val] += 1

    return dist


def get_skipped_layers(labels_data: list) -> list:
    """Return list of (dimension, value) pairs with < LABEL_MIN_LAYER_SIZE samples.

    These layers will be skipped in stratified analysis (plan §5.3, 附录 A).
    """
    dist = compute_label_distribution(labels_data)
    skipped = []
    for dim in LABEL_DIMENSIONS:
        for val in LABEL_VALUES:
            if dist[dim][val] < LABEL_MIN_LAYER_SIZE:
                skipped.append((dim, val))
    return skipped


# ---- BudgetLedger (6B1-D, with allocated_cap_by_slice schema) ----

class BudgetLedger:
    """Global budget ledger with fail-closed corruption checks.

    6B1-D 扩展: 新增 allocated_cap_by_slice 字段作为 effective_cap 权威来源.
    """

    def __init__(self, ledger_path: str):
        self.path = ledger_path
        self._data = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {
                "global_hard_cap": GLOBAL_LEDGER_CAP,
                "slices_completed": [],
                "calls_attempted_by_slice": {},
                "total_calls_attempted": 0,
                "allocated_cap_by_slice": {},
            }
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = f.read()
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            print(json.dumps({
                "status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path, "error": str(e),
                "reason": "账本 JSON 损坏，无法继续 - fail-closed",
            }, ensure_ascii=False))
            raise SystemExit(2)

        # Validate required fields
        for field in ("global_hard_cap", "slices_completed",
                      "calls_attempted_by_slice", "total_calls_attempted"):
            if field not in data:
                print(json.dumps({
                    "status": "BUDGET_LEDGER_CORRUPTED",
                    "path": self.path, "error": f"缺少字段 {field}",
                    "reason": "账本结构不完整 - fail-closed",
                }, ensure_ascii=False))
                raise SystemExit(2)

        # allocated_cap_by_slice: 可选字段（旧 ledger 可能没有），默认空 dict
        if "allocated_cap_by_slice" not in data:
            data["allocated_cap_by_slice"] = {}

        # Validate global_hard_cap
        if data["global_hard_cap"] != GLOBAL_LEDGER_CAP:
            print(json.dumps({
                "status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"global_hard_cap={data['global_hard_cap']} != {GLOBAL_LEDGER_CAP}",
                "reason": "账本硬上限被篡改 - fail-closed",
            }, ensure_ascii=False))
            raise SystemExit(2)

        # Validate calls_attempted_by_slice
        per_slice = data["calls_attempted_by_slice"]
        if not isinstance(per_slice, dict):
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path, "error": "calls_attempted_by_slice 非 dict",
                "reason": "账本结构损坏 - fail-closed"}, ensure_ascii=False))
            raise SystemExit(2)
        for sid, cnt in per_slice.items():
            if not isinstance(cnt, int) or cnt < 0:
                print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                    "path": self.path,
                    "error": f"slice {sid} 调用数 {cnt!r} 非非负整数",
                    "reason": "账本计数非法 - fail-closed"}, ensure_ascii=False))
                raise SystemExit(2)

        # Validate total == sum(per_slice)
        recomputed_total = sum(per_slice.values())
        if data["total_calls_attempted"] != recomputed_total:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"total={data['total_calls_attempted']} != sum(per_slice)={recomputed_total}",
                "reason": "账本 total 与明细不一致 - fail-closed"}, ensure_ascii=False))
            raise SystemExit(2)
        if data["total_calls_attempted"] > data["global_hard_cap"]:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"total={data['total_calls_attempted']} > hard_cap={data['global_hard_cap']}",
                "reason": "账本总额超限 - fail-closed"}, ensure_ascii=False))
            raise SystemExit(2)

        # Validate allocated_cap_by_slice structure (6B1-D)
        allocated = data["allocated_cap_by_slice"]
        if not isinstance(allocated, dict):
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path, "error": "allocated_cap_by_slice 非 dict",
                "reason": "账本结构损坏 - fail-closed"}, ensure_ascii=False))
            raise SystemExit(2)
        for sid, cap in allocated.items():
            if not isinstance(cap, int) or cap < SLICE_BASE_CALLS or cap > SLICE_MAX_CAP:
                print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                    "path": self.path,
                    "error": f"slice {sid} allocated_cap {cap!r} 不在 [{SLICE_BASE_CALLS}, {SLICE_MAX_CAP}]",
                    "reason": "allocated_cap 非法 - fail-closed"}, ensure_ascii=False))
                raise SystemExit(2)

        return data

    def _save(self) -> None:
        atomic_write_json(self.path, self._data)

    @property
    def total_attempted(self) -> int:
        return self._data["total_calls_attempted"]

    @property
    def hard_cap(self) -> int:
        return self._data["global_hard_cap"]

    def sliced_completed(self, slice_id: str) -> bool:
        return slice_id in self._data["slices_completed"]

    def record_slice_completed(self, slice_id: str, calls: int) -> None:
        """Atomically record slice completion with idempotent max."""
        prev = self._data["calls_attempted_by_slice"].get(slice_id, 0)
        recorded = max(prev, calls)
        self._data["calls_attempted_by_slice"][slice_id] = recorded

        if slice_id not in self._data["slices_completed"]:
            self._data["slices_completed"].append(slice_id)

        self._data["total_calls_attempted"] = sum(
            self._data["calls_attempted_by_slice"].values()
        )
        self._save()

    def budget_ok(self, remaining_scheduled: int) -> bool:
        return self.total_attempted + remaining_scheduled <= self.hard_cap

    def budget_ok_for_slice(self, slice_id: str, slice_hard_cap: int) -> bool:
        """Frozen formula:
        total_attempted + (slice_hard_cap - already_attempted_for_slice) <= 1320
        """
        already = self._data["calls_attempted_by_slice"].get(slice_id, 0)
        remaining_for_slice = max(0, slice_hard_cap - already)
        return self.total_attempted + remaining_for_slice <= self.hard_cap

    def record_calls_only(self, slice_id: str, calls: int) -> None:
        """Record calls consumed WITHOUT marking slice as completed."""
        prev = self._data["calls_attempted_by_slice"].get(slice_id, 0)
        recorded = max(prev, calls)
        self._data["calls_attempted_by_slice"][slice_id] = recorded
        self._data["total_calls_attempted"] = sum(
            self._data["calls_attempted_by_slice"].values()
        )
        self._save()

    def remaining_budget(self) -> int:
        return self.hard_cap - self.total_attempted

    def validate_against_schedule(self, schedule: dict,
                                  provider: str, model: str) -> None:
        """Validate ALL ledger slice IDs belong to schedule. Fail-closed.

        6B1-D 扩展: 同时校验 allocated_cap_by_slice 的 key 和与 manifest hard_cap 的一致性.
        """
        schedule_ids = {sl["slice_id"] for sl in schedule["slices"]}
        schedule_by_id = {sl["slice_id"]: sl for sl in schedule["slices"]}

        # 1. calls_attempted_by_slice 的 key 必须属于 schedule
        calls_keys = set(self._data["calls_attempted_by_slice"].keys())
        unknown_call_keys = calls_keys - schedule_ids
        if unknown_call_keys:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"calls_attempted_by_slice 含未知 slice ID: "
                         f"{sorted(unknown_call_keys)[:5]}",
                "reason": "账本调用明细含虚假 slice ID - fail-closed"},
                ensure_ascii=False))
            raise SystemExit(2)

        # 2. slices_completed 必须有对应调用记录
        completed_set = set(self._data["slices_completed"])
        calls_set = set(self._data["calls_attempted_by_slice"].keys())
        orphan_completed = completed_set - calls_set
        if orphan_completed:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"slices_completed 含无调用记录的 ID: "
                         f"{sorted(orphan_completed)[:5]}",
                "reason": "completed slice 无对应调用明细 - fail-closed"},
                ensure_ascii=False))
            raise SystemExit(2)

        # 3. slices_completed 的 key 必须属于 schedule
        unknown_completed = completed_set - schedule_ids
        if unknown_completed:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"slices_completed 含未知 slice ID: "
                         f"{sorted(unknown_completed)[:5]}",
                "reason": "completed slice 不在 schedule 中 - fail-closed"},
                ensure_ascii=False))
            raise SystemExit(2)

        # 4. allocated_cap_by_slice 的 key 必须属于 schedule
        allocated_keys = set(self._data["allocated_cap_by_slice"].keys())
        unknown_allocated = allocated_keys - schedule_ids
        if unknown_allocated:
            print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                "path": self.path,
                "error": f"allocated_cap_by_slice 含未知 slice ID: "
                         f"{sorted(unknown_allocated)[:5]}",
                "reason": "allocated_cap 含虚假 slice ID - fail-closed"},
                ensure_ascii=False))
            raise SystemExit(2)

        # 5. allocated_cap 与 manifest hard_cap 一致性检查
        #    对于已有 manifest 的 slice, allocated_cap 必须等于 manifest hard_cap
        for sid, allocated_cap in self._data["allocated_cap_by_slice"].items():
            sl = schedule_by_id.get(sid)
            if sl is None:
                continue  # 已被第 4 步拦截
            manifest_path = sl.get("manifest_path")
            if manifest_path and os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        runner_manifest = json.load(f)
                    manifest_hard_cap = runner_manifest.get("hard_cap")
                    if manifest_hard_cap is not None and manifest_hard_cap != allocated_cap:
                        print(json.dumps({"status": "BUDGET_LEDGER_CORRUPTED",
                            "path": self.path,
                            "error": f"slice {sid}: allocated_cap={allocated_cap} "
                                     f"!= manifest hard_cap={manifest_hard_cap}",
                            "reason": "allocated_cap 与 manifest hard_cap 不一致 - fail-closed"},
                            ensure_ascii=False))
                        raise SystemExit(2)
                except (json.JSONDecodeError, OSError):
                    # manifest 损坏由 verify_slice_manifest 处理，这里跳过
                    pass


# ---- effective cap helpers ----

def compute_effective_cap(slice_id: str, ledger: BudgetLedger,
                          already_attempted_for_slice: int) -> int:
    """首次启动分配 cap, 写入 BudgetLedger._data["allocated_cap_by_slice"].
    resume 从 ledger 读取, 不重新分配, 但必须执行全局预算公式检查.

    already_attempted_for_slice: 必须显式传入, 无默认值.
    来源: ledger._data["calls_attempted_by_slice"][slice_id] (经 events reconciliation).
    resume 前必须先完成 events -> ledger reconciliation, 再计算预算.
    """
    # 0. 验证 already_attempted_for_slice 已显式传入且合法
    if already_attempted_for_slice is None:
        raise SystemExit(2)
    if already_attempted_for_slice < 0:
        raise SystemExit(2)

    cumulative_calls = ledger._data["total_calls_attempted"]
    allocations = ledger._data.setdefault("allocated_cap_by_slice", {})

    # 1. resume 路径: 已有分配
    if slice_id in allocations:
        effective_cap = allocations[slice_id]
        if already_attempted_for_slice > effective_cap:
            raise SystemExit(2)
        # 执行冻结的 resume 预算公式:
        # total_attempted + (effective_cap - already_attempted) <= 1320
        remaining_budget = cumulative_calls + (effective_cap - already_attempted_for_slice)
        if remaining_budget > GLOBAL_LEDGER_CAP:
            print(json.dumps({"status": "BLOCKED_BUDGET_EXHAUSTED",
                             "slice_id": slice_id,
                             "cumulative_calls": cumulative_calls,
                             "effective_cap": effective_cap,
                             "already_attempted": already_attempted_for_slice,
                             "projected_total": remaining_budget},
                             ensure_ascii=False))
            raise SystemExit(2)
        return effective_cap

    # 2. 首次分配
    global_remaining = GLOBAL_LEDGER_CAP - cumulative_calls
    effective_cap = min(SLICE_MAX_CAP, global_remaining)

    if effective_cap < SLICE_BASE_CALLS:
        print(json.dumps({"status": "BLOCKED_BUDGET_EXHAUSTED",
                         "slice_id": slice_id,
                         "cumulative_calls": cumulative_calls,
                         "remaining": global_remaining},
                         ensure_ascii=False))
        raise SystemExit(2)

    # 3. 原子写入 BudgetLedger
    allocations[slice_id] = effective_cap
    ledger._save()
    return effective_cap


def verify_cap_consistency_on_resume(slice_id: str, runner_manifest: dict,
                                     ledger: BudgetLedger):
    """resume 时验证 ledger 分配值与 runner manifest hard_cap 一致.

    返回 ledger_cap (已分配的 cap), 供后续步骤使用.
    """
    ledger_cap = ledger._data.get("allocated_cap_by_slice", {}).get(slice_id)
    manifest_cap = runner_manifest.get("hard_cap")

    if ledger_cap is None and manifest_cap is None:
        return None  # 两者都无, 首跑
    if ledger_cap is None and manifest_cap is not None:
        raise SystemExit(2)  # runner manifest 存在但 ledger 缺失
    if ledger_cap is not None and manifest_cap is None:
        return ledger_cap  # ledger 有分配但 runner 无产物, 允许首跑
    if ledger_cap != manifest_cap:
        raise SystemExit(2)  # 两者不一致
    return ledger_cap


# ---- events helpers (复用 6B1) ----

def _count_call_attempts(events_path: str) -> int:
    """Count call_attempt events from events file."""
    if not events_path or not os.path.exists(events_path):
        return 0
    count = 0
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("kind") == "call_attempt":
                    count += 1
            except json.JSONDecodeError:
                pass
    return count


def _validate_events(events_path: str, scheduled_calls: int,
                     hard_cap: int) -> tuple:
    """Validate events file: parseable, count within [scheduled_calls, hard_cap].
    Returns (ok, count, reason).
    """
    if not events_path or not os.path.exists(events_path):
        return False, 0, "events file missing"
    count = 0
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("kind") == "call_attempt":
                    count += 1
    except (json.JSONDecodeError, OSError) as e:
        return False, 0, f"events file corrupt: {e}"
    if count < scheduled_calls:
        return False, count, f"calls {count} < scheduled {scheduled_calls}"
    if count > hard_cap:
        return False, count, f"calls {count} > hard_cap {hard_cap}"
    return True, count, "ok"


def _validate_partial_events(events_path: str, allocated_cap: int) -> tuple:
    """Validate partial events: parseable, 1 <= count <= allocated_cap.
    Allows calls < scheduled_calls (partial resume).
    Rejects count == 0 (零调用 events 视为损坏, 合法零调用走 manifest-only 分支).
    Returns (ok, count, reason).
    """
    if not events_path or not os.path.exists(events_path):
        return False, 0, "events file missing"
    count = 0
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("kind") == "call_attempt":
                    count += 1
    except (json.JSONDecodeError, OSError) as e:
        return False, 0, f"events file corrupt: {e}"
    if count == 0:
        return False, 0, "events file exists but has 0 call_attempt (corrupt, use manifest-only branch for zero calls)"
    if count > allocated_cap:
        return False, count, f"calls {count} > allocated_cap {allocated_cap}"
    return True, count, "ok"


def reconcile_partial_events(sl: dict, ledger: BudgetLedger,
                             allocated_cap: int) -> int:
    """Partial resume 的证据回算 helper.

    用于崩溃后已产生部分调用的 slice (smoke 或普通 slice).
    与 verify_smoke_completed 不同, 本函数:
    - 允许调用数小于 scheduled_calls;
    - 不要求 details 完整、expected keys 完全相等、parser 8/8;
    - 不标记 slice 为 completed;
    - 只按 events 中的 call_attempt 回算 ledger.

    参数 allocated_cap: 从 ledger._data["allocated_cap_by_slice"] 读取的历史分配值
    (不是 compute_effective_cap 的返回值, 避免循环依赖).

    Manifest-only 状态处理 (events 不存在):
    - events 不存在时, 不调用 _validate_partial_events
    - 仅真正 manifest-only (manifest 存在、details 不存在、ledger 历史调用数为 0) 时返回 0
    - 若 details 已存在或 ledger 历史调用数非零, 说明调用证据丢失, BLOCKED_EVIDENCE_LOST
    """
    events_path = sl["events_path"]
    events_exists = os.path.exists(events_path)

    # 1. Manifest-only 状态严格判定 (events 不存在)
    if not events_exists:
        details_exists = os.path.exists(sl["detail_path"])
        ledger_calls = ledger._data["calls_attempted_by_slice"].get(sl["slice_id"], 0)

        # 仅当 details 不存在且 ledger 历史调用数为 0 时才是合法 manifest-only
        if details_exists or ledger_calls != 0:
            print(json.dumps({"status": "BLOCKED_EVIDENCE_LOST",
                             "slice_id": sl["slice_id"],
                             "reason": "events missing but details exists or ledger_calls non-zero",
                             "details_exists": details_exists,
                             "ledger_calls": ledger_calls},
                             ensure_ascii=False))
            raise SystemExit(2)

        # 真正的 manifest-only: 无证据可回算, already_attempted = 0
        return 0

    # 2. events 存在: 解析, 只统计 kind == "call_attempt"
    ok, calls, reason = _validate_partial_events(events_path, allocated_cap)
    if not ok:
        print(json.dumps({"status": "BLOCKED_PARTIAL_EVENTS_CORRUPT",
                         "slice_id": sl["slice_id"],
                         "reason": reason}, ensure_ascii=False))
        raise SystemExit(2)

    # 3. 事务式 ledger 回算 (先在副本上验证, 全部通过后一次性提交)
    new_calls_by_slice = dict(ledger._data["calls_attempted_by_slice"])
    new_calls_by_slice[sl["slice_id"]] = calls
    new_total = sum(new_calls_by_slice.values())

    # 4. 预算检查
    if new_total > ledger.hard_cap:
        print(json.dumps({"status": "BUDGET_EXCEEDED",
                         "slice_id": sl["slice_id"],
                         "new_total": new_total}, ensure_ascii=False))
        raise SystemExit(2)

    # 5. 全部验证通过, 一次性替换内存状态 (不加入 slices_completed)
    ledger._data["calls_attempted_by_slice"] = new_calls_by_slice
    ledger._data["total_calls_attempted"] = new_total
    ledger._save()

    return calls


# ---- smoke state machine ----

def determine_smoke_state(smoke_sl: dict) -> str:
    """直接复用 6B1 五状态判定逻辑.

    路径来源: schedule 中已冻结的 smoke_sl["detail_path"]/events_path/manifest_path.
    返回: fresh / resume / completed / blocked_corrupt
    """
    smoke_detail = Path(smoke_sl["detail_path"])
    smoke_manifest = Path(smoke_sl["manifest_path"])
    smoke_events = Path(smoke_sl["events_path"])

    detail_exists = smoke_detail.exists()
    manifest_exists = smoke_manifest.exists()
    events_exists = smoke_events.exists()

    # 1. 无任何产物 -> fresh
    if not detail_exists and not manifest_exists and not events_exists:
        return "fresh"

    # 2. detail + manifest 都存在 -> 检查终态数量
    if detail_exists and manifest_exists:
        rows = load_jsonl(str(smoke_detail))
        terminal_count = sum(
            1 for r in rows
            if r.get("terminal_state") in TERMINAL_STATES
        )
        if terminal_count >= smoke_sl["size"]:
            return "completed"
        else:
            return "resume"

    # 3. manifest 存在但 detail 不存在 -> 合法 resume (manifest-only)
    if manifest_exists and not detail_exists:
        return "resume"

    # 4. detail 存在但 manifest 不存在 -> blocked_corrupt
    if detail_exists and not manifest_exists:
        return "blocked_corrupt"

    # 5. 其他情况 -> blocked_corrupt
    return "blocked_corrupt"


def verify_smoke_completed(smoke_sl: dict, args, ledger: BudgetLedger,
                           require_parser_rate: bool = True):
    """completed 状态的完整验证, 直接复用 6B1 完整验证路径.
    验证成功后执行原子 ledger reconciliation.
    Returns (ok, reason).

    require_parser_rate=True (smoke): 要求 8/8 parsed (SMOKE_PARSER_RATE_THRESHOLD).
    require_parser_rate=False (main): 不要求全部 parsed, 但验证终态数量、expected-set、
        manifest、events. invalid/unresolved/call_failed 保留在分母中不阻断.
    """
    smoke_detail = Path(smoke_sl["detail_path"])
    smoke_manifest = Path(smoke_sl["manifest_path"])
    smoke_events = Path(smoke_sl["events_path"])

    # 1. events 必须存在
    if not smoke_events.exists():
        return False, "completed state but events file missing"

    # 2. verify_slice_manifest 全字段指纹
    ok, diff = verify_slice_manifest(smoke_sl, args.provider, args.model)
    if not ok:
        return False, f"smoke manifest 与当前配置不一致: {diff}"

    # 3. expected attempt-key 集合完全相等
    rows = load_jsonl(str(smoke_detail))
    detail_keys = [tuple(r.get("attempt_key", [])) for r in rows]
    completed_keys = set(detail_keys)
    dataset_id = os.path.splitext(os.path.basename(smoke_sl["dataset"]))[0]
    expected_keys = set()
    for case_id in smoke_sl["case_ids"]:
        expected_keys.add(build_expected_key(
            dataset_id, REASONED_PROFILE, smoke_sl["arm"],
            case_id, smoke_sl["repeat"], args.provider, args.model,
        ))

    # 4. details 数量 == expected 数量
    if len(detail_keys) != len(expected_keys):
        return False, f"details 数量不匹配: expected={len(expected_keys)} got={len(detail_keys)}"

    # 5. 无重复 attempt key
    if len(completed_keys) != len(detail_keys):
        return False, "存在重复 attempt key"

    # 6. completed keys == expected keys
    if completed_keys != expected_keys:
        return False, "completed keys != expected keys"

    # 7. parser rate (smoke: 8/8 = 100%, main: 不要求全部 parsed)
    if require_parser_rate:
        parse_ok = sum(1 for r in rows if r.get("terminal_state") == "parsed")
        parser_rate = parse_ok / len(rows) if rows else 0
        if parser_rate < SMOKE_PARSER_RATE_THRESHOLD:
            return False, f"parser_rate={parser_rate} < {SMOKE_PARSER_RATE_THRESHOLD}"
    else:
        non_terminal = sum(
            1 for r in rows if r.get("terminal_state") not in TERMINAL_STATES)
        if non_terminal > 0:
            return False, f"{non_terminal} records without terminal state"

    # 8. events 可解析 + 调用数 ∈ [scheduled, hard_cap]
    ev_ok, calls, ev_reason = _validate_events(
        str(smoke_events), smoke_sl["size"], smoke_sl["hard_cap"])
    if not ev_ok:
        return False, f"events validation failed: {ev_reason}"

    # 9. 事务式 ledger reconciliation
    new_calls_by_slice = dict(ledger._data["calls_attempted_by_slice"])
    new_calls_by_slice[smoke_sl["slice_id"]] = calls
    new_total = sum(new_calls_by_slice.values())

    if new_total > ledger.hard_cap:
        return False, f"BUDGET_EXCEEDED after reconciliation: total={new_total}"
    if new_total != sum(new_calls_by_slice.values()):
        return False, f"ledger total mismatch: new_total={new_total}"

    ledger._data["calls_attempted_by_slice"] = new_calls_by_slice
    ledger._data["total_calls_attempted"] = new_total
    if smoke_sl["slice_id"] not in ledger._data["slices_completed"]:
        ledger._data["slices_completed"].append(smoke_sl["slice_id"])
    ledger._save()

    return True, "ok"


# ---- manifest verification (reuse runner's RESUME_MANIFEST_FIELDS) ----

def _build_current_manifest(sl: dict, provider: str, model: str) -> dict:
    """Build manifest dict matching runner's build_resume_manifest()."""
    from benchmark.runners.run_benchmark import _sha256_file, _code_fingerprint, RESUME_MANIFEST_FIELDS
    from benchmark.runners.profiles import prompt_fingerprint, resolve_profile

    profile = resolve_profile(REASONED_PROFILE, sl.get("chart_schema_version", CHART_SCHEMA))
    case_ids_file = os.path.join(sl["output_dir"], f"case_ids_{sl['slice_id']}.json")

    manifest = {
        "dataset_sha256": _sha256_file(os.path.abspath(sl["dataset"])),
        "case_ids_sha256": (_sha256_file(os.path.abspath(case_ids_file))
                            if os.path.exists(case_ids_file) else None),
        "profile_id": profile.profile_id,
        "chart_schema_version": profile.chart_schema_version,
        "arm": sl["arm"],
        "ziwei_arm": sl["ziwei_arm"],
        "attempt_stage": "main",
        "repeat_idx": sl["repeat"],
        "provider": provider,
        "model": model,
        "temperature": 0.0,
        "sample_temperature": 0.4,
        "n_samples": 1,
        "aggregate": "majority",
        "method": "direct_choice",
        "prompt_template_sha256": prompt_fingerprint(profile),
        "code_sha256": _code_fingerprint(),
        "scheduled_calls": sl["size"],
        "hard_cap": sl["hard_cap"],
        "as_of_date": FROZEN_DATE,
    }
    return manifest


def build_expected_key(dataset_id: str, profile_id: str, arm: str,
                       case_id: str, repeat_idx: int,
                       provider: str, model: str) -> tuple:
    """Build expected attempt key matching runner's 10-tuple format."""
    return (dataset_id, profile_id, arm, "main", provider, model,
            str(case_id), int(repeat_idx), 0, "p0")


def verify_slice_manifest(sl: dict, provider: str, model: str) -> tuple:
    """Verify slice manifest matches current configuration.
    Returns (ok, diff) where diff is {} on success or {field: {stored, current}} on mismatch.
    """
    from benchmark.runners.run_benchmark import RESUME_MANIFEST_FIELDS

    manifest_path = sl["manifest_path"]
    if not os.path.exists(manifest_path):
        return False, {"_manifest": {"stored": "<MISSING>", "current": "exists expected"}}
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            stored = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, {"_manifest": {"stored": f"<ERROR: {e}>", "current": "valid JSON expected"}}

    current = _build_current_manifest(sl, provider, model)
    diff = {}
    for k in RESUME_MANIFEST_FIELDS:
        stored_val = stored.get(k, "<MISSING>")
        current_val = current.get(k)
        if stored_val != current_val:
            diff[k] = {"stored": stored_val, "current": current_val}
    return len(diff) == 0, diff


def generate_schedule(output_dir) -> dict:
    """Generate atomic 150-slice schedule with 5×5 Latin square.

    5 arms × 5 groups × 2 years × 3 repeats = 150 slices.
    每 slice 8 题, local cap 10, 全局 hard cap 1320.
    5×5 Latin square 全程交错, 每个 (year, repeat) 内 5 个 position 覆盖全部 5 arm.

    Builds the schedule via _build_schedule (pure, no I/O) then atomically writes
    schedule.json. main() verifies the run manifest BEFORE calling this on resume.
    """
    schedule = _build_schedule(output_dir)
    output_dir = Path(output_dir)
    schedule_path = output_dir / "schedule.json"
    atomic_write_json(str(schedule_path), schedule)
    print(f"[schedule] {len(schedule['slices'])} slices, "
          f"{schedule['total_scheduled_calls']} calls "
          f"(hard_cap total={schedule['total_hard_cap']}) -> {schedule_path}")
    return schedule


def _build_schedule(output_dir) -> dict:
    """Pure schedule construction (no disk writes). Used by main() for resume
    consistency checks and by dry-run inspection without side effects."""
    output_dir = Path(output_dir)

    slices = []
    # Interleave: cycle positions across all (year, repeat) cells
    # to avoid temporal bias (spec §8.1)
    for position in range(GROUPS_PER_CELL):
        for year in YEARS:
            for repeat in REPEATS:
                for group in range(GROUPS_PER_CELL):
                    arm = LATIN_SQUARE[position][group]
                    size = SLICE_SIZE
                    ziwei_arm = ARM_ZIWEI_MAP[arm]
                    # slice_id format: {year}_{arm}_R{repeat}_P{position}_G{group}
                    slice_id = f"{year}_{arm}_R{repeat}_P{position}_G{group}"

                    case_start = group * SLICE_SIZE
                    case_end = case_start + size

                    slice_dir = output_dir / f"slice_{slice_id}"
                    detail_name = f"details_{slice_id}.jsonl"
                    events_name = f"details_{slice_id}.events.jsonl"
                    manifest_name = f"details_{slice_id}.manifest.json"

                    slices.append({
                        "slice_id": slice_id,
                        "year": year,
                        "repeat": repeat,
                        "arm": arm,
                        "ziwei_arm": ziwei_arm,
                        "group": group,
                        "position": position,
                        "size": size,
                        "scheduled_calls": size,
                        "hard_cap": SLICE_MAX_CAP,
                        "case_start": case_start,
                        "case_end": case_end,
                        "output_dir": str(slice_dir),
                        "detail_path": str(slice_dir / detail_name),
                        "events_path": str(slice_dir / events_name),
                        "manifest_path": str(slice_dir / manifest_name),
                        "dataset": YEAR_DATASETS[year],
                        "chart_schema_version": CHART_SCHEMA,
                    })

    # Fill case_ids for each slice
    year_cases = {}
    for year in YEARS:
        year_cases[year] = load_jsonl(YEAR_DATASETS[year])

    for sl in slices:
        sl["case_ids"] = [
            c["case_id"]
            for c in year_cases[sl["year"]][sl["case_start"]:sl["case_end"]]
        ]
        sl["question_ids"] = [
            c.get("question", f"q_{c['case_id']}")
            for c in year_cases[sl["year"]][sl["case_start"]:sl["case_end"]]
        ]

    schedule = {
        "experiment": EXPERIMENT_ID_PREFIX,
        "total_slices": len(slices),
        "total_scheduled_calls": sum(s["size"] for s in slices),
        "total_hard_cap": sum(s["hard_cap"] for s in slices),
        "global_hard_cap": GLOBAL_LEDGER_CAP,
        "frozen_date": FROZEN_DATE,
        "years": YEARS,
        "repeats": len(REPEATS),
        "arms": ARMS,
        "arm_ziwei_map": ARM_ZIWEI_MAP,
        "profile": REASONED_PROFILE,
        "chart_schema_version": CHART_SCHEMA,
        "latin_square": {str(k): v for k, v in LATIN_SQUARE.items()},
        "slice_layout": SLICE_LAYOUT,
        "groups_per_cell": GROUPS_PER_CELL,
        "slice_size": SLICE_SIZE,
        "slice_max_cap": SLICE_MAX_CAP,
        "slices": slices,
    }
    return schedule


# ---- resume/fresh detection (P0 #1: verify manifest BEFORE schedule write) ----

def _has_historical_artifacts(output_dir: Path) -> bool:
    """True if output_dir shows evidence of a prior run beyond a dry-run schedule.

    budget_ledger.json or any slice_* directory indicate a real (possibly partial)
    run. schedule.json alone does NOT (it may be a dry-run leftover).
    """
    if (output_dir / "budget_ledger.json").exists():
        return True
    if output_dir.exists():
        for entry in output_dir.iterdir():
            if entry.is_dir() and entry.name.startswith("slice_"):
                return True
    return False


def _load_schedule_json(output_dir: Path):
    """Load on-disk schedule.json; return None if missing/corrupt."""
    path = output_dir / "schedule.json"
    if not path.exists():
        return None
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


_SCHEDULE_TOP_LEVEL_SEMANTIC_FIELDS = (
    "experiment", "total_slices", "total_scheduled_calls", "total_hard_cap",
    "global_hard_cap", "frozen_date", "years", "repeats", "arms",
    "arm_ziwei_map", "profile", "chart_schema_version", "latin_square",
    "slice_layout", "groups_per_cell", "slice_size", "slice_max_cap",
)

_SLICE_PATH_FIELDS = ("output_dir", "detail_path", "events_path", "manifest_path")


def _canonicalize(value):
    """Normalize a value to its JSON-canonical form for comparison.

    JSON round-trip (json.loads(json.dumps(x))) stringifies all dict keys, so a
    freshly built schedule (int dict keys, e.g. latin_square inner keys) and a
    schedule loaded from disk (all-string keys after JSON serialization) compare
    equal. Real semantic tampering (e.g. a changed arm value) survives
    canonicalization and is still detected.
    """
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False))


def _strip_path_fields(slice_dict):
    """Return a copy of slice_dict with derived path fields removed.

    Path fields (output_dir/detail_path/events_path/manifest_path) are
    recomputed from output_dir and carry no experiment semantics, so they are
    excluded from consistency comparison. Every other field (including ones
    added in the future) is compared, so new semantic fields cannot slip
    through unchecked.
    """
    return {k: v for k, v in slice_dict.items() if k not in _SLICE_PATH_FIELDS}


def _verify_schedule_consistent(historical, built) -> tuple:
    """Verify a freshly built schedule matches the on-disk historical schedule.

    Deep-compares all semantic fields (experiment-defining values) while
    excluding only derived path fields (output_dir/detail_path/events_path/
    manifest_path), which are recomputed from output_dir and carry no
    experiment semantics. Values are canonicalized via JSON round-trip so that
    key-type artifacts from JSON serialization (int keys -> str keys) do not
    cause false positives, while real semantic tampering (e.g. a changed arm)
    is still caught.

    Slice comparison is order- and count-preserving (the main loop treats
    slices[0:5] as smoke and iterates the rest in order, so reordering or
    duplicate slice_ids must be detected): it verifies len(slices) equals the
    declared total_slices, slice_id uniqueness, equal list lengths, and a
    position-wise deep-compare of each slice (minus path fields). Returns
    (ok, reason).
    """
    if historical is None:
        return False, "run_manifest exists but schedule.json missing/corrupt"

    for field in _SCHEDULE_TOP_LEVEL_SEMANTIC_FIELDS:
        hv = _canonicalize(historical.get(field))
        bv = _canonicalize(built.get(field))
        if hv != bv:
            return False, (f"top-level {field} mismatch: "
                           f"historical={hv!r} built={bv!r}")

    h_slices = historical.get("slices", []) or []
    b_slices = built.get("slices", []) or []
    total = historical.get("total_slices")

    # Count must equal the declared total_slices (catches a tampered total_slices
    # that still matches between historical/built but disagrees with the actual
    # list length, e.g. total_slices=150 with 151 slices).
    if total is not None and len(h_slices) != total:
        return False, (f"historical len(slices)={len(h_slices)} != "
                       f"total_slices={total}")
    if total is not None and len(b_slices) != total:
        return False, (f"built len(slices)={len(b_slices)} != "
                       f"total_slices={total}")

    # Equal list lengths (catches appended duplicate / removed slice).
    if len(h_slices) != len(b_slices):
        return False, (f"slice count mismatch: historical={len(h_slices)} "
                       f"built={len(b_slices)}")

    # slice_id uniqueness within each list (catches duplicate slice_ids that a
    # dict-based comparison would silently fold together).
    for label, slices in (("historical", h_slices), ("built", b_slices)):
        ids = [s.get("slice_id") for s in slices]
        if len(ids) != len(set(ids)):
            dupes = [i for i in ids if ids.count(i) > 1]
            return False, (f"{label} has duplicate slice_ids: {set(dupes)}")

    # Position-wise deep-compare (order-preserving): the main loop treats
    # slices[0:5] as smoke and iterates the rest in order, so a reordering that
    # a dict comparison would miss must be caught here.
    for idx, (h_sl, b_sl) in enumerate(zip(h_slices, b_slices)):
        h_norm = _canonicalize(_strip_path_fields(h_sl))
        b_norm = _canonicalize(_strip_path_fields(b_sl))
        if h_norm != b_norm:
            sid = h_sl.get("slice_id", f"<pos {idx}>")
            diff_keys = sorted(set(h_norm.keys()) ^ set(b_norm.keys()))
            if diff_keys:
                return False, (f"slice {sid} (pos {idx}) field set mismatch: "
                               f"symmetric diff={diff_keys}")
            changed = sorted(k for k in h_norm if h_norm.get(k) != b_norm.get(k))
            return False, (f"slice {sid} (pos {idx}) field(s) mismatch: "
                           f"{changed}")
    return True, "ok"


# ---- slice state machine (unified for smoke and main) ----

def _resolve_slice_state(sl: dict) -> str:
    """统一状态判定: fresh / resume / completed / blocked_corrupt.
    复用 determine_smoke_state 逻辑.
    """
    return determine_smoke_state(sl)


def _verify_slice_completed(sl: dict, args, ledger: BudgetLedger,
                            is_smoke: bool = True) -> bool:
    """验证 slice 已完成: manifest 一致 + expected-set 完整 + ledger reconciliation.
    is_smoke=True: 要求 100% parser rate (smoke gate).
    is_smoke=False: 不要求全部 parsed (main slice, invalid/unresolved/call_failed 保留在分母中).
    成功返回 True, 失败返回 False (不 exit, 由调用者决定).
    """
    ok, reason = verify_smoke_completed(sl, args, ledger,
                                        require_parser_rate=is_smoke)
    if not ok:
        print(json.dumps({"status": "BLOCKED_SLICE_VERIFY",
            "slice_id": sl["slice_id"], "reason": reason}, ensure_ascii=False))
        return False
    return True


def _audit_skipped_slices(schedule: dict, from_slice: int, args,
                          ledger: BudgetLedger) -> bool:
    """--from-slice 审计: 被跳过的 slice 必须全部 completed 且验证通过.
    返回 True=通过, False=失败.
    """
    if from_slice <= 0:
        return True

    # Cap at schedule length: --from-slice beyond TOTAL_SLICES audits all
    # existing slices (avoids IndexError; main loop already ignores idx >= 150).
    n = len(schedule["slices"])
    for idx in range(min(from_slice, n)):
        sl = schedule["slices"][idx]
        state = _resolve_slice_state(sl)
        if state != "completed":
            print(json.dumps({"status": "BLOCKED_FROM_SLICE_AUDIT",
                "slice_id": sl["slice_id"], "index": idx,
                "state": state,
                "reason": f"--from-slice 跳过的 slice 未完成 (state={state})"},
                ensure_ascii=False))
            return False
        if not _verify_slice_completed(sl, args, ledger,
                                        is_smoke=(idx < 5)):
            return False
    return True


def _integrity_gate(schedule: dict, ledger: BudgetLedger,
                    args) -> tuple:
    """实验完成前 integrity gate:
    1. 1200 条记录 (150 slices × 8)
    2. 每臂 240 条 (150/5 × 8)
    3. 全部 150 slices completed
    返回 (ok, reason).
    """
    # 1. 全部 150 slices completed
    completed_set = set(ledger._data["slices_completed"])
    schedule_ids = {sl["slice_id"] for sl in schedule["slices"]}
    missing = schedule_ids - completed_set
    if missing:
        return False, f"未完成 slices: {len(missing)} (如 {sorted(missing)[:3]})"

    # 2. 1200 条记录
    total_records = 0
    arm_records = {arm: 0 for arm in ARMS}
    for sl in schedule["slices"]:
        if not os.path.exists(sl["detail_path"]):
            return False, f"slice {sl['slice_id']} detail 文件缺失"
        rows = load_jsonl(sl["detail_path"])
        total_records += len(rows)
        arm_records[sl["arm"]] += len(rows)

    if total_records != TOTAL_SCHEDULED_CALLS:
        return False, f"总记录数 {total_records} != {TOTAL_SCHEDULED_CALLS}"

    # 3. 每臂 240 条
    expected_per_arm = (TOTAL_SLICES // len(ARMS)) * SLICE_SIZE
    for arm, count in arm_records.items():
        if count != expected_per_arm:
            return False, f"arm {arm} 记录数 {count} != {expected_per_arm}"

    return True, "ok"


# ---- descriptive comparison table (plan §4.12) ----

def _collect_arm_clusters(schedule: dict, ledger: BudgetLedger) -> dict:
    """Collect per-arm correctness grouped by (year, case_id) cluster.

    Returns {arm: {(year, case_id): [correct_bool, ...]}}.
    Only completed slices with readable detail files are included.
    """
    arm_clusters: dict = {arm: {} for arm in ARMS}
    for sl in schedule["slices"]:
        if not ledger.sliced_completed(sl["slice_id"]):
            continue
        if not os.path.exists(sl["detail_path"]):
            continue
        for row in load_jsonl(sl["detail_path"]):
            correct = row.get("correct") is True
            cluster_key = (sl["year"], row.get("case_id"))
            arm_clusters[sl["arm"]].setdefault(cluster_key, []).append(correct)
    return arm_clusters


def _cluster_accuracy_ci(clusters: dict) -> tuple:
    """Cluster bootstrap CI for a single arm's accuracy.

    Resampling unit: (year, case_id) cluster. seed=42, 10k draws.
    Returns (point_estimate, ci_low, ci_high). Without numpy, CI == point.
    """
    if not clusters:
        return 0.0, 0.0, 0.0

    keys = sorted(clusters.keys())
    sums = [sum(clusters[k]) for k in keys]
    sizes = [len(clusters[k]) for k in keys]
    total_correct = sum(sums)
    total_n = sum(sizes)
    point = total_correct / total_n if total_n else 0.0

    if not _HAS_NUMPY or len(keys) < 2:
        return point, point, point

    sums_arr = np.array(sums, dtype=float)
    sizes_arr = np.array(sizes, dtype=float)
    n = len(keys)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    idx = rng.integers(0, n, size=(BOOTSTRAP_DRAWS, n))
    num = sums_arr[idx].sum(axis=1)
    den = sizes_arr[idx].sum(axis=1)
    # Guard against zero denominator (only possible if all clusters empty)
    draws = np.where(den > 0, num / den, 0.0)
    ci_low = float(np.percentile(draws, 2.5))
    ci_high = float(np.percentile(draws, 97.5))
    return float(point), ci_low, ci_high


def _pairwise_diff_ci(clusters_a: dict, clusters_b: dict) -> tuple:
    """Paired cluster bootstrap CI for acc_a - acc_b.

    Same resample indices applied to both arms (paired). seed=42, 10k draws.
    Returns (point_diff, ci_low, ci_high).
    """
    common = sorted(set(clusters_a.keys()) & set(clusters_b.keys()))
    if not common:
        return 0.0, 0.0, 0.0

    sums_a = [sum(clusters_a[k]) for k in common]
    sums_b = [sum(clusters_b[k]) for k in common]
    sizes = [len(clusters_a[k]) for k in common]
    total_n = sum(sizes)
    point = (sum(sums_a) - sum(sums_b)) / total_n if total_n else 0.0

    if not _HAS_NUMPY or len(common) < 2:
        return point, point, point

    sums_a_arr = np.array(sums_a, dtype=float)
    sums_b_arr = np.array(sums_b, dtype=float)
    sizes_arr = np.array(sizes, dtype=float)
    n = len(common)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    idx = rng.integers(0, n, size=(BOOTSTRAP_DRAWS, n))
    den = sizes_arr[idx].sum(axis=1)
    acc_a = np.where(den > 0, sums_a_arr[idx].sum(axis=1) / den, 0.0)
    acc_b = np.where(den > 0, sums_b_arr[idx].sum(axis=1) / den, 0.0)
    draws = acc_a - acc_b
    ci_low = float(np.percentile(draws, 2.5))
    ci_high = float(np.percentile(draws, 97.5))
    return float(point), ci_low, ci_high


def generate_comparison_table(schedule: dict, ledger: BudgetLedger,
                              provider: str, model: str) -> dict:
    """5-arm descriptive comparison table with cluster bootstrap CI.

    纯描述性分析, 不作显著性宣称 (plan §4.12).
    - 五臂准确率排序
    - 两两差值表 (10 pairs)
    - Bootstrap CI: seed=42, 10k draws, year×question 聚类
    """
    arm_clusters = _collect_arm_clusters(schedule, ledger)

    arm_stats = {}
    for arm in ARMS:
        clusters = arm_clusters[arm]
        point, ci_low, ci_high = _cluster_accuracy_ci(clusters)
        arm_stats[arm] = {
            "accuracy": round(point, 4),
            "ci_low": round(ci_low, 4),
            "ci_high": round(ci_high, 4),
            "n_records": sum(len(v) for v in clusters.values()),
            "n_clusters": len(clusters),
        }

    ranking = sorted(ARMS, key=lambda a: arm_stats[a]["accuracy"], reverse=True)

    pairwise_diffs = []
    for i, arm_a in enumerate(ARMS):
        for arm_b in ARMS[i + 1:]:
            diff, d_low, d_high = _pairwise_diff_ci(
                arm_clusters[arm_a], arm_clusters[arm_b])
            pairwise_diffs.append({
                "arm_a": arm_a,
                "arm_b": arm_b,
                "diff": round(diff, 4),
                "ci_low": round(d_low, 4),
                "ci_high": round(d_high, 4),
            })

    return {
        "experiment": EXPERIMENT_ID_PREFIX,
        "arms": list(ARMS),
        "arm_stats": arm_stats,
        "ranking": ranking,
        "pairwise_diffs": pairwise_diffs,
        "bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "draws": BOOTSTRAP_DRAWS,
            "clustering": BOOTSTRAP_CLUSTERS,
            "numpy_available": _HAS_NUMPY,
        },
        "token_stats": compute_token_stats(schedule, ledger, provider, model),
        "tiktoken_available": _HAS_TIKTOKEN,
        "total_calls_attempted": ledger.total_attempted,
    }


def compute_token_stats(schedule: dict, ledger: BudgetLedger,
                        provider: str, model: str) -> dict:
    """Compute per-arm token statistics (plan §4.9).

    Per-arm source selection (NOT global): each arm independently uses provider
    usage if its completed slices carry usage fields, otherwise falls back to
    tiktoken estimation, otherwise NOT_AVAILABLE.

    tiktoken fallback renders prompts for ALL 80 unique cases across both year
    datasets (not a 10-case sample), so avg_input reflects the experiment mean.

    When output tokens are unknown (tiktoken fallback), avg_total is NOT_AVAILABLE
    (not equal to avg_input).

    Returns {arm: {avg_input, avg_output, avg_total, source, n}} where source
    is "provider", "tiktoken", or "NOT_AVAILABLE".
    """
    NOT_AVAILABLE = "NOT_AVAILABLE"
    stats = {}

    # Phase 1: collect provider usage per arm from completed slices' detail rows
    arm_usage = {arm: {"input": [], "output": []} for arm in ARMS}
    for sl in schedule["slices"]:
        if not ledger.sliced_completed(sl["slice_id"]):
            continue
        if not os.path.exists(sl["detail_path"]):
            continue
        for row in load_jsonl(sl["detail_path"]):
            usage = row.get("usage") or row.get("token_usage")
            if usage and isinstance(usage, dict):
                inp = usage.get("prompt_tokens") or usage.get("input_tokens")
                out = usage.get("completion_tokens") or usage.get("output_tokens")
                if inp is not None:
                    arm_usage[sl["arm"]]["input"].append(int(inp))
                if out is not None:
                    arm_usage[sl["arm"]]["output"].append(int(out))

    # Phase 2: tiktoken estimation over all 80 unique cases (both years)
    arm_tiktoken_counts = {arm: [] for arm in ARMS}
    tiktoken_ready = False
    enc = None
    if _HAS_TIKTOKEN:
        try:
            import tiktoken as _tk
            enc = _tk.get_encoding("cl100k_base")
            tiktoken_ready = True
        except Exception:
            tiktoken_ready = False

    if tiktoken_ready:
        from benchmark.formatters.chart_context import render_reasoned_context
        from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt
        # All 80 unique cases across both year datasets
        all_cases = []
        for year in YEARS:
            all_cases.extend(load_jsonl(YEAR_DATASETS[year]))
        arm_ziwei = {a: ARM_ZIWEI_MAP[a] for a in ARMS}
        for arm in ARMS:
            za = arm_ziwei[arm]
            for case in all_cases:
                ctx = render_reasoned_context(case, CHART_SCHEMA, za)
                prompt = _assemble_reasoned_choice_prompt(case, ctx)
                arm_tiktoken_counts[arm].append(len(enc.encode(prompt)))

    # Phase 3: per-arm source selection
    for arm in ARMS:
        inp_list = arm_usage[arm]["input"]
        out_list = arm_usage[arm]["output"]
        if inp_list:
            avg_in = round(sum(inp_list) / len(inp_list), 1)
            avg_out = round(sum(out_list) / len(out_list), 1) if out_list else None
            if avg_out is not None:
                avg_total = round(avg_in + avg_out, 1)
            else:
                avg_total = NOT_AVAILABLE
            stats[arm] = {
                "avg_input": avg_in,
                "avg_output": avg_out if avg_out is not None else NOT_AVAILABLE,
                "avg_total": avg_total,
                "source": "provider",
                "n": len(inp_list),
            }
        elif tiktoken_ready and arm_tiktoken_counts[arm]:
            counts = arm_tiktoken_counts[arm]
            avg_in = round(sum(counts) / len(counts), 1)
            stats[arm] = {
                "avg_input": avg_in,
                "avg_output": NOT_AVAILABLE,
                "avg_total": NOT_AVAILABLE,
                "source": "tiktoken",
                "n": len(counts),
            }
        else:
            stats[arm] = {
                "avg_input": NOT_AVAILABLE,
                "avg_output": NOT_AVAILABLE,
                "avg_total": NOT_AVAILABLE,
                "source": NOT_AVAILABLE,
                "n": 0,
            }
    return stats


def generate_report(schedule: dict, table: dict, output_dir: Path,
                    ledger: BudgetLedger) -> str:
    """Generate descriptive Markdown comparison report (plan §4.12).

    全描述性, 不含"显著"、"确认"等词. 写入 output_dir/report.md.
    """
    arm_label = {
        "b1a_prime": "b1a_prime (none)",
        "b1b": "b1b (only)",
        "b1c": "b1c (combined)",
        "b2b": "b2b (ziwei_mini)",
        "b2c": "b2c (sequential)",
    }

    lines = []
    lines.append("# Phase 6 6B1-D Comparison Report")
    lines.append("")
    lines.append(f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Experiment**: {table['experiment']}")
    lines.append("")
    lines.append("> 全描述性分析, 仅报告观察到的差异与区间, 不作统计推断. "
                 "Bootstrap CI 基于 year×question 聚类"
                 f" (seed={table['bootstrap']['seed']}, "
                 f"{table['bootstrap']['draws']} draws).")
    lines.append("")

    lines.append("## Five-Arm Accuracy (sorted)")
    lines.append("")
    lines.append("| Rank | Arm | Accuracy | 95% CI | Records | Clusters |")
    lines.append("|------|-----|----------|--------|---------|----------|")
    for rank, arm in enumerate(table["ranking"], 1):
        s = table["arm_stats"][arm]
        lines.append(
            f"| {rank} | {arm_label.get(arm, arm)} | {s['accuracy']:.2%} | "
            f"[{s['ci_low']:.2%}, {s['ci_high']:.2%}] | "
            f"{s['n_records']} | {s['n_clusters']} |"
        )
    lines.append("")

    lines.append("## Pairwise Differences (arm_a − arm_b)")
    lines.append("")
    lines.append("| Arm A | Arm B | Diff | 95% CI |")
    lines.append("|-------|-------|------|--------|")
    for d in table["pairwise_diffs"]:
        lines.append(
            f"| {arm_label.get(d['arm_a'], d['arm_a'])} | "
            f"{arm_label.get(d['arm_b'], d['arm_b'])} | "
            f"{d['diff']:+.2%} | [{d['ci_low']:+.2%}, {d['ci_high']:+.2%}] |"
        )
    lines.append("")

    lines.append("## Token Statistics (descriptive, plan §4.9)")
    lines.append("")
    token_stats = table.get("token_stats", {})
    tiktoken_avail = table.get("tiktoken_available", False)
    lines.append(f"- tiktoken available: {tiktoken_avail}")
    if token_stats:
        lines.append("")
        lines.append("| Arm | Avg Input | Avg Output | Avg Total | Source | N |")
        lines.append("|-----|-----------|------------|-----------|--------|---|")
        for arm in ARMS:
            ts = token_stats.get(arm, {})
            lines.append(
                f"| {arm_label.get(arm, arm)} | "
                f"{ts.get('avg_input', 'N/A')} | "
                f"{ts.get('avg_output', 'N/A')} | "
                f"{ts.get('avg_total', 'N/A')} | "
                f"{ts.get('source', 'N/A')} | "
                f"{ts.get('n', 0)} |"
            )
    lines.append("")

    lines.append("## Integrity")
    lines.append("")
    lines.append(f"- Total slices: {schedule['total_slices']}")
    lines.append(f"- Slices completed: {len(ledger._data['slices_completed'])}")
    lines.append(f"- Total calls attempted: {ledger.total_attempted} "
                 f"/ {ledger.hard_cap}")
    lines.append(f"- numpy available for bootstrap: {table['bootstrap']['numpy_available']}")
    lines.append("")

    lines.append("## Schedule")
    lines.append("")
    lines.append(f"- Arms: {', '.join(table['arms'])}")
    lines.append(f"- Years: {', '.join(YEARS)}")
    lines.append(f"- Repeats: {len(REPEATS)}")
    lines.append(f"- Total scheduled calls: {schedule['total_scheduled_calls']}")
    lines.append("")

    report = "\n".join(lines)

    # Fail-closed: plan §4.12 requires purely descriptive wording. Reject any
    # report that contains a forbidden substring (catches e.g. "显著性").
    found = [w for w in FORBIDDEN_WORDS if w in report]
    if found:
        print(json.dumps({"status": "BLOCKED_REPORT_FORBIDDEN_WORD",
            "words": found,
            "reason": "报告含禁用词, 违反纯描述性要求"}, ensure_ascii=False))
        raise SystemExit(2)

    report_path = output_dir / "report.md"
    with open(str(report_path), "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[report] -> {report_path}")
    return str(report_path)


# ---- formal archive generation (P0 #3d/e) ----

def _crash_audit_prefix(sl: dict) -> str:
    """Crash audit file prefix for per-slice crash_retry.* artifacts."""
    return os.path.join(sl["output_dir"], "crash_retry")


def _compute_dataset_hashes() -> dict:
    """SHA-256 of each enriched dataset."""
    hashes = {}
    for year, path in YEAR_DATASETS.items():
        if os.path.exists(path):
            with open(path, "rb") as f:
                hashes[year] = hashlib.sha256(f.read()).hexdigest()
    return hashes


def _compute_context_fingerprint(schedule: dict, provider: str, model: str) -> dict:
    """SHA-256 of rendered context for 3 cases × 5 arms = 15 fingerprints."""
    from benchmark.formatters.chart_context import render_reasoned_context
    from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt

    arms_seen = {}
    case_ids_used = []
    first_sl = schedule["slices"][0]
    cases = load_jsonl(first_sl["dataset"])
    selected_cases = cases[:3]
    for case in selected_cases:
        case_ids_used.append(case.get("case_id", "unknown"))
    fingerprints = {}
    for sl in schedule["slices"]:
        arm = sl["arm"]
        if arm in arms_seen:
            continue
        arms_seen[arm] = True
        for i, case in enumerate(selected_cases):
            ctx = render_reasoned_context(case, CHART_SCHEMA, sl["ziwei_arm"])
            prompt = _assemble_reasoned_choice_prompt(case, ctx)
            key = f"{case.get('case_id', f'case{i}')}_{arm}"
            fingerprints[key] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return {
        "case_ids": case_ids_used,
        "arms": list(arms_seen.keys()),
        "fingerprints": fingerprints,
        "total": len(fingerprints),
    }


def _copy_slice_artifacts(sl: dict, dest_dir: Path) -> dict:
    """Copy per-slice evidence (details/manifest/events/crash_retry.*) to archive.
    Returns file hashes for audit_index."""
    import shutil
    hashes = {}
    src_map = {
        "details.jsonl": sl["detail_path"],
        "details.manifest.json": sl["manifest_path"],
        "details.events.jsonl": sl["events_path"],
    }
    for name, src in src_map.items():
        if os.path.exists(src):
            dst = dest_dir / name
            shutil.copy2(src, str(dst))
            with open(dst, "rb") as f:
                hashes[name] = hashlib.sha256(f.read()).hexdigest()
    prefix = _crash_audit_prefix(sl)
    for suffix in (".returncode", ".stdout.log", ".stderr.log",
                   ".retry.returncode", ".retry.stdout.log", ".retry.stderr.log"):
        src = f"{prefix}{suffix}"
        if os.path.exists(src):
            dst_name = f"crash_retry{suffix}"
            dst = dest_dir / dst_name
            shutil.copy2(src, str(dst))
            with open(dst, "rb") as f:
                hashes[dst_name] = hashlib.sha256(f.read()).hexdigest()
    return hashes


def _merge_artifacts(schedule: dict, archive_dir: Path,
                     provider: str, model: str) -> dict:
    """Merge all 150 slice details + events into merged_details/events.jsonl.
    Per-slice validation: manifest, row count, attempt keys, call count.
    Does NOT enforce parser rate (that's smoke-only)."""
    if not provider or not model:
        raise ValueError("provider and model are mandatory for _merge_artifacts")

    merged_details = archive_dir / "merged_details.jsonl"
    merged_events = archive_dir / "merged_events.jsonl"
    detail_count = 0
    event_count = 0
    expected_details = schedule["total_scheduled_calls"]

    missing = []
    for sl in schedule["slices"]:
        if not os.path.exists(sl["detail_path"]):
            missing.append(f"{sl['slice_id']}/details.jsonl")
        if not os.path.exists(sl["events_path"]):
            missing.append(f"{sl['slice_id']}/details.events.jsonl")
        if not os.path.exists(sl["manifest_path"]):
            missing.append(f"{sl['slice_id']}/details.manifest.json")
    if missing:
        print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
            "reason": f"{len(missing)} 个必需文件缺失，禁止合并",
            "missing_sample": missing[:5]}, ensure_ascii=False))
        raise SystemExit(2)

    per_slice_report = []
    for sl in schedule["slices"]:
        ok, diff = verify_slice_manifest(sl, provider, model)
        if not ok:
            print(json.dumps({"status": "ARCHIVE_MANIFEST_DRIFT",
                "slice_id": sl["slice_id"], "diff": diff}, ensure_ascii=False))
            raise SystemExit(2)
        rows = load_jsonl(sl["detail_path"])
        if len(rows) != sl["size"]:
            print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
                "slice_id": sl["slice_id"],
                "reason": f"detail rows {len(rows)} != scheduled {sl['size']}"},
                ensure_ascii=False))
            raise SystemExit(2)
        detail_keys = [tuple(r.get("attempt_key", [])) for r in rows]
        dataset_id = os.path.splitext(os.path.basename(sl["dataset"]))[0]
        expected_keys = set()
        for case_id in sl["case_ids"]:
            expected_keys.add(build_expected_key(
                dataset_id, REASONED_PROFILE, sl["arm"],
                case_id, sl["repeat"], provider, model))
        if len(set(detail_keys)) != len(detail_keys):
            print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
                "slice_id": sl["slice_id"], "reason": "duplicate attempt keys"},
                ensure_ascii=False))
            raise SystemExit(2)
        extra = set(detail_keys) - expected_keys
        if extra:
            print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
                "slice_id": sl["slice_id"], "reason": "extra attempt keys",
                "extra_sample": list(extra)[:3]}, ensure_ascii=False))
            raise SystemExit(2)
        ev_rows = load_jsonl(sl["events_path"])
        call_count = sum(1 for r in ev_rows if r.get("kind") == "call_attempt")
        if call_count < sl["size"] or call_count > sl["hard_cap"]:
            print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
                "slice_id": sl["slice_id"],
                "reason": f"call_attempt {call_count} not in [{sl['size']}, {sl['hard_cap']}]"},
                ensure_ascii=False))
            raise SystemExit(2)
        per_slice_report.append({"slice_id": sl["slice_id"],
                                  "detail_rows": len(rows),
                                  "call_attempts": call_count})

    with open(merged_details, "w", encoding="utf-8") as df, \
         open(merged_events, "w", encoding="utf-8") as ef:
        for sl in schedule["slices"]:
            for src in (sl["detail_path"], sl["events_path"]):
                with open(src, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if src == sl["detail_path"]:
                            df.write(line + "\n")
                            detail_count += 1
                        else:
                            ef.write(line + "\n")
                            event_count += 1

    if detail_count != expected_details:
        print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
            "reason": f"merged detail rows {detail_count} != expected {expected_details}"},
            ensure_ascii=False))
        raise SystemExit(2)

    return {"detail_rows": detail_count, "event_rows": event_count,
            "expected_detail_rows": expected_details,
            "per_slice": per_slice_report}


def generate_archive(schedule: dict, ledger: BudgetLedger,
                     output_dir: Path, provider: str, model: str,
                     labels_sha256: str | None = None,
                     labels_data: list | None = None,
                     archive_root: Path | None = None) -> str:
    """Generate v9 §12 formal archive for 6B1-D.

    - Five smoke archive directories (smoke_<arm>/)
    - All non-smoke slices in slices/<id>/
    - audit_index.json with artifact hashes, labels, distribution
    - Atomic publish via temp dir
    - Independent run ID: 6b1d-<date>-<provider>-<model>-<code_hash>
    """
    import shutil
    import tempfile

    if archive_root is None:
        archive_root = Path(ARCHIVE_ROOT)
    archive_root = Path(archive_root)

    code_hash = _compute_experiment_code_fingerprint()
    run_id = f"{EXPERIMENT_ID_PREFIX}-{FROZEN_DATE}-{provider}-{model}-{code_hash}"
    archive_dir = archive_root / run_id

    if archive_dir.exists():
        print(json.dumps({"status": "ARCHIVE_ALREADY_EXISTS",
            "archive_dir": str(archive_dir),
            "reason": "归档目录已存在，拒绝覆盖"}, ensure_ascii=False))
        raise SystemExit(2)

    parent = archive_root
    parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}_", dir=str(parent)))
    try:
        # Five smoke directories
        smoke_hashes = {}
        for sl in schedule["slices"][:5]:
            smoke_dir = tmp_dir / f"smoke_{sl['arm']}"
            smoke_dir.mkdir(exist_ok=True)
            smoke_hashes[sl["arm"]] = _copy_slice_artifacts(sl, smoke_dir)

        # Non-smoke slices
        slices_dir = tmp_dir / "slices"
        slices_dir.mkdir(exist_ok=True)
        slice_hashes = {}
        for sl in schedule["slices"][5:]:
            sl_dir = slices_dir / sl["slice_id"]
            sl_dir.mkdir(exist_ok=True)
            slice_hashes[sl["slice_id"]] = _copy_slice_artifacts(sl, sl_dir)

        # Merged artifacts
        merge_counts = _merge_artifacts(schedule, tmp_dir, provider, model)

        # Label distribution
        label_dist = compute_label_distribution(labels_data) if labels_data else {}
        skipped = get_skipped_layers(labels_data) if labels_data else []

        # audit_index.json
        audit_index = {
            "run_id": run_id,
            "experiment_id": EXPERIMENT_ID_PREFIX,
            "frozen_date": FROZEN_DATE,
            "provider": provider,
            "model": model,
            "code_fingerprint": code_hash,
            "fingerprint_scope": list(FINGERPRINT_SCOPE),
            "labels_sha256": labels_sha256,
            "label_distribution": label_dist,
            "skipped_layers": skipped,
            "dataset_hashes": _compute_dataset_hashes(),
            "context_fingerprints": _compute_context_fingerprint(schedule, provider, model),
            "schedule_total_slices": schedule["total_slices"],
            "schedule_total_scheduled_calls": schedule["total_scheduled_calls"],
            "schedule_total_hard_cap": schedule["total_hard_cap"],
            "latin_square": {str(k): v for k, v in LATIN_SQUARE.items()},
            "slice_layout": SLICE_LAYOUT,
            "budget_total_calls": ledger.total_attempted,
            "budget_hard_cap": ledger.hard_cap,
            "merge_counts": merge_counts,
            "smoke_artifact_hashes": smoke_hashes,
            "slice_artifact_hashes": slice_hashes,
            "generated_at": time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        atomic_write_json(str(tmp_dir / "audit_index.json"), audit_index)

        # Copy schedule + budget ledger
        shutil.copy2(str(output_dir / "schedule.json"), str(tmp_dir / "schedule.json"))
        shutil.copy2(str(output_dir / "run_manifest.json"),
                     str(tmp_dir / "run_manifest.json"))
        ledger_src = output_dir / "budget_ledger.json"
        if not ledger_src.exists():
            print(json.dumps({"status": "ARCHIVE_INTEGRITY_FAILED",
                "reason": "budget_ledger.json 缺失"}, ensure_ascii=False))
            raise SystemExit(2)
        budget_dir = tmp_dir / "budget"
        budget_dir.mkdir(exist_ok=True)
        shutil.copy2(str(ledger_src), str(budget_dir / f"{run_id}.json"))

        # Copy labels.jsonl
        labels_src = output_dir / "labels.jsonl"
        if labels_src.exists():
            shutil.copy2(str(labels_src), str(tmp_dir / "labels.jsonl"))

        generate_report(schedule, generate_comparison_table(
            schedule, ledger, provider, model), tmp_dir, ledger)

        try:
            os.rename(str(tmp_dir), str(archive_dir))
        except (FileExistsError, PermissionError, OSError) as e:
            print(json.dumps({"status": "ARCHIVE_RACE_DETECTED",
                "archive_dir": str(archive_dir), "error": str(e)},
                ensure_ascii=False))
            raise SystemExit(2)
    except BaseException:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
        raise
    return str(archive_dir)


def _write_case_ids_file(sl: dict) -> str:
    """Write case_ids JSON file for runner --case-ids-file."""
    case_ids_file = os.path.join(sl["output_dir"], f"case_ids_{sl['slice_id']}.json")
    os.makedirs(sl["output_dir"], exist_ok=True)
    with open(case_ids_file, "w", encoding="utf-8") as f:
        json.dump(sl["case_ids"], f, ensure_ascii=False)
    return case_ids_file


def _build_runner_cmd(sl: dict, args, resume: bool = False) -> list:
    """Build runner subprocess command for a slice."""
    cmd = [
        sys.executable, "-m", "benchmark.runners.run_benchmark",
        "--profile", REASONED_PROFILE,
        "--chart-schema-version", sl.get("chart_schema_version", CHART_SCHEMA),
        "--arm", sl["arm"],
        "--ziwei-arm", sl["ziwei_arm"],
        "--attempt-stage", "main",
        "--repeat-idx", str(sl["repeat"]),
        "--case-details-jsonl", sl["detail_path"],
        "--case-ids-file", _write_case_ids_file(sl),
        "--dataset", sl["dataset"],
        "--provider", args.provider,
        "--model", args.model,
        "--method", "direct_choice",
        "--model-runner",
        "--n-samples", "1",
        "--temperature", "0",
        "--scheduled-calls", str(sl["size"]),
        "--hard-cap", str(sl["hard_cap"]),
        "--output-dir", sl["output_dir"],
        "--as-of-date", FROZEN_DATE,
    ]
    if resume:
        cmd.append("--resume")
    return cmd


def _run_slice(sl: dict, args, ledger: BudgetLedger,
               resume: bool = False) -> int:
    """Run a single slice via runner subprocess.

    Returns: 0=success, 2=config error, 3=budget exhausted, other=crash.
    """
    cmd = _build_runner_cmd(sl, args, resume=resume)

    clean_env = dict(os.environ)
    for var in ENV_CLEANUP:
        clean_env.pop(var, None)

    result = subprocess.run(cmd, capture_output=False, text=True, env=clean_env)

    calls_attempted = _count_call_attempts(sl["events_path"])

    if result.returncode == 0:
        ledger.record_slice_completed(sl["slice_id"], calls_attempted)
    else:
        ledger.record_calls_only(sl["slice_id"], calls_attempted)

    return result.returncode


def _process_slice(sl: dict, idx: int, total: int, args,
                   ledger: BudgetLedger, is_smoke: bool = True) -> int:
    """统一处理单个 slice (smoke 或 main).
    is_smoke=True: smoke gate, 要求 100% parser rate.
    is_smoke=False: main slice, 不要求全部 parsed.
    返回: 0=跳过(已完成), 1=成功执行, 2=失败, 3=budget exhausted.
    """
    state = _resolve_slice_state(sl)
    print(f"[slice] {idx}/{total} {sl['slice_id']}: state={state}")

    if state == "blocked_corrupt":
        print(json.dumps({"status": "BLOCKED_SLICE_CORRUPT",
            "slice_id": sl["slice_id"],
            "reason": "产物损坏，fail-closed"}, ensure_ascii=False))
        return 2

    if state == "completed":
        if not _verify_slice_completed(sl, args, ledger, is_smoke=is_smoke):
            return 2
        print(f"[slice] {sl['slice_id']}: PASS (completed, verified)")
        return 0

    # Budget pre-check
    if not ledger.budget_ok_for_slice(sl["slice_id"], sl["hard_cap"]):
        print(json.dumps({"status": "BUDGET_EXHAUSTED",
            "slice_id": sl["slice_id"],
            "total_attempted": ledger.total_attempted,
            "reason": "全局预算耗尽"}, ensure_ascii=False))
        return 3

    # fresh or resume: allocate cap
    allocated_cap = ledger._data["allocated_cap_by_slice"].get(sl["slice_id"])
    if allocated_cap is None:
        effective_cap = compute_effective_cap(sl["slice_id"], ledger, 0)
    else:
        already = reconcile_partial_events(sl, ledger, allocated_cap)
        effective_cap = compute_effective_cap(sl["slice_id"], ledger, already)

    sl["hard_cap"] = effective_cap

    rc = _run_slice(sl, args, ledger, resume=(state == "resume"))

    if rc == 2:
        print(json.dumps({"status": "BLOCKED_RUNNER_CONFIG",
            "slice_id": sl["slice_id"], "returncode": 2,
            "reason": "确定性错误"}, ensure_ascii=False))
        return 2
    if rc == 3:
        print(json.dumps({"status": "BLOCKED_INCOMPLETE",
            "slice_id": sl["slice_id"], "returncode": 3,
            "reason": "hard cap 耗尽"}, ensure_ascii=False))
        return 3
    if rc != 0:
        print(json.dumps({"status": "BLOCKED_SLICE_CRASH",
            "slice_id": sl["slice_id"], "returncode": rc,
            "reason": "子进程崩溃"}, ensure_ascii=False))
        return 2

    # Verify slice completed successfully
    if not _verify_slice_completed(sl, args, ledger, is_smoke=is_smoke):
        return 2
    print(f"[slice] {sl['slice_id']}: PASS")
    return 1


def main(argv=None):
    """Main entry point for 6B1-D orchestrator.

    5 arms × 5 groups × 2 years × 3 repeats = 150 slices.
    正式 schedule 的前 5 个 slice (position=0, 2024, repeat=0, G0-G4) 即五臂 smoke.
    主循环处理 slices[5:].
    Dynamic effective_cap, BudgetLedger.allocated_cap_by_slice 权威.
    """
    parser = argparse.ArgumentParser(description="Phase 6 6B1-D orchestrator")
    parser.add_argument("--provider", default="deepseek", help="模型 provider")
    parser.add_argument("--model", default="deepseek-v4-pro",
                        help="模型名 (DeepSeek API 现仅接受 deepseek-v4-pro / deepseek-v4-flash)")
    parser.add_argument("--output-dir", default="benchmark/outputs/phase6_6b1d",
                        help="产物输出根目录")
    parser.add_argument("--dry-run", action="store_true", help="仅生成 schedule，不调 API")
    parser.add_argument("--from-slice", type=int, default=0,
                        help="从指定 slice 索引开始（0-149，跳过需审计已完成）")
    parser.add_argument("--labels-file", default=None,
                        help="labels.jsonl 路径（默认 docs/phase6/6b1d/labels.jsonl）")
    parser.add_argument("--archive-root", default=None,
                        help="归档根目录（默认 docs/phase6/6b1d）")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    os.makedirs(str(output_dir), exist_ok=True)

    # 0. P0: output-dir 独占锁。在任何产物读写（含 dry-run 的 schedule.json）之前
    #    原子获取；第二个 orchestrator 必须 fail-closed，防止并发写入导致每 case
    #    双调用、detail 重复、verify 竞态、ledger 超 hard_cap（r2 事故根因）。
    #    锁释放依赖 atexit（覆盖 return / SystemExit / 未捕获异常）+ stale 检测
    #    （兜底 SIGKILL/崩溃残留）。main 的所有 return 路径都会触发 atexit。
    _main_lock = OutputDirLock.acquire(str(output_dir))
    if _main_lock is None:
        print(json.dumps({"status": "BLOCKED_OUTPUT_DIR_LOCKED",
            "output_dir": str(output_dir),
            "reason": "output-dir 已被其他 orchestrator 持有锁，拒绝并发写入 (fail-closed)"},
            ensure_ascii=False))
        return 2

    # 1. Dry-run: generate (write) schedule, print summary, exit.
    #    Dry-run does not make model calls or touch the run manifest, so the
    #    resume/fresh protection below does not apply to it.
    if args.dry_run:
        schedule = generate_schedule(output_dir)
        if schedule["total_scheduled_calls"] != TOTAL_SCHEDULED_CALLS:
            print(f"ERROR: expected {TOTAL_SCHEDULED_CALLS} scheduled calls, "
                  f"got {schedule['total_scheduled_calls']}")
            raise SystemExit(1)
        if schedule["total_slices"] != TOTAL_SLICES:
            print(f"ERROR: expected {TOTAL_SLICES} slices, got {schedule['total_slices']}")
            raise SystemExit(1)
        print(f"\n[dry-run] schedule OK: {schedule['total_slices']} slices, "
              f"{schedule['total_scheduled_calls']} calls "
              f"(hard_cap total={schedule['total_hard_cap']})")
        print(f"[dry-run] arms: {ARMS}")
        print(f"[dry-run] years: {YEARS}")
        print(f"[dry-run] repeats: {REPEATS}")
        print(f"[dry-run] global hard cap: {GLOBAL_LEDGER_CAP}")
        print(f"[dry-run] smoke = schedule[0:5] (position=0, 2024, R0, G0-G4)")
        print("[dry-run] Exiting without API calls.")
        return 0

    # 2. Labels preflight (before any model calls / schedule write)
    labels_path = args.labels_file or LABELS_DEFAULT_PATH
    ok, labels_sha256, labels_data, reason = validate_labels(labels_path)
    if not ok:
        print(json.dumps({"status": "BLOCKED_LABELS_PREFLIGHT",
            "labels_path": labels_path, "reason": reason},
            ensure_ascii=False))
        return 2

    dist = compute_label_distribution(labels_data)
    skipped = get_skipped_layers(labels_data)
    print(f"[labels] {len(labels_data)} cases validated, SHA-256={labels_sha256[:12]}...")
    for dim in LABEL_DIMENSIONS:
        print(f"[labels] {dim}: {dist[dim]}")
    if skipped:
        print(f"[labels] layers with <{LABEL_MIN_LAYER_SIZE} samples (will skip): {skipped}")

    # 3. Resume/fresh detection BEFORE writing schedule (P0 #1).
    #    历史产物存在但 run_manifest 缺失 -> fail-closed (无法验证旧结果来源).
    #    run_manifest 存在 -> 先校验指纹/配置漂移, 再读取历史 schedule.
    run_manifest_path = output_dir / "run_manifest.json"
    has_manifest = run_manifest_path.exists()
    has_artifacts = _has_historical_artifacts(output_dir)

    if has_artifacts and not has_manifest:
        print(json.dumps({"status": "BLOCKED_ARTIFACTS_WITHOUT_MANIFEST",
            "output_dir": str(output_dir),
            "reason": "output_dir 含历史产物但 run_manifest.json 缺失，无法验证来源 (fail-closed)"},
            ensure_ascii=False))
        return 2

    historical_schedule = None
    if has_manifest:
        ok, reason = verify_run_manifest(output_dir, args.provider, args.model,
                                         labels_sha256)
        if not ok:
            print(json.dumps({"status": "BLOCKED_RUN_MANIFEST_DRIFT",
                "reason": reason,
                "hint": "实验代码或配置已变更，历史产物与当前不兼容"}, ensure_ascii=False))
            return 2
        # Read historical schedule (never overwritten on the resume path).
        historical_schedule = _load_schedule_json(output_dir)

    # 4. Obtain the schedule. Resume compares an in-memory candidate against the
    #    historical schedule BEFORE any write, so a drift rejection leaves the
    #    on-disk schedule.json byte-identical. Fresh runs build+persist a new
    #    schedule and commit the run manifest.
    if has_manifest:
        candidate = _build_schedule(output_dir)
        ok, reason = _verify_schedule_consistent(historical_schedule, candidate)
        if not ok:
            print(json.dumps({"status": "BLOCKED_SCHEDULE_DRIFT",
                "reason": reason,
                "hint": "历史 schedule 与当前代码生成的不一致"}, ensure_ascii=False))
            return 2
        # Consistent: reuse the historical on-disk schedule (no overwrite).
        schedule = historical_schedule
    else:
        schedule = generate_schedule(output_dir)
        write_run_manifest(output_dir, args.provider, args.model, labels_sha256)

    if schedule["total_scheduled_calls"] != TOTAL_SCHEDULED_CALLS:
        print(f"ERROR: expected {TOTAL_SCHEDULED_CALLS} scheduled calls, "
              f"got {schedule['total_scheduled_calls']}")
        raise SystemExit(1)
    if schedule["total_slices"] != TOTAL_SLICES:
        print(f"ERROR: expected {TOTAL_SLICES} slices, got {schedule['total_slices']}")
        raise SystemExit(1)

    ledger_path = str(output_dir / "budget_ledger.json")
    ledger = BudgetLedger(ledger_path)

    # 6. Validate ledger against schedule
    ledger.validate_against_schedule(schedule, args.provider, args.model)

    # 4. Smoke gate - schedule[0:5] 即五臂 smoke
    print("\n=== SMOKE GATE (schedule[0:5], one arm per slice) ===")
    smoke_slices = schedule["slices"][:5]

    for idx, sl in enumerate(smoke_slices):
        result = _process_slice(sl, idx, TOTAL_SLICES, args, ledger,
                                is_smoke=True)
        if result == 2:
            return 2
        if result == 3:
            # smoke budget exhausted -> fatal
            return 2
        # result 0 (completed) or 1 (ran successfully) -> continue

    print("[smoke] All 5 smoke slices passed.")

    # 5. --from-slice audit: 被跳过的 slice 必须全部 completed
    if args.from_slice > 5:
        print(f"\n=== FROM-SLICE AUDIT (slices 5..{args.from_slice-1}) ===")
        if not _audit_skipped_slices(schedule, args.from_slice, args, ledger):
            return 2

    # 6. Main loop - slices[5:]
    print(f"\n=== MAIN LOOP (slices 5..{TOTAL_SLICES-1}) ===")
    for idx in range(5, TOTAL_SLICES):
        if idx < args.from_slice:
            continue

        sl = schedule["slices"][idx]
        result = _process_slice(sl, idx, TOTAL_SLICES, args, ledger,
                                is_smoke=False)

        if result == 2:
            return 2
        if result == 3:
            # main slice budget exhausted -> fatal (不能继续)
            print(json.dumps({"status": "BLOCKED_BUDGET_EXHAUSTED",
                "total_attempted": ledger.total_attempted,
                "reason": "预算耗尽，实验不完整"}, ensure_ascii=False))
            return 2
        # result 0 (completed) or 1 (ran successfully) -> continue

    # 7. Integrity gate - 阻止不完整实验返回 0
    print("\n=== INTEGRITY GATE ===")
    ok, reason = _integrity_gate(schedule, ledger, args)
    if not ok:
        print(json.dumps({"status": "BLOCKED_INTEGRITY",
            "reason": reason,
            "total_attempted": ledger.total_attempted}, ensure_ascii=False))
        return 2

    # 8. Descriptive comparison table + report (plan §4.12)
    print("\n=== COMPARISON TABLE ===")
    table = generate_comparison_table(schedule, ledger, args.provider, args.model)
    table_path = output_dir / "comparison_table.json"
    atomic_write_json(str(table_path), table)
    print(f"[comparison] -> {table_path}")
    generate_report(schedule, table, output_dir, ledger)

    # 9. Copy labels.jsonl to output_dir for archive
    import shutil
    labels_dest = output_dir / "labels.jsonl"
    if labels_path != str(labels_dest):
        shutil.copy2(labels_path, str(labels_dest))

    # 10. Formal archive (P0 #3d/e)
    print("\n=== ARCHIVE ===")
    archive_root = Path(args.archive_root) if args.archive_root else None
    archive_path = generate_archive(
        schedule, ledger, output_dir, args.provider, args.model,
        labels_sha256=labels_sha256, labels_data=labels_data,
        archive_root=archive_root)
    print(f"[archive] -> {archive_path}")

    print(f"\n=== COMPLETE: {ledger.total_attempted}/{ledger.hard_cap} calls, "
          f"{len(ledger._data['slices_completed'])} slices ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
