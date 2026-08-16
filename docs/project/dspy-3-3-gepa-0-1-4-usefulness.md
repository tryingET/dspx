---
summary: "Bounded DSPx product contract for GEPA 0.1.4 proposal strategies, budgets, and receipt evidence."
read_when:
  - "Before using or changing DSPx GEPA multi-proposal optimization."
  - "Before claiming GEPA 0.1.4 reflection-cost, callback, checkpoint, or ReflectionLM support."
type: "reference"
---

# GEPA 0.1.4 usefulness contract

AK-4800 makes the safe, testable part of GEPA 0.1.4's proposal machinery available through DSPx. It does not expose arbitrary upstream objects or imply that every new upstream capability fits DSPy's 3.3.0 adapter and DSPx's typed effect boundary.

## Product surface

`dspx optimize gepa` accepts bounded configuration for three distinct decisions:

1. **parent selection** remains DSPy's existing internal `pareto` default;
2. **proposal sampling** chooses proposal tasks per iteration;
3. **proposal selection** chooses which improving tasks proceed to full validation.

Available proposal sampling:

- `single` — one classic mutation;
- `same-parent` — `n` mutations from one selected parent;
- `independent` — `n` independently selected parent/minibatch tasks;
- `pxn` — `n` mutations for each of `p` selected parents.

Available proposal selection:

- `all-improvements`;
- `best-improvement`;
- `top-k-improvements`.

Available acceptance criteria:

- `strict-improvement` (default);
- `improvement-or-equal`.

Example:

```bash
dspx optimize gepa \
  --program program.py \
  --train train.csv \
  --out generated/gepa-run \
  --student-provider stub \
  --max-metric-calls 40 \
  --proposal-sampling same-parent \
  --proposal-n 2 \
  --proposal-selection top-k-improvements \
  --proposal-top-k 2 \
  --proposal-acceptance strict-improvement
```

DSPx accepts at most eight proposal tasks per iteration and at most four parents. Irrelevant or ambiguous fields fail before provider construction. Multi-proposal mode requires an explicit positive `--max-metric-calls`; DSPy's `auto` and `max_full_evals` calculations do not account for proposal multiplicity.

## Budget truth

`max_metric_calls` is an iteration-boundary **stop threshold**, not a hard pre-effect ceiling. A multi-proposal iteration can perform parent minibatch evaluation, child minibatch evaluation, and selected full validation before the next stop check. DSPx caps proposal fan-out and records both the configured threshold and the observed total, but it does not relabel the threshold as a strict effect limit.

The typed provider adapter continues to serialize direct and optimizer calls through its operation lock. GEPA 0.1.4 normally catches reflection exceptions and continues with no proposal. DSPx therefore wraps only the owned reflection LM: a typed provider failure escapes GEPA's `Exception` fallback during compilation, then is restored as the original safe provider error after optimizer unwinding. No later student evaluation, manifest write, retry, or fallback is allowed after that reflection failure. Indeterminate effects remain terminal.

## Receipt evidence

Every optimizer manifest records:

- exact DSPy and GEPA versions;
- the complete normalized proposal configuration;
- exact upstream sampling and selection class names;
- configured budget and its stop-threshold semantics;
- observed candidate count, metric-call total, full-validation count, and best score/index;
- fixed internal callback counts for proposal starts/ends, acceptance/rejection, budget updates, and continuing upstream errors;
- bounded parent lineage, discovery counts, validation scores, and SHA-256 candidate-component commitments;
- full-array SHA-256 bindings plus an explicit truncation flag when more than 256 candidates exist;
- bounded student/reflection provider metadata and the existing output-payload inventory.

DSPy detailed results are summarized and detached before whole-program save. When the bounded arrays are not truncated, their hashes are independently recomputable from the manifest; a truncated full-array hash remains a runtime assertion rather than independently reconstructable evidence. Candidate sets, prompts, reflection outputs, and raw best outputs are not copied into the manifest or retained through `detailed_results`.

The selected candidate's instructions necessarily remain in the saved optimized program. GEPA/DSPy loggers can also emit proposed instructions or reflection diagnostics to configured console/tracker sinks. The manifest non-retention field is not a general privacy or log-redaction guarantee.

## Deliberately unavailable 0.1.4 features

### Reflection-cost limits

DSPy 3.3.0 passes a plain callable around `DspyAdapter.stripped_lm_call`. GEPA's tracker reports zero cost for that custom callable, so a positive `max_reflection_cost` would look configured without enforcing a truthful cost bound. DSPx does not expose it.

### `ReflectionLM` / `BatchReflectionLM`

DSPy's `DspyAdapter.propose_new_texts` owns proposal generation. GEPA 0.1.4 rejects an additional `reflection_strategy` rather than silently ignoring it. DSPx preserves that owner boundary and does not bypass the typed reflection provider.

### Arbitrary callbacks and tracking objects

Arbitrary callbacks are executable objects and are not accepted from CLI/config. DSPx installs one fixed counter callback that discards event payloads and records bounded lifecycle counts in the manifest. MLflow/W&B remain optional observability sinks, not receipt or authority stores.

### Checkpoint/resume

GEPA 0.1.4 checkpoint state and one-way migration are not yet exposed as a DSPx resumable-effect contract. Failed, interrupted, or indeterminate optimizer attempts cannot be mechanically resumed until a separate custody design proves path binding and effect disposition.

## Nonclaims

The new controls establish credential-free local optimizer execution and bounded configuration/evidence only. They do not establish semantic improvement, answer quality, hard cost ceilings, live-provider compatibility, safe pickle activation, real-output candidate materialization, replay equivalence, promotion, routing, release, or production admission.
