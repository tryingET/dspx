# summary: "Exercises adversarial safety boundaries for generated programs, CLIs, diagnostics, and sidecar artifacts."
# read_when:
#   - "You are hardening generated-program execution, error redaction, output confinement, or CLI boundary failures."

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import program_service
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_quality_evaluation import evaluate_declared_quality
from dspx.services.program_runtime_episode import _generated_program_module
from dspx.services.program_surfaces import (
    render_direct_run_code,
    render_eval_behavior,
    render_eval_examples,
    render_eval_jury,
    render_eval_promotion,
)

runner = CliRunner()


def test_sidecar_output_guard_calls_declare_artifact_root_policy() -> None:
    services_root = Path("packages/dspx-core/src/dspx/services")
    offenders: list[str] = []
    for path in sorted(services_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Name):
                continue
            if func.id != "prepare_sidecar_output_path":
                continue
            keyword_names = {keyword.arg for keyword in node.keywords}
            if "payload_artifact_root_policy" not in keyword_names:
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == []


def test_generated_program_module_serializes_concurrent_global_imports(
    tmp_path: Path,
) -> None:
    for name, value in (("a", "A"), ("b", "B")):
        candidate = tmp_path / name
        candidate.mkdir()
        (candidate / "program.py").write_text(
            "def io_spec():\n"
            "    for _ in range(10000):\n"
            "        pass\n"
            f"    return {{'outputs': ['{value}']}}\n",
            encoding="utf-8",
        )

    def load(candidate: Path) -> str:
        with _generated_program_module(candidate) as module:
            return str(module.io_spec()["outputs"][0])

    for _ in range(10):
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert list(executor.map(load, [tmp_path / "a", tmp_path / "b"])) == [
                "A",
                "B",
            ]


def test_generated_direct_run_accepts_plain_string_outputs(tmp_path: Path) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "direct_run.py").write_text(
        render_direct_run_code(object()), encoding="utf-8"
    )
    (program_dir / "program.py").write_text(
        """
def io_spec(): return {"inputs": ["q"], "outputs": ["answer"]}
def configure_observability(**kw): return False
def end_observability_run(started, status="FINISHED"): pass
class P:
    def __call__(self, **kw): return "hello"
def build_program(): return P()
""",
        encoding="utf-8",
    )
    inputs = program_dir / "inputs.json"
    inputs.write_text('{"q": "x"}\n', encoding="utf-8")
    outdir = tmp_path / "out"
    env = {
        **os.environ,
        "DSPX_PROVIDER": "stub",
        "MLFLOW_ENABLE": "0",
    }

    result = subprocess.run(
        [
            sys.executable,
            str(program_dir / "direct_run.py"),
            "--inputs",
            str(inputs),
            "--outdir",
            str(outdir),
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads((outdir / "answer").read_text(encoding="utf-8")) == "hello"


def test_generated_direct_run_rejects_output_path_escape(tmp_path: Path) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "direct_run.py").write_text(
        render_direct_run_code(object()), encoding="utf-8"
    )
    (program_dir / "program.py").write_text(
        """
def io_spec(): return {"inputs": ["q"], "outputs": ["../escape.json"]}
def configure_observability(**kw): return False
def end_observability_run(started, status="FINISHED"): pass
class P:
    def __call__(self, **kw): return {"../escape.json": {"ok": True}}
def build_program(): return P()
""",
        encoding="utf-8",
    )
    inputs = program_dir / "inputs.json"
    inputs.write_text('{"q": "x"}\n', encoding="utf-8")
    outdir = tmp_path / "out"
    env = {
        **os.environ,
        "DSPX_PROVIDER": "stub",
        "MLFLOW_ENABLE": "0",
    }

    result = subprocess.run(
        [
            sys.executable,
            str(program_dir / "direct_run.py"),
            "--inputs",
            str(inputs),
            "--outdir",
            str(outdir),
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "unsafe generated output field path" in result.stderr
    assert not (tmp_path / "escape.json").exists()


@pytest.mark.parametrize(
    "field_name",
    ["manifest.json", "nested/behavior_results.json", "direct_run_receipt.json"],
)
def test_generated_direct_run_rejects_protected_output_artifact_names(
    tmp_path: Path, field_name: str
) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "direct_run.py").write_text(
        render_direct_run_code(object()), encoding="utf-8"
    )
    (program_dir / "program.py").write_text(
        f"""
def io_spec(): return {{"inputs": ["q"], "outputs": [{field_name!r}]}}
def configure_observability(**kw): return False
def end_observability_run(started, status="FINISHED"): pass
class P:
    def __call__(self, **kw): return {{{field_name!r}: {{"ok": True}}}}
def build_program(): return P()
""",
        encoding="utf-8",
    )
    inputs = program_dir / "inputs.json"
    inputs.write_text('{"q": "x"}\n', encoding="utf-8")
    outdir = tmp_path / "out"
    env = {
        **os.environ,
        "DSPX_PROVIDER": "stub",
        "MLFLOW_ENABLE": "0",
    }

    result = subprocess.run(
        [
            sys.executable,
            str(program_dir / "direct_run.py"),
            "--inputs",
            str(inputs),
            "--outdir",
            str(outdir),
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "generated output field collides with protected artifact path" in result.stderr
    )
    if field_name != "direct_run_receipt.json":
        assert not (outdir / field_name).exists()
    receipt = json.loads(
        (outdir / "direct_run_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "failed"
    assert receipt["error"]["message"].startswith(
        "generated output field collides with protected artifact path"
    )


def test_generated_direct_run_redacts_secret_failure_diagnostics(
    tmp_path: Path,
) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "direct_run.py").write_text(
        render_direct_run_code(object()), encoding="utf-8"
    )
    secret_message = (
        "provider failed api_key=supersecret-value Authorization: Bearer bearer-secret "
        "https://user:pass@example.test/run?token=url-secret&ok=1"
    )
    (program_dir / "program.py").write_text(
        f"""
def io_spec(): return {{"inputs": ["q"], "outputs": ["answer"]}}
def configure_observability(**kw): return False
def end_observability_run(started, status="FINISHED"): pass
class P:
    def __call__(self, **kw):
        raise RuntimeError({secret_message!r})
def build_program(): return P()
""",
        encoding="utf-8",
    )
    inputs = program_dir / "inputs.json"
    inputs.write_text('{"q": "x"}\n', encoding="utf-8")
    outdir = tmp_path / "out"
    env = {
        **os.environ,
        "DSPX_PROVIDER": "stub",
        "MLFLOW_ENABLE": "0",
    }

    result = subprocess.run(
        [
            sys.executable,
            str(program_dir / "direct_run.py"),
            "--inputs",
            str(inputs),
            "--outdir",
            str(outdir),
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    receipt = json.loads(
        (outdir / "direct_run_receipt.json").read_text(encoding="utf-8")
    )
    combined = result.stderr + json.dumps(receipt, sort_keys=True)
    assert "supersecret-value" not in combined
    assert "bearer-secret" not in combined
    assert "url-secret" not in combined
    assert "user:pass@" not in combined
    assert "api_key=[REDACTED]" in combined
    assert "Bearer [REDACTED]" in combined
    assert "token=[REDACTED]" in combined
    assert "Traceback" not in result.stderr
    assert receipt["status"] == "failed"
    assert receipt["error"]["message"] == result.stderr.strip()


def test_generated_eval_examples_redacts_secret_failure_diagnostics(
    tmp_path: Path,
) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "eval_examples.py").write_text(
        render_eval_examples(object()), encoding="utf-8"
    )
    secret_message = (
        "provider failed api_key=supersecret-value Authorization: Bearer bearer-secret "
        "https://user:pass@example.test/run?token=url-secret&ok=1"
    )
    (program_dir / "program.py").write_text(
        f"""
def io_spec(): return {{"inputs": ["q"], "outputs": ["answer"]}}
def intent_summary(): return {{"name": "secret-eval"}}
def normalize_output(name, expected, observed, pred_trace=None): return expected, observed
class P:
    def __call__(self, **kw):
        raise RuntimeError({secret_message!r})
def build_program(): return P()
""",
        encoding="utf-8",
    )
    (program_dir / "examples.json").write_text(
        '[{"inputs": {"q": "x"}, "outputs": {"answer": "ok"}}]\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "eval_examples.py"],
        cwd=program_dir,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((program_dir / "behavior_results.json").read_text())
    combined = json.dumps(payload, sort_keys=True)
    assert "supersecret-value" not in combined
    assert "bearer-secret" not in combined
    assert "url-secret" not in combined
    assert "user:pass@" not in combined
    assert "api_key=[REDACTED]" in combined
    assert "Bearer [REDACTED]" in combined
    assert "token=[REDACTED]" in combined
    assert payload["examples"][0]["status"] == "error"


def test_generated_eval_jury_redacts_contract_diagnostics(
    tmp_path: Path,
) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "eval_jury.py").write_text(render_eval_jury(), encoding="utf-8")
    secret_message = (
        "api_key=supersecret-value Authorization: Bearer bearer-secret "
        "https://user:pass@example.test/run?token=url-secret&ok=1"
    )
    (program_dir / "jury.json").write_text(
        json.dumps({"schema_version": "program-jury-v1"}), encoding="utf-8"
    )
    (program_dir / "jury_selection.json").write_text(
        json.dumps(
            {
                "schema_version": "program-jury-selection-v1",
                "selected_jurors": secret_message,
                "authority": "selection_contract_only_non_authoritative",
            }
        ),
        encoding="utf-8",
    )
    (program_dir / "jury_rubric.json").write_text(
        json.dumps(
            {
                "schema_version": "program-jury-rubric-v1",
                "juror_rubrics": [],
                "authority": "rubric_contract_only_non_authoritative",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "eval_jury.py"],
        cwd=program_dir,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "supersecret-value" not in result.stderr
    assert "bearer-secret" not in result.stderr
    assert "url-secret" not in result.stderr
    assert "user:pass@" not in result.stderr
    assert "api_key=[REDACTED]" in result.stderr
    assert "Bearer [REDACTED]" in result.stderr
    assert "token=[REDACTED]" in result.stderr
    assert "Traceback" not in result.stderr


def test_generated_eval_promotion_redacts_contract_diagnostics(
    tmp_path: Path,
) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "eval_promotion.py").write_text(
        render_eval_promotion(), encoding="utf-8"
    )
    secret_message = (
        "api_key=supersecret-value Authorization: Bearer bearer-secret "
        "https://user:pass@example.test/run?token=url-secret&ok=1"
    )
    base_review = {
        "schema_version": "program-promotion-review-v1",
        "promotion_state": "not_promoted",
        "decision": {"status": "pending"},
        "adjudicator": "local",
        "external_authority": {"opaque_ref": "none"},
        "blocking_conditions": secret_message,
        "non_authority": {
            "automatic_promotion": False,
            "ranking_pruning_promotion": False,
            "external_authority_export": False,
        },
    }
    request = {
        "schema_version": "program-promotion-adjudication-request-v1",
        "adjudicator": "local",
        "external_authority": {"opaque_ref": "none"},
        "decision_record_template": {
            "schema_version": "program-promotion-decision-v1",
            "status": "pending",
            "decided_by": None,
        },
        "authority": "adjudication_request_only_non_authoritative",
        "missing_required_evidence": [],
        "status": "not_ready_blocked",
    }
    (program_dir / "promotion_review.json").write_text(
        json.dumps(base_review), encoding="utf-8"
    )
    (program_dir / "promotion_adjudication_request.json").write_text(
        json.dumps(request), encoding="utf-8"
    )
    (program_dir / "promotion_decision_template.json").write_text(
        json.dumps(request["decision_record_template"]), encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, "eval_promotion.py"],
        cwd=program_dir,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "supersecret-value" not in result.stderr
    assert "bearer-secret" not in result.stderr
    assert "url-secret" not in result.stderr
    assert "user:pass@" not in result.stderr
    assert "api_key=[REDACTED]" in result.stderr
    assert "Bearer [REDACTED]" in result.stderr
    assert "token=[REDACTED]" in result.stderr
    assert "Traceback" not in result.stderr


def test_generated_eval_behavior_redacts_child_diagnostics(
    tmp_path: Path,
) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    intent = SimpleNamespace(
        examples=[{"inputs": {"q": "x"}, "outputs": {"answer": "ok"}}],
        examples_path=None,
        dataset=None,
        datasets=None,
    )
    (program_dir / "eval_behavior.py").write_text(
        render_eval_behavior(intent), encoding="utf-8"
    )
    (program_dir / "program.py").write_text(
        "def configure_observability(**kw): return False\n"
        "def end_observability_run(started, status='FINISHED'): pass\n",
        encoding="utf-8",
    )
    secret_message = (
        "api_key=supersecret-value Authorization: Bearer bearer-secret "
        "https://user:pass@example.test/run?token=url-secret&ok=1"
    )
    (program_dir / "eval_examples.py").write_text(
        "import sys\n"
        f"print({secret_message!r})\n"
        f"print({secret_message!r}, file=sys.stderr)\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "eval_behavior.py"],
        cwd=program_dir,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((program_dir / "behavior_episode.json").read_text())
    combined = json.dumps(payload, sort_keys=True)
    assert "supersecret-value" not in combined
    assert "bearer-secret" not in combined
    assert "url-secret" not in combined
    assert "user:pass@" not in combined
    assert "api_key=[REDACTED]" in combined
    assert "Bearer [REDACTED]" in combined
    assert "token=[REDACTED]" in combined
    source = payload["sources"][0]
    assert source["status"] == "failed"


def test_generated_eval_behavior_rejects_quality_summary_record_drift(
    tmp_path: Path,
) -> None:
    program_dir = tmp_path / "program-quality-drift"
    program_dir.mkdir()
    criterion = {
        "id": "declared",
        "output_field": "answer",
        "evaluator": "concept_coverage",
        "required_concept_groups": [["safe"]],
        "forbidden_concepts": [],
        "min_score": 1.0,
    }
    intent = SimpleNamespace(
        examples=[{"inputs": {"q": "x"}, "outputs": {"answer": "ok"}}],
        examples_path=None,
        dataset=None,
        datasets=None,
        quality_criteria=[criterion],
    )
    (program_dir / "eval_behavior.py").write_text(
        render_eval_behavior(intent), encoding="utf-8"
    )
    (program_dir / "program.py").write_text(
        "def configure_observability(**kw): return False\n"
        "def end_observability_run(started, status='FINISHED'): pass\n",
        encoding="utf-8",
    )
    fake_passed_record = {
        "schema_version": "program-quality-evaluation-v1",
        "status": "passed",
        "criteria_total": 1,
        "criteria_passed": 1,
        "criteria_failed": 0,
        "criteria": [],
        "quality_approved": False,
    }
    payload = {
        "intent": {"quality_criteria": [criterion]},
        "examples": [
            {"observed_outputs": {}, "quality_evaluation": fake_passed_record}
        ],
        "summary": {"status": "passed", "total": 1},
        "quality_evaluation": {
            "status": "passed",
            "criteria_declared": True,
            "evaluations_total": 1,
            "evaluations_passed": 1,
            "evaluations_failed": 0,
            "quality_approved": False,
        },
    }
    (program_dir / "eval_examples.py").write_text(
        "import json\nfrom pathlib import Path\n"
        f"Path('behavior_results.json').write_text(json.dumps({payload!r}))\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "eval_behavior.py"],
        cwd=program_dir,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "quality drifts from observed outputs" in result.stderr
    assert not (program_dir / "behavior_episode.json").exists()


def test_generated_eval_behavior_rejects_child_criteria_substitution(
    tmp_path: Path,
) -> None:
    root = tmp_path / "criteria-substitution"
    root.mkdir()
    strict = {
        "id": "strict",
        "output_field": "answer",
        "evaluator": "concept_coverage",
        "required_concept_groups": [["must-appear"]],
        "forbidden_concepts": [],
        "min_score": 1.0,
    }
    weak = {**strict, "id": "weak", "required_concept_groups": [["safe"]]}
    intent = SimpleNamespace(
        examples=[{"inputs": {"q": "x"}, "outputs": {"answer": "x"}}],
        examples_path=None,
        dataset=None,
        datasets=None,
        quality_criteria=[strict],
    )
    (root / "eval_behavior.py").write_text(render_eval_behavior(intent))
    (root / "program.py").write_text(
        "def configure_observability(**kw): return False\n"
        "def end_observability_run(started, status='FINISHED'): pass\n"
    )
    record_quality = evaluate_declared_quality([weak], {"answer": "safe"})
    payload = {
        "intent": {"quality_criteria": [weak]},
        "examples": [
            {
                "observed_outputs": {"answer": "safe"},
                "quality_evaluation": record_quality,
            }
        ],
        "summary": {"status": "passed", "total": 1},
        "quality_evaluation": {
            "status": "passed",
            "criteria_declared": True,
            "evaluations_total": 1,
            "evaluations_passed": 1,
            "evaluations_failed": 0,
            "quality_approved": False,
        },
    }
    (root / "eval_examples.py").write_text(
        "import json\nfrom pathlib import Path\n"
        f"Path('behavior_results.json').write_text(json.dumps({payload!r}))\n"
    )

    result = subprocess.run(
        [sys.executable, "eval_behavior.py"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "criteria drift from candidate intent" in result.stderr
    assert not (root / "behavior_episode.json").exists()


@pytest.mark.parametrize(
    ("flag", "value", "message"),
    [
        ("--parallel", "0", "--parallel must be >= 1"),
        ("--timeout-seconds", "0", "--timeout-seconds must be > 0"),
        ("--retries", "-1", "--retries must be >= 0"),
    ],
)
def test_generated_direct_batch_rejects_invalid_limits(
    tmp_path: Path, flag: str, value: str, message: str
) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "direct_run.py").write_text(
        render_direct_run_code(object()), encoding="utf-8"
    )
    inputs_root = tmp_path / "inputs"
    inputs_root.mkdir()
    (inputs_root / "case.json").write_text('{"q": "x"}\n', encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(program_dir / "direct_run.py"),
            "--inputs-root",
            str(inputs_root),
            "--out-root",
            str(tmp_path / "out"),
            flag,
            value,
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert message in result.stderr


def test_generated_direct_batch_records_timeout_without_crashing(
    tmp_path: Path,
) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "direct_run.py").write_text(
        render_direct_run_code(object()), encoding="utf-8"
    )
    (program_dir / "program.py").write_text(
        """
import time

def io_spec(): return {"inputs": ["q"], "outputs": ["answer"]}
def configure_observability(**kw): return False
def end_observability_run(started, status="FINISHED"): pass
class P:
    def __call__(self, **kw):
        time.sleep(3)
        return {"answer": "late"}
def build_program(): return P()
""",
        encoding="utf-8",
    )
    inputs_root = tmp_path / "inputs"
    inputs_root.mkdir()
    (inputs_root / "case.json").write_text('{"q": "x"}\n', encoding="utf-8")
    out_root = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            str(program_dir / "direct_run.py"),
            "--inputs-root",
            str(inputs_root),
            "--out-root",
            str(out_root),
            "--timeout-seconds",
            "1",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    summary = json.loads((out_root / "direct_batch_receipt.json").read_text())
    assert summary["status"] == "failed"
    assert summary["failed"] == 1
    attempt = summary["results"][0]["attempts"][0]
    assert attempt["timed_out"] is True
    assert attempt["error_type"] == "TimeoutExpired"


def test_generated_direct_batch_records_internal_worker_exception(
    tmp_path: Path,
) -> None:
    namespace: dict[str, Any] = {"__file__": str(tmp_path / "direct_run.py")}
    exec(render_direct_run_code(object()), namespace, namespace)

    def boom(*args: object, **kwargs: object) -> dict[str, object]:
        raise ValueError("bad child receipt")

    namespace["_run_child"] = boom
    inputs_root = tmp_path / "inputs"
    inputs_root.mkdir()
    (inputs_root / "case.json").write_text('{"q": "x"}\n', encoding="utf-8")
    out_root = tmp_path / "out"

    summary = namespace["_batch_run"](inputs_root, out_root, 1, 1, 0, None)

    assert summary["status"] == "failed"
    assert summary["failed"] == 1
    result = summary["results"][0]
    assert result["target"] == "case"
    assert result["error_type"] == "ValueError"
    assert result["error"] == "bad child receipt"
    assert (
        json.loads((out_root / "direct_batch_receipt.json").read_text())["failed"] == 1
    )


def test_program_harness_runner_redacts_secret_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_stdout = "stdout api_key=supersecret-value"
    secret_stderr = (
        "stderr Authorization: Bearer bearer-secret "
        "https://user:pass@example.test/path?token=url-secret"
    )

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[sys.executable, "eval_smoke.py"],
            returncode=0,
            stdout=secret_stdout,
            stderr=secret_stderr,
        )

    monkeypatch.setattr(program_service.subprocess, "run", fake_run)

    result = program_service._run_eval_smoke(tmp_path)
    combined = json.dumps(result, sort_keys=True)

    assert "supersecret-value" not in combined
    assert "bearer-secret" not in combined
    assert "url-secret" not in combined
    assert "user:pass@" not in combined
    assert "api_key=[REDACTED]" in combined
    assert "Bearer [REDACTED]" in combined
    assert "token=[REDACTED]" in combined


def test_program_harness_runner_redacts_secret_failure_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_stderr = (
        "Traceback provider api_key=supersecret-value "
        "Authorization: Bearer bearer-secret "
        "https://user:pass@example.test/path?token=url-secret"
    )

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[sys.executable, "eval_smoke.py"],
            returncode=1,
            stdout="",
            stderr=secret_stderr,
        )

    monkeypatch.setattr(program_service.subprocess, "run", fake_run)

    with pytest.raises(ValueError) as excinfo:
        program_service._run_eval_smoke(tmp_path)

    message = str(excinfo.value)
    assert "supersecret-value" not in message
    assert "bearer-secret" not in message
    assert "url-secret" not in message
    assert "user:pass@" not in message
    assert "api_key=[REDACTED]" in message
    assert "Bearer [REDACTED]" in message
    assert "token=[REDACTED]" in message


def test_program_gen_failure_cleans_partial_outdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    root = tmp_path / "program"
    original = program_service._run_eval_smoke
    monkeypatch.setattr(
        program_service,
        "_run_eval_smoke",
        lambda _root: (_ for _ in ()).throw(RuntimeError("simulated smoke failure")),
    )

    with pytest.raises(RuntimeError, match="simulated smoke failure"):
        program_service.materialize_program_from_intent(
            ProgramIntent(name="X", objective="x", inputs=["q"], outputs=["a"]),
            outdir=root,
        )

    assert not root.exists()

    monkeypatch.setattr(program_service, "_run_eval_smoke", original)
    artifact = program_service.materialize_program_from_intent(
        ProgramIntent(name="X", objective="x", inputs=["q"], outputs=["a"]),
        outdir=root,
    )
    assert Path(artifact.root_path, "manifest.json").exists()


def test_program_gen_compile_failure_removes_new_empty_outdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "program"
    monkeypatch.setattr(
        program_service, "render_program_code", lambda _intent: "def broken(:\n"
    )

    with pytest.raises(SyntaxError):
        program_service.materialize_program_from_intent(
            ProgramIntent(name="X", objective="x", inputs=["q"], outputs=["a"]),
            outdir=root,
        )

    assert not root.exists()


def test_program_gen_rejects_existing_empty_outdir_without_partial_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "program"
    root.mkdir()

    def should_not_run(_root: Path) -> dict[str, object]:
        raise AssertionError("materialization should not start for existing outdir")

    monkeypatch.setattr(program_service, "_run_eval_smoke", should_not_run)

    with pytest.raises(ValueError, match="program-gen outdir already exists"):
        program_service.materialize_program_from_intent(
            ProgramIntent(name="X", objective="x", inputs=["q"], outputs=["a"]),
            outdir=root,
        )

    assert root.exists()
    assert list(root.iterdir()) == []


def test_cli_boundary_failures_are_concise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.delenv("DSPX_CONFIG", raising=False)

    provider_result = runner.invoke(
        app, ["providers", "resolve", "--provider", "no-such", "--json"]
    )
    assert provider_result.exit_code == 2
    assert "unknown provider: no-such" in provider_result.output
    assert "Traceback" not in provider_result.output

    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "info": {"title": "t", "version": "1"},
                "paths": {
                    "/x": {
                        "get": {
                            "operationId": "getX",
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    missing_op = runner.invoke(
        app,
        ["tools", "openapi", "describe", "--spec", str(spec), "--op", "missing"],
    )
    assert missing_op.exit_code == 2
    assert "unknown OpenAPI operationId: missing" in missing_op.output
    assert "getX" in missing_op.output
    assert "Traceback" not in missing_op.output

    missing_spec = runner.invoke(
        app,
        ["tools", "openapi", "describe", "--spec", "/no/such", "--op", "nope"],
    )
    assert missing_spec.exit_code == 2
    assert "failed to load OpenAPI spec /no/such" in missing_spec.output
    assert "Traceback" not in missing_spec.output

    bad_config_dir = tmp_path / "bad-config"
    bad_config_dir.mkdir()
    (bad_config_dir / "config.toml").write_text("[provider\n", encoding="utf-8")
    with runner.isolated_filesystem(temp_dir=bad_config_dir):
        bad_config = runner.invoke(app, ["providers", "list", "--json"])
    assert bad_config.exit_code == 2
    assert "Failed to parse DSPx config TOML" in bad_config.output
    assert "Traceback" not in bad_config.output

    capabilities_result = runner.invoke(
        app, ["providers", "capabilities", "--provider", "no-such", "--json"]
    )
    assert capabilities_result.exit_code == 2
    assert "unknown provider: no-such" in capabilities_result.output
    assert "Traceback" not in capabilities_result.output

    missing_key = runner.invoke(
        app,
        [
            "--openrouter-api-key-file",
            str(tmp_path / "missing.key"),
            "providers",
            "health",
            "--provider",
            "openrouter",
            "--json",
        ],
    )
    assert missing_key.exit_code == 2
    assert "failed to read OpenRouter API key file" in missing_key.output
    assert "Traceback" not in missing_key.output

    invalid_key = tmp_path / "invalid.key"
    invalid_key.write_bytes(b"\xff\xfe")
    invalid_key_result = runner.invoke(
        app,
        [
            "--openrouter-api-key-file",
            str(invalid_key),
            "providers",
            "health",
            "--provider",
            "openrouter",
            "--json",
        ],
    )
    assert invalid_key_result.exit_code == 2
    assert "failed to read OpenRouter API key file" in invalid_key_result.output
    assert "Traceback" not in invalid_key_result.output


def test_cli_boundary_errors_redact_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_error = (
        "request failed token=secret-token Authorization: Bearer bearer-secret "
        "https://user:pass@example.test/spec.json?api_key=url-secret&ok=1"
    )

    import dspx.provider_runtime as provider_runtime
    import dspx.tools.openapi as openapi_tools

    def raise_secret_provider(_name: str) -> dict[str, object]:
        raise RuntimeError(secret_error)

    def raise_secret_spec(
        _spec: str, *, allowed_hosts: object = None
    ) -> dict[str, object]:
        raise RuntimeError(secret_error)

    monkeypatch.setattr(provider_runtime, "describe_provider", raise_secret_provider)
    monkeypatch.setattr(openapi_tools, "load_spec", raise_secret_spec)

    provider_result = runner.invoke(
        app, ["providers", "resolve", "--provider", "secret-provider", "--json"]
    )
    assert provider_result.exit_code == 2
    assert "[REDACTED]" in provider_result.output
    assert "secret-token" not in provider_result.output
    assert "bearer-secret" not in provider_result.output
    assert "url-secret" not in provider_result.output
    assert "user:pass" not in provider_result.output
    assert "Traceback" not in provider_result.output

    spec_result = runner.invoke(
        app,
        [
            "tools",
            "openapi",
            "describe",
            "--spec",
            "https://user:pass@example.test/spec.json?api_key=url-secret&ok=1",
            "--op",
            "missing",
        ],
    )
    assert spec_result.exit_code == 2
    assert "[REDACTED]" in spec_result.output
    assert "secret-token" not in spec_result.output
    assert "bearer-secret" not in spec_result.output
    assert "url-secret" not in spec_result.output
    assert "user:pass" not in spec_result.output
    assert "Traceback" not in spec_result.output
