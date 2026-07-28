# ---
# summary: "Validate DSPx workflow documentation, commands, and engineering-lane contract surfaces."
# read_when:
#   - "Changing workflow docs, Just recipes, CI entrypoints, or loop-validation policy."
# ---
from __future__ import annotations

if __package__ == "scripts":
    from .workflow_contracts import Issue, collect_issues, main
elif __name__ == "__main__":
    from workflow_contracts import Issue, collect_issues, main
else:
    from scripts.workflow_contracts import Issue, collect_issues, main

__all__ = ["Issue", "collect_issues", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
