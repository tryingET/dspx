---
summary: "Current-vs-target evidence for Decision 105's bounded DSPx execution-episode authority."
read_when:
  - "Checking what DSPx currently enforces or merely observes for Decision 105."
type: "evidence"
status: "proposed"
decision_id: 105
source_commit: "1976d77f8ce11ccf96f64259b6cc87ad02649dd2"
---
# Evidence note — DSPx execution-episode custody

## Frozen source observations

The source observations below are bound to DSPx commit `1976d77f8ce11ccf96f64259b6cc87ad02649dd2`. They describe current code; they do not authorize use.

| Surface | Observed current behavior | What it does not prove |
|---|---|---|
| `program_execution_episode.py` | Builds a non-authoritative materialization/evidence projection from already observed harness inputs. | That this builder executes a program, mediates protected data, or owns a runtime lifecycle. |
| `program_runtime_episode.py::_verify_candidate_integrity` | Requires a valid candidate receipt and current hashes for declared candidate surfaces before runtime. | Semantic-owner approval, provider identity, or safe external effects. |
| `program_runtime_episode.py::_verify_generated_program_surfaces_safety` | Applies a static allow/deny membrane to generated Python imports, nodes, and calls. | OS sandboxing, complete Python effect isolation, network isolation, or safety of provider internals. |
| `program_runtime_episode.py::_write_private_json_exclusive` | Writes `runtime_inputs.json` and an optional replay fixture with mode `0600`, no-follow/exclusive creation, fsync, and no-replace publication. | General dataset custody, encryption, leases, revocation, reader identity, or cleanup of caller-owned inputs. |
| `program_runtime_episode.py::run_program_runtime_episode` | Verifies candidate/input material, derives an episode ID, creates a disjoint local output root, invokes one generated program call in the current DSPx process, records returned outputs or a caught exception, writes local evidence, then writes a run receipt. | Exactly-once provider transport, provider-internal retries, executed model identity, subprocess supervision, external process cleanup, or effect-free failure. |
| runtime evidence writers | Write behavior results, traces, a runtime manifest, Oracle-readable evidence, an episode file, and finally a receipt; optional candidate-local Oracle indexing and preflight sidecars are separate downstream effects. | One atomic multi-file evidence commit in current code or shared Oracle/publication authority. |
| `program_execution_replay.py` | Supports a bounded local stub-backed replay with receipt/hash checks, explicit subprocess and temporary-filesystem effects, no-replace replay evidence publication, and declared non-authority. | General semantic reproduction, arbitrary provider replay, network isolation, or permission to retry an ambiguous original attempt. |
| `run_receipts.py` | Binds run identity, execution context, replay policy, outputs, and provenance into versioned receipts. | That a receipt caused the action, that every external effect is captured, or that signing would enforce behavior. |

## Current capability boundary

DSPx currently mediates or directly controls only a narrow local surface:

- pre-execution validation of local candidate and input artifacts;
- allocation of its local episode output directory and exclusive private input snapshot;
- invocation of the generated-program callable through its configured runtime path;
- observation of values/exceptions returned to that path;
- local evidence, receipt, replay-output, and candidate-local Oracle writes that DSPx performs itself.

DSPx currently observes but does not independently enforce or prove:

- provider transport-call count, provider-internal retry behavior, or executed model identity;
- whether provider-owned subprocess/network effects occurred exactly once;
- OS-level containment or cleanup outside DSPx-owned local files;
- semantic correctness or deterministic verdict truth.

DSPx does not currently own:

- a protected semantic-evaluation dataset store;
- leases, opaque read handles, revocation, or access-history authority;
- a PID-reuse-safe process supervisor or general child-process custody layer;
- semantic policy meaning, ROCS evaluation, Decision 53 publication/currentness, or AK governance authority.

## Architectural inference

Decision 105 should define **execution-episode custody**, not a generic custody broker. Custody means DSPx owns the integrity and terminal disposition of its local attempt/evidence record. It does not mean DSPx owns caller data, provider infrastructure, semantic truth, or publication.

The target lifecycle needs durable attempt-start, observed-outcome, evidence-seal, and terminal markers that current code does not yet implement as one canonical machine. A crash after the start marker and before a sealed outcome is `indeterminate`; the same attempt identity cannot be retried. This is a proposed correction, not shipped behavior.

## Nonclaims

No current code, test, receipt, source commit, or this note proves Decision 105 constructible or accepted. No provider/model, network, real policy/data, publication, consumer, Pi, or automatic-preflight effect is authorized.
