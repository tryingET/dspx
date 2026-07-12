# summary: "Defines bounded request, analysis, result, and preflight contracts for program Oracle semantics."
# read_when:
#   - "Changing program Oracle semantic schemas, evidence identity, or advisory authority labels."

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from dspx.services.program_oracle_secret_policy import (
    ProgramOracleSecretPolicyError,
    validate_publisher_assertion_no_secret,
)

ORACLE_SEMANTIC_REQUEST_SCHEMA = "dspx-program-oracle-semantic-request-v1"
ORACLE_SEMANTIC_RESULT_SCHEMA = "dspx-program-oracle-semantic-result-v1"
ORACLE_SEMANTIC_PREFLIGHT_SCHEMA = "dspx-program-oracle-semantic-preflight-v1"
ORACLE_SEMANTIC_FIXTURE_SCHEMA = "dspx-program-oracle-semantic-fixture-v1"
REQUIRED_ANALYSIS_FIELDS = (
    "observations",
    "failure_attractors",
    "quality_contract_violations",
    "hypotheses",
    "recommended_experiments",
    "evidence_refs",
)
MAX_REQUEST_BYTES = 200_000


class ProgramOracleSemanticBackendError(ValueError):
    """Raised when semantic configuration, evidence, or output fails closed."""


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProgramOracleSemanticBackendError(
            f"Oracle semantic value must be canonical JSON: {exc}"
        ) from exc


def _bounded_text(value: object, *, field: str, maximum: int = 20_000) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProgramOracleSemanticBackendError(f"{field} must not be empty")
    if len(text.encode("utf-8")) > maximum:
        raise ProgramOracleSemanticBackendError(
            f"{field} exceeds the {maximum}-byte safety bound"
        )
    try:
        validate_publisher_assertion_no_secret(text)
    except ProgramOracleSecretPolicyError as exc:
        raise ProgramOracleSemanticBackendError(
            f"{field} contains secret-shaped material: {exc}"
        ) from exc
    return text


def _validate_payload_no_obvious_secrets(value: object, *, field: str) -> None:
    rendered = canonical_json(value)
    try:
        validate_publisher_assertion_no_secret(rendered)
    except ProgramOracleSecretPolicyError as exc:
        raise ProgramOracleSemanticBackendError(
            f"{field} contains secret-shaped material: {exc}"
        ) from exc


@dataclass(frozen=True)
class OracleSemanticRequest:
    """Receipt-bound evidence submitted for non-authoritative semantic analysis."""

    objective: str
    evidence: Mapping[str, Any]
    quality_contract: Mapping[str, Any] | None = None
    _payload_json: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        objective = _bounded_text(self.objective, field="objective")
        # Canonical JSON round-tripping snapshots nested caller-owned values so
        # later mutations cannot change validated evidence or its request hash.
        evidence = json.loads(canonical_json(dict(self.evidence)))
        quality_contract = (
            json.loads(canonical_json(dict(self.quality_contract)))
            if self.quality_contract is not None
            else None
        )
        _validate_payload_no_obvious_secrets(evidence, field="evidence")
        if quality_contract is not None:
            _validate_payload_no_obvious_secrets(
                quality_contract, field="quality_contract"
            )
        payload = {
            "schema_version": ORACLE_SEMANTIC_REQUEST_SCHEMA,
            "objective": objective,
            "evidence": evidence,
            "quality_contract": quality_contract,
        }
        payload_json = canonical_json(payload)
        if len(payload_json.encode("utf-8")) > MAX_REQUEST_BYTES:
            raise ProgramOracleSemanticBackendError(
                f"Oracle semantic request exceeds the {MAX_REQUEST_BYTES}-byte safety bound"
            )
        object.__setattr__(self, "objective", objective)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "quality_contract", quality_contract)
        object.__setattr__(self, "_payload_json", payload_json)

    def payload(self) -> dict[str, Any]:
        payload = json.loads(self._payload_json)
        if not isinstance(payload, dict):  # pragma: no cover - internal invariant
            raise ProgramOracleSemanticBackendError("invalid frozen request payload")
        return payload

    @property
    def request_sha256(self) -> str:
        return hashlib.sha256(self._payload_json.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OracleSemanticAnalysis:
    observations: tuple[str, ...]
    failure_attractors: tuple[str, ...]
    quality_contract_violations: tuple[str, ...]
    hypotheses: tuple[str, ...]
    recommended_experiments: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    confidence: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> OracleSemanticAnalysis:
        unknown = sorted(set(value) - {*REQUIRED_ANALYSIS_FIELDS, "confidence"})
        if unknown:
            raise ProgramOracleSemanticBackendError(
                "Oracle semantic analysis contains unknown fields: "
                + ", ".join(unknown)
            )

        def string_tuple(field: str) -> tuple[str, ...]:
            raw = value.get(field)
            if not isinstance(raw, list):
                raise ProgramOracleSemanticBackendError(
                    f"analysis.{field} must be a JSON array"
                )
            return tuple(
                _bounded_text(
                    item,
                    field=f"analysis.{field}[{index}]",
                    maximum=4_000,
                )
                for index, item in enumerate(raw)
            )

        raw_confidence = value.get("confidence")
        if isinstance(raw_confidence, bool) or not isinstance(
            raw_confidence, (int, float)
        ):
            raise ProgramOracleSemanticBackendError(
                "analysis.confidence must be a number from 0 through 1"
            )
        confidence = float(raw_confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ProgramOracleSemanticBackendError(
                "analysis.confidence must be a number from 0 through 1"
            )
        return cls(
            observations=string_tuple("observations"),
            failure_attractors=string_tuple("failure_attractors"),
            quality_contract_violations=string_tuple("quality_contract_violations"),
            hypotheses=string_tuple("hypotheses"),
            recommended_experiments=string_tuple("recommended_experiments"),
            evidence_refs=string_tuple("evidence_refs"),
            confidence=confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observations": list(self.observations),
            "failure_attractors": list(self.failure_attractors),
            "quality_contract_violations": list(self.quality_contract_violations),
            "hypotheses": list(self.hypotheses),
            "recommended_experiments": list(self.recommended_experiments),
            "evidence_refs": list(self.evidence_refs),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class OracleSemanticResult:
    request_sha256: str
    backend_kind: str
    preferred_model: str
    configured_provider: str | None
    configured_model: str | None
    executed_provider: str | None
    executed_model: str | None
    execution_status: str
    live_call_succeeded: bool
    analysis: OracleSemanticAnalysis | None = None
    fixture_sha256: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ORACLE_SEMANTIC_RESULT_SCHEMA,
            "authority": "local_empirical_advisory_only",
            "request_sha256": self.request_sha256,
            "backend_kind": self.backend_kind,
            "preferred_model": self.preferred_model,
            "configured_provider": self.configured_provider,
            "configured_model": self.configured_model,
            "executed_provider": self.executed_provider,
            "executed_model": self.executed_model,
            "execution_status": self.execution_status,
            "live_call_succeeded": self.live_call_succeeded,
            "fixture_sha256": self.fixture_sha256,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class OracleSemanticPreflight:
    ready: bool
    backend_kind: str
    preferred_model: str
    configured_provider: str | None
    configured_model: str | None
    fixture_path: str | None
    checks: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ORACLE_SEMANTIC_PREFLIGHT_SCHEMA,
            "status": "ready" if self.ready else "not_ready",
            "ready": self.ready,
            "backend_kind": self.backend_kind,
            "preferred_model": self.preferred_model,
            "configured_provider": self.configured_provider,
            "configured_model": self.configured_model,
            "executed_provider": None,
            "executed_model": None,
            "live_verified": False,
            "fixture_path": self.fixture_path,
            "checks": list(self.checks),
            "authority": "configuration_preflight_only",
        }


class ProgramOracleSemanticBackend(Protocol):
    def analyze(self, request: OracleSemanticRequest) -> OracleSemanticResult: ...
