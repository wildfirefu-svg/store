import argparse
import hashlib
import json
import os
import sys
import time
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from benchmark.scorers.choice_accuracy import load_jsonl, score_choice_answers, extract_choice, extract_choice_with_meta
from benchmark.runners.shuffle_options import shuffle_options as _shuffle_options_fn, unshuffle_predicted_answer
from benchmark.runners.self_consistency import majority_vote, sample_answers
from benchmark.formatters.baziqa_prompt import (
    format_direct_choice_prompt,
    format_direct_c2_prompt,
    format_structured_reasoning_prompt,
    format_multi_turn_context,
    format_multi_turn_question,
)
from benchmark.formatters.two_stage_reasoning import (
    format_stage1_prompt,
    format_stage2_prompt,
    parse_stage1_result,
    build_stage2_evidence,
    is_time_location_question,
)
from benchmark.formatters.dual_system_reasoning import (
    build_bazi_pipeline_prompt, build_ziwei_pipeline_prompt,
    build_judge_prompt, extract_judge_answer, judge_swap_seed)
from benchmark.formatters.chart_context import extract_reasoned_choice_answer
from benchmark.scorers.evidence_score import score_case_evidence, aggregate_evidence_score
from benchmark.scorers.safety_score import score_safety, aggregate_safety_score
from benchmark.reports.generate_report import save_report
from benchmark.phase3 import to_original_option_identity, classify_parser_failure
import data_store


SYSTEM_PROMPT_BENCHMARK = (
    "你是一位专业命理师，擅长根据八字命盘进行分析。回答选择题时请直接给出选项字母。"
)


# ---- Phase 6：attempt key / 终态 / 重试与预算账本 / resume manifest（设计 §4.3/§4.4）----

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
)

_CODE_SCOPE: tuple = (
    "benchmark/runners/run_benchmark.py",
    "benchmark/runners/profiles.py",
    "benchmark/formatters/chart_context.py",
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


class Phase6Context:
    def __init__(self, dataset_id, profile_id, arm, attempt_stage, provider, model,
                 repeat_idx, detail_path, events_path, scheduled_calls, hard_cap, resume,
                 thinking_mode=None):
        self.dataset_id = dataset_id
        self.profile_id = profile_id
        self.arm = arm or "default"
        self.attempt_stage = attempt_stage
        self.provider = provider
        self.model = model
        self.thinking_mode = thinking_mode
        self.repeat_idx = int(repeat_idx or 0)
        self.detail_path = detail_path
        self.events_path = events_path
        self.scheduled_calls = scheduled_calls
        self.hard_cap = hard_cap
        # 事件即账本：成功/失败调用都有 call_attempt 事件，resume 时全量恢复计数
        self.calls_attempted = load_call_attempt_count(events_path) if resume else 0
        self.retry_counts = load_retry_counts(events_path) if resume else {}
        self.truncation_counts = load_truncation_counts(events_path) if resume else {}
        self._call_meta_cache: dict = {}   # run 内即时缓存，不跨 resume 恢复（meta 非预算）

    def attempt_key_for(self, case, sample_idx=0):
        return build_attempt_key(
            self.dataset_id, self.profile_id, self.arm, self.attempt_stage,
            self.provider, self.model, case.get("case_id"), self.repeat_idx,
            sample_idx, case.get("_permutation_id") or "p0",
        )

    def before_call(self, key):
        if self.hard_cap is not None and self.calls_attempted >= self.hard_cap:
            raise _HardCapExhausted(f"hard_cap {self.hard_cap} 耗尽")
        _append_jsonl(self.events_path, {
            "kind": "call_attempt", "attempt_key": list(key),
            "retry_idx": None, "error_type": None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        self.calls_attempted += 1   # 先写事件记账，再发起调用（含每次重试）

    def record_failure(self, key, exc):
        retry_idx = self.retry_counts.get(key, 0) + 1
        self.retry_counts[key] = retry_idx
        _append_jsonl(self.events_path, {
            "kind": "model_call_failed",
            "attempt_key": list(key), "retry_idx": retry_idx,
            "error_type": str(exc)[:120],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return retry_idx

    def record_truncation(self, key, meta):
        """记录一次 finish_reason != 'stop' 的截断，独立于网络重试预算（每键上限 1 次）。"""
        idx = self.truncation_counts.get(key, 0) + 1
        self.truncation_counts[key] = idx
        _append_jsonl(self.events_path, {
            "kind": "model_call_failed",
            "attempt_key": list(key), "retry_idx": None,
            "error_type": f"truncated_response: finish_reason={meta.get('finish_reason')}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return idx

    def record_call_meta(self, key, meta, truncated=False):
        """把单次调用的诊断 meta 记入 events，用于事后审计。"""
        row = {
            "kind": "call_meta",
            "attempt_key": list(key),
            "truncated": truncated,
            "finish_reason": meta.get("finish_reason"),
            "http_status": meta.get("http_status"),
            "latency_ms": meta.get("latency_ms"),
            "usage": meta.get("usage"),
            "response_id": meta.get("response_id"),
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "requested_model": meta.get("requested_model"),
            "response_model": meta.get("response_model"),
            "thinking_mode": meta.get("thinking_mode"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _append_jsonl(self.events_path, row)
        key_tuple = tuple(key)
        self._call_meta_cache[key_tuple] = row

    def get_last_call_meta(self, case, sample_idx=0):
        key = self.attempt_key_for(case, sample_idx=sample_idx)
        return self._call_meta_cache.get(tuple(key))

    def enrich_row(self, row):
        key = self.attempt_key_for({"case_id": row.get("case_id"),
                                    "_permutation_id": row.get("permutation_id")},
                                   sample_idx=int(row.get("sample_idx") or 0))
        row["attempt_key"] = list(key)
        if row.get("terminal_state") in TERMINAL_STATES:
            # 调用方已显式标记终态（如可见性门禁 unresolved）：保留不重算（执行偏离）
            pass
        elif row.get("error") or row.get("parser_failure_reason") == "model_call_failed":
            row["terminal_state"] = "call_failed"
        elif row.get("parser_valid") is False:
            row["terminal_state"] = "invalid"
        else:
            row["terminal_state"] = "parsed"
        row["raw_response_path"] = self.detail_path
        # 注入调用诊断元数据
        meta = self._call_meta_cache.get(tuple(key))
        if meta:
            row["finish_reason"] = meta.get("finish_reason")
            row["latency_ms"] = meta.get("latency_ms")
            row["response_id"] = meta.get("response_id")
            row["usage"] = meta.get("usage")
            row["requested_model"] = meta.get("requested_model")
            row["response_model"] = meta.get("response_model")
            row["thinking_mode"] = meta.get("thinking_mode")
        return row


_PHASE6_CTX: Phase6Context | None = None


def init_phase6_context(ctx: Phase6Context | None) -> None:
    global _PHASE6_CTX
    _PHASE6_CTX = ctx


def _mingli_data_ready() -> bool:
    return os.path.exists(os.path.join("data", "mingli", "data.json")) and \
        os.path.exists(os.path.join("data", "mingli", "fortune_api_results.json"))


def _attempt_with_ledger(case, call_once, sample_idx=0):
    """Phase 6 模型调用重试账本。

    两套独立预算：
      - 网络异常 / provider 异常：每键最多 3 次重试（4 次尝试），原策略不变。
      - finish_reason != 'stop' 截断：每键最多 1 次重试（截断 2 次后耗尽），窄重试。
    两种预算互不消耗；总调用受 hard_cap 限制。
    - ctx 为 None（非 profile 运行）：直接调用。
    - 崩溃类 RuntimeError（无 model_call_failed / truncated_response 前缀）-> 直接冒泡，不算重试。
    - before_call 先记账后调用（Policy A）。
    """
    ctx = _PHASE6_CTX
    if ctx is None:
        return call_once()
    key = ctx.attempt_key_for(case or {}, sample_idx=sample_idx)
    while True:
        if ctx.retry_counts.get(key, 0) >= 3:
            raise RuntimeError(f"model_call_failed: retry budget exhausted ({key[6]})")
        if ctx.truncation_counts.get(key, 0) >= 2:
            raise RuntimeError(f"model_call_failed: truncated_response budget exhausted ({key[6]})")
        ctx.before_call(key)
        try:
            result = call_once()
        except RuntimeError as exc:
            if not str(exc).startswith("model_call_failed") and \
               not str(exc).startswith("truncated_response"):
                raise   # 崩溃类 RuntimeError 直接冒泡，不算重试
            ctx.record_failure(key, exc)
            continue
        except Exception as exc:
            # 真实网络/provider 异常 → 计入重试账本
            ctx.record_failure(key, exc)
            continue
        # 调用成功：检查 finish_reason，非正常终止值才算截断（独立预算）
        # 正常终止值：OpenAI 系 stop；Anthropic 系 end_turn / stop_sequence / max_tokens(视为上限)。
        # 注：max_tokens 在 Anthropic 也表示触顶，但语义偏"已达上限"而非异常截断，
        # 与 DeepSeek 的 length（推理/token 耗尽）不同；本次实验用 DeepSeek，length 仍判截断。
        meta = result[1] if isinstance(result, (tuple, list)) and len(result) >= 2 else {}
        finish = meta.get("finish_reason") if isinstance(meta, dict) else None
        _NORMAL_FINISH_REASONS = {"stop", "end_turn", "stop_sequence"}
        if finish and finish not in _NORMAL_FINISH_REASONS:
            ctx.record_truncation(key, meta)
            ctx.record_call_meta(key, meta, truncated=True)
            continue
        # 正常完成：记录 meta 并返回文本
        if isinstance(meta, dict):
            ctx.record_call_meta(key, meta, truncated=False)
            # 6B2 协议审计：显式 non-thinking 运行拒绝响应模型漂移（大小写敏感精确
            # 匹配；抛于重试 try/except 之外，不消耗网络重试预算）
            response_model = meta.get("response_model")
            if ctx.thinking_mode == "disabled" and response_model and \
                    response_model != ctx.model:
                raise RuntimeError(
                    f"response_model_mismatch: {response_model} != {ctx.model}")
        if isinstance(result, (tuple, list)):
            return result[0]
        return result


def run_offline_benchmark(cases, predictions):
    return score_choice_answers(cases, predictions)


def build_benchmark_prompt(case, method='direct_choice', phase4_exp_a=False,
                           chart_schema_version=None, profile_formatter=None,
                           ziwei_arm=None):
    if profile_formatter == 'format_official_cot_prompt':
        # 裁决 2A（执行偏离）：官方 CoT 为单参签名，astro 取自
        # case["chart_input"]["official_astro"]，不再经 render_chart_context 两参传入。
        from benchmark.formatters.mingli_prompt import format_official_cot_prompt
        return format_official_cot_prompt(case)
    if profile_formatter == 'format_dual_system_prompt':
        return build_bazi_pipeline_prompt(case)
    if profile_formatter == 'format_reasoned_choice_prompt':
        from benchmark.formatters.chart_context import render_reasoned_context
        from benchmark.formatters.baziqa_prompt import _assemble_reasoned_choice_prompt
        if ziwei_arm is None:
            print(json.dumps({"status": "BLOCKED",
                "reason": "reasoned profile 要求显式 ziwei_arm (none/only/combined)，"
                          "程序化调用不可静默回退 none"}, ensure_ascii=False))
            raise SystemExit(2)
        context_text = render_reasoned_context(case, chart_schema_version, ziwei_arm)
        return _assemble_reasoned_choice_prompt(case, context_text)
    if method == 'two_stage_reasoning':
        return format_stage1_prompt(case, exp_a=phase4_exp_a)
    if method == 'structured_reasoning':
        return format_structured_reasoning_prompt(case)
    if method in ('direct_choice', 'multi_turn'):
        context_text = None
        if chart_schema_version:
            from benchmark.formatters.chart_context import render_chart_context
            context_text = render_chart_context(case, chart_schema_version)
        return format_direct_choice_prompt(case, chart_context_text=context_text)
    raise ValueError(f"Unsupported benchmark method: {method}")


def _case_chart(case):
    chart = (case or {}).get('chart_input') or {}
    if not chart:
        person = (case or {}).get('person') or {}
        birth = person.get('birth') or {}
        chart = {
            'four_pillars': {},
            'day_master': {},
            'birth_info': {
                'year': birth.get('year'),
                'month': birth.get('month'),
                'day': birth.get('day'),
                'hour': birth.get('hour'),
                'minute': birth.get('minute'),
                'gender': person.get('gender') or '',
            },
        }
    if case and isinstance(chart, dict):
        chart = dict(chart)
        chart["query_domain"] = case.get("domain") or "unknown"
        options = case.get("options") or []
        chart["query_text"] = " ".join([str(case.get("question") or "")] + [str(opt) for opt in options])
    return chart


def _get_bench_case_index():
    if os.environ.get('BAZI_RAG') != '1':
        return None
    try:
        from pathlib import Path as _Path
        from case_index import CaseIndex
        global _BENCH_CASE_INDEX, _BENCH_CASE_INDEX_PATH
        corpus = _Path(os.environ.get(
            "BAZI_RAG_CORPUS",
            str(_Path(__file__).resolve().parents[2] / "benchmark" / "datasets" / "baziqa_contest8_2021_2024_corpus.jsonl"),
        ))
        if not corpus.exists():
            return None
        if _BENCH_CASE_INDEX is None or _BENCH_CASE_INDEX_PATH != str(corpus):
            _BENCH_CASE_INDEX = CaseIndex(corpus)
            _BENCH_CASE_INDEX_PATH = str(corpus)
        return _BENCH_CASE_INDEX
    except Exception:
        return None


def _compute_case_leak(rag_trace, expected_answer):
    """Return True iff expected_answer appears in any retrieved fact string.

    Mirrors `scripts.compute_retrieved_answer_leak.compute_leak_ratio` per-case
    logic so per-trace and post-hoc aggregations stay consistent.
    """
    answer = str(expected_answer or "").strip().lower()
    if not answer:
        return False
    for hit in rag_trace or []:
        for fact in (hit.get("facts") or []) if isinstance(hit, dict) else []:
            if isinstance(fact, str) and answer in fact.lower():
                return True
    return False


def _resolve_rag_trace(case, k=2):
    case_index = _get_bench_case_index()
    if case_index is None:
        return []
    try:
        from bazi_features import extract
        chart = _case_chart(case)
        features = extract(chart)
        cases = case_index.top_k_cases(features, k=k)
        exclude_case_id = str((case or {}).get("case_id") or "")
        if exclude_case_id:
            cases = [c for c in cases if c.get("case_id") != exclude_case_id]
        out = []
        for rank, item in enumerate(cases, 1):
            out.append({
                "rank": rank,
                "person_id": item.get("person_id"),
                "name": item.get("name"),
                "birth_year": item.get("birth_year"),
                "gender": item.get("gender"),
                "domains": item.get("domains") or {},
                "score": item.get("_score"),
                "match_reasons": item.get("match_reasons") or [],
                "facts": (item.get("facts") or [])[:5],
            })
        return out
    except Exception:
        return []


def _resolve_option_evidence_trace(case, k=2):
    case_index = _get_bench_case_index()
    if case_index is None:
        return {}, {}
    try:
        from bazi_features import extract
        chart = _case_chart(case)
        features = extract(chart)
        evidence = case_index.option_evidence(
            features,
            question=str((case or {}).get("question") or ""),
            options=list((case or {}).get("options") or []),
            domain=(case or {}).get("domain") or chart.get("query_domain"),
            k_per_option=k,
            exclude_case_id=str((case or {}).get("case_id") or ""),
        )
        coverage = {label: len(evidence.get(label) or []) for label in ["A", "B", "C", "D"]}
        return evidence, coverage
    except Exception:
        return {}, {}


def _resolve_system_prompt(case, rag_k=2, retrieval_mode='legacy', option_evidence_k=2, suppress_rag=False, suppress_apb=False):
    if suppress_rag and suppress_apb:
        return SYSTEM_PROMPT_BENCHMARK
    prompt = _resolve_system_prompt_inner(case, rag_k, retrieval_mode, option_evidence_k, suppress_rag=suppress_rag)
    if not suppress_apb and os.environ.get('BAZI_APB_BLOCK') == '1' and os.environ.get('BAZI_RAG') == '1':
        try:
            from rag_prompt_builder import format_apb_instruction_block
            prompt = prompt + "\n\n" + format_apb_instruction_block(has_evidence=True)
        except Exception:
            pass
    return prompt


def _resolve_system_prompt_inner(case, rag_k=2, retrieval_mode='legacy', option_evidence_k=2, suppress_rag=False):
    fewshot_path = os.environ.get('BAZI_FEWSHOT_FILE') or ''
    fewshot_examples = []
    if fewshot_path:
        try:
            from rag_prompt_builder import load_fewshot_examples
            fewshot_examples = load_fewshot_examples(fewshot_path)
        except Exception:
            fewshot_examples = []

    if suppress_rag or os.environ.get('BAZI_RAG') != '1':
        if not fewshot_examples:
            return SYSTEM_PROMPT_BENCHMARK
        try:
            from rag_prompt_builder import build_system_prompt
            return build_system_prompt(
                SYSTEM_PROMPT_BENCHMARK,
                {},
                None,  # type: ignore[arg-type]
                enable_rag=False,
                few_shot_examples=fewshot_examples,
            )
        except Exception:
            return SYSTEM_PROMPT_BENCHMARK
    try:
        from rag_prompt_builder import build_system_prompt
        case_index = _get_bench_case_index()
        if case_index is None:
            return SYSTEM_PROMPT_BENCHMARK
        return build_system_prompt(
            SYSTEM_PROMPT_BENCHMARK,
            _case_chart(case),
            case_index,
            enable_rag=True,
            few_shot_examples=fewshot_examples,
            k=rag_k,
            retrieval_mode=retrieval_mode,
            question=str((case or {}).get('question') or ''),
            options=list((case or {}).get('options') or []),
            option_evidence_k=option_evidence_k,
            exclude_case_id=str((case or {}).get('case_id') or ''),
        )
    except Exception:
        return SYSTEM_PROMPT_BENCHMARK


_BENCH_CASE_INDEX = None


def _call_once_messages(messages, provider, model, case=None, temperature=None, timeout=300,
                        rag_k=2, retrieval_mode='legacy', option_evidence_k=2,
                        suppress_rag=False, suppress_apb=False):
    """单次模型调用（不包装异常）。返回 (text, meta_dict)，异常原样抛出。"""
    from claude_api import call_model_messages_sync_with_meta
    text, meta = call_model_messages_sync_with_meta(
        messages,
        provider=provider,
        model=model,
        system_prompt=_resolve_system_prompt(case, rag_k=rag_k, retrieval_mode=retrieval_mode, option_evidence_k=option_evidence_k, suppress_rag=suppress_rag, suppress_apb=suppress_apb),
        temperature=temperature,
        timeout=timeout,
        thinking_mode=(
            _PHASE6_CTX.thinking_mode if _PHASE6_CTX is not None else None
        ),
    )
    return str(text).strip(), meta


def _call_with_optional_ledger(messages, provider, model, case, temperature, timeout,
                               rag_k, retrieval_mode, option_evidence_k,
                               suppress_rag, suppress_apb, sample_idx=0):
    # 执行偏离（Task 6）：计划要求两函数各抽一份 _call_once 闭包；实现合并为单一
    # 共享入口，语义等价且消除重复。ctx=None 时保留原"包装一切异常"旧行为（零变化）；
    # ctx 激活时交 _attempt_with_ledger（崩溃冒泡 / 网络失败重试记账）。
    call_once = lambda: _call_once_messages(  # noqa: E731
        messages, provider, model, case=case, temperature=temperature, timeout=timeout,
        rag_k=rag_k, retrieval_mode=retrieval_mode, option_evidence_k=option_evidence_k,
        suppress_rag=suppress_rag, suppress_apb=suppress_apb)
    if _PHASE6_CTX is None:
        try:
            text, _ = call_once()
            return text
        except Exception as e:
            raise RuntimeError(f"model_call_failed: {type(e).__name__}: {str(e)[:120]}") from e
    return _attempt_with_ledger(case, call_once, sample_idx=sample_idx)


def call_model_sync(prompt, provider, model, case=None, temperature=None, timeout=300, rag_k=2, retrieval_mode='legacy', option_evidence_k=2, suppress_rag=False, suppress_apb=False, sample_idx=0):
    messages = [{"role": "user", "content": prompt}]
    return _call_with_optional_ledger(
        messages, provider, model, case, temperature, timeout,
        rag_k, retrieval_mode, option_evidence_k, suppress_rag, suppress_apb,
        sample_idx=sample_idx)


def call_model_messages_with_history(messages, provider, model, case=None, temperature=None, timeout=300, rag_k=2, retrieval_mode='legacy', option_evidence_k=2, suppress_rag=False, suppress_apb=False):
    return _call_with_optional_ledger(
        messages, provider, model, case, temperature, timeout,
        rag_k, retrieval_mode, option_evidence_k, suppress_rag, suppress_apb)


def _group_cases_by_person(cases):
    groups = {}
    order = []
    for case in cases:
        person = case.get('person') or {}
        person_id = person.get('person_id') or case.get('case_id')
        if person_id not in groups:
            groups[person_id] = []
            order.append(person_id)
        groups[person_id].append(case)
    return [(pid, groups[pid]) for pid in order]


def _prepare_jsonl(path):
    if not path:
        return None
    out_path = os.path.abspath(path)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8"):
        pass
    return out_path


def _append_jsonl(path, row):
    if not path:
        return None
    if _PHASE6_CTX is not None and _PHASE6_CTX.detail_path and \
            os.path.abspath(path) == os.path.abspath(_PHASE6_CTX.detail_path):
        row = _PHASE6_CTX.enrich_row(row)
    out_path = os.path.abspath(path)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out_path


def _write_jsonl(path, rows):
    out_path = _prepare_jsonl(path)
    if not out_path:
        return None
    for row in rows:
        _append_jsonl(out_path, row)
    return out_path


def _retrieval_call_kwargs(rag_k, retrieval_mode='legacy', option_evidence_k=2):
    kwargs = {"rag_k": rag_k}
    if retrieval_mode != 'legacy':
        kwargs["retrieval_mode"] = retrieval_mode
        kwargs["option_evidence_k"] = option_evidence_k
    return kwargs


def _load_stage1_cache(path):
    if not path:
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return {}


def _save_stage1_cache(path, cache):
    if not path:
        return
    out_path = os.path.abspath(path)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)


def _phase4_runtime_config(provider, model, prompt_version, rag_k, retrieval_mode, option_evidence_k):
    return {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "rag": os.environ.get('BAZI_RAG') == '1',
        "rag_corpus": os.environ.get('BAZI_RAG_CORPUS') or "",
        "rag_k": rag_k,
        "retrieval_mode": retrieval_mode,
        "option_evidence_k": option_evidence_k,
        "fewshot_file": os.environ.get('BAZI_FEWSHOT_FILE') or "",
        "fewshot": "on" if os.environ.get('BAZI_FEWSHOT_FILE') else "off",
        "apb_block": os.environ.get('BAZI_APB_BLOCK') == '1',
    }


# ---- Phase 6 6B2: dual_system reasoning pipeline ----

def _dual_stage_seed(case) -> bool:
    ctx = _PHASE6_CTX
    return judge_swap_seed(ctx.dataset_id, case.get("case_id", ""), ctx.repeat_idx)


def _load_existing_detail(detail_path, key):
    if not detail_path or not os.path.exists(detail_path):
        return "", None
    target = list(key)
    try:
        with open(detail_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("attempt_key") == target:
                    return row.get("raw_answer", ""), row.get("predicted_answer")
    except (OSError, json.JSONDecodeError):
        pass
    return "", None


def _dual_write_detail(case, stage, raw, predicted, terminal_state=None, parser_valid=None):
    ctx = _PHASE6_CTX
    expected = extract_choice(case.get("answer"))
    row = {
        "case_id": case.get("case_id"),
        "predicted_answer": predicted,
        "raw_answer": raw,
        "expected_answer": expected,
        "correct": predicted == expected if predicted is not None else False,
        "call_success": bool(raw) and not str(raw).startswith("model_call_failed"),
        "dual_stage": stage,
        "parser_valid": parser_valid if parser_valid is not None else (predicted is not None),
        "sample_idx": 0,
        "permutation_id": case.get("_permutation_id") or "p0",
    }
    if terminal_state:
        row["terminal_state"] = terminal_state
    _append_jsonl(ctx.detail_path, row)


def _call_dual_stage(case, provider, model, temperature, stage, prompt, rag_k, retrieval_mode, option_evidence_k):
    """单 stage 调用。只捕获 model_call_failed；HardCapExhausted/崩溃冒泡。
    返回 (raw, ans, failed)。
    """
    from benchmark.runners.profiles import resolve_profile, visibility_gate
    ctx = _PHASE6_CTX
    # Visibility gate (Task 8)
    ziwei_arm_map = {"bazi": "none", "ziwei": "only", "judge": "judge"}
    profile = resolve_profile(ctx.profile_id)
    gate = visibility_gate(prompt, profile, "legacy_v0", ziwei_arm=ziwei_arm_map.get(stage))
    if gate != "PASS":
        _dual_write_detail(case, stage, prompt, None, terminal_state="unresolved", parser_valid=False)
        return prompt, None, True
    prev = ctx.attempt_stage
    ctx.attempt_stage = stage
    try:
        raw = call_model_sync(prompt, provider, model, case=case, temperature=temperature,
                              **_retrieval_call_kwargs(rag_k, retrieval_mode, option_evidence_k))
        if stage == "judge":
            ans = extract_judge_answer(raw)
            if ans is None:
                _dual_write_detail(case, stage, raw, None, terminal_state="judge_unresolved", parser_valid=False)
            else:
                _dual_write_detail(case, stage, raw, ans)
        else:
            ans = extract_reasoned_choice_answer(raw)
            if ans is None:
                _dual_write_detail(case, stage, raw, None, terminal_state="invalid", parser_valid=False)
            else:
                _dual_write_detail(case, stage, raw, ans)
        return raw, ans, False
    except RuntimeError as exc:
        if not str(exc).startswith("model_call_failed"):
            raise
        _dual_write_detail(case, stage, "", None, terminal_state="call_failed", parser_valid=False)
        return "", None, True
    finally:
        ctx.attempt_stage = prev


def _resolve_and_judge(case, provider, model, temperature, b_ans, b_raw, z_ans, z_raw,
                       completed_keys, rag_k, retrieval_mode, option_evidence_k):
    ctx = _PHASE6_CTX
    cid = case.get("case_id")
    if b_ans is not None and z_ans is not None and b_ans == z_ans:
        return b_ans
    if b_ans is None and z_ans is None:
        return None
    prev = ctx.attempt_stage
    ctx.attempt_stage = "judge"
    try:
        j_key = ctx.attempt_key_for(case)
        if completed_keys and tuple(j_key) in completed_keys:
            _, existing = _load_existing_detail(ctx.detail_path, j_key)
            return existing
        r1 = b_raw if b_raw else "未达成结论"
        r2 = z_raw if z_raw else "未达成结论"
        a1 = b_ans or "未给出"
        a2 = z_ans or "未给出"
        swap = _dual_stage_seed(case)
        prompt = build_judge_prompt(case, a1, r1, a2, r2, swap=swap)
        _, verdict, _ = _call_dual_stage(case, provider, model, temperature, "judge", prompt,
                                         rag_k, retrieval_mode, option_evidence_k)
        return verdict
    finally:
        ctx.attempt_stage = prev


def _run_dual_case(case, provider, model, temperature, rag_k, retrieval_mode, option_evidence_k,
                   completed_keys):
    ctx = _PHASE6_CTX
    cid = case.get("case_id")
    prev_stage = ctx.attempt_stage
    b_raw, b_ans, z_raw, z_ans = "", None, "", None
    try:
        ctx.attempt_stage = "bazi"
        b_key = ctx.attempt_key_for(case)
        if completed_keys and tuple(b_key) in completed_keys:
            b_raw, b_ans = _load_existing_detail(ctx.detail_path, b_key)
        else:
            b_raw, b_ans, _ = _call_dual_stage(
                case, provider, model, temperature, "bazi", build_bazi_pipeline_prompt(case),
                rag_k, retrieval_mode, option_evidence_k)

        ctx.attempt_stage = "ziwei"
        z_key = ctx.attempt_key_for(case)
        if completed_keys and tuple(z_key) in completed_keys:
            z_raw, z_ans = _load_existing_detail(ctx.detail_path, z_key)
        else:
            z_raw, z_ans, _ = _call_dual_stage(
                case, provider, model, temperature, "ziwei", build_ziwei_pipeline_prompt(case),
                rag_k, retrieval_mode, option_evidence_k)

        final = _resolve_and_judge(case, provider, model, temperature,
                                   b_ans, b_raw, z_ans, z_raw, completed_keys,
                                   rag_k, retrieval_mode, option_evidence_k)
        return cid, final, b_ans, z_ans
    finally:
        ctx.attempt_stage = prev_stage


def run_dual_system_benchmark(cases, provider, model, prompt_version, max_cases=20, temperature=0.0,
                              case_details_jsonl=None, rag_k=2, config_id=None, retrieval_mode='legacy',
                              option_evidence_k=2, resume_append=False, completed_keys=None):
    if case_details_jsonl and not resume_append:
        _prepare_jsonl(case_details_jsonl)
    predictions, case_details, failed_cases = {}, [], []

    for case in (cases[:max_cases] if max_cases else cases):
        cid, final, b_ans, z_ans = _run_dual_case(
            case, provider, model, temperature, rag_k, retrieval_mode, option_evidence_k,
            completed_keys)
        predictions[cid] = final
        case_details.append({
            "case_id": cid,
            "predicted_answer": final,
            "bazi_answer": b_ans,
            "ziwei_answer": z_ans,
        })
        if final is None:
            failed_cases.append({"case_id": cid, "reason": "unresolved",
                                 "bazi_ans": b_ans, "ziwei_ans": z_ans})
        time.sleep(1)

    return {
        "cases": (cases[:max_cases] if max_cases else cases),
        "predictions": predictions,
        "evidence_results": [],
        "safety_results": [],
        "case_details": case_details,
        "failed_cases": failed_cases,
    }


def run_model_benchmark(cases, provider, model, prompt_version, max_cases=20, method='direct_choice', temperature=0.0, case_details_jsonl=None, rag_k=2, config_id=None, retrieval_mode='legacy', option_evidence_k=2, shuffle_options=False, shuffle_seed=None, n_samples=1, sample_temperature=0.4, aggregate='majority', phase4_evidence_mode='all', phase4_stage1_cache=None, phase4_exp_b=False, phase4_exp_a=False, phase4_exp_c=False, phase4_exp_c2=False, phase4_direct_c2=False, chart_schema_version=None, profile_formatter=None, ziwei_arm=None, resume_append=False, completed_keys=None):
    if method == 'multi_turn':
        return run_multi_turn_benchmark(cases, provider, model, max_cases=max_cases, temperature=temperature, case_details_jsonl=case_details_jsonl, rag_k=rag_k, config_id=config_id, retrieval_mode=retrieval_mode, option_evidence_k=option_evidence_k, chart_schema_version=chart_schema_version, resume_append=resume_append)
    if method == 'dual_system':
        return run_dual_system_benchmark(cases, provider, model, prompt_version, max_cases=max_cases,
                                         temperature=temperature, case_details_jsonl=case_details_jsonl,
                                         rag_k=rag_k, config_id=config_id, retrieval_mode=retrieval_mode,
                                         option_evidence_k=option_evidence_k, resume_append=resume_append,
                                         completed_keys=completed_keys)
    if phase4_exp_c and phase4_exp_c2:
        raise ValueError("run_model_benchmark: --phase4-exp-c and --phase4-exp-c2 are mutually exclusive")
    if phase4_direct_c2 and method != 'direct_choice':
        raise ValueError("run_model_benchmark: --phase4-direct-c2 requires --method direct_choice")
    runtime_config = _phase4_runtime_config(provider, model, prompt_version, rag_k, retrieval_mode, option_evidence_k)

    if not isinstance(n_samples, int) or n_samples < 1:
        raise ValueError(f"run_model_benchmark: n_samples must be a positive int, got {n_samples!r}")
    if aggregate not in {"majority", "emit_samples"}:
        raise ValueError(f"run_model_benchmark: aggregate {aggregate!r} is not supported")
    if aggregate == "emit_samples":
        if not isinstance(n_samples, int) or n_samples < 2:
            raise ValueError("emit_samples 需要 n_samples > 1（6A1 逐样本模式）")
        if _PHASE6_CTX is None:
            raise ValueError("emit_samples 仅支持 Phase 6 profile 模式（需 attempt 账本/续跑/manifest）")

    if shuffle_options:
        if shuffle_seed is None:
            raise ValueError("run_model_benchmark: shuffle_options=True requires an explicit int shuffle_seed")
        cases = [
            _shuffle_options_fn(case, seed=shuffle_seed + idx)
            for idx, case in enumerate(cases)
        ]

    if not resume_append:
        _prepare_jsonl(case_details_jsonl)

    predictions = {}
    evidence_results = []
    safety_results = []
    case_details = []
    failed_cases = []

    # Stage 1 cache for two_stage_reasoning. The optional file path lets
    # separate perm/mode subprocesses share the same Stage 1 hypotheses.
    stage1_cache = _load_stage1_cache(phase4_stage1_cache)

    limited_cases = cases[:max_cases]
    print(f"Running model benchmark on {len(limited_cases)} cases...")

    for i, case in enumerate(limited_cases):
        case_id = case['case_id']
        print(f"  [{i+1}/{len(limited_cases)}] {case_id}")

        option_scores = None
        if phase4_direct_c2:
            from benchmark.runners.per_option_scorer import score_options

            option_scores = score_options(case)
            prompt = format_direct_c2_prompt(case, option_scores)
        else:
            prompt = build_benchmark_prompt(case, method=method, phase4_exp_a=phase4_exp_a,
                                            chart_schema_version=chart_schema_version,
                                            profile_formatter=profile_formatter,
                                            ziwei_arm=ziwei_arm)

        # Two-stage reasoning path
        if method == 'two_stage_reasoning':
            try:
                # Stage 1: label-blind reasoning (suppress RAG/APB)
                cached = stage1_cache.get(case_id)
                stage1_cache_hit = cached is not None
                if stage1_cache_hit:
                    raw1, hypothesis = cached.get("raw"), cached.get("hypothesis")
                    print(f"    [Stage 1 cached]")
                else:
                    raw1 = call_model_sync(
                        prompt,
                        provider,
                        model,
                        case=case,
                        temperature=0.0,
                        suppress_rag=True,
                        suppress_apb=True,
                    )
                    hypothesis = parse_stage1_result(raw1)
                    stage1_cache[case_id] = {"raw": raw1, "hypothesis": hypothesis}
                    _save_stage1_cache(phase4_stage1_cache, stage1_cache)

                # Parse failure → fallback to structured_reasoning
                if hypothesis is None:
                    print(f"    [Stage 1 parse failed → fallback to structured_reasoning]")
                    fallback_prompt = format_structured_reasoning_prompt(case)
                    answer = call_model_sync(
                        fallback_prompt,
                        provider,
                        model,
                        case=case,
                        temperature=temperature,
                        **_retrieval_call_kwargs(rag_k, retrieval_mode, option_evidence_k),
                    )
                    predicted = None
                    sample_records = None
                    fallback = True
                    fallback_reason = "stage1_parse_failed"
                else:
                    # Stage 2: option matching with evidence
                    if phase4_exp_b:
                        # Experiment B: skip Stage 1 hypothesis, use evidence only
                        print(f"    [Stage 2 EXP-B: no hypothesis]")
                        is_time = is_time_location_question(case.get('question', ''), case.get('options', []))
                        evidence_mode = phase4_evidence_mode if phase4_evidence_mode in ('all', 'top2') else 'all'
                        evidence = build_stage2_evidence(case, "", mode=evidence_mode, exp_c=phase4_exp_c, exp_c2=phase4_exp_c2)
                        stage2_prompt = format_stage2_prompt(case, hypothesis=None, evidence=evidence, is_time=is_time)
                    else:
                        # Normal mode: with Stage 1 hypothesis
                        print(f"    [Stage 2 with hypothesis]")
                        is_time = is_time_location_question(case.get('question', ''), case.get('options', []))
                        # evidence_mode: 'all' for smoke (default), 'top2' only for formal if hit rate >= 0.85
                        evidence_mode = phase4_evidence_mode if phase4_evidence_mode in ('all', 'top2') else 'all'
                        evidence = build_stage2_evidence(case, hypothesis, mode=evidence_mode, exp_c=phase4_exp_c, exp_c2=phase4_exp_c2)
                        stage2_prompt = format_stage2_prompt(case, hypothesis, evidence, is_time=is_time)

                    # Self-consistency for Stage 2: multiple samples with majority vote
                    if n_samples > 1:
                        def _do_stage2_call(call_temperature):
                            raw = call_model_sync(
                                stage2_prompt,
                                provider,
                                model,
                                case=case,
                                temperature=call_temperature,
                                **_retrieval_call_kwargs(rag_k, retrieval_mode, option_evidence_k),
                            )
                            parsed = extract_choice_with_meta(raw)
                            return raw, parsed.get('choice')

                        samples = sample_answers(
                            _do_stage2_call,
                            n=n_samples,
                            temperatures=[sample_temperature] * n_samples,
                        )
                        predicted = majority_vote([label for _, label in samples])
                        # Use the first sample whose predicted label matches the majority vote
                        answer = samples[0][0]
                        if predicted is not None:
                            for raw, label in samples:
                                if label == predicted:
                                    answer = raw
                                    break
                        sample_records = [{"raw": raw, "predicted": label} for raw, label in samples]
                        print(f"    [SC votes: {dict((label, sum(1 for _, l in samples if l == label)) for label in set(l for _, l in samples if l is not None))} → {predicted}]")
                    else:
                        answer = call_model_sync(
                            stage2_prompt,
                            provider,
                            model,
                            case=case,
                            temperature=temperature,
                            **_retrieval_call_kwargs(rag_k, retrieval_mode, option_evidence_k),
                        )
                        sample_records = None
                        predicted = None
                    fallback = False
                    fallback_reason = None

                # Build detail for two_stage
                expected = extract_choice(case.get('answer'))
                meta = extract_choice_with_meta(answer)
                if predicted is None:
                    predicted = meta['choice']
                rag_trace = _resolve_rag_trace(case, k=rag_k)
                option_evidence = {}
                option_evidence_coverage = {}
                if retrieval_mode == 'option_grounded':
                    option_evidence, option_evidence_coverage = _resolve_option_evidence_trace(case, k=option_evidence_k)

                ev_result = score_case_evidence(case, answer)
                ev_result['case_id'] = case_id
                evidence_results.append(ev_result)

                safe_result = score_safety(answer)
                safe_result['case_id'] = case_id
                safety_results.append(safe_result)

                predictions[case_id] = answer

                detail = {
                    "case_id": case_id,
                    "domain": case.get('domain', 'unknown'),
                    "question": case.get('question', '')[:50],
                    "expected_answer": expected,
                    "predicted_answer": predicted,
                    "raw_answer": answer,
                    "correct": predicted == expected,
                    "evidence_coverage": ev_result.get('coverage', 0.0),
                    "safety_score": safe_result.get('score', 0.0),
                    "parser_source": meta.get('source'),
                    "parser_valid": meta.get('valid'),
                    "rag_k": rag_k,
                    "retrieval_mode": retrieval_mode,
                    "rag_trace": rag_trace,
                    "option_evidence": option_evidence,
                    "option_evidence_coverage": option_evidence_coverage,
                    "retrieved_answer_leak": _compute_case_leak(rag_trace, expected),
                    "config_id": config_id,
                    "call_success": True,
                    "permutation_id": case.get('_permutation_id'),
                    "label_map": case.get('answer_label_map') or {},
                    "predicted_identity": to_original_option_identity(predicted, case.get('answer_label_map') or {}),
                    "correct_identity": case.get('_original_answer'),
                    "mode": "on-3" if case.get('answer_label_map') else "off-3",
                    # Phase 4 fields
                    "phase4_stage1_raw": raw1 if not fallback else None,
                    "phase4_stage1_hypothesis": hypothesis if not fallback else None,
                    "phase4_stage1_cache_hit": stage1_cache_hit,
                    "phase4_stage1_call_made": not stage1_cache_hit,
                    "phase4_stage2_raw": answer if not fallback else None,
                    "phase4_fallback": fallback,
                    "phase4_fallback_reason": fallback_reason,
                    "phase4_is_time_question": is_time if not fallback else None,
                    "phase4_conflict": None,  # TODO: detect conflict between hypothesis and evidence
                    "phase4_evidence_mode": evidence_mode if not fallback else None,
                    "phase4_sc_samples": sample_records if sample_records else None,
                }
                if phase4_exp_c2:
                    from benchmark.runners.per_option_scorer import score_options

                    phase4_scores = score_options(case)
                    detail["phase4_exp_c2"] = True
                    detail["phase4_option_scores"] = phase4_scores
                    detail["phase4_option_score_domain"] = phase4_scores[0]["domain"] if phase4_scores else None
                    detail["phase4_runtime_config"] = runtime_config
                parser_failure_reason = classify_parser_failure(
                    raw_answer=answer,
                    parsed_choice=predicted,
                    valid=meta.get('valid', False),
                    label_map=case.get('answer_label_map') or {},
                    call_success=True,
                )
                detail["parser_failure_reason"] = parser_failure_reason
                if shuffle_options:
                    label_map = case.get('answer_label_map') or {}
                    detail["answer_label_map"] = label_map
                    detail["original_expected_answer"] = case.get('_original_answer')
                    detail["original_predicted_answer"] = unshuffle_predicted_answer(predicted, label_map)
                case_details.append(detail)
                _append_jsonl(case_details_jsonl, detail)
                time.sleep(1)
                continue
            except RuntimeError as e:
                err_msg = str(e)[:120]
                failed_cases.append({'case_id': case_id, 'error': err_msg})
                expected_letter = extract_choice(case.get('answer'))
                failure_detail = {
                    "case_id": case_id,
                    "domain": case.get('domain', 'unknown'),
                    "question": case.get('question', '')[:50],
                    "expected_answer": expected_letter,
                    "predicted_answer": None,
                    "raw_answer": "",
                    "correct": False,
                    "error": err_msg,
                    "evidence_coverage": 0.0,
                    "safety_score": 0.0,
                    "parser_source": None,
                    "parser_valid": False,
                    "rag_k": rag_k,
                    "retrieval_mode": retrieval_mode,
                    "rag_trace": [],
                    "option_evidence": {},
                    "option_evidence_coverage": {},
                    "retrieved_answer_leak": False,
                    "config_id": config_id,
                    "call_success": False,
                    "permutation_id": case.get('_permutation_id'),
                    "label_map": case.get('answer_label_map') or {},
                    "predicted_identity": None,
                    "correct_identity": case.get('_original_answer'),
                    "mode": "on-3" if case.get('answer_label_map') else "off-3",
                    "parser_failure_reason": "model_call_failed",
                    "phase4_fallback": True,
                    "phase4_fallback_reason": "model_call_failed",
                }
                if phase4_exp_c2:
                    failure_detail["phase4_exp_c2"] = True
                    failure_detail["phase4_runtime_config"] = runtime_config
                case_details.append(failure_detail)
                _append_jsonl(case_details_jsonl, failure_detail)
                time.sleep(1)
                continue

        def _do_one_call(call_temperature):
            raw = call_model_sync(
                prompt,
                provider,
                model,
                case=case,
                temperature=call_temperature,
                **_retrieval_call_kwargs(rag_k, retrieval_mode, option_evidence_k),
            )
            parsed = extract_choice_with_meta(raw)
            return raw, parsed.get('choice')

        if aggregate == "emit_samples":
            # 6A1（设计 §5.2）：逐样本独立调用/记账/明细；聚合完全离线（编排器 strict_majority）。
            # 每样本：sample_idx 入 attempt key（独立终态/重试账本/续跑），
            # temperature=sample_temperature；失败样本写 call_failed 行（占分母）后继续。
            expected = extract_choice(case.get('answer'))
            ctx = _PHASE6_CTX
            pending = [i for i in range(n_samples)
                       if not completed_keys
                       or ctx.attempt_key_for(case, sample_idx=i) not in completed_keys]
            if not pending:
                continue                    # resume：该 case 5 样本全部完成
            for sample_idx in pending:
                try:
                    raw = call_model_sync(
                        prompt, provider, model, case=case,
                        temperature=sample_temperature, sample_idx=sample_idx,
                        **_retrieval_call_kwargs(rag_k, retrieval_mode, option_evidence_k),
                    )
                    meta = extract_choice_with_meta(raw)
                    s_pred = meta["choice"]
                    ev = score_case_evidence(case, raw)
                    sf = score_safety(raw)
                    s_detail = {
                        "case_id": case_id, "domain": case.get("domain", "unknown"),
                        "question": case.get("question", "")[:50],
                        "expected_answer": expected, "predicted_answer": s_pred,
                        "raw_answer": raw, "correct": s_pred == expected,
                        "evidence_coverage": ev.get("coverage", 0.0),
                        "safety_score": sf.get("score", 0.0),
                        "parser_source": meta.get("source"), "parser_valid": meta.get("valid"),
                        "rag_k": rag_k, "retrieval_mode": retrieval_mode,
                        "rag_trace": [], "option_evidence": {}, "option_evidence_coverage": {},
                        "retrieved_answer_leak": False, "config_id": config_id,
                        "call_success": True,
                        "permutation_id": case.get("_permutation_id"),
                        "label_map": case.get("answer_label_map") or {},
                        "predicted_identity": s_pred,
                        "correct_identity": case.get("_original_answer"),
                        "mode": "off-3",
                        "parser_failure_reason": classify_parser_failure(
                            raw_answer=raw, parsed_choice=s_pred,
                            valid=meta.get("valid", False),
                            label_map=case.get("answer_label_map") or {}, call_success=True),
                        "sample_idx": sample_idx, "n_samples": n_samples,
                        "aggregate": aggregate,
                    }
                except RuntimeError as e:
                    if not str(e).startswith("model_call_failed"):
                        raise   # 崩溃类冒泡（Policy A）
                    s_detail = {
                        "case_id": case_id, "domain": case.get("domain", "unknown"),
                        "question": case.get("question", "")[:50],
                        "expected_answer": expected, "predicted_answer": None,
                        "raw_answer": "", "correct": False,
                        "error": str(e)[:120],
                        "evidence_coverage": 0.0, "safety_score": 0.0,
                        "parser_source": None, "parser_valid": False,
                        "rag_k": rag_k, "retrieval_mode": retrieval_mode,
                        "rag_trace": [], "option_evidence": {}, "option_evidence_coverage": {},
                        "retrieved_answer_leak": False, "config_id": config_id,
                        "call_success": False,
                        "permutation_id": case.get("_permutation_id"),
                        "label_map": case.get("answer_label_map") or {},
                        "predicted_identity": None,
                        "correct_identity": case.get("_original_answer"),
                        "mode": "off-3",
                        "parser_failure_reason": "model_call_failed",
                        "sample_idx": sample_idx, "n_samples": n_samples,
                        "aggregate": aggregate,
                    }
                case_details.append(s_detail)
                _append_jsonl(case_details_jsonl, s_detail)
                time.sleep(1)
            predictions[case_id] = s_detail.get("raw_answer") or ""
            continue

        try:
            if n_samples > 1:
                samples = sample_answers(
                    _do_one_call,
                    n=n_samples,
                    temperatures=[sample_temperature] * n_samples,
                )
                predicted = majority_vote([label for _, label in samples])
                # Use the first sample whose predicted label matches the
                # majority-vote winner as the canonical raw_answer so that
                # downstream evidence/safety scoring and detail["raw_answer"]
                # stay consistent with predicted_answer instead of possibly
                # reflecting a minority-vote sample text.
                answer = samples[0][0]
                if predicted is not None:
                    for raw, label in samples:
                        if label == predicted:
                            answer = raw
                            break
                sample_records = [{"raw": raw, "predicted": label} for raw, label in samples]
            else:
                answer = call_model_sync(
                    prompt,
                    provider,
                    model,
                    case=case,
                    temperature=temperature,
                    **_retrieval_call_kwargs(rag_k, retrieval_mode, option_evidence_k),
                )
                predicted = None
                sample_records = None
        except RuntimeError as e:
            if _PHASE6_CTX is not None and not str(e).startswith("model_call_failed"):
                raise  # Phase 6：崩溃类异常直接冒泡（保证崩溃续跑/预算语义可测）
            err_msg = str(e)[:120]
            failed_cases.append({'case_id': case_id, 'error': err_msg})
            # Persist a failure-marker detail so case_details / JSONL denominator
            # stays at max_cases and the ablation accuracy can not be inflated
            # by silently dropping unanswerable cases.
            expected_letter = extract_choice(case.get('answer'))
            failure_detail = {
                "case_id": case_id,
                "domain": case.get('domain', 'unknown'),
                "question": case.get('question', '')[:50],
                "expected_answer": expected_letter,
                "predicted_answer": None,
                "raw_answer": "",
                "correct": False,
                "error": err_msg,
                "evidence_coverage": 0.0,
                "safety_score": 0.0,
                "parser_source": None,
                "parser_valid": False,
                "rag_k": rag_k,
                "retrieval_mode": retrieval_mode,
                "rag_trace": [],
                "option_evidence": {},
                "option_evidence_coverage": {},
                "retrieved_answer_leak": False,
                "config_id": config_id,
                # Phase 3 fields
                "call_success": False,
                "permutation_id": case.get('_permutation_id'),
                "label_map": case.get('answer_label_map') or {},
                "predicted_identity": None,
                "correct_identity": case.get('_original_answer'),
                "mode": "on-3" if case.get('answer_label_map') else "off-3",
                "parser_failure_reason": "model_call_failed",
            }
            if shuffle_options:
                label_map = case.get('answer_label_map') or {}
                failure_detail["answer_label_map"] = label_map
                failure_detail["original_expected_answer"] = case.get('_original_answer')
                failure_detail["original_predicted_answer"] = None
            if phase4_direct_c2:
                failure_detail["phase4_direct_c2"] = True
                failure_detail["phase4_option_scores"] = option_scores or []
                failure_detail["phase4_option_score_domain"] = option_scores[0]["domain"] if option_scores else None
                failure_detail["phase4_runtime_config"] = runtime_config
            case_details.append(failure_detail)
            _append_jsonl(case_details_jsonl, failure_detail)
            time.sleep(1)
            continue

        predictions[case_id] = answer

        ev_result = score_case_evidence(case, answer)
        ev_result['case_id'] = case_id
        evidence_results.append(ev_result)

        safe_result = score_safety(answer)
        safe_result['case_id'] = case_id
        safety_results.append(safe_result)

        expected = extract_choice(case.get('answer'))

        if profile_formatter == 'format_reasoned_choice_prompt':
            from benchmark.formatters.chart_context import extract_reasoned_choice_answer
            predicted = extract_reasoned_choice_answer(answer)
            meta = {
                "choice": predicted,
                "source": "reasoned_final_answer",
                "valid": predicted is not None,
            }
            predictions[case_id] = predicted
        else:
            meta = extract_choice_with_meta(answer)
            if predicted is None:
                predicted = meta['choice']
        rag_trace = _resolve_rag_trace(case, k=rag_k)
        option_evidence = {}
        option_evidence_coverage = {}
        if retrieval_mode == 'option_grounded':
            option_evidence, option_evidence_coverage = _resolve_option_evidence_trace(case, k=option_evidence_k)

        detail = {
            "case_id": case_id,
            "domain": case.get('domain', 'unknown'),
            "question": case.get('question', '')[:50],
            "expected_answer": expected,
            "predicted_answer": predicted,
            "raw_answer": answer,
            "correct": predicted == expected,
            "evidence_coverage": ev_result.get('coverage', 0.0),
            "safety_score": safe_result.get('score', 0.0),
            "parser_source": meta.get('source'),
            "parser_valid": meta.get('valid'),
            "rag_k": rag_k,
            "retrieval_mode": retrieval_mode,
            "rag_trace": rag_trace,
            "option_evidence": option_evidence,
            "option_evidence_coverage": option_evidence_coverage,
            "retrieved_answer_leak": _compute_case_leak(rag_trace, expected),
            "config_id": config_id,
            # Phase 3 fields
            "call_success": True,
            "permutation_id": case.get('_permutation_id'),
            "label_map": case.get('answer_label_map') or {},
            "predicted_identity": to_original_option_identity(predicted, case.get('answer_label_map') or {}),
            "correct_identity": case.get('_original_answer'),
            "mode": "on-3" if case.get('answer_label_map') else "off-3",
        }
        if phase4_direct_c2:
            detail["phase4_direct_c2"] = True
            detail["phase4_option_scores"] = option_scores or []
            detail["phase4_option_score_domain"] = option_scores[0]["domain"] if option_scores else None
            detail["phase4_runtime_config"] = runtime_config
        parser_failure_reason = classify_parser_failure(
            raw_answer=answer,
            parsed_choice=predicted,
            valid=meta.get('valid', False),
            label_map=case.get('answer_label_map') or {},
            call_success=True,
        )
        detail["parser_failure_reason"] = parser_failure_reason
        if shuffle_options:
            label_map = case.get('answer_label_map') or {}
            detail["answer_label_map"] = label_map
            detail["original_expected_answer"] = case.get('_original_answer')
            detail["original_predicted_answer"] = unshuffle_predicted_answer(predicted, label_map)
        if sample_records is not None:
            detail["n_samples"] = n_samples
            detail["aggregate"] = aggregate
            detail["samples"] = sample_records
        case_details.append(detail)
        _append_jsonl(case_details_jsonl, detail)

        time.sleep(1)

    return {
        "cases": limited_cases,
        "predictions": predictions,
        "evidence_results": evidence_results,
        "safety_results": safety_results,
        "case_details": case_details,
        "failed_cases": failed_cases,
    }


def run_multi_turn_benchmark(cases, provider, model, max_cases=20, temperature=0.0, case_details_jsonl=None, rag_k=2, config_id=None, retrieval_mode='legacy', option_evidence_k=2, chart_schema_version=None, resume_append=False):
    if not resume_append:
        _prepare_jsonl(case_details_jsonl)
    limited_cases = cases[:max_cases]
    predictions = {}
    evidence_results = []
    safety_results = []
    case_details = []
    failed_cases = []

    groups = _group_cases_by_person(limited_cases)
    print(f"Running multi-turn benchmark on {len(limited_cases)} cases across {len(groups)} persons...")

    for group_idx, (person_id, person_cases) in enumerate(groups):
        if chart_schema_version:
            from benchmark.formatters.chart_context import render_chart_context
            context_text = format_multi_turn_context(
                person_cases[0],
                chart_context_text=render_chart_context(person_cases[0], chart_schema_version),
            )
        else:
            context_text = format_multi_turn_context(person_cases[0])
        history = [
            {"role": "user", "content": context_text},
            {"role": "assistant", "content": "已记住命主信息，请提问。"},
        ]
        for case_idx, case in enumerate(person_cases):
            case_id = case['case_id']
            print(f"  [group {group_idx+1}/{len(groups)} q {case_idx+1}/{len(person_cases)}] {case_id}")
            question_text = format_multi_turn_question(case)
            messages = history + [{"role": "user", "content": question_text}]
            try:
                answer = call_model_messages_with_history(
                    messages,
                    provider,
                    model,
                    case=case,
                    temperature=temperature,
                    **_retrieval_call_kwargs(rag_k, retrieval_mode, option_evidence_k),
                )
            except RuntimeError as e:
                if _PHASE6_CTX is not None and not str(e).startswith("model_call_failed"):
                    raise  # Phase 6：崩溃类异常直接冒泡（保证崩溃续跑/预算语义可测）
                err_msg = str(e)[:120]
                failed_cases.append({'case_id': case_id, 'error': err_msg})
                expected = extract_choice(case.get('answer'))
                detail = {
                    "case_id": case_id,
                    "domain": case.get('domain', 'unknown'),
                    "question": case.get('question', '')[:50],
                    "expected_answer": expected,
                    "predicted_answer": None,
                    "raw_answer": "",
                    "correct": False,
                    "error": err_msg,
                    "evidence_coverage": 0.0,
                    "safety_score": 0.0,
                    "parser_source": None,
                    "parser_valid": False,
                    "rag_k": rag_k,
                    "retrieval_mode": retrieval_mode,
                    "rag_trace": [],
                    "option_evidence": {},
                    "option_evidence_coverage": {},
                    "retrieved_answer_leak": False,
                    "config_id": config_id,
                    "call_success": False,
                    "permutation_id": case.get('_permutation_id'),
                    "label_map": case.get('answer_label_map') or {},
                    "predicted_identity": None,
                    "correct_identity": case.get('_original_answer'),
                    "mode": "on-3" if case.get('answer_label_map') else "off-3",
                    "parser_failure_reason": "model_call_failed",
                }
                case_details.append(detail)
                _append_jsonl(case_details_jsonl, detail)
                continue

            predictions[case_id] = answer
            history.append({"role": "user", "content": question_text})
            history.append({"role": "assistant", "content": answer})

            ev_result = score_case_evidence(case, answer)
            ev_result['case_id'] = case_id
            evidence_results.append(ev_result)

            safe_result = score_safety(answer)
            safe_result['case_id'] = case_id
            safety_results.append(safe_result)

            expected = extract_choice(case.get('answer'))
            meta = extract_choice_with_meta(answer)
            predicted = meta['choice']
            rag_trace = _resolve_rag_trace(case, k=rag_k)
            option_evidence = {}
            option_evidence_coverage = {}
            if retrieval_mode == 'option_grounded':
                option_evidence, option_evidence_coverage = _resolve_option_evidence_trace(case, k=option_evidence_k)
            detail = {
                "case_id": case_id,
                "domain": case.get('domain', 'unknown'),
                "question": case.get('question', '')[:50],
                "expected_answer": expected,
                "predicted_answer": predicted,
                "raw_answer": answer,
                "correct": predicted == expected,
                "evidence_coverage": ev_result.get('coverage', 0.0),
                "safety_score": safe_result.get('score', 0.0),
                "parser_source": meta.get('source'),
                "parser_valid": meta.get('valid'),
                "rag_k": rag_k,
                "retrieval_mode": retrieval_mode,
                "rag_trace": rag_trace,
                "option_evidence": option_evidence,
                "option_evidence_coverage": option_evidence_coverage,
                "retrieved_answer_leak": _compute_case_leak(rag_trace, expected),
                "config_id": config_id,
            }
            case_details.append(detail)
            _append_jsonl(case_details_jsonl, detail)
            time.sleep(1)

    return {
        "cases": limited_cases,
        "predictions": predictions,
        "evidence_results": evidence_results,
        "safety_results": safety_results,
        "case_details": case_details,
        "failed_cases": failed_cases,
    }


def _phase6_visibility_filter(cases, profile, profile_formatter, args):
    """裁决 1B（计划 Task 6 增补）：per-case 可见性门禁。违规 case 不进入模型运行，
    直接以 terminal_state=unresolved 追加 detail（经 _append_jsonl 富化 attempt_key）；
    官方臂 gate 文本取官方 prompt，reasoned 臂取 render_reasoned_context，
    dual_system 臂分别对 bazi/ziwei/judge 三段做检查，任一违规即 BLOCK，
    其余取 render_chart_context。"""
    from benchmark.runners.profiles import assert_visibility
    detail_abs = os.path.abspath(args.case_details_jsonl) if args.case_details_jsonl else None
    ziwei_arm = getattr(args, "ziwei_arm", None)
    passed = []
    for case in cases:
        if profile_formatter == 'format_official_cot_prompt':
            from benchmark.formatters.mingli_prompt import format_official_cot_prompt
            gate_text = format_official_cot_prompt(case)
            violations = assert_visibility(gate_text, profile, profile.chart_schema_version,
                                           ziwei_arm=ziwei_arm)
        elif profile_formatter == 'format_dual_system_prompt':
            # Dual system: check all three stages independently
            violations = []
            # Bazi stage
            gate_b = build_bazi_pipeline_prompt(case)
            v_b = assert_visibility(gate_b, profile, profile.chart_schema_version,
                                    ziwei_arm="none", stage="bazi")
            if v_b:
                violations.extend([f"bazi:{v}" for v in v_b])
            # Ziwei stage
            gate_z = build_ziwei_pipeline_prompt(case)
            v_z = assert_visibility(gate_z, profile, profile.chart_schema_version,
                                    ziwei_arm="only", stage="ziwei")
            if v_z:
                violations.extend([f"ziwei:{v}" for v in v_z])
            # Judge stage (check blinded version without answer labels)
            swap = bool(_dual_stage_seed(case) % 2)
            gate_j = build_judge_prompt(case, "A", "(bazi rationale placeholder)",
                                        "B", "(ziwei rationale placeholder)", swap=swap)
            v_j = assert_visibility(gate_j, profile, profile.chart_schema_version,
                                    ziwei_arm=None, stage="judge")
            if v_j:
                violations.extend([f"judge:{v}" for v in v_j])
        elif profile_formatter == 'format_reasoned_choice_prompt':
            from benchmark.formatters.chart_context import render_reasoned_context
            if ziwei_arm is None:
                print(json.dumps({"status": "BLOCKED",
                    "reason": "reasoned profile visibility gate 要求显式 ziwei_arm"},
                    ensure_ascii=False))
                raise SystemExit(2)
            gate_text = render_reasoned_context(case, profile.chart_schema_version, ziwei_arm)
            violations = assert_visibility(gate_text, profile, profile.chart_schema_version,
                                           ziwei_arm=ziwei_arm)
        else:
            from benchmark.formatters.chart_context import render_chart_context
            gate_text = render_chart_context(case, profile.chart_schema_version)
            violations = assert_visibility(gate_text, profile, profile.chart_schema_version,
                                           ziwei_arm=ziwei_arm)
        if violations:
            print(f"  [gate BLOCKED] {case.get('case_id')}: {len(violations)} violations")
            _append_jsonl(detail_abs, {
                "case_id": case.get("case_id"),
                "gate_blocked": True,
                "violations": violations,
                "expected_answer": extract_choice(case.get("answer")),
                "predicted_answer": None,
                "raw_answer": "",
                "correct": False,
                "call_success": False,
                "terminal_state": "unresolved",
            })
        else:
            passed.append(case)
    return passed


def _write_phase6_summary(args, status):
    ctx = _PHASE6_CTX
    summary = {
        "status": status,
        "profile_id": args.profile,
        "arm": args.arm,
        "repeat_idx": args.repeat_idx,
        "scheduled_calls": args.scheduled_calls,
        "hard_cap": args.hard_cap,
        "calls_attempted": ctx.calls_attempted if ctx else None,
        "retry_total": sum(ctx.retry_counts.values()) if ctx else None,
    }
    os.makedirs(os.path.abspath(args.output_dir), exist_ok=True)
    with open(os.path.join(os.path.abspath(args.output_dir), "summary.json"),
              "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run BaziQA-style benchmark')
    parser.add_argument('--dataset', required=True, help='Path to JSONL dataset')
    parser.add_argument('--predictions', help='Path to JSON predictions map (offline mode)')
    parser.add_argument('--model-runner', action='store_true', help='Enable real model calls')
    parser.add_argument('--provider', default='deepseek', help='deepseek, anthropic, kimi, glm, or qwen')
    parser.add_argument('--model', default='deepseek-v4-pro', help='Model name')
    parser.add_argument('--prompt-version', default='srp_v1', help='Prompt version')
    parser.add_argument('--output-dir', default='benchmark/outputs', help='Report output directory')
    parser.add_argument('--max-cases', type=int, default=20, help='Max cases to run (model mode)')
    parser.add_argument('--method', default=None, choices=['direct_choice', 'multi_turn', 'structured_reasoning', 'two_stage_reasoning', 'dual_system'])
    parser.add_argument('--rag', action='store_true', help='Enable BaziQA case retrieval augmentation (sets BAZI_RAG=1).')
    parser.add_argument('--rag-corpus', default='', help='JSONL corpus file used when --rag is enabled')
    parser.add_argument('--fewshot-file', default='', help='Optional JSONL file with few-shot example questions injected into the system prompt')
    parser.add_argument('--case-details-jsonl', default='', help='Optional JSONL path for full per-case predictions and RAG trace')
    parser.add_argument('--temperature', type=float, default=0.0, help='Benchmark model temperature')
    parser.add_argument('--rag-k', type=int, default=2, help='Number of retrieved RAG cases to inject (default: 2)')
    parser.add_argument('--retrieval-mode', default='legacy', choices=['legacy', 'option_grounded', 'option_grounded_hybrid'], help='Retrieval prompt/trace mode')
    parser.add_argument('--option-evidence-k', type=int, default=2, help='Number of option-grounded evidence items per answer option')
    parser.add_argument('--config-id', default=None, help='Optional retrieval ablation config id; persisted into case_details.config_id')
    parser.add_argument('--shuffle-options', action='store_true', help='Randomize option order per case using --shuffle-seed for reproducibility')
    parser.add_argument('--shuffle-seed', type=int, default=None, help='Integer seed required when --shuffle-options is enabled')
    parser.add_argument('--n-samples', type=int, default=1, help='Self-consistency: number of samples per case (default: 1 disables SC)')
    parser.add_argument('--sample-temperature', type=float, default=0.4, help='Sampling temperature used when --n-samples > 1')
    parser.add_argument('--aggregate', default='majority', choices=['majority', 'emit_samples'],
                        help='Aggregation strategy; emit_samples = Phase 6 6A1 逐样本明细（聚合离线）')
    parser.add_argument('--attempt-stage', default='main',
                        help='Phase 6 attempt key 的 attempt_stage（main/anchor/diversity_probe/...）')
    parser.add_argument('--as-of-date', default='',
                        help='v6 高优 7：enrichment 锚定日期，入 resume manifest')
    parser.add_argument('--apb-block', action='store_true', help='Append anti-position-bias instruction to system prompt (Phase 3)')
    parser.add_argument('--phase4-evidence-mode', default='all', choices=['all', 'top2'], help='Phase 4: evidence mode for Stage 2 (all=retrieve all options, top2=top-2 TF-IDF match)')
    parser.add_argument('--phase4-stage1-cache', help='Phase 4: JSON cache path for sharing Stage 1 hypotheses across subprocesses')
    parser.add_argument('--phase4-exp-b', action='store_true', help='Phase 4: Experiment B - skip Stage 1 hypothesis, run Stage 2 with evidence only')
    parser.add_argument('--phase4-exp-a', action='store_true', help='Phase 4: Experiment A - Stage 1 without options, force neutral description')
    parser.add_argument('--phase4-exp-c', action='store_true', help='Phase 4: Experiment C - structured命理 evidence for non-time Stage 2')
    parser.add_argument('--phase4-exp-c2', action='store_true', help='Phase 4: Experiment C2 - per-option scoring evidence for non-time Stage 2')
    parser.add_argument('--phase4-direct-c2', action='store_true', help='Phase 4: inject C2 per-option scoring evidence into direct_choice prompt')
    # Phase 6 五维 profile（profile 是 dataset/prompt_style/interaction_mode/schema/scoring 唯一来源；
    # 不注册 --overwrite：设计 §4.4.3 禁止任何启动路径截断，重跑只能换新 run/slice 目录）
    parser.add_argument('--profile', default=None, help='Phase 6 五维 profile（唯一五维来源）')
    parser.add_argument('--chart-schema-version', default=None, choices=['legacy_v0', 'approved_v1'])
    parser.add_argument('--arm', default=None)
    parser.add_argument('--repeat-idx', type=int, default=0)
    parser.add_argument('--case-ids-file', default=None, help='JSON 数组文件：仅运行其中 case_id')
    parser.add_argument('--resume', action='store_true', help='续跑：跳过已完成 attempt key')
    parser.add_argument('--scheduled-calls', type=int, default=None)
    parser.add_argument('--hard-cap', type=int, default=None)
    parser.add_argument(
        "--thinking-mode",
        choices=("disabled",),
        default=None,
        help="Explicit DeepSeek thinking protocol for controlled experiments",
    )
    parser.add_argument('--ziwei-arm', choices=['none', 'only', 'combined', 'ziwei_mini', 'sequential'],
                        default=None, help='紫微星盘消融臂 (none/only/combined/ziwei_mini/sequential)')
    args = parser.parse_args(argv)

    # 防跨测试/跨调用污染（执行偏离）：每次 main 启动先清空全局 ctx，profile 分支再设真值
    init_phase6_context(None)

    profile = None
    profile_formatter = None
    if args.profile:
        from benchmark.runners.profiles import derive_formatter, resolve_profile
        profile = resolve_profile(args.profile, args.chart_schema_version)
        if profile.dataset == "mingli" and not _mingli_data_ready():
            print(json.dumps({"status": "BLOCKED",
                              "reason": "MingLi 数据前置未完成：先运行 scripts/fetch_mingli_bench.py"},
                             ensure_ascii=False))
            return 4
        args.method = resolve_method(args.profile, args.method)
        # ---- Phase 6 6B1 reasoned arm → ziwei_arm fail-closed mapping ----
        if profile.profile_id == "baziqa_xjz_reasoned":
            _REASONED_ARM_MAP = {
                "b1a_prime": "none",
                "b1b": "only",
                "b1c": "combined",
                "b2b": "ziwei_mini",
                "b2c": "sequential",
            }
            ziwei_arg = getattr(args, "ziwei_arm", None)
            if args.arm not in _REASONED_ARM_MAP:
                print(json.dumps({
                    "status": "BLOCKED",
                    "reason": f"baziqa_xjz_reasoned 要求 arm ∈ {list(_REASONED_ARM_MAP.keys())}，"
                              f"实际 arm={args.arm!r}",
                }, ensure_ascii=False))
                raise SystemExit(2)
            expected_ziwei = _REASONED_ARM_MAP[args.arm]
            if ziwei_arg is None:
                print(json.dumps({
                    "status": "BLOCKED",
                    "reason": f"baziqa_xjz_reasoned arm={args.arm!r} 必须显式传 --ziwei-arm {expected_ziwei}，"
                              f"当前缺失（静默回退 none 已被禁止）",
                }, ensure_ascii=False))
                raise SystemExit(2)
            if ziwei_arg != expected_ziwei:
                print(json.dumps({
                    "status": "BLOCKED",
                    "reason": f"arm={args.arm!r} → 要求 --ziwei-arm {expected_ziwei}，"
                              f"实际 --ziwei-arm={ziwei_arg!r}",
                }, ensure_ascii=False))
                raise SystemExit(2)
        elif profile.profile_id == "baziqa_xjz_dual":
            # dual_system: 内置 bazi/ziwei/judge 三阶段，禁止外部传 --ziwei-arm
            ziwei_arg = getattr(args, "ziwei_arm", None)
            if ziwei_arg is not None:
                print(json.dumps({
                    "status": "BLOCKED",
                    "reason": f"baziqa_xjz_dual 内置三阶段，禁止传 --ziwei-arm；"
                              f"实际 --ziwei-arm={ziwei_arg!r}",
                }, ensure_ascii=False))
                raise SystemExit(2)
        # ---- end fail-closed mapping ----
        profile_formatter = derive_formatter(profile)
        detail_abs = os.path.abspath(args.case_details_jsonl) if args.case_details_jsonl else None
        events_abs = None                                  # detail_abs 为空时保持 None（旧行为）
        if detail_abs:
            manifest_path = (detail_abs[:-6] + ".manifest.json"
                             if detail_abs.endswith(".jsonl")
                             else detail_abs + ".manifest.json")
            events_abs = (detail_abs[:-6] + ".events.jsonl"
                          if detail_abs.endswith(".jsonl")
                          else detail_abs + ".events.jsonl")
            detail_exists = os.path.exists(detail_abs)
            manifest_exists = os.path.exists(manifest_path)
            artifact_exists = (detail_exists or manifest_exists
                               or os.path.exists(events_abs))
            if artifact_exists and not args.resume:
                # 任一运行产物存在（含 --resume 首跑崩溃残留的 manifest/events，此时
                # detail 可能不存在）→ 拒绝；否则 Phase6Context(resume=False) 不恢复
                # events 中的 calls_attempted，会静默重置单切片预算
                print(json.dumps({"status": "ARTIFACT_EXISTS", "detail": detail_abs,
                                  "reason": "已有 Phase 6 运行产物（detail/events/manifest 任一）；"
                                            "必须 --resume 续跑，或换用新的 run/slice 目录重跑"
                                            "（禁止任何启动路径截断，设计 §4.4.3）"},
                                 ensure_ascii=False))
                raise SystemExit(2)
            current_manifest = build_resume_manifest(args, profile)
            if manifest_exists:
                check_resume_manifest(manifest_path, current_manifest)  # 不一致 SystemExit(2)
            elif detail_exists or os.path.exists(events_abs):
                # 旧 detail/events 在而 manifest 缺失（被删或旧版本遗留）→ fail-closed，
                # 不得基于当前配置新建 manifest 混合旧结果
                print(json.dumps({"status": "MANIFEST_MISSING",
                                  "detail": detail_abs, "manifest": manifest_path,
                                  "reason": "detail/events 已存在但 manifest 缺失，无法验证旧结果"
                                            "与当前配置一致，禁止续跑（fail-closed，设计 L168）"},
                                 ensure_ascii=False))
                raise SystemExit(2)
            else:
                _atomic_write_json(manifest_path, current_manifest)     # 三态全无 → 首跑创建（含 --resume 首跑）
        init_phase6_context(Phase6Context(
            dataset_id=os.path.splitext(os.path.basename(args.dataset))[0],
            profile_id=profile.profile_id,
            arm=args.arm, attempt_stage=args.attempt_stage,
            provider=args.provider, model=args.model,
            repeat_idx=args.repeat_idx,
            detail_path=detail_abs,
            events_path=events_abs,
            scheduled_calls=args.scheduled_calls, hard_cap=args.hard_cap,
            resume=args.resume,
            thinking_mode=args.thinking_mode,
        ))
    else:
        args.method = args.method or "direct_choice"
    if args.phase4_exp_c and args.phase4_exp_c2:
        raise ValueError("--phase4-exp-c and --phase4-exp-c2 are mutually exclusive")
    if args.phase4_direct_c2 and args.method != 'direct_choice':
        raise ValueError("--phase4-direct-c2 requires --method direct_choice")
    if (args.phase4_exp_c2 or args.phase4_direct_c2) and os.environ.get('BAZI_FEWSHOT_FILE') and not args.fewshot_file:
        raise ValueError("C2 evaluation requires fewshot=off; clear BAZI_FEWSHOT_FILE or pass an explicit comparable --fewshot-file")

    if args.rag:
        os.environ['BAZI_RAG'] = '1'
        if args.rag_corpus:
            os.environ['BAZI_RAG_CORPUS'] = args.rag_corpus
    if args.fewshot_file:
        os.environ['BAZI_FEWSHOT_FILE'] = args.fewshot_file
    if args.apb_block:
        os.environ['BAZI_APB_BLOCK'] = '1'

    cases = load_jsonl(args.dataset)

    if args.case_ids_file:
        with open(args.case_ids_file, "r", encoding="utf-8") as f:
            wanted = {str(x) for x in json.load(f)}
        cases = [c for c in cases if str(c.get("case_id")) in wanted]
    completed_keys = None
    if args.profile and args.resume:
        completed = load_completed_keys(os.path.abspath(args.case_details_jsonl))
        ctx = _PHASE6_CTX
        if args.aggregate == "emit_samples" or args.method == "dual_system":
            completed_keys = completed      # emit/dual：case 级预过滤会误丢部分完成 case，改按 stage 跳过
        else:
            cases = [c for c in cases if ctx.attempt_key_for(c) not in completed]

    if args.model_runner:
        run_id = str(uuid.uuid4().hex[:8])

        gated_cases = cases
        if profile is not None:
            if not cases:
                # resume 后无剩余 case（全部完成）→ 零调用直接完成（执行偏离：防空跑全链路）
                _write_phase6_summary(args, "OK")
                return 0
            gated_cases = _phase6_visibility_filter(cases, profile, profile_formatter, args)
            if not gated_cases:
                # 全部被可见性门禁 BLOCK：任何模型调用之前短路（裁决 1B，零调用测试锁定）
                _write_phase6_summary(args, "BLOCKED_PRECONDITION")
                return 0

        try:
            model_result = run_model_benchmark(
                gated_cases,
                args.provider,
                args.model,
                args.prompt_version,
                args.max_cases,
                method=args.method,
                temperature=args.temperature,
                case_details_jsonl=args.case_details_jsonl,
                rag_k=args.rag_k,
                config_id=args.config_id,
                retrieval_mode=args.retrieval_mode,
                option_evidence_k=args.option_evidence_k,
                shuffle_options=args.shuffle_options,
                shuffle_seed=args.shuffle_seed,
                n_samples=args.n_samples,
                sample_temperature=args.sample_temperature,
                aggregate=args.aggregate,
                phase4_evidence_mode=args.phase4_evidence_mode,
                phase4_stage1_cache=args.phase4_stage1_cache,
                phase4_exp_b=args.phase4_exp_b,
                phase4_exp_a=args.phase4_exp_a,
                phase4_exp_c=args.phase4_exp_c,
                phase4_exp_c2=args.phase4_exp_c2,
                phase4_direct_c2=args.phase4_direct_c2,
                chart_schema_version=profile.chart_schema_version if profile else None,
                profile_formatter=profile_formatter,
                ziwei_arm=args.ziwei_arm,
                # 执行偏离（Task 6）：计划为 resume_append=args.resume；改为 profile 模式
                # 恒增量——门禁 BLOCK 行先于模型运行写入 detail，_prepare_jsonl 会将其抹掉。
                resume_append=bool(profile),
                completed_keys=completed_keys,
            )
        except _HardCapExhausted:
            _write_phase6_summary(args, "BLOCKED_INCOMPLETE")
            return 3

        model_cases = model_result['cases']
        predictions = model_result['predictions']
        evidence_results = model_result['evidence_results']
        safety_results = model_result['safety_results']
        case_details = model_result['case_details']
        failed_cases = model_result['failed_cases']

        if failed_cases and not predictions and not args.profile:
            # 执行偏离（Task 7）：Phase 6 profile 模式跳过全灭 return 2——call_failed 是
            # 设计 §4.4.2 的合法终态（按错误计入分母），全灭 run 仍以 summary+detail 交付，
            # 退出码 0；非 profile 旧行为不变。
            print(f"Error: all model calls failed ({len(failed_cases)} cases)")
            return 2

        choice_result = score_choice_answers(model_cases, predictions)
        avg_evidence = aggregate_evidence_score(evidence_results)
        avg_safety = aggregate_safety_score(safety_results)

        report_data = {
            "run_id": run_id,
            "dataset": os.path.basename(args.dataset),
            "provider": args.provider,
            "model": args.model,
            "method": args.method,
            "prompt_version": args.prompt_version,
            "reasoning_protocol": "baziqa_srp_v1" if args.method == 'structured_reasoning' else "xuanjizi_srp_v1",
            "choice_accuracy": choice_result,
            "evidence_score": avg_evidence,
            "stability_score": None,
            "safety_score": avg_safety,
            "case_details": case_details,
            "failed_cases": failed_cases,
            "run_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        output_dir = args.output_dir
        if not os.path.isabs(output_dir):
            output_dir = os.path.abspath(output_dir)
        aggregate_json = json.dumps({
            "by_year": choice_result.get("by_year", {}),
            "by_domain": choice_result.get("by_domain", {}),
            "failed_cases": failed_cases,
        }, ensure_ascii=False)

        report_path = save_report(report_data, output_dir)
        print(f"\nReport saved to: {report_path}")
        if not args.profile:
            # 非 profile 旧行为：尾部重写全量 detail；profile 模式 detail 全靠增量 append
            # （门禁 BLOCK 行不在 case_details 中，重写会丢行——执行偏离，计划原为 not args.resume）
            case_details_path = _write_jsonl(args.case_details_jsonl, case_details)
            if case_details_path:
                print(f"Case details JSONL saved to: {case_details_path}")

        data_store.save_benchmark_run(
            id=run_id,
            dataset=os.path.basename(args.dataset),
            provider=args.provider,
            model=args.model,
            method=args.method,
            prompt_version=args.prompt_version,
            reasoning_protocol=report_data['reasoning_protocol'],
            n_cases=len(case_details),
            n_questions=len(case_details),
            accuracy=choice_result['accuracy'],
            evidence_score=avg_evidence,
            stability_score=None,
            safety_score=avg_safety,
            report_path=report_path,
            aggregate_json=aggregate_json,
        )

        print(f"\nBenchmark run saved to database (id={run_id})")

        print("\n" + "="*60)
        print("SUMMARY:")
        print(f"  Total: {choice_result['total']}")
        print(f"  Correct: {choice_result['correct']}")
        print(f"  Accuracy: {round(choice_result['accuracy'] * 100)}%")
        print(f"  AccuracyExact: {choice_result['correct']}/{choice_result['total']}={choice_result['accuracy']:.6f}")
        print(f"  Evidence Coverage: {round(avg_evidence * 100)}%")
        print(f"  Safety Score: {round(avg_safety * 100)}%")
        print("="*60)

        if args.profile:
            _write_phase6_summary(args, "OK")

    else:
        if not args.predictions:
            print("Error: --predictions is required for offline mode")
            return 1

        with open(args.predictions, 'r', encoding='utf-8') as f:
            predictions = json.load(f)
        result = run_offline_benchmark(cases, predictions)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
