# summary: "Proves the exact DSPy 3.3 typed adapter, offline provider port, and pre-effect rejection contract."
# read_when:
#   - "Changing typed LM translation, provider effects, state/copy/history, or DSPy callbacks."

from __future__ import annotations

import asyncio
import base64
import builtins
from collections.abc import Iterator, Mapping
import inspect
import io
import json
import os
from pathlib import Path
from threading import Event, Thread
import time
from typing import TYPE_CHECKING, Any
import uuid

import dspy
import httpx
import pytest

from dspx.image_admission import (
    CEILINGS,
    ImageContractError,
    SyntheticImageAuthority,
    canonical,
    digest,
    parse_json,
    sha,
    validate_admission,
)
from dspx.image_custody import ImageCustodySession, parent_initializer
from dspx.image_privacy import image_privacy, runtime_identity
from dspx.image_records import list_root, publish, read_record
from dspx.image_supervision import supervise_image_worker
from dspx.image_worker import worker_entry
from dspx.provider_contract import (
    EffectDisposition,
    ProviderImagePart,
    ProviderInvocationError,
    ProviderMessage,
    ProviderPartsMessage,
    ProviderRequest,
    ProviderResult,
    ProviderTextPart,
)
from dspx.provider_registry import create_image_lm
from dspx.stub_provider import StubProvider
from test_image_privacy import _context, _generated, _load_generated, _png, _status

_TYPED_LM_AVAILABLE = hasattr(dspy, "LMRequest")
pytestmark = pytest.mark.skipif(
    not _TYPED_LM_AVAILABLE,
    reason="DSPy 3.3 typed-LM contract is proved in the retained exact target",
)

if TYPE_CHECKING or _TYPED_LM_AVAILABLE:
    from dspy import (
        BaseLM,
        LMRequest,
        LMResponse,
        LMTransportError,
        LMUnsupportedFeatureError,
    )
    from dspy.core.types import (
        LMAudioPart,
        LMCacheConfig,
        LMConfig,
        LMDocumentPart,
        LMImagePart,
        LMMessage,
        LMTextPart,
        LMToolCallPart,
        LMToolSpec,
    )
    from dspy.utils.callback import BaseCallback

    from dspx.dspy_typed_lm import DSPyTypedLMAdapter
else:

    class _Unavailable:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

    BaseLM = BaseCallback = LMConfig = LMMessage = LMTextPart = _Unavailable
    LMAudioPart = LMCacheConfig = LMDocumentPart = LMImagePart = _Unavailable
    LMToolCallPart = LMToolSpec = _Unavailable
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
    copied_provider = copied.provider

    assert copied is not lm
    assert copied.cache is False
    assert copied_provider is not provider
    assert isinstance(copied_provider, StubProvider)
    assert copied.history == []
    assert copied.callbacks is not lm.callbacks
    assert copied.kwargs is not lm.kwargs
    assert copied_provider.provider_events == ()
    copied(request=_request("copy"))
    assert len(provider.provider_events) == 1
    assert len(copied_provider.provider_events) == 1


class _RecordingCallback(BaseCallback):
    def __init__(self) -> None:
        self.events: list[tuple[str, BaseException | None]] = []

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
        exception: BaseException | None = None,
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
    copied_provider = copied.provider
    assert copied_provider is not original_provider
    assert isinstance(copied_provider, StubProvider)
    assert copied._operation_lock is copied_provider.operation_lock
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
            copied_provider.invoke(
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
    assert copied_provider.attempt_total == 1
    assert copied_provider.terminal_effect is EffectDisposition.EFFECT_INDETERMINATE
    assert copied_provider.provider_events == (copied_provider.provider_events[0],)
    event = copied_provider.provider_events[0]
    assert event.requested_model == "stub/echo"
    assert event.observed_model == "stub/echo"
    assert event.dispatch_count == 1
    assert event.disposition is EffectDisposition.EFFECT_INDETERMINATE


# --- AK6607-S06/S33: image-mode affordances at the sole typed adapter ---------------
# Every variant runs on the real image path inside one guarded clean worker: a real
# ImageCustodySession and create_image_lm over a MockTransport send counter. Only safe
# published facts cross back; the parent asserts them per Revision2 case.

_HERE = "test_dspy_typed_lm"
_MODEL = "synthetic-vision-fixture"
_FIXTURE = "affordance-fixture.png"
_IDLE_ROOT = ["lock", "ready.json"]
_S33_DATA = base64.b64encode(b"synthetic-s33-invalid").decode("ascii") + "!"
_REFUSED = "image_admission_invalid"
_S06_CASES = {
    "E01-remote_https_url": [f"typed:{_REFUSED}"],
    "E02-loopback_image_url": [f"typed:{_REFUSED}"],
    "E03-file_url": [f"typed:{_REFUSED}"],
    "E04-file_id": [f"typed:{_REFUSED}"],
    "E05-typed_local_path": [f"typed:{_REFUSED}"],
    "E06-image_metadata": [f"typed:{_REFUSED}"],
    "E07-assistant_image": [f"typed:{_REFUSED}", f"provider:{_REFUSED}"],
    "E08-system_image": [f"typed:{_REFUSED}", f"provider:{_REFUSED}"],
    "E09-detail_high": [f"typed:{_REFUSED}"],
    "E10-detail_auto": [f"typed:{_REFUSED}"],
    "E11-audio_part": [f"typed:{_REFUSED}"],
    "E12-document_part": [f"typed:{_REFUSED}"],
    "E13-tool_call": [f"tools:{_REFUSED}", f"tool_call_part:{_REFUSED}"],
    "E14-async_invocation": ["acall:unsupported:async", "aforward:unsupported:async"],
    "E15-generation_override": [
        f"request_config:{_REFUSED}",
        f"call_kwargs:{_REFUSED}",
        f"cache_override:{_REFUSED}",
    ],
}


def _drive(coroutine: Any) -> Any:
    """Step an async call without an event loop, thread or signal handler."""
    try:
        coroutine.send(None)
    except StopIteration as stop:
        return stop.value
    coroutine.close()
    raise AssertionError("async invocation suspended")


def _affordance_variants(lm: Any, session: Any, baseline: Any, fixture: str):
    """(case, route, call): the admitted baseline with exactly one affordance added."""
    system, user = baseline.messages
    index = next(i for i, part in enumerate(user.parts) if type(part) is LMImagePart)
    image = user.parts[index]
    rest = [part for i, part in enumerate(user.parts) if i != index]

    def typed(*messages: Any, **update: Any) -> Any:
        return baseline.model_copy(update={"messages": list(messages), **update})

    def plus(*messages: Any, **update: Any) -> Any:
        return lambda: lm(request=typed(system, user, *messages, **update))

    def swap(make: Any) -> Any:
        def call() -> Any:
            parts = list(user.parts)
            parts[index] = make()
            return lm(request=typed(system, user.model_copy(update={"parts": parts})))

        return call

    def source(**kwargs: Any) -> Any:
        return swap(lambda: LMImagePart(media_type="image/png", **kwargs))

    def moved(role: str) -> Any:
        def call() -> Any:
            bare = user.model_copy(update={"parts": rest})
            if role == "system":
                host = system.model_copy(update={"parts": [*system.parts, image]})
                return lm(request=typed(host, bare))
            visual = LMMessage(role=role, parts=[image])
            return lm(request=typed(system, bare, visual))

        return call

    def direct(role: str) -> Any:
        def call() -> Any:
            item = session.context.occurrences[0]
            pixels = (item.media_type, item.data, sha(item.data), len(item.data))
            part = ProviderImagePart(
                *pixels, item.width, item.height, item.occurrence_id
            )
            message = ProviderPartsMessage(role, (ProviderTextPart("A"), part))
            return lm.provider.invoke(ProviderRequest(_MODEL, (message,), session))

        return call

    audio = base64.b64encode(b"RIFF\x24\0\0\0WAVEfmt ").decode("ascii")
    document = base64.b64encode(b"%PDF-1.4 synthetic").decode("ascii")
    tool_call = LMToolCallPart(name="lookup", args={"q": "A"})
    return [
        ("E01", "typed", source(url="https://images.example.invalid/affordance.png")),
        ("E02", "typed", source(url="http://127.0.0.1:8000/v1/affordance.png")),
        ("E03", "typed", source(url=f"file://{fixture}")),
        ("E04", "typed", source(file_id="file-synthetic-affordance")),
        ("E05", "typed", source(path=fixture)),
        ("E06", "typed", swap(lambda: image.model_copy(update={"metadata": {"k": 1}}))),
        ("E07", "typed", moved("assistant")),
        ("E07", "provider", direct("assistant")),
        ("E08", "typed", moved("system")),
        ("E08", "provider", direct("system")),
        ("E09", "typed", swap(lambda: image.model_copy(update={"detail": "high"}))),
        ("E10", "typed", swap(lambda: image.model_copy(update={"detail": "auto"}))),
        ("E11", "typed", swap(lambda: LMAudioPart(data=audio, media_type="audio/wav"))),
        ("E12", "typed", swap(lambda: LMDocumentPart(data=document))),
        ("E13", "tools", plus(tools=[LMToolSpec(name="lookup")])),
        ("E13", "tool_call_part", plus(LMMessage(role="assistant", parts=[tool_call]))),
        ("E14", "acall", lambda: _drive(lm.acall(request=baseline))),
        ("E14", "aforward", lambda: _drive(lm.aforward(baseline))),
        ("E15", "request_config", plus(config=LMConfig(temperature=0.7))),
        ("E15", "call_kwargs", lambda: lm(request=baseline, temperature=0.7)),
        (
            "E15",
            "cache_override",
            plus(config=LMConfig(cache=LMCacheConfig(enabled=True))),
        ),
        ("S33", "parse", source(data=_S33_DATA)),
    ]


def _observe_affordances(
    lm: Any, session: Any, baseline: Any, root_fd: int, sends: list[bytes], fixture: str
) -> dict[str, Any]:
    invoked: list[Any] = []
    opened: list[str] = []
    provider_type = type(lm.provider)
    real_invoke, real_os_open = provider_type.invoke, os.open
    passthrough = {"open": io.open}

    def invoke_spy(provider: Any, request: Any) -> Any:
        invoked.append(request)
        return real_invoke(provider, request)

    def os_open_spy(path: Any, *args: Any, **kwargs: Any) -> Any:
        if _FIXTURE in os.fsdecode(path):
            opened.append("os.open")
        return real_os_open(path, *args, **kwargs)

    def io_open_spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(file, int) and _FIXTURE in os.fsdecode(file):
            opened.append("io.open")
        return passthrough["open"](file, *args, **kwargs)  # caller closes it

    def counts() -> list[int]:
        return [len(sends), len(invoked), lm.provider.attempt_total, len(opened)]

    rows = []
    with pytest.MonkeyPatch.context() as spies:
        spies.setattr(provider_type, "invoke", invoke_spy)
        spies.setattr(os, "open", os_open_spy)
        spies.setattr(io, "open", io_open_spy)
        spies.setattr(builtins, "open", io_open_spy)
        for case, route, call in _affordance_variants(lm, session, baseline, fixture):
            before = counts()
            error: BaseException | None = None
            try:
                call()
                outcome = "accepted"
            except ImageContractError as caught:
                error, outcome = caught, caught.code
            except LMUnsupportedFeatureError as caught:
                error, outcome = caught, "unsupported:" + ",".join(caught.features)
            except Exception as caught:
                error, outcome = caught, "other:" + type(caught).__name__
            rendered = "" if error is None else repr(error) + str(error)
            chain: list[str] = []
            linked = None if error is None else error.__cause__ or error.__context__
            while linked is not None and len(chain) < 8:
                chain.append(f"{type(linked).__name__}:{getattr(linked, 'code', '')}")
                linked = linked.__cause__ or linked.__context__
            latched = lm._indeterminate_latched or lm.provider._indeterminate_latched
            rows.append(
                {
                    "case": case,
                    "route": route,
                    "outcome": outcome,
                    "deltas": [a - b for a, b in zip(counts(), before, strict=True)],
                    "custody": sorted(list_root(root_fd)),
                    "spent": session.poisoned or latched,
                    "chain": chain,
                    "rendered_payload": _S33_DATA[:-1] in rendered,
                }
            )
        try:  # recorded, not raised: a regressed row is then pinpointed per case
            text = lm(request=baseline).text
        except Exception as error:
            text = getattr(error, "code", type(error).__name__)
        nominal: list[Any] = []
        for request in invoked[-1:]:
            nominal += [request, *request.messages]
            nominal += [part for message in request.messages for part in message.parts]
        control = {
            "text": text,
            "counts": counts(),
            "custody": sorted(list_root(root_fd)),
            "reprs": sorted({repr(value) for value in nominal}),
        }
    return {"rows": rows, "control": control}


@worker_entry
def _affordance_entry(params: dict[str, Any]) -> dict[str, object]:
    prepared = parse_json(params["prepared"].encode("ascii"))
    raw = params["admission"].encode("ascii")
    custody = parse_json(raw)["custody"]
    authority = SyntheticImageAuthority(
        raw, "3" * 64, custody["root_dev"], custody["root_ino"], _used=[False]
    )
    admission = validate_admission(
        raw,
        source=prepared["source"],
        authority=authority,
        runtime_identity_sha256=runtime_identity(),
    )
    with image_privacy() as active:
        profile, program = _load_generated(Path(params["source"]))
        active.bind_graph(program, profile=profile)
        ctx = _context(active, profile, params["input_fd"])
        session = ImageCustodySession(
            root_fd=params["root_fd"],
            admission=admission,
            authority=authority,
            context=ctx,
        )
        active.session = session
        sends: list[bytes] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sends.append(request.content)
            choice = {"message": {"role": "assistant", "content": "fixture result"}}
            body = {"model": _MODEL, "choices": [choice]}
            return httpx.Response(200, json=body, request=request)

        lm = create_image_lm(session, transport=httpx.MockTransport(handler))
        messages = active.formatter.format(
            program.predict.signature, [], ctx.materialized()
        )
        baseline = LMRequest(model=_MODEL, messages=messages)
        observed = _observe_affordances(
            lm, session, baseline, params["root_fd"], sends, params["fixture"]
        )
    commitment = publish(params["observation_fd"], "observations.json", observed)
    return _status("completed", commitment)


def _run_affordance_worker(tmp: Path) -> dict[str, Any]:
    source = tmp / "candidate"
    _generated(source)
    pixels = _png(b"\x10\x20\x30")
    names = ("inputs", "prep", "custody", "observations", "loose")
    for name in names:
        (tmp / name).mkdir(mode=0o700)
    image = {"type": "image_base64", "media_type": "image/png"}
    image["data"] = base64.b64encode(pixels).decode("ascii")
    visual = json.dumps({"visual": ["A", image, "B"]})
    (tmp / "inputs" / "inputs.json").write_text(visual)
    (tmp / "loose" / _FIXTURE).write_bytes(pixels)
    flags = os.O_RDONLY | os.O_DIRECTORY
    fds = {name: os.open(tmp / name, flags) for name in names[:4]}
    try:
        status = supervise_image_worker(
            "test_image_privacy:_privacy_prepare_entry",
            {
                "source": str(source),
                "input_fd": fds["inputs"],
                "prep_fd": fds["prep"],
                "model": _MODEL,
            },
            fds=(fds["inputs"], fds["prep"]),
            wall_ms=30_000,
        )
        prepared_raw = read_record(fds["prep"], "preparation.json")
        assert status["commitment_sha256"] == sha(prepared_raw)
        prepared = parse_json(prepared_raw)
        root = os.fstat(fds["custody"])
        now = time.time_ns() // 1_000_000
        record = {
            "schema_version": "dspx-image-admission-v2",
            "mode": "synthetic",
            "provider_kind": "openai-compatible",
            "model": _MODEL,
            "canonical_base_endpoint": "http://127.0.0.1:8000/v1",
            "source_package_sha256": digest("source-v1", prepared["source"]),
            "candidate_manifest_sha256": sha((source / "manifest.json").read_bytes()),
            "runtime_identity_sha256": runtime_identity(),
            "decoder_profile_sha256": prepared["source"]["decoder_profile_sha256"],
            "request_plan": prepared["plan"],
            "limits": {**CEILINGS, "total_dispatch_allowance": 1},
            "deadlines": {
                "not_before_utc_ms": now - 1000,
                "expires_utc_ms": now + 60_000,
                "total_wall_ms": 30_000,
                "per_request_io_timeout_ms": 30_000,
            },
            "custody": {
                "custody_id": str(uuid.uuid4()),
                "caller_run_id": str(uuid.uuid4()),
                "caller_binding_sha256": "2" * 64,
                "root_dev": root.st_dev,
                "root_ino": root.st_ino,
                "caller_expectation_sha256": "3" * 64,
            },
            "approval_binding": dict.fromkeys(
                (
                    "owning_ak_task",
                    "operator_evidence_ref",
                    "parent_confirmation_sha256",
                )
            ),
        }
        raw = canonical(record)
        authority = SyntheticImageAuthority(raw, "3" * 64, root.st_dev, root.st_ino)
        admission = validate_admission(
            raw,
            source=prepared["source"],
            authority=authority,
            runtime_identity_sha256=runtime_identity(),
        )
        manifest = {
            "schema_version": "dspx-image-input-manifest-v2",
            "source_package_sha256": record["source_package_sha256"],
            "admission_sha256": admission.sha256,
            "marker_entries": prepared["markers"],
        }
        initialize = parent_initializer(
            fds["custody"],
            authority,
            admission,
            source_sha256=record["source_package_sha256"],
            manifest_sha256=digest("manifest-v2", manifest),
        )
        params = {
            "source": str(source),
            "input_fd": fds["inputs"],
            "root_fd": fds["custody"],
            "observation_fd": fds["observations"],
            "admission": raw.decode("ascii"),
            "prepared": prepared_raw.decode("ascii"),
            "fixture": str(tmp / "loose" / _FIXTURE),
        }
        status = supervise_image_worker(
            f"{_HERE}:_affordance_entry",
            params,
            fds=(fds["inputs"], fds["custody"], fds["observations"]),
            wall_ms=30_000,
            parent_action=initialize,
        )
        observed_raw = read_record(fds["observations"], "observations.json")
        assert status == _status("completed", sha(observed_raw))
        observed = parse_json(observed_raw)
        observed["custody"] = sorted(list_root(fds["custody"]))
        for kind in ("intent", "terminal"):
            if f"{kind}-1.json" in observed["custody"]:
                record = read_record(fds["custody"], f"{kind}-1.json")
                observed[kind] = parse_json(record)
        return observed
    finally:
        for fd in fds.values():
            os.close(fd)


@pytest.fixture(scope="module")
def image_affordances(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """One supervised clean-worker run: every affordance, then the baseline once."""
    tmp = tmp_path_factory.mktemp("typed-affordances")
    with pytest.MonkeyPatch.context() as env:
        env.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
        env.setenv("MLFLOW_ENABLE", "0")
        return _run_affordance_worker(tmp)


def _assert_first_slot_only(observed: dict[str, Any]) -> None:
    """The unchanged baseline, sent after every refusal, consumed slot 1 once."""
    direct = sum(row["route"] == "provider" for row in observed["rows"])
    control = observed["control"]
    assert control["text"] == "fixture result"
    # [HTTP sends, provider invokes, provider attempts, fixture opens]
    assert control["counts"] == [1, direct + 1, 1, 0]
    slot = ["intent-1.json", "lock", "ready.json", "terminal-1.json"]
    assert control["custody"] == observed["custody"] == slot
    terminal = observed["terminal"]
    assert observed["intent"]["attempt_ordinal"] == terminal["attempt_ordinal"] == 1
    assert terminal["dispatch_count"] == 1
    assert terminal["provider_disposition"] == "completed_success"
    assert terminal["finalization_kind"] == "dspy_lm"
    assert terminal["typed_finalization_completed"] is True


@pytest.mark.parametrize("case", list(_S06_CASES))
def test_image_mode_unsupported_affordance_rejects_before_transport(
    image_affordances: dict[str, Any], case: str
) -> None:
    """AK6607-S06: provider invoke and HTTP send stay zero; no slot is consumed."""
    rows = [row for row in image_affordances["rows"] if row["case"] == case[:3]]
    assert [f"{row['route']}:{row['outcome']}" for row in rows] == _S06_CASES[case]
    for row in rows:
        direct = row["route"] == "provider"
        # A direct port call is itself the invoke; it still records no attempt.
        assert row["deltas"] == [0, int(direct), 0, 0]
        assert row["custody"] == _IDLE_ROOT and row["spent"] is False
        # Fixed codes only, chain-free on both routes: the port's custody transaction
        # re-raises its pre-reserve refusal's own code with no cause or context.
        assert row["chain"] == []
    _assert_first_slot_only(image_affordances)


def test_image_mode_nominal_repr_and_parse_failure_are_payload_free(
    image_affordances: dict[str, Any],
) -> None:
    """AK6607-S33: real image-path DTO repr and a fixed, chain-free parse refusal."""
    (row,) = [row for row in image_affordances["rows"] if row["case"] == "S33"]
    assert row["outcome"] == "image_input_invalid" and row["chain"] == []
    assert row["rendered_payload"] is False and row["deltas"] == [0, 0, 0, 0]
    assert row["custody"] == _IDLE_ROOT and row["spent"] is False
    # Every nominal DTO of the admitted request (pixels included) renders bare.
    names = ("ImagePart", "PartsMessage", "Request", "TextPart")
    assert image_affordances["control"]["reprs"] == [f"Provider{n}()" for n in names]
    _assert_first_slot_only(image_affordances)
