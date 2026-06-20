from scripts.build_domain_action_plan import build_actions, render_report


def test_build_actions_flags_low_accuracy_domains():
    summary = {
        "domain_summary": [
            {"domain": "health", "total": 5, "correct": 1, "accuracy": 0.2},
            {"domain": "career", "total": 8, "correct": 4, "accuracy": 0.5},
            {"domain": "study", "total": 1, "correct": 0, "accuracy": 0.0},
        ]
    }
    actions = build_actions(summary, min_cases=3, threshold=0.25)
    assert actions == [{
        "domain": "health",
        "total": 5,
        "accuracy": 0.2,
        "action": "add_domain_rules_and_examples",
    }]


def test_render_report_contains_domain_actions():
    text = render_report([{
        "domain": "health",
        "total": 5,
        "accuracy": 0.2,
        "action": "add_domain_rules_and_examples",
    }])
    assert "| health | 5 | 20.0% | add_domain_rules_and_examples |" in text
