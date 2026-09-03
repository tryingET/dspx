# summary: "Defines explicit model roles (codex/ declarations, local/ loopback ids) for the autonomous DSPx foundry."
# read_when:
#   - "Changing intent/quality conversation or Oracle semantic model selection."
#   - "Changing role-specific reasoning effort, provider routing, or evidence labels."

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from dspx.provider_registry import UnsupportedProviderError

CODEX_REASONING_EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh", "max"})
# Route prefixes a role model id may use. ``codex/`` is the declared (not live)
# subscription route; ``local/`` is a loopback OpenAI-compatible model id served
# through the typed ``openai-compatible`` provider port.
CODEX_ROUTE_PREFIX = "codex/"
LOCAL_ROUTE_PREFIX = "local/"
MODEL_ROUTE_PREFIXES = (CODEX_ROUTE_PREFIX, LOCAL_ROUTE_PREFIX)


@dataclass(frozen=True)
class ModelRole:
    """One explicit LM role whose runtime identity must remain observable."""

    name: str
    model: str
    reasoning_effort: str
    purpose: str

    def __post_init__(self) -> None:
        if not self.model.startswith(MODEL_ROUTE_PREFIXES) or len(self.model) <= len(
            self.route_prefix
        ):
            allowed = " or ".join(MODEL_ROUTE_PREFIXES)
            raise ValueError(f"model role {self.name!r} must use the {allowed} route")
        if self.reasoning_effort not in CODEX_REASONING_EFFORTS:
            allowed = ", ".join(sorted(CODEX_REASONING_EFFORTS))
            raise ValueError(
                f"model role {self.name!r} reasoning effort must be one of "
                f"{allowed}; got {self.reasoning_effort!r}"
            )

    @property
    def route_prefix(self) -> str:
        for prefix in MODEL_ROUTE_PREFIXES:
            if self.model.startswith(prefix):
                return prefix
        return ""

    @property
    def is_local_route(self) -> bool:
        return self.route_prefix == LOCAL_ROUTE_PREFIX

    def evidence_descriptor(self) -> dict[str, str | bool]:
        # ``local/`` ids run through the typed openai-compatible loopback port;
        # they never claim the removed ``dspy-lm-auth`` provider or a Codex auth route.
        if self.is_local_route:
            provider = "openai-compatible"
            auth_route = "loopback_credential_free"
        else:
            provider = "dspy-lm-auth"
            auth_route = "codex_subscription"
        return {
            "schema_version": "dspx-model-role-declaration-v1",
            "status": "declared_not_live_verified",
            "live_verified": False,
            "role": self.name,
            "provider": provider,
            "auth_route": auth_route,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "purpose": self.purpose,
        }


QUALITY_CRITERIA_ROLE = ModelRole(
    name="quality_criteria",
    model="codex/gpt-5.6-sol",
    reasoning_effort="high",
    purpose="propose and refine measurable quality criteria from user intent",
)

ORACLE_SEMANTIC_ROLE = ModelRole(
    name="oracle_semantic",
    model="codex/gpt-5.6-sol",
    reasoning_effort="max",
    purpose="interpret receipt-bound behavioral evidence and shape bounded exploration",
)

_ROLE_DEFAULTS = {
    QUALITY_CRITERIA_ROLE.name: QUALITY_CRITERIA_ROLE,
    ORACLE_SEMANTIC_ROLE.name: ORACLE_SEMANTIC_ROLE,
}

_ROLE_ENV_PREFIXES = {
    QUALITY_CRITERIA_ROLE.name: "DSPX_QUALITY_CRITERIA",
    ORACLE_SEMANTIC_ROLE.name: "DSPX_ORACLE_SEMANTIC",
}


def resolve_model_role(
    name: str, *, environ: Mapping[str, str] | None = None
) -> ModelRole:
    """Resolve a role with explicit environment overrides and validated effort."""

    try:
        default = _ROLE_DEFAULTS[name]
        prefix = _ROLE_ENV_PREFIXES[name]
    except KeyError as exc:
        raise ValueError(f"unknown DSPx model role: {name!r}") from exc
    env = os.environ if environ is None else environ
    return ModelRole(
        name=default.name,
        model=str(env.get(f"{prefix}_MODEL", default.model)).strip(),
        reasoning_effort=str(
            env.get(f"{prefix}_REASONING_EFFORT", default.reasoning_effort)
        )
        .strip()
        .lower(),
        purpose=default.purpose,
    )


def create_role_lm(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
    timeout: float | None = 60.0,
    resolved_role: ModelRole | None = None,
) -> None:
    """Reject the removed authenticated role provider before any effect."""

    env = os.environ if environ is None else environ
    role = resolved_role or resolve_model_role(name, environ=env)
    if role.name != name:
        raise ValueError(
            f"resolved model role {role.name!r} does not match requested role {name!r}"
        )
    del timeout
    raise UnsupportedProviderError(
        "provider 'dspy-lm-auth' is unsupported after the typed hard cutover"
    )
