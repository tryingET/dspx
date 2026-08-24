from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dspy

from module import (
    DefinePersonaModule,
    AnswerElaborateModule,
    io_spec,
    normalize_output,
    output_weights,
)

OBJECTIVE = 'Define the requested persona, then develop a complete, nuanced spoken answer to the transcription.'
CONSTRAINTS = ['Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.', 'Define a concrete persona from persona_intent before answering.', 'Develop the answer with context, reasoning, implications, and useful caveats.', 'Prefer coherent spoken prose over terse bullets.', 'Do not echo the transcription or persona intent.', 'Return only the response field.']
METRIC = 'f1'
QUALITY_CRITERIA = []
DECLARED_TOPOLOGY = {'kind': 'pipeline', 'execution_status': 'declared_not_materialized', 'modules': [{'id': 'define_persona', 'primitive': 'Predict', 'signature': {'name': 'DefinePersona', 'inputs': ['persona_intent'], 'outputs': ['persona']}, 'role': 'define_persona'}, {'id': 'answer_elaborate', 'primitive': 'ChainOfThought', 'signature': {'name': 'AnswerElaborate', 'inputs': ['transcription', 'persona'], 'outputs': ['response']}, 'role': 'developed_answer'}], 'edges': [{'from': 'input', 'to': 'define_persona'}, {'from': 'define_persona', 'to': 'answer_elaborate'}, {'from': 'answer_elaborate', 'to': 'output'}]}
INFERRED_TOPOLOGY = {}
MATERIALIZED_TOPOLOGY = {'kind': 'pipeline', 'execution_status': 'pipeline_materialized', 'modules': [{'id': 'define_persona', 'primitive': 'Predict', 'signature': {'name': 'DefinePersona', 'inputs': ['persona_intent'], 'outputs': ['persona']}, 'role': 'define_persona'}, {'id': 'answer_elaborate', 'primitive': 'ChainOfThought', 'signature': {'name': 'AnswerElaborate', 'inputs': ['transcription', 'persona'], 'outputs': ['response']}, 'role': 'developed_answer'}], 'edges': [{'from': 'input', 'to': 'define_persona'}, {'from': 'define_persona', 'to': 'answer_elaborate'}, {'from': 'answer_elaborate', 'to': 'output'}], 'scheduler_plan': {'schema_version': 'program-topology-scheduler-plan-v1', 'status': 'deterministic_local_dag_schedule', 'scheduler': 'bounded_ready_queue', 'module_order': ['define_persona', 'answer_elaborate'], 'declaration_order': ['define_persona', 'answer_elaborate'], 'output_producers': ['answer_elaborate'], 'module_readiness': {'define_persona': {'required_inputs': ['persona_intent'], 'produced_outputs': ['persona'], 'inbound_edges': [{'from': 'input', 'to': 'define_persona'}], 'primitive': 'Predict'}, 'answer_elaborate': {'required_inputs': ['transcription', 'persona'], 'produced_outputs': ['response'], 'inbound_edges': [{'from': 'define_persona', 'to': 'answer_elaborate'}], 'primitive': 'ChainOfThought'}}, 'effect': {'provider_called': False, 'tool_called': False, 'retriever_called': False, 'custom_import_loaded': False, 'authority_mutated': False}}}
TOPOLOGY_EXECUTION_STATUS = 'pipeline_materialized'
MATERIALIZATION_SCOPE = {'topology_declared': True, 'topology_inferred': False, 'topology_materialized': True, 'current_renderer': 'pipeline_topology_renderer'}
SCHEDULER_PLAN = {'schema_version': 'program-topology-scheduler-plan-v1', 'status': 'deterministic_local_dag_schedule', 'scheduler': 'bounded_ready_queue', 'module_order': ['define_persona', 'answer_elaborate'], 'declaration_order': ['define_persona', 'answer_elaborate'], 'output_producers': ['answer_elaborate'], 'module_readiness': {'define_persona': {'required_inputs': ['persona_intent'], 'produced_outputs': ['persona'], 'inbound_edges': [{'from': 'input', 'to': 'define_persona'}], 'primitive': 'Predict'}, 'answer_elaborate': {'required_inputs': ['transcription', 'persona'], 'produced_outputs': ['response'], 'inbound_edges': [{'from': 'define_persona', 'to': 'answer_elaborate'}], 'primitive': 'ChainOfThought'}}, 'effect': {'provider_called': False, 'tool_called': False, 'retriever_called': False, 'custom_import_loaded': False, 'authority_mutated': False}}
MODULE_ORDER = ['define_persona', 'answer_elaborate']
MODULE_SIGNATURES = {'define_persona': {'inputs': ['persona_intent'], 'outputs': ['persona']}, 'answer_elaborate': {'inputs': ['transcription', 'persona'], 'outputs': ['response']}}
MODULE_PRIMITIVES = {'define_persona': 'Predict', 'answer_elaborate': 'ChainOfThought'}
PROGRAM_OUTPUTS = ['response']
EDGES = [{'from': 'input', 'to': 'define_persona'}, {'from': 'define_persona', 'to': 'answer_elaborate'}, {'from': 'answer_elaborate', 'to': 'output'}]
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


class VoiceTurnElaborateBrainPipelineProgram(dspy.Module):
    """Composed explicit pipeline topology program."""

    def __init__(self, use_cot: bool = False) -> None:
        super().__init__()
        self.define_persona = DefinePersonaModule(use_cot=use_cot)
        self.answer_elaborate = AnswerElaborateModule(use_cot=use_cot)

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
                elif module_id == 'answer_elaborate':
                    prediction = self.answer_elaborate(**kwargs)
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
    return VoiceTurnElaborateBrainPipelineProgram()


def build_student(*, use_cot: bool = False) -> dspy.Module:
    return VoiceTurnElaborateBrainPipelineProgram(use_cot=use_cot)


def intent_summary() -> dict[str, object]:
    return {
        'name': 'VoiceTurnElaborateBrain',
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
        'program_class': 'VoiceTurnElaborateBrainPipelineProgram',
    }
