import dspy
from typing import Literal


class SentimentWithConfidence(dspy.Signature):
    """Classify the sentiment of a given text as positive, negative, or neutral, and provide a confidence score for the classification."""

    text: str = dspy.InputField(desc="The input text to analyze for sentiment.")
    sentiment_label: Literal["positive", "negative", "neutral"] = dspy.OutputField(
        desc="The predicted sentiment category for the input text."
    )
    confidence: float = dspy.OutputField(
        desc="Model confidence in the predicted sentiment label as a value between 0.0 and 1.0."
    )
