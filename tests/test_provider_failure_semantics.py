# summary: "Tests fail-closed registered provider defaults, explicit error markers, and truthful CLI exits."
# read_when:
#   - "Changing provider strictness defaults, health probes, smoke behavior, or benchmark status."

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
import dspx.cli.commands.providers as provider_commands
from dspx.dtos import LMResponse
from dspx.multi_provider_lm import MultiProviderIndeterminateError, MultiProviderLM
import dspx.provider_runtime as provider_runtime
import dspx.providers_register_claude as claude_registration
import dspx.providers_register_codex as codex_registration
import dspx.providers_register_gemini as gemini_registration
import dspx.providers_register_multi as multi_registration
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


def test_registered_multi_factory_applies_finite_timeout_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers: list[SimpleNamespace] = []

    def create(_name: str) -> SimpleNamespace:
        provider = SimpleNamespace(model=_name, timeout=None)
        providers.append(provider)
        return provider

    monkeypatch.setattr(multi_registration, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(multi_registration, "create", create)
    monkeypatch.delenv("DSPX_MULTI_TIMEOUT", raising=False)

    lm = multi_registration._factory()

    assert lm.provider_timeout_s == 60.0
    assert [provider.timeout for provider in providers] == [60.0, 60.0, 60.0]


def test_registered_multi_factory_timeout_is_configurable_and_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers: list[SimpleNamespace] = []

    def create(_name: str) -> SimpleNamespace:
        timeout = 12.0 if not providers else None
        provider = SimpleNamespace(model=_name, timeout=timeout)
        providers.append(provider)
        return provider

    monkeypatch.setattr(multi_registration, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(multi_registration, "create", create)
    monkeypatch.setenv("DSPX_MULTI_TIMEOUT", "7.5")

    lm = multi_registration._factory()

    assert lm.provider_timeout_s == 7.5
    assert [provider.timeout for provider in providers] == [12.0, 7.5, 7.5]

    monkeypatch.setenv("DSPX_MULTI_TIMEOUT", "0")
    with pytest.raises(ValueError, match="positive finite"):
        multi_registration._factory()

    monkeypatch.setenv("DSPX_MULTI_TIMEOUT", "")
    with pytest.raises(ValueError, match="positive finite"):
        multi_registration._factory()


def test_parallel_start_failure_is_not_replayed_through_forward() -> None:
    class _StartFailure:
        model = "start-failure"

        def __init__(self) -> None:
            self.forward_calls = 0

        def start(self, prompt=None, messages=None):
            raise RuntimeError("start failed")

        def forward(self, prompt=None, messages=None):
            self.forward_calls += 1
            return {"choices": [{"text": "unsafe replay"}]}

    class _Good:
        model = "good"

        def forward(self, prompt=None, messages=None):
            return {"choices": [{"text": "winner"}]}

    failed = _StartFailure()
    lm = MultiProviderLM(
        [failed, _Good()],
        names=["failed", "good"],
        strategy="parallel_first",
    )

    response = lm.forward(prompt="hello")

    assert response.choices[0]["text"] == "winner"
    assert failed.forward_calls == 0


def test_parallel_empty_start_handle_is_not_replayed_through_forward() -> None:
    class _EmptyStart:
        model = "empty-start"

        def __init__(self) -> None:
            self.forward_calls = 0

        def start(self, prompt=None, messages=None):
            return None

        def forward(self, prompt=None, messages=None):
            self.forward_calls += 1
            return {"choices": [{"text": "unsafe replay"}]}

    class _Good:
        model = "good"

        def forward(self, prompt=None, messages=None):
            return {"choices": [{"text": "winner"}]}

    empty = _EmptyStart()
    lm = MultiProviderLM(
        [empty, _Good()],
        names=["empty", "good"],
        strategy="parallel_first",
    )

    response = lm.forward(prompt="hello")

    assert response.choices[0]["text"] == "winner"
    assert empty.forward_calls == 0


def test_parallel_start_timeout_stops_later_provider_launch() -> None:
    class _StartTimeout:
        model = "start-timeout"

        def start(self, prompt=None, messages=None):
            raise TimeoutError("start timed out")

    class _Later:
        model = "later"

        def __init__(self) -> None:
            self.calls = 0

        def forward(self, prompt=None, messages=None):
            self.calls += 1
            return {"choices": [{"text": "unsafe fallback"}]}

    later = _Later()
    lm = MultiProviderLM(
        [_StartTimeout(), later],
        names=["timeout", "later"],
        strategy="parallel_first",
    )

    with pytest.raises(MultiProviderIndeterminateError, match="fallback was stopped"):
        lm.forward(prompt="hello")

    assert later.calls == 0


def test_multi_provider_raw_metadata_redacts_structured_child_secrets() -> None:
    class _Provider:
        model = "secret-provider"

        def forward(self, prompt=None, messages=None):
            return SimpleNamespace(
                choices=[{"text": "valid"}],
                raw={"api_key": "supersecret-value", "request_id": "req-1"},
            )

    response = MultiProviderLM([_Provider()], names=["child"]).forward(prompt="hello")
    encoded = json.dumps(response.raw)

    assert "supersecret-value" not in encoded
    assert "[REDACTED]" in encoded
    assert response.raw["child"]["raw"]["request_id"] == "req-1"


@pytest.mark.parametrize(
    "malformed",
    [
        {"outputs": "unsafe"},
        {"outputs": [{"error": "hidden"}]},
        {"choices": "unsafe"},
    ],
)
def test_multi_provider_malformed_envelope_is_conclusive_failure(
    malformed: dict[str, Any],
) -> None:
    class _Malformed:
        model = "malformed"

        def forward(self, prompt=None, messages=None):
            return malformed

    class _Good:
        model = "good"

        def forward(self, prompt=None, messages=None):
            return {"choices": [{"text": "winner"}]}

    response = MultiProviderLM([_Malformed(), _Good()], names=["bad", "good"]).forward(
        prompt="hello"
    )

    assert response.choices[0]["text"] == "winner"


def test_deadline_exception_is_indeterminate_and_stops_fallback() -> None:
    class DeadlineExceeded(RuntimeError):
        pass

    class _Deadline:
        model = "deadline"

        def forward(self, prompt=None, messages=None):
            raise DeadlineExceeded("provider deadline exceeded")

    class _Later:
        model = "later"

        def __init__(self) -> None:
            self.calls = 0

        def forward(self, prompt=None, messages=None):
            self.calls += 1
            return {"choices": [{"text": "unsafe fallback"}]}

    later = _Later()
    lm = MultiProviderLM([_Deadline(), later], names=["deadline", "later"])

    with pytest.raises(MultiProviderIndeterminateError, match="fallback was stopped"):
        lm.forward(prompt="hello")

    assert later.calls == 0


def test_declared_deadline_payload_is_indeterminate_and_stops_fallback() -> None:
    class _DeadlinePayload:
        model = "deadline"

        def forward(self, prompt=None, messages=None):
            return SimpleNamespace(
                choices=[{"text": "invalid"}],
                raw={
                    "_dspx_error": True,
                    "_dspx_error_type": "DeadlineExceeded",
                    "error": "provider deadline exceeded",
                },
            )

    class _Later:
        model = "later"

        def __init__(self) -> None:
            self.calls = 0

        def forward(self, prompt=None, messages=None):
            self.calls += 1
            return {"choices": [{"text": "unsafe fallback"}]}

    later = _Later()
    lm = MultiProviderLM([_DeadlinePayload(), later], names=["deadline", "later"])

    with pytest.raises(MultiProviderIndeterminateError, match="fallback was stopped"):
        lm.forward(prompt="hello")

    assert later.calls == 0


def test_nested_mapping_raw_failure_cannot_become_output() -> None:
    class _NestedFailure:
        model = "nested-failure"

        def forward(self, prompt=None, messages=None):
            return {
                "choices": [{"text": "unsafe"}],
                "raw": {"_dspx_error": True, "error": "provider failed"},
            }

    class _Good:
        model = "good"

        def forward(self, prompt=None, messages=None):
            return {"choices": [{"text": "winner"}]}

    response = MultiProviderLM(
        [_NestedFailure(), _Good()], names=["bad", "good"]
    ).forward(prompt="hello")

    assert response.choices[0]["text"] == "winner"


def test_non_timeout_deadline_configuration_error_allows_fallback() -> None:
    class DeadlineConfigurationError(RuntimeError):
        pass

    class _ConfigurationFailure:
        model = "configuration"

        def forward(self, prompt=None, messages=None):
            raise DeadlineConfigurationError("invalid deadline configuration")

    class _Good:
        model = "good"

        def forward(self, prompt=None, messages=None):
            return {"choices": [{"text": "winner"}]}

    response = MultiProviderLM(
        [_ConfigurationFailure(), _Good()], names=["bad", "good"]
    ).forward(prompt="hello")

    assert response.choices[0]["text"] == "winner"


def test_duplicate_provider_names_preserve_each_raw_result() -> None:
    class _Provider:
        def __init__(self, model: str, request_id: str) -> None:
            self.model = model
            self.request_id = request_id

        def forward(self, prompt=None, messages=None):
            return SimpleNamespace(
                choices=[{"text": self.model}],
                raw={"request_id": self.request_id},
            )

    response = MultiProviderLM(
        [_Provider("left", "req-left"), _Provider("right", "req-right")],
        names=["dup", "dup"],
        strategy="collect_concat",
    ).forward(prompt="hello")

    assert set(response.raw) == {"dup", "dup#2"}
    assert response.raw["dup"]["raw"]["request_id"] == "req-left"
    assert response.raw["dup#2"]["raw"]["request_id"] == "req-right"

    collision = MultiProviderLM(
        [
            _Provider("named-suffix", "req-named"),
            _Provider("first-dup", "req-first"),
            _Provider("second-dup", "req-second"),
        ],
        names=["dup#2", "dup", "dup"],
        strategy="collect_concat",
    ).forward(prompt="hello")

    assert set(collision.raw) == {"dup#2", "dup", "dup#3"}
    assert collision.raw["dup#2"]["raw"]["request_id"] == "req-named"
    assert collision.raw["dup"]["raw"]["request_id"] == "req-first"
    assert collision.raw["dup#3"]["raw"]["request_id"] == "req-second"
