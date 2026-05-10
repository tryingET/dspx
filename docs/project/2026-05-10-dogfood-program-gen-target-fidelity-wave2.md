---
summary: "Wave 2 dogfood receipt for program-gen target-fidelity CLI preflight."
read_when:
  - "You are checking whether program-gen target-contract, fitness-suite, and generation-gate commands were dogfooded."
  - "You are continuing target-protocol fidelity gate rollout."
type: "evidence"
---

# Program-gen target-fidelity Wave 2 dogfood

Date: 2026-05-10
Task: AK-2719

## Scope

This receipt covers the Wave 2 CLI/preflight integration for the accepted target-protocol fidelity gates.
It verifies the deterministic pre-generation path only:

```text
intent.yaml
-> generation_target_contract.json
-> generation_fitness_suite.json
-> generation_gate_preflight.json
-> gated program-gen candidate materialization
```

It does not claim semantic target truth, domain approval, production activation, Oracle authority, or GEPA training readiness.

## Dogfood fixture

Intent fixture:

```text
tests/fixtures/program_gen/pdf_transition/intent.yaml
```

This is the Obsidian/PDF transition intent that previously exposed the false-success failure mode.

## Commands run

```bash
TD=$(mktemp -d /tmp/dspx-gen-wave2-dogfood.XXXXXX)
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
```

Observed latest dogfood root:

```text
/tmp/dspx-gen-wave2-dogfood.OrnEv5
```

## Observed result

```json
{
  "candidate_manifest_exists": true,
  "candidate_schema": "program-candidate-assembly-v1",
  "contract_risk_tier": "authority_adjacent",
  "contract_schema": "gen-target-contract-v1",
  "dogfood_root": "/tmp/dspx-gen-wave2-dogfood.OrnEv5",
  "generation_allowed": true,
  "preflight_status": "generation_allowed",
  "suite_schema": "gen-fitness-suite-v1"
}
```

The generated preflight states only:

```text
declared_contract_and_suite_sufficiency_only
```

and explicitly does not guarantee:

```text
semantic_truth_of_target_protocol
```

## Interpretation

Wave 2 now has a dogfooded path that can create the pre-generation sidecars and require a successful gate before `program-gen` materializes a candidate.

This is still not the full target-fitness lifecycle. Follow-up waves need post-generation traceability and fitness-result execution before adapter materialization or downstream adjudication can rely on target-fidelity evidence.
