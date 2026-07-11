# summary: "Loads, scores, and writes bounded evidence-only semantic benchmark corpora and results."
# read_when:
#   - "Changing generic semantic corpus validation, concept scoring, benchmark execution, or result persistence."

"""Reproducible, evidence-only semantic benchmark harness."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, cast

from jsonschema import Draft202012Validator

from dspx.provider_runtime import sanitize_text

RESULT_SCHEMA = "dspx-semantic-benchmark-result-v1"
CORPUS_SCHEMA = "dspx-semantic-benchmark-corpus-v1"
_MAX_CASES = 100
_MAX_TEXT_CHARS = 20_000


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def load_semantic_corpus(path: Path) -> dict[str, Any]:
    """Load and fail closed on an invalid or unbounded benchmark corpus."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != CORPUS_SCHEMA:
        raise ValueError(f"unsupported semantic benchmark corpus: {path}")
    allowed_top_level = {"schema_version", "name", "version", "thresholds", "cases"}
    unknown_top_level = set(raw) - allowed_top_level
    if unknown_top_level:
        raise ValueError(
            "corpus contains unknown fields: " + ", ".join(sorted(unknown_top_level))
        )
    name = raw.get("name")
    version = raw.get("version")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("corpus name must be a non-empty string")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("corpus version must be a positive integer")
    cases = raw.get("cases")
    thresholds = raw.get("thresholds")
    if not isinstance(cases, list) or not cases or len(cases) > _MAX_CASES:
        raise ValueError("corpus cases must be a non-empty bounded list")
    if not isinstance(thresholds, dict):
        raise ValueError("corpus thresholds must be an object")
    expected_thresholds = {
        "min_overall_score",
        "min_case_score",
        "max_failed_cases",
    }
    if set(thresholds) != expected_thresholds:
        raise ValueError(
            "corpus thresholds must contain exactly: "
            + ", ".join(sorted(expected_thresholds))
        )

    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"case {index} must be an object")
        case_id = case.get("id")
        category = case.get("category")
        prompt = case.get("prompt")
        response = case.get("offline_response")
        groups = case.get("required_concept_groups")
        forbidden = case.get("forbidden_concepts", [])
        if not isinstance(case_id, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9_-]*", case_id
        ):
            raise ValueError(f"case {index} has invalid id")
        if case_id in seen:
            raise ValueError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"case {case_id} has invalid category")
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt) > _MAX_TEXT_CHARS
        ):
            raise ValueError(f"case {case_id} has invalid prompt")
        if not isinstance(response, str) or len(response) > _MAX_TEXT_CHARS:
            raise ValueError(f"case {case_id} has invalid offline_response")
        if not isinstance(groups, list) or not groups:
            raise ValueError(f"case {case_id} requires concept groups")
        for group in groups:
            if (
                not isinstance(group, list)
                or not group
                or not all(isinstance(term, str) and term.strip() for term in group)
            ):
                raise ValueError(f"case {case_id} has invalid concept group")
        if not isinstance(forbidden, list) or not all(
            isinstance(term, str) and term.strip() for term in forbidden
        ):
            raise ValueError(f"case {case_id} has invalid forbidden concepts")

    for name in ("min_overall_score", "min_case_score"):
        value = thresholds.get(name)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0 <= value <= 1
        ):
            raise ValueError(f"threshold {name} must be between 0 and 1")
    max_failed = thresholds.get("max_failed_cases")
    if (
        not isinstance(max_failed, int)
        or isinstance(max_failed, bool)
        or max_failed < 0
    ):
        raise ValueError("threshold max_failed_cases must be a non-negative integer")
    return cast(dict[str, Any], raw)


def _contains(text: str, term: str) -> bool:
    normalized = " ".join(text.casefold().split())
    needle = " ".join(term.casefold().split())
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", normalized) is not None


def score_semantic_response(case: dict[str, Any], response: str) -> dict[str, Any]:
    """Score declared concepts without embeddings, network, models, or randomness."""
    groups = cast(list[list[str]], case["required_concept_groups"])
    forbidden = cast(list[str], case.get("forbidden_concepts", []))
    matched = [any(_contains(response, term) for term in group) for group in groups]
    forbidden_hits = [term for term in forbidden if _contains(response, term)]
    score = sum(matched) / len(groups) if not forbidden_hits else 0.0
    return {
        "score": round(score, 6),
        "required_groups_total": len(groups),
        "required_groups_matched": sum(matched),
        "missing_group_indexes": [i for i, value in enumerate(matched) if not value],
        "forbidden_hits": forbidden_hits,
    }


def run_semantic_benchmark(
    corpus: dict[str, Any],
    *,
    mode: str = "offline",
    provider: str | None = None,
    invoke: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Run offline fixtures by default; live calls require explicit provider and invoker."""
    if mode not in {"offline", "live"}:
        raise ValueError("mode must be offline or live")
    if mode == "offline" and (provider is not None or invoke is not None):
        raise ValueError("offline mode rejects provider configuration")
    if mode == "live" and (not provider or invoke is None):
        raise ValueError("live mode requires an explicit provider and invoker")

    thresholds = cast(dict[str, Any], corpus["thresholds"])
    case_results: list[dict[str, Any]] = []
    for case in cast(list[dict[str, Any]], corpus["cases"]):
        error: str | None = None
        try:
            response = (
                cast(Callable[[str], str], invoke)(case["prompt"])
                if mode == "live"
                else str(case["offline_response"])
            )
            if len(response) > _MAX_TEXT_CHARS:
                raise ValueError("provider response exceeds benchmark limit")
            scored = score_semantic_response(case, response)
        except Exception as exc:
            response = ""
            error = sanitize_text(str(exc), limit=240)
            scored = {
                "score": 0.0,
                "required_groups_total": len(case["required_concept_groups"]),
                "required_groups_matched": 0,
                "missing_group_indexes": list(
                    range(len(case["required_concept_groups"]))
                ),
                "forbidden_hits": [],
            }
        passed = error is None and scored["score"] >= thresholds["min_case_score"]
        case_results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "status": "passed" if passed else ("error" if error else "failed"),
                **scored,
                "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
                "error": error,
            }
        )

    score = round(sum(row["score"] for row in case_results) / len(case_results), 6)
    failed = sum(row["status"] != "passed" for row in case_results)
    threshold_pass = (
        score >= thresholds["min_overall_score"]
        and failed <= thresholds["max_failed_cases"]
    )
    return {
        "schema_version": RESULT_SCHEMA,
        "corpus": {
            "schema_version": corpus["schema_version"],
            "name": corpus["name"],
            "version": corpus["version"],
            "sha256": _sha256(corpus),
        },
        "execution": {
            "mode": mode,
            "provider": provider,
            "network_allowed": mode == "live",
            "deterministic": mode == "offline",
        },
        "thresholds": thresholds,
        "summary": {
            "cases_total": len(case_results),
            "cases_passed": len(case_results) - failed,
            "cases_failed": failed,
            "overall_score": score,
            "threshold_pass": threshold_pass,
        },
        "cases": case_results,
        "authority": {
            "evidence_only": True,
            "authoritative_decision": False,
            "promotion_approved": False,
            "external_authority_mutated": False,
            "ak_called": False,
        },
    }


def write_result(
    result: dict[str, Any], path: Path, *, result_schema_path: Path
) -> None:
    """Validate and atomically write the machine-readable result."""
    schema = json.loads(result_schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
