"""Phase 8 婚姻类能力前提分析测试（Task 1：P8-1 亚型拆分 + 基础设施）。

设计依据：docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md（v1.3.1）
计划依据：docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md（v3.2）
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_P8_DIR = _REPO / "docs" / "phase8" / "marriage-capability"
_CLASSIFICATION = (
    _REPO / "docs" / "phase7" / "error-analysis" / "error_classification.jsonl"
)
_MINGLI_160 = (
    _REPO
    / "docs" / "phase7" / "phase7-mingli-v4flash-nt-20260811-r2" / "mingli_160.jsonl"
)

SUBTYPES = ["婚姻状态", "结婚离婚应期", "多段婚姻", "配偶特征", "事件反查"]
PRIORITY = ["多段婚姻", "事件反查", "配偶特征", "结婚离婚应期", "婚姻状态"]
MERGEABLE_BUCKETS = ["感情细节", "其他"]

# P8-2A 冻结 schema（计划 v3.1）：六 KB 入口允许键与 top_n 类型。
KB_ALLOWED_QUERIES = {
    "search_gejue": {"allowed_args": {"query", "category"}, "top_n": "int"},
    "search_shishen_combo": {"allowed_args": {"combo_name"}, "top_n": "int"},
    "search_shensha": {"allowed_args": {"name"}, "top_n": "null"},
    "search_nayin": {"allowed_args": {"gan", "zhi"}, "top_n": "null"},
    "search_bingyao": {"allowed_args": {"query"}, "top_n": "int"},
    "search_xiangyi": {"allowed_args": {"gan_or_zhi"}, "top_n": "int"},
}
COMPUTATION_TYPES = {"dayun", "liunian", "sihua", "other"}


def _load_module(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, _REPO / relpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def _expected_35() -> list[str]:
    rows = _load_jsonl(_CLASSIFICATION)
    return sorted(
        r["case_id"]
        for r in rows
        if r.get("category") == "婚姻" and r.get("error_type") == "knowledge"
    )


def _load_split() -> dict:
    return json.loads((_P8_DIR / "subtype_split.json").read_text(encoding="utf-8"))


def _json_canonical_sha(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    obj = json.loads(text)
    canonical = json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _phase7_buckets_from_source() -> list[tuple[str, re.Pattern]]:
    """从 Phase 7 冻结脚本 quantitative_stats.py 的源码 AST 提取 buckets 字面量。

    buckets 是该脚本 main() 的局部变量，无法 import；此处按源码顺序解析
    `re.compile(r"...")` 字面量，保持与冻结规则逐字一致。
    """
    src = (
        _REPO / "docs" / "phase7" / "error-analysis" / "quantitative_stats.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "buckets" for t in node.targets):
            continue
        value = node.value
        assert isinstance(value, ast.Dict), "buckets must be a dict literal"
        out: list[tuple[str, re.Pattern]] = []
        for k, v in zip(value.keys, value.values):
            assert isinstance(k, ast.Constant) and isinstance(k.value, str)
            assert (
                isinstance(v, ast.Call)
                and isinstance(v.func, ast.Attribute)
                and isinstance(v.func.value, ast.Name)
                and v.func.value.id == "re"
                and v.func.attr == "compile"
                and v.args
                and isinstance(v.args[0], ast.Constant)
                and isinstance(v.args[0].value, str)
            )
            out.append((k.value, re.compile(v.args[0].value)))
        return out
    raise AssertionError("buckets literal not found in phase7 quantitative_stats.py")


class TestSubtypeSplit:
    """subtype_split.json 结构校验（五类枚举、优先级、计数和=35）。"""

    def test_35_marriage_knowledge_cases_selected(self):
        split = _load_split()
        assert [c["case_id"] for c in split["cases"]] == _expected_35()

    def test_primary_subtype_in_frozen_enum(self):
        split = _load_split()
        for case in split["cases"]:
            assert case["primary_subtype"] in SUBTYPES

    def test_secondary_subtypes_in_frozen_enum(self):
        split = _load_split()
        for case in split["cases"]:
            for st in case.get("secondary_subtypes") or []:
                assert st in SUBTYPES

    def test_priority_order_matches_frozen(self):
        split = _load_split()
        assert split["priority_order"] == PRIORITY

    def test_count_sum_equals_35(self):
        split = _load_split()
        assert split["summary"]["total"] == 35
        assert sum(split["summary"]["by_primary_subtype"].values()) == 35
        assert sum(split["summary"]["by_primary_subtype"].values()) == len(
            split["cases"]
        )

    def test_merged_cases_carry_merge_reason(self):
        split = _load_split()
        for case in split["cases"]:
            if case.get("merged_from"):
                assert case["merged_from"] in MERGEABLE_BUCKETS
                assert case.get("merge_reason")
            else:
                assert case.get("merge_reason") is None

    def test_phase7_bucket_reproducible(self):
        """机械 bucket 必须与 Phase 7 quantitative_stats.py 冻结源码逐条一致。"""
        split_mod = _load_module(
            "p8_subtype_split",
            "docs/phase8/marriage-capability/p8_subtype_split.py",
        )
        frozen = _phase7_buckets_from_source()
        assert [(n, rx.pattern) for n, rx in split_mod.PHASE7_BUCKETS] == [
            (n, rx.pattern) for n, rx in frozen
        ]
        norm = {r["case_id"]: r for r in _load_jsonl(_MINGLI_160)}
        split = _load_split()
        for case in split["cases"]:
            q = norm[case["case_id"]].get("question") or ""
            expected = next(
                (name for name, rx in frozen if rx.search(q)), "其他"
            )
            assert case["phase7_bucket"] == expected, case["case_id"]


class TestFreezeManifest:
    """phase8_freeze_manifest.json 与 p8_freeze.py 原子更新契约。"""

    def test_manifest_has_subtype_split_entry(self):
        manifest = json.loads(
            (_P8_DIR / "phase8_freeze_manifest.json").read_text(encoding="utf-8")
        )
        entries = {e["path"]: e for e in manifest["entries"]}
        entry = entries["docs/phase8/marriage-capability/subtype_split.json"]
        assert entry["strategy"] == "json_canonical"
        assert entry["sha256"] == _json_canonical_sha(_P8_DIR / "subtype_split.json")

    def test_atomic_add_creates_and_preserves_entries(self, tmp_path):
        freeze = _load_module("p8_freeze", "docs/phase8/marriage-capability/p8_freeze.py")
        manifest = tmp_path / "m.json"
        freeze.atomic_add(
            manifest, [{"path": "a", "sha256": "1" * 64, "strategy": "raw_bytes"}]
        )
        freeze.atomic_add(
            manifest, [{"path": "b", "sha256": "2" * 64, "strategy": "json_canonical"}]
        )
        m = json.loads(manifest.read_text(encoding="utf-8"))
        assert {e["path"] for e in m["entries"]} == {"a", "b"}
        assert {e["sha256"] for e in m["entries"]} == {"1" * 64, "2" * 64}

    def test_atomic_add_fault_before_replace_keeps_manifest_parseable(
        self, tmp_path, monkeypatch
    ):
        freeze = _load_module("p8_freeze", "docs/phase8/marriage-capability/p8_freeze.py")
        manifest = tmp_path / "m.json"
        freeze.atomic_add(
            manifest, [{"path": "a", "sha256": "1" * 64, "strategy": "raw_bytes"}]
        )
        before = manifest.read_bytes()

        def boom(*_args, **_kwargs):
            raise RuntimeError("simulated crash before replace")

        monkeypatch.setattr(freeze.os, "replace", boom)
        with pytest.raises(RuntimeError):
            freeze.atomic_add(
                manifest, [{"path": "b", "sha256": "2" * 64, "strategy": "raw_bytes"}]
            )
        assert manifest.read_bytes() == before
        assert json.loads(manifest.read_text(encoding="utf-8"))  # 无半写状态

    def test_atomic_add_fault_during_tmp_write_keeps_manifest_parseable(
        self, tmp_path, monkeypatch
    ):
        freeze = _load_module("p8_freeze", "docs/phase8/marriage-capability/p8_freeze.py")
        manifest = tmp_path / "m.json"
        freeze.atomic_add(
            manifest, [{"path": "a", "sha256": "1" * 64, "strategy": "raw_bytes"}]
        )
        before = manifest.read_bytes()

        def boom(*_args, **_kwargs):
            raise OSError("simulated disk full")

        monkeypatch.setattr(freeze.Path, "write_text", boom)
        with pytest.raises(OSError):
            freeze.atomic_add(
                manifest, [{"path": "b", "sha256": "2" * 64, "strategy": "raw_bytes"}]
            )
        assert manifest.read_bytes() == before
        assert json.loads(manifest.read_text(encoding="utf-8"))

    def test_atomic_add_rejects_invalid_entry(self, tmp_path):
        freeze = _load_module("p8_freeze", "docs/phase8/marriage-capability/p8_freeze.py")
        manifest = tmp_path / "m.json"
        with pytest.raises(ValueError):
            freeze.atomic_add(manifest, [{"path": "a"}])
        assert not manifest.exists()

    def test_atomic_add_rejects_bad_sha256_format(self, tmp_path):
        freeze = _load_module("p8_freeze", "docs/phase8/marriage-capability/p8_freeze.py")
        manifest = tmp_path / "m.json"
        with pytest.raises(ValueError):
            freeze.atomic_add(
                manifest,
                [{"path": "a", "sha256": "not-hex", "strategy": "raw_bytes"}],
            )
        with pytest.raises(ValueError):
            freeze.atomic_add(
                manifest,
                [{"path": "a", "sha256": "abcd" * 15, "strategy": "raw_bytes"}],
            )
        assert not manifest.exists()

    def test_atomic_add_corrupted_manifest_raises_without_overwrite(self, tmp_path):
        freeze = _load_module("p8_freeze", "docs/phase8/marriage-capability/p8_freeze.py")
        manifest = tmp_path / "m.json"
        manifest.write_text("{broken json", encoding="utf-8")
        with pytest.raises(ValueError, match="corrupted"):
            freeze.atomic_add(
                manifest,
                [{"path": "a", "sha256": "0" * 64, "strategy": "raw_bytes"}],
            )
        assert manifest.read_text(encoding="utf-8") == "{broken json"


class TestRequiredKnowledge:
    """required_knowledge.jsonl 结构化 schema 校验（P8-2A，计划 v3.1）。"""

    def _rows(self) -> list[dict]:
        path = _P8_DIR / "required_knowledge.jsonl"
        return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]

    def test_35_rows(self):
        rows = self._rows()
        assert len(rows) == 35
        assert [r["case_id"] for r in rows] == _expected_35()

    def test_row_schema(self):
        for row in self._rows():
            assert isinstance(row.get("case_id"), str)
            assert isinstance(row.get("items"), list) and row["items"]
            for item in row["items"]:
                for key in (
                    "item_id",
                    "item_type",
                    "computation_type",
                    "target_years",
                    "required_inputs",
                    "query_specs",
                ):
                    assert key in item, f"{row['case_id']}: missing {key}"

    def test_item_id_stable_and_sequential(self):
        for row in self._rows():
            for i, item in enumerate(row["items"], start=1):
                assert item["item_id"] == f"{row['case_id']}#k{i}"

    def test_item_type_enum(self):
        for row in self._rows():
            for item in row["items"]:
                assert item["item_type"] in {"computation", "doctrine"}

    def test_computation_items(self):
        for row in self._rows():
            for item in row["items"]:
                if item["item_type"] != "computation":
                    continue
                assert item["computation_type"] in COMPUTATION_TYPES, item["item_id"]
                assert item["target_years"] is not None and item["target_years"], item["item_id"]
                assert isinstance(item["required_inputs"], list) and item["required_inputs"]
                assert item["query_specs"] == []

    def test_doctrine_items(self):
        for row in self._rows():
            for item in row["items"]:
                if item["item_type"] != "doctrine":
                    continue
                assert item["computation_type"] is None
                assert item["target_years"] is None
                assert item["query_specs"], item["item_id"]

    def test_entrypoint_whitelist(self):
        for row in self._rows():
            for item in row["items"]:
                for qs in item["query_specs"]:
                    assert qs["entrypoint"] in KB_ALLOWED_QUERIES, qs["query_id"]

    def test_query_id_format(self):
        for row in self._rows():
            for item in row["items"]:
                for j, qs in enumerate(item["query_specs"], start=1):
                    assert qs["query_id"] == f"{item['item_id']}#q{j}"

    def test_args_exact_allowed_keys_and_no_top_n(self):
        """args 键恰对应该入口冻结允许键；args 内不得含 top_n；未知键/缺键 fail-closed。"""
        for row in self._rows():
            for item in row["items"]:
                for qs in item["query_specs"]:
                    allowed = KB_ALLOWED_QUERIES[qs["entrypoint"]]["allowed_args"]
                    assert set(qs["args"]) == allowed, qs["query_id"]
                    assert "top_n" not in qs["args"]

    def test_top_n_type_per_entrypoint(self):
        for row in self._rows():
            for item in row["items"]:
                for qs in item["query_specs"]:
                    want = KB_ALLOWED_QUERIES[qs["entrypoint"]]["top_n"]
                    if want == "int":
                        assert isinstance(qs["top_n"], int) and qs["top_n"] > 0
                    else:
                        assert qs["top_n"] is None

    def test_synonym_source_nonempty(self):
        for row in self._rows():
            for item in row["items"]:
                for qs in item["query_specs"]:
                    assert isinstance(qs["synonym_source"], str) and qs["synonym_source"]


SNAPSHOT_TABLES = [
    "gejue", "gejue_fts", "gejue_fts_data", "gejue_fts_idx",
    "gejue_fts_docsize", "gejue_fts_config",
    "shishen_combos", "shensha", "nayin", "bingyao", "xiangyi",
]
EXCLUDED_TABLES = ["ziwei_patterns", "yangzhai", "wuyun_liuqi"]
CLASSIC_TEXT_BOOKS = ["ditiansui", "qiongtongbaojian", "sanmingtonghui", "zipingzhenquan"]
PROBE_QUERIES = [
    {"entrypoint": "search_gejue", "args": {"query": "婚姻", "category": None}, "top_n": 5},
    {"entrypoint": "search_shishen_combo", "args": {"combo_name": "官星"}, "top_n": 5},
    {"entrypoint": "search_shensha", "args": {"name": "红鸾"}, "top_n": None},
    {"entrypoint": "search_nayin", "args": {"gan": "甲", "zhi": "子"}, "top_n": None},
    {"entrypoint": "search_bingyao", "args": {"query": "火"}, "top_n": 5},
    {"entrypoint": "search_xiangyi", "args": {"gan_or_zhi": "甲"}, "top_n": 10},
]


def _git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(_REPO), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestKbQuerySet:
    """kb_query_set.json：入口名 + 类型化参数 + 来源溯源，六入口允许键 fail-closed。"""

    def _qset(self) -> dict:
        return _load_json(_P8_DIR / "kb_query_set.json")

    def _rk_doctrine_qs(self) -> list[dict]:
        rows = [
            json.loads(l)
            for l in (_P8_DIR / "required_knowledge.jsonl").open(encoding="utf-8")
            if l.strip()
        ]
        return [
            qs
            for row in rows
            for item in row["items"]
            for qs in item["query_specs"]
        ]

    def test_schema_and_entrypoint_whitelist(self):
        qset = self._qset()
        assert qset["schema_version"] == "1.0"
        assert qset["queries"]
        for q in qset["queries"]:
            assert q["entrypoint"] in KB_ALLOWED_QUERIES
            allowed = KB_ALLOWED_QUERIES[q["entrypoint"]]["allowed_args"]
            assert set(q["args"]) == allowed
            assert "top_n" not in q["args"]
            want = KB_ALLOWED_QUERIES[q["entrypoint"]]["top_n"]
            if want == "int":
                assert isinstance(q["top_n"], int) and q["top_n"] > 0
            else:
                assert q["top_n"] is None
            assert q["sources"]

    def test_no_duplicate_query(self):
        qset = self._qset()
        keys = [(q["entrypoint"], json.dumps(q["args"], sort_keys=True)) for q in qset["queries"]]
        assert len(keys) == len(set(keys))

    def test_full_coverage_of_doctrine_query_specs(self):
        qset = self._qset()
        rk = self._rk_doctrine_qs()
        qids = {q["query_id"] for q in rk}
        covered: set[str] = set()
        for q in qset["queries"]:
            for src in q["sources"]:
                assert src["query_id"] in qids, src
                covered.add(src["query_id"])
        assert covered == qids


class TestClassicTextsFreeze:
    """classic_texts_freeze.json：四书文件 allowlist + blob SHA + 可达 commit。"""

    def test_eight_files_at_head(self):
        freeze = _load_json(_P8_DIR / "classic_texts_freeze.json")
        files = [f["path"] for f in freeze["files"]]
        expected = [
            f"knowledge_base/classic_texts/{book}/{name}"
            for book in CLASSIC_TEXT_BOOKS
            for name in ("all_rules.json", "quarantine_rules.jsonl")
        ]
        assert files == expected

    def test_blob_sha_matches_head(self):
        freeze = _load_json(_P8_DIR / "classic_texts_freeze.json")
        for f in freeze["files"]:
            blob = _git(["rev-parse", f"HEAD:{f['path']}"])
            assert f["blob_sha"] == blob, f["path"]
            assert f["commit"]
            _git(["cat-file", "-e", f["commit"] + "^{commit}"])


class TestKbSnapshot:
    """kb_snapshot.db：全表全字段导出 + 行数一致 + FTS 结构保留。"""

    def _snap_tables(self) -> set[str]:
        conn = sqlite3.connect((_P8_DIR / "kb_snapshot.db").resolve().as_uri() + "?mode=ro", uri=True)
        try:
            return {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','virtual')"
                )
            }
        finally:
            conn.close()

    def test_tables_present_and_excluded_absent(self):
        tables = self._snap_tables()
        assert set(SNAPSHOT_TABLES) <= tables
        assert not (set(EXCLUDED_TABLES) & tables)

    def test_row_counts_match_original(self):
        conn_snap = sqlite3.connect((_P8_DIR / "kb_snapshot.db").resolve().as_uri() + "?mode=ro", uri=True)
        conn_orig = sqlite3.connect((_REPO / "knowledge-base" / "bazi_kb.db").resolve().as_uri() + "?mode=ro", uri=True)
        try:
            for table in [t for t in SNAPSHOT_TABLES if t != "gejue_fts"]:
                n_snap = conn_snap.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                n_orig = conn_orig.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                assert n_snap == n_orig, table
        finally:
            conn_snap.close()
            conn_orig.close()

    def test_fts_schema_preserved(self):
        conn_snap = sqlite3.connect((_P8_DIR / "kb_snapshot.db").resolve().as_uri() + "?mode=ro", uri=True)
        try:
            sql = conn_snap.execute(
                "SELECT sql FROM sqlite_master WHERE name='gejue_fts'"
            ).fetchone()[0]
            assert "fts5" in sql and "content='gejue'" in sql
        finally:
            conn_snap.close()


class TestKbEquivalence:
    """kb_equivalence.json：全部查询 + 探针查询，命中 ID/顺序/行数/canonical 内容一致。"""

    def test_all_queries_ok(self):
        eq = _load_json(_P8_DIR / "kb_equivalence.json")
        assert eq["summary"]["total"] > 0
        assert eq["summary"]["ok"] == eq["summary"]["total"]
        for q in eq["queries"]:
            assert q["ok"] is True
            assert q["ids_equal"] and q["order_equal"] and q["content_equal"]

    def test_gejue_no_like_fallback(self):
        """无 category 的 gejue 走 FTS5 路径（bazi_kb.py:261-270），必须证明未静默退回 LIKE。"""
        eq = _load_json(_P8_DIR / "kb_equivalence.json")
        gejue = [q for q in eq["queries"] if q["entrypoint"] == "search_gejue"]
        assert gejue
        fts_gejue = [q for q in gejue if not q["args"].get("category")]
        assert fts_gejue  # 探针查询必须走 FTS 路径
        for q in fts_gejue:
            assert q["fts_direct_match"] is True
            assert q["fallback_used"] is False
        for q in gejue:
            assert q["fallback_used"] is False
            if q["args"].get("category"):
                # category 限定路径为纯 LIKE（bazi_kb.py:255-259），无 FTS 也无 fallback
                assert q["fts_direct_match"] is None

    def test_covers_query_set_and_probes(self):
        eq = _load_json(_P8_DIR / "kb_equivalence.json")
        qset = _load_json(_P8_DIR / "kb_query_set.json")
        qids = {q["query_id"] for q in qset["queries"]}
        probe_ids = {q["query_id"] for q in eq["queries"] if q["source"] == "probe"}
        assert len(probe_ids) == len(PROBE_QUERIES)
        covered = {q["query_id"] for q in eq["queries"] if q["source"] == "kb_query_set"}
        assert covered == qids

    def test_regeneration_deterministic(self):
        """重跑等价性校验应产生与落盘产物字节一致的 JSON。"""
        snap = _load_module(
            "p8_kb_snapshot", "docs/phase8/marriage-capability/p8_kb_snapshot.py"
        )
        tmp_out = _REPO / ".tmp" / "phase8_kb_equivalence_rerun.json"
        snap.run_equivalence(
            _P8_DIR / "kb_query_set.json",
            PROBE_QUERIES,
            _REPO / "knowledge-base" / "bazi_kb.db",
            _P8_DIR / "kb_snapshot.db",
            tmp_out,
        )
        try:
            before = (_P8_DIR / "kb_equivalence.json").read_bytes()
            after = tmp_out.read_bytes()
            assert before == after
        finally:
            tmp_out.unlink(missing_ok=True)


    def test_regen_paths_are_posix(self):
        """重生成的 JSON 不得含反斜杠路径（跨平台字节可重现的前提）。"""
        snap = _load_module(
            "p8_kb_snapshot", "docs/phase8/marriage-capability/p8_kb_snapshot.py"
        )
        tmp_out = _REPO / ".tmp" / "phase8_kb_equivalence_posix_probe.json"
        snap.run_equivalence(
            _P8_DIR / "kb_query_set.json",
            PROBE_QUERIES,
            _REPO / "knowledge-base" / "bazi_kb.db",
            _P8_DIR / "kb_snapshot.db",
            tmp_out,
        )
        try:
            assert b"\\" not in tmp_out.read_bytes()
        finally:
            tmp_out.unlink(missing_ok=True)

class TestComputabilityProbe:
    """computability_probe.json：四态、无 current_*、双跑字节一致、缺失三态。"""

    def _probe(self) -> dict:
        return _load_json(_P8_DIR / "computability_probe.json")

    def _computation_items(self) -> list[dict]:
        rows = [
            json.loads(l)
            for l in (_P8_DIR / "required_knowledge.jsonl").open(encoding="utf-8")
            if l.strip()
        ]
        return [
            item
            for row in rows
            for item in row["items"]
            if item["item_type"] == "computation"
        ]

    def test_status_enum_and_coverage(self):
        probe = self._probe()
        assert probe["schema_version"] == "1.0"
        statuses = [i["computability_status"] for i in probe["items"]]
        assert set(statuses) <= {"computable", "missing_input", "no_interface", "semantic_gap"}
        assert "computable" in statuses  # dayun/liunian 至少可算
        assert "no_interface" in statuses  # 流年四化无独立接口
        assert len(probe["items"]) == len(self._computation_items())

    def test_item_id_set_matches_computation_items(self):
        probe = self._probe()
        expected = {i["item_id"] for i in self._computation_items()}
        actual = {i["item_id"] for i in probe["items"]}
        assert actual == expected

    def test_no_current_fields_recursive(self):
        """递归扫描探针输出，不得出现任何 current_* 字段。"""
        probe = self._probe()
        hits: list[str] = []

        def walk(obj, path: str) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.startswith("current_"):
                        hits.append(f"{path}.{k}")
                    walk(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    walk(v, f"{path}[{i}]")

        walk(probe, "$")
        assert hits == []

    def test_double_run_byte_identical(self):
        """双跑字节一致门：重跑探针输出与落盘产物逐字节一致。"""
        probe_mod = _load_module(
            "p8_probe", "docs/phase8/marriage-capability/p8_probe.py"
        )
        tmp_out = _REPO / ".tmp" / "phase8_probe_rerun.json"
        probe_mod.run_probe(
            _P8_DIR / "required_knowledge.jsonl",
            _MINGLI_160,
            tmp_out,
        )
        try:
            assert (_P8_DIR / "computability_probe.json").read_bytes() == tmp_out.read_bytes()
        finally:
            tmp_out.unlink(missing_ok=True)

    def test_missing_gender(self):
        """gender 缺失/非男女 → missing_input。"""
        probe_mod = _load_module(
            "p8_probe", "docs/phase8/marriage-capability/p8_probe.py"
        )
        case = {
            "case_id": "mingli_ftb_test",
            "chart_input": {
                "official_astro": {"chinese_date": "甲寅 戊辰 己亥 壬申"}
            },
            "birth_info": {"gender": "其他", "year": 1974, "month": 4, "day": 28},
        }
        item = {
            "item_id": "mingli_ftb_test#k1",
            "computation_type": "dayun",
            "target_years": ["2006"],
        }
        result = probe_mod.probe_computation_item(item, case)
        assert result["computability_status"] == "missing_input"
        assert "gender" in result["reason"]

    def test_bad_chinese_date(self):
        """chinese_date 解析失败 → missing_input + 原因。"""
        probe_mod = _load_module(
            "p8_probe", "docs/phase8/marriage-capability/p8_probe.py"
        )
        case = {
            "case_id": "mingli_ftb_test",
            "chart_input": {"official_astro": {"chinese_date": "甲寅戊辰"}},
            "birth_info": {"gender": "男", "year": 1974, "month": 4, "day": 28},
        }
        item = {
            "item_id": "mingli_ftb_test#k2",
            "computation_type": "liunian",
            "target_years": ["2006"],
        }
        result = probe_mod.probe_computation_item(item, case)
        assert result["computability_status"] == "missing_input"
        assert "chinese_date" in result["reason"]

    def test_no_interface_sihua(self):
        """四化无独立接口 → no_interface。"""
        probe = self._probe()
        sihua = [i for i in probe["items"] if i["computation_type"] == "sihua"]
        assert sihua
        for i in sihua:
            assert i["computability_status"] == "no_interface"
            assert i["reason"]

    def test_parse_rules_recorded(self):
        """chinese_date→年/月柱解析规则必须落盘。"""
        probe = self._probe()
        rules = probe.get("parse_rules")
        assert rules and "chinese_date" in rules and "gender" in rules

    def test_dayun_pillars_keep_content(self):
        """dayun 的 pillars 元素必须保留稳定字段（gan/zhi/years 等），不得被滤空。"""
        probe = self._probe()
        dayun = [i for i in probe["items"] if i["computation_type"] == "dayun"]
        assert dayun
        for i in dayun:
            pillars = i["output_summary"]["pillars"]
            assert pillars and all(
                p.get("gan") and p.get("zhi") and p.get("years") for p in pillars
            ), i["item_id"]


CLASSIC_TEXT_ALLOWED_FIELDS = {"rule", "original_text", "subject", "condition", "category"}
GAP_CLASSES = {"知识缺失", "检索不可见", "计算缺失", "注入缺失", "模型未利用", "undetermined"}
PRIMARY_GAP_PRIORITY = ["计算缺失", "注入缺失", "检索不可见", "知识缺失", "模型未利用"]


class TestClassicTextsSearch:
    """classic_texts_search.py：匹配语义冻结 + schema fail-closed + quarantine 标记。"""

    def _mod(self):
        return _load_module(
            "classic_texts_search",
            "docs/phase8/marriage-capability/classic_texts_search.py",
        )

    def test_search_fields_frozen(self):
        mod = self._mod()
        assert set(mod.SEARCH_FIELDS) == CLASSIC_TEXT_ALLOWED_FIELDS
        assert set(mod.PRIMARY_FIELDS) == {"rule", "original_text"}
        assert set(mod.AUX_FIELDS) == {"subject", "condition", "category"}

    def test_schema_fail_closed_on_unknown_field(self, tmp_path):
        mod = self._mod()
        bad = tmp_path / "bad.json"
        bad.write_text(
            json.dumps([{"id": "x", "rule": "r", "unknown_field": "u"}]),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit):
            mod.search_file(bad, [["婚姻"]])

    def test_schema_fail_closed_on_missing_required(self, tmp_path):
        mod = self._mod()
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps([{"id": "x", "rule": "r"}]), encoding="utf-8")
        with pytest.raises(SystemExit):
            mod.search_file(bad, [["婚姻"]])

    def test_group_or_and_between_groups(self, tmp_path):
        """同义词组内 OR、组间 AND、子串匹配（去空白）。"""
        mod = self._mod()
        fixture = tmp_path / "rules.json"
        fixture.write_text(
            json.dumps(
                [
                    {"id": "a", "category": "婚姻", "subject": "婚配", "condition": "男命",
                     "rule": "财星得地妻贤", "original_text": "财星得地妻贤",
                     "source_book": "x", "source_chapter": "y"},
                    {"id": "b", "category": "婚姻", "subject": "婚配", "condition": "女命",
                     "rule": "官星有根夫贵", "original_text": "官星有根夫贵",
                     "source_book": "x", "source_chapter": "y"},
                    {"id": "c", "category": "婚姻", "subject": "婚配", "condition": "男命",
                     "rule": "财星得地 妻贤", "original_text": "财星得地 妻贤",
                     "source_book": "x", "source_chapter": "y"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        # 组内 OR（财星|官星）AND 组间（妻贤）
        hits = mod.search_file(fixture, [["财星", "官星"], ["妻贤"]])
        ids = {h["record_id"] for h in hits}
        assert ids == {"a", "c"}  # c 去空白后子串命中；b 缺妻贤
        for h in hits:
            assert h["matched_fields"]

    def test_quarantine_flagged(self, tmp_path):
        mod = self._mod()
        fixture = tmp_path / "q.jsonl"
        fixture.write_text(
            json.dumps({"id": "q1", "category": "婚姻", "subject": "s", "condition": "c",
                        "rule": "财星得地妻贤", "original_text": "财星得地妻贤",
                        "source_book": "x", "source_chapter": "y", "quarantine_reason": "低质"},
                       ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        hits = mod.search_file(fixture, [["财星"]], quarantined=True)
        assert hits and all(h["quarantined"] is True for h in hits)

    def test_results_stable_order_and_pointer(self, tmp_path):
        mod = self._mod()
        fixture = tmp_path / "rules.json"
        fixture.write_text(
            json.dumps(
                [
                    {"id": "a", "category": "婚姻", "subject": "s", "condition": "c",
                     "rule": "财星得地妻贤", "original_text": "财星得地妻贤",
                     "source_book": "x", "source_chapter": "y"},
                    {"id": "b", "category": "婚姻", "subject": "s", "condition": "c",
                     "rule": "官星有根夫贵", "original_text": "官星有根夫贵",
                     "source_book": "x", "source_chapter": "y"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        hits = mod.search_file(fixture, [["财星", "官星"]])  # 单组 OR
        assert [h["record_id"] for h in hits] == ["a", "b"]  # 文件序+行序稳定
        for h in hits:
            assert h["json_pointer"].startswith("/")
            assert h["excerpt"]


class TestPromptRebuild:
    """prompt 重建审计：fingerprint 硬门 + prompt_evidence。"""

    def test_fingerprint_matches_receipt(self):
        audit = _load_module("p8_audit", "docs/phase8/marriage-capability/p8_audit.py")
        profile = audit.resolve_profile("mingli_official_cot_astro")
        assert audit.prompt_fingerprint(profile) == (
            "e136106a8e8730020eb3631b32b6c24424beaf73f5f0fcbc82a274e2120cb22d"
        )

    def test_prompt_evidence_recorded(self):
        """case 级 prompt_evidence：字段路径 + 逐字摘录。"""
        audit = json.loads(
            (_P8_DIR / "knowledge_audit.jsonl").open(encoding="utf-8").readline()
        )
        assert "prompt_evidence" in audit
        ev = audit["prompt_evidence"]
        assert ev and all("field_path" in e and "excerpt" in e for e in ev)

    def test_item_prompt_evidence_recorded(self):
        """逐知识项 prompt_evidence：required_term + found + excerpt（不得硬编码）。"""
        rows = [
            json.loads(l)
            for l in (_P8_DIR / "knowledge_audit.jsonl").open(encoding="utf-8")
            if l.strip()
        ]
        for row in rows:
            for item in row["items"]:
                pe = item["prompt_evidence"]
                assert "required_term" in pe and "found" in pe, item["item_id"]
                assert isinstance(pe["found"], bool)
                if pe["found"]:
                    assert pe["excerpt"]

    def test_model_not_utilized_evidence_semantics(self):
        """'模型未利用'若存在，证据必须来自非结构化学理文本（星曜名/宫位名不算）。"""
        rows = [
            json.loads(l)
            for l in (_P8_DIR / "knowledge_audit.jsonl").open(encoding="utf-8")
            if l.strip()
        ]
        cls = [i["gap_class"] for row in rows for i in row["items"]]
        # 模型未利用=0 是合法结果（官方 prompt 注入区无断诀文本）；
        # 若存在，其证据不得来自结构化事实（found 需为 True 且摘录含断诀句式）
        for row in rows:
            for item in row["items"]:
                if item["gap_class"] != "模型未利用":
                    continue
                pe = item["prompt_evidence"]
                assert pe["found"] is True, item["item_id"]
                assert pe.get("chart_fact_present") is not True, item["item_id"]

    def test_question_terms_not_injected(self):
        """负向：题干/选项关键词（结婚/婚期）不得判'模型未利用'。"""
        rows = {
            r["case_id"]: r
            for r in (
                json.loads(l)
                for l in (_P8_DIR / "knowledge_audit.jsonl").open(encoding="utf-8")
                if l.strip()
            )
        }
        item = next(i for i in rows["mingli_ftb_0002"]["items"] if i["item_id"] == "mingli_ftb_0002#k4")
        assert item["gap_class"] == "检索不可见"  # 题干含'结婚'，但注入区无该知识
        assert item["prompt_evidence"]["found"] is False

    def test_birth_year_not_injection(self):
        """负向：出生日期含四位年份不得判目标年份计算已注入。"""
        rows = {
            r["case_id"]: r
            for r in (
                json.loads(l)
                for l in (_P8_DIR / "knowledge_audit.jsonl").open(encoding="utf-8")
                if l.strip()
            )
        }
        item = next(i for i in rows["mingli_ftb_0092"]["items"] if i["item_id"] == "mingli_ftb_0092#k1")
        assert item["gap_class"] == "注入缺失"  # other 年龄换算：年份出现在 birth_info 不得判注入
        assert item["prompt_evidence"]["found"] is False

    def test_palace_name_not_injection(self):
        """负向：'子女宫'等宫位名不得满足'子女'检索词。"""
        rows = {
            r["case_id"]: r
            for r in (
                json.loads(l)
                for l in (_P8_DIR / "knowledge_audit.jsonl").open(encoding="utf-8")
                if l.strip()
            )
        }
        item = next(i for i in rows["mingli_ftb_0098"]["items"] if i["item_id"] == "mingli_ftb_0098#k1")
        assert item["gap_class"] == "检索不可见"  # '子女'命中'子女宫'（宫位名）不得判注入
        assert item["prompt_evidence"]["found"] is False

    def test_star_fact_not_doctrine_injection(self):
        """负向：星曜名出现（文昌星在盘）只记 chart_fact_present，不判'模型未利用'。"""
        rows = {
            r["case_id"]: r
            for r in (
                json.loads(l)
                for l in (_P8_DIR / "knowledge_audit.jsonl").open(encoding="utf-8")
                if l.strip()
            )
        }
        item = next(i for i in rows["mingli_ftb_0044"]["items"] if i["item_id"] == "mingli_ftb_0044#k4")
        # 盘面含文昌星（结构化事实），但文昌断诀/含义未注入 → 检索不可见
        assert item["gap_class"] == "检索不可见"
        assert item["prompt_evidence"]["found"] is False
        assert item["prompt_evidence"]["chart_fact_present"] is True

    def test_doctrine_evidence_query_ids(self):
        """doctrine evidence 落盘 query_id + classic 定位/摘录。"""
        rows = [
            json.loads(l)
            for l in (_P8_DIR / "knowledge_audit.jsonl").open(encoding="utf-8")
            if l.strip()
        ]
        for row in rows:
            for item in row["items"]:
                if item["item_type"] != "doctrine":
                    continue
                ev = item["evidence"]
                assert ev["kb_queries"] and all("query_id" in q and "hit_ids" in q for q in ev["kb_queries"])
                assert ev["classic_queries"]
                for q in ev["classic_queries"]:
                    assert "query_id" in q and "term" in q
                    for h in q["hits"]:
                        assert "json_pointer" in h and "excerpt" in h


class TestKnowledgeAudit:
    """knowledge_audit.jsonl：gap_class 枚举、探针映射、primary_gap 优先级、双口径分母。"""

    def _rows(self) -> list[dict]:
        return [
            json.loads(l)
            for l in (_P8_DIR / "knowledge_audit.jsonl").open(encoding="utf-8")
            if l.strip()
        ]

    def test_35_rows_and_case_set(self):
        rows = self._rows()
        assert len(rows) == 35
        assert [r["case_id"] for r in rows] == _expected_35()

    def test_gap_class_enum(self):
        for row in self._rows():
            for item in row["items"]:
                assert item["gap_class"] in GAP_CLASSES

    def test_probe_mapping(self):
        """no_interface→计算缺失；missing_input→undetermined(input_missing)；semantic_gap→undetermined。"""
        probe = _load_json(_P8_DIR / "computability_probe.json")
        status_by_id = {i["item_id"]: i["computability_status"] for i in probe["items"]}
        for row in self._rows():
            for item in row["items"]:
                if item["item_type"] != "computation":
                    continue
                status = status_by_id[item["item_id"]]
                if status == "no_interface":
                    assert item["gap_class"] == "计算缺失", item["item_id"]
                elif status == "missing_input":
                    assert item["gap_class"] == "undetermined"
                    assert item["undetermined_reason"] == "input_missing"
                elif status == "semantic_gap":
                    assert item["gap_class"] == "undetermined"

    def test_primary_gap_priority(self):
        for row in self._rows():
            determined = [
                i["gap_class"] for i in row["items"] if i["gap_class"] != "undetermined"
            ]
            if not determined:
                assert row["primary_gap"] == "undetermined"
            else:
                expected = min(determined, key=PRIMARY_GAP_PRIORITY.index)
                assert row["primary_gap"] == expected
                assert row["primary_gap_reason"]

    def test_denominator_reconciliation(self):
        """知识项总数 = 五类 + undetermined（双口径分母对账）。"""
        rows = self._rows()
        n_items = sum(len(r["items"]) for r in rows)
        gap_counts: dict[str, int] = {}
        for row in rows:
            for item in row["items"]:
                gap_counts[item["gap_class"]] = gap_counts.get(item["gap_class"], 0) + 1
        assert sum(gap_counts.values()) == n_items
        # 本数据集探针无 missing_input/semantic_gap，undetermined 可为 0（设计允许单列）


class TestC1Detector:
    """c1_detector.py：检测/候选提取/重选（合成 fixture）。"""

    def _mod(self):
        return _load_module("c1_detector", "docs/phase8/marriage-capability/c1_detector.py")

    def _fixture(self) -> list[dict]:
        return [
            json.loads(l)
            for l in (_REPO / "tests" / "fixtures" / "phase8" / "c1_synth.jsonl").open(encoding="utf-8")
            if l.strip()
        ]

    def test_detect_conflict_positive(self):
        mod = self._mod()
        for row in self._fixture():
            if row["case_id"].startswith("mingli_ftb_00"):
                result = mod.detect(row["raw_answer"], row["options"])
                assert result["conflict"] is True, row["case_id"]
                assert result["final_letter"] == row["predicted_answer"]
                assert result["body_conclusion"] is not None

    def test_detect_conflict_negative(self):
        mod = self._mod()
        for row in self._fixture():
            if row["case_id"].startswith("synth_neg"):
                result = mod.detect(row["raw_answer"], row["options"])
                assert result["conflict"] is False, row["case_id"]

    def test_candidate_extraction(self):
        mod = self._mod()
        row = next(r for r in self._fixture() if r["case_id"] == "mingli_ftb_0018")
        result = mod.detect(row["raw_answer"], row["options"])
        assert result["candidate_letter"] == "B"  # 正文结论 2018 → 选项 B

    def test_reselect(self):
        mod = self._mod()
        row = next(r for r in self._fixture() if r["case_id"] == "mingli_ftb_0034")
        result = mod.detect(row["raw_answer"], row["options"])
        assert result["candidate_letter"] == "C"  # 正文结论 2012 → 选项 C


class TestC1Replay:
    """c1_replay.py：纯评估逻辑（四态、分母对账、PASS/TERMINATED 裁决）。"""

    def _mod(self):
        return _load_module("c1_replay", "docs/phase8/marriage-capability/c1_replay.py")

    def _fixture(self) -> list[dict]:
        return [
            json.loads(l)
            for l in (_REPO / "tests" / "fixtures" / "phase8" / "c1_synth.jsonl").open(encoding="utf-8")
            if l.strip()
        ]

    def test_change_result_enum(self):
        mod = self._mod()
        for row in self._fixture():
            result = mod.evaluate_row(row)
            assert result["change_result"] in {"improved", "harmed", "unchanged", "changed_wrong_to_wrong"}

    def test_improved(self):
        mod = self._mod()
        row = next(r for r in self._fixture() if r["case_id"] == "mingli_ftb_0018")
        result = mod.evaluate_row(row)
        assert result["change_result"] == "improved"
        assert result["old_letter"] == "C"
        assert result["new_letter"] == "B"
        assert result["expected"] == "B"

    def test_unchanged_when_not_triggered(self):
        mod = self._mod()
        row = next(r for r in self._fixture() if r["case_id"] == "synth_neg_001")
        result = mod.evaluate_row(row)
        assert result["change_result"] == "unchanged"
        assert result["new_letter"] is None

    def test_verdict_pass(self):
        """0018/0034/0073 全 improved 且 harmed=0 → C1_PASS。"""
        mod = self._mod()
        rows = self._fixture()
        verdict = mod.compute_verdict(rows)
        assert verdict["verdict"] == "C1_PASS"
        assert verdict["harmed"] == 0
        assert verdict["targets_improved"] == ["mingli_ftb_0018", "mingli_ftb_0034", "mingli_ftb_0073"]

    def test_verdict_terminated_on_harmed(self):
        mod = self._mod()
        rows = self._fixture()
        # 构造一个 harmed 例：正文结论 2018（选项 B），但最终答案 A 正确
        rows.append({
            "case_id": "synth_harmed",
            "expected_answer": "A",
            "predicted_answer": "A",
            "options": ["A. 2016", "B. 2018", "C. 2020", "D. 2022"],
            "raw_answer": "综合判断：2018年机会最大。\n\n**答案：A**",
        })
        verdict = mod.compute_verdict(rows)
        assert verdict["verdict"] == "C1_TERMINATED"

    def test_denominator_160(self):
        """四态和 == 160（回放分母对账）。"""
        mod = self._mod()
        rows = self._fixture()
        verdict = mod.compute_verdict(rows)
        total = sum(verdict["counts"].values())
        assert total == len(rows)


class TestC1ReplayResult:
    """c1_detector_eval.json：单次回放产物校验（6B）。"""

    def _eval(self) -> dict:
        return _load_json(_P8_DIR / "c1_detector_eval.json")

    def test_replay_count_and_total(self):
        data = self._eval()
        assert data["replay_count"] == 1
        assert data["total"] == 160

    def test_change_result_sum_160(self):
        data = self._eval()
        assert sum(data["counts"].values()) == 160

    def test_verdict_terminal(self):
        data = self._eval()
        assert data["verdict"] in {"C1_PASS", "C1_TERMINATED"}

    def test_targets_recorded(self):
        data = self._eval()
        targets = [r for r in data["results"] if r["case_id"] in {
            "mingli_ftb_0018", "mingli_ftb_0034", "mingli_ftb_0073"
        }]
        assert len(targets) == 3
        for t in targets:
            assert t["change_result"] in {"improved", "harmed", "unchanged", "changed_wrong_to_wrong"}

    def test_no_overwrite_gate(self):
        """已存在 c1_detector_eval.json 时拒绝覆盖（单次回放机械门）。"""
        assert (_P8_DIR / "c1_detector_eval.json").exists()
        replay = _load_module("c1_replay", "docs/phase8/marriage-capability/c1_replay.py")
        with pytest.raises(SystemExit, match="已存在"):
            replay._check_frozen_and_no_overwrite(_P8_DIR / "c1_detector_eval.json")

    def test_frozen_sha_drift_gate(self, tmp_path, monkeypatch):
        """双冻结 SHA 漂移即拒绝运行。"""
        replay = _load_module("c1_replay", "docs/phase8/marriage-capability/c1_replay.py")
        # 模拟 manifest 中 c1_detector.py SHA 漂移
        import json as _json
        manifest_path = _P8_DIR / "phase8_freeze_manifest.json"
        original = _json.loads(manifest_path.read_text(encoding="utf-8"))
        tampered = _json.loads(manifest_path.read_text(encoding="utf-8"))
        for e in tampered["entries"]:
            if e["path"].endswith("c1_detector.py"):
                e["sha256"] = "0" * 64
        monkeypatch.setattr(
            replay, "P8_DIR", tmp_path
        )
        (tmp_path / "phase8_freeze_manifest.json").write_text(
            _json.dumps(tampered), encoding="utf-8"
        )
        (tmp_path / "c1_detector.py").write_text("x", encoding="utf-8")
        (tmp_path / "c1_replay.py").write_text("y", encoding="utf-8")
        with pytest.raises(SystemExit, match="SHA 漂移"):
            replay._check_frozen_and_no_overwrite(tmp_path / "out.json")


class TestReconcileSubtype:
    """p8_reconcile.py 对账（首项亚型 + 全量总对账）。"""

    def test_reconcile_subtype_passes(self):
        proc = subprocess.run(
            [sys.executable, str(_P8_DIR / "p8_reconcile.py")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=_REPO,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "subtype" in proc.stdout

    def test_reconcile_full_sections(self):
        """Task 8 全量对账：七节全 ok 且 manifest_disk 覆盖全部产物。"""
        proc = subprocess.run(
            [sys.executable, str(_P8_DIR / "p8_reconcile.py")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=_REPO,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        for section in (
            "subtype_split", "required_knowledge", "computability_probe",
            "knowledge_audit", "c1_replay", "kb_equivalence", "manifest_disk",
        ):
            assert f"[{section}]" in proc.stdout, section
        assert "FAIL" not in proc.stdout
