# summary: "Exact task, request, owner, reservation, and journal identity for semantic v11."
from __future__ import annotations

import inspect
import json

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_artifacts_v11 import (
    PROVIDER_OUTCOMES_NAME,
    ConsumedAttempt,
    TaskBinding,
    record_case_terminal,
    reserve_case,
)
from dspx.services.program_oracle_semantic_contract_v11 import (
    BoundContractCase,
    CASE_ORDER,
    SemanticV11Error,
    assert_sha256,
    canonical,
    semantic_request_sha256,
    sha256,
)
from dspx.services.program_oracle_semantic_result_v11 import VerifiedSemanticResult
from dspx.services.provider_outcome_receipt_contract import (
    ReceiptProjection,
    ReceiptReservation,
)
from dspx.services.provider_outcome_receipt_identity import (
    VerifiedOwnerArtifact,
    verify_owner_artifact,
)
from dspx.services.provider_outcome_receipt_journal import ReceiptJournal

LOGICAL_REQUEST_DOMAIN = b"dspx-oracle-semantic-v11-logical-request-v1\0"
TRANSPORT_GATE_DOMAIN = b"dspx-oracle-semantic-v11-transport-gate-v1\0"
PROCESS_DOMAIN = b"dspx-oracle-semantic-v11-process-v1\0"
REQUESTED_ROUTE = "dspy-lm-auth:codex:gpt-5.6-sol:max"
RESOLVED_ROUTE = "openai:gpt-5.6-sol:responses"


_VERIFIED_V11_OWNER_TOKEN = object()


class VerifiedV11Owner:
    """Exact accepted producer artifact plus its public LM type."""

    __slots__ = ("artifact", "lm_type", "_lm_source", "_sealed")

    artifact: VerifiedOwnerArtifact
    lm_type: type[Any]
    _lm_source: Path
    _sealed: bool

    def __init__(
        self,
        *,
        artifact: VerifiedOwnerArtifact,
        lm_type: type[Any],
        lm_source: Path,
        token: object,
    ) -> None:
        if token is not _VERIFIED_V11_OWNER_TOKEN:
            raise TypeError("VerifiedV11Owner is created by exact owner verification")
        if type(artifact) is not VerifiedOwnerArtifact or artifact.accepted is not True:
            raise SemanticV11Error("verified v11 owner artifact drift")
        object.__setattr__(self, "artifact", artifact)
        object.__setattr__(self, "lm_type", lm_type)
        object.__setattr__(self, "_lm_source", lm_source)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("VerifiedV11Owner is immutable")
        object.__setattr__(self, name, value)

    def revalidate(self) -> None:
        if type(self) is not VerifiedV11Owner:
            raise SemanticV11Error("verified v11 owner type drift")
        self.artifact.revalidate()
        source = inspect.getsourcefile(self.lm_type)
        if (
            self.lm_type.__module__ != "dspy_lm_auth.lm"
            or self.lm_type.__name__ != "LM"
            or source is None
            or Path(source).resolve(strict=True) != self._lm_source
        ):
            raise SemanticV11Error("verified owner LM type drift")


_PREPARED_RECEIPT_TOKEN = object()


class PreparedReceipt:
    """Opaque paired request/journal capability created only after exact custody."""

    __slots__ = (
        "attempt",
        "reservation",
        "journal",
        "_provider_receipt",
        "_semantic_raw",
        "_case",
        "case_ordinal",
        "_owner",
        "_sealed",
    )

    attempt: ConsumedAttempt
    reservation: ReceiptReservation
    journal: ReceiptJournal
    _provider_receipt: object
    _semantic_raw: bytes
    _case: BoundContractCase
    case_ordinal: int
    _owner: VerifiedV11Owner
    _sealed: bool

    def __init__(
        self,
        *,
        attempt: ConsumedAttempt,
        reservation: ReceiptReservation,
        journal: ReceiptJournal,
        provider_receipt: object,
        semantic_request: Mapping[str, Any],
        case: BoundContractCase,
        owner: VerifiedV11Owner,
        token: object,
    ) -> None:
        if token is not _PREPARED_RECEIPT_TOKEN:
            raise TypeError("PreparedReceipt is created by exact receipt custody")
        if type(attempt) is not ConsumedAttempt or type(journal) is not ReceiptJournal:
            raise SemanticV11Error("prepared receipt capability type drift")
        if type(owner) is not VerifiedV11Owner:
            raise SemanticV11Error("prepared owner artifact type drift")
        if type(case) is not BoundContractCase:
            raise SemanticV11Error("prepared bound case type drift")
        case.require_canonical()
        owner.revalidate()
        object.__setattr__(self, "attempt", attempt)
        object.__setattr__(self, "reservation", reservation)
        object.__setattr__(self, "journal", journal)
        object.__setattr__(self, "_provider_receipt", provider_receipt)
        object.__setattr__(self, "_semantic_raw", canonical(dict(semantic_request)))
        object.__setattr__(self, "_case", case)
        object.__setattr__(self, "case_ordinal", case.case_ordinal)
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("PreparedReceipt is immutable")
        object.__setattr__(self, name, value)

    @property
    def semantic_request(self) -> Mapping[str, Any]:
        value = json.loads(self._semantic_raw)
        if not isinstance(value, Mapping):  # pragma: no cover - constructor invariant
            raise SemanticV11Error("prepared semantic request schema drift")
        return dict(value)

    def require_effect_capability(self) -> None:
        if type(self) is not PreparedReceipt:
            raise SemanticV11Error("prepared receipt capability type drift")
        self.attempt.require_live()
        self._owner.revalidate()
        if (
            semantic_request_sha256(self.semantic_request)
            != self.reservation.semantic_request_sha256
        ):
            raise SemanticV11Error("prepared semantic request digest drift")
        if (
            type(self.journal) is not ReceiptJournal
            or self.journal._root.parent
            != self.attempt.attempt_root / PROVIDER_OUTCOMES_NAME
            or self.journal._reservation != self.reservation
            or self.reservation.source_identity != self._owner.artifact.source_identity
            or self.reservation.dependency_identity
            != self._owner.artifact.dependency_identity
            or type(self._provider_receipt) is not self._owner.artifact.receipt_type
            or getattr(self._provider_receipt, "logical_request_id", None)
            != self.reservation.logical_request_id
            or getattr(self._provider_receipt, "semantic_request_sha256", None)
            != self.reservation.semantic_request_sha256
        ):
            raise SemanticV11Error("prepared receipt/journal pairing drift")

    @property
    def owner_lm_type(self) -> type[Any]:
        self._owner.revalidate()
        return self._owner.lm_type

    def record_terminal(
        self, semantic_result: VerifiedSemanticResult
    ) -> ReceiptProjection:
        self.require_effect_capability()
        if semantic_result._case is not self._case:
            raise SemanticV11Error("semantic result/prepared case capability drift")
        return record_case_terminal(
            self.attempt,
            case=self._case,
            semantic_result=semantic_result,
            journal=self.journal,
            artifact=self._owner.artifact,
        )


def domain_id(domain: bytes, payload: Mapping[str, Any]) -> str:
    return sha256(domain + canonical(dict(payload)))


def process_id(attempt: ConsumedAttempt) -> str:
    process_digest = attempt.ledger.get("process_identity_sha256")
    return domain_id(
        PROCESS_DOMAIN,
        {
            "live_task_id": attempt.binding.live_task_id,
            "ledger_sha256": attempt.ledger_sha256,
            "process_identity_sha256": assert_sha256(
                process_digest, "process_identity_sha256"
            ),
        },
    )


def logical_request_id(
    binding: TaskBinding,
    *,
    contract_sha256: str,
    ledger_sha256: str,
    case_id: str,
    case_ordinal: int,
) -> str:
    if (
        case_ordinal < 1
        or case_ordinal > len(CASE_ORDER)
        or case_id != CASE_ORDER[case_ordinal - 1]
    ):
        raise SemanticV11Error("case identity/ordinal drift")
    return domain_id(
        LOGICAL_REQUEST_DOMAIN,
        {
            "live_task_id": binding.live_task_id,
            "contract_sha256": assert_sha256(contract_sha256, "contract_sha256"),
            "ledger_sha256": assert_sha256(ledger_sha256, "ledger_sha256"),
            "case_id": case_id,
            "case_ordinal": case_ordinal,
        },
    )


def transport_gate_id(logical_request: str) -> str:
    return domain_id(
        TRANSPORT_GATE_DOMAIN,
        {"logical_request_id": logical_request, "gate_ordinal": 1},
    )


def verify_exact_owner(
    owner_source_root: Path,
    event_type: type[Any],
    receipt_type: type[Any],
    lm_type: type[Any],
) -> VerifiedV11Owner:
    artifact = verify_owner_artifact(owner_source_root, event_type, receipt_type)
    try:
        observed = Path(inspect.getsourcefile(lm_type) or "").resolve(strict=True)
        expected = (
            owner_source_root.expanduser().resolve(strict=True)
            / "src/dspy_lm_auth/lm.py"
        ).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SemanticV11Error("verified owner LM source unavailable") from exc
    if (
        lm_type.__module__ != "dspy_lm_auth.lm"
        or lm_type.__name__ != "LM"
        or observed != expected
    ):
        raise SemanticV11Error("verified owner LM source drift")
    owner = VerifiedV11Owner(
        artifact=artifact,
        lm_type=lm_type,
        lm_source=expected,
        token=_VERIFIED_V11_OWNER_TOKEN,
    )
    owner.revalidate()
    return owner


def prepare_receipt(
    attempt: ConsumedAttempt,
    *,
    case: BoundContractCase,
    semantic_request: Mapping[str, Any],
    endpoint_origin_sha256: str,
    artifact: VerifiedV11Owner,
) -> PreparedReceipt:
    if type(artifact) is not VerifiedV11Owner:
        raise SemanticV11Error("exact accepted owner artifact required")
    if type(case) is not BoundContractCase:
        raise SemanticV11Error("exact bound contract case required")
    case.require_canonical()
    attempt.require_live()
    if attempt.ledger.get("contract_sha256") != case.contract_sha256:
        raise SemanticV11Error("attempt/bound contract digest drift")
    artifact.revalidate()
    owner_artifact = artifact.artifact
    case_id = case.case_id
    case_ordinal = case.case_ordinal
    logical = logical_request_id(
        attempt.binding,
        contract_sha256=case.contract_sha256,
        ledger_sha256=attempt.ledger_sha256,
        case_id=case_id,
        case_ordinal=case_ordinal,
    )
    request_digest = semantic_request_sha256(semantic_request)
    reservation = ReceiptReservation(
        consumer_task_id=attempt.binding.live_task_id,
        ledger_sha256=attempt.ledger_sha256,
        process_id=process_id(attempt),
        case_id=case_id,
        logical_request_id=logical,
        transport_gate_id=transport_gate_id(logical),
        semantic_request_sha256=request_digest,
        contract_sha256=case.contract_sha256,
        mode="sync",
        requested_route=REQUESTED_ROUTE,
        resolved_route=RESOLVED_ROUTE,
        endpoint_origin_sha256=assert_sha256(
            endpoint_origin_sha256, "endpoint_origin_sha256"
        ),
        source_identity=owner_artifact.source_identity,
        dependency_identity=owner_artifact.dependency_identity,
    )
    # Force complete closed-schema validation and durable fixed-order custody
    # before creating the single-use journal.
    reservation_payload = reservation.payload()
    reserve_case(
        attempt,
        case=case,
        logical_request_id=logical,
        semantic_request_sha256=request_digest,
        reservation_sha256=sha256(canonical(reservation_payload)),
    )
    parent = attempt.attempt_root / PROVIDER_OUTCOMES_NAME
    journal_root = parent / f"{case_ordinal:02d}-{case_id}"
    journal = ReceiptJournal.create(journal_root, reservation, owner_artifact)
    receipt = journal.provider_receipt()
    return PreparedReceipt(
        attempt=attempt,
        reservation=reservation,
        journal=journal,
        provider_receipt=receipt,
        semantic_request=semantic_request,
        case=case,
        owner=artifact,
        token=_PREPARED_RECEIPT_TOKEN,
    )
