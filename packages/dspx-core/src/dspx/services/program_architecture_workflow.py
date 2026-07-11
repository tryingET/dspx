# summary: "Orchestrates the local intent-normalization, architecture, tournament, and recommendation workflow."
# read_when:
#   - "Changing the guided program-architecture loop, its sidecars, or workflow boundaries."

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import sha256_text
from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_architecture import (
    build_program_architecture_candidates,
    write_program_architecture_candidates,
)
from dspx.services.program_architecture_recommendation import (
    build_program_architecture_recommendation_from_tournament,
    write_program_architecture_recommendation,
)
from dspx.services.program_architecture_tournament import (
    preflight_program_architecture_tournament,
    run_program_architecture_tournament_from_plan_path,
    write_program_architecture_tournament_result,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_intent_normalization import (
    ProgramIntentNormalizationError,
    normalize_program_intent_from_path,
    normalize_program_intent_from_prompt,
    normalize_program_intent_from_request_path,
    write_normalized_intent,
    write_program_intent_normalization,
)

PROGRAM_ARCHITECT_LOOP_SCHEMA = "program-architect-loop-v1"
_FORBIDDEN_OUTPUT_NAMES = set(PROTECTED_PROGRAM_ARTIFACT_NAMES)


class ProgramArchitectureWorkflowError(ProgramIntentNormalizationError):
    """Raised when the guided architecture loop cannot run safely."""


def _json_text(payload: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _safe_outdir(path: Path) -> Path:
    target = path.expanduser().resolve()
    if target.exists() and not target.is_dir():
        raise ProgramArchitectureWorkflowError(
            f"architecture loop outdir is a file: {target}"
        )
    if target.exists() and any(target.iterdir()):
        raise ProgramArchitectureWorkflowError(
            f"architecture loop outdir is not empty: {target}"
        )
    return target


def _safe_output_path(path: Path) -> Path:
    target = path.expanduser().resolve()
    if target.name in _FORBIDDEN_OUTPUT_NAMES:
        raise ProgramArchitectureWorkflowError(
            f"refusing to write architecture loop sidecar to generated candidate artifact path: {target.name}"
        )
    if target.exists() and target.is_dir():
        raise ProgramArchitectureWorkflowError(
            f"architecture loop output path is a directory: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _artifact(path: Path, *, schema_version: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(path.expanduser().resolve()),
        "exists": path.exists(),
    }
    if path.exists() and path.is_file():
        payload["content_hash"] = sha256_text(path.read_text(encoding="utf-8"))
    if schema_version is not None:
        payload["schema_version"] = schema_version
    return payload


def _non_authority() -> dict[str, bool]:
    return {
        "guided_architecture_loop_only": True,
        "advisory_only": True,
        "winner_selection": False,
        "ranking_authority": False,
        "promotion_authority": False,
        "activation_authority": False,
        "oracle_authority": False,
        "governance_authority": False,
        "canonical_mutation": False,
        "external_mutation": False,
    }


def _effect(
    *, with_oracle_reports: bool, materialized_count: int = 0
) -> dict[str, Any]:
    return {
        "normalization_sidecar_written": True,
        "normalized_intent_written": True,
        "architecture_plan_written": True,
        "candidate_intents_materialized": True,
        "candidate_programs_materialized": materialized_count > 0,
        "receipts_replay_checked": materialized_count > 0,
        "tournament_sidecar_written": True,
        "recommendation_sidecar_written": True,
        "workflow_summary_written": False,
        "oracle_index_mutated": bool(with_oracle_reports and materialized_count > 0),
        "oracle_index_scope": "candidate_local_explicit_paths"
        if with_oracle_reports and materialized_count > 0
        else "none",
        "shared_oracle_mutated": False,
        "ak_called": False,
        "governance_mutated": False,
        "external_authority_mutated": False,
        "winner_selected": False,
        "promotion_applied": False,
    }


def _validate_source(
    intent: Path | None, prompt: str | None, request: Path | None
) -> None:
    supplied = [intent is not None, prompt is not None, request is not None]
    if sum(1 for item in supplied if item) != 1:
        raise ProgramArchitectureWorkflowError(
            "supply exactly one of intent, prompt, or request"
        )


def run_program_architecture_loop(
    *,
    outdir: Path,
    intent: Path | None = None,
    prompt: str | None = None,
    request: Path | None = None,
    name: str | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    metric: str | None = None,
    candidate_ids: list[str] | None = None,
    with_oracle_reports: bool = False,
) -> dict[str, Any]:
    """Run normalize -> architecture plan -> tournament -> recommendation locally."""

    _validate_source(intent, prompt, request)
    root = _safe_outdir(outdir)
    normalization_path = root / "normalization.json"
    normalized_intent_path = root / "normalized_intent.json"
    architecture_plan_path = root / "architecture_plan.json"
    tournament_path = root / "tournament.json"
    recommendation_path = root / "architecture_recommendation.json"

    if intent is not None:
        normalization_payload = normalize_program_intent_from_path(intent)
    elif request is not None:
        normalization_payload = normalize_program_intent_from_request_path(
            request,
            name=name,
            inputs=inputs,
            outputs=outputs,
            metric=metric,
        )
    else:
        assert prompt is not None
        normalization_payload = normalize_program_intent_from_prompt(
            prompt,
            name=name,
            inputs=inputs,
            outputs=outputs,
            metric=metric,
        )
    normalized_intent = normalization_payload.get("normalized_intent")
    if not isinstance(normalized_intent, Mapping):
        raise ProgramArchitectureWorkflowError(
            "normalization payload missing normalized_intent"
        )
    plan_payload = build_program_architecture_candidates(
        ProgramIntent.model_validate(dict(normalized_intent))
    )
    preflight_program_architecture_tournament(
        architecture_plan=plan_payload,
        outdir=root / "tournament",
        candidate_ids=candidate_ids,
    )

    normalized_intent_artifact = write_normalized_intent(
        normalization_payload,
        normalized_intent_path,
    )
    normalization_payload = {
        **normalization_payload,
        "normalized_intent_artifact": normalized_intent_artifact,
        "effect": {
            **dict(normalization_payload.get("effect") or {}),
            "normalized_intent_written": True,
        },
    }
    normalization_written = write_program_intent_normalization(
        normalization_payload,
        normalization_path,
    )

    plan_written = write_program_architecture_candidates(
        plan_payload,
        architecture_plan_path,
    )

    tournament_payload = run_program_architecture_tournament_from_plan_path(
        architecture_plan_path,
        outdir=root / "tournament",
        candidate_ids=candidate_ids,
        candidate_local_oracle=with_oracle_reports,
    )
    tournament_written = write_program_architecture_tournament_result(
        tournament_payload,
        tournament_path,
    )

    recommendation_payload = build_program_architecture_recommendation_from_tournament(
        tournament_path
    )
    recommendation_written = write_program_architecture_recommendation(
        recommendation_payload,
        recommendation_path,
    )

    materialized_count = int(
        tournament_written.get("materialized_candidate_count") or 0
    )
    status = "ok"
    if recommendation_written.get("status") in {
        "needs_attention",
        "insufficient_tournament_evidence",
    }:
        status = "degraded"
    return {
        "schema_version": PROGRAM_ARCHITECT_LOOP_SCHEMA,
        "status": status,
        "steps": {
            "normalization": {
                "status": normalization_written.get("status"),
                "path": str(normalization_path),
                "normalized_intent_path": str(normalized_intent_path),
                "missing_evidence_count": len(
                    normalization_written.get("missing_evidence") or []
                ),
                "generation_risk_count": len(
                    normalization_written.get("generation_risks") or []
                ),
            },
            "architecture_plan": {
                "status": plan_written.get("status"),
                "path": str(architecture_plan_path),
                "candidate_count": plan_written.get("candidate_count"),
                "recommended_candidate_id": plan_written.get(
                    "recommended_candidate_id"
                ),
            },
            "tournament": {
                "status": tournament_written.get("status"),
                "path": str(tournament_path),
                "materialized_candidate_count": materialized_count,
                "candidate_count": tournament_written.get("candidate_count"),
            },
            "recommendation": {
                "status": recommendation_written.get("status"),
                "path": str(recommendation_path),
                "next_move_count": len(recommendation_written.get("next_moves") or []),
            },
        },
        "generated_sidecars": [
            _artifact(
                normalization_path, schema_version="program-intent-normalization-v1"
            ),
            _artifact(normalized_intent_path, schema_version="program-intent-v2"),
            _artifact(
                architecture_plan_path,
                schema_version="program-architecture-candidates-v1",
            ),
            _artifact(
                tournament_path, schema_version="program-architecture-tournament-v1"
            ),
            _artifact(
                recommendation_path,
                schema_version="program-architecture-recommendation-v1",
            ),
        ],
        "effect": _effect(
            with_oracle_reports=with_oracle_reports,
            materialized_count=materialized_count,
        ),
        "non_authority": _non_authority(),
    }


def write_program_architecture_loop_result(
    payload: Mapping[str, Any], out: Path
) -> dict[str, Any]:
    target = _safe_output_path(out)
    payload_without_artifact = dict(payload)
    payload_without_artifact.pop("artifact", None)
    payload_without_artifact["effect"] = {
        **dict(payload_without_artifact.get("effect") or {}),
        "workflow_summary_written": True,
    }
    payload_hash = sha256_text(_json_text(payload_without_artifact))
    updated = dict(payload_without_artifact)
    updated["artifact"] = {
        "path": str(target),
        "payload_hash_excluding_artifact": payload_hash,
        "schema_version": PROGRAM_ARCHITECT_LOOP_SCHEMA,
    }
    target.write_text(_json_text(updated), encoding="utf-8")
    return updated
