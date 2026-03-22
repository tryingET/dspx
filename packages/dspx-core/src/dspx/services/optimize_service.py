from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, cast


@dataclass
class GEPAResult:
    out_dir: Path
    input_keys: List[str]
    output_keys: List[str]
    chosen_output_keys: List[str]
    metric: str
    output_weights: Dict[str, float]
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


def _output_weights_from_program(mod: object) -> Optional[Dict[str, float]]:
    fn = getattr(mod, "output_weights", None)
    if fn is None or not callable(fn):
        return None
    raw = fn()
    if not isinstance(raw, dict):
        raise RuntimeError("output_weights() must return dict[str, float]")
    out: Dict[str, float] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            raise RuntimeError("output_weights() keys must be strings")
        try:
            out[k] = float(v)
        except Exception as e:
            raise RuntimeError(f"output_weights[{k!r}] is not a float") from e
    return out


def _normalize_output_from_program(
    mod: object,
) -> Optional[Callable[[str, str, str, Optional[str], object], Tuple[str, str]]]:
    """
    Optional program hook:
      normalize_output(key, gold: str, pred: str, pred_name: str|None, pred_trace) -> (gold, pred)
    """
    fn = getattr(mod, "normalize_output", None)
    if fn is None or not callable(fn):
        return None
    return fn


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
    input_keys = [str(key) for key in input_fields.keys()]
    output_keys = [str(key) for key in output_fields.keys()]
    return input_keys, output_keys


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


def _trace_hint(pred_trace: object) -> str:
    if pred_trace is None:
        return ""
    for attr in ("steps", "events", "trace"):
        try:
            v = getattr(pred_trace, attr, None)
            if isinstance(v, list):
                return f" trace_{attr}_len={len(v)}"
        except Exception:
            pass
    return " trace=1"


def _default_gepa_metric(
    output_keys: List[str],
    *,
    metric_name: str,
    output_weights: Dict[str, float],
    normalize_output: Optional[
        Callable[[str, str, str, Optional[str], object], Tuple[str, str]]
    ],
):
    from dspy.teleprompt.gepa.gepa_utils import ScoreWithFeedback

    def metric_fn(gold, pred, *args, **kwargs):
        # DSPy metric call conventions vary by version:
        # - newer: metric(gold, pred)
        # - older/GEPA: metric(gold, pred, trace, pred_name, pred_trace)
        pred_name = None
        pred_trace = None
        try:
            if len(args) >= 3:
                _trace, pred_name, pred_trace = args[0], args[1], args[2]
            else:
                pred_name = kwargs.get("pred_name")
                pred_trace = kwargs.get("pred_trace")
                _trace = kwargs.get("trace")
        except Exception:
            pass
        weighted = 0.0
        weight_sum = 0.0
        feedback_lines: List[str] = []
        for k in output_keys:
            try:
                gold_val = getattr(gold, k)
            except Exception:
                gold_val = gold[k]
            try:
                pred_val = getattr(pred, k)
            except Exception:
                pred_val = pred.get(k) if hasattr(pred, "get") else None

            g = str(gold_val).strip()
            p = str(pred_val).strip() if pred_val is not None else ""

            if normalize_output is not None:
                try:
                    g, p = normalize_output(k, g, p, pred_name, pred_trace)
                except Exception:
                    # Best-effort; normalizers must not break optimization.
                    pass

            if metric_name == "exact":
                s = 1.0 if p == g else 0.0
            elif metric_name == "contains":
                s = 1.0 if (g.lower() in p.lower()) else 0.0
            elif metric_name == "f1":
                s = _f1_score(g, p)
            else:
                raise ValueError("metric must be one of: exact, contains, f1")

            w = float(output_weights.get(k, 1.0))
            if w < 0:
                raise ValueError("output weights must be >= 0")
            weighted += w * float(s)
            weight_sum += w
            if s >= 0.999:
                feedback_lines.append(f"{k}: ok")
            else:
                feedback_lines.append(f"{k}: expected={g!r} got={p!r}")

        score = weighted / weight_sum if weight_sum > 0 else 0.0
        prefix = f"predictor={pred_name}" if pred_name else "predictor=<program>"
        fb = f"{prefix}{_trace_hint(pred_trace)} " + " ; ".join(feedback_lines)
        return ScoreWithFeedback(score=float(score), feedback=fb)

    return metric_fn


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
    output_weights: Optional[Dict[str, float]] = None,
    seed: int = 0,
    nrows: Optional[int] = None,
) -> GEPAResult:
    """
    Optimize a DSPy program/module via GEPA and save it as a loadable program dir.

    Provider selection:
    - student_provider defaults to DSPX_PROVIDER (default: pi-rpc).
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
    from dspx.provider_runtime import provider_metadata_from_instance

    ensure_default_providers()

    student_lm = (
        create(student_provider)
        if student_provider
        else create_from_env(default="pi-rpc")
    )
    reflection_lm = (
        create(reflection_provider)
        if reflection_provider
        else (
            create(student_provider)
            if student_provider
            else create_from_env(default="pi-rpc")
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

    weights = dict(output_weights or {})
    prog_weights = _output_weights_from_program(mod)
    if prog_weights is not None:
        weights = dict(prog_weights)
    for k in list(weights.keys()):
        if k not in out_keys:
            raise ValueError(f"Unknown output key in weights: {k}")
    for k, v in list(weights.items()):
        try:
            weights[k] = float(v)
        except Exception as e:
            raise ValueError(f"Invalid weight for {k}: {v!r}") from e
        if weights[k] < 0:
            raise ValueError("output weights must be >= 0")

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

    normalize_output = _normalize_output_from_program(mod)

    gepa: Any = GEPA(
        _default_gepa_metric(
            out_keys,
            metric_name=metric,
            output_weights=weights,
            normalize_output=normalize_output,
        ),
        auto=auto,  # type: ignore[arg-type]
        max_full_evals=max_full_evals,
        max_metric_calls=max_metric_calls,
        reflection_lm=cast(Any, reflection_lm),
        seed=seed,
    )

    compiled: Any = gepa.compile(
        student=cast(Any, student),
        trainset=cast(Any, trainset),
        valset=cast(Any, valset),
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Save the whole program so we can load it later without source imports.
    # DSPy 3.1+ requires: `dspy.load(out_dir, allow_pickle=True)`.
    compiled.save(str(out_dir), save_program=True)

    # Capture source + manifest for auditability and offline repro.
    source_dir = out_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    program_path = Path(program_path).resolve()
    copied_program = source_dir / program_path.name
    copied_program.write_bytes(program_path.read_bytes())

    student_provider_name = student_provider or os.getenv("DSPX_PROVIDER", "pi-rpc")
    reflection_provider_name = (
        reflection_provider or student_provider or os.getenv("DSPX_PROVIDER", "pi-rpc")
    )

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dspy_version": getattr(dspy, "__version__", "unknown"),
        "dspx_version": _dspx_version(),
        "python": _python_env(),
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
            "output_weights": weights,
            "auto": auto,
            "max_metric_calls": max_metric_calls,
            "max_full_evals": max_full_evals,
            "seed": seed,
        },
        "providers": {
            "student": provider_metadata_from_instance(
                str(student_provider_name), student_lm
            ),
            "reflection": provider_metadata_from_instance(
                str(reflection_provider_name), reflection_lm
            ),
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return GEPAResult(
        out_dir=out_dir,
        input_keys=in_keys,
        output_keys=out_keys,
        chosen_output_keys=out_keys,
        metric=metric,
        output_weights=weights,
        student_provider=str(student_provider_name),
        reflection_provider=str(reflection_provider_name),
    )


def _dspx_version() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("dspx")
        except PackageNotFoundError:
            return None
    except Exception:
        return None


def _python_env() -> dict[str, str]:
    import platform
    import sys

    return {
        "executable": sys.executable,
        "version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
