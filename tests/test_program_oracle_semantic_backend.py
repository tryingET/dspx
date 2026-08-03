# summary: "Tests provider-neutral program Oracle semantic execution, replay, and truthful preflight evidence."

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dspx.capabilities import ProviderCapabilities
from dspx.cli.commands.oracle import app as oracle_app
from dspx.dtos import LMResponse
from dspx.services.program_oracle_semantic_backend import (
    FixtureReplayOracleSemanticBackend,
    LiveLMOracleSemanticBackend,
    ProgramOracleSemanticBackendError,
    _analysis_prompt,
    _analysis_response_format,
    preflight_program_oracle_semantic_backend,
    resolve_program_oracle_semantic_backend,
)
from dspx.services.program_oracle_semantic_contract import (
    ORACLE_SEMANTIC_FIXTURE_SCHEMA,
    OracleSemanticPreflight,
    OracleSemanticRequest,
)
from typer.testing import CliRunner


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


def test_codebook_prompt_requires_minimum_directly_entailed_code_set() -> None:
    request = OracleSemanticRequest(
        objective="Classify only observed behavior",
        evidence={"refs": [{"ref": "receipt:run-7"}], "status": "passed"},
        quality_contract={
            "analysis_codebook": {
                "observations": ["passed", "failed"],
                "hypotheses": ["cause_unproven"],
            }
        },
    )

    prompt = _analysis_prompt(request)

    assert "directly and unambiguously entails" in prompt
    assert "Use an empty array" in prompt
    assert "minimum exact code set" in prompt
    assert "not every plausible code" in prompt
    assert "same proposition with the same subject and state" in prompt
    assert "do not infer an unmentioned workflow entity" in prompt
    assert "requires explicit causal, mechanism" in prompt
    assert "narrowest single" in prompt


class _LiveLM:
    requested_model = "openai/gpt-5.4"

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def generate(self, request, **kwargs):
        self.calls += 1
        assert kwargs == {"response_format": _analysis_response_format()}
        if self.fail:
            raise RuntimeError(
                "provider unavailable; authorization: Bearer secret-token-value"
            )
        assert "local transition authority" not in request.prompt
        return LMResponse(
            outputs=[json.dumps(_analysis())],
            model="openai/gpt-5.4-2026-06-01",
        )


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


def test_live_preflight_resolves_provider_without_calling_model(monkeypatch) -> None:
    from dspx import provider_registry

    monkeypatch.setattr(provider_registry, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        provider_registry,
        "capabilities",
        lambda name: ProviderCapabilities(
            json_mode=True, structured_output_format="json"
        ),
    )
    monkeypatch.setattr(
        provider_registry,
        "available",
        lambda: {"test-provider": object()},
    )
    monkeypatch.setattr(
        provider_registry,
        "create",
        lambda name: pytest.fail("preflight must not run provider factories"),
    )

    payload = preflight_program_oracle_semantic_backend(
        environ={
            "DSPX_ORACLE_SEMANTIC_BACKEND": "live",
            "DSPX_ORACLE_SEMANTIC_PROVIDER": "test-provider",
        }
    ).to_dict()

    assert payload["ready"] is True
    assert payload["preferred_model"] == "codex/gpt-5.6-sol"
    assert payload["configured_provider"] == "test-provider"
    assert payload["configured_model"] is None
    assert payload["executed_model"] is None
    assert payload["live_verified"] is False


def test_dspy_lm_auth_preflight_binds_configured_model_without_factory(
    monkeypatch,
) -> None:
    from dspx import provider_registry

    monkeypatch.setattr(provider_registry, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        provider_registry,
        "capabilities",
        lambda name: ProviderCapabilities(
            json_mode=True, structured_output_format="json"
        ),
    )
    monkeypatch.setattr(
        provider_registry,
        "available",
        lambda: {"dspy-lm-auth": object()},
    )
    monkeypatch.setattr(
        provider_registry,
        "create",
        lambda name: pytest.fail("preflight must not run provider factories"),
    )

    payload = preflight_program_oracle_semantic_backend(
        environ={
            "DSPX_ORACLE_SEMANTIC_BACKEND": "live",
            "DSPX_ORACLE_SEMANTIC_PROVIDER": "dspy-lm-auth",
            "DSPX_ORACLE_SEMANTIC_MODEL": "codex/gpt-5.6-sol",
        }
    ).to_dict()

    assert payload["ready"] is True
    assert payload["preferred_model"] == "codex/gpt-5.6-sol"
    assert payload["configured_model"] == "codex/gpt-5.6-sol"
    assert payload["executed_model"] is None
    assert payload["live_verified"] is False


def test_dspy_lm_auth_resolver_constructs_the_resolved_role(monkeypatch) -> None:
    import dspx.services.program_oracle_semantic_backend as semantic_backend
    from dspx import provider_registry

    lm = _LiveLM()
    lm.requested_model = "codex/gpt-5.6-sol"
    captured: dict[str, object] = {}

    def fake_create_role_lm(name, *, environ, resolved_role):
        captured["name"] = name
        captured["environ"] = environ
        captured["role"] = resolved_role
        return lm

    monkeypatch.setattr(semantic_backend, "create_role_lm", fake_create_role_lm)
    monkeypatch.setattr(
        provider_registry,
        "create",
        lambda name: pytest.fail("role-bound dspy-lm-auth must bypass generic factory"),
    )
    environ = {
        "DSPX_ORACLE_SEMANTIC_BACKEND": "live",
        "DSPX_ORACLE_SEMANTIC_PROVIDER": "dspy-lm-auth",
        "DSPX_ORACLE_SEMANTIC_MODEL": "codex/gpt-5.6-sol",
        "DSPX_ORACLE_SEMANTIC_REASONING_EFFORT": "xhigh",
    }

    backend = resolve_program_oracle_semantic_backend(environ=environ)

    assert isinstance(backend, LiveLMOracleSemanticBackend)
    assert backend.preferred_model == "codex/gpt-5.6-sol"
    assert backend.configured_model == "codex/gpt-5.6-sol"
    assert captured["name"] == "oracle_semantic"
    assert captured["environ"] is environ
    role = captured["role"]
    assert getattr(role, "model") == "codex/gpt-5.6-sol"
    assert getattr(role, "reasoning_effort") == "xhigh"


def test_live_preflight_fails_for_provider_without_json_capability(monkeypatch) -> None:
    from dspx import provider_registry

    monkeypatch.setattr(provider_registry, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        provider_registry,
        "capabilities",
        lambda name: ProviderCapabilities(
            json_mode=False, structured_output_format="none"
        ),
    )

    payload = preflight_program_oracle_semantic_backend(
        environ={"DSPX_ORACLE_SEMANTIC_PROVIDER": "text-only"}
    ).to_dict()

    assert payload["ready"] is False
    assert payload["executed_provider"] is None
    assert "JSON output capability" in payload["checks"][0]["detail"]


def test_live_execution_preserves_preferred_configured_and_observed_models() -> None:
    lm = _LiveLM()
    backend = LiveLMOracleSemanticBackend(
        provider_name="openai-api",
        preferred_model="codex/gpt-5.6-sol",
        lm=lm,
    )

    payload = backend.analyze(_request()).to_dict()

    assert payload["execution_status"] == "succeeded"
    assert payload["preferred_model"] == "codex/gpt-5.6-sol"
    assert payload["configured_model"] == "openai/gpt-5.4"
    assert payload["executed_provider"] is None
    assert payload["executed_model"] == "openai/gpt-5.4-2026-06-01"
    assert payload["live_call_succeeded"] is True
    assert payload["analysis"] == _analysis()


def test_failed_live_execution_never_claims_executed_identity() -> None:
    backend = LiveLMOracleSemanticBackend(
        provider_name="openai-api",
        preferred_model="codex/gpt-5.6-sol",
        lm=_LiveLM(fail=True),
    )

    payload = backend.analyze(_request()).to_dict()

    assert payload["execution_status"] == "failed_before_live_success"
    assert payload["executed_provider"] is None
    assert payload["executed_model"] is None
    assert payload["live_call_succeeded"] is False
    assert "secret-token-value" not in payload["error"]


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
