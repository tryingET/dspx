from __future__ import annotations

import dspy


POLICY = (
    "Apply CLARITY: Constraints-first; Learn causal structure and uncertainty; "
    "Abduce multiple hypotheses; Robust-plan for worst-case and expected value; "
    "Intervene with safe, reversible experiments; Trace decisions with provenance and counterfactuals; "
    "Yield outcome and regret. Lexicographic: Safety > Risk > Performance."
)


class _ConstraintsSig(dspy.Signature):
    instruction: str = dspy.InputField(
        desc="High-level step instruction with policy context"
    )
    input: str = dspy.InputField(desc="Primary input text for the step")
    constraints: str = dspy.OutputField(
        desc="Hard requirements and must-not-violate rules"
    )


class _LearnSig(dspy.Signature):
    constraints: str = dspy.InputField(desc="Constraints carried from previous phase")
    input: str = dspy.InputField(desc="Same input text for continuity")
    learnings: str = dspy.OutputField(desc="Key observations, facts, and uncertainties")


class _AbduceSig(dspy.Signature):
    constraints: str = dspy.InputField(desc="Constraints context")
    learnings: str = dspy.InputField(desc="Learn phase findings")
    input: str = dspy.InputField(desc="Reference input")
    hypotheses: str = dspy.OutputField(
        desc="Multiple candidate hypotheses with rationale"
    )


class _PlanSig(dspy.Signature):
    constraints: str = dspy.InputField(desc="Constraints to satisfy")
    learnings: str = dspy.InputField(desc="Learnings to leverage")
    hypotheses: str = dspy.InputField(desc="Hypotheses to consider")
    input: str = dspy.InputField(desc="Original input for grounding")
    plan: str = dspy.OutputField(
        desc="Robust plan addressing constraints and hypotheses"
    )


class _InterveneSig(dspy.Signature):
    constraints: str = dspy.InputField(desc="Constraints to respect")
    plan: str = dspy.InputField(desc="Plan to execute or test")
    input: str = dspy.InputField(desc="Reference input")
    intervention: str = dspy.OutputField(desc="Safe, reversible intervention proposal")


class _TraceSig(dspy.Signature):
    constraints: str = dspy.InputField(desc="Constraints context")
    learnings: str = dspy.InputField(desc="Learnings context")
    hypotheses: str = dspy.InputField(desc="Hypotheses context")
    plan: str = dspy.InputField(desc="Plan context")
    intervention: str = dspy.InputField(desc="Intervention context")
    input: str = dspy.InputField(desc="Reference input")
    trace: str = dspy.OutputField(
        desc="Decision trace with provenance and counterfactuals"
    )


class _YieldSig(dspy.Signature):
    constraints: str = dspy.InputField(desc="Constraints context")
    learnings: str = dspy.InputField(desc="Learnings context")
    hypotheses: str = dspy.InputField(desc="Hypotheses context")
    plan: str = dspy.InputField(desc="Plan context")
    intervention: str = dspy.InputField(desc="Intervention context")
    trace: str = dspy.InputField(desc="Trace context")
    input: str = dspy.InputField(desc="Reference input")
    yield_output: str = dspy.OutputField(desc="Outcome summary and regret")


class _DecisionSig(dspy.Signature):
    constraints: str = dspy.InputField(desc="Constraints context")
    learnings: str = dspy.InputField(desc="Learnings context")
    hypotheses: str = dspy.InputField(desc="Hypotheses context")
    plan: str = dspy.InputField(desc="Plan context")
    input: str = dspy.InputField(desc="Reference input")
    decision: str = dspy.OutputField(desc="Chosen branch label")


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
        abd = self.m_abduce(
            constraints=c.constraints, learnings=learn.learnings, input=input
        )
        plan = self.m_plan(
            constraints=c.constraints,
            learnings=learn.learnings,
            hypotheses=abd.hypotheses,
            input=input,
        )
        inter = self.m_intervene(constraints=c.constraints, plan=plan.plan, input=input)
        tr = self.m_trace(
            constraints=c.constraints,
            learnings=learn.learnings,
            hypotheses=abd.hypotheses,
            plan=plan.plan,
            intervention=inter.intervention,
            input=input,
        )
        y = self.m_yield(
            constraints=c.constraints,
            learnings=learn.learnings,
            hypotheses=abd.hypotheses,
            plan=plan.plan,
            intervention=inter.intervention,
            trace=tr.trace,
            input=input,
        )
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
