Next Steps (Immediate)
======================

Completed
---------
- Provider selection in config/CLI:
  - [x] `[provider].name` in `config.toml` + `DSPX_PROVIDER` env override
  - [x] `--provider` flag in `codegen`, `vibegen`, `viberefine`
  - [x] Services instantiate LMs via `ProviderRegistry` (default `codex-exec`)

Remaining
---------
1) ToolRegistry scaffolding
- Introduce a minimal `ToolRegistry` with a couple of function tools
  (e.g., retrieval stub, python_exec stub) and a registration API.
- Expose tool selection in services (esp. AgentService later).

2) AgentService (ReAct) skeleton
- Add `dspx/services/agent_service.py` that composes LMBase + ToolRegistry
  and runs a minimal ReAct loop (using DSPy’s ReAct if available).
- Add a demo CLI to showcase tool use.

3) Tests
- Add unit tests for provider selection and `ToolRegistry`.
- Include a smoke test for `AgentService` with `StubLM`.
- Optional: a trace-smoke task that emits to MLflow.

4) OpenAI Responses provider (optional)
- Add `providers_register_openai.py` using `dspy.LM("openai/...")` when API key
  is present; register it with `ProviderRegistry` and set capability flags.
