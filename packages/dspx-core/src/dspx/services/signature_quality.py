# summary: "Records, summarizes, gates, and formats signature-generation quality events."
# read_when:
#   - "Changing signature quality logging, aggregation metrics, thresholds, or summary output."

from __future__ import annotations

import json
import math
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


def quality_logging_enabled() -> bool:
    return _truthy(os.getenv("DSPX_SIGNATURE_QUALITY_ENABLE", "1"), default=True)


def quality_log_path() -> Path:
    raw = os.getenv("DSPX_SIGNATURE_QUALITY_LOG")
    if raw:
        return Path(raw).expanduser().resolve()
    return cache_dir() / "signature" / "quality_runs.jsonl"


def append_quality_event(event: dict[str, Any]) -> Path | None:
    if not quality_logging_enabled():
        return None

    path = quality_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = dict(event)
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_quality_events(path: Path | None = None) -> list[dict[str, Any]]:
    p = (path or quality_log_path()).expanduser().resolve()
    if not p.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t:
            continue
        try:
            raw = json.loads(t)
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


def _nearest_rank_percentile(values: list[int], percentile: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    rank = max(1, int(math.ceil((percentile / 100.0) * len(v))))
    return float(v[min(len(v), rank) - 1])


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    runs_total = len(rows)
    attempts: list[int] = []
    attempts_dist: dict[str, int] = {}

    fallback_count = 0
    validation_pass_count = 0
    validation_total = 0
    smoke_pass_count = 0
    smoke_total = 0

    providers: set[str] = set()

    for row in rows:
        provider = str(row.get("provider") or "unknown")
        providers.add(provider)

        attempts_used = max(0, _to_int(row.get("attempts_used"), default=0))
        attempts.append(attempts_used)
        key = str(attempts_used)
        attempts_dist[key] = attempts_dist.get(key, 0) + 1

        fallback_used = _to_bool(
            row.get("fallback_used"),
            default=str(row.get("candidate_source") or "") == "fallback",
        )
        if fallback_used:
            fallback_count += 1

        v_total = max(
            0,
            _to_int(
                row.get("validation_total"),
                default=attempts_used,
            ),
        )
        v_pass = _to_int(row.get("validation_pass_count"), default=-1)
        if v_pass < 0:
            v_rate = _to_float(row.get("validation_pass_rate"), default=0.0)
            v_pass = int(round(v_rate * float(v_total))) if v_total > 0 else 0
        v_pass = max(0, min(v_pass, v_total))

        s_total = max(
            0,
            _to_int(
                row.get("smoke_total"),
                default=attempts_used,
            ),
        )
        s_pass = _to_int(row.get("smoke_pass_count"), default=-1)
        if s_pass < 0:
            s_rate = _to_float(row.get("smoke_pass_rate"), default=0.0)
            s_pass = int(round(s_rate * float(s_total))) if s_total > 0 else 0
        s_pass = max(0, min(s_pass, s_total))

        validation_pass_count += v_pass
        validation_total += v_total
        smoke_pass_count += s_pass
        smoke_total += s_total

    attempts_avg = float(sum(attempts)) / float(runs_total) if runs_total > 0 else 0.0

    return {
        "runs_total": runs_total,
        "providers": sorted(providers),
        "fallback_count": fallback_count,
        "fallback_rate": (
            float(fallback_count) / float(runs_total) if runs_total > 0 else 0.0
        ),
        "attempts_used_distribution": {
            k: attempts_dist[k] for k in sorted(attempts_dist, key=lambda x: int(x))
        },
        "attempts_avg": attempts_avg,
        "attempts_p95": _nearest_rank_percentile(attempts, 95.0),
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
    }


def summarize_quality_events(
    events: list[dict[str, Any]],
    *,
    provider: str | None = None,
    run_kind: str | None = None,
) -> dict[str, Any]:
    rows = [e for e in events if isinstance(e, dict)]

    if provider:
        rows = [e for e in rows if str(e.get("provider") or "") == provider]
    if run_kind:
        rows = [e for e in rows if str(e.get("run_kind") or "") == run_kind]

    summary = _summarize_rows(rows)
    summary["provider_filter"] = provider
    summary["run_kind_filter"] = run_kind

    if provider is None:
        by_provider: dict[str, dict[str, Any]] = {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            name = str(row.get("provider") or "unknown")
            grouped.setdefault(name, []).append(row)
        for name in sorted(grouped):
            by_provider[name] = _summarize_rows(grouped[name])
        summary["by_provider"] = by_provider

    return summary


@dataclass(frozen=True)
class SignatureQualityGate:
    max_fallback_rate: float = 0.25
    max_attempts_p95: float = 3.0
    min_validation_pass_rate: float = 0.90
    min_smoke_pass_rate: float = 0.90


def evaluate_quality_gates(
    summary: dict[str, Any],
    *,
    gate: SignatureQualityGate | None = None,
) -> dict[str, Any]:
    g = gate or SignatureQualityGate()

    fallback_rate = _to_float(summary.get("fallback_rate"), default=0.0)
    attempts_p95 = _to_float(summary.get("attempts_p95"), default=0.0)
    validation_pass_rate = _to_float(summary.get("validation_pass_rate"), default=0.0)
    smoke_pass_rate = _to_float(summary.get("smoke_pass_rate"), default=0.0)

    checks = {
        "fallback_rate": {
            "value": fallback_rate,
            "max": float(g.max_fallback_rate),
            "pass": fallback_rate <= float(g.max_fallback_rate),
        },
        "attempts_p95": {
            "value": attempts_p95,
            "max": float(g.max_attempts_p95),
            "pass": attempts_p95 <= float(g.max_attempts_p95),
        },
        "validation_pass_rate": {
            "value": validation_pass_rate,
            "min": float(g.min_validation_pass_rate),
            "pass": validation_pass_rate >= float(g.min_validation_pass_rate),
        },
        "smoke_pass_rate": {
            "value": smoke_pass_rate,
            "min": float(g.min_smoke_pass_rate),
            "pass": smoke_pass_rate >= float(g.min_smoke_pass_rate),
        },
    }

    return {
        "runs_total": _to_int(summary.get("runs_total"), default=0),
        "overall_pass": all(bool(v.get("pass")) for v in checks.values()),
        "checks": checks,
        "thresholds": asdict(g),
    }


def format_quality_summary(
    summary: dict[str, Any],
    gate_eval: dict[str, Any] | None = None,
) -> str:
    runs_total = _to_int(summary.get("runs_total"), default=0)
    provider_filter = summary.get("provider_filter")
    run_kind_filter = summary.get("run_kind_filter")

    dist = summary.get("attempts_used_distribution")
    if isinstance(dist, dict) and dist:
        normalized_dist = sorted(
            ((str(k), _to_int(v)) for k, v in dist.items()),
            key=lambda kv: int(kv[0]),
        )
        dist_text = ", ".join(f"{k}:{v}" for k, v in normalized_dist)
    else:
        dist_text = "-"

    lines = ["signature quality summary"]
    if provider_filter:
        lines.append(f"provider_filter={provider_filter}")
    if run_kind_filter:
        lines.append(f"run_kind_filter={run_kind_filter}")

    lines.extend(
        [
            f"runs_total={runs_total}",
            f"fallback_rate={_to_float(summary.get('fallback_rate')):.4f}",
            f"attempts_p95={_to_float(summary.get('attempts_p95')):.2f}",
            f"attempts_distribution={dist_text}",
            f"validation_pass_rate={_to_float(summary.get('validation_pass_rate')):.4f}",
            f"smoke_pass_rate={_to_float(summary.get('smoke_pass_rate')):.4f}",
        ]
    )

    if gate_eval:
        overall = bool(gate_eval.get("overall_pass"))
        lines.append(f"gates={'PASS' if overall else 'FAIL'}")
        checks = gate_eval.get("checks")
        if isinstance(checks, dict):
            for key in (
                "fallback_rate",
                "attempts_p95",
                "validation_pass_rate",
                "smoke_pass_rate",
            ):
                entry = checks.get(key)
                if not isinstance(entry, dict):
                    continue
                status = "pass" if bool(entry.get("pass")) else "fail"
                value = _to_float(entry.get("value"), default=0.0)
                if "max" in entry:
                    lines.append(
                        f"- {key}: {status} (value={value:.4f}, max={float(entry.get('max')):.4f})"
                    )
                else:
                    lines.append(
                        f"- {key}: {status} (value={value:.4f}, min={float(entry.get('min')):.4f})"
                    )

    return "\n".join(lines)
