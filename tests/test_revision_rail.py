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


from scripts.classic_artifacts import validate_revision_manifest

EMPTY_BASELINE_MANIFEST = {
    "schema_version": "1.0", "book": "sanmingtonghui",
    "freeze_base_commit": "c5cff699fdb547bd9270acbebe1f485380848751",
    "batches": []}


def _manifest_with(batch: dict) -> dict:
    return {**EMPTY_BASELINE_MANIFEST, "batches": [batch]}


def _record(**over) -> dict:
    r = {"kind": "rule", "id": "smth_t_001", "sha256": "a" * 64,
         "source_chapter": "卷二·论坐命宫", "snapshot_path":
         "knowledge_base/classic_texts/sanmingtonghui/formal/source_snapshots/"
         "b4e9be580dbecd3e233d3adbe163299f06c6ca5174309dc83e8f14433796aaa2"
         "/extracted/raw_025.txt",
         "snapshot_sha256": "b" * 64, "historical_basis": None}
    r.update(over)
    return r


class TestManifestSchema:
    def test_empty_baseline_literal_passes(self):
        validate_revision_manifest(EMPTY_BASELINE_MANIFEST)

    def test_top_field_add_rejected(self):
        m = {**EMPTY_BASELINE_MANIFEST, "extra": 1}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(m)

    def test_top_field_missing_rejected(self):
        m = {k: v for k, v in EMPTY_BASELINE_MANIFEST.items() if k != "book"}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(m)

    def test_wrong_book_rejected(self):
        m = {**EMPTY_BASELINE_MANIFEST, "book": "ditiansui"}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(m)

    def test_batch_unknown_field_rejected(self):
        b = {"batch_id": "B01", "date": "2026-09-08", "author": "owner",
             "records": [], "x": 1}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b))

    @pytest.mark.parametrize("bad", [
        {"kind": "other"},                      # kind 枚举外
        {"sha256": "short"},                    # sha256 非 64-hex
        {"snapshot_path": "../escape.txt"},     # 路径逃逸
        {"snapshot_path": "raw_025.txt"},       # 根目录 raw 文件
        {"snapshot_sha256": "z" * 63},          # 非 64-hex
    ])
    def test_record_shapes_rejected(self, bad):
        b = {"batch_id": "B01", "date": "2026-09-08", "author": "owner",
             "records": [_record(**bad)]}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b))

    def test_record_unknown_field_rejected(self):
        rec = {**_record(), "unknown_field": 1}
        b = {"batch_id": "B01", "date": "2026-09-08", "author": "owner",
             "records": [rec]}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b))

    def test_duplicate_record_identity_rejected(self):
        rec = _record()
        b = {"batch_id": "B01", "date": "2026-09-08", "author": "owner",
             "records": [rec, dict(rec)]}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b))

    def test_duplicate_batch_id_rejected(self):
        b1 = {"batch_id": "B01", "date": "2026-09-08", "author": "o",
              "records": [_record()]}
        b2 = {"batch_id": "B01", "date": "2026-09-08", "author": "o",
              "records": []}
        m = {**EMPTY_BASELINE_MANIFEST, "batches": [b1, b2]}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(m)

    def test_historical_basis_shape(self):
        hb = {"commit": "1" * 40, "path": "knowledge_base/classic_texts/"
               "sanmingtonghui/all_rules.json", "source_chapter": "卷二·论坐命宫",
               "record_content_sha256": "c" * 64, "match_count": 1}
        rec = _record(historical_basis=hb)
        b = {"batch_id": "B01", "date": "2026-09-08", "author": "o",
             "records": [rec]}
        validate_revision_manifest(_manifest_with(b))
        bad = _record(historical_basis={**hb, "match_count": 2})
        b2 = {"batch_id": "B01", "date": "2026-09-08", "author": "o",
              "records": [bad]}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b2))

    def test_batch_id_unhashable_rejected(self):
        """执行复审 P0-3：batch_id 非法类型（unhashable）→ 稳定
        RevisionArtifactError，不得 TypeError 冒泡。"""
        b = {"batch_id": [], "date": "2026-09-08", "author": "o",
             "records": []}
        with pytest.raises(RevisionArtifactError):
            validate_revision_manifest(_manifest_with(b))

# --- linked worktree fixture（5-R.12 端到端基底）-------------------------------
import re

import scripts.generate_quality_report as gqr


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8")


class RailWorktree:
    """隔离测试仓库（linked worktree + 临时分支）；退出时强制清理。

    从真实仓库 HEAD 检出（自带 freeze/evidence/E/R/B1/B2/聚合，E0-E2 天然
    通过），但 HEAD 看不到主工作区未提交的开发中代码——因此构造**合成 T 提交**：
    把主工作区当前待测脚本字节（scripts/generate_quality_report.py、
    scripts/classic_artifacts.py）复制入 worktree 并提交，R→C→V 全部建立在
    该 T 之上（P0-4 复审修复："实现后、提交前 GREEN"才成立，不以先提交生产
    实现代替 TDD）。
    """

    def __init__(self, tmp_path: Path):
        self.path = tmp_path / "wt"
        self.branch = f"rail-test-{uuid4().hex[:8]}"
        _git(ROOT, "worktree", "add", "-b", self.branch, str(self.path), "HEAD")
        self.sync_synthetic_t()

    def sync_synthetic_t(self) -> None:
        """复制主工作区当前待测脚本字节入 worktree；有差异才提交合成 T，
        无差异（代码已提交——干净 CI 命中）则保持 HEAD 为 T（P0-2：普通
        `git commit` 在无改动时会失败，须先查 `status --porcelain`）。"""
        for rel in ("scripts/generate_quality_report.py",
                    "scripts/classic_artifacts.py"):
            self.write(rel, (ROOT / rel).read_bytes())
        dirty = _git(self.path, "status", "--porcelain", "--",
                     "scripts/generate_quality_report.py",
                     "scripts/classic_artifacts.py").strip()
        if dirty:
            self.commit("T: synthetic toolchain (in-development working-tree bytes)")
        self.toolchain_commit = self.rev("HEAD")
        self.head0 = self.toolchain_commit

    def rev(self, rev: str) -> str:
        return _git(self.path, "rev-parse", rev).strip()

    def blob(self, rev: str, rel: str) -> bytes:
        r = subprocess.run(["git", "-C", str(self.path), "show", f"{rev}:{rel}"],
                           capture_output=True)
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
        return r.stdout

    def write(self, rel: str, data: bytes) -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def append_line(self, rel: str, line: bytes) -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("ab") as f:
            f.write(line)

    def replace_constant(self, name: str, value: str) -> None:
        """唯一替换脚本常量值（其余字节不动；V/R 提交形态）。"""
        rel = "scripts/generate_quality_report.py"
        src = (self.path / rel).read_bytes().decode("utf-8")
        new, n = re.subn(
            rf'^{name} = "[0-9a-f]{{64}}"$', f'{name} = "{value}"',
            src, count=1, flags=re.M)
        assert n == 1, f"constant {name} not found"
        self.write(rel, new.encode("utf-8"))

    def commit(self, msg: str) -> str:
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-m", msg, "--no-verify")
        return self.rev("HEAD")

    def cleanup(self) -> None:
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force",
                        str(self.path)], capture_output=True)
        subprocess.run(["git", "-C", str(ROOT), "branch", "-D", self.branch],
                       capture_output=True)


@pytest.fixture()
def rail_wt(tmp_path):
    wt = RailWorktree(tmp_path)
    yield wt
    wt.cleanup()


def _anchor_line(batch_id: str, content_commit: str, manifest_sha: str,
                 prev: str, toolchain: str) -> bytes:
    obj = {"batch_id": batch_id, "content_commit": content_commit,
           "manifest_sha256_after": manifest_sha, "prev_anchor_sha256": prev,
           "toolchain_commit": toolchain, "date": "2026-09-08"}
    return (_canonical(obj) + "\n").encode("utf-8")


def _registry_line(toolchain: str, prev: str, review_ref: str = "test") -> bytes:
    obj = {"toolchain_commit": toolchain, "date": "2026-09-08",
           "review_ref": review_ref, "prev_registry_sha256": prev}
    return (_canonical(obj) + "\n").encode("utf-8")


def _canonical_bytes(obj) -> bytes:
    return _canonical(obj).encode("utf-8")


def _freeze_of(wt: RailWorktree) -> dict:
    return json.loads(wt.blob("HEAD", gqr.FREEZE_REL))


def _evidence_of(wt: RailWorktree) -> dict:
    return json.loads(wt.blob("HEAD", gqr.EVIDENCE_REL))


def _mk_rule(id_: str, chapter: str, text: str) -> dict:
    return {"id": id_, "category": "格局", "subject": "测试", "condition": "测试",
            "rule": text, "original_text": text, "source_book": "三命通会",
            "source_chapter": chapter}


def _mk_mcq(id_: str, rule_id: str) -> dict:
    return {"id": id_, "question": "测试题干？", "options": {"A": "甲", "B": "乙",
            "C": "丙", "D": "丁"}, "answer": "A", "explanation": "测试",
            "source_rule_id": rule_id, "source_book": "三命通会",
            "source_chapter": "卷二·论坐命宫"}


SNAP_REL = ("knowledge_base/classic_texts/sanmingtonghui/formal/"
            "source_snapshots/b4e9be580dbecd3e233d3adbe163299f06c6ca517"
            "4309dc83e8f14433796aaa2")
RAW025_REL = SNAP_REL + "/extracted/raw_025.txt"


class TestRailCore:
    """rail ①-⑤：解析→schema→锚链→基线比较→分区等式（合成 B01 批次）。"""

    def _make_c1(self, wt: RailWorktree, batch_id: str = "B01",
                 rule_text: str = "测试修订规则") -> dict:
        """在 worktree 构造 C₁：聚合追加 1 rule + 1 mcq + manifest 批次。"""
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        mcq_rel = "knowledge_base/classic_texts/sanmingtonghui/all_mcq.jsonl"
        snap_sha = _sha256(wt.blob("HEAD", RAW025_REL))
        # original_text 取该章原文去空白前 30 字（保证 ⑦ 子串命中）
        src_text = wt.blob("HEAD", RAW025_REL).decode("utf-8", "replace")
        probe = re.sub(r"\s+", "", src_text)[:30]
        rule = _mk_rule("smth_t_001", "卷二·论坐命宫", rule_text)
        rule["original_text"] = probe
        mcq = _mk_mcq("smth_t_001_m1", "smth_t_001")
        from scripts.generate_classic_historical_freeze import _record_entry
        rec_rule = {"kind": "rule", "id": rule["id"],
                    "sha256": _record_entry(rule)["sha256"],
                    "source_chapter": "卷二·论坐命宫", "snapshot_path": RAW025_REL,
                    "snapshot_sha256": snap_sha, "historical_basis": None}
        rec_mcq = {"kind": "mcq", "id": mcq["id"],
                   "sha256": _record_entry(mcq)["sha256"],
                   "source_chapter": "卷二·论坐命宫", "snapshot_path": RAW025_REL,
                   "snapshot_sha256": snap_sha, "historical_basis": None}
        # P0-1：all_rules.json 是 JSON 数组（非 JSONL）——解析数组、追加
        # 对象、序列化数组；all_mcq.jsonl 才按 JSONL 追加。
        rules_arr = json.loads(wt.blob("HEAD", rules_rel).decode("utf-8"))
        rules_arr.append(rule)
        wt.write(rules_rel,
                 json.dumps(rules_arr, ensure_ascii=False).encode("utf-8"))
        wt.write(mcq_rel, wt.blob("HEAD", mcq_rel)
                 + (_canonical(mcq) + "\n").encode("utf-8"))
        manifest = {"schema_version": "1.0", "book": "sanmingtonghui",
                    "freeze_base_commit":
                        "c5cff699fdb547bd9270acbebe1f485380848751",
                    "batches": [{"batch_id": batch_id, "date": "2026-09-08",
                                 "author": "test",
                                 "records": [rec_rule, rec_mcq]}]}
        wt.write(MANIFEST_REL, _canonical_bytes(manifest) + b"\n")
        return manifest

    def test_rail_none_when_no_manifest(self, rail_wt):
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["revision_state"] == "NONE"
        assert res["ok"] is True  # 无修订：沿现行 E3 语义（HEAD==freeze）
        assert res["error_code"] is None

    def test_rail_candidate_unaccepted_default_mode(self, rail_wt):
        """默认模式遇未锚合法追加 → REVISION_UNACCEPTED（④）。"""
        self._make_c1(rail_wt)
        rail_wt.commit("C1")  # rail 读 HEAD blob——写入必须提交（计划 Step 4 预期）
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["ok"] is False
        assert res["error_code"] == "REVISION_UNACCEPTED"

    def test_rail_malformed_manifest(self, rail_wt):
        rail_wt.write(MANIFEST_REL, b'{"schema_version":"1.0",')
        rail_wt.commit("malformed manifest")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_MANIFEST_MALFORMED"

    def test_rail_partition_mismatch_unmanifested_extra(self, rail_wt):
        """清单外新增（聚合加了记录、manifest 不列）→ ⑤ MISMATCH +
        unmanifested_extra 明细。"""
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        rule = _mk_rule("smth_t_002", "卷二·论坐命宫", "清单外记录")
        rules_arr = json.loads(rail_wt.blob("HEAD", rules_rel).decode("utf-8"))
        rules_arr.append(rule)
        rail_wt.write(rules_rel,
                      json.dumps(rules_arr, ensure_ascii=False).encode("utf-8"))
        rail_wt.commit("unmanifested extra")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_PARTITION_MISMATCH"
        assert res["partition_detail"]["unmanifested_extra"] >= 1

    def test_rail_legacy_mutated_detail(self, rail_wt):
        """freeze 内记录被改（改首条规则 category）→ ⑤ MISMATCH +
        legacy_mutated 明细。"""
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        arr = json.loads(rail_wt.blob("HEAD", rules_rel).decode("utf-8"))
        arr[0] = {**arr[0], "category": "tampered"}
        rail_wt.write(rules_rel,
                      json.dumps(arr, ensure_ascii=False).encode("utf-8"))
        rail_wt.commit("legacy mutated")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_PARTITION_MISMATCH"
        assert res["partition_detail"]["legacy_mutated"] >= 1

    def test_rail_other_book_manifest_rejected(self, rail_wt):
        """非锚书出现 manifest → REVISION_SOURCE_UNVERIFIABLE（5-R.0）。"""
        rail_wt.write("knowledge_base/classic_texts/ditiansui/revision_manifest.json",
                      _canonical_bytes(EMPTY_BASELINE_MANIFEST) + b"\n")
        rail_wt.commit("ditiansui manifest")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "ditiansui", _freeze_of(rail_wt), _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_SOURCE_UNVERIFIABLE"

    def test_trust_roots_start_at_genesis(self):
        """P0-2：两信任根以确定 64-hex 字面量初始化且 == genesis_sha
        （测试重算验证；满足设计 5-R.6 首批路径的空链规范值）。"""
        assert gqr.REVISION_ANCHOR_HEAD == GENESIS_SHA
        assert gqr.TOOLCHAIN_REGISTRY_HEAD == GENESIS_SHA

    def test_fixture_no_diff_synthetic_t(self, rail_wt):
        """P0-2：T 已提交后再同步（字节无差异）→ 不产生新提交、T 不变
        （覆盖"代码已提交"的干净场景；普通 commit 在无改动时会失败）。"""
        before = rail_wt.toolchain_commit
        rail_wt.sync_synthetic_t()
        assert rail_wt.toolchain_commit == before
        assert rail_wt.rev("HEAD") == before

    def test_rail_absent_kind_added_record_mismatch(self, rail_wt):
        """执行复审 P0-1：冻结时缺席的 KIND（quarantine_mcq）在 HEAD 新增
        记录 → ⑤ MISMATCH（缺席 KIND 的 baseline Counter 为空而非忽略
        HEAD——不得沿用旧 E3 的 present 跳过语义）。"""
        qrel = ("knowledge_base/classic_texts/sanmingtonghui/"
                "quarantine_mcq.jsonl")
        mcq = _mk_mcq("smth_q_001", "smth_t_001")
        rail_wt.write(qrel, (_canonical(mcq) + "\n").encode("utf-8"))
        rail_wt.commit("absent-kind record added")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_PARTITION_MISMATCH"
        assert res["partition_detail"]["unmanifested_extra"] >= 1

    def test_rail_missing_anchor_nongenesis_constant_stale(self, rail_wt,
                                                            monkeypatch):
        """执行复审 P0-2：manifest 与锚文件均缺失 + 信任根常量非 genesis →
        CHAIN_STALE（缺失与空锚同样必须核对信任根，不得退回 NONE）。
        rail 读取运行中执行体的进程内常量（与评审内存注入复现同源）。"""
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", "f" * 64)
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_CHAIN_STALE"

    def test_rail_malformed_anchor_line_stale(self, rail_wt):
        """执行复审 P0-3：畸形锚行 → 解析异常映射 REVISION_CHAIN_STALE
        返回结构，不向上抛未处理异常。"""
        rail_wt.append_line(gqr.REVISION_ANCHOR_REL, b'{"bad":\n')
        rail_wt.commit("malformed anchor line")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_CHAIN_STALE"

    def test_rail_other_books_none_after_sanming_acceptance(self, rail_wt,
                                                             monkeypatch):
        """执行复审 P0：三命通会合法 C→V 落地后，其他三书不受锚链影响
        ——仍 NONE 且本书历史分区通过（不读三命通会锚、不套用其常量规则）；
        三命通会本身经 ①-⑦ 走到 ACCEPTED。V₁ 后执行体常量 == @HEAD 链头
        （monkeypatch 对齐进程内常量与 HEAD 脚本常量，模拟真实部署同源）。"""
        manifest = self._make_c1(rail_wt)
        c1 = rail_wt.commit("C1")
        anchor = _anchor_line("B01", c1, _sha256(_canonical_bytes(manifest)),
                              GENESIS_SHA, rail_wt.head0)
        rail_wt.append_line(gqr.REVISION_ANCHOR_REL, anchor)
        head = chain_head([json.loads(anchor.decode())], GENESIS_SHA)
        rail_wt.replace_constant("REVISION_ANCHOR_HEAD", head)
        rail_wt.commit("V1")
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", head)
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["revision_state"] == "ACCEPTED"
        assert res["ok"] is True
        for book in ("ditiansui", "qiongtongbaojian", "zipingzhenquan"):
            r = gqr.evaluate_revision_rail(
                rail_wt.path, book, _freeze_of(rail_wt), _evidence_of(rail_wt))
            assert r["revision_state"] == "NONE"
            assert r["ok"] is True and r["e3_ok"] is True

    def test_rail_double_corruption_reports_manifest_first(self, rail_wt):
        """执行复审 P1：manifest 与锚同时损坏 → 按冻结优先级报阶段①
        REVISION_MANIFEST_MALFORMED（锚解析不得抢在阶段①之前）。"""
        rail_wt.write(MANIFEST_REL, b'{"schema_version":"1.0",')
        rail_wt.append_line(gqr.REVISION_ANCHOR_REL, b'{"bad":\n')
        rail_wt.commit("double corruption")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_MANIFEST_MALFORMED"


class TestRailSourceAndContent:
    """⑥ 源身份锚定链 + ⑦ 内容检查。

    ⑥ 负向走整链：先建 V₁（验收锚 + 常量对齐，④⑤⑥⑦ 全过、前置断言
    ACCEPTED），再篡改 evidence 钉住的源（raw_025 / source_manifest）→
    ⑥ 逐章 sha / OID+SHA 不符 → SOURCE_UNVERIFIABLE。
    ⑦ 内容检查无法在默认 rail 单点触发——未验收新增批次被 ④ UNACCEPTED
    拦截、已验收批次记录被改被 ⑤ PARTITION_MISMATCH 拦截；故直接测
    _source_identity_and_content 纯函数（构造已验 source 状态 + 合法
    ⑥ 前置的 manifest_recs），每个负向测试先跑同状态 good 对照断言 None，
    再断言坏例 == SOURCE_UNVERIFIABLE（证明 ⑥ 通过、⑦ 才是拦截点）。
    """

    def _v1(self, rail_wt, monkeypatch) -> str:
        core = TestRailCore()
        manifest = core._make_c1(rail_wt)
        c1 = rail_wt.commit("C1")
        anchor = _anchor_line("B01", c1, _sha256(_canonical_bytes(manifest)),
                              GENESIS_SHA, rail_wt.head0)
        rail_wt.append_line(gqr.REVISION_ANCHOR_REL, anchor)
        head = chain_head([json.loads(anchor.decode())], GENESIS_SHA)
        rail_wt.replace_constant("REVISION_ANCHOR_HEAD", head)
        rail_wt.commit("V1")
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", head)
        # 前置断言：V₁ 必须已验收（④⑤⑥⑦ 全过）——篡改才有测试意义，
        # 避免"本来就 SOURCE_UNVERIFIABLE"的假绿。
        base = gqr.evaluate_revision_rail(rail_wt.path, "sanmingtonghui",
                                          _freeze_of(rail_wt),
                                          _evidence_of(rail_wt))
        assert base["error_code"] is None and base["revision_state"] == "ACCEPTED", base
        return manifest

    def test_source_identity_recomputed(self, rail_wt, monkeypatch):
        """⑥：V₁ 后篡改 raw_025.txt（聚合/manifest 不动）→ 逐章
        extracted_text_sha256 不符 → SOURCE_UNVERIFIABLE。"""
        self._v1(rail_wt, monkeypatch)
        rail_wt.write(RAW025_REL, rail_wt.blob("HEAD", RAW025_REL) + "篡改".encode())
        rail_wt.commit("tampered raw025")  # rail 读 HEAD blob——篡改须提交
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_SOURCE_UNVERIFIABLE"

    def test_source_manifest_oid_sha_split(self, rail_wt, monkeypatch):
        """⑥-1/⑥-2：V₁ 后改 source_manifest.json 一个字节 → OID/SHA 不符
        → SOURCE_UNVERIFIABLE（evidence 钉住的双身份拦截）。"""
        self._v1(rail_wt, monkeypatch)
        sm_rel = SNAP_REL + "/source_manifest.json"
        rail_wt.write(sm_rel, rail_wt.blob("HEAD", sm_rel) + b" ")
        rail_wt.commit("tampered source_manifest")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_SOURCE_UNVERIFIABLE"

    def test_original_text_substring(self, rail_wt):
        """⑦：rule.original_text 去空白后非对应章子串 → SOURCE_UNVERIFIABLE。
        直接测 _source_identity_and_content：good 对照（probe ⊆ 章）先断言
        None 证明 ⑥ 通过，bad（非子串）再断言 SOURCE_UNVERIFIABLE。"""
        snap_sha = _sha256(rail_wt.blob("HEAD", RAW025_REL))
        src_text = rail_wt.blob("HEAD", RAW025_REL).decode("utf-8", "replace")
        probe = re.sub(r"\s+", "", src_text)[:30]
        good = _mk_rule("smth_t_good", "卷二·论坐命宫", "规则")
        good["original_text"] = probe
        bad = _mk_rule("smth_t_001", "卷二·论坐命宫", "正文")
        bad["original_text"] = "这段文字绝不出现在raw_025原文中XYZQ"
        from scripts.generate_classic_historical_freeze import _record_entry
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        arr = json.loads(rail_wt.blob("HEAD", rules_rel).decode("utf-8"))
        arr.append(good)
        arr.append(bad)
        rail_wt.write(rules_rel,
                      json.dumps(arr, ensure_ascii=False).encode("utf-8"))
        rail_wt.commit("substring control + defective head records")
        ev = _evidence_of(rail_wt)
        rec_good = {"kind": "rule", "id": good["id"],
                    "sha256": _record_entry(good)["sha256"],
                    "source_chapter": "卷二·论坐命宫",
                    "snapshot_path": RAW025_REL,
                    "snapshot_sha256": snap_sha, "historical_basis": None}
        assert gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev, [rec_good]) is None
        rec_bad = {"kind": "rule", "id": bad["id"],
                   "sha256": _record_entry(bad)["sha256"],
                   "source_chapter": "卷二·论坐命宫",
                   "snapshot_path": RAW025_REL,
                   "snapshot_sha256": snap_sha, "historical_basis": None}
        assert gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev,
            [rec_bad]) == "REVISION_SOURCE_UNVERIFIABLE"

    def test_mcq_dangling_fk_rejected(self, rail_wt):
        """⑦：mcq.source_rule_id 悬空 → SOURCE_UNVERIFIABLE。good 对照
        （外键存在）先断言 None，bad（悬空外键）再断言拒绝。"""
        snap_sha = _sha256(rail_wt.blob("HEAD", RAW025_REL))
        src_text = rail_wt.blob("HEAD", RAW025_REL).decode("utf-8", "replace")
        probe = re.sub(r"\s+", "", src_text)[:30]
        rule = _mk_rule("smth_t_001", "卷二·论坐命宫", "规则")
        rule["original_text"] = probe
        mcq_ok = _mk_mcq("smth_t_001_m1", "smth_t_001")
        mcq_bad = _mk_mcq("smth_t_001_m2", "smth_nope")  # 悬空外键
        from scripts.generate_classic_historical_freeze import _record_entry
        mcq_rel = "knowledge_base/classic_texts/sanmingtonghui/all_mcq.jsonl"
        rail_wt.write(mcq_rel, rail_wt.blob("HEAD", mcq_rel)
                      + (_canonical(mcq_ok) + "\n").encode("utf-8")
                      + (_canonical(mcq_bad) + "\n").encode("utf-8"))
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        arr = json.loads(rail_wt.blob("HEAD", rules_rel).decode("utf-8"))
        arr.append(rule)
        rail_wt.write(rules_rel,
                      json.dumps(arr, ensure_ascii=False).encode("utf-8"))
        rail_wt.commit("dangling fk head records")
        ev = _evidence_of(rail_wt)
        rec_rule = {"kind": "rule", "id": rule["id"],
                    "sha256": _record_entry(rule)["sha256"],
                    "source_chapter": "卷二·论坐命宫",
                    "snapshot_path": RAW025_REL,
                    "snapshot_sha256": snap_sha, "historical_basis": None}
        rec_ok = {"kind": "mcq", "id": mcq_ok["id"],
                  "sha256": _record_entry(mcq_ok)["sha256"],
                  "source_chapter": "卷二·论坐命宫",
                  "snapshot_path": RAW025_REL,
                  "snapshot_sha256": snap_sha, "historical_basis": None}
        assert gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev,
            [rec_rule, rec_ok]) is None
        rec_bad = {"kind": "mcq", "id": mcq_bad["id"],
                   "sha256": _record_entry(mcq_bad)["sha256"],
                   "source_chapter": "卷二·论坐命宫",
                   "snapshot_path": RAW025_REL,
                   "snapshot_sha256": snap_sha, "historical_basis": None}
        assert gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev,
            [rec_rule, rec_bad]) == "REVISION_SOURCE_UNVERIFIABLE"
