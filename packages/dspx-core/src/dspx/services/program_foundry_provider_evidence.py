# summary: "Conservative provider labels; names never authenticate live execution."
# read_when:
#   - "Changing how foundry sidecars, GEPA receipts, comparisons, or jury receipts label the evidence their providers produced."
#   - "Reading a provider_evidence_kind value in a foundry artifact or the Misegraph receipt consumer."

"""Provider evidence labelling for the foundry lineage.

Retained ``provider_evidence_kind`` values are historical assertions, not proof.
New name-only classification can identify a stub, never authenticate live execution.
The retained closed vocabulary is:

- ``live`` — a real model behind a supported provider port answered;
- ``authored_fixture_replay`` — an operator-authored fixture entry was replayed;
- ``stub_echo`` — the stub provider echoed its input (or an injected fixture).

The label is additive and backward compatible: an absent value means
``unknown`` (every retained pre-AK-5362 receipt stays valid). A lineage's
label is its weakest link: any ``stub_echo`` wins over any
``authored_fixture_replay``, which wins over ``live``; ``live`` is claimed only
when every known link is live and no link is unknown.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

PROVIDER_EVIDENCE_LIVE = "live"
PROVIDER_EVIDENCE_AUTHORED_FIXTURE_REPLAY = "authored_fixture_replay"
PROVIDER_EVIDENCE_STUB_ECHO = "stub_echo"
PROVIDER_EVIDENCE_KINDS: tuple[str, ...] = (
    PROVIDER_EVIDENCE_LIVE,
    PROVIDER_EVIDENCE_AUTHORED_FIXTURE_REPLAY,
    PROVIDER_EVIDENCE_STUB_ECHO,
)
PROVIDER_EVIDENCE_KIND_FIELD = "provider_evidence_kind"

_STUB_PROVIDER_NAMES = frozenset({"stub"})
_STUB_MODEL_IDS = frozenset({"stub/echo"})


def is_provider_evidence_kind(value: object) -> bool:
    return isinstance(value, str) and value in PROVIDER_EVIDENCE_KINDS


def provider_evidence_kind_for_provider(provider: object) -> str | None:
    """Label one provider port or task-local jury provider name; None when unknown."""

    if not isinstance(provider, str):
        return None
    name = provider.strip().lower()
    if not name:
        return None
    if name in _STUB_PROVIDER_NAMES:
        return PROVIDER_EVIDENCE_STUB_ECHO
    return None


def provider_evidence_kind_for_model(model: object) -> str | None:
    """Label a bare model id (``stub/echo``, ``local/...``); None when unknown."""

    if not isinstance(model, str):
        return None
    text = model.strip()
    if text in _STUB_MODEL_IDS:
        return PROVIDER_EVIDENCE_STUB_ECHO
    return None


def provider_evidence_kind_from_behavior_results(
    behavior_results: Mapping[str, Any] | None,
) -> str | None:
    """Label the provider block of a program-run or generated behavior_results."""

    if not isinstance(behavior_results, Mapping):
        return None
    provider = behavior_results.get("provider")
    if not isinstance(provider, Mapping):
        return None
    if provider.get("status") != "configured":
        return None
    metadata = provider.get("metadata")
    if isinstance(metadata, Mapping):
        kind = provider_evidence_kind_for_provider(metadata.get("provider"))
        if kind is not None:
            return kind
        kind = provider_evidence_kind_for_model(metadata.get("model"))
        if kind is not None:
            return kind
    kind = provider_evidence_kind_for_provider(provider.get("provider"))
    if kind is not None:
        return kind
    return provider_evidence_kind_for_model(provider.get("provider"))


def provider_evidence_kind_from_oracle_result(
    semantic_result: Mapping[str, Any] | None,
) -> str | None:
    """Label an Oracle semantic result; only terminal successes are labelled."""

    if not isinstance(semantic_result, Mapping):
        return None
    backend_kind = semantic_result.get("backend_kind")
    execution_status = semantic_result.get("execution_status")
    if backend_kind == "fixture-replay" and execution_status == "replayed_fixture":
        return PROVIDER_EVIDENCE_AUTHORED_FIXTURE_REPLAY
    if (
        backend_kind == "live"
        and execution_status == "succeeded"
        and semantic_result.get("live_call_succeeded") is True
    ):
        return provider_evidence_kind_for_provider(
            semantic_result.get("executed_provider")
        )
    return None


def provider_evidence_kind_from_gepa_result(
    gepa_result: Mapping[str, Any] | None,
) -> str | None:
    """Label a program-refinement GEPA result from its student/reflection providers."""

    if not isinstance(gepa_result, Mapping):
        return None
    gepa = gepa_result.get("gepa")
    if not isinstance(gepa, Mapping) or gepa.get("attempted") is not True:
        return None
    if gepa.get("status") != "completed":
        return None
    return weakest_provider_evidence_kind(
        provider_evidence_kind_for_provider(gepa.get("student_provider")),
        provider_evidence_kind_for_provider(gepa.get("reflection_provider")),
    )


def weakest_provider_evidence_kind(*kinds: str | None) -> str | None:
    """Weakest link: stub_echo < authored_fixture_replay < live; unknown never upgrades."""

    known = [kind for kind in kinds if kind is not None]
    for kind in known:
        if not is_provider_evidence_kind(kind):
            raise ValueError(f"unknown provider evidence kind {kind!r}")
    if PROVIDER_EVIDENCE_STUB_ECHO in known:
        return PROVIDER_EVIDENCE_STUB_ECHO
    if PROVIDER_EVIDENCE_AUTHORED_FIXTURE_REPLAY in known:
        return PROVIDER_EVIDENCE_AUTHORED_FIXTURE_REPLAY
    if known and len(known) == len(kinds):
        return PROVIDER_EVIDENCE_LIVE
    return None


def lineage_provider_evidence(
    links: Mapping[str, str | None],
) -> dict[str, Any]:
    """Project per-link labels plus the weakest-link lineage label."""

    ordered = {str(name): kind for name, kind in links.items()}
    return {
        "schema_version": "dspx-provider-evidence-kind-v1",
        "links": ordered,
        "lineage": weakest_provider_evidence_kind(*ordered.values()),
        "closed_values": list(PROVIDER_EVIDENCE_KINDS),
        "absent_means": "unknown",
    }


def provider_evidence_kind_from_interpretation(
    comparison: Mapping[str, Any] | None,
) -> str | None:
    """Read a candidate comparison's interpretation label; None when absent."""

    if not isinstance(comparison, Mapping):
        return None
    interpretation = comparison.get("interpretation")
    if not isinstance(interpretation, Mapping):
        return None
    kind = interpretation.get(PROVIDER_EVIDENCE_KIND_FIELD)
    return kind if is_provider_evidence_kind(kind) else None


def validate_optional_provider_evidence_kind(value: object) -> str | None:
    """Accept an absent or closed-set label; reject anything else."""

    if value is None:
        return None
    if not is_provider_evidence_kind(value):
        raise ValueError(
            f"{PROVIDER_EVIDENCE_KIND_FIELD} must be one of "
            + ", ".join(PROVIDER_EVIDENCE_KINDS)
        )
    return str(value)


__all__: Sequence[str] = [
    "PROVIDER_EVIDENCE_AUTHORED_FIXTURE_REPLAY",
    "PROVIDER_EVIDENCE_KIND_FIELD",
    "PROVIDER_EVIDENCE_KINDS",
    "PROVIDER_EVIDENCE_LIVE",
    "PROVIDER_EVIDENCE_STUB_ECHO",
    "is_provider_evidence_kind",
    "lineage_provider_evidence",
    "provider_evidence_kind_for_model",
    "provider_evidence_kind_for_provider",
    "provider_evidence_kind_from_behavior_results",
    "provider_evidence_kind_from_gepa_result",
    "provider_evidence_kind_from_interpretation",
    "provider_evidence_kind_from_oracle_result",
    "validate_optional_provider_evidence_kind",
    "weakest_provider_evidence_kind",
]
