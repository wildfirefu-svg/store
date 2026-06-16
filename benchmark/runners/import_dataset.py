import argparse
import json
import os
import sys

if __package__ in (None, ''):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from benchmark.scorers.choice_accuracy import load_jsonl
import data_store


def import_dataset(jsonl_path):
    cases = load_jsonl(jsonl_path)
    imported_cases = 0
    imported_questions = 0

    for case in cases:
        case_id = case['case_id']
        person = case['person']
        birth = person.get('birth', {})

        profile_json = json.dumps({
            'name': person.get('name', ''),
            'gender': person.get('gender', ''),
            'birth_year': birth.get('year'),
            'birth_month': birth.get('month'),
            'birth_day': birth.get('day'),
            'birth_hour': birth.get('hour'),
            'birth_minute': birth.get('minute', 0),
            'birth_place': birth.get('place', ''),
        }, ensure_ascii=False)

        chart_input_json = json.dumps(birth, ensure_ascii=False)

        existing = data_store.get_benchmark_case(case_id)
        if existing:
            print(f"Skipping existing case: {case_id}")
            continue

        data_store.save_benchmark_case(
            id=case_id,
            source='baziqa_mini',
            person_id=f"person_{case_id}",
            name=person.get('name', ''),
            profile_json=profile_json,
            chart_input_json=chart_input_json,
            chart_result_json='{}',
            verified_events_json='[]',
            anonymized=1,
            license_note='Internal BaziQA Mini Dataset',
        )
        imported_cases += 1

        question_id = f"q_{case_id}"
        options_json = json.dumps(case.get('options', []), ensure_ascii=False)
        expected_evidence_json = json.dumps(case.get('expected_evidence', []), ensure_ascii=False)

        existing_q = data_store.get_benchmark_question(question_id)
        if not existing_q:
            data_store.save_benchmark_question(
                id=question_id,
                case_id=case_id,
                domain=case.get('domain', 'unknown'),
                question=case.get('question', ''),
                options_json=options_json,
                answer=case.get('answer', ''),
                expected_evidence_json=expected_evidence_json,
                difficulty=case.get('difficulty', 'medium'),
            )
            imported_questions += 1

    return imported_cases, imported_questions


def main(argv=None):
    parser = argparse.ArgumentParser(description='Import BaziQA JSONL dataset into SQLite')
    parser.add_argument('jsonl_path', help='Path to JSONL dataset file')
    args = parser.parse_args(argv)

    if not os.path.exists(args.jsonl_path):
        print(f"Error: File not found - {args.jsonl_path}")
        return 1

    cases, questions = import_dataset(args.jsonl_path)
    print(f"Imported: {cases} cases, {questions} questions")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
