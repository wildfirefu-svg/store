# Phase 8 marriage-capability 修复/豁免实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **执行边界（修订 v2，2026-09-01，采纳复审 P0）：Task 1–6 全部为批准门禁任务——Task 1 修改被 manifest 钉定的 `p8_kb_snapshot.py`，必须随后级联重冻结，不可单独收尾；未经明确批准不执行任何代码/产物修改，批准前仅允许只读验证；Task 7 推送另行批准；不合并主线，不触碰 acceptance 冻结链（`CLASSIC_ACCEPTANCE_FREEZE_V2` / payload `ba7cc51…` / 两 identity manifest）。**

**Goal:** 消除 Phase 8 的 4 个 CI 失败（或按用户决策豁免），使 `integration/classic-texts-clean` 双作业 CI 全绿，解除合并主线前的最后一个独立阻断。

**Architecture:** 三个相互独立的根因、三组处置：①迁移诱导的 classic-texts 冻结漂移（3/8 文件）→ 按既定 supersession 模式把 `classic_texts_freeze.json` 再冻结到清洁链；②路径序列化未归一化 + 冻结后环境漂移 → `p8_kb_snapshot.py` 改 `.as_posix()` 并在当前环境整体重生成快照产物；③对 gitignored 可重建 SQLite 产物钉 raw_bytes 字节 → 结构不可满足，从 manifest 移除该条目（语义门禁由 `TestKbSnapshot` 已有测试承担）。

**Tech Stack:** Python 3.11 + pytest；SQLite/FTS5；git blob/SHA 对账；`p8_freeze.py atomic_add` 原子 manifest 更新；`p8_provenance.py` 由 manifest 再生成 provenance。

---

## 0. 证据基础（全部机械核实于 2026-08-31）

### 0.1 CI 事实（run `33383577945`，两作业逐字节一致 → 确定性失败）

- `affected-tests`（5m26s）与 `test`（6m0s）均 `4 failed, 2542 passed, 37 skipped`；ruff/mypy/syntax 全绿。
- 4 个失败全部位于 `tests/test_phase8_marriage_capability.py`：
  1. `TestClassicTextsFreeze::test_blob_sha_matches_head`（:472）
  2. `TestKbEquivalence::test_regeneration_deterministic`（:572）
  3. `TestReconcileSubtype::test_reconcile_subtype_passes`（:1185）
  4. `TestReconcileSubtype::test_reconcile_full_sections`（:1198）

### 0.2 根因一：迁移诱导的冻结漂移（失败 1）

`docs/phase8/marriage-capability/classic_texts_freeze.json` 的 `frozen_commit = a06a3373…`（main 时代），8 个钉定文件中 **3 个已漂移**（HEAD vs `origin/main 3d3b41cf` 逐 blob 核对；pytest 首错即停，CI 只报出第 1 个）：

| 文件 | 冻结/ main blob | 清洁链 HEAD blob |
|---|---|---|
| `qiongtongbaojian/all_rules.json` | `7325c350fe61a9d8fbe225009c045cd3343c557d` | `dc10d5749821e930a4ccb4af99ed25866094d0c5` |
| `qiongtongbaojian/quarantine_rules.jsonl` | `fef8051c76d4f76c4156934abc70df354ca8f3c2` | `e8c7c13e1152206ef406fd6fdfaeebe53a34bfca` |
| `sanmingtonghui/all_rules.json` | `74eaaa09b5a7ba8b53d9d83055aa6e1eb454b48e` | `97716ca0455e59167944569380b5fb8c0983ba46` |

其余 5 项与 main 逐字节相同（ditiansui/all `df67639d…`、ditiansui/quar `e69de29b…`、sanmingtonghui/quar `e69de29b…`、zipingzhenquan/all `6ccf684b…`、zipingzhenquan/quar `e69de29b…`）。C2 overlay（`80bc630`）按闭包以候选 blob 置换 classic-texts 数据是**迁移的既定行为**，故此失败属"迁移正确、冻结记录未跟上"。`kb_equivalence.json`、`docs/phase8/**`、`knowledge-base/` 在 `3d3b41cf..1f266be` 间零改动（`git diff --stat` 为空）→ 失败 2/3/4 为 main 上已存在的历史红灯。

### 0.3 根因二：路径未归一化 + 冻结后环境漂移（失败 2）

- 提交态 `kb_equivalence.json`（blob `afb141d4…`，main 与 HEAD 相同）为 Windows 环境 所写：路径含反斜杠（`knowledge-base\bazi_kb.db`）、`ok: 59`。
- `p8_kb_snapshot.py:187-188` 用 `str(path.relative_to(REPO))` 写 `source_db`/`snapshot_db` → OS 原生分隔符，POSIX 重生成**结构上不可能**与 Windows 产物字节相等。
- 环境漂移证据：主 worktree 现存 `bazi_kb.db` SHA == 冻结记录 `115bace4…`（自冻结后从未重建）；今日同机重建 → `1b22b629…` ≠ 冻结，且重生成 `ok: 53`，与 CI 的 53 **翻转集完全一致**——6 个 `search_gejue` 查询（`mingli_ftb_0026#k1#q2` 1→2、`mingli_ftb_0002#k4#q1` 0→2、`mingli_ftb_0077#k4#q2` 1→0、`mingli_ftb_0122#k1#q2` 1→0、`mingli_ftb_0100#k1#q2` 2→0、`mingli_ftb_0099#k4#q1` 1→0）。KB 输入 `knowledge-base/gejue.json` 自 2026-05-28（`c6f3c57`）未变 → 漂移源为冻结后的 SQLite/FTS5 库版本演进（本机当前 sqlite 3.50.4），非数据变更、非迁移。

### 0.4 根因三：对可重建产物钉 raw_bytes 结构不可满足（失败 3/4）

- `phase8_freeze_manifest.json:145-149` 以 `raw_bytes` 钉 `knowledge-base/bazi_kb.db` = `115bace4…`；该文件被 `.gitignore:9` 忽略、不入库（约 740 KB），CI 每次先执行 `python knowledge-base/bazi_kb.py --build`（ci.yml:71-72、123-124）。
- 失败形态：CI = 存在但字节不符；全新 worktree = 文件缺失（本地复现 `5 failed, 79 passed`，构建 DB 后 `4 failed, 80 passed` 与 CI 完全同组）。唯一能让 raw_bytes 通过的环境是"自冻结后从未重建"——任何 CI 都不满足。
- `test_reconcile_full_sections`（:1188-1204）仅断言七节存在 + 无 `FAIL`，不校验 entry 清单 → 从 manifest 移除该条目机械安全；DB 语义完整性已由 `TestKbSnapshot`（表结构/行数/FTS schema）与 `TestKbEquivalence`（行为等价）覆盖。

### 0.5 再冻结级联面与陷阱

- 级联：改动产物 → `p8_freeze.py atomic_add`（按 path 去重置换、原子写）更新 `phase8_freeze_manifest.json` → `python p8_provenance.py` 由 manifest 再生成 `provenance.json` → 再 `atomic_add` provenance 新 SHA → `p8_reconcile.py` 须 exit 0。
- **陷阱**：`p8_kb_snapshot.py build_classic_texts_freeze`（:255-258）在产物已存在时**复用旧 `frozen_commit a06a3373`**——天真重跑会继续钉旧链。必须先删除 `classic_texts_freeze.json` 再生成（此时 head 回落为 `rev-parse HEAD`）。
- `p8_kb_snapshot.py` 自身被 manifest 以 `git_canonical_lf` 钉定 → Task 1 的代码修改必须进入 Task 4 的 `atomic_add` 清单。

## 决策点（执行前用户必答；本计划按推荐组合编写）

- **D1（失败 1）**：A（推荐）supersede `classic_texts_freeze.json` 到清洁链（旧记录留历史，附 receipt）；B 改测试为链感知双钉（不推荐：测试语义复杂化）。
- **D2（失败 3/4）**：A（推荐）从 manifest 移除 `bazi_kb.db` raw_bytes 条目，语义门禁交由既有 `TestKbSnapshot`/`TestKbEquivalence`；B 在 `p8_reconcile.py` 新增 `sqlite_logical` 策略（schema+行数+内容摘要）；C 将 DB 入库并调整 CI 构建步（影响面最大，不推荐）。
- **D3**：批准执行 Task 1–6（Phase 8 冻结域 re-freeze v2）；未批准前仅允许只读验证。**[RATIFIED，2026-09-01] 用户在聊天正文直接发送追认句（原文逐字："我追认并批准 Phase 8 计划的 D1=A、D2=A、D3，批准现有 Task 1–6 技术成果进入重新验证；Task 7 推送仍需另行批准。"），替代经 58a7e36 判定无效的转述记录（该无效档案保留于提交历史）。据此：D1=A（supersede classic_texts_freeze.json）、D2=A（移除 bazi_kb.db raw_bytes 钉定）、D3=Task 1–6 技术成果批准进入重新验证；Task 7 推送另行批准。**

---

### Task 1: 路径归一化（TDD；**批准门禁**——修改被 manifest 以 git_canonical_lf 钉定的 `p8_kb_snapshot.py`，其提交必须由 Task 4 的 atomic_add 级联收尾）

**Files:**
- Modify: `docs/phase8/marriage-capability/p8_kb_snapshot.py:187-188`
- Test: `tests/test_phase8_marriage_capability.py`（`TestKbEquivalence` 类内新增）

- [ ] **Step 1: 准备环境（phase8 worktree `G:\project\agent-phase8`，分支 `task/phase8-marriage-capability`）**

```powershell
python knowledge-base/bazi_kb.py --build   # 已验证可重建（976 gejue 等行数）
```

- [ ] **Step 2: 写失败测试**（`TestKbEquivalence` 类内追加）

```python
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
```

- [ ] **Step 3: 验证失败**

```powershell
python -m pytest tests/test_phase8_marriage_capability.py::TestKbEquivalence::test_regen_paths_are_posix -q
```
预期：FAIL（输出含 `knowledge-base\\bazi_kb.db`）。

- [ ] **Step 4: 最小实现**（187-188 行）

```python
        "source_db": src_db.relative_to(REPO).as_posix(),
        "snapshot_db": snap_db.relative_to(REPO).as_posix(),
```

- [ ] **Step 5: 验证新测试通过；`test_regeneration_deterministic` 仍红（产物未再冻结，预期内）**

```powershell
python -m pytest tests/test_phase8_marriage_capability.py::TestKbEquivalence -q
```
预期：`test_regen_paths_are_posix` PASS；`test_regeneration_deterministic` FAIL（ok 53 vs 59 的既有漂移）。

- [ ] **Step 6: 提交**

```powershell
git add docs/phase8/marriage-capability/p8_kb_snapshot.py tests/test_phase8_marriage_capability.py
git commit -m "fix(phase8): normalize KB snapshot artifact paths to POSIX separators"
```

### Task 2: 当前环境整体重生成（**批准门禁**，D3）

**Files:** 再生成 `docs/phase8/marriage-capability/{kb_snapshot.db, kb_query_set.json, classic_texts_freeze.json, kb_equivalence.json}`

- [ ] **Step 1: 回避 frozen_commit 复用陷阱，先删后生成**

```powershell
git rm docs/phase8/marriage-capability/classic_texts_freeze.json
python docs/phase8/marriage-capability/p8_kb_snapshot.py
```
预期输出：`snapshot+query_set+freeze+equivalence written to …`；`classic_texts_freeze.json` 的 `frozen_commit` == 当前 HEAD。

- [ ] **Step 2: 核对 8 项 blob 全部等于 HEAD 对应 blob**

```powershell
python -c "import json,subprocess;f=json.load(open('docs/phase8/marriage-capability/classic_texts_freeze.json',encoding='utf-8'));bad=[e['path'] for e in f['files'] if e['blob_sha']!=subprocess.check_output(['git','rev-parse','HEAD:'+e['path']]).decode().strip()];print('mismatch:',bad);assert not bad"
```
预期：`mismatch: []`（3 个漂移项更新为 `dc10d574…`/`e8c7c13e…`/`97716ca0…`，5 项不变）。

- [ ] **Step 3: 核对 `kb_query_set.json` 是否字节稳定**（其输入 `required_knowledge.jsonl` 未变）

```powershell
git diff --stat -- docs/phase8/marriage-capability/kb_query_set.json
```
预期：无输出（字节一致）；若出现 diff，停下按根因二同样口径分析后再继续。

### Task 3: 移除 `bazi_kb.db` raw_bytes 钉定（**批准门禁**，D2=A）

**Files:** Modify `docs/phase8/marriage-capability/phase8_freeze_manifest.json:145-149`

- [ ] **Step 1: 删除该 entry 对象（含逗号），并用一行校验 JSON 可解析**

```powershell
python -c "import json;m=json.load(open('docs/phase8/marriage-capability/phase8_freeze_manifest.json',encoding='utf-8'));assert not any(e['path']=='knowledge-base/bazi_kb.db' for e in m['entries']);print('entries:',len(m['entries']))"
```
预期：打印 entries 数（原数 −1），无异常。

### Task 4: manifest/provenance 级联更新（**批准门禁**）

**Files:** `phase8_freeze_manifest.json`、`provenance.json`

- [ ] **Step 1: atomic_add 更新全部变更产物 SHA**

```powershell
python -c "import importlib.util,pathlib;spec=importlib.util.spec_from_file_location('pf','docs/phase8/marriage-capability/p8_freeze.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);P=pathlib.Path('docs/phase8/marriage-capability');entries=[{'path':p.as_posix(),'sha256':m.git_canonical_lf_sha256(p),'strategy':'git_canonical_lf'} for p in [P/'p8_kb_snapshot.py']]+[{'path':p.as_posix(),'sha256':m.json_canonical_sha256(p),'strategy':'json_canonical'} for p in [P/'classic_texts_freeze.json',P/'kb_equivalence.json',P/'kb_query_set.json']]+[{'path':p.as_posix(),'sha256':m.raw_sha256(p),'strategy':'raw_bytes'} for p in [P/'kb_snapshot.db']];m.atomic_add(P/'phase8_freeze_manifest.json',entries);print('ok')"
```

- [ ] **Step 2: 再生成 provenance 并回写其 SHA**

```powershell
python docs/phase8/marriage-capability/p8_provenance.py
python -c "import importlib.util,pathlib;spec=importlib.util.spec_from_file_location('pf','docs/phase8/marriage-capability/p8_freeze.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);P=pathlib.Path('docs/phase8/marriage-capability');m.atomic_add(P/'phase8_freeze_manifest.json',[{'path':'docs/phase8/marriage-capability/provenance.json','sha256':m.json_canonical_sha256(P/'provenance.json'),'strategy':'json_canonical'}]);print('ok')"
```

- [ ] **Step 3: 对账门禁**

```powershell
python docs/phase8/marriage-capability/p8_reconcile.py
```
预期：exit 0，七节全 `ok`，无 `FAIL`。

### Task 5: 全量验证 + 提交（**批准门禁**）

- [ ] **Step 1: 测试文件全绿**

```powershell
python -m pytest tests/test_phase8_marriage_capability.py -q
```
预期：`85 passed`（原 84 + 新增 1；4 个 CI 失败全数转绿）。

- [ ] **Step 2: 确认 acceptance 域零影响**

```powershell
python scripts/generate_acceptance_integration_closure.py --check --candidate-commit 80bc630396f31c6b6c122e49ef97f6d912e6f636 --base-commit 3d3b41cf65af487b03ca5233a109fee14191b88c --no-legacy --tooling-pin-commit ed5493a94d0268b88f2dca448f963880e7cc1ad5
python scripts/generate_acceptance_manifests.py --check --freeze-ref CLASSIC_ACCEPTANCE_FREEZE_V2 --expected-freeze-tag-oid 98c7cb90b0f0d1b8d3f512c657c3a1614303cdf7
```
预期：两命令均 exit 0。

- [ ] **Step 3: 提交**

```powershell
git add -A
git commit -m "refreeze(phase8): v2 against clean chain and current env" -m "Supersede classic_texts_freeze.json to the C2 chain (3 drifted blobs), regenerate snapshot/equivalence artifacts with POSIX path normalization in the current environment (sqlite 3.50.4), and drop the structurally unsatisfiable raw_bytes pin of the gitignored, rebuildable bazi_kb.db; semantic integrity stays gated by TestKbSnapshot and TestKbEquivalence."
```

### Task 6: superseding receipt（**批准门禁**）

- [ ] 新建 `docs/superpowers/<执行日期>-phase8-freeze-v2-superseding-receipt.md`（`<执行日期>` 为执行当日 YYYY-MM-DD 字面；沿用 Review E receipt 结构）：新旧 SHA 对照表（classic_texts_freeze 8 项、kb_snapshot.db、kb_equivalence.json、kb_query_set.json、p8_kb_snapshot.py、manifest、provenance）、环境记录（sqlite 3.50.4、Python、日期）、被移除条目的理由（0.4 节证据）、旧冻结仅留历史效力的声明。提交于同分支。

### Task 7: 推送 + 正式 CI（推送指令由用户单独下达）

- [ ] `git push -u origin task/phase8-marriage-capability`，开 PR（base `integration/classic-texts-clean`）或按用户指示直推集成链。
- [ ] CI 两作业预期 `0 failed`，passed ≥ 2546、skipped 37。
- [ ] 双作业全绿后向用户报告：合并门禁满足，合并与否待用户批准。

## 非目标

- 不改 `acceptance/task1` 历史；不动 `CLASSIC_ACCEPTANCE_FREEZE_V2` 及其 payload/manifests；不合并主线；不处理 337.6 MB `QUALITY_REPORT.json`（已由 C2 排除）。
