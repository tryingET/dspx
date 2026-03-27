from __future__ import annotations

import json
from pathlib import Path

from dspx.dtos import ModuleSpec
import dspx.services.module_service as module_service
from dspx.services.module_service import run_generate


def test_module_service_simple_no_signature(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_RECEIPTS_PATH",
        str(tmp_path / "receipts"),
    )
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_INDEX_PATH",
        str(tmp_path / "oracle" / "coordinates.db"),
    )
    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    art = run_generate(spec, use_signature=False)
    assert "class Summarizer(dspy.Module):" in art.code
    assert "self.predict = dspy.Predict('text -> summary')" in art.code
    assert "def forward(self, text: str)" in art.code
    assert '"""Construct the generated module for runtime selection."""' in art.code

    synthesis = art.metadata["synthesis"]
    assert synthesis["request"]["artifact_kind"] == "module"
    assert synthesis["request"]["spec"]["name"] == "Summarizer"
    assert synthesis["strategy"]["strategy_id"] == "module.multi_candidate.template"
    assert len(synthesis["candidates"]) >= 2
    assert synthesis["candidates"][-1]["artifact"]["content_hash"]
    assert any(item["status"] == "selected" for item in synthesis["candidates"])
    assert (
        sum(1 for item in synthesis["evaluations"] if item["status"] == "passed") >= 2
    )
    assert synthesis["promotion_decision"]["outcome"] == "withheld"
    assert synthesis["promotion_shell"]["status"] == "ready"
    workspace = synthesis["candidate_workspaces"][0]
    assert Path(workspace["artifact_path"]).exists()
    assert Path(workspace["manifest_path"]).exists()
    assert synthesis["promotion_shell"]["target_path"].endswith("Summarizer.py")
    assert art.metadata["run_summary"]["candidate_count"] >= 2
    assert art.metadata["run_summary"]["selected_candidate_rank"] == 1
    assert art.metadata["run_summary"]["validation_pass_rate"] == 1.0
    assert art.metadata["run_summary"]["smoke_pass_rate"] == 1.0

    diagnostics = art.metadata["synthesis_diagnostics"]
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
    assert (
        diagnostics["historical_convergence_advisory"]["selected_artifact"][
            "selected_candidate_id"
        ]
        == art.metadata["selected_candidate_id"]
    )


def test_module_service_simple_with_signature(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_RECEIPTS_PATH",
        str(tmp_path / "receipts"),
    )
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_INDEX_PATH",
        str(tmp_path / "oracle" / "coordinates.db"),
    )
    spec = ModuleSpec(
        name="Intent",
        description="Extracts intent from context",
        inputs=["context"],
        outputs=["output"],
        options={"template_version": "simple-v1"},
    )
    art = run_generate(spec, use_signature=True)
    assert "class Sig_Intent(dspy.Signature):" in art.code
    assert "self.predict = dspy.Predict(Sig_Intent)" in art.code
    assert "def forward(self, context: str)" in art.code
    assert '"""Construct the generated module for runtime selection."""' in art.code

    synthesis = art.metadata["synthesis"]
    assert synthesis["request"]["spec"]["use_signature"] is True
    assert synthesis["request"]["spec"]["template_version"] == "simple-v1"
    assert all(item["status"] == "passed" for item in synthesis["evaluations"])
    assert synthesis["evaluations"][0]["evidence"]["smoke"]["module-smoke"] is True
    assert (
        synthesis["selection_policy"]["policy_id"] == "module.v7.multi-candidate-ranked"
    )
    assert synthesis["strategy"]["metadata"]["use_signature"] is True
    assert (
        synthesis["strategy"]["metadata"]["fan_out_kind"]
        == "deterministic_template_variants"
    )
    assert synthesis["candidate_workspaces"][0]["metadata"]["strategy_version"] == "v0"
    assert synthesis["promotion_shell"]["status"] == "ready"
    assert art.metadata["backend"] == "synthesis_runtime"
    assert (
        art.metadata["synthesis_diagnostics"]["evidence_bundle"]["request"][
            "use_signature"
        ]
        is True
    )
    assert (
        art.metadata["synthesis_diagnostics"]["historical_convergence_advisory"][
            "status"
        ]
        == "no_history"
    )


def test_module_service_degrades_diagnostics_when_evidence_is_partially_broken(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_RECEIPTS_PATH",
        str(tmp_path / "receipts"),
    )
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_INDEX_PATH",
        str(tmp_path / "oracle" / "coordinates.db"),
    )

    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    malformed = receipts_dir / "bad.meta.json"
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
    art = run_generate(spec, use_signature=False)

    diagnostics = art.metadata["synthesis_diagnostics"]
    assert diagnostics["retrieval_status"] == "degraded"
    assert diagnostics["evidence_summary"]["receipt_scan_error_count"] == 1
    assert diagnostics["evidence_summary"]["oracle_lookup_status"] == "unavailable"
    assert diagnostics["evidence_bundle"]["receipt_scan_errors"][0][
        "receipt_path"
    ] == str(malformed)
    assert diagnostics["evidence_bundle"]["oracle_lookup_error"]["type"]
    assert "ignored 1 malformed exact-match receipt(s)" in " ".join(
        diagnostics["historical_convergence_advisory"]["notes"]
    )


def test_module_service_preserves_diagnostics_shape_when_evidence_retrieval_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "0")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_MODULE_SYNTHESIS_QUALITY_ENABLE", "0")

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(module_service, "retrieve_module_synthesis_evidence", _boom)

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    art = run_generate(spec, use_signature=False)

    diagnostics = art.metadata["synthesis_diagnostics"]
    assert diagnostics["retrieval_status"] == "unavailable"
    assert diagnostics["retrieval_error"]["type"] == "RuntimeError"
    assert diagnostics["evidence_summary"] == {
        "exact_match_receipt_count": 0,
        "positive_evidence_count": 0,
        "oracle_neighbor_count": 0,
        "oracle_index_available": False,
        "oracle_lookup_status": "unavailable",
        "receipt_scan_error_count": 0,
    }
    assert diagnostics["evidence_bundle"]["request"]["name"] == "Summarizer"
    assert diagnostics["evidence_bundle"]["oracle_lookup_status"] == "unavailable"
    assert diagnostics["evidence_bundle"]["exact_match_receipt_scan_errors"] == []
    assert diagnostics["evidence_bundle"]["exact_match_receipt_scan_error_count"] == 0
    assert (
        diagnostics["evidence_bundle"]["oracle_lookup_error"]["type"] == "RuntimeError"
    )
    assert diagnostics["historical_convergence_advisory"]["status"] == "unavailable"


def test_module_service_surfaces_quality_event_failures_in_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "0")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_MODULE_SYNTHESIS_QUALITY_ENABLE", "1")

    def _boom(*args, **kwargs):
        raise RuntimeError("quality broken")

    monkeypatch.setattr(
        module_service, "build_module_quality_event_from_metadata", _boom
    )

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    art = run_generate(spec, use_signature=False)

    assert art.metadata["quality_event_status"] == "unavailable"
    assert art.metadata["quality_event_error"]["type"] == "RuntimeError"
    assert art.metadata["quality_event_error"]["message"] == "quality broken"
    assert "quality_event" not in art.metadata
