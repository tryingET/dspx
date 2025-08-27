Next Steps (Immediate)
======================

Completed
---------
- Provider selection in config/CLI:
  - [x] `[provider].name` in `config.toml` + `DSPX_PROVIDER` env override
  - [x] `--provider` flag in `codegen`, `vibegen`, `viberefine`
  - [x] Services instantiate LMs via `ProviderRegistry` (default `codex-exec`)
 - ToolRegistry scaffolding:
   - [x] `web_search`, `web_fetch`, `web_scrape`, `data_preview`
   - [x] Justfile tasks for `web-search`, `web-fetch`, `web-scrape`, `data-preview`
 - AgentService (ReAct) skeleton:
   - [x] `agent_demo.py` CLI wired to DSPy tools

Remaining
---------
1) Tests
- Add unit tests for provider selection and `ToolRegistry`.
- Include a smoke test for `AgentService` with `StubLM`.
- Optional: a trace-smoke task that emits to MLflow.

2) OpenAI Responses provider (optional)
- Add `providers_register_openai.py` using `dspy.LM("openai/...")` when API key
  is present; register it with `ProviderRegistry` and set capability flags.
