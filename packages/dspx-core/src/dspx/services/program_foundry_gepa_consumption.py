# summary: "Consumes one successful foundry GEPA execution into one receipt-bound local candidate comparison."
# read_when:
#   - "Changing execution-receipt consumption, candidate materialization/comparison, or downstream no-replay behavior."

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_foundry_gepa_execution_validation import (
    ProgramFoundryGepaExecutionError,
    validate_successful_program_foundry_gepa_execution_receipt,
)
from dspx.services.program_foundry_gepa_proposal_io import (
    assert_path_descriptor_identity,
    read_regular_bytes,
)
from dspx.services.program_foundry_io import foundry_lock
from dspx.services.program_refinement_comparison import (
    validate_program_refinement_candidate_comparison_contract,
)
from dspx.services.program_refinement_gepa_candidate_contracts import (
    validate_program_refinement_gepa_candidate_result_contract,
)
from dspx.services.program_refinement_workflow import (
    materialize_and_compare_gepa_refinement_candidate,
    write_program_refinement_workflow_result,
)

PROGRAM_FOUNDRY_GEPA_CONSUMPTION_ATTEMPT_SCHEMA = (
    "dspx-program-foundry-gepa-consumption-attempt-v1"
)
PROGRAM_FOUNDRY_GEPA_CONSUMPTION_SCHEMA = "dspx-program-foundry-gepa-consumption-v1"


class ProgramFoundryGepaConsumptionError(ValueError):
    """Raised when a successful GEPA execution cannot be consumed safely."""


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
        raise ProgramFoundryGepaConsumptionError(
            f"foundry GEPA consumption value must be canonical JSON: {exc}"
        ) from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(read_regular_bytes(path, label=label).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramFoundryGepaConsumptionError(f"{label} must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProgramFoundryGepaConsumptionError(
            f"{label} must contain one JSON object"
        )
    return {str(key): item for key, item in payload.items()}


def _load_json_snapshot(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    raw = read_regular_bytes(path, label=label)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramFoundryGepaConsumptionError(f"{label} must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProgramFoundryGepaConsumptionError(
            f"{label} must contain one JSON object"
        )
    return ({str(key): item for key, item in payload.items()}, _sha256_bytes(raw))


def _write_json_exclusive(
    path: Path,
    payload: Mapping[str, Any],
    *,
    root_descriptor: int,
) -> str:
    target = path.expanduser().absolute()
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if target.parent.name != "gepa-experiment":
        raise ProgramFoundryGepaConsumptionError(
            "GEPA consumption sidecars must stay in the canonical experiment directory"
        )
    experiment_descriptor = os.open(
        "gepa-experiment",
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=root_descriptor,
    )
    try:
        assert_path_descriptor_identity(
            target.parent,
            experiment_descriptor,
            label="foundry GEPA experiment directory",
        )
        descriptor = os.open(
            target.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=experiment_descriptor,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        os.fsync(experiment_descriptor)
        os.fsync(root_descriptor)
    finally:
        os.close(experiment_descriptor)
    return _sha256_bytes(encoded)


def _paths(experiment_root: Path) -> dict[str, Path]:
    return {
        "attempt": experiment_root / "consumption-attempt.json",
        "candidate_root": experiment_root / "materialized-candidate",
        "candidate_result": experiment_root / "candidate-result.json",
        "comparison": experiment_root / "candidate-comparison.json",
        "workflow": experiment_root / "materialize-and-compare-result.json",
        "receipt": experiment_root / "consumption-receipt.json",
    }


def _validate_materialized_outputs(
    *, paths: Mapping[str, Path], source_manifest: Path, gepa_result: Path
) -> dict[str, Any]:
    candidate_result, candidate_result_sha256 = _load_json_snapshot(
        paths["candidate_result"],
        label="GEPA candidate result",
    )
    declared_candidate = candidate_result.get("candidate")
    if not isinstance(declared_candidate, Mapping):
        raise ProgramFoundryGepaConsumptionError(
            "GEPA candidate result is missing candidate binding"
        )
    expected_candidate_root = paths["candidate_root"]
    candidate_manifest = expected_candidate_root / "manifest.json"
    if (
        Path(str(declared_candidate.get("root_path") or "")) != expected_candidate_root
        or Path(str(declared_candidate.get("manifest_path") or ""))
        != candidate_manifest
        or expected_candidate_root.is_symlink()
    ):
        raise ProgramFoundryGepaConsumptionError(
            "GEPA candidate must use the canonical foundry output root"
        )
    candidate_manifest_snapshot, candidate_manifest_sha256 = _load_json_snapshot(
        candidate_manifest,
        label="GEPA candidate manifest",
    )
    validated_candidate = validate_program_refinement_gepa_candidate_result_contract(
        candidate_result,
        expected_source_manifest_path=source_manifest,
        expected_gepa_result_path=gepa_result,
        label="foundry GEPA candidate result",
        error_type=ProgramFoundryGepaConsumptionError,
    )
    if (
        Path(str(validated_candidate["candidate_root"])) != expected_candidate_root
        or Path(str(validated_candidate["candidate_manifest_path"]))
        != candidate_manifest
    ):
        raise ProgramFoundryGepaConsumptionError(
            "validated GEPA candidate escaped the canonical foundry output root"
        )
    candidate_manifest_after, candidate_manifest_hash_after = _load_json_snapshot(
        candidate_manifest,
        label="GEPA candidate manifest",
    )
    if (
        candidate_manifest_after != candidate_manifest_snapshot
        or candidate_manifest_hash_after != candidate_manifest_sha256
    ):
        raise ProgramFoundryGepaConsumptionError(
            "GEPA candidate manifest changed during validation"
        )
    comparison = validate_program_refinement_candidate_comparison_contract(
        comparison_path=paths["comparison"],
        candidate_manifest_path=candidate_manifest,
        source_manifest_path=source_manifest,
    )
    candidate_manifest_final, candidate_manifest_hash_final = _load_json_snapshot(
        candidate_manifest,
        label="GEPA candidate manifest",
    )
    if (
        candidate_manifest_final != candidate_manifest_snapshot
        or candidate_manifest_hash_final != candidate_manifest_sha256
    ):
        raise ProgramFoundryGepaConsumptionError(
            "GEPA candidate manifest changed during comparison validation"
        )
    comparison_snapshot, comparison_sha256 = _load_json_snapshot(
        paths["comparison"],
        label="GEPA candidate comparison",
    )
    if comparison_snapshot != comparison:
        raise ProgramFoundryGepaConsumptionError(
            "GEPA comparison changed during validation"
        )
    workflow, workflow_sha256 = _load_json_snapshot(
        paths["workflow"],
        label="GEPA materialize-and-compare result",
    )
    expected_workflow_status = (
        "materialized_and_compared_gepa_candidate"
        if comparison.get("status") == "compared"
        else "materialized_gepa_candidate_with_insufficient_behavior_evidence"
    )
    if (
        workflow.get("schema_version")
        != "program-refinement-gepa-generate-and-compare-result-v1"
        or workflow.get("generation") != candidate_result
        or workflow.get("status") != expected_workflow_status
        or workflow.get("comparison_sidecar", {}).get("path")
        != str(paths["comparison"])
        or workflow.get("comparison_sidecar", {}).get("status")
        != comparison.get("status")
        or workflow.get("effect")
        != {
            "local_gepa_candidate_generated": True,
            "local_comparison_written": True,
            "source_program_files_mutated": False,
            "gepa_optimizer_output_mutated": False,
            "comparison_mutated_source_candidate": False,
            "comparison_mutated_gepa_candidate": False,
            "third_candidate_generated": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
        }
        or workflow.get("non_authority")
        != {
            "local_generation_and_comparison_only": False,
            "local_gepa_generation_and_comparison_only": True,
            "program_gen_automation": False,
            "automatic_promotion": False,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "winner_selection": False,
            "external_authority_export": False,
            "governance_authority": False,
            "external_mutation": False,
        }
    ):
        raise ProgramFoundryGepaConsumptionError(
            "GEPA materialize-and-compare workflow binding is invalid"
        )
    return {
        "candidate_result": candidate_result,
        "candidate_manifest": candidate_manifest,
        "comparison": comparison,
        "workflow": workflow,
        "hashes": {
            "candidate_manifest": candidate_manifest_sha256,
            "candidate_result": candidate_result_sha256,
            "comparison": comparison_sha256,
            "workflow": workflow_sha256,
        },
    }


def _receipt_payload(
    *,
    execution: Mapping[str, Any],
    paths: Mapping[str, Path],
    outputs: Mapping[str, Any],
) -> dict[str, Any]:
    comparison = outputs["comparison"]
    comparison_status = comparison.get("status")
    return {
        "schema_version": PROGRAM_FOUNDRY_GEPA_CONSUMPTION_SCHEMA,
        "status": "ok" if comparison_status == "compared" else "degraded",
        "proposal_id": execution["proposal_id"],
        "bindings": {
            "execution_receipt_path": str(execution["execution_receipt_path"]),
            "execution_receipt_sha256": execution["execution_receipt_sha256"],
            "source_manifest_path": str(execution["manifest_path"]),
            "source_manifest_sha256": execution["source_manifest_sha256"],
            "gepa_result_path": str(execution["result_path"]),
            "gepa_result_sha256": execution["execution_receipt"]["result_sha256"],
            "consumption_attempt_sha256": execution["consumption_attempt_sha256"],
            "candidate_manifest_path": str(outputs["candidate_manifest"]),
            "candidate_manifest_sha256": outputs["hashes"]["candidate_manifest"],
            "candidate_result_path": str(paths["candidate_result"]),
            "candidate_result_sha256": outputs["hashes"]["candidate_result"],
            "comparison_path": str(paths["comparison"]),
            "comparison_sha256": outputs["hashes"]["comparison"],
            "workflow_path": str(paths["workflow"]),
            "workflow_sha256": outputs["hashes"]["workflow"],
        },
        "comparison_status": comparison_status,
        "effect": {
            "one_local_candidate_materialized": True,
            "local_comparison_recorded": True,
            "gepa_reexecuted": False,
            "winner_selected": False,
            "promotion_applied": False,
            "external_authority_mutated": False,
            "ak_called": False,
        },
        "non_authority": {
            "local_candidate_and_comparison_evidence_only": True,
            "winner_selection": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
        },
    }


def _validate_existing_receipt(
    *,
    execution: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> dict[str, Any]:
    outputs = _validate_materialized_outputs(
        paths=paths,
        source_manifest=execution["manifest_path"],
        gepa_result=execution["result_path"],
    )
    expected = _receipt_payload(execution=execution, paths=paths, outputs=outputs)
    receipt = _load_json(paths["receipt"], label="GEPA consumption receipt")
    if receipt != expected:
        raise ProgramFoundryGepaConsumptionError(
            "GEPA consumption receipt or bound artifacts drifted"
        )
    return {**receipt, "reused": True}


def consume_successful_program_foundry_gepa_receipt(
    *, execution_receipt_path: Path
) -> dict[str, Any]:
    """Materialize and compare exactly one candidate from one successful receipt."""

    receipt_path = execution_receipt_path.expanduser().absolute()
    root = receipt_path.parent.parent
    with foundry_lock(root) as root_descriptor:
        assert_path_descriptor_identity(root, root_descriptor, label="foundry root")
        try:
            execution = validate_successful_program_foundry_gepa_execution_receipt(
                receipt_path,
                root_descriptor=root_descriptor,
            )
        except ProgramFoundryGepaExecutionError as exc:
            raise ProgramFoundryGepaConsumptionError(str(exc)) from exc
        experiment_root = Path(str(execution["experiment_root"]))
        source_manifest = Path(str(execution["manifest_path"]))
        gepa_result = Path(str(execution["result_path"]))
        paths = _paths(experiment_root)
        if paths["receipt"].exists():
            _, attempt_sha256 = _load_json_snapshot(
                paths["attempt"],
                label="GEPA consumption attempt",
            )
            execution = {
                **execution,
                "consumption_attempt_sha256": attempt_sha256,
            }
            return _validate_existing_receipt(execution=execution, paths=paths)
        if paths["attempt"].exists():
            return {
                "schema_version": PROGRAM_FOUNDRY_GEPA_CONSUMPTION_SCHEMA,
                "status": "blocked_indeterminate",
                "proposal_id": execution["proposal_id"],
                "effect_disposition": "candidate_materialization_or_comparison_may_have_occurred",
                "reused": True,
                "non_authority": {
                    "winner_selection": False,
                    "promotion_authority": False,
                    "activation_authority": False,
                    "governance_authority": False,
                },
            }
        protected_outputs = (
            paths["candidate_root"],
            paths["candidate_result"],
            paths["comparison"],
            paths["workflow"],
        )
        if any(path.exists() or path.is_symlink() for path in protected_outputs):
            raise ProgramFoundryGepaConsumptionError(
                "foundry GEPA consumption outputs exist without an attempt marker"
            )
        attempt_body = {
            "schema_version": PROGRAM_FOUNDRY_GEPA_CONSUMPTION_ATTEMPT_SCHEMA,
            "status": "effect_possible",
            "proposal_id": execution["proposal_id"],
            "execution_receipt_path": str(receipt_path),
            "execution_receipt_sha256": execution["execution_receipt_sha256"],
            "no_replay_after_marker": True,
            "effect_disposition": "indeterminate_until_consumption_receipt",
            "non_authority": {
                "winner_selection": False,
                "promotion_authority": False,
                "activation_authority": False,
                "governance_authority": False,
            },
        }
        attempt = {
            **attempt_body,
            "attempt_id": _sha256_bytes(_canonical_json(attempt_body).encode("utf-8")),
        }
        attempt_sha256 = _write_json_exclusive(
            paths["attempt"],
            attempt,
            root_descriptor=root_descriptor,
        )
        execution = {**execution, "consumption_attempt_sha256": attempt_sha256}
        experiment_descriptor = os.open(
            "gepa-experiment",
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_descriptor,
        )
        try:
            assert_path_descriptor_identity(
                experiment_root,
                experiment_descriptor,
                label="foundry GEPA experiment directory",
            )
            assert_path_descriptor_identity(
                root,
                root_descriptor,
                label="foundry root",
            )
            workflow = materialize_and_compare_gepa_refinement_candidate(
                manifest_path=source_manifest,
                gepa_result_path=gepa_result,
                outdir=paths["candidate_root"],
                comparison_out_path=paths["comparison"],
                gepa_candidate_result_out=paths["candidate_result"],
            )
            workflow = write_program_refinement_workflow_result(
                workflow,
                paths["workflow"],
            )
            assert_path_descriptor_identity(
                experiment_root,
                experiment_descriptor,
                label="foundry GEPA experiment directory",
            )
            assert_path_descriptor_identity(
                root,
                root_descriptor,
                label="foundry root",
            )
            outputs = _validate_materialized_outputs(
                paths=paths,
                source_manifest=source_manifest,
                gepa_result=gepa_result,
            )
            if outputs["workflow"] != workflow:
                raise ProgramFoundryGepaConsumptionError(
                    "persisted GEPA workflow differs from materialization result"
                )
            assert_path_descriptor_identity(
                experiment_root,
                experiment_descriptor,
                label="foundry GEPA experiment directory",
            )
            receipt = _receipt_payload(
                execution=execution,
                paths=paths,
                outputs=outputs,
            )
            _write_json_exclusive(
                paths["receipt"],
                receipt,
                root_descriptor=root_descriptor,
            )
            return {**receipt, "reused": False}
        finally:
            os.close(experiment_descriptor)
