# summary: "Defines bounded GEPA 0.1.4 proposal sampling, selection, and acceptance policy."
# read_when:
#   - "Changing GEPA multi-proposal controls, optimizer budgets, or receipt configuration."

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ProposalSampling = Literal["single", "same-parent", "independent", "pxn"]
ProposalSelection = Literal[
    "all-improvements", "best-improvement", "top-k-improvements"
]
ProposalAcceptance = Literal["strict-improvement", "improvement-or-equal"]

_MAX_PROPOSAL_TASKS = 8
_MAX_PROPOSAL_PARENTS = 4
_MAX_RECEIPT_CANDIDATES = 256


@dataclass(frozen=True)
class GEPAProposalConfig:
    """Validated product configuration for GEPA 0.1.4 proposal composition."""

    sampling: ProposalSampling = "single"
    proposal_n: int = 1
    proposal_p: int = 1
    selection: ProposalSelection = "all-improvements"
    top_k: int = 1
    acceptance: ProposalAcceptance = "strict-improvement"

    def __post_init__(self) -> None:
        for name, value in (
            ("proposal_n", self.proposal_n),
            ("proposal_p", self.proposal_p),
            ("top_k", self.top_k),
        ):
            if type(value) is not int:
                raise ValueError(f"{name} must be an integer")
        if self.sampling not in {"single", "same-parent", "independent", "pxn"}:
            raise ValueError(f"unsupported proposal sampling strategy: {self.sampling}")
        if self.selection not in {
            "all-improvements",
            "best-improvement",
            "top-k-improvements",
        }:
            raise ValueError(
                f"unsupported proposal selection strategy: {self.selection}"
            )
        if self.acceptance not in {"strict-improvement", "improvement-or-equal"}:
            raise ValueError(
                f"unsupported proposal acceptance criterion: {self.acceptance}"
            )
        if self.proposal_n < 1 or self.proposal_n > _MAX_PROPOSAL_TASKS:
            raise ValueError("proposal_n must be between 1 and 8")
        if self.proposal_p < 1 or self.proposal_p > _MAX_PROPOSAL_PARENTS:
            raise ValueError("proposal_p must be between 1 and 4")
        if self.top_k < 1 or self.top_k > _MAX_PROPOSAL_TASKS:
            raise ValueError("top_k must be between 1 and 8")

        if self.sampling == "single":
            if self.proposal_n != 1 or self.proposal_p != 1:
                raise ValueError(
                    "single sampling requires proposal_n=1 and proposal_p=1"
                )
        elif self.sampling in {"same-parent", "independent"}:
            if self.proposal_n < 2:
                raise ValueError(f"{self.sampling} sampling requires proposal_n>=2")
            if self.proposal_p != 1:
                raise ValueError(f"{self.sampling} sampling requires proposal_p=1")
        elif self.task_count < 2:
            raise ValueError("pxn sampling requires proposal_p*proposal_n>=2")

        if self.task_count > _MAX_PROPOSAL_TASKS:
            raise ValueError("proposal_p*proposal_n must not exceed 8")
        if self.selection == "top-k-improvements":
            if self.top_k > self.task_count:
                raise ValueError("top_k must not exceed the proposal task count")
        elif self.top_k != 1:
            raise ValueError(f"{self.selection} selection requires top_k=1")

    @property
    def task_count(self) -> int:
        if self.sampling == "pxn":
            return self.proposal_p * self.proposal_n
        if self.sampling in {"same-parent", "independent"}:
            return self.proposal_n
        return 1

    @property
    def is_multi_proposal(self) -> bool:
        return self.task_count > 1

    def to_gepa_kwargs(self) -> dict[str, object]:
        from gepa.strategies.proposal_sampling import (
            IndependentSampling,
            PxNSampling,
            SameParentSampling,
            SingleMutationSampling,
        )
        from gepa.strategies.proposal_selection import (
            AllImprovements,
            BestImprovement,
            TopKImprovements,
        )

        if self.sampling == "single":
            sampling: object = SingleMutationSampling()
        elif self.sampling == "same-parent":
            sampling = SameParentSampling(self.proposal_n)
        elif self.sampling == "independent":
            sampling = IndependentSampling(self.proposal_n)
        else:
            sampling = PxNSampling(self.proposal_p, self.proposal_n)

        if self.selection == "all-improvements":
            selection: object = AllImprovements()
        elif self.selection == "best-improvement":
            selection = BestImprovement()
        else:
            selection = TopKImprovements(self.top_k)

        acceptance = self.acceptance.replace("-", "_")
        return {
            "sampling_strategy": sampling,
            "selection_strategy": selection,
            "acceptance_criterion": acceptance,
        }

    def to_manifest(self) -> dict[str, object]:
        kwargs = self.to_gepa_kwargs()
        return {
            "schema_version": "dspx-gepa-proposal-config-v1",
            "sampling": self.sampling,
            "proposal_n": self.proposal_n,
            "proposal_p": self.proposal_p,
            "proposal_task_count": self.task_count,
            "selection": self.selection,
            "top_k": self.top_k,
            "acceptance": self.acceptance,
            "upstream_sampling_type": type(kwargs["sampling_strategy"]).__name__,
            "upstream_selection_type": type(kwargs["selection_strategy"]).__name__,
            "max_proposal_tasks": _MAX_PROPOSAL_TASKS,
            "max_proposal_parents": _MAX_PROPOSAL_PARENTS,
        }


def validate_gepa_budget(
    config: GEPAProposalConfig,
    *,
    auto: str | None,
    max_metric_calls: int | None,
    max_full_evals: int | None,
) -> None:
    """Fail before provider construction for invalid or misleading budgets."""

    budget_set = sum(
        value is not None for value in (auto, max_metric_calls, max_full_evals)
    )
    if budget_set != 1:
        raise ValueError(
            "Exactly one of auto, max_metric_calls, max_full_evals must be set."
        )
    if auto is not None and (
        type(auto) is not str or auto not in {"light", "medium", "heavy"}
    ):
        raise ValueError("auto must be one of: light, medium, heavy")
    if max_metric_calls is not None and type(max_metric_calls) is not int:
        raise ValueError("max_metric_calls must be an integer")
    if max_full_evals is not None and type(max_full_evals) is not int:
        raise ValueError("max_full_evals must be an integer")
    if max_metric_calls is not None and max_metric_calls < 1:
        raise ValueError("max_metric_calls must be >= 1")
    if max_full_evals is not None and max_full_evals < 1:
        raise ValueError("max_full_evals must be >= 1")
    if config.is_multi_proposal and max_metric_calls is None:
        raise ValueError(
            "multi-proposal GEPA requires explicit max_metric_calls; auto and "
            "max_full_evals do not account for proposal multiplicity"
        )


def validate_num_threads(num_threads: int) -> None:
    if type(num_threads) is not int:
        raise ValueError("num_threads must be an integer")
    if not 1 <= num_threads <= 32:
        raise ValueError("num_threads must be between 1 and 32")


class _GEPAReflectionProviderAbort(BaseException):
    def __init__(self, error: Exception) -> None:
        super().__init__(type(error).__name__)
        self.error = error


class TerminalGEPAReflectionLM:
    """Make typed reflection-provider failures escape GEPA's broad fallback."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._delegate(*args, **kwargs)
        except Exception as exc:
            raise _GEPAReflectionProviderAbort(exc) from None


def compile_with_terminal_reflection_effects(gepa: Any, **kwargs: Any) -> Any:
    try:
        return gepa.compile(**kwargs)
    except _GEPAReflectionProviderAbort as abort:
        raise abort.error from None


@dataclass
class GEPAReceiptCallback:
    """Count bounded lifecycle events without retaining event payloads."""

    proposal_starts: int = 0
    proposal_ends: int = 0
    candidates_accepted: int = 0
    candidates_rejected: int = 0
    budget_updates: int = 0
    continuing_errors: int = 0

    def on_proposal_start(self, event: object) -> None:
        del event
        self.proposal_starts += 1

    def on_proposal_end(self, event: object) -> None:
        del event
        self.proposal_ends += 1

    def on_candidate_accepted(self, event: object) -> None:
        del event
        self.candidates_accepted += 1

    def on_candidate_rejected(self, event: object) -> None:
        del event
        self.candidates_rejected += 1

    def on_budget_updated(self, event: object) -> None:
        del event
        self.budget_updates += 1

    def on_error(self, event: dict[str, object]) -> None:
        if event.get("will_continue") is True:
            self.continuing_errors += 1

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": "dspx-gepa-event-counts-v1",
            "proposal_starts": self.proposal_starts,
            "proposal_ends": self.proposal_ends,
            "candidates_accepted": self.candidates_accepted,
            "candidates_rejected": self.candidates_rejected,
            "budget_updates": self.budget_updates,
            "continuing_errors": self.continuing_errors,
            "event_payloads_retained": False,
        }


def detach_gepa_run_stats(
    compiled: Any, *, event_counts: dict[str, object]
) -> dict[str, object]:
    """Detach DSPy's detailed result and return a bounded receipt summary."""

    import hashlib
    import json

    details = getattr(compiled, "detailed_results", None)
    if details is None:
        raise RuntimeError("GEPA detailed results are required for receipt evidence")

    candidates = list(getattr(details, "candidates", []) or [])
    parents = list(getattr(details, "parents", []) or [])
    discovery_counts = list(getattr(details, "discovery_eval_counts", []) or [])
    scores = list(getattr(details, "val_aggregate_scores", []) or [])
    best_index = getattr(details, "best_idx", None) if scores else None
    best_score = (
        float(scores[best_index])
        if isinstance(best_index, int) and 0 <= best_index < len(scores)
        else None
    )

    def digest(value: object) -> str:
        payload = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    candidate_components = getattr(details, "_candidate_components", None)
    if not callable(candidate_components):
        raise RuntimeError("GEPA candidate component hashing is unavailable")
    candidate_hashes = [
        digest(candidate_components(candidate)) for candidate in candidates
    ]
    retained_count = min(len(candidates), _MAX_RECEIPT_CANDIDATES)
    truncated = len(candidates) > retained_count

    total_metric_calls = getattr(details, "total_metric_calls", None)
    num_full_val_evals = getattr(details, "num_full_val_evals", None)
    summary: dict[str, object] = {
        "schema_version": "dspx-gepa-run-stats-v1",
        "candidate_count": len(candidates),
        "best_candidate_index": best_index,
        "best_validation_score": best_score,
        "total_metric_calls": total_metric_calls,
        "num_full_val_evals": num_full_val_evals,
        "retained_candidate_count": retained_count,
        "candidate_summary_truncated": truncated,
        "candidate_component_sha256": candidate_hashes[:retained_count],
        "parents": parents[:retained_count],
        "discovery_eval_counts": discovery_counts[:retained_count],
        "validation_scores": scores[:retained_count],
        "parents_sha256": digest(parents),
        "discovery_eval_counts_sha256": digest(discovery_counts),
        "validation_scores_sha256": digest(scores),
        "event_counts": dict(event_counts),
        "raw_detailed_result_candidates_or_outputs_retained": False,
    }
    delattr(compiled, "detailed_results")
    return summary
