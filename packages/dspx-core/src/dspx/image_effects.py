"""Image HTTP effect phases; provisional facts are not immutable terminals."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import time
from typing import TYPE_CHECKING

import httpx
from dspy import BaseLM, LMRequest, LMResponse
from dspy.core.types import LMUsage

from .image_admission import CEILINGS, ImageContractError, parse_json, require, sha
from .image_records import publish, read_record
from .image_custody import ImageCustodySession
from .image_input_contract import reject_output
from .image_privacy import require_privacy
from .image_supervision import worker_deadline, require_admitted_worker_budget
from .policy import allow_network_mutate, check_capability, check_provider_allowed
from .provider_contract import (
    EffectDisposition,
    ProviderRequest,
    ProviderResult,
    image_payload,
)

if TYPE_CHECKING:
    from .openai_compatible_provider import OpenAICompatibleProvider
    from .dspy_typed_lm import DSPyTypedLMAdapter


def typed_provider_response(
    lm: DSPyTypedLMAdapter, result: ProviderResult
) -> LMResponse:
    """Common unchanged typed-finalization checks for image and historical text."""
    from .dspy_typed_lm import _ProviderResultFailure
    from .openai_compatible_provider import OpenAICompatibleProvider
    from .stub_provider import StubProvider

    if type(result) is not ProviderResult:
        raise TypeError("provider returned an invalid result type")
    if not isinstance(result.effect_disposition, EffectDisposition):
        raise TypeError("provider returned an invalid effect disposition")
    if result.effect_disposition is not EffectDisposition.COMPLETED_SUCCESS:
        raise _ProviderResultFailure(code=result.effect_disposition.value)
    if result.model != lm.model:
        raise _ProviderResultFailure(code="provider_model_mismatch")
    if not isinstance(result.text, str) or len(result.text) > 1_000_000:
        raise ValueError("provider result text is invalid or exceeds the bound")
    provider_data = dict(result.provider_data)
    usage_data = dict(result.usage)
    keys = {"input_tokens", "output_tokens", "total_tokens"}
    if type(lm.provider) is StubProvider:
        if provider_data != {"provider_kind": "stub"}:
            raise ValueError("provider data is not in the stub allowlist")
        if set(usage_data) != keys or any(
            value != 0 or isinstance(value, bool) for value in usage_data.values()
        ):
            raise ValueError("provider usage is not the exact zero-token canary shape")
    elif type(lm.provider) is OpenAICompatibleProvider:
        if provider_data != {"provider_kind": "openai-compatible"}:
            raise ValueError("provider data is not in the HTTP provider allowlist")
        if usage_data and (
            set(usage_data) != keys
            or any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in usage_data.values()
            )
        ):
            raise ValueError("provider usage is incomplete or invalid")
    else:
        raise ValueError("provider result is not from an allowlisted provider")
    provider_data["effect_disposition"] = result.effect_disposition.value
    return LMResponse.from_text(
        result.text,
        model=lm.model,
        usage=LMUsage(
            input_tokens=usage_data.get("input_tokens"),
            output_tokens=usage_data.get("output_tokens"),
            total_tokens=usage_data.get("total_tokens"),
        ),
        provider_data=provider_data,
    )


class ObservedResponseFailure(Exception):
    """Only a fully observed, explicitly checked local refusal selects this phase."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def invoke_image_provider(
    provider: OpenAICompatibleProvider, request: ProviderRequest
) -> ProviderResult:
    """Clean-boundary probe precedes the operation lock; then one image dispatch."""
    require_privacy()
    with provider.operation_lock:
        return invoke_image_http(provider, request)


def invoke_image_http(
    provider: OpenAICompatibleProvider, request: ProviderRequest
) -> ProviderResult:
    from .openai_compatible_provider import _validated_endpoint, _ResponseFailure

    active = require_privacy()
    active.check()
    session = provider.image_session
    if type(session) is not ImageCustodySession:
        raise ImageContractError("image_custody") from None
    require(
        active.session is session and active.context is session.context, "image_privacy"
    )
    require(not provider._indeterminate_latched, "image_spent")
    from .provider_contract import ImageClientBinding

    binding = provider._image_client_binding
    if type(binding) is not ImageClientBinding:
        raise ImageContractError("image_privacy") from None
    binding.check(provider._client)
    with session.transaction("direct_provider") as tx:
        body, shape, sequence = image_payload(request, session)
        base, endpoint = _validated_endpoint(provider.base_endpoint)
        require(
            base == session.record["canonical_base_endpoint"]
            and provider.model == session.record["model"],
            "image_admission_invalid",
        )
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        require(
            len(raw) <= session.record["limits"]["max_request_body_bytes"],
            "image_budget",
        )
        require(allow_network_mutate(), "image_admission_invalid")
        check_provider_allowed("openai-compatible")
        check_capability("network.mutate")
        require(
            provider.effective_timeout * 1000
            <= session.record["deadlines"]["per_request_io_timeout_ms"],
            "image_budget",
        )
        timeout = min(provider.effective_timeout, worker_deadline() - time.monotonic())
        require(timeout > 0, "image_budget")
        http_request = httpx.Request(
            "POST",
            endpoint,
            headers={"Content-Type": "application/json"},
            content=raw,
            extensions={
                "timeout": {
                    key: timeout for key in ("connect", "read", "write", "pool")
                }
            },
        )
        tx.reserve(shape, sequence)
        response: httpx.Response | None = None
        result: ProviderResult | None = None
        disposition = "effect_indeterminate"
        failure: str | None = "io"
        try:
            active.check()
            require_admitted_worker_budget(session.record["deadlines"])
            binding.check(provider._client)
            tx.dispatch_entered = True
            response = provider._client.send(http_request, stream=True)
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                worker_deadline()
                require(type(chunk) is bytes, "image_input_invalid")
                size += len(chunk)
                require(
                    size <= session.record["limits"]["max_response_bytes"],
                    "image_budget",
                )
                chunks.append(chunk)
            data = b"".join(chunks)
            tx.response_sha256, tx.response_byte_count = sha(data), len(data)
            # Body collection alone never selects completed_failure: unexpected
            # validation/SDK/cleanup faults remain unknown even with these facts.
            if not 200 <= response.status_code < 300:
                raise ObservedResponseFailure("response")
            try:
                text, usage, observed = provider._validated_response(data)
            except (_ResponseFailure, json.JSONDecodeError, UnicodeDecodeError):
                raise ObservedResponseFailure("response") from None
            tx.observed_model = observed
            try:
                reject_output(text, session.context)
                require(
                    type(text) is str
                    and len(text) <= session.record["limits"]["max_output_chars"],
                    "image_budget",
                )
            except ImageContractError as error:
                raise ObservedResponseFailure(
                    "budget" if error.code == "image_budget" else "privacy"
                ) from None
            result = ProviderResult(
                text,
                observed,
                EffectDisposition.COMPLETED_SUCCESS,
                usage,
                {"provider_kind": "openai-compatible"},
            )
            tx.result_completed = True
        except ObservedResponseFailure as error:
            disposition, failure = "completed_failure", error.code
        except BaseException:
            if not tx.dispatch_entered:
                disposition, failure = "preflight_rejected", "validation"
            else:
                disposition, failure = "effect_indeterminate", "finalization"
        # Exactly one cleanup attempt, and BEFORE selecting/publishing terminal
        # facts. A failed close is not retried through a finally block.
        if response is not None:
            owned_response, response = response, None
            try:
                owned_response.close()
            except BaseException:
                disposition, failure, result = (
                    "effect_indeterminate",
                    "finalization",
                    None,
                )
        if result is not None:
            try:
                active.check()
                worker_deadline()
            except BaseException:
                disposition, failure, result = (
                    "effect_indeterminate",
                    "finalization",
                    None,
                )
            else:
                disposition, failure = "completed_success", None
        tx.pending_disposition, tx.pending_failure = disposition, failure
        if disposition == "effect_indeterminate":
            provider._indeterminate_latched = session.poisoned = True
        if tx.kind == "direct_provider":
            if disposition == "completed_success" and tx.ordinal == len(
                session.record["request_plan"]
            ):
                try:
                    provider.close()
                except BaseException:
                    disposition, failure, result = (
                        "effect_indeterminate",
                        "finalization",
                        None,
                    )
                    provider._indeterminate_latched = session.poisoned = True
            tx.finish(disposition, failure_code=failure)
        provider._record(
            requested_model=provider.model,
            observed_model=tx.observed_model,
            dispatch_count=int(tx.dispatch_entered),
            disposition=EffectDisposition(disposition),
        )
        if result is not None:
            return result
    raise ImageContractError("image_finalization") from None


def invoke_image_lm(
    lm: DSPyTypedLMAdapter,
    items: tuple[object, ...],
    kwargs: dict[str, object],
) -> LMResponse:
    from .openai_compatible_provider import OpenAICompatibleProvider

    provider = lm.provider
    if type(provider) is not OpenAICompatibleProvider:
        raise ImageContractError("image_custody") from None
    session = provider.image_session
    if type(session) is not ImageCustodySession:
        raise ImageContractError("image_custody") from None
    active = require_privacy()
    active.check()
    request = kwargs.get("request")
    if type(request) is not LMRequest:
        raise ImageContractError("image_admission_invalid") from None
    require(
        not items
        and set(kwargs) == {"request"}
        and active.lm is lm
        and active.session is session
        and lm.cache is False,
        "image_admission_invalid",
    )
    with lm._operation_lock, session.transaction("dspy_lm") as tx:
        try:
            result = BaseLM.__call__(lm, request=request)
            active.check()
            if type(result) is not LMResponse or not tx.result_completed:
                raise ImageContractError("image_finalization") from None
            tx.typed_completed = True
            if tx.ordinal == len(session.record["request_plan"]):
                provider.close()
            active.check()
            worker_deadline()
            tx.finish("completed_success")
            return result
        except BaseException as error:
            failure_code = (
                error.code
                if type(error) is ImageContractError
                else "image_finalization"
            )
            if session.poisoned:
                lm._latch_indeterminate()
            if tx.intent is not None and tx.terminal is None:
                disposition = tx.pending_disposition
                if disposition not in {"preflight_rejected", "completed_failure"}:
                    disposition = (
                        "effect_indeterminate"
                        if tx.dispatch_entered
                        else "preflight_rejected"
                    )
                if disposition == "effect_indeterminate":
                    lm._latch_indeterminate()
                    session.poisoned = True
                tx.finish(
                    disposition, failure_code=tx.pending_failure or "finalization"
                )
    raise ImageContractError(failure_code) from None


def image_effect_envelope(session) -> dict[str, object]:
    rows = session._scan()
    attempts = []
    for intent, terminal in rows:
        require(
            terminal is not None
            and terminal["provider_disposition"] != "effect_indeterminate",
            "image_spent",
        )
        attempts.append(
            {
                "provider_kind": "openai-compatible",
                "requested_model": session.record["model"],
                "observed_model": terminal["observed_model"],
                "dispatch_count": terminal["dispatch_count"],
                "disposition": terminal["provider_disposition"],
                **{
                    key: intent[key]
                    for key in (
                        "attempt_id",
                        "attempt_ordinal",
                        "plan_ordinal",
                        "request_sha256",
                        "validated_image_count",
                        "validated_image_bytes",
                    )
                },
                "intent_sha256": terminal["intent_sha256"],
                "terminal_sha256": sha(
                    read_record(
                        session.root_fd, f"terminal-{intent['attempt_ordinal']}.json"
                    )
                ),
                "failure_code": terminal["failure_code"],
            }
        )
    effects = [row["disposition"] for row in attempts]
    return {
        "schema_version": "dspx-provider-effect-evidence-v2",
        "image_contract_version": "dspx-bounded-image-contract-v2",
        "admission_sha256": session.admission.sha256,
        "input_manifest_sha256": session.manifest_sha256,
        "custody_id": session.binding["custody_id"],
        "caller_run_id": session.binding["caller_run_id"],
        "attempt_total": len(rows),
        "attempts_truncated": False,
        "terminal_effect": "completed_success"
        if effects and all(row == "completed_success" for row in effects)
        else "completed_failure",
        "attempts": attempts,
    }


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticTransportFixture:
    """Owner-defined closed response. The worker builds the exact MockTransport.

    Its handler publishes only send ordinal, block kinds, image hashes/media types and
    the request hash. No callable, transport object or HTTP body crosses processes.
    """

    completion: str
    observation_fd: int | None = None

    def __post_init__(self) -> None:
        require(
            type(self.completion) is str
            and 0 < len(self.completion) <= 16_384
            and (
                self.observation_fd is None
                or (type(self.observation_fd) is int and self.observation_fd > 2)
            ),
            "image_admission_invalid",
        )

    @property
    def record(self) -> dict[str, object]:
        return {"completion": self.completion, "observation_fd": self.observation_fd}


def fixture_transport(fixture: dict[str, object], model: str) -> httpx.MockTransport:
    observation_fd = fixture["observation_fd"]
    sends: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(True)
        packet = parse_json(request.content, limit=CEILINGS["max_request_body_bytes"])
        kinds: list[list[str]] = []
        images: list[str] = []
        media: list[str] = []
        for message in packet["messages"]:
            content = message["content"]
            if type(content) is str:
                kinds.append(["text"])
                continue
            kinds.append([block["type"] for block in content])
            for block in content:
                if block["type"] == "image_url":
                    header, _, data = block["image_url"]["url"].partition(",")
                    require(
                        header.startswith("data:") and header.endswith(";base64"),
                        "image_finalization",
                    )
                    media.append(header[5:-7])
                    images.append(sha(base64.b64decode(data, validate=True)))
        if type(observation_fd) is int:
            publish(
                observation_fd,
                f"wire-{len(sends)}.json",
                {
                    "schema_version": "dspx-image-wire-observation-v1",
                    "send_ordinal": len(sends),
                    "message_block_kinds": kinds,
                    "image_sha256": images,
                    "image_media_types": media,
                    "request_sha256": sha(request.content),
                },
            )
        return httpx.Response(
            200,
            json={
                "model": model,
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": fixture["completion"],
                        }
                    }
                ],
            },
            request=request,
        )

    return httpx.MockTransport(handler)
