"""Offline contract tests for the stdlib-only, read-only registry helper."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable
from email.message import Message
from http.client import IncompleteRead
from io import BytesIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/release/registry.py"
COMMIT = "a" * 40
MANIFEST_HASH = "b" * 64
PACKAGE = "dspx-core"
VERSION = "0.2.0"
JSON_URL = f"https://pypi.org/pypi/{PACKAGE}/{VERSION}/json"


class Response(BytesIO):
    def __init__(self, data: bytes, url: str, status: int = 200):
        super().__init__(data)
        self.url = url
        self.status = status

    def geturl(self) -> str:
        return self.url


@pytest.fixture
def module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_registry_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module, "build_opener", Mock(side_effect=AssertionError("unmocked network"))
    )
    monkeypatch.setattr(module.time, "sleep", Mock())
    return module


@pytest.fixture
def candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    dist = tmp_path / "dist"
    dist.mkdir()
    files = []
    for package in (PACKAGE, "dspx-forge"):
        stem = package.replace("-", "_")
        for kind, suffix in (("wheel", "-py3-none-any.whl"), ("sdist", ".tar.gz")):
            filename = f"{stem}-{VERSION}{suffix}"
            data = f"inert fixture {filename}".encode()
            (dist / filename).write_bytes(data)
            files.append(
                {
                    "filename": filename,
                    "package": package,
                    "version": VERSION,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                    "kind": kind,
                }
            )
    manifest = {
        "schema": "dspx-package-release-v1",
        "commit": COMMIT,
        "ak_scope_evidence": "fixture-only",
        "versions": {PACKAGE: VERSION, "dspx-forge": VERSION},
        "files": files,
        "extra_parent_validated_field": {"ignored": True},
    }
    (dist / "release-manifest.json").write_text(json.dumps(manifest))
    artifacts = ModuleType("artifacts")
    loader = Mock(return_value=manifest)
    monkeypatch.setattr(artifacts, "load_and_verify", loader, raising=False)
    monkeypatch.setitem(sys.modules, "artifacts", artifacts)
    return SimpleNamespace(
        dist=dist, stage=tmp_path / "stage", manifest=manifest, loader=loader
    )


@pytest.fixture
def network(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    queues: dict[str, list[Any]] = {}
    calls = []

    def enqueue(url: str, *results: Any) -> None:
        queues.setdefault(url, []).extend(results)

    def open_request(request: Any, *, timeout: int) -> Response:
        url = request.full_url
        calls.append(url)
        assert request.get_method() == "GET"
        assert request.data is None
        assert request.get_header("Accept-encoding") == "identity"
        assert timeout == 30
        assert url in queues and queues[url], f"unexpected request {url}"
        result = queues[url].pop(0)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, Response):
            return result
        if isinstance(result, dict):
            result = json.dumps(result).encode()
        return Response(result, url)

    def build(handler: Any) -> SimpleNamespace:
        assert isinstance(handler, module._NoRedirect)
        return SimpleNamespace(open=open_request)

    monkeypatch.setattr(module, "build_opener", build)
    return SimpleNamespace(enqueue=enqueue, calls=calls)


def payload(candidate: SimpleNamespace, package: str = PACKAGE) -> dict[str, Any]:
    return {
        "info": {"name": package, "version": VERSION},
        "urls": [
            {
                "filename": row["filename"],
                "size": row["bytes"],
                "digests": {"sha256": row["sha256"]},
                "yanked": False,
                "url": f"https://files.pythonhosted.org/packages/aa/{row['filename']}",
            }
            for row in candidate.manifest["files"]
            if row["package"] == package
        ],
    }


def run(module: ModuleType, candidate: SimpleNamespace, **kwargs: Any) -> dict:
    if not kwargs.get("verify") and "stage" not in kwargs:
        kwargs["stage"] = candidate.stage
    package = kwargs.pop("package", PACKAGE)
    return module.reconcile(candidate.dist, COMMIT, MANIFEST_HASH, package, **kwargs)


def http_error(code: int) -> HTTPError:
    return HTTPError(JSON_URL, code, "fixture", Message(), None)


@pytest.mark.parametrize("package", [PACKAGE, "dspx-forge"])
def test_absent_stages_only_selected_package(module, candidate, network, package):
    url = f"https://pypi.org/pypi/{package}/{VERSION}/json"
    network.enqueue(url, http_error(404))
    result = run(module, candidate, package=package)
    expected = {
        row["filename"]
        for row in candidate.manifest["files"]
        if row["package"] == package
    }
    assert result["state"] == "absent"
    assert result["missing"] == sorted(expected)
    assert result["stage"] == str(candidate.stage)
    assert result["downloads"] == []
    assert result["version"] == VERSION
    assert result["versions"] == candidate.manifest["versions"]
    assert {p.name for p in candidate.stage.iterdir()} == expected
    for name in expected:
        assert (candidate.stage / name).read_bytes() == (
            candidate.dist / name
        ).read_bytes()
    candidate.loader.assert_called_once_with(candidate.dist, COMMIT, MANIFEST_HASH)
    assert network.calls == [url]
    module.time.sleep.assert_not_called()


@pytest.mark.parametrize(
    "count,state", [(0, "partial_exact"), (1, "partial_exact"), (2, "exact")]
)
def test_stage_exact_subset(module, candidate, network, count, state):
    observed = payload(candidate)
    all_names = {row["filename"] for row in observed["urls"]}
    observed["urls"] = observed["urls"][:count]
    network.enqueue(JSON_URL, observed)
    result = run(module, candidate)
    missing = all_names - {row["filename"] for row in observed["urls"]}
    assert result["state"] == state
    assert result["missing"] == sorted(missing)
    assert {p.name for p in candidate.stage.iterdir()} == missing
    assert network.calls == [JSON_URL]


BAD_PAYLOADS: list[tuple[str, Callable[[dict], Any]]] = [
    ("extra", lambda p: p["urls"].append({"filename": "extra.whl"})),
    ("duplicate", lambda p: p["urls"].append(copy.deepcopy(p["urls"][0]))),
    ("hash", lambda p: p["urls"][0]["digests"].update(sha256="0" * 64)),
    ("size", lambda p: p["urls"][0].update(size=999)),
    ("size-bool", lambda p: p["urls"][0].update(size=True)),
    ("size-missing", lambda p: p["urls"][0].pop("size")),
    ("digests-missing", lambda p: p["urls"][0].pop("digests")),
    ("sha-missing", lambda p: p["urls"][0]["digests"].pop("sha256")),
    ("yanked", lambda p: p["urls"][0].update(yanked=True)),
    ("yank-missing", lambda p: p["urls"][0].pop("yanked")),
    ("yank-null", lambda p: p["urls"][0].update(yanked=None)),
    ("yank-zero", lambda p: p["urls"][0].update(yanked=0)),
    ("yank-string", lambda p: p["urls"][0].update(yanked="false")),
    ("name", lambda p: p["info"].update(name="dspx-forge")),
    ("version", lambda p: p["info"].update(version="0.3.0")),
    ("info-missing", lambda p: p.pop("info")),
    ("version-missing", lambda p: p["info"].pop("version")),
    ("urls-missing", lambda p: p.pop("urls")),
    ("urls-null", lambda p: p.update(urls=None)),
    ("urls-object", lambda p: p.update(urls={})),
    ("file-not-object", lambda p: p["urls"].append(None)),
    ("filename-missing", lambda p: p["urls"][0].pop("filename")),
    ("filename-unhashable", lambda p: p["urls"][0].update(filename=[])),
    ("url-missing", lambda p: p["urls"][0].pop("url")),
]


@pytest.mark.parametrize("verify", [False, True])
@pytest.mark.parametrize("label,change", BAD_PAYLOADS, ids=[x[0] for x in BAD_PAYLOADS])
def test_conflicts_fail_immediately(module, candidate, network, label, change, verify):
    observed = payload(candidate)
    change(observed)
    network.enqueue(JSON_URL, observed)
    with pytest.raises(module.RegistryError):
        run(module, candidate, verify=verify)
    assert not candidate.stage.exists()
    assert network.calls == [JSON_URL]
    module.time.sleep.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://files.pythonhosted.org/{name}",
        "https://files.pythonhosted.org.evil.test/{name}",
        "https://pypi.org/{name}",
        "https://files.pythonhosted.org@evil.test/{name}",
        "https://user@files.pythonhosted.org/{name}",
        "https://files.pythonhosted.org:443/{name}",
        "https://files.pythonhosted.org/{name}?query=1",
        "https://files.pythonhosted.org/{name}#fragment",
        "https://files.pythonhosted.org/wrong.whl",
        "https://files.pythonhosted.org/{name}%2Fevil",
        "https://files.pythonhosted.org/\n{name}",
        "https://[invalid/{name}",
    ],
)
def test_reject_untrusted_download_urls(module, candidate, network, url):
    observed = payload(candidate)
    observed["urls"][0]["url"] = url.format(name=observed["urls"][0]["filename"])
    network.enqueue(JSON_URL, observed)
    with pytest.raises(module.RegistryError, match="URL"):
        run(module, candidate, verify=True)
    assert network.calls == [JSON_URL]
    module.time.sleep.assert_not_called()


@pytest.mark.parametrize(
    "result",
    [
        http_error(500),
        http_error(403),
        http_error(429),
        http_error(302),
        URLError("offline"),
        TimeoutError("offline"),
        IncompleteRead(b"incomplete"),
        b"not JSON",
        b"\xff",
        b"[]",
        b"null",
        b'{"info":{},"info":{}}',
        b'{"bad":NaN}',
        Response(b"", JSON_URL, 204),
        Response(b"", "https://evil.test/json"),
    ],
)
def test_transport_and_json_errors_never_poll(module, candidate, network, result):
    network.enqueue(JSON_URL, result)
    with pytest.raises(module.RegistryError):
        run(module, candidate, verify=True)
    assert network.calls == [JSON_URL]
    module.time.sleep.assert_not_called()


def test_redirect_handler_does_not_follow(module):
    assert (
        module._NoRedirect().redirect_request(
            None, None, 302, "", {}, "https://evil.test"
        )
        is None
    )


def test_metadata_size_limit(module, candidate, network, monkeypatch):
    monkeypatch.setattr(module, "MAX_JSON_BYTES", 10)
    network.enqueue(JSON_URL, b" " * 11)
    with pytest.raises(module.RegistryError, match="byte limit"):
        run(module, candidate)
    assert not candidate.stage.exists()


def test_read_deadline(module, candidate, network, monkeypatch):
    monkeypatch.setattr(module.time, "monotonic", Mock(side_effect=[0, 0, 121]))
    network.enqueue(JSON_URL, payload(candidate))
    with pytest.raises(module.RegistryError, match="deadline"):
        run(module, candidate)


@pytest.mark.parametrize("existing", ["directory", "file", "symlink"])
def test_stage_must_be_new_and_never_overwrites(module, candidate, network, existing):
    if existing == "directory":
        candidate.stage.mkdir()
        (candidate.stage / "sentinel").write_bytes(b"keep")
    elif existing == "file":
        candidate.stage.write_bytes(b"keep")
    else:
        candidate.stage.symlink_to(candidate.dist, target_is_directory=True)
    before = {p.name: p.read_bytes() for p in candidate.dist.iterdir()}
    network.enqueue(JSON_URL, http_error(404))
    with pytest.raises(FileExistsError):
        run(module, candidate)
    assert {p.name: p.read_bytes() for p in candidate.dist.iterdir()} == before
    if existing == "directory":
        assert list(candidate.stage.iterdir()) == [candidate.stage / "sentinel"]
        assert (candidate.stage / "sentinel").read_bytes() == b"keep"
    elif existing == "file":
        assert candidate.stage.read_bytes() == b"keep"
    else:
        assert candidate.stage.is_symlink()


def test_artifact_failure_precedes_network_and_staging(module, candidate, network):
    candidate.loader.side_effect = ValueError("custody mismatch")
    with pytest.raises(ValueError, match="custody mismatch"):
        run(module, candidate)
    assert network.calls == []
    assert not candidate.stage.exists()


@pytest.mark.parametrize("change", ["same-size", "shorter", "longer", "missing"])
def test_source_change_cleans_failed_stage(module, candidate, network, change):
    names = sorted(
        row["filename"]
        for row in candidate.manifest["files"]
        if row["package"] == PACKAGE
    )
    source = candidate.dist / names[-1]  # First staged file must also be cleaned.
    data = source.read_bytes()
    if change == "missing":
        source.unlink()
    else:
        source.write_bytes(
            {
                "same-size": b"X" * len(data),
                "shorter": data[:-1],
                "longer": data + b"X",
            }[change]
        )
    network.enqueue(JSON_URL, http_error(404))
    with pytest.raises((module.RegistryError, FileNotFoundError)):
        run(module, candidate)
    assert not candidate.stage.exists()


def enqueue_downloads(network, candidate, observed):
    for row in observed["urls"]:
        network.enqueue(row["url"], (candidate.dist / row["filename"]).read_bytes())


def test_verify_exact_streams_hashes_without_retaining_files(
    module, candidate, network
):
    observed = payload(candidate)
    network.enqueue(JSON_URL, observed)
    enqueue_downloads(network, candidate, observed)
    result = run(module, candidate, verify=True)
    assert result["state"] == "exact"
    assert result["missing"] == []
    assert result["stage"] is None
    assert result["versions"] == candidate.manifest["versions"]
    assert len(result["downloads"]) == 2
    for proof in result["downloads"]:
        data = (candidate.dist / proof["filename"]).read_bytes()
        assert proof["sha256"] == hashlib.sha256(data).hexdigest()
        assert proof["bytes"] == len(data)
        assert proof["version"] == VERSION
        assert proof["package"] == PACKAGE
    assert list(candidate.dist.parent.iterdir()) == [candidate.dist]
    assert len(network.calls) == 3
    module.time.sleep.assert_not_called()


@pytest.mark.parametrize("bad", ["hash", "short", "long", "404", "500", "timeout"])
def test_download_failures_do_not_retry(module, candidate, network, bad):
    observed = payload(candidate)
    network.enqueue(JSON_URL, observed)
    row = sorted(observed["urls"], key=lambda r: r["filename"])[0]
    data = (candidate.dist / row["filename"]).read_bytes()
    replacement = {
        "hash": b"X" * len(data),
        "short": data[:-1],
        "long": data + b"X",
        "404": http_error(404),
        "500": http_error(500),
        "timeout": URLError("offline"),
    }[bad]
    network.enqueue(row["url"], replacement)
    with pytest.raises(module.RegistryError):
        run(module, candidate, verify=True)
    assert len(network.calls) == 2
    module.time.sleep.assert_not_called()


def test_verify_polls_only_visibility_then_downloads(module, candidate, network):
    exact = payload(candidate)
    partial = copy.deepcopy(exact)
    partial["urls"] = partial["urls"][:1]
    network.enqueue(JSON_URL, http_error(404), partial, exact)
    enqueue_downloads(network, candidate, exact)
    result = run(module, candidate, verify=True, attempts=3, delay=0)
    assert result["state"] == "exact"
    assert network.calls[:3] == [JSON_URL] * 3
    assert len(network.calls) == 5
    assert module.time.sleep.call_count == 2
    module.time.sleep.assert_called_with(0)


@pytest.mark.parametrize("state", ["absent", "partial_exact"])
def test_polling_bound_is_twelve_attempts(module, candidate, network, state):
    observed = payload(candidate)
    observed["urls"] = observed["urls"][:1]
    network.enqueue(
        JSON_URL,
        *[http_error(404) if state == "absent" else observed for _ in range(12)],
    )
    with pytest.raises(
        module.RegistryError, match=f"remains {state} after 12 attempts"
    ):
        run(module, candidate, verify=True)
    assert network.calls == [JSON_URL] * 12
    assert module.time.sleep.call_count == 11
    module.time.sleep.assert_called_with(10)


def test_conflict_after_absence_stops_polling(module, candidate, network):
    observed = payload(candidate)
    observed["urls"][0]["yanked"] = True
    network.enqueue(JSON_URL, http_error(404), observed)
    with pytest.raises(module.RegistryError, match="yanked"):
        run(module, candidate, verify=True)
    assert len(network.calls) == 2
    assert module.time.sleep.call_count == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"attempts": 0},
        {"attempts": 13},
        {"attempts": True},
        {"delay": -1},
        {"delay": 11},
        {"delay": float("nan")},
        {"delay": float("inf")},
        {"package": "other"},
        {"stage": None},
        {"verify": True, "stage": Path("forbidden")},
    ],
)
def test_invalid_configuration_fails_before_io(module, candidate, network, kwargs):
    with pytest.raises(module.RegistryError):
        run(module, candidate, **kwargs)
    assert not network.calls
    candidate.loader.assert_not_called()


def test_cli_machine_json(module, candidate, network, capsys):
    network.enqueue(JSON_URL, http_error(404))
    args = [
        "stage",
        "--dist",
        str(candidate.dist),
        "--commit",
        COMMIT,
        "--manifest-sha256",
        MANIFEST_HASH,
        "--package",
        PACKAGE,
        "--stage",
        str(candidate.stage),
    ]
    assert module.main(args) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["state"] == "absent"
    assert captured.err == ""
    candidate.loader.assert_called_once_with(candidate.dist, COMMIT, MANIFEST_HASH)


def test_cli_failure_has_no_success_json(module, candidate, network, capsys):
    network.enqueue(JSON_URL, http_error(500))
    assert (
        module.main(
            [
                "verify",
                "--dist",
                str(candidate.dist),
                "--commit",
                COMMIT,
                "--manifest-sha256",
                MANIFEST_HASH,
                "--package",
                PACKAGE,
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "HTTP 500" in json.loads(captured.err)["error"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("filename", "../escape.whl"),
        ("filename", "."),
        ("version", "other"),
        ("bytes", True),
        ("bytes", -1),
        ("bytes", 512 * 1024 * 1024 + 1),
    ],
)
def test_selected_artifact_bounds_before_network(
    module, candidate, network, field, value
):
    candidate.manifest["files"][0][field] = value
    with pytest.raises(module.RegistryError, match="invalid or oversized"):
        run(module, candidate)
    assert network.calls == []
    assert not candidate.stage.exists()


@pytest.mark.parametrize("duplicate", [False, True])
def test_expected_inventory_requires_two_unique_files(
    module, candidate, network, duplicate
):
    if duplicate:
        candidate.manifest["files"][1] = candidate.manifest["files"][0].copy()
    else:
        candidate.manifest["files"].pop(0)
    with pytest.raises(module.RegistryError, match="exactly two"):
        run(module, candidate)
    assert network.calls == []


def test_download_is_chunked_closed_and_bounded(module, network):
    data = b"inert" * 50000
    expected = {
        "filename": "fixture.whl",
        "package": PACKAGE,
        "version": VERSION,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    url = "https://files.pythonhosted.org/fixture.whl"

    class TrackingResponse(Response):
        def __init__(self, body):
            super().__init__(body, url)
            self.reads = []
            self.total = 0

        def read1(self, size=-1):
            self.reads.append(size)
            chunk = super().read1(size)
            self.total += len(chunk)
            return chunk

    exact = TrackingResponse(data)
    network.enqueue(url, exact)
    assert module._download(url, expected)["sha256"] == expected["sha256"]
    assert len(exact.reads) > 2
    assert max(exact.reads) <= module.CHUNK_BYTES
    assert exact.closed
    oversized = TrackingResponse(data + b"extra bytes that must not be fully read")
    network.enqueue(url, oversized)
    with pytest.raises(module.RegistryError, match="byte limit"):
        module._download(url, expected)
    assert oversized.total == len(data) + 1
    assert oversized.closed


def test_download_http_protocol_error_is_fail_closed(module, candidate, network):
    observed = payload(candidate)
    network.enqueue(JSON_URL, observed)
    first = min(observed["urls"], key=lambda row: row["filename"])
    network.enqueue(first["url"], IncompleteRead(b"partial"))
    with pytest.raises(module.RegistryError, match="download failed"):
        run(module, candidate, verify=True)
    assert len(network.calls) == 2
    module.time.sleep.assert_not_called()
