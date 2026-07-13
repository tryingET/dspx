# summary: "Tests signed owner completion import, trust pins, exact lineage, quorum, and terminal durability."

from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import program_adjudicator_protocol as protocol
import dspx.services.program_foundry_gepa_adjudicator_completion as completion
from dspx.services.program_foundry_gepa_adjudicator_completion_contract import (
    OWNER_VERIFIED_ADJUDICATOR_COMPLETION_SCHEMA,
    ProgramFoundryGepaAdjudicatorCompletionError,
    canonical_completion_json,
    expected_adjudicator_request_binding,
)
from dspx.services.program_foundry_gepa_adjudicator_completion_trust import (
    ADJUDICATOR_VERIFIER_TRUST_POLICY_SCHEMA,
)

_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
_PUBLIC_KEY_B64 = base64.b64encode(
    _PRIVATE_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
).decode("ascii")
_VALID_FROM = "2026-01-01T00:00:00Z"
_VALID_UNTIL = "2027-01-01T00:00:00Z"
_VERIFICATION_TIME = datetime.fromisoformat("2026-07-13T18:30:00+00:00")
_RECEIPT_ID = "owner-completion-001"


def _request_fixture(
    tmp_path: Path,
    *,
    kind: str = "human_panel",
    subjects: list[str] | None = None,
    subject_kinds: list[str] | None = None,
    quorum_mode: str = "unanimous",
    quorum_required: int | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    root = tmp_path / "foundry"
    experiment = root / "gepa-experiment"
    experiment.mkdir(parents=True)
    subjects = subjects or ["person-a", "person-b"]
    registration = protocol.build_task_adjudicator_registration(
        task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        kind=kind,
        implementation_id=f"{kind}-owner-adapter",
        subjects=subjects,
        subject_kinds=subject_kinds,
        quorum_mode=quorum_mode if len(subjects) > 1 else None,
        quorum_required=quorum_required,
    )
    registration_path = experiment / "adjudicator-registration.json"
    registration_path.write_text(json.dumps(registration), encoding="utf-8")
    request_path = experiment / "comparison-adjudicator-request.json"
    request = {
        "schema_version": "dspx-program-foundry-gepa-adjudicator-request-v1",
        "status": "pending",
        "proposal_id": "p" * 64,
        "task_kind": protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        "selected_adjudicator": registration,
        "bindings": {
            "comparison_jury_receipt_sha256": "a" * 64,
            "jury_results_sha256": "b" * 64,
            "candidate_manifest_sha256": "c" * 64,
            "comparison_sha256": "d" * 64,
            "registration_snapshot_sha256": "e" * 64,
            "selection_sha256": "f" * 64,
        },
    }
    request["request_id"] = hashlib.sha256(
        canonical_completion_json(request)
    ).hexdigest()
    request_path.write_text(json.dumps(request), encoding="utf-8")
    validated = {
        "request": request,
        "request_path": request_path,
        "request_sha256": "q" * 64,
        "validated_jury": {},
    }
    return request_path, registration_path, validated


def _claim(
    subject: str,
    kind: str,
    disposition: str,
    *,
    subject_signature_verified: bool = False,
) -> dict[str, Any]:
    return {
        "subject": subject,
        "subject_kind": kind,
        "disposition": disposition,
        "owner_verifier_assertions": {
            "identity_verified": True,
            "roster_membership_verified": True,
            "participation_verified": True,
            "disposition_attested": True,
            "subject_signature_verified": subject_signature_verified,
        },
    }


def _signed_owner_completion(
    validated: dict[str, Any],
    claims: list[dict[str, Any]],
    *,
    receipt_id: str = _RECEIPT_ID,
) -> dict[str, Any]:
    body = {
        "schema_version": OWNER_VERIFIED_ADJUDICATOR_COMPLETION_SCHEMA,
        "owner_receipt_id": receipt_id,
        "issued_at": "2026-07-13T18:00:00Z",
        "verification_scope": "dspx_foundry_gepa_adjudicator_completion",
        "request_binding": expected_adjudicator_request_binding(
            validated["request"], validated["request_sha256"]
        ),
        "verifier_evidence": {
            "owner": "example-owner",
            "implementation_id": "example-owner-verifier-v1",
            "protocol_version": "owner-adjudicator-completion-v1",
            "algorithm": "Ed25519",
            "key_id": "example-owner-key-1",
            "public_key_b64": _PUBLIC_KEY_B64,
            "key_status": "active",
            "valid_from": _VALID_FROM,
            "valid_until": _VALID_UNTIL,
            "declaration_is_trust_root": False,
        },
        "claims": claims,
        "authority_boundary": {
            "identity_verification_assertion": True,
            "participation_verification_assertion": True,
            "bounded_local_disposition_authority": False,
            "production_promotion": False,
            "activation": False,
            "governance": False,
            "external_apply": False,
        },
    }
    signed = canonical_completion_json(body)
    return {
        **body,
        "signature": {
            "algorithm": "Ed25519",
            "key_id": "example-owner-key-1",
            "signed_payload_digest": hashlib.sha256(signed).hexdigest(),
            "signature_b64": base64.b64encode(_PRIVATE_KEY.sign(signed)).decode(
                "ascii"
            ),
        },
    }


def _trust_policy(validated: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": ADJUDICATOR_VERIFIER_TRUST_POLICY_SCHEMA,
        "policy_id": "example-owner-policy-1",
        "observed_at": "2026-07-13T17:00:00Z",
        "expires_at": "2026-12-31T00:00:00Z",
        "verification_scope": "dspx_foundry_gepa_adjudicator_completion",
        "request_binding": {
            "request_id": validated["request"]["request_id"],
            "request_sha256": validated["request_sha256"],
            "request_canonical_sha256": hashlib.sha256(
                canonical_completion_json(validated["request"])
            ).hexdigest(),
            "task_kind": protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
            "registration_id": validated["request"]["selected_adjudicator"][
                "registration_id"
            ],
            "registration_snapshot_sha256": validated["request"]["bindings"][
                "registration_snapshot_sha256"
            ],
            "selection_sha256": validated["request"]["bindings"]["selection_sha256"],
        },
        "verifier_evidence": {
            "owner": "example-owner",
            "implementation_id": "example-owner-verifier-v1",
            "protocol_version": "owner-adjudicator-completion-v1",
            "algorithm": "Ed25519",
            "key_id": "example-owner-key-1",
            "public_key_b64": _PUBLIC_KEY_B64,
            "key_status": "active",
            "valid_from": _VALID_FROM,
            "valid_until": _VALID_UNTIL,
            "declaration_is_trust_root": False,
        },
        "authority_boundary": {
            "local_completion_trust_anchor": True,
            "social_identity_authority": False,
            "production_promotion": False,
            "activation": False,
            "governance": False,
            "external_apply": False,
        },
    }


def _write_owner_completion(
    tmp_path: Path, validated: dict[str, Any], claims: list[dict[str, Any]]
) -> Path:
    path = tmp_path / "owner-completion.json"
    path.write_text(
        json.dumps(_signed_owner_completion(validated, claims)), encoding="utf-8"
    )
    (tmp_path / "verifier-policy.json").write_text(
        json.dumps(_trust_policy(validated)), encoding="utf-8"
    )
    return path


def _install_request_validation(
    monkeypatch: pytest.MonkeyPatch, validated: dict[str, Any]
) -> None:
    monkeypatch.setattr(
        completion,
        "validate_program_foundry_gepa_adjudicator_request",
        lambda path, **kwargs: dict(validated),
    )
    monkeypatch.setattr(completion, "_utc_now", lambda: _VERIFICATION_TIME)


def _import(
    *, request_path: Path, registration_path: Path, owner_completion_path: Path
) -> dict[str, Any]:
    verifier_policy_path = owner_completion_path.parent / "verifier-policy.json"
    policy_payload = json.loads(verifier_policy_path.read_text(encoding="utf-8"))
    request_payload = json.loads(request_path.read_text(encoding="utf-8"))
    return completion.import_program_foundry_gepa_adjudicator_completion(
        request_path=request_path,
        registration_paths=[registration_path],
        owner_completion_path=owner_completion_path,
        verifier_policy_path=verifier_policy_path,
        trusted_policy_sha256=hashlib.sha256(
            canonical_completion_json(policy_payload)
        ).hexdigest(),
        declared_request_id=request_payload["request_id"],
        expected_owner_receipt_id=_RECEIPT_ID,
    )


def test_imports_and_reuses_unanimous_owner_verified_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(tmp_path)
    _install_request_validation(monkeypatch, validated)
    source = _write_owner_completion(
        tmp_path,
        validated,
        [
            _claim("person-a", "human", "promote_locally"),
            _claim("person-b", "human", "promote_locally"),
        ],
    )

    first = _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )
    second = _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )

    assert first["status"] == "completed"
    assert first["disposition"] == "promote_locally"
    assert first["quorum"]["quorum_satisfied"] is True
    assert first["quorum"]["participation_count"] == 2
    assert first["effect"]["bounded_local_disposition_recorded"] is True
    assert first["effect"]["candidate_mutated"] is False
    assert first["verifier"]["signature_validated_by_dspx"] is True
    assert first["verifier"]["verifier_identity_authenticated_by_dspx"] is False
    assert first["non_authority"]["society_membership_authenticated_by_dspx"] is False
    assert first["reused"] is False
    assert second["reused"] is True
    assert Path(first["path"]).stat().st_mode & 0o777 == 0o600
    assert first["verifier"]["verified_at"] == "2026-07-13T18:30:00Z"
    assert first["request"]["snapshot"] == validated["request"]
    assert (
        first["trust_policy"]["policy"]["request_binding"]["request_id"]
        == validated["request"]["request_id"]
    )


@pytest.mark.parametrize(
    ("kind", "subjects", "subject_kinds", "disposition"),
    [
        ("human", ["person-a"], None, "promote_locally"),
        (
            "multi_agent_panel",
            ["agent-a", "agent-b"],
            ["agent", "agent"],
            "reject_locally",
        ),
    ],
)
def test_single_human_and_multi_agent_completions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    subjects: list[str],
    subject_kinds: list[str] | None,
    disposition: str,
) -> None:
    request, registration, validated = _request_fixture(
        tmp_path,
        kind=kind,
        subjects=subjects,
        subject_kinds=subject_kinds,
    )
    _install_request_validation(monkeypatch, validated)
    claim_kind = "human" if kind == "human" else "agent"
    source = _write_owner_completion(
        tmp_path,
        validated,
        [_claim(subject, claim_kind, disposition) for subject in subjects],
    )

    result = _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )

    assert result["disposition"] == disposition
    assert result["quorum"]["quorum_satisfied"] is True


def test_threshold_tie_completes_as_require_review_without_quorum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(
        tmp_path,
        subjects=["a", "b", "c", "d"],
        quorum_mode="threshold",
        quorum_required=2,
    )
    _install_request_validation(monkeypatch, validated)
    source = _write_owner_completion(
        tmp_path,
        validated,
        [
            _claim("a", "human", "promote_locally"),
            _claim("b", "human", "promote_locally"),
            _claim("c", "human", "reject_locally"),
            _claim("d", "human", "reject_locally"),
        ],
    )

    result = _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )

    assert result["disposition"] == "require_review"
    assert result["quorum"]["quorum_satisfied"] is False
    assert result["quorum"]["reason"] == "ambiguous_quorum_dispositions"
    assert result["quorum"]["winning_dispositions"] == [
        "promote_locally",
        "reject_locally",
    ]


def test_hybrid_requires_and_accepts_cross_constituency_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(
        tmp_path,
        kind="hybrid",
        subjects=["person-a", "agent-a", "agent-b"],
        subject_kinds=["human", "agent", "agent"],
        quorum_mode="threshold",
        quorum_required=2,
    )
    _install_request_validation(monkeypatch, validated)
    source = _write_owner_completion(
        tmp_path,
        validated,
        [
            _claim("person-a", "human", "reject_locally"),
            _claim("agent-a", "agent", "reject_locally"),
            _claim("agent-b", "agent", "abstain"),
        ],
    )

    result = _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )

    assert result["disposition"] == "reject_locally"
    assert result["quorum"]["quorum_satisfied"] is True
    assert result["quorum"]["constituency_satisfied"] is True
    assert result["quorum"]["abstention_count"] == 1


def test_hybrid_same_constituency_threshold_fails_to_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(
        tmp_path,
        kind="hybrid",
        subjects=["person-a", "agent-a", "agent-b"],
        subject_kinds=["human", "agent", "agent"],
        quorum_mode="threshold",
        quorum_required=2,
    )
    _install_request_validation(monkeypatch, validated)
    source = _write_owner_completion(
        tmp_path,
        validated,
        [
            _claim("person-a", "human", "abstain"),
            _claim("agent-a", "agent", "promote_locally"),
            _claim("agent-b", "agent", "promote_locally"),
        ],
    )

    result = _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )

    assert result["disposition"] == "require_review"
    assert result["quorum"]["quorum_satisfied"] is False
    assert (
        result["quorum"]["reason"] == "hybrid_cross_constituency_quorum_not_satisfied"
    )


def test_rejects_partial_completion_and_unknown_subjects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(tmp_path)
    _install_request_validation(monkeypatch, validated)
    source = _write_owner_completion(
        tmp_path, validated, [_claim("person-a", "human", "abstain")]
    )
    with pytest.raises(
        ProgramFoundryGepaAdjudicatorCompletionError,
        match="exactly one claim for every",
    ):
        _import(
            request_path=request,
            registration_path=registration,
            owner_completion_path=source,
        )
    assert not (request.parent / "comparison-adjudicator-completion.json").exists()


def test_rejects_unverified_roster_membership_and_unpinned_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(tmp_path)
    _install_request_validation(monkeypatch, validated)
    claims = [
        _claim("person-a", "human", "promote_locally"),
        _claim("person-b", "human", "promote_locally"),
    ]
    claims[0]["owner_verifier_assertions"]["roster_membership_verified"] = False
    source = _write_owner_completion(tmp_path, validated, claims)
    policy = tmp_path / "verifier-policy.json"

    with pytest.raises(
        ProgramFoundryGepaAdjudicatorCompletionError,
        match="registered-roster membership",
    ):
        _import(
            request_path=request,
            registration_path=registration,
            owner_completion_path=source,
        )

    source.write_text(
        json.dumps(
            _signed_owner_completion(
                validated,
                [
                    _claim("person-a", "human", "promote_locally"),
                    _claim("person-b", "human", "promote_locally"),
                ],
            )
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        ProgramFoundryGepaAdjudicatorCompletionError,
        match="external digest pin",
    ):
        completion.import_program_foundry_gepa_adjudicator_completion(
            request_path=request,
            registration_paths=[registration],
            owner_completion_path=source,
            verifier_policy_path=policy,
            trusted_policy_sha256="0" * 64,
            declared_request_id=validated["request"]["request_id"],
            expected_owner_receipt_id=_RECEIPT_ID,
        )


def test_digest_pinned_policy_cannot_cross_request_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, first = _request_fixture(tmp_path)
    source = _write_owner_completion(
        tmp_path,
        first,
        [
            _claim("person-a", "human", "promote_locally"),
            _claim("person-b", "human", "promote_locally"),
        ],
    )
    policy = tmp_path / "verifier-policy.json"
    policy_payload = json.loads(policy.read_text(encoding="utf-8"))
    policy_digest = hashlib.sha256(
        canonical_completion_json(policy_payload)
    ).hexdigest()
    second = {**first, "request": json.loads(json.dumps(first["request"]))}
    second["request"].pop("request_id")
    second["request"]["proposal_id"] = "o" * 64
    second["request"]["request_id"] = hashlib.sha256(
        canonical_completion_json(second["request"])
    ).hexdigest()
    second["request_sha256"] = "z" * 64
    source.write_text(
        json.dumps(
            _signed_owner_completion(
                second,
                [
                    _claim("person-a", "human", "promote_locally"),
                    _claim("person-b", "human", "promote_locally"),
                ],
            )
        ),
        encoding="utf-8",
    )
    _install_request_validation(monkeypatch, second)

    with pytest.raises(
        ProgramFoundryGepaAdjudicatorCompletionError,
        match="exact request scope",
    ):
        completion.import_program_foundry_gepa_adjudicator_completion(
            request_path=request,
            registration_paths=[registration],
            owner_completion_path=source,
            verifier_policy_path=policy,
            trusted_policy_sha256=policy_digest,
            declared_request_id=second["request"]["request_id"],
            expected_owner_receipt_id=_RECEIPT_ID,
        )


def test_rejects_signature_key_substitution_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(tmp_path)
    _install_request_validation(monkeypatch, validated)
    payload = _signed_owner_completion(
        validated,
        [
            _claim("person-a", "human", "require_review"),
            _claim("person-b", "human", "require_review"),
        ],
    )
    payload["claims"][0]["disposition"] = "promote_locally"
    source = tmp_path / "tampered.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "verifier-policy.json").write_text(
        json.dumps(_trust_policy(validated)), encoding="utf-8"
    )

    with pytest.raises(
        ProgramFoundryGepaAdjudicatorCompletionError,
        match="payload digest drifted",
    ):
        _import(
            request_path=request,
            registration_path=registration,
            owner_completion_path=source,
        )
    assert not (request.parent / "comparison-adjudicator-completion.json").exists()


def test_source_or_request_drift_before_commit_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(tmp_path)
    changed = {**validated, "request_sha256": "z" * 64}
    calls = 0

    def validate(path: Path, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return dict(validated if calls == 1 else changed)

    monkeypatch.setattr(
        completion, "validate_program_foundry_gepa_adjudicator_request", validate
    )
    monkeypatch.setattr(completion, "_utc_now", lambda: _VERIFICATION_TIME)
    source = _write_owner_completion(
        tmp_path,
        validated,
        [
            _claim("person-a", "human", "abstain"),
            _claim("person-b", "human", "abstain"),
        ],
    )

    with pytest.raises(
        ProgramFoundryGepaAdjudicatorCompletionError,
        match="changed during import",
    ):
        _import(
            request_path=request,
            registration_path=registration,
            owner_completion_path=source,
        )
    assert not (request.parent / "comparison-adjudicator-completion.json").exists()


def test_committed_embedded_evidence_survives_later_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(tmp_path)
    _install_request_validation(monkeypatch, validated)
    source = _write_owner_completion(
        tmp_path,
        validated,
        [
            _claim("person-a", "human", "require_review"),
            _claim("person-b", "human", "require_review"),
        ],
    )
    real_publish = completion.atomic_publish_bytes

    def publish_then_mutate(*args: Any, **kwargs: Any) -> None:
        real_publish(*args, **kwargs)
        source.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(completion, "atomic_publish_bytes", publish_then_mutate)
    first = _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )
    second = _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )

    assert first["status"] == "completed"
    assert (
        first["source"]["receipt"]["schema_version"]
        == OWNER_VERIFIED_ADJUDICATOR_COMPLETION_SCHEMA
    )
    assert second["reused"] is True


def test_terminal_reuse_rejects_quorum_snapshot_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(tmp_path)
    _install_request_validation(monkeypatch, validated)
    source = _write_owner_completion(
        tmp_path,
        validated,
        [
            _claim("person-a", "human", "promote_locally"),
            _claim("person-b", "human", "promote_locally"),
        ],
    )
    result = _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )
    terminal = Path(result["path"])
    payload = json.loads(terminal.read_text(encoding="utf-8"))
    payload["request"]["snapshot"]["selected_adjudicator"]["quorum"]["required"] = 1
    payload["request"]["canonical_sha256"] = hashlib.sha256(
        canonical_completion_json(payload["request"]["snapshot"])
    ).hexdigest()
    body = {key: value for key, value in payload.items() if key != "completion_id"}
    payload["completion_id"] = hashlib.sha256(
        canonical_completion_json(body)
    ).hexdigest()
    terminal.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ProgramFoundryGepaAdjudicatorCompletionError,
        match="request snapshot id|registration",
    ):
        _import(
            request_path=request,
            registration_path=registration,
            owner_completion_path=source,
        )


def test_changed_external_source_cannot_replace_committed_terminal_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(tmp_path)
    _install_request_validation(monkeypatch, validated)
    source = _write_owner_completion(
        tmp_path,
        validated,
        [
            _claim("person-a", "human", "promote_locally"),
            _claim("person-b", "human", "promote_locally"),
        ],
    )
    _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )
    source.write_text(
        json.dumps(
            _signed_owner_completion(
                validated,
                [
                    _claim("person-a", "human", "reject_locally"),
                    _claim("person-b", "human", "reject_locally"),
                ],
            )
        ),
        encoding="utf-8",
    )

    reused = _import(
        request_path=request,
        registration_path=registration,
        owner_completion_path=source,
    )

    assert reused["reused"] is True
    assert reused["disposition"] == "promote_locally"


def test_commit_followed_by_lock_release_failure_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, registration, validated = _request_fixture(tmp_path)
    _install_request_validation(monkeypatch, validated)
    source = _write_owner_completion(
        tmp_path,
        validated,
        [
            _claim("person-a", "human", "require_review"),
            _claim("person-b", "human", "require_review"),
        ],
    )
    real_lock = completion.foundry_lock

    @contextmanager
    def failing_release(root: Path):
        with real_lock(root) as descriptor:
            yield descriptor
        raise OSError("simulated lock release failure")

    monkeypatch.setattr(completion, "foundry_lock", failing_release)
    with pytest.raises(
        completion.ProgramFoundryGepaAdjudicatorCompletionIndeterminateError,
        match="may have committed before lock release",
    ):
        _import(
            request_path=request,
            registration_path=registration,
            owner_completion_path=source,
        )


def test_completion_cli_forwards_external_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = tmp_path / "request.json"
    registration = tmp_path / "registration.json"
    source = tmp_path / "completion.json"
    policy = tmp_path / "verifier-policy.json"
    for path in (request, registration, source, policy):
        path.write_text("{}", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    def fake_import(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "status": "completed",
            "disposition": "require_review",
            "quorum": {"quorum_satisfied": False},
            "path": "terminal.json",
        }

    monkeypatch.setattr(
        completion, "import_program_foundry_gepa_adjudicator_completion", fake_import
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "import-foundry-gepa-adjudicator-completion",
            "--request",
            str(request),
            "--registration",
            str(registration),
            "--completion",
            str(source),
            "--verifier-policy",
            str(policy),
            "--trusted-policy-sha256",
            "a" * 64,
            "--declare-request-id",
            "r" * 64,
            "--declare-owner-receipt-id",
            _RECEIPT_ID,
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0]["request_path"] == request
    assert calls[0]["owner_completion_path"] == source
    assert calls[0]["verifier_policy_path"] == policy
    assert calls[0]["trusted_policy_sha256"] == "a" * 64
