from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


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
    body: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout: Optional[float] = None


class OpenAPICallResult(BaseModel):
    status_code: int
    body: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    raw_text: Optional[str] = None


# --- Codegen DTOs ---


class CodegenRequest(BaseModel):
    spec: str
    language: Optional[str] = None
    template_version: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)


class CodegenResult(BaseModel):
    code: str
    language: Optional[str] = None
    raw_text: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
