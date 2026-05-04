from __future__ import annotations

from contextlib import contextmanager
import os
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

from dspx.run_receipts import load_run_receipt
from dspx.services.run_replay_service import check_run_receipt

_REASON_CODE_VERSION = "v1"
_REASON_PRECEDENCE: tuple[str, ...] = (
    "mlflow_disabled",
    "mlflow_remote_lookup_not_enabled",
    "mlflow_remote_auth_unavailable",
    "mlflow_remote_time_budget_exceeded",
    "mlflow_remote_search_failed",
    "mlflow_remote_candidate_cap_reached",
    "mlflow_remote_no_candidate",
    "mlflow_remote_multi_candidate",
    "mlflow_tag_contract_violation",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_bool_dict(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): bool(v) for k, v in value.items()}


def _ordered_unique_reason_codes(codes: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for code in codes:
        c = str(code or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        unique.append(c)

    rank = {code: idx for idx, code in enumerate(_REASON_PRECEDENCE)}
    fallback_rank = len(rank)
    return sorted(unique, key=lambda c: rank.get(c, fallback_rank))


def _service_from_run_kind(run_kind: str) -> str | None:
    return {
        "signature-gen": "signature",
        "signature-refine": "signature",
        "module-gen": "module",
        "program-gen": "program",
        "codegen": "codegen",
        "mermaid": "mermaid",
    }.get((run_kind or "").strip().lower())


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


_MLFLOW_CORRELATION_TAG_KEYS: tuple[str, ...] = (
    "dspx.run_kind",
    "dspx.template_version",
    "dspx.output_basename",
    "dspx.cache_key",
    "dspx.output_hash_prefix",
    "service",
    "template_version",
)


def _normalized_expected_mlflow_tags(receipt: Mapping[str, Any]) -> dict[str, str]:
    hints = _as_dict(receipt.get("mlflow_hints"))
    expected = _as_dict(hints.get("expected_tags"))
    output_basename = Path(str(receipt.get("output_path") or "")).name
    run_kind = str(
        expected.get("dspx.run_kind") or receipt.get("run_kind") or ""
    ).strip()
    template_version = str(
        expected.get("dspx.template_version")
        or expected.get("template_version")
        or receipt.get("template_version")
        or ""
    ).strip()
    service = str(
        expected.get("service") or _service_from_run_kind(run_kind) or ""
    ).strip()

    normalized: dict[str, str] = {}
    for key in _MLFLOW_CORRELATION_TAG_KEYS:
        raw = expected.get(key)
        if key == "dspx.run_kind" and raw in {None, ""}:
            raw = run_kind
        elif key == "dspx.template_version" and raw in {None, ""}:
            raw = template_version
        elif key == "template_version" and raw in {None, ""}:
            raw = template_version
        elif key == "service" and raw in {None, ""}:
            raw = service
        elif key == "dspx.output_basename" and raw in {None, ""}:
            raw = output_basename
        value = str(raw or "").strip()
        if value:
            normalized[key] = value
    return normalized


def _load_mlflow_run_tags(run_dir: Path) -> dict[str, str]:
    tags_dir = run_dir / "tags"
    if not tags_dir.exists() or not tags_dir.is_dir():
        return {}

    out: dict[str, str] = {}
    for path in tags_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            key = path.relative_to(tags_dir).as_posix()
            out[key] = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
    return out


def _expected_local_artifacts(
    *, meta_path: Path, receipt: Mapping[str, Any]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    required: list[str] = []
    optional: list[str] = []

    if meta_path.name:
        required.append(meta_path.name)

    output_name = Path(str(receipt.get("output_path") or "")).name
    if output_name and Path(output_name).suffix:
        if output_name not in required:
            required.append(output_name)
    elif output_name or str(receipt.get("run_kind") or "").strip().lower() == "mermaid":
        optional.append("manifest.json")

    return tuple(required), tuple(dict.fromkeys(optional))


def _relevant_mlflow_actual_tags(tags: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: str(tags.get(key) or "").strip()
        for key in _MLFLOW_CORRELATION_TAG_KEYS
        if str(tags.get(key) or "").strip()
    }


def _mlflow_candidate_tag_conflicts(
    tags: Mapping[str, Any],
    expected_tags: Mapping[str, str],
) -> bool:
    relevant_actual = _relevant_mlflow_actual_tags(tags)
    if not relevant_actual:
        return False

    for key, actual in relevant_actual.items():
        expected = expected_tags.get(key)
        if expected is None:
            continue
        if actual != str(expected).strip():
            return True
    return False


def _mlflow_candidate_tags_match(
    tags: Mapping[str, Any],
    expected_tags: Mapping[str, str],
    *,
    strict: bool,
) -> bool:
    relevant_actual = _relevant_mlflow_actual_tags(tags)
    if not relevant_actual:
        return not strict

    if strict:
        for key, expected in expected_tags.items():
            if key not in _MLFLOW_CORRELATION_TAG_KEYS:
                continue
            if relevant_actual.get(key) != str(expected).strip():
                return False
        return True

    return not _mlflow_candidate_tag_conflicts(tags, expected_tags)


def _artifacts_cover_required(
    *,
    required_artifacts: tuple[str, ...],
    matched_artifacts: set[str],
) -> bool:
    if not required_artifacts:
        return True

    matched_names = {Path(artifact).name for artifact in matched_artifacts}
    for artifact in required_artifacts:
        if artifact in matched_artifacts:
            continue
        if artifact in matched_names:
            continue
        return False
    return True


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


def _uses_deprecated_filesystem_tracking_backend(tracking_uri: str) -> bool:
    uri = str(tracking_uri or "").strip()
    if not uri:
        return False
    parsed = urlparse(uri)
    if parsed.scheme in {"", "file"}:
        return True
    return False


def _artifact_roots_from_mlflow_experiments(tracking_uri: str) -> list[Path]:
    if _uses_deprecated_filesystem_tracking_backend(tracking_uri):
        return []
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


def _run_tags_from_client(run_id: str, *, tracking_uri: str) -> dict[str, str]:
    try:
        from mlflow.tracking import MlflowClient
    except Exception:
        return {}

    try:
        client = MlflowClient(tracking_uri=tracking_uri)
        run = client.get_run(run_id)
    except Exception:
        return {}

    tags = getattr(run.data, "tags", {}) if hasattr(run, "data") else {}
    if not isinstance(tags, Mapping):
        return {}
    return {
        str(key): str(value).strip()
        for key, value in tags.items()
        if str(value).strip()
    }


def _find_linked_local_runs(
    *,
    tracking_roots: list[Path],
    required_artifacts: tuple[str, ...],
    optional_artifacts: tuple[str, ...],
    tracking_uri: str,
    expected_tags: Mapping[str, str],
    limit: int = 20,
) -> tuple[list[dict[str, Any]], bool]:
    found: dict[str, dict[str, Any]] = {}
    tag_contract_violation = False
    search_artifacts = tuple(dict.fromkeys([*required_artifacts, *optional_artifacts]))
    for tracking_root in tracking_roots:
        if not tracking_root.exists() or not tracking_root.is_dir():
            continue
        for artifact_name in search_artifacts:
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

    out: list[dict[str, Any]] = []
    for rec in found.values():
        run_id = str(rec.get("run_id") or "")
        run_dir = rec.pop("_run_dir", None)
        matched_artifacts = {
            str(item)
            for item in rec.get("matched_artifacts") or []
            if str(item).strip()
        }
        if not _artifacts_cover_required(
            required_artifacts=required_artifacts,
            matched_artifacts=matched_artifacts,
        ):
            continue

        tags: dict[str, str] = {}
        if isinstance(run_dir, Path):
            rec.update(_load_mlflow_run_meta(run_dir))
            tags = _load_mlflow_run_tags(run_dir)

        if run_id and (
            not rec.get("artifact_uri")
            or not rec.get("status")
            or not rec.get("start_time")
        ):
            rec.update(_run_meta_from_client(run_id, tracking_uri=tracking_uri))
        if run_id and expected_tags and not tags:
            tags = _run_tags_from_client(run_id, tracking_uri=tracking_uri)

        if expected_tags and _mlflow_candidate_tag_conflicts(tags, expected_tags):
            tag_contract_violation = True
        if expected_tags and not _mlflow_candidate_tags_match(
            tags,
            expected_tags,
            strict=False,
        ):
            continue

        matched_tags = [
            key
            for key, expected in expected_tags.items()
            if str(tags.get(key) or "").strip() == str(expected).strip()
        ]
        if matched_tags:
            rec["matched_tags"] = matched_tags
        out.append(rec)
        if len(out) >= limit:
            break

    return out, tag_contract_violation


def _truthy_env(name: str, default: str = "1") -> bool:
    raw = os.getenv(name, default)
    if raw is None:
        return True
    s = str(raw).strip().lower()
    return s not in {"", "0", "false", "no"}


def _quote_filter_value(value: str) -> str:
    return value.replace("'", "")


@contextmanager
def _temporary_env(overrides: Mapping[str, str]):
    original: dict[str, str | None] = {
        str(key): os.environ.get(str(key)) for key in overrides
    }
    try:
        for key, value in overrides.items():
            os.environ[str(key)] = str(value)
        yield
    finally:
        for key, prior in original.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


def _bounded_remote_http_env(*, time_budget_ms: int):
    budget = max(1, int(time_budget_ms))
    timeout_seconds = max(1, min(30, (budget + 999) // 1000))
    return _temporary_env(
        {
            "MLFLOW_HTTP_REQUEST_TIMEOUT": str(timeout_seconds),
            "MLFLOW_DEPLOYMENT_CLIENT_HTTP_REQUEST_TIMEOUT": str(timeout_seconds),
            "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "0",
            "MLFLOW_HTTP_REQUEST_BACKOFF_FACTOR": "1",
            "MLFLOW_HTTP_REQUEST_BACKOFF_JITTER": "0",
        }
    )


def _remote_search_candidates(
    *,
    receipt: Mapping[str, Any],
    tracking_uri: str,
    candidate_cap: int,
    time_budget_ms: int,
) -> tuple[list[dict[str, Any]], list[str], float]:
    reasons: list[str] = []
    started = time.perf_counter()

    try:
        from mlflow.entities import ViewType
        from mlflow.tracking import MlflowClient
    except Exception:
        elapsed = (time.perf_counter() - started) * 1000.0
        reasons.append("mlflow_remote_search_failed")
        return [], reasons, elapsed

    try:
        with _bounded_remote_http_env(time_budget_ms=time_budget_ms):
            client = MlflowClient(tracking_uri=tracking_uri)
            experiments = client.search_experiments(
                view_type=ViewType.ACTIVE_ONLY,
                max_results=5000,
            )
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000.0
        msg = str(exc).lower()
        if any(
            token in msg
            for token in ("401", "403", "unauthorized", "forbidden", "auth")
        ):
            reasons.append("mlflow_remote_auth_unavailable")
        else:
            reasons.append("mlflow_remote_search_failed")
        return [], reasons, elapsed

    if (time.perf_counter() - started) * 1000.0 > float(time_budget_ms):
        elapsed = (time.perf_counter() - started) * 1000.0
        reasons.append("mlflow_remote_time_budget_exceeded")
        return [], reasons, elapsed

    exp_ids: list[str] = []
    for exp in experiments:
        exp_id = str(getattr(exp, "experiment_id", "") or "")
        if exp_id:
            exp_ids.append(exp_id)

    if not exp_ids:
        elapsed = (time.perf_counter() - started) * 1000.0
        reasons.append("mlflow_remote_no_candidate")
        return [], reasons, elapsed

    expected_tags = _normalized_expected_mlflow_tags(receipt)

    run_kind = str(expected_tags.get("dspx.run_kind") or "").strip()
    template_version = str(expected_tags.get("dspx.template_version") or "").strip()
    output_basename = str(expected_tags.get("dspx.output_basename") or "").strip()
    service = str(expected_tags.get("service") or "").strip()

    filter_candidates: list[str] = []
    if run_kind and template_version and output_basename:
        filter_candidates.append(
            " and ".join(
                [
                    f"tags.dspx.run_kind = '{_quote_filter_value(run_kind)}'",
                    f"tags.dspx.template_version = '{_quote_filter_value(template_version)}'",
                    f"tags.dspx.output_basename = '{_quote_filter_value(output_basename)}'",
                ]
            )
        )
    if run_kind and template_version:
        filter_candidates.append(
            " and ".join(
                [
                    f"tags.dspx.run_kind = '{_quote_filter_value(run_kind)}'",
                    f"tags.dspx.template_version = '{_quote_filter_value(template_version)}'",
                ]
            )
        )
    if service and template_version and output_basename:
        filter_candidates.append(
            " and ".join(
                [
                    f"tags.service = '{_quote_filter_value(service)}'",
                    f"tags.template_version = '{_quote_filter_value(template_version)}'",
                    f"tags.dspx.output_basename = '{_quote_filter_value(output_basename)}'",
                ]
            )
        )
    if service and template_version:
        filter_candidates.append(
            " and ".join(
                [
                    f"tags.service = '{_quote_filter_value(service)}'",
                    f"tags.template_version = '{_quote_filter_value(template_version)}'",
                ]
            )
        )
    if service and output_basename:
        filter_candidates.append(
            " and ".join(
                [
                    f"tags.service = '{_quote_filter_value(service)}'",
                    f"tags.dspx.output_basename = '{_quote_filter_value(output_basename)}'",
                ]
            )
        )
    if service:
        filter_candidates.append(f"tags.service = '{_quote_filter_value(service)}'")
    filter_candidates.append("")

    seen_filters: set[str] = set()
    ordered_filters: list[str] = []
    for flt in filter_candidates:
        if flt in seen_filters:
            continue
        seen_filters.add(flt)
        ordered_filters.append(flt)

    runs: list[Any] = []
    for flt in ordered_filters:
        if (time.perf_counter() - started) * 1000.0 > float(time_budget_ms):
            reasons.append("mlflow_remote_time_budget_exceeded")
            break
        try:
            with _bounded_remote_http_env(time_budget_ms=time_budget_ms):
                runs = list(
                    client.search_runs(
                        experiment_ids=exp_ids,
                        filter_string=flt,
                        max_results=int(candidate_cap),
                        order_by=["attributes.start_time DESC"],
                    )
                )
        except Exception as exc:
            msg = str(exc).lower()
            if any(
                token in msg
                for token in ("401", "403", "unauthorized", "forbidden", "auth")
            ):
                reasons.append("mlflow_remote_auth_unavailable")
            else:
                reasons.append("mlflow_remote_search_failed")
            runs = []
            break
        if runs:
            break

    elapsed = (time.perf_counter() - started) * 1000.0

    candidates: list[dict[str, Any]] = []
    tag_contract_violation = False
    for run in runs[: int(candidate_cap)]:
        info = getattr(run, "info", None)
        data = getattr(run, "data", None)
        tags = _as_dict(getattr(data, "tags", {}))
        if expected_tags and _mlflow_candidate_tag_conflicts(tags, expected_tags):
            tag_contract_violation = True
        if expected_tags and not _mlflow_candidate_tags_match(
            tags,
            expected_tags,
            strict=True,
        ):
            continue
        run_name = getattr(info, "run_name", None) or tags.get("mlflow.runName")
        candidate = {
            "run_id": str(getattr(info, "run_id", "") or ""),
            "experiment_id": str(getattr(info, "experiment_id", "") or ""),
            "status": getattr(info, "status", None),
            "lifecycle_stage": getattr(info, "lifecycle_stage", None),
            "start_time": getattr(info, "start_time", None),
            "end_time": getattr(info, "end_time", None),
            "artifact_uri": getattr(info, "artifact_uri", None),
            "run_name": run_name,
        }
        matched_tags = [
            key
            for key, expected in expected_tags.items()
            if str(tags.get(key) or "").strip() == str(expected).strip()
        ]
        if matched_tags:
            candidate["matched_tags"] = matched_tags
        candidates.append(candidate)

    if tag_contract_violation:
        reasons.append("mlflow_tag_contract_violation")
    if len(candidates) >= int(candidate_cap):
        reasons.append("mlflow_remote_candidate_cap_reached")
    if not candidates:
        reasons.append("mlflow_remote_no_candidate")
    elif len(candidates) > 1:
        reasons.append("mlflow_remote_multi_candidate")

    return candidates, reasons, elapsed


def _mlflow_context(
    *,
    meta_path: Path,
    receipt: Mapping[str, Any],
    with_mlflow: bool,
    mlflow_remote_lookup: bool,
) -> dict[str, Any]:
    reasons: list[str] = []
    out: dict[str, Any] = {
        "requested": bool(with_mlflow),
        "mode": "disabled",
        "lookup_mode": "disabled",
        "tracking_uri": os.getenv("MLFLOW_TRACKING_URI") or "",
        "linked_runs": [],
        "warnings": [],
        "lookup_steps": [],
        "degrade_reason_codes": [],
        "reason_code_version": _REASON_CODE_VERSION,
        "candidate_count": 0,
        "matched_count": 0,
        "remote_candidate_cap": 25,
        "remote_time_budget_ms": 3000,
        "remote_elapsed_ms": 0.0,
    }
    if not with_mlflow:
        out["note"] = "mlflow enrichment not requested"
        return out

    if not _truthy_env("MLFLOW_ENABLE", "1"):
        reasons.append("mlflow_disabled")

    tracking_root, mode, tracking_display = _resolve_tracking_root(
        os.getenv("MLFLOW_TRACKING_URI")
    )
    out["mode"] = mode
    out["tracking_uri"] = tracking_display

    if tracking_root is None:
        out["lookup_mode"] = "remote-search"
        out["lookup_steps"] = ["baseline-local-replay", "remote-tag-search"]

        if not mlflow_remote_lookup:
            out["note"] = "remote tracking URI detected; remote lookup disabled"
            out["warnings"] = [
                "remote MLflow lookup disabled (use --mlflow-remote-lookup for bounded search)",
            ]
            reasons.append("mlflow_remote_lookup_not_enabled")
        else:
            candidates, remote_reasons, elapsed_ms = _remote_search_candidates(
                receipt=receipt,
                tracking_uri=tracking_display,
                candidate_cap=int(out["remote_candidate_cap"]),
                time_budget_ms=int(out["remote_time_budget_ms"]),
            )
            out["linked_runs"] = candidates
            out["candidate_count"] = len(candidates)
            out["matched_count"] = 1 if len(candidates) == 1 else 0
            out["remote_elapsed_ms"] = float(elapsed_ms)
            reasons.extend(remote_reasons)
            if candidates:
                out["note"] = "bounded remote MLflow candidate search completed"
            else:
                out["note"] = (
                    "bounded remote MLflow candidate search found no definitive link"
                )

        out["degrade_reason_codes"] = _ordered_unique_reason_codes(reasons)
        return out

    out["lookup_mode"] = "local-scan"

    candidate_roots = _candidate_tracking_roots(
        tracking_root=tracking_root,
        tracking_uri=tracking_display,
    )
    out["scan_roots"] = [str(p) for p in candidate_roots]
    out["lookup_steps"] = [
        "baseline-local-replay",
        "local-artifact-root-resolution",
        "local-artifact-linkage-scan",
    ]

    local_roots = [p for p in candidate_roots if p.exists() and p.is_dir()]
    if not local_roots:
        if candidate_roots:
            out["note"] = "local MLflow artifact roots missing: " + ", ".join(
                str(p) for p in candidate_roots
            )
        else:
            out["note"] = "no local MLflow artifact roots resolved"
        out["degrade_reason_codes"] = _ordered_unique_reason_codes(reasons)
        return out

    expected_tags = _normalized_expected_mlflow_tags(receipt)
    required_artifacts, optional_artifacts = _expected_local_artifacts(
        meta_path=meta_path,
        receipt=receipt,
    )
    linked_runs, tag_contract_violation = _find_linked_local_runs(
        tracking_roots=local_roots,
        required_artifacts=required_artifacts,
        optional_artifacts=optional_artifacts,
        tracking_uri=tracking_display,
        expected_tags=expected_tags,
    )
    if tag_contract_violation:
        reasons.append("mlflow_tag_contract_violation")
    out["linked_runs"] = linked_runs
    out["candidate_count"] = len(linked_runs)
    out["matched_count"] = len(linked_runs)

    if linked_runs:
        out["note"] = "best-effort local MLflow artifact linkage"
    else:
        out["note"] = "no linked local MLflow runs found"

    out["degrade_reason_codes"] = _ordered_unique_reason_codes(reasons)
    return out


def explain_run_receipt(
    meta_path: Path,
    *,
    with_mlflow: bool = False,
    mlflow_remote_lookup: bool = False,
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
            mlflow_remote_lookup=mlflow_remote_lookup,
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
        mlflow_remote_lookup=mlflow_remote_lookup,
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
