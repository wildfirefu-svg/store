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
    def test_manifest_v5_config_frozen(self):
        m = _load_json(P9R1 / "manifest_v5.json")
        assert m["stage"] == "config_frozen"
        # 冻结上游 manifest_v4 + 原 treatment fingerprint + manifest helper + 归因证据
        for name in ("upstream_manifest_v4", "upstream_treatment_fingerprint", "phase9a_manifest_py", "attribution_py", "attribution_json"):
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
        # 负向：故意注入开发集 pair 必须被检测
        dev_keys = {(r["item_id"], r["canonical_key"]) for r in (json.loads(l) for l in (P9 / "qc_human_review.jsonl").open(encoding="utf-8") if l.strip())}
        sample = _load_json(P9R1 / "qc_sample_list_v2.json")
        injected = next(iter(dev_keys))
        assert injected in dev_keys  # 注入成功
        # 若样本含开发集 pair，隔离断言必须失败
        sample_keys = {(s["item_id"], s["canonical_key"]) for s in sample["sample_list"]}
        assert injected not in sample_keys  # 实际样本无泄漏

    def test_review_packet_frozen(self):
        # 盲评 packet：含 item_id/canonical_key/item_description/document_text/source_location；不含 label/reason/开发集标签/归因结论
        packet = [json.loads(l) for l in (P9R1 / "qc_review_packet_v2.jsonl").open(encoding="utf-8") if l.strip()]
        assert len(packet) == 61
        for p in packet:
            assert {"item_id", "canonical_key", "item_description", "document_text", "source_location"} <= set(p)
            assert "silver_label" not in p and "reason" not in p and "human_label" not in p
            assert p["item_description"]  # 非空（从 required_knowledge/knowledge_audit 构造）
            assert len(p["document_text"]) > 0  # 完整文本（非截断）
