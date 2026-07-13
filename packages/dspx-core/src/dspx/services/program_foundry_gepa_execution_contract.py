# summary: "Validates reviewed foundry GEPA proposals, declarations, and bound source evidence."
# read_when:
#   - "Changing foundry GEPA execution consent, proposal eligibility, or source revalidation."

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_evidence_closure import snapshot_candidate_artifact_closure
from dspx.services.program_foundry_gepa_proposal import (
    PROGRAM_FOUNDRY_GEPA_PROPOSAL_SCHEMA,
    validate_oracle_semantic_recommendation,
)
from dspx.services.program_foundry_gepa_proposal_io import (
    read_regular_bytes,
    sha256_regular_file,
)
from dspx.services.program_quality_contract import validate_quality_proposal
from dspx.services.program_oracle_secret_policy import (
    ProgramOracleSecretPolicyError,
    validate_publisher_assertion_no_secret,
)
from dspx.services.run_replay_service import check_run_receipt

_SUPPORTED_METRICS = {"exact", "contains", "f1"}


class ProgramFoundryGepaExecutionError(ValueError):
    """Raised when reviewed GEPA execution cannot proceed safely."""


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProgramFoundryGepaExecutionError(
            f"foundry GEPA execution value must be canonical JSON: {exc}"
        ) from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def load_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    raw = read_regular_bytes(path, label=label)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramFoundryGepaExecutionError(f"{label} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ProgramFoundryGepaExecutionError(f"{label} must contain one JSON object")
    return (
        {str(key): item for key, item in value.items()},
        sha256_bytes(raw),
    )


def validate_review_declaration(
    *, proposal_id: str, declared_reviewed: str, operator_label: str
) -> dict[str, Any]:
    if declared_reviewed != proposal_id:
        raise ProgramFoundryGepaExecutionError(
            "--declare-reviewed must exactly equal the proposal_id"
        )
    label = operator_label.strip()
    if not label or len(label.encode("utf-8")) > 200:
        raise ProgramFoundryGepaExecutionError(
            "--operator-label must contain 1 through 200 UTF-8 bytes"
        )
    try:
        validate_publisher_assertion_no_secret(label)
    except ProgramOracleSecretPolicyError as exc:
        raise ProgramFoundryGepaExecutionError(
            f"--operator-label contains secret-shaped material: {exc}"
        ) from exc
    declaration = (
        f"I reviewed DSPx foundry GEPA proposal {proposal_id} and request one "
        "bounded local GEPA experiment execution. I understand this is an "
        "unauthenticated statement of operator intent and grants no winner-selection, "
        "promotion, activation, governance, or external authority."
    )
    return {
        "schema_version": "dspx-foundry-gepa-review-declaration-v1",
        "kind": "operator_self_declaration",
        "proposal_id": proposal_id,
        "declaration": declaration,
        "operator_label": label,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "authenticated": False,
        "identity_verified": False,
        "approval_authority_asserted": False,
        "execution_intent_only": True,
    }


def _require_hash(path: Path, expected: object, *, label: str) -> None:
    if sha256_regular_file(path, label=label) != expected:
        raise ProgramFoundryGepaExecutionError(f"{label} drifted from the proposal")


def _closure_hash(manifest_path: Path) -> str:
    closure = snapshot_candidate_artifact_closure(manifest_path)
    return sha256_bytes(
        canonical_json(
            [
                {"kind": item.kind, "path": str(item.path), "sha256": item.sha256}
                for item in closure.artifacts
            ]
        ).encode("utf-8")
    )


def validate_execution_proposal(
    *,
    proposal_path: Path,
    proposal_sha256: str,
    payload: Mapping[str, Any],
    root: Path,
) -> dict[str, Any]:
    proposal_id = str(payload.get("proposal_id") or "")
    body = {str(key): item for key, item in payload.items() if key != "proposal_id"}
    if (
        payload.get("schema_version") != PROGRAM_FOUNDRY_GEPA_PROPOSAL_SCHEMA
        or payload.get("status") != "proposal_ready_for_review"
        or payload.get("authority") != "local_advisory_experiment_proposal_only"
        or len(proposal_id) != 64
        or sha256_bytes(canonical_json(body).encode("utf-8")) != proposal_id
    ):
        raise ProgramFoundryGepaExecutionError(
            "foundry GEPA proposal identity is invalid"
        )
    if proposal_path != root / "gepa_experiment_proposal.json":
        raise ProgramFoundryGepaExecutionError(
            "GEPA proposal must be the canonical sidecar in its foundry root"
        )
    effect = mapping(payload.get("effect"))
    non_authority = mapping(payload.get("non_authority"))
    if (
        effect.get("gepa_invoked") is not False
        or effect.get("gepa_model_calls_made") is not False
        or effect.get("candidate_mutated") is not False
        or effect.get("external_authority_mutated") is not False
        or non_authority.get("may_invoke_gepa") is not False
        or non_authority.get("execution_authority") is not False
        or non_authority.get("winner_selection") is not False
        or non_authority.get("promotion_authority") is not False
        or non_authority.get("activation_authority") is not False
        or non_authority.get("governance_authority") is not False
    ):
        raise ProgramFoundryGepaExecutionError(
            "foundry GEPA proposal effect or authority boundary is invalid"
        )

    candidate = mapping(payload.get("candidate_binding"))
    accepted = mapping(candidate.get("accepted_binding"))
    semantic = mapping(payload.get("semantic_binding"))
    runtime = mapping(payload.get("runtime_binding"))
    plan = mapping(payload.get("gepa_plan"))
    manifest = root / "candidate" / "manifest.json"
    receipt = root / "candidate" / "manifest.json.meta.json"
    _require_hash(
        manifest, candidate.get("manifest_sha256"), label="candidate manifest"
    )
    _require_hash(receipt, candidate.get("receipt_sha256"), label="candidate receipt")
    if check_run_receipt(receipt).get("status") != "ok":
        raise ProgramFoundryGepaExecutionError("candidate receipt is not reusable")
    if _closure_hash(manifest) != candidate.get("closure_sha256"):
        raise ProgramFoundryGepaExecutionError("candidate artifact closure drifted")
    accepted_path = (
        Path(str(accepted.get("quality_proposal_path") or "")).expanduser().absolute()
    )
    quality_payload, quality_sha256 = load_json(
        accepted_path,
        label="accepted quality proposal",
    )
    if quality_sha256 != accepted.get("quality_proposal_sha256"):
        raise ProgramFoundryGepaExecutionError(
            "accepted quality proposal drifted from the proposal"
        )
    try:
        validate_quality_proposal(
            quality_payload,
            allowed_statuses={"accepted_for_program_generation"},
        )
    except Exception as exc:
        raise ProgramFoundryGepaExecutionError(
            f"accepted quality proposal contract is invalid: {exc}"
        ) from exc
    semantic_path = root / "runtime" / "program_oracle_semantic.json"
    semantic_payload, semantic_sha256 = load_json(
        semantic_path,
        label="Oracle semantic sidecar",
    )
    if semantic_sha256 != semantic.get("sha256"):
        raise ProgramFoundryGepaExecutionError(
            "Oracle semantic sidecar drifted from the proposal"
        )
    selection = mapping(payload.get("selection"))
    index = selection.get("recommended_experiment_index")
    if isinstance(index, bool) or not isinstance(index, int):
        raise ProgramFoundryGepaExecutionError("GEPA recommendation index is invalid")
    try:
        _, analysis, recommendation = validate_oracle_semantic_recommendation(
            semantic_payload,
            recommendation_index=index,
        )
    except Exception as exc:
        raise ProgramFoundryGepaExecutionError(
            f"Oracle semantic recommendation contract is invalid: {exc}"
        ) from exc
    if (
        recommendation != selection.get("recommended_experiment_text")
        or sha256_bytes(recommendation.encode("utf-8"))
        != selection.get("recommended_experiment_sha256")
        or sha256_bytes(canonical_json(analysis.to_dict()).encode("utf-8"))
        != semantic.get("analysis_sha256")
    ):
        raise ProgramFoundryGepaExecutionError(
            "Oracle semantic recommendation binding drifted"
        )
    source_binding = mapping(semantic.get("source_binding"))
    expected_runtime_paths = {
        "runtime_episode": root / "runtime" / "runtime_episode.json",
        "behavior_results": root / "runtime" / "behavior_results.json",
        "oracle_evidence": root / "runtime" / "oracle_evidence.json",
        "runtime_receipt": root / "runtime" / "runtime_episode.json.meta.json",
    }
    if set(source_binding) != set(expected_runtime_paths):
        raise ProgramFoundryGepaExecutionError("semantic source binding set drifted")
    for name, path in expected_runtime_paths.items():
        bound = mapping(source_binding.get(name))
        if bound.get("path") != str(path):
            raise ProgramFoundryGepaExecutionError(f"semantic {name} path drifted")
        _require_hash(path, bound.get("sha256"), label=f"semantic {name}")
    if (
        check_run_receipt(expected_runtime_paths["runtime_receipt"]).get("status")
        != "ok"
    ):
        raise ProgramFoundryGepaExecutionError("runtime receipt is not reusable")
    if runtime.get("runtime_episode_sha256") != source_binding["runtime_episode"].get(
        "sha256"
    ):
        raise ProgramFoundryGepaExecutionError("runtime episode binding drifted")
    if runtime.get("runtime_receipt_sha256") != source_binding["runtime_receipt"].get(
        "sha256"
    ):
        raise ProgramFoundryGepaExecutionError("runtime receipt binding drifted")

    metric = mapping(plan.get("metric"))
    optimizer_metric = metric.get("optimizer_metric")
    max_metric_calls = plan.get("max_metric_calls")
    output_dir = root / "gepa-experiment" / "optimizer-output"
    result_path = root / "gepa-experiment" / "gepa-result.json"
    if (
        plan.get("kind") != "program_refinement_gepa"
        or plan.get("manifest_path") != str(manifest)
        or plan.get("seed") != 0
        or optimizer_metric not in _SUPPORTED_METRICS
        or metric.get("operator_metric_required") is not False
        or isinstance(max_metric_calls, bool)
        or not isinstance(max_metric_calls, int)
        or not 1 <= max_metric_calls <= 20
        or plan.get("proposed_output_dir") != str(output_dir)
        or plan.get("proposed_result_path") != str(result_path)
        or plan.get("execution_requires_explicit_operator_review") is not True
    ):
        raise ProgramFoundryGepaExecutionError(
            "GEPA proposal plan is not executable under the bounded executor"
        )
    return {
        "proposal_id": proposal_id,
        "proposal_sha256": proposal_sha256,
        "manifest_path": manifest,
        "source_manifest_sha256": candidate.get("manifest_sha256"),
        "output_dir": output_dir,
        "result_path": result_path,
        "optimizer_metric": optimizer_metric,
        "max_metric_calls": max_metric_calls,
    }
