# summary: "Builds immutable, source-bound GEPA experiment proposals from successful foundry Oracle recommendations."
# read_when:
#   - "Changing Oracle-to-GEPA handoff, proposal bindings, bounded optimizer settings, or proposal authority."

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_evidence_closure import snapshot_candidate_artifact_closure
from dspx.services.program_foundry_gepa_proposal_io import (
    ProgramFoundryGepaProposalError,
    assert_path_descriptor_identity,
    read_root_relative_bytes,
    sha256_regular_file,
)
from dspx.services.program_oracle_semantic_contract import OracleSemanticAnalysis

PROGRAM_FOUNDRY_GEPA_PROPOSAL_SCHEMA = "dspx-program-foundry-gepa-proposal-v1"
_SUPPORTED_METRICS = {"exact_match", "exact", "contains", "f1"}


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProgramFoundryGepaProposalError(
            f"GEPA proposal value must be canonical JSON: {exc}"
        ) from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _validate_semantic_result(
    payload: Mapping[str, Any], *, recommendation_index: int
) -> tuple[dict[str, Any], OracleSemanticAnalysis, str]:
    if isinstance(recommendation_index, bool) or recommendation_index < 0:
        raise ProgramFoundryGepaProposalError(
            "GEPA recommendation index must be a non-negative integer"
        )
    effect = _mapping(payload.get("effect"))
    non_authority = _mapping(payload.get("non_authority"))
    result = _mapping(payload.get("semantic_result"))
    request_sha256 = str(payload.get("request_sha256") or "")
    if (
        payload.get("schema_version") != "program-runtime-oracle-semantic-v1"
        or payload.get("status") != "ok"
        or effect.get("effect_disposition") != "terminal_result_recorded"
        or non_authority.get("promotion_authority") is not False
        or non_authority.get("activation_authority") is not False
    ):
        raise ProgramFoundryGepaProposalError(
            "GEPA proposal requires terminal successful non-authoritative Oracle semantics"
        )
    if (
        result.get("schema_version") != "dspx-program-oracle-semantic-result-v1"
        or result.get("authority") != "local_empirical_advisory_only"
        or result.get("execution_status") not in {"succeeded", "replayed_fixture"}
        or len(request_sha256) != 64
        or any(character not in "0123456789abcdef" for character in request_sha256)
        or result.get("request_sha256") != request_sha256
        or effect.get("semantic_backend_invoked") is not True
        or effect.get("live_call_succeeded") != result.get("live_call_succeeded")
    ):
        raise ProgramFoundryGepaProposalError(
            "Oracle semantic result identity or execution contract is invalid for a GEPA proposal"
        )
    execution_status = result["execution_status"]
    if (
        not str(result.get("preferred_model") or "").strip()
        or result.get("error") is not None
    ):
        raise ProgramFoundryGepaProposalError(
            "Oracle semantic result model provenance or terminal status is invalid"
        )
    if execution_status == "succeeded":
        if (
            result.get("backend_kind") != "live"
            or result.get("live_call_succeeded") is not True
            or not str(result.get("configured_provider") or "").strip()
            or not str(result.get("configured_model") or "").strip()
            or not str(result.get("executed_provider") or "").strip()
            or not str(result.get("executed_model") or "").strip()
            or result.get("fixture_sha256") is not None
        ):
            raise ProgramFoundryGepaProposalError(
                "successful live Oracle provenance is incomplete for a GEPA proposal"
            )
    else:
        fixture_sha256 = str(result.get("fixture_sha256") or "")
        invalid_fixture = (
            result.get("backend_kind") != "fixture-replay"
            or result.get("live_call_succeeded") is not False
            or result.get("configured_provider") is not None
            or result.get("configured_model") is not None
            or result.get("executed_provider") is not None
            or result.get("executed_model") is not None
            or len(fixture_sha256) != 64
            or any(character not in "0123456789abcdef" for character in fixture_sha256)
        )
        if invalid_fixture:
            raise ProgramFoundryGepaProposalError(
                "fixture-replayed Oracle provenance is incomplete for a GEPA proposal"
            )
    analysis_payload = result.get("analysis")
    if not isinstance(analysis_payload, Mapping):
        raise ProgramFoundryGepaProposalError(
            "Oracle semantic result has no validated analysis for a GEPA proposal"
        )
    analysis = OracleSemanticAnalysis.from_mapping(analysis_payload)
    if recommendation_index >= len(analysis.recommended_experiments):
        raise ProgramFoundryGepaProposalError(
            "GEPA recommendation index is outside Oracle recommended_experiments"
        )
    return result, analysis, analysis.recommended_experiments[recommendation_index]


def _validate_semantic_sources(
    payload: Mapping[str, Any],
    *,
    runtime: Mapping[str, Any],
    root: Path,
    root_descriptor: int,
) -> dict[str, Any]:
    source_binding = _mapping(payload.get("source_binding"))
    artifact_hashes = _mapping(runtime.get("artifact_hashes"))
    expected = {
        # Exact-key validation prevents unbound semantic sources from being silently dropped.
        "runtime_episode": (
            root / "runtime" / "runtime_episode.json",
            runtime.get("runtime_episode_sha256"),
        ),
        "behavior_results": (
            root / "runtime" / "behavior_results.json",
            artifact_hashes.get("behavior_results_sha256"),
        ),
        "oracle_evidence": (
            root / "runtime" / "oracle_evidence.json",
            artifact_hashes.get("oracle_evidence_sha256"),
        ),
        "runtime_receipt": (
            root / "runtime" / "runtime_episode.json.meta.json",
            runtime.get("runtime_receipt_sha256"),
        ),
    }
    validated: dict[str, Any] = {}
    if set(source_binding) != set(expected):
        raise ProgramFoundryGepaProposalError(
            "Oracle semantic source binding must contain exactly the foundry runtime sources"
        )
    validated: dict[str, Any] = {}
    for name, (expected_path, expected_hash_value) in expected.items():
        declared = _mapping(source_binding.get(name))
        raw_path = str(declared.get("path") or "").strip()
        declared_hash = str(declared.get("sha256") or "")
        expected_hash = str(expected_hash_value or "")
        if raw_path != str(expected_path) or declared_hash != expected_hash:
            raise ProgramFoundryGepaProposalError(
                f"Oracle semantic source binding does not match foundry runtime for {name}"
            )
        observed_hash = _sha256_bytes(
            read_root_relative_bytes(
                root_descriptor,
                f"runtime/{expected_path.name}",
                label=f"semantic source {name}",
            )
        )
        if observed_hash != expected_hash:
            raise ProgramFoundryGepaProposalError(
                f"Oracle semantic source binding drifted for {name}"
            )
        validated[name] = {"path": raw_path, "sha256": observed_hash}
    return validated


def _metric_plan(candidate: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _mapping(candidate.get("manifest"))
    intent = _mapping(manifest.get("intent"))
    declared = str(intent.get("metric") or "").strip() or None
    if declared in _SUPPORTED_METRICS:
        optimizer_metric = "exact" if declared in {"exact", "exact_match"} else declared
        return {
            "declared_metric": declared,
            "optimizer_metric": optimizer_metric,
            "operator_metric_required": False,
            "blockers": [],
        }
    return {
        "declared_metric": declared,
        "optimizer_metric": None,
        "operator_metric_required": True,
        "blockers": ["unsupported_or_missing_manifest_metric_requires_operator_review"],
    }


def build_program_foundry_gepa_proposal(
    *,
    semantic_payload: Mapping[str, Any],
    semantic_path: Path,
    recommendation_index: int,
    accepted_binding: Mapping[str, Any],
    candidate: Mapping[str, Any],
    runtime: Mapping[str, Any],
    foundry_root: Path,
    foundry_root_descriptor: int,
    max_metric_calls: int = 2,
) -> dict[str, Any]:
    """Convert one explicitly selected Oracle recommendation into a plan only."""

    if (
        isinstance(max_metric_calls, bool)
        or not isinstance(max_metric_calls, int)
        or not 1 <= max_metric_calls <= 20
    ):
        raise ProgramFoundryGepaProposalError(
            "GEPA proposal max_metric_calls must be an integer from 1 through 20"
        )
    result, analysis, recommendation = _validate_semantic_result(
        semantic_payload, recommendation_index=recommendation_index
    )
    root = foundry_root.expanduser().absolute()
    assert_path_descriptor_identity(
        root,
        foundry_root_descriptor,
        label="foundry root",
    )
    semantic_sources = _validate_semantic_sources(
        semantic_payload,
        runtime=runtime,
        root=root,
        root_descriptor=foundry_root_descriptor,
    )
    semantic_path = semantic_path.expanduser().absolute()
    if semantic_path != root / "runtime" / "program_oracle_semantic.json":
        raise ProgramFoundryGepaProposalError(
            "Oracle semantic proposal source must be the foundry runtime sidecar"
        )
    semantic_bytes = read_root_relative_bytes(
        foundry_root_descriptor,
        "runtime/program_oracle_semantic.json",
        label="Oracle semantic proposal source",
    )
    semantic_hash = _sha256_bytes(semantic_bytes)
    try:
        persisted_semantic = json.loads(semantic_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramFoundryGepaProposalError(
            "Oracle semantic proposal source must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(persisted_semantic, Mapping) or _canonical_json(
        persisted_semantic
    ) != _canonical_json(semantic_payload):
        raise ProgramFoundryGepaProposalError(
            "Oracle semantic proposal source differs from the persisted sidecar"
        )
    manifest_hash = _sha256_bytes(
        read_root_relative_bytes(
            foundry_root_descriptor,
            "candidate/manifest.json",
            label="foundry candidate manifest",
        )
    )
    receipt_hash = _sha256_bytes(
        read_root_relative_bytes(
            foundry_root_descriptor,
            "candidate/manifest.json.meta.json",
            label="foundry candidate receipt",
        )
    )
    if manifest_hash != candidate.get(
        "manifest_sha256"
    ) or receipt_hash != candidate.get("receipt_sha256"):
        raise ProgramFoundryGepaProposalError(
            "foundry candidate manifest or receipt drifted before GEPA proposal"
        )
    candidate_directory = os.open(
        "candidate",
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=foundry_root_descriptor,
    )
    try:
        assert_path_descriptor_identity(
            root / "candidate",
            candidate_directory,
            label="foundry candidate directory",
        )
        closure = snapshot_candidate_artifact_closure(
            root / "candidate" / "manifest.json"
        )
        assert_path_descriptor_identity(
            root / "candidate",
            candidate_directory,
            label="foundry candidate directory",
        )
    finally:
        os.close(candidate_directory)
    closure_hash = _sha256_bytes(
        _canonical_json(
            [
                {"kind": item.kind, "path": str(item.path), "sha256": item.sha256}
                for item in closure.artifacts
            ]
        ).encode("utf-8")
    )
    if closure_hash != candidate.get("closure_sha256"):
        raise ProgramFoundryGepaProposalError(
            "foundry candidate artifact closure drifted before GEPA proposal"
        )
    accepted_path = (
        Path(str(accepted_binding.get("quality_proposal_path") or ""))
        .expanduser()
        .absolute()
    )
    if sha256_regular_file(
        accepted_path, label="accepted quality proposal"
    ) != accepted_binding.get("quality_proposal_sha256"):
        raise ProgramFoundryGepaProposalError(
            "accepted quality proposal drifted before GEPA proposal"
        )

    metric_plan = _metric_plan(candidate)
    candidate_binding = {
        key: candidate.get(key)
        for key in (
            "manifest_path",
            "manifest_sha256",
            "receipt_path",
            "receipt_sha256",
            "receipt_status",
            "closure_sha256",
            "identity",
        )
    }
    candidate_binding["accepted_binding"] = dict(accepted_binding)
    body: dict[str, Any] = {
        "schema_version": PROGRAM_FOUNDRY_GEPA_PROPOSAL_SCHEMA,
        "status": "proposal_ready_for_review",
        "authority": "local_advisory_experiment_proposal_only",
        "selection": {
            "recommended_experiment_index": recommendation_index,
            "recommended_experiment_text": recommendation,
            "recommended_experiment_sha256": _sha256_bytes(
                recommendation.encode("utf-8")
            ),
            "selection_explicitly_requested": True,
            "gepa_fit_asserted": False,
        },
        "semantic_binding": {
            "path": str(semantic_path),
            "sha256": semantic_hash,
            "schema_version": semantic_payload.get("schema_version"),
            "request_sha256": semantic_payload.get("request_sha256"),
            "result_schema_version": result.get("schema_version"),
            "backend_kind": result.get("backend_kind"),
            "preferred_model": result.get("preferred_model"),
            "configured_provider": result.get("configured_provider"),
            "configured_model": result.get("configured_model"),
            "executed_provider": result.get("executed_provider"),
            "executed_model": result.get("executed_model"),
            "execution_status": result.get("execution_status"),
            "live_call_succeeded": result.get("live_call_succeeded"),
            "fixture_sha256": result.get("fixture_sha256"),
            "analysis_sha256": _sha256_bytes(
                _canonical_json(analysis.to_dict()).encode("utf-8")
            ),
            "source_binding": semantic_sources,
        },
        "candidate_binding": candidate_binding,
        "runtime_binding": {
            key: runtime.get(key)
            for key in (
                "runtime_episode_path",
                "runtime_episode_sha256",
                "runtime_receipt_path",
                "runtime_receipt_sha256",
                "runtime_episode_id",
                "artifact_hashes",
            )
        },
        "gepa_plan": {
            "kind": "program_refinement_gepa",
            "manifest_path": candidate.get("manifest_path"),
            "metric": metric_plan,
            "max_metric_calls": max_metric_calls,
            "seed": 0,
            "evidence_selection": "deferred_to_explicit_gepa_executor",
            "proposed_output_dir": str(root / "gepa-experiment" / "optimizer-output"),
            "proposed_result_path": str(root / "gepa-experiment" / "gepa-result.json"),
            "execution_requires_explicit_operator_review": True,
        },
        "effect": {
            "proposal_written": True,
            "gepa_invoked": False,
            "gepa_model_calls_made": False,
            "candidate_mutated": False,
            "runtime_mutated": False,
            "external_authority_mutated": False,
            "ak_called": False,
        },
        "non_authority": {
            "may_invoke_gepa": False,
            "execution_authority": False,
            "automatic_optimization": False,
            "automatic_promotion": False,
            "winner_selection": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
        },
    }
    proposal_id = _sha256_bytes(_canonical_json(body).encode("utf-8"))
    assert_path_descriptor_identity(
        root,
        foundry_root_descriptor,
        label="foundry root",
    )
    return {**body, "proposal_id": proposal_id}
