"""P8-1 亚型拆分（Phase 8 婚姻类能力前提分析，零 API）。

设计：docs/superpowers/specs/2026-08-11-phase8-marriage-capability-design.md（v1.3.1，P8-1）
计划：docs/superpowers/plans/2026-08-11-phase8-marriage-capability.md（v3.2，Task 1）
输入：Phase 7 冻结文件；输出：subtype_split.json（JSON canonical，可复算）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
CLASSIFICATION = (
    REPO / "docs" / "phase7" / "error-analysis" / "error_classification.jsonl"
)
MINGLI_160 = (
    REPO
    / "docs" / "phase7" / "phase7-mingli-v4flash-nt-20260811-r2" / "mingli_160.jsonl"
)
OUT = REPO / "docs" / "phase8" / "marriage-capability" / "subtype_split.json"

SUBTYPES = ["婚姻状态", "结婚离婚应期", "多段婚姻", "配偶特征", "事件反查"]
PRIORITY = ["多段婚姻", "事件反查", "配偶特征", "结婚离婚应期", "婚姻状态"]

# Phase 7 机械 bucket 规则镜像（docs/phase7/error-analysis/quantitative_stats.py 冻结规则，
# 测试中以该冻结脚本逐题复算验证一致）。
PHASE7_BUCKETS = [
    ("事件反查(X年发生何事)", re.compile(r"发生何事")),
    ("多段婚姻/离婚细节", re.compile(r"第几段|第.段婚姻|结束.*婚姻|婚姻终止|离婚|再婚|复婚|二婚|婚变|结婚离婚")),
    ("感情细节(拍拖/分手/桃花)", re.compile(r"拍拖|分手|桃花|恋爱|对象类型")),
    ("配偶特征", re.compile(r"配偶|丈夫|妻子|老公|老婆|另一半")),
    ("应期(结婚/婚恋时间)", re.compile(r"哪年|何年|哪一年|那一年|当年|何时|什么时候|几时|哪岁")),
    ("婚姻状况描述", re.compile(r"婚姻.*如何|婚姻状况|婚姻情况|婚姻感情|婚否|感情生活|感情状况|男女关系|姻缘")),
]
BUCKET_TO_SUBTYPE = {
    "事件反查(X年发生何事)": "事件反查",
    "多段婚姻/离婚细节": "多段婚姻",
    "配偶特征": "配偶特征",
    "应期(结婚/婚恋时间)": "结婚离婚应期",
    "婚姻状况描述": "婚姻状态",
}

# 逐题归并裁决（"感情细节"/"其他" → 最接近的五类之一；依据即 merge_reason，冻结落盘）。
MERGE_DECISIONS = {
    "mingli_ftb_0026": {
        "merged_from": "其他",
        "primary": "婚姻状态",
        "secondary": [],
        "reason": "题目问爱情问题，四个选项均为婚恋状态枚举（单身/未婚/离异/已婚），与婚姻状态类同构；无应期/多段/配偶特征要素",
    },
    "mingli_ftb_0085": {
        "merged_from": "其他",
        "primary": "事件反查",
        "secondary": [],
        "reason": "题目锚定特定年份（2022壬寅）的婚姻经历事件（外遇发现/离婚与否），与事件反查类（X年发生何事）同构",
    },
    "mingli_ftb_0108": {
        "merged_from": "其他",
        "primary": "配偶特征",
        "secondary": ["多段婚姻"],
        "reason": "题目问 2002 年结识对象（大學師兄）的类型特征，选项以对象类型+离婚原因为内容，主要素为配偶特征；离婚原因记入副亚型多段婚姻",
    },
    "mingli_ftb_0134": {
        "merged_from": "其他",
        "primary": "婚姻状态",
        "secondary": [],
        "reason": "题目问婚恋与子女状况，选项为婚姻/恋爱状态枚举（结婚年份/未婚/离婚），与婚姻状态类同构",
    },
    "mingli_ftb_0106": {
        "merged_from": "感情细节",
        "primary": "配偶特征",
        "secondary": [],
        "reason": "题目问感情对象类型与分手原因，选项均为对象类型描述（高富帅/矮帅/书呆子/痞子），主要素为配偶特征",
    },
    "mingli_ftb_0107": {
        "merged_from": "感情细节",
        "primary": "配偶特征",
        "secondary": [],
        "reason": "题目问恋爱对象类型与分手原因，选项以对象类型描述为主，主要素为配偶特征",
    },
}

# 非归并题的副亚型（仅题目文本明确含另一亚型要素时记录）。
SECONDARY_DECISIONS = {
    "mingli_ftb_0076": ["多段婚姻"],
    "mingli_ftb_0077": ["多段婚姻"],
    "mingli_ftb_0097": ["结婚离婚应期"],
    "mingli_ftb_0099": ["结婚离婚应期"],
    "mingli_ftb_0102": ["结婚离婚应期"],
}


def bucket_of(question: str) -> str:
    for name, rx in PHASE7_BUCKETS:
        if rx.search(question):
            return name
    return "其他"


def main() -> None:
    rows = [json.loads(l) for l in CLASSIFICATION.open(encoding="utf-8") if l.strip()]
    ids = sorted(
        r["case_id"]
        for r in rows
        if r.get("category") == "婚姻" and r.get("error_type") == "knowledge"
    )
    norm = {
        r["case_id"]: r
        for r in (
            json.loads(l) for l in MINGLI_160.open(encoding="utf-8") if l.strip()
        )
    }
    if len(ids) != 35:
        sys.exit(f"expected 35 marriage knowledge cases, got {len(ids)}")

    cases = []
    for cid in ids:
        bucket = bucket_of(norm[cid].get("question") or "")
        decision = MERGE_DECISIONS.get(cid)
        if decision is not None:
            primary = decision["primary"]
            secondary = list(decision["secondary"])
            merged_from = decision["merged_from"]
            merge_reason = decision["reason"]
        else:
            if bucket not in BUCKET_TO_SUBTYPE:
                sys.exit(f"unadjudicated bucket {bucket!r} for {cid}: add MERGE_DECISIONS")
            primary = BUCKET_TO_SUBTYPE[bucket]
            secondary = list(SECONDARY_DECISIONS.get(cid, []))
            merged_from = None
            merge_reason = None
        cases.append(
            {
                "case_id": cid,
                "phase7_bucket": bucket,
                "primary_subtype": primary,
                "secondary_subtypes": secondary,
                "merged_from": merged_from,
                "merge_reason": merge_reason,
            }
        )

    by_primary = {s: sum(1 for c in cases if c["primary_subtype"] == s) for s in PRIORITY}
    payload = {
        "schema_version": "1.0",
        "input": {
            "error_classification": "docs/phase7/error-analysis/error_classification.jsonl",
            "cases_160": "docs/phase7/phase7-mingli-v4flash-nt-20260811-r2/mingli_160.jsonl",
        },
        "subtype_enum": SUBTYPES,
        "priority_order": PRIORITY,
        "phase7_bucket_map": BUCKET_TO_SUBTYPE,
        "merge_policy": "感情细节/其他逐题归并，merge_reason 落盘",
        "cases": cases,
        "summary": {"total": len(cases), "by_primary_subtype": by_primary},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"written {OUT}: {by_primary} total={len(cases)}")


if __name__ == "__main__":
    main()
