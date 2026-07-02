from benchmark.reports.accuracy_stats import summarize_accuracy


def test_summarize_accuracy_computes_mean_min_max_and_spread():
    rows = [
        {"label": "rag-structured", "accuracy": 0.30},
        {"label": "rag-structured", "accuracy": 0.40},
        {"label": "rag-structured", "accuracy": 0.50},
    ]

    summary = summarize_accuracy(rows)
    stats = summary["rag-structured"]

    assert stats["runs"] == 3
    assert round(stats["mean"], 6) == 0.4
    assert stats["min"] == 0.3
    assert stats["max"] == 0.5
    assert round(stats["stdev"], 6) == 0.1


def test_summarize_accuracy_groups_multiple_labels():
    rows = [
        {"label": "baseline", "accuracy": 0.20},
        {"label": "rag", "accuracy": 0.35},
    ]

    summary = summarize_accuracy(rows)

    assert summary["baseline"]["mean"] == 0.2
    assert summary["rag"]["mean"] == 0.35
