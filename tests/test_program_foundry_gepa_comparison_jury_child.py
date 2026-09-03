# summary: "Tests the fresh -I -B subprocess boundary that runs every task-local foundry comparison jury."

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import dspx.services.program_foundry_gepa_comparison_jury as comparison_jury
import dspx.services.program_foundry_gepa_comparison_jury_child as jury_child
import dspx.services.program_foundry_gepa_comparison_jury_receipt_validation as receipt_validation
from dspx.cli.dspx import app
from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (
    LOCAL_VLLM_ENDPOINT_ENV,
    LOCAL_VLLM_FAMILY,
    XAI_FAMILY,
)
from dspx.services.program_model_jury_provider_runtime import (
    ProgramModelJuryProviderRuntimeBinding,
    validate_model_jury_process_slot,
)
from test_program_foundry_gepa_comparison_jury import _fixture, _model_result, _sha256

CHILD_TIMEOUT = 180
ALLOWED_ENV_KEYS = {
    "HOME",
    "PATH",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "DSPX_CACHE_DIR",
    "DSPX_CACHE_ENABLE",
    "MLFLOW_ENABLE",
    "PYTHONDONTWRITEBYTECODE",
    LOCAL_VLLM_ENDPOINT_ENV,
}


def _owner_modules() -> set[str]:
    return {
        name
        for name in sys.modules
        if name == "dspy_lm_auth" or name.startswith("dspy_lm_auth.")
    }


def _install(monkeypatch: pytest.MonkeyPatch, validated: dict[str, Any]) -> None:
    monkeypatch.setattr(
        comparison_jury,
        "validate_successful_program_foundry_gepa_consumption_receipt",
        lambda path, **kwargs: dict(validated),
    )
    monkeypatch.setattr(
        comparison_jury, "run_task_local_preflight", lambda request, **kwargs: None
    )
    monkeypatch.setattr(
        comparison_jury,
        "build_comparison_model_jury_result",
        lambda *a, **k: pytest.fail("the parent must not run a task-local jury"),
    )


def _execute(receipt: Path, owner_root: Path, provider: str) -> dict[str, Any]:
    return comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider=provider,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
        max_jurors=1,
    )


def _script_argv(tmp_path: Path, body: str, *args: str) -> tuple[str, ...]:
    script = tmp_path / "fake-child.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return (sys.executable, "-I", "-B", str(script), *args)


def _sidecars(receipt: Path) -> dict[str, bool]:
    experiment = receipt.parent
    return {
        "attempt": (experiment / "comparison-jury-attempt.json").exists(),
        "result": (experiment / "comparison-jury-results.json").exists(),
        "receipt": (experiment / "comparison-jury-receipt.json").exists(),
        "journals": (experiment / "provider-outcomes").exists(),
    }


# --- the real child ------------------------------------------------------------


def test_default_child_argv_is_isolated_bytecode_free_module_run() -> None:
    assert comparison_jury._CHILD_ARGV == (
        sys.executable,
        "-I",
        "-B",
        "-m",
        "dspx.services.program_foundry_gepa_comparison_jury_child",
    )
    assert comparison_jury._CHILD_ARGV == jury_child.default_child_argv()


def test_real_child_self_check_starts_fresh_without_owner_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/definitely/ignored/by/-I")
    completed = subprocess.run(
        [*jury_child.default_child_argv(), "--self-check"],
        input=b"",
        capture_output=True,
        env=jury_child.child_environment(XAI_FAMILY),
        timeout=CHILD_TIMEOUT,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert json.loads(completed.stdout) == {
        "isolated": True,
        "dont_write_bytecode": True,
        "owner_modules_at_start": [],
    }


def test_real_child_rejects_garbage_request_silently() -> None:
    completed = subprocess.run(
        list(jury_child.default_child_argv()),
        input=b"not a request",
        capture_output=True,
        env=jury_child.child_environment(None),
        timeout=CHILD_TIMEOUT,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stdout == b""


def test_child_main_refuses_a_non_isolated_interpreter(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert not sys.flags.isolated
    assert jury_child.main([]) == 1
    assert jury_child.main(["--unexpected"]) == 2
    assert capsys.readouterr().out == ""


# --- child-side request execution (in-process, provider build faked) ------------


def test_run_child_request_acquires_slot_and_binds_task_local_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    request = comparison_jury._execution_request(
        provider=XAI_FAMILY.provider_name,
        adjudicator_id="local_foundry_adjudicator",
        adjudicator_kind="local_foundry_adjudicator",
        adjudicator_repo=None,
        max_jurors=1,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
    )
    calls: list[dict[str, Any]] = []

    def build(slot: object, **kwargs: Any) -> dict[str, Any]:
        validate_model_jury_process_slot(slot)  # type: ignore[arg-type]
        calls.append(kwargs)
        return {"status": "executed"}

    monkeypatch.setattr(jury_child, "build_comparison_model_jury_result", build)
    payload = jury_child.child_request_payload(
        request=request,
        validated=validated,
        experiment_root=receipt.parent,
        attempt_sha256="a" * 64,
        input_sha256={Path(validated["comparison_path"]): "b" * 64},
    )
    assert jury_child.run_child_request(json.loads(json.dumps(payload))) == {
        "status": "executed"
    }
    assert len(calls) == 1
    assert calls[0]["provider"] == XAI_FAMILY.provider_name
    assert calls[0]["manifest_path"] == Path(validated["candidate_manifest_path"])
    assert calls[0]["evidence_paths"] == [Path(validated["comparison_path"])]
    assert calls[0]["expected_input_sha256"] == {
        Path(validated["comparison_path"]): "b" * 64
    }
    assert isinstance(
        calls[0]["provider_runtime_binding"], ProgramModelJuryProviderRuntimeBinding
    )
    generic = {**payload, "request": {**request, "provider": "fixture-provider"}}
    with pytest.raises(comparison_jury.ProgramFoundryGepaComparisonJuryError):
        jury_child.run_child_request(generic)
    with pytest.raises(ValueError, match="shape drifted"):
        jury_child._decode_request(
            json.dumps({**payload, "extra": True}).encode("utf-8")
        )


def test_child_environment_is_an_allowlist_with_family_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("PYTHONPATH", "/must/not/leak")
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, "http://localhost:8000/v1")
    monkeypatch.setenv("DSPX_CACHE_DIR", "/tmp/cache")
    vllm_env = jury_child.child_environment(LOCAL_VLLM_FAMILY)
    xai_env = jury_child.child_environment(XAI_FAMILY)
    assert set(vllm_env) <= ALLOWED_ENV_KEYS
    assert vllm_env[LOCAL_VLLM_ENDPOINT_ENV] == "http://localhost:8000/v1"
    assert LOCAL_VLLM_ENDPOINT_ENV not in xai_env
    for env in (vllm_env, xai_env):
        assert env["DSPX_CACHE_ENABLE"] == "0"
        assert env["MLFLOW_ENABLE"] == "0"
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        assert env["DSPX_CACHE_DIR"] == "/tmp/cache"
        assert "OPENAI_API_KEY" not in env and "PYTHONPATH" not in env
    assert jury_child.child_timeout_seconds(3) == 240.0
    assert jury_child.child_timeout_seconds(0) == 120.0


# --- parent-side boundary with a faked child -----------------------------------


def test_parent_runs_task_local_jury_in_child_without_importing_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv(LOCAL_VLLM_ENDPOINT_ENV, "http://localhost:8000/v1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    receipt, validated = _fixture(tmp_path)
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    _install(monkeypatch, validated)
    monkeypatch.setattr(
        receipt_validation,
        "_validate_jury_result",
        lambda *, result_path, **kwargs: (
            json.loads(result_path.read_text(encoding="utf-8")),
            _sha256(result_path),
        ),
    )
    canned = tmp_path / "canned-result.json"
    canned.write_text(json.dumps(_model_result(validated)), encoding="utf-8")
    seen = tmp_path / "seen.json"
    monkeypatch.setattr(
        comparison_jury,
        "_CHILD_ARGV",
        _script_argv(
            tmp_path,
            """
            import json, os, sys
            from pathlib import Path
            payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
            Path(sys.argv[1]).write_text(json.dumps({
                "payload": payload,
                "env": dict(os.environ),
                "isolated": bool(sys.flags.isolated),
                "dont_write_bytecode": sys.dont_write_bytecode,
                "own_session": os.getsid(0) == os.getpid(),
            }), encoding="utf-8")
            sys.stderr.write("diagnostic noise the parent must discard\\n")
            result = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
            sys.stdout.write(json.dumps(
                {"schema_version": "dspx-foundry-jury-child-result-v1", "result": result}
            ))
            """,
            str(seen),
            str(canned),
        ),
    )
    owner_before = _owner_modules()

    payload = _execute(receipt, owner_root, LOCAL_VLLM_FAMILY.provider_name)

    assert payload["status"] == "ok"
    assert payload["reused"] is False
    assert not (_owner_modules() - owner_before)
    assert _sidecars(receipt) == {
        "attempt": True,
        "result": True,
        "receipt": True,
        "journals": False,
    }
    observed = json.loads(seen.read_text(encoding="utf-8"))
    assert observed["isolated"] is True
    assert observed["dont_write_bytecode"] is True
    assert observed["own_session"] is True
    assert set(observed["env"]) <= ALLOWED_ENV_KEYS
    assert observed["env"][LOCAL_VLLM_ENDPOINT_ENV] == "http://localhost:8000/v1"
    assert observed["env"]["DSPX_CACHE_DIR"] == str(tmp_path / "cache")
    attempt = json.loads(
        (receipt.parent / "comparison-jury-attempt.json").read_text(encoding="utf-8")
    )
    child_request = observed["payload"]
    assert child_request["schema_version"] == jury_child.CHILD_REQUEST_SCHEMA
    assert child_request["request"] == attempt["execution_request"]
    assert child_request["attempt_sha256"] == _sha256(
        receipt.parent / "comparison-jury-attempt.json"
    )
    assert child_request["experiment_root"] == str(receipt.parent)
    assert child_request["candidate_manifest_path"] == str(
        validated["candidate_manifest_path"]
    )
    assert child_request["comparison_path"] == str(validated["comparison_path"])
    assert child_request["expected_input_sha256"] == {
        entry["path"]: entry["sha256"] for entry in attempt["jury_input_snapshots"]
    }
    written = json.loads(
        (receipt.parent / "comparison-jury-results.json").read_text(encoding="utf-8")
    )
    assert written == _model_result(validated)
    reused = _execute(receipt, owner_root, LOCAL_VLLM_FAMILY.provider_name)
    assert reused["reused"] is True


def test_child_failure_leaves_attempt_marker_and_blocks_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    _install(monkeypatch, validated)
    monkeypatch.setattr(
        comparison_jury,
        "_CHILD_ARGV",
        (sys.executable, "-I", "-B", "-c", "import sys; sys.exit(7)"),
    )
    with pytest.raises(
        RuntimeError,
        match="exited with status 7; one or more provider juror calls may have occurred",
    ):
        _execute(receipt, owner_root, XAI_FAMILY.provider_name)
    assert _sidecars(receipt) == {
        "attempt": True,
        "result": False,
        "receipt": False,
        "journals": False,
    }
    blocked = _execute(receipt, owner_root, XAI_FAMILY.provider_name)
    assert blocked["status"] == "blocked_indeterminate"
    assert blocked["effect_disposition"] == (
        "one_or_more_provider_juror_calls_may_have_occurred"
    )
    assert _sidecars(receipt)["result"] is False


def test_child_failure_exits_3_through_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    _install(monkeypatch, validated)
    monkeypatch.setattr(
        comparison_jury,
        "_CHILD_ARGV",
        (sys.executable, "-I", "-B", "-c", "import sys; sys.exit(1)"),
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "jury-foundry-gepa-comparison",
            "--receipt",
            str(receipt),
            "--provider",
            XAI_FAMILY.provider_name,
            "--owner-source-root",
            str(owner_root),
            "--execution-task-id",
            "6000",
            "--execution-claimant",
            "pi:test",
        ],
    )
    assert result.exit_code == 3, result.output
    assert "may have occurred" in result.output
    assert _sidecars(receipt)["attempt"] is True


@pytest.mark.parametrize(
    ("stdout", "reason"),
    [
        ("this is not json", "output is not JSON"),
        ('{"schema_version": "other", "result": {}}', "output shape drifted"),
        ('{"result": {"status": "executed"}}', "output shape drifted"),
        (
            '{"schema_version": "dspx-foundry-jury-child-result-v1", "result": []}',
            "output shape drifted",
        ),
        ("", "output is not JSON"),
    ],
)
def test_unparsable_child_output_is_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdout: str, reason: str
) -> None:
    receipt, validated = _fixture(tmp_path)
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    _install(monkeypatch, validated)
    monkeypatch.setattr(
        comparison_jury,
        "_CHILD_ARGV",
        (sys.executable, "-I", "-B", "-c", f"import sys; sys.stdout.write({stdout!r})"),
    )
    with pytest.raises(RuntimeError, match=reason):
        _execute(receipt, owner_root, XAI_FAMILY.provider_name)
    assert _sidecars(receipt) == {
        "attempt": True,
        "result": False,
        "receipt": False,
        "journals": False,
    }


def test_child_timeout_kills_the_child_and_stays_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    _install(monkeypatch, validated)
    pid_file = tmp_path / "child.pid"
    monkeypatch.setattr(
        comparison_jury,
        "_CHILD_ARGV",
        _script_argv(
            tmp_path,
            """
            import os, sys, time
            from pathlib import Path
            Path(sys.argv[1]).write_text(str(os.getpid()), encoding="utf-8")
            sys.stdout.write("partial")
            sys.stdout.flush()
            time.sleep(60)
            """,
            str(pid_file),
        ),
    )
    monkeypatch.setattr(comparison_jury, "child_timeout_seconds", lambda count: 2.0)
    with pytest.raises(RuntimeError, match="timed out"):
        _execute(receipt, owner_root, XAI_FAMILY.provider_name)
    child_pid = int(pid_file.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
    assert _sidecars(receipt)["attempt"] is True
    assert _sidecars(receipt)["result"] is False


def test_generic_provider_still_runs_in_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    monkeypatch.setattr(
        comparison_jury,
        "validate_successful_program_foundry_gepa_consumption_receipt",
        lambda path, **kwargs: dict(validated),
    )
    calls: list[dict[str, Any]] = []

    def build(slot: object, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return _model_result(validated)

    monkeypatch.setattr(comparison_jury, "build_comparison_model_jury_result", build)
    monkeypatch.setattr(
        comparison_jury,
        "_CHILD_ARGV",
        (sys.executable, "-I", "-B", "-c", "import sys; sys.exit(9)"),
    )
    payload = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider="fixture-provider",
        max_jurors=1,
    )
    assert payload["status"] == "ok"
    assert len(calls) == 1
    assert calls[0]["provider_runtime_binding"] is None
