---
summary: "Real credential-free GEPA 0.1.4 output materialization, fresh-process behavior, receipt, replay, and comparison disposition."
read_when:
  - "Before claiming real GEPA 0.1.4 candidate materialization or executable replay compatibility."
  - "Before considering GEPA output for trusted-local production admission."
type: "evidence"
---

# GEPA 0.1.4 real materialization disposition

AK-4805 disposition: **`accepted_real_materialization_compatibility_only`**.

One exact credential-free journey passes under CPython 3.13, DSPy/DSPy-AI 3.3.0, GEPA 0.1.4, and the repository's explicit GEPA compatibility override:

```text
real GEPA output
→ hash-bound refinement sidecar
→ new candidate assembly
→ fresh-process behavior load and evaluation
→ candidate receipt check
→ separate runtime episode
→ executable runtime replay
→ non-authoritative comparison
```

## Observed journey

The proof uses DSPx's typed `stub/echo` provider for both student and reflection calls. It does not replace GEPA with a fake and does not use a synthetic `compiled.bin` payload.

1. A minimal program candidate with one inline ticket-classification example is materialized locally.
2. `program-refine optimize-gepa` invokes real `dspy.teleprompt.gepa.GEPA` and writes genuine DSPy whole-program output including `program.pkl`, `metadata.json`, source capture, and a GEPA/DSPx manifest.
3. The refinement sidecar classifies that output as hash-bound and ready for candidate materialization.
4. The candidate materializer copies and verifies the optimizer payload, emits a new candidate identity, and writes a gated loader using `dspy.load(..., allow_pickle=True)`.
5. Loading requires `DSPX_ALLOW_UNSAFE_GEPA_PICKLE_SHA256` to equal the exact copied optimizer-manifest SHA-256. Without that artifact-specific opt-in, behavior/runtime execution fails before unpickling.
6. Behavior refresh launches `eval_behavior.py` in a fresh Python subprocess under that explicit opt-in. The copied real optimizer output loads and the example-backed behavior result passes.
7. The candidate's `program-gen` receipt passes integrity checking. It remains check-only by contract.
8. A separate `program-runtime` episode executes the candidate with explicit inputs and a bounded local replay fixture.
9. Executable replay re-runs that runtime receipt and reports `runtime_execution_reproduction=passed` while semantic reproduction remains `not_evaluated`.
10. Local comparison reaches `compared` without selecting a winner or granting promotion authority.

The source candidate, optimizer output, and materialized candidate roots match their regular-file inventories across the stages where they are inputs. Candidate and optimizer path contracts separately reject symlink payloads.

## Defects discovered and repaired

The real probes found defects that synthetic tests could not expose:

- source optimization and runtime execution could write `__pycache__` files into immutable candidate roots;
- independent import locks could race while changing process-global `sys.dont_write_bytecode`;
- optimizer imports left the temporary program module installed in `sys.modules`;
- GEPA progress output preceded `--json` output on stdout, making the command non-machine-readable;
- pickle loading had no explicit artifact-specific execution opt-in.

All candidate-owned import routes now use one shared bytecode-suppression context that serializes and exactly restores the process-global flag on success or failure. Each route retains its existing module-table lock, and optimizer imports restore the prior program module. The JSON CLI redirects optimizer progress to stderr, leaving stdout as exactly one JSON document. The generated GEPA loader enforces the exact-manifest-hash opt-in before unpickling; executable replay forwards that explicit opt-in through its otherwise scrubbed environment.

## Receipt and replay truth

Two receipt kinds remain distinct:

- candidate `manifest.json.meta.json`: `program-gen`, integrity/check-only;
- runtime `runtime_episode.json.meta.json`: `program-runtime`, executable local reproduction when its exact stub fixture and policy bindings pass.

Executable replay proves local runtime reproduction for the recorded fixture. It does not prove deterministic program regeneration, semantic equivalence, quality improvement, cross-machine portability, or release readiness.

The exact-hash opt-in is an operator acknowledgment bound to one local artifact. Hash integrity is not provenance, authenticity, sandboxing, or proof that pickle code is safe.

## Nonclaims and production boundary

This proof does not establish:

- that GEPA improved the program;
- semantic equivalence between source and GEPA candidates;
- answer quality or DSPy/GEPA version causality;
- live-provider, credentialed, network, cancellation, or checkpoint compatibility;
- safe unpickling of untrusted artifacts;
- non-pickle serialization;
- routing, promotion, publication, release, or activation authority.

The output remains pickle-backed whole-program state. It is accepted as local compatibility evidence only and remains excluded from the trusted-local Core production matrix. Any production admission requires a separately reviewed non-pickle or equivalently safe artifact contract plus owner-authorized activation evidence.
