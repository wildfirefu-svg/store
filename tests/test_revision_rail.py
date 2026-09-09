"""§5-R 修订溯源双轨契约 TDD 测试（设计 v29.3 §5-R；权威条款见设计文档）。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.classic_artifacts import (
    GENESIS_SHA,
    REVISION_GENESIS,
    RevisionArtifactError,
    chain_head,
    parse_jsonl_line,
)
from scripts.generate_classic_historical_freeze import _canonical

ROOT = Path(__file__).resolve().parent.parent
ANCHOR_REL = ("docs/superpowers/plans/notes/approvals/revisions/sanmingtonghui/"
              "accepted_anchors.jsonl")
REGISTRY_REL = ("docs/superpowers/plans/notes/approvals/revisions/sanmingtonghui/"
                "toolchain_registry.jsonl")
MANIFEST_REL = "knowledge_base/classic_texts/sanmingtonghui/revision_manifest.json"


def _sha256(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


class TestGenesis:
    def test_genesis_object_frozen(self):
        assert REVISION_GENESIS == {
            "schema": "sanmingtonghui-revision-genesis-v1",
            "book": "sanmingtonghui",
            "freeze_base_commit":
                "c5cff699fdb547bd9270acbebe1f485380848751",
            "b2_commit": "ccb833a46977c8274c0fb8c8c79c1b2f5d494c5e",
        }

    def test_genesis_sha_recomputed(self):
        # 权威公式重算，不信任常量抄写（设计 5-R.3）
        expect = _sha256(_canonical(REVISION_GENESIS).encode("utf-8"))
        assert GENESIS_SHA == expect
        assert len(GENESIS_SHA) == 64


class TestChainHead:
    def _anchor(self, **over):
        a = {"batch_id": "B01", "content_commit": "1" * 40,
             "manifest_sha256_after": "2" * 64,
             "prev_anchor_sha256": GENESIS_SHA,
             "toolchain_commit": "3" * 40, "date": "2026-09-08"}
        a.update(over)
        return a

    def test_single_entry_chain_head(self):
        h1 = chain_head([self._anchor()], GENESIS_SHA)
        expect = _sha256(GENESIS_SHA.encode("ascii")
                         + _canonical(self._anchor()).encode("utf-8"))
        assert h1 == expect

    def test_multi_entry_chain_head(self):
        a1 = self._anchor()
        h1 = chain_head([a1], GENESIS_SHA)
        a2 = self._anchor(batch_id="B02", prev_anchor_sha256=h1)
        assert chain_head([a1, a2], GENESIS_SHA) == _sha256(
            h1.encode("ascii") + _canonical(a2).encode("utf-8"))

    def test_first_prev_must_be_genesis(self):
        with pytest.raises(RevisionArtifactError):
            chain_head([self._anchor(prev_anchor_sha256="0" * 64)], GENESIS_SHA)

    def test_prev_link_mismatch_rejected(self):
        a1 = self._anchor()
        a2 = self._anchor(batch_id="B02", prev_anchor_sha256="f" * 64)
        with pytest.raises(RevisionArtifactError):
            chain_head([a1, a2], GENESIS_SHA)


class TestParseJsonlLine:
    def _line(self, obj) -> bytes:
        return (_canonical(obj) + "\n").encode("utf-8")

    def test_canonical_line_accepted(self):
        obj = {"a": 1, "b": "中"}
        assert parse_jsonl_line(self._line(obj)) == obj

    def test_non_canonical_line_rejected(self):
        raw = (json.dumps({"b": "中", "a": 1}, ensure_ascii=False,
                          separators=(",", ":")) + "\n").encode("utf-8")  # 键序非排序
        with pytest.raises(RevisionArtifactError):
            parse_jsonl_line(raw)

    def test_duplicate_key_rejected(self):
        raw = b'{"a":1,"a":2}\n'
        with pytest.raises(RevisionArtifactError):
            parse_jsonl_line(raw)

    def test_crlf_rejected(self):
        obj = {"a": 1}
        raw = (_canonical(obj) + "\r\n").encode("utf-8")
        with pytest.raises(RevisionArtifactError):
            parse_jsonl_line(raw)
