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
        # Task 4 终态：finalize 后 stage 单向迁移至 sealed（TestTerminalV2 交叉验证）
        assert m["stage"] == "sealed"
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


class TestTerminalV2:
    def test_effective_disagreement_gate(self):
        result = _load_json(P9R1 / "qc_result_v2.json")
        assert "effective_disagreement" in result
        assert result["effective_disagreement"] == result["disagreement_count"] + result["uncertain_count"]
        assert result["verdict"] in {"SILVER_LABEL_CALIBRATED", "SILVER_LABEL_NOT_CALIBRATED"}
        if result["effective_disagreement"] <= 6:
            assert result["verdict"] == "SILVER_LABEL_CALIBRATED"
        else:
            assert result["verdict"] == "SILVER_LABEL_NOT_CALIBRATED"

    def test_uncertain_not_double_counted(self):
        # 单条 uncertain 贡献恰好 1，不是 2
        fin = _load_module("finalize_r1", "docs/phase9a/r1/finalize_r1.py")
        reviews = [{"item_id": "a", "canonical_key": "kb:gejue:1", "human_label": "uncertain", "note": "x"}]
        silver = {("a", "kb:gejue:1"): "relevant"}
        n_diff, n_uncertain = fin._count_disagreement(reviews, silver)
        assert n_diff == 0 and n_uncertain == 1  # uncertain 不计入 diff，只计 1 次

    def test_calibration_fingerprint(self):
        fp = _load_json(P9R1 / "calibration_fingerprint.json")
        assert fp["components"] and fp["sha256"]
        names = {c["logical_name"] for c in fp["components"]}
        assert {"silver_judge_v3_py", "silver_relevance_judgment_v3", "silver_judgment_summary_v3", "qc_sample_list_v2", "attribution_json"} <= names

    def test_treatment_fingerprint_unchanged(self):
        # 原 treatment_fingerprint 字节不变（双 SHA 口径分离：文件 canonical SHA vs 内部组件摘要）
        orig = _load_json(P9 / "treatment_fingerprint.json")
        m4 = _load_json(P9 / "manifest_v4.json")
        expected_file_sha = m4["entries"]["treatment_fingerprint"]["sha256"]
        actual_file_sha = hashlib.sha256(json.dumps(orig, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode() + b"\n").hexdigest()
        assert actual_file_sha == expected_file_sha  # 文件字节不变
        assert orig["sha256"]  # 内部摘要存在（与文件 SHA 语义不同，不混用）

    def test_manifest_v5_sealed(self):
        m = _load_json(P9R1 / "manifest_v5.json")
        assert m["stage"] == "sealed"
        assert "closure" in m["entries"]
        assert "upstream_manifest_v4" in m["entries"]

    def test_receipt_binds_sealed_manifest(self):
        # RECEIPT 绑定 sealed manifest SHA + 产物元数据，不加入 manifest
        receipt = _load_json(P9R1 / "RECEIPT_r1.json")
        m = _load_json(P9R1 / "manifest_v5.json")
        assert receipt["manifest_sha256"] == hashlib.sha256(json.dumps(m, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode() + b"\n").hexdigest()
        assert "receipt_r1" not in m["entries"]  # RECEIPT 不加入 manifest（避免循环）
        assert set(receipt["artifacts"]) == {"qc_result_v2.json", "calibration_fingerprint.json", "CLOSURE.md"}
        for name, meta in receipt["artifacts"].items():
            raw = (P9R1 / name).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == meta["sha256"]
            assert len(raw) == meta["size"] and meta["strategy"] == "raw_bytes"

    def test_no_overwrite_on_rerun(self):
        # 正式终态产物已存在时 finalize_r1 必须 fail-closed
        proc = subprocess.run([sys.executable, str(P9R1 / "finalize_r1.py")], capture_output=True, text=True, encoding="utf-8", cwd=REPO)
        assert proc.returncode != 0 and "already exists" in (proc.stdout + proc.stderr)

    def test_reconcile_r1_exit_zero(self):
        # R1 最终对账入口：sealed 后 reconcile_r1.py 必须 exit 0
        proc = subprocess.run([sys.executable, str(P9R1 / "reconcile_r1.py")], capture_output=True, text=True, encoding="utf-8", cwd=REPO)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "FAIL" not in proc.stdout


class TestFinalizeResumeProtocol:
    """4 个生产路径测试（镜像从 code_frozen 输入构造，不依赖正式终态产物，可在正式发布前运行）。"""

    def _make_r1_mirror(self, tmp_path):
        """从 code_frozen 输入构造镜像：复制冻结输入 + 代码，不含正式终态产物。"""
        import shutil
        root = tmp_path / "repo"
        mirror_r1 = root / "docs" / "phase9a" / "r1"
        mirror_r1.mkdir(parents=True)
        for name in ("manifest_v5.json", "finalize_r1.py", "reconcile_r1.py", "silver_relevance_judgment_v3.jsonl",
                     "silver_judgment_summary_v3.json", "qc_sample_list_v2.json", "qc_human_review_v2.jsonl",
                     "silver_judge_v3.py", "attribution.py", "attribution.json", "generate_validation_sample.py"):
            shutil.copy(P9R1 / name, mirror_r1 / name)
        # P9 copytree（qc_gate 等依赖，已含 phase9a_manifest.py）
        shutil.copytree(P9, root / "docs" / "phase9a" / "retrieval")
        (root / "docs" / "phase8" / "marriage-capability").mkdir(parents=True)
        shutil.copy(P8 / "p8_freeze.py", root / "docs" / "phase8" / "marriage-capability" / "p8_freeze.py")
        # 净化镜像 manifest 至 code_frozen 输入态：正式发布后真实 manifest 已 sealed 且含三项终态条目，
        # 镜像从 code_frozen 输入构造（不含终态产物），需剥离终态条目并回退 stage（可重复执行前提）
        m_path = mirror_r1 / "manifest_v5.json"
        data = json.loads(m_path.read_text(encoding="utf-8"))
        data["stage"] = "code_frozen"
        for terminal in ("qc_result_v2", "calibration_fingerprint", "closure"):
            data["entries"].pop(terminal, None)
        m_path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        return root

    def _run_finalize(self, root):
        mirror_r1 = root / "docs" / "phase9a" / "r1"
        return subprocess.run([sys.executable, str(mirror_r1 / "finalize_r1.py")], capture_output=True, text=True, encoding="utf-8", cwd=root)

    def _reset_manifest_to_code_frozen(self, mirror_r1):
        m = mirror_r1 / "manifest_v5.json"
        data = json.loads(m.read_text(encoding="utf-8"))
        data["stage"] = "code_frozen"
        m.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")

    def test_resume_partial_same_products_completes(self, tmp_path):
        # 模拟真实窗口——发布一项后、freeze 前崩溃（fresh 镜像不含三项终态 manifest 条目）
        control_root = self._make_r1_mirror(tmp_path / "control")
        assert self._run_finalize(control_root).returncode == 0
        control_r1 = control_root / "docs" / "phase9a" / "r1"
        closure_bytes = (control_r1 / "CLOSURE.md").read_bytes()
        fresh_root = self._make_r1_mirror(tmp_path / "fresh")
        fresh_r1 = fresh_root / "docs" / "phase9a" / "r1"
        (fresh_r1 / "CLOSURE.md").write_bytes(closure_bytes)  # 只复制一项已发布产物
        proc = self._run_finalize(fresh_root)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert (fresh_r1 / "CLOSURE.md").read_bytes() == closure_bytes  # 既有产物字节未变
        assert (fresh_r1 / "qc_result_v2.json").exists() and (fresh_r1 / "calibration_fingerprint.json").exists()
        assert json.loads((fresh_r1 / "manifest_v5.json").read_text(encoding="utf-8"))["stage"] == "sealed"
        assert (fresh_r1 / "RECEIPT_r1.json").exists()

    def test_resume_byte_mismatch_rejected(self, tmp_path):
        # fresh 镜像 + 磁盘上留下损坏的已发布产物（真实窗口：发布后字节损坏）→ 拒绝
        control_root = self._make_r1_mirror(tmp_path / "control")
        assert self._run_finalize(control_root).returncode == 0
        control_r1 = control_root / "docs" / "phase9a" / "r1"
        corrupted = (control_r1 / "qc_result_v2.json").read_bytes() + b"tampered"
        fresh_root = self._make_r1_mirror(tmp_path / "fresh")
        fresh_r1 = fresh_root / "docs" / "phase9a" / "r1"
        (fresh_r1 / "qc_result_v2.json").write_bytes(corrupted)
        proc = self._run_finalize(fresh_root)
        assert proc.returncode != 0 and "byte mismatch" in (proc.stdout + proc.stderr)

    def test_sealed_no_receipt_republishes(self, tmp_path):
        # sealed + 无 RECEIPT：校验后补发
        root = self._make_r1_mirror(tmp_path)
        mirror_r1 = root / "docs" / "phase9a" / "r1"
        assert self._run_finalize(root).returncode == 0
        (mirror_r1 / "RECEIPT_r1.json").unlink()  # 删除 RECEIPT（manifest 仍 sealed）
        proc = self._run_finalize(root)
        assert proc.returncode == 0 and (mirror_r1 / "RECEIPT_r1.json").exists()

    def test_code_frozen_receipt_exists_rejected(self, tmp_path):
        # code_frozen + RECEIPT 已存在：拒绝且不得覆盖
        root = self._make_r1_mirror(tmp_path)
        mirror_r1 = root / "docs" / "phase9a" / "r1"
        assert self._run_finalize(root).returncode == 0
        self._reset_manifest_to_code_frozen(mirror_r1)  # 保留 RECEIPT，重置 stage
        receipt_before = (mirror_r1 / "RECEIPT_r1.json").read_bytes()
        proc = self._run_finalize(root)
        assert proc.returncode != 0 and "already exists" in (proc.stdout + proc.stderr)
        assert (mirror_r1 / "RECEIPT_r1.json").read_bytes() == receipt_before
