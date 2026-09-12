"""§5-R 修订溯源双轨契约 TDD 测试（设计 v29.3 §5-R；权威条款见设计文档）。"""
from __future__ import annotations

import hashlib
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
import sys

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
        # R₀ 后真实仓库登记/锚/manifest 可能非空，fixture 必须从 genesis
        # 空状态开始——否则 append_line 叠加真实行 → 链头/常量错配（R₀
        # 复审暴露）。三文件删除留作未提交改动，随测试首个 commit 纳入。
        for rel in (REGISTRY_REL, ANCHOR_REL, MANIFEST_REL):
            p = self.path / rel
            if p.exists():
                p.unlink()
        # C₁ 后真实聚合含修订记录（R25 2 rule + 2 mcq），worktree 继承会
        # 与 freeze 基线失衡 → 分区等式 REVISION_PARTITION_MISMATCH（C₁
        # 复审暴露）。与登记/锚/manifest 同理归零：数据文件重置为冻结基点
        # 内容（== freeze 记录），随 T 提交（git add -A）纳入。
        for rel in ("knowledge_base/classic_texts/sanmingtonghui/all_rules.json",
                    "knowledge_base/classic_texts/sanmingtonghui/all_mcq.jsonl"):
            self.write(rel, _git(
                ROOT, "show",
                f"{REVISION_GENESIS['freeze_base_commit']}:{rel}").encode("utf-8"))
        self.sync_synthetic_t()

    def sync_synthetic_t(self) -> None:
        """复制主工作区当前待测脚本字节入 worktree；有差异才提交合成 T，
        无差异（代码已提交——干净 CI 命中）则保持 HEAD 为 T（P0-2：普通
        `git commit` 在无改动时会失败，须先查 `status --porcelain`）。"""
        for rel in ("scripts/generate_quality_report.py",
                    "scripts/classic_artifacts.py"):
            self.write(rel, (ROOT / rel).read_bytes())
        # R₀ 后真实脚本信任根常量绑定真实登记/锚链，fixture 须回 genesis
        # 空状态（与 __init__ 的登记/锚/manifest 归零一致）——否则脚本
        # 常量与 worktree 空链错配 → CHAIN_STALE/TOOLCHAIN_INVALID。
        self.replace_constant("REVISION_ANCHOR_HEAD", GENESIS_SHA)
        self.replace_constant("TOOLCHAIN_REGISTRY_HEAD", GENESIS_SHA)
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
            "source_chapter": "卷二·论坐命宫",
            "difficulty": "medium", "category": "格局"}


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
        """信任根不变量：REVISION_ANCHOR_HEAD == genesis（尚无 V 登记）；
        TOOLCHAIN_REGISTRY_HEAD == @HEAD 登记文件重算链头（R₀ 前空登记链
        == genesis；R₀ 登记后绑定登记链头——与 _registry_head 一致）。"""
        assert gqr.REVISION_ANCHOR_HEAD == GENESIS_SHA
        assert gqr.TOOLCHAIN_REGISTRY_HEAD == gqr._registry_head(ROOT)

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
    ACCEPTED），再篡改/删除 evidence 钉住的源（raw_025 / source_manifest）
    → ⑥ 逐章 sha / OID+SHA 不符 → SOURCE_UNVERIFIABLE（删除同样稳定报错，
    不抛 RuntimeError）。
    ⑦ 内容检查无法在默认 rail 单点触发——未验收新增批次被 ④ UNACCEPTED
    拦截、已验收批次记录被改被 ⑤ PARTITION_MISMATCH 拦截；故直接测
    _source_identity_and_content 纯函数（构造已验 source 状态 + 合法
    ⑥ 前置的 manifest_recs），每个负向测试先跑同状态 good 对照断言 None，
    再断言坏例 == SOURCE_UNVERIFIABLE（证明 ⑥ 通过、⑦ 才是拦截点）。
    historical_basis（P0-1，设计 5-R.2）：真实 git show <commit>:<path>
    重算，按章过滤 + canonical sha 匹配恰好 1 条；commit/path 不存在、
    零/多匹配、SHA 不符均拒绝，不信任 match_count。
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

    # ---- P0-2 入口级：删除源文件 → 稳定错误码（不抛 RuntimeError）----

    def test_source_manifest_deleted(self, rail_wt, monkeypatch):
        """P0-2：V₁ 后删除 source_manifest.json → ⑥-1 rev-parse 缺失 →
        稳定 REVISION_SOURCE_UNVERIFIABLE（异常不冒泡）。"""
        self._v1(rail_wt, monkeypatch)
        (rail_wt.path / (SNAP_REL + "/source_manifest.json")).unlink()
        rail_wt.commit("deleted source_manifest")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_SOURCE_UNVERIFIABLE"

    def test_source_raw025_deleted(self, rail_wt, monkeypatch):
        """P0-2：V₁ 后删除 raw_025.txt → ⑥ 逐章 blob 缺失 → 稳定
        REVISION_SOURCE_UNVERIFIABLE（异常不冒泡）。"""
        self._v1(rail_wt, monkeypatch)
        (rail_wt.path / RAW025_REL).unlink()
        rail_wt.commit("deleted raw025")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_SOURCE_UNVERIFIABLE"

    # ---- 非阻断补证：OID 匹配、SHA 不匹配（⑥-2 分支独立触发）----

    def test_source_manifest_sha_branch(self, rail_wt):
        """⑥-2：OID 匹配（真实 HEAD blob OID）但钉住 blob sha256 不符 →
        SOURCE_UNVERIFIABLE。good 对照（双身份均真实）先断言 None，证明
        ⑥-2 分支独立拦截、非 ⑥-1 抢先。"""
        core = TestRailCore()
        manifest = core._make_c1(rail_wt)
        rail_wt.commit("C1")
        recs = [r for b in manifest["batches"] for r in b["records"]]
        ev = _evidence_of(rail_wt)
        assert gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev, recs) is None
        sc = dict(ev["source_chain"]["sanmingtonghui"])
        sc["manifest_file_sha256"] = "0" * 64  # OID 不动、仅 SHA 伪造
        ev["source_chain"]["sanmingtonghui"] = sc
        err = gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev, recs)
        assert err == "REVISION_SOURCE_UNVERIFIABLE"

    # ---- P0-2：空/非字符串引文、非字符串 answer（异常不冒泡）----

    def test_original_text_empty_rejected(self, rail_wt):
        """⑦：rule.original_text 缺失/非字符串/去空白为空 → 拒绝（空串恒为
        子串，不得放行）。good 对照（probe）→ None。"""
        snap_sha = _sha256(rail_wt.blob("HEAD", RAW025_REL))
        src_text = rail_wt.blob("HEAD", RAW025_REL).decode("utf-8", "replace")
        probe = re.sub(r"\s+", "", src_text)[:30]
        good = _mk_rule("smth_t_good", "卷二·论坐命宫", "规则")
        good["original_text"] = probe
        bads = []
        for i, ot in (("smth_t_empty", ""), ("smth_t_ws", " \t\n "),
                      ("smth_t_int", 42)):
            r = _mk_rule(i, "卷二·论坐命宫", "规则")
            r["original_text"] = ot
            bads.append(r)
        from scripts.generate_classic_historical_freeze import _record_entry
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        arr = json.loads(rail_wt.blob("HEAD", rules_rel).decode("utf-8"))
        arr.append(good)
        arr.extend(bads)
        rail_wt.write(rules_rel,
                      json.dumps(arr, ensure_ascii=False).encode("utf-8"))
        rail_wt.commit("empty/ws/non-string original_text head records")
        ev = _evidence_of(rail_wt)

        def _rec(r):
            return {"kind": "rule", "id": r["id"],
                    "sha256": _record_entry(r)["sha256"],
                    "source_chapter": "卷二·论坐命宫",
                    "snapshot_path": RAW025_REL,
                    "snapshot_sha256": snap_sha, "historical_basis": None}
        assert gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev, [_rec(good)]) is None
        for b in bads:
            err = gqr._source_identity_and_content(
                rail_wt.path, "sanmingtonghui", ev, [_rec(b)])
            assert err == "REVISION_SOURCE_UNVERIFIABLE", (b["id"], err)

    def test_mcq_answer_nonstring_rejected(self, rail_wt):
        """⑦：mcq.answer 非字符串（None）→ SOURCE_UNVERIFIABLE（G8 形态
        需字符串前置判断，不抛 TypeError）。good 对照（answer='A'）→ None。"""
        snap_sha = _sha256(rail_wt.blob("HEAD", RAW025_REL))
        src_text = rail_wt.blob("HEAD", RAW025_REL).decode("utf-8", "replace")
        probe = re.sub(r"\s+", "", src_text)[:30]
        rule = _mk_rule("smth_t_001", "卷二·论坐命宫", "规则")
        rule["original_text"] = probe
        mcq_ok = _mk_mcq("smth_t_001_m1", "smth_t_001")
        mcq_bad = _mk_mcq("smth_t_001_m2", "smth_t_001")
        mcq_bad["answer"] = None
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
        rail_wt.commit("non-string answer head records")
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
        err = gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev,
            [rec_rule, rec_bad])
        assert err == "REVISION_SOURCE_UNVERIFIABLE"

    # ---- P0-1：historical_basis 真实 Git 重算（设计 5-R.2）----

    def test_historical_basis_consumed(self, rail_wt):
        """P0-1：historical_basis 从 git show <commit>:<path> 重算——按
        source_chapter 过滤后与 record_content_sha256（该历史记录 _canonical
        序列化字节 SHA-256）匹配必须恰好 1 条。正向（恰 1 条）→ None；
        commit 不存在 / path 不存在 / 零匹配（错章）/ 多匹配（同内容 2 条）/
        SHA 不符 → 均 SOURCE_UNVERIFIABLE；不信任 match_count。"""
        core = TestRailCore()
        manifest = core._make_c1(rail_wt)
        c1 = rail_wt.commit("C1")
        ev = _evidence_of(rail_wt)
        snap_sha = _sha256(rail_wt.blob("HEAD", RAW025_REL))
        # good 与 _make_c1 写入 HEAD 的规则逐字段一致（_mk_rule + probe 覆写）
        src_text = rail_wt.blob("HEAD", RAW025_REL).decode("utf-8", "replace")
        good = _mk_rule("smth_t_001", "卷二·论坐命宫", "测试修订规则")
        good["original_text"] = re.sub(r"\s+", "", src_text)[:30]
        from scripts.generate_classic_historical_freeze import _record_entry
        hrule = _mk_rule("hist_001", "卷二·论坐命宫", "历史恢复规则")
        S = _sha256(_canonical(hrule).encode("utf-8"))
        hist_dir = "knowledge_base/classic_texts/sanmingtonghui/formal/kb_hist"
        rail_wt.write(hist_dir + "/histA.json",
                      json.dumps([hrule], ensure_ascii=False).encode("utf-8"))
        rail_wt.write(hist_dir + "/histB.json",
                      json.dumps([hrule, hrule], ensure_ascii=False)
                      .encode("utf-8"))
        H = rail_wt.commit("historical basis fixtures")
        histA, histB = hist_dir + "/histA.json", hist_dir + "/histB.json"

        def _rec(hb):
            return {"kind": "rule", "id": good["id"],
                    "sha256": _record_entry(good)["sha256"],
                    "source_chapter": "卷二·论坐命宫",
                    "snapshot_path": RAW025_REL,
                    "snapshot_sha256": snap_sha, "historical_basis": hb}

        def _hb(commit=H, path=histA, chapter="卷二·论坐命宫",
                sha=S, count=1):
            return {"commit": commit, "path": path, "source_chapter": chapter,
                    "record_content_sha256": sha, "match_count": count}

        # 正向：恰 1 条匹配 → 通过（⑥⑦ + historical 重算全过）
        assert gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev, [_rec(_hb())]) is None
        # 负向：commit 不存在
        err = gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev,
            [_rec(_hb(commit="0" * 40))])
        assert err == "REVISION_SOURCE_UNVERIFIABLE", err
        # 负向：path 不存在
        err = gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev,
            [_rec(_hb(path=hist_dir + "/nope.json"))])
        assert err == "REVISION_SOURCE_UNVERIFIABLE", err
        # 负向：零匹配（章过滤后无记录）
        err = gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev,
            [_rec(_hb(chapter="卷一·原造化之始"))])
        assert err == "REVISION_SOURCE_UNVERIFIABLE", err
        # 负向：多匹配（同内容 2 条）
        err = gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev,
            [_rec(_hb(path=histB))])
        assert err == "REVISION_SOURCE_UNVERIFIABLE", err
        # 负向：SHA 不符（record_content_sha256 与历史记录不匹配）
        err = gqr._source_identity_and_content(
            rail_wt.path, "sanmingtonghui", ev,
            [_rec(_hb(sha="0" * 64))])
        assert err == "REVISION_SOURCE_UNVERIFIABLE", err

# ---- Task 5：VALID 书构造 helper（复制自 test_classic_distillation_quality_report
# ---- .py::_setup_passing_book 的 provenance 写入段；计划 Task 5 注记：勿跨文件
# ---- import 私有函数，故整段落地本文件）-------------------------------------

def _git_blob_sha(file_path: Path) -> str:
    r = subprocess.run(["git", "hash-object", str(file_path)],
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else ""


def _make_full_rule(id: str, chapter: str, rule_text: str) -> dict:
    return {"id": id, "category": "test", "subject": "test", "condition": "test",
            "rule": rule_text, "original_text": rule_text, "source_book": "test",
            "source_chapter": chapter}


def _make_full_mcq(id: str, question: str, answer: str, source_rule_id: str) -> dict:
    return {"id": id, "question": question,
            "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
            "answer": answer, "explanation": "test",
            "source_rule_id": source_rule_id, "difficulty": "easy",
            "category": "test"}


def _make_passing_book(base: Path, dir_key: str, head: str) -> Path:
    """构造通过全部 validator 门禁的书 + provenance.json（本文件版
    _setup_passing_book）。与 _setup_passing_book 的差异：anchor_commit /
    input_baseline_commit 用调用方给定的真实存在提交 head
    （validate_provenance 的 git_root 存在性检查；linked worktree 与主仓
    共享对象库）；既有 raw_*.txt 先全部删除（validate 按 glob 全覆盖校验
    raw_text_shas）；fill 操作 target 白名单仅
    zipingzhenquan/qiongtongbaojian（run_manifest 校验）——dir_key 须取
    白名单内书名。"""
    from scripts.classic_artifacts import (
        CODE_FILE_NAMES, mcq_record_sha256, sha256_file)
    scripts_dir = ROOT / "scripts"
    p = base / dir_key
    p.mkdir(parents=True, exist_ok=True)
    for f in p.glob("raw_*.txt"):
        f.unlink()
    rules = [_make_full_rule("r1", "ch1", "甲木参天"),
             _make_full_rule("r2", "ch1", "乙木系甲")]
    mcqs = [_make_full_mcq("m1", "问题一", "A", "r1"),
            _make_full_mcq("m2", "问题二", "B", "r2"),
            _make_full_mcq("m3", "问题三", "C", "r1"),
            _make_full_mcq("m4", "问题四", "D", "r2")]
    (p / "all_rules.json").write_text(
        json.dumps(rules, ensure_ascii=False), encoding="utf-8")
    (p / "all_mcq.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mcqs),
        encoding="utf-8")
    (p / "raw_001.txt").write_text("甲木参天乙木系甲", encoding="utf-8")
    (p / "quarantine_rules.jsonl").write_text("", encoding="utf-8")
    (p / "quarantine_mcq.jsonl").write_text("", encoding="utf-8")
    (p / "remediation_meta.json").write_text("{}", encoding="utf-8")
    names = ("all_rules.json", "all_mcq.jsonl", "quarantine_rules.jsonl",
             "quarantine_mcq.jsonl", "remediation_meta.json")
    from scripts.distill_lib import (
        canonical_prompt_sha256, canonical_config_sha256, FROZEN_MODEL_CONFIG,
        compute_code_sha, ledger_code_files)
    rules_payload = json.dumps(rules, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")
    rules_io_sha = hashlib.sha256(rules_payload).hexdigest()
    rm_manifest = {
        "immutable": {
            "targets": [dir_key],
            "frozen_config_sha256": canonical_config_sha256(),
            "frozen_prompt_sha256": canonical_prompt_sha256(),
            "input_files": {
                dir_key: {"all_rules.json_sha256": sha256_file(p / "all_rules.json"),
                          "all_rules.json_bytes": len((p / "all_rules.json").read_bytes()),
                          "pre_run_mcq_ids": [], "operation": "fill",
                          "preserves_existing_mcqs": True},
            },
        },
        "mutable": {},
    }
    rm_sha = hashlib.sha256(
        json.dumps(rm_manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    ident_code_sha = compute_code_sha(ledger_code_files(scripts_dir, scripts_dir.parent))
    ident_rules_sha = rm_sha
    ident_run_id = hashlib.sha256(
        (ident_code_sha + ":" + ident_rules_sha).encode("utf-8")).hexdigest()[:16]
    run_manifest = {
        "manifest": rm_manifest,
        "manifest_sha256": rm_sha,
        "run_id": ident_run_id,
        "code_sha": ident_code_sha,
        "rules_sha": ident_rules_sha,
    }
    real_head = head
    provenance = {
        "generated_at": "2025-01-01",
        "anchor_commit": real_head,
        "anchor_commit_verified": True,
        "no_api": True,
        "input_baseline_commit": real_head,
        "worktree_dirty": False,
        "code_fingerprint": "a" * 64,
        "upstream_provenance_status": "unavailable",
        "file_shas": {n: sha256_file(p / n) for n in names},
        "code_shas": {n: sha256_file(scripts_dir / n) for n in CODE_FILE_NAMES
                      if (scripts_dir / n).exists()},
        "raw_text_shas": {"raw_001.txt": sha256_file(p / "raw_001.txt")},
        "input_baseline_blob_shas": {"raw_001.txt": _git_blob_sha(p / "raw_001.txt")},
        "api_generation": {
            "run_id": ident_run_id,
            "code_sha": ident_code_sha,
            "rules_sha": ident_rules_sha,
            "rules_input_sha": rules_io_sha,
            "rules_output_sha": rules_io_sha,
            "rules_added": 0,
            "mcq_output_sha": sha256_file(p / "all_mcq.jsonl"),
            "generated_mcq_sha256_by_id": {
                m["id"]: mcq_record_sha256(m) for m in mcqs
            },
            "prompt_sha256": canonical_prompt_sha256(),
            "config_sha256": canonical_config_sha256(),
            "script_sha256": sha256_file(scripts_dir / "distill_lib.py"),
            "provider": FROZEN_MODEL_CONFIG["provider"],
            "model": FROZEN_MODEL_CONFIG["model"],
            "thinking_mode": FROZEN_MODEL_CONFIG["thinking_mode"],
            "temperature": FROZEN_MODEL_CONFIG["temperature"],
            "calls_made": 4,
            "accepted": 4,
            "skipped": 0,
            "verification_level": "full",
            "operation": "fill",
            "preserves_existing_mcqs": True,
            "pre_run_mcq_ids": [],
            "completed": True,
        },
        "run_manifest": run_manifest,
        "run_manifest_sha256": rm_sha,
    }
    (p / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False), encoding="utf-8")
    return p


def _setup_passing_book_in_wt(wt: RailWorktree, dir_key: str = "zipingzhenquan") -> Path:
    return _make_passing_book(
        wt.path / "knowledge_base" / "classic_texts", dir_key, wt.rev("HEAD"))


class TestRailIntegration:
    """Task 5：E3 并入 rail + 5-R.10 状态矩阵 + 报告字段 + 默认模式闭环。"""

    def test_admissibility_consumes_rail_single_call(self, rail_wt, monkeypatch):
        """evaluate_provenance_admissibility 只调 rail 一次、消费其结果；
        E3_ok = rail ⑤ 结果；新增 revision_state / revision_provenance_valid。"""
        calls = []
        real = gqr.evaluate_revision_rail

        def spy(git_root, book, freeze, evidence, candidate_batch_id=None):
            calls.append(book)
            return real(git_root, book, freeze, evidence,
                        candidate_batch_id=candidate_batch_id)

        monkeypatch.setattr(gqr, "evaluate_revision_rail", spy)
        adm = gqr.evaluate_provenance_admissibility(
            rail_wt.path / "knowledge_base" / "classic_texts" / "sanmingtonghui",
            rail_wt.path)
        assert calls == ["sanmingtonghui"]
        assert adm["revision_state"] == "NONE"
        assert adm["revision_provenance_valid"] is False  # NONE != ACCEPTED
        assert adm["E3_ok"] is True

    def test_matrix_valid_book_with_manifest_unsupported(self, rail_wt):
        """5-R.10 VALID×manifest 存在 → UNSUPPORTED_STATE（唯一行为修改）。
        构造 VALID：为 zipingzhenquan（fill target 白名单内）写与其磁盘工件
        一致的 provenance.json。"""
        from scripts.classic_artifacts import EMPTY_BASELINE_MANIFEST
        book_dir = _setup_passing_book_in_wt(rail_wt, "zipingzhenquan")
        rail_wt.write(
            "knowledge_base/classic_texts/zipingzhenquan/revision_manifest.json",
            _canonical_bytes(EMPTY_BASELINE_MANIFEST) + b"\n")
        rail_wt.commit("VALID ditiansui + revision manifest")
        adm = gqr.evaluate_provenance_admissibility(book_dir, rail_wt.path)
        assert adm["provenance_state"] == "VALID"
        assert adm["exemption_error_code"] == "REVISION_UNSUPPORTED_STATE"
        assert adm["provenance_admissible"] is False

    def test_matrix_missing_with_anchors_manifest_wiped(self, rail_wt, monkeypatch):
        """5-R.10 MISSING × manifest 不存在 × 有已验收锚 → CHAIN_STALE。"""
        TestRailSourceAndContent()._v1(rail_wt, monkeypatch)
        _git(rail_wt.path, "rm", MANIFEST_REL)
        rail_wt.commit("wipe manifest")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_CHAIN_STALE"

    def test_default_mode_accepted_flow(self, rail_wt, monkeypatch):
        """完整默认模式正循环：C₁+V₁ 后 ACCEPTED、E0-E2 过、admissible。"""
        TestRailSourceAndContent()._v1(rail_wt, monkeypatch)
        adm = gqr.evaluate_provenance_admissibility(
            rail_wt.path / "knowledge_base" / "classic_texts" / "sanmingtonghui",
            rail_wt.path)
        assert adm["revision_state"] == "ACCEPTED"
        assert adm["revision_provenance_valid"] is True
        assert adm["provenance_admissible"] is True
        assert adm["E0_ok"] and adm["E1_ok"] and adm["E2_ok"] and adm["E3_ok"]

class TestRailReportTopLevel:
    """Task 5 复审 P0：报告顶层修订字段（设计 A.1）——从已计算的三命通会
    结果派生、不再调 rail；E0/E1/E2 提前失败（rail 未评）→ 顶层 FAILED
    （顶层枚举仅允许四值，不得写 None）；每书 rail 恰调用一次；
    source BLOCKED 优先于修订字段的 status/exit。"""

    FOUR = ("ditiansui", "qiongtongbaojian", "sanmingtonghui", "zipingzhenquan")

    def _four_missing_books(self, tmp_path):
        head = _git(ROOT, "rev-parse", "HEAD").strip()
        for k in self.FOUR:
            p = _make_passing_book(tmp_path, k, head)
            (p / "provenance.json").unlink()  # → MISSING（走 E0-E2 + rail）

    _NO_ARCHIVE = object()  # 哨兵：区分"未传（默认 tmp_path）"与"显式 None"

    def _stub_source(self, monkeypatch, status="PASS", reason=None):
        monkeypatch.setattr(
            "scripts.generate_quality_report._run_source_chain_check",
            lambda gr, ar: {"status": status, "reason": reason})

    def _run_report(self, tmp_path, monkeypatch, books=None,
                    archive_root=_NO_ARCHIVE, git_root=ROOT):
        monkeypatch.setattr("scripts.generate_quality_report._find_git_root",
                            lambda: git_root)
        return gqr.generate_report(
            base_path=tmp_path,
            books=books if books is not None else {k: "书" for k in self.FOUR},
            archive_root=(tmp_path if archive_root is self._NO_ARCHIVE
                          else archive_root))

    def test_report_top_level_none_and_single_rail_call_per_book(
            self, tmp_path, monkeypatch, rail_wt):
        """四书 MISSING + 真实 rail → 顶层 NONE；每书 rail 恰一次（不重复）。
        git_root 用隔离基线 worktree（rail_wt）而非真实 ROOT——C₁
        后真实仓库含未接纳修订，rail 将返 UNACCEPTED 而非 NONE。"""
        self._four_missing_books(tmp_path)
        calls = []
        real = gqr.evaluate_revision_rail

        def spy(git_root, book, freeze, evidence, candidate_batch_id=None):
            calls.append(book)
            return real(git_root, book, freeze, evidence,
                        candidate_batch_id=candidate_batch_id)

        monkeypatch.setattr(gqr, "evaluate_revision_rail", spy)
        self._stub_source(monkeypatch)
        report, exit_code = self._run_report(tmp_path, monkeypatch,
                                          git_root=rail_wt.path)
        assert len(calls) == 4 and set(calls) == set(self.FOUR)
        assert report["revision_state"] == "NONE"
        assert report["revision_provenance_valid"] is False
        assert report["provenance_admissible_all"] is True
        assert report["status"] == "FAIL"  # 三书 S 口径 source FAIL
        assert exit_code == 1

    def test_report_top_level_accepted(self, tmp_path, monkeypatch):
        """三命通会 rail ACCEPTED（fake rail 记录调用次数）→ 顶层 ACCEPTED、
        revision_provenance_valid=True。"""
        self._four_missing_books(tmp_path)
        calls = []

        def fake_rail(git_root, book, freeze, evidence, candidate_batch_id=None):
            calls.append(book)
            return {"ok": True, "revision_state": "ACCEPTED",
                    "error_code": None, "e3_ok": True}

        monkeypatch.setattr(gqr, "evaluate_revision_rail", fake_rail)
        self._stub_source(monkeypatch)
        report, exit_code = self._run_report(tmp_path, monkeypatch)
        assert len(calls) == 4  # 每书一次，不重复
        assert report["revision_state"] == "ACCEPTED"
        assert report["revision_provenance_valid"] is True
        assert report["provenance_admissible_all"] is True
        assert exit_code == 1  # source FAIL 仍压 overall（S 口径）

    def test_report_top_level_revision_failed(self, tmp_path, monkeypatch):
        """rail FAILED → 顶层 FAILED、revision_provenance_valid=False、
        provenance_admissible_all=False。"""
        self._four_missing_books(tmp_path)
        monkeypatch.setattr(
            gqr, "evaluate_revision_rail",
            lambda gr, book, fr, ev, candidate_batch_id=None: {
                "ok": False, "revision_state": "FAILED",
                "error_code": "REVISION_SOURCE_UNVERIFIABLE", "e3_ok": False})
        self._stub_source(monkeypatch)
        report, exit_code = self._run_report(tmp_path, monkeypatch)
        assert report["revision_state"] == "FAILED"
        assert report["revision_provenance_valid"] is False
        assert report["provenance_admissible_all"] is False
        assert report["status"] == "FAIL"
        assert exit_code == 1

    def test_report_top_level_failed_when_e0_short_circuits(
            self, tmp_path, monkeypatch):
        """E0 提前失败 → rail 未运行（revision_state=None）→ 顶层必须
        fail-closed 写 FAILED（不得把 None 写入四值枚举）。"""
        head = _git(ROOT, "rev-parse", "HEAD").strip()
        p = _make_passing_book(tmp_path, "sanmingtonghui", head)
        (p / "provenance.json").unlink()
        rail_calls = []
        monkeypatch.setattr(
            gqr, "evaluate_revision_rail",
            lambda gr, book, fr, ev, candidate_batch_id=None:
                rail_calls.append(book) or {})
        monkeypatch.setattr(
            "scripts.generate_quality_report._e0_static_check",
            lambda gr: {"ok": False, "error_code": "FREEZE_STATIC_MISMATCH"})
        self._stub_source(monkeypatch)
        report, exit_code = self._run_report(
            tmp_path, monkeypatch, books={"sanmingtonghui": "三命通会"})
        assert rail_calls == []  # E0 短路，rail 未运行
        assert report["revision_state"] == "FAILED"
        assert report["revision_provenance_valid"] is False
        assert exit_code == 1

    def test_report_source_blocked_takes_precedence(self, tmp_path, monkeypatch,
                                                        rail_wt):
        """source BLOCKED → status=BLOCKED/exit 3 优先；顶层 revision_state
        仍照实输出真实 rail 结果（NONE），不被 BLOCKED 改写。
        git_root 用隔离 worktree（见同类上一测试）。"""
        head = _git(ROOT, "rev-parse", "HEAD").strip()
        p = _make_passing_book(tmp_path, "sanmingtonghui", head)
        (p / "provenance.json").unlink()
        report, exit_code = self._run_report(
            tmp_path, monkeypatch, books={"sanmingtonghui": "三命通会"},
            archive_root=None, git_root=rail_wt.path)  # 显式 None → BLOCKED(archive_root_missing)
        assert report["status"] == "BLOCKED"
        assert report["overall_pass"] is False
        assert exit_code == 3
        assert (report["books"]["sanmingtonghui"]["source_blocked_reason"]
                == "archive_root_missing")
        assert report["revision_state"] == "NONE"
        assert report["revision_provenance_valid"] is False

class TestFieldSchema:
    def test_report_field_schema_matches_appendix(self):
        """内嵌表与附录 A 逐字段一致（schema_version/字段名/类型/方向/上限）。"""
        s = gqr.REPORT_FIELD_SCHEMA
        assert s["schema_version"] == "1.0"
        top = {f["name"] for f in s["top_level"]}
        assert {"status", "overall_pass", "revision_state",
                "revision_provenance_valid", "approval_b2_constant_valid",
                "validator_ran_live"} <= top
        g7 = [f for f in s["book_gate_details"]
              if f["name"] == "G7_chapter_complete.missing_count"][0]
        assert g7["type"] == "int" and g7["direction"] == "increase_bad"
        assert g7["upper_bound"]["sanmingtonghui"] == 303
        g6i = [f for f in s["book_gate_details"]
               if f["name"] == "G6_answer_dist.invalid_answers"][0]
        assert g6i["pass_value"] == 0

    def test_process_stage_fields_exempt_from_degradation(self):
        """流程阶段字段退出通用退化比较（v29.2 P0）：候选模式合法推进
        ACCEPTED/true → PENDING_ACCEPTANCE/false 不判退化。"""
        cmp = gqr.compare_gate_fields
        assert cmp(
            {"revision_state": "ACCEPTED", "revision_provenance_valid": True},
            {"revision_state": "PENDING_ACCEPTANCE",
             "revision_provenance_valid": False}, mode="candidate") == []

    def test_degradation_detected(self):
        cmp = gqr.compare_gate_fields
        bad = cmp(
            {"books": {"x": {"gates": {"G3_schema": True}}}},
            {"books": {"x": {"gates": {"G3_schema": False}}}}, mode="candidate")
        assert bad == ["x.G3_schema: PASS->FAIL"]

    def test_allowed_red_improvement_accepted_cap_enforced(self):
        cmp = gqr.compare_gate_fields
        base = {"books": {"sanmingtonghui": {"gate_details": {
            "G7_chapter_complete": {"missing_count": 303}}}}}
        improved = {"books": {"sanmingtonghui": {"gate_details": {
            "G7_chapter_complete": {"missing_count": 302}}}}}
        assert cmp(base, improved, mode="candidate") == []
        worse = {"books": {"sanmingtonghui": {"gate_details": {
            "G7_chapter_complete": {"missing_count": 304}}}}}
        assert cmp(base, worse, mode="candidate") == [
            "sanmingtonghui.G7_chapter_complete.missing_count: 304>303"]

    def test_b_minus_n_field_removed_rejected(self):
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"gates": {"G3_schema": True}}}}
        cand = {"books": {"x": {"gates": {}}}}  # 旧有门禁字段消失
        assert cmp(base, cand, mode="candidate") == ["x.G3_schema: removed"]

    def test_allowed_red_relative_increase_rejected(self):
        """P0-1：允许红项相对恶化——missing_count 10→11（未超冻结上限 303）
        也是相对增大，必须拒绝（不能只查上限、跳过与基线比较）。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"sanmingtonghui": {"gate_details": {
            "G7_chapter_complete": {"missing_count": 10}}}}}
        worse = {"books": {"sanmingtonghui": {"gate_details": {
            "G7_chapter_complete": {"missing_count": 11}}}}}
        assert cmp(base, worse, mode="candidate") == [
            "sanmingtonghui.G7_chapter_complete.missing_count: 11>10"]

    def test_detail_field_removed_rejected(self):
        """P0-2：明细字段 B−N——基线含 G3_schema.bad_rules、候选缺该键 → removed。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"gate_details": {"G3_schema": {
            "bad_rules": 1, "bad_mcq": 0, "parse_errors": 0}}}}}
        cand = {"books": {"x": {"gate_details": {"G3_schema": {
            "bad_mcq": 0, "parse_errors": 0}}}}}
        assert cmp(base, cand, mode="candidate") == [
            "x.G3_schema.bad_rules: removed"]

    def test_detail_field_new_in_candidate_cap_enforced(self):
        """P0-2：明细字段 N−B——候选新增 G7 missing_count（sm）超冻结上限
        303 → 拒（新字段按 schema 上限校验，不得静默跳过）。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"sanmingtonghui": {"gate_details": {}}}}
        cand = {"books": {"sanmingtonghui": {"gate_details": {
            "G7_chapter_complete": {"missing_count": 400}}}}}
        assert cmp(base, cand, mode="candidate") == [
            "sanmingtonghui.G7_chapter_complete.missing_count: 400>303"]

    def test_detail_field_type_changed_rejected(self):
        """P0-2：类型/语义校验——同名字段改类型（int → str）→ 拒（A.0）。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"gate_details": {"G3_schema": {"bad_rules": 0}}}}}
        cand = {"books": {"x": {"gate_details": {"G3_schema": {"bad_rules": "0"}}}}}
        assert cmp(base, cand, mode="candidate") == [
            "x.G3_schema.bad_rules: type-changed"]

    def test_a4_provenance_admissible_degradation_rejected(self):
        """P0-2：A.4 逐书 provenance_admissible true→false → 拒
        （不能靠当前布尔门替代完整字段契约）。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"provenance_admissible": True}}}
        cand = {"books": {"x": {"provenance_admissible": False}}}
        assert cmp(base, cand, mode="candidate") == [
            "x.provenance_admissible: PASS->FAIL"]

    def test_a4_field_removed_rejected(self):
        """P0-2：A.4 字段 B−N——候选书缺 source_e2e_status → removed。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"source_e2e_status": "FAIL"}}}
        cand = {"books": {"x": {}}}
        assert cmp(base, cand, mode="candidate") == [
            "x.source_e2e_status: removed"]

    def test_a4_provenance_state_degrade_invalid_rejected(self):
        """P0-2：A.4 provenance_state 退化为 INVALID → 拒。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"provenance_state": "VALID"}}}
        cand = {"books": {"x": {"provenance_state": "INVALID"}}}
        assert cmp(base, cand, mode="candidate") == [
            "x.provenance_state: VALID->INVALID"]

    def test_detail_field_new_with_failure_value_rejected(self):
        """P0-1：明细 N−B 消费 pass_value——新增 G3_schema.bad_rules=1（非零）
        → 拒（新增错误计数须满足通过值 0）。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"gate_details": {"G3_schema": {
            "bad_mcq": 0, "parse_errors": 0}}}}}
        cand = {"books": {"x": {"gate_details": {"G3_schema": {
            "bad_rules": 1, "bad_mcq": 0, "parse_errors": 0}}}}}
        assert cmp(base, cand, mode="candidate") == [
            "x.G3_schema.bad_rules: new-invalid"]

    def test_new_gate_bool_must_be_pass(self):
        """P0-1：九门布尔 N−B——候选新增 G3_schema=false → 拒（新增布尔须 PASS）。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"gates": {}}}}
        cand = {"books": {"x": {"gates": {"G3_schema": False}}}}
        assert cmp(base, cand, mode="candidate") == [
            "x.G3_schema: new-invalid"]

    def test_new_gate_bool_strictly_true_required(self):
        """P0-2：新增门布尔须严格为 True——0 / "FAIL" 也拒（非仅字面量 False）。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"gates": {}}}}
        for bad_val in (0, "FAIL"):
            cand = {"books": {"x": {"gates": {"G3_schema": bad_val}}}}
            assert cmp(base, cand, mode="candidate") == [
                "x.G3_schema: new-invalid"]

    def test_gate_bool_type_changed_rejected(self):
        """P0-2：共有九门先验类型再比退化——候选 G3_schema=0（int）→ type-changed。"""
        cmp = gqr.compare_gate_fields
        base = {"books": {"x": {"gates": {"G3_schema": True}}}}
        cand = {"books": {"x": {"gates": {"G3_schema": 0}}}}
        assert cmp(base, cand, mode="candidate") == ["x.G3_schema: type-changed"]


_BOOK_META = {
    "ditiansui": "滴天髓",
    "zipingzhenquan": "子平真诠",
    "qiongtongbaojian": "穷通宝鉴",
    "sanmingtonghui": "三命通会",
}
_BOOK_GATE_KEYS = (
    "G1_rule_id_unique", "G2_mcq_id_unique", "G3_schema",
    "G4_source_rule_id", "G5_traceability", "G6_answer_dist",
    "G7_chapter_complete", "G8_mcq_well_formed", "G9_content_dedup")


def _passing_book(book: str) -> dict:
    """单书全绿形态：九门布尔全 True + 九门 gate_details 齐备 + 豁免链全过。"""
    return {
        "name": _BOOK_META[book],
        "dir": book,
        "all_gates_pass": True,
        "gates": {g: True for g in _BOOK_GATE_KEYS},
        "gate_details": {
            "G1_rule_id_unique": {"total": 1, "unique": 1, "duplicates": 0,
                                  "pass": True},
            "G2_mcq_id_unique": {"total": 4, "unique": 4, "duplicates": 0,
                                 "pass": True},
            "G3_schema": {"bad_rules": 0, "bad_mcq": 0, "parse_errors": 0,
                          "pass": True},
            "G4_source_rule_id": {"total_refs": 4, "bad": 0,
                                  "ambiguous_rule_ids": 0, "pass": True},
            "G5_traceability": {"total": 1, "untraceable": 0, "rate": 1.0,
                                "pass": True},
            # P0-4：G6 分布须与生产语义一致——A=100% 会被判越界 FAIL；
            # 用四字母各 25%（∈[0.18,0.32]），与 G2.total/G4.total_refs=4 同步。
            "G6_answer_dist": {"dist_pct": {"A": 0.25, "B": 0.25,
                                            "C": 0.25, "D": 0.25},
                               "invalid_answers": 0, "out_of_band": [],
                               "pass": True},
            # G7 形态随冻结事实：有章节列表的书（ziping/qiong/sm）为完整
            # 计数形态；无章节列表（ditiansui）为简化形态。
            "G7_chapter_complete": (
                {"expected": 1, "done": 1, "missing": [], "missing_count": 0,
                 "extra": [], "extra_count": 0, "pass": True}
                if book != "ditiansui"
                else {"pass": True, "reason": "no chapter_list"}),
            "G8_mcq_well_formed": {"malformed": 0, "pass": True},
            "G9_content_dedup": {"rule_text_duplicate_groups": 0,
                                 "rule_text_duplicate_count": 0,
                                 "rule_text_duplicate_samples": {},
                                 "mcq_question_duplicates": 0, "pass": True},
        },
        "provenance_state": "MISSING",
        "provenance_missing": True,
        "provenance_ok": False,
        "historical_exemption_valid": True,
        "provenance_admissible": True,
        "exemption_error_code": None,
        "exemption_stages": {"E0_ok": True, "E1_ok": True,
                             "E2_ok": True, "E3_ok": True},
        "source_e2e_status": "FAIL" if book != "sanmingtonghui" else "PASS",
        "source_blocked_reason": None,
        "end_to_end_provenance": False,
    }


def _baseline_report_fixture(first_batch: bool = True) -> dict:
    """03c02bb 时点真实形态的**四书完整合格**基线报告（键集/字段以
    03c02bb 自带脚本 `generate_report` 重跑产出实测为准——该时点跟踪的
    QUALITY_REPORT.json 为旧脚本产物，重跑前被新生成守卫删除，不作
    判据；值合成）。

    合格形态（设计 5-R.8）：rc==1 时 status=FAIL ∧ 失败项 ⊆ 允许红项
    （仅 sanmingtonghui.G7 missing_count=303，附录 A.3 上限）；其余全绿；
    三书 source_e2e=FAIL（S 口径）、sanmingtonghui=PASS；E0-E2 全过；
    approval_b2_constant_valid=true；validator_ran_live=true。
    首批例外：无修订字段；first_batch=False 时追加
    revision_state=ACCEPTED ∧ revision_provenance_valid=true。
    """
    books = {b: _passing_book(b) for b in _BOOK_META}
    books["sanmingtonghui"]["all_gates_pass"] = False
    books["sanmingtonghui"]["gates"]["G7_chapter_complete"] = False
    books["sanmingtonghui"]["gate_details"]["G7_chapter_complete"] = {
        "expected": 383, "done": 80, "missing": [], "missing_count": 303,
        "extra": [], "extra_count": 0, "pass": False}
    rep = {
        "generated_at": "2026-09-07T11:04:08",
        "known_limitations": [],
        "validator": "scripts/validate_classic_distillation.py",
        "validator_code_sha256": "0" * 64,
        "validator_ran_live": True,
        "books": books,
        "remediation_pass": False,
        "end_to_end_pass": False,
        "content_gates_pass": False,       # sanmingtonghui G7 红项
        "provenance_admissible_all": True,
        "approval_b2_constant_valid": True,
        "source_e2e_status": "FAIL",       # 三书 S 口径（生成器 §7 聚合必有此键，round-4）
        "source_e2e_pass": False,
        "overall_pass": False,
        "status": "FAIL",
    }
    if not first_batch:
        rep["revision_state"] = "ACCEPTED"
        rep["revision_provenance_valid"] = True
    return rep


def _blocked_report_fixture(reason: str = "archive_root_missing") -> dict:
    """round-4 P0-1：生产形态 source-BLOCKED 质量报告。run_baseline 读取
    的是完整 QUALITY_REPORT.json——生成器 §7 顶层状态机：任一书
    source_e2e_status=BLOCKED → 顶层 source_e2e_status=BLOCKED ∧
    source_e2e_pass=False ∧ status=BLOCKED ∧ overall_pass=False（exit 3）；
    reason 在逐书 source_blocked_reason，不在顶层。"""
    rep = _baseline_report_fixture()
    sm = rep["books"]["sanmingtonghui"]
    sm["source_e2e_status"] = "BLOCKED"
    sm["source_blocked_reason"] = reason
    rep["source_e2e_status"] = "BLOCKED"
    rep["source_e2e_pass"] = False
    rep["status"] = "BLOCKED"
    rep["overall_pass"] = False
    return rep


class TestBaselineQualification:
    def test_first_batch_qualified_fail_report(self):
        assert gqr._qualified_baseline_report(
            1, _baseline_report_fixture(), first_batch=True) is True

    def test_first_batch_allowed_red_improved_still_qualified(self):
        """允许红项改善为 PASS（G7 全过）→ 仍合格（改善向下不设限）。"""
        rep = _baseline_report_fixture()
        sm = rep["books"]["sanmingtonghui"]
        sm["all_gates_pass"] = True
        sm["gates"]["G7_chapter_complete"] = True
        sm["gate_details"]["G7_chapter_complete"] = {
            "expected": 383, "done": 383, "missing": [], "missing_count": 0,
            "extra": [], "extra_count": 0, "pass": True}
        rep["content_gates_pass"] = True
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is True

    def test_first_batch_rc7_rejected(self):
        assert gqr._qualified_baseline_report(
            7, _baseline_report_fixture(), first_batch=True) is False

    def test_baseline_out_of_allowed_fail_rejected(self):
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gates"]["G3_schema"] = False
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is False

    def test_missing_book_rejected(self):
        """缺书 → 不合格（四书齐备为合格条件④）。"""
        rep = _baseline_report_fixture()
        del rep["books"]["ditiansui"]
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is False

    def test_incomplete_gate_details_rejected(self):
        """gate_details 缺门 → 不合格（九门齐备为合格条件④）。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"] = {
            "G7_chapter_complete": rep["books"]["sanmingtonghui"]
            ["gate_details"]["G7_chapter_complete"]}
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is False

    def test_gate_detail_contradicts_bool_rejected(self):
        """P0-4：明细失败却声明 PASS（G6 out_of_band 非空但 pass=True）→ 拒绝
        （合格条件④：布尔与明细推导一致）。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"]["G6_answer_dist"] = {
            "dist_pct": {"A": 1.0}, "invalid_answers": 0,
            "out_of_band": ["A"], "pass": True}   # 明细自相矛盾
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is False

    def test_baseline_stale_report_not_accepted(self, rail_wt, monkeypatch):
        """P0-3：基线预置合格旧报告 + 本次 rc=1 且未写出 → 拒绝
        （新生成守卫：旧报告先删、运行后缺失即证明未产出）。"""
        rep_path = (rail_wt.path / "knowledge_base" / "classic_texts"
                    / "QUALITY_REPORT.json")
        rep_path.parent.mkdir(parents=True, exist_ok=True)
        rep_path.write_text(json.dumps(_baseline_report_fixture()),
                            encoding="utf-8")
        base = rail_wt.commit("baseline-with-stale-report")
        monkeypatch.setattr(gqr, "_run_report_in_worktree",
                            lambda tmp, ar: (1, b""))
        rc, rep = gqr.run_baseline(base, rail_wt.path, rail_wt.path,
                                   first_batch=True)
        assert (rc, rep) == (1, {})
        assert gqr._qualified_baseline_report(rc, rep, first_batch=True) is False

    def test_non_first_batch_requires_accepted_fields(self):
        rep = _baseline_report_fixture(first_batch=False)
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=False) is True
        rep2 = _baseline_report_fixture()          # 缺两修订字段 → 不合格
        assert gqr._qualified_baseline_report(
            1, rep2, first_batch=False) is False
        rep3 = _baseline_report_fixture()          # 有 state 缺 valid → 不合格
        rep3["revision_state"] = "ACCEPTED"
        assert gqr._qualified_baseline_report(
            1, rep3, first_batch=False) is False

    def test_rc_status_inconsistency_rejected(self):
        """完整合格 stdout + 异常退出码 / rc 与状态不一致 → 拒绝。"""
        rep = _baseline_report_fixture()
        rep["overall_pass"] = True
        rep["status"] = "PASS"
        assert gqr._qualified_baseline_report(
            7, rep, first_batch=True) is False
        assert gqr._qualified_baseline_report(
            1, rep, first_batch=True) is False  # rc=1 与 PASS 状态不一致

    def test_classify_first_batch_context_paired(self):
        """round-4 P0-3：同一份缺修订字段的报告——first_batch=True 判
        QUALIFIED、first_batch=False 判 INVALID；首批上下文由调用方按已
        验证锚链状态显式传入，不从报告缺字段推断。"""
        rep = _baseline_report_fixture()   # 缺 revision_state/revision_provenance_valid
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "QUALIFIED"
        assert gqr._classify_baseline_rc(1, rep, first_batch=False) == "INVALID"

    def test_baseline_rc3_with_missing_report_invalid(self):
        """P0-2：rc=3 但报告缺失（{}）→ 不是 source BLOCKED，判 INVALID。"""
        assert gqr._classify_baseline_rc(3, {}, first_batch=True) == "INVALID"

    def test_baseline_rc3_plain_fail_report_invalid(self):
        """P0-2：rc=3 但报告是普通 FAIL 形态 → 判 INVALID（不能当 BLOCKED）。"""
        assert gqr._classify_baseline_rc(
            3, _baseline_report_fixture(), first_batch=True) == "INVALID"

    def test_baseline_rc3_verifier_shaped_object_invalid(self):
        """round-4 P0-1：verifier CLI 三字段对象 {schema_version,status,reason}
        是 source verifier 输出形态，不是 QUALITY_REPORT.json——run_baseline
        读的是完整质量报告（reason 在逐书 source_blocked_reason），不得冒充。"""
        rep = {"schema_version": "1.0", "status": "BLOCKED",
               "reason": "archive_root_missing"}
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"

    def test_baseline_rc3_blocked_report_classified(self):
        """round-4 P0-1：rc=3 ∧ 生产形态 BLOCKED 质量报告（顶层 BLOCKED +
        sanmingtonghui source_e2e_status=BLOCKED + 五值 reason）→ "BLOCKED"。"""
        assert gqr._classify_baseline_rc(
            3, _blocked_report_fixture(), first_batch=True) == "BLOCKED"

    def test_baseline_rc3_blocked_bad_reason_invalid(self):
        """round-4 P0-1：BLOCKED 形态但逐书 reason 非五值 → 判 INVALID。"""
        assert gqr._classify_baseline_rc(
            3, _blocked_report_fixture("BOGUS"), first_batch=True) == "INVALID"

    def test_baseline_rc3_blocked_no_blocked_book_invalid(self):
        """round-4 P0-1：顶层标 BLOCKED 但无任何书 source_e2e_status=BLOCKED
        → 判 INVALID（顶层聚合与逐书状态必须一致）。"""
        rep = _blocked_report_fixture()
        sm = rep["books"]["sanmingtonghui"]
        sm["source_e2e_status"] = "PASS"
        sm["source_blocked_reason"] = None
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"

    def test_baseline_rc3_unknown_book_invalid(self):
        """round-5 P0：报告含未知书名（ghost）→ 结构层拒绝，判 INVALID。"""
        rep = _blocked_report_fixture()
        rep["books"]["ghost"] = rep["books"]["sanmingtonghui"]
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"

    def test_baseline_rc3_missing_book_invalid(self):
        """round-5 P0：缺书（四书键集不齐）→ 结构层拒绝，判 INVALID。"""
        rep = _blocked_report_fixture()
        del rep["books"]["ditiansui"]
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"

    def test_baseline_rc3_missing_required_field_invalid(self):
        """round-5 P0：顶层缺必需字段（source_e2e_pass）→ 结构层拒绝。"""
        rep = _blocked_report_fixture()
        del rep["source_e2e_pass"]
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"

    def test_baseline_rc3_e2e_pass_contradiction_invalid(self):
        """round-5 P0：source_e2e_pass=true 与顶层 BLOCKED 矛盾 → INVALID。"""
        rep = _blocked_report_fixture()
        rep["source_e2e_pass"] = True
        assert gqr._classify_baseline_rc(3, rep, first_batch=True) == "INVALID"

    def test_baseline_sm_source_policy_enforced(self):
        """P0-3：source 政策（A.4）——三命通会 source_e2e_status 必须 PASS
        （S 口径），改 FAIL → 不合格/INVALID。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["source_e2e_status"] = "FAIL"
        assert gqr._qualified_baseline_report(1, rep, first_batch=True) is False
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "INVALID"

    def test_baseline_g7_cap_enforced(self):
        """P0-3：允许计数上限——三命通会 G7 missing_count=304 > 303 → 不合格。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"]["G7_chapter_complete"] = {
            "expected": 384, "done": 80, "missing": [], "missing_count": 304,
            "extra": [], "extra_count": 0, "pass": False}
        assert gqr._qualified_baseline_report(1, rep, first_batch=True) is False

    def test_baseline_missing_required_field_invalid(self):
        """P0-3：统一先验报告结构——rc=1 删必需字段 generated_at →
        INVALID/不合格（此前仅 rc=3 分支执行结构检查）。"""
        rep = _baseline_report_fixture()
        del rep["generated_at"]
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "INVALID"
        assert gqr._qualified_baseline_report(1, rep, first_batch=True) is False

    def test_baseline_detail_field_missing_invalid(self):
        """P0-2：明细必需字段完整性——删 G7.missing_count → 结构层拒 →
        INVALID/不合格（此前仅验 gate_details 值为 dict，子键缺失漏检）。"""
        rep = _baseline_report_fixture()
        del rep["books"]["sanmingtonghui"]["gate_details"][
            "G7_chapter_complete"]["missing_count"]
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "INVALID"
        assert gqr._qualified_baseline_report(1, rep, first_batch=True) is False

    def test_baseline_detail_field_type_invalid(self):
        """P0-2：明细类型/取值域——G7.missing_count 改为字符串 "303" →
        结构层拒（不得抛 TypeError）。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"][
            "G7_chapter_complete"]["missing_count"] = "303"
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "INVALID"
        assert gqr._qualified_baseline_report(1, rep, first_batch=True) is False

    def test_baseline_provenance_not_admissible_invalid(self):
        """P0-2：资格状态——逐书及顶层 provenance_admissible 改 false →
        不合格/INVALID（A.1 候选可接纳值须 true）。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["provenance_admissible"] = False
        rep["provenance_admissible_all"] = False
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "INVALID"
        assert gqr._qualified_baseline_report(1, rep, first_batch=True) is False

    def test_baseline_rate_out_of_domain_invalid(self):
        """P0-1：G5.rate=2.0 超出合法域 [0,1] → 结构层拒 → INVALID。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"][
            "G5_traceability"]["rate"] = 2.0
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "INVALID"
        assert gqr._qualified_baseline_report(1, rep, first_batch=True) is False

    def test_baseline_rate_nan_invalid(self):
        """P0-1：G5.rate=NaN（非有限）→ 结构层拒 → INVALID（不得抛异常）。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"][
            "G5_traceability"]["rate"] = float("nan")
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "INVALID"

    def test_baseline_dist_pct_illegal_key_value_invalid(self):
        """P0-1：dist_pct 键/值非法（{"Z":"bad"}）→ 结构层拒 → INVALID。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"][
            "G6_answer_dist"]["dist_pct"] = {"Z": "bad"}
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "INVALID"

    def test_baseline_dist_pct_out_of_band_quality_not_schema(self):
        """P0-1：合法但越界比例（{"A": 0.9}，∈[0,1] 却越 [0.18,0.32]）是质量
        失败而非 schema 错误 → 结构层不因比例本身拒绝。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"][
            "G6_answer_dist"]["dist_pct"] = {"A": 0.9}
        assert gqr._report_structure_ok(rep) is True

    def test_sm_g7_simplified_shape_rejected(self):
        """P0-3：三命通会不得借缺 expected 跳过计数检查——sm G7 改 {pass,
        reason}（缺 expected/done/missing_count/extra_count）必须结构层拒绝
        （sm 有 chapter_list，G7 计数字段适用，简化形态非法）。"""
        rep = _baseline_report_fixture()
        rep["books"]["sanmingtonghui"]["gate_details"][
            "G7_chapter_complete"] = {"pass": True, "reason": "no chapter_list"}
        assert gqr._report_structure_ok(rep) is False
        assert gqr._classify_baseline_rc(1, rep, first_batch=True) == "INVALID"

    def test_non_sm_g7_simplified_missing_pass_rejected(self):
        """P1：非 sm 书 G7 简化形态必须含 pass 键——仅 {reason} 缺 pass 不得
        通过结构检查（严格简化形态 = pass is True ∧ reason=="no chapter_list"）。"""
        rep = _baseline_report_fixture()
        rep["books"]["ditiansui"]["gate_details"][
            "G7_chapter_complete"] = {"reason": "no chapter_list"}
        assert gqr._report_structure_ok(rep) is False

    def test_non_sm_g7_simplified_pass_false_rejected(self):
        """P1：非 sm 书 G7 简化形态 pass 必须严格 True（False 拒）。"""
        rep = _baseline_report_fixture()
        rep["books"]["ditiansui"]["gate_details"][
            "G7_chapter_complete"] = {"pass": False, "reason": "no chapter_list"}
        assert gqr._report_structure_ok(rep) is False

    def test_non_sm_g7_gate_bool_contradicts_rejected(self):
        """P1：非 sm 书 G7 门布尔与简化形态一致——gates 声明 False 而明细无
        chapter_list（推导必 True）→ _gate_consistent 拒（合理层）。"""
        rep = _baseline_report_fixture()
        rep["books"]["ditiansui"]["gates"]["G7_chapter_complete"] = False
        assert gqr._qualified_baseline_report(1, rep, first_batch=True) is False


def _load_report_module(wt: RailWorktree):
    """P0-1：从 fixture 磁盘脚本经 importlib **隔离加载**报告模块。
    patch 已导入模块的 ROOT 不会同步 `TOOLCHAIN_REGISTRY_HEAD`/`BASE`/
    `SCRIPTS_DIR`（导入时定值）——R₀ 替换后的登记链头与旧模块常量不符会被
    入口前置核验提前拒绝；隔离加载使 ROOT、BASE 与两信任根常量全部取
    fixture 态。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"gqr_rail_test_{uuid4().hex[:8]}",
        wt.path / "scripts" / "generate_quality_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCandidateCli:
    FIRST = "03c02bb571dec9e2da1f7d503a292da229415d8f"

    def _cli(self, wt, *args):
        r = subprocess.run(
            [sys.executable,
             str(wt.path / "scripts" / "generate_quality_report.py"), *args],
            capture_output=True, cwd=str(wt.path), timeout=100)
        return (r.returncode, r.stdout.decode("utf-8", "replace"),
                r.stderr.decode("utf-8", "replace"))

    def _r0(self, wt) -> str:
        line = _registry_line(wt.head0, GENESIS_SHA)
        wt.append_line(REGISTRY_REL, line)
        from scripts.classic_artifacts import (
            REVISION_REGISTRY_FIELDS, chain_head as _ch)
        h = _ch([json.loads(line.decode())], GENESIS_SHA,
                prev_field="prev_registry_sha256",
                fields=REVISION_REGISTRY_FIELDS)
        wt.replace_constant("TOOLCHAIN_REGISTRY_HEAD", h)
        return wt.commit("R0: register T0")

    def test_missing_args_exit2(self, rail_wt):
        rc, _, _ = self._cli(rail_wt, "--pending-batch", "B01")
        assert rc == 2

    def test_first_batch_wrong_baseline_exit2(self, rail_wt):
        self._r0(rail_wt)
        rc, _, _ = self._cli(rail_wt, "--pending-batch", "B01",
                             "--baseline-commit", "0" * 40,
                             "--toolchain-commit", rail_wt.head0,
                             "--archive-root", str(rail_wt.path))
        assert rc == 2

    def test_non_first_batch_first_baseline_exit2(self, rail_wt):
        """非首批（有已验收锚）传 03c02bb → exit 2（错配反向）。
        P0-5：先建登记 R₀——否则 T 准入先失败（TOOLCHAIN_INVALID），
        到不了基线错配的 exit 2 分支。"""
        self._r0(rail_wt)
        core = TestRailCore()
        manifest = core._make_c1(rail_wt)
        c1 = rail_wt.commit("C1")
        rail_wt.append_line(ANCHOR_REL, _anchor_line(
            "B01", c1, _sha256(_canonical_bytes(manifest)), GENESIS_SHA,
            rail_wt.head0))
        from scripts.classic_artifacts import chain_head as _ch
        rail_wt.replace_constant(
            "REVISION_ANCHOR_HEAD",
            _ch([json.loads(_anchor_line(
                "B01", c1, _sha256(_canonical_bytes(manifest)), GENESIS_SHA,
                rail_wt.head0).decode())], GENESIS_SHA))
        rail_wt.commit("V1")
        rc, _, _ = self._cli(rail_wt, "--pending-batch", "B02",
                             "--baseline-commit", self.FIRST,
                             "--toolchain-commit", rail_wt.head0,
                             "--archive-root", str(rail_wt.path))
        assert rc == 2

    def test_toolchain_not_registered_exit1(self, rail_wt):
        rc, _, err = self._cli(rail_wt, "--pending-batch", "B01",
                               "--baseline-commit", self.FIRST,
                               "--toolchain-commit", rail_wt.head0,
                               "--archive-root", str(rail_wt.path))
        assert rc == 1 and "REVISION_TOOLCHAIN_INVALID" in err

    def test_disk_tamper_exit1(self, rail_wt):
        """磁盘工具链脚本未提交篡改（仅换行差异）→ TOOLCHAIN_INVALID。"""
        self._r0(rail_wt)
        rel = "scripts/generate_quality_report.py"
        src = (rail_wt.path / rel).read_bytes()
        (rail_wt.path / rel).write_bytes(src.replace(b"\n", b"\r\n", 1))
        rc, _, err = self._cli(rail_wt, "--pending-batch", "B01",
                               "--baseline-commit", self.FIRST,
                               "--toolchain-commit", rail_wt.head0,
                               "--archive-root", str(rail_wt.path))
        assert rc == 1 and "REVISION_TOOLCHAIN_INVALID" in err
        # 注：toolchain 传已登记的 T（head0）——若传未登记 R0 会先在 T 准入
        # 失败，无法单独命中磁盘篡改分支；P0-4 后 head0 == 合成 T。

    def test_candidate_exit4_boundary(self, rail_wt, monkeypatch, capsys):
        """候选 exit 4 边界测试（P0-5/P0-1 round-3）：R₀ → C₁ → exit 4。

        边界声明：**隔离模块加载**（`_load_report_module` 从 fixture 磁盘
        脚本 importlib 加载——patch `gqr.ROOT` 不更新已导入的
        `TOOLCHAIN_REGISTRY_HEAD`/`BASE`/`SCRIPTS_DIR`，隔离加载后 ROOT
        与两信任根常量全为 fixture 态，R₀ 替换的登记链头才与新模块常量
        一致，入口前置核验不提前拒绝）。fakes：`run_baseline`（基线 rc=1
        合格 FAIL，签名含 first_batch）与 `verify_source_chain`（真实接口
        `(output_dict, exit_code)`——status=="OK"、code=0；`--archive-root`
        不提供真实归档，必须 fake；经 `_run_source_chain_check` 转换为
        `{"status":"PASS","reason":None}` 供 §7 聚合消费）。**真实归档重放 + 完整链集成（真实 source/G1-G9/退出码
        联合）在 Part B Task 11 执行**——本测试只证明候选边界（T 准入/执行
        来源/首批基线/rail 候选分支/基线联合分类/退化比较/exit 4）在隔离
        模块下闭合，不替代集成。"""
        self._r0(rail_wt)
        TestRailCore()._make_c1(rail_wt)
        rail_wt.commit("C1")
        mod = _load_report_module(rail_wt)         # P0-1：隔离加载
        monkeypatch.setattr(mod, "run_baseline",
                            lambda bc, gr, ar, first_batch=True: (
                                1, _baseline_report_fixture()))
        monkeypatch.setattr(
            mod, "verify_source_chain",
            # round-4 P0-2：真实接口 (output_dict, exit_code)——
            # verify_sanming_source_chain.verify_source_chain 的 OK 输出
            # （status=="OK"、code=0；生成器 _run_source_chain_check 解包后
            # code==0 ∧ status!=BLOCKED → {"status":"PASS","reason":None}）。
            # 单键 dict 会被 out, code = ... 解包成两个键名字符串致崩溃。
            lambda *a, **k: ({"schema_version": "1.0", "status": "OK",
                              "chapters_expected": 303, "c1_pass": 303,
                              "c2_pass": 303, "c3_pass": 303,
                              "failures": []}, 0))
        rc = mod.main(["--pending-batch", "B01", "--baseline-commit",
                       self.FIRST, "--toolchain-commit", rail_wt.head0,
                       "--archive-root", str(rail_wt.path)])
        out = capsys.readouterr().out
        assert rc == 4
        rep = json.loads(out)
        assert rep["books"]["sanmingtonghui"]["revision_state"] == \
            "PENDING_ACCEPTANCE"


class TestVStructure:
    def _v1(self, wt) -> str:
        core = TestRailCore()
        manifest = core._make_c1(wt)
        c1 = wt.commit("C1")
        anchor = _anchor_line("B01", c1, _sha256(_canonical_bytes(manifest)),
                              GENESIS_SHA, wt.head0)
        wt.append_line(ANCHOR_REL, anchor)
        wt.replace_constant("REVISION_ANCHOR_HEAD", chain_head(
            [json.loads(anchor.decode())], GENESIS_SHA))
        return wt.commit("V1")

    def test_v1_structure_valid(self, rail_wt):
        v1 = self._v1(rail_wt)
        assert gqr.validate_v_structure(rail_wt.path, v1) is None

    def test_v_merge_commit_rejected(self, rail_wt):
        # side 分支须唯一：worktree 共享主仓库 refs，固定名残留跨次运行冲突
        self._v1(rail_wt)
        side = f"side-{uuid4().hex[:8]}"
        _git(rail_wt.path, "checkout", "-b", side, "HEAD~1")
        rail_wt.write("README.side", b"x")
        rail_wt.commit("side")
        _git(rail_wt.path, "checkout", "-")
        _git(rail_wt.path, "merge", "-m", "merge", side)
        v2 = rail_wt.rev("HEAD")
        assert gqr.validate_v_structure(
            rail_wt.path, v2) == "REVISION_CHAIN_STALE"

    def test_v_extra_diff_path_rejected(self, rail_wt):
        """diff 含第三路径 → 拒绝。"""
        self._v1(rail_wt)
        rail_wt.write("docs/superpowers/plans/notes/approvals/revisions/"
                      "sanmingtonghui/extra.txt", b"x")
        v2 = rail_wt.commit("V-with-extra")
        assert gqr.validate_v_structure(
            rail_wt.path, v2) == "REVISION_CHAIN_STALE"

    def test_v1_still_valid_after_r2(self, rail_wt):
        """P0-2：追加合法 R₂（登记头常量变化，验收头常量不变）后重验旧 V₁
        仍通过——第 7 项只比较锚文件 + 验收头常量，不比整个脚本（TOOLCHAIN_
        REGISTRY_HEAD 随 R₂ 变不应误拒历史 V）。"""
        v1 = self._v1(rail_wt)
        reg_line = _registry_line(rail_wt.head0, GENESIS_SHA)
        rail_wt.append_line(REGISTRY_REL, reg_line)
        from scripts.classic_artifacts import (
            REVISION_REGISTRY_FIELDS, chain_head as _ch)
        h = _ch([json.loads(reg_line.decode())], GENESIS_SHA,
                prev_field="prev_registry_sha256",
                fields=REVISION_REGISTRY_FIELDS)
        rail_wt.replace_constant("TOOLCHAIN_REGISTRY_HEAD", h)
        rail_wt.commit("R2")
        assert gqr.validate_v_structure(rail_wt.path, v1) is None


class TestNormalizedScriptDiff:
    def _blob(self, anchor, registry, line_end=b"\n", trailing=True):
        tail = line_end if trailing else b""
        return (b'REVISION_ANCHOR_HEAD = "' + anchor + b'"' + line_end
                + b'TOOLCHAIN_REGISTRY_HEAD = "' + registry + b'"' + tail)

    def test_only_constant_value_change_ok(self):
        a = self._blob(b"a" * 64, b"b" * 64)
        b = self._blob(b"c" * 64, b"b" * 64)
        ok, names = gqr._normalized_script_diff(a, b)
        assert ok is True and names == {"REVISION_ANCHOR_HEAD"}

    def test_lf_to_crlf_rejected(self):
        """P0-1：仅行尾 LF→CRLF（常量值不变）也须拒绝——不得用 splitlines
        抹掉原始字节差异。"""
        a = self._blob(b"a" * 64, b"b" * 64, line_end=b"\n")
        b = self._blob(b"a" * 64, b"b" * 64, line_end=b"\r\n")
        assert gqr._normalized_script_diff(a, b)[0] is False

    def test_missing_trailing_newline_rejected(self):
        """P0-1：删除末尾换行（常量值不变）也须拒绝。"""
        a = self._blob(b"a" * 64, b"b" * 64, line_end=b"\n")
        b = self._blob(b"a" * 64, b"b" * 64, line_end=b"\n", trailing=False)
        assert gqr._normalized_script_diff(a, b)[0] is False


def _fake_source_ok():
    """verify_source_chain 真实接口 fake：(output_dict, exit_code) → OK。"""
    return lambda *a, **k: ({"schema_version": "1.0", "status": "OK",
                             "chapters_expected": 303, "c1_pass": 303,
                             "c2_pass": 303, "c3_pass": 303,
                             "failures": []}, 0)


def _batch_pair(wt: RailWorktree, rule_id: str,
                rule_text: str = "测试修订规则"):
    """构造一对 rule/mcq（original_text 取 raw_025 去空白前 30 字）及其
    manifest 记录；不写盘。"""
    snap_sha = _sha256(wt.blob("HEAD", RAW025_REL))
    src_text = wt.blob("HEAD", RAW025_REL).decode("utf-8", "replace")
    probe = re.sub(r"\s+", "", src_text)[:30]
    rule = _mk_rule(rule_id, "卷二·论坐命宫", rule_text)
    rule["original_text"] = probe
    mcq = _mk_mcq(rule_id + "_m1", rule_id)
    # 题干须与其它批次不同——G9 内容去重拦同文 MCQ（多批连续验收时
    # _make_c1 的固定题干会构成重复组）。
    mcq["question"] = f"测试题干（{rule_id}）？"
    from scripts.generate_classic_historical_freeze import _record_entry
    recs = []
    for kind, obj in (("rule", rule), ("mcq", mcq)):
        recs.append({"kind": kind, "id": obj["id"],
                     "sha256": _record_entry(obj)["sha256"],
                     "source_chapter": "卷二·论坐命宫",
                     "snapshot_path": RAW025_REL,
                     "snapshot_sha256": snap_sha,
                     "historical_basis": None})
    return rule, mcq, recs


def _append_batch(wt: RailWorktree, batch_id: str, rule: dict, mcq: dict,
                  recs: list, write_aggregate: bool = True) -> dict:
    """聚合 + manifest 追加一批（manifest 读盘优先——连续追加时未提交的
    前批不可经 HEAD 读）；返回追加后的 manifest。"""
    rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
    mcq_rel = "knowledge_base/classic_texts/sanmingtonghui/all_mcq.jsonl"
    if write_aggregate:
        arr = json.loads(wt.blob("HEAD", rules_rel).decode("utf-8"))
        arr.append(rule)
        wt.write(rules_rel,
                 json.dumps(arr, ensure_ascii=False).encode("utf-8"))
        wt.write(mcq_rel, wt.blob("HEAD", mcq_rel)
                 + (_canonical(mcq) + "\n").encode("utf-8"))
    mp = wt.path / MANIFEST_REL
    manifest = json.loads(
        mp.read_bytes().decode("utf-8") if mp.exists()
        else wt.blob("HEAD", MANIFEST_REL).decode("utf-8"))
    manifest["batches"].append({"batch_id": batch_id, "date": "2026-09-08",
                                "author": "test", "records": recs})
    wt.write(MANIFEST_REL, _canonical_bytes(manifest) + b"\n")
    return manifest


def _accept_batch(wt: RailWorktree, manifest: dict, batch_id: str, c_oid: str,
                  prev_head: str, toolchain: str) -> str:
    """追加验收锚行 + 唯一替换验收头常量（不提交）；返回新锚链头。"""
    anchor = _anchor_line(batch_id, c_oid, _sha256(_canonical_bytes(manifest)),
                           prev_head, toolchain)
    wt.append_line(gqr.REVISION_ANCHOR_REL, anchor)
    entries = [json.loads(ln) for ln
               in (wt.path / gqr.REVISION_ANCHOR_REL).read_bytes()
               .decode("utf-8").splitlines() if ln.strip()]
    head = chain_head(entries, GENESIS_SHA)
    wt.replace_constant("REVISION_ANCHOR_HEAD", head)
    return head


def _register_toolchain(wt: RailWorktree, toolchain: str) -> str:
    """追加登记行（prev=当前链头）+ 唯一替换登记头常量（不提交）；
    返回新登记链头。"""
    from scripts.classic_artifacts import (
        REVISION_REGISTRY_FIELDS, chain_head as _ch)
    entries = [json.loads(ln) for ln
               in (wt.path / gqr.REVISION_REGISTRY_REL).read_bytes()
               .decode("utf-8").splitlines() if ln.strip()]
    prev = _ch(entries, GENESIS_SHA, prev_field="prev_registry_sha256",
               fields=REVISION_REGISTRY_FIELDS)
    line = _registry_line(toolchain, prev)
    wt.append_line(gqr.REVISION_REGISTRY_REL, line)
    entries.append(json.loads(line.decode()))
    return _ch(entries, GENESIS_SHA, prev_field="prev_registry_sha256",
               fields=REVISION_REGISTRY_FIELDS)


def _first_missing_chapter(wt: RailWorktree) -> str:
    """G7 口径下第一个缺失章节（chapter_list 归一化 − progress.done；
    归一化与 validate_classic_distillation._load_chapter_list 同构）。"""
    p = "knowledge_base/classic_texts/sanmingtonghui"
    cl = (wt.path / p / "chapter_list.txt").read_text(
        encoding="utf-8").splitlines()
    prog = json.loads(wt.blob("HEAD", f"{p}/progress.json"))

    def n(v: str) -> str:
        return re.sub(r"\s+", "", v.strip())
    es = {n(re.sub(r"^\d+[\.\s]*", "", ln.split("\t")[0]).strip())
          for ln in cl if ln.strip()}
    ds = {n(c) for c in prog.get("done", [])}
    missing = sorted(es - ds)
    assert missing, "precondition: at least one missing chapter"
    return missing[0]


class TestRevisionMatrix:
    """Task 8：5-R.12 全矩阵收口。勾稽（既有覆盖，不重复建）：
    VALID 书出现 manifest → UNSUPPORTED_STATE
    （test_matrix_valid_book_with_manifest_unsupported）；门禁字段删除/
    改类型 → 拒绝（test_b_minus_n_field_removed_rejected /
    test_detail_field_type_changed_rejected）；新增布尔 FAIL/计数超上限/
    枚举不可接纳 → 拒绝（test_new_gate_bool_must_be_pass /
    test_detail_field_new_with_failure_value_rejected / A.4 系列）；
    首批传非 03c02bb 与非首批传 03c02bb → exit 2（TestCandidateCli 两
    方向）；锚缺失 + 常量为后续值 → CHAIN_STALE
    （test_rail_missing_anchor_nongenesis_constant_stale）；rc=3 BLOCKED
    分类矩阵（TestBaselineQualification rc3 系列）。"""

    def _v1(self, wt: RailWorktree):
        """R₀→C₁→V₁ 标准链；返回 (v1, h1)。"""
        TestCandidateCli()._r0(wt)
        core = TestRailCore()
        m1 = core._make_c1(wt)
        c1 = wt.commit("C1")
        h1 = _accept_batch(wt, m1, "B01", c1, GENESIS_SHA, wt.head0)
        return wt.commit("V1"), h1

    def test_two_consecutive_batches(self, rail_wt, monkeypatch, capsys):
        """候选接线 + 两批 rail 结构（P0 边界标注）：候选模式以 fake 基线
        重跑证明 C₂ 候选 PENDING/false 不判退化；V₂ 收尾为 rail 层 + 结构层
        （两锚、常量==链头、validate_v_structure），非完整默认报告。完整默认
        复验 + 合格基线判定见 test_default_report_qualified_baseline_chain。"""
        v1, h1 = self._v1(rail_wt)
        # 规则文本须与 B01 不同——G9 内容去重会拦截同文规则（真实
        # 门禁行为，非退化误报）。
        rule, mcq, recs = _batch_pair(rail_wt, "smth_t_002",
                                      rule_text="测试修订规则二")
        m2 = _append_batch(rail_wt, "B02", rule, mcq, recs)
        c2 = rail_wt.commit("C2")
        # 候选（非首批：基线 V₁）——基线重跑 fake 为 ACCEPTED 合格报告
        mod = _load_report_module(rail_wt)
        monkeypatch.setattr(mod, "run_baseline",
                            lambda bc, gr, ar, first_batch=True: (
                                1, _baseline_report_fixture(first_batch=False)))
        monkeypatch.setattr(mod, "verify_source_chain", _fake_source_ok())
        rc = mod.main(["--pending-batch", "B02", "--baseline-commit", v1,
                       "--toolchain-commit", rail_wt.head0,
                       "--archive-root", str(rail_wt.path)])
        assert rc == 4
        rep = json.loads(capsys.readouterr().out)
        sm = rep["books"]["sanmingtonghui"]
        assert sm["revision_state"] == "PENDING_ACCEPTANCE"
        assert rep["revision_provenance_valid"] is False  # 修订字段不入退化比较
        # V₂ 验收 + 默认复验
        h2 = _accept_batch(rail_wt, m2, "B02", c2, h1, rail_wt.head0)
        v2 = rail_wt.commit("V2")
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", h2)
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["revision_state"] == "ACCEPTED"
        assert res["error_code"] is None
        anchors = gqr._anchor_entries(rail_wt.path)
        assert len(anchors) == 2
        assert chain_head(anchors, GENESIS_SHA) == h2
        assert gqr.validate_v_structure(rail_wt.path, v2) is None

    def test_default_report_qualified_baseline_chain(self, rail_wt, monkeypatch):
        """P0：实际报告调用链——默认模式真实 generate_report（G1-G9/rail
        真实执行，仅 source 重放边界以 _fake_source_ok 替身化，不伪造合格
        基线结论）。证明：① V₁ 默认报告满足验收条件（revision_state==
        ACCEPTED）且被 _qualified_baseline_report 判为合格基线（非首批）；
        ② V₂ 完整默认报告同样满足验收条件，且 V₂ 可作后续批次基线。"""
        v1, h1 = self._v1(rail_wt)
        mod1 = _load_report_module(rail_wt)
        monkeypatch.setattr(mod1, "verify_source_chain", _fake_source_ok())
        rep1, rc1 = mod1.generate_report(archive_root=str(rail_wt.path))
        assert rep1["revision_state"] == "ACCEPTED"
        assert rep1["books"]["sanmingtonghui"]["revision_state"] == "ACCEPTED"
        # V₁ 默认报告满足非首批验收条件 → 合格基线（内部再验结构/门一致性/
        # source 政策/允许红项上界）。
        assert gqr._qualified_baseline_report(rc1, rep1, first_batch=False) is True

        rule, mcq, recs = _batch_pair(rail_wt, "smth_t_002",
                                      rule_text="测试修订规则二")
        m2 = _append_batch(rail_wt, "B02", rule, mcq, recs)
        c2 = rail_wt.commit("C2")
        h2 = _accept_batch(rail_wt, m2, "B02", c2, h1, rail_wt.head0)
        v2 = rail_wt.commit("V2")

        mod2 = _load_report_module(rail_wt)
        monkeypatch.setattr(mod2, "verify_source_chain", _fake_source_ok())
        rep2, rc2 = mod2.generate_report(archive_root=str(rail_wt.path))
        assert rep2["revision_state"] == "ACCEPTED"
        assert rep2["books"]["sanmingtonghui"]["revision_state"] == "ACCEPTED"
        anchors = gqr._anchor_entries(rail_wt.path)
        assert len(anchors) == 2
        assert chain_head(anchors, GENESIS_SHA) == h2
        assert gqr._qualified_baseline_report(rc2, rep2, first_batch=False) is True
        assert gqr.validate_v_structure(rail_wt.path, v2) is None

    def test_toolchain_upgrade_old_v_still_valid(self, rail_wt):
        """工具链升级链：R₀(T₀)→C₁→V₁（锚绑 T₀）→ T₁ 真实脚本改动 + R₁
        登记 → 旧 V₁ 仍按其锚内 T₀ 通过（历史兼容，不拿 HEAD 新登记头/
        新代码要求旧提交）。"""
        v1, _ = self._v1(rail_wt)
        assert gqr.validate_v_structure(rail_wt.path, v1) is None
        rel = "scripts/generate_quality_report.py"
        rail_wt.write(rel, (rail_wt.path / rel).read_bytes()
                      + b"# toolchain upgrade T1\n")
        t1 = rail_wt.commit("T1: legal script change")
        _register_toolchain(rail_wt, t1)
        rail_wt.commit("R1: register T1")
        assert gqr.validate_v_structure(rail_wt.path, v1) is None

    def test_candidate_improvement_exit4(self, rail_wt, monkeypatch, capsys):
        """候选改善端到端：C₁ 把一个缺失章节写入 progress.json（G7 的
        done/missing 口径在 progress.done，非规则聚合）→ 真实候选 G7
        missing_count 302 vs 基线 303 → 允许项向下改善被接受（exit 4）。"""
        TestCandidateCli()._r0(rail_wt)
        TestRailCore()._make_c1(rail_wt)
        prog_rel = "knowledge_base/classic_texts/sanmingtonghui/progress.json"
        prog = json.loads(rail_wt.blob("HEAD", prog_rel).decode("utf-8"))
        prog["done"].append(_first_missing_chapter(rail_wt))
        rail_wt.write(prog_rel,
                      json.dumps(prog, ensure_ascii=False).encode("utf-8"))
        rail_wt.commit("C1")
        mod = _load_report_module(rail_wt)
        monkeypatch.setattr(mod, "run_baseline",
                            lambda bc, gr, ar, first_batch=True: (
                                1, _baseline_report_fixture()))
        monkeypatch.setattr(mod, "verify_source_chain", _fake_source_ok())
        rc = mod.main(["--pending-batch", "B01", "--baseline-commit",
                       TestCandidateCli.FIRST, "--toolchain-commit",
                       rail_wt.head0, "--archive-root", str(rail_wt.path)])
        assert rc == 4
        rep = json.loads(capsys.readouterr().out)
        g7 = rep["books"]["sanmingtonghui"]["gate_details"][
            "G7_chapter_complete"]
        assert g7["missing_count"] == 302

    def test_empty_anchor_file_zero_lines_valid(self, rail_wt):
        """空锚文件（零行）+ 常量==genesis → 合法 NONE。"""
        rail_wt.write(gqr.REVISION_ANCHOR_REL, b"")
        rail_wt.commit("empty anchor file")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["revision_state"] == "NONE"
        assert res["ok"] is True and res["e3_ok"] is True

    def test_same_batch_mutated_history_drift(self, rail_wt, monkeypatch):
        """同 batch_id 改记录内容并同步 manifest 候选 SHA（C/A/常量不动，
        仅改 HEAD）→ REVISION_HISTORY_DRIFT（④ 先于 ⑤ 拦截）。"""
        _, h1 = self._v1(rail_wt)
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", h1)
        res0 = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res0["revision_state"] == "ACCEPTED"
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        arr = json.loads(rail_wt.blob("HEAD", rules_rel).decode("utf-8"))
        target = next(r for r in arr if r["id"] == "smth_t_001")
        target["rule"] = "被篡改的规则文本"
        rail_wt.write(rules_rel,
                      json.dumps(arr, ensure_ascii=False).encode("utf-8"))
        from scripts.generate_classic_historical_freeze import _record_entry
        manifest = json.loads(rail_wt.blob("HEAD", MANIFEST_REL)
                              .decode("utf-8"))
        for rec in manifest["batches"][0]["records"]:
            if rec["id"] == "smth_t_001":
                rec["sha256"] = _record_entry(target)["sha256"]
        rail_wt.write(MANIFEST_REL, _canonical_bytes(manifest) + b"\n")
        rail_wt.commit("mutate accepted batch records (sha synced)")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_HISTORY_DRIFT"

    def test_anchor_tamper_chain_stale(self, rail_wt, monkeypatch):
        """锚文件篡改（改 manifest_sha256_after、常量不动）→ ③ 链头重算
        不符 → REVISION_CHAIN_STALE。"""
        _, h1 = self._v1(rail_wt)
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", h1)
        relp = rail_wt.path / gqr.REVISION_ANCHOR_REL
        line = json.loads(relp.read_bytes().decode("utf-8"))
        line["manifest_sha256_after"] = "f" * 64
        relp.write_bytes((_canonical(line) + "\n").encode("utf-8"))
        rail_wt.commit("tamper anchor manifest_sha256_after")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_CHAIN_STALE"

    def test_delete_batch_chain_stale(self, rail_wt, monkeypatch):
        """删批（manifest 抹除已验收批次）→ REVISION_CHAIN_STALE。"""
        _, h1 = self._v1(rail_wt)
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", h1)
        manifest = json.loads(rail_wt.blob("HEAD", MANIFEST_REL)
                              .decode("utf-8"))
        manifest["batches"] = []
        rail_wt.write(MANIFEST_REL, _canonical_bytes(manifest) + b"\n")
        rail_wt.commit("delete accepted batch from manifest")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_CHAIN_STALE"

    def test_two_extra_batches_unaccepted(self, rail_wt, monkeypatch):
        """多批追加（+2）→ REVISION_UNACCEPTED（候选 ④：len(hb)>n+1）。"""
        _, h1 = self._v1(rail_wt)
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", h1)
        rule, mcq, recs = _batch_pair(rail_wt, "smth_t_003")
        rule2, mcq2, recs2 = _batch_pair(rail_wt, "smth_t_004")
        _append_batch(rail_wt, "B02", rule, mcq, recs, write_aggregate=False)
        _append_batch(rail_wt, "B03", rule2, mcq2, recs2,
                      write_aggregate=False)
        rail_wt.commit("two extra batches")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt), candidate_batch_id="B02")
        assert res["error_code"] == "REVISION_UNACCEPTED"

    def test_manifest_freeze_intersection_malformed(self, rail_wt):
        """manifest 与 freeze 交集（同一记录双列）→ ②
        REVISION_MANIFEST_MALFORMED。"""
        freeze = _freeze_of(rail_wt)
        fr = freeze["books"]["sanmingtonghui"]["all_rules"]["records"][0]
        snap_sha = _sha256(rail_wt.blob("HEAD", RAW025_REL))
        rec = {"kind": "rule", "id": fr["id"], "sha256": fr["sha256"],
               "source_chapter": "卷二·论坐命宫", "snapshot_path": RAW025_REL,
               "snapshot_sha256": snap_sha, "historical_basis": None}
        manifest = {"schema_version": "1.0", "book": "sanmingtonghui",
                    "freeze_base_commit":
                        "c5cff699fdb547bd9270acbebe1f485380848751",
                    "batches": [{"batch_id": "B01", "date": "2026-09-08",
                                 "author": "test", "records": [rec]}]}
        rail_wt.write(MANIFEST_REL, _canonical_bytes(manifest) + b"\n")
        rail_wt.commit("manifest lists freeze record")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", freeze, _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_MANIFEST_MALFORMED"

    def test_manifest_orphan_mismatch(self, rail_wt, monkeypatch):
        """manifest_orphan（manifest 列了记录、HEAD 聚合缺）→ ⑤ MISMATCH
        （partition_detail.manifest_orphan ≥ 1）。"""
        _, h1 = self._v1(rail_wt)
        monkeypatch.setattr(gqr, "REVISION_ANCHOR_HEAD", h1)
        rules_rel = "knowledge_base/classic_texts/sanmingtonghui/all_rules.json"
        mcq_rel = "knowledge_base/classic_texts/sanmingtonghui/all_mcq.jsonl"
        arr = [r for r in json.loads(rail_wt.blob("HEAD", rules_rel)
                                     .decode("utf-8"))
               if r["id"] != "smth_t_001"]
        rail_wt.write(rules_rel,
                      json.dumps(arr, ensure_ascii=False).encode("utf-8"))
        kept = [ln for ln in rail_wt.blob("HEAD", mcq_rel)
                .decode("utf-8").splitlines() if ln.strip()
                and json.loads(ln)["id"] != "smth_t_001_m1"]
        rail_wt.write(mcq_rel, ("\n".join(kept) + "\n").encode("utf-8"))
        rail_wt.commit("drop batch records from aggregates")
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "sanmingtonghui", _freeze_of(rail_wt),
            _evidence_of(rail_wt))
        assert res["error_code"] == "REVISION_PARTITION_MISMATCH"
        assert res["partition_detail"]["manifest_orphan"] >= 1

    def _candidate_with_fake_baseline(self, rail_wt, monkeypatch, capsys,
                                      baseline_rc, baseline_rep,
                                      run_baseline_calls=None):
        """R₀→C₁→候选 CLI（generate_report/基线重跑均 fake）；返回
        (rc, stderr)。run_baseline_calls 若传 list，则逐次记录基线替身
        调用参数 (baseline_commit, first_batch)，供断言"替身确实被调用"。"""
        TestCandidateCli()._r0(rail_wt)
        TestRailCore()._make_c1(rail_wt)
        rail_wt.commit("C1")
        mod = _load_report_module(rail_wt)
        cand = _baseline_report_fixture()
        cand["revision_state"] = "PENDING_ACCEPTANCE"
        cand["revision_provenance_valid"] = False
        # _candidate_mode 读书级 revision 字段（generate_report 真实
        # 输出在 book entry 上），fake 须同构补齐，否则误走第 6 步。
        csm = cand["books"]["sanmingtonghui"]
        csm["revision_state"] = "PENDING_ACCEPTANCE"
        csm["revision_provenance_valid"] = False
        monkeypatch.setattr(mod, "generate_report",
                            lambda *a, **k: (cand, 1))
        calls = run_baseline_calls if run_baseline_calls is not None else []

        def _fake_run_baseline(bc, gr, ar, first_batch=True):
            calls.append((bc, first_batch))
            return baseline_rc, baseline_rep

        monkeypatch.setattr(mod, "run_baseline", _fake_run_baseline)
        rc = mod.main(["--pending-batch", "B01", "--baseline-commit",
                       TestCandidateCli.FIRST, "--toolchain-commit",
                       rail_wt.head0, "--archive-root", str(rail_wt.path)])
        return rc, capsys.readouterr().err

    def test_baseline_rc7_exit1(self, rail_wt, monkeypatch, capsys):
        """基线重跑 rc=7 端到端 → exit 1（REVISION_BASELINE_INVALID）。"""
        rc, err = self._candidate_with_fake_baseline(
            rail_wt, monkeypatch, capsys, 7, {})
        assert rc == 1 and "REVISION_BASELINE_INVALID" in err

    def test_baseline_out_of_allowed_fail_exit1(self, rail_wt, monkeypatch,
                                                capsys):
        """基线含**自洽**允许集合外 FAIL（G3）端到端 → exit 1。

        P0：明细与门布尔须自洽（bad_rules=1 ∧ gates[G3]=False），先断言
        结构层与门一致性通过，再断言目标资格检查拒绝——证明"自洽但不在
        允许集合的失败被拒"，而非"布尔与明细矛盾被拒"。同时记录基线替身
        确实被调用。"""
        rep = _baseline_report_fixture()
        sm = rep["books"]["sanmingtonghui"]
        sm["gates"]["G3_schema"] = False
        sm["gate_details"]["G3_schema"] = {
            "bad_rules": 1, "bad_mcq": 0, "parse_errors": 0, "pass": False}
        # 前置：结构层过 + 门布尔与明细推导自洽（gate_consistent True）。
        assert gqr._report_structure_ok(rep) is True
        assert gqr._gate_consistent(sm["gates"], sm["gate_details"]) is True
        # 自洽但 G3 ∉ 允许红项集合 → 资格检查拒绝。
        assert gqr._qualified_baseline_report(1, rep, first_batch=True) is False
        calls = []
        rc, err = self._candidate_with_fake_baseline(
            rail_wt, monkeypatch, capsys, 1, rep, run_baseline_calls=calls)
        assert calls, "基线替身应被调用"
        assert rc == 1 and "REVISION_BASELINE_INVALID" in err

    def test_baseline_blocked_exit3(self, rail_wt, monkeypatch, capsys):
        """rc=3 基线 BLOCKED 上抛 → exit 3（SOURCE_CHAIN_BLOCKED:<reason>）。"""
        rc, err = self._candidate_with_fake_baseline(
            rail_wt, monkeypatch, capsys, 3,
            _blocked_report_fixture("archive_missing"))
        assert rc == 3 and "SOURCE_CHAIN_BLOCKED:archive_missing" in err

    def test_committed_tamper_unregistered_exit1(self, rail_wt):
        """已提交篡改未登记（worktree 内提交改脚本字节但未走 R）→ 候选
        CLI 执行来源核验拒 → exit 1（REVISION_TOOLCHAIN_INVALID）。"""
        TestCandidateCli()._r0(rail_wt)
        rel = "scripts/generate_quality_report.py"
        rail_wt.write(rel, (rail_wt.path / rel).read_bytes() + b"# tamper\n")
        rail_wt.commit("tamper script without registration")
        cli = TestCandidateCli()
        rc, _, err = cli._cli(rail_wt, "--pending-batch", "B01",
                              "--baseline-commit", TestCandidateCli.FIRST,
                              "--toolchain-commit", rail_wt.head0,
                              "--archive-root", str(rail_wt.path))
        assert rc == 1 and "REVISION_TOOLCHAIN_INVALID" in err

    def test_qiongtongbaojian_quarantine_stock_none(self, rail_wt):
        """非空隔离存量书（穷通宝鉴 310 条 quarantine 记录）在等式中保留
        多重性——HEAD==freeze 分区对该书不回归，rail NONE。"""
        freeze = _freeze_of(rail_wt)
        q = freeze["books"]["qiongtongbaojian"]
        n_q = (len(q["quarantine_mcq"]["records"])
               + len(q["quarantine_rules"]["records"]))
        assert n_q >= 1  # 前置：确有非空隔离存量
        res = gqr.evaluate_revision_rail(
            rail_wt.path, "qiongtongbaojian", freeze, _evidence_of(rail_wt))
        assert res["revision_state"] == "NONE"
        assert res["ok"] is True and res["e3_ok"] is True
