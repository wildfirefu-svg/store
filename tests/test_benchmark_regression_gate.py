from benchmark.scorers.regression_gate import evaluate_regression_gate


def test_regression_gate_passes_for_improvement():
    baseline = {"accuracy": 0.35, "safety_score": 0.9}
    current = {"accuracy": 0.38, "safety_score": 0.92}

    result = evaluate_regression_gate(current, baseline)

    assert result["passed"] is True
    assert result["failures"] == []


def test_regression_gate_fails_for_accuracy_drop():
    baseline = {"accuracy": 0.40, "safety_score": 0.9}
    current = {"accuracy": 0.34, "safety_score": 0.91}

    result = evaluate_regression_gate(current, baseline, max_accuracy_drop=0.03)

    assert result["passed"] is False
    assert any("accuracy" in item for item in result["failures"])


def test_regression_gate_fails_for_safety_drop():
    baseline = {"accuracy": 0.40, "safety_score": 0.95}
    current = {"accuracy": 0.41, "safety_score": 0.80}

    result = evaluate_regression_gate(current, baseline, max_safety_drop=0.05)

    assert result["passed"] is False
    assert any("safety" in item for item in result["failures"])
