# summary: "Tests receipt-bound adjudicator dispatch requests, deterministic routing, pending external forms, and drift safety."

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import program_adjudicator_protocol as protocol
import dspx.services.program_foundry_gepa_adjudicator_dispatch as dispatch


def _jury_fixture(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "foundry"
    experiment = root / "gepa-experiment"
    candidate = experiment / "materialized-candidate" / "manifest.json"
    experiment.mkdir(parents=True)
    candidate.parent.mkdir()
    receipt = experiment / "comparison-jury-receipt.json"
    result = experiment / "comparison-jury-results.json"
    comparison = experiment / "candidate-comparison.json"
    for path in (receipt, result, comparison, candidate):
        path.write_text("{}", encoding="utf-8")
    return receipt, {
        "root": root,
        "experiment_root": experiment,
        "proposal_id": "a" * 64,
        "jury_receipt_path": receipt,
        "jury_receipt_sha256": "jury-receipt-hash",
        "jury_result_path": result,
        "jury_result_sha256": "jury-result-hash",
        "candidate_manifest_path": candidate,
        "candidate_manifest_sha256": "candidate-hash",
        "comparison_path": comparison,
        "comparison_sha256": "comparison-hash",
    }


def _write_registration(path: Path, registration: dict[str, Any]) -> None:
    path.write_text(json.dumps(registration), encoding="utf-8")


def _install_jury_validation(
    monkeypatch: pytest.MonkeyPatch,
    validated: dict[str, Any],
) -> None:
    monkeypatch.setattr(
        dispatch,
        "validate_successful_program_foundry_gepa_comparison_jury_receipt",
        lambda path, **kwargs: dict(validated),
    )


def test_external_human_panel_dispatch_stays_pending_and_is_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _jury_fixture(tmp_path)
    _install_jury_validation(monkeypatch, validated)
    registration = protocol.build_task_adjudicator_registration(
        task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        kind="human_panel",
        implementation_id="society-review-panel",
        subjects=["person-a", "person-b"],
        quorum_mode="unanimous",
    )
    registration_path = tmp_path / "panel.json"
    _write_registration(registration_path, registration)
    deterministic_calls = 0

    def fail_deterministic(**kwargs: Any) -> dict[str, Any]:
        nonlocal deterministic_calls
        deterministic_calls += 1
        raise AssertionError("external adjudicator must not execute")

    monkeypatch.setattr(
        dispatch,
        "adjudicate_program_foundry_gepa_comparison",
        fail_deterministic,
    )

    first = dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
        comparison_jury_receipt_path=receipt,
        registration_paths=[registration_path],
    )
    second = dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
        comparison_jury_receipt_path=receipt,
        registration_paths=[registration_path],
    )

    assert first == second
    assert first["status"] == "pending"
    assert first["disposition"] == "pending"
    assert first["selected_adjudicator"]["backend"]["kind"] == "human_panel"
    assert first["execution"]["external_executor_invoked"] is False
    assert first["execution"]["human_or_panel_contacted"] is False
    assert first["identity_authenticated_by_dspx"] is False
    assert deterministic_calls == 0
    request = json.loads(
        (receipt.parent / "comparison-adjudicator-request.json").read_text(
            encoding="utf-8"
        )
    )
    assert request["status"] == "pending"
    assert request["execution"]["started"] is False
    assert request["identity"]["authenticated_by_dspx"] is False
    assert request["identity"]["quorum_satisfied"] is False
    assert request["registration_snapshot"]["entries"][0]["source_path"] == str(
        registration_path.absolute()
    )
    request_path = receipt.parent / "comparison-adjudicator-request.json"
    with dispatch.foundry_lock(validated["root"]) as root_descriptor:
        validated_request = dispatch.validate_program_foundry_gepa_adjudicator_request(
            request_path,
            root_descriptor=root_descriptor,
            registration_paths=[registration_path],
        )
    assert validated_request["request"] == request
    assert validated_request["request_path"] == request_path
    alternate = protocol.build_task_adjudicator_registration(
        task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        kind="human",
        implementation_id="different-person",
        subjects=["person-c"],
    )
    alternate_path = registration_path.parent / "alternate.json"
    _write_registration(alternate_path, alternate)
    with dispatch.foundry_lock(validated["root"]) as root_descriptor:
        with pytest.raises(
            dispatch.ProgramFoundryGepaAdjudicatorDispatchError,
            match="do not match explicit inputs",
        ):
            dispatch.validate_program_foundry_gepa_adjudicator_request(
                request_path,
                root_descriptor=root_descriptor,
                registration_paths=[alternate_path],
            )


def test_request_commit_followed_by_lock_release_failure_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _jury_fixture(tmp_path)
    _install_jury_validation(monkeypatch, validated)
    registration = protocol.build_task_adjudicator_registration(
        task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        kind="human",
        implementation_id="person-review",
        subjects=["person-label"],
    )
    registration_path = tmp_path / "human.json"
    _write_registration(registration_path, registration)
    real_lock = dispatch.foundry_lock

    @contextmanager
    def failing_release(root: Path):
        with real_lock(root) as descriptor:
            yield descriptor
        raise OSError("simulated lock release failure")

    monkeypatch.setattr(dispatch, "foundry_lock", failing_release)
    with pytest.raises(
        dispatch.ProgramFoundryGepaAdjudicatorDispatchIndeterminateError,
        match="may have committed before lock release",
    ):
        dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
            comparison_jury_receipt_path=receipt,
            registration_paths=[registration_path],
        )
    assert (receipt.parent / "comparison-adjudicator-request.json").exists()


def test_builtin_fallback_executes_only_existing_deterministic_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _jury_fixture(tmp_path)
    _install_jury_validation(monkeypatch, validated)
    calls: list[Path] = []

    def deterministic(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["comparison_jury_receipt_path"])
        payload = {
            "status": "recorded",
            "disposition": "promote_locally",
            "bindings": {
                "comparison_jury_receipt_path": str(receipt.absolute()),
                "comparison_jury_receipt_sha256": validated["jury_receipt_sha256"],
            },
        }
        (receipt.parent / "comparison-adjudication.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return {**payload, "reused": len(calls) > 1}

    monkeypatch.setattr(
        dispatch,
        "adjudicate_program_foundry_gepa_comparison",
        deterministic,
    )
    first = dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
        comparison_jury_receipt_path=receipt
    )
    second = dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
        comparison_jury_receipt_path=receipt
    )

    assert first["status"] == "completed"
    assert first["disposition"] == "promote_locally"
    assert first["selected_adjudicator"]["backend"]["execution_support"] == (
        "implemented"
    )
    assert first["execution"]["deterministic_backend_executed_or_reused"] is True
    assert first["execution"]["external_executor_invoked"] is False
    assert second["deterministic_adjudication"]["reused"] is True
    assert calls == [receipt.absolute(), receipt.absolute()]


def test_deterministic_dispatch_rejects_lineage_change_between_lock_acquisitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _jury_fixture(tmp_path)
    changed = {**validated, "jury_receipt_sha256": "changed-jury-hash"}
    validation_calls = 0

    def validate(path: Path, **kwargs: Any) -> dict[str, Any]:
        nonlocal validation_calls
        validation_calls += 1
        return dict(validated if validation_calls <= 2 else changed)

    monkeypatch.setattr(
        dispatch,
        "validate_successful_program_foundry_gepa_comparison_jury_receipt",
        validate,
    )

    def changed_deterministic(**kwargs: Any) -> dict[str, Any]:
        payload = {
            "status": "recorded",
            "disposition": "promote_locally",
            "bindings": {
                "comparison_jury_receipt_path": str(receipt.absolute()),
                "comparison_jury_receipt_sha256": "changed-jury-hash",
            },
        }
        (receipt.parent / "comparison-adjudication.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return payload

    monkeypatch.setattr(
        dispatch,
        "adjudicate_program_foundry_gepa_comparison",
        changed_deterministic,
    )

    with pytest.raises(
        dispatch.ProgramFoundryGepaAdjudicatorDispatchIndeterminateError,
        match="different jury lineage",
    ):
        dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
            comparison_jury_receipt_path=receipt
        )


def test_deterministic_dispatch_rejects_persisted_request_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _jury_fixture(tmp_path)
    _install_jury_validation(monkeypatch, validated)

    def mutate_request(**kwargs: Any) -> dict[str, Any]:
        request_path = receipt.parent / "comparison-adjudicator-request.json"
        request_path.write_text('{"tampered":true}', encoding="utf-8")
        payload = {
            "status": "recorded",
            "disposition": "promote_locally",
            "bindings": {
                "comparison_jury_receipt_path": str(receipt.absolute()),
                "comparison_jury_receipt_sha256": validated["jury_receipt_sha256"],
            },
        }
        (receipt.parent / "comparison-adjudication.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return payload

    monkeypatch.setattr(
        dispatch,
        "adjudicate_program_foundry_gepa_comparison",
        mutate_request,
    )
    with pytest.raises(
        dispatch.ProgramFoundryGepaAdjudicatorDispatchIndeterminateError,
        match="request changed",
    ):
        dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
            comparison_jury_receipt_path=receipt
        )


def test_missing_registration_is_a_controlled_dispatch_input_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _jury_fixture(tmp_path)
    _install_jury_validation(monkeypatch, validated)
    missing = tmp_path / "missing-registration.json"

    with pytest.raises(
        dispatch.ProgramFoundryGepaAdjudicatorDispatchError,
        match="cannot be read safely",
    ):
        dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
            comparison_jury_receipt_path=receipt,
            registration_paths=[missing],
        )
    cli_result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "dispatch-foundry-gepa-adjudicator",
            "--receipt",
            str(receipt),
            "--registration",
            str(missing),
            "--json",
        ],
    )
    assert cli_result.exit_code == 2
    assert "cannot be read safely" in cli_result.output


def test_ambiguous_external_registrations_require_review_without_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _jury_fixture(tmp_path)
    _install_jury_validation(monkeypatch, validated)
    paths: list[Path] = []
    for index, kind in enumerate(("llm", "human")):
        registration = protocol.build_task_adjudicator_registration(
            task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
            kind=kind,
            implementation_id=f"implementation-{index}",
            subjects=[f"subject-{index}"],
            priority=50,
        )
        path = tmp_path / f"registration-{index}.json"
        _write_registration(path, registration)
        paths.append(path)
    monkeypatch.setattr(
        dispatch,
        "adjudicate_program_foundry_gepa_comparison",
        lambda **kwargs: pytest.fail("ambiguous selection must not execute"),
    )

    result = dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
        comparison_jury_receipt_path=receipt,
        registration_paths=paths,
        include_builtin_fallback=False,
    )

    assert result["status"] == "require_review"
    assert result["disposition"] == "require_review"
    assert result["selected_adjudicator"] is None
    assert result["execution"]["external_executor_invoked"] is False


def test_duplicate_registration_contracts_preserve_sources_without_false_ambiguity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _jury_fixture(tmp_path)
    _install_jury_validation(monkeypatch, validated)
    registration = protocol.build_task_adjudicator_registration(
        task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        kind="llm",
        implementation_id="same-model",
        subjects=["model-label"],
    )
    paths = [tmp_path / "a.json", tmp_path / "b.json"]
    for path in paths:
        _write_registration(path, registration)

    result = dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
        comparison_jury_receipt_path=receipt,
        registration_paths=paths,
    )

    assert result["status"] == "pending"
    request = json.loads(
        (receipt.parent / "comparison-adjudicator-request.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(request["registration_snapshot"]["entries"]) == 2
    assert request["selection"]["reason"] == "adjudicator_executor_not_implemented"


def test_existing_request_rejects_registration_or_selection_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _jury_fixture(tmp_path)
    _install_jury_validation(monkeypatch, validated)
    first_registration = protocol.build_task_adjudicator_registration(
        task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        kind="human",
        implementation_id="person-a",
        subjects=["person-a"],
    )
    path = tmp_path / "registration.json"
    _write_registration(path, first_registration)
    dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
        comparison_jury_receipt_path=receipt,
        registration_paths=[path],
    )
    changed = protocol.build_task_adjudicator_registration(
        task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        kind="human",
        implementation_id="person-b",
        subjects=["person-b"],
    )
    _write_registration(path, changed)

    with pytest.raises(
        dispatch.ProgramFoundryGepaAdjudicatorDispatchError,
        match="request or bound inputs drifted",
    ):
        dispatch.dispatch_program_foundry_gepa_comparison_adjudicator(
            comparison_jury_receipt_path=receipt,
            registration_paths=[path],
        )


def test_dispatch_cli_forwards_receipt_registrations_and_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "comparison-jury-receipt.json"
    registration = tmp_path / "registration.json"
    receipt.write_text("{}", encoding="utf-8")
    registration.write_text("{}", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    def fake_dispatch(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "status": "pending",
            "disposition": "pending",
            "request_path": "request.json",
        }

    monkeypatch.setattr(
        dispatch,
        "dispatch_program_foundry_gepa_comparison_adjudicator",
        fake_dispatch,
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "dispatch-foundry-gepa-adjudicator",
            "--receipt",
            str(receipt),
            "--registration",
            str(registration),
            "--no-builtin-fallback",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "comparison_jury_receipt_path": receipt,
            "registration_paths": [registration],
            "include_builtin_fallback": False,
        }
    ]
