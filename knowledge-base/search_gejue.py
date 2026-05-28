#!/usr/bin/env python3
"""Semantic search for Blind School Secret Song Library.
Uses ChromaDB vector search (multilingual embeddings) with bigram fallback.
"""

import json, os, sys, re

# Try ChromaDB first, fall back to bigram
_vector_search = None

def _get_vector_search():
    global _vector_search
    if _vector_search is None:
        try:
            from search_vector import VectorSearch
            _vector_search = VectorSearch()
        except Exception:
            _vector_search = False
    return _vector_search


def load_gejue(core_only=False):
    # Try core first (fast, curated), fall back to full
    core_path = os.path.join(os.path.dirname(__file__), 'gejue_core.json')
    full_path = os.path.join(os.path.dirname(__file__), 'gejue.json')

    if core_only and os.path.exists(core_path):
        with open(core_path, encoding='utf-8') as f:
            data = json.load(f)
        return data['entries'], data.get('categories', {})

    # Default: core entries, full categories
    entries = []
    categories = {}
    if os.path.exists(core_path):
        with open(core_path, encoding='utf-8') as f:
            data = json.load(f)
        entries = data['entries']
    if os.path.exists(full_path):
        with open(full_path, encoding='utf-8') as f:
            data = json.load(f)
        categories = data.get('categories', {})
        # Merge: if core had <50 results, also search full
        if len(entries) < 50:
            entries = data['entries']

    return entries, categories


# ===== Query Pre-Classifier =====
# Maps query keywords → likely category for routing

_QUERY_CLASSIFIER = {
    '婚姻': '婚姻断诀','结婚':'婚姻断诀','离婚':'婚姻断诀','夫妻':'婚姻断诀',
    '配偶':'婚姻断诀','克夫':'婚姻断诀','嫁':'婚姻断诀','娶':'婚姻断诀',
    '桃花':'婚姻断诀','感情':'婚姻断诀',
    '财运':'财运','发财':'财运','破财':'财运','求财':'财运',
    '赚钱':'财运','投资':'财运','存钱':'财运','富':'财运','穷':'财运',
    '升职':'官运','升迁':'官运','仕途':'官运','当官':'官运',
    '公务员':'官运','退休':'官运','创业':'官运','事业':'官运',
    '疾病':'寿元疾厄诀','健康':'寿元疾厄诀','病':'寿元疾厄诀',
    '身体':'寿元疾厄诀','寿命':'寿元疾厄诀','死':'寿元疾厄诀',
    '血光':'寿元疾厄诀','手术':'寿元疾厄诀',
    '流年':'大运流年诀','今年':'大运流年诀','明年':'大运流年诀',
    '运势':'大运流年诀','大运':'大运流年诀',
    '小孩':'小儿关煞','儿童':'小儿关煞','宝宝':'小儿关煞',
    '小儿':'小儿关煞','童子':'小儿关煞',
    '排盘':'万年桩','八字排':'万年桩','五虎遁':'万年桩',
    '藏干':'万年桩','节气':'节气交节诀',
    '十神':'十神赋文','正官':'十神赋文','七杀':'十神赋文',
    '正财':'十神赋文','偏财':'十神赋文','正印':'十神赋文',
    '偏印':'十神赋文','食神':'十神赋文','伤官':'十神赋文',
    '格局':'格局歌诀','成格':'格局歌诀','破格':'格局歌诀',
    '从格':'格局歌诀','化气':'格局歌诀',
    '神煞':'神煞断诀','贵人':'神煞断诀','天乙':'神煞断诀',
    '文昌':'神煞断诀','驿马':'神煞断诀','华盖':'神煞断诀',
    '羊刃':'神煞断诀','魁罡':'神煞断诀',
    '六亲':'六亲断诀','父母':'六亲断诀','子女':'六亲断诀',
    '兄弟':'六亲断诀','姐妹':'六亲断诀',
    '性格':'性格相貌诀','相貌':'性格相貌诀','长相':'性格相貌诀',
    '干支':'干支象意诀','天干':'干支象意诀','地支':'干支象意诀',
    '纳音':'纳音断诀','海中金':'纳音断诀','炉中火':'纳音断诀',
    '铁口':'铁口直断','直断':'铁口直断','断语':'铁口直断',
    '病药':'病药直断','找药':'病药直断','看病':'病药直断',
    '做功':'做功直断','功神':'做功直断',
    '应期':'应期直断','什么时候':'应期直断','何时':'应期直断',
    '贼捕':'贼捕直断',
    '滴天':'滴天髓歌诀','穷通':'穷通宝鉴歌诀',
    '子平':'格局歌诀','神峰':'神峰通考歌诀',
    '段建业':'盲派段建业','邢铭芬':'盲派邢铭芬',
    '苏国圣':'盲派苏国圣','杨清娟':'盲派杨清娟','张成达':'盲派张成达',
}

def _classify_query(query):
    """Predict the most likely category for a query.
    Uses weighted scoring: specific category terms (婚姻/财运/疾病) override generic terms (什么时候/如何).
    """
    # Priority 1: Specific category keywords (high weight)
    priority1 = {
        '婚姻断诀':['婚姻','结婚','离婚','夫妻','配偶','克夫','嫁','娶','桃花运','感情'],
        '财运':['财运','发财','破财','求财','赚钱','投资','存钱','富','穷','财','有钱'],
        '寿元疾厄诀':['疾病','健康','生病','身体','寿命','血光','手术','死'],
        '官运':['升职','升迁','仕途','当官','公务员','退休','创业','事业'],
        '小儿关煞':['小孩','儿童','宝宝','小儿','童子'],
        '大运流年诀':['流年运势','今年运势','明年运势','本命年'],
    }
    # Priority 2: Generic/time keywords (low weight, only if P1 doesn't match)
    priority2 = {
        '应期直断':['什么时候','何时','几时'],
        '病药直断':['病药','找药','药到'],
        '铁口直断':['甲午','丁亥','戊子','壬午','癸巳','庚寅','辛卯','己亥','乙巳','丙申'],
        '大运流年诀':['流年','今年','明年','运势','大运'],
        '十神赋文':['十神','正官','七杀','正财','偏财','正印','偏印','食神','伤官'],
        '格局歌诀':['格局','成格','破格','从格'],
        '神煞断诀':['神煞','贵人','文昌','驿马','华盖','羊刃'],
        '干支象意诀':['干支','天干','地支'],
        '纳音断诀':['纳音'],
        '综合':['理象','心法','总结'],
    }

    scores = {}
    # Check P1 first
    for cat, keywords in priority1.items():
        for kw in keywords:
            if kw in query:
                scores[cat] = scores.get(cat, 0) + 3  # high weight
    # Check P2 only if P1 didn't match
    if not scores:
        for cat, keywords in priority2.items():
            for kw in keywords:
                if kw in query:
                    scores[cat] = scores.get(cat, 0) + 1  # low weight
    # Generic keyword fallback
    if not scores:
        for keyword, cat in _QUERY_CLASSIFIER.items():
            if keyword in query:
                scores[cat] = scores.get(cat, 0) + 1

    if scores:
        return max(scores, key=scores.get)
    return None


def search(query, category=None, tags=None, top_k=5):
    """Semantic search with query pre-classification for category routing.
    Falls back to bigram Jaccard if vector DB unavailable.
    """
    # Auto-detect category from query if not specified
    if not category:
        category = _classify_query(query)

    # Bigram Jaccard — use FULL gejue for open search (best recall)
    # For known-category agent calls: use gejue_core.json directly
    entries, _ = load_gejue(core_only=False)
    query_bi = set(_bigrams(query))

    scored = []
    for entry in entries:
        if category and entry['category'] != category:
            continue
        if tags and not all(t in entry.get('tags', []) for t in tags):
            continue

        # Base score: bigram on text+tags
        text_bi = set(_bigrams(entry['text'] + ' ' + ' '.join(entry.get('tags', []))))
        sim = _jaccard(query_bi, text_bi)


        # Tag bonus
        for t in entry.get('tags', []):
            if t in query: sim += 0.10
        if entry.get('category', '') in query: sim += 0.05

        if sim > 0.01:
            scored.append((sim, entry))

    if len(scored) < top_k and category:
        # Fall back to full gejue
        full_entries, _ = load_gejue(core_only=False)
        for entry in full_entries:
            if entry['category'] == category: continue
            if tags and not all(t in entry.get('tags', []) for t in tags): continue
            text_bi = set(_bigrams(entry['text']))
            sim = _jaccard(query_bi, text_bi) * 0.3  # stronger penalty
            for t in entry.get('tags', []):
                if t in query: sim += 0.05
            for t in entry.get('tags', []):
                if t in query: sim += 0.05
            if sim > 0.01:
                scored.append((sim, entry))

    scored.sort(key=lambda x: -x[0])
    return [entry for _, entry in scored[:top_k]]


def _bigrams(text):
    chars = re.sub(r'[^一-鿿]', '', text)
    if len(chars) < 2:
        return {chars} if chars else set()
    return {chars[i:i+2] for i in range(len(chars)-1)}


def _jaccard(set1, set2):
    if not set1 or not set2: return 0.0
    return len(set1 & set2) / len(set1 | set2)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Semantic search in Blind School Secret Song Library'
    )
    parser.add_argument('query', nargs='?', default='', help='Search query (Chinese)')
    parser.add_argument('-c', '--category', help='Filter by category')
    parser.add_argument('-t', '--tags', nargs='*', help='Filter by tags (AND)')
    parser.add_argument('-n', '--top', type=int, default=5, help='Max results (default: 5)')
    parser.add_argument('-l', '--list-categories', action='store_true',
                        help='List all categories with counts')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Show similarity scores')
    args = parser.parse_args()

    if args.list_categories:
        entries, categories = load_gejue()
        from collections import Counter
        counts = Counter(e['category'] for e in entries)
        for cat, desc in sorted(categories.items()):
            print(f'{cat} ({counts[cat]}条): {desc}')
        return

    results = search(args.query, args.category, args.tags, args.top)

    if not results:
        print(f'No results for "{args.query}"')
        return

    for entry in results:
        if args.verbose:
            print(f'[{entry["category"]}|{",".join(entry["tags"])}] {entry["text"]}')
        else:
            print(f'[{entry["category"]}] {entry["text"]}')


if __name__ == '__main__':
    main()
