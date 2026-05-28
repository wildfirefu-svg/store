#!/usr/bin/env python3
"""Three-Layer Retrieval Architecture for BaZi Knowledge Base.

Layer 1 — Query Classifier: routes query to correct KB module + category
Layer 2 — Bigram Jaccard: precise matching within predicted category
Layer 3 — ChromaDB Vector: cross-KB semantic exploration (fallback)
"""

import json, os, re, sys, time, math
from collections import Counter

KB_DIR = os.path.dirname(__file__)

# ============================================================
# Layer 1: Query Classifier
# ============================================================

QUERY_ROUTES = {
    # Module routing: query keywords → (kb_file, category)
    ('gejue', '婚姻断诀'): ['婚姻','结婚','离婚','夫妻','配偶','克夫','嫁','娶','桃花运','感情','外遇','二婚','晚婚'],
    ('gejue', '财运'): ['财运','发财','破财','求财','赚钱','投资','存钱','富','穷','有钱','横财','合伙'],
    ('gejue', '官运'): ['升职','升迁','仕途','当官','公务员','退休','创业','事业','面试','跳槽'],
    ('gejue', '寿元疾厄诀'): ['疾病','健康','生病','身体','寿命','血光','手术','失眠','死','体质'],
    ('gejue', '大运流年诀'): ['今年运势','明年运势','本命年','流年运势','犯太岁','岁运'],
    ('gejue', '小儿关煞'): ['小孩','儿童','宝宝','小儿','童子','婴儿','幼儿','孩子'],
    ('gejue', '十神赋文'): ['十神含义','正官特点','七杀特点','正财偏财','印星','食神伤官'],
    ('gejue', '格局歌诀'): ['格局判定','成格','破格','从格','化气','格局高低','格局层次'],
    ('gejue', '神煞断诀'): ['神煞','贵人','文昌','驿马','华盖','羊刃','天乙','桃花位'],
    ('gejue', '六亲断诀'): ['六亲','父母','子女','兄弟','姐妹','祖上','亲戚'],
    ('gejue', '纳音断诀'): ['纳音','海中金','炉中火','大林木','剑锋金','天河水'],
    ('gejue', '干支象意诀'): ['甲木','乙木','天干象意','地支象意','干支组合'],
    ('gejue', '铁口直断'): ['铁口','直断','断语','甲午','丁亥','戊子','壬午','癸巳'],
    ('gejue', '病药直断'): ['病药','找药','药到','有病','看病'],
    ('gejue', '做功直断'): ['做功','功神','制用','化用','墓用'],
    ('gejue', '应期直断'): ['什么时候','何时','几时','应期','何年'],
    ('gejue', '滴天髓歌诀'): ['滴天髓','天道','源流','真假','清浊','中和','顺逆'],
    ('gejue', '穷通宝鉴歌诀'): ['穷通宝鉴','调候','十干实物'],
    ('gejue', '性格相貌诀'): ['性格','相貌','长相','脾气'],
    ('gejue', '万年桩'): ['排盘','起运','五虎遁','五鼠遁','藏干','节气口诀'],
    ('nayin', None): ['纳音表','纳音五行','海中金','炉中火'],
    ('shensha', None): ['神煞表','神煞查','驿马在','桃花在','华盖在'],
    ('shishen-combos', None): ['十神组合','官印相生','杀印相生','食神生财','伤官配印'],
    ('ziwei-patterns', None): ['紫微格局','紫府同宫','日月并明','火贪格'],
    ('bingyao', None): ['病药配对','财多身弱','杀重攻身','寒局无暖'],
    ('yangzhai', None): ['阳宅','卧室方位','缺角','九宫','风水调理'],
    ('wuyun-liuqi', None): ['五运六气','体质偏性','天刑之年','五运','六气'],
}

# Priority 1 keywords (high weight — category-specific)
P1_KEYWORDS = [
    '婚姻','结婚','离婚','夫妻','配偶','克夫','感情',
    '财运','发财','破财','求财','赚钱','投资','存钱',
    '升职','升迁','仕途','当官','公务员','退休','创业','事业',
    '疾病','健康','生病','身体','寿命','血光','手术',
    '小孩','儿童','宝宝','小儿','童子','孩子',
    '排盘','起运','五虎遁',
]
# Keywords that override even P1 matches (strongest priority)
P0_KEYWORDS = ['小孩','儿童','宝宝','小儿','童子','孩子']  # 小儿关煞 always wins

# Load trained centroid model if available
_centroid_model = None

def _load_centroid_model():
    global _centroid_model
    if _centroid_model is None:
        path = os.path.join(KB_DIR, '.query_classifier.json')
        if os.path.exists(path):
            _centroid_model = json.load(open(path, encoding='utf-8'))
        else:
            _centroid_model = False
    return _centroid_model

def _cosine(v1, v2):
    import math
    dot = sum(v1.get(k,0) * v2.get(k,0) for k in set(v1)|set(v2))
    n1 = math.sqrt(sum(w*w for w in v1.values())) or 1
    n2 = math.sqrt(sum(w*w for w in v2.values())) or 1
    return dot / (n1 * n2)

def _tfidf_vector(text):
    import math
    bgs = _bigrams(text)
    tf = Counter(bgs)
    total = sum(tf.values()) or 1
    model = _load_centroid_model()
    if not model: return {}
    idf = model['idf']
    return {bg: (cnt/total) * idf.get(bg, 1.0) for bg, cnt in tf.items() if bg in idf}

def classify(query):
    """Layer 1: Hybrid classifier — keyword rules + TF-IDF centroid fallback."""
    best_score = 0
    best_route = (None, None)

    # Primary: keyword rules
    for (module, cat), keywords in QUERY_ROUTES.items():
        score = 0
        for kw in keywords:
            if kw in query:
                score += 5 if kw in P0_KEYWORDS else (3 if kw in P1_KEYWORDS else 1)
        if score > best_score:
            best_score = score
            best_route = (module, cat)

    # If keyword rules found ANY match (score >= 1), return it — don't let centroid override
    if best_score >= 1:
        return best_route

    # Secondary: TF-IDF centroid for low-confidence queries
    model = _load_centroid_model()
    if model and model.get('centroids'):
        qv = _tfidf_vector(query)
        if qv:
            best_sim = 0
            best_cat = None
            for cat, cvec in model['centroids'].items():
                sim = _cosine(qv, cvec)
                if sim > best_sim:
                    best_sim = sim
                    best_cat = cat
            if best_sim > 0.3:  # confidence threshold
                return (None, best_cat)

    return best_route if best_score > 0 else (None, None)


# ============================================================
# Layer 2: Bigram Jaccard (within category)
# ============================================================

def _bigrams(text):
    chars = re.sub(r'[^一-鿿]', '', text)
    if len(chars) < 2:
        return {chars} if chars else set()
    return {chars[i:i+2] for i in range(len(chars)-1)}

def _jaccard(s1, s2):
    if not s1 or not s2: return 0.0
    return len(s1 & s2) / len(s1 | s2)

def search_gejue(query, category=None, top_k=5):
    """Layer 2: Bigram search within gejue, optionally filtered by category."""
    path = os.path.join(KB_DIR, 'gejue.json')
    if not os.path.exists(path):
        return []
    entries = json.load(open(path, encoding='utf-8'))['entries']
    qb = _bigrams(query)
    scored = []
    for e in entries:
        if category and e.get('category') != category:
            continue
        tb = _bigrams(e.get('text', '') + ' ' + ' '.join(e.get('tags', [])))
        sim = _jaccard(qb, tb)
        for t in e.get('tags', []):
            if t in query: sim += 0.15
        if e.get('category', '') in query: sim += 0.1
        if sim > 0.01:
            scored.append((sim, e))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:top_k]]


# ============================================================
# Layer 3: ChromaDB Vector (cross-KB semantic fallback)
# ============================================================

_vector_search = None

def _get_vs():
    global _vector_search
    if _vector_search is None:
        try:
            from search_vector import VectorSearch
            _vector_search = VectorSearch()
        except Exception:
            _vector_search = False
    return _vector_search

def search_vector(query, source=None, top_k=5):
    """Layer 3: ChromaDB vector semantic search across all KB."""
    vs = _get_vs()
    if not vs:
        return []
    try:
        return vs.search(query, top_k=top_k, source_filter=source)
    except Exception:
        return []


# ============================================================
# Unified Search (three-layer)
# ============================================================

def _search_kb(query, top_k=5):
    """Search via SQLite knowledge base (bazi_kb)."""
    try:
        sys.path.insert(0, KB_DIR)
        import importlib.util
        spec = importlib.util.spec_from_file_location('bazi_kb', os.path.join(KB_DIR, 'bazi_kb.py'))
        kb_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kb_mod)
        kb = kb_mod.BaziKnowledgeBase()
        results = kb.fulltext_search(query, top_k)
        kb.close()
        return results
    except Exception:
        return []

def search(query, top_k=5):
    """Unified search — SQLite KB first, then three-layer fallback.
    0. SQLite KB fulltext search (primary)
    1. Classify query → (module, category)
    2. Bigram search within category
    3. Vector search as fallback for cross-KB
    """
    t0 = time.time()
    results = {'layer': 0, 'module': '', 'category': '', 'items': [], 'time_ms': 0}

    # Layer 0: SQLite KB (fastest, most comprehensive)
    kb_items = _search_kb(query, top_k)
    if kb_items:
        results['layer'] = 0
        results['items'] = [{'text': item.get('text','')[:120],
                             'source': item.get('_source', 'gejue'),
                             'category': item.get('category',''),
                             'id': item.get('id','')} for item in kb_items]
        results['time_ms'] = round((time.time() - t0) * 1000)
        return results

    module, category = classify(query)
    results['module'] = module
    results['category'] = category

    # Layer 1 + 2: Classified bigram search
    if module == 'gejue' and category:
        items = search_gejue(query, category=category, top_k=top_k)
        if items:
            results['layer'] = 2
            results['items'] = [{'text': e['text'][:120], 'category': e.get('category',''),
                                 'source': 'gejue.json', 'id': e.get('id','')} for e in items]
            results['time_ms'] = round((time.time() - t0) * 1000)
            return results

    # Layer 1 + 3: Vector search for non-gejue or unfound
    if module and module != 'gejue':
        items = search_vector(query, source=f'{module}.json', top_k=top_k)
        if items:
            results['layer'] = 3
            results['items'] = [{'text': i.get('text','')[:120], 'score': i.get('score',0),
                                 'source': i.get('meta',{}).get('source','')} for i in items]
            results['time_ms'] = round((time.time() - t0) * 1000)
            return results

    # Layer 3 fallback: full vector search
    items = search_vector(query, top_k=top_k)
    if items:
        results['layer'] = 3
        results['items'] = [{'text': i.get('text','')[:120], 'score': i.get('score',0),
                             'source': i.get('meta',{}).get('source','')} for i in items]
    results['time_ms'] = round((time.time() - t0) * 1000)
    return results


# ============================================================
# CLI
# ============================================================

def main():
    import argparse
    ap = argparse.ArgumentParser(description='BaZi KB Three-Layer Search')
    ap.add_argument('query', nargs='?', default='', help='Search query')
    ap.add_argument('-n', '--top', type=int, default=5)
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    if not args.query:
        print('Usage: python search.py "查询内容"')
        return

    result = search(args.query, args.top)

    if args.verbose:
        print(f'Layer: {result["layer"]} | Module: {result["module"]} | Category: {result["category"]}')
        print(f'Time: {result["time_ms"]}ms')
    print()

    if not result['items']:
        print(f'No results for "{args.query}"')
        return

    for i, item in enumerate(result['items']):
        print(f'{i+1}. [{item.get("source","")}] {item["text"]}')
        print()


if __name__ == '__main__':
    main()
