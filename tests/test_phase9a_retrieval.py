import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
P9 = REPO / "docs" / "phase9a" / "retrieval"
P8 = REPO / "docs" / "phase8" / "marriage-capability"

sys.path.insert(0, str(P8))
sys.path.insert(0, str(P9))  # 模块顶层注入：消除测试间顺序依赖，单跑任一测试均可 import


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestFrozenConfigs:
    def test_query_set_53_queries(self):
        qs = _load_json(P9 / "query_set_frozen.json")
        assert len(qs["queries"]) == 53
        for q in qs["queries"]:
            assert {"query_id", "entrypoint", "args", "top_n"} <= set(q)

    def test_qc_params_frozen(self):
        cfg = _load_json(P9 / "qc_config.json")
        assert cfg["seed"] and cfg["sample_ratio"] == 0.1
        assert cfg["max_disagreement_rate"] == 0.1
        assert cfg["sampling"] == "stratified_by_item"  # 分层抽样，非平面 random.sample

    def test_truncation_numeric(self):
        cfg = _load_json(P9 / "truncation_config.json")
        assert cfg["N_chars_per_doc"] == 200 and cfg["M_docs_per_item"] == 5 and cfg["K_chars_per_question"] == 1200

    def test_manifest_frozen_before_strategy(self):
        m = _load_json(P9 / "manifest.json")
        assert m["stage"] in {"config_frozen", "code_frozen"}  # Task 1 初始化 config_frozen；Task 3 冻结代码后 code_frozen
        for name in ("query_set_frozen", "synonym_table", "ranking_config", "truncation_config", "qc_config", "upstream_inputs_sha"):
            assert name in m["entries"]


class TestPhase9aManifest:
    def test_append_only_rejects_change(self, tmp_path):
        import phase9a_manifest as pm
        m = tmp_path / "manifest.json"
        f = tmp_path / "a.json"
        f.write_text('{"x": 1}', encoding="utf-8")
        pm.freeze(m, {"a": (f, "json_canonical")})
        f.write_text('{"x": 2}', encoding="utf-8")  # 篡改
        try:
            pm.freeze(m, {"a": (f, "json_canonical")})
            raised = None
        except SystemExit as e:
            raised = e
        assert raised is not None  # append-only：同名 SHA 变化必须 fail-closed
        assert "already frozen" in str(raised.code) or "append-only" in str(raised.code)

    def test_idempotent_same_sha(self, tmp_path):
        import phase9a_manifest as pm
        m = tmp_path / "manifest.json"
        f = tmp_path / "a.json"
        f.write_text('{"x": 1}', encoding="utf-8")
        pm.freeze(m, {"a": (f, "json_canonical")})
        pm.freeze(m, {"a": (f, "json_canonical")})  # 幂等：SHA 一致不报错
        assert len(json.loads(m.read_text(encoding="utf-8"))["entries"]) == 1

    def test_verify_frozen_fail_closed(self, tmp_path):
        import phase9a_manifest as pm
        m = tmp_path / "manifest.json"
        pm.set_stage(m, "config_frozen")
        pm.set_stage(m, "code_frozen")  # 中优：先推进至 code_frozen，排除 stage 不符干扰，真正覆盖缺条目被拒
        try:
            pm.verify_frozen(m, ["retriever_py"])
            raised = None
        except SystemExit as e:
            raised = e
        assert raised is not None  # code_frozen 下缺条目（retriever_py 未冻结）→ fail-closed
        assert "not frozen" in str(raised.code)

    def test_stage_machine_one_way(self, tmp_path):
        import phase9a_manifest as pm
        m = tmp_path / "manifest.json"
        pm.set_stage(m, "config_frozen")
        pm.set_stage(m, "code_frozen")
        pm.set_stage(m, "sealed")
        for bad in ("code_frozen", "config_frozen"):
            try:
                pm.set_stage(m, bad)
                raised = None
            except SystemExit as e:
                raised = e
            assert raised is not None  # 回退拒绝
            assert "forbidden" in str(raised.code) or "expected next" in str(raised.code)
        try:
            pm.set_stage(m, None)
            raised = None
        except SystemExit as e:
            raised = e
        assert raised is not None  # None 拒绝（unknown stage 分支）
        assert "unknown stage" in str(raised.code)

    def test_stage_jump_rejected(self, tmp_path):
        """P0：禁跳级——None→sealed、config_frozen→sealed 必须失败。"""
        import phase9a_manifest as pm
        m = tmp_path / "manifest.json"
        for jump in ("sealed", "code_frozen"):
            try:
                pm.set_stage(m, jump)
                raised = None
            except SystemExit as e:
                raised = e
            assert raised is not None  # 跳级拒绝
            assert "forbidden" in str(raised.code) or "expected next" in str(raised.code)
        pm.set_stage(m, "config_frozen")
        try:
            pm.set_stage(m, "sealed")
            raised = None
        except SystemExit as e:
            raised = e
        assert raised is not None  # config_frozen→sealed 跳级拒绝
        assert "forbidden" in str(raised.code) or "expected next" in str(raised.code)

    def test_sealed_rejects_new_entry(self, tmp_path):
        import phase9a_manifest as pm
        m = tmp_path / "manifest.json"
        f = tmp_path / "a.json"
        f.write_text('{"x": 1}', encoding="utf-8")
        pm.set_stage(m, "config_frozen")
        pm.set_stage(m, "code_frozen")
        pm.set_stage(m, "sealed")
        try:
            pm.freeze(m, {"a": (f, "json_canonical")})
            raised = None
        except SystemExit as e:
            raised = e
        assert raised is not None  # sealed 后新增条目必须拒绝（幂等核验除外）
        assert "sealed" in str(raised.code) or "cannot modify" in str(raised.code)


class TestQcStateMachine:
    def test_pending_review_blocks_eval(self, tmp_path):
        g = _load_module("qc_gate", "docs/phase9a/retrieval/qc_gate.py")
        # 无复核记录 → HUMAN_QC_REQUIRED（阻塞指标计算与终态）
        empty_review = tmp_path / "qc_human_review.jsonl"
        empty_review.write_text("", encoding="utf-8")
        assert g.qc_state(empty_review, P9 / "qc_sample_list.json") == "HUMAN_QC_REQUIRED"

    def test_review_coverage_fail_closed(self):
        g = _load_module("qc_gate", "docs/phase9a/retrieval/qc_gate.py")
        sample = [{"item_id": "a", "canonical_key": "kb:gejue:1"}]
        reviews = [{"item_id": "a", "canonical_key": "kb:gejue:2", "human_label": "relevant"}]  # 额外 pair
        try:
            g.validate_review_coverage(sample, reviews)
            raised = False
        except SystemExit:
            raised = True
        assert raised


class TestQcSampleList:
    def test_stratified_by_item(self):
        lst = _load_json(P9 / "qc_sample_list.json")
        cfg = _load_json(P9 / "qc_config.json")
        assert lst["seed"] == cfg["seed"] and lst["sample_ratio"] == cfg["sample_ratio"]
        sample = lst["sample_list"]
        assert sample and len(sample) >= 10
        by_item = {}
        for s in sample:
            by_item.setdefault(s["item_id"], 0)
            by_item[s["item_id"]] += 1
        assert len(by_item) >= 10  # 分层：覆盖多个 item，而非平面抽样集中于少数 item
        pairs = [(s["item_id"], s["canonical_key"]) for s in sample]
        assert len(pairs) == len(set(pairs))


class TestSilverJudgment:
    def test_pairs_only_no_metadata_rows(self):
        rows = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
        assert rows and all("item_id" in r and "canonical_key" in r for r in rows)
        keys = [(r["item_id"], r["canonical_key"]) for r in rows]
        assert len(keys) == len(set(keys))

    def test_summary_separate_file(self):
        s = _load_json(P9 / "silver_judgment_summary.json")
        assert "pool_stats" in s and "actual_pair_count" in s["pool_stats"]
        assert "item_summaries" in s and "rule_sha" in s["pool_stats"]  # rule_sha 在 pool_stats 内
        assert s["pool_stats"]["actual_pair_count"] == len([json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()])
        assert s["pool_stats"]["actual_pair_count"] != 2519  # 不得用全局文档数代替

    def test_label_enum_closed(self):
        rows = [json.loads(l) for l in (P9 / "silver_relevance_judgment.jsonl").open(encoding="utf-8") if l.strip()]
        assert {r["label"] for r in rows} <= {"relevant", "partially_relevant", "irrelevant", "uncertain"}


class TestFullDoubleRun:
    def test_exec_code_frozen_before_run(self):
        # freeze-before-use 门：真实门调用（stage+条目+SHA drift 全过才不抛），非仅断言条目存在
        import phase9a_manifest as pm
        names = ["retriever_py", "run_strategies_py", "strategy_store_py",
                 "query_set_frozen", "ranking_config", "synonym_table", "upstream_inputs_sha"]
        pm.verify_frozen(P9 / "manifest.json", names)

    def test_all_53_queries_double_run_byte_identical(self):
        # strategy_outputs.jsonl 为全量 53 query 双跑产物：每行 (query_id, strategy, run1_hits, run2_hits)
        rows = [json.loads(l) for l in (P9 / "strategy_outputs.jsonl").open(encoding="utf-8") if l.strip()]
        qids = {r["query_id"] for r in rows}
        qset = _load_json(P9 / "query_set_frozen.json")
        assert len(qids) == 53
        pairs = {(r["query_id"], r["strategy"]) for r in rows}
        assert len(pairs) == 265  # 53 x 5 唯一 (query_id, strategy)
        assert len(rows) == 265
        for r in rows:
            assert r["run1_hits"] == r["run2_hits"]  # 字节一致（canonical key 序列相同）
            assert all({"canonical_key", "score", "source_priority", "category"} <= set(h) for h in r["run1_hits"])  # P0：完整命中信息供单源消费
        per_strategy = {r["strategy"] for r in rows}
        assert per_strategy == {"s1", "s2", "s3", "s4", "s5"}


class TestRetrieverCore:
    def test_canonical_keys(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        assert r.canonical_key("kb", "gejue", "ss2_021") == "kb:gejue:ss2_021"
        assert r.canonical_key("classic", "ditiansui/all_rules.json", 3, "x1") == "classic:ditiansui/all_rules.json:3:x1"

    def test_sort_key_order(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        a = r.sort_key(score=3.0, source_priority=1, category="婚姻", doc_key="kb:gejue:a")
        b = r.sort_key(score=2.0, source_priority=1, category="婚姻", doc_key="kb:gejue:b")
        assert a < b

    def test_s5_parses_json_array(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        hits = r.strategy_s5("婚姻", top_n=5)
        assert isinstance(hits, list)  # .json 数组解析成功即不崩溃（P0-5 修复验证）

    def test_s5_git_show_fail_closed(self):
        r = _load_module("retriever", "docs/phase9a/retrieval/retriever.py")
        try:
            r._load_frozen_file("docs/phase8/marriage-capability/nonexistent.json", "deadbeef")
            raised = False
        except SystemExit:
            raised = True
        assert raised  # git show 失败必须 fail-closed

    def test_s5_frozen_blob_sha_consistent(self):
        """冻结 blob 一致性：classic_texts_freeze.json 声明的 commit:path 必须可 git show，
        且实际 blob SHA 与声明一致（若声明 blob_sha，中优：不做仅 cat-file 的存在性检查）。"""
        import subprocess as sp
        freeze = json.loads((P8 / "classic_texts_freeze.json").read_text(encoding="utf-8"))
        for f in freeze["files"]:
            if "quarantine" in f["path"]:
                continue
            proc = sp.run(["git", "-C", str(REPO), "cat-file", "-e", f"{f['commit']}:{f['path']}"], capture_output=True)
            assert proc.returncode == 0, f"frozen blob missing: {f['commit']}:{f['path']}"
            if "blob_sha" in f:  # 声明了 blob_sha 则必须与 git rev-parse 一致
                rev = sp.run(["git", "-C", str(REPO), "rev-parse", f"{f['commit']}:{f['path']}"], capture_output=True, text=True)
                assert rev.returncode == 0 and rev.stdout.strip() == f["blob_sha"], f"blob sha mismatch: {f['path']}"


class TestMetricsPure:
    def test_recall_noise_split_with_overlap(self):
        ev = _load_module("evaluate", "docs/phase9a/retrieval/evaluate.py")
        judgment = [
            {"item_id": "x", "canonical_key": "kb:gejue:1", "label": "relevant"},
            {"item_id": "x", "canonical_key": "kb:gejue:2", "label": "relevant"},
            {"item_id": "x", "canonical_key": "kb:gejue:3", "label": "partially_relevant"},
            {"item_id": "x", "canonical_key": "kb:gejue:4", "label": "irrelevant"},
        ]
        bundles = {"x": [{"canonical_key": "kb:gejue:1"}, {"canonical_key": "kb:gejue:4"}]}
        metrics = ev.compute_metrics(judgment, ["x"], bundles)
        assert abs(metrics["per_item"]["x"]["weighted_recall"] - 1.0 / 2.5) < 1e-9
        assert abs(metrics["per_item"]["x"]["bundle_noise"] - 0.5) < 1e-9
        assert metrics["binary_item_coverage"] == 1.0

    def test_fixed_denominator_with_missing_item(self):
        ev = _load_module("evaluate", "docs/phase9a/retrieval/evaluate.py")
        judgment = [{"item_id": "x", "canonical_key": "kb:gejue:1", "label": "relevant"}]
        metrics = ev.compute_metrics(judgment, ["x", "y"], {"x": [{"canonical_key": "kb:gejue:1"}]})
        assert metrics["n_items"] == 2
        assert metrics["binary_item_coverage"] == 0.5
        assert "y" in metrics["no_gold_mass_items"]

    def test_judgeable_union_no_double_count(self):
        ev = _load_module("evaluate", "docs/phase9a/retrieval/evaluate.py")
        judgment = [
            {"item_id": "u", "canonical_key": "kb:gejue:1", "label": "uncertain"},
            {"item_id": "n", "canonical_key": "kb:gejue:2", "label": "irrelevant"},
        ]
        metrics = ev.compute_metrics(judgment, ["u", "n", "x"], {"x": [{"canonical_key": "kb:gejue:3"}]})
        assert metrics["judgeable_item_rate"] == 0.0
        assert set(metrics["no_gold_mass_items"]) == {"n", "x"}
        assert metrics["unjudgeable_items"] == ["u"]
        assert metrics["binary_item_coverage"] == 0.0

    def test_no_keyerror_on_unjudgeable_summary(self):
        ev = _load_module("evaluate", "docs/phase9a/retrieval/evaluate.py")
        judgment = [{"item_id": "u", "canonical_key": "kb:gejue:1", "label": "uncertain"}]
        assert ev.compute_metrics(judgment, ["u"], {})["binary_item_coverage"] == 0.0

    def test_bundle_k_budget_enforced(self, tmp_path, monkeypatch):
        ev = _load_module("evaluate", "docs/phase9a/retrieval/evaluate.py")
        import retriever as rt

        strategy_outputs = tmp_path / "strategy_outputs.jsonl"
        strategy_outputs.write_text(
            "\n".join(
                [
                    json.dumps({"query_id": "q1", "strategy": "s1", "run1_hits": [
                        {"canonical_key": "kb:gejue:1", "score": 1.0, "source_priority": 1, "category": "婚姻"},
                        {"canonical_key": "kb:gejue:2", "score": 1.0, "source_priority": 1, "category": "婚姻"},
                        {"canonical_key": "kb:gejue:3", "score": 1.0, "source_priority": 1, "category": "婚姻"},
                    ]}),
                    json.dumps({"query_id": "q2", "strategy": "s1", "run1_hits": [
                        {"canonical_key": "kb:gejue:1", "score": 1.0, "source_priority": 1, "category": "婚姻"},
                    ]}),
                ]
            ) + "\n",
            encoding="utf-8",
        )
        fake_docs = {key: {"text": "婚" * 200, "category": "婚姻"} for key in ("kb:gejue:1", "kb:gejue:2", "kb:gejue:3")}
        monkeypatch.setattr(rt, "doc_text", lambda key: fake_docs[key])
        item_map = [
            {"case_id": "c1", "item_id": "i1", "queries": [{"query_id": "q1"}]},
            {"case_id": "c1", "item_id": "i2", "queries": [{"query_id": "q2"}]},
        ]
        rows = ev.build_bundle(
            item_map,
            {"N_chars_per_doc": 200, "M_docs_per_item": 5, "K_chars_per_question": 300},
            strategies=("s1",),
            strategy_outputs_path=strategy_outputs,
        )
        assert sum(len(doc["text"]) for row in rows for doc in row["docs"]) <= 300
        assert any(len(row["docs"]) < 3 for row in rows)


class TestRealEval:
    def test_qc_fail_terminal_artifacts(self):
        result = _load_json(P9 / "retrieval_eval.json")
        receipt = _load_json(P9 / "RECEIPT.json")
        assert result["verdict"] == "SILVER_RETRIEVAL_NOT_READY"
        assert result["qc_state"] == "QC_FAIL"
        assert result["metrics"] == "not_computed"
        assert set(receipt["artifacts"]) == {"qc_result.json", "retrieval_eval.json"}
        assert not (P9 / "retrieval_bundle_dev.jsonl").exists()
        assert not (P9 / "per_strategy_eval.json").exists()

    def test_receipt_matches_published_artifacts(self):
        receipt = _load_json(P9 / "RECEIPT.json")
        for name, metadata in receipt["artifacts"].items():
            raw = (P9 / name).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == metadata["sha256"]
            assert len(raw) == metadata["size"]
            assert metadata["strategy"] == "raw_bytes"

    def test_no_overwrite_on_rerun(self):
        proc = subprocess.run(
            [sys.executable, str(P9 / "run_eval.py")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=REPO,
        )
        assert proc.returncode != 0
        assert "already exists" in proc.stdout + proc.stderr
