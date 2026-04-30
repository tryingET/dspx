from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True)


@app.command("review")
def review(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to program-gen manifest.json",
    ),
    oracle_report: Path = typer.Option(
        ...,
        "--oracle-report",
        help="Path to explicit Oracle program-evidence report JSON",
    ),
    refinement_proposal: Path = typer.Option(
        ...,
        "--refinement-proposal",
        help="Path to explicit program refinement proposal JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the refined local promotion-review packet should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print review packet JSON"),
) -> None:
    """Build a refined local promotion-review packet without promotion authority."""
    from dspx.services.program_promotion_refinement import (
        ProgramPromotionRefinementError,
        build_program_promotion_refinement,
        write_program_promotion_refinement,
    )

    try:
        packet = build_program_promotion_refinement(
            manifest_path=manifest,
            oracle_report_path=oracle_report,
            refinement_proposal_path=refinement_proposal,
        )
        payload = write_program_promotion_refinement(packet, out)
    except ProgramPromotionRefinementError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program promotion review refinement failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("jury")
def jury(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to program-gen manifest.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local jury results sidecar should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print jury results JSON"),
) -> None:
    """Run local deterministic jury execution without promotion authority."""
    from dspx.services.program_jury_execution import (
        ProgramJuryExecutionError,
        build_program_jury_execution_result,
        write_program_jury_execution_result,
    )

    try:
        result = build_program_jury_execution_result(manifest_path=manifest)
        payload = write_program_jury_execution_result(result, out)
    except ProgramJuryExecutionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program jury execution failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("plan")
def plan(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to candidate program-candidate-assembly-v1 manifest.json",
    ),
    decision_record: Path = typer.Option(
        ...,
        "--decision-record",
        help="Path to local program-promotion-decision-record-v1 JSON",
    ),
    comparison: Path = typer.Option(
        ...,
        "--comparison",
        help="Path to program-refinement-candidate-comparison-v1 JSON",
    ),
    target: str = typer.Option(
        ...,
        "--target",
        help="Local non-mutating target kind for the plan",
    ),
    authority_owner: str = typer.Option(
        ...,
        "--authority-owner",
        help="Explicit local operator/adjudication authority owner identifier",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local promotion/adjudication plan should be written",
    ),
    review: Path | None = typer.Option(
        None,
        "--review",
        help="Optional program-promotion-review-refined-v1 JSON",
    ),
    source_manifest: Path | None = typer.Option(
        None,
        "--source-manifest",
        help="Optional source manifest used to verify comparison source identity",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print plan JSON"),
) -> None:
    """Build a local promotion/adjudication plan without applying promotion."""
    from dspx.services.program_promotion_plan import (
        ProgramPromotionPlanError,
        build_program_promotion_plan,
        write_program_promotion_plan,
    )

    try:
        plan_payload = build_program_promotion_plan(
            manifest_path=manifest,
            decision_record_path=decision_record,
            comparison_path=comparison,
            target=target,
            authority_owner=authority_owner,
            review_path=review,
            source_manifest_path=source_manifest,
        )
        payload = write_program_promotion_plan(plan_payload, out)
    except ProgramPromotionPlanError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program promotion planning failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("status")
def status(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to candidate program-candidate-assembly-v1 manifest.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local candidate truth-state sidecar should be written",
    ),
    source_manifest: Path | None = typer.Option(
        None,
        "--source-manifest",
        help="Optional source manifest when the candidate state includes refinement lineage",
    ),
    oracle_report: Path | None = typer.Option(
        None,
        "--oracle-report",
        help="Optional program-oracle-evidence-report-v1 JSON",
    ),
    refinement_proposal: Path | None = typer.Option(
        None,
        "--refinement-proposal",
        help="Optional program-refinement-proposal-v1 JSON",
    ),
    review: Path | None = typer.Option(
        None,
        "--review",
        help="Optional program-promotion-review-refined-v1 JSON",
    ),
    decision_record: Path | None = typer.Option(
        None,
        "--decision-record",
        help="Optional program-promotion-decision-record-v1 JSON",
    ),
    comparison: Path | None = typer.Option(
        None,
        "--comparison",
        help="Optional program-refinement-candidate-comparison-v1 JSON",
    ),
    promotion_plan: Path | None = typer.Option(
        None,
        "--promotion-plan",
        help="Optional program-promotion-plan-v1 JSON",
    ),
    export_preflight: Path | None = typer.Option(
        None,
        "--export-preflight",
        help="Optional program-external-authority-export-preflight-v1 JSON",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print state JSON"),
) -> None:
    """Summarize the local truth state for one program candidate."""
    from dspx.services.program_candidate_state import (
        ProgramCandidateStateError,
        build_program_candidate_state,
        write_program_candidate_state,
    )

    try:
        state = build_program_candidate_state(
            manifest_path=manifest,
            out_path=out,
            source_manifest_path=source_manifest,
            oracle_report_path=oracle_report,
            refinement_proposal_path=refinement_proposal,
            review_path=review,
            decision_record_path=decision_record,
            comparison_path=comparison,
            promotion_plan_path=promotion_plan,
            export_preflight_path=export_preflight,
        )
        payload = write_program_candidate_state(state, out)
    except ProgramCandidateStateError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program candidate state summarization failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("decide")
def decide(
    review: Path = typer.Option(
        ...,
        "--review",
        help="Path to program-promotion-review-refined-v1 JSON",
    ),
    outcome: str = typer.Option(
        ...,
        "--outcome",
        help="Decision outcome: withhold, reject, request_more_evidence, or promote",
    ),
    decided_by: str = typer.Option(
        ...,
        "--decided-by",
        help="Explicit local operator/adjudicator identifier",
    ),
    rationale: str = typer.Option(
        ...,
        "--rationale",
        help="Non-empty rationale for the local decision record",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local decision sidecar should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print decision record JSON"),
) -> None:
    """Record a local adjudicator decision sidecar without promotion authority."""
    from dspx.services.program_promotion_decision import (
        ProgramPromotionDecisionError,
        build_program_promotion_decision_record,
        write_program_promotion_decision_record,
    )

    try:
        record = build_program_promotion_decision_record(
            refined_review_path=review,
            outcome=outcome,
            decided_by=decided_by,
            rationale=rationale,
        )
        payload = write_program_promotion_decision_record(record, out)
    except ProgramPromotionDecisionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program promotion decision recording failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))
