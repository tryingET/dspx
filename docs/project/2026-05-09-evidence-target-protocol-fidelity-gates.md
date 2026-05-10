---
summary: "Evidence for the DSPx *-gen target-protocol fidelity gap, including the Obsidian/PDF dogfood failure and current downstream-only judging surfaces."
read_when:
  - "You are reviewing the target-protocol fidelity gates RFC."
  - "You need current-state evidence for why runnable generated candidates are insufficient."
type: "evidence"
---

# Evidence: target-protocol fidelity gates current state

## Current DSPx generation evidence

The current `program-gen` path is mature in local artifact mechanics. It can materialize a structured intent into a replayable program-shaped candidate assembly with sidecars such as:

```text
manifest.json
manifest.json.meta.json
intent.json
plan.json
module_surfaces.json
execution_episode.json
behavior_results.json
oracle_evidence.json
jury.json
jury_selection.json
jury_rubric.json
promotion_review.json
promotion_adjudication_request.json
promotion_decision_template.json
```

The current `program-loop` can compose generation, replay check, candidate-local Oracle indexing/reporting, and candidate-state summary without external authority effects.

The current meta-adjudication sidecars can inspect an existing candidate and produce target/jury/adjudicator/evidence artifacts:

```text
target_profile.json
jury_requirements.json
meta_jury_selection.json
jury_verification.json
program_adjudicator_formation.json
program_adjudicator_verification.json
program_evidence_adjudication.json
adjudication_behavior_trace.json
adjudication_gepa_example.json
```

This is useful, but most of it happens after a candidate exists.

## Current limitation

The current generation path proves candidate materialization and local evidence coherence. It does not yet require a verified target-protocol contract before candidate creation.

`docs/project/program-gen-walkthrough.md` explicitly states that target-sensitive meta-adjudication is separate from current `program-gen` / `program-loop` behavior. That separation preserved authority boundaries, but it also means generation can be target-light until later review.

## Obsidian/PDF dogfood failure evidence

The Obsidian architecture requires transition before canon. The canonical PDF transition decision is:

```text
PDF -> source package -> section units -> distillation frames -> evidence cards -> merge/create -> review -> canonical notes
```

The target also has profile-specific aliases and constraints, including chapter-level reading by default, selected passage reading only when requested, and synthesis checks before note-shaped proposals.

The broader Obsidian vision reinforces the same boundary:

```text
source / idea encounter
-> source capture and source authority
-> assessment and routing
-> puzzle register / Wiki / Atlas transition
-> experiments, Efforts, or Output
-> feedback
-> refined puzzle understanding
```

It also states:

- source authority is not canonical acceptance;
- transition artifacts are reviewable non-canonical material;
- runtime evidence does not silently become authority;
- merge-before-create is a core principle.

The concrete dogfood violation was not that DSPx failed to run. It ran. The violation was that the generated candidate produced semantically wrong review artifacts. Examples included plausible-looking create proposals and draft-like Wiki text such as:

```text
create Wiki/Herstellung von Gefühlskarten.md
create Wiki/Pseudogefühle und Interpretationen in der Gewaltfreien Kommunikation.md
```

Those outputs were not faithful to the source workflow for `How to Read a Paragraph` / the Obsidian `_System` transition rules. They inflated local/procedural source material into canonical-note-shaped proposals, drifted from the original language, and skipped required reading/synthesis gates.

This makes the two real-PDF runtime episodes valuable as **failure evidence**, not promotion evidence.

## What the runtime episodes proved

Recent `program-run` dogfood proved useful infrastructure:

- existing generated candidates can run on explicit runtime inputs;
- runtime episodes can write coherent sidecars;
- local Oracle SQLite evidence can index per-runtime episodes without run-id collisions;
- publication preflight can be prepared without mutating shared Oracle/Postgres;
- source candidate manifests remain unchanged.

That evidence proves the runtime substrate. It does not prove target-protocol fitness.

## Why post-hoc adjudication is not enough

The meta-adjudication architecture remains valid. DSPx should still have two levels:

1. DSPx/meta jury + adjudicator verify the generated program's judging setup.
2. The generated program's own jury + adjudicator judge the generated program evidence within delegated scope.

But if the candidate is generated before the target protocol is explicit, both layers can become late detectors instead of early constraints. Late detection is still useful for withholding and learning, but it wastes generation/dogfood cycles and may produce confusing artifacts for operators.

## Generalization beyond Obsidian

The Obsidian review adapter currently checks review-only mutation boundaries. That is necessary, but not sufficient: a target-bound adapter should also require `fitness_passed` or write a failure-only/withheld packet so target-failed artifacts do not enter the normal review queue.

The failure is repo-wide for `*-gen` because the pattern can occur anywhere a generator targets an external protocol, domain workflow, or owner surface:

| Surface | Example false-success mode |
| --- | --- |
| `signature-gen` | Generates plausible IO fields that omit required protocol state or provenance. |
| `module-gen` | Generates a module that satisfies a local metric while skipping domain invariants. |
| `program-gen` | Generates runnable program assemblies that skip target workflow stages. |
| future `*-gen` | Generates artifacts shaped correctly but semantically unfit for their owner surface. |

## Evidence conclusion

DSPx needs a shared generation contract layer that can say, before generation:

```text
I know the target protocol.
I know the required stages and forbidden shortcuts.
I know the adversarial cases that would expose plausible nonsense.
I will block generation if that knowledge is insufficient.
```

Then, after generation, DSPx needs traceability and fitness results that prove the candidate implemented that contract or was withheld with failure evidence.
