from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from dspx.services.semantic_benchmark import (
    load_semantic_corpus,
    run_semantic_benchmark,
    score_semantic_response,
    write_result,
)

_BENCHMARK_ROOT = Path(__file__).parents[1] / "benchmarks/semantic"
_CORPUS = _BENCHMARK_ROOT / "corpus-v1.json"
_RESULT_SCHEMA = _BENCHMARK_ROOT / "result-schema-v1.json"


def test_offline_corpus_is_deterministic_and_passes_thresholds(tmp_path: Path) -> None:
    corpus = load_semantic_corpus(_CORPUS)
    first = run_semantic_benchmark(corpus)
    second = run_semantic_benchmark(corpus)

    assert first == second
    assert first["schema_version"] == "dspx-semantic-benchmark-result-v1"
    assert first["execution"] == {
        "mode": "offline",
        "provider": None,
        "network_allowed": False,
        "deterministic": True,
    }
    assert first["summary"] == {
        "cases_total": 6,
        "cases_passed": 6,
        "cases_failed": 0,
        "overall_score": 1.0,
        "threshold_pass": True,
    }
    assert first["authority"]["external_authority_mutated"] is False
    assert first["authority"]["promotion_approved"] is False
    assert all("response" not in row for row in first["cases"])
    schema = json.loads(_RESULT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(first)

    out = tmp_path / "nested" / "result.json"
    write_result(first, out)
    assert json.loads(out.read_text(encoding="utf-8")) == first


def test_scoring_requires_semantics_and_rejects_forbidden_claim() -> None:
    case = load_semantic_corpus(_CORPUS)["cases"][3]
    incomplete = score_semantic_response(case, "This is evidence.")
    unsafe = score_semantic_response(
        case, "Evidence can automatically activates the program after promotion."
    )

    assert incomplete["score"] == 0.25
    assert incomplete["missing_group_indexes"] == [1, 2, 3]
    assert unsafe["score"] == 0.0
    assert unsafe["forbidden_hits"] == ["automatically activates"]


def test_live_mode_is_explicit_and_provider_results_remain_evidence_only() -> None:
    corpus = load_semantic_corpus(_CORPUS)
    responses = {case["prompt"]: case["offline_response"] for case in corpus["cases"]}

    with pytest.raises(ValueError, match="requires an explicit provider"):
        run_semantic_benchmark(corpus, mode="live")
    with pytest.raises(ValueError, match="rejects provider"):
        run_semantic_benchmark(corpus, provider="stub")

    result = run_semantic_benchmark(
        corpus,
        mode="live",
        provider="test-provider",
        invoke=responses.__getitem__,
    )
    assert result["summary"]["threshold_pass"] is True
    assert result["execution"]["network_allowed"] is True
    assert result["execution"]["deterministic"] is False
    assert result["authority"]["authoritative_decision"] is False


def test_provider_error_is_sanitized_and_fails_threshold() -> None:
    corpus = load_semantic_corpus(_CORPUS)

    def fail(_prompt: str) -> str:
        raise RuntimeError("provider failed api_key=supersecret-value")

    result = run_semantic_benchmark(corpus, mode="live", provider="broken", invoke=fail)
    rendered = json.dumps(result)
    assert result["summary"]["threshold_pass"] is False
    assert result["summary"]["cases_failed"] == 6
    assert "supersecret-value" not in rendered
    assert "[REDACTED]" in rendered


def test_corpus_validation_fails_closed(tmp_path: Path) -> None:
    corpus = load_semantic_corpus(_CORPUS)
    invalid = deepcopy(corpus)
    invalid["cases"][1]["id"] = invalid["cases"][0]["id"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate case id"):
        load_semantic_corpus(path)
