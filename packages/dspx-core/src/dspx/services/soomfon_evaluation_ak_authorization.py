"""Read-only canonical Agent Kernel reconciliation for Soomfon execution."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, NoReturn, cast

from dspx.services.soomfon_evaluation_ak_runtime import (
    AK_EXECUTABLE,
    AK_EXECUTABLE_MODE,
    AK_EXECUTABLE_SHA256,
    run_ak_json as _run_ak_json,
)
from dspx.services.soomfon_evaluation_contract import (
    CONTRACT_PREPARATION_TASK_ID,
    REVIEWED_CONTRACT_SHA256,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_REVIEW_CHECK_TYPES = (
    "review:independent-security",
    "test:independent-provider-free",
)
_OPERATOR_CHECK_TYPE = "authorization:operator-one-suite"
_COMPLETION_KIND = "soomfon_one_suite_execution_authorization"
_DISPATCH_RE = re.compile(r"^dispatch-[0-9]{10,20}$")
_OPERATOR_REQUEST_RE = re.compile(
    r"^operator-request-[A-Za-z0-9][A-Za-z0-9._:-]{7,95}$"
)

_EXPECTED_OUTCOMES = [
    f"Authorize exactly one six-case Soomfon suite for contract {REVIEWED_CONTRACT_SHA256} "
    f"prepared under AK-{CONTRACT_PREPARATION_TASK_ID}",
    "Bind the exact reviewed DSPx source commit and tree or exact installed wheel payload",
    "Bind the exact AK-4991 owner artifact, codex/gpt-5.6-luna, reasoning xhigh, and no-refresh custody",
    "Limit the suite to twelve provider transports with zero retry, fallback, health probe, resume, or selective rerun",
]
_EXPECTED_VALIDATION = [
    "Require at least 1800 seconds of claim lease and reconcile canonical AK before state and every case marker",
    "Reconcile canonical AK in every child and with at least 90 seconds remaining before each logical provider call",
    "Bind distinct review dispatch references and an explicit operator one-suite request without claiming cryptographic principal authentication",
]
_EXPECTED_EVIDENCE_CLASSES = [*_REVIEW_CHECK_TYPES, _OPERATOR_CHECK_TYPE]
_EXPECTED_REVIEW_QUESTIONS = [
    "Do the reviewed DSPx and owner identities exactly match the executing payloads?",
    "Can any path exceed one suite or twelve provider transports?",
]
_EXPECTED_GUARDRAILS = {
    "invariants": [
        "The active contract, executing DSPx identity, owner artifact, model, and effect budget remain exact",
        "Every effect-capable call remains bound to the current authorization marker, receipt journal, and unchanged canonical authority",
        "The trusted effective OS user and canonical AK DB define the local authority threat boundary",
    ],
    "anti_goals": [
        "Do not authorize generic dspy-lm-auth selection, routing, promotion, activation, release, or publication",
        "Do not treat a local authorization projection or caller-supplied digest as canonical authority",
        "Do not relabel checked_by metadata or dispatch references as cryptographic distinct-principal authentication",
    ],
    "constraints": [
        "Exactly one six-case suite and at most twelve provider transports",
        "Zero retry, fallback, health probe, selective rerun, and resume",
        "Use only the exact digest-pinned fd-executed Agent Kernel binary and clean no-bytecode source or payload roots",
    ],
    "rollback_boundaries": [
        "Any missing, expired, changed, or mismatched canonical AK fact rejects before effect",
    ],
}


class CanonicalAKAuthorizationError(RuntimeError):
    """Fixed-message canonical AK reconciliation failure."""


@dataclass(frozen=True, slots=True)
class CanonicalAKAuthorization:
    task_id: int
    evidence_ids: tuple[int, int, int]
    reconciliation_sha256: str


AKRunner = Callable[[tuple[str, ...]], object]


def expected_execution_task_contract() -> dict[str, object]:
    return {
        "completion_kind": _COMPLETION_KIND,
        "required_outcomes": list(_EXPECTED_OUTCOMES),
        "required_validation": list(_EXPECTED_VALIDATION),
        "required_evidence_classes": list(_EXPECTED_EVIDENCE_CLASSES),
        "review_questions": list(_EXPECTED_REVIEW_QUESTIONS),
    }


def expected_execution_task_guardrails() -> dict[str, list[str]]:
    return {key: list(value) for key, value in _EXPECTED_GUARDRAILS.items()}


def _reject() -> NoReturn:
    raise CanonicalAKAuthorizationError("canonical AK authorization rejected")


def _mapping(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _reject()
    typed = cast(Mapping[str, Any], value)
    return dict(typed)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        _reject()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _reject()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _task_from_machine(value: object, *, task_id: int, repo: str) -> dict[str, Any]:
    envelope = _mapping(
        value,
        {
            "surface",
            "schema_version",
            "emitted_at",
            "payload_kind",
            "schema_locator",
            "ok",
            "payload",
            "error",
        },
    )
    if (
        envelope["surface"] != "task.show"
        or envelope["schema_version"] != 1
        or envelope["payload_kind"] != "task_detail"
        or envelope["schema_locator"] != "ak machine schema task-show"
        or envelope["ok"] is not True
        or envelope["error"] is not None
    ):
        _reject()
    _timestamp(envelope["emitted_at"])
    payload = _mapping(envelope["payload"], {"task"})
    task = _mapping(
        payload["task"],
        {
            "id",
            "repo",
            "title",
            "description",
            "status",
            "priority",
            "claimed_by",
            "claimed_at",
            "lease_expires_at",
            "depends_on",
            "evidence",
            "result",
            "created_at",
            "completed_at",
            "scope",
            "entity_version",
        },
    )
    if (
        task["id"] != task_id
        or task["repo"] != repo
        or not isinstance(task["title"], str)
        or not task["title"].strip()
        or isinstance(task["priority"], bool)
        or not isinstance(task["priority"], int)
        or isinstance(task["entity_version"], bool)
        or not isinstance(task["entity_version"], int)
        or not isinstance(task["depends_on"], list)
        or any(type(item) is not int for item in task["depends_on"])
    ):
        _reject()
    scope = _mapping(
        task["scope"], {"allowed_paths", "required_paths", "forbidden_paths"}
    )
    if any(
        not isinstance(scope[key], list)
        or any(not isinstance(item, str) for item in scope[key])
        for key in scope
    ):
        _reject()
    return task


def _validate_claim(task: Mapping[str, Any], *, minimum_lease_seconds: float) -> None:
    claimed_by = task.get("claimed_by")
    lease = _timestamp(task.get("lease_expires_at"))
    _timestamp(task.get("claimed_at"))
    if (
        task.get("status") != "claimed"
        or not isinstance(claimed_by, str)
        or not claimed_by.strip()
        or lease.timestamp() - time.time() < minimum_lease_seconds
        or task.get("depends_on") != [CONTRACT_PREPARATION_TASK_ID]
        or task.get("completed_at") is not None
    ):
        _reject()


def _validate_dependency(task: Mapping[str, Any]) -> None:
    if task.get("status") != "done" or task.get("completed_at") is None:
        _reject()
    _timestamp(task["completed_at"])


def _validate_contract(value: object, *, task_id: int, repo: str) -> dict[str, Any]:
    payload = _mapping(
        value, {"task_id", "repo", "title", "status", "done_contract", "guardrails"}
    )
    if (
        payload["task_id"] != task_id
        or payload["repo"] != repo
        or payload["status"] != "claimed"
        or not isinstance(payload["title"], str)
    ):
        _reject()
    done = _mapping(
        payload["done_contract"],
        {"id", "task_id", "entity_version", "contract", "created_at", "updated_at"},
    )
    guardrails = _mapping(
        payload["guardrails"],
        {"id", "task_id", "entity_version", "guardrails", "created_at", "updated_at"},
    )
    if (
        done["task_id"] != task_id
        or guardrails["task_id"] != task_id
        or done["contract"] != expected_execution_task_contract()
        or guardrails["guardrails"] != expected_execution_task_guardrails()
    ):
        _reject()
    return payload


def _common_evidence_details(
    *,
    contract_sha256: str,
    dspx_artifact: Mapping[str, Any],
    owner_artifact: Mapping[str, Any],
    effect_budget: Mapping[str, Any],
) -> dict[str, object]:
    return {
        "schema_version": "soomfon-ak5061-authorization-evidence-v3",
        "preparation_task_id": CONTRACT_PREPARATION_TASK_ID,
        "contract_sha256": contract_sha256,
        "dspx_artifact": dict(dspx_artifact),
        "owner_artifact": dict(owner_artifact),
        "requested_model": "codex/gpt-5.6-luna",
        "reasoning_effort": "xhigh",
        "effect_budget": dict(effect_budget),
        "ak_runtime": {
            "path": str(AK_EXECUTABLE),
            "sha256": AK_EXECUTABLE_SHA256,
            "mode": f"{AK_EXECUTABLE_MODE:04o}",
        },
    }


def _evidence_record(value: object, *, task_id: int, repo: str) -> dict[str, Any]:
    record = _mapping(
        value,
        {
            "id",
            "task_id",
            "task_ref",
            "repo",
            "repo_scope",
            "check_type",
            "result",
            "details",
            "checked_at",
            "checked_by",
        },
    )
    if (
        isinstance(record["id"], bool)
        or not isinstance(record["id"], int)
        or record["task_id"] != task_id
        or record["task_ref"] != task_id
        or record["repo"] != repo
        or record["repo_scope"] != repo
        or record["result"] != "pass"
        or not isinstance(record["checked_by"], str)
        or not record["checked_by"].strip()
    ):
        _reject()
    _timestamp(record["checked_at"])
    return record


def reconcile_canonical_ak_authorization(
    *,
    task_id: int,
    repo: str,
    contract_sha256: str,
    dspx_artifact: Mapping[str, Any],
    owner_artifact: Mapping[str, Any],
    review_references: tuple[Mapping[str, Any], Mapping[str, Any]],
    operator_evidence_id: int,
    operator_request_id: str,
    effect_budget: Mapping[str, Any],
    minimum_lease_seconds: float,
    runner: AKRunner | None = None,
) -> CanonicalAKAuthorization:
    """Reconcile a local projection against canonical, read-only AK state."""

    if runner is None:
        runner = _run_ak_json
    task = _task_from_machine(
        runner(("task", "show", str(task_id), "--machine")),
        task_id=task_id,
        repo=repo,
    )
    if minimum_lease_seconds < 0:
        _reject()
    _validate_claim(task, minimum_lease_seconds=minimum_lease_seconds)
    dependency = _task_from_machine(
        runner(("task", "show", str(CONTRACT_PREPARATION_TASK_ID), "--machine")),
        task_id=CONTRACT_PREPARATION_TASK_ID,
        repo=repo,
    )
    _validate_dependency(dependency)
    contract = _validate_contract(
        runner(("task", "contract", "show", str(task_id), "-F", "json")),
        task_id=task_id,
        repo=repo,
    )
    attached_raw = runner(("evidence", "task", str(task_id), "-F", "json"))
    if not isinstance(attached_raw, list):
        _reject()
    attached_values = cast(list[object], attached_raw)
    attached = {
        record["id"]: record
        for raw in attached_values
        for record in [_evidence_record(raw, task_id=task_id, repo=repo)]
    }
    review_evidence_ids = cast(
        tuple[int, int],
        tuple(reference.get("evidence_id") for reference in review_references),
    )
    expected_ids = (*review_evidence_ids, operator_evidence_id)
    if len(attached) != 3 or set(attached) != set(expected_ids):
        _reject()
    common = _common_evidence_details(
        contract_sha256=contract_sha256,
        dspx_artifact=dspx_artifact,
        owner_artifact=owner_artifact,
        effect_budget=effect_budget,
    )
    review_types: list[str] = []
    validated_evidence: list[dict[str, Any]] = []
    for evidence_id in expected_ids:
        shown = _evidence_record(
            runner(("evidence", "show", str(evidence_id), "-F", "json")),
            task_id=task_id,
            repo=repo,
        )
        if shown != attached[evidence_id]:
            _reject()
        if evidence_id == operator_evidence_id:
            expected_details = {
                **common,
                "operator_request_id": operator_request_id,
                "explicit_one_suite_request": True,
            }
            if (
                shown["check_type"] != _OPERATOR_CHECK_TYPE
                or shown["details"] != expected_details
            ):
                _reject()
        else:
            index = review_evidence_ids.index(evidence_id)
            reference = review_references[index]
            dispatch_id = reference.get("dispatch_id")
            verdict = reference.get("verdict")
            check_type = reference.get("check_type")
            if (
                not isinstance(dispatch_id, str)
                or _DISPATCH_RE.fullmatch(dispatch_id) is None
                or (check_type, verdict)
                != (_REVIEW_CHECK_TYPES[index], ("ACCEPT", "PASS")[index])
            ):
                _reject()
            review_types.append(shown["check_type"])
            expected_details = {
                **common,
                "review_dispatch_id": dispatch_id,
                "review_dispatch_verdict": verdict,
            }
            if (
                shown["check_type"] != check_type
                or shown["details"] != expected_details
            ):
                _reject()
        validated_evidence.append(shown)
    dispatch_ids = tuple(
        reference.get("dispatch_id") for reference in review_references
    )
    if (
        tuple(review_types) != _REVIEW_CHECK_TYPES
        or len(set(dispatch_ids)) != 2
        or not isinstance(operator_request_id, str)
        or _OPERATOR_REQUEST_RE.fullmatch(operator_request_id) is None
        or operator_request_id in dispatch_ids
    ):
        _reject()
    normalized = {
        "task": task,
        "dependency": dependency,
        "contract": contract,
        "evidence": validated_evidence,
    }
    digest = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CanonicalAKAuthorization(task_id, expected_ids, digest)


__all__ = [
    "CanonicalAKAuthorization",
    "CanonicalAKAuthorizationError",
    "expected_execution_task_contract",
    "expected_execution_task_guardrails",
    "reconcile_canonical_ak_authorization",
]
