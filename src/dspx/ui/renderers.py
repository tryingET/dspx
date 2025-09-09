from __future__ import annotations

from typing import Dict, Any, List
from dspx.tools.descriptors import ToolDescriptor


def tool_descriptor_to_json(desc: ToolDescriptor) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "name": desc.name,
    }
    if desc.capabilities:
        out["capabilities"] = list(desc.capabilities)
    if desc.description:
        out["description"] = desc.description
    if desc.kind == "openapi" and desc.openapi is not None:
        out.update(
            {
                "openapi": True,
                "method": str(desc.openapi.method or "").upper(),
                "path": desc.openapi.path or "",
                "server": desc.openapi.server or None,
                "tags": list(desc.openapi.tags or []),
                "summary": desc.openapi.summary or None,
            }
        )
    return out


def tool_descriptor_to_list_text(desc: ToolDescriptor) -> str:
    return f"{desc.name} - {desc.description}" if desc.description else desc.name


def tool_descriptor_describe_text(
    desc: ToolDescriptor, examples: List[str] | None = None
) -> str:
    lines: List[str] = [f"name: {desc.name}"]
    if desc.description:
        lines.append(f"description: {desc.description}")
    if desc.capabilities:
        lines.append("capabilities: " + ", ".join(desc.capabilities))
    if desc.kind == "openapi" and desc.openapi is not None:
        lines.append(f"method: {str(desc.openapi.method or '').upper()}")
        lines.append(f"path: {desc.openapi.path or ''}")
        if desc.openapi.server:
            lines.append(f"server: {desc.openapi.server}")
        if desc.openapi.summary:
            lines.append(f"summary: {desc.openapi.summary}")
        if desc.openapi.tags:
            lines.append("tags:")
            for t in desc.openapi.tags:
                lines.append(f"  - {t}")
        # Parameters
        params = desc.openapi.parameters or []
        lines.append("parameters:")
        if params:
            for p in params:
                if isinstance(p, dict):
                    where = str(p.get("in") or "")
                    nm = str(p.get("name") or "")
                    req = bool(p.get("required", False))
                    t = (
                        (p.get("schema") or {}).get("type")
                        if isinstance(p.get("schema"), dict)
                        else None
                    ) or ""
                    lines.append(
                        f"  - {where}:{nm} required={str(req).lower()} type={t}"
                    )
        else:
            lines.append("  - (none)")
        # Request body
        rb = desc.openapi.requestBody
        lines.append("requestBody:")
        if isinstance(rb, dict) and (rb.get("required") or rb.get("schema")):
            req = bool(rb.get("required", False))
            lines.append(f"  required={str(req).lower()}")
        else:
            lines.append("  (none)")
        # Responses summary
        lines.append("responses:")
        resps = desc.openapi.responses or {}
        if isinstance(resps, dict) and resps:
            for code, rd in resps.items():
                try:
                    schema = (rd or {}).get("schema") if isinstance(rd, dict) else None
                    cts = (
                        (rd or {}).get("contentTypes") if isinstance(rd, dict) else None
                    )
                    lines.append(f"  - {code} contentTypes={cts or []}")
                    if isinstance(schema, dict):
                        t = schema.get("type")
                        if t == "object":
                            props = schema.get("properties") or {}
                            reqs = set(schema.get("required") or [])
                            if props:
                                lines.append("    properties:")
                                for nm, ps in props.items():
                                    ty = (ps or {}).get("type", "")
                                    lines.append(
                                        f"      - {nm}: type={ty} required={'true' if nm in reqs else 'false'}"
                                    )
                            else:
                                lines.append("    properties: (none)")
                        else:
                            lines.append(f"    schema.type={t}")
                except Exception:
                    pass
        else:
            lines.append("  (none)")
    if examples:
        lines.append("examples:")
        for ex in examples:
            lines.append(f"  - {ex}")
    return "\n".join(lines)
