---
summary: "Hands-on walkthrough for program-gen candidate assemblies, execution episodes, replay checks, Oracle-readable evidence, and authority boundaries."
read_when:
  - "You want to understand one-intent program generation end to end."
  - "You need to inspect execution_episode.json, behavior_results.json, oracle_evidence.json, manifest, receipt, and replay without invoking Oracle or AK."
  - "You are explaining the current shipped program-gen product loop to an operator."
type: "guide"
---

# Program-gen Walkthrough

This walkthrough shows the current shipped `program-gen` path from one structured intent to a runnable, evaluated, replayable program-shaped candidate assembly.

It is deliberately local-first and non-authoritative:

- uses `DSPX_PROVIDER=stub`
- sets `MLFLOW_ENABLE=0`
- writes to a temp directory
- does not call `ak`
- does not invoke Oracle indexing or mutate Oracle DBs
- does not run a model jury or promotion adjudicator
- does not rank, prune, promote, export authority, or mutate governance state

The goal is to see the current artifact contract clearly, not to claim a final product loop.

## What this proves today

The current `program-gen` loop proves:

1. A structured intent can materialize a deterministic program-shaped candidate assembly.
2. Signature, module, program, jury, promotion, and eval harness surfaces are generated as separate artifacts.
3. `execution_episode.json` is a standalone `program-execution-episode-v1` contract artifact.
4. When examples exist, `eval_examples.py` invokes the generated program locally and writes `behavior_results.json`.
5. `oracle_evidence.json` is Oracle-readable evidence derived from behavior results without invoking Oracle.
6. `manifest.json` and `manifest.json.meta.json` declare hashes and evidence paths for replay.
7. `dspx run replay --check-only` verifies the declared program evidence artifacts, including `execution_episode.json`.
8. Promotion and authority remain explicitly pending / non-authoritative.

It does **not** prove:

- rich topology inference,
- dataset splits,
- model-backed jury execution,
- promotion adjudication,
- Oracle indexing/interpretation,
- GEPA/search refinement,
- AK export or task mutation.

## 1. Prepare a temp workspace

From the repo root:

```bash
TD="$(mktemp -d)"
export TD

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
  external_authority:
    refs:
      - system: agent_kernel
        ref: AK-EXAMPLE
        role: optional_authority_export_target
YAML

export DSPX_PROVIDER=stub
export MLFLOW_ENABLE=0
export DSPX_CACHE_DIR="$TD/cache"
export DSPX_CACHE_ENABLE=1
```

These environment settings keep the walkthrough offline and temp-dir scoped.

## 2. Generate the program candidate assembly

```bash
uv run -q python -m dspx.cli.dspx program-gen \
  --intent "$TD/intent.yaml" \
  --outdir "$TD/program"
```

List the top-level generated artifacts:

```bash
find "$TD/program" -maxdepth 1 -type f -printf '%f\n' | sort
```

Expected high-signal artifacts include:

- `plan.json`
- `jury.json`
- `jury_selection.json`
- `jury_rubric.json`
- `promotion_review.json`
- `promotion_adjudication_request.json`
- `promotion_decision_template.json`
- `signature.py`
- `module.py`
- `program.py`
- `eval_smoke.py`
- `eval_jury.py`
- `eval_promotion.py`
- `examples.json`
- `eval_examples.py`
- `behavior_results.json`
- `oracle_evidence.json`
- `execution_episode.json`
- `manifest.json`
- `manifest.json.meta.json`

## 3. Verify generated Python harnesses compile

```bash
python -m py_compile \
  "$TD/program/program.py" \
  "$TD/program/eval_smoke.py" \
  "$TD/program/eval_jury.py" \
  "$TD/program/eval_promotion.py" \
  "$TD/program/eval_examples.py"
```

`program-gen` already ran the generated harnesses during materialization; this command is just a visible operator check.

## 4. Inspect the execution episode contract

```bash
python - <<'PY'
import json, os
root = os.environ["TD"] + "/program"
payload = json.load(open(f"{root}/execution_episode.json"))
print(json.dumps({
    "schema_version": payload["schema_version"],
    "status": payload["status"],
    "phase": payload["phase"],
    "materialization": payload["materialization"],
    "checks": payload["checks"],
    "behavioral_evaluation": payload["behavioral_evaluation"],
    "oracle_readability": payload["oracle_readability"],
    "non_authority": payload["non_authority"],
}, indent=2, sort_keys=True))
PY
```

How to read it:

- `materialization` means files were generated and the bundle exists.
- `checks.compile` means generated Python source compiled before write/materialization completed.
- `checks.smoke` means `eval_smoke.py` imported/built the program and checked IO shape.
- `checks.examples_binding` means `examples.json` matched declared input/output fields.
- `checks.jury_binding` means `jury.json`, `jury_selection.json`, and `jury_rubric.json` are internally consistent; no juror model was called.
- `checks.promotion_binding` means promotion review/request/template artifacts are internally consistent; no adjudicator was invoked.
- `behavioral_evaluation` points to `behavior_results.json` only when examples existed and `eval_examples.py` wrote that evidence.
- `oracle_readability` points to `oracle_evidence.json` only when behavior evidence existed; `oracle_invoked` remains `false`.
- `non_authority` keeps evidence separate from ranking, pruning, promotion, governance, Oracle, and external mutation authority.

## 5. Inspect actual behavior over examples

```bash
python - <<'PY'
import json, os
root = os.environ["TD"] + "/program"
payload = json.load(open(f"{root}/behavior_results.json"))
print(json.dumps({
    "schema_version": payload["schema_version"],
    "authority": payload["authority"],
    "summary": payload["summary"],
    "examples": payload["examples"],
}, indent=2, sort_keys=True))
PY
```

This is the behavioral evidence surface. It records what happened when the generated program was invoked over declared examples.

With the stub provider, the example may fail exact-match comparison. That is still useful evidence: it means the generated program executed and produced observable behavior that did not match the expected output.

Do not reinterpret this as promotion or ranking. It is evidence only.

## 6. Inspect Oracle-readable evidence without invoking Oracle

```bash
python - <<'PY'
import json, os
root = os.environ["TD"] + "/program"
payload = json.load(open(f"{root}/oracle_evidence.json"))
print(json.dumps({
    "schema_version": payload["schema_version"],
    "evidence_kind": payload["evidence_kind"],
    "authority": payload["authority"],
    "identity": payload["identity"],
    "behavior": payload["behavior"],
    "oracle_facets": payload["oracle_facets"],
    "non_authority": payload["non_authority"],
    "oracle_text_preview": payload["oracle_text"][:500],
}, indent=2, sort_keys=True))
PY
```

This artifact is shaped for later Oracle consumption, but the walkthrough does not run `dspx oracle ...`, does not index anything, and does not mutate an Oracle DB.

## 7. Inspect manifest and receipt declarations

```bash
python - <<'PY'
import json, os
root = os.environ["TD"] + "/program"
manifest = json.load(open(f"{root}/manifest.json"))
receipt = json.load(open(f"{root}/manifest.json.meta.json"))
print("## manifest execution episode artifact")
print(json.dumps(manifest["execution_episode_artifact"], indent=2, sort_keys=True))
print("## receipt run summary")
print(json.dumps({
    "run_kind": receipt["run_kind"],
    "hash": receipt["hash"],
    "execution_episode_path": receipt["run_summary"].get("execution_episode_path"),
    "execution_episode_hash": receipt["run_summary"].get("execution_episode_hash"),
    "behavior_results_hash": receipt["run_summary"].get("behavior_results_hash"),
    "oracle_evidence_hash": receipt["run_summary"].get("oracle_evidence_hash"),
}, indent=2, sort_keys=True))
print("## receipt bundle evidence keys")
print(sorted(manifest["receipt_bundle"]["evidence"].keys()))
PY
```

Replay is declaration-driven: the receipt points at `manifest.json`, and the manifest/receipt bundle declare which evidence artifacts and hashes must match.

## 8. Run clean replay

```bash
uv run -q python -m dspx.cli.dspx run replay \
  --from "$TD/program/manifest.json.meta.json" \
  --check-only \
  --json
```

Expected result:

- exit code `0`
- `status: ok`
- `checks.output_hash_match: true`
- `checks.program_execution_episode_hash_match: true`
- `checks.program_behavior_results_hash_match: true`
- `checks.program_oracle_evidence_hash_match: true`

Replay is local/offline. It should not require MLflow, a provider, Oracle, or AK.

## 9. Prove replay detects execution-episode drift

```bash
cp "$TD/program/execution_episode.json" "$TD/execution_episode.original.json"
python - "$TD/program/execution_episode.json" <<'PY'
import json, sys
p = sys.argv[1]
payload = json.load(open(p))
payload["status"] = "drifted"
open(p, "w").write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY

if uv run -q python -m dspx.cli.dspx run replay \
  --from "$TD/program/manifest.json.meta.json" \
  --check-only \
  --json > "$TD/execution-episode-drift.json"; then
  echo "expected replay drift failure" >&2
  exit 1
fi

python - "$TD/execution-episode-drift.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
assert payload["status"] == "failed"
assert payload["checks"]["output_hash_match"] is True
assert payload["checks"]["program_execution_episode_hash_match"] is False
assert "program_evidence_hash_mismatch" in payload["error_codes"]
print("execution episode replay drift check ok")
PY

cp "$TD/execution_episode.original.json" "$TD/program/execution_episode.json"
```

This proves `execution_episode.json` is a replay-checked evidence artifact, not just duplicated metadata.

## 10. Optional sidecar authority export plan

The local base smoke includes an optional authority adapter planning step:

```bash
uv run -q python -m dspx.cli.dspx adapters authority agent-kernel-plan \
  --manifest "$TD/program/manifest.json" \
  --external-ref AK-EXAMPLE \
  --out "$TD/program/ak-export-plan.json"
```

This writes:

- `ak-export-plan.json`
- `ak-export-plan.json.meta.json`

The plan status is `planned_not_exported`. It is not an AK mutation, not a promotion decision, and not an authority export.

## 11. Cleanup

```bash
rm -rf "$TD"
```

## Interpretation checklist

Use this checklist when reviewing a generated program assembly:

- `manifest.json` exists and has `schema_version: program-candidate-assembly-v1`.
- `execution_episode.json` exists and has `schema_version: program-execution-episode-v1`.
- `execution_episode.json` separates materialization, binding checks, behavioral evaluation, and Oracle readability.
- If examples exist, `behavioral_evaluation.result_artifact` is `behavior_results.json` and its hash matches manifest/receipt declarations.
- If examples do not exist, behavioral evaluation is `not_applicable` rather than falsely passed.
- `oracle_readability.oracle_invoked` is `false`.
- `promotion_review.json` keeps `promotion_state: not_promoted`.
- replay passes before drift and fails after declared evidence drift.
- no Oracle indexing, AK mutation, ranking, pruning, promotion, or governance mutation happened.

## Where this points next

The best next implementation wave after this walkthrough is a separate, explicitly non-authoritative Oracle consumption/indexing slice over `oracle_evidence.json` and receipt bundles.

A richer execution-episode wave should wait until there is a narrow target such as dataset splits, traces, or selected model-jury execution. Promotion/adjudication should remain separate until an explicit authority contract exists.
