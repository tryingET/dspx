from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class GEPAResult:
    out_dir: Path
    input_keys: List[str]
    output_keys: List[str]
    chosen_output_keys: List[str]
    metric: str
    student_provider: str
    reflection_provider: str


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


def _io_spec_from_program(mod: object) -> Optional[Tuple[List[str], List[str]]]:
    io_spec = getattr(mod, "io_spec", None)
    if io_spec is None or not callable(io_spec):
        return None
    spec = io_spec()
    if isinstance(spec, tuple) and len(spec) == 2:
        inputs, outputs = spec
        if isinstance(inputs, list) and isinstance(outputs, list):
            return inputs, outputs
    if isinstance(spec, dict):
        inputs = spec.get("inputs")
        outputs = spec.get("outputs")
        if isinstance(inputs, list) and isinstance(outputs, list):
            return inputs, outputs
    raise RuntimeError(
        "io_spec() must return (inputs: list[str], outputs: list[str]) or "
        "{'inputs': [...], 'outputs': [...]}."
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
    output_keys: List[str],
) -> List[object]:
    import dspy

    out: List[object] = []
    for i, r in enumerate(records):
        missing = [k for k in ([*input_keys, *output_keys]) if k not in r]
        if missing:
            raise KeyError(f"Missing keys {missing} at row {i}")
        ex = dspy.Example(**{k: r[k] for k in ([*input_keys, *output_keys])})
        ex = ex.with_inputs(*input_keys)
        out.append(ex)
    return out


def _tokenize(s: str) -> List[str]:
    import re

    return [t for t in re.findall(r"[A-Za-z0-9_]+", s.lower()) if t]


def _f1_score(gold: str, pred: str) -> float:
    from collections import Counter

    g = _tokenize(gold)
    p = _tokenize(pred)
    if not g and not p:
        return 1.0
    if not g or not p:
        return 0.0
    cg = Counter(g)
    cp = Counter(p)
    overlap = sum((cg & cp).values())
    prec = overlap / max(1, len(p))
    rec = overlap / max(1, len(g))
    if prec + rec == 0.0:
        return 0.0
    return 2.0 * prec * rec / (prec + rec)


def _default_gepa_metric(output_keys: List[str], metric: str):
    from dspy.teleprompt.gepa.gepa_utils import ScoreWithFeedback

    def metric(gold, pred, trace, pred_name, pred_trace):  # type: ignore[no-untyped-def]
        scores: List[float] = []
        feedback_lines: List[str] = []
        for k in output_keys:
            try:
                gold_val = getattr(gold, k)
            except Exception:
                gold_val = gold[k]  # type: ignore[index]
            try:
                pred_val = getattr(pred, k)
            except Exception:
                pred_val = pred.get(k) if hasattr(pred, "get") else None

            g = str(gold_val).strip()
            p = str(pred_val).strip() if pred_val is not None else ""

            if metric == "exact":
                s = 1.0 if p == g else 0.0
            elif metric == "contains":
                s = 1.0 if (g.lower() in p.lower()) else 0.0
            elif metric == "f1":
                s = _f1_score(g, p)
            else:
                raise ValueError("metric must be one of: exact, contains, f1")

            scores.append(float(s))
            if s >= 0.999:
                feedback_lines.append(f"{k}: ok")
            else:
                feedback_lines.append(f"{k}: expected={g!r} got={p!r}")

        score = sum(scores) / max(1, len(scores))
        fb = " ; ".join(feedback_lines)
        return ScoreWithFeedback(score=float(score), feedback=fb)

    return metric


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_gepa_optimize(
    *,
    program_path: Path,
    train_path: Path,
    out_dir: Path,
    input_keys: Optional[List[str]] = None,
    output_keys: Optional[List[str]] = None,
    val_path: Optional[Path] = None,
    student_provider: Optional[str] = None,
    reflection_provider: Optional[str] = None,
    auto: Optional[str] = "light",
    max_metric_calls: Optional[int] = None,
    max_full_evals: Optional[int] = None,
    metric: str = "exact",
    seed: int = 0,
    nrows: Optional[int] = None,
) -> GEPAResult:
    """
    Optimize a DSPy program/module via GEPA and save it as a loadable program dir.

    Provider selection:
    - student_provider defaults to DSPX_PROVIDER (default: codex-exec).
    - reflection_provider defaults to student_provider.

    Program requirements:
    - PROGRAM_PATH must export build_student() -> dspy.Module
    - Provide IO in one of three ways (in order of preference):
      1) Pass input_keys/output_keys explicitly
      2) Export io_spec() -> (inputs, outputs) or {'inputs': [...], 'outputs': [...]}
      3) Student exposes student.predict.signature.{input_fields,output_fields}
    """
    import json
    import os
    from datetime import datetime, timezone

    import dspy
    from dspx.provider_registry import create, create_from_env, ensure_default_providers

    ensure_default_providers()

    student_lm = (
        create(student_provider)
        if student_provider
        else create_from_env(default="codex-exec")
    )
    reflection_lm = (
        create(reflection_provider)
        if reflection_provider
        else (
            create(student_provider)
            if student_provider
            else create_from_env(default="codex-exec")
        )
    )

    # Ensure GEPA + Predict calls use the student LM; GEPA reflections use reflection_lm.
    dspy.configure(lm=student_lm)

    mod = _import_program_module(Path(program_path))
    student = _build_student(mod)

    inferred = _io_spec_from_program(mod) or _infer_io_from_student(student)
    inferred_inputs, inferred_outputs = inferred

    in_keys = list(input_keys or inferred_inputs)
    out_keys = list(output_keys or inferred_outputs)
    if not in_keys:
        raise ValueError(
            "No input keys detected; pass input_keys or implement io_spec()"
        )
    if not out_keys:
        raise ValueError(
            "No output keys detected; pass output_keys or implement io_spec()"
        )

    train_records = _load_records(Path(train_path), nrows=nrows)
    trainset = _make_examples(train_records, input_keys=in_keys, output_keys=out_keys)
    valset = None
    if val_path is not None:
        val_records = _load_records(Path(val_path), nrows=nrows)
        valset = _make_examples(val_records, input_keys=in_keys, output_keys=out_keys)

    from dspy.teleprompt.gepa.gepa import GEPA

    budget_set = sum(
        1 for x in (auto, max_metric_calls, max_full_evals) if x is not None
    )
    if budget_set != 1:
        raise ValueError(
            "Exactly one of auto, max_metric_calls, max_full_evals must be set."
        )

    gepa = GEPA(
        _default_gepa_metric(out_keys, metric),
        auto=auto,  # type: ignore[arg-type]
        max_full_evals=max_full_evals,
        max_metric_calls=max_metric_calls,
        reflection_lm=reflection_lm,
        seed=seed,
    )

    compiled = gepa.compile(student=student, trainset=trainset, valset=valset)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Save the whole program so we can `dspy.load(out_dir)` later without source imports.
    compiled.save(str(out_dir), save_program=True)

    # Capture source + manifest for auditability and offline repro.
    source_dir = out_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    program_path = Path(program_path).resolve()
    copied_program = source_dir / program_path.name
    copied_program.write_bytes(program_path.read_bytes())

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dspy_version": getattr(dspy, "__version__", "unknown"),
        "program": {
            "path": str(program_path),
            "sha256": _sha256_file(program_path),
            "copied_to": str(copied_program),
        },
        "dataset": {
            "train": {
                "path": str(Path(train_path)),
                "sha256": _sha256_file(Path(train_path)),
                "nrows_cap": nrows,
                "nrows_loaded": len(train_records),
            },
            "val": (
                {
                    "path": str(Path(val_path)),
                    "sha256": _sha256_file(Path(val_path)),
                    "nrows_cap": nrows,
                    "nrows_loaded": len(val_records) if val_path is not None else 0,
                }
                if val_path is not None
                else None
            ),
        },
        "io": {"inputs": in_keys, "outputs": out_keys},
        "gepa": {
            "metric": metric,
            "auto": auto,
            "max_metric_calls": max_metric_calls,
            "max_full_evals": max_full_evals,
            "seed": seed,
        },
        "providers": {
            "student": {
                "name": student_provider or os.getenv("DSPX_PROVIDER", "codex-exec"),
                "model": getattr(student_lm, "model", None),
            },
            "reflection": {
                "name": reflection_provider
                or student_provider
                or os.getenv("DSPX_PROVIDER", "codex-exec"),
                "model": getattr(reflection_lm, "model", None),
            },
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return GEPAResult(
        out_dir=out_dir,
        input_keys=in_keys,
        output_keys=out_keys,
        chosen_output_keys=out_keys,
        metric=metric,
        student_provider=manifest["providers"]["student"]["name"],
        reflection_provider=manifest["providers"]["reflection"]["name"],
    )
