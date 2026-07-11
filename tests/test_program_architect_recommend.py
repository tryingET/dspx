# summary: "Tests advisory architecture recommendations and fail-closed tournament authority validation."
# read_when:
#   - "Changing program-architect recommendations, evidence-matrix validation, or non-authority flags."

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.cache import sha256_text
from dspx.cli.dspx import app
from program_architecture_shared import (
    _recommendation_tournament_non_authority,
    _write_intent,
    runner,
)


@pytest.mark.slow
def test_program_architect_recommend_emits_next_moves_without_winner_selection(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    tournament_out = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "architecture_recommendation.json"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
        examples=True,
    )
    assert (
        runner.invoke(
            app,
            [
                "program-architect",
                "plan",
                "--intent",
                str(intent_path),
                "--out",
                str(plan_path),
            ],
        ).exit_code
        == 0
    )
    tournament_result = runner.invoke(
        app,
        [
            "program-architect",
            "tournament",
            "--architecture-plan",
            str(plan_path),
            "--outdir",
            str(tmp_path / "tournament"),
            "--out",
            str(tournament_out),
        ],
    )
    assert tournament_result.exit_code == 0, tournament_result.output
    before_hash = sha256_text(tournament_out.read_text(encoding="utf-8"))

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_out),
            "--out",
            str(recommendation_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(recommendation_out.read_text(encoding="utf-8"))
    assert json.loads(result.output) == payload
    assert sha256_text(tournament_out.read_text(encoding="utf-8")) == before_hash
    assert payload["schema_version"] == "program-architecture-recommendation-v1"
    assert payload["created_from"]["tournament_schema_version"] == (
        "program-architecture-tournament-v1"
    )
    assert payload["status"] in {"advisory_ready", "needs_attention"}
    assert payload["next_moves"]
    assert [item["candidate_id"] for item in payload["candidate_advisories"]] == [
        "baseline_single_predict",
        "prompt_inferred_pipeline",
    ]
    assert all("winner" not in item for item in payload)
    assert "selected_candidate_id" not in payload
    assert "winner_candidate_id" not in payload
    assert payload["effect"]["recommendation_sidecar_written"] is True
    assert payload["effect"]["candidate_programs_materialized"] is False
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["effect"]["winner_selected"] is False
    assert payload["effect"]["promotion_applied"] is False
    assert payload["effect"]["ak_called"] is False
    assert payload["effect"]["governance_mutated"] is False
    assert payload["non_authority"]["advisory_only"] is True
    assert payload["non_authority"]["winner_selection"] is False
    assert payload["non_authority"]["promotion_authority"] is False
    for advisory in payload["candidate_advisories"]:
        assert advisory["non_authority"] == {
            "winner_selection": False,
            "ranking_authority": False,
            "promotion_authority": False,
            "activation_authority": False,
            "oracle_authority": False,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "governance_authority": False,
            "external_mutation": False,
            "canonical_mutation": False,
        }


def test_program_architect_recommend_rejects_authority_widened_tournament(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                },
                "effect": {
                    "winner_selected": True,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": {"winner_selection": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "widens authority" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_shared_oracle_mutation(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": True,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "shared_oracle_mutated" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_missing_tournament_non_authority_flags(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": False,
                        "promotion_authority": False,
                        "oracle_ranking": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": {"winner_selection": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "tournament non_authority missing authority flags" in result.output
    assert "ranking_authority" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_missing_evidence_matrix_non_authority_flags(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": False,
                        "promotion_authority": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "evidence_matrix non_authority missing authority flags" in result.output
    assert "oracle_ranking" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_missing_candidate_row_non_authority_flags(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [
                        {
                            "candidate_id": "candidate_a",
                            "status": "skipped",
                            "reason": "test",
                            "non_authority": {
                                "winner_selection": False,
                                "promotion_authority": False,
                            },
                        }
                    ],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": False,
                        "promotion_authority": False,
                        "oracle_ranking": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "row 0 non_authority missing authority flags" in result.output
    assert "oracle_ranking" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_widened_evidence_matrix_non_authority(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": True,
                        "promotion_authority": False,
                        "oracle_ranking": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "evidence_matrix non_authority widens authority" in result.output
    assert "winner_selection" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_widened_candidate_row_non_authority(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [
                        {
                            "candidate_id": "candidate_a",
                            "status": "skipped",
                            "reason": "test",
                            "non_authority": {
                                "winner_selection": False,
                                "promotion_authority": False,
                                "oracle_ranking": True,
                            },
                        }
                    ],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": False,
                        "promotion_authority": False,
                        "oracle_ranking": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "row 0 non_authority widens authority" in result.output
    assert "oracle_ranking" in result.output
    assert not recommendation_out.exists()


def test_program_architect_recommend_rejects_widened_candidate_row_effect(
    tmp_path: Path,
) -> None:
    tournament_path = tmp_path / "tournament.json"
    recommendation_out = tmp_path / "recommendation.json"
    tournament_path.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-tournament-v1",
                "status": "materialized_and_replay_checked",
                "evidence_matrix": {
                    "schema_version": "program-architecture-tournament-evidence-matrix-v1",
                    "rows": [
                        {
                            "candidate_id": "candidate_a",
                            "status": "skipped",
                            "reason": "test",
                            "effect": {"winner_selected": True},
                            "non_authority": {
                                "winner_selection": False,
                                "promotion_authority": False,
                                "oracle_ranking": False,
                            },
                        }
                    ],
                    "non_authority": {
                        "evidence_summary_only": True,
                        "winner_selection": False,
                        "promotion_authority": False,
                        "oracle_ranking": False,
                    },
                },
                "effect": {
                    "winner_selected": False,
                    "promotion_applied": False,
                    "ak_called": False,
                    "governance_mutated": False,
                    "external_authority_mutated": False,
                    "shared_oracle_mutated": False,
                },
                "non_authority": _recommendation_tournament_non_authority(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-architect",
            "recommend",
            "--tournament",
            str(tournament_path),
            "--out",
            str(recommendation_out),
        ],
    )

    assert result.exit_code == 2
    assert "row 0 effect widens authority" in result.output
    assert "winner_selected" in result.output
    assert not recommendation_out.exists()
