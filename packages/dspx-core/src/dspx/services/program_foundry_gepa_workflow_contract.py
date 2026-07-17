# summary: "Defines integrated foundry GEPA continuation status and non-authority projections."
# read_when:
#   - "Changing integrated foundry continuation statuses, stage summaries, or authority labels."

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.redaction import sanitize_diagnostic_text

PROGRAM_FOUNDRY_GEPA_WORKFLOW_SCHEMA = "program-foundry-gepa-workflow-v1"


class ProgramFoundryGepaWorkflowError(ValueError):
    """Raised when integrated continuation inputs or canonical state are invalid."""


def stage_projection(
    payload: Mapping[str, Any],
    *,
    artifact_path: Path | None = None,
) -> dict[str, Any]:
    projection = {
        "status": payload.get("status"),
        "disposition": payload.get("disposition"),
        "effect_disposition": payload.get("effect_disposition"),
        "reused": payload.get("reused"),
    }
    if artifact_path is not None:
        projection["path"] = str(artifact_path)
    for key in ("proposal_id", "request_id", "jury_status", "comparison_status"):
        if payload.get(key) is not None:
            projection[key] = payload[key]
    return {key: value for key, value in projection.items() if value is not None}


def workflow_result(
    *,
    root: Path,
    proposal_path: Path,
    proposal_id: str,
    status: str,
    disposition: str,
    stages: Mapping[str, Any],
    blocked_stage: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": PROGRAM_FOUNDRY_GEPA_WORKFLOW_SCHEMA,
        "status": status,
        "disposition": disposition,
        "proposal_id": proposal_id,
        "proposal_path": str(proposal_path),
        "foundry_root": str(root),
        "stages": dict(stages),
        "effect": {
            "gepa_invoked_or_reused": "gepa_execution" in stages,
            "candidate_materialized_or_reused": "candidate_consumption" in stages,
            "jury_provider_calls_invoked_or_reused": "comparison_jury" in stages,
            "external_adjudicator_invoked": False,
            "production_activation_applied": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
            "ak_called": False,
        },
        "non_authority": {
            "workflow_projection_only": True,
            "review_declaration_authenticated": False,
            "identity_authenticated_by_dspx": False,
            "winner_selection_authority": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
            "external_apply_authority": False,
        },
    }
    if blocked_stage is not None:
        payload["blocked_stage"] = blocked_stage
    if detail is not None:
        payload["detail"] = sanitize_diagnostic_text(detail, limit=1_000)
    return payload


def blocked_result(
    *,
    root: Path,
    proposal_path: Path,
    proposal_id: str,
    stages: Mapping[str, Any],
    blocked_stage: str,
    detail: str,
) -> dict[str, Any]:
    return workflow_result(
        root=root,
        proposal_path=proposal_path,
        proposal_id=proposal_id,
        status="blocked_indeterminate",
        disposition="indeterminate_no_replay",
        stages=stages,
        blocked_stage=blocked_stage,
        detail=detail,
    )
