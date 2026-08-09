from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dspy

from module import (
    DefinePersonaModule,
    AnswerSimpleModule,
    io_spec,
    normalize_output,
    output_weights,
)

OBJECTIVE = 'Define the requested persona, then answer the spoken transcription directly and concisely.'
CONSTRAINTS = ['Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.', 'Define a concrete persona from persona_intent before answering.', 'Give a direct, concise, factual answer.', 'Do not echo the transcription or persona intent.', 'Return only the response field.', 'load local GEPA optimizer output as the candidate program implementation']
METRIC = 'f1'
QUALITY_CRITERIA = []
DECLARED_TOPOLOGY = {'kind': 'pipeline', 'execution_status': 'declared_not_materialized', 'modules': [{'id': 'define_persona', 'primitive': 'Predict', 'signature': {'name': 'DefinePersona', 'inputs': ['persona_intent'], 'outputs': ['persona']}, 'role': 'define_persona'}, {'id': 'answer_simple', 'primitive': 'Predict', 'signature': {'name': 'AnswerSimple', 'inputs': ['transcription', 'persona'], 'outputs': ['response']}, 'role': 'direct_answer'}], 'edges': [{'from': 'input', 'to': 'define_persona'}, {'from': 'define_persona', 'to': 'answer_simple'}, {'from': 'answer_simple', 'to': 'output'}]}
INFERRED_TOPOLOGY = {}
MATERIALIZED_TOPOLOGY = {'kind': 'pipeline', 'execution_status': 'pipeline_materialized', 'modules': [{'id': 'define_persona', 'primitive': 'Predict', 'signature': {'name': 'DefinePersona', 'inputs': ['persona_intent'], 'outputs': ['persona']}, 'role': 'define_persona'}, {'id': 'answer_simple', 'primitive': 'Predict', 'signature': {'name': 'AnswerSimple', 'inputs': ['transcription', 'persona'], 'outputs': ['response']}, 'role': 'direct_answer'}], 'edges': [{'from': 'input', 'to': 'define_persona'}, {'from': 'define_persona', 'to': 'answer_simple'}, {'from': 'answer_simple', 'to': 'output'}], 'scheduler_plan': {'schema_version': 'program-topology-scheduler-plan-v1', 'status': 'deterministic_local_dag_schedule', 'scheduler': 'bounded_ready_queue', 'module_order': ['define_persona', 'answer_simple'], 'declaration_order': ['define_persona', 'answer_simple'], 'output_producers': ['answer_simple'], 'module_readiness': {'define_persona': {'required_inputs': ['persona_intent'], 'produced_outputs': ['persona'], 'inbound_edges': [{'from': 'input', 'to': 'define_persona'}], 'primitive': 'Predict'}, 'answer_simple': {'required_inputs': ['transcription', 'persona'], 'produced_outputs': ['response'], 'inbound_edges': [{'from': 'define_persona', 'to': 'answer_simple'}], 'primitive': 'Predict'}}, 'effect': {'provider_called': False, 'tool_called': False, 'retriever_called': False, 'custom_import_loaded': False, 'authority_mutated': False}}}
TOPOLOGY_EXECUTION_STATUS = 'pipeline_materialized'
MATERIALIZATION_SCOPE = {'topology_declared': True, 'topology_inferred': False, 'topology_materialized': True, 'current_renderer': 'pipeline_topology_renderer'}
SCHEDULER_PLAN = {'schema_version': 'program-topology-scheduler-plan-v1', 'status': 'deterministic_local_dag_schedule', 'scheduler': 'bounded_ready_queue', 'module_order': ['define_persona', 'answer_simple'], 'declaration_order': ['define_persona', 'answer_simple'], 'output_producers': ['answer_simple'], 'module_readiness': {'define_persona': {'required_inputs': ['persona_intent'], 'produced_outputs': ['persona'], 'inbound_edges': [{'from': 'input', 'to': 'define_persona'}], 'primitive': 'Predict'}, 'answer_simple': {'required_inputs': ['transcription', 'persona'], 'produced_outputs': ['response'], 'inbound_edges': [{'from': 'define_persona', 'to': 'answer_simple'}], 'primitive': 'Predict'}}, 'effect': {'provider_called': False, 'tool_called': False, 'retriever_called': False, 'custom_import_loaded': False, 'authority_mutated': False}}
MODULE_ORDER = ['define_persona', 'answer_simple']
MODULE_SIGNATURES = {'define_persona': {'inputs': ['persona_intent'], 'outputs': ['persona']}, 'answer_simple': {'inputs': ['transcription', 'persona'], 'outputs': ['response']}}
MODULE_PRIMITIVES = {'define_persona': 'Predict', 'answer_simple': 'Predict'}
PROGRAM_OUTPUTS = ['response']
EDGES = [{'from': 'input', 'to': 'define_persona'}, {'from': 'define_persona', 'to': 'answer_simple'}, {'from': 'answer_simple', 'to': 'output'}]
PROGRAM_TEMPLATE_VERSION = 'program-candidate-assembly-v1'


def assembly_manifest_path() -> Path:
    return Path(__file__).with_name('manifest.json')


def load_manifest() -> dict[str, Any]:
    path = assembly_manifest_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _current_manifest_hash() -> str:
    path = assembly_manifest_path()
    if not path.exists():
        return ''
    try:
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return ''


def _receipt_manifest_hash() -> str:
    path = Path(str(assembly_manifest_path()) + '.meta.json')
    if not path.exists():
        return ''
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return ''
    if not isinstance(payload, dict):
        return ''
    value = payload.get('hash') or payload.get('output_hash')
    return str(value) if value else ''


def _manifest_hash() -> str:
    return _receipt_manifest_hash() or _current_manifest_hash()


def program_observability_tags() -> dict[str, str]:
    manifest = load_manifest()
    assembly = manifest.get('candidate_assembly')
    if not isinstance(assembly, dict):
        assembly = {}
    tags = {
        'program.name': str(intent_summary().get('name') or ''),
        'program.assembly_id': str(assembly.get('assembly_id') or ''),
        'program.candidate_id': str(assembly.get('candidate_id') or ''),
    }
    manifest_hash = _manifest_hash()
    if manifest_hash:
        tags['program.manifest_hash'] = manifest_hash
    return {key: value for key, value in tags.items() if value}


def configure_observability(
    *,
    run_name: str = 'program-runtime',
    run_kind: str = 'program-runtime',
) -> bool:
    try:
        from dspx.tracing import enable_mlflow_from_env, ensure_run_with_standard_tags, get_mlflow

        enable_mlflow_from_env()
        if get_mlflow() is None:
            return False
        extra_tags = program_observability_tags()
        if run_kind in {'program-runtime', 'program-eval'} and not extra_tags.get('program.assembly_id'):
            return False
        return ensure_run_with_standard_tags(
            'program',
            template_version=PROGRAM_TEMPLATE_VERSION,
            run_name=run_name,
            run_kind=run_kind,
            output_basename='program.py',
            output_hash=_manifest_hash(),
            extra=extra_tags,
        )
    except Exception:
        return False


def _active_mlflow():
    try:
        from dspx.tracing import get_mlflow

        mlflow = get_mlflow()
        if mlflow is None or mlflow.active_run() is None:
            return None
        return mlflow
    except Exception:
        return None


def _set_observability_status(status: str, *, error: Exception | None = None) -> None:
    mlflow = _active_mlflow()
    if mlflow is None:
        return
    try:
        mlflow.set_tag('program.runtime.status', status)
    except Exception:
        pass
    try:
        mlflow.log_metric('program.runtime.error', 1.0 if error is not None else 0.0)
    except Exception:
        pass
    if error is not None:
        try:
            mlflow.set_tag('program.runtime.error_type', type(error).__name__)
        except Exception:
            pass


def end_observability_run(started: bool, *, status: str = 'FINISHED') -> None:
    if not started:
        return
    try:
        from dspx.tracing import get_mlflow

        mlflow = get_mlflow()
        if mlflow is not None:
            try:
                mlflow.end_run(status=status)
            except TypeError:
                mlflow.end_run()
    except Exception:
        pass


def run_with_observability(**inputs: object) -> dspy.Prediction:
    started = configure_observability(run_name='program-runtime', run_kind='program-runtime')
    end_status = 'FINISHED'
    try:
        program = build_program()
        prediction = program(**inputs)
        _set_observability_status('passed')
        return prediction
    except Exception as exc:
        end_status = 'FAILED'
        _set_observability_status('failed', error=exc)
        raise
    finally:
        end_observability_run(started, status=end_status)


def _prediction_mapping(prediction: object) -> dict[str, object]:
    if isinstance(prediction, dict):
        return dict(prediction)
    for method_name in ('toDict', 'to_dict', 'model_dump'):
        method = getattr(prediction, method_name, None)
        if callable(method):
            try:
                payload = method()
            except Exception:
                continue
            if isinstance(payload, dict):
                return dict(payload)
    return {}


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


class VoiceTurnSimpleBrainPipelineProgram(dspy.Module):
    """Composed explicit pipeline topology program."""

    def __init__(self, use_cot: bool = False) -> None:
        super().__init__()
        self.define_persona = DefinePersonaModule(use_cot=use_cot)
        self.answer_simple = AnswerSimpleModule(use_cot=use_cot)

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
                module = getattr(self, module_id)
                kwargs = {name: state[name] for name in signature['inputs']}
                prediction = module(**kwargs)
                executed.add(module_id)
                pending = pending - {module_id}
                progressed = True
                mapped = _prediction_mapping(prediction)
                call_outputs: dict[str, object] = {}
                for output_name in signature['outputs']:
                    if output_name in mapped:
                        state[output_name] = mapped[output_name]
                    elif hasattr(prediction, output_name):
                        state[output_name] = getattr(prediction, output_name)
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
    return VoiceTurnSimpleBrainPipelineProgram()


def build_student(*, use_cot: bool = False) -> dspy.Module:
    return VoiceTurnSimpleBrainPipelineProgram(use_cot=use_cot)


def intent_summary() -> dict[str, object]:
    return {
        'name': 'VoiceTurnSimpleBrain',
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
        'program_class': 'VoiceTurnSimpleBrainPipelineProgram',
    }

import json
from pathlib import Path
from typing import Any

import dspy

from module import io_spec, normalize_output, output_weights

OBJECTIVE = 'Define the requested persona, then answer the spoken transcription directly and concisely.'
CONSTRAINTS = ['Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.', 'Define a concrete persona from persona_intent before answering.', 'Give a direct, concise, factual answer.', 'Do not echo the transcription or persona intent.', 'Return only the response field.', 'load local GEPA optimizer output as the candidate program implementation']
METRIC = 'f1'
PROGRAM_TEMPLATE_VERSION = 'program-candidate-assembly-v1'
GEPA_OPTIMIZER_OUTPUT_DIR = 'gepa_optimizer_output'


def assembly_manifest_path() -> Path:
    return Path(__file__).with_name('manifest.json')


def optimizer_output_path() -> Path:
    return Path(__file__).with_name(GEPA_OPTIMIZER_OUTPUT_DIR)


def load_manifest() -> dict[str, Any]:
    path = assembly_manifest_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _receipt_manifest_hash() -> str:
    path = Path(str(assembly_manifest_path()) + '.meta.json')
    if not path.exists():
        return ''
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return ''
    if not isinstance(payload, dict):
        return ''
    value = payload.get('hash') or payload.get('output_hash')
    return str(value) if value else ''


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _current_manifest_hash() -> str:
    path = assembly_manifest_path()
    return _sha256_file(path) if path.exists() else ''


def _manifest_hash() -> str:
    return _receipt_manifest_hash() or _current_manifest_hash()


def program_observability_tags() -> dict[str, str]:
    manifest = load_manifest()
    assembly = manifest.get('candidate_assembly')
    if not isinstance(assembly, dict):
        assembly = {}
    tags = {
        'program.name': str(intent_summary().get('name') or ''),
        'program.assembly_id': str(assembly.get('assembly_id') or ''),
        'program.candidate_id': str(assembly.get('candidate_id') or ''),
    }
    manifest_hash = _manifest_hash()
    if manifest_hash:
        tags['program.manifest_hash'] = manifest_hash
    return {key: value for key, value in tags.items() if value}


def configure_observability(
    *,
    run_name: str = 'program-runtime',
    run_kind: str = 'program-runtime',
) -> bool:
    try:
        from dspx.tracing import enable_mlflow_from_env, ensure_run_with_standard_tags, get_mlflow

        enable_mlflow_from_env()
        if get_mlflow() is None:
            return False
        extra_tags = program_observability_tags()
        if run_kind in {'program-runtime', 'program-eval'} and not extra_tags.get('program.assembly_id'):
            return False
        return ensure_run_with_standard_tags(
            'program',
            template_version=PROGRAM_TEMPLATE_VERSION,
            run_name=run_name,
            run_kind=run_kind,
            output_basename='program.py',
            output_hash=_manifest_hash(),
            extra=extra_tags,
        )
    except Exception:
        return False


def end_observability_run(started: bool, *, status: str = 'FINISHED') -> None:
    if not started:
        return
    try:
        from dspx.tracing import get_mlflow

        mlflow = get_mlflow()
        if mlflow is not None:
            try:
                mlflow.end_run(status=status)
            except TypeError:
                mlflow.end_run()
    except Exception:
        pass


def _active_mlflow():
    try:
        from dspx.tracing import get_mlflow

        mlflow = get_mlflow()
        if mlflow is None or mlflow.active_run() is None:
            return None
        return mlflow
    except Exception:
        return None


def _set_observability_status(status: str, *, error: Exception | None = None) -> None:
    mlflow = _active_mlflow()
    if mlflow is None:
        return
    try:
        mlflow.set_tag('program.runtime.status', status)
    except Exception:
        pass
    try:
        mlflow.log_metric('program.runtime.error', 1.0 if error is not None else 0.0)
    except Exception:
        pass
    if error is not None:
        try:
            mlflow.set_tag('program.runtime.error_type', type(error).__name__)
        except Exception:
            pass


def _optimizer_payload_inventory(root: Path) -> dict[str, Any]:
    import hashlib

    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise RuntimeError(f'GEPA optimizer output contains symlink: {path}')
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == 'manifest.json':
            continue
        files.append({'path': rel, 'sha256': _sha256_file(path), 'size_bytes': path.stat().st_size})
    tree_text = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return {
        'hash_algorithm': 'sha256',
        'tree_hash': hashlib.sha256(tree_text.encode('utf-8')).hexdigest(),
        'files': files,
    }


def verify_optimizer_output() -> None:
    root = optimizer_output_path()
    manifest_path = root / 'manifest.json'
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise RuntimeError('GEPA optimizer manifest cannot be read before load') from exc
    if not isinstance(manifest, dict):
        raise RuntimeError('GEPA optimizer manifest must be a JSON object before load')
    candidate_manifest = load_manifest()
    gepa_refinement = candidate_manifest.get('gepa_refinement')
    if not isinstance(gepa_refinement, dict):
        raise RuntimeError('GEPA candidate manifest is missing GEPA lineage before load')
    expected_manifest_hash = str(gepa_refinement.get('gepa_optimizer_manifest_sha256') or '')
    if not expected_manifest_hash:
        raise RuntimeError('GEPA candidate manifest is missing optimizer manifest hash before load')
    if _sha256_file(manifest_path) != expected_manifest_hash:
        raise RuntimeError('GEPA optimizer manifest hash changed before load')
    declared = manifest.get('output_payload')
    if not isinstance(declared, dict) or declared.get('hash_algorithm') != 'sha256':
        raise RuntimeError('GEPA optimizer payload inventory is missing before load')
    actual = _optimizer_payload_inventory(root)
    declared_files = declared.get('files')
    if not isinstance(declared_files, list) or not declared_files:
        raise RuntimeError('GEPA optimizer payload inventory is empty before load')
    declared_by_path = {str(item.get('path')): item for item in declared_files if isinstance(item, dict)}
    actual_by_path = {str(item['path']): item for item in actual['files']}
    if set(declared_by_path) != set(actual_by_path):
        raise RuntimeError('GEPA optimizer payload file set changed before load')
    for rel, actual_item in actual_by_path.items():
        declared_item = declared_by_path[rel]
        if declared_item.get('sha256') != actual_item.get('sha256'):
            raise RuntimeError('GEPA optimizer payload hash changed before load')
        if declared_item.get('size_bytes') != actual_item.get('size_bytes'):
            raise RuntimeError('GEPA optimizer payload size changed before load')
    if declared.get('tree_hash') != actual.get('tree_hash'):
        raise RuntimeError('GEPA optimizer payload tree hash changed before load')


def build_program() -> dspy.Module:
    verify_optimizer_output()
    return dspy.load(str(optimizer_output_path()), allow_pickle=True)


def build_student(*, use_cot: bool = False) -> dspy.Module:
    _ = use_cot
    return build_program()


def run_with_observability(**inputs: object) -> dspy.Prediction:
    started = configure_observability(run_name='program-runtime', run_kind='program-runtime')
    end_status = 'FINISHED'
    try:
        prediction = build_program()(**inputs)
        _set_observability_status('passed')
        return prediction
    except Exception as exc:
        end_status = 'FAILED'
        _set_observability_status('failed', error=exc)
        raise
    finally:
        end_observability_run(started, status=end_status)


def intent_summary() -> dict[str, object]:
    return {
        'name': 'VoiceTurnSimpleBrain',
        'objective': OBJECTIVE,
        'constraints': list(CONSTRAINTS),
        'metric': METRIC,
        'io': io_spec(),
        'materialization_scope': {
            'topology_materialized': True,
            'current_renderer': 'gepa_optimizer_output_loader',
        },
    }
