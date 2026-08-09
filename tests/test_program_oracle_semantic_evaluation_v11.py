from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from dspx.services.program_oracle_semantic_artifacts_v11 import (
    REQUIRED_LIVE_COMPLETION_KIND,
    TaskBinding,
    assert_attempt_absent,
    consume_attempt,
    consume_fixture_attempt,
    load_case_custody,
    load_consumed_attempt,
)
from dspx.services.program_oracle_semantic_contract_v10 import INHERITED_KEYS
from dspx.services.program_oracle_semantic_contract_v11 import (
    CASE_ORDER,
    CONSUMER_MODULE_HASHES,
    CONTRACT_PATH,
    CONTRACT_SHA256,
    PROPOSAL_PATH,
    PROPOSAL_SHA256,
    SEMANTIC_KEYS,
    V10_PATH,
    BoundContractCase,
    SemanticV11Error,
    canonical,
    load_bound_cases,
    load_candidate,
    materialized_request,
    semantic_request_projection,
    semantic_request_sha256,
    sha256,
)
from dspx.services.program_oracle_semantic_evaluation_v11 import (
    EvaluatedCase,
    normalized_semantic_request,
)
from dspx.services.program_oracle_semantic_gate4_v11 import (
    EXACT_ROUTE,
    GATE4_DONE_CONTRACT,
    GATE4_GUARDRAILS,
    Gate4AuthorityCapability,
    authenticate_gate4_authority,
    candidate_source_manifest_sha256,
    validate_gate4_authority_documents,
)
from dspx.services.program_oracle_semantic_identity_v11 import (
    prepare_receipt,
    verify_exact_owner,
)
from dspx.services.program_oracle_semantic_result_artifact_v11 import (
    write_evaluation_result,
)
from dspx.services.program_oracle_semantic_result_v11 import (
    VerifiedSemanticResult,
    evaluate_semantic_response,
)
from dspx.services.program_oracle_semantic_runner_v11 import run_corpus
from dspx.services.program_oracle_semantic_verification_v11 import (
    candidate_manifest,
    verify_retained_evaluation,
    write_independent_verification,
)
from dspx.services.provider_outcome_receipt_contract import (
    ProviderOutcomeConsumerError,
    ReceiptProjection,
)

REPO = Path(__file__).resolve().parents[1]
OWNER_ROOT = Path(
    os.environ.get(
        "DSPX_PROVIDER_OUTCOME_OWNER_SOURCE",
        "/home/tryinget/.local/state/pi-quests/tmp/dspy-lm-auth-ak4672-outcome-receipt",
    )
)
RUNNER = REPO / "scripts/ci/run_oracle_semantic_analysis_evaluation_v11.py"


def _private(path: Path) -> Path:
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def _copy_candidate(tmp_path: Path) -> Path:
    paths = [
        CONTRACT_PATH,
        V10_PATH,
        Path("benchmarks/semantic/oracle-semantic-analysis-evaluation-v9.json"),
        Path("benchmarks/semantic/oracle-semantic-code-semantics-v1.json"),
        PROPOSAL_PATH,
    ]
    paths.extend(
        Path("packages/dspx-core/src/dspx/services") / name
        for name in CONSUMER_MODULE_HASHES
    )
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    return tmp_path


def _machine(surface: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"surface": surface, "ok": True, "payload": dict(payload), "error": None}


def _authority_documents(
    task_id: int, review_id: int, gate_id: int
) -> tuple[dict[str, Any], ...]:
    commit = "1" * 40
    tree = "2" * 40
    review_task_id = task_id + 300_000
    source_manifest = candidate_source_manifest_sha256(REPO)
    task = {
        "id": task_id,
        "repo": str(REPO),
        "status": "claimed",
        "entity_version": 7,
    }
    contract = {
        "task_id": task_id,
        "repo": str(REPO),
        "title": "Exact Oracle semantic v11 live execution",
        "status": "claimed",
        "done_contract": {
            "id": 1,
            "task_id": task_id,
            "entity_version": 1,
            "contract": GATE4_DONE_CONTRACT,
            "created_at": "bounded",
            "updated_at": "bounded",
        },
        "guardrails": {
            "id": 2,
            "task_id": task_id,
            "entity_version": 1,
            "guardrails": GATE4_GUARDRAILS,
            "created_at": "bounded",
            "updated_at": "bounded",
        },
    }
    review_task = {
        "id": review_task_id,
        "repo": str(REPO),
        "status": "done",
        "entity_version": 3,
    }
    review_contract = {
        "task_id": review_task_id,
        "repo": str(REPO),
        "title": "Exact Oracle semantic v11 candidate review",
        "status": "done",
        "done_contract": {
            "id": 3,
            "task_id": review_task_id,
            "entity_version": 1,
            "contract": {
                "completion_kind": "oracle_semantic_v11_candidate_review",
                "required_outcomes": ["exact candidate accepted or rejected"],
                "required_validation": ["provider-free full gate"],
                "required_evidence_classes": ["exact review"],
                "review_questions": [],
            },
            "created_at": "bounded",
            "updated_at": "bounded",
        },
        "guardrails": None,
    }
    review = {
        "schema_version": "dspx-oracle-semantic-v11-candidate-review-v1",
        "gate_2_task_id": 4691,
        "gate_3_task_id": review_task_id,
        "decision": "ACCEPT_V11_CANDIDATE_FOR_SEPARATE_LIVE_GATE",
        "contract_sha256": CONTRACT_SHA256,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest_sha256": source_manifest,
        "provider_free_gate": "passed",
    }
    gate = {
        "schema_version": "dspx-oracle-semantic-v11-live-gate-v1",
        "live_task_id": task_id,
        "completion_kind": REQUIRED_LIVE_COMPLETION_KIND,
        "decision": "AUTHORIZE_EXACTLY_ONE_V11_CORPUS_PROCESS",
        "operator_authorization": (
            "OPERATOR_AUTHORIZED_EXACTLY_ONE_V11_CORPUS_PROCESS"
        ),
        "candidate_review_evidence_id": review_id,
        "candidate_review_sha256": sha256(canonical(review)),
        "contract_sha256": CONTRACT_SHA256,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest_sha256": source_manifest,
        "task_entity_version": 7,
        "task_contract_sha256": sha256(canonical(contract)),
        "route": EXACT_ROUTE,
        "maximum_corpus_processes": 1,
        "maximum_health_probes": 0,
        "maximum_dspx_managed_retries": 0,
        "fallback_allowed": False,
    }
    review_evidence = {
        "id": review_id,
        "task_ref": review_task_id,
        "check_type": "oracle_semantic_v11_candidate_review",
        "result": "pass",
        "details": review,
    }
    gate_evidence = {
        "id": gate_id,
        "task_ref": task_id,
        "check_type": "oracle_semantic_v11_live_gate",
        "result": "pass",
        "details": gate,
    }
    return (
        _machine("task.show", {"task": task}),
        contract,
        _machine("task.show", {"task": review_task}),
        review_contract,
        _machine("evidence.show", {"evidence": review_evidence}),
        _machine("evidence.show", {"evidence": gate_evidence}),
    )


def _authority(task_id: int) -> Gate4AuthorityCapability:
    review_id = task_id + 100_000
    gate_id = task_id + 200_000
    review_task_id = task_id + 300_000
    documents = _authority_documents(task_id, review_id, gate_id)

    def fake_ak(*args: str) -> dict[str, Any]:
        if args[:2] == ("evidence", "show") and args[2] == str(review_id):
            return documents[4]
        if args[:2] == ("evidence", "show") and args[2] == str(gate_id):
            return documents[5]
        if args[:2] == ("task", "show") and args[2] == str(task_id):
            return documents[0]
        if args[:3] == ("task", "contract", "show") and args[3] == str(task_id):
            return documents[1]
        if args[:2] == ("task", "show") and args[2] == str(review_task_id):
            return documents[2]
        if args[:3] == ("task", "contract", "show") and args[3] == str(review_task_id):
            return documents[3]
        raise AssertionError(args)

    with (
        patch(
            "dspx.services.program_oracle_semantic_gate4_v11._run_ak",
            side_effect=fake_ak,
        ),
        patch(
            "dspx.services.program_oracle_semantic_gate4_v11._git_identity",
            return_value=("1" * 40, "2" * 40),
        ),
    ):
        return authenticate_gate4_authority(
            repo_root=REPO,
            live_task_id=task_id,
            review_evidence_id=review_id,
            gate_evidence_id=gate_id,
        )


@contextmanager
def _owner_types() -> Iterator[tuple[Any, Any, Any, Any]]:
    source = str(OWNER_ROOT / "src")
    sys.path.insert(0, source)
    try:
        package = importlib.import_module("dspy_lm_auth")
        owner_lm_module = importlib.import_module("dspy_lm_auth.lm")
        yield (
            package.OutcomeReceiptEvent,
            package.ProviderOutcomeReceipt,
            owner_lm_module.LM,
            owner_lm_module,
        )
    finally:
        if sys.path[0] == source:
            sys.path.pop(0)


def _passing_analysis(case: BoundContractCase) -> dict[str, Any]:
    hidden = case.case["hidden_labels"]
    return {
        **hidden["expected_codes"],
        "evidence_refs": hidden["expected_evidence_refs"],
        "confidence": 0.8,
    }


def _sink(prepared: Any, event: object) -> None:
    sink = getattr(prepared._provider_receipt, "sink", None)
    if not callable(sink):
        raise AssertionError("exact owner receipt sink missing")
    sink(event)


def _delegate_to_exact_owner_environment(test_name: str) -> bool:
    if os.environ.get("DSPX_EXACT_OWNER_CHILD") == "1":
        return False
    python = OWNER_ROOT / ".venv/bin/python"
    env = {
        **os.environ,
        "DSPX_EXACT_OWNER_CHILD": "1",
        "DSPX_PROVIDER_OUTCOME_OWNER_SOURCE": str(OWNER_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            [str(OWNER_ROOT / "src"), str(REPO / "packages/dspx-core/src")]
        ),
    }
    completed = subprocess.run(
        [
            str(python),
            "-m",
            "pytest",
            "-q",
            f"{Path(__file__).name}::{test_name}",
        ],
        cwd=Path(__file__).parent,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return True


def _terminal_events(event_type: Any, response_id: str, model: str = "gpt-5.6-sol"):
    return [
        event_type(kind="wrapper_request_accepted"),
        event_type(kind="transport_gate_entered", gate_ordinal=1),
        event_type(kind="transport_effect_pending", gate_ordinal=1),
        event_type(kind="transport_entered", gate_ordinal=1),
        event_type(kind="http_response_observed", gate_ordinal=1, status_class=2),
        event_type(
            kind="parsed_protocol_event_observed",
            protocol_event="response.completed",
            response_id_sha256=response_id,
        ),
        event_type(
            kind="provider_response_completed",
            status_class=2,
            response_id_sha256=response_id,
            observed_model=model,
        ),
    ]


def test_candidate_contract_preserves_all_v10_semantic_subtrees():
    contract, semantics, digest = load_candidate(REPO)
    v10 = json.loads((REPO / V10_PATH).read_text())
    assert digest == CONTRACT_SHA256
    assert tuple(case["id"] for case in contract["cases"]) == CASE_ORDER
    for key in INHERITED_KEYS:
        assert canonical(contract[key]) == canonical(v10[key])
    assert (
        hashlib.sha256((REPO / PROPOSAL_PATH).read_bytes()).hexdigest()
        == PROPOSAL_SHA256
    )
    assert semantics["schema_version"] == "dspx-oracle-semantic-code-semantics-v1"


def test_candidate_rejects_contract_and_consumer_tamper(tmp_path):
    root = _copy_candidate(tmp_path)
    path = root / CONTRACT_PATH
    value = json.loads(path.read_text())
    value["thresholds"]["minimum_case_score"] = 0.99
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    with pytest.raises(SemanticV11Error, match="inherited subtree"):
        load_candidate(root, check_sources=False)

    root = _copy_candidate(tmp_path / "consumer")
    target = (
        root
        / "packages/dspx-core/src/dspx/services/provider_outcome_receipt_contract.py"
    )
    target.write_text(target.read_text() + "\n# drift\n")
    with pytest.raises(SemanticV11Error, match="consumer source"):
        load_candidate(root)


def test_bound_cases_close_caller_authored_scoring_and_are_immutable():
    cases = load_bound_cases(REPO)
    case = cases[0]
    with pytest.raises(TypeError, match="exact contract"):
        BoundContractCase(
            case_id=case.case_id,
            case_ordinal=1,
            contract_sha256=CONTRACT_SHA256,
            contract_raw=(REPO / CONTRACT_PATH).read_bytes(),
            case=case.case,
            semantics={},
            token=object(),
        )
    forged = case.case
    forged["hidden_labels"]["expected_codes"]["observations"] = ["forged"]
    with pytest.raises(SemanticV11Error, match="bound semantic case"):
        evaluate_semantic_response(forged, "{}")  # ty: ignore[invalid-argument-type]
    result = evaluate_semantic_response(case, json.dumps(_passing_analysis(case)))
    assert result.outcome == "score_pass"
    before = result.payload()
    analysis = dict(result.analysis or {})
    score = dict(result.score or {})
    analysis["observations"] = ["caller-authored-drift"]
    score["status"] = "failed"
    assert result.payload() == before
    with pytest.raises(TypeError, match="immutable"):
        result._analysis_raw = b"{}"
    with pytest.raises(TypeError, match="deterministic scoring"):
        VerifiedSemanticResult(
            case=case,
            outcome="score_pass",
            analysis={},
            score={"status": "passed"},
            analysis_sha256="a" * 64,
            token=object(),
        )


def test_semantic_request_requires_exact_seven_keys_and_hides_labels():
    cases = load_bound_cases(REPO)
    semantic = normalized_semantic_request(cases[0].materialized_request())
    assert set(semantic) == SEMANTIC_KEYS
    baseline = semantic_request_sha256(semantic)
    assert semantic_request_sha256({**semantic, "temperature": None}) == baseline
    with pytest.raises(SemanticV11Error, match="missing"):
        semantic_request_projection(
            {key: value for key, value in semantic.items() if key != "text"}
        )
    with pytest.raises(SemanticV11Error, match="unsupported"):
        semantic_request_projection({**semantic, "api_key": "forbidden"})
    contract, semantics, _ = load_candidate(REPO)
    mutable = json.loads(json.dumps(contract["cases"][0]))
    before = materialized_request(mutable, semantics).request_sha256
    mutable["hidden_labels"]["expected_codes"]["observations"] = ["hidden-drift"]
    assert materialized_request(mutable, semantics).request_sha256 == before


def test_caller_json_cannot_mint_gate4_authority(tmp_path):
    task_id, review_id, gate_id = 900001, 910001, 920001
    documents = _authority_documents(task_id, review_id, gate_id)
    with patch(
        "dspx.services.program_oracle_semantic_gate4_v11._git_identity",
        return_value=("1" * 40, "2" * 40),
    ):
        facts = validate_gate4_authority_documents(
            repo_root=REPO,
            live_task_id=task_id,
            review_evidence_id=review_id,
            gate_evidence_id=gate_id,
            task_document=documents[0],
            contract_document=documents[1],
            review_task_document=documents[2],
            review_contract_document=documents[3],
            review_evidence_document=documents[4],
            gate_evidence_document=documents[5],
        )
    assert facts["live_task_id"] == task_id
    with pytest.raises(TypeError, match="canonical AK authentication"):
        Gate4AuthorityCapability(**facts, token=object())
    state = _private(tmp_path / "state")
    with pytest.raises(SemanticV11Error, match="canonical Gate-4"):
        consume_attempt(state, facts)  # ty: ignore[invalid-argument-type]
    assert list(state.iterdir()) == []


def test_authority_tamper_rejected_before_mint():
    task_id, review_id, gate_id = 900002, 910002, 920002
    documents = list(_authority_documents(task_id, review_id, gate_id))
    documents[5] = json.loads(json.dumps(documents[5]))
    documents[5]["payload"]["evidence"]["details"]["maximum_dspx_managed_retries"] = 1

    def fake_ak(*args: str) -> dict[str, Any]:
        if args[:2] == ("evidence", "show") and args[2] == str(review_id):
            return documents[4]
        if args[:2] == ("evidence", "show") and args[2] == str(gate_id):
            return documents[5]
        if args[:2] == ("task", "show") and args[2] == str(task_id):
            return documents[0]
        if args[:3] == ("task", "contract", "show") and args[3] == str(task_id):
            return documents[1]
        if args[:2] == ("task", "show"):
            return documents[2]
        if args[:3] == ("task", "contract", "show"):
            return documents[3]
        raise AssertionError(args)

    with (
        patch(
            "dspx.services.program_oracle_semantic_gate4_v11._run_ak",
            side_effect=fake_ak,
        ),
        patch(
            "dspx.services.program_oracle_semantic_gate4_v11._git_identity",
            return_value=("1" * 40, "2" * 40),
        ),
        pytest.raises(SemanticV11Error, match="Gate-4 authorization"),
    ):
        authenticate_gate4_authority(
            repo_root=REPO,
            live_task_id=task_id,
            review_evidence_id=review_id,
            gate_evidence_id=gate_id,
        )


def test_fixture_attempt_is_authority_false_and_private(tmp_path):
    root = _private(tmp_path / "state")
    binding = TaskBinding.create(900003, REQUIRED_LIVE_COMPLETION_KIND)
    assert_attempt_absent(root, binding)
    attempt = consume_fixture_attempt(root, binding)
    assert attempt.live_authorized is False
    assert stat.S_IMODE(attempt.attempt_root.stat().st_mode) == 0o700
    raw = (attempt.attempt_root / "ledger.json").read_bytes()
    assert b'"live_authorized":false' in raw
    assert b'"uid"' not in raw and b'"boot_id"' not in raw and b"/home/" not in raw
    with pytest.raises(SemanticV11Error, match="Gate-4 capability"):
        attempt.require_live()
    loaded = load_consumed_attempt(root, binding)
    assert loaded.ledger_sha256 == attempt.ledger_sha256
    with pytest.raises(SemanticV11Error, match="already exists"):
        assert_attempt_absent(root, binding)


def test_live_authority_consumes_once_and_process_digest_is_tamper_evident(tmp_path):
    root = _private(tmp_path / "state")
    authority = _authority(900004)
    attempt = consume_attempt(root, authority)
    assert attempt.live_authorized is True
    attempt.require_live()
    with pytest.raises(SemanticV11Error, match="already consumed"):
        consume_attempt(_private(tmp_path / "other"), authority)
    ledger_path = attempt.attempt_root / "ledger.json"
    ledger = json.loads(ledger_path.read_bytes())
    ledger["process_identity_sha256"] = "0" * 64
    ledger_path.write_bytes(canonical(ledger))
    with pytest.raises(SemanticV11Error, match="process custody|bytes drift"):
        attempt.require_live()


def test_caller_cannot_construct_aggregate_projection():
    projection = ReceiptProjection(
        provider_outcome_receipt="accepted",
        request_acknowledged=True,
        external_effect_possible=True,
        producer_terminal="provider_response_completed",
        empirical_disposition="passed",
        reason="provider_response_completed",
    )
    with pytest.raises(TypeError, match="retained case custody"):
        EvaluatedCase(
            case_id="authority-boundary",
            semantic_outcome="score_pass",
            score={"status": "passed"},
            projection=projection,
            observed_model="forged",
            token=object(),
        )


def test_exact_owner_receipt_full_corpus_result_and_gate5_rederive(tmp_path):
    if _delegate_to_exact_owner_environment(
        "test_exact_owner_receipt_full_corpus_result_and_gate5_rederive"
    ):
        return
    root = _private(tmp_path / "state")
    attempt = consume_attempt(root, _authority(900010))
    cases = load_bound_cases(REPO)
    with _owner_types() as (event_type, receipt_type, owner_lm_type, _):
        owner = verify_exact_owner(OWNER_ROOT, event_type, receipt_type, owner_lm_type)
        for case in cases:
            semantic = normalized_semantic_request(case.materialized_request())
            prepared = prepare_receipt(
                attempt,
                case=case,
                semantic_request=semantic,
                endpoint_origin_sha256="d" * 64,
                artifact=owner,
            )
            assert not hasattr(prepared, "provider_receipt")
            assert (
                semantic_request_sha256(prepared.semantic_request)
                == prepared.reservation.semantic_request_sha256
            )
            response_id = f"{case.case_ordinal}" * 64
            for event in _terminal_events(event_type, response_id[:64]):
                _sink(prepared, event)
            result = evaluate_semantic_response(
                case, json.dumps(_passing_analysis(case))
            )
            projection = prepared.record_terminal(result)
            assert projection.empirical_disposition == "passed"
        payload = write_evaluation_result(attempt, cases, owner.artifact)
        assert payload["empirical_gate"] == "passed"
        assert payload["operation_counts"]["reached_requests"] == 4
        assert payload["artifact_integrity_review"] == "not_evaluated"
        assert payload["candidate_commit"] == "1" * 40
        assert payload["candidate_tree"] == "2" * 40
        assert payload["cases"][0]["provider_outcome"]["fixture_only"] is True
        assert payload["cases"][0]["provider_outcome"]["v11_authorized"] is False
        with patch(
            "dspx.services.program_oracle_semantic_verification_v11._git_identity",
            return_value=("1" * 40, "2" * 40),
        ):
            _, verified = verify_retained_evaluation(
                repo_root=REPO,
                state_root=root,
                live_task_id=900010,
                artifact=owner.artifact,
            )
            assert verified["empirical_gate"] == "passed"
            written = write_independent_verification(
                repo_root=REPO,
                state_root=root,
                live_task_id=900010,
                artifact=owner.artifact,
            )
            assert written["live_execution_authorized"] is False
            with pytest.raises(SemanticV11Error, match="already exists"):
                write_independent_verification(
                    repo_root=REPO,
                    state_root=root,
                    live_task_id=900010,
                    artifact=owner.artifact,
                )
            debug_path = attempt.attempt_root / "debug.json"
            debug_path.write_bytes(canonical({"access_token": "forbidden"}))
            debug_path.chmod(0o600)
            with pytest.raises(SemanticV11Error, match="tree grammar|private data"):
                verify_retained_evaluation(
                    repo_root=REPO,
                    state_root=root,
                    live_task_id=900010,
                    artifact=owner.artifact,
                )


def test_late_callback_after_durable_terminal_preserves_disk_rederived_completion(
    tmp_path,
):
    if _delegate_to_exact_owner_environment(
        "test_late_callback_after_durable_terminal_preserves_disk_rederived_completion"
    ):
        return
    root = _private(tmp_path / "state")
    attempt = consume_attempt(root, _authority(900020))
    case = load_bound_cases(REPO)[0]
    with _owner_types() as (event_type, receipt_type, owner_lm_type, _):
        owner = verify_exact_owner(OWNER_ROOT, event_type, receipt_type, owner_lm_type)
        prepared = prepare_receipt(
            attempt,
            case=case,
            semantic_request=normalized_semantic_request(case.materialized_request()),
            endpoint_origin_sha256="d" * 64,
            artifact=owner,
        )
        for event in _terminal_events(event_type, "e" * 64):
            _sink(prepared, event)
        with pytest.raises(ProviderOutcomeConsumerError) as caught:
            _sink(prepared, event_type(kind="wrapper_request_accepted"))
        assert caught.value.reason == "event_after_terminal"
        projection = prepared.record_terminal(
            evaluate_semantic_response(case, json.dumps(_passing_analysis(case)))
        )
        assert projection.producer_terminal == "provider_response_completed"
        assert projection.empirical_disposition == "passed"
        next_case = case.case_at(2)
        next_prepared = prepare_receipt(
            attempt,
            case=next_case,
            semantic_request=normalized_semantic_request(
                next_case.materialized_request()
            ),
            endpoint_origin_sha256="d" * 64,
            artifact=owner,
        )
        assert next_prepared.case_ordinal == 2


def test_terminal_tamper_blocks_continuation_even_when_score_pass_is_retained(tmp_path):
    if _delegate_to_exact_owner_environment(
        "test_terminal_tamper_blocks_continuation_even_when_score_pass_is_retained"
    ):
        return
    root = _private(tmp_path / "state")
    attempt = consume_attempt(root, _authority(900030))
    cases = load_bound_cases(REPO)
    with _owner_types() as (event_type, receipt_type, owner_lm_type, _):
        owner = verify_exact_owner(OWNER_ROOT, event_type, receipt_type, owner_lm_type)
        prepared = prepare_receipt(
            attempt,
            case=cases[0],
            semantic_request=normalized_semantic_request(
                cases[0].materialized_request()
            ),
            endpoint_origin_sha256="d" * 64,
            artifact=owner,
        )
        for event in _terminal_events(event_type, "f" * 64):
            _sink(prepared, event)
        prepared.record_terminal(
            evaluate_semantic_response(
                cases[0], json.dumps(_passing_analysis(cases[0]))
            )
        )
        terminal_path = attempt.attempt_root / "case-custody/01-terminal.json"
        terminal = json.loads(terminal_path.read_bytes())
        terminal["semantic_result"]["score"]["status"] = "failed"
        terminal["semantic_result_sha256"] = sha256(
            canonical(terminal["semantic_result"])
        )
        terminal_path.write_bytes(canonical(terminal))
        with pytest.raises(SemanticV11Error, match="semantic score|terminal"):
            prepare_receipt(
                attempt,
                case=cases[1],
                semantic_request=normalized_semantic_request(
                    cases[1].materialized_request()
                ),
                endpoint_origin_sha256="d" * 64,
                artifact=owner,
            )


def test_candidate_manifest_and_runner_are_provider_free_by_default():
    manifest = candidate_manifest(REPO)
    assert manifest["provider_invoked"] is False
    assert manifest["fixture_only"] is True
    assert manifest["live_execution_authorized"] is False
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--repo",
            str(REPO),
            "--task-binding-check",
            "900040",
        ],
        cwd=REPO,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["provider_invoked"] is False
    assert payload["task_binding"]["live_task_id"] == 900040


def test_post_entry_setup_failure_terminalizes_consumed_result(tmp_path):
    root = _private(tmp_path / "state")
    with pytest.raises(Exception):
        run_corpus(
            repo_root=REPO,
            state_root=root,
            owner_source_root=tmp_path / "missing-owner",
            authority=_authority(900041),
        )
    attempt_root = root / "oracle-semantic-analysis-evaluations/AK-900041/v11/attempt"
    assert (attempt_root / "ledger.json").is_file()
    result = json.loads((attempt_root / "evaluation-result.json").read_bytes())
    assert result["empirical_gate"] == "error"
    assert result["artifact_integrity_review"] == "not_evaluated"
    assert result["operation_counts"]["reached_requests"] == 0
    assert result["pre_effect_setup_terminal_sha256"] is not None


def test_per_case_pre_effect_failures_terminalize_error_results(tmp_path):
    if _delegate_to_exact_owner_environment(
        "test_per_case_pre_effect_failures_terminalize_error_results"
    ):
        return

    receipt_root = _private(tmp_path / "receipt-state")
    with (
        patch(
            "dspx.services.provider_outcome_receipt_journal.ReceiptJournal.create",
            side_effect=ProviderOutcomeConsumerError("journal_root_create_failed"),
        ),
        pytest.raises(ProviderOutcomeConsumerError),
    ):
        run_corpus(
            repo_root=REPO,
            state_root=receipt_root,
            owner_source_root=OWNER_ROOT,
            authority=_authority(900042),
        )
    receipt_attempt = (
        receipt_root / "oracle-semantic-analysis-evaluations/AK-900042/v11/attempt"
    )
    receipt_result = json.loads(
        (receipt_attempt / "evaluation-result.json").read_bytes()
    )
    receipt_terminal = json.loads(
        (receipt_attempt / "case-custody/01-terminal.json").read_bytes()
    )
    assert receipt_result["empirical_gate"] == "error"
    assert receipt_result["operation_counts"]["dspx_generate_calls"] == 0
    assert receipt_terminal["reason"] == "receipt_preparation_failed_before_effect"
    assert receipt_terminal["external_effect_possible"] is False

    request_root = _private(tmp_path / "request-state")
    with (
        patch.object(
            BoundContractCase,
            "materialized_request",
            side_effect=SemanticV11Error("request materialization failed"),
        ),
        pytest.raises(SemanticV11Error, match="request materialization failed"),
    ):
        run_corpus(
            repo_root=REPO,
            state_root=request_root,
            owner_source_root=OWNER_ROOT,
            authority=_authority(900043),
        )
    request_attempt = (
        request_root / "oracle-semantic-analysis-evaluations/AK-900043/v11/attempt"
    )
    request_result = json.loads(
        (request_attempt / "evaluation-result.json").read_bytes()
    )
    assert request_result["empirical_gate"] == "error"
    assert request_result["operation_counts"]["reached_requests"] == 0
    assert request_result["pre_effect_setup_terminal_sha256"] is not None

    with _owner_types() as (event_type, receipt_type, owner_lm_type, _):
        effect_root = _private(tmp_path / "effect-state")

        def fail_after_effect(prepared: Any, *, lm: Any) -> None:
            del lm
            for event in (
                event_type(kind="wrapper_request_accepted"),
                event_type(kind="transport_gate_entered", gate_ordinal=1),
                event_type(kind="transport_effect_pending", gate_ordinal=1),
                event_type(kind="transport_entered", gate_ordinal=1),
            ):
                _sink(prepared, event)
            raise RuntimeError("fake post-effect failure")

        with (
            patch(
                "dspx.services.program_oracle_semantic_evaluation_v11.execute_case",
                side_effect=fail_after_effect,
            ),
            pytest.raises(RuntimeError, match="fake post-effect failure"),
        ):
            run_corpus(
                repo_root=REPO,
                state_root=effect_root,
                owner_source_root=OWNER_ROOT,
                authority=_authority(900044),
            )
        effect_attempt = (
            effect_root / "oracle-semantic-analysis-evaluations/AK-900044/v11/attempt"
        )
        effect_terminal = json.loads(
            (effect_attempt / "case-custody/01-terminal.json").read_bytes()
        )
        effect_result = json.loads(
            (effect_attempt / "evaluation-result.json").read_bytes()
        )
        assert effect_terminal["external_effect_possible"] is True
        assert effect_terminal["reason"] != "receipt_preparation_failed_before_effect"
        assert effect_result["empirical_gate"] == "effect_indeterminate"
        assert effect_result["operation_counts"]["dspx_generate_calls"] == 1

        owner = verify_exact_owner(OWNER_ROOT, event_type, receipt_type, owner_lm_type)
        with patch(
            "dspx.services.program_oracle_semantic_verification_v11._git_identity",
            return_value=("1" * 40, "2" * 40),
        ):
            _, receipt_verification = verify_retained_evaluation(
                repo_root=REPO,
                state_root=receipt_root,
                live_task_id=900042,
                artifact=owner.artifact,
            )
            _, request_verification = verify_retained_evaluation(
                repo_root=REPO,
                state_root=request_root,
                live_task_id=900043,
                artifact=owner.artifact,
            )
            _, effect_verification = verify_retained_evaluation(
                repo_root=REPO,
                state_root=effect_root,
                live_task_id=900044,
                artifact=owner.artifact,
            )
            reserved_path = receipt_attempt / "case-custody/01-reserved.json"
            retained_result_path = receipt_attempt / "evaluation-result.json"
            forged_reserved = json.loads(reserved_path.read_bytes())
            forged_reserved["logical_request_id"] = "a" * 64
            forged_reserved["reservation_sha256"] = "b" * 64
            reserved_path.write_bytes(canonical(forged_reserved))
            forged_result = json.loads(retained_result_path.read_bytes())
            forged_result["cases"][0]["reservation_sha256"] = "b" * 64
            retained_result_path.write_bytes(canonical(forged_result))
            with pytest.raises(SemanticV11Error, match="pre-effect case derivation"):
                verify_retained_evaluation(
                    repo_root=REPO,
                    state_root=receipt_root,
                    live_task_id=900042,
                    artifact=owner.artifact,
                )
    assert receipt_verification["empirical_gate"] == "error"
    assert request_verification["empirical_gate"] == "error"
    assert effect_verification["empirical_gate"] == "effect_indeterminate"


def test_no_ak_database_or_live_state_is_touched_by_candidate_manifest(tmp_path):
    before = list(tmp_path.iterdir())
    candidate_manifest(REPO)
    assert list(tmp_path.iterdir()) == before
    assert load_case_custody  # imported state reader is not invoked by the manifest
