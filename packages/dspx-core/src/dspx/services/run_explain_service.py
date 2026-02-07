from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

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
      - local-file-store
      - remote-uri
    """
    if not tracking_uri:
        root = (Path.cwd() / "mlruns").resolve()
        return root, "local-file-store", str(root)

    uri = str(tracking_uri).strip()
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


def _find_linked_local_runs(
    *,
    tracking_root: Path,
    artifact_names: set[str],
    limit: int = 20,
) -> list[dict[str, Any]]:
    if not tracking_root.exists() or not tracking_root.is_dir():
        return []

    found: dict[str, dict[str, Any]] = {}
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

    out = list(found.values())
    for rec in out:
        run_id = str(rec.get("run_id") or "")
        if not run_id:
            continue
        exp_id = str(rec.get("experiment_id") or "")
        run_dir = tracking_root / exp_id / run_id
        rec.update(_load_mlflow_run_meta(run_dir))

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

    if not tracking_root.exists() or not tracking_root.is_dir():
        out["note"] = f"local MLflow tracking directory missing: {tracking_root}"
        return out

    output_name = Path(str(receipt.get("output_path") or "")).name
    artifact_names = {meta_path.name, output_name, "manifest.json"}
    linked_runs = _find_linked_local_runs(
        tracking_root=tracking_root,
        artifact_names=artifact_names,
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
