import dspy
from typing import Literal, Optional

class EchoViaProviderFlag(dspy.Signature):
    """Create a signature that echoes back the provided text input, optionally prefixed or suffixed based on a provider flag, returning the final echoed message."""

    text: str = dspy.InputField(desc="The text content to echo back")
    provider_flag: Literal['default', 'verbose', 'raw'] = dspy.InputField(desc="Selects echo behavior by provider")
    prefix: Optional[str] = dspy.InputField(desc="Optional string to prepend when provider requires it")
    suffix: Optional[str] = dspy.InputField(desc="Optional string to append when provider requires it")
    echoed_text: str = dspy.OutputField(desc="The final echoed message after applying provider-specific formatting")