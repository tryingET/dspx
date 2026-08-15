# summary: "Proves the exact DSPy 3.3 typed adapter, offline provider port, and pre-effect rejection contract."
# read_when:
#   - "Changing typed LM translation, provider effects, state/copy/history, or DSPy callbacks."

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
import inspect
from threading import Event, Thread
from typing import Any

import dspy
import pytest

from dspx.provider_contract import (
    EffectDisposition,
    ProviderInvocationError,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
)
from dspx.stub_provider import StubProvider

_TYPED_LM_AVAILABLE = hasattr(dspy, "LMRequest")
pytestmark = pytest.mark.skipif(
    not _TYPED_LM_AVAILABLE,
    reason="DSPy 3.3 typed-LM contract is proved in the retained exact target",
)

if _TYPED_LM_AVAILABLE:
    from dspy import (
        BaseLM,
        LMRequest,
        LMResponse,
        LMTransportError,
        LMUnsupportedFeatureError,
    )
    from dspy.core.types import LMConfig, LMMessage, LMTextPart
    from dspy.utils.callback import BaseCallback

    from dspx.dspy_typed_lm import DSPyTypedLMAdapter
else:

    class _Unavailable:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

    BaseLM = BaseCallback = LMConfig = LMMessage = LMTextPart = _Unavailable
    LMRequest = LMResponse = DSPyTypedLMAdapter = _Unavailable
    LMTransportError = LMUnsupportedFeatureError = Exception


def _request(
    text: str = "hello",
    *,
    metadata: dict[str, Any] | None = None,
    config: LMConfig | None = None,
) -> LMRequest:
    return LMRequest(
        model="stub/echo",
        messages=[
            LMMessage(
                role="user",
                parts=[LMTextPart(text=text)],
            )
        ],
        metadata=metadata or {},
        config=config or LMConfig(),
    )


def test_typed_adapter_is_the_only_dspy_subclass_in_the_new_kernel() -> None:
    assert issubclass(DSPyTypedLMAdapter, BaseLM)
    assert not issubclass(StubProvider, BaseLM)
    assert list(inspect.signature(DSPyTypedLMAdapter.forward).parameters) == [
        "self",
        "request",
    ]
    assert DSPyTypedLMAdapter.forward_contract == "typed_lm"


def test_explicit_typed_request_returns_typed_response_and_effect_disposition() -> None:
    provider = StubProvider()
    lm = DSPyTypedLMAdapter(provider)

    response = lm(request=_request())

    assert isinstance(response, LMResponse)
    assert response.model == "stub/echo"
    assert response.text == "stub: hello"
    assert response.provider_data == {
        "provider_kind": "stub",
        "effect_disposition": "completed_success",
    }
    assert response.usage is not None
    assert response.usage.input_tokens == 0
    assert response.usage.output_tokens == 0
    assert response.usage.total_tokens == 0
    assert len(provider.provider_events) == 1
    assert (
        provider.provider_events[0].disposition is EffectDisposition.COMPLETED_SUCCESS
    )


def test_ordinary_dspy_call_converts_only_at_the_public_dspy_boundary() -> None:
    provider = StubProvider()
    lm = DSPyTypedLMAdapter(provider)

    assert lm(prompt="hello") == ["stub: hello"]
    assert len(provider.provider_events) == 1


@pytest.mark.parametrize(
    "request_kind,feature",
    [
        ("metadata", "request_metadata"),
        ("config", "generation_config"),
    ],
)
def test_unsupported_typed_features_reject_before_provider_effect(
    request_kind: str,
    feature: str,
) -> None:
    provider = StubProvider()
    lm = DSPyTypedLMAdapter(provider)
    request = (
        _request(metadata={"trace": "forbidden"})
        if request_kind == "metadata"
        else _request(config=LMConfig(temperature=0.2))
    )

    with pytest.raises(LMUnsupportedFeatureError) as exc_info:
        lm(request=request)

    assert feature in exc_info.value.features
    assert provider.provider_events == ()


def test_async_rejects_before_provider_effect_without_thread_fallback() -> None:
    provider = StubProvider()
    lm = DSPyTypedLMAdapter(provider)

    with pytest.raises(LMUnsupportedFeatureError) as exc_info:
        asyncio.run(lm.acall(request=_request()))

    assert exc_info.value.features == ["async"]
    assert provider.provider_events == ()


def test_unknown_provider_exception_is_effect_indeterminate_and_redacted() -> None:
    class BrokenProvider:
        model = "stub/echo"

        def invoke(self, request: ProviderRequest) -> Any:
            del request
            raise RuntimeError("secret provider detail")

        def dump_state(self) -> dict[str, object]:
            return {"kind": "broken"}

    callback = _RecordingCallback()
    lm = DSPyTypedLMAdapter(BrokenProvider(), callbacks=[callback])

    with pytest.raises(LMTransportError) as exc_info:
        lm(request=_request())

    assert exc_info.value.code == "effect_indeterminate"
    assert "secret provider detail" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert callback.events[-1] == ("end", exc_info.value)


def test_hostile_provider_data_fails_post_effect_as_redacted_indeterminate() -> None:
    class LeakyProvider:
        model = "stub/echo"

        def __init__(self) -> None:
            self.invocations = 0

        def invoke(self, request: ProviderRequest) -> ProviderResult:
            del request
            self.invocations += 1
            return ProviderResult(
                text="completed text",
                model=self.model,
                effect_disposition=EffectDisposition.COMPLETED_SUCCESS,
                provider_data={"api_key": "secret provider value"},
            )

        def dump_state(self) -> dict[str, object]:
            return {"kind": "leaky"}

    provider = LeakyProvider()
    callback = _RecordingCallback()
    lm = DSPyTypedLMAdapter(provider, callbacks=[callback])

    with pytest.raises(LMTransportError) as exc_info:
        lm(request=_request())

    assert provider.invocations == 1
    assert exc_info.value.code == "effect_indeterminate"
    assert "secret" not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert callback.events[-1] == ("end", exc_info.value)


def test_hostile_mapping_exception_cannot_bypass_effect_redaction() -> None:
    class HostileMapping(Mapping[str, Any]):
        def __getitem__(self, key: str) -> Any:
            del key
            raise LMTransportError("secret mapping value", code="secret_code")

        def __iter__(self) -> Iterator[str]:
            raise LMTransportError("secret mapping iterator", code="secret_code")

        def __len__(self) -> int:
            return 1

    class HostileMappingProvider:
        model = "stub/echo"

        def invoke(self, request: ProviderRequest) -> ProviderResult:
            del request
            return ProviderResult(
                text="completed text",
                model=self.model,
                effect_disposition=EffectDisposition.COMPLETED_SUCCESS,
                provider_data=HostileMapping(),
            )

        def dump_state(self) -> dict[str, object]:
            return {"kind": "hostile"}

    with pytest.raises(LMTransportError) as exc_info:
        DSPyTypedLMAdapter(HostileMappingProvider())(request=_request())

    assert exc_info.value.code == "effect_indeterminate"
    assert "secret" not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_stub_canary_rejects_nonzero_or_incomplete_usage_after_effect() -> None:
    class NonzeroUsageProvider:
        model = "stub/echo"

        def invoke(self, request: ProviderRequest) -> ProviderResult:
            del request
            return ProviderResult(
                text="completed text",
                model=self.model,
                effect_disposition=EffectDisposition.COMPLETED_SUCCESS,
                usage={"total_tokens": 1},
                provider_data={"provider_kind": "stub"},
            )

        def dump_state(self) -> dict[str, object]:
            return {"kind": "nonzero"}

    with pytest.raises(LMTransportError) as exc_info:
        DSPyTypedLMAdapter(NonzeroUsageProvider())(request=_request())

    assert exc_info.value.code == "effect_indeterminate"


def test_state_dump_rejects_non_stub_before_provider_state_access() -> None:
    class SecretStateProvider:
        model = "stub/echo"

        def __init__(self) -> None:
            self.state_accessed = False

        def invoke(self, request: ProviderRequest) -> ProviderResult:
            del request
            raise AssertionError("not invoked")

        def dump_state(self) -> dict[str, object]:
            self.state_accessed = True
            return {"kind": "secret", "api_key": "secret"}

    provider = SecretStateProvider()
    lm = DSPyTypedLMAdapter(provider)

    with pytest.raises(LMUnsupportedFeatureError) as exc_info:
        lm.dump_state()

    assert exc_info.value.features == ["state:provider"]
    assert provider.state_accessed is False


def test_declared_provider_failure_preserves_exact_effect_disposition() -> None:
    class FailedProvider:
        model = "stub/echo"

        def invoke(self, request: ProviderRequest) -> Any:
            del request
            raise ProviderInvocationError(
                "safe failure",
                disposition=EffectDisposition.COMPLETED_FAILURE,
                provider="failed",
            )

        def dump_state(self) -> dict[str, object]:
            return {"kind": "failed"}

    lm = DSPyTypedLMAdapter(FailedProvider())

    with pytest.raises(LMTransportError) as exc_info:
        lm(request=_request())

    assert exc_info.value.code == "completed_failure"


def test_state_round_trip_is_allowlisted_secret_free_and_trusted() -> None:
    lm = DSPyTypedLMAdapter(StubProvider("stub/custom"), cache=False)
    state = lm.dump_state()

    assert state == {
        "_dspy_lm_class": "dspx.dspy_typed_lm.DSPyTypedLMAdapter",
        "schema": "dspx-dspy-typed-lm-state-v1",
        "model": "stub/custom",
        "model_type": "text",
        "cache": False,
        "num_retries": 0,
        "provider_state": {
            "schema": "dspx-provider-state-v1",
            "kind": "stub",
            "model": "stub/custom",
        },
    }
    assert "secret" not in repr(state).lower()

    restored = BaseLM.load_state(state, allow_custom_lm_class=True)

    assert isinstance(restored, DSPyTypedLMAdapter)
    response = restored(
        request=LMRequest(
            model="stub/custom",
            messages=[LMMessage(role="user", parts=[LMTextPart(text="state")])],
        )
    )
    assert response.text == "stub: state"


def test_copy_resets_dspy_history_and_does_not_alias_provider_events() -> None:
    provider = StubProvider()
    lm = DSPyTypedLMAdapter(provider)
    lm(request=_request("original"))
    assert lm.history

    with pytest.raises(LMUnsupportedFeatureError) as exc_info:
        lm.copy(model="stub/other")
    assert exc_info.value.features == ["copy:model"]
    assert len(provider.provider_events) == 1

    for key, value in (("num_retries", 7), ("model_type", "chat")):
        with pytest.raises(LMUnsupportedFeatureError) as drift_info:
            lm.copy(**{key: value})
        assert drift_info.value.features == [f"copy:{key}"]
    with pytest.raises(TypeError, match="cache must be a boolean"):
        lm.copy(cache="no")
    assert lm.num_retries == 0
    assert lm.model_type == "text"

    copied = lm.copy(cache=False)

    assert copied is not lm
    assert copied.cache is False
    assert copied.provider is not provider
    assert copied.history == []
    assert copied.callbacks is not lm.callbacks
    assert copied.kwargs is not lm.kwargs
    assert copied.provider.provider_events == ()
    copied(request=_request("copy"))
    assert len(provider.provider_events) == 1
    assert len(copied.provider.provider_events) == 1


class _RecordingCallback(BaseCallback):
    def __init__(self) -> None:
        self.events: list[tuple[str, Exception | None]] = []

    def on_lm_start(
        self,
        call_id: str,
        instance: Any,
        inputs: dict[str, Any],
    ) -> None:
        del call_id, instance, inputs
        self.events.append(("start", None))

    def on_lm_end(
        self,
        call_id: str,
        outputs: dict[str, Any] | None,
        exception: Exception | None = None,
    ) -> None:
        del call_id, outputs
        self.events.append(("end", exception))


def test_callbacks_wrap_success_and_pre_effect_rejection_but_are_not_receipts() -> None:
    callback = _RecordingCallback()
    provider = StubProvider()
    lm = DSPyTypedLMAdapter(provider, callbacks=[callback])

    lm(request=_request())
    with pytest.raises(LMUnsupportedFeatureError):
        lm(request=_request(metadata={"unsupported": True}))

    assert [event[0] for event in callback.events] == ["start", "end", "start", "end"]
    assert callback.events[1][1] is None
    assert isinstance(callback.events[3][1], LMUnsupportedFeatureError)
    assert len(provider.provider_events) == 1


def test_dspx_provider_request_identity_remains_distinct_from_dspy() -> None:
    assert ProviderRequest is not LMRequest


def test_latched_stub_cannot_dispatch_dump_or_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = StubProvider()
    lm = DSPyTypedLMAdapter(provider)

    def fail_response(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise ValueError("post-effect failure")

    monkeypatch.setattr(LMResponse, "from_text", fail_response)
    with pytest.raises(LMTransportError, match="response processing") as exc_info:
        lm(request=_request())
    assert exc_info.value.code == "effect_indeterminate"
    assert provider.attempt_total == 1
    assert provider.terminal_effect is EffectDisposition.EFFECT_INDETERMINATE

    with pytest.raises(LMTransportError) as second:
        lm(request=_request())
    assert second.value.code == "effect_indeterminate"
    assert provider.attempt_total == 1
    with pytest.raises(RuntimeError, match="terminal"):
        provider.dump_state()
    with pytest.raises(LMUnsupportedFeatureError, match="terminal"):
        lm.dump_state()
    with pytest.raises(LMUnsupportedFeatureError, match="terminal"):
        lm.copy()


def test_copied_adapter_and_provider_share_isolated_lock_during_postprocessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_provider = StubProvider()
    original = DSPyTypedLMAdapter(original_provider)
    copied = original.copy()
    assert copied.provider is not original_provider
    assert copied._operation_lock is copied.provider.operation_lock
    assert copied._operation_lock is not original._operation_lock

    postprocessing = Event()
    release = Event()
    direct_started = Event()
    direct_finished = Event()
    outcomes: list[str] = []

    def fail_response(*args: object, **kwargs: object) -> object:
        del args, kwargs
        postprocessing.set()
        assert release.wait(5)
        raise ValueError("postprocessing failure")

    monkeypatch.setattr(LMResponse, "from_text", fail_response)

    def adapter_call() -> None:
        try:
            copied(request=_request("copied"))
        except LMTransportError as exc:
            outcomes.append(f"adapter:{exc.code}")

    def direct_call() -> None:
        direct_started.set()
        try:
            copied.provider.invoke(
                ProviderRequest(
                    model="stub/echo",
                    messages=(ProviderMessage(role="user", text="direct"),),
                )
            )
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

    assert not first.is_alive() and not second.is_alive()
    assert sorted(outcomes) == [
        "adapter:effect_indeterminate",
        "direct:effect_indeterminate",
    ]
    assert original_provider.provider_events == ()
    assert original_provider.attempt_total == 0
    assert copied.provider.attempt_total == 1
    assert copied.provider.terminal_effect is EffectDisposition.EFFECT_INDETERMINATE
    assert copied.provider.provider_events == (copied.provider.provider_events[0],)
    event = copied.provider.provider_events[0]
    assert event.requested_model == "stub/echo"
    assert event.observed_model == "stub/echo"
    assert event.dispatch_count == 1
    assert event.disposition is EffectDisposition.EFFECT_INDETERMINATE
