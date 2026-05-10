---
summary: "Wave 3 dogfood receipt for program-gen traceability and target-fitness results."
read_when:
  - "You are checking whether post-generation target-fidelity sidecars were dogfooded."
  - "You are continuing Obsidian/PDF target-fidelity hardening."
type: "evidence"
---

# Program-gen target-fidelity Wave 3 dogfood

Date: 2026-05-10
Task: AK-2721

## Scope

This receipt covers the Wave 3 post-generation sidecars:

```text
generation_traceability.json
generation_fitness_results.json
```

It extends the Wave 2 preflight path:

```text
intent.yaml
-> generation_target_contract.json
-> generation_fitness_suite.json
-> generation_gate_preflight.json
-> gated program-gen candidate
-> generation_traceability.json
-> generation_fitness_results.json
```

The result remains non-authoritative. `fitness_passed` renders only as:

```text
eligible_for_downstream_evidence_review
```

It does not mean approved, promoted, activated, ready for domain decision, or accepted by Obsidian.

## Dogfood fixture

```text
tests/fixtures/program_gen/pdf_transition/intent.yaml
```

## Commands run

```bash
TD=$(mktemp -d /tmp/dspx-gen-wave3-dogfood.XXXXXX)
INTENT=tests/fixtures/program_gen/pdf_transition/intent.yaml

uv run dspx program-gen target-contract \
  --intent "$INTENT" \
  --out "$TD/generation_target_contract.json" \
  --json > "$TD/target_contract.stdout.json"

uv run dspx program-gen fitness-suite \
  --target-contract "$TD/generation_target_contract.json" \
  --out "$TD/generation_fitness_suite.json" \
  --json > "$TD/fitness_suite.stdout.json"

uv run dspx program-gen verify-generation-gate \
  --intent "$INTENT" \
  --target-contract "$TD/generation_target_contract.json" \
  --fitness-suite "$TD/generation_fitness_suite.json" \
  --out "$TD/generation_gate_preflight.json" \
  --json > "$TD/preflight.stdout.json"

uv run dspx program-gen \
  --intent "$INTENT" \
  --outdir "$TD/program" \
  --generation-gate-preflight "$TD/generation_gate_preflight.json" \
  --print-manifest > "$TD/program_manifest.stdout.json"

uv run dspx program-gen traceability \
  --manifest "$TD/program/manifest.json" \
  --target-contract "$TD/generation_target_contract.json" \
  --out "$TD/generation_traceability.json" \
  --json > "$TD/traceability.stdout.json"

uv run dspx program-gen fitness-results \
  --manifest "$TD/program/manifest.json" \
  --target-contract "$TD/generation_target_contract.json" \
  --fitness-suite "$TD/generation_fitness_suite.json" \
  --traceability "$TD/generation_traceability.json" \
  --out "$TD/generation_fitness_results.json" \
  --json > "$TD/fitness_results.stdout.json"
```

Observed latest dogfood root:

```text
/tmp/dspx-gen-wave3-dogfood.M1k8w8
```

## Observed result

```json
{
  "candidate_schema": "program-candidate-assembly-v1",
  "contract_risk_tier": "authority_adjacent",
  "dogfood_root": "/tmp/dspx-gen-wave3-dogfood.M1k8w8",
  "fitness_rendered_state": "eligible_for_downstream_evidence_review",
  "fitness_schema": "gen-fitness-results-v1",
  "fitness_status": "fitness_passed",
  "preflight_status": "generation_allowed",
  "traceability_requirement_count": 7,
  "traceability_schema": "gen-traceability-v1"
}
```

## Interpretation

Wave 3 creates post-generation target-fidelity readback sidecars and keeps command language safe.
The current fitness result is a mechanical declared-suite result, not a domain semantic acceptance result.

The older Obsidian/PDF DSPy review artifacts should not be treated as valid review-ready output. They should be retained until Wave 5 captures them as failure fixtures or quarantine evidence, then removed from normal active-review surfaces by an Obsidian-scoped cleanup task. They should not be deleted before the failure evidence is captured.
