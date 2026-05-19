from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


# --- Template Adapter DTOs ---


class TemplateMessage(BaseModel):
    """A single message template for dspy-template-adapter integration.

    Supports standard roles plus special directives:
    - demos: Inject few-shot demonstrations with optional templates
    - history: Inject conversation history
    """

    model_config = ConfigDict(
        populate_by_name=True
    )  # Allow both `user` and `user_template`

    role: Literal["system", "user", "assistant", "demos", "history"]
    content: Optional[str] = Field(
        default=None,
        description="Template content. Required except for demos/history directives.",
    )
    # For demos directive customization
    user_template: Optional[str] = Field(
        default=None,
        alias="user",
        description="Custom template for demo user messages",
    )
    assistant_template: Optional[str] = Field(
        default=None,
        alias="assistant",
        description="Custom template for demo assistant messages",
    )


class TemplateAdapterConfig(BaseModel):
    """Configuration for dspy-template-adapter integration.

    Provides exact prompt fidelity with user-defined message templates,
    provider-aware output format selection, and optimizer compatibility.

    Example:
        config = TemplateAdapterConfig(
            messages=[
                TemplateMessage(role="system", content="{instruction}"),
                TemplateMessage(role="user", content="{inputs(style='yaml')}"),
            ],
            parse_mode="json",
        )
    """

    model_config = ConfigDict(
        extra="allow"
    )  # Allow extra fields for future extensibility

    messages: List[TemplateMessage] = Field(
        default_factory=lambda: [
            TemplateMessage(role="system", content="{instruction}"),
            TemplateMessage(role="user", content="{inputs(style='yaml')}"),
        ],
        description="Message templates for the adapter",
    )

    parse_mode: Literal["json", "xml", "full_text", "chat", "auto"] = Field(
        default="auto",
        description=(
            "Output parsing mode. "
            "'auto' selects based on provider capabilities (json for json_mode providers, "
            "xml for Claude, json otherwise). "
            "'chat' falls back to DSPy's ChatAdapter parsing."
        ),
    )

    custom_parse_fn: Optional[str] = Field(
        default=None,
        description=(
            "Import path to custom parse function with signature: "
            "(signature, completion) -> dict. "
            "Example: 'myapp.parsing.custom_json_parser'"
        ),
    )

    register_helpers: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map of helper name -> import path for custom template functions. "
            "Example: {'format_priority': 'myapp.template_helpers.format_priority'}"
        ),
    )


# --- Core DTOs ---


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Any


class LMRequest(BaseModel):
    prompt: Optional[str] = None
    messages: Optional[List[Message]] = None
    options: dict[str, Any] = Field(default_factory=dict)


class LMResponse(BaseModel):
    outputs: List[str]
    model: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    raw: Optional[dict[str, Any]] = None


# --- v1 DTOs for services (contracts) ---


class SignatureGenRequest(BaseModel):
    """Request to generate a DSPy signature class from a prompt.

    Minimal fields for Phase 1; can be extended/versioned later.
    """

    prompt: str
    use_cot: bool = Field(
        default=False, description="Prefer chain-of-thought when available"
    )
    template_version: Optional[str] = Field(
        default=None, description="Template version tag"
    )
    options: Dict[str, Any] = Field(default_factory=dict)

    # Template adapter integration (opt-in)
    template_adapter: Optional[TemplateAdapterConfig] = Field(
        default=None,
        description=(
            "If provided, use dspy-template-adapter for exact prompt fidelity. "
            "Requires optional dependency: pip install dspx-core[templates]"
        ),
    )


class SignatureGenResult(BaseModel):
    """Result of signature generation, returning code and metadata."""

    code: str
    signature_name: Optional[str] = None
    task_description: Optional[str] = None
    fields: Optional[List[Dict[str, Any]]] = None
    reasoning: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModuleSpec(BaseModel):
    """Specification for generating a reusable DSPy Module skeleton."""

    name: str
    description: Optional[str] = None
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    options: Dict[str, Any] = Field(default_factory=dict)


class ModuleArtifact(BaseModel):
    """Generated module artifact (e.g., Python code and metadata)."""

    name: str
    code: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProgramGraphSpec(BaseModel):
    """Specification of a program graph, typically from Mermaid."""

    mermaid: Optional[str] = None
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    name: Optional[str] = None


class ProgramArtifact(BaseModel):
    """Generated program artifact details (paths, code, manifest)."""

    name: str
    files: Dict[str, str] = Field(
        default_factory=dict, description="Mapping of filename -> content or path"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OpenAPICallRequest(BaseModel):
    """Skeleton for an OpenAPI operation call."""

    operation_id: str
    method: Optional[str] = None
    server: Optional[str] = None
    path: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    body: Any = None
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout: Optional[float] = None


class OpenAPICallResult(BaseModel):
    status_code: int
    body: Any = None
    headers: Dict[str, str] = Field(default_factory=dict)
    raw_text: Optional[str] = None


# --- Codegen DTOs ---


class CodegenRequest(BaseModel):
    spec: str
    language: Optional[str] = None
    template_version: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)

    # Template adapter integration (opt-in)
    template_adapter: Optional[TemplateAdapterConfig] = Field(
        default=None,
        description=(
            "If provided, use dspy-template-adapter for exact prompt fidelity. "
            "Requires optional dependency: pip install dspx-core[templates]"
        ),
    )


class CodegenResult(BaseModel):
    code: str
    language: Optional[str] = None
    raw_text: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
