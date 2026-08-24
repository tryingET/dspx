# summary: "Exact owner, request, reservation, and hidden one-delegation custody for v11."
from __future__ import annotations

import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_artifacts_v11 import ConsumedAttempt
from dspx.services.program_oracle_semantic_contract_v11 import (
    BoundContractCase,
    CASE_ORDER,
    SemanticV11Error,
    assert_sha256,
    canonical,
    semantic_request_sha256,
    sha256,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    EXPECTED_ENDPOINT_ORIGIN_SHA256,
    REQUESTED_ROUTE,
    RESOLVED_ROUTE,
)
from dspx.services.provider_outcome_receipt_contract import ReceiptReservation
from dspx.services.provider_outcome_receipt_identity import (
    VerifiedOwnerArtifact,
    verify_owner_artifact,
)

LOGICAL_REQUEST_DOMAIN = b"dspx-oracle-semantic-v11-logical-request-v1\0"
TRANSPORT_GATE_DOMAIN = b"dspx-oracle-semantic-v11-transport-gate-v1\0"
PROCESS_DOMAIN = b"dspx-oracle-semantic-v11-process-v1\0"


class VerifiedV11Owner:
    """Exact accepted producer artifact plus its loaded public LM type."""

    __slots__ = ("artifact", "lm_type", "_lm_source", "_sealed")

    artifact: VerifiedOwnerArtifact
    lm_type: type[Any]
    _lm_source: Path
    _sealed: bool

    def __init__(
        self,
        artifact: VerifiedOwnerArtifact,
        lm_type: type[Any],
        lm_source: Path,
    ) -> None:
        if type(artifact) is not VerifiedOwnerArtifact or artifact.accepted is not True:
            raise SemanticV11Error("verified v11 owner artifact drift")
        object.__setattr__(self, "artifact", artifact)
        object.__setattr__(self, "lm_type", lm_type)
        object.__setattr__(self, "_lm_source", lm_source)
        object.__setattr__(self, "_sealed", True)
        self.revalidate()

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


def domain_id(domain: bytes, payload: Mapping[str, Any]) -> str:
    return sha256(domain + canonical(dict(payload)))


def process_id(attempt: ConsumedAttempt) -> str:
    ledger = attempt.ledger
    return domain_id(
        PROCESS_DOMAIN,
        {
            "live_task_id": attempt.binding.live_task_id,
            "state_root_identity_sha256": attempt.binding.state_root_identity_sha256,
            "ledger_sha256": attempt.ledger_sha256,
            "process_identity_sha256": assert_sha256(
                ledger.get("process_identity_sha256"), "process_identity_sha256"
            ),
        },
    )


def logical_request_id(attempt: ConsumedAttempt, case: BoundContractCase) -> str:
    case.require_canonical()
    if case.case_id != CASE_ORDER[case.case_ordinal - 1]:
        raise SemanticV11Error("case identity/ordinal drift")
    return domain_id(
        LOGICAL_REQUEST_DOMAIN,
        {
            "live_task_id": attempt.binding.live_task_id,
            "state_root_identity_sha256": attempt.binding.state_root_identity_sha256,
            "contract_sha256": case.contract_sha256,
            "ledger_sha256": attempt.ledger_sha256,
            "case_id": case.case_id,
            "case_ordinal": case.case_ordinal,
        },
    )


def transport_gate_id(logical_request: str) -> str:
    return domain_id(
        TRANSPORT_GATE_DOMAIN,
        {
            "logical_request_id": assert_sha256(logical_request, "logical_request_id"),
            "gate_ordinal": 1,
        },
    )


def expected_reservation(
    attempt: ConsumedAttempt,
    *,
    case: BoundContractCase,
    semantic_request: Mapping[str, Any],
    artifact: VerifiedOwnerArtifact,
) -> ReceiptReservation:
    """Reconstruct every reservation field, including the fixed endpoint origin."""

    case.require_canonical()
    if type(artifact) is not VerifiedOwnerArtifact or artifact.accepted is not True:
        raise SemanticV11Error("exact owner artifact required")
    artifact.revalidate()
    if attempt.ledger.get("contract_sha256") != case.contract_sha256:
        raise SemanticV11Error("attempt/bound contract digest drift")
    logical = logical_request_id(attempt, case)
    return ReceiptReservation(
        consumer_task_id=attempt.binding.live_task_id,
        ledger_sha256=attempt.ledger_sha256,
        process_id=process_id(attempt),
        case_id=case.case_id,
        logical_request_id=logical,
        transport_gate_id=transport_gate_id(logical),
        semantic_request_sha256=semantic_request_sha256(semantic_request),
        contract_sha256=case.contract_sha256,
        mode="sync",
        requested_route=REQUESTED_ROUTE,
        resolved_route=RESOLVED_ROUTE,
        endpoint_origin_sha256=EXPECTED_ENDPOINT_ORIGIN_SHA256,
        source_identity=artifact.source_identity,
        dependency_identity=artifact.dependency_identity,
    )


def assert_exact_reservation(
    observed: ReceiptReservation, expected: ReceiptReservation
) -> None:
    """Compare the complete closed payload; no field or route alias is tolerated."""

    if (
        type(observed) is not ReceiptReservation
        or type(expected) is not ReceiptReservation
    ):
        raise SemanticV11Error("reservation type drift")
    if observed.payload() != expected.payload():
        raise SemanticV11Error("retained reservation exact-field drift")


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
    return VerifiedV11Owner(artifact, lm_type, expected)
