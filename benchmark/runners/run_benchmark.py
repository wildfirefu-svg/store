import argparse
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
from benchmark.scorers.evidence_score import score_case_evidence, aggregate_evidence_score
from benchmark.scorers.safety_score import score_safety, aggregate_safety_score
from benchmark.reports.generate_report import save_report
from benchmark.phase3 import to_original_option_identity, classify_parser_failure
import data_store


SYSTEM_PROMPT_BENCHMARK = (
    "你是一位专业命理师，擅长根据八字命盘进行分析。回答选择题时请直接给出选项字母。"
)


def run_offline_benchmark(cases, predictions):
    return score_choice_answers(cases, predictions)


def build_benchmark_prompt(case, method='direct_choice', phase4_exp_a=False):
    if method == 'two_stage_reasoning':
        return format_stage1_prompt(case, exp_a=phase4_exp_a)
    if method == 'structured_reasoning':
        return format_structured_reasoning_prompt(case)
    if method in ('direct_choice', 'multi_turn'):
        return format_direct_choice_prompt(case)
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


def call_model_sync(prompt, provider, model, case=None, temperature=None, timeout=300, rag_k=2, retrieval_mode='legacy', option_evidence_k=2, suppress_rag=False, suppress_apb=False):
    try:
        from claude_api import call_model_messages_sync
        messages = [{"role": "user", "content": prompt}]
        response = call_model_messages_sync(
            messages,
            provider=provider,
            model=model,
            system_prompt=_resolve_system_prompt(case, rag_k=rag_k, retrieval_mode=retrieval_mode, option_evidence_k=option_evidence_k, suppress_rag=suppress_rag, suppress_apb=suppress_apb),
            temperature=temperature,
            timeout=timeout,
        )
        return str(response).strip()
    except Exception as e:
        raise RuntimeError(f"model_call_failed: {type(e).__name__}: {str(e)[:120]}") from e


def call_model_messages_with_history(messages, provider, model, case=None, temperature=None, timeout=300, rag_k=2, retrieval_mode='legacy', option_evidence_k=2, suppress_rag=False, suppress_apb=False):
    try:
        from claude_api import call_model_messages_sync
        response = call_model_messages_sync(
            messages,
            provider=provider,
            model=model,
            system_prompt=_resolve_system_prompt(case, rag_k=rag_k, retrieval_mode=retrieval_mode, option_evidence_k=option_evidence_k, suppress_rag=suppress_rag, suppress_apb=suppress_apb),
            temperature=temperature,
            timeout=timeout,
        )
        return str(response).strip()
    except Exception as e:
        raise RuntimeError(f"model_call_failed: {type(e).__name__}: {str(e)[:120]}") from e


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


def run_model_benchmark(cases, provider, model, prompt_version, max_cases=20, method='direct_choice', temperature=0.0, case_details_jsonl=None, rag_k=2, config_id=None, retrieval_mode='legacy', option_evidence_k=2, shuffle_options=False, shuffle_seed=None, n_samples=1, sample_temperature=0.4, aggregate='majority', phase4_evidence_mode='all', phase4_stage1_cache=None, phase4_exp_b=False, phase4_exp_a=False, phase4_exp_c=False, phase4_exp_c2=False, phase4_direct_c2=False):
    if method == 'multi_turn':
        return run_multi_turn_benchmark(cases, provider, model, max_cases=max_cases, temperature=temperature, case_details_jsonl=case_details_jsonl, rag_k=rag_k, config_id=config_id, retrieval_mode=retrieval_mode, option_evidence_k=option_evidence_k)
    if phase4_exp_c and phase4_exp_c2:
        raise ValueError("run_model_benchmark: --phase4-exp-c and --phase4-exp-c2 are mutually exclusive")
    if phase4_direct_c2 and method != 'direct_choice':
        raise ValueError("run_model_benchmark: --phase4-direct-c2 requires --method direct_choice")
    runtime_config = _phase4_runtime_config(provider, model, prompt_version, rag_k, retrieval_mode, option_evidence_k)

    if not isinstance(n_samples, int) or n_samples < 1:
        raise ValueError(f"run_model_benchmark: n_samples must be a positive int, got {n_samples!r}")
    if aggregate not in {"majority"}:
        raise ValueError(f"run_model_benchmark: aggregate {aggregate!r} is not supported (expected 'majority')")

    if shuffle_options:
        if shuffle_seed is None:
            raise ValueError("run_model_benchmark: shuffle_options=True requires an explicit int shuffle_seed")
        cases = [
            _shuffle_options_fn(case, seed=shuffle_seed + idx)
            for idx, case in enumerate(cases)
        ]

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
            prompt = build_benchmark_prompt(case, method=method, phase4_exp_a=phase4_exp_a)

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


def run_multi_turn_benchmark(cases, provider, model, max_cases=20, temperature=0.0, case_details_jsonl=None, rag_k=2, config_id=None, retrieval_mode='legacy', option_evidence_k=2):
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
    parser.add_argument('--method', default='direct_choice', choices=['direct_choice', 'multi_turn', 'structured_reasoning', 'two_stage_reasoning'])
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
    parser.add_argument('--aggregate', default='majority', choices=['majority'], help='Aggregation strategy over samples')
    parser.add_argument('--apb-block', action='store_true', help='Append anti-position-bias instruction to system prompt (Phase 3)')
    parser.add_argument('--phase4-evidence-mode', default='all', choices=['all', 'top2'], help='Phase 4: evidence mode for Stage 2 (all=retrieve all options, top2=top-2 TF-IDF match)')
    parser.add_argument('--phase4-stage1-cache', help='Phase 4: JSON cache path for sharing Stage 1 hypotheses across subprocesses')
    parser.add_argument('--phase4-exp-b', action='store_true', help='Phase 4: Experiment B - skip Stage 1 hypothesis, run Stage 2 with evidence only')
    parser.add_argument('--phase4-exp-a', action='store_true', help='Phase 4: Experiment A - Stage 1 without options, force neutral description')
    parser.add_argument('--phase4-exp-c', action='store_true', help='Phase 4: Experiment C - structured命理 evidence for non-time Stage 2')
    parser.add_argument('--phase4-exp-c2', action='store_true', help='Phase 4: Experiment C2 - per-option scoring evidence for non-time Stage 2')
    parser.add_argument('--phase4-direct-c2', action='store_true', help='Phase 4: inject C2 per-option scoring evidence into direct_choice prompt')
    args = parser.parse_args(argv)
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

    if args.model_runner:
        run_id = str(uuid.uuid4().hex[:8])

        model_result = run_model_benchmark(
            cases,
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
        )

        model_cases = model_result['cases']
        predictions = model_result['predictions']
        evidence_results = model_result['evidence_results']
        safety_results = model_result['safety_results']
        case_details = model_result['case_details']
        failed_cases = model_result['failed_cases']

        if failed_cases and not predictions:
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
