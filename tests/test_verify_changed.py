from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "verify_changed.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_changed", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _plan(*paths: str) -> dict[str, object]:
    module = _load_module()
    impact_map = module.load_impact_map()
    return module.build_plan(
        list(paths),
        impact_map,
        base_mode="explicit_files",
        base_ref=None,
    )


def _command_ids(plan: dict[str, object]) -> list[str]:
    return [str(command["id"]) for command in plan["commands"]]  # type: ignore[index]


def test_docs_only_change_selects_docs_strict_without_full_verification() -> None:
    plan = _plan("docs/project/developer_workflow.md")

    assert plan["schema_version"] == "dspx-verification-impact-plan-v1"
    assert plan["risk"] == "docs_only"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == ["docs_strict"]


def test_program_generation_spine_selects_expanded_adjacent_checks() -> None:
    plan = _plan("packages/dspx-core/src/dspx/services/program_service.py")

    assert plan["risk"] == "expanded"
    assert plan["full_verification_required"] is False
    assert _command_ids(plan) == [
        "ruff_touched",
        "typecheck_core",
        "pytest_program_generation_spine",
        "boundary_contract_check",
        "docs_strict",
    ]


def test_refinement_comparison_and_test_change_deduplicate_commands() -> None:
    plan = _plan(
        "packages/dspx-core/src/dspx/services/program_refinement_comparison.py",
        "tests/test_program_refinement_comparison.py",
    )

    assert plan["risk"] == "bounded"
    command_ids = _command_ids(plan)
    assert command_ids.count("ruff_touched") == 1
    assert command_ids.count("pytest_refinement_candidate_comparison") == 1
    assert "pytest_touched" in command_ids


def test_unknown_file_fails_wide() -> None:
    plan = _plan("misc/unmapped.file")

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert "unmapped path: misc/unmapped.file" in str(plan["wide_reason"])
    classification = plan["classifications"][0]  # type: ignore[index]
    assert classification["category"] == "unknown"


def test_justfile_change_requires_wide_verification() -> None:
    plan = _plan("Justfile")

    assert plan["risk"] == "wide"
    assert plan["full_verification_required"] is True
    assert _command_ids(plan) == ["workflow_contract_check", "verify_fast"]


def test_changed_files_accepts_just_style_base_assignment(monkeypatch) -> None:
    module = _load_module()

    calls: list[list[str]] = []

    def fake_run_git(args: list[str]) -> list[str]:
        calls.append(args)
        return ["docs/project/developer_workflow.md"]

    monkeypatch.setattr(module, "_run_git", fake_run_git)

    mode, base_ref, paths = module.changed_files(
        base="base=HEAD~1",
        staged=False,
        explicit_files=[],
    )

    assert mode == "diff"
    assert base_ref == "HEAD~1"
    assert paths == ["docs/project/developer_workflow.md"]
    assert calls == [["diff", "--name-only", "HEAD~1"]]


def test_working_tree_status_parser_preserves_first_path_character(monkeypatch) -> None:
    module = _load_module()

    monkeypatch.setattr(
        module,
        "_run_git",
        lambda args: [" M Justfile", "?? docs/project/developer_workflow.md"],
    )

    assert module._working_tree_paths() == [
        "Justfile",
        "docs/project/developer_workflow.md",
    ]


def test_run_plan_writes_result_receipt(tmp_path, monkeypatch) -> None:
    module = _load_module()
    plan = _plan("docs/project/developer_workflow.md")
    result_out = tmp_path / "impact-result.json"
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    exit_code = module.run_plan(plan, allow_wide=False, result_out=result_out)

    assert exit_code == 0
    assert calls == [
        [
            "node",
            str(Path.home() / "ai-society/core/agent-scripts/scripts/docs-list.mjs"),
            "--docs",
            ".",
            "--strict",
        ]
    ]
    payload = json.loads(result_out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "dspx-verification-impact-result-v1"
    assert payload["status"] == "passed"
    assert payload["exit_code"] == 0
    assert payload["summary"] == {
        "blocked_wide": False,
        "command_count": 1,
        "failed_count": 0,
        "full_verification_required": False,
        "passed_count": 1,
        "risk": "docs_only",
    }
    assert payload["commands"][0]["id"] == "docs_strict"
    assert payload["commands"][0]["returncode"] == 0
    assert payload["non_authority"]["full_verification_replacement"] is False


def test_main_run_writes_result_receipt_from_cli_args(tmp_path, monkeypatch) -> None:
    module = _load_module()
    result_out = tmp_path / "cli-impact-result.json"
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    exit_code = module.main(
        [
            "--files",
            "tests/test_verify_changed.py",
            "--run",
            "--result-out",
            str(result_out),
            "--json",
        ]
    )

    assert exit_code == 0
    assert calls == [
        ["uvx", "ruff", "check", "tests/test_verify_changed.py"],
        [
            "uv",
            "run",
            "--no-sync",
            "-m",
            "pytest",
            "-q",
            "tests/test_verify_changed.py",
        ],
    ]
    payload = json.loads(result_out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "dspx-verification-impact-result-v1"
    assert payload["status"] == "passed"
    assert payload["summary"]["command_count"] == 2
    assert payload["plan"]["changed_files"] == ["tests/test_verify_changed.py"]


def test_run_plan_writes_blocked_wide_receipt(tmp_path) -> None:
    module = _load_module()
    plan = _plan("Justfile")
    result_out = tmp_path / "impact-wide-result.json"

    exit_code = module.run_plan(plan, allow_wide=False, result_out=result_out)

    assert exit_code == 2
    payload = json.loads(result_out.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked_wide"
    assert payload["summary"]["blocked_wide"] is True
    assert payload["commands"] == []
    assert payload["plan"]["full_verification_required"] is True


def test_plan_json_is_serializable() -> None:
    plan = _plan("docs/project/developer_workflow.md")

    encoded = json.dumps(plan, sort_keys=True)

    assert "dspx-verification-impact-plan-v1" in encoded
