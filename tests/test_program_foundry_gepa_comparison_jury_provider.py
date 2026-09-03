# summary: "Provider-free tests for foundry-only dspy-lm-auth jury custody."
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import threading
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
import dspy

from dspx.provider_registry import SUPPORTED_PROVIDER_NAMES
from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.provider_contract import (
    EffectDisposition,
    ProviderInvocationError,
    ProviderRequest,
)
from dspx.services.program_foundry_gepa_comparison_jury_owner import (
    FOUNDRY_JURY_OWNER_SOURCE,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider import (
    FoundryJuryJSONAdapter,
    _FoundryJuryFormattingProvider,
    configure_foundry_jury_provider,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
    PROVIDER_NAME,
    FoundryJuryCallCustodian,
    FoundryJuryProviderConfigurationError,
    canonical_ak_task_revalidator,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_evidence import (
    validate_foundry_jury_provider_evidence,
)
from dspx.services.program_model_jury_execution import _run_juror_model
from dspx.services.program_model_jury_provider_runtime import (
    ProgramModelJuryProviderExecutionError,
)
from dspx.services.soomfon_provider_outcome_receipt_contract import EVENT_FIELDS_V2
from dspy.utils.exceptions import AdapterParseError
from dspx.services.soomfon_provider_outcome_receipt_identity import (
    VerifiedOwnerArtifact,
    _ARTIFACT_TOKEN,
    _fixture_owner_artifact,
)


@dataclass(frozen=True, slots=True)
class _Event:
    kind: str
    gate_ordinal: int | None = None
    status_class: int | None = None
    status_code: int | None = None
    error_class: str | None = None
    protocol_event: str | None = None
    response_id_sha256: str | None = None
    observed_model: str | None = None


assert tuple(_Event.__dataclass_fields__) == EVENT_FIELDS_V2


@dataclass(slots=True)
class _Receipt:
    logical_request_id: str
    semantic_request_sha256: str
    sink: Any
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _used: bool = False


class _Owner:
    def __init__(self, artifact: VerifiedOwnerArtifact) -> None:
        self.artifact = artifact

    def revalidate(self) -> None:
        self.artifact.revalidate()


def _artifact(*, accepted: bool = True) -> VerifiedOwnerArtifact:
    expected = FOUNDRY_JURY_OWNER_SOURCE
    fixture = _fixture_owner_artifact(
        source_identity={
            "owner": "tryinget-dspy-lm-auth",
            "version": expected.version,
            "commit": expected.commit,
            "tree": expected.tree,
            "lock_sha256": expected.lock_sha256,
            "module_sha256": {
                name: digest for name, (_, digest) in expected.modules.items()
            },
        },
        dependency_identity={
            name: {
                "version": item.version,
                "locked_wheel_sha256": item.wheel_sha256,
                "payload_count": item.payload_count,
                "payload_sha256": item.payload_sha256,
                "record_sha256": item.record_sha256,
            }
            for name, item in expected.dependencies.items()
        },
        event_type=_Event,
        receipt_type=_Receipt,
    )
    if not accepted:
        return fixture
    return VerifiedOwnerArtifact(
        source_identity=fixture.source_identity,
        dependency_identity=fixture.dependency_identity,
        event_type=_Event,
        receipt_type=_Receipt,
        revalidator=lambda: None,
        accepted=True,
        token=_ARTIFACT_TOKEN,
    )


def _completed(receipt: object) -> list[dict[str, str]]:
    typed_receipt = cast(_Receipt, receipt)
    response_hash = "b" * 64
    for event in (
        _Event(kind="wrapper_request_accepted"),
        _Event(kind="transport_gate_entered", gate_ordinal=1),
        _Event(kind="transport_effect_pending", gate_ordinal=1),
        _Event(kind="transport_entered", gate_ordinal=1),
        _Event(
            kind="http_response_observed",
            gate_ordinal=1,
            status_class=2,
            status_code=200,
        ),
        _Event(
            kind="parsed_protocol_event_observed",
            protocol_event="response.completed",
            response_id_sha256=response_hash,
        ),
        _Event(
            kind="provider_response_completed",
            status_class=2,
            status_code=200,
            response_id_sha256=response_hash,
            observed_model="gpt-5.6-luna",
        ),
    ):
        typed_receipt.sink(event)
    return [{"judgment_json": "{}"}]


def _custodian(tmp_path: Path) -> FoundryJuryCallCustodian:
    return FoundryJuryCallCustodian(
        journal_parent=tmp_path / "provider-outcomes",
        owner=_Owner(_artifact()),  # type: ignore[arg-type]
        execution_task_id=6000,
        contract_sha256="a" * 64,
        expected_juror_ids=("quality", "authority"),
        requested_route="dspy-lm-auth:codex:gpt-5.6-luna",
        resolved_route="openai:gpt-5.6-luna:responses",
        authority_revalidator=lambda: None,
    )


def test_foundry_provider_is_not_restored_in_generic_registry() -> None:
    assert PROVIDER_NAME not in SUPPORTED_PROVIDER_NAMES


def test_custodian_records_one_closed_receipt_per_juror_and_revalidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custodian = _custodian(tmp_path)
    assert custodian.invoke(
        juror_id="quality",
        semantic_request_sha256="c" * 64,
        invoke=_completed,
    ) == [{"judgment_json": "{}"}]
    custodian.invoke(
        juror_id="authority",
        semantic_request_sha256="d" * 64,
        invoke=_completed,
    )
    evidence = custodian.finalize()

    assert evidence["logical_call_total"] == 2
    assert evidence["maximum_provider_transports"] == 2
    assert evidence["session_disposition"] == "complete"
    assert evidence["stopped_after_call"] is None
    assert evidence["stop_reason"] is None
    assert [record["juror_id"] for record in evidence["call_records"]] == [
        "quality",
        "authority",
    ]
    assert all(
        record["producer_terminal"] == "provider_response_completed"
        for record in evidence["call_records"]
    )
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_provider_evidence.verify_foundry_jury_owner_source",
        lambda path: _artifact().source_identity,
    )
    validated = validate_foundry_jury_provider_evidence(
        evidence,
        journal_parent=tmp_path / "provider-outcomes",
        owner_source_root=tmp_path / "owner",
        execution_task_id=6000,
        contract_sha256="a" * 64,
        expected_juror_ids=("quality", "authority"),
        expected_model="gpt-5.6-luna",
    )
    assert validated == evidence


def test_custodian_latches_indeterminate_open_effect_and_forbids_replay(
    tmp_path: Path,
) -> None:
    custodian = _custodian(tmp_path)

    def incomplete(receipt: object) -> None:
        typed_receipt = cast(_Receipt, receipt)
        typed_receipt.sink(_Event(kind="wrapper_request_accepted"))
        typed_receipt.sink(_Event(kind="transport_gate_entered", gate_ordinal=1))
        typed_receipt.sink(_Event(kind="transport_effect_pending", gate_ordinal=1))
        raise RuntimeError("transport outcome unknown")

    with pytest.raises(ProgramModelJuryProviderExecutionError) as first:
        custodian.invoke(
            juror_id="quality",
            semantic_request_sha256="c" * 64,
            invoke=incomplete,
        )
    assert first.value.effect_indeterminate is True

    with pytest.raises(ProgramModelJuryProviderExecutionError) as replay:
        custodian.invoke(
            juror_id="quality",
            semantic_request_sha256="c" * 64,
            invoke=_completed,
        )
    assert replay.value.effect_indeterminate is False
    assert replay.value.reason == "provider_session_terminal"


def test_custodian_rejects_out_of_order_juror_before_receipt_creation(
    tmp_path: Path,
) -> None:
    custodian = _custodian(tmp_path)
    with pytest.raises(ProgramModelJuryProviderExecutionError) as exc:
        custodian.invoke(
            juror_id="authority",
            semantic_request_sha256="c" * 64,
            invoke=_completed,
        )
    assert exc.value.effect_indeterminate is False
    assert not list((tmp_path / "provider-outcomes").iterdir())


def test_closed_completed_prefix_can_finalize_without_false_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custodian = _custodian(tmp_path)
    custodian.invoke(
        juror_id="quality",
        semantic_request_sha256="c" * 64,
        invoke=_completed,
    )
    custodian.latch_closed_after_completed_call()

    evidence = custodian.finalize()
    assert evidence["logical_call_total"] == 1
    assert evidence["maximum_logical_calls"] == 2
    assert evidence["session_disposition"] == "closed_terminal"
    assert evidence["stopped_after_call"] == 1
    assert evidence["stop_reason"] == (
        "local_postprocessing_failed_after_closed_receipt"
    )
    assert evidence["call_records"][0]["producer_terminal"] == (
        "provider_response_completed"
    )
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_provider_evidence.verify_foundry_jury_owner_source",
        lambda path: _artifact().source_identity,
    )
    validated = validate_foundry_jury_provider_evidence(
        evidence,
        journal_parent=tmp_path / "provider-outcomes",
        owner_source_root=tmp_path / "owner",
        execution_task_id=6000,
        contract_sha256="a" * 64,
        expected_juror_ids=("quality", "authority"),
        expected_model="gpt-5.6-luna",
    )
    assert validated == evidence


def test_retained_validation_rejects_semantic_request_record_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custodian = _custodian(tmp_path)
    custodian.invoke(
        juror_id="quality",
        semantic_request_sha256="c" * 64,
        invoke=_completed,
    )
    custodian.invoke(
        juror_id="authority",
        semantic_request_sha256="d" * 64,
        invoke=_completed,
    )
    evidence = copy.deepcopy(custodian.finalize())
    evidence["call_records"][0]["semantic_request_sha256"] = "e" * 64
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_provider_evidence.verify_foundry_jury_owner_source",
        lambda path: _artifact().source_identity,
    )

    with pytest.raises(
        FoundryJuryProviderConfigurationError,
        match="journal binding drifted",
    ):
        validate_foundry_jury_provider_evidence(
            evidence,
            journal_parent=tmp_path / "provider-outcomes",
            owner_source_root=tmp_path / "owner",
            execution_task_id=6000,
            contract_sha256="a" * 64,
            expected_juror_ids=("quality", "authority"),
            expected_model="gpt-5.6-luna",
        )


def test_implementation_task_is_rejected_as_live_call_authority(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        FoundryJuryProviderConfigurationError,
        match="authority parameters are invalid",
    ):
        canonical_ak_task_revalidator(
            execution_task_id=5308,
            execution_claimant="pi:implementation",
            repo_root=tmp_path,
            minimum_lease_seconds=90,
        )


@dataclass(frozen=True, slots=True)
class _BackendMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class _BackendRequest:
    model: str
    messages: tuple[_BackendMessage, ...]
    reasoning_effort: str
    response_format: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class _BackendResponse:
    output_text: str
    semantic_request_sha256: str


class _Backend:
    def __init__(self, output_text: str, *, response_hash: str | None = None) -> None:
        self.output_text = output_text
        self.response_hash = response_hash
        self.requests: list[_BackendRequest] = []
        self.semantic_hashes: list[str] = []

    def prepare(self, request: _BackendRequest):
        self.requests.append(request)
        semantic_hash = hashlib.sha256(
            b"dspy-lm-auth-backend-test-v1\0"
            + json.dumps(
                asdict(request), separators=(",", ":"), sort_keys=True
            ).encode()
        ).hexdigest()
        self.semantic_hashes.append(semantic_hash)
        return type(
            "Prepared",
            (),
            {"semantic_request_sha256": semantic_hash},
        )()

    def invoke(self, prepared: object, *, outcome_receipt: object) -> _BackendResponse:
        del outcome_receipt
        semantic_hash = getattr(prepared, "semantic_request_sha256")
        return _BackendResponse(
            self.output_text,
            self.response_hash or semantic_hash,
        )


class _AdapterOwner:
    def __init__(self) -> None:
        self.message_type = _BackendMessage
        self.request_type = _BackendRequest
        self.response_type = _BackendResponse

    def revalidate(self) -> None:
        return None


class _AdapterCustodian:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def invoke(self, *, juror_id: str, semantic_request_sha256: str, invoke):
        self.calls.append((juror_id, semantic_request_sha256))
        return invoke(object())

    def latch_closed_after_completed_call(self) -> None:
        raise AssertionError("successful adapter path must not latch closed")


def test_effect_capable_provider_constructor_has_no_authority_injection() -> None:
    parameters = inspect.signature(configure_foundry_jury_provider).parameters
    assert "authority_revalidator" not in parameters


def test_fixed_backend_runs_through_dspx_adapter_without_external_lm() -> None:
    judgment = {
        "outcome": "supports_review_evidence",
        "rationale": "bounded fixture",
        "evidence_strengths": ["receipt"],
        "concerns": [],
        "improvement_requests": [],
        "confidence": "high",
    }
    backend = _Backend(json.dumps({"judgment_json": json.dumps(judgment)}))
    owner = _AdapterOwner()
    custodian = _AdapterCustodian()
    provider = _FoundryJuryFormattingProvider("gpt-5.6-luna")
    lm = DSPyTypedLMAdapter(provider, cache=False, callbacks=[])
    adapter = FoundryJuryJSONAdapter(
        owner=owner,  # type: ignore[arg-type]
        lm=lm,
        backend=backend,
        custodian=custodian,  # type: ignore[arg-type]
        model="gpt-5.6-luna",
        reasoning_effort="xhigh",
        timeout_seconds=60.0,
    )
    previous_lm = getattr(dspy.settings, "lm", None)
    previous_adapter = getattr(dspy.settings, "adapter", None)
    try:
        dspy.configure(lm=lm, adapter=adapter)
        result = _run_juror_model(
            juror={"id": "quality", "perspective": "quality"},
            rubric={"criteria": ["bounded"]},
            candidate_identity={"sha256": "a" * 64},
            evidence_json='{"bounded":true}',
            adjudicator={"kind": "deterministic"},
        )
    finally:
        dspy.configure(lm=previous_lm, adapter=previous_adapter)

    assert result["outcome"] == "supports_review_evidence"
    assert type(lm) is DSPyTypedLMAdapter
    assert backend.requests[0].model == "gpt-5.6-luna"
    assert backend.requests[0].response_format == "text"
    assert custodian.calls == [("quality", backend.semantic_hashes[0])]
    json_object_hash = backend.prepare(
        replace(backend.requests[0], response_format="json_object")
    ).semantic_request_sha256
    assert json_object_hash != backend.semantic_hashes[0]
    with pytest.raises(ProviderInvocationError) as caught:
        provider.invoke(ProviderRequest(model=provider.model, messages=()))
    assert caught.value.disposition is EffectDisposition.PREFLIGHT_REJECTED


class _LatchingAdapterCustodian(_AdapterCustodian):
    def __init__(self) -> None:
        super().__init__()
        self.latched = 0

    def latch_closed_after_completed_call(self) -> None:
        self.latched += 1


def _judgment_fixture() -> dict[str, object]:
    return {
        "outcome": "supports_review_evidence",
        "rationale": "bounded fixture",
        "evidence_strengths": ["receipt"],
        "concerns": [],
        "improvement_requests": [],
        "confidence": "high",
    }


def _adapter_for(backend: _Backend, custodian: _AdapterCustodian):
    provider = _FoundryJuryFormattingProvider("gpt-5.6-luna")
    lm = DSPyTypedLMAdapter(provider, cache=False, callbacks=[])
    adapter = FoundryJuryJSONAdapter(
        owner=_AdapterOwner(),  # type: ignore[arg-type]
        lm=lm,
        backend=backend,
        custodian=custodian,  # type: ignore[arg-type]
        model="gpt-5.6-luna",
        reasoning_effort="xhigh",
        timeout_seconds=60.0,
    )
    return lm, adapter


def _run_quality_juror() -> dict[str, Any]:
    return _run_juror_model(
        juror={"id": "quality", "perspective": "quality"},
        rubric={"criteria": ["bounded"]},
        candidate_identity={"sha256": "a" * 64},
        evidence_json='{"bounded":true}',
        adjudicator={"kind": "deterministic"},
    )


@pytest.mark.parametrize(
    "output_text",
    [
        json.dumps(_judgment_fixture()),
        json.dumps({"judgment_json": json.dumps(_judgment_fixture())}),
        json.dumps({"judgment_json": _judgment_fixture()}),
        "```json\n" + json.dumps(_judgment_fixture()) + "\n```",
    ],
)
def test_adapter_accepts_bare_and_wrapped_closed_judgment_shapes(
    output_text: str,
) -> None:
    backend = _Backend(output_text)
    custodian = _AdapterCustodian()
    lm, adapter = _adapter_for(backend, custodian)
    previous_lm = getattr(dspy.settings, "lm", None)
    previous_adapter = getattr(dspy.settings, "adapter", None)
    try:
        dspy.configure(lm=lm, adapter=adapter)
        result = _run_quality_juror()
    finally:
        dspy.configure(lm=previous_lm, adapter=previous_adapter)
    assert result == _judgment_fixture()
    assert len(backend.requests) == 1
    assert custodian.calls == [("quality", backend.semantic_hashes[0])]


@pytest.mark.parametrize(
    "output_text",
    [
        json.dumps({**_judgment_fixture(), "extra": "widening"}),
        json.dumps({"outcome": "withhold"}),
        json.dumps([_judgment_fixture()]),
        json.dumps("supports_review_evidence"),
    ],
)
def test_adapter_rejects_non_contract_shapes_then_latches_terminal(
    output_text: str,
) -> None:
    backend = _Backend(output_text)
    custodian = _LatchingAdapterCustodian()
    lm, adapter = _adapter_for(backend, custodian)
    previous_lm = getattr(dspy.settings, "lm", None)
    previous_adapter = getattr(dspy.settings, "adapter", None)
    try:
        dspy.configure(lm=lm, adapter=adapter)
        with pytest.raises(AdapterParseError):
            _run_quality_juror()
        assert len(backend.requests) == 1
        assert custodian.latched == 1
        # The completed-but-unparseable call latches the session closed: later
        # jurors fail before any provider call with a truthful reason.
        with pytest.raises(ProgramModelJuryProviderExecutionError) as caught:
            _run_quality_juror()
    finally:
        dspy.configure(lm=previous_lm, adapter=previous_adapter)
    assert caught.value.reason == "adapter_session_terminal"
    assert caught.value.effect_indeterminate is False
    assert len(backend.requests) == 1
    assert len(custodian.calls) == 1


def test_adapter_reports_lm_identity_drift_distinct_from_terminal_latch() -> None:
    backend = _Backend(json.dumps(_judgment_fixture()))
    lm, adapter = _adapter_for(backend, _AdapterCustodian())
    other_lm = DSPyTypedLMAdapter(
        _FoundryJuryFormattingProvider("gpt-5.6-luna"), cache=False, callbacks=[]
    )
    with pytest.raises(ProgramModelJuryProviderExecutionError) as caught:
        adapter(other_lm, {}, object, [], {"juror_json": "{}"})
    assert caught.value.reason == "adapter_lm_identity_drift"
    assert backend.requests == []
    del lm


def test_fixed_backend_rejects_response_semantic_hash_drift() -> None:
    judgment = {
        "outcome": "supports_review_evidence",
        "rationale": "bounded fixture",
        "evidence_strengths": [],
        "concerns": [],
        "improvement_requests": [],
        "confidence": "high",
    }
    backend = _Backend(
        json.dumps({"judgment_json": json.dumps(judgment)}),
        response_hash="f" * 64,
    )
    owner = _AdapterOwner()
    provider = _FoundryJuryFormattingProvider("gpt-5.6-sol")
    lm = DSPyTypedLMAdapter(provider, cache=False, callbacks=[])
    adapter = FoundryJuryJSONAdapter(
        owner=owner,  # type: ignore[arg-type]
        lm=lm,
        backend=backend,
        custodian=_AdapterCustodian(),  # type: ignore[arg-type]
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        timeout_seconds=60.0,
    )
    previous_lm = getattr(dspy.settings, "lm", None)
    previous_adapter = getattr(dspy.settings, "adapter", None)
    try:
        dspy.configure(lm=lm, adapter=adapter)
        with pytest.raises(ProgramModelJuryProviderExecutionError) as caught:
            _run_juror_model(
                juror={"id": "quality", "perspective": "quality"},
                rubric={"criteria": ["bounded"]},
                candidate_identity={"sha256": "a" * 64},
                evidence_json='{"bounded":true}',
                adjudicator={"kind": "deterministic"},
            )
    finally:
        dspy.configure(lm=previous_lm, adapter=previous_adapter)
    assert caught.value.reason == "owner_backend_response_shape_drift"
    assert caught.value.effect_indeterminate is False


def test_canonical_task_revalidator_binds_exact_claimant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = {
        "id": 6000,
        "title": "Execute one receipt-bound foundry comparison jury with dspy-lm-auth Codex",
        "repo": str(tmp_path.resolve()),
        "status": "claimed",
        "claimed_by": "pi:expected",
        "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        "completed_at": None,
        "result": None,
    }
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_provider_custody.run_ak_task_show",
        lambda task_id: dict(task),
    )
    revalidate = canonical_ak_task_revalidator(
        execution_task_id=6000,
        execution_claimant="pi:expected",
        repo_root=tmp_path,
        minimum_lease_seconds=90,
    )
    revalidate()

    task["claimed_by"] = "pi:someone-else"
    with pytest.raises(
        FoundryJuryProviderConfigurationError,
        match="authority is not active",
    ):
        revalidate()
