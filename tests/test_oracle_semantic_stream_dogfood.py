# summary: "Tests typed Codex semantic-stream dogfood receipts and retry accounting."

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from dspx.dspy_lm_auth_lm import DspyLMAuthLM, DspyLmAuthCall
from dspx.services.program_oracle_semantic_backend import LiveLMOracleSemanticBackend
from dspx.services.program_oracle_semantic_contract import (
    OracleSemanticAnalysis,
    OracleSemanticResult,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/ci/run_oracle_semantic_stream_dogfood.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "oracle_semantic_stream_dogfood", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _analysis() -> OracleSemanticAnalysis:
    return OracleSemanticAnalysis.from_mapping(
        {
            "observations": ["local_quality_checks_passed"],
            "failure_attractors": ["authority_overreach_risk"],
            "quality_contract_violations": [],
            "hypotheses": [],
            "recommended_experiments": ["governing_owner_review"],
            "evidence_refs": [
                "episode:authority:quality",
                "episode:authority:effects",
            ],
            "confidence": 0.8,
        }
    )


def _result(*, succeeded: bool) -> OracleSemanticResult:
    return OracleSemanticResult(
        request_sha256="a" * 64,
        backend_kind="live",
        preferred_model="codex/gpt-5.6-sol",
        configured_provider="dspy-lm-auth",
        configured_model="codex/gpt-5.6-sol",
        executed_provider=None,
        executed_model="openai/gpt-5.6-sol",
        execution_status="succeeded" if succeeded else "failed_after_live_response",
        live_call_succeeded=True,
        analysis=_analysis() if succeeded else None,
        error=None if succeeded else "extracted output was not valid JSON",
    )


def _backend(
    results: list[OracleSemanticResult], *, stream_completed_match: bool = True
) -> LiveLMOracleSemanticBackend:
    lm = DspyLMAuthLM(
        model="codex/gpt-5.6-sol",
        auth_provider="codex",
        kwargs={"reasoning_effort": "max"},
    )
    backend = LiveLMOracleSemanticBackend(
        provider_name="dspy-lm-auth",
        preferred_model="codex/gpt-5.6-sol",
        lm=lm,
    )

    def analyze(request: Any) -> OracleSemanticResult:
        del request
        result = results.pop(0)
        now = time.time()
        lm.history.append(
            DspyLmAuthCall(
                model="codex/gpt-5.6-sol",
                auth_provider="codex",
                started_at=now,
                ended_at=now,
                text="structured",
                usage={},
                transport={
                    "event_counts": {
                        "output_text_delta": 1,
                        "reasoning": 1,
                    },
                    "output_text_chars": 10,
                    "completed_output_text": True,
                    "stream_output_text_chars": 10,
                    "stream_completed_match": stream_completed_match,
                },
            )
        )
        return result

    cast(Any, backend).analyze = analyze
    return backend


def test_dogfood_first_pass_records_typed_transport(
    monkeypatch, tmp_path: Path
) -> None:
    module = _module()
    monkeypatch.setattr(module, "_clean_commit", lambda repo, **kwargs: "source-commit")
    artifact = tmp_path / "artifact"
    ledger = tmp_path / "state" / "ledger.json"
    ledger.parent.mkdir(mode=0o700)

    payload = module.run(
        repo_root=REPO_ROOT,
        artifact_root=artifact,
        ledger_path=ledger,
        resolve_backend=lambda: _backend(
            [_result(succeeded=True)], stream_completed_match=False
        ),
        dependency_identity=lambda: {
            "package": "dspy-lm-auth",
            "version": "test",
            "git_commit": "dependency-commit",
            "module_sha256": "b" * 64,
        },
        test_mode=True,
    )

    assert payload["status"] == "wiring_only_passed"
    assert payload["recovery"] == "first_pass"
    assert len(payload["attempts"]) == 1
    assert (
        payload["claims"]["authoritative_completed_response_json_transport_passed"]
        is False
    )
    assert payload["claims"]["ak_4506_case_reexecuted_under_ak_4535"] is True
    assert payload["claims"]["ak_4506_ledger_reused"] is False
    assert payload["attempts"][0]["transport"]["stream_completed_match"] is False
    assert "typed_stream_json_transport_passed" not in payload["claims"]
    assert payload["semantic_score"]["status"] == "passed"
    assert "raw" not in str(payload).lower()
    assert (artifact / module.RESULT_NAME).stat().st_mode & 0o777 == 0o600
    assert artifact.stat().st_mode & 0o777 == 0o700


def test_dogfood_allows_one_visible_corrective_retry(
    monkeypatch, tmp_path: Path
) -> None:
    module = _module()
    monkeypatch.setattr(module, "_clean_commit", lambda repo, **kwargs: "source-commit")
    artifact = tmp_path / "artifact"
    ledger = tmp_path / "state" / "ledger.json"
    ledger.parent.mkdir(mode=0o700)

    payload = module.run(
        repo_root=REPO_ROOT,
        artifact_root=artifact,
        ledger_path=ledger,
        resolve_backend=lambda: _backend(
            [_result(succeeded=False), _result(succeeded=True)]
        ),
        dependency_identity=lambda: {
            "package": "dspy-lm-auth",
            "version": "test",
            "git_commit": "dependency-commit",
            "module_sha256": "b" * 64,
        },
        test_mode=True,
    )

    assert payload["status"] == "wiring_only_passed"
    assert payload["first_pass_status"] == "failed_after_live_response"
    assert payload["recovery"] == "one_corrective_retry"
    assert [attempt["attempt"] for attempt in payload["attempts"]] == [1, 2]
    assert ledger.read_text(encoding="utf-8").count("attempt_count") == 1

    with pytest.raises(FileExistsError):
        module.run(
            repo_root=REPO_ROOT,
            artifact_root=tmp_path / "second-artifact",
            ledger_path=ledger,
            resolve_backend=lambda: pytest.fail("consumed ledger must fail first"),
            dependency_identity=lambda: pytest.fail("consumed ledger must fail first"),
            test_mode=True,
        )
