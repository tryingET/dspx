"""Host-only canonical authority and bounded, owned process lifetimes.

Fake command results in tests are unit evidence, never native integration proof.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import uuid
from datetime import datetime, timezone

from verify_full_membership import claimed_id, strict_json
from verify_full_processes import HOST_ENV, Processes as Processes, Containers
from pathlib import Path
from verify_full_git import read_git
from verify_full_closure import validate_mount_targets, closure_mounts

G = "/home/tryinget/ai-society/softwareco/owned/agent-kernel/scripts/ak-runtime-gate.sh"


def canonical_claim(run, repo: Path, claimant: str, expected: int) -> int:
    output = run(
        "claim",
        [G, "--", "task", "list", "-s", "claimed", "-F", "json", "--verbose"],
        cwd=repo,
        env=HOST_ENV,
    )
    return claimed_id(strict_json(output), repo, claimant, expected)


def host_scope(run, repo: Path, claimant: str, expected: int):
    # Load only the stdlib-only scope module; no host site/.pth/DSPx import.
    path = repo / "packages/dspx-core/src/dspx/task_scope.py"
    spec = importlib.util.spec_from_file_location("_verify_full_task_scope", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("task scope loader unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # The gate entrypoint runs under -B; any other caller must not leave a
    # __pycache__ in the repository whose scope is about to be inspected.
    write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = write_bytecode

    def git_result(cmd, *, cwd):
        if not cmd or cmd[0] != "git":
            raise RuntimeError("scope attempted unexpected host command")
        codes: list[int] = []
        output = read_git(run, "scope-git", cmd[1:], cwd, check=False, status=codes)
        return subprocess.CompletedProcess(cmd, codes[0], output, "")

    def git_nul(cmd, *, cwd):
        result = git_result(["git", *cmd], cwd=cwd)
        if result.returncode:
            raise RuntimeError(result.stdout)
        return [name for name in result.stdout.split("\0") if name]

    setattr(module, "_run", git_result)
    setattr(module, "_git_output_nul", git_nul)
    result = module.check_task_scope(
        repo,
        mode="auto",
        claimed_task_resolver=lambda root: canonical_claim(
            run, root, claimant, expected
        ),
    )
    if not result.ok or result.task_id != expected:
        raise RuntimeError(module.format_scope_result(result))
    return {
        "task_id": result.task_id,
        "mode": result.mode,
        "changed_files": result.changed_files,
    }


def native_task5061(run, repo: Path):
    value = strict_json(
        run(
            "task5061",
            [G, "--", "task", "show", "5061", "--machine"],
            cwd=repo,
            env=HOST_ENV,
        )
    )
    if not isinstance(value, dict) or value.get("ok") is not True:
        raise ValueError("native task5061 machine response denied")
    task = value.get("payload", {}).get("task", {})
    if type(task.get("id")) is not int or task["id"] != 5061:
        raise ValueError("native task5061 response identity mismatch")
    return {
        "kind": "native-integration",
        "task_id": task["id"],
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


R = Path("/home/tryinget/ai-society/softwareco/owned/dspx")


class Docker(Containers):
    def preflight(self):
        info = strict_json(
            self.command("docker-info", ["info", "--format", "{{json .}} "])
        )
        if (
            any(
                "rootless" in str(item) or "userns" in str(item)
                for item in info.get("SecurityOptions", [])
            )
            or info.get("OSType") != "linux"
        ):
            raise ValueError("rootful native UID Docker required")
        images = strict_json(
            self.command("image-inspect", ["image", "inspect", self.review["image"]])
        )
        image = images[0]
        if image["Id"] != self.review["image"] or image["Config"].get("Volumes"):
            raise ValueError("image identity/implicit volumes rejected")
        for entry in image["Config"].get("Env") or []:
            if entry.split("=", 1)[0] not in {"PATH", "LANG", "LC_ALL"}:
                raise ValueError("unsafe image startup environment")

    def stage(
        self, name: str, argv: list[str], source: Path, state: Path, *, extra_env=None
    ):
        if self.environment is None:
            raise ValueError("closed fixture environment required")
        env = self.environment | (extra_env or {})
        state.mkdir(mode=0o700)
        for directory in ("home", "tmp", "oracle", "evidence", "reports"):
            (state / directory).mkdir()
        cidfile = self.job / f"{name}.cid"
        attempt = str(uuid.uuid4())
        container_name = f"dspx-full-{self.label}-{name}"
        args = [
            "create",
            "--name",
            container_name,
            "--label",
            f"dspx.verify-full.attempt={attempt}",
            "--pull=never",
            "--runtime=runc",
            "--user=1000:1000",
            "--network=none",
            "--ipc=private",
            "--cgroupns=private",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--read-only",
            "--pids-limit=1024",
            "--memory=12g",
            "--cpus=16",
            "--ulimit=nofile=4096:4096",
            "--log-driver=local",
            "--log-opt=max-size=128m",
            "--log-opt=max-file=1",
            "--log-opt=compress=false",
            "--label",
            f"dspx.verify-full={self.label}",
            "--cidfile",
            str(cidfile),
            "--workdir",
            str(R),
            "--entrypoint=/usr/bin/env",
        ]
        validate_mount_targets(self.review["closure"], R)
        if (source / ".git").is_symlink() or not (source / ".git").is_dir():
            raise ValueError("private Git metadata must be a directory")
        (state / "prek").mkdir()
        mounts = [
            (source, R, False),
            (source / ".git", R / ".git", True),
            (state, Path("/fixture"), False),
            (state / "prek", Path("/home/tryinget/.cache/prek"), False),
        ]
        mounts.extend(closure_mounts(self.prepared, self.review["closure"], R))
        for origin, destination, readonly in mounts:
            if origin.is_symlink() or origin.resolve() != origin:
                raise ValueError(
                    "bind origin must be a private concrete path, not an alias"
                )
            if "," in str(origin) or "," in str(destination):
                raise ValueError("invalid mount path")
            args += [
                "--mount",
                f"type=bind,src={origin},dst={destination}"
                + (",readonly" if readonly else ""),
            ]
        args += [
            self.review["image"],
            "-i",
            *(f"{key}={value}" for key, value in sorted(env.items())),
            *argv,
        ]
        intent = {
            "stage": name,
            "name": container_name,
            "attempt": attempt,
            "image": self.review["image"],
            "label": self.label,
            "mounts": [(str(a), str(b), ro) for a, b, ro in mounts],
            "command": args[args.index(self.review["image"]) + 1 :],
            "head": self.review.get("head"),
            "source": self.review.get("source"),
        }
        self.record_intent(intent)
        try:
            self.command(f"{name}-create", args)
        except BaseException:
            self.reconcile(intent, cidfile)
            raise
        cid = self.reconcile(intent, cidfile)
        self.started.add(name)
        self.event(name, "start-attempted", {"cid": cid})
        self.command(f"{name}-start", ["start", "--attach", cid], capture=False)
        terminal = strict_json(self.command(f"{name}-terminal", ["inspect", cid]))[0]
        if (
            terminal["State"]["Running"]
            or terminal["State"]["ExitCode"] != 0
            or terminal["State"]["OOMKilled"]
            or terminal["State"]["Error"]
        ):
            raise RuntimeError(f"{name}: container failed")
        self.remove(cid)
