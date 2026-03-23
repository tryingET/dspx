from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dspx.cache import cache_dir


_FALSEY = {"", "0", "false", "False", "no", "No"}


def _truthy(value: str | None, *, default: bool = True) -> bool:
    if value is None:
        return default
    return value not in _FALSEY


def module_quality_logging_enabled() -> bool:
    return _truthy(os.getenv("DSPX_MODULE_SYNTHESIS_QUALITY_ENABLE", "1"), default=True)


def module_quality_log_path() -> Path:
    raw = os.getenv("DSPX_MODULE_SYNTHESIS_QUALITY_LOG")
    if raw:
        return Path(raw).expanduser().resolve()
    return cache_dir() / "module" / "quality_runs.jsonl"


def append_module_quality_event(event: dict[str, Any]) -> Path | None:
    if not module_quality_logging_enabled():
        return None

    path = module_quality_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = dict(event)
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_module_quality_events(path: Path | None = None) -> list[dict[str, Any]]:
    p = (path or module_quality_log_path()).expanduser().resolve()
    if not p.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            raw = json.loads(text)
        except Exception:
            continue
        if isinstance(raw, dict):
            events.append(raw)
    return events


def _to_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value not in _FALSEY
    if value is None:
        return default
    return bool(value)


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    runs_total = len(rows)
    candidate_counts: list[int] = []
    selected_rank_dist: dict[str, int] = {}

    validation_pass_count = 0
    validation_total = 0
    smoke_pass_count = 0
    smoke_total = 0
    selection_integrity_count = 0
    receipt_coverage_count = 0
    promotion_receipt_count = 0
    promotion_total = 0
    signature_runs = 0

    for row in rows:
        candidate_count = max(0, _to_int(row.get("candidate_count"), default=0))
        candidate_counts.append(candidate_count)

        selected_rank = max(0, _to_int(row.get("selected_candidate_rank"), default=0))
        if selected_rank > 0:
            key = str(selected_rank)
            selected_rank_dist[key] = selected_rank_dist.get(key, 0) + 1

        if _to_bool(row.get("use_signature"), default=False):
            signature_runs += 1

        v_total = max(0, _to_int(row.get("validation_total"), default=0))
        v_pass = max(
            0,
            min(
                _to_int(row.get("validation_pass_count"), default=0),
                v_total,
            ),
        )
        validation_pass_count += v_pass
        validation_total += v_total

        s_total = max(0, _to_int(row.get("smoke_total"), default=0))
        s_pass = max(
            0,
            min(
                _to_int(row.get("smoke_pass_count"), default=0),
                s_total,
            ),
        )
        smoke_pass_count += s_pass
        smoke_total += s_total

        if _to_bool(row.get("selection_integrity"), default=False):
            selection_integrity_count += 1
        if _to_bool(row.get("receipt_coverage"), default=False):
            receipt_coverage_count += 1

        if _to_bool(row.get("promotion_requested"), default=False):
            promotion_total += 1
            if _to_bool(row.get("promotion_receipt_coverage"), default=False):
                promotion_receipt_count += 1

    candidate_count_avg = (
        float(sum(candidate_counts)) / float(runs_total) if runs_total > 0 else 0.0
    )

    return {
        "runs_total": runs_total,
        "signature_runs": signature_runs,
        "candidate_count_avg": candidate_count_avg,
        "candidate_count_min": min(candidate_counts) if candidate_counts else 0,
        "candidate_count_max": max(candidate_counts) if candidate_counts else 0,
        "selected_rank_distribution": {
            key: selected_rank_dist[key]
            for key in sorted(selected_rank_dist, key=lambda item: int(item))
        },
        "validation_pass_count": validation_pass_count,
        "validation_total": validation_total,
        "validation_pass_rate": (
            float(validation_pass_count) / float(validation_total)
            if validation_total > 0
            else 0.0
        ),
        "smoke_pass_count": smoke_pass_count,
        "smoke_total": smoke_total,
        "smoke_pass_rate": (
            float(smoke_pass_count) / float(smoke_total) if smoke_total > 0 else 0.0
        ),
        "selection_integrity_count": selection_integrity_count,
        "selection_integrity_rate": (
            float(selection_integrity_count) / float(runs_total)
            if runs_total > 0
            else 0.0
        ),
        "receipt_coverage_count": receipt_coverage_count,
        "receipt_coverage_rate": (
            float(receipt_coverage_count) / float(runs_total) if runs_total > 0 else 0.0
        ),
        "promotion_total": promotion_total,
        "promotion_receipt_count": promotion_receipt_count,
        "promotion_receipt_coverage_rate": (
            float(promotion_receipt_count) / float(promotion_total)
            if promotion_total > 0
            else 1.0
        ),
    }


def summarize_module_quality_events(
    events: list[dict[str, Any]],
    *,
    run_kind: str | None = None,
) -> dict[str, Any]:
    rows = [event for event in events if isinstance(event, dict)]
    if run_kind:
        rows = [event for event in rows if str(event.get("run_kind") or "") == run_kind]

    summary = _summarize_rows(rows)
    summary["run_kind_filter"] = run_kind
    return summary


@dataclass(frozen=True)
class ModuleSynthesisQualityGate:
    min_validation_pass_rate: float = 1.0
    min_smoke_pass_rate: float = 1.0
    min_selection_integrity_rate: float = 1.0
    min_receipt_coverage_rate: float = 1.0
    min_promotion_receipt_coverage_rate: float = 1.0


def evaluate_module_quality_gates(
    summary: dict[str, Any],
    *,
    gate: ModuleSynthesisQualityGate | None = None,
) -> dict[str, Any]:
    resolved = gate or ModuleSynthesisQualityGate()

    validation_pass_rate = _to_float(summary.get("validation_pass_rate"), default=0.0)
    smoke_pass_rate = _to_float(summary.get("smoke_pass_rate"), default=0.0)
    selection_integrity_rate = _to_float(
        summary.get("selection_integrity_rate"), default=0.0
    )
    receipt_coverage_rate = _to_float(summary.get("receipt_coverage_rate"), default=0.0)
    promotion_receipt_coverage_rate = _to_float(
        summary.get("promotion_receipt_coverage_rate"), default=1.0
    )

    checks = {
        "validation_pass_rate": {
            "value": validation_pass_rate,
            "min": float(resolved.min_validation_pass_rate),
            "pass": validation_pass_rate >= float(resolved.min_validation_pass_rate),
        },
        "smoke_pass_rate": {
            "value": smoke_pass_rate,
            "min": float(resolved.min_smoke_pass_rate),
            "pass": smoke_pass_rate >= float(resolved.min_smoke_pass_rate),
        },
        "selection_integrity_rate": {
            "value": selection_integrity_rate,
            "min": float(resolved.min_selection_integrity_rate),
            "pass": selection_integrity_rate
            >= float(resolved.min_selection_integrity_rate),
        },
        "receipt_coverage_rate": {
            "value": receipt_coverage_rate,
            "min": float(resolved.min_receipt_coverage_rate),
            "pass": receipt_coverage_rate >= float(resolved.min_receipt_coverage_rate),
        },
        "promotion_receipt_coverage_rate": {
            "value": promotion_receipt_coverage_rate,
            "min": float(resolved.min_promotion_receipt_coverage_rate),
            "pass": promotion_receipt_coverage_rate
            >= float(resolved.min_promotion_receipt_coverage_rate),
        },
    }

    return {
        "runs_total": _to_int(summary.get("runs_total"), default=0),
        "overall_pass": all(bool(value.get("pass")) for value in checks.values()),
        "checks": checks,
        "thresholds": asdict(resolved),
    }


def format_module_quality_summary(
    summary: dict[str, Any],
    gate_eval: dict[str, Any] | None = None,
) -> str:
    selected_rank_dist = summary.get("selected_rank_distribution")
    if isinstance(selected_rank_dist, dict) and selected_rank_dist:
        rank_text = ", ".join(
            f"{key}:{_to_int(value)}"
            for key, value in sorted(
                selected_rank_dist.items(), key=lambda item: int(item[0])
            )
        )
    else:
        rank_text = "-"

    lines = ["module synthesis quality summary"]
    run_kind_filter = summary.get("run_kind_filter")
    if run_kind_filter:
        lines.append(f"run_kind_filter={run_kind_filter}")

    lines.extend(
        [
            f"runs_total={_to_int(summary.get('runs_total'), default=0)}",
            f"signature_runs={_to_int(summary.get('signature_runs'), default=0)}",
            f"candidate_count_avg={_to_float(summary.get('candidate_count_avg')):.2f}",
            f"candidate_count_min={_to_int(summary.get('candidate_count_min'), default=0)}",
            f"candidate_count_max={_to_int(summary.get('candidate_count_max'), default=0)}",
            f"selected_rank_distribution={rank_text}",
            f"validation_pass_rate={_to_float(summary.get('validation_pass_rate')):.4f}",
            f"smoke_pass_rate={_to_float(summary.get('smoke_pass_rate')):.4f}",
            f"selection_integrity_rate={_to_float(summary.get('selection_integrity_rate')):.4f}",
            f"receipt_coverage_rate={_to_float(summary.get('receipt_coverage_rate')):.4f}",
            "promotion_receipt_coverage_rate="
            f"{_to_float(summary.get('promotion_receipt_coverage_rate'), default=1.0):.4f}",
        ]
    )

    if gate_eval:
        lines.append(
            f"gates={'PASS' if bool(gate_eval.get('overall_pass')) else 'FAIL'}"
        )
        checks = gate_eval.get("checks")
        if isinstance(checks, dict):
            for key in (
                "validation_pass_rate",
                "smoke_pass_rate",
                "selection_integrity_rate",
                "receipt_coverage_rate",
                "promotion_receipt_coverage_rate",
            ):
                entry = checks.get(key)
                if not isinstance(entry, dict):
                    continue
                lines.append(
                    f"- {key}: {'pass' if bool(entry.get('pass')) else 'fail'} "
                    f"(value={_to_float(entry.get('value')):.4f}, "
                    f"min={_to_float(entry.get('min')):.4f})"
                )

    return "\n".join(lines)
