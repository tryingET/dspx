# summary: "Tests v4 provider registration, dspy-lm-auth integration, Codex response handling, CLI provider surfaces, and optimize bindings."
# read_when:
#   - "Changing v4 provider capabilities, dspy-lm-auth or Codex behavior, provider CLI commands, runtime metadata, or optimization provider selection."

from __future__ import annotations

import builtins
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.dspy_lm_auth_lm import (
    DspyLMAuthCodexStreamResponse,
    DspyLMAuthLM,
    DspyLMAuthMinimalResponse,
)
import dspx.provider_registry as provider_registry
from dspx.capabilities import ProviderCapabilities
from dspx.provider_registry import available, ensure_default_providers
import dspx.providers_register_multi as providers_register_multi
from dspx.providers_register_openai_compatible import _truthy
from dspx.dtos import LMRequest, Message
from dspx.run_receipts import build_run_receipt
from dspx.services.optimize_service import run_gepa_optimize

runner = CliRunner()


class _FakeAuthStorage:
    def __init__(self, path=None):
        self.path = path

    def has_auth(self, provider: str) -> bool:
        return provider in {"codex", "openai-codex"}


class _FakeLM:
    last_kwargs = None
    last_messages = None

    def __init__(
        self, model: str, *args, auth_provider=None, auth_storage=None, **kwargs
    ):
        self.model = f"openai/{model.split('/', 1)[-1]}"
        self.model_type = "responses"
        self.resolved_model_string = self.model
        self.kwargs = {
            "headers": {"Authorization": "Bearer secret-token", "X-Test": "ok"}
        }
        self._uses_codex_route = True
        self.auth_provider = auth_provider
        self.auth_storage = auth_storage

    def forward(self, prompt=None, messages=None, **kwargs):
        _FakeLM.last_kwargs = dict(kwargs)
        _FakeLM.last_messages = messages
        text = (
            prompt or ((messages or [{}])[0].get("content") if messages else "") or ""
        )
        return {
            "choices": [{"text": f"auth:{text}"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


def test_registry_includes_v4_providers() -> None:
    ensure_default_providers()
    reg = available()
    assert "dspy-lm-auth" in reg
    assert "openai-compatible" in reg
    assert "vllm-local" in reg


def test_dspy_lm_auth_registry_declares_default_codex_vision_support(
    monkeypatch,
) -> None:
    from dspx.providers_register_dspy_lm_auth import register

    saved_registry = dict(provider_registry._REGISTRY)
    try:
        provider_registry._REGISTRY.clear()
        monkeypatch.delenv("DSPX_LM_AUTH_MODEL", raising=False)
        monkeypatch.delenv("DSPX_LM_AUTH_PROVIDER", raising=False)
        register()
        caps = provider_registry.capabilities("dspy-lm-auth")
        assert caps.supports_vision is True
    finally:
        provider_registry._REGISTRY.clear()
        provider_registry._REGISTRY.update(saved_registry)


def test_dspy_lm_auth_default_capabilities_refresh_with_env_changes(
    monkeypatch,
) -> None:
    saved_registry = dict(provider_registry._REGISTRY)
    try:
        provider_registry._REGISTRY.clear()
        monkeypatch.setenv("DSPX_LM_AUTH_MODEL", "openai/gpt-4o")
        monkeypatch.delenv("DSPX_LM_AUTH_PROVIDER", raising=False)
        ensure_default_providers()
        assert provider_registry.capabilities("dspy-lm-auth").supports_vision is False

        monkeypatch.setenv("DSPX_LM_AUTH_MODEL", "codex/gpt-5.5")
        ensure_default_providers()
        assert provider_registry.capabilities("dspy-lm-auth").supports_vision is True
    finally:
        provider_registry._REGISTRY.clear()
        provider_registry._REGISTRY.update(saved_registry)


def test_dspy_lm_auth_wrapper_health_and_generate(monkeypatch, tmp_path: Path) -> None:
    fake = types.SimpleNamespace(LM=_FakeLM, AuthStorage=_FakeAuthStorage)
    monkeypatch.setitem(sys.modules, "dspy_lm_auth", fake)

    storage = tmp_path / "auth.json"
    storage.write_text("{}\n", encoding="utf-8")
    lm = DspyLMAuthLM(
        model="codex/gpt-5.4-mini",
        auth_provider="codex",
        auth_storage=str(storage),
    )

    health = lm.healthcheck()
    assert health["ok"] is True
    assert health["metadata"]["auth_storage"] == "[REDACTED]"
    assert health["metadata"]["auth_storage_exists"] == "[REDACTED]"

    assert lm.capabilities.supports_vision is True

    res = lm.generate(LMRequest(prompt="hello", messages=None))
    assert res.outputs == ["auth:hello"]
    assert res.usage == {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    runtime = lm.runtime_metadata()
    assert runtime["resolved_headers"]["Authorization"] == "[REDACTED]"


def test_dspy_lm_auth_healthcheck_redacts_probe_text(monkeypatch) -> None:
    fake = types.SimpleNamespace(LM=_FakeLM, AuthStorage=_FakeAuthStorage)
    monkeypatch.setitem(sys.modules, "dspy_lm_auth", fake)

    lm = DspyLMAuthLM(auth_provider="codex")

    health = lm.healthcheck(probe=True, prompt="api_key=supersecret-value")

    assert health["ok"] is True
    assert health["probe"]["text"] == "auth:api_key=[REDACTED]"
    assert "supersecret" not in json.dumps(health)


def test_dspy_lm_auth_healthcheck_redacts_direct_errors(monkeypatch) -> None:
    class BadAuthStorage:
        def __init__(self, path=None):
            self.path = path

        def has_auth(self, provider: str) -> bool:
            raise RuntimeError(
                f"auth_storage=/tmp/secret-auth.json api_key=supersecret-{provider}"
            )

    fake = types.SimpleNamespace(LM=_FakeLM, AuthStorage=BadAuthStorage)
    monkeypatch.setitem(sys.modules, "dspy_lm_auth", fake)

    lm = DspyLMAuthLM(auth_provider="codex", auth_storage="/tmp/secret-auth.json")

    health = lm.healthcheck()

    assert health["ok"] is False
    assert "supersecret" not in json.dumps(health)
    assert "[REDACTED]" in health["error"]
    assert health["checks"][-1]["detail"] == health["error"]


def test_dspy_lm_auth_generate_preserves_non_strict_error_payload(monkeypatch) -> None:
    class BadInner:
        def forward(self, **kwargs):
            raise RuntimeError("boom api_key=supersecret-value")

    lm = DspyLMAuthLM(strict=False)
    monkeypatch.setattr(lm, "_build_inner", lambda: BadInner())

    result = lm.generate(LMRequest(prompt="hello"))

    assert result.outputs == ["boom api_key=[REDACTED]"]
    assert result.raw is not None
    assert result.raw["_dspx_error"] is True
    assert result.raw["_dspx_error_type"] == "RuntimeError"
    assert "supersecret" not in json.dumps(result.raw)


def test_dspy_lm_auth_wrapper_import_error_mentions_repo_helper(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "dspy_lm_auth", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "dspy_lm_auth":
            raise ImportError("missing test dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    lm = DspyLMAuthLM()
    with pytest.raises(RuntimeError, match="just link-dspy-lm-auth"):
        lm._import_module()


def test_dspy_lm_auth_wrapper_strips_unsupported_params_and_streams_codex_route(
    monkeypatch, tmp_path: Path
) -> None:
    fake = types.SimpleNamespace(LM=_FakeLM, AuthStorage=_FakeAuthStorage)
    monkeypatch.setitem(sys.modules, "dspy_lm_auth", fake)
    _FakeLM.last_kwargs = None

    storage = tmp_path / "auth.json"
    storage.write_text("{}\n", encoding="utf-8")
    lm = DspyLMAuthLM(
        model="codex/gpt-5.4",
        auth_provider="codex",
        auth_storage=str(storage),
    )
    lm.forward(prompt="hello", max_tokens=8, temperature=0)
    assert _FakeLM.last_kwargs is not None
    assert "max_tokens" not in _FakeLM.last_kwargs
    assert "temperature" not in _FakeLM.last_kwargs
    assert _FakeLM.last_kwargs["stream"] is True
    assert _FakeLM.last_kwargs["cache"] is False


def test_dspy_lm_auth_generate_preserves_user_image_blocks(
    monkeypatch, tmp_path: Path
) -> None:
    fake = types.SimpleNamespace(LM=_FakeLM, AuthStorage=_FakeAuthStorage)
    monkeypatch.setitem(sys.modules, "dspy_lm_auth", fake)
    _FakeLM.last_messages = None

    storage = tmp_path / "auth.json"
    storage.write_text("{}\n", encoding="utf-8")
    lm = DspyLMAuthLM(
        model="codex/gpt-5.5",
        auth_provider="codex",
        auth_storage=str(storage),
    )

    lm.generate(
        LMRequest(
            messages=[
                Message(
                    role="user",
                    content=[
                        {"type": "input_text", "text": "describe"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,iVBORw0KGgo=",
                            },
                        },
                    ],
                )
            ]
        )
    )

    assert _FakeLM.last_messages == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "describe"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
                },
            ],
        }
    ]


def test_dspy_lm_auth_codex_route_normalizes_assistant_message_blocks(
    monkeypatch, tmp_path: Path
) -> None:
    fake = types.SimpleNamespace(LM=_FakeLM, AuthStorage=_FakeAuthStorage)
    monkeypatch.setitem(sys.modules, "dspy_lm_auth", fake)
    _FakeLM.last_messages = None

    storage = tmp_path / "auth.json"
    storage.write_text("{}\n", encoding="utf-8")
    lm = DspyLMAuthLM(
        model="codex/gpt-5.5",
        auth_provider="codex",
        auth_storage=str(storage),
    )

    lm.forward(
        messages=[
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
            {
                "role": "assistant",
                "content": [
                    {"type": "input_text", "text": "demo answer"},
                    {"type": "refusal", "refusal": "cannot comply"},
                ],
            },
        ]
    )

    assert _FakeLM.last_messages == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": [{"type": "output_text", "text": "answer"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": "demo answer"},
                {"type": "refusal", "refusal": "cannot comply"},
            ],
        },
    ]


def test_dspy_lm_auth_minimal_response_uses_responses_output_text_blocks() -> None:
    resp = DspyLMAuthMinimalResponse(
        model="dspy-lm-auth/codex/gpt-5.5",
        choices=[{"text": "hello"}],
        usage={},
    )

    assert resp.output[0].content[0].type == "output_text"
    assert resp.output[0].content[0].text == "hello"


def test_dspy_lm_auth_codex_stream_patch_captures_output_text(monkeypatch) -> None:
    fake_module = types.SimpleNamespace(__name__="fake_dspy_lm_auth")
    fake_lm_module = types.ModuleType("fake_dspy_lm_auth.lm")
    setattr(
        fake_lm_module,
        "_consume_codex_response_stream",
        lambda response_stream: response_stream,
    )
    monkeypatch.setitem(sys.modules, "fake_dspy_lm_auth.lm", fake_lm_module)

    DspyLMAuthLM._patch_codex_stream_text_capture(fake_module)

    completed_response = types.SimpleNamespace(usage={"total_tokens": 3})
    completed_event = types.SimpleNamespace(response=completed_response)

    class _Stream:
        completed_response = completed_event

        def __iter__(self):
            return iter(
                [
                    types.SimpleNamespace(delta="auto"),
                    types.SimpleNamespace(delta="plan"),
                    types.SimpleNamespace(
                        type="response.output_text.done", text="ignored"
                    ),
                ]
            )

    consume = getattr(fake_lm_module, "_consume_codex_response_stream")
    captured = consume(_Stream())
    assert isinstance(captured, DspyLMAuthCodexStreamResponse)
    assert captured.output_text == "autoplan"
    assert captured.usage == {"total_tokens": 3}
    assert captured.raw is completed_response


def test_dspy_lm_auth_codex_stream_patch_uses_text_when_completed_response_missing(
    monkeypatch,
) -> None:
    fake_module = types.SimpleNamespace(__name__="fake_dspy_lm_auth_missing_completed")
    fake_lm_module = types.ModuleType("fake_dspy_lm_auth_missing_completed.lm")
    setattr(
        fake_lm_module,
        "_consume_codex_response_stream",
        lambda response_stream: response_stream,
    )
    monkeypatch.setitem(
        sys.modules, "fake_dspy_lm_auth_missing_completed.lm", fake_lm_module
    )

    DspyLMAuthLM._patch_codex_stream_text_capture(fake_module)

    class _Stream:
        completed_response = types.SimpleNamespace(response=None)

        def __iter__(self):
            return iter(
                [
                    types.SimpleNamespace(delta="stage "),
                    types.SimpleNamespace(delta="d"),
                ]
            )

    consume = getattr(fake_lm_module, "_consume_codex_response_stream")
    captured = consume(_Stream())
    assert isinstance(captured, DspyLMAuthCodexStreamResponse)
    assert captured.output_text == "stage d"
    assert captured.usage is None


def test_dspy_lm_auth_codex_stream_patch_raises_on_error_event(
    monkeypatch,
) -> None:
    fake_module = types.SimpleNamespace(__name__="fake_dspy_lm_auth_error_stream")
    fake_lm_module = types.ModuleType("fake_dspy_lm_auth_error_stream.lm")
    setattr(
        fake_lm_module,
        "_consume_codex_response_stream",
        lambda response_stream: response_stream,
    )
    monkeypatch.setitem(
        sys.modules, "fake_dspy_lm_auth_error_stream.lm", fake_lm_module
    )

    DspyLMAuthLM._patch_codex_stream_text_capture(fake_module)

    class _Stream:
        completed_response = types.SimpleNamespace(response=None)

        def __iter__(self):
            return iter(
                [
                    types.SimpleNamespace(delta="partial text"),
                    types.SimpleNamespace(
                        type="response.failed",
                        error=types.SimpleNamespace(message="rate limited"),
                    ),
                ]
            )

    consume = getattr(fake_lm_module, "_consume_codex_response_stream")
    with pytest.raises(RuntimeError, match="rate limited"):
        consume(_Stream())


class _UsageObj:
    def model_dump(self):
        return {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}


class _ContentBlock:
    def __init__(self, text: str):
        self.text = text


class _Message:
    def __init__(self, text: str):
        self.content = [_ContentBlock(text)]


class _ResponseObj:
    def __init__(self, text: str):
        self.output = [_Message(text)]
        self.usage = _UsageObj()


def test_dspy_lm_auth_extracts_output_text_and_usage_from_response_object() -> None:
    resp = _ResponseObj("hello")
    assert DspyLMAuthLM._extract_text(resp) == "hello"
    assert DspyLMAuthLM._extract_usage(resp) == {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
    }


def test_cli_providers_resolve_and_benchmark(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    resolved = runner.invoke(
        app, ["providers", "resolve", "--provider", "stub", "--json"]
    )
    assert resolved.exit_code == 0
    payload = json.loads(resolved.stdout)
    assert payload["provider"] == "stub"
    assert payload["model"] == "stub/echo"

    summary = tmp_path / "providers-benchmark.json"
    bench = runner.invoke(
        app,
        [
            "providers",
            "benchmark",
            "--provider",
            "stub",
            "--repeats",
            "2",
            "--summary-json-out",
            str(summary),
            "--json",
        ],
    )
    assert bench.exit_code == 0
    bench_payload = json.loads(bench.stdout)
    assert bench_payload["ranking"] == ["stub"]
    assert summary.exists()


def test_cli_providers_smoke_json_sanitizes_and_fails_nonzero(monkeypatch) -> None:
    class _FailingProvider:
        model = "fake/model"

        def forward(self, **kwargs):  # noqa: ANN001
            raise RuntimeError("provider failed api_key=supersecret-value")

    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setattr(provider_registry, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        provider_registry,
        "create_from_env",
        lambda default="pi-rpc": _FailingProvider(),
    )

    result = runner.invoke(
        app, ["providers", "smoke", "hi", "--provider", "stub", "--json"]
    )

    assert result.exit_code == 2
    assert "supersecret" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"] == "provider failed api_key=[REDACTED]"


def test_cli_provider_capabilities_match_runtime_json_mode(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "vllm-local")
    monkeypatch.setenv("DSPX_VLLM_JSON_MODE", "1")

    caps_result = runner.invoke(
        app, ["providers", "capabilities", "--provider", "vllm-local", "--json"]
    )
    assert caps_result.exit_code == 0
    caps_payload = json.loads(caps_result.stdout)

    resolved_result = runner.invoke(
        app, ["providers", "resolve", "--provider", "vllm-local", "--json"]
    )
    assert resolved_result.exit_code == 0
    resolved_payload = json.loads(resolved_result.stdout)

    assert caps_payload["json_mode"] is True
    assert caps_payload["json_mode"] == resolved_payload["capabilities"]["json_mode"]
    assert (
        caps_payload["structured_output_format"]
        == resolved_payload["capabilities"]["structured_output_format"]
        == "json"
    )


def test_cli_multi_provider_capabilities_follow_runtime_aggregation(
    monkeypatch,
) -> None:
    saved_registry = dict(provider_registry._REGISTRY)

    class _FakeProvider:
        def __init__(self, model: str, caps: ProviderCapabilities) -> None:
            self.model = model
            self.model_type = "text"
            self.capabilities = caps

    left_caps = ProviderCapabilities(
        supports_tools=False,
        code_exec=False,
        json_mode=True,
        multi_turn=False,
        structured_output_format="json",
    )
    right_caps = ProviderCapabilities(
        supports_tools=True,
        code_exec=False,
        json_mode=False,
        multi_turn=True,
        structured_output_format="none",
        supports_vision=True,
    )

    try:
        provider_registry._REGISTRY.clear()
        provider_registry.register_provider(
            "left",
            lambda: _FakeProvider("left/model", left_caps),
            left_caps,
        )
        provider_registry.register_provider(
            "right",
            lambda: _FakeProvider("right/model", right_caps),
            right_caps,
        )
        provider_registry.register_provider(
            "multi",
            providers_register_multi._factory,
            ProviderCapabilities(
                supports_tools=False,
                code_exec=True,
                json_mode=True,
                multi_turn=False,
                structured_output_format="json",
            ),
        )

        monkeypatch.setenv("MLFLOW_ENABLE", "0")
        monkeypatch.setenv("DSPX_MULTI_PROVIDERS", "left,right")

        caps_result = runner.invoke(
            app, ["providers", "capabilities", "--provider", "multi", "--json"]
        )
        assert caps_result.exit_code == 0
        caps_payload = json.loads(caps_result.stdout)

        resolved_result = runner.invoke(
            app, ["providers", "resolve", "--provider", "multi", "--json"]
        )
        assert resolved_result.exit_code == 0
        resolved_payload = json.loads(resolved_result.stdout)

        assert caps_payload == {
            "provider": "multi",
            "supports_tools": True,
            "code_exec": False,
            "json_mode": False,
            "multi_turn": True,
            "structured_output_format": "none",
            "supports_vision": True,
            "supports_audio": False,
        }
        assert caps_payload == {
            "provider": "multi",
            **resolved_payload["capabilities"],
        }
    finally:
        provider_registry._REGISTRY.clear()
        provider_registry._REGISTRY.update(saved_registry)


def test_truthy_strips_whitespace_and_falsey_variants(monkeypatch) -> None:
    for raw in ("0 ", " false", "false ", " no ", ""):
        monkeypatch.setenv("DSPX_BOOL_TEST", raw)
        assert _truthy("DSPX_BOOL_TEST", True) is False

    monkeypatch.setenv("DSPX_BOOL_TEST", " 1 ")
    assert _truthy("DSPX_BOOL_TEST", False) is True


def test_ensure_default_providers_preserves_custom_openai_compatible(
    monkeypatch,
) -> None:
    saved_registry = dict(provider_registry._REGISTRY)
    try:
        provider_registry._REGISTRY.clear()
        custom_caps = ProviderCapabilities(
            supports_tools=True,
            code_exec=True,
            json_mode=True,
            multi_turn=False,
            structured_output_format="json",
        )
        provider_registry.register_provider(
            "openai-compatible",
            lambda: "custom-openai-compatible",
            custom_caps,
        )

        monkeypatch.setenv("DSPX_VLLM_JSON_MODE", "1")
        ensure_default_providers()

        reg = available()
        assert reg["openai-compatible"].factory() == "custom-openai-compatible"
        assert (
            reg["openai-compatible"].capabilities.model_dump()
            == custom_caps.model_dump()
        )
        assert "vllm-local" in reg
        assert reg["vllm-local"].capabilities.json_mode is True
    finally:
        provider_registry._REGISTRY.clear()
        provider_registry._REGISTRY.update(saved_registry)


def test_ensure_default_providers_preserves_custom_vllm_local(
    monkeypatch,
) -> None:
    saved_registry = dict(provider_registry._REGISTRY)
    try:
        provider_registry._REGISTRY.clear()
        custom_caps = ProviderCapabilities(
            supports_tools=False,
            code_exec=False,
            json_mode=False,
            multi_turn=False,
            structured_output_format="none",
        )
        provider_registry.register_provider(
            "vllm-local",
            lambda: "custom-vllm-local",
            custom_caps,
        )

        monkeypatch.setenv("DSPX_OPENAI_COMPAT_JSON_MODE", "1")
        ensure_default_providers()

        reg = available()
        assert reg["vllm-local"].factory() == "custom-vllm-local"
        assert reg["vllm-local"].capabilities.model_dump() == custom_caps.model_dump()
        assert "openai-compatible" in reg
        assert reg["openai-compatible"].capabilities.json_mode is True
    finally:
        provider_registry._REGISTRY.clear()
        provider_registry._REGISTRY.update(saved_registry)


def test_dspy_lm_auth_factory_accepts_codex_reasoning_effort_without_max_tokens(
    monkeypatch,
) -> None:
    from dspx.providers_register_dspy_lm_auth import _factory

    monkeypatch.setenv("DSPX_LM_AUTH_MODEL", "codex/gpt-5.5")
    monkeypatch.setenv("DSPX_LM_AUTH_REASONING_EFFORT", "low")
    monkeypatch.setenv("DSPX_LM_AUTH_MAX_TOKENS", "2048")

    lm = _factory()

    assert lm.kwargs["reasoning_effort"] == "low"
    assert "max_tokens" not in lm.kwargs


def test_dspy_lm_auth_factory_rejects_invalid_codex_reasoning_effort(
    monkeypatch,
) -> None:
    from dspx.providers_register_dspy_lm_auth import _factory

    monkeypatch.setenv("DSPX_LM_AUTH_MODEL", "codex/gpt-5.5")
    monkeypatch.setenv("DSPX_LM_AUTH_REASONING_EFFORT", "minimal")

    with pytest.raises(ValueError, match="DSPX_LM_AUTH_REASONING_EFFORT"):
        _factory()


def test_run_receipt_includes_redacted_provider_details(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "dspy-lm-auth")
    monkeypatch.setenv("DSPX_LM_AUTH_MODEL", "codex/gpt-5.4-mini")
    monkeypatch.setenv("DSPX_LM_AUTH_PROVIDER", "codex")
    auth_path = tmp_path / "auth.json"
    auth_path.write_text('{"openai-codex": {"access": "secret"}}\n', encoding="utf-8")
    monkeypatch.setenv("DSPX_LM_AUTH_STORAGE", str(auth_path))

    out = tmp_path / "x.py"
    out.write_text("print('x')\n", encoding="utf-8")
    receipt = build_run_receipt(
        run_kind="codegen",
        output_path=out,
        output_hash="abc123def456",
        template_version="t1",
        cache_key="k",
        cache_file="c",
        cache_enabled=True,
        replay_inputs={"spec": "demo"},
    )
    details = receipt["provider_details"]
    assert details["provider"] == "dspy-lm-auth"
    assert details["requested_model"] == "codex/gpt-5.4-mini"
    assert details["auth_storage"] == "[REDACTED]"
    assert details["auth_storage_exists"] == "[REDACTED]"
    assert "secret" not in json.dumps(details)


def test_cli_optimize_gepa_uses_configured_provider_defaults(
    monkeypatch, tmp_path: Path
) -> None:
    import dspx.services.optimize_service as optimize_service

    program = tmp_path / "prog.py"
    program.write_text("def build_student():\n    return object()\n", encoding="utf-8")
    train = tmp_path / "train.csv"
    train.write_text("question,answer\nq,a\n", encoding="utf-8")
    out = tmp_path / "out"

    captured: dict[str, object] = {}

    def _fake_run_gepa_optimize(**kwargs):
        captured.update(kwargs)
        out.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(out_dir=out)

    monkeypatch.setattr(optimize_service, "run_gepa_optimize", _fake_run_gepa_optimize)
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_OPTIMIZE_STUDENT_PROVIDER", "vllm-local")
    monkeypatch.setenv("DSPX_OPTIMIZE_REFLECTION_PROVIDER", "dspy-lm-auth")

    result = runner.invoke(
        app,
        [
            "optimize",
            "gepa",
            "--program",
            str(program),
            "--train",
            str(train),
            "--out",
            str(out),
            "--max-metric-calls",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert captured["student_provider"] == "vllm-local"
    assert captured["reflection_provider"] == "dspy-lm-auth"


def test_cli_optimize_gepa_loads_config_before_resolving_provider_defaults(
    monkeypatch, tmp_path: Path
) -> None:
    import dspx.services.optimize_service as optimize_service

    program = tmp_path / "prog.py"
    program.write_text("def build_student():\n    return object()\n", encoding="utf-8")
    train = tmp_path / "train.csv"
    train.write_text("question,answer\nq,a\n", encoding="utf-8")
    out = tmp_path / "out"
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [provider]
        name = "vllm-local"

        [optimize]
        student_provider = "vllm-local"
        reflection_provider = "dspy-lm-auth"
        """,
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_run_gepa_optimize(**kwargs):
        captured.update(kwargs)
        out.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(out_dir=out)

    monkeypatch.setattr(optimize_service, "run_gepa_optimize", _fake_run_gepa_optimize)
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_CONFIG", str(cfg))
    monkeypatch.delenv("DSPX_PROVIDER", raising=False)
    monkeypatch.delenv("DSPX_OPTIMIZE_STUDENT_PROVIDER", raising=False)
    monkeypatch.delenv("DSPX_OPTIMIZE_REFLECTION_PROVIDER", raising=False)

    result = runner.invoke(
        app,
        [
            "optimize",
            "gepa",
            "--program",
            str(program),
            "--train",
            str(train),
            "--out",
            str(out),
            "--max-metric-calls",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert captured["student_provider"] == "vllm-local"
    assert captured["reflection_provider"] == "dspy-lm-auth"


def test_optimize_manifest_includes_provider_runtime_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_TRUSTED_PROGRAM_ROOTS", str(tmp_path))

    program = tmp_path / "prog.py"
    program.write_text(
        "\n".join(
            [
                "import dspy",
                "",
                "class Student(dspy.Module):",
                "    def __init__(self):",
                "        super().__init__()",
                "        self.predict = dspy.Predict('question -> answer')",
                "",
                "    def forward(self, question: str) -> dspy.Prediction:",
                "        return self.predict(question=question)",
                "",
                "def build_student() -> dspy.Module:",
                "    return Student()",
                "",
            ]
        ),
        encoding="utf-8",
    )
    train = tmp_path / "train.csv"
    train.write_text("question,answer\nWhat is 2+2?,4\n", encoding="utf-8")
    out_dir = tmp_path / "optimized"

    run_gepa_optimize(
        program_path=program,
        train_path=train,
        out_dir=out_dir,
        auto=None,
        max_metric_calls=1,
        seed=0,
        student_provider="stub",
        reflection_provider="stub",
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    student = manifest["providers"]["student"]
    assert student["provider"] == "stub"
    assert student["capabilities"]["code_exec"] is False
    assert student["runtime"] == {}


def test_cli_fails_closed_for_missing_dspx_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_CONFIG", str(tmp_path / "missing.toml"))

    result = runner.invoke(app, ["providers", "list", "--json"])

    assert result.exit_code == 2
    assert "DSPX_CONFIG path not found" in result.output
