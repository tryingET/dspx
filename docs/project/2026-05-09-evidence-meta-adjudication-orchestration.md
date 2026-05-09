---
summary: "Evidence note for current DSPx jury/adjudication, Oracle/Postgres publication, and GEPA seams relevant to meta-adjudication orchestration."
read_when:
  - "You are reviewing the meta-adjudication orchestration RFC."
  - "You need current-state evidence for DSPx jury/adjudicator and GEPA integration."
type: "evidence"
---

# Evidence: meta-adjudication orchestration current state

## Current DSPx generated-program surfaces

Existing generated-program artifacts already include the raw materials for a future meta-adjudication layer:

- `manifest.json` / `manifest.json.meta.json`
- `behavior_results.json` / `behavior_episode.json`
- `oracle_evidence.json`
- `program_oracle_report.json`
- `program_candidate_state.json`
- `jury.json`
- `jury_selection.json`
- `jury_rubric.json`
- `promotion_review.json`
- `promotion_adjudication_request.json`
- `promotion_decision_template.json`
- optional refined review, jury results, decision, promotion plan, activation packet, and shared Oracle publication receipt sidecars

Relevant current services:

```text
packages/dspx-core/src/dspx/services/program_jury.py
packages/dspx-core/src/dspx/services/program_jury_execution.py
packages/dspx-core/src/dspx/services/program_promotion.py
packages/dspx-core/src/dspx/services/program_promotion_decision.py
packages/dspx-core/src/dspx/services/program_activation_packet.py
packages/dspx-core/src/dspx/services/program_oracle_publication.py
packages/dspx-core/src/dspx/services/program_oracle_publication_preflight.py
```

## Current limitation

The current jury path is deterministic and local. It infers baseline perspectives and writes `program-jury-results-v1`, but it does not perform target research, model-backed juror deliberation, meta-jury verification, or program-adjudicator formation.

The current `program-loop` stops at generated candidate, replay check, local Oracle index/report, optional shared publication, and candidate state. It does not orchestrate a multi-level judging lifecycle.

## Oracle/Postgres evidence substrate

The accepted Oracle publication boundary states that shared Oracle/Postgres is empirical memory, not authority. It is now capable of retaining curated generated-program evidence with explicit publication labels and non-authority flags.

Key existing posture:

- candidate-local Oracle indexes remain SQLite/local scratch;
- shared Oracle publication is explicit opt-in;
- shared publication receipts are evidence only;
- authority-mirror labels require explicit authority refs;
- activation remains blocked until domain/governance requirements are met.

This is the right substrate for storing adjudication behavior traces, including failures and near-misses, so later analysis and GEPA improvement are possible without converting empirical memory into authority.

## GEPA/DSPy optimization seam

The workspace `contrib/dspy` checkout provides `dspy.GEPA`, a reflective prompt optimizer. Important properties for DSPx adjudication:

- GEPA optimizes textual instruction/prompt components of DSPy programs.
- It expects train/validation examples and a metric callable shaped like:

```python
def metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    return dspy.Prediction(score=score, feedback=feedback)
```

- Rich textual feedback is the main learning signal.
- With `track_stats=True`, GEPA exposes detailed candidate and lineage results on the optimized program.

This suggests a safe future lane:

1. keep deterministic DSPx jury execution as baseline/guardrail;
2. introduce separate model-backed DSPy modules for jury selection, jury verification, adjudicator formation, and evidence adjudication;
3. publish all sidecars/traces/outcomes to Oracle/Postgres as non-authoritative behavior memory;
4. curate accepted/rejected/human-corrected examples;
5. use GEPA to optimize judging prompts/rubrics/policies;
6. version optimized adjudication policies separately from activation authority.

## Recent Obsidian/PDF evidence

The Obsidian/PDF transition path now has live-provider generated behavior and a review-only adapter dogfood:

```text
DSPX_PROVIDER=dspy-lm-auth
DSPX_LM_AUTH_MODEL=codex/gpt-5.5
behavior_status=passed
adapter_status=materialized
canonical_mutation_performed=false
wiki_mutation_performed=false
atlas_mutation_performed=false
```

That dogfood proves review-only materialization, not production activation. It is a useful target for the first meta-adjudication pilot because the target has concrete domain risks: source grounding, review-only mutation boundaries, Wiki/Atlas authority separation, and rollout/rollback requirements.
