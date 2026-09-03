---
summary: "Importing a foreign evidence package: derive closed schemas from the peer's source, keep the peer-facing record closed and push extra provenance into a sidecar, pin unchanged intent fields by hash, and label offline Oracle fixtures as authored replay."
read_when:
  - "You are writing a DSPx consumer for an artifact another repo produces and verifies (Misegraph evidence packages, future producer/consumer seams)."
  - "You are tempted to add a field to a record that another tool deserializes with deny_unknown_fields."
  - "You are running an offline foundry lineage with DSPX_ORACLE_SEMANTIC_BACKEND=fixture-replay."
type: "learning"
task_id: 5355
---

# Misegraph evidence import: closed consumer schemas

## Context

AK-5355 (Phase 2, slices D1-D3) replaced the hand-assembled Misegraph intent (two examples where
the second was the first plus `"\nValidation copy."`) with `dspx foundry import-misegraph-evidence`,
a verifier for `misegraph-evidence-package-v1` that emits `intent.json`, `inputs.json`, and a
`dspx-misegraph-evidence-binding-v1` record that Misegraph's `evidence verify-receipt` reads back.

## Discovery

1. **Derive the schema from the peer's deserializer, not from the design note.** The plan's
   binding sketch was right, but the authoritative shape is `src/evidence/receipt.rs`: every
   struct is `#[serde(deny_unknown_fields)]`, `emitted.*_path` is opened with `Path::new` and
   re-hashed, and `package.producer` must equal the manifest's producer struct exactly. Reading
   `evidence.rs`/`store.rs` also gave the canonical JSON rule (serde_json pretty, sorted keys,
   trailing newline), which Python reproduces with `json.dumps(indent=2, sort_keys=True,
   ensure_ascii=False) + "\n"`; this was verified by recomputing the fixture's `package_sha256`
   before writing any loader code.
2. **A closed peer-facing record cannot carry your extra provenance; use a sidecar.** The task
   asked for the answers-file hash "in the binding". With `deny_unknown_fields` on every level
   there is no lawful slot. The answers hash went into `misegraph-import-provenance.json`
   (`dspx-misegraph-import-provenance-v1`), and the binding's `emitted.intent_sha256` binds the
   answers transitively (they are inside the intent). Do not bend a peer's schema for
   convenience; add a versioned sibling.
3. **Pin the "unchanged" part by hash.** "Keep all other intent fields identical to the
   reference" is only testable if the reference is captured: the test pins sha256 of the
   reference intent minus `examples`, so any drift in name, options, or quality criteria fails
   loudly instead of silently breaking `dspx foundry`'s `candidate_intent == intent` check.
4. **Turning a Typer command into a group is a registration change with a behavioral edge.**
   `dspx foundry import-misegraph-evidence` required `foundry` to become a group with an
   `invoke_without_command=True` callback. Click parses group options before the subcommand,
   so the four required foundry options had to become `Optional` with an explicit guard;
   otherwise every subcommand call fails with "Missing option --intent".
5. **Read-only means fd-level read-only.** Opening the package through a directory fd with
   `O_NOFOLLOW` and `fstat` regular-file checks rejects symlink escapes even when the linked
   bytes hash correctly; the test also runs the importer against a `chmod 555` package copy.
6. **Offline Oracle evidence is authored replay.** Every offline foundry lineage adds a
   hand-copied fixture entry for the per-run request hash. That is not Oracle analysis. Label it
   `authored_fixture_replay` wherever the lineage is recorded.

## Evidence

- `tests/test_program_foundry_misegraph_evidence.py` (34 tests): tampered byte, wrong length,
  missing file, stray/hidden file, unknown top-level and nested keys, wrong schema_version,
  wrong `package_sha256`, non-canonical manifest, authority flags, symlinked artifact and
  package dir, `../` artifact name, canonical-IR schema violation, behavior-case hash mismatch
  all reject; package snapshot unchanged after load and import; byte-identical output across
  two runs; emitted intent loads through `load_program_intent`; binding key sets exact; answers
  hash in provenance and answer changes move `intent_sha256`; offline stub `program-gen` +
  `program-run` accept the bundle.
- Reference check: `docs/project/2026-09-03-foundry-misegraph-evidence-import.md`.

## Application

Any future DSPx consumer of a foreign, self-verifying artifact (governance-kernel projections,
Prompt Vault exports, other owned-lane evidence packages): read the peer's deserializer first,
recompute its content hash from the fixture before coding, keep its record closed, and put your
own facts in a sidecar with its own `schema_version`.

## TIP Candidate

Yes, as a small producer/consumer seam checklist: (1) derive from the peer deserializer,
(2) reproduce the peer hash from a real fixture first, (3) never widen a closed peer record,
(4) pin unchanged fields by hash, (5) name authored fixtures as authored.
