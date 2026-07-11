# summary: "Tests the program-loop workflow from intent generation through behavior evidence, Oracle reporting, publication, and candidate state."
# read_when:
#   - "Changing program-loop CLI orchestration, behavior evaluation, Oracle indexing/publication, candidate state, or output-path confinement."

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import (
    CoordinateIndex,
    CoordinateStore,
    ExecutionEmbedding,
    reset_embedding_engine,
)
import dspx.services.program_workflow as program_workflow
from dspx.services.program_workflow import run_program_loop_from_intent_path

runner = CliRunner()


class FakeSharedOracleStore:
    backend_name = "fake_shared_oracle"
    redacted_database_url = (
        "postgresql://dspx_oracle:<redacted>@example.invalid/dspx_oracle"
    )

    def __init__(self) -> None:
        self.records: dict[str, ExecutionEmbedding] = {}

    def upsert(self, embedding: ExecutionEmbedding) -> bool:
        self.records[embedding.run_id] = embedding
        return True


def _write_intent(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: TicketProgram",
                "objective: Classify support ticket urgency.",
                "inputs:",
                "  - ticket_text",
                "outputs:",
                "  - urgency",
                "metric: exact_match",
                "constraints:",
                "  - use only the supplied ticket text",
                "examples:",
                "  - inputs:",
                "      ticket_text: Server is down for all users",
                "    outputs:",
                "      urgency: high",
            ]
        ),
        encoding="utf-8",
    )


def _loop_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_STUB_RESPONSE_JSON", '{"urgency":"high"}')
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def test_program_loop_cli_runs_one_intent_to_stateful_oracle_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-loop-workflow-v2"
    assert payload["status"] == "ok"
    assert payload["candidate"]["manifest_path"] == str(outdir / "manifest.json")
    assert payload["steps"]["program_gen"]["status"] == "ok"
    assert payload["steps"]["program_gen"]["materialization_status"] == "materialized"
    assert payload["steps"]["behavior_evaluation"]["status"] == "passed"
    assert payload["steps"]["behavior_evaluation"]["source_kind"] == "behavior_episode"
    assert payload["steps"]["behavior_evaluation"]["passed"] is True
    assert payload["steps"]["replay_check"]["status"] == "ok"
    assert payload["steps"]["oracle_index"]["status"] == "ok"
    assert payload["steps"]["oracle_index"]["result"]["indexed"] == 1
    assert payload["steps"]["oracle_report"]["status"] == "ok"
    assert payload["steps"]["candidate_state"]["status"]
    assert payload["effect"] == {
        "program_candidate_materialized": True,
        "replay_checked": True,
        "oracle_index_mutated": True,
        "oracle_index_scope": "candidate-local explicit path",
        "oracle_report_written": True,
        "candidate_state_written": True,
        "oracle_publication_preflight_written": False,
        "oracle_publication_receipt_written": False,
        "shared_oracle_mutated": False,
        "shared_oracle_publication_scope": "none",
        "workflow_summary_written": True,
        "ak_called": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
        "promotion_applied": False,
        "winner_selected": False,
    }
    assert payload["steps"]["oracle_publication"] == {
        "status": "skipped",
        "preflight_path": None,
        "receipt_path": None,
        "publication_id": None,
        "publication_label": None,
        "evidence_only": False,
        "scope": "none",
    }
    assert payload["non_authority"]["promotion_authority"] is False
    assert payload["non_authority"]["automatic_promotion"] is False

    index_path = outdir / "oracle" / "coordinates.db"
    report_path = outdir / "program_oracle_report.json"
    state_path = outdir / "program_candidate_state.json"
    workflow_path = outdir / "program_loop.json"
    assert index_path.exists()
    assert report_path.exists()
    assert state_path.exists()
    assert workflow_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "program-oracle-evidence-report-v1"
    assert report["total_records"] == 1
    assert report["non_authority"]["oracle_promotion"] is False

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema_version"] == "program-candidate-state-v1"
    assert state["truth_summary"]["program_materialized"] is True
    assert state["truth_summary"]["behavior_evidence_present"] is True
    assert state["truth_summary"]["oracle_report_present"] is True
    assert state["truth_summary"]["promotion_applied"] is False
    assert state["truth_summary"]["ak_called"] is False
    assert state["truth_summary"]["oracle_publication_ref_present"] is False

    index = CoordinateIndex(db_path=index_path)
    stats = index.stats()
    assert stats["total"] == 1
    assert stats["by_run_kind"]["program-oracle-evidence"] == 1


def test_program_loop_prefers_aggregate_behavior_episode_over_inline_results() -> None:
    evaluation = program_workflow._workflow_behavior_evaluation(
        {
            "created_from": {
                "behavior_results_path": "/candidate/behavior_results.json",
                "behavior_episode_path": "/candidate/behavior_episode.json",
            },
            "evidence_state": {
                "behavior": {
                    "present": True,
                    "status": "passed",
                    "sha256": "a" * 64,
                },
                "behavior_episode": {
                    "present": True,
                    "status": "failed",
                    "sha256": "b" * 64,
                },
            },
        }
    )

    assert evaluation["source_kind"] == "behavior_episode"
    assert evaluation["status"] == "failed"
    assert evaluation["passed"] is False
    assert evaluation["path"] == "/candidate/behavior_episode.json"


def test_program_loop_behavior_failure_is_nonzero_but_preserves_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)
    intent_path.write_text(
        intent_path.read_text(encoding="utf-8").replace(
            "urgency: high", "urgency: impossible"
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "behavior_failed"
    assert payload["steps"]["program_gen"]["status"] == "ok"
    assert payload["steps"]["program_gen"]["materialization_status"] == "materialized"
    assert payload["steps"]["replay_check"]["status"] == "ok"
    assert payload["steps"]["behavior_evaluation"]["status"] == "failed"
    assert payload["steps"]["behavior_evaluation"]["passed"] is False
    assert (outdir / "manifest.json").exists()
    assert (outdir / "behavior_results.json").exists()
    assert (outdir / "program_loop.json").exists()


def test_program_loop_without_behavior_evidence_is_degraded_and_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)
    intent_text = intent_path.read_text(encoding="utf-8")
    intent_path.write_text(intent_text.split("examples:", 1)[0], encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--skip-oracle-index",
            "--json",
        ],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "degraded"
    assert payload["steps"]["program_gen"]["status"] == "ok"
    assert payload["steps"]["behavior_evaluation"] == {
        "path": None,
        "passed": False,
        "sha256": None,
        "source_kind": "none",
        "status": "not_evaluated",
        "summary": {
            "present": False,
            "sha256": None,
            "status": "not_evaluated",
            "status_counts": {},
        },
    }
    assert (outdir / "manifest.json").exists()
    assert (outdir / "program_loop.json").exists()


def test_program_loop_can_skip_oracle_index_and_still_write_candidate_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--skip-oracle-index",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-loop-workflow-v2"
    assert payload["status"] == "ok"
    assert payload["steps"]["oracle_index"]["status"] == "skipped"
    assert payload["steps"]["oracle_report"]["status"] == "skipped"
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["effect"]["oracle_report_written"] is False
    assert (outdir / "program_candidate_state.json").exists()
    assert (outdir / "program_loop.json").exists()
    assert not (outdir / "program_oracle_report.json").exists()
    assert not (outdir / "oracle" / "coordinates.db").exists()

    state = json.loads((outdir / "program_candidate_state.json").read_text())
    assert state["truth_summary"]["program_materialized"] is True
    assert state["truth_summary"]["oracle_report_present"] is False
    assert state["truth_summary"]["ak_called"] is False


def test_program_loop_shared_publication_opt_in_writes_receipt_as_evidence_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)
    store = FakeSharedOracleStore()
    monkeypatch.setenv("DSPX_ORACLE_STORE", "postgres_pgvector")
    monkeypatch.setenv(
        "DSPX_ORACLE_DATABASE_URL",
        "postgresql://dspx_oracle:secret@example.invalid:55432/dspx_oracle",
    )

    payload = run_program_loop_from_intent_path(
        intent_path,
        outdir=outdir,
        publish_to_shared="retained",
        publisher_id="pi-test",
        publisher_role="operator",
        publisher_assertion="share synthetic behavior evidence for future Oracle retrieval",
        redaction_status="checked",
        retention_class="retained_behavior_memory",
        shared_publication_store=cast(CoordinateStore, store),
    )

    assert payload["status"] == "ok"
    publication_step = payload["steps"]["oracle_publication"]
    assert publication_step["status"] == "published"
    assert publication_step["publication_id"].startswith("prog-oracle-pub-")
    assert publication_step["publication_label"] == "retained"
    assert publication_step["evidence_only"] is True
    assert publication_step["scope"] == "explicit_shared_publication_opt_in"
    assert payload["effect"]["oracle_publication_preflight_written"] is True
    assert payload["effect"]["oracle_publication_receipt_written"] is True
    assert payload["effect"]["shared_oracle_mutated"] is True
    assert payload["effect"]["ak_called"] is False
    oracle_index_result = payload["steps"]["oracle_index"]["result"]
    assert Path(oracle_index_result["index_path"]).exists()
    assert "database_url" not in oracle_index_result["index_stats"]
    assert payload["effect"]["governance_mutated"] is False
    assert payload["effect"]["promotion_applied"] is False
    assert len(store.records) == 1

    receipt_path = outdir / "program_oracle_publication_receipt.json"
    preflight_path = outdir / "program_oracle_publication_preflight.json"
    state_path = outdir / "program_candidate_state.json"
    assert receipt_path.exists()
    assert preflight_path.exists()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "program-oracle-shared-publication-receipt-v1"
    assert receipt["effect"]["shared_oracle_mutated"] is True
    assert receipt["effect"]["ak_called"] is False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["truth_summary"]["oracle_publication_ref_present"] is False
    assert state["shared_oracle_publication"] == {
        "preflight_present": True,
        "preflight_ready": True,
        "publication_id": receipt["publication_id"],
        "evidence_ref_present": False,
        "evidence_only": True,
        "activation_authority": False,
        "promotion_authority": False,
    }
    assert state["truth_summary"]["promotion_applied"] is False
    assert state["truth_summary"]["winner_selected"] is False


def test_program_loop_validates_candidate_closure_before_shared_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)
    store = FakeSharedOracleStore()
    monkeypatch.setenv("DSPX_ORACLE_STORE", "postgres_pgvector")
    monkeypatch.setenv(
        "DSPX_ORACLE_DATABASE_URL",
        "postgresql://dspx_oracle:secret@example.invalid:55432/dspx_oracle",
    )
    monkeypatch.setattr(
        program_workflow,
        "snapshot_candidate_artifact_closure",
        lambda _path: (_ for _ in ()).throw(ValueError("stale candidate closure")),
    )

    with pytest.raises(
        ValueError,
        match="invalid before shared Oracle publication",
    ):
        run_program_loop_from_intent_path(
            intent_path,
            outdir=outdir,
            publish_to_shared="retained",
            publisher_id="pi-test",
            publisher_role="operator",
            publisher_assertion="share synthetic behavior evidence",
            redaction_status="checked",
            retention_class="retained_behavior_memory",
            shared_publication_store=cast(CoordinateStore, store),
        )

    assert store.records == {}
    assert not (outdir / "program_oracle_publication_receipt.json").exists()
    assert not (outdir / "program_candidate_state.json").exists()


def test_program_loop_revalidates_shared_publication_receipt_before_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)
    store = FakeSharedOracleStore()
    monkeypatch.setenv("DSPX_ORACLE_STORE", "postgres_pgvector")
    monkeypatch.setenv(
        "DSPX_ORACLE_DATABASE_URL",
        "postgresql://dspx_oracle:secret@example.invalid:55432/dspx_oracle",
    )
    original_writer = program_workflow.write_program_oracle_publication_receipt

    def _tampered_writer(receipt: dict[str, Any], out_path: Path) -> dict[str, Any]:
        payload = original_writer(receipt, out_path)
        record = dict(payload.get("record") or {})
        record["non_authority"] = {
            **dict(record.get("non_authority") or {}),
            "oracle_promotion": True,
        }
        payload["record"] = record
        return payload

    monkeypatch.setattr(
        program_workflow,
        "write_program_oracle_publication_receipt",
        _tampered_writer,
    )

    with pytest.raises(ValueError, match="planned_record: non_authority"):
        run_program_loop_from_intent_path(
            intent_path,
            outdir=outdir,
            publish_to_shared="retained",
            publisher_id="pi-test",
            publisher_role="operator",
            publisher_assertion="share synthetic behavior evidence for future Oracle retrieval",
            redaction_status="checked",
            retention_class="retained_behavior_memory",
            shared_publication_store=cast(CoordinateStore, store),
        )

    state_path = outdir / "program_candidate_state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["shared_oracle_publication"]["preflight_ready"] is True
    assert state["shared_oracle_publication"]["evidence_ref_present"] is False
    assert len(store.records) == 1
    assert not (outdir / "program_loop.json").exists()


def test_program_loop_cli_publish_to_shared_fails_closed_without_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    monkeypatch.delenv("DSPX_ORACLE_STORE", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DSPX_ORACLE_POSTGRES_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--publish-to-shared",
            "retained",
            "--publisher-id",
            "pi-test",
            "--publisher-role",
            "operator",
            "--publisher-assertion",
            "share synthetic behavior evidence for future Oracle retrieval",
            "--redaction-status",
            "checked",
            "--retention-class",
            "retained_behavior_memory",
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "configured and available Postgres/pgvector Oracle backend" in result.output
    assert not (outdir / "program_oracle_publication_receipt.json").exists()
    assert not (outdir / "program_loop.json").exists()


def test_program_loop_publish_to_shared_requires_publisher_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    _write_intent(intent_path)

    outdir = tmp_path / "candidate"
    with pytest.raises(ValueError, match="publisher_id is required"):
        run_program_loop_from_intent_path(
            intent_path,
            outdir=outdir,
            publish_to_shared="retained",
            publisher_role="operator",
            publisher_assertion="share synthetic behavior evidence",
            redaction_status="checked",
            retention_class="retained_behavior_memory",
            shared_publication_store=cast(CoordinateStore, FakeSharedOracleStore()),
        )
    assert not outdir.exists()


def test_program_loop_rejects_output_path_overwriting_candidate_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)

    with pytest.raises(ValueError, match="state_out must not overwrite manifest.json"):
        run_program_loop_from_intent_path(
            intent_path,
            outdir=outdir,
            state_out=outdir / "manifest.json",
        )
    assert not outdir.exists()


def test_program_loop_rejects_output_path_overwriting_program_py_before_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--skip-oracle-index",
            "--state-out",
            str(outdir / "program.py"),
        ],
    )

    assert result.exit_code == 2
    assert "state_out must not overwrite program.py" in result.output
    assert not outdir.exists()


def test_program_loop_rejects_oracle_index_sidecar_output_collision_before_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    shared = tmp_path / "shared.db"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--index-path",
            str(shared),
            "--oracle-report-out",
            str(shared),
        ],
    )

    assert result.exit_code == 2
    assert "duplicates sidecar output path" in result.output
    assert not outdir.exists()
    assert not shared.exists()


def test_program_loop_rejects_duplicate_sidecar_output_paths_before_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    shared = tmp_path / "shared.json"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--oracle-report-out",
            str(shared),
            "--state-out",
            str(shared),
        ],
    )

    assert result.exit_code == 2
    assert "duplicates sidecar output path" in result.output
    assert not outdir.exists()
    assert not shared.exists()


def test_program_loop_rejects_sidecar_parent_child_collision_before_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    shared_dir = tmp_path / "sidecars"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--skip-oracle-index",
            "--state-out",
            str(shared_dir / "state.json"),
            "--workflow-out",
            str(shared_dir),
        ],
    )

    assert result.exit_code == 2
    assert "conflicts with sidecar output path" in result.output
    assert not outdir.exists()
    assert not shared_dir.exists()


def test_program_loop_rejects_index_path_parent_child_collision_before_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    index_dir = tmp_path / "index"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--workflow-out",
            str(index_dir),
            "--index-path",
            str(index_dir / "coordinates.db"),
        ],
    )

    assert result.exit_code == 2
    assert "conflicts with sidecar output path" in result.output
    assert not outdir.exists()
    assert not index_dir.exists()


def test_program_loop_rejects_workflow_out_equal_to_outdir_before_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--skip-oracle-index",
            "--workflow-out",
            str(outdir),
        ],
    )

    assert result.exit_code == 2
    assert (
        "workflow_out output path collides with generated program output directory"
        in result.output
    )
    assert not outdir.exists()


def test_program_loop_rejects_workflow_out_equal_to_future_oracle_dir_before_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _loop_env(tmp_path, monkeypatch)
    intent_path = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent_path)

    result = runner.invoke(
        app,
        [
            "program-loop",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--workflow-out",
            str(outdir / "oracle"),
        ],
    )

    assert result.exit_code == 2
    assert (
        "workflow_out output path collides with generated program output directory"
        in result.output
    )
    assert not outdir.exists()
