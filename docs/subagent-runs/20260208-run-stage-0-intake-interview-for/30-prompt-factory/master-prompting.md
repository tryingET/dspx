# Master prompt factory output

## Input synthesis references
- `00-intake/interview-4d.responses.md`
- `00-intake/brief.md`
- `10-explorers/codebase.md`
- `10-explorers/docs.md`
- `10-explorers/database.md`
- `20-synthesis/technical-writer.md`

## Domain roster
1. DSPx workflow orchestration domain
   - scope: intake router, subagent workflow contracts, run artifacts/gates
2. Upstream MLflow observability domain
   - scope: tracing/autolog hardening and correlation semantics from RFC packet
3. Upstream DSPy callback contract domain
   - scope: callback lifecycle/context contracts from RFC packet

## Generated system prompts
- `30-prompt-factory/system-prompts/dspx-architect-system.md`
- `30-prompt-factory/system-prompts/mlflow-architect-system.md`
- `30-prompt-factory/system-prompts/dspy-architect-system.md`

## Generated task prompts
- `30-prompt-factory/task-prompts/dspx-architect-task.md`
- `30-prompt-factory/task-prompts/mlflow-architect-task.md`
- `30-prompt-factory/task-prompts/dspy-architect-task.md`

## Prompt quality checks
- Boundary/anti-goals present: yes
- Constraints/dependencies explicit: yes
- Invariants/risks explicit: yes
- Output contract explicit: yes
- Evidence citation requirement: yes

## Escalation triggers
- Canonical `mlflow.db` is clarified but file is not locally available for DB explorer evidence.
- RFC packet has sequencing + placeholders, but top-3 issue/PR execution priority still needs owner pinning.
- Related handoff run-id exists (`20260208-dspx-development-session-kickoff`); current run-id remains canonical unless explicitly changed in command.
