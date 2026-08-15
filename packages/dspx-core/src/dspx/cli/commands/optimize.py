# summary: "Defines the CLI command for running bounded GEPA optimization on DSPy programs."
# read_when:
#   - "Changing optimizer provider resolution, budget selection, dataset options, metrics, or output weights."

"""Program optimization commands.

Commands for running DSPy optimizers like GEPA.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Literal, Optional, cast

import typer

from dspx.cli.utils import ensure_env

app = typer.Typer(no_args_is_help=True)


def _resolve_optimize_providers(
    student_provider: Optional[str], reflection_provider: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    student = (
        student_provider
        if student_provider is not None
        else os.getenv("DSPX_OPTIMIZE_STUDENT_PROVIDER") or os.getenv("DSPX_PROVIDER")
    )
    reflection = (
        reflection_provider
        if reflection_provider is not None
        else os.getenv("DSPX_OPTIMIZE_REFLECTION_PROVIDER") or student
    )
    return student, reflection


@app.command("gepa")
def optimize_gepa(
    program: Path = typer.Option(
        ...,
        "--program",
        help="Path to a Python file exporting build_student() -> dspy.Module",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    train: Path = typer.Option(
        ...,
        "--train",
        help="Training dataset path (.csv/.parquet) with columns matching module inputs + output",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Output directory to save optimized program (loadable via dspy.load)",
        file_okay=False,
        dir_okay=True,
    ),
    val: Optional[Path] = typer.Option(
        None,
        "--val",
        help="Optional validation dataset path (.csv/.parquet)",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    input_keys: List[str] = typer.Option(
        [],
        "--input",
        help="Input column/key (repeatable). If omitted, inferred from io_spec() or module signature.",
    ),
    output_keys: List[str] = typer.Option(
        [],
        "--output-key",
        help="Output column/key (repeatable). If omitted, inferred from io_spec() or module signature.",
    ),
    metric: str = typer.Option(
        "exact", help="Metric: exact|contains|f1 (per output, averaged)"
    ),
    output_weight: List[str] = typer.Option(
        [],
        "--output-weight",
        help="Per-output weight as key=float (repeatable). Overrides defaults; can also be provided by program output_weights().",
    ),
    student_provider: Optional[str] = typer.Option(
        None,
        "--student-provider",
        help="Provider for student calls (stub or configured openai-compatible; defaults to explicit DSPX_PROVIDER).",
    ),
    reflection_provider: Optional[str] = typer.Option(
        None,
        "--reflection-provider",
        help="Provider for GEPA reflections (stub or configured openai-compatible; defaults to student-provider).",
    ),
    auto: Optional[str] = typer.Option(
        None,
        help="GEPA intensity: light|medium|heavy (required unless using --max-metric-calls/--max-full-evals).",
    ),
    max_metric_calls: Optional[int] = typer.Option(
        None,
        help="Limit total metric calls (controls GEPA cost/time). If set, --auto is ignored.",
    ),
    max_full_evals: Optional[int] = typer.Option(
        None,
        help="Limit full evaluations (alternative GEPA budget selector).",
    ),
    seed: int = typer.Option(0, help="Deterministic seed for GEPA search"),
    nrows: Optional[int] = typer.Option(
        None, help="Optional cap on rows loaded from train/val datasets"
    ),
) -> None:
    """Run GEPA optimization on a DSPy program.

    The program file must export a build_student() function that returns a dspy.Module.
    """
    from dspx.services.optimize_service import run_gepa_optimize

    ensure_env(student_provider)
    student_provider, reflection_provider = _resolve_optimize_providers(
        student_provider, reflection_provider
    )

    budget_set = sum(
        1 for x in (auto, max_metric_calls, max_full_evals) if x is not None
    )
    if budget_set != 1:
        raise typer.BadParameter(
            "Exactly one of --auto, --max-metric-calls, --max-full-evals must be set."
        )

    weights = None
    if output_weight:
        weights = {}
        for item in output_weight:
            if "=" not in item:
                raise typer.BadParameter(
                    "Invalid --output-weight; expected key=float",
                    param_hint="--output-weight",
                )
            k, v = item.split("=", 1)
            k = k.strip()
            if not k:
                raise typer.BadParameter(
                    "Invalid --output-weight; empty key", param_hint="--output-weight"
                )
            try:
                weights[k] = float(v.strip())
            except Exception as e:
                raise typer.BadParameter(
                    "Invalid --output-weight; value must be float",
                    param_hint="--output-weight",
                ) from e

    res = run_gepa_optimize(
        program_path=program,
        train_path=train,
        val_path=val,
        out_dir=out,
        input_keys=input_keys or None,
        output_keys=output_keys or None,
        student_provider=student_provider,
        reflection_provider=reflection_provider,
        auto=cast(Optional[Literal["light", "medium", "heavy"]], auto),
        max_metric_calls=int(max_metric_calls)
        if max_metric_calls is not None
        else None,
        max_full_evals=int(max_full_evals) if max_full_evals is not None else None,
        metric=metric,
        output_weights=weights,
        seed=int(seed),
        nrows=nrows,
    )
    typer.echo(str(res.out_dir))
