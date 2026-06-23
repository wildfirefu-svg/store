"""Local case-level retrieval index over BaziQA corpus rows.

Aggregates rows by ``person_id`` so each case carries the chart context together
with the factual events disclosed by the dataset answers, and exposes a
``top_k_cases`` lookup with structured filters and a keyword fallback.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from bazi_features import extract as extract_bazi_features


HOLDOUT_MARKERS = ("holdout", "_holdout")

DOMAIN_HINTS = {
    "career": ("事业", "工作", "职位", "官", "权", "名", "升", "职", "创业", "管理", "仕途"),
    "wealth": ("财", "富", "钱", "收入", "致富", "投资", "经商", "破财", "合作", "挥霍", "守财", "财源", "暴起暴跌"),
    "relationship": ("婚", "感情", "配偶", "夫妻", "恋", "桃花", "离", "伴侣", "再婚", "外遇", "争吵"),
    "health": ("健康", "病", "疾", "伤", "灾", "寿", "身体", "手术", "意外", "慢性"),
    "family": ("父", "母", "子", "女", "家庭", "兄弟", "亲人", "家境", "祖业"),
    "annual_fortune": ("流年", "年份", "大运", "岁运", "应期", "转折", "年份"),
    "study": ("学", "考试", "文凭", "读书", "学历", "升学", "科研"),
    "personality": ("性格", "个性", "为人", "脾气", "保守", "开朗", "固执"),
}

STOP_PHRASES = (
    "命主", "是否", "哪个", "哪项", "以下", "最", "比较", "容易", "可能", "明显", "情况", "选项", "正确", "判断",
    "此命", "出生", "如何", "请问", "现在", "发生", "何事", "哪一", "哪种", "一种", "命局",
)

GENERIC_PHRASES = {
    "出生", "如何", "此命", "命主", "情况", "发生", "何事", "现在", "请问", "父母", "家中", "身材", "外貌",
    "哪个", "哪项", "一种", "哪种", "正确", "判断", "问题", "选项", "比较", "容易",
}


_DEFAULT_RETRIEVAL_CONFIG_PATH = Path(__file__).resolve().parent / "benchmark" / "configs" / "baziqa_retrieval_configs.yaml"


def load_retrieval_config(config_id: str, path: Optional[Path] = None) -> Dict[str, Any]:
    """Resolve a retrieval ablation config by id from baziqa_retrieval_configs.yaml.

    Parameters
    ----------
    config_id : str
        The ``id`` field of the desired config entry (e.g. ``"bm25"``).
    path : Path, optional
        Override path to the YAML file. Defaults to the repository's
        ``benchmark/configs/baziqa_retrieval_configs.yaml``.

    Returns
    -------
    dict
        The entry for the requested ``config_id`` with its ``id`` preserved.

    Raises
    ------
    KeyError
        If ``config_id`` is not present; the message lists available ids
        for quick debugging.
    ValueError
        If the YAML payload is not a list of mappings.
    """
    import yaml  # local import keeps optional yaml dep out of module-load critical path

    yaml_path = Path(path) if path is not None else _DEFAULT_RETRIEVAL_CONFIG_PATH
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError(
            f"retrieval config file {yaml_path} must contain a list of dict entries"
        )

    for entry in raw:
        if entry.get("id") == config_id:
            return entry

    available = [entry.get("id") for entry in raw]
    raise KeyError(
        f"retrieval config id {config_id!r} not found in {yaml_path}; "
        f"available={available}"
    )


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_enabled(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


_TOKEN_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]+")


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    tokens: List[str] = []
    for chunk in _TOKEN_RE.findall(text):
        if re.match(r"[\u4e00-\u9fa5]+", chunk):
            tokens.extend(list(chunk))
        else:
            tokens.append(chunk.lower())
    return tokens


def _hint_matches(text: str, hints) -> List[str]:
    haystack = str(text or "")
    return [h for h in hints if h and h in haystack]


def _semantic_phrases(text: str) -> List[str]:
    text = re.sub(r"[A-D][\.、\s]*", " ", str(text or ""))
    chunks = re.split(r"[，。；、,.?？!！\s]+", text)
    phrases = set()
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        for stop in STOP_PHRASES:
            chunk = chunk.replace(stop, "")
        if len(chunk) >= 3 and chunk not in GENERIC_PHRASES:
            phrases.add(chunk[:12])
        for i in range(0, max(len(chunk) - 2, 0)):
            gram = chunk[i:i + 3]
            if len(gram) == 3 and gram not in GENERIC_PHRASES:
                phrases.add(gram)
        for i in range(0, max(len(chunk) - 3, 0)):
            gram = chunk[i:i + 4]
            if len(gram) == 4 and gram not in GENERIC_PHRASES:
                phrases.add(gram)
    return sorted(
        p for p in phrases
        if p and p not in GENERIC_PHRASES and not p.isdigit() and not p.startswith("的")
    )


class CaseIndex:
    def __init__(
        self,
        corpus_path: Path,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
    ):
        path = Path(corpus_path)
        name = path.name.lower()
        if any(marker in name for marker in HOLDOUT_MARKERS):
            raise ValueError(
                f"Refusing to load holdout file as corpus: {path}. "
                "case_index must never index holdout data."
            )
        if not path.exists():
            raise FileNotFoundError(path)

        self.path = path
        self._embed_fn = embed_fn
        self._cases: List[Dict[str, Any]] = self._load(path)
        self._doc_tokens = [_tokenize(c["text_blob"]) for c in self._cases]
        self._idf = self._build_idf(self._doc_tokens)
        self._build_vector_index()

    # ------------------------------------------------------------ loading
    def _load(self, path: Path) -> List[Dict[str, Any]]:
        people: Dict[str, Dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                person = row.get("person") or {}
                pid = person.get("person_id") or row.get("case_id")
                if not pid:
                    continue
                bucket = people.setdefault(pid, {"person": person, "facts": [], "domains": Counter(), "chart_features": None})
                fact = self._row_fact(row)
                if fact:
                    bucket["facts"].append(fact)
                domain = str(row.get("domain") or "unknown")
                bucket["domains"][domain] += 1
                if bucket["chart_features"] is None and row.get("chart_input"):
                    try:
                        bucket["chart_features"] = extract_bazi_features(row["chart_input"])["structured"]
                    except Exception:
                        pass

        cases: List[Dict[str, Any]] = []
        for pid, bucket in people.items():
            person = bucket["person"]
            birth = person.get("birth") or {}
            year = birth.get("year")
            decade = (int(year) // 10) * 10 if isinstance(year, int) else None
            domains = dict(bucket["domains"])
            text_blob = self._make_text_blob(person, bucket["facts"], domains)
            cases.append({
                "person_id": pid,
                "name": person.get("name") or pid,
                "gender": str(person.get("gender") or ""),
                "birth_year": year,
                "birth_decade": decade,
                "facts": bucket["facts"],
                "text_blob": text_blob,
                "domains": domains,
                "keywords": self._case_keywords(bucket["facts"], domains),
                "semantic_phrases": _semantic_phrases(text_blob),
                "chart_features": bucket.get("chart_features"),
            })
        return cases

    @staticmethod
    def _row_fact(row: Dict[str, Any]) -> str:
        answer = str(row.get("answer") or "").strip().upper()
        options = row.get("options") or []
        question = str(row.get("question") or "").strip()
        if not answer or not options:
            return ""
        idx_map = {"A": 0, "B": 1, "C": 2, "D": 3}
        idx = idx_map.get(answer)
        if idx is None or idx >= len(options):
            return ""
        return f"{question} -> {options[idx]}"

    @staticmethod
    def _case_keywords(facts: List[str], domains: Dict[str, int]) -> List[str]:
        text = "；".join(facts)
        keywords = set()
        for hints in DOMAIN_HINTS.values():
            keywords.update(_hint_matches(text, hints))
        return sorted(keywords)

    @staticmethod
    def _make_text_blob(person: Dict[str, Any], facts: List[str], domains: Dict[str, int]) -> str:
        birth = person.get("birth") or {}
        domain_text = " ".join(domains.keys())
        keyword_text = " ".join(CaseIndex._case_keywords(facts, domains))
        head = (
            f"{person.get('name') or ''}，"
            f"出生 {birth.get('year', '?')}-{birth.get('month', '?')}-{birth.get('day', '?')} "
            f"性别 {person.get('gender') or ''} "
            f"领域 {domain_text} 关键词 {keyword_text}"
        )
        body = "；".join(facts[:8])
        text = f"{head}。事实：{body}"
        
        # 增强：注入八字结构化特征文本
        if person.get("chart_features"):
            chart = person["chart_features"]
            structured_parts = []
            if chart.get("day_master_gan"):
                structured_parts.append(f"日主{chart['day_master_gan']}")
            if chart.get("day_master_wuxing"):
                structured_parts.append(f"日主五行{chart['day_master_wuxing']}")
            if chart.get("four_pillars"):
                pillars = "".join(chart["four_pillars"])  # 例：["甲子", "乙丑", "丙寅", "丁卯"]
                structured_parts.append(f"四柱{pillars}")
            if chart.get("wuxing_stats"):
                wuxing = chart["wuxing_stats"]
                wuxing_str = ",".join(f"{k}{v}" for k, v in wuxing.items() if v > 0)
                structured_parts.append(f"五行分布{wuxing_str}")
            if chart.get("major_universe"):
                major_universe = chart["major_universe"]
                structured_parts.append(f"大运{major_universe}")
            if structured_parts:
                text += "；结构化特征：" + " ".join(structured_parts)
        
        return text[:1200]

    # --------------------------------------------------------------- bm25
    @staticmethod
    def _build_idf(doc_tokens: List[List[str]]) -> Dict[str, float]:
        n = max(len(doc_tokens), 1)
        df: Counter = Counter()
        for tokens in doc_tokens:
            df.update(set(tokens))
        return {term: math.log((n - f + 0.5) / (f + 0.5) + 1.0) for term, f in df.items()}

    def _bm25_scores(self, query_tokens: List[str]) -> List[float]:
        if not query_tokens:
            return [0.0] * len(self._cases)
        k1 = 1.5
        b = 0.75
        avg_dl = (sum(len(t) for t in self._doc_tokens) / max(len(self._doc_tokens), 1)) or 1.0
        scores = []
        for tokens in self._doc_tokens:
            tf = Counter(tokens)
            dl = len(tokens) or 1
            score = 0.0
            for term in query_tokens:
                if term not in tf:
                    continue
                idf = self._idf.get(term, 0.0)
                num = tf[term] * (k1 + 1)
                den = tf[term] + k1 * (1 - b + b * dl / avg_dl)
                score += idf * num / max(den, 1e-6)
            scores.append(score)
        return scores

    def _score_chart_structure(self, case: Dict[str, Any], structured: Dict[str, Any]) -> tuple:
        score = 0.0
        reasons = []
        chart = case.get("chart_features") or {}
        if not chart:
            return score, reasons
        if structured.get("day_master_gan") and structured.get("day_master_gan") == chart.get("day_master_gan"):
            score += 0.45
            reasons.append("same_day_master")
        if structured.get("day_master_wuxing") and structured.get("day_master_wuxing") == chart.get("day_master_wuxing"):
            score += 0.25
            reasons.append("same_day_master_wuxing")
        if structured.get("month_zhi") and structured.get("month_zhi") == chart.get("month_zhi"):
            score += 0.45
            reasons.append("same_month_branch")
        query_wuxing = structured.get("wuxing_stats") or {}
        case_wuxing = chart.get("wuxing_stats") or {}
        overlap = sum(min(int(query_wuxing.get(k, 0) or 0), int(case_wuxing.get(k, 0) or 0)) for k in ("木", "火", "土", "金", "水"))
        if overlap:
            score += min(overlap * 0.08, 0.40)
            reasons.append(f"wuxing_overlap:{overlap}")
        query_shishen = structured.get("shishen_stats") or {}
        case_shishen = chart.get("shishen_stats") or {}
        hits = sorted(k for k in query_shishen if k in case_shishen)
        if hits:
            score += min(len(hits) * 0.15, 0.45)
            reasons.append("shishen_overlap:" + ",".join(hits[:3]))
        return score, reasons

    def _score_semantic_overlap(self, case: Dict[str, Any], query_text: str) -> tuple:
        query_phrases = set(_semantic_phrases(query_text))
        case_phrases = set(case.get("semantic_phrases") or [])
        overlap = sorted(query_phrases & case_phrases, key=lambda x: (-len(x), x))
        if not overlap:
            return 0.0, []
        long_overlap = [p for p in overlap if len(p) >= 3]
        score = min(0.18 * len(overlap) + 0.12 * len(long_overlap), 1.2)
        return score, overlap[:6]

    def _score_structured_match(self, case: Dict[str, Any], structured: Dict[str, Any]) -> tuple:
        score = 0.0
        reasons = []
        decade = structured.get("birth_decade")
        gender = structured.get("gender")
        day_master = structured.get("day_master_gan")
        month_zhi = structured.get("month_zhi")
        query_domain = structured.get("query_domain")
        query_text = str(structured.get("query_text") or "")
        branches = set(structured.get("branches") or [])

        if gender and case["gender"] == gender:
            score += 0.4
            reasons.append("same_gender")
        if decade and case["birth_decade"] is not None:
            gap = abs((case["birth_decade"] or 0) - int(decade))
            if gap == 0:
                score += 0.35
                reasons.append("same_decade")
            elif gap <= 10:
                score += 0.2
                reasons.append("near_decade")
        if query_domain and case.get("domains", {}).get(query_domain):
            score += 1.2
            reasons.append(f"same_domain:{query_domain}")
        domain_hits = _hint_matches(query_text, DOMAIN_HINTS.get(query_domain, ()))
        if domain_hits:
            overlap = [kw for kw in case.get("keywords", []) if kw in domain_hits]
            if overlap:
                score += min(0.25 * len(overlap), 0.75)
                reasons.append("intent_overlap:" + ",".join(overlap[:4]))
        if day_master and day_master in case["text_blob"]:
            score += 0.2
            reasons.append("day_master_text")
        if month_zhi and month_zhi in case["text_blob"]:
            score += 0.15
            reasons.append("month_branch_text")
        if branches:
            overlap = sum(1 for b in branches if b in case["text_blob"])
            if overlap:
                score += min(overlap * 0.08, 0.32)
                reasons.append(f"branch_overlap:{overlap}")
        return score, reasons

    # --------------------------------------------------------- vector index
    _VECTOR_MODEL_NAME = "all-MiniLM-L6-v2"

    def _build_vector_index(self) -> None:
        """Pre-compute embeddings for all corpus cases (sentence-transformers or TF-IDF fallback)."""
        self._case_embeddings: Optional[np.ndarray] = None
        self._vector_model = None
        self._vector_model = None
        if not _env_enabled("BAZI_RAG_VECTOR", False):
            return
        # Try sentence-transformers (check HF cache for model)
        st_mode = os.environ.get("BAZI_RAG_VECTOR_MODE", "auto")
        if st_mode in ("st", "auto"):
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer(self._VECTOR_MODEL_NAME)
                texts = [c["text_blob"] for c in self._cases]
                if texts:
                    self._case_embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
                    self._vector_model = model
                return
            except Exception as exc:
                import logging
                logging.getLogger(__name__).info("sentence-transformers failed, using TF-IDF fallback: %s", exc)
        # Fallback: TF-IDF cosine similarity
        self._build_tfidf_index()

    def _build_tfidf_index(self) -> None:
        """Build TF-IDF matrix for cosine similarity retrieval."""
        if not self._cases:
            return
        n = len(self._cases)
        # Compute TF-IDF vectors using existing token/IDF infrastructure
        self._tfidf_matrix: List[Dict[str, float]] = []
        for tokens in self._doc_tokens:
            tf = Counter(tokens)
            dl = len(tokens) or 1
            vec = {}
            for term, count in tf.items():
                idf = self._idf.get(term, 0.0)
                vec[term] = (count / dl) * idf
            # L2 normalize
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self._tfidf_matrix.append({k: v / norm for k, v in vec.items()})
        # Use identity matrix placeholder so _score_vector_similarity knows TF-IDF is active
        self._case_embeddings = np.zeros((n, 1))  # sentinel

    def _score_vector_similarity(self, query: str) -> List[float]:
        """Return cosine similarity scores between query and all cases."""
        if self._case_embeddings is None or not query:
            return [0.0] * len(self._cases)
        # sentence-transformers path
        if self._vector_model is not None:
            try:
                q_emb = self._vector_model.encode([query], normalize_embeddings=True)
                sims = self._case_embeddings @ q_emb.T
                return sims.flatten().tolist()
            except Exception:
                return [0.0] * len(self._cases)
        # TF-IDF cosine fallback
        if hasattr(self, '_tfidf_matrix') and self._tfidf_matrix:
            query_tokens = _tokenize(query)
            tf = Counter(query_tokens)
            dl = len(query_tokens) or 1
            q_vec = {}
            for term, count in tf.items():
                idf = self._idf.get(term, 0.0)
                q_vec[term] = (count / dl) * idf
            q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0
            q_vec = {k: v / q_norm for k, v in q_vec.items()}
            scores = []
            for doc_vec in self._tfidf_matrix:
                dot = sum(q_vec.get(k, 0.0) * v for k, v in doc_vec.items())
                scores.append(dot)
            return scores
        return [0.0] * len(self._cases)

    # --------------------------------------------------------------- public
    def top_k_cases(
        self,
        features: Dict[str, Any],
        k: int = 3,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not self._cases:
            return []
        query = str(features.get("text_blob") or "")

        if self._embed_fn is not None:
            try:
                _ = self._embed_fn(query)
            except Exception:
                pass

        query_tokens = _tokenize(query)
        scores = self._bm25_scores(query_tokens)
        vector_scores = self._score_vector_similarity(query)

        structured = features.get("structured") or {}
        active_filters = filters or {}

        ranked = []
        for i, (case, score) in enumerate(zip(self._cases, scores)):
            if active_filters.get("gender") and case["gender"] != active_filters["gender"]:
                continue
            structured_weight = _env_float("BAZI_RAG_STRUCTURED_WEIGHT", 1.0)
            semantic_enabled = _env_enabled("BAZI_RAG_SEMANTIC", True)
            semantic_weight = _env_float("BAZI_RAG_SEMANTIC_WEIGHT", 1.0)

            structured_score, reasons = self._score_structured_match(case, structured)
            structured_score *= structured_weight
            chart_score, chart_reasons = self._score_chart_structure(case, structured)
            vector_weight = _env_float("BAZI_RAG_VECTOR_WEIGHT", 1.5)
            vector_score = vector_scores[i] * vector_weight if i < len(vector_scores) else 0.0
            semantic_score, phrase_hits = (0.0, [])
            if semantic_enabled:
                semantic_score, phrase_hits = self._score_semantic_overlap(case, structured.get("query_text") or query)
                semantic_score *= semantic_weight
            all_reasons = list(reasons) + list(chart_reasons)
            if vector_score > 0.2:
                all_reasons.append(f"vector_sim:{vector_scores[i]:.3f}")
            if phrase_hits:
                all_reasons.append("semantic_overlap:" + ",".join(phrase_hits[:4]))
            adj = score + structured_score + chart_score + semantic_score + vector_score
            ranked.append((adj, all_reasons, case))

        ranked.sort(
            key=lambda x: (
                -x[0],
                str(x[2].get("person_id") or ""),
                str(x[2].get("birth_year") or ""),
                str(x[2].get("name") or ""),
            )
        )
        seen: set = set()
        out: List[Dict[str, Any]] = []
        for score, reasons, case in ranked:
            if case["person_id"] in seen:
                continue
            seen.add(case["person_id"])
            item = dict(case)
            item["_score"] = round(float(score), 6)
            item["match_reasons"] = list(reasons)
            out.append(item)
            if len(out) >= k:
                break
        return out
