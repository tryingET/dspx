from __future__ import annotations

from typing import Any, Mapping

from dspx.services.program_contracts import sanitize_ident, surface_description

PIPELINE_MATERIALIZED_STATUS = "pipeline_materialized"
SUPPORTED_PIPELINE_PRIMITIVES = {"Predict", "ChainOfThought"}


class ProgramTopologyMaterializationError(ValueError):
    """Raised when a declared topology cannot be safely materialized."""


def declared_pipeline_topology(intent: Any) -> dict[str, Any]:
    topology = dict(getattr(intent, "topology", {}) or {})
    if topology.get("kind") != "pipeline":
        return {}
    return topology


def has_declared_pipeline_topology(intent: Any) -> bool:
    return bool(declared_pipeline_topology(intent))


def _module_signature(module: Mapping[str, Any]) -> dict[str, Any]:
    signature = module.get("signature")
    return dict(signature) if isinstance(signature, Mapping) else {}


def validate_materializable_pipeline_topology(intent: Any) -> dict[str, Any]:
    """Return the normalized pipeline topology or fail for unsupported execution."""

    topology = declared_pipeline_topology(intent)
    if not topology:
        return {}
    modules = [
        dict(item) for item in topology.get("modules", []) if isinstance(item, Mapping)
    ]
    if not modules:
        raise ProgramTopologyMaterializationError(
            "pipeline topology materialization requires at least one module"
        )
    unsupported = sorted(
        {
            str(module.get("primitive") or "")
            for module in modules
            if str(module.get("primitive") or "") not in SUPPORTED_PIPELINE_PRIMITIVES
        }
    )
    if unsupported:
        allowed = ", ".join(sorted(SUPPORTED_PIPELINE_PRIMITIVES))
        raise ProgramTopologyMaterializationError(
            "pipeline topology materialization supports only module primitives "
            f"{allowed}; unsupported primitives: {unsupported}"
        )
    signature_names = [
        str(_module_signature(module).get("name") or "") for module in modules
    ]
    if len(set(signature_names)) != len(signature_names):
        raise ProgramTopologyMaterializationError(
            "pipeline topology materialization requires unique signature.name values"
        )
    module_class_names = [module_class_name(module) for module in modules]
    if len(set(module_class_names)) != len(module_class_names):
        raise ProgramTopologyMaterializationError(
            "pipeline topology materialization requires unique generated module class names"
        )
    edges = [
        dict(item) for item in topology.get("edges", []) if isinstance(item, Mapping)
    ]
    for edge in edges:
        when = edge.get("when")
        if when is None:
            continue
        if not isinstance(when, Mapping):
            raise ProgramTopologyMaterializationError(
                "pipeline topology supports only simple when.field/equals routing clauses"
            )
        if set(when) - {"field", "equals"}:
            raise ProgramTopologyMaterializationError(
                "pipeline topology supports only simple when.field/equals routing clauses"
            )
    return topology


def materializes_pipeline_topology(intent: Any) -> bool:
    if not has_declared_pipeline_topology(intent):
        return False
    validate_materializable_pipeline_topology(intent)
    return True


def materialized_pipeline_topology(intent: Any) -> dict[str, Any]:
    topology = validate_materializable_pipeline_topology(intent)
    if not topology:
        return {}
    materialized = dict(topology)
    materialized["execution_status"] = PIPELINE_MATERIALIZED_STATUS
    return materialized


def module_class_name(module: Mapping[str, Any]) -> str:
    signature = _module_signature(module)
    return f"{sanitize_ident(str(signature.get('name') or module.get('id')))}Module"


def _signature_class_name(module: Mapping[str, Any]) -> str:
    signature = _module_signature(module)
    return sanitize_ident(str(signature.get("name") or module.get("id")))


def _signature_inputs(module: Mapping[str, Any]) -> list[str]:
    signature = _module_signature(module)
    return [str(item) for item in signature.get("inputs", [])]


def _signature_outputs(module: Mapping[str, Any]) -> list[str]:
    signature = _module_signature(module)
    return [str(item) for item in signature.get("outputs", [])]


def _module_id(module: Mapping[str, Any]) -> str:
    return str(module.get("id") or "")


def _field_line(name: str, *, role: str) -> str:
    field_factory = "InputField" if role == "input" else "OutputField"
    desc = f"{name.replace('_', ' ')} ({role})"
    return f"    {name}: str = dspy.{field_factory}(desc={desc!r})"


def render_pipeline_signature_surface(intent: Any) -> tuple[str, dict[str, Any]]:
    topology = validate_materializable_pipeline_topology(intent)
    modules = [dict(item) for item in topology.get("modules", [])]
    lines = ["import dspy", ""]
    for index, module in enumerate(modules):
        signature_name = _signature_class_name(module)
        role = str(module.get("role") or getattr(intent, "objective", ""))
        doc = surface_description(role or getattr(intent, "objective", ""))
        lines.extend(
            [
                f"class {signature_name}(dspy.Signature):",
                f'    """{doc}"""',
                "",
            ]
        )
        lines.extend(
            _field_line(name, role="input") for name in _signature_inputs(module)
        )
        lines.extend(
            _field_line(name, role="output") for name in _signature_outputs(module)
        )
        if index != len(modules) - 1:
            lines.extend(["", ""])
    lines.append("")
    return "\n".join(lines), {
        "topology_materialized": True,
        "topology_kind": "pipeline",
        "signature_classes": [_signature_class_name(module) for module in modules],
    }


def render_pipeline_module_surface(intent: Any) -> tuple[str, dict[str, Any]]:
    topology = validate_materializable_pipeline_topology(intent)
    modules = [dict(item) for item in topology.get("modules", [])]
    signature_names = [_signature_class_name(module) for module in modules]
    lines: list[str] = ["import dspy", "", "from signature import ("]
    lines.extend(f"    {name}," for name in signature_names)
    lines.extend([")", ""])
    for index, module in enumerate(modules):
        signature_name = _signature_class_name(module)
        class_name = module_class_name(module)
        primitive = str(module.get("primitive") or "Predict")
        doc = surface_description(
            str(module.get("role") or getattr(intent, "objective", ""))
        )
        input_names = _signature_inputs(module)
        input_params = ", ".join(f"{name}: str" for name in input_names)
        call_args = ", ".join(f"{name}={name}" for name in input_names)
        lines.extend(
            [
                f"class {class_name}(dspy.Module):",
                f'    """{doc}"""',
                "",
                "    def __init__(self, use_cot: bool = False) -> None:",
                "        super().__init__()",
                f"        self.predict = dspy.{primitive}({signature_name})",
                "",
                f"    def forward(self, {input_params}) -> dspy.Prediction:",
                f"        return self.predict({call_args})",
            ]
        )
        if index != len(modules) - 1:
            lines.extend(["", ""])
    lines.extend(
        [
            "",
            "",
            "def build_modules(*, use_cot: bool = False) -> dict[str, dspy.Module]:",
            '    """Construct the generated topology module instances."""',
            "    return {",
        ]
    )
    lines.extend(
        f"        {_module_id(module)!r}: {module_class_name(module)}(use_cot=use_cot),"
        for module in modules
    )
    lines.extend(
        [
            "    }",
            "",
            "",
            "def io_spec() -> dict[str, list[str]]:",
            '    """Return the declared program IO contract."""',
            f"    return {{'inputs': {list(getattr(intent, 'inputs', []))!r}, 'outputs': {list(getattr(intent, 'outputs', []))!r}}}",
            "",
            "",
            "def output_weights() -> dict[str, float]:",
            '    """Provide deterministic output weighting for evaluation."""',
            "    return {",
        ]
    )
    lines.extend(f"        {name!r}: 1.0," for name in getattr(intent, "outputs", []))
    lines.extend(
        [
            "    }",
            "",
            "",
            "def normalize_output(",
            "    key: str,",
            "    gold: str,",
            "    pred: str,",
            "    pred_name: str | None = None,",
            "    pred_trace: object | None = None,",
            ") -> tuple[str, str]:",
            '    """Normalize gold/pred pairs for deterministic checks."""',
            "    return gold, pred",
            "",
        ]
    )
    return "\n".join(lines), {
        "topology_materialized": True,
        "topology_kind": "pipeline",
        "module_classes": [module_class_name(module) for module in modules],
    }


def render_pipeline_program_code(intent: Any) -> str:
    topology = validate_materializable_pipeline_topology(intent)
    modules = [dict(item) for item in topology.get("modules", [])]
    module_classes = [module_class_name(module) for module in modules]
    program_class = (
        f"{sanitize_ident(getattr(intent, 'name', 'IntentProgram'))}PipelineProgram"
    )
    constraints = list(getattr(intent, "constraints", []))
    metric = getattr(intent, "metric", None) or "unspecified"
    materialization_scope = {
        "topology_declared": True,
        "topology_materialized": True,
        "current_renderer": "pipeline_topology_renderer",
    }
    module_signatures = {
        _module_id(module): {
            "inputs": _signature_inputs(module),
            "outputs": _signature_outputs(module),
        }
        for module in modules
    }
    lines: list[str] = [
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "import dspy",
        "",
        "from module import (",
    ]
    lines.extend(f"    {name}," for name in module_classes)
    lines.extend(
        [
            "    io_spec,",
            "    normalize_output,",
            "    output_weights,",
            ")",
            "",
            f"OBJECTIVE = {getattr(intent, 'objective', '')!r}",
            f"CONSTRAINTS = {constraints!r}",
            f"METRIC = {metric!r}",
            f"DECLARED_TOPOLOGY = {topology!r}",
            f"MATERIALIZED_TOPOLOGY = {materialized_pipeline_topology(intent)!r}",
            f"TOPOLOGY_EXECUTION_STATUS = {PIPELINE_MATERIALIZED_STATUS!r}",
            f"MATERIALIZATION_SCOPE = {materialization_scope!r}",
            f"MODULE_ORDER = {[_module_id(module) for module in modules]!r}",
            f"MODULE_SIGNATURES = {module_signatures!r}",
            f"EDGES = {list(topology.get('edges', []))!r}",
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
            "def _edge_condition_matches(edge: dict[str, object], state: dict[str, object]) -> bool:",
            "    when = edge.get('when')",
            "    if not isinstance(when, dict):",
            "        return True",
            "    field = str(when.get('field') or '')",
            "    return str(state.get(field, '')) == str(when.get('equals'))",
            "",
            "",
            "def _edge_source_ready(edge: dict[str, object], executed: set[str]) -> bool:",
            "    source = str(edge.get('from') or '')",
            "    return source == 'input' or source in executed",
            "",
            "",
            "def _module_ready(module_id: str, state: dict[str, object], executed: set[str]) -> bool:",
            "    inputs = list(MODULE_SIGNATURES[module_id]['inputs'])",
            "    if any(name not in state for name in inputs):",
            "        return False",
            "    inbound = [edge for edge in EDGES if edge.get('to') == module_id]",
            "    if not inbound:",
            "        return False",
            "    return any(",
            "        _edge_source_ready(edge, executed) and _edge_condition_matches(edge, state)",
            "        for edge in inbound",
            "    )",
            "",
            "",
            f"class {program_class}(dspy.Module):",
            '    """Composed explicit pipeline topology program."""',
            "",
            "    def __init__(self, use_cot: bool = False) -> None:",
            "        super().__init__()",
        ]
    )
    lines.extend(
        f"        self.{_module_id(module)} = {module_class_name(module)}(use_cot=use_cot)"
        for module in modules
    )
    forward_params = ", ".join(f"{name}: str" for name in getattr(intent, "inputs", []))
    state_payload = ", ".join(
        f"{name!r}: {name}" for name in getattr(intent, "inputs", [])
    )
    output_payload = ", ".join(
        f"{name}=_jsonable(state.get({name!r}, ''))"
        for name in getattr(intent, "outputs", [])
    )
    lines.extend(
        [
            "",
            f"    def forward(self, {forward_params}) -> dspy.Prediction:",
            f"        state: dict[str, object] = {{{state_payload}}}",
            "        executed: set[str] = set()",
            "        for module_id in MODULE_ORDER:",
            "            if not _module_ready(module_id, state, executed):",
            "                continue",
            "            signature = MODULE_SIGNATURES[module_id]",
            "            module = getattr(self, module_id)",
            "            kwargs = {name: state[name] for name in signature['inputs']}",
            "            prediction = module(**kwargs)",
            "            executed.add(module_id)",
            "            mapped = _prediction_mapping(prediction)",
            "            for output_name in signature['outputs']:",
            "                if output_name in mapped:",
            "                    state[output_name] = mapped[output_name]",
            "                elif hasattr(prediction, output_name):",
            "                    state[output_name] = getattr(prediction, output_name)",
            f"        return dspy.Prediction({output_payload})",
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
            "def build_program() -> dspy.Module:",
            f"    return {program_class}()",
            "",
            "",
            "def build_student(*, use_cot: bool = False) -> dspy.Module:",
            f"    return {program_class}(use_cot=use_cot)",
            "",
            "",
            "def intent_summary() -> dict[str, object]:",
            "    return {",
            f"        'name': {getattr(intent, 'name', '')!r},",
            "        'objective': OBJECTIVE,",
            "        'constraints': list(CONSTRAINTS),",
            "        'metric': METRIC,",
            "        'io': io_spec(),",
            "        'declared_topology': dict(DECLARED_TOPOLOGY),",
            "        'materialized_topology': dict(MATERIALIZED_TOPOLOGY),",
            "        'topology_execution_status': TOPOLOGY_EXECUTION_STATUS,",
            "        'materialization_scope': dict(MATERIALIZATION_SCOPE),",
            "        'module_order': list(MODULE_ORDER),",
            f"        'program_class': {program_class!r},",
            "    }",
            "",
        ]
    )
    return "\n".join(lines)
