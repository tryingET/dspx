# summary: "Validates and scores the dependency-preflighted Oracle semantic-analysis evaluation contract."
# read_when:
#   - "Changing AK-4577 contract validation, label scoring, evidence identity, or private artifact helpers."

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
import pwd
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_backend import _analysis_prompt
from dspx.services.program_oracle_semantic_contract import (
    REQUIRED_ANALYSIS_FIELDS,
    OracleSemanticRequest,
)

CONTRACT_RELATIVE_PATH = Path(
    "benchmarks/semantic/oracle-semantic-analysis-evaluation-v8.json"
)
EXPECTED_REVIEW_INVARIANT_SHA256 = (
    "fbcb2cbe6afe2c13c7574ed7debb53817263ea86d7ec18ace1412c767f1b8d90"
)
RESULT_NAME = "evaluation-result.json"
ATTEMPT_NAME = "attempt-status.json"
VERIFICATION_NAME = "independent-verification.json"
CONTRACT_SNAPSHOT_NAME = "contract-snapshot.json"
RESULT_SCHEMA = "dspx-oracle-semantic-analysis-evaluation-result-v8"
ATTEMPT_SCHEMA = "dspx-oracle-semantic-analysis-evaluation-attempt-v8"
VERIFICATION_SCHEMA = "dspx-oracle-semantic-analysis-independent-verification-v8"
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


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _review_invariant_bytes(raw: bytes, contract: Mapping[str, Any]) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SemanticAnalysisEvaluationError(
            "semantic-analysis contract must be UTF-8"
        ) from exc
    top_status = contract.get("status")
    adjudication = _mapping(
        contract.get("offline_adjudication"), "offline_adjudication"
    )
    successor_review = _mapping(
        adjudication.get("successor_review"), "offline_adjudication.successor_review"
    )
    top_line = f'  "status": {json.dumps(top_status)},'
    if text.count(top_line) != 1:
        raise SemanticAnalysisEvaluationError(
            "top-level review status serialization drift"
        )
    text = text.replace(top_line, '  "status": "<REVIEW_STATE>",', 1)
    block_start = text.find('    "successor_review": {\n')
    block_end_marker = '\n    }\n  },\n  "cases":'
    block_end = text.find(block_end_marker, block_start)
    if block_start < 0 or block_end < 0:
        raise SemanticAnalysisEvaluationError(
            "successor review serialization boundary drift"
        )
    prefix = text[:block_start]
    block = text[block_start:block_end]
    suffix = text[block_end:]
    replacements = {
        "status": "<SUCCESSOR_REVIEW_STATE>",
        "reviewer": "<SUCCESSOR_REVIEWER>",
        "review_evidence": "<SUCCESSOR_REVIEW_EVIDENCE>",
    }
    for field, placeholder in replacements.items():
        value = successor_review.get(field)
        line = f'      "{field}": {json.dumps(value)},'
        if block.count(line) != 1:
            raise SemanticAnalysisEvaluationError(
                f"successor review {field} serialization drift"
            )
        block = block.replace(
            line,
            f'      "{field}": "{placeholder}",',
            1,
        )
    return (prefix + block + suffix).encode("utf-8")


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


def _write_private_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    target = path.expanduser().absolute()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(target, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _replace_private_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    target = path.expanduser().absolute()
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        _write_private_exclusive(temporary, payload)
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _attempt_ledger_path() -> Path:
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    return (
        home
        / ".local"
        / "state"
        / "dspx"
        / "oracle-semantic-analysis-evaluations"
        / "AK-4577.json"
    )


def _consume_attempt_ledger(
    *, root: Path, contract_sha256: str, ledger_path: Path | None = None
) -> Path:
    ledger = (ledger_path or _attempt_ledger_path()).expanduser().absolute()
    ledger.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ledger.parent, 0o700)
    payload = {
        "schema_version": "dspx-oracle-semantic-analysis-evaluation-ledger-v8",
        "ak_task_id": 4577,
        "contract_sha256": contract_sha256,
        "root": str(root),
        "status": "started",
        "maximum_evaluation_processes": 1,
        "selective_case_rerun_allowed": False,
    }
    try:
        _write_private_exclusive(ledger, payload)
    except FileExistsError as exc:
        raise SemanticAnalysisEvaluationError(
            f"AK-4577 semantic-analysis evaluation ledger is already consumed: {ledger}"
        ) from exc
    return ledger


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


def preflight_maintained_lm_auth() -> dict[str, str]:
    """Fail before ledger consumption unless the exact maintained release imports."""

    distribution_name = "tryinget-dspy-lm-auth"
    expected_version = "0.1.5"
    try:
        module = importlib.import_module("dspy_lm_auth")
        observed_version = importlib.metadata.version(distribution_name)
    except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
        raise SemanticAnalysisEvaluationError(
            "maintained dspy-lm-auth 0.1.5 dependency preflight failed"
        ) from exc
    module_path = getattr(module, "__file__", None)
    if observed_version != expected_version or not isinstance(module_path, str):
        raise SemanticAnalysisEvaluationError(
            "maintained dspy-lm-auth dependency identity drift"
        )
    return {
        "distribution": distribution_name,
        "version": observed_version,
        "module_path": str(Path(module_path).resolve()),
    }


def load_contract(
    repo_root: Path, *, require_current_sources: bool = True
) -> tuple[dict[str, Any], str]:
    root = repo_root.expanduser().resolve()
    contract_path = root / CONTRACT_RELATIVE_PATH
    contract, raw = _read_json(contract_path, label="semantic-analysis contract")
    observed_hash = _sha256_bytes(raw)
    invariant_hash = _sha256_bytes(_review_invariant_bytes(raw, contract))
    if invariant_hash != EXPECTED_REVIEW_INVARIANT_SHA256:
        raise SemanticAnalysisEvaluationError(
            "semantic-analysis review invariant drift"
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
    if contract.get("schema_version") != "dspx-oracle-semantic-analysis-evaluation-v8":
        raise SemanticAnalysisEvaluationError("semantic-analysis contract schema drift")
    if contract.get("status") not in {
        "successor_offline_review_pending_live_authorized_not_run",
        "offline_adjudicated_live_authorized_not_run",
    }:
        raise SemanticAnalysisEvaluationError("semantic-analysis contract status drift")
    if _strict_int(contract.get("ak_task_id"), "ak_task_id") != 4577:
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
        if not isinstance(expected_hash, str):
            raise SemanticAnalysisEvaluationError(f"{label} source hash drift")
        if (
            require_current_sources
            and _sha256_file(root / expected_path) != expected_hash
        ):
            raise SemanticAnalysisEvaluationError(f"{label} source hash drift")

    route = _mapping(contract.get("route"), "route")
    if route != {
        "required_backend_kind": "live",
        "requested_provider": "dspy-lm-auth",
        "requested_model": "codex/gpt-5.6-sol",
        "reasoning_effort": "max",
        "live_authorized": True,
        "executed_provider_requirement": "explicit_null_not_proven",
        "executed_model_requirement": "non_empty_observed_response_identity",
        "production_adapter_requirement": (
            "exact_dspx_dspy_lm_auth_lm_type_with_call_history"
        ),
        "source_requirement": (
            "caller_supplied_exact_reviewed_git_commit_matches_head_and_all_"
            "evaluation_sources"
        ),
    }:
        raise SemanticAnalysisEvaluationError("semantic-analysis route drift")
    policy = _mapping(contract.get("attempt_policy"), "attempt_policy")
    ledger_policy = _mapping(policy.get("ledger"), "attempt_policy.ledger")
    if (
        policy.get("maximum_evaluation_processes") != 1
        or policy.get("maximum_generate_calls_per_case") != 1
        or policy.get("dspx_generate_invocation_count")
        != "recorded_before_each_analyze_and_verified_against_case_rows"
        or policy.get("maximum_separate_health_probes") != 0
        or policy.get("maximum_dspx_managed_retries") != 0
        or policy.get("selective_case_rerun_allowed") is not False
        or policy.get("stop_after_first_failed_or_indeterminate_case") is not True
        or ledger_policy
        != {
            "kind": "task_fixed_owner_local",
            "namespace": "dspx/oracle-semantic-analysis-evaluations",
            "key": "AK-4577",
            "created_before_backend_resolution": True,
            "started_or_terminal_marker_forbids_another_root": True,
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
    source_contract = _mapping(
        adjudication.get("source_contract"), "offline_adjudication.source_contract"
    )
    successor_review = _mapping(
        adjudication.get("successor_review"), "offline_adjudication.successor_review"
    )
    if (
        adjudication.get("schema_version")
        != "dspx-oracle-semantic-label-adjudication-v1"
        or adjudication.get("status") != "independent_offline_review_accepted"
        or adjudication.get("reviewer") != "operator"
        or adjudication.get("review_evidence") != "ak:evidence:6252"
        or adjudication.get("v6_label_corrections") != []
        or source_contract
        != {
            "path": "benchmarks/semantic/oracle-semantic-analysis-evaluation-v7.json",
            "sha256": "8ead13cab9dc5f7614f56dae1d4499fb2257a6d41b28e5ce72dc43c41d29c1e8",
        }
    ):
        raise SemanticAnalysisEvaluationError(
            "semantic-analysis offline adjudication drift"
        )
    review_status = successor_review.get("status")
    review_reviewer = successor_review.get("reviewer")
    review_evidence = successor_review.get("review_evidence")
    pending_review = (
        contract.get("status")
        == "successor_offline_review_pending_live_authorized_not_run"
        and review_status == "independent_successor_review_pending"
        and review_reviewer is None
        and review_evidence is None
    )
    accepted_review = (
        contract.get("status") == "offline_adjudicated_live_authorized_not_run"
        and review_status == "independent_successor_review_accepted"
        and isinstance(review_reviewer, str)
        and bool(review_reviewer.strip())
        and isinstance(review_evidence, str)
        and review_evidence.startswith("ak:evidence:")
        and review_evidence.removeprefix("ak:evidence:").isdigit()
    )
    if not (pending_review or accepted_review):
        raise SemanticAnalysisEvaluationError(
            "semantic-analysis successor review state drift"
        )
    cases = _sequence(contract.get("cases"), "cases")
    if tuple(str(_mapping(case, "case").get("id")) for case in cases) != _CASE_ORDER:
        raise SemanticAnalysisEvaluationError("semantic-analysis case order drift")
    for raw_case in cases:
        case = _mapping(raw_case, "case")
        marker = case.get("hidden_marker")
        if not isinstance(marker, str) or not marker.startswith("HIDDEN-AK4577-"):
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
