# summary: "Defines the CLI command for generating DSPy module scaffolds and recording local receipts."
# read_when:
#   - "Changing module-gen validation, generation options, output receipts, caching, or MLflow logging."

"""Module generation command.

Command for generating DSPy module scaffolds.
"""

from __future__ import annotations

import keyword
import os
import re
import sys
from pathlib import Path
from typing import Any, List, Optional

import typer

from dspx.cli.utils import ensure_env, require_template_adapter

app = typer.Typer(no_args_is_help=True)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _invalid_field_names(values: List[str]) -> list[str]:
    invalid: list[str] = []
    for raw in values:
        name = str(raw).strip()
        if not name or not _IDENTIFIER_RE.match(name) or keyword.iskeyword(name):
            invalid.append(str(raw))
    return invalid


def validate_module_fields_or_exit(
    inputs: List[str], outputs: List[str], module_name: str | None = None
) -> None:
    invalid_inputs = _invalid_field_names(inputs)
    invalid_outputs = _invalid_field_names(outputs)
    invalid_module = []
    if module_name is not None:
        invalid_module = _invalid_field_names([module_name])

    duplicate_inputs = sorted({value for value in inputs if inputs.count(value) > 1})
    duplicate_outputs = sorted({value for value in outputs if outputs.count(value) > 1})
    overlap = sorted(set(inputs) & set(outputs))

    if (
        invalid_module
        or invalid_inputs
        or invalid_outputs
        or duplicate_inputs
        or duplicate_outputs
        or overlap
    ):
        details: list[str] = []
        if invalid_module:
            details.append(f"module={invalid_module}")
        if invalid_inputs:
            details.append(f"inputs={invalid_inputs}")
        if invalid_outputs:
            details.append(f"outputs={invalid_outputs}")
        if duplicate_inputs:
            details.append(f"duplicate_inputs={duplicate_inputs}")
        if duplicate_outputs:
            details.append(f"duplicate_outputs={duplicate_outputs}")
        if overlap:
            details.append(f"input_output_overlap={overlap}")
        typer.echo(
            "Error: module name and fields must be valid Python identifiers and unique; "
            + "; ".join(details),
            err=True,
        )
        raise typer.Exit(code=2)


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

    # Fast-fail if template-config requested but file doesn't exist or adapter not installed
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


def _write_module_output(
    outfile: Path,
    code: str,
    name: str,
    description: str,
    inputs: List[str],
    outputs: List[str],
    use_signature: bool,
    template_version: str,
    artifact_metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Write module output with receipt and MLflow logging."""
    outfile.parent.mkdir(parents=True, exist_ok=True)
    outfile.write_text(code, encoding="utf-8")

    # Write a versioned run receipt for replay/explain
    try:
        from dspx.cache import cache_dir, cache_enabled, make_key, sha256_text
        from dspx.run_receipts import (
            build_mlflow_hints,
            build_run_receipt,
            current_receipt_lineage,
            write_run_receipt,
        )

        cache_key = make_key(
            {
                "kind": "module",
                "name": name,
                "description": description,
                "inputs": inputs,
                "outputs": outputs,
                "use_signature": bool(use_signature),
                "template_version": template_version,
            }
        )
        cfile = cache_dir() / "module" / f"{cache_key}.json"
        cache_is_enabled = cache_enabled()
        output_hash = sha256_text(code)

        synthesis_extra: dict[str, Any] = {}
        run_summary = None
        if isinstance(artifact_metadata, dict):
            maybe_summary = artifact_metadata.get("run_summary")
            if isinstance(maybe_summary, dict):
                run_summary = maybe_summary
            synthesis = artifact_metadata.get("synthesis")
            if isinstance(synthesis, dict):
                synthesis_extra["synthesis"] = synthesis
                request = synthesis.get("request")
                if isinstance(request, dict) and request.get("request_id"):
                    synthesis_extra["synthesis_request_id"] = request["request_id"]
                diagnostics = artifact_metadata.get("synthesis_diagnostics")
                if isinstance(diagnostics, dict):
                    synthesis_extra["synthesis_diagnostics"] = diagnostics
                candidates = synthesis.get("candidates")
                if isinstance(candidates, list):
                    synthesis_extra["synthesis_candidate_ids"] = [
                        item.get("candidate_id")
                        for item in candidates
                        if isinstance(item, dict) and item.get("candidate_id")
                    ]
                evaluations = synthesis.get("evaluations")
                if isinstance(evaluations, list):
                    synthesis_extra["synthesis_evaluation_ids"] = [
                        item.get("evaluation_id")
                        for item in evaluations
                        if isinstance(item, dict) and item.get("evaluation_id")
                    ]
                if isinstance(synthesis.get("promotion_shell"), dict):
                    synthesis_extra["synthesis_promotion_shell"] = synthesis[
                        "promotion_shell"
                    ]
                if isinstance(synthesis.get("promotion_decision"), dict):
                    synthesis_extra["synthesis_promotion_decision"] = synthesis[
                        "promotion_decision"
                    ]
                    ranked = (
                        synthesis["promotion_decision"].get("metadata", {})
                        if isinstance(
                            synthesis["promotion_decision"].get("metadata"), dict
                        )
                        else {}
                    )
                    if isinstance(ranked.get("ranked_candidates"), list):
                        synthesis_extra["synthesis_ranked_candidates"] = ranked[
                            "ranked_candidates"
                        ]
                if isinstance(synthesis.get("selection_policy"), dict):
                    synthesis_extra["synthesis_selection_policy"] = synthesis[
                        "selection_policy"
                    ]

        meta = build_run_receipt(
            run_kind="module-gen",
            output_path=outfile,
            output_hash=output_hash,
            template_version=template_version,
            cache_key=cache_key,
            cache_file=str(cfile),
            cache_enabled=cache_is_enabled,
            replay_inputs={
                "name": name,
                "description": description,
                "inputs": list(inputs),
                "outputs": list(outputs),
                "use_signature": bool(use_signature),
                "template_version": template_version,
            },
            run_summary=run_summary,
            extra={
                "use_signature": bool(use_signature),
                "name": name,
                "inputs": list(inputs),
                "outputs": list(outputs),
                **synthesis_extra,
                "mlflow_hints": build_mlflow_hints(
                    run_kind="module-gen",
                    template_version=template_version,
                    output_path=outfile,
                    output_hash=output_hash,
                    cache_key=cache_key,
                ),
            },
            **current_receipt_lineage(),
        )
        write_run_receipt(outfile, meta)
    except Exception:
        pass

    # MLflow logging of artifacts
    try:
        from dspx.cache import make_key, sha256_text
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        cache_key_for_tags = make_key(
            {
                "kind": "module",
                "name": name,
                "description": description,
                "inputs": inputs,
                "outputs": outputs,
                "use_signature": bool(use_signature),
                "template_version": template_version,
            }
        )
        output_hash_for_tags = sha256_text(code)

        mlflow = get_mlflow()
        if mlflow is not None:
            ensure_run_with_standard_tags(
                "module",
                template_version=template_version,
                run_name=f"module-{name}",
                run_kind="module-gen",
                output_basename=outfile.name,
                cache_key=cache_key_for_tags,
                output_hash=output_hash_for_tags,
            )
            if mlflow.active_run() is not None:
                try:
                    mlflow.log_artifact(str(outfile))
                except Exception:
                    pass
                meta_path = outfile.parent / (outfile.name + ".meta.json")
                if meta_path.exists():
                    try:
                        mlflow.log_artifact(str(meta_path))
                    except Exception:
                        pass
    except Exception:
        pass


def _print_module_cache_info(
    name: str,
    description: str,
    inputs: List[str],
    outputs: List[str],
    use_signature: bool,
    template_version: str,
) -> None:
    """Print cache key and file info for module."""
    try:
        from dspx.cache import cache_dir, make_key

        cache_key = make_key(
            {
                "kind": "module",
                "name": name,
                "description": description,
                "inputs": inputs,
                "outputs": outputs,
                "use_signature": bool(use_signature),
                "template_version": template_version,
            }
        )
        cfile = cache_dir() / "module" / f"{cache_key}.json"
        typer.echo(
            f"cache_key={cache_key} cache_file={cfile} exists={cfile.exists()}",
            err=True,
        )
    except Exception:
        pass
