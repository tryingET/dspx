from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import dspx.cli.utils as dspx_utils
import dspx.services.run_replay_service as replay_service
from dspx.cli.dspx import app
from dspx.cache import make_key
from dspx.run_receipts import (
    _capture_git_dirty,
    build_run_receipt,
    load_run_receipt,
    write_run_receipt,
)
from dspx.services.run_replay_service import check_run_receipt
from run_receipts_helpers import (
    _generate_signature_receipt,
    runner,
)


def test_run_replay_prefers_receipt_relative_paths_over_ambient_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    receipt_dir = tmp_path / "receipt-dir"
    receipt_dir.mkdir()
    actual_output = receipt_dir / "artifact.py"
    actual_output.write_text("print('right')\n", encoding="utf-8")
    (tmp_path / "artifact.py").write_text("print('wrong')\n", encoding="utf-8")

    replay_inputs = {
        "prompt": "Extract names from text",
        "template_version": "simple-v1",
        "options": {},
        "class_name": "GeneratedSignature",
    }
    cache_key = make_key(
        {
            "kind": "signature",
            "prompt": replay_inputs["prompt"],
            "template_version": replay_inputs["template_version"],
            "class_name": replay_inputs["class_name"],
            "options": replay_inputs["options"],
        }
    )
    cache_dir = receipt_dir / "cache" / "signature"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / f"{cache_key}.json"
    cache_file.write_text(
        json.dumps({"code": actual_output.read_text(encoding="utf-8")}),
        encoding="utf-8",
    )

    output_hash = hashlib.sha256(
        actual_output.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()

    receipt = {
        "receipt_version": "v2",
        "created_at": "2026-01-01T00:00:00+00:00",
        "run_kind": "signature-gen",
        "provider": "stub",
        "output_path": "artifact.py",
        "hash": output_hash,
        "template_version": "simple-v1",
        "cache_key": cache_key,
        "cache_file": f"cache/signature/{cache_key}.json",
        "cache_enabled": True,
        "replay_inputs": replay_inputs,
    }
    meta_path = write_run_receipt(actual_output, receipt)

    report = check_run_receipt(meta_path)

    assert report["status"] == "ok"
    assert report["output_path"] == str(actual_output)
    assert report["cache_file"] == str(cache_file)
    assert report["error_codes"] == []


def test_run_replay_rejects_external_absolute_cache_file(tmp_path: Path) -> None:
    receipt_dir = tmp_path / "receipt-dir"
    receipt_dir.mkdir()
    actual_output = receipt_dir / "artifact.py"
    actual_output.write_text("print('right')\n", encoding="utf-8")

    replay_inputs = {
        "prompt": "Extract names from text",
        "template_version": "simple-v1",
        "options": {},
        "class_name": "GeneratedSignature",
    }
    cache_key = make_key(
        {
            "kind": "signature",
            "prompt": replay_inputs["prompt"],
            "template_version": replay_inputs["template_version"],
            "class_name": replay_inputs["class_name"],
            "options": replay_inputs["options"],
        }
    )
    external_cache = tmp_path / "outside-cache" / "signature" / f"{cache_key}.json"
    external_cache.parent.mkdir(parents=True)
    external_cache.write_text(
        json.dumps({"code": actual_output.read_text(encoding="utf-8")}),
        encoding="utf-8",
    )
    receipt = {
        "receipt_version": "v2",
        "created_at": "2026-01-01T00:00:00+00:00",
        "run_kind": "signature-gen",
        "provider": "stub",
        "output_path": "artifact.py",
        "hash": hashlib.sha256(
            actual_output.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest(),
        "template_version": "simple-v1",
        "cache_key": cache_key,
        "cache_file": str(external_cache),
        "cache_enabled": True,
        "replay_inputs": replay_inputs,
    }
    meta_path = write_run_receipt(actual_output, receipt)

    report = check_run_receipt(meta_path)

    assert report["status"] == "invalid"
    assert "receipt_invalid_cache_file" in report["error_codes"]


@pytest.mark.slow
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


@pytest.mark.slow
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
        diagnostics["candidate_prior_counterfactual_advisory"][
            "candidate_prior_counterfactual_advisory_version"
        ]
        == "v1"
    )
    assert (
        diagnostics["candidate_prior_counterfactual_advisory"]["status"]
        == "counterfactual_signal_sparse"
    )
    assert (
        diagnostics["shadow_predictive_ranking_advisory"][
            "shadow_predictive_ranking_advisory_version"
        ]
        == "v1"
    )
    assert (
        diagnostics["shadow_predictive_ranking_advisory"]["status"]
        == "no_shadow_predictive_signal"
    )
    governed = diagnostics["governed_policy_evaluations"]
    assert len(governed) == 2
    assert {item["variant_class"] for item in governed} == {
        "ranking_evaluation",
        "promotion_evaluation",
    }
    nominations = diagnostics["promotion_eligibility_nominations"]
    assert len(nominations) == 2
    assert {item["eligibility_outcome"] for item in nominations} == {
        "promotion_eligibility_not_nominated"
    }
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
    assert (
        followup_diagnostics["candidate_prior_counterfactual_advisory"]["status"]
        == "counterfactual_signal_sparse"
    )
    assert (
        followup_diagnostics["shadow_predictive_ranking_advisory"]["status"]
        == "shadow_predictive_ranking_matches_v7"
    )
    followup_governed = followup_diagnostics["governed_policy_evaluations"]
    assert len(followup_governed) == 2
    assert {item["outcome"] for item in followup_governed} == {
        "policy_evaluation_affirms_live_policy"
    }
    followup_nominations = followup_diagnostics["promotion_eligibility_nominations"]
    assert len(followup_nominations) == 2
    assert {item["eligibility_outcome"] for item in followup_nominations} == {
        "promotion_eligibility_not_nominated"
    }
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


@pytest.mark.slow
def test_cli_meta_receipts_normalize_relative_paths_to_absolute(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", "cache")

    r_sig = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            "sig.py",
        ],
    )
    assert r_sig.exit_code == 0

    sig_meta = json.loads((tmp_path / "sig.py.meta.json").read_text(encoding="utf-8"))
    assert sig_meta["output_path"] == str((tmp_path / "sig.py").resolve())
    assert sig_meta["cache_file"] == str(Path(str(sig_meta["cache_file"])).resolve())


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
def test_run_execution_replay_materializes_verified_signature_with_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path, monkeypatch, output_name="execution-source.py"
    )
    replay_out = tmp_path / "execution-replay.py"

    result = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(meta_path),
            "--no-check-only",
            "--to",
            str(replay_out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "executed"
    assert payload["execution"]["strategy"] == "signature-gen-local-reexecution"
    assert payload["execution"]["provider"] == "stub"
    assert payload["execution"]["effects"]["network_access_requested"] is False
    assert payload["execution"]["effects"]["network_isolation_enforced"] is False
    assert payload["execution"]["effects"]["provider_call"] is False
    assert payload["execution"]["effects"]["subprocess"] is True
    assert payload["execution"]["effects"]["shared_oracle"] is False
    assert (
        payload["execution"]["effects"]["external_authority_mutation_requested"]
        is False
    )
    assert payload["execution"]["actual_hash"] == payload["receipt_hash"]
    assert payload["checks"]["execution_replay_reexecuted_output_hash_match"] is True
    assert payload["checks"]["execution_replay_source_output_preserved"] is True
    evidence = payload["execution"]["evidence"]
    assert evidence["schema_version"] == "execution-replay-evidence-v1"
    assert evidence["subprocess_returncode"] == 0
    assert evidence["temporary_artifacts_cleaned"] is True
    assert replay_out.read_bytes() == (tmp_path / "execution-source.py").read_bytes()


@pytest.mark.slow
def test_run_execution_replay_fails_closed_on_drift_without_writing(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path, monkeypatch, output_name="drift-source.py"
    )
    (tmp_path / "drift-source.py").write_text("drift\n", encoding="utf-8")
    replay_out = tmp_path / "must-not-exist.py"

    result = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(meta_path),
            "--no-check-only",
            "--to",
            str(replay_out),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["execution"]["attempted"] is False
    assert payload["execution"]["blocked_reason"] == "receipt_or_artifact_drift"
    assert "output_hash_mismatch" in payload["error_codes"]
    assert not replay_out.exists()


@pytest.mark.slow
def test_run_execution_replay_fails_closed_on_unsupported_run_kind(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    generated = runner.invoke(
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
            str(tmp_path / "module.py"),
        ],
    )
    assert generated.exit_code == 0, generated.stdout

    result = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "module.py.meta.json"),
            "--no-check-only",
            "--to",
            str(tmp_path / "must-not-exist.py"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert "execution_replay_unsupported_kind" in payload["error_codes"]
    assert not (tmp_path / "must-not-exist.py").exists()


@pytest.mark.slow
def test_run_execution_replay_fails_closed_on_effect_policy_drift(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path, monkeypatch, output_name="effects-source.py"
    )
    receipt = json.loads(meta_path.read_text(encoding="utf-8"))
    receipt["execution_replay"]["effects"]["network_access_requested"] = True
    meta_path.write_text(json.dumps(receipt), encoding="utf-8")
    replay_out = tmp_path / "must-not-exist.py"

    result = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(meta_path),
            "--no-check-only",
            "--to",
            str(replay_out),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert "execution_replay_unsupported_effects" in payload["error_codes"]
    assert not replay_out.exists()


@pytest.mark.slow
def test_run_execution_replay_detects_fresh_output_drift_before_publish(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path, monkeypatch, output_name="fresh-drift-source.py"
    )
    source_receipt = json.loads(meta_path.read_text(encoding="utf-8"))
    replay_out = tmp_path / "must-not-publish.py"

    def fake_reexecution(argv, **_kwargs):
        child_out = Path(argv[argv.index("--outfile") + 1])
        child_out.write_text("print('fresh drift')\n", encoding="utf-8")
        drift_hash = hashlib.sha256(child_out.read_bytes()).hexdigest()
        child_receipt = json.loads(json.dumps(source_receipt))
        child_receipt["output_path"] = str(child_out)
        child_receipt["hash"] = drift_hash
        child_receipt["cache_enabled"] = False
        child_receipt["execution_replay"]["output_identity"]["hash"] = drift_hash
        write_run_receipt(child_out, child_receipt)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(replay_service.subprocess, "run", fake_reexecution)
    result = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(meta_path),
            "--no-check-only",
            "--to",
            str(replay_out),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["execution"]["blocked_reason"] == (
        "reexecution_identity_or_output_drift"
    )
    assert "execution_replay_output_hash_mismatch" in payload["error_codes"]
    assert payload["checks"]["execution_replay_reexecuted_output_hash_match"] is False
    assert not replay_out.exists()


@pytest.mark.slow
def test_run_execution_replay_fails_on_bound_runtime_identity_drift(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path, monkeypatch, output_name="runtime-drift-source.py"
    )
    receipt = json.loads(meta_path.read_text(encoding="utf-8"))
    receipt["execution_replay"]["runtime_identity"]["python_version"] = "0.0.0"
    meta_path.write_text(json.dumps(receipt), encoding="utf-8")
    replay_out = tmp_path / "must-not-exist.py"

    result = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(meta_path),
            "--no-check-only",
            "--to",
            str(replay_out),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert "execution_replay_identity_drift" in payload["error_codes"]
    assert payload["checks"]["execution_replay_runtime_identity_match"] is False
    assert not replay_out.exists()


def test_run_execution_replay_ignores_inherited_pythonpath_startup_hook(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_signature_receipt(
        tmp_path, monkeypatch, output_name="isolated-source.py"
    )
    injected = tmp_path / "injected"
    injected.mkdir()
    marker = tmp_path / "startup-hook-ran"
    (injected / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(injected))

    result = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(meta_path),
            "--no-check-only",
            "--to",
            str(tmp_path / "isolated-replay.py"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert not marker.exists()


def test_execution_replay_runtime_identity_is_versioned_not_source_bound() -> None:
    from dspx.run_receipts import current_execution_replay_runtime_identity

    identity = current_execution_replay_runtime_identity()
    assert identity["executor_version"] == "local-execution-replay-v1"
    assert identity["python_version"].count(".") == 1
    assert "implementation_hash" not in identity


def test_execution_replay_confined_write_rejects_swapped_parent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    parent = root / "nested"
    parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    saved = root / "saved"
    parent.rename(saved)
    parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        replay_service._exclusive_write_confined(
            root.resolve(), root / "nested" / "replayed.py", b"safe"
        )

    assert not (outside / "replayed.py").exists()


def test_run_execution_replay_requires_explicit_output(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "unused.meta.json"),
            "--no-check-only",
        ],
    )
    assert result.exit_code == 2
    assert "--to is required" in result.output


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
