from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.dtos import ModuleSpec
from dspx.services.module_synthesis_evidence import (
    build_module_synthesis_candidate_prior_audit,
    build_module_synthesis_candidate_winner_priors,
    build_module_synthesis_history_advisory,
    extract_module_synthesis_candidate_prior_inputs,
    extract_module_synthesis_ranked_candidate_inputs,
    retrieve_module_synthesis_evidence,
)
from module_synthesis_evidence_helpers import (
    _generate_module_receipt,
)


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
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
