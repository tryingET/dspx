from __future__ import annotations

import importlib


def test_legacy_forge_module_is_alias_of_app_module() -> None:
    legacy = importlib.import_module("dspx.forge.issues")
    app = importlib.import_module("dspx.apps.forge_app.issues")
    assert legacy is app
