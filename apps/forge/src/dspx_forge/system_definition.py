# summary: "Renders a Forge WorkOrder as the Markdown system-definition card written with its plan."
# read_when:
#   - "Changing Forge system-definition card sections or WorkOrder field presentation."

from __future__ import annotations

from dspx_forge.models import WorkOrder


def render_system_definition_card(wo: WorkOrder) -> str:
    # Minimal 4D card; Forge v0 wants this file to exist and be referenced from issues.
    constraints = (
        "\n".join(f"- {c.id}: {c.text}" for c in (wo.constraints or [])) or "- (none)"
    )
    reqs = (
        "\n".join(f"- {r.id}: {r.text}" for r in (wo.requirements or [])) or "- (none)"
    )
    acc = (
        "\n".join(
            f"- {a.id}: Given {a.given} When {a.when} Then {a.then}"
            for a in (wo.acceptance_tests or [])
        )
        or "- (none)"
    )
    return "\n".join(
        [
            "# System Definition Card",
            "",
            f"- WorkOrder: {wo.id}",
            f"- Fingerprint: {wo.fingerprint}",
            "",
            "## Container",
            f"- Deliverable: {wo.intent.deliverable}",
            f"- Offline default: {'true' if wo.intent.offline_default else 'false'}",
            "",
            "## Compass",
            f"- Title: {wo.title}",
            "",
            "## Engine",
            "### Requirements",
            reqs,
            "",
            "### Acceptance",
            acc,
            "",
            "## Fog",
            "### Constraints",
            constraints,
            "",
        ]
    )
