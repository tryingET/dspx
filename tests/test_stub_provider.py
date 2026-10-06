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
