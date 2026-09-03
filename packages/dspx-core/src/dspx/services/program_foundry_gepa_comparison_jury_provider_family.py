"""Task-local provider families for foundry-only dspy-lm-auth jury calls."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

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

    def requested_route(self, model: str) -> str:
        return self.requested_route_template.format(model=model)

    def resolved_route(self, model: str) -> str:
        return self.resolved_route_template.format(model=model)

    def model_allowed(self, model: object) -> bool:
        return isinstance(model, str) and self.model_re.fullmatch(model) is not None

    def reasoning_effort_allowed(self, value: object) -> bool:
        if self.allowed_reasoning_efforts is None:
            return value is None
        return isinstance(value, str) and value in self.allowed_reasoning_efforts

    def resolve_model(self, model: str | None) -> str:
        return self.default_model if model is None else model

    def resolve_reasoning_effort(self, value: str | None) -> str | None:
        return self.default_reasoning_effort if value is None else value

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
        return common | keys


CODEX_ENDPOINT_ORIGIN = "https://chatgpt.com/backend-api/codex"
COPILOT_ENDPOINT_ORIGIN = "https://api.individual.githubcopilot.com"

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

COPILOT_FAMILY = FoundryJuryProviderFamily(
    provider_name="foundry-dspy-lm-auth-github-copilot",
    auth_provider="github-copilot",
    model_re=re.compile(r"^gemini-[a-z0-9][a-z0-9.-]{0,63}$"),
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
    contract_module="dspy_lm_auth.copilot_backend_contract",
    message_class="CopilotBackendMessage",
    request_class="CopilotBackendRequest",
    response_class="CopilotBackendResponse",
    allowed_roles=frozenset({"system", "user", "assistant"}),
    model_key="model",
    strict_observed_model=False,
)

FAMILIES: Mapping[str, FoundryJuryProviderFamily] = {
    CODEX_FAMILY.provider_name: CODEX_FAMILY,
    COPILOT_FAMILY.provider_name: COPILOT_FAMILY,
}
TASK_LOCAL_PROVIDER_NAMES = frozenset(FAMILIES)


def family_for_provider(provider: object) -> FoundryJuryProviderFamily | None:
    """Return the task-local family for a provider name, or None when generic."""

    if not isinstance(provider, str):
        return None
    return FAMILIES.get(provider)


__all__ = [
    "CODEX_FAMILY",
    "COPILOT_FAMILY",
    "CREDENTIAL_MODE",
    "DEFAULT_TIMEOUT_SECONDS",
    "ENDPOINT_ORIGIN_DOMAIN",
    "FAMILIES",
    "IMPLEMENTATION_TASK_ID",
    "TASK_LOCAL_PROVIDER_NAMES",
    "FoundryJuryProviderFamily",
    "endpoint_origin_sha256",
    "family_for_provider",
]
