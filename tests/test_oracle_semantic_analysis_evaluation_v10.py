# summary: "Offline tests for the task-local hardened AK-4643 v10 evaluator."
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from dspx.services.program_oracle_semantic_artifacts_v10 import (
    GATE_SCHEMA,
    LEDGER_SCHEMA,
    REVIEW_SCHEMA,
    append_event,
    derive_disposition,
    load_events,
)
from dspx.services.program_oracle_semantic_artifacts_v10 import (
    has_open_effect as _has_open_effect,
)
from dspx.services.program_oracle_semantic_backend import (
    _analysis_prompt,
    _analysis_response_format,
)
from dspx.services.program_oracle_semantic_contract import (
    OracleSemanticAnalysis,
    OracleSemanticResult,
)
from dspx.services.program_oracle_semantic_contract_v10 import (
    ATTEMPT_DIR,
    CANDIDATE_RECEIPT,
    CASE_ORDER,
    CONTRACT_PATH,
    EVENT_DIR,
    EXPECTED_SOURCE_PATHS,
    LEDGER_NAME,
    LIVE_GATE_RECEIPT,
    RESULT_NAME,
    SEMANTICS_PATH,
    SEMANTICS_SHA256,
    TASK_ID,
    V9_PATH,
    V9_SHA256,
    SemanticV10Error,
    load_candidate,
    materialized_request,
    read_json,
    request_hashes,
    score_v10,
    sha256,
    write_exclusive,
)
from dspx.services.program_oracle_semantic_evaluation_v10 import (
    CONTRACT_SNAPSHOT,
    GATE_SNAPSHOT,
    REVIEW_SNAPSHOT,
    _case_rows,
    _disposition,
    _terminal_result,
)
from dspx.services.program_oracle_semantic_identity_v10 import (
    ROUTE,
    create_live_gate,
    validate_receipts,
)
from dspx.services.program_oracle_semantic_verification_v10 import verify_evaluation

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts/ci/run_oracle_semantic_analysis_evaluation_v10.py"


def _runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("semantic_v10_runner_test", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _passing() -> list[dict[str, Any]]:
    return [
        {
            "observations": ["local_quality_checks_passed"],
            "failure_attractors": ["authority_overreach_risk"],
            "quality_contract_violations": [],
            "hypotheses": [],
            "recommended_experiments": ["governing_owner_review"],
            "evidence_refs": ["episode:authority:quality", "episode:authority:effects"],
            "confidence": 0.8,
        },
        {
            "observations": ["accuracy_decreased"],
            "failure_attractors": [],
            "quality_contract_violations": ["minimum_accuracy_violated"],
            "hypotheses": ["causal_explanation_unproven"],
            "recommended_experiments": ["controlled_prompt_ablation"],
            "evidence_refs": ["episode:causal:metric", "episode:causal:diagnostic"],
            "confidence": 0.7,
        },
        {
            "observations": ["review_only", "proposal_not_applied"],
            "failure_attractors": ["proposal_decision_conflation_risk"],
            "quality_contract_violations": [],
            "hypotheses": [],
            "recommended_experiments": ["approval_preflight"],
            "evidence_refs": ["episode:review:status", "episode:review:effects"],
            "confidence": 0.8,
        },
        {
            "observations": [
                "receipt_manifest_hash_mismatch",
                "quality_not_evaluated_after_mismatch",
            ],
            "failure_attractors": [],
            "quality_contract_violations": ["evidence_identity_violated"],
            "hypotheses": [],
            "recommended_experiments": ["rebind_and_verified_replay"],
            "evidence_refs": [
                "episode:provenance:mismatch",
                "episode:provenance:quality",
            ],
            "confidence": 0.7,
        },
    ]


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _attempt(state: Path) -> Path:
    attempt = _private_dir(state / ATTEMPT_DIR)
    _private_dir(attempt / EVENT_DIR)
    write_exclusive(
        attempt / LEDGER_NAME,
        {
            "schema_version": LEDGER_SCHEMA,
            "ak_task_id": TASK_ID,
            "status": "consumed",
            "maximum_evaluation_processes": 1,
            "retry_allowed": False,
            "root": str(attempt),
        },
    )
    append_event(
        attempt, "attempt_consumed", evaluation_processes=1, retry_allowed=False
    )
    return attempt


def _receipt_state(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    state = _private_dir(tmp_path / "AK-4643")
    contract, semantics, contract_hash = load_candidate(REPO)
    requests = request_hashes(contract, semantics)
    dependency = {
        "distribution": "tryinget-dspy-lm-auth",
        "version": "0.1.5",
        "module_origin": "/test/dspy_lm_auth/__init__.py",
        "module_sha256": "1" * 64,
        "module_tree_sha256": "2" * 64,
        "distribution_payload_count": 3,
        "distribution_payload_sha256": "3" * 64,
        "direct_url_sha256": "4" * 64,
        "record_sha256": "5" * 64,
        "editable": True,
    }
    identity = {
        "candidate_commit": "a" * 40,
        "candidate_tree": "b" * 40,
        "source_hashes": contract["source_bindings"],
    }
    review = {
        "schema_version": REVIEW_SCHEMA,
        "ak_task_id": TASK_ID,
        "decision": "ACCEPT_CANDIDATE_FOR_TASK_GATE",
        "reviewer": "offline-reviewer",
        "review_ref": "temp:test-review",
        "contract_sha256": contract_hash,
        "source_hashes": contract["source_bindings"],
        "request_hashes": requests,
        "dependency_identity": dependency,
        "candidate_commit": identity["candidate_commit"],
        "candidate_tree": identity["candidate_tree"],
    }
    write_exclusive(state / CANDIDATE_RECEIPT, review)
    _, review_raw = read_json(state / CANDIDATE_RECEIPT, "review")
    gate = {
        "schema_version": GATE_SCHEMA,
        "ak_task_id": TASK_ID,
        "decision": "AUTHORIZE_EXACTLY_ONE_CORPUS_PROCESS",
        "gate_ref": "temp:test-gate",
        "candidate_review_sha256": sha256(review_raw),
        "contract_sha256": contract_hash,
        "source_hashes": contract["source_bindings"],
        "request_hashes": requests,
        "candidate_commit": identity["candidate_commit"],
        "candidate_tree": identity["candidate_tree"],
        "route": ROUTE,
        "dependency_identity": dependency,
        "maximum_corpus_processes": 1,
        "fallback_allowed": False,
        "retry_allowed": False,
    }
    write_exclusive(state / LIVE_GATE_RECEIPT, gate)
    _, gate_raw = read_json(state / LIVE_GATE_RECEIPT, "gate")
    return state, {
        "contract": contract,
        "semantics": semantics,
        "contract_sha256": contract_hash,
        "request_hashes": requests,
        "review": review,
        "review_sha256": sha256(review_raw),
        "gate": gate,
        "gate_sha256": sha256(gate_raw),
        "source_identity": identity,
    }


def _copy_candidate(tmp_path: Path) -> Path:
    for relative in (
        CONTRACT_PATH,
        V9_PATH,
        SEMANTICS_PATH,
        *map(Path, EXPECTED_SOURCE_PATHS),
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    return tmp_path


class _LM:
    generate_invocation_count = 0

    def __init__(self) -> None:
        self.history: list[object] = []


class _Backend:
    def __init__(
        self,
        lm: _LM,
        analyses: list[dict[str, Any]],
        *,
        error_at: int | None = None,
        models: list[str] | None = None,
    ) -> None:
        self.lm, self.analyses, self.error_at, self.calls = lm, analyses, error_at, 0
        self.models = models or [ROUTE["model"]] * len(analyses)

    def analyze(self, request) -> OracleSemanticResult:
        self.lm.generate_invocation_count += 1
        self.lm.history.append(object())
        index = self.calls
        self.calls += 1
        if self.error_at == index:
            raise TimeoutError("not retained")
        analysis = OracleSemanticAnalysis.from_mapping(self.analyses[index])
        return OracleSemanticResult(
            request_sha256=request.request_sha256,
            backend_kind="live",
            preferred_model=ROUTE["model"],
            configured_provider=ROUTE["provider"],
            configured_model=ROUTE["model"],
            executed_provider=None,
            executed_model=self.models[index],
            execution_status="succeeded",
            live_call_succeeded=True,
            analysis=analysis,
        )


def test_v10_preserves_every_frozen_v9_semantic_subtree() -> None:
    contract, semantics, digest = load_candidate(REPO)
    v9 = json.loads((REPO / V9_PATH).read_text())
    assert hashlib.sha256((REPO / V9_PATH).read_bytes()).hexdigest() == V9_SHA256
    assert (
        hashlib.sha256((REPO / SEMANTICS_PATH).read_bytes()).hexdigest()
        == SEMANTICS_SHA256
    )
    assert digest == hashlib.sha256((REPO / CONTRACT_PATH).read_bytes()).hexdigest()
    inherited = set(v9) - {
        "schema_version",
        "status",
        "ak_task_id",
        "purpose",
        "source_bindings",
        "route",
        "attempt_policy",
    }
    assert all(contract[key] == v9[key] for key in inherited)
    assert contract["ak_task_id"] == TASK_ID
    assert contract["route"]["live_authorized_by_contract"] is False
    assert sum(len(codes) for codes in semantics["fields"].values()) == 26


def test_materialization_is_complete_visible_and_hidden_label_independent() -> None:
    contract, semantics, _ = load_candidate(REPO)
    for case in contract["cases"]:
        request = materialized_request(case, semantics)
        quality = request.quality_contract
        assert quality is not None
        assert quality["analysis_code_semantics"] == semantics
        assert "analysis_code_semantics_ref" not in quality
        rendered = _analysis_prompt(request)
        assert case["hidden_marker"] not in rendered
        assert json.dumps(case["hidden_labels"], sort_keys=True) not in rendered
        mutated = json.loads(json.dumps(case))
        mutated["hidden_marker"] = "HIDDEN-CANARY"
        mutated["hidden_labels"] = {"secret": "answer"}
        assert (
            materialized_request(mutated, semantics).request_sha256
            == request.request_sha256
        )


def test_response_schema_enums_derive_only_from_visible_request() -> None:
    contract, semantics, _ = load_candidate(REPO)
    for case in contract["cases"]:
        request = materialized_request(case, semantics)
        schema = _analysis_response_format(request)["schema"]["properties"]
        quality = request.quality_contract
        assert quality is not None
        for field, codes in quality["analysis_codebook"].items():
            assert schema[field]["items"]["enum"] == codes
            assert schema[field]["uniqueItems"] is True
        refs = [record["ref"] for record in request.evidence["records"]]
        assert schema["evidence_refs"]["items"]["enum"] == refs


@pytest.mark.parametrize("target", ["v9", "semantics", "source"])
def test_offline_candidate_drift_fails_without_creating_state(
    tmp_path: Path, target: str
) -> None:
    repo = _copy_candidate(tmp_path / "repo")
    path = (
        repo
        / (
            {
                "v9": V9_PATH,
                "semantics": SEMANTICS_PATH,
                "source": Path(EXPECTED_SOURCE_PATHS[0]),
            }[target]
        )
    )
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(SemanticV10Error):
        load_candidate(repo)
    assert not (tmp_path / "AK-4643").exists()


def test_contract_rejects_unknown_and_widened_fields(tmp_path: Path) -> None:
    repo = _copy_candidate(tmp_path / "repo")
    payload = json.loads((repo / CONTRACT_PATH).read_text())
    payload["fallback_route"] = "fixture"
    (repo / CONTRACT_PATH).write_text(json.dumps(payload))
    with pytest.raises(SemanticV10Error, match="fields drift"):
        load_candidate(repo)


def test_receipts_are_distinct_exact_and_no_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_identity_v10 as verification

    state, expected = _receipt_state(tmp_path)
    monkeypatch.setattr(
        verification, "committed_identity", lambda *a, **k: expected["source_identity"]
    )
    observed = validate_receipts(
        repo_root=REPO,
        state_root=state,
        require_current_commit=False,
        _test_owner_home=tmp_path,
    )
    assert observed["review_sha256"] != observed["gate_sha256"]
    assert observed["review"]["decision"] == "ACCEPT_CANDIDATE_FOR_TASK_GATE"
    assert observed["gate"]["decision"] == "AUTHORIZE_EXACTLY_ONE_CORPUS_PROCESS"
    with pytest.raises(FileExistsError):
        write_exclusive(state / LIVE_GATE_RECEIPT, expected["gate"])
    tampered = json.loads((state / LIVE_GATE_RECEIPT).read_text())
    tampered["route"]["model"] = "fallback"
    (state / LIVE_GATE_RECEIPT).write_text(json.dumps(tampered))
    with pytest.raises(SemanticV10Error, match="live-gate"):
        validate_receipts(
            repo_root=REPO,
            state_root=state,
            require_current_commit=False,
            _test_owner_home=tmp_path,
        )


def test_live_gate_creation_requires_separate_explicit_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_identity_v10 as verification

    state, expected = _receipt_state(tmp_path)
    (state / LIVE_GATE_RECEIPT).unlink()
    monkeypatch.setattr(
        verification, "committed_identity", lambda *a, **k: expected["source_identity"]
    )
    monkeypatch.setattr(
        verification,
        "dependency_identity",
        lambda: expected["review"]["dependency_identity"],
    )
    with pytest.raises(SemanticV10Error, match="explicitly authorize"):
        create_live_gate(
            repo_root=REPO,
            state_root=state,
            gate_ref="temp",
            decision="ACCEPT_CANDIDATE_FOR_TASK_GATE",
            _test_owner_home=tmp_path,
        )
    create_live_gate(
        repo_root=REPO,
        state_root=state,
        gate_ref="temp",
        decision="AUTHORIZE_EXACTLY_ONE_CORPUS_PROCESS",
        _test_owner_home=tmp_path,
    )
    assert (state / LIVE_GATE_RECEIPT).exists()


def test_standard_library_bootstrap_consumes_before_post_entry_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_evaluation_v10 as evaluation

    runner = _runner()
    state, receipts = _receipt_state(tmp_path)
    monkeypatch.setattr(evaluation, "validate_receipts", lambda **kwargs: receipts)
    monkeypatch.setattr(evaluation, "_environment_route", lambda: None)
    monkeypatch.setattr(
        evaluation,
        "_production_backend",
        lambda: pytest.fail("test root reached provider backend"),
    )
    assert runner._run(REPO, state, _test_owner_home=tmp_path) == 1
    attempt = state / ATTEMPT_DIR
    ledger = json.loads((attempt / LEDGER_NAME).read_text())
    kinds = [
        json.loads(path.read_text())["kind"]
        for path in sorted((attempt / EVENT_DIR).iterdir())
    ]
    assert ledger["status"] == "consumed"
    assert kinds[0] == "attempt_consumed"
    assert "preflight_error" in kinds and kinds[-1] == "terminal"
    assert not any(kind == "effect_possible" for kind in kinds)
    assert runner._run(REPO, state, _test_owner_home=tmp_path) == 2


def test_missing_live_gate_does_not_consume_attempt(tmp_path: Path) -> None:
    runner = _runner()
    state, _ = _receipt_state(tmp_path)
    (state / LIVE_GATE_RECEIPT).unlink()
    assert runner._run(REPO, state, _test_owner_home=tmp_path) == 2
    assert not (state / ATTEMPT_DIR).exists()


def test_tampered_preentry_receipt_does_not_consume_attempt(tmp_path: Path) -> None:
    runner = _runner()
    state, _ = _receipt_state(tmp_path)
    review = json.loads((state / CANDIDATE_RECEIPT).read_text())
    review["unexpected"] = True
    (state / CANDIDATE_RECEIPT).write_text(json.dumps(review))
    os.chmod(state / CANDIDATE_RECEIPT, 0o600)
    assert runner._run(REPO, state, _test_owner_home=tmp_path) == 2
    assert not (state / ATTEMPT_DIR).exists()


def test_alternate_task_root_cannot_create_second_attempt(tmp_path: Path) -> None:
    runner = _runner()
    state, _ = _receipt_state(tmp_path)
    alternate = _private_dir(tmp_path / "alternate")
    shutil.copyfile(state / CANDIDATE_RECEIPT, alternate / CANDIDATE_RECEIPT)
    shutil.copyfile(state / LIVE_GATE_RECEIPT, alternate / LIVE_GATE_RECEIPT)
    os.chmod(alternate / CANDIDATE_RECEIPT, 0o600)
    os.chmod(alternate / LIVE_GATE_RECEIPT, 0o600)
    assert runner._run(REPO, alternate, _test_owner_home=tmp_path) == 2
    assert not (alternate / ATTEMPT_DIR).exists()


def test_runner_has_no_selector_retry_or_preimport_dspx() -> None:
    source = RUNNER.read_text()
    before_run = source.split("def _run", 1)[0]
    assert "from dspx" not in before_run and "import dspx" not in before_run
    help_text = _runner()._parser().format_help()
    assert "--state-root" not in source
    assert "_fixed_state_root()" in source
    assert (
        "selector" not in help_text
        and "retry" not in help_text
        and "fallback" not in help_text
    )


def test_attempt_root_and_events_are_private_append_only(tmp_path: Path) -> None:
    runner = _runner()
    state = _private_dir(tmp_path / "AK-4643")
    attempt = runner._consume_attempt(state, _test_owner_home=tmp_path)
    runner._bootstrap_event(attempt, "preflight_error", classification="test")
    assert stat.S_IMODE(attempt.stat().st_mode) == 0o700
    assert stat.S_IMODE((attempt / EVENT_DIR).stat().st_mode) == 0o700
    for path in [attempt / LEDGER_NAME, *(attempt / EVENT_DIR).iterdir()]:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(RuntimeError, match="already consumed"):
        runner._consume_attempt(state, _test_owner_home=tmp_path)
    with pytest.raises(FileExistsError):
        write_exclusive(attempt / EVENT_DIR / "000001.json", {"replacement": True})


def test_exact_pass_vector_marks_before_each_fake_effect_and_calls_once(
    tmp_path: Path,
) -> None:
    contract, semantics, _ = load_candidate(REPO)
    state = _private_dir(tmp_path / "state")
    attempt = _attempt(state)
    lm = _LM()
    backend = _Backend(lm, _passing())
    rows, any_error, open_effect = _case_rows(
        contract=contract,
        semantics=semantics,
        requests=request_hashes(contract, semantics),
        attempt=attempt,
        backend=backend,
        lm=lm,
    )
    assert _disposition(rows, any_error=any_error, open_effect=open_effect) == "passed"
    assert backend.calls == 4 == lm.generate_invocation_count
    events = [event for event, _ in load_events(attempt)]
    for case_id in CASE_ORDER:
        kinds = [event["kind"] for event in events if event.get("case_id") == case_id]
        assert kinds == [
            "case_started",
            "effect_possible",
            "effect_observed",
            "case_scored",
        ]


def test_first_scored_failure_stops_without_retry(tmp_path: Path) -> None:
    contract, semantics, _ = load_candidate(REPO)
    analyses = _passing()
    analyses[0]["observations"] = ["local_quality_checks_failed"]
    state = _private_dir(tmp_path / "state")
    attempt = _attempt(state)
    lm, backend = _LM(), None
    backend = _Backend(lm, analyses)
    rows, any_error, open_effect = _case_rows(
        contract=contract,
        semantics=semantics,
        requests=request_hashes(contract, semantics),
        attempt=attempt,
        backend=backend,
        lm=lm,
    )
    assert _disposition(rows, any_error=any_error, open_effect=open_effect) == "failed"
    assert backend.calls == 1 and rows[0]["status"] == "failed"


def test_executed_model_drift_is_error_and_stops(tmp_path: Path) -> None:
    contract, semantics, _ = load_candidate(REPO)
    state = _private_dir(tmp_path / "state")
    attempt = _attempt(state)
    lm = _LM()
    backend = _Backend(lm, _passing(), models=[ROUTE["model"], "codex/drift"])
    rows, any_error, open_effect = _case_rows(
        contract=contract,
        semantics=semantics,
        requests=request_hashes(contract, semantics),
        attempt=attempt,
        backend=backend,
        lm=lm,
    )
    assert _disposition(rows, any_error=any_error, open_effect=open_effect) == "error"
    assert backend.calls == 2 and rows[-1]["status"] == "error"


def test_timeout_after_effect_marker_is_indeterminate_and_stops(tmp_path: Path) -> None:
    contract, semantics, _ = load_candidate(REPO)
    state = _private_dir(tmp_path / "state")
    attempt = _attempt(state)
    lm = _LM()
    backend = _Backend(lm, _passing(), error_at=0)
    rows, any_error, open_effect = _case_rows(
        contract=contract,
        semantics=semantics,
        requests=request_hashes(contract, semantics),
        attempt=attempt,
        backend=backend,
        lm=lm,
    )
    assert rows == [] and any_error and open_effect
    assert (
        _disposition(rows, any_error=any_error, open_effect=open_effect)
        == "effect_indeterminate"
    )
    assert backend.calls == 1
    events = [event["kind"] for event, _ in load_events(attempt)]
    assert events[-2:] == ["effect_possible", "case_error"]


def test_unexpected_base_exception_after_effect_marker_stays_open(
    tmp_path: Path,
) -> None:
    contract, semantics, _ = load_candidate(REPO)
    state = _private_dir(tmp_path / "state")
    attempt = _attempt(state)

    class CrashBackend:
        def analyze(self, request):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _case_rows(
            contract=contract,
            semantics=semantics,
            requests=request_hashes(contract, semantics),
            attempt=attempt,
            backend=CrashBackend(),
            lm=_LM(),
        )
    assert _has_open_effect(attempt) is True


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda a: a["observations"].append("accuracy_increased"), "failed"),
        (lambda a: a["observations"].clear(), "failed"),
        (lambda a: a["evidence_refs"].append("episode:authority:distractor"), "failed"),
        (lambda a: a["evidence_refs"].clear(), "failed"),
        (lambda a: a["evidence_refs"].append(a["evidence_refs"][0]), "failed"),
        (lambda a: a["observations"].append(a["observations"][0]), "failed"),
    ],
)
def test_scoring_falsifiers(mutator, expected: str) -> None:
    contract, _, _ = load_candidate(REPO)
    analysis = json.loads(json.dumps(_passing()[0]))
    mutator(analysis)
    assert score_v10(contract["cases"][0], analysis)["status"] == expected


def test_confidence_bounds_use_the_frozen_case_specific_maximum() -> None:
    contract, _, _ = load_candidate(REPO)
    analysis = json.loads(json.dumps(_passing()[1]))
    analysis["confidence"] = 1.0
    assert score_v10(contract["cases"][1], analysis)["status"] == "failed"


def test_terminal_precedence_is_effect_then_error_then_failed_then_passed(
    tmp_path: Path,
) -> None:
    state = _private_dir(tmp_path / "state")
    attempt = _attempt(state)
    append_event(
        attempt,
        "case_scored",
        case_id=CASE_ORDER[0],
        status="failed",
        score_sha256="a" * 64,
    )
    append_event(attempt, "preflight_error", classification="test")
    append_event(attempt, "effect_possible", effect_token="open", case_id=CASE_ORDER[0])
    assert derive_disposition(load_events(attempt), None) == "effect_indeterminate"
    assert _disposition([], any_error=True, open_effect=False) == "error"
    assert (
        _disposition(
            [{"case_id": CASE_ORDER[0], "status": "failed"}],
            any_error=False,
            open_effect=False,
        )
        == "failed"
    )
    assert (
        _disposition(
            [{"case_id": case, "status": "passed"} for case in CASE_ORDER],
            any_error=False,
            open_effect=False,
        )
        == "passed"
    )


def _terminal_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disposition: str = "error"
) -> tuple[Path, Path]:
    import dspx.services.program_oracle_semantic_identity_v10 as verification

    state, receipts = _receipt_state(tmp_path)
    monkeypatch.setattr(
        verification, "committed_identity", lambda *a, **k: receipts["source_identity"]
    )
    attempt = _attempt(state)
    for name, payload in (
        (CONTRACT_SNAPSHOT, receipts["contract"]),
        (REVIEW_SNAPSHOT, receipts["review"]),
        (GATE_SNAPSHOT, receipts["gate"]),
    ):
        write_exclusive(attempt / name, payload)
    rows: list[dict[str, Any]] = []
    if disposition == "error":
        append_event(attempt, "preflight_error", classification="dependency_error")
    elif disposition == "failed":
        append_event(
            attempt,
            "preflight_passed",
            contract_sha256=receipts["contract_sha256"],
            candidate_review_sha256=receipts["review_sha256"],
            live_gate_sha256=receipts["gate_sha256"],
        )
        case = receipts["contract"]["cases"][0]
        request = materialized_request(case, receipts["semantics"])
        analysis = _passing()[0]
        analysis["observations"] = ["local_quality_checks_failed"]
        semantic = OracleSemanticResult(
            request_sha256=request.request_sha256,
            backend_kind="live",
            preferred_model=ROUTE["model"],
            configured_provider=ROUTE["provider"],
            configured_model=ROUTE["model"],
            executed_provider=None,
            executed_model=ROUTE["model"],
            execution_status="succeeded",
            live_call_succeeded=True,
            analysis=OracleSemanticAnalysis.from_mapping(analysis),
        ).to_dict()
        score = score_v10(case, analysis)
        append_event(
            attempt,
            "case_started",
            case_id=CASE_ORDER[0],
            request_sha256=request.request_sha256,
        )
        append_event(
            attempt,
            "effect_possible",
            case_id=CASE_ORDER[0],
            request_sha256=request.request_sha256,
            effect_token="case:generate:1",
            generate_invocation=1,
        )
        append_event(
            attempt,
            "effect_observed",
            case_id=CASE_ORDER[0],
            effect_token="case:generate:1",
            generate_invocation_delta=1,
            history_delta=1,
            response_attributable=True,
        )
        append_event(
            attempt,
            "case_scored",
            case_id=CASE_ORDER[0],
            status="failed",
            score_sha256=sha256(
                json.dumps(score, sort_keys=True, separators=(",", ":")).encode()
            ),
        )
        rows = [
            {
                "case_id": CASE_ORDER[0],
                "request_sha256": request.request_sha256,
                "semantic_result": semantic,
                "score": score,
                "status": "failed",
            }
        ]
    _terminal_result(
        attempt=attempt,
        receipts=receipts,
        rows=rows,
        disposition=disposition,
        dependency=receipts["review"]["dependency_identity"],
        preflight_error="dependency_error" if disposition == "error" else None,
    )
    return state, attempt


def test_provider_free_verifier_separates_integrity_from_empirical_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, _ = _terminal_packet(tmp_path, monkeypatch, "error")
    packet = verify_evaluation(
        repo_root=REPO, state_root=state, _test_owner_home=tmp_path
    )
    assert packet["artifact_integrity_review"] == "accepted"
    assert packet["empirical_gate"] == "error"
    assert packet["provider_invoked_by_verifier"] is False
    assert (
        verify_evaluation(repo_root=REPO, state_root=state, _test_owner_home=tmp_path)
        == packet
    )


def test_typed_response_error_row_verifies_without_model_list_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_identity_v10 as identity

    state, receipts = _receipt_state(tmp_path)
    monkeypatch.setattr(
        identity, "committed_identity", lambda *a, **k: receipts["source_identity"]
    )
    attempt = _attempt(state)
    for name, payload in (
        (CONTRACT_SNAPSHOT, receipts["contract"]),
        (REVIEW_SNAPSHOT, receipts["review"]),
        (GATE_SNAPSHOT, receipts["gate"]),
    ):
        write_exclusive(attempt / name, payload)
    case_id = CASE_ORDER[0]
    append_event(
        attempt,
        "preflight_passed",
        contract_sha256=receipts["contract_sha256"],
        candidate_review_sha256=receipts["review_sha256"],
        live_gate_sha256=receipts["gate_sha256"],
    )
    request_sha = receipts["request_hashes"][case_id]
    append_event(attempt, "case_started", case_id=case_id, request_sha256=request_sha)
    append_event(
        attempt,
        "effect_possible",
        case_id=case_id,
        request_sha256=request_sha,
        effect_token="error:1",
        generate_invocation=1,
    )
    append_event(
        attempt,
        "effect_observed",
        case_id=case_id,
        effect_token="error:1",
        generate_invocation_delta=1,
        history_delta=1,
        response_attributable=True,
    )
    append_event(
        attempt, "case_error", case_id=case_id, classification="typed_response_error"
    )
    semantic = OracleSemanticResult(
        request_sha256=request_sha,
        backend_kind="live",
        preferred_model=ROUTE["model"],
        configured_provider=ROUTE["provider"],
        configured_model=ROUTE["model"],
        executed_provider=None,
        executed_model=ROUTE["model"],
        execution_status="failed_after_live_response",
        live_call_succeeded=True,
        error="bounded malformed response",
    ).to_dict()
    _terminal_result(
        attempt=attempt,
        receipts=receipts,
        rows=[
            {
                "case_id": case_id,
                "request_sha256": request_sha,
                "semantic_result": semantic,
                "score": None,
                "status": "error",
            }
        ],
        disposition="error",
        dependency=receipts["review"]["dependency_identity"],
        preflight_error="typed_response_error",
    )
    packet = verify_evaluation(
        repo_root=REPO, state_root=state, _test_owner_home=tmp_path
    )
    assert packet["artifact_integrity_review"] == "accepted"
    assert packet["empirical_gate"] == "error"


def test_verifier_accepts_truthful_open_effect_as_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_identity_v10 as verification

    state, receipts = _receipt_state(tmp_path)
    monkeypatch.setattr(
        verification, "committed_identity", lambda *a, **k: receipts["source_identity"]
    )
    attempt = _attempt(state)
    request_sha = receipts["request_hashes"][CASE_ORDER[0]]
    for name, payload in (
        (CONTRACT_SNAPSHOT, receipts["contract"]),
        (REVIEW_SNAPSHOT, receipts["review"]),
        (GATE_SNAPSHOT, receipts["gate"]),
    ):
        write_exclusive(attempt / name, payload)
    append_event(
        attempt,
        "preflight_passed",
        contract_sha256=receipts["contract_sha256"],
        candidate_review_sha256=receipts["review_sha256"],
        live_gate_sha256=receipts["gate_sha256"],
    )
    append_event(
        attempt, "case_started", case_id=CASE_ORDER[0], request_sha256=request_sha
    )
    append_event(
        attempt,
        "effect_possible",
        effect_token="case:generate:1",
        case_id=CASE_ORDER[0],
        request_sha256=request_sha,
        generate_invocation=1,
    )
    packet = verify_evaluation(
        repo_root=REPO, state_root=state, _test_owner_home=tmp_path
    )
    assert packet["artifact_integrity_review"] == "accepted"
    assert packet["empirical_gate"] == "effect_indeterminate"
    assert packet["result_sha256"] is None


@pytest.mark.parametrize(
    "target",
    ["receipt", "receipt_mode", "ledger", "event", "result", "snapshot", "mode"],
)
def test_verifier_rejects_tampered_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    state, attempt = _terminal_packet(tmp_path, monkeypatch, "error")
    path = {
        "receipt": state / LIVE_GATE_RECEIPT,
        "receipt_mode": state / LIVE_GATE_RECEIPT,
        "ledger": attempt / LEDGER_NAME,
        "event": attempt / EVENT_DIR / "000001.json",
        "result": attempt / RESULT_NAME,
        "snapshot": attempt / CONTRACT_SNAPSHOT,
        "mode": attempt / RESULT_NAME,
    }[target]
    if target in {"mode", "receipt_mode"}:
        os.chmod(path, 0o644)
    else:
        payload = json.loads(path.read_text())
        payload["tampered"] = True
        path.write_text(json.dumps(payload))
        os.chmod(path, 0o600)
    with pytest.raises(SemanticV10Error):
        verify_evaluation(repo_root=REPO, state_root=state, _test_owner_home=tmp_path)


def test_retained_verification_mode_drift_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, attempt = _terminal_packet(tmp_path, monkeypatch, "error")
    verify_evaluation(repo_root=REPO, state_root=state, _test_owner_home=tmp_path)
    os.chmod(attempt / "independent-verification.json", 0o644)
    with pytest.raises(SemanticV10Error):
        verify_evaluation(repo_root=REPO, state_root=state, _test_owner_home=tmp_path)


def test_no_authority_or_raw_output_fields_in_terminal_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, attempt = _terminal_packet(tmp_path, monkeypatch, "failed")
    rendered = (attempt / RESULT_NAME).read_text()
    forbidden = [
        "access_token",
        "authorization_header",
        "auth_store_path",
        "raw_provider_output",
    ]
    assert not any(item in rendered for item in forbidden)
    contract, _, _ = load_candidate(REPO)
    assert contract["privacy_and_effects"]["retain_raw_provider_output"] is False
    assert contract["privacy_and_effects"]["shared_store_connections"] == 0
    assert contract["nonclaims"]["production_activation"] is False
    packet = verify_evaluation(
        repo_root=REPO, state_root=state, _test_owner_home=tmp_path
    )
    assert packet["empirical_gate"] == "failed"
