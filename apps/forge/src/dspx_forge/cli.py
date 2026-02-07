from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, cast

import typer

from dspx.config_loader import load_config_env
from dspx.policy import allow_network_mutate
from dspx.tracing import enable_mlflow_from_env
from dspx_forge.issues import (
    apply_issue_specs,
    build_issue_spec,
    close_marked_duplicates,
    default_paths,
    write_issue_specs,
)
from dspx_forge.models import Intent, Routing
from dspx_forge.overlaps import compute_overlaps, write_overlaps
from dspx_forge.plan import build_plan, write_plan
from dspx_forge.routing import route_candidates
from dspx_forge.workorder import build_workorder, load_workorder, write_workorder


app = typer.Typer(no_args_is_help=True, add_completion=False)
issues_app = typer.Typer(no_args_is_help=True)
app.add_typer(issues_app, name="issues", help="GitLab issues (apply/close-duplicates)")


def _ensure_env() -> None:
    load_config_env()
    enable_mlflow_from_env()


@app.command("intake")
def intake(
    prompt: Optional[str] = typer.Argument(
        None, help="Freeform prompt (or use --prompt-file)"
    ),
    prompt_file: Optional[Path] = typer.Option(
        None,
        "--prompt-file",
        help="Read prompt from file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    title: Optional[str] = typer.Option(
        None, "--title", help="WorkOrder title (default: first line of prompt)"
    ),
    deliverable: Optional[str] = typer.Option(
        None,
        "--deliverable",
        help="python_cli|library|server|workflow|optimizer|integration|eval_harness",
    ),
    evidence_level: Optional[str] = typer.Option(
        None, "--evidence", help="smoke|unit|golden|eval|perf"
    ),
    risk_profile: Optional[str] = typer.Option(
        None, "--risk", help="safe_default|power_user"
    ),
    primary_project: Optional[str] = typer.Option(
        None, "--primary-project", help="Routing primary project key (default: core)"
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Do not prompt; use defaults"
    ),
    out_root: Path = typer.Option(
        Path("generated/forge"),
        "--out-root",
        help="Output root; writes generated/forge/<workorder_id>/...",
        file_okay=False,
        dir_okay=True,
    ),
) -> None:
    _ensure_env()

    raw = ""
    if prompt_file is not None:
        raw = prompt_file.read_text(encoding="utf-8")
    else:
        raw = (prompt or "").strip()
    if not raw:
        raise typer.Exit(code=2)

    def _pick(val: Optional[str], *, name: str, default: str, allowed: set[str]) -> str:
        if val is not None and val.strip():
            v = val.strip()
        elif non_interactive:
            v = default
        else:
            v = typer.prompt(f"{name}", default=default).strip()
        if v not in allowed:
            typer.echo(f"invalid {name}: {v} (allowed: {sorted(allowed)})", err=True)
            raise typer.Exit(code=2)
        return v

    deliverable_lit = cast(
        Any,
        _pick(
            deliverable,
            name="deliverable",
            default="python_cli",
            allowed={
                "python_cli",
                "library",
                "server",
                "workflow",
                "optimizer",
                "integration",
                "eval_harness",
            },
        ),
    )
    evidence_lit = cast(
        Any,
        _pick(
            evidence_level,
            name="evidence_level",
            default="smoke",
            allowed={"smoke", "unit", "golden", "eval", "perf"},
        ),
    )
    risk_lit = cast(
        Any,
        _pick(
            risk_profile,
            name="risk_profile",
            default="safe_default",
            allowed={"safe_default", "power_user"},
        ),
    )
    it = Intent(
        deliverable=deliverable_lit,
        evidence_level=evidence_lit,
        risk_profile=risk_lit,
        offline_default=True,
    )
    rt = Routing(primary_project=(primary_project or "core"))

    doc = build_workorder(raw, title=title, intent=it, routing=rt, offline_default=True)
    paths = write_workorder(out_root, doc)
    typer.echo(str(paths.workorder_yaml))


@app.command("plan")
def plan(
    workorder: Path = typer.Argument(
        ..., help="Path to workorder.yaml", exists=True, file_okay=True, dir_okay=False
    ),
) -> None:
    _ensure_env()
    doc = load_workorder(workorder)
    out = write_plan(workorder.parent, build_plan(doc))
    typer.echo(str(out))


@app.command("route")
def route(
    workorder: Path = typer.Argument(
        ..., help="Path to workorder.yaml", exists=True, file_okay=True, dir_okay=False
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    _ensure_env()
    doc = load_workorder(workorder)
    wo = doc.work_order
    cands = route_candidates(wo.sanitized_input)
    if json_out:
        import json as _json

        typer.echo(
            _json.dumps(
                {
                    "current": wo.routing.model_dump(),
                    "candidates": [
                        {
                            "project_key": c.project_key,
                            "score": c.score,
                            "reasons": c.reasons,
                        }
                        for c in cands
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    typer.echo(f"current primary_project={wo.routing.primary_project}")
    typer.echo("candidates:")
    for c in cands:
        typer.echo(f"- {c.project_key} score={c.score} reasons={c.reasons}")


@app.command("overlaps")
def overlaps(
    workorder: Path = typer.Argument(
        ..., help="Path to workorder.yaml", exists=True, file_okay=True, dir_okay=False
    ),
) -> None:
    _ensure_env()
    doc = load_workorder(workorder)
    out = write_overlaps(workorder.parent, compute_overlaps(doc))
    typer.echo(str(out))


@issues_app.command("apply")
def issues_apply(
    workorder: Path = typer.Argument(
        ..., help="Path to workorder.yaml", exists=True, file_okay=True, dir_okay=False
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Perform GitLab mutations (default: dry-run)"
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Override project_key for generated IssueSpecs"
    ),
) -> None:
    _ensure_env()
    doc = load_workorder(workorder)
    paths = default_paths(workorder)
    specs = [build_issue_spec(doc, project_key=project)]
    write_issue_specs(paths, specs)

    if apply:
        from dspx_forge.gitlab_client import load_gitlab_config_from_env

        if not allow_network_mutate():
            typer.echo(
                "refusing to apply without --allow-network-mutate (or DSPX_POLICY_ALLOW_NETWORK_MUTATE=1)",
                err=True,
            )
            raise typer.Exit(code=2)
        try:
            load_gitlab_config_from_env()
        except Exception as e:
            typer.echo(f"GitLab not configured: {e}", err=True)
            raise typer.Exit(code=2) from e

    import json as _json

    manifest, results = apply_issue_specs(workorder, doc, specs, dry_run=not apply)
    typer.echo(
        _json.dumps(
            {"manifest": manifest.model_dump(), "results": results},
            ensure_ascii=False,
            indent=2,
        )
    )


@issues_app.command("close-duplicates")
def issues_close_duplicates(
    workorder: Path = typer.Argument(
        ..., help="Path to workorder.yaml", exists=True, file_okay=True, dir_okay=False
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Close marked duplicates in GitLab (default: dry-run)"
    ),
    allow_issue_close: bool = typer.Option(
        False,
        "--allow-issue-close",
        help="Required to close any issues (separate gate from --allow-network-mutate)",
    ),
) -> None:
    _ensure_env()

    if apply:
        from dspx_forge.gitlab_client import load_gitlab_config_from_env

        if not allow_network_mutate():
            typer.echo(
                "refusing to close issues without --allow-network-mutate (or DSPX_POLICY_ALLOW_NETWORK_MUTATE=1)",
                err=True,
            )
            raise typer.Exit(code=2)
        if not allow_issue_close:
            typer.echo("refusing to close issues without --allow-issue-close", err=True)
            raise typer.Exit(code=2)
        try:
            load_gitlab_config_from_env()
        except Exception as e:
            typer.echo(f"GitLab not configured: {e}", err=True)
            raise typer.Exit(code=2) from e

    import json as _json

    doc = load_workorder(workorder)
    manifest, results = close_marked_duplicates(workorder, doc, dry_run=not apply)
    typer.echo(
        _json.dumps(
            {"manifest": manifest.model_dump(), "results": results},
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
