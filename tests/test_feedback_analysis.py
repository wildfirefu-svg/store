#!/usr/bin/env python3
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quality.feedback_analysis import analyze_feedback


def test_analyze_feedback_outputs_required_fields():
    db_path = os.path.join(tempfile.gettempdir(), 'test_feedback_analysis.db')
    if os.path.exists(db_path):
        os.unlink(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('''CREATE TABLE feedback (
            id TEXT PRIMARY KEY,
            analysis_id TEXT NOT NULL,
            dimension TEXT NOT NULL,
            judgment_text TEXT NOT NULL,
            is_accurate INTEGER NOT NULL,
            user_comment TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT ''
        )''')
        conn.executemany(
            'INSERT INTO feedback (id, analysis_id, dimension, judgment_text, is_accurate) VALUES (?, ?, ?, ?, ?)',
            [
                ('f1', 'a1', 'career', '适合专业路线', 1),
                ('f2', 'a1', 'career', '适合创业', 0),
                ('f3', 'a2', 'marriage', '感情稳定', 0),
            ]
        )
        conn.commit()
        result = analyze_feedback(db_path)
        assert 'dimension_accuracy' in result
        assert 'worst_dimensions' in result
        assert 'top_inaccurate_judgments' in result
        assert 'prompt_suggestions' in result
        assert result['dimension_accuracy']['career']['total'] == 2
    finally:
        conn.close()
        if os.path.exists(db_path):
            os.unlink(db_path)
