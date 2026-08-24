---
summary: "Exact DSPy 3.3.0 / GEPA 0.1.4 compatibility-override transition contract and bounded support posture."
read_when:
  - "Before changing the GEPA resolver override or claiming GEPA 0.1.4 compatibility."
  - "Before exposing GEPA 0.1.4 proposal, reflection, cost, callback, or checkpoint features in DSPx."
type: "evidence"
---

# DSPy 3.3.0 / GEPA 0.1.4 transition

AK-4798 transitions the DSPx workspace from GEPA 0.1.1 to GEPA 0.1.4 as an explicit, tested compatibility override. It does not yet expose GEPA 0.1.4's new optimization controls as DSPx product configuration.

## Dependency truth

DSPy 3.3.0 declares `gepa[dspy]==0.1.1`. A routine `uv lock --upgrade-package gepa` therefore retains 0.1.1. DSPx deliberately records this mismatch instead of presenting 0.1.4 as ordinary upstream-supported resolution:

```toml
[tool.uv]
override-dependencies = ["gepa[dspy]==0.1.4"]
```

The repository lock is the controlled local deployment contract. Standalone installation of the published `dspx-core` wheel without the repository lock or an equivalent reviewed override can still resolve DSPy's declared GEPA 0.1.1 requirement. This transition is not evidence that DSPy upstream supports the combination in package metadata.

Historical GEPA 0.1.1 evidence documents remain immutable observations of their exact environment. They are not rewritten as 0.1.4 evidence.

## Accepted compatibility surface

The transition gate must prove all of the following under CPython 3.13, DSPy/DSPy-AI 3.3.0, and GEPA 0.1.4:

- the explicit override and installed versions match the declared matrix;
- DSPy's `dspy.teleprompt.gepa.GEPA` adapter imports and executes;
- the real credential-free stub path compiles, saves, pickle-loads, and predicts;
- metric hooks, MLflow tracing, provider restoration/closure, refinement classification, and candidate hash checks remain passing;
- optimizer manifests record both `dspy_version` and `gepa_version`;
- repository validation and packaging use the frozen lock.

The compatibility override remains reversible. A future DSPy release whose metadata supports GEPA 0.1.4 must remove the override through a separate dependency transaction rather than silently retaining it.

## Available but not activated

GEPA 0.1.4 makes these upstream surfaces available for a separately scoped usefulness transaction:

- `ReflectionLM`, `BatchReflectionLM`, and `ReflectionProposal`;
- `SingleMutationSampling`, `SameParentSampling`, `IndependentSampling`, and `PxNSampling`;
- `AllImprovements`, `BestImprovement`, and `TopKImprovements`;
- reflection-cost limits, callbacks, acceptance criteria, tracking, and checkpoint-state improvements.

Availability is not DSPx integration. DSPy's 3.3.0 wrapper owns proposal construction and exposes only a generic `gepa_kwargs` passthrough for many standalone controls. DSPx must not advertise a capability until tests show that it remains inside typed provider, effect, budget, receipt, and no-replay boundaries.

## Nonclaims

This transition does not establish:

- semantic improvement, answer quality, or version causality;
- safe parallel model effects, retries, or cancellation;
- credentialed or live-provider compatibility;
- fresh-process materialization, replay, or comparison of real GEPA 0.1.4 output;
- non-pickle serialization or trusted-local production admission;
- routing, promotion, publication, release, or activation authority.

Whole-program `save_program=True` output still requires `dspy.load(..., allow_pickle=True)`. It remains compatibility-only and excluded from the trusted-local production matrix.
