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
        assert m["stage"] == "config_frozen"
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
