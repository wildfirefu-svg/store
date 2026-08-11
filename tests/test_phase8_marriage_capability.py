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


class TestReconcileSubtype:
    """p8_reconcile.py 首项：亚型 35 题对账。"""

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
