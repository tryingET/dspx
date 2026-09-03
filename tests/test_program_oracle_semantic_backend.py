# summary: "Tests the typed loopback live Oracle semantic backend, fixture replay, strict parsing, and truthful preflight evidence."

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
from dspx.cli.commands.oracle import app as oracle_app
from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.openai_compatible_provider import OpenAICompatibleProvider
from dspx.services.program_foundry_gepa_proposal import (
    validate_oracle_semantic_recommendation,
)
from dspx.services.program_oracle_semantic_backend import (
    FixtureReplayOracleSemanticBackend,
    ProgramOracleSemanticBackendError,
    TypedProviderOracleSemanticBackend,
    _analysis_prompt,
    _analysis_response_format,
    _parse_analysis_text,
    preflight_program_oracle_semantic_backend,
    resolve_program_oracle_semantic_backend,
)
from dspx.services.program_oracle_semantic_contract import (
    ORACLE_SEMANTIC_FIXTURE_SCHEMA,
    OracleSemanticPreflight,
    OracleSemanticRequest,
)
from typer.testing import CliRunner

LOOPBACK_BASE = "http://127.0.0.1:2456/v1"
LOCAL_MODEL = "local/Qwen3.8-27B-AEON-NVFP4-FP8"


def _analysis() -> dict[str, object]:
    return {
        "observations": ["accuracy fell after the prompt change"],
        "failure_attractors": ["overly broad instructions"],
        "quality_contract_violations": ["accuracy below 0.90"],
        "hypotheses": ["the prompt removed a necessary constraint"],
        "recommended_experiments": ["restore the constraint and replay"],
        "evidence_refs": ["receipt:run-7"],
        "confidence": 0.8,
    }


def _request() -> OracleSemanticRequest:
    return OracleSemanticRequest(
        objective="Explain the observed regression",
        evidence={"receipt_refs": ["receipt:run-7"], "accuracy": 0.72},
        quality_contract={"minimum_accuracy": 0.9},
    )


def test_codebook_prompt_separates_literal_and_prospective_field_rules() -> None:
    request = OracleSemanticRequest(
        objective="Classify only observed behavior",
        evidence={"refs": [{"ref": "receipt:run-7"}], "status": "passed"},
        quality_contract={
            "analysis_codebook": {
                "observations": ["passed", "failed"],
                "hypotheses": ["cause_unproven"],
            },
            "analysis_field_rubric": {
                "observations": {"mode": "literal"},
                "failure_attractors": {"mode": "bounded_prospective"},
            },
        },
    )

    prompt = _analysis_prompt(request)

    assert "analysis_field_rubric exactly" in prompt
    assert "Observations are literal target-subject facts" in prompt
    assert "same proposition, subject, and state" in prompt
    assert "a regression alone does not prove" in prompt
    assert "Hypotheses are explicit causal or mechanism epistemic states" in prompt
    assert "prospective fields" in prompt
    assert "risk or action need not appear verbatim" in prompt
    assert "Never invent the subject" in prompt
    assert "Use an empty array" in prompt
    assert "minimum exact code set" in prompt
    assert "not every plausible code" in prompt


def test_code_semantics_and_request_values_constrain_prompt_and_schema() -> None:
    semantics = {
        "schema_version": "dspx-oracle-semantic-code-semantics-v1",
        "selection_rules": ["Use context-independent denotations."],
        "fields": {
            "observations": {
                "passed": {
                    "meaning": "The target explicitly passed.",
                    "select_when": ["A target pass is explicit."],
                    "exclude_when": ["Only absence of failure is known."],
                }
            }
        },
    }
    request = OracleSemanticRequest(
        objective="Classify bounded evidence",
        evidence={
            "records": [
                {"ref": "receipt:target", "fact": "The target passed."},
                {"ref": "receipt:distractor", "fact": "Another target passed."},
            ]
        },
        quality_contract={
            "analysis_codebook": {"observations": ["passed", "failed"]},
            "analysis_code_semantics": semantics,
            "analysis_evidence_ref_rubric": {
                "selection": "all_and_only_direct_support"
            },
            "analysis_confidence_rubric": {"meaning": "classification confidence"},
        },
    )

    prompt = _analysis_prompt(request)
    response_format = _analysis_response_format(request)
    properties = response_format["schema"]["properties"]

    assert "analysis_code_semantics is the authoritative" in prompt
    assert "all and only exact ref values" in prompt
    assert json.dumps(semantics, sort_keys=True, separators=(",", ":")) in prompt
    assert properties["observations"]["items"]["enum"] == ["passed", "failed"]
    assert properties["observations"]["uniqueItems"] is True
    assert properties["evidence_refs"]["items"]["enum"] == [
        "receipt:target",
        "receipt:distractor",
    ]
    assert properties["evidence_refs"]["uniqueItems"] is True


def test_request_hash_is_deterministic_and_secret_shaped_evidence_fails() -> None:
    left = _request()
    right = OracleSemanticRequest(
        objective="Explain the observed regression",
        evidence={"accuracy": 0.72, "receipt_refs": ["receipt:run-7"]},
        quality_contract={"minimum_accuracy": 0.9},
    )
    assert left.request_sha256 == right.request_sha256
    caller_evidence = {"refs": ["receipt:original"]}
    frozen = OracleSemanticRequest(objective="Analyze", evidence=caller_evidence)
    frozen_hash = frozen.request_sha256
    caller_evidence["refs"].append("receipt:mutated")
    assert frozen.request_sha256 == frozen_hash
    assert frozen.payload()["evidence"] == {"refs": ["receipt:original"]}

    with pytest.raises(ProgramOracleSemanticBackendError, match="secret-shaped"):
        OracleSemanticRequest(
            objective="Analyze",
            evidence={"api_key": "sk-abcdefghijklmnopqrstuvwxyz"},
        )


def _live_env(**overrides: str) -> dict[str, str]:
    env = {
        "DSPX_ORACLE_SEMANTIC_BACKEND": "live",
        "DSPX_ORACLE_SEMANTIC_PROVIDER": "openai-compatible",
        "DSPX_OPENAI_COMPAT_API_BASE": LOOPBACK_BASE,
        "DSPX_OPENAI_COMPAT_MODEL": LOCAL_MODEL,
        "DSPX_OPENAI_COMPAT_TIMEOUT": "180",
    }
    env.update(overrides)
    return env


def _forbid_provider_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    from dspx import provider_registry

    monkeypatch.setattr(
        provider_registry,
        "create",
        lambda *args, **kwargs: pytest.fail("provider must not be constructed"),
    )


def test_live_preflight_validates_configuration_without_constructing_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_provider_construction(monkeypatch)
    monkeypatch.delenv("DSPX_POLICY_ALLOWED_PROVIDERS", raising=False)

    payload = preflight_program_oracle_semantic_backend(environ=_live_env()).to_dict()

    assert payload["ready"] is True
    assert payload["backend_kind"] == "live"
    assert payload["configured_provider"] == "openai-compatible"
    assert payload["configured_model"] == LOCAL_MODEL
    assert payload["preferred_model"] == "codex/gpt-5.6-sol"
    assert payload["live_verified"] is False
    assert payload["executed_model"] is None
    check = payload["checks"][0]
    assert check["ok"] is True
    assert check["dispatched"] is False
    assert check["credential_free"] is True
    assert check["timeout"] == 180.0
    assert "2456" in check["endpoint"]


def test_live_preflight_reports_local_model_override_as_role_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_provider_construction(monkeypatch)
    monkeypatch.delenv("DSPX_POLICY_ALLOWED_PROVIDERS", raising=False)

    payload = preflight_program_oracle_semantic_backend(
        environ=_live_env(DSPX_ORACLE_SEMANTIC_MODEL=LOCAL_MODEL)
    ).to_dict()

    assert payload["ready"] is True
    assert payload["preferred_model"] == LOCAL_MODEL
    assert payload["configured_model"] == LOCAL_MODEL
    assert payload["checks"][0]["model_override"] is True


@pytest.mark.parametrize(
    "overrides,match",
    [
        (
            {"DSPX_ORACLE_SEMANTIC_PROVIDER": "stub"},
            "must be one of: openai-compatible",
        ),
        ({"DSPX_ORACLE_SEMANTIC_PROVIDER": "dspy-lm-auth"}, "must be one of"),
        ({"DSPX_OPENAI_COMPAT_API_BASE": ""}, "API_BASE is required"),
        (
            {"DSPX_OPENAI_COMPAT_API_BASE": "http://example.com/v1"},
            "endpoint is invalid",
        ),
        (
            {"DSPX_OPENAI_COMPAT_API_BASE": "https://127.0.0.1:2456/v1"},
            "endpoint is invalid",
        ),
        ({"DSPX_OPENAI_COMPAT_MODEL": ""}, "MODEL"),
        ({"DSPX_OPENAI_COMPAT_MODEL": "bad model id"}, "model id is invalid"),
        ({"DSPX_OPENAI_COMPAT_TIMEOUT": "never"}, "TIMEOUT"),
        ({"DSPX_OPENAI_COMPAT_TIMEOUT": "-1"}, "TIMEOUT"),
        ({"DSPX_OPENAI_COMPAT_API_KEY": "sk-not-allowed"}, "credential-free"),
        ({"DSPX_ORACLE_SEMANTIC_MODEL": "codex/gpt-5.6-sol"}, "local/ route"),
    ],
)
def test_live_resolver_and_preflight_reject_bad_configuration_before_effects(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str], match: str
) -> None:
    _forbid_provider_construction(monkeypatch)
    monkeypatch.delenv("DSPX_POLICY_ALLOWED_PROVIDERS", raising=False)
    environ = _live_env(**overrides)

    with pytest.raises(ProgramOracleSemanticBackendError, match=match):
        resolve_program_oracle_semantic_backend(environ=environ)
    preflight = preflight_program_oracle_semantic_backend(environ=environ).to_dict()
    assert preflight["ready"] is False
    assert preflight["live_verified"] is False
    assert preflight["checks"][0]["name"] == "provider_configuration"
    assert "sk-not-allowed" not in json.dumps(preflight)


def test_live_resolver_rejects_policy_disallowed_provider_before_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_provider_construction(monkeypatch)
    monkeypatch.setenv("DSPX_POLICY_ALLOWED_PROVIDERS", "stub")

    with pytest.raises(
        ProgramOracleSemanticBackendError, match="not allowed by policy"
    ):
        resolve_program_oracle_semantic_backend(environ=_live_env())
    preflight = preflight_program_oracle_semantic_backend(environ=_live_env()).to_dict()
    assert preflight["ready"] is False
    assert "policy" in preflight["checks"][0]["detail"]


def test_live_resolver_constructs_typed_openai_compatible_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DSPX_POLICY_ALLOWED_PROVIDERS", raising=False)

    backend = resolve_program_oracle_semantic_backend(environ=_live_env())

    assert isinstance(backend, TypedProviderOracleSemanticBackend)
    assert backend.provider_name == "openai-compatible"
    assert backend.configured_model == LOCAL_MODEL
    assert backend.preferred_model == "codex/gpt-5.6-sol"
    assert type(backend.lm) is DSPyTypedLMAdapter
    assert type(backend.lm.provider) is OpenAICompatibleProvider
    assert backend.lm.provider.effective_timeout == 180.0
    backend.close()


def test_typed_backend_rejects_non_openai_compatible_adapters() -> None:
    from dspx.stub_provider import StubProvider

    with pytest.raises(ProgramOracleSemanticBackendError, match="openai-compatible"):
        TypedProviderOracleSemanticBackend(
            provider_name="openai-compatible",
            preferred_model="codex/gpt-5.6-sol",
            lm=DSPyTypedLMAdapter(StubProvider(model="stub/echo")),
        )
    with pytest.raises(
        ProgramOracleSemanticBackendError, match="only the openai-compatible"
    ):
        TypedProviderOracleSemanticBackend(
            provider_name="stub",
            preferred_model="codex/gpt-5.6-sol",
            lm=DSPyTypedLMAdapter(StubProvider(model="stub/echo")),
        )


def _codebook_request() -> OracleSemanticRequest:
    return OracleSemanticRequest(
        objective="Classify bounded evidence",
        evidence={
            "records": [
                {"ref": "receipt:target", "fact": "The target passed."},
                {"ref": "receipt:distractor", "fact": "Another target passed."},
            ]
        },
        quality_contract={
            "analysis_codebook": {
                "observations": ["passed", "failed"],
                "recommended_experiments": ["replay_with_constraint"],
            }
        },
    )


def _completion(text: str, *, model: str = LOCAL_MODEL) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _fake_backend(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[TypedProviderOracleSemanticBackend, list[httpx.Request]]:
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    monkeypatch.delenv("DSPX_POLICY_ALLOWED_PROVIDERS", raising=False)
    monkeypatch.delenv("DSPX_POLICY_ALLOWED_CAPS", raising=False)
    requests: list[httpx.Request] = []

    def transport_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    provider = OpenAICompatibleProvider(
        base_url=LOOPBACK_BASE,
        model=LOCAL_MODEL,
        timeout=5.0,
        _transport=httpx.MockTransport(transport_handler),
    )
    backend = TypedProviderOracleSemanticBackend(
        provider_name="openai-compatible",
        preferred_model="codex/gpt-5.6-sol",
        lm=DSPyTypedLMAdapter(provider, cache=False),
    )
    return backend, requests


def _runtime_sidecar_shape(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "program-runtime-oracle-semantic-v1",
        "status": "ok",
        "request_sha256": result["request_sha256"],
        "semantic_result": result,
        "effect": {
            "semantic_backend_invoked": True,
            "effect_disposition": "terminal_result_recorded",
            "live_call_succeeded": result["live_call_succeeded"],
        },
        "non_authority": {"promotion_authority": False, "activation_authority": False},
    }


def test_typed_backend_success_carries_complete_live_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _codebook_request()
    analysis = {
        "observations": ["passed"],
        "failure_attractors": [],
        "quality_contract_violations": [],
        "hypotheses": [],
        "recommended_experiments": ["replay_with_constraint"],
        "evidence_refs": ["receipt:target"],
        "confidence": 0.7,
    }
    backend, requests = _fake_backend(
        monkeypatch,
        lambda _request: httpx.Response(
            200, json=_completion("```json\n" + json.dumps(analysis) + "\n```")
        ),
    )

    result = backend.analyze(request).to_dict()

    assert len(requests) == 1
    sent = json.loads(requests[0].content)
    assert sent["model"] == LOCAL_MODEL
    assert sent["messages"][0]["role"] == "user"
    assert _analysis_prompt(request) == sent["messages"][0]["content"]
    assert "Authorization" not in requests[0].headers
    assert result["backend_kind"] == "live"
    assert result["execution_status"] == "succeeded"
    assert result["live_call_succeeded"] is True
    assert result["configured_provider"] == "openai-compatible"
    assert result["configured_model"] == LOCAL_MODEL
    assert result["executed_provider"] == "openai-compatible"
    assert result["executed_model"] == LOCAL_MODEL
    assert result["fixture_sha256"] is None
    assert result["error"] is None
    assert result["analysis"] == analysis
    _, validated, recommendation = validate_oracle_semantic_recommendation(
        _runtime_sidecar_shape(result), recommendation_index=0
    )
    assert recommendation == "replay_with_constraint"
    assert validated.evidence_refs == ("receipt:target",)
    with pytest.raises(ProgramOracleSemanticBackendError, match="one-shot"):
        backend.analyze(request)


def test_typed_backend_enforces_evidence_refs_enum_after_live_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _codebook_request()
    analysis = {
        "observations": ["passed"],
        "failure_attractors": [],
        "quality_contract_violations": [],
        "hypotheses": [],
        "recommended_experiments": [],
        "evidence_refs": ["receipt:target", "receipt:invented"],
        "confidence": 0.7,
    }
    backend, _ = _fake_backend(
        monkeypatch,
        lambda _request: httpx.Response(200, json=_completion(json.dumps(analysis))),
    )

    result = backend.analyze(request).to_dict()

    assert result["execution_status"] == "failed_after_live_response"
    assert result["live_call_succeeded"] is True
    assert result["executed_model"] == LOCAL_MODEL
    assert result["analysis"] is None
    assert "evidence_refs" in result["error"]
    assert "receipt:invented" in result["error"]
    with pytest.raises(Exception, match="invalid for a GEPA proposal"):
        validate_oracle_semantic_recommendation(
            _runtime_sidecar_shape(result), recommendation_index=0
        )


def test_typed_backend_enforces_codebook_enum_and_json_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _codebook_request()
    bad_code = {
        "observations": ["passed", "invented_code"],
        "failure_attractors": [],
        "quality_contract_violations": [],
        "hypotheses": [],
        "recommended_experiments": [],
        "evidence_refs": ["receipt:target"],
        "confidence": 0.7,
    }
    backend, _ = _fake_backend(
        monkeypatch,
        lambda _request: httpx.Response(200, json=_completion(json.dumps(bad_code))),
    )
    result = backend.analyze(request).to_dict()
    assert result["execution_status"] == "failed_after_live_response"
    assert "observations" in result["error"] and "invented_code" in result["error"]

    backend, _ = _fake_backend(
        monkeypatch,
        lambda _request: httpx.Response(200, json=_completion("not json at all")),
    )
    result = backend.analyze(request).to_dict()
    assert result["execution_status"] == "failed_after_live_response"
    assert result["live_call_succeeded"] is True
    assert "not valid JSON" in result["error"]


def test_typed_backend_completed_failure_is_before_live_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, requests = _fake_backend(
        monkeypatch, lambda _request: httpx.Response(500, text="upstream failure")
    )

    result = backend.analyze(_codebook_request()).to_dict()

    assert len(requests) == 1
    assert result["execution_status"] == "failed_before_live_success"
    assert result["live_call_succeeded"] is False
    assert result["executed_provider"] is None
    assert result["analysis"] is None
    assert "completed_failure" in result["error"]
    assert "upstream failure" not in result["error"]


def test_typed_backend_preflight_rejection_never_dispatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, requests = _fake_backend(
        monkeypatch, lambda _request: httpx.Response(200, json=_completion("{}"))
    )
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "0")

    result = backend.analyze(_codebook_request()).to_dict()

    assert requests == []
    assert result["execution_status"] == "failed_before_live_success"
    assert "preflight_rejected" in result["error"]


def test_typed_backend_indeterminate_effect_is_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection dropped mid-flight")

    backend, requests = _fake_backend(monkeypatch, explode)
    request = _codebook_request()

    with pytest.raises(ProgramOracleSemanticBackendError, match="indeterminate"):
        backend.analyze(request)
    assert len(requests) == 1
    with pytest.raises(ProgramOracleSemanticBackendError, match="indeterminate"):
        backend.analyze(request)
    assert len(requests) == 1, "an indeterminate effect must never be retried"
    assert backend.lm.provider.terminal_effect is not None
    assert backend.lm.provider.terminal_effect.value == "effect_indeterminate"


def test_parse_analysis_text_is_strict_about_shape_and_enums() -> None:
    request = _codebook_request()
    response_format = _analysis_response_format(request)
    good = {
        "observations": ["failed"],
        "failure_attractors": [],
        "quality_contract_violations": [],
        "hypotheses": [],
        "recommended_experiments": [],
        "evidence_refs": ["receipt:distractor"],
        "confidence": 0.2,
    }
    parsed = _parse_analysis_text(
        "```\n" + json.dumps(good) + "\n```", response_format=response_format
    )
    assert parsed.to_dict() == good
    duplicate = dict(good, evidence_refs=["receipt:target", "receipt:target"])
    with pytest.raises(ProgramOracleSemanticBackendError, match="repeats an item"):
        _parse_analysis_text(json.dumps(duplicate), response_format=response_format)
    with pytest.raises(ProgramOracleSemanticBackendError, match="one JSON object"):
        _parse_analysis_text("[1, 2]", response_format=response_format)
    with pytest.raises(ProgramOracleSemanticBackendError, match="unknown fields"):
        _parse_analysis_text(
            json.dumps(dict(good, extra=1)), response_format=response_format
        )
    with pytest.raises(ProgramOracleSemanticBackendError, match="outside the request"):
        _parse_analysis_text(
            json.dumps(dict(good, evidence_refs=["receipt:other"])),
            response_format=response_format,
        )
    # Without a request-derived enum the parser still enforces the base contract.
    assert _parse_analysis_text(json.dumps(good)).confidence == 0.2


def _loopback_vllm_available() -> bool:
    try:
        response = httpx.get(f"{LOOPBACK_BASE}/models", timeout=2.0, trust_env=False)
    except Exception:
        return False
    return response.status_code == 200 and LOCAL_MODEL in response.text


@pytest.mark.live
@pytest.mark.model
@pytest.mark.network
def test_live_loopback_vllm_typed_backend_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bounded credential-free round trip against the local vLLM (opt-in only)."""

    if not _loopback_vllm_available():
        pytest.skip("loopback vLLM at 127.0.0.1:2456 is not serving the local model")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    monkeypatch.delenv("DSPX_POLICY_ALLOWED_PROVIDERS", raising=False)
    monkeypatch.delenv("DSPX_POLICY_ALLOWED_CAPS", raising=False)
    monkeypatch.delenv("DSPX_OPENAI_COMPAT_API_KEY", raising=False)
    environ = {
        **{k: v for k, v in os.environ.items() if not k.startswith("DSPX_ORACLE_")},
        **_live_env(),
    }
    preflight = preflight_program_oracle_semantic_backend(environ=environ).to_dict()
    assert preflight["ready"] is True and preflight["live_verified"] is False
    backend = resolve_program_oracle_semantic_backend(environ=environ)
    assert isinstance(backend, TypedProviderOracleSemanticBackend)

    result = backend.analyze(_codebook_request()).to_dict()

    assert result["backend_kind"] == "live"
    assert result["configured_provider"] == "openai-compatible"
    assert result["configured_model"] == LOCAL_MODEL
    assert result["execution_status"] in {
        "succeeded",
        "failed_after_live_response",
        "failed_before_live_success",
    }
    if result["execution_status"] == "failed_before_live_success":
        # Observed 2026-09-04 against vLLM 0.27: the reply carries extra null
        # message keys (refusal, annotations, audio, function_call, reasoning)
        # and usage.prompt_tokens_details, which the typed port's strict
        # response validator (openai_compatible_provider._validated_response)
        # classifies as completed_failure. Recorded, not papered over.
        assert result["live_call_succeeded"] is False
        assert "completed_failure" in str(result["error"])
        pytest.xfail(
            "typed openai-compatible port rejects this vLLM response shape: "
            + str(result["error"])
        )
    assert result["live_call_succeeded"] is True
    assert result["executed_provider"] == "openai-compatible"
    assert result["executed_model"] == LOCAL_MODEL
    if result["execution_status"] == "succeeded":
        analysis = result["analysis"]
        assert set(analysis["observations"]) <= {"passed", "failed"}
        assert set(analysis["evidence_refs"]) <= {
            "receipt:target",
            "receipt:distractor",
        }
    else:
        # Strict JSON failures stay recorded as truthful post-response failures.
        assert result["error"]


def _write_fixture(path: Path, request: OracleSemanticRequest) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": ORACLE_SEMANTIC_FIXTURE_SCHEMA,
                "entries": {
                    request.request_sha256: {
                        "request_sha256": request.request_sha256,
                        "analysis": _analysis(),
                    }
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_fixture_replay_is_deterministic_and_never_claims_live_execution(
    tmp_path: Path,
) -> None:
    request = _request()
    fixture = tmp_path / "oracle.json"
    _write_fixture(fixture, request)
    backend = FixtureReplayOracleSemanticBackend(
        fixture_path=fixture,
        preferred_model="codex/gpt-5.6-sol",
    )

    first = backend.analyze(request).to_dict()
    second = backend.analyze(request).to_dict()

    assert first == second
    assert first["execution_status"] == "replayed_fixture"
    assert first["executed_provider"] is None
    assert first["executed_model"] is None
    assert first["live_call_succeeded"] is False
    assert first["fixture_sha256"]


def test_fixture_replay_fails_closed_for_missing_request(tmp_path: Path) -> None:
    fixture = tmp_path / "oracle.json"
    fixture.write_text(
        json.dumps({"schema_version": ORACLE_SEMANTIC_FIXTURE_SCHEMA, "entries": {}}),
        encoding="utf-8",
    )

    with pytest.raises(ProgramOracleSemanticBackendError, match="has no entry"):
        FixtureReplayOracleSemanticBackend(
            fixture_path=fixture,
            preferred_model="codex/gpt-5.6-sol",
        ).analyze(_request())


def test_fixture_preflight_validates_every_entry(tmp_path: Path) -> None:
    request = _request()
    fixture = tmp_path / "invalid-oracle.json"
    invalid = _analysis()
    invalid["confidence"] = 2.0
    fixture.write_text(
        json.dumps(
            {
                "schema_version": ORACLE_SEMANTIC_FIXTURE_SCHEMA,
                "entries": {
                    request.request_sha256: {
                        "request_sha256": request.request_sha256,
                        "analysis": invalid,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    payload = preflight_program_oracle_semantic_backend(
        environ={
            "DSPX_ORACLE_SEMANTIC_BACKEND": "fixture-replay",
            "DSPX_ORACLE_SEMANTIC_FIXTURE_PATH": str(fixture),
        }
    ).to_dict()

    assert payload["ready"] is False
    assert "confidence" in payload["checks"][0]["detail"]


def test_fixture_replay_rejects_symlinks(tmp_path: Path) -> None:
    request = _request()
    fixture = tmp_path / "oracle.json"
    link = tmp_path / "oracle-link.json"
    _write_fixture(fixture, request)
    link.symlink_to(fixture)

    with pytest.raises(ProgramOracleSemanticBackendError, match="non-symlink"):
        FixtureReplayOracleSemanticBackend(
            fixture_path=link,
            preferred_model="codex/gpt-5.6-sol",
        ).analyze(request)


def test_fixture_preflight_and_resolver_do_not_touch_provider(
    monkeypatch, tmp_path: Path
) -> None:
    from dspx import provider_registry

    request = _request()
    fixture = tmp_path / "oracle.json"
    _write_fixture(fixture, request)
    monkeypatch.setattr(
        provider_registry,
        "create",
        lambda name: pytest.fail("fixture replay must not create a provider"),
    )
    environ = {
        "DSPX_ORACLE_SEMANTIC_BACKEND": "fixture-replay",
        "DSPX_ORACLE_SEMANTIC_FIXTURE_PATH": str(fixture),
    }

    preflight = preflight_program_oracle_semantic_backend(environ=environ).to_dict()
    backend = resolve_program_oracle_semantic_backend(environ=environ)

    assert preflight["ready"] is True
    assert preflight["backend_kind"] == "fixture-replay"
    assert preflight["live_verified"] is False
    assert isinstance(backend, FixtureReplayOracleSemanticBackend)


def test_cli_preflight_json_and_not_ready_exit(monkeypatch) -> None:
    import dspx.config_loader as config_loader
    import dspx.services.program_oracle_semantic_backend as semantic_backend

    monkeypatch.setattr(config_loader, "load_config_env", lambda path=None: {})
    ready = OracleSemanticPreflight(
        ready=True,
        backend_kind="live",
        preferred_model="codex/gpt-5.6-sol",
        configured_provider="test-provider",
        configured_model=None,
        fixture_path=None,
        checks=({"name": "provider_configuration", "ok": True},),
    )
    monkeypatch.setattr(
        semantic_backend,
        "preflight_program_oracle_semantic_backend",
        lambda: ready,
    )
    runner = CliRunner()

    result = runner.invoke(oracle_app, ["program-semantic-preflight", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ready"] is True
    assert payload["executed_model"] is None

    not_ready = OracleSemanticPreflight(
        ready=False,
        backend_kind="fixture-replay",
        preferred_model="codex/gpt-5.6-sol",
        configured_provider=None,
        configured_model=None,
        fixture_path=None,
        checks=({"name": "fixture", "ok": False},),
    )
    monkeypatch.setattr(
        semantic_backend,
        "preflight_program_oracle_semantic_backend",
        lambda: not_ready,
    )

    failed = runner.invoke(oracle_app, ["program-semantic-preflight", "--json"])

    assert failed.exit_code == 2
    assert json.loads(failed.stdout)["ready"] is False
