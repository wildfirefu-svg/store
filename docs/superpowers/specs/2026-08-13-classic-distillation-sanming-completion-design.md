# 《三命通会》经典文本补全 — 设计文档 v2.3.6

- 日期：2026-08-13（v2.3.6 修订）
- 状态：**已批准**（第十一轮终审结论 APPROVED，2026-08-13）
- 终审确认：canonical tar 参数已精确冻结、archive URI 内容寻址、snapshot 幂等复用与漂移拒绝
  完整、九步发布顺序与 8/9 崩溃语义一致、哈希依赖无环、物化状态动态推导不污染不可变 manifest、
  全文版本引用统一为 v2.3.6。
- 收尾项（已落实）：golden archive SHA 测试须冻结具体 fixture 文件名/原始字节/字面量 SHA（见
  实施计划 Task）；§2.5 JSON 块注释已移出代码块。
- 关联：`docs/superpowers/plans/2026-08-13-phase9a-marriage-retrieval.md`（并行 phase9a，不在本设计范围）
- 后续：批准后重新生成 TDD 实施计划
  `docs/superpowers/plans/2026-08-13-classic-distillation-sanming-completion.md`（现计划为废弃草稿）。

## 0. 目标与范围

在既有受控 fill 管线上补齐《三命通会》（sanmingtonghui）缺失的 303 章，使四部经典文本通过
validate/generate_quality_report 门禁。**明确不做**：向量化、RAG 写入、并入 BaziQA、准确率实验、
自动上线、四书之外的文本扩展。

> **外部操作声明**：两类外部操作均需单独批准，互不覆盖：① 原文网页抓取（外部网络）；② 真实模型
> 调用（API）。

### 0.1 现状基线（已核对磁盘）

| 书 | rules | MCQ | raw | 状态 |
|---|---:|---:|---|---|
| 滴天髓 ditiansui | 799 | 646 | 完整 | 见 1A |
| 子平真诠 zipingzhenquan | 156 | 155 | 完整 | 见 1A |
| 穷通宝鉴 qiongtongbaojian | 2312 | 2120 | 完整 | 见 1A |
| 三命通会 sanmingtonghui | 1542 | 777 | 80/383 | G7 不通过 |

**上述"状态"不代表可提交基线**：当前验证器实测四书 `provenance_ok=false`、`end_to_end=false`
（全部）；《穷通宝鉴》另有非 provenance gate 失败。现有规则无 `canonical_key`；《三命通会》首章
ID 从 `smth_000_000` 起（0-based ch_idx）。

《三命通会》现状：
- `chapter_list.txt`：383 行，格式 `<序号>. <标题>\t<URL>`；383 唯一 URL、383 唯一序号（1..383）。
- 前 80 章 `raw_NNN_<标题>.txt`（编号 001..080 连续，标题以 `_` 分隔，如 `raw_001_卷一_原造化之始.txt`）；
  剩余 303 章未抓取；无 `raw_full.txt`。

### 0.2 关键现状约束

1. fill allowlist 仅 `("zipingzhenquan", "qiongtongbaojian")`。
2. `distill_chapter()` 用 `text[:8000]` 静默截断（字符上限，非 token）。
3. `assign_rule_ids()` 用 `{prefix}_{ch:03d}_{i:03d}`（0-based ch）。
4. `BudgetLedger` 强绑定 `run_id/code_sha/rules_sha`，跨 run 加载被拒。
5. `RULE_PROMPT` 含 `__BOOK__`（2 处）、`__CH__`（2 处）、`__TEXT__`（1 处）三个占位符；渲染 =
   `.replace("__BOOK__", book).replace("__CH__", chapter).replace("__TEXT__", text)`。
6. `_RECEIPT_OUTPUT_NAMES` 只覆盖 5 个输出；provenance 结构为
   `file_shas/code_shas/raw_text_shas/remediation_actions`，无 `api_generation`。
7. 非 E2E 全量门禁未归零（3 failed 属 phase8 `bazi_kb.db` 快照一致性）。

## 1. 设计原则（不可谈判）

- **D1 受控批处理**：真实模型调用走冻结 manifest + 双层账本 + 事务发布。
- **D2 无静默截断**：正文全部分段且守恒，否则 fail-closed。
- **D3 可恢复检查点**：一批成功即不可变检查点。
- **D4 单一权威**：每类契约单一权威文件，无复制常量。
- **D5 fail-closed**：任何校验失败即停止。
- **D6 不伪造**：所有 SHA/receipt/预算/调用计数可复算，不手改 `progress.done`。
- **D7 非循环发布**：哈希不形成生成环；审批序列必须 B0→B1 非循环（见 §7.2）。
- **D8 确定性预算**：安全 hard cap 由冻结的强制上限计算（相加）。
- **D9 机器可执行豁免**：豁免 schema 绑定精确历史字节 + 审批 receipt，只豁免缺失上游链，不豁免
  内容完整性与质量门。
- **D10 权威扣账**：project ledger 在每次外部调用前原子扣账；run ledger 每次调用原子持久化，
  无审计断裂窗口。
- **D11 生产门禁不用 assert**：`python -O` 会移除断言；所有上限门禁用显式异常。

## 2. 契约一：原文抓取与事务化 source snapshot

### 2.1 输入冻结

- `chapter_list.txt` 是 383 章唯一权威目录：`^\s*(\d{1,3})\.\s*(.+?)\t(\S+)$`；断言 383 行、
  383 唯一 URL、383 唯一序号，否则 fail-closed。

### 2.2 目录布局（响应体入同一原子 snapshot）

正式书目录冻结布局：

```text
sanmingtonghui/
  source_snapshots/<snapshot_sha256>/
    source_manifest.json
    RESPONSE_ARCHIVE_POINTER.json            # 归档 pointer（指向持久 artifact store）
    extracted/raw_001_<title>.txt ... raw_383_<title>.txt
    responses/raw_081.html ... raw_383.html      # 新抓 303 章必须存在（Git 外归档，见 §2.5）
  active_source_snapshot.json                    # 唯一 pointer（记录 snapshot_sha256 + manifest_sha256）
  all_rules.json
  all_mcq.jsonl
  progress.json
  ...
```

发布顺序（单一事务，P0 冻结——archive pointer 进入构造序列）：
1. staging 构造 `extracted/`（80 导入 + 303 新抓）与 `responses/`（303 新抓）。
2. 从 `responses/` 创建归档包并写入持久 artifact store。
3. 回读并校验 archive SHA、大小及 303 个响应体。
4. 计算 `snapshot_sha256`。
5. 在 staging 写入 `RESPONSE_ARCHIVE_POINTER.json`（含 snapshot_sha256、archive_uri、
   archive_sha256、archive_size、response_count、archive_format）。
6. 计算 pointer SHA，写入 `source_manifest.json`（`response_archive_pointer_sha256`）。
7. 校验 manifest、pointer、archive、303 个响应体完整闭环（任一环不通过即 fail-closed）。
8. 对 staging 目录整体原子重命名为 `source_snapshots/<snapshot_sha256>/`。
9. 最后原子替换单一 active pointer（先写临时 + `os.replace`）。

**canonical tar 与内容寻址 URI（P0 冻结——snapshot 身份与 pointer/manifest 确定性）**：
`snapshot_sha256` 只绑定 383 条 canonical records，但同目录的 pointer 与 manifest 还依赖 tar
元数据与 `archive_uri`；若 tar 生成非确定，相同响应体可能落入同一 `<snapshot_sha256>` 目录却
对应不同 pointer/manifest，破坏不可变与幂等。因此冻结：
- **canonical tar（精确参数，非选择项）**：

```text
archive_format = tarfile.GNU_FORMAT
成员 = 303 个普通文件，不写目录 entry
成员路径 = responses/raw_NNN.html，使用 "/" 分隔
成员顺序 = NNN 数值升序
mtime = 0
uid = 0
gid = 0
uname = ""
gname = ""
mode = 0o644
压缩 = none
```

- **golden archive SHA 测试（冻结）**：使用一个固定小 fixture（如 3 个响应体）生成归档，
  断言其 archive SHA 等于**冻结的 golden 值**，防 Python tarfile 实现或参数漂移。
- **内容寻址 URI**：`archive_uri = <artifact_root>/<archive_sha256>.tar`；`artifact_root`
  在抓取批准时冻结。
- **已存在 snapshot 幂等复用/漂移拒绝**（目标目录已存在时不得覆盖）：
  - manifest、pointer、archive 身份**完全一致** → 复用已有 snapshot，仅切换 active pointer；
  - 任一字段漂移 → fail-closed（禁止覆盖）。
- **确定性测试（冻结）**：
  1. 同一 responses 构建两次，archive/pointer/manifest 字节完全相同；
  2. 修改任一响应体，archive SHA 与 snapshot SHA 均改变；
  3. 已存在且完全一致时幂等复用；
  4. 相同 snapshot SHA 下 pointer 或 manifest 漂移时拒绝覆盖。

**pointer 冻结**（中优）：`active_source_snapshot.json` 同时记录 `snapshot_sha256` 与
`source_manifest_sha256`（manifest 自身 SHA，防 manifest 内容被改而目录名不变）。

**崩溃保证与物化状态（P0 冻结：状态动态推导，不写入不可变 manifest）**：8/9 之间崩溃 →
`<snapshot_sha256>/` 存在但 active pointer 未切 → 孤立 snapshot。物化状态定义（区分不可变发布事件与
当前机器状态）：
- **`published`**：不可变的发布事件（pointer 切换完成），不表示当前机器状态。
- **`materialized`**：由 preflight **动态推导**——303 个响应体全部存在且 SHA 与
  manifest/pointer 一致。
- **`unmaterialized`**：其余一切情况。

**物化状态不得写入 `source_manifest.json`**：snapshot 与 manifest 是内容寻址、不可变对象；
任何状态字段都会改变 manifest 字节与 SHA，使 active pointer 和 snapshot 身份失效。因此：
- `source_manifest.json` **不包含** `materialization_status`。
- 如需缓存，可写 Git 忽略的 `materialization_state.json`，但**每次使用前仍须重新验证**，
  不能作为可信来源。
- restore 成功后**不得修改** source manifest、active pointer 或任何 snapshot 身份字段。

**所有运行入口增加 response materialization preflight**：在完整 provenance 验证与蒸馏执行前，
动态推导指向 snapshot 的物化状态；`unmaterialized` 时 fail-closed（提示先执行
`restore-responses`）。

**物化状态测试（冻结）**：
1. 干净 clone 推导为 `unmaterialized`，且 manifest 字节不变；
2. restore 后推导为 `materialized`；
3. 缺失或篡改任一响应体后重新推导为 `unmaterialized`；
4. restore 前后 manifest SHA、pointer SHA 完全不变。

### 2.3 首次 bootstrap（P0-5 关联）

```python
bootstrap_snapshot(
    legacy_raw_dir,      # 前 80 章 raw_NNN_*.txt
    chapter_list,        # 383 章权威目录
    fetched_records_081_383,  # 新抓 303 章记录
) -> FullSourceSnapshot
```

必须：
- 从 legacy root **导入前 80 章**（按编号匹配 + **标题规范化匹配**，非仅编号；见中优）；
- **校验前 80 章 SHA**（legacy 文件复算与 chapter_list 一致；漂移 fail-closed）；
- 80 + 303 合并为 383；断言 `sorted(ids) == 1..383`（无重复无遗漏）；
- 写入 `source_manifest.json`。

**禁止**：传入 303 项只生成 303 章；传入 383 项时错误重抓历史 80 章（bootstrap 区分
`legacy_raw_dir` 导入 vs `fetched_records_081_383` 新抓）。

**孤立 snapshot 清理**：不得按"非当前 pointer"删除；扫描**全部引用集合**（pointer、batch
manifest、receipt、generation index、provenance）中引用的 snapshot SHA，只删无任何引用的目录。

### 2.4 source canonical record（P0-5 冻结，含完整来源元数据）

snapshot 身份 canonical 记录**必须包含完整来源元数据**——URL 与 encoding 属来源证据，缺失时
可改 manifest 的 URL/encoding 而目录名不变。冻结：

```json
// 新章（responses 必存）
{
  "index": 81,
  "title": "卷六·论命",
  "url": "https://www.44414.cn/...",
  "response_body_sha256": "<sha>",
  "response_body_status": "archived",
  "provenance_level": "full",
  "encoding": "utf-8",
  "extracted_text_sha256": "<sha>",
  "extractor_sha256": "<sha>",
  "normalized_page_title": "<规范化页面标题>"
}
```

```json
// 前 80 章 sentinel（不要把字符串塞进 SHA 字段，字段类型统一为 null + 状态）
{
  "index": 1,
  "title": "卷一·原造化之始",
  "url": "https://www.44414.cn/...",
  "response_body_sha256": null,
  "response_body_status": "historical_unavailable",
  "provenance_level": "historical_text_only",
  "encoding": "utf-8",
  "extracted_text_sha256": "<sha>",
  "extractor_sha256": null,
  "normalized_page_title": null
}
```

- 新旧章节**都显式包含** `response_body_status` 与 `provenance_level`，避免同样的 null 有多种
  解释（中优）。`encoding` 是实际解码采用值，并作为 extractor 输入（进入 extractor SHA 计算的
  输入域），不只是元数据（中优）。

`snapshot_sha256 = sha256(canonical_json([383 canonical records in index order]))`。
新章 `response_body_sha256` 必非 null；前 80 章为 null + `provenance_level=historical_text_only`。

### 2.5 响应体版本控制与持久归档（P0-4 冻结）

- **新抓 303 章响应体是否进入 Git**：**不进入 Git**（`responses/` 目录由 `.gitignore` 排除）。
- **原因**：响应体是网页原始字节（可能大、含广告/脚本），不宜进版本库；Git 只跟踪提取文本
  （`extracted/`）、`source_manifest.json` 与 `RESPONSE_ARCHIVE_POINTER.json`（pointer 本身在
  Git 内，归档包在 Git 外）。
- **持久归档契约（不是临时 staging；中优-2 固定路径）**：
  - 路径固定为 `source_snapshots/<snapshot_sha256>/RESPONSE_ARCHIVE_POINTER.json`（Git 内跟踪），
    内容如下：

```json
{
  "snapshot_sha256": "...",
  "archive_format": "tar",
  "archive_sha256": "...",
  "archive_size": 123456,
  "archive_uri": "<artifact_root>/<archive_sha256>.tar",
  "response_count": 303
}
```

> 说明：`archive_uri` 为内容寻址位置 `<artifact_root>/<archive_sha256>.tar`，见 §2.2。

- **canonical tar / 内容寻址 URI / 幂等复用**的完整契约见 §2.2 发布顺序（本处 pointer 字段与此
  保持一致，不重复定义）：`archive_uri` 为内容寻址位置 `<artifact_root>/<archive_sha256>.tar`，
  tar 按 canonical 规则生成（确定性），已存在 snapshot 幂等复用或漂移拒绝。

- 路径**固定为** `source_snapshots/<snapshot_sha256>/RESPONSE_ARCHIVE_POINTER.json`（中优-2）：
  - `source_manifest.json` 记录该 pointer 的 SHA（`response_archive_pointer_sha256`）；
  - `active_source_snapshot.json` 记录 `source_manifest_sha256`（已有）；
  - `restore-responses` 拒绝 snapshot 与 pointer 不匹配（pointer.snapshot_sha256 必须等于当前
    snapshot SHA，且 pointer SHA 与 manifest 记录一致）。
- 归档包（tar）放在**明确的持久 artifact store**；`staging` 只是暂存，不是最终归档。
  若当前无可用 artifact store，则在**批准抓取时冻结绝对位置**（用户指定持久目录），
  并把 URI 写入 pointer；不得继续称 `benchmark/staging` 为最终归档。
- 恢复流程 `scripts/fetch_sanming_chapters.py restore-responses --snapshot <sha>`：
  1. 读取 Git 内 `RESPONSE_ARCHIVE_POINTER.json`；
  2. 从 `archive_uri` 获取 archive；
  3. 校验 `archive_sha256`/`archive_size`；
  4. 解包；
  5. 校验 303 个 `response_body_sha256`；
  6. 重建 snapshot 的 ignored `responses/`。
- **干净 clone**：初始推导为 `unmaterialized`（无响应体、有 Git 内 pointer，含 archive_uri +
  archive_sha256）；执行 `restore-responses` 并校验 303 个 SHA 后，preflight 动态推导为
  `materialized`（**manifest/pointer 字节不变**）；`materialized` 前禁止完整 provenance 验证与
  蒸馏执行（§2.2 preflight）。物化状态不写入 `source_manifest.json`（见 §2.2 P0）。
- 交付物中"source snapshot 含 responses"表述修正为：`responses/` 是持久归档产物（Git 外，
  由 Git 内 pointer 定位），`extracted/` + manifest + pointer 进入 Git。

### 2.6 抓取协议与门禁

- `scripts/fetch_sanming_chapters.py` 唯一入口（无模型调用）；`tests/test_fetch_sanming_chapters.py`。
- 下载到 staging；批次校验；通过后按 §2.2/§2.3 组装 383 章并原子发布。
- 新抓 303 章必须保留响应体并归档（§2.5）。
- 抓取门禁：robots/许可、限速+退避、429/5xx 记失败、模板漂移、错页门禁（HTTP 200 但页面标题与
  manifest 标题不一致 → fail-closed）。
- 页面标题规范化：去站点后缀/空白/全角半角/小写化；双向 `in` 包含匹配；归一化函数版本化并入
  extractor SHA。

### 2.7 稳定性与测试

幂等重抓（raw 字节、canonical SHA 不变）；测试：URL 重复、序号缺失、HTTP 失败、空正文、模板污染、
错页、响应体缺失、部分抓取不发布、重复执行稳定、bootstrap 恰好 383、孤立 snapshot 按引用集合清理、
崩溃后 pointer/响应体一致、**source canonical record 含 URL/encoding（改 URL 则 snapshot SHA 变）**、
**响应体归档 receipt 校验**。

## 3. 契约二：长章节无损分段（完整 prompt renderer + 可复算限制）

### 3.1 分段器（book/chapter/limits 感知，P0-2 冻结）

```python
@dataclass(frozen=True)
class PromptLimits:
    max_prompt_chars: int = 8000
    max_request_bytes: int = 16000
    # 无 token 硬门（见 §3.3）——token 仅作诊断指标

def segment_chapter(
    text: str,
    *,
    book: str,
    chapter: str,
    limits: PromptLimits,
) -> list[Segment]:
    """按段落切分，但每选取一个 segment 即用完整 renderer 校验字符+字节上限。

    必须寻找满足限制的最大前缀，而不是先按固定字符数切完再整体失败。
    """
```

- 切分器在选取每个 segment 时调用完整 renderer（`render_rule_prompt(book, chapter, text)`），
  并寻找满足字符与 UTF-8 字节限制的最大前缀；不允许"先按固定 `max_chars` 切完，再发现超限而让
  整章失败"。
- 因中文先撞字节门（非字符门），`limits` 同时承载两门；不再暴露裸 `max_chars` 参数。
- `scripts/classic_artifacts.py::segment_manifest_sha256()` 校验辅助；每段记录
  `segment_index/char_start/char_end/text/segment_sha256`。

### 3.2 守恒断言（无重叠，全部满足）

```python
segments[0].char_start == 0
segments[i].char_start == segments[i-1].char_end
segments[-1].char_end == len(normalized_text)
"".join(seg.text for seg in segments) == normalized_text
```

任一条不满足即 fail-closed。

### 3.3 完整 prompt renderer 与可复算限制算法（P0-1 冻结）

**renderer（与现有 `.replace` 链一致，单一权威）**：

```python
def render_rule_prompt(*, book: str, chapter: str, text: str) -> str:
    return (RULE_PROMPT
            .replace("__BOOK__", book)
            .replace("__CH__", chapter)
            .replace("__TEXT__", text))
```

**限制算法（可复算，生产不用 assert；P0-2 取消 token 硬门）**：

```python
MAX_PROMPT_CHARS = 8000
MAX_REQUEST_BYTES = 16000
# token 硬门已删除：当前无确定性 tokenizer。token 数仅作 smoke 报告诊断指标，
# 不参与 fail-closed。未来获得可复算 tokenizer 后，再单独修改协议版本启用。

class PromptLimitError(RuntimeError):
    def __init__(self, violations):
        self.violations = violations
        super().__init__(f"prompt exceeds bounds: {violations}")


def validate_segment_prompt(rendered: str) -> None:
    violations = []
    if len(rendered) > MAX_PROMPT_CHARS:
        violations.append("chars")
    if len(rendered.encode("utf-8")) > MAX_REQUEST_BYTES:
        violations.append("bytes")
    if violations:
        raise PromptLimitError(violations)


def validate_segment(segment_text: str, *, book: str, chapter: str) -> None:
    rendered = render_rule_prompt(book=book, chapter=chapter, text=segment_text)
    validate_segment_prompt(rendered)
```

- `segment_chapter` 通过 `PromptLimits` 感知 book/chapter，并在选取每个 segment 时调用
  `validate_segment`；不暴露裸 `max_chars` 猜测。
- **token 契约（冻结为单一路径）**：删除生产 token 门；只保留字符与 UTF-8 字节硬门；token 数
  作为 smoke 报告中的诊断指标（不参与 fail-closed）。当前没有冻结确定性 tokenizer，故不保留
  `FROZEN_TOKENIZER`/`count_tokens` 条件契约；未来获得可复算 tokenizer 后，单独修改协议版本启用。
- 生产门禁用显式 `PromptLimitError`，不用 `assert`（D11）。

### 3.4 超长自然段 fallback

禁 `text[:8000]`；句子边界（。？！；）→ 硬切 `hard_split=true`；满足 §3.2/§3.3。

### 3.5 测试

短章单段、长章覆盖、超长段 fallback、不丢首尾、重复分段一致、segment SHA 漂移 resume fail-closed、
**渲染后 prompt 超字符/UTF-8 字节上限的负向测试（中文文本先撞字节门）**、
**renderer 与现有 distill_chapter 渲染结果一致**、**分段器在字节门下找到最大前缀（不整章失败）**。

## 4. 契约三：批次蒸馏、ID 稳定、双层账本、provenance 链

### 4.1 allowlist 与修改范围

`VALID_TARGETS_BY_OPERATION["fill"]` 增加 `"sanmingtonghui"`；默认无参不得触发 303 章真实调用，
必须显式传 batch manifest。修改 `distill_lib.py`/`fill_missing_chapters.py`/`classic_artifacts.py`
及对应测试。

### 4.2 batch manifest

章节来自 `chapter_list.txt`，连续且未完成；每批 5–10 章（协议 smoke 后核定）；不可重叠、按序。
字段：`selected_chapter_ids`、`source_sha_map`、`segment_manifest_sha`、`pre_run_output_sha`、
`model/prompt/config_sha`、`batch_hard_cap`、`parent_commit`、`parent_head_sha`、既有
`run_id/code_sha/rules_sha`。

### 4.3 每批事务发布

staging → 校验 → prepared receipt → 原子发布 → completed receipt。失败整批回滚；resume 仅同一
batch manifest。

### 4.4 规则合并、canonical 去重、ID 分配

- canonical_key = sha256(canonical_json({source_book, source_chapter, category, subject,
  condition, rule, original_text}))；前 80 章一次性补写（迁移记录进 provenance）。
- ID 顺序：按固定章节序号排序 → 按 segment_index 合并 → 章内 canonical dedup（同 key 保首见，
  登记 `dedup_origin_segment`）→ 稳定排序（segment_index + `_origin_order`）→ 一次性分配
  `{prefix}_{ch:03d}_{i:03d}`（ch 0-based，章节序号 1→ch=0）→ MCQ 绑定最终 rule ID →
  resume 复用章节号与 segment manifest。
- 兼容金标：前 80 章 ID 不变；金标测试断言 80 章 ID 集合迁移前后一致；80→81 边界测试断言
  第 81 章从 `smth_080_000` 起且不冲突。

### 4.5 恢复状态机（A/B）

- A 类（网络/限流/临时，代码输入未变）：resume 原 run。
- B 类（代码变化）：原 run 标 `ABANDONED`，新 run_id + 新 manifest；从 project ledger 预占剩余。
- 判定由 `code_sha/input_sha` 自动完成。

### 4.6 双层预算账本（attempt_id 级持久化，P0-4 冻结）

现有 `BudgetLedger` 强绑 run_id。冻结两层账本 + **attempt_id 级权威扣账**（无审计断裂窗口）：

- **project ledger**：绑定固定 `experiment_id`，保存累计 reservation 与总 cap；不绑 run_id。
- **run ledger**：绑定 `run_id/code_sha/rules_sha`，记录本 run 的 attempt 归属。

**唯一账本协议（删除"备选预占 run allocation"）**：

```text
project.before_call(attempt_id)    # 原子记录 reservation（写文件+锁，永不退款）
run.record_attempt(attempt_id)     # 原子记录 run 归属（写文件+锁）
external_api_call()
run.record_terminal(attempt_id, status)   # success | failed | interrupted
```

- **每次调用两个账本都原子持久化**（不用"定期持久化"）——project 与 run 每步可对账。
- 崩溃恢复（P0-4）：
  - project reservation 永不退款（预算保守）；
  - 有 project reservation 无 run.record_attempt → `reserved_unattributed`；
  - 有 attempt 无 terminal → `interrupted_unknown`；
  - 恢复不得重新调用，除非重试策略显式允许且再次消耗预算。
- `before_call()` 原子写（临时 + os.replace）、文件锁、corruption/hash 校验；project 耗尽抛异常
  fail-closed（不调用 API）。
- **删除 §v2.2 的"备选预占 run allocation"**——只冻结本协议。

**attempt_id 唯一性与重复调用语义（P0-3 冻结）**：

```python
attempt_id = sha256(canonical_json({
    "run_id": run_id,
    "batch_id": batch_id,
    "chapter_id": chapter_id,
    "segment_id": segment_id,
    "operation": operation,
    "rule_id": rule_id_or_null,
    "attempt_no": attempt_no,
}))
# canonical_json: json.dumps(d, sort_keys=True, ensure_ascii=False,
#                            separators=(",", ":")).encode("utf-8")
```

（中优-3：冻结 `sort_keys=True`、UTF-8、无多余空格，避免字符串拼接歧义。）

规则：
- 每个真实外部请求拥有**唯一 attempt_id**。
- **retry 必须递增 `attempt_no`**，生成新 ID 并**重新扣账**（不复用旧 ID）。
- `project.before_call(existing_attempt_id)` 返回 `ALREADY_RESERVED`（幂等标记）。
- 收到 `ALREADY_RESERVED` 时**禁止再次外部调用**。
- run/project 对同一 ID 的 `operation`、`case`、`attempt_no` 必须一致；
  **duplicate ID 内容不一致视为 corruption**（fail-closed）。
- **负向测试**：重复 ID 不得再次调用；duplicate ID 内容不一致 → corruption。

### 4.7 跨批次 provenance 链（Git-only anchor，P0-3 冻结）

非循环发布顺序：
1. batch manifest
2. staging outputs
3. prepared receipt（绑定输入 + staging SHA）
4. 原子发布 outputs
5. completed receipt（验证正式字节 == prepared 绑定 staging 字节）
6. 更新 generation index（记录 completed receipt SHA）
7. 生成 `batch_anchor_receipt.json`（见下）
8. 明确 pathspec 提交为 commit `Cₙ`

**Git-only 外部锚定（唯一实现，不用"或 audit index"）**：
- genesis = B1 commit SHA（见 §7.2；非占位符）。
- batch N 完成后生成 `batch_anchor_receipt.json`，记录：batch ID、generation index head SHA、
  completed receipt SHA、parent batch commit、source snapshot SHA。
- 明确 pathspec 提交为 commit `Cₙ`。
- batch N+1 manifest 绑定 `Cₙ` 与 head SHA。
- 最终验证器**按 Git parent 链顺序复算所有 batch anchor**。
- **防尾部删除（P0 冻结：方案 A 外部最终审批 receipt）**：Git 内部哈希链只能证明内部自洽，
  不能自行提供最终可信锚点。冻结**仓库外不可变最终审批 receipt**（当前无签名基础设施，选方案 A）：
  - 用户终验后，在 Git 仓库之外保存不可变 `final_anchor_receipt.json`：

```json
{
  "experiment_id": "sanming-303-completion",
  "final_commit": "<C_final>",
  "generation_index_head_sha256": "...",
  "final_audit_receipt_sha256": "...",
  "approved_at": "...",
  "approver": "...",
  "repository_identity": "..."
}
```

  - 验证器通过显式 `--final-anchor <path>` 读取；缺失、SHA 不符或 `final_commit` 不可达均
    fail-closed。
  - **信任边界（中优-2）**：当前无签名基础设施，验证器把用户通过 `--final-anchor` 提供的文件
    视作**外部信任根**；它**不能证明该文件自身"不可变"**（文件本身无签名）。其可信性来自
    该路径由独立于仓库的受控流程（用户终验）提供并妥善保存，而非来自文件内容自证。
  - **不再使用"更后续提交或外部记录"的无限后移锚定**（`C_final ← A1 ← A2 ← ...` 无法防
    整段 Git 尾部重写）。Git-only 链的职责限定为：证明从 B1 到 `C_final` 内部自洽；最终可信锚点
    由 repo 外 `final_anchor_receipt.json` 提供。

**实现要求**：
- index 更新用**原子写**（临时 + os.replace），不用 `write_text()` 直接覆写。
- 单写者锁：基于 `O_CREAT|O_EXCL`；**陈旧锁判定绑定 PID + 进程启动时间 + owner token**
  （仅 PID 会复用，不足）。
- orphan finder 返回**完整 batch entry**（不只 SHA），补登幂等（重复 batch ID/receipt SHA 拒绝）。
- **负向测试**：删除尾部 entry 后从 genesis 重算缩短链 → verify 失败；completed receipt 与正式
  发布字节不一致 → 失败。

### 4.8 每批提交 pathspec

每批用明确 pathspec；下一批 provenance 绑定上一批 commit `Cₙ` + head SHA（不依赖工作区脏状态）。

## 5. 契约四：确定性预算

### 5.1 冻结并强制执行的输入上限（生产常量，协议 smoke 前写入）

```python
MAX_RULES_PER_SEGMENT = 8
MAX_RULE_EXTRACTION_ATTEMPTS = 3
MAX_MCQ_ATTEMPTS_PER_RULE = 3
MAX_PROMPT_CHARS = 8000
MAX_REQUEST_BYTES = 16000
# token 硬门已删除（§3.3）：token 数仅作诊断指标，不参与 fail-closed
```

**`MAX_RULES_PER_SEGMENT` 溢出行为（冻结单一语义）**：parser 解析出的规则 > 8 条时，
**整次规则提取 attempt 无效**并按重试策略处理（计入 `MAX_RULE_EXTRACTION_ATTEMPTS`）——不是
"截断或失败"两种行为。

### 5.2 正确 hard-cap 公式

```text
batch_cap =
    total_segments × MAX_RULE_EXTRACTION_ATTEMPTS
  + total_segments × MAX_RULES_PER_SEGMENT × MAX_MCQ_ATTEMPTS_PER_RULE
```

- 两类调用相加；网络/截断重试已含在 `MAX_*_ATTEMPTS` 中。
- `total_segments` 由 segment manifest 确定（实际冻结，非推测）。
- 超 cap 立即停止（fail-closed）。

### 5.3 预算总览

- project 总 cap = §5.2 对全部批次求和 + 安全余量；独立批准后冻结。
- 3 章协议 smoke 仅验证协议，不推导 cap。
- 所有上限在真实 API smoke 前写入生产常量并带负向测试。

## 6. 模型配置（冻结）

```text
provider=deepseek
model=deepseek-v4-flash
thinking_mode=disabled
temperature=0.0
```

## 7. 阶段门禁与成功标准

### 7.1 阶段 0（不调用 API/网络）

1. 6D SHA 跨 8192 字节边界缺陷 — 已修复（`422d491`）。
2. Phase 8 三项失败 — 二选一写死：修复到干净 clone 全量退出 0，或正式改契约并经独立审批；
   **删除"正式解释即可"分支。**
3. 干净 clone CI 等价门禁退出 0，JUnit XML 保存。

### 7.2 阶段 1A：历史基线整治（E→R→B1 三对象非循环审批序列，P0-1/P0-2 冻结）

**非循环三对象序列（无自引用，文件不记录包含自身的 commit/receipt SHA）**：

1. **`B0`**：提交历史产物 manifest（精确文件 SHA、验证器代码 SHA）。B0 内容不记录 B0 自身 SHA。
2. 创建 **exemption request `E`**（实施脚本生成）：
   - 绑定 B0（`baseline_commit`）、绑定历史文件 SHA（`artifact_sha256_by_path`）；
   - **不含 approval receipt SHA、不含 B1 SHA**（E 不反向引用 R 或 B1）。
3. **独立审核**（非实施脚本）生成 approval receipt `R`：
   - 绑定 B0 SHA、绑定 artifact manifest SHA、绑定 **E 的 SHA**（`exemption_request_sha256`）；
   - R 不含 B1 SHA、不含 schema 自身 SHA。
4. **`B1`**：提交 E + R。B1 SHA 仅由后续 run manifest / generation genesis 记录。

**验证器分别加载 E 与 R，检查（冻结）**：

```text
R.exemption_request_sha256 == sha256(E)
R.baseline_commit == B0
current approval commit == B1（由后续 run manifest 记录，不在 E/R 内）
```

**历史豁免 E / R 结构**：

```json
// E (exemption request) —— 不反向引用 R/B1
{
  "book": "ditiansui",
  "artifact_sha256_by_path": {
    "raw": {"raw_001_xxx.txt": "<sha>", "...": "..."},
    "rules": {"all_rules.json": "<sha>"},
    "mcq": {"all_mcq.jsonl": "<sha>"}
  },
  "baseline_commit": "<B0 SHA>",
  "validator_code_sha256": "<B0 时验证器代码 SHA>",
  "exempted_checks": ["missing_upstream_response_body"],
  "non_exempt_checks": ["artifact_integrity", "quality_gates",
                        "future_generation_provenance"],
  "author": "...", "date": "..."
}
```

```json
// R (approval receipt) —— 由独立审核生成，绑定 E，不反向引用 B1
{
  "exemption_request_sha256": "<sha256(E)>",
  "baseline_commit": "<B0 SHA>",
  "artifact_manifest_sha256": "<B0 中 manifest SHA>",
  "approver": "<独立审核人>",
  "approved_at": "<ISO 时间>"
}
```

**豁免语义（冻结）**：
- 只豁免 `exempted_checks`（缺失上游响应体链）；**绝不豁免** `non_exempt_checks`。
- `artifact_sha256_by_path` 绑定被豁免文件的精确历史字节；后续新增/修改不覆盖，必须走完整
  provenance。
- 验证器对 E 缺失/伪造、R 缺失/伪造、`R.exemption_request_sha256 != sha256(E)`、
  `R.baseline_commit != B0` fail-closed。
- approval receipt 不能由实施脚本自行"批准"生成。

阶段 1A 产出验证器可消费的冻结契约（E/R schema + validator 代码变更），非说明文档。

### 7.3 阶段 2（设计确认）

设计 v2.3.6 已批准。据此**重新生成** TDD 实施计划
`docs/superpowers/plans/2026-08-13-classic-distillation-sanming-completion.md`
（现计划为废弃草稿）。

### 7.4 阶段 3–10

每批执行序：验证 code/prompt/source/前序 commit+head → 建 batch manifest → 运行 →
§4.4 合并/去重/分配 ID → 校验新增规则/MCQ → 单书门禁 → 校验 provenance 链 → 生成 batch anchor →
保存报告与账本 → 按 pathspec 提交 `Cₙ` → 下一批。禁止：跳章、改代码后跑旧 manifest、新建账本绕过
project 累计、手改 `progress.done`、删题过门禁、直接 `regen_mcq.py sanmingtonghui` 全书。

### 7.5 阶段 7：离线协议 smoke（不调用 API/网络）

**完整流程 fake smoke**：batch manifest → segment → validate_segment → merge/dedup → run ledger
（attempt_id 持久化）→ staging → prepared receipt → publish → completed receipt → generation
index → batch anchor → resume → rollback，全程 monkeypatch 网络"调用即失败"。仅协议验证。

### 7.6 阶段 8：真实 API 协议 smoke（单独批准）

3 章真实 API，仅协议验证；检查 call_failed=0、parser 有效率 100%、覆盖 100%、linked MCQ==规则数、
provenance 校验、resume 不重复、事务发布与 receipt 完整、**渲染后 prompt 不超上限**。任一失败即停。
P95/成本需另设分层 pilot 并单独批准。

### 7.7 阶段 9：预算核定（单独批准）

由 §5 冻结安全 cap；预期成本仅审批用。冻结初始批次/每批 cap/项目总 cap/重试上限/超预算停止。
预算确定后再次批准。

### 7.8 阶段 11：最终验收

```powershell
python scripts/validate_classic_distillation.py
python scripts/generate_quality_report.py
python -m pytest tests/test_classic_distillation_remediation.py `
  tests/test_classic_distillation_quality_report.py `
  tests/test_classic_distillation_validator.py -q
ruff check .
python -m pytest tests/ -q --tb=short --timeout=120 --ignore=tests/test_e2e.py
```

最终硬门：G7 383/383；四书 G1–G9 全 PASS（非 provenance gate）；provenance 按 §7.2 schema
（豁免只覆盖已冻结字节，非豁免要求 end_to_end=true）；`overall_pass` 按 schema 语义；
专项测试通过、非 E2E 全量退出 0、工作区无未提交蒸馏产物。

## 8. 交付物

四书完整规则库与 MCQ；原文与 source snapshot（Git 内：extracted + manifest + pointer +
`RESPONSE_ARCHIVE_POINTER.json` + restore 代码；Git 外：响应体归档包）；每批 run manifest/ledger
摘要/receipt/batch anchor；generation index 与 Git-only 逐批锚定 + repo 外 `final_anchor_receipt.json`；
`historical_exemption.json`（E→R→B1 非循环审批序列）；`_validation_report.json`、`QUALITY_REPORT.json`、
蒸馏完成报告、干净 clone 复算说明。

## 9. 风险与待审核点

1. **来源合法性**：外部抓取须 robots/许可/限速/退避/模板漂移门禁；外部网络操作单独批准。
2. **历史豁免**：E→R→B1 三对象非循环审批（E 不反向引用 R/B1，R 由独立审核生成并绑定 E 与 B0）；
   验证器消费逻辑独立审核。
3. **Phase 8**：二选一，删除"正式解释即可"。
4. **Windows 文件名**：标题清洗提升为 §2 正式契约（非法字符/保留名/尾部点/路径上限/碰撞加序号）。
5. **tokenizer**：生产 token 硬门已删除（§3.3）；token 数仅作 smoke 诊断指标。未来获得可复算
   tokenizer 后单独修改协议版本启用。
6. **基线编号**：前 80 章 `raw_001..080` 连续；bootstrap 以 `chapter_list.txt` 383 唯一序号为权威，
   标题规范化匹配。

## 10. 下一步

设计 v2.3.6 已批准。下一步：废弃并**重新生成** TDD 实施计划（离线实现 + fake smoke；
网页抓取与真实模型 API 需分别获得批准）。
