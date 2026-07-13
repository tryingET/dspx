# summary: "Dispatches a selected task adjudicator through one receipt-bound foundry request without executing external backends."
# read_when:
#   - "Changing adjudicator dispatch requests, registration provenance, deterministic adapter routing, or pending behavior."

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from dspx.services.artifact_boundary import (
    atomic_publish_bytes,
    read_stable_json_artifact,
)
from dspx.services.program_adjudicator_protocol import (
    FOUNDRY_GEPA_COMPARISON_TASK_KIND,
    builtin_foundry_deterministic_registration,
    ProgramAdjudicatorProtocolError,
    load_task_adjudicator_registration,
    select_task_adjudicator,
)
from dspx.services.program_foundry_gepa_comparison_adjudication import (
    ProgramFoundryGepaComparisonAdjudicationError,
    ProgramFoundryGepaComparisonAdjudicationIndeterminateError,
    adjudicate_program_foundry_gepa_comparison,
)
from dspx.services.program_foundry_gepa_comparison_jury import (
    ProgramFoundryGepaComparisonJuryError,
    validate_successful_program_foundry_gepa_comparison_jury_receipt,
)
from dspx.services.program_foundry_io import foundry_lock

PROGRAM_FOUNDRY_GEPA_ADJUDICATOR_REQUEST_SCHEMA = (
    "dspx-program-foundry-gepa-adjudicator-request-v1"
)
PROGRAM_FOUNDRY_GEPA_ADJUDICATOR_DISPATCH_SCHEMA = (
    "dspx-program-foundry-gepa-adjudicator-dispatch-v1"
)


class ProgramFoundryGepaAdjudicatorDispatchError(ValueError):
    """Raised when a selected foundry adjudicator cannot be dispatched safely."""


class ProgramFoundryGepaAdjudicatorDispatchIndeterminateError(
    ProgramFoundryGepaAdjudicatorDispatchError
):
    """Raised when request publication may have committed durably."""


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProgramFoundryGepaAdjudicatorDispatchError(
            f"adjudicator dispatch value must be canonical JSON: {exc}"
        ) from exc


def _pretty_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _registration_snapshot(
    registration_paths: Sequence[Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    registrations_by_id: dict[str, dict[str, Any]] = {}
    seen_paths: set[Path] = set()
    for raw_path in registration_paths:
        path = _lexical_path(raw_path)
        if path in seen_paths:
            raise ProgramFoundryGepaAdjudicatorDispatchError(
                f"duplicate adjudicator registration source path: {path}"
            )
        seen_paths.add(path)
        try:
            registration, source_sha256 = load_task_adjudicator_registration(path)
        except ProgramAdjudicatorProtocolError as exc:
            raise ProgramFoundryGepaAdjudicatorDispatchError(str(exc)) from exc
        entries.append(
            {
                "source_path": str(path),
                "source_sha256": source_sha256,
                "registration_id": registration["registration_id"],
                "registration": registration,
            }
        )
        registrations_by_id[registration["registration_id"]] = registration
    entries.sort(
        key=lambda item: (
            item["registration_id"],
            item["source_sha256"],
            item["source_path"],
        )
    )
    registrations = [registrations_by_id[key] for key in sorted(registrations_by_id)]
    return entries, registrations


def _request_body(
    *,
    validated_jury: Mapping[str, Any],
    registration_entries: Sequence[Mapping[str, Any]],
    selection: Mapping[str, Any],
    include_builtin_fallback: bool,
) -> dict[str, Any]:
    registration_snapshot = [dict(entry) for entry in registration_entries]
    snapshot_sha256 = _sha256(_canonical_json(registration_snapshot))
    selection_snapshot = dict(selection)
    selection_sha256 = _sha256(_canonical_json(selection_snapshot))
    selected = selection.get("selected_registration")
    selected_registration = dict(selected) if isinstance(selected, Mapping) else None
    selection_status = selection.get("status")
    request_status = (
        "ready"
        if selection_status == "selected"
        else "pending"
        if selection_status == "pending"
        else "require_review"
    )
    return {
        "schema_version": PROGRAM_FOUNDRY_GEPA_ADJUDICATOR_REQUEST_SCHEMA,
        "status": request_status,
        "task_kind": FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        "proposal_id": validated_jury["proposal_id"],
        "include_builtin_fallback": include_builtin_fallback,
        "registration_snapshot": {
            "entries": registration_snapshot,
            "sha256": snapshot_sha256,
        },
        "selection": selection_snapshot,
        "bindings": {
            "comparison_jury_receipt_path": str(validated_jury["jury_receipt_path"]),
            "comparison_jury_receipt_sha256": validated_jury["jury_receipt_sha256"],
            "jury_results_path": str(validated_jury["jury_result_path"]),
            "jury_results_sha256": validated_jury["jury_result_sha256"],
            "candidate_manifest_path": str(validated_jury["candidate_manifest_path"]),
            "candidate_manifest_sha256": validated_jury["candidate_manifest_sha256"],
            "comparison_path": str(validated_jury["comparison_path"]),
            "comparison_sha256": validated_jury["comparison_sha256"],
            "registration_snapshot_sha256": snapshot_sha256,
            "selection_sha256": selection_sha256,
        },
        "selected_adjudicator": selected_registration,
        "execution": {
            "started": False,
            "external_executor_invoked": False,
            "provider_calls_may_have_occurred": False,
            "human_or_panel_contacted": False,
            "effects_applied": False,
        },
        "identity": {
            "claims": (
                selected_registration["identity_claims"]
                if selected_registration is not None
                else None
            ),
            "authenticated_by_dspx": False,
            "quorum_satisfied": False,
        },
        "authority": {
            "bounded_local_dispatch_request_only": True,
            "production_promotion": False,
            "activation": False,
            "governance": False,
            "external_apply": False,
        },
    }


def _request_payload(**kwargs: Any) -> dict[str, Any]:
    body = _request_body(**kwargs)
    return {**body, "request_id": _sha256(_canonical_json(body))}


def _load_current_registrations(
    entries: Sequence[Mapping[str, Any]],
) -> None:
    for entry in entries:
        path = Path(str(entry["source_path"]))
        try:
            registration, digest = load_task_adjudicator_registration(path)
        except ProgramAdjudicatorProtocolError as exc:
            raise ProgramFoundryGepaAdjudicatorDispatchError(str(exc)) from exc
        if (
            digest != entry["source_sha256"]
            or registration != entry["registration"]
            or registration["registration_id"] != entry["registration_id"]
        ):
            raise ProgramFoundryGepaAdjudicatorDispatchError(
                "adjudicator registration source changed during dispatch"
            )


def _dispatch_envelope(
    *,
    request: Mapping[str, Any],
    request_path: Path,
    deterministic_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if deterministic_result is not None:
        status = "completed"
        disposition = deterministic_result["disposition"]
        execution = {
            "backend_kind": "deterministic_policy",
            "deterministic_backend_executed_or_reused": True,
            "external_executor_invoked": False,
            "provider_calls_may_have_occurred": False,
            "human_or_panel_contacted": False,
        }
    else:
        status = str(request["status"])
        disposition = "pending" if status == "pending" else "require_review"
        execution = {
            "backend_kind": (
                request["selected_adjudicator"]["backend"]["kind"]
                if request.get("selected_adjudicator") is not None
                else None
            ),
            "deterministic_backend_executed_or_reused": False,
            "external_executor_invoked": False,
            "provider_calls_may_have_occurred": False,
            "human_or_panel_contacted": False,
        }
    return {
        "schema_version": PROGRAM_FOUNDRY_GEPA_ADJUDICATOR_DISPATCH_SCHEMA,
        "status": status,
        "disposition": disposition,
        "request_id": request["request_id"],
        "request_path": str(request_path),
        "selected_adjudicator": request.get("selected_adjudicator"),
        "execution": execution,
        "deterministic_adjudication": (
            dict(deterministic_result) if deterministic_result is not None else None
        ),
        "identity_authenticated_by_dspx": False,
        "production_activation_applied": False,
        "governance_mutated": False,
        "external_authority_mutated": False,
    }


def validate_program_foundry_gepa_adjudicator_request(
    request_path: Path,
    *,
    root_descriptor: int,
    registration_paths: Sequence[Path],
) -> dict[str, Any]:
    """Rebuild a persisted dispatch request from current jury and registration bytes."""

    lexical = _lexical_path(request_path)
    if (
        lexical.name != "comparison-adjudicator-request.json"
        or lexical.parent.name != "gepa-experiment"
    ):
        raise ProgramFoundryGepaAdjudicatorDispatchError(
            "foundry adjudicator request path is not canonical"
        )
    artifact = read_stable_json_artifact(
        lexical,
        label="foundry adjudicator request",
        error_type=ProgramFoundryGepaAdjudicatorDispatchError,
    )
    request = artifact.payload
    snapshot = request.get("registration_snapshot")
    entries = snapshot.get("entries") if isinstance(snapshot, Mapping) else None
    if not isinstance(entries, list):
        raise ProgramFoundryGepaAdjudicatorDispatchError(
            "foundry adjudicator registration snapshot is invalid"
        )
    explicit_entries, explicit_registrations = _registration_snapshot(
        registration_paths
    )
    if entries != explicit_entries:
        raise ProgramFoundryGepaAdjudicatorDispatchError(
            "foundry adjudicator request registration sources do not match explicit inputs"
        )
    fallback = request.get("include_builtin_fallback")
    if not isinstance(fallback, bool):
        raise ProgramFoundryGepaAdjudicatorDispatchError(
            "foundry adjudicator fallback declaration must be boolean"
        )
    try:
        selection = select_task_adjudicator(
            task_kind=FOUNDRY_GEPA_COMPARISON_TASK_KIND,
            registrations=explicit_registrations,
            include_builtin_fallback=fallback,
        )
        validated_jury = (
            validate_successful_program_foundry_gepa_comparison_jury_receipt(
                lexical.parent / "comparison-jury-receipt.json",
                root_descriptor=root_descriptor,
            )
        )
    except (
        ProgramAdjudicatorProtocolError,
        ProgramFoundryGepaComparisonJuryError,
    ) as exc:
        raise ProgramFoundryGepaAdjudicatorDispatchError(str(exc)) from exc
    expected = _request_payload(
        validated_jury=validated_jury,
        registration_entries=explicit_entries,
        selection=selection,
        include_builtin_fallback=fallback,
    )
    if request != expected:
        raise ProgramFoundryGepaAdjudicatorDispatchError(
            "foundry adjudicator request or bound inputs drifted"
        )
    return {
        "request": request,
        "request_path": lexical,
        "request_sha256": artifact.sha256,
        "validated_jury": validated_jury,
    }


def _validate_deterministic_result_binding(
    *,
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    current_jury: Mapping[str, Any],
) -> None:
    request_bindings = request.get("bindings")
    result_bindings = result.get("bindings")
    if not isinstance(request_bindings, Mapping) or not isinstance(
        result_bindings, Mapping
    ):
        raise ProgramFoundryGepaAdjudicatorDispatchIndeterminateError(
            "deterministic adjudication committed without request lineage bindings"
        )
    expected_path = str(current_jury["jury_receipt_path"])
    expected_hash = current_jury["jury_receipt_sha256"]
    if (
        request_bindings.get("comparison_jury_receipt_path") != expected_path
        or request_bindings.get("comparison_jury_receipt_sha256") != expected_hash
        or result_bindings.get("comparison_jury_receipt_path") != expected_path
        or result_bindings.get("comparison_jury_receipt_sha256") != expected_hash
    ):
        raise ProgramFoundryGepaAdjudicatorDispatchIndeterminateError(
            "deterministic adjudication committed for different jury lineage"
        )


def _dispatch_program_foundry_gepa_comparison_adjudicator(
    *,
    comparison_jury_receipt_path: Path,
    registration_paths: Sequence[Path] = (),
    include_builtin_fallback: bool = True,
) -> dict[str, Any]:
    """Persist one dispatch request and execute only the trusted deterministic backend."""

    jury_receipt_path = _lexical_path(comparison_jury_receipt_path)
    root = jury_receipt_path.parent.parent
    registration_entries, registrations = _registration_snapshot(registration_paths)
    try:
        selection = select_task_adjudicator(
            task_kind=FOUNDRY_GEPA_COMPARISON_TASK_KIND,
            registrations=registrations,
            include_builtin_fallback=include_builtin_fallback,
        )
    except ProgramAdjudicatorProtocolError as exc:
        raise ProgramFoundryGepaAdjudicatorDispatchError(str(exc)) from exc
    request_path = jury_receipt_path.parent / "comparison-adjudicator-request.json"
    with foundry_lock(root) as root_descriptor:
        try:
            validated_jury = (
                validate_successful_program_foundry_gepa_comparison_jury_receipt(
                    jury_receipt_path,
                    root_descriptor=root_descriptor,
                )
            )
        except ProgramFoundryGepaComparisonJuryError as exc:
            raise ProgramFoundryGepaAdjudicatorDispatchError(str(exc)) from exc
        expected = _request_payload(
            validated_jury=validated_jury,
            registration_entries=registration_entries,
            selection=selection,
            include_builtin_fallback=include_builtin_fallback,
        )
        if request_path.exists() or request_path.is_symlink():
            existing = read_stable_json_artifact(
                request_path,
                label="foundry adjudicator request",
                error_type=ProgramFoundryGepaAdjudicatorDispatchError,
            ).payload
            if existing != expected:
                raise ProgramFoundryGepaAdjudicatorDispatchError(
                    "foundry adjudicator request or bound inputs drifted"
                )
            request = existing
        else:

            def precommit() -> None:
                _load_current_registrations(registration_entries)
                try:
                    current = validate_successful_program_foundry_gepa_comparison_jury_receipt(
                        jury_receipt_path,
                        root_descriptor=root_descriptor,
                    )
                except ProgramFoundryGepaComparisonJuryError as exc:
                    raise ProgramFoundryGepaAdjudicatorDispatchError(str(exc)) from exc
                if current != validated_jury:
                    raise ProgramFoundryGepaAdjudicatorDispatchError(
                        "comparison jury lineage changed during adjudicator dispatch"
                    )

            atomic_publish_bytes(
                request_path,
                _pretty_json(expected),
                label="foundry adjudicator request",
                precommit=precommit,
                error_type=ProgramFoundryGepaAdjudicatorDispatchError,
                indeterminate_error_type=ProgramFoundryGepaAdjudicatorDispatchIndeterminateError,
                replace_existing=False,
            )
            try:
                request = read_stable_json_artifact(
                    request_path,
                    label="foundry adjudicator request",
                    error_type=ProgramFoundryGepaAdjudicatorDispatchError,
                ).payload
            except ProgramFoundryGepaAdjudicatorDispatchError as exc:
                raise ProgramFoundryGepaAdjudicatorDispatchIndeterminateError(
                    "foundry adjudicator request committed but cannot be revalidated"
                ) from exc
            if request != expected:
                raise ProgramFoundryGepaAdjudicatorDispatchIndeterminateError(
                    "foundry adjudicator request committed with unexpected bytes"
                )
    selected = request.get("selected_adjudicator")
    deterministic_result: dict[str, Any] | None = None
    builtin = builtin_foundry_deterministic_registration()
    if request.get("status") == "ready" and selected == builtin:
        try:
            deterministic_result = adjudicate_program_foundry_gepa_comparison(
                comparison_jury_receipt_path=jury_receipt_path,
            )
        except ProgramFoundryGepaComparisonAdjudicationIndeterminateError as exc:
            raise ProgramFoundryGepaAdjudicatorDispatchIndeterminateError(
                str(exc)
            ) from exc
        except ProgramFoundryGepaComparisonAdjudicationError as exc:
            raise ProgramFoundryGepaAdjudicatorDispatchError(str(exc)) from exc
        try:
            with foundry_lock(root) as root_descriptor:
                persisted_request = read_stable_json_artifact(
                    request_path,
                    label="foundry adjudicator request",
                    error_type=ProgramFoundryGepaAdjudicatorDispatchIndeterminateError,
                ).payload
                if persisted_request != request:
                    raise ProgramFoundryGepaAdjudicatorDispatchIndeterminateError(
                        "adjudicator request changed while deterministic adjudication ran"
                    )
                current_jury = (
                    validate_successful_program_foundry_gepa_comparison_jury_receipt(
                        jury_receipt_path,
                        root_descriptor=root_descriptor,
                    )
                )
                result_path = jury_receipt_path.parent / "comparison-adjudication.json"
                persisted_result = read_stable_json_artifact(
                    result_path,
                    label="foundry deterministic adjudication",
                    error_type=ProgramFoundryGepaAdjudicatorDispatchIndeterminateError,
                ).payload
                returned_canonical = {
                    key: value
                    for key, value in deterministic_result.items()
                    if key != "reused"
                }
                if persisted_result != returned_canonical:
                    raise ProgramFoundryGepaAdjudicatorDispatchIndeterminateError(
                        "deterministic adjudication changed before dispatch completion"
                    )
                _validate_deterministic_result_binding(
                    request=persisted_request,
                    result=persisted_result,
                    current_jury=current_jury,
                )
                deterministic_result = {
                    **persisted_result,
                    "reused": deterministic_result.get("reused", False),
                }
        except ProgramFoundryGepaAdjudicatorDispatchIndeterminateError:
            raise
        except Exception as exc:
            raise ProgramFoundryGepaAdjudicatorDispatchIndeterminateError(
                "deterministic adjudication committed but completion validation failed"
            ) from exc
    return _dispatch_envelope(
        request=request,
        request_path=request_path,
        deterministic_result=deterministic_result,
    )


def dispatch_program_foundry_gepa_comparison_adjudicator(
    *,
    comparison_jury_receipt_path: Path,
    registration_paths: Sequence[Path] = (),
    include_builtin_fallback: bool = True,
) -> dict[str, Any]:
    """Dispatch with commit-aware classification for request lock failures."""

    receipt_path = _lexical_path(comparison_jury_receipt_path)
    request_path = receipt_path.parent / "comparison-adjudicator-request.json"
    existed_before = request_path.exists() or request_path.is_symlink()
    try:
        return _dispatch_program_foundry_gepa_comparison_adjudicator(
            comparison_jury_receipt_path=receipt_path,
            registration_paths=registration_paths,
            include_builtin_fallback=include_builtin_fallback,
        )
    except ProgramFoundryGepaAdjudicatorDispatchIndeterminateError:
        raise
    except Exception as exc:
        if not existed_before and (request_path.exists() or request_path.is_symlink()):
            raise ProgramFoundryGepaAdjudicatorDispatchIndeterminateError(
                "foundry adjudicator request may have committed before lock release"
            ) from exc
        if isinstance(exc, ProgramFoundryGepaAdjudicatorDispatchError):
            raise
        raise ProgramFoundryGepaAdjudicatorDispatchError(str(exc)) from exc
