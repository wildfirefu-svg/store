from benchmark.scorers.choice_accuracy import extract_choice, load_jsonl, score_choice_answers


def test_score_choice_answers_counts_accuracy():
    cases = [{'case_id': 'q1', 'answer': 'A'}, {'case_id': 'q2', 'answer': 'B'}]
    preds = {'q1': 'A', 'q2': 'C'}
    result = score_choice_answers(cases, preds)
    assert result['total'] == 2
    assert result['correct'] == 1
    assert result['accuracy'] == 0.5


def test_extract_choice_from_common_answer_text():
    assert extract_choice('A') == 'A'
    assert extract_choice('答案：A') == 'A'
    assert extract_choice('我选择 b') == 'B'
    assert extract_choice('无法判断') is None


def test_score_choice_answers_breaks_down_by_domain():
    cases = [
        {'case_id': 'q1', 'domain': 'career', 'answer': 'A'},
        {'case_id': 'q2', 'domain': 'career', 'answer': 'B'},
        {'case_id': 'q3', 'domain': 'wealth', 'answer': 'C'},
    ]
    preds = {'q1': 'A', 'q2': 'C'}
    result = score_choice_answers(cases, preds)
    assert result['by_domain']['career']['total'] == 2
    assert result['by_domain']['career']['correct'] == 1
    assert result['by_domain']['wealth']['missing'] == 1
    assert result['missing'] == ['q3']


def test_score_choice_answers_reports_invalid_expected_answer():
    cases = [{'case_id': 'bad1', 'domain': 'career', 'answer': 'X'}]
    result = score_choice_answers(cases, {'bad1': 'A'})
    assert result['total'] == 0
    assert result['invalid_cases'] == ['bad1']


def test_baziqa_mini_dataset_format_is_valid():
    cases = load_jsonl('benchmark/datasets/baziqa_mini_v1.jsonl')
    assert len(cases) >= 5
    domains = {c['domain'] for c in cases}
    assert len(domains) >= 3
    for c in cases:
        assert c['case_id']
        assert c['domain']
        assert c['person']['birth']['year']
        assert c['question']
        assert c['options']
        assert c['answer'] in ['A', 'B', 'C', 'D']
