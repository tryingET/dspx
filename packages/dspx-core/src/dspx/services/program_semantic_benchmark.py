"""Semantic benchmark lane over generated DSPx program-loop behavior evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, cast

from jsonschema import Draft202012Validator

from dspx.provider_runtime import sanitize_text
from dspx.services.program_quality_evaluation import (
    evaluate_declared_quality,
    normalize_quality_criteria,
)
from dspx.services.program_workflow import run_program_loop_from_intent_path
from dspx.services.run_replay_service import check_run_receipt
from dspx.services.semantic_benchmark import score_semantic_response

CORPUS_SCHEMA = "dspx-program-semantic-benchmark-corpus-v1"
RESULT_SCHEMA = "dspx-program-semantic-benchmark-result-v1"
_MAX_CASES = 20
_MAX_CORPUS_BYTES = 1_000_000
_MAX_TEXT_CHARS = 20_000
_MAX_ARTIFACT_BYTES = 5_000_000
_HEX_64 = re.compile(r"[0-9a-f]{64}")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_value(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_bounded_bytes(
    path: Path, *, label: str, max_bytes: int = _MAX_ARTIFACT_BYTES
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"{label} must be a regular file: {path}")
        if before.st_size > max_bytes:
            raise ValueError(f"{label} exceeds {max_bytes}-byte limit: {path}")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 64 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"{label} exceeds {max_bytes}-byte limit: {path}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError(f"{label} changed while it was being read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_file_hash(path: Path, *, label: str) -> str:
    return hashlib.sha256(_read_bounded_bytes(path, label=label)).hexdigest()


def _read_json_and_hash(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    content = _read_bounded_bytes(path, label=label)
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return cast(dict[str, Any], payload), hashlib.sha256(content).hexdigest()


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    payload, _content_hash = _read_json_and_hash(path, label=label)
    return payload


def _required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAX_TEXT_CHARS:
        raise ValueError(f"{field} exceeds {_MAX_TEXT_CHARS} characters")
    return value


def _validate_benchmark_intent(intent: Mapping[str, Any], *, case_id: str) -> None:
    allowed = {
        "name",
        "objective",
        "inputs",
        "outputs",
        "metric",
        "constraints",
        "quality_criteria",
        "topology",
        "examples",
    }
    unknown = set(intent) - allowed
    if unknown:
        raise ValueError(
            f"case {case_id} intent contains unsupported fields: "
            + ", ".join(sorted(unknown))
        )
    topology = intent.get("topology")
    if topology is None:
        return
    if not isinstance(topology, Mapping) or set(topology) - {
        "kind",
        "execution_status",
        "modules",
        "edges",
    }:
        raise ValueError(f"case {case_id} topology exceeds the benchmark subset")
    if topology.get("kind") != "pipeline":
        raise ValueError(f"case {case_id} benchmark topology must be pipeline")
    modules = topology.get("modules")
    edges = topology.get("edges")
    if not isinstance(modules, list) or not modules:
        raise ValueError(f"case {case_id} pipeline requires modules")
    if not isinstance(edges, list) or not edges:
        raise ValueError(f"case {case_id} pipeline requires edges")
    for module in modules:
        if not isinstance(module, Mapping) or set(module) - {
            "id",
            "primitive",
            "signature",
            "role",
        }:
            raise ValueError(f"case {case_id} module exceeds the benchmark subset")
        if module.get("primitive") not in {
            "Predict",
            "predict",
            "ChainOfThought",
            "chain_of_thought",
        }:
            raise ValueError(f"case {case_id} module primitive is not benchmark-safe")
        signature = module.get("signature")
        if not isinstance(signature, Mapping) or set(signature) != {
            "name",
            "inputs",
            "outputs",
        }:
            raise ValueError(f"case {case_id} module signature has an invalid shape")
    for edge in edges:
        if not isinstance(edge, Mapping) or set(edge) != {"from", "to"}:
            raise ValueError(f"case {case_id} edge exceeds the benchmark subset")


def _validate_program_semantic_corpus_payload(
    raw: object, *, source: str
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"unsupported program semantic benchmark corpus: {source}")
    payload = cast(dict[str, Any], raw)
    if payload.get("schema_version") != CORPUS_SCHEMA:
        raise ValueError(f"unsupported program semantic benchmark corpus: {source}")
    allowed = {"schema_version", "name", "version", "thresholds", "cases"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(
            "corpus contains unknown fields: " + ", ".join(sorted(unknown))
        )
    _required_string(payload.get("name"), field="corpus name")
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("corpus version must be a positive integer")
    thresholds = payload.get("thresholds")
    if not isinstance(thresholds, dict) or set(thresholds) != {
        "min_overall_score",
        "min_case_score",
        "max_failed_cases",
    }:
        raise ValueError("corpus thresholds have an invalid shape")
    for key in ("min_overall_score", "min_case_score"):
        value = thresholds[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 1
        ):
            raise ValueError(f"threshold {key} must be between 0 and 1")
    maximum_failed = thresholds["max_failed_cases"]
    if (
        isinstance(maximum_failed, bool)
        or not isinstance(maximum_failed, int)
        or maximum_failed < 0
    ):
        raise ValueError("threshold max_failed_cases must be a non-negative integer")

    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases or len(cases) > _MAX_CASES:
        raise ValueError("corpus cases must be a non-empty bounded list")
    seen: set[str] = set()
    for index, item in enumerate(cases):
        if not isinstance(item, dict):
            raise ValueError(f"case {index} must be an object")
        expected_fields = {
            "id",
            "category",
            "intent",
            "response_field",
            "offline_stub_response",
            "required_concept_groups",
            "forbidden_concepts",
        }
        if set(item) != expected_fields:
            raise ValueError(f"case {index} fields do not match the v1 contract")
        case_id = _required_string(item.get("id"), field=f"case {index} id")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", case_id):
            raise ValueError(f"case {index} has invalid id")
        if case_id in seen:
            raise ValueError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        _required_string(item.get("category"), field=f"case {case_id} category")
        response_field = _required_string(
            item.get("response_field"), field=f"case {case_id} response_field"
        )
        raw_intent = item.get("intent")
        if not isinstance(raw_intent, dict):
            raise ValueError(f"case {case_id} intent must be an object")
        intent = cast(dict[str, Any], raw_intent)
        _validate_benchmark_intent(intent, case_id=case_id)
        outputs = intent.get("outputs")
        if not isinstance(outputs, list) or response_field not in outputs:
            raise ValueError(
                f"case {case_id} response_field must be a declared intent output"
            )
        examples = intent.get("examples")
        if not isinstance(examples, list) or len(examples) != 1:
            raise ValueError(f"case {case_id} intent must declare exactly one example")
        stub = item.get("offline_stub_response")
        if not isinstance(stub, dict) or response_field not in stub:
            raise ValueError(
                f"case {case_id} offline_stub_response must contain response_field"
            )
        groups = item.get("required_concept_groups")
        if not isinstance(groups, list) or not groups:
            raise ValueError(f"case {case_id} requires concept groups")
        for group in groups:
            if (
                not isinstance(group, list)
                or not group
                or not all(isinstance(term, str) and term.strip() for term in group)
            ):
                raise ValueError(f"case {case_id} has an invalid concept group")
        forbidden = item.get("forbidden_concepts")
        if not isinstance(forbidden, list) or not all(
            isinstance(term, str) and term.strip() for term in forbidden
        ):
            raise ValueError(f"case {case_id} has invalid forbidden concepts")
        bounded_outer = normalize_quality_criteria(
            [
                {
                    "id": "benchmark_case",
                    "output_field": response_field,
                    "evaluator": "concept_coverage",
                    "required_concept_groups": groups,
                    "forbidden_concepts": forbidden,
                    "min_score": thresholds["min_case_score"],
                }
            ],
            outputs=[response_field],
        )[0]
        raw_declared = intent.get("quality_criteria", [])
        if raw_declared:
            declared = normalize_quality_criteria(
                raw_declared, outputs=cast(list[str], outputs)
            )
            if len(declared) != 1 or (
                declared[0]["required_concept_groups"]
                != bounded_outer["required_concept_groups"]
                or declared[0]["forbidden_concepts"]
                != bounded_outer["forbidden_concepts"]
            ):
                raise ValueError(
                    f"case {case_id} outer semantic contract drifts from intent quality_criteria"
                )
            intent["quality_criteria"] = declared
    return cast(dict[str, Any], json.loads(_canonical_bytes(payload)))


def load_program_semantic_corpus(path: Path) -> dict[str, Any]:
    """Load a bounded corpus whose cases contain safe, inline program intents."""

    lexical = _lexical_absolute(path)
    _reject_symlink_components(
        lexical, include_leaf=True, label="program semantic corpus"
    )
    if not lexical.is_file():
        raise ValueError(f"program semantic corpus must be a regular file: {lexical}")
    raw = json.loads(
        _read_bounded_bytes(
            lexical, label="program semantic corpus", max_bytes=_MAX_CORPUS_BYTES
        )
    )
    return _validate_program_semantic_corpus_payload(raw, source=str(lexical))


def _confined_file(
    root: Path, raw_path: object, *, expected_name: str, label: str
) -> Path:
    path = Path(_required_string(raw_path, field=label)).expanduser()
    if not path.is_absolute():
        path = root / path
    is_direct_symlink = path.is_symlink()
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes candidate root: {resolved}") from exc
    if resolved.name != expected_name or not resolved.is_file() or is_direct_symlink:
        raise ValueError(
            f"{label} is not the expected current {expected_name}: {resolved}"
        )
    return resolved


def _preflight_candidate_tree(root: Path) -> None:
    total = 0
    for directory, directories, files in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in [*directories, *files]:
            path = base / name
            if path.is_symlink():
                raise ValueError(f"candidate tree contains a symlink: {path}")
        for name in files:
            path = base / name
            size = path.stat().st_size
            if size > _MAX_ARTIFACT_BYTES:
                raise ValueError(
                    f"candidate artifact exceeds {_MAX_ARTIFACT_BYTES}-byte limit: {path}"
                )
            total += size
            if total > _MAX_ARTIFACT_BYTES * 20:
                raise ValueError("candidate artifact tree exceeds benchmark size limit")


def _require_hash(value: object, *, field: str) -> str:
    text = _required_string(value, field=field)
    if _HEX_64.fullmatch(text) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return text


def _load_case_evidence(
    *, case: Mapping[str, Any], workflow: Mapping[str, Any], case_root: Path
) -> dict[str, Any]:
    """Rebind workflow claims to current candidate files before semantic scoring."""

    if workflow.get("schema_version") != "program-loop-workflow-v2":
        raise ValueError("program-loop returned an unsupported workflow schema")
    if workflow.get("status") != "ok":
        raise ValueError(f"program-loop behavior status is {workflow.get('status')!r}")
    effect = workflow.get("effect")
    if not isinstance(effect, Mapping) or any(
        effect.get(key) is not False
        for key in (
            "shared_oracle_mutated",
            "ak_called",
            "external_authority_mutated",
            "governance_mutated",
            "promotion_applied",
            "winner_selected",
        )
    ):
        raise ValueError("program-loop widened authority or external effects")

    candidate = cast(Mapping[str, Any], workflow.get("candidate") or {})
    raw_root = Path(
        _required_string(candidate.get("root_path"), field="candidate root")
    )
    if raw_root.is_symlink() or case_root.is_symlink():
        raise ValueError("program-loop candidate root must not be a symlink")
    root = raw_root.resolve()
    if root != case_root.resolve():
        raise ValueError(
            "program-loop candidate root does not match the benchmark case root"
        )
    manifest = _confined_file(
        root,
        candidate.get("manifest_path"),
        expected_name="manifest.json",
        label="manifest",
    )
    receipt = _confined_file(
        root,
        candidate.get("receipt_path"),
        expected_name="manifest.json.meta.json",
        label="receipt",
    )
    _preflight_candidate_tree(root)
    manifest_payload, manifest_hash = _read_json_and_hash(manifest, label="manifest")
    receipt_payload, receipt_hash = _read_json_and_hash(receipt, label="receipt")
    if receipt_payload.get("cache_enabled") is not False:
        raise ValueError(
            "benchmark candidate receipt must not depend on an external cache file"
        )
    replay = check_run_receipt(receipt)
    if replay.get("status") != "ok":
        raise ValueError("candidate receipt no longer passes replay integrity checks")
    _preflight_candidate_tree(root)
    if manifest_hash != _read_file_hash(
        manifest, label="manifest"
    ) or receipt_hash != _read_file_hash(receipt, label="receipt"):
        raise ValueError(
            "candidate manifest or receipt changed during replay validation"
        )

    workflow_path = _confined_file(
        root,
        workflow.get("workflow_path"),
        expected_name="program_loop.json",
        label="workflow",
    )
    persisted_workflow, workflow_hash = _read_json_and_hash(
        workflow_path, label="workflow"
    )
    if persisted_workflow != dict(workflow):
        raise ValueError(
            "persisted workflow does not match the in-memory program-loop result"
        )

    steps = cast(Mapping[str, Any], workflow.get("steps") or {})
    behavior = cast(Mapping[str, Any], steps.get("behavior_evaluation") or {})
    if behavior.get("passed") is not True or behavior.get("status") != "passed":
        raise ValueError("generated behavior did not pass")
    episode = _confined_file(
        root,
        behavior.get("path"),
        expected_name="behavior_episode.json",
        label="behavior episode",
    )
    expected_episode_hash = _require_hash(
        behavior.get("sha256"), field="behavior episode hash"
    )
    episode_payload, episode_hash = _read_json_and_hash(
        episode, label="behavior episode"
    )
    if episode_hash != expected_episode_hash:
        raise ValueError("behavior episode hash is stale")
    sources = (
        episode_payload.get("sources") if isinstance(episode_payload, dict) else None
    )
    if (
        not isinstance(sources, list)
        or len(sources) != 1
        or not isinstance(sources[0], dict)
    ):
        raise ValueError("benchmark cases require exactly one behavior source")
    source = sources[0]
    results = _confined_file(
        root,
        source.get("behavior_results_path"),
        expected_name="behavior_results.json",
        label="behavior results",
    )
    expected_results_hash = _require_hash(
        source.get("behavior_results_hash"), field="behavior results hash"
    )
    result_payload, results_hash = _read_json_and_hash(
        results, label="behavior results"
    )
    if results_hash != expected_results_hash:
        raise ValueError("behavior results hash is stale")
    examples = (
        result_payload.get("examples") if isinstance(result_payload, dict) else None
    )
    if (
        not isinstance(examples, list)
        or len(examples) != 1
        or not isinstance(examples[0], dict)
    ):
        raise ValueError("benchmark behavior results require exactly one example")
    example = examples[0]
    if example.get("status") != "passed":
        raise ValueError("benchmark behavior example did not pass")
    observed = example.get("observed_outputs")
    manifest_intent = manifest_payload.get("intent")
    if not isinstance(manifest_intent, Mapping):
        raise ValueError("candidate manifest intent is missing")
    manifest_outputs = (
        [str(item) for item in manifest_intent.get("outputs", [])]
        if isinstance(manifest_intent.get("outputs"), list)
        else []
    )
    declared_quality = normalize_quality_criteria(
        manifest_intent.get("quality_criteria", []), outputs=manifest_outputs
    )
    canonical_quality = evaluate_declared_quality(
        declared_quality,
        observed if isinstance(observed, Mapping) else {},
    )
    if declared_quality:
        if canonical_quality.get("status") != "passed":
            raise ValueError("generated behavior declared quality did not pass")
        expected_quality_summary = {
            "status": "passed",
            "evaluations_total": 1,
            "evaluations_passed": 1,
            "evaluations_failed": 0,
            "quality_approved": False,
        }
        if result_payload.get("quality_evaluation") != expected_quality_summary:
            raise ValueError("generated behavior quality summary is inconsistent")
        if example.get("quality_evaluation") != canonical_quality:
            raise ValueError("generated behavior quality record is inconsistent")
    response_field = str(case["response_field"])
    response = observed.get(response_field) if isinstance(observed, dict) else None
    if not isinstance(response, str) or len(response) > _MAX_TEXT_CHARS:
        raise ValueError("generated response field must be a bounded string")
    current_hashes = {
        "manifest": _read_file_hash(manifest, label="manifest"),
        "receipt": _read_file_hash(receipt, label="receipt"),
        "workflow": _read_file_hash(workflow_path, label="workflow"),
        "behavior episode": _read_file_hash(episode, label="behavior episode"),
        "behavior results": _read_file_hash(results, label="behavior results"),
    }
    expected_hashes = {
        "manifest": manifest_hash,
        "receipt": receipt_hash,
        "workflow": workflow_hash,
        "behavior episode": episode_hash,
        "behavior results": results_hash,
    }
    if current_hashes != expected_hashes:
        raise ValueError("candidate evidence changed before benchmark aggregation")
    return {
        "response": response,
        "artifacts": {
            "candidate_root": root.name,
            "manifest_sha256": manifest_hash,
            "receipt_sha256": receipt_hash,
            "workflow_sha256": workflow_hash,
            "behavior_episode_sha256": episode_hash,
            "behavior_results_sha256": results_hash,
        },
        "candidate": {
            "assembly_id": candidate.get("assembly_id"),
            "candidate_id": candidate.get("candidate_id"),
            "receipt_bundle_id": candidate.get("receipt_bundle_id"),
        },
    }


@contextmanager
def _case_environment(
    *, mode: str, provider: str | None, stub: Mapping[str, Any], cache_dir: Path
) -> Iterator[None]:
    keys = (
        "DSPX_PROVIDER",
        "DSPX_STUB_RESPONSE_JSON",
        "DSPX_CACHE_DIR",
        "DSPX_CACHE_ENABLE",
        "MLFLOW_ENABLE",
        "DSPX_ORACLE_EMBEDDING_BACKEND",
    )
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ["DSPX_PROVIDER"] = "stub" if mode == "offline" else str(provider)
        if mode == "offline":
            os.environ["DSPX_STUB_RESPONSE_JSON"] = json.dumps(stub, sort_keys=True)
        else:
            os.environ.pop("DSPX_STUB_RESPONSE_JSON", None)
        os.environ["DSPX_CACHE_DIR"] = str(cache_dir)
        os.environ["DSPX_CACHE_ENABLE"] = "0"
        os.environ["MLFLOW_ENABLE"] = "0"
        os.environ["DSPX_ORACLE_EMBEDDING_BACKEND"] = "mock"
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _lexical_absolute(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return Path(os.path.abspath(expanded))


def _reject_symlink_components(path: Path, *, include_leaf: bool, label: str) -> None:
    absolute = _lexical_absolute(path)
    components = absolute.parts if include_leaf else absolute.parent.parts
    current = Path(components[0])
    for component in components[1:]:
        current /= component
        if current.is_symlink():
            raise ValueError(f"{label} contains a symlink component: {current}")
        if not current.exists():
            break


def _preflight_paths(
    *, corpus_path: Path, work_root: Path, result_path: Path
) -> tuple[Path, Path]:
    root = _lexical_absolute(work_root)
    result = _lexical_absolute(result_path)
    corpus = corpus_path.expanduser().resolve()
    _reject_symlink_components(root, include_leaf=True, label="benchmark work root")
    _reject_symlink_components(result, include_leaf=True, label="benchmark result")
    if root.exists():
        raise ValueError(f"benchmark work root already exists: {root}")
    if result.exists() and result.is_dir():
        raise ValueError(f"benchmark result path is a directory: {result}")
    for label, left, right in (
        ("result/work root", result, root),
        ("corpus/work root", corpus, root),
        ("corpus/result", corpus, result),
    ):
        if left == right or left in right.parents or right in left.parents:
            raise ValueError(f"{label} paths must be disjoint: {left} vs {right}")
    return root, result


def run_program_semantic_benchmark(
    corpus: Mapping[str, Any],
    *,
    corpus_path: Path,
    work_root: Path,
    result_path: Path,
    mode: str = "offline",
    provider: str | None = None,
) -> dict[str, Any]:
    """Run every semantic case through a generated candidate and current evidence."""

    corpus = _validate_program_semantic_corpus_payload(
        dict(corpus), source="in-memory benchmark corpus"
    )
    if mode not in {"offline", "live"}:
        raise ValueError("mode must be offline or live")
    if mode == "offline" and provider is not None:
        raise ValueError("offline mode rejects provider configuration")
    if mode == "live" and (not isinstance(provider, str) or not provider.strip()):
        raise ValueError("live mode requires an explicit provider")
    root, _result = _preflight_paths(
        corpus_path=corpus_path, work_root=work_root, result_path=result_path
    )
    root.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(root, include_leaf=True, label="benchmark work root")
    root.mkdir(exist_ok=False)
    thresholds = cast(Mapping[str, Any], corpus["thresholds"])
    rows: list[dict[str, Any]] = []
    for case in cast(list[dict[str, Any]], corpus["cases"]):
        case_root = root / case["id"]
        intent_path = root / f"{case['id']}.intent.json"
        if case_root.parent != root or intent_path.parent != root:
            raise ValueError(f"case {case['id']} paths escape benchmark work root")
        intent_path.write_text(
            json.dumps(case["intent"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        error: str | None = None
        response = ""
        evidence: dict[str, Any] | None = None
        try:
            with _case_environment(
                mode=mode,
                provider=provider,
                stub=cast(Mapping[str, Any], case["offline_stub_response"]),
                cache_dir=root / ".cache" / case["id"],
            ):
                workflow = run_program_loop_from_intent_path(
                    intent_path,
                    outdir=case_root,
                    skip_oracle_index=True,
                )
                evidence = _load_case_evidence(
                    case=case, workflow=workflow, case_root=case_root
                )
            response = str(evidence.pop("response"))
            scored = score_semantic_response(case, response)
        except Exception as exc:
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
        passed = (
            error is None
            and scored["score"] >= thresholds["min_case_score"]
            and not scored["forbidden_hits"]
        )
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "status": "passed" if passed else ("error" if error else "failed"),
                **scored,
                "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
                "error": error,
                "candidate": evidence["candidate"] if evidence else None,
                "artifacts": evidence["artifacts"] if evidence else None,
            }
        )
    score = round(sum(row["score"] for row in rows) / len(rows), 6)
    failed = sum(row["status"] != "passed" for row in rows)
    return {
        "schema_version": RESULT_SCHEMA,
        "corpus": {
            "schema_version": corpus["schema_version"],
            "name": corpus["name"],
            "version": corpus["version"],
            "sha256": _sha256_value(corpus),
        },
        "execution": {
            "mode": mode,
            "provider": provider,
            "network_allowed": mode == "live",
            "deterministic": mode == "offline",
            "generated_program_path": True,
            "oracle_indexed": False,
        },
        "thresholds": dict(thresholds),
        "summary": {
            "cases_total": len(rows),
            "cases_passed": len(rows) - failed,
            "cases_failed": failed,
            "overall_score": score,
            "threshold_pass": score >= thresholds["min_overall_score"]
            and failed <= thresholds["max_failed_cases"],
        },
        "cases": rows,
        "authority": {
            "evidence_only": True,
            "authoritative_decision": False,
            "promotion_approved": False,
            "activation_applied": False,
            "shared_oracle_mutated": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "ak_called": False,
            "winner_selected": False,
        },
    }


def write_program_semantic_result(
    result: Mapping[str, Any], path: Path, *, result_schema_path: Path
) -> None:
    """Validate then atomically replace the aggregate evidence packet."""

    schema_path = _lexical_absolute(result_schema_path)
    _reject_symlink_components(
        schema_path, include_leaf=True, label="benchmark result schema"
    )
    schema = _read_json_object(schema_path, label="benchmark result schema")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)

    target = _lexical_absolute(path)
    _reject_symlink_components(target, include_leaf=True, label="benchmark result")
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(target, include_leaf=True, label="benchmark result")
    parent_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_fd = os.open(target.parent, parent_flags)
    temporary_name = f".{target.name}.{secrets.token_hex(12)}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        content = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(
            temporary_name,
            target.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)
