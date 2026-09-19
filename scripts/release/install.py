"""Read-only installation proof in fresh environments; never run in writer jobs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from artifacts import load_and_verify


def run(args: list[str], cwd: Path) -> None:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("PYTHONPATH", "PYTHONHOME", "PIP_", "UV_", "DSPX_"))
    }
    env.update(
        UV_NO_CONFIG="true", UV_NO_PROGRESS="1", MLFLOW_TRACKING_URI="file:./mlruns"
    )
    subprocess.run(args, cwd=cwd, env=env, check=True)


def prove(dist: Path, commit: str, digest: str, python: str, registry: bool) -> None:
    data = load_and_verify(dist, commit, digest)
    with tempfile.TemporaryDirectory(prefix="dspx-release-install-") as tmp:
        root = Path(tmp)
        for kind in ("wheel",) if registry else ("wheel", "sdist"):
            core = next(
                r
                for r in data["files"]
                if r["package"] == "dspx-core" and r["kind"] == kind
            )
            forge = next(
                r
                for r in data["files"]
                if r["package"] == "dspx-forge" and r["kind"] == kind
            )
            for package in ("dspx-core", "dspx-forge"):
                environment = root / f"{kind}-{package}"
                run(["uv", "venv", "--python", python, str(environment)], root)
                executable = environment / "bin/python"
                install = [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(executable),
                    "--index-url",
                    "https://pypi.org/simple",
                    "--no-sources",
                ]
                if registry:
                    # Do not provide a Core file or pin independently: prove that
                    # installing Forge from PyPI resolves its published Core bound.
                    targets = [f"{package}=={data['versions'][package]}"]
                else:
                    targets = [str(dist / core["filename"])]
                    if package == "dspx-forge":
                        targets.append(str(dist / forge["filename"]))
                    if kind == "sdist":
                        install += ["--no-binary", "dspx-core,dspx-forge"]
                run(install + targets, root)
                run(["uv", "pip", "check", "--python", str(executable)], root)
                check = (
                    "import importlib.metadata as m,json; "
                    f"assert m.version('dspx-core') == {data['versions']['dspx-core']!r}; "
                    "from dspx.server.app import app; assert app is not None; "
                )
                if package == "dspx-forge":
                    check += f"assert m.version('dspx-forge') == {data['versions']['dspx-forge']!r}; "
                else:
                    check += "assert not any(d.metadata['Name']=='dspx-forge' for d in m.distributions()); "
                check += "print(json.dumps({d.metadata['Name']:d.version for d in m.distributions()},sort_keys=True))"
                run([str(executable), "-I", "-c", check], root)
                command = "dspx-forge" if package == "dspx-forge" else "dspx"
                run([str(environment / "bin" / command), "--help"], root)
    print(
        json.dumps(
            {
                "commit": commit,
                "versions": data["versions"],
                "python": python,
                "registry_install": registry,
                "status": "pass",
                "live_provider_claim": False,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--python", choices=("3.13", "3.14"), required=True)
    parser.add_argument("--registry", action="store_true")
    args = parser.parse_args()
    prove(
        args.dist.resolve(),
        args.commit,
        args.manifest_sha256,
        args.python,
        args.registry,
    )
