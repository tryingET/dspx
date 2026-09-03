"""Task-local provider families for foundry-only dspy-lm-auth jury calls."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlsplit

from dspx.services.provider_outcome_receipt_contract import ID_RE as _ROUTE_ID_RE
from dspx.services.soomfon_provider_outcome_receipt_contract import (
    canonical_json,
    sha256,
)

# Same derivation as program_oracle_semantic_gate4_v11._validate_endpoint so the
# Codex family reproduces the historical pinned constant byte-for-byte.
ENDPOINT_ORIGIN_DOMAIN = b"dspx-oracle-semantic-v11-endpoint-origin-v1\0"
CREDENTIAL_MODE = "no-refresh"
DEFAULT_TIMEOUT_SECONDS = 60.0
IMPLEMENTATION_TASK_ID = 5308
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
_LOOPBACK_PATH = "/v1"


def endpoint_origin_sha256(endpoint: str) -> str:
    """Hash the https origin of one fixed provider endpoint."""

    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("endpoint origin must be a plain https origin")
    return sha256(
        ENDPOINT_ORIGIN_DOMAIN
        + canonical_json({"scheme": parsed.scheme, "hostname": parsed.hostname})
    )


def validate_loopback_endpoint(value: object) -> str:
    """Accept exactly ``http://{127.0.0.1|localhost|[::1]}:<port>/v1``.

    Mirrors ``dspy_lm_auth.chat_backend_contract.validate_loopback_api_base`` so
    DSPx rejects the same inputs before the owner backend is constructed. Port
    80 is rejected because the owner transport normalizes it away.
    """

    if (
        not isinstance(value, str)
        or not value
        or not all(0x21 <= ord(char) <= 0x7E for char in value)
    ):
        raise ValueError("local endpoint must be a printable ASCII URL")
    parts = urlsplit(value)
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("local endpoint port is not valid") from exc
    host = parts.netloc.rsplit(":", 1)[0]
    if (
        parts.scheme != "http"
        or "@" in parts.netloc
        or port is None
        or port == 80
        or not 1 <= port <= 65535
        or host not in _LOOPBACK_HOSTS
        or parts.netloc != f"{host}:{port}"
        or parts.path != _LOOPBACK_PATH
        or parts.query
        or parts.fragment
        or value != f"http://{host}:{port}{_LOOPBACK_PATH}"
    ):
        raise ValueError("local endpoint is outside the loopback endpoint contract")
    return value


def loopback_endpoint_origin_sha256(endpoint: str) -> str:
    """Hash the exact ``http`` loopback origin, including its explicit port."""

    validated = validate_loopback_endpoint(endpoint)
    parsed = urlsplit(validated)
    return sha256(
        ENDPOINT_ORIGIN_DOMAIN
        + canonical_json(
            {"scheme": "http", "hostname": parsed.hostname, "port": parsed.port}
        )
    )


def _route_model(model: str) -> str:
    """Project a model id into the receipt route charset.

    Served local model ids may carry ``/`` (``org/model``); receipt routes are
    bounded ids without it. ``:`` is outside every family's model charset, so
    the projection is injective and the exact model stays retained in the
    request, metadata, and juror results.
    """

    return model.replace("/", ":")


@dataclass(frozen=True, slots=True)
class FoundryJuryProviderFamily:
    """One reviewed task-local provider family over a dspy-lm-auth backend."""

    provider_name: str
    auth_provider: str
    model_re: re.Pattern[str]
    default_model: str
    allowed_reasoning_efforts: frozenset[str] | None
    default_reasoning_effort: str | None
    execution_task_title: str
    endpoint_origin: str
    endpoint_origin_sha256: str
    requested_route_template: str
    resolved_route_template: str
    backend_module: str
    backend_class: str
    contract_module: str
    message_class: str
    request_class: str
    response_class: str
    allowed_roles: frozenset[str]
    model_key: str
    strict_observed_model: bool
    # Env-resolved families bind the exact loopback base URL per run: the
    # request key retains it and the origin hash is recomputed on resolution.
    endpoint_env: str | None = None
    endpoint_key: str | None = None

    def requested_route(self, model: str) -> str:
        return self.requested_route_template.format(model=_route_model(model))

    def resolved_route(self, model: str) -> str:
        return self.resolved_route_template.format(model=_route_model(model))

    def model_allowed(self, model: object) -> bool:
        """Family model rule plus the receipt contract's bounded route ids."""

        return (
            isinstance(model, str)
            and self.model_re.fullmatch(model) is not None
            and _ROUTE_ID_RE.fullmatch(self.requested_route(model)) is not None
            and _ROUTE_ID_RE.fullmatch(self.resolved_route(model)) is not None
        )

    def reasoning_effort_allowed(self, value: object) -> bool:
        if self.allowed_reasoning_efforts is None:
            return value is None
        return isinstance(value, str) and value in self.allowed_reasoning_efforts

    def resolve_model(self, model: str | None) -> str:
        return self.default_model if model is None else model

    def resolve_reasoning_effort(self, value: str | None) -> str | None:
        return self.default_reasoning_effort if value is None else value

    @property
    def endpoint_resolved(self) -> bool:
        return self.endpoint_env is not None

    def with_endpoint(self, endpoint: str | None) -> FoundryJuryProviderFamily:
        """Bind one explicit or environment-provided endpoint into this family.

        Fixed families accept only ``None`` and return themselves. Env-resolved
        families read ``endpoint_env`` when ``endpoint`` is None, validate the
        loopback contract, and return a copy whose origin hash covers exactly
        that origin.
        """

        if self.endpoint_env is None:
            if endpoint is not None:
                raise ValueError(f"{self.auth_provider} endpoint is fixed")
            return self
        resolved = (
            os.environ.get(self.endpoint_env, self.endpoint_origin)
            if endpoint is None
            else endpoint
        )
        validated = validate_loopback_endpoint(resolved)
        if validated == self.endpoint_origin:
            return self
        return replace(
            self,
            endpoint_origin=validated,
            endpoint_origin_sha256=loopback_endpoint_origin_sha256(validated),
        )

    def construct_backend(
        self,
        owner: Any,
        *,
        auth_path: str | os.PathLike[str] | None = None,
        endpoint: str | None = None,
    ) -> Any:
        """Instantiate the exact owner backend type for this family.

        Fixed families construct ``backend_type()`` (or with ``auth_path``
        when one is given). Env-resolved families pass their bound loopback
        base URL positionally and never read a credential file.
        """

        backend_type = owner.backend_type
        if self.endpoint_env is None:
            if endpoint is not None and endpoint != self.endpoint_origin:
                raise ValueError(f"{self.auth_provider} endpoint is fixed")
            if auth_path is None:
                return backend_type()
            return backend_type(auth_path=auth_path)
        if auth_path is not None:
            raise ValueError(f"{self.auth_provider} backend reads no credential")
        if endpoint is not None and endpoint != self.endpoint_origin:
            raise ValueError(f"{self.auth_provider} endpoint drifted from the family")
        return backend_type(self.endpoint_origin)

    def build_backend_request(
        self,
        owner: Any,
        *,
        model: str,
        messages: tuple[Any, ...],
        reasoning_effort: str | None,
        timeout_seconds: float,
    ) -> Any:
        """Build the exact owner request type for this family."""

        if self.allowed_reasoning_efforts is None:
            return owner.request_type(
                model=model,
                messages=messages,
                timeout_seconds=timeout_seconds,
            )
        return owner.request_type(
            model=model,
            messages=messages,
            reasoning_effort=reasoning_effort,
            response_format="text",
            timeout_seconds=timeout_seconds,
        )

    def execution_request_keys(self, common: frozenset[str]) -> frozenset[str]:
        keys = {
            "owner_source_root",
            "execution_task_id",
            "execution_claimant",
            self.model_key,
        }
        if self.allowed_reasoning_efforts is not None:
            keys.add("reasoning_effort")
        if self.endpoint_key is not None:
            keys.add(self.endpoint_key)
        return common | keys


CODEX_ENDPOINT_ORIGIN = "https://chatgpt.com/backend-api/codex"
COPILOT_ENDPOINT_ORIGIN = "https://api.individual.githubcopilot.com"
XAI_ENDPOINT_ORIGIN = "https://api.x.ai"
LOCAL_VLLM_ENDPOINT_ENV = "DSPX_LOCAL_VLLM_BASE_URL"
LOCAL_VLLM_DEFAULT_ENDPOINT = "http://127.0.0.1:2456/v1"
_CHAT_CONTRACT_MODULE = "dspy_lm_auth.chat_backend_contract"
_CHAT_ROLES = frozenset({"system", "user", "assistant"})

CODEX_FAMILY = FoundryJuryProviderFamily(
    provider_name="foundry-dspy-lm-auth-codex",
    auth_provider="codex",
    model_re=re.compile(r"^gpt-[A-Za-z0-9][A-Za-z0-9.-]{0,63}$"),
    default_model="gpt-5.4",
    allowed_reasoning_efforts=frozenset({"low", "medium", "high", "xhigh"}),
    default_reasoning_effort="xhigh",
    execution_task_title=(
        "Execute one receipt-bound foundry comparison jury with dspy-lm-auth Codex"
    ),
    endpoint_origin=CODEX_ENDPOINT_ORIGIN,
    endpoint_origin_sha256=(
        "7d4b206e8a080358f16d8048e0705d8e17c9df9b8968ab150ff73ed1643294c8"
    ),
    requested_route_template="dspy-lm-auth:codex:{model}",
    resolved_route_template="openai:{model}:responses",
    backend_module="dspy_lm_auth.codex_backend",
    backend_class="CodexBackend",
    contract_module="dspy_lm_auth.codex_backend_contract",
    message_class="CodexBackendMessage",
    request_class="CodexBackendRequest",
    response_class="CodexBackendResponse",
    allowed_roles=frozenset({"system", "developer", "user", "assistant"}),
    model_key="codex_model",
    strict_observed_model=True,
)

# The maintained fork now defines the Copilot message/request/response names
# as aliases of the generic chat contract types, so the loaded-owner check
# binds the generic contract module for every chat-completions family.
COPILOT_FAMILY = FoundryJuryProviderFamily(
    provider_name="foundry-dspy-lm-auth-github-copilot",
    auth_provider="github-copilot",
    model_re=re.compile(r"^(gemini|grok)-[a-z0-9][a-z0-9.-]{0,63}$"),
    default_model="gemini-3.7-flash",
    allowed_reasoning_efforts=None,
    default_reasoning_effort=None,
    execution_task_title=(
        "Execute one receipt-bound foundry comparison jury with dspy-lm-auth "
        "GitHub Copilot"
    ),
    endpoint_origin=COPILOT_ENDPOINT_ORIGIN,
    endpoint_origin_sha256=(
        "492c0bc03782d6829c9555ed9da0d359510619c2beb561c89505495cb241871d"
    ),
    requested_route_template="dspy-lm-auth:github-copilot:{model}",
    resolved_route_template="openai:{model}:chat",
    backend_module="dspy_lm_auth.copilot_backend",
    backend_class="GithubCopilotBackend",
    contract_module=_CHAT_CONTRACT_MODULE,
    message_class="ChatBackendMessage",
    request_class="ChatBackendRequest",
    response_class="ChatBackendResponse",
    allowed_roles=_CHAT_ROLES,
    model_key="model",
    strict_observed_model=False,
)

XAI_FAMILY = FoundryJuryProviderFamily(
    provider_name="foundry-dspy-lm-auth-xai",
    auth_provider="xai",
    model_re=re.compile(r"^grok-[a-z0-9][a-z0-9.-]{0,63}$"),
    default_model="grok-4.6",
    allowed_reasoning_efforts=None,
    default_reasoning_effort=None,
    execution_task_title=(
        "Execute one receipt-bound foundry comparison jury with dspy-lm-auth xAI"
    ),
    endpoint_origin=XAI_ENDPOINT_ORIGIN,
    endpoint_origin_sha256=(
        "b1cca9c83dc27a51b9887f2a66a651bea19f23ac4d86dccc456fab2141f5e40d"
    ),
    requested_route_template="dspy-lm-auth:xai:{model}",
    resolved_route_template="openai:{model}:chat",
    backend_module="dspy_lm_auth.xai_backend",
    backend_class="XaiBackend",
    contract_module=_CHAT_CONTRACT_MODULE,
    message_class="ChatBackendMessage",
    request_class="ChatBackendRequest",
    response_class="ChatBackendResponse",
    allowed_roles=_CHAT_ROLES,
    model_key="model",
    strict_observed_model=False,
)

LOCAL_VLLM_FAMILY = FoundryJuryProviderFamily(
    provider_name="foundry-dspy-lm-auth-local-vllm",
    auth_provider="none",
    model_re=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$"),
    default_model="local/Qwen3.8-27B-AEON-NVFP4-FP8",
    allowed_reasoning_efforts=None,
    default_reasoning_effort=None,
    execution_task_title=(
        "Execute one receipt-bound foundry comparison jury with dspy-lm-auth local vLLM"
    ),
    endpoint_origin=LOCAL_VLLM_DEFAULT_ENDPOINT,
    endpoint_origin_sha256=(
        "ba556a06889d35554dd17c01d1aa4f421082aefb8602d915919c4920872eb3bb"
    ),
    requested_route_template="dspy-lm-auth:local-vllm:{model}",
    resolved_route_template="openai:{model}:chat",
    backend_module="dspy_lm_auth.local_vllm_backend",
    backend_class="LocalVllmBackend",
    contract_module=_CHAT_CONTRACT_MODULE,
    message_class="ChatBackendMessage",
    request_class="ChatBackendRequest",
    response_class="ChatBackendResponse",
    allowed_roles=_CHAT_ROLES,
    model_key="model",
    strict_observed_model=False,
    endpoint_env=LOCAL_VLLM_ENDPOINT_ENV,
    endpoint_key="local_vllm_base_url",
)

FAMILIES: Mapping[str, FoundryJuryProviderFamily] = {
    CODEX_FAMILY.provider_name: CODEX_FAMILY,
    COPILOT_FAMILY.provider_name: COPILOT_FAMILY,
    XAI_FAMILY.provider_name: XAI_FAMILY,
    LOCAL_VLLM_FAMILY.provider_name: LOCAL_VLLM_FAMILY,
}
TASK_LOCAL_PROVIDER_NAMES = frozenset(FAMILIES)


def family_for_provider(provider: object) -> FoundryJuryProviderFamily | None:
    """Return the task-local family for a provider name, or None when generic.

    Env-resolved families come back with their default endpoint; use
    ``family_for_request`` to bind the endpoint retained in a request.
    """

    if not isinstance(provider, str):
        return None
    return FAMILIES.get(provider)


def family_for_request(request: Mapping[str, Any]) -> FoundryJuryProviderFamily | None:
    """Return the family bound to the exact endpoint retained in ``request``."""

    family = family_for_provider(request.get("provider"))
    if family is None or family.endpoint_key is None:
        return family
    endpoint = request.get(family.endpoint_key)
    if not isinstance(endpoint, str):
        raise ValueError(f"{family.auth_provider} endpoint is missing from request")
    return family.with_endpoint(endpoint)


__all__ = [
    "CODEX_FAMILY",
    "COPILOT_FAMILY",
    "CREDENTIAL_MODE",
    "DEFAULT_TIMEOUT_SECONDS",
    "ENDPOINT_ORIGIN_DOMAIN",
    "FAMILIES",
    "IMPLEMENTATION_TASK_ID",
    "LOCAL_VLLM_DEFAULT_ENDPOINT",
    "LOCAL_VLLM_ENDPOINT_ENV",
    "LOCAL_VLLM_FAMILY",
    "TASK_LOCAL_PROVIDER_NAMES",
    "XAI_FAMILY",
    "FoundryJuryProviderFamily",
    "endpoint_origin_sha256",
    "family_for_provider",
    "family_for_request",
    "loopback_endpoint_origin_sha256",
    "validate_loopback_endpoint",
]
