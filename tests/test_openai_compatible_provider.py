# summary: "Proves loopback HTTP, exact payload, policy, effect, retry, and receipt invariants."
# read_when:
#   - "Changing the typed OpenAI-compatible provider or its adapter/registry boundary."

from __future__ import annotations

import inspect
import json
from threading import Event, Thread
from typing import Any

import dspy
from dspy.core.types import LMMessage, LMTextPart
import httpx
import pytest

import dspx.openai_compatible_provider as provider_module
from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.openai_compatible_provider import OpenAICompatibleProvider
from dspx.provider_contract import (
    EffectDisposition,
    ProviderInvocationError,
    ProviderMessage,
    ProviderRequest,
)
from dspx.provider_registry import (
    create,
    create_configured,
    create_from_env,
    supported_provider_names,
)
from dspx.services.program_runtime_episode import _validate_provider_evidence
from dspx.provider_runtime import (
    invoke_provider,
    provider_attempts_from_instance,
    provider_effect_evidence_from_instance,
    provider_metadata_from_instance,
)


@pytest.fixture(autouse=True)
def _network_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    for key in (
        "DSPX_POLICY_ALLOWED_PROVIDERS",
        "DSPX_POLICY_DISALLOWED_PROVIDERS",
        "DSPX_POLICY_ALLOWED_CAPS",
        "DSPX_POLICY_DISALLOWED_CAPS",
        "DSPX_POLICY_MAX_TIMEOUT",
        "DSPX_OPENAI_COMPAT_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def _payload(*, usage: object = None, model: str = "local-model") -> dict[str, object]:
    payload: dict[str, object] = {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": "local answer"}}],
    }
    if usage is not None:
        payload["usage"] = usage
    return payload


def _request() -> ProviderRequest:
    return ProviderRequest(
        model="local-model",
        messages=(
            ProviderMessage(role="system", text="be concise"),
            ProviderMessage(role="user", text="hello"),
        ),
    )


def _provider(
    response: tuple[int, object] | Exception,
    *,
    base_url: str = "http://127.0.0.1:8000/v1",
    timeout: float = 30.0,
) -> tuple[OpenAICompatibleProvider, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if isinstance(response, Exception):
            raise response
        status, payload = response
        return httpx.Response(status, json=payload, request=request)

    provider = OpenAICompatibleProvider(
        base_url=base_url,
        model="local-model",
        timeout=timeout,
        _transport=httpx.MockTransport(handler),
    )
    return provider, requests


def _typed_request() -> dspy.LMRequest:
    return dspy.LMRequest(
        model="local-model",
        messages=[
            LMMessage(
                role="user",
                parts=[LMTextPart(text="secret prompt value")],
            )
        ],
    )


def test_exact_payload_success_usage_and_attempt_projection() -> None:
    provider, requests = _provider(
        (
            200,
            _payload(
                usage={
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": 5,
                }
            ),
        )
    )

    result = provider.invoke(_request())

    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "http://127.0.0.1:8000/v1/chat/completions"
    assert json.loads(requests[0].content) == {
        "model": "local-model",
        "messages": [
            {"role": "system", "content": "be concise"},
            {"role": "user", "content": "hello"},
        ],
    }
    assert result.text == "local answer"
    assert result.usage == {
        "input_tokens": 2,
        "output_tokens": 3,
        "total_tokens": 5,
    }
    lm = DSPyTypedLMAdapter(provider)
    assert provider_attempts_from_instance(lm) == [
        {
            "provider_kind": "openai-compatible",
            "requested_model": "local-model",
            "observed_model": "local-model",
            "dispatch_count": 1,
            "effect_disposition": "completed_success",
        }
    ]


@pytest.mark.parametrize(
    "base_url",
    [
        "https://127.0.0.1:8000/v1",
        "http://localhost:8000/v1",
        "http://192.0.2.1:8000/v1",
        "http://user@127.0.0.1:8000/v1",
        "http://127.0.0.1:8000/v1?x=1",
        "http://127.0.0.1:8000/v1#x",
        " http://127.0.0.1:8000/v1",
        "http://127.0.0.1:0/v1",
        "http://[::1%25lo]:8000/v1",
        "http://127.0.0.1:8000/v1//models",
        "http://127.0.0.1:8000/v1/../models",
        "http://127.0.0.1:8000/v1/%2e%2e/models",
        "http://127.0.0.1:8000/v1/chat/completions",
        "http://127.0.0.1:8000/v1;mode=x",
    ],
)
def test_adversarial_targets_reject_before_transport(base_url: str) -> None:
    dispatched = 0

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        nonlocal dispatched
        dispatched += 1
        raise AssertionError("must not dispatch")

    with pytest.raises(ValueError):
        OpenAICompatibleProvider(
            base_url=base_url,
            model="local-model",
            _transport=httpx.MockTransport(handler),
        )
    assert dispatched == 0


@pytest.mark.parametrize("model", ["", " local", "local model", "local\nmodel"])
def test_ambiguous_model_rejects_before_transport(model: str) -> None:
    with pytest.raises(ValueError, match="model"):
        OpenAICompatibleProvider(
            base_url="http://127.0.0.1/v1",
            model=model,
            _transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        )


def test_owned_client_has_no_ambient_auth_cookies_redirects_or_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, request=request)
    )

    def transport_factory(**kwargs: Any) -> httpx.BaseTransport:
        captured.update(kwargs)
        return transport

    monkeypatch.setattr(provider_module.httpx, "HTTPTransport", transport_factory)
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1/v1", model="local-model"
    )

    assert captured == {"trust_env": False, "retries": 0}
    assert provider._client.follow_redirects is False
    assert provider._client._auth is None
    assert list(provider._client.cookies.jar) == []
    assert "client" not in inspect.signature(create).parameters
    assert "client" not in inspect.signature(create_from_env).parameters


def test_policy_opt_in_provider_and_capability_checks_precede_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in (
        ("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "0"),
        ("DSPX_POLICY_DISALLOWED_PROVIDERS", "openai-compatible"),
        ("DSPX_POLICY_DISALLOWED_CAPS", "network.mutate"),
    ):
        provider, requests = _provider((200, _payload()))
        monkeypatch.setenv(key, value)
        with pytest.raises(ProviderInvocationError) as exc_info:
            provider.invoke(_request())
        assert exc_info.value.disposition is EffectDisposition.PREFLIGHT_REJECTED
        assert requests == []
        assert provider.provider_events[-1].dispatch_count == 0
        monkeypatch.delenv(key, raising=False)


def test_policy_timeout_caps_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_POLICY_MAX_TIMEOUT", "2.5")
    provider, _ = _provider((200, _payload()), timeout=30.0)
    lm = DSPyTypedLMAdapter(provider)

    assert provider.effective_timeout == 2.5
    metadata = provider_metadata_from_instance("openai-compatible", lm)
    assert set(metadata) == {
        "provider",
        "model",
        "model_type",
        "typed_contract",
        "capabilities",
        "runtime",
    }
    assert metadata["runtime"] == {
        "provider_kind": "openai-compatible",
        "base_endpoint": "http://127.0.0.1:8000/v1",
        "effective_timeout": 2.5,
    }


@pytest.mark.parametrize("status", [300, 302, 400, 500])
def test_fully_read_non_success_is_completed_failure_without_retry(status: int) -> None:
    provider, requests = _provider((status, {"error": "secret detail"}))

    with pytest.raises(ProviderInvocationError) as exc_info:
        provider.invoke(_request())

    assert exc_info.value.disposition is EffectDisposition.COMPLETED_FAILURE
    assert str(exc_info.value) == "DSPx openai-compatible provider invocation failed"
    assert len(requests) == 1
    assert provider.provider_events[-1].dispatch_count == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "other", "choices": []},
        {"model": "local-model", "choices": []},
        {
            "model": "local-model",
            "choices": [{"message": {"role": "user", "content": "wrong"}}],
        },
        {
            "model": "local-model",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "answer",
                        "tool_calls": [],
                    }
                }
            ],
        },
        {**_payload(), "usage": None},
        {**_payload(), "usage": {"total_tokens": 1}},
        {
            **_payload(),
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 3,
                "total_tokens": 4,
            },
        },
        {
            **_payload(),
            "usage": {
                "prompt_tokens": 1_000_000_001,
                "completion_tokens": 0,
                "total_tokens": 1_000_000_001,
            },
        },
    ],
)
def test_fully_read_malformed_success_is_completed_failure(payload: object) -> None:
    provider, requests = _provider((200, payload))

    with pytest.raises(ProviderInvocationError) as exc_info:
        provider.invoke(_request())

    assert exc_info.value.disposition is EffectDisposition.COMPLETED_FAILURE
    assert len(requests) == 1


class FailingStream(httpx.SyncByteStream):
    def __iter__(self):
        raise httpx.ReadError("secret read failure")
        yield b""  # pragma: no cover


def test_transport_and_read_failures_are_indeterminate_without_retry() -> None:
    cases: list[Exception | httpx.Response] = [
        httpx.ConnectError("secret transport failure"),
        httpx.Response(200, stream=FailingStream()),
    ]
    for case in cases:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if isinstance(case, Exception):
                raise case
            return httpx.Response(200, stream=FailingStream(), request=request)

        provider = OpenAICompatibleProvider(
            base_url="http://127.0.0.1/v1",
            model="local-model",
            _transport=httpx.MockTransport(handler),
        )
        with pytest.raises(ProviderInvocationError) as exc_info:
            provider.invoke(_request())
        assert exc_info.value.disposition is EffectDisposition.EFFECT_INDETERMINATE
        assert len(requests) == 1
        assert provider.provider_events[-1].dispatch_count == 1


def test_endpoint_is_revalidated_immediately_before_dispatch() -> None:
    provider, requests = _provider((200, _payload()))
    provider._base_url = "http://192.0.2.1/v1"

    with pytest.raises(ProviderInvocationError) as exc_info:
        provider.invoke(_request())

    assert exc_info.value.disposition is EffectDisposition.PREFLIGHT_REJECTED
    assert requests == []


def test_adapter_failure_is_constant_redacted_and_cause_free() -> None:
    provider, requests = _provider((200, {"secret": "credential-value"}))
    lm = DSPyTypedLMAdapter(provider)

    with pytest.raises(dspy.LMTransportError) as exc_info:
        lm(request=_typed_request())

    assert exc_info.value.code == "completed_failure"
    assert "credential-value" not in repr(exc_info.value)
    assert "secret prompt value" not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert len(requests) == 1


def test_attempt_history_is_bounded_and_truncation_is_explicit() -> None:
    provider, requests = _provider((200, _payload()))
    for _ in range(65):
        provider.invoke(_request())
    evidence = provider_effect_evidence_from_instance(DSPyTypedLMAdapter(provider))
    assert len(requests) == 65
    assert len(provider.provider_events) == 64
    assert evidence["attempt_total"] == 65
    assert evidence["attempts_truncated"] is True
    assert evidence["terminal_effect"] == "completed_success"


def test_indeterminate_latches_without_a_second_attempt_or_dispatch() -> None:
    provider, requests = _provider(httpx.ConnectError("api_key=secret-value"))
    lm = DSPyTypedLMAdapter(provider)

    for _ in range(2):
        with pytest.raises(ProviderInvocationError) as exc_info:
            provider.invoke(_request())
        assert exc_info.value.disposition is EffectDisposition.EFFECT_INDETERMINATE
        assert "secret-value" not in repr(exc_info.value)

    evidence = provider_effect_evidence_from_instance(lm)
    assert len(requests) == 1
    assert evidence == {
        "schema_version": "dspx-provider-effect-evidence-v1",
        "attempt_total": 1,
        "attempts_truncated": False,
        "terminal_effect": "effect_indeterminate",
        "attempts": [
            {
                "provider_kind": "openai-compatible",
                "requested_model": "local-model",
                "observed_model": None,
                "dispatch_count": 1,
                "effect_disposition": "effect_indeterminate",
            }
        ],
    }


def test_mismatched_provider_controlled_model_is_never_retained() -> None:
    secret = "api_key=secret-value"
    provider, _ = _provider((200, _payload(model=secret)))
    with pytest.raises(ProviderInvocationError) as exc_info:
        provider.invoke(_request())
    evidence = provider_effect_evidence_from_instance(DSPyTypedLMAdapter(provider))
    assert evidence["attempts"][0]["observed_model"] is None
    assert secret not in repr(exc_info.value)
    assert secret not in json.dumps(evidence)


def test_registry_config_is_explicit_secret_free_and_has_no_empty_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_MODEL", "ambient-model")
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_API_BASE", "http://127.0.0.1/v1")
    assert supported_provider_names() == ("stub", "openai-compatible")
    with pytest.raises(ValueError, match="base URL|model"):
        create_configured("openai-compatible", model="", base_url="")
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_API_KEY", "forbidden-secret")
    with pytest.raises(ValueError, match="credentials are unsupported"):
        create_configured("openai-compatible")


def test_runtime_invocation_preserves_usage_without_response_facsimile() -> None:
    provider, requests = _provider(
        (
            200,
            _payload(
                usage={
                    "prompt_tokens": 4,
                    "completion_tokens": 6,
                    "total_tokens": 10,
                }
            ),
        )
    )
    lm = DSPyTypedLMAdapter(provider)

    text, usage = invoke_provider(lm, prompt="hello")

    assert text == "local answer"
    assert usage == {
        "input_tokens": 4,
        "output_tokens": 6,
        "total_tokens": 10,
    }
    assert len(requests) == 1


def test_adapter_postprocessing_indeterminate_reclassifies_and_latches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, requests = _provider((200, _payload()))
    lm = DSPyTypedLMAdapter(provider)

    def fail_response(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise ValueError("api_key=secret-value")

    monkeypatch.setattr(dspy.LMResponse, "from_text", fail_response)
    for _ in range(2):
        with pytest.raises(dspy.LMTransportError) as exc_info:
            lm(request=_typed_request())
        assert exc_info.value.code == "effect_indeterminate"
        assert "secret-value" not in repr(exc_info.value)

    evidence = provider_effect_evidence_from_instance(lm)
    assert len(requests) == 1
    assert evidence["attempt_total"] == 1
    assert evidence["terminal_effect"] == "effect_indeterminate"
    assert evidence["attempts"][0]["effect_disposition"] == "effect_indeterminate"


def test_provider_metadata_canonicalizes_registry_style_names() -> None:
    provider, _ = _provider((200, _payload()))
    metadata = provider_metadata_from_instance(
        "  OpenAI-Compatible  ", DSPyTypedLMAdapter(provider)
    )
    assert metadata["provider"] == "openai-compatible"


def _validated_runtime_evidence(lm: DSPyTypedLMAdapter) -> dict[str, Any]:
    evidence = {
        "status": "configured",
        "metadata": provider_metadata_from_instance("openai-compatible", lm),
        "effect_evidence": provider_effect_evidence_from_instance(lm),
    }
    _validate_provider_evidence(evidence)
    return evidence["effect_evidence"]


def test_concurrent_transport_indeterminate_blocks_second_adapter_dispatch() -> None:
    entered = Event()
    release = Event()
    second_started = Event()
    second_finished = Event()
    requests: list[httpx.Request] = []
    codes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        entered.set()
        assert release.wait(5)
        raise httpx.ConnectError("indeterminate", request=request)

    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:8000/v1",
        model="local-model",
        _transport=httpx.MockTransport(handler),
    )
    lm = DSPyTypedLMAdapter(provider)

    def invoke(first: bool) -> None:
        if not first:
            second_started.set()
        try:
            lm(request=_typed_request())
        except dspy.LMTransportError as exc:
            codes.append(str(exc.code))
        finally:
            if not first:
                second_finished.set()

    first = Thread(target=invoke, args=(True,))
    second = Thread(target=invoke, args=(False,))
    first.start()
    assert entered.wait(5)
    second.start()
    assert second_started.wait(5)
    assert not second_finished.wait(0.05)
    release.set()
    first.join(5)
    second.join(5)

    evidence = _validated_runtime_evidence(lm)
    assert not first.is_alive() and not second.is_alive()
    assert codes == ["effect_indeterminate", "effect_indeterminate"]
    assert len(requests) == 1
    assert evidence["attempt_total"] == 1
    assert evidence["terminal_effect"] == "effect_indeterminate"
    assert evidence["attempts"][0]["effect_disposition"] == "effect_indeterminate"


def test_adapter_postprocessing_lock_blocks_concurrent_direct_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    postprocessing = Event()
    release = Event()
    direct_started = Event()
    direct_finished = Event()
    requests: list[httpx.Request] = []
    outcomes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_payload(), request=request)

    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:8000/v1",
        model="local-model",
        _transport=httpx.MockTransport(handler),
    )
    lm = DSPyTypedLMAdapter(provider)

    def fail_response(*args: object, **kwargs: object) -> object:
        del args, kwargs
        postprocessing.set()
        assert release.wait(5)
        raise ValueError("postprocessing failure")

    monkeypatch.setattr(dspy.LMResponse, "from_text", fail_response)

    def adapter_call() -> None:
        try:
            lm(request=_typed_request())
        except dspy.LMTransportError as exc:
            outcomes.append(f"adapter:{exc.code}")

    def direct_call() -> None:
        direct_started.set()
        try:
            provider.invoke(_request())
        except ProviderInvocationError as exc:
            outcomes.append(f"direct:{exc.disposition.value}")
        finally:
            direct_finished.set()

    first = Thread(target=adapter_call)
    second = Thread(target=direct_call)
    first.start()
    assert postprocessing.wait(5)
    second.start()
    assert direct_started.wait(5)
    assert not direct_finished.wait(0.05)
    release.set()
    first.join(5)
    second.join(5)

    evidence = _validated_runtime_evidence(lm)
    assert not first.is_alive() and not second.is_alive()
    assert sorted(outcomes) == [
        "adapter:effect_indeterminate",
        "direct:effect_indeterminate",
    ]
    assert len(requests) == 1
    assert evidence["attempt_total"] == 1
    assert evidence["terminal_effect"] == "effect_indeterminate"
    assert evidence["attempts"][-1]["effect_disposition"] == "effect_indeterminate"
