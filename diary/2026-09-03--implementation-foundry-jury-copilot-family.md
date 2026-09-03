---
summary: "AK-5345: second task-local foundry jury provider family over dspy-lm-auth GithubCopilotBackend (gemini-3.7-flash default), Codex family unchanged."
read_when:
  - "Adding or re-pinning a task-local dspy-lm-auth provider family for foundry comparison juries."
  - "Checking why Copilot call records carry observed_model while Codex records do not."
type: "diary"
---

# Implementation: foundry jury GitHub Copilot family

## What changed

- New `program_foundry_gepa_comparison_jury_provider_family.py`: frozen `FoundryJuryProviderFamily`
  with `CODEX_FAMILY` and `COPILOT_FAMILY`, `endpoint_origin_sha256()`, `family_for_provider()`.
  The custody module keeps every Codex constant as an alias of `CODEX_FAMILY`.
- Custody: `canonical_ak_task_revalidator(..., family=)` binds the family's execution task title;
  `FoundryJuryCallCustodian(..., family=)` binds the family's endpoint origin; call records are
  built by `call_record()`, which adds `observed_model` only for non-strict families.
- Owner: `VerifiedFoundryJuryOwner.family`, `verify_loaded_foundry_jury_owner(root, family)`;
  one marked OWNER PIN BLOCK; `inspect.getsourcefile` failures now read as backend drift.
- Provider: family threaded through adapter, configured provider, and
  `configure_foundry_jury_provider(model=None, reasoning_effort=None, family=)`; metadata
  projection/validation moved to `..._provider_metadata.py` to stay under the 500-line budget.
- Runtime: `TASK_LOCAL_PROVIDER_NAMES`, per-family execution-request keys (`model` vs
  `codex_model`, no `reasoning_effort` for Copilot), `revalidate_execution_request()` moved out of
  `_jury.py` (679 -> 629 lines; still above budget but reduced).
- CLI: `--model` (family default), `--codex-model` Codex alias, `--reasoning-effort` default per family.
- Tests: `tests/test_program_foundry_gepa_comparison_jury_copilot.py` (family literals, endpoint
  derivation pins, model/effort rules, revalidator titles, custodian and metadata parametrized over
  both families, observed-model rule, request normalization, CLI forwarding, attempt/receipt run
  through the Copilot family, adapter+custody end-to-end with a fake Copilot backend, loaded-owner
  rules, repin helper). `tests/foundry_jury_owner_repin.py` prints the pin block.

## Decisions

- Endpoint origin derivation recovered from `program_oracle_semantic_gate4_v11._validate_endpoint`
  (domain `dspx-oracle-semantic-v11-endpoint-origin-v1`, `{scheme, hostname}` canonical JSON).
- Observed model: Codex strict; Copilot recorded-not-enforced because Gemini may answer with a
  versioned id. Codex evidence shape is unchanged so retained AK-5322/5327 evidence still validates.
- The receipt contract fixes the eight `module_sha256` names, so new fork modules are pinned in
  `_EXTRA_OWNER_FILES` rather than `_OWNER_MODULES`.

## Pins

Pinned against fork commit `944f081de5abf44960995263355b42d41de38aba` (tree `26468980...`),
verified equal to `tests/foundry_jury_owner_repin.py --print-pins` output. The fork has since
added docs-only commit `944f081` (identical source hashes); re-pin commit/tree with the helper if
that commit should become the bound owner.

## Out of scope / follow-up

- `program_model_jury_provider_runtime.py:121` restricts the runtime binding to the Codex name;
  it must accept both family names before a live Copilot jury can run through
  `build_comparison_model_jury_result`. Not edited (outside AK-5345 file scope).
- No live provider call, no AK mutation, no commit.
