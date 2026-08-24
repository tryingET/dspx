# summary: "Validates the provider-free receipt-bound Oracle semantic v11 candidate."
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_contract import OracleSemanticRequest
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CASE_ORDER,
    CONSUMER_MODULE_HASHES,
    CONTRACT_SHA256,
    OPTIONAL_UNSET_KEYS,
    PROPOSAL_SHA256,
    SEMANTIC_KEYS,
    SemanticV11Error,
    assert_sha256,
    canonical,
    mapping,
    semantic_request_projection,
    semantic_request_sha256,
    sha256,
)
from dspx.services.program_oracle_semantic_contract_v10 import (
    INHERITED_KEYS,
    SEMANTICS_PATH,
    SEMANTICS_SHA256,
    V9_PATH,
    V9_SHA256,
    materialized_request as materialized_request_v10,
    score_v10,
)

__all__ = [
    "assert_sha256",
    "semantic_request_projection",
    "semantic_request_sha256",
]

CANDIDATE_TASK_ID = 4691
CONTRACT_PATH = Path("benchmarks/semantic/oracle-semantic-analysis-evaluation-v11.json")
V10_PATH = Path("benchmarks/semantic/oracle-semantic-analysis-evaluation-v10.json")
PROPOSAL_PATH = Path("docs/project/oracle-semantic-analysis-v11-contract-proposal.md")
V10_SHA256 = "fb90f0c266e984489110fc3ae945c3bd37bf71b6ec8f725f56d6167241ab4128"
SCHEMA = "dspx-oracle-semantic-analysis-evaluation-v11"
STATUS = "candidate_requires_receipt_review_and_separate_live_gate"
TEMPLATE_SCHEMA = "dspx-oracle-semantic-analysis-v11-contract-template-v1"
EXPECTED_SCHEMA_BINDINGS = {
    "producer_event_family": "dspy-lm-provider-outcome-receipt-v1",
    "reservation": "dspx-provider-outcome-reservation-v1",
    "consumption": "dspx-provider-outcome-consumption-v1",
    "consumption_event": "dspx-provider-outcome-consumption-event-v1",
    "inflight": "dspx-provider-outcome-inflight-v1",
    "poison": "dspx-provider-outcome-poison-v1",
    "projection": "dspx-provider-outcome-projection-v1",
    "ledger": "dspx-oracle-semantic-v11-ledger-v1",
    "candidate_review": "dspx-oracle-semantic-v11-candidate-review-v1",
    "live_gate": "dspx-oracle-semantic-v11-live-gate-v1",
    "result": "dspx-oracle-semantic-v11-result-v1",
    "verification": "dspx-oracle-semantic-v11-verification-v1",
}
V11_KEYS = {
    "schema_version",
    "status",
    "candidate_task_id",
    "contract_template",
    "proposal_binding",
    "predecessor_bindings",
    "ownership_and_authority",
    "schema_bindings",
    "producer_binding",
    "consumer_binding",
    "dependency_policy",
    "route",
    "request_policy",
    "task_binding_template",
    "attempt_policy",
    "artifact_policy",
    "receipt_policy",
    "terminal_policy",
    "gate_policy",
    *INHERITED_KEYS,
}
_BOUND_CASE_TOKEN = object()


class BoundContractCase:
    """Opaque case loaded from the exact canonical v11 contract bytes."""

    __slots__ = (
        "case_id",
        "case_ordinal",
        "contract_sha256",
        "_contract_raw",
        "_case_raw",
        "_semantics_raw",
        "_sealed",
    )

    case_id: str
    case_ordinal: int
    contract_sha256: str
    _contract_raw: bytes
    _case_raw: bytes
    _semantics_raw: bytes
    _sealed: bool

    def __init__(
        self,
        *,
        case_id: str,
        case_ordinal: int,
        contract_sha256: str,
        contract_raw: bytes,
        case: Mapping[str, Any],
        semantics: Mapping[str, Any],
        token: object,
    ) -> None:
        if token is not _BOUND_CASE_TOKEN:
            raise TypeError("BoundContractCase is loaded from the exact contract")
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "case_ordinal", case_ordinal)
        object.__setattr__(self, "contract_sha256", contract_sha256)
        object.__setattr__(self, "_contract_raw", bytes(contract_raw))
        object.__setattr__(self, "_case_raw", canonical(case))
        object.__setattr__(self, "_semantics_raw", canonical(semantics))
        object.__setattr__(self, "_sealed", True)
        self.require_canonical()

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("BoundContractCase is immutable")
        object.__setattr__(self, name, value)

    def require_canonical(self) -> None:
        if (
            type(self) is not BoundContractCase
            or self.contract_sha256 != CONTRACT_SHA256
            or self.case_ordinal < 1
            or self.case_ordinal > len(CASE_ORDER)
            or self.case_id != CASE_ORDER[self.case_ordinal - 1]
        ):
            raise SemanticV11Error("bound contract case identity drift")
        case = self.case
        contract = mapping(json.loads(self._contract_raw), "bound v11 contract")
        cases = sequence(contract.get("cases"), "bound v11 cases")
        if (
            sha256(self._contract_raw) != self.contract_sha256
            or len(cases) != len(CASE_ORDER)
            or case.get("id") != self.case_id
            or canonical(mapping(cases[self.case_ordinal - 1], "bound case"))
            != self._case_raw
        ):
            raise SemanticV11Error("bound contract case bytes drift")

    @property
    def case(self) -> dict[str, Any]:
        value = json.loads(self._case_raw)
        return mapping(value, "bound contract case")

    def materialized_request(self) -> OracleSemanticRequest:
        self.require_canonical()
        semantics = mapping(json.loads(self._semantics_raw), "bound code semantics")
        return materialized_request_v10(self.case, semantics)

    def score(self, analysis: Mapping[str, Any]) -> dict[str, Any]:
        self.require_canonical()
        return score_v10(self.case, analysis)

    def case_at(self, case_ordinal: int) -> "BoundContractCase":
        """Derive a sibling case only from the same exact contract bytes."""

        self.require_canonical()
        if case_ordinal < 1 or case_ordinal > len(CASE_ORDER):
            raise SemanticV11Error("bound sibling case ordinal drift")
        contract = mapping(json.loads(self._contract_raw), "bound v11 contract")
        cases = sequence(contract.get("cases"), "bound v11 cases")
        semantics = mapping(json.loads(self._semantics_raw), "bound code semantics")
        return BoundContractCase(
            case_id=CASE_ORDER[case_ordinal - 1],
            case_ordinal=case_ordinal,
            contract_sha256=self.contract_sha256,
            contract_raw=self._contract_raw,
            case=mapping(cases[case_ordinal - 1], "bound sibling case"),
            semantics=semantics,
            token=_BOUND_CASE_TOKEN,
        )


def file_sha256(path: Path) -> str:
    try:
        return sha256(path.read_bytes())
    except OSError as exc:
        raise SemanticV11Error("bound file is unavailable") from exc


def sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SemanticV11Error(f"{label} must be an array")
    return list(value)


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticV11Error(f"{label} is unavailable or invalid") from exc
    return mapping(value, label), raw


def materialized_request(
    case: Mapping[str, Any], semantics: Mapping[str, Any]
) -> OracleSemanticRequest:
    return materialized_request_v10(case, semantics)


def score_v11(case: Mapping[str, Any], analysis: Mapping[str, Any]) -> dict[str, Any]:
    return score_v10(case, analysis)


def _validate_static_identity(contract: Mapping[str, Any]) -> None:
    if (
        set(contract) != V11_KEYS
        or contract.get("schema_version") != SCHEMA
        or contract.get("status") != STATUS
        or contract.get("candidate_task_id") != CANDIDATE_TASK_ID
        or contract.get("contract_template") != TEMPLATE_SCHEMA
    ):
        raise SemanticV11Error("v11 contract identity drift")
    proposal = mapping(contract.get("proposal_binding"), "proposal_binding")
    if proposal != {
        "ak_task_id": 4689,
        "completion_kind": "oracle_semantic_v11_contract_proposal",
        "disposition": "v11_candidate_designable",
        "path": str(PROPOSAL_PATH),
        "sha256": PROPOSAL_SHA256,
        "commit": "793d5269a015291be6e87308b0c6feceef4b742a",
        "tree": "dee0e52facac356f3eb9f598c916db60dad3c4b1",
    }:
        raise SemanticV11Error("proposal binding drift")
    if contract.get("schema_bindings") != EXPECTED_SCHEMA_BINDINGS:
        raise SemanticV11Error("closed schema binding drift")
    consumer = mapping(contract.get("consumer_binding"), "consumer_binding")
    if (
        consumer.get("ak_task_id") != 4678
        or consumer.get("commit") != "0f7a3efde290c66a3cf810cb436d3652e21431b3"
        or consumer.get("tree") != "593854ef76baed50b976547505dd07b153b301f0"
        or consumer.get("module_sha256") != CONSUMER_MODULE_HASHES
        or consumer.get("projection_authority")
        != {
            "fixture_only": True,
            "v11_authorized": False,
            "live_execution_authorized": False,
        }
    ):
        raise SemanticV11Error("consumer binding drift")
    producer = mapping(contract.get("producer_binding"), "producer_binding")
    if (
        producer.get("owner") != "tryinget-dspy-lm-auth"
        or producer.get("version") != "0.1.5"
        or producer.get("commit") != "40dd8c0be1bdd48d1b296297c89613931c033239"
        or producer.get("tree") != "5d980c2849685d24166d5f6924f82b9defaf1393"
        or producer.get("lock_sha256")
        != "0d6c79b4b5d70f7a11a879b0bb26dc61dce064fe8dd2ca7e694a9099b43e90e1"
    ):
        raise SemanticV11Error("producer binding drift")
    task = mapping(contract.get("task_binding_template"), "task_binding_template")
    if task != {
        "live_task_placeholder": "<T>",
        "required_completion_kind": "oracle_semantic_v11_live_execution",
        "ledger_namespace": "dspx/oracle-semantic-analysis-evaluations/AK-<T>/v11",
        "ledger_key": "AK-<T>:oracle-semantic-analysis-v11:one-process",
        "artifact_key": "oracle-semantic-analysis-evaluations/AK-<T>/v11/attempt",
        "forbidden_task_ids": [4643],
    }:
        raise SemanticV11Error("task binding template drift")
    route = mapping(contract.get("route"), "route")
    if route != {
        "required_backend_kind": "live",
        "requested_provider": "dspy-lm-auth",
        "requested_model": "codex/gpt-5.6-sol",
        "reasoning_effort": "max",
        "mode": "sync",
        "cache": False,
        "num_retries": 0,
        "stream": True,
        "store": False,
        "executed_provider_requirement": "not_proven",
        "executed_model_requirement": "bounded_provider_reported_not_proof",
        "live_authorized_by_contract": False,
    }:
        raise SemanticV11Error("route policy drift")
    request = mapping(contract.get("request_policy"), "request_policy")
    if set(request.get("required_semantic_keys", [])) != SEMANTIC_KEYS:
        raise SemanticV11Error("semantic request policy drift")
    if set(request.get("optional_unset_only_keys", [])) != OPTIONAL_UNSET_KEYS:
        raise SemanticV11Error("semantic optional-key policy drift")


def load_candidate(
    repo_root: Path, *, check_sources: bool = True
) -> tuple[dict[str, Any], dict[str, Any], str]:
    root = repo_root.expanduser().resolve()
    contract, raw = _read_json(root / CONTRACT_PATH, "v11 contract")
    v10, v10_raw = _read_json(root / V10_PATH, "v10 contract")
    semantics, semantics_raw = _read_json(root / SEMANTICS_PATH, "code semantics")
    _, v9_raw = _read_json(root / V9_PATH, "v9 contract")
    if (
        sha256(v10_raw) != V10_SHA256
        or sha256(v9_raw) != V9_SHA256
        or sha256(semantics_raw) != SEMANTICS_SHA256
        or file_sha256(root / PROPOSAL_PATH) != PROPOSAL_SHA256
    ):
        raise SemanticV11Error("immutable predecessor binding drift")
    _validate_static_identity(contract)
    for key in INHERITED_KEYS:
        if canonical(contract.get(key)) != canonical(v10.get(key)):
            raise SemanticV11Error(f"v10 inherited subtree drift: {key}")
    cases = sequence(contract.get("cases"), "cases")
    if tuple(mapping(case, "case").get("id") for case in cases) != CASE_ORDER:
        raise SemanticV11Error("case order drift")
    if sha256(raw) != CONTRACT_SHA256:
        raise SemanticV11Error("v11 contract bytes drift")
    if check_sources:
        base = root / "packages/dspx-core/src/dspx/services"
        for name, digest in CONSUMER_MODULE_HASHES.items():
            if file_sha256(base / name) != digest:
                raise SemanticV11Error("accepted consumer source drift")
    return contract, semantics, sha256(raw)


def load_bound_cases(
    repo_root: Path, *, check_sources: bool = True
) -> tuple[BoundContractCase, ...]:
    """Load the fixed four cases as non-caller-authorable scoring capabilities."""

    contract, semantics, digest = load_candidate(repo_root, check_sources=check_sources)
    cases = sequence(contract.get("cases"), "cases")
    bound = tuple(
        BoundContractCase(
            case_id=CASE_ORDER[index - 1],
            case_ordinal=index,
            contract_sha256=digest,
            contract_raw=(
                repo_root.expanduser().resolve() / CONTRACT_PATH
            ).read_bytes(),
            case=mapping(value, "case"),
            semantics=semantics,
            token=_BOUND_CASE_TOKEN,
        )
        for index, value in enumerate(cases, start=1)
    )
    if len(bound) != len(CASE_ORDER):
        raise SemanticV11Error("bound contract case cardinality drift")
    return bound
