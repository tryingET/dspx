# summary: "Tests pluggable task adjudicator registrations, selection, pending backends, identity boundaries, and CLI routing."

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import program_adjudicator_protocol as protocol


@pytest.mark.parametrize(
    ("kind", "subjects", "quorum_mode", "quorum_required"),
    [
        ("deterministic_policy", ["policy"], None, None),
        ("ml_algorithm", ["classifier-v1"], None, None),
        ("llm", ["reasoning-model"], None, None),
        ("harnessed_llm", ["harnessed-agent"], None, None),
        ("human", ["declared-person"], None, None),
        ("human_panel", ["person-a", "person-b"], "unanimous", None),
        ("multi_agent_panel", ["agent-a", "agent-b", "agent-c"], "threshold", 2),
        ("hybrid", ["person-a", "agent-a"], "threshold", 2),
    ],
)
def test_registration_contract_supports_all_adjudicator_forms_without_authentication(
    kind: str,
    subjects: list[str],
    quorum_mode: str | None,
    quorum_required: int | None,
) -> None:
    registration = protocol.build_task_adjudicator_registration(
        task_kind="custom_task",
        kind=kind,
        implementation_id=f"{kind}-implementation",
        subjects=subjects,
        subject_kinds=["human", "agent"] if kind == "hybrid" else None,
        quorum_mode=quorum_mode,
        quorum_required=quorum_required,
    )

    assert protocol.validate_task_adjudicator_registration(registration) == registration
    assert registration["backend"]["kind"] == kind
    assert registration["backend"]["execution_support"] == "pending_only"
    assert registration["identity_claims"]["authenticated"] is False
    assert registration["identity_claims"]["assertion_mode"] == "caller_declared"
    assert registration["identity_claims"]["verifier_receipt"] is None
    assert registration["allowed_dispositions"] == list(
        protocol.SHARED_ADJUDICATOR_DISPOSITIONS
    )
    assert registration["authority"]["production_promotion"] is False
    assert registration["authority"]["activation"] is False
    assert registration["authority"]["governance"] is False
    assert registration["execution"]["started"] is False


def test_builtin_deterministic_registration_is_the_only_implemented_backend() -> None:
    registration = protocol.builtin_foundry_deterministic_registration()

    assert registration["backend"] == {
        "kind": "deterministic_policy",
        "implementation_id": protocol.BUILTIN_DETERMINISTIC_IMPLEMENTATION,
        "execution_support": "implemented",
    }
    assert registration["execution"]["replay_policy"] == "pure_recompute"
    assert registration["execution"]["started"] is False


def test_external_registration_cannot_claim_the_builtin_executor() -> None:
    external = protocol.build_task_adjudicator_registration(
        task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        kind="deterministic_policy",
        implementation_id=protocol.BUILTIN_DETERMINISTIC_IMPLEMENTATION,
        subjects=["caller-policy"],
        priority=999,
    )
    assert external["backend"]["execution_support"] == "pending_only"

    forged = protocol.builtin_foundry_deterministic_registration()
    with pytest.raises(
        protocol.ProgramAdjudicatorProtocolError,
        match="cannot claim implemented execution support",
    ):
        protocol.validate_task_adjudicator_registration(forged)


def test_hybrid_registration_requires_both_typed_constituencies() -> None:
    with pytest.raises(
        protocol.ProgramAdjudicatorProtocolError,
        match="both human and agent",
    ):
        protocol.build_task_adjudicator_registration(
            task_kind="custom_task",
            kind="hybrid",
            implementation_id="invalid-hybrid",
            subjects=["person-a", "person-b"],
            subject_kinds=["human", "human"],
            quorum_mode="unanimous",
        )
    valid = protocol.build_task_adjudicator_registration(
        task_kind="custom_task",
        kind="hybrid",
        implementation_id="valid-hybrid",
        subjects=["person-a", "agent-a"],
        subject_kinds=["human", "agent"],
        quorum_mode="threshold",
        quorum_required=2,
    )
    assert valid["quorum"]["constituency_rule"] == ("at_least_one_human_and_one_agent")


def test_registration_rejects_identity_authentication_claims() -> None:
    registration = protocol.build_task_adjudicator_registration(
        task_kind="custom_task",
        kind="human",
        implementation_id="declared-human",
        subjects=["society-person-label"],
    )
    registration["identity_claims"]["authenticated"] = True
    registration["identity_claims"]["verifier_receipt"] = "invented"

    with pytest.raises(
        protocol.ProgramAdjudicatorProtocolError,
        match="cannot authenticate identity claims",
    ):
        protocol.validate_task_adjudicator_registration(registration)


def test_panel_registration_requires_multiple_subjects_and_valid_quorum() -> None:
    with pytest.raises(protocol.ProgramAdjudicatorProtocolError, match="at least two"):
        protocol.build_task_adjudicator_registration(
            task_kind="custom_task",
            kind="human_panel",
            implementation_id="panel",
            subjects=["only-person"],
            quorum_mode="unanimous",
        )
    with pytest.raises(protocol.ProgramAdjudicatorProtocolError, match="between two"):
        protocol.build_task_adjudicator_registration(
            task_kind="custom_task",
            kind="multi_agent_panel",
            implementation_id="panel",
            subjects=["a", "b"],
            quorum_mode="threshold",
            quorum_required=3,
        )


def test_selector_uses_task_priority_and_leaves_unimplemented_backend_pending() -> None:
    low = protocol.build_task_adjudicator_registration(
        task_kind="custom_task",
        kind="deterministic_policy",
        implementation_id="custom-policy",
        subjects=["policy"],
        priority=10,
    )
    high = protocol.build_task_adjudicator_registration(
        task_kind="custom_task",
        kind="human_panel",
        implementation_id="review-board",
        subjects=["person-a", "person-b"],
        priority=20,
        quorum_mode="unanimous",
    )

    selection = protocol.select_task_adjudicator(
        task_kind="custom_task",
        registrations=[low, high],
    )

    assert selection["status"] == "pending"
    assert selection["disposition"] == "pending"
    assert (
        selection["selected_registration"]["registration_id"] == high["registration_id"]
    )
    assert selection["reason"] == "adjudicator_executor_not_implemented"
    assert selection["execution_started"] is False
    assert selection["identity_authenticated_by_dspx"] is False


def test_selector_fails_ambiguous_highest_priority_to_review() -> None:
    first = protocol.build_task_adjudicator_registration(
        task_kind="custom_task",
        kind="llm",
        implementation_id="model-a",
        subjects=["model-a"],
        priority=50,
    )
    second = protocol.build_task_adjudicator_registration(
        task_kind="custom_task",
        kind="human",
        implementation_id="person-a",
        subjects=["person-a"],
        priority=50,
    )

    selection = protocol.select_task_adjudicator(
        task_kind="custom_task",
        registrations=[first, second],
    )

    assert selection["status"] == "require_review"
    assert selection["disposition"] == "require_review"
    assert selection["reason"] == "ambiguous_highest_priority_adjudicators"
    assert selection["selected_registration"] is None
    assert selection["candidate_registration_ids"] == sorted(
        [first["registration_id"], second["registration_id"]]
    )


def test_selector_preserves_builtin_deterministic_compatibility() -> None:
    selection = protocol.select_task_adjudicator(
        task_kind=protocol.FOUNDRY_GEPA_COMPARISON_TASK_KIND,
        registrations=[],
    )

    assert selection["status"] == "selected"
    assert selection["disposition"] == "pending"
    assert selection["fallback_used"] is True
    assert selection["selected_registration"]["backend"]["implementation_id"] == (
        protocol.BUILTIN_DETERMINISTIC_IMPLEMENTATION
    )
    assert selection["reason"] == "adjudicator_ready_for_explicit_execution"


def test_selector_without_match_or_fallback_requires_review() -> None:
    selection = protocol.select_task_adjudicator(
        task_kind="unknown_task",
        registrations=[],
        include_builtin_fallback=False,
    )
    assert selection["status"] == "require_review"
    assert selection["reason"] == "no_matching_adjudicator_registration"
    assert selection["execution_started"] is False


def test_select_adjudicator_cli_loads_regular_registration_without_execution(
    tmp_path: Path,
) -> None:
    registration = protocol.build_task_adjudicator_registration(
        task_kind="foundry_gepa_comparison",
        kind="harnessed_llm",
        implementation_id="bounded-review-harness",
        subjects=["harness-label"],
        priority=100,
    )
    path = tmp_path / "adjudicator-registration.json"
    path.write_text(json.dumps(registration), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "select-adjudicator",
            "--task-kind",
            "foundry_gepa_comparison",
            "--registration",
            str(path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "pending"
    assert payload["disposition"] == "pending"
    assert payload["selected_registration"]["backend"]["kind"] == "harnessed_llm"
    assert payload["execution_started"] is False
    assert payload["identity_authenticated_by_dspx"] is False
    assert payload["registration_sources"][0]["path"] == str(path.resolve())
