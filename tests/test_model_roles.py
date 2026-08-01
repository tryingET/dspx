# summary: "Tests explicit Codex subscription roles for quality conversation and Oracle semantics."

from __future__ import annotations

import pytest
from dspx.model_roles import (
    ORACLE_SEMANTIC_ROLE,
    QUALITY_CRITERIA_ROLE,
    create_role_lm,
    resolve_model_role,
)


def test_quality_criteria_role_uses_sol_high() -> None:
    assert QUALITY_CRITERIA_ROLE.evidence_descriptor() == {
        "schema_version": "dspx-model-role-declaration-v1",
        "status": "declared_not_live_verified",
        "live_verified": False,
        "role": "quality_criteria",
        "provider": "dspy-lm-auth",
        "auth_route": "codex_subscription",
        "model": "codex/gpt-5.6-sol",
        "reasoning_effort": "high",
        "purpose": "propose and refine measurable quality criteria from user intent",
    }


def test_oracle_semantic_role_uses_observed_sol_route_with_max_effort() -> None:
    assert ORACLE_SEMANTIC_ROLE.evidence_descriptor() == {
        "schema_version": "dspx-model-role-declaration-v1",
        "status": "declared_not_live_verified",
        "live_verified": False,
        "role": "oracle_semantic",
        "provider": "dspy-lm-auth",
        "auth_route": "codex_subscription",
        "model": "codex/gpt-5.6-sol",
        "reasoning_effort": "max",
        "purpose": "interpret receipt-bound behavioral evidence and shape bounded exploration",
    }


def test_role_overrides_remain_explicit_and_validated() -> None:
    role = resolve_model_role(
        "oracle_semantic",
        environ={
            "DSPX_ORACLE_SEMANTIC_MODEL": "codex/gpt-5.6-sol-preview",
            "DSPX_ORACLE_SEMANTIC_REASONING_EFFORT": "xhigh",
        },
    )

    assert role.model == "codex/gpt-5.6-sol-preview"
    assert role.reasoning_effort == "xhigh"


def test_role_rejects_non_codex_route() -> None:
    with pytest.raises(ValueError, match="must use the codex/ route"):
        resolve_model_role(
            "quality_criteria",
            environ={"DSPX_QUALITY_CRITERIA_MODEL": "openai/gpt-5.6-sol"},
        )


def test_role_rejects_unknown_reasoning_effort() -> None:
    with pytest.raises(ValueError, match="reasoning effort must be one of"):
        resolve_model_role(
            "oracle_semantic",
            environ={"DSPX_ORACLE_SEMANTIC_REASONING_EFFORT": "unbounded"},
        )


def test_create_role_lm_preserves_route_model_effort_and_redacted_auth() -> None:
    lm = create_role_lm(
        "oracle_semantic",
        environ={"DSPX_LM_AUTH_STORAGE": "/private/auth.json"},
        timeout=90.0,
    )

    assert lm.requested_model == "codex/gpt-5.6-sol"
    assert lm.auth_provider == "codex"
    assert lm.auth_storage == "/private/auth.json"
    assert lm.timeout == 90.0
    assert lm.kwargs == {"reasoning_effort": "max"}
    assert lm.runtime_metadata()["auth_storage"] == "[REDACTED]"


def test_create_role_lm_uses_one_pre_resolved_role_snapshot() -> None:
    role = resolve_model_role(
        "oracle_semantic",
        environ={
            "DSPX_ORACLE_SEMANTIC_MODEL": "codex/gpt-5.6-sol",
            "DSPX_ORACLE_SEMANTIC_REASONING_EFFORT": "xhigh",
        },
    )

    lm = create_role_lm(
        "oracle_semantic",
        environ={
            "DSPX_ORACLE_SEMANTIC_MODEL": "codex/gpt-5.5",
            "DSPX_ORACLE_SEMANTIC_REASONING_EFFORT": "low",
        },
        resolved_role=role,
    )

    assert lm.requested_model == "codex/gpt-5.6-sol"
    assert lm.kwargs == {"reasoning_effort": "xhigh"}
