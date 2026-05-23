from __future__ import annotations

from typing import Any, Mapping
import re

from dspx.services.program_capabilities import (
    is_pipeline_module_materializable,
    materializable_pipeline_primitives,
    normalize_inline_retriever_config,
)
from dspx.services.program_contracts import sanitize_ident, surface_description

PIPELINE_MATERIALIZED_STATUS = "pipeline_materialized"
PROMPT_INFERRED_PIPELINE_RENDERER = "prompt_inferred_pipeline_renderer"
SUPPORTED_PIPELINE_PRIMITIVES = materializable_pipeline_primitives()
_REASONING_CUES = {
    "adjudicate",
    "analyse",
    "analyze",
    "assess",
    "compare",
    "critique",
    "derive",
    "diagnose",
    "evaluate",
    "explain",
    "infer",
    "judge",
    "multi-step",
    "plan",
    "rationale",
    "reason",
    "review",
    "strategy",
    "synthesize",
}
_ROUTING_CUES = {"classify", "dispatch", "route", "triage"}
_GENERATION_CUES = {"answer", "draft", "recommend", "respond", "response"}
_EXTRACT_CUES = {"extract", "parse", "summarize", "summarise"}
_VALIDATE_CUES = {"check", "validate", "verify"}


class ProgramTopologyMaterializationError(ValueError):
    """Raised when a declared topology cannot be safely materialized."""


def declared_pipeline_topology(intent: Any) -> dict[str, Any]:
    topology = dict(getattr(intent, "topology", {}) or {})
    if topology.get("kind") != "pipeline":
        return {}
    return topology


def has_declared_pipeline_topology(intent: Any) -> bool:
    return bool(declared_pipeline_topology(intent))


def _objective_tokens(intent: Any) -> set[str]:
    text = " ".join(
        str(part or "")
        for part in [
            getattr(intent, "objective", ""),
            getattr(intent, "task_type", ""),
            " ".join(str(item) for item in getattr(intent, "constraints", []) or []),
        ]
    ).casefold()
    words = set(re.findall(r"[a-z][a-z0-9_\-]*", text))
    if "step" in words and "by" in words:
        words.add("step-by-step")
    if "multi" in words and "step" in words:
        words.add("multi-step")
    return words


def _module_inference_enabled(intent: Any) -> bool:
    options = getattr(intent, "options", {}) or {}
    if not isinstance(options, Mapping):
        return True
    if "module_inference" not in options and "prompt_module_inference" not in options:
        if bool(options.get("focused_json_bundle_runtime")):
            return False
    raw = options.get("module_inference", options.get("prompt_module_inference", True))
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().casefold() not in {"0", "false", "no", "off", "none"}


def _pascal_name(value: str, *, fallback: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value) if part]
    if not parts:
        return fallback
    return sanitize_ident(
        "".join(part[:1].upper() + part[1:] for part in parts), fallback=fallback
    )


def _signature(
    name: str, *, inputs: list[str], outputs: list[str]
) -> dict[str, list[str] | str]:
    return {"name": name, "inputs": list(inputs), "outputs": list(outputs)}


def _with_intermediate(inputs: list[str], name: str) -> list[str]:
    return [*inputs, *([] if name in inputs else [name])]


def _prompt_inference_notes(reason: str) -> list[str]:
    return [
        "No explicit topology was declared; program-gen inferred a bounded generated module topology from the objective/task wording.",
        reason,
        "Inference is deterministic, local, and limited to generated Predict/ChainOfThought modules; no custom Python imports, tools, external retrievers, ReAct, ranking, promotion, or external authority mutation are performed.",
    ]


def prompt_inferred_pipeline_topology(intent: Any) -> dict[str, Any]:
    """Infer a safe generated module topology from the user intent.

    This is deliberately conservative: it only upgrades no-topology intents from the
    default Predict scaffold to generated Predict/ChainOfThought pipeline modules
    when the prompt contains clear routing, extraction/validation, or reasoning
    cues. It does not infer arbitrary custom imports or non-supported DSPy
    primitives.
    """

    if getattr(intent, "topology", {}) or not _module_inference_enabled(intent):
        return {}
    tokens = _objective_tokens(intent)
    inputs = [str(item) for item in getattr(intent, "inputs", []) or ["context"]]
    outputs = [str(item) for item in getattr(intent, "outputs", []) or ["output"]]
    first_output = outputs[0]

    if tokens & _ROUTING_CUES and tokens & _GENERATION_CUES:
        final_id = f"produce_{first_output}"
        return {
            "kind": "pipeline",
            "execution_status": "prompt_inferred_not_materialized",
            "origin": "prompt_inferred",
            "inference_reason": "routing/generation cues favor a generated classifier plus reasoned output module over a single Predict scaffold.",
            "modules": [
                {
                    "id": "classify_route",
                    "primitive": "Predict",
                    "signature": _signature(
                        "ClassifyRoute",
                        inputs=inputs,
                        outputs=["route"],
                    ),
                    "role": "Classify the input into the most useful route before generating the final output.",
                },
                {
                    "id": final_id,
                    "primitive": "ChainOfThought",
                    "signature": _signature(
                        _pascal_name(final_id, fallback="ProduceOutput"),
                        inputs=_with_intermediate(inputs, "route"),
                        outputs=outputs,
                    ),
                    "role": "Use the route and original inputs to produce the requested output with reasoning.",
                },
            ],
            "edges": [
                {"from": "input", "to": "classify_route"},
                {"from": "classify_route", "to": final_id},
                {"from": final_id, "to": "output"},
            ],
            "notes": _prompt_inference_notes(
                "Detected routing plus generation cues in the prompt."
            ),
        }

    if tokens & _EXTRACT_CUES and tokens & _VALIDATE_CUES:
        final_id = f"validate_{first_output}"
        return {
            "kind": "pipeline",
            "execution_status": "prompt_inferred_not_materialized",
            "origin": "prompt_inferred",
            "inference_reason": "extract/validate cues favor an extraction module plus a reasoned validation/output module over a single Predict scaffold.",
            "modules": [
                {
                    "id": "extract_evidence",
                    "primitive": "Predict",
                    "signature": _signature(
                        "ExtractEvidence",
                        inputs=inputs,
                        outputs=["evidence"],
                    ),
                    "role": "Extract the evidence needed by the final generated program output.",
                },
                {
                    "id": final_id,
                    "primitive": "ChainOfThought",
                    "signature": _signature(
                        _pascal_name(final_id, fallback="ValidateOutput"),
                        inputs=_with_intermediate(inputs, "evidence"),
                        outputs=outputs,
                    ),
                    "role": "Validate extracted evidence and produce the requested output.",
                },
            ],
            "edges": [
                {"from": "input", "to": "extract_evidence"},
                {"from": "extract_evidence", "to": final_id},
                {"from": final_id, "to": "output"},
            ],
            "notes": _prompt_inference_notes(
                "Detected extraction plus validation cues in the prompt."
            ),
        }

    if tokens & _REASONING_CUES:
        module_id = f"reason_{first_output}"
        return {
            "kind": "pipeline",
            "execution_status": "prompt_inferred_not_materialized",
            "origin": "prompt_inferred",
            "inference_reason": "reasoning/review cues favor a generated ChainOfThought module over a single Predict scaffold.",
            "modules": [
                {
                    "id": module_id,
                    "primitive": "ChainOfThought",
                    "signature": _signature(
                        _pascal_name(module_id, fallback="ReasonedOutput"),
                        inputs=inputs,
                        outputs=outputs,
                    ),
                    "role": "Reason over the supplied inputs before producing the requested output.",
                }
            ],
            "edges": [
                {"from": "input", "to": module_id},
                {"from": module_id, "to": "output"},
            ],
            "notes": _prompt_inference_notes(
                "Detected reasoning/review cues in the prompt."
            ),
        }
    return {}


def effective_pipeline_topology(intent: Any) -> dict[str, Any]:
    return declared_pipeline_topology(intent) or prompt_inferred_pipeline_topology(
        intent
    )


def pipeline_topology_origin(intent: Any) -> str | None:
    if declared_pipeline_topology(intent):
        return "declared"
    if prompt_inferred_pipeline_topology(intent):
        return "prompt_inferred"
    return None


def has_materializable_pipeline_topology(intent: Any) -> bool:
    return bool(effective_pipeline_topology(intent))


def _module_signature(module: Mapping[str, Any]) -> dict[str, Any]:
    signature = module.get("signature")
    return dict(signature) if isinstance(signature, Mapping) else {}


def validate_materializable_pipeline_topology(intent: Any) -> dict[str, Any]:
    """Return the normalized pipeline topology or fail for unsupported execution."""

    topology = effective_pipeline_topology(intent)
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
            if not is_pipeline_module_materializable(module)
        }
    )
    if unsupported:
        allowed = ", ".join(
            sorted([*SUPPORTED_PIPELINE_PRIMITIVES, "Retriever:inline_corpus"])
        )
        raise ProgramTopologyMaterializationError(
            "pipeline topology materialization supports only module primitives "
            f"{allowed} under the capability-registry materialization policy; "
            f"unsupported primitives: {unsupported}"
        )
    for module in modules:
        if str(module.get("primitive") or "") != "Retriever":
            continue
        normalize_inline_retriever_config(
            module.get("retriever"), module_id=str(module.get("id") or "")
        )
        outputs = _signature_outputs(module)
        if len(outputs) != 1:
            raise ProgramTopologyMaterializationError(
                "pipeline Retriever modules must declare exactly one signature output"
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
    if not has_materializable_pipeline_topology(intent):
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
    lines: list[str] = ["import json", "", "import dspy", "", "from signature import ("]
    lines.extend(f"    {name}," for name in signature_names)
    lines.extend([")", ""])
    if any(str(module.get("primitive") or "") == "Retriever" for module in modules):
        lines.extend(
            [
                "",
                "def _retriever_tokens(value: object) -> set[str]:",
                "    text = ''.join(ch.lower() if ch.isalnum() else ' ' for ch in str(value))",
                "    return {part for part in text.split() if part}",
                "",
                "",
                "def _select_inline_documents(query: object, documents: list[dict[str, str]], k: int) -> list[dict[str, object]]:",
                "    query_tokens = _retriever_tokens(query)",
                "    scored: list[tuple[int, int, dict[str, str]]] = []",
                "    for index, document in enumerate(documents):",
                "        document_tokens = _retriever_tokens(document.get('text', ''))",
                "        score = len(query_tokens & document_tokens)",
                "        scored.append((score, index, document))",
                "    scored.sort(key=lambda item: (-item[0], item[1]))",
                "    selected = []",
                "    for score, _index, document in scored[:k]:",
                "        selected.append({'id': document.get('id', ''), 'text': document.get('text', ''), 'score': score})",
                "    return selected",
                "",
            ]
        )
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
        if primitive == "Retriever":
            retriever = normalize_inline_retriever_config(
                module.get("retriever"), module_id=str(module.get("id") or "")
            )
            output_name = _signature_outputs(module)[0]
            query_expr = (
                " + ' ' + ".join(f"str({name})" for name in input_names) or "''"
            )
            lines.extend(
                [
                    f"class {class_name}(dspy.Module):",
                    f'    """{doc}"""',
                    "",
                    f"    _DOCUMENTS = {retriever['documents']!r}",
                    f"    _K = {retriever['k']!r}",
                    "",
                    "    def __init__(self, use_cot: bool = False) -> None:",
                    "        super().__init__()",
                    "",
                    f"    def forward(self, {input_params}) -> dspy.Prediction:",
                    f"        selected = _select_inline_documents({query_expr}, self._DOCUMENTS, self._K)",
                    f"        return dspy.Prediction({output_name}=json.dumps(selected, ensure_ascii=False, sort_keys=True))",
                ]
            )
        else:
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
            "    if _json_container_text(gold) and _json_container_text(pred):",
            "        return _normalize_json_text(gold), _normalize_json_text(pred)",
            "    return gold, pred",
            "",
            "",
            "def _json_container_text(value: str) -> bool:",
            "    text = value.strip()",
            "    return (text.startswith('{') and text.endswith('}')) or (text.startswith('[') and text.endswith(']'))",
            "",
            "",
            "def _normalize_json_text(value: str) -> str:",
            "    parsed = json.loads(value.strip())",
            "    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(',', ':'))",
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
    declared_topology = declared_pipeline_topology(intent)
    inferred_topology = prompt_inferred_pipeline_topology(intent)
    renderer = (
        PROMPT_INFERRED_PIPELINE_RENDERER
        if inferred_topology and not declared_topology
        else "pipeline_topology_renderer"
    )
    materialization_scope = {
        "topology_declared": bool(declared_topology),
        "topology_inferred": bool(inferred_topology and not declared_topology),
        "topology_materialized": True,
        "current_renderer": renderer,
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
        "import json",
        "from pathlib import Path",
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
            f"DECLARED_TOPOLOGY = {declared_topology!r}",
            f"INFERRED_TOPOLOGY = {inferred_topology!r}",
            f"MATERIALIZED_TOPOLOGY = {materialized_pipeline_topology(intent)!r}",
            f"TOPOLOGY_EXECUTION_STATUS = {PIPELINE_MATERIALIZED_STATUS!r}",
            f"MATERIALIZATION_SCOPE = {materialization_scope!r}",
            f"MODULE_ORDER = {[_module_id(module) for module in modules]!r}",
            f"MODULE_SIGNATURES = {module_signatures!r}",
            f"EDGES = {list(topology.get('edges', []))!r}",
            "PROGRAM_TEMPLATE_VERSION = 'program-candidate-assembly-v1'",
            "",
            "",
            "def assembly_manifest_path() -> Path:",
            "    return Path(__file__).with_name('manifest.json')",
            "",
            "",
            "def load_manifest() -> dict[str, Any]:",
            "    path = assembly_manifest_path()",
            "    if not path.exists():",
            "        return {}",
            "    try:",
            "        payload = json.loads(path.read_text(encoding='utf-8'))",
            "    except Exception:",
            "        return {}",
            "    return dict(payload) if isinstance(payload, dict) else {}",
            "",
            "",
            "def _current_manifest_hash() -> str:",
            "    path = assembly_manifest_path()",
            "    if not path.exists():",
            "        return ''",
            "    try:",
            "        import hashlib",
            "",
            "        return hashlib.sha256(path.read_bytes()).hexdigest()",
            "    except Exception:",
            "        return ''",
            "",
            "",
            "def _receipt_manifest_hash() -> str:",
            "    path = Path(str(assembly_manifest_path()) + '.meta.json')",
            "    if not path.exists():",
            "        return ''",
            "    try:",
            "        payload = json.loads(path.read_text(encoding='utf-8'))",
            "    except Exception:",
            "        return ''",
            "    if not isinstance(payload, dict):",
            "        return ''",
            "    value = payload.get('hash') or payload.get('output_hash')",
            "    return str(value) if value else ''",
            "",
            "",
            "def _manifest_hash() -> str:",
            "    return _receipt_manifest_hash() or _current_manifest_hash()",
            "",
            "",
            "def program_observability_tags() -> dict[str, str]:",
            "    manifest = load_manifest()",
            "    assembly = manifest.get('candidate_assembly')",
            "    if not isinstance(assembly, dict):",
            "        assembly = {}",
            "    tags = {",
            "        'program.name': str(intent_summary().get('name') or ''),",
            "        'program.assembly_id': str(assembly.get('assembly_id') or ''),",
            "        'program.candidate_id': str(assembly.get('candidate_id') or ''),",
            "    }",
            "    manifest_hash = _manifest_hash()",
            "    if manifest_hash:",
            "        tags['program.manifest_hash'] = manifest_hash",
            "    return {key: value for key, value in tags.items() if value}",
            "",
            "",
            "def configure_observability(",
            "    *,",
            "    run_name: str = 'program-runtime',",
            "    run_kind: str = 'program-runtime',",
            ") -> bool:",
            "    try:",
            "        from dspx.tracing import enable_mlflow_from_env, ensure_run_with_standard_tags, get_mlflow",
            "",
            "        enable_mlflow_from_env()",
            "        if get_mlflow() is None:",
            "            return False",
            "        extra_tags = program_observability_tags()",
            "        if run_kind in {'program-runtime', 'program-eval'} and not extra_tags.get('program.assembly_id'):",
            "            return False",
            "        return ensure_run_with_standard_tags(",
            "            'program',",
            "            template_version=PROGRAM_TEMPLATE_VERSION,",
            "            run_name=run_name,",
            "            run_kind=run_kind,",
            "            output_basename='program.py',",
            "            output_hash=_manifest_hash(),",
            "            extra=extra_tags,",
            "        )",
            "    except Exception:",
            "        return False",
            "",
            "",
            "def _active_mlflow():",
            "    try:",
            "        from dspx.tracing import get_mlflow",
            "",
            "        mlflow = get_mlflow()",
            "        if mlflow is None or mlflow.active_run() is None:",
            "            return None",
            "        return mlflow",
            "    except Exception:",
            "        return None",
            "",
            "",
            "def _set_observability_status(status: str, *, error: Exception | None = None) -> None:",
            "    mlflow = _active_mlflow()",
            "    if mlflow is None:",
            "        return",
            "    try:",
            "        mlflow.set_tag('program.runtime.status', status)",
            "    except Exception:",
            "        pass",
            "    try:",
            "        mlflow.log_metric('program.runtime.error', 1.0 if error is not None else 0.0)",
            "    except Exception:",
            "        pass",
            "    if error is not None:",
            "        try:",
            "            mlflow.set_tag('program.runtime.error_type', type(error).__name__)",
            "        except Exception:",
            "            pass",
            "",
            "",
            "def end_observability_run(started: bool, *, status: str = 'FINISHED') -> None:",
            "    if not started:",
            "        return",
            "    try:",
            "        from dspx.tracing import get_mlflow",
            "",
            "        mlflow = get_mlflow()",
            "        if mlflow is not None:",
            "            try:",
            "                mlflow.end_run(status=status)",
            "            except TypeError:",
            "                mlflow.end_run()",
            "    except Exception:",
            "        pass",
            "",
            "",
            "def run_with_observability(**inputs: object) -> dspy.Prediction:",
            "    started = configure_observability(run_name='program-runtime', run_kind='program-runtime')",
            "    end_status = 'FINISHED'",
            "    try:",
            "        program = build_program()",
            "        prediction = program(**inputs)",
            "        _set_observability_status('passed')",
            "        return prediction",
            "    except Exception as exc:",
            "        end_status = 'FAILED'",
            "        _set_observability_status('failed', error=exc)",
            "        raise",
            "    finally:",
            "        end_observability_run(started, status=end_status)",
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
            "        pending: set[str] = set(MODULE_ORDER)",
            "        while pending:",
            "            progressed = False",
            "            for module_id in MODULE_ORDER:",
            "                if module_id not in pending:",
            "                    continue",
            "                if not _module_ready(module_id, state, executed):",
            "                    continue",
            "                signature = MODULE_SIGNATURES[module_id]",
            "                module = getattr(self, module_id)",
            "                kwargs = {name: state[name] for name in signature['inputs']}",
            "                prediction = module(**kwargs)",
            "                executed.add(module_id)",
            "                pending.remove(module_id)",
            "                progressed = True",
            "                mapped = _prediction_mapping(prediction)",
            "                for output_name in signature['outputs']:",
            "                    if output_name in mapped:",
            "                        state[output_name] = mapped[output_name]",
            "                    elif hasattr(prediction, output_name):",
            "                        state[output_name] = getattr(prediction, output_name)",
            "            if not progressed:",
            "                break",
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
            "        'inferred_topology': dict(INFERRED_TOPOLOGY),",
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
