"""Call, journal, and AK custody for foundry-only dspy-lm-auth jury calls."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

from dspx.services.program_foundry_gepa_comparison_jury_ak_runtime import (
    FoundryJuryAKRuntimeError,
    run_ak_task_show,
)
from dspx.services.program_foundry_gepa_comparison_jury_owner import (
    VerifiedFoundryJuryOwner,
)
from dspx.services.program_model_jury_provider_runtime import (
    ProgramModelJuryProviderExecutionError,
)
from dspx.services.soomfon_provider_outcome_receipt_contract import (
    ProviderOutcomeConsumerError,
    ReceiptReservation,
    canonical_json,
    sha256,
)
from dspx.services.soomfon_provider_outcome_receipt_journal import ReceiptJournal
from dspx.services.soomfon_provider_outcome_receipt_reducer import (
    reduce_verified_chain,
    verify_receipt_chain,
)

PROVIDER_NAME = "foundry-dspy-lm-auth-codex"
AUTH_PROVIDER = "codex"
CREDENTIAL_MODE = "no-refresh"
DEFAULT_CODEX_MODEL = "gpt-5.6-luna"
DEFAULT_REASONING_EFFORT = "xhigh"
DEFAULT_TIMEOUT_SECONDS = 60.0
IMPLEMENTATION_TASK_ID = 5308
EXECUTION_TASK_TITLE = (
    "Execute one receipt-bound foundry comparison jury with dspy-lm-auth Codex"
)
ENDPOINT_ORIGIN_SHA256 = (
    "7d4b206e8a080358f16d8048e0705d8e17c9df9b8968ab150ff73ed1643294c8"
)
ALLOWED_REASONING_EFFORTS = frozenset({"low", "medium", "high", "xhigh"})
MODEL_RE = re.compile(r"^gpt-[A-Za-z0-9][A-Za-z0-9.-]{0,63}$")
_JUROR_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_CLAIMANT_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_LOCAL_CLOSED_STOP_REASONS = frozenset(
    {
        "canonical_authority_or_owner_invalid",
        "jury_logical_call_order_drift",
        "pre_effect_provider_custody_failed",
        "local_postprocessing_failed_after_closed_receipt",
        "provider_invocation_failed_after_closed_receipt",
    }
)


class FoundryJuryProviderConfigurationError(ValueError):
    """Raised before a task-local provider runtime is configured."""


def closed_failure(reason: str) -> NoReturn:
    raise ProgramModelJuryProviderExecutionError(reason, effect_indeterminate=False)


def indeterminate_failure(reason: str) -> NoReturn:
    raise ProgramModelJuryProviderExecutionError(reason, effect_indeterminate=True)


def _private_directory(path: Path, *, create: bool = False) -> Path:
    target = path.expanduser().absolute()
    if create:
        try:
            os.mkdir(target, 0o700)
            os.chmod(target, 0o700)
        except FileExistsError as exc:
            raise FoundryJuryProviderConfigurationError(
                "provider outcome journal root is already consumed"
            ) from exc
        except OSError as exc:
            raise FoundryJuryProviderConfigurationError(
                "provider outcome journal root cannot be created"
            ) from exc
    try:
        info = target.lstat()
        resolved = target.resolve(strict=True)
    except OSError as exc:
        raise FoundryJuryProviderConfigurationError(
            "provider outcome journal root is unavailable"
        ) from exc
    if (
        target.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or resolved != target
    ):
        raise FoundryJuryProviderConfigurationError(
            "provider outcome journal root posture is invalid"
        )
    return resolved


def _journal_projection_sha256(journal: Any) -> str:
    return sha256(
        canonical_json(
            {
                "reservation_id": journal.reservation.reservation_id,
                "event_sha256": [event.digest for event in journal.events],
                "artifact_verification": journal.artifact_verification,
            }
        )
    )


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise FoundryJuryProviderConfigurationError(
            "canonical AK task lease is unavailable"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FoundryJuryProviderConfigurationError(
            "canonical AK task lease is invalid"
        ) from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def canonical_ak_task_revalidator(
    *,
    execution_task_id: int,
    execution_claimant: str,
    repo_root: Path,
    minimum_lease_seconds: float,
) -> Callable[[], None]:
    """Build an exact-binary canonical-AK claim/lease revalidator for each call."""

    if (
        isinstance(execution_task_id, bool)
        or not isinstance(execution_task_id, int)
        or execution_task_id < 1
        or execution_task_id == IMPLEMENTATION_TASK_ID
        or _CLAIMANT_RE.fullmatch(execution_claimant) is None
        or minimum_lease_seconds < 1
    ):
        raise FoundryJuryProviderConfigurationError(
            "execution task authority parameters are invalid"
        )
    expected_repo = repo_root.expanduser().resolve(strict=True)

    def revalidate() -> None:
        try:
            task = run_ak_task_show(execution_task_id)
            observed_repo = (
                Path(str(task.get("repo"))).expanduser().resolve(strict=True)
            )
        except (FoundryJuryAKRuntimeError, OSError) as exc:
            raise FoundryJuryProviderConfigurationError(
                "canonical AK task read is invalid"
            ) from exc
        remaining = (
            _parse_timestamp(task.get("lease_expires_at")) - datetime.now(UTC)
        ).total_seconds()
        if (
            task.get("id") != execution_task_id
            or observed_repo != expected_repo
            or task.get("status") != "claimed"
            or task.get("claimed_by") != execution_claimant
            or task.get("title") != EXECUTION_TASK_TITLE
            or task.get("result") is not None
            or task.get("completed_at") is not None
            or remaining < minimum_lease_seconds
        ):
            raise FoundryJuryProviderConfigurationError(
                "canonical AK task authority is not active"
            )

    return revalidate


def _request_identity(
    *, contract_sha256: str, execution_task_id: int, ordinal: int, juror_id: str
) -> tuple[str, str, str]:
    logical = sha256(
        b"dspx-foundry-jury-logical-request-v1\0"
        + canonical_json(
            {
                "contract_sha256": contract_sha256,
                "ordinal": ordinal,
                "juror_id": juror_id,
                "execution_task_id": execution_task_id,
            }
        )
    )
    process = sha256(
        b"dspx-foundry-jury-process-v1\0"
        + canonical_json({"contract_sha256": contract_sha256})
    )
    gate = sha256(
        b"dspx-foundry-jury-transport-gate-v1\0"
        + canonical_json({"logical_request_id": logical})
    )
    return logical, process, gate


class FoundryJuryCallCustodian:
    """One receipt journal per juror with closed failure and no replay."""

    def __init__(
        self,
        *,
        journal_parent: Path,
        owner: VerifiedFoundryJuryOwner,
        execution_task_id: int,
        contract_sha256: str,
        expected_juror_ids: Sequence[str],
        requested_route: str,
        resolved_route: str,
        authority_revalidator: Callable[[], None],
    ) -> None:
        juror_ids = tuple(expected_juror_ids)
        invalid_identity = (
            not juror_ids
            or len(set(juror_ids)) != len(juror_ids)
            or any(_JUROR_ID_RE.fullmatch(item) is None for item in juror_ids)
            or re.fullmatch(r"[0-9a-f]{64}", contract_sha256) is None
            or isinstance(execution_task_id, bool)
            or not isinstance(execution_task_id, int)
            or execution_task_id < 1
            or execution_task_id == IMPLEMENTATION_TASK_ID
            or not callable(authority_revalidator)
        )
        if invalid_identity:
            raise FoundryJuryProviderConfigurationError(
                "foundry jury call custody identity is invalid"
            )
        owner.revalidate()
        self._journal_parent = _private_directory(journal_parent, create=True)
        self._owner = owner
        self._execution_task_id = execution_task_id
        self._contract_sha256 = contract_sha256
        self._expected_juror_ids = juror_ids
        self._requested_route = requested_route
        self._resolved_route = resolved_route
        self._authority_revalidator = authority_revalidator
        self._records: list[dict[str, object]] = []
        self._terminal = False
        self._stop_reason: str | None = None

    def _reservation(
        self, *, ordinal: int, juror_id: str, semantic_request_sha256: str
    ) -> ReceiptReservation:
        logical, process, gate = _request_identity(
            contract_sha256=self._contract_sha256,
            execution_task_id=self._execution_task_id,
            ordinal=ordinal,
            juror_id=juror_id,
        )
        return ReceiptReservation(
            consumer_task_id=self._execution_task_id,
            ledger_sha256=self._contract_sha256,
            process_id=process,
            case_id=f"jury-{ordinal}",
            logical_request_id=logical,
            transport_gate_id=gate,
            semantic_request_sha256=semantic_request_sha256,
            contract_sha256=self._contract_sha256,
            mode="sync",
            requested_route=self._requested_route,
            resolved_route=self._resolved_route,
            endpoint_origin_sha256=ENDPOINT_ORIGIN_SHA256,
            source_identity=self._owner.artifact.source_identity,
            dependency_identity=self._owner.artifact.dependency_identity,
        )

    def invoke(
        self,
        *,
        juror_id: str,
        semantic_request_sha256: str,
        invoke: Callable[[object], Any],
    ) -> Any:
        ordinal = len(self._records) + 1
        if self._terminal:
            closed_failure("provider_session_terminal")
        if (
            ordinal > len(self._expected_juror_ids)
            or juror_id != self._expected_juror_ids[ordinal - 1]
            or re.fullmatch(r"[0-9a-f]{64}", semantic_request_sha256) is None
        ):
            self._terminal = True
            self._stop_reason = (
                "jury_logical_call_order_drift" if self._records else None
            )
            closed_failure("jury_logical_call_order_drift")
        try:
            self._authority_revalidator()
            self._owner.revalidate()
        except BaseException:
            self._terminal = True
            self._stop_reason = (
                "canonical_authority_or_owner_invalid" if self._records else None
            )
            closed_failure("canonical_authority_or_owner_invalid")
        reservation = self._reservation(
            ordinal=ordinal,
            juror_id=juror_id,
            semantic_request_sha256=semantic_request_sha256,
        )
        root = self._journal_parent / f"{ordinal:02d}-{reservation.logical_request_id}"
        try:
            journal = ReceiptJournal.create(root, reservation, self._owner.artifact)
            receipt = journal.provider_receipt()
        except ProviderOutcomeConsumerError as exc:
            self._terminal = True
            self._stop_reason = (
                "pre_effect_provider_custody_failed" if self._records else None
            )
            if exc.effect_possible:
                indeterminate_failure(exc.reason)
            closed_failure(exc.reason)
        result: Any = None
        invocation_error: BaseException | None = None
        try:
            result = invoke(receipt)
        except BaseException as exc:
            invocation_error = exc
        try:
            loaded = journal.load_verified()
            reduced = reduce_verified_chain(verify_receipt_chain(loaded))
            if loaded.artifact_verification != "accepted_exact":
                raise ProviderOutcomeConsumerError(
                    "accepted_owner_artifact_required",
                    effect_possible=reduced.external_effect_possible,
                )
            self._owner.revalidate()
        except ProviderOutcomeConsumerError as exc:
            self._terminal = True
            self._stop_reason = (
                "pre_effect_provider_custody_failed" if self._records else None
            )
            if exc.effect_possible:
                indeterminate_failure(exc.reason)
            closed_failure(exc.reason)
        self._records.append(
            {
                "call_ordinal": ordinal,
                "juror_id": juror_id,
                "reservation_id": reservation.reservation_id,
                "journal_sha256": _journal_projection_sha256(loaded),
                "semantic_request_sha256": reservation.semantic_request_sha256,
                "provider_outcome_receipt": "accepted",
                "request_acknowledged": reduced.request_acknowledged,
                "external_effect_possible": reduced.external_effect_possible,
                "producer_terminal": reduced.terminal,
                "status_class": reduced.status_class,
                "status_code": reduced.status_code,
                "empirical_disposition": reduced.empirical_disposition,
                "reason": reduced.reason,
            }
        )
        if reduced.terminal != "provider_response_completed":
            self._terminal = True
            self._stop_reason = reduced.reason
            if reduced.empirical_disposition == "effect_indeterminate":
                indeterminate_failure(reduced.reason)
            closed_failure(reduced.reason)
        if invocation_error is not None:
            self._terminal = True
            self._stop_reason = "provider_invocation_failed_after_closed_receipt"
            closed_failure("provider_invocation_failed_after_closed_receipt")
        return result

    def latch_closed_after_completed_call(self) -> None:
        """Record that local post-processing stopped after a closed provider call."""

        if (
            self._records
            and self._records[-1]["producer_terminal"] == "provider_response_completed"
        ):
            self._terminal = True
            self._stop_reason = self._stop_reason or (
                "local_postprocessing_failed_after_closed_receipt"
            )

    def evidence(self) -> dict[str, Any]:
        return {
            "schema_version": "dspx-foundry-jury-provider-outcome-evidence-v1",
            "artifact_verification": (
                "accepted_exact" if self._owner.artifact.accepted else "fixture_only"
            ),
            "logical_call_total": len(self._records),
            "maximum_logical_calls": len(self._expected_juror_ids),
            "maximum_provider_transports": len(self._expected_juror_ids),
            "sync_only": True,
            "fallback_allowed": False,
            "health_probe_allowed": False,
            "retry_count": 0,
            "session_disposition": (
                "closed_terminal" if self._terminal else "complete"
            ),
            "stopped_after_call": len(self._records) if self._terminal else None,
            "stop_reason": self._stop_reason if self._terminal else None,
            "call_records": [dict(item) for item in self._records],
        }

    def finalize(self) -> dict[str, Any]:
        if not self._records:
            closed_failure("provider_call_evidence_missing")
        if not self._terminal and len(self._records) != len(self._expected_juror_ids):
            indeterminate_failure("provider_call_count_incomplete")
        if self._terminal and not self._stop_reason:
            closed_failure("provider_closed_stop_reason_missing")
        return self.evidence()
