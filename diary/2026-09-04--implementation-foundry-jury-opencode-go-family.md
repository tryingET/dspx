---
summary: "AK-5368: fifth task-local foundry jury family `foundry-dspy-lm-auth-opencode-go` over the fork's OpencodeGoBackend (Pi api_key credential), preflight probe api-key path, owner repinned to dspy-lm-auth 80c970c9; 384 jury tests green, nothing live."
read_when:
  - "Adding another task-local provider family or a new owner auth mode to the foundry jury."
  - "Checking why the preflight probe carries `auth_mode` and a `_chat_credential.py` hash."
  - "Preparing the first live OpenCode Go jury."
type: "diary"
---

# Implementation: OpenCode Go foundry jury family (AK-5368)

## What changed

- `services/program_foundry_gepa_comparison_jury_provider_family.py`: `OPENCODE_GO_FAMILY`
  (`foundry-dspy-lm-auth-opencode-go`, auth provider `opencode-go`, model rule
  `^[a-z0-9][a-z0-9.-]{0,63}$`, default `kimi-k2.7-code`, no reasoning effort, 180 s timeout,
  routes `dspy-lm-auth:opencode-go:{model}` / `openai:{model}:chat`, backend
  `dspy_lm_auth.opencode_go_backend.OpencodeGoBackend`, generic chat contract types,
  `catalog_path` `/zen/go/v1/models`, non-strict observed model). New constants
  `OPENCODE_GO_ENDPOINT_ORIGIN = "https://opencode.ai"` (origin only; the owner's api_base carries
  `/zen/go/v1`, so `catalog_url` composes to `https://opencode.ai/zen/go/v1/models`) and the
  pinned origin hash `49a9f205011074eef3fbd38c759a8389feeab6133037dad880ac96a5063d3513`. New
  family field `auth_mode` (`AUTH_MODE_PI_OAUTH` default, `AUTH_MODE_PI_API_KEY`, `AUTH_MODE_NONE`
  for local vLLM). Registered in `FAMILIES`, so `TASK_LOCAL_PROVIDER_NAMES`, the runtime binding,
  the process slot, and the loaded-owner checks pick it up without further edits.
- `services/program_foundry_gepa_comparison_jury_owner.py`: pin block regenerated on the fork's
  clean `80c970c9` (tree `22fc8646`; lock hash unchanged); `opencode_go_backend.py` added to
  `_EXTRA_OWNER_FILES`; `tests/foundry_jury_owner_repin.py` required list extended.
- `services/program_foundry_gepa_comparison_jury_preflight_probe.py`: config now carries
  `auth_mode`. `pi-api-key` verifies the hash of the owner's `_chat_credential.py`
  (`credential_module_path`/`credential_module_sha256`) without loading it, then reads the
  `api_key` entry with a verbatim copy of `read_existing_api_key_credential` plus the
  printable-ASCII gate, emitting only booleans (`expires_ms` 0). `opencode-go` joined the bearer
  providers for the catalog GET. Unknown modes raise, so the child exits 1 and the parent
  rejects with "credential probe failed closed".
- `services/program_foundry_gepa_comparison_jury_preflight.py`: `_probe_config` passes
  `auth_mode` and, for api-key families, the credential module path/hash; `probed` keys off
  `auth_mode != "none"`.
- `cli/commands/program_refine_foundry_jury.py`: help strings list the fifth family and its
  default. This file is outside the task's stated allowlist, but the existing help-text test
  asserts every `TASK_LOCAL_PROVIDER_NAMES` entry appears there, so the eight-line help edit was
  required for the suites to stay green; flagged for the reviewer.
- Tests: new `tests/test_program_foundry_gepa_comparison_jury_opencode_go.py` (62 tests: family
  literals, origin constant, model rules, revalidator/custodian/metadata, execution request, CLI
  forwarding, fake-backend end-to-end through configure/adapter/custody, api-key probe with a
  fake auth file and a loopback catalog, loaded-owner type binding, runtime binding for five
  names, owner repin literals). Existing xAI/Copilot/local vLLM/preflight suites updated from four
  to five families and the probe config gained `auth_mode`.
- Docs: dated section in `docs/project/2026-09-01-foundry-dspy-lm-auth-jury-integration.md`.

## Why the probe copies the reader instead of aliasing `_chat_credential.py`

The probe child imports only stdlib and httpx and never imports `dspy_lm_auth`. `auth.py` can be
loaded from a file path under an alias because it is self-contained; `_chat_credential.py`
imports `dspy_lm_auth.outcome_receipt` at module level, so aliasing it would import the owner
package in the child. The hash of the owner file is still bound into the config and verified, so
a change to the owner's reader rules fails the probe until the copy is reviewed and the pin
refreshed.

## Validation

- `uv run --no-sync pytest tests/test_program_foundry_gepa_comparison_jury*.py tests/test_program_model_jury*.py -m "not live"`: 384 passed.
- `ruff check` / `ruff format --check` on services, the CLI command, and tests: clean.
- `ty check` on the four touched service modules and the CLI command: clean.
- `git diff --check`: clean.
- `just task-scope-check task_id=5368`: skip (no AK scope snapshot; repo-default scope applies).

## Not done

- No live OpenCode Go jury, no network, no AK mutation, no commit. `~/.pi/agent/auth.json` was
  not read; the probe tests use a fake auth file under `tmp_path`.
