# summary: "Tests program-generation validation cache keys, path rebasing, effect replay, and private result copies."
# read_when:
#   - "Changing cached generation harness execution, module-smoke caching, or cache isolation semantics."

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from program_generation_cache import ProgramGenerationValidationCache


def test_default_module_evidence_root_is_test_local(tmp_path: Path) -> None:
    evidence_root = Path(os.environ["DSPX_TEST_MODULE_SYNTHESIS_EVIDENCE_ROOT"])

    assert evidence_root == tmp_path / "module-synthesis-evidence"
    assert not evidence_root.exists()


def _write_program_input(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "eval_behavior.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "intent.json").write_text(
        json.dumps({"root": str(root.parent)}, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_harness_cache_replays_private_path_rebased_file_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = ProgramGenerationValidationCache(tmp_path / "validation-cache")
    first_root = tmp_path / "first" / "program"
    second_root = tmp_path / "second" / "program"
    _write_program_input(first_root)
    _write_program_input(second_root)
    calls: list[Path] = []

    def execute(root: Path, _filename: str) -> dict[str, object]:
        calls.append(root)
        output = root / "behavior_episode.json"
        output.write_text(
            json.dumps({"program_root": str(root.resolve())}) + "\n",
            encoding="utf-8",
        )
        return {"returncode": 0, "root": str(root.resolve())}

    monkeypatch.setenv("DSPX_CACHE_DIR", str(first_root.parent / "cache"))
    first = cache.run_harness(
        first_root,
        "eval_behavior.py",
        label="behavior",
        execute=execute,
        execution_token="test-executor-v1",
    )
    monkeypatch.setenv("DSPX_CACHE_DIR", str(second_root.parent / "cache"))
    second = cache.run_harness(
        second_root,
        "eval_behavior.py",
        label="behavior",
        execute=execute,
        execution_token="test-executor-v1",
    )

    assert calls == [first_root.resolve()]
    assert first["root"] == str(first_root.resolve())
    assert second["root"] == str(second_root.resolve())
    assert json.loads(
        (second_root / "behavior_episode.json").read_text(encoding="utf-8")
    ) == {"program_root": str(second_root.resolve())}
    assert first_root / "behavior_episode.json" != second_root / "behavior_episode.json"


def test_harness_cache_key_binds_complete_input_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = ProgramGenerationValidationCache(tmp_path / "validation-cache")
    roots = [tmp_path / name / "program" for name in ("first", "second")]
    for root in roots:
        _write_program_input(root)
    (roots[1] / "eval_behavior.py").write_text("print('changed')\n", encoding="utf-8")
    calls = 0

    def execute(root: Path, _filename: str) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"returncode": 0, "root": str(root)}

    for root in roots:
        monkeypatch.setenv("DSPX_CACHE_DIR", str(root.parent / "cache"))
        cache.run_harness(
            root,
            "eval_behavior.py",
            label="behavior",
            execute=execute,
            execution_token="test-executor-v1",
        )

    assert calls == 2


def test_module_smoke_cache_returns_private_copies(tmp_path: Path) -> None:
    cache = ProgramGenerationValidationCache(tmp_path / "validation-cache")
    calls = 0

    def execute(
        _code: str, _payload: Mapping[str, object], _timeout: int | None
    ) -> tuple[bool, dict[str, bool], list[str]]:
        nonlocal calls
        calls += 1
        return True, {"module-smoke": True}, []

    first = cache.run_module_smoke(
        "class Example: pass\n",
        payload={"expected_module": "Example"},
        timeout=10,
        execute=execute,
        execution_token="test-smoke-v1",
    )
    first[1]["module-smoke"] = False
    second = cache.run_module_smoke(
        "class Example: pass\n",
        payload={"expected_module": "Example"},
        timeout=10,
        execute=execute,
        execution_token="test-smoke-v1",
    )

    assert calls == 1
    assert second == (True, {"module-smoke": True}, [])
