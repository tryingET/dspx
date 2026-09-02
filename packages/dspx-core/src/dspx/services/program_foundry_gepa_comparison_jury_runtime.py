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
    ALLOWED_REASONING_EFFORTS,
    IMPLEMENTATION_TASK_ID,
    MODEL_RE,
    canonical_ak_task_revalidator,
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

COMMON_EXECUTION_REQUEST_KEYS = {
    "provider",
    "adjudicator_id",
    "adjudicator_kind",
    "adjudicator_repo",
    "max_jurors",
}
TASK_LOCAL_EXECUTION_REQUEST_KEYS = COMMON_EXECUTION_REQUEST_KEYS | {
    "owner_source_root",
    "execution_task_id",
    "execution_claimant",
    "codex_model",
    "reasoning_effort",
}
_DSPX_REPO_ROOT = Path(__file__).resolve().parents[5]
_TASK_LOCAL_PROCESS_LOCK = threading.Lock()


class ProgramFoundryGepaComparisonJuryError(ValueError):
    """Raised when a receipt-bound comparison jury cannot execute safely."""


@contextmanager
def task_local_process_slot(provider: str) -> Iterator[None]:
    if provider != TASK_LOCAL_PROVIDER_NAME:
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
    codex_model: str = DEFAULT_CODEX_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
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
    if normalized_provider == TASK_LOCAL_PROVIDER_NAME:
        if (
            owner_source_root is None
            or isinstance(execution_task_id, bool)
            or not isinstance(execution_task_id, int)
            or execution_task_id < 1
            or execution_task_id == IMPLEMENTATION_TASK_ID
            or not isinstance(execution_claimant, str)
            or not execution_claimant.strip()
            or MODEL_RE.fullmatch(codex_model) is None
            or reasoning_effort not in ALLOWED_REASONING_EFFORTS
        ):
            raise ProgramFoundryGepaComparisonJuryError(
                "task-local dspy-lm-auth jury requires owner source and execution task"
            )
        request.update(
            {
                "owner_source_root": str(owner_source_root.expanduser().resolve()),
                "execution_task_id": execution_task_id,
                "execution_claimant": execution_claimant,
                "codex_model": codex_model,
                "reasoning_effort": reasoning_effort,
            }
        )
    elif (
        owner_source_root is not None
        or execution_task_id is not None
        or execution_claimant is not None
    ):
        raise ProgramFoundryGepaComparisonJuryError(
            "owner source and execution task are only valid for the task-local provider"
        )
    return request


def preflight_task_local_request(request: Mapping[str, Any]) -> None:
    if request["provider"] != TASK_LOCAL_PROVIDER_NAME:
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
    if request["provider"] != TASK_LOCAL_PROVIDER_NAME:
        return None

    def make_provider_runtime(
        selected: Sequence[Mapping[str, Any]],
    ) -> Any:
        juror_ids = [
            str(item.get("id") or item.get("perspective") or "") for item in selected
        ]
        return configure_foundry_jury_provider(
            owner_source_root=Path(str(request["owner_source_root"])),
            journal_parent=experiment_root / "provider-outcomes",
            execution_task_id=int(request["execution_task_id"]),
            execution_claimant=str(request["execution_claimant"]),
            repo_root=_DSPX_REPO_ROOT,
            contract_sha256=attempt_sha256,
            expected_juror_ids=juror_ids,
            model=str(request["codex_model"]),
            reasoning_effort=str(request["reasoning_effort"]),
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
                if request["provider"] == TASK_LOCAL_PROVIDER_NAME
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
    "PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_ATTEMPT_SCHEMA",
    "PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA",
    "ProgramFoundryGepaComparisonJuryError",
    "TASK_LOCAL_EXECUTION_REQUEST_KEYS",
    "TASK_LOCAL_PROVIDER_NAME",
    "execution_request",
    "make_task_local_runtime_binding",
    "preflight_task_local_request",
    "receipt_payload",
    "task_local_process_slot",
]
