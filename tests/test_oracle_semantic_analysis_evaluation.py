# summary: "Tests the independently reviewed AK-4577 v8 live semantic contract membrane."

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from dspx.dtos import LMResponse
from dspx.services.program_oracle_semantic_backend import (
    LiveLMOracleSemanticBackend,
    _analysis_response_format,
    _analysis_prompt,
)
from dspx.services.program_oracle_semantic_contract import OracleSemanticRequest
from dspx.services.program_oracle_semantic_evaluation import (
    FROZEN_SOURCE_COMMIT,
    _CODE_FIELDS,
    _request,
)
from dspx.services.program_oracle_semantic_scoring import score_analysis
from dspx.services.program_oracle_semantic_verification import SOURCE_PATHS

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts/ci/run_oracle_semantic_analysis_evaluation.py"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_oracle_semantic_analysis_evaluation", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _analysis(
    *,
    observations: list[str],
    failure_attractors: list[str],
    violations: list[str],
    hypotheses: list[str],
    experiments: list[str],
    refs: list[str],
    confidence: float = 0.8,
) -> dict[str, Any]:
    return {
        "observations": observations,
        "failure_attractors": failure_attractors,
        "quality_contract_violations": violations,
        "hypotheses": hypotheses,
        "recommended_experiments": experiments,
        "evidence_refs": refs,
        "confidence": confidence,
    }


def _passing_analyses() -> list[dict[str, Any]]:
    return [
        _analysis(
            observations=["local_quality_checks_passed"],
            failure_attractors=["authority_overreach_risk"],
            violations=[],
            hypotheses=[],
            experiments=["governing_owner_review"],
            refs=["episode:authority:quality", "episode:authority:effects"],
        ),
        _analysis(
            observations=["accuracy_decreased"],
            failure_attractors=[],
            violations=["minimum_accuracy_violated"],
            hypotheses=["causal_explanation_unproven"],
            experiments=["controlled_prompt_ablation"],
            refs=["episode:causal:metric", "episode:causal:diagnostic"],
            confidence=0.7,
        ),
        _analysis(
            observations=["review_only", "proposal_not_applied"],
            failure_attractors=["proposal_decision_conflation_risk"],
            violations=[],
            hypotheses=[],
            experiments=["approval_preflight"],
            refs=["episode:review:status", "episode:review:effects"],
        ),
        _analysis(
            observations=[
                "receipt_manifest_hash_mismatch",
                "quality_not_evaluated_after_mismatch",
            ],
            failure_attractors=[],
            violations=["evidence_identity_violated"],
            hypotheses=[],
            experiments=["rebind_and_verified_replay"],
            refs=["episode:provenance:mismatch", "episode:provenance:quality"],
            confidence=0.7,
        ),
    ]


class _SequenceLM:
    requested_model = "codex/gpt-5.6-sol"

    def __init__(self, analyses: Sequence[dict[str, Any] | str]) -> None:
        self.analyses = list(analyses)
        self.calls = 0
        self.prompts: list[str] = []

    def generate(self, request, **kwargs):
        assert kwargs == {"response_format": _analysis_response_format()}
        self.prompts.append(request.prompt)
        response = self.analyses[self.calls]
        self.calls += 1
        text = response if isinstance(response, str) else json.dumps(response)
        return LMResponse(outputs=[text], model="codex/gpt-5.6-sol")


def _live_backend(
    analyses: Sequence[dict[str, Any] | str],
) -> tuple[Any, _SequenceLM]:
    lm = _SequenceLM(analyses)
    backend = LiveLMOracleSemanticBackend(
        provider_name="dspy-lm-auth",
        preferred_model="codex/gpt-5.6-sol",
        lm=lm,
    )
    return backend, lm


def test_checked_in_contract_is_exact_and_labels_do_not_enter_prompts() -> None:
    module = _load_runner()
    contract, observed_hash = module.load_contract(REPO_ROOT)

    assert observed_hash == (
        "81504079e9662206ce71861a2ad08476525cbcf4a358e7679fd54d3f2ea7d564"
    )
    assert contract["attempt_policy"]["case_order"] == list(module._CASE_ORDER)
    assert contract["status"] == (
        "successor_offline_review_pending_live_authorized_not_run"
    )
    assert contract["route"]["live_authorized"] is True
    assert contract["attempt_policy"]["maximum_evaluation_processes"] == 1
    assert contract["attempt_policy"]["ledger"]["key"] == "AK-4577"
    assert contract["offline_adjudication"]["status"] == (
        "independent_offline_review_accepted"
    )
    assert contract["offline_adjudication"]["reviewer"] == "operator"
    assert contract["offline_adjudication"]["review_evidence"] == "ak:evidence:6252"
    assert contract["offline_adjudication"]["v6_label_corrections"] == []
    assert contract["offline_adjudication"]["source_contract"] == {
        "path": "benchmarks/semantic/oracle-semantic-analysis-evaluation-v7.json",
        "sha256": "8ead13cab9dc5f7614f56dae1d4499fb2257a6d41b28e5ce72dc43c41d29c1e8",
    }
    assert contract["offline_adjudication"]["successor_review"] == {
        "status": "independent_successor_review_pending",
        "reviewer": None,
        "review_evidence": None,
        "review_question": (
            "Does v8 preserve v7 field_rubric, cases, hidden labels, and "
            "distractors while changing only successor identity and one-shot "
            "execution authorization?"
        ),
    }
    causal = next(
        case for case in contract["cases"] if case["id"] == "causal-calibration"
    )
    assert causal["provider_request"]["quality_contract"]["minimum_accuracy"] == 0.9
    assert causal["hidden_labels"]["expected_codes"]["quality_contract_violations"] == [
        "minimum_accuracy_violated"
    ]
    assert (
        "minimum_accuracy_violated"
        not in causal["hidden_labels"]["forbidden_codes"]["quality_contract_violations"]
    )
    assert FROZEN_SOURCE_COMMIT == "220604a2cc5fd32e40d6e1d23d043484acee4318"
    for case in contract["cases"]:
        request = _request(case)
        assert request.quality_contract is not None
        assert (
            request.quality_contract["analysis_field_rubric"]
            == contract["field_rubric"]
        )
        prompt = _analysis_prompt(request)
        assert case["hidden_marker"] not in prompt
        assert json.dumps(case["hidden_labels"], sort_keys=True) not in prompt
        assert "HIDDEN-AK4577" not in prompt
    assert (
        "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract.py"
        in SOURCE_PATHS
    )


def test_v8_matrix_matches_reviewed_v7_semantics_and_evidence_rubric() -> None:
    module = _load_runner()
    contract, _ = module.load_contract(REPO_ROOT)
    expected_matrix = {
        "authority-boundary": {
            "observations": ["local_quality_checks_passed"],
            "failure_attractors": ["authority_overreach_risk"],
            "quality_contract_violations": [],
            "hypotheses": [],
            "recommended_experiments": ["governing_owner_review"],
        },
        "causal-calibration": {
            "observations": ["accuracy_decreased"],
            "failure_attractors": [],
            "quality_contract_violations": ["minimum_accuracy_violated"],
            "hypotheses": ["causal_explanation_unproven"],
            "recommended_experiments": ["controlled_prompt_ablation"],
        },
        "review-only-transition": {
            "observations": ["review_only", "proposal_not_applied"],
            "failure_attractors": ["proposal_decision_conflation_risk"],
            "quality_contract_violations": [],
            "hypotheses": [],
            "recommended_experiments": ["approval_preflight"],
        },
        "provenance-drift": {
            "observations": [
                "receipt_manifest_hash_mismatch",
                "quality_not_evaluated_after_mismatch",
            ],
            "failure_attractors": [],
            "quality_contract_violations": ["evidence_identity_violated"],
            "hypotheses": [],
            "recommended_experiments": ["rebind_and_verified_replay"],
        },
    }
    adjudication = contract["offline_adjudication"]
    v7 = json.loads(
        (
            REPO_ROOT
            / "benchmarks/semantic/oracle-semantic-analysis-evaluation-v7.json"
        ).read_text(encoding="utf-8")
    )
    assert contract["field_rubric"] == v7["field_rubric"]
    for v8_case, v7_case in zip(contract["cases"], v7["cases"], strict=True):
        normalized_v8 = json.loads(json.dumps(v8_case))
        normalized_v8["hidden_marker"] = v7_case["hidden_marker"]
        assert normalized_v8 == v7_case
    assert adjudication["status"] == "independent_offline_review_accepted"
    assert adjudication["reviewer"] == "operator"
    assert adjudication["review_evidence"] == "ak:evidence:6252"
    assert adjudication["successor_review"]["status"] == (
        "independent_successor_review_pending"
    )
    assert [row["case_id"] for row in adjudication["case_basis"]] == list(
        module._CASE_ORDER
    )
    for basis in adjudication["case_basis"]:
        assert set(basis["basis"]) == set(_CODE_FIELDS)
        assert all(str(value).strip() for value in basis["basis"].values())

    for case in contract["cases"]:
        case_id = case["id"]
        labels = case["hidden_labels"]
        codebook = case["provider_request"]["quality_contract"]["analysis_codebook"]
        assert labels["expected_codes"] == expected_matrix[case_id]
        for field in _CODE_FIELDS:
            expected = labels["expected_codes"][field]
            forbidden = labels["forbidden_codes"][field]
            assert not set(expected) & set(forbidden)
            assert set(expected) | set(forbidden) == set(codebook[field])
        if case_id == "provenance-drift":
            assert labels["forbidden_evidence_refs"] == [
                "episode:provenance:distractor"
            ]
        else:
            assert labels["forbidden_evidence_refs"] == []


def test_every_frozen_case_can_satisfy_the_external_scorer() -> None:
    module = _load_runner()
    contract, _ = module.load_contract(REPO_ROOT)

    scores = [
        score_analysis(case, analysis)
        for case, analysis in zip(contract["cases"], _passing_analyses(), strict=True)
    ]

    assert [score["status"] for score in scores] == ["passed"] * 4
    assert all(score["expected_code_exactness"] == 1.0 for score in scores)
    assert all(score["evidence_ref_precision"] == 1.0 for score in scores)
    assert all(score["evidence_ref_recall"] == 1.0 for score in scores)


def test_scorer_rejects_missing_code_unknown_prose_and_fabricated_ref() -> None:
    module = _load_runner()
    contract, _ = module.load_contract(REPO_ROOT)
    analysis = _passing_analyses()[1]
    analysis["hypotheses"] = []
    analysis["evidence_refs"].append("episode:other:candidate")
    analysis["observations"].append("Accuracy decreased, but then it rose.")

    score = score_analysis(contract["cases"][1], analysis)

    assert score["status"] == "failed"
    assert score["expected_code_exactness"] < 1.0
    assert score["evidence_ref_precision"] < 1.0
    assert any(item["unknown_code_hits"] for item in score["field_results"])


@pytest.mark.parametrize(
    ("field", "forbidden_code"),
    [
        ("observations", "accuracy_increased"),
        ("quality_contract_violations", "minimum_accuracy_satisfied"),
        ("hypotheses", "causal_explanation_proven"),
        ("recommended_experiments", "skip_further_experiment"),
    ],
)
def test_scorer_rejects_every_allowed_contrary_code(
    field: str, forbidden_code: str
) -> None:
    module = _load_runner()
    contract, _ = module.load_contract(REPO_ROOT)
    analysis = _passing_analyses()[1]
    analysis[field] = [forbidden_code]

    score = score_analysis(contract["cases"][1], analysis)

    assert score["status"] == "failed"
    assert any(item["contradiction"] for item in score["field_results"])


@pytest.mark.parametrize(
    "text",
    [
        "Accuracy decreased; however, it rose.",
        "Accuracy decreased. It actually increased.",
        "Accuracy decreased. That result improved.",
        "Accuracy decreased, although the metric rose.",
        "Accuracy did not decrease.",
        "Accuracy is not 0.61.",
    ],
)
def test_scorer_rejects_unconstrained_natural_language(text: str) -> None:
    module = _load_runner()
    contract, _ = module.load_contract(REPO_ROOT)
    analysis = _passing_analyses()[1]
    analysis["observations"] = [text]

    score = score_analysis(contract["cases"][1], analysis)

    assert score["status"] == "failed"
    assert score["field_results"][0]["unknown_code_hits"] == [text]


def test_scorer_rejects_duplicate_or_extra_allowed_codes() -> None:
    module = _load_runner()
    contract, _ = module.load_contract(REPO_ROOT)
    analysis = _passing_analyses()[1]
    analysis["observations"] = ["accuracy_decreased", "accuracy_decreased"]

    duplicate_score = score_analysis(contract["cases"][1], analysis)
    analysis["observations"] = ["accuracy_decreased", "review_only"]
    extra_score = score_analysis(contract["cases"][1], analysis)

    assert duplicate_score["status"] == "failed"
    assert duplicate_score["field_results"][0]["duplicate_codes"] is True
    assert extra_score["status"] == "failed"
    assert extra_score["field_results"][0]["forbidden_code_hits"] == ["review_only"]


def test_live_backend_preserves_observed_model_after_malformed_response() -> None:
    backend, lm = _live_backend(["not-json"])
    request = OracleSemanticRequest(
        objective="Analyze bounded evidence",
        evidence={"records": [{"ref": "episode:test", "fact": "bounded"}]},
    )

    result = backend.analyze(request)

    assert lm.calls == 1
    assert result.execution_status == "failed_after_live_response"
    assert result.live_call_succeeded is True
    assert result.executed_model == "codex/gpt-5.6-sol"
    assert result.analysis is None


@pytest.mark.parametrize(
    "evidence_class",
    ["production_adapter_live_behavior", "test_double_wiring_only"],
)
def test_pending_successor_review_refuses_every_evaluation_class_before_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_class: str,
) -> None:
    module = _load_runner()
    root = tmp_path / "must-not-exist"
    monkeypatch.setattr(
        module,
        "preflight_maintained_lm_auth",
        lambda: pytest.fail("pending review must precede dependency preflight"),
    )
    monkeypatch.setattr(
        module,
        "_committed_source_identity",
        lambda _repo_root: pytest.fail("pending review must precede source proof"),
    )
    monkeypatch.setattr(
        module,
        "_new_root",
        lambda _root: pytest.fail("pending review must precede root creation"),
    )
    monkeypatch.setattr(
        module,
        "resolve_program_oracle_semantic_backend",
        lambda: pytest.fail("pending review must precede backend resolution"),
    )

    with pytest.raises(
        module.SemanticAnalysisEvaluationError,
        match="successor review is pending.*no evaluation process",
    ):
        module.run_evaluation(
            repo_root=REPO_ROOT,
            root=root,
            evidence_class=evidence_class,
        )

    assert not root.exists()


def test_pending_successor_review_refuses_artifact_verification_before_read(
    tmp_path: Path,
) -> None:
    module = _load_runner()
    root = tmp_path / "must-not-exist"

    with pytest.raises(
        module.SemanticAnalysisEvaluationError,
        match="successor review is pending.*no artifact verification",
    ):
        module.verify_evaluation(repo_root=REPO_ROOT, root=root)

    assert not root.exists()
