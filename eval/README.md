# Eval

- **Agent harness (offline goldens):** [`eval/harness/`](harness/) — routing, category
  match, conversation contract. Run: `PYTHONPATH=. python -m eval.harness`
- **Retrieval eval (LLM):** known-item RAG below.

---

# Retrieval eval

Automatic **known-item retrieval** evaluation for the knowledge-base RAG
pipeline (`knowledge_bot/services/query/brain_query.py`).

It samples real notes, asks an LLM to write the question each note answers,
runs the **production** `preselect → select` pipeline, and measures whether the
source note is recovered and at what rank.

## Run

```bash
set -a && source .env && set +a      # VAULT_PATH + DEEPSEEK_API_KEY
export PYTHONPATH=.
knowledge_bot/venv/bin/python eval/retrieval_eval.py --n 25 --seed 7
```

Outputs `eval/results.json` (+ `eval/results.png` bar chart for slides).

## Metrics

| Metric | Meaning |
|--------|---------|
| `corpus_notes` | total notes in the knowledge index |
| `searchable_window` | notes that fit the single-shot compact catalog (context cap) |
| `window_coverage` | `searchable_window / corpus_notes` |
| `preselect_recall` | source note survives the stage-1 compact-catalog funnel |
| `select_recall_at_k` | source note is in the final selected set (≤14) |
| `select_recall_at_1` | source note is the **top** selected note |
| `mrr` | mean reciprocal rank across the selected set |
| `answer_coverage` | share of queries that produced a grounded answer |

## Why we evaluate on the *searchable window*

Production preselect runs over one compact catalog capped by context size
(`KNOWLEDGE_COMPACT_CATALOG_MAX_CHARS`). Notes beyond that cap are not searchable
in a single shot, so sampling them would measure the **context cap**, not
retriever quality. We therefore report:

- **`window_coverage`** — how much of the corpus is searchable in one shot (a real
  scaling limit; the honest fix is hierarchical / embedding-based preselect — see roadmap);
- **recall/MRR on the in-window sample** — the true quality of the retriever when
  the target note is actually in scope.

This split is exactly what motivates the embeddings A/B: LLM-catalog retrieval is
strong in-window but caps corpus coverage as the vault grows.

## Honest caveats

- Synthetic known-item questions are a **baseline**, not a labeled QA gold set;
  they bias optimistic because the source note is guaranteed relevant.
- The question prompt forbids quoting rare verbatim strings to reduce trivial
  lexical matching, but lexical leakage is not fully eliminated.
- This harness is the scaffold to grow a **human-labeled** QA set and to A/B
  the current LLM-catalog retriever against an embeddings baseline.
