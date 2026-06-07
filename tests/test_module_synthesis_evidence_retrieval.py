from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.dtos import ModuleSpec
from dspx.services.module_synthesis_evidence import (
    build_module_synthesis_candidate_prior_readiness_advisory,
    build_module_synthesis_history_advisory,
    retrieve_module_synthesis_evidence,
)
from module_synthesis_evidence_helpers import (
    _generate_module_receipt,
    _generate_signature_receipt,
    _index_receipt,
)


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
def test_retrieve_module_synthesis_evidence_rejects_wrongly_typed_governed_policy_fields(
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
        {
            "policy_evaluation_receipt_version": False,
            "evaluation_contract_version": "v1",
            "variant_class": "ranking_evaluation",
            "variant_policy_id": "policy-id",
            "variant_policy_version": "v1",
            "variant_policy_mode": "governance_only",
            "outcome": "match",
            "authority_limit": "governance_only",
            "decision_rule_summary": "summary",
            "live_policy_context": {},
            "request_context": {},
            "bounded_inputs": {},
            "evaluation_result": {},
            "promotion_authority": {},
        }
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
    assert bundle.receipt_scan_errors[0]["field"] == "policy_evaluation_receipt_version"


@pytest.mark.slow
def test_retrieve_module_synthesis_evidence_rejects_wrongly_typed_run_summary_fields(
    tmp_path: Path, monkeypatch
) -> None:
    meta_path = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="single.py",
    )
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    run_summary = dict(payload.get("run_summary") or {})
    run_summary["selected_candidate_rank"] = True
    payload["run_summary"] = run_summary
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
        == "receipt_invalid_selected_candidate_rank"
    )


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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
