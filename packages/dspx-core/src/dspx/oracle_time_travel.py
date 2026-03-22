from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from dspx.run_receipts import load_run_receipt


@dataclass(frozen=True)
class ReceiptRecord:
    run_id: str
    receipt_path: Path
    output_path: str
    created_at: str | None
    created_dt: datetime | None
    branch: str
    run_kind: str
    provider: str
    outcome: str
    parent_run_id: str | None
    causal_chain: tuple[str, ...]

    @property
    def lineage_ids(self) -> tuple[str, ...]:
        ids = list(self.causal_chain)
        if self.parent_run_id and self.parent_run_id not in ids:
            ids.append(self.parent_run_id)
        return tuple(ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "receipt_path": str(self.receipt_path),
            "output_path": self.output_path,
            "created_at": self.created_at,
            "branch": self.branch,
            "run_kind": self.run_kind,
            "provider": self.provider,
            "outcome": self.outcome,
            "parent_run_id": self.parent_run_id,
            "causal_chain": list(self.causal_chain),
            "lineage_ids": list(self.lineage_ids),
        }


@dataclass(frozen=True)
class BranchSummary:
    branch: str
    runs_total: int
    outcomes: dict[str, int]
    run_kinds: dict[str, int]
    first_run_at: str | None
    last_run_at: str | None
    lineage_links: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "runs_total": self.runs_total,
            "outcomes": dict(self.outcomes),
            "run_kinds": dict(self.run_kinds),
            "first_run_at": self.first_run_at,
            "last_run_at": self.last_run_at,
            "lineage_links": self.lineage_links,
        }


def _parse_created_at(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _receipt_run_id(receipt: dict[str, Any], meta_path: Path) -> str:
    for key in ("execution_id", "run_id"):
        value = receipt.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    output_path = receipt.get("output_path")
    if isinstance(output_path, str) and output_path.strip():
        return output_path.strip()
    for key in ("cache_key", "hash"):
        value = receipt.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(meta_path)


def _normalize_lineage_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    seen: set[str] = set()
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        run_id = item.strip()
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        normalized.append(run_id)
    return tuple(normalized)


def _load_record(meta_path: Path) -> ReceiptRecord | None:
    receipt = load_run_receipt(meta_path)
    if not isinstance(receipt, dict):
        return None

    created_at_raw = receipt.get("created_at")
    created_at = created_at_raw.strip() if isinstance(created_at_raw, str) else None
    parent_run_id_raw = receipt.get("parent_run_id")
    parent_run_id = (
        parent_run_id_raw.strip()
        if isinstance(parent_run_id_raw, str) and parent_run_id_raw.strip()
        else None
    )
    output_path = receipt.get("output_path")
    output_text = output_path.strip() if isinstance(output_path, str) else ""
    branch = receipt.get("branch")
    branch_name = (
        branch.strip() if isinstance(branch, str) and branch.strip() else "main"
    )
    run_kind = receipt.get("run_kind")
    run_kind_text = (
        run_kind.strip()
        if isinstance(run_kind, str) and run_kind.strip()
        else "unknown"
    )
    provider = receipt.get("provider")
    provider_text = (
        provider.strip()
        if isinstance(provider, str) and provider.strip()
        else "unknown"
    )
    outcome = receipt.get("outcome")
    outcome_text = (
        outcome.strip() if isinstance(outcome, str) and outcome.strip() else "unknown"
    )

    return ReceiptRecord(
        run_id=_receipt_run_id(receipt, meta_path),
        receipt_path=meta_path,
        output_path=output_text,
        created_at=created_at,
        created_dt=_parse_created_at(created_at),
        branch=branch_name,
        run_kind=run_kind_text,
        provider=provider_text,
        outcome=outcome_text,
        parent_run_id=parent_run_id,
        causal_chain=_normalize_lineage_ids(receipt.get("causal_chain")),
    )


def load_receipt_records(path: Path | None = None) -> list[ReceiptRecord]:
    scan_path = path or (Path.cwd() / "generated")
    if scan_path.is_file():
        candidate_paths = [scan_path] if scan_path.name.endswith(".meta.json") else []
    else:
        candidate_paths = (
            sorted(scan_path.rglob("*.meta.json")) if scan_path.exists() else []
        )

    records = [
        record for candidate in candidate_paths if (record := _load_record(candidate))
    ]
    return sorted(
        records,
        key=lambda record: (
            record.created_dt or datetime.min.replace(tzinfo=timezone.utc),
            record.branch,
            record.run_id,
            str(record.receipt_path),
        ),
    )


def summarize_branches(records: Iterable[ReceiptRecord]) -> list[BranchSummary]:
    grouped: dict[str, list[ReceiptRecord]] = defaultdict(list)
    for record in records:
        grouped[record.branch].append(record)

    summaries: list[BranchSummary] = []
    for branch_name in sorted(grouped):
        branch_records = sorted_branch_records(grouped[branch_name])
        outcome_counts = Counter(record.outcome for record in branch_records)
        run_kind_counts = Counter(record.run_kind for record in branch_records)
        first_run_at = branch_records[0].created_at if branch_records else None
        last_run_at = branch_records[-1].created_at if branch_records else None
        lineage_links = sum(
            1
            for record in branch_records
            if record.parent_run_id or record.causal_chain
        )
        summaries.append(
            BranchSummary(
                branch=branch_name,
                runs_total=len(branch_records),
                outcomes=dict(sorted(outcome_counts.items())),
                run_kinds=dict(sorted(run_kind_counts.items())),
                first_run_at=first_run_at,
                last_run_at=last_run_at,
                lineage_links=lineage_links,
            )
        )
    return summaries


def sorted_branch_records(records: Iterable[ReceiptRecord]) -> list[ReceiptRecord]:
    return sorted(
        records,
        key=lambda record: (
            record.created_dt or datetime.min.replace(tzinfo=timezone.utc),
            record.run_id,
            str(record.receipt_path),
        ),
    )


def branch_timeline(
    records: Iterable[ReceiptRecord], branch: str
) -> list[ReceiptRecord]:
    branch_name = branch.strip()
    return sorted_branch_records(
        record for record in records if record.branch == branch_name
    )


def branch_report(records: Iterable[ReceiptRecord], branch: str) -> dict[str, Any]:
    branch_records = branch_timeline(records, branch)
    if not branch_records:
        raise ValueError(f"Unknown branch: {branch}")

    summary = summarize_branches(branch_records)[0]
    return {
        "branch": summary.branch,
        "summary": summary.to_dict(),
        "runs": [record.to_dict() for record in branch_records],
    }


def _lineage_set(records: Iterable[ReceiptRecord]) -> set[str]:
    lineage: set[str] = set()
    for record in records:
        lineage.add(record.run_id)
        lineage.update(record.lineage_ids)
    return lineage


def diff_branches(
    records: Iterable[ReceiptRecord], left: str, right: str
) -> dict[str, Any]:
    left_records = branch_timeline(records, left)
    right_records = branch_timeline(records, right)
    if not left_records:
        raise ValueError(f"Unknown branch: {left}")
    if not right_records:
        raise ValueError(f"Unknown branch: {right}")

    left_summary = summarize_branches(left_records)[0]
    right_summary = summarize_branches(right_records)[0]
    left_run_ids = {record.run_id for record in left_records}
    right_run_ids = {record.run_id for record in right_records}
    left_lineage = _lineage_set(left_records)
    right_lineage = _lineage_set(right_records)
    left_run_kinds = {record.run_kind for record in left_records}
    right_run_kinds = {record.run_kind for record in right_records}

    return {
        "left_branch": left,
        "right_branch": right,
        "left_summary": left_summary.to_dict(),
        "right_summary": right_summary.to_dict(),
        "shared_lineage_ids": sorted(left_lineage & right_lineage),
        "shared_run_kinds": sorted(left_run_kinds & right_run_kinds),
        "left_only_run_ids": sorted(left_run_ids - right_run_ids),
        "right_only_run_ids": sorted(right_run_ids - left_run_ids),
        "left_only_run_kinds": sorted(left_run_kinds - right_run_kinds),
        "right_only_run_kinds": sorted(right_run_kinds - left_run_kinds),
    }


def bisect_branch(
    records: Iterable[ReceiptRecord],
    branch: str,
    *,
    bad_outcomes: Iterable[str] = ("failure", "partial"),
) -> dict[str, Any]:
    branch_records = branch_timeline(records, branch)
    if not branch_records:
        raise ValueError(f"Unknown branch: {branch}")

    bad_set = {outcome.strip() for outcome in bad_outcomes if outcome.strip()}
    if not bad_set:
        bad_set = {"failure", "partial"}

    first_bad = next(
        (record for record in branch_records if record.outcome in bad_set),
        None,
    )
    if first_bad is None:
        return {
            "branch": branch,
            "bad_outcomes": sorted(bad_set),
            "status": "clean",
            "method": "branch_timeline",
            "last_good_run": branch_records[-1].to_dict() if branch_records else None,
            "first_bad_run": None,
            "candidate_window": [],
        }

    record_by_run_id = {record.run_id: record for record in records}
    lineage_records = [
        record_by_run_id[run_id]
        for run_id in first_bad.causal_chain
        if run_id in record_by_run_id
    ]
    missing_lineage_ids = [
        run_id for run_id in first_bad.causal_chain if run_id not in record_by_run_id
    ]

    last_good = next(
        (
            record
            for record in reversed(lineage_records)
            if record.outcome not in bad_set
        ),
        None,
    )
    method = "causal_chain"
    if last_good is None:
        method = "branch_timeline"
        prefix_records = branch_records[: branch_records.index(first_bad)]
        last_good = next(
            (
                record
                for record in reversed(prefix_records)
                if record.outcome not in bad_set
            ),
            None,
        )

    candidate_window = [first_bad.run_id]
    if last_good is not None:
        candidate_window = [last_good.run_id, first_bad.run_id]

    return {
        "branch": branch,
        "bad_outcomes": sorted(bad_set),
        "status": "boundary_found",
        "method": method,
        "last_good_run": last_good.to_dict() if last_good is not None else None,
        "first_bad_run": first_bad.to_dict(),
        "candidate_window": candidate_window,
        "missing_lineage_ids": missing_lineage_ids,
    }


def format_branch_summaries(summaries: Iterable[BranchSummary]) -> str:
    summary_list = list(summaries)
    lines = [f"Branches: {len(summary_list)}"]
    for summary in summary_list:
        lines.append(
            "- "
            f"{summary.branch}: {summary.runs_total} runs, "
            f"outcomes={json.dumps(summary.outcomes, sort_keys=True)}, "
            f"window={summary.first_run_at or 'unknown'} → {summary.last_run_at or 'unknown'}"
        )
    return "\n".join(lines)


def format_branch_report(report: dict[str, Any]) -> str:
    lines = [
        f"Branch {report['branch']} ({report['summary']['runs_total']} runs)",
    ]
    for run in report["runs"]:
        lines.append(
            "- "
            f"{run['created_at'] or 'unknown'} "
            f"{run['run_id']} "
            f"{run['run_kind']} "
            f"outcome={run['outcome']} "
            f"parent={run['parent_run_id'] or '-'} "
            f"lineage={len(run['causal_chain'])}"
        )
    return "\n".join(lines)


def format_diff_report(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Diff {report['left_branch']} ↔ {report['right_branch']}",
            (f"- shared_lineage_ids={', '.join(report['shared_lineage_ids']) or '-'}"),
            (
                f"- {report['left_branch']}_only_runs="
                f"{', '.join(report['left_only_run_ids']) or '-'}"
            ),
            (
                f"- {report['right_branch']}_only_runs="
                f"{', '.join(report['right_only_run_ids']) or '-'}"
            ),
            (
                f"- outcomes_left={json.dumps(report['left_summary']['outcomes'], sort_keys=True)}"
            ),
            (
                f"- outcomes_right={json.dumps(report['right_summary']['outcomes'], sort_keys=True)}"
            ),
        ]
    )


def format_bisect_report(report: dict[str, Any]) -> str:
    lines = [
        f"Bisect {report['branch']} ({report['status']})",
        f"- method={report['method']}",
        f"- bad_outcomes={', '.join(report['bad_outcomes'])}",
    ]
    last_good = report.get("last_good_run")
    if last_good is not None:
        lines.append(
            f"- last_good={last_good['run_id']} outcome={last_good['outcome']}"
        )
    first_bad = report.get("first_bad_run")
    if first_bad is not None:
        lines.append(
            f"- first_bad={first_bad['run_id']} outcome={first_bad['outcome']}"
        )
    window = report.get("candidate_window") or []
    lines.append(f"- candidate_window={', '.join(window) or '-'}")
    missing = report.get("missing_lineage_ids") or []
    if missing:
        lines.append(f"- missing_lineage_ids={', '.join(missing)}")
    return "\n".join(lines)
