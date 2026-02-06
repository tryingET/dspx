from __future__ import annotations

import re


MANAGED_START = "<!-- DSPX_MANAGED_START -->"
MANAGED_END = "<!-- DSPX_MANAGED_END -->"


def build_managed_block(
    *,
    workorder_id: str,
    fingerprint: str,
    system_definition_card_path: str,
    body_lines: list[str] | None = None,
) -> str:
    body_lines = body_lines or []
    lines = [
        MANAGED_START,
        "Context",
        f"- WorkOrder: {workorder_id}",
        f"- Fingerprint: {fingerprint}",
        f"- 4D: {system_definition_card_path}",
        f"<!-- DSPX_FINGERPRINT: {fingerprint} -->",
        MANAGED_END,
    ]
    if body_lines:
        lines.extend(body_lines)
    return "\n".join(lines)


def upsert_managed_block(existing: str, new_block: str) -> str:
    if MANAGED_START in existing and MANAGED_END in existing:
        pat = re.compile(
            re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END),
            flags=re.DOTALL,
        )
        return pat.sub(new_block, existing, count=1)
    return new_block + "\n\n" + existing.lstrip()
