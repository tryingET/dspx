---
name: dspx-program-intent-authoring
description: Convert a user's natural-language DSPy program request into a valid DSPx program-intent-v2 YAML/JSON file for dspx program-gen. Use when asked to author, normalize, validate, or optionally materialize a DSPx program intent from prose.
---

# DSPx Program Intent Authoring

Use this skill to turn natural-language DSPy program requests into structured DSPx `program-intent-v2` YAML/JSON for `dspx program-gen`.

The skill owns **intent authoring guidance only**. DSPx core still owns structured intent validation and program materialization. Do not make DSPx core responsible for natural-language interpretation in this workflow.

## Output contract

Produce a simple valid YAML intent first. Prefer YAML unless the user asks for JSON.

A useful minimum intent contains:

```yaml
name: TicketProgram
objective: Classify support ticket urgency.
inputs:
  - ticket_text
outputs:
  - urgency
metric: exact_match
promotion:
  adjudicator:
    kind: human_operator
    id: local_operator
```

`objective` is the only strictly required field in the current Pydantic model, because `name`, `inputs`, `outputs`, `task_type`, and collection fields have defaults. For Pi authoring, do not rely on those defaults except when the user explicitly wants a sketch; include `name`, `objective`, `inputs`, and `outputs` so assumptions are inspectable.

## Supported intent fields

Current `ProgramIntent` accepts these fields and allows additional metadata:

- `schema_version` — defaults to `program-intent-v2`; include only when helpful.
- `name` — program/class seed name; non-blank.
- `objective` — non-blank behavior goal.
- `inputs` — list of Python identifier field names.
- `outputs` — list of Python identifier field names.
- `input_fields` — richer field specs; each has `name`, optional `type`, optional `desc`.
- `output_fields` — richer field specs; each has `name`, optional `type`, optional `desc`.
- `task_type` — defaults to `single_module`.
- `topology` — optional explicit topology object; omit unless clearly requested.
- `constraints` — list of behavioral or source constraints.
- `examples` — inline example records with `inputs` and `outputs` mappings.
- `examples_path` — optional YAML/JSON list of example records, resolved relative to intent file.
- `metric` — optional metric name such as `exact_match`, `accuracy`, `contains`.
- `runtime` — optional runtime/provider/dataset conditions.
- `jury` — optional future evaluation contract metadata; no juror models are run by `program-gen`.
- `promotion` — optional pending adjudicator/external ref metadata; no promotion happens.
- `options` — optional local metadata; use sparingly.

If `input_fields` or `output_fields` are present, they override `inputs` or `outputs` respectively during normalization. Keep both aligned if including both for readability.

## Clarification policy

Ask clarifying questions only when needed to avoid an invalid or materially misleading intent.

Ask when any of these are missing or ambiguous:

1. The objective cannot be stated in one sentence.
2. Input field names cannot be inferred.
3. Output field names cannot be inferred.
4. A user asks for behavior evidence but provides no example or examples file.
5. Requested fields overlap between inputs and outputs.
6. The user requests external authority, promotion, ranking, or winner selection without an explicit non-authoritative intent boundary.

Do **not** ask when safe defaults are obvious:

- Use `single_module` for a single behavior request.
- Use `exact_match` for simple label/classification examples unless another metric is named.
- Use `human_operator` / `local_operator` as the pending adjudicator when promotion metadata is useful but unspecified.
- Omit `examples` when the user gives none and only wants an intent skeleton.
- Omit `jury` unless perspectives or evaluation criteria are clearly present.
- Omit `topology`, `runtime`, and external authority refs unless clearly requested.

If clarification is needed, ask the smallest possible set of questions, then write the intent after the user answers.

## Field-name normalization

DSPx requires input and output field names to be valid Python identifiers:

- start with a letter or `_`
- contain only letters, digits, and `_`
- not be a Python keyword
- unique within inputs and outputs
- no overlap between input and output names

When the user gives invalid names, normalize to lower snake_case and explain briefly.

Examples:

| User phrase | Intent field |
| --- | --- |
| `ticket text` | `ticket_text` |
| `Ticket Text` | `ticket_text` |
| `urgency-label` | `urgency_label` |
| `class` | `class_label` |
| `1st answer` | `first_answer` or `answer_1` |

Preserve exact user-provided valid field names. Do not rename valid identifiers merely for style.

## Examples policy

- If the user provides examples, include at least one example.
- Each example must use exactly the normalized input/output field names.
- If examples are many or already stored in a file, prefer `examples_path` and keep it relative to the intent file when practical.
- If no examples are provided, either omit `examples` or ask for one only when the user wants behavior evidence from `eval_examples.py` / `behavior_results.json`.
- Do not invent datasets or examples. If you create an illustrative placeholder, label it as a placeholder and do not present it as user evidence.

Example record:

```yaml
examples:
  - inputs:
      ticket_text: "Server is down for all users"
    outputs:
      urgency: high
```

## Optional rich fields

Use richer field specs when the user clearly provides type or description details, or when it prevents ambiguity:

```yaml
input_fields:
  - name: ticket_text
    type: str
    desc: Raw support ticket text
output_fields:
  - name: urgency
    type: Literal['low', 'medium', 'high']
    desc: Urgency label
task_type: single_module
metric: exact_match
constraints:
  - use only supplied inputs
jury:
  perspectives:
    - correctness
    - robustness
promotion:
  adjudicator:
    kind: human_operator
    id: local_operator
```

Keep rich fields small. Do not infer complex topology, dataset splits, GEPA/search policy, juror pools, or external authority refs unless the user explicitly asks.

## Optional YAML/JSON healing

If the authored YAML/JSON is syntactically malformed and `sanitize` is installed, you may use `softwareco/contrib/sanitize` as an optional Pi-side repair helper before `program-gen` validation:

```bash
sanitize lint "$TD/intent.yaml" || sanitize fix "$TD/intent.yaml" > "$TD/intent.healed.yaml"
```

Use `sanitize` only for structured-text syntax healing such as indentation, missing spaces after colons, list dash spacing, trailing commas, fenced JSON, or prose-wrapped JSON. Do not use it to infer fields, normalize identifiers, invent examples, or make semantic/authority decisions. After any fix, inspect or summarize what changed and still let DSPx `ProgramIntent` / `program-gen` validate the resulting file.

## Non-authority boundaries

Always preserve these boundaries:

- Do not run `ak`.
- Do not mutate `governance/work-items.json` or task-scope snapshots.
- Do not invent AK refs, Oracle authority, datasets, promotion decisions, approvals, rankings, winners, or external authority exports.
- Do not generate source code directly; the primary output is structured intent YAML/JSON.
- Do not run Oracle indexing/reporting/refinement/promotion/candidate comparison unless the user explicitly asks after intent generation.
- Do not say a candidate is promoted, selected, approved, or best.
- `program-gen` may write local candidate artifacts only when explicitly requested.
- `program-gen` must not automatically index, report, refine, review, decide, generate follow-up candidates, compare candidates, promote, export authority, or introduce `eval_behavior.py`.

## Authoring workflow

1. Parse the natural-language request into objective, inputs, outputs, metric, constraints, examples, and optional richer fields.
2. Normalize invalid field names and record a brief note if any changed.
3. Ask only blocking clarifying questions.
4. Write the intent YAML/JSON to the user-requested path. If no path is provided, propose a path before writing, or show the YAML for the user to paste.
5. If the user explicitly asks to validate or materialize, run `program-gen` in a temp directory or a user-requested output directory.
6. Summarize generated artifacts and next decisions without ranking, promotion, or authority claims.

## `program-gen` validation command

From the DSPx repo root, with a user-approved intent path:

```bash
export DSPX_PROVIDER=stub
export MLFLOW_ENABLE=0
export DSPX_CACHE_DIR="$TD/cache"
export DSPX_CACHE_ENABLE=1

uv run --package dspx-core -q python -m dspx.cli.dspx program-gen \
  --intent "$TD/intent.yaml" \
  --outdir "$TD/program"

test -f "$TD/program/manifest.json"
test -f "$TD/program/program.py"
# If examples were provided:
test -f "$TD/program/eval_examples.py"
test -f "$TD/program/behavior_results.json"
# This surface must not exist in the current slice:
test ! -f "$TD/program/eval_behavior.py"
```

If no examples are present, `eval_examples.py` and `behavior_results.json` are not expected.

## Canonical example

Natural-language request:

> Create a DSPy program that classifies support tickets by urgency. It receives ticket_text and outputs urgency. Use only the supplied ticket text. Example: "Server is down for all users" should be high.

Intent:

```yaml
name: TicketProgram
objective: Classify support ticket urgency.
inputs:
  - ticket_text
outputs:
  - urgency
metric: exact_match
constraints:
  - use only the supplied ticket text
examples:
  - inputs:
      ticket_text: "Server is down for all users"
    outputs:
      urgency: high
promotion:
  adjudicator:
    kind: human_operator
    id: local_operator
```
