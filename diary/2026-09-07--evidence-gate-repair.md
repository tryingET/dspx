---
summary: "AK-5511 bounded tests-only gate repair: offline focused evidence, awaiting independent implementation review."
read_when:
  - "Reviewing the Oracle live-test and BERTScore test opt-in repair."
---

# AK-5511 gate repair — observed 2026-09-09

Baseline HEAD `92443fbee2ceb72c8844482215342ac76ed3211a`. Read target AGENTS,
local engineering/policy, developer workflow, AK task/scope and direction status.
AK-5511 claim and scope v5 matched dispatch; only the parent scope snapshot was
initially dirty. Controller reports design acceptance `dispatch-1788933214927`;
the plan was appended to `docs/project/2026-09-07-evidence-integrity-design.md`
before code edits. No implementation-review acceptance is claimed.

## Changes / coverage

- Oracle live entrypoint now requires both exact opt-ins, rejects enabled bypass,
  checks provider and read/mutate capabilities before HTTP, and never grants or
  clears caller policy. Fixed endpoint/model and credential-free behavior remain.
  Offline `_fake_backend` policy helper is unchanged.
- New `tests/test_program_oracle_live_gate.py`: **44 passing cases**, calling the
  actual live-test function with counted fake HTTP/preflight/resolve/analyze seams.
  Missing/invalid/partial flags, policy-enabled bypass variants, provider/capability
  allowlist exclusion, explicit denial and deny-over-allow all leave four counters
  zero. Allowed paths verify check ordering and preserve policy: unavailable HTTP
  status/exception yields `(1,0,0,0)` and skip; fake success yields `(1,1,1,1)`.
  Counting observes swallowed HTTP exceptions, not merely a sentinel exception.
- `tests/test_adapters_eval_bertscore.py`: **25 passing offline cases**, one gated
  real smoke skip. Optional import moved behind exact
  `DSPX_BERTSCORE_REAL_MODEL=1` inside the smoke body. Fake module/import counters
  cover closed opt-in variants, module-body loading with opt-in off/on, and fake
  enabled smoke; adapter coverage checks candidates-before-references, list
  conversion, default/explicit options, F1 tensor/iterable means, empty/mismatch
  short-circuits and macro delegation. No optional bert-score or torch dependency
  is needed for these fake-module proofs.
- Existing Oracle backend file: **32 passed, one gated live smoke skipped**.
  No production source, shared conftest, Justfile, pin or historical evidence edit.

## Exact validation (from DSPx root)

Existing installed tools only; no sync, dependency resolution or downloads.
`unshare -Urn true` succeeded. Observed host namespace `net:[4026531833]` and
probe namespace `net:[4026535580]` differed. Test/typecheck commands each create
an offline network namespace, including isolated loopback.

```bash
unshare -Urn env -u DSPX_ORACLE_LIVE_VLLM -u DSPX_BERTSCORE_REAL_MODEL \
  UV_OFFLINE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -ra -p no:cacheprovider \
  tests/test_program_oracle_semantic_backend.py \
  tests/test_program_oracle_live_gate.py tests/test_adapters_eval_bertscore.py
# 101 passed, 2 skipped in 1.66s; exit 0.
# Skips: requires exact DSPX_ORACLE_LIVE_VLLM=1;
#        requires exact DSPX_BERTSCORE_REAL_MODEL=1.

unshare -Urn env UV_OFFLINE=1 .venv/bin/ty check \
  tests/test_program_oracle_semantic_backend.py \
  tests/test_program_oracle_live_gate.py tests/test_adapters_eval_bertscore.py
# All checks passed; exit 0.

.venv/bin/ruff format --check tests/test_program_oracle_semantic_backend.py \
  tests/test_program_oracle_live_gate.py tests/test_adapters_eval_bertscore.py
# 3 files already formatted; exit 0.
.venv/bin/ruff check tests/test_program_oracle_semantic_backend.py \
  tests/test_program_oracle_live_gate.py tests/test_adapters_eval_bertscore.py
# All checks passed; exit 0.
git diff --check
# No whitespace errors; exit 0.
```

Final test-file SHA-256:

| File under `tests/` | SHA-256 |
|---|---|
| `test_program_oracle_semantic_backend.py` | `5ad34a8c4b35be81a8025e2947b643350cb12a924573e614e1c8c3dc92e7c19b` |
| `test_program_oracle_live_gate.py` | `8201456a74e98bd166bd06546d54dae8b2df0a68459ea9d9804b1a8befeda456` |
| `test_adapters_eval_bertscore.py` | `00c18d475dd76f9bb0e768589c3e0f8ca2629cb0c44708f0d5a2d13794885e97` |

## Limits / handoff

This is focused test-harness and existing offline backend evidence, not actual
provider/model availability, semantic model quality, model-download behavior,
full-suite conformance, release readiness or lifecycle authorization. No blanket
marker/subset gate was added; these are three explicitly selected complete files.
No live call, model download, SCI/ontology generation, original evidence replay,
AK mutation, commit, push, source-pin change or full-gate run was performed.
Scratch honored existing TMPDIR; no multi-GiB job or unrelated cleanup was used.
Immutable upstream engineering guidance was not retrieved (remote effects barred).
Next: independent implementation review of this exact diff; only after acceptance,
controller-authorized full-gate execution under the scratch/heavy-job contract.

Final bounded checks:

```bash
unshare -Urn env UV_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
  just task-scope-check task_id=5511 mode=working-tree
# ok: AK-5511 working-tree scope; all six changed paths (including parent's
# untouched snapshot and this diary) admitted; exit 0.
```

Read-only comparison against HEAD also confirmed `_fake_backend` function bytes
unchanged and the entire historical design document retained as an exact prefix.


## Final bounded review disposition — 2026-09-09

Controller dispatch supplies independent **SHIP** `dispatch1788934614753`: exact
three reviewed hashes above, **101 passed / 2 skipped**, plus a separately labelled
**38-case premature-probe negative mutant**. The review/mutant result is supplied
review evidence, not a fresh mutant execution here. Fresh finalization independently
reran the three complete files: **101 passed / 2 skipped**, exit0, 1.27s, unchanged
source hashes, sanitized environment and isolated network namespace. No model or
provider smoke was enabled. This supersedes the earlier pending-review statement
only for the bounded test repair; it does not erase the later full-gate failure.

See `diary/2026-09-07--evidence-finalization.md` and its compact JSON receipt for
current checks, scope v6, commit inventory and remaining gates. Normal main commit
is now controller-authorized; full-gate/lifecycle/external-effect authority is not.
