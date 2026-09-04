# summary: "Credential-free tests for the loopback local vLLM foundry jury provider family."
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import dspy
import pytest
from typer.testing import CliRunner

import dspx.services.program_foundry_gepa_comparison_jury as comparison_jury
import dspx.services.program_foundry_gepa_comparison_jury_receipt_validation as receipt_validation
import dspx.services.program_model_jury_provider_runtime as jury_runtime
from dspx.cli.dspx import app
from dspx.provider_registry import SUPPORTED_PROVIDER_NAMES
from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
    CODEX_FAMILY,
    COPILOT_FAMILY,
    TASK_LOCAL_PROVIDER_NAMES,
    FoundryJuryProviderConfigurationError,
    FoundryJuryProviderFamily,
    family_for_provider,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (
    FAMILIES,
    LOCAL_VLLM_DEFAULT_ENDPOINT,
    LOCAL_VLLM_ENDPOINT_ENV,
    LOCAL_VLLM_FAMILY,
    OPENCODE_GO_FAMILY,
    XAI_FAMILY,
    family_for_request,
    loopback_endpoint_origin_sha256,
    validate_loopback_endpoint,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_metadata import (
    provider_metadata,
    validate_foundry_jury_provider_metadata,
)
from dspx.services.program_foundry_gepa_comparison_jury_result import (
    validate_task_local_jury_result,
)
from dspx.services.program_foundry_gepa_comparison_jury_runtime import (
    execution_request,
    make_task_local_runtime_binding,
    revalidate_execution_request,
    task_local_execution_request_keys,
    task_local_family,
)
from test_program_foundry_gepa_comparison_jury import (
    _fixture,
    _model_result,
    _sha256,
)
from test_program_foundry_gepa_comparison_jury_copilot import _completed_with
from test_program_foundry_gepa_comparison_jury_provider import _artifact
from test_program_foundry_gepa_comparison_jury_xai import (
    _ChatBackend,
    _ChatOwner,
    _custodian,
    _stub_owner_source,
    _validate,
    run_configured_jury,
)

LOCAL_MODEL = "local/Qwen3.8-27B-AEON-NVFP4-FP8"
DEFAULT_ENDPOINT = "http://127.0.0.1:2456/v1"
DEFAULT_ENDPOINT_ORIGIN_SHA256 = (
    "ba556a06889d35554dd17c01d1aa4f421082aefb8602d915919c4920872eb3bb"
)
ALT_ENDPOINT = "http://localhost:8000/v1"
# Receipt routes are bounded ids without "/"; the family projects "/" to ":".
ROUTE_MODEL = "local:Qwen3.8-27B-AEON-NVFP4-FP8"
REQUESTED_ROUTE = f"dspy-lm-auth:local-vllm:{ROUTE_MODEL}"
RESOLVED_ROUTE = f"openai:{ROUTE_MODEL}:chat"


@pytest.fixture(autouse=True)
def _in_process_jury(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run task-local juries in this process so patched fakes stay reachable."""

    monkeypatch.setattr(comparison_jury, "_CHILD_ARGV", None)


def _rule(hostname: str, port: int) -> str:
    canonical = json.dumps(
        {"scheme": "http", "hostname": hostname, "port": port},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(
        b"dspx-oracle-semantic-v11-endpoint-origin-v1\0" + canonical
    ).hexdigest()


def test_local_vllm_family_literals_are_pinned() -> None:
    assert LOCAL_VLLM_FAMILY.provider_name == "foundry-dspy-lm-auth-local-vllm"
    assert LOCAL_VLLM_FAMILY.auth_provider == "none"
    assert LOCAL_VLLM_FAMILY.default_model == LOCAL_MODEL
    assert LOCAL_VLLM_FAMILY.allowed_reasoning_efforts is None
    assert LOCAL_VLLM_FAMILY.default_reasoning_effort is None
    assert LOCAL_VLLM_FAMILY.execution_task_title == (
        "Execute one receipt-bound foundry comparison jury with dspy-lm-auth local vLLM"
    )
    assert LOCAL_VLLM_ENDPOINT_ENV == "DSPX_LOCAL_VLLM_BASE_URL"
    assert LOCAL_VLLM_DEFAULT_ENDPOINT == DEFAULT_ENDPOINT
    assert LOCAL_VLLM_FAMILY.endpoint_env == LOCAL_VLLM_ENDPOINT_ENV
    assert LOCAL_VLLM_FAMILY.endpoint_key == "local_vllm_base_url"
    assert LOCAL_VLLM_FAMILY.endpoint_origin == DEFAULT_ENDPOINT
    assert LOCAL_VLLM_FAMILY.endpoint_resolved is True
    assert LOCAL_VLLM_FAMILY.requested_route(LOCAL_MODEL) == REQUESTED_ROUTE
    assert LOCAL_VLLM_FAMILY.resolved_route(LOCAL_MODEL) == RESOLVED_ROUTE
    assert LOCAL_VLLM_FAMILY.requested_route("Qwen3-8B") == (
        "dspy-lm-auth:local-vllm:Qwen3-8B"
    )
    assert LOCAL_VLLM_FAMILY.resolved_route("Qwen3-8B") == "openai:Qwen3-8B:chat"
    assert LOCAL_VLLM_FAMILY.backend_module == "dspy_lm_auth.local_vllm_backend"
    assert LOCAL_VLLM_FAMILY.backend_class == "LocalVllmBackend"
    assert LOCAL_VLLM_FAMILY.contract_module == "dspy_lm_auth.chat_backend_contract"
    assert LOCAL_VLLM_FAMILY.message_class == "ChatBackendMessage"
    assert LOCAL_VLLM_FAMILY.request_class == "ChatBackendRequest"
    assert LOCAL_VLLM_FAMILY.response_class == "ChatBackendResponse"
    assert LOCAL_VLLM_FAMILY.allowed_roles == frozenset({"system", "user", "assistant"})
    assert LOCAL_VLLM_FAMILY.model_key == "model"
    assert LOCAL_VLLM_FAMILY.strict_observed_model is False
    assert family_for_provider(LOCAL_VLLM_FAMILY.provider_name) is LOCAL_VLLM_FAMILY
    assert FAMILIES[LOCAL_VLLM_FAMILY.provider_name] is LOCAL_VLLM_FAMILY
    assert LOCAL_VLLM_FAMILY.provider_name in TASK_LOCAL_PROVIDER_NAMES
    assert LOCAL_VLLM_FAMILY.provider_name not in SUPPORTED_PROVIDER_NAMES
    assert task_local_execution_request_keys(
        LOCAL_VLLM_FAMILY.provider_name
    ) == frozenset(
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
            "local_vllm_base_url",
        }
    )


def test_local_vllm_default_endpoint_origin_constant_binds_port() -> None:
    assert LOCAL_VLLM_FAMILY.endpoint_origin_sha256 == DEFAULT_ENDPOINT_ORIGIN_SHA256
    assert _rule("127.0.0.1", 2456) == DEFAULT_ENDPOINT_ORIGIN_SHA256
    assert loopback_endpoint_origin_sha256(DEFAULT_ENDPOINT) == (
        DEFAULT_ENDPOINT_ORIGIN_SHA256
    )
    assert loopback_endpoint_origin_sha256("http://127.0.0.1:2457/v1") == _rule(
        "127.0.0.1", 2457
    )
    assert loopback_endpoint_origin_sha256("http://127.0.0.1:2457/v1") != (
        DEFAULT_ENDPOINT_ORIGIN_SHA256
    )
    assert loopback_endpoint_origin_sha256("http://localhost:8000/v1") == _rule(
        "localhost", 8000
    )
    assert loopback_endpoint_origin_sha256("http://[::1]:2456/v1") == _rule("::1", 2456)
    with pytest.raises(ValueError):
        loopback_endpoint_origin_sha256("https://127.0.0.1:2456/v1")


@pytest.mark.parametrize(
    "model",
    [
        LOCAL_MODEL,
        "Qwen/Qwen3-8B",
        "grok-4.6",
        "gpt-5.4",
        "a",
        "0-model",
        "a" * 104,
        "org/sub-dir/model_v1.0",
    ],
)
def test_local_vllm_model_rule_accepts_served_model_ids(model: str) -> None:
    assert LOCAL_VLLM_FAMILY.model_allowed(model)
    assert len(LOCAL_VLLM_FAMILY.requested_route(model)) <= 128
    assert "/" not in LOCAL_VLLM_FAMILY.requested_route(model)


@pytest.mark.parametrize(
    "model",
    [
        "",
        "/Qwen3",
        "-model",
        ".model",
        "_model",
        "a b",
        "a:b",
        # Route ids are bounded to 128 chars by the receipt contract.
        "a" * 105,
        "a" * 129,
        "model\n",
        "modél",
        None,
        1,
    ],
)
def test_local_vllm_model_rule_rejects_other_ids(model: object) -> None:
    assert not LOCAL_VLLM_FAMILY.model_allowed(model)


def test_local_vllm_reasoning_effort_is_not_applicable() -> None:
    assert LOCAL_VLLM_FAMILY.reasoning_effort_allowed(None)
    assert not LOCAL_VLLM_FAMILY.reasoning_effort_allowed("xhigh")
    assert LOCAL_VLLM_FAMILY.resolve_reasoning_effort(None) is None
    assert LOCAL_VLLM_FAMILY.resolve_model(None) == LOCAL_MODEL


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:2456/v1",
        "http://127.0.0.1:1/v1",
        "http://127.0.0.1:65535/v1",
        "http://localhost:8000/v1",
        "http://[::1]:2456/v1",
    ],
)
def test_loopback_endpoint_validation_accepts_exact_loopback_forms(
    endpoint: str,
) -> None:
    assert validate_loopback_endpoint(endpoint) == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:2456/v1",
        "http://10.0.0.1:2456/v1",
        "http://192.168.1.2:2456/v1",
        "http://example.com:2456/v1",
        "http://127.0.0.1.example.com:2456/v1",
        "http://127.0.0.2:2456/v1",
        "http://127.1:2456/v1",
        "http://0.0.0.0:2456/v1",
        "http://::1:2456/v1",
        "http://[::1%eth0]:2456/v1",
        "http://LOCALHOST:2456/v1",
        "HTTP://127.0.0.1:2456/v1",
        "http://127.0.0.1/v1",
        "http://127.0.0.1:/v1",
        "http://127.0.0.1:0/v1",
        "http://127.0.0.1:80/v1",
        "http://127.0.0.1:65536/v1",
        "http://127.0.0.1:abc/v1",
        "http://127.0.0.1:2456",
        "http://127.0.0.1:2456/",
        "http://127.0.0.1:2456/v1/",
        "http://127.0.0.1:2456/v2",
        "http://127.0.0.1:2456/v1/chat/completions",
        "http://127.0.0.1:2456/v1?x=1",
        "http://127.0.0.1:2456/v1#frag",
        "http://user@127.0.0.1:2456/v1",
        "http://user:secret@127.0.0.1:2456/v1",
        "http://user:secret@localhost:2456/v1",
        "http://127.0.0.1:2456/v1 ",
        " http://127.0.0.1:2456/v1",
        "http://127.0.0.1:2456/v1\n",
        "http://127.0.0.1:2456/v1é",
        "127.0.0.1:2456/v1",
        "//127.0.0.1:2456/v1",
        "file:///v1",
        "",
        None,
        2456,
    ],
)
def test_loopback_endpoint_validation_rejects_non_loopback_forms(
    endpoint: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError):
        validate_loopback_endpoint(endpoint)
    if isinstance(endpoint, str):
        with pytest.raises(ValueError):
            LOCAL_VLLM_FAMILY.with_endpoint(endpoint)
        monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, endpoint)
        with pytest.raises(ValueError):
            LOCAL_VLLM_FAMILY.with_endpoint(None)


def test_with_endpoint_resolves_env_then_default_and_binds_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(LOCAL_VLLM_ENDPOINT_ENV, raising=False)
    assert LOCAL_VLLM_FAMILY.with_endpoint(None) is LOCAL_VLLM_FAMILY
    assert LOCAL_VLLM_FAMILY.with_endpoint(DEFAULT_ENDPOINT) is LOCAL_VLLM_FAMILY
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, ALT_ENDPOINT)
    resolved = LOCAL_VLLM_FAMILY.with_endpoint(None)
    assert resolved is not LOCAL_VLLM_FAMILY
    assert resolved.provider_name == LOCAL_VLLM_FAMILY.provider_name
    assert resolved.endpoint_origin == ALT_ENDPOINT
    assert resolved.endpoint_origin_sha256 == _rule("localhost", 8000)
    assert resolved.endpoint_key == "local_vllm_base_url"
    assert resolved.endpoint_resolved is True
    # An explicit endpoint wins over the environment.
    explicit = LOCAL_VLLM_FAMILY.with_endpoint("http://[::1]:2456/v1")
    assert explicit.endpoint_origin == "http://[::1]:2456/v1"
    assert explicit.endpoint_origin_sha256 == _rule("::1", 2456)
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, "https://127.0.0.1:2456/v1")
    with pytest.raises(ValueError, match="loopback"):
        LOCAL_VLLM_FAMILY.with_endpoint(None)
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, "http://user@127.0.0.1:2456/v1")
    with pytest.raises(ValueError, match="loopback"):
        LOCAL_VLLM_FAMILY.with_endpoint(None)
    for fixed in (CODEX_FAMILY, COPILOT_FAMILY, XAI_FAMILY):
        assert fixed.with_endpoint(None) is fixed
        with pytest.raises(ValueError, match="endpoint is fixed"):
            fixed.with_endpoint(DEFAULT_ENDPOINT)


def test_family_for_request_requires_retained_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, ALT_ENDPOINT)
    request = {
        "provider": LOCAL_VLLM_FAMILY.provider_name,
        "local_vllm_base_url": DEFAULT_ENDPOINT,
    }
    # The retained request, not the environment, binds the family.
    assert family_for_request(request) is LOCAL_VLLM_FAMILY
    other = family_for_request({**request, "local_vllm_base_url": ALT_ENDPOINT})
    assert other.endpoint_origin == ALT_ENDPOINT
    with pytest.raises(ValueError, match="endpoint is missing"):
        family_for_request({"provider": LOCAL_VLLM_FAMILY.provider_name})
    with pytest.raises(ValueError, match="endpoint is missing"):
        family_for_request({**request, "local_vllm_base_url": 2456})
    with pytest.raises(ValueError, match="loopback"):
        family_for_request({**request, "local_vllm_base_url": "http://10.0.0.1:1/v1"})
    assert family_for_request({"provider": "fixture-provider"}) is None
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="not bound"
    ):
        task_local_family({"provider": LOCAL_VLLM_FAMILY.provider_name})


def _request(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "provider": LOCAL_VLLM_FAMILY.provider_name,
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


def test_local_vllm_execution_request_records_env_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(LOCAL_VLLM_ENDPOINT_ENV, raising=False)
    request = _request(tmp_path)
    assert request["model"] == LOCAL_MODEL
    assert request["local_vllm_base_url"] == DEFAULT_ENDPOINT
    assert "codex_model" not in request
    assert "reasoning_effort" not in request
    assert set(request) == task_local_execution_request_keys(
        LOCAL_VLLM_FAMILY.provider_name
    )
    assert revalidate_execution_request(request) == request
    assert task_local_family(request) is LOCAL_VLLM_FAMILY
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, ALT_ENDPOINT)
    from_env = _request(tmp_path, model="Qwen/Qwen3-8B")
    assert from_env["local_vllm_base_url"] == ALT_ENDPOINT
    assert from_env["model"] == "Qwen/Qwen3-8B"
    bound = task_local_family(from_env)
    assert bound is not None
    assert bound.endpoint_origin == ALT_ENDPOINT
    assert bound.endpoint_origin_sha256 == _rule("localhost", 8000)
    explicit = _request(tmp_path, endpoint="http://[::1]:2456/v1")
    assert explicit["local_vllm_base_url"] == "http://[::1]:2456/v1"
    # Revalidation binds the retained endpoint regardless of the environment.
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, "http://10.0.0.1:2456/v1")
    assert revalidate_execution_request(request) == request
    assert revalidate_execution_request(from_env) == from_env
    assert revalidate_execution_request(explicit) == explicit


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:2456/v1",
        "http://10.0.0.1:2456/v1",
        "http://127.0.0.1:2456/v2",
        "http://user@127.0.0.1:2456/v1",
        "http://127.0.0.1/v1",
    ],
)
def test_local_vllm_execution_request_rejects_invalid_env_endpoint(
    endpoint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, endpoint)
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="loopback"
    ):
        _request(tmp_path)
    monkeypatch.delenv(LOCAL_VLLM_ENDPOINT_ENV, raising=False)
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="loopback"
    ):
        _request(tmp_path, endpoint=endpoint)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"model": "/Qwen3"}, "requires owner source"),
        ({"model": "a b"}, "requires owner source"),
        ({"reasoning_effort": "xhigh"}, "requires owner source"),
        ({"codex_model": "gpt-5.4"}, "codex_model is only"),
        ({"execution_task_id": 5308}, "requires owner source"),
    ],
)
def test_local_vllm_execution_request_rejects_invalid_inputs(
    overrides: dict[str, Any],
    match: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(LOCAL_VLLM_ENDPOINT_ENV, raising=False)
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match=match
    ):
        _request(tmp_path, **overrides)
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="only valid"
    ):
        execution_request(
            provider="fixture-provider",
            adjudicator_id="local",
            adjudicator_kind="local",
            adjudicator_repo=None,
            max_jurors=1,
            endpoint=DEFAULT_ENDPOINT,
        )


def test_local_vllm_revalidate_rejects_missing_or_drifted_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(LOCAL_VLLM_ENDPOINT_ENV, raising=False)
    request = _request(tmp_path)
    missing = {k: v for k, v in request.items() if k != "local_vllm_base_url"}
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="types are invalid"
    ):
        revalidate_execution_request(missing)
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="types are invalid"
    ):
        revalidate_execution_request({**request, "local_vllm_base_url": 2456})
    for drifted in ("http://10.0.0.1:2456/v1", "https://127.0.0.1:2456/v1"):
        with pytest.raises(
            comparison_jury.ProgramFoundryGepaComparisonJuryError, match="loopback"
        ):
            revalidate_execution_request({**request, "local_vllm_base_url": drifted})
    xai = {**request, "provider": XAI_FAMILY.provider_name, "model": "grok-4.6"}
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="types are invalid"
    ):
        revalidate_execution_request(xai)


def test_local_vllm_comparison_jury_cli_forwards_provider_and_model(
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
            "foundry-dspy-lm-auth-local-vllm",
            "--owner-source-root",
            str(owner_root),
            "--execution-task-id",
            "6000",
            "--execution-claimant",
            "pi:test",
            "--model",
            "local/Qwen3.8-27B-AEON-NVFP4-FP8",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "consumption_receipt_path": receipt,
            "provider": "foundry-dspy-lm-auth-local-vllm",
            "adjudicator_id": "local_foundry_adjudicator",
            "adjudicator_kind": "local_foundry_adjudicator",
            "adjudicator_repo": None,
            "max_jurors": None,
            "owner_source_root": owner_root,
            "execution_task_id": 6000,
            "execution_claimant": "pi:test",
            "codex_model": None,
            "reasoning_effort": None,
            "model": "local/Qwen3.8-27B-AEON-NVFP4-FP8",
        }
    ]


def test_local_vllm_comparison_jury_binds_endpoint_into_attempt_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, ALT_ENDPOINT)
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
        provider=LOCAL_VLLM_FAMILY.provider_name,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
        max_jurors=1,
    )
    assert payload["status"] == "ok"
    assert payload["effect"]["ak_called"] is True
    assert payload["execution_request"]["model"] == LOCAL_MODEL
    assert payload["execution_request"]["local_vllm_base_url"] == ALT_ENDPOINT
    assert "reasoning_effort" not in payload["execution_request"]
    assert isinstance(
        calls[0]["provider_runtime_binding"],
        jury_runtime.ProgramModelJuryProviderRuntimeBinding,
    )
    experiment = Path(str(validated["experiment_root"]))
    attempt = json.loads(
        (experiment / "comparison-jury-attempt.json").read_text(encoding="utf-8")
    )
    assert attempt["execution_request"]["local_vllm_base_url"] == ALT_ENDPOINT
    # A different environment no longer matches the retained attempt/receipt.
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, DEFAULT_ENDPOINT)
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="drifted"
    ):
        comparison_jury.execute_program_foundry_gepa_comparison_jury(
            consumption_receipt_path=receipt,
            provider=LOCAL_VLLM_FAMILY.provider_name,
            owner_source_root=owner_root,
            execution_task_id=6000,
            execution_claimant="pi:test",
            max_jurors=1,
        )
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, ALT_ENDPOINT)
    reused = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider=LOCAL_VLLM_FAMILY.provider_name,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
        max_jurors=1,
    )
    assert reused["reused"] is True
    assert len(calls) == 1


def test_runtime_binding_factory_configures_resolved_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(LOCAL_VLLM_ENDPOINT_ENV, raising=False)
    request = _request(tmp_path, endpoint=ALT_ENDPOINT)
    seen: list[dict[str, Any]] = []

    def configure(**kwargs: Any) -> Any:
        seen.append(kwargs)
        return object()

    monkeypatch.setattr(
        "dspx.services.program_foundry_gepa_comparison_jury_runtime.configure_foundry_jury_provider",
        configure,
    )
    binding = make_task_local_runtime_binding(
        request=request, experiment_root=tmp_path, attempt_sha256="b" * 64
    )
    assert binding is not None
    binding.factory([{"id": "quality", "perspective": "quality"}])
    family = seen[0]["family"]
    assert family.provider_name == LOCAL_VLLM_FAMILY.provider_name
    assert family.endpoint_origin == ALT_ENDPOINT
    assert family.endpoint_origin_sha256 == _rule("localhost", 8000)
    assert seen[0]["model"] == LOCAL_MODEL
    assert seen[0]["reasoning_effort"] is None


def test_local_vllm_metadata_binds_endpoint_origin_and_hash() -> None:
    artifact = _artifact()
    family = LOCAL_VLLM_FAMILY.with_endpoint(ALT_ENDPOINT)
    metadata = provider_metadata(
        family=family,
        model=LOCAL_MODEL,
        reasoning_effort=None,
        timeout_seconds=60.0,
        execution_task_id=6000,
        execution_claimant="pi:test",
        source_identity=artifact.source_identity,
        dependency_identity=artifact.dependency_identity,
    )
    assert metadata["provider"] == LOCAL_VLLM_FAMILY.provider_name
    assert metadata["auth_provider"] == "none"
    assert metadata["endpoint_origin"] == ALT_ENDPOINT
    assert metadata["endpoint_origin_sha256"] == _rule("localhost", 8000)
    assert metadata["requested_route"] == REQUESTED_ROUTE
    assert metadata["resolved_route"] == RESOLVED_ROUTE
    validated = validate_foundry_jury_provider_metadata(
        metadata,
        execution_task_id=6000,
        execution_claimant="pi:test",
        model=LOCAL_MODEL,
        reasoning_effort=None,
        family=family,
    )
    assert validated == metadata
    for other in (LOCAL_VLLM_FAMILY, XAI_FAMILY, COPILOT_FAMILY, CODEX_FAMILY):
        with pytest.raises(FoundryJuryProviderConfigurationError, match="drifted"):
            validate_foundry_jury_provider_metadata(
                metadata,
                execution_task_id=6000,
                execution_claimant="pi:test",
                model=LOCAL_MODEL,
                reasoning_effort=None,
                family=other,
            )


def test_local_vllm_custodian_binds_resolved_origin_into_journals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    family = LOCAL_VLLM_FAMILY.with_endpoint(ALT_ENDPOINT)
    custodian = _custodian(tmp_path, family, LOCAL_MODEL)
    for juror_id, semantic in (("quality", "c" * 64), ("authority", "d" * 64)):
        custodian.invoke(
            juror_id=juror_id,
            semantic_request_sha256=semantic,
            invoke=_completed_with(LOCAL_MODEL),
        )
    evidence = custodian.finalize()
    assert evidence["session_disposition"] == "complete"
    assert evidence["call_records"][0]["observed_model"] == LOCAL_MODEL
    journal = sorted((tmp_path / "provider-outcomes").iterdir())[0]
    wrapper = json.loads((journal / "reservation.json").read_text("utf-8"))
    reservation = wrapper["reservation"]
    assert reservation["endpoint_origin_sha256"] == _rule("localhost", 8000)
    assert reservation["requested_route"] == REQUESTED_ROUTE
    _stub_owner_source(monkeypatch)
    assert _validate(evidence, tmp_path, family, LOCAL_MODEL) == evidence
    for other in (LOCAL_VLLM_FAMILY, XAI_FAMILY, COPILOT_FAMILY):
        with pytest.raises(
            FoundryJuryProviderConfigurationError, match="journal binding drifted"
        ):
            _validate(evidence, tmp_path, other, LOCAL_MODEL)


class _LocalVllmBackend(_ChatBackend):
    """Fake LocalVllmBackend: positional base_url, no credential file."""

    observed_model = LOCAL_MODEL
    constructed: list[Any] = []

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        validate_loopback_endpoint(base_url)
        self.base_url = base_url
        self.api_key = api_key
        self.extra_body = extra_body
        type(self).constructed.append(self)


def test_local_vllm_construct_backend_hook_passes_bound_endpoint_only() -> None:
    owner = _ChatOwner(_LocalVllmBackend)
    _LocalVllmBackend.constructed.clear()
    default = LOCAL_VLLM_FAMILY.construct_backend(owner)
    assert type(default) is _LocalVllmBackend
    assert default.base_url == DEFAULT_ENDPOINT
    assert default.api_key is None and default.extra_body is None
    resolved = LOCAL_VLLM_FAMILY.with_endpoint(ALT_ENDPOINT)
    bound = resolved.construct_backend(owner, endpoint=ALT_ENDPOINT)
    assert bound.base_url == ALT_ENDPOINT
    with pytest.raises(ValueError, match="endpoint drifted"):
        resolved.construct_backend(owner, endpoint=DEFAULT_ENDPOINT)
    with pytest.raises(ValueError, match="reads no credential"):
        LOCAL_VLLM_FAMILY.construct_backend(owner, auth_path="/tmp/auth.json")
    assert len(_LocalVllmBackend.constructed) == 2


def test_local_vllm_family_runs_end_to_end_through_configure_adapter_and_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, ALT_ENDPOINT)
    family = LOCAL_VLLM_FAMILY.with_endpoint(None)
    assert family.endpoint_origin == ALT_ENDPOINT
    previous_lm = getattr(dspy.settings, "lm", None)
    _LocalVllmBackend.constructed.clear()
    metadata, result, evidence, _ = run_configured_jury(
        tmp_path,
        monkeypatch,
        family=family,
        backend_type=_LocalVllmBackend,
        model=LOCAL_MODEL,
    )
    assert getattr(dspy.settings, "lm", None) is previous_lm
    assert result["outcome"] == "supports_review_evidence"
    backend = _LocalVllmBackend.constructed[-1]
    assert backend.base_url == ALT_ENDPOINT
    assert backend.api_key is None
    request = backend.requests[0]
    assert request.model == LOCAL_MODEL
    assert request.timeout_seconds == 60.0
    assert not hasattr(request, "reasoning_effort")
    assert {m.role for m in request.messages} <= {"system", "user", "assistant"}
    assert metadata["provider"] == LOCAL_VLLM_FAMILY.provider_name
    assert metadata["auth_provider"] == "none"
    assert metadata["endpoint_origin"] == ALT_ENDPOINT
    assert metadata["endpoint_origin_sha256"] == _rule("localhost", 8000)
    assert validate_foundry_jury_provider_metadata(
        metadata,
        execution_task_id=6000,
        execution_claimant="pi:test",
        model=LOCAL_MODEL,
        reasoning_effort=None,
        family=family,
    )
    assert evidence["session_disposition"] == "complete"
    record = evidence["call_records"][0]
    assert record["semantic_request_sha256"] == backend.semantic_hashes[0]
    assert record["observed_model"] == LOCAL_MODEL
    journal = sorted((tmp_path / "provider-outcomes").iterdir())[0]
    wrapper = json.loads((journal / "reservation.json").read_text("utf-8"))
    reservation = wrapper["reservation"]
    assert reservation["endpoint_origin_sha256"] == _rule("localhost", 8000)
    assert reservation["resolved_route"] == RESOLVED_ROUTE
    _stub_owner_source(monkeypatch)
    assert _validate(evidence, tmp_path, family, LOCAL_MODEL, ("quality",)) == evidence
    # Retained result validation rebinds the endpoint from the request, so the
    # default-endpoint family (a different origin hash) no longer validates.
    with pytest.raises(
        FoundryJuryProviderConfigurationError, match="journal binding drifted"
    ):
        _validate(evidence, tmp_path, LOCAL_VLLM_FAMILY, LOCAL_MODEL, ("quality",))


def test_task_local_result_validation_rebinds_endpoint_from_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, ALT_ENDPOINT)
    family = LOCAL_VLLM_FAMILY.with_endpoint(None)
    _LocalVllmBackend.constructed.clear()
    metadata, judgment, evidence, _ = run_configured_jury(
        tmp_path,
        monkeypatch,
        family=family,
        backend_type=_LocalVllmBackend,
        model=LOCAL_MODEL,
    )
    _stub_owner_source(monkeypatch)
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    (candidate_dir / "jury_selection.json").write_text(
        json.dumps({"selected_jurors": [{"id": "quality", "perspective": "quality"}]}),
        encoding="utf-8",
    )
    result_path = tmp_path / "comparison-jury-results.json"
    result = {
        "jury": {"provider_outcome_evidence": evidence, "provider_config": metadata},
        "juror_results": [
            {
                "juror_id": "quality",
                "perspective": "quality",
                "provider": LOCAL_VLLM_FAMILY.provider_name,
                "model": LOCAL_MODEL,
                "status": "judged",
                "judgment": judgment,
            }
        ],
    }
    request = _request(tmp_path, endpoint=ALT_ENDPOINT)
    validated = {"candidate_manifest_path": str(candidate_dir / "manifest.json")}
    monkeypatch.delenv(LOCAL_VLLM_ENDPOINT_ENV, raising=False)
    validate_task_local_jury_result(
        result=result,
        result_path=result_path,
        validated=validated,
        request=request,
        attempt_sha256="a" * 64,
    )
    drifted = {**request, "local_vllm_base_url": DEFAULT_ENDPOINT}
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="drifted"
    ):
        validate_task_local_jury_result(
            result=result,
            result_path=result_path,
            validated=validated,
            request=drifted,
            attempt_sha256="a" * 64,
        )
    missing = {k: v for k, v in request.items() if k != "local_vllm_base_url"}
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError, match="not bound"
    ):
        validate_task_local_jury_result(
            result=result,
            result_path=result_path,
            validated=validated,
            request=missing,
            attempt_sha256="a" * 64,
        )


def test_local_vllm_family_is_distinct_from_the_other_families() -> None:
    families: tuple[FoundryJuryProviderFamily, ...] = (
        CODEX_FAMILY,
        COPILOT_FAMILY,
        XAI_FAMILY,
        OPENCODE_GO_FAMILY,
        LOCAL_VLLM_FAMILY,
    )
    assert len({f.provider_name for f in families}) == 5
    assert len({f.execution_task_title for f in families}) == 5
    assert len({f.requested_route("m") for f in families}) == 5
    assert len({f.backend_module for f in families}) == 5
    assert len({f.endpoint_origin_sha256 for f in families}) == 5
    assert [f.endpoint_resolved for f in families] == [
        False,
        False,
        False,
        False,
        True,
    ]
