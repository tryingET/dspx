# summary: "Tests Sol-backed quality proposals, decisions, and safe artifact publication."

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app

from dspx.dtos import LMRequest, LMResponse
from dspx.services.program_intent import load_program_intent
from dspx.services.program_quality_contract import identity_for
from dspx.services.program_quality_conversation import (
    ProgramQualityConversationError,
    propose_program_quality_criteria,
    set_quality_proposal_decision,
    write_accepted_program_intent,
    write_quality_proposal,
)


class _FakeQualityLM:
    def __init__(
        self,
        payload: dict,
        *,
        model: str = "fake-quality-model",
        prefix: str = "",
    ) -> None:
        self.payload = payload
        self.model = model
        self.prefix = prefix
        self.requests: list[LMRequest] = []

    def generate(self, request: LMRequest, **kwargs) -> LMResponse:  # noqa: ANN003
        self.requests.append(request)
        return LMResponse(
            outputs=[self.prefix + json.dumps(self.payload)],
            model=self.model,
            usage={"input_tokens": 100, "output_tokens": 50},
        )


def _model_payload() -> dict:
    return {
        "metric": "concept_coverage",
        "quality_criteria": [
            {
                "id": "helpful_response",
                "output_field": "response",
                "evaluator": "concept_coverage",
                "required_concept_groups": [
                    ["resolution", "next step"],
                    ["billing", "technical"],
                ],
                "forbidden_concepts": ["guaranteed refund"],
                "min_score": 1.0,
            }
        ],
        "rationale": "The response should classify the issue and provide a useful next step.",
        "clarifying_questions": ["Should policy compliance be evaluated separately?"],
    }


def test_proposal_uses_normalized_fields_and_stays_pending() -> None:
    lm = _FakeQualityLM(_model_payload())

    payload = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=lm,
    )

    assert payload["schema_version"] == "program-quality-criteria-proposal-v1"
    assert payload["status"] == "proposed_pending_acceptance"
    assert payload["intent"]["inputs"] == ["ticket_text"]
    assert payload["intent"]["outputs"] == ["response"]
    assert payload["proposal"]["quality_criteria"][0]["id"] == "helpful_response"
    assert (
        payload["candidate_intent"]["quality_criteria"]
        == payload["proposal"]["quality_criteria"]
    )
    assert (
        payload["candidate_intent"]["options"]["quality_proposal"]["accepted"] is False
    )
    assert payload["model_role"]["model"] == "codex/gpt-5.6-sol"
    assert payload["model_role"]["reasoning_effort"] == "high"
    assert payload["model_role"]["status"] == "declared_not_live_verified"
    assert payload["model_execution"] == {
        "status": "completed",
        "execution_mode": "injected_test_double",
        "requested_model": "codex/gpt-5.6-sol",
        "reported_model": "fake-quality-model",
        "reasoning_effort": "high",
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "response_sha256": payload["model_execution"]["response_sha256"],
        "json_extraction": "direct_object",
    }
    assert payload["effect"]["program_generated"] is False
    assert payload["non_authority"]["model_proposal_is_decision"] is False
    assert len(lm.requests) == 1
    assert "Return only one JSON object" in str(lm.requests[0].prompt)


def test_wrapped_model_reasoning_is_not_persisted_as_proposal_content() -> None:
    payload = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(
            _model_payload(),
            prefix="Planning criteria before returning the requested object: ",
        ),
    )

    assert payload["model_execution"]["json_extraction"] == ("fenced_or_wrapped_object")
    assert payload["proposal"]["metric"] == "concept_coverage"
    assert "Planning criteria" not in json.dumps(payload["proposal"])


def test_feedback_is_bound_into_next_proposal_turn() -> None:
    lm = _FakeQualityLM(_model_payload())

    payload = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        feedback=["Add a policy-safety criterion."],
        lm=lm,
    )

    assert payload["conversation"] == {
        "feedback": ["Add a policy-safety criterion."],
        "turn": 1,
        "history": [],
    }
    assert "Add a policy-safety criterion." in str(lm.requests[0].prompt)


def test_invalid_or_unbound_quality_contract_fails_closed() -> None:
    invalid = _model_payload()
    invalid["quality_criteria"][0]["output_field"] = "undeclared"

    with pytest.raises(
        ProgramQualityConversationError,
        match="references undeclared output",
    ):
        propose_program_quality_criteria(
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            lm=_FakeQualityLM(invalid),
        )


def test_acceptance_is_explicit_and_writes_valid_program_intent(tmp_path: Path) -> None:
    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    accepted = set_quality_proposal_decision(proposal, decision="accept")
    proposal_path = write_quality_proposal(accepted, tmp_path / "proposal.json")
    intent_path = write_accepted_program_intent(accepted, tmp_path / "intent.json")

    assert proposal_path.stat().st_mode & 0o777 == 0o600
    assert accepted["status"] == "accepted_for_program_generation"
    assert (
        accepted["candidate_intent"]["options"]["quality_proposal"]["accepted"] is True
    )
    intent = load_program_intent(intent_path)
    assert intent.metric == "concept_coverage"
    assert intent.quality_criteria[0]["id"] == "helpful_response"


def test_pending_proposal_cannot_write_program_intent(tmp_path: Path) -> None:
    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )

    with pytest.raises(
        ProgramQualityConversationError,
        match="accepted_for_program_generation",
    ):
        write_accepted_program_intent(proposal, tmp_path / "intent.json")


runner = CliRunner()


def test_quality_chat_non_interactive_accepts_proposal(
    monkeypatch, tmp_path: Path
) -> None:
    from dspx.services import program_quality_conversation as quality_service

    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    monkeypatch.setattr(
        quality_service,
        "propose_program_quality_criteria",
        lambda prompt, feedback=(), history=(): proposal,
    )
    out = tmp_path / "proposal.json"

    result = runner.invoke(
        app,
        [
            "program-gen",
            "quality-chat",
            "--prompt",
            "route tickets",
            "--out",
            str(out),
            "--non-interactive",
            "--accept",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["status"] == "accepted_for_program_generation"
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == (
        "accepted_for_program_generation"
    )


def test_quality_chat_non_interactive_writes_pending_proposal(
    monkeypatch, tmp_path: Path
) -> None:
    from dspx.services import program_quality_conversation as quality_service

    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    monkeypatch.setattr(
        quality_service,
        "propose_program_quality_criteria",
        lambda prompt, feedback=(), history=(): proposal,
    )
    out = tmp_path / "proposal.json"

    result = runner.invoke(
        app,
        [
            "program-gen",
            "quality-chat",
            "--prompt",
            "route tickets",
            "--out",
            str(out),
            "--non-interactive",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == (
        "proposed_pending_acceptance"
    )


def test_quality_chat_rejects_json_in_interactive_mode(
    monkeypatch, tmp_path: Path
) -> None:
    from dspx.cli import dspx as cli_module
    from dspx.services import program_quality_conversation as quality_service

    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    monkeypatch.setattr(
        quality_service,
        "propose_program_quality_criteria",
        lambda prompt, feedback=(), history=(): proposal,
    )
    monkeypatch.setattr(cli_module, "_interactive_quality_chat_available", lambda: True)
    out = tmp_path / "interactive.json"

    result = runner.invoke(
        app,
        [
            "program-gen",
            "quality-chat",
            "--prompt",
            "route tickets",
            "--out",
            str(out),
            "--json",
        ],
        input="accept\n",
    )

    assert result.exit_code == 2
    assert "--json requires --non-interactive" in result.stderr
    assert not out.exists()


def test_revision_turn_includes_prior_validated_proposal() -> None:
    first = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    lm = _FakeQualityLM(_model_payload())

    second = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        feedback=["Make helpful_response stricter."],
        history=[first],
        lm=lm,
    )

    assert second["conversation"]["turn"] == 2
    assert (
        second["conversation"]["history"][0]["proposal"]["quality_criteria"][0]["id"]
        == "helpful_response"
    )
    assert "helpful_response" in str(lm.requests[0].prompt)


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda payload: payload.pop("rationale"), "fields mismatch"),
        (
            lambda payload: payload.__setitem__("metric", "accuracy"),
            "must be concept_coverage",
        ),
        (
            lambda payload: payload.__setitem__("clarifying_questions", {}),
            "must be a list",
        ),
    ],
)
def test_model_payload_requires_exact_v1_contract(mutation, match: str) -> None:  # noqa: ANN001
    invalid = _model_payload()
    mutation(invalid)

    with pytest.raises(ProgramQualityConversationError, match=match):
        propose_program_quality_criteria(
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            lm=_FakeQualityLM(invalid),
        )


def test_secret_shaped_intent_is_rejected_before_model_call() -> None:
    lm = _FakeQualityLM(_model_payload())

    with pytest.raises(ProgramQualityConversationError, match="secret-shaped"):
        propose_program_quality_criteria(
            "Build a helper with api_key=sk-abcdefghijklmnopqrstuvwxyz123456",
            lm=lm,
        )

    assert lm.requests == []


def test_tampered_proposal_cannot_be_accepted() -> None:
    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    proposal["proposal"]["rationale"] = "substituted"

    with pytest.raises(ProgramQualityConversationError, match="identity binding"):
        set_quality_proposal_decision(proposal, decision="accept")


def test_writers_reject_existing_and_symlink_outputs(tmp_path: Path) -> None:
    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    existing = tmp_path / "existing.json"
    existing.write_text("original", encoding="utf-8")
    target = tmp_path / "target.json"
    target.write_text("target-original", encoding="utf-8")
    symlink = tmp_path / "proposal.json"
    symlink.symlink_to(target)

    with pytest.raises(ProgramQualityConversationError, match="already exists"):
        write_quality_proposal(proposal, existing)
    with pytest.raises(ProgramQualityConversationError, match="already exists"):
        write_quality_proposal(proposal, symlink)

    assert existing.read_text(encoding="utf-8") == "original"
    assert target.read_text(encoding="utf-8") == "target-original"
    assert symlink.is_symlink()


def test_criterion_requires_exact_keys_and_native_types() -> None:
    missing = _model_payload()
    missing["quality_criteria"][0].pop("min_score")
    coerced = _model_payload()
    coerced["quality_criteria"][0]["id"] = 123

    for payload in (missing, coerced):
        with pytest.raises(ProgramQualityConversationError):
            propose_program_quality_criteria(
                "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
                lm=_FakeQualityLM(payload),
            )


def test_model_output_secret_is_rejected() -> None:
    secret = _model_payload()
    secret["rationale"] = "Use api_key=sk-abcdefghijklmnopqrstuvwxyz123456"

    with pytest.raises(ProgramQualityConversationError, match="secret-shaped"):
        propose_program_quality_criteria(
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            lm=_FakeQualityLM(secret),
        )


def test_history_requires_a_valid_same_intent_envelope() -> None:
    first = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    first["conversation"]["feedback"] = ["substituted"]

    with pytest.raises(ProgramQualityConversationError, match="identity binding"):
        propose_program_quality_criteria(
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            history=[first],
            lm=_FakeQualityLM(_model_payload()),
        )


def test_accepted_status_requires_bound_decision_evidence() -> None:
    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    proposal["status"] = "accepted_for_program_generation"

    with pytest.raises(ProgramQualityConversationError, match="lifecycle status"):
        write_quality_proposal(proposal, Path("unused.json"))


def test_exclusive_publication_does_not_overwrite_racing_target(
    monkeypatch, tmp_path: Path
) -> None:
    from dspx.services import artifact_boundary

    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    target = tmp_path / "racing.json"
    real_link = artifact_boundary.os.link

    def racing_link(*args, **kwargs):  # noqa: ANN002, ANN003
        target.write_text("racer", encoding="utf-8")
        return real_link(*args, **kwargs)

    monkeypatch.setattr(artifact_boundary.os, "link", racing_link)

    with pytest.raises(ProgramQualityConversationError, match="atomic publication"):
        write_quality_proposal(proposal, target)

    assert target.read_text(encoding="utf-8") == "racer"


def test_intent_hash_must_match_candidate_provenance() -> None:
    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    proposal["intent"]["text_sha256"] = "a" * 64
    proposal["identity"] = identity_for(proposal)

    with pytest.raises(ProgramQualityConversationError, match="provenance hashes"):
        write_quality_proposal(proposal, Path("unused.json"))


def test_reported_model_secret_is_redacted_before_persistence() -> None:
    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(
            _model_payload(),
            model="api_key=sk-abcdefghijklmnopqrstuvwxyz123456",
        ),
    )

    assert proposal["model_execution"]["reported_model"] == "[REDACTED]"


def test_decision_source_hash_must_match_derived_pending_envelope() -> None:
    proposal = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    accepted = set_quality_proposal_decision(proposal, decision="accept")
    accepted["decision"]["source_envelope_sha256"] = "f" * 64
    accepted["identity"] = identity_for(accepted)

    with pytest.raises(ProgramQualityConversationError, match="decision evidence"):
        write_quality_proposal(accepted, Path("unused.json"))


def test_history_rejects_independent_nonextending_turns() -> None:
    first = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )
    independent = propose_program_quality_criteria(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        lm=_FakeQualityLM(_model_payload()),
    )

    with pytest.raises(ProgramQualityConversationError, match="preceding lineage"):
        propose_program_quality_criteria(
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            history=[first, independent],
            lm=_FakeQualityLM(_model_payload()),
        )
