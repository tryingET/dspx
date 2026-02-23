"""Adapter commands for datasets and evaluation.

Commands for dataset loading, splitting, and evaluation metrics.
"""

from __future__ import annotations

import csv as csv_module
import json
import os
from pathlib import Path
from typing import Any, Optional, cast

import typer

from dspx.adapters import datasets as _datasets

app = typer.Typer(no_args_is_help=True)
dataset_app = typer.Typer(no_args_is_help=True)
eval_app = typer.Typer(no_args_is_help=True)

app.add_typer(dataset_app, name="dataset", help="Dataset adapters")
app.add_typer(eval_app, name="eval", help="Evaluation helpers")


@app.command("list")
def adapters_list(
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List available adapters."""
    # Keep this list in sync with adapters package
    items = [
        "dataset.csv",
        "dataset.parquet",
        "dataset.mlflow",
        "eval.accuracy",
        "eval.f1_binary",
        "store.local_object",
    ]
    descs = {
        "dataset.csv": "CSV dataset loader",
        "dataset.parquet": "Parquet dataset loader",
        "dataset.mlflow": "MLflow dataset reference",
        "eval.accuracy": "Accuracy metric",
        "eval.f1_binary": "F1 (binary) metric",
        "store.local_object": "Local object store",
    }
    if json_out:
        typer.echo(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        for line in items:
            d = descs.get(line)
            if d:
                typer.echo(f"{line} - {d}")
            else:
                typer.echo(line)


@dataset_app.command("describe")
def adapters_dataset_describe(
    type: str = typer.Option(..., "--type", "-t", help="csv|parquet|mlflow"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="File path"),
    run_id: Optional[str] = typer.Option(None, help="MLflow run_id (mlflow only)"),
    artifact_path: Optional[str] = typer.Option(
        None, help="MLflow artifact path (mlflow only)"
    ),
    nrows: int = typer.Option(5, help="Preview rows for csv/parquet"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Describe a dataset."""
    t = type.strip().lower()
    if t in {"csv", "parquet"}:
        if not path:
            raise typer.Exit(code=2)
        if t == "csv":
            ds = _datasets.CSVDataset(str(path), nrows=nrows)
        else:
            ds = _datasets.ParquetDataset(str(path), nrows=nrows)
        try:
            rows = ds.load()
        except Exception as e:
            typer.echo(f"error: {e}")
            raise typer.Exit(code=1)
        cols = list(rows[0].keys()) if rows else []
        out = {"type": t, "path": str(path), "columns": cols, "rows": rows}
    elif t == "mlflow":
        if not run_id or not artifact_path:
            raise typer.Exit(code=2)
        ref = _datasets.MLflowDatasetRef(run_id=run_id, artifact_path=artifact_path)
        out = ref.describe()
    else:
        raise typer.Exit(code=2)

    if json_out:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if out.get("type") == "mlflow_artifact":
            typer.echo(
                f"mlflow dataset: run_id={out['run_id']} artifact_path={out['artifact_path']}"
            )
        else:
            typer.echo(f"type: {out['type']} path: {out['path']}")
            cols_any = out.get("columns")
            cols_txt = (
                ", ".join(str(c) for c in cols_any)
                if isinstance(cols_any, list)
                else ""
            )
            typer.echo("columns: " + cols_txt)
            typer.echo("rows:")
            for r in out.get("rows", [])[:nrows]:
                typer.echo(str(r))


@dataset_app.command("split")
def adapters_dataset_split(
    csv: Path = typer.Option(..., "--csv", help="CSV path to split"),
    outdir: Path = typer.Option(..., "--outdir", help="Output directory for splits"),
    test_size: Optional[float] = typer.Option(None, help="Test fraction (0-1)"),
    ratios: Optional[str] = typer.Option(
        None, help="Comma-separated ratios train,val,test that sum to 1"
    ),
    seed: int = typer.Option(42, help="Random seed for shuffling"),
    stratify_col: Optional[str] = typer.Option(
        None, help="Column name for label stratification"
    ),
    group_col: Optional[str] = typer.Option(
        None, help="Optional group column to keep groups intact"
    ),
    group_balance: str = typer.Option(
        "instances",
        help="When using --group-col with stratification, balance per label by 'instances' or 'groups'",
    ),
    min_per_label: Optional[int] = typer.Option(
        None,
        help="Minimum per-label count per partition (applies only to stratified splits)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Output JSON summary"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Plan splits without writing files"
    ),
) -> None:
    """Split a dataset into train/val/test partitions."""
    import pandas as pd
    from dspx.adapters.datasets import (
        train_test_split as _tts,
        train_val_test_split as _tvts,
        stratified_train_test_split as _stts,
        stratified_train_val_test_split as _stvts,
    )

    df = pd.read_csv(str(csv))
    records = df.to_dict(orient="records")
    if not dry_run:
        outdir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"input": str(csv), "outdir": str(outdir)}

    if ratios:
        try:
            parts = [float(x.strip()) for x in ratios.split(",")]
        except Exception:
            raise typer.Exit(code=2)
        # If stratify requested, ensure columns exist and use stratified split
        if stratify_col:
            if stratify_col not in df.columns:
                typer.echo(f"error: stratify_col '{stratify_col}' not found")
                raise typer.Exit(code=2)
            if group_col and group_col not in df.columns:
                typer.echo(f"error: group_col '{group_col}' not found")
                raise typer.Exit(code=2)
            tr, va, te = _stvts(
                records,
                label_key=str(stratify_col),
                ratios=tuple(parts),
                seed=seed,
                group_key=str(group_col) if group_col else None,
                group_balance=group_balance,
                min_per_label=min_per_label,
            )
        else:
            tr, va, te = _tvts(records, ratios=tuple(parts), seed=seed)
        if not dry_run:
            pd.DataFrame(tr).to_csv(outdir / "train.csv", index=False)
            pd.DataFrame(va).to_csv(outdir / "val.csv", index=False)
            pd.DataFrame(te).to_csv(outdir / "test.csv", index=False)
        summary.update(
            {
                "train": str(outdir / "train.csv"),
                "val": str(outdir / "val.csv"),
                "test": str(outdir / "test.csv"),
                "counts": {"train": len(tr), "val": len(va), "test": len(te)},
            }
        )
    else:
        ts = 0.2 if test_size is None else float(test_size)
        if stratify_col:
            if stratify_col not in df.columns:
                typer.echo(f"error: stratify_col '{stratify_col}' not found")
                raise typer.Exit(code=2)
            if group_col and group_col not in df.columns:
                typer.echo(f"error: group_col '{group_col}' not found")
                raise typer.Exit(code=2)
            tr, te = _stts(
                records,
                label_key=str(stratify_col),
                test_size=ts,
                seed=seed,
                group_key=str(group_col) if group_col else None,
                group_balance=group_balance,
                min_per_label=min_per_label,
            )
        else:
            tr, te = _tts(records, test_size=ts, seed=seed)
        if not dry_run:
            pd.DataFrame(tr).to_csv(outdir / "train.csv", index=False)
            pd.DataFrame(te).to_csv(outdir / "test.csv", index=False)
        summary.update(
            {
                "train": str(outdir / "train.csv"),
                "test": str(outdir / "test.csv"),
                "counts": {"train": len(tr), "test": len(te)},
            }
        )
    # Always emit JSON for deterministic CLI consumption
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


def _parse_bool(x: object) -> object:
    """Normalize booleans from common textual forms."""
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    if s in {"true", "1", "yes"}:
        return True
    if s in {"false", "0", "no"}:
        return False
    return x


@eval_app.command("run")
def adapters_eval_run(
    csv: Path = typer.Option(..., "--csv", help="CSV path containing labels"),
    truth_col: str = typer.Option(..., "--truth-col", help="Column for ground truth"),
    pred_col: str = typer.Option(..., "--pred-col", help="Column for predictions"),
    metric: str = typer.Option(
        ...,
        "--metric",
        help="accuracy|f1|confusion|roc_auc|roc_curve|rouge1_f1|bleu1|bertscore_f1|per_class_pr|pr_curve|ece",
    ),
    positive_label: Optional[str] = typer.Option(
        None, "--positive-label", help="Label considered positive for F1"
    ),
    average: str = typer.Option(
        "micro", "--average", help="Averaging for text metrics (micro|macro)"
    ),
    outdir: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Directory to export CSVs for supported metrics (pr_curve, roc_curve, per_class_pr)",
    ),
    json_out: bool = typer.Option(True, "--json", help="Output JSON"),
) -> None:
    """Run evaluation metrics on predictions."""
    import pandas as pd
    from dspx.adapters.eval import (
        accuracy,
        f1_binary,
        confusion_matrix_binary,
        rouge1_f1,
        bleu1,
        rouge1_f1_macro,
        bleu1_macro,
        roc_auc_binary,
        roc_curve_binary,
        precision_recall_per_class,
        pr_curve_binary,
        expected_calibration_error_binary,
        bertscore_f1,
        bertscore_f1_macro,
    )

    df = pd.read_csv(str(csv))
    if truth_col not in df.columns or pred_col not in df.columns:
        raise typer.Exit(code=2)
    y_true = [_parse_bool(v) for v in df[truth_col].tolist()]
    y_pred = [_parse_bool(v) for v in df[pred_col].tolist()]
    m = metric.strip().lower()

    if m == "accuracy":
        val = accuracy(y_true, y_pred)
        out: dict[str, Any] = {"metric": m, "value": float(val)}
    elif m == "f1":
        val = f1_binary(y_true, y_pred, positive_label=positive_label)
        out = {"metric": m, "value": float(val)}
    elif m == "confusion":
        cm = confusion_matrix_binary(y_true, y_pred, positive_label=positive_label)
        out = {"metric": m, **cm}
        if json_out:
            typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"tp={cm['tp']} tn={cm['tn']} fp={cm['fp']} fn={cm['fn']}")
        return
    elif m == "roc_auc":
        try:
            val = roc_auc_binary(y_true, y_pred, positive_label=positive_label)
        except Exception:
            try:
                scores = [float(cast(Any, v)) for v in y_pred]
            except Exception:
                raise typer.Exit(code=2)
            val = roc_auc_binary(y_true, scores, positive_label=positive_label)
        out = {"metric": m, "value": float(val)}
    elif m == "rouge1_f1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        val = rouge1_f1(refs, cands) if avg == "micro" else rouge1_f1_macro(refs, cands)
        out = {"metric": m, "value": float(val)}
    elif m == "bleu1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        val = bleu1(refs, cands) if avg == "micro" else bleu1_macro(refs, cands)
        out = {"metric": m, "value": float(val)}
    elif m == "per_class_pr":
        per = precision_recall_per_class(y_true, y_pred)
        out = {"metric": m, "classes": per}
        _export_pr_csv(outdir, per)
        if json_out:
            typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            for k, v in per.items():
                typer.echo(
                    f"{k}: precision={v['precision']:.4f} recall={v['recall']:.4f}"
                )
        return
    elif m == "bertscore_f1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        model = os.getenv("DSPX_BERTSCORE_MODEL")
        lang = os.getenv("DSPX_BERTSCORE_LANG", "en")
        rescale = os.getenv("DSPX_BERTSCORE_RESCALE", "").lower() in {
            "1",
            "true",
            "yes",
        }
        try:
            val = (
                bertscore_f1(
                    refs, cands, model=model, lang=lang, rescale_with_baseline=rescale
                )
                if avg == "micro"
                else bertscore_f1_macro(
                    refs, cands, model=model, lang=lang, rescale_with_baseline=rescale
                )
            )
        except ImportError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=2)
        out = {"metric": m, "value": float(val)}
    elif m == "pr_curve":
        try:
            scores = [float(cast(Any, v)) for v in y_pred]
        except Exception:
            raise typer.Exit(code=2)
        curve = pr_curve_binary(y_true, scores, positive_label=positive_label)
        _export_curve_csv(
            outdir,
            "pr_curve",
            ["threshold", "precision", "recall"],
            zip(curve["thresholds"], curve["precision"], curve["recall"]),
        )
        out = {"metric": m, **curve}
        if json_out:
            typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"points={len(curve['thresholds'])}")
        return
    elif m == "roc_curve":
        try:
            scores = [float(cast(Any, v)) for v in y_pred]
        except Exception:
            raise typer.Exit(code=2)
        curve = roc_curve_binary(y_true, scores, positive_label=positive_label)
        _export_curve_csv(
            outdir,
            "roc_curve",
            ["threshold", "tpr", "fpr"],
            zip(curve["thresholds"], curve["tpr"], curve["fpr"]),
        )
        out = {"metric": m, **curve}
        if json_out:
            typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"points={len(curve['thresholds'])}")
        return
    elif m == "ece":
        try:
            scores = [float(cast(Any, v)) for v in y_pred]
        except Exception:
            raise typer.Exit(code=2)
        val = expected_calibration_error_binary(
            y_true, scores, positive_label=positive_label
        )
        out = {"metric": m, "value": float(val)}
        if json_out:
            typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"ece: {val:.6f}")
        return
    else:
        raise typer.Exit(code=2)

    if json_out:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"{m}: {out['value']:.6f}")


@eval_app.command("run2")
def adapters_eval_run2(
    csv_true: Path = typer.Option(..., "--csv-true", help="CSV with ground truth"),
    csv_pred: Path = typer.Option(..., "--csv-pred", help="CSV with predictions"),
    id_col: str = typer.Option("id", "--id-col", help="Join key column"),
    truth_col: str = typer.Option("y", "--truth-col", help="Truth column in csv_true"),
    pred_col: str = typer.Option("yhat", "--pred-col", help="Pred column in csv_pred"),
    metric: str = typer.Option(
        ...,
        "--metric",
        help="accuracy|f1|confusion|roc_auc|roc_curve|rouge1_f1|bleu1|bertscore_f1|per_class_pr|pr_curve",
    ),
    positive_label: Optional[str] = typer.Option(
        None, "--positive-label", help="Label considered positive for F1/confusion"
    ),
    average: str = typer.Option(
        "micro", "--average", help="Averaging for text metrics (micro|macro)"
    ),
    outdir: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Directory to export CSVs for supported metrics",
    ),
    json_out: bool = typer.Option(True, "--json", help="Output JSON"),
) -> None:
    """Run evaluation metrics on two CSV files joined by ID."""
    import pandas as pd
    from dspx.adapters.eval import (
        accuracy,
        f1_binary,
        confusion_matrix_binary,
        rouge1_f1,
        bleu1,
        rouge1_f1_macro,
        bleu1_macro,
        roc_auc_binary,
        precision_recall_per_class,
        pr_curve_binary,
        roc_curve_binary,
        bertscore_f1,
        bertscore_f1_macro,
    )

    df_t = pd.read_csv(str(csv_true))[[id_col, truth_col]]
    df_p = pd.read_csv(str(csv_pred))[[id_col, pred_col]]
    merged = pd.merge(df_t, df_p, on=id_col, how="inner", suffixes=("_t", "_p"))
    y_true = merged[truth_col].tolist()
    y_pred = merged[pred_col].tolist()
    m = metric.strip().lower()

    if m == "accuracy":
        val = accuracy(y_true, y_pred)
        out: dict[str, Any] = {
            "metric": m,
            "value": float(val),
            "count": int(len(merged)),
        }
    elif m == "f1":
        val = f1_binary(y_true, y_pred, positive_label=positive_label)
        out = {"metric": m, "value": float(val), "count": int(len(merged))}
    elif m == "confusion":
        cm = confusion_matrix_binary(y_true, y_pred, positive_label=positive_label)
        out = {"metric": m, **cm, "count": int(len(merged))}
    elif m == "roc_auc":
        try:
            val = roc_auc_binary(y_true, y_pred, positive_label=positive_label)
        except Exception:
            try:
                scores = [float(v) for v in y_pred]
            except Exception:
                raise typer.Exit(code=2)
            val = roc_auc_binary(y_true, scores, positive_label=positive_label)
        out = {"metric": m, "value": float(val), "count": int(len(merged))}
    elif m == "rouge1_f1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        val = rouge1_f1(refs, cands) if avg == "micro" else rouge1_f1_macro(refs, cands)
        out = {
            "metric": m,
            "value": float(val),
            "count": int(len(merged)),
            "average": avg,
        }
    elif m == "bleu1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        val = bleu1(refs, cands) if avg == "micro" else bleu1_macro(refs, cands)
        out = {
            "metric": m,
            "value": float(val),
            "count": int(len(merged)),
            "average": avg,
        }
    elif m == "bertscore_f1":
        refs = [str(v) for v in y_true]
        cands = [str(v) for v in y_pred]
        avg = (average or "micro").strip().lower()
        model = os.getenv("DSPX_BERTSCORE_MODEL")
        lang = os.getenv("DSPX_BERTSCORE_LANG", "en")
        rescale = os.getenv("DSPX_BERTSCORE_RESCALE", "").lower() in {
            "1",
            "true",
            "yes",
        }
        try:
            val = (
                bertscore_f1(
                    refs, cands, model=model, lang=lang, rescale_with_baseline=rescale
                )
                if avg == "micro"
                else bertscore_f1_macro(
                    refs, cands, model=model, lang=lang, rescale_with_baseline=rescale
                )
            )
        except ImportError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=2)
        out = {
            "metric": m,
            "value": float(val),
            "count": int(len(merged)),
            "average": avg,
        }
    elif m == "per_class_pr":
        per = precision_recall_per_class(y_true, y_pred)
        out = {"metric": m, "classes": per, "count": int(len(merged))}
        _export_pr_csv(outdir, per)
    elif m == "pr_curve":
        try:
            scores = [float(v) for v in y_pred]
        except Exception:
            raise typer.Exit(code=2)
        curve = pr_curve_binary(y_true, scores, positive_label=positive_label)
        _export_curve_csv(
            outdir,
            "pr_curve",
            ["threshold", "precision", "recall"],
            zip(curve["thresholds"], curve["precision"], curve["recall"]),
        )
        out = {"metric": m, **curve, "count": int(len(merged))}
    elif m == "roc_curve":
        try:
            scores = [float(v) for v in y_pred]
        except Exception:
            raise typer.Exit(code=2)
        curve = roc_curve_binary(y_true, scores, positive_label=positive_label)
        _export_curve_csv(
            outdir,
            "roc_curve",
            ["threshold", "tpr", "fpr"],
            zip(curve["thresholds"], curve["tpr"], curve["fpr"]),
        )
        out = {"metric": m, **curve, "count": int(len(merged))}
    else:
        raise typer.Exit(code=2)

    if json_out:
        typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if "value" in out:
            typer.echo(f"{m}: {out['value']:.6f} (n={out['count']})")
        else:
            typer.echo(
                f"tp={out['tp']} tn={out['tn']} fp={out['fp']} fn={out['fn']} (n={out['count']})"
            )


def _export_pr_csv(outdir: Optional[Path], per: dict[str, Any]) -> None:
    """Export per-class precision/recall to CSV."""
    if not outdir:
        return
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        with open(outdir / "per_class_pr.csv", "w", encoding="utf-8", newline="") as f:
            w = csv_module.writer(f)
            w.writerow(["class", "precision", "recall", "support"])
            for k, v in per.items():
                w.writerow(
                    [
                        k,
                        v.get("precision", 0.0),
                        v.get("recall", 0.0),
                        v.get("support", 0.0),
                    ]
                )
    except Exception:
        pass


def _export_curve_csv(
    outdir: Optional[Path],
    name: str,
    headers: list[str],
    rows: Any,
) -> None:
    """Export curve data to CSV."""
    if not outdir:
        return
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        with open(outdir / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv_module.writer(f)
            w.writerow(headers)
            for row in rows:
                w.writerow(row)
    except Exception:
        pass
