from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProviderCapabilities(BaseModel):
    """Describes what a provider supports for capability-aware adapters.

    Used by:
    - Template adapter for parse_mode auto-selection
    - MultiProviderLM for aggregate capability reporting
    - Services for provider-aware behavior selection
    """

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
    structured_output_format: Literal["json", "xml", "none"] = Field(
        default="none",
        description="Preferred structured output format for this provider. "
        "Used by template adapter for parse_mode auto-selection.",
    )

    # Future capability extensions can be added as optional fields
    # to maintain backward compatibility
    supports_vision: bool = Field(
        default=False, description="Whether provider can process images"
    )
    supports_audio: bool = Field(
        default=False, description="Whether provider can process audio"
    )
