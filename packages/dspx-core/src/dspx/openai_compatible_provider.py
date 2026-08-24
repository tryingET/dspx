# summary: "Implements the bounded loopback-only OpenAI-compatible DSPx provider port."
# read_when:
#   - "Changing local OpenAI-compatible HTTP dispatch, response validation, or effects."

from __future__ import annotations

from collections import deque
from _thread import RLock as ReentrantLock
import ipaddress
import json
import math
import re
from typing import Final
from urllib.parse import urlsplit, urlunsplit

import httpx

from .policy import (
    allow_network_mutate,
    check_capability,
    check_provider_allowed,
    max_timeout,
)
from .provider_contract import (
    EffectDisposition,
    ProviderAttemptEvent,
    ProviderInvocationError,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
)

_PROVIDER_KIND: Final = "openai-compatible"
_FAILURE_MESSAGE: Final = "DSPx openai-compatible provider invocation failed"
_MAX_MODEL_CHARS: Final = 256
_MAX_MESSAGES: Final = 256
_MAX_INPUT_CHARS: Final = 1_000_000
_MAX_OUTPUT_CHARS: Final = 1_000_000
_MAX_RESPONSE_BYTES: Final = 2_000_000
_MAX_USAGE_TOKENS: Final = 1_000_000_000
_USAGE_KEYS: Final = frozenset({"prompt_tokens", "completion_tokens", "total_tokens"})
_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9_~-]+(?:\.[A-Za-z0-9_~-]+)*$")


class _ResponseFailure(Exception):
    def __init__(self, observed_model: str | None = None) -> None:
        super().__init__("invalid response")
        self.observed_model = observed_model


def _default_transport() -> httpx.BaseTransport:
    return httpx.HTTPTransport(trust_env=False, retries=0)


class OpenAICompatibleProvider:
    """One synchronous text-only chat-completions transport with no DSPy inheritance."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: float = 30.0,
        _transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url, self._endpoint = _validated_endpoint(base_url)
        self._model = _validated_model(model)
        configured_timeout = _validated_timeout(timeout)
        policy_cap = max_timeout()
        self._effective_timeout = (
            min(configured_timeout, policy_cap)
            if policy_cap is not None
            else configured_timeout
        )
        if _transport is not None and not isinstance(_transport, httpx.BaseTransport):
            raise TypeError("test transport must implement httpx.BaseTransport")
        transport = _transport if _transport is not None else _default_transport()
        self._client = httpx.Client(
            auth=None,
            cookies=None,
            timeout=self._effective_timeout,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )
        self._operation_lock = ReentrantLock()
        self._events: deque[ProviderAttemptEvent] = deque(maxlen=64)
        self._attempt_total = 0
        self._terminal_effect: EffectDisposition | None = None
        self._indeterminate_latched = False

    @property
    def operation_lock(self) -> ReentrantLock:
        return self._operation_lock

    @property
    def model(self) -> str:
        with self._operation_lock:
            return self._model

    @property
    def base_endpoint(self) -> str:
        with self._operation_lock:
            return self._base_url

    @property
    def effective_timeout(self) -> float:
        with self._operation_lock:
            return self._effective_timeout

    @property
    def provider_events(self) -> tuple[ProviderAttemptEvent, ...]:
        with self._operation_lock:
            return tuple(self._events)

    @property
    def attempt_total(self) -> int:
        with self._operation_lock:
            return self._attempt_total

    @property
    def attempts_truncated(self) -> bool:
        with self._operation_lock:
            return self._attempt_total > len(self._events)

    @property
    def terminal_effect(self) -> EffectDisposition | None:
        with self._operation_lock:
            return self._terminal_effect

    def invoke(self, request: ProviderRequest) -> ProviderResult:
        """Serialize one complete direct invocation through terminal classification."""

        with self._operation_lock:
            return self._invoke(request)

    def _invoke(self, request: ProviderRequest) -> ProviderResult:
        """Dispatch exactly once after complete local validation and never retry."""

        if self._indeterminate_latched:
            raise ProviderInvocationError(
                _FAILURE_MESSAGE,
                disposition=EffectDisposition.EFFECT_INDETERMINATE,
                provider=_PROVIDER_KIND,
            ) from None

        requested_model = _requested_model(request)
        try:
            payload = self._request_payload(request)
            canonical_base, canonical_endpoint = _validated_endpoint(self._base_url)
            if canonical_base != self._base_url or canonical_endpoint != self._endpoint:
                raise ValueError("provider endpoint identity changed")
            if not allow_network_mutate():
                raise PermissionError(
                    "network mutation requires explicit policy opt-in"
                )
            check_provider_allowed(_PROVIDER_KIND)
            check_capability("network.mutate")
            http_request = httpx.Request(
                "POST",
                canonical_endpoint,
                headers={"Content-Type": "application/json"},
                content=json.dumps(
                    payload, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8"),
            )
        except Exception:
            self._fail(
                requested_model=requested_model,
                observed_model=None,
                dispatch_count=0,
                disposition=EffectDisposition.PREFLIGHT_REJECTED,
            )

        try:
            response = self._client.send(http_request, stream=True)
        except Exception:
            self._fail(
                requested_model=requested_model,
                observed_model=None,
                dispatch_count=1,
                disposition=EffectDisposition.EFFECT_INDETERMINATE,
            )

        try:
            status_code = int(response.status_code)
            body = _read_bounded(response)
        except Exception:
            failure = EffectDisposition.EFFECT_INDETERMINATE
        else:
            failure = None
        finally:
            try:
                response.close()
            except Exception:
                pass
        if failure is not None:
            self._fail(
                requested_model=requested_model,
                observed_model=None,
                dispatch_count=1,
                disposition=failure,
            )

        if not 200 <= status_code < 300:
            self._fail(
                requested_model=requested_model,
                observed_model=None,
                dispatch_count=1,
                disposition=EffectDisposition.COMPLETED_FAILURE,
            )

        try:
            text, usage, observed_model = self._validated_response(body)
        except _ResponseFailure as exc:
            observed_model = exc.observed_model
            failure = EffectDisposition.COMPLETED_FAILURE
        except Exception:
            observed_model = None
            failure = EffectDisposition.COMPLETED_FAILURE
        else:
            failure = None
        if failure is not None:
            self._fail(
                requested_model=requested_model,
                observed_model=observed_model,
                dispatch_count=1,
                disposition=failure,
            )

        disposition = EffectDisposition.COMPLETED_SUCCESS
        self._record(
            requested_model=requested_model,
            observed_model=observed_model,
            dispatch_count=1,
            disposition=disposition,
        )
        return ProviderResult(
            text=text,
            model=self.model,
            effect_disposition=disposition,
            usage=usage,
            provider_data={"provider_kind": _PROVIDER_KIND},
        )

    def latch_indeterminate_after_dispatch(self) -> None:
        """Reclassify only the latest dispatched attempt without adding an attempt."""

        with self._operation_lock:
            self._indeterminate_latched = True
            if not self._events or self._events[-1].dispatch_count != 1:
                return
            latest = self._events[-1]
            self._events[-1] = ProviderAttemptEvent(
                provider_kind=latest.provider_kind,
                requested_model=latest.requested_model,
                observed_model=latest.observed_model,
                dispatch_count=latest.dispatch_count,
                disposition=EffectDisposition.EFFECT_INDETERMINATE,
            )
            self._terminal_effect = EffectDisposition.EFFECT_INDETERMINATE

    def dump_state(self) -> dict[str, object]:
        with self._operation_lock:
            raise RuntimeError("openai-compatible provider state is unsupported")

    def close(self) -> None:
        with self._operation_lock:
            self._client.close()

    def _request_payload(self, request: ProviderRequest) -> dict[str, object]:
        if type(request) is not ProviderRequest or request.model != self.model:
            raise ValueError("provider request identity is invalid")
        if not request.messages or len(request.messages) > _MAX_MESSAGES:
            raise ValueError("provider request message count is invalid")
        total_chars = 0
        messages: list[dict[str, str]] = []
        for message in request.messages:
            if (
                type(message) is not ProviderMessage
                or message.role not in {"system", "user", "assistant"}
                or not isinstance(message.text, str)
            ):
                raise ValueError("provider request message is invalid")
            total_chars += len(message.text)
            if total_chars > _MAX_INPUT_CHARS:
                raise ValueError("provider request exceeds the input bound")
            messages.append({"role": message.role, "content": message.text})
        return {"model": self.model, "messages": messages}

    def _validated_response(self, body: bytes) -> tuple[str, dict[str, int], str]:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise _ResponseFailure()
        if payload.get("model") != self.model:
            raise _ResponseFailure()
        observed_model = self.model
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise _ResponseFailure(observed_model)
        choice = choices[0]
        if not isinstance(choice, dict):
            raise _ResponseFailure(observed_model)
        message = choice.get("message")
        if (
            not isinstance(message, dict)
            or set(message) != {"role", "content"}
            or message.get("role") != "assistant"
            or not isinstance(message.get("content"), str)
            or "text" in choice
        ):
            raise _ResponseFailure(observed_model)
        text = message["content"]
        if len(text) > _MAX_OUTPUT_CHARS:
            raise _ResponseFailure(observed_model)

        if "usage" not in payload:
            return text, {}, self.model
        usage_payload = payload["usage"]
        if not isinstance(usage_payload, dict) or set(usage_payload) != _USAGE_KEYS:
            raise _ResponseFailure(observed_model)
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            or value > _MAX_USAGE_TOKENS
            for value in usage_payload.values()
        ):
            raise _ResponseFailure(observed_model)
        if (
            usage_payload["total_tokens"]
            != usage_payload["prompt_tokens"] + usage_payload["completion_tokens"]
        ):
            raise _ResponseFailure(observed_model)
        return (
            text,
            {
                "input_tokens": usage_payload["prompt_tokens"],
                "output_tokens": usage_payload["completion_tokens"],
                "total_tokens": usage_payload["total_tokens"],
            },
            self.model,
        )

    def _record(
        self,
        *,
        requested_model: str,
        observed_model: str | None,
        dispatch_count: int,
        disposition: EffectDisposition,
    ) -> None:
        self._attempt_total += 1
        self._terminal_effect = disposition
        if disposition is EffectDisposition.EFFECT_INDETERMINATE:
            self._indeterminate_latched = True
        self._events.append(
            ProviderAttemptEvent(
                provider_kind=_PROVIDER_KIND,
                requested_model=requested_model,
                observed_model=observed_model,
                dispatch_count=dispatch_count,
                disposition=disposition,
            )
        )

    def _fail(
        self,
        *,
        requested_model: str,
        observed_model: str | None,
        dispatch_count: int,
        disposition: EffectDisposition,
    ) -> None:
        self._record(
            requested_model=requested_model,
            observed_model=observed_model,
            dispatch_count=dispatch_count,
            disposition=disposition,
        )
        raise ProviderInvocationError(
            _FAILURE_MESSAGE,
            disposition=disposition,
            provider=_PROVIDER_KIND,
        ) from None


def _validated_endpoint(base_url: str) -> tuple[str, str]:
    if (
        not isinstance(base_url, str)
        or not base_url
        or base_url != base_url.strip()
        or any(
            char.isspace() or ord(char) < 32 or ord(char) == 127 for char in base_url
        )
    ):
        raise ValueError("base URL must be a bounded canonical string")
    try:
        parsed = urlsplit(base_url)
        host = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
        if host is None or "%" in host:
            raise ValueError("scoped or absent host")
        address = ipaddress.ip_address(host)
    except (TypeError, ValueError):
        raise ValueError(
            "base URL must use an IP-literal loopback HTTP origin"
        ) from None
    path = parsed.path
    segments = path.strip("/").split("/") if path.strip("/") else []
    if (
        parsed.scheme != "http"
        or not address.is_loopback
        or username is not None
        or password is not None
        or parsed.query
        or parsed.fragment
        or port == 0
        or "\\" in path
        or "%" in path
        or "//" in path
        or any(segment in {".", ".."} for segment in segments)
        or any(not _PATH_SEGMENT.fullmatch(segment) for segment in segments)
        or [segment.lower() for segment in segments[-2:]] == ["chat", "completions"]
    ):
        raise ValueError("base URL must use an unambiguous loopback HTTP endpoint")
    netloc = f"[{address.compressed}]" if address.version == 6 else address.compressed
    if port is not None:
        netloc = f"{netloc}:{port}"
    base_path = "/" + "/".join(segments) if segments else ""
    canonical_base = urlunsplit(("http", netloc, base_path, "", ""))
    endpoint = urlunsplit(("http", netloc, f"{base_path}/chat/completions", "", ""))
    return canonical_base, endpoint


def _validated_model(model: str) -> str:
    if (
        not isinstance(model, str)
        or not model
        or len(model) > _MAX_MODEL_CHARS
        or model != model.strip()
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in model)
    ):
        raise ValueError("model must be a bounded canonical non-empty string")
    return model


def _validated_timeout(timeout: float) -> float:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or float(timeout) <= 0
    ):
        raise ValueError("timeout must be a positive finite number")
    return float(timeout)


def _requested_model(request: object) -> str:
    try:
        model = getattr(request, "model", None)
    except Exception:
        return "<invalid>"
    return _safe_event_model(model) or "<invalid>"


def _safe_event_model(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return _validated_model(value)
    except (TypeError, ValueError):
        return None


def _read_bounded(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        if not isinstance(chunk, bytes):
            raise TypeError("HTTP response chunk is not bytes")
        size += len(chunk)
        if size > _MAX_RESPONSE_BYTES:
            raise ValueError("HTTP response exceeds the byte bound")
        chunks.append(chunk)
    return b"".join(chunks)
