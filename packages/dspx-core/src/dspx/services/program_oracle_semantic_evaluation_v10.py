# summary: "Executes the already-consumed, no-retry AK-4643 semantic v10 attempt."
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from dspx.services.program_oracle_semantic_artifacts_v10 import (
    active_case,
    require_mode,
    append_case_error as _case_error,
    append_event,
    case_row as _row,
    derive_disposition,
    disposition as _disposition,
    ensure_private_directory,
    load_events,
    retained_rows,
    result_payload,
    verify_snapshot,
)
from dspx.services.program_oracle_semantic_artifacts_v10 import (
    has_open_effect as _has_open_effect,
)
from dspx.services.program_oracle_semantic_contract_v10 import (
    ATTEMPT_DIR,
    LEDGER_NAME,
    CASE_ORDER,
    RESULT_NAME,
    SemanticV10Error,
    canonical,
    mapping,
    read_json,
    require_recorded_process_inactive,
    retained_json,
    materialized_request,
    score_v10,
    sequence,
    terminal_error_classification,
    validate_attempt_ledger,
    validate_route_environment,
    sha256,
    write_exclusive,
)
from dspx.services.program_oracle_semantic_identity_v10 import (
    ROUTE,
    loaded_source_identity,
    validate_dependency_imports,
    validate_receipts,
)

CONTRACT_SNAPSHOT = "contract-snapshot.json"
REVIEW_SNAPSHOT = "candidate-review-snapshot.json"
GATE_SNAPSHOT = "live-gate-snapshot.json"


def _production_backend() -> tuple[Any, Any]:
    raise SemanticV10Error(
        "semantic v10 production backend is unavailable after the typed hard cutover; "
        "the terminal effect_indeterminate attempt remains immutable and is not retried"
    )


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
    any_error = open_effect = False
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
        before = (
            int(getattr(lm, "generate_invocation_count", 0)),
            len(getattr(lm, "history", [])),
        )
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
        except Exception:  # noqa: BLE001 - provider boundary remains effect-indeterminate
            _case_error(attempt, case_id, "backend_call_incomplete")
            any_error = True
            break
        delta = (
            int(getattr(lm, "generate_invocation_count", 0)) - before[0],
            len(getattr(lm, "history", [])) - before[1],
        )
        if delta[0] not in {0, 1} or delta[1] not in {0, 1} or delta[0] != delta[1]:
            _case_error(attempt, case_id, "adapter_cardinality_drift")
            any_error = True
            break
        result_dict = semantic_result.to_dict()
        if len(canonical(result_dict)) > 180_000:
            result_dict = {
                **{key: result_dict.get(key) for key in result_dict},
                "execution_status": "failed_after_live_response",
                "live_call_succeeded": True,
                "analysis": None,
                "error": "bounded_response_retention_error",
            }
        status = result_dict.get("execution_status")
        attributable = (
            status in {"succeeded", "failed_after_live_response"}
            and result_dict.get("live_call_succeeded") is True
        )
        if attributable or delta == (0, 0):
            append_event(
                attempt,
                "effect_observed",
                case_id=case_id,
                effect_token=token,
                generate_invocation_delta=delta[0],
                history_delta=delta[1],
                response_attributable=attributable,
            )
            open_effect = False
        error_row = _row(case_id, request.request_sha256, result_dict, None, "error")
        route_ok = (
            result_dict.get("backend_kind") == "live"
            and result_dict.get("preferred_model") == ROUTE["model"]
            and result_dict.get("configured_provider") == ROUTE["provider"]
            and result_dict.get("configured_model") == ROUTE["model"]
            and result_dict.get("executed_provider") is None
            and result_dict.get("fixture_sha256") is None
            and bool(str(result_dict.get("executed_model") or "").strip())
        )
        classification: str | None = None
        if open_effect:
            _case_error(attempt, case_id, "effect_outcome_unresolved")
            any_error = True
            break
        if not route_ok:
            classification = "route_identity_error"
        elif result_dict.get("error") == "bounded_response_retention_error":
            classification = "response_retention_error"
        elif (
            not attributable
            or status != "succeeded"
            or result_dict.get("analysis") is None
        ):
            classification = "typed_response_error"
        else:
            prior = {
                str(row["semantic_result"].get("executed_model"))
                for row in rows
                if row.get("status") == "passed"
            }
            if prior and str(result_dict.get("executed_model")) not in prior:
                classification = "executed_model_drift"
        if classification:
            _case_error(attempt, case_id, classification, error_row)
            rows.append(error_row)
            any_error = True
            break
        try:
            score = score_v10(case, cast(Mapping[str, Any], result_dict["analysis"]))
        except Exception:  # noqa: BLE001 - malformed typed response
            _case_error(attempt, case_id, "response_schema_error", error_row)
            rows.append(error_row)
            any_error = True
            break
        row_status = str(score.get("status"))
        scored = _row(case_id, request.request_sha256, result_dict, score, row_status)
        if len(canonical(scored)) > 220_000:
            bounded = dict(error_row)
            bounded["semantic_result"] = {
                **result_dict,
                "analysis": None,
                "execution_status": "failed_after_live_response",
                "error": "bounded_response_retention_error",
            }
            _case_error(attempt, case_id, "response_retention_error", bounded)
            rows.append(bounded)
            any_error = True
            break
        rows.append(scored)
        append_event(
            attempt,
            "case_result",
            case_id=case_id,
            row_sha256=sha256(canonical(scored)),
            row=scored,
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


def _terminal_result(
    *,
    attempt: Path,
    receipts: Mapping[str, Any],
    rows: list[dict[str, Any]],
    disposition: str,
    dependency: Mapping[str, Any] | None,
    preflight_error: str | None,
) -> dict[str, Any]:
    result = result_payload(
        attempt=attempt,
        receipts=receipts,
        rows=rows,
        disposition=disposition,
        dependency=dependency,
        preflight_error=preflight_error,
        route=ROUTE,
    )
    result_sha = sha256(retained_json(result))
    append_event(attempt, "terminal", disposition=disposition, result_sha256=result_sha)
    write_exclusive(attempt / RESULT_NAME, result)
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
        if _test_owner_home is not None:
            raise SemanticV10Error("test state roots are permanently effect-disabled")
        receipts["source_identity"] = {
            **mapping(receipts["source_identity"], "source identity"),
            "loaded_modules": loaded_source_identity(
                repo_root, mapping(receipts["contract"]["source_bindings"], "sources")
            ),
        }
        validate_dependency_imports(
            mapping(receipts["gate"]["dependency_identity"], "dependency identity")
        )
        validate_route_environment(ROUTE)
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
    except Exception:  # noqa: BLE001 - consumed attempt must terminalize
        current_case = active_case(attempt)
        preflight_passed = any(
            event.get("kind") == "preflight_passed" for event, _ in load_events(attempt)
        )
        preflight_error = (
            "case_processing_error"
            if current_case
            else "post_preflight_error"
            if preflight_passed
            else "post_entry_preflight_error"
        )
        if current_case:
            _case_error(attempt, current_case, preflight_error)
        else:
            append_event(
                attempt,
                "attempt_error" if preflight_passed else "preflight_error",
                classification=preflight_error,
            )
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


def finalize_interrupted(
    *, repo_root: Path, state_root: Path, _test_owner_home: Path | None = None
) -> dict[str, Any]:
    """Provider-free recovery after the runner proves the recorded process is dead."""
    state = ensure_private_directory(
        state_root, create=False, _test_owner_home=_test_owner_home
    )
    attempt = state / ATTEMPT_DIR
    require_mode(attempt / LEDGER_NAME, 0o600, "ledger")
    ledger, _ = read_json(attempt / LEDGER_NAME, "ledger")
    validate_attempt_ledger(ledger, attempt)
    require_recorded_process_inactive(
        mapping(ledger["process_identity"], "process identity")
    )
    receipts = validate_receipts(
        repo_root=repo_root,
        state_root=state,
        require_current_commit=False,
        _test_owner_home=_test_owner_home,
    )
    receipts["source_identity"] = {
        **mapping(receipts["source_identity"], "source identity"),
        "loaded_modules": loaded_source_identity(
            repo_root,
            mapping(receipts["contract"]["source_bindings"], "sources"),
            reject_unexpected=False,
        ),
    }
    for name, payload, label in (
        (CONTRACT_SNAPSHOT, receipts["contract"], "contract snapshot"),
        (REVIEW_SNAPSHOT, receipts["review"], "candidate-review snapshot"),
        (GATE_SNAPSHOT, receipts["gate"], "live-gate snapshot"),
    ):
        path = attempt / name
        if path.exists():
            verify_snapshot(attempt, name, cast(Mapping[str, Any], payload), label)
        else:
            write_exclusive(path, cast(Mapping[str, Any], payload))
    events = load_events(attempt)
    terminal = [event for event, _ in events if event.get("kind") == "terminal"]
    if not terminal:
        if events[-1][0].get("kind") == "case_result":
            row = mapping(events[-1][0].get("row"), "case result")
            append_event(
                attempt,
                "case_scored",
                case_id=str(row.get("case_id")),
                status=str(row.get("status")),
                score_sha256=sha256(canonical(row.get("score"))),
            )
        events = load_events(attempt)
        last = events[-1][0]
        stopped = last.get("kind") in {
            "preflight_error",
            "attempt_error",
            "case_error",
        } or (last.get("kind") == "case_scored" and last.get("status") == "failed")
        if not stopped:
            current = active_case(attempt)
            if current:
                _case_error(
                    attempt,
                    current,
                    "interrupted_effect_unresolved"
                    if _has_open_effect(attempt)
                    else "interrupted_case_incomplete",
                )
            else:
                scored = [
                    event for event, _ in events if event.get("kind") == "case_scored"
                ]
                if not (
                    len(scored) == len(CASE_ORDER)
                    and all(event.get("status") == "passed" for event in scored)
                ):
                    append_event(
                        attempt,
                        "attempt_error"
                        if any(
                            event.get("kind") == "preflight_passed"
                            for event, _ in events
                        )
                        else "preflight_error",
                        classification="interrupted_process_terminated",
                    )
        events = load_events(attempt)
        rows = retained_rows(events)
        disposition = derive_disposition(events, None)
        classification = terminal_error_classification(events)
        return _terminal_result(
            attempt=attempt,
            receipts=receipts,
            rows=rows,
            disposition=disposition,
            dependency=mapping(receipts["gate"]["dependency_identity"], "dependency"),
            preflight_error=classification,
        )
    if len(terminal) != 1:
        raise SemanticV10Error("terminal event cardinality drift")
    rows = retained_rows(events)
    disposition = str(terminal[0].get("disposition"))
    classification = terminal_error_classification(events)
    result = result_payload(
        attempt=attempt,
        receipts=receipts,
        rows=rows,
        disposition=disposition,
        dependency=mapping(receipts["gate"]["dependency_identity"], "dependency"),
        preflight_error=classification,
        route=ROUTE,
    )
    if terminal[0].get("result_sha256") != sha256(retained_json(result)):
        raise SemanticV10Error("terminal recovery result binding drift")
    path = attempt / RESULT_NAME
    if path.exists() or path.is_symlink():
        raise SemanticV10Error("terminal result already exists")
    write_exclusive(path, result)
    return result
