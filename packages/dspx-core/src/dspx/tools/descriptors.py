# summary: "Defines typed descriptors for builtin and OpenAPI-backed DSPx tools."
# read_when:
#   - "Changing tool capability metadata or OpenAPI descriptor fields."

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel
from dspx.tools.openapi.models import OpenAPIOperationInfo


class ToolDescriptor(BaseModel):
    name: str
    capabilities: List[str] = []
    description: Optional[str] = None
    kind: str = "builtin"  # builtin|openapi|other
    openapi: Optional[OpenAPIOperationInfo] = None
