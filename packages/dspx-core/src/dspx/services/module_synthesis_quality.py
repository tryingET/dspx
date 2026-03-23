from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dspx.cache import cache_dir


_FALSEY = {"", "0", "false", "False", "no", "No"}


@dataclass(frozen=True)
class ModuleReceiptInvariantResult:
    ok: bool
    issues: tuple[str, ...]
    ranked_candidate_ids: tuple[str, ...]
    selected_candidate_id: str | None
    selected_candidate_rank: int | None


@dataclass(frozen=True)
class ModuleRuntimeQualityEvent:
    payload: dict[str, Any]
    receipt_invariants: ModuleReceiptInvariantResult


@dataclass(frozen=True)
class ModuleSynthesisQualityGate:
    min_validation_pass_rate: float = 1.0
    min_smoke_pass_rate: float = 1.0
    min_selection_integrity_rate: float = 1.0
    min_receipt_coverage_rate: float = 1.0
    min_promotion_receipt_coverage_rate: float = 1.0


MODULE_SYNTHESIS_CORPUS_GATE = ModuleSynthesisQualityGate()


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


def _ranked_candidates(synthesis: dict[str, Any]) -> list[dict[str, Any]]:
    decision = synthesis.get("promotion_decision")
    if not isinstance(decision, dict):
        return []
    metadata = decision.get("metadata")
    if not isinstance(metadata, dict):
        return []
    ranked = metadata.get("ranked_candidates")
    if not isinstance(ranked, list):
        return []
    return [item for item in ranked if isinstance(item, dict)]


def evaluate_module_receipt_invariants(
    metadata: dict[str, Any],
    synthesis: dict[str, Any],
    *,
    output_hash: str | None = None,
) -> ModuleReceiptInvariantResult:
    issues: list[str] = []

    run_summary = metadata.get("run_summary")
    if not isinstance(run_summary, dict):
        issues.append("missing run_summary")
    elif run_summary.get("backend") != "synthesis_runtime":
        issues.append("run_summary backend != synthesis_runtime")

    request = synthesis.get("request")
    strategy = synthesis.get("strategy")
    selection_policy = synthesis.get("selection_policy")
    promotion_shell = synthesis.get("promotion_shell")
    promotion_decision = synthesis.get("promotion_decision")
    candidates = synthesis.get("candidates")
    workspaces = synthesis.get("candidate_workspaces")
    evaluations = synthesis.get("evaluations")

    if not isinstance(request, dict):
        issues.append("missing request")
    if not isinstance(strategy, dict):
        issues.append("missing strategy")
    if not isinstance(selection_policy, dict):
        issues.append("missing selection_policy")
    if not isinstance(promotion_shell, dict):
        issues.append("missing promotion_shell")
    if not isinstance(promotion_decision, dict):
        issues.append("missing promotion_decision")
    if not isinstance(candidates, list) or not candidates:
        issues.append("missing candidates")
    if not isinstance(workspaces, list) or not workspaces:
        issues.append("missing candidate_workspaces")
    if not isinstance(evaluations, list) or not evaluations:
        issues.append("missing evaluations")

    candidate_ids = [
        str(item.get("candidate_id"))
        for item in candidates or []
        if isinstance(item, dict) and item.get("candidate_id")
    ]
    workspace_ids = [
        str(item.get("candidate_id"))
        for item in workspaces or []
        if isinstance(item, dict) and item.get("candidate_id")
    ]
    evaluation_ids = [
        str(item.get("candidate_id"))
        for item in evaluations or []
        if isinstance(item, dict) and item.get("candidate_id")
    ]
    ranked_candidates = _ranked_candidates(synthesis)
    ranked_candidate_ids = tuple(
        str(item.get("candidate_id"))
        for item in ranked_candidates
        if item.get("candidate_id")
    )

    if not candidate_ids:
        issues.append("candidate ids missing")
    elif len(set(candidate_ids)) != len(candidate_ids):
        issues.append("candidate ids not unique")

    if sorted(workspace_ids) != sorted(candidate_ids):
        issues.append("workspace candidate ids do not match candidates")
    if sorted(evaluation_ids) != sorted(candidate_ids):
        issues.append("evaluation candidate ids do not match candidates")
    if ranked_candidate_ids and sorted(ranked_candidate_ids) != sorted(candidate_ids):
        issues.append("ranked candidate ids do not match candidates")

    metadata_ranked_ids = metadata.get("ranked_candidate_ids")
    if not isinstance(metadata_ranked_ids, list):
        issues.append("metadata missing ranked_candidate_ids")
    else:
        normalized_metadata_ranked = [str(item) for item in metadata_ranked_ids]
        if normalized_metadata_ranked != list(ranked_candidate_ids):
            issues.append("metadata ranked_candidate_ids drift from synthesis ranking")

    selected_candidate_id = metadata.get("selected_candidate_id")
    if selected_candidate_id is not None:
        selected_candidate_id = str(selected_candidate_id)
    decision_candidate_id = (
        str(promotion_decision.get("candidate_id"))
        if isinstance(promotion_decision, dict)
        and promotion_decision.get("candidate_id")
        else None
    )
    shell_candidate_id = (
        str(promotion_shell.get("selected_candidate_id"))
        if isinstance(promotion_shell, dict)
        and promotion_shell.get("selected_candidate_id")
        else None
    )

    if not selected_candidate_id:
        issues.append("metadata missing selected_candidate_id")
    elif selected_candidate_id not in candidate_ids:
        issues.append("selected_candidate_id not present in candidates")

    if decision_candidate_id != selected_candidate_id:
        issues.append("promotion_decision candidate_id drift")
    if shell_candidate_id != selected_candidate_id:
        issues.append("promotion_shell selected_candidate_id drift")

    selected_candidate_rank = _to_int(
        metadata.get("selected_candidate_rank"), default=0
    )
    if selected_candidate_rank <= 0:
        issues.append("metadata missing selected_candidate_rank")
        normalized_selected_rank: int | None = None
    else:
        normalized_selected_rank = selected_candidate_rank

    if ranked_candidate_ids:
        if (
            not selected_candidate_id
            or ranked_candidate_ids[0] != selected_candidate_id
        ):
            issues.append("selected candidate is not rank 1")
        elif normalized_selected_rank != 1:
            issues.append("selected_candidate_rank != 1")

        rank_from_payload = next(
            (
                _to_int(item.get("rank"), default=0)
                for item in ranked_candidates
                if item.get("candidate_id") == selected_candidate_id
            ),
            0,
        )
        if (
            normalized_selected_rank is not None
            and rank_from_payload != normalized_selected_rank
        ):
            issues.append("selected_candidate_rank drift from ranked payload")

    ranking_policy_id = metadata.get("ranking_policy_id")
    if (
        isinstance(selection_policy, dict)
        and ranking_policy_id is not None
        and str(selection_policy.get("policy_id") or "") != str(ranking_policy_id)
    ):
        issues.append("ranking policy drift between metadata and synthesis bundle")

    if output_hash:
        selected_candidate_hash = next(
            (
                str(((item.get("artifact") or {}).get("content_hash") or ""))
                for item in candidates or []
                if isinstance(item, dict)
                and item.get("candidate_id") == selected_candidate_id
                and isinstance(item.get("artifact"), dict)
                and ((item.get("artifact") or {}).get("content_hash"))
            ),
            "",
        )
        if not selected_candidate_hash:
            issues.append("selected candidate content hash missing")
        elif selected_candidate_hash != output_hash:
            issues.append("output hash drift from selected candidate artifact")

    return ModuleReceiptInvariantResult(
        ok=not issues,
        issues=tuple(issues),
        ranked_candidate_ids=ranked_candidate_ids,
        selected_candidate_id=selected_candidate_id,
        selected_candidate_rank=normalized_selected_rank,
    )


def _runtime_selection_integrity(
    metadata: dict[str, Any],
    receipt_invariants: ModuleReceiptInvariantResult,
) -> bool:
    if not receipt_invariants.ok:
        return False
    if receipt_invariants.selected_candidate_rank != 1:
        return False
    return bool(receipt_invariants.selected_candidate_id)


def _runtime_promotion_receipt_coverage(
    metadata: dict[str, Any],
    synthesis: dict[str, Any],
    *,
    promotion_requested: bool,
) -> bool:
    if not promotion_requested:
        return True

    promotion_shell = synthesis.get("promotion_shell")
    promotion_decision = synthesis.get("promotion_decision")
    if not isinstance(promotion_shell, dict) or not isinstance(
        promotion_decision, dict
    ):
        return False

    return (
        metadata.get("promotion_status") == "promoted"
        and metadata.get("promotion_outcome") == "promoted"
        and promotion_shell.get("status") == "promoted"
        and promotion_decision.get("outcome") == "promoted"
    )


def build_module_quality_event_from_metadata(
    metadata: dict[str, Any],
    *,
    use_signature: bool,
    promotion_requested: bool,
    case_name: str | None = None,
    output_hash: str | None = None,
) -> ModuleRuntimeQualityEvent:
    synthesis = metadata.get("synthesis")
    if not isinstance(synthesis, dict):
        receipt_invariants = ModuleReceiptInvariantResult(
            ok=False,
            issues=("missing synthesis metadata",),
            ranked_candidate_ids=(),
            selected_candidate_id=None,
            selected_candidate_rank=None,
        )
    else:
        receipt_invariants = evaluate_module_receipt_invariants(
            metadata,
            synthesis,
            output_hash=output_hash,
        )

    payload = {
        "run_kind": "module-gen",
        "case_name": case_name,
        "use_signature": bool(use_signature),
        "promotion_requested": bool(promotion_requested),
        "candidate_count": _to_int(metadata.get("candidate_count"), default=0),
        "selected_candidate_id": receipt_invariants.selected_candidate_id,
        "selected_candidate_rank": receipt_invariants.selected_candidate_rank or 0,
        "ranked_candidate_ids": list(receipt_invariants.ranked_candidate_ids),
        "validation_pass_count": _to_int(
            metadata.get("validation_pass_count"), default=0
        ),
        "validation_total": _to_int(metadata.get("validation_total"), default=0),
        "smoke_pass_count": _to_int(metadata.get("smoke_pass_count"), default=0),
        "smoke_total": _to_int(metadata.get("smoke_total"), default=0),
        "selection_integrity": _runtime_selection_integrity(
            metadata,
            receipt_invariants,
        ),
        "receipt_coverage": receipt_invariants.ok,
        "promotion_receipt_coverage": _runtime_promotion_receipt_coverage(
            metadata,
            synthesis if isinstance(synthesis, dict) else {},
            promotion_requested=promotion_requested,
        ),
        "output_hash": output_hash,
        "receipt_invariant_issues": list(receipt_invariants.issues),
    }
    return ModuleRuntimeQualityEvent(
        payload=payload, receipt_invariants=receipt_invariants
    )


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
            0, min(_to_int(row.get("validation_pass_count"), default=0), v_total)
        )
        validation_pass_count += v_pass
        validation_total += v_total

        s_total = max(0, _to_int(row.get("smoke_total"), default=0))
        s_pass = max(0, min(_to_int(row.get("smoke_pass_count"), default=0), s_total))
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
