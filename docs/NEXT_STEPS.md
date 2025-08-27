Next Steps (Immediate)
======================

These are the direct next tasks to continue the refactor with provider selection and tools.

1) Provider selection in config/CLI
- Add `provider` to `config.toml` and honor `DSPX_PROVIDER` env.
- Update services/CLIs to accept a `--provider` flag (fallback to config/env).
- Default remains `codex-exec`.

2) ToolRegistry scaffolding
- Introduce a minimal `ToolRegistry` with a couple of function tools
  (e.g., simple retrieval stub, python_exec stub) and a registration API.
- Expose tool selection in services (esp. AgentService later).

3) AgentService (ReAct) skeleton
- Add `dspx/services/agent_service.py` that composes LMBase + ToolRegistry
  and runs a minimal ReAct loop (using DSPy’s ReAct if available).
- Initial demo CLI to showcase tool use (no heavy logic yet).

4) Tests
- Add unit tests for provider selection and ToolRegistry.
- Include a smoke test for AgentService with StubLM.

5) OpenAI Responses provider (optional)
- Add a basic `providers_register_openai.py` that uses dspy.LM("openai/...")
  when API key is present; register with the ProviderRegistry.
