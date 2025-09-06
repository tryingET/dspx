import dspy
from typing import Literal


class TextSentimentClassifier(dspy.Signature):
    """Classify the sentiment of an input text as positive, negative, or neutral, and return the predicted label along with a confidence score between 0 and 1."""

    text: str = dspy.InputField(desc="The input text to analyze for sentiment")
    sentiment_label: Literal["positive", "negative", "neutral"] = dspy.OutputField(
        desc="Predicted sentiment class for the input text"
    )
    confidence: float = dspy.OutputField(
        desc="Model confidence in the predicted sentiment label (0.0–1.0)"
    )
