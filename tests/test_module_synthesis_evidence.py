from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateIndex, get_embedding_engine
from dspx.dtos import ModuleSpec
from dspx.run_receipts import load_run_receipt
from dspx.services.module_synthesis_evidence import (
    ModuleSynthesisEvidenceBundle,
    ModuleSynthesisEvidenceMatch,
    ModuleSynthesisEvidenceRequest,
    ModuleSynthesisHistoricalDiagnostics,
    ModuleSynthesisReceiptEvidence,
    ModuleSynthesisReplayEvidence,
    build_module_synthesis_candidate_prior_audit,
    build_module_synthesis_candidate_prior_counterfactual_advisory,
    build_module_synthesis_candidate_prior_divergence_explanation,
    build_module_synthesis_candidate_prior_readiness_advisory,
    build_module_synthesis_candidate_winner_priors,
    build_module_synthesis_governed_policy_evaluations,
    build_module_synthesis_shadow_predictive_ranking_advisory,
    build_module_synthesis_history_advisory,
    extract_module_synthesis_candidate_prior_inputs,
    extract_module_synthesis_ranked_candidate_comparison_inputs,
    extract_module_synthesis_ranked_candidate_inputs,
    retrieve_module_synthesis_evidence,
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


def test_retrieve_module_synthesis_evidence_collects_exact_match_receipts_and_oracle_neighbors(
    tmp_path: Path, monkeypatch
) -> None:
    exact_ok = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="exact-ok.py",
    )
    exact_drift = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="exact-drift.py",
    )
    non_match = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="other.py",
        name="Classifier",
        description="Classifies text",
        outputs=("label",),
    )
    signature_meta = _generate_signature_receipt(
        tmp_path,
        monkeypatch,
        output_name="sig.py",
    )

    (tmp_path / "exact-drift.py").write_text(
        "print('drifted output')\n", encoding="utf-8"
    )

    index_path = tmp_path / "oracle" / "coordinates.db"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    for meta_path in (exact_ok, exact_drift, non_match, signature_meta):
        _index_receipt(meta_path, index_path=index_path)

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
        oracle_index_path=index_path,
        oracle_top_k=10,
    )

    assert bundle.request.to_dict() == {
        "name": "Summarizer",
        "description": "Summarizes text",
        "inputs": ["text"],
        "outputs": ["summary"],
        "use_signature": False,
        "template_version": "simple-v1",
    }
    assert bundle.retrieval_order == (
        "exact_match_receipts",
        "replay_verification",
        "oracle_neighbors",
    )
    assert bundle.receipts_scanned == 4
    assert bundle.oracle_index_available is True
    assert bundle.oracle_query_text == (
        "name: Summarizer\n"
        "description: Summarizes text\n"
        "inputs: ['text']\n"
        "outputs: ['summary']"
    )

    matches = bundle.exact_match_receipts
    assert len(matches) == 2
    assert bundle.positive_evidence_count == 1

    receipt_paths = {Path(item.receipt.receipt_path).name for item in matches}
    assert receipt_paths == {"exact-ok.py.meta.json", "exact-drift.py.meta.json"}

    healthy_by_receipt = {
        Path(item.receipt.receipt_path).name: item.positive_evidence for item in matches
    }
    assert healthy_by_receipt["exact-ok.py.meta.json"] is True
    assert healthy_by_receipt["exact-drift.py.meta.json"] is False

    drift_match = next(
        item
        for item in matches
        if Path(item.receipt.receipt_path).name == "exact-drift.py.meta.json"
    )
    assert drift_match.replay.replay_status == "failed"
    assert "output_hash_mismatch" in drift_match.replay.replay_error_codes
    assert drift_match.replay.local_facts["failed_replay_checks"] == [
        "output_hash_match"
    ]
    assert drift_match.receipt.selected_candidate_rank == 1
    assert drift_match.receipt.ranking_policy_id == "module.v7.multi-candidate-ranked"
    assert drift_match.receipt.synthesis is not None
    assert drift_match.receipt.synthesis_selection_policy is not None
    assert drift_match.receipt.synthesis_ranked_candidates
    assert drift_match.receipt.historical_diagnostics is not None
    assert drift_match.receipt.historical_diagnostics.candidate_prior_audit is not None
    assert (
        drift_match.receipt.historical_diagnostics.candidate_prior_divergence_explanation
        is not None
    )
    assert (
        drift_match.receipt.historical_diagnostics.candidate_prior_readiness_advisory
        is not None
    )
    assert (
        drift_match.receipt.historical_diagnostics.candidate_prior_counterfactual_advisory
        is not None
    )
    assert (
        drift_match.receipt.historical_diagnostics.shadow_predictive_ranking_advisory
        is not None
    )

    assert bundle.oracle_neighbors
    assert all(item.run_kind == "module-gen" for item in bundle.oracle_neighbors)
    assert all(item.receipt_identity for item in bundle.oracle_neighbors)

    payload = bundle.to_dict()
    assert payload["positive_evidence_count"] == 1
    assert len(payload["exact_match_receipts"]) == 2
    assert (
        payload["exact_match_receipts"][0]["receipt"]["replay_inputs"]["name"]
        == "Summarizer"
    )
    assert (
        payload["exact_match_receipts"][0]["receipt"]["synthesis_diagnostics"][
            "candidate_prior_audit"
        ]
        is not None
    )
    assert (
        payload["exact_match_receipts"][0]["receipt"]["synthesis_diagnostics"][
            "candidate_prior_counterfactual_advisory"
        ]
        is not None
    )
    assert (
        payload["exact_match_receipts"][0]["receipt"]["synthesis_diagnostics"][
            "shadow_predictive_ranking_advisory"
        ]
        is not None
    )
    assert all(item["run_kind"] == "module-gen" for item in payload["oracle_neighbors"])


def test_retrieve_module_synthesis_evidence_exposes_missing_historical_diagnostics_to_readiness_rollup(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="single.py",
    )
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload.pop("synthesis_diagnostics", None)
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
    )

    readiness = build_module_synthesis_candidate_prior_readiness_advisory(bundle)

    assert len(bundle.exact_match_receipts) == 1
    assert bundle.exact_match_receipts[0].receipt.historical_diagnostics is None
    assert readiness["status"] == "candidate_prior_readiness_unavailable"
    assert readiness["history_summary"]["unusable_receipt_count"] == 1


def test_retrieve_module_synthesis_evidence_rejects_malformed_shadow_surface(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="single.py",
    )
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    diagnostics = dict(payload.get("synthesis_diagnostics") or {})
    diagnostics["shadow_predictive_ranking_advisory"] = {
        "shadow_predictive_ranking_advisory_version": "v1"
    }
    payload["synthesis_diagnostics"] = diagnostics
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
    )

    assert bundle.exact_match_receipts == ()
    assert bundle.receipt_scan_error_count == 1
    assert bundle.receipt_scan_errors[0]["code"] == "receipt_invalid_sg2_surface"
    assert (
        bundle.receipt_scan_errors[0]["surface"] == "shadow_predictive_ranking_advisory"
    )


def test_retrieve_module_synthesis_evidence_rejects_malformed_governed_policy_receipts(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="single.py",
    )
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    diagnostics = dict(payload.get("synthesis_diagnostics") or {})
    diagnostics["governed_policy_evaluations"] = [
        {"variant_class": "ranking_evaluation"}
    ]
    payload["synthesis_diagnostics"] = diagnostics
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
    )

    assert bundle.exact_match_receipts == ()
    assert bundle.receipt_scan_error_count == 1
    assert (
        bundle.receipt_scan_errors[0]["code"]
        == "receipt_invalid_governed_policy_evaluations"
    )
    assert bundle.receipt_scan_errors[0]["surface"] == "governed_policy_evaluations"


def test_retrieve_module_synthesis_evidence_handles_missing_oracle_index(
    tmp_path: Path, monkeypatch
) -> None:
    _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="single.py",
    )

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
        oracle_index_path=tmp_path / "missing" / "coordinates.db",
    )

    assert len(bundle.exact_match_receipts) == 1
    assert bundle.oracle_index_available is False
    assert bundle.oracle_neighbors == ()
    assert bundle.positive_evidence_count == 1


def test_retrieve_module_synthesis_evidence_respects_use_signature_in_exact_match(
    tmp_path: Path, monkeypatch
) -> None:
    plain = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="plain.py",
        use_signature=False,
    )
    signed = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="signed.py",
        use_signature=True,
    )

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    plain_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
    )
    signed_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=True,
        receipts_path=tmp_path,
    )

    assert len(plain_bundle.exact_match_receipts) == 1
    assert Path(plain_bundle.exact_match_receipts[0].receipt.receipt_path) == plain
    assert len(signed_bundle.exact_match_receipts) == 1
    assert Path(signed_bundle.exact_match_receipts[0].receipt.receipt_path) == signed

    signed_receipt = json.loads(signed.read_text(encoding="utf-8"))
    assert signed_receipt["replay_inputs"]["use_signature"] is True


def test_retrieve_module_synthesis_evidence_skips_malformed_exact_match_receipt_and_records_error(
    tmp_path: Path, monkeypatch
) -> None:
    malformed = tmp_path / "malformed.meta.json"
    malformed.write_text(
        json.dumps(
            {
                "receipt_version": "v2",
                "created_at": "2026-03-24T00:00:00+00:00",
                "run_kind": "module-gen",
                "provider": "stub",
                "output_path": str(tmp_path / "bad.py"),
                "hash": "abc",
                "template_version": "simple-v1",
                "cache_key": "cache-key",
                "cache_file": str(tmp_path / "cache" / "module" / "cache-key.json"),
                "cache_enabled": True,
                "replay_inputs": {
                    "name": "Summarizer",
                    "description": "Summarizes text",
                    "inputs": ["text"],
                    "outputs": ["summary"],
                    "use_signature": False,
                    "template_version": "simple-v1",
                },
                "run_summary": {
                    "backend": "synthesis_runtime",
                    "selected_candidate_id": "cand-a",
                    "selected_candidate_rank": "not-an-int",
                    "ranked_candidate_ids": ["cand-a"],
                    "ranking_policy_id": "module.v7.multi-candidate-ranked",
                },
            }
        ),
        encoding="utf-8",
    )

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
    )

    assert bundle.exact_match_receipts == ()
    assert bundle.receipt_scan_error_count == 1
    assert bundle.exact_match_receipt_scan_error_count == 1
    assert bundle.receipt_scan_errors[0]["receipt_path"] == str(malformed)
    assert (
        bundle.receipt_scan_errors[0]["code"]
        == "receipt_invalid_selected_candidate_rank"
    )
    advisory = build_module_synthesis_history_advisory(
        bundle,
        selected_candidate_id="cand-now",
        output_hash="hash-now",
        cache_key="cache-now",
    )
    assert advisory["status"] == "degraded_history_only"


def test_retrieve_module_synthesis_evidence_records_invalid_json_receipts_as_scan_errors(
    tmp_path: Path,
) -> None:
    malformed = tmp_path / "malformed.meta.json"
    malformed.write_text("{not json", encoding="utf-8")

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
    )

    assert bundle.exact_match_receipts == ()
    assert bundle.receipt_scan_error_count == 1
    assert bundle.exact_match_receipt_scan_error_count == 0
    assert bundle.receipt_scan_errors[0]["receipt_path"] == str(malformed)
    assert bundle.receipt_scan_errors[0]["code"] == "receipt_invalid_json"
    advisory = build_module_synthesis_history_advisory(
        bundle,
        selected_candidate_id="cand-now",
        output_hash="hash-now",
        cache_key="cache-now",
    )
    assert advisory["status"] == "no_history"
    assert (
        "ignored malformed non-attributable receipt scan errors outside exact-match authority"
        in advisory["notes"]
    )


def test_retrieve_module_synthesis_evidence_reports_unavailable_oracle_lookup(
    tmp_path: Path,
) -> None:
    bad_db = tmp_path / "oracle" / "coordinates.db"
    bad_db.parent.mkdir(parents=True, exist_ok=True)
    bad_db.write_text("not sqlite", encoding="utf-8")

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
        oracle_index_path=bad_db,
    )

    assert bundle.oracle_lookup_status == "unavailable"
    assert bundle.oracle_index_available is False
    assert bundle.oracle_lookup_error is not None
    assert bundle.oracle_lookup_error["type"]


def test_build_module_synthesis_history_advisory_statuses(
    tmp_path: Path, monkeypatch
) -> None:
    exact_ok = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="exact-ok.py",
    )
    exact_drift = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="exact-drift.py",
    )
    (tmp_path / "exact-drift.py").write_text(
        "print('drifted output')\n", encoding="utf-8"
    )

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )

    no_history_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path / "missing",
    )
    no_history = build_module_synthesis_history_advisory(
        no_history_bundle,
        selected_candidate_id="cand-now",
        output_hash="hash-now",
        cache_key="cache-now",
    )
    assert no_history["status"] == "no_history"

    degraded_only_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=exact_drift,
    )
    degraded_only = build_module_synthesis_history_advisory(
        degraded_only_bundle,
        selected_candidate_id="cand-now",
        output_hash="hash-now",
        cache_key="cache-now",
    )
    assert degraded_only["status"] == "degraded_history_only"

    convergent_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
    )
    ok_receipt = json.loads(exact_ok.read_text(encoding="utf-8"))
    convergent = build_module_synthesis_history_advisory(
        convergent_bundle,
        selected_candidate_id="cand-now",
        output_hash=ok_receipt["hash"],
        cache_key=ok_receipt["cache_key"],
    )
    assert convergent["status"] == "convergent_with_positive_history"
    assert len(convergent["matching_positive_receipts"]) == 1

    divergent = build_module_synthesis_history_advisory(
        convergent_bundle,
        selected_candidate_id="cand-now",
        output_hash="different-hash",
        cache_key="cache-now",
    )
    assert divergent["status"] == "divergent_from_positive_history"
    assert len(divergent["divergent_positive_receipts"]) == 1


def test_build_module_synthesis_candidate_winner_priors_statuses(
    tmp_path: Path, monkeypatch
) -> None:
    exact_ok = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="exact-ok.py",
    )
    exact_drift = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="exact-drift.py",
    )
    (tmp_path / "exact-drift.py").write_text(
        "print('drifted output')\n", encoding="utf-8"
    )

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    synthesis = json.loads(exact_ok.read_text(encoding="utf-8"))["synthesis"]
    current_candidates = extract_module_synthesis_candidate_prior_inputs(synthesis)

    no_history_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path / "missing",
    )
    no_history = build_module_synthesis_candidate_winner_priors(
        no_history_bundle,
        current_candidates=current_candidates,
    )
    assert no_history["history_summary"]["candidate_count"] == len(current_candidates)
    assert {item["status"] for item in no_history["candidate_priors"]} == {
        "no_positive_winner_history"
    }

    degraded_only_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=exact_drift,
    )
    degraded_only = build_module_synthesis_candidate_winner_priors(
        degraded_only_bundle,
        current_candidates=current_candidates,
    )
    assert {item["status"] for item in degraded_only["candidate_priors"]} == {
        "degraded_history_only"
    }

    convergent_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
    )
    convergent = build_module_synthesis_candidate_winner_priors(
        convergent_bundle,
        current_candidates=current_candidates,
    )
    by_variant = {item["variant_id"]: item for item in convergent["candidate_priors"]}
    assert (
        by_variant["explainable_helpers"]["status"] == "matches_positive_winner_history"
    )
    assert by_variant["explainable_helpers"]["positive_winner_match_count"] == 1
    assert by_variant["explainable_helpers"]["matching_positive_receipts"][0][
        "receipt_path"
    ] == str(exact_ok)
    assert by_variant["baseline"]["status"] == "no_positive_winner_history"
    assert by_variant["traceable"]["status"] == "no_positive_winner_history"

    unsupported_candidates = [dict(item) for item in current_candidates]
    unsupported_candidates[0]["variant_origin"] = None
    unsupported = build_module_synthesis_candidate_winner_priors(
        convergent_bundle,
        current_candidates=tuple(unsupported_candidates),
    )
    assert (
        unsupported["candidate_priors"][0]["status"] == "unsupported_candidate_identity"
    )


def test_build_module_synthesis_candidate_prior_audit_statuses(
    tmp_path: Path, monkeypatch
) -> None:
    exact_ok = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="exact-ok.py",
    )
    exact_drift = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="exact-drift.py",
    )
    (tmp_path / "exact-drift.py").write_text(
        "print('drifted output')\n", encoding="utf-8"
    )

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    receipt_payload = json.loads(exact_ok.read_text(encoding="utf-8"))
    synthesis = receipt_payload["synthesis"]
    current_candidates = extract_module_synthesis_candidate_prior_inputs(synthesis)
    ranked_candidates = extract_module_synthesis_ranked_candidate_inputs(synthesis)
    selected_candidate_id = receipt_payload["run_summary"]["selected_candidate_id"]

    no_history_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path / "missing",
    )
    no_history_priors = build_module_synthesis_candidate_winner_priors(
        no_history_bundle,
        current_candidates=current_candidates,
    )
    no_history_audit = build_module_synthesis_candidate_prior_audit(
        no_history_priors,
        current_candidates=current_candidates,
        ranked_candidates=ranked_candidates,
        selected_candidate_id=selected_candidate_id,
    )
    assert no_history_audit["status"] == "no_positive_prior_candidates"
    assert no_history_audit["history_summary"]["positive_prior_candidate_count"] == 0
    assert (
        no_history_audit["selected_candidate"]["candidate_id"] == selected_candidate_id
    )

    degraded_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=exact_drift,
    )
    degraded_priors = build_module_synthesis_candidate_winner_priors(
        degraded_bundle,
        current_candidates=current_candidates,
    )
    degraded_audit = build_module_synthesis_candidate_prior_audit(
        degraded_priors,
        current_candidates=current_candidates,
        ranked_candidates=ranked_candidates,
        selected_candidate_id=selected_candidate_id,
    )
    assert degraded_audit["status"] == "selected_candidate_prior_degraded"

    convergent_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
    )
    convergent_priors = build_module_synthesis_candidate_winner_priors(
        convergent_bundle,
        current_candidates=current_candidates,
    )
    convergent_audit = build_module_synthesis_candidate_prior_audit(
        convergent_priors,
        current_candidates=current_candidates,
        ranked_candidates=ranked_candidates,
        selected_candidate_id=selected_candidate_id,
    )
    assert convergent_audit["status"] == "selected_matches_positive_winner_history"
    assert convergent_audit["history_summary"]["positive_prior_candidate_count"] == 1
    assert len(convergent_audit["positive_prior_candidates"]) == 1
    assert convergent_audit["positive_prior_candidates"][0]["rank"] == 1

    divergent_selected_candidate_id = next(
        item["candidate_id"]
        for item in current_candidates
        if item["candidate_id"] != selected_candidate_id
    )
    divergent_audit = build_module_synthesis_candidate_prior_audit(
        convergent_priors,
        current_candidates=current_candidates,
        ranked_candidates=ranked_candidates,
        selected_candidate_id=divergent_selected_candidate_id,
    )
    assert (
        divergent_audit["status"]
        == "positive_prior_candidates_present_but_not_selected"
    )
    assert len(divergent_audit["non_selected_positive_prior_candidates"]) == 1

    unsupported_candidates = [dict(item) for item in current_candidates]
    unsupported_candidates[0]["variant_origin"] = None
    unsupported_priors = build_module_synthesis_candidate_winner_priors(
        convergent_bundle,
        current_candidates=tuple(unsupported_candidates),
    )
    unsupported_selected_candidate_id = unsupported_candidates[0]["candidate_id"]
    unsupported_audit = build_module_synthesis_candidate_prior_audit(
        unsupported_priors,
        current_candidates=tuple(unsupported_candidates),
        ranked_candidates=ranked_candidates,
        selected_candidate_id=unsupported_selected_candidate_id,
    )
    assert unsupported_audit["status"] == "selected_candidate_prior_unsupported"


def test_extract_module_synthesis_ranked_candidate_comparison_inputs_preserves_explicit_runtime_metadata() -> (
    None
):
    synthesis = {
        "promotion_decision": {
            "metadata": {
                "ranked_candidates": [
                    {
                        "candidate_id": "cand-a",
                        "rank": 1,
                        "variant_id": "variant-a",
                        "variant_origin": "runtime-origin-a",
                        "ordinal": 0,
                        "status": "passed",
                        "passed": True,
                        "score": 103.0,
                    },
                    {
                        "candidate_id": "cand-b",
                        "rank": 2,
                        "variant_id": "variant-b",
                        "variant_origin": "runtime-origin-b",
                        "ordinal": 1,
                        "status": "failed",
                        "passed": False,
                        "score": 2.0,
                    },
                ]
            }
        },
        "evaluations": [
            {"candidate_id": "cand-a", "summary": "selected summary"},
            {"candidate_id": "cand-b", "summary": "failed summary"},
        ],
    }

    comparison_inputs = extract_module_synthesis_ranked_candidate_comparison_inputs(
        synthesis
    )

    assert comparison_inputs == (
        {
            "candidate_id": "cand-a",
            "rank": 1,
            "variant_id": "variant-a",
            "variant_origin": "runtime-origin-a",
            "ordinal": 0,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 103.0,
            "evaluation_summary": "selected summary",
        },
        {
            "candidate_id": "cand-b",
            "rank": 2,
            "variant_id": "variant-b",
            "variant_origin": "runtime-origin-b",
            "ordinal": 1,
            "evaluation_status": "failed",
            "passed": False,
            "ranking_score": 2.0,
            "evaluation_summary": "failed summary",
        },
    )


def test_extract_module_synthesis_ranked_candidate_comparison_inputs_augments_variant_origin_from_candidates() -> (
    None
):
    synthesis = {
        "candidates": [
            {
                "candidate_id": "cand-a",
                "ordinal": 0,
                "metadata": {"variant_id": "variant-a"},
                "lineage": {"variant_origin": "deterministic_template_variant"},
            }
        ],
        "promotion_decision": {
            "metadata": {
                "ranked_candidates": [
                    {
                        "candidate_id": "cand-a",
                        "rank": 1,
                        "variant_id": "variant-a",
                        "ordinal": 0,
                        "status": "passed",
                        "passed": True,
                        "score": 103.0,
                    }
                ]
            }
        },
        "evaluations": [{"candidate_id": "cand-a", "summary": "selected summary"}],
    }

    comparison_inputs = extract_module_synthesis_ranked_candidate_comparison_inputs(
        synthesis
    )

    assert comparison_inputs[0]["variant_origin"] == "deterministic_template_variant"


def test_build_module_synthesis_candidate_prior_divergence_explanation_fails_closed_on_malformed_or_duplicate_current_comparison_metadata() -> (
    None
):
    audit = {
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "history_summary": {
            "exact_match_receipt_count": 3,
            "positive_evidence_count": 3,
            "positive_prior_candidate_count": 1,
        },
        "non_selected_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 2,
            }
        ],
        "notes": [],
    }

    malformed = build_module_synthesis_candidate_prior_divergence_explanation(
        audit,
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": True,
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": False,
                "evaluation_summary": "cand-b malformed",
            },
        ),
    )
    assert malformed["status"] == "candidate_prior_divergence_unavailable"

    duplicated = build_module_synthesis_candidate_prior_divergence_explanation(
        audit,
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 1.0,
                "evaluation_summary": "cand-b duplicate",
            },
        ),
    )
    assert duplicated["status"] == "candidate_prior_divergence_unavailable"


def test_build_module_synthesis_candidate_prior_divergence_explanation_statuses() -> (
    None
):
    no_divergence = build_module_synthesis_candidate_prior_divergence_explanation(
        {
            "status": "selected_matches_positive_winner_history",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 1,
                "positive_prior_candidate_count": 1,
            },
            "non_selected_positive_prior_candidates": [],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(),
    )
    assert no_divergence["status"] == "no_divergence_to_explain"
    assert no_divergence["selected_candidate"]["candidate_id"] == "cand-a"

    unresolved = build_module_synthesis_candidate_prior_divergence_explanation(
        {
            "status": "selected_candidate_prior_degraded",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "degraded_history_only",
                "rank": None,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 0,
                "positive_prior_candidate_count": 0,
            },
            "non_selected_positive_prior_candidates": [],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(),
    )
    assert unresolved["status"] == "selected_candidate_prior_unresolved"

    audit = {
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "history_summary": {
            "exact_match_receipt_count": 2,
            "positive_evidence_count": 2,
            "positive_prior_candidate_count": 2,
        },
        "non_selected_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 2,
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 3,
            },
        ],
        "notes": [],
    }

    failures = build_module_synthesis_candidate_prior_divergence_explanation(
        audit,
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 2.0,
                "evaluation_summary": "cand-b failed",
            },
            {
                "candidate_id": "cand-c",
                "rank": 3,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 1.0,
                "evaluation_summary": "cand-c failed",
            },
        ),
    )
    assert failures["status"] == "divergence_explained_by_runtime_failures"
    assert {
        item["comparison_status"]
        for item in failures["compared_positive_prior_candidates"]
    } == {"failed_runtime_validation"}
    assert failures["history_summary"]["compared_candidate_count"] == 2

    scoring = build_module_synthesis_candidate_prior_divergence_explanation(
        audit,
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 102.0,
                "evaluation_summary": "cand-b passed",
            },
            {
                "candidate_id": "cand-c",
                "rank": 3,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 101.0,
                "evaluation_summary": "cand-c passed",
            },
        ),
    )
    assert scoring["status"] == "divergence_explained_by_runtime_scoring"
    assert {
        item["comparison_status"]
        for item in scoring["compared_positive_prior_candidates"]
    } == {"lower_ranked_pass"}
    assert scoring["selected_candidate"]["ranking_score"] == 103.0

    mixed = build_module_synthesis_candidate_prior_divergence_explanation(
        audit,
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 2.0,
                "evaluation_summary": "cand-b failed",
            },
            {
                "candidate_id": "cand-c",
                "rank": 3,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 101.0,
                "evaluation_summary": "cand-c passed",
            },
        ),
    )
    assert mixed["status"] == "divergence_explained_by_mixed_runtime_outcomes"


def test_build_module_synthesis_candidate_prior_divergence_explanation_fails_closed_on_incomplete_comparison_truth() -> (
    None
):
    explanation = build_module_synthesis_candidate_prior_divergence_explanation(
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 1,
                "positive_prior_candidate_count": 1,
            },
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": None,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert explanation["status"] == "candidate_prior_divergence_unavailable"
    assert explanation["history_summary"]["compared_candidate_count"] == 1
    assert explanation["compared_positive_prior_candidates"] == []


def test_build_module_synthesis_candidate_prior_divergence_explanation_fails_closed_on_malformed_compared_candidates() -> (
    None
):
    explanation = build_module_synthesis_candidate_prior_divergence_explanation(
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 1,
                "positive_prior_candidate_count": 2,
            },
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                },
                "MALFORMED",
            ],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 102.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert explanation["status"] == "candidate_prior_divergence_unavailable"
    assert explanation["compared_positive_prior_candidates"] == []


def test_build_module_synthesis_candidate_prior_readiness_advisory_statuses() -> None:
    request = ModuleSynthesisEvidenceRequest(
        name="Summarizer",
        description="Summarizes text",
        inputs=("text",),
        outputs=("summary",),
        use_signature=False,
        template_version="simple-v1",
    )

    def _bundle(
        *matches: ModuleSynthesisEvidenceMatch,
    ) -> ModuleSynthesisEvidenceBundle:
        return ModuleSynthesisEvidenceBundle(
            request=request,
            retrieval_order=("exact_match_receipts", "replay_verification"),
            exact_match_receipts=matches,
            oracle_neighbors=(),
            receipts_path="/tmp/receipts",
            oracle_index_path="/tmp/oracle.db",
            receipts_scanned=len(matches),
            oracle_query_text=request.oracle_query_text(),
            receipt_scan_errors=(),
            exact_match_receipt_scan_errors=(),
            oracle_lookup_status="missing",
            oracle_lookup_error=None,
        )

    insufficient = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            )
        )
    )
    assert insufficient["status"] == "insufficient_prior_history"

    unavailable = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r2.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
                include_diagnostics=False,
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r3.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
        )
    )
    assert unavailable["status"] == "candidate_prior_readiness_unavailable"
    assert unavailable["history_summary"]["unusable_receipt_count"] == 1

    convergent = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r2.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r3.meta.json",
                audit_status="no_positive_prior_candidates",
                divergence_status="no_divergence_to_explain",
            ),
        )
    )
    assert convergent["status"] == "priors_consistently_convergent"

    runtime_failures = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_failures",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r2.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_failures",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r3.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
        )
    )
    assert runtime_failures["status"] == "priors_mostly_blocked_by_runtime_failures"

    runtime_scoring = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_scoring",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r2.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_scoring",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r3.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
        )
    )
    assert runtime_scoring["status"] == "priors_mostly_outscored_under_v7"

    mixed = build_module_synthesis_candidate_prior_readiness_advisory(
        _bundle(
            _synthetic_prior_readiness_match(
                receipt_path="r1.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_failures",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r2.meta.json",
                audit_status="positive_prior_candidates_present_but_not_selected",
                divergence_status="divergence_explained_by_runtime_scoring",
            ),
            _synthetic_prior_readiness_match(
                receipt_path="r3.meta.json",
                audit_status="selected_matches_positive_winner_history",
                divergence_status="no_divergence_to_explain",
            ),
        )
    )
    assert mixed["status"] == "priors_mixed_or_inconclusive"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_statuses() -> (
    None
):
    audit = {
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "history_summary": {
            "exact_match_receipt_count": 4,
            "positive_evidence_count": 4,
            "positive_prior_candidate_count": 2,
        },
        "non_selected_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 2,
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 3,
            },
        ],
        "notes": [],
    }
    comparison_inputs = (
        {
            "candidate_id": "cand-a",
            "rank": 1,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 103.0,
            "evaluation_summary": "selected passed",
        },
        {
            "candidate_id": "cand-b",
            "rank": 2,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 102.0,
            "evaluation_summary": "cand-b passed",
        },
        {
            "candidate_id": "cand-c",
            "rank": 3,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 101.0,
            "evaluation_summary": "cand-c passed",
        },
    )
    scoring_divergence = {
        "status": "divergence_explained_by_runtime_scoring",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "compared_positive_prior_candidates": [
            {"candidate_id": "cand-b", "comparison_status": "lower_ranked_pass"},
            {"candidate_id": "cand-c", "comparison_status": "lower_ranked_pass"},
        ],
        "notes": [],
    }

    positive = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 4,
                "replay_healthy_receipt_count": 4,
                "usable_receipt_count": 4,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 3,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        scoring_divergence,
        audit,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert positive["status"] == "counterfactual_positive_prior_alternatives_present"
    assert positive["history_summary"]["passing_positive_prior_candidate_count"] == 2
    assert [
        item["candidate_id"]
        for item in positive["counterfactual_positive_prior_candidates"]
    ] == ["cand-b", "cand-c"]

    sparse = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "insufficient_prior_history",
            "history_summary": {
                "exact_match_receipt_count": 2,
                "replay_healthy_receipt_count": 2,
                "usable_receipt_count": 2,
                "convergent_receipt_count": 0,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        scoring_divergence,
        audit,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert sparse["status"] == "counterfactual_signal_sparse"
    assert sparse["counterfactual_positive_prior_candidates"]

    no_signal = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_blocked_by_runtime_failures",
            "history_summary": {
                "exact_match_receipt_count": 4,
                "replay_healthy_receipt_count": 4,
                "usable_receipt_count": 4,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 3,
                "runtime_scoring_divergence_count": 0,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_failures",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 103.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "failed_runtime_validation",
                }
            ],
            "notes": [],
        },
        {
            **audit,
            "non_selected_positive_prior_candidates": [
                audit["non_selected_positive_prior_candidates"][0]
            ],
        },
        ranked_candidate_comparison_inputs=(
            comparison_inputs[0],
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 2.0,
                "evaluation_summary": "cand-b failed",
            },
        ),
    )
    assert no_signal["status"] == "no_counterfactual_signal"
    assert no_signal["counterfactual_positive_prior_candidates"] == []

    mixed = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mixed_or_inconclusive",
            "history_summary": {
                "exact_match_receipt_count": 4,
                "replay_healthy_receipt_count": 4,
                "usable_receipt_count": 4,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 1,
                "runtime_scoring_divergence_count": 1,
                "mixed_divergence_count": 1,
                "unresolved_receipt_count": 1,
            },
            "notes": [],
        },
        {
            "status": "divergence_explained_by_mixed_runtime_outcomes",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 103.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                },
                {
                    "candidate_id": "cand-c",
                    "comparison_status": "failed_runtime_validation",
                },
            ],
            "notes": [],
        },
        audit,
        ranked_candidate_comparison_inputs=(
            comparison_inputs[0],
            comparison_inputs[1],
            {
                "candidate_id": "cand-c",
                "rank": 3,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 1.0,
                "evaluation_summary": "cand-c failed",
            },
        ),
    )
    assert mixed["status"] == "counterfactual_signal_mixed_or_inconclusive"
    assert len(mixed["counterfactual_positive_prior_candidates"]) == 1


def test_build_module_synthesis_governed_policy_evaluations_statuses() -> None:
    synthesis = {
        "request": {
            "spec": {
                "name": "Summarizer",
                "description": "Summarizes text",
                "inputs": ["text"],
                "outputs": ["summary"],
                "use_signature": False,
                "template_version": "simple-v1",
            }
        },
        "selection_policy": {
            "policy_id": "module.v7.multi-candidate-ranked",
            "policy_version": "v0",
        },
        "promotion_shell": {
            "metadata": {
                "promotion_policy_id": "module.v7.selected-candidate-promotion",
                "promotion_policy_version": "v0",
            }
        },
    }
    candidate_winner_priors = {
        "candidate_prior_version": "v1",
        "mode": "winner_history_only",
        "history_summary": {
            "exact_match_receipt_count": 4,
            "positive_evidence_count": 4,
            "oracle_neighbor_count": 0,
            "candidate_count": 3,
        },
        "candidate_priors": [
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "status": "no_positive_winner_history",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "status": "matches_positive_winner_history",
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "status": "matches_positive_winner_history",
            },
        ],
        "notes": [],
    }
    audit = {
        "candidate_prior_audit_version": "v1",
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "notes": [],
    }
    divergence = {
        "candidate_prior_divergence_explanation_version": "v1",
        "status": "divergence_explained_by_runtime_scoring",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "compared_positive_prior_candidates": [
            {"candidate_id": "cand-b", "comparison_status": "lower_ranked_pass"},
            {"candidate_id": "cand-c", "comparison_status": "lower_ranked_pass"},
        ],
        "notes": [],
    }
    readiness = {
        "candidate_prior_readiness_advisory_version": "v1",
        "status": "priors_mostly_outscored_under_v7",
        "history_summary": {
            "exact_match_receipt_count": 4,
            "replay_healthy_receipt_count": 4,
            "usable_receipt_count": 4,
            "convergent_receipt_count": 1,
            "runtime_failure_divergence_count": 0,
            "runtime_scoring_divergence_count": 3,
            "mixed_divergence_count": 0,
            "unresolved_receipt_count": 0,
        },
        "notes": [],
    }
    counterfactual = {
        "candidate_prior_counterfactual_advisory_version": "v1",
        "status": "counterfactual_positive_prior_alternatives_present",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "counterfactual_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "ranking_score": 102.0,
                "evaluation_status": "passed",
                "notes": [],
            }
        ],
        "notes": [],
    }
    shadow = {
        "shadow_predictive_ranking_advisory_version": "v1",
        "status": "shadow_predictive_ranking_prefers_positive_prior_alternative",
        "shadow_policy_id": "module.sg2.shadow-predictive-ranking.v1",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "shadow_preferred_candidate": {
            "candidate_id": "cand-b",
            "variant_id": "variant-b",
            "variant_origin": "deterministic_template_variant",
            "rank": 2,
            "ranking_score": 102.0,
        },
        "notes": [],
    }
    comparison_inputs = (
        {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 103.0,
            "evaluation_summary": "selected passed",
        },
        {
            "candidate_id": "cand-b",
            "variant_id": "variant-b",
            "variant_origin": "deterministic_template_variant",
            "rank": 2,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 102.0,
            "evaluation_summary": "cand-b passed",
        },
    )

    receipts = build_module_synthesis_governed_policy_evaluations(
        synthesis=synthesis,
        candidate_winner_priors=candidate_winner_priors,
        candidate_prior_audit=audit,
        candidate_prior_divergence_explanation=divergence,
        candidate_prior_readiness_advisory=readiness,
        candidate_prior_counterfactual_advisory=counterfactual,
        shadow_predictive_ranking_advisory=shadow,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )

    assert len(receipts) == 2
    ranking = next(
        item for item in receipts if item["variant_class"] == "ranking_evaluation"
    )
    promotion = next(
        item for item in receipts if item["variant_class"] == "promotion_evaluation"
    )
    assert ranking["outcome"] == "policy_evaluation_surfaces_governance_candidate"
    assert ranking["comparison_scope"] == ["cand-a", "cand-b"]
    assert ranking["evaluation_result"]["governance_candidate_id"] == "cand-b"
    assert ranking["decision_rule_summary"].startswith("Compare the live selected")
    assert "shadow_predictive_ranking_advisory:v1" in ranking["input_contracts"]
    assert (
        ranking["bounded_inputs"]["surface_versions"][
            "shadow_predictive_ranking_advisory"
        ]
        == "v1"
    )
    assert ranking["promotion_authority"]["can_change_live_ranking"] is False
    assert ranking["request_context"]["selected_candidate_id"] == "cand-a"
    assert promotion["outcome"] == "policy_evaluation_surfaces_governance_candidate"
    assert promotion["comparison_scope"] == "selected_candidate_only"
    assert (
        promotion["evaluation_result"]["promotion_posture"]
        == "promotion_posture_requires_human_review"
    )
    assert promotion["promotion_authority"]["can_change_live_promotion"] is False


def test_build_module_synthesis_governed_policy_evaluations_fail_closed_without_shadow() -> (
    None
):
    receipts = build_module_synthesis_governed_policy_evaluations(
        synthesis={
            "request": {
                "spec": {
                    "name": "Summarizer",
                    "description": "Summarizes text",
                    "inputs": ["text"],
                    "outputs": ["summary"],
                }
            }
        },
        candidate_winner_priors={"candidate_prior_version": "v1"},
        candidate_prior_audit={"candidate_prior_audit_version": "v1"},
        candidate_prior_divergence_explanation={
            "candidate_prior_divergence_explanation_version": "v1"
        },
        candidate_prior_readiness_advisory={
            "candidate_prior_readiness_advisory_version": "v1"
        },
        candidate_prior_counterfactual_advisory={
            "candidate_prior_counterfactual_advisory_version": "v1",
            "counterfactual_positive_prior_candidates": [],
        },
        shadow_predictive_ranking_advisory=None,
        ranked_candidate_comparison_inputs=(),
    )

    assert len(receipts) == 2
    assert {item["outcome"] for item in receipts} == {"policy_evaluation_unavailable"}
    ranking = next(
        item for item in receipts if item["variant_class"] == "ranking_evaluation"
    )
    promotion = next(
        item for item in receipts if item["variant_class"] == "promotion_evaluation"
    )
    assert ranking["comparison_scope"] == []
    assert promotion["comparison_scope"] == "selected_candidate_only"


def test_build_module_synthesis_shadow_predictive_ranking_advisory_statuses() -> None:
    candidate_winner_priors = {
        "candidate_prior_version": "v1",
        "mode": "winner_history_only",
        "history_summary": {
            "exact_match_receipt_count": 4,
            "positive_evidence_count": 4,
            "oracle_neighbor_count": 0,
            "candidate_count": 3,
        },
        "candidate_priors": [
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "status": "no_positive_winner_history",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "status": "matches_positive_winner_history",
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "status": "matches_positive_winner_history",
            },
        ],
        "notes": [],
    }
    audit = {
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "history_summary": {
            "exact_match_receipt_count": 4,
            "positive_evidence_count": 4,
            "candidate_count": 3,
            "positive_prior_candidate_count": 2,
        },
        "positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 2,
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 3,
            },
        ],
        "non_selected_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 2,
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 3,
            },
        ],
        "notes": [],
    }
    divergence = {
        "status": "divergence_explained_by_runtime_scoring",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "compared_positive_prior_candidates": [
            {"candidate_id": "cand-b", "comparison_status": "lower_ranked_pass"},
            {"candidate_id": "cand-c", "comparison_status": "lower_ranked_pass"},
        ],
        "notes": [],
    }
    readiness = {
        "status": "priors_mostly_outscored_under_v7",
        "history_summary": {
            "exact_match_receipt_count": 4,
            "replay_healthy_receipt_count": 4,
            "usable_receipt_count": 4,
            "convergent_receipt_count": 1,
            "runtime_failure_divergence_count": 0,
            "runtime_scoring_divergence_count": 3,
            "mixed_divergence_count": 0,
            "unresolved_receipt_count": 0,
        },
        "notes": [],
    }
    counterfactual = {
        "status": "counterfactual_positive_prior_alternatives_present",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 103.0,
        },
        "history_summary": {
            "exact_match_receipt_count": 4,
            "replay_healthy_receipt_count": 4,
            "positive_prior_signal_receipt_count": 4,
            "passing_positive_prior_candidate_count": 2,
        },
        "counterfactual_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "ranking_score": 102.0,
                "evaluation_status": "passed",
                "notes": [],
            },
            {
                "candidate_id": "cand-c",
                "variant_id": "variant-c",
                "variant_origin": "deterministic_template_variant",
                "rank": 3,
                "ranking_score": 101.0,
                "evaluation_status": "passed",
                "notes": [],
            },
        ],
        "notes": [],
    }
    comparison_inputs = (
        {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 103.0,
            "evaluation_summary": "selected passed",
        },
        {
            "candidate_id": "cand-b",
            "variant_id": "variant-b",
            "variant_origin": "deterministic_template_variant",
            "rank": 2,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 102.0,
            "evaluation_summary": "cand-b passed",
        },
        {
            "candidate_id": "cand-c",
            "variant_id": "variant-c",
            "variant_origin": "deterministic_template_variant",
            "rank": 3,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 101.0,
            "evaluation_summary": "cand-c passed",
        },
    )

    prefers_alternative = build_module_synthesis_shadow_predictive_ranking_advisory(
        candidate_winner_priors,
        audit,
        divergence,
        readiness,
        counterfactual,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert (
        prefers_alternative["status"]
        == "shadow_predictive_ranking_prefers_positive_prior_alternative"
    )
    assert prefers_alternative["shadow_policy_id"]
    assert prefers_alternative["shadow_preferred_candidate"]["candidate_id"] == "cand-b"
    assert (
        prefers_alternative["history_summary"]["passing_positive_prior_candidate_count"]
        == 2
    )

    no_signal = build_module_synthesis_shadow_predictive_ranking_advisory(
        {
            **candidate_winner_priors,
            "candidate_priors": [
                {
                    **candidate_winner_priors["candidate_priors"][0],
                    "status": "no_positive_winner_history",
                },
                {
                    **candidate_winner_priors["candidate_priors"][1],
                    "status": "no_positive_winner_history",
                },
            ],
        },
        {
            "status": "no_positive_prior_candidates",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 0,
                "candidate_count": 2,
                "positive_prior_candidate_count": 0,
            },
            "positive_prior_candidates": [],
            "non_selected_positive_prior_candidates": [],
            "notes": [],
        },
        {
            "status": "no_divergence_to_explain",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [],
            "notes": [],
        },
        {
            "status": "insufficient_prior_history",
            "history_summary": {
                "exact_match_receipt_count": 1,
                "replay_healthy_receipt_count": 0,
                "usable_receipt_count": 0,
                "convergent_receipt_count": 0,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 0,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "counterfactual_signal_sparse",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "replay_healthy_receipt_count": 0,
                "positive_prior_signal_receipt_count": 0,
                "passing_positive_prior_candidate_count": 0,
            },
            "counterfactual_positive_prior_candidates": [],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "evaluation_status": "failed",
                "passed": False,
                "ranking_score": 1.0,
                "evaluation_summary": "cand-b failed",
            },
        ),
    )
    assert no_signal["status"] == "no_shadow_predictive_signal"
    assert no_signal["shadow_preferred_candidate"]["candidate_id"] is None

    matches_v7 = build_module_synthesis_shadow_predictive_ranking_advisory(
        {
            **candidate_winner_priors,
            "candidate_priors": [
                {
                    **candidate_winner_priors["candidate_priors"][0],
                    "status": "matches_positive_winner_history",
                },
                {
                    **candidate_winner_priors["candidate_priors"][1],
                    "status": "no_positive_winner_history",
                },
            ],
        },
        {
            "status": "selected_matches_positive_winner_history",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "positive_evidence_count": 1,
                "candidate_count": 2,
                "positive_prior_candidate_count": 1,
            },
            "positive_prior_candidates": [
                {
                    "candidate_id": "cand-a",
                    "variant_id": "variant-a",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 1,
                }
            ],
            "non_selected_positive_prior_candidates": [],
            "notes": [],
        },
        {
            "status": "no_divergence_to_explain",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [],
            "notes": [],
        },
        {
            "status": "insufficient_prior_history",
            "history_summary": {
                "exact_match_receipt_count": 1,
                "replay_healthy_receipt_count": 1,
                "usable_receipt_count": 1,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 0,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "counterfactual_signal_sparse",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "history_summary": {
                "exact_match_receipt_count": 1,
                "replay_healthy_receipt_count": 1,
                "positive_prior_signal_receipt_count": 1,
                "passing_positive_prior_candidate_count": 0,
            },
            "counterfactual_positive_prior_candidates": [],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )
    assert matches_v7["status"] == "shadow_predictive_ranking_matches_v7"
    assert matches_v7["shadow_preferred_candidate"]["candidate_id"] == "cand-a"

    mixed = build_module_synthesis_shadow_predictive_ranking_advisory(
        {
            **candidate_winner_priors,
            "candidate_priors": [
                {
                    **candidate_winner_priors["candidate_priors"][0],
                    "status": "degraded_history_only",
                },
                {
                    **candidate_winner_priors["candidate_priors"][1],
                    "status": "matches_positive_winner_history",
                },
            ],
        },
        {
            "status": "selected_candidate_prior_degraded",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "degraded_history_only",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 3,
                "positive_evidence_count": 1,
                "candidate_count": 2,
                "positive_prior_candidate_count": 1,
            },
            "positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "notes": [],
        },
        {
            "status": "selected_candidate_prior_unresolved",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "degraded_history_only",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [
                {"candidate_id": "cand-b", "comparison_status": "lower_ranked_pass"}
            ],
            "notes": [],
        },
        {
            "status": "priors_mixed_or_inconclusive",
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 1,
                "usable_receipt_count": 3,
                "convergent_receipt_count": 0,
                "runtime_failure_divergence_count": 1,
                "runtime_scoring_divergence_count": 1,
                "mixed_divergence_count": 1,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "counterfactual_signal_mixed_or_inconclusive",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 1,
                "positive_prior_signal_receipt_count": 3,
                "passing_positive_prior_candidate_count": 1,
            },
            "counterfactual_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "rank": 2,
                    "ranking_score": 9.0,
                    "evaluation_status": "passed",
                    "notes": [],
                }
            ],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )
    assert mixed["status"] == "shadow_predictive_ranking_mixed_or_inconclusive"
    assert mixed["shadow_preferred_candidate"]["candidate_id"] is None


def test_build_module_synthesis_shadow_predictive_ranking_advisory_fails_closed_on_counterfactual_comparison_set_drift() -> (
    None
):
    advisory = build_module_synthesis_shadow_predictive_ranking_advisory(
        {
            "candidate_prior_version": "v1",
            "mode": "winner_history_only",
            "history_summary": {
                "exact_match_receipt_count": 2,
                "positive_evidence_count": 2,
                "oracle_neighbor_count": 0,
                "candidate_count": 2,
            },
            "candidate_priors": [
                {
                    "candidate_id": "cand-a",
                    "variant_id": "variant-a",
                    "variant_origin": "deterministic_template_variant",
                    "status": "no_positive_winner_history",
                },
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "status": "matches_positive_winner_history",
                },
            ],
            "notes": [],
        },
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {},
            "positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [
                {"candidate_id": "cand-b", "comparison_status": "lower_ranked_pass"}
            ],
            "notes": [],
        },
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 2,
                "replay_healthy_receipt_count": 2,
                "usable_receipt_count": 2,
                "convergent_receipt_count": 0,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "counterfactual_positive_prior_alternatives_present",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "history_summary": {
                "exact_match_receipt_count": 2,
                "replay_healthy_receipt_count": 2,
                "positive_prior_signal_receipt_count": 2,
                "passing_positive_prior_candidate_count": 0,
            },
            "counterfactual_positive_prior_candidates": [],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert advisory["status"] == "shadow_predictive_ranking_unavailable"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_incomplete_comparison_truth() -> (
    None
):
    advisory = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 3,
                "usable_receipt_count": 3,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 103.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                }
            ],
            "notes": [],
        },
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 3,
                "positive_evidence_count": 3,
                "positive_prior_candidate_count": 1,
            },
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 103.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": None,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert advisory["status"] == "candidate_prior_counterfactual_unavailable"
    assert advisory["counterfactual_positive_prior_candidates"] == []


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_preserves_zero_selected_ranking_score() -> (
    None
):
    advisory = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 3,
                "usable_receipt_count": 3,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 999.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                }
            ],
            "notes": [],
        },
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 3,
                "positive_evidence_count": 3,
                "positive_prior_candidate_count": 1,
            },
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 0.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": -1.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert advisory["selected_candidate"]["ranking_score"] == 0.0


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_unsupported_status_values() -> (
    None
):
    base_readiness = {
        "status": "priors_mostly_outscored_under_v7",
        "history_summary": {},
        "notes": [],
    }
    base_divergence = {
        "status": "divergence_explained_by_runtime_scoring",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "rank": 1,
            "ranking_score": 10.0,
        },
        "compared_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "comparison_status": "lower_ranked_pass",
            }
        ],
        "notes": [],
    }
    base_audit = {
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "history_summary": {},
        "non_selected_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 2,
            }
        ],
        "notes": [],
    }
    comparison_inputs = (
        {
            "candidate_id": "cand-a",
            "rank": 1,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 10.0,
            "evaluation_summary": "selected passed",
        },
        {
            "candidate_id": "cand-b",
            "rank": 2,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 9.0,
            "evaluation_summary": "cand-b passed",
        },
    )

    unsupported_readiness = (
        build_module_synthesis_candidate_prior_counterfactual_advisory(
            {**base_readiness, "status": "NOT_A_REAL_STATUS"},
            base_divergence,
            base_audit,
            ranked_candidate_comparison_inputs=comparison_inputs,
        )
    )
    assert (
        unsupported_readiness["status"] == "candidate_prior_counterfactual_unavailable"
    )

    unsupported_divergence = (
        build_module_synthesis_candidate_prior_counterfactual_advisory(
            base_readiness,
            {**base_divergence, "status": "NOT_A_REAL_DIVERGENCE_STATUS"},
            base_audit,
            ranked_candidate_comparison_inputs=comparison_inputs,
        )
    )
    assert (
        unsupported_divergence["status"] == "candidate_prior_counterfactual_unavailable"
    )

    unsupported_audit = build_module_synthesis_candidate_prior_counterfactual_advisory(
        base_readiness,
        base_divergence,
        {**base_audit, "status": "NOT_A_REAL_AUDIT_STATUS"},
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert unsupported_audit["status"] == "candidate_prior_counterfactual_unavailable"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_selected_candidate_identity_drift() -> (
    None
):
    advisory = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {},
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-z",
                "variant_id": "variant-z",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                }
            ],
            "notes": [],
        },
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {},
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert advisory["status"] == "candidate_prior_counterfactual_unavailable"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_duplicate_compared_candidate_ids() -> (
    None
):
    advisory = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 3,
                "usable_receipt_count": 3,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                }
            ],
            "notes": [],
        },
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 3,
                "positive_evidence_count": 3,
                "positive_prior_candidate_count": 1,
            },
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                },
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b",
                    "variant_origin": "deterministic_template_variant",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                },
            ],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert advisory["status"] == "candidate_prior_counterfactual_unavailable"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_malformed_or_mismatched_divergence_compared_candidates() -> (
    None
):
    base_readiness = {
        "status": "priors_mostly_outscored_under_v7",
        "history_summary": {},
        "notes": [],
    }
    base_audit = {
        "status": "positive_prior_candidates_present_but_not_selected",
        "selected_candidate": {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "prior_status": "no_positive_winner_history",
            "rank": 1,
        },
        "history_summary": {},
        "non_selected_positive_prior_candidates": [
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "matches_positive_winner_history",
                "rank": 2,
            }
        ],
        "notes": [],
    }
    comparison_inputs = (
        {
            "candidate_id": "cand-a",
            "rank": 1,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 10.0,
            "evaluation_summary": "selected passed",
        },
        {
            "candidate_id": "cand-b",
            "rank": 2,
            "evaluation_status": "passed",
            "passed": True,
            "ranking_score": 9.0,
            "evaluation_summary": "cand-b passed",
        },
    )

    malformed = build_module_synthesis_candidate_prior_counterfactual_advisory(
        base_readiness,
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": ["MALFORMED"],
            "notes": [],
        },
        base_audit,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert malformed["status"] == "candidate_prior_counterfactual_unavailable"

    mismatched = build_module_synthesis_candidate_prior_counterfactual_advisory(
        base_readiness,
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-z",
                    "comparison_status": "lower_ranked_pass",
                }
            ],
            "notes": [],
        },
        base_audit,
        ranked_candidate_comparison_inputs=comparison_inputs,
    )
    assert mismatched["status"] == "candidate_prior_counterfactual_unavailable"


def test_build_module_synthesis_candidate_prior_counterfactual_advisory_fails_closed_on_current_comparison_variant_identity_drift() -> (
    None
):
    advisory = build_module_synthesis_candidate_prior_counterfactual_advisory(
        {
            "status": "priors_mostly_outscored_under_v7",
            "history_summary": {
                "exact_match_receipt_count": 3,
                "replay_healthy_receipt_count": 3,
                "usable_receipt_count": 3,
                "convergent_receipt_count": 1,
                "runtime_failure_divergence_count": 0,
                "runtime_scoring_divergence_count": 2,
                "mixed_divergence_count": 0,
                "unresolved_receipt_count": 0,
            },
            "notes": [],
        },
        {
            "status": "divergence_explained_by_runtime_scoring",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "rank": 1,
                "ranking_score": 10.0,
            },
            "compared_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "comparison_status": "lower_ranked_pass",
                }
            ],
            "notes": [],
        },
        {
            "status": "positive_prior_candidates_present_but_not_selected",
            "selected_candidate": {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "prior_status": "no_positive_winner_history",
                "rank": 1,
            },
            "history_summary": {
                "exact_match_receipt_count": 3,
                "positive_evidence_count": 3,
                "positive_prior_candidate_count": 1,
            },
            "non_selected_positive_prior_candidates": [
                {
                    "candidate_id": "cand-b",
                    "variant_id": "variant-b-audit",
                    "variant_origin": "audit-origin",
                    "prior_status": "matches_positive_winner_history",
                    "rank": 2,
                }
            ],
            "notes": [],
        },
        ranked_candidate_comparison_inputs=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 10.0,
                "evaluation_summary": "selected passed",
            },
            {
                "candidate_id": "cand-b",
                "rank": 2,
                "variant_id": "variant-b-runtime",
                "variant_origin": "runtime-origin",
                "evaluation_status": "passed",
                "passed": True,
                "ranking_score": 9.0,
                "evaluation_summary": "cand-b passed",
            },
        ),
    )

    assert advisory["status"] == "candidate_prior_counterfactual_unavailable"


def test_extract_module_synthesis_ranked_candidate_inputs_fails_closed_without_rank_metadata() -> (
    None
):
    synthesis = {
        "promotion_decision": {
            "metadata": {
                "ranked_candidates": [
                    {"candidate_id": "cand-a", "ordinal": 0},
                    {"candidate_id": "cand-b", "rank": 0, "ordinal": 1},
                ]
            }
        },
        "promotion_shell": {
            "metadata": {
                "ranked_candidates": [
                    {"candidate_id": "cand-a", "rank": 1, "ordinal": 0},
                    {"candidate_id": "cand-b", "rank": 2, "ordinal": 1},
                ]
            }
        },
    }

    ranked_candidates = extract_module_synthesis_ranked_candidate_inputs(synthesis)

    assert ranked_candidates == (
        {"candidate_id": "cand-a", "rank": 1, "variant_id": None, "ordinal": 0},
        {"candidate_id": "cand-b", "rank": 2, "variant_id": None, "ordinal": 1},
    )


def test_build_module_synthesis_candidate_prior_audit_omits_fabricated_rank_context() -> (
    None
):
    current_candidates = (
        {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "ordinal": 0,
        },
        {
            "candidate_id": "cand-b",
            "variant_id": "variant-b",
            "variant_origin": "deterministic_template_variant",
            "ordinal": 1,
        },
    )
    candidate_winner_priors = {
        "candidate_prior_version": "v1",
        "mode": "winner_history_only",
        "history_summary": {
            "exact_match_receipt_count": 1,
            "positive_evidence_count": 1,
            "candidate_count": 2,
        },
        "candidate_priors": [
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "status": "matches_positive_winner_history",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "status": "no_positive_winner_history",
            },
        ],
        "notes": [],
    }

    audit = build_module_synthesis_candidate_prior_audit(
        candidate_winner_priors,
        current_candidates=current_candidates,
        ranked_candidates=(),
        selected_candidate_id="cand-a",
    )

    assert audit["selected_candidate"]["rank"] is None
    assert audit["positive_prior_candidates"][0]["rank"] is None
    assert any("ranked-candidate order unavailable" in note for note in audit["notes"])


def test_build_module_synthesis_candidate_prior_audit_omits_partial_rank_context() -> (
    None
):
    current_candidates = (
        {
            "candidate_id": "cand-a",
            "variant_id": "variant-a",
            "variant_origin": "deterministic_template_variant",
            "ordinal": 0,
        },
        {
            "candidate_id": "cand-b",
            "variant_id": "variant-b",
            "variant_origin": "deterministic_template_variant",
            "ordinal": 1,
        },
    )
    candidate_winner_priors = {
        "candidate_prior_version": "v1",
        "mode": "winner_history_only",
        "history_summary": {
            "exact_match_receipt_count": 1,
            "positive_evidence_count": 1,
            "candidate_count": 2,
        },
        "candidate_priors": [
            {
                "candidate_id": "cand-a",
                "variant_id": "variant-a",
                "variant_origin": "deterministic_template_variant",
                "status": "no_positive_winner_history",
            },
            {
                "candidate_id": "cand-b",
                "variant_id": "variant-b",
                "variant_origin": "deterministic_template_variant",
                "status": "matches_positive_winner_history",
            },
        ],
        "notes": [],
    }

    audit = build_module_synthesis_candidate_prior_audit(
        candidate_winner_priors,
        current_candidates=current_candidates,
        ranked_candidates=(
            {
                "candidate_id": "cand-a",
                "rank": 1,
                "variant_id": "variant-a",
                "ordinal": 0,
            },
        ),
        selected_candidate_id="cand-a",
    )

    assert audit["status"] == "positive_prior_candidates_present_but_not_selected"
    assert audit["selected_candidate"]["rank"] is None
    assert audit["positive_prior_candidates"][0]["rank"] is None
    assert any("ranked-candidate order incomplete" in note for note in audit["notes"])
