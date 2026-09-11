"""Bounded host process groups, cancellation, output custody and reaping."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import tempfile
import threading
import time
import uuid

from verify_full_closure import strict_json

HOST_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/home/tryinget",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "TMPDIR": "/home/tryinget/.local/state/pi-quests/tmp",
}


class Processes:
    """Retain full output up to a hard disk budget; no silent truncation or retry.

    Cooperative custody only. Groups are kept until killed/reaped, even when the
    leader exits first. Cancellation is polled in every run, including parallel
    branches. Receipts/logs live outside disposable preparation/job directories.
    """

    def __init__(self, logs: Path, *, limit: int = 128 * 1024 * 1024, grace: float = 2):
        logs.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.logs, self.limit, self.grace = logs, limit, grace
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.groups: dict[int, subprocess.Popen] = {}
        self.sequence = 0

    @staticmethod
    def kill_group(pid: int, sig: int):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            pass

    def settle(self, process):
        self.kill_group(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=self.grace)
        except subprocess.TimeoutExpired:
            pass
        # Includes children left after the leader exited. Never touch unrelated groups.
        self.kill_group(process.pid, signal.SIGKILL)
        process.wait(timeout=self.grace)
        deadline = time.monotonic() + self.grace
        while True:
            try:
                while os.waitpid(-process.pid, os.WNOHANG)[0]:
                    pass
            except ChildProcessError:
                pass
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("unsettled owned process group; retain logs")
            time.sleep(0.01)
        with self.lock:
            self.groups.pop(process.pid, None)

    def run(
        self,
        label: str,
        argv: list[str],
        *,
        cwd: Path,
        env=None,
        timeout: float = 3600,
        capture: bool = True,
        cleanup: bool = False,
        check: bool = True,
        status: list[int] | None = None,
        settlement: dict | None = None,
        input_bytes: bytes | None = None,
    ) -> str:
        if input_bytes is not None and (
            not isinstance(input_bytes, bytes) or len(input_bytes) > 1024 * 1024
        ):
            raise ValueError("stdin budget/type exceeded")
        if settlement is not None:
            settlement.update({"settled": True, "pid": None})
        if self.cancelled.is_set() and not cleanup:
            raise RuntimeError("cancelled before stage startup")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", label):
            raise ValueError("unsafe log label")
        with self.lock:
            self.sequence += 1
            log = self.logs / f"{self.sequence:03d}-{label}.log"
        output = bytearray()
        count = 0
        process = None
        input_stream = None
        started = time.monotonic()
        terminal = "incomplete"
        try:
            with log.open("xb") as stream, selectors.DefaultSelector() as selector:
                if input_bytes is not None:
                    input_stream = tempfile.TemporaryFile(
                        dir=(env or HOST_ENV)["TMPDIR"]
                    )
                    input_stream.write(input_bytes)
                    input_stream.seek(0)
                if settlement is not None:
                    settlement["settled"] = False
                process = subprocess.Popen(
                    argv,
                    cwd=cwd,
                    env=env or HOST_ENV,
                    stdin=input_stream
                    if input_stream is not None
                    else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                if settlement is not None:
                    settlement["pid"] = process.pid
                with self.lock:
                    self.groups[process.pid] = process
                assert process.stdout is not None
                os.set_blocking(process.stdout.fileno(), False)
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map() or process.poll() is None:
                    if (
                        self.cancelled.is_set() and not cleanup
                    ) or time.monotonic() - started > timeout:
                        raise RuntimeError(f"{label}: cancellation/timeout")
                    for key, _ in selector.select(0.05):
                        block = os.read(key.fd, 65536)
                        if not block:
                            selector.unregister(key.fileobj)
                            continue
                        count += len(block)
                        if count > self.limit or (capture and count > 1024 * 1024):
                            raise RuntimeError(
                                f"{label}: output budget exceeded (not a pass)"
                            )
                        stream.write(block)
                        if capture:
                            output.extend(block)
                if (
                    self.cancelled.is_set() and not cleanup
                ) or time.monotonic() - started > timeout:
                    raise RuntimeError(f"{label}: cancellation/timeout after pipe EOF")
                code = process.wait(timeout=0.1)
                terminal = f"exit={code}"
                if status is not None:
                    status.append(code)
                if code and check:
                    raise RuntimeError(f"{label}: {terminal}; full output: {log}")
                return output.decode("utf-8", errors="strict")
        finally:
            if process is not None:
                self.settle(process)
                if process.stdout is not None:
                    process.stdout.close()
            if input_stream is not None:
                input_stream.close()
            if settlement is not None:
                settlement["settled"] = True
            if self.cancelled.is_set() and not cleanup:
                terminal = "cancelled"
            log.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "argv": argv,
                        "stdin_sha256": (
                            hashlib.sha256(input_bytes).hexdigest()
                            if input_bytes is not None
                            else None
                        ),
                        "status": terminal,
                        "bytes": count,
                        "elapsed": time.monotonic() - started,
                    }
                )
                + "\n"
            )

            if self.cancelled.is_set() and not cleanup:
                raise RuntimeError(f"{label}: cancellation during settlement")

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            groups = tuple(self.groups)
        for pid in groups:
            self.kill_group(pid, signal.SIGTERM)


class Containers:
    """Exact daemon object custody; create response loss is not permission to retry."""

    def __init__(self, run, review, prepared: Path, job: Path, *, environment=None):
        self.run, self.review, self.prepared, self.job = run, review, prepared, job
        self.environment = environment
        self.label = str(uuid.uuid4())
        self.cids: dict[str, str] = {}
        self.intents: dict[str, dict] = {}
        self.pending: set[str] = set()
        self.started: set[str] = set()
        self.settled = True

    def command(self, label, args, *, capture=True, cleanup=False, timeout=7200):
        return self.run(
            label,
            ["/usr/bin/docker", *args],
            cwd=Path("/home/tryinget/ai-society/softwareco/owned/dspx"),
            env=HOST_ENV,
            timeout=timeout,
            capture=capture,
            cleanup=cleanup,
        )

    def event(self, name, event, detail):
        path = self.job / f"{name}.intent.jsonl"
        with path.open("x" if event == "intent" else "a") as stream:
            stream.write(
                json.dumps({"event": event, "detail": detail}, sort_keys=True) + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(self.job, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def record_intent(self, intent):
        name = intent["stage"]
        if not re.fullmatch("[a-zA-Z0-9_-]+", name) or name in self.intents:
            raise ValueError("duplicate/unsafe container attempt")
        self.event(name, "intent", intent)  # Durable BEFORE daemon call.
        self.intents[name] = intent
        self.pending.add(name)
        self.settled = False

    def check_container(self, data, cid, mounts, command=None):
        host, config = data["HostConfig"], data["Config"]
        if command is not None and (
            config.get("Entrypoint") != ["/usr/bin/env"]
            or config.get("Cmd") != command
            or data["State"]["Running"]
        ):
            raise ValueError("container startup command/state drift")
        if command is not None and (
            host.get("Memory") != 12 * 1024**3
            or host.get("NanoCpus") != 16 * 10**9
            or host.get("PidsLimit") != 1024
        ):
            raise ValueError("container resource bounds drift")
        if (
            data["Id"] != cid
            or data["Image"] != self.review["image"]
            or config["Labels"].get("dspx.verify-full") != self.label
        ):
            raise ValueError("container identity mismatch")
        if (
            config["User"] != "1000:1000"
            or not host["ReadonlyRootfs"]
            or host["Privileged"]
            or host["NetworkMode"] != "none"
            or host["Runtime"] != "runc"
            or host.get("CapAdd")
            or host["CapDrop"] != ["ALL"]
        ):
            raise ValueError("unsafe container isolation")
        if (
            host.get("Devices")
            or host.get("DeviceRequests")
            or host.get("PidMode")
            or host.get("UsernsMode")
            or host["IpcMode"] != "private"
            or host.get("CgroupnsMode") != "private"
            or "no-new-privileges" not in host["SecurityOpt"]
        ):
            raise ValueError("host service/device/namespace exposure")
        actual = {
            (m["Source"], m["Destination"], not m["RW"])
            for m in data["Mounts"]
            if m["Type"] == "bind"
        }
        expected = {(str(a), str(b), ro) for a, b, ro in mounts}
        if len(data["Mounts"]) != len(expected) or actual != expected:
            raise ValueError("unexpected live mount")

    def identity(self, data, intent, cid):
        labels = data["Config"].get("Labels") or {}
        actual = {
            (m["Source"], m["Destination"], not m["RW"])
            for m in data["Mounts"]
            if m["Type"] == "bind"
        }
        if (
            data["Id"] != cid
            or data.get("Name") != "/" + intent["name"]
            or data["Image"] != intent["image"]
            or labels.get("dspx.verify-full") != intent["label"]
            or labels.get("dspx.verify-full.attempt") != intent["attempt"]
            or data["Config"].get("Cmd") != intent["command"]
            or data["Config"].get("Entrypoint") != ["/usr/bin/env"]
            or len(data["Mounts"]) != len(intent["mounts"])
            or actual != {tuple(m) for m in intent["mounts"]}
            or data["State"].get("Paused")
            or data["State"].get("Restarting")
        ):
            raise ValueError("container identity changed/protected; no removal")

    def reconcile(self, intent, cidfile):
        name = intent["stage"]
        try:
            if cidfile.exists():
                candidates = [cidfile.read_text().strip()]
            else:
                output = self.command(
                    "recover-create",
                    [
                        "ps",
                        "--all",
                        "--no-trunc",
                        "--filter",
                        f"name=^/{intent['name']}$",
                        "--filter",
                        f"label=dspx.verify-full={self.label}",
                        "--filter",
                        f"label=dspx.verify-full.attempt={intent['attempt']}",
                        "--format",
                        "{{.ID}}",
                    ],
                    cleanup=True,
                    timeout=30,
                )
                candidates = output.splitlines()
            self.event(name, "observed-candidates", {"ids": candidates})
            if len(candidates) != 1 or not re.fullmatch("[0-9a-f]{64}", candidates[0]):
                raise RuntimeError("absent/ambiguous create result; preserve intent")
            cid = candidates[0]
            data = strict_json(
                self.command(
                    "recover-inspect", ["inspect", cid], cleanup=True, timeout=30
                )
            )[0]
            self.identity(data, intent, cid)
            if data["State"].get("Status") != "created":
                raise ValueError("unexpected pre-start container state; protected")
            mounts = [(Path(a), Path(b), ro) for a, b, ro in intent["mounts"]]
            self.check_container(data, cid, mounts, intent["command"])
            self.event(name, "verified-created", {"cid": cid})
            self.cids[cid] = name
            self.pending.remove(name)
            return cid
        except BaseException as exc:
            self.event(name, "unsettled", {"error": str(exc)})
            raise

    def remove(self, cid):
        name = self.cids[cid]
        intent = self.intents[name]
        data = strict_json(
            self.command("cleanup-inspect", ["inspect", cid], cleanup=True, timeout=30)
        )[0]
        self.identity(data, intent, cid)
        if data["State"]["Running"]:
            if name not in self.started:
                raise ValueError("unadmitted running object is protected")
            try:
                self.command(
                    "cleanup-stop", ["stop", "--time=2", cid], cleanup=True, timeout=30
                )
            except RuntimeError:
                self.command("cleanup-kill", ["kill", cid], cleanup=True, timeout=30)
            data = strict_json(
                self.command(
                    "cleanup-stopped", ["inspect", cid], cleanup=True, timeout=30
                )
            )[0]
            self.identity(data, intent, cid)
            if data["State"]["Running"]:
                self.command("cleanup-kill", ["kill", cid], cleanup=True, timeout=30)
        self.command("cleanup-wait", ["wait", cid], cleanup=True, timeout=30)
        self.command("cleanup-remove", ["rm", cid], cleanup=True, timeout=30)
        self.event(name, "removed", {"cid": cid})
        del self.cids[cid]
        self.settled = not self.cids and not self.pending

    def close(self):
        failures = []
        for cid in tuple(self.cids):
            try:
                self.remove(cid)
            except Exception as exc:
                failures.append(str(exc))
        if failures or self.pending or not self.settled:
            raise RuntimeError(
                f"unsettled Docker effects; retain job: {failures}; pending={sorted(self.pending)}"
            )
