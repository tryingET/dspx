from __future__ import annotations

from typing import Dict

import dspy


class SixESignature(dspy.Signature):
    """Extract the Initial 6 Elements (6E) from context text.

    Fields:
    - constraints: Hard rules ("We must...")
    - boundaries: Responsibility boundaries ("Ends here...")
    - edges: Integration points ("Happens at...")
    - assumptions: Accepted truths ("We assume...")
    - dependencies: Preconditions ("Requires...")
    - exceptions: Guarded deviations ("Allowed unless/until...")
    """

    # Inputs
    context: str = dspy.InputField(desc="Source text (or JSON) to extract 6E from.")

    # Outputs
    constraints: str = dspy.OutputField(desc="Hard rules: 'We must…'")
    boundaries: str = dspy.OutputField(desc="Responsibility boundaries: 'Ends here…'")
    edges: str = dspy.OutputField(desc="Integration points: 'Happens at…'")
    assumptions: str = dspy.OutputField(desc="Accepted truths: 'We assume…'")
    dependencies: str = dspy.OutputField(desc="Preconditions: 'Requires…'")
    exceptions: str = dspy.OutputField(desc="Guarded deviations: 'Allowed unless/until…'")


class SixEExtractor(dspy.Module):
    """CoT extractor for 6E, returns a structured prediction."""

    def __init__(self, *, use_cot: bool = True):
        super().__init__()
        P = dspy.ChainOfThought if use_cot else dspy.Predict
        self.extract = P(SixESignature)

    def forward(self, context: str) -> dspy.Prediction:
        pred = self.extract(context=context)
        return dspy.Prediction(
            constraints=getattr(pred, "constraints", ""),
            boundaries=getattr(pred, "boundaries", ""),
            edges=getattr(pred, "edges", ""),
            assumptions=getattr(pred, "assumptions", ""),
            dependencies=getattr(pred, "dependencies", ""),
            exceptions=getattr(pred, "exceptions", ""),
        )


def to_dict(pred: dspy.Prediction) -> Dict[str, str]:
    return dict(
        constraints=getattr(pred, "constraints", ""),
        boundaries=getattr(pred, "boundaries", ""),
        edges=getattr(pred, "edges", ""),
        assumptions=getattr(pred, "assumptions", ""),
        dependencies=getattr(pred, "dependencies", ""),
        exceptions=getattr(pred, "exceptions", ""),
    )


def to_summary(pred: dspy.Prediction) -> str:
    parts = []
    def add(label: str, val: str) -> None:
        v = (val or "").strip()
        if v:
            parts.append(f"{label}: {v}")
    add("Constraints", getattr(pred, "constraints", ""))
    add("Boundaries", getattr(pred, "boundaries", ""))
    add("Edges", getattr(pred, "edges", ""))
    add("Assumptions", getattr(pred, "assumptions", ""))
    add("Dependencies", getattr(pred, "dependencies", ""))
    add("Exceptions", getattr(pred, "exceptions", ""))
    return " \n".join(parts)


class SixEWriter(dspy.Module):
    """Generate a 6E document draft from intent + context.

    Produces a compact JSON-like document with keys:
    constraints, boundaries, edges, assumptions, dependencies, exceptions.
    """

    def __init__(self, *, use_cot: bool = True):
        super().__init__()
        P = dspy.ChainOfThought if use_cot else dspy.Predict
        self.write = P("intent, context -> sixe_doc")

    def forward(self, intent: str, context: str) -> dspy.Prediction:
        instruction = (
            "Write a concise 6E JSON object with keys: "
            "constraints, boundaries, edges, assumptions, dependencies, exceptions. "
            "Keep values short bullet-like strings."
        )
        prompt = f"Instruction: {instruction}\nIntent: {intent}\nContext:\n{context}"
        pred = self.write(intent=intent, context=prompt)
        return dspy.Prediction(sixe_doc=getattr(pred, "sixe_doc", str(pred)))
