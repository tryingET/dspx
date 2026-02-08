from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

from dspx.run_receipts import load_run_receipt
from dspx.services.run_replay_service import check_run_receipt


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_bool_dict(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): bool(v) for k, v in value.items()}


def _artifact_run_dir(artifact_path: Path) -> Path | None:
    for parent in artifact_path.parents:
        if parent.name == "artifacts":
            return parent.parent
    return None


def _load_mlflow_run_meta(run_dir: Path) -> dict[str, Any]:
    meta_path = run_dir / "meta.yaml"
    if not meta_path.exists() or not meta_path.is_file():
        return {}
    try:
        import yaml

        loaded = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(loaded, Mapping):
        return {}

    out: dict[str, Any] = {}
    for key in (
        "run_id",
        "run_name",
        "status",
        "lifecycle_stage",
        "start_time",
        "end_time",
        "artifact_uri",
    ):
        if key in loaded:
            out[key] = loaded.get(key)
    return out


def _resolve_tracking_root(tracking_uri: str | None) -> tuple[Path | None, str, str]:
    """Resolve tracking root.

    Returns (path_or_none, mode, tracking_uri_display).
    mode:
      - local-sqlite-default
      - local-sqlite
      - local-file-store
      - remote-uri

    Note: for sqlite tracking, MLflow default artifact location is cwd-local
    `./mlruns` unless users configured a custom artifact root.
    """
    if not tracking_uri:
        root = (Path.cwd() / "mlruns").resolve()
        return root, "local-sqlite-default", "sqlite:///mlflow.db"

    uri = str(tracking_uri).strip()
    low = uri.lower()

    if low.startswith("sqlite:"):
        root = (Path.cwd() / "mlruns").resolve()
        return root, "local-sqlite", uri

    if "://" in uri and not uri.startswith("file:"):
        return None, "remote-uri", uri

    if uri.startswith("file:"):
        raw = uri[len("file:") :]
        root = Path(raw or "./mlruns").expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        return root, "local-file-store", uri

    root = Path(uri).expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    return root, "local-file-store", str(root)


def _local_path_from_uri(uri: str | None) -> Path | None:
    raw = str(uri or "").strip()
    if not raw:
        return None

    parsed = urlparse(raw)
    if parsed.scheme and parsed.scheme != "file":
        return None

    if parsed.scheme == "file":
        if parsed.netloc and parsed.netloc not in {"", "localhost"}:
            return None
        path_str = unquote(parsed.path or "")
        if not path_str:
            return None
        path = Path(path_str)
    else:
        path = Path(raw).expanduser()

    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _artifact_roots_from_mlflow_experiments(tracking_uri: str) -> list[Path]:
    try:
        from mlflow.entities import ViewType
        from mlflow.tracking import MlflowClient
    except Exception:
        return []

    try:
        client = MlflowClient(tracking_uri=tracking_uri)
        experiments = client.search_experiments(
            view_type=ViewType.ACTIVE_ONLY,
            max_results=5000,
        )
    except Exception:
        return []

    preferred_name = os.getenv("MLFLOW_EXPERIMENT", "DSPy")
    preferred: list[Path] = []
    other: list[Path] = []
    for exp in experiments:
        loc = getattr(exp, "artifact_location", None)
        path = _local_path_from_uri(str(loc) if loc is not None else None)
        if path is None:
            continue
        if str(getattr(exp, "name", "")) == preferred_name:
            preferred.append(path)
        else:
            other.append(path)
    return [*preferred, *other]


def _candidate_tracking_roots(
    *,
    tracking_root: Path | None,
    tracking_uri: str,
) -> list[Path]:
    roots = _artifact_roots_from_mlflow_experiments(tracking_uri)
    if not roots and tracking_root is not None:
        roots.append(tracking_root)

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except Exception:
            key = str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def _run_meta_from_client(run_id: str, *, tracking_uri: str) -> dict[str, Any]:
    try:
        from mlflow.tracking import MlflowClient
    except Exception:
        return {}

    try:
        client = MlflowClient(tracking_uri=tracking_uri)
        run = client.get_run(run_id)
    except Exception:
        return {}

    info = run.info
    tags = getattr(run.data, "tags", {}) if hasattr(run, "data") else {}
    run_name = getattr(info, "run_name", None) or (
        str(tags.get("mlflow.runName")) if isinstance(tags, Mapping) else None
    )

    out: dict[str, Any] = {
        "run_id": getattr(info, "run_id", run_id),
        "experiment_id": str(getattr(info, "experiment_id", "") or ""),
        "status": getattr(info, "status", None),
        "lifecycle_stage": getattr(info, "lifecycle_stage", None),
        "start_time": getattr(info, "start_time", None),
        "end_time": getattr(info, "end_time", None),
        "artifact_uri": getattr(info, "artifact_uri", None),
    }
    if run_name:
        out["run_name"] = run_name
    return out


def _find_linked_local_runs(
    *,
    tracking_roots: list[Path],
    artifact_names: set[str],
    tracking_uri: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for tracking_root in tracking_roots:
        if not tracking_root.exists() or not tracking_root.is_dir():
            continue
        for artifact_name in sorted(artifact_names):
            if not artifact_name:
                continue
            for candidate in tracking_root.rglob(artifact_name):
                run_dir = _artifact_run_dir(candidate)
                if run_dir is None:
                    continue

                run_id = run_dir.name
                rec = found.setdefault(
                    run_id,
                    {
                        "run_id": run_id,
                        "experiment_id": run_dir.parent.name,
                        "matched_artifacts": [],
                        "_run_dir": run_dir,
                    },
                )
                try:
                    rel = str(candidate.relative_to(run_dir / "artifacts"))
                except Exception:
                    rel = candidate.name

                matched = rec.get("matched_artifacts")
                if isinstance(matched, list) and rel not in matched:
                    matched.append(rel)

                if len(found) >= limit:
                    break
            if len(found) >= limit:
                break
        if len(found) >= limit:
            break

    out = list(found.values())
    for rec in out:
        run_id = str(rec.get("run_id") or "")
        run_dir = rec.pop("_run_dir", None)
        if isinstance(run_dir, Path):
            rec.update(_load_mlflow_run_meta(run_dir))

        if run_id and (
            not rec.get("artifact_uri")
            or not rec.get("status")
            or not rec.get("start_time")
        ):
            rec.update(_run_meta_from_client(run_id, tracking_uri=tracking_uri))

    return out


def _mlflow_context(
    *, meta_path: Path, receipt: Mapping[str, Any], with_mlflow: bool
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "requested": bool(with_mlflow),
        "mode": "disabled",
        "tracking_uri": os.getenv("MLFLOW_TRACKING_URI") or "",
        "linked_runs": [],
        "warnings": [],
    }
    if not with_mlflow:
        out["note"] = "mlflow enrichment not requested"
        return out

    tracking_root, mode, tracking_display = _resolve_tracking_root(
        os.getenv("MLFLOW_TRACKING_URI")
    )
    out["mode"] = mode
    out["tracking_uri"] = tracking_display

    if tracking_root is None:
        out["note"] = "remote tracking URI; local linkage scan skipped"
        out["warnings"] = [
            "remote MLflow enrichment is not implemented; baseline explain remains local"
        ]
        return out

    candidate_roots = _candidate_tracking_roots(
        tracking_root=tracking_root,
        tracking_uri=tracking_display,
    )
    out["scan_roots"] = [str(p) for p in candidate_roots]

    local_roots = [p for p in candidate_roots if p.exists() and p.is_dir()]
    if not local_roots:
        if candidate_roots:
            out["note"] = "local MLflow artifact roots missing: " + ", ".join(
                str(p) for p in candidate_roots
            )
        else:
            out["note"] = "no local MLflow artifact roots resolved"
        return out

    output_name = Path(str(receipt.get("output_path") or "")).name
    artifact_names = {meta_path.name, output_name, "manifest.json"}
    linked_runs = _find_linked_local_runs(
        tracking_roots=local_roots,
        artifact_names=artifact_names,
        tracking_uri=tracking_display,
    )
    out["linked_runs"] = linked_runs

    if linked_runs:
        out["note"] = "best-effort local MLflow artifact linkage"
    else:
        out["note"] = "no linked local MLflow runs found"
    return out


def explain_run_receipt(
    meta_path: Path, *, with_mlflow: bool = False
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "ok",
        "receipt_path": str(meta_path),
        "replay_status": "ok",
        "local_facts": {},
        "replay_checks": {},
        "replay_inputs": {},
        "run_summary": {},
        "mlflow_context": {},
        "warnings": [],
        "errors": [],
        "replay_error_codes": [],
        "replay_error_details": [],
    }

    receipt = load_run_receipt(meta_path)
    if receipt is None:
        report["status"] = "invalid"
        report["replay_status"] = "invalid"
        report["errors"] = ["receipt not found or invalid JSON object"]
        report["replay_error_codes"] = ["receipt_invalid_json_object"]
        report["replay_error_details"] = [
            {
                "code": "receipt_invalid_json_object",
                "message": "receipt not found or invalid JSON object",
            }
        ]
        report["mlflow_context"] = _mlflow_context(
            meta_path=meta_path,
            receipt={},
            with_mlflow=with_mlflow,
        )
        return report

    replay_report = check_run_receipt(meta_path)
    replay_status = str(replay_report.get("status") or "invalid")
    report["replay_status"] = replay_status
    replay_checks = _as_bool_dict(replay_report.get("checks"))
    failed_checks = [k for k, v in replay_checks.items() if not v]

    local_facts = {
        "created_at": receipt.get("created_at"),
        "run_kind": receipt.get("run_kind"),
        "provider": receipt.get("provider"),
        "template_version": receipt.get("template_version"),
        "output_path": replay_report.get("output_path") or receipt.get("output_path"),
        "output_hash": receipt.get("hash"),
        "cache_key": receipt.get("cache_key"),
        "cache_file": replay_report.get("cache_file") or receipt.get("cache_file"),
        "cache_enabled": receipt.get("cache_enabled"),
        "failed_replay_checks": failed_checks,
    }
    report["local_facts"] = local_facts
    report["replay_checks"] = replay_checks
    report["replay_inputs"] = _as_dict(receipt.get("replay_inputs"))
    report["run_summary"] = _as_dict(receipt.get("run_summary"))

    report["mlflow_context"] = _mlflow_context(
        meta_path=meta_path,
        receipt=receipt,
        with_mlflow=with_mlflow,
    )

    replay_errors = replay_report.get("errors")
    replay_warnings = replay_report.get("warnings")
    replay_error_codes = replay_report.get("error_codes")
    replay_error_details = replay_report.get("error_details")
    if isinstance(replay_errors, list):
        report["errors"] = [str(v) for v in replay_errors]
    if isinstance(replay_warnings, list):
        report["warnings"] = [str(v) for v in replay_warnings]
    if isinstance(replay_error_codes, list):
        report["replay_error_codes"] = [str(v) for v in replay_error_codes]
    if isinstance(replay_error_details, list):
        details: list[dict[str, str]] = []
        for item in replay_error_details:
            if not isinstance(item, Mapping):
                details.append({"code": "", "message": str(item)})
                continue
            detail: dict[str, str] = {
                "code": str(item.get("code") or ""),
                "message": str(item.get("message") or ""),
            }
            check = item.get("check")
            if check not in {None, ""}:
                detail["check"] = str(check)
            details.append(detail)
        report["replay_error_details"] = details

    if replay_status == "invalid":
        report["status"] = "invalid"
    elif replay_status == "failed":
        report["status"] = "degraded"
        report["warnings"] = list(report.get("warnings") or []) + [
            "replay verification drift detected; explanation is best-effort"
        ]
    else:
        report["status"] = "ok"

    return report
