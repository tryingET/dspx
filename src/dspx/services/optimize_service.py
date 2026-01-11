from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class GEPAResult:
    out_dir: Path
    input_keys: List[str]
    output_keys: List[str]
    chosen_output_key: str


def _import_program_module(program_path: Path) -> object:
    import importlib.util
    import sys

    program_path = program_path.resolve()
    spec = importlib.util.spec_from_file_location(program_path.stem, program_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import program module from {program_path}")
    mod = importlib.util.module_from_spec(spec)
    # Ensure relative imports inside the program can work if it expects cwd context.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_student(mod: object) -> object:
    if hasattr(mod, "build_student") and callable(getattr(mod, "build_student")):
        return getattr(mod, "build_student")()
    raise RuntimeError(
        "Program file must export build_student() -> dspy.Module for GEPA optimization"
    )


def _infer_io_from_student(student: object) -> Tuple[List[str], List[str]]:
    # We intentionally keep the first GEPA slice narrow:
    # require a `student.predict` with a DSPy signature for field discovery.
    predict = getattr(student, "predict", None)
    sig = getattr(predict, "signature", None)
    input_fields = getattr(sig, "input_fields", None)
    output_fields = getattr(sig, "output_fields", None)
    if not isinstance(input_fields, dict) or not isinstance(output_fields, dict):
        raise RuntimeError(
            "Student module must expose .predict.signature.input_fields/output_fields"
        )
    return list(input_fields.keys()), list(output_fields.keys())


def _load_records(path: Path, *, nrows: Optional[int] = None) -> List[Dict[str, Any]]:
    from dspx.adapters.datasets import CSVDataset, ParquetDataset

    lower = path.name.lower()
    if lower.endswith(".csv"):
        return CSVDataset(path, nrows=nrows).load()
    if lower.endswith(".parquet"):
        return ParquetDataset(path, nrows=nrows).load()
    raise ValueError("Unsupported dataset type (expected .csv or .parquet)")


def _make_examples(
    records: Iterable[Dict[str, Any]],
    *,
    input_keys: List[str],
    output_key: str,
) -> List[object]:
    import dspy

    out: List[object] = []
    for i, r in enumerate(records):
        missing = [k for k in ([*input_keys, output_key]) if k not in r]
        if missing:
            raise KeyError(f"Missing keys {missing} at row {i}")
        ex = dspy.Example(**{k: r[k] for k in ([*input_keys, output_key])})
        ex = ex.with_inputs(*input_keys)
        out.append(ex)
    return out


def _default_gepa_metric(output_key: str):
    from dspy.teleprompt.gepa.gepa_utils import ScoreWithFeedback

    def metric(gold, pred, trace, pred_name, pred_trace):  # type: ignore[no-untyped-def]
        try:
            gold_val = getattr(gold, output_key)
        except Exception:
            gold_val = gold[output_key]  # type: ignore[index]
        try:
            pred_val = getattr(pred, output_key)
        except Exception:
            pred_val = pred.get(output_key) if hasattr(pred, "get") else None

        g = str(gold_val).strip()
        p = str(pred_val).strip()
        score = 1.0 if p == g else 0.0
        if score >= 1.0:
            fb = "Correct."
        else:
            fb = f"Expected {output_key}={g!r} but got {p!r}."
        return ScoreWithFeedback(score=score, feedback=fb)

    return metric


def run_gepa_optimize(
    *,
    program_path: Path,
    train_path: Path,
    out_dir: Path,
    output_key: Optional[str] = None,
    val_path: Optional[Path] = None,
    provider: Optional[str] = None,
    auto: str = "light",
    max_metric_calls: Optional[int] = None,
    max_full_evals: Optional[int] = None,
    seed: int = 0,
    nrows: Optional[int] = None,
) -> GEPAResult:
    """
    Optimize a DSPy program/module via GEPA and save it as a loadable program dir.

    Provider selection:
    - Defaults to DSPX_PROVIDER (provider registry), which defaults to 'codex-exec'.
    - For GEPA, both the student's LM and GEPA's reflection_lm use the same provider.

    Program requirements (first slice):
    - PROGRAM_PATH must export build_student() -> dspy.Module
    - The returned module must expose .predict.signature.input_fields/output_fields
    """
    import dspy
    from dspx.provider_registry import create_from_env

    if provider:
        import os

        os.environ["DSPX_PROVIDER"] = provider

    lm = create_from_env()
    # Ensure GEPA + Predict calls use the same LM (CodexExecLM by default).
    dspy.configure(lm=lm)

    mod = _import_program_module(Path(program_path))
    student = _build_student(mod)
    input_keys, output_keys = _infer_io_from_student(student)

    chosen_output = output_key or (output_keys[0] if len(output_keys) == 1 else None)
    if not chosen_output:
        raise ValueError(
            "Multiple output fields detected; pass output_key to select one"
        )

    train_records = _load_records(Path(train_path), nrows=nrows)
    trainset = _make_examples(
        train_records, input_keys=input_keys, output_key=chosen_output
    )
    valset = None
    if val_path is not None:
        val_records = _load_records(Path(val_path), nrows=nrows)
        valset = _make_examples(
            val_records, input_keys=input_keys, output_key=chosen_output
        )

    from dspy.teleprompt.gepa.gepa import GEPA

    metric = _default_gepa_metric(chosen_output)
    # GEPA requires exactly one budget selector: auto OR max_metric_calls OR max_full_evals.
    auto_arg: Optional[str] = auto
    if max_metric_calls is not None or max_full_evals is not None:
        auto_arg = None

    gepa = GEPA(
        metric,
        auto=auto_arg,  # type: ignore[arg-type]
        max_full_evals=max_full_evals,
        max_metric_calls=max_metric_calls,
        reflection_lm=lm,  # critical: run reflections on the same provider (codex)
        seed=seed,
    )

    compiled = gepa.compile(student=student, trainset=trainset, valset=valset)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Save the whole program so we can `dspy.load(out_dir)` later without source imports.
    try:
        compiled.save(
            str(out_dir),
            save_program=True,
            modules_to_serialize=[mod],  # type: ignore[list-item]
        )
    except Exception:
        # Fallback: save without module-by-value registration.
        compiled.save(str(out_dir), save_program=True)

    return GEPAResult(
        out_dir=out_dir,
        input_keys=input_keys,
        output_keys=output_keys,
        chosen_output_key=chosen_output,
    )
