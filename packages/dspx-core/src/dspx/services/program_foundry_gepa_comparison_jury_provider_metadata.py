"""Task-local provider metadata projection and retained validation per family."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dspx.services.program_foundry_gepa_comparison_jury_owner import (
    OWNER_COMMIT,
    OWNER_TREE,
    OWNER_VERSION,
    expected_foundry_jury_dependency_identity,
    expected_foundry_jury_source_identity,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
    FoundryJuryProviderConfigurationError,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (
    CODEX_FAMILY,
    CREDENTIAL_MODE,
    FoundryJuryProviderFamily,
)
from dspx.services.soomfon_provider_outcome_receipt_contract import (
    canonical_json,
    sha256,
)


def provider_metadata(
    *,
    family: FoundryJuryProviderFamily,
    model: str,
    reasoning_effort: str | None,
    timeout_seconds: float,
    execution_task_id: int,
    execution_claimant: str,
    source_identity: Mapping[str, Any],
    dependency_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Project the closed configured-provider metadata for one family."""

    metadata: dict[str, Any] = {
        "status": "configured",
        "provider": family.provider_name,
        "model": model,
        "requested_route": family.requested_route(model),
        "resolved_route": family.resolved_route(model),
        "auth_provider": family.auth_provider,
        "credential_mode": CREDENTIAL_MODE,
        "reasoning_effort": reasoning_effort,
        "num_retries": 0,
        "cache": False,
        "timeout_seconds": timeout_seconds,
        "sync_only": True,
        "fallback_allowed": False,
        "health_probe_allowed": False,
        "execution_task_id": execution_task_id,
        "execution_claimant": execution_claimant,
        "owner_commit": OWNER_COMMIT,
        "owner_tree": OWNER_TREE,
        "owner_version": OWNER_VERSION,
        "source_identity_sha256": sha256(canonical_json(source_identity)),
        "dependency_identity_sha256": sha256(canonical_json(dependency_identity)),
    }
    if family.endpoint_resolved:
        # Fixed families keep their historical metadata shape; env-resolved
        # families bind the exact base URL and its origin hash per run.
        metadata["endpoint_origin"] = family.endpoint_origin
        metadata["endpoint_origin_sha256"] = family.endpoint_origin_sha256
    return metadata


def validate_foundry_jury_provider_metadata(
    value: Mapping[str, Any],
    *,
    execution_task_id: int,
    execution_claimant: str,
    model: str,
    reasoning_effort: str | None,
    family: FoundryJuryProviderFamily = CODEX_FAMILY,
) -> dict[str, Any]:
    expected = provider_metadata(
        family=family,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=family.default_timeout_seconds,
        execution_task_id=execution_task_id,
        execution_claimant=execution_claimant,
        source_identity=expected_foundry_jury_source_identity(),
        dependency_identity=expected_foundry_jury_dependency_identity(),
    )
    if dict(value) != expected:
        raise FoundryJuryProviderConfigurationError(
            "task-local provider metadata drifted"
        )
    return expected


__all__ = [
    "FoundryJuryProviderConfigurationError",
    "provider_metadata",
    "validate_foundry_jury_provider_metadata",
]
