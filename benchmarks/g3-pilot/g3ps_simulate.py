"""G3 SUCCESSOR joint-criterion Monte Carlo (AK 5095; decision 138 REV 3).

Simulates the operating characteristics of the FROZEN joint criterion
(primary pooled exact McNemar + floored template guard + family rule)
under clustered data-generating models, per review observes N2/N6:

  scenarios
  - design point: 12 templates x 6 pairs, per-template stochastic-task mix,
    discordance p_d ~ 0.40, evidence-only share pi ~ 0.75, deterministic-task
    fraction ~ 0.5 (v3b observables; recorded as ASSUMPTIONS)
  - concentration (adversarial): all signal in 1, 2, 3 templates —
    must be rejected or rendered INCONCLUSIVE by the floored guard
  - at-floor: exactly 4 discordant templates (review N2)
  - clustered null: no arm effect, template-level ICC > 0 (type-I check)
  - null edge: no effect, independent pairs (empirical size)

Outputs: empirical PASS / FAIL / INCONCLUSIVE rates + empirical size at the
null and the design-point power. Recorded verbatim in the freeze manifest.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

N_TEMPLATES = 12
PAIRS_PER_TEMPLATE = 6  # 3 instances x 2 families
N_PAIRS = N_TEMPLATES * PAIRS_PER_TEMPLATE
SEED = 20260826
N_SIM = 4000

# criterion constants (REV 3 sec 4)
ALPHA = 0.05
MIN_DISCORDANT_TEMPLATES = 4
COMPLETION = 1.0  # simulation assumes full completion (criterion (v) is operational)


def exact_mcnemar_p(n_e_only: int, n_s_only: int) -> float:
    """Two-sided exact binomial (sign) test on discordant pairs."""
    n = n_e_only + n_s_only
    if n == 0:
        return 1.0
    k = min(n_e_only, n_s_only)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def criterion(evidence: list[int], static: list[int], template: list[int],
              family: list[int]) -> dict:
    n_e_only = sum(1 for e, s in zip(evidence, static) if e == 1 and s == 0)
    n_s_only = sum(1 for e, s in zip(evidence, static) if e == 0 and s == 1)
    p = exact_mcnemar_p(n_e_only, n_s_only)
    # template guard
    tmpl_e: dict[int, int] = {}
    tmpl_s: dict[int, int] = {}
    for e, s, t in zip(evidence, static, template):
        tmpl_e[t] = tmpl_e.get(t, 0) + (1 if e == 1 and s == 0 else 0)
        tmpl_s[t] = tmpl_s.get(t, 0) + (1 if e == 0 and s == 1 else 0)
    discordant_templates = [t for t in tmpl_e if tmpl_e[t] > 0 or tmpl_s[t] > 0]
    d = len(discordant_templates)
    e_dominant = sum(1 for t in discordant_templates if tmpl_e[t] > tmpl_s[t])
    s_dominant = sum(1 for t in discordant_templates if tmpl_s[t] > tmpl_e[t])
    guard_pass = d >= MIN_DISCORDANT_TEMPLATES and e_dominant > d / 2
    guard_fail = d >= MIN_DISCORDANT_TEMPLATES and s_dominant > d / 2
    # family rule
    fam_ok = True
    for f in (0, 1):
        idx = [i for i, ff in enumerate(family) if ff == f]
        if not idx:
            continue
        ev = sum(evidence[i] for i in idx) / len(idx)
        st = sum(static[i] for i in idx) / len(idx)
        if ev < st - 1e-12:
            fam_ok = False
    if p < ALPHA and guard_pass and fam_ok and n_e_only > n_s_only:
        return "PASS"
    if p < ALPHA and guard_fail and fam_ok and n_s_only > n_e_only:
        return "FAIL"
    if d < MIN_DISCORDANT_TEMPLATES and p < ALPHA:
        return "INCONCLUSIVE_INSUFFICIENT_TEMPLATE_DISPERSION"
    return "INCONCLUSIVE"


def simulate(scenario: str, seed: int = SEED, n_sim: int = N_SIM) -> dict:
    rng = random.Random(seed)
    outcomes: dict[str, int] = {}
    for _ in range(n_sim):
        evidence: list[int] = []
        static: list[int] = []
        template: list[int] = []
        family: list[int] = []
        tmpl_stochastic = _tmpl_stochastic(rng, scenario)
        for t in range(N_TEMPLATES):
            for inst in range(3):
                for fam in (0, 1):
                    e, s = _draw_pair(rng, scenario, t, tmpl_stochastic)
                    evidence.append(e)
                    static.append(s)
                    template.append(t)
                    family.append(fam)
        v = criterion(evidence, static, template, family)
        outcomes[v] = outcomes.get(v, 0) + 1
    return {k: round(c / n_sim, 4) for k, c in sorted(outcomes.items())}


def _draw_pair(rng: random.Random, scenario: str, t: int, tmpl_stochastic: dict) -> tuple[int, int]:
    """Draw (evidence, static) for one pair.

    Two v3b-calibrated parameterizations are simulated and BOTH disclosed:
    - pair-level calibration: every template stochastic; per-pair
      P(1,0)=0.30, P(0,1)=0.10 (pair discordance 0.40, e-only share 0.75 —
      the v3b observables read at the pair level);
    - template-level calibration: ~50% of templates fully deterministic
      (v3b cross-run stability 5/10), stochastic templates carry the same
      per-pair rates; overall pair discordance then ~0.20.
    Concentration scenarios override both.
    """
    if scenario == "null_independent":
        return (rng.random() < 0.5 and 1 or 0, rng.random() < 0.5 and 1 or 0)
    if scenario == "null_clustered_icc":
        hard = _tmpl_hard(t)
        rate = 0.15 if hard else 0.85
        return (rng.random() < rate and 1 or 0, rng.random() < rate and 1 or 0)
    if scenario.startswith("concentrate_"):
        k = int(scenario.split("_")[1])
        if t >= k:
            r = rng.random()
            return (1 if r < 0.5 else 0, 1 if r < 0.5 else 0)
        return (int(rng.random() < 0.9), int(rng.random() < 0.2))
    if scenario == "at_floor_d4":
        if t >= 4:
            r = rng.random()
            return (1 if r < 0.7 else 0, 1 if r < 0.7 else 0)
        return (int(rng.random() < 0.9), int(rng.random() < 0.2))
    stochastic = tmpl_stochastic.get(t, True)
    if scenario.startswith("design_pair_"):
        stochastic = True
    elif scenario.startswith("design_tmpl_"):
        pass  # use per-template determinism
    if not stochastic:
        both = rng.random() < 0.6
        return (1, 1) if both else (0, 0)
    u = rng.random()
    if u < 0.30:
        return (1, 0)
    if u < 0.40:
        return (0, 1)
    both = rng.random() < 0.5
    return (1, 1) if both else (0, 0)


def _tmpl_stochastic(rng: random.Random, scenario: str) -> dict[int, bool]:
    frac_det = 0.0 if scenario.startswith("design_pair_") else 0.5
    return {t: rng.random() >= frac_det for t in range(N_TEMPLATES)}


def _tmpl_hard(t: int) -> bool:
    key = "hard"
    if key not in _TMPL_HARD_CACHE:
        rng = random.Random(SEED + 7)
        _TMPL_HARD_CACHE[key] = [rng.random() < 0.5 for _ in range(N_TEMPLATES)]
    return _TMPL_HARD_CACHE[key][t]


_TMPL_HARD_CACHE: dict[str, list[bool]] = {}


def main() -> None:
    scenarios = [
        ("null_independent", "null edge: empirical size (independent)"),
        ("null_clustered_icc", "null with template-level clustering (ICC>0)"),
        ("design_pair_level", "design point, PAIR-level calibration (all templates stochastic; pair p_d=0.40, pi=0.75)"),
        ("design_tmpl_level", "design point, TEMPLATE-level calibration (~50% deterministic templates; overall pair p_d~0.20)"),
        ("concentrate_1", "adversarial: all signal in 1 template"),
        ("concentrate_2", "adversarial: signal in 2 templates"),
        ("concentrate_3", "adversarial: signal in 3 templates"),
        ("at_floor_d4", "exactly-at-floor: d=4 discordant templates (N2)"),
    ]
    out = {
        "schema": "dspx.g3ps-joint-criterion-simulation/1",
        "n_sim": N_SIM,
        "seed": SEED,
        "criterion": "pooled exact McNemar p<0.05 + guard(d>=4 & strict e-majority) + family rule + completion",
        "assumptions": [
            "discordance 0.40 and evidence-only share 0.75 are v3b OBSERVABLES at n=1-per-cell",
            "deterministic-task fraction 0.5 estimated from v3b cross-run stability (5/10 identical)",
            "v3/v3b contains NO repeated instances; the cross-run read is wheel-confounded",
            "these parameters are assumptions of the simulation, not measurements of the successor corpus",
        ],
        "results": {},
    }
    for scen, label in scenarios:
        out["results"][scen] = {"label": label, "rates": simulate(scen)}
        print(scen, label, out["results"][scen]["rates"], file=sys.stderr)
    dest = Path(__file__).resolve().parents[2] / "docs/v1-proof/g3ps-simulation.json"
    dest.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out["results"], indent=1))


if __name__ == "__main__":
    main()
