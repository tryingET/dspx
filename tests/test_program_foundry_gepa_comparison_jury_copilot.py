# summary: "Credential-free tests for the GitHub Copilot foundry jury provider family."
from __future__ import annotations

import hashlib
import json
import subprocess
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
import dspx.services.program_model_jury_provider_runtime as jury_runtime
from dspx.cli.dspx import app
from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.provider_registry import SUPPORTED_PROVIDER_NAMES
from dspx.services.program_foundry_gepa_comparison_jury_owner import (
    _EXTRA_OWNER_FILES,
    _OWNER_MODULES,
    OWNER_COMMIT,
    OWNER_LOCK_SHA256,
    OWNER_TREE,
    VerifiedFoundryJuryOwner,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider import (
    FoundryJuryJSONAdapter,
    _FoundryJuryFormattingProvider,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
    ALLOWED_REASONING_EFFORTS,
    AUTH_PROVIDER,
    CODEX_FAMILY,
    COPILOT_FAMILY,
    DEFAULT_CODEX_MODEL,
    DEFAULT_REASONING_EFFORT,
    ENDPOINT_ORIGIN_SHA256,
    EXECUTION_TASK_TITLE,
    MODEL_RE,
    PROVIDER_NAME,
    TASK_LOCAL_PROVIDER_NAMES,
    FoundryJuryCallCustodian,
    FoundryJuryProviderConfigurationError,
    FoundryJuryProviderFamily,
    canonical_ak_task_revalidator,
    endpoint_origin_sha256,
    family_for_provider,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (
    LOCAL_VLLM_FAMILY,
    XAI_FAMILY,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_evidence import (
    validate_foundry_jury_provider_evidence,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_metadata import (
    provider_metadata,
    validate_foundry_jury_provider_metadata,
)
from dspx.services.program_foundry_gepa_comparison_jury_runtime import (
    TASK_LOCAL_EXECUTION_REQUEST_KEYS,
    execution_request,
    revalidate_execution_request,
    task_local_execution_request_keys,
    task_local_process_slot,
)
from dspx.services.program_model_jury_execution import _run_juror_model
from dspx.services.soomfon_provider_outcome_receipt_contract import (
    ProviderOutcomeConsumerError,
)
from foundry_jury_owner_repin import collect_pins, render_pin_block
from test_program_foundry_gepa_comparison_jury import (
    _fixture,
    _model_result,
    _sha256,
)
from test_program_foundry_gepa_comparison_jury_provider import (
    _Event,
    _Owner,
    _Receipt,
    _artifact,
)

FAMILIES = (CODEX_FAMILY, COPILOT_FAMILY)
FORK_ROOT = Path("/home/tryinget/ai-society/softwareco/fork/dspy-lm-auth")


def test_family_literals_and_codex_aliases_are_pinned() -> None:
    assert CODEX_FAMILY.provider_name == "foundry-dspy-lm-auth-codex"
    assert COPILOT_FAMILY.provider_name == "foundry-dspy-lm-auth-github-copilot"
    assert COPILOT_FAMILY.auth_provider == "github-copilot"
    assert COPILOT_FAMILY.default_model == "gemini-3.7-flash"
    assert COPILOT_FAMILY.allowed_reasoning_efforts is None
    assert COPILOT_FAMILY.default_reasoning_effort is None
    assert COPILOT_FAMILY.execution_task_title == (
        "Execute one receipt-bound foundry comparison jury with dspy-lm-auth "
        "GitHub Copilot"
    )
    assert COPILOT_FAMILY.requested_route("gemini-3.7-flash") == (
        "dspy-lm-auth:github-copilot:gemini-3.7-flash"
    )
    assert COPILOT_FAMILY.resolved_route("gemini-3.7-flash") == (
        "openai:gemini-3.7-flash:chat"
    )
    assert COPILOT_FAMILY.model_key == "model"
    assert COPILOT_FAMILY.strict_observed_model is False
    assert COPILOT_FAMILY.backend_class == "GithubCopilotBackend"
    assert PROVIDER_NAME == CODEX_FAMILY.provider_name == "foundry-dspy-lm-auth-codex"
    assert AUTH_PROVIDER == "codex"
    assert DEFAULT_CODEX_MODEL == "gpt-5.4"
    assert DEFAULT_REASONING_EFFORT == "xhigh"
    assert ALLOWED_REASONING_EFFORTS == frozenset({"low", "medium", "high", "xhigh"})
    assert MODEL_RE is CODEX_FAMILY.model_re
    assert EXECUTION_TASK_TITLE == (
        "Execute one receipt-bound foundry comparison jury with dspy-lm-auth Codex"
    )
    assert CODEX_FAMILY.requested_route("gpt-5.4") == "dspy-lm-auth:codex:gpt-5.4"
    assert CODEX_FAMILY.resolved_route("gpt-5.4") == "openai:gpt-5.4:responses"
    assert CODEX_FAMILY.model_key == "codex_model"
    assert CODEX_FAMILY.strict_observed_model is True
    assert TASK_LOCAL_PROVIDER_NAMES == frozenset(
        {
            CODEX_FAMILY.provider_name,
            COPILOT_FAMILY.provider_name,
            XAI_FAMILY.provider_name,
            LOCAL_VLLM_FAMILY.provider_name,
        }
    )
    assert COPILOT_FAMILY.contract_module == "dspy_lm_auth.chat_backend_contract"
    assert COPILOT_FAMILY.message_class == "ChatBackendMessage"
    assert COPILOT_FAMILY.endpoint_env is None
    assert COPILOT_FAMILY.with_endpoint(None) is COPILOT_FAMILY
    assert family_for_provider("fixture-provider") is None
    assert family_for_provider(None) is None
    for family in FAMILIES:
        assert family.provider_name not in SUPPORTED_PROVIDER_NAMES


def test_endpoint_origin_sha256_uses_the_v11_origin_rule() -> None:
    def rule(host: str) -> str:
        canonical = json.dumps(
            {"scheme": "https", "hostname": host},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(
            b"dspx-oracle-semantic-v11-endpoint-origin-v1\0" + canonical
        ).hexdigest()

    assert CODEX_FAMILY.endpoint_origin == "https://chatgpt.com/backend-api/codex"
    assert COPILOT_FAMILY.endpoint_origin == "https://api.individual.githubcopilot.com"
    assert (
        ENDPOINT_ORIGIN_SHA256
        == CODEX_FAMILY.endpoint_origin_sha256
        == ("7d4b206e8a080358f16d8048e0705d8e17c9df9b8968ab150ff73ed1643294c8")
    )
    assert COPILOT_FAMILY.endpoint_origin_sha256 == (
        "492c0bc03782d6829c9555ed9da0d359510619c2beb561c89505495cb241871d"
    )
    for family in FAMILIES:
        assert endpoint_origin_sha256(family.endpoint_origin) == (
            family.endpoint_origin_sha256
        )
        assert rule(family.endpoint_origin.split("//", 1)[1].split("/", 1)[0]) == (
            family.endpoint_origin_sha256
        )
    with pytest.raises(ValueError):
        endpoint_origin_sha256("http://chatgpt.com")
    with pytest.raises(ValueError):
        endpoint_origin_sha256("https://user@chatgpt.com")


@pytest.mark.parametrize(
    ("family", "allowed", "rejected"),
    [
        (CODEX_FAMILY, "gpt-5.6-luna", "gemini-3.7-flash"),
        (COPILOT_FAMILY, "gemini-3.7-flash", "gpt-5.4"),
        (COPILOT_FAMILY, "gemini-3.7-flash-001", "Gemini-3.7"),
        (COPILOT_FAMILY, "grok-4.6", "Grok-4.6"),
        (COPILOT_FAMILY, "grok-4.6-fast", "claude-4"),
    ],
)
def test_model_rules_are_family_specific(
    family: FoundryJuryProviderFamily, allowed: str, rejected: str
) -> None:
    assert family.model_allowed(allowed)
    assert not family.model_allowed(rejected)
    assert not family.model_allowed(None)


def test_reasoning_effort_rules_are_family_specific() -> None:
    assert CODEX_FAMILY.reasoning_effort_allowed("xhigh")
    assert not CODEX_FAMILY.reasoning_effort_allowed(None)
    assert not CODEX_FAMILY.reasoning_effort_allowed("max")
    assert COPILOT_FAMILY.reasoning_effort_allowed(None)
    assert not COPILOT_FAMILY.reasoning_effort_allowed("xhigh")
    assert COPILOT_FAMILY.resolve_reasoning_effort(None) is None
    assert CODEX_FAMILY.resolve_reasoning_effort(None) == "xhigh"


@pytest.mark.parametrize("family", FAMILIES, ids=lambda item: item.auth_provider)
def test_canonical_task_revalidator_binds_family_execution_title(
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
    other = COPILOT_FAMILY if family is CODEX_FAMILY else CODEX_FAMILY
    task["title"] = other.execution_task_title
    with pytest.raises(
        FoundryJuryProviderConfigurationError, match="authority is not active"
    ):
        revalidate()


def _completed_with(observed_model: str):
    def completed(receipt: object) -> list[dict[str, str]]:
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
                observed_model=observed_model,
            ),
        ):
            typed_receipt.sink(event)
        return [{"judgment_json": "{}"}]

    return completed


def _custodian(
    tmp_path: Path, family: FoundryJuryProviderFamily, model: str
) -> FoundryJuryCallCustodian:
    return FoundryJuryCallCustodian(
        journal_parent=tmp_path / "provider-outcomes",
        owner=_Owner(_artifact()),  # type: ignore[arg-type]
        execution_task_id=6000,
        contract_sha256="a" * 64,
        expected_juror_ids=("quality", "authority"),
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
) -> dict[str, Any]:
    return validate_foundry_jury_provider_evidence(
        evidence,
        journal_parent=tmp_path / "provider-outcomes",
        owner_source_root=tmp_path / "owner",
        execution_task_id=6000,
        contract_sha256="a" * 64,
        expected_juror_ids=("quality", "authority"),
        expected_model=model,
        family=family,
    )


@pytest.mark.parametrize(
    ("family", "model"),
    [(CODEX_FAMILY, "gpt-5.6-luna"), (COPILOT_FAMILY, "gemini-3.7-flash")],
    ids=("codex", "copilot"),
)
def test_custodian_binds_family_routes_and_origin_into_journals(
    family: FoundryJuryProviderFamily,
    model: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custodian = _custodian(tmp_path, family, model)
    for juror_id, semantic in (("quality", "c" * 64), ("authority", "d" * 64)):
        custodian.invoke(
            juror_id=juror_id,
            semantic_request_sha256=semantic,
            invoke=_completed_with(model),
        )
    evidence = custodian.finalize()
    assert evidence["session_disposition"] == "complete"
    record = evidence["call_records"][0]
    assert ("observed_model" in record) is (not family.strict_observed_model)
    if not family.strict_observed_model:
        assert record["observed_model"] == model
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_provider_evidence.verify_foundry_jury_owner_source",
        lambda path: _artifact().source_identity,
    )
    assert _validate(evidence, tmp_path, family, model) == evidence
    other = COPILOT_FAMILY if family is CODEX_FAMILY else CODEX_FAMILY
    with pytest.raises(
        FoundryJuryProviderConfigurationError, match="journal binding drifted"
    ):
        _validate(evidence, tmp_path, other, model)


def test_observed_model_rule_is_strict_for_codex_and_recorded_for_copilot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_provider_evidence.verify_foundry_jury_owner_source",
        lambda path: _artifact().source_identity,
    )
    copilot_root = tmp_path / "copilot"
    copilot_root.mkdir()
    custodian = _custodian(copilot_root, COPILOT_FAMILY, "gemini-3.7-flash")
    for juror_id, semantic in (("quality", "c" * 64), ("authority", "d" * 64)):
        custodian.invoke(
            juror_id=juror_id,
            semantic_request_sha256=semantic,
            invoke=_completed_with("gemini-3.7-flash-001"),
        )
    evidence = custodian.finalize()
    assert [item["observed_model"] for item in evidence["call_records"]] == [
        "gemini-3.7-flash-001",
        "gemini-3.7-flash-001",
    ]
    assert _validate(evidence, copilot_root, COPILOT_FAMILY, "gemini-3.7-flash")
    tampered = json.loads(json.dumps(evidence))
    tampered["call_records"][0]["observed_model"] = "gemini-3.7-flash"
    with pytest.raises(
        FoundryJuryProviderConfigurationError, match="journal binding drifted"
    ):
        _validate(tampered, copilot_root, COPILOT_FAMILY, "gemini-3.7-flash")

    codex_root = tmp_path / "codex"
    codex_root.mkdir()
    custodian = _custodian(codex_root, CODEX_FAMILY, "gpt-5.6-luna")
    custodian.invoke(
        juror_id="quality",
        semantic_request_sha256="c" * 64,
        invoke=_completed_with("gpt-5.6-luna-2026"),
    )
    custodian.latch_closed_after_completed_call()
    evidence = custodian.finalize()
    assert "observed_model" not in evidence["call_records"][0]
    with pytest.raises(
        FoundryJuryProviderConfigurationError, match="journal binding drifted"
    ):
        _validate(evidence, codex_root, CODEX_FAMILY, "gpt-5.6-luna")


@pytest.mark.parametrize(
    ("family", "model", "effort"),
    [(CODEX_FAMILY, "gpt-5.4", "xhigh"), (COPILOT_FAMILY, "gemini-3.7-flash", None)],
    ids=("codex", "copilot"),
)
def test_provider_metadata_validates_per_family(
    family: FoundryJuryProviderFamily, model: str, effort: str | None
) -> None:
    artifact = _artifact()
    metadata = provider_metadata(
        family=family,
        model=model,
        reasoning_effort=effort,
        timeout_seconds=60.0,
        execution_task_id=6000,
        execution_claimant="pi:test",
        source_identity=artifact.source_identity,
        dependency_identity=artifact.dependency_identity,
    )
    assert metadata["provider"] == family.provider_name
    assert metadata["auth_provider"] == family.auth_provider
    assert metadata["credential_mode"] == "no-refresh"
    assert metadata["requested_route"] == family.requested_route(model)
    assert metadata["resolved_route"] == family.resolved_route(model)
    assert metadata["reasoning_effort"] == effort
    assert metadata["owner_commit"] == OWNER_COMMIT
    validated = validate_foundry_jury_provider_metadata(
        metadata,
        execution_task_id=6000,
        execution_claimant="pi:test",
        model=model,
        reasoning_effort=effort,
        family=family,
    )
    assert validated == metadata
    other = COPILOT_FAMILY if family is CODEX_FAMILY else CODEX_FAMILY
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
        "provider": COPILOT_FAMILY.provider_name,
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


def test_copilot_execution_request_uses_model_key_without_reasoning_effort(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    assert request["model"] == "gemini-3.7-flash"
    assert "codex_model" not in request
    assert "reasoning_effort" not in request
    assert set(request) == task_local_execution_request_keys(
        COPILOT_FAMILY.provider_name
    )
    assert revalidate_execution_request(request) == request
    assert task_local_execution_request_keys(CODEX_FAMILY.provider_name) == (
        TASK_LOCAL_EXECUTION_REQUEST_KEYS
    )
    assert "codex_model" in TASK_LOCAL_EXECUTION_REQUEST_KEYS
    codex = _request(tmp_path, provider=CODEX_FAMILY.provider_name)
    assert codex["codex_model"] == "gpt-5.4"
    assert codex["reasoning_effort"] == "xhigh"
    assert revalidate_execution_request(codex) == codex
    aliased = _request(
        tmp_path, provider=CODEX_FAMILY.provider_name, model="gpt-5.6-luna"
    )
    assert aliased["codex_model"] == "gpt-5.6-luna"


@pytest.mark.parametrize(
    ("provider", "overrides", "match"),
    [
        (COPILOT_FAMILY.provider_name, {"model": "gpt-5.4"}, "requires owner source"),
        (CODEX_FAMILY.provider_name, {"model": "gemini-3.7-flash"}, "requires owner"),
        (COPILOT_FAMILY.provider_name, {"reasoning_effort": "xhigh"}, "requires owner"),
        (
            COPILOT_FAMILY.provider_name,
            {"codex_model": "gpt-5.4"},
            "codex_model is only",
        ),
        (
            CODEX_FAMILY.provider_name,
            {"model": "gpt-5.4", "codex_model": "gpt-5.6-luna"},
            "must agree",
        ),
        ("fixture-provider", {"model": "gemini-3.7-flash"}, "only valid for"),
    ],
)
def test_execution_request_rejects_family_mismatches(
    provider: str, overrides: dict[str, Any], match: str, tmp_path: Path
) -> None:
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match=match
    ):
        if provider == "fixture-provider":
            execution_request(
                provider=provider,
                adjudicator_id="local",
                adjudicator_kind="local",
                adjudicator_repo=None,
                max_jurors=1,
                **overrides,
            )
        else:
            _request(tmp_path, provider=provider, **overrides)


def test_revalidate_rejects_wrong_model_key_for_family(tmp_path: Path) -> None:
    request = _request(tmp_path)
    drifted = {key: value for key, value in request.items() if key != "model"}
    drifted["codex_model"] = "gemini-3.7-flash"
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="types are invalid"
    ):
        revalidate_execution_request(drifted)


def test_task_local_process_slot_serializes_copilot_family() -> None:
    with task_local_process_slot(COPILOT_FAMILY.provider_name):
        with pytest.raises(
            comparison_jury.ProgramFoundryGepaComparisonJuryError,
            match="already active",
        ):
            with task_local_process_slot(CODEX_FAMILY.provider_name):
                pass


def test_copilot_comparison_jury_cli_forwards_model_and_family(
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
            "foundry-dspy-lm-auth-github-copilot",
            "--owner-source-root",
            str(owner_root),
            "--execution-task-id",
            "6000",
            "--execution-claimant",
            "pi:test",
            "--model",
            "gemini-3.7-flash",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "consumption_receipt_path": receipt,
            "provider": "foundry-dspy-lm-auth-github-copilot",
            "adjudicator_id": "local_foundry_adjudicator",
            "adjudicator_kind": "local_foundry_adjudicator",
            "adjudicator_repo": None,
            "max_jurors": None,
            "owner_source_root": owner_root,
            "execution_task_id": 6000,
            "execution_claimant": "pi:test",
            "codex_model": None,
            "reasoning_effort": None,
            "model": "gemini-3.7-flash",
        }
    ]


def test_copilot_comparison_jury_binds_runtime_and_records_model_key(
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
    monkeypatch.setattr(comparison_jury, "_validate_jury_result", validate_result)

    payload = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider=COPILOT_FAMILY.provider_name,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
        max_jurors=1,
    )
    assert payload["status"] == "ok"
    assert payload["effect"]["ak_called"] is True
    assert payload["execution_request"]["model"] == "gemini-3.7-flash"
    assert "reasoning_effort" not in payload["execution_request"]
    assert calls[0]["provider"] == COPILOT_FAMILY.provider_name
    assert isinstance(
        calls[0]["provider_runtime_binding"],
        jury_runtime.ProgramModelJuryProviderRuntimeBinding,
    )
    reused = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider=COPILOT_FAMILY.provider_name,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
        max_jurors=1,
    )
    assert reused["reused"] is True
    assert len(calls) == 1


@dataclass(frozen=True, slots=True)
class _CopilotMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class _CopilotRequest:
    model: str
    messages: tuple[_CopilotMessage, ...]
    timeout_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class _CopilotResponse:
    output_text: str
    observed_model: str | None
    semantic_request_sha256: str


class _CopilotBackend:
    """Fake GithubCopilotBackend: chat messages only, no reasoning or format."""

    def __init__(self, output_text: str, observed_model: str) -> None:
        self.output_text = output_text
        self.observed_model = observed_model
        self.requests: list[_CopilotRequest] = []
        self.semantic_hashes: list[str] = []

    def prepare(self, request: _CopilotRequest):
        assert type(request) is _CopilotRequest
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

    def invoke(self, prepared: object, *, outcome_receipt: object) -> _CopilotResponse:
        _completed_with(self.observed_model)(outcome_receipt)
        return _CopilotResponse(
            self.output_text,
            self.observed_model,
            getattr(prepared, "semantic_request_sha256"),
        )


class _CopilotOwner(_Owner):
    def __init__(self) -> None:
        super().__init__(_artifact())
        self.message_type = _CopilotMessage
        self.request_type = _CopilotRequest
        self.response_type = _CopilotResponse


def test_copilot_family_runs_end_to_end_through_adapter_and_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    judgment = {
        "outcome": "supports_review_evidence",
        "rationale": "bounded fixture",
        "evidence_strengths": ["receipt"],
        "concerns": [],
        "improvement_requests": [],
        "confidence": "high",
    }
    backend = _CopilotBackend(
        json.dumps({"judgment_json": json.dumps(judgment)}),
        observed_model="gemini-3.7-flash-001",
    )
    owner = _CopilotOwner()
    custodian = FoundryJuryCallCustodian(
        journal_parent=tmp_path / "provider-outcomes",
        owner=owner,  # type: ignore[arg-type]
        execution_task_id=6000,
        contract_sha256="a" * 64,
        expected_juror_ids=("quality",),
        requested_route=COPILOT_FAMILY.requested_route("gemini-3.7-flash"),
        resolved_route=COPILOT_FAMILY.resolved_route("gemini-3.7-flash"),
        authority_revalidator=lambda: None,
        family=COPILOT_FAMILY,
    )
    provider = _FoundryJuryFormattingProvider(
        "gemini-3.7-flash", COPILOT_FAMILY.provider_name
    )
    lm = DSPyTypedLMAdapter(provider, cache=False, callbacks=[])
    adapter = FoundryJuryJSONAdapter(
        owner=owner,  # type: ignore[arg-type]
        lm=lm,
        backend=backend,
        custodian=custodian,
        model="gemini-3.7-flash",
        reasoning_effort=None,
        timeout_seconds=60.0,
        family=COPILOT_FAMILY,
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
    request = backend.requests[0]
    assert request.model == "gemini-3.7-flash"
    assert request.timeout_seconds == 60.0
    assert not hasattr(request, "reasoning_effort")
    assert not hasattr(request, "response_format")
    assert {m.role for m in request.messages} <= {"system", "user", "assistant"}
    evidence = custodian.finalize()
    assert evidence["session_disposition"] == "complete"
    record = evidence["call_records"][0]
    assert record["semantic_request_sha256"] == backend.semantic_hashes[0]
    assert record["observed_model"] == "gemini-3.7-flash-001"
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
        expected_juror_ids=("quality",),
        expected_model="gemini-3.7-flash",
        family=COPILOT_FAMILY,
    )
    assert validated == evidence


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


@pytest.mark.parametrize("family", FAMILIES, ids=lambda item: item.auth_provider)
def test_loaded_owner_rules_apply_to_both_families(
    family: FoundryJuryProviderFamily, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_owner.verify_foundry_jury_owner_source",
        lambda root: {},
    )
    other = COPILOT_FAMILY if family is CODEX_FAMILY else CODEX_FAMILY
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
    exact = type(family.backend_class, (), {"__module__": family.backend_module})
    monkeypatch.setitem(sys.modules, "dspy_lm_auth.lm", cast(Any, object()))
    with pytest.raises(ProviderOutcomeConsumerError) as legacy_drift:
        _loaded_owner(family, exact, tmp_path).revalidate()
    assert legacy_drift.value.reason == "loaded_owner_backend_type_drift"


def test_owner_pins_cover_copilot_modules_and_repin_helper_reproduces_them(
    tmp_path: Path,
) -> None:
    for relative in (
        "src/dspy_lm_auth/_codex_credential.py",
        "src/dspy_lm_auth/codex_request.py",
        "src/dspy_lm_auth/outcome_receipt_chat.py",
        "src/dspy_lm_auth/copilot_backend_contract.py",
        "src/dspy_lm_auth/_copilot_credential.py",
        "src/dspy_lm_auth/copilot_receipt_transport.py",
        "src/dspy_lm_auth/copilot_receipt_runtime.py",
        "src/dspy_lm_auth/copilot_backend.py",
        "src/dspy_lm_auth/chat_backend.py",
        "src/dspy_lm_auth/chat_backend_contract.py",
    ):
        assert relative in _EXTRA_OWNER_FILES
    root = tmp_path / "owner"
    for relative, _ in _OWNER_MODULES.values():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(f"# {relative}\n", encoding="utf-8")
    for relative in _EXTRA_OWNER_FILES:
        (root / relative).write_text(f"# {relative}\n", encoding="utf-8")
    (root / "uv.lock").write_text("lock\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "dspy-lm-auth"\nversion = "9.9.9"\n', encoding="utf-8"
    )
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
    }
    for command in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "pin"]):
        subprocess.run(["git", "-C", str(root), *command], check=True, env=env)
    pins = collect_pins(root)
    block = render_pin_block(pins)
    assert pins["dirty"] is False
    assert block.startswith(f'OWNER_COMMIT = "{pins["commit"]}"')
    assert f'OWNER_TREE = "{pins["tree"]}"' in block
    assert 'OWNER_VERSION = "9.9.9"' in block
    assert f'OWNER_LOCK_SHA256 = "{hashlib.sha256(b"lock\n").hexdigest()}"' in block
    for name in _OWNER_MODULES:
        assert f'    "{name}": (' in block
    for relative in _EXTRA_OWNER_FILES:
        assert f'    "{relative}": "' in block


def test_pinned_owner_block_matches_fork_checkout_when_available() -> None:
    if not (FORK_ROOT / ".git").exists():
        pytest.skip("maintained dspy-lm-auth fork checkout is not available")
    pins = collect_pins(FORK_ROOT)
    # File hashes are stable across docs-only fork commits; commit/tree are
    # only asserted when the checkout sits on the pinned owner commit.
    assert pins["lock_sha256"] == OWNER_LOCK_SHA256
    assert pins["modules"] == _OWNER_MODULES
    assert pins["extra_files"] == _EXTRA_OWNER_FILES
    if pins["commit"] == OWNER_COMMIT:
        assert pins["tree"] == OWNER_TREE
