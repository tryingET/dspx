"""Reviewed local copy inventories, dependency custody and fixture mount bounds."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tomllib


def strict_json(text: str):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def inventory(root: Path, names: list[str] | None = None):
    rows = {}
    paths = (
        [root / name for name in names]
        if names is not None
        else (
            [root]
            if root.is_file() or root.is_symlink()
            else [root, *sorted(root.rglob("*"))]
        )
    )
    for path in paths:
        name = path.relative_to(root).as_posix()
        if (
            any(part in {"..", ""} for part in Path(name).parts)
            or path.is_absolute() is False
        ):
            raise ValueError("noncanonical inventory path")
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            rows[name] = {"link": os.readlink(path)}
        elif stat.S_ISREG(info.st_mode):
            rows[name] = {
                "sha256": file_hash(path),
                "bytes": info.st_size,
                "mode": stat.S_IMODE(info.st_mode),
            }
        elif stat.S_ISDIR(info.st_mode):
            rows[name] = {"directory": True, "mode": stat.S_IMODE(info.st_mode)}
        else:
            raise ValueError(f"special file in closure: {path}")
    return rows


def assert_inventory(root: Path, expected: dict, names: list[str] | None = None):
    actual = inventory(root, names)
    if actual != expected:
        raise ValueError(f"custody/source drift: {root}")


# Exact observed runtime identity, not an arbitrary interpreter mount prefix.
PYTHON_PHYSICAL = Path(
    "/home/tryinget/.local/share/uv/python/cpython-3.13.12-linux-x86_64-gnu"
)
PYTHON_MINOR = Path(
    "/home/tryinget/.local/share/uv/python/cpython-3.13-linux-x86_64-gnu"
)


def target_paths(row: dict) -> tuple[Path, ...]:
    target = Path(row["target"])
    if row["role"] == "python":
        if target != PYTHON_PHYSICAL or row.get("aliases") != [str(PYTHON_MINOR)]:
            raise ValueError("exact reviewed physical/minor Python pair required")
        return (PYTHON_PHYSICAL, PYTHON_MINOR)
    if "aliases" in row:
        raise ValueError("aliases only supported for the exact Python runtime pair")
    return (target,)


def closure_mounts(prepared: Path, entries: list[dict], repo: Path):
    validate_mount_targets(entries, repo)
    return [
        (prepared / f"closure-{index}", target, True)
        for index, row in enumerate(entries)
        for target in target_paths(row)
    ]


def validate_python_home(entries, venv):
    runtimes = [row for row in entries if row["role"] == "python"]
    if not runtimes:
        return
    if len(runtimes) != 1:
        raise ValueError("exactly one physical Python runtime required")
    executable = runtimes[0]["members"].get("bin/python3.13", {})
    if not (
        re.fullmatch("[0-9a-f]{64}", executable.get("sha256", ""))
        and executable.get("bytes", 0) > 0
        and executable.get("mode", 0) & 0o111
    ):
        raise ValueError("physical Python executable identity is not bound")
    if venv["members"].get("bin/python") != {
        "link": str(PYTHON_MINOR / "bin/python3.13")
    }:
        raise ValueError("installed venv interpreter alias differs")
    if "sha256" not in venv["members"].get("pyvenv.cfg", {}):
        raise ValueError("regular bound pyvenv.cfg required")
    config = {}
    for line in (Path(venv["source"]) / "pyvenv.cfg").read_text().splitlines():
        key, separator, value = line.partition("=")
        if not separator or key.strip() in config:
            raise ValueError("malformed/duplicate pyvenv.cfg value")
        config[key.strip()] = value.strip()
    expected = {
        "home": str(PYTHON_MINOR / "bin"),
        "implementation": "CPython",
        "version_info": "3.13.12",
        "include-system-site-packages": "false",
    }
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("unbound Python home/version or host site access")


def validate_mount_targets(entries: list[dict], repo: Path):
    """Closed DSPx role targets, never arbitrary overlays over reviewed source."""
    home = Path("/home/tryinget")
    tool_paths = {
        Path("/usr/bin/uv"),
        Path("/usr/bin/just"),
        Path("/usr/bin/node"),
        home / ".local/bin/prek",
        home / ".local/share/uv/tools/prek/bin/prek",
    }
    hooks = home / ".cache/prek"
    targets = []
    for row in entries:
        target = Path(row["target"])
        role = row["role"]
        if "link" in row.get("members", {}).get(".", {}):
            raise ValueError("symlink mount root could bind live host bytes")
        if (
            not target.is_absolute()
            or ".." in target.parts
            or str(target) != row["target"]
        ):
            raise ValueError("noncanonical closure mount target")
        allowed = (
            role == "venv"
            and target == repo / ".venv"
            or role == "python"
            and target == PYTHON_PHYSICAL
            or role == "tool"
            and target in tool_paths
            or role == "docs"
            and target == home / "ai-society/core/agent-scripts"
            or role == "hooks"
            and target.parent in {hooks / "hooks", hooks / "repos", hooks / "cache"}
            or role == "fixture"
            and (
                target.parent == Path("/fixtures")
                or target in {Path("/usr/bin/python3"), Path("/usr/bin/python3.13")}
            )
        )
        if not allowed:
            raise ValueError(f"role cannot mount over source/runtime: {role} {target}")
        if target.is_relative_to(repo) and (role != "venv" or target != repo / ".venv"):
            raise ValueError("closure cannot hide reviewed source or Git metadata")
        for logical in target_paths(row):
            if any(
                logical.is_relative_to(other) or other.is_relative_to(logical)
                for other in targets
            ):
                raise ValueError("duplicate/nested mount shadows")
            targets.append(logical)


def bound_destination(bound: dict, name: str) -> str:
    """Resolve recorded file OR directory aliases without consulting the host."""
    current = name
    for _ in range(32):
        path = Path(current)
        changed = False
        for prefix in [*reversed(path.parents), path]:
            member = bound.get(str(prefix), {})
            if "link" in member:
                link = Path(member["link"])
                base = link if link.is_absolute() else prefix.parent / link
                current = os.path.normpath(base / path.relative_to(prefix))
                changed = True
                break
        if not changed:
            if current not in bound:
                raise ValueError(f"unbound closure alias: {name}")
            return current
    raise ValueError("cyclic closure alias")


def validate_closure(review: dict, repo: Path):
    """Refuse unsafe closure; never prune installed membership to pass.

    Exact byte inventories are locally reviewed custody, not fresh authentication
    from PyPI. RECORD hashes are cross-checked independently; the entire installed
    tree (including metadata and executable hooks) remains in the byte inventory.
    """
    entries = review["closure"]
    validate_mount_targets(entries, repo)
    targets = [target for row in entries for target in target_paths(row)]
    if len(targets) != len(set(targets)) or not entries:
        raise ValueError("duplicate/empty closure")
    denied = {
        ".env",
        ".ssh",
        ".aws",
        ".azure",
        ".netrc",
        ".npmrc",
        "society.v2.db",
        "ak",
        "ak-bin",
        "ak.sh",
    }
    roots = [repo, *targets]
    if any(
        a != b and (a.is_relative_to(b) or b.is_relative_to(a))
        for a in targets
        for b in targets
    ):
        raise ValueError("overlapping closure roots obscure membership")
    locked = tomllib.loads((repo / "uv.lock").read_text())
    packages = {
        (p["name"].lower().replace("_", "-"), p.get("version"))
        for p in locked["package"]
    }
    venvs = [row for row in entries if row["role"] == "venv"]
    if len(venvs) != 1 or venvs[0]["target"] != str(repo / ".venv"):
        raise ValueError("exact existing repo venv required")
    bound = {
        str(repo / name): member
        for name, member in review.get("source", {}).items()
        if member != {"deleted": True}
    }
    for row in entries:
        for target in target_paths(row):
            bound.update(
                {str(target / name): member for name, member in row["members"].items()}
            )
    for name, member in bound.items():
        if "link" in member:
            destination = Path(bound_destination(bound, name))
            if destination.is_relative_to(repo) and not destination.is_relative_to(
                repo / ".venv"
            ):
                raise ValueError("closure alias cannot shadow source directories")
    for selected in review.get("fixtures", {}).values():
        if selected is not None and (
            not isinstance(selected, str) or selected not in bound
        ):
            raise ValueError("optional fixture must bind exact copied member bytes")
    for row in entries:
        target = Path(row["target"])
        source = Path(row["source"])
        if not source.is_absolute() or not target.is_absolute() or ".." in target.parts:
            raise ValueError("closure roots must be canonical absolute paths")
        if target in {Path("/"), Path("/home"), Path("/home/tryinget"), repo} or any(
            part in denied for part in target.parts
        ):
            raise ValueError("unsafe closure mount")
        if any(
            target.is_relative_to(Path(root))
            for root in ("/proc", "/sys", "/dev", "/run", "/fixture")
        ):
            raise ValueError("closure cannot replace runtime/private state")
        if row["role"] not in {"venv", "python", "tool", "docs", "hooks", "fixture"}:
            raise ValueError("unknown closure role")
        assert_inventory(source, row["members"])
        for name, member in row["members"].items():
            parts = Path(name).parts
            if (
                Path(name).is_absolute()
                or ".." in parts
                or set(parts) & denied
                or any(name.endswith(s) for s in (".safetensors", ".gguf", ".key"))
            ):
                raise ValueError(f"authority/credential/model or unsafe member: {name}")
            if name.endswith(".pem"):
                certificate = (source / name).read_bytes()
                if (
                    b"-----BEGIN CERTIFICATE-----" not in certificate
                    or b"PRIVATE KEY" in certificate
                ):
                    raise ValueError("non-public certificate/key in tool closure")
            if "link" in member:
                link = Path(member["link"])
                resolved = Path(
                    os.path.normpath(
                        link if link.is_absolute() else target / name / ".." / link
                    )
                )
                if not any(resolved.is_relative_to(root) for root in roots):
                    raise ValueError(f"escaping closure alias: {name}")
            if name.endswith(".pth"):
                for line in (source / name).read_text().splitlines():
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith(("import ", "import\t")):
                        # Executable .pth lines require exact separate review, not parsing guesses.
                        if review["pth_imports"].get(str(target / name)) != member.get(
                            "sha256"
                        ):
                            raise ValueError(f"unreviewed executable .pth: {name}")
                    elif (
                        ".." in Path(line).parts
                        or not Path(line).is_absolute()
                        or not any(
                            Path(name).is_relative_to(Path(line)) for name in bound
                        )
                    ):
                        raise ValueError(f"unbound editable .pth reference: {name}")
        if row["role"] != "venv":
            continue
        for metadata in source.glob("lib/python*/site-packages/*.dist-info/METADATA"):
            fields = dict(
                line.split(": ", 1)
                for line in metadata.read_text().splitlines()
                if line.startswith(("Name: ", "Version: "))
            )
            identity = (fields["Name"].lower().replace("_", "-"), fields["Version"])
            if identity not in packages:
                raise ValueError(f"installed package outside uv.lock: {identity}")
            record = metadata.with_name("RECORD")
            seen = set()
            for name, encoded, size in csv.reader(record.read_text().splitlines()):
                path = (metadata.parent.parent / name).resolve()
                if (
                    name in seen
                    or not path.is_relative_to(source.resolve())
                    or not path.is_file()
                ):
                    raise ValueError("unsafe/duplicate/missing RECORD member")
                seen.add(name)
                if encoded:
                    algorithm, value = encoded.split("=", 1)
                    observed = (
                        base64.urlsafe_b64encode(bytes.fromhex(file_hash(path)))
                        .decode()
                        .rstrip("=")
                    )
                    if (
                        algorithm != "sha256"
                        or value != observed
                        or int(size) != path.stat().st_size
                    ):
                        raise ValueError(f"installed RECORD drift: {path}")
                elif path != record and path.suffix != ".pyc":
                    raise ValueError(f"unhashed installed RECORD member: {path}")

    validate_python_home(entries, venvs[0])


def read_review(path: Path, expected: str, expected_environment: dict):
    if not re.fullmatch("[0-9a-f]{64}", expected) or file_hash(path) != expected:
        raise ValueError("review manifest must have an independently supplied SHA256")
    review = strict_json(path.read_text())
    required = {
        "schema",
        "head",
        "source",
        "index",
        "closure",
        "pth_imports",
        "image",
        "skips",
        "fixtures",
        "environment",
        "collection",
    }
    if (
        not isinstance(review, dict)
        or set(review) != required
        or review["schema"] != "dspx-full-local-custody-v3"
    ):
        raise ValueError("invalid reviewed closure schema")
    index = review["index"]
    if (
        not isinstance(index, dict)
        or set(index) != {"sha256", "entries"}
        or not isinstance(index["sha256"], str)
        or not re.fullmatch("[0-9a-f]{64}", index["sha256"])
        or not isinstance(index["entries"], str)
        or len(index["entries"].encode()) > 1024 * 1024
    ):
        raise ValueError("reviewed source index custody required")
    if not re.fullmatch("sha256:[0-9a-f]{64}", review["image"]):
        raise ValueError("image must be an existing immutable local image ID")
    collection = review["collection"]
    if (
        not isinstance(collection, dict)
        or set(collection) != {"nodes", "skips"}
        or not isinstance(collection["nodes"], list)
        or not collection["nodes"]
        or not all(isinstance(node, str) and node for node in collection["nodes"])
        or len(collection["nodes"]) != len(set(collection["nodes"]))
        or not isinstance(collection["skips"], dict)
        or not all(
            isinstance(node, str)
            and node
            and isinstance(sha, str)
            and re.fullmatch("[0-9a-f]{64}", sha)
            for node, sha in collection["skips"].items()
        )
    ):
        raise ValueError(
            "independently reviewed collection/collector baseline required"
        )
    if review["environment"] != expected_environment:
        raise ValueError("reviewed closed environment differs")
    if set(review["fixtures"]) != {"AK5456_REVIEW_PROBES", "host_interpreter"}:
        raise ValueError("optional fixture inventory must be explicit")
    for name in review["source"]:
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or any(
                part in {".env", ".venv", "generated", "__pycache__"}
                for part in Path(name).parts
            )
        ):
            raise ValueError("unsafe source input")
        if "deleted" in review["source"][name] and review["source"][name] != {
            "deleted": True
        }:
            raise ValueError("source deletion must be an explicit tombstone")
        if "link" in review["source"][name]:
            raise ValueError("source symlinks require separate design admission")
    return review
