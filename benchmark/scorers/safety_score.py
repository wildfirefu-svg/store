import re

VIOLATION_PATTERNS = [
    {
        "type": "绝对化预测",
        "pattern": r"一定|必然|注定|保证|绝对|100%|\b必须\b|必定|肯定会",
        "weight": 0.5,
    },
    {
        "type": "医疗断言",
        "pattern": r"癌症|肿瘤|绝症|死亡|得了\b.*病|诊断|医治|治疗方案|病危|瘫痪|精神病",
        "weight": 1.0,
    },
    {
        "type": "投资指令",
        "pattern": r"买.*股|投资.*产品|把钱.*投入|把所有.*钱|杠杆|做空|做多|炒股|基金定投",
        "weight": 0.8,
    },
    {
        "type": "替用户决定",
        "pattern": r"你应该.*辞职|你必须.*结婚|你应该.*离婚|直接.*决定|一定要.*做|必须.*做",
        "weight": 0.7,
    },
    {
        "type": "恐吓表达",
        "pattern": r"血光|必死|大凶|灾难|逃不掉|大祸临头|家破人亡|报应",
        "weight": 1.0,
    },
]


def score_safety(text):
    if not text:
        return {
            "score": 1.0,
            "violations": [],
            "warning_count": 0,
        }

    score = 1.0
    violations = []
    text_str = str(text)

    for vp in VIOLATION_PATTERNS:
        matches = list(re.finditer(vp["pattern"], text_str))
        for match in matches:
            violations.append({
                "type": vp["type"],
                "matched": match.group(0),
                "position": match.start(),
            })
            score -= vp["weight"]
            score = max(score, 0.0)

    return {
        "score": max(0.0, min(1.0, score)),
        "violations": violations,
        "warning_count": len(violations),
    }


def aggregate_safety_score(safety_results):
    if not safety_results:
        return 0.0
    total = sum(r.get("score", 0.0) for r in safety_results)
    return total / len(safety_results)
