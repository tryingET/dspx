# summary: "Records asynchronous human adjudicator claims as receipt-bound unverified evidence that cannot satisfy quorum."
# read_when:
#   - "Changing human/panel adjudicator submissions, identity claims, quorum boundaries, or submission receipts."

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
from dspx.services.program_adjudicator_protocol import SHARED_ADJUDICATOR_DISPOSITIONS
from dspx.services.program_foundry_gepa_adjudicator_dispatch import (
    ProgramFoundryGepaAdjudicatorDispatchError,
    validate_program_foundry_gepa_adjudicator_request,
)
from dspx.services.program_foundry_io import foundry_lock

PROGRAM_FOUNDRY_GEPA_ADJUDICATOR_SUBMISSION_SCHEMA = (
    "dspx-program-foundry-gepa-adjudicator-submission-v1"
)
_ALLOWED_SUBMISSION_DISPOSITIONS = frozenset(SHARED_ADJUDICATOR_DISPOSITIONS) - {
    "pending"
}
_HUMAN_SUBMISSION_BACKENDS = frozenset({"human", "human_panel", "hybrid"})


class ProgramFoundryGepaAdjudicatorSubmissionError(ValueError):
    """Raised when an asynchronous human submission cannot be recorded safely."""


class ProgramFoundryGepaAdjudicatorSubmissionIndeterminateError(
    ProgramFoundryGepaAdjudicatorSubmissionError
):
    """Raised when an unverified submission receipt may already have committed."""


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
        raise ProgramFoundryGepaAdjudicatorSubmissionError(
            f"adjudicator submission must be canonical JSON: {exc}"
        ) from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _lexical(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _subject_kind(selected: Mapping[str, Any], subject: str) -> str:
    identity = selected.get("identity_claims")
    if not isinstance(identity, Mapping):
        raise ProgramFoundryGepaAdjudicatorSubmissionError(
            "selected adjudicator identity claims are missing"
        )
    subjects = identity.get("subjects")
    kinds = identity.get("subject_kinds")
    if not isinstance(subjects, list) or not isinstance(kinds, list):
        raise ProgramFoundryGepaAdjudicatorSubmissionError(
            "selected adjudicator subject declarations are invalid"
        )
    matches = [index for index, label in enumerate(subjects) if label == subject]
    if len(matches) != 1 or matches[0] >= len(kinds):
        raise ProgramFoundryGepaAdjudicatorSubmissionError(
            "submission subject is not declared by the selected adjudicator"
        )
    kind = kinds[matches[0]]
    if kind != "human":
        raise ProgramFoundryGepaAdjudicatorSubmissionError(
            "this submission recorder accepts only declared human subjects"
        )
    return str(kind)


def _submission_payload(
    *,
    validated_request: Mapping[str, Any],
    subject: str,
    disposition: str,
) -> tuple[dict[str, Any], str]:
    request = validated_request["request"]
    selected = request.get("selected_adjudicator")
    if request.get("status") != "pending" or not isinstance(selected, Mapping):
        raise ProgramFoundryGepaAdjudicatorSubmissionError(
            "human submission requires a pending selected adjudicator request"
        )
    backend = selected.get("backend")
    backend_kind = backend.get("kind") if isinstance(backend, Mapping) else None
    if backend_kind not in _HUMAN_SUBMISSION_BACKENDS:
        raise ProgramFoundryGepaAdjudicatorSubmissionError(
            "selected adjudicator does not accept human submissions"
        )
    normalized_subject = str(subject).strip()
    if not normalized_subject:
        raise ProgramFoundryGepaAdjudicatorSubmissionError(
            "submission subject label is required"
        )
    normalized_disposition = str(disposition).strip()
    if normalized_disposition not in _ALLOWED_SUBMISSION_DISPOSITIONS:
        raise ProgramFoundryGepaAdjudicatorSubmissionError(
            "submission disposition must be promote_locally, reject_locally, require_review, or abstain"
        )
    kind = _subject_kind(selected, normalized_subject)
    bindings = request["bindings"]
    body = {
        "schema_version": PROGRAM_FOUNDRY_GEPA_ADJUDICATOR_SUBMISSION_SCHEMA,
        "status": "recorded_unverified",
        "request": {
            "path": str(validated_request["request_path"]),
            "request_id": request["request_id"],
            "sha256": validated_request["request_sha256"],
        },
        "lineage": {
            "proposal_id": request["proposal_id"],
            "comparison_jury_receipt_path": bindings["comparison_jury_receipt_path"],
            "comparison_jury_receipt_sha256": bindings[
                "comparison_jury_receipt_sha256"
            ],
            "registration_id": selected["registration_id"],
            "registration_snapshot_sha256": bindings["registration_snapshot_sha256"],
            "selection_sha256": bindings["selection_sha256"],
        },
        "subject_claim": {
            "label": normalized_subject,
            "kind": kind,
            "assertion_mode": "caller_declared",
            "authenticated": False,
            "membership_verified": False,
            "participation_verified": False,
            "signature_verified": False,
            "verifier_receipt": None,
        },
        "submission": {"disposition_claim": normalized_disposition},
        "effect": {
            "recorded_unverified_evidence": True,
            "counts_toward_quorum": False,
            "quorum_satisfied": False,
            "adjudication_completed": False,
            "transition_allowed": False,
            "candidate_mutated": False,
            "production_activation": False,
            "governance_mutated": False,
            "external_apply": False,
        },
        "non_authority": {
            "identity_authentication": False,
            "membership_verification": False,
            "participation_verification": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
        },
    }
    submission_id = _sha256(_canonical_json(body))
    receipt = {**body, "submission_id": submission_id}
    subject_key = _sha256(
        _canonical_json(
            {
                "request_id": request["request_id"],
                "registration_id": selected["registration_id"],
                "subject": normalized_subject,
            }
        )
    )
    return receipt, subject_key


def _record_program_foundry_gepa_adjudicator_submission(
    *,
    request_path: Path,
    registration_paths: Sequence[Path],
    declared_request_id: str,
    subject: str,
    disposition: str,
    commit_state: dict[str, Any],
) -> dict[str, Any]:
    lexical_request = _lexical(request_path)
    root = lexical_request.parent.parent
    with foundry_lock(root) as root_descriptor:
        try:
            validated_request = validate_program_foundry_gepa_adjudicator_request(
                lexical_request,
                root_descriptor=root_descriptor,
                registration_paths=registration_paths,
            )
        except ProgramFoundryGepaAdjudicatorDispatchError as exc:
            raise ProgramFoundryGepaAdjudicatorSubmissionError(str(exc)) from exc
        if validated_request["request"].get("request_id") != declared_request_id:
            raise ProgramFoundryGepaAdjudicatorSubmissionError(
                "declared request id does not match the persisted adjudicator request"
            )
        receipt, subject_key = _submission_payload(
            validated_request=validated_request,
            subject=subject,
            disposition=disposition,
        )
        output_path = (
            lexical_request.parent
            / "comparison-adjudicator-submissions"
            / f"{subject_key}.json"
        )
        commit_state["output_path"] = output_path
        if output_path.exists() or output_path.is_symlink():
            existing = read_stable_json_artifact(
                output_path,
                label="foundry adjudicator submission",
                error_type=ProgramFoundryGepaAdjudicatorSubmissionError,
            ).payload
            if existing != receipt:
                raise ProgramFoundryGepaAdjudicatorSubmissionError(
                    "adjudicator subject already has a different recorded submission"
                )
            return {**existing, "reused": True, "path": str(output_path)}

        def precommit() -> None:
            try:
                current = validate_program_foundry_gepa_adjudicator_request(
                    lexical_request,
                    root_descriptor=root_descriptor,
                    registration_paths=registration_paths,
                )
            except ProgramFoundryGepaAdjudicatorDispatchError as exc:
                raise ProgramFoundryGepaAdjudicatorSubmissionError(str(exc)) from exc
            if current != validated_request:
                raise ProgramFoundryGepaAdjudicatorSubmissionError(
                    "adjudicator request changed during submission recording"
                )

        atomic_publish_bytes(
            output_path,
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True).encode(
                "utf-8"
            )
            + b"\n",
            label="foundry adjudicator submission",
            precommit=precommit,
            error_type=ProgramFoundryGepaAdjudicatorSubmissionError,
            indeterminate_error_type=ProgramFoundryGepaAdjudicatorSubmissionIndeterminateError,
            replace_existing=False,
        )
        commit_state["committed"] = True
        try:
            persisted = read_stable_json_artifact(
                output_path,
                label="foundry adjudicator submission",
                error_type=ProgramFoundryGepaAdjudicatorSubmissionError,
            ).payload
        except ProgramFoundryGepaAdjudicatorSubmissionError as exc:
            raise ProgramFoundryGepaAdjudicatorSubmissionIndeterminateError(
                "adjudicator submission committed but cannot be revalidated"
            ) from exc
        if persisted != receipt:
            raise ProgramFoundryGepaAdjudicatorSubmissionIndeterminateError(
                "adjudicator submission committed with unexpected bytes"
            )
        return {**persisted, "reused": False, "path": str(output_path)}


def record_program_foundry_gepa_adjudicator_submission(
    *,
    request_path: Path,
    registration_paths: Sequence[Path],
    declared_request_id: str,
    subject: str,
    disposition: str,
) -> dict[str, Any]:
    """Record an unverified submission with commit-aware lock failure handling."""

    lexical_request = _lexical(request_path)
    commit_state: dict[str, Any] = {"committed": False, "output_path": None}
    try:
        return _record_program_foundry_gepa_adjudicator_submission(
            request_path=lexical_request,
            registration_paths=registration_paths,
            declared_request_id=declared_request_id,
            subject=subject,
            disposition=disposition,
            commit_state=commit_state,
        )
    except ProgramFoundryGepaAdjudicatorSubmissionIndeterminateError:
        raise
    except Exception as exc:
        if commit_state["committed"] is True:
            raise ProgramFoundryGepaAdjudicatorSubmissionIndeterminateError(
                "adjudicator submission may have committed before lock release"
            ) from exc
        if isinstance(exc, ProgramFoundryGepaAdjudicatorSubmissionError):
            raise
        raise ProgramFoundryGepaAdjudicatorSubmissionError(str(exc)) from exc
