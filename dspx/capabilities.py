from __future__ import annotations

from pydantic import BaseModel


class ProviderCapabilities(BaseModel):
    supports_tools: bool = False
    code_exec: bool = True
    json_mode: bool = False
    multi_turn: bool = True

