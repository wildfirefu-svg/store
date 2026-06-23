import argparse
import json
import os
import sys
import time
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from benchmark.scorers.choice_accuracy import load_jsonl, score_choice_answers, extract_choice, extract_choice_with_meta
from benchmark.formatters.baziqa_prompt import (
    format_direct_choice_prompt,
    format_structured_reasoning_prompt,
    format_multi_turn_context,
    format_multi_turn_question,
)
from benchmark.scorers.evidence_score import score_case_evidence, aggregate_evidence_score
from benchmark.scorers.safety_score import score_safety, aggregate_safety_score
from benchmark.reports.generate_report import save_report
import data_store


SYSTEM_PROMPT_BENCHMARK = (
    "你是一位专业命理师，擅长根据八字命盘进行分析。回答选择题时请直接给出选项字母。"
)


def run_offline_benchmark(cases, predictions):
    return score_choice_answers(cases, predictions)


def build_benchmark_prompt(case, method='direct_choice'):
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


def _resolve_system_prompt(case, rag_k=2):
    fewshot_path = os.environ.get('BAZI_FEWSHOT_FILE') or ''
    fewshot_examples = []
    if fewshot_path:
        try:
            from rag_prompt_builder import load_fewshot_examples
            fewshot_examples = load_fewshot_examples(fewshot_path)
        except Exception:
            fewshot_examples = []

    if os.environ.get('BAZI_RAG') != '1':
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
        )
    except Exception:
        return SYSTEM_PROMPT_BENCHMARK


_BENCH_CASE_INDEX = None


def call_model_sync(prompt, provider, model, case=None, temperature=None, rag_k=2):
    try:
        from claude_api import call_model_messages_sync
        messages = [{"role": "user", "content": prompt}]
        response = call_model_messages_sync(
            messages,
            provider=provider,
            model=model,
            system_prompt=_resolve_system_prompt(case, rag_k=rag_k),
            temperature=temperature,
        )
        return str(response).strip()
    except Exception as e:
        raise RuntimeError(f"model_call_failed: {type(e).__name__}: {str(e)[:120]}") from e


def call_model_messages_with_history(messages, provider, model, case=None, temperature=None, rag_k=2):
    try:
        from claude_api import call_model_messages_sync
        response = call_model_messages_sync(
            messages,
            provider=provider,
            model=model,
            system_prompt=_resolve_system_prompt(case, rag_k=rag_k),
            temperature=temperature,
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


def run_model_benchmark(cases, provider, model, prompt_version, max_cases=20, method='direct_choice', temperature=0.0, case_details_jsonl=None, rag_k=2, config_id=None):
    if method == 'multi_turn':
        return run_multi_turn_benchmark(cases, provider, model, max_cases=max_cases, temperature=temperature, case_details_jsonl=case_details_jsonl, rag_k=rag_k, config_id=config_id)

    _prepare_jsonl(case_details_jsonl)

    predictions = {}
    evidence_results = []
    safety_results = []
    case_details = []
    failed_cases = []

    limited_cases = cases[:max_cases]
    print(f"Running model benchmark on {len(limited_cases)} cases...")

    for i, case in enumerate(limited_cases):
        case_id = case['case_id']
        print(f"  [{i+1}/{len(limited_cases)}] {case_id}")

        prompt = build_benchmark_prompt(case, method=method)
        try:
            answer = call_model_sync(prompt, provider, model, case=case, temperature=temperature, rag_k=rag_k)
        except RuntimeError as e:
            failed_cases.append({'case_id': case_id, 'error': str(e)[:120]})
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
        predicted = meta['choice']
        rag_trace = _resolve_rag_trace(case, k=rag_k)

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
            "rag_trace": rag_trace,
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


def run_multi_turn_benchmark(cases, provider, model, max_cases=20, temperature=0.0, case_details_jsonl=None, rag_k=2, config_id=None):
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
                answer = call_model_messages_with_history(messages, provider, model, case=case, temperature=temperature, rag_k=rag_k)
            except RuntimeError as e:
                failed_cases.append({'case_id': case_id, 'error': str(e)[:120]})
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
                "rag_trace": rag_trace,
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
    parser.add_argument('--provider', default='deepseek', help='deepseek or anthropic')
    parser.add_argument('--model', default='deepseek-v4-pro', help='Model name')
    parser.add_argument('--prompt-version', default='srp_v1', help='Prompt version')
    parser.add_argument('--output-dir', default='benchmark/outputs', help='Report output directory')
    parser.add_argument('--max-cases', type=int, default=20, help='Max cases to run (model mode)')
    parser.add_argument('--method', default='direct_choice', choices=['direct_choice', 'multi_turn', 'structured_reasoning'])
    parser.add_argument('--rag', action='store_true', help='Enable BaziQA case retrieval augmentation (sets BAZI_RAG=1).')
    parser.add_argument('--rag-corpus', default='', help='JSONL corpus file used when --rag is enabled')
    parser.add_argument('--fewshot-file', default='', help='Optional JSONL file with few-shot example questions injected into the system prompt')
    parser.add_argument('--case-details-jsonl', default='', help='Optional JSONL path for full per-case predictions and RAG trace')
    parser.add_argument('--temperature', type=float, default=0.0, help='Benchmark model temperature')
    parser.add_argument('--rag-k', type=int, default=2, help='Number of retrieved RAG cases to inject (default: 2)')
    parser.add_argument('--config-id', default=None, help='Optional retrieval ablation config id; persisted into case_details.config_id')
    args = parser.parse_args(argv)

    if args.rag:
        os.environ['BAZI_RAG'] = '1'
        if args.rag_corpus:
            os.environ['BAZI_RAG_CORPUS'] = args.rag_corpus
    if args.fewshot_file:
        os.environ['BAZI_FEWSHOT_FILE'] = args.fewshot_file

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
