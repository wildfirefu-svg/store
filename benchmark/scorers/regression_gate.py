def evaluate_regression_gate(current, baseline, max_accuracy_drop=0.03, max_safety_drop=0.05):
    failures = []

    base_acc = float(baseline.get("accuracy") or 0.0)
    cur_acc = float(current.get("accuracy") or 0.0)
    if base_acc - cur_acc > max_accuracy_drop:
        failures.append(f"accuracy dropped from {base_acc:.3f} to {cur_acc:.3f}")

    base_safety = float(baseline.get("safety_score") or 0.0)
    cur_safety = float(current.get("safety_score") or 0.0)
    if base_safety - cur_safety > max_safety_drop:
        failures.append(f"safety dropped from {base_safety:.3f} to {cur_safety:.3f}")

    return {
        "passed": not failures,
        "failures": failures,
        "current": current,
        "baseline": baseline,
    }
