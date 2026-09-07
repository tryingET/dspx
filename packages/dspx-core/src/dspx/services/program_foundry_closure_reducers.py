"""Shared deterministic comparison reducers; no I/O, provider or recipe execution."""

from typing import Any, Mapping

_LIMITS = [
    "Comparison includes generated local behavior evidence: behavior_episode.json and, when present, example-backed behavior_results.json.",
    "Optional program-run runtime episodes may be compared only after final-consumer validation rebinds their manifest, inputs, behavior, runtime traces, and Oracle-readable evidence to current files.",
    "Dataset split evidence is summarized from the bounded eval_behavior.py orchestration; no extra dataset, model jury, topology, or custom-module execution is run by comparison.",
    "This comparison is not a promotion, ranking, winner-selection, or approval decision.",
    "interpretation.provider_evidence_kind labels what produced the compared behavior (live, authored_fixture_replay, stub_echo); absent or null means unknown, and stub_echo or authored_fixture_replay evidence cannot support a review recommendation.",
]


def metric_is_exact(metric: object) -> bool:
    return str(metric or "").strip().lower() in {"", "exact", "exact_match"}


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _identity_from_manifest(manifest: Mapping[str, Any]) -> dict[str, str | None]:
    request = _safe_mapping(manifest.get("request"))
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    return {
        "request_id": _first_text(
            request.get("request_id"),
            candidate_assembly.get("request_id"),
            execution_episode.get("request_id"),
            receipt_bundle.get("request_id"),
        ),
        "candidate_id": _first_text(
            candidate_assembly.get("candidate_id"),
            execution_episode.get("candidate_id"),
            receipt_bundle.get("candidate_id"),
        ),
        "assembly_id": _first_text(
            candidate_assembly.get("assembly_id"),
            execution_episode.get("assembly_id"),
            receipt_bundle.get("assembly_id"),
        ),
        "episode_id": _first_text(
            execution_episode.get("episode_id"),
            receipt_bundle.get("episode_id"),
        ),
        "receipt_bundle_id": _first_text(receipt_bundle.get("receipt_bundle_id")),
    }


def _output_fields(
    manifest: Mapping[str, Any], behavior: Mapping[str, Any] | None
) -> list[str]:
    fields = _string_list(_safe_mapping(manifest.get("intent")).get("outputs"))
    if fields:
        return fields
    if behavior is not None:
        return _string_list(behavior.get("output_fields"))
    return []


def _behavior_examples(behavior: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if behavior is None:
        return []
    return [
        dict(item)
        for item in _safe_list(behavior.get("examples"))
        if isinstance(item, Mapping)
    ]


def _failure_signals_from_behavior(
    behavior: Mapping[str, Any] | None,
    *,
    output_fields: list[str],
    exact_metric: bool = True,
) -> list[str]:
    signals: list[str] = []
    comparison_signal = "mismatch" if exact_metric else "differs"
    for record in _behavior_examples(behavior):
        status = str(record.get("status") or "unknown")
        expected = _safe_mapping(record.get("expected_outputs"))
        observed = _safe_mapping(record.get("observed_outputs"))
        if status == "error":
            error = _safe_mapping(record.get("error"))
            signals.append(f"error:{error.get('type') or 'unknown'}")
        if status.startswith("degraded"):
            signals.append(status)
        for field in output_fields:
            if (
                field in expected
                and field in observed
                and str(expected[field]) != str(observed[field])
            ):
                signals.append(f"{comparison_signal}:{field}")
            if field not in observed and status != "error":
                signals.append(f"missing_observed:{field}")
        for note in _string_list(record.get("notes")):
            if "output mismatch" in note:
                for field in output_fields:
                    if field in note:
                        signals.append(f"{comparison_signal}:{field}")
    unique: list[str] = []
    for signal in signals:
        if signal not in unique:
            unique.append(signal)
    return unique


def _safe_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return int(text)
        except ValueError:
            return default
    return default


def _status_counts(behavior: Mapping[str, Any] | None) -> dict[str, int]:
    summary = _safe_mapping(behavior.get("summary")) if behavior is not None else {}
    raw_counts = summary.get("status_counts")
    if isinstance(raw_counts, Mapping):
        return {str(key): _safe_int(value) for key, value in sorted(raw_counts.items())}
    counts: dict[str, int] = {}
    for record in _behavior_examples(behavior):
        status = str(record.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _runtime_artifact_hashes(
    runtime_episode: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if runtime_episode is None:
        return {}
    artifact_hashes = _safe_mapping(runtime_episode.get("artifact_hashes"))
    return {
        "runtime_inputs_hash": artifact_hashes.get("runtime_inputs_sha256"),
        "behavior_results_hash": artifact_hashes.get("behavior_results_sha256"),
        "program_runtime_traces_hash": artifact_hashes.get(
            "program_runtime_traces_sha256"
        ),
        "oracle_evidence_hash": artifact_hashes.get("oracle_evidence_sha256"),
    }


def _runtime_summary(
    *,
    manifest: Mapping[str, Any],
    runtime_episode: Mapping[str, Any] | None,
    runtime_behavior: Mapping[str, Any] | None,
    legacy_exact: bool = False,
) -> dict[str, Any]:
    if runtime_episode is None:
        return {
            "behavior_evidence_present": False,
            "behavior_evidence_kind": None,
            "runtime_evidence_present": False,
            "runtime_episode_id": None,
            "runtime_status": "not_supplied",
            "contract_mode": None,
            "behavior_status": "insufficient_runtime_evidence",
            "example_count": 0,
            "status_counts": {},
            "failure_signals": [],
            "artifact_hashes": {},
        }
    behavior_summary = _behavior_summary(
        manifest=manifest,
        behavior=runtime_behavior,
        behavior_episode=None,
        legacy_exact=legacy_exact,
    )
    return {
        "behavior_evidence_present": True,
        "behavior_evidence_kind": "runtime_episode",
        "runtime_evidence_present": True,
        "runtime_episode_id": runtime_episode.get("runtime_episode_id"),
        "runtime_status": runtime_episode.get("status"),
        "contract_mode": runtime_episode.get("contract_mode"),
        "behavior_status": behavior_summary.get("behavior_status"),
        "example_count": behavior_summary.get("example_count"),
        "status_counts": behavior_summary.get("status_counts"),
        "failure_signals": behavior_summary.get("failure_signals"),
        "artifact_hashes": _runtime_artifact_hashes(runtime_episode),
    }


def _episode_status_counts(episode: Mapping[str, Any]) -> dict[str, int]:
    summary = _safe_mapping(episode.get("summary"))
    counts: dict[str, int] = {}
    for key in ("passed", "failed", "error", "degraded"):
        value = _safe_int(summary.get(key))
        if value:
            counts[key] = value
    if counts:
        return {key: counts[key] for key in sorted(counts)}
    raw_counts = summary.get("status_counts")
    if isinstance(raw_counts, Mapping):
        return {str(key): _safe_int(value) for key, value in sorted(raw_counts.items())}
    return {}


def _failure_signals_from_episode(episode: Mapping[str, Any]) -> list[str]:
    signals: list[str] = []
    for source in _safe_list(episode.get("sources")):
        if not isinstance(source, Mapping):
            continue
        source_label = _first_text(
            source.get("split"), source.get("source_kind"), "source"
        )
        summary = _safe_mapping(source.get("summary"))
        failed = _safe_int(summary.get("failed"))
        error = _safe_int(summary.get("error"))
        degraded = _safe_int(summary.get("degraded"))
        if failed:
            signals.append(f"failed:{source_label}")
        if error:
            signals.append(f"error:{source_label}")
        if degraded:
            signals.append(f"degraded:{source_label}")
        behavior_status = _first_text(source.get("behavior_status"))
        if behavior_status in {"failed", "error"} or str(behavior_status).startswith(
            "degraded"
        ):
            signals.append(f"source_status:{source_label}:{behavior_status}")
    unique: list[str] = []
    for signal in signals:
        if signal not in unique:
            unique.append(signal)
    return unique


def _behavior_summary(
    *,
    manifest: Mapping[str, Any],
    behavior: Mapping[str, Any] | None,
    behavior_episode: Mapping[str, Any] | None,
    legacy_exact: bool = False,
) -> dict[str, Any]:
    if behavior is None and behavior_episode is None:
        return {
            "behavior_evidence_present": False,
            "behavior_results_present": False,
            "behavior_episode_present": False,
            "behavior_evidence_kind": None,
            "behavior_status": "insufficient_behavior_evidence",
            "example_count": 0,
            "source_count": 0,
            "status_counts": {},
            "failure_signals": [],
        }
    if behavior is not None:
        summary = _safe_mapping(behavior.get("summary"))
        output_fields = _output_fields(manifest, behavior)
        return {
            "behavior_evidence_present": True,
            "behavior_results_present": True,
            "behavior_episode_present": behavior_episode is not None,
            "behavior_evidence_kind": "behavior_results",
            "behavior_status": str(summary.get("status") or "unknown"),
            "example_count": _safe_int(
                summary.get("total"), default=len(_behavior_examples(behavior))
            ),
            "source_count": _safe_int(
                _safe_mapping((behavior_episode or {}).get("summary")).get(
                    "source_count"
                ),
                default=1,
            ),
            "status_counts": _status_counts(behavior),
            "failure_signals": _failure_signals_from_behavior(
                behavior,
                output_fields=output_fields,
                exact_metric=legacy_exact
                or metric_is_exact(_safe_mapping(manifest.get("intent")).get("metric")),
            ),
        }
    episode_summary = _safe_mapping((behavior_episode or {}).get("summary"))
    return {
        "behavior_evidence_present": True,
        "behavior_results_present": False,
        "behavior_episode_present": True,
        "behavior_evidence_kind": "behavior_episode",
        "behavior_status": str(episode_summary.get("status") or "unknown"),
        "example_count": _safe_int(episode_summary.get("total")),
        "source_count": _safe_int(episode_summary.get("source_count")),
        "status_counts": _episode_status_counts(behavior_episode or {}),
        "failure_signals": _failure_signals_from_episode(behavior_episode or {}),
    }


def _failed_count(summary: Mapping[str, Any]) -> int:
    counts = _safe_mapping(summary.get("status_counts"))
    return _safe_int(counts.get("failed"))


def _count_for(summary: Mapping[str, Any], key: str) -> int:
    counts = _safe_mapping(summary.get("status_counts"))
    return _safe_int(counts.get(key))


def _behavior_delta(
    source_summary: Mapping[str, Any], candidate_summary: Mapping[str, Any]
) -> dict[str, Any]:
    source_signals = set(_string_list(source_summary.get("failure_signals")))
    candidate_signals = set(_string_list(candidate_summary.get("failure_signals")))
    source_failed = _failed_count(source_summary)
    candidate_failed = _failed_count(candidate_summary)
    source_error = _count_for(source_summary, "error")
    candidate_error = _count_for(candidate_summary, "error")
    source_degraded = sum(
        count
        for status, count in _safe_mapping(source_summary.get("status_counts")).items()
        if str(status).startswith("degraded")
    )
    candidate_degraded = sum(
        count
        for status, count in _safe_mapping(
            candidate_summary.get("status_counts")
        ).items()
        if str(status).startswith("degraded")
    )
    return {
        "source_failed_count": source_failed,
        "candidate_failed_count": candidate_failed,
        "failed_count_delta": candidate_failed - source_failed,
        "source_error_count": source_error,
        "candidate_error_count": candidate_error,
        "error_count_delta": candidate_error - source_error,
        "source_degraded_count": source_degraded,
        "candidate_degraded_count": candidate_degraded,
        "degraded_count_delta": candidate_degraded - source_degraded,
        "status_changed": source_summary.get("behavior_status")
        != candidate_summary.get("behavior_status"),
        "failure_signals_removed": sorted(source_signals - candidate_signals),
        "failure_signals_added": sorted(candidate_signals - source_signals),
        "failure_signals_persisted": sorted(source_signals & candidate_signals),
    }


def _interpretation(
    *,
    source_summary: Mapping[str, Any],
    candidate_summary: Mapping[str, Any],
    delta: Mapping[str, Any],
) -> dict[str, Any]:
    source_present = source_summary.get("behavior_evidence_present") is True
    candidate_present = candidate_summary.get("behavior_evidence_present") is True
    if not source_present or not candidate_present:
        summary = "Comparison has insufficient local behavior evidence for one or both candidates."
        improvement_observed = False
        needs_more_evidence = True
    else:
        removed = _string_list(delta.get("failure_signals_removed"))
        added = _string_list(delta.get("failure_signals_added"))
        failed_delta = int(delta.get("failed_count_delta") or 0)
        error_delta = int(delta.get("error_count_delta") or 0)
        degraded_delta = int(delta.get("degraded_count_delta") or 0)
        improvement_observed = bool(removed) and failed_delta <= 0 and error_delta <= 0
        if failed_delta < 0 or error_delta < 0 or degraded_delta < 0:
            improvement_observed = True
        if improvement_observed:
            summary = "The second candidate removed or reduced at least one observed local behavior signal."
        elif _string_list(delta.get("failure_signals_persisted")):
            summary = "The second candidate did not remove the observed local behavior signal."
        elif added:
            summary = "The second candidate introduced new local behavior signals without removing prior signals."
        else:
            summary = "The second candidate behavior status is unchanged on the available local evidence."
        needs_more_evidence = not improvement_observed or bool(added)
    return {
        "summary": summary,
        "improvement_observed": improvement_observed,
        "needs_more_evidence": needs_more_evidence,
        "limits": list(_LIMITS),
    }
