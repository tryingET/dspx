---
summary: "Repo-owned Pi skill for authoring DSPx program-intent-v2 YAML/JSON from natural-language DSPy program requests."
read_when:
  - "You want Pi to convert a user prose request into a DSPx program intent."
  - "You need to decide whether this surface should be a prompt template, Pi skill, or Pi extension."
type: "guide"
---

# Pi DSPx Intent Assistant

## Purpose

DSPx already has a structured-intent-first `program-gen` path:

```text
structured program intent YAML/JSON
-> dspx program-gen
-> local program candidate assembly
-> eval_examples.py / behavior_results.json when examples are present
-> oracle_evidence.json readability artifact
-> optional explicit refinement loop
```

This slice adds the first reusable Pi-facing assistant surface for the step before `program-gen`:

```text
user natural-language DSPy program request
-> Pi skill-guided clarification and normalization
-> valid DSPx program-intent-v2 YAML/JSON
-> optional explicit program-gen validation/materialization
```

The shipped artifact is a project-local Pi skill:

```text
.pi/skills/dspx-program-intent-authoring/SKILL.md
```

It is repo-owned and can be loaded by Pi without mutating global `~/.pi/agent/skills`.

## Decision: prompt template vs skill vs extension

| Option | Fit for this slice | Decision |
| --- | --- | --- |
| Prompt template | Enough for a one-off manual MVP. It can expand a prompt but is weak at carrying reusable workflow, validation policy, examples, and boundaries. | Not the durable first surface. |
| Pi skill | Best durable first product surface. Pi discovers project skills from `.pi/skills/`, exposes `/skill:<name>`, and progressively loads full instructions only when relevant. A skill can carry examples, field policy, clarification policy, and non-authority boundaries without adding executable runtime. | **Chosen.** |
| Pi extension/custom tool | Useful later when the workflow stabilizes and needs typed UI, wizard questions, controlled file writes, direct CLI execution, or richer interactive validation. It adds TypeScript execution and a stronger maintenance/security boundary than needed now. | Deferred. |

A prompt template can still be added later as a convenience wrapper if users want a terse `/dspx-intent ...` expansion. A custom extension should wait until there is enough observed repetition to justify a typed wizard or file-writing tool.

## Why a project-local skill

Pi documentation supports project skills in `.pi/skills/` and `.agents/skills/` under the current working directory and ancestors. Directory skills contain a `SKILL.md` file with `name` and `description` frontmatter. Pi only keeps descriptions in the startup prompt and asks the agent to read the full skill when the task matches, so the larger DSPx-specific guidance does not permanently bloat every session.

This fits the DSPx boundary:

- Natural-language interpretation stays in Pi instructions, not DSPx core.
- DSPx core still validates and materializes only structured intent.
- No global machine-local skill installation is required.
- No custom TypeScript extension runs with full system access.
- The surface is versioned with the repo and reviewable with normal code/docs changes.

## Skill usage

From a Pi session rooted in this repo, invoke:

```text
/skill:dspx-program-intent-authoring
```

Then provide a natural-language request, for example:

```text
Create a DSPy program that classifies support tickets by urgency. It receives ticket_text and outputs urgency. Use only the supplied ticket text. Example: "Server is down for all users" should be high.
```

The skill should produce intent YAML like:

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

If the user asks Pi to write the file, write the intent to the requested path. If no path is supplied, ask or show the YAML for copy/paste. If the user asks for materialization and does not provide an output path, prefer a temp directory so generated candidate artifacts do not dirty the repo.

## Intent field support

Current `ProgramIntent` supports:

- `schema_version`
- `name`
- `objective`
- `inputs`
- `outputs`
- `input_fields`
- `output_fields`
- `task_type`
- `topology`
- `constraints`
- `examples`
- `examples_path`
- `metric`
- `runtime`
- `jury`
- `promotion`
- `options`

The model allows extra keys, but the skill should prefer the stable fields above.

For Pi authoring, the practical minimum is:

```yaml
name: IntentProgram
objective: <one sentence behavior goal>
inputs:
  - <valid_python_identifier>
outputs:
  - <valid_python_identifier>
```

The Pydantic model can default `name`, `inputs`, `outputs`, and `task_type`, but Pi should normally write them explicitly so assumptions are inspectable.

## Rich optional fields worth asking about

Ask about or include these only when useful:

- `metric` — use `exact_match` for simple classification/label examples unless the user names a metric.
- `constraints` — source restrictions, style rules, safety limits, or “use only supplied inputs”.
- `examples` — inline input/output examples when the user provides them.
- `examples_path` — external YAML/JSON examples when there are many examples.
- `input_fields` / `output_fields` — type and description details, especially `Literal[...]` label spaces.
- `jury.perspectives` — future evaluation criteria such as `correctness` or `robustness`; `program-gen` plans artifacts but does not call juror models.
- `promotion.adjudicator` — default to pending `human_operator` / `local_operator` when promotion metadata is useful but unspecified.

Do not infer `topology`, dataset splits, GEPA/search settings, external authority refs, juror pools, promotion decisions, or Oracle authority from generic prose.

## Clarification and normalization policy

The skill asks clarifying questions only when required to avoid invalid or materially misleading intent:

- unclear objective,
- missing input/output fields,
- overlapping input/output names,
- invalid field names that cannot be safely normalized,
- a request for behavior evidence without an example,
- or an attempted authority/promotion/ranking action without an explicit non-authoritative boundary.

It should not over-question when safe defaults are clear.

DSPx requires input/output names to be unique non-overlapping Python identifiers. The skill preserves valid names and normalizes invalid names to lower snake_case, explaining briefly. Examples:

| User text | Intent name |
| --- | --- |
| `ticket text` | `ticket_text` |
| `urgency-label` | `urgency_label` |
| `class` | `class_label` |
| `1st answer` | `answer_1` or `first_answer` |

## Optional YAML/JSON healing

If Pi produces malformed structured text, `softwareco/contrib/sanitize` can be used as an optional Pi-side syntax repair helper before validation:

```bash
sanitize lint "$TD/intent.yaml" || sanitize fix "$TD/intent.yaml" > "$TD/intent.healed.yaml"
```

This is intentionally not a DSPx core dependency for this slice. Use it only for syntax-level structured-text repair such as indentation, missing spaces after colons, list dash spacing, trailing commas, fenced JSON, or prose-wrapped JSON. It must not infer intent fields, normalize identifiers, invent examples, decide promotion, attach authority refs, or replace `ProgramIntent` / `program-gen` validation. After a fix, Pi should inspect or summarize the change and then run `program-gen` against the original or healed file explicitly selected by the operator.

## Non-authority boundaries

This assistant surface must not widen DSPx authority. In particular:

- Do not run AK or mutate AK tasks.
- Do not edit `governance/work-items.json` or task-scope snapshots.
- Do not invent AK refs, datasets, Oracle authority, approvals, promotion decisions, rankings, winners, or external authority exports.
- Do not generate source code directly; the output is structured intent YAML/JSON.
- Do not make `program-gen` automatically index, report, refine, review, decide, generate follow-up candidates, compare candidates, promote, export authority, or introduce `eval_behavior.py`.
- Do not run Oracle/refinement/promotion/candidate comparison surfaces unless the user explicitly asks after intent generation.
- Keep generated candidate artifacts in a temp directory unless the user explicitly asks for a repo path.

## Validation recipe

Use this minimal temp-dir validation when checking a skill-authored sample intent:

```bash
TD="$(mktemp -d)"
cat > "$TD/intent.yaml" <<'YAML'
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
YAML

export DSPX_PROVIDER=stub
export MLFLOW_ENABLE=0
export DSPX_CACHE_DIR="$TD/cache"
export DSPX_CACHE_ENABLE=1

uv run --package dspx-core -q python -m dspx.cli.dspx program-gen \
  --intent "$TD/intent.yaml" \
  --outdir "$TD/program"

test -f "$TD/program/manifest.json"
test -f "$TD/program/program.py"
test -f "$TD/program/eval_examples.py"
test -f "$TD/program/behavior_results.json"
test ! -f "$TD/program/eval_behavior.py"
```

This proves the authored intent shape can pass the structured DSPx path without adding a natural-language interpreter to DSPx core and without running downstream authority/refinement automation.

## Later extension criteria

A custom Pi extension or tool becomes appropriate only after the workflow stabilizes enough to justify executable UX. Clear triggers would be:

- repeated need for a typed multi-question wizard,
- automatic field-name normalization previews,
- controlled file-writing into approved intent paths,
- built-in `program-gen` temp-dir execution with artifact summary,
- or integration with Pi UI dialogs for structured example entry.

Even then, the extension should remain a Pi-side authoring/materialization helper. It should not promote candidates, select winners, mutate AK/governance, or make Oracle authoritative.
