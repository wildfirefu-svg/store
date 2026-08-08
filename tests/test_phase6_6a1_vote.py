from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase6_6a1_ablation import (
    ANCHOR_CAPS,
    PROFILE_ID,
    VoteConfig,
    aggregate_metrics,
    build_main_schedule,
    cost_metrics,
    diversity_rate,
    evaluate_t_switch,
    gate_verdict,
    load_dev_temperature,
    probe_rows_complete,
    run_vote,
    sha256_file,
    strict_rows_complete,
    validate_case_ids,
)
from scripts.run_phase6_6a1_ablation import (
    main as vote_main,
)
from tests.phase6_helpers import RunnerSpy

CASE_IDS = [f"c{i}" for i in range(40)]
PROBE_IDS = [f"c{i}" for i in range(10)]


def fake_vote_config(**overrides):
    base = dict(run_id="t", year=2024, root=Path(".tmp/x"), enriched_path=Path("e.jsonl"))
    base.update(overrides)
    return VoteConfig(**base)


def srow(case_id, repeat, sample_idx, letter, arm="vote5_samples", terminal="parsed"):
    """构造采样/锚定行（真实行形状：臂/repeat/sample 在 attempt_key 内）。"""
    stage = {"vote5_samples": "main", "anchor_single0": "anchor"}[arm]
    return {"case_id": case_id, "correct": letter == "B",
            "expected_answer": "B", "predicted_answer": letter,
            "terminal_state": terminal,
            "attempt_key": ["ds", PROFILE_ID, arm, stage, "deepseek", "deepseek-chat",
                            case_id, repeat, sample_idx, "p0"]}


def probe_row(case_id, sample_idx, letter, arm="probe_r1", terminal="parsed"):
    """v5 阻断 2：构造 probe 行（arm=probe_r1/probe_r2、stage=diversity_probe、repeat_idx=-1）。
    srow 只支持 vote5_samples/anchor_single0，probe 测试必须用本 fixture。"""
    assert arm in ("probe_r1", "probe_r2")
    return {"case_id": case_id, "correct": letter == "B",
            "expected_answer": "B", "predicted_answer": letter,
            "terminal_state": terminal,
            "attempt_key": ["ds", PROFILE_ID, arm, "diversity_probe", "deepseek",
                            "deepseek-chat", case_id, -1, sample_idx, "p0"]}


class TestDiversity:
    def test_rate_and_switch_decision(self):
        # 6/10 题 ≥2 个不同合法选项 → 0.6 → 冻结 0.4，不跑 r2
        rows = []
        for i in range(10):
            letters = ["A", "A", "B", "A", "A"] if i < 6 else ["A"] * 5
            for j, L in enumerate(letters):
                rows.append(probe_row(f"c{i}", j, L))
        assert diversity_rate(rows, PROBE_IDS) == 0.6
        assert evaluate_t_switch(0.6, None) == ("freeze", 0.4)
        assert evaluate_t_switch(0.5, None) == ("probe_r2", 0.4)
        assert evaluate_t_switch(0.5, 0.7) == ("freeze", 1.0)
        assert evaluate_t_switch(0.5, 0.4) == ("freeze_low_diversity", 1.0)

    def test_invalid_not_counted_as_second_option(self):
        # 4×A(parsed) + 1 条 call_failed -> None 不算第二选项（v2 阻断 4）-> 0 diverse / 10 题分母 = 0.0
        rows = []
        for i in range(10):
            for j in range(4):
                rows.append(probe_row(f"c{i}", j, "A"))
            rows.append(probe_row(f"c{i}", 4, None, terminal="call_failed"))
        assert diversity_rate(rows, PROBE_IDS) == 0.0

    def test_all_invalid_stays_in_denominator(self):
        """v3 阻断 2：6 diverse + 4 all-invalid -> 0.6（全 invalid 题保留分母，而非 6/6=1.0）。"""
        rows = []
        for i in range(10):
            if i < 6:
                for j, L in enumerate(["A", "A", "B", "A", "A"]):
                    rows.append(probe_row(f"c{i}", j, L))
            else:
                for j in range(5):
                    rows.append(probe_row(f"c{i}", j, None, terminal="call_failed"))
        assert diversity_rate(rows, PROBE_IDS) == 0.6

    def test_probe_completeness_required(self):
        # v5 阻断 1+2：probe_row + expected_arm；不足 10 题/重复 sample_idx/缺样本 -> 不完整
        with pytest.raises(ValueError, match="不完整"):
            probe_rows_complete([probe_row(f"c{i}", j, "A") for i in range(9) for j in range(5)],
                                PROBE_IDS, "probe_r1")
        with pytest.raises(ValueError, match="不完整"):
            probe_rows_complete([probe_row(f"c{i}", j, "A") for i in range(10) for j in [0, 0, 1, 2, 3]],
                                PROBE_IDS, "probe_r1")
        with pytest.raises(ValueError, match="不完整"):
            probe_rows_complete([probe_row(f"c{i}", j, "A") for i in range(10) for j in [0, 1, 2, 3]],
                                PROBE_IDS, "probe_r1")
        probe_rows_complete([probe_row(f"c{i}", j, "A") for i in range(10) for j in range(5)],
                            PROBE_IDS, "probe_r1")


class TestSchedule:
    def test_main_schedule_order_and_caps(self):
        sched = build_main_schedule(fake_vote_config(), CASE_IDS)
        assert len(sched) == 12
        seq = [(s.arm, s.group) for s in sched[:4]]
        assert seq == [("vote5_samples", "group_a"), ("anchor_single0", "group_a"),
                       ("anchor_single0", "group_b"), ("vote5_samples", "group_b")]
        assert sum(s.hard_cap for s in sched) == 660 + sum(ANCHOR_CAPS)
        assert sum(s.scheduled_calls for s in sched) == 720
        sample = [s for s in sched if s.arm == "vote5_samples"][0]
        anchor = [s for s in sched if s.arm == "anchor_single0"][0]
        assert (sample.n_samples, sample.temperature) == (5, 0.4)
        assert (anchor.n_samples, anchor.temperature) == (1, 0.0)
        assert sample.stage == "main" and anchor.stage == "anchor"

    def test_schedule_requires_40(self):
        with pytest.raises(ValueError):
            build_main_schedule(fake_vote_config(), CASE_IDS[:39])

    def test_schedule_requires_unique_case_ids(self):
        # 40 个 case_id 但有重复 → 拒绝（审核高优 7c）
        dup = CASE_IDS[:39] + ["c0"]
        with pytest.raises(ValueError, match="唯一"):
            build_main_schedule(fake_vote_config(), dup)


def _full_rows(per_repeat_correct_v5, per_repeat_correct_s0):
    """构造 40 题 × 3 repeats：采样臂每题 5 行（3B2A → vote5 恒 B）+ 锚定行。"""
    rows = []
    for rep in range(3):
        for i in range(40):
            cid = f"c{i}"
            v5_win = i < per_repeat_correct_v5[rep]
            letters = ["B", "B", "B", "A", "A"] if v5_win else ["A", "A", "A", "B", "B"]
            for j, L in enumerate(letters):
                rows.append(srow(cid, rep, j, L))
            rows.append(srow(cid, rep, 0, "B" if i < per_repeat_correct_s0[rep] else "A",
                             arm="anchor_single0"))
    return rows


class TestCompleteness:
    """审核阻断 2：完整性全量断言；任一异常 → ValueError（上层映射 BLOCKED_INCOMPLETE）。"""

    def test_full_ok(self):
        strict_rows_complete(_full_rows([40, 40, 40], [35, 35, 35]), CASE_IDS, 3)

    def test_missing_case(self):
        rows = [r for r in _full_rows([40, 40, 40], [35, 35, 35]) if r["case_id"] != "c0"]
        with pytest.raises(ValueError, match="不完整"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_missing_anchor(self):
        rows = [r for r in _full_rows([40, 40, 40], [35, 35, 35])
                if not (r["case_id"] == "c0" and r["attempt_key"][7] == 0
                        and r["attempt_key"][2] == "anchor_single0")]
        with pytest.raises(ValueError, match="不完整"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_duplicate_sample(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows.append(srow("c0", 0, 0, "B"))
        with pytest.raises(ValueError, match="重复"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_extra_repeat(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows.append(srow("c0", 5, 0, "B"))
        with pytest.raises(ValueError, match="额外 repeat"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_extra_case(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows.append(srow("c99", 0, 0, "B"))
        with pytest.raises(ValueError, match="额外 case"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_unknown_arm(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        bad = srow("c0", 0, 0, "B")
        bad["attempt_key"][2] = "mystery_arm"
        rows.append(bad)
        with pytest.raises(ValueError, match="未知 arm"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_bad_terminal_state(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows[0]["terminal_state"] = "weird"
        with pytest.raises(ValueError, match="终态"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_extra_anchor_sample_idx_rejected(self):
        """v3 中优 4：anchor sample_idx != 0 直接拒绝（不允许 0..4）。"""
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows.append(srow("c0", 0, 1, "B", arm="anchor_single0"))   # anchor idx=1
        with pytest.raises(ValueError, match="anchor"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_extra_sample_set_rejected(self):
        """v3 中优 4：额外 sample 行（超范围 idx）也拒绝，不只检查缺失。"""
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        rows.append(srow("c0", 0, 5, "B"))   # sample_idx=5 超范围
        with pytest.raises(ValueError, match="sample_idx|额外"):
            strict_rows_complete(rows, CASE_IDS, 3)

    def test_aggregate_blocked_on_incomplete(self):
        rows = [r for r in _full_rows([40, 40, 40], [35, 35, 35]) if r["case_id"] != "c0"]
        with pytest.raises(ValueError, match="不完整"):
            aggregate_metrics(rows, CASE_IDS, repeats=3)


class TestAggregate:
    def test_metrics_and_verdict_promote(self):
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        m = aggregate_metrics(rows, CASE_IDS, repeats=3)
        assert m["acc"]["vote5"] == [1.0, 1.0, 1.0]
        assert m["acc"]["single_t"] == [1.0, 1.0, 1.0]
        assert m["acc"]["anchor"] == [0.875, 0.875, 0.875]
        assert m["delta1_pp"] == 0.0 and m["delta2_pp"] == 12.5
        assert m["unresolved_rate"] == 0.0
        assert gate_verdict(3.0, 0.0) == "PROMOTE_CANDIDATE"
        assert gate_verdict(3.0, -0.5) == "AGGREGATION_EFFECT_ONLY"
        assert gate_verdict(2.9, 5.0) == "NON_INFERIOR"
        assert gate_verdict(-3.0, 0.0) == "ROLLBACK"
        assert gate_verdict(0.0, 5.0) == "NON_INFERIOR"

    def test_unresolved_counts_wrong_and_rate(self):
        rows = []
        for rep in range(3):
            for i in range(40):
                for j, L in enumerate(["B", "B", "A", "A", "C"]):
                    rows.append(srow(f"c{i}", rep, j, L))
                rows.append(srow(f"c{i}", rep, 0, "B", arm="anchor_single0"))
        m = aggregate_metrics(rows, CASE_IDS, repeats=3)
        assert m["acc"]["vote5"] == [0.0, 0.0, 0.0]
        assert m["unresolved_rate"] == 1.0
        assert m["delta1_pp"] == -100.0

    def test_no_cross_repeat_aggregation(self):
        rows = []
        for rep in range(3):
            win = rep == 0
            for i in range(40):
                letters = ["B", "B", "B", "A", "A"] if win else ["A", "A", "A", "B", "B"]
                for j, L in enumerate(letters):
                    rows.append(srow(f"c{i}", rep, j, L))
                rows.append(srow(f"c{i}", rep, 0, "B" if win else "A", arm="anchor_single0"))
        m = aggregate_metrics(rows, CASE_IDS, repeats=3)
        assert m["acc"]["vote5"] == [1.0, 0.0, 0.0]
        assert m["per_repeat_delta1"] == [0.0, 0.0, 0.0]
        assert m["delta1_pp"] == 0.0

    def test_four_grid(self):
        m = aggregate_metrics(_full_rows([40, 40, 40], [35, 35, 35]), CASE_IDS, repeats=3)
        assert m["four_grid_vote5_vs_anchor"] == {"both": 105, "vote5_only": 15,
                                                  "anchor_only": 0, "neither": 0}

    def test_case_records_fields(self):
        # 首类指标（审核高优 5）：逐题明细 5 票/vote5/single@T/anchor/correct/unresolved
        m = aggregate_metrics(_full_rows([40, 40, 40], [35, 35, 35]), CASE_IDS, repeats=3)
        recs = m["case_records"]
        assert len(recs) == 120
        r0 = next(r for r in recs if r["case_id"] == "c0" and r["repeat_idx"] == 0)
        assert len(r0["votes"]) == 5
        assert r0["vote5"] == "B" and r0["single_t"] == "B" and r0["anchor"] == "B"
        assert r0["expected"] == "B" and r0["unresolved"] is False
        assert r0["vote5_correct"] is True
        bad = next(r for r in recs if r["case_id"] == "c39" and r["repeat_idx"] == 0)
        assert bad["anchor"] == "A" and bad["anchor_correct"] is False

    def test_acc_trimmed_mean_field(self):
        """v3 中优 5：三臂 repeat 准确率的 trimmed_mean 附列（不入 gate，设计 §2.1）。"""
        m = aggregate_metrics(_full_rows([40, 40, 40], [35, 35, 35]), CASE_IDS, repeats=3)
        assert set(m["acc_trimmed_mean"].keys()) == {"vote5", "single_t", "anchor"}
        # vote5 = [1.0, 1.0, 1.0]，trimmed_mean(0.1) 截尾后仍 1.0
        assert m["acc_trimmed_mean"]["vote5"] == 1.0
        assert m["acc_trimmed_mean"]["anchor"] == 0.875

    def test_by_domain_metrics(self):
        """v3 中优 5：by_domain 输出每个 domain 的三臂准确率及 Δ（设计 §2.1）。"""
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        for r in rows:
            r["domain"] = "d0" if int(r["case_id"][1:]) < 20 else "d1"
        m = aggregate_metrics(rows, CASE_IDS, repeats=3)
        bd = m["by_domain"]
        assert set(bd.keys()) == {"d0", "d1"}
        # d0=c0-c19：vote5 全对，anchor 全对（i<35）
        assert bd["d0"]["vote5"] == 1.0
        assert bd["d0"]["anchor"] == 1.0
        # d1=c20-c39：vote5 全对，anchor c20-c34 对(15)/c35-c39 错(5) -> 0.75
        assert bd["d1"]["vote5"] == 1.0
        assert bd["d1"]["anchor"] == 0.75


class TestAuditRecompute:
    """v3 阻断 1：审计复算必须是题级投票 + 独立完整性检查 + 与归档 summary 自动比对。"""

    def test_recompute_vote_accuracy(self):
        from scripts.build_phase6_audit_index import recompute_vote_accuracy
        out = recompute_vote_accuracy(_full_rows([40, 40, 40], [35, 35, 35]), CASE_IDS, repeats=3)
        assert out["acc"]["vote5"] == [1.0, 1.0, 1.0]
        assert out["acc"]["single_t"] == [1.0, 1.0, 1.0]
        assert out["acc"]["anchor"] == [0.875, 0.875, 0.875]
        assert out["delta1_pp"] == 0.0 and out["delta2_pp"] == 12.5
        assert out["unresolved"] == 0

    def test_recompute_differs_from_per_row(self):
        # 按行统计会把 vote5 的 3B2A 样本算成 60%，题级投票是 100%——两者必须区分
        from scripts.build_phase6_audit_index import (
            recompute_accuracy,
            recompute_vote_accuracy,
        )
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        vote = recompute_vote_accuracy(rows, CASE_IDS, repeats=3)
        per_row = recompute_accuracy(rows, arms=("vote5_samples", "anchor_single0"))
        assert vote["acc"]["vote5"] == [1.0, 1.0, 1.0]
        assert per_row["per_arm"]["vote5_samples"][0]["accuracy"] == 0.6

    def test_recompute_rejects_incomplete_rows(self):
        """v3 阻断 1：缺整题/缺 anchor/重复行 -> ValueError，不静默缩小分母。"""
        from scripts.build_phase6_audit_index import recompute_vote_accuracy
        full = _full_rows([40, 40, 40], [35, 35, 35])
        # 缺整题（c0 两臂全丢）
        with pytest.raises(ValueError, match="不完整|缺失"):
            recompute_vote_accuracy([r for r in full if r["case_id"] != "c0"], CASE_IDS, repeats=3)
        # 缺 anchor（c0 的 anchor 行丢，sample 保留）
        with pytest.raises(ValueError, match="不完整|缺失"):
            recompute_vote_accuracy([r for r in full if not (r["case_id"] == "c0"
                and r["attempt_key"][2] == "anchor_single0")], CASE_IDS, repeats=3)
        # 重复 sample 行
        dup = full + [srow("c0", 0, 0, "B")]
        with pytest.raises(ValueError, match="重复"):
            recompute_vote_accuracy(dup, CASE_IDS, repeats=3)

    def test_check_summary_match(self, tmp_path):
        """v3 阻断 1：审计复算与归档 summary.json 自动比对，不一致返回 False。"""
        from scripts.build_phase6_audit_index import (
            check_summary_match,
            recompute_vote_accuracy,
        )
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        recomputed = recompute_vote_accuracy(rows, CASE_IDS, repeats=3)
        bad = tmp_path / "summary.json"
        bad.write_text(json.dumps({"delta1_pp": 99.9, "delta2_pp": 12.5,
            "acc": recomputed["acc"], "unresolved": 0}), encoding="utf-8")
        assert not check_summary_match(recomputed, bad)
        good = tmp_path / "summary.json"
        good.write_text(json.dumps({"delta1_pp": 0.0, "delta2_pp": 12.5,
            "acc": recomputed["acc"], "unresolved_rate": 0.0,
            "unresolved": 0}), encoding="utf-8")
        assert check_summary_match(recomputed, good)


class TestYearSeal:
    """审核阻断 3：dev 仅 2024；复核仅 2021；其余一律 exit 2（校验先于数据读取）。"""

    def test_dev_rejects_non_2024(self):
        assert vote_main(["--run-id", "x", "--year", "2022"]) == 2
        assert vote_main(["--run-id", "x", "--year", "2023"]) == 2

    def test_recheck_rejects_non_2021(self):
        assert vote_main(["--run-id", "x", "--year", "2024", "--recheck",
                          "--dev-run-id", "d"]) == 2

    def test_dev_mode_rejects_2021(self):
        assert vote_main(["--run-id", "x", "--year", "2021"]) == 2


DEV_DATASET_SHA = "d" * 64   # fixture：approved_2024_dataset_sha


def _dev_archive(tmp_path, run_id="dev-1", verdict="PROMOTE_CANDIDATE", temp=0.4):
    """完整归档 fixture（v11 收口）：manifest/summary/audit_index 全字段，
    覆盖 load_dev_temperature 的 9 项强制核验；参照真实归档 docs/phase6/6a1-2024-001/
    的字段形态（verdict 除外，实验归档为 ROLLBACK，fixture 用 PROMOTE_CANDIDATE）。"""
    d = tmp_path / run_id
    d.mkdir(parents=True)
    manifest = {"run_id": run_id, "sample_temperature": temp,
                "temperature_freeze": {"sample_temperature": temp},
                "dataset_sha256": DEV_DATASET_SHA,
                "profile_id": PROFILE_ID, "chart_schema_version": "legacy_v0",
                "provider": "deepseek", "model": "deepseek-chat"}
    summary = {"status": "OK", "verdict": verdict, "year": 2024, "recheck": False,
               "delta1_pp": 0.0, "delta2_pp": 0.0}
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    audit = {"mode": "vote", "run_id": run_id, "year": 2024,
             "dataset_sha256": DEV_DATASET_SHA,
             "summary_check": {"status": "PASS",
                               "summary_sha256": sha256_file(d / "summary.json"),
                               "recomputed": {"delta1_pp": 0.0, "delta2_pp": 0.0}}}
    (d / "audit_index.json").write_text(json.dumps(audit), encoding="utf-8")
    return d


def _mutate(d, name, fn):
    """就地修改归档 JSON（fn 接收解析后的 dict 并原地改）。"""
    p = d / name
    data = json.loads(p.read_text(encoding="utf-8"))
    fn(data)
    p.write_text(json.dumps(data), encoding="utf-8")


class TestDevRunId:
    """v11 收口：load_dev_temperature fail-closed，9 项强制核验（缺字段或不一致即拒绝）。"""

    def _load(self, tmp_path, run_id="dev-1", provider="deepseek", model="deepseek-chat",
              sha=DEV_DATASET_SHA):
        return load_dev_temperature(run_id, archive_dir=tmp_path,
                                    provider=provider, model=model,
                                    approved_2024_dataset_sha=sha)

    def test_reads_temperature_and_verdict(self, tmp_path):
        _dev_archive(tmp_path)
        t, info = self._load(tmp_path)
        assert t == 0.4
        assert info["verdict"] == "PROMOTE_CANDIDATE"
        assert info["dev_run_id"] == "dev-1" and info["dev_manifest_sha256"]
        assert info["dataset_sha256"] == DEV_DATASET_SHA

    def test_rejects_non_promote(self, tmp_path):       # ② verdict 非 PROMOTE_CANDIDATE
        _dev_archive(tmp_path, verdict="NON_INFERIOR")
        with pytest.raises(ValueError, match="PROMOTE_CANDIDATE"):
            self._load(tmp_path)

    def test_rejects_config_mismatch(self, tmp_path):
        _dev_archive(tmp_path)
        with pytest.raises(ValueError, match="不一致"):
            self._load(tmp_path, model="other-model")

    def test_rejects_missing_status(self, tmp_path):    # ① summary.status 缺失
        d = _dev_archive(tmp_path)
        _mutate(d, "summary.json", lambda s: s.pop("status"))
        with pytest.raises(ValueError, match="status 非 OK"):
            self._load(tmp_path)

    def test_rejects_wrong_year(self, tmp_path):        # ③ summary.year 非 2024
        d = _dev_archive(tmp_path)
        _mutate(d, "summary.json", lambda s: s.update(year=2021))
        with pytest.raises(ValueError, match="year 非 2024"):
            self._load(tmp_path)

    def test_rejects_recheck_true(self, tmp_path):      # ④ summary.recheck 非 false
        d = _dev_archive(tmp_path)
        _mutate(d, "summary.json", lambda s: s.update(recheck=True))
        with pytest.raises(ValueError, match="recheck 非 false"):
            self._load(tmp_path)

    def test_rejects_run_id_mismatch(self, tmp_path):   # ⑤ manifest.run_id 不一致
        d = _dev_archive(tmp_path)
        _mutate(d, "manifest.json", lambda m: m.update(run_id="other-run"))
        with pytest.raises(ValueError, match="run_id 不一致"):
            self._load(tmp_path)

    def test_rejects_illegal_temperature(self, tmp_path):  # ⑥ 温度∉{0.4,1.0}
        _dev_archive(tmp_path, temp=0.7)
        with pytest.raises(ValueError, match="温度非法"):
            self._load(tmp_path)

    def test_rejects_missing_temperature_freeze(self, tmp_path):  # ⑦ freeze 块缺失
        d = _dev_archive(tmp_path)
        _mutate(d, "manifest.json", lambda m: m.pop("temperature_freeze"))
        with pytest.raises(ValueError, match="缺 temperature_freeze"):
            self._load(tmp_path)

    def test_rejects_temperature_freeze_mismatch(self, tmp_path):  # ⑦ freeze 与温度不一致
        d = _dev_archive(tmp_path)
        _mutate(d, "manifest.json",
                lambda m: m.update(temperature_freeze={"sample_temperature": 1.0}))
        with pytest.raises(ValueError, match="temperature_freeze"):
            self._load(tmp_path)

    def test_rejects_dataset_sha_mismatch(self, tmp_path):  # ⑧ dataset_sha256 不一致
        _dev_archive(tmp_path)
        with pytest.raises(ValueError, match="dataset SHA"):
            self._load(tmp_path, sha="e" * 64)

    def test_rejects_missing_audit_index(self, tmp_path):   # ⑨ audit_index.json 缺失
        d = _dev_archive(tmp_path)
        (d / "audit_index.json").unlink()
        with pytest.raises(ValueError, match="audit_index"):
            self._load(tmp_path)

    def test_rejects_audit_not_pass(self, tmp_path):        # ⑨ summary_check 非 PASS
        d = _dev_archive(tmp_path)
        _mutate(d, "audit_index.json",
                lambda a: a["summary_check"].update(status="FAIL"))
        with pytest.raises(ValueError, match="summary_check 非 PASS"):
            self._load(tmp_path)


class TestCost:
    def test_cost_metrics(self):
        # 40 题 × 100 字符 × 3 repeats：vote5=60000，单臂=12000，比值 5.0（v3 中优 5）
        m = cost_metrics([100] * 40, repeats=3)
        assert m["arm_total_chars_per_run"] == {"vote5": 60000, "single_t": 12000, "anchor": 12000}
        assert m["cost_ratio_vote5_vs_single_t"] == 5.0
        assert m["cost_ratio_vote5_vs_anchor"] == 5.0
        assert m["per_case_chars_trimmed_mean"] == 100.0


class TestRunVote:
    def test_slices_in_order_and_ledger(self, tmp_path):
        spy = RunnerSpy()
        cfg = fake_vote_config(root=tmp_path)
        sched = build_main_schedule(cfg, CASE_IDS)
        result = run_vote(cfg, sched, slice_runner=spy)
        assert result["status"] == "OK"
        assert len(spy.calls) == 12
        result2 = run_vote(cfg, sched, slice_runner=spy)
        assert result2["status"] == "OK"        # 幂等：不触发溢出

    def test_blocked_incomplete_on_exit3(self, tmp_path):
        class Spy3(RunnerSpy):
            def __call__(self, slice_run, **kw):
                super().__call__(slice_run, **kw)
                return type("R", (), {"exit_code": 3, "records": [], "calls_attempted": 0})
        cfg = fake_vote_config(root=tmp_path)
        result = run_vote(cfg, build_main_schedule(cfg, CASE_IDS), slice_runner=Spy3())
        assert result["status"] == "BLOCKED_INCOMPLETE"


class TestValidateCaseIds:
    """v3 中优 6：case_id 早期校验，probe 前即拒绝畸形 dataset。"""

    def test_valid_40_unique(self):
        validate_case_ids(CASE_IDS)

    def test_rejects_short(self):
        with pytest.raises(ValueError, match="40"):
            validate_case_ids(CASE_IDS[:39])

    def test_rejects_duplicate(self):
        with pytest.raises(ValueError, match="唯一"):
            validate_case_ids(CASE_IDS[:39] + ["c0"])


class TestManifestReconciliation:
    """v3 阻断 3：manifest 预算对账与 slice_order 含 probe。"""

    def test_manifest_includes_probe(self, tmp_path):
        from scripts.run_phase6_6a1_ablation import (
            VoteConfig,
            _build_manifest,
            build_main_schedule,
            build_probe_slice,
            split_ab_ba,
        )
        config = VoteConfig(run_id="t", year=2024, root=tmp_path,
                            enriched_path=tmp_path / "e.jsonl")
        group_a, _ = split_ab_ba(CASE_IDS, config.seed)
        probe = build_probe_slice(config, group_a, "probe_r1", 0.4)
        main_sched = build_main_schedule(config, CASE_IDS)
        executed = [probe, *main_sched]
        manifest = _build_manifest(
            config, executed, attempted=770, temperature=0.4,
            probe_info={"rate_r1": 0.7, "action_r1": "freeze", "sample_temperature": 0.4},
            case_ids=CASE_IDS, dataset_sha256="abc", groups_sha256="def",
            dev_dataset_sha256="abc")
        br = manifest["budget_reconciliation"]
        assert br["probe_scheduled"] == 50
        assert br["main_scheduled"] == 720
        assert br["scheduled_total"] == 770
        assert br["attempted_total"] == 770
        assert br["registered_hard_cap"] == 910
        assert any("probe_r1" in s for s in manifest["slice_order"])
        assert len(manifest["slice_order"]) == 13   # 1 probe + 12 main


class TestProbeCaseBinding:
    """v4 阻断 2 + v5 阻断 1+2：probe_rows_complete 绑定预期 case + expected_arm；
    diversity_rate 拒绝预期外 case。probe 测试必须用 probe_row（非 srow）。"""

    def test_probe_rejects_wrong_case_set(self):
        """probe 结果混入另外 10 题 -> 集合不匹配 -> ValueError（不再只看题数）。"""
        from scripts.run_phase6_6a1_ablation import probe_rows_complete
        expected = [f"c{i}" for i in range(10)]
        rows = [probe_row(f"c{i + 100}", j, "A") for i in range(10) for j in range(5)]
        with pytest.raises(ValueError, match="集合不匹配"):
            probe_rows_complete(rows, expected, "probe_r1")

    def test_probe_rejects_wrong_arm(self):
        """v5 阻断 1：arm != expected_arm -> ValueError（禁止混合 probe_r1/r2）。"""
        from scripts.run_phase6_6a1_ablation import probe_rows_complete
        expected = [f"c{i}" for i in range(10)]
        rows = [probe_row(f"c{i}", j, "A", arm="probe_r2") for i in range(10) for j in range(5)]
        with pytest.raises(ValueError, match="arm 异常"):
            probe_rows_complete(rows, expected, "probe_r1")

    def test_diversity_rejects_unexpected_case(self):
        """diversity_rate 遇预期外 case -> ValueError（不再 setdefault 扩大分母）。"""
        from scripts.run_phase6_6a1_ablation import diversity_rate
        expected = [f"c{i}" for i in range(10)]
        rows = [probe_row("c999", 0, "A")]
        with pytest.raises(ValueError, match="预期外 case"):
            diversity_rate(rows, expected)


class TestAuditCliSummaryCheck:
    """v4 阻断 1 + v5 高优 7：审计 --mode vote 默认检查 summary，mismatch 时 main() 返回非零。
    v5 高优 7：测试用真实目录结构 <root>/<arm>/runs/<run_id>/slice_*/detail.jsonl + --root。"""

    @staticmethod
    def _write_real_slices(tmp_path, rows):
        """按 collect_run 真实目录写 detail.jsonl（arm 遍历 vote5_samples/anchor_single0）。"""
        by_arm = {}
        for r in rows:
            by_arm.setdefault(r["attempt_key"][2], []).append(r)
        for arm, arm_rows in by_arm.items():
            slice_dir = tmp_path / arm / "runs" / "6a1-2024-001" / "slice_main_0"
            slice_dir.mkdir(parents=True)
            (slice_dir / "detail.jsonl").write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in arm_rows) + "\n",
                encoding="utf-8")

    def test_audit_main_returns_nonzero_on_summary_mismatch(self, tmp_path, monkeypatch):
        """构造 summary.json 与复算结果不一致 -> main() 返回 2（真实目录 + --root）。"""
        import scripts.build_phase6_audit_index as audit
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        self._write_real_slices(tmp_path, rows)
        (tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl").parent.mkdir(parents=True,
                                                                                           exist_ok=True)
        (tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl").write_text(
            "\n".join(json.dumps({"case_id": f"c{i}"}) for i in range(40)) + "\n", encoding="utf-8")
        archive_root = tmp_path / "phase6_archive"
        archive = archive_root / "6a1-2024-001"
        archive.mkdir(parents=True)
        (archive / "summary.json").write_text(json.dumps({
            "delta1_pp": 99.9, "delta2_pp": 12.5,
            "acc": {"vote5": [1.0, 1.0, 1.0], "single_t": [1.0, 1.0, 1.0],
                    "anchor": [0.875, 0.875, 0.875]},
            "unresolved_rate": 0.0,
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(audit, "ARCHIVE_ROOT", archive_root)
        rc = audit.main(["--run-id", "6a1-2024-001", "--year", "2024",
                         "--arms", "vote5_samples,anchor_single0", "--mode", "vote",
                         "--root", str(tmp_path)])
        assert rc == 2

    def test_audit_main_skip_summary_check_returns_zero(self, tmp_path, monkeypatch):
        """--skip-summary-check 诊断模式 -> 不检查，返回 0（真实目录 + --root）。"""
        import scripts.build_phase6_audit_index as audit
        rows = _full_rows([40, 40, 40], [35, 35, 35])
        self._write_real_slices(tmp_path, rows)
        (tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl").parent.mkdir(parents=True,
                                                                                           exist_ok=True)
        (tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl").write_text(
            "\n".join(json.dumps({"case_id": f"c{i}"}) for i in range(40)) + "\n", encoding="utf-8")
        archive_root = tmp_path / "phase6_archive"
        archive = archive_root / "6a1-2024-001"
        archive.mkdir(parents=True)
        (archive / "summary.json").write_text(json.dumps({"delta1_pp": 99.9}),
                                              encoding="utf-8")
        monkeypatch.setattr(audit, "ARCHIVE_ROOT", archive_root)
        rc = audit.main(["--run-id", "6a1-2024-001", "--year", "2024",
                         "--arms", "vote5_samples,anchor_single0", "--mode", "vote",
                         "--skip-summary-check", "--root", str(tmp_path)])
        assert rc == 0


class TestValidateCaseIdsCli:
    """v4 高优 4：畸形 case_id -> 结构化 JSON 错误 + exit 2 + runner 调用 0 次。"""

    def test_invalid_case_ids_returns_2_and_zero_calls(self, tmp_path, monkeypatch):
        """v6 测试缺口 + v8 阻断：40 行文件但含一个重复 case_id，通过实体校验后被
        validate_case_ids 拒（不再靠"39 行 + row_count=40"这种会被 v8 实体校验拒的方式）。"""
        import scripts.run_phase6_6a1_ablation as vote
        enriched = tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
        enriched.parent.mkdir(parents=True)
        # 40 行但含一个重复 case_id（39 唯一 + 1 重复）
        rows = [{"case_id": f"c{i}"} for i in range(39)] + [{"case_id": "c0"}]
        enriched.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        # v8 阻断：manifest row_count=40 与实际 40 行一致，SHA 与实际文件匹配
        manifest = tmp_path / "enrich_manifest.json"
        manifest.write_text(json.dumps({
            "as_of_date": "2024-01-01",
            "entries": [{"year": 2024, "output_path": str(enriched),
                         "output_sha256": vote.sha256_file(enriched),
                         "row_count": 40, "as_of_date": "2024-01-01"}],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(vote, "_collect_workspace_state",
                            lambda: {"clean": True, "dirty_files": [], "file_sha256": {}})
        calls = []
        monkeypatch.setattr(vote, "run_vote", lambda *a, **k: calls.append(1) or {"status": "OK"})
        monkeypatch.setattr(vote, "offline_gate", lambda c: [])
        rc = vote.main(["--run-id", "t", "--year", "2024", "--root", str(tmp_path), "--yes"])
        assert rc == 2
        assert calls == []   # runner 未被调用


class TestProbeInfoRoundTrip:
    """v7 阻断 2：freeze_temperature 纯函数 + manifest 组合测试。
    v9 中优收口：本测试不驱动生产 main，只验证"纯函数写入 -> _build_manifest 保留 ->
    load_dev_temperature 读取"的字段链路；生产 main 是否真正调用 freeze_temperature 由
    TestFreezeTemperatureMainCallSpy 覆盖。"""

    def test_manifest_round_trip_has_sample_temperature(self, tmp_path, monkeypatch):
        """probe 流程生成的 manifest 必须含 temperature_freeze.sample_temperature，
        load_dev_temperature 读取时该字段必存且等于 manifest.sample_temperature。"""
        import scripts.run_phase6_6a1_ablation as vote
        # 构造合法 dataset + manifest
        enriched = tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
        enriched.parent.mkdir(parents=True)
        enriched.write_text("\n".join(json.dumps({"case_id": f"c{i}"}) for i in range(40)) + "\n",
                            encoding="utf-8")
        manifest = tmp_path / "enrich_manifest.json"
        manifest.write_text(json.dumps({
            "as_of_date": "2024-01-01",
            "entries": [{"year": 2024, "output_path": str(enriched),
                         "output_sha256": vote.sha256_file(enriched),
                         "row_count": 40, "as_of_date": "2024-01-01"}],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(vote, "_collect_workspace_state",
                            lambda: {"clean": True, "dirty_files": [], "file_sha256": {}})
        # 模拟 probe 流程：用 freeze_temperature 纯函数（生产 main 也调用同一函数，
        # 若生产删除该调用，本测试立即失败）
        temperature = 0.4
        probe_info = vote.freeze_temperature({"rate_r1": 0.7, "action_r1": "freeze"}, temperature)
        assert probe_info["sample_temperature"] == temperature      # v8 高优 2：断言纯函数确写入
        config = vote.VoteConfig(run_id="dev", year=2024, root=tmp_path,
                                 enriched_path=enriched, as_of_date="2024-01-01",
                                 dev_dataset_sha256=vote.sha256_file(enriched))
        executed = [vote.build_probe_slice(config, [f"c{i}" for i in range(40)],
                                           "probe_r1", temperature)]
        m = vote._build_manifest(config, executed, attempted=50, temperature=temperature,
                                 probe_info=probe_info, case_ids=[f"c{i}" for i in range(40)],
                                 dataset_sha256=vote.sha256_file(enriched),
                                 groups_sha256="g", dev_dataset_sha256=config.dev_dataset_sha256)
        # 写入归档
        archive_dir = tmp_path / "phase6" / "dev"
        archive_dir.mkdir(parents=True)
        (archive_dir / "manifest.json").write_text(json.dumps(m, ensure_ascii=False),
                                                   encoding="utf-8")
        # v7 阻断 2：load_dev_temperature 要求 summary.json + audit_index.json 完整
        (archive_dir / "summary.json").write_text(json.dumps({
            "status": "OK", "verdict": "PROMOTE_CANDIDATE", "year": 2024,
            "recheck": False, "delta1_pp": 0.0, "delta2_pp": 0.0,
        }, ensure_ascii=False), encoding="utf-8")
        summary_sha = vote.sha256_file(archive_dir / "summary.json")
        (archive_dir / "audit_index.json").write_text(json.dumps({
            "mode": "vote", "run_id": "dev", "year": 2024,
            "dataset_sha256": config.dev_dataset_sha256,
            "summary_check": {"status": "PASS", "summary_sha256": summary_sha,
                              "recomputed": {"delta1_pp": 0.0, "delta2_pp": 0.0}},
        }, ensure_ascii=False), encoding="utf-8")
        # 闭环：load_dev_temperature 读取，验证 sample_temperature 字段存在且一致
        temperature_loaded, _ = vote.load_dev_temperature(
            "dev", archive_dir=tmp_path / "phase6",
            provider="deepseek", model="deepseek-chat",
            approved_2024_dataset_sha=config.dev_dataset_sha256)
        assert temperature_loaded == temperature
        assert m["temperature_freeze"]["sample_temperature"] == temperature


class TestAsOfDateResume:
    """v7 阻断 3：as_of_date resume 三场景测试。
    真实签名：build_resume_manifest(args, profile) / check_resume_manifest(manifest_path, current)。"""

    def _make_args(self, as_of_date, tmp_path):
        """构造带 as_of_date 属性的 args namespace + profile（最小桩）。"""
        import argparse
        ns = argparse.Namespace(
            as_of_date=as_of_date, attempt_stage="main",
            dataset=str(tmp_path / "ds.jsonl"), case_ids_file=None,
            arm="vote5_samples", repeat_idx=0, provider="deepseek", model="deepseek-chat",
            temperature=0.4, sample_temperature=0.4, n_samples=5,
            aggregate="emit_samples", method="strict_majority",
            scheduled_calls=50, hard_cap=60,
        )
        (tmp_path / "ds.jsonl").write_text("x\n", encoding="utf-8")
        # 执行偏差登记：计划原桩缺 dataset/prompt_style/interaction_mode，
        # Task 2 已批准实现 prompt_fingerprint -> derive_formatter 需要这三个路由字段
        # （否则 AttributeError）；补齐路由字段，断言语义不变。
        profile = argparse.Namespace(
            profile_id="baziqa_v1", chart_schema_version="v1",
            prompt_template="", system_prompt="", user_prompt_template="",
            parser_mode="strict", aggregation="strict_majority",
            dataset="baziqa", prompt_style="xjz_direct", interaction_mode="direct",
        )
        return ns, profile

    def test_same_date_allows_resume(self, tmp_path):
        """相同 as_of_date -> resume 允许（check_resume_manifest 不抛 SystemExit）。"""
        from benchmark.runners.run_benchmark import (
            build_resume_manifest,
            check_resume_manifest,
        )
        args, profile = self._make_args("2024-01-01", tmp_path)
        new_manifest = build_resume_manifest(args, profile)
        old_path = tmp_path / "resume.json"
        old_path.write_text(json.dumps(new_manifest, ensure_ascii=False), encoding="utf-8")
        check_resume_manifest(str(old_path), new_manifest)  # 不抛异常即通过

    def test_date_change_rejects_resume(self, tmp_path):
        """as_of_date 变化 -> SystemExit(2) 拒绝 resume。"""
        import pytest

        from benchmark.runners.run_benchmark import (
            build_resume_manifest,
            check_resume_manifest,
        )
        args_old, profile = self._make_args("2024-01-01", tmp_path)
        old_manifest = build_resume_manifest(args_old, profile)
        old_path = tmp_path / "resume.json"
        old_path.write_text(json.dumps(old_manifest, ensure_ascii=False), encoding="utf-8")
        args_new, _ = self._make_args("2024-02-01", tmp_path)
        new_manifest = build_resume_manifest(args_new, profile)
        with pytest.raises(SystemExit) as ei:
            check_resume_manifest(str(old_path), new_manifest)
        assert ei.value.code == 2

    def test_missing_date_in_old_manifest_rejects_resume(self, tmp_path):
        """旧 manifest 缺 as_of_date 字段 -> SystemExit(2) fail-closed。"""
        import pytest

        from benchmark.runners.run_benchmark import (
            build_resume_manifest,
            check_resume_manifest,
        )
        args, profile = self._make_args("2024-01-01", tmp_path)
        new_manifest = build_resume_manifest(args, profile)
        old_manifest = {k: v for k, v in new_manifest.items() if k != "as_of_date"}
        old_path = tmp_path / "resume.json"
        old_path.write_text(json.dumps(old_manifest, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(SystemExit) as ei:
            check_resume_manifest(str(old_path), new_manifest)
        assert ei.value.code == 2


class TestValidateEnrichmentEntry:
    """v7 高优 4 + v8 阻断/高优 1：validate_enrichment_entry 纯函数测试。"""

    def _write_valid_enriched(self, path: Path, n_rows: int = 40):
        """写 n_rows 唯一 case_id 的 enriched.jsonl。"""
        rows = [{"case_id": f"c{i}"} for i in range(n_rows)]
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    def test_valid_entry_returns_sha(self, tmp_path):
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        entry = {"year": 2024, "output_path": str(enriched),
                 "output_sha256": vote.sha256_file(enriched), "row_count": 40,
                 "as_of_date": "2024-01-01"}
        assert validate_enrichment_entry(entry, enriched, 2024, "2024-01-01") == entry["output_sha256"]

    def test_wrong_year_rejected(self, tmp_path):
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        entry = {"year": 2023, "output_path": str(enriched),
                 "output_sha256": vote.sha256_file(enriched), "row_count": 40,
                 "as_of_date": "2024-01-01"}
        with pytest.raises(ValueError, match="year 异常"):
            validate_enrichment_entry(entry, enriched, 2024, "2024-01-01")

    def test_path_mismatch_rejected(self, tmp_path):
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        other = tmp_path / "other.jsonl"
        self._write_valid_enriched(other)
        entry = {"year": 2024, "output_path": str(other),
                 "output_sha256": vote.sha256_file(other), "row_count": 40,
                 "as_of_date": "2024-01-01"}
        with pytest.raises(ValueError, match="output_path 与 enriched_path 不一致"):
            validate_enrichment_entry(entry, enriched, 2024, "2024-01-01")

    def test_sha_mismatch_rejected(self, tmp_path):
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        entry = {"year": 2024, "output_path": str(enriched),
                 "output_sha256": "wrong", "row_count": 40, "as_of_date": "2024-01-01"}
        with pytest.raises(ValueError, match="output_sha256 不匹配"):
            validate_enrichment_entry(entry, enriched, 2024, "2024-01-01")

    def test_actual_row_count_mismatch_rejected(self, tmp_path):
        """v8 阻断：实际 39 行但 row_count 声明 40 -> 拒（原漏洞正是此场景）。"""
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched, n_rows=39)
        entry = {"year": 2024, "output_path": str(enriched),
                 "output_sha256": vote.sha256_file(enriched), "row_count": 40,
                 "as_of_date": "2024-01-01"}
        with pytest.raises(ValueError, match="实际行数"):
            validate_enrichment_entry(entry, enriched, 2024, "2024-01-01")

    def test_as_of_date_mismatch_with_top_rejected(self, tmp_path):
        """v8 高优 1：entry.as_of_date != expected_as_of_date -> 拒。"""
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        entry = {"year": 2024, "output_path": str(enriched),
                 "output_sha256": vote.sha256_file(enriched), "row_count": 40,
                 "as_of_date": "2024-02-01"}
        with pytest.raises(ValueError, match="as_of_date 与顶层不一致"):
            validate_enrichment_entry(entry, enriched, 2024, "2024-01-01")

    def test_empty_as_of_date_rejected(self, tmp_path):
        import scripts.run_phase6_6a1_ablation as vote
        from scripts.run_phase6_6a1_ablation import validate_enrichment_entry
        enriched = tmp_path / "enriched.jsonl"
        self._write_valid_enriched(enriched)
        entry = {"year": 2024, "output_path": str(enriched),
                 "output_sha256": vote.sha256_file(enriched), "row_count": 40, "as_of_date": ""}
        with pytest.raises(ValueError, match="as_of_date 为空"):
            validate_enrichment_entry(entry, enriched, 2024, "")


class TestAllowDirtyCli:
    """v8 高优 3：--allow-dirty 策略 CLI 测试锁定。"""

    def _prepare_valid_dataset(self, tmp_path):
        """写合法 40 行 dataset + enrich_manifest（供 CLI 用）。"""
        import scripts.run_phase6_6a1_ablation as vote
        enriched = tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
        enriched.parent.mkdir(parents=True)
        rows = [{"case_id": f"c{i}"} for i in range(40)]
        enriched.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        (tmp_path / "enrich_manifest.json").write_text(json.dumps({
            "as_of_date": "2024-01-01",
            "entries": [{"year": 2024, "output_path": str(enriched),
                         "output_sha256": vote.sha256_file(enriched),
                         "row_count": 40, "as_of_date": "2024-01-01"}],
        }, ensure_ascii=False), encoding="utf-8")
        return enriched

    def test_allow_dirty_with_yes_rejected(self, tmp_path):
        """--allow-dirty --yes 组合被 parser.error 拒（SystemExit 2）。"""
        import pytest

        import scripts.run_phase6_6a1_ablation as vote
        with pytest.raises(SystemExit) as ei:
            vote.main(["--run-id", "t", "--year", "2024", "--root", str(tmp_path),
                       "--allow-dirty", "--yes"])
        assert ei.value.code == 2

    def test_only_allow_dirty_zero_run_vote_calls(self, tmp_path, monkeypatch):
        """仅 --allow-dirty（无 --yes）时 fake run_vote 调用 0 次（不进模型调用路径）。
        v9 阻断：主流程缺 --yes 走 dry-run 语义 return 0；关键不变量是 calls == []。"""
        import scripts.run_phase6_6a1_ablation as vote
        self._prepare_valid_dataset(tmp_path)
        calls = []
        monkeypatch.setattr(vote, "run_vote", lambda *a, **k: calls.append(1) or {"status": "OK"})
        monkeypatch.setattr(vote, "offline_gate", lambda c: [])
        rc = vote.main(["--run-id", "t", "--year", "2024", "--root", str(tmp_path),
                        "--allow-dirty"])
        assert calls == []                              # runner 0 次（关键不变量）
        assert rc == 0                                  # dry-run 语义

    def test_dirty_without_allow_exits_before_offline_gate(self, tmp_path, monkeypatch):
        """workspace dirty 且无 --allow-dirty -> offline_gate 前 exit 2（fake gate 不被调用）。"""
        import scripts.run_phase6_6a1_ablation as vote
        self._prepare_valid_dataset(tmp_path)
        monkeypatch.setattr(vote, "_collect_workspace_state",
                            lambda: {"clean": False, "dirty_files": ["scripts/run_phase6_6a1_ablation.py M"],
                                     "file_sha256": {}})
        gate_calls = []
        monkeypatch.setattr(vote, "offline_gate", lambda c: gate_calls.append(1) or [])
        rc = vote.main(["--run-id", "t", "--year", "2024", "--root", str(tmp_path), "--yes"])
        assert rc == 2
        assert gate_calls == []                         # offline_gate 未被调用


class TestFreezeTemperatureMainCallSpy:
    """v9 中优：spy 包装 freeze_temperature 驱动生产 main，断言主流程确实调用。
    若生产 main 删除 `probe_info = freeze_temperature(...)` 那一行，本测试立即失败。"""

    def test_main_invokes_freeze_temperature_once(self, tmp_path, monkeypatch):
        import scripts.run_phase6_6a1_ablation as vote
        # 合法 dataset + manifest（复用 TestAllowDirtyCli 的准备逻辑）
        enriched = tmp_path / "datasets" / "baziqa_contest8_2024_holdout_enriched.jsonl"
        enriched.parent.mkdir(parents=True)
        rows = [{"case_id": f"c{i}"} for i in range(40)]
        enriched.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        (tmp_path / "enrich_manifest.json").write_text(json.dumps({
            "as_of_date": "2024-01-01",
            "entries": [{"year": 2024, "output_path": str(enriched),
                         "output_sha256": vote.sha256_file(enriched),
                         "row_count": 40, "as_of_date": "2024-01-01"}],
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(vote, "_collect_workspace_state",
                            lambda: {"clean": True, "dirty_files": [], "file_sha256": {}})
        monkeypatch.setattr(vote, "offline_gate", lambda c: [])
        # stub probe/main：run_vote 每次返回 OK；probe 后从 glob 读 rows -> stub 返回空
        # 走 probe_rows_complete + diversity_rate -> stub diversity_rate 直接给冻结 0.4 分支
        monkeypatch.setattr(vote, "run_vote", lambda *a, **k: {"status": "OK"})
        monkeypatch.setattr(vote, "probe_rows_complete", lambda *a, **k: None)
        monkeypatch.setattr(vote, "diversity_rate", lambda *a, **k: 0.7)  # >= 0.6 -> freeze 0.4
        monkeypatch.setattr(vote, "evaluate_t_switch", lambda r1, r2: ("freeze", 0.4))
        monkeypatch.setattr(vote, "write_report",
                            lambda *a, **k: {"status": "OK"})  # v10 阻断：返回 dict 避免 .get 崩
        # spy freeze_temperature（生产 main 内部通过模块属性调用，monkeypatch 生效）
        real = vote.freeze_temperature
        spy_calls = []
        def spy(info, temp):
            spy_calls.append((dict(info), temp))
            return real(info, temp)
        monkeypatch.setattr(vote, "freeze_temperature", spy)
        rc = vote.main(["--run-id", "t", "--year", "2024", "--root", str(tmp_path), "--yes"])
        assert rc == 0                                   # v10 阻断：锁定主流程正常终止
        assert len(spy_calls) == 1                       # 主流程调用 1 次
        info, temp = spy_calls[0]
        assert temp == 0.4                               # 参数正确
        assert "sample_temperature" not in info          # 传入 info 尚未含该字段
