# summary: "Prints the foundry jury owner pin block for one maintained dspy-lm-auth checkout."
# read_when:
#   - "Regenerating OWNER_COMMIT/OWNER_TREE/OWNER_LOCK_SHA256 and per-file hashes after a fork commit."
"""Usage: uv run --no-sync python tests/foundry_jury_owner_repin.py --print-pins <root>

The printed block replaces the marked OWNER PIN BLOCK in
``dspx/services/program_foundry_gepa_comparison_jury_owner.py``. Module and
extra-file hashes are read from the working tree; commit and tree come from git
HEAD, so run it on the exact clean commit you intend to pin.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import cast

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "packages" / "dspx-core" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dspx.services.program_foundry_gepa_comparison_jury_owner import (  # noqa: E402
    _EXTRA_OWNER_FILES,
    _OWNER_MODULES,
)


# Every reviewed fork module the owner must hash-pin beyond the closed
# eight-name receipt module set; extend when a new provider family lands.
REQUIRED_EXTRA_OWNER_FILES: tuple[str, ...] = (
    "src/dspy_lm_auth/codex_backend.py",
    "src/dspy_lm_auth/codex_backend_contract.py",
    "src/dspy_lm_auth/_codex_credential.py",
    "src/dspy_lm_auth/codex_request.py",
    "src/dspy_lm_auth/outcome_receipt_chat.py",
    "src/dspy_lm_auth/copilot_backend.py",
    "src/dspy_lm_auth/copilot_backend_contract.py",
    "src/dspy_lm_auth/_copilot_credential.py",
    "src/dspy_lm_auth/copilot_receipt_transport.py",
    "src/dspy_lm_auth/copilot_receipt_runtime.py",
    "src/dspy_lm_auth/_route_policy.py",
    "src/dspy_lm_auth/auth.py",
    "src/dspy_lm_auth/chat_backend.py",
    "src/dspy_lm_auth/chat_backend_contract.py",
    "src/dspy_lm_auth/chat_backend_runtime.py",
    "src/dspy_lm_auth/chat_backend_transport.py",
    "src/dspy_lm_auth/_chat_credential.py",
    "src/dspy_lm_auth/xai_backend.py",
    "src/dspy_lm_auth/local_vllm_backend.py",
    "src/dspy_lm_auth/opencode_go_backend.py",
)


def missing_required_extra_files() -> tuple[str, ...]:
    """Return required reviewed fork files absent from the owner pin block."""

    return tuple(
        relative
        for relative in REQUIRED_EXTRA_OWNER_FILES
        if relative not in _EXTRA_OWNER_FILES
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def collect_pins(root: Path) -> dict[str, object]:
    """Collect commit, tree, version, lock hash, and per-file hashes for one root."""

    missing = missing_required_extra_files()
    if missing:
        raise ValueError(f"owner pin block lacks required files: {missing}")
    root = root.expanduser().resolve(strict=True)
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        "commit": _git(root, "rev-parse", "HEAD^{commit}"),
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "dirty": bool(_git(root, "status", "--porcelain", "--untracked-files=normal")),
        "version": str(project["project"]["version"]),
        "lock_sha256": _sha256(root / "uv.lock"),
        "modules": {
            name: (relative, _sha256(root / relative))
            for name, (relative, _) in _OWNER_MODULES.items()
        },
        "extra_files": {
            relative: _sha256(root / relative) for relative in _EXTRA_OWNER_FILES
        },
    }


def render_pin_block(pins: dict[str, object]) -> str:
    """Render the Python source of the marked owner pin block."""

    modules = cast(dict[str, tuple[str, str]], pins["modules"])
    extras = cast(dict[str, str], pins["extra_files"])
    lines = [
        f'OWNER_COMMIT = "{pins["commit"]}"',
        f'OWNER_TREE = "{pins["tree"]}"',
        f'OWNER_VERSION = "{pins["version"]}"',
        f'OWNER_LOCK_SHA256 = "{pins["lock_sha256"]}"',
        "",
        "_OWNER_MODULES: dict[str, tuple[str, str]] = {",
    ]
    for name, (relative, digest) in modules.items():
        lines.extend(
            [
                f'    "{name}": (',
                f'        "{relative}",',
                f'        "{digest}",',
                "    ),",
            ]
        )
    lines.extend(["}", "", "_EXTRA_OWNER_FILES = {"])
    for relative, digest in extras.items():
        lines.append(f'    "{relative}": "{digest}",')
    lines.append("}")
    if pins["dirty"]:
        lines.insert(
            0, "# WARNING: working tree is dirty; commit/tree do not cover these hashes"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-pins", metavar="ROOT", required=True)
    args = parser.parse_args(argv)
    sys.stdout.write(render_pin_block(collect_pins(Path(args.print_pins))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
