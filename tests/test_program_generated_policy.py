from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.services import program_service
from dspx.services.program_generated_policy import (
    ProgramGeneratedPolicyError,
    build_program_generated_module_policy,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt


MODULE_SURFACES = {
    "schema_version": "program-module-surfaces-v1",
    "module_surfaces": [
        {
            "module_id": "generated_module",
            "effects": {
                "provider_called": False,
                "tool_called": False,
                "custom_import_loaded": False,
                "network": False,
                "filesystem_read": False,
                "filesystem_write": False,
                "subprocess": False,
                "external_authority": False,
            },
        }
    ],
}


def _configure_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")


@pytest.mark.parametrize(
    ("snippet", "code"),
    [
        (
            "dspy_retrieve",
            "import json\nimport dspy\nfrom signature import X\ndspy.Retrieve(k=1)\n",
        ),
        (
            "dspy_settings",
            "import json\nimport dspy\nfrom signature import X\ndspy.settings.configure(rm=None)\n",
        ),
        (
            "dspy_configure",
            "import json\nimport dspy\nfrom signature import X\ndspy.configure(lm=None)\n",
        ),
        (
            "dspy_lm",
            "import json\nimport dspy\nfrom signature import X\ndspy.LM('openai/gpt-4o-mini')\n",
        ),
        (
            "dspy_dict_lm",
            "import json\nimport dspy\nfrom signature import X\ndspy.__dict__['LM']('openai/gpt-4o-mini')\n",
        ),
        (
            "dspy_dunder_getattribute",
            "import json\nimport dspy\nfrom signature import X\ndspy.__getattribute__('LM')('openai/gpt-4o-mini')\n",
        ),
        (
            "object_dunder_getattribute_dspy_dict",
            "import json\nimport dspy\nfrom signature import X\nobject.__getattribute__(dspy, '__dict__')['LM']('openai/gpt-4o-mini')\n",
        ),
        (
            "type_dunder_getattribute_dspy_dict",
            "import json\nimport dspy\nfrom signature import X\ntype.__getattribute__(type(dspy), '__dict__')['LM']('openai/gpt-4o-mini')\n",
        ),
        (
            "aliased_object_dunder_getattribute",
            "import json\nimport dspy\nfrom signature import X\nOG = object.__getattribute__\nOG(dspy, 'LM')('openai/gpt-4o-mini')\n",
        ),
        (
            "aliased_object_root_dunder_getattribute",
            "import json\nimport dspy\nfrom signature import X\nO = object\nO.__getattribute__(dspy, 'LM')('openai/gpt-4o-mini')\n",
        ),
        (
            "dynamic_import",
            "import json\nimport dspy\nfrom signature import X\n__import__('os')\n",
        ),
        (
            "builtins_subscript",
            "import json\nimport dspy\nfrom signature import X\n__builtins__['open']('x')\n",
        ),
        (
            "importlib",
            "import json\nimport importlib\nimport dspy\nfrom signature import X\n",
        ),
        (
            "filesystem",
            "import json\nimport dspy\nfrom signature import X\nopen('secret.txt')\n",
        ),
        (
            "subprocess",
            "import json\nimport subprocess\nimport dspy\nfrom signature import X\nsubprocess.run(['true'])\n",
        ),
        (
            "network",
            "import json\nimport requests\nimport dspy\nfrom signature import X\nrequests.get('https://example.com')\n",
        ),
        (
            "tool",
            "import json\nimport dspy\nfrom signature import X\ndspy.Tool(lambda x: x)\n",
        ),
        (
            "react_without_surface",
            "import json\nimport dspy\nfrom signature import X\ndspy.ReAct(X, tools=[], max_iters=1)\n",
        ),
        (
            "program_of_thought_without_surface",
            "import json\nimport dspy\nfrom signature import X\ndspy.ProgramOfThought(X, max_iters=1)\n",
        ),
        (
            "aliased_react",
            "import json\nimport dspy\nfrom signature import X\nRA = dspy.ReAct\nRA(X, tools=['unsafe'], max_iters=99)\n",
        ),
        (
            "aliased_python_interpreter",
            "import json\nimport dspy\nfrom signature import X\nPI = dspy.PythonInterpreter\nPI(deno_command=['deno'])\n",
        ),
        (
            "tuple_aliased_react",
            "import json\nimport dspy\nfrom signature import X\n(RA,) = (dspy.ReAct,)\nRA(X, tools=['unsafe'], max_iters=99)\n",
        ),
        (
            "unsafe_program_of_thought_interpreter_binding",
            "import json\nimport dspy\nfrom signature import X\ninterpreter = None\ndspy.ProgramOfThought(X, max_iters=1, interpreter=interpreter)\n",
        ),
        (
            "default_aliased_react",
            "import json\nimport dspy\nfrom signature import X\ndef make(RA=dspy.ReAct):\n    return RA(X, tools=['unsafe'], max_iters=99)\n",
        ),
    ],
)
def test_generated_module_policy_rejects_disallowed_effects(
    snippet: str, code: str
) -> None:
    policy = build_program_generated_module_policy(
        code,
        module_surfaces=MODULE_SURFACES,
    )

    assert policy["status"] == "failed", snippet
    assert policy["violations"]


def test_generated_module_policy_requires_module_surfaces() -> None:
    policy = build_program_generated_module_policy(
        "import json\nimport dspy\nfrom signature import X\n",
        module_surfaces={"schema_version": "program-module-surfaces-v1"},
    )

    assert policy["status"] == "failed"
    assert any(
        item["code"] == "module_surfaces_missing" for item in policy["violations"]
    )


def test_generated_module_policy_rejects_untruthful_effect_flags() -> None:
    payload = json.loads(json.dumps(MODULE_SURFACES))
    payload["module_surfaces"][0]["effects"]["network"] = True

    policy = build_program_generated_module_policy(
        "import json\nimport dspy\nfrom signature import X\n",
        module_surfaces=payload,
    )

    assert policy["status"] == "failed"
    assert any(
        item["code"] == "module_surface_effect_not_allowed"
        for item in policy["violations"]
    )


def test_program_gen_writes_and_replay_checks_generated_module_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_local(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="PolicySidecarProgram",
            objective="Answer a question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    root = Path(artifact.root_path)
    policy_path = root / "generated_module_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    assert policy["schema_version"] == "program-generated-module-policy-v1"
    assert policy["status"] == "passed"
    assert manifest["program_generated_module_policy"] == policy
    assert manifest["generated_module_policy_artifact"]["path"] == (
        "generated_module_policy.json"
    )
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"

    policy["status"] = "drifted"
    policy_path.write_text(
        json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    drift = check_run_receipt(root / "manifest.json.meta.json")
    assert drift["status"] == "failed"
    assert drift["checks"]["program_generated_module_policy_hash_match"] is False


def test_program_gen_policy_failure_blocks_manifest_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_local(tmp_path, monkeypatch)
    real_render_module_surface = program_service.render_module_surface

    def poisoned_render_module_surface(intent: object) -> tuple[str, dict[str, object]]:
        code, metadata = real_render_module_surface(intent)
        return f"{code}\nimport importlib\n", metadata

    monkeypatch.setattr(
        program_service,
        "render_module_surface",
        poisoned_render_module_surface,
    )

    with pytest.raises(ProgramGeneratedPolicyError):
        materialize_program_from_intent(
            ProgramIntent(
                name="PoisonedPolicyProgram",
                objective="Policy should block importlib.",
                inputs=["question"],
                outputs=["answer"],
            ),
            outdir=tmp_path / "program",
        )

    assert not (tmp_path / "program" / "manifest.json").exists()
