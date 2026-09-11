---
summary: "AK-5511 real Docker feasibility results and remaining native-AK/full-gate boundary; AK-5512 separately completed."
read_when:
  - "Resuming AK-5511 full validation after the September 11 runtime probes."
type: reference
---

# Runtime proof — observed September 11, 2026

**Two feasibility payloads passed. DSPx full validation remains unsatisfied.**
This filename follows the task's admitted September 7 path prefix, not the execution date.
The tested DSPx source is unchanged at `e8a551d13637d7e61086b8d1cb5d15a62128484b`,
including the independently landed synthetic reading producer. No repository tests
were run in the two Docker payloads.

## Actual results and bounded effects

Operator intent `please resolve those` followed the explicit two-runtime-step
consent request; evidence9066/9067 records that approval. Original timed-out form
defaults were never treated as consent.

- P1: real UID/GID1000, root-owned binary UID0, read-only mounts, zero capabilities,
  seccomp/no-new-privileges, private-file permission negatives and private-loopback
  HTTP with waited child all passed. Payload exit0, no OOM/error.
- P2: real Python3.13.12, Node26.8.1, uv0.12.9, just1.58.0, Ruff0.15.4 and
  ty0.0.19 version checks passed. `.pth` files were inspected as metadata, not
  executed; no DSPx/site/plugin imports. Payload exit0, no OOM/error.
- Exactly two payload executions occurred. Three Docker objects existed over the
  full preparation history: one never-started failed setup and the two payload
  objects. All three were removed nonforce after exact owned-state verification.
- No host-provider calls, external network, GPU, full test run, image pull,
  old-workload cleanup or runner-accounting mutation occurred in these probes.

| Identity | Disposition |
|---|---|
| `7ea783a0564a41baab46b929d313860f4d922ac95d13ed3f81e2223c562303a2` | Never-started logging setup failure; exact owned nonforce removal |
| `eaae1cdaa9f7a5134357c1e58255bcd93a08c0b63a6243dfb18ac3eedcc92af0` | P1 exit0, nonforce removal |
| `0c67521e8500f33786529ea715a0a0f4b96c6db4bd700de5d8f9821946731d78` | P2 exit0, nonforce removal |

Parent recomputed payload-output SHA256 values:

- P1: `fad521cb493b4023597b5092d27d33e1bdcd5da72527ca2fc71df9f9540eba08`
- P2: `aa5b5eaa316641e04949e10f4e7eabd96cf28be53f52bc0b973707da67028c17`

P1 output/terminal/removal receipts:
`/home/tryinget/.local/state/pi-quests/tmp/dspx-probe-logging-final.gPTnT6-execution/`.
P2 output/terminal/removal receipts:
`/home/tryinget/.local/state/pi-quests/tmp/dspx-probe-p2-env.pnarc9-execution/`.
Post-run inventory:
`/home/tryinget/.local/state/pi-quests/tmp/dspx-p2-executor.FBz6Q0/`.

## Preserved preparation failures

The original exact checker rejected Docker's semantically identical Ulimits list
ordering before start. A separately reviewed correction accepted only unique-name,
exact-value permutations, never duplicate/missing/extra limits. The first attempted
start then failed before the payload because local-driver compression is incompatible
with max-file1. Explicit `compress=false` retained the same storage/output bounds.
P2's initial admission rejected equivalent Config.Env ordering; a separately reviewed
unique-name/exact-value comparison resolved that without relaxing image-env safety.

Original packets, failed receipts and inspections remain immutable in their scratch
roots. Continuations were independently reviewed and parent-admitted as evidence9079,
9095 and9102. Review dispatches include `dispatch-1789114700010` and
`dispatch-1789116872850`. Mock check counts are preparation evidence, not runtime proof.

## What this does not establish

The constructed valid ancestors and partial runtime mounts are not actual full-checkout
or full-toolchain execution proof. Stable cooperative custody remains required; the
containers do not certify that every exposed local package is secret-free, or protect
against hostile same-UID/Docker-capable actors. No production guard or source pin changed.

Full-gate source inspection exposed an additional owner boundary:

- The scope gate and some tests invoke `ak task list -s claimed -F json`.
- Current installed AK uses a writable database-open path for that operation and
  requires its canonical host-coherent exclusive runtime gate. Semantic reads are
  not physically read-only storage operations.
- Binding a copied/read-only DB, bypassing the installed admission wrapper or replaying
  captured AK output would not preserve that authority contract. None was done.
- A host control plane plus isolated pytest plane is a candidate, not an admitted
  implementation. Some tests currently exercise native AK or optional fixture paths;
  explicitly separating CI-like fixture coverage from native AK integration needs
  owner review rather than silently dropping a branch.
- Native module-corpus diagnostics can resolve an Oracle index and model-backed
  embedding implementation. Any no-live profile must deliberately use the existing
  `none` embedding configuration, fresh isolated index/outputs and reviewed fixture
  inputs; stub LM selection alone does not exclude cached model execution.

Read-only design review `dispatch-1789117566482` holds execution pending these details,
exact coverage/failure propagation, complete tool/fixture exposure and cancellation
handling. No new test executor, gate profile, AK feature, database mount or changed
pytest selection has been implemented or authorized by this document. The prior full
run `run-1788935170-066132954db9cde8` remains a failure, not retroactively repaired proof.

## Separate auth closeout

AK-5512 is complete after its actual full run
`run-1789113753-d202b469948fb89e`, independently verified by
`dispatch-1789114096131`: 627 tests, constrained distributions/Twine, isolated
hash-required wheel install/import, 13 snapshots and strict ROCS zero findings.
Canonical evidence9082/9083, closed reconciliation and ready-to-close true bind that
outcome. Auth evidence commit `3a1ff7de54dab569385e26836cb7c23ea0a801ab` and exported
completed scope `ada0fb3ced76f59df70f3e4276771c84e7cec57b` are owner-local projections.
This does not complete DSPx5511, admit5525, release a package or prove a live provider.
