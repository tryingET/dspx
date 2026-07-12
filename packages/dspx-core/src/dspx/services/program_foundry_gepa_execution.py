# summary: "Executes one reviewed foundry GEPA proposal with durable no-replay and receipt-bound local evidence."
# read_when:
#   - "Changing reviewed GEPA execution, attempt durability, or execution receipts."

from __future__ import annotations

import json
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_foundry_gepa_execution_contract import (
    ProgramFoundryGepaExecutionError,
    canonical_json,
    load_json,
    mapping,
    sha256_bytes,
    validate_execution_proposal,
    validate_review_declaration,
)
from dspx.services.program_foundry_gepa_proposal_io import (
    assert_path_descriptor_identity,
    sha256_regular_file,
)
from dspx.services.program_foundry_io import foundry_lock
from dspx.services.program_refinement_gepa import build_program_refinement_gepa_result

PROGRAM_FOUNDRY_GEPA_ATTEMPT_SCHEMA = "dspx-program-foundry-gepa-attempt-v1"
PROGRAM_FOUNDRY_GEPA_EXECUTION_SCHEMA = "dspx-program-foundry-gepa-execution-v1"


def _write_json_exclusive(
    directory: int, name: str, payload: Mapping[str, Any]
) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=directory,
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
    os.fsync(directory)


def _read_json_at(directory: int, name: str, *, label: str) -> dict[str, Any]:
    descriptor = os.open(
        name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ProgramFoundryGepaExecutionError(f"{label} must be a regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = -1
            payload = json.load(stream)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(payload, dict):
        raise ProgramFoundryGepaExecutionError(f"{label} must contain one JSON object")
    return payload


def _optimizer_payload_inventory(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ProgramFoundryGepaExecutionError(
                "optimizer output must not contain symlinks"
            )
        if not path.is_file() or path.relative_to(root).as_posix() == "manifest.json":
            continue
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_regular_file(path, label="optimizer output file"),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "hash_algorithm": "sha256",
        "tree_hash": sha256_bytes(canonical_json(files).encode("utf-8")),
        "files": files,
        "excludes": ["manifest.json"],
    }


def _optimizer_tree_hash(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise ProgramFoundryGepaExecutionError(
            "optimizer output must be a real directory"
        )
    inventory: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ProgramFoundryGepaExecutionError(
                "optimizer output must not contain symlinks"
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise ProgramFoundryGepaExecutionError(
                "optimizer output must contain only regular files"
            )
        inventory.append(
            {
                "path": str(path.relative_to(root)),
                "sha256": sha256_regular_file(path, label="optimizer output file"),
            }
        )
    if not inventory:
        raise ProgramFoundryGepaExecutionError("optimizer output is empty")
    return sha256_bytes(canonical_json(inventory).encode("utf-8"))


def _validate_result(
    result: Mapping[str, Any], *, validated: Mapping[str, Any]
) -> dict[str, Any]:
    gepa = mapping(result.get("gepa"))
    output = mapping(result.get("gepa_output"))
    readiness = mapping(output.get("readiness"))
    effect = mapping(result.get("effect"))
    non_authority = mapping(result.get("non_authority"))
    if (
        result.get("schema_version") != "program-refinement-gepa-result-v1"
        or result.get("status")
        not in {
            "degraded",
            "gepa_output_unverified",
            "gepa_unavailable_for_program_candidate",
            "insufficient_behavior_evidence",
        }
        or effect.get("local_gepa_candidate_generated") is not False
        or effect.get("external_authority_mutated") is not False
        or effect.get("governance_mutated") is not False
        or non_authority.get("winner_selection") is not False
        or non_authority.get("automatic_promotion") is not False
    ):
        raise ProgramFoundryGepaExecutionError(
            "GEPA refinement result contract is invalid"
        )
    completed = gepa.get("status") == "completed"
    if completed and gepa.get("attempted") is not True:
        raise ProgramFoundryGepaExecutionError(
            "completed GEPA result must record an attempted optimizer call"
        )
    tree_sha256: str | None = None
    manifest_sha256: str | None = None
    terminal_ok = (
        completed and readiness.get("ready_for_future_candidate_materializer") is True
    )
    output_dir = Path(str(validated["output_dir"]))
    if output_dir.exists():
        tree_sha256 = _optimizer_tree_hash(output_dir)
    if terminal_ok:
        manifest_path = output_dir / "manifest.json"
        manifest_payload, manifest_sha256 = load_json(
            manifest_path,
            label="optimizer output manifest",
        )
        if (
            set(manifest_payload)
            != {
                "created_at",
                "dspy_version",
                "dspx_version",
                "python",
                "program",
                "dataset",
                "io",
                "gepa",
                "providers",
                "output_payload",
            }
            or not isinstance(manifest_payload.get("python"), Mapping)
            or not isinstance(manifest_payload.get("program"), Mapping)
            or not isinstance(manifest_payload.get("dataset"), Mapping)
            or not isinstance(manifest_payload.get("io"), Mapping)
            or not isinstance(manifest_payload.get("gepa"), Mapping)
            or not isinstance(manifest_payload.get("providers"), Mapping)
            or manifest_payload.get("output_payload")
            != _optimizer_payload_inventory(output_dir)
        ):
            raise ProgramFoundryGepaExecutionError(
                "GEPA optimizer output manifest contract is invalid"
            )
        if (
            output.get("root_path") != str(output_dir)
            or output.get("manifest_path") != str(manifest_path)
            or output.get("manifest_present") is not True
            or output.get("manifest_valid") is not True
            or output.get("manifest_kind") != "dspy_gepa_optimizer_output_manifest"
            or output.get("manifest_sha256") != manifest_sha256
        ):
            raise ProgramFoundryGepaExecutionError(
                "GEPA optimizer output binding is invalid"
            )
    return {
        "terminal_ok": terminal_ok,
        "gepa": gepa,
        "readiness": readiness,
        "optimizer_manifest_sha256": manifest_sha256,
        "optimizer_tree_sha256": tree_sha256,
    }


def _build_receipt(
    *,
    validated: Mapping[str, Any],
    attempt_sha256: str,
    result: Mapping[str, Any],
    result_sha256: str,
) -> dict[str, Any]:
    checked = _validate_result(result, validated=validated)
    gepa = checked["gepa"]
    return {
        "schema_version": PROGRAM_FOUNDRY_GEPA_EXECUTION_SCHEMA,
        "status": "ok" if checked["terminal_ok"] else "degraded",
        "proposal_id": validated["proposal_id"],
        "proposal_sha256": validated["proposal_sha256"],
        "attempt_sha256": attempt_sha256,
        "result_path": str(validated["result_path"]),
        "result_sha256": result_sha256,
        "gepa_status": gepa.get("status"),
        "optimizer_output_readiness": checked["readiness"],
        "optimizer_manifest_sha256": checked["optimizer_manifest_sha256"],
        "optimizer_tree_sha256": checked["optimizer_tree_sha256"],
        "effect": {
            "gepa_invoked": gepa.get("attempted") is True,
            "terminal_result_recorded": True,
            "candidate_materialized": False,
            "winner_selected": False,
            "promotion_applied": False,
            "external_authority_mutated": False,
            "ak_called": False,
        },
        "non_authority": {
            "local_optimizer_evidence_only": True,
            "winner_selection": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
        },
    }


def _existing_execution_state(
    experiment_directory: int,
    *,
    validated: Mapping[str, Any],
    operator_label: str,
) -> dict[str, Any]:
    try:
        attempt = _read_json_at(
            experiment_directory,
            "attempt.json",
            label="GEPA attempt",
        )
    except FileNotFoundError as exc:
        raise ProgramFoundryGepaExecutionError(
            "existing GEPA experiment directory has no durable attempt marker"
        ) from exc
    declaration = mapping(attempt.get("review_declaration"))
    expected_declaration = validate_review_declaration(
        proposal_id=str(validated["proposal_id"]),
        declared_reviewed=str(validated["proposal_id"]),
        operator_label=operator_label,
    )
    attempt_non_authority = mapping(attempt.get("non_authority"))
    attempt_body = {
        str(key): item for key, item in attempt.items() if key != "attempt_id"
    }
    declaration_fields = {
        "schema_version",
        "kind",
        "proposal_id",
        "declaration",
        "operator_label",
        "recorded_at",
        "authenticated",
        "identity_verified",
        "approval_authority_asserted",
        "execution_intent_only",
    }
    recorded_at = str(declaration.get("recorded_at") or "")
    try:
        parsed_recorded_at = datetime.fromisoformat(recorded_at)
        recorded_at_valid = (
            "T" in recorded_at
            and parsed_recorded_at.tzinfo is not None
            and parsed_recorded_at.utcoffset() is not None
        )
    except ValueError:
        recorded_at_valid = False
    if (
        attempt.get("schema_version") != PROGRAM_FOUNDRY_GEPA_ATTEMPT_SCHEMA
        or set(attempt)
        != {
            "attempt_id",
            "schema_version",
            "status",
            "proposal_id",
            "proposal_sha256",
            "review_declaration",
            "effect_disposition",
            "gepa_invocation_possible",
            "no_replay_after_marker",
            "non_authority",
        }
        or attempt.get("attempt_id")
        != sha256_bytes(canonical_json(attempt_body).encode("utf-8"))
        or attempt.get("proposal_id") != validated["proposal_id"]
        or attempt.get("proposal_sha256") != validated["proposal_sha256"]
        or attempt.get("status") != "effect_possible"
        or attempt.get("effect_disposition") != "indeterminate_until_terminal_receipt"
        or attempt.get("gepa_invocation_possible") is not True
        or attempt.get("no_replay_after_marker") is not True
        or declaration.get("schema_version") != expected_declaration["schema_version"]
        or declaration.get("kind") != expected_declaration["kind"]
        or declaration.get("proposal_id") != expected_declaration["proposal_id"]
        or declaration.get("declaration") != expected_declaration["declaration"]
        or declaration.get("operator_label") != operator_label
        or set(declaration) != declaration_fields
        or not recorded_at_valid
        or declaration.get("authenticated") is not False
        or declaration.get("identity_verified") is not False
        or declaration.get("approval_authority_asserted") is not False
        or declaration.get("execution_intent_only") is not True
        or attempt_non_authority
        != {
            "winner_selection": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
        }
    ):
        raise ProgramFoundryGepaExecutionError("existing GEPA attempt identity drifted")
    attempt_path = Path(str(validated["result_path"])).parent / "attempt.json"
    attempt_sha256 = sha256_regular_file(attempt_path, label="GEPA attempt")
    try:
        result = _read_json_at(
            experiment_directory,
            "gepa-result.json",
            label="GEPA result",
        )
    except FileNotFoundError:
        return {
            **attempt,
            "status": "blocked_indeterminate",
            "effect_disposition": "indeterminate_no_replay",
            "reused": True,
        }
    result_path = Path(str(validated["result_path"]))
    result_sha256 = sha256_regular_file(result_path, label="GEPA result")
    try:
        receipt = _read_json_at(
            experiment_directory,
            "execution-receipt.json",
            label="GEPA execution receipt",
        )
    except FileNotFoundError:
        receipt = _build_receipt(
            validated=validated,
            attempt_sha256=attempt_sha256,
            result=result,
            result_sha256=result_sha256,
        )
        _write_json_exclusive(
            experiment_directory,
            "execution-receipt.json",
            receipt,
        )
        return {**receipt, "reused": True, "receipt_finalized": True}
    expected = _build_receipt(
        validated=validated,
        attempt_sha256=attempt_sha256,
        result=result,
        result_sha256=result_sha256,
    )
    if receipt != expected:
        raise ProgramFoundryGepaExecutionError(
            "GEPA execution receipt or bound output drifted"
        )
    return {**receipt, "reused": True}


def execute_reviewed_program_foundry_gepa(
    *, proposal_path: Path, declared_reviewed: str, operator_label: str
) -> dict[str, Any]:
    """Execute the proposal once after durable review and attempt recording."""

    proposal_path = proposal_path.expanduser().absolute()
    root = proposal_path.parent
    with foundry_lock(root) as root_descriptor:
        assert_path_descriptor_identity(root, root_descriptor, label="foundry root")
        proposal, proposal_sha256 = load_json(
            proposal_path,
            label="foundry GEPA proposal",
        )
        validated = validate_execution_proposal(
            proposal_path=proposal_path,
            proposal_sha256=proposal_sha256,
            payload=proposal,
            root=root,
        )
        declaration = validate_review_declaration(
            proposal_id=validated["proposal_id"],
            declared_reviewed=declared_reviewed,
            operator_label=operator_label,
        )
        try:
            os.mkdir("gepa-experiment", 0o700, dir_fd=root_descriptor)
            created = True
        except FileExistsError:
            created = False
        os.fsync(root_descriptor)
        experiment_directory = os.open(
            "gepa-experiment",
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_descriptor,
        )
        try:
            if not created:
                return _existing_execution_state(
                    experiment_directory,
                    validated=validated,
                    operator_label=operator_label.strip(),
                )
            attempt_body = {
                "schema_version": PROGRAM_FOUNDRY_GEPA_ATTEMPT_SCHEMA,
                "status": "effect_possible",
                "proposal_id": validated["proposal_id"],
                "proposal_sha256": validated["proposal_sha256"],
                "review_declaration": declaration,
                "effect_disposition": "indeterminate_until_terminal_receipt",
                "gepa_invocation_possible": True,
                "no_replay_after_marker": True,
                "non_authority": {
                    "winner_selection": False,
                    "promotion_authority": False,
                    "activation_authority": False,
                    "governance_authority": False,
                },
            }
            attempt = {
                **attempt_body,
                "attempt_id": sha256_bytes(
                    canonical_json(attempt_body).encode("utf-8")
                ),
            }
            _write_json_exclusive(experiment_directory, "attempt.json", attempt)
            os.fsync(root_descriptor)
            result = build_program_refinement_gepa_result(
                manifest_path=validated["manifest_path"],
                outdir=validated["output_dir"],
                metric=validated["optimizer_metric"],
                max_metric_calls=validated["max_metric_calls"],
                result_out=validated["result_path"],
            )
            _validate_result(result, validated=validated)
            _write_json_exclusive(experiment_directory, "gepa-result.json", result)
            result_sha256 = sha256_regular_file(
                validated["result_path"], label="GEPA result"
            )
            receipt = _build_receipt(
                validated=validated,
                attempt_sha256=sha256_regular_file(
                    root / "gepa-experiment" / "attempt.json",
                    label="GEPA attempt",
                ),
                result=result,
                result_sha256=result_sha256,
            )
            _write_json_exclusive(
                experiment_directory,
                "execution-receipt.json",
                receipt,
            )
            return {**receipt, "reused": False}
        finally:
            os.close(experiment_directory)
