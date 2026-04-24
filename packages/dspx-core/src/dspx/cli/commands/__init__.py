"""Command modules for dspx CLI.

Each module exports a Typer app that is registered in the main dspx.py.

Extraction status:
  ✅ cache      - dspx.cli.commands.cache
  ✅ run        - dspx.cli.commands.run
  ✅ optimize   - dspx.cli.commands.optimize
  ✅ providers  - dspx.cli.commands.providers
  ✅ oracle     - dspx.cli.commands.oracle
  ✅ signature  - dspx.cli.commands.signature
  ✅ mermaid    - dspx.cli.commands.mermaid
  ✅ openapi    - dspx.cli.commands.openapi
  ✅ web        - dspx.cli.commands.web
  ✅ tools      - dspx.cli.commands.tools
  ✅ adapters   - dspx.cli.commands.adapters
  ✅ codegen    - dspx.cli.commands.codegen (helper functions)
  ✅ module     - dspx.cli.commands.module (helper functions)
  ✅ program    - root-level program-gen command uses dspx.services.program_service
"""

from dspx.cli.commands.adapters import (
    app as adapters_app,
    dataset_app as adapters_dataset_app,
    eval_app as adapters_eval_app,
)
from dspx.cli.commands.cache import app as cache_app
from dspx.cli.commands.mermaid import app as mermaid_app
from dspx.cli.commands.openapi import app as openapi_app
from dspx.cli.commands.optimize import app as optimize_app
from dspx.cli.commands.oracle import app as oracle_app
from dspx.cli.commands.providers import app as providers_app
from dspx.cli.commands.run import app as run_app
from dspx.cli.commands.signature import app as signature_app
from dspx.cli.commands.tools import app as tools_app
from dspx.cli.commands.web import app as web_app

__all__ = [
    "cache_app",
    "run_app",
    "optimize_app",
    "providers_app",
    "oracle_app",
    "signature_app",
    "mermaid_app",
    "openapi_app",
    "web_app",
    "tools_app",
    "adapters_app",
    "adapters_dataset_app",
    "adapters_eval_app",
]
