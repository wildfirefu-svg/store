import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P9R1 = REPO / "docs" / "phase9a" / "r1"
P8 = REPO / "docs" / "phase8" / "marriage-capability"

sys.path.insert(0, str(P8))
sys.path.insert(0, str(P9))
sys.path.insert(0, str(P9R1))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestR1ManifestInit:
    def test_manifest_v5_code_frozen(self):
        m = _load_json(P9R1 / "manifest_v5.json")
        assert m["stage"] == "code_frozen"
        # 冻结上游 manifest_v4 + 原 treatment fingerprint + manifest helper + 归因证据
        for name in ("upstream_manifest_v4", "upstream_treatment_fingerprint", "phase9a_manifest_py", "attribution_py", "attribution_json"):
            assert name in m["entries"], f"{name} not frozen"
        # Task 2 新增：校准规则脚本 + v3 产物已冻结
        for name in ("silver_judge_v3_py", "silver_relevance_judgment_v3", "silver_judgment_summary_v3"):
            assert name in m["entries"], f"{name} not frozen"


class TestAttribution:
    def test_attribution_frozen(self):
        attr = _load_json(P9R1 / "attribution.json")
        assert attr["total_disagreements"] == 36
        assert attr["distribution"]["partially_relevant_to_relevant"] == 31
        assert attr["distribution"]["partially_relevant_to_irrelevant"] == 4
        assert attr["distribution"]["irrelevant_to_partially_relevant"] == 1
        assert attr["key_finding"]["cat_match_false_count"] == 31
        assert attr["key_finding"]["query_no_category_count"] == 26


class TestValidationSample:
    def test_sample_frozen_before_v3(self):
        sample = _load_json(P9R1 / "qc_sample_list_v2.json")
        assert sample["sample_size"] == 61
        assert sample["seed"] == 20260814
        assert len(sample["sample_list"]) == 61
        items = {s["item_id"] for s in sample["sample_list"]}
        assert len(items) == 37
        # 开发集隔离（tuple pair key，非字符串）
        dev_keys = {(r["item_id"], r["canonical_key"]) for r in (json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip())}
        for s in sample["sample_list"]:
            assert (s["item_id"], s["canonical_key"]) not in dev_keys
        keys = [(s["item_id"], s["canonical_key"]) for s in sample["sample_list"]]
        assert len(keys) == len(set(keys))

    def test_dev_set_isolation_negative(self):
        # 负向：把隔离检查作用于"注入开发集 pair 的污染样本"必须命中；作用于正式样本必须为空
        dev_keys = {(r["item_id"], r["canonical_key"]) for r in (json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip())}
        sample = _load_json(P9R1 / "qc_sample_list_v2.json")
        sample_keys = {(s["item_id"], s["canonical_key"]) for s in sample["sample_list"]}
        injected = min(dev_keys)  # 确定性选择（非 set 迭代顺序）
        polluted = sample_keys | {injected}
        assert polluted & dev_keys, "注入污染样本必须被交集检测命中"  # 检测逻辑正向生效
        assert not (sample_keys & dev_keys), "实际样本无泄漏"  # 实际样本负向

    def test_review_packet_frozen(self):
        # 盲评 packet：含 item_id/canonical_key/item_description/document_text/source_location；不含 label/reason/开发集标签/归因结论
        packet = [json.loads(l) for l in (P9R1 / "qc_review_packet_v2.jsonl").open(encoding="utf-8") if l.strip()]
        assert len(packet) == 61
        for p in packet:
            assert {"item_id", "canonical_key", "item_description", "document_text", "source_location"} <= set(p)
            assert "silver_label" not in p and "reason" not in p and "human_label" not in p
            assert p["item_description"]  # 非空（从 required_knowledge/knowledge_audit 构造）
            assert len(p["document_text"]) > 0  # 完整文本（非截断）


class TestCalibratedJudgment:
    def test_v3_rule_frozen(self):
        j = _load_module("silver_judge_v3", "docs/phase9a/r1/silver_judge_v3.py")
        # 注：同义词列表含"婚姻"以命中 doc 文本；测试目标是 cat_ok 边界而非同义词匹配本身
        syn = {"synonyms": {"结婚": ["婚期", "成婚", "婚姻"]}}
        # query 无 category → relevant（不降级）
        result = j.label_pair("结婚", None, {"text": "婚姻美满", "category": ""}, syn)
        assert result["label"] == "relevant"
        # query 有 category 且匹配 → relevant
        result2 = j.label_pair("结婚", "婚姻", {"text": "婚姻美满", "category": "婚姻"}, syn)
        assert result2["label"] == "relevant"
        # query 有 category 但不匹配 → partial
        result3 = j.label_pair("结婚", "事业", {"text": "婚姻美满", "category": "婚姻"}, syn)
        assert result3["label"] == "partially_relevant"

    def test_v3_judgment_generated(self):
        rows = [json.loads(l) for l in (P9R1 / "silver_relevance_judgment_v3.jsonl").open(encoding="utf-8") if l.strip()]
        assert len(rows) == 673

    def test_v2_v3_pair_diff_only_allowed_transition(self):
        # 逐 pair 比较：只有冻结规则允许的 partial→relevant 可以变化，其余 label 必须一致
        v2 = {r["item_id"] + "|" + r["canonical_key"]: r["label"] for r in (json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip())}
        v3 = {r["item_id"] + "|" + r["canonical_key"]: r["label"] for r in (json.loads(l) for l in (P9R1 / "silver_relevance_judgment_v3.jsonl").open(encoding="utf-8") if l.strip())}
        assert set(v2.keys()) == set(v3.keys())
        changed = 0
        for key in v2:
            if v2[key] != v3[key]:
                changed += 1
                assert v2[key] == "partially_relevant" and v3[key] == "relevant", f"unexpected transition {v2[key]} -> {v3[key]} for {key}"
        assert changed > 0  # 至少发生一项允许的变化（防 v3 输出与 v2 完全相同的失效实现）


class TestQcStateMachineV2:
    def test_r1_template_and_schema_exist(self):
        # R1 模板/schema/盲评 packet 必须存在（新增契约）
        assert (P9R1 / "qc_human_review_v2.jsonl").exists()
        assert (P9R1 / "qc_human_review_schema_v2.json").exists()
        assert (P9R1 / "qc_review_packet_v2.jsonl").exists()

    def test_packet_no_label_leak(self):
        # packet 不含任何 label/reason/开发集标签/归因结论
        packet = [json.loads(l) for l in (P9R1 / "qc_review_packet_v2.jsonl").open(encoding="utf-8") if l.strip()]
        for p in packet:
            assert "silver_label" not in p and "reason" not in p and "human_label" not in p
            assert "note" not in p  # 开发集标签字段

    def test_packet_matches_sample(self):
        # packet 与 sample 61 条一一对应
        packet = [json.loads(l) for l in (P9R1 / "qc_review_packet_v2.jsonl").open(encoding="utf-8") if l.strip()]
        sample = _load_json(P9R1 / "qc_sample_list_v2.json")
        packet_keys = {(p["item_id"], p["canonical_key"]) for p in packet}
        sample_keys = {(s["item_id"], s["canonical_key"]) for s in sample["sample_list"]}
        assert packet_keys == sample_keys

    def test_review_coverage_fail_closed(self):
        g = _load_module("qc_gate", "docs/phase9a/retrieval/qc_gate.py")
        sample = [{"item_id": "a", "canonical_key": "kb:gejue:1"}]
        reviews = [{"item_id": "a", "canonical_key": "kb:gejue:2", "human_label": "relevant"}]
        try:
            g.validate_review_coverage(sample, reviews)
            raised = False
        except SystemExit:
            raised = True
        assert raised
