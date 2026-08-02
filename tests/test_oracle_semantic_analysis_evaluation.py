# summary: "Tests the independent-label AK-4568 successor Oracle semantic-analysis LM evaluation membrane."

from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from dspx.dspy_lm_auth_lm import DspyLMAuthLM
from dspx.dtos import LMResponse
from dspx.services.program_oracle_semantic_backend import (
    LiveLMOracleSemanticBackend,
    _analysis_response_format,
    _analysis_prompt,
)
from dspx.services.program_oracle_semantic_contract import OracleSemanticRequest
from dspx.services.program_oracle_semantic_evaluation import FROZEN_SOURCE_COMMIT
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


def _route_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_ORACLE_SEMANTIC_BACKEND", "live")
    monkeypatch.setenv("DSPX_ORACLE_SEMANTIC_PROVIDER", "dspy-lm-auth")
    monkeypatch.setenv("DSPX_ORACLE_SEMANTIC_MODEL", "codex/gpt-5.6-sol")
    monkeypatch.setenv("DSPX_ORACLE_SEMANTIC_REASONING_EFFORT", "max")


def test_checked_in_contract_is_exact_and_labels_do_not_enter_prompts() -> None:
    module = _load_runner()
    contract, observed_hash = module.load_contract(REPO_ROOT)

    assert observed_hash == (
        "27eeb61640c3270d2acc52d4b9b2072815eb036877975f29ae2954989fce8435"
    )
    assert contract["attempt_policy"]["case_order"] == list(module._CASE_ORDER)
    assert FROZEN_SOURCE_COMMIT == "a67e87168efea9a4ff303acd2575dc327438077a"
    for case in contract["cases"]:
        request = module._request(case)
        prompt = _analysis_prompt(request)
        assert case["hidden_marker"] not in prompt
        assert json.dumps(case["hidden_labels"], sort_keys=True) not in prompt
        assert "HIDDEN-AK4568" not in prompt
    assert (
        "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract.py"
        in SOURCE_PATHS
    )


def test_every_frozen_case_can_satisfy_the_external_scorer() -> None:
    module = _load_runner()
    contract, _ = module.load_contract(REPO_ROOT)

    scores = [
        module.score_analysis(case, analysis)
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

    score = module.score_analysis(contract["cases"][1], analysis)

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

    score = module.score_analysis(contract["cases"][1], analysis)

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

    score = module.score_analysis(contract["cases"][1], analysis)

    assert score["status"] == "failed"
    assert score["field_results"][0]["unknown_code_hits"] == [text]


def test_scorer_rejects_duplicate_or_extra_allowed_codes() -> None:
    module = _load_runner()
    contract, _ = module.load_contract(REPO_ROOT)
    analysis = _passing_analyses()[1]
    analysis["observations"] = ["accuracy_decreased", "accuracy_decreased"]

    duplicate_score = module.score_analysis(contract["cases"][1], analysis)
    analysis["observations"] = ["accuracy_decreased", "review_only"]
    extra_score = module.score_analysis(contract["cases"][1], analysis)

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


def test_double_run_is_explicitly_wiring_only_and_live_verifier_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    _route_env(monkeypatch)
    backend, lm = _live_backend(_passing_analyses())
    monkeypatch.setattr(
        module, "resolve_program_oracle_semantic_backend", lambda: backend
    )
    monkeypatch.setattr(
        module, "_attempt_ledger_path", lambda: tmp_path / "ledger.json"
    )
    root = tmp_path / "evaluation"

    result = module.run_evaluation(
        repo_root=REPO_ROOT,
        root=root,
        evidence_class=module._WIRING_EVIDENCE_CLASS,
    )
    verification = module.verify_evaluation(repo_root=REPO_ROOT, root=root)

    assert result["status"] == "wiring_only_passed"
    assert result["evidence_class"] == module._WIRING_EVIDENCE_CLASS
    assert result["execution_provenance"]["trusted_for_live_behavior"] is False
    assert result["claims"]["four_case_semantic_analysis_gate_passed"] is False
    assert result["attempt"] == {
        "evaluation_processes": 1,
        "separate_health_probes": 0,
        "dspx_managed_retries": 0,
        "selective_case_rerun": False,
        "dspx_analyze_invocations": 4,
        "generate_call_count": "not_directly_observed",
    }
    assert lm.calls == 4
    assert len(lm.prompts) == 4
    assert all("HIDDEN-AK4568" not in prompt for prompt in lm.prompts)
    assert verification["status"] == "rejected"
    assert verification["labels_freshly_deterministically_rescored"] is True
    assert verification["implementation_independence_claimed"] is False
    assert verification["production_adapter_provenance_checked"] is False
    assert verification["source_commit_independently_checked"] is False
    assert verification["failed_history_preserved"] is False
    assert verification["terminal_history_disposition"] == (
        "wiring_only_not_live_history"
    )
    assert verification["shared_store_or_embedding_evidence_used"] is False
    assert stat_mode(root / module.RESULT_NAME) == 0o600
    assert verification["attempt_policy_independently_checked"] is True


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_live_evidence_rejects_test_double_before_generate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    _route_env(monkeypatch)
    backend, lm = _live_backend(_passing_analyses())
    monkeypatch.setattr(
        module, "resolve_program_oracle_semantic_backend", lambda: backend
    )
    monkeypatch.setattr(
        module,
        "_committed_source_identity",
        lambda _repo_root: {"git_commit": "test-only-committed-source"},
    )
    monkeypatch.setattr(
        module, "_attempt_ledger_path", lambda: tmp_path / "ledger.json"
    )

    result = module.run_evaluation(
        repo_root=REPO_ROOT,
        root=tmp_path / "live-rejects-double",
    )

    assert result["status"] == "failed"
    assert result["claims"]["four_case_semantic_analysis_gate_passed"] is False
    assert "exact production DspyLMAuthLM adapter" in result["terminal_error"]
    assert lm.calls == 0


def test_live_evidence_rejects_rebound_exact_adapter_methods() -> None:
    module = _load_runner()
    lm = DspyLMAuthLM(
        model="codex/gpt-5.6-sol",
        auth_provider="codex",
        strict=True,
        kwargs={"reasoning_effort": "max"},
    )
    lm.__dict__["generate"] = lambda *_args, **_kwargs: None
    lm.__dict__["runtime_metadata"] = lambda: {
        "provider_family": "dspy-lm-auth",
        "requested_model": "codex/gpt-5.6-sol",
        "uses_codex_route": True,
        "resolved_model": "codex/gpt-5.6-sol",
    }
    backend = LiveLMOracleSemanticBackend(
        provider_name="dspy-lm-auth",
        preferred_model="codex/gpt-5.6-sol",
        lm=lm,
    )

    with pytest.raises(
        module.SemanticAnalysisEvaluationError, match="methods were rebound"
    ):
        module._adapter_preflight(backend, evidence_class=module._LIVE_EVIDENCE_CLASS)


def test_live_evidence_rejects_swapped_production_class_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_runner()
    lm = DspyLMAuthLM(
        model="codex/gpt-5.6-sol",
        auth_provider="codex",
        strict=True,
        kwargs={"reasoning_effort": "max"},
    )
    backend = LiveLMOracleSemanticBackend(
        provider_name="dspy-lm-auth",
        preferred_model="codex/gpt-5.6-sol",
        lm=lm,
    )
    monkeypatch.setattr(DspyLMAuthLM, "generate", DspyLMAuthLM.forward)

    with pytest.raises(
        module.SemanticAnalysisEvaluationError, match="methods were rebound"
    ):
        module._adapter_preflight(backend, evidence_class=module._LIVE_EVIDENCE_CLASS)


def test_failure_stops_remaining_cases_and_consumes_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    _route_env(monkeypatch)
    backend, lm = _live_backend([_passing_analyses()[0], "not-json"])
    ledger = tmp_path / "ledger.json"
    monkeypatch.setattr(
        module, "resolve_program_oracle_semantic_backend", lambda: backend
    )
    monkeypatch.setattr(module, "_attempt_ledger_path", lambda: ledger)
    root = tmp_path / "failed"

    result = module.run_evaluation(
        repo_root=REPO_ROOT,
        root=root,
        evidence_class=module._WIRING_EVIDENCE_CLASS,
    )

    assert result["status"] == "failed"
    assert len(result["cases"]) == 2
    assert lm.calls == 2
    assert result["cases"][1]["semantic_result"]["executed_model"] == (
        "codex/gpt-5.6-sol"
    )
    assert result["cases"][1]["semantic_result"]["execution_status"] == (
        "failed_after_live_response"
    )
    with pytest.raises(
        module.SemanticAnalysisEvaluationError, match="already consumed"
    ):
        module.run_evaluation(
            repo_root=REPO_ROOT,
            root=tmp_path / "selective-retry",
            evidence_class=module._WIRING_EVIDENCE_CLASS,
        )


def test_route_drift_fails_before_provider_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    _route_env(monkeypatch)
    monkeypatch.setenv("DSPX_ORACLE_SEMANTIC_MODEL", "codex/other")
    monkeypatch.setattr(
        module, "_attempt_ledger_path", lambda: tmp_path / "ledger.json"
    )
    monkeypatch.setattr(
        module,
        "resolve_program_oracle_semantic_backend",
        lambda: pytest.fail("route drift must fail before backend resolution"),
    )

    result = module.run_evaluation(
        repo_root=REPO_ROOT,
        root=tmp_path / "route-drift",
        evidence_class=module._WIRING_EVIDENCE_CLASS,
    )

    assert result["status"] == "failed"
    assert result["cases"] == []
    assert result["attempt"]["dspx_analyze_invocations"] == 0
    assert result["attempt"]["generate_call_count"] == "not_directly_observed"


def test_existing_root_is_rejected_before_attempt_ledger_consumption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    existing_root = tmp_path / "existing"
    existing_root.mkdir()
    ledger = tmp_path / "ledger.json"
    monkeypatch.setattr(module, "_attempt_ledger_path", lambda: ledger)

    with pytest.raises(
        module.SemanticAnalysisEvaluationError, match="must not already"
    ):
        module.run_evaluation(
            repo_root=REPO_ROOT,
            root=existing_root,
            evidence_class=module._WIRING_EVIDENCE_CLASS,
        )

    assert not ledger.exists()


def test_verifier_rejects_tampered_score_without_overwriting_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    _route_env(monkeypatch)
    backend, _ = _live_backend(_passing_analyses())
    monkeypatch.setattr(
        module, "resolve_program_oracle_semantic_backend", lambda: backend
    )
    monkeypatch.setattr(
        module, "_attempt_ledger_path", lambda: tmp_path / "ledger.json"
    )
    root = tmp_path / "tampered"
    module.run_evaluation(
        repo_root=REPO_ROOT,
        root=root,
        evidence_class=module._WIRING_EVIDENCE_CLASS,
    )
    result_path = root / module.RESULT_NAME
    payload = json.loads(result_path.read_text())
    payload["cases"][0]["score"]["required_group_recall"] = 0.0
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        module.SemanticAnalysisEvaluationError, match="attempt policy evidence drift"
    ):
        module.verify_evaluation(repo_root=REPO_ROOT, root=root)

    assert not (root / module.VERIFICATION_NAME).exists()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _rebind_tampered_packet(module: ModuleType, root: Path, ledger: Path) -> None:
    result_path = root / module.RESULT_NAME
    attempt_path = root / module.ATTEMPT_NAME
    result_sha256 = hashlib.sha256(result_path.read_bytes()).hexdigest()
    attempt = json.loads(attempt_path.read_text())
    attempt["result_sha256"] = result_sha256
    _write_json(attempt_path, attempt)
    ledger_payload = json.loads(ledger.read_text())
    ledger_payload["result_sha256"] = result_sha256
    ledger_payload["attempt_sha256"] = hashlib.sha256(
        attempt_path.read_bytes()
    ).hexdigest()
    _write_json(ledger, ledger_payload)


@pytest.mark.parametrize(
    ("tamper", "expected_error"),
    [
        ("route", "stored semantic score drift"),
        ("authority", "stored semantic score drift"),
        ("inner-request", "semantic result request hash drift"),
        ("summary", "result summary drift"),
        ("attempt", "attempt policy evidence drift"),
    ],
)
def test_verifier_rejects_rebound_route_attempt_and_summary_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
    expected_error: str,
) -> None:
    module = _load_runner()
    _route_env(monkeypatch)
    backend, _ = _live_backend(_passing_analyses())
    ledger = tmp_path / f"{tamper}-ledger.json"
    root = tmp_path / f"{tamper}-root"
    monkeypatch.setattr(
        module, "resolve_program_oracle_semantic_backend", lambda: backend
    )
    monkeypatch.setattr(module, "_attempt_ledger_path", lambda: ledger)
    module.run_evaluation(
        repo_root=REPO_ROOT,
        root=root,
        evidence_class=module._WIRING_EVIDENCE_CLASS,
    )
    result_path = root / module.RESULT_NAME
    result = json.loads(result_path.read_text())
    attempt_path = root / module.ATTEMPT_NAME
    if tamper == "route":
        result["cases"][0]["semantic_result"]["configured_model"] = "codex/other"
        _write_json(result_path, result)
    elif tamper == "authority":
        result["cases"][0]["semantic_result"]["authority"] = (
            "production_activation_authority"
        )
        _write_json(result_path, result)
    elif tamper == "inner-request":
        result["cases"][0]["semantic_result"]["request_sha256"] = "0" * 64
        _write_json(result_path, result)
    elif tamper == "summary":
        result["summary"]["passed_case_count"] = 99
        _write_json(result_path, result)
    else:
        attempt = json.loads(attempt_path.read_text())
        attempt["dspx_analyze_invocations"] = 99
        _write_json(attempt_path, attempt)
    _rebind_tampered_packet(module, root, ledger)

    with pytest.raises(module.SemanticAnalysisEvaluationError, match=expected_error):
        module.verify_evaluation(repo_root=REPO_ROOT, root=root)


def test_verifier_rejects_world_readable_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_runner()
    _route_env(monkeypatch)
    backend, _ = _live_backend(_passing_analyses())
    ledger = tmp_path / "mode-ledger.json"
    root = tmp_path / "mode-root"
    monkeypatch.setattr(
        module, "resolve_program_oracle_semantic_backend", lambda: backend
    )
    monkeypatch.setattr(module, "_attempt_ledger_path", lambda: ledger)
    module.run_evaluation(
        repo_root=REPO_ROOT,
        root=root,
        evidence_class=module._WIRING_EVIDENCE_CLASS,
    )
    (root / module.RESULT_NAME).chmod(0o644)

    with pytest.raises(module.SemanticAnalysisEvaluationError, match="mode drift"):
        module.verify_evaluation(repo_root=REPO_ROOT, root=root)


def test_canonical_ledger_ignores_home_and_xdg_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_runner()
    before = module._attempt_ledger_path()
    monkeypatch.setenv("HOME", str(tmp_path / "other-home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "other-state"))

    assert module._attempt_ledger_path() == before
