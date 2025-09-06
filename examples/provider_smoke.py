import dspy


class EchoText(dspy.Signature):
    """Defines a minimal signature that echoes a given text input back as output unchanged."""

    text: str = dspy.InputField(desc="The text to be echoed back")
    echoed_text: str = dspy.OutputField(
        desc="The echoed result identical to the input text"
    )
