import argparse
import json
import os
import sys
import time
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from benchmark.scorers.choice_accuracy import load_jsonl, score_choice_answers
from benchmark.formatters.baziqa_prompt import (
    format_direct_choice_prompt,
    format_structured_reasoning_prompt,
)
from benchmark.scorers.evidence_score import score_case_evidence, aggregate_evidence_score
from benchmark.scorers.safety_score import score_safety, aggregate_safety_score
from benchmark.reports.generate_report import save_report
import data_store


def run_offline_benchmark(cases, predictions):
    return score_choice_answers(cases, predictions)


def build_benchmark_prompt(case, method='direct_choice'):
    if method == 'structured_reasoning':
        return format_structured_reasoning_prompt(case)
    if method in ('direct_choice', 'multi_turn'):
        return format_direct_choice_prompt(case)
    raise ValueError(f"Unsupported benchmark method: {method}")


def call_model_sync(prompt, provider, model):
    try:
        import claude_api
        messages = [{"role": "user", "content": prompt}]
        system_prompt = "你是一位专业命理师，擅长根据八字命盘进行分析。回答选择题时请直接给出选项字母。"

        if provider == "deepseek":
            from claude_api import _call_deepseek
            response = _call_deepseek(messages, system_prompt, model)
        else:
            from claude_api import _call_anthropic
            response = _call_anthropic(messages, system_prompt, model)

        if isinstance(response, dict):
            content = response.get('content', '')
            if isinstance(content, list):
                content = content[0].get('text', '') if content else ''
            return str(content).strip()
        return str(response).strip()
    except Exception as e:
        raise RuntimeError(f"model_call_failed: {type(e).__name__}") from e


def run_model_benchmark(cases, provider, model, prompt_version, max_cases=20, method='direct_choice'):
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
            answer = call_model_sync(prompt, provider, model)
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

        from benchmark.scorers.choice_accuracy import extract_choice
        expected = extract_choice(case.get('answer'))
        predicted = extract_choice(answer)

        case_details.append({
            "case_id": case_id,
            "domain": case.get('domain', 'unknown'),
            "question": case.get('question', '')[:50],
            "expected_answer": expected,
            "predicted_answer": predicted,
            "correct": predicted == expected,
            "evidence_coverage": ev_result.get('coverage', 0.0),
            "safety_score": safe_result.get('score', 0.0),
        })

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
    args = parser.parse_args(argv)

    cases = load_jsonl(args.dataset)

    if args.model_runner:
        run_id = str(uuid.uuid4().hex[:8])

        model_result = run_model_benchmark(
            cases, args.provider, args.model, args.prompt_version, args.max_cases, method=args.method
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
