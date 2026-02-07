from __future__ import annotations

import importlib as _importlib
import sys as _sys

_mod = _importlib.import_module("dspx.apps.forge_app.gitlab_client")
_sys.modules[__name__] = _mod
