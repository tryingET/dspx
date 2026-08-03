# summary: "Validates the zero-process AK-4574 semantic-analysis contract candidate."
# read_when:
#   - "Changing AK-4574 contract validation, field labels, or prompt-isolation rules."

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_backend import _analysis_prompt
from dspx.services.program_oracle_semantic_contract import (
    REQUIRED_ANALYSIS_FIELDS,
    OracleSemanticRequest,
)

CONTRACT_RELATIVE_PATH = Path(
    "benchmarks/semantic/oracle-semantic-analysis-evaluation-v7.json"
)
EXPECTED_CONTRACT_SHA256 = (
    "23dafeeae90886a6ec686bd061f8c5d201cab97513080bc6a08e59f68381628e"
)
FROZEN_SOURCE_COMMIT = "1decb1701af762d23d0f8d41bb00f86c08095c3f"
_MAX_JSON_BYTES = 1_000_000
_CASE_ORDER = (
    "authority-boundary",
    "causal-calibration",
    "review-only-transition",
    "provenance-drift",
)
_CODE_FIELDS = REQUIRED_ANALYSIS_FIELDS[:-1]


class SemanticAnalysisEvaluationError(ValueError):
    """Raised when the frozen semantic-analysis evaluation fails closed."""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SemanticAnalysisEvaluationError(
            f"evaluation value must be canonical JSON: {exc}"
        ) from exc


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_git_blob(repo_root: Path, commit: str, path: str) -> str:
    try:
        raw = subprocess.check_output(
            ["git", "-C", str(repo_root), "show", f"{commit}:{path}"],
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        raise SemanticAnalysisEvaluationError(
            f"frozen source binding is unavailable: {commit}:{path}"
        ) from exc
    return _sha256_bytes(raw)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticAnalysisEvaluationError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SemanticAnalysisEvaluationError(f"{label} must be an array")
    return list(value)


def _strict_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SemanticAnalysisEvaluationError(f"{label} must be an integer")
    return value


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    target = path.expanduser().absolute()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise SemanticAnalysisEvaluationError(
            f"{label} must be an existing regular non-symlink file"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SemanticAnalysisEvaluationError(f"{label} must be a regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(_MAX_JSON_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > _MAX_JSON_BYTES:
            raise SemanticAnalysisEvaluationError(
                f"{label} exceeds the {_MAX_JSON_BYTES}-byte bound"
            )
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise SemanticAnalysisEvaluationError(f"{label} changed while read")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemanticAnalysisEvaluationError(f"{label} must be valid JSON") from exc
    return _mapping(payload, label), raw


def _provider_refs(value: object) -> set[str]:
    """Return every evidence ref recursively exposed to the provider."""
    refs: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "ref" and isinstance(item, str):
                refs.add(item)
            refs.update(_provider_refs(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            refs.update(_provider_refs(item))
    return refs


def _request(case: Mapping[str, Any]) -> OracleSemanticRequest:
    """Build the provider request without copying hidden labels."""
    raw = _mapping(case.get("provider_request"), "case.provider_request")
    evidence = _mapping(raw.get("evidence"), "case.provider_request.evidence")
    quality_raw = raw.get("quality_contract")
    quality = (
        _mapping(quality_raw, "case.provider_request.quality_contract")
        if quality_raw is not None
        else None
    )
    return OracleSemanticRequest(
        objective=str(raw.get("objective") or ""),
        evidence=evidence,
        quality_contract=quality,
    )


def load_contract(repo_root: Path) -> tuple[dict[str, Any], str]:
    root = repo_root.expanduser().resolve()
    contract_path = root / CONTRACT_RELATIVE_PATH
    contract, raw = _read_json(contract_path, label="semantic-analysis contract")
    observed_hash = _sha256_bytes(raw)
    if observed_hash != EXPECTED_CONTRACT_SHA256:
        raise SemanticAnalysisEvaluationError(
            "semantic-analysis contract byte hash drift"
        )
    expected_fields = {
        "schema_version",
        "status",
        "ak_task_id",
        "purpose",
        "claim_scope",
        "source_bindings",
        "route",
        "attempt_policy",
        "thresholds",
        "privacy_and_effects",
        "field_rubric",
        "offline_adjudication",
        "cases",
        "falsifiers",
        "nonclaims",
    }
    if set(contract) != expected_fields:
        raise SemanticAnalysisEvaluationError("semantic-analysis contract fields drift")
    if contract.get("schema_version") != "dspx-oracle-semantic-analysis-evaluation-v7":
        raise SemanticAnalysisEvaluationError("semantic-analysis contract schema drift")
    if contract.get("status") != "candidate_offline_review_pending_live_not_authorized":
        raise SemanticAnalysisEvaluationError("semantic-analysis contract status drift")
    if _strict_int(contract.get("ak_task_id"), "ak_task_id") != 4574:
        raise SemanticAnalysisEvaluationError("semantic-analysis task identity drift")

    source_bindings = _mapping(contract.get("source_bindings"), "source_bindings")
    for label, expected_path in {
        "semantic_backend": "packages/dspx-core/src/dspx/services/program_oracle_semantic_backend.py",
        "production_adapter": "packages/dspx-core/src/dspx/dspy_lm_auth_lm.py",
        "model_roles": "packages/dspx-core/src/dspx/model_roles.py",
    }.items():
        binding = _mapping(source_bindings.get(label), f"source_bindings.{label}")
        if binding.get("path") != expected_path:
            raise SemanticAnalysisEvaluationError(f"{label} source path drift")
        expected_hash = binding.get("sha256")
        if (
            not isinstance(expected_hash, str)
            or _sha256_git_blob(root, FROZEN_SOURCE_COMMIT, expected_path)
            != expected_hash
        ):
            raise SemanticAnalysisEvaluationError(f"{label} source hash drift")

    route = _mapping(contract.get("route"), "route")
    if route != {
        "required_backend_kind": "live",
        "requested_provider": "dspy-lm-auth",
        "requested_model": "codex/gpt-5.6-sol",
        "reasoning_effort": "max",
        "live_authorized": False,
        "executed_provider_requirement": "explicit_null_not_proven",
        "executed_model_requirement": "non_empty_observed_response_identity",
        "production_adapter_requirement": (
            "exact_dspx_dspy_lm_auth_lm_type_with_call_history"
        ),
        "source_requirement": (
            "all_evaluation_sources_match_one_committed_git_snapshot"
        ),
    }:
        raise SemanticAnalysisEvaluationError("semantic-analysis route drift")
    policy = _mapping(contract.get("attempt_policy"), "attempt_policy")
    ledger_policy = _mapping(policy.get("ledger"), "attempt_policy.ledger")
    if (
        policy.get("maximum_evaluation_processes") != 0
        or policy.get("maximum_generate_calls_per_case") != 1
        or policy.get("maximum_separate_health_probes") != 0
        or policy.get("maximum_dspx_managed_retries") != 0
        or policy.get("selective_case_rerun_allowed") is not False
        or policy.get("stop_after_first_failed_or_indeterminate_case") is not True
        or ledger_policy
        != {
            "kind": "unassigned_successor_required",
            "namespace": "dspx/oracle-semantic-analysis-evaluations",
            "key": "UNASSIGNED-LIVE-SUCCESSOR",
            "created_before_backend_resolution": False,
            "started_or_terminal_marker_forbids_another_root": False,
        }
        or tuple(_sequence(policy.get("case_order"), "case_order")) != _CASE_ORDER
    ):
        raise SemanticAnalysisEvaluationError("semantic-analysis attempt policy drift")
    thresholds = _mapping(contract.get("thresholds"), "thresholds")
    if thresholds != {
        "minimum_case_score": 1.0,
        "minimum_macro_score": 1.0,
        "minimum_expected_code_exactness": 1.0,
        "minimum_evidence_ref_precision": 1.0,
        "minimum_evidence_ref_recall": 1.0,
        "maximum_forbidden_hits": 0,
        "maximum_failed_or_error_cases": 0,
    }:
        raise SemanticAnalysisEvaluationError("semantic-analysis thresholds drift")
    field_rubric = _mapping(contract.get("field_rubric"), "field_rubric")
    if field_rubric.get("schema_version") != "dspx-oracle-semantic-field-rubric-v1":
        raise SemanticAnalysisEvaluationError("semantic-analysis field rubric drift")
    rubric_fields = _mapping(field_rubric.get("fields"), "field_rubric.fields")
    expected_modes = {
        "observations": "literal_target_fact",
        "failure_attractors": "bounded_prospective",
        "quality_contract_violations": "literal_criterion_check",
        "hypotheses": "literal_uncertainty",
        "recommended_experiments": "bounded_prospective",
    }
    if set(rubric_fields) != set(expected_modes) or any(
        _mapping(rubric_fields.get(field), f"field_rubric.fields.{field}").get("mode")
        != mode
        for field, mode in expected_modes.items()
    ):
        raise SemanticAnalysisEvaluationError("semantic-analysis field rubric drift")
    adjudication = _mapping(
        contract.get("offline_adjudication"), "offline_adjudication"
    )
    if (
        adjudication.get("schema_version")
        != "dspx-oracle-semantic-label-adjudication-v1"
        or adjudication.get("status") != "independent_offline_review_pending"
        or adjudication.get("reviewer") is not None
        or adjudication.get("review_evidence") is not None
    ):
        raise SemanticAnalysisEvaluationError(
            "semantic-analysis offline adjudication drift"
        )
    cases = _sequence(contract.get("cases"), "cases")
    if tuple(str(_mapping(case, "case").get("id")) for case in cases) != _CASE_ORDER:
        raise SemanticAnalysisEvaluationError("semantic-analysis case order drift")
    for raw_case in cases:
        case = _mapping(raw_case, "case")
        marker = case.get("hidden_marker")
        if not isinstance(marker, str) or not marker.startswith("HIDDEN-AK4574-"):
            raise SemanticAnalysisEvaluationError("hidden marker identity drift")
        labels = _mapping(case.get("hidden_labels"), "case.hidden_labels")
        request = _request(case)
        quality_contract = _mapping(
            request.quality_contract, "case.provider_request.quality_contract"
        )
        if quality_contract.get("analysis_field_rubric") != field_rubric:
            raise SemanticAnalysisEvaluationError("provider request field rubric drift")
        prompt = _analysis_prompt(request)
        if marker in prompt or _canonical_json(labels) in prompt:
            raise SemanticAnalysisEvaluationError(
                "hidden labels leaked into provider prompt"
            )
        provider_refs = _provider_refs(request.payload())
        expected_refs = set(
            str(item)
            for item in _sequence(
                labels.get("expected_evidence_refs"), "expected_evidence_refs"
            )
        )
        forbidden_refs = set(
            str(item)
            for item in _sequence(
                labels.get("forbidden_evidence_refs"), "forbidden_evidence_refs"
            )
        )
        if not expected_refs or not expected_refs <= provider_refs:
            raise SemanticAnalysisEvaluationError(
                "expected evidence refs are not provider evidence"
            )
        if not forbidden_refs <= provider_refs:
            raise SemanticAnalysisEvaluationError(
                "forbidden evidence refs are not provider evidence"
            )
        quality = _mapping(request.quality_contract, "request.quality_contract")
        codebook = _mapping(quality.get("analysis_codebook"), "analysis_codebook")
        expected_codes = _mapping(labels.get("expected_codes"), "expected_codes")
        forbidden_codes = _mapping(labels.get("forbidden_codes"), "forbidden_codes")
        if set(codebook) != set(_CODE_FIELDS):
            raise SemanticAnalysisEvaluationError("analysis codebook fields drift")
        if set(expected_codes) != set(_CODE_FIELDS) or set(forbidden_codes) != set(
            _CODE_FIELDS
        ):
            raise SemanticAnalysisEvaluationError("hidden code label fields drift")
        expected_count = 0
        for field in _CODE_FIELDS:
            allowed = [
                str(item)
                for item in _sequence(codebook.get(field), f"codebook.{field}")
            ]
            expected = [
                str(item)
                for item in _sequence(
                    expected_codes.get(field), f"expected_codes.{field}"
                )
            ]
            forbidden = [
                str(item)
                for item in _sequence(
                    forbidden_codes.get(field), f"forbidden_codes.{field}"
                )
            ]
            if (
                not allowed
                or len(allowed) != len(set(allowed))
                or any(not item for item in allowed)
                or set(expected) & set(forbidden)
                or set(expected) | set(forbidden) != set(allowed)
            ):
                raise SemanticAnalysisEvaluationError(
                    f"analysis code labels drift for {field}"
                )
            expected_count += len(expected)
        if expected_count == 0:
            raise SemanticAnalysisEvaluationError("hidden expected codes are empty")
    if any(
        value is not False
        for value in _mapping(contract.get("nonclaims"), "nonclaims").values()
    ):
        raise SemanticAnalysisEvaluationError("semantic-analysis nonclaim widened")
    return contract, observed_hash
