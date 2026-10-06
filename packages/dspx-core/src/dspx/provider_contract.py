# summary: "Defines DSPx-owned provider invocation, result, and effect contracts independent of DSPy."
# read_when:
#   - "Adding a provider, changing provider effects, or adapting providers to DSPy."

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Mapping, Protocol, runtime_checkable, cast


class EffectDisposition(StrEnum):
    """What is known about provider effects after an invocation attempt."""

    NOT_STARTED = "not_started"
    PREFLIGHT_REJECTED = "preflight_rejected"
    COMPLETED_SUCCESS = "completed_success"
    COMPLETED_FAILURE = "completed_failure"
    EFFECT_INDETERMINATE = "effect_indeterminate"
    CANCELLED_BEFORE_START = "cancelled_before_start"
    CANCELLED_AFTER_START = "cancelled_after_start"


@dataclass(frozen=True, slots=True)
class ProviderAttemptEvent:
    """Bounded secret-free terminal evidence for one provider invocation attempt."""

    provider_kind: str
    requested_model: str
    observed_model: str | None
    dispatch_count: int
    disposition: EffectDisposition


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    """One text-only message accepted by the first typed-provider slice."""

    role: str = field(repr=False)
    text: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProviderTextPart:
    text: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProviderImagePart:
    media_type: str = field(repr=False)
    data: bytes = field(repr=False)
    sha256: str = field(repr=False)
    byte_count: int = field(repr=False)
    width: int = field(repr=False)
    height: int = field(repr=False)
    occurrence_id: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProviderPartsMessage:
    role: str = field(repr=False)
    parts: tuple[ProviderTextPart | ProviderImagePart, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """DSPx-owned provider request, intentionally distinct from DSPy LMRequest."""

    model: str = field(repr=False)
    messages: tuple[ProviderMessage | ProviderPartsMessage, ...] = field(repr=False)
    image_binding: object | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """Completed provider result plus explicit effect disposition."""

    text: str = field(repr=False)
    model: str = field(repr=False)
    effect_disposition: EffectDisposition = field(repr=False)
    usage: Mapping[str, int] = field(default_factory=dict, repr=False)
    provider_data: Mapping[str, Any] = field(default_factory=dict, repr=False)


class ProviderInvocationError(RuntimeError):
    """Safe provider failure carrying the only authoritative effect disposition."""

    def __init__(
        self,
        message: str,
        *,
        disposition: EffectDisposition,
        provider: str,
    ) -> None:
        super().__init__(message)
        self.disposition = disposition
        self.provider = provider


def requested_model_for_event(
    request: object,
    validate_model: Callable[[str], str],
) -> str:
    """Bounded event identity without DSPy/runtime imports or arbitrary repr."""
    try:
        model = getattr(request, "model", None)
    except Exception:
        return "<invalid>"
    if not isinstance(model, str):
        return "<invalid>"
    try:
        return validate_model(model) or "<invalid>"
    except (TypeError, ValueError):
        return "<invalid>"


@runtime_checkable
class Provider(Protocol):
    """Synchronous DSPx provider port; it has no DSPy lifecycle surface."""

    @property
    def model(self) -> str: ...

    def invoke(self, request: ProviderRequest) -> ProviderResult: ...

    def dump_state(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True, repr=False)
class ImageClientBinding:
    """Concrete client/transport identities; serialized flags never attest them."""

    client: object
    transport: object
    headers: tuple[tuple[bytes, bytes], ...]
    methods: tuple[tuple[object, object], ...]
    handler: object
    handler_code: object
    transport_method: object
    transport_code: object

    @classmethod
    def capture(cls, client: object, transport: object) -> ImageClientBinding:
        import httpx
        from .image_admission import require

        require(type(client) is httpx.Client, "image_privacy")
        client = cast(httpx.Client, client)
        require(isinstance(transport, httpx.BaseTransport), "image_privacy")
        transport = cast(httpx.BaseTransport, transport)
        functions = tuple(
            getattr(client, name).__func__
            for name in (
                "send",
                "_send_single_request",
                "_send_handling_auth",
                "_send_handling_redirects",
            )
        )
        handler = transport.handler if type(transport) is httpx.MockTransport else None
        binding = cls(
            client,
            transport,
            tuple(client.headers.raw),
            tuple((fn, fn.__code__) for fn in functions),
            handler,
            getattr(handler, "__code__", None),
            transport.handle_request.__func__,
            transport.handle_request.__func__.__code__,
        )
        binding.check(client)
        return binding

    def check(self, client: object) -> None:
        import httpx
        from .image_admission import require

        require(type(client) is httpx.Client and client is self.client, "image_privacy")
        client = cast(httpx.Client, client)
        require(type(client.cookies) is httpx.Cookies, "image_privacy")
        method = getattr(self.transport, "handle_request")
        require(
            getattr(method, "__func__", None) is self.transport_method
            and getattr(self.transport_method, "__code__", None) is self.transport_code,
            "image_privacy",
        )
        require(
            client._transport is self.transport
            and client._auth is None
            and client.follow_redirects is False
            and not client._mounts
            and tuple(client.headers.raw) == self.headers
            and not client.cookies,
            "image_privacy",
        )
        hooks = client.event_hooks
        require(
            type(hooks) is dict
            and set(hooks) == {"request", "response"}
            and all(type(value) is list and not value for value in hooks.values()),
            "image_privacy",
        )
        for name, (expected, code) in zip(
            (
                "send",
                "_send_single_request",
                "_send_handling_auth",
                "_send_handling_redirects",
            ),
            self.methods,
            strict=True,
        ):
            method = getattr(client, name)
            require(
                getattr(method, "__func__", None) is expected
                and getattr(expected, "__code__", None) is code,
                "image_privacy",
            )
        if type(self.transport) is httpx.MockTransport:
            require(
                self.transport.handler is self.handler
                and getattr(self.handler, "__code__", None) is self.handler_code,
                "image_privacy",
            )


def image_request_from_lm(request, session) -> ProviderRequest:
    """Exact installed typed parts -> nominal immutable ports, source/plan-bound."""
    from dspy.core.types import LMImagePart, LMMessage, LMRequest, LMTextPart
    from .image_admission import require, sha
    from .image_source_io import image_bytes

    require(
        type(request) is LMRequest
        and request.model == session.record["model"]
        and not request.tools
        and not request.metadata,
        "image_admission_invalid",
    )
    config = request.config.model_dump(exclude_none=True)
    cache = config.pop("cache", None)
    extensions = config.pop("extensions", {})
    require(extensions == {}, "image_admission_invalid")
    require(
        not config and (cache is None or cache == {"enabled": False}),
        "image_admission_invalid",
    )
    tx = session._transaction
    require(tx is not None and tx.kind == "dspy_lm", "image_custody")
    sequence = session.record["request_plan"][tx.ordinal - 1][
        "image_occurrence_sequence"
    ]
    by_id = {item.occurrence_id: item for item in session.context.occurrences}
    cursor = 0
    messages = []
    for message in request.messages:
        require(
            type(message) is LMMessage
            and message.name is None
            and not message.metadata
            and message.role in {"system", "user", "assistant"}
            and message.parts,
            "image_admission_invalid",
        )
        parts = []
        for part in message.parts:
            if type(part) is LMTextPart:
                require(
                    not part.metadata and type(part.text) is str,
                    "image_admission_invalid",
                )
                parts.append(ProviderTextPart(part.text))
            else:
                require(
                    type(part) is LMImagePart
                    and message.role == "user"
                    and not part.metadata
                    and part.detail is None
                    and part.url is None
                    and part.path is None
                    and part.file_id is None
                    and cursor < len(sequence),
                    "image_admission_invalid",
                )
                raw = image_bytes(part.data, part.media_type)
                expected = by_id[sequence[cursor]]
                require(
                    part.media_type == expected.media_type
                    and sha(raw) == sha(expected.data)
                    and raw == expected.data,
                    "image_admission_invalid",
                )
                parts.append(
                    ProviderImagePart(
                        expected.media_type,
                        raw,
                        sha(raw),
                        len(raw),
                        expected.width,
                        expected.height,
                        expected.occurrence_id,
                    )
                )
                cursor += 1
        messages.append(ProviderPartsMessage(message.role, tuple(parts)))
    require(cursor == len(sequence), "image_admission_invalid")
    return ProviderRequest(request.model, tuple(messages), session)


def image_payload(request: ProviderRequest, session):
    """One bounded ordered wire representation and admission-independent shape."""
    import base64
    from .image_admission import ImageContractError, require, digest, sha
    from .image_decoder import FrozenImageDecoder
    from .image_source_io import plain_text

    require(
        type(request) is ProviderRequest
        and request.image_binding is session
        and request.model == session.record["model"]
        and type(request.messages) is tuple,
        "image_admission_invalid",
    )
    limits = session.record["limits"]
    require(0 < len(request.messages) <= limits["max_messages"], "image_budget")
    known = {item.occurrence_id: item for item in session.context.occurrences}
    messages, shapes, sequence = [], [], []
    chars = count = image_bytes_total = 0
    decoder = FrozenImageDecoder()
    for message in request.messages:
        require(
            type(message) in {ProviderMessage, ProviderPartsMessage}
            and type(message.role) is str
            and message.role in {"system", "user", "assistant"},
            "image_admission_invalid",
        )
        if type(message) is ProviderMessage:
            parts = (ProviderTextPart(message.text),)
        elif type(message) is ProviderPartsMessage:
            parts = message.parts
        else:
            raise ImageContractError("image_admission_invalid") from None
        require(type(parts) is tuple and bool(parts), "image_admission_invalid")
        blocks, part_shapes = [], []
        for part in parts:
            count += 1
            require(count <= limits["max_parts"], "image_budget")
            if type(part) is ProviderTextPart:
                text = plain_text(part.text)
                chars += len(text)
                require(chars <= limits["max_text_chars"], "image_budget")
                blocks.append({"type": "text", "text": text})
                part_shapes.append(
                    {"kind": "text", "text_sha256": sha(text.encode("utf-8"))}
                )
            elif type(part) is ProviderImagePart:
                require(
                    message.role == "user"
                    and part.occurrence_id in known
                    and type(part.data) is bytes,
                    "image_admission_invalid",
                )
                expected = known[part.occurrence_id]
                require(
                    part.data == expected.data
                    and part.sha256 == sha(part.data)
                    and part.media_type == expected.media_type
                    and part.byte_count == len(part.data)
                    and (part.width, part.height)
                    == decoder.decode(part.data, part.media_type),
                    "image_admission_invalid",
                )
                image_bytes_total += len(part.data)
                sequence.append(part.occurrence_id)
                require(
                    len(sequence) <= limits["max_request_images"]
                    and len(part.data) <= limits["max_image_bytes"]
                    and image_bytes_total <= limits["max_request_image_bytes"],
                    "image_budget",
                )
                uri = f"data:{part.media_type};base64," + base64.b64encode(
                    part.data
                ).decode("ascii")
                blocks.append({"type": "image_url", "image_url": {"url": uri}})
                part_shapes.append(
                    {
                        "kind": "image",
                        "occurrence_id": part.occurrence_id,
                        "content_sha256": part.sha256,
                    }
                )
            else:
                raise ImageContractError("image_admission_invalid") from None
        content = message.text if type(message) is ProviderMessage else blocks
        messages.append({"role": message.role, "content": content})
        shapes.append({"role": message.role, "parts": part_shapes})
    require(bool(sequence), "image_admission_invalid")
    shape = digest("request-shape-v1", {"model": request.model, "messages": shapes})
    import json

    body = {"model": request.model, "messages": messages}
    require(
        len(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        <= limits["max_request_body_bytes"],
        "image_budget",
    )
    return body, shape, sequence
