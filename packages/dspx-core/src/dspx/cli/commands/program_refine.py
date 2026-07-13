# summary: "Defines bounded local program refinement, GEPA candidate, comparison, and guided episode commands."
# read_when:
#   - "Changing refinement proposals, candidate materialization, GEPA workflows, comparisons, or episode orchestration."

from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True)


@app.command("execute-foundry-gepa")
def execute_foundry_gepa(
    proposal: Path = typer.Option(
        ...,
        "--proposal",
        help="Canonical foundry gepa_experiment_proposal.json sidecar",
    ),
    declare_reviewed: str = typer.Option(
        ...,
        "--declare-reviewed",
        help="Exact proposal_id declaring explicit review and one execution request",
    ),
    operator_label: str = typer.Option(
        ...,
        "--operator-label",
        help="Unauthenticated operator-supplied label recorded with execution intent",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print execution receipt JSON"),
) -> None:
    """Execute one reviewed foundry GEPA proposal without replay or promotion."""
    from dspx.services.program_foundry_gepa_execution import (
        ProgramFoundryGepaExecutionError,
        execute_reviewed_program_foundry_gepa,
    )

    try:
        payload = execute_reviewed_program_foundry_gepa(
            proposal_path=proposal,
            declared_reviewed=declare_reviewed,
            operator_label=operator_label,
        )
    except ProgramFoundryGepaExecutionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: foundry GEPA effect may be indeterminate: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(proposal.parent / "gepa-experiment" / "execution-receipt.json"))
        typer.echo(f"foundry_gepa_status: {payload.get('status')}")
    if payload.get("status") == "blocked_indeterminate":
        raise typer.Exit(code=3)
    if payload.get("status") != "ok":
        raise typer.Exit(code=1)


@app.command("consume-foundry-gepa-receipt")
def consume_foundry_gepa_receipt(
    receipt: Path = typer.Option(
        ...,
        "--receipt",
        help="Canonical successful foundry GEPA execution-receipt.json",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print consumption receipt JSON"
    ),
) -> None:
    """Materialize and compare one GEPA candidate from one successful receipt."""
    from dspx.services.program_foundry_gepa_consumption import (
        ProgramFoundryGepaConsumptionError,
        consume_successful_program_foundry_gepa_receipt,
    )

    try:
        payload = consume_successful_program_foundry_gepa_receipt(
            execution_receipt_path=receipt,
        )
    except ProgramFoundryGepaConsumptionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: candidate materialization/comparison may be indeterminate: {exc}",
            err=True,
        )
        raise typer.Exit(code=3) from exc
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(receipt.parent / "consumption-receipt.json"))
        typer.echo(f"foundry_gepa_consumption_status: {payload.get('status')}")
    if payload.get("status") == "blocked_indeterminate":
        raise typer.Exit(code=3)
    if payload.get("status") != "ok":
        raise typer.Exit(code=1)


@app.command("jury-foundry-gepa-comparison")
def jury_foundry_gepa_comparison(
    receipt: Path = typer.Option(
        ...,
        "--receipt",
        help="Canonical successful foundry GEPA consumption-receipt.json",
    ),
    provider: str = typer.Option(
        ...,
        "--provider",
        help="Explicit provider for program-specific juror calls",
    ),
    adjudicator_id: str = typer.Option(
        "local_foundry_adjudicator",
        "--adjudicator-id",
        help="Local downstream adjudicator id recorded without transition authority",
    ),
    adjudicator_kind: str = typer.Option(
        "local_foundry_adjudicator",
        "--adjudicator-kind",
        help="Local downstream adjudicator kind",
    ),
    adjudicator_repo: str | None = typer.Option(
        None,
        "--adjudicator-repo",
        help="Owning repo for downstream adjudication, when known",
    ),
    max_jurors: int | None = typer.Option(
        None,
        "--max-jurors",
        help="Optional positive bound on selected program-specific jurors",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print jury receipt JSON"),
) -> None:
    """Run one receipt-bound program-specific jury without transition authority."""
    from dspx.services.program_foundry_gepa_comparison_jury import (
        ProgramFoundryGepaComparisonJuryError,
        execute_program_foundry_gepa_comparison_jury,
    )

    try:
        payload = execute_program_foundry_gepa_comparison_jury(
            consumption_receipt_path=receipt,
            provider=provider,
            adjudicator_id=adjudicator_id,
            adjudicator_kind=adjudicator_kind,
            adjudicator_repo=adjudicator_repo,
            max_jurors=max_jurors,
        )
    except ProgramFoundryGepaComparisonJuryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: one or more comparison-jury provider calls may have occurred: {exc}",
            err=True,
        )
        raise typer.Exit(code=3) from exc
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(receipt.parent / "comparison-jury-receipt.json"))
        typer.echo(f"foundry_gepa_comparison_jury_status: {payload.get('status')}")
    if payload.get("status") == "blocked_indeterminate":
        raise typer.Exit(code=3)
    if payload.get("status") != "ok":
        raise typer.Exit(code=1)


@app.command("adjudicate-foundry-gepa-comparison")
def adjudicate_foundry_gepa_comparison(
    receipt: Path = typer.Option(
        ...,
        "--receipt",
        help="Canonical successful foundry GEPA comparison-jury-receipt.json",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Print bounded local adjudication JSON",
    ),
) -> None:
    """Run the built-in deterministic adjudicator backend over jury evidence."""
    from dspx.services.program_foundry_gepa_comparison_adjudication import (
        ProgramFoundryGepaComparisonAdjudicationError,
        adjudicate_program_foundry_gepa_comparison,
    )

    try:
        payload = adjudicate_program_foundry_gepa_comparison(
            comparison_jury_receipt_path=receipt,
        )
    except ProgramFoundryGepaComparisonAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(receipt.parent / "comparison-adjudication.json"))
        typer.echo(f"local_disposition: {payload.get('disposition')}")
        typer.echo(f"reused: {payload.get('reused')}")


@app.command("select-adjudicator")
def select_adjudicator(
    task_kind: str = typer.Option(
        "foundry_gepa_comparison",
        "--task-kind",
        help="Exact task kind requiring an adjudicator",
    ),
    registration: list[Path] = typer.Option(
        [],
        "--registration",
        help="Task adjudicator registration JSON (repeatable)",
    ),
    builtin_fallback: bool = typer.Option(
        True,
        "--builtin-fallback/--no-builtin-fallback",
        help="Allow the built-in deterministic foundry adjudicator when no registration matches",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print selection JSON"),
) -> None:
    """Select a task-specific adjudicator without executing or authenticating it."""
    from dspx.services.program_adjudicator_protocol import (
        ProgramAdjudicatorProtocolError,
        load_task_adjudicator_registration,
        select_task_adjudicator,
    )

    try:
        loaded = [
            (path, *load_task_adjudicator_registration(path)) for path in registration
        ]
        payload = select_task_adjudicator(
            task_kind=task_kind,
            registrations=[item[1] for item in loaded],
            include_builtin_fallback=builtin_fallback,
        )
        payload["registration_sources"] = [
            {
                "path": str(path.expanduser().resolve()),
                "sha256": digest,
                "registration_id": registration_payload["registration_id"],
            }
            for path, registration_payload, digest in loaded
        ]
    except ProgramAdjudicatorProtocolError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(f"selection_status: {payload.get('status')}")
        typer.echo(f"disposition: {payload.get('disposition')}")
        selected = payload.get("selected_registration")
        if isinstance(selected, dict):
            typer.echo(f"adjudicator_kind: {selected.get('backend', {}).get('kind')}")
            typer.echo(
                f"execution_support: {selected.get('backend', {}).get('execution_support')}"
            )
    if payload.get("status") == "require_review":
        raise typer.Exit(code=1)


@app.command("dispatch-foundry-gepa-adjudicator")
def dispatch_foundry_gepa_adjudicator(
    receipt: Path = typer.Option(
        ...,
        "--receipt",
        help="Canonical successful foundry GEPA comparison-jury-receipt.json",
    ),
    registration: list[Path] = typer.Option(
        [],
        "--registration",
        help="Task adjudicator registration JSON (repeatable)",
    ),
    builtin_fallback: bool = typer.Option(
        True,
        "--builtin-fallback/--no-builtin-fallback",
        help="Use the trusted built-in deterministic backend when no registration matches",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print dispatch JSON"),
) -> None:
    """Persist one receipt-bound request and execute no external adjudicator."""
    from dspx.services.program_foundry_gepa_adjudicator_dispatch import (
        ProgramFoundryGepaAdjudicatorDispatchError,
        ProgramFoundryGepaAdjudicatorDispatchIndeterminateError,
        dispatch_program_foundry_gepa_comparison_adjudicator,
    )

    try:
        payload = dispatch_program_foundry_gepa_comparison_adjudicator(
            comparison_jury_receipt_path=receipt,
            registration_paths=registration,
            include_builtin_fallback=builtin_fallback,
        )
    except ProgramFoundryGepaAdjudicatorDispatchIndeterminateError as exc:
        typer.echo(
            f"Error: adjudicator request publication may have committed: {exc}",
            err=True,
        )
        raise typer.Exit(code=3) from exc
    except ProgramFoundryGepaAdjudicatorDispatchError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(f"dispatch_status: {payload.get('status')}")
        typer.echo(f"disposition: {payload.get('disposition')}")
        typer.echo(f"request_path: {payload.get('request_path')}")
    if payload.get("status") == "require_review":
        raise typer.Exit(code=1)


@app.command("record-foundry-gepa-adjudicator-submission")
def record_foundry_gepa_adjudicator_submission(
    request: Path = typer.Option(
        ...,
        "--request",
        help="Canonical pending comparison-adjudicator-request.json",
    ),
    registration: list[Path] = typer.Option(
        ...,
        "--registration",
        help="Exact registration source used by dispatch (repeatable)",
    ),
    declare_request_id: str = typer.Option(
        ...,
        "--declare-request-id",
        help="Exact request_id acknowledging the pending dispatch request",
    ),
    subject: str = typer.Option(
        ...,
        "--subject",
        help="Caller-declared human subject label from the selected registration",
    ),
    disposition: str = typer.Option(
        ...,
        "--disposition",
        help="Claimed disposition: promote_locally, reject_locally, require_review, or abstain",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print unverified submission receipt JSON"
    ),
) -> None:
    """Record an unverified human claim that cannot satisfy quorum or transition."""
    from dspx.services.program_foundry_gepa_adjudicator_submission import (
        ProgramFoundryGepaAdjudicatorSubmissionError,
        ProgramFoundryGepaAdjudicatorSubmissionIndeterminateError,
        record_program_foundry_gepa_adjudicator_submission,
    )

    try:
        payload = record_program_foundry_gepa_adjudicator_submission(
            request_path=request,
            registration_paths=registration,
            declared_request_id=declare_request_id,
            subject=subject,
            disposition=disposition,
        )
    except ProgramFoundryGepaAdjudicatorSubmissionIndeterminateError as exc:
        typer.echo(
            f"Error: unverified submission receipt may have committed: {exc}", err=True
        )
        raise typer.Exit(code=3) from exc
    except ProgramFoundryGepaAdjudicatorSubmissionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(f"submission_status: {payload.get('status')}")
        typer.echo(
            f"counts_toward_quorum: {payload.get('effect', {}).get('counts_toward_quorum')}"
        )
        typer.echo(f"path: {payload.get('path')}")


@app.command("import-foundry-gepa-adjudicator-completion")
def import_foundry_gepa_adjudicator_completion(
    request: Path = typer.Option(
        ..., "--request", help="Canonical pending comparison-adjudicator-request.json"
    ),
    registration: list[Path] = typer.Option(
        ...,
        "--registration",
        help="Exact registration source used by dispatch (repeatable)",
    ),
    completion: Path = typer.Option(
        ..., "--completion", help="Externally signed owner completion receipt JSON"
    ),
    verifier_policy: Path = typer.Option(
        ...,
        "--verifier-policy",
        help="Scoped external verifier trust-policy JSON",
    ),
    trusted_policy_sha256: str = typer.Option(
        ...,
        "--trusted-policy-sha256",
        help="Out-of-band trusted SHA-256 pin for canonical verifier-policy JSON",
    ),
    declare_request_id: str = typer.Option(
        ..., "--declare-request-id", help="Exact pending dispatch request_id"
    ),
    declare_owner_receipt_id: str = typer.Option(
        ...,
        "--declare-owner-receipt-id",
        help="Exact externally assigned owner completion receipt id",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print terminal completion receipt JSON"
    ),
) -> None:
    """Import signed verification under a digest-pinned scoped trust policy."""
    from dspx.services.program_foundry_gepa_adjudicator_completion import (
        ProgramFoundryGepaAdjudicatorCompletionError,
        ProgramFoundryGepaAdjudicatorCompletionIndeterminateError,
        import_program_foundry_gepa_adjudicator_completion,
    )

    try:
        payload = import_program_foundry_gepa_adjudicator_completion(
            request_path=request,
            registration_paths=registration,
            owner_completion_path=completion,
            verifier_policy_path=verifier_policy,
            trusted_policy_sha256=trusted_policy_sha256,
            declared_request_id=declare_request_id,
            expected_owner_receipt_id=declare_owner_receipt_id,
        )
    except ProgramFoundryGepaAdjudicatorCompletionIndeterminateError as exc:
        typer.echo(
            f"Error: terminal adjudicator completion may have committed: {exc}",
            err=True,
        )
        raise typer.Exit(code=3) from exc
    except ProgramFoundryGepaAdjudicatorCompletionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(f"completion_status: {payload.get('status')}")
        typer.echo(f"disposition: {payload.get('disposition')}")
        typer.echo(
            f"quorum_satisfied: {payload.get('quorum', {}).get('quorum_satisfied')}"
        )
        typer.echo(f"path: {payload.get('path')}")


@app.command("optimize-gepa")
def optimize_gepa(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to an existing program-candidate-assembly-v1 manifest.json",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory where local GEPA optimizer output may be written",
    ),
    result_out: Path = typer.Option(
        ...,
        "--result-out",
        help="Path where the local GEPA refinement result sidecar should be written",
    ),
    train: Path | None = typer.Option(
        None,
        "--train",
        help="Optional explicit train JSONL file shaped like program examples",
    ),
    validation: Path | None = typer.Option(
        None,
        "--validation",
        help="Optional explicit validation JSONL file shaped like program examples",
    ),
    metric: str | None = typer.Option(
        None,
        "--metric",
        help="Optional metric override: exact_match/exact, contains, or f1",
    ),
    max_metric_calls: int = typer.Option(
        2,
        "--max-metric-calls",
        help="Bounded GEPA metric-call budget",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print result JSON"),
) -> None:
    """Run a local GEPA-backed refinement attempt without promotion authority."""
    from dspx.services.program_refinement_gepa import (
        ProgramRefinementGepaError,
        build_program_refinement_gepa_result,
        write_program_refinement_gepa_result,
    )

    try:
        result = build_program_refinement_gepa_result(
            manifest_path=manifest,
            outdir=outdir,
            train_path=train,
            validation_path=validation,
            metric=metric,
            max_metric_calls=max_metric_calls,
            result_out=result_out,
        )
        payload = write_program_refinement_gepa_result(result, result_out)
    except ProgramRefinementGepaError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program GEPA refinement failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(result_out.expanduser().resolve()))


@app.command("materialize-gepa-candidate")
def materialize_gepa_candidate(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to source program-candidate-assembly-v1 manifest.json",
    ),
    gepa_result: Path = typer.Option(
        ...,
        "--gepa-result",
        help="Path to ready program-refinement-gepa-result-v1 JSON",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory where the GEPA-backed local candidate assembly is materialized",
    ),
    result_out: Path | None = typer.Option(
        None,
        "--result-out",
        help="Optional path for program-refinement-gepa-candidate-result-v1 JSON",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print result JSON"),
) -> None:
    """Materialize one local candidate from hash-bound GEPA optimizer output."""
    from dspx.services.program_refinement_gepa_candidate import (
        ProgramRefinementGepaCandidateError,
        materialize_gepa_refinement_candidate,
    )

    try:
        payload = materialize_gepa_refinement_candidate(
            manifest_path=manifest,
            gepa_result_path=gepa_result,
            outdir=outdir,
            result_out=result_out,
        )
    except ProgramRefinementGepaCandidateError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program GEPA candidate materialization failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(outdir.expanduser().resolve()))


@app.command("materialize-and-compare-gepa-candidate")
def materialize_and_compare_gepa_candidate(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to source program-candidate-assembly-v1 manifest.json",
    ),
    gepa_result: Path = typer.Option(
        ...,
        "--gepa-result",
        help="Path to ready program-refinement-gepa-result-v1 JSON",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory where the GEPA-backed local candidate assembly is materialized",
    ),
    comparison_out: Path = typer.Option(
        ...,
        "--comparison-out",
        help="Path where the local source-vs-GEPA-candidate comparison sidecar is written",
    ),
    gepa_candidate_result_out: Path | None = typer.Option(
        None,
        "--gepa-candidate-result-out",
        help="Optional path for the GEPA candidate materialization result sidecar",
    ),
    workflow_out: Path | None = typer.Option(
        None,
        "--workflow-out",
        help="Optional path for the GEPA materialize-and-compare workflow result sidecar",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print workflow result JSON"),
) -> None:
    """Materialize one local GEPA candidate, then compare it without promotion."""
    from dspx.services.program_refinement_workflow import (
        ProgramRefinementWorkflowError,
        assert_distinct_workflow_output_paths,
        materialize_and_compare_gepa_refinement_candidate,
        write_program_refinement_workflow_result,
    )

    try:
        assert_distinct_workflow_output_paths(
            artifact_label="program GEPA materialize-and-compare workflow",
            source_root=manifest.expanduser().resolve().parent,
            outdir=outdir,
            comparison_out=comparison_out,
            gepa_candidate_result_out=gepa_candidate_result_out,
            workflow_out=workflow_out,
        )
        payload = materialize_and_compare_gepa_refinement_candidate(
            manifest_path=manifest,
            gepa_result_path=gepa_result,
            outdir=outdir,
            comparison_out_path=comparison_out,
            gepa_candidate_result_out=gepa_candidate_result_out,
        )
        if workflow_out is not None:
            payload = write_program_refinement_workflow_result(payload, workflow_out)
    except ProgramRefinementWorkflowError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program GEPA materialize-and-compare failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(comparison_out.expanduser().resolve()))


@app.command("episode")
def episode(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to an existing program-candidate-assembly-v1 manifest.json",
    ),
    oracle_report: Path = typer.Option(
        ...,
        "--oracle-report",
        help="Path to explicit non-authoritative Oracle program-evidence report JSON",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory where local refinement-episode sidecars should be written",
    ),
    decision_outcome: str = typer.Option(
        ...,
        "--decision-outcome",
        help="Explicit local decision outcome; use request_more_evidence to generate a second candidate",
    ),
    decided_by: str = typer.Option(
        ...,
        "--decided-by",
        help="Explicit local operator/adjudicator identifier for the decision record",
    ),
    rationale: str = typer.Option(
        ...,
        "--rationale",
        help="Explicit rationale for the local decision record",
    ),
    generate_second_candidate: bool = typer.Option(
        True,
        "--generate-second-candidate/--no-generate-second-candidate",
        help="When true, materialize one local second candidate and compare it; requires request_more_evidence",
    ),
    proposal_out: Path | None = typer.Option(
        None,
        "--proposal-out",
        help="Optional explicit path for the refinement proposal sidecar",
    ),
    review_out: Path | None = typer.Option(
        None,
        "--review-out",
        help="Optional explicit path for the refined promotion-review packet",
    ),
    decision_out: Path | None = typer.Option(
        None,
        "--decision-out",
        help="Optional explicit path for the local decision record",
    ),
    comparison_out: Path | None = typer.Option(
        None,
        "--comparison-out",
        help="Optional explicit path for the candidate comparison sidecar",
    ),
    state_out: Path | None = typer.Option(
        None,
        "--state-out",
        help="Optional explicit path for the refreshed candidate-state summary",
    ),
    workflow_out: Path | None = typer.Option(
        None,
        "--workflow-out",
        help="Optional explicit path for the refinement episode summary",
    ),
    promotion_plan: bool = typer.Option(
        False,
        "--promotion-plan/--no-promotion-plan",
        help="Optionally write a local non-authoritative promotion/adjudication plan over the second candidate",
    ),
    promotion_plan_target: str | None = typer.Option(
        None,
        "--promotion-plan-target",
        help="Required with --promotion-plan; local plan target such as local_preferred_candidate",
    ),
    promotion_plan_authority_owner: str | None = typer.Option(
        None,
        "--promotion-plan-authority-owner",
        help="Required with --promotion-plan; explicit local authority-owner identifier",
    ),
    promotion_plan_out: Path | None = typer.Option(
        None,
        "--promotion-plan-out",
        help="Optional explicit path for the local promotion/adjudication plan sidecar",
    ),
    jury_results: Path | None = typer.Option(
        None,
        "--jury-results",
        help="Optional local deterministic program-jury-results-v2 JSON to consume as evidence only",
    ),
    run_local_jury: bool = typer.Option(
        False,
        "--run-local-jury/--no-run-local-jury",
        help="Generate one local deterministic jury-results sidecar and consume it as evidence only",
    ),
    jury_results_out: Path | None = typer.Option(
        None,
        "--jury-results-out",
        help="Optional output path for --run-local-jury program-jury-results-v2 evidence",
    ),
    meta_adjudication_plan: bool = typer.Option(
        False,
        "--meta-adjudication-plan/--no-meta-adjudication-plan",
        help="Optionally write a local non-authoritative meta-adjudication plan over source-candidate episode evidence",
    ),
    meta_adjudication_plan_out: Path | None = typer.Option(
        None,
        "--meta-adjudication-plan-out",
        help="Optional output path for --meta-adjudication-plan program-meta-adjudication-plan-v1 evidence",
    ),
    model_jury_results: Path | None = typer.Option(
        None,
        "--model-jury-results",
        help="Optional provider-backed program-model-jury-results-v1 JSON to consume as local evidence only",
    ),
    external_ref: str | None = typer.Option(
        None,
        "--external-ref",
        help="Optional opaque external authority ref for local export-preflight generation",
    ),
    export_preflight_out: Path | None = typer.Option(
        None,
        "--export-preflight-out",
        help="Optional path for a generated program-external-authority-export-preflight-v1 sidecar",
    ),
    second_candidate_outdir: Path | None = typer.Option(
        None,
        "--second-candidate-outdir",
        help="Optional directory where the proposal-derived second candidate assembly is materialized",
    ),
    gepa_result: Path | None = typer.Option(
        None,
        "--gepa-result",
        help="Optional ready program-refinement-gepa-result-v1 sidecar to materialize and compare as the episode candidate",
    ),
    gepa_candidate_outdir: Path | None = typer.Option(
        None,
        "--gepa-candidate-outdir",
        help="Optional directory where the GEPA-backed candidate assembly is materialized",
    ),
    gepa_candidate_result_out: Path | None = typer.Option(
        None,
        "--gepa-candidate-result-out",
        help="Optional path for the GEPA candidate materialization result sidecar",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print workflow JSON"),
) -> None:
    """Run one guided local refinement episode without authority effects."""
    from dspx.services.program_refinement_episode import (
        ProgramRefinementEpisodeError,
        run_program_refinement_episode,
    )

    try:
        payload = run_program_refinement_episode(
            manifest_path=manifest,
            oracle_report_path=oracle_report,
            sidecar_outdir=outdir,
            decision_outcome=decision_outcome,
            decided_by=decided_by,
            rationale=rationale,
            generate_second_candidate=generate_second_candidate,
            proposal_out=proposal_out,
            review_out=review_out,
            decision_out=decision_out,
            comparison_out=comparison_out,
            state_out=state_out,
            workflow_out=workflow_out,
            second_candidate_outdir=second_candidate_outdir,
            generate_promotion_plan=promotion_plan,
            promotion_plan_target=promotion_plan_target,
            promotion_plan_authority_owner=promotion_plan_authority_owner,
            promotion_plan_out=promotion_plan_out,
            jury_results_path=jury_results,
            run_local_jury=run_local_jury,
            jury_results_out=jury_results_out,
            generate_meta_adjudication_plan=meta_adjudication_plan,
            meta_adjudication_plan_out=meta_adjudication_plan_out,
            model_jury_results_path=model_jury_results,
            export_preflight_out=export_preflight_out,
            external_ref=external_ref,
            gepa_result_path=gepa_result,
            gepa_candidate_outdir=gepa_candidate_outdir,
            gepa_candidate_result_out=gepa_candidate_result_out,
        )
    except ProgramRefinementEpisodeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program refinement episode failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(payload.get("workflow_path") or workflow_out or outdir))
        decision = (payload.get("steps") or {}).get("decision_record") or {}
        state = (payload.get("steps") or {}).get("candidate_state") or {}
        typer.echo(f"decision: {decision.get('outcome')}")
        typer.echo(f"candidate_state: {state.get('status')}")


@app.command("propose")
def propose(
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
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local refinement proposal artifact should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print proposal JSON"),
) -> None:
    """Propose a bounded program refinement without applying changes."""
    from dspx.services.program_refinement import (
        ProgramRefinementError,
        build_program_refinement_proposal,
        write_program_refinement_proposal,
    )

    try:
        proposal = build_program_refinement_proposal(
            manifest_path=manifest,
            oracle_report_path=oracle_report,
        )
        payload = write_program_refinement_proposal(proposal, out)
    except ProgramRefinementError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program refinement proposal failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("compare-candidates")
def compare_candidates(
    source_manifest: Path = typer.Option(
        ...,
        "--source-manifest",
        help="Path to source program-candidate-assembly-v1 manifest.json",
    ),
    candidate_manifest: Path = typer.Option(
        ...,
        "--candidate-manifest",
        help="Path to refinement candidate program-candidate-assembly-v1 manifest.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local candidate comparison sidecar should be written",
    ),
    refinement_proposal: Path | None = typer.Option(
        None,
        "--refinement-proposal",
        help="Optional program-refinement-proposal-v1 lineage input",
    ),
    decision_record: Path | None = typer.Option(
        None,
        "--decision-record",
        help="Optional program-promotion-decision-record-v1 lineage input",
    ),
    source_runtime_episode: Path | None = typer.Option(
        None,
        "--source-runtime-episode",
        help="Optional source program-runtime-episode-v1 JSON from program-run",
    ),
    candidate_runtime_episode: Path | None = typer.Option(
        None,
        "--candidate-runtime-episode",
        help="Optional candidate program-runtime-episode-v1 JSON from program-run",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print comparison JSON"),
) -> None:
    """Compare existing source and refinement candidates without authority effects."""
    from dspx.services.program_refinement_comparison import (
        ProgramRefinementComparisonError,
        build_program_refinement_candidate_comparison,
        write_program_refinement_candidate_comparison,
    )

    try:
        comparison = build_program_refinement_candidate_comparison(
            source_manifest_path=source_manifest,
            candidate_manifest_path=candidate_manifest,
            refinement_proposal_path=refinement_proposal,
            decision_record_path=decision_record,
            source_runtime_episode_path=source_runtime_episode,
            candidate_runtime_episode_path=candidate_runtime_episode,
        )
        payload = write_program_refinement_candidate_comparison(comparison, out)
    except ProgramRefinementComparisonError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program refinement candidate comparison failed: {exc}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("generate-and-compare")
def generate_and_compare(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to source program-gen manifest.json",
    ),
    refinement_proposal: Path = typer.Option(
        ...,
        "--refinement-proposal",
        help="Path to program-refinement-proposal-v1 JSON",
    ),
    decision_record: Path = typer.Option(
        ...,
        "--decision-record",
        help="Path to local request-more-evidence decision record JSON",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory where the second candidate assembly is materialized",
    ),
    comparison_out: Path = typer.Option(
        ...,
        "--comparison-out",
        help="Path where the local candidate comparison sidecar should be written",
    ),
    workflow_out: Path | None = typer.Option(
        None,
        "--workflow-out",
        help="Optional path for a local generate-and-compare workflow result sidecar",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print workflow result JSON"),
) -> None:
    """Generate one local second candidate, then compare it without promotion."""
    from dspx.services.program_refinement_workflow import (
        ProgramRefinementWorkflowError,
        assert_distinct_workflow_output_paths,
        materialize_and_compare_refinement_candidate,
        write_program_refinement_workflow_result,
    )

    try:
        assert_distinct_workflow_output_paths(
            artifact_label="program refinement generate-and-compare workflow",
            source_root=manifest.expanduser().resolve().parent,
            outdir=outdir,
            comparison_out=comparison_out,
            workflow_out=workflow_out,
        )
        payload = materialize_and_compare_refinement_candidate(
            manifest_path=manifest,
            refinement_proposal_path=refinement_proposal,
            decision_record_path=decision_record,
            outdir=outdir,
            comparison_out_path=comparison_out,
        )
        if workflow_out is not None:
            payload = write_program_refinement_workflow_result(payload, workflow_out)
    except ProgramRefinementWorkflowError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program refinement generate-and-compare failed: {exc}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(comparison_out.expanduser().resolve()))


@app.command("generate-candidate")
def generate_candidate(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to source program-gen manifest.json",
    ),
    refinement_proposal: Path = typer.Option(
        ...,
        "--refinement-proposal",
        help="Path to program-refinement-proposal-v1 JSON",
    ),
    decision_record: Path = typer.Option(
        ...,
        "--decision-record",
        help="Path to local program-promotion-decision-record-v1 JSON",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory where the second candidate assembly is materialized",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print candidate result JSON"),
) -> None:
    """Generate one explicit local second candidate from a request-more-evidence path."""
    from dspx.services.program_refinement_candidate import (
        ProgramRefinementCandidateError,
        materialize_refinement_candidate,
    )

    try:
        payload = materialize_refinement_candidate(
            manifest_path=manifest,
            refinement_proposal_path=refinement_proposal,
            decision_record_path=decision_record,
            outdir=outdir,
        )
    except ProgramRefinementCandidateError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program refinement candidate generation failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(outdir.expanduser().resolve()))
