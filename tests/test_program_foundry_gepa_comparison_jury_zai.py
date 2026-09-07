# summary: "Credential-free tests for the Z.ai Coding Plan foundry jury provider family."
from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import dspy
import pytest
from dspy import BaseLM
from typer.testing import CliRunner

import dspx.services.program_foundry_gepa_comparison_jury as comparison_jury
import dspx.services.program_foundry_gepa_comparison_jury_preflight as preflight
import dspx.services.program_foundry_gepa_comparison_jury_receipt_validation as receipt_validation
import dspx.services.program_foundry_gepa_comparison_jury_provider as provider_module
import dspx.services.program_model_jury_provider_runtime as jury_runtime
from dspx.cli.dspx import app
from dspx.provider_registry import SUPPORTED_PROVIDER_NAMES
from dspx.services.program_foundry_gepa_comparison_jury_owner import (
    _EXTRA_OWNER_FILES,
    OWNER_COMMIT,
    OWNER_LOCK_SHA256,
    OWNER_TREE,
    OWNER_VERSION,
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
    AUTH_MODE_NONE,
    AUTH_MODE_PI_API_KEY,
    AUTH_MODE_PI_OAUTH,
    FAMILIES,
    LOCAL_VLLM_FAMILY,
    ZAI_ENDPOINT_ORIGIN,
    ZAI_FAMILY,
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
from test_program_foundry_gepa_comparison_jury_preflight import _Catalog, _serve
from test_program_foundry_gepa_comparison_jury_provider import _Owner, _artifact
from test_program_foundry_gepa_comparison_jury_xai import (
    _ChatMessage,
    _ChatOwner,
    _ChatRequest,
    _LoadedOwnerArtifact,
    _XaiBackend,
    run_configured_jury,
)

ALL_FAMILIES = (
    CODEX_FAMILY,
    COPILOT_FAMILY,
    XAI_FAMILY,
    ZAI_FAMILY,
    LOCAL_VLLM_FAMILY,
)
GO_MODEL = "glm-5.3"
GO_ENDPOINT_ORIGIN_SHA256 = (
    "784fab9bbd73a8bc4fd132a14aa3a30437e9d94c19ffc8cbd24854c0a02f07d9"
)
GO_OBSERVED = "glm-5.3-0904"
SECRET = "sk-zai-SECRET-0123456789"
FAKE_CREDENTIAL_MODULE = "# fake owner _chat_credential.py; never loaded by the probe\n"


@pytest.fixture(autouse=True)
def _in_process_jury(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run task-local juries in this process so patched fakes stay reachable."""

    monkeypatch.setattr(comparison_jury, "_CHILD_ARGV", None)


@pytest.fixture
def go_catalog_server() -> Iterator[tuple[_Catalog, str]]:
    catalog = _Catalog(
        200, json.dumps({"data": [{"id": GO_MODEL}, {"id": "glm-5.3-flash"}]}).encode()
    )
    generator = _serve(catalog)
    base = next(generator)
    try:
        yield catalog, base
    finally:
        next(generator, None)


def _other(family: FoundryJuryProviderFamily) -> FoundryJuryProviderFamily:
    index = ALL_FAMILIES.index(family)
    return ALL_FAMILIES[(index + 1) % len(ALL_FAMILIES)]


# --- family literals ------------------------------------------------------------


def test_zai_family_literals_are_pinned() -> None:
    assert ZAI_FAMILY.provider_name == "foundry-dspy-lm-auth-zai"
    assert ZAI_FAMILY.auth_provider == "zai"
    assert ZAI_FAMILY.auth_mode == AUTH_MODE_PI_API_KEY == "pi-api-key"
    assert ZAI_FAMILY.model_re.pattern == r"^glm-[a-z0-9][a-z0-9.-]{0,63}$"
    assert ZAI_FAMILY.default_model == GO_MODEL
    assert ZAI_FAMILY.allowed_reasoning_efforts is None
    assert ZAI_FAMILY.default_reasoning_effort is None
    assert ZAI_FAMILY.execution_task_title == (
        "Execute one receipt-bound foundry comparison jury with dspy-lm-auth "
        "Z.ai Coding Plan"
    )
    assert ZAI_FAMILY.endpoint_origin == ZAI_ENDPOINT_ORIGIN
    assert ZAI_ENDPOINT_ORIGIN == "https://api.z.ai"
    assert ZAI_FAMILY.catalog_path == "/api/coding/paas/v4/models"
    assert ZAI_FAMILY.catalog_url == "https://api.z.ai/api/coding/paas/v4/models"
    assert ZAI_FAMILY.requested_route(GO_MODEL) == "dspy-lm-auth:zai:glm-5.3"
    assert ZAI_FAMILY.resolved_route(GO_MODEL) == "openai:glm-5.3:chat"
    assert ZAI_FAMILY.backend_module == "dspy_lm_auth.zai_backend"
    assert ZAI_FAMILY.backend_class == "ZaiBackend"
    assert ZAI_FAMILY.contract_module == "dspy_lm_auth.chat_backend_contract"
    assert (
        ZAI_FAMILY.message_class,
        ZAI_FAMILY.request_class,
        ZAI_FAMILY.response_class,
    ) == ("ChatBackendMessage", "ChatBackendRequest", "ChatBackendResponse")
    assert ZAI_FAMILY.allowed_roles == frozenset({"system", "user", "assistant"})
    assert ZAI_FAMILY.model_key == "model"
    assert ZAI_FAMILY.strict_observed_model is False
    assert ZAI_FAMILY.endpoint_env is None
    assert ZAI_FAMILY.endpoint_key is None
    assert ZAI_FAMILY.endpoint_resolved is False
    assert ZAI_FAMILY.default_timeout_seconds == 180.0
    assert family_for_provider(ZAI_FAMILY.provider_name) is ZAI_FAMILY
    assert FAMILIES[ZAI_FAMILY.provider_name] is ZAI_FAMILY
    assert ZAI_FAMILY.provider_name in TASK_LOCAL_PROVIDER_NAMES
    assert len(TASK_LOCAL_PROVIDER_NAMES) == 6
    assert ZAI_FAMILY.provider_name not in SUPPORTED_PROVIDER_NAMES
    assert task_local_execution_request_keys(ZAI_FAMILY.provider_name) == frozenset(
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


def test_auth_modes_are_pinned_per_family() -> None:
    assert [family.auth_mode for family in ALL_FAMILIES] == [
        AUTH_MODE_PI_OAUTH,
        AUTH_MODE_PI_OAUTH,
        AUTH_MODE_PI_OAUTH,
        AUTH_MODE_PI_API_KEY,
        AUTH_MODE_NONE,
    ]
    assert (AUTH_MODE_PI_OAUTH, AUTH_MODE_PI_API_KEY, AUTH_MODE_NONE) == (
        "pi-oauth-no-refresh",
        "pi-api-key",
        "none",
    )


def test_zai_endpoint_origin_constant_uses_the_v11_rule() -> None:
    canonical = json.dumps(
        {"scheme": "https", "hostname": "api.z.ai"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected = hashlib.sha256(
        b"dspx-oracle-semantic-v11-endpoint-origin-v1\0" + canonical
    ).hexdigest()
    assert ZAI_FAMILY.endpoint_origin_sha256 == GO_ENDPOINT_ORIGIN_SHA256 == expected
    # The owner's fixed api_base carries the path; the origin hash ignores it.
    assert endpoint_origin_sha256("https://api.z.ai/api/coding/paas/v4") == expected
    assert endpoint_origin_sha256(ZAI_FAMILY.endpoint_origin) == expected
    assert len({family.endpoint_origin_sha256 for family in ALL_FAMILIES}) == 5


@pytest.mark.parametrize(
    "model",
    [
        "glm-5.3",
        "glm-5.3-flash",
        "glm-5.3-highspeed",
        "glm-5.2",
        "glm-5-turbo",
        "glm-4.7",
    ],
)
def test_zai_model_rule_accepts_lowercase_vendor_neutral_ids(
    model: str,
) -> None:
    assert ZAI_FAMILY.model_allowed(model)


@pytest.mark.parametrize(
    "model",
    [
        "Kimi-K2.7-Code",
        "-kimi",
        ".kimi",
        "kimi k2",
        "kimi_k2",
        "local/Qwen3.8-27B-AEON-NVFP4-FP8",
        "kimi:k2",
        "a" * 65,
        "",
        None,
        2.7,
    ],
)
def test_zai_model_rule_rejects_other_ids(model: object) -> None:
    assert not ZAI_FAMILY.model_allowed(model)


def test_zai_reasoning_effort_is_not_applicable() -> None:
    assert ZAI_FAMILY.reasoning_effort_allowed(None)
    assert not ZAI_FAMILY.reasoning_effort_allowed("xhigh")
    assert ZAI_FAMILY.resolve_reasoning_effort(None) is None
    assert ZAI_FAMILY.resolve_model(None) == GO_MODEL
    assert ZAI_FAMILY.resolve_model("glm-5.3") == "glm-5.3"


def test_zai_endpoint_is_fixed() -> None:
    assert ZAI_FAMILY.with_endpoint(None) is ZAI_FAMILY
    with pytest.raises(ValueError, match="endpoint is fixed"):
        ZAI_FAMILY.with_endpoint("https://api.z.ai")
    assert family_for_request({"provider": ZAI_FAMILY.provider_name}) is ZAI_FAMILY


# --- revalidator, custodian, metadata ------------------------------------------


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


def test_zai_custodian_binds_routes_and_origin_into_journals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custodian = _custodian(tmp_path, ZAI_FAMILY, GO_MODEL)
    for juror_id, semantic in (("quality", "c" * 64), ("authority", "d" * 64)):
        custodian.invoke(
            juror_id=juror_id,
            semantic_request_sha256=semantic,
            invoke=_completed_with(GO_OBSERVED),
        )
    evidence = custodian.finalize()
    assert evidence["session_disposition"] == "complete"
    assert [item["observed_model"] for item in evidence["call_records"]] == [
        GO_OBSERVED,
        GO_OBSERVED,
    ]
    _stub_owner_source(monkeypatch)
    assert _validate(evidence, tmp_path, ZAI_FAMILY, GO_MODEL) == evidence
    for other in (CODEX_FAMILY, COPILOT_FAMILY, XAI_FAMILY, LOCAL_VLLM_FAMILY):
        with pytest.raises(
            FoundryJuryProviderConfigurationError, match="journal binding drifted"
        ):
            _validate(evidence, tmp_path, other, GO_MODEL)


def test_zai_provider_metadata_validates_and_rejects_other_families() -> None:
    artifact = _artifact()
    metadata = provider_metadata(
        family=ZAI_FAMILY,
        model=GO_MODEL,
        reasoning_effort=None,
        timeout_seconds=180.0,
        execution_task_id=6000,
        execution_claimant="pi:test",
        source_identity=artifact.source_identity,
        dependency_identity=artifact.dependency_identity,
    )
    assert metadata["provider"] == ZAI_FAMILY.provider_name
    assert metadata["auth_provider"] == "zai"
    assert metadata["credential_mode"] == "no-refresh"
    assert metadata["timeout_seconds"] == 180.0
    assert metadata["requested_route"] == "dspy-lm-auth:zai:glm-5.3"
    assert metadata["resolved_route"] == "openai:glm-5.3:chat"
    assert metadata["owner_commit"] == OWNER_COMMIT
    assert "endpoint_origin" not in metadata
    assert "endpoint_origin_sha256" not in metadata
    assert (
        validate_foundry_jury_provider_metadata(
            metadata,
            execution_task_id=6000,
            execution_claimant="pi:test",
            model=GO_MODEL,
            reasoning_effort=None,
            family=ZAI_FAMILY,
        )
        == metadata
    )
    for other in ALL_FAMILIES:
        if other is ZAI_FAMILY:
            continue
        with pytest.raises(FoundryJuryProviderConfigurationError, match="drifted"):
            validate_foundry_jury_provider_metadata(
                metadata,
                execution_task_id=6000,
                execution_claimant="pi:test",
                model=GO_MODEL,
                reasoning_effort=None,
                family=other,
            )


# --- execution request ----------------------------------------------------------


def _request(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "provider": ZAI_FAMILY.provider_name,
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


def test_zai_execution_request_uses_model_key_without_effort_or_endpoint(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    assert request["model"] == GO_MODEL
    assert "codex_model" not in request
    assert "reasoning_effort" not in request
    assert "local_vllm_base_url" not in request
    assert set(request) == task_local_execution_request_keys(ZAI_FAMILY.provider_name)
    assert revalidate_execution_request(request) == request
    assert task_local_family(request) is ZAI_FAMILY
    explicit = _request(tmp_path, model="glm-5.3")
    assert explicit["model"] == "glm-5.3"
    assert revalidate_execution_request(explicit) == explicit


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"model": "Kimi-K2.7-Code"}, "requires owner source"),
        ({"model": "local/Qwen3.8-27B-AEON-NVFP4-FP8"}, "requires owner source"),
        ({"reasoning_effort": "xhigh"}, "requires owner source"),
        ({"codex_model": "gpt-5.4"}, "codex_model is only"),
        ({"endpoint": "https://api.z.ai/api/coding/paas/v4"}, "loopback"),
        ({"execution_task_id": 5308}, "requires owner source"),
    ],
)
def test_zai_execution_request_rejects_invalid_inputs(
    overrides: dict[str, Any], match: str, tmp_path: Path
) -> None:
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match=match
    ):
        _request(tmp_path, **overrides)


def test_zai_revalidate_rejects_foreign_keys(tmp_path: Path) -> None:
    request = _request(tmp_path)
    for key, value in (
        ("reasoning_effort", "xhigh"),
        ("local_vllm_base_url", "http://127.0.0.1:2456/v1"),
        ("codex_model", GO_MODEL),
    ):
        drifted = {**request, key: value}
        with pytest.raises(
            comparison_jury.ProgramFoundryGepaComparisonJuryError,
            match="types are invalid",
        ):
            revalidate_execution_request(drifted)
    drifted = {**request, "model": "Kimi-K2.7-Code"}
    with pytest.raises(comparison_jury.ProgramFoundryGepaComparisonJuryError):
        revalidate_execution_request(drifted)


# --- CLI ------------------------------------------------------------------------


def test_zai_comparison_jury_cli_forwards_provider_and_model(
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
            "foundry-dspy-lm-auth-zai",
            "--owner-source-root",
            str(owner_root),
            "--execution-task-id",
            "6000",
            "--execution-claimant",
            "pi:test",
            "--model",
            "glm-5.3",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "consumption_receipt_path": receipt,
            "provider": "foundry-dspy-lm-auth-zai",
            "adjudicator_id": "local_foundry_adjudicator",
            "adjudicator_kind": "local_foundry_adjudicator",
            "adjudicator_repo": None,
            "max_jurors": None,
            "owner_source_root": owner_root,
            "execution_task_id": 6000,
            "execution_claimant": "pi:test",
            "codex_model": None,
            "reasoning_effort": None,
            "model": "glm-5.3",
        }
    ]
    help_result = CliRunner().invoke(
        app, ["program-refine", "jury-foundry-gepa-comparison", "--help"]
    )
    assert help_result.exit_code == 0
    compact = "".join(help_result.output.split())
    assert "foundry-dspy-lm-auth-zai" in compact
    for name in TASK_LOCAL_PROVIDER_NAMES:
        assert name in compact


def test_zai_comparison_jury_binds_runtime_and_records_model_key(
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
        execution_repo_root=tmp_path,
        consumption_receipt_path=receipt,
        provider=ZAI_FAMILY.provider_name,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
        max_jurors=1,
    )
    assert payload["status"] == "ok"
    assert payload["effect"]["ak_called"] is True
    assert payload["execution_request"]["provider"] == ZAI_FAMILY.provider_name
    assert payload["execution_request"]["model"] == GO_MODEL
    assert "reasoning_effort" not in payload["execution_request"]
    assert calls[0]["provider"] == ZAI_FAMILY.provider_name
    assert isinstance(
        calls[0]["provider_runtime_binding"],
        jury_runtime.ProgramModelJuryProviderRuntimeBinding,
    )
    reused = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        execution_repo_root=tmp_path,
        consumption_receipt_path=receipt,
        provider=ZAI_FAMILY.provider_name,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
        max_jurors=1,
    )
    assert reused["reused"] is True
    assert len(calls) == 1


# --- credential-free end to end -------------------------------------------------


class _ZaiBackend(_XaiBackend):
    """Fake ZaiBackend: keyword-only auth_path, fixed endpoint, api_key."""

    observed_model = GO_OBSERVED
    constructed: list[Any] = []


def test_zai_construct_backend_hook_uses_keyword_auth_path_only() -> None:
    owner = _ChatOwner(_ZaiBackend)
    _ZaiBackend.constructed.clear()
    default = ZAI_FAMILY.construct_backend(owner)
    assert type(default) is _ZaiBackend
    assert default.auth_path == "<default-pi-auth>"
    explicit = ZAI_FAMILY.construct_backend(owner, auth_path="/tmp/auth.json")
    assert explicit.auth_path == "/tmp/auth.json"
    same = ZAI_FAMILY.construct_backend(owner, endpoint="https://api.z.ai")
    assert type(same) is _ZaiBackend
    with pytest.raises(ValueError, match="endpoint is fixed"):
        ZAI_FAMILY.construct_backend(
            owner, endpoint="https://api.z.ai/api/coding/paas/v4"
        )
    assert len(_ZaiBackend.constructed) == 3


def test_zai_build_backend_request_omits_effort_and_format() -> None:
    owner = _ChatOwner(_ZaiBackend)
    request = ZAI_FAMILY.build_backend_request(
        owner,
        model=GO_MODEL,
        messages=(_ChatMessage("user", "hi"),),
        reasoning_effort=None,
        timeout_seconds=180.0,
    )
    assert type(request) is _ChatRequest
    assert request.model == GO_MODEL
    assert request.timeout_seconds == 180.0
    assert not hasattr(request, "reasoning_effort")
    assert not hasattr(request, "response_format")


def test_zai_family_runs_end_to_end_through_configure_adapter_and_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous_lm = getattr(dspy.settings, "lm", None)
    previous_adapter = getattr(dspy.settings, "adapter", None)
    _ZaiBackend.constructed.clear()
    metadata, result, evidence, _ = run_configured_jury(
        tmp_path,
        monkeypatch,
        family=ZAI_FAMILY,
        backend_type=_ZaiBackend,
        model=GO_MODEL,
    )
    assert getattr(dspy.settings, "lm", None) is previous_lm
    assert getattr(dspy.settings, "adapter", None) is previous_adapter
    assert result["outcome"] == "supports_review_evidence"
    backend = _ZaiBackend.constructed[-1]
    assert type(backend) is _ZaiBackend
    assert backend.auth_path == "<default-pi-auth>"
    request = backend.requests[0]
    assert request.model == GO_MODEL
    assert request.timeout_seconds == 180.0
    assert metadata["timeout_seconds"] == 180.0
    assert not hasattr(request, "reasoning_effort")
    assert not hasattr(request, "response_format")
    assert metadata["provider"] == ZAI_FAMILY.provider_name
    assert metadata["model"] == GO_MODEL
    assert metadata["auth_provider"] == "zai"
    assert metadata["reasoning_effort"] is None
    assert "endpoint_origin_sha256" not in metadata
    assert validate_foundry_jury_provider_metadata(
        metadata,
        execution_task_id=6000,
        execution_claimant="pi:test",
        model=GO_MODEL,
        reasoning_effort=None,
        family=ZAI_FAMILY,
    )
    assert evidence["session_disposition"] == "complete"
    record = evidence["call_records"][0]
    assert record["semantic_request_sha256"] == backend.semantic_hashes[0]
    assert record["observed_model"] == GO_OBSERVED
    _stub_owner_source(monkeypatch)
    validated = _validate(evidence, tmp_path, ZAI_FAMILY, GO_MODEL, ("quality",))
    assert validated == evidence
    journal = sorted((tmp_path / "provider-outcomes").iterdir())[0]
    wrapper = json.loads((journal / "reservation.json").read_text("utf-8"))
    reservation = wrapper["reservation"]
    assert reservation["endpoint_origin_sha256"] == GO_ENDPOINT_ORIGIN_SHA256
    assert reservation["requested_route"] == "dspy-lm-auth:zai:glm-5.3"
    assert reservation["resolved_route"] == "openai:glm-5.3:chat"


def test_zai_configure_rejects_invalid_model_or_timeout_before_owner_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def verify(root: Path, bound: FoundryJuryProviderFamily) -> Any:
        raise AssertionError("owner must not load for a rejected configuration")

    monkeypatch.setattr(provider_module, "verify_loaded_foundry_jury_owner", verify)
    for model, effort in (("Kimi-K2.7-Code", None), (GO_MODEL, "xhigh")):
        with pytest.raises(FoundryJuryProviderConfigurationError, match="zai"):
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
                family=ZAI_FAMILY,
            )
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
            timeout_seconds=60.0,
            family=ZAI_FAMILY,
        )


# --- preflight credential probe (api_key entry) ---------------------------------


def _fake_owner(tmp_path: Path) -> tuple[Path, str, str]:
    """Fake owner root with an auth.py (never loaded here) and a credential module."""

    root = tmp_path / "owner"
    package = root / "src" / "dspy_lm_auth"
    package.mkdir(parents=True, exist_ok=True)
    auth = package / "auth.py"
    auth.write_text("raise RuntimeError('auth.py must not load for api_key')\n")
    credential = package / "_chat_credential.py"
    credential.write_text(FAKE_CREDENTIAL_MODULE, encoding="utf-8")
    return (
        root,
        hashlib.sha256(auth.read_bytes()).hexdigest(),
        hashlib.sha256(credential.read_bytes()).hexdigest(),
    )


def _api_key_auth_json(tmp_path: Path, entry: dict[str, Any] | None) -> Path:
    path = tmp_path / "auth.json"
    payload = {} if entry is None else {"zai": entry}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _api_key_probe_config(
    tmp_path: Path,
    *,
    catalog_url: str | None,
    entry: dict[str, Any] | None = None,
    model: str = GO_MODEL,
) -> dict[str, Any]:
    root, auth_digest, credential_digest = _fake_owner(tmp_path)
    if entry is None:
        entry = {"type": "api_key", "key": SECRET}
    return {
        "auth_provider": "zai",
        "auth_mode": "pi-api-key",
        "model": model,
        "catalog_url": catalog_url,
        "auth_module_path": str(root / "src" / "dspy_lm_auth" / "auth.py"),
        "auth_module_sha256": auth_digest,
        "auth_path": str(_api_key_auth_json(tmp_path, entry)),
        "credential_module_path": str(
            root / "src" / "dspy_lm_auth" / "_chat_credential.py"
        ),
        "credential_module_sha256": credential_digest,
    }


def test_preflight_probe_config_carries_credential_module_only_for_api_key(
    tmp_path: Path,
) -> None:
    go = preflight._probe_config(
        ZAI_FAMILY, owner_source_root=tmp_path, model=GO_MODEL, auth_path=None
    )
    assert go["auth_mode"] == "pi-api-key"
    assert go["auth_provider"] == "zai"
    assert go["catalog_url"] == "https://api.z.ai/api/coding/paas/v4/models"
    assert go["credential_module_path"] == str(
        tmp_path / "src/dspy_lm_auth/_chat_credential.py"
    )
    assert (
        go["credential_module_sha256"]
        == _EXTRA_OWNER_FILES["src/dspy_lm_auth/_chat_credential.py"]
    )
    assert go["auth_module_sha256"] == _EXTRA_OWNER_FILES["src/dspy_lm_auth/auth.py"]
    xai = preflight._probe_config(
        XAI_FAMILY, owner_source_root=tmp_path, model="grok-4.6", auth_path=None
    )
    assert xai["auth_mode"] == "pi-oauth-no-refresh"
    assert "credential_module_path" not in xai
    assert "credential_module_sha256" not in xai
    vllm = preflight._probe_config(
        LOCAL_VLLM_FAMILY, owner_source_root=tmp_path, model="local/q", auth_path=None
    )
    assert vllm["auth_mode"] == "none"


def test_api_key_probe_reports_booleans_and_never_returns_the_key(
    tmp_path: Path, go_catalog_server: tuple[_Catalog, str]
) -> None:
    catalog, base = go_catalog_server
    config = _api_key_probe_config(tmp_path, catalog_url=base + "/models")
    facts = preflight.run_probe(config)
    encoded = json.dumps(facts)
    assert SECRET not in encoded
    assert set(facts) == {
        "credential_present",
        "expiry_ok",
        "expires_ms",
        "endpoint_fixed",
        "catalog",
    }
    assert facts["credential_present"] is True
    assert facts["expiry_ok"] is True
    assert facts["endpoint_fixed"] is True
    assert facts["expires_ms"] == 0
    assert facts["catalog"]["status_class"] == "2xx"
    assert facts["catalog"]["catalog_count"] == 2
    assert facts["catalog"]["model_listed"] is True
    method, path, headers = catalog.requests[0]
    assert (method, path) == ("GET", "/v1/models")
    assert headers["Authorization"] == f"Bearer {SECRET}"
    assert headers["Accept-Encoding"] == "identity"
    assert "Copilot-Integration-Id" not in headers
    assert len(catalog.requests) == 1


@pytest.mark.parametrize(
    "entry",
    [
        None,
        {"type": "oauth", "access": SECRET, "expires": 4_000_000_000_000},
        {"type": "api_key"},
        {"type": "api_key", "key": ""},
        {"type": "api_key", "key": "not printable é"},
        {"type": "api_key", "key": "with space"},
        {"type": "api_key", "key": 42},
    ],
    ids=("absent", "oauth_typed", "no_key", "empty", "non_ascii", "space", "int"),
)
def test_api_key_probe_reports_missing_credential_without_catalog(
    tmp_path: Path, entry: dict[str, Any] | None
) -> None:
    config = _api_key_probe_config(tmp_path, catalog_url="http://127.0.0.1:9/models")
    _api_key_auth_json(tmp_path, entry)
    facts = preflight.run_probe(config)
    assert facts["credential_present"] is False
    assert facts["expiry_ok"] is False
    assert facts["endpoint_fixed"] is False
    assert facts["expires_ms"] == 0
    assert facts["catalog"] is None


def test_api_key_probe_fails_closed_on_credential_module_hash_drift(
    tmp_path: Path,
) -> None:
    config = _api_key_probe_config(tmp_path, catalog_url=None)
    config["credential_module_sha256"] = "0" * 64
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="probe failed closed",
    ):
        preflight.run_probe(config)
    missing = _api_key_probe_config(tmp_path, catalog_url=None)
    Path(missing["credential_module_path"]).unlink()
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="probe failed closed",
    ):
        preflight.run_probe(missing)


def test_api_key_probe_fails_closed_on_unknown_auth_mode(tmp_path: Path) -> None:
    config = _api_key_probe_config(tmp_path, catalog_url=None)
    config["auth_mode"] = "env"
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="probe failed closed",
    ):
        preflight.run_probe(config)


def test_zai_probe_through_family_binds_owner_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    go_catalog_server: tuple[_Catalog, str],
) -> None:
    catalog, base = go_catalog_server
    root, _auth_digest, credential_digest = _fake_owner(tmp_path)
    auth_path = _api_key_auth_json(tmp_path, {"type": "api_key", "key": SECRET})
    monkeypatch.setattr(preflight, "_OWNER_CREDENTIAL_SHA256", credential_digest)
    # Point the fixed family's listing at the loopback catalog; the origin hash
    # is irrelevant to the probe, which only composes ``catalog_url``.
    family = replace(
        ZAI_FAMILY,
        endpoint_origin=base.removesuffix("/v1"),
        catalog_path="/v1/models",
    )
    seen: list[dict[str, Any]] = []
    real_run_probe = preflight.run_probe

    def spy(config: dict[str, Any]) -> dict[str, Any]:
        seen.append(dict(config))
        return real_run_probe(config)

    monkeypatch.setattr(preflight, "run_probe", spy)
    credential, facts = preflight.probe_credential_and_catalog(
        family, owner_source_root=root, model=GO_MODEL, auth_path=auth_path
    )
    assert seen[0]["auth_mode"] == "pi-api-key"
    assert seen[0]["credential_module_sha256"] == credential_digest
    assert credential == {
        "probed": True,
        "credential_present": True,
        "expiry_ok": True,
        "expires_ms": 0,
        "endpoint_fixed": True,
    }
    assert facts["checked"] is True
    assert facts["model_listed"] is True
    assert facts["catalog_count"] == 2
    assert catalog.requests[0][2]["Authorization"] == f"Bearer {SECRET}"
    _api_key_auth_json(tmp_path, None)
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="zai credential is absent, expired, or misrouted",
    ):
        preflight.probe_credential_and_catalog(
            family, owner_source_root=root, model=GO_MODEL, auth_path=auth_path
        )
    assert len(catalog.requests) == 1


# --- loaded owner and runtime binding ------------------------------------------


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


def test_loaded_owner_rules_bind_the_zai_backend_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    family = ZAI_FAMILY
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_owner.verify_foundry_jury_owner_source",
        lambda root: {},
    )
    expected = tmp_path / "src" / "dspy_lm_auth" / "zai_backend.py"
    expected.parent.mkdir(parents=True, exist_ok=True)
    expected.write_text("class ZaiBackend: ...\n", encoding="utf-8")
    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_owner.inspect.getsourcefile",
        lambda item: str(expected),
    )
    exact = type("ZaiBackend", (), {"__module__": family.backend_module})
    assert "dspy_lm_auth.lm" not in sys.modules
    _loaded_owner(family, exact, tmp_path).revalidate()
    for other in ALL_FAMILIES:
        if other is family:
            continue
        foreign = type(other.backend_class, (), {"__module__": other.backend_module})
        with pytest.raises(ProviderOutcomeConsumerError) as foreign_drift:
            _loaded_owner(family, foreign, tmp_path).revalidate()
        assert foreign_drift.value.reason == "loaded_owner_backend_type_drift"
    renamed = type("ZaiOtherBackend", (), {"__module__": family.backend_module})
    with pytest.raises(ProviderOutcomeConsumerError) as rename_drift:
        _loaded_owner(family, renamed, tmp_path).revalidate()
    assert rename_drift.value.reason == "loaded_owner_backend_type_drift"
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


def test_runtime_binding_accepts_six_task_local_provider_names() -> None:
    assert sorted(TASK_LOCAL_PROVIDER_NAMES) == [
        "foundry-dspy-lm-auth-codex",
        "foundry-dspy-lm-auth-github-copilot",
        "foundry-dspy-lm-auth-local-vllm",
        "foundry-dspy-lm-auth-opencode-go",
        "foundry-dspy-lm-auth-xai",
        "foundry-dspy-lm-auth-zai",
    ]
    for provider in sorted(TASK_LOCAL_PROVIDER_NAMES):
        runtimes: list[_FakeRuntime] = []

        def factory(selected: Any, provider: str = provider) -> _FakeRuntime:
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
    with pytest.raises(
        jury_runtime.ProgramModelJuryExecutionError, match="restricted to the foundry"
    ):
        run_program_model_jurors(
            selected=[],
            rubrics={},
            candidate_identity={},
            evidence_json="{}",
            adjudicator={},
            provider="zai",
            configure_provider=lambda name: {},
            run_juror=lambda **kwargs: {},
            sanitize_diagnostic=lambda exc: "",
            provider_runtime_binding=_bind_program_model_jury_provider_runtime(
                lambda selected: _FakeRuntime("x")
            ),
        )


# --- owner repin ----------------------------------------------------------------


def test_owner_is_repinned_to_the_zai_fork_commit() -> None:
    assert OWNER_COMMIT == "6c3473ca17bf03325698e3e1a8419a8abc915938"
    assert OWNER_TREE == "dc9098779ec5b500d82ed914d8bba7857d276b85"
    assert OWNER_VERSION == "0.1.6"
    assert OWNER_LOCK_SHA256 == (
        "d24ee392e2846b3baac33e16a67ff3e9094b3b021c67e32e50a1f1d11b077648"
    )
    for relative in (
        "src/dspy_lm_auth/zai_backend.py",
        "src/dspy_lm_auth/_chat_credential.py",
        "src/dspy_lm_auth/chat_backend_contract.py",
        "src/dspy_lm_auth/chat_backend.py",
        "src/dspy_lm_auth/auth.py",
    ):
        assert relative in REQUIRED_EXTRA_OWNER_FILES
        assert relative in _EXTRA_OWNER_FILES
    assert _EXTRA_OWNER_FILES["src/dspy_lm_auth/zai_backend.py"] == (
        "c993c6bbea73f153fbc8a82b6fc86d602349f5a6e9039b00016cd9a0552cac35"
    )
    assert missing_required_extra_files() == ()
