---
summary: "Observed DSPx evidence that ReActV2 corpus-tool execution is currently blocked and requires a reviewed contract."
read_when:
  - "Reviewing the bounded ReActV2 declared-corpus tool RFC."
type: "reference"
---

# Evidence: current ReActV2 and corpus retrieval boundary

Observed on `main` at `d731f5eb` during AK-4694 preflight:

- `packages/dspx-core/src/dspx/services/program_topology.py` renders ReActV2 with `tools=[]` and `_TOOL_BINDING_ALLOWED = False`.
- `packages/dspx-core/src/dspx/services/program_generated_policy.py` accepts only empty ReAct/ReActV2 tool lists and bounded iterations.
- `packages/dspx-core/src/dspx/services/run_replay_service.py` verifies that tool binding remains false.
- `packages/dspx-core/src/dspx/services/program_tool_contracts.py` keeps refs descriptor-only and explicitly denies `dspy.Tool` execution.
- `tests/test_program_topology_intent_react_v2.py`, `tests/test_program_generated_policy.py`, and `tests/test_program_tool_contracts.py` assert the no-tool contract.
- `local_corpus_snapshot` already captures a declared JSONL corpus at materialization and emits deterministic bounded lexical retrieval without rereading the source at runtime.
- `docs/project/program-gen-broadening-strategic-frame.md` says executable tool binding requires a later explicit reviewed safety contract; its recommended executable-safe-subset wave follows descriptor and dry-run policy work.

The operator-supplied acceptance contract additionally requires a fixed callable, hash-bound embedded snapshot, no network/subprocess/environment/arbitrary filesystem/mutation effects, bounded query/result/call/iteration budgets, deterministic tie-breaking, runtime tool-call evidence, citation validation, generated-policy agreement, and replay rejection of drift.

Live endpoint preflight observed:

- baseline text `http://127.0.0.1:1234/v1/models`: HTTP 200;
- ASR TCP listener `127.0.0.1:1260`: reachable;
- TTS HTTP service at `127.0.0.1:7861`: listener responded (root returned HTTP 404, which is not an application health proof);
- `${XDG_RUNTIME_DIR}/voice-dictation/control.sock`: absent, so workstation dictation/physical proof was blocked at this observation point.

No source implementation is authorized by this evidence note. It records why the decision membrane applies.
