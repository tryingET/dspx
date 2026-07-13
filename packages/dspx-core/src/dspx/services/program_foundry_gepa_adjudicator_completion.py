# summary: "Imports one signed, receipt-bound adjudicator completion under a digest-pinned trust policy."
# read_when: "Changing completion import persistence, trust-policy rebinding, or terminal receipts."
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from dspx.services.program_adjudicator_protocol import (
    ProgramAdjudicatorProtocolError,
    validate_task_adjudicator_registration,
)

from dspx.services.artifact_boundary import (
    StableJsonArtifact,
    atomic_publish_bytes,
    read_stable_json_artifact,
)
from dspx.services.program_foundry_gepa_adjudicator_completion_contract import (
    PROGRAM_FOUNDRY_GEPA_ADJUDICATOR_COMPLETION_SCHEMA,
    ProgramFoundryGepaAdjudicatorCompletionError,
    canonical_completion_json,
    expected_adjudicator_request_binding,
    validate_owner_verified_adjudicator_completion,
)
from dspx.services.program_foundry_gepa_adjudicator_dispatch import (
    ProgramFoundryGepaAdjudicatorDispatchError,
    validate_program_foundry_gepa_adjudicator_request,
)
from dspx.services.program_foundry_io import foundry_lock


class ProgramFoundryGepaAdjudicatorCompletionIndeterminateError(
    ProgramFoundryGepaAdjudicatorCompletionError
):
    """Raised when a terminal completion receipt may already have committed."""


def _pretty_json(value: Mapping[str, Any]) -> bytes:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: object) -> str:
    return _sha256(canonical_completion_json(value))


def _lexical(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parsed_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ProgramFoundryGepaAdjudicatorCompletionError(f"{label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            f"{label} is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProgramFoundryGepaAdjudicatorCompletionError(f"{label} is invalid")
    return parsed


def _completion_payload(
    *,
    source_path: Path,
    source: StableJsonArtifact,
    trust_policy_path: Path,
    trust_policy: StableJsonArtifact,
    validated_request: Mapping[str, Any],
    verified_at: str,
    verified: Mapping[str, Any],
) -> dict[str, Any]:
    request = validated_request["request"]
    selected = request["selected_adjudicator"]
    quorum = verified["quorum"]
    policy = verified["trust_policy"]
    body = {
        "schema_version": PROGRAM_FOUNDRY_GEPA_ADJUDICATOR_COMPLETION_SCHEMA,
        "status": "completed",
        "disposition": quorum["disposition"],
        "source": {
            "path": str(source_path),
            "sha256": source.sha256,
            "canonical_sha256": _canonical_sha256(source.payload),
            "owner_receipt_id": verified["owner_receipt_id"],
            "signed_payload_digest": verified["signed_payload_digest"],
            "receipt": dict(source.payload),
        },
        "trust_policy": {
            "path": str(trust_policy_path),
            "sha256": trust_policy.sha256,
            "canonical_sha256": _canonical_sha256(trust_policy.payload),
            "policy_id": policy["policy_id"],
            "observed_at": policy["observed_at"],
            "expires_at": policy["expires_at"],
            "policy": dict(trust_policy.payload),
        },
        "request": {
            "path": str(validated_request["request_path"]),
            "request_id": request["request_id"],
            "sha256": validated_request["request_sha256"],
            "canonical_sha256": _canonical_sha256(request),
            "snapshot": dict(request),
        },
        "lineage": expected_adjudicator_request_binding(
            request, validated_request["request_sha256"]
        ),
        "selected_adjudicator": {
            "registration_id": selected["registration_id"],
            "backend_kind": selected["backend"]["kind"],
        },
        "verifier": {
            "owner": verified["verifier"]["owner"],
            "implementation_id": verified["verifier"]["implementation_id"],
            "protocol_version": verified["verifier"]["protocol_version"],
            "key_id": verified["verifier"]["key_id"],
            "public_key_sha256": _sha256(
                base64.b64decode(verified["verifier"]["public_key_b64"], validate=True)
            ),
            "key_status": verified["verifier"]["key_status"],
            "valid_from": verified["verifier"]["valid_from"],
            "valid_until": verified["verifier"]["valid_until"],
            "verified_at": verified_at,
            "trust_source": "externally_digest_pinned_scoped_policy",
            "embedded_declaration_is_trust_root": False,
            "signature_validated_by_dspx": True,
            "verifier_identity_authenticated_by_dspx": False,
        },
        "claims": list(verified["claims"]),
        "quorum": dict(quorum),
        "unverified_submission_policy": {
            "prior_unverified_submissions_consulted": False,
            "prior_unverified_submissions_counted": False,
            "conflicts_resolved_by_dspx": False,
            "rule": "signed_owner_completion_is_independent_terminal_evidence",
        },
        "effect": {
            "externally_verified_evidence_imported": True,
            "verified_claims_counted_toward_quorum": True,
            "quorum_satisfied": quorum["quorum_satisfied"],
            "adjudication_completed": True,
            "bounded_local_disposition_recorded": True,
            "candidate_mutated": False,
            "production_activation": False,
            "governance_mutated": False,
            "external_apply": False,
        },
        "non_authority": {
            "social_identity_authenticated_by_dspx": False,
            "society_membership_authenticated_by_dspx": False,
            "production_promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
            "external_apply_authority": False,
        },
    }
    return {**body, "completion_id": _sha256(canonical_completion_json(body))}


def _read_external_artifact(path: Path, *, label: str) -> StableJsonArtifact:
    return read_stable_json_artifact(
        path,
        label=label,
        error_type=ProgramFoundryGepaAdjudicatorCompletionError,
        max_bytes=1024 * 1024,
    )


def _validate_inputs(
    *,
    lexical_request: Path,
    lexical_source: Path,
    lexical_policy: Path,
    root_descriptor: int,
    registration_paths: Sequence[Path],
    declared_request_id: str,
    expected_owner_receipt_id: str,
    trusted_policy_sha256: str,
    verification_time: datetime,
) -> tuple[dict[str, Any], StableJsonArtifact, StableJsonArtifact, dict[str, Any]]:
    try:
        validated_request = validate_program_foundry_gepa_adjudicator_request(
            lexical_request,
            root_descriptor=root_descriptor,
            registration_paths=registration_paths,
        )
    except ProgramFoundryGepaAdjudicatorDispatchError as exc:
        raise ProgramFoundryGepaAdjudicatorCompletionError(str(exc)) from exc
    if validated_request["request"].get("request_id") != declared_request_id:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "declared request id does not match the persisted adjudicator request"
        )
    source = _read_external_artifact(
        lexical_source, label="owner-verified adjudicator completion"
    )
    policy = _read_external_artifact(
        lexical_policy, label="adjudicator verifier trust policy"
    )
    verified = validate_owner_verified_adjudicator_completion(
        source.payload,
        request=validated_request["request"],
        request_sha256=validated_request["request_sha256"],
        expected_owner_receipt_id=expected_owner_receipt_id,
        trust_policy=policy.payload,
        trust_policy_sha256=_canonical_sha256(policy.payload),
        trusted_policy_sha256=trusted_policy_sha256,
        verification_time=verification_time,
    )
    return validated_request, source, policy, verified


def _reuse_existing_completion(
    *,
    existing: Mapping[str, Any],
    lexical_request: Path,
    lexical_source: Path,
    lexical_policy: Path,
    trusted_policy_sha256: str,
    declared_request_id: str,
    expected_owner_receipt_id: str,
    output_path: Path,
) -> dict[str, Any]:
    request_section = existing.get("request")
    source_section = existing.get("source")
    policy_section = existing.get("trust_policy")
    verifier_section = existing.get("verifier")
    if not all(
        isinstance(item, Mapping)
        for item in (request_section, source_section, policy_section, verifier_section)
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "persisted adjudicator completion has incomplete embedded evidence"
        )
    assert isinstance(request_section, Mapping)
    assert isinstance(source_section, Mapping)
    assert isinstance(policy_section, Mapping)
    assert isinstance(verifier_section, Mapping)
    request_snapshot = request_section.get("snapshot")
    source_payload = source_section.get("receipt")
    policy_payload = policy_section.get("policy")
    if not all(
        isinstance(item, Mapping)
        for item in (request_snapshot, source_payload, policy_payload)
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "persisted adjudicator completion snapshots are invalid"
        )
    request_canonical_sha256 = _canonical_sha256(request_snapshot)
    source_canonical_sha256 = _canonical_sha256(source_payload)
    policy_canonical_sha256 = _canonical_sha256(policy_payload)
    if (
        request_section.get("path") != str(lexical_request)
        or request_section.get("request_id") != declared_request_id
        or request_section.get("canonical_sha256") != request_canonical_sha256
        or source_section.get("path") != str(lexical_source)
        or source_section.get("owner_receipt_id") != expected_owner_receipt_id
        or source_section.get("canonical_sha256") != source_canonical_sha256
        or policy_section.get("path") != str(lexical_policy)
        or policy_section.get("canonical_sha256") != policy_canonical_sha256
        or policy_canonical_sha256 != trusted_policy_sha256
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "persisted adjudicator completion does not match explicit import inputs or canonical evidence digests"
        )
    request_copy = dict(request_snapshot)
    snapshot_request_id = request_copy.pop("request_id", None)
    if (
        snapshot_request_id != declared_request_id
        or _canonical_sha256(request_copy) != snapshot_request_id
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "persisted adjudicator request snapshot id is invalid"
        )
    selected = request_snapshot.get("selected_adjudicator")
    if not isinstance(selected, Mapping):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "persisted adjudicator request selection is invalid"
        )
    try:
        validate_task_adjudicator_registration(selected)
    except ProgramAdjudicatorProtocolError as exc:
        raise ProgramFoundryGepaAdjudicatorCompletionError(str(exc)) from exc
    verified_at = verifier_section.get("verified_at")
    verified_time = _parsed_utc(verified_at, "persisted verifier verified_at")
    request_sha256 = request_section.get("sha256")
    source_sha256 = source_section.get("sha256")
    policy_source_sha256 = policy_section.get("sha256")
    if not all(
        isinstance(item, str)
        for item in (request_sha256, source_sha256, policy_source_sha256)
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "persisted adjudicator completion source hashes are invalid"
        )
    verified = validate_owner_verified_adjudicator_completion(
        source_payload,
        request=request_snapshot,
        request_sha256=request_sha256,
        expected_owner_receipt_id=expected_owner_receipt_id,
        trust_policy=policy_payload,
        trust_policy_sha256=policy_canonical_sha256,
        trusted_policy_sha256=trusted_policy_sha256,
        verification_time=verified_time,
    )
    expected = _completion_payload(
        source_path=lexical_source,
        source=StableJsonArtifact(
            path=lexical_source,
            sha256=source_sha256,
            payload=dict(source_payload),
        ),
        trust_policy_path=lexical_policy,
        trust_policy=StableJsonArtifact(
            path=lexical_policy,
            sha256=policy_source_sha256,
            payload=dict(policy_payload),
        ),
        validated_request={
            "request": dict(request_snapshot),
            "request_path": lexical_request,
            "request_sha256": request_sha256,
        },
        verified_at=str(verified_at),
        verified=verified,
    )
    if dict(existing) != expected:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "persisted adjudicator completion failed embedded evidence validation"
        )
    return {**expected, "reused": True, "path": str(output_path)}


def _import_program_foundry_gepa_adjudicator_completion(
    *,
    request_path: Path,
    registration_paths: Sequence[Path],
    owner_completion_path: Path,
    verifier_policy_path: Path,
    trusted_policy_sha256: str,
    declared_request_id: str,
    expected_owner_receipt_id: str,
    commit_state: dict[str, Any],
) -> dict[str, Any]:
    lexical_request = _lexical(request_path)
    lexical_source = _lexical(owner_completion_path)
    lexical_policy = _lexical(verifier_policy_path)
    root = lexical_request.parent.parent
    output_path = lexical_request.parent / "comparison-adjudicator-completion.json"
    if len({lexical_request, lexical_source, lexical_policy, output_path}) != 4:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "request, owner completion, verifier policy, and terminal output must be distinct"
        )
    with foundry_lock(root) as root_descriptor:
        commit_state["output_path"] = output_path
        if output_path.exists() or output_path.is_symlink():
            existing = read_stable_json_artifact(
                output_path,
                label="foundry adjudicator completion",
                error_type=ProgramFoundryGepaAdjudicatorCompletionError,
            ).payload
            return _reuse_existing_completion(
                existing=existing,
                lexical_request=lexical_request,
                lexical_source=lexical_source,
                lexical_policy=lexical_policy,
                trusted_policy_sha256=trusted_policy_sha256,
                declared_request_id=declared_request_id,
                expected_owner_receipt_id=expected_owner_receipt_id,
                output_path=output_path,
            )

        verified_time = _utc_now()
        validated_request, source, policy, verified = _validate_inputs(
            lexical_request=lexical_request,
            lexical_source=lexical_source,
            lexical_policy=lexical_policy,
            root_descriptor=root_descriptor,
            registration_paths=registration_paths,
            declared_request_id=declared_request_id,
            expected_owner_receipt_id=expected_owner_receipt_id,
            trusted_policy_sha256=trusted_policy_sha256,
            verification_time=verified_time,
        )
        receipt = _completion_payload(
            source_path=lexical_source,
            source=source,
            trust_policy_path=lexical_policy,
            trust_policy=policy,
            validated_request=validated_request,
            verified_at=_utc_text(verified_time),
            verified=verified,
        )

        def revalidate() -> None:
            current_time = _utc_now()
            if current_time < verified_time:
                raise ProgramFoundryGepaAdjudicatorCompletionError(
                    "system clock moved backward during adjudicator completion import"
                )
            try:
                current = _validate_inputs(
                    lexical_request=lexical_request,
                    lexical_source=lexical_source,
                    lexical_policy=lexical_policy,
                    root_descriptor=root_descriptor,
                    registration_paths=registration_paths,
                    declared_request_id=declared_request_id,
                    expected_owner_receipt_id=expected_owner_receipt_id,
                    trusted_policy_sha256=trusted_policy_sha256,
                    verification_time=current_time,
                )
            except ProgramFoundryGepaAdjudicatorCompletionError as exc:
                raise ProgramFoundryGepaAdjudicatorCompletionError(
                    "adjudicator request, owner completion, or trust policy changed during import"
                ) from exc
            if current != (validated_request, source, policy, verified):
                raise ProgramFoundryGepaAdjudicatorCompletionError(
                    "adjudicator request, owner completion, or trust policy changed during import"
                )

        atomic_publish_bytes(
            output_path,
            _pretty_json(receipt),
            label="foundry adjudicator completion",
            precommit=revalidate,
            error_type=ProgramFoundryGepaAdjudicatorCompletionError,
            indeterminate_error_type=ProgramFoundryGepaAdjudicatorCompletionIndeterminateError,
            replace_existing=False,
        )
        commit_state["committed"] = True
        try:
            persisted = read_stable_json_artifact(
                output_path,
                label="foundry adjudicator completion",
                error_type=ProgramFoundryGepaAdjudicatorCompletionError,
            ).payload
        except ProgramFoundryGepaAdjudicatorCompletionError as exc:
            raise ProgramFoundryGepaAdjudicatorCompletionIndeterminateError(
                "adjudicator completion committed but cannot be reread"
            ) from exc
        if persisted != receipt:
            raise ProgramFoundryGepaAdjudicatorCompletionIndeterminateError(
                "adjudicator completion committed with unexpected bytes"
            )
        return {**persisted, "reused": False, "path": str(output_path)}


def import_program_foundry_gepa_adjudicator_completion(
    *,
    request_path: Path,
    registration_paths: Sequence[Path],
    owner_completion_path: Path,
    verifier_policy_path: Path,
    trusted_policy_sha256: str,
    declared_request_id: str,
    expected_owner_receipt_id: str,
) -> dict[str, Any]:
    """Import one terminal completion under an independently digest-pinned policy."""

    commit_state: dict[str, Any] = {"committed": False, "output_path": None}
    try:
        return _import_program_foundry_gepa_adjudicator_completion(
            request_path=request_path,
            registration_paths=registration_paths,
            owner_completion_path=owner_completion_path,
            verifier_policy_path=verifier_policy_path,
            trusted_policy_sha256=trusted_policy_sha256,
            declared_request_id=declared_request_id,
            expected_owner_receipt_id=expected_owner_receipt_id,
            commit_state=commit_state,
        )
    except ProgramFoundryGepaAdjudicatorCompletionIndeterminateError:
        raise
    except Exception as exc:
        if commit_state["committed"] is True:
            raise ProgramFoundryGepaAdjudicatorCompletionIndeterminateError(
                "adjudicator completion may have committed before lock release"
            ) from exc
        if isinstance(exc, ProgramFoundryGepaAdjudicatorCompletionError):
            raise
        raise ProgramFoundryGepaAdjudicatorCompletionError(str(exc)) from exc
