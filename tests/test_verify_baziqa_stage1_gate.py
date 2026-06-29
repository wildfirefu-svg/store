import json

from scripts import verify_baziqa_stage1_gate as gate


def _summary(**overrides):
    data = {
        "mean": 35,
        "stdev": 2,
        "leak": 20,
        "calls": 100,
        "estimated_calls": 100,
        "stage_cost_cny": 10,
        "stage_budget_cny": 20,
        "cumulative_cost_cny": 10,
    }
    data.update(overrides)
    return gate.normalize_summary(data)


def test_stage1_gate_pass_matrix_case():
    summary = _summary(mean=35, stdev=2, leak=20)
    decision = gate.decide_stage1_gate(summary)
    assert decision == gate.PASS
    assert gate.exit_code_for_decision(decision) == 0


def test_stage1_gate_gray_a_for_mid_mean_or_low_leak():
    summary = _summary(mean=33, stdev=2, leak=10)
    decision = gate.decide_stage1_gate(summary)
    assert decision == gate.GRAY_A
    assert gate.exit_code_for_decision(decision) == 2


def test_stage1_gate_gray_b_when_leak_high_but_mean_below_threshold():
    summary = _summary(mean=32, stdev=2, leak=20)
    decision = gate.decide_stage1_gate(summary)
    assert decision == gate.GRAY_B
    assert gate.exit_code_for_decision(decision) == 2


def test_stage1_gate_gray_b_when_mean_below_three_stdevs():
    summary = _summary(mean=36, stdev=13, leak=20)
    decision = gate.decide_stage1_gate(summary)
    assert decision == gate.GRAY_B
    assert gate.exit_code_for_decision(decision) == 2


def test_stage1_gate_pass_when_mean_exceeds_three_stdevs():
    summary = _summary(mean=36, stdev=10, leak=20)
    decision = gate.decide_stage1_gate(summary)
    assert decision == gate.PASS
    assert gate.exit_code_for_decision(decision) == 0


def test_stage1_gate_rollback_for_low_mean_and_low_leak():
    summary = _summary(mean=20, stdev=2, leak=3)
    decision = gate.decide_stage1_gate(summary)
    assert decision == gate.ROLLBACK
    assert gate.exit_code_for_decision(decision) == 3


def test_stage1_gate_blocked_budget_when_stage_cost_exceeds_guard():
    summary = _summary(mean=40, stdev=2, leak=20, stage_cost_cny=31, stage_budget_cny=20)
    decision = gate.decide_stage1_gate(summary)
    assert decision == gate.BLOCKED_BUDGET
    assert gate.exit_code_for_decision(decision) == 3


def test_stage1_gate_fast_track_for_task_11_and_13_only():
    summary = _summary(mean=36, stdev=1.5, leak=18, executed_tasks=["1.3", "1.1"])
    decision = gate.decide_stage1_gate(summary)
    assert decision == gate.FAST_TRACK
    assert gate.exit_code_for_decision(decision) == 0


def test_stage1_gate_cli_outputs_json_and_exit_code(tmp_path):
    summary_path = tmp_path / "summary.json"
    output_path = tmp_path / "result.json"
    summary_path.write_text(json.dumps({"mean": 0.33, "stdev": 0.02, "leak": 0.1}), encoding="utf-8")

    rc = gate.main(["--summary-json", str(summary_path), "--json", "--output-json", str(output_path)])
    result = json.loads(output_path.read_text(encoding="utf-8"))

    assert rc == 2
    assert result["decision"] == gate.GRAY_A
    assert result["metrics"]["mean"] == 33.0
    assert result["metrics"]["leak"] == 10.0
