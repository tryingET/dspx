import dspy
from typing import Optional


class ExtractPersonNames(dspy.Signature):
    """Extract person names mentioned in an input text string and return a unique, ordered list of detected names."""

    text: str = dspy.InputField(
        desc="Raw input text from which to extract person names"
    )
    language: Optional[str] = dspy.InputField(
        desc="Optional ISO language hint (e.g., 'en') to improve extraction"
    )
    person_names: list[str] = dspy.OutputField(
        desc="Unique list of detected person names in reading order"
    )
