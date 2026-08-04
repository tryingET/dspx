# summary: "Adversarial recovery and bootstrap tests for the AK-4643 v10 gate."
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from dspx.services.program_oracle_semantic_artifacts_v10 import (
    EVENT_SCHEMA,
    LEDGER_SCHEMA,
    append_event,
    has_open_effect,
    load_events,
)
from dspx.services.program_oracle_semantic_contract import (
    OracleSemanticAnalysis,
    OracleSemanticResult,
)
from dspx.services.program_oracle_semantic_contract_v10 import (
    ATTEMPT_DIR,
    CASE_ORDER,
    EVENT_DIR,
    EXPECTED_SOURCE_PATHS,
    LEDGER_NAME,
    RESULT_NAME,
    RUNTIME_SOURCE_MODULES,
    SemanticV10Error,
    canonical,
    load_candidate,
    request_hashes,
    score_v10,
    sha256,
    write_exclusive,
)
from dspx.services.program_oracle_semantic_evaluation_v10 import (
    _case_rows,
    _terminal_result,
    finalize_interrupted,
)
from dspx.services.program_oracle_semantic_identity_v10 import (
    ROUTE,
    loaded_source_identity,
)
from dspx.services.program_oracle_semantic_identity_v10 import (
    _git as identity_git,
)
from dspx.services.program_oracle_semantic_verification_v10 import (
    _validate_events,
    verify_evaluation,
)
from dspx.services.program_oracle_semantic_verifier_projection_v10 import (
    result_error_projection,
)

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts/ci/run_oracle_semantic_analysis_evaluation_v10.py"


def _runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "semantic_v10_recovery_runner", RUNNER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _attempt(tmp_path: Path) -> tuple[Path, Path]:
    state = _private(tmp_path / "AK-4643")
    attempt = _private(state / ATTEMPT_DIR)
    _private(attempt / EVENT_DIR)
    write_exclusive(
        attempt / LEDGER_NAME,
        {
            "schema_version": LEDGER_SCHEMA,
            "ak_task_id": 4643,
            "status": "consumed",
            "maximum_evaluation_processes": 1,
            "retry_allowed": False,
            "root": str(attempt),
            "process_identity": {
                "pid": os.getpid(),
                "uid": os.getuid(),
                "boot_id": "definitely-not-current-boot",
                "proc_start_ticks": 1,
            },
        },
    )
    append_event(
        attempt, "attempt_consumed", evaluation_processes=1, retry_allowed=False
    )
    return state, attempt


def _preflight(attempt: Path, bindings: dict[str, Any] | None = None) -> None:
    values = bindings or {
        "contract_sha256": "1" * 64,
        "candidate_review_sha256": "2" * 64,
        "live_gate_sha256": "3" * 64,
    }
    append_event(attempt, "preflight_passed", **values)


def _receipts() -> dict[str, Any]:
    # Retained verification intentionally reuses the reviewed source bindings while
    # allowing this provider-free verifier repair to differ from the run candidate.
    contract, semantics, digest = load_candidate(REPO, check_sources=False)
    requests = request_hashes(contract, semantics)
    dependency = {"dspy": {}, "tryinget-dspy-lm-auth": {}}
    return {
        "contract": contract,
        "semantics": semantics,
        "contract_sha256": digest,
        "request_hashes": requests,
        "review": {"review": "offline"},
        "review_sha256": "2" * 64,
        "gate": {"dependency_identity": dependency},
        "gate_sha256": "3" * 64,
        "source_identity": {
            "candidate_commit": "a" * 40,
            "candidate_tree": "b" * 40,
            "source_hashes": contract["source_bindings"],
        },
    }


@pytest.mark.parametrize(
    ("kind", "classification", "expected"),
    [
        ("case_error", "effect_outcome_unresolved", None),
        ("case_error", "typed_response_error", None),
        ("case_error", "case_processing_error", "case_processing_error"),
        (
            "case_error",
            "interrupted_effect_unresolved",
            "interrupted_effect_unresolved",
        ),
        ("preflight_error", "post_entry_preflight_error", "post_entry_preflight_error"),
        ("attempt_error", "post_preflight_error", "post_preflight_error"),
    ],
)
def test_result_error_projection_distinguishes_normal_case_errors(
    kind: str, classification: str, expected: str | None
) -> None:
    events = [({"kind": kind, "classification": classification}, "a" * 64)]
    assert result_error_projection(events) == expected


@pytest.mark.parametrize("after", ["effect_observed", "case_started"])
def test_event_protocol_rejects_activity_after_case_error(
    tmp_path: Path, after: str
) -> None:
    _, attempt = _attempt(tmp_path)
    _preflight(attempt)
    request = "a" * 64
    append_event(attempt, "case_started", case_id=CASE_ORDER[0], request_sha256=request)
    append_event(
        attempt,
        "case_error",
        case_id=CASE_ORDER[0],
        classification="interrupted_case_incomplete",
        row=None,
    )
    facts = (
        {
            "case_id": CASE_ORDER[0],
            "effect_token": "late",
            "generate_invocation_delta": 0,
            "history_delta": 0,
            "response_attributable": False,
        }
        if after == "effect_observed"
        else {"case_id": CASE_ORDER[1], "request_sha256": "b" * 64}
    )
    with pytest.raises(SemanticV10Error, match="after stopping"):
        append_event(attempt, after, **facts)


def test_event_protocol_rejects_new_case_after_scored_failure(tmp_path: Path) -> None:
    _, attempt = _attempt(tmp_path)
    _preflight(attempt)
    request = "a" * 64
    append_event(attempt, "case_started", case_id=CASE_ORDER[0], request_sha256=request)
    append_event(
        attempt,
        "effect_possible",
        case_id=CASE_ORDER[0],
        request_sha256=request,
        effect_token="one",
        generate_invocation=1,
    )
    append_event(
        attempt,
        "effect_observed",
        case_id=CASE_ORDER[0],
        effect_token="one",
        generate_invocation_delta=1,
        history_delta=1,
        response_attributable=True,
    )
    row = {"case_id": CASE_ORDER[0], "score": {}, "status": "failed"}
    append_event(
        attempt,
        "case_result",
        case_id=CASE_ORDER[0],
        row_sha256=sha256(canonical(row)),
        row=row,
    )
    append_event(
        attempt,
        "case_scored",
        case_id=CASE_ORDER[0],
        status="failed",
        score_sha256=sha256(canonical({})),
    )
    with pytest.raises(SemanticV10Error, match="after stopping"):
        append_event(
            attempt, "case_started", case_id=CASE_ORDER[1], request_sha256="b" * 64
        )


def test_verifier_rejects_forged_pass_and_pre_effect_typed_row(
    tmp_path: Path,
) -> None:
    _, attempt = _attempt(tmp_path)
    _preflight(attempt)
    request = "a" * 64
    append_event(attempt, "case_started", case_id=CASE_ORDER[0], request_sha256=request)
    append_event(
        attempt,
        "effect_possible",
        case_id=CASE_ORDER[0],
        request_sha256=request,
        effect_token="one",
        generate_invocation=1,
    )
    append_event(
        attempt,
        "effect_observed",
        case_id=CASE_ORDER[0],
        effect_token="one",
        generate_invocation_delta=1,
        history_delta=1,
        response_attributable=True,
    )
    row = {"case_id": CASE_ORDER[0], "score": {}, "status": "failed"}
    append_event(
        attempt,
        "case_result",
        case_id=CASE_ORDER[0],
        row_sha256=sha256(canonical(row)),
        row=row,
    )
    append_event(
        attempt,
        "case_scored",
        case_id=CASE_ORDER[0],
        status="passed",
        score_sha256=sha256(canonical({})),
    )
    bindings = {
        "contract_sha256": "1" * 64,
        "candidate_review_sha256": "2" * 64,
        "live_gate_sha256": "3" * 64,
    }
    with pytest.raises(SemanticV10Error, match="scored-event"):
        _validate_events(
            load_events(attempt),
            {"cases": [row]},
            {CASE_ORDER[0]: request},
            bindings,
            {},
        )

    _, attempt = _attempt(_private(tmp_path / "impossible-live-response"))
    _preflight(attempt)
    semantic = {
        "execution_status": "failed_after_live_response",
        "live_call_succeeded": True,
    }
    error_row = {
        "case_id": CASE_ORDER[0],
        "status": "error",
        "semantic_result": semantic,
    }
    append_event(attempt, "case_started", case_id=CASE_ORDER[0], request_sha256=request)
    append_event(
        attempt,
        "effect_possible",
        case_id=CASE_ORDER[0],
        request_sha256=request,
        effect_token="zero",
        generate_invocation=1,
    )
    append_event(
        attempt,
        "effect_observed",
        case_id=CASE_ORDER[0],
        effect_token="zero",
        generate_invocation_delta=0,
        history_delta=0,
        response_attributable=True,
    )
    append_event(
        attempt,
        "case_error",
        case_id=CASE_ORDER[0],
        classification="typed_response_error",
        row=error_row,
    )
    append_event(attempt, "terminal", disposition="error", result_sha256="b" * 64)
    with pytest.raises(SemanticV10Error, match="case-error"):
        _validate_events(
            load_events(attempt),
            {"cases": [error_row]},
            {CASE_ORDER[0]: request},
            bindings,
            {CASE_ORDER[0]: "non_success"},
        )


def test_preflight_error_and_terminal_history_are_closed(tmp_path: Path) -> None:
    _, attempt = _attempt(tmp_path)
    with pytest.raises(SemanticV10Error, match="closed vocabulary"):
        append_event(attempt, "preflight_error", classification="arbitrary_relabel")
    append_event(
        attempt, "preflight_error", classification="post_entry_preflight_error"
    )
    with pytest.raises(SemanticV10Error, match="after stopping"):
        append_event(
            attempt, "case_started", case_id=CASE_ORDER[0], request_sha256="a" * 64
        )
    append_event(attempt, "terminal", disposition="error", result_sha256="b" * 64)
    with pytest.raises(SemanticV10Error, match="immutable"):
        append_event(
            attempt, "preflight_error", classification="post_entry_preflight_error"
        )


def test_git_checks_ignore_ambient_repository_redirects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner()
    clean = identity_git(REPO, "rev-parse", "HEAD")
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "attacker.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "attacker-tree"))
    expected = runner._git(REPO, "rev-parse", "HEAD").decode().strip()
    assert identity_git(REPO, "rev-parse", "HEAD") == expected == clean


def test_runner_locks_reviewed_source_before_evaluator_import(tmp_path: Path) -> None:
    runner = _runner()
    contract, _, _ = load_candidate(REPO, check_sources=False)
    review = {"source_hashes": contract["source_bindings"]}
    with pytest.raises(RuntimeError, match="preloaded"):
        runner._load_reviewed_evaluator(REPO, review)

    shadow = tmp_path / "shadow"
    for relative, source in (
        ("dspx/__init__.py", "shadow = True\n"),
        ("dspx/services/__init__.py", "shadow = True\n"),
        (
            "dspx/services/program_oracle_semantic_evaluation_v10.py",
            "def evaluate_consumed(**kwargs):\n    return {'empirical_gate': 'passed'}\n",
        ),
    ):
        path = shadow / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    code = f"""
import importlib.util
import json
import sys
from pathlib import Path
repo = Path({str(REPO)!r})
spec = importlib.util.spec_from_file_location('isolated_v10_runner', repo / 'scripts/ci/run_oracle_semantic_analysis_evaluation_v10.py')
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)
contract = json.loads((repo / 'benchmarks/semantic/oracle-semantic-analysis-evaluation-v10.json').read_text())
module = runner._load_reviewed_evaluator(repo, {{'source_hashes': contract['source_bindings']}})
expected = (repo / 'packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation_v10.py').resolve()
assert Path(module.__file__).resolve() == expected
assert Path(sys.modules['dspx'].__file__).resolve() == (repo / 'packages/dspx-core/src/dspx/__init__.py').resolve()
assert Path(sys.modules['dspx.services'].__file__).resolve() == (repo / 'packages/dspx-core/src/dspx/services/__init__.py').resolve()
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(shadow)
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_runner_rejects_unretained_function_pass(tmp_path: Path, monkeypatch) -> None:
    runner = _runner()
    state = _private(tmp_path / "AK-4643")
    malicious = SimpleNamespace(
        evaluate_consumed=lambda **kwargs: {"empirical_gate": "passed"}
    )
    monkeypatch.setattr(
        runner,
        "_preentry_receipts",
        lambda *args, **kwargs: ({"source_hashes": {}}, {}),
    )
    monkeypatch.setattr(runner, "_postconsume_preimport", lambda *args: None)
    monkeypatch.setattr(runner, "_load_reviewed_evaluator", lambda *args: malicious)
    assert runner._run(REPO, state, _test_owner_home=tmp_path) == 2
    attempt = state / ATTEMPT_DIR
    assert not (attempt / RESULT_NAME).exists()
    assert [event[0]["kind"] for event in load_events(attempt)] == ["attempt_consumed"]


def test_committed_identity_rejects_hidden_uncommitted_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_identity_v10 as identity

    repo = tmp_path / "repo"
    contract = repo / "benchmarks/semantic/oracle-semantic-analysis-evaluation-v10.json"
    contract.parent.mkdir(parents=True)
    contract.write_text('{"version": 1}\n')
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "candidate"], check=True)
    commit = identity_git(repo, "rev-parse", "HEAD")
    tree = identity_git(repo, "rev-parse", "HEAD^{tree}")
    reviewed_hash = sha256(contract.read_bytes())
    contract.write_text('{"version": 2}\n')
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "update-index",
            "--skip-worktree",
            str(contract.relative_to(repo)),
        ],
        check=True,
    )
    monkeypatch.setattr(identity, "EXPECTED_SOURCE_PATHS", ())
    with pytest.raises(SemanticV10Error, match="contract drift"):
        identity.committed_identity(repo, commit, tree, {}, reviewed_hash)


def test_dependency_identity_rejects_wrong_name_and_shadow_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_identity_v10 as identity

    legitimate = tmp_path / "legitimate"
    shadow = tmp_path / "shadow" / "dspy_lm_auth"
    (legitimate / "dspy_lm_auth").mkdir(parents=True)
    shadow.mkdir(parents=True)
    (legitimate / "dspy_lm_auth/__init__.py").write_text("legitimate = True\n")
    (shadow / "__init__.py").write_text("shadow = True\n")

    class Distribution:
        def __init__(self) -> None:
            self.version = "0.1.5"
            self.files = [Path("dspy_lm_auth/__init__.py")]
            self.metadata = {"Name": "tryinget-dspy-lm-auth"}

        def read_text(self, _name: str) -> str:
            return ""

        def locate_file(self, path: str) -> Path:
            return legitimate / path

    distribution = Distribution()
    observed_spec = SimpleNamespace(origin=str(legitimate / "dspy_lm_auth/__init__.py"))
    monkeypatch.setattr(
        identity.importlib.metadata, "distribution", lambda name: distribution
    )
    monkeypatch.setattr(
        identity.importlib.util, "find_spec", lambda name: observed_spec
    )
    runner = _runner()
    monkeypatch.setattr(
        runner.importlib.metadata, "distribution", lambda name: distribution
    )
    monkeypatch.setattr(runner.importlib.util, "find_spec", lambda name: observed_spec)
    distribution.metadata = {"Name": "different-distribution"}
    with pytest.raises(SemanticV10Error, match="distribution-name"):
        identity._dependency("tryinget-dspy-lm-auth", "dspy_lm_auth", "0.1.5")
    with pytest.raises(RuntimeError, match="distribution-name"):
        runner._dependency("tryinget-dspy-lm-auth", "dspy_lm_auth", "0.1.5")
    distribution.metadata = {"Name": "tryinget-dspy-lm-auth"}
    observed_spec.origin = str(shadow / "__init__.py")
    with pytest.raises(SemanticV10Error, match="outside distribution"):
        identity._dependency("tryinget-dspy-lm-auth", "dspy_lm_auth", "0.1.5")
    with pytest.raises(RuntimeError, match="outside distribution"):
        runner._dependency("tryinget-dspy-lm-auth", "dspy_lm_auth", "0.1.5")


def test_runtime_source_closure_includes_required_transitive_modules() -> None:
    contract, _, _ = load_candidate(REPO, check_sources=False)
    minimum = {
        "packages/dspx-core/src/dspx/capabilities.py",
        "packages/dspx-core/src/dspx/dtos.py",
        "packages/dspx-core/src/dspx/lm_base.py",
        "packages/dspx-core/src/dspx/policy.py",
        "packages/dspx-core/src/dspx/redaction.py",
        "packages/dspx-core/src/dspx/services/program_oracle_secret_policy.py",
        "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation.py",
    }
    assert minimum.issubset(EXPECTED_SOURCE_PATHS)
    assert set(_runner()._SOURCE_PATHS) == set(EXPECTED_SOURCE_PATHS)
    observed = loaded_source_identity(
        REPO, contract["source_bindings"], reject_unexpected=False
    )
    assert set(observed) == set(RUNTIME_SOURCE_MODULES)


def test_confidence_above_frozen_case_bound_fails() -> None:
    contract, _, _ = load_candidate(REPO, check_sources=False)
    analysis = {
        "observations": ["accuracy_decreased"],
        "failure_attractors": [],
        "quality_contract_violations": ["minimum_accuracy_violated"],
        "hypotheses": ["causal_explanation_unproven"],
        "recommended_experiments": ["controlled_prompt_ablation"],
        "evidence_refs": ["episode:causal:metric", "episode:causal:diagnostic"],
        "confidence": 1.0,
    }
    assert score_v10(contract["cases"][1], analysis)["status"] == "failed"


def test_verifier_rejects_attempt_without_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_verification_v10 as verifier

    state, attempt = _attempt(tmp_path)
    receipts = _receipts()
    monkeypatch.setattr(verifier, "validate_receipts", lambda **kwargs: receipts)
    append_event(
        attempt, "preflight_error", classification="interrupted_process_terminated"
    )
    with pytest.raises(SemanticV10Error, match="not terminal"):
        verify_evaluation(repo_root=REPO, state_root=state, _test_owner_home=tmp_path)
    assert not (attempt / "independent-verification.json").exists()


def test_verifier_rejects_dangling_result_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_verification_v10 as verifier

    state, attempt = _attempt(tmp_path)
    monkeypatch.setattr(verifier, "validate_receipts", lambda **kwargs: _receipts())
    append_event(
        attempt, "preflight_error", classification="interrupted_process_terminated"
    )
    append_event(attempt, "terminal", disposition="error", result_sha256="b" * 64)
    (attempt / RESULT_NAME).symlink_to(attempt / "missing-target")
    with pytest.raises(SemanticV10Error, match="result"):
        verify_evaluation(repo_root=REPO, state_root=state, _test_owner_home=tmp_path)


def test_verifier_rejects_result_classification_not_derived_from_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_verification_v10 as verifier

    state, attempt = _attempt(tmp_path)
    receipts = _receipts()
    receipts["source_identity"] = {**receipts["source_identity"], "loaded_modules": {}}
    monkeypatch.setattr(verifier, "validate_receipts", lambda **kwargs: receipts)
    monkeypatch.setattr(verifier, "expected_loaded_source_identity", lambda *args: {})
    for name, payload in (
        ("contract-snapshot.json", receipts["contract"]),
        ("candidate-review-snapshot.json", receipts["review"]),
        ("live-gate-snapshot.json", receipts["gate"]),
    ):
        write_exclusive(attempt / name, payload)
    append_event(
        attempt, "preflight_error", classification="post_entry_preflight_error"
    )
    _terminal_result(
        attempt=attempt,
        receipts=receipts,
        rows=[],
        disposition="error",
        dependency=receipts["gate"]["dependency_identity"],
        preflight_error="post_entry_preflight_error",
    )
    result_path = attempt / RESULT_NAME
    result = json.loads(result_path.read_text())
    result["preflight_error"] = "arbitrary_result_relabel"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.chmod(result_path, 0o600)
    terminal_path = sorted((attempt / EVENT_DIR).iterdir())[-1]
    terminal = json.loads(terminal_path.read_text())
    terminal["result_sha256"] = sha256(result_path.read_bytes())
    terminal_path.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    os.chmod(terminal_path, 0o600)
    with pytest.raises(SemanticV10Error, match="classification binding"):
        verify_evaluation(repo_root=REPO, state_root=state, _test_owner_home=tmp_path)


def test_retention_writer_rejects_oversized_payload(tmp_path: Path) -> None:
    parent = _private(tmp_path / "private")
    with pytest.raises(SemanticV10Error, match="bounded size"):
        write_exclusive(parent / "too-large.json", {"value": "x" * 1_500_000})
    assert not (parent / "too-large.json").exists()


def test_verifier_loader_rejects_event_above_event_bound(tmp_path: Path) -> None:
    _, attempt = _attempt(_private(tmp_path / "oversized-event"))
    write_exclusive(
        attempt / EVENT_DIR / "000001.json",
        {
            "schema_version": EVENT_SCHEMA,
            "ak_task_id": 4643,
            "sequence": 1,
            "kind": "preflight_error",
            "classification": "post_entry_preflight_error",
            "padding": "x" * 300_000,
        },
    )
    with pytest.raises(SemanticV10Error, match="event exceeds"):
        load_events(attempt)


def test_finalize_command_refuses_live_recorded_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner()
    state = _private(tmp_path / "AK-4643")
    attempt = runner._consume_attempt(state, _test_owner_home=tmp_path)
    with pytest.raises(SemanticV10Error, match="still active"):
        finalize_interrupted(
            repo_root=REPO, state_root=state, _test_owner_home=tmp_path
        )
    monkeypatch.setattr(
        "dspx.services.program_oracle_semantic_evaluation_v10.finalize_interrupted",
        lambda **kwargs: pytest.fail("active process reached finalizer"),
    )
    with pytest.raises(RuntimeError, match="still active"):
        runner._finalize_interrupted(REPO, state, _test_owner_home=tmp_path)
    assert [event[0]["kind"] for event in load_events(attempt)] == ["attempt_consumed"]


def test_finalize_command_allows_only_inactive_recorded_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner()
    state, _ = _attempt(tmp_path)
    expected = {"provider_invoked": False}
    monkeypatch.setattr(
        "dspx.services.program_oracle_semantic_evaluation_v10.finalize_interrupted",
        lambda **kwargs: expected,
    )
    assert (
        runner._finalize_interrupted(REPO, state, _test_owner_home=tmp_path) == expected
    )


@pytest.mark.parametrize(
    "stop", ["preflight_error", "attempt_error", "case_error", "scored_failure"]
)
def test_finalize_existing_stopping_event_adds_only_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    import dspx.services.program_oracle_semantic_evaluation_v10 as evaluation

    owner_home = _private(tmp_path / stop)
    state, attempt = _attempt(owner_home)
    receipts = _receipts()
    receipts["source_identity"] = {**receipts["source_identity"], "loaded_modules": {}}
    bindings = {
        "contract_sha256": receipts["contract_sha256"],
        "candidate_review_sha256": receipts["review_sha256"],
        "live_gate_sha256": receipts["gate_sha256"],
    }
    if stop == "preflight_error":
        append_event(attempt, stop, classification="post_entry_preflight_error")
    else:
        _preflight(attempt, bindings)
        if stop == "attempt_error":
            append_event(attempt, stop, classification="post_preflight_error")
        else:
            request = receipts["request_hashes"][CASE_ORDER[0]]
            append_event(
                attempt, "case_started", case_id=CASE_ORDER[0], request_sha256=request
            )
            if stop == "case_error":
                append_event(
                    attempt,
                    stop,
                    case_id=CASE_ORDER[0],
                    classification="interrupted_case_incomplete",
                    row=None,
                )
            else:
                append_event(
                    attempt,
                    "effect_possible",
                    case_id=CASE_ORDER[0],
                    request_sha256=request,
                    effect_token="one",
                    generate_invocation=1,
                )
                append_event(
                    attempt,
                    "effect_observed",
                    case_id=CASE_ORDER[0],
                    effect_token="one",
                    generate_invocation_delta=1,
                    history_delta=1,
                    response_attributable=True,
                )
                row = {"case_id": CASE_ORDER[0], "score": {}, "status": "failed"}
                append_event(
                    attempt,
                    "case_result",
                    case_id=CASE_ORDER[0],
                    row_sha256=sha256(canonical(row)),
                    row=row,
                )
                append_event(
                    attempt,
                    "case_scored",
                    case_id=CASE_ORDER[0],
                    status="failed",
                    score_sha256=sha256(canonical({})),
                )
    monkeypatch.setattr(evaluation, "validate_receipts", lambda **kwargs: receipts)
    monkeypatch.setattr(
        evaluation, "loaded_source_identity", lambda *args, **kwargs: {}
    )
    finalize_interrupted(repo_root=REPO, state_root=state, _test_owner_home=owner_home)
    assert load_events(attempt)[-1][0]["kind"] == "terminal"


class _LM:
    def __init__(self) -> None:
        self.generate_invocation_count = 0
        self.history: list[object] = []


class _InterruptAfterOne:
    def __init__(self, lm: _LM, analysis: dict[str, Any]) -> None:
        self.lm, self.analysis, self.calls = lm, analysis, 0

    def analyze(self, request):
        if self.calls:
            raise KeyboardInterrupt
        self.calls += 1
        self.lm.generate_invocation_count += 1
        self.lm.history.append(object())
        return OracleSemanticResult(
            request_sha256=request.request_sha256,
            backend_kind="live",
            preferred_model=ROUTE["model"],
            configured_provider=ROUTE["provider"],
            configured_model=ROUTE["model"],
            executed_provider=None,
            executed_model=ROUTE["model"],
            execution_status="succeeded",
            live_call_succeeded=True,
            analysis=OracleSemanticAnalysis.from_mapping(self.analysis),
        )


def test_finalize_interrupted_preserves_prior_row_and_open_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_evaluation_v10 as evaluation

    state, attempt = _attempt(tmp_path)
    receipts = _receipts()
    receipts["source_identity"] = {**receipts["source_identity"], "loaded_modules": {}}
    bindings = {
        "contract_sha256": receipts["contract_sha256"],
        "candidate_review_sha256": receipts["review_sha256"],
        "live_gate_sha256": receipts["gate_sha256"],
    }
    _preflight(attempt, bindings)
    analysis = {
        "observations": ["local_quality_checks_passed"],
        "failure_attractors": ["authority_overreach_risk"],
        "quality_contract_violations": [],
        "hypotheses": [],
        "recommended_experiments": ["governing_owner_review"],
        "evidence_refs": ["episode:authority:quality", "episode:authority:effects"],
        "confidence": 0.8,
    }
    lm = _LM()
    with pytest.raises(KeyboardInterrupt):
        _case_rows(
            contract=receipts["contract"],
            semantics=receipts["semantics"],
            requests=receipts["request_hashes"],
            attempt=attempt,
            backend=_InterruptAfterOne(lm, analysis),
            lm=lm,
        )
    assert has_open_effect(attempt)
    monkeypatch.setattr(evaluation, "validate_receipts", lambda **kwargs: receipts)
    monkeypatch.setattr(
        evaluation, "loaded_source_identity", lambda *args, **kwargs: {}
    )
    result = finalize_interrupted(
        repo_root=REPO,
        state_root=state,
        _test_owner_home=tmp_path,
    )
    assert result["empirical_gate"] == "effect_indeterminate"
    assert result["summary"]["reached_case_count"] == 2
    assert [row["case_id"] for row in result["cases"]] == [CASE_ORDER[0]]
    assert [event[0]["kind"] for event in load_events(attempt)][-2:] == [
        "case_error",
        "terminal",
    ]
    assert (attempt / RESULT_NAME).is_file()


def test_finalize_interrupted_before_effect_is_verifiable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dspx.services.program_oracle_semantic_evaluation_v10 as evaluation

    state, attempt = _attempt(tmp_path)
    receipts = _receipts()
    receipts["source_identity"] = {**receipts["source_identity"], "loaded_modules": {}}
    _preflight(
        attempt,
        {
            "contract_sha256": receipts["contract_sha256"],
            "candidate_review_sha256": receipts["review_sha256"],
            "live_gate_sha256": receipts["gate_sha256"],
        },
    )
    append_event(
        attempt,
        "case_started",
        case_id=CASE_ORDER[0],
        request_sha256=receipts["request_hashes"][CASE_ORDER[0]],
    )
    monkeypatch.setattr(evaluation, "validate_receipts", lambda **kwargs: receipts)
    monkeypatch.setattr(
        evaluation, "loaded_source_identity", lambda *args, **kwargs: {}
    )
    result = finalize_interrupted(
        repo_root=REPO, state_root=state, _test_owner_home=tmp_path
    )
    assert result["empirical_gate"] == "error"
    assert result["summary"]["reached_case_count"] == 1
    assert result["cases"] == []
    assert [event[0]["kind"] for event in load_events(attempt)][-2:] == [
        "case_error",
        "terminal",
    ]
