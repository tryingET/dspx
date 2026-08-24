---
summary: "AK-4694 captured the architecture gate for one bounded generated ReActV2 corpus-search callable."
read_when:
  - "Continuing the six-brain hardware voice-turn work after Decision 115 review."
type: "diary"
---

# Bounded ReActV2 declared-corpus tool decision gate

## Observed

The six-brain voice-turn handoff requires deep-research to execute a real ReActV2 corpus-search call. Current DSPx source still renders `tools=[]`, sets tool binding false, and replay-checks that no executable binding exists. The existing `local_corpus_snapshot` seam is a deterministic materialization-time corpus capture, not a ReActV2 callable.

The checked-in program-gen broadening frame explicitly reserves executable tool binding for a later reviewed safe-adapter contract. This makes the requested change architecture-significant rather than a routine bounded source patch.

## Authority actions

- Created and claimed AK task 4694 for the decision-gate artifacts only.
- Created AK Decision 115 in `review_pending` with architecture tier and the RFC linked.
- Attached the problem brief and evidence note.
- Did not implement, stage, or claim generated tool execution.

## Local concurrent state preserved

Pre-existing/concurrent DSPx changes were not absorbed:

- `packages/dspx-core/src/dspx/services/optimize_service.py`;
- `.ontology/`;
- `examples/voice_turn_brains/`.

The voice-brain directory contains preliminary intents, generated local candidates, live behavior outputs, and partial/degraded GEPA attempts from an earlier session. Deep-research there still uses a scheduled Retriever rather than the required ReActV2 tool, so those artifacts do not prove the objective and remain uncommitted.

## Next legal move

Run the required structured review for Decision 115. Implementation may begin only after a legal `ready_for_adr` closure, accepted ADR, and linked implementation plus validation/rollout/rollback artifacts. If review returns `revise_rfc`, revise and re-review rather than continuing source work.
