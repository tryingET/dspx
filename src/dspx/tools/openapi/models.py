from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class OpenAPIOperationInfo(BaseModel):
    operation_id: str
    method: str
    path: str
    server: Optional[str] = None
    tags: List[str] = []
    summary: Optional[str] = None
    parameters: List[Dict[str, Any]] = []
    requestBody: Optional[Dict[str, Any]] = None
    responses: Dict[str, Any] = {}
