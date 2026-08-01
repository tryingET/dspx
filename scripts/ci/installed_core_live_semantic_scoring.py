# summary: "Independently scores the exact bounded semantic case from current behavior evidence."
# read_when:
#   - "Changing installed live semantic case binding, concept coverage, or quality checks."

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, cast

from installed_core_proof_io import InstalledCoreGoldenPathError, json_artifact


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstalledCoreGoldenPathError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise InstalledCoreGoldenPathError(f"{label} must be an array")
    return value


def _same_typed_value(value: object, expected: object) -> bool:
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        if not isinstance(value, dict):
            return False
        observed = cast(dict[object, object], value)
        required = cast(dict[object, object], expected)
        return observed.keys() == required.keys() and all(
            _same_typed_value(observed[key], item) for key, item in required.items()
        )
    if isinstance(expected, list):
        if not isinstance(value, list):
            return False
        return len(value) == len(expected) and all(
            _same_typed_value(left, right)
            for left, right in zip(value, expected, strict=True)
        )
    return value == expected


def _expect(value: object, expected: object, label: str) -> None:
    if not _same_typed_value(value, expected):
        raise InstalledCoreGoldenPathError(
            f"{label} drift: expected {expected!r}, observed {value!r}"
        )


def _contains(text: str, term: str) -> bool:
    normalized = " ".join(text.casefold().split())
    needle = " ".join(term.casefold().split())
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", normalized) is not None


def verify_replay_claims(replay: Mapping[str, Any], *, case_id: str) -> dict[str, str]:
    """Verify one case's receipt-only replay claims without widening them."""

    _expect(replay.get("status"), "ok", f"{case_id} replay status")
    _expect(replay.get("error_codes"), [], f"{case_id} replay errors")
    claims = _mapping(replay.get("replay_claims"), f"{case_id} replay claims")
    dimensions = _mapping(claims.get("dimensions"), f"{case_id} replay dimensions")
    expected = {
        "receipt_integrity_check": "passed",
        "deterministic_regeneration": "not_run",
        "runtime_execution_reproduction": "not_run",
        "semantic_reproduction": "not_evaluated",
        "quality_evaluation_reproduction": "not_evaluated",
    }
    for name, status in expected.items():
        observed = _mapping(dimensions.get(name), f"{case_id} replay dimension {name}")
        _expect(observed.get("status"), status, f"{case_id} replay dimension {name}")
    _expect(
        claims.get("release_claim_allowed"), False, f"{case_id} replay release claim"
    )
    authority = _mapping(claims.get("authority"), f"{case_id} replay authority")
    for field in (
        "release_authority",
        "promotion_authority",
        "activation_authority",
        "governance_authority",
        "external_authority",
    ):
        _expect(authority.get(field), False, f"{case_id} replay authority.{field}")
    return expected


def _false_fields(value: object, fields: tuple[str, ...], label: str) -> None:
    payload = _mapping(value, label)
    for field in fields:
        _expect(payload.get(field), False, f"{label}.{field}")


def _artifact_hash(
    root_descriptor: int, relative: str, *, label: str
) -> tuple[dict[str, Any], str]:
    return json_artifact(root_descriptor, relative, label=label)


def verify_case_artifacts(
    root_descriptor: int,
    *,
    case: Mapping[str, Any],
    row: Mapping[str, Any],
    provider: str,
    requested_model: str,
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    """Bind one declared case to generated artifacts, replay, route, and score."""

    case_id = str(case.get("id") or "")
    _expect(row.get("id"), case_id, f"{case_id} benchmark row id")
    _expect(row.get("status"), "passed", f"{case_id} benchmark row status")
    _expect(row.get("score"), 1.0, f"{case_id} benchmark row score")
    _expect(row.get("error"), None, f"{case_id} benchmark row error")
    expected_replay_status = (
        "not_run_live_unsupported"
        if case.get("runtime_contract") is not None
        else "not_required"
    )
    _expect(
        row.get("runtime_replay_status"),
        expected_replay_status,
        f"{case_id} benchmark runtime replay",
    )
    _expect(row.get("runtime_replay"), None, f"{case_id} live runtime replay")

    candidate = _mapping(row.get("candidate"), f"{case_id} candidate identity")
    artifacts = _mapping(row.get("artifacts"), f"{case_id} benchmark artifacts")
    candidate_root = f"benchmark/{case_id}"
    artifact_specs = {
        "manifest": ("manifest.json", "manifest_sha256"),
        "receipt": ("manifest.json.meta.json", "receipt_sha256"),
        "behavior": ("behavior_results.json", "behavior_results_sha256"),
        "episode": ("behavior_episode.json", "behavior_episode_sha256"),
        "oracle_evidence": ("oracle_evidence.json", None),
        "workflow": ("program_loop.json", "workflow_sha256"),
    }
    loaded: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for name, (filename, result_field) in artifact_specs.items():
        payload, digest = _artifact_hash(
            root_descriptor,
            f"{candidate_root}/{filename}",
            label=f"{case_id} {name}",
        )
        loaded[name] = payload
        hashes[f"{name}_sha256"] = digest
        if result_field is not None:
            _expect(
                artifacts.get(result_field),
                digest,
                f"{case_id} benchmark artifacts.{result_field}",
            )

    assembly = _mapping(
        loaded["manifest"].get("candidate_assembly"),
        f"{case_id} manifest candidate assembly",
    )
    receipt_bundle = _mapping(
        loaded["manifest"].get("receipt_bundle"),
        f"{case_id} manifest receipt bundle",
    )
    _expect(
        candidate.get("assembly_id"),
        assembly.get("assembly_id"),
        f"{case_id} assembly id",
    )
    _expect(
        candidate.get("candidate_id"),
        assembly.get("candidate_id"),
        f"{case_id} candidate id",
    )
    _expect(
        candidate.get("receipt_bundle_id"),
        receipt_bundle.get("receipt_bundle_id"),
        f"{case_id} receipt bundle id",
    )
    _expect(
        loaded["receipt"].get("run_kind"), "program-gen", f"{case_id} receipt run kind"
    )

    behavior = loaded["behavior"]
    behavior_summary = _mapping(behavior.get("summary"), f"{case_id} behavior summary")
    _expect(behavior_summary.get("status"), "passed", f"{case_id} behavior status")
    _expect(behavior_summary.get("total"), 1, f"{case_id} behavior total")
    _expect(behavior_summary.get("passed"), 1, f"{case_id} behavior passed")
    semantic_score = verify_semantic_case(case=case, behavior=behavior, row=row)
    provider_identity = _mapping(
        behavior.get("provider"), f"{case_id} behavior provider"
    )
    _expect(
        str(provider_identity.get("provider", "")),
        f"{provider}/{requested_model}",
        f"{case_id} exact selected live route",
    )
    _expect(
        loaded["episode"].get("status"), "passed", f"{case_id} behavior episode status"
    )
    _false_fields(
        behavior.get("non_authority"),
        (
            "external_authority_mutated",
            "external_mutation",
            "governance_authority",
            "optimization_authority",
            "oracle_promotion",
            "oracle_pruning",
            "oracle_ranking",
            "promotion_authority",
            "winner_selection",
        ),
        f"{case_id} behavior non-authority",
    )
    oracle_behavior = _mapping(
        loaded["oracle_evidence"].get("behavior"), f"{case_id} Oracle evidence behavior"
    )
    oracle_summary = _mapping(
        oracle_behavior.get("summary"), f"{case_id} Oracle behavior summary"
    )
    _expect(oracle_summary.get("status"), "passed", f"{case_id} Oracle behavior status")
    _expect(
        oracle_behavior.get("result_hash"),
        hashes["behavior_sha256"],
        f"{case_id} Oracle evidence behavior hash",
    )
    _expect(loaded["workflow"].get("status"), "ok", f"{case_id} program-loop status")
    _false_fields(
        loaded["workflow"].get("effect"),
        (
            "ak_called",
            "external_authority_mutated",
            "governance_mutated",
            "promotion_applied",
            "shared_oracle_mutated",
            "winner_selected",
        ),
        f"{case_id} program-loop effect",
    )
    replay, replay_hash = _artifact_hash(
        root_descriptor, f"replay/{case_id}.json", label=f"{case_id} replay check"
    )
    replay_claims = verify_replay_claims(replay, case_id=case_id)
    hashes["replay_check_sha256"] = replay_hash
    return (
        {
            "case_id": case_id,
            "status": "passed",
            "semantic_score": semantic_score,
            "candidate_identity": dict(candidate),
            "receipt_check_status": "ok",
            "evidence_hashes": hashes,
        },
        replay_claims,
        {str(candidate["receipt_bundle_id"]): hashes["behavior_sha256"]},
    )


def verify_semantic_case(
    *, case: Mapping[str, Any], behavior: Mapping[str, Any], row: Mapping[str, Any]
) -> float:
    """Derive semantic score from the exact case and current observed output."""

    intent = _mapping(case.get("intent"), "semantic case intent")
    intent_examples = _sequence(intent.get("examples"), "semantic case examples")
    behavior_examples = _sequence(behavior.get("examples"), "behavior examples")
    _expect(len(intent_examples), 1, "semantic case example count")
    _expect(len(behavior_examples), 1, "behavior example count")
    declared = _mapping(intent_examples[0], "semantic case example")
    observed = _mapping(behavior_examples[0], "behavior example")
    _expect(observed.get("status"), "passed", "behavior example status")
    _expect(observed.get("inputs"), declared.get("inputs"), "behavior example inputs")
    _expect(
        observed.get("expected_outputs"),
        declared.get("outputs"),
        "behavior expected outputs",
    )
    response_field = str(case.get("response_field") or "")
    outputs = _mapping(observed.get("observed_outputs"), "behavior observed outputs")
    response = outputs.get(response_field)
    if not isinstance(response, str) or not response.strip():
        raise InstalledCoreGoldenPathError("bounded semantic response is unavailable")
    groups = _sequence(case.get("required_concept_groups"), "required concept groups")
    forbidden = _sequence(case.get("forbidden_concepts"), "forbidden concepts")
    matched = 0
    missing: list[int] = []
    for index, raw_group in enumerate(groups):
        group = _sequence(raw_group, f"required concept group {index}")
        if any(_contains(response, str(phrase)) for phrase in group):
            matched += 1
        else:
            missing.append(index)
    forbidden_hits = [
        str(phrase) for phrase in forbidden if _contains(response, str(phrase))
    ]
    score = round(matched / len(groups), 6) if groups else 0.0
    _expect(missing, [], "independent semantic missing groups")
    _expect(forbidden_hits, [], "independent semantic forbidden hits")
    _expect(row.get("required_groups_total"), len(groups), "benchmark group total")
    _expect(row.get("required_groups_matched"), matched, "benchmark groups matched")
    _expect(row.get("missing_group_indexes"), missing, "benchmark missing groups")
    _expect(row.get("forbidden_hits"), forbidden_hits, "benchmark forbidden hits")
    _expect(row.get("score"), score, "benchmark independently derived score")
    _expect(
        row.get("response_sha256"),
        hashlib.sha256(response.encode("utf-8")).hexdigest(),
        "benchmark response hash",
    )
    quality = _mapping(observed.get("quality_evaluation"), "quality evaluation")
    _expect(quality.get("status"), "passed", "quality status")
    _expect(quality.get("quality_approved"), False, "quality approval authority")
    criteria = _sequence(quality.get("criteria"), "quality criteria")
    declared_criteria = _sequence(
        intent.get("quality_criteria"), "declared quality criteria"
    )
    _expect(len(criteria), 1, "quality criterion count")
    _expect(len(declared_criteria), 1, "declared quality criterion count")
    criterion = _mapping(criteria[0], "quality criterion")
    declared_criterion = _mapping(declared_criteria[0], "declared quality criterion")
    _expect(criterion.get("id"), declared_criterion.get("id"), "quality criterion id")
    _expect(criterion.get("score"), score, "quality criterion score")
    _expect(criterion.get("missing_group_indexes"), missing, "quality missing groups")
    _expect(criterion.get("forbidden_hits"), forbidden_hits, "quality forbidden hits")
    return score
