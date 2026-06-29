# BaziQA Option-grounded Evidence Retrieval Redesign

Date: 2026-06-29

## 1. Background

BaziQA Hybrid Stage 1 ended with a `ROLLBACK` gate decision.

Primary Stage 1 evidence:

| item | result |
|---|---:|
| best flash config | `tfidf_vector`, mean 27.5% |
| best pro Top-2 config | `tfidf_vector`, mean 25.8% |
| pro run results | `10/40`, `12/40`, `9/40` |
| strict retrieved-answer leak | 0.0% |
| Stage 1 gate | `ROLLBACK` |

The current retrieval mechanism retrieves similar historical cases and injects them into the prompt as loose context. This did not create stable choice accuracy. The failure pattern suggests that similar cases are not enough: the model still has to decide how those cases map to A/B/C/D, and that mapping is unstable.

Task 5 domain subsets also showed strong distribution differences:

| domain | pro Top-2 signal |
|---|---|
| `annual_fortune` | strong, both Top-2 configs mean 66.7% |
| `health` | partial, one pro config passes |
| `relationship` | blocked |
| `unknown` | blocked |

The redesign target is to convert retrieved material from broad similar-case context into option-specific evidence that directly supports, contradicts, or fails to support each candidate answer.

## 2. Problem statement

The current flow is case-centered:

```text
current chart + question -> retrieve similar cases -> inject case summaries -> model picks A/B/C/D
```

This has three problems:

1. Evidence is not aligned to answer options.
2. Retrieved cases are presented as narrative facts rather than judgment primitives.
3. The model performs the final evidence-to-option mapping implicitly, so repeated runs can disagree even when retrieval is stable.

The new flow should be option-centered:

```text
current chart + question + each option -> retrieve option evidence -> compare evidence per option -> model picks A/B/C/D
```

## 3. Goals

1. Build option-grounded retrieval that retrieves evidence separately for A/B/C/D.
2. Make every injected evidence item traceable to a source case and match reason.
3. Preserve strict holdout isolation.
4. Keep the initial implementation local and deterministic except for the final model call.
5. Produce trace output that can diagnose whether an answer failed due to retrieval, evidence ranking, or model choice.
6. Improve the next gate attempt from Stage 1 `ROLLBACK` toward at least `GRAY_A`, with a path to `PASS`.

## 4. Non-goals

1. Do not add external vector database infrastructure in the first version.
2. Do not hand-label a large new evidence corpus before proving the approach.
3. Do not tune on the full 2025 holdout answer labels beyond the existing evaluation protocol.
4. Do not use current-question answer labels in retrieval, prompt construction, or evidence ranking.
5. Do not promote domain subset gains as full Stage 1 success unless the primary holdout gate passes.

## 5. Proposed design

### 5.1 New retrieval unit: OptionEvidence

Each option receives its own evidence list.

```json
{
  "option_label": "B",
  "option_text": "2024年事业有明显转折",
  "evidence": [
    {
      "case_id": "2021_xxx",
      "person_id": "p123",
      "score": 0.72,
      "stance": "support",
      "match_reasons": ["domain:annual_fortune", "option_keyword:转折", "chart_feature:食伤生财"],
      "fact_excerpt": "流年变化明显，事业发生转折 -> 事业调整",
      "source_domain": "annual_fortune",
      "source_answer_option_text": "事业调整"
    }
  ]
}
```

Required fields:

| field | meaning |
|---|---|
| `option_label` | `A/B/C/D` |
| `option_text` | option text from the current question |
| `case_id` | source corpus row or aggregated person id |
| `score` | deterministic retrieval score |
| `stance` | `support`, `contradict`, or `related` |
| `match_reasons` | human-readable score components |
| `fact_excerpt` | short evidence text shown to the model |
| `source_domain` | source row/case domain |
| `source_answer_option_text` | historical correct option text, not current answer |

The first version may only emit `support` and `related`; `contradict` can be added once negative matching is reliable.

### 5.2 Option-grounded retrieval API

Add a new method beside the existing case-level retrieval:

```python
CaseIndex.option_evidence(
    features,
    question: str,
    options: list[str],
    domain: str | None = None,
    k_per_option: int = 2,
) -> dict[str, list[dict]]
```

Expected output:

```python
{
    "A": [evidence_a1, evidence_a2],
    "B": [evidence_b1, evidence_b2],
    "C": [evidence_c1, evidence_c2],
    "D": [evidence_d1, evidence_d2],
}
```

Scoring components:

| component | purpose |
|---|---|
| domain match | keep evidence within the current question's domain when possible |
| option keyword overlap | align evidence with each candidate answer |
| question keyword overlap | preserve task intent |
| chart structure overlap | compare extracted chart features |
| annual-fortune temporal cues | boost year/flow-year/major-luck terms for annual questions |
| generic penalty | penalize vague overlaps like `情况`, `容易`, `判断` |
| source diversity penalty | prevent one person/case from dominating all four options |

The scorer should record every positive and negative component in `match_reasons`.

### 5.3 Prompt format

The prompt should replace the old loose similar-case block with an option evidence block.

```text
<选项证据>
A. {option_text}
- support/related evidence 1: ...
- support/related evidence 2: ...

B. {option_text}
- support/related evidence 1: ...
- support/related evidence 2: ...

C. {option_text}
- 暂无强证据

D. {option_text}
- support/related evidence 1: ...
</选项证据>
```

The model must output an evidence table before the final answer:

```text
A: 支持/反驳/无证据；理由：...
B: 支持/反驳/无证据；理由：...
C: 支持/反驳/无证据；理由：...
D: 支持/反驳/无证据；理由：...
最终答案：X
```

The final answer parser remains unchanged: `最终答案：X` has highest priority.

### 5.4 Trace format

Per-case detail JSONL should include option evidence.

```json
{
  "case_id": "2025_001",
  "domain": "annual_fortune",
  "predicted_answer": "B",
  "expected_answer": "B",
  "correct": true,
  "retrieval_mode": "option_grounded",
  "option_evidence": {
    "A": [{"case_id": "...", "score": 0.31, "match_reasons": ["..."]}],
    "B": [{"case_id": "...", "score": 0.72, "match_reasons": ["..."]}],
    "C": [],
    "D": [{"case_id": "...", "score": 0.28, "match_reasons": ["..."]}]
  },
  "evidence_coverage": {
    "A": 1,
    "B": 2,
    "C": 0,
    "D": 1
  }
}
```

Trace invariants:

1. Every option key exists.
2. Every evidence item has `case_id`, `score`, `match_reasons`, and `fact_excerpt`.
3. No current-question answer label is used in retrieval input.
4. No holdout file is loaded into the index.
5. Current expected answer may appear only in scorer output fields after model execution, never in retrieval context.

## 6. Evaluation plan

### 6.1 Non-network tests

Add deterministic tests for:

1. `CaseIndex.option_evidence` returns A/B/C/D keys.
2. Evidence respects `k_per_option`.
3. Option-specific keywords change ranking.
4. Domain match is recorded in `match_reasons`.
5. Source diversity prevents one case from filling every option if alternatives exist.
6. Holdout corpus loading remains rejected.
7. Prompt builder includes `<选项证据>` and per-option lines.
8. Per-case detail export includes `option_evidence` and `evidence_coverage`.
9. Strict answer-leak check remains 0 for synthetic fixtures.

### 6.2 Local smoke

Run a no-network smoke over a small fixture:

```text
option_evidence coverage = 100% of cases have A/B/C/D keys
parser contract remains valid
trace JSONL is complete
```

### 6.3 Real API smoke

First run only 10 cases:

| gate | target |
|---|---:|
| no crash | 100% |
| parser_valid | >= 90% |
| evidence coverage | 100% |
| accuracy | >= 40% |
| strict leak | 0% or explainable |

### 6.4 Full holdout evaluation

If the 10-case smoke passes:

| stage | target |
|---|---:|
| flash 40-case × 3 | mean >= 30%, min >= 25% |
| pro Top-2 × 3 | mean >= 35%, min >= 30% |
| Stage gate | at least `GRAY_A`, ideally `PASS` |

## 7. Rollback conditions

Rollback this redesign if any of the following happens:

1. Option-grounded flash mean is below the current best flash baseline by more than 3pp.
2. Parser validity drops below 90%.
3. Strict retrieved-answer leak becomes non-zero due to prompt construction.
4. Evidence coverage falls below 95% on the primary holdout.
5. Prompt length truncation removes the base BaziQA answer contract.
6. Repeated pro runs still produce mean below 30% with leak below 5%.

## 8. Implementation phases

### Phase 1: Data structure and retrieval

- Add `option_evidence` retrieval method.
- Add deterministic scoring components.
- Add trace schema fixtures.

### Phase 2: Prompt builder integration

- Add `retrieval_mode="option_grounded"`.
- Add option evidence block formatting.
- Preserve existing `rag_k` behavior for legacy mode.

### Phase 3: Benchmark runner integration

- Add CLI flag:

```text
--retrieval-mode option_grounded
--option-evidence-k 2
```

- Export `option_evidence` and `evidence_coverage` in case details JSONL.

### Phase 4: Evaluation scripts and report

- Add focused smoke command.
- Add ablation config for option-grounded evidence.
- Report against Stage 1 baseline.

## 9. Open questions

1. Should `annual_fortune` receive a domain-specific scorer in v1, or should v1 stay generic?
2. Should `contradict` stance be included immediately, or deferred until support/related scoring works?
3. Should the model see historical correct labels as letters, or only historical option text? Recommendation: only historical option text.
4. Should option-grounded retrieval replace legacy RAG, or exist as a parallel retrieval mode first? Recommendation: parallel mode first.

## 10. Recommended decision

Proceed with Option-grounded Evidence Retrieval as a parallel retrieval mode.

Do not replace the legacy retrieval path until the new mode passes:

1. deterministic non-network tests;
2. 10-case real API smoke;
3. 40-case flash repeated evaluation.

The first implementation plan should focus on minimal, traceable option evidence rather than advanced semantic embeddings or large evidence-card authoring.
