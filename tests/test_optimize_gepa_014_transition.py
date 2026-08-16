# summary: "Pins the explicit DSPy 3.3.0 / GEPA 0.1.4 compatibility override and capability surface."
# read_when:
#   - "Changing the GEPA dependency override or adopting GEPA 0.1.4 capabilities."

from __future__ import annotations

import inspect
from importlib.metadata import requires, version
from pathlib import Path
import tomllib


def test_gepa_014_override_is_explicit_and_active() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["tool"]["uv"]["override-dependencies"] == ["gepa[dspy]==0.1.4"]
    assert version("dspy") == "3.3.0"
    assert version("gepa") == "0.1.4"

    dspy_gepa_requirements = [
        requirement
        for requirement in requires("dspy") or ()
        if requirement.lower().startswith("gepa")
    ]
    assert dspy_gepa_requirements == ["gepa[dspy]==0.1.1"]


def test_gepa_014_usefulness_surface_is_available_but_not_implicitly_enabled() -> None:
    from gepa import optimize
    from gepa.proposer.reflective_mutation.reflection_lm import (
        BatchReflectionLM,
        ReflectionLM,
        ReflectionProposal,
    )
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

    parameters = inspect.signature(optimize).parameters
    assert {
        "max_reflection_cost",
        "callbacks",
        "sampling_strategy",
        "selection_strategy",
        "reflection_strategy",
        "acceptance_criterion",
    } <= parameters.keys()

    assert SameParentSampling(2).n == 2
    assert IndependentSampling(2).n == 2
    assert PxNSampling(2, 3).p == 2
    assert PxNSampling(2, 3).n == 3
    assert SingleMutationSampling is not None
    assert AllImprovements is not None
    assert BestImprovement is not None
    assert TopKImprovements(2).k == 2
    assert ReflectionLM is not None
    assert BatchReflectionLM is not None
    assert ReflectionProposal(new_texts={"instruction": "bounded"}).new_texts == {
        "instruction": "bounded"
    }
