# summary: "Tests the explicit stub-only typed provider registry and replay fixture boundary."
# read_when:
#   - "Changing supported providers, environment selection, or explicit replay fixtures."

from __future__ import annotations

from typing import Any, cast

import pytest

from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.provider_registry import (
    ProviderSelectionRequiredError,
    UnknownProviderError,
    UnsupportedProviderError,
    create,
    create_from_env,
    supported_provider_names,
)
from dspx.stub_provider import StubProvider


def test_support_matrix_includes_stub_and_loopback_http() -> None:
    assert supported_provider_names() == ("stub", "openai-compatible")
    lm = create("stub")
    assert type(lm) is DSPyTypedLMAdapter
    assert type(lm.provider) is StubProvider


def test_registry_rejects_stub_model_identity_drift() -> None:
    with pytest.raises(ValueError, match="stub/echo"):
        create("stub", model="stub/custom")


def test_environment_selection_is_explicit(monkeypatch) -> None:
    monkeypatch.delenv("DSPX_PROVIDER", raising=False)
    with pytest.raises(ProviderSelectionRequiredError):
        create_from_env()
    assert type(create_from_env(allow_stub_default=True)) is DSPyTypedLMAdapter


def test_removed_and_unknown_provider_names_are_distinct(monkeypatch) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "pi-rpc")
    with pytest.raises(UnsupportedProviderError):
        create_from_env()
    with pytest.raises(UnknownProviderError):
        create("invented-provider")


def test_explicit_replay_fixture_is_validated_and_bound_to_stub(monkeypatch) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_REPLAY_FIXTURE_JSON", '{"urgency":"high"}')
    lm = create_from_env()
    assert lm(prompt="ignored") == ['{"urgency": "high"}']
    with pytest.raises(ValueError, match="not serializable"):
        lm.dump_state()


def test_invalid_replay_fixture_fails_before_provider_invocation(monkeypatch) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_REPLAY_FIXTURE_JSON", "api_key=secret")
    with pytest.raises(ValueError, match="valid JSON"):
        create_from_env()


def test_stub_preflight_rejection_records_zero_dispatch_attempt() -> None:
    provider = StubProvider()
    from dspx.provider_contract import (
        ProviderInvocationError,
        ProviderMessage,
        ProviderRequest,
    )

    request = ProviderRequest(
        model="stub/other",
        messages=(ProviderMessage(role="user", text="not retained"),),
    )
    with pytest.raises(ProviderInvocationError):
        provider.invoke(request)
    assert provider.provider_events[-1].requested_model == "stub/other"
    assert provider.provider_events[-1].observed_model is None
    assert provider.provider_events[-1].dispatch_count == 0
    assert provider.provider_events[-1].disposition.value == "preflight_rejected"


@pytest.mark.parametrize("fixture", [None, "fixture-success-must-not-bypass"])
def test_direct_stub_rejects_malformed_image_union_before_fixture(fixture) -> None:
    from dspx.provider_contract import ProviderInvocationError, ProviderRequest

    provider = StubProvider(explicit_response_text=fixture)
    # Runtime DTO annotation is not a validator: exercise actual direct preflight.
    request = ProviderRequest(
        model=provider.model, messages=cast(Any, ({"type": "image_url"},))
    )
    with pytest.raises(ProviderInvocationError) as failure:
        provider.invoke(request)
    assert failure.value.disposition.value == "preflight_rejected"
    assert len(provider.provider_events) == 1
    assert provider.provider_events[0].dispatch_count == 0


def test_provider_text_dtos_do_not_format_payload_repr() -> None:
    from dspx.provider_contract import (
        EffectDisposition,
        ProviderMessage,
        ProviderRequest,
        ProviderResult,
    )

    # ubs:ignore -- synthetic redaction canary, not a credential
    secret = "synthetic-private-text-value"
    message = ProviderMessage(role="user", text=secret)
    request = ProviderRequest(model="stub/echo", messages=(message,))
    result = ProviderResult(
        text=secret,
        model="stub/echo",
        effect_disposition=EffectDisposition.COMPLETED_SUCCESS,
        provider_data={"unsafe": secret},
    )
    exposed = any(secret in repr(value) for value in (message, request, result))
    assert not exposed, "nominal DTO repr exposed payload"


@pytest.mark.parametrize("fixture", [None, "fixture-success-must-not-bypass"])
@pytest.mark.parametrize("image", [False, True])
def test_stub_denies_nominal_parts_even_in_direct_fixture_mode(fixture, image) -> None:
    from dspx.provider_contract import (
        ProviderImagePart,
        ProviderInvocationError,
        ProviderPartsMessage,
        ProviderRequest,
        ProviderTextPart,
    )
    from dspx.image_admission import sha

    provider = StubProvider(explicit_response_text=fixture)
    raw = b"synthetic-unadmitted-image-fixture"
    part = (
        ProviderImagePart("image/png", raw, sha(raw), len(raw), 1, 1, "s000001")
        if image
        else ProviderTextPart("synthetic-text")
    )
    message = ProviderPartsMessage("user", (part,))
    request = ProviderRequest(provider.model, (message,))
    with pytest.raises(ProviderInvocationError) as failure:
        provider.invoke(request)
    assert str(failure.value) == "DSPx stub provider invocation failed"
    assert failure.value.disposition.value == "preflight_rejected"
    assert len(provider.provider_events) == 1
    assert provider.provider_events[0].dispatch_count == 0


def test_stub_denies_image_binding_before_fixture() -> None:
    from dspx.provider_contract import (
        ProviderInvocationError,
        ProviderMessage,
        ProviderRequest,
    )

    provider = StubProvider(explicit_response_text="not-an-image-canary")
    request = ProviderRequest(
        provider.model, (ProviderMessage("user", "ordinary"),), object()
    )
    with pytest.raises(ProviderInvocationError) as failure:
        provider.invoke(request)
    assert failure.value.disposition.value == "preflight_rejected"
    assert provider.provider_events[0].dispatch_count == 0


def _exception_chain(error: BaseException | None) -> list[BaseException]:
    chain: list[BaseException] = []
    while error is not None and len(chain) < 16:
        chain.append(error)
        error = error.__cause__ or error.__context__
    return chain


@pytest.mark.parametrize("fixture", [None, "fixture-success-must-not-bypass"])
@pytest.mark.parametrize(
    "route", ["typed_request", "path_part", "legacy_messages", "generated_predict"]
)
def test_native_typed_image_to_stub_is_not_a_text_canary(fixture, route) -> None:
    """AK6607-S04: ordered text,image,text never reaches StubProvider.invoke."""
    import base64

    import dspy
    from dspy import LMUnsupportedFeatureError
    from dspy.core.types import LMImagePart, LMMessage, LMRequest, LMTextPart

    provider = StubProvider(explicit_response_text=fixture)
    invoked: list[object] = []
    real_invoke = provider.invoke

    def invoke_spy(request):
        invoked.append(request)
        return real_invoke(request)

    vars(provider)["invoke"] = invoke_spy
    lm = DSPyTypedLMAdapter(provider)
    data = base64.b64encode(b"synthetic-s04-pixels").decode("ascii")
    filename = "synthetic-s04-screenshot.png"
    image = (
        LMImagePart(path=filename)
        if route == "path_part"
        else LMImagePart(data=data, media_type="image/png")
    )
    ordered = [LMTextPart(text="before"), image, LMTextPart(text="after")]

    class Shot(dspy.Signature):
        """Describe the synthetic screenshot."""

        shot: dspy.Image = dspy.InputField()
        answer: str = dspy.OutputField()

    with pytest.raises(LMUnsupportedFeatureError) as failure:
        if route in {"typed_request", "path_part"}:
            message = LMMessage(role="user", parts=ordered)
            lm(request=LMRequest(model=provider.model, messages=[message]))
        elif route == "legacy_messages":
            content = [
                {"type": "text", "text": "before"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{data}"},
                },
                {"type": "text", "text": "after"},
            ]
            lm(messages=[{"role": "user", "content": content}])
        else:
            with dspy.context(lm=lm):
                dspy.Predict(Shot)(shot=dspy.Image(f"data:image/png;base64,{data}"))
    # Rejected at the typed adapter: no filename, marker or description reached the
    # stub in place of the pixels, and no stub attempt (even preflight) was recorded.
    assert failure.value.features == ["message_part:image"]
    assert invoked == [] and provider.provider_events == ()
    assert provider.attempt_total == 0 and lm.history == []
    for error in _exception_chain(failure.value):
        rendered = repr(error) + str(error)
        assert data not in rendered and filename not in rendered
    if route != "generated_predict":
        assert failure.value.__cause__ is None and failure.value.__context__ is None


def test_nominal_dtos_and_fixed_errors_never_format_payloads(monkeypatch) -> None:
    """AK6607-S33: request/result/message/part repr and upstream-error chains."""
    import base64
    import re
    from collections.abc import Iterator, Mapping

    import pydantic
    from dspy import LMResponse, LMTransportError
    from dspy.core.types import LMMessage, LMRequest, LMTextPart

    from dspx.image_admission import sha
    from dspx.provider_contract import (
        EffectDisposition,
        ProviderAttemptEvent,
        ProviderImagePart,
        ProviderInvocationError,
        ProviderMessage,
        ProviderPartsMessage,
        ProviderRequest,
        ProviderResult,
        ProviderTextPart,
    )

    # ubs:ignore -- synthetic redaction canary, not a credential
    text = "synthetic-s33-private-text"
    pixels = b"synthetic-s33-private-image-bytes"
    encoded = base64.b64encode(pixels).decode("ascii")
    echo = f"echo {text} {encoded}"
    forbidden = (text, encoded, pixels.hex(), repr(pixels), "synthetic-s33")
    formatted: list[str] = []

    class SpyMapping(Mapping[str, Any]):
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = data

        def __getitem__(self, key: str) -> Any:
            return self._data[key]

        def __iter__(self) -> Iterator[str]:
            return iter(self._data)

        def __len__(self) -> int:
            return len(self._data)

        def __repr__(self) -> str:
            formatted.append("mapping")
            return echo

    class SpyBinding:
        def __repr__(self) -> str:
            formatted.append("binding")
            return echo

    text_part = ProviderTextPart(text)
    image_part = ProviderImagePart(
        "image/png", pixels, sha(pixels), len(pixels), 1, 1, "s000001"
    )
    parts = ProviderPartsMessage("user", (text_part, image_part, text_part))
    message = ProviderMessage("assistant", echo)
    values: tuple[object, ...] = (
        text_part,
        image_part,
        parts,
        message,
        ProviderRequest("stub/echo", (parts, message), SpyBinding()),
        ProviderResult(
            echo,
            "stub/echo",
            EffectDisposition.COMPLETED_SUCCESS,
            usage=SpyMapping({"total_tokens": len(echo)}),
            provider_data=SpyMapping({"echo": echo}),
        ),
        ProviderAttemptEvent(
            "stub", "stub/echo", "stub/echo", 1, EffectDisposition.COMPLETED_SUCCESS
        ),
        ProviderInvocationError(
            "DSPx stub provider invocation failed",
            disposition=EffectDisposition.PREFLIGHT_REJECTED,
            provider="stub",
        ),
    )
    allowlisted = {
        "provider_kind",
        "requested_model",
        "observed_model",
        "dispatch_count",
        "disposition",
    }
    for value in values:
        for rendered in (repr(value), str(value), f"{value!r}", f"{value}"):
            assert not any(item in rendered for item in forbidden)
            assert set(re.findall(r"(\w+)=", rendered)) <= allowlisted
    assert formatted == [], "usage/provider_data/binding were formatted"

    # An upstream Pydantic failure carrying the echo stays behind a fixed error.
    upstream: list[BaseException] = []

    def upstream_validation(*args: object, **kwargs: object) -> object:
        del args, kwargs
        try:
            LMResponse.model_validate(
                {"outputs": [{"parts": [{"type": "text", "text": text, "x": text}]}]}
            )
        except pydantic.ValidationError as error:
            upstream.append(error)
            raise
        raise AssertionError("upstream model accepted an invalid payload")

    monkeypatch.setattr(LMResponse, "from_text", upstream_validation)
    lm = DSPyTypedLMAdapter(StubProvider(explicit_response_text=echo))
    request = LMRequest(
        model="stub/echo",
        messages=[LMMessage(role="user", parts=[LMTextPart(text=text)])],
    )
    with pytest.raises(LMTransportError) as failure:
        lm(request=request)
    assert len(upstream) == 1 and text in str(upstream[0])
    assert failure.value.code == "effect_indeterminate"
    assert failure.value.__cause__ is None and failure.value.__context__ is None
    rendered = repr(failure.value) + str(failure.value)
    assert not any(item in rendered for item in forbidden)
