# summary: "Tests receipt-backed Oracle branch timelines, diffs, indexing, and failure bisection."
# read_when:
#   - "Changing Oracle behavioral time-travel commands or lineage semantics."

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.oracle_time_travel import bisect_branch, load_receipt_records
from dspx.run_receipts import build_run_receipt, write_run_receipt


runner = CliRunner()


def _write_receipt(
    root: Path,
    *,
    output_name: str,
    run_id: str,
    created_at: str,
    run_kind: str,
    outcome: Literal["success", "failure", "partial", "cached", "unknown"],
    branch: str | None = None,
    parent_run_id: str | None = None,
    causal_chain: list[str] | None = None,
) -> None:
    output_path = root / output_name
    output_path.write_text("print('ok')\n", encoding="utf-8")
    receipt = build_run_receipt(
        run_kind=run_kind,
        output_path=output_path,
        output_hash=run_id,
        template_version="simple-v1",
        cache_key=None,
        cache_file=None,
        cache_enabled=False,
        execution_id=run_id,
        branch=branch,
        parent_run_id=parent_run_id,
        causal_chain=causal_chain,
        outcome=outcome,
        capture_context=False,
    )
    receipt["created_at"] = created_at
    write_run_receipt(output_path, receipt)


def _seed_time_travel_receipts(root: Path) -> None:
    _write_receipt(
        root,
        output_name="root.py",
        run_id="root-001",
        created_at="2026-03-21T10:00:00+00:00",
        run_kind="signature-gen",
        outcome="success",
    )
    _write_receipt(
        root,
        output_name="main-2.py",
        run_id="main-002",
        created_at="2026-03-21T10:03:00+00:00",
        run_kind="module-gen",
        outcome="success",
        parent_run_id="root-001",
        causal_chain=["root-001"],
    )
    _write_receipt(
        root,
        output_name="feature-a-1.py",
        run_id="feature-a-001",
        created_at="2026-03-21T10:05:00+00:00",
        run_kind="module-gen",
        outcome="success",
        branch="feature-a",
        parent_run_id="root-001",
        causal_chain=["root-001"],
    )
    _write_receipt(
        root,
        output_name="feature-a-2.py",
        run_id="feature-a-002",
        created_at="2026-03-21T10:10:00+00:00",
        run_kind="module-gen",
        outcome="failure",
        branch="feature-a",
        parent_run_id="feature-a-001",
        causal_chain=["root-001", "feature-a-001"],
    )
    _write_receipt(
        root,
        output_name="feature-b-1.py",
        run_id="feature-b-001",
        created_at="2026-03-21T10:07:00+00:00",
        run_kind="module-gen",
        outcome="success",
        branch="feature-b",
        parent_run_id="root-001",
        causal_chain=["root-001"],
    )
    _write_receipt(
        root,
        output_name="feature-b-2.py",
        run_id="feature-b-002",
        created_at="2026-03-21T10:12:00+00:00",
        run_kind="module-gen",
        outcome="partial",
        branch="feature-b",
        causal_chain=[
            "root-001",
            "feature-a-001",
            "feature-b-001",
            "feature-a-001",
            "missing-parent",
        ],
    )


def test_oracle_index_since_compares_timezone_instants(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    _write_receipt(
        tmp_path,
        output_name="after.py",
        run_id="after-boundary",
        created_at="2023-12-31T20:00:00-05:00",
        run_kind="module-gen",
        outcome="success",
    )
    _write_receipt(
        tmp_path,
        output_name="before.py",
        run_id="before-boundary",
        created_at="2023-12-31T18:00:00-05:00",
        run_kind="module-gen",
        outcome="success",
    )

    result = runner.invoke(
        app,
        [
            "oracle",
            "index",
            "--from-receipts",
            "--path",
            str(tmp_path),
            "--index-path",
            str(tmp_path / "coordinates.db"),
            "--since",
            "2024-01-01T00:00:00Z",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["scanned"] == 2
    assert payload["indexed"] == 1
    assert payload["skipped"] == 1


def test_oracle_branch_lists_behavioral_branches(tmp_path: Path) -> None:
    _seed_time_travel_receipts(tmp_path)

    result = runner.invoke(
        app,
        ["oracle", "branch", "--path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    branches = {entry["branch"]: entry for entry in payload["branches"]}
    assert set(branches) == {"main", "feature-a", "feature-b"}
    assert branches["main"]["runs_total"] == 2
    assert branches["main"]["lineage_links"] == 1
    assert branches["feature-a"]["runs_total"] == 2
    assert branches["feature-a"]["lineage_links"] == 2
    assert branches["feature-b"]["runs_total"] == 2
    assert branches["feature-b"]["lineage_links"] == 2


def test_oracle_branch_reports_branch_timeline(tmp_path: Path) -> None:
    _seed_time_travel_receipts(tmp_path)

    result = runner.invoke(
        app,
        ["oracle", "branch", "feature-a", "--path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["branch"] == "feature-a"
    assert payload["summary"]["runs_total"] == 2
    assert [run["run_id"] for run in payload["runs"]] == [
        "feature-a-001",
        "feature-a-002",
    ]
    assert payload["runs"][1]["parent_run_id"] == "feature-a-001"
    assert payload["runs"][1]["causal_chain"] == ["root-001", "feature-a-001"]


def test_oracle_branch_falls_back_to_main_when_branch_metadata_absent(
    tmp_path: Path,
) -> None:
    _seed_time_travel_receipts(tmp_path)

    result = runner.invoke(
        app,
        ["oracle", "branch", "main", "--path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["branch"] == "main"
    assert payload["summary"]["runs_total"] == 2
    assert [run["run_id"] for run in payload["runs"]] == ["root-001", "main-002"]
    assert payload["runs"][1]["parent_run_id"] == "root-001"
    assert payload["runs"][1]["lineage_ids"] == ["root-001"]


def test_oracle_bisect_accepts_single_pass_iterables(tmp_path: Path) -> None:
    _seed_time_travel_receipts(tmp_path)

    payload = bisect_branch(
        (record for record in load_receipt_records(tmp_path)),
        "feature-a",
    )

    assert payload["status"] == "boundary_found"
    assert payload["method"] == "causal_chain"
    assert payload["candidate_window"] == ["feature-a-001", "feature-a-002"]


def test_oracle_diff_compares_branch_lineage(tmp_path: Path) -> None:
    _seed_time_travel_receipts(tmp_path)

    result = runner.invoke(
        app,
        ["oracle", "diff", "feature-a", "feature-b", "--path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["left_branch"] == "feature-a"
    assert payload["right_branch"] == "feature-b"
    assert payload["shared_lineage_ids"] == ["feature-a-001", "root-001"]
    assert payload["left_only_run_ids"] == ["feature-a-001", "feature-a-002"]
    assert payload["right_only_run_ids"] == ["feature-b-001", "feature-b-002"]


def test_oracle_diff_does_not_collapse_distinct_runs_with_same_output_hash(
    tmp_path: Path,
) -> None:
    for branch, output_name, execution_id, created_at in (
        ("feature-a", "a.py", "exec-a", "2026-03-21T10:00:00+00:00"),
        ("feature-b", "b.py", "exec-b", "2026-03-21T10:05:00+00:00"),
    ):
        output_path = tmp_path / output_name
        output_path.write_text("print('same')\n", encoding="utf-8")
        receipt = build_run_receipt(
            run_kind="module-gen",
            output_path=output_path,
            output_hash="same-output-hash",
            template_version="simple-v1",
            cache_key=None,
            cache_file=None,
            cache_enabled=False,
            execution_id=execution_id,
            branch=branch,
            outcome="success",
            capture_context=False,
        )
        receipt["created_at"] = created_at
        write_run_receipt(output_path, receipt)

    result = runner.invoke(
        app,
        ["oracle", "diff", "feature-a", "feature-b", "--path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["shared_lineage_ids"] == []
    assert payload["left_only_run_ids"] == ["exec-a"]
    assert payload["right_only_run_ids"] == ["exec-b"]


def test_oracle_diff_ignores_non_string_lineage_entries(tmp_path: Path) -> None:
    left_output = tmp_path / "left.py"
    left_output.write_text("print('ok')\n", encoding="utf-8")
    left_receipt = build_run_receipt(
        run_kind="module-gen",
        output_path=left_output,
        output_hash="left-001",
        template_version="simple-v1",
        cache_key=None,
        cache_file=None,
        cache_enabled=False,
        execution_id="left-001",
        branch="feature-left",
        outcome="success",
        capture_context=False,
    )
    left_receipt["created_at"] = "2026-03-21T10:00:00+00:00"
    left_receipt["causal_chain"] = ["root-001", None, 123, "root-001"]
    write_run_receipt(left_output, left_receipt)

    _write_receipt(
        tmp_path,
        output_name="right.py",
        run_id="right-001",
        created_at="2026-03-21T10:05:00+00:00",
        run_kind="module-gen",
        outcome="success",
        branch="feature-right",
        causal_chain=["root-001"],
    )

    result = runner.invoke(
        app,
        [
            "oracle",
            "diff",
            "feature-left",
            "feature-right",
            "--path",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["shared_lineage_ids"] == ["root-001"]
    assert "123" not in payload["shared_lineage_ids"]
    assert "None" not in payload["shared_lineage_ids"]


def test_oracle_diff_prefers_legacy_cache_key_over_shared_output_path(
    tmp_path: Path,
) -> None:
    shared_output_path = "/repo/generated/same.py"
    for output_name, branch, cache_key, created_at in (
        ("feature-left.py", "feature-left", "cache-left", "2026-03-21T10:00:00+00:00"),
        (
            "feature-right.py",
            "feature-right",
            "cache-right",
            "2026-03-21T10:05:00+00:00",
        ),
    ):
        output_path = tmp_path / output_name
        output_path.write_text("print('same')\n", encoding="utf-8")
        receipt = build_run_receipt(
            run_kind="module-gen",
            output_path=output_path,
            output_hash="same-output-hash",
            template_version="simple-v1",
            cache_key=cache_key,
            cache_file=None,
            cache_enabled=False,
            branch=branch,
            outcome="success",
            capture_context=False,
        )
        receipt.pop("execution_id", None)
        receipt["output_path"] = shared_output_path
        receipt["created_at"] = created_at
        write_run_receipt(output_path, receipt)

    result = runner.invoke(
        app,
        [
            "oracle",
            "diff",
            "feature-left",
            "feature-right",
            "--path",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["shared_lineage_ids"] == []
    assert payload["left_only_run_ids"] == ["cache-left"]
    assert payload["right_only_run_ids"] == ["cache-right"]


def test_oracle_bisect_uses_parent_run_id_when_causal_chain_is_partial(
    tmp_path: Path,
) -> None:
    _write_receipt(
        tmp_path,
        output_name="root.py",
        run_id="root-001",
        created_at="2026-03-21T10:00:00+00:00",
        run_kind="signature-gen",
        outcome="success",
        branch="feature-parent",
    )
    _write_receipt(
        tmp_path,
        output_name="parent.py",
        run_id="parent-001",
        created_at="2026-03-21T10:05:00+00:00",
        run_kind="module-gen",
        outcome="success",
        branch="feature-parent",
        parent_run_id="root-001",
        causal_chain=["root-001"],
    )
    _write_receipt(
        tmp_path,
        output_name="bad.py",
        run_id="bad-001",
        created_at="2026-03-21T10:10:00+00:00",
        run_kind="module-gen",
        outcome="failure",
        branch="feature-parent",
        parent_run_id="parent-001",
        causal_chain=["root-001"],
    )

    result = runner.invoke(
        app,
        ["oracle", "bisect", "feature-parent", "--path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "boundary_found"
    assert payload["method"] == "causal_chain"
    assert payload["last_good_run"]["run_id"] == "parent-001"
    assert payload["first_bad_run"]["run_id"] == "bad-001"
    assert payload["candidate_window"] == ["parent-001", "bad-001"]


def test_oracle_bisect_finds_first_bad_boundary(tmp_path: Path) -> None:
    _seed_time_travel_receipts(tmp_path)

    result = runner.invoke(
        app,
        ["oracle", "bisect", "feature-a", "--path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "boundary_found"
    assert payload["method"] == "causal_chain"
    assert payload["last_good_run"]["run_id"] == "feature-a-001"
    assert payload["first_bad_run"]["run_id"] == "feature-a-002"
    assert payload["candidate_window"] == ["feature-a-001", "feature-a-002"]


def test_oracle_bisect_falls_back_to_branch_timeline_when_lineage_is_partial(
    tmp_path: Path,
) -> None:
    _seed_time_travel_receipts(tmp_path)
    _write_receipt(
        tmp_path,
        output_name="feature-c-1.py",
        run_id="feature-c-001",
        created_at="2026-03-21T10:15:00+00:00",
        run_kind="module-gen",
        outcome="success",
        branch="feature-c",
    )
    _write_receipt(
        tmp_path,
        output_name="feature-c-2.py",
        run_id="feature-c-002",
        created_at="2026-03-21T10:20:00+00:00",
        run_kind="module-gen",
        outcome="failure",
        branch="feature-c",
        causal_chain=["missing-parent"],
    )

    result = runner.invoke(
        app,
        ["oracle", "bisect", "feature-c", "--path", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "boundary_found"
    assert payload["method"] == "branch_timeline"
    assert payload["last_good_run"]["run_id"] == "feature-c-001"
    assert payload["first_bad_run"]["run_id"] == "feature-c-002"
    assert payload["candidate_window"] == ["feature-c-001", "feature-c-002"]
    assert payload["missing_lineage_ids"] == ["missing-parent"]
