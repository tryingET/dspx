---
summary: "Repository-level DSPx operating contract for agents."
read_when:
  - "You are starting work in the DSPx repo."
  - "You need repo-specific guardrails, owner boundaries, read order, or validation commands."
type: "reference"
---

# AGENTS.md — dspx

## 1. True intent

DSPx provides behavioral intelligence for DSPy programs through local generation, replay, evaluation, Oracle analysis, and receipt-backed evidence.

DSPx artifacts are empirical/runtime evidence. They do not approve production activation, mutate external authority, or replace AK/governance decisions unless an explicit owner surface says so.

## 2. Non-negotiable axioms

1. **Source-owner axiom** — do not absorb another owner by convenience. Prompt/procedure truth lives in Prompt Vault; work/task/direction/decision/evidence truth lives in AK; semantics live in ROCS; empirical behavior analysis lives in Oracle/DSPx.
2. **Projection axiom** — checked-in direction docs and generated governance files are projections/orientation unless the surface explicitly declares authority.
3. **Evidence axiom** — pass/fail and promotion-adjacent claims need machine-checkable evidence or a clear advisory/non-authoritative label.
4. **Locality axiom** — DSPx generation, replay, local eval, Oracle evidence, and local jury/adjudication sidecars stay local until a separate owner-authorized export/apply surface exists.
5. **No-secrets axiom** — never commit secrets, credentials, model keys, local DBs, or non-reproducible machine artifacts.

## 3. Authority and owner boundaries

- Active direction/task/decision/evidence truth: AK runtime (`ak ...`) for this registered repo.
- Prompt and reusable cognitive/procedure templates: Prompt Vault. Do **not** read machine-local prompt-file paths as canonical prompt sources.
- Semantic ontology: ROCS / ontology owner surfaces.
- Operator workbench behavior: Pi runtime / pi-extensions.
- Behavioral analysis: DSPx Oracle and receipt/replay artifacts.
- Knowledge capture: repo-local `diary/` for session notes and `docs/learnings/` for crystallized patterns.

Generated DSPy program promotion boundary:

- DSPx owns generation, replay, local eval, Oracle evidence, and local jury/adjudication sidecars for generated DSPy programs.
- DSPx artifacts do not by themselves approve production activation.
- For generated-program production activation, use the governance-kernel boundary: `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`.
- The owning domain or delegated governing body is the judge; AK/current accepted runtime authority records canonical decision/evidence/transition truth where landed.

## 4. Reasoning breadth vs mutation scope

Use broad adversarial reasoning with bounded mutation.

- Broad reasoning is expected for boundary contracts, generated-program promotion, Oracle/AK/governance seams, reusable prompts/procedures, and operator workflow changes.
- Bounded mutation means changing only the owner-authorized files/surfaces needed for the current task.
- If broad reasoning identifies Prompt Vault, ROCS, AK, governance, Pi/runtime, or template changes, hand off or use that owner surface explicitly; do not patch DSPx docs/code as a substitute for owner truth.

## 5. Cognitive prompts and review stack

Prompt Vault is canonical for reusable cognitive prompts and procedures.

When an operator asks to apply a named prompt/review stack such as `inversion`, `telescopic`, `nexus`, `audit`, `blast-radius`, `escape-hatch`, `knowledge-crystallization`, or `deep-review`:

1. discover/confirm the template with `vault_query` unless the exact vault name is already known;
2. run `vault_dispatch_check` before applying/running it;
3. retrieve/use the template text only when dispatch posture permits text-only use;
4. use the required orchestrator/workflow binding when the dispatch check says text-only interpretation is not lawful.

Reasoning frameworks do not authorize ungated mutation. They widen analysis; they do not move owner authority.

## 6. Read order

1. `docs/system4d/compass.md` — direction projection.
2. `docs/ARCHITECTURE.md` — system design and boundary map.
3. `docs/project/vision.md` — long-horizon direction.
4. `docs/project/product-posture.md` — shipped-vs-target product posture.
5. `docs/project/developer_workflow.md` — canonical local workflow and validation contract.
6. `docs/project/program-gen-broadening-strategic-frame.md` — program-gen broadening frame when relevant.
7. `docs/learnings/` — crystallized repo patterns.
8. `diary/` — repo-local session notes when historical context is needed.

Active direction and execution truth live in AK direction/task/decision runtime where landed. Checked-in direction docs are projections/orientation, not parallel authority.

## 7. Development stack

- Python 3.13 + uv + just.
- Quality gates: ruff + ty + pytest.
- Use the repo-local `Justfile` as the primary command surface.
- Keep `docs/_core/**` immutable unless the task explicitly authorizes core-reference maintenance.
- Follow the workspace/company main-first workflow unless the operator explicitly asks for a review gate.
- Run `just hooks-install` after cloning.

## 8. Commands

```bash
just install          # setup
just hooks-install    # install pre-commit + pre-push hooks
just help             # list supported recipes
just check            # repo-declared readiness gate
just verify-full      # full workflow + governance + repo validation
just fmt lint typecheck test
just dspx ...         # run DSPx CLI
just forge ...        # run Forge app CLI
```

Useful shared tooling:

```bash
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --task "<task>" --top 8
uv tool run --from ~/ai-society/core/engineering-core engineering-core show py --prefer-repo
```

Oracle quick reference:

```bash
dspx oracle index --from-receipts
dspx oracle search "<query>"
dspx oracle territory
dspx oracle contract verify
dspx oracle attractors --health
```

## 9. Direction workflow

- Use `ak direction check` / `ak direction export` from the repo root when current posture needs verification.
- Treat `ak direction check` as the authority-reconciliation gate between repo direction projections and AK's structured direction substrate.
- Do not run `ak direction import` as a routine post-edit or posture-check habit. Use import only for intentional migration/backfill from direction docs into AK.
- For exact AK task work, inspect the task and scope first, implement within scope, run the smallest truthful validation, and avoid broad queue curation unless the task itself requires it.

## 10. Local artifact boundaries

- Receipts/manifests are canonical for replay; MLflow is an optional observability sink.
- Local generated sidecars are advisory/local unless a separate contract grants external authority.
- Do not commit caches, local DBs, secrets, or generated artifacts that are reproducible/local-only.
- Keep repo-local learnings in `docs/learnings/`; do not use parent AGENTS files or workspace docs as a diary substitute.
