import json
import sqlite3

import data_store
from benchmark.runners.import_dataset import import_dataset


def test_import_dataset_updates_questions_for_existing_cases(tmp_path, monkeypatch):
    db = tmp_path / 'benchmark_import.db'
    monkeypatch.setattr(data_store, 'DB_PATH', str(db))
    data_store.init_db()

    dataset = tmp_path / 'cases.jsonl'
    case = {
        'case_id': 'case_import_001',
        'person': {'name': '命主001', 'gender': 'male', 'birth': {'year': 1990, 'month': 1, 'day': 1, 'hour': 12}},
        'domain': 'career',
        'question': '事业如何？',
        'options': ['A', 'B', 'C', 'D'],
        'answer': 'A',
        'expected_evidence': ['官星'],
        'difficulty': 'easy',
    }
    dataset.write_text(json.dumps(case, ensure_ascii=False) + '\n', encoding='utf-8')

    cases, questions = import_dataset(str(dataset))
    assert cases == 1
    assert questions == 1
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM benchmark_questions WHERE id = ?", ('q_case_import_001',))
    conn.commit()
    conn.close()
    cases, questions = import_dataset(str(dataset))
    assert cases == 0
    assert questions == 1
    assert data_store.get_benchmark_question('q_case_import_001') is not None
