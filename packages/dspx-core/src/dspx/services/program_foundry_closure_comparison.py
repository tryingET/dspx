"""Finite historical comparison reconstruction from captured outputs, never reruns."""

from program_foundry_closure_io import Rejected, canonical, equal, sibling  # ty: ignore[unresolved-import]
from program_foundry_closure_reducers import (  # ty: ignore[unresolved-import]
    _behavior_summary,
    _runtime_summary,
    _behavior_delta,
    _interpretation,
)

RUNTIME_LIMITS = [
    "Runtime episodes are already-produced local program-run evidence; comparison never reruns candidates.",
    "Runtime success, trace coverage, or Oracle-readable evidence is not promotion, activation, ranking, or owner acceptance.",
]
# These are finite saved producer dialects, not assertions of actual model origin.
STYLES = {
    "777388ad9c692b0657e6b6e1d4820b15fcb6641d": ("unlabelled_exact",),
    "80cc409da976028263da884ed633bef0806cd986": ("legacy_labels",),
    "6c3473ca17bf03325698e3e1a8419a8abc915938": (
        "legacy_labels",
        "conservative_labels",
    ),
}


def label(behavior: dict, legacy: bool):
    provider = behavior.get("provider", {})
    if not isinstance(provider, dict):
        raise Rejected("comparison_provider_shape")
    if provider.get("status") != "configured":
        return None
    metadata = provider.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    for name in (
        metadata.get("provider"),
        metadata.get("model"),
        provider.get("provider"),
    ):
        if not isinstance(name, str):
            continue
        if name in {"stub", "stub/echo"}:
            return "stub_echo"
        if legacy and (
            name == "openai-compatible"
            or name.startswith(("local/", "foundry-dspy-lm-auth"))
        ):
            return "live"  # reconstruct the old assertion only; never report authenticated-live
    return None


def weakest(values):
    for name in ("stub_echo", "authored_fixture_replay"):
        if name in values:
            return name
    return "live" if values and all(x == "live" for x in values) else None


def view(
    manifests: list,
    behaviors: list,
    episodes: list,
    runtime_episodes: list,
    runtime_behaviors: list,
    style: str,
) -> dict:
    legacy_exact = style == "unlabelled_exact"
    summaries = [
        _behavior_summary(
            manifest=m, behavior=b, behavior_episode=e, legacy_exact=legacy_exact
        )
        for m, b, e in zip(manifests, behaviors, episodes, strict=True)
    ]
    runtimes = [
        _runtime_summary(
            manifest=m, runtime_episode=e, runtime_behavior=b, legacy_exact=legacy_exact
        )
        for m, e, b in zip(manifests, runtime_episodes, runtime_behaviors, strict=True)
    ]
    delta, runtime_delta = _behavior_delta(*summaries), _behavior_delta(*runtimes)
    generated = _interpretation(
        source_summary=summaries[0], candidate_summary=summaries[1], delta=delta
    )
    ri = _interpretation(
        source_summary=runtimes[0], candidate_summary=runtimes[1], delta=runtime_delta
    )
    if legacy_exact:
        # The 777388a producer predates the fifth, provider-label limitation.
        generated["limits"] = generated["limits"][:4]
        ri["limits"] = ri["limits"][:4]
    conflict = any(
        generated[k] != ri[k] for k in ("improvement_observed", "needs_more_evidence")
    )
    interpretation = {
        **generated,
        "evidence_basis": "generated_behavior",
        "generated_evidence_compared": True,
        "runtime_evidence_compared": True,
        "evidence_conflict": conflict,
    }
    if conflict:
        interpretation.update(
            summary="Generated behavior and runtime episode comparison evidence disagree; inspect runtime_evidence_comparison before planning.",
            improvement_observed=False,
            needs_more_evidence=True,
            evidence_basis="mixed_generated_and_runtime",
        )
    if not legacy_exact:
        names = (
            "source_generated_behavior",
            "candidate_generated_behavior",
            "source_runtime_behavior",
            "candidate_runtime_behavior",
        )
        links = dict(
            zip(
                names,
                [
                    label(b, style == "legacy_labels")
                    for b in behaviors + runtime_behaviors
                ],
                strict=True,
            )
        )
        interpretation.update(
            provider_evidence_kind=weakest(list(links.values())),
            provider_evidence_links=links,
        )
        ri["provider_evidence_kind"] = weakest([links[x] for x in names[2:]])
    return {
        "behavior_comparison": {
            "source": summaries[0],
            "candidate": summaries[1],
            "delta": delta,
        },
        "runtime_evidence_comparison": {
            "source": runtimes[0],
            "candidate": runtimes[1],
            "delta": runtime_delta,
            "compared": True,
            "interpretation": ri,
            "limits": RUNTIME_LIMITS,
        },
        "interpretation": interpretation,
    }


def verify_comparison(
    s, comparison: dict, source_path: str, candidate_path: str, owner: str
) -> None:
    styles = STYLES.get(owner)
    if styles is None:
        raise Rejected("comparison_owner_unsupported", "unsupported")
    paths = [source_path, candidate_path]
    runtime_paths = [
        comparison["created_from"][k + "_runtime_episode_path"]
        for k in ("source", "candidate")
    ]
    arguments = (
        [s.json(p) for p in paths],
        [s.json(sibling(p, "behavior_results.json")) for p in paths],
        [s.json(sibling(p, "behavior_episode.json")) for p in paths],
        [s.json(p) for p in runtime_paths],
        [s.json(sibling(p, "behavior_results.json")) for p in runtime_paths],
    )
    actual = {
        k: comparison.get(k)
        for k in (
            "behavior_comparison",
            "runtime_evidence_comparison",
            "interpretation",
        )
    }
    if not any(
        canonical(actual) == canonical(view(*arguments, style)) for style in styles
    ):
        raise Rejected("comparison_semantics_mismatch")
    equal(comparison["status"], "compared")
