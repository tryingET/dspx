# summary: "Shared intent and non-authority fixtures for program architecture recommendation and tournament tests."
# read_when:
#   - "Testing architecture candidates, tournaments, recommendations, or their non-authority contract."

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

runner = CliRunner()


def _recommendation_tournament_non_authority() -> dict[str, bool]:
    return {
        "winner_selection": False,
        "ranking_authority": False,
        "promotion_authority": False,
        "activation_authority": False,
        "oracle_authority": False,
        "governance_authority": False,
        "external_mutation": False,
        "canonical_mutation": False,
    }


def _write_intent(path: Path, objective: str, *, examples: bool = False) -> None:
    lines = [
        "schema_version: program-intent-v2",
        "name: ArchitectDogfoodProgram",
        f"objective: {objective}",
        "inputs:",
        "  - ticket_text",
        "outputs:",
        "  - response",
        "metric: exact_match",
    ]
    if examples:
        lines.extend(
            [
                "examples:",
                "  - inputs:",
                "      ticket_text: I was charged twice for my subscription.",
                "    outputs:",
                "      response: This is a billing issue.",
            ]
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
