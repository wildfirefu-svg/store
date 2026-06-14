#!/usr/bin/env python3
"""Vector semantic search for entire knowledge base using ChromaDB."""

import json, os, sys, time
import chromadb
from chromadb.config import Settings

KB_DIR = os.path.dirname(__file__)
COLLECTION_NAME = "bazi_knowledge_base"
PERSIST_DIR = os.path.join(KB_DIR, ".chroma_db")


class VectorSearch:
    def __init__(self, model_name='paraphrase-multilingual-MiniLM-L12-v2'):
        self.model_name = model_name
        try:
            from chromadb.utils import embedding_functions
            self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=model_name
            )
        except Exception:
            self.ef = None  # fallback to default
        self.client = chromadb.PersistentClient(path=PERSIST_DIR)
        self.collection = self._get_or_build()

    def _get_or_build(self):
        try:
            coll = self.client.get_collection(COLLECTION_NAME)
            if coll.count() > 0:
                return coll
        except Exception:
            pass
        return self._build_index()

    def _build_index(self):
        # Delete existing if any
        try:
            self.client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

        kwargs = {
            "name": COLLECTION_NAME,
            "metadata": {"description": f"BaZi KB vector index ({self.model_name})"}
        }
        if self.ef:
            kwargs["embedding_function"] = self.ef
        coll = self.client.create_collection(**kwargs)

        docs, metadatas, ids_list = [], [], []

        for fname in sorted(os.listdir(KB_DIR)):
            if not fname.endswith('.json') or fname.startswith('.'):
                continue
            path = os.path.join(KB_DIR, fname)
            data = json.load(open(path, encoding='utf-8'))

            for key in ['entries', 'patterns', 'combinations', 'positions',
                         'tiangan', 'dizhi', 'wuyun', 'liuqi', 'rules']:
                items = data.get(key, [])
                if isinstance(items, dict):
                    items = list(items.values())
                if not isinstance(items, list):
                    continue
                for entry in items:
                    if not isinstance(entry, dict):
                        continue
                    text = self._flatten(entry, key, fname)
                    if not text.strip():
                        continue
                    eid = entry.get('id') or entry.get('name') or entry.get('combo') or entry.get('disease') or entry.get('position') or str(len(docs))
                    doc_id = f"{fname}:{eid}"
                    meta = {
                        'source': fname,
                        'type': key,
                        'category': entry.get('category', ''),
                    }
                    tags = entry.get('tags', [])
                    if tags:
                        meta['tags'] = ','.join(tags)
                    docs.append(text)
                    metadatas.append(meta)
                    ids_list.append(doc_id)

        # Batch add
        batch_size = 200
        for i in range(0, len(docs), batch_size):
            end = min(i + batch_size, len(docs))
            coll.add(
                documents=docs[i:end],
                metadatas=metadatas[i:end],
                ids=ids_list[i:end],
            )

        return coll

    def _flatten(self, entry, key, source):
        parts = []
        if key == 'entries':
            parts.append(entry.get('nayin', ''))
            parts.append(entry.get('wuxing', ''))
            parts.append(entry.get('symptom', ''))
            parts.append(entry.get('text', ''))
            m = entry.get('medicine', {})
            parts.append(str(m))
            b = entry.get('baihua', '')
            parts.append(b)
        elif key in ('tiangan', 'dizhi'):
            parts.append(entry.get('gan', entry.get('zhi', '')))
            parts.append(entry.get('wuxing', ''))
            img = entry.get('imagery', {})
            for v in img.values():
                if isinstance(v, list):
                    parts.append(' '.join(v))
                else:
                    parts.append(str(v))
        elif key == 'patterns':
            parts.append(entry.get('name', ''))
            parts.append(entry.get('condition', ''))
            parts.append(entry.get('meaning', ''))
        elif key == 'combinations':
            parts.append(entry.get('combo', ''))
            parts.append(entry.get('gods', ''))
            parts.append(str(entry.get('meaning', {})))
            parts.append(entry.get('condition', ''))
        elif key == 'positions':
            parts.append(entry.get('position', ''))
            parts.append(entry.get('gua', ''))
            parts.append(' '.join(entry.get('represents', [])))
        else:
            parts.append(str(entry))
        return ' '.join(parts)

    def search(self, query, top_k=5, source_filter=None):
        where = None
        if source_filter:
            where = {'source': source_filter}
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )
        output = []
        for i in range(len(results['ids'][0])):
            output.append({
                'id': results['ids'][0][i],
                'text': results['documents'][0][i][:200],
                'score': round(1 - results['distances'][0][i], 4) if results['distances'] else 0,
                'meta': results['metadatas'][0][i],
            })
        return output

    def stats(self):
        return {
            'total_docs': self.collection.count(),
            'collection': COLLECTION_NAME,
            'model': self.model_name,
            'persist_dir': PERSIST_DIR,
        }


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Vector search for BaZi knowledge base')
    ap.add_argument('query', nargs='?', default='', help='Search query (natural language)')
    ap.add_argument('-n', '--top', type=int, default=5)
    ap.add_argument('-s', '--source', default=None, help='Filter by source file')
    ap.add_argument('--stats', action='store_true')
    ap.add_argument('--rebuild', action='store_true')
    args = ap.parse_args()

    if args.rebuild:
        import shutil
        if os.path.exists(PERSIST_DIR):
            shutil.rmtree(PERSIST_DIR)

    t0 = time.time()
    vs = VectorSearch()

    if args.stats:
        s = vs.stats()
        print(f'Documents: {s["total_docs"]}')
        print(f'Build time: {time.time()-t0:.1f}s')
        return

    results = vs.search(args.query, args.top, args.source)
    for r in results:
        print(f'[{r["score"]:.4f}] [{r["meta"].get("source","")}] {r["text"][:100]}')
        print()
    if not results:
        print(f'No results for "{args.query}"')


if __name__ == '__main__':
    main()
