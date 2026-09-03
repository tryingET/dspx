# summary: "Credential-free tests for the xAI foundry jury provider family."
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import dspy
import pytest
from dspy import BaseLM
from typer.testing import CliRunner

import dspx.services.program_foundry_gepa_comparison_jury as comparison_jury
import dspx.services.program_foundry_gepa_comparison_jury_receipt_validation as receipt_validation
import dspx.services.program_foundry_gepa_comparison_jury_provider as provider_module
import dspx.services.program_model_jury_provider_runtime as jury_runtime
from dspx.cli.dspx import app
from dspx.provider_registry import SUPPORTED_PROVIDER_NAMES
from dspx.services.program_foundry_gepa_comparison_jury_owner import (
    _EXTRA_OWNER_FILES,
    OWNER_COMMIT,
    VerifiedFoundryJuryOwner,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider import (
    configure_foundry_jury_provider,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
    CODEX_FAMILY,
    COPILOT_FAMILY,
    TASK_LOCAL_PROVIDER_NAMES,
    FoundryJuryCallCustodian,
    FoundryJuryProviderConfigurationError,
    FoundryJuryProviderFamily,
    canonical_ak_task_revalidator,
    endpoint_origin_sha256,
    family_for_provider,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_evidence import (
    validate_foundry_jury_provider_evidence,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (
    FAMILIES,
    LOCAL_VLLM_FAMILY,
    XAI_FAMILY,
    family_for_request,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_metadata import (
    provider_metadata,
    validate_foundry_jury_provider_metadata,
)
from dspx.services.program_foundry_gepa_comparison_jury_runtime import (
    execution_request,
    revalidate_execution_request,
    task_local_execution_request_keys,
    task_local_family,
)
from dspx.services.program_model_jury_execution import _run_juror_model
from dspx.services.program_model_jury_provider_runtime import (
    _bind_program_model_jury_provider_runtime,
    run_program_model_jurors,
)
from dspx.services.soomfon_provider_outcome_receipt_contract import (
    ProviderOutcomeConsumerError,
)
from foundry_jury_owner_repin import (
    REQUIRED_EXTRA_OWNER_FILES,
    missing_required_extra_files,
)
from test_program_foundry_gepa_comparison_jury import (
    _fixture,
    _model_result,
    _sha256,
)
from test_program_foundry_gepa_comparison_jury_copilot import _completed_with
from test_program_foundry_gepa_comparison_jury_provider import _Owner, _artifact

ALL_FAMILIES = (CODEX_FAMILY, COPILOT_FAMILY, XAI_FAMILY, LOCAL_VLLM_FAMILY)
XAI_MODEL = "grok-4.6"
XAI_ENDPOINT_ORIGIN_SHA256 = (
    "b1cca9c83dc27a51b9887f2a66a651bea19f23ac4d86dccc456fab2141f5e40d"
)
JUDGMENT = {
    "outcome": "supports_review_evidence",
    "rationale": "bounded fixture",
    "evidence_strengths": ["receipt"],
    "concerns": [],
    "improvement_requests": [],
    "confidence": "high",
}


@pytest.fixture(autouse=True)
def _in_process_jury(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run task-local juries in this process so patched fakes stay reachable."""

    monkeypatch.setattr(comparison_jury, "_CHILD_ARGV", None)


def _other(family: FoundryJuryProviderFamily) -> FoundryJuryProviderFamily:
    index = ALL_FAMILIES.index(family)
    return ALL_FAMILIES[(index + 1) % len(ALL_FAMILIES)]


def test_xai_family_literals_are_pinned() -> None:
    assert XAI_FAMILY.provider_name == "foundry-dspy-lm-auth-xai"
    assert XAI_FAMILY.auth_provider == "xai"
    assert XAI_FAMILY.default_model == XAI_MODEL
    assert XAI_FAMILY.allowed_reasoning_efforts is None
    assert XAI_FAMILY.default_reasoning_effort is None
    assert XAI_FAMILY.execution_task_title == (
        "Execute one receipt-bound foundry comparison jury with dspy-lm-auth xAI"
    )
    assert XAI_FAMILY.endpoint_origin == "https://api.x.ai"
    assert XAI_FAMILY.requested_route(XAI_MODEL) == "dspy-lm-auth:xai:grok-4.6"
    assert XAI_FAMILY.resolved_route(XAI_MODEL) == "openai:grok-4.6:chat"
    assert XAI_FAMILY.backend_module == "dspy_lm_auth.xai_backend"
    assert XAI_FAMILY.backend_class == "XaiBackend"
    assert XAI_FAMILY.contract_module == "dspy_lm_auth.chat_backend_contract"
    assert (
        XAI_FAMILY.message_class,
        XAI_FAMILY.request_class,
        XAI_FAMILY.response_class,
    ) == ("ChatBackendMessage", "ChatBackendRequest", "ChatBackendResponse")
    assert XAI_FAMILY.allowed_roles == frozenset({"system", "user", "assistant"})
    assert XAI_FAMILY.model_key == "model"
    assert XAI_FAMILY.strict_observed_model is False
    assert XAI_FAMILY.endpoint_env is None
    assert XAI_FAMILY.endpoint_key is None
    assert XAI_FAMILY.endpoint_resolved is False
    assert XAI_FAMILY.default_timeout_seconds == 180.0
    assert family_for_provider(XAI_FAMILY.provider_name) is XAI_FAMILY
    assert FAMILIES[XAI_FAMILY.provider_name] is XAI_FAMILY
    assert XAI_FAMILY.provider_name in TASK_LOCAL_PROVIDER_NAMES
    assert len(TASK_LOCAL_PROVIDER_NAMES) == 4
    assert XAI_FAMILY.provider_name not in SUPPORTED_PROVIDER_NAMES
    assert task_local_execution_request_keys(XAI_FAMILY.provider_name) == frozenset(
        {
            "provider",
            "adjudicator_id",
            "adjudicator_kind",
            "adjudicator_repo",
            "max_jurors",
            "owner_source_root",
            "execution_task_id",
            "execution_claimant",
            "model",
        }
    )


def test_xai_endpoint_origin_constant_uses_the_v11_rule() -> None:
    canonical = json.dumps(
        {"scheme": "https", "hostname": "api.x.ai"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected = hashlib.sha256(
        b"dspx-oracle-semantic-v11-endpoint-origin-v1\0" + canonical
    ).hexdigest()
    assert XAI_FAMILY.endpoint_origin_sha256 == XAI_ENDPOINT_ORIGIN_SHA256 == expected
    assert endpoint_origin_sha256("https://api.x.ai/v1") == expected
    assert endpoint_origin_sha256(XAI_FAMILY.endpoint_origin) == expected
    assert len({family.endpoint_origin_sha256 for family in ALL_FAMILIES}) == 4


@pytest.mark.parametrize(
    "model",
    ["grok-4.6", "grok-4", "grok-4.6-fast", "grok-3-mini-beta", "grok-" + "a" * 64],
)
def test_xai_model_rule_accepts_lowercase_grok_ids(model: str) -> None:
    assert XAI_FAMILY.model_allowed(model)
    assert COPILOT_FAMILY.model_allowed(model)


@pytest.mark.parametrize(
    "model",
    [
        "Grok-4.6",
        "grok-",
        "grok-4.6 ",
        "gemini-3.7-flash",
        "gpt-5.4",
        "local/Qwen3.8-27B-AEON-NVFP4-FP8",
        "grok-4_6",
        "grok-" + "a" * 65,
        "",
        None,
        4.6,
    ],
)
def test_xai_model_rule_rejects_other_ids(model: object) -> None:
    assert not XAI_FAMILY.model_allowed(model)


def test_xai_reasoning_effort_is_not_applicable() -> None:
    assert XAI_FAMILY.reasoning_effort_allowed(None)
    assert not XAI_FAMILY.reasoning_effort_allowed("xhigh")
    assert XAI_FAMILY.resolve_reasoning_effort(None) is None
    assert XAI_FAMILY.resolve_model(None) == XAI_MODEL
    assert XAI_FAMILY.resolve_model("grok-4") == "grok-4"


def test_xai_endpoint_is_fixed() -> None:
    assert XAI_FAMILY.with_endpoint(None) is XAI_FAMILY
    with pytest.raises(ValueError, match="endpoint is fixed"):
        XAI_FAMILY.with_endpoint("https://api.x.ai")
    assert family_for_request({"provider": XAI_FAMILY.provider_name}) is XAI_FAMILY


@pytest.mark.parametrize("family", ALL_FAMILIES, ids=lambda item: item.auth_provider)
def test_canonical_task_revalidator_binds_each_family_title(
    family: FoundryJuryProviderFamily, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = {
        "id": 6000,
        "title": family.execution_task_title,
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
        family=family,
    )
    revalidate()
    task["title"] = _other(family).execution_task_title
    with pytest.raises(
        FoundryJuryProviderConfigurationError, match="authority is not active"
    ):
        revalidate()


def _custodian(
    tmp_path: Path,
    family: FoundryJuryProviderFamily,
    model: str,
    owner: Any = None,
    juror_ids: tuple[str, ...] = ("quality", "authority"),
) -> FoundryJuryCallCustodian:
    return FoundryJuryCallCustodian(
        journal_parent=tmp_path / "provider-outcomes",
        owner=owner if owner is not None else _Owner(_artifact()),
        execution_task_id=6000,
        contract_sha256="a" * 64,
        expected_juror_ids=juror_ids,
        requested_route=family.requested_route(model),
        resolved_route=family.resolved_route(model),
        authority_revalidator=lambda: None,
        family=family,
    )


def _validate(
    evidence: dict[str, Any],
    tmp_path: Path,
    family: FoundryJuryProviderFamily,
    model: str,
    juror_ids: tuple[str, ...] = ("quality", "authority"),
) -> dict[str, Any]:
    return validate_foundry_jury_provider_evidence(
        evidence,
        journal_parent=tmp_path / "provider-outcomes",
        owner_source_root=tmp_path / "owner",
        execution_task_id=6000,
        contract_sha256="a" * 64,
        expected_juror_ids=juror_ids,
        expected_model=model,
        family=family,
    )


def _stub_owner_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_provider_evidence.verify_foundry_jury_owner_source",
        lambda path: _artifact().source_identity,
    )


def test_xai_custodian_binds_routes_and_origin_into_journals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custodian = _custodian(tmp_path, XAI_FAMILY, XAI_MODEL)
    for juror_id, semantic in (("quality", "c" * 64), ("authority", "d" * 64)):
        custodian.invoke(
            juror_id=juror_id,
            semantic_request_sha256=semantic,
            invoke=_completed_with("grok-4.6-0901"),
        )
    evidence = custodian.finalize()
    assert evidence["session_disposition"] == "complete"
    assert [item["observed_model"] for item in evidence["call_records"]] == [
        "grok-4.6-0901",
        "grok-4.6-0901",
    ]
    _stub_owner_source(monkeypatch)
    assert _validate(evidence, tmp_path, XAI_FAMILY, XAI_MODEL) == evidence
    for other in (CODEX_FAMILY, COPILOT_FAMILY, LOCAL_VLLM_FAMILY):
        with pytest.raises(
            FoundryJuryProviderConfigurationError, match="journal binding drifted"
        ):
            _validate(evidence, tmp_path, other, XAI_MODEL)


@pytest.mark.parametrize(
    ("family", "model", "effort"),
    [
        (CODEX_FAMILY, "gpt-5.4", "xhigh"),
        (COPILOT_FAMILY, "grok-4.6", None),
        (XAI_FAMILY, "grok-4.6", None),
    ],
    ids=("codex", "copilot", "xai"),
)
def test_provider_metadata_validates_per_fixed_family(
    family: FoundryJuryProviderFamily, model: str, effort: str | None
) -> None:
    artifact = _artifact()
    metadata = provider_metadata(
        family=family,
        model=model,
        reasoning_effort=effort,
        timeout_seconds=family.default_timeout_seconds,
        execution_task_id=6000,
        execution_claimant="pi:test",
        source_identity=artifact.source_identity,
        dependency_identity=artifact.dependency_identity,
    )
    assert metadata["provider"] == family.provider_name
    assert metadata["auth_provider"] == family.auth_provider
    assert metadata["credential_mode"] == "no-refresh"
    assert metadata["timeout_seconds"] == family.default_timeout_seconds
    assert metadata["requested_route"] == family.requested_route(model)
    assert metadata["resolved_route"] == family.resolved_route(model)
    assert metadata["owner_commit"] == OWNER_COMMIT
    # Fixed families keep the historical metadata shape.
    assert "endpoint_origin" not in metadata
    assert "endpoint_origin_sha256" not in metadata
    validated = validate_foundry_jury_provider_metadata(
        metadata,
        execution_task_id=6000,
        execution_claimant="pi:test",
        model=model,
        reasoning_effort=effort,
        family=family,
    )
    assert validated == metadata
    for other in ALL_FAMILIES:
        if other is family:
            continue
        with pytest.raises(FoundryJuryProviderConfigurationError, match="drifted"):
            validate_foundry_jury_provider_metadata(
                metadata,
                execution_task_id=6000,
                execution_claimant="pi:test",
                model=model,
                reasoning_effort=effort,
                family=other,
            )


def _request(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "provider": XAI_FAMILY.provider_name,
        "adjudicator_id": "local",
        "adjudicator_kind": "local",
        "adjudicator_repo": None,
        "max_jurors": 1,
        "owner_source_root": tmp_path,
        "execution_task_id": 6000,
        "execution_claimant": "pi:test",
    }
    arguments.update(overrides)
    return execution_request(**arguments)


def test_xai_execution_request_uses_model_key_without_effort_or_endpoint(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    assert request["model"] == XAI_MODEL
    assert "codex_model" not in request
    assert "reasoning_effort" not in request
    assert "local_vllm_base_url" not in request
    assert set(request) == task_local_execution_request_keys(XAI_FAMILY.provider_name)
    assert revalidate_execution_request(request) == request
    assert task_local_family(request) is XAI_FAMILY
    explicit = _request(tmp_path, model="grok-4")
    assert explicit["model"] == "grok-4"
    assert revalidate_execution_request(explicit) == explicit


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"model": "gemini-3.7-flash"}, "requires owner source"),
        ({"model": "Grok-4.6"}, "requires owner source"),
        ({"model": "gpt-5.4"}, "requires owner source"),
        ({"reasoning_effort": "xhigh"}, "requires owner source"),
        ({"codex_model": "gpt-5.4"}, "codex_model is only"),
        ({"endpoint": "https://api.x.ai"}, "loopback"),
        ({"execution_task_id": 5308}, "requires owner source"),
    ],
)
def test_xai_execution_request_rejects_invalid_inputs(
    overrides: dict[str, Any], match: str, tmp_path: Path
) -> None:
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match=match
    ):
        _request(tmp_path, **overrides)


def test_xai_revalidate_rejects_foreign_keys(tmp_path: Path) -> None:
    request = _request(tmp_path)
    for key, value in (
        ("reasoning_effort", "xhigh"),
        ("local_vllm_base_url", "http://127.0.0.1:2456/v1"),
        ("codex_model", XAI_MODEL),
    ):
        drifted = {**request, key: value}
        with pytest.raises(
            comparison_jury.ProgramFoundryGepaComparisonJuryError,
            match="types are invalid",
        ):
            revalidate_execution_request(drifted)
    drifted = {**request, "model": "gemini-3.7-flash"}
    with pytest.raises(comparison_jury.ProgramFoundryGepaComparisonJuryError):
        revalidate_execution_request(drifted)


def test_xai_comparison_jury_cli_forwards_provider_and_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "consumption-receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    calls: list[dict[str, Any]] = []

    def execute(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"status": "ok", "reused": False}

    monkeypatch.setattr(
        comparison_jury, "execute_program_foundry_gepa_comparison_jury", execute
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "jury-foundry-gepa-comparison",
            "--receipt",
            str(receipt),
            "--provider",
            "foundry-dspy-lm-auth-xai",
            "--owner-source-root",
            str(owner_root),
            "--execution-task-id",
            "6000",
            "--execution-claimant",
            "pi:test",
            "--model",
            "grok-4.6",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "consumption_receipt_path": receipt,
            "provider": "foundry-dspy-lm-auth-xai",
            "adjudicator_id": "local_foundry_adjudicator",
            "adjudicator_kind": "local_foundry_adjudicator",
            "adjudicator_repo": None,
            "max_jurors": None,
            "owner_source_root": owner_root,
            "execution_task_id": 6000,
            "execution_claimant": "pi:test",
            "codex_model": None,
            "reasoning_effort": None,
            "model": "grok-4.6",
        }
    ]
    help_result = CliRunner().invoke(
        app, ["program-refine", "jury-foundry-gepa-comparison", "--help"]
    )
    assert help_result.exit_code == 0
    compact = "".join(help_result.output.split())
    for name in TASK_LOCAL_PROVIDER_NAMES:
        assert name in compact


def test_xai_comparison_jury_binds_runtime_and_records_model_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    owner_root = tmp_path / "maintained-owner"
    owner_root.mkdir()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        comparison_jury,
        "validate_successful_program_foundry_gepa_consumption_receipt",
        lambda path, **kwargs: dict(validated),
    )
    monkeypatch.setattr(
        comparison_jury, "run_task_local_preflight", lambda request, **kwargs: None
    )

    def build(slot: object, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return _model_result(validated)

    def validate_result(
        *, result_path: Path, **kwargs: Any
    ) -> tuple[dict[str, Any], str]:
        return json.loads(result_path.read_text(encoding="utf-8")), _sha256(result_path)

    monkeypatch.setattr(comparison_jury, "build_comparison_model_jury_result", build)
    monkeypatch.setattr(receipt_validation, "_validate_jury_result", validate_result)
    payload = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider=XAI_FAMILY.provider_name,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
        max_jurors=1,
    )
    assert payload["status"] == "ok"
    assert payload["effect"]["ak_called"] is True
    assert payload["execution_request"]["provider"] == XAI_FAMILY.provider_name
    assert payload["execution_request"]["model"] == XAI_MODEL
    assert "reasoning_effort" not in payload["execution_request"]
    assert calls[0]["provider"] == XAI_FAMILY.provider_name
    assert isinstance(
        calls[0]["provider_runtime_binding"],
        jury_runtime.ProgramModelJuryProviderRuntimeBinding,
    )
    reused = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider=XAI_FAMILY.provider_name,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
        max_jurors=1,
    )
    assert reused["reused"] is True
    assert len(calls) == 1


@dataclass(frozen=True, slots=True)
class _ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class _ChatRequest:
    model: str
    messages: tuple[_ChatMessage, ...]
    timeout_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class _ChatResponse:
    output_text: str
    observed_model: str | None
    semantic_request_sha256: str


class _ChatBackend:
    """Fake generic chat backend: messages only, no reasoning or format."""

    output_text = json.dumps({"judgment_json": json.dumps(JUDGMENT)})
    observed_model = "fake-observed"

    def __init__(self) -> None:
        self.requests: list[_ChatRequest] = []
        self.semantic_hashes: list[str] = []

    def prepare(self, request: _ChatRequest):
        assert type(request) is _ChatRequest
        assert all(m.role in {"system", "user", "assistant"} for m in request.messages)
        self.requests.append(request)
        semantic_hash = hashlib.sha256(
            b"dspx-oracle-semantic-chat-request-v1\0"
            + json.dumps(
                {
                    "messages": [asdict(m) for m in request.messages],
                    "model": request.model,
                    "stream": False,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        self.semantic_hashes.append(semantic_hash)
        return type("Prepared", (), {"semantic_request_sha256": semantic_hash})()

    def invoke(self, prepared: object, *, outcome_receipt: object) -> _ChatResponse:
        _completed_with(self.observed_model)(outcome_receipt)
        return _ChatResponse(
            self.output_text,
            self.observed_model,
            getattr(prepared, "semantic_request_sha256"),
        )


class _XaiBackend(_ChatBackend):
    """Fake XaiBackend: keyword-only auth_path, fixed endpoint."""

    observed_model = "grok-4.6-0901"
    constructed: list[Any] = []

    def __init__(self, *, auth_path: Any = "<default-pi-auth>") -> None:
        super().__init__()
        self.auth_path = auth_path
        type(self).constructed.append(self)


class _ChatOwner(_Owner):
    def __init__(self, backend_type: type[Any]) -> None:
        super().__init__(_artifact())
        self.backend_type = backend_type
        self.message_type = _ChatMessage
        self.request_type = _ChatRequest
        self.response_type = _ChatResponse


def test_xai_construct_backend_hook_uses_keyword_auth_path_only() -> None:
    owner = _ChatOwner(_XaiBackend)
    _XaiBackend.constructed.clear()
    default = XAI_FAMILY.construct_backend(owner)
    assert type(default) is _XaiBackend and default.auth_path == "<default-pi-auth>"
    explicit = XAI_FAMILY.construct_backend(owner, auth_path="/tmp/auth.json")
    assert explicit.auth_path == "/tmp/auth.json"
    same = XAI_FAMILY.construct_backend(owner, endpoint="https://api.x.ai")
    assert type(same) is _XaiBackend
    with pytest.raises(ValueError, match="endpoint is fixed"):
        XAI_FAMILY.construct_backend(owner, endpoint="https://api.x.ai:8443")
    assert len(_XaiBackend.constructed) == 3


def run_configured_jury(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    family: FoundryJuryProviderFamily,
    backend_type: type[Any],
    model: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Any]:
    """Configure the family through its owner hook and run one fake juror."""

    owner = _ChatOwner(backend_type)
    task = {
        "id": 6000,
        "title": family.execution_task_title,
        "repo": str(tmp_path.resolve()),
        "status": "claimed",
        "claimed_by": "pi:test",
        "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        "completed_at": None,
        "result": None,
    }
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_provider_custody.run_ak_task_show",
        lambda task_id: dict(task),
    )
    loaded: list[tuple[Path, FoundryJuryProviderFamily]] = []

    def verify(root: Path, bound: FoundryJuryProviderFamily) -> Any:
        loaded.append((root, bound))
        return owner

    monkeypatch.setattr(provider_module, "verify_loaded_foundry_jury_owner", verify)
    configured = configure_foundry_jury_provider(
        owner_source_root=tmp_path,
        journal_parent=tmp_path / "provider-outcomes",
        execution_task_id=6000,
        execution_claimant="pi:test",
        repo_root=tmp_path,
        contract_sha256="a" * 64,
        expected_juror_ids=("quality",),
        model=model,
        family=family,
    )
    try:
        assert loaded == [(tmp_path, family)]
        metadata = dict(configured.metadata())
        result = _run_juror_model(
            juror={"id": "quality", "perspective": "quality"},
            rubric={"criteria": ["bounded"]},
            candidate_identity={"sha256": "a" * 64},
            evidence_json='{"bounded":true}',
            adjudicator={"kind": "deterministic"},
        )
        evidence = dict(configured.finalize())
    finally:
        configured.close()
    return metadata, result, evidence, owner


def test_xai_family_runs_end_to_end_through_configure_adapter_and_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous_lm = getattr(dspy.settings, "lm", None)
    previous_adapter = getattr(dspy.settings, "adapter", None)
    _XaiBackend.constructed.clear()
    metadata, result, evidence, _ = run_configured_jury(
        tmp_path,
        monkeypatch,
        family=XAI_FAMILY,
        backend_type=_XaiBackend,
        model=XAI_MODEL,
    )
    assert getattr(dspy.settings, "lm", None) is previous_lm
    assert getattr(dspy.settings, "adapter", None) is previous_adapter
    assert result["outcome"] == "supports_review_evidence"
    backend = _XaiBackend.constructed[-1]
    assert backend.auth_path == "<default-pi-auth>"
    request = backend.requests[0]
    assert request.model == XAI_MODEL
    assert request.timeout_seconds == 180.0
    assert metadata["timeout_seconds"] == 180.0
    assert not hasattr(request, "reasoning_effort")
    assert not hasattr(request, "response_format")
    assert metadata["provider"] == XAI_FAMILY.provider_name
    assert metadata["model"] == XAI_MODEL
    assert metadata["auth_provider"] == "xai"
    assert metadata["reasoning_effort"] is None
    assert "endpoint_origin_sha256" not in metadata
    assert validate_foundry_jury_provider_metadata(
        metadata,
        execution_task_id=6000,
        execution_claimant="pi:test",
        model=XAI_MODEL,
        reasoning_effort=None,
        family=XAI_FAMILY,
    )
    assert evidence["session_disposition"] == "complete"
    record = evidence["call_records"][0]
    assert record["semantic_request_sha256"] == backend.semantic_hashes[0]
    assert record["observed_model"] == "grok-4.6-0901"
    _stub_owner_source(monkeypatch)
    validated = _validate(evidence, tmp_path, XAI_FAMILY, XAI_MODEL, ("quality",))
    assert validated == evidence
    journal = sorted((tmp_path / "provider-outcomes").iterdir())[0]
    wrapper = json.loads((journal / "reservation.json").read_text("utf-8"))
    reservation = wrapper["reservation"]
    assert reservation["endpoint_origin_sha256"] == XAI_ENDPOINT_ORIGIN_SHA256
    assert reservation["requested_route"] == "dspy-lm-auth:xai:grok-4.6"
    assert reservation["resolved_route"] == "openai:grok-4.6:chat"


def test_xai_configure_rejects_invalid_model_before_owner_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def verify(root: Path, bound: FoundryJuryProviderFamily) -> Any:
        raise AssertionError("owner must not load for a rejected model")

    monkeypatch.setattr(provider_module, "verify_loaded_foundry_jury_owner", verify)
    for model, effort in (("gemini-3.7-flash", None), (XAI_MODEL, "xhigh")):
        with pytest.raises(FoundryJuryProviderConfigurationError, match="xai"):
            configure_foundry_jury_provider(
                owner_source_root=tmp_path,
                journal_parent=tmp_path / "provider-outcomes",
                execution_task_id=6000,
                execution_claimant="pi:test",
                repo_root=tmp_path,
                contract_sha256="a" * 64,
                expected_juror_ids=("quality",),
                model=model,
                reasoning_effort=effort,
                family=XAI_FAMILY,
            )


def test_family_timeouts_are_pinned_and_enforced_before_owner_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """xAI carries 180 s per call; the other three families keep 60 s."""

    assert [family.default_timeout_seconds for family in ALL_FAMILIES] == [
        60.0,
        60.0,
        180.0,
        60.0,
    ]
    assert XAI_FAMILY.default_timeout_seconds == 180.0

    def verify(root: Path, bound: FoundryJuryProviderFamily) -> Any:
        raise AssertionError("owner must not load for a rejected timeout")

    monkeypatch.setattr(provider_module, "verify_loaded_foundry_jury_owner", verify)
    for family, wrong in ((XAI_FAMILY, 60.0), (COPILOT_FAMILY, 180.0)):
        with pytest.raises(
            FoundryJuryProviderConfigurationError, match="timeout must match"
        ):
            configure_foundry_jury_provider(
                owner_source_root=tmp_path,
                journal_parent=tmp_path / "provider-outcomes",
                execution_task_id=6000,
                execution_claimant="pi:test",
                repo_root=tmp_path,
                contract_sha256="a" * 64,
                expected_juror_ids=("quality",),
                timeout_seconds=wrong,
                family=family,
            )


class _LoadedOwnerArtifact:
    source_identity: dict[str, Any] = {}
    dependency_identity: dict[str, Any] = {}
    accepted = True

    def revalidate(self) -> None:
        return None


def _loaded_owner(
    family: FoundryJuryProviderFamily, backend_type: type[Any], tmp_path: Path
) -> VerifiedFoundryJuryOwner:
    def typed(name: str) -> type[Any]:
        return type(name, (), {"__module__": family.contract_module})

    return VerifiedFoundryJuryOwner(
        artifact=cast(Any, _LoadedOwnerArtifact()),
        backend_type=backend_type,
        message_type=typed(family.message_class),
        request_type=typed(family.request_class),
        response_type=typed(family.response_class),
        backend_module=None,
        receipt_module=None,
        source_root=tmp_path,
        family=family,
    )


@pytest.mark.parametrize("family", ALL_FAMILIES, ids=lambda item: item.auth_provider)
def test_loaded_owner_rules_apply_to_all_four_families(
    family: FoundryJuryProviderFamily, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_owner.verify_foundry_jury_owner_source",
        lambda root: {},
    )
    expected = tmp_path / "src" / (family.backend_module.replace(".", "/") + ".py")
    expected.parent.mkdir(parents=True, exist_ok=True)
    expected.write_text(f"class {family.backend_class}: ...\n", encoding="utf-8")
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_owner.inspect.getsourcefile",
        lambda item: str(expected),
    )
    exact = type(family.backend_class, (), {"__module__": family.backend_module})
    assert "dspy_lm_auth.lm" not in sys.modules
    _loaded_owner(family, exact, tmp_path).revalidate()
    for other in ALL_FAMILIES:
        if other is family:
            continue
        foreign = type(other.backend_class, (), {"__module__": other.backend_module})
        with pytest.raises(ProviderOutcomeConsumerError) as foreign_drift:
            _loaded_owner(family, foreign, tmp_path).revalidate()
        assert foreign_drift.value.reason == "loaded_owner_backend_type_drift"
    lm_subclass = type(
        family.backend_class, (BaseLM,), {"__module__": family.backend_module}
    )
    with pytest.raises(ProviderOutcomeConsumerError) as lm_drift:
        _loaded_owner(family, lm_subclass, tmp_path).revalidate()
    assert lm_drift.value.reason == "loaded_owner_backend_type_drift"
    monkeypatch.setitem(sys.modules, "dspy_lm_auth.lm", cast(Any, object()))
    with pytest.raises(ProviderOutcomeConsumerError) as legacy_drift:
        _loaded_owner(family, exact, tmp_path).revalidate()
    assert legacy_drift.value.reason == "loaded_owner_backend_type_drift"


class _FakeRuntime:
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.closed = False

    def metadata(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": "fixture"}

    def finalize(self) -> dict[str, Any]:
        return {"logical_call_total": 1}

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("provider", sorted(TASK_LOCAL_PROVIDER_NAMES))
def test_runtime_binding_accepts_every_task_local_provider_name(
    provider: str,
) -> None:
    runtimes: list[_FakeRuntime] = []

    def factory(selected: Any) -> _FakeRuntime:
        runtime = _FakeRuntime(provider)
        runtimes.append(runtime)
        return runtime

    config, results, evidence = run_program_model_jurors(
        selected=[{"id": "quality", "perspective": "quality"}],
        rubrics={},
        candidate_identity={"sha256": "a" * 64},
        evidence_json="{}",
        adjudicator={"kind": "deterministic"},
        provider=provider,
        configure_provider=lambda name: {"provider": "unused"},
        run_juror=lambda **kwargs: {"outcome": "supports_review_evidence"},
        sanitize_diagnostic=lambda exc: type(exc).__name__,
        provider_runtime_binding=_bind_program_model_jury_provider_runtime(factory),
    )
    assert config["provider"] == provider
    assert results[0]["provider"] == provider
    assert results[0]["status"] == "judged"
    assert evidence == {"logical_call_total": 1}
    assert runtimes[0].closed is True


def test_runtime_binding_still_rejects_generic_provider_names() -> None:
    with pytest.raises(
        jury_runtime.ProgramModelJuryExecutionError, match="restricted to the foundry"
    ):
        run_program_model_jurors(
            selected=[],
            rubrics={},
            candidate_identity={},
            evidence_json="{}",
            adjudicator={},
            provider="openai-compatible",
            configure_provider=lambda name: {},
            run_juror=lambda **kwargs: {},
            sanitize_diagnostic=lambda exc: "",
            provider_runtime_binding=_bind_program_model_jury_provider_runtime(
                lambda selected: _FakeRuntime("x")
            ),
        )


def test_owner_pins_cover_generic_chat_and_xai_modules() -> None:
    for relative in (
        "src/dspy_lm_auth/chat_backend.py",
        "src/dspy_lm_auth/chat_backend_contract.py",
        "src/dspy_lm_auth/chat_backend_runtime.py",
        "src/dspy_lm_auth/chat_backend_transport.py",
        "src/dspy_lm_auth/_chat_credential.py",
        "src/dspy_lm_auth/xai_backend.py",
        "src/dspy_lm_auth/local_vllm_backend.py",
    ):
        assert relative in REQUIRED_EXTRA_OWNER_FILES
        assert relative in _EXTRA_OWNER_FILES
    assert missing_required_extra_files() == ()
