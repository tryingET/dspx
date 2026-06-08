from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

import dspx.cli.utils as dspx_utils
from dspx.cli.dspx import app
from run_receipts_helpers import (
    _end_active_mlflow_runs,
    _generate_signature_receipt,
    _setup_sqlite_mlflow,
    _write_fake_local_mlflow_run,
    _write_sqlite_mlflow_run,
    runner,
)


@pytest.mark.slow
def test_run_explain_local_first_without_mlflow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "sig.py"
    r_gen = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    def _boom() -> bool:
        raise AssertionError("run explain must not bootstrap MLflow by default")

    monkeypatch.setattr(dspx_utils, "enable_mlflow_from_env", _boom)
    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(tmp_path / "sig.py.meta.json"),
            "--json",
        ],
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    assert payload["status"] == "ok"
    assert payload["replay_status"] == "ok"
    assert payload["local_facts"]["run_kind"] == "signature-gen"
    assert payload["replay_checks"]["output_hash_match"] is True
    assert payload["replay_error_codes"] == []
    assert payload["replay_error_details"] == []
    assert payload["mlflow_context"]["requested"] is False
    assert payload["mlflow_context"]["mode"] == "disabled"
    assert payload["mlflow_context"]["lookup_mode"] == "disabled"
    assert payload["mlflow_context"]["reason_code_version"] == "v1"
    assert payload["mlflow_context"]["degrade_reason_codes"] == []


@pytest.mark.slow
def test_run_explain_with_mlflow_requires_explicit_tracking_uri(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "sig.py"
    r_gen = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(tmp_path / "sig.py.meta.json"),
            "--with-mlflow",
            "--json",
        ],
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    ctx = payload["mlflow_context"]
    assert ctx["requested"] is True
    assert ctx["mode"] == "unconfigured"
    assert ctx["lookup_mode"] == "disabled"
    assert ctx["tracking_uri"] == ""
    assert ctx["degrade_reason_codes"] == ["mlflow_tracking_uri_missing"]
    assert not (tmp_path / "mlflow.db").exists()
    assert not (tmp_path / "mlruns").exists()


def test_run_explain_mlflow_context_redacts_tracking_uri_secrets(
    tmp_path: Path, monkeypatch
) -> None:
    from dspx.services.run_explain_service import _mlflow_context

    monkeypatch.setenv(
        "MLFLOW_TRACKING_URI",
        "https://user:super-secret-token@mlflow.example/path?token=super-secret-token",
    )

    context = _mlflow_context(
        meta_path=tmp_path / "sig.py.meta.json",
        receipt={"run_kind": "codegen"},
        with_mlflow=True,
        mlflow_remote_lookup=False,
    )

    assert context["mode"] == "remote-uri"
    assert context["tracking_uri"] == (
        "https://[REDACTED]@mlflow.example/path?token=[REDACTED]"
    )
    assert "super-secret-token" not in repr(context)


@pytest.mark.slow
def test_run_explain_is_stable_with_partial_lineage_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path,
        monkeypatch,
        output_name="sig-lineage-partial.py",
    )
    receipt = json.loads(meta_path.read_text(encoding="utf-8"))
    receipt["branch"] = "feature-partial"
    receipt["parent_run_id"] = "missing-parent"
    receipt["causal_chain"] = ["missing-parent", "merge-base-001", "missing-parent"]
    meta_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(meta_path),
            "--json",
        ],
    )

    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    assert payload["status"] == "ok"
    assert payload["replay_status"] == "ok"
    assert payload["replay_error_codes"] == []
    assert payload["local_facts"]["run_kind"] == "signature-gen"
    assert payload["local_facts"]["output_path"].endswith("sig-lineage-partial.py")
    assert payload["local_facts"]["failed_replay_checks"] == []
    assert "branch" not in payload["local_facts"]
    assert all("lineage" not in str(w) for w in payload["warnings"])


@pytest.mark.slow
def test_run_explain_degraded_status_on_drift(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "gen.py"
    r_gen = runner.invoke(
        app,
        [
            "codegen",
            "A CLI that prints hi",
            "--language",
            "python",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    out.write_text("print('drift')\n", encoding="utf-8")

    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(tmp_path / "gen.py.meta.json"),
            "--json",
        ],
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    assert payload["status"] == "degraded"
    assert payload["replay_status"] == "failed"
    assert payload["replay_checks"]["output_hash_match"] is False
    assert "output_hash_match" in payload["local_facts"]["failed_replay_checks"]
    assert "output_hash_mismatch" in payload["replay_error_codes"]
    assert any(
        d.get("code") == "output_hash_mismatch"
        and d.get("check") == "output_hash_match"
        for d in payload["replay_error_details"]
    )
    assert any(
        "replay verification drift detected" in str(w)
        for w in payload.get("warnings") or []
    )


@pytest.mark.slow
def test_run_explain_with_mlflow_flag_is_graceful(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")

    _end_active_mlflow_runs()
    try:
        out = tmp_path / "gen.py"
        r_gen = runner.invoke(
            app,
            [
                "codegen",
                "A CLI that prints hi",
                "--language",
                "python",
                "--template-version",
                "simple-v1",
                "--outfile",
                str(out),
            ],
        )
        assert r_gen.exit_code == 0

        r_explain = runner.invoke(
            app,
            [
                "run",
                "explain",
                "--from",
                str(tmp_path / "gen.py.meta.json"),
                "--with-mlflow",
                "--json",
            ],
        )
        assert r_explain.exit_code == 0
        payload = json.loads(r_explain.stdout)
        assert payload["status"] == "ok"
        assert payload["replay_status"] == "ok"
        assert payload["replay_error_codes"] == []
        assert payload["mlflow_context"]["requested"] is True
        assert payload["mlflow_context"]["mode"] == "local-sqlite"
        assert payload["mlflow_context"]["lookup_mode"] == "local-scan"
        assert payload["mlflow_context"]["reason_code_version"] == "v1"
        assert "linked_runs" in payload["mlflow_context"]
    finally:
        _end_active_mlflow_runs()


@pytest.mark.slow
def test_run_explain_with_mlflow_sqlite_custom_artifact_root(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    tracking_db = tmp_path / "tracking" / "mlflow.db"
    tracking_db.parent.mkdir(parents=True, exist_ok=True)
    tracking_uri = f"sqlite:///{tracking_db}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking_uri)

    experiment_name = "DSPxExplainCustomArtifact"
    artifact_root = tmp_path / "mlflow_custom_artifacts"
    monkeypatch.setenv("MLFLOW_EXPERIMENT", experiment_name)

    from mlflow import MlflowClient

    _end_active_mlflow_runs()
    try:
        client = MlflowClient(tracking_uri=tracking_uri)
        try:
            client.create_experiment(
                experiment_name,
                artifact_location=artifact_root.resolve().as_uri(),
            )
        except Exception:
            pass

        out = tmp_path / "gen.py"
        r_gen = runner.invoke(
            app,
            [
                "codegen",
                "A CLI that prints hi",
                "--language",
                "python",
                "--template-version",
                "simple-v1",
                "--outfile",
                str(out),
            ],
        )
        assert r_gen.exit_code == 0

        r_explain = runner.invoke(
            app,
            [
                "run",
                "explain",
                "--from",
                str(tmp_path / "gen.py.meta.json"),
                "--with-mlflow",
                "--json",
            ],
        )
        assert r_explain.exit_code == 0
        payload = json.loads(r_explain.stdout)
        assert payload["status"] == "ok"
        assert payload["mlflow_context"]["mode"] == "local-sqlite"
        assert payload["mlflow_context"]["lookup_mode"] == "local-scan"

        linked_runs = payload["mlflow_context"].get("linked_runs") or []
        assert linked_runs
        assert any(
            str(artifact_root) in str(run.get("artifact_uri") or "")
            for run in linked_runs
        )
    finally:
        _end_active_mlflow_runs()


@pytest.mark.slow
def test_run_explain_local_mlflow_filters_same_artifacts_by_expected_tags(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path,
        monkeypatch,
        output_name="sig.py",
    )
    receipt = json.loads(meta_path.read_text(encoding="utf-8"))
    expected_tags = dict(receipt["mlflow_hints"]["expected_tags"])
    output_path = tmp_path / "sig.py"

    artifact_payloads = {
        "sig.py": output_path.read_text(encoding="utf-8"),
        "sig.py.meta.json": meta_path.read_text(encoding="utf-8"),
    }
    _setup_sqlite_mlflow(
        tmp_path,
        monkeypatch,
        experiment_name="DSPxExplainTagFiltering",
    )
    matching_run_id = _write_sqlite_mlflow_run(
        tmp_path,
        run_name="matching-run",
        artifacts=artifact_payloads,
        tags=expected_tags,
    )
    mismatched_tags = dict(expected_tags)
    mismatched_tags["dspx.output_hash_prefix"] = "deadbeefdead"
    _write_sqlite_mlflow_run(
        tmp_path,
        run_name="mismatched-run",
        artifacts=artifact_payloads,
        tags=mismatched_tags,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", FutureWarning)
        r_explain = runner.invoke(
            app,
            [
                "run",
                "explain",
                "--from",
                str(meta_path),
                "--with-mlflow",
                "--json",
            ],
        )
    assert not any(
        "filesystem tracking backend" in str(item.message) for item in caught
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    linked_runs = payload["mlflow_context"].get("linked_runs") or []
    assert len(linked_runs) == 1
    assert linked_runs[0]["run_id"] == matching_run_id
    assert payload["mlflow_context"]["candidate_count"] == 1
    assert payload["mlflow_context"]["matched_count"] == 1
    assert "mlflow_tag_contract_violation" in (
        payload["mlflow_context"].get("degrade_reason_codes") or []
    )


@pytest.mark.slow
def test_run_explain_local_mlflow_accepts_partial_matching_tags(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path,
        monkeypatch,
        output_name="sig.py",
    )
    receipt = json.loads(meta_path.read_text(encoding="utf-8"))
    expected_tags = dict(receipt["mlflow_hints"]["expected_tags"])
    output_path = tmp_path / "sig.py"

    artifact_payloads = {
        "sig.py": output_path.read_text(encoding="utf-8"),
        "sig.py.meta.json": meta_path.read_text(encoding="utf-8"),
    }
    _setup_sqlite_mlflow(
        tmp_path,
        monkeypatch,
        experiment_name="DSPxExplainPartialTags",
    )
    partial_run_id = _write_sqlite_mlflow_run(
        tmp_path,
        run_name="partial-run",
        artifacts=artifact_payloads,
        tags={"service": expected_tags["service"]},
    )

    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(meta_path),
            "--with-mlflow",
            "--json",
        ],
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    linked_runs = payload["mlflow_context"].get("linked_runs") or []
    assert len(linked_runs) == 1
    assert linked_runs[0]["run_id"] == partial_run_id
    assert payload["mlflow_context"]["candidate_count"] == 1
    assert "mlflow_tag_contract_violation" not in (
        payload["mlflow_context"].get("degrade_reason_codes") or []
    )


@pytest.mark.slow
def test_run_explain_local_mlflow_accepts_nested_artifact_paths(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path,
        monkeypatch,
        output_name="sig.py",
    )
    receipt = json.loads(meta_path.read_text(encoding="utf-8"))
    expected_tags = dict(receipt["mlflow_hints"]["expected_tags"])
    output_path = tmp_path / "sig.py"

    artifact_payloads = {
        "nested/sig.py": output_path.read_text(encoding="utf-8"),
        "nested/sig.py.meta.json": meta_path.read_text(encoding="utf-8"),
    }
    _setup_sqlite_mlflow(
        tmp_path,
        monkeypatch,
        experiment_name="DSPxExplainNestedArtifacts",
    )
    nested_run_id = _write_sqlite_mlflow_run(
        tmp_path,
        run_name="nested-run",
        artifacts=artifact_payloads,
        tags=expected_tags,
    )

    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(meta_path),
            "--with-mlflow",
            "--json",
        ],
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    linked_runs = payload["mlflow_context"].get("linked_runs") or []
    assert len(linked_runs) == 1
    assert linked_runs[0]["run_id"] == nested_run_id
    assert sorted(linked_runs[0]["matched_artifacts"]) == [
        "nested/sig.py",
        "nested/sig.py.meta.json",
    ]
    assert "mlflow_tag_contract_violation" not in (
        payload["mlflow_context"].get("degrade_reason_codes") or []
    )


@pytest.mark.slow
def test_run_explain_rejects_filesystem_tracking_uri_without_linking_runs(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path,
        monkeypatch,
        output_name="sig.py",
    )
    receipt = json.loads(meta_path.read_text(encoding="utf-8"))
    expected_tags = dict(receipt["mlflow_hints"]["expected_tags"])
    tracking_root = tmp_path / "mlruns"
    _write_fake_local_mlflow_run(
        tracking_root,
        experiment_id="0",
        run_id="unsupported-run",
        artifacts={
            "sig.py": (tmp_path / "sig.py").read_text(encoding="utf-8"),
            "sig.py.meta.json": meta_path.read_text(encoding="utf-8"),
        },
        tags=expected_tags,
    )
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking_root.resolve().as_uri())

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", FutureWarning)
        result = runner.invoke(
            app,
            [
                "run",
                "explain",
                "--from",
                str(meta_path),
                "--with-mlflow",
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert not any(
        "filesystem tracking backend" in str(item.message) for item in caught
    )
    payload = json.loads(result.stdout)
    ctx = payload["mlflow_context"]
    assert ctx["mode"] == "unsupported-filesystem-tracking"
    assert ctx["lookup_mode"] == "disabled"
    assert ctx["linked_runs"] == []
    assert ctx["candidate_count"] == 0
    assert ctx["matched_count"] == 0
    assert "mlflow_filesystem_backend_unsupported" in ctx["degrade_reason_codes"]
    assert "unsupported-run" not in json.dumps(ctx)


@pytest.mark.slow
def test_run_explain_rejects_local_path_tracking_uri(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path,
        monkeypatch,
        output_name="sig.py",
    )
    tracking_root = tmp_path / "mlruns"
    tracking_root.mkdir()
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", str(tracking_root))

    result = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(meta_path),
            "--with-mlflow",
            "--json",
        ],
    )

    assert result.exit_code == 0
    ctx = json.loads(result.stdout)["mlflow_context"]
    assert ctx["mode"] == "unsupported-filesystem-tracking"
    assert ctx["lookup_mode"] == "disabled"
    assert ctx["degrade_reason_codes"] == ["mlflow_filesystem_backend_unsupported"]


@pytest.mark.slow
def test_run_explain_remote_uri_default_off_lookup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")

    out = tmp_path / "sig.py"
    r_gen = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")

    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(tmp_path / "sig.py.meta.json"),
            "--with-mlflow",
            "--json",
        ],
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    ctx = payload["mlflow_context"]
    assert ctx["mode"] == "remote-uri"
    assert ctx["lookup_mode"] == "remote-search"
    assert ctx["reason_code_version"] == "v1"
    assert "mlflow_remote_lookup_not_enabled" in (ctx.get("degrade_reason_codes") or [])


@pytest.mark.slow
def test_run_explain_remote_lookup_flag_graceful(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")

    out = tmp_path / "sig.py"
    r_gen = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:1")

    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(tmp_path / "sig.py.meta.json"),
            "--with-mlflow",
            "--mlflow-remote-lookup",
            "--json",
        ],
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    ctx = payload["mlflow_context"]
    assert ctx["mode"] == "remote-uri"
    assert ctx["lookup_mode"] == "remote-search"
    assert ctx["reason_code_version"] == "v1"
    reason_codes = set(ctx.get("degrade_reason_codes") or [])
    assert reason_codes.intersection(
        {
            "mlflow_remote_auth_unavailable",
            "mlflow_remote_search_failed",
            "mlflow_remote_no_candidate",
            "mlflow_remote_time_budget_exceeded",
        }
    )


def test_remote_program_lookup_includes_related_assembly_runs(monkeypatch) -> None:
    import sys
    import types

    from dspx.services.run_explain_service import _remote_search_candidates

    def _run(run_id: str, run_kind: str, *, assembly_id: str = "asm-1"):
        tags = {
            "service": "program",
            "template_version": "program-candidate-assembly-v1",
            "dspx.run_kind": run_kind,
            "dspx.template_version": "program-candidate-assembly-v1",
            "dspx.output_basename": "manifest.json"
            if run_kind == "program-gen"
            else "program.py",
            "program.assembly_id": assembly_id,
            "mlflow.runName": run_kind,
        }
        return types.SimpleNamespace(
            info=types.SimpleNamespace(
                run_id=run_id,
                experiment_id="exp-1",
                status="FINISHED",
                lifecycle_stage="active",
                start_time=1,
                end_time=2,
                artifact_uri=f"mlflow-artifacts:/exp-1/{run_id}/artifacts",
                run_name=run_kind,
            ),
            data=types.SimpleNamespace(tags=tags),
        )

    class _FakeClient:
        def __init__(self, tracking_uri: str) -> None:
            assert tracking_uri == "http://mlflow.example:5000"

        def search_experiments(self, **kwargs):
            return [types.SimpleNamespace(experiment_id="exp-1")]

        def search_runs(self, *, filter_string: str, **kwargs):
            if "tags.program.assembly_id" in filter_string:
                return [
                    _run("eval-1", "program-eval"),
                    _run("runtime-1", "program-runtime"),
                    _run("gen-1", "program-gen"),
                ]
            return [_run("gen-1", "program-gen")]

    mlflow_mod = types.ModuleType("mlflow")
    entities_mod = types.ModuleType("mlflow.entities")
    tracking_mod = types.ModuleType("mlflow.tracking")
    setattr(entities_mod, "ViewType", types.SimpleNamespace(ACTIVE_ONLY="active"))
    setattr(tracking_mod, "MlflowClient", _FakeClient)
    monkeypatch.setitem(sys.modules, "mlflow", mlflow_mod)
    monkeypatch.setitem(sys.modules, "mlflow.entities", entities_mod)
    monkeypatch.setitem(sys.modules, "mlflow.tracking", tracking_mod)

    receipt = {
        "run_kind": "program-gen",
        "template_version": "program-candidate-assembly-v1",
        "output_path": "manifest.json",
        "run_summary": {"assembly_id": "asm-1"},
        "mlflow_hints": {
            "expected_tags": {
                "service": "program",
                "template_version": "program-candidate-assembly-v1",
                "dspx.run_kind": "program-gen",
                "dspx.template_version": "program-candidate-assembly-v1",
                "dspx.output_basename": "manifest.json",
            }
        },
    }

    linked, related, reasons, elapsed_ms = _remote_search_candidates(
        receipt=receipt,
        tracking_uri="http://mlflow.example:5000",
        candidate_cap=10,
        time_budget_ms=3000,
    )

    assert elapsed_ms >= 0
    assert reasons == []
    assert [run["run_id"] for run in linked] == ["gen-1"]
    assert {run["run_kind"] for run in related} == {
        "program-gen",
        "program-runtime",
        "program-eval",
    }
    assert {run["relation"] for run in related} == {"same_program_assembly"}


def test_remote_program_lookup_reports_related_assembly_lookup_failure(
    monkeypatch,
) -> None:
    import sys
    import types

    from dspx.services.run_explain_service import _remote_search_candidates

    def _run(run_id: str, run_kind: str):
        tags = {
            "service": "program",
            "template_version": "program-candidate-assembly-v1",
            "dspx.run_kind": run_kind,
            "dspx.template_version": "program-candidate-assembly-v1",
            "dspx.output_basename": "manifest.json",
            "program.assembly_id": "asm-1",
            "mlflow.runName": run_kind,
        }
        return types.SimpleNamespace(
            info=types.SimpleNamespace(
                run_id=run_id,
                experiment_id="exp-1",
                status="FINISHED",
                lifecycle_stage="active",
                start_time=1,
                end_time=2,
                artifact_uri=f"mlflow-artifacts:/exp-1/{run_id}/artifacts",
                run_name=run_kind,
            ),
            data=types.SimpleNamespace(tags=tags),
        )

    class _FakeClient:
        def __init__(self, tracking_uri: str) -> None:
            assert tracking_uri == "http://mlflow.example:5000"

        def search_experiments(self, **kwargs):
            return [types.SimpleNamespace(experiment_id="exp-1")]

        def search_runs(self, *, filter_string: str, **kwargs):
            if "tags.program.assembly_id" in filter_string:
                raise RuntimeError("related lookup backend unavailable")
            return [_run("gen-1", "program-gen")]

    mlflow_mod = types.ModuleType("mlflow")
    entities_mod = types.ModuleType("mlflow.entities")
    tracking_mod = types.ModuleType("mlflow.tracking")
    setattr(entities_mod, "ViewType", types.SimpleNamespace(ACTIVE_ONLY="active"))
    setattr(tracking_mod, "MlflowClient", _FakeClient)
    monkeypatch.setitem(sys.modules, "mlflow", mlflow_mod)
    monkeypatch.setitem(sys.modules, "mlflow.entities", entities_mod)
    monkeypatch.setitem(sys.modules, "mlflow.tracking", tracking_mod)

    receipt = {
        "run_kind": "program-gen",
        "template_version": "program-candidate-assembly-v1",
        "output_path": "manifest.json",
        "run_summary": {"assembly_id": "asm-1"},
        "mlflow_hints": {
            "expected_tags": {
                "service": "program",
                "template_version": "program-candidate-assembly-v1",
                "dspx.run_kind": "program-gen",
                "dspx.template_version": "program-candidate-assembly-v1",
                "dspx.output_basename": "manifest.json",
            }
        },
    }

    linked, related, reasons, _elapsed_ms = _remote_search_candidates(
        receipt=receipt,
        tracking_uri="http://mlflow.example:5000",
        candidate_cap=10,
        time_budget_ms=3000,
    )

    assert [run["run_id"] for run in linked] == ["gen-1"]
    assert related == []
    assert "mlflow_related_runs_lookup_failed" in reasons


def test_run_explain_invalid_receipt_exit_code(tmp_path: Path) -> None:
    bad_meta = tmp_path / "bad-explain.meta.json"
    bad_meta.write_text('{"receipt_version":"v1"}\n', encoding="utf-8")

    r_explain = runner.invoke(
        app,
        ["run", "explain", "--from", str(bad_meta), "--json"],
    )
    assert r_explain.exit_code == 2
    payload = json.loads(r_explain.stdout)
    assert payload["status"] == "invalid"
    assert payload["replay_status"] == "invalid"
    assert "receipt_missing_required_field" in payload["replay_error_codes"]
    assert any(
        d.get("code") == "receipt_missing_required_field"
        for d in payload["replay_error_details"]
    )
