import dspy

class EchoSmoke(dspy.Signature):
    """Create a minimal echo signature for smoke testing that takes a string prompt and returns the same string, confirming the pipeline and I/O wiring work."""

    prompt: str = dspy.InputField(desc="Arbitrary input text to be echoed back")
    echo: str = dspy.OutputField(desc="The exact same text returned for verification")