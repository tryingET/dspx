# summary: "Tests provider-neutral program Oracle semantic execution, replay, and truthful preflight evidence."

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dspx.cli.commands.oracle import app as oracle_app
from dspx.services.program_oracle_semantic_backend import (
    FixtureReplayOracleSemanticBackend,
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


def test_live_preflight_is_explicitly_unavailable_without_provider_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dspx import provider_registry

    monkeypatch.setattr(
        provider_registry,
        "create",
        lambda name: pytest.fail(f"live preflight must not create provider {name}"),
    )
    payload = preflight_program_oracle_semantic_backend(
        environ={
            "DSPX_ORACLE_SEMANTIC_BACKEND": "live",
            "DSPX_ORACLE_SEMANTIC_PROVIDER": "stub",
        }
    ).to_dict()

    assert payload["ready"] is False
    assert payload["configured_provider"] == "stub"
    assert (
        "live Oracle semantic providers are unsupported"
        in payload["checks"][0]["detail"]
    )


def test_live_resolver_fails_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dspx import provider_registry

    monkeypatch.setattr(
        provider_registry,
        "create",
        lambda name: pytest.fail(f"live resolver must not create provider {name}"),
    )
    with pytest.raises(ProgramOracleSemanticBackendError, match="live Oracle semantic"):
        resolve_program_oracle_semantic_backend(
            environ={
                "DSPX_ORACLE_SEMANTIC_BACKEND": "live",
                "DSPX_ORACLE_SEMANTIC_PROVIDER": "stub",
            }
        )


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
