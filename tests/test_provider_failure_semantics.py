# summary: "Tests fail-closed registered provider defaults, explicit error markers, and truthful CLI exits."
# read_when:
#   - "Changing provider strictness defaults, health probes, smoke behavior, or benchmark status."

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
import dspx.cli.commands.providers as provider_commands
from dspx.dtos import LMResponse
import dspx.provider_runtime as provider_runtime
import dspx.providers_register_claude as claude_registration
import dspx.providers_register_codex as codex_registration
import dspx.providers_register_gemini as gemini_registration
import dspx.providers_register_pi as pi_registration

runner = CliRunner()

_REGISTERED_STRICT_PROVIDERS = (
    (pi_registration, "DSPX_PI_STRICT"),
    (codex_registration, "DSPX_CODEX_STRICT"),
    (claude_registration, "DSPX_CLAUDE_STRICT"),
    (gemini_registration, "DSPX_GEMINI_STRICT"),
)


@pytest.mark.parametrize(("registration", "strict_env"), _REGISTERED_STRICT_PROVIDERS)
def test_registered_cli_provider_defaults_fail_closed(
    registration: Any,
    strict_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(strict_env, raising=False)

    lm = registration._factory()

    assert lm.strict is True


@pytest.mark.parametrize(("registration", "strict_env"), _REGISTERED_STRICT_PROVIDERS)
def test_registered_cli_provider_legacy_soft_failure_requires_explicit_opt_out(
    registration: Any,
    strict_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(strict_env, "0")

    lm = registration._factory()

    assert lm.strict is False


def test_pi_health_probe_missing_binary_is_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_commands, "ensure_env", lambda *args, **kwargs: None)
    monkeypatch.setenv("DSPX_PI_BIN", "/definitely/missing/pi")
    monkeypatch.delenv("DSPX_PI_STRICT", raising=False)

    result = runner.invoke(
        app,
        ["providers", "health", "--provider", "pi-rpc", "--probe", "--json"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["probe"]["ok"] is False
    assert "/definitely/missing/pi" in payload["error"]


class _MarkedFailureProvider:
    model = "fake/model"

    def generate(self, request: Any, **kwargs: Any) -> LMResponse:
        return LMResponse(
            outputs=["authentication failed"],
            model=self.model,
            raw={
                "_dspx_error": True,
                "_dspx_error_type": "RuntimeError",
                "error": "api_key=supersecret-value authentication failed",
            },
        )


class _ErrorLookingSuccessProvider:
    model = "fake/model"

    def generate(self, request: Any, **kwargs: Any) -> LMResponse:
        return LMResponse(outputs=["authentication failed"], model=self.model)


class _NonErrorMarkerProvider:
    model = "fake/model"

    def __init__(self, marker: Any) -> None:
        self.marker = marker

    def generate(self, request: Any, **kwargs: Any) -> LMResponse:
        return LMResponse(
            outputs=["valid output"],
            model=self.model,
            raw={"_dspx_error": self.marker, "error": ""},
        )


class _ExplicitInvocationFailureProvider:
    model = "fake/model"

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw

    def generate(self, request: Any, **kwargs: Any) -> LMResponse:
        return LMResponse(outputs=["invalid output"], model=self.model, raw=self.raw)


class _ContradictoryHealthProvider:
    model = "fake/model"

    def healthcheck(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "probe": {"ok": False, "error": "provider probe failed"},
        }


class _MarkedHealthProvider:
    model = "fake/model"

    def healthcheck(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "_dspx_error": True,
            "error": "api_key=supersecret-value provider health failed",
        }


class _ExplicitErrorHealthProvider:
    model = "fake/model"

    def healthcheck(self, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "error": "provider health failed"}


class _ExplicitProbeErrorHealthProvider:
    model = "fake/model"

    def healthcheck(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "probe": {"ok": True, "error": "provider probe failed"},
        }


class _ErrorStatusHealthProvider:
    model = "fake/model"

    def healthcheck(self, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "status": "error"}


class _ProbeFailureStatusHealthProvider:
    model = "fake/model"

    def healthcheck(self, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "probe": {"ok": True, "status": "failure"}}


def test_explicit_provider_error_marker_fails_health_and_benchmark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_runtime, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        provider_runtime, "create", lambda _provider: _MarkedFailureProvider()
    )

    health = provider_runtime.check_provider_health("fake", probe=True)
    benchmark = provider_runtime.benchmark_providers(
        ["fake"], prompt="hello", repeats=2
    )

    assert health["ok"] is False
    assert health["probe"]["ok"] is False
    assert "supersecret" not in json.dumps(health)
    assert benchmark["ok"] is False
    assert benchmark["results"][0]["successes"] == 0
    assert benchmark["results"][0]["failures"] == 2
    assert "supersecret" not in json.dumps(benchmark)


def test_error_looking_text_is_valid_when_provider_reports_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_runtime, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        provider_runtime, "create", lambda _provider: _ErrorLookingSuccessProvider()
    )

    health = provider_runtime.check_provider_health("fake", probe=True)

    assert health["ok"] is True
    assert health["probe"]["text"] == "authentication failed"


@pytest.mark.parametrize("marker", [False, "false", 1])
def test_only_typed_true_error_marker_is_a_failure(
    marker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_runtime, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        provider_runtime,
        "create",
        lambda _provider: _NonErrorMarkerProvider(marker),
    )

    health = provider_runtime.check_provider_health("fake", probe=True)

    assert health["ok"] is True
    assert health["probe"]["text"] == "valid output"


@pytest.mark.parametrize(
    "raw",
    [
        {"error": "provider execution failed"},
        {"status": "failure"},
    ],
)
def test_invocation_error_fields_and_failure_statuses_never_become_output(
    raw: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_runtime, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        provider_runtime,
        "create",
        lambda _provider: _ExplicitInvocationFailureProvider(raw),
    )

    health = provider_runtime.check_provider_health("fake", probe=True)
    benchmark = provider_runtime.benchmark_providers(
        ["fake"], prompt="hello", repeats=1
    )

    assert health["ok"] is False
    assert benchmark["ok"] is False
    assert benchmark["results"][0]["successes"] == 0


@pytest.mark.parametrize(
    ("provider", "probe"),
    [
        (_ContradictoryHealthProvider(), False),
        (_MarkedHealthProvider(), True),
        (_ExplicitErrorHealthProvider(), True),
        (_ExplicitProbeErrorHealthProvider(), False),
        (_ErrorStatusHealthProvider(), False),
        (_ProbeFailureStatusHealthProvider(), False),
    ],
)
def test_custom_health_payload_cannot_contradict_probe_or_error_status(
    provider: Any,
    probe: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_runtime, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(provider_runtime, "create", lambda _provider: provider)

    health = provider_runtime.check_provider_health("fake", probe=probe)

    assert health["ok"] is False
    assert health["status"] == "error"
    assert "supersecret" not in json.dumps(health)


def test_benchmark_requires_at_least_one_measured_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_runtime, "ensure_default_providers", lambda: None)

    with pytest.raises(ValueError, match="repeats must be at least 1"):
        provider_runtime.benchmark_providers(["fake"], prompt="hello", repeats=0)

    result = runner.invoke(
        app,
        ["providers", "benchmark", "--provider", "fake", "--repeats", "0"],
    )
    assert result.exit_code == 2


def test_provider_benchmark_cli_exits_nonzero_when_any_provider_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_commands, "ensure_env", lambda *args, **kwargs: None)
    monkeypatch.setattr(provider_runtime, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        provider_runtime, "create", lambda _provider: _MarkedFailureProvider()
    )

    result = runner.invoke(
        app,
        ["providers", "benchmark", "--provider", "fake", "--json"],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout)["ok"] is False
