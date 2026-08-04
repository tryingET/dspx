# summary: "Owner-private task root, append-only event, and terminal disposition helpers for AK-4643."
from __future__ import annotations

import json
import os
import pwd
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_contract_v10 import (
    CASE_ORDER,
    EVENT_CLASSIFICATIONS,
    EVENT_DIR,
    LEDGER_NAME,
    MAX_EVENT_BYTES,
    RESULT_NAME,
    TASK_ID,
    VERIFICATION_NAME,
    SemanticV10Error,
    canonical,
    mapping,
    read_json,
    retained_json,
    sha256,
    write_exclusive,
)

REVIEW_SCHEMA = "dspx-oracle-semantic-v10-candidate-review-v1"
GATE_SCHEMA = "dspx-oracle-semantic-v10-live-gate-v1"
LEDGER_SCHEMA = "dspx-oracle-semantic-v10-ledger-v1"
EVENT_SCHEMA = "dspx-oracle-semantic-v10-event-v1"
RESULT_SCHEMA = "dspx-oracle-semantic-v10-result-v1"
VERIFICATION_SCHEMA = "dspx-oracle-semantic-v10-verification-v1"
SEMANTIC_RESULT_KEYS = {
    "schema_version",
    "authority",
    "request_sha256",
    "backend_kind",
    "preferred_model",
    "configured_provider",
    "configured_model",
    "executed_provider",
    "executed_model",
    "execution_status",
    "live_call_succeeded",
    "fixture_sha256",
    "analysis",
    "error",
}
EVALUATION_RESULT_KEYS = {
    "schema_version",
    "ak_task_id",
    "artifact_integrity_review",
    "empirical_gate",
    "contract_sha256",
    "candidate_review_sha256",
    "live_gate_sha256",
    "source_identity",
    "request_hashes",
    "route",
    "dependency_identity",
    "cases",
    "summary",
    "attempt",
    "preflight_error",
    "event_history_sha256",
    "effects",
    "claims",
}
EVENT_FACT_KEYS = {
    "attempt_consumed": {"evaluation_processes", "retry_allowed"},
    "preflight_passed": {
        "contract_sha256",
        "candidate_review_sha256",
        "live_gate_sha256",
    },
    "preflight_error": {"classification"},
    "attempt_error": {"classification"},
    "case_started": {"case_id", "request_sha256"},
    "effect_possible": {
        "case_id",
        "request_sha256",
        "effect_token",
        "generate_invocation",
    },
    "effect_observed": {
        "case_id",
        "effect_token",
        "generate_invocation_delta",
        "history_delta",
        "response_attributable",
    },
    "case_result": {"case_id", "row_sha256", "row"},
    "case_error": {"case_id", "classification", "row"},
    "case_scored": {"case_id", "status", "score_sha256"},
    "terminal": {"disposition", "result_sha256"},
}
ATTEMPT_PROJECTION = {
    "evaluation_processes": 1,
    "separate_health_probes": 0,
    "dspx_managed_retries": 0,
    "case_selector": None,
    "selective_rerun": False,
    "provider_transport_call_count": "not_proven",
    "provider_internal_retry_behavior": "not_proven",
}
EFFECT_PROJECTION = {
    "shared_store_connections": 0,
    "shared_oracle_publications": 0,
    "embedding_model_calls": 0,
    "release_mutations": 0,
    "governance_mutations": 0,
    "activation_mutations": 0,
    "possible_provider_auth_refresh": "disclosed_not_observed",
}
ATTEMPT_MEMBER_NAMES = frozenset(
    {
        LEDGER_NAME,
        EVENT_DIR,
        "contract-snapshot.json",
        "candidate-review-snapshot.json",
        "live-gate-snapshot.json",
        RESULT_NAME,
        VERIFICATION_NAME,
    }
)


def task_state_root(*, _test_owner_home: Path | None = None) -> Path:
    home = (_test_owner_home or Path(pwd.getpwuid(os.getuid()).pw_dir)).absolute()
    if _test_owner_home is not None:
        return home / f"AK-{TASK_ID}"
    return (
        home
        / ".local"
        / "state"
        / "dspx"
        / "oracle-semantic-analysis-evaluations"
        / f"AK-{TASK_ID}"
    )


def ensure_private_directory(
    path: Path, *, create: bool, _test_owner_home: Path | None = None
) -> Path:
    target = path.expanduser().absolute()
    home = (_test_owner_home or Path(pwd.getpwuid(os.getuid()).pw_dir)).absolute()
    if target != task_state_root(_test_owner_home=_test_owner_home):
        raise SemanticV10Error("task state root is not the fixed AK-4643 root")
    try:
        relative = target.relative_to(home)
    except ValueError as exc:
        raise SemanticV10Error("task state must remain below the owner home") from exc
    current = home
    for index, part in enumerate(relative.parts):
        current /= part
        if create and not current.exists():
            current.mkdir(mode=0o700)
        info = current.lstat()
        require_private = index >= max(0, len(relative.parts) - 2)
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.getuid()
            or (require_private and stat.S_IMODE(info.st_mode) != 0o700)
        ):
            raise SemanticV10Error("task-state ancestor identity/mode drift")
    return target


def require_mode(path: Path, mode: int, label: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise SemanticV10Error(f"{label} missing") from exc
    expected_type = (
        stat.S_ISDIR(info.st_mode) if mode == 0o700 else stat.S_ISREG(info.st_mode)
    )
    if (
        not expected_type
        or stat.S_ISLNK(info.st_mode)
        or stat.S_IMODE(info.st_mode) != mode
        or info.st_uid != os.getuid()
        or (mode == 0o600 and info.st_nlink != 1)
    ):
        raise SemanticV10Error(f"{label} mode/type/owner drift")


def verify_snapshot(
    attempt: Path, name: str, expected: Mapping[str, Any], label: str
) -> None:
    path = attempt / name
    require_mode(path, 0o600, label)
    observed, _ = read_json(path, label)
    if observed != expected:
        raise SemanticV10Error(f"{label} drift")


def _admit_event(
    events: list[dict[str, Any]], kind: str, facts: Mapping[str, Any]
) -> None:
    if kind not in EVENT_FACT_KEYS or set(facts) != EVENT_FACT_KEYS[kind]:
        raise SemanticV10Error("closed event schema drift")
    if (
        kind in EVENT_CLASSIFICATIONS
        and facts.get("classification") not in EVENT_CLASSIFICATIONS[kind]
    ):
        raise SemanticV10Error("event classification is not in the closed vocabulary")
    if not events:
        if kind != "attempt_consumed":
            raise SemanticV10Error("attempt-consumed event must be first")
        return
    prior = str(events[-1].get("kind") or "")
    if prior == "terminal":
        raise SemanticV10Error("terminal history is immutable")
    if prior in {"preflight_error", "attempt_error", "case_error"} or (
        prior == "case_scored" and events[-1].get("status") == "failed"
    ):
        if kind != "terminal":
            raise SemanticV10Error("activity after stopping event is forbidden")
        return
    allowed = {
        "attempt_consumed": {"preflight_passed", "preflight_error"},
        "preflight_passed": {"case_started", "attempt_error"},
        "case_started": {"effect_possible", "case_error"},
        "effect_possible": {"effect_observed", "case_error"},
        "effect_observed": {"case_result", "case_error"},
        "case_result": {"case_scored"},
        "case_scored": {"case_started", "attempt_error", "terminal"},
    }
    if kind not in allowed.get(prior, set()):
        raise SemanticV10Error(f"illegal event transition: {prior}->{kind}")
    if kind == "terminal" and not (
        prior == "case_scored"
        and events[-1].get("status") == "passed"
        and sum(event.get("kind") == "case_scored" for event in events)
        == len(CASE_ORDER)
    ):
        raise SemanticV10Error("terminal event lacks a stopping predecessor")


def append_event(attempt: Path, kind: str, **facts: Any) -> dict[str, Any]:
    event_dir = attempt / EVENT_DIR
    names = sorted(path.name for path in event_dir.iterdir())
    if names != [f"{index:06d}.json" for index in range(len(names))]:
        raise SemanticV10Error("event history is not append-only and contiguous")
    existing = [payload for payload, _ in load_events(attempt)]
    _admit_event(existing, kind, facts)
    payload = {
        "schema_version": EVENT_SCHEMA,
        "ak_task_id": TASK_ID,
        "sequence": len(names),
        "kind": kind,
        **facts,
    }
    if len(retained_json(payload)) > MAX_EVENT_BYTES:
        raise SemanticV10Error("event exceeds bounded retention size")
    write_exclusive(event_dir / f"{len(names):06d}.json", payload)
    return payload


def history_hashes(attempt: Path) -> dict[str, str]:
    return {
        path.name: sha256(path.read_bytes())
        for path in sorted((attempt / EVENT_DIR).iterdir())
    }


def has_open_effect(attempt: Path) -> bool:
    open_tokens: set[str] = set()
    for path in sorted((attempt / EVENT_DIR).iterdir()):
        payload = mapping(json.loads(path.read_bytes()), "event")
        if payload.get("kind") == "effect_possible":
            token = str(payload.get("effect_token") or "")
            if not token or token in open_tokens:
                raise SemanticV10Error("persisted effect marker drift")
            open_tokens.add(token)
        elif payload.get("kind") == "effect_observed":
            token = str(payload.get("effect_token") or "")
            if token not in open_tokens:
                raise SemanticV10Error("persisted effect observation drift")
            open_tokens.remove(token)
    return bool(open_tokens)


def load_events(attempt: Path) -> list[tuple[dict[str, Any], str]]:
    event_dir = attempt / EVENT_DIR
    require_mode(event_dir, 0o700, "event directory")
    names = sorted(path.name for path in event_dir.iterdir())
    if names != [f"{index:06d}.json" for index in range(len(names))]:
        raise SemanticV10Error("append-only event sequence drift")
    result: list[tuple[dict[str, Any], str]] = []
    for index, name in enumerate(names):
        path = event_dir / name
        require_mode(path, 0o600, f"event {index}")
        payload, raw = read_json(path, f"event {index}")
        if len(raw) > MAX_EVENT_BYTES:
            raise SemanticV10Error("event exceeds bounded retention size")
        if (
            payload.get("schema_version") != EVENT_SCHEMA
            or payload.get("ak_task_id") != TASK_ID
            or payload.get("sequence") != index
        ):
            raise SemanticV10Error("event identity drift")
        result.append((payload, sha256(raw)))
    return result


def active_case(attempt: Path) -> str | None:
    active: str | None = None
    for event, _ in load_events(attempt):
        kind = event.get("kind")
        if kind == "case_started":
            active = str(event.get("case_id") or "")
        elif kind in {"case_scored", "case_error"}:
            active = None
    return active


def retained_rows(events: list[tuple[dict[str, Any], str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event, _ in events:
        row: object = None
        if event.get("kind") == "case_result":
            row = event.get("row")
        elif event.get("kind") == "case_error":
            row = event.get("row")
        if row is not None:
            parsed = mapping(row, "retained case row")
            if event.get("kind") == "case_result" and sha256(
                canonical(parsed)
            ) != event.get("row_sha256"):
                raise SemanticV10Error("retained case-row digest drift")
            rows.append(parsed)
    return rows


def started_cases(events: list[tuple[dict[str, Any], str]]) -> list[str]:
    return [
        str(event.get("case_id") or "")
        for event, _ in events
        if event.get("kind") == "case_started"
    ]


def case_row(
    case_id: str,
    request_sha: str,
    semantic: Mapping[str, Any],
    score: object,
    status: str,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "request_sha256": request_sha,
        "semantic_result": dict(semantic),
        "score": score,
        "status": status,
    }


def append_case_error(
    attempt: Path,
    case_id: str,
    classification: str,
    row: Mapping[str, Any] | None = None,
) -> None:
    append_event(
        attempt,
        "case_error",
        case_id=case_id,
        classification=classification,
        row=dict(row) if row is not None else None,
    )


def disposition(
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


def result_payload(
    *,
    attempt: Path,
    receipts: Mapping[str, Any],
    rows: list[dict[str, Any]],
    disposition: str,
    dependency: Mapping[str, Any] | None,
    preflight_error: str | None,
    route: Mapping[str, str],
) -> dict[str, Any]:
    events = load_events(attempt)
    if retained_rows(events) != rows:
        raise SemanticV10Error("in-memory and retained case rows differ")
    scores = [row["score"] for row in rows if isinstance(row.get("score"), Mapping)]
    hashes = history_hashes(attempt)
    if events[-1][0].get("kind") == "terminal":
        hashes.pop(f"{len(events) - 1:06d}.json")
    contract = mapping(receipts.get("contract"), "contract")
    return {
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
            "requested": dict(route),
            "configured_provider": route["provider"] if rows else None,
            "configured_model": route["model"] if rows else None,
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
            "reached_case_count": len(started_cases(events)),
            "passed_case_count": sum(row.get("status") == "passed" for row in rows),
            "macro_score": sum(float(score.get("score", 0.0)) for score in scores)
            / len(CASE_ORDER),
        },
        "attempt": dict(ATTEMPT_PROJECTION),
        "preflight_error": preflight_error,
        "event_history_sha256": hashes,
        "effects": dict(EFFECT_PROJECTION),
        "claims": {
            "exact_four_case_empirical_gate_passed": disposition == "passed",
            **mapping(contract.get("nonclaims"), "nonclaims"),
            "rocs_conformance": False,
            "shared_oracle_publication": False,
        },
    }


def derive_disposition(
    events: list[tuple[dict[str, Any], str]], result: Mapping[str, Any] | None
) -> str:
    open_effects: set[str] = set()
    has_error = False
    failed = False
    passed_cases: list[str] = []
    terminal: list[str] = []
    for event, _ in events:
        kind = event.get("kind")
        if kind == "effect_possible":
            token = str(event.get("effect_token") or "")
            if not token or token in open_effects:
                raise SemanticV10Error("effect marker drift")
            open_effects.add(token)
        elif kind == "effect_observed":
            token = str(event.get("effect_token") or "")
            if token not in open_effects:
                raise SemanticV10Error("effect observation without marker")
            open_effects.remove(token)
        elif kind in {"preflight_error", "attempt_error", "case_error"}:
            has_error = True
        elif kind == "case_scored":
            if event.get("status") == "passed":
                passed_cases.append(str(event.get("case_id")))
            else:
                failed = True
        elif kind == "terminal":
            terminal.append(str(event.get("disposition")))
    derived = (
        "effect_indeterminate"
        if open_effects
        else "error"
        if has_error
        else "failed"
        if failed
        else "passed"
        if tuple(passed_cases) == CASE_ORDER
        else "error"
    )
    if len(terminal) > 1 or (terminal and terminal != [derived]):
        raise SemanticV10Error("terminal precedence drift")
    if result is not None and result.get("empirical_gate") != derived:
        raise SemanticV10Error("result empirical disposition drift")
    return derived
