---
summary: "Measured DSPx service hotspots and the behavior-preserving runtime-object decomposition sequence."
read_when:
  - "You are splitting an oversized DSPx service."
  - "You need to choose a runtime-object boundary instead of moving arbitrary helpers."
---

# Runtime-object decomposition sequence

## Purpose

DSPx service decomposition follows the runtime ontology in
`docs/project/program-synthesis-boundary.md`. A split is justified when it gives one
runtime object a coherent contract boundary while the existing service remains the
orchestrating facade. File size alone is a signal, not a design boundary.

## Hotspot map (2026-07-10 baseline)

Measured with `wc -l packages/dspx-core/src/dspx/services/*.py` before this slice:

| Service | LOC | Coupled responsibilities | Runtime-object seam |
|---|---:|---|---|
| `module_synthesis_evidence.py` | 5,567 | evidence retrieval, prior/history interpretation, policy diagnostics | behavioral evidence / phenotype inputs; requires a separate design pass because several evidence schemas coexist |
| `program_meta_adjudication.py` | 3,708 | evidence loading, jury/meta-adjudication validation, plan materialization | adjudication episode and local decision artifacts; authority checks make this high risk |
| `program_service.py` | 3,266 | plan assembly, candidate materialization, harness execution, execution-episode contract, Oracle readability, receipt/manifest assembly | candidate assembly facade plus execution episode and receipt bundle |
| `program_candidate_state.py` | 2,351 | sidecar discovery/validation and truth-state projection | promotion state projection; preserve its non-authoritative status boundary |
| `run_replay_service.py` | 2,092 | receipt validation, replay execution, comparison/explanation support | receipt bundle replay; public replay behavior needs characterization first |
| `program_activation_packet.py` | 1,935 | activation evidence validation and packet assembly | promotion-state handoff; governance boundary makes mechanical splitting unsafe |
| `program_runtime_episode.py` | 1,876 | post-materialization guided runtime execution | execution episode execution; distinct from the deterministic materialization episode contract |

The selected first extraction is the deterministic **program execution episode
contract** from `program_service.py`. It was a contiguous contract builder with a
stable schema and explicit inputs. It was not selected merely because it was easy
to move: it corresponds directly to the first-class Execution Episode object,
returns one artifact payload, performs no writes, and carries the non-authority
membrane consumed by manifests and receipts.

## Landed boundary

- `program_service.py` remains the program-shaped Candidate Assembly facade. It
  materializes surfaces, runs harnesses, builds evidence inputs, writes artifacts,
  and assembles manifest/receipt outputs.
- `program_execution_episode.py` owns construction of
  `program-execution-episode-v1` from already-observed harness and evidence inputs.
- The builder does not run generated code, read or write artifacts, invoke Oracle,
  rank candidates, select winners, promote, or mutate external authority.
- The facade passes its existing `evaluation_sources` and
  `behavior_evidence_summary` into the builder. This avoids recomputing truth in a
  second owner and preserves the emitted contract byte-for-byte after sorted JSON
  serialization.
- `program_runtime_episode.py` is intentionally unchanged. It executes a later,
  operator-requested runtime episode; combining that behavior with deterministic
  materialization evidence would blur lifecycle phases.

## Decomposition sequence

1. **Execution Episode contract (landed here).** Characterize the emitted contract,
   extract its pure builder, retain orchestration and writes in `program_service`,
   and verify existing materialization/replay/jury suites.
2. **Receipt Bundle assembly.** Map the manifest/run-receipt construction and its
   hash/lineage invariants. Extract only after golden tests prove surface ordering,
   hashes, cache behavior, and replay identity. Keep filesystem commit/cleanup in
   the candidate-assembly facade until atomicity has an explicit owner.
3. **Candidate Assembly materializer.** Introduce a cohesive materialization object
   around surface rendering, compile checks, and artifact inventory. Do not split
   rendering helpers by convenience; move the transaction only when its rollback,
   cache, and outdir semantics can remain one unit.
4. **Behavioral evidence / Oracle readability.** Separate evidence interpretation
   only after its schema relationship to `module_synthesis_evidence.py` is mapped.
   Preserve Oracle's advisory role and do not turn readability into ranking or a
   promotion gate.
5. **Promotion-state and adjudication hotspots.** Address
   `program_candidate_state.py`, `program_meta_adjudication.py`, and
   `program_activation_packet.py` in owner-specific slices with explicit authority
   tests. These are not safe follow-on mechanical extractions.

## Extraction gate

Each later slice must show all of the following before code moves:

1. one named runtime object and lifecycle phase;
2. a contiguous input/output contract with no hidden authority expansion;
3. characterization tests for hashes, ordering, status, and failure cleanup;
4. one owner for filesystem effects and rollback;
5. no compatibility wrapper that silently creates two implementations of truth;
6. a measurable reduction in the source hotspot without creating a new oversized
   miscellaneous module.

If these conditions are absent, leave the code in place and improve the map rather
than shuffle helpers.
