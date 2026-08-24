# summary: "Provider-free candidate projection and exact retained-tree grammar."
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_artifacts_v11 import (
    LEDGER_KEYS,
    MAX_RETAINED_BYTES,
    ConsumedAttempt,
    TaskBinding,
    load_consumed_attempt,
    read_private_json,
    require_consumed_attempt,
)
from dspx.services.program_oracle_semantic_contract_v11 import (
    CASE_ORDER,
    SemanticV11Error,
    load_bound_cases,
    load_candidate,
    semantic_request_sha256,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CANDIDATE_REVIEW_NAME,
    LEDGER_NAME,
    LEDGER_SCHEMA,
    LIVE_GATE_NAME,
    LIVE_GATE_SCHEMA,
    GATE5_REJECTION_REASON_CODES,
    PROVIDER_OUTCOMES_NAME,
    REQUIRED_LIVE_COMPLETION_KIND,
    RESULT_FRAGMENTS_NAME,
    RESULT_NAME,
    RESULT_SCHEMA,
    VERIFICATION_NAME,
    VERIFICATION_SCHEMA,
)

from dspx.services.program_oracle_semantic_review_grammar_v11 import (
    valid_candidate_review,
)

_FORBIDDEN_RETAINED = (
    b'"access_token"',
    b'"refresh_token"',
    b'"api_key"',
    b'"headers"',
    b'"credential"',
    b'"exception"',
    b'"traceback"',
    b'"diagnostic"',
    b'"diagnostics"',
    b'"details"',
    b'"command"',
    b'"checked_at"',
    b'"checked_by"',
    b'"url"',
    b'"body"',
    b'"raw_output"',
    b'"prompt"',
    b"Traceback (most recent call last)",
    b"https://",
    b"http://",
    b"/home/",
    b'"/var/',
)
_JOURNALS = tuple(
    f"{ordinal:02d}-{case_id}" for ordinal, case_id in enumerate(CASE_ORDER, start=1)
)
_EVENT_RE = re.compile(r"[0-9]{6}\.json")
_LIVE_GATE_KEYS = {
    "schema_version",
    "artifact_kind",
    "live_task_id",
    "gate_3_task_id",
    "state_root_identity_sha256",
    "task_entity_version",
    "gate_4_task_contract_sha256",
    "gate_4_guardrails_sha256",
    "candidate_review_evidence_id",
    "candidate_review_sha256",
    "operator_evidence_id",
    "operator_evidence_sha256",
    "candidate_commit",
    "candidate_tree",
    "candidate_source_manifest_sha256",
    "contract_sha256",
    "route",
    "maximum_corpus_processes",
    "maximum_effect_capable_delegations_per_request",
    "maximum_health_probes",
    "maximum_dspx_managed_retries",
    "fallback_allowed",
}
_RESULT_KEYS = {
    "schema_version",
    "artifact_kind",
    "live_task_id",
    "task_binding",
    "ledger_sha256",
    "root_binding_sha256",
    "candidate_commit",
    "candidate_tree",
    "candidate_source_manifest_sha256",
    "contract_sha256",
    "candidate_review_sha256",
    "live_gate_sha256",
    "authority_snapshot_sha256",
    "provider_owner_source_identity_sha256",
    "dependency_identity_sha256",
    "artifact_integrity_review",
    "empirical_gate",
    "cases",
    "operation_counts",
    "observed_model",
    "fixture_only",
    "v11_authorized",
    "live_execution_authorized",
}
_OPERATION_KEYS = {
    "corpus_processes",
    "reached_requests",
    "admitted_invocations",
    "dspx_generate_calls",
    "effect_capable_delegations",
    "receipt_journals",
    "separate_health_probes",
    "dspx_managed_retries",
    "fallback_routes",
    "provider_transport_calls",
}
_CASE_SUMMARY_KEYS = {
    "case_id",
    "case_ordinal",
    "semantic_request_sha256",
    "reservation_sha256",
    "terminal_event_sha256",
    "semantic_result_sha256",
    "semantic_outcome",
    "provider_outcome",
    "observed_model",
    "dspx_generate_entered",
    "invocation_admitted",
    "effect_capable_delegations",
    "receipt_journal",
    "clean_terminal_order_proven",
}
_SETUP_FRAGMENT_KEYS = {
    "schema_version",
    "artifact_kind",
    "live_task_id",
    "setup_stage",
    "external_effect_possible",
    "empirical_disposition",
    "reason",
    "dspx_generate_entered",
    "invocation_admitted",
    "effect_capable_delegations",
    "fixture_only",
    "v11_authorized",
    "live_execution_authorized",
}
_CASE_TERMINAL_MARKER_KEYS = {
    "schema_version",
    "artifact_kind",
    "live_task_id",
    "case_id",
    "case_ordinal",
    "stage",
    "case_result_fragment_sha256",
    "external_effect_possible",
    "empirical_disposition",
    "reason",
    "fixture_only",
    "v11_authorized",
    "live_execution_authorized",
}
_CASE_FRAGMENT_KEYS = {
    "schema_version",
    "artifact_kind",
    "case_phase",
    "live_task_id",
    "case_id",
    "case_ordinal",
    "semantic_request_sha256",
    "reservation_id",
    "reservation_sha256",
    "journal_present",
    "dspx_generate_entered",
    "invocation_admitted",
    "effect_capable_delegations",
    "clean_terminal_order_proven",
    "terminal_event_sha256",
    "semantic_result",
    "semantic_result_sha256",
    "observed_model",
    "provider_outcome",
    "fixture_only",
    "v11_authorized",
    "live_execution_authorized",
}
_SEMANTIC_KEYS = {"case_id", "outcome", "analysis", "score", "analysis_sha256"}
_PROJECTION_KEYS = {
    "schema_version",
    "provider_outcome_receipt",
    "request_acknowledged",
    "external_effect_possible",
    "producer_terminal",
    "empirical_disposition",
    "reason",
    "fixture_only",
    "v11_authorized",
    "live_execution_authorized",
}
_EMPIRICAL_DISPOSITIONS = {"effect_indeterminate", "error", "failed", "passed"}
_GIT_ID_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


_VERIFICATION_KEYS = {
    "schema_version",
    "artifact_kind",
    "gate5_task_id",
    "gate5_evidence_id",
    "gate5_task_contract_sha256",
    "gate5_guardrails_sha256",
    "gate5_evidence_sha256",
    "live_task_id",
    "artifact_integrity_review",
    "empirical_gate",
    "result_sha256",
    "ledger_sha256",
    "candidate_review_sha256",
    "live_gate_sha256",
    "candidate_commit",
    "candidate_tree",
    "candidate_source_manifest_sha256",
    "contract_sha256",
    "provider_owner_source_identity_sha256",
    "dependency_identity_sha256",
    "operation_counts",
    "privacy",
    "provider_invoked",
    "terminal_evidence_modified",
    "fixture_only",
    "v11_authorized",
    "live_execution_authorized",
    "authority_granted",
}
_REJECTED_VERIFICATION_KEYS = _VERIFICATION_KEYS | {"rejection_reason_code"}


_RESERVATION_WRAPPER_KEYS = {
    "schema_version",
    "reservation_id",
    "artifact_verification",
    "reservation",
}
_RESERVATION_KEYS = {
    "schema_version",
    "consumer_task_id",
    "ledger_sha256",
    "process_id",
    "case_id",
    "logical_request_id",
    "transport_gate_id",
    "semantic_request_sha256",
    "contract_sha256",
    "mode",
    "requested_route",
    "resolved_route",
    "endpoint_origin_sha256",
    "source_identity",
    "dependency_identity",
}
_EVENT_ENVELOPE_KEYS = {
    "schema_version",
    "reservation_id",
    "sequence",
    "previous_event_sha256",
    "producer",
    "source_identity_sha256",
    "dependency_identity_sha256",
    "event",
}
_EVENT_KEYS = {
    "kind",
    "gate_ordinal",
    "status_class",
    "error_class",
    "protocol_event",
    "response_id_sha256",
    "observed_model",
}


def candidate_manifest(repo_root: Path) -> dict[str, Any]:
    _, _, contract_hash = load_candidate(repo_root)
    from dspx.services.program_oracle_semantic_evaluation_v11 import (
        normalized_semantic_request,
    )

    requests: dict[str, dict[str, int | str]] = {}
    for case in load_bound_cases(repo_root):
        request = case.materialized_request()
        requests[case.case_id] = {
            "case_ordinal": case.case_ordinal,
            "oracle_request_sha256": request.request_sha256,
            "semantic_request_sha256": semantic_request_sha256(
                normalized_semantic_request(request)
            ),
        }
    if tuple(requests) != CASE_ORDER:
        raise SemanticV11Error("candidate request order drift")
    return {
        "schema_version": VERIFICATION_SCHEMA,
        "artifact_kind": "candidate_manifest",
        "artifact_integrity_review": "not_evaluated",
        "empirical_gate": "not_evaluated",
        "provider_invoked": False,
        "terminal_evidence_modified": False,
        "contract_sha256": contract_hash,
        "requests": requests,
        "fixture_only": True,
        "v11_authorized": False,
        "live_execution_authorized": False,
        "authority_granted": False,
    }


def verify_task_binding_fixture(state_root: Path, live_task_id: int) -> dict[str, Any]:
    binding = TaskBinding.create(
        live_task_id, REQUIRED_LIVE_COMPLETION_KIND, state_root
    )
    attempt = load_consumed_attempt(state_root, live_task_id)
    return {
        "binding": binding.payload(),
        "ledger_sha256": attempt.ledger_sha256,
        "retry_allowed": False,
        "maximum_evaluation_processes": 1,
        "provider_invoked": False,
        "fixture_only": True,
        "v11_authorized": False,
        "live_execution_authorized": False,
        "authority_granted": False,
    }


def _allowed_shape(relative: str, *, include_verification: bool) -> bool:
    if relative in {
        ".",
        LEDGER_NAME,
        CANDIDATE_REVIEW_NAME,
        LIVE_GATE_NAME,
        RESULT_NAME,
        PROVIDER_OUTCOMES_NAME,
        RESULT_FRAGMENTS_NAME,
    }:
        return True
    if relative == VERIFICATION_NAME:
        return include_verification
    if relative.startswith(f"{RESULT_FRAGMENTS_NAME}/"):
        name = relative.split("/", 1)[1]
        return name == "00-setup.json" or name in {
            *(f"{ordinal:02d}-case.json" for ordinal in range(1, 5)),
            *(f"{ordinal:02d}-terminal.json" for ordinal in range(1, 5)),
        }
    if not relative.startswith(f"{PROVIDER_OUTCOMES_NAME}/"):
        return False
    parts = relative.split("/")
    if len(parts) < 2 or parts[1] not in _JOURNALS:
        return False
    if len(parts) == 2:
        return True
    if len(parts) == 3:
        return parts[2] in {
            "reservation.json",
            "events",
            "poisoned.json",
            "inflight.json",
        }
    return (
        len(parts) == 4 and parts[2] == "events" and bool(_EVENT_RE.fullmatch(parts[3]))
    )


def _validate_json_shape(relative: str, value: dict[str, Any]) -> None:
    if relative == LEDGER_NAME:
        valid = (
            set(value) == LEDGER_KEYS and value.get("schema_version") == LEDGER_SCHEMA
        )
    elif relative == CANDIDATE_REVIEW_NAME:
        valid = valid_candidate_review(value)
    elif relative == LIVE_GATE_NAME:
        valid = (
            set(value) == _LIVE_GATE_KEYS
            and value.get("schema_version") == LIVE_GATE_SCHEMA
            and value.get("artifact_kind") == "live_gate"
        )
    elif relative == RESULT_NAME:
        cases = value.get("cases")
        counts = value.get("operation_counts")
        valid = (
            set(value) == _RESULT_KEYS
            and value.get("schema_version") == RESULT_SCHEMA
            and value.get("artifact_kind") == "evaluation_result"
            and isinstance(cases, list)
            and all(
                isinstance(item, dict) and set(item) == _CASE_SUMMARY_KEYS
                for item in cases
            )
            and isinstance(counts, dict)
            and set(counts) == _OPERATION_KEYS
        )
    elif relative == VERIFICATION_NAME:
        integrity = value.get("artifact_integrity_review")
        common = (
            value.get("schema_version") == VERIFICATION_SCHEMA
            and value.get("artifact_kind") == "independent_verification"
            and value.get("provider_invoked") is False
            and value.get("terminal_evidence_modified") is False
            and value.get("authority_granted") is False
            and value.get("live_execution_authorized") is False
            and value.get("v11_authorized") is False
        )
        if integrity == "accepted":
            valid = (
                common
                and set(value) == _VERIFICATION_KEYS
                and isinstance(value.get("operation_counts"), dict)
                and set(value["operation_counts"]) == _OPERATION_KEYS
                and isinstance(value.get("privacy"), dict)
                and set(value["privacy"]) == {"files", "directories", "bytes"}
            )
        elif integrity == "rejected":
            nullable_hashes = (
                "gate5_task_contract_sha256",
                "gate5_guardrails_sha256",
                "gate5_evidence_sha256",
                "result_sha256",
                "ledger_sha256",
                "candidate_review_sha256",
                "live_gate_sha256",
                "candidate_source_manifest_sha256",
                "contract_sha256",
                "provider_owner_source_identity_sha256",
                "dependency_identity_sha256",
            )
            valid = (
                common
                and set(value) == _REJECTED_VERIFICATION_KEYS
                and value.get("rejection_reason_code") in GATE5_REJECTION_REASON_CODES
                and value.get("empirical_gate") in {*_EMPIRICAL_DISPOSITIONS, None}
                and all(
                    value.get(key) is None
                    or (
                        isinstance(value.get(key), str)
                        and bool(_SHA256_RE.fullmatch(value[key]))
                    )
                    for key in nullable_hashes
                )
                and (
                    value.get("candidate_commit") is None
                    or (
                        isinstance(value.get("candidate_commit"), str)
                        and bool(_GIT_ID_RE.fullmatch(value["candidate_commit"]))
                    )
                )
                and (
                    value.get("candidate_tree") is None
                    or (
                        isinstance(value.get("candidate_tree"), str)
                        and bool(_GIT_ID_RE.fullmatch(value["candidate_tree"]))
                    )
                )
                and (
                    value.get("operation_counts") is None
                    or (
                        isinstance(value.get("operation_counts"), dict)
                        and set(value["operation_counts"]) == _OPERATION_KEYS
                    )
                )
                and value.get("privacy") is None
            )
        else:
            valid = False
    elif relative.startswith(f"{RESULT_FRAGMENTS_NAME}/"):
        semantic = value.get("semantic_result")
        projection = value.get("provider_outcome")
        if relative.endswith("-terminal.json"):
            valid = (
                set(value) == _CASE_TERMINAL_MARKER_KEYS
                and value.get("artifact_kind") == "case_terminal_marker"
                and value.get("stage") in {"post_return_projection", "result_fragment"}
                and value.get("external_effect_possible") is True
                and value.get("empirical_disposition") == "error"
            )
        elif relative.endswith("00-setup.json"):
            valid = (
                set(value) == _SETUP_FRAGMENT_KEYS
                and value.get("artifact_kind") == "setup_result_fragment"
                and value.get("dspx_generate_entered") is False
            )
        else:
            valid = (
                set(value) == _CASE_FRAGMENT_KEYS
                and value.get("artifact_kind") == "case_result_fragment"
                and (
                    (
                        value.get("case_phase") == "generate_call_terminal"
                        and value.get("dspx_generate_entered") is True
                    )
                    or (
                        value.get("case_phase") == "pre_generate_terminal"
                        and value.get("dspx_generate_entered") is False
                        and value.get("journal_present") is False
                    )
                )
                and isinstance(semantic, dict)
                and set(semantic) == _SEMANTIC_KEYS
                and isinstance(projection, dict)
                and set(projection) == _PROJECTION_KEYS
            )
        valid = valid and value.get("schema_version") == RESULT_SCHEMA
    elif relative.endswith("reservation.json"):
        reservation = value.get("reservation")
        valid = (
            set(value) == _RESERVATION_WRAPPER_KEYS
            and value.get("schema_version") == "dspx-provider-outcome-consumption-v1"
            and isinstance(reservation, dict)
            and set(reservation) == _RESERVATION_KEYS
            and reservation.get("schema_version")
            == "dspx-provider-outcome-reservation-v1"
        )
    elif "/events/" in relative:
        valid = (
            set(value) == _EVENT_ENVELOPE_KEYS
            and value.get("schema_version")
            == "dspx-provider-outcome-consumption-event-v1"
            and isinstance(value.get("producer"), dict)
            and set(value["producer"]) == {"owner", "version", "commit", "tree"}
            and isinstance(value.get("event"), dict)
            and set(value["event"]) == _EVENT_KEYS
        )
    elif relative.endswith("poisoned.json"):
        valid = (
            set(value) == {"schema_version", "effect_possible"}
            and value.get("schema_version") == "dspx-provider-outcome-poison-v1"
            and isinstance(value.get("effect_possible"), bool)
        )
    elif relative.endswith("inflight.json"):
        valid = (
            set(value) == {"schema_version", "sequence", "effect_possible"}
            and value.get("schema_version") == "dspx-provider-outcome-inflight-v1"
            and not isinstance(value.get("sequence"), bool)
            and isinstance(value.get("sequence"), int)
            and value["sequence"] >= 0
            and isinstance(value.get("effect_possible"), bool)
        )
    else:  # pragma: no cover - static path filter owns this branch
        valid = False
    if not valid:
        raise SemanticV11Error("path-specific retained schema/key drift")


def _expected_from_result(
    attempt: ConsumedAttempt,
    observed_files: set[str],
    observed_directories: set[str],
    *,
    include_verification: bool,
) -> tuple[set[str], set[str]]:
    result, _ = read_private_json(
        attempt.attempt_root / RESULT_NAME, "evaluation result"
    )
    cases = result.get("cases")
    if not isinstance(cases, list):
        raise SemanticV11Error("retained result case shape drift")
    directories = {".", PROVIDER_OUTCOMES_NAME, RESULT_FRAGMENTS_NAME}
    files = {LEDGER_NAME, CANDIDATE_REVIEW_NAME, LIVE_GATE_NAME, RESULT_NAME}
    if include_verification:
        files.add(VERIFICATION_NAME)
    if not cases:
        files.add(f"{RESULT_FRAGMENTS_NAME}/00-setup.json")
    else:
        for ordinal, summary in enumerate(cases, start=1):
            if (
                not isinstance(summary, dict)
                or summary.get("case_id") != CASE_ORDER[ordinal - 1]
                or summary.get("case_ordinal") != ordinal
                or not isinstance(summary.get("dspx_generate_entered"), bool)
            ):
                raise SemanticV11Error("retained result case order/count drift")
            files.add(f"{RESULT_FRAGMENTS_NAME}/{ordinal:02d}-case.json")
            marker = f"{RESULT_FRAGMENTS_NAME}/{ordinal:02d}-terminal.json"
            if marker in observed_files:
                marker_value, _ = read_private_json(
                    attempt.attempt_root / marker, "case terminal marker"
                )
                stage = marker_value.get("stage")
                provider_outcome = summary.get("provider_outcome")
                if (
                    not isinstance(provider_outcome, dict)
                    or provider_outcome.get("reason")
                    != f"post_entry_{stage}_failed_after_case_terminal"
                ):
                    raise SemanticV11Error("retained case terminal marker drift")
                files.add(marker)
            journal = f"{PROVIDER_OUTCOMES_NAME}/{_JOURNALS[ordinal - 1]}"
            if summary.get("receipt_journal") is True:
                directories.update({journal, f"{journal}/events"})
                files.add(f"{journal}/reservation.json")
                marker_files = {
                    f"{journal}/poisoned.json",
                    f"{journal}/inflight.json",
                } & observed_files
                if len(marker_files) > 1:
                    raise SemanticV11Error("retained journal marker cardinality drift")
                files.update(marker_files)
                event_prefix = f"{journal}/events/"
                event_names = sorted(
                    item.removeprefix(event_prefix)
                    for item in observed_files
                    if item.startswith(event_prefix)
                )
                if event_names != [
                    f"{index:06d}.json" for index in range(len(event_names))
                ]:
                    raise SemanticV11Error("retained journal event sequence drift")
                files.update(event_prefix + item for item in event_names)
                inflight = f"{journal}/inflight.json"
                if inflight in observed_files:
                    marker, _ = read_private_json(
                        attempt.attempt_root / inflight, "inflight marker"
                    )
                    lawful = {len(event_names)}
                    if event_names:
                        lawful.add(len(event_names) - 1)
                    if marker.get("sequence") not in lawful:
                        raise SemanticV11Error(
                            "retained inflight marker sequence drift"
                        )
            elif summary.get("receipt_journal") is not False:
                raise SemanticV11Error("retained journal count field drift")
    if len(cases) > len(CASE_ORDER):
        raise SemanticV11Error("retained result case cardinality drift")
    counts = result["operation_counts"]
    if (
        counts["reached_requests"] != len(cases)
        or counts["dspx_generate_calls"]
        != sum(bool(item["dspx_generate_entered"]) for item in cases)
        or counts["admitted_invocations"]
        != sum(bool(item["invocation_admitted"]) for item in cases)
        or counts["effect_capable_delegations"]
        != sum(item["effect_capable_delegations"] for item in cases)
        or counts["receipt_journals"]
        != sum(bool(item["receipt_journal"]) for item in cases)
    ):
        raise SemanticV11Error("retained operation count derivation drift")
    return directories, files


def verify_private_tree(
    attempt: ConsumedAttempt, *, include_verification: bool = False
) -> dict[str, int]:
    """Reject every extra object before deriving exact paths, privacy, or counts."""

    attempt = require_consumed_attempt(attempt)
    total = files = directories = 0
    observed_directories: set[str] = set()
    observed_files: set[str] = set()
    try:
        paths = [attempt.attempt_root, *attempt.attempt_root.rglob("*")]
    except OSError as exc:
        raise SemanticV11Error("retained tree listing failed") from exc
    for path in paths:
        relative = (
            "."
            if path == attempt.attempt_root
            else path.relative_to(attempt.attempt_root).as_posix()
        )
        if not _allowed_shape(relative, include_verification=include_verification):
            raise SemanticV11Error("retained tree contains a non-whitelisted object")
        try:
            info = path.lstat()
        except OSError as exc:
            raise SemanticV11Error("retained tree member unavailable") from exc
        if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
            raise SemanticV11Error("retained tree ownership/link drift")
        if stat.S_ISDIR(info.st_mode):
            if stat.S_IMODE(info.st_mode) != 0o700:
                raise SemanticV11Error("retained directory mode drift")
            directories += 1
            observed_directories.add(relative)
            continue
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            raise SemanticV11Error("retained file posture drift")
        raw = path.read_bytes()
        if not raw or any(item in raw for item in _FORBIDDEN_RETAINED):
            raise SemanticV11Error("retained private data boundary rejected")
        try:
            value = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SemanticV11Error("retained JSON member invalid") from exc
        if (
            not isinstance(value, dict)
            or json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            != raw
        ):
            raise SemanticV11Error("retained JSON canonical drift")
        _validate_json_shape(relative, value)
        files += 1
        observed_files.add(relative)
        total += len(raw)
        if total > MAX_RETAINED_BYTES:
            raise SemanticV11Error("retained private data boundary rejected")
    expected_directories, expected_files = _expected_from_result(
        attempt,
        observed_files,
        observed_directories,
        include_verification=include_verification,
    )
    if observed_directories != expected_directories or observed_files != expected_files:
        raise SemanticV11Error("retained tree grammar drift")
    return {"files": files, "directories": directories, "bytes": total}
