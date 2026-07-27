# summary: "Tests pinned, bounded, fail-closed DSPx engineering-guidance retrieval."
# read_when:
#   - "Changing scripts/engineering_guidance.py or engineering-lane policy semantics."

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "engineering_guidance.py"
    spec = importlib.util.spec_from_file_location("engineering_guidance", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()
PIN = "8f59f4178f0c40f73d64c417e7a591de42a0f0d2"
SOURCE = f"git+https://example.invalid/engineering-core.git@{PIN}"


def _write_policy(tmp_path: Path, **overrides: Any) -> Path:
    engineering_core: dict[str, Any] = {
        "lane": "py",
        "disciplines": ["validation", "testing"],
        "release_pin": {
            "source": SOURCE,
            "resolved_commit": PIN,
        },
    }
    engineering_core.update(overrides)
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps({"engineering_core": engineering_core}), encoding="utf-8"
    )
    return path


def test_load_contract_and_commands_use_only_the_immutable_policy_pin(
    tmp_path: Path,
) -> None:
    contract = MODULE.load_contract(_write_policy(tmp_path))

    lane = MODULE.build_command(contract, "lane")
    discipline = MODULE.build_command(contract, "discipline", "validation")

    assert lane == [
        "uv",
        "tool",
        "-n",
        "run",
        "--from",
        SOURCE,
        "engineering-core",
        "show",
        "py",
    ]
    assert discipline[-2:] == ["show-discipline", "validation"]
    assert "--prefer-repo" not in lane
    assert not any(
        "/engineering-core" in part and not part.startswith("git+") for part in lane
    )


def test_retrieve_markdown_invokes_runner_without_a_shell(tmp_path: Path) -> None:
    contract = MODULE.load_contract(_write_policy(tmp_path))
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "# Lane\nbody\n", "")

    output = MODULE.retrieve_markdown(contract, "lane", runner=runner)

    assert output == "# Lane\nbody\n"
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[-2:] == ["show", "py"]
    assert kwargs == {
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": 120,
    }


def test_default_subprocess_capture_is_bounded() -> None:
    success = MODULE.run_bounded_command(
        [sys.executable, "-c", "print('# Small')"], timeout=5
    )
    assert success.returncode == 0
    assert success.stdout == "# Small\n"

    oversized = (
        "import sys; "
        f"sys.stdout.write('x' * {MODULE.MAX_CAPTURE_BYTES + 1}); "
        "sys.stdout.flush()"
    )
    with pytest.raises(MODULE.GuidanceError, match="exceeded the 1 MiB capture limit"):
        MODULE.run_bounded_command([sys.executable, "-c", oversized], timeout=5)


def test_timeout_kills_the_dedicated_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []
    real_killpg = MODULE.os.killpg

    def recording_killpg(process_group: int, sig: int) -> None:
        calls.append((process_group, sig))
        real_killpg(process_group, sig)

    monkeypatch.setattr(MODULE.os, "killpg", recording_killpg)

    with pytest.raises(MODULE.GuidanceError, match="exceeded 0.05 seconds"):
        MODULE.run_bounded_command(
            [sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.05
        )

    assert len(calls) == 1
    assert calls[0][1] == MODULE.signal.SIGKILL


def test_headings_and_range_are_bounded() -> None:
    markdown = "intro\n# One\nbody\n#### Four\n##### Five\ntail\n"

    assert MODULE.render_headings(markdown) == "2:# One\n4:#### Four\n"
    assert MODULE.render_range(markdown, 2, 4) == "# One\nbody\n#### Four\n"


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        (0, 1, "1 <= start <= end"),
        (3, 2, "1 <= start <= end"),
        (1, 4, "exceeds retrieved guidance length 3"),
        (1, 41, "maximum is 40"),
    ],
)
def test_invalid_ranges_fail_closed(start: int, end: int, message: str) -> None:
    with pytest.raises(MODULE.GuidanceError, match=message):
        MODULE.render_range("one\ntwo\nthree\n", start, end)


def test_cli_rejects_invalid_range_before_upstream_retrieval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy = _write_policy(tmp_path)

    def unexpected_retrieval(*_args: Any, **_kwargs: Any) -> str:
        pytest.fail("invalid range reached upstream retrieval")

    monkeypatch.setattr(MODULE, "retrieve_markdown", unexpected_retrieval)

    result = MODULE.main(["--policy", str(policy), "lane", "range", "10", "3"])

    assert result == 2
    assert "range must satisfy 1 <= start <= end" in capsys.readouterr().err


def test_heading_count_and_output_bytes_are_bounded() -> None:
    too_many_headings = "\n".join(f"# Heading {index}" for index in range(101))
    with pytest.raises(MODULE.GuidanceError, match="maximum is 100"):
        MODULE.render_headings(too_many_headings)

    oversized_line = "x" * (MODULE.MAX_OUTPUT_BYTES + 1)
    with pytest.raises(MODULE.GuidanceError, match="maximum is 16384"):
        MODULE.render_range(oversized_line, 1, 1)


def test_unknown_discipline_fails_before_execution(tmp_path: Path) -> None:
    contract = MODULE.load_contract(_write_policy(tmp_path))

    with pytest.raises(MODULE.GuidanceError, match="is not selected by policy"):
        MODULE.build_command(contract, "discipline", "security-privacy")


@pytest.mark.parametrize(
    "release_pin",
    [
        {"source": "/home/user/engineering-core", "resolved_commit": PIN},
        {
            "source": "git+https://example.invalid/engineering-core.git@main",
            "resolved_commit": PIN,
        },
        {
            "source": "git+https://example.invalid/engineering-core.git@main",
            "resolved_commit": "main",
        },
        {
            "source": f"git+https://example.invalid/core.git@{PIN} --prefer-repo",
            "resolved_commit": PIN,
        },
        {"source": SOURCE},
    ],
)
def test_missing_floating_or_local_pin_sources_fail_closed(
    tmp_path: Path, release_pin: dict[str, str]
) -> None:
    policy = _write_policy(tmp_path, release_pin=release_pin)

    with pytest.raises(MODULE.GuidanceError):
        MODULE.load_contract(policy)


def test_option_like_lane_or_discipline_fails_closed(tmp_path: Path) -> None:
    option_lane = _write_policy(tmp_path, lane="--help")
    with pytest.raises(MODULE.GuidanceError, match="non-option identifier"):
        MODULE.load_contract(option_lane)

    option_discipline = _write_policy(tmp_path, disciplines=["testing", "--help"])
    with pytest.raises(MODULE.GuidanceError, match="non-option identifiers"):
        MODULE.load_contract(option_discipline)


def test_duplicate_or_empty_disciplines_fail_closed(tmp_path: Path) -> None:
    duplicate = _write_policy(tmp_path, disciplines=["testing", "testing"])
    with pytest.raises(MODULE.GuidanceError, match="contains duplicates"):
        MODULE.load_contract(duplicate)

    empty = _write_policy(tmp_path, disciplines=[])
    with pytest.raises(MODULE.GuidanceError, match="must be a non-empty list"):
        MODULE.load_contract(empty)


def test_upstream_failure_is_reported_without_returning_content(tmp_path: Path) -> None:
    contract = MODULE.load_contract(_write_policy(tmp_path))

    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 17, "partial", "network unavailable"
        )

    with pytest.raises(MODULE.GuidanceError, match="exited 17: network unavailable"):
        MODULE.retrieve_markdown(contract, "lane", runner=runner)


def test_upstream_failure_never_falls_back_to_stdout_and_truncates_stderr(
    tmp_path: Path,
) -> None:
    contract = MODULE.load_contract(_write_policy(tmp_path))

    def stdout_only(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 9, "sensitive partial output", "")

    with pytest.raises(
        MODULE.GuidanceError, match="exited 9: no stderr"
    ) as stdout_error:
        MODULE.retrieve_markdown(contract, "lane", runner=stdout_only)
    assert "sensitive partial output" not in str(stdout_error.value)

    def large_stderr(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 8, "", "e" * 10_000)

    with pytest.raises(MODULE.GuidanceError, match=r"\[truncated\]") as stderr_error:
        MODULE.retrieve_markdown(contract, "lane", runner=large_stderr)
    assert len(str(stderr_error.value)) < 1_100


def test_no_headings_fails_closed() -> None:
    with pytest.raises(MODULE.GuidanceError, match="contains no level 1-4 headings"):
        MODULE.render_headings("plain text only\n")
