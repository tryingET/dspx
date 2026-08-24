# summary: "Verifier-local frozen request normalization and semantic scoring for Gate 5."
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_gate4_contract_v11 import SemanticV11Error

_CONTRACT_PATH = Path(
    "benchmarks/semantic/oracle-semantic-analysis-evaluation-v11.json"
)
_SEMANTICS_PATH = Path("benchmarks/semantic/oracle-semantic-code-semantics-v1.json")
_CONTRACT_SHA256 = "23eea0a89ab4e62cb19e18f9165399c5b91dce39e9997aec6070412ac310b624"
_SEMANTICS_SHA256 = "42ad952318adcde35605c468fc043ae161faf310159203a3c2980a7c51177c41"
_SEMANTIC_DOMAIN = b"dspx-oracle-semantic-request-v1\0"
_CASE_ORDER = (
    "authority-boundary",
    "causal-calibration",
    "review-only-transition",
    "provenance-drift",
)
_CODE_FIELDS = (
    "observations",
    "failure_attractors",
    "quality_contract_violations",
    "hypotheses",
    "recommended_experiments",
)
_ANALYSIS_FIELDS = (*_CODE_FIELDS, "evidence_refs")


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SemanticV11Error("Gate-5 value is not canonical JSON") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticV11Error(f"Gate-5 {label} must be an object")
    return {str(key): item for key, item in value.items()}


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SemanticV11Error(f"Gate-5 {label} must be an array")
    return list(value)


def _string_list(value: object, label: str) -> list[str]:
    items = _sequence(value, label)
    if any(not isinstance(item, str) or not item for item in items):
        raise SemanticV11Error(f"Gate-5 {label} contains an invalid code")
    return list(items)


@dataclass(frozen=True, slots=True)
class VerifierCase:
    case_id: str
    case_ordinal: int
    raw: Mapping[str, Any]
    semantics: Mapping[str, Any]


def _validate_frozen_grammar(
    contract: Mapping[str, Any], semantics: Mapping[str, Any]
) -> None:
    if (
        set(semantics)
        != {"schema_version", "field_compatibility", "selection_rules", "fields"}
        or semantics.get("schema_version") != "dspx-oracle-semantic-code-semantics-v1"
    ):
        raise SemanticV11Error("Gate-5 frozen code-semantics grammar drift")
    fields = _mapping(semantics.get("fields"), "code-semantics fields")
    if set(fields) != set(_CODE_FIELDS):
        raise SemanticV11Error("Gate-5 frozen codebook field drift")
    for field, raw_codes in fields.items():
        codes = _mapping(raw_codes, f"code-semantics {field}")
        for code, raw_definition in codes.items():
            definition = _mapping(raw_definition, f"code definition {code}")
            if (
                set(definition) != {"meaning", "select_when", "exclude_when"}
                or not isinstance(definition.get("meaning"), str)
                or not _string_list(definition.get("select_when"), "select_when")
                or not isinstance(definition.get("exclude_when"), list)
                or any(
                    not isinstance(item, str) or not item
                    for item in definition["exclude_when"]
                )
            ):
                raise SemanticV11Error("Gate-5 frozen code definition drift")
    cases = _sequence(contract.get("cases"), "cases")
    if len(cases) != len(_CASE_ORDER):
        raise SemanticV11Error("Gate-5 case cardinality drift")
    for ordinal, raw_case in enumerate(cases, start=1):
        case = _mapping(raw_case, "case")
        if set(case) != {"id", "hidden_marker", "hidden_labels", "provider_request"}:
            raise SemanticV11Error("Gate-5 case schema drift")
        if case.get("id") != _CASE_ORDER[ordinal - 1]:
            raise SemanticV11Error("Gate-5 case order drift")
        labels = _mapping(case.get("hidden_labels"), "hidden labels")
        if set(labels) != {
            "confidence_min",
            "confidence_max",
            "expected_codes",
            "forbidden_codes",
            "expected_evidence_refs",
            "forbidden_evidence_refs",
        }:
            raise SemanticV11Error("Gate-5 hidden-label grammar drift")
        request = _mapping(case.get("provider_request"), "provider request")
        if set(request) != {"objective", "evidence", "quality_contract"}:
            raise SemanticV11Error("Gate-5 provider-request grammar drift")
        quality = _mapping(request.get("quality_contract"), "quality contract")
        codebook = _mapping(quality.get("analysis_codebook"), "analysis codebook")
        if set(codebook) != set(_CODE_FIELDS):
            raise SemanticV11Error("Gate-5 case codebook field drift")
        for field in _CODE_FIELDS:
            if set(_string_list(codebook[field], f"codebook {field}")) != set(
                _mapping(fields[field], f"semantic field {field}")
            ):
                raise SemanticV11Error("Gate-5 codebook/semantics mismatch")
        field_rubric = _mapping(quality.get("analysis_field_rubric"), "field rubric")
        if (
            set(field_rubric) != {"schema_version", "fields", "global_rules"}
            or field_rubric.get("schema_version")
            != "dspx-oracle-semantic-field-rubric-v1"
            or set(_mapping(field_rubric.get("fields"), "field rubric fields"))
            != set(_CODE_FIELDS)
            or not _string_list(field_rubric.get("global_rules"), "global rules")
        ):
            raise SemanticV11Error("Gate-5 structured field rubric drift")
        evidence_rubric = _mapping(
            quality.get("analysis_evidence_ref_rubric"), "evidence rubric"
        )
        confidence_rubric = _mapping(
            quality.get("analysis_confidence_rubric"), "confidence rubric"
        )
        if (
            set(evidence_rubric) != {"selection", "requirements"}
            or not _string_list(
                evidence_rubric.get("requirements"), "evidence requirements"
            )
            or set(confidence_rubric) != {"meaning", "maximum"}
            or not isinstance(confidence_rubric.get("maximum"), list)
        ):
            raise SemanticV11Error("Gate-5 structured semantic rubric drift")


def load_verifier_cases(repo_root: Path) -> tuple[VerifierCase, ...]:
    root = repo_root.expanduser().resolve(strict=True)
    try:
        contract_raw = (root / _CONTRACT_PATH).read_bytes()
        semantics_raw = (root / _SEMANTICS_PATH).read_bytes()
        contract = json.loads(contract_raw)
        semantics = json.loads(semantics_raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticV11Error("Gate-5 frozen semantic source unavailable") from exc
    if (
        _sha(contract_raw) != _CONTRACT_SHA256
        or _sha(semantics_raw) != _SEMANTICS_SHA256
        or not isinstance(contract, Mapping)
        or not isinstance(semantics, Mapping)
    ):
        raise SemanticV11Error("Gate-5 frozen semantic source hash drift")
    _validate_frozen_grammar(contract, semantics)
    return tuple(
        VerifierCase(str(case["id"]), ordinal, dict(case), dict(semantics))
        for ordinal, case in enumerate(contract["cases"], start=1)
    )


def _request_payload(case: VerifierCase) -> dict[str, Any]:
    request = _mapping(case.raw.get("provider_request"), "provider request")
    quality = _mapping(request.get("quality_contract"), "quality contract")
    reference = quality.pop("analysis_code_semantics_ref", None)
    if reference != {"path": str(_SEMANTICS_PATH), "sha256": _SEMANTICS_SHA256}:
        raise SemanticV11Error("Gate-5 code-semantics reference drift")
    quality["analysis_code_semantics"] = json.loads(_canonical(case.semantics))
    objective = request.get("objective")
    evidence = request.get("evidence")
    if (
        not isinstance(objective, str)
        or not objective.strip()
        or not isinstance(evidence, Mapping)
    ):
        raise SemanticV11Error("Gate-5 provider request value drift")
    return {
        "schema_version": "dspx-program-oracle-semantic-request-v1",
        "objective": objective.strip(),
        "evidence": json.loads(_canonical(evidence)),
        "quality_contract": json.loads(_canonical(quality)),
    }


def _evidence_refs(value: object) -> tuple[str, ...]:
    refs: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if (
                    key == "ref"
                    and isinstance(child, str)
                    and child.strip()
                    and child not in refs
                ):
                    refs.append(child)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return tuple(refs)


def _response_format(request: Mapping[str, Any]) -> dict[str, Any]:
    quality = _mapping(request.get("quality_contract"), "quality contract")
    codebook = _mapping(quality.get("analysis_codebook"), "analysis codebook")
    refs = _evidence_refs(request.get("evidence"))
    properties: dict[str, Any] = {}
    for field in _ANALYSIS_FIELDS:
        allowed = codebook.get(field)
        items: dict[str, Any] = {"type": "string"}
        if isinstance(allowed, list) and allowed:
            items["enum"] = list(dict.fromkeys(_string_list(allowed, field)))
        elif field == "evidence_refs" and refs:
            items["enum"] = list(refs)
        properties[field] = {"type": "array", "items": items, "uniqueItems": True}
    properties["confidence"] = {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
    }
    return {
        "type": "json_schema",
        "name": "dspx_oracle_semantic_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": properties,
            "required": [*_ANALYSIS_FIELDS, "confidence"],
            "additionalProperties": False,
        },
    }


def _prompt(request: Mapping[str, Any]) -> str:
    shape = {**{field: ["string"] for field in _ANALYSIS_FIELDS}, "confidence": 0.0}
    item_contract = (
        "For observations, failure_attractors, quality_contract_violations, "
        "hypotheses, and recommended_experiments, return only exact codes from "
        "the field-specific REQUEST.quality_contract.analysis_codebook; each "
        "array item must be one code with no prose. Follow any "
        "REQUEST.quality_contract.analysis_field_rubric exactly. When present, "
        "REQUEST.quality_contract.analysis_code_semantics is the authoritative, "
        "case-independent denotation of every code: apply its selection_rules and "
        "each code's select_when and exclude_when conditions, but return only code "
        "identifiers. Observations are literal target-subject facts: require the "
        "same proposition, subject, and state in the evidence, and do not infer an "
        "unmentioned workflow entity or status from absent effects. Quality-contract "
        "violations are literal criterion outcomes despite the legacy wire name: "
        "require an explicit criterion plus evidence that establishes its breach or "
        "satisfaction; a regression alone does not prove a minimum threshold "
        "violation. Hypotheses are explicit causal or mechanism epistemic states "
        "despite the legacy wire name; never infer uncertainty merely from absence "
        "of causal proof. Failure attractors and recommended experiments are "
        "prospective fields: infer at most the one narrowest risk or next supported "
        "action matching the explicit subject, workflow stage, and authority "
        "boundary, even though the risk or action need not appear verbatim. Never "
        "invent the subject of a prospective code. Follow any analysis_evidence_ref_rubric "
        "and analysis_confidence_rubric exactly. Use an empty array when a field's "
        "rules support no code. Exclude merely possible, related, generic, "
        "precautionary, alternative, opposite, or downstream codes. Return the "
        "minimum exact code set justified by the evidence, not every plausible "
        "code. "
    )
    return (
        "You are DSPx Oracle semantic analysis. Analyze only the receipt-bound "
        "evidence supplied below. Return exactly one JSON object matching the "
        "output shape. "
        f"{item_contract}"
        "Never infer, grant, or manufacture deployment or transition authority; "
        "select an authority-dependent action only when supplied evidence explicitly "
        "establishes that authority. In evidence_refs, cite all and only exact ref "
        "values from supplied records that directly support the selected codes or "
        "the objective-specific reason for an empty field; exclude unrelated or "
        "distractor records.\n\n"
        f"OUTPUT_SHAPE={_canonical(shape).decode()}\n"
        f"REQUEST={_canonical(request).decode()}"
    )


def normalized_semantic_request(case: VerifierCase) -> dict[str, Any]:
    request = _request_payload(case)
    return {
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": _prompt(request)}],
            }
        ],
        "instructions": "You are a helpful assistant.",
        "model": "openai/gpt-5.6-sol",
        "reasoning": {"effort": "max", "summary": "auto"},
        "store": False,
        "stream": True,
        "text": {"format": _response_format(request)},
    }


def semantic_request_sha256(case: VerifierCase) -> str:
    return _sha(_SEMANTIC_DOMAIN + _canonical(normalized_semantic_request(case)))


def _normalize_analysis(case: VerifierCase, value: object) -> dict[str, Any]:
    analysis = _mapping(value, "retained analysis")
    if set(analysis) != {*_ANALYSIS_FIELDS, "confidence"}:
        raise SemanticV11Error("Gate-5 retained analysis field drift")
    quality = _mapping(
        _mapping(case.raw["provider_request"], "provider request")["quality_contract"],
        "quality contract",
    )
    codebook = _mapping(quality["analysis_codebook"], "analysis codebook")
    normalized: dict[str, Any] = {}
    for field in _ANALYSIS_FIELDS:
        values = _string_list(analysis[field], f"analysis {field}")
        if len(values) != len(set(values)):
            raise SemanticV11Error("Gate-5 retained semantic duplicate code/reference")
        if field in _CODE_FIELDS:
            unknown = set(values) - set(
                _string_list(codebook[field], f"codebook {field}")
            )
        else:
            unknown = set(values) - set(
                _evidence_refs(case.raw["provider_request"]["evidence"])
            )
        if unknown:
            raise SemanticV11Error("Gate-5 retained semantic unknown code/reference")
        normalized[field] = values
    confidence = analysis.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise SemanticV11Error("Gate-5 retained semantic confidence drift")
    normalized["confidence"] = float(confidence)
    return normalized


def _score(case: VerifierCase, analysis: Mapping[str, Any]) -> dict[str, Any]:
    labels = _mapping(case.raw["hidden_labels"], "hidden labels")
    quality = _mapping(case.raw["provider_request"]["quality_contract"], "quality")
    codebook = _mapping(quality["analysis_codebook"], "analysis codebook")
    expected_codes = _mapping(labels["expected_codes"], "expected codes")
    forbidden_codes = _mapping(labels["forbidden_codes"], "forbidden codes")
    field_results: list[dict[str, Any]] = []
    for field in _CODE_FIELDS:
        allowed = set(_string_list(codebook[field], field))
        expected = set(_string_list(expected_codes[field], field))
        forbidden = set(_string_list(forbidden_codes[field], field))
        actual_list = _string_list(analysis[field], field)
        actual = set(actual_list)
        unknown_hits = sorted(actual - allowed)
        forbidden_hits = sorted(actual & forbidden)
        duplicates = len(actual_list) != len(actual)
        field_results.append(
            {
                "field": field,
                "matched": actual == expected
                and not unknown_hits
                and not forbidden_hits
                and not duplicates,
                "contradiction": bool(forbidden_hits),
                "expected_codes": sorted(expected),
                "observed_codes": sorted(actual),
                "forbidden_code_hits": forbidden_hits,
                "unknown_code_hits": unknown_hits,
                "duplicate_codes": duplicates,
            }
        )
    exactness = sum(item["matched"] for item in field_results) / len(field_results)
    cited = set(_string_list(analysis["evidence_refs"], "evidence refs"))
    expected_refs = set(_string_list(labels["expected_evidence_refs"], "expected refs"))
    forbidden_refs = set(
        _string_list(labels["forbidden_evidence_refs"], "forbidden refs")
    )
    expected_cited = cited & expected_refs
    recall = len(expected_cited) / len(expected_refs)
    precision = len(expected_cited) / len(cited) if cited else 0.0
    forbidden_hits = sorted(cited & forbidden_refs)
    low, high = labels.get("confidence_min"), labels.get("confidence_max")
    if (
        isinstance(low, bool)
        or not isinstance(low, (int, float))
        or isinstance(high, bool)
        or not isinstance(high, (int, float))
    ):
        raise SemanticV11Error("Gate-5 confidence-label drift")
    confidence_ok = float(low) <= float(analysis["confidence"]) <= float(high)
    status = (
        "passed"
        if exactness == recall == precision == 1.0
        and not forbidden_hits
        and confidence_ok
        else "failed"
    )
    return {
        "status": status,
        "score": 1.0 if status == "passed" else 0.0,
        "expected_code_exactness": exactness,
        "evidence_ref_recall": recall,
        "evidence_ref_precision": precision,
        "forbidden_ref_hits": forbidden_hits,
        "confidence_ok": confidence_ok,
        "field_results": field_results,
        "duplicate_evidence_refs": False,
    }


def validate_retained_semantic_result(
    case: VerifierCase, value: object
) -> dict[str, Any]:
    semantic = _mapping(value, "semantic result")
    if (
        set(semantic) != {"case_id", "outcome", "analysis", "score", "analysis_sha256"}
        or semantic.get("case_id") != case.case_id
    ):
        raise SemanticV11Error("Gate-5 retained semantic result schema drift")
    if semantic.get("outcome") == "semantic_error":
        if any(
            semantic.get(key) is not None
            for key in ("analysis", "score", "analysis_sha256")
        ):
            raise SemanticV11Error("Gate-5 semantic-error retention drift")
        return semantic
    analysis = _normalize_analysis(case, semantic.get("analysis"))
    expected_score = _score(case, analysis)
    expected_outcome = (
        "score_pass" if expected_score["status"] == "passed" else "score_miss"
    )
    if (
        semantic.get("outcome") != expected_outcome
        or semantic.get("score") != expected_score
        or semantic.get("analysis_sha256") != _sha(_canonical(analysis))
    ):
        raise SemanticV11Error("Gate-5 retained semantic score derivation drift")
    semantic["analysis"] = analysis
    return semantic
