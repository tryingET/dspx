# summary: "Composes accepted intent, candidate generation, runtime evidence, and Oracle semantics into a resumable local foundry workflow."
# read_when:
#   - "Changing the integrated foundry stage order, resume validation, identity binding, or workflow projection."

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.redaction import sanitize_diagnostic_text
from dspx.services.program_evidence_closure import snapshot_candidate_artifact_closure
from dspx.services.program_intent import ProgramIntent, load_program_intent
from dspx.services.program_foundry_io import (
    PROGRAM_FOUNDRY_SUMMARY_NAME,
    foundry_lock,
    preflight_foundry_paths,
    write_summary_atomic,
)
from dspx.services.program_foundry_gepa_proposal import (
    build_program_foundry_gepa_proposal,
)
from dspx.services.program_foundry_gepa_proposal_io import (
    write_or_reuse_program_foundry_gepa_proposal,
)
from dspx.services.program_quality_contract import validate_quality_proposal
from dspx.services.program_runtime_episode import (
    load_validated_program_runtime_episode_bundle,
    run_program_runtime_episode,
)
from dspx.services.program_runtime_oracle_semantic import (
    DEFAULT_PROGRAM_RUNTIME_ORACLE_SEMANTIC_NAME,
    run_program_runtime_oracle_semantics,
)
from dspx.services.program_service import run_generate_from_intent_path
from dspx.services.run_replay_service import check_run_receipt

PROGRAM_FOUNDRY_SCHEMA = "dspx-program-foundry-workflow-v1"
_RUNTIME_TERMINAL_SUCCESS = {
    "executed",
    "executed_quality_passed",
    "executed_valid_review_only",
}


class ProgramFoundryError(ValueError):
    """Raised when a foundry stage is partial, drifted, or not accepted."""


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
        raise ProgramFoundryError(
            f"foundry value must be canonical JSON: {exc}"
        ) from exc


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _intent_payload(intent: ProgramIntent) -> dict[str, Any]:
    return intent.model_dump(mode="json", exclude_none=True)


def _intent_hash(intent: ProgramIntent) -> str:
    # Match program_service's receipt_bundle.evidence.intent_hash contract.
    rendered = json.dumps(_intent_payload(intent), sort_keys=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _accepted_intent_binding(
    intent: ProgramIntent, *, quality_proposal_path: Path
) -> dict[str, Any]:
    proposal_payload = _read_json_object(
        quality_proposal_path, label="accepted quality proposal"
    )
    try:
        validated = validate_quality_proposal(
            proposal_payload,
            allowed_statuses={"accepted_for_program_generation"},
        )
    except Exception as exc:
        raise ProgramFoundryError(
            f"quality proposal acceptance is invalid: {exc}"
        ) from exc
    candidate = ProgramIntent.model_validate(validated["candidate_intent"])
    if candidate.model_dump(mode="json") != intent.model_dump(mode="json"):
        raise ProgramFoundryError(
            "accepted quality proposal candidate intent does not match --intent"
        )
    provenance = intent.options.get("quality_proposal")
    if not isinstance(provenance, Mapping) or provenance.get("accepted") is not True:
        raise ProgramFoundryError(
            "accepted program intent is missing accepted quality provenance"
        )
    if not intent.quality_criteria:
        raise ProgramFoundryError(
            "accepted intent must include at least one frozen quality criterion"
        )
    identity = validated.get("identity")
    decision = validated.get("decision")
    identity_map = dict(identity) if isinstance(identity, Mapping) else {}
    decision_map = dict(decision) if isinstance(decision, Mapping) else {}
    return {
        "accepted": True,
        "quality_proposal_schema": validated.get("schema_version"),
        "quality_proposal_path": str(quality_proposal_path.expanduser().resolve()),
        "quality_proposal_sha256": _sha256_file(quality_proposal_path),
        "proposal_envelope_sha256": identity_map.get("envelope_sha256"),
        "candidate_intent_sha256": identity_map.get("candidate_intent_sha256"),
        "decision_source_envelope_sha256": decision_map.get("source_envelope_sha256"),
        "source_intent_sha256": identity_map.get("intent_sha256"),
        "program_intent_sha256": _intent_hash(intent),
        "quality_criterion_count": len(intent.quality_criteria),
    }


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    target = path.expanduser().resolve()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProgramFoundryError(f"{label} must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProgramFoundryError(f"{label} must contain one JSON object")
    return {str(key): value for key, value in payload.items()}


def _receipt_ok(path: Path, *, label: str) -> dict[str, Any]:
    result = check_run_receipt(path)
    if result.get("status") != "ok":
        detail = "; ".join(str(item) for item in result.get("errors") or [])
        raise ProgramFoundryError(
            f"{label} receipt is not reusable: {detail or result.get('status')}"
        )
    return result


def _candidate_identity(manifest: Mapping[str, Any]) -> dict[str, Any]:
    assembly = manifest.get("candidate_assembly")
    receipt = manifest.get("receipt_bundle")
    assembly_map = dict(assembly) if isinstance(assembly, Mapping) else {}
    receipt_map = dict(receipt) if isinstance(receipt, Mapping) else {}
    return {
        "candidate_id": assembly_map.get("candidate_id")
        or receipt_map.get("candidate_id"),
        "assembly_id": assembly_map.get("assembly_id")
        or receipt_map.get("assembly_id"),
        "receipt_bundle_id": receipt_map.get("receipt_bundle_id"),
        "episode_id": receipt_map.get("episode_id"),
    }


def _validate_candidate_stage(
    *, candidate_dir: Path, expected_intent_hash: str
) -> dict[str, Any]:
    manifest_path = candidate_dir / "manifest.json"
    receipt_path = candidate_dir / "manifest.json.meta.json"
    if not manifest_path.is_file() or not receipt_path.is_file():
        raise ProgramFoundryError(
            "candidate stage is partial; use a new foundry outdir rather than replay generation"
        )
    manifest = _read_json_object(manifest_path, label="candidate manifest")
    receipt = _receipt_ok(receipt_path, label="candidate")
    try:
        closure = snapshot_candidate_artifact_closure(manifest_path)
    except Exception as exc:
        raise ProgramFoundryError(
            f"candidate artifact closure is invalid: {exc}"
        ) from exc
    receipt_bundle = manifest.get("receipt_bundle")
    receipt_bundle_map = (
        dict(receipt_bundle) if isinstance(receipt_bundle, Mapping) else {}
    )
    evidence = receipt_bundle_map.get("evidence")
    evidence_map = dict(evidence) if isinstance(evidence, Mapping) else {}
    if evidence_map.get("intent_hash") != expected_intent_hash:
        raise ProgramFoundryError(
            "candidate intent binding drifted from accepted intent"
        )
    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256_file(manifest_path),
        "receipt_path": str(receipt_path),
        "receipt_sha256": _sha256_file(receipt_path),
        "receipt_status": receipt.get("status"),
        "closure_sha256": _sha256_bytes(
            _canonical_json(
                [
                    {
                        "kind": artifact.kind,
                        "path": str(artifact.path),
                        "sha256": artifact.sha256,
                    }
                    for artifact in closure.artifacts
                ]
            ).encode("utf-8")
        ),
        "identity": _candidate_identity(manifest),
        "manifest": manifest,
    }


def _load_runtime_inputs(path: Path) -> dict[str, Any]:
    payload = _read_json_object(path, label="foundry runtime inputs")
    nested = payload.get("inputs")
    if isinstance(nested, Mapping):
        return {str(key): item for key, item in nested.items()}
    return payload


def _runtime_inputs_hash(path: Path) -> str:
    normalized = {"inputs": _load_runtime_inputs(path)}
    rendered = (
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _validate_runtime_stage(
    *, runtime_dir: Path, candidate: Mapping[str, Any], inputs_path: Path
) -> dict[str, Any]:
    episode_path = runtime_dir / "runtime_episode.json"
    receipt_path = runtime_dir / "runtime_episode.json.meta.json"
    if not episode_path.is_file() or not receipt_path.is_file():
        raise ProgramFoundryError(
            "runtime stage is partial or effect-indeterminate; use a new foundry outdir rather than replay execution"
        )
    manifest_path = Path(str(candidate["manifest_path"]))
    manifest = candidate["manifest"]
    try:
        bundle = load_validated_program_runtime_episode_bundle(
            runtime_episode_path=episode_path,
            expected_manifest_path=manifest_path,
            expected_manifest=manifest,
            expected_manifest_sha256=str(candidate["manifest_sha256"]),
            label="foundry runtime stage",
            error_type=ProgramFoundryError,
        )
    except ProgramFoundryError:
        raise
    except Exception as exc:
        raise ProgramFoundryError(f"runtime stage is invalid: {exc}") from exc
    receipt = _receipt_ok(receipt_path, label="runtime")
    hashes = bundle.runtime_episode.get("artifact_hashes")
    hash_map = dict(hashes) if isinstance(hashes, Mapping) else {}
    expected_inputs_hash = _runtime_inputs_hash(inputs_path)
    if hash_map.get("runtime_inputs_sha256") != expected_inputs_hash:
        raise ProgramFoundryError("runtime inputs drifted from the terminal episode")
    return {
        "runtime_episode_path": str(episode_path),
        "runtime_episode_sha256": bundle.runtime_episode_sha256,
        "runtime_receipt_path": str(receipt_path),
        "runtime_receipt_sha256": _sha256_file(receipt_path),
        "runtime_episode_id": bundle.runtime_episode.get("runtime_episode_id"),
        "execution_status": bundle.runtime_episode.get("execution_status"),
        "status": bundle.runtime_episode.get("status"),
        "artifact_hashes": hash_map,
        "receipt_status": receipt.get("status"),
    }


def _validate_semantic_stage(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = payload.get("semantic_result")
    effect = payload.get("effect")
    non_authority = payload.get("non_authority")
    source_binding = payload.get("source_binding")
    result_map = dict(result) if isinstance(result, Mapping) else {}
    effect_map = dict(effect) if isinstance(effect, Mapping) else {}
    non_authority_map = (
        dict(non_authority) if isinstance(non_authority, Mapping) else {}
    )
    disposition = str(effect_map.get("effect_disposition") or "")
    execution_status = str(result_map.get("execution_status") or "")
    contract_valid = (
        payload.get("schema_version") == "program-runtime-oracle-semantic-v1"
        and payload.get("status") in {"ok", "degraded"}
        and isinstance(source_binding, Mapping)
        and len(str(payload.get("request_sha256") or "")) == 64
        and disposition in {"terminal_result_recorded", "indeterminate"}
        and execution_status
        and non_authority_map.get("promotion_authority") is False
        and non_authority_map.get("activation_authority") is False
    )
    indeterminate = (
        not contract_valid
        or disposition == "indeterminate"
        or execution_status == "effect_indeterminate"
    )
    return {
        "contract_valid": contract_valid,
        "indeterminate": indeterminate,
        "execution_status": execution_status or "effect_indeterminate",
        "effect": effect_map,
        "non_authority": non_authority_map,
        "result": result_map,
    }


def _run_program_foundry_locked(
    *,
    intent_path: Path,
    quality_proposal_path: Path,
    inputs_path: Path,
    root: Path,
    root_descriptor: int,
    skip_oracle_index: bool,
    gepa_recommendation_index: int | None,
    gepa_max_metric_calls: int,
) -> dict[str, Any]:
    """Run or resume accepted intent → candidate → runtime → Oracle semantics.

    Existing stage artifacts and receipts, not foundry.json, decide resumability.
    Partial generation/runtime stages fail closed because their model effects may
    already have occurred. Semantic replay safety is owned by its attempt sidecar.
    """

    intent = load_program_intent(intent_path)
    accepted = _accepted_intent_binding(
        intent, quality_proposal_path=quality_proposal_path
    )
    inputs_path = inputs_path.expanduser().resolve()
    _load_runtime_inputs(inputs_path)
    candidate_dir = root / "candidate"
    runtime_dir = root / "runtime"
    summary_path = root / PROGRAM_FOUNDRY_SUMMARY_NAME
    if candidate_dir.exists():
        candidate_disposition = "reused"
    else:
        candidate_disposition = "created"
        run_generate_from_intent_path(intent_path, outdir=candidate_dir)
    candidate = _validate_candidate_stage(
        candidate_dir=candidate_dir,
        expected_intent_hash=str(accepted["program_intent_sha256"]),
    )

    if runtime_dir.exists():
        runtime_disposition = "reused"
    else:
        runtime_disposition = "created"
        run_program_runtime_episode(
            manifest_path=Path(str(candidate["manifest_path"])),
            inputs_path=inputs_path,
            outdir=runtime_dir,
            skip_oracle_index=skip_oracle_index,
            run_oracle_semantic=False,
        )
    runtime = _validate_runtime_stage(
        runtime_dir=runtime_dir,
        candidate=candidate,
        inputs_path=inputs_path,
    )

    semantic_path = runtime_dir / DEFAULT_PROGRAM_RUNTIME_ORACLE_SEMANTIC_NAME
    if semantic_path.is_symlink():
        raise ProgramFoundryError(
            "foundry Oracle semantic sidecar must not be a symlink"
        )
    semantic_disposition = "reused" if semantic_path.exists() else "created"
    semantic = run_program_runtime_oracle_semantics(
        runtime_episode_path=Path(str(runtime["runtime_episode_path"])),
        out_path=semantic_path,
    )
    semantic_validation = _validate_semantic_stage(semantic)
    semantic_result_map = semantic_validation["result"]
    semantic_execution = str(semantic_validation["execution_status"])
    if semantic_validation["indeterminate"]:
        status = "blocked_indeterminate"
    elif semantic.get("status") != "ok":
        status = "degraded"
    elif runtime.get("status") in _RUNTIME_TERMINAL_SUCCESS:
        status = "ok"
    else:
        status = "behavior_failed"

    gepa_proposal_stage: dict[str, Any] = {
        "status": "not_requested",
        "disposition": "not_created",
        "gepa_invoked": False,
        "execution_authority": False,
    }
    if gepa_recommendation_index is not None:
        if (
            not semantic_validation["contract_valid"]
            or semantic_validation["indeterminate"]
        ):
            raise ProgramFoundryError(
                "GEPA proposal requires a terminal valid Oracle semantic contract"
            )
        proposal_path = root / "gepa_experiment_proposal.json"
        proposal = build_program_foundry_gepa_proposal(
            semantic_payload=semantic,
            semantic_path=semantic_path,
            recommendation_index=gepa_recommendation_index,
            accepted_binding=accepted,
            candidate=candidate,
            runtime=runtime,
            foundry_root=root,
            max_metric_calls=gepa_max_metric_calls,
            foundry_root_descriptor=root_descriptor,
        )
        proposal, proposal_disposition = write_or_reuse_program_foundry_gepa_proposal(
            payload=proposal,
            out_path=proposal_path,
            foundry_root_descriptor=root_descriptor,
        )
        gepa_proposal_stage = {
            "status": proposal["status"],
            "disposition": proposal_disposition,
            "path": str(proposal_path),
            "proposal_id": proposal["proposal_id"],
            "recommended_experiment_index": gepa_recommendation_index,
            "gepa_invoked": False,
            "execution_authority": False,
        }

    payload: dict[str, Any] = {
        "schema_version": PROGRAM_FOUNDRY_SCHEMA,
        "status": status,
        "intent_path": str(intent_path.expanduser().resolve()),
        "inputs_path": str(inputs_path),
        "foundry_root": str(root),
        "workflow_path": str(summary_path),
        "stages": {
            "accepted_intent": {"status": "accepted", "binding": accepted},
            "candidate": {
                "status": "terminal_validated",
                "disposition": candidate_disposition,
                **{key: value for key, value in candidate.items() if key != "manifest"},
            },
            "runtime": {
                "status": "terminal_validated",
                "disposition": runtime_disposition,
                **runtime,
            },
            "oracle_semantic": {
                "status": semantic.get("status"),
                "disposition": semantic_disposition,
                "path": str(semantic_path),
                "request_sha256": semantic.get("request_sha256"),
                "execution_status": semantic_execution,
                "preferred_model": semantic_result_map.get("preferred_model"),
                "executed_model": semantic_result_map.get("executed_model"),
                "contract_valid": semantic_validation["contract_valid"],
                "effect": semantic_validation["effect"],
                "non_authority": semantic_validation["non_authority"],
            },
            "gepa_experiment_proposal": gepa_proposal_stage,
        },
        "bindings": {
            "accepted_intent_sha256": accepted["program_intent_sha256"],
            "candidate_manifest_sha256": candidate["manifest_sha256"],
            "candidate_identity": candidate["identity"],
            "runtime_episode_id": runtime["runtime_episode_id"],
            "runtime_artifact_hashes": runtime["artifact_hashes"],
            "semantic_request_sha256": semantic.get("request_sha256"),
            "semantic_source_binding": semantic.get("source_binding"),
        },
        "effect": {
            "candidate_created": candidate_disposition == "created",
            "runtime_executed": runtime_disposition == "created",
            "semantic_stage_created": semantic_disposition == "created",
            "gepa_proposal_written": gepa_proposal_stage["disposition"] == "created",
            "gepa_invoked": False,
            "shared_oracle_mutated": False,
            "external_authority_mutated": False,
            "ak_called": False,
        },
        "non_authority": {
            "workflow_projection_only": True,
            "promotion_authority": False,
            "activation_authority": False,
            "winner_selection": False,
            "automatic_optimization": False,
            "gepa_execution_authority": False,
            "governance_mutated": False,
        },
    }
    write_summary_atomic(
        summary_path,
        payload,
        root_descriptor=root_descriptor,
    )
    return payload


def run_program_foundry(
    *,
    intent_path: Path,
    quality_proposal_path: Path,
    inputs_path: Path,
    outdir: Path,
    skip_oracle_index: bool = False,
    gepa_recommendation_index: int | None = None,
    gepa_max_metric_calls: int = 2,
) -> dict[str, Any]:
    """Run or safely resume the local foundry under one exclusive root lock."""

    root = preflight_foundry_paths(
        intent_path=intent_path,
        quality_proposal_path=quality_proposal_path,
        inputs_path=inputs_path,
        outdir=outdir,
    )
    with foundry_lock(root) as root_descriptor:
        return _run_program_foundry_locked(
            intent_path=intent_path,
            quality_proposal_path=quality_proposal_path,
            inputs_path=inputs_path,
            root=root,
            root_descriptor=root_descriptor,
            skip_oracle_index=skip_oracle_index,
            gepa_recommendation_index=gepa_recommendation_index,
            gepa_max_metric_calls=gepa_max_metric_calls,
        )


def foundry_failure_message(exc: Exception) -> str:
    """Return a bounded diagnostic for CLI projection without leaking secrets."""

    return sanitize_diagnostic_text(str(exc), limit=2_000)
