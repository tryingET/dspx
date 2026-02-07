"""Forge app compatibility facade.

Purpose:
- Keep `dspx forge ...` behavior stable while introducing an app boundary.
- Centralize Forge imports behind one module so extraction can happen incrementally.

Current implementation forwards through `dspx.apps.forge_app.*` wrappers,
which currently delegate to legacy `dspx.forge.*` modules.
"""

from __future__ import annotations

from dspx.apps.forge_app.gitlab_client import (
    GitLabConfig,
    GitLabClient,
    load_gitlab_config_from_env,
)
from dspx.apps.forge_app.issues import (
    apply_issue_specs,
    build_issue_spec,
    close_marked_duplicates,
    default_paths,
    write_issue_specs,
)
from dspx.apps.forge_app.models import Intent, Routing
from dspx.apps.forge_app.overlaps import compute_overlaps, write_overlaps
from dspx.apps.forge_app.plan import build_plan, write_plan
from dspx.apps.forge_app.routing import route_candidates
from dspx.apps.forge_app.workorder import (
    build_workorder,
    load_workorder,
    write_workorder,
)

__all__ = [
    "Intent",
    "Routing",
    "GitLabConfig",
    "GitLabClient",
    "apply_issue_specs",
    "build_issue_spec",
    "build_plan",
    "build_workorder",
    "close_marked_duplicates",
    "compute_overlaps",
    "default_paths",
    "load_gitlab_config_from_env",
    "load_workorder",
    "route_candidates",
    "write_issue_specs",
    "write_overlaps",
    "write_plan",
    "write_workorder",
]
