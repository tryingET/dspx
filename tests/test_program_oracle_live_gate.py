# summary: "Offline effect-counted regressions for the actual Oracle live-test gate."

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest
import test_program_oracle_semantic_backend as live
from dspx import policy


@pytest.fixture
def effects(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    # Hermetic policy only for this fake-effect regression harness.
    for name in tuple(os.environ):
        if name.startswith("DSPX_POLICY_") or name == "DSPX_ORACLE_LIVE_VLLM":
            monkeypatch.delenv(name)
    state: dict[str, Any] = {
        "http": 0,
        "preflight": 0,
        "resolve": 0,
        "analyze": 0,
        "available": False,
        "http_error": False,
    }

    def get(url: str, **kwargs: Any) -> httpx.Response:
        state["http"] += 1
        assert url == "http://127.0.0.1:2456/v1/models"
        assert kwargs == {"timeout": 2.0, "trust_env": False}
        if state["http_error"]:
            raise OSError("fake unavailable transport")
        return httpx.Response(
            200 if state["available"] else 503,
            text="local/Qwen3.8-27B-AEON-NVFP4-FP8",
        )

    class Preflight:
        def to_dict(self) -> dict[str, bool]:
            return {"ready": True, "live_verified": False}

    def check_config(environ: dict[str, str]) -> None:
        assert environ["DSPX_OPENAI_COMPAT_API_BASE"] == live.LOOPBACK_BASE
        assert environ["DSPX_OPENAI_COMPAT_MODEL"] == live.LOCAL_MODEL
        assert environ["DSPX_ORACLE_SEMANTIC_PROVIDER"] == "openai-compatible"
        assert environ["DSPX_ORACLE_SEMANTIC_BACKEND"] == "live"

    def preflight(*, environ: dict[str, str]) -> Preflight:
        state["preflight"] += 1
        check_config(environ)
        return Preflight()

    class Result:
        def to_dict(self) -> dict[str, Any]:
            return {
                "backend_kind": "live",
                "configured_provider": "openai-compatible",
                "configured_model": live.LOCAL_MODEL,
                "execution_status": "succeeded",
                "live_call_succeeded": True,
                "executed_provider": "openai-compatible",
                "executed_model": live.LOCAL_MODEL,
                "analysis": {
                    "observations": ["passed"],
                    "evidence_refs": ["receipt:target"],
                },
            }

    class Backend(live.TypedProviderOracleSemanticBackend):
        def __init__(self) -> None:
            pass  # No real provider or LM construction.

        def analyze(self, request: Any) -> Any:
            state["analyze"] += 1
            assert request == live._codebook_request()
            return Result()

    def resolve(*, environ: dict[str, str]) -> Backend:
        state["resolve"] += 1
        check_config(environ)
        return Backend()

    monkeypatch.setattr(live.httpx, "get", get)
    monkeypatch.setattr(live, "preflight_program_oracle_semantic_backend", preflight)
    monkeypatch.setattr(live, "resolve_program_oracle_semantic_backend", resolve)
    return state


def _counts(effects: dict[str, Any]) -> tuple[int, ...]:
    return tuple(effects[key] for key in ("http", "preflight", "resolve", "analyze"))


def _opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_ORACLE_LIVE_VLLM", "1")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")


@pytest.mark.parametrize(
    "flag", ["DSPX_ORACLE_LIVE_VLLM", "DSPX_POLICY_ALLOW_NETWORK_MUTATE"]
)
@pytest.mark.parametrize(
    "value", [None, "", "0", "true", "yes", "on", "01", " 1", "1 ", "2"]
)
def test_exact_opt_ins_before_effects(
    monkeypatch: pytest.MonkeyPatch,
    effects: dict[str, Any],
    flag: str,
    value: str | None,
) -> None:
    _opt_in(monkeypatch)
    if value is None:
        monkeypatch.delenv(flag)
    else:
        monkeypatch.setenv(flag, value)
    with pytest.raises(pytest.skip.Exception, match=f"requires exact {flag}=1"):
        live.test_live_loopback_vllm_typed_backend_round_trip(monkeypatch)
    assert _counts(effects) == (0, 0, 0, 0)


def test_default_before_effects(
    monkeypatch: pytest.MonkeyPatch, effects: dict[str, Any]
) -> None:
    with pytest.raises(pytest.skip.Exception, match="requires exact"):
        live.test_live_loopback_vllm_typed_backend_round_trip(monkeypatch)
    assert _counts(effects) == (0, 0, 0, 0)


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", " TRUE ", "Yes", " ON "])
def test_bypass_before_effects(
    monkeypatch: pytest.MonkeyPatch, effects: dict[str, Any], value: str
) -> None:
    _opt_in(monkeypatch)
    monkeypatch.setenv("DSPX_POLICY_BYPASS", value)
    with pytest.raises(
        pytest.skip.Exception, match="does not permit DSPX_POLICY_BYPASS"
    ):
        live.test_live_loopback_vllm_typed_backend_round_trip(monkeypatch)
    assert _counts(effects) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    "restrictions",
    [
        {"ALLOWED_PROVIDERS": "stub"},
        {"DISALLOWED_PROVIDERS": "openai-compatible"},
        {
            "ALLOWED_PROVIDERS": "openai-compatible",
            "DISALLOWED_PROVIDERS": "openai-compatible",
        },
        {"ALLOWED_CAPS": "network.read"},
        {"ALLOWED_CAPS": "network.mutate"},
        {"ALLOWED_CAPS": "unrelated"},
        {"DISALLOWED_CAPS": "network.read"},
        {"DISALLOWED_CAPS": "network.mutate"},
        {
            "ALLOWED_CAPS": "network.read,network.mutate",
            "DISALLOWED_CAPS": "network.read",
        },
        {
            "ALLOWED_CAPS": "network.read,network.mutate",
            "DISALLOWED_CAPS": "network.mutate",
        },
    ],
)
def test_restrictions_before_effects(
    monkeypatch: pytest.MonkeyPatch,
    effects: dict[str, Any],
    restrictions: dict[str, str],
) -> None:
    _opt_in(monkeypatch)
    for name, value in restrictions.items():
        monkeypatch.setenv(f"DSPX_POLICY_{name}", value)
    before = dict(os.environ)
    with pytest.raises(pytest.skip.Exception, match="policy"):
        live.test_live_loopback_vllm_typed_backend_round_trip(monkeypatch)
    assert _counts(effects) == (0, 0, 0, 0)
    assert dict(os.environ) == before


@pytest.mark.parametrize(
    "available,http_error", [(False, False), (False, True), (True, False)]
)
@pytest.mark.parametrize("restricted", [False, True])
def test_permitted_fake_path(
    monkeypatch: pytest.MonkeyPatch,
    effects: dict[str, Any],
    available: bool,
    http_error: bool,
    restricted: bool,
) -> None:
    _opt_in(monkeypatch)
    monkeypatch.setenv("DSPX_POLICY_BYPASS", "0")
    if restricted:
        monkeypatch.setenv("DSPX_POLICY_ALLOWED_PROVIDERS", "stub,openai-compatible")
        monkeypatch.setenv("DSPX_POLICY_DISALLOWED_PROVIDERS", "other")
        monkeypatch.setenv("DSPX_POLICY_ALLOWED_CAPS", "NETWORK.READ, network.mutate")
        monkeypatch.setenv("DSPX_POLICY_DISALLOWED_CAPS", "unrelated")
    before = {k: v for k, v in os.environ.items() if k.startswith("DSPX_POLICY_")}
    effects.update(available=available, http_error=http_error)
    checks: list[str] = []
    for name in ("check_provider_allowed", "check_capability"):
        original = getattr(policy, name)

        def checked(value: str, original: Any = original) -> None:
            assert _counts(effects) == (0, 0, 0, 0)
            checks.append(value)
            original(value)

        monkeypatch.setattr(policy, name, checked)
    if available:
        live.test_live_loopback_vllm_typed_backend_round_trip(monkeypatch)
        assert _counts(effects) == (1, 1, 1, 1)
    else:
        with pytest.raises(pytest.skip.Exception, match="not serving the local model"):
            live.test_live_loopback_vllm_typed_backend_round_trip(monkeypatch)
        assert _counts(effects) == (1, 0, 0, 0)
    assert checks == ["openai-compatible", "network.read", "network.mutate"]
    assert {
        k: v for k, v in os.environ.items() if k.startswith("DSPX_POLICY_")
    } == before
