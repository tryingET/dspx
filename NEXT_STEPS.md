Next Steps (Immediate)
======================

These are the direct next tasks to advance the refactor while keeping current CLIs working.

1) Introduce LMBase + DTO stubs
- Add a small provider interface (e.g., `lm_base.py`) with `generate(prompt|messages, **opts)`.
- Define v1 request/response DTOs (pydantic) used between Services and Providers.
- Adapt `CodexExecLM` to implement LMBase while preserving the DSPy BaseLM bridge.

2) ProviderRegistry + Capabilities
- Add a simple registry (`providers/__init__.py`) mapping provider name → factory.
- Add a `ProviderCapabilities` struct (e.g., `supports_tools`, `code_exec`, `json_mode`).
- Register `codex-exec` with current defaults from `config.toml`.

3) Move orchestration into Services
- Create `services/codegen.py` and `services/signatures.py`, `services/refine.py`.
- Lift logic from `codegen.py`, `vibegen.py`, `viberefine.py` into these services.
- Keep CLIs as thin wrappers calling the services.

4) Shared CLI options
- Add a `cli/shared.py` (or mixin) for standard flags (model, tracing toggle, config path).
- Update CLIs to use shared options and rely on `config_loader` + `tracing`.

5) Minimal tests
- Add a stub provider that returns canned responses for unit tests.
- Unit-test service functions (no network) and verify DTO conversions.
- Add a smoke test for one CLI path with MLflow disabled.

