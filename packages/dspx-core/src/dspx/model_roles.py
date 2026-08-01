# summary: "Defines explicit Codex subscription model roles for the autonomous DSPx foundry."
# read_when:
#   - "Changing intent/quality conversation or Oracle semantic model selection."
#   - "Changing role-specific Codex reasoning effort, auth routing, or evidence labels."

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from dspx.dspy_lm_auth_lm import DspyLMAuthLM

CODEX_REASONING_EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh", "max"})


@dataclass(frozen=True)
class ModelRole:
    """One explicit LM role whose runtime identity must remain observable."""

    name: str
    model: str
    reasoning_effort: str
    purpose: str

    def __post_init__(self) -> None:
        if not self.model.startswith("codex/"):
            raise ValueError(f"model role {self.name!r} must use the codex/ route")
        if self.reasoning_effort not in CODEX_REASONING_EFFORTS:
            allowed = ", ".join(sorted(CODEX_REASONING_EFFORTS))
            raise ValueError(
                f"model role {self.name!r} reasoning effort must be one of "
                f"{allowed}; got {self.reasoning_effort!r}"
            )

    def evidence_descriptor(self) -> dict[str, str | bool]:
        return {
            "schema_version": "dspx-model-role-declaration-v1",
            "status": "declared_not_live_verified",
            "live_verified": False,
            "role": self.name,
            "provider": "dspy-lm-auth",
            "auth_route": "codex_subscription",
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
) -> DspyLMAuthLM:
    """Create a lazy authenticated DSPy LM from one resolved role snapshot."""

    env = os.environ if environ is None else environ
    role = resolved_role or resolve_model_role(name, environ=env)
    if role.name != name:
        raise ValueError(
            f"resolved model role {role.name!r} does not match requested role {name!r}"
        )
    auth_storage = str(env.get("DSPX_LM_AUTH_STORAGE", "~/.pi/agent/auth.json")).strip()
    return DspyLMAuthLM(
        model=role.model,
        auth_provider="codex",
        auth_storage=auth_storage or None,
        timeout=timeout,
        strict=True,
        kwargs={"reasoning_effort": role.reasoning_effort},
    )
