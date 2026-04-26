from __future__ import annotations

from typing import Any

from dspx.dtos import ModuleSpec, SignatureGenRequest
from dspx.services.program_contracts import (
    intent_field_specs,
    intent_surface_names,
    sanitize_ident,
    surface_description,
)
from dspx.services.program_topology import (
    has_declared_pipeline_topology,
    render_pipeline_module_surface,
    render_pipeline_program_code,
    render_pipeline_signature_surface,
)


def render_signature_surface(intent: Any) -> tuple[str, dict[str, Any]]:
    """Render the signature surface through the signature generation service."""

    if has_declared_pipeline_topology(intent):
        return render_pipeline_signature_surface(intent)

    from dspx.services.signatures_service import run_generate_dto

    names = intent_surface_names(intent)
    result = run_generate_dto(
        SignatureGenRequest(
            prompt=surface_description(intent.objective),
            template_version=str(
                intent.options.get("signature_template_version") or "simple-v1"
            ),
            options={
                "class_name": names["signature_class"],
                "inputs": list(intent.inputs or ["context"]),
                "outputs": list(intent.outputs or ["output"]),
                "input_fields": intent_field_specs(intent, role="input"),
                "output_fields": intent_field_specs(intent, role="output"),
                "run_kind": "program-signature-surface",
            },
        )
    )
    return result.code, dict(result.metadata or {})


def render_module_surface(intent: Any) -> tuple[str, dict[str, Any]]:
    """Render the module surface through the module generation service."""

    if has_declared_pipeline_topology(intent):
        return render_pipeline_module_surface(intent)

    from dspx.services.module_service import run_generate as run_module_generate

    names = intent_surface_names(intent)
    artifact = run_module_generate(
        ModuleSpec(
            name=names["module_class"],
            description=surface_description(intent.objective),
            inputs=list(intent.inputs or ["context"]),
            outputs=list(intent.outputs or ["output"]),
            options={
                "template_version": str(
                    intent.options.get("module_template_version") or "simple-v1"
                ),
                "signature_class_name": names["signature_class"],
            },
        ),
        use_signature=True,
    )
    return artifact.code, dict(artifact.metadata or {})


def render_program_code(intent: Any) -> str:
    """Render the program assembly surface that composes generated surfaces."""

    if has_declared_pipeline_topology(intent):
        return render_pipeline_program_code(intent)

    names = intent_surface_names(intent)
    constraints = list(intent.constraints)
    metric = intent.metric or "unspecified"
    declared_topology = dict(intent.topology or {})
    topology_execution_status = str(
        declared_topology.get("execution_status")
        or "single_module_scaffold_materialized"
    )
    materialization_scope = {
        "topology_declared": bool(declared_topology),
        "topology_materialized": not bool(declared_topology),
        "current_renderer": "single_module_scaffold",
    }

    lines: list[str] = [
        "from __future__ import annotations",
        "",
        "import dspy",
        "",
        "from module import (",
        "    build_student as build_module_student,",
        "    io_spec,",
        "    normalize_output,",
        "    output_weights,",
        ")",
        "",
        f"OBJECTIVE = {intent.objective!r}",
        f"CONSTRAINTS = {constraints!r}",
        f"METRIC = {metric!r}",
        f"DECLARED_TOPOLOGY = {declared_topology!r}",
        f"TOPOLOGY_EXECUTION_STATUS = {topology_execution_status!r}",
        f"MATERIALIZATION_SCOPE = {materialization_scope!r}",
        "",
        "",
        "def build_program() -> dspy.Module:",
        "    return build_module_student()",
        "",
        "",
        "def build_student(*, use_cot: bool = False) -> dspy.Module:",
        "    return build_module_student(use_cot=use_cot)",
        "",
        "",
        "def intent_summary() -> dict[str, object]:",
        "    return {",
        f"        'name': {intent.name!r},",
        "        'objective': OBJECTIVE,",
        "        'constraints': list(CONSTRAINTS),",
        "        'metric': METRIC,",
        "        'io': io_spec(),",
        "        'declared_topology': dict(DECLARED_TOPOLOGY),",
        "        'topology_execution_status': TOPOLOGY_EXECUTION_STATUS,",
        "        'materialization_scope': dict(MATERIALIZATION_SCOPE),",
        f"        'signature_class': {names['signature_class']!r},",
        f"        'module_class': {names['module_class']!r},",
        "    }",
        "",
    ]
    return "\n".join(lines)


def render_eval_smoke(intent: Any) -> str:
    program_class = sanitize_ident(intent.name)
    sample_inputs = {name: f"sample_{name}" for name in intent.inputs}
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "from program import build_program, intent_summary, io_spec",
            "",
            "",
            "def main() -> None:",
            "    program = build_program()",
            "    assert program is not None",
            f"    assert io_spec()['inputs'] == {list(intent.inputs)!r}",
            f"    assert io_spec()['outputs'] == {list(intent.outputs)!r}",
            "    assert intent_summary()['objective']",
            f"    print('program smoke ok: {program_class}')",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
            f"SAMPLE_INPUTS = {sample_inputs!r}",
        ]
    )


def render_eval_examples(intent: Any) -> str:
    """Render a deterministic examples behavior-evidence harness."""

    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import json",
            "from pathlib import Path",
            "from typing import Any",
            "",
            "from program import build_program, intent_summary, io_spec, normalize_output",
            "",
            "RESULT_PATH = Path('behavior_results.json')",
            "",
            "",
            "def _mapping_for(example: dict[str, object], role: str) -> dict[str, object]:",
            "    nested = example.get(role)",
            "    if isinstance(nested, dict):",
            "        return dict(nested)",
            "    return example",
            "",
            "",
            "def _jsonable(value: object) -> object:",
            "    if value is None or isinstance(value, (str, int, float, bool)):",
            "        return value",
            "    if isinstance(value, dict):",
            "        return {str(key): _jsonable(item) for key, item in value.items()}",
            "    if isinstance(value, (list, tuple)):",
            "        return [_jsonable(item) for item in value]",
            "    return str(value)",
            "",
            "",
            "def _prediction_mapping(prediction: object) -> dict[str, object]:",
            "    if isinstance(prediction, dict):",
            "        return dict(prediction)",
            "    for method_name in ('toDict', 'to_dict', 'model_dump'):",
            "        method = getattr(prediction, method_name, None)",
            "        if callable(method):",
            "            try:",
            "                payload = method()",
            "            except Exception:",
            "                continue",
            "            if isinstance(payload, dict):",
            "                return dict(payload)",
            "    return {}",
            "",
            "",
            "def _observed_outputs(prediction: object, outputs: list[str]) -> tuple[dict[str, object], list[str]]:",
            "    observed: dict[str, object] = {}",
            "    notes: list[str] = []",
            "    mapped = _prediction_mapping(prediction)",
            "    for name in outputs:",
            "        if name in mapped:",
            "            observed[name] = mapped[name]",
            "        elif hasattr(prediction, name):",
            "            observed[name] = getattr(prediction, name)",
            "    if not observed:",
            "        notes.append('prediction exposed no declared output fields')",
            "    return observed, notes",
            "",
            "",
            "def _status_for(",
            "    outputs: list[str],",
            "    expected: dict[str, object],",
            "    observed: dict[str, object],",
            "    prediction: object,",
            ") -> tuple[str, list[str]]:",
            "    comparable = [name for name in outputs if name in observed]",
            "    if not comparable:",
            "        return 'degraded_no_comparable_output', ['no declared outputs were observable']",
            "    failures: list[str] = []",
            "    for name in comparable:",
            "        gold, pred = normalize_output(",
            "            name, str(expected.get(name, '')), str(observed.get(name, '')), pred_trace=prediction",
            "        )",
            "        if gold != pred:",
            "            failures.append(name)",
            "    if failures:",
            "        return 'failed', [f'output mismatch: {failures}']",
            "    if len(comparable) != len(outputs):",
            "        missing = [name for name in outputs if name not in observed]",
            "        return 'executed', [f'missing non-compared outputs: {missing}']",
            "    return 'passed', []",
            "",
            "",
            "def _summary(records: list[dict[str, object]]) -> dict[str, object]:",
            "    statuses = [str(record.get('status') or 'unknown') for record in records]",
            "    counts = {status: statuses.count(status) for status in sorted(set(statuses))}",
            "    error_count = sum(1 for status in statuses if status == 'error')",
            "    failed_count = sum(1 for status in statuses if status == 'failed')",
            "    degraded_count = sum(1 for status in statuses if status.startswith('degraded'))",
            "    passed_count = sum(1 for status in statuses if status == 'passed')",
            "    if records and passed_count == len(records):",
            "        episode_status = 'passed'",
            "    elif error_count == len(records):",
            "        episode_status = 'error'",
            "    elif failed_count:",
            "        episode_status = 'failed'",
            "    elif degraded_count:",
            "        episode_status = 'degraded'",
            "    else:",
            "        episode_status = 'executed'",
            "    return {",
            "        'total': len(records),",
            "        'passed': passed_count,",
            "        'failed': failed_count,",
            "        'error': error_count,",
            "        'degraded': degraded_count,",
            "        'status_counts': counts,",
            "        'status': episode_status,",
            "    }",
            "",
            "",
            "def _configure_provider() -> dict[str, object]:",
            "    try:",
            "        import dspy",
            "        from dspx.provider_registry import create_from_env, ensure_default_providers",
            "",
            "        ensure_default_providers()",
            "        lm = create_from_env(default='stub')",
            "        dspy.configure(lm=lm)",
            "        return {'status': 'configured', 'provider': getattr(lm, 'model', type(lm).__name__)}",
            "    except Exception as exc:",
            "        return {'status': 'unavailable', 'error': {'type': type(exc).__name__, 'message': str(exc)}}",
            "",
            "",
            "def main() -> None:",
            "    examples = json.loads(Path('examples.json').read_text(encoding='utf-8'))",
            "    assert isinstance(examples, list)",
            "    spec = io_spec()",
            "    inputs = list(spec['inputs'])",
            "    outputs = list(spec['outputs'])",
            "    provider = _configure_provider()",
            "    program = build_program()",
            "    records: list[dict[str, object]] = []",
            "    for index, example in enumerate(examples):",
            "        assert isinstance(example, dict), f'example {index} must be an object'",
            "        input_values = _mapping_for(example, 'inputs')",
            "        output_values = _mapping_for(example, 'outputs')",
            "        missing_inputs = [name for name in inputs if name not in input_values]",
            "        missing_outputs = [name for name in outputs if name not in output_values]",
            "        assert not missing_inputs, f'example {index} missing inputs: {missing_inputs}'",
            "        assert not missing_outputs, f'example {index} missing outputs: {missing_outputs}'",
            "        record: dict[str, object] = {",
            "            'index': index,",
            "            'inputs': _jsonable(input_values),",
            "            'expected_outputs': _jsonable(output_values),",
            "        }",
            "        try:",
            "            prediction = program(**{name: input_values[name] for name in inputs})",
            "            observed, notes = _observed_outputs(prediction, outputs)",
            "            status, status_notes = _status_for(outputs, output_values, observed, prediction)",
            "            record.update(",
            "                {",
            "                    'status': status,",
            "                    'observed_outputs': _jsonable(observed),",
            "                    'notes': notes + status_notes,",
            "                }",
            "            )",
            "        except Exception as exc:",
            "            record.update(",
            "                {",
            "                    'status': 'error',",
            "                    'observed_outputs': {},",
            "                    'error': {'type': type(exc).__name__, 'message': str(exc)},",
            "                }",
            "            )",
            "        records.append(record)",
            "    payload: dict[str, Any] = {",
            "        'schema_version': 'program-behavior-results-v1',",
            "        'intent': intent_summary(),",
            "        'intent_name': intent_summary().get('name'),",
            "        'input_fields': inputs,",
            "        'output_fields': outputs,",
            "        'provider': provider,",
            "        'examples': records,",
            "        'summary': _summary(records),",
            "        'authority': 'behavior_evidence_only_non_authoritative',",
            "    }",
            "    RESULT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')",
            '    print(f\'program examples ok: {len(examples)} example(s); behavior status: {payload["summary"]["status"]}\')',
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )


def render_eval_jury() -> str:
    """Render a deterministic jury artifact binding validation harness."""

    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import json",
            "from pathlib import Path",
            "",
            "",
            "def _load(name: str) -> dict[str, object]:",
            "    payload = json.loads(Path(name).read_text(encoding='utf-8'))",
            "    assert isinstance(payload, dict), f'{name} must contain an object'",
            "    return payload",
            "",
            "",
            "def main() -> None:",
            "    jury = _load('jury.json')",
            "    selection = _load('jury_selection.json')",
            "    rubric = _load('jury_rubric.json')",
            "    assert jury['schema_version'] == 'program-jury-v1'",
            "    assert selection['schema_version'] == 'program-jury-selection-v1'",
            "    assert rubric['schema_version'] == 'program-jury-rubric-v1'",
            "    selected = selection.get('selected_jurors')",
            "    rubrics = rubric.get('juror_rubrics')",
            "    assert isinstance(selected, list)",
            "    assert isinstance(rubrics, list)",
            "    assert len(selected) == len(rubrics)",
            "    selected_ids = {item.get('id') for item in selected if isinstance(item, dict)}",
            "    rubric_ids = {item.get('juror_id') for item in rubrics if isinstance(item, dict)}",
            "    assert selected_ids == rubric_ids",
            "    assert selection['authority'] == 'selection_contract_only_non_authoritative'",
            "    assert rubric['authority'] == 'rubric_contract_only_non_authoritative'",
            "    print(f'program jury artifacts ok: {len(selected_ids)} selected juror(s)')",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )


def render_eval_promotion() -> str:
    """Render a deterministic promotion artifact binding validation harness."""

    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import json",
            "from pathlib import Path",
            "",
            "",
            "def _load(name: str) -> dict[str, object]:",
            "    payload = json.loads(Path(name).read_text(encoding='utf-8'))",
            "    assert isinstance(payload, dict), f'{name} must contain an object'",
            "    return payload",
            "",
            "",
            "def main() -> None:",
            "    review = _load('promotion_review.json')",
            "    request = _load('promotion_adjudication_request.json')",
            "    decision_template = _load('promotion_decision_template.json')",
            "    assert review['schema_version'] == 'program-promotion-review-v1'",
            "    assert request['schema_version'] == 'program-promotion-adjudication-request-v1'",
            "    assert decision_template['schema_version'] == 'program-promotion-decision-v1'",
            "    assert review['promotion_state'] == 'not_promoted'",
            "    assert review['decision']['status'] == 'pending'",
            "    assert request['adjudicator'] == review['adjudicator']",
            "    assert request['external_authority'] == review['external_authority']",
            "    assert request['decision_record_template'] == decision_template",
            "    assert decision_template['status'] == 'pending'",
            "    assert decision_template['decided_by'] is None",
            "    assert request['authority'] == 'adjudication_request_only_non_authoritative'",
            "    blockers = review.get('blocking_conditions')",
            "    missing = request.get('missing_required_evidence')",
            "    assert isinstance(blockers, list)",
            "    assert isinstance(missing, list)",
            "    assert missing == blockers",
            "    if blockers:",
            "        assert request['status'] == 'not_ready_blocked'",
            "    assert review['non_authority']['automatic_promotion'] is False",
            "    assert review['non_authority']['ranking_pruning_promotion'] is False",
            "    assert review['non_authority']['external_authority_export'] is False",
            "    print(f'program promotion artifacts ok: {request[\"status\"]}')",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )
