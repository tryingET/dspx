# summary: "Provider-free retained packet and behavioral re-derivation for task-4643 semantic v10."
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_artifacts_v10 import (
    ATTEMPT_MEMBER_NAMES,
    ATTEMPT_PROJECTION,
    EFFECT_PROJECTION,
    EVALUATION_RESULT_KEYS,
    EVENT_FACT_KEYS,
    RESULT_SCHEMA,
    SEMANTIC_RESULT_KEYS,
    VERIFICATION_SCHEMA,
    _admit_event,
    derive_disposition,
    ensure_private_directory,
    load_events,
    require_mode,
    started_cases,
    verify_snapshot,
)
from dspx.services.program_oracle_semantic_contract_v10 import (
    ATTEMPT_DIR,
    CASE_ORDER,
    EVENT_DIR,
    LEDGER_NAME,
    RESULT_NAME,
    TASK_ID,
    VERIFICATION_NAME,
    SemanticV10Error,
    canonical,
    mapping,
    read_json,
    score_v10,
    sequence,
    sha256,
    validate_attempt_ledger,
    write_exclusive,
)
from dspx.services.program_oracle_semantic_identity_v10 import (
    ROUTE,
    expected_loaded_source_identity,
    validate_receipts,
)
from dspx.services.program_oracle_semantic_verifier_projection_v10 import (
    result_error_projection,
    route_fields_are_live,
    rowless_case_error_is_consistent,
)


def _validate_result(
    *,
    result: Mapping[str, Any],
    contract: Mapping[str, Any],
    requests: Mapping[str, str],
    disposition: str,
    dependency: Mapping[str, Any],
    reached_count: int,
) -> dict[str, str]:
    if (
        set(result) != EVALUATION_RESULT_KEYS
        or result.get("empirical_gate") != disposition
        or result.get("artifact_integrity_review") != "pending_independent_verification"
    ):
        raise SemanticV10Error("closed terminal-result schema drift")
    error = result.get("preflight_error")
    if (
        disposition in {"passed", "failed"}
        and error is not None
        or error is not None
        and (not isinstance(error, str) or not error)
    ):
        raise SemanticV10Error("preflight-error classification drift")
    rows = sequence(result.get("cases"), "result.cases")
    cases = [
        mapping(value, "case") for value in sequence(contract.get("cases"), "cases")
    ]
    if len(rows) > len(cases):
        raise SemanticV10Error("result case count widened")
    scores: list[Mapping[str, Any]] = []
    statuses: list[str] = []
    observed_models: list[str] = []
    error_reasons: dict[str, str] = {}
    passed_count = 0
    for index, value in enumerate(rows):
        row = mapping(value, f"result.cases[{index}]")
        if set(row) != {
            "case_id",
            "request_sha256",
            "semantic_result",
            "score",
            "status",
        }:
            raise SemanticV10Error("closed case-row schema drift")
        case = cases[index]
        case_id = str(case.get("id"))
        if row.get("case_id") != case_id or row.get("request_sha256") != requests.get(
            case_id
        ):
            raise SemanticV10Error("case identity/request drift")
        semantic = mapping(row.get("semantic_result"), "semantic_result")
        if (
            set(semantic) != SEMANTIC_RESULT_KEYS
            or semantic.get("request_sha256") != requests.get(case_id)
            or semantic.get("schema_version")
            != "dspx-program-oracle-semantic-result-v1"
            or semantic.get("authority") != "local_empirical_advisory_only"
            or not route_fields_are_live(semantic, ROUTE)
        ):
            raise SemanticV10Error("semantic live-route/authority drift")
        status = str(row.get("status"))
        statuses.append(status)
        observed = str(semantic.get("executed_model") or "").strip()
        if status in {"passed", "failed"}:
            analysis = mapping(semantic.get("analysis"), "semantic_result.analysis")
            expected = score_v10(case, analysis)
            if (
                row.get("score") != expected
                or status != expected.get("status")
                or semantic.get("execution_status") != "succeeded"
                or semantic.get("live_call_succeeded") is not True
                or not observed
                or semantic.get("error") is not None
            ):
                raise SemanticV10Error("case route/score drift")
            scores.append(expected)
            passed_count += status == "passed"
        elif status != "error" or row.get("score") is not None:
            raise SemanticV10Error("case terminal class drift")
        elif not observed:
            error_reasons[case_id] = "route_identity_error"
        elif semantic.get("error") == "bounded_response_retention_error":
            if semantic.get("analysis") is not None:
                raise SemanticV10Error("bounded response retained analysis")
            error_reasons[case_id] = "response_retention_error"
        elif semantic.get("execution_status") == "succeeded":
            if (
                semantic.get("live_call_succeeded") is not True
                or not isinstance(semantic.get("analysis"), Mapping)
                or semantic.get("error") is not None
            ):
                raise SemanticV10Error("successful-response error evidence drift")
            if observed_models and observed not in set(observed_models):
                error_reasons[case_id] = "executed_model_drift"
            else:
                try:
                    score_v10(case, mapping(semantic["analysis"], "analysis"))
                except (TypeError, ValueError):
                    error_reasons[case_id] = "response_schema_error"
                else:
                    raise SemanticV10Error("successful response was relabeled as error")
        elif (
            semantic.get("analysis") is not None
            or not str(semantic.get("error") or "").strip()
            or semantic.get("execution_status")
            not in {"failed_before_live_success", "failed_after_live_response"}
            or semantic.get("live_call_succeeded")
            is not (semantic.get("execution_status") == "failed_after_live_response")
        ):
            raise SemanticV10Error("typed error attribution drift")
        else:
            error_reasons[case_id] = "non_success"
        if observed:
            observed_models.append(observed)
    if disposition == "passed" and (
        len(rows) != len(CASE_ORDER) or statuses != ["passed"] * len(CASE_ORDER)
    ):
        raise SemanticV10Error("passing disposition lacks four passing rows")
    if disposition == "failed" and (not rows or statuses[-1] != "failed"):
        raise SemanticV10Error("failed disposition lacks a scored failure")
    expected_route = {
        "requested": ROUTE,
        "configured_provider": ROUTE["provider"] if rows else None,
        "configured_model": ROUTE["model"] if rows else None,
        "observed_models": observed_models,
    }
    expected_summary = {
        "expected_case_count": len(CASE_ORDER),
        "reached_case_count": reached_count,
        "passed_case_count": passed_count,
        "macro_score": sum(float(score.get("score", 0.0)) for score in scores)
        / len(CASE_ORDER),
    }
    if (
        result.get("route") != expected_route
        or result.get("dependency_identity") != dependency
        or result.get("summary") != expected_summary
        or result.get("attempt") != ATTEMPT_PROJECTION
        or (disposition != "error" and len(set(observed_models)) > 1)
    ):
        raise SemanticV10Error("route/dependency/summary drift")
    if result.get("effects") != EFFECT_PROJECTION:
        raise SemanticV10Error("effect boundary drift")
    claims = {
        "exact_four_case_empirical_gate_passed": disposition == "passed",
        **mapping(contract.get("nonclaims"), "nonclaims"),
        "rocs_conformance": False,
        "shared_oracle_publication": False,
    }
    if result.get("claims") != claims:
        raise SemanticV10Error("terminal nonclaim drift")
    return error_reasons


def _validate_events(
    events: Sequence[tuple[dict[str, Any], str]],
    result: Mapping[str, Any],
    requests: Mapping[str, str],
    bindings: Mapping[str, str],
    error_reasons: Mapping[str, str],
) -> None:
    prefix: list[dict[str, Any]] = []
    started: list[str] = []
    effects: dict[str, str] = {}
    observed: dict[str, tuple[int, int, bool]] = {}
    result_rows = [
        mapping(row, "result row") for row in sequence(result.get("cases"), "cases")
    ]
    retained: list[dict[str, Any]] = []
    active: str | None = None
    preflight_count = terminal_count = 0
    for index, (event, _) in enumerate(events):
        kind = str(event.get("kind") or "")
        if kind not in EVENT_FACT_KEYS or set(event) != {
            "schema_version",
            "ak_task_id",
            "sequence",
            "kind",
            *EVENT_FACT_KEYS[kind],
        }:
            raise SemanticV10Error("closed event schema drift")
        facts = {key: event[key] for key in EVENT_FACT_KEYS[kind]}
        _admit_event(prefix, kind, facts)
        prefix.append(event)
        if kind == "attempt_consumed":
            if (
                index != 0
                or event.get("evaluation_processes") != 1
                or event.get("retry_allowed") is not False
            ):
                raise SemanticV10Error("attempt-consumed event drift")
        elif kind == "preflight_passed":
            preflight_count += 1
            if preflight_count != 1 or any(
                event.get(key) != value for key, value in bindings.items()
            ):
                raise SemanticV10Error("preflight binding/cardinality drift")
        elif kind == "case_started":
            case_id = str(event.get("case_id") or "")
            if (
                active is not None
                or preflight_count != 1
                or len(started) >= len(CASE_ORDER)
                or case_id != CASE_ORDER[len(started)]
                or event.get("request_sha256") != requests.get(case_id)
            ):
                raise SemanticV10Error("reached-case sequence/request drift")
            started.append(case_id)
            active = case_id
        elif kind == "effect_possible":
            case_id = str(event.get("case_id") or "")
            token = str(event.get("effect_token") or "")
            if (
                active != case_id
                or case_id in effects
                or not token
                or event.get("request_sha256") != requests.get(case_id)
                or event.get("generate_invocation") != 1
            ):
                raise SemanticV10Error("provider-effect cardinality drift")
            effects[case_id] = token
        elif kind == "effect_observed":
            case_id = str(event.get("case_id") or "")
            delta = event.get("generate_invocation_delta")
            if (
                active != case_id
                or case_id in observed
                or effects.get(case_id) != event.get("effect_token")
                or delta not in {0, 1}
                or event.get("history_delta") != delta
                or not isinstance(event.get("response_attributable"), bool)
            ):
                raise SemanticV10Error("effect-observation drift")
            observed[case_id] = (
                int(delta),
                int(delta),
                bool(event["response_attributable"]),
            )
        elif kind == "case_result":
            case_id = str(event.get("case_id") or "")
            row = mapping(event.get("row"), "case-result row")
            if (
                active != case_id
                or observed.get(case_id) != (1, 1, True)
                or event.get("row_sha256") != sha256(canonical(row))
                or row.get("case_id") != case_id
            ):
                raise SemanticV10Error("case-result evidence drift")
            retained.append(row)
        elif kind == "case_scored":
            case_id = str(event.get("case_id") or "")
            row = retained[-1] if retained else None
            if (
                active != case_id
                or row is None
                or row.get("case_id") != case_id
                or event.get("status") not in {"passed", "failed"}
                or row.get("status") != event.get("status")
                or event.get("score_sha256") != sha256(canonical(row.get("score")))
            ):
                raise SemanticV10Error("scored-event/result drift")
            active = None
        elif kind == "case_error":
            case_id = str(event.get("case_id") or "")
            event_row = event.get("row")
            if (
                active != case_id
                or not str(event.get("classification") or "")
                or event_row is None
                and not rowless_case_error_is_consistent(
                    event.get("classification"),
                    effect_open=case_id in effects and case_id not in observed,
                )
            ):
                raise SemanticV10Error("case-error event drift")
            if event_row is not None:
                row = mapping(event_row, "case-error row")
                semantic = mapping(row.get("semantic_result"), "case-error semantic")
                response_attributable = (
                    semantic.get("execution_status")
                    in {"succeeded", "failed_after_live_response"}
                    and semantic.get("live_call_succeeded") is True
                )
                expected_observation = (
                    (1, 1, True) if response_attributable else (0, 0, False)
                )
                reason = error_reasons.get(case_id)
                expected = (
                    "typed_response_error"
                    if reason == "non_success" and case_id in observed
                    else "effect_outcome_unresolved"
                    if reason == "non_success"
                    else reason
                )
                if (
                    observed.get(case_id) != expected_observation
                    or row.get("status") != "error"
                    or event.get("classification") != expected
                ):
                    raise SemanticV10Error("case-error classification drift")
                retained.append(row)
            active = None
        elif kind in {"preflight_error", "attempt_error"}:
            if not str(event.get("classification") or ""):
                raise SemanticV10Error("attempt-error classification drift")
        elif kind == "terminal":
            terminal_count += 1
            if index != len(events) - 1:
                raise SemanticV10Error("terminal event is not last")
    if terminal_count != 1 or preflight_count > 1 or retained != result_rows:
        raise SemanticV10Error("terminal/result event cardinality drift")
    if [str(row.get("case_id")) for row in retained] != started[: len(retained)] or len(
        started
    ) - len(retained) > 1:
        raise SemanticV10Error("event/result reached-case drift")
    if not set(error_reasons).issubset(
        {
            str(event.get("case_id"))
            for event, _ in events
            if event.get("kind") == "case_error"
        }
    ):
        raise SemanticV10Error("error row lacks case-error event")


def verify_evaluation(
    *, repo_root: Path, state_root: Path, _test_owner_home: Path | None = None
) -> dict[str, Any]:
    state = ensure_private_directory(
        state_root, create=False, _test_owner_home=_test_owner_home
    )
    attempt = state / ATTEMPT_DIR
    require_mode(state, 0o700, "task state")
    require_mode(attempt, 0o700, "attempt root")
    require_mode(attempt / LEDGER_NAME, 0o600, "ledger")
    ledger, ledger_raw = read_json(attempt / LEDGER_NAME, "ledger")
    validate_attempt_ledger(ledger, attempt)
    receipts = validate_receipts(
        repo_root=repo_root,
        state_root=state,
        require_current_commit=False,
        _test_owner_home=_test_owner_home,
    )
    events = load_events(attempt)
    if not events or events[0][0].get("kind") != "attempt_consumed":
        raise SemanticV10Error("initial attempt event missing")
    terminal = [event for event, _ in events if event.get("kind") == "terminal"]
    if len(terminal) != 1 or events[-1][0].get("kind") != "terminal":
        raise SemanticV10Error("attempt is not terminal; finalize interruption first")
    result_path = attempt / RESULT_NAME
    try:
        result_path.lstat()
    except OSError as exc:
        raise SemanticV10Error("terminal result missing") from exc
    require_mode(result_path, 0o600, "result")
    result, result_raw = read_json(result_path, "result")
    result_hash = sha256(result_raw)
    if terminal[0].get("result_sha256") != result_hash:
        raise SemanticV10Error("terminal result hash drift")
    for name, payload, label in (
        ("contract-snapshot.json", receipts["contract"], "contract snapshot"),
        (
            "candidate-review-snapshot.json",
            receipts["review"],
            "candidate-review snapshot",
        ),
        ("live-gate-snapshot.json", receipts["gate"], "live-gate snapshot"),
    ):
        verify_snapshot(attempt, name, payload, label)
    expected_source = {
        **mapping(receipts["source_identity"], "source identity"),
        "loaded_modules": expected_loaded_source_identity(
            repo_root,
            mapping(receipts["contract"]["source_bindings"], "sources"),
        ),
    }
    if (
        result.get("schema_version") != RESULT_SCHEMA
        or result.get("ak_task_id") != TASK_ID
        or result.get("contract_sha256") != receipts["contract_sha256"]
        or result.get("candidate_review_sha256") != receipts["review_sha256"]
        or result.get("live_gate_sha256") != receipts["gate_sha256"]
        or result.get("source_identity") != expected_source
        or result.get("request_hashes") != receipts["request_hashes"]
    ):
        raise SemanticV10Error("terminal result binding drift")
    history = {
        f"{index:06d}.json": digest
        for index, (event, digest) in enumerate(events)
        if event.get("kind") != "terminal"
    }
    if result.get("event_history_sha256") != history or result.get(
        "preflight_error"
    ) != result_error_projection(events):
        raise SemanticV10Error("result event-history/classification binding drift")
    empirical = derive_disposition(events, result)
    reasons = _validate_result(
        result=result,
        contract=receipts["contract"],
        requests=receipts["request_hashes"],
        disposition=empirical,
        dependency=mapping(receipts["gate"]["dependency_identity"], "dependency"),
        reached_count=len(started_cases(events)),
    )
    _validate_events(
        events,
        result,
        receipts["request_hashes"],
        {
            "contract_sha256": receipts["contract_sha256"],
            "candidate_review_sha256": receipts["review_sha256"],
            "live_gate_sha256": receipts["gate_sha256"],
        },
        reasons,
    )
    for path in attempt.iterdir():
        if path.name not in ATTEMPT_MEMBER_NAMES:
            raise SemanticV10Error("unexpected retained artifact")
        expected_mode = 0o700 if path.name == EVENT_DIR else 0o600
        require_mode(path, expected_mode, f"attempt member {path.name}")
    verification = {
        "schema_version": VERIFICATION_SCHEMA,
        "artifact_integrity_review": "accepted",
        "empirical_gate": empirical,
        "ak_task_id": TASK_ID,
        "contract_sha256": receipts["contract_sha256"],
        "candidate_review_sha256": receipts["review_sha256"],
        "live_gate_sha256": receipts["gate_sha256"],
        "ledger_sha256": sha256(ledger_raw),
        "result_sha256": result_hash,
        "event_sha256": {
            f"{index:06d}.json": digest for index, (_, digest) in enumerate(events)
        },
        "provider_invoked_by_verifier": False,
        "terminal_evidence_modified": False,
        "maximum_claim": "exact_four_case_one_process_dspx_empirical_gate_only",
    }
    path = attempt / VERIFICATION_NAME
    if path.exists() or path.is_symlink():
        require_mode(path, 0o600, "independent verification")
        retained, _ = read_json(path, "independent verification")
        if retained != verification:
            raise SemanticV10Error("retained verification drift")
        return retained
    write_exclusive(path, verification)
    return verification
