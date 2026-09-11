"""Small config-free Git adapter for host reads and private local cloning.

Never open the original/local config with Git. A bounded metadata view contains
only index/ref/object lookup data and inert ignore/attribute files; no includes,
remote, aliases, hooks, filter definitions or executable extensions. .gitignore
continues to be read from the actual worktree. Linked/alternate object stores are
unsupported and reject rather than silently changing the inventory.
"""

from __future__ import annotations

import hashlib
import os
import json
from pathlib import Path
import re
import shutil
import stat
import struct
import tempfile

from verify_full_processes import HOST_ENV
from verify_full_closure import inventory

GIT_ENV = HOST_ENV | {
    "TMPDIR": os.environ.get("TMPDIR", HOST_ENV["TMPDIR"]),
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_COUNT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_ALLOW_PROTOCOL": "file",
}
FLAGS = {
    "ls-files": {"-z", "--cached", "--others", "--exclude-standard", "--stage"},
    "diff": {"--name-only", "--numstat", "--check", "-z", "--diff-filter=ACMRD"},
    "diff-tree": {
        "--root",
        "--no-commit-id",
        "--name-only",
        "--diff-filter=ACMRD",
        "-r",
    },
    "rev-parse": {"--verify"},
    "rev-list": {"--reverse", "--ancestry-path"},
    "notes": set(),
    "ls-tree": {"-r", "-z"},
}


def index_data(path: Path):
    """Admit SHA1 index v2, stage0, ordinary modes, no semantic flags.

    TREE is a dispensable cache, stripped before Git reads it. Every other
    extension (including split/sparse/fsmonitor/resolve-undo) fails closed.
    Stat cache bytes are custody-bound but never used as membership authority.
    """
    if not path.exists() and not path.is_symlink():
        return {"sha256": hashlib.sha256(b"").hexdigest(), "entries": ""}, b""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("unsafe Git index")
        raw = stream.read(16 * 1024**2 + 1)
    if len(raw) > 16 * 1024**2 or len(raw) < 32:
        raise ValueError("Git index budget/header")
    signature, version, count = struct.unpack("!4sII", raw[:12])
    if (
        signature != b"DIRC"
        or version != 2
        or hashlib.sha1(raw[:-20]).digest() != raw[-20:]
    ):
        raise ValueError("unsupported/corrupt Git index version/checksum")
    offset, previous, rows = 12, b"", []
    for _ in range(count):
        start = offset
        if start + 62 >= len(raw) - 20:
            raise ValueError("truncated Git index entry")
        mode = struct.unpack("!I", raw[start + 24 : start + 28])[0]
        oid = raw[start + 40 : start + 60].hex()
        flags = struct.unpack("!H", raw[start + 60 : start + 62])[0]
        end = raw.find(b"\0", start + 62, len(raw) - 20)
        if end < 0:
            raise ValueError("unterminated Git index path")
        name_bytes = raw[start + 62 : end]
        name = name_bytes.decode("utf-8", errors="strict")
        path_name = Path(name)
        if mode == 0o160000:
            raise ValueError("submodule Git metadata unsupported; no silent omission")
        if (
            mode not in {0o100644, 0o100755, 0o120000}
            or flags & 0xF000
            or flags != min(len(name_bytes), 0xFFF)
            or oid == "0" * 40
        ):
            raise ValueError("unsupported Git index mode/flags/unmerged/OID")
        if (
            name in {"", "."}
            or path_name.is_absolute()
            or path_name.as_posix() != name
            or any(
                part in {".", ".."} or part.casefold() == ".git"
                for part in path_name.parts
            )
            or name_bytes <= previous
        ):
            raise ValueError("unsafe/duplicate/unsorted Git index path")
        offset = start + ((62 + len(name_bytes) + 8) // 8) * 8
        if offset > len(raw) - 20 or any(raw[end:offset]):
            raise ValueError("invalid Git index padding")
        rows.append(f"{mode:06o} {oid} 0\t{name}\0")
        previous = name_bytes
    body = raw[:offset]
    seen = set()
    while offset < len(raw) - 20:
        if offset + 8 > len(raw) - 20:
            raise ValueError("truncated Git index extension")
        kind, size = struct.unpack("!4sI", raw[offset : offset + 8])
        offset += 8 + size
        if kind != b"TREE" or kind in seen or offset > len(raw) - 20:
            raise ValueError("unsupported Git index extension")
        seen.add(kind)
    entries = "".join(rows)
    if len(entries.encode()) > 1024 * 1024:
        raise ValueError("Git stage-list budget exceeded")
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "entries": entries,
    }, body + hashlib.sha1(body).digest()


def source_index(repo: Path):
    if (
        repo.resolve() != repo
        or (repo / ".git").is_symlink()
        or not (repo / ".git").is_dir()
    ):
        raise ValueError("ordinary private .git directory required")
    return index_data(repo / ".git/index")[0]


def metadata_view(repo: Path) -> Path:
    metadata = repo / ".git"
    if metadata.is_symlink() or not metadata.is_dir():
        raise ValueError("ordinary private .git directory required")
    if any((metadata / name).is_symlink() for name in ("refs", "info")):
        raise ValueError("linked Git metadata directory unsupported")
    objects = metadata / "objects"
    if (
        objects.is_symlink()
        or not objects.is_dir()
        or (objects / "info/alternates").exists()
    ):
        raise ValueError("linked/alternate Git object storage unsupported")
    root = Path(
        tempfile.mkdtemp(
            prefix="dspx-git-view-", dir=os.environ.get("TMPDIR", HOST_ENV["TMPDIR"])
        )
    )
    try:
        total = 0

        def copy_file(path: Path):
            nonlocal total
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 16 * 1024**2:
                raise ValueError("unsafe Git metadata member")
            total += info.st_size
            if total > 32 * 1024**2:
                raise ValueError("Git metadata view budget exceeded")
            destination = root / path.relative_to(metadata)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination, follow_symlinks=False)

        for name in (
            "HEAD",
            "index",
            "packed-refs",
            "shallow",
            "info/exclude",
            "info/attributes",
        ):
            path = metadata / name
            if path.exists() or path.is_symlink():
                copy_file(path)
        if (root / "index").exists():
            _, sanitized = index_data(root / "index")
            (root / "index").write_bytes(sanitized)
        for path in (metadata / "refs").rglob("*"):
            if path.is_symlink() or not path.is_dir():
                copy_file(path)
        for path in metadata.glob("sharedindex.*"):
            copy_file(path)
        (root / "objects").symlink_to(objects.resolve(), target_is_directory=True)
        (root / "refs").mkdir(exist_ok=True)
        (root / "config").write_text(
            "[core]\nrepositoryformatversion = 0\nbare = false\nfsmonitor = false\nhooksPath = /dev/null\n"
        )
        return root
    except BaseException:
        shutil.rmtree(root)  # Construction spawned no child; only this new view exists.
        raise


def read_argv(view: Path, repo: Path, arguments: list[str]):
    if not arguments or arguments[0] not in FLAGS:
        raise ValueError("unsupported host Git command")
    operation = arguments[0]
    positional = []
    paths = False
    for argument in arguments[1:]:
        if argument == "--":
            paths = True
        elif argument.startswith("-") and not paths:
            if argument not in FLAGS[operation] and not (
                operation == "rev-list"
                and re.fullmatch(r"--max-count=\d{1,4}", argument)
                or operation == "notes"
                and re.fullmatch(r"--ref=refs/notes/[A-Za-z0-9/_.-]+", argument)
            ):
                raise ValueError("unsupported host Git option")
        else:
            positional.append(argument)
    if operation == "notes" and (len(positional) != 2 or positional[0] != "show"):
        raise ValueError("only Git notes show is admitted")
    flags = (
        ["--no-ext-diff", "--no-textconv"] if operation in {"diff", "diff-tree"} else []
    )
    return [
        "/usr/bin/git",
        "--no-pager",
        "--no-replace-objects",
        f"--git-dir={view}",
        f"--work-tree={repo}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        operation,
        *flags,
        *arguments[1:],
    ]


def view_call(run, uses: list[dict], *args, **kwargs):
    state = {"settled": False}
    uses.append(state)
    return run(*args, **kwargs, settlement=state)


def close_view(view: Path, uses: list[dict]):
    if all(state.get("settled") is True for state in uses):
        shutil.rmtree(view)
    else:
        (view / "retained.json").write_text(
            json.dumps(
                {
                    "status": "retained-unsettled-or-unverified",
                    "view": str(view),
                    "invocations": uses,
                },
                sort_keys=True,
            )
            + "\n"
        )


def read_git(run, label: str, arguments: list[str], repo: Path, **kwargs):
    view = metadata_view(repo)
    uses: list[dict] = []
    try:
        index = view_call(
            run,
            uses,
            label + "-gitlinks",
            read_argv(view, repo, ["ls-files", "--stage", "-z"]),
            cwd=repo,
            env=GIT_ENV,
        )
        if any(row.startswith("160000 ") for row in index.split("\0")):
            raise ValueError(
                "submodule Git metadata is unsupported; no silent omission"
            )
        return view_call(
            run,
            uses,
            label,
            read_argv(view, repo, arguments),
            cwd=repo,
            env=GIT_ENV,
            **kwargs,
        )
    finally:
        close_view(view, uses)


def source_names(run, repo: Path):
    raw = read_git(
        run,
        "source-names",
        ["ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        repo,
    )
    names = {name for name in raw.split("\0") if name}
    # HEAD supplies staged deletions, which are absent from the current index.
    head = read_git(run, "source-head", ["ls-tree", "-r", "-z", "HEAD"], repo)
    for row in head.split("\0"):
        if not row:
            continue
        metadata, name = row.split("\t", 1)
        if metadata.startswith("160000 "):
            raise ValueError("submodule Git metadata unsupported; no silent omission")
        names.add(name)
    return sorted(names)  # Never exists(): a missing tracked entry is a tombstone.


def source_inventory(root: Path, names: list[str] | None = None):
    """lstat-based source state. No supported source link, even if dangling."""
    if root.resolve() != root or not root.is_dir():
        raise ValueError("unsafe source root ancestry")
    if names is None:
        names = ["."]

        def denied(error):
            raise error

        for directory, dirs, files in os.walk(root, followlinks=False, onerror=denied):
            if Path(directory) == root:
                dirs[:] = [name for name in dirs if name != ".git"]
            names.extend(
                (Path(directory) / name).relative_to(root).as_posix()
                for name in [*dirs, *files]
            )
    rows = {}
    for name in sorted(set(names)):
        path = Path(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != name
            or ".git" in path.parts
        ):
            raise ValueError("unsafe source input path")
        current = root
        missing = False
        for part in path.parts:
            current /= part
            try:
                info = current.lstat()
            except FileNotFoundError:
                missing = True
                break
            if stat.S_ISLNK(info.st_mode):
                raise ValueError(f"unsupported source link/ancestry: {current}")
            if current != root / path and not stat.S_ISDIR(info.st_mode):
                raise ValueError("unsafe source ancestor type")
        if missing:
            rows[name] = {"deleted": True}
        else:
            rows.update(inventory(root, [name]))
    return rows


def clone_source(run, repo: Path, destination: Path, head: str):
    source_inventory(repo, source_names(run, repo))  # Reject links before clone.
    admitted = source_index(repo)
    if not re.fullmatch("[0-9a-f]{40}", head):
        raise ValueError("invalid reviewed HEAD")
    if (
        destination.exists()
        or destination.is_symlink()
        or destination.resolve() != destination
    ):
        raise ValueError("fresh private clone destination required")
    view = metadata_view(repo)
    uses: list[dict] = []
    try:
        if index_data(view / "index")[0]["entries"] != admitted["entries"]:
            raise ValueError("source index drift before clone")
        view_call(
            run,
            uses,
            "private-clone",
            [
                "/usr/bin/git",
                "--no-pager",
                "-c",
                "protocol.file.allow=always",
                "clone",
                "--upload-pack=/usr/bin/git-upload-pack",
                "--no-local",
                "--no-checkout",
                str(view),
                str(destination),
            ],
            cwd=repo,
            env=GIT_ENV,
            timeout=600,
            capture=False,
        )
        shutil.copyfile(view / "config", destination / ".git/config")
        # Metadata only: never materialize unchecked HEAD files or links.
        # Pack staged blobs too: newly added OIDs need not be reachable from HEAD.
        # Git reads only the sanitized view and writes only this new private pack.
        if admitted["entries"]:
            oids = sorted(
                {row.split(" ", 2)[1] for row in admitted["entries"].split("\0") if row}
            )
            types = view_call(
                run,
                uses,
                "index-types",
                ["/usr/bin/git", f"--git-dir={view}", "cat-file", "--batch-check"],
                cwd=destination,
                env=GIT_ENV,
                input_bytes=("\n".join(oids) + "\n").encode(),
            ).splitlines()
            if len(types) != len(oids) or any(
                not re.fullmatch(oid + r" blob [0-9]+", row)
                for oid, row in zip(oids, types, strict=True)
            ):
                raise ValueError("missing/non-blob staged object")
            view_call(
                run,
                uses,
                "index-objects",
                [
                    "/usr/bin/git",
                    f"--git-dir={view}",
                    "pack-objects",
                    "--no-reuse-delta",
                    "--no-reuse-object",
                    str(destination / ".git/objects/pack/reviewed-index"),
                ],
                cwd=destination,
                env=GIT_ENV,
                timeout=600,
                input_bytes=("\n".join(oids) + "\n").encode(),
            )
        commands = [
            (["update-ref", "--no-deref", "HEAD", head], None),
            (["read-tree", "--empty"], None),
            (["update-index", "-z", "--index-info"], admitted["entries"].encode()),
        ]
        for command, stdin in commands:
            view_call(
                run,
                uses,
                "source-index",
                [
                    "/usr/bin/git",
                    "--no-pager",
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    "core.hooksPath=/dev/null",
                    *command,
                ],
                cwd=destination,
                env=GIT_ENV,
                timeout=600,
                capture=False,
                input_bytes=stdin,
            )
        if source_index(repo) != admitted:
            raise ValueError("source index drift during clone")
        if source_index(destination)["entries"] != admitted["entries"]:
            raise ValueError("private index reconstruction drift")
    finally:
        close_view(view, uses)
