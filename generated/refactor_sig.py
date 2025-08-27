import dspy

class EchoText(dspy.Signature):
    """Creates a minimal interface that accepts a text string and returns the exact same text unchanged."""

    text: str = dspy.InputField(desc="The input text to be echoed back verbatim")
    echoed_text: str = dspy.OutputField(desc="The output text identical to the input text")