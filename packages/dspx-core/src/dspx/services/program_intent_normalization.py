from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import sha256_text
from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_contracts import sanitize_ident
from dspx.services.program_intent import ProgramIntent, load_program_intent
from dspx.services.program_generation_preview import (
    build_generation_assumption_preview,
    preview_tokens,
)

PROGRAM_INTENT_NORMALIZATION_SCHEMA = "program-intent-normalization-v1"
_FORBIDDEN_OUTPUT_NAMES = set(PROTECTED_PROGRAM_ARTIFACT_NAMES)
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
_UNSUPPORTED_PRIMITIVE_CUES = {
    "react": "ReAct",
    "reactv2": "ReActV2",
    "react-v2": "ReActV2",
    "react_v2": "ReActV2",
    "tool": "tool_using_module",
    "tools": "tool_using_module",
    "retrieve": "Retriever",
    "retrieval": "Retriever",
    "retriever": "Retriever",
    "programofthought": "ProgramOfThought",
    "program-of-thought": "ProgramOfThought",
    "program_of_thought": "ProgramOfThought",
}


class ProgramIntentNormalizationError(ValueError):
    """Raised when intent normalization cannot proceed safely."""


def _json_text(payload: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _safe_output_path(path: Path, *, label: str) -> Path:
    target = path.expanduser().resolve()
    if target.name in _FORBIDDEN_OUTPUT_NAMES:
        raise ProgramIntentNormalizationError(
            f"refusing to write {label} to generated candidate artifact path: {target.name}"
        )
    if target.exists() and target.is_dir():
        raise ProgramIntentNormalizationError(
            f"{label} output path is a directory: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _source_hash_text(text: str) -> str:
    return sha256_text(text)


def _intent_hash(intent_payload: Mapping[str, Any]) -> str:
    return sha256_text(json.dumps(intent_payload, ensure_ascii=False, sort_keys=True))


def _tokens(text: str) -> set[str]:
    return preview_tokens(text)


def _name_from_prompt(prompt: str) -> str:
    words = [word for word in re.findall(r"[A-Za-z][A-Za-z0-9]*", prompt)[:6]]
    if not words:
        return "NormalizedIntentProgram"
    return sanitize_ident(
        "".join(word[:1].upper() + word[1:] for word in words),
        fallback="NormalizedIntentProgram",
    )


def _infer_inputs(prompt: str, token_set: set[str]) -> tuple[list[str], list[str]]:
    assumptions: list[str] = []
    if "ticket" in token_set or "tickets" in token_set:
        return ["ticket_text"], assumptions
    if "evidence" in token_set:
        return ["evidence"], assumptions
    if "pdf" in token_set or "document" in token_set or "documents" in token_set:
        return ["document_text"], assumptions
    if "question" in token_set:
        return ["context", "question"], assumptions
    assumptions.append(
        "No explicit input field was detected; defaulted to a single `context` input."
    )
    return ["context"], assumptions


def _infer_outputs(prompt: str, token_set: set[str]) -> tuple[list[str], list[str]]:
    assumptions: list[str] = []
    if "response" in token_set or "respond" in token_set or "draft" in token_set:
        return ["response"], assumptions
    if "recommend" in token_set or "recommendation" in token_set:
        return ["recommendation"], assumptions
    if "classify" in token_set or "classification" in token_set:
        return ["label"], assumptions
    if "summary" in token_set or "summarize" in token_set or "summarise" in token_set:
        return ["summary"], assumptions
    assumptions.append(
        "No explicit output field was detected; defaulted to a single `answer` output."
    )
    return ["answer"], assumptions


def _constraint_candidates(prompt: str) -> list[str]:
    constraints: list[str] = []
    for raw_sentence in re.split(r"(?<=[.!?])\s+", prompt.strip()):
        sentence = raw_sentence.strip().strip(" .")
        lower = sentence.casefold()
        if not sentence:
            continue
        if any(
            cue in lower
            for cue in [
                "must",
                "should",
                "only",
                "without",
                "preserve",
                "do not",
                "don't",
            ]
        ):
            constraints.append(sentence)
    return constraints[:8]


def _topology_hints(token_set: set[str]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    if token_set & _ROUTING_CUES and token_set & _GENERATION_CUES:
        hints.append(
            {
                "hint": "route_then_generate",
                "topology_kind": "pipeline",
                "confidence": "medium",
                "reason": "Routing/classification cues plus generation/response cues suggest a classifier followed by a reasoned output module.",
                "materializable_now": True,
            }
        )
    if token_set & _EXTRACT_CUES and token_set & _VALIDATE_CUES:
        hints.append(
            {
                "hint": "extract_validate_generate",
                "topology_kind": "pipeline",
                "confidence": "medium",
                "reason": "Extraction and validation cues suggest separate evidence extraction and validation/output surfaces.",
                "materializable_now": True,
            }
        )
    if token_set & _REASONING_CUES:
        hints.append(
            {
                "hint": "reasoned_single_module",
                "topology_kind": "pipeline",
                "confidence": "medium",
                "reason": "Reasoning/review/explanation cues suggest a generated ChainOfThought surface over a plain Predict scaffold.",
                "materializable_now": True,
            }
        )
    return hints


def _has_bounded_inline_retriever(intent: ProgramIntent | None) -> bool:
    if intent is None:
        return False
    topology = dict(intent.topology or {})
    if topology.get("kind") not in {"pipeline", "retrieve_then_answer"}:
        return False
    for raw_module in topology.get("modules", []):
        if not isinstance(raw_module, Mapping):
            continue
        module = dict(raw_module)
        if str(module.get("primitive") or "") != "Retriever":
            continue
        retriever = module.get("retriever")
        if isinstance(retriever, Mapping) and retriever.get("mode") == "inline_corpus":
            return True
    return False


def _primitive_hints(
    token_set: set[str], intent: ProgramIntent | None = None
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    bounded_inline_retriever = _has_bounded_inline_retriever(intent)
    if token_set & _ROUTING_CUES or token_set & _EXTRACT_CUES:
        hints.append(
            {
                "primitive": "Predict",
                "status": "supported",
                "reason": "Classification/extraction surfaces can use the current generated Predict primitive.",
            }
        )
    if (
        token_set & _GENERATION_CUES
        or token_set & _REASONING_CUES
        or token_set & _VALIDATE_CUES
    ):
        hints.append(
            {
                "primitive": "ChainOfThought",
                "status": "supported",
                "reason": "Reasoned generation/review/validation can use the current generated ChainOfThought primitive.",
            }
        )
    for cue, primitive in sorted(_UNSUPPORTED_PRIMITIVE_CUES.items()):
        if cue not in token_set:
            continue
        if primitive == "Retriever" and bounded_inline_retriever:
            hints.append(
                {
                    "primitive": primitive,
                    "status": "conditionally_materializable_with_bounded_inline_adapter",
                    "reason": f"Prompt mentions {cue!r}, and the explicit topology declares a bounded inline_corpus Retriever adapter materializable by the current pipeline/retrieve_then_answer renderer.",
                }
            )
            continue
        hints.append(
            {
                "primitive": primitive,
                "status": "declared_only_not_executable_by_current_renderer",
                "reason": f"Prompt mentions {cue!r}, but current executable rendering is limited to generated Predict/ChainOfThought modules plus explicit bounded inline-corpus Retriever adapters in supported topologies.",
            }
        )
    if not hints:
        hints.append(
            {
                "primitive": "Predict",
                "status": "supported_default",
                "reason": "No richer primitive cue was detected; default generated Predict remains the baseline.",
            }
        )
    return hints


def _missing_evidence(intent: ProgramIntent) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    if not intent.examples and not intent.examples_path:
        missing.append(
            {
                "kind": "examples",
                "severity": "medium",
                "message": "No inline examples or examples_path were supplied; behavior evidence will be narrow until examples are added.",
            }
        )
    if not intent.dataset and not intent.datasets:
        missing.append(
            {
                "kind": "dataset",
                "severity": "medium",
                "message": "No dataset or explicit splits were supplied; tournament evaluation cannot compare broader data behavior.",
            }
        )
    if not intent.metric:
        missing.append(
            {
                "kind": "metric",
                "severity": "low",
                "message": "No metric was supplied; downstream generated plans will use an unspecified/default metric posture.",
            }
        )
    return missing


def _generation_risks(
    token_set: set[str], intent: ProgramIntent
) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    unsupported = [
        hint
        for hint in _primitive_hints(token_set, intent)
        if hint["status"].startswith("declared_only")
    ]
    if unsupported:
        risks.append(
            {
                "kind": "unsupported_primitive",
                "severity": "high",
                "message": "Prompt asks for primitives beyond the current executable renderer; keep them declared-only until safe contracts land.",
            }
        )
    if not intent.examples and not intent.dataset and not intent.datasets:
        risks.append(
            {
                "kind": "insufficient_behavior_evidence",
                "severity": "medium",
                "message": "Generated candidates can be materialized and replay-checked, but empirical comparison will be weak without examples or datasets.",
            }
        )
    if any(
        word in token_set
        for word in ["deploy", "activate", "production", "canonical", "mutate"]
    ):
        risks.append(
            {
                "kind": "authority_boundary",
                "severity": "high",
                "message": "Activation/canonical mutation language requires a separate owner-authorized governance path; normalization does not grant authority.",
            }
        )
    return risks


_SUPPORT_LEVEL_TAXONOMY: tuple[dict[str, Any], ...] = (
    {
        "level": "descriptor_only",
        "label": "Descriptor-only",
        "meaning": "Capability is represented in the normalized intent/preview evidence but is not executed.",
        "allowed_in_blocker": True,
        "effect_allowed": False,
    },
    {
        "level": "local_dry_run_evaluation",
        "label": "Local dry-run/evaluation",
        "meaning": "Capability may be checked locally through schema/hash/preview validation without live tool, retriever, import, or authority effects.",
        "allowed_in_blocker": True,
        "effect_allowed": False,
    },
    {
        "level": "executable_local",
        "label": "Executable local",
        "meaning": "Capability may execute only inside the generated candidate's declared local runtime/evaluation boundary.",
        "allowed_in_blocker": True,
        "effect_allowed": True,
    },
    {
        "level": "production_activation",
        "label": "Production activation",
        "meaning": "Capability affects live routing, canonical state, source-owner systems, or external authority.",
        "allowed_in_blocker": False,
        "effect_allowed": False,
    },
)


def _support_level_taxonomy() -> list[dict[str, Any]]:
    return [dict(item) for item in _SUPPORT_LEVEL_TAXONOMY]


def _primitive_support_level(status: str) -> str:
    if status.startswith("declared_only"):
        return "descriptor_only"
    if status.startswith("conditionally_materializable"):
        return "executable_local"
    if status.startswith("supported"):
        return "executable_local"
    return "local_dry_run_evaluation"


def _primitive_support_blockers(primitive: str, status: str) -> list[str]:
    if status.startswith("declared_only"):
        return [
            f"{primitive} is preserved as a declaration because the current "
            "renderer cannot execute it safely.",
            "Do not bind live tools, live retrievers, arbitrary imports, "
            "filesystem, network, subprocess, or authority effects.",
        ]
    if status.startswith("conditionally_materializable"):
        return [
            "Materialization requires an explicit bounded local adapter declaration and receipt replay evidence.",
            "External/live retrievers and authority effects remain disabled.",
        ]
    return []


def _safe_next_actions_for_support(level: str, *, capability: str) -> list[str]:
    if level == "descriptor_only":
        return [
            f"Keep {capability} hash-bound in the preview/intent contract.",
            "Add an explicit safe adapter policy before allowing execution.",
        ]
    if level == "local_dry_run_evaluation":
        return [
            f"Validate {capability} through local schema/hash/preview checks only.",
            "Promote to executable-local only after an explicit renderer/adapter contract exists.",
        ]
    if level == "executable_local":
        return [
            f"Materialize {capability} only through the bounded local renderer.",
            "Run generated-module policy checks and receipt replay before trusting evidence.",
        ]
    return [
        "Route production activation through the owner-authorized governance boundary; "
        "this blocker does not grant activation authority."
    ]


def _primitive_support_classifications(
    primitive_hints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    classifications: list[dict[str, Any]] = []
    for hint in primitive_hints:
        primitive = str(hint.get("primitive") or "unknown")
        status = str(hint.get("status") or "review_required")
        level = _primitive_support_level(status)
        classifications.append(
            {
                "capability_kind": "primitive",
                "name": primitive,
                "source_status": status,
                "support_level": level,
                "materialization_effects_allowed": level == "executable_local",
                "blockers": _primitive_support_blockers(primitive, status),
                "safe_next_actions": _safe_next_actions_for_support(
                    level, capability=primitive
                ),
            }
        )
    return classifications


def _topology_support_classifications(
    generation_preview: Mapping[str, Any],
) -> list[dict[str, Any]]:
    classifications: list[dict[str, Any]] = []
    candidates = generation_preview.get("topology_candidates")
    if not isinstance(candidates, list):
        return classifications
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, Mapping):
            continue
        candidate = dict(raw_candidate)
        kind = str(candidate.get("kind") or "unknown")
        materializable_now = bool(candidate.get("materializable_now"))
        level = "executable_local" if materializable_now else "descriptor_only"
        blockers: list[str] = []
        if not materializable_now:
            blockers.append(
                "Candidate is preview/contract evidence only until a bounded renderer "
                "validates an executable subset."
            )
        boundary = str(candidate.get("safety_boundary") or "")
        if boundary:
            blockers.append(boundary)
        classifications.append(
            {
                "capability_kind": "topology_candidate",
                "name": kind,
                "source": str(candidate.get("source") or "unknown"),
                "support_level": level,
                "materialization_effects_allowed": materializable_now,
                "renderer": str(candidate.get("renderer") or ""),
                "blockers": blockers,
                "safe_next_actions": _safe_next_actions_for_support(
                    level, capability=kind
                ),
            }
        )
    return classifications


def _feature_support_level(
    feature: str, *, intent: ProgramIntent, boundary: Mapping[str, Any]
) -> str:
    declared_module_primitives = _declared_module_primitives_for_support(intent)
    if feature == "retrievers":
        return (
            "executable_local"
            if _has_bounded_inline_retriever(intent)
            else "descriptor_only"
        )
    if feature == "react":
        return (
            "executable_local"
            if "ReAct" in declared_module_primitives
            else "descriptor_only"
        )
    if feature == "program_of_thought":
        return (
            "executable_local"
            if "ProgramOfThought" in declared_module_primitives
            else "descriptor_only"
        )
    if feature in {"tools", "react_v2", "custom_modules"}:
        return "descriptor_only"
    status = str(boundary.get("status") or "")
    if status == "not_requested":
        return "descriptor_only"
    return "local_dry_run_evaluation"


def _declared_module_primitives_for_support(intent: ProgramIntent) -> set[str]:
    modules = dict(intent.topology or {}).get("modules")
    if not isinstance(modules, list):
        return set()
    return {
        str(module.get("primitive") or "")
        for module in modules
        if isinstance(module, Mapping)
    }


def _feature_support_classifications(
    generation_preview: Mapping[str, Any], intent: ProgramIntent
) -> list[dict[str, Any]]:
    boundaries = generation_preview.get("capability_boundaries")
    if not isinstance(boundaries, Mapping):
        return []
    classifications: list[dict[str, Any]] = []
    for feature, raw_boundary in boundaries.items():
        if not isinstance(raw_boundary, Mapping):
            continue
        boundary = dict(raw_boundary)
        requested = bool(boundary.get("need_detected") or boundary.get("requested"))
        if not requested:
            continue
        feature_name = str(feature)
        level = _feature_support_level(feature_name, intent=intent, boundary=boundary)
        blockers = [str(boundary.get("boundary") or "Review before materialization.")]
        if level == "descriptor_only":
            blockers.append(
                "No executable local adapter is enabled for this feature in the "
                "current preview slice."
            )
        classifications.append(
            {
                "capability_kind": "feature_boundary",
                "name": feature_name,
                "source_status": str(boundary.get("status") or "review_required"),
                "support_level": level,
                "materialization_effects_allowed": level == "executable_local",
                "blockers": blockers,
                "safe_next_actions": _safe_next_actions_for_support(
                    level, capability=feature_name
                ),
            }
        )
    return classifications


def _support_level_preview(
    *,
    intent: ProgramIntent,
    primitive_hints: list[dict[str, Any]],
    generation_preview: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "program-support-level-preview-v1",
        "status": "preview_only_not_materialization_authority",
        "taxonomy": _support_level_taxonomy(),
        "classifications": {
            "primitives": _primitive_support_classifications(primitive_hints),
            "topology_candidates": _topology_support_classifications(
                generation_preview
            ),
            "features": _feature_support_classifications(generation_preview, intent),
            "production_activation": {
                "capability_kind": "authority_boundary",
                "name": "production_activation",
                "support_level": "production_activation",
                "in_scope": False,
                "materialization_effects_allowed": False,
                "blockers": [
                    "Generated-program artifacts remain non-authoritative.",
                    "Activation requires a separate owner-authorized governance path.",
                ],
                "safe_next_actions": _safe_next_actions_for_support(
                    "production_activation", capability="production_activation"
                ),
            },
        },
        "safe_next_actions": [
            "Review support levels, blockers, missing evidence, and topology "
            "candidates before materialization.",
            "Treat descriptor-only capabilities as preserved contracts, not "
            "executable behavior.",
            "Keep production activation outside program-gen blocker #1 unless the "
            "owning governance surface explicitly authorizes it.",
        ],
        "effect": {
            "program_materialized": False,
            "tool_called": False,
            "retriever_called": False,
            "custom_import_loaded": False,
            "authority_mutated": False,
        },
    }


def _effect() -> dict[str, bool]:
    return {
        "normalized_intent_written": False,
        "program_materialized": False,
        "provider_called": False,
        "oracle_index_mutated": False,
        "ak_called": False,
        "governance_mutated": False,
        "external_authority_mutated": False,
        "winner_selected": False,
        "promotion_applied": False,
    }


def _non_authority() -> dict[str, bool]:
    return {
        "normalization_only": True,
        "program_generation": False,
        "ranking_authority": False,
        "winner_selection": False,
        "promotion_authority": False,
        "activation_authority": False,
        "oracle_authority": False,
        "governance_authority": False,
        "canonical_mutation": False,
        "external_mutation": False,
    }


def build_program_intent_normalization(
    intent: ProgramIntent,
    *,
    source: Mapping[str, Any],
    assumptions: list[str] | None = None,
) -> dict[str, Any]:
    intent_payload = intent.model_dump(mode="json", exclude_none=True)
    objective_text = str(intent.objective or "")
    token_set = _tokens(
        " ".join([objective_text, intent.task_type, " ".join(intent.constraints)])
    )
    all_assumptions = list(assumptions or [])
    if not intent.constraints:
        all_assumptions.append(
            "No explicit constraints were supplied; no constraints were invented."
        )
    if not intent.topology:
        all_assumptions.append(
            "No explicit topology was supplied; topology hints are advisory only."
        )
    primitive_hints = _primitive_hints(token_set, intent)
    generation_preview = build_generation_assumption_preview(token_set, intent)
    return {
        "schema_version": PROGRAM_INTENT_NORMALIZATION_SCHEMA,
        "status": "normalized",
        "source": dict(source),
        "normalized_intent": intent_payload,
        "normalized_intent_hash": _intent_hash(intent_payload),
        "assumptions": all_assumptions,
        "missing_evidence": _missing_evidence(intent),
        "topology_hints": _topology_hints(token_set),
        "primitive_hints": primitive_hints,
        "generation_assumptions_preview": generation_preview,
        "support_level_preview": _support_level_preview(
            intent=intent,
            primitive_hints=primitive_hints,
            generation_preview=generation_preview,
        ),
        "generation_risks": _generation_risks(token_set, intent),
        "next_actions": [
            "Inspect assumptions, missing evidence, topology hints, and generation risks before materialization.",
            "Run `dspx program-architect plan --intent <normalized-intent>` to inspect candidate architectures.",
            "Add examples or datasets before using tournament evidence for serious comparison.",
        ],
        "effect": _effect(),
        "non_authority": _non_authority(),
    }


def normalize_program_intent_from_path(path: Path) -> dict[str, Any]:
    source = path.expanduser().resolve()
    text = source.read_text(encoding="utf-8")
    intent = load_program_intent(source)
    return build_program_intent_normalization(
        intent,
        source={
            "kind": "intent_file",
            "path": str(source),
            "content_hash": _source_hash_text(text),
        },
    )


def normalize_program_intent_from_prompt(
    prompt: str,
    *,
    name: str | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    metric: str | None = None,
) -> dict[str, Any]:
    text = str(prompt or "").strip()
    if not text:
        raise ProgramIntentNormalizationError("prompt must not be blank")
    token_set = _tokens(text)
    inferred_inputs, input_assumptions = _infer_inputs(text, token_set)
    inferred_outputs, output_assumptions = _infer_outputs(text, token_set)
    chosen_inputs = [str(item) for item in (inputs or inferred_inputs)]
    chosen_outputs = [str(item) for item in (outputs or inferred_outputs)]
    constraints = _constraint_candidates(text)
    options = {
        "normalization": {
            "schema_version": PROGRAM_INTENT_NORMALIZATION_SCHEMA,
            "source_kind": "prompt",
            "source_hash": _source_hash_text(text),
        },
        "module_inference": True,
    }
    intent = ProgramIntent(
        name=name or _name_from_prompt(text),
        objective=text,
        inputs=chosen_inputs,
        outputs=chosen_outputs,
        constraints=constraints,
        metric=metric,
        options=options,
    )
    assumptions = [*input_assumptions, *output_assumptions]
    if inputs is not None:
        assumptions.append("Input fields were supplied explicitly by the operator.")
    if outputs is not None:
        assumptions.append("Output fields were supplied explicitly by the operator.")
    if metric is not None:
        assumptions.append("Metric was supplied explicitly by the operator.")
    return build_program_intent_normalization(
        intent,
        source={"kind": "prompt", "content_hash": _source_hash_text(text)},
        assumptions=assumptions,
    )


def normalize_program_intent_from_request_path(
    path: Path,
    *,
    name: str | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    metric: str | None = None,
) -> dict[str, Any]:
    source = path.expanduser().resolve()
    text = source.read_text(encoding="utf-8")
    payload = normalize_program_intent_from_prompt(
        text,
        name=name,
        inputs=inputs,
        outputs=outputs,
        metric=metric,
    )
    payload["source"] = {
        "kind": "request_file",
        "path": str(source),
        "content_hash": _source_hash_text(text),
    }
    return payload


def write_program_intent_normalization(
    payload: Mapping[str, Any], out: Path
) -> dict[str, Any]:
    target = _safe_output_path(out, label="intent normalization")
    payload_without_artifact = dict(payload)
    payload_without_artifact.pop("artifact", None)
    payload_hash = sha256_text(_json_text(payload_without_artifact))
    updated = dict(payload_without_artifact)
    updated["artifact"] = {
        "path": str(target),
        "payload_hash_excluding_artifact": payload_hash,
        "schema_version": PROGRAM_INTENT_NORMALIZATION_SCHEMA,
    }
    target.write_text(_json_text(updated), encoding="utf-8")
    return updated


def write_normalized_intent(payload: Mapping[str, Any], out: Path) -> dict[str, Any]:
    target = _safe_output_path(out, label="normalized intent")
    intent_payload = payload.get("normalized_intent")
    if not isinstance(intent_payload, Mapping):
        raise ProgramIntentNormalizationError(
            "normalization payload missing normalized_intent"
        )
    rendered = _json_text(dict(intent_payload))
    target.write_text(rendered, encoding="utf-8")
    return {
        "path": str(target),
        "content_hash": sha256_text(rendered),
        "schema_version": str(
            intent_payload.get("schema_version") or "program-intent-v2"
        ),
    }
