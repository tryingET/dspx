# summary: "Tests AK-5362 provider_evidence_kind labelling across Oracle sidecars, foundry.json, GEPA receipts, comparisons, and jury execution requests."
# read_when:
#   - "Changing program_foundry_provider_evidence.py or any artifact that carries provider_evidence_kind."

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

import pytest

import dspx.services.program_foundry as foundry
import dspx.services.program_foundry_gepa_comparison_jury as comparison_jury
import dspx.services.program_foundry_gepa_execution as execution
from dspx.services.program_foundry_gepa_comparison_jury_runtime import (
    ProgramFoundryGepaComparisonJuryError,
    execution_request,
    revalidate_execution_request,
)
from dspx.services.program_foundry_provider_evidence import (
    PROVIDER_EVIDENCE_KINDS,
    lineage_provider_evidence,
    provider_evidence_kind_for_model,
    provider_evidence_kind_for_provider,
    provider_evidence_kind_from_behavior_results,
    provider_evidence_kind_from_gepa_result,
    provider_evidence_kind_from_interpretation,
    provider_evidence_kind_from_oracle_result,
    validate_optional_provider_evidence_kind,
    weakest_provider_evidence_kind,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_refinement_comparison import (
    build_program_refinement_candidate_comparison,
    validate_program_refinement_candidate_comparison_contract,
)
from dspx.services.program_service import materialize_program_from_intent
from test_program_foundry import (
    _env,
    _inputs,
    _quality_artifacts,
    _successful_semantic_stub,
)
from test_program_foundry_gepa_comparison_jury import (
    _fixture,
    _install_success,
    _sha256,
)
from test_program_foundry_gepa_execution import _completed_result, _proposal
from test_program_refinement_comparison import _setup_env, _write_runtime_episode

DOCS_PROJECT = Path(__file__).resolve().parents[1] / "docs" / "project"


@pytest.fixture(autouse=True)
def _in_process_jury(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comparison_jury, "_CHILD_ARGV", None)


# --- closed derivation -----------------------------------------------------------


def test_kinds_are_closed_and_derived_from_actual_runtimes() -> None:
    assert PROVIDER_EVIDENCE_KINDS == ("live", "authored_fixture_replay", "stub_echo")
    assert provider_evidence_kind_for_provider("openai-compatible") == "live"
    assert provider_evidence_kind_for_provider("stub") == "stub_echo"
    assert (
        provider_evidence_kind_for_provider("foundry-dspy-lm-auth-local-vllm") == "live"
    )
    assert provider_evidence_kind_for_provider("fixture-provider") is None
    assert provider_evidence_kind_for_provider(None) is None
    assert provider_evidence_kind_for_model("stub/echo") == "stub_echo"
    assert (
        provider_evidence_kind_for_model("local/Qwen3.8-27B-AEON-NVFP4-FP8") == "live"
    )
    assert provider_evidence_kind_for_model("codex/gpt-5.6-sol") is None
    runtime_stub = {
        "provider": {
            "status": "configured",
            "metadata": {"provider": "stub", "model": "stub/echo"},
        }
    }
    runtime_live = {
        "provider": {
            "status": "configured",
            "metadata": {"provider": "openai-compatible", "model": "local/x"},
        }
    }
    generated_stub = {"provider": {"status": "configured", "provider": "stub/echo"}}
    assert provider_evidence_kind_from_behavior_results(runtime_stub) == "stub_echo"
    assert provider_evidence_kind_from_behavior_results(runtime_live) == "live"
    assert provider_evidence_kind_from_behavior_results(generated_stub) == "stub_echo"
    assert (
        provider_evidence_kind_from_behavior_results(
            {"provider": {"status": "unavailable", "provider": "stub/echo"}}
        )
        is None
    )
    assert provider_evidence_kind_from_behavior_results(None) is None
    assert (
        provider_evidence_kind_from_oracle_result(
            {"backend_kind": "fixture-replay", "execution_status": "replayed_fixture"}
        )
        == "authored_fixture_replay"
    )
    assert (
        provider_evidence_kind_from_oracle_result(
            {
                "backend_kind": "live",
                "execution_status": "succeeded",
                "live_call_succeeded": True,
                "executed_provider": "openai-compatible",
            }
        )
        == "live"
    )
    assert (
        provider_evidence_kind_from_oracle_result(
            {
                "backend_kind": "live",
                "execution_status": "failed_after_live_response",
                "live_call_succeeded": True,
                "executed_provider": "openai-compatible",
            }
        )
        is None
    )
    assert (
        provider_evidence_kind_from_gepa_result(
            {
                "gepa": {
                    "attempted": True,
                    "status": "completed",
                    "student_provider": "stub",
                    "reflection_provider": "stub",
                }
            }
        )
        == "stub_echo"
    )
    assert (
        provider_evidence_kind_from_gepa_result(
            {
                "gepa": {
                    "attempted": True,
                    "status": "completed",
                    "student_provider": "openai-compatible",
                    "reflection_provider": "openai-compatible",
                }
            }
        )
        == "live"
    )
    assert (
        provider_evidence_kind_from_gepa_result({"gepa": {"attempted": False}}) is None
    )


def test_lineage_kind_is_the_weakest_link_and_unknown_never_upgrades() -> None:
    assert weakest_provider_evidence_kind("live", "live") == "live"
    assert weakest_provider_evidence_kind("live", "authored_fixture_replay") == (
        "authored_fixture_replay"
    )
    assert weakest_provider_evidence_kind("live", "stub_echo") == "stub_echo"
    assert weakest_provider_evidence_kind("authored_fixture_replay", "stub_echo") == (
        "stub_echo"
    )
    assert weakest_provider_evidence_kind("live", None) is None
    assert weakest_provider_evidence_kind(None, "stub_echo") == "stub_echo"
    assert weakest_provider_evidence_kind() is None
    with pytest.raises(ValueError, match="unknown provider evidence kind"):
        weakest_provider_evidence_kind("live", "mock")
    lineage = lineage_provider_evidence(
        {
            "program_run": "live",
            "oracle_semantic": "authored_fixture_replay",
            "gepa": None,
        }
    )
    assert lineage["lineage"] == "authored_fixture_replay"
    assert lineage["absent_means"] == "unknown"
    assert validate_optional_provider_evidence_kind(None) is None
    assert validate_optional_provider_evidence_kind("live") == "live"
    with pytest.raises(ValueError, match="must be one of"):
        validate_optional_provider_evidence_kind("mock")
    assert (
        provider_evidence_kind_from_interpretation(
            {"interpretation": {"provider_evidence_kind": "stub_echo"}}
        )
        == "stub_echo"
    )
    assert provider_evidence_kind_from_interpretation({"interpretation": {}}) is None
    assert provider_evidence_kind_from_interpretation({"status": "compared"}) is None


# --- foundry.json, Oracle sidecar, GEPA receipt ---------------------------------


def test_foundry_summary_labels_program_run_and_oracle_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)
    intent = tmp_path / "intent.json"
    proposal = tmp_path / "quality-proposal.json"
    inputs = tmp_path / "inputs.json"
    root = tmp_path / "foundry"
    _quality_artifacts(intent, proposal)
    _inputs(inputs)
    monkeypatch.setattr(
        foundry, "run_program_runtime_oracle_semantics", _successful_semantic_stub
    )

    payload = foundry.run_program_foundry(
        intent_path=intent,
        quality_proposal_path=proposal,
        inputs_path=inputs,
        outdir=root,
        skip_oracle_index=True,
    )

    assert payload["provider_evidence"] == {
        "schema_version": "dspx-provider-evidence-kind-v1",
        "links": {
            "program_run": "stub_echo",
            "oracle_semantic": "authored_fixture_replay",
            "gepa": None,
        },
        "lineage": "stub_echo",
        "closed_values": ["live", "authored_fixture_replay", "stub_echo"],
        "absent_means": "unknown",
    }
    assert payload["stages"]["runtime"]["provider_evidence_kind"] == "stub_echo"
    assert (
        payload["stages"]["oracle_semantic"]["provider_evidence_kind"]
        == "authored_fixture_replay"
    )
    summary = json.loads((root / "foundry.json").read_text(encoding="utf-8"))
    assert summary["provider_evidence"] == payload["provider_evidence"]


def test_gepa_execution_receipt_labels_optimizer_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal_path = _proposal(tmp_path, monkeypatch)
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))

    def fake_build(**kwargs: Any) -> dict[str, Any]:
        result = _completed_result(**kwargs)
        result["gepa"].update(
            {"student_provider": "stub", "reflection_provider": "stub"}
        )
        return result

    monkeypatch.setattr(execution, "build_program_refinement_gepa_result", fake_build)
    first = execution.execute_reviewed_program_foundry_gepa(
        proposal_path=proposal_path,
        declared_reviewed=proposal["proposal_id"],
        operator_label="local-operator",
    )
    second = execution.execute_reviewed_program_foundry_gepa(
        proposal_path=proposal_path,
        declared_reviewed=proposal["proposal_id"],
        operator_label="local-operator",
    )

    assert first["provider_evidence_kind"] == "stub_echo"
    assert second["reused"] is True
    assert second["provider_evidence_kind"] == "stub_echo"
    receipt = json.loads(
        (proposal_path.parent / "gepa-experiment" / "execution-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["provider_evidence_kind"] == "stub_echo"


# --- candidate comparison --------------------------------------------------------


def test_candidate_comparison_interpretation_carries_provider_evidence_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    source = materialize_program_from_intent(
        ProgramIntent(
            name="RuntimeOnlySource",
            objective="Answer a question.",
            inputs=["ticket_text"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    candidate = materialize_program_from_intent(
        ProgramIntent(
            name="RuntimeOnlyCandidate",
            objective="Answer a question.",
            inputs=["ticket_text"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program-v2",
    )
    source_root = Path(source.root_path)
    candidate_root = Path(candidate.root_path)
    source_runtime = _write_runtime_episode(
        source_root, tmp_path / "source-runtime", text="Server is down"
    )
    candidate_runtime = _write_runtime_episode(
        candidate_root, tmp_path / "candidate-runtime", text="Server is down"
    )

    payload = build_program_refinement_candidate_comparison(
        source_manifest_path=source_root / "manifest.json",
        candidate_manifest_path=candidate_root / "manifest.json",
        source_runtime_episode_path=source_runtime,
        candidate_runtime_episode_path=candidate_runtime,
    )

    interpretation = payload["interpretation"]
    assert interpretation["provider_evidence_kind"] == "stub_echo"
    assert interpretation["provider_evidence_links"] == {
        "source_generated_behavior": None,
        "candidate_generated_behavior": None,
        "source_runtime_behavior": "stub_echo",
        "candidate_runtime_behavior": "stub_echo",
    }
    assert (
        payload["runtime_evidence_comparison"]["interpretation"][
            "provider_evidence_kind"
        ]
        == "stub_echo"
    )
    assert any("provider_evidence_kind" in limit for limit in interpretation["limits"])
    comparison_path = tmp_path / "comparison.json"
    comparison_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    validated = validate_program_refinement_candidate_comparison_contract(
        comparison_path=comparison_path,
        candidate_manifest_path=candidate_root / "manifest.json",
        source_manifest_path=source_root / "manifest.json",
    )
    assert validated["interpretation"]["provider_evidence_kind"] == "stub_echo"


# --- jury execution request -------------------------------------------------------


def test_execution_request_accepts_absent_or_closed_label_only() -> None:
    plain = execution_request(
        provider="stub",
        adjudicator_id="local",
        adjudicator_kind="local",
        adjudicator_repo=None,
        max_jurors=1,
    )
    assert "provider_evidence_kind" not in plain
    assert revalidate_execution_request(plain) == plain
    labelled = execution_request(
        provider="stub",
        adjudicator_id="local",
        adjudicator_kind="local",
        adjudicator_repo=None,
        max_jurors=1,
        provider_evidence_kind="stub_echo",
    )
    assert labelled == {**plain, "provider_evidence_kind": "stub_echo"}
    assert revalidate_execution_request(labelled) == labelled
    with pytest.raises(ProgramFoundryGepaComparisonJuryError, match="must be one of"):
        execution_request(
            provider="stub",
            adjudicator_id="local",
            adjudicator_kind="local",
            adjudicator_repo=None,
            max_jurors=1,
            provider_evidence_kind="mock",
        )
    with pytest.raises(ProgramFoundryGepaComparisonJuryError, match="must be one of"):
        revalidate_execution_request({**plain, "provider_evidence_kind": "mock"})
    with pytest.raises(
        ProgramFoundryGepaComparisonJuryError, match="types are invalid"
    ):
        revalidate_execution_request({**labelled, "extra": 1})


def test_retained_pre_label_jury_receipts_still_revalidate() -> None:
    receipts = 0
    for path in sorted(glob.glob(str(DOCS_PROJECT / "*-evidence.json"))):
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        artifacts = document.get("artifacts") or {}
        jury_receipt = artifacts.get("jury_receipt")
        if not isinstance(jury_receipt, dict):
            continue
        projection = jury_receipt.get("projection")
        if not isinstance(projection, dict):
            continue
        request = projection.get("execution_request")
        if not isinstance(request, dict):
            continue
        receipts += 1
        assert "provider_evidence_kind" not in request, path
        assert revalidate_execution_request(request) == request, path
    assert receipts >= 5, "AK-5346/5352/5358/5360/5361 receipts must be present"


def _labelled_fixture(tmp_path: Path, kind: str | None) -> tuple[Path, dict[str, Any]]:
    receipt, validated = _fixture(tmp_path)
    comparison = Path(validated["comparison_path"])
    payload: dict[str, Any] = {
        "schema_version": "program-refinement-candidate-comparison-v1",
        "status": "compared",
    }
    if kind is not None:
        payload["interpretation"] = {"provider_evidence_kind": kind}
    comparison.write_text(json.dumps(payload), encoding="utf-8")
    validated["comparison_sha256"] = _sha256(comparison)
    return receipt, validated


def test_jury_request_carries_weakest_lineage_label_and_reuses_retained_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _labelled_fixture(tmp_path, "stub_echo")
    execution_receipt = Path(validated["execution_receipt_path"])
    execution_receipt.write_text(
        json.dumps({"status": "ok", "provider_evidence_kind": "live"}),
        encoding="utf-8",
    )
    validated["execution_receipt_sha256"] = _sha256(execution_receipt)
    runtime_dir = Path(validated["root"]) / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "program_oracle_semantic.json").write_text(
        json.dumps({"provider_evidence_kind": "authored_fixture_replay"}),
        encoding="utf-8",
    )
    calls: list[dict[str, Any]] = []
    _install_success(monkeypatch, validated, calls)

    first = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt, provider="stub", max_jurors=1
    )
    assert first["execution_request"]["provider_evidence_kind"] == "stub_echo"
    attempt = json.loads(
        (validated["experiment_root"] / "comparison-jury-attempt.json").read_text(
            encoding="utf-8"
        )
    )
    assert attempt["execution_request"]["provider_evidence_kind"] == "stub_echo"
    receipt_payload = json.loads(
        (validated["experiment_root"] / "comparison-jury-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt_payload["schema_version"] == (
        "dspx-program-foundry-gepa-comparison-jury-v1"
    )
    assert receipt_payload["execution_request"]["provider_evidence_kind"] == "stub_echo"

    # A later run recomputing a different lineage must reuse the retained label.
    monkeypatch.setattr(
        comparison_jury, "lineage_provider_evidence_kind", lambda *a, **k: "live"
    )
    second = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt, provider="stub", max_jurors=1
    )
    assert second["reused"] is True
    assert second["execution_request"]["provider_evidence_kind"] == "stub_echo"
    assert len(calls) == 1


def test_jury_request_omits_label_when_any_link_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _labelled_fixture(tmp_path, None)
    calls: list[dict[str, Any]] = []
    _install_success(monkeypatch, validated, calls)

    first = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt, provider="fixture-provider", max_jurors=1
    )
    assert "provider_evidence_kind" not in first["execution_request"]
    lineage = comparison_jury.lineage_provider_evidence_kind(
        validated, jury_provider="fixture-provider"
    )
    assert lineage is None
    # A live jury over an unknown lineage stays unknown; a stub jury decides it.
    assert (
        comparison_jury.lineage_provider_evidence_kind(
            validated, jury_provider="foundry-dspy-lm-auth-local-vllm"
        )
        is None
    )
    assert (
        comparison_jury.lineage_provider_evidence_kind(validated, jury_provider="stub")
        == "stub_echo"
    )
    second = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt, provider="fixture-provider", max_jurors=1
    )
    assert second["reused"] is True
    assert "provider_evidence_kind" not in second["execution_request"]
