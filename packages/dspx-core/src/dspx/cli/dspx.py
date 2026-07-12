# summary: "Wires the main DSPx CLI, program generation/runtime workflows, inline generators, and global policy setup."
# read_when:
#   - "Changing top-level commands, program workflows, generation gates, artifact logging, or global CLI policy options."

"""Main dspx CLI entrypoint.

This is a thin orchestrator that wires up command groups from
dspx.cli.commands modules. Command implementations live in their
respective modules for maintainability.

Note: codegen and module-gen are kept inline as single commands.
"""

from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional

import typer

from dspx.cli.utils import (
    ensure_env,
    require_template_adapter,
    check_template_adapter_available,
    sanitize_cli_error,
    _TEMPLATE_ADAPTER_AVAILABLE,
)
from dspx.tracing import enable_mlflow_from_env

# Re-exports for backward compatibility with tests
__all__ = [
    "app",
    "enable_mlflow_from_env",
    "check_template_adapter_available",
    "_TEMPLATE_ADAPTER_AVAILABLE",
]

# Import extracted command apps
from dspx.cli.commands import (
    cache_app,
    run_app,
    optimize_app,
    providers_app,
    program_promote_app,
    program_refine_app,
    program_architect_app,
    oracle_app,
    signature_app,
    mermaid_app,
    openapi_app,
    web_app,
    tools_app,
    adapters_app,
    adapters_dataset_app,
    adapters_eval_app,
)

# Main app
app = typer.Typer(no_args_is_help=True, add_completion=False)

# Register command groups (imported from extracted modules)
app.add_typer(signature_app, name="signature", help="Signature operations")
app.add_typer(mermaid_app, name="mermaid", help="Mermaid workflow operations")
app.add_typer(providers_app, name="providers", help="Provider utilities")
app.add_typer(tools_app, name="tools", help="Tools and integrations")
tools_app.add_typer(openapi_app, name="openapi", help="OpenAPI loader/caller")
tools_app.add_typer(web_app, name="web", help="Web tools (fetch/scrape)")
app.add_typer(adapters_app, name="adapters", help="Adapters (datasets/eval/stores)")
adapters_app.add_typer(adapters_dataset_app, name="dataset", help="Dataset adapters")
adapters_app.add_typer(adapters_eval_app, name="eval", help="Evaluation helpers")
app.add_typer(cache_app, name="cache", help="Inspect and manage the on-disk cache")
app.add_typer(optimize_app, name="optimize", help="Program optimization (GEPA, etc.)")
app.add_typer(run_app, name="run", help="Replay/explain operations")
app.add_typer(
    program_refine_app,
    name="program-refine",
    help="Bounded program refinement proposals",
)
app.add_typer(
    program_promote_app,
    name="program-promote",
    help="Local program promotion-review evidence packets",
)
app.add_typer(
    program_architect_app,
    name="program-architect",
    help="Non-authoritative program architecture candidate planning",
)
app.add_typer(
    oracle_app, name="oracle", help="Behavioral oracle (semantic coordinates)"
)

layer12_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Layer12/direction-controller proposal/eval helpers against AK verifier surfaces",
)
app.add_typer(layer12_app, name="layer12")

program_gen_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Generate DSPy program candidates and target-fidelity preflight sidecars",
)
app.add_typer(program_gen_app, name="program-gen")


def _interactive_quality_chat_available() -> bool:
    return bool(sys.stdin.isatty())


# =============================================================================
# Inline Commands (single commands kept inline for simplicity)
# =============================================================================


@layer12_app.command("eval-proposals")
def layer12_eval_proposals(
    agent_kernel_repo: Path = typer.Option(
        Path("~/ai-society/softwareco/owned/agent-kernel"),
        "--agent-kernel-repo",
        help="Path to the agent-kernel repo that owns the deterministic Layer12 verifier",
    ),
    fixtures_dir: Optional[Path] = typer.Option(
        None,
        "--fixtures-dir",
        help="Agent-kernel-owned proposal fixture directory (defaults to docs/project/layer12/fixtures/proposals)",
    ),
    eval_fixture: Optional[Path] = typer.Option(
        None,
        "--eval-fixture",
        help="Agent-kernel-owned generated-program eval fixture for candidate_scores",
    ),
    candidate_proposals: Optional[List[Path]] = typer.Option(
        None,
        "--candidate-proposal",
        help="Agent-kernel-owned generated-program candidate proposal to score with AK eval_summary (repeatable)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON summary"),
) -> None:
    """Evaluate Layer12 proposals through AK's deterministic direction-controller.

    This command is read-only: DSPx orchestrates proposal/eval reporting while
    AK remains the legality authority and no apply is performed.
    """

    from dspx.services.layer12_controller import evaluate_layer12_proposals

    payload = evaluate_layer12_proposals(
        agent_kernel_repo=agent_kernel_repo.expanduser(),
        fixtures_dir=fixtures_dir.expanduser() if fixtures_dir is not None else None,
        eval_fixture=eval_fixture.expanduser() if eval_fixture is not None else None,
        candidate_proposals=[path.expanduser() for path in candidate_proposals or []],
    )
    if json_out:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    metrics = payload["metrics"]
    typer.echo("layer12 direction-controller proposal eval")
    typer.echo(f"  cases: {metrics['case_count']}")
    typer.echo(f"  verdicts: {metrics['verdict_counts']}")
    typer.echo(f"  false_unblock_rate: {metrics['false_unblock_rate']}")
    typer.echo(
        f"  candidate_scores: {payload['candidate_score_metrics']['score_count']}"
    )
    typer.echo(
        f"  best_candidate_score: {payload['candidate_score_metrics']['best_score']}"
    )
    typer.echo(
        f"  legality_authority: {payload['authority_boundary']['legality_authority']}"
    )
    typer.echo(f"  apply_performed: {payload['apply_performed']}")


@app.command("module-gen")
def module_gen(
    name: str = typer.Option(..., "--name", "-n", help="Module class name"),
    description: str = typer.Option(
        "", "--description", "-d", help="Description docstring"
    ),
    input: List[str] = typer.Option(
        [], "--input", "-i", help="Input fields (repeatable)"
    ),
    output: List[str] = typer.Option(
        [], "--output", "-o", help="Output fields (repeatable)"
    ),
    template_version: str = typer.Option(
        "simple-v1", help="Template version (use 'simple-*' for deterministic output)"
    ),
    use_signature: bool = typer.Option(
        False, help="Embed a simple Signature and wire Predict"
    ),
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    outfile: Optional[Path] = typer.Option(None, help="Write code to file"),
    no_cache: bool = typer.Option(False, help="Bypass on-disk cache for this run"),
    cache_info: bool = typer.Option(False, help="Print cache key and path info"),
    budget_ms: Optional[int] = typer.Option(
        None, help="Time budget in ms (logs to MLflow)"
    ),
    template_config: Optional[Path] = typer.Option(
        None,
        "--template-config",
        help="YAML config file for TemplateAdapter (requires dspy-template-adapter)",
    ),
) -> None:
    """Generate a DSPy module scaffold from a specification."""
    from dspx.dtos import ModuleSpec
    from dspx.services.module_service import run_generate as module_run_generate
    from dspx.cli.commands.module import (
        _write_module_output,
        _print_module_cache_info,
        validate_module_fields_or_exit,
    )

    if template_config is not None:
        if not template_config.exists():
            typer.echo(
                f"Error: Template config file not found: {template_config}",
                err=True,
            )
            raise typer.Exit(code=2)
        require_template_adapter("template-config")

    ensure_env(provider)
    if no_cache:
        os.environ["DSPX_CACHE_ENABLE"] = "0"
    if budget_ms is not None:
        os.environ["DSPX_BUDGET_MODULE_MS"] = str(int(budget_ms))

    validate_module_fields_or_exit(input, output, name)

    spec = ModuleSpec(
        name=name,
        description=description,
        inputs=input,
        outputs=output,
        options={"template_version": template_version},
    )
    art = module_run_generate(
        spec,
        use_signature=use_signature,
        promotion_target=outfile,
    )

    if outfile:
        _write_module_output(
            outfile=outfile,
            code=art.code,
            name=name,
            description=description,
            inputs=input,
            outputs=output,
            use_signature=use_signature,
            template_version=template_version,
            artifact_metadata=art.metadata,
        )
        typer.echo(str(outfile))
    else:
        sys.stdout.write(art.code)
        if cache_info:
            _print_module_cache_info(
                name, description, input, output, use_signature, template_version
            )


def _as_root_relative_file(root: Path, value: object) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    candidate = path if path.is_absolute() else root / path
    try:
        resolved = candidate.resolve()
        root_resolved = root.resolve()
        if not resolved.is_relative_to(root_resolved):
            return None
        if not resolved.is_file():
            return None
        return resolved.relative_to(root_resolved)
    except Exception:
        return None


def _collect_program_manifest_paths(value: object) -> list[object]:
    paths: list[object] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "entrypoint", "harness", "result"}:
                paths.append(item)
            paths.extend(_collect_program_manifest_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_collect_program_manifest_paths(item))
    return paths


def _declared_program_artifact_files(
    *,
    root: Path,
    artifact: Any,
    manifest: dict[str, Any],
) -> list[Path]:
    candidates: list[object] = ["manifest.json", "manifest.json.meta.json"]
    candidates.extend(_collect_program_manifest_paths(manifest))
    files = getattr(artifact, "files", {}) or {}
    if isinstance(files, dict):
        candidates.extend(files.keys())
        candidates.extend(files.values())

    out: list[Path] = []
    seen: set[str] = set()
    for value in candidates:
        rel = _as_root_relative_file(root, value)
        if rel is None:
            continue
        key = rel.as_posix()
        if key in seen:
            continue
        seen.add(key)
        out.append(rel)
    return out


def _log_declared_program_artifacts(
    mlflow: Any, *, root: Path, files: list[Path]
) -> None:
    with tempfile.TemporaryDirectory(prefix="dspx-program-mlflow-") as tmp:
        staging = Path(tmp)
        for rel in files:
            source = root / rel
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        mlflow.log_artifacts(str(staging))


def _log_program_artifact_to_mlflow(artifact: Any) -> None:
    """Best-effort MLflow logging for materialized program-gen assemblies."""
    try:
        from dspx.cache import sha256_text
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is None:
            return

        def _safe_set_tag(key: str, value: object) -> None:
            try:
                mlflow.set_tag(key, str(value)[:500])
            except Exception:
                pass

        def _safe_log_metric(key: str, value: float) -> None:
            try:
                mlflow.log_metric(key, float(value))
            except Exception:
                pass

        root = Path(str(getattr(artifact, "root_path", "") or ""))
        if not root.exists() or not root.is_dir():
            return

        manifest_path = root / "manifest.json"
        manifest: dict[str, Any] = {}
        if manifest_path.exists() and manifest_path.is_file():
            try:
                loaded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(loaded_manifest, dict):
                    manifest = loaded_manifest
            except Exception:
                manifest = {}
        receipt_path = Path(str(getattr(artifact, "receipt_path", "") or ""))
        receipt: dict[str, Any] = {}
        if receipt_path.exists() and receipt_path.is_file():
            try:
                loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    receipt = loaded
            except Exception:
                receipt = {}

        declared_files = _declared_program_artifact_files(
            root=root,
            artifact=artifact,
            manifest=manifest,
        )
        metadata = dict(getattr(artifact, "metadata", {}) or {})
        template_version = str(
            receipt.get("template_version") or "program-candidate-assembly-v1"
        )
        cache_key = str(
            receipt.get("cache_key") or metadata.get("request_id") or manifest_path
        )
        if receipt.get("output_hash"):
            output_hash = str(receipt["output_hash"])
        elif manifest_path.exists():
            output_hash = sha256_text(manifest_path.read_text(encoding="utf-8"))
        else:
            output_hash = ""

        started_run = ensure_run_with_standard_tags(
            "program",
            template_version=template_version,
            run_name="program-gen",
            run_kind="program-gen",
            output_basename=manifest_path.name,
            cache_key=cache_key,
            output_hash=output_hash,
            extra={
                "program.name": str(getattr(artifact, "name", "") or ""),
                "program.assembly_id": str(metadata.get("assembly_id") or ""),
                "program.episode_id": str(metadata.get("episode_id") or ""),
            },
        )

        try:
            if mlflow.active_run() is not None:
                try:
                    mlflow.log_param(
                        "program.generated_file_count",
                        str(len(declared_files)),
                    )
                except Exception:
                    pass
                try:
                    _log_declared_program_artifacts(
                        mlflow,
                        root=root,
                        files=declared_files,
                    )
                    _safe_set_tag("program.artifacts.upload_status", "logged")
                    _safe_log_metric("program.artifacts.upload_error", 0.0)
                except Exception as exc:
                    _safe_set_tag("program.artifacts.upload_status", "failed")
                    _safe_set_tag("program.artifacts.error_type", type(exc).__name__)
                    _safe_set_tag("program.artifacts.error", str(exc))
                    _safe_log_metric("program.artifacts.upload_error", 1.0)
        finally:
            if started_run:
                try:
                    mlflow.end_run()
                except Exception:
                    pass
    except Exception:
        return


def _echo_generation_payload(
    payload: dict[str, Any], *, json_out: bool, out: Path | None
) -> None:
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    elif out is not None:
        typer.echo(str(out.expanduser().resolve()))
    else:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _load_allowed_contract_verification(
    path: Path, *, intent_path: Path | None = None
) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"contract verification not found: {path}")
    payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    from dspx.services.program_service import _validate_contract_verification_payload

    _validate_contract_verification_payload(payload, intent_source=intent_path)
    return payload


def _load_allowed_generation_gate(
    path: Path, *, intent_path: Path | None = None
) -> dict[str, Any]:
    from dspx.services.program_generation_contract import (
        build_generation_gate_preflight,
        load_generation_fitness_suite,
        load_generation_gate_preflight,
        load_generation_target_contract,
        validate_generation_gate_preflight_payload,
    )

    if not path.exists():
        raise FileNotFoundError(f"generation gate preflight not found: {path}")
    payload = load_generation_gate_preflight(path)
    intent_sha256: str | None = None
    if intent_path is not None:
        import hashlib

        intent_sha256 = hashlib.sha256(
            intent_path.expanduser().resolve().read_bytes()
        ).hexdigest()
    if payload.get("generation_allowed") is not True:
        reasons = payload.get("fail_closed_reasons") or []
        raise ValueError(f"generation gate blocked candidate creation: {reasons}")
    validate_generation_gate_preflight_payload(payload, intent_sha256=intent_sha256)

    preflight_dir = path.expanduser().resolve().parent
    target_contract_path = preflight_dir / "generation_target_contract.json"
    fitness_suite_path = preflight_dir / "generation_fitness_suite.json"
    if not target_contract_path.exists() or not fitness_suite_path.exists():
        raise ValueError(
            "generation gate preflight requires sibling generation_target_contract.json "
            "and generation_fitness_suite.json for provenance verification"
        )
    expected_payload = build_generation_gate_preflight(
        target_contract=load_generation_target_contract(target_contract_path),
        fitness_suite=load_generation_fitness_suite(fitness_suite_path),
    )
    for key in (
        "schema_version",
        "status",
        "generation_allowed",
        "fail_closed_reasons",
        "target_contract_validation",
        "fitness_suite_validation",
        "non_authority",
        "effect",
    ):
        if payload.get(key) != expected_payload.get(key):
            raise ValueError(f"generation gate preflight {key}_mismatch")
    raw_identity = payload.get("identity")
    raw_expected_identity = expected_payload.get("identity")
    identity = raw_identity if isinstance(raw_identity, dict) else {}
    expected_identity = (
        raw_expected_identity if isinstance(raw_expected_identity, dict) else {}
    )
    for key in ("target_contract_sha256", "fitness_suite_sha256"):
        if identity.get(key) != expected_identity.get(key):
            raise ValueError(f"generation gate preflight identity.{key}_mismatch")
    return payload


@program_gen_app.command("quality-chat")
def quality_chat(
    prompt: str = typer.Option(
        ...,
        "--prompt",
        help="Provider-bound natural-language intent; secret-shaped content is rejected and accepted text is persisted in the candidate intent",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Fresh path for the quality-proposal conversation artifact",
    ),
    feedback: List[str] = typer.Option(
        [],
        "--feedback",
        help="Feedback for the quality proposal; may repeat",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Do not prompt; emit a pending proposal unless --accept is explicit",
    ),
    accept: bool = typer.Option(
        False,
        "--accept",
        help="Explicitly accept the generated proposal in non-interactive mode",
    ),
    max_turns: int = typer.Option(
        3,
        "--max-turns",
        min=1,
        max=8,
        help="Maximum proposal/revision turns for interactive chat",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Print the complete proposal/decision artifact as JSON",
    ),
) -> None:
    """Discuss and freeze quality criteria before generating a program."""
    from dspx.config_loader import load_config_env
    from dspx.services.program_quality_conversation import (
        ProgramQualityConversationError,
        propose_program_quality_criteria,
        set_quality_proposal_decision,
        write_quality_proposal,
    )

    if accept and not non_interactive:
        typer.echo("Error: --accept requires --non-interactive", err=True)
        raise typer.Exit(code=2)
    if json_out and not non_interactive:
        typer.echo(
            "Error: --json requires --non-interactive so stdout remains one machine-readable document",
            err=True,
        )
        raise typer.Exit(code=2)
    if not non_interactive and not _interactive_quality_chat_available():
        typer.echo(
            "Error: interactive quality chat requires a TTY; use --non-interactive",
            err=True,
        )
        raise typer.Exit(code=2)
    turns = list(feedback)
    history: list[dict[str, Any]] = []
    try:
        load_config_env()
        payload = propose_program_quality_criteria(
            prompt, feedback=turns, history=history
        )
        if non_interactive:
            if accept:
                payload = set_quality_proposal_decision(payload, decision="accept")
        else:
            for turn_index in range(max_turns):
                proposal = payload.get("proposal") or {}
                typer.echo(json.dumps(proposal, ensure_ascii=False, indent=2), err=True)
                choice = (
                    typer.prompt(
                        "Decision [accept/revise/reject]",
                        default="accept",
                        err=True,
                    )
                    .strip()
                    .lower()
                )
                if choice in {"accept", "a"}:
                    payload = set_quality_proposal_decision(payload, decision="accept")
                    break
                if choice in {"reject", "rj"}:
                    payload = set_quality_proposal_decision(payload, decision="reject")
                    break
                if choice not in {"revise", "r"}:
                    raise ProgramQualityConversationError(
                        "interactive decision must be accept, revise, or reject"
                    )
                if turn_index + 1 >= max_turns:
                    raise ProgramQualityConversationError(
                        "quality conversation exhausted --max-turns before a decision"
                    )
                revision = typer.prompt("Revision feedback", err=True).strip()
                if not revision:
                    raise ProgramQualityConversationError(
                        "revision feedback must not be blank"
                    )
                turns.append(revision)
                history.append(payload)
                payload = propose_program_quality_criteria(
                    prompt, feedback=turns, history=history
                )
        written = write_quality_proposal(payload, out)
    except ProgramQualityConversationError as exc:
        typer.echo(f"Error: {sanitize_cli_error(exc)}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: quality conversation failed: {sanitize_cli_error(exc)}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(written))


@program_gen_app.command("normalize-intent")
def normalize_intent(
    intent: Optional[Path] = typer.Option(
        None,
        "--intent",
        "-i",
        help="Path to an existing JSON/YAML program-intent-v2 file to normalize",
    ),
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt",
        help="Natural-language program request to normalize into a draft program intent",
    ),
    request: Optional[Path] = typer.Option(
        None,
        "--request",
        help="Path to a text file containing a natural-language program request",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-intent-normalization-v1 sidecar should be written",
    ),
    normalized_intent_out: Optional[Path] = typer.Option(
        None,
        "--normalized-intent-out",
        help="Optional path where the normalized program-intent-v2 JSON should be written",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help="Optional program name when normalizing from --prompt/--request",
    ),
    input_field: List[str] = typer.Option(
        [],
        "--input",
        help="Explicit input field for prompt/request normalization; may repeat",
    ),
    output_field: List[str] = typer.Option(
        [],
        "--output",
        help="Explicit output field for prompt/request normalization; may repeat",
    ),
    metric: Optional[str] = typer.Option(
        None,
        "--metric",
        help="Optional metric for prompt/request normalization",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print normalization JSON"),
) -> None:
    """Normalize a program request/intent before materialization."""
    from dspx.services.program_intent_normalization import (
        ProgramIntentNormalizationError,
        normalize_program_intent_from_path,
        normalize_program_intent_from_prompt,
        normalize_program_intent_from_request_path,
        write_normalized_intent,
        write_program_intent_normalization,
    )

    supplied = [intent is not None, prompt is not None, request is not None]
    if sum(1 for item in supplied if item) != 1:
        typer.echo(
            "Error: supply exactly one of --intent, --prompt, or --request", err=True
        )
        raise typer.Exit(code=2)
    try:
        if intent is not None:
            payload = normalize_program_intent_from_path(intent)
        elif request is not None:
            payload = normalize_program_intent_from_request_path(
                request,
                name=name,
                inputs=input_field or None,
                outputs=output_field or None,
                metric=metric,
            )
        else:
            assert prompt is not None
            payload = normalize_program_intent_from_prompt(
                prompt,
                name=name,
                inputs=input_field or None,
                outputs=output_field or None,
                metric=metric,
            )
        if normalized_intent_out is not None:
            intent_artifact = write_normalized_intent(payload, normalized_intent_out)
            payload = {
                **payload,
                "normalized_intent_artifact": intent_artifact,
                "effect": {
                    **dict(payload.get("effect") or {}),
                    "normalized_intent_written": True,
                },
            }
        written = write_program_intent_normalization(payload, out)
    except ProgramIntentNormalizationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program intent normalization failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(written, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@program_gen_app.callback(invoke_without_command=True)
def program_gen(
    ctx: typer.Context,
    intent: Optional[Path] = typer.Option(
        None,
        "--intent",
        "-i",
        help="Path to a JSON/YAML one-intent program specification",
    ),
    outdir: Optional[Path] = typer.Option(
        None,
        "--outdir",
        "-o",
        help="Directory where the program candidate assembly is materialized",
    ),
    print_manifest: bool = typer.Option(
        False,
        "--print-manifest",
        help="Print the generated manifest JSON instead of only the output directory",
    ),
    generation_gate_preflight: Optional[Path] = typer.Option(
        None,
        "--generation-gate-preflight",
        help="Require a successful gen-generation-gate-preflight-v1 sidecar before candidate creation",
    ),
    contract_verification: Optional[Path] = typer.Option(
        None,
        "--contract-verification",
        help="Require a verified program-architecture-contract-verification-v1 sidecar matching this intent",
    ),
) -> None:
    """Generate a program-shaped DSPy candidate assembly from one intent."""
    if ctx.invoked_subcommand is not None:
        return
    from dspx.services.program_service import run_generate_from_intent_path

    if intent is None:
        typer.echo(
            "Error: --intent is required when program-gen has no subcommand", err=True
        )
        raise typer.Exit(code=2)
    if not intent.exists():
        typer.echo(f"Error: intent file not found: {intent}", err=True)
        raise typer.Exit(code=2)

    if generation_gate_preflight is not None:
        try:
            _load_allowed_generation_gate(generation_gate_preflight, intent_path=intent)
        except Exception as exc:
            typer.echo(f"Error: generation gate preflight failed: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    if contract_verification is not None:
        try:
            _load_allowed_contract_verification(
                contract_verification, intent_path=intent
            )
        except Exception as exc:
            typer.echo(f"Error: contract verification failed: {exc}", err=True)
            raise typer.Exit(code=2) from exc

    ensure_env(None)

    try:
        artifact = run_generate_from_intent_path(
            intent, outdir=outdir, contract_verification_path=contract_verification
        )
    except Exception as exc:
        typer.echo(f"Error: program intent generation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    _log_program_artifact_to_mlflow(artifact)

    if print_manifest:
        typer.echo(json.dumps(artifact.manifest, indent=2, sort_keys=True))
    else:
        typer.echo(artifact.root_path)


@program_gen_app.command("target-contract")
def program_gen_target_contract(
    intent: Path = typer.Option(
        ...,
        "--intent",
        "-i",
        help="Path to a JSON/YAML one-intent program specification",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Write generation_target_contract.json here",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print target contract JSON"),
) -> None:
    """Build and validate a gen-target-contract-v1 sidecar from structured intent."""
    from dspx.services.program_generation_contract import (
        build_generation_target_contract_from_intent,
        validate_generation_target_contract,
        write_generation_json,
    )

    if not intent.exists():
        typer.echo(f"Error: intent file not found: {intent}", err=True)
        raise typer.Exit(code=2)
    try:
        payload = build_generation_target_contract_from_intent(intent)
        validation = validate_generation_target_contract(payload)
        write_generation_json(payload, out)
    except Exception as exc:
        typer.echo(f"Error: target contract generation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _echo_generation_payload(payload, json_out=json_out, out=out)
    if validation.get("status") != "valid":
        raise typer.Exit(code=2)


def _run_program_gen_requirements_intake(
    *, profile: str, requirements: Path, outdir: Path, intent_out: Path | None = None
) -> dict[str, Any]:
    from dspx.services.program_generation_contract import (
        build_generation_requirements_intake_artifacts,
        load_generation_target_contract,
        write_generation_json,
        write_generation_yaml,
    )

    if not requirements.exists():
        raise FileNotFoundError(f"requirements file not found: {requirements}")
    packet = load_generation_target_contract(requirements)
    artifacts = build_generation_requirements_intake_artifacts(
        profile=profile, requirements=packet, include_intent=intent_out is not None
    )
    outdir_resolved = outdir.expanduser().resolve()
    outdir_resolved.mkdir(parents=True, exist_ok=True)
    target_contract_path = outdir_resolved / "generation_target_contract.json"
    fitness_suite_path = outdir_resolved / "generation_fitness_suite.json"
    preflight_path = outdir_resolved / "generation_gate_preflight.json"
    write_generation_json(artifacts["target_contract"], target_contract_path)
    write_generation_json(artifacts["fitness_suite"], fitness_suite_path)
    paths = {
        "target_contract": str(target_contract_path),
        "fitness_suite": str(fitness_suite_path),
        "generation_gate_preflight": str(preflight_path),
    }
    if intent_out is not None and "program_intent" in artifacts:
        import hashlib

        intent_path = intent_out.expanduser().resolve()
        write_generation_yaml(artifacts["program_intent"], intent_path)
        identity = artifacts["generation_gate_preflight"].setdefault("identity", {})
        if isinstance(identity, dict):
            identity["requirements_packet_sha256"] = identity.get("intent_sha256")
            identity["intent_sha256"] = hashlib.sha256(
                intent_path.read_bytes()
            ).hexdigest()
        paths["program_intent"] = str(intent_path)
    write_generation_json(artifacts["generation_gate_preflight"], preflight_path)
    return {
        "schema_version": artifacts["schema_version"],
        "profile": profile,
        "requirements_validation": artifacts["requirements_validation"],
        "generation_gate_preflight": artifacts["generation_gate_preflight"],
        "paths": paths,
        "verifier_guarantee": artifacts["verifier_guarantee"],
        "verifier_non_guarantee": artifacts["verifier_non_guarantee"],
    }


@program_gen_app.command("prepare")
def program_gen_prepare(
    profile: str = typer.Option(
        ...,
        "--profile",
        help="Generation preparation profile, for example designmd-visual-dossier",
    ),
    requirements: Path = typer.Option(
        ...,
        "--requirements",
        help="Path to an external repo requirements packet JSON/YAML file",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory for prepared generation gate artifacts",
    ),
    intent_out: Optional[Path] = typer.Option(
        None,
        "--intent-out",
        help="Optionally write a minimal program-intent-v2 YAML for follow-on program-gen",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print preparation summary JSON"
    ),
) -> None:
    """Prepare DSPx-native generation gate artifacts from external requirements."""
    try:
        summary = _run_program_gen_requirements_intake(
            profile=profile,
            requirements=requirements,
            outdir=outdir,
            intent_out=intent_out,
        )
    except Exception as exc:
        typer.echo(f"Error: generation preparation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _echo_generation_payload(summary, json_out=json_out, out=outdir)
    if summary["generation_gate_preflight"].get("generation_allowed") is not True:
        raise typer.Exit(code=2)


@program_gen_app.command("requirements-intake")
def program_gen_requirements_intake(
    profile: str = typer.Option(
        ...,
        "--profile",
        help="Requirements adapter profile, for example designmd-visual-dossier",
    ),
    requirements: Path = typer.Option(
        ...,
        "--requirements",
        help="Path to an external repo requirements packet JSON/YAML file",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        help="Directory for generation_target_contract.json, generation_fitness_suite.json, and generation_gate_preflight.json",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print intake summary JSON"),
) -> None:
    """Normalize external requirements into DSPx-native generation gate artifacts."""
    try:
        summary = _run_program_gen_requirements_intake(
            profile=profile, requirements=requirements, outdir=outdir
        )
    except Exception as exc:
        typer.echo(f"Error: requirements intake failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _echo_generation_payload(summary, json_out=json_out, out=outdir)
    if summary["generation_gate_preflight"].get("generation_allowed") is not True:
        raise typer.Exit(code=2)


@program_gen_app.command("fitness-suite")
def program_gen_fitness_suite(
    target_contract: Path = typer.Option(
        ...,
        "--target-contract",
        help="Path to generation_target_contract.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Write generation_fitness_suite.json here",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print fitness suite JSON"),
) -> None:
    """Build and validate a gen-fitness-suite-v1 sidecar."""
    from dspx.services.program_generation_contract import (
        build_generation_fitness_suite_from_target_contract,
        load_generation_target_contract,
        validate_generation_fitness_suite,
        write_generation_json,
    )

    if not target_contract.exists():
        typer.echo(
            f"Error: target contract file not found: {target_contract}", err=True
        )
        raise typer.Exit(code=2)
    try:
        contract_payload = load_generation_target_contract(target_contract)
        payload = build_generation_fitness_suite_from_target_contract(contract_payload)
        validation = validate_generation_fitness_suite(
            payload, target_contract=contract_payload
        )
        write_generation_json(payload, out)
    except Exception as exc:
        typer.echo(f"Error: fitness suite generation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _echo_generation_payload(payload, json_out=json_out, out=out)
    if validation.get("status") != "valid":
        raise typer.Exit(code=2)


@program_gen_app.command("verify-generation-gate")
def program_gen_verify_generation_gate(
    intent: Path = typer.Option(
        ...,
        "--intent",
        "-i",
        help="Path to the intent bound by the target contract",
    ),
    target_contract: Path = typer.Option(
        ...,
        "--target-contract",
        help="Path to generation_target_contract.json",
    ),
    fitness_suite: Path = typer.Option(
        ...,
        "--fitness-suite",
        help="Path to generation_fitness_suite.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Write generation_gate_preflight.json here",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print preflight JSON"),
) -> None:
    """Verify deterministic generation preflight before program candidate creation."""
    from dspx.services.program_generation_contract import (
        build_generation_gate_preflight,
        load_generation_fitness_suite,
        load_generation_target_contract,
        write_generation_gate_preflight,
    )

    missing = [
        str(path)
        for path in (intent, target_contract, fitness_suite)
        if not path.exists()
    ]
    if missing:
        typer.echo(f"Error: required file(s) not found: {', '.join(missing)}", err=True)
        raise typer.Exit(code=2)
    try:
        contract_payload = load_generation_target_contract(target_contract)
        suite_payload = load_generation_fitness_suite(fitness_suite)
        preflight = build_generation_gate_preflight(
            target_contract=contract_payload, fitness_suite=suite_payload
        )
        contract_intent_sha = (
            (contract_payload.get("identity") or {}).get("intent_sha256")
            if isinstance(contract_payload.get("identity"), dict)
            else None
        )
        if contract_intent_sha:
            import hashlib

            actual_intent_sha = hashlib.sha256(
                intent.expanduser().resolve().read_bytes()
            ).hexdigest()
            if actual_intent_sha != contract_intent_sha:
                preflight["status"] = "generation_blocked"
                preflight["generation_allowed"] = False
                reasons = set(preflight.get("fail_closed_reasons") or [])
                reasons.add("intent_sha256_mismatch")
                preflight["fail_closed_reasons"] = sorted(reasons)
        write_generation_gate_preflight(preflight, out)
    except Exception as exc:
        typer.echo(f"Error: generation gate verification failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _echo_generation_payload(preflight, json_out=json_out, out=out)
    if preflight.get("generation_allowed") is not True:
        raise typer.Exit(code=2)


@program_gen_app.command("traceability")
def program_gen_traceability(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to generated program manifest.json",
    ),
    target_contract: Path = typer.Option(
        ...,
        "--target-contract",
        help="Path to generation_target_contract.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Write generation_traceability.json here",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print traceability JSON"),
) -> None:
    """Write gen-traceability-v1 for a generated candidate."""
    from dspx.services.program_generation_contract import (
        build_generation_traceability,
        load_candidate_manifest,
        load_generation_target_contract,
        validate_generation_traceability,
        write_generation_json,
    )

    missing = [str(path) for path in (manifest, target_contract) if not path.exists()]
    if missing:
        typer.echo(f"Error: required file(s) not found: {', '.join(missing)}", err=True)
        raise typer.Exit(code=2)
    try:
        manifest_payload = load_candidate_manifest(manifest)
        contract_payload = load_generation_target_contract(target_contract)
        traceability = build_generation_traceability(
            target_contract=contract_payload, candidate_manifest=manifest_payload
        )
        validation = validate_generation_traceability(traceability)
        write_generation_json(traceability, out)
    except Exception as exc:
        typer.echo(f"Error: traceability generation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _echo_generation_payload(traceability, json_out=json_out, out=out)
    if validation.get("status") != "valid":
        raise typer.Exit(code=2)


@program_gen_app.command("fitness-results")
def program_gen_fitness_results(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to generated program manifest.json",
    ),
    target_contract: Path = typer.Option(
        ...,
        "--target-contract",
        help="Path to generation_target_contract.json",
    ),
    fitness_suite: Path = typer.Option(
        ...,
        "--fitness-suite",
        help="Path to generation_fitness_suite.json",
    ),
    traceability: Path = typer.Option(
        ...,
        "--traceability",
        help="Path to generation_traceability.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Write generation_fitness_results.json here",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print fitness results JSON"),
) -> None:
    """Write gen-fitness-results-v1 after candidate generation."""
    from dspx.services.program_generation_contract import (
        build_generation_fitness_results,
        load_candidate_manifest,
        load_generation_fitness_suite,
        load_generation_target_contract,
        load_generation_traceability,
        validate_generation_fitness_results,
        write_generation_json,
    )

    missing = [
        str(path)
        for path in (manifest, target_contract, fitness_suite, traceability)
        if not path.exists()
    ]
    if missing:
        typer.echo(f"Error: required file(s) not found: {', '.join(missing)}", err=True)
        raise typer.Exit(code=2)
    try:
        manifest_payload = load_candidate_manifest(manifest)
        contract_payload = load_generation_target_contract(target_contract)
        suite_payload = load_generation_fitness_suite(fitness_suite)
        trace_payload = load_generation_traceability(traceability)
        fitness_results = build_generation_fitness_results(
            candidate_manifest=manifest_payload,
            target_contract=contract_payload,
            fitness_suite=suite_payload,
            traceability=trace_payload,
        )
        validation = validate_generation_fitness_results(fitness_results)
        write_generation_json(fitness_results, out)
    except Exception as exc:
        typer.echo(f"Error: fitness results generation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    _echo_generation_payload(fitness_results, json_out=json_out, out=out)
    if validation.get("status") != "valid":
        raise typer.Exit(code=2)


@app.command("foundry")
def program_foundry(
    intent: Path = typer.Option(
        ...,
        "--intent",
        "-i",
        help="Path to a quality-accepted program-intent-v2 JSON/YAML artifact",
    ),
    quality_proposal: Path = typer.Option(
        ...,
        "--quality-proposal",
        help="Path to the accepted quality-proposal envelope that emitted --intent",
    ),
    inputs: Path = typer.Option(
        ...,
        "--inputs",
        help="Runtime inputs JSON object or {inputs: {...}}",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        "-o",
        help="Foundry root containing candidate, runtime, semantic, and workflow artifacts",
    ),
    skip_oracle_index: bool = typer.Option(
        False,
        "--skip-oracle-index",
        help="Skip the candidate-local runtime Oracle coordinate index/report",
    ),
    gepa_recommendation_index: Optional[int] = typer.Option(
        None,
        "--propose-gepa-experiment",
        min=0,
        help="Write a non-executing GEPA proposal from this Oracle recommended_experiments index",
    ),
    gepa_max_metric_calls: int = typer.Option(
        2,
        "--gepa-max-metric-calls",
        min=1,
        max=20,
        help="Bounded future GEPA metric-call budget recorded in the proposal",
    ),
    gepa_metric: Optional[str] = typer.Option(
        None,
        "--gepa-metric",
        help="Explicit bounded optimizer metric recorded in the proposal",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print foundry workflow JSON"),
) -> None:
    """Run or safely resume accepted intent through runtime Oracle semantics."""
    from dspx.services.program_foundry import (
        foundry_failure_message,
        run_program_foundry,
    )

    if not intent.exists():
        typer.echo(f"Error: intent file not found: {intent}", err=True)
        raise typer.Exit(code=2)
    if not quality_proposal.exists():
        typer.echo(
            f"Error: quality proposal file not found: {quality_proposal}", err=True
        )
        raise typer.Exit(code=2)
    if not inputs.exists():
        typer.echo(f"Error: inputs file not found: {inputs}", err=True)
        raise typer.Exit(code=2)
    ensure_env(None)
    try:
        payload = run_program_foundry(
            intent_path=intent,
            quality_proposal_path=quality_proposal,
            inputs_path=inputs,
            outdir=outdir,
            skip_oracle_index=skip_oracle_index,
            gepa_recommendation_index=gepa_recommendation_index,
            gepa_max_metric_calls=gepa_max_metric_calls,
            gepa_metric=gepa_metric,
        )
    except Exception as exc:
        typer.echo(f"Error: foundry failed: {foundry_failure_message(exc)}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(payload.get("workflow_path") or outdir / "foundry.json"))
        typer.echo(f"foundry_status: {payload.get('status')}")
        for name in (
            "candidate",
            "runtime",
            "oracle_semantic",
            "gepa_experiment_proposal",
        ):
            stage = (payload.get("stages") or {}).get(name) or {}
            typer.echo(f"{name}: {stage.get('status')} ({stage.get('disposition')})")
    if payload.get("status") != "ok":
        raise typer.Exit(code=1)


@app.command("program-loop")
def program_loop(
    intent: Path = typer.Option(
        ...,
        "--intent",
        "-i",
        help="Path to a JSON/YAML one-intent program specification",
    ),
    outdir: Optional[Path] = typer.Option(
        None,
        "--outdir",
        "-o",
        help="Directory where the program candidate assembly is materialized",
    ),
    index_path: Optional[Path] = typer.Option(
        None,
        "--index-path",
        help="Candidate-local Oracle CoordinateIndex path; defaults below --outdir",
    ),
    oracle_report_out: Optional[Path] = typer.Option(
        None,
        "--oracle-report-out",
        help="Path for the non-authoritative Oracle report sidecar",
    ),
    state_out: Optional[Path] = typer.Option(
        None,
        "--state-out",
        help="Path for the local candidate truth-state summary sidecar",
    ),
    workflow_out: Optional[Path] = typer.Option(
        None,
        "--workflow-out",
        help="Path for the local program-loop summary sidecar",
    ),
    skip_oracle_index: bool = typer.Option(
        False,
        "--skip-oracle-index",
        help="Skip local Oracle indexing/reporting and only write candidate state",
    ),
    publish_to_shared: Optional[str] = typer.Option(
        None,
        "--publish-to-shared",
        help="Explicitly publish program Oracle evidence to shared Oracle with this label",
    ),
    publisher_id: Optional[str] = typer.Option(
        None,
        "--publisher-id",
        help="Required with --publish-to-shared: declared publisher/session identity",
    ),
    publisher_role: Optional[str] = typer.Option(
        None,
        "--publisher-role",
        help="Required with --publish-to-shared: publisher role",
    ),
    publisher_assertion: Optional[str] = typer.Option(
        None,
        "--publisher-assertion",
        help="Required with --publish-to-shared: custody assertion",
    ),
    redaction_status: Optional[str] = typer.Option(
        None,
        "--redaction-status",
        help="Required with --publish-to-shared: checked, not_required, or redacted",
    ),
    retention_class: Optional[str] = typer.Option(
        None,
        "--retention-class",
        help="Required with --publish-to-shared: retention class",
    ),
    authority_ref: Optional[str] = typer.Option(
        None,
        "--authority-ref",
        help="Required for authority-mirror publication labels",
    ),
    publisher_secret_ref: list[str] = typer.Option(
        [],
        "--publisher-secret-ref",
        help="1Password op:// ref relevant to publisher custody; value is never resolved or persisted",
    ),
    publication_preflight_out: Optional[Path] = typer.Option(
        None,
        "--publication-preflight-out",
        help="Path for the local shared-publication preflight sidecar",
    ),
    publication_receipt_out: Optional[Path] = typer.Option(
        None,
        "--publication-receipt-out",
        help="Path for the local shared-publication receipt sidecar",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print workflow JSON"),
) -> None:
    """Run the coherent local one-intent program loop without authority effects."""
    from dspx.services.program_workflow import run_program_loop_from_intent_path

    if not intent.exists():
        typer.echo(f"Error: intent file not found: {intent}", err=True)
        raise typer.Exit(code=2)

    ensure_env(None)

    try:
        payload = run_program_loop_from_intent_path(
            intent,
            outdir=outdir,
            index_path=index_path,
            oracle_report_out=oracle_report_out,
            state_out=state_out,
            workflow_out=workflow_out,
            skip_oracle_index=skip_oracle_index,
            publish_to_shared=publish_to_shared,
            publisher_id=publisher_id,
            publisher_role=publisher_role,
            publisher_assertion=publisher_assertion,
            redaction_status=redaction_status,
            retention_class=retention_class,
            authority_ref=authority_ref,
            publisher_secret_refs=publisher_secret_ref,
            publication_preflight_out=publication_preflight_out,
            publication_receipt_out=publication_receipt_out,
        )
    except Exception as exc:
        typer.echo(f"Error: program loop failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        steps = payload.get("steps") or {}
        generation = steps.get("program_gen") or {}
        behavior = steps.get("behavior_evaluation") or {}
        state = steps.get("candidate_state") or {}
        typer.echo(str(payload.get("workflow_path") or "program_loop.json"))
        typer.echo(f"workflow_status: {payload.get('status')}")
        typer.echo(
            f"materialization_status: {generation.get('materialization_status')}"
        )
        typer.echo(f"behavior_status: {behavior.get('status')}")
        typer.echo(f"candidate_state: {state.get('status')}")
        required_next_steps = state.get("required_next_steps") or []
        if required_next_steps:
            typer.echo("next:")
            for item in required_next_steps:
                typer.echo(f"- {item}")
    if payload.get("status") != "ok":
        raise typer.Exit(code=1)


@app.command("program-run")
def program_run(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to an existing generated program manifest.json",
    ),
    inputs: Path = typer.Option(
        ...,
        "--inputs",
        help="Path to a JSON file containing an object, or {inputs: {...}}, for the generated program's declared inputs",
    ),
    outdir: Path = typer.Option(
        ...,
        "--outdir",
        "-o",
        help="Directory where the runtime episode sidecars are written",
    ),
    contract_mode: str = typer.Option(
        "none",
        "--contract-mode",
        help="Runtime contract gates: none or pdf_transition_review",
    ),
    skip_oracle_index: bool = typer.Option(
        False,
        "--skip-oracle-index",
        help="Skip local runtime-episode Oracle indexing/reporting",
    ),
    publication_preflight_out: Optional[Path] = typer.Option(
        None,
        "--publication-preflight-out",
        help="Optional shared-publication preflight sidecar path; no shared write is performed",
    ),
    publication_target: Optional[str] = typer.Option(
        None,
        "--publication-target",
        help="Required with --publication-preflight-out: shared Oracle target",
    ),
    publication_label: Optional[str] = typer.Option(
        None,
        "--publication-label",
        help="Required with --publication-preflight-out: publication label such as retained",
    ),
    publisher_id: Optional[str] = typer.Option(
        None,
        "--publisher-id",
        help="Required with --publication-preflight-out: declared publisher/session identity",
    ),
    publisher_role: Optional[str] = typer.Option(
        None,
        "--publisher-role",
        help="Required with --publication-preflight-out: publisher role",
    ),
    publisher_assertion: Optional[str] = typer.Option(
        None,
        "--publisher-assertion",
        help="Required with --publication-preflight-out: custody assertion",
    ),
    redaction_status: Optional[str] = typer.Option(
        None,
        "--redaction-status",
        help="Required with --publication-preflight-out: checked, not_required, or redacted",
    ),
    retention_class: Optional[str] = typer.Option(
        None,
        "--retention-class",
        help="Required with --publication-preflight-out: retention class",
    ),
    capture_replay_fixture: bool = typer.Option(
        False,
        "--capture-replay-fixture",
        help="Explicitly persist a mode-0600 local stub/input replay fixture; may contain sensitive runtime data",
    ),
    oracle_semantic: bool = typer.Option(
        False,
        "--oracle-semantic",
        help="Run configured receipt-bound Oracle semantic analysis after the runtime receipt validates",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print runtime workflow JSON"),
) -> None:
    """Run an existing generated program on explicit runtime inputs."""
    from dspx.services.program_runtime_episode import run_program_runtime_episode

    if not manifest.exists():
        typer.echo(f"Error: manifest file not found: {manifest}", err=True)
        raise typer.Exit(code=2)
    if not inputs.exists():
        typer.echo(f"Error: inputs file not found: {inputs}", err=True)
        raise typer.Exit(code=2)

    ensure_env(None)

    try:
        payload = run_program_runtime_episode(
            manifest_path=manifest,
            inputs_path=inputs,
            outdir=outdir,
            contract_mode=contract_mode,
            skip_oracle_index=skip_oracle_index,
            publication_preflight_out=publication_preflight_out,
            publication_target=publication_target,
            publication_label=publication_label,
            publisher_id=publisher_id,
            publisher_role=publisher_role,
            publisher_assertion=publisher_assertion,
            redaction_status=redaction_status,
            retention_class=retention_class,
            capture_replay_fixture=capture_replay_fixture,
            run_oracle_semantic=oracle_semantic,
        )
    except Exception as exc:
        typer.echo(f"Error: program runtime episode failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(payload.get("runtime_root") or outdir))
        runtime = (payload.get("steps") or {}).get("runtime_execution") or {}
        typer.echo(f"runtime_execution: {runtime.get('status')}")
        report = (payload.get("steps") or {}).get("oracle_report") or {}
        typer.echo(f"oracle_report: {report.get('status')}")
        semantic = (payload.get("steps") or {}).get("oracle_semantic") or {}
        typer.echo(f"oracle_semantic: {semantic.get('status')}")


@app.command("codegen")
def codegen(
    spec: str = typer.Argument(..., help="Codegen task description"),
    language: Optional[str] = typer.Option(
        None, "--language", "-l", help="Target language"
    ),
    template_version: str = typer.Option(
        "simple-v1", help="Template version (use 'simple-*' for deterministic output)"
    ),
    provider: Optional[str] = typer.Option(None, help="Provider (registry name)"),
    outfile: Optional[Path] = typer.Option(None, help="Write code to file"),
    no_cache: bool = typer.Option(False, help="Bypass on-disk cache for this run"),
    cache_info: bool = typer.Option(False, help="Print cache key and path info"),
    budget_ms: Optional[int] = typer.Option(
        None, help="Time budget in ms (logs to MLflow; may clamp provider timeout)"
    ),
    template_config: Optional[Path] = typer.Option(
        None,
        "--template-config",
        help="YAML config file for TemplateAdapter (requires dspy-template-adapter)",
    ),
) -> None:
    """Generate code from a specification."""
    from dspx.dtos import CodegenRequest
    from dspx.services.codegen_service import run_dto as codegen_run_dto
    from dspx.cli.commands.codegen import (
        _write_codegen_output,
        _print_codegen_cache_info,
    )

    if template_config is not None:
        if not template_config.exists():
            typer.echo(
                f"Error: Template config file not found: {template_config}",
                err=True,
            )
            raise typer.Exit(code=2)
        require_template_adapter("template-config")

    ensure_env(provider)
    if no_cache:
        os.environ["DSPX_CACHE_ENABLE"] = "0"
    if budget_ms is not None:
        os.environ["DSPX_BUDGET_CODEGEN_MS"] = str(int(budget_ms))

    req = CodegenRequest(
        spec=spec, language=language, template_version=template_version
    )
    res = codegen_run_dto(req)

    if outfile:
        _write_codegen_output(
            outfile=outfile,
            code=res.code,
            spec=spec,
            language=language,
            template_version=template_version,
        )
        typer.echo(str(outfile))
    else:
        sys.stdout.write(res.code)
        if cache_info:
            _print_codegen_cache_info(spec, language, template_version)


# =============================================================================
# Policy Callback (OpenRouter key injection, policy env setup)
# =============================================================================


@app.callback()
def _policy_callback(
    openrouter_api_key_file: Optional[Path] = typer.Option(
        None,
        "--openrouter-api-key-file",
        help="Read OPENROUTER_API_KEY from a file (recommended vs passing via CLI).",
    ),
    openrouter_api_key_op: Optional[str] = typer.Option(
        None,
        "--openrouter-api-key-op",
        help="Read OPENROUTER_API_KEY via 1Password CLI `op read <ref>` (e.g., op://Vault/Item/field).",
    ),
    openrouter_api_key_stdin: bool = typer.Option(
        False,
        "--openrouter-api-key-stdin",
        help="Read OPENROUTER_API_KEY from stdin (e.g., CI).",
    ),
    openrouter_api_key_prompt: bool = typer.Option(
        False,
        "--openrouter-api-key-prompt",
        help="Prompt for OPENROUTER_API_KEY (hidden input).",
    ),
    bypass_permissions: bool = typer.Option(
        False, "--bypass-permissions", help="Bypass policy checks (unsafe)"
    ),
    allowed_tools: Optional[str] = typer.Option(
        None, "--allowed-tools", help="Comma list of allowed tool names"
    ),
    disallowed_tools: Optional[str] = typer.Option(
        None, "--disallowed-tools", help="Comma list of denied tool names"
    ),
    allowed_providers: Optional[str] = typer.Option(
        None, "--allowed-providers", help="Comma list of allowed provider names"
    ),
    disallowed_providers: Optional[str] = typer.Option(
        None, "--disallowed-providers", help="Comma list of denied provider names"
    ),
    max_timeout: Optional[float] = typer.Option(
        None, "--max-timeout", help="Max timeout (s) to allow for tool calls"
    ),
    allow_network_mutate: bool = typer.Option(
        False,
        "--allow-network-mutate",
        help="Allow HTTP POST/PUT/PATCH/DELETE in tools",
    ),
    allowed_http_methods: Optional[str] = typer.Option(
        None, "--allowed-http-methods", help="Comma list of allowed HTTP methods"
    ),
    disallowed_http_methods: Optional[str] = typer.Option(
        None, "--disallowed-http-methods", help="Comma list of denied HTTP methods"
    ),
) -> None:
    """Global callback for policy and API key setup."""
    # OpenRouter API key injection (avoid leaking secrets via CLI args).
    if os.getenv("OPENROUTER_API_KEY") is None:
        if openrouter_api_key_file is not None:
            try:
                os.environ["OPENROUTER_API_KEY"] = openrouter_api_key_file.read_text(
                    encoding="utf-8"
                ).strip()
            except (OSError, UnicodeError) as exc:
                typer.echo(
                    "Error: failed to read OpenRouter API key file: "
                    f"{sanitize_cli_error(exc)}",
                    err=True,
                )
                raise typer.Exit(code=2) from exc
        elif openrouter_api_key_op:
            if shutil.which("op") is None:
                typer.echo("Error: 1Password CLI 'op' not found", err=True)
                raise typer.Exit(code=2)
            p = subprocess.run(
                ["op", "read", str(openrouter_api_key_op)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if p.returncode != 0:
                msg = sanitize_cli_error((p.stderr or "").strip() or "op read failed")
                typer.echo(msg, err=True)
                raise typer.Exit(code=p.returncode)
            os.environ["OPENROUTER_API_KEY"] = (p.stdout or "").strip()
        elif openrouter_api_key_stdin:
            os.environ["OPENROUTER_API_KEY"] = sys.stdin.read().strip()
        elif openrouter_api_key_prompt:
            os.environ["OPENROUTER_API_KEY"] = getpass.getpass(
                "OPENROUTER_API_KEY: "
            ).strip()

    # Export policy envs for downstream modules
    if bypass_permissions:
        os.environ["DSPX_POLICY_BYPASS"] = "1"
    if allowed_tools is not None:
        os.environ["DSPX_POLICY_ALLOWED_TOOLS"] = str(allowed_tools)
    if disallowed_tools is not None:
        os.environ["DSPX_POLICY_DISALLOWED_TOOLS"] = str(disallowed_tools)
    if allowed_providers is not None:
        os.environ["DSPX_POLICY_ALLOWED_PROVIDERS"] = str(allowed_providers)
    if disallowed_providers is not None:
        os.environ["DSPX_POLICY_DISALLOWED_PROVIDERS"] = str(disallowed_providers)
    if max_timeout is not None:
        os.environ["DSPX_POLICY_MAX_TIMEOUT"] = str(max_timeout)
    if allow_network_mutate:
        os.environ["DSPX_POLICY_ALLOW_NETWORK_MUTATE"] = "1"
    if allowed_http_methods is not None:
        os.environ["DSPX_POLICY_ALLOWED_HTTP_METHODS"] = str(allowed_http_methods)
    if disallowed_http_methods is not None:
        os.environ["DSPX_POLICY_DISALLOWED_HTTP_METHODS"] = str(disallowed_http_methods)


def main() -> None:
    """Main entrypoint for dspx CLI."""
    app()


if __name__ == "__main__":
    main()
