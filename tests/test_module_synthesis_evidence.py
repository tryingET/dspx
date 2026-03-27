from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateIndex, get_embedding_engine
from dspx.dtos import ModuleSpec
from dspx.run_receipts import load_run_receipt
from dspx.services.module_synthesis_evidence import (
    build_module_synthesis_candidate_winner_priors,
    build_module_synthesis_history_advisory,
    extract_module_synthesis_candidate_prior_inputs,
    retrieve_module_synthesis_evidence,
)


runner = CliRunner()


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
    assert all(item["run_kind"] == "module-gen" for item in payload["oracle_neighbors"])


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
    current_candidates = extract_module_synthesis_candidate_prior_inputs(
        json.loads(exact_ok.read_text(encoding="utf-8"))["synthesis"]
    )

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
