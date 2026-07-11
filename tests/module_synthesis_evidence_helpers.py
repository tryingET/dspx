# summary: "Shared fixtures for generating, indexing, and modeling module-synthesis receipt and replay evidence."
# read_when:
#   - "Testing module-synthesis evidence retrieval, readiness diagnostics, or receipt indexing."

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateIndex, get_embedding_engine
from dspx.run_receipts import load_run_receipt
from dspx.services.module_synthesis_evidence import (
    ModuleSynthesisEvidenceMatch,
    ModuleSynthesisHistoricalDiagnostics,
    ModuleSynthesisReceiptEvidence,
    ModuleSynthesisReplayEvidence,
)


runner = CliRunner()


def _synthetic_prior_readiness_match(
    *,
    receipt_path: str,
    audit_status: str,
    divergence_status: str,
    healthy: bool = True,
    include_diagnostics: bool = True,
) -> ModuleSynthesisEvidenceMatch:
    historical_diagnostics = (
        ModuleSynthesisHistoricalDiagnostics(
            evidence_bundle_version="v1",
            historical_convergence_advisory=None,
            candidate_winner_priors=None,
            candidate_prior_audit={"status": audit_status},
            candidate_prior_divergence_explanation={"status": divergence_status},
        )
        if include_diagnostics
        else None
    )
    return ModuleSynthesisEvidenceMatch(
        receipt=ModuleSynthesisReceiptEvidence(
            receipt_path=receipt_path,
            created_at="2026-03-28T00:00:00+00:00",
            run_kind="module-gen",
            provider="stub",
            template_version="simple-v1",
            replay_inputs={
                "name": "Summarizer",
                "description": "Summarizes text",
                "inputs": ["text"],
                "outputs": ["summary"],
                "use_signature": False,
                "template_version": "simple-v1",
            },
            output_path=f"{receipt_path}.py",
            output_hash="hash",
            cache_key="cache-key",
            selected_candidate_id="cand-a",
            selected_candidate_rank=1,
            ranked_candidate_ids=("cand-a", "cand-b"),
            ranking_policy_id="module.v7.multi-candidate-ranked",
            ranking_policy_version="v0",
            validation_pass_count=3,
            validation_total=3,
            smoke_pass_count=3,
            smoke_total=3,
            evaluation_status="passed",
            promotion_status="withheld",
            promotion_outcome="withheld",
            synthesis=None,
            synthesis_request_id=None,
            synthesis_candidate_ids=(),
            synthesis_evaluation_ids=(),
            synthesis_selection_policy=None,
            synthesis_ranked_candidates=(),
            synthesis_promotion_shell=None,
            synthesis_promotion_decision=None,
            historical_diagnostics=historical_diagnostics,
        ),
        replay=ModuleSynthesisReplayEvidence(
            replay_status="ok" if healthy else "failed",
            replay_checks={"output_hash_match": healthy},
            local_facts={
                "failed_replay_checks": [] if healthy else ["output_hash_match"]
            },
            replay_error_codes=() if healthy else ("output_hash_mismatch",),
            replay_error_details=(),
            healthy=healthy,
        ),
    )


def _configure_generation_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_MODULE_SYNTHESIS_QUALITY_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")


def _generate_module_receipt(
    tmp_path: Path,
    monkeypatch,
    *,
    output_name: str,
    name: str = "Summarizer",
    description: str = "Summarizes text",
    inputs: tuple[str, ...] = ("text",),
    outputs: tuple[str, ...] = ("summary",),
    use_signature: bool = False,
) -> Path:
    _configure_generation_env(tmp_path, monkeypatch)

    out = tmp_path / output_name
    args = [
        "module-gen",
        "--name",
        name,
        "--description",
        description,
        "--template-version",
        "simple-v1",
        "--outfile",
        str(out),
    ]
    for item in inputs:
        args.extend(["--input", item])
    for item in outputs:
        args.extend(["--output", item])
    if use_signature:
        args.append("--use-signature")

    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.stdout
    return tmp_path / f"{output_name}.meta.json"


def _generate_signature_receipt(
    tmp_path: Path,
    monkeypatch,
    *,
    output_name: str,
) -> Path:
    _configure_generation_env(tmp_path, monkeypatch)

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
    assert result.exit_code == 0, result.stdout
    return tmp_path / f"{output_name}.meta.json"


def _index_receipt(meta_path: Path, *, index_path: Path) -> None:
    receipt = load_run_receipt(meta_path)
    assert isinstance(receipt, dict)
    engine = get_embedding_engine()
    embedding = engine.embed_receipt(receipt, receipt_path=meta_path)
    assert embedding is not None
    index = CoordinateIndex(db_path=index_path)
    assert index.upsert(embedding) is True
