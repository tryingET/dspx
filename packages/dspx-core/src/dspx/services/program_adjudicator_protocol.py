# summary: "Defines task-specific pluggable adjudicator registrations and deterministic selection without executing adjudicators."
# read_when:
#   - "Changing adjudicator forms, task routing, quorum, identity claims, execution support, or shared dispositions."

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from dspx.services.program_foundry_gepa_proposal_io import read_regular_bytes

TASK_ADJUDICATOR_REGISTRATION_SCHEMA = "dspx-task-adjudicator-registration-v1"
TASK_ADJUDICATOR_SELECTION_SCHEMA = "dspx-task-adjudicator-selection-v1"
FOUNDRY_GEPA_COMPARISON_TASK_KIND = "foundry_gepa_comparison"
BOUNDED_LOCAL_DISPOSITION_SCOPE = "bounded_local_disposition"
BUILTIN_DETERMINISTIC_IMPLEMENTATION = "foundry-gepa-comparison-jury-disposition-v1"

ADJUDICATOR_KINDS = frozenset(
    {
        "deterministic_policy",
        "ml_algorithm",
        "llm",
        "harnessed_llm",
        "human",
        "human_panel",
        "multi_agent_panel",
        "hybrid",
    }
)
SHARED_ADJUDICATOR_DISPOSITIONS = (
    "promote_locally",
    "reject_locally",
    "require_review",
    "abstain",
    "pending",
)
PANEL_ADJUDICATOR_KINDS = frozenset({"human_panel", "multi_agent_panel", "hybrid"})
_DEFAULT_SUBJECT_KIND = {
    "deterministic_policy": "system",
    "ml_algorithm": "algorithm",
    "llm": "model",
    "harnessed_llm": "agent",
    "human": "human",
    "human_panel": "human",
    "multi_agent_panel": "agent",
}


class ProgramAdjudicatorProtocolError(ValueError):
    """Raised when an adjudicator registration or selection is invalid."""


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProgramAdjudicatorProtocolError(
            f"adjudicator protocol value must be canonical JSON: {exc}"
        ) from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalized_subjects(subjects: Sequence[str]) -> list[str]:
    normalized = [str(subject).strip() for subject in subjects]
    if not normalized or any(not subject for subject in normalized):
        raise ProgramAdjudicatorProtocolError(
            "adjudicator identity claims require non-empty subject labels"
        )
    if len(set(normalized)) != len(normalized):
        raise ProgramAdjudicatorProtocolError(
            "adjudicator identity subject labels must be unique"
        )
    return normalized


def _subject_kinds(
    *, kind: str, subject_count: int, subject_kinds: Sequence[str] | None
) -> list[str]:
    if kind == "hybrid":
        if subject_kinds is None or len(subject_kinds) != subject_count:
            raise ProgramAdjudicatorProtocolError(
                "hybrid adjudicators require one explicit subject kind per subject"
            )
        normalized = [str(value).strip() for value in subject_kinds]
        if set(normalized) != {"human", "agent"}:
            raise ProgramAdjudicatorProtocolError(
                "hybrid adjudicators require both human and agent constituencies"
            )
        return normalized
    expected = _DEFAULT_SUBJECT_KIND[kind]
    if subject_kinds is None:
        return [expected] * subject_count
    normalized = [str(value).strip() for value in subject_kinds]
    if normalized != [expected] * subject_count:
        raise ProgramAdjudicatorProtocolError(
            f"{kind} subject kinds must all be {expected}"
        )
    return normalized


def _quorum_for_kind(
    *,
    kind: str,
    subject_count: int,
    quorum_mode: str | None,
    quorum_required: int | None,
) -> dict[str, Any]:
    if kind in PANEL_ADJUDICATOR_KINDS:
        if subject_count < 2:
            raise ProgramAdjudicatorProtocolError(
                f"{kind} requires at least two declared subjects"
            )
        mode = str(quorum_mode or "").strip()
        if mode not in {"threshold", "unanimous"}:
            raise ProgramAdjudicatorProtocolError(
                f"{kind} quorum mode must be threshold or unanimous"
            )
        required = subject_count if mode == "unanimous" else quorum_required
        if (
            isinstance(required, bool)
            or not isinstance(required, int)
            or required < 2
            or required > subject_count
        ):
            raise ProgramAdjudicatorProtocolError(
                f"{kind} quorum required must be between two and subject count"
            )
        return {
            "mode": mode,
            "required": required,
            "eligible": subject_count,
            "constituency_rule": (
                "at_least_one_human_and_one_agent" if kind == "hybrid" else None
            ),
        }
    if subject_count != 1:
        raise ProgramAdjudicatorProtocolError(
            f"{kind} requires exactly one declared subject"
        )
    if quorum_mode not in {None, "single"} or quorum_required not in {None, 1}:
        raise ProgramAdjudicatorProtocolError(
            f"{kind} does not accept panel quorum configuration"
        )
    return {
        "mode": "single",
        "required": 1,
        "eligible": 1,
        "constituency_rule": None,
    }


def _build_registration(
    *,
    task_kind: str,
    kind: str,
    implementation_id: str,
    subjects: Sequence[str],
    subject_kinds: Sequence[str] | None,
    priority: int,
    quorum_mode: str | None,
    quorum_required: int | None,
    execution_support: str,
) -> dict[str, Any]:
    normalized_task_kind = str(task_kind).strip()
    normalized_kind = str(kind).strip()
    normalized_implementation = str(implementation_id).strip()
    if not normalized_task_kind:
        raise ProgramAdjudicatorProtocolError("adjudicator task_kind is required")
    if normalized_kind not in ADJUDICATOR_KINDS:
        raise ProgramAdjudicatorProtocolError(
            "adjudicator kind must be one of: " + ", ".join(sorted(ADJUDICATOR_KINDS))
        )
    if not normalized_implementation:
        raise ProgramAdjudicatorProtocolError(
            "adjudicator implementation_id is required"
        )
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ProgramAdjudicatorProtocolError("adjudicator priority must be an integer")
    if execution_support not in {"implemented", "pending_only"}:
        raise ProgramAdjudicatorProtocolError("invalid adjudicator execution support")
    normalized_subjects = _normalized_subjects(subjects)
    normalized_subject_kinds = _subject_kinds(
        kind=normalized_kind,
        subject_count=len(normalized_subjects),
        subject_kinds=subject_kinds,
    )
    quorum = _quorum_for_kind(
        kind=normalized_kind,
        subject_count=len(normalized_subjects),
        quorum_mode=quorum_mode,
        quorum_required=quorum_required,
    )
    body = {
        "schema_version": TASK_ADJUDICATOR_REGISTRATION_SCHEMA,
        "task_selector": {
            "task_kind": normalized_task_kind,
            "policy_scope": BOUNDED_LOCAL_DISPOSITION_SCOPE,
            "priority": priority,
        },
        "backend": {
            "kind": normalized_kind,
            "implementation_id": normalized_implementation,
            "execution_support": execution_support,
        },
        "allowed_dispositions": list(SHARED_ADJUDICATOR_DISPOSITIONS),
        "quorum": quorum,
        "identity_claims": {
            "subjects": normalized_subjects,
            "subject_kinds": normalized_subject_kinds,
            "assertion_mode": "caller_declared",
            "authenticated": False,
            "verifier_receipt": None,
        },
        "authority": {
            "bounded_local_disposition": True,
            "production_promotion": False,
            "activation": False,
            "governance": False,
            "external_apply": False,
        },
        "execution": {
            "started": False,
            "effectful_backend_may_require_attempt_receipt": normalized_kind
            in {
                "llm",
                "harnessed_llm",
                "human",
                "human_panel",
                "multi_agent_panel",
                "hybrid",
            },
            "replay_policy": (
                "pure_recompute"
                if execution_support == "implemented"
                else "not_started_pending_executor"
            ),
        },
    }
    return {**body, "registration_id": _sha256(_canonical_json(body))}


def build_task_adjudicator_registration(
    *,
    task_kind: str,
    kind: str,
    implementation_id: str,
    subjects: Sequence[str],
    subject_kinds: Sequence[str] | None = None,
    priority: int = 100,
    quorum_mode: str | None = None,
    quorum_required: int | None = None,
) -> dict[str, Any]:
    """Build an unauthenticated protocol registration; it never grants execution."""

    return _build_registration(
        task_kind=task_kind,
        kind=kind,
        implementation_id=implementation_id,
        subjects=subjects,
        subject_kinds=subject_kinds,
        priority=priority,
        quorum_mode=quorum_mode,
        quorum_required=quorum_required,
        execution_support="pending_only",
    )


def builtin_foundry_deterministic_registration() -> dict[str, Any]:
    """Return the sole internally trusted implemented registration."""

    return _build_registration(
        task_kind=FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        kind="deterministic_policy",
        implementation_id=BUILTIN_DETERMINISTIC_IMPLEMENTATION,
        subjects=["dspx_builtin_deterministic_policy"],
        subject_kinds=["system"],
        priority=0,
        quorum_mode=None,
        quorum_required=None,
        execution_support="implemented",
    )


def validate_task_adjudicator_registration(
    payload: Mapping[str, Any],
    *,
    allow_internal_implemented: bool = False,
) -> dict[str, Any]:
    """Validate exact registration bytes while authenticating no identity."""

    if set(payload) != {
        "schema_version",
        "registration_id",
        "task_selector",
        "backend",
        "allowed_dispositions",
        "quorum",
        "identity_claims",
        "authority",
        "execution",
    }:
        raise ProgramAdjudicatorProtocolError(
            "adjudicator registration has unexpected or missing fields"
        )
    if payload.get("schema_version") != TASK_ADJUDICATOR_REGISTRATION_SCHEMA:
        raise ProgramAdjudicatorProtocolError(
            f"adjudicator registration schema must be {TASK_ADJUDICATOR_REGISTRATION_SCHEMA}"
        )
    raw_selector = payload.get("task_selector")
    raw_backend = payload.get("backend")
    raw_identity = payload.get("identity_claims")
    raw_quorum = payload.get("quorum")
    if (
        not isinstance(raw_selector, Mapping)
        or not isinstance(raw_backend, Mapping)
        or not isinstance(raw_identity, Mapping)
        or not isinstance(raw_quorum, Mapping)
    ):
        raise ProgramAdjudicatorProtocolError(
            "adjudicator selector, backend, identity, and quorum must be objects"
        )
    selector = {str(key): value for key, value in raw_selector.items()}
    backend = {str(key): value for key, value in raw_backend.items()}
    identity = {str(key): value for key, value in raw_identity.items()}
    quorum = {str(key): value for key, value in raw_quorum.items()}
    if (
        identity.get("authenticated") is not False
        or identity.get("verifier_receipt") is not None
    ):
        raise ProgramAdjudicatorProtocolError(
            "DSPx adjudicator registrations cannot authenticate identity claims"
        )
    subjects = identity.get("subjects")
    kinds = identity.get("subject_kinds")
    if (
        not isinstance(subjects, list)
        or not all(isinstance(item, str) for item in subjects)
        or not isinstance(kinds, list)
        or not all(isinstance(item, str) for item in kinds)
    ):
        raise ProgramAdjudicatorProtocolError(
            "adjudicator identity subjects and subject kinds must be label lists"
        )
    if backend.get("execution_support") == "implemented":
        builtin = builtin_foundry_deterministic_registration()
        if not allow_internal_implemented or dict(payload) != builtin:
            raise ProgramAdjudicatorProtocolError(
                "external adjudicator registrations cannot claim implemented execution support"
            )
        return builtin
    priority = selector.get("priority")
    quorum_required = quorum.get("required")
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ProgramAdjudicatorProtocolError(
            "adjudicator registration priority must be an integer"
        )
    if quorum_required is not None and (
        isinstance(quorum_required, bool) or not isinstance(quorum_required, int)
    ):
        raise ProgramAdjudicatorProtocolError(
            "adjudicator registration quorum required must be an integer or null"
        )
    expected = build_task_adjudicator_registration(
        task_kind=str(selector.get("task_kind") or ""),
        kind=str(backend.get("kind") or ""),
        implementation_id=str(backend.get("implementation_id") or ""),
        subjects=subjects,
        subject_kinds=kinds,
        priority=priority,
        quorum_mode=str(quorum.get("mode") or ""),
        quorum_required=quorum_required,
    )
    if dict(payload) != expected:
        raise ProgramAdjudicatorProtocolError(
            "adjudicator registration does not match its canonical contract"
        )
    return expected


def load_task_adjudicator_registration(path: Path) -> tuple[dict[str, Any], str]:
    """Load one external protocol registration; executable claims fail closed."""

    try:
        raw = read_regular_bytes(path, label="task adjudicator registration")
    except (OSError, ValueError) as exc:
        raise ProgramAdjudicatorProtocolError(
            f"task adjudicator registration cannot be read safely: {path}"
        ) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramAdjudicatorProtocolError(
            "task adjudicator registration must be valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramAdjudicatorProtocolError(
            "task adjudicator registration must contain one JSON object"
        )
    return validate_task_adjudicator_registration(payload), _sha256(raw)


def select_task_adjudicator(
    *,
    task_kind: str,
    registrations: Sequence[Mapping[str, Any]],
    include_builtin_fallback: bool = True,
) -> dict[str, Any]:
    """Select one exact task registration without executing or authenticating it."""

    normalized_task_kind = str(task_kind).strip()
    if not normalized_task_kind:
        raise ProgramAdjudicatorProtocolError(
            "adjudicator selection task_kind is required"
        )
    validated_by_id = {
        item["registration_id"]: item
        for item in (
            validate_task_adjudicator_registration(candidate)
            for candidate in registrations
        )
    }
    matches = [
        item
        for item in validated_by_id.values()
        if item["task_selector"]["task_kind"] == normalized_task_kind
        and item["task_selector"]["policy_scope"] == BOUNDED_LOCAL_DISPOSITION_SCOPE
    ]
    fallback_used = False
    if (
        not matches
        and include_builtin_fallback
        and normalized_task_kind == FOUNDRY_GEPA_COMPARISON_TASK_KIND
    ):
        matches = [builtin_foundry_deterministic_registration()]
        fallback_used = True
    ordered = sorted(
        matches,
        key=lambda item: (-item["task_selector"]["priority"], item["registration_id"]),
    )
    if not ordered:
        return {
            "schema_version": TASK_ADJUDICATOR_SELECTION_SCHEMA,
            "status": "require_review",
            "task_kind": normalized_task_kind,
            "disposition": "require_review",
            "reason": "no_matching_adjudicator_registration",
            "selected_registration": None,
            "fallback_used": False,
            "execution_started": False,
            "identity_authenticated_by_dspx": False,
        }
    highest_priority = ordered[0]["task_selector"]["priority"]
    highest = [
        item
        for item in ordered
        if item["task_selector"]["priority"] == highest_priority
    ]
    if len(highest) != 1:
        return {
            "schema_version": TASK_ADJUDICATOR_SELECTION_SCHEMA,
            "status": "require_review",
            "task_kind": normalized_task_kind,
            "disposition": "require_review",
            "reason": "ambiguous_highest_priority_adjudicators",
            "candidate_registration_ids": [item["registration_id"] for item in highest],
            "selected_registration": None,
            "fallback_used": fallback_used,
            "execution_started": False,
            "identity_authenticated_by_dspx": False,
        }
    selected = highest[0]
    support = selected["backend"]["execution_support"]
    return {
        "schema_version": TASK_ADJUDICATOR_SELECTION_SCHEMA,
        "status": "selected" if support == "implemented" else "pending",
        "task_kind": normalized_task_kind,
        "disposition": "pending",
        "reason": (
            "adjudicator_ready_for_explicit_execution"
            if support == "implemented"
            else "adjudicator_executor_not_implemented"
        ),
        "selected_registration": selected,
        "fallback_used": fallback_used,
        "execution_started": False,
        "identity_authenticated_by_dspx": False,
    }
