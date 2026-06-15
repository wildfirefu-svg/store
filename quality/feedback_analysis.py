#!/usr/bin/env python3
import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, 'bazi_data.db')


def analyze_feedback(db_path=DEFAULT_DB):
    if not os.path.exists(db_path):
        return {
            'dimension_accuracy': {},
            'worst_dimensions': [],
            'top_inaccurate_judgments': [],
            'prompt_suggestions': [],
        }
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        dimension_accuracy = _dimension_accuracy(conn)
        worst_dimensions = sorted(
            dimension_accuracy.items(),
            key=lambda item: (item[1]['accuracy'], -item[1]['total'])
        )[:5]
        top_inaccurate_judgments = _top_inaccurate_judgments(conn)
        prompt_suggestions = [
            f"维度 {dimension} 准确率偏低，建议补充该维度的反证据和 Few-shot 案例。"
            for dimension, _stats in worst_dimensions
        ]
        return {
            'dimension_accuracy': dimension_accuracy,
            'worst_dimensions': [{'dimension': d, **stats} for d, stats in worst_dimensions],
            'top_inaccurate_judgments': top_inaccurate_judgments,
            'prompt_suggestions': prompt_suggestions,
        }
    finally:
        conn.close()


def _dimension_accuracy(conn):
    rows = conn.execute(
        '''SELECT dimension, COUNT(*) AS total, SUM(is_accurate) AS accurate
           FROM feedback GROUP BY dimension'''
    ).fetchall()
    result = {}
    for row in rows:
        total = row['total'] or 0
        accurate = row['accurate'] or 0
        result[row['dimension']] = {
            'total': total,
            'accurate': accurate,
            'inaccurate': total - accurate,
            'accuracy': round(accurate / total, 3) if total else 0,
        }
    return result


def _top_inaccurate_judgments(conn):
    rows = conn.execute(
        '''SELECT dimension, judgment_text, COUNT(*) AS count
           FROM feedback
           WHERE is_accurate = 0
           GROUP BY dimension, judgment_text
           ORDER BY count DESC, dimension ASC
           LIMIT 10'''
    ).fetchall()
    return [dict(row) for row in rows]


def main():
    print(json.dumps(analyze_feedback(DEFAULT_DB), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
