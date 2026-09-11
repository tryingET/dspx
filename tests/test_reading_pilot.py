"""Synthetic socket-server tests of the actual generated Core/DSPy runtime.

Run only in the task's offline bwrap namespace, never against host services.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time

import pytest

from dspx.services.reading_pilot import prepare_pilot, run_pilot
from dspx.services.reading_pilot_verification import (
    canonical,
    private_parent,
    public_spec,
    runtime_fingerprint,
    sha,
    verify_pilot,
)

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "examples/reading_pilot/intent.yaml"
SOURCE = b"SYNTHETIC_PASSAGE_SENTINEL: Small trials can reveal errors, but cannot establish universal reliability."
PURPOSE_A = "PURPOSE_A: design a cautious classroom experiment."
PURPOSE_B = "PURPOSE_B: evaluate a universal reliability claim."


def output_for(purpose: str = PURPOSE_A) -> dict:
    def claim(text: str = "Small trials offer limited evidence.") -> dict:
        return {
            "text": text,
            "uncertainty": "One invented passage only.",
            "evidence": [
                {
                    "locator": "paragraph-1",
                    "quote": "cannot establish universal reliability",
                    "quotation_status": "exact",
                }
            ],
        }

    return {
        "schema_version": "reading-pilot-output-v1",
        "passage_context": claim(),
        "purpose_guided_question": purpose,
        "L1_paraphrase": claim(),
        "L2_explication": {
            "main_point": claim(),
            "elaboration": claim(),
            "generated_example": "An invented classroom trial.",
            "generated_analogy": "A small sample.",
        },
        "L3_analysis": {
            k: claim()
            for k in (
                "purpose_in_source",
                "question",
                "information",
                "concepts",
                "assumptions",
                "inferences",
                "implications",
                "point_of_view",
            )
        },
        "L4_evaluation": {
            k: claim()
            for k in (
                "clarity",
                "accuracy",
                "precision",
                "relevance",
                "depth",
                "breadth",
                "logic",
                "significance",
                "fairness",
            )
        },
        "L5_author_perspective": {
            "simulation": "simulated_author_perspective_not_testimony",
            "question": "What is the limit?",
            "answer": claim(),
        },
        "L6_added_transfer": {
            "attribution": "added_L6_not_Paul_Elder",
            "proposed_use": purpose,
            "source_basis": claim(),
            "limits": "Not universal evidence.",
            "counterexample": "Unobserved failure.",
            "observable_test": "Record errors in a small trial.",
            "uncertainty": "Fixture only.",
            "canonical_apply_allowed": False,
        },
        "source_qualifiers": [claim()],
        "counterevidence_or_absence": claim(),
        "passage_synthesis": claim(),
        "whole_book_supported": False,
    }


class FixtureServer:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.mode = "valid"
        self.delay = 0.2
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                pass

            def do_POST(self) -> None:
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                payload = json.loads(raw)
                owner.requests.append(payload)
                if owner.mode == "timeout":
                    time.sleep(owner.delay)
                purpose = PURPOSE_B if PURPOSE_B in raw.decode() else PURPOSE_A
                output = output_for(purpose)
                if owner.mode == "badrefs":
                    output["L1_paraphrase"]["evidence"][0]["quote"] = "NOT IN SOURCE"
                text = (
                    canonical(output).decode()
                    if owner.mode != "malformed"
                    else "not JSON"
                )
                content = (
                    f"[[ ## reading_analysis_json ## ]]\n{text}\n[[ ## completed ## ]]"
                )
                if owner.mode == "chatbad":
                    content = "SYNTHETIC_RESPONSE_SENTINEL unparseable chat formatting"
                body = canonical(
                    {
                        "model": payload["model"],
                        "choices": [
                            {"message": {"role": "assistant", "content": content}}
                        ],
                    }
                )
                try:
                    self.send_response(500 if owner.mode == "http500" else 200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    if owner.mode == "trickle":
                        # Keep socket reads active while exceeding the explicit worker deadline.
                        for _ in range(100):
                            self.wfile.write(b" ")
                            self.wfile.flush()
                            time.sleep(0.1)
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.http.server_port}/v1"

    def close(self) -> None:
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()


@pytest.fixture
def server() -> Iterator[FixtureServer]:
    # An accidental ambient invocation must not contact even a host loopback server.
    if os.environ.get("READING_PILOT_ISOLATED_TESTS") != "1":
        pytest.skip("reading pilot requires the explicit offline bwrap test namespace")
    instance = FixtureServer()
    yield instance
    instance.close()


@pytest.fixture
def contract_data(tmp_path: Path, server: FixtureServer) -> tuple[Path, dict]:
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    data = {
        "schema_version": "reading-pilot-contract-v1",
        "campaign_id": "pilot-fixture",
        "parent_identity_sha256": private_parent(parent),
        "source_sha256": sha(SOURCE),
        "source_review_ref": "fixture-only-source-review-not-live-consent",
        "locators": [
            {
                "name": "paragraph-1",
                "start_byte": 0,
                "end_byte": len(SOURCE),
                "excerpt_sha256": sha(SOURCE),
            }
        ],
        "purposes": [{"id": "A", "text": PURPOSE_A}, {"id": "B", "text": PURPOSE_B}],
        "public_spec_sha256": sha(canonical(public_spec())),
        "template_sha256": sha(TEMPLATE.read_bytes()),
        "runtime_sha256": runtime_fingerprint(),
        "runtime_review_ref": "fixture-runtime-review",
        "operator_admission_ref": "synthetic-network-namespace-only-not-live-consent",
        "budget_review_ref": "fixture-budget-two",
        "max_dispatches": 2,
        "route": {
            "provider": "openai-compatible",
            "base_url": server.url,
            "model": "synthetic-fixture",
            "timeout_seconds": 30.0,
            "worker_deadline_seconds": 120.0,
            "server_output_limit_bytes": 200000,
            "server_config_sha256": sha(b"synthetic server bound"),
            "server_bound_review_ref": "fixture-reviewed-bound",
            "local_only_route_review_ref": "fixture-isolated-loopback",
        },
    }
    return parent, data


def prepare(data: tuple[Path, dict]):
    parent, contract = data
    digest = sha(canonical(contract))
    status = prepare_pilot(
        parent=parent,
        contract_payload=contract,
        source=SOURCE,
        template_bytes=TEMPLATE.read_bytes(),
        expected_contract_sha256=digest,
    )
    # Failures are local fixture diagnostics, never real corpus data.
    if status.state != "prepared":
        log = parent / contract["campaign_id"] / "prepare.log"
        pytest.fail(
            f"prepare: {status}; fixture log={log.read_text() if log.exists() else 'no log'}"
        )
    return status


def execute(data: tuple[Path, dict], prepared):
    parent, contract = data
    return run_pilot(
        parent=parent,
        campaign_id=contract["campaign_id"],
        expected_contract_sha256=sha(canonical(contract)),
        expected_candidate_sha256=prepared.candidate_sha256,
        candidate_review_ref="fixture-candidate-review",
        operator_admission_ref=contract["operator_admission_ref"],
    )


def verified(data: tuple[Path, dict], prepared, result):
    parent, contract = data
    return verify_pilot(
        parent=parent,
        campaign_id=contract["campaign_id"],
        expected_contract_sha256=sha(canonical(contract)),
        expected_candidate_sha256=prepared.candidate_sha256,
        expected_result_sha256=result.result_sha256,
    )


def test_native_ab_socket_dogfood(contract_data, server, capfd):
    protected = [
        REPO / "packages/dspx-core/src/dspx/services" / f"program_reading_{name}.py"
        for name in ("runtime", "contracts", "receipts")
    ]
    before = [sha(p.read_bytes()) for p in protected]
    prepared = prepare(contract_data)
    assert server.requests == []  # Native generation did not call the fixture.
    result = execute(contract_data, prepared)
    assert result.state == "completed", result
    assert result.dispatches == 2 and len(server.requests) == 2
    assert result.semantic_review == "needed"
    assert result.independent_provider_observation_required is True
    assert result.formatting == result.source_reference_integrity == "passed"
    assert verified(contract_data, prepared, result) == result
    parent, contract = contract_data
    root = parent / contract["campaign_id"]
    source_values = []
    for index, name in enumerate(("A", "B")):
        native = json.loads((root / name / "runtime_inputs.json").read_bytes())[
            "inputs"
        ]
        source_values.append(native["source_text"].encode())
        assert native["reader_purpose"] == (PURPOSE_A, PURPOSE_B)[index]
        evidence = json.loads((root / name / "behavior_results.json").read_bytes())[
            "provider"
        ]["effect_evidence"]
        assert (
            evidence["attempt_total"] == evidence["attempts"][0]["dispatch_count"] == 1
        )
        assert evidence["terminal_effect"] == "completed_success"
        assert (
            json.loads((root / f"{name}.intent.json").read_bytes())[
                "reserved_cumulative"
            ]
            == index + 1
        )
        request_text = json.dumps(server.requests[index], ensure_ascii=False)
        assert (PURPOSE_A, PURPOSE_B)[index] in request_text
        for term in (
            "L5_author_perspective",
            "added_L6_not_Paul_Elder",
            "additionalProperties",
            "observable_test",
        ):
            assert term in request_text
    assert source_values == [SOURCE, SOURCE]
    module = ast.parse((root / "candidate" / "module.py").read_text())
    predicts = [
        n
        for n in ast.walk(module)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "Predict"
    ]
    assert len(predicts) == 1
    for path in [root, *root.rglob("*")]:
        assert not path.is_symlink()
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
    assert [sha(p.read_bytes()) for p in protected] == before
    stdout, stderr = capfd.readouterr()
    assert "SYNTHETIC_PASSAGE_SENTINEL" not in stdout + stderr + str(asdict(result))
    assert "SYNTHETIC_RESPONSE_SENTINEL" not in stdout + stderr + str(asdict(result))
    assert execute(contract_data, prepared).state == "latched"
    assert len(server.requests) == 2


@pytest.mark.parametrize("mode", ["malformed", "chatbad", "badrefs", "http500"])
def test_bad_response_no_fallback_or_B(contract_data, server, mode, capfd):
    server.mode = mode
    prepared = prepare(contract_data)
    result = execute(contract_data, prepared)
    assert result.state == "failed", result
    assert len(server.requests) == result.dispatches == 1
    assert execute(contract_data, prepared).state == "latched"
    assert len(server.requests) == 1
    assert "SYNTHETIC_RESPONSE_SENTINEL" not in "".join(capfd.readouterr())


def test_http_timeout_latches_unknown_effect(contract_data, server):
    server.mode = "timeout"
    contract_data[1]["route"]["timeout_seconds"] = 0.02
    prepared = prepare(contract_data)
    result = execute(contract_data, prepared)
    assert result.state == "effect_indeterminate"
    assert result.dispatches == 1 and len(server.requests) == 1
    assert result.provider_effect == "effect_indeterminate"
    assert execute(contract_data, prepared).state == "latched"
    assert len(server.requests) == 1


def test_worker_deadline_after_dispatch_latches(contract_data, server):
    server.mode = "trickle"
    contract_data[1]["route"].update(timeout_seconds=0.3, worker_deadline_seconds=6.0)
    prepared = prepare(contract_data)
    result = execute(contract_data, prepared)
    assert result.state == "effect_indeterminate" and result.dispatches is None
    assert len(server.requests) == 1
    parent, data = contract_data
    root = parent / data["campaign_id"]
    assert (
        json.loads((root / "A.terminal.json").read_bytes())["effect"]
        == "effect_indeterminate"
    )
    assert not (root / "B.intent.json").exists()
    assert execute(contract_data, prepared).state == "latched"
    assert len(server.requests) == 1


@pytest.mark.parametrize(
    "missing",
    [
        "source_review_ref",
        "runtime_review_ref",
        "operator_admission_ref",
        "budget_review_ref",
        "runtime_sha256",
    ],
)
def test_missing_admission_zero_calls(contract_data, server, missing):
    parent, data = contract_data
    data.pop(missing)
    result = prepare_pilot(
        parent=parent,
        contract_payload=data,
        source=SOURCE,
        template_bytes=TEMPLATE.read_bytes(),
        expected_contract_sha256=sha(canonical(data)),
    )
    assert result.state == "rejected" and server.requests == []
    assert list(parent.iterdir()) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("base_url", "http://example.com/v1"),
        ("base_url", "http://localhost:8000/v1"),
        ("server_bound_review_ref", ""),
        ("server_output_limit_bytes", 0),
        ("worker_deadline_seconds", 1.0),
    ],
)
def test_bad_route_or_bound_zero_calls(contract_data, server, field, value):
    parent, data = contract_data
    data["route"][field] = value
    result = prepare_pilot(
        parent=parent,
        contract_payload=data,
        source=SOURCE,
        template_bytes=TEMPLATE.read_bytes(),
        expected_contract_sha256=sha(canonical(data)),
    )
    assert result.state == "rejected" and server.requests == []
    assert list(parent.iterdir()) == []


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:0{port}/v1",
        "http://127.0.0.1:{port}/v1?",
        "http://127.0.0.1:{port}/v1#",
        "http://127.0.0.1:{port}/v1?q=x",
        "http://127.0.0.1:{port}/v1#x",
        "http://@127.0.0.1:{port}/v1",
        "http://user:pw@127.0.0.1:{port}/v1",
        "HTTP://127.0.0.1:{port}/v1",
        "http://127.0.0.1:{port}/v1/",
        "http://127.0.0.1:{port}:/v1",
        "http://127.0.0.1:/v1",
        "http://[0:0:0:0:0:0:0:1]:{port}/v1",
        "http://[::1%lo]:{port}/v1",
        "http://127.0.0.1:0/v1",
    ],
)
def test_noncanonical_route_rejected_before_prepare(contract_data, server, url):
    parent, data = contract_data
    data["route"]["base_url"] = url.format(port=server.http.server_port)
    result = prepare_pilot(
        parent=parent,
        contract_payload=data,
        source=SOURCE,
        template_bytes=TEMPLATE.read_bytes(),
        expected_contract_sha256=sha(canonical(data)),
    )
    assert result.state == "rejected" and result.dispatches == 0
    assert server.requests == [] and list(parent.iterdir()) == []


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8000/v1", "http://127.0.0.1:80", "http://[::1]:8000/v1"]
)
def test_admitted_route_matches_native_canonical_form(contract_data, url):
    from dspx.openai_compatible_provider import _validated_endpoint
    from dspx.services.reading_pilot_verification import PilotContract

    data = contract_data[1]
    data["route"]["base_url"] = url
    assert (
        PilotContract.model_validate(data).route.base_url == _validated_endpoint(url)[0]
    )


@pytest.mark.parametrize(
    "mode,effect", [("valid", "completed_success"), ("http500", "completed_failure")]
)
def test_known_provider_effect_survives_later_readback_failure(
    contract_data, server, monkeypatch, capfd, mode, effect
):
    import dspx.services.reading_pilot as pilot
    from dspx.services.reading_pilot_verification import inventory

    server.mode = mode
    prepared = prepare(contract_data)
    native_verify = pilot.verify_case
    captured = {}

    def fail_after_native_readback(root, contract, index, observed_digest):
        observed = native_verify(root, contract, index, observed_digest)
        captured["native"] = inventory(root / "A")
        captured["provider"] = (root / "A.provider.json").read_bytes()
        assert observed["effect"] == effect and observed["dispatches"] == 1
        raise ValueError("SYNTHETIC_READBACK_SENTINEL")

    monkeypatch.setattr(pilot, "verify_case", fail_after_native_readback)
    result = execute(contract_data, prepared)
    parent, data = contract_data
    root = parent / data["campaign_id"]
    assert result.state == "failed_integrity" and result.integrity == "failed"
    assert (
        result.provider_effect == effect
        and result.dispatches == len(server.requests) == 1
    )
    assert not (root / "B.intent.json").exists()
    assert inventory(root / "A") == captured["native"]
    assert (root / "A.provider.json").read_bytes() == captured["provider"]
    terminal = json.loads((root / "A.terminal.json").read_bytes())
    assert terminal["effect"] == effect and terminal["dispatches"] == 1
    frozen = (root / "result.json").read_bytes()
    assert execute(contract_data, prepared).state == "latched"
    assert (root / "result.json").read_bytes() == frozen
    assert "SYNTHETIC_READBACK_SENTINEL" not in "".join(capfd.readouterr()) + str(
        asdict(result)
    )


def test_poisoned_ambient_discarded_in_native_worker(
    contract_data, server, monkeypatch, tmp_path
):
    poison = tmp_path / "poison"
    poison.mkdir(mode=0o700)
    (poison / "sitecustomize.py").write_text("raise RuntimeError('SYNTHETIC_POISON')\n")
    for key, value in {
        "HTTP_PROXY": "http://127.0.0.1:1",
        "HTTPS_PROXY": "http://127.0.0.1:1",
        "DSPX_PROVIDER": "removed",
        "DSPX_OPENAI_COMPAT_API_BASE": "http://127.0.0.1:1",
        "DSPX_OPENAI_COMPAT_API_KEY": "SYNTHETIC-ONLY",
        "MLFLOW_ENABLE": "1",
        "PYTHONPYCACHEPREFIX": str(poison / "bytecode"),
        "PYTHONPATH": str(poison),
    }.items():
        monkeypatch.setenv(key, value)
    prepared = prepare(contract_data)
    result = execute(contract_data, prepared)
    assert (
        result.state == "completed" and len(server.requests) == result.dispatches == 2
    )
    assert verified(contract_data, prepared, result) == result
    assert os.environ["DSPX_PROVIDER"] == "removed"  # Caller environment never mutated.
    assert not (poison / "bytecode").exists()


def test_cached_candidate_rejected_before_dispatch(contract_data, server):
    import py_compile

    prepared = prepare(contract_data)
    parent, data = contract_data
    candidate = parent / data["campaign_id"] / "candidate"
    py_compile.compile(
        str(candidate / "module.py"), cfile=str(candidate / "module.pyc"), doraise=True
    )
    result = execute(contract_data, prepared)
    assert result.state == "rejected" and server.requests == []
    assert not (candidate.parent / "started.json").exists()


@pytest.mark.parametrize(
    "mode",
    [
        "valid",
        "split",
        "missing",
        "truncated",
        "malformed",
        "uppercase",
        "extra",
        "oversized",
        "error",
        "deadline",
        "inherited_writer",
        "prepare",
    ],
)
def test_bounded_inherited_ipc_launcher(contract_data, monkeypatch, capfd, mode):
    import signal
    import sys

    import dspx.services.reading_pilot_custody as custody
    from dspx.services.reading_pilot_verification import PilotContract

    parent, data = contract_data
    data["route"].update(timeout_seconds=0.1, worker_deadline_seconds=1.5)
    contract = PilotContract.model_validate(data)
    popen = custody.subprocess.Popen
    pipe = os.pipe
    descriptors = []

    def tracked_pipe():
        fds = pipe()
        descriptors.extend(fds)
        return fds

    monkeypatch.setattr(custody.os, "pipe", tracked_pipe)
    launched = []
    monkeypatch.setenv("READING_PILOT_CUSTODY_FD", "1")
    monkeypatch.setenv("DSPX_CUSTODY_FD", "2")
    script = """
import os, sys, time
mode = sys.argv[1]
print("SYNTHETIC_PRIVATE_STDOUT", flush=True)
print("SYNTHETIC_PRIVATE_STDERR", file=sys.stderr, flush=True)
if mode == "prepare":
    assert len(sys.argv) == 2
    sys.exit(0)
fd = int(sys.argv[2])
assert fd > 2
payload = b"a" * 64 + b"\\n"
if mode == "inherited_writer":
    child = os.fork()
    if child == 0:
        time.sleep(60)
        os._exit(0)
    with open("descendant.pid", "w") as stream:
        stream.write(str(child))
    os.write(fd, payload)
    sys.exit(0)
if mode == "split":
    for byte in payload:
        os.write(fd, bytes([byte]))
elif mode == "oversized":
    os.write(fd, b"x" * 1000000)
elif mode != "missing":
    payload = {
        "truncated": payload[:-1], "malformed": b"g" * 64 + b"\\n",
        "uppercase": b"A" * 64 + b"\\n", "extra": payload + b"x",
    }.get(mode, payload)
    os.write(fd, payload)
if mode == "deadline":
    os.close(fd)
    time.sleep(60)
sys.exit(1 if mode == "error" else 0)
"""

    def synthetic_process(args, **kwargs):
        assert kwargs["stdout"] is kwargs["stderr"]
        assert "READING_PILOT_CUSTODY_FD" not in kwargs["env"]
        assert "DSPX_CUSTODY_FD" not in kwargs["env"]
        assert kwargs["start_new_session"] is True
        fds = kwargs["pass_fds"]
        assert fds == (() if mode == "prepare" else (int(args[-1]),))
        process = popen(
            [sys.executable, "-c", script, mode, *[str(fd) for fd in fds]], **kwargs
        )
        launched.append(process)
        return process

    monkeypatch.setattr(custody.subprocess, "Popen", synthetic_process)
    start = time.monotonic()
    result = custody._child(parent, contract, None if mode == "prepare" else "A")
    assert time.monotonic() - start < 10  # Only the fault probe has a wall-clock bound.
    assert len(launched) == 1 and launched[0].poll() is not None
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)
    assert "SYNTHETIC_PRIVATE" not in "".join(capfd.readouterr())
    if mode in ("valid", "split", "prepare"):
        assert result == custody.ChildOutcome(
            "returned", None if mode == "prepare" else "a" * 64
        )
    else:
        assert result.status != "returned" and result.observed_digest is None
    if mode == "inherited_writer":
        pid = int((parent / "descendant.pid").read_text())
        # Orphan zombies may await namespace init reaping, but must not remain running.
        for _ in range(100):
            stat = Path(f"/proc/{pid}/stat")
            if not stat.exists() or stat.read_text().split()[2] == "Z":
                break
            time.sleep(0.01)
        else:
            os.kill(pid, signal.SIGKILL)
            pytest.fail("owned descendant survived deadline cleanup")
    log = parent / ("prepare.log" if mode == "prepare" else "A.log")
    assert log.stat().st_mode & 0o777 == 0o600
    assert "SYNTHETIC_PRIVATE_STDOUT" in log.read_text()
    assert "SYNTHETIC_PRIVATE_STDERR" in log.read_text()


def test_custody_helper_actual_bytes_are_runtime_bound(monkeypatch):
    original = runtime_fingerprint()
    read_bytes = Path.read_bytes

    def changed_helper(path):
        raw = read_bytes(path)
        return (
            raw + b"# synthetic drift"
            if path.name == "reading_pilot_custody.py"
            else raw
        )

    monkeypatch.setattr(Path, "read_bytes", changed_helper)
    assert runtime_fingerprint() != original
