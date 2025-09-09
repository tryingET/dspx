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
