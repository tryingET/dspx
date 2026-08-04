# summary: "Executes the already-consumed, no-retry AK-4643 semantic v10 attempt."
from __future__ import annotations

import inspect
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from dspx.redaction import sanitize_diagnostic_text
from dspx.services.program_oracle_semantic_artifacts_v10 import (
    ATTEMPT_PROJECTION,
    EFFECT_PROJECTION,
    RESULT_SCHEMA,
    active_case,
    append_event,
    ensure_private_directory,
)
from dspx.services.program_oracle_semantic_artifacts_v10 import (
    has_open_effect as _has_open_effect,
)
from dspx.services.program_oracle_semantic_artifacts_v10 import (
    history_hashes as _history_hashes,
)
from dspx.services.program_oracle_semantic_contract_v10 import (
    ATTEMPT_DIR,
    CASE_ORDER,
    RESULT_NAME,
    TASK_ID,
    SemanticV10Error,
    canonical,
    mapping,
    materialized_request,
    score_v10,
    sequence,
    sha256,
    write_exclusive,
)
from dspx.services.program_oracle_semantic_identity_v10 import ROUTE, validate_receipts

CONTRACT_SNAPSHOT = "contract-snapshot.json"
REVIEW_SNAPSHOT = "candidate-review-snapshot.json"
GATE_SNAPSHOT = "live-gate-snapshot.json"
NONCLAIMS = {
    "statistical_representativeness": False,
    "broad_production_semantic_quality": False,
    "embedding_quality": False,
    "shared_coordinate_store_readiness": False,
    "executed_provider_identity": False,
    "provider_transport_call_cardinality": False,
    "provider_internal_retry_absence": False,
    "oracle_governance_authority": False,
    "release_authority": False,
    "package_publication": False,
    "production_activation": False,
    "rocs_conformance": False,
    "shared_oracle_publication": False,
}


def _environment_route() -> None:
    expected = {
        "DSPX_ORACLE_SEMANTIC_BACKEND": "live",
        "DSPX_ORACLE_SEMANTIC_PROVIDER": ROUTE["provider"],
        "DSPX_ORACLE_SEMANTIC_MODEL": ROUTE["model"],
        "DSPX_ORACLE_SEMANTIC_REASONING_EFFORT": ROUTE["reasoning_effort"],
    }
    if {key: os.getenv(key) for key in expected} != expected:
        raise SemanticV10Error("exact live route environment drift")
    if os.getenv("DSPX_ORACLE_SEMANTIC_FIXTURE_PATH"):
        raise SemanticV10Error("fixture route is forbidden")


def _production_backend() -> tuple[Any, Any]:
    from dspx.dspy_lm_auth_lm import DspyLMAuthLM
    from dspx.services.program_oracle_semantic_backend import (
        LiveLMOracleSemanticBackend,
        resolve_program_oracle_semantic_backend,
    )

    backend = resolve_program_oracle_semantic_backend()
    if (
        type(backend) is not LiveLMOracleSemanticBackend
        or type(backend.lm) is not DspyLMAuthLM
    ):
        raise SemanticV10Error(
            "only the exact production DspyLMAuthLM backend is permitted"
        )
    lm = backend.lm
    if (
        "generate" in lm.__dict__
        or getattr(lm, "requested_model", None) != ROUTE["model"]
        or getattr(lm, "auth_provider", None) != "codex"
        or getattr(lm, "strict", None) is not True
        or getattr(lm, "kwargs", None) != {"reasoning_effort": "max"}
        or getattr(lm, "history", None)
    ):
        raise SemanticV10Error("production adapter configuration drift")
    for name in ("_build_inner", "forward", "generate", "runtime_metadata"):
        descriptor = inspect.getattr_static(DspyLMAuthLM, name, None)
        bound = getattr(lm, name, None)
        if (
            name in lm.__dict__
            or descriptor is None
            or getattr(bound, "__func__", None) is not descriptor
        ):
            raise SemanticV10Error("production adapter method drift")
    if (
        backend.provider_name != ROUTE["provider"]
        or backend.preferred_model != ROUTE["model"]
        or backend.configured_model != ROUTE["model"]
    ):
        raise SemanticV10Error("configured route identity drift")
    return backend, lm


def _case_rows(
    *,
    contract: Mapping[str, Any],
    semantics: Mapping[str, Any],
    requests: Mapping[str, str],
    attempt: Path,
    backend: Any,
    lm: Any,
    rows_out: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], bool, bool]:
    rows = rows_out if rows_out is not None else []
    any_error = False
    open_effect = False
    for raw_case in sequence(contract.get("cases"), "cases"):
        case = mapping(raw_case, "case")
        case_id = str(case.get("id"))
        request = materialized_request(case, semantics)
        if requests.get(case_id) != request.request_sha256:
            raise SemanticV10Error("reviewed request hash drift")
        append_event(
            attempt,
            "case_started",
            case_id=case_id,
            request_sha256=request.request_sha256,
        )
        generate_before = int(getattr(lm, "generate_invocation_count", 0))
        history_before = len(getattr(lm, "history", []))
        token = f"{case_id}:generate:1"
        append_event(
            attempt,
            "effect_possible",
            case_id=case_id,
            request_sha256=request.request_sha256,
            effect_token=token,
            generate_invocation=1,
        )
        open_effect = True
        try:
            semantic_result = backend.analyze(request)
        except Exception:  # noqa: BLE001 - provider boundary must classify arbitrary failures
            append_event(
                attempt,
                "case_error",
                case_id=case_id,
                classification="backend_call_incomplete",
            )
            any_error = True
            break
        generate_delta = (
            int(getattr(lm, "generate_invocation_count", 0)) - generate_before
        )
        history_delta = len(getattr(lm, "history", [])) - history_before
        if (
            generate_delta not in {0, 1}
            or history_delta not in {0, 1}
            or generate_delta != history_delta
        ):
            append_event(
                attempt,
                "case_error",
                case_id=case_id,
                classification="adapter_cardinality_drift",
            )
            any_error = True
            break
        result_dict = semantic_result.to_dict()
        status = result_dict.get("execution_status")
        response_attributable = (
            status in {"succeeded", "failed_after_live_response"}
            and result_dict.get("live_call_succeeded") is True
        )
        no_call = generate_delta == 0 and history_delta == 0
        if response_attributable or no_call:
            append_event(
                attempt,
                "effect_observed",
                case_id=case_id,
                effect_token=token,
                generate_invocation_delta=generate_delta,
                history_delta=history_delta,
                response_attributable=response_attributable,
            )
            open_effect = False
        if (
            not response_attributable
            or status != "succeeded"
            or result_dict.get("analysis") is None
        ):
            append_event(
                attempt,
                "case_error",
                case_id=case_id,
                classification="typed_response_error"
                if not open_effect
                else "effect_outcome_unresolved",
            )
            rows.append(
                {
                    "case_id": case_id,
                    "request_sha256": request.request_sha256,
                    "semantic_result": result_dict,
                    "score": None,
                    "status": "error",
                }
            )
            any_error = True
            break
        if (
            result_dict.get("backend_kind") != "live"
            or result_dict.get("preferred_model") != ROUTE["model"]
            or result_dict.get("configured_provider") != ROUTE["provider"]
            or result_dict.get("configured_model") != ROUTE["model"]
            or result_dict.get("executed_provider") is not None
            or not str(result_dict.get("executed_model") or "").strip()
        ):
            append_event(
                attempt,
                "case_error",
                case_id=case_id,
                classification="route_identity_error",
            )
            rows.append(
                {
                    "case_id": case_id,
                    "request_sha256": request.request_sha256,
                    "semantic_result": result_dict,
                    "score": None,
                    "status": "error",
                }
            )
            any_error = True
            break
        prior_models = {
            str(
                mapping(row.get("semantic_result"), "semantic_result").get(
                    "executed_model"
                )
            )
            for row in rows
            if row.get("status") == "passed"
        }
        if prior_models and str(result_dict.get("executed_model")) not in prior_models:
            append_event(
                attempt,
                "case_error",
                case_id=case_id,
                classification="executed_model_drift",
            )
            rows.append(
                {
                    "case_id": case_id,
                    "request_sha256": request.request_sha256,
                    "semantic_result": result_dict,
                    "score": None,
                    "status": "error",
                }
            )
            any_error = True
            break
        try:
            score = score_v10(case, cast(Mapping[str, Any], result_dict["analysis"]))
        except Exception:  # noqa: BLE001 - provider boundary must classify arbitrary failures
            append_event(
                attempt,
                "case_error",
                case_id=case_id,
                classification="response_schema_error",
            )
            rows.append(
                {
                    "case_id": case_id,
                    "request_sha256": request.request_sha256,
                    "semantic_result": result_dict,
                    "score": None,
                    "status": "error",
                }
            )
            any_error = True
            break
        row_status = str(score.get("status"))
        rows.append(
            {
                "case_id": case_id,
                "request_sha256": request.request_sha256,
                "semantic_result": result_dict,
                "score": score,
                "status": row_status,
            }
        )
        append_event(
            attempt,
            "case_scored",
            case_id=case_id,
            status=row_status,
            score_sha256=sha256(canonical(score)),
        )
        if row_status != "passed":
            break
    return rows, any_error, open_effect


def _disposition(
    rows: list[dict[str, Any]], *, any_error: bool, open_effect: bool
) -> str:
    if open_effect:
        return "effect_indeterminate"
    if any_error:
        return "error"
    if any(row.get("status") != "passed" for row in rows):
        return "failed"
    return (
        "passed" if tuple(row.get("case_id") for row in rows) == CASE_ORDER else "error"
    )


def _terminal_result(
    *,
    attempt: Path,
    receipts: Mapping[str, Any],
    rows: list[dict[str, Any]],
    disposition: str,
    dependency: Mapping[str, str] | None,
    preflight_error: str | None,
) -> dict[str, Any]:
    scores = [row["score"] for row in rows if isinstance(row.get("score"), Mapping)]
    result = {
        "schema_version": RESULT_SCHEMA,
        "ak_task_id": TASK_ID,
        "artifact_integrity_review": "pending_independent_verification",
        "empirical_gate": disposition,
        "contract_sha256": receipts.get("contract_sha256"),
        "candidate_review_sha256": receipts.get("review_sha256"),
        "live_gate_sha256": receipts.get("gate_sha256"),
        "source_identity": receipts.get("source_identity"),
        "request_hashes": receipts.get("request_hashes"),
        "route": {
            "requested": ROUTE,
            "configured_provider": ROUTE["provider"] if rows else None,
            "configured_model": ROUTE["model"] if rows else None,
            "observed_models": [
                str(row["semantic_result"].get("executed_model"))
                for row in rows
                if isinstance(row.get("semantic_result"), Mapping)
                and str(row["semantic_result"].get("executed_model") or "").strip()
            ],
        },
        "dependency_identity": dependency,
        "cases": rows,
        "summary": {
            "expected_case_count": len(CASE_ORDER),
            "reached_case_count": len(rows),
            "passed_case_count": sum(row.get("status") == "passed" for row in rows),
            "macro_score": sum(float(score.get("score", 0.0)) for score in scores)
            / len(CASE_ORDER),
        },
        "attempt": dict(ATTEMPT_PROJECTION),
        "preflight_error": preflight_error,
        "event_history_sha256": _history_hashes(attempt),
        "effects": dict(EFFECT_PROJECTION),
        "claims": {
            "exact_four_case_empirical_gate_passed": disposition == "passed",
            **NONCLAIMS,
        },
    }
    write_exclusive(attempt / RESULT_NAME, result)
    append_event(
        attempt,
        "terminal",
        disposition=disposition,
        result_sha256=sha256((attempt / RESULT_NAME).read_bytes()),
    )
    return result


def evaluate_consumed(
    *, repo_root: Path, state_root: Path, _test_owner_home: Path | None = None
) -> dict[str, Any]:
    """Run only after the standard-library runner has durably consumed the attempt."""
    state = ensure_private_directory(
        state_root, create=False, _test_owner_home=_test_owner_home
    )
    attempt = state / ATTEMPT_DIR
    receipts: dict[str, Any] = {}
    dependency: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    any_error = False
    open_effect = False
    preflight_error: str | None = None
    try:
        # Preserve historically verifiable reviewed objects before any current-source,
        # dependency, route, or backend check can fail this already-consumed attempt.
        receipts = validate_receipts(
            repo_root=repo_root,
            state_root=state,
            require_current_commit=False,
            _test_owner_home=_test_owner_home,
        )
        dependency = mapping(receipts["gate"]["dependency_identity"], "dependency")
        write_exclusive(
            attempt / CONTRACT_SNAPSHOT, cast(Mapping[str, Any], receipts["contract"])
        )
        write_exclusive(
            attempt / REVIEW_SNAPSHOT, cast(Mapping[str, Any], receipts["review"])
        )
        write_exclusive(
            attempt / GATE_SNAPSHOT, cast(Mapping[str, Any], receipts["gate"])
        )
        receipts = validate_receipts(
            repo_root=repo_root,
            state_root=state,
            require_current_commit=True,
            _test_owner_home=_test_owner_home,
        )
        _environment_route()
        if _test_owner_home is not None:
            raise SemanticV10Error("test state roots are permanently effect-disabled")
        append_event(
            attempt,
            "preflight_passed",
            contract_sha256=receipts["contract_sha256"],
            candidate_review_sha256=receipts["review_sha256"],
            live_gate_sha256=receipts["gate_sha256"],
        )
        backend, lm = _production_backend()
        rows, any_error, open_effect = _case_rows(
            contract=receipts["contract"],
            semantics=receipts["semantics"],
            requests=receipts["request_hashes"],
            attempt=attempt,
            backend=backend,
            lm=lm,
            rows_out=rows,
        )
    except Exception as exc:  # noqa: BLE001 - consumed attempt must terminalize
        preflight_error = sanitize_diagnostic_text(type(exc).__name__)[:160]
        current_case = active_case(attempt)
        if current_case:
            append_event(
                attempt,
                "case_error",
                case_id=current_case,
                classification=preflight_error,
            )
        else:
            append_event(attempt, "preflight_error", classification=preflight_error)
        any_error = True
    open_effect = open_effect or _has_open_effect(attempt)
    disposition = _disposition(rows, any_error=any_error, open_effect=open_effect)
    return _terminal_result(
        attempt=attempt,
        receipts=receipts,
        rows=rows,
        disposition=disposition,
        dependency=dependency,
        preflight_error=preflight_error,
    )
