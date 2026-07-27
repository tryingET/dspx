# ---
# summary: "Retrieve only bounded DSPx engineering guidance from the consumer-pinned engineering-core release."
# read_when:
#   - "Changing DSPx engineering guidance retrieval or its policy contract."
# ---
from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HEADING_PATTERN = re.compile(r"^#{1,4} ")
COMMIT_PATTERN = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z")
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
MAX_CAPTURE_BYTES = 1_048_576
MAX_ERROR_CHARS = 1_000
MAX_HEADING_LINES = 100
MAX_OUTPUT_BYTES = 16_384
MAX_RANGE_LINES = 40
Runner = Callable[..., subprocess.CompletedProcess[str]]


class GuidanceError(ValueError):
    """Raised when guidance retrieval cannot proceed fail-closed."""


@dataclass(frozen=True)
class EngineeringContract:
    source: str
    resolved_commit: str
    lane: str
    disciplines: tuple[str, ...]


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GuidanceError(f"policy field {field} must be a non-empty string")
    return value.strip()


def load_contract(policy_path: Path) -> EngineeringContract:
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GuidanceError(f"policy file not found: {policy_path}") from exc
    except json.JSONDecodeError as exc:
        raise GuidanceError(f"invalid policy JSON: {exc}") from exc

    engineering_core = (
        payload.get("engineering_core") if isinstance(payload, dict) else None
    )
    if not isinstance(engineering_core, dict):
        raise GuidanceError("policy field engineering_core must be an object")
    release_pin = engineering_core.get("release_pin")
    if not isinstance(release_pin, dict):
        raise GuidanceError(
            "policy field engineering_core.release_pin must be an object"
        )

    source = _required_string(
        release_pin.get("source"), "engineering_core.release_pin.source"
    )
    resolved_commit = _required_string(
        release_pin.get("resolved_commit"),
        "engineering_core.release_pin.resolved_commit",
    )
    if not COMMIT_PATTERN.fullmatch(resolved_commit):
        raise GuidanceError(
            "release_pin.resolved_commit must be a full 40- or 64-character hexadecimal commit"
        )
    lane = _required_string(engineering_core.get("lane"), "engineering_core.lane")
    if not IDENTIFIER_PATTERN.fullmatch(lane):
        raise GuidanceError(
            "policy field engineering_core.lane must be a non-option identifier"
        )
    raw_disciplines = engineering_core.get("disciplines")
    if not isinstance(raw_disciplines, list) or not raw_disciplines:
        raise GuidanceError(
            "policy field engineering_core.disciplines must be a non-empty list"
        )
    disciplines = tuple(
        _required_string(item, f"engineering_core.disciplines[{index}]")
        for index, item in enumerate(raw_disciplines)
    )
    if any(not IDENTIFIER_PATTERN.fullmatch(item) for item in disciplines):
        raise GuidanceError(
            "policy field engineering_core.disciplines must contain non-option identifiers"
        )
    if len(set(disciplines)) != len(disciplines):
        raise GuidanceError(
            "policy field engineering_core.disciplines contains duplicates"
        )
    if not source.startswith("git+") or not source.endswith(f"@{resolved_commit}"):
        raise GuidanceError(
            "release_pin.source must be an immutable git source ending in resolved_commit"
        )
    if "--prefer-repo" in source:
        raise GuidanceError("release_pin.source must not contain --prefer-repo")

    return EngineeringContract(
        source=source,
        resolved_commit=resolved_commit,
        lane=lane,
        disciplines=disciplines,
    )


def build_command(
    contract: EngineeringContract,
    surface: str,
    discipline: str | None = None,
) -> list[str]:
    command = [
        "uv",
        "tool",
        "-n",
        "run",
        "--from",
        contract.source,
        "engineering-core",
    ]
    if surface == "lane":
        if discipline is not None:
            raise GuidanceError("lane retrieval does not accept a discipline")
        return [*command, "show", contract.lane]
    if surface != "discipline":
        raise GuidanceError(f"unknown guidance surface: {surface}")
    if discipline not in contract.disciplines:
        allowed = ", ".join(contract.disciplines)
        raise GuidanceError(
            f"discipline {discipline!r} is not selected by policy; choose one of: {allowed}"
        )
    return [*command, "show-discipline", discipline]


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_bounded_command(
    command: list[str], *, timeout: float = 120
) -> subprocess.CompletedProcess[str]:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        raise GuidanceError(f"engineering-core retrieval failed: {exc}") from exc
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    captured = 0
    deadline = time.monotonic() + timeout
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_process_group(process)
                raise GuidanceError(
                    f"engineering-core retrieval exceeded {timeout:g} seconds"
                )
            events = selector.select(remaining)
            if not events:
                continue
            for key, _ in events:
                chunk = os.read(key.fd, 65_536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                captured += len(chunk)
                if captured > MAX_CAPTURE_BYTES:
                    _kill_process_group(process)
                    raise GuidanceError(
                        "engineering-core retrieval exceeded the 1 MiB capture limit"
                    )
                buffers[key.data].extend(chunk)
        returncode = process.wait()
    finally:
        selector.close()
        if process.poll() is None:
            _kill_process_group(process)
    return subprocess.CompletedProcess(
        command,
        returncode,
        buffers["stdout"].decode("utf-8", errors="replace"),
        buffers["stderr"].decode("utf-8", errors="replace"),
    )


def retrieve_markdown(
    contract: EngineeringContract,
    surface: str,
    discipline: str | None = None,
    *,
    runner: Runner | None = None,
) -> str:
    command = build_command(contract, surface, discipline)
    if runner is None:
        result = run_bounded_command(command)
    else:
        try:
            result = runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GuidanceError(f"engineering-core retrieval failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip()
        if not detail:
            detail = "no stderr"
        elif len(detail) > MAX_ERROR_CHARS:
            detail = f"{detail[:MAX_ERROR_CHARS]}… [truncated]"
        raise GuidanceError(
            f"engineering-core retrieval exited {result.returncode}: {detail}"
        )
    return result.stdout


def _validate_output_size(output: str) -> None:
    output_bytes = len(output.encode("utf-8"))
    if output_bytes > MAX_OUTPUT_BYTES:
        raise GuidanceError(
            f"bounded output is {output_bytes} bytes; maximum is {MAX_OUTPUT_BYTES}"
        )


def render_headings(markdown: str) -> str:
    headings = [
        f"{line_number}:{line}"
        for line_number, line in enumerate(markdown.splitlines(), start=1)
        if HEADING_PATTERN.match(line)
    ]
    if not headings:
        raise GuidanceError("retrieved guidance contains no level 1-4 headings")
    if len(headings) > MAX_HEADING_LINES:
        raise GuidanceError(
            f"retrieved guidance has {len(headings)} headings; maximum is {MAX_HEADING_LINES}"
        )
    output = "\n".join(headings) + "\n"
    _validate_output_size(output)
    return output


def validate_range(start: int, end: int, line_count: int | None = None) -> None:
    if start < 1 or end < 1 or start > end:
        raise GuidanceError("range must satisfy 1 <= start <= end")
    span = end - start + 1
    if span > MAX_RANGE_LINES:
        raise GuidanceError(f"range spans {span} lines; maximum is {MAX_RANGE_LINES}")
    if line_count is not None and end > line_count:
        raise GuidanceError(
            f"range end {end} exceeds retrieved guidance length {line_count}"
        )


def render_range(markdown: str, start: int, end: int) -> str:
    lines = markdown.splitlines()
    validate_range(start, end, len(lines))
    output = "\n".join(lines[start - 1 : end]) + "\n"
    _validate_output_size(output)
    return output


def _add_mode_parsers(parent: argparse.ArgumentParser) -> None:
    modes = parent.add_subparsers(dest="mode", required=True)
    modes.add_parser("headings", help="Print only level 1-4 headings with line numbers")
    range_parser = modes.add_parser("range", help="Print one inclusive line range")
    range_parser.add_argument("start", type=int)
    range_parser.add_argument("end", type=int)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retrieve bounded guidance from DSPx's pinned engineering-core release"
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("policy/engineering-lane.json"),
        help="Engineering policy path (default: policy/engineering-lane.json)",
    )
    surfaces = parser.add_subparsers(dest="surface", required=True)
    lane = surfaces.add_parser("lane", help="Retrieve the policy-selected lane")
    _add_mode_parsers(lane)
    discipline = surfaces.add_parser(
        "discipline", help="Retrieve one policy-selected discipline"
    )
    discipline.add_argument("name")
    _add_mode_parsers(discipline)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        contract = load_contract(args.policy)
        discipline = args.name if args.surface == "discipline" else None
        if args.mode == "range":
            validate_range(args.start, args.end)
        markdown = retrieve_markdown(contract, args.surface, discipline)
        if args.mode == "headings":
            output = render_headings(markdown)
        else:
            output = render_range(markdown, args.start, args.end)
    except GuidanceError as exc:
        print(f"engineering-guidance: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
