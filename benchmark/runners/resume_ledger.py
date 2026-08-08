"""Phase 6 resume / ledger subsystem（自 run_benchmark.py 拆出，降低单文件内聚边界）。

内容：attempt key / 终态枚举、重试与预算账本恢复函数、代码指纹与 _CODE_SCOPE、
resume manifest 构建/校验（设计 §4.3/§4.4，L168）。

run_benchmark.py 保持对这些符号的重导出，外部 `from benchmark.runners.run_benchmark
import ...` 的既有导入路径不变。本文件承载实验 resume 门禁逻辑，已纳入 _CODE_SCOPE：
改动本文件会产生 code_sha256 漂移，resume manifest 会拒绝跨改动续跑。
"""
import hashlib
import json
import os
import sys

if __package__ in (None, ''):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


# ---- Phase 6：attempt key / 终态 / 重试与预算账本（设计 §4.3/§4.4）----

ATTEMPT_KEY_FIELDS: tuple = (
    "dataset_id", "profile_id", "arm", "attempt_stage", "provider", "model",
    "case_id", "repeat_idx", "sample_idx", "permutation_id",
)
ATTEMPT_STAGES = ("main", "bazi", "ziwei", "judge", "diversity_probe", "anchor")
TERMINAL_STATES = ("parsed", "invalid", "unresolved", "judge_unresolved", "call_failed")


def build_attempt_key(dataset_id, profile_id, arm, attempt_stage, provider, model,
                      case_id, repeat_idx, sample_idx, permutation_id):
    return (dataset_id, profile_id, arm, attempt_stage, provider, model,
            str(case_id), int(repeat_idx), int(sample_idx), permutation_id or "p0")


def compute_hard_cap(scheduled_calls: int) -> int:
    import math
    reserve = int(math.ceil(scheduled_calls * 0.10 / 10.0)) * 10
    return scheduled_calls + reserve


def load_completed_keys(detail_path) -> set:
    keys = set()
    if not detail_path or not os.path.exists(detail_path):
        return keys
    with open(detail_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            key = row.get("attempt_key")
            if key and row.get("terminal_state") in TERMINAL_STATES:
                keys.add(tuple(key))
    return keys


def load_retry_counts(events_path) -> dict:
    """只数网络/provider 失败事件（retry_idx 非 None），按 attempt_key 取 retry_idx 最大值。

    截断事件 (record_truncation 写入 retry_idx=None, error_type 以 truncated_response 开头)
    不计入网络重试预算，由 load_truncation_counts 单独恢复。
    """
    counts: dict = {}
    if not events_path or not os.path.exists(events_path):
        return counts
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") != "model_call_failed":
                continue
            if row.get("retry_idx") is None:
                continue   # 截断事件，走独立预算
            key = tuple(row["attempt_key"])
            counts[key] = max(counts.get(key, 0), int(row["retry_idx"]))
    return counts


def load_truncation_counts(events_path) -> dict:
    """数 finish_reason != 'stop' 截断事件（retry_idx is None），按 attempt_key 计数。

    与 load_retry_counts 互不干扰：网络失败 retry_idx 非 None，截断 retry_idx 为 None。
    """
    counts: dict = {}
    if not events_path or not os.path.exists(events_path):
        return counts
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") != "model_call_failed":
                continue
            if row.get("retry_idx") is not None:
                continue   # 网络失败事件，走 load_retry_counts
            key = tuple(row["attempt_key"])
            counts[key] = counts.get(key, 0) + 1
    return counts


def load_call_attempt_count(events_path) -> int:
    """数 kind=="call_attempt" 事件行数——calls_attempted 跨 resume 恢复的唯一依据。"""
    if not events_path or not os.path.exists(events_path):
        return 0
    n = 0
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            if json.loads(line).get("kind") == "call_attempt":
                n += 1
    return n


def resolve_method(profile_name, explicit_method):
    if profile_name:
        from benchmark.runners.profiles import derive_method, resolve_profile
        derived = derive_method(resolve_profile(profile_name))
        if explicit_method and explicit_method != derived:
            raise SystemExit(2)
        return derived
    return explicit_method or "direct_choice"


# ---- resume manifest（设计 L168：temperature/模板/代码/数据哈希不进 attempt key，由 manifest 约束）----

RESUME_MANIFEST_FIELDS: tuple = (
    "dataset_sha256", "case_ids_sha256", "profile_id", "chart_schema_version",
    "arm", "ziwei_arm", "attempt_stage", "repeat_idx", "provider", "model",
    "temperature", "sample_temperature", "n_samples", "aggregate", "method",
    "prompt_template_sha256", "code_sha256", "scheduled_calls", "hard_cap",
    "as_of_date",                              # v6 高优 7：enrichment 锚定日期
    "thinking_mode",                           # 6B2：显式 thinking 协议（None=未声明）
    "time_context_injection",                  # 6D：时间上下文注入开关（off/on）
    "temporal_routed_cases_sha256",            # 6D：冻结路由清单 SHA-256（None=未启用）
)

_CODE_SCOPE: tuple = (
    "benchmark/runners/run_benchmark.py",
    # resume/ledger 子系统拆出后仍属实验代码范围：其改动必须产生指纹漂移。
    "benchmark/runners/resume_ledger.py",
    "benchmark/runners/profiles.py",
    "benchmark/formatters/chart_context.py",
    "benchmark/formatters/bazi_time_context.py",
    "benchmark/formatters/baziqa_prompt.py",
    "benchmark/formatters/mingli_prompt.py",
    "benchmark/formatters/dual_system_reasoning.py",
    "benchmark/formatters/leak_scan.py",
    # 评审收口（6A0 CONDITIONAL_COMPLETE）：真实模型调用路径——provider 配置与
    # API 客户端改动必须产生 code_sha256 漂移，否则 resume manifest 无法拒绝。
    "config.py",
    "claude_api.py",
)


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_sha256(path: str) -> str:
    """Canonical SHA-256 of a JSON file (parse + sort_keys re-serialize)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _code_fingerprint() -> str:
    """实验范围代码 SHA-256：范围内文件 bytes 按序拼接；任一文件改动 → 指纹变化 → resume 拒绝。"""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    h = hashlib.sha256()
    for rel in _CODE_SCOPE:
        h.update(rel.encode())
        p = os.path.join(root, rel)
        h.update(open(p, "rb").read() if os.path.exists(p) else b"<missing>")
    return h.hexdigest()


def _atomic_write_json(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def build_resume_manifest(args, profile) -> dict:
    """当前运行的 manifest 字段全集；args.case_ids_file 为 None 时 case_ids_sha256 记 None
    （全集运行由 dataset_sha256 约束）。method 记录 resolve_method 后的生效值
    （接线顺序保证 resolve 先于本函数）；temperature 是 n_samples=1 时真正控制模型调用的
    温度（仓库 `--temperature` 默认 0.0），sample_temperature 仅 n_samples>1 生效仍记录。"""
    from benchmark.runners.profiles import prompt_fingerprint
    return {
        "dataset_sha256": _sha256_file(os.path.abspath(args.dataset)),
        "case_ids_sha256": (_sha256_file(os.path.abspath(args.case_ids_file))
                            if args.case_ids_file else None),
        "profile_id": profile.profile_id,
        "chart_schema_version": profile.chart_schema_version,
        "arm": args.arm or "default",
        "ziwei_arm": getattr(args, "ziwei_arm", None) or "default",
        "attempt_stage": getattr(args, "attempt_stage", "main"),
        "repeat_idx": args.repeat_idx,
        "provider": args.provider,
        "model": args.model,
        "temperature": args.temperature,
        "sample_temperature": args.sample_temperature,
        "n_samples": args.n_samples,
        "aggregate": args.aggregate,
        "method": args.method,
        "prompt_template_sha256": prompt_fingerprint(profile),
        "code_sha256": _code_fingerprint(),
        "scheduled_calls": args.scheduled_calls,
        "hard_cap": args.hard_cap,
        "as_of_date": getattr(args, "as_of_date", ""),       # v6 高优 7
        "thinking_mode": getattr(args, "thinking_mode", None),
        "time_context_injection": getattr(args, "time_context_injection", "off"),
        "temporal_routed_cases_sha256": (
            _canonical_json_sha256(args.temporal_routed_cases_file)
            if getattr(args, "temporal_routed_cases_file", None) else None),
    }


def check_resume_manifest(manifest_path: str, current: dict) -> None:
    """--resume 前置校验：字段完整性 + 逐字段完全匹配。缺失字段记 "<MISSING>" 进 diff
    （不得用 stored.get(k)——"字段缺失且 current 为 None"会误判相等放行）；任一不一致
    打印 diff 并 SystemExit(2)，禁止续跑。"""
    with open(manifest_path, "r", encoding="utf-8") as f:
        stored = json.load(f)
    diff = {}
    for k in RESUME_MANIFEST_FIELDS:
        if k not in stored:
            diff[k] = {"stored": "<MISSING>", "current": current.get(k)}
        elif stored[k] != current.get(k):
            diff[k] = {"stored": stored[k], "current": current.get(k)}
    if diff:
        print(json.dumps({"status": "MANIFEST_MISMATCH", "diff": diff}, ensure_ascii=False))
        raise SystemExit(2)


class _HardCapExhausted(Exception):
    """hard_cap 耗尽：非 RuntimeError，循环体的 except RuntimeError 不捕获，冒泡到 main。"""
