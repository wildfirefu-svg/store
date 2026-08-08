#!/usr/bin/env python3
"""Semantic search for Gan-Zhi Imagery Library (干支象意库).
Uses character bigram Jaccard similarity across all imagery dimensions.
"""

import json
import os
import re


def load():
    path = os.path.join(os.path.dirname(__file__), 'xiangyi.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _bigrams(text):
    chars = re.sub(r'[^一-鿿\w]', '', text)
    if len(chars) < 2:
        return {chars} if chars else set()
    return {chars[i:i+2] for i in range(len(chars)-1)}


def _jaccard(s1, s2):
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def _entry_text(entry, is_tiangan=True):
    """Flatten entry to searchable text."""
    parts = []
    if is_tiangan:
        parts.append(entry['gan'])
        parts.append(entry['wuxing'])
        parts.append(entry['yinyang'])
        img = entry['imagery']
        parts.append(img.get('nature',''))
        parts.append(' '.join(img.get('body',[])))
        parts.append(' '.join(img.get('person',[])))
        parts.append(' '.join(img.get('career',[])))
        parts.append(img.get('emotion',''))
        parts.append(img.get('color',''))
        parts.append(img.get('direction',''))
    else:
        parts.append(entry['zhi'])
        parts.append(entry['wuxing'])
        parts.append(entry['animal'])
        parts.append(entry['month'])
        img = entry['imagery']
        parts.append(img.get('nature',''))
        parts.append(' '.join(img.get('body',[])))
        parts.append(' '.join(img.get('person',[])))
        parts.append(' '.join(img.get('career',[])))
        parts.append(img.get('emotion',''))
        parts.append(img.get('environment',''))
    return ' '.join(parts)


def search(query, kind='all', top_k=5):
    """Semantic search across tiangan/dizhi imagery.
    Args:
        query: natural language query
        kind: 'tiangan', 'dizhi', or 'all'
        top_k: max results
    """
    data = load()
    query_bigrams = _bigrams(query)

    results = []
    for entry_type, entries, is_tg in [
        ('tiangan', data['tiangan'], True),
        ('dizhi', data['dizhi'], False)
    ]:
        if kind not in (entry_type, 'all'):
            continue
        for entry in entries:
            text = _entry_text(entry, is_tg)
            sim = _jaccard(query_bigrams, _bigrams(text))
            # Bonus for exact name match
            name = entry.get('gan', entry.get('zhi', ''))
            if name in query:
                sim += 0.3
            if sim > 0:
                results.append((sim, entry_type, entry))

    results.sort(key=lambda x: -x[0])
    return [
        {'type': t, 'sim': round(s, 3), 'entry': e}
        for s, t, e in results[:top_k]
    ]


def main():
    import argparse
    p = argparse.ArgumentParser(description='Semantic search Gan-Zhi imagery')
    p.add_argument('query', nargs='?', default='', help='Search query (Chinese)')
    p.add_argument('-k', '--kind', default='all', choices=['tiangan','dizhi','all'])
    p.add_argument('-n', '--top', type=int, default=5)
    p.add_argument('-v', '--verbose', action='store_true')
    p.add_argument('-l', '--list', action='store_true', help='List all entries')
    args = p.parse_args()

    if args.list:
        data = load()
        for e in data['tiangan']:
            print(f'[{e["gan"]}] {e["wuxing"]}{e["yinyang"]} | {e["imagery"]["nature"][:30]}')
        for e in data['dizhi']:
            print(f'[{e["zhi"]}] {e["wuxing"]}·{e["animal"]} | {e["imagery"]["nature"][:30]}')
        return

    results = search(args.query, args.kind, args.top)
    if not results:
        print(f'No results for "{args.query}"')
        return

    for r in results:
        e = r['entry']
        name = e.get('gan', e.get('zhi', ''))
        img = e['imagery']
        if args.verbose:
            print(f'[{r["type"]}] {name} (sim={r["sim"]})')
            print(f'  五行:{e["wuxing"]} | 自然:{img["nature"][:40]}')
            print(f'  身体:{" ".join(img["body"][:4])}')
            print(f'  人物:{" ".join(img["person"][:4])}')
            print(f'  职业:{" ".join(img["career"][:4])}')
            print()
        else:
            print(f'[{r["type"]}] {name}({e["wuxing"]}) {img["nature"][:40]}')


if __name__ == '__main__':
    main()
