# summary: "Fail-closed tests for local projection and canonical AK authority."
from __future__ import annotations

import hashlib
import json
from typing import Any, cast
from pathlib import Path

import pytest

from dspx.services import soomfon_evaluation_authorization as authorization


REPO = Path(__file__).resolve().parents[1]
CONTRACT_SHA256 = "c" * 64


def _artifact(*, task_id: int = 6000) -> dict[str, Any]:
    return {
        "schema_version": "soomfon-execution-authorization-v3",
        "producer": {
            "owner": "dspx-local-projection",
            "projection_schema": "soomfon-ak-reconciliation-projection-v3",
            "projection_id": "local-projection-6000-suite-1",
        },
        "execution_task_id": task_id,
        "repo": str(REPO),
        "contract_sha256": CONTRACT_SHA256,
        "dspx_artifact": {
            "kind": "reviewed_source_commit_tree",
            "version": "0.2.1",
            "commit": "1" * 40,
            "tree": "2" * 40,
            "wheel_sha256": None,
            "installed_payload_sha256": None,
        },
        "owner_artifact": authorization.expected_owner_authorization_identity(),
        "independent_reviews": [
            {
                "evidence_id": 91001,
                "check_type": "review:independent-security",
                "dispatch_id": "dispatch-1787594193347",
                "verdict": "ACCEPT",
            },
            {
                "evidence_id": 91002,
                "check_type": "test:independent-provider-free",
                "dispatch_id": "dispatch-1787594193358",
                "verdict": "PASS",
            },
        ],
        "operator_authorization": {
            "explicit": True,
            "evidence_id": 91003,
            "scope": "one_suite",
            "request_id": "operator-request-soomfon-suite-6000",
        },
        "effect_budget": {
            "suite_attempts": 1,
            "cases": 6,
            "logical_lm_calls_per_successful_case": 2,
            "maximum_logical_lm_calls": 12,
            "maximum_provider_transports": 12,
            "retries": 0,
            "fallbacks": 0,
            "health_probes": 0,
            "selective_reruns": 0,
            "resume": False,
        },
        "authority_nonclaims": {
            "routing": False,
            "promotion": False,
            "activation": False,
            "release": False,
            "publication": False,
        },
    }


def _write(path: Path, payload: dict[str, object]) -> str:
    raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def test_valid_out_of_band_authorization_binds_one_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "authorization.json"
    digest = _write(path, _artifact())
    from types import SimpleNamespace
    from dspx.services import soomfon_evaluation_ak_authorization as ak_authorization
    from dspx.services import soomfon_evaluation_dspx_identity as dspx_identity

    monkeypatch.setattr(
        ak_authorization,
        "reconcile_canonical_ak_authorization",
        lambda **_: SimpleNamespace(reconciliation_sha256="a" * 64),
    )
    monkeypatch.setattr(
        dspx_identity, "verify_executing_dspx_artifact", lambda **_: None
    )

    result = authorization.validate_execution_authorization(
        path=path,
        expected_sha256=digest,
        repo_root=REPO,
        contract_sha256=CONTRACT_SHA256,
    )

    assert result.execution_task_id == 6000
    assert result.authorization_sha256 == digest
    assert result.maximum_provider_transports == 12
    assert result.ak_reconciliation_sha256 == "a" * 64


@pytest.mark.parametrize("expected", [None, "0" * 64])
def test_missing_or_forged_authorization_digest_fails_closed(
    tmp_path: Path, expected: str | None
) -> None:
    path = tmp_path / "authorization.json"
    _write(path, _artifact())
    with pytest.raises(authorization.SoomfonExecutionAuthorizationError):
        authorization.validate_execution_authorization(
            path=path,
            expected_sha256=expected,
            repo_root=REPO,
            contract_sha256=CONTRACT_SHA256,
        )


def test_task_5028_cannot_authorize_execution(tmp_path: Path) -> None:
    path = tmp_path / "authorization.json"
    digest = _write(path, _artifact(task_id=5028))
    with pytest.raises(
        authorization.SoomfonExecutionAuthorizationError, match="task or repo binding"
    ):
        authorization.validate_execution_authorization(
            path=path,
            expected_sha256=digest,
            repo_root=REPO,
            contract_sha256=CONTRACT_SHA256,
        )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda p: p.__setitem__("contract_sha256", "d" * 64), "contract"),
        (
            lambda p: p["owner_artifact"].__setitem__("wheel_sha256", "e" * 64),
            "owner",
        ),
        (
            lambda p: p["effect_budget"].__setitem__("maximum_provider_transports", 13),
            "budget",
        ),
        (
            lambda p: p["authority_nonclaims"].__setitem__("routing", True),
            "authority",
        ),
    ],
)
def test_stale_or_widened_authorization_is_rejected(
    tmp_path: Path, mutate, reason: str
) -> None:
    payload = _artifact()
    mutate(payload)
    path = tmp_path / "authorization.json"
    digest = _write(path, payload)
    with pytest.raises(authorization.SoomfonExecutionAuthorizationError, match=reason):
        authorization.validate_execution_authorization(
            path=path,
            expected_sha256=digest,
            repo_root=REPO,
            contract_sha256=CONTRACT_SHA256,
        )


def test_authorization_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    digest = _write(target, _artifact())
    link = tmp_path / "authorization.json"
    link.symlink_to(target)
    with pytest.raises(authorization.SoomfonExecutionAuthorizationError):
        authorization.validate_execution_authorization(
            path=link,
            expected_sha256=digest,
            repo_root=REPO,
            contract_sha256=CONTRACT_SHA256,
        )


def test_missing_authorization_refuses_before_marker_owner_import_or_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dspx.services import soomfon_evaluation_executor as executor
    from dspx.services import soomfon_evaluation_provider as provider

    state_root = tmp_path / "state"
    marker_calls: list[str] = []
    owner_calls: list[str] = []
    monkeypatch.setattr(executor, "_repo_root", lambda: REPO)
    monkeypatch.setattr(executor, "default_state_root", lambda: state_root)
    monkeypatch.setattr(
        authorization,
        "validate_execution_authorization",
        lambda **_: (_ for _ in ()).throw(
            authorization.SoomfonExecutionAuthorizationError("missing")
        ),
    )
    monkeypatch.setattr(
        executor,
        "_persist_attempt_before_effect",
        lambda **_: marker_calls.append("marker"),
    )
    monkeypatch.setattr(
        provider,
        "verify_soomfon_owner_source",
        lambda *_: owner_calls.append("owner"),
    )
    with pytest.raises(authorization.SoomfonExecutionAuthorizationError):
        executor.execute_soomfon_evaluation_suite(
            expected_contract_sha256=(
                "0f602482f29037d1a8f0c71731872390614198998d1fda94079172052cc29207"
            ),
            execution_authorization_path=None,
            expected_authorization_sha256=None,
            owner_source_root=REPO,
            environment={},
        )
    assert marker_calls == []
    assert owner_calls == []
    assert not state_root.exists()


def _machine_task(
    *,
    task_id: int,
    status: str,
    completed: bool = False,
    lease_seconds: int = 3600,
) -> dict[str, object]:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    return {
        "surface": "task.show",
        "schema_version": 1,
        "emitted_at": now.isoformat(),
        "payload_kind": "task_detail",
        "schema_locator": "ak machine schema task-show",
        "ok": True,
        "payload": {
            "task": {
                "id": task_id,
                "repo": str(REPO),
                "title": "bounded execution",
                "description": None,
                "status": status,
                "priority": 1,
                "claimed_by": "operator" if status == "claimed" else None,
                "claimed_at": now.isoformat() if status == "claimed" else None,
                "lease_expires_at": (now + timedelta(seconds=lease_seconds)).isoformat()
                if status == "claimed"
                else None,
                "depends_on": [5028] if task_id != 5028 else [4987],
                "evidence": None,
                "result": None,
                "created_at": now.isoformat(),
                "completed_at": now.isoformat() if completed else None,
                "scope": {
                    "allowed_paths": [],
                    "required_paths": [],
                    "forbidden_paths": [],
                },
                "entity_version": 1,
            }
        },
        "error": None,
    }


def _canonical_runner(
    payload: dict[str, Any], *, lease_seconds: int = 3600, task_status: str = "claimed"
):
    from dspx.services import soomfon_evaluation_ak_authorization as ak_authorization

    task_id = int(payload["execution_task_id"])
    reviews = payload["independent_reviews"]
    review_ids = [review["evidence_id"] for review in reviews]
    operator = payload["operator_authorization"]
    operator_id = operator["evidence_id"]
    common = {
        "schema_version": "soomfon-ak5028-authorization-evidence-v3",
        "preparation_task_id": 5028,
        "contract_sha256": payload["contract_sha256"],
        "dspx_artifact": payload["dspx_artifact"],
        "owner_artifact": payload["owner_artifact"],
        "requested_model": "codex/gpt-5.6-sol",
        "reasoning_effort": "max",
        "effect_budget": payload["effect_budget"],
        "ak_runtime": {
            "path": "/home/tryinget/.local/libexec/agent-kernel/c6297eccf67a3762ef01269f67e87eaa8828f127/ak-bin",
            "sha256": "61f6290115262e0319c3b178f053d74a486a3eba881aaa13739c1db45f0f6b91",
            "mode": "0555",
        },
    }
    check_types = {
        review_ids[0]: "review:independent-security",
        review_ids[1]: "test:independent-provider-free",
        operator_id: "authorization:operator-one-suite",
    }
    records = {}
    for evidence_id, check_type in check_types.items():
        details = dict(common)
        if evidence_id == operator_id:
            details["operator_request_id"] = operator["request_id"]
            details["explicit_one_suite_request"] = True
        else:
            review = reviews[review_ids.index(evidence_id)]
            details["review_dispatch_id"] = review["dispatch_id"]
            details["review_dispatch_verdict"] = review["verdict"]
        records[evidence_id] = {
            "id": evidence_id,
            "task_id": task_id,
            "task_ref": task_id,
            "repo": str(REPO),
            "repo_scope": str(REPO),
            "check_type": check_type,
            "result": "pass",
            "details": details,
            "checked_at": "2026-08-24 20:00:00+00:00",
            "checked_by": "cli",
        }
    contract = {
        "task_id": task_id,
        "repo": str(REPO),
        "title": "bounded execution",
        "status": "claimed",
        "done_contract": {
            "id": 1,
            "task_id": task_id,
            "entity_version": 1,
            "contract": ak_authorization.expected_execution_task_contract(),
            "created_at": "2026-08-24 20:00:00",
            "updated_at": "2026-08-24 20:00:00",
        },
        "guardrails": {
            "id": 2,
            "task_id": task_id,
            "entity_version": 1,
            "guardrails": ak_authorization.expected_execution_task_guardrails(),
            "created_at": "2026-08-24 20:00:00",
            "updated_at": "2026-08-24 20:00:00",
        },
    }

    def run(arguments: tuple[str, ...]) -> object:
        if arguments == ("task", "show", str(task_id), "--machine"):
            return _machine_task(
                task_id=task_id, status=task_status, lease_seconds=lease_seconds
            )
        if arguments == ("task", "show", "5028", "--machine"):
            return _machine_task(task_id=5028, status="done", completed=True)
        if arguments[:3] == ("task", "contract", "show"):
            return contract
        if arguments[:2] == ("evidence", "task"):
            return list(records.values())
        if arguments[:2] == ("evidence", "show"):
            return records[int(arguments[2])]
        raise AssertionError(arguments)

    return run


def test_canonical_ak_reconciliation_rejects_self_hashed_self_assertion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dspx.services import soomfon_evaluation_ak_authorization as ak_authorization
    from dspx.services import soomfon_evaluation_dspx_identity as dspx_identity

    path = tmp_path / "authorization.json"
    digest = _write(path, _artifact())
    monkeypatch.setattr(
        ak_authorization,
        "_run_ak_json",
        lambda *_: (_ for _ in ()).throw(
            ak_authorization.CanonicalAKAuthorizationError("unavailable")
        ),
    )
    monkeypatch.setattr(
        dspx_identity, "verify_executing_dspx_artifact", lambda **_: None
    )
    with pytest.raises(
        authorization.SoomfonExecutionAuthorizationError, match="canonical AK"
    ):
        authorization.validate_execution_authorization(
            path=path,
            expected_sha256=digest,
            repo_root=REPO,
            contract_sha256=CONTRACT_SHA256,
        )


@pytest.mark.parametrize("depends_on", [[], [4987], [5028, 4987]])
def test_canonical_ak_requires_exact_preparation_dependency(
    depends_on: list[int],
) -> None:
    import copy
    from dspx.services import soomfon_evaluation_ak_authorization as ak_authorization

    payload = _artifact()
    valid = _canonical_runner(payload)

    def drifted(arguments: tuple[str, ...]) -> object:
        value = valid(arguments)
        if arguments == ("task", "show", "6000", "--machine"):
            value = copy.deepcopy(value)
            value["payload"]["task"]["depends_on"] = depends_on
        return value

    with pytest.raises(ak_authorization.CanonicalAKAuthorizationError):
        ak_authorization.reconcile_canonical_ak_authorization(
            task_id=6000,
            repo=str(REPO),
            contract_sha256=CONTRACT_SHA256,
            dspx_artifact=payload["dspx_artifact"],
            owner_artifact=payload["owner_artifact"],
            review_references=tuple(payload["independent_reviews"]),
            operator_evidence_id=91003,
            operator_request_id=payload["operator_authorization"]["request_id"],
            effect_budget=payload["effect_budget"],
            minimum_lease_seconds=1800,
            runner=drifted,
        )


def test_live_completion_contract_binds_current_hash_and_preparation_task() -> None:
    from dspx.services import soomfon_evaluation_ak_authorization as ak_authorization

    contract = ak_authorization.expected_execution_task_contract()
    outcomes = cast(list[str], contract["required_outcomes"])
    assert outcomes[0] == (
        "Authorize exactly one six-case Soomfon suite for contract "
        "0f602482f29037d1a8f0c71731872390614198998d1fda94079172052cc29207 prepared under AK-5028"
    )


def test_canonical_ak_reconciliation_binds_task_contract_and_all_evidence() -> None:
    from dspx.services import soomfon_evaluation_ak_authorization as ak_authorization

    payload = _artifact()
    result = ak_authorization.reconcile_canonical_ak_authorization(
        task_id=6000,
        repo=str(REPO),
        contract_sha256=CONTRACT_SHA256,
        dspx_artifact=payload["dspx_artifact"],
        owner_artifact=payload["owner_artifact"],
        review_references=tuple(payload["independent_reviews"]),
        operator_evidence_id=91003,
        operator_request_id=payload["operator_authorization"]["request_id"],
        effect_budget=payload["effect_budget"],
        minimum_lease_seconds=1800,
        runner=_canonical_runner(payload),
    )
    assert result.evidence_ids == (91001, 91002, 91003)
    assert len(result.reconciliation_sha256) == 64


def test_canonical_ak_reconciliation_rejects_unattached_evidence() -> None:
    from dspx.services import soomfon_evaluation_ak_authorization as ak_authorization

    payload = _artifact()
    valid = _canonical_runner(payload)

    def unattached(arguments: tuple[str, ...]) -> object:
        value = valid(arguments)
        if arguments[:2] == ("evidence", "task"):
            return value[:-1]
        return value

    with pytest.raises(ak_authorization.CanonicalAKAuthorizationError):
        ak_authorization.reconcile_canonical_ak_authorization(
            task_id=6000,
            repo=str(REPO),
            contract_sha256=CONTRACT_SHA256,
            dspx_artifact=payload["dspx_artifact"],
            owner_artifact=payload["owner_artifact"],
            review_references=tuple(payload["independent_reviews"]),
            operator_evidence_id=91003,
            operator_request_id=payload["operator_authorization"]["request_id"],
            effect_budget=payload["effect_budget"],
            minimum_lease_seconds=1800,
            runner=unattached,
        )


def test_reviewed_source_identity_binds_loaded_origins_and_rejects_shadow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    from importlib.machinery import ModuleSpec
    from types import ModuleType
    from dspx.services import soomfon_evaluation_dspx_identity as identity

    identity.preload_security_critical_dspx_modules()
    monkeypatch.setattr(identity.sys, "dont_write_bytecode", True)
    monkeypatch.setattr(identity, "_verify_no_bytecode", lambda *_: None)
    artifact = {
        "kind": "reviewed_source_commit_tree",
        "version": "0.2.1",
        "commit": "1" * 40,
        "tree": "2" * 40,
        "wheel_sha256": None,
        "installed_payload_sha256": None,
    }

    def git_text(_root: Path, *arguments: str) -> str:
        if arguments[-1] == "HEAD^{commit}":
            return "1" * 40
        if arguments[-1] == "HEAD^{tree}":
            return "2" * 40
        if arguments[:2] == ("status", "--porcelain"):
            return ""
        raise AssertionError(arguments)

    def git_blob(root: Path, *arguments: str) -> bytes:
        assert arguments[0] == "show"
        relative = arguments[1].removeprefix("HEAD:")
        return (root / relative).read_bytes()

    monkeypatch.setattr(identity, "_git_text", git_text)
    monkeypatch.setattr(identity, "_git", git_blob)
    identity.verify_executing_dspx_artifact(repo_root=REPO, artifact=artifact)

    shadow_path = tmp_path / "soomfon_evaluation_shadow_probe.py"
    shadow_path.write_text("SHADOW = True\n")
    shadow = ModuleType("dspx.services.soomfon_evaluation_shadow_probe")
    shadow.__file__ = str(shadow_path)
    shadow.__spec__ = ModuleSpec(shadow.__name__, loader=None, origin=str(shadow_path))
    monkeypatch.setitem(sys.modules, shadow.__name__, shadow)
    with pytest.raises(identity.SoomfonDSPxIdentityError):
        identity.verify_executing_dspx_artifact(repo_root=REPO, artifact=artifact)


def test_child_revalidates_canonical_ak_then_loaded_provider_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace
    from dspx.services import soomfon_evaluation_authorization as auth
    from dspx.services import soomfon_evaluation_child as child
    from dspx.services import soomfon_evaluation_dspx_identity as identity

    events: list[str] = []
    artifact = _artifact()["dspx_artifact"]
    monkeypatch.setattr(
        auth,
        "validate_execution_authorization",
        lambda **_: (
            events.append("canonical"),
            SimpleNamespace(
                execution_task_id=6000,
                authorization_sha256="f" * 64,
                ak_reconciliation_sha256="e" * 64,
                dspx_artifact=artifact,
            ),
        )[1],
    )
    monkeypatch.setattr(
        identity,
        "preload_security_critical_dspx_modules",
        lambda: events.append("provider-modules-loaded"),
    )
    monkeypatch.setattr(
        identity,
        "verify_executing_dspx_artifact",
        lambda **_: events.append("loaded-bytes"),
    )
    child._revalidate_child_authorization(
        path=tmp_path / "projection.json",
        expected_sha256="f" * 64,
        repo_root=REPO,
        contract_sha256=CONTRACT_SHA256,
        execution_task_id=6000,
        ak_reconciliation_sha256="e" * 64,
    )
    assert events == [
        "canonical",
        "provider-modules-loaded",
        "loaded-bytes",
    ]


def test_installed_payload_identity_rejects_loaded_checkout_shadow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace
    from dspx.services import soomfon_evaluation_dspx_identity as identity

    identity.preload_security_critical_dspx_modules()
    monkeypatch.setattr(identity.sys, "dont_write_bytecode", True)
    monkeypatch.setattr(identity, "_verify_no_bytecode", lambda *_: None)
    modules = identity._loaded_critical_modules()
    relative = {
        name: identity._module_relative_path(name, module) for name, module in modules
    }
    source_root = REPO / "packages/dspx-core/src"

    class Distribution:
        version = "0.2.1"
        files = list(relative.values())

        @staticmethod
        def read_text(name: str) -> str:
            assert name == "direct_url.json"
            return json.dumps({"archive_info": {"hash": "sha256=" + "1" * 64}})

        @staticmethod
        def locate_file(item: object) -> Path:
            return source_root / str(item)

    monkeypatch.setattr(
        identity.importlib.metadata, "distribution", lambda _: Distribution()
    )
    monkeypatch.setattr(
        identity,
        "_record_digest",
        lambda *_: {"payload_sha256": "2" * 64},
    )
    artifact = {
        "kind": "installed_wheel_payload",
        "version": "0.2.1",
        "commit": None,
        "tree": None,
        "wheel_sha256": "1" * 64,
        "installed_payload_sha256": "2" * 64,
    }
    identity.verify_executing_dspx_artifact(repo_root=REPO, artifact=artifact)

    shadow_distribution = SimpleNamespace(
        version="0.2.1",
        files=list(relative.values()),
        read_text=Distribution.read_text,
        locate_file=lambda item: tmp_path / str(item),
    )
    monkeypatch.setattr(
        identity.importlib.metadata, "distribution", lambda _: shadow_distribution
    )
    with pytest.raises(identity.SoomfonDSPxIdentityError):
        identity.verify_executing_dspx_artifact(repo_root=REPO, artifact=artifact)


@pytest.mark.parametrize(
    ("minimum", "lease_seconds", "task_status"),
    [
        (1800, 1799, "claimed"),
        (90, 89, "claimed"),
        (90, 3600, "queued"),
    ],
)
def test_canonical_ak_rejects_short_lease_or_revocation(
    minimum: int, lease_seconds: int, task_status: str
) -> None:
    from dspx.services import soomfon_evaluation_ak_authorization as ak_authorization

    payload = _artifact()
    with pytest.raises(ak_authorization.CanonicalAKAuthorizationError):
        ak_authorization.reconcile_canonical_ak_authorization(
            task_id=6000,
            repo=str(REPO),
            contract_sha256=CONTRACT_SHA256,
            dspx_artifact=payload["dspx_artifact"],
            owner_artifact=payload["owner_artifact"],
            review_references=tuple(payload["independent_reviews"]),
            operator_evidence_id=91003,
            operator_request_id=payload["operator_authorization"]["request_id"],
            effect_budget=payload["effect_budget"],
            minimum_lease_seconds=minimum,
            runner=_canonical_runner(
                payload, lease_seconds=lease_seconds, task_status=task_status
            ),
        )


def test_projection_rejects_duplicate_review_dispatches(
    tmp_path: Path,
) -> None:
    payload = _artifact()
    payload["independent_reviews"][1]["dispatch_id"] = payload["independent_reviews"][
        0
    ]["dispatch_id"]
    path = tmp_path / "authorization.json"
    digest = _write(path, payload)
    with pytest.raises(
        authorization.SoomfonExecutionAuthorizationError, match="review evidence"
    ):
        authorization.validate_execution_authorization(
            path=path,
            expected_sha256=digest,
            repo_root=REPO,
            contract_sha256=CONTRACT_SHA256,
        )


def test_timestamp_valid_source_matching_pyc_is_rejected(tmp_path: Path) -> None:
    import py_compile
    from dspx.services import soomfon_evaluation_dspx_identity as identity

    package = tmp_path / "dspx"
    package.mkdir()
    source = package / "security_module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    cached = package / "__pycache__/security_module.cpython-313.pyc"
    cached.parent.mkdir()
    py_compile.compile(
        str(source),
        cfile=str(cached),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    assert cached.is_file()
    with pytest.raises(identity.SoomfonDSPxIdentityError):
        identity._verify_no_bytecode(package, ())


def test_pinned_ak_binary_is_hashed_and_executed_through_open_fd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dspx.services import soomfon_evaluation_ak_runtime as runtime

    real_popen = runtime.subprocess.Popen
    observed: dict[str, object] = {}

    def tracked_popen(argv, **kwargs):
        observed["argv"] = tuple(argv)
        observed["pass_fds"] = kwargs.get("pass_fds")
        return real_popen(argv, **kwargs)

    monkeypatch.setattr(runtime.subprocess, "Popen", tracked_popen)
    result = cast(
        dict[str, Any],
        runtime.run_ak_json(("task", "show", "5028", "--machine")),
    )
    assert result["payload"]["task"]["id"] == 5028
    argv = cast(tuple[str, ...], observed["argv"])
    passed = observed["pass_fds"]
    assert argv[0].startswith("/proc/self/fd/")
    assert passed == (int(argv[0].rsplit("/", 1)[1]),)


def test_pinned_ak_binary_digest_drift_rejects_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dspx.services import soomfon_evaluation_ak_runtime as runtime

    fake = tmp_path / "ak-bin"
    fake.write_bytes(b"not the pinned agent kernel")
    fake.chmod(0o555)
    monkeypatch.setattr(runtime, "AK_EXECUTABLE", fake)
    with pytest.raises(runtime.AKRuntimeIdentityError):
        runtime._open_verified_ak_executable()


def test_existing_loaded_module_cached_artifact_is_rejected(tmp_path: Path) -> None:
    from importlib.machinery import ModuleSpec
    from types import ModuleType
    from dspx.services import soomfon_evaluation_dspx_identity as identity

    package = tmp_path / "dspx"
    package.mkdir()
    cached = tmp_path / "security.pyc"
    cached.write_bytes(b"timestamp-valid-placeholder")
    module = ModuleType("dspx.services.soomfon_evaluation_security")
    module.__file__ = str(package / "security.py")
    setattr(module, "__cached__", str(cached))
    module.__spec__ = ModuleSpec(module.__name__, loader=None, origin=module.__file__)
    with pytest.raises(identity.SoomfonDSPxIdentityError):
        identity._verify_no_bytecode(package, ((module.__name__, module),))


def test_canonical_changed_evidence_record_rejects() -> None:
    import copy
    from dspx.services import soomfon_evaluation_ak_authorization as ak_authorization

    payload = _artifact()
    valid = _canonical_runner(payload)

    def changed(arguments: tuple[str, ...]) -> object:
        value = valid(arguments)
        if arguments == ("evidence", "show", "91002", "-F", "json"):
            value = copy.deepcopy(value)
            value["details"]["review_dispatch_verdict"] = "FAIL"
        return value

    with pytest.raises(ak_authorization.CanonicalAKAuthorizationError):
        ak_authorization.reconcile_canonical_ak_authorization(
            task_id=6000,
            repo=str(REPO),
            contract_sha256=CONTRACT_SHA256,
            dspx_artifact=payload["dspx_artifact"],
            owner_artifact=payload["owner_artifact"],
            review_references=tuple(payload["independent_reviews"]),
            operator_evidence_id=91003,
            operator_request_id=payload["operator_authorization"]["request_id"],
            effect_budget=payload["effect_budget"],
            minimum_lease_seconds=90,
            runner=changed,
        )


def test_parent_execution_preflight_requires_dont_write_bytecode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dspx.services import soomfon_evaluation_dspx_identity as identity

    monkeypatch.setattr(identity.sys, "dont_write_bytecode", False)
    with pytest.raises(identity.SoomfonDSPxIdentityError):
        identity.verify_executing_dspx_artifact(
            repo_root=REPO,
            artifact={
                "kind": "reviewed_source_commit_tree",
                "commit": "1" * 40,
                "tree": "2" * 40,
            },
        )


def test_owner_package_pyc_is_rejected_even_when_source_is_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dspx.services import soomfon_evaluation_owner as owner

    package = tmp_path / "src/dspy_lm_auth"
    package.mkdir(parents=True)
    (package / "lm.py").write_text("VALUE = 1\n", encoding="utf-8")
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "lm.cpython-313.pyc").write_bytes(b"source-matching-pyc")
    monkeypatch.setattr(owner.sys, "dont_write_bytecode", True)
    from dspx.services.provider_outcome_receipt_contract import (
        ProviderOutcomeConsumerError,
    )

    with pytest.raises(ProviderOutcomeConsumerError) as captured:
        owner._verify_owner_no_bytecode(tmp_path)
    assert captured.value.reason == "owner_bytecode_posture_drift"


def test_projection_rejects_operator_reuse_of_review_evidence_id(
    tmp_path: Path,
) -> None:
    payload = _artifact()
    payload["operator_authorization"]["evidence_id"] = payload["independent_reviews"][
        0
    ]["evidence_id"]
    path = tmp_path / "authorization.json"
    digest = _write(path, payload)
    with pytest.raises(
        authorization.SoomfonExecutionAuthorizationError,
        match="operator authorization",
    ):
        authorization.validate_execution_authorization(
            path=path,
            expected_sha256=digest,
            repo_root=REPO,
            contract_sha256=CONTRACT_SHA256,
        )
