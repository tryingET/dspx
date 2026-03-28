from __future__ import annotations

from pathlib import Path
import json
import subprocess

from typer.testing import CliRunner

import dspx.cli.utils as dspx_utils
from dspx.cli.dspx import app
from dspx.run_receipts import (
    _capture_git_dirty,
    build_run_receipt,
    current_receipt_lineage,
    load_run_receipt,
    normalize_receipt_provenance,
    resolve_receipt_provenance,
    resolve_receipt_run_id,
    resolve_run_identity,
    write_run_receipt,
)


runner = CliRunner()


def _end_active_mlflow_runs() -> None:
    try:
        import mlflow
    except Exception:
        return

    try:
        active_run = getattr(mlflow, "active_run", None)
        end_run = getattr(mlflow, "end_run", None)
        if not callable(active_run) or not callable(end_run):
            return
        while active_run() is not None:
            end_run()
    except Exception:
        pass


def _generate_signature_receipt(
    tmp_path: Path, monkeypatch, *, output_name: str
) -> Path:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / output_name
    result = runner.invoke(
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
    assert result.exit_code == 0
    return tmp_path / f"{output_name}.meta.json"


def test_capture_git_dirty_includes_untracked_files(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "pi@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Pi"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "tracked.txt").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "untracked.txt").write_text("drift\n", encoding="utf-8")

    monkeypatch.chdir(repo)

    assert _capture_git_dirty() is True


def test_run_receipt_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    receipt = build_run_receipt(
        run_kind="unit-test",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=str(tmp_path / "cache" / "x.json"),
        cache_enabled=True,
        replay_inputs={"x": 1, "y": [1, 2]},
        run_summary={"ok": True},
        extra={"label": "demo"},
    )
    meta_path = write_run_receipt(out, receipt)
    loaded = load_run_receipt(meta_path)

    assert loaded is not None
    assert loaded["receipt_version"] == "v2"  # Bumped for Phase C+ fields
    assert loaded["run_kind"] == "unit-test"
    assert loaded["hash"] == "abc123"
    assert loaded["cache_key"] == "k1"
    assert loaded["label"] == "demo"
    assert loaded["replay_inputs"]["x"] == 1
    # Phase C+: execution_context is captured by default
    assert "execution_context" in loaded
    assert "python_version" in loaded["execution_context"]


def test_cli_meta_receipts_are_versioned(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    sig_out = tmp_path / "sig.py"
    r_sig = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(sig_out),
        ],
    )
    assert r_sig.exit_code == 0
    sig_meta = json.loads((tmp_path / "sig.py.meta.json").read_text(encoding="utf-8"))
    assert sig_meta["receipt_version"] == "v2"  # Bumped for Phase C+ fields
    assert sig_meta["run_kind"] == "signature-gen"
    assert sig_meta["output_path"] == str(sig_out)
    assert isinstance(sig_meta.get("replay_inputs"), dict)
    assert isinstance(sig_meta.get("mlflow_hints"), dict)
    assert sig_meta["mlflow_hints"]["expected_tags"]["dspx.run_kind"] == "signature-gen"
    # Phase C+: execution context captured by default
    assert "execution_context" in sig_meta

    mod_out = tmp_path / "mod.py"
    r_mod = runner.invoke(
        app,
        [
            "module-gen",
            "--name",
            "Summarizer",
            "--description",
            "Summarizes text",
            "--input",
            "text",
            "--output",
            "summary",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(mod_out),
        ],
    )
    assert r_mod.exit_code == 0
    mod_meta = json.loads((tmp_path / "mod.py.meta.json").read_text(encoding="utf-8"))
    assert mod_meta["receipt_version"] == "v2"
    assert mod_meta["run_kind"] == "module-gen"
    assert isinstance(mod_meta.get("mlflow_hints"), dict)
    assert mod_meta["mlflow_hints"]["expected_tags"]["dspx.run_kind"] == "module-gen"
    assert mod_meta["run_summary"]["backend"] == "synthesis_runtime"
    assert mod_meta["run_summary"]["candidate_count"] >= 2
    assert mod_meta["run_summary"]["selected_candidate_rank"] == 1
    assert mod_meta["run_summary"]["validation_pass_rate"] == 1.0
    assert mod_meta["run_summary"]["smoke_pass_rate"] == 1.0
    assert isinstance(mod_meta.get("synthesis"), dict)
    assert mod_meta["synthesis_request_id"].startswith("sreq-")
    assert len(mod_meta["synthesis_candidate_ids"]) >= 2
    assert mod_meta["synthesis_evaluation_ids"]
    assert (
        mod_meta["synthesis_selection_policy"]["policy_id"]
        == "module.v7.multi-candidate-ranked"
    )
    assert isinstance(mod_meta.get("synthesis_ranked_candidates"), list)
    assert mod_meta["synthesis_ranked_candidates"][0]["rank"] == 1
    assert mod_meta["synthesis_promotion_shell"]["status"] == "promoted"
    assert mod_meta["synthesis_promotion_decision"]["outcome"] == "promoted"
    diagnostics = mod_meta["synthesis_diagnostics"]
    assert diagnostics["evidence_bundle_version"] == "v1"
    assert diagnostics["retrieval_status"] == "ok"
    assert diagnostics["evidence_summary"] == {
        "exact_match_receipt_count": 0,
        "positive_evidence_count": 0,
        "oracle_neighbor_count": 0,
        "oracle_index_available": False,
        "oracle_lookup_status": "missing",
        "receipt_scan_error_count": 0,
    }
    assert diagnostics["evidence_bundle"]["request"]["name"] == "Summarizer"
    assert diagnostics["evidence_bundle"]["request"]["use_signature"] is False
    assert diagnostics["historical_convergence_advisory"]["status"] == "no_history"
    assert diagnostics["candidate_winner_priors"]["candidate_prior_version"] == "v1"
    assert diagnostics["candidate_prior_audit"]["candidate_prior_audit_version"] == "v1"
    assert (
        diagnostics["candidate_prior_audit"]["status"] == "no_positive_prior_candidates"
    )
    assert (
        diagnostics["candidate_prior_divergence_explanation"][
            "candidate_prior_divergence_explanation_version"
        ]
        == "v1"
    )
    assert (
        diagnostics["candidate_prior_divergence_explanation"]["status"]
        == "no_divergence_to_explain"
    )
    assert (
        diagnostics["candidate_prior_readiness_advisory"][
            "candidate_prior_readiness_advisory_version"
        ]
        == "v1"
    )
    assert (
        diagnostics["candidate_prior_readiness_advisory"]["status"]
        == "insufficient_prior_history"
    )
    assert (
        diagnostics["candidate_winner_priors"]["history_summary"]["candidate_count"]
        >= 2
    )
    assert {
        item["status"]
        for item in diagnostics["candidate_winner_priors"]["candidate_priors"]
    } == {"no_positive_winner_history"}

    mod_again_out = tmp_path / "mod-again.py"
    r_mod_again = runner.invoke(
        app,
        [
            "module-gen",
            "--name",
            "Summarizer",
            "--description",
            "Summarizes text",
            "--input",
            "text",
            "--output",
            "summary",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(mod_again_out),
        ],
    )
    assert r_mod_again.exit_code == 0
    mod_again_meta = json.loads(
        (tmp_path / "mod-again.py.meta.json").read_text(encoding="utf-8")
    )
    followup_diagnostics = mod_again_meta["synthesis_diagnostics"]
    assert followup_diagnostics["evidence_summary"]["exact_match_receipt_count"] == 1
    assert followup_diagnostics["evidence_summary"]["positive_evidence_count"] == 1
    assert followup_diagnostics["evidence_summary"]["oracle_lookup_status"] == "missing"
    assert followup_diagnostics["historical_convergence_advisory"]["status"] == (
        "convergent_with_positive_history"
    )
    assert (
        followup_diagnostics["candidate_prior_audit"]["status"]
        == "selected_matches_positive_winner_history"
    )
    assert (
        followup_diagnostics["candidate_prior_divergence_explanation"]["status"]
        == "no_divergence_to_explain"
    )
    assert (
        followup_diagnostics["candidate_prior_readiness_advisory"]["status"]
        == "insufficient_prior_history"
    )
    prior_receipt = followup_diagnostics["evidence_bundle"]["exact_match_receipts"][0]
    assert Path(prior_receipt["receipt"]["receipt_path"]).name == "mod.py.meta.json"
    assert prior_receipt["positive_evidence"] is True
    assert (
        followup_diagnostics["historical_convergence_advisory"][
            "matching_positive_receipts"
        ][0]["receipt_path"]
        == prior_receipt["receipt"]["receipt_path"]
    )
    priors_by_variant = {
        item["variant_id"]: item
        for item in followup_diagnostics["candidate_winner_priors"]["candidate_priors"]
    }
    assert (
        priors_by_variant["explainable_helpers"]["status"]
        == "matches_positive_winner_history"
    )
    assert priors_by_variant["baseline"]["status"] == "no_positive_winner_history"
    assert priors_by_variant["traceable"]["status"] == "no_positive_winner_history"
    assert (
        priors_by_variant["explainable_helpers"]["matching_positive_receipts"][0][
            "receipt_path"
        ]
        == prior_receipt["receipt"]["receipt_path"]
    )
    assert (
        followup_diagnostics["candidate_prior_audit"]["history_summary"][
            "positive_prior_candidate_count"
        ]
        == 1
    )
    assert (
        followup_diagnostics["candidate_prior_audit"]["positive_prior_candidates"][0][
            "candidate_id"
        ]
        == mod_again_meta["run_summary"]["selected_candidate_id"]
    )

    gen_out = tmp_path / "gen.py"
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
            str(gen_out),
        ],
    )
    assert r_gen.exit_code == 0
    gen_meta = json.loads((tmp_path / "gen.py.meta.json").read_text(encoding="utf-8"))
    assert gen_meta["receipt_version"] == "v2"
    assert gen_meta["run_kind"] == "codegen"
    assert isinstance(gen_meta.get("mlflow_hints"), dict)
    assert gen_meta["mlflow_hints"]["expected_tags"]["dspx.run_kind"] == "codegen"

    refine_out = tmp_path / "refined.py"
    r_refine = runner.invoke(
        app,
        [
            "signature",
            "refine",
            "Extract names from text",
            "--attempts",
            "1",
            "--outfile",
            str(refine_out),
        ],
    )
    assert r_refine.exit_code == 0
    refine_meta = json.loads(
        (tmp_path / "refined.py.meta.json").read_text(encoding="utf-8")
    )
    assert refine_meta["receipt_version"] == "v2"
    assert refine_meta["run_kind"] == "signature-refine"
    assert isinstance(refine_meta.get("mlflow_hints"), dict)
    assert (
        refine_meta["mlflow_hints"]["expected_tags"]["dspx.run_kind"]
        == "signature-refine"
    )


def test_run_replay_check_only_passes_and_is_local(tmp_path: Path, monkeypatch) -> None:
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
        raise AssertionError("run replay must not bootstrap MLflow")

    monkeypatch.setattr(dspx_utils, "enable_mlflow_from_env", _boom)
    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "sig.py.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert r_replay.exit_code == 0, r_replay.stdout
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "ok"
    assert payload["checks"]["output_hash_match"] is True
    assert payload["checks"]["cache_key_recomputes"] is True
    assert payload["error_codes"] == []


def test_run_replay_check_only_is_stable_without_parent_lineage_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path,
        monkeypatch,
        output_name="sig-lineage-none.py",
    )
    receipt = json.loads(meta_path.read_text(encoding="utf-8"))

    assert isinstance(receipt.get("branch"), str)
    assert "parent_run_id" not in receipt
    assert "causal_chain" not in receipt

    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(meta_path),
            "--check-only",
            "--json",
        ],
    )

    assert r_replay.exit_code == 0, r_replay.stdout
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "ok"
    assert payload["checks"]["output_hash_match"] is True
    assert payload["error_codes"] == []
    assert all("lineage" not in str(w) for w in payload["warnings"])


def test_run_replay_fails_on_output_hash_drift(tmp_path: Path, monkeypatch) -> None:
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

    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "gen.py.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert r_replay.exit_code == 1
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "failed"
    assert payload["checks"]["output_hash_match"] is False
    assert "output_hash_mismatch" in payload["error_codes"]
    assert any(
        d.get("code") == "output_hash_mismatch"
        and d.get("check") == "output_hash_match"
        for d in payload["error_details"]
    )


def test_run_replay_fails_on_cache_provenance_drift(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "mod.py"
    r_gen = runner.invoke(
        app,
        [
            "module-gen",
            "--name",
            "Summarizer",
            "--description",
            "Summarizes text",
            "--input",
            "text",
            "--output",
            "summary",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    receipt = json.loads((tmp_path / "mod.py.meta.json").read_text(encoding="utf-8"))
    cache_file = Path(str(receipt["cache_file"]))
    cache_payload = json.loads(cache_file.read_text(encoding="utf-8"))
    cache_payload["code"] = "print('cache drift')\n"
    cache_file.write_text(json.dumps(cache_payload), encoding="utf-8")

    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "mod.py.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert r_replay.exit_code == 1
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "failed"
    assert payload["checks"]["cache_code_hash_matches_receipt"] is False
    assert "cache_code_hash_mismatch" in payload["error_codes"]
    assert any(
        d.get("code") == "cache_code_hash_mismatch"
        and d.get("check") == "cache_code_hash_matches_receipt"
        for d in payload["error_details"]
    )


def test_run_replay_fails_on_missing_cache_file(tmp_path: Path, monkeypatch) -> None:
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

    receipt = json.loads((tmp_path / "sig.py.meta.json").read_text(encoding="utf-8"))
    cache_file = Path(str(receipt["cache_file"]))
    assert cache_file.exists()
    cache_file.unlink()

    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "sig.py.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert r_replay.exit_code == 1
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "failed"
    assert payload["checks"]["cache_file_exists"] is False
    assert "cache_file_missing" in payload["error_codes"]
    assert any(
        d.get("code") == "cache_file_missing" and d.get("check") == "cache_file_exists"
        for d in payload["error_details"]
    )


def test_run_replay_fails_on_wrong_cache_kind_folder(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "mod.py"
    r_gen = runner.invoke(
        app,
        [
            "module-gen",
            "--name",
            "Summarizer",
            "--description",
            "Summarizes text",
            "--input",
            "text",
            "--output",
            "summary",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    meta_path = tmp_path / "mod.py.meta.json"
    receipt = json.loads(meta_path.read_text(encoding="utf-8"))
    cache_file = Path(str(receipt["cache_file"]))
    wrong_cache_file = cache_file.parent.parent / "signature" / cache_file.name
    wrong_cache_file.parent.mkdir(parents=True, exist_ok=True)
    wrong_cache_file.write_text(
        cache_file.read_text(encoding="utf-8"), encoding="utf-8"
    )
    receipt["cache_file"] = str(wrong_cache_file)
    meta_path.write_text(json.dumps(receipt), encoding="utf-8")

    r_replay = runner.invoke(
        app,
        ["run", "replay", "--from", str(meta_path), "--check-only", "--json"],
    )
    assert r_replay.exit_code == 1
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "failed"
    assert payload["checks"]["cache_kind_matches_run_kind"] is False
    assert payload["checks"]["cache_file_exists"] is True
    assert "cache_linkage_kind_mismatch" in payload["error_codes"]
    assert any(
        d.get("code") == "cache_linkage_kind_mismatch"
        and d.get("check") == "cache_kind_matches_run_kind"
        for d in payload["error_details"]
    )


def test_run_replay_fails_on_malformed_cache_json(tmp_path: Path, monkeypatch) -> None:
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

    receipt = json.loads((tmp_path / "gen.py.meta.json").read_text(encoding="utf-8"))
    cache_file = Path(str(receipt["cache_file"]))
    cache_file.write_text("{ malformed", encoding="utf-8")

    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "gen.py.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert r_replay.exit_code == 1
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "failed"
    assert payload["checks"]["cache_file_json_object"] is False
    assert "cache_file_invalid_json_object" in payload["error_codes"]
    assert any(
        d.get("code") == "cache_file_invalid_json_object"
        and d.get("check") == "cache_file_json_object"
        for d in payload["error_details"]
    )


def test_run_replay_invalid_receipt_exit_code(tmp_path: Path) -> None:
    bad_meta = tmp_path / "bad.meta.json"
    bad_meta.write_text('{"receipt_version":"v1"}\n', encoding="utf-8")

    r_replay = runner.invoke(
        app,
        ["run", "replay", "--from", str(bad_meta), "--check-only", "--json"],
    )
    assert r_replay.exit_code == 2
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "invalid"
    assert "receipt_missing_required_field" in payload["error_codes"]
    assert any(
        d.get("code") == "receipt_missing_required_field"
        for d in payload["error_details"]
    )


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


# =============================================================================
# Phase C+ Tests (Time Travel / Dreaming / Consciousness)
# =============================================================================


def test_run_receipt_phase_c_causal_chain(tmp_path: Path) -> None:
    """Test causal chain for Time Travel behavioral lineage."""
    from dspx.run_receipts import build_causal_chain, extend_causal_chain

    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    # Build receipt with causal chain
    receipt = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        causal_chain=["sig-run-001", "refine-run-002"],
        parent_run_id="sig-run-001",
        branch="feature-x",
    )

    assert receipt["causal_chain"] == ["sig-run-001", "refine-run-002"]
    assert receipt["parent_run_id"] == "sig-run-001"
    assert receipt["branch"] == "feature-x"

    # Test helper functions
    chain = build_causal_chain("a", "b", "a", "c")  # dedup
    assert chain == ["a", "b", "c"]

    extended = extend_causal_chain(["x", "y"], "z")
    assert extended == ["x", "y", "z"]

    # Test max depth
    long_chain = extend_causal_chain(
        list("abcdefghijklmnopqrstuvwxyz"), "new", max_depth=10
    )
    assert len(long_chain) == 10
    assert long_chain[-1] == "new"


def test_run_receipt_phase_c_dreaming_fields(tmp_path: Path) -> None:
    """Test outcome/latency/tokens fields for Dreaming simulation."""
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    receipt = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        outcome="success",
        latency_ms=1234.5,
        tokens_used=1500,
        tokens_prompt=1000,
        tokens_completion=500,
    )

    assert receipt["outcome"] == "success"
    assert receipt["latency_ms"] == 1234.5
    assert receipt["tokens_used"] == 1500
    assert receipt["tokens_prompt"] == 1000
    assert receipt["tokens_completion"] == 500


def test_run_receipt_phase_c_execution_context(tmp_path: Path) -> None:
    """Test execution context capture for Consciousness."""
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    # With context capture (default)
    receipt = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        capture_context=True,
    )

    assert "execution_context" in receipt
    ctx = receipt["execution_context"]
    assert "python_version" in ctx
    assert "platform" in ctx
    # git_commit may or may not be present depending on environment

    # Without context capture
    receipt_no_ctx = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        capture_context=False,
    )

    assert "execution_context" not in receipt_no_ctx


def test_run_receipt_execution_context_hash_tracks_env_value_changes(
    tmp_path: Path, monkeypatch
) -> None:
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    receipt_a = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        capture_context=True,
    )

    monkeypatch.setenv("DSPX_PROVIDER", "pi-rpc")
    receipt_b = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        capture_context=True,
    )

    assert (
        receipt_a["execution_context"]["env_hash"]
        != receipt_b["execution_context"]["env_hash"]
    )


def test_resolve_run_identity_exposes_contract_facets() -> None:
    receipt = {
        "execution_id": "exec-123",
        "run_id": "mlflow-456",
        "cache_key": "cache-789",
        "hash": "hash-abc",
        "output_path": "/tmp/out.py",
    }

    identity = resolve_run_identity(receipt)

    assert identity.canonical_id == "exec-123"
    assert identity.canonical_source == "execution_id"
    assert identity.behavioral_id == "mlflow-456"
    assert identity.behavioral_source == "run_id"
    assert identity.storage_id == "exec-123"
    assert identity.storage_source == "execution_id"
    assert identity.alias_ids == (
        "exec-123",
        "mlflow-456",
        "cache-789",
        "hash-abc",
        "/tmp/out.py",
    )


def test_normalize_receipt_provenance_prefers_canonical_identity_fields() -> None:
    receipt = {
        "execution_id": "exec-123",
        "run_id": "mlflow-456",
        "cache_key": "cache-789",
        "hash": "hash-abc",
        "output_path": "/tmp/out.py",
        "branch": "feature-a",
        "parent_run_id": "parent-1",
        "causal_chain": ["root-1", "parent-1", "root-1"],
    }

    provenance = normalize_receipt_provenance(receipt)

    assert provenance["run_id"] == "exec-123"
    assert provenance["branch"] == "feature-a"
    assert provenance["parent_run_id"] == "parent-1"
    assert provenance["causal_chain"] == ["root-1", "parent-1"]
    assert provenance["lineage_ids"] == ["root-1", "parent-1"]
    assert provenance["identity"]["canonical_source"] == "execution_id"
    assert provenance["warnings"] == ["causal_chain:deduplicated_items=1"]


def test_resolve_receipt_provenance_ignores_non_string_lineage_items() -> None:
    receipt = {
        "execution_id": "exec-123",
        "parent_run_id": 42,
        "causal_chain": ["root-1", None, 123, "", "root-1"],
    }

    provenance = resolve_receipt_provenance(receipt)

    assert provenance.run_id == "exec-123"
    assert provenance.parent_run_id is None
    assert provenance.causal_chain == ("root-1",)
    assert provenance.lineage_ids == ("root-1",)
    assert provenance.warnings == (
        "parent_run_id:ignored_invalid_value",
        "causal_chain:ignored_non_string_items=2",
        "causal_chain:ignored_blank_items=1",
        "causal_chain:deduplicated_items=1",
    )


def test_resolve_receipt_run_id_prefers_legacy_ids_before_output_path() -> None:
    receipt = {
        "output_path": "/repo/generated/same.py",
        "cache_key": "cache-left",
        "hash": "hash-left",
    }

    assert resolve_receipt_run_id(receipt) == "cache-left"


def test_current_receipt_lineage_appends_parent_to_causal_chain(monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CAUSAL_CHAIN", '["root-1"]')

    lineage = current_receipt_lineage(parent_run_id="parent-1", branch="feature-a")

    assert lineage == {
        "branch": "feature-a",
        "parent_run_id": "parent-1",
        "causal_chain": ["root-1", "parent-1"],
    }


def test_current_receipt_lineage_allows_explicit_empty_chain_override(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DSPX_CAUSAL_CHAIN", '["root-1"]')

    lineage = current_receipt_lineage(causal_chain=[], branch="feature-a")

    assert lineage == {"branch": "feature-a"}


def test_cli_generated_receipt_includes_execution_id_and_branch(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_RECEIPT_BRANCH", "feature-receipt")

    out = tmp_path / "sig.py"
    result = runner.invoke(
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
    assert result.exit_code == 0

    receipt = json.loads((tmp_path / "sig.py.meta.json").read_text(encoding="utf-8"))
    assert receipt["branch"] == "feature-receipt"
    assert isinstance(receipt.get("execution_id"), str)
    assert receipt["execution_id"]


def test_run_receipt_phase_c_defaults_omit_empty_fields(tmp_path: Path) -> None:
    """Test that default/empty Phase C+ fields are omitted from receipt."""
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    receipt = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        # All Phase C+ fields left as defaults
    )

    # These should NOT be in the receipt when using defaults
    assert "causal_chain" not in receipt
    assert "parent_run_id" not in receipt
    assert "branch" not in receipt
    assert "outcome" not in receipt  # "unknown" is default, omitted
    assert "latency_ms" not in receipt
    assert "tokens_used" not in receipt
    assert "tokens_prompt" not in receipt
    assert "tokens_completion" not in receipt

    # But execution_context IS captured by default
    assert "execution_context" in receipt


def test_module_receipts_use_canonical_default_oracle_index_with_outfile(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_MODULE_SYNTHESIS_QUALITY_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")

    first_out = tmp_path / "first.py"
    first = runner.invoke(
        app,
        [
            "module-gen",
            "--name",
            "Summarizer",
            "--description",
            "Summarizes text",
            "--input",
            "text",
            "--output",
            "summary",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(first_out),
        ],
    )
    assert first.exit_code == 0

    from dspx.coordinates import CoordinateIndex, get_embedding_engine

    first_meta_path = tmp_path / "first.py.meta.json"
    first_receipt = load_run_receipt(first_meta_path)
    assert isinstance(first_receipt, dict)
    embedding = get_embedding_engine().embed_receipt(
        first_receipt,
        receipt_path=first_meta_path,
    )
    assert embedding is not None
    oracle_index = tmp_path / "generated" / "oracle" / "coordinates.db"
    CoordinateIndex(db_path=oracle_index).upsert(embedding)

    second_out = tmp_path / "second.py"
    second = runner.invoke(
        app,
        [
            "module-gen",
            "--name",
            "Summarizer",
            "--description",
            "Summarizes text",
            "--input",
            "text",
            "--output",
            "summary",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(second_out),
        ],
    )
    assert second.exit_code == 0

    second_meta = json.loads((tmp_path / "second.py.meta.json").read_text())
    diagnostics = second_meta["synthesis_diagnostics"]
    assert diagnostics["evidence_summary"]["oracle_index_available"] is True
    assert diagnostics["evidence_summary"]["oracle_lookup_status"] == "available"
    assert diagnostics["evidence_summary"]["oracle_neighbor_count"] >= 1
    assert diagnostics["evidence_bundle"]["oracle_index_path"] == str(oracle_index)


def test_module_receipts_align_default_oracle_index_with_outfile_root_when_cwd_differs(
    tmp_path: Path, monkeypatch
) -> None:
    cwd = tmp_path / "cwd-root"
    out_root = tmp_path / "out-root"
    cwd.mkdir(parents=True, exist_ok=True)
    out_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(cwd)
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(cwd / "cache"))
    monkeypatch.setenv("DSPX_MODULE_SYNTHESIS_QUALITY_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")

    first_out = out_root / "first.py"
    first = runner.invoke(
        app,
        [
            "module-gen",
            "--name",
            "Summarizer",
            "--description",
            "Summarizes text",
            "--input",
            "text",
            "--output",
            "summary",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(first_out),
        ],
    )
    assert first.exit_code == 0

    from dspx.coordinates import CoordinateIndex, get_embedding_engine

    first_meta_path = out_root / "first.py.meta.json"
    first_receipt = load_run_receipt(first_meta_path)
    assert isinstance(first_receipt, dict)
    embedding = get_embedding_engine().embed_receipt(
        first_receipt,
        receipt_path=first_meta_path,
    )
    assert embedding is not None
    oracle_index = out_root / "generated" / "oracle" / "coordinates.db"
    CoordinateIndex(db_path=oracle_index).upsert(embedding)

    second_out = out_root / "second.py"
    second = runner.invoke(
        app,
        [
            "module-gen",
            "--name",
            "Summarizer",
            "--description",
            "Summarizes text",
            "--input",
            "text",
            "--output",
            "summary",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(second_out),
        ],
    )
    assert second.exit_code == 0

    second_meta = json.loads((out_root / "second.py.meta.json").read_text())
    diagnostics = second_meta["synthesis_diagnostics"]
    assert diagnostics["evidence_bundle"]["receipts_path"] == str(out_root)
    assert diagnostics["evidence_bundle"]["oracle_index_path"] == str(oracle_index)
    assert diagnostics["evidence_summary"]["oracle_lookup_status"] == "available"
    assert diagnostics["evidence_summary"]["oracle_neighbor_count"] >= 1
