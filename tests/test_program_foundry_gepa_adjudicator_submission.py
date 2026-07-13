# summary: "Tests asynchronous human adjudicator submissions remain unverified, non-quorum, receipt-bound, and idempotent."

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import program_adjudicator_protocol as protocol
import dspx.services.program_foundry_gepa_adjudicator_submission as submission


def _request_fixture(
    tmp_path: Path,
    *,
    kind: str = "human_panel",
    subjects: list[str] | None = None,
    subject_kinds: list[str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "foundry"
    experiment = root / "gepa-experiment"
    experiment.mkdir(parents=True)
    request_path = experiment / "comparison-adjudicator-request.json"
    subjects = subjects or ["person-a", "person-b"]
    registration = protocol.build_task_adjudicator_registration(
        task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        kind=kind,
        implementation_id=f"{kind}-implementation",
        subjects=subjects,
        subject_kinds=subject_kinds,
        quorum_mode="unanimous" if len(subjects) > 1 else None,
    )
    request = {
        "schema_version": "dspx-program-foundry-gepa-adjudicator-request-v1",
        "status": "pending",
        "request_id": "r" * 64,
        "proposal_id": "p" * 64,
        "selected_adjudicator": registration,
        "bindings": {
            "comparison_jury_receipt_path": str(
                experiment / "comparison-jury-receipt.json"
            ),
            "comparison_jury_receipt_sha256": "jury-hash",
            "registration_snapshot_sha256": "registration-snapshot-hash",
            "selection_sha256": "selection-hash",
        },
    }
    request_path.write_text(json.dumps(request), encoding="utf-8")
    (experiment / "adjudicator-registration.json").write_text(
        json.dumps(registration), encoding="utf-8"
    )
    validated = {
        "request": request,
        "request_path": request_path,
        "request_sha256": "request-hash",
        "validated_jury": {},
    }
    return request_path, validated


def _install_validation(
    monkeypatch: pytest.MonkeyPatch,
    validated: dict[str, Any],
) -> None:
    monkeypatch.setattr(
        submission,
        "validate_program_foundry_gepa_adjudicator_request",
        lambda path, **kwargs: dict(validated),
    )


def _record_submission(
    *, request_path: Path, subject: str, disposition: str
) -> dict[str, Any]:
    return submission.record_program_foundry_gepa_adjudicator_submission(
        request_path=request_path,
        registration_paths=[request_path.parent / "adjudicator-registration.json"],
        declared_request_id="r" * 64,
        subject=subject,
        disposition=disposition,
    )


def test_records_and_reuses_unverified_human_submission_without_quorum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, validated = _request_fixture(tmp_path)
    _install_validation(monkeypatch, validated)

    first = _record_submission(
        request_path=request,
        subject="person-a",
        disposition="promote_locally",
    )
    second = _record_submission(
        request_path=request,
        subject="person-a",
        disposition="promote_locally",
    )

    assert first["status"] == "recorded_unverified"
    assert first["reused"] is False
    assert second["reused"] is True
    assert first["submission"]["disposition_claim"] == "promote_locally"
    assert first["subject_claim"] == {
        "label": "person-a",
        "kind": "human",
        "assertion_mode": "caller_declared",
        "authenticated": False,
        "membership_verified": False,
        "participation_verified": False,
        "signature_verified": False,
        "verifier_receipt": None,
    }
    assert first["effect"]["counts_toward_quorum"] is False
    assert first["effect"]["quorum_satisfied"] is False
    assert first["effect"]["adjudication_completed"] is False
    assert first["effect"]["transition_allowed"] is False
    assert first["non_authority"]["promotion_authority"] is False
    assert Path(first["path"]).stat().st_mode & 0o777 == 0o600


def test_one_subject_cannot_record_conflicting_submission_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, validated = _request_fixture(tmp_path)
    _install_validation(monkeypatch, validated)
    _record_submission(
        request_path=request,
        subject="person-a",
        disposition="promote_locally",
    )

    with pytest.raises(
        submission.ProgramFoundryGepaAdjudicatorSubmissionError,
        match="different recorded submission",
    ):
        _record_submission(
            request_path=request,
            subject="person-a",
            disposition="reject_locally",
        )


def test_rejects_unknown_nonhuman_and_pending_submission_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, validated = _request_fixture(
        tmp_path,
        kind="hybrid",
        subjects=["person-a", "agent-a"],
        subject_kinds=["human", "agent"],
    )
    _install_validation(monkeypatch, validated)
    with pytest.raises(
        submission.ProgramFoundryGepaAdjudicatorSubmissionError,
        match="not declared",
    ):
        _record_submission(
            request_path=request,
            subject="person-unknown",
            disposition="abstain",
        )
    with pytest.raises(
        submission.ProgramFoundryGepaAdjudicatorSubmissionError,
        match="only declared human",
    ):
        _record_submission(
            request_path=request,
            subject="agent-a",
            disposition="abstain",
        )
    with pytest.raises(
        submission.ProgramFoundryGepaAdjudicatorSubmissionError,
        match="must be promote_locally",
    ):
        _record_submission(
            request_path=request,
            subject="person-a",
            disposition="pending",
        )


def test_submission_requires_pending_human_selected_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, validated = _request_fixture(
        tmp_path,
        kind="llm",
        subjects=["model-a"],
    )
    _install_validation(monkeypatch, validated)
    with pytest.raises(
        submission.ProgramFoundryGepaAdjudicatorSubmissionError,
        match="does not accept human submissions",
    ):
        _record_submission(
            request_path=request,
            subject="model-a",
            disposition="abstain",
        )
    validated["request"]["status"] = "ready"
    with pytest.raises(
        submission.ProgramFoundryGepaAdjudicatorSubmissionError,
        match="requires a pending",
    ):
        _record_submission(
            request_path=request,
            subject="model-a",
            disposition="abstain",
        )


def test_request_drift_before_commit_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, validated = _request_fixture(tmp_path)
    changed = {**validated, "request_sha256": "changed"}
    calls = 0

    def validate(path: Path, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return dict(validated if calls == 1 else changed)

    monkeypatch.setattr(
        submission,
        "validate_program_foundry_gepa_adjudicator_request",
        validate,
    )
    with pytest.raises(
        submission.ProgramFoundryGepaAdjudicatorSubmissionError,
        match="changed during",
    ):
        _record_submission(
            request_path=request,
            subject="person-a",
            disposition="require_review",
        )
    submissions = request.parent / "comparison-adjudicator-submissions"
    assert not submissions.exists() or not list(submissions.glob("*.json"))


def test_terminal_completion_closes_submission_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, validated = _request_fixture(tmp_path)
    _install_validation(monkeypatch, validated)
    (request.parent / "comparison-adjudicator-completion.json").write_text(
        "{}", encoding="utf-8"
    )

    with pytest.raises(
        submission.ProgramFoundryGepaAdjudicatorSubmissionError,
        match="submissions are closed",
    ):
        _record_submission(
            request_path=request,
            subject="person-a",
            disposition="abstain",
        )


def test_commit_followed_by_lock_release_failure_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, validated = _request_fixture(tmp_path)
    _install_validation(monkeypatch, validated)
    real_lock = submission.foundry_lock

    @contextmanager
    def failing_release(root: Path):
        with real_lock(root) as descriptor:
            yield descriptor
        raise OSError("simulated lock release failure")

    monkeypatch.setattr(submission, "foundry_lock", failing_release)
    with pytest.raises(
        submission.ProgramFoundryGepaAdjudicatorSubmissionIndeterminateError,
        match="may have committed before lock release",
    ):
        _record_submission(
            request_path=request,
            subject="person-a",
            disposition="abstain",
        )


def test_submission_cli_forwards_unverified_claim_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = tmp_path / "comparison-adjudicator-request.json"
    request.write_text("{}", encoding="utf-8")
    registration = tmp_path / "registration.json"
    registration.write_text("{}", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    def fake_record(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "status": "recorded_unverified",
            "effect": {"counts_toward_quorum": False},
            "path": "submission.json",
        }

    monkeypatch.setattr(
        submission,
        "record_program_foundry_gepa_adjudicator_submission",
        fake_record,
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "record-foundry-gepa-adjudicator-submission",
            "--request",
            str(request),
            "--registration",
            str(registration),
            "--declare-request-id",
            "r" * 64,
            "--subject",
            "person-a",
            "--disposition",
            "abstain",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "request_path": request,
            "registration_paths": [registration],
            "declared_request_id": "r" * 64,
            "subject": "person-a",
            "disposition": "abstain",
        }
    ]
