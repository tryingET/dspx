from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import sha256_text
from dspx.services.program_architecture import ProgramArchitectureError, _non_authority
from dspx.services.program_architecture_tournament import (
    PROGRAM_ARCHITECTURE_TOURNAMENT_EVIDENCE_MATRIX_SCHEMA,
    PROGRAM_ARCHITECTURE_TOURNAMENT_SCHEMA,
)

PROGRAM_ARCHITECTURE_RECOMMENDATION_SCHEMA = "program-architecture-recommendation-v1"
_FORBIDDEN_OUTPUT_NAMES = {
    "manifest.json",
    "manifest.json.meta.json",
    "plan.json",
    "program.py",
    "module.py",
    "signature.py",
    "module_surfaces.json",
    "execution_episode.json",
    "oracle_evidence.json",
    "behavior_results.json",
    "tournament.json",
}
_AUTHORITY_FALSE_EFFECT_FLAGS = (
    "winner_selected",
    "promotion_applied",
    "ak_called",
    "governance_mutated",
    "external_authority_mutated",
    "shared_oracle_mutated",
)
_AUTHORITY_FALSE_NON_AUTHORITY_FLAGS = (
    "winner_selection",
    "ranking_authority",
    "promotion_authority",
    "activation_authority",
    "oracle_authority",
    "governance_authority",
    "external_mutation",
    "canonical_mutation",
)


class ProgramArchitectureRecommendationError(ProgramArchitectureError):
    """Raised when architecture recommendation cannot be built safely."""


def _json_text(payload: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProgramArchitectureRecommendationError(
            f"failed to read JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramArchitectureRecommendationError(
            "architecture recommendation input must be a JSON object"
        )
    return payload


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip()) if value.strip() else 0
        except ValueError:
            return 0
    return 0


def _safe_output_path(path: Path) -> Path:
    target = path.expanduser().resolve()
    if target.name in _FORBIDDEN_OUTPUT_NAMES:
        raise ProgramArchitectureRecommendationError(
            f"refusing to write architecture recommendation to generated/tournament artifact path: {target.name}"
        )
    if target.exists() and target.is_dir():
        raise ProgramArchitectureRecommendationError(
            f"architecture recommendation output path is a directory: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _validate_tournament(tournament: Mapping[str, Any]) -> None:
    if tournament.get("schema_version") != PROGRAM_ARCHITECTURE_TOURNAMENT_SCHEMA:
        raise ProgramArchitectureRecommendationError(
            "tournament schema_version must be program-architecture-tournament-v1"
        )
    matrix = _mapping(tournament.get("evidence_matrix"))
    if (
        matrix.get("schema_version")
        != PROGRAM_ARCHITECTURE_TOURNAMENT_EVIDENCE_MATRIX_SCHEMA
    ):
        raise ProgramArchitectureRecommendationError(
            "tournament evidence_matrix schema_version must be program-architecture-tournament-evidence-matrix-v1"
        )
    effect = _mapping(tournament.get("effect"))
    widened_effect = [
        key for key in _AUTHORITY_FALSE_EFFECT_FLAGS if effect.get(key) is not False
    ]
    if widened_effect:
        raise ProgramArchitectureRecommendationError(
            "tournament effect widens authority: " + ", ".join(widened_effect)
        )
    non_authority = _mapping(tournament.get("non_authority"))
    widened_non_authority = [
        key
        for key in _AUTHORITY_FALSE_NON_AUTHORITY_FLAGS
        if key in non_authority and non_authority.get(key) is not False
    ]
    if widened_non_authority:
        raise ProgramArchitectureRecommendationError(
            "tournament non_authority widens authority: "
            + ", ".join(widened_non_authority)
        )


def _candidate_advisory(row: Mapping[str, Any]) -> dict[str, Any]:
    candidate_id = str(row.get("candidate_id") or "unknown")
    if row.get("status") == "skipped":
        return {
            "candidate_id": candidate_id,
            "advisory": "not_materialized",
            "attention": "candidate was skipped or declared-only; inspect the tournament skip reason before trying to materialize it.",
            "evidence_basis": ["tournament skipped candidate record"],
            "non_authority": {"winner_selection": False, "promotion_authority": False},
        }
    replay_status = str(row.get("replay_status") or "unknown")
    behavior_summary = _mapping(row.get("behavior_summary"))
    behavior_sources = _mapping(row.get("behavior_sources"))
    oracle_readability = _mapping(row.get("oracle_readability"))
    checks = _mapping(row.get("checks"))
    total = _safe_int(behavior_summary.get("total"))
    failed = _safe_int(behavior_summary.get("failed"))
    errors = _safe_int(behavior_summary.get("error"))
    degraded = _safe_int(behavior_summary.get("degraded"))
    source_count = _safe_int(behavior_sources.get("source_count"))
    oracle_records = _safe_int(oracle_readability.get("candidate_local_report_records"))
    if replay_status != "ok":
        advisory = "needs_replay_attention"
        attention = "receipt replay is not ok; fix or rerun materialization before interpreting this candidate."
    elif total == 0 or source_count == 0:
        advisory = "needs_more_behavior_evidence"
        attention = "candidate replayed, but behavior evidence is sparse or absent; add examples/datasets before serious comparison."
    elif failed or errors or degraded:
        advisory = "needs_behavior_review"
        attention = "candidate has failed/error/degraded behavior counts; inspect generated behavior evidence before downstream review."
    else:
        advisory = "ready_for_human_review"
        attention = "candidate has replay-ok local evidence with no aggregate failure/error/degraded counts; inspect artifacts manually before any authority path."
    optional_actions: list[str] = []
    if oracle_records == 0:
        optional_actions.append(
            "Rerun tournament with --with-oracle-reports if behavioral interpretation is useful."
        )
    if checks.get("examples_binding") in {None, "not_applicable"}:
        optional_actions.append(
            "Add inline examples or examples_path for stronger behavior evidence."
        )
    return {
        "candidate_id": candidate_id,
        "label": row.get("label"),
        "family": row.get("family"),
        "plan_recommendation": row.get("plan_recommendation"),
        "advisory": advisory,
        "attention": attention,
        "optional_actions": optional_actions,
        "evidence_basis": [
            f"replay_status={replay_status}",
            f"behavior_total={total}",
            f"behavior_failed={failed}",
            f"behavior_error={errors}",
            f"behavior_degraded={degraded}",
            f"behavior_source_count={source_count}",
            f"candidate_local_oracle_records={oracle_records}",
        ],
        "non_authority": {"winner_selection": False, "promotion_authority": False},
    }


def _next_moves(
    *,
    tournament: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    advisories: list[Mapping[str, Any]],
) -> list[dict[str, str]]:
    moves: list[dict[str, str]] = []
    materialized = [row for row in rows if row.get("status") != "skipped"]
    replay_not_ok = [
        item for item in advisories if item.get("advisory") == "needs_replay_attention"
    ]
    sparse = [
        item
        for item in advisories
        if item.get("advisory") == "needs_more_behavior_evidence"
    ]
    behavior_attention = [
        item for item in advisories if item.get("advisory") == "needs_behavior_review"
    ]
    ready = [
        item for item in advisories if item.get("advisory") == "ready_for_human_review"
    ]
    skipped = [
        item for item in advisories if item.get("advisory") == "not_materialized"
    ]
    if not materialized:
        moves.append(
            {
                "move": "create_materializable_candidates",
                "reason": "No materialized candidates were present in the tournament evidence.",
            }
        )
    if replay_not_ok:
        moves.append(
            {
                "move": "fix_replay_before_interpretation",
                "reason": "At least one candidate does not have an ok replay check.",
            }
        )
    if sparse:
        moves.append(
            {
                "move": "add_examples_or_dataset_and_rerun_tournament",
                "reason": "At least one replay-ok candidate has sparse or absent behavior evidence.",
            }
        )
    if behavior_attention:
        moves.append(
            {
                "move": "inspect_behavior_failures_before_review",
                "reason": "At least one candidate has aggregate failed/error/degraded behavior counts.",
            }
        )
    oracle_enabled = bool(
        _mapping(tournament.get("effect")).get("oracle_index_mutated")
    )
    if materialized and not oracle_enabled:
        moves.append(
            {
                "move": "rerun_with_candidate_local_oracle_reports_if_interpretation_needed",
                "reason": "Tournament has materialized candidates but no candidate-local Oracle reports.",
            }
        )
    if skipped:
        moves.append(
            {
                "move": "revise_or_ignore_non_materializable_candidates",
                "reason": "At least one planned candidate was skipped or declared-only.",
            }
        )
    if ready and len(materialized) > 1:
        moves.append(
            {
                "move": "manual_side_by_side_review_or_explicit_adjudication",
                "reason": "Multiple candidates have usable local evidence; inspect them or run an explicit downstream review without treating this packet as winner selection.",
            }
        )
    if not moves:
        moves.append(
            {
                "move": "inspect_candidate_artifacts",
                "reason": "Tournament evidence is locally consistent; inspect artifacts before any authority-bearing path.",
            }
        )
    return moves


def _status(advisories: list[Mapping[str, Any]]) -> str:
    if not advisories:
        return "insufficient_tournament_evidence"
    kinds = {str(item.get("advisory")) for item in advisories}
    if kinds <= {"not_materialized"}:
        return "insufficient_tournament_evidence"
    if kinds & {"needs_replay_attention", "needs_behavior_review"}:
        return "needs_attention"
    return "advisory_ready"


def build_program_architecture_recommendation_from_tournament(
    tournament_path: Path,
) -> dict[str, Any]:
    source = tournament_path.expanduser().resolve()
    tournament = _load_json(source)
    _validate_tournament(tournament)
    matrix = _mapping(tournament.get("evidence_matrix"))
    raw_rows = matrix.get("rows")
    if not isinstance(raw_rows, list):
        raise ProgramArchitectureRecommendationError(
            "tournament evidence_matrix rows must be a list"
        )
    rows = [_mapping(row) for row in raw_rows]
    advisories = [_candidate_advisory(row) for row in rows]
    return {
        "schema_version": PROGRAM_ARCHITECTURE_RECOMMENDATION_SCHEMA,
        "status": _status(advisories),
        "created_from": {
            "tournament_path": str(source),
            "tournament_hash": _file_hash(source),
            "tournament_schema_version": tournament.get("schema_version"),
            "evidence_matrix_schema_version": matrix.get("schema_version"),
            "tournament_status": tournament.get("status"),
        },
        "candidate_advisories": advisories,
        "next_moves": _next_moves(
            tournament=tournament, rows=rows, advisories=advisories
        ),
        "limitations": [
            "This packet is advisory only and does not select a winning candidate.",
            "It summarizes aggregate tournament evidence; inspect candidate artifacts before any authority-bearing action.",
            "Oracle report presence is interpretation support only, not ranking, pruning, promotion, or governance authority.",
        ],
        "effect": {
            "recommendation_sidecar_written": False,
            "candidate_programs_materialized": False,
            "oracle_index_mutated": False,
            "shared_oracle_mutated": False,
            "ak_called": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
            "winner_selected": False,
            "promotion_applied": False,
        },
        "non_authority": {
            **_non_authority(),
            "advisory_only": True,
            "ranking_authority": False,
            "oracle_ranking": False,
        },
    }


def write_program_architecture_recommendation(
    payload: Mapping[str, Any], out: Path
) -> dict[str, Any]:
    target = _safe_output_path(out)
    payload_without_artifact = dict(payload)
    payload_without_artifact.pop("artifact", None)
    payload_without_artifact["effect"] = {
        **dict(payload_without_artifact.get("effect") or {}),
        "recommendation_sidecar_written": True,
    }
    payload_hash = sha256_text(_json_text(payload_without_artifact))
    updated = dict(payload_without_artifact)
    updated["artifact"] = {
        "path": str(target),
        "payload_hash_excluding_artifact": payload_hash,
        "schema_version": PROGRAM_ARCHITECTURE_RECOMMENDATION_SCHEMA,
    }
    target.write_text(_json_text(updated), encoding="utf-8")
    return updated
