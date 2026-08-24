from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dspy

from module import (
    DefinePersonaModule,
    RetrieveVoiceTurnResearchCorpusModule,
    SynthesizeDeepResearchModule,
    io_spec,
    normalize_output,
    output_weights,
)

OBJECTIVE = 'Define the requested persona, retrieve bounded local evidence, and synthesize multiple evidence perspectives with corpus-grounded citations.'
CONSTRAINTS = ['Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.', 'Define a concrete persona from persona_intent before answering.', 'Use only facts supported by passages whose lexical score is greater than zero.', 'Synthesize at least two relevant perspectives such as ownership, execution scope, evidence safety, optimization, or residual limitations when the corpus supports them.', 'Cite every material claim with the exact retrieved document id in square brackets.', 'Never invent a citation id, source, quote, or external fact.', 'State conflicts or missing evidence explicitly.', 'If no retrieved passage with positive score supports the question, respond exactly: No supporting sources were found in the declared corpus.', 'Return only the response field.']
METRIC = 'f1'
QUALITY_CRITERIA = []
DECLARED_TOPOLOGY = {'kind': 'retrieve_then_answer', 'execution_status': 'declared_not_materialized', 'modules': [{'id': 'define_persona', 'primitive': 'Predict', 'signature': {'name': 'DefinePersona', 'inputs': ['persona_intent'], 'outputs': ['persona']}, 'role': 'define_persona'}, {'id': 'retrieve_corpus', 'primitive': 'Retriever', 'signature': {'name': 'RetrieveVoiceTurnResearchCorpus', 'inputs': ['transcription'], 'outputs': ['passages']}, 'role': 'retrieve_multi_perspective_grounding', 'retriever': {'mode': 'inline_corpus', 'k': 5, 'documents': [{'id': 'voice-turn-owner-split', 'text': 'The batch voice-turn has three explicit owners. softwareco/infra/workstation owns physical OpenDeck actions, the dictation activation lease, microphone capture, and clipboard transcript delivery. softwareco/owned/local-ai-control-plane owns ai-control voice-turn composition, brain and TTS invocation, and the single sanitized receipt. softwareco/owned/dspx owns the six separate DSPy brain programs and their GEPA optimization evidence.'}, {'id': 'voice-turn-capture-contract', 'text': 'Capture reuses the existing dictate-clip path. The OpenDeck action starts an acknowledged same-user lease on the voice-dictation control socket; a second press releases that lease. When the combined gate becomes inactive, voice-dictation injects finalizing silence and publishes the final transcript to the clipboard. local-ai-control-plane never touches this lease.'}, {'id': 'voice-turn-batch-scope', 'text': 'The v1 hardware-triggered voice-turn is batch and one-time: capture one utterance, run exactly one selected mode brain, synthesize one answer, and persist one receipt. Streaming, a continuing interactive loop, and Pipecat belong to a later real-time phase and are not part of v1.'}, {'id': 'voice-turn-research-boundary', 'text': 'The researched and deep-research brains retrieve only from an operator-declared bounded inline or local corpus snapshot. They do not use live external retrieval, ReAct tool binding, or fabricated sources. If retrieved passages do not support an answer, the brain must say that no supporting sources were found.'}, {'id': 'voice-turn-receipt-boundary', 'text': 'A voice-turn receipt is evidence, not promotion authority. It may contain mode identifiers, model identifiers, timings, statuses, and SHA-256 digests, but it must not contain raw utterance, persona intent, transcript, answer text, or raw artifact paths. Operator-visible stdout may carry in-flight transcript and answer text.'}, {'id': 'voice-turn-modality-boundary', 'text': 'The voice-turn is a composed audio-to-audio route: captured audio becomes text, a text-generation brain transforms it, and TTS produces audio. A composed route is not a native omni model and must never be labeled native-omni.'}, {'id': 'voice-turn-gepa-boundary', 'text': 'GEPA optimization in DSPx consumes explicit behavior examples, writes hash-bound optimizer output, and requires a separate materialize-gepa-candidate step to create an optimized candidate manifest. Optimization and materialization are local empirical evidence; neither selects a winner, approves promotion, activates production, mutates governance, or transfers authority.'}]}}, {'id': 'synthesize_deep_research', 'primitive': 'ChainOfThought', 'signature': {'name': 'SynthesizeDeepResearch', 'inputs': ['transcription', 'persona', 'passages'], 'outputs': ['response']}, 'role': 'multi_perspective_cited_synthesis'}], 'edges': [{'from': 'input', 'to': 'define_persona'}, {'from': 'input', 'to': 'retrieve_corpus'}, {'from': 'define_persona', 'to': 'synthesize_deep_research'}, {'from': 'retrieve_corpus', 'to': 'synthesize_deep_research'}, {'from': 'synthesize_deep_research', 'to': 'output'}]}
INFERRED_TOPOLOGY = {}
MATERIALIZED_TOPOLOGY = {'kind': 'retrieve_then_answer', 'execution_status': 'retrieve_then_answer_materialized', 'modules': [{'id': 'define_persona', 'primitive': 'Predict', 'signature': {'name': 'DefinePersona', 'inputs': ['persona_intent'], 'outputs': ['persona']}, 'role': 'define_persona'}, {'id': 'retrieve_corpus', 'primitive': 'Retriever', 'signature': {'name': 'RetrieveVoiceTurnResearchCorpus', 'inputs': ['transcription'], 'outputs': ['passages']}, 'role': 'retrieve_multi_perspective_grounding', 'retriever': {'mode': 'inline_corpus', 'k': 5, 'documents': [{'id': 'voice-turn-owner-split', 'text': 'The batch voice-turn has three explicit owners. softwareco/infra/workstation owns physical OpenDeck actions, the dictation activation lease, microphone capture, and clipboard transcript delivery. softwareco/owned/local-ai-control-plane owns ai-control voice-turn composition, brain and TTS invocation, and the single sanitized receipt. softwareco/owned/dspx owns the six separate DSPy brain programs and their GEPA optimization evidence.'}, {'id': 'voice-turn-capture-contract', 'text': 'Capture reuses the existing dictate-clip path. The OpenDeck action starts an acknowledged same-user lease on the voice-dictation control socket; a second press releases that lease. When the combined gate becomes inactive, voice-dictation injects finalizing silence and publishes the final transcript to the clipboard. local-ai-control-plane never touches this lease.'}, {'id': 'voice-turn-batch-scope', 'text': 'The v1 hardware-triggered voice-turn is batch and one-time: capture one utterance, run exactly one selected mode brain, synthesize one answer, and persist one receipt. Streaming, a continuing interactive loop, and Pipecat belong to a later real-time phase and are not part of v1.'}, {'id': 'voice-turn-research-boundary', 'text': 'The researched and deep-research brains retrieve only from an operator-declared bounded inline or local corpus snapshot. They do not use live external retrieval, ReAct tool binding, or fabricated sources. If retrieved passages do not support an answer, the brain must say that no supporting sources were found.'}, {'id': 'voice-turn-receipt-boundary', 'text': 'A voice-turn receipt is evidence, not promotion authority. It may contain mode identifiers, model identifiers, timings, statuses, and SHA-256 digests, but it must not contain raw utterance, persona intent, transcript, answer text, or raw artifact paths. Operator-visible stdout may carry in-flight transcript and answer text.'}, {'id': 'voice-turn-modality-boundary', 'text': 'The voice-turn is a composed audio-to-audio route: captured audio becomes text, a text-generation brain transforms it, and TTS produces audio. A composed route is not a native omni model and must never be labeled native-omni.'}, {'id': 'voice-turn-gepa-boundary', 'text': 'GEPA optimization in DSPx consumes explicit behavior examples, writes hash-bound optimizer output, and requires a separate materialize-gepa-candidate step to create an optimized candidate manifest. Optimization and materialization are local empirical evidence; neither selects a winner, approves promotion, activates production, mutates governance, or transfers authority.'}]}}, {'id': 'synthesize_deep_research', 'primitive': 'ChainOfThought', 'signature': {'name': 'SynthesizeDeepResearch', 'inputs': ['transcription', 'persona', 'passages'], 'outputs': ['response']}, 'role': 'multi_perspective_cited_synthesis'}], 'edges': [{'from': 'input', 'to': 'define_persona'}, {'from': 'input', 'to': 'retrieve_corpus'}, {'from': 'define_persona', 'to': 'synthesize_deep_research'}, {'from': 'retrieve_corpus', 'to': 'synthesize_deep_research'}, {'from': 'synthesize_deep_research', 'to': 'output'}], 'materialized_from_kind': 'retrieve_then_answer', 'renderer': 'retrieve_then_answer_topology_renderer', 'scheduler_plan': {'schema_version': 'program-topology-scheduler-plan-v1', 'status': 'deterministic_local_dag_schedule', 'scheduler': 'bounded_ready_queue', 'module_order': ['define_persona', 'retrieve_corpus', 'synthesize_deep_research'], 'declaration_order': ['define_persona', 'retrieve_corpus', 'synthesize_deep_research'], 'output_producers': ['synthesize_deep_research'], 'module_readiness': {'define_persona': {'required_inputs': ['persona_intent'], 'produced_outputs': ['persona'], 'inbound_edges': [{'from': 'input', 'to': 'define_persona'}], 'primitive': 'Predict'}, 'retrieve_corpus': {'required_inputs': ['transcription'], 'produced_outputs': ['passages'], 'inbound_edges': [{'from': 'input', 'to': 'retrieve_corpus'}], 'primitive': 'Retriever'}, 'synthesize_deep_research': {'required_inputs': ['transcription', 'persona', 'passages'], 'produced_outputs': ['response'], 'inbound_edges': [{'from': 'define_persona', 'to': 'synthesize_deep_research'}, {'from': 'retrieve_corpus', 'to': 'synthesize_deep_research'}], 'primitive': 'ChainOfThought'}}, 'effect': {'provider_called': False, 'tool_called': False, 'retriever_called': False, 'custom_import_loaded': False, 'authority_mutated': False}}}
TOPOLOGY_EXECUTION_STATUS = 'retrieve_then_answer_materialized'
MATERIALIZATION_SCOPE = {'topology_declared': True, 'topology_inferred': False, 'topology_materialized': True, 'current_renderer': 'retrieve_then_answer_topology_renderer'}
SCHEDULER_PLAN = {'schema_version': 'program-topology-scheduler-plan-v1', 'status': 'deterministic_local_dag_schedule', 'scheduler': 'bounded_ready_queue', 'module_order': ['define_persona', 'retrieve_corpus', 'synthesize_deep_research'], 'declaration_order': ['define_persona', 'retrieve_corpus', 'synthesize_deep_research'], 'output_producers': ['synthesize_deep_research'], 'module_readiness': {'define_persona': {'required_inputs': ['persona_intent'], 'produced_outputs': ['persona'], 'inbound_edges': [{'from': 'input', 'to': 'define_persona'}], 'primitive': 'Predict'}, 'retrieve_corpus': {'required_inputs': ['transcription'], 'produced_outputs': ['passages'], 'inbound_edges': [{'from': 'input', 'to': 'retrieve_corpus'}], 'primitive': 'Retriever'}, 'synthesize_deep_research': {'required_inputs': ['transcription', 'persona', 'passages'], 'produced_outputs': ['response'], 'inbound_edges': [{'from': 'define_persona', 'to': 'synthesize_deep_research'}, {'from': 'retrieve_corpus', 'to': 'synthesize_deep_research'}], 'primitive': 'ChainOfThought'}}, 'effect': {'provider_called': False, 'tool_called': False, 'retriever_called': False, 'custom_import_loaded': False, 'authority_mutated': False}}
MODULE_ORDER = ['define_persona', 'retrieve_corpus', 'synthesize_deep_research']
MODULE_SIGNATURES = {'define_persona': {'inputs': ['persona_intent'], 'outputs': ['persona']}, 'retrieve_corpus': {'inputs': ['transcription'], 'outputs': ['passages']}, 'synthesize_deep_research': {'inputs': ['transcription', 'persona', 'passages'], 'outputs': ['response']}}
MODULE_PRIMITIVES = {'define_persona': 'Predict', 'retrieve_corpus': 'Retriever', 'synthesize_deep_research': 'ChainOfThought'}
PROGRAM_OUTPUTS = ['response']
EDGES = [{'from': 'input', 'to': 'define_persona'}, {'from': 'input', 'to': 'retrieve_corpus'}, {'from': 'define_persona', 'to': 'synthesize_deep_research'}, {'from': 'retrieve_corpus', 'to': 'synthesize_deep_research'}, {'from': 'synthesize_deep_research', 'to': 'output'}]
PROGRAM_TEMPLATE_VERSION = 'program-candidate-assembly-v1'


def load_manifest() -> dict[str, Any]:
    return {}


def _manifest_hash() -> str:
    return ''


def configure_observability(
    *,
    run_name: str = 'program-runtime',
    run_kind: str = 'program-runtime',
) -> bool:
    return False


def end_observability_run(started: bool, *, status: str = 'FINISHED') -> None:
    return None


def _prediction_mapping(prediction: object) -> dict[str, object]:
    return dict(prediction)


def _edge_condition_matches(edge: dict[str, object], state: dict[str, object]) -> bool:
    when = edge.get('when')
    if not isinstance(when, dict):
        return True
    field = str(when.get('field') or '')
    return str(state.get(field, '')) == str(when.get('equals'))


def _edge_source_ready(edge: dict[str, object], executed: set[str]) -> bool:
    source = str(edge.get('from') or '')
    return source == 'input' or source in executed


def _module_ready(module_id: str, state: dict[str, object], executed: set[str]) -> bool:
    inputs = list(MODULE_SIGNATURES[module_id]['inputs'])
    if any(name not in state for name in inputs):
        return False
    inbound = [edge for edge in EDGES if edge.get('to') == module_id]
    if not inbound:
        return False
    return any(
        _edge_source_ready(edge, executed) and _edge_condition_matches(edge, state)
        for edge in inbound
    )


def _output_edges_ready(module_id: str, state: dict[str, object], executed: set[str]) -> bool:
    outbound = [edge for edge in EDGES if edge.get('from') == module_id and edge.get('to') == 'output']
    return any(
        _edge_source_ready(edge, executed) and _edge_condition_matches(edge, state)
        for edge in outbound
    )


def _missing_declared_outputs(outputs: dict[str, object]) -> list[str]:
    return [name for name in PROGRAM_OUTPUTS if name not in outputs]


class VoiceTurnDeepResearchBrainPipelineProgram(dspy.Module):
    """Composed explicit pipeline topology program."""

    def __init__(self, use_cot: bool = False) -> None:
        super().__init__()
        self.define_persona = DefinePersonaModule(use_cot=use_cot)
        self.retrieve_corpus = RetrieveVoiceTurnResearchCorpusModule(use_cot=use_cot)
        self.synthesize_deep_research = SynthesizeDeepResearchModule(use_cot=use_cot)

    def forward(self, transcription: str, persona_intent: str) -> dspy.Prediction:
        state: dict[str, object] = {'transcription': transcription, 'persona_intent': persona_intent}
        delivered_outputs: dict[str, object] = {}
        self._last_runtime_trace = {'schema_version': 'program-runtime-trace-fragment-v1', 'module_calls': [], 'final_outputs': {}, 'scheduler_events': []}
        executed: set[str] = set()
        pending: set[str] = set(MODULE_ORDER)
        while pending:
            progressed = False
            for module_id in MODULE_ORDER:
                if module_id not in pending:
                    continue
                if not _module_ready(module_id, state, executed):
                    continue
                signature = MODULE_SIGNATURES[module_id]
                kwargs = {name: state[name] for name in signature['inputs']}
                if module_id == 'define_persona':
                    prediction = self.define_persona(**kwargs)
                elif module_id == 'retrieve_corpus':
                    prediction = self.retrieve_corpus(**kwargs)
                elif module_id == 'synthesize_deep_research':
                    prediction = self.synthesize_deep_research(**kwargs)
                else:
                    raise RuntimeError(f'unknown pipeline module: {module_id}')
                executed.add(module_id)
                pending = pending - {module_id}
                progressed = True
                mapped = _prediction_mapping(prediction)
                call_outputs: dict[str, object] = {}
                for output_name in signature['outputs']:
                    if output_name in mapped:
                        state[output_name] = mapped[output_name]
                    if output_name in state:
                        call_outputs[output_name] = state[output_name]
                self._last_runtime_trace['module_calls'].append({
                    'module_id': module_id,
                    'primitive': MODULE_PRIMITIVES.get(module_id, 'Predict'),
                    'inputs': _jsonable(kwargs),
                    'outputs': _jsonable(call_outputs),
                    'status': 'executed',
                    'react_steps': [],
                    'react_v2_steps': [],
                    'program_of_thought_steps': [],
                    'tool_call_intents': [],
                    'tool_call_results': [],
                })
                if _output_edges_ready(module_id, state, executed):
                    for output_name in signature['outputs']:
                        if output_name in PROGRAM_OUTPUTS and output_name in state:
                            delivered_outputs[output_name] = state[output_name]
            if not progressed:
                missing_outputs = _missing_declared_outputs(delivered_outputs)
                if missing_outputs:
                    self._last_runtime_trace['scheduler_events'].append({'status': 'scheduler_stalled', 'missing_outputs': list(missing_outputs), 'pending': sorted(pending)})
                    raise RuntimeError(
                        'pipeline topology scheduler stalled before producing declared outputs: '
                        f'missing_outputs={missing_outputs} pending={sorted(pending)}'
                    )
                break
        missing_outputs = _missing_declared_outputs(delivered_outputs)
        if missing_outputs:
            self._last_runtime_trace['scheduler_events'].append({'status': 'completed_missing_outputs', 'missing_outputs': list(missing_outputs), 'pending': sorted(pending)})
            raise RuntimeError(
                'pipeline topology completed without declared outputs: '
                f'missing_outputs={missing_outputs}'
            )
        self._last_runtime_trace['scheduler_events'].append({'status': 'completed', 'missing_outputs': [], 'pending': []})
        self._last_runtime_trace['final_outputs'] = _jsonable(delivered_outputs)
        return dspy.Prediction(response=_jsonable(delivered_outputs['response']))


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def build_program() -> dspy.Module:
    return VoiceTurnDeepResearchBrainPipelineProgram()


def build_student(*, use_cot: bool = False) -> dspy.Module:
    return VoiceTurnDeepResearchBrainPipelineProgram(use_cot=use_cot)


def intent_summary() -> dict[str, object]:
    return {
        'name': 'VoiceTurnDeepResearchBrain',
        'objective': OBJECTIVE,
        'constraints': list(CONSTRAINTS),
        'metric': METRIC,
        'quality_criteria': list(QUALITY_CRITERIA),
        'io': io_spec(),
        'declared_topology': dict(DECLARED_TOPOLOGY),
        'inferred_topology': dict(INFERRED_TOPOLOGY),
        'materialized_topology': dict(MATERIALIZED_TOPOLOGY),
        'topology_execution_status': TOPOLOGY_EXECUTION_STATUS,
        'materialization_scope': dict(MATERIALIZATION_SCOPE),
        'scheduler_plan': dict(SCHEDULER_PLAN),
        'module_order': list(MODULE_ORDER),
        'program_class': 'VoiceTurnDeepResearchBrainPipelineProgram',
    }
