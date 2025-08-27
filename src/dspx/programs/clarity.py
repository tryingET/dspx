from __future__ import annotations

import dspy


POLICY = (
    "Apply CLARITY: Constraints-first; Learn causal structure and uncertainty; "
    "Abduce multiple hypotheses; Robust-plan for worst-case and expected value; "
    "Intervene with safe, reversible experiments; Trace decisions with provenance and counterfactuals; "
    "Yield outcome and regret. Lexicographic: Safety > Risk > Performance."
)


class _ConstraintsSig(dspy.Signature):
    instruction: str
    input: str
    constraints: str


class _LearnSig(dspy.Signature):
    constraints: str
    input: str
    learnings: str


class _AbduceSig(dspy.Signature):
    constraints: str
    learnings: str
    input: str
    hypotheses: str


class _PlanSig(dspy.Signature):
    constraints: str
    learnings: str
    hypotheses: str
    input: str
    plan: str


class _InterveneSig(dspy.Signature):
    constraints: str
    plan: str
    input: str
    intervention: str


class _TraceSig(dspy.Signature):
    constraints: str
    learnings: str
    hypotheses: str
    plan: str
    intervention: str
    input: str
    trace: str


class _YieldSig(dspy.Signature):
    constraints: str
    learnings: str
    hypotheses: str
    plan: str
    intervention: str
    trace: str
    input: str
    yield_output: str


class _DecisionSig(dspy.Signature):
    constraints: str
    learnings: str
    hypotheses: str
    plan: str
    input: str
    decision: str


def _decorate(instr: str) -> str:
    # Append policy once so it influences each phase consistently.
    return f"{instr} | {POLICY}"


class ClarityStep(dspy.Module):
    """A multi-phase CLARITY step: returns a structured outcome.

    Fields available on the return Prediction: constraints, learnings, hypotheses,
    plan, intervention, trace, yield_output.
    """

    def __init__(self, *, use_cot: bool = True):
        super().__init__()
        P = dspy.ChainOfThought if use_cot else dspy.Predict
        self.m_constraints = P(_ConstraintsSig)
        self.m_learn = P(_LearnSig)
        self.m_abduce = P(_AbduceSig)
        self.m_plan = P(_PlanSig)
        self.m_intervene = P(_InterveneSig)
        self.m_trace = P(_TraceSig)
        self.m_yield = P(_YieldSig)

    def forward(self, instruction: str, input: str) -> dspy.Prediction:
        instr = _decorate(instruction)
        c = self.m_constraints(instruction=instr, input=input)
        learn = self.m_learn(constraints=c.constraints, input=input)
        abd = self.m_abduce(constraints=c.constraints, learnings=learn.learnings, input=input)
        plan = self.m_plan(constraints=c.constraints, learnings=learn.learnings, hypotheses=abd.hypotheses, input=input)
        inter = self.m_intervene(constraints=c.constraints, plan=plan.plan, input=input)
        tr = self.m_trace(constraints=c.constraints, learnings=learn.learnings, hypotheses=abd.hypotheses, plan=plan.plan, intervention=inter.intervention, input=input)
        y = self.m_yield(constraints=c.constraints, learnings=learn.learnings, hypotheses=abd.hypotheses, plan=plan.plan, intervention=inter.intervention, trace=tr.trace, input=input)
        return dspy.Prediction(
            constraints=getattr(c, "constraints", ""),
            learnings=getattr(learn, "learnings", ""),
            hypotheses=getattr(abd, "hypotheses", ""),
            plan=getattr(plan, "plan", ""),
            intervention=getattr(inter, "intervention", ""),
            trace=getattr(tr, "trace", ""),
            yield_output=getattr(y, "yield_output", str(y)),
        )


class ClarityDecision(dspy.Module):
    """A CLARITY-informed decision. Returns a short branch label in `decision`."""

    def __init__(self, *, use_cot: bool = True):
        super().__init__()
        self.step = ClarityStep(use_cot=use_cot)
        P = dspy.ChainOfThought if use_cot else dspy.Predict
        self.decide = P(_DecisionSig)

    def forward(self, instruction: str, input: str) -> dspy.Prediction:
        s = self.step(instruction=instruction, input=input)
        pred = self.decide(
            constraints=s.constraints,
            learnings=s.learnings,
            hypotheses=s.hypotheses,
            plan=s.plan,
            input=input,
        )
        return dspy.Prediction(decision=getattr(pred, "decision", str(pred)))

