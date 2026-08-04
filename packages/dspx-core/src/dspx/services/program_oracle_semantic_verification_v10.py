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
    LEDGER_SCHEMA,
    RESULT_SCHEMA,
    SEMANTIC_RESULT_KEYS,
    VERIFICATION_SCHEMA,
    derive_disposition,
    ensure_private_directory,
    load_events,
    require_mode,
    verify_snapshot,
)
from dspx.services.program_oracle_semantic_contract_v10 import (
    ATTEMPT_DIR,
    CASE_ORDER,
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
    write_exclusive,
)
from dspx.services.program_oracle_semantic_identity_v10 import ROUTE, validate_receipts


def _validate_result(
    *,
    result: Mapping[str, Any],
    contract: Mapping[str, Any],
    requests: Mapping[str, str],
    disposition: str,
    dependency: Mapping[str, Any],
) -> dict[str, str]:
    if (
        set(result) != EVALUATION_RESULT_KEYS
        or result.get("empirical_gate") != disposition
        or result.get("artifact_integrity_review") != "pending_independent_verification"
    ):
        raise SemanticV10Error("closed terminal-result schema drift")
    preflight_error = result.get("preflight_error")
    if (
        disposition in {"passed", "failed"}
        and preflight_error is not None
        or preflight_error is not None
        and not isinstance(preflight_error, str)
    ):
        raise SemanticV10Error("preflight-error classification drift")
    rows = sequence(result.get("cases"), "result.cases")
    cases = [mapping(case, "case") for case in sequence(contract.get("cases"), "cases")]
    if len(rows) > len(cases):
        raise SemanticV10Error("result case count widened")
    passed_count = 0
    scores: list[Mapping[str, Any]] = []
    observed_models: list[str] = []
    statuses: list[str] = []
    error_reasons: dict[str, str] = {}
    for index, raw_row in enumerate(rows):
        row = mapping(raw_row, f"result.cases[{index}]")
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
        ):
            raise SemanticV10Error("semantic route/authority drift")
        status = str(row.get("status"))
        statuses.append(status)
        observed = str(semantic.get("executed_model") or "").strip()
        if status in {"passed", "failed"}:
            analysis = mapping(semantic.get("analysis"), "semantic_result.analysis")
            expected_score = score_v10(case, analysis)
            if (
                row.get("score") != expected_score
                or status != expected_score.get("status")
                or semantic.get("execution_status") != "succeeded"
                or semantic.get("backend_kind") != "live"
                or semantic.get("preferred_model") != ROUTE["model"]
                or semantic.get("configured_provider") != ROUTE["provider"]
                or semantic.get("configured_model") != ROUTE["model"]
                or semantic.get("executed_provider") is not None
                or semantic.get("fixture_sha256") is not None
                or semantic.get("live_call_succeeded") is not True
                or not observed
                or semantic.get("error") is not None
            ):
                raise SemanticV10Error("case route/score drift")
            scores.append(expected_score)
            passed_count += status == "passed"
            observed_models.append(observed)
        elif status != "error" or row.get("score") is not None:
            raise SemanticV10Error("case terminal class drift")
        elif semantic.get("execution_status") == "succeeded":
            if (
                semantic.get("live_call_succeeded") is not True
                or not isinstance(semantic.get("analysis"), Mapping)
                or semantic.get("error") is not None
            ):
                raise SemanticV10Error("successful-response error evidence drift")
            route_ok = (
                semantic.get("backend_kind") == "live"
                and semantic.get("preferred_model") == ROUTE["model"]
                and semantic.get("configured_provider") == ROUTE["provider"]
                and semantic.get("configured_model") == ROUTE["model"]
                and semantic.get("executed_provider") is None
                and semantic.get("fixture_sha256") is None
                and bool(observed)
            )
            if not route_ok:
                error_reasons[case_id] = "route_identity_error"
            elif observed_models and observed not in set(observed_models):
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
        if status == "error" and observed:
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
    if (
        result.get("route") != expected_route
        or result.get("dependency_identity") != dependency
        or (disposition != "error" and len(set(observed_models)) > 1)
    ):
        raise SemanticV10Error("route/dependency identity drift")
    expected_summary = {
        "expected_case_count": len(CASE_ORDER),
        "reached_case_count": len(rows),
        "passed_case_count": passed_count,
        "macro_score": sum(float(score.get("score", 0.0)) for score in scores)
        / len(CASE_ORDER),
    }
    if (
        result.get("summary") != expected_summary
        or result.get("attempt") != ATTEMPT_PROJECTION
    ):
        raise SemanticV10Error("summary/attempt projection drift")
    if result.get("effects") != EFFECT_PROJECTION:
        raise SemanticV10Error("effect boundary drift")
    expected_claims = {
        "exact_four_case_empirical_gate_passed": disposition == "passed",
        **mapping(contract.get("nonclaims"), "nonclaims"),
        "rocs_conformance": False,
        "shared_oracle_publication": False,
    }
    if result.get("claims") != expected_claims:
        raise SemanticV10Error("terminal nonclaim drift")
    return error_reasons


def _validate_events(
    events: Sequence[tuple[Mapping[str, Any], str]],
    result: Mapping[str, Any] | None,
    requests: Mapping[str, str],
    preflight_bindings: Mapping[str, str],
    error_reasons: Mapping[str, str],
) -> None:
    started: list[str] = []
    effects: dict[str, str] = {}
    rows = (
        [mapping(row, "case row") for row in sequence(result.get("cases"), "cases")]
        if result is not None
        else []
    )
    row_by_case = {str(row.get("case_id")): row for row in rows}
    observed_effects: dict[str, tuple[int, int, bool]] = {}
    case_errors: set[str] = set()
    terminal_count = 0
    preflight_count = 0
    stopped = False
    active_case: str | None = None
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
        if kind == "attempt_consumed":
            if (
                index != 0
                or event.get("evaluation_processes") != 1
                or event.get("retry_allowed") is not False
            ):
                raise SemanticV10Error("attempt-consumed event drift")
            continue
        if kind == "preflight_passed":
            preflight_count += 1
            if preflight_count != 1 or any(
                event.get(field) != digest
                for field, digest in preflight_bindings.items()
            ):
                raise SemanticV10Error("preflight binding/cardinality drift")
            continue
        case_id = str(event.get("case_id") or "")
        if kind == "case_started":
            if (
                stopped
                or active_case is not None
                or preflight_count != 1
                or len(started) >= len(CASE_ORDER)
                or case_id != CASE_ORDER[len(started)]
                or event.get("request_sha256") != requests.get(case_id)
            ):
                raise SemanticV10Error("reached-case sequence/request drift")
            started.append(case_id)
            active_case = case_id
        elif kind == "effect_possible":
            token = str(event.get("effect_token") or "")
            if (
                case_id not in started
                or active_case != case_id
                or case_id in effects
                or not token
                or event.get("request_sha256") != requests.get(case_id)
                or event.get("generate_invocation") != 1
            ):
                raise SemanticV10Error("provider-effect cardinality drift")
            effects[case_id] = token
        elif kind == "effect_observed":
            if (
                effects.get(case_id) != event.get("effect_token")
                or event.get("generate_invocation_delta") not in {0, 1}
                or event.get("history_delta") != event.get("generate_invocation_delta")
                or not isinstance(event.get("response_attributable"), bool)
            ):
                raise SemanticV10Error("effect-observation drift")
            observed_effects[case_id] = (
                int(event["generate_invocation_delta"]),
                int(event["history_delta"]),
                bool(event["response_attributable"]),
            )
        elif kind == "case_scored":
            row = row_by_case.get(case_id)
            digest = event.get("score_sha256")
            digest_ok = (
                isinstance(digest, str)
                and len(digest) == 64
                and all(character in "0123456789abcdef" for character in digest)
            )
            if (
                event.get("status") not in {"passed", "failed"}
                or active_case != case_id
                or observed_effects.get(case_id) != (1, 1, True)
                or not digest_ok
                or result is not None
                and (
                    row is None
                    or row.get("status") != event.get("status")
                    or digest != sha256(canonical(row.get("score")))
                )
            ):
                raise SemanticV10Error("scored-event/result drift")
            stopped = stopped or event.get("status") == "failed"
            active_case = None
        elif kind == "case_error":
            if (
                active_case != case_id
                or case_id not in started
                or not str(event.get("classification") or "")
            ):
                raise SemanticV10Error("case-error event drift")
            row = row_by_case.get(case_id)
            if row is not None and row.get("status") != "error":
                raise SemanticV10Error("case-error/result class drift")
            reason = error_reasons.get(case_id)
            expected = (
                "typed_response_error"
                if reason == "non_success" and case_id in observed_effects
                else "effect_outcome_unresolved"
                if reason == "non_success"
                else reason
            )
            if row is not None and event.get("classification") != expected:
                raise SemanticV10Error("case-error classification was not re-derived")
            case_errors.add(case_id)
            stopped = True
            active_case = None
        elif kind == "preflight_error" and not str(event.get("classification") or ""):
            raise SemanticV10Error("preflight-error event drift")
        elif kind == "terminal":
            terminal_count += 1
            if index != len(events) - 1:
                raise SemanticV10Error("terminal event is not last")
    missing_effects = [case for case in started if case not in effects]
    if (
        preflight_count > 1
        or terminal_count > 1
        or (result is not None and terminal_count != 1)
        or len(missing_effects) > 1
        or bool(missing_effects)
        and (missing_effects[0] != started[-1] or missing_effects[0] not in case_errors)
    ):
        raise SemanticV10Error("terminal/effect event cardinality drift")
    if result is not None:
        row_ids = [str(row.get("case_id")) for row in rows]
        if not set(error_reasons).issubset(case_errors):
            raise SemanticV10Error("error row lacks its derived case-error event")
        if row_ids != started[: len(row_ids)] or len(started) - len(row_ids) > 1:
            raise SemanticV10Error("event/result reached-case drift")


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
    if ledger != {
        "schema_version": LEDGER_SCHEMA,
        "ak_task_id": TASK_ID,
        "status": "consumed",
        "maximum_evaluation_processes": 1,
        "retry_allowed": False,
        "root": str(attempt),
    }:
        raise SemanticV10Error("attempt ledger drift")
    receipts = validate_receipts(
        repo_root=repo_root,
        state_root=state,
        require_current_commit=False,
        _test_owner_home=_test_owner_home,
    )
    events = load_events(attempt)
    if not events or events[0][0].get("kind") != "attempt_consumed":
        raise SemanticV10Error("initial attempt event missing")
    preflight_reached = any(
        event.get("kind") == "preflight_passed" for event, _ in events
    )
    result_path = attempt / RESULT_NAME
    result: dict[str, Any] | None = None
    result_hash: str | None = None
    if result_path.exists():
        require_mode(result_path, 0o600, "result")
        result, raw = read_json(result_path, "result")
        result_hash = sha256(raw)
    if result is not None or preflight_reached:
        verify_snapshot(
            attempt,
            "contract-snapshot.json",
            receipts["contract"],
            "contract snapshot",
        )
        verify_snapshot(
            attempt,
            "candidate-review-snapshot.json",
            receipts["review"],
            "candidate-review snapshot",
        )
        verify_snapshot(
            attempt,
            "live-gate-snapshot.json",
            receipts["gate"],
            "live-gate snapshot",
        )
    if result is not None:
        if (
            result.get("schema_version") != RESULT_SCHEMA
            or result.get("ak_task_id") != TASK_ID
            or result.get("contract_sha256") != receipts["contract_sha256"]
            or result.get("candidate_review_sha256") != receipts["review_sha256"]
            or result.get("live_gate_sha256") != receipts["gate_sha256"]
            or result.get("source_identity") != receipts["source_identity"]
            or result.get("request_hashes") != receipts["request_hashes"]
        ):
            raise SemanticV10Error("terminal result binding drift")
        history = {
            f"{index:06d}.json": digest
            for index, (event, digest) in enumerate(events)
            if event.get("kind") != "terminal"
        }
        if result.get("event_history_sha256") != history:
            raise SemanticV10Error("result event-history binding drift")
    empirical = derive_disposition(events, result)
    error_reasons = (
        _validate_result(
            result=result,
            contract=receipts["contract"],
            requests=receipts["request_hashes"],
            disposition=empirical,
            dependency=mapping(
                receipts["gate"]["dependency_identity"], "dependency_identity"
            ),
        )
        if result is not None
        else {}
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
        error_reasons,
    )
    if any(path.name not in ATTEMPT_MEMBER_NAMES for path in attempt.iterdir()):
        raise SemanticV10Error("unexpected retained artifact")
    terminal_events = [event for event, _ in events if event.get("kind") == "terminal"]
    if terminal_events and terminal_events[0].get("result_sha256") != result_hash:
        raise SemanticV10Error("terminal result hash drift")
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
    if path.exists():
        require_mode(path, 0o600, "independent verification")
        retained, _ = read_json(path, "independent verification")
        if retained != verification:
            raise SemanticV10Error("retained verification drift")
        return retained
    write_exclusive(path, verification)
    return verification
