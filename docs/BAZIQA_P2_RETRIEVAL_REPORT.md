# BaziQA P2 Retrieval Quality Upgrade Report

## Implementation

P2 extends the Milestone C retrieval upgrade with local semantic phrase overlap ranking:

- Extracts semantic phrases from question/options/factual answer text.
- Mixes BM25 score, structured score, and semantic overlap score.
- Adds `semantic_overlap:*` to `match_reasons` in RAG trace and prompt.
- Filters generic/noisy phrases such as `出生`, `如何`, `此命`, pure numeric fragments, and phrases starting with `的`.

## Verification

### Non-network tests

Command:

```powershell
python -m pytest -q -m "not e2e"
```

Result:

```text
316 passed, 1 skipped, 7 deselected
```

### Real API validation

#### Full 40-case run before semantic-noise refinement

Report: [run_ecdec259.md](file:///f:/project/agent/docs/p2_real_api_output/run_ecdec259.md)

- Method: structured_reasoning
- RAG: enabled
- rag_k: 2
- Total: 40
- Correct: 9
- Accuracy: 22.5%
- Evidence Coverage: 100%
- Safety Score: 100%

Finding: trace showed overly broad semantic matches such as `出生` and `如何`, which likely introduced retrieval noise.

#### Refined 10-case smoke run after filtering generic phrases

Report: [run_d33408bd.md](file:///f:/project/agent/docs/p2_refined_real_api_output/run_d33408bd.md)

- Method: structured_reasoning
- RAG: enabled
- rag_k: 2
- Total: 10
- Correct: 5
- Accuracy: 50.0%
- Evidence Coverage: 100%
- Safety Score: 100%

Trace check:

- `semantic_overlap` reasons still appear.
- Generic reasons containing `出生`, `如何`, `此命` are removed.

## Conclusion

P2 implementation is technically working and traceable, but the full 40-case pre-refine run did not improve accuracy. The refined 10-case smoke run is promising but too small to be treated as final lift evidence.

Recommended next validation: run a refined 40-case `rag_k=2` real API benchmark to confirm whether the generic-phrase filter improves full-set performance.
