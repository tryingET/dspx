# summary: "Tests the independently reviewed AK-4577 v8 live semantic contract membrane."

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
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
    EXPECTED_REVIEW_INVARIANT_SHA256,
    _CODE_FIELDS,
    SemanticAnalysisEvaluationError,
    _consume_attempt_ledger,
    _review_invariant_bytes,
    _request,
)
from dspx.services.program_oracle_semantic_scoring import score_analysis
from dspx.services.program_oracle_semantic_verification import (
    LIVE_EVIDENCE_CLASS,
    SOURCE_PATHS,
    _preserve_independent_verification,
    _validate_execution_provenance,
    historical_committed_source_identity,
)

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
        response_format = kwargs.get("response_format")
        assert isinstance(response_format, dict)
        assert response_format["name"] == "dspx_oracle_semantic_analysis"
        assert response_format["strict"] is True
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
    contract, observed_hash = module.load_contract(
        REPO_ROOT, require_current_sources=False
    )

    contract_path = (
        REPO_ROOT / "benchmarks/semantic/oracle-semantic-analysis-evaluation-v8.json"
    )
    assert observed_hash == hashlib.sha256(contract_path.read_bytes()).hexdigest()
    assert contract["attempt_policy"]["case_order"] == list(module._CASE_ORDER)
    assert contract["status"] in {
        "successor_offline_review_pending_live_authorized_not_run",
        "offline_adjudicated_live_authorized_not_run",
    }
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
    successor_review = contract["offline_adjudication"]["successor_review"]
    assert successor_review["review_question"] == (
        "Does v8 preserve v7 field_rubric, cases, hidden labels, and distractors "
        "while changing only successor identity and one-shot execution "
        "authorization?"
    )
    if contract["status"].startswith("successor_offline_review_pending"):
        assert successor_review["status"] == "independent_successor_review_pending"
        assert successor_review["reviewer"] is None
        assert successor_review["review_evidence"] is None
    else:
        assert successor_review["status"] == "independent_successor_review_accepted"
        assert str(successor_review["reviewer"]).strip()
        assert str(successor_review["review_evidence"]).startswith("ak:evidence:")
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
    assert EXPECTED_REVIEW_INVARIANT_SHA256 == (
        "fbcb2cbe6afe2c13c7574ed7debb53817263ea86d7ec18ace1412c767f1b8d90"
    )
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


def test_review_invariant_allows_only_activation_metadata_byte_changes() -> None:
    contract_path = (
        REPO_ROOT / "benchmarks/semantic/oracle-semantic-analysis-evaluation-v8.json"
    )
    pending_raw = contract_path.read_bytes()
    pending = json.loads(pending_raw)
    accepted = json.loads(pending_raw)
    accepted["status"] = "offline_adjudicated_live_authorized_not_run"
    successor_review = accepted["offline_adjudication"]["successor_review"]
    successor_review["status"] = "independent_successor_review_accepted"
    successor_review["reviewer"] = "independent-reviewer"
    successor_review["review_evidence"] = "ak:evidence:9999"
    accepted_raw = (json.dumps(accepted, indent=2) + "\n").encode("utf-8")

    assert _review_invariant_bytes(pending_raw, pending) == _review_invariant_bytes(
        accepted_raw, accepted
    )
    reformatted = pending_raw.replace(b'"purpose":', b'"purpose" :', 1)
    assert _review_invariant_bytes(reformatted, json.loads(reformatted)) != (
        _review_invariant_bytes(pending_raw, pending)
    )


def test_v8_matrix_matches_reviewed_v7_semantics_and_evidence_rubric() -> None:
    module = _load_runner()
    contract, _ = module.load_contract(REPO_ROOT, require_current_sources=False)
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
    assert adjudication["successor_review"]["status"] in {
        "independent_successor_review_pending",
        "independent_successor_review_accepted",
    }
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
    contract, _ = module.load_contract(REPO_ROOT, require_current_sources=False)

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
    contract, _ = module.load_contract(REPO_ROOT, require_current_sources=False)
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
    contract, _ = module.load_contract(REPO_ROOT, require_current_sources=False)
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
    contract, _ = module.load_contract(REPO_ROOT, require_current_sources=False)
    analysis = _passing_analyses()[1]
    analysis["observations"] = [text]

    score = score_analysis(contract["cases"][1], analysis)

    assert score["status"] == "failed"
    assert score["field_results"][0]["unknown_code_hits"] == [text]


def test_scorer_rejects_duplicate_or_extra_allowed_codes() -> None:
    module = _load_runner()
    contract, _ = module.load_contract(REPO_ROOT, require_current_sources=False)
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


def test_failed_after_response_provenance_is_fully_correlated() -> None:
    semantic = {
        "execution_status": "failed_after_live_response",
        "live_call_succeeded": True,
        "executed_model": "codex/gpt-5.6-sol",
        "error": "structured response parse failed",
    }
    rows = [{"semantic_result": semantic}]
    provenance = {
        "evidence_class": LIVE_EVIDENCE_CLASS,
        "trusted_for_live_behavior": True,
        "adapter_type": "dspx.dspy_lm_auth_lm.DspyLMAuthLM",
        "requested_model": "codex/gpt-5.6-sol",
        "auth_provider": "codex",
        "reasoning_effort": "max",
        "strict": True,
        "history_count_before": 0,
        "status": "failed_or_indeterminate",
        "calls": [
            {
                "history_index": 0,
                "history_delta": 1,
                "generate_invocation_delta": 1,
                "requested_model": "codex/gpt-5.6-sol",
                "auth_provider": "codex",
                "call_error": None,
                "resolved_model": "codex/gpt-5.6-sol",
                "uses_codex_route": True,
                "observed_response_model": "codex/gpt-5.6-sol",
            }
        ],
        "history_count_after": 1,
    }

    assert (
        _validate_execution_provenance(
            provenance,
            evidence_class=LIVE_EVIDENCE_CLASS,
            executed_models=[],
            case_rows=rows,
            attempted_count=1,
            generate_call_count=1,
            mechanics_passed=False,
        )
        is True
    )

    tampered_rows = json.loads(json.dumps(rows))
    tampered_rows[0]["semantic_result"]["live_call_succeeded"] = False
    with pytest.raises(ValueError, match="failed-after-response provenance drift"):
        _validate_execution_provenance(
            provenance,
            evidence_class=LIVE_EVIDENCE_CLASS,
            executed_models=[],
            case_rows=tampered_rows,
            attempted_count=1,
            generate_call_count=1,
            mechanics_passed=False,
        )


def test_consumed_v8_execution_refuses_current_source_drift_before_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_runner()
    root = tmp_path / "must-not-exist"
    contract, _ = module.load_contract(REPO_ROOT, require_current_sources=False)
    assert contract["ak_task_id"] == 4577
    with pytest.raises(
        module.SemanticAnalysisEvaluationError,
        match="semantic_backend source hash drift",
    ):
        module.load_contract(REPO_ROOT)
    monkeypatch.setattr(
        module,
        "preflight_maintained_lm_auth",
        lambda: pytest.fail("source drift must precede dependency preflight"),
    )
    monkeypatch.setattr(
        module,
        "_new_root",
        lambda _root: pytest.fail("source drift must precede artifact root creation"),
    )

    with pytest.raises(
        module.SemanticAnalysisEvaluationError,
        match="semantic_backend source hash drift",
    ):
        module.run_evaluation(
            repo_root=REPO_ROOT,
            root=root,
            evidence_class="production_adapter_live_behavior",
        )

    assert not root.exists()


def test_historical_source_identity_hashes_git_objects_without_importing_old_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dspx.services.program_oracle_semantic_verification as verification

    repo = tmp_path / "history-repo"
    repo.mkdir()

    def git(*args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    git("init", "-q")
    git("config", "user.email", "history@example.invalid")
    git("config", "user.name", "History Test")
    (repo / "source.py").write_text("value = 'original'\n", encoding="utf-8")
    (repo / "runner.py").write_text("print('original')\n", encoding="utf-8")
    git("add", "source.py", "runner.py")
    git("commit", "-q", "-m", "original")
    commit = git("rev-parse", "HEAD")
    expected_source_hash = hashlib.sha256(b"value = 'original'\n").hexdigest()
    (repo / "source.py").write_text("value = 'current'\n", encoding="utf-8")

    monkeypatch.setattr(verification, "SOURCE_PATHS", ("source.py", "runner.py"))
    monkeypatch.setattr(
        verification,
        "_LOADED_SOURCE_MODULES",
        {"historical.module": "source.py"},
    )
    monkeypatch.setattr(
        verification.importlib,
        "import_module",
        lambda _name: pytest.fail("historical verification must not import old code"),
    )

    identity = historical_committed_source_identity(repo, expected_commit=commit)

    assert identity["git_commit"] == commit
    assert identity["path_sha256"]["source.py"] == expected_source_hash
    assert identity["loaded_module_paths"] == {"historical.module": "source.py"}
    assert hashlib.sha256((repo / "source.py").read_bytes()).hexdigest() != (
        expected_source_hash
    )
    with pytest.raises(
        SemanticAnalysisEvaluationError,
        match="recorded source commit must be a full lowercase Git SHA",
    ):
        historical_committed_source_identity(repo, expected_commit="invalid")
    with pytest.raises(
        SemanticAnalysisEvaluationError,
        match="source commit preflight failed",
    ):
        historical_committed_source_identity(repo, expected_commit="0" * 40)


def test_retained_verification_is_idempotent_and_never_overwritten(
    tmp_path: Path,
) -> None:
    path = tmp_path / "independent-verification.json"
    verification = {"schema_version": "test", "status": "rejected"}

    first = _preserve_independent_verification(path, verification)
    original_bytes = path.read_bytes()
    original_stat = path.stat()
    second = _preserve_independent_verification(path, verification)

    assert first == second == verification
    assert path.read_bytes() == original_bytes
    assert path.stat().st_ino == original_stat.st_ino
    assert path.stat().st_mtime_ns == original_stat.st_mtime_ns
    with pytest.raises(
        SemanticAnalysisEvaluationError,
        match="retained independent verification drift",
    ):
        _preserve_independent_verification(
            path, {"schema_version": "test", "status": "accepted"}
        )
    assert path.read_bytes() == original_bytes


def test_second_ledger_consumption_fails_without_changing_original(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "ledger" / "AK-4577.json"
    first_root = tmp_path / "first-root"
    second_root = tmp_path / "second-root"

    _consume_attempt_ledger(
        root=first_root,
        contract_sha256="a" * 64,
        ledger_path=ledger,
    )
    original_bytes = ledger.read_bytes()
    original_stat = ledger.stat()

    with pytest.raises(
        SemanticAnalysisEvaluationError,
        match="ledger is already consumed",
    ):
        _consume_attempt_ledger(
            root=second_root,
            contract_sha256="a" * 64,
            ledger_path=ledger,
        )

    assert ledger.read_bytes() == original_bytes
    assert ledger.stat().st_ino == original_stat.st_ino
    assert ledger.stat().st_mtime_ns == original_stat.st_mtime_ns


def test_pending_review_refuses_artifact_verification_without_effects(
    tmp_path: Path,
) -> None:
    module = _load_runner()
    root = tmp_path / "must-not-exist"
    contract, _ = module.load_contract(REPO_ROOT, require_current_sources=False)

    if contract["status"].startswith("successor_offline_review_pending"):
        with pytest.raises(
            module.SemanticAnalysisEvaluationError,
            match="successor review is pending.*no artifact verification",
        ):
            module.verify_evaluation(repo_root=REPO_ROOT, root=root)

    assert not root.exists()


def _v9_contract() -> dict[str, Any]:
    return json.loads(
        (
            REPO_ROOT
            / "benchmarks/semantic/oracle-semantic-analysis-evaluation-v9.json"
        ).read_text(encoding="utf-8")
    )


def _v9_code_semantics() -> dict[str, Any]:
    contract = _v9_contract()
    binding = contract["code_semantics_binding"]
    path = REPO_ROOT / binding["path"]
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding["sha256"]
    return json.loads(raw)


def _provider_request(case: dict[str, Any]) -> OracleSemanticRequest:
    payload = case["provider_request"]
    quality_contract = json.loads(json.dumps(payload["quality_contract"]))
    semantics_ref = quality_contract.pop("analysis_code_semantics_ref")
    binding = _v9_contract()["code_semantics_binding"]
    assert semantics_ref == {
        "path": binding["path"],
        "sha256": binding["sha256"],
    }
    quality_contract["analysis_code_semantics"] = _v9_code_semantics()
    return OracleSemanticRequest(
        objective=payload["objective"],
        evidence=payload["evidence"],
        quality_contract=quality_contract,
    )


def test_v9_is_zero_process_and_preserves_v8_hidden_adjudication() -> None:
    v8 = json.loads(
        (
            REPO_ROOT
            / "benchmarks/semantic/oracle-semantic-analysis-evaluation-v8.json"
        ).read_text(encoding="utf-8")
    )
    v9 = _v9_contract()

    assert v9["schema_version"] == ("dspx-oracle-semantic-analysis-evaluation-v9")
    assert v9["status"] == "offline_disambiguation_review_pending_zero_process"
    assert v9["ak_task_id"] == 4591
    assert v9["route"]["live_authorized"] is False
    assert v9["attempt_policy"]["maximum_evaluation_processes"] == 0
    assert v9["attempt_policy"]["maximum_generate_calls_per_case"] == 0
    assert v9["attempt_policy"]["dspx_generate_invocation_count"] == 0
    assert v9["attempt_policy"]["ledger"]["kind"] == "none_zero_process"
    assert v9["offline_adjudication"]["successor_review"]["status"] == (
        "independent_successor_review_pending"
    )
    assert v9["remediation"]["terminal_result_sha256"] == (
        "9428cab41a13d550b3c8ef497e1d0f7b5b8a25743f398da81910a7e4dcc6bf09"
    )

    for v9_case, v8_case in zip(v9["cases"], v8["cases"], strict=True):
        assert v9_case["id"] == v8_case["id"]
        assert v9_case["hidden_labels"] == v8_case["hidden_labels"]
        assert (
            v9_case["provider_request"]["objective"]
            == (v8_case["provider_request"]["objective"])
        )
        assert (
            v9_case["provider_request"]["evidence"]
            == (v8_case["provider_request"]["evidence"])
        )
        assert (
            v9_case["provider_request"]["quality_contract"]["analysis_codebook"]
            == v8_case["provider_request"]["quality_contract"]["analysis_codebook"]
        )


def test_v9_code_semantics_are_complete_uniform_and_case_independent() -> None:
    contract = _v9_contract()
    semantics = _v9_code_semantics()
    binding = contract["code_semantics_binding"]
    serialized = json.dumps(semantics, sort_keys=True, separators=(",", ":"))
    expected_fields = {
        "observations",
        "failure_attractors",
        "quality_contract_violations",
        "hypotheses",
        "recommended_experiments",
    }

    assert semantics["schema_version"] == ("dspx-oracle-semantic-code-semantics-v1")
    assert binding["schema_version"] == semantics["schema_version"]
    assert contract["semantic_materialization"]["source"] == binding["path"]
    assert contract["semantic_materialization"]["canonical_sha256"] == binding["sha256"]
    assert set(semantics["fields"]) == expected_fields
    assert sum(len(codes) for codes in semantics["fields"].values()) == 26
    for forbidden_text in (
        "HIDDEN-",
        "hidden_labels",
        "expected_codes",
        "forbidden_codes",
        "episode:authority:",
        "episode:causal:",
        "episode:review:",
        "episode:provenance:",
        "authority-boundary",
        "causal-calibration",
        "review-only-transition",
        "provenance-drift",
    ):
        assert forbidden_text not in serialized

    for case in contract["cases"]:
        quality = case["provider_request"]["quality_contract"]
        assert quality["analysis_code_semantics_ref"] == {
            "path": binding["path"],
            "sha256": binding["sha256"],
        }
        assert "analysis_code_semantics" not in quality
        assert (
            quality["analysis_evidence_ref_rubric"] == contract["evidence_ref_rubric"]
        )
        assert quality["analysis_confidence_rubric"] == contract["confidence_rubric"]
        for field in expected_fields:
            assert (
                list(semantics["fields"][field]) == quality["analysis_codebook"][field]
            )
            for definition in semantics["fields"][field].values():
                assert set(definition) == {"meaning", "select_when", "exclude_when"}
                assert str(definition["meaning"]).strip()
                assert definition["select_when"]
                assert definition["exclude_when"]


def test_v9_hidden_label_mutation_cannot_change_provider_prompt() -> None:
    contract = _v9_contract()
    for case in contract["cases"]:
        original_prompt = _analysis_prompt(_provider_request(case))
        mutated = json.loads(json.dumps(case))
        mutated["hidden_marker"] = "HIDDEN-MUTATION-CANARY"
        mutated["hidden_labels"]["expected_codes"] = {
            field: ["hidden-answer-canary"]
            for field in mutated["hidden_labels"]["expected_codes"]
        }
        mutated_prompt = _analysis_prompt(_provider_request(mutated))

        assert mutated_prompt == original_prompt
        assert case["hidden_marker"] not in original_prompt
        assert "HIDDEN-AK4591" not in original_prompt
        assert "hidden-answer-canary" not in mutated_prompt
        assert json.dumps(case["hidden_labels"], sort_keys=True) not in original_prompt


def test_v9_response_schema_uses_visible_code_and_evidence_ref_enums() -> None:
    contract = _v9_contract()
    authority = next(
        case for case in contract["cases"] if case["id"] == "authority-boundary"
    )
    request = _provider_request(authority)
    response_format = _analysis_response_format(request)
    properties = response_format["schema"]["properties"]
    quality_contract = request.quality_contract
    assert quality_contract is not None

    for field, codes in quality_contract["analysis_codebook"].items():
        assert properties[field]["items"]["enum"] == codes
        assert properties[field]["uniqueItems"] is True
    assert properties["evidence_refs"]["items"]["enum"] == [
        "episode:authority:quality",
        "episode:authority:effects",
    ]
    assert properties["evidence_refs"]["uniqueItems"] is True
