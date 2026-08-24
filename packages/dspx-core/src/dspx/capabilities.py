# summary: "Defines the immutable capability model shared by DSPx language-model providers."
# read_when:
#   - "You are declaring provider features or adding capability-aware behavior."

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


# Type alias for structured output format (reusable for type hints)
StructuredOutputFormat: TypeAlias = Literal["json", "xml", "none"]


class ProviderCapabilities(BaseModel):
    """Describes what a provider supports for capability-aware adapters.

    Used by:
    - Template adapter for parse_mode auto-selection
    - Typed provider adapters for pre-effect capability checks
    - Services for provider-aware behavior selection

    Note: This model is frozen to prevent accidental mutation at runtime.
    """

    model_config = ConfigDict(frozen=True)

    supports_tools: bool = Field(
        default=False, description="Whether provider supports function/tool calling"
    )
    code_exec: bool = Field(
        default=True, description="Whether provider can execute code locally"
    )
    json_mode: bool = Field(
        default=False, description="Whether provider guarantees valid JSON output"
    )
    multi_turn: bool = Field(
        default=True, description="Whether provider supports conversation history"
    )
    structured_output_format: StructuredOutputFormat = Field(
        default="none",
        description="Preferred structured output format for this provider. "
        "Used by template adapter for parse_mode auto-selection.",
    )

    # Future capability extensions (optional, maintain backward compatibility)
    supports_vision: bool = Field(
        default=False, description="Whether provider can process images"
    )
    supports_audio: bool = Field(
        default=False, description="Whether provider can process audio"
    )
