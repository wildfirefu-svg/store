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
