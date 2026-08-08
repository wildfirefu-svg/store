from __future__ import annotations

from typing import Any

_MARRIAGE_SHENSHA = {"红艳煞", "桃花", "红鸾", "天喜", "孤鸾煞", "阴差阳错", "咸池"}
_RELATION_TYPES = {"冲", "六冲", "三刑", "自刑", "六害", "三合", "六合", "半合"}
_SUPPORTED_DOMAINS = {"family", "health", "relationship"}


def _shishen_count(counts: dict[str, Any], name: str) -> int:
    try:
        return int(counts.get(name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _pillar_label(pillar: dict[str, Any]) -> str:
    gan = str(pillar.get("gan") or "")
    zhi = str(pillar.get("zhi") or "")
    return (gan + zhi).strip() or "?"


def _branch_relations_line(branch_relations: Any) -> str | None:
    if not isinstance(branch_relations, list):
        return None
    items = []
    for entry in branch_relations:
        if not isinstance(entry, dict):
            continue
        rtype = str(entry.get("type") or "")
        if rtype not in _RELATION_TYPES:
            continue
        detail = str(entry.get("detail") or "").strip()
        pillars = str(entry.get("pillars") or "").strip()
        segment = rtype
        if detail:
            segment = f"{rtype}({detail})"
        if pillars:
            segment = f"{segment}[{pillars}]"
        items.append(segment)
    if not items:
        return None
    return "地支关系: " + "、".join(items)


def _shensha_line(shensha: Any) -> str | None:
    if not isinstance(shensha, list):
        return None
    hits = []
    for entry in shensha:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        if name in _MARRIAGE_SHENSHA:
            position = str(entry.get("position") or "").strip() or "?"
            hits.append(f"{name}@{position}")
    if not hits:
        return None
    return "婚姻相关神煞: " + "、".join(hits)


def _family_lines(chart: dict[str, Any]) -> list:
    four = chart.get("four_pillars") or {}
    year = four.get("year") or {}
    month = four.get("month") or {}
    day = four.get("day") or {}
    hour = four.get("hour") or {}
    counts = (chart.get("shishen_stats") or {}).get("counts") or {}
    lines = []
    lines.append(
        "配偶星: 男命看正财偏财; 女命看正官七杀。"
        f"正官={_shishen_count(counts, '正官')} 七杀={_shishen_count(counts, '七杀')}"
        f" 正财={_shishen_count(counts, '正财')} 偏财={_shishen_count(counts, '偏财')}"
    )
    lines.append(
        "父母星(印星): "
        f"正印={_shishen_count(counts, '正印')} 偏印={_shishen_count(counts, '偏印')}; "
        f"年柱={_pillar_label(year)} 月柱={_pillar_label(month)}"
    )
    lines.append(
        "子女星(食伤): "
        f"食神={_shishen_count(counts, '食神')} 伤官={_shishen_count(counts, '伤官')}; "
        f"时柱={_pillar_label(hour)}"
    )
    lines.append(
        "兄弟星(比劫): "
        f"比肩={_shishen_count(counts, '比肩')} 劫财={_shishen_count(counts, '劫财')}"
    )
    cang = day.get("cang_gan") or []
    cang_shi = day.get("cang_gan_shi_shen") or []
    lines.append(
        f"配偶宫(日支)={day.get('zhi') or '?'} 藏干={list(cang)} 藏干十神={list(cang_shi)}"
    )
    return lines


def _health_lines(chart: dict[str, Any]) -> list:
    dm = chart.get("day_master") or {}
    wuxing = chart.get("wuxing_stats") or {}
    wyq = chart.get("wuyun_liuqi") or {}
    lines = []
    lines.append(
        f"日主={dm.get('gan') or '?'}{dm.get('wuxing') or ''}({dm.get('yinyang') or ''}),"
        f" 十二长生@日={dm.get('shier_changsheng') or '?'}"
    )
    lines.append(
        "五行分布: "
        f"金={wuxing.get('jin', 0)} 木={wuxing.get('mu', 0)}"
        f" 水={wuxing.get('shui', 0)} 火={wuxing.get('huo', 0)}"
        f" 土={wuxing.get('tu', 0)}; "
        f"缺={('、'.join(wuxing.get('missing') or [])) or '无'};"
        f" 最旺={wuxing.get('strongest') or '?'} 最弱={wuxing.get('weakest') or '?'}"
    )
    if wyq:
        lines.append(
            f"五运={wyq.get('五运') or '?'} 主事脏腑={wyq.get('主事脏腑') or '?'}"
            f" 体质倾向={wyq.get('体质倾向') or '?'} 六气={wyq.get('六气') or '?'}"
            f" 外邪倾向={wyq.get('外邪倾向') or '?'}"
        )
    return lines


def _relationship_lines(chart: dict[str, Any]) -> list:
    four = chart.get("four_pillars") or {}
    day = four.get("day") or {}
    hour = four.get("hour") or {}
    counts = (chart.get("shishen_stats") or {}).get("counts") or {}
    lines = []
    lines.append(
        "配偶宫(日支)="
        f"{day.get('zhi') or '?'} 藏干={list(day.get('cang_gan') or [])}"
        f" 藏干十神={list(day.get('cang_gan_shi_shen') or [])}"
    )
    lines.append(
        "配偶星: 男命看正财偏财; 女命看正官七杀。"
        f"正官={_shishen_count(counts, '正官')} 七杀={_shishen_count(counts, '七杀')}"
        f" 正财={_shishen_count(counts, '正财')} 偏财={_shishen_count(counts, '偏财')}"
    )
    lines.append(
        "食伤(子女): "
        f"食神={_shishen_count(counts, '食神')} 伤官={_shishen_count(counts, '伤官')}; "
        f"时柱={_pillar_label(hour)}"
    )
    return lines


def build_domain_summary(chart: dict[str, Any] | None, domain: str | None) -> str | None:
    if not isinstance(chart, dict) or not chart:
        return None
    key = str(domain or "").strip().lower()
    if key not in _SUPPORTED_DOMAINS:
        return None
    if not chart.get("four_pillars"):
        return None
    if key == "family":
        lines = _family_lines(chart)
    elif key == "health":
        lines = _health_lines(chart)
    else:
        lines = _relationship_lines(chart)
    shensha_line = _shensha_line(chart.get("shensha"))
    if shensha_line and key in {"family", "relationship"}:
        lines.append(shensha_line)
    branch_line = _branch_relations_line(chart.get("branch_relations"))
    if branch_line:
        lines.append(branch_line)
    header = f"<命主关键项摘要-{key}>"
    footer = f"</命主关键项摘要-{key}>"
    return "\n".join([header, *lines, footer])
