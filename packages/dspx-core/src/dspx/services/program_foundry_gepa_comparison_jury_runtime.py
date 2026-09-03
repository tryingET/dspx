"""Task-local request, authority, and process runtime for foundry comparison juries."""

from __future__ import annotations

import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping, Sequence

from dspx.services.program_foundry_gepa_comparison_jury_owner import (
    verify_foundry_jury_owner_source,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider import (
    DEFAULT_CODEX_MODEL,
    DEFAULT_REASONING_EFFORT,
    PROVIDER_NAME as TASK_LOCAL_PROVIDER_NAME,
    configure_foundry_jury_provider,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
    CODEX_FAMILY,
    IMPLEMENTATION_TASK_ID,
    TASK_LOCAL_PROVIDER_NAMES,
    FoundryJuryProviderFamily,
    canonical_ak_task_revalidator,
    family_for_provider,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (
    family_for_request,
)
from dspx.services.program_model_jury_provider_runtime import (
    ProgramModelJuryProviderRuntimeBinding,
    _bind_program_model_jury_provider_runtime,
)

PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA = (
    "dspx-program-foundry-gepa-comparison-jury-v1"
)
PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_ATTEMPT_SCHEMA = (
    "dspx-program-foundry-gepa-comparison-jury-attempt-v1"
)

COMMON_EXECUTION_REQUEST_KEYS = frozenset(
    {
        "provider",
        "adjudicator_id",
        "adjudicator_kind",
        "adjudicator_repo",
        "max_jurors",
    }
)
TASK_LOCAL_EXECUTION_REQUEST_KEYS = CODEX_FAMILY.execution_request_keys(
    COMMON_EXECUTION_REQUEST_KEYS
)
_DSPX_REPO_ROOT = Path(__file__).resolve().parents[5]
_TASK_LOCAL_PROCESS_LOCK = threading.Lock()


class ProgramFoundryGepaComparisonJuryError(ValueError):
    """Raised when a receipt-bound comparison jury cannot execute safely."""


def task_local_family(
    request: Mapping[str, Any],
) -> FoundryJuryProviderFamily | None:
    """Family for one normalized request, bound to its retained endpoint."""

    try:
        return family_for_request(request)
    except ValueError as exc:
        raise ProgramFoundryGepaComparisonJuryError(
            "task-local provider endpoint is not bound in the request"
        ) from exc


def task_local_execution_request_keys(provider: object) -> frozenset[str]:
    family = family_for_provider(provider)
    if family is None:
        return COMMON_EXECUTION_REQUEST_KEYS
    return family.execution_request_keys(COMMON_EXECUTION_REQUEST_KEYS)


@contextmanager
def task_local_process_slot(provider: str) -> Iterator[None]:
    if provider not in TASK_LOCAL_PROVIDER_NAMES:
        yield
        return
    if not _TASK_LOCAL_PROCESS_LOCK.acquire(blocking=False):
        raise ProgramFoundryGepaComparisonJuryError(
            "task-local provider process slot is already active"
        )
    try:
        yield
    finally:
        _TASK_LOCAL_PROCESS_LOCK.release()


def _resolve_task_local_model(
    family: FoundryJuryProviderFamily,
    *,
    model: str | None,
    codex_model: str | None,
) -> str:
    if codex_model is not None and family is not CODEX_FAMILY:
        raise ProgramFoundryGepaComparisonJuryError(
            "codex_model is only valid for the Codex task-local family"
        )
    if model is not None and codex_model is not None and model != codex_model:
        raise ProgramFoundryGepaComparisonJuryError(
            "model and codex_model must agree when both are given"
        )
    return family.resolve_model(model if model is not None else codex_model)


def _resolve_task_local_endpoint(
    family: FoundryJuryProviderFamily, endpoint: str | None
) -> FoundryJuryProviderFamily:
    try:
        return family.with_endpoint(endpoint)
    except ValueError as exc:
        raise ProgramFoundryGepaComparisonJuryError(
            "task-local provider endpoint must be an explicit loopback "
            "http://127.0.0.1|localhost|[::1]:<port>/v1 base URL"
        ) from exc


def execution_request(
    *,
    provider: str,
    adjudicator_id: str,
    adjudicator_kind: str,
    adjudicator_repo: str | None,
    max_jurors: int | None,
    owner_source_root: Path | None = None,
    execution_task_id: int | None = None,
    execution_claimant: str | None = None,
    codex_model: str | None = None,
    reasoning_effort: str | None = None,
    model: str | None = None,
    endpoint: str | None = None,
) -> dict[str, Any]:
    normalized_provider = provider.strip()
    if not normalized_provider:
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury requires an explicit provider"
        )
    if not adjudicator_id.strip() or not adjudicator_kind.strip():
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury requires adjudicator id and kind"
        )
    if max_jurors is not None and (isinstance(max_jurors, bool) or max_jurors < 1):
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury max_jurors must be at least one"
        )
    request: dict[str, Any] = {
        "provider": normalized_provider,
        "adjudicator_id": adjudicator_id.strip(),
        "adjudicator_kind": adjudicator_kind.strip(),
        "adjudicator_repo": (
            adjudicator_repo.strip()
            if isinstance(adjudicator_repo, str) and adjudicator_repo.strip()
            else None
        ),
        "max_jurors": max_jurors,
    }
    family = family_for_provider(normalized_provider)
    if family is not None:
        resolved_model = _resolve_task_local_model(
            family, model=model, codex_model=codex_model
        )
        resolved_effort = family.resolve_reasoning_effort(reasoning_effort)
        family = _resolve_task_local_endpoint(family, endpoint)
        if (
            owner_source_root is None
            or isinstance(execution_task_id, bool)
            or not isinstance(execution_task_id, int)
            or execution_task_id < 1
            or execution_task_id == IMPLEMENTATION_TASK_ID
            or not isinstance(execution_claimant, str)
            or not execution_claimant.strip()
            or not family.model_allowed(resolved_model)
            or not family.reasoning_effort_allowed(resolved_effort)
        ):
            raise ProgramFoundryGepaComparisonJuryError(
                "task-local dspy-lm-auth jury requires owner source and execution task"
            )
        request.update(
            {
                "owner_source_root": str(owner_source_root.expanduser().resolve()),
                "execution_task_id": execution_task_id,
                "execution_claimant": execution_claimant,
                family.model_key: resolved_model,
            }
        )
        if family.allowed_reasoning_efforts is not None:
            request["reasoning_effort"] = resolved_effort
        if family.endpoint_key is not None:
            request[family.endpoint_key] = family.endpoint_origin
    elif (
        owner_source_root is not None
        or execution_task_id is not None
        or execution_claimant is not None
        or codex_model is not None
        or reasoning_effort is not None
        or model is not None
        or endpoint is not None
    ):
        raise ProgramFoundryGepaComparisonJuryError(
            "owner source and execution task are only valid for the task-local provider"
        )
    return request


def revalidate_execution_request(raw_request: Mapping[str, Any]) -> dict[str, Any]:
    """Re-normalize one retained execution_request and require exact equality."""

    provider = raw_request.get("provider")
    expected_keys = task_local_execution_request_keys(provider)
    family = family_for_provider(provider)
    adjudicator_id = raw_request.get("adjudicator_id")
    adjudicator_kind = raw_request.get("adjudicator_kind")
    adjudicator_repo = raw_request.get("adjudicator_repo")
    max_jurors = raw_request.get("max_jurors")
    owner_source_root = raw_request.get("owner_source_root")
    execution_task_id = raw_request.get("execution_task_id")
    execution_claimant = raw_request.get("execution_claimant")
    model = raw_request.get(family.model_key) if family is not None else None
    reasoning_effort = raw_request.get("reasoning_effort")
    endpoint = (
        raw_request.get(family.endpoint_key)
        if family is not None and family.endpoint_key is not None
        else None
    )
    if (
        set(raw_request) != expected_keys
        or not isinstance(provider, str)
        or not isinstance(adjudicator_id, str)
        or not isinstance(adjudicator_kind, str)
        or (adjudicator_repo is not None and not isinstance(adjudicator_repo, str))
        or (
            max_jurors is not None
            and (isinstance(max_jurors, bool) or not isinstance(max_jurors, int))
        )
        or (owner_source_root is not None and not isinstance(owner_source_root, str))
        or (
            execution_task_id is not None
            and (
                isinstance(execution_task_id, bool)
                or not isinstance(execution_task_id, int)
            )
        )
        or (execution_claimant is not None and not isinstance(execution_claimant, str))
        or (family is not None and not isinstance(model, str))
        or (reasoning_effort is not None and not isinstance(reasoning_effort, str))
        or (
            family is not None
            and family.endpoint_key is not None
            and not isinstance(endpoint, str)
        )
    ):
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury receipt execution_request types are invalid"
        )
    request = execution_request(
        provider=provider,
        adjudicator_id=adjudicator_id,
        adjudicator_kind=adjudicator_kind,
        adjudicator_repo=adjudicator_repo,
        max_jurors=max_jurors,
        owner_source_root=(
            Path(owner_source_root) if owner_source_root is not None else None
        ),
        execution_task_id=execution_task_id,
        execution_claimant=execution_claimant,
        reasoning_effort=reasoning_effort,
        model=model,
        endpoint=endpoint,
    )
    if request != dict(raw_request):
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury receipt execution_request is not normalized"
        )
    return request


def preflight_task_local_request(request: Mapping[str, Any]) -> None:
    family = family_for_provider(request["provider"])
    if family is None:
        return
    owner_source_root = Path(str(request["owner_source_root"]))
    if any(
        name == "dspy_lm_auth" or name.startswith("dspy_lm_auth.")
        for name in sys.modules
    ):
        raise ProgramFoundryGepaComparisonJuryError(
            "task-local provider requires a fresh one-shot process"
        )
    try:
        verify_foundry_jury_owner_source(owner_source_root)
        canonical_ak_task_revalidator(
            execution_task_id=int(request["execution_task_id"]),
            execution_claimant=str(request["execution_claimant"]),
            repo_root=_DSPX_REPO_ROOT,
            minimum_lease_seconds=90.0,
            family=family,
        )()
    except ValueError as exc:
        raise ProgramFoundryGepaComparisonJuryError(
            "task-local provider preflight rejected exact owner or AK authority"
        ) from exc


def make_task_local_runtime_binding(
    *,
    request: Mapping[str, Any],
    experiment_root: Path,
    attempt_sha256: str,
) -> ProgramModelJuryProviderRuntimeBinding | None:
    family = task_local_family(request)
    if family is None:
        return None
    bound_family = family

    def make_provider_runtime(
        selected: Sequence[Mapping[str, Any]],
    ) -> Any:
        juror_ids = [
            str(item.get("id") or item.get("perspective") or "") for item in selected
        ]
        effort = request.get("reasoning_effort")
        return configure_foundry_jury_provider(
            owner_source_root=Path(str(request["owner_source_root"])),
            journal_parent=experiment_root / "provider-outcomes",
            execution_task_id=int(request["execution_task_id"]),
            execution_claimant=str(request["execution_claimant"]),
            repo_root=_DSPX_REPO_ROOT,
            contract_sha256=attempt_sha256,
            expected_juror_ids=juror_ids,
            model=str(request[bound_family.model_key]),
            reasoning_effort=str(effort) if effort is not None else None,
            family=bound_family,
        )

    return _bind_program_model_jury_provider_runtime(make_provider_runtime)


def receipt_payload(
    *,
    validated: Mapping[str, Any],
    request: Mapping[str, Any],
    attempt_sha256: str,
    result: Mapping[str, Any],
    result_sha256: str,
    paths: Mapping[str, Path],
) -> dict[str, Any]:
    return {
        "schema_version": PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA,
        "status": "ok",
        "jury_status": result["status"],
        "proposal_id": validated["proposal_id"],
        "execution_request": dict(request),
        "bindings": {
            "consumption_receipt_path": str(validated["receipt_path"]),
            "consumption_receipt_sha256": validated["receipt_sha256"],
            "execution_receipt_path": str(validated["execution_receipt_path"]),
            "execution_receipt_sha256": validated["execution_receipt_sha256"],
            "source_manifest_path": str(validated["source_manifest_path"]),
            "source_manifest_sha256": validated["source_manifest_sha256"],
            "candidate_manifest_path": str(validated["candidate_manifest_path"]),
            "candidate_manifest_sha256": validated["candidate_manifest_sha256"],
            "comparison_path": str(validated["comparison_path"]),
            "comparison_sha256": validated["comparison_sha256"],
            "attempt_path": str(paths["attempt"]),
            "attempt_sha256": attempt_sha256,
            "jury_results_path": str(paths["result"]),
            "jury_results_sha256": result_sha256,
        },
        "aggregate": result["aggregate"],
        "effect": {
            "program_specific_jury_executed": True,
            "provider_calls_may_have_occurred": True,
            "comparison_mutated": False,
            "candidate_mutated": False,
            "winner_selected": False,
            "promotion_applied": False,
            "activation_applied": False,
            "external_authority_mutated": False,
            **(
                {"ak_called": True, "ak_mutated": False}
                if request["provider"] in TASK_LOCAL_PROVIDER_NAMES
                else {"ak_called": False}
            ),
        },
        "non_authority": {
            "local_jury_evidence_only": True,
            "winner_selection": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
        },
    }


__all__ = [
    "COMMON_EXECUTION_REQUEST_KEYS",
    "DEFAULT_CODEX_MODEL",
    "DEFAULT_REASONING_EFFORT",
    "PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_ATTEMPT_SCHEMA",
    "PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA",
    "ProgramFoundryGepaComparisonJuryError",
    "TASK_LOCAL_EXECUTION_REQUEST_KEYS",
    "TASK_LOCAL_PROVIDER_NAME",
    "TASK_LOCAL_PROVIDER_NAMES",
    "execution_request",
    "make_task_local_runtime_binding",
    "preflight_task_local_request",
    "receipt_payload",
    "revalidate_execution_request",
    "task_local_execution_request_keys",
    "task_local_family",
    "task_local_process_slot",
]
