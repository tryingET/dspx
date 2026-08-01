# ---
# summary: "Tests Core wheel-only signing, policy selection, identity, and owner authorization."
# read_when:
#   - "Changing Decision 88 signer policy or release-authorization verification."
# ---

from __future__ import annotations

import base64
import copy
import importlib
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ObjectIdentifier

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts/ci"
POLICY_PATH = REPO_ROOT / "governance/release-signing/trust-policy-v001.json"
POLICY_V2_PATH = REPO_ROOT / "governance/release-signing/trust-policy-v002.json"
SELECTOR_V1_PATH = REPO_ROOT / "governance/release-signing/policy-selector-v001.json"
SELECTOR_V2_PATH = REPO_ROOT / "governance/release-signing/policy-selector-v002.json"
ROSTER_PATH = REPO_ROOT / "governance/release-signing/release-owner-roster-v001.json"


def _modules() -> tuple[ModuleType, ModuleType, ModuleType, ModuleType]:
    sys.path.insert(0, str(SCRIPTS))
    try:
        names = (
            "core_release_policy",
            "core_release_policy_live",
            "core_release_signing_identity",
            "core_release_signing",
        )
        modules = tuple(importlib.import_module(name) for name in names)
        assert len(modules) == 4
        return modules[0], modules[1], modules[2], modules[3]
    finally:
        sys.path.remove(str(SCRIPTS))


@pytest.fixture
def modules() -> tuple[ModuleType, ModuleType, ModuleType, ModuleType]:
    return _modules()


def _policy() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _policy_v2() -> dict[str, Any]:
    return json.loads(POLICY_V2_PATH.read_text(encoding="utf-8"))


def _roster() -> dict[str, Any]:
    return json.loads(ROSTER_PATH.read_text(encoding="utf-8"))


def _synthetic_bundle() -> tuple[dict[str, Any], dict[str, bytes]]:
    commit = "1" * 40
    source = {
        "git_commit": commit,
        "tree_state": "clean",
        "commit_binding_status": "commit_bound_clean_tree",
    }
    package = {"name": "dspx-core", "version": "0.1.0", "requires_python": ">=3.13"}
    values = {
        "dspx_core-0.1.0-py3-none-any.whl": b"wheel",
        "source.tar.gz": b"sdist",
        "installed.json": b"installed",
        "release.json": json.dumps({"source": source}).encode(),
        "wheel-sbom.json": b"wheel sbom",
        "environment-sbom.json": b"environment sbom",
    }
    roles = (
        ("core-wheel", "dspx_core-0.1.0-py3-none-any.whl"),
        ("core-sdist", "source.tar.gz"),
        ("installed-proof", "installed.json"),
        ("release-evidence", "release.json"),
        ("core-sbom", "wheel-sbom.json"),
        ("core-installed-environment-sbom", "environment-sbom.json"),
    )
    files = [
        {
            "role": role,
            "filename": name,
            "sha256": __import__("hashlib").sha256(values[name]).hexdigest(),
            "size": len(values[name]),
        }
        for role, name in roles
    ]
    manifest = {
        "schema_version": "dspx-core-release-bundle-v3",
        "source": source,
        "package": package,
        "files": files,
    }
    values["bundle-manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
    return manifest, values


def _statement(signing: ModuleType, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    manifest, payloads = _synthetic_bundle()
    monkeypatch.setattr(signing, "_bundle_payloads", lambda _path: (manifest, payloads))
    monkeypatch.setattr(signing, "_git_bytes", lambda *_args: b"workflow")
    return signing.build_statement(
        bundle_path=Path("bundle.zip"),
        policy=_policy(),
        repo_root=REPO_ROOT,
        run_id=123,
        run_attempt=2,
        workflow_commit_sha="1" * 40,
    )


def test_policy_and_unbound_roster_are_exact_and_fail_closed(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
) -> None:
    policy, _live, _identity, _signing = modules
    valid = policy.validate_policy(_policy())
    assert valid["policy_version"] == 1
    assert valid["claims"]["release_authority"] is False
    roster = policy.validate_roster(_roster())
    assert roster["authorization_enabled"] is False
    with pytest.raises(policy.CoreReleaseEvidenceError, match="three distinct"):
        policy.validate_roster(_roster(), require_bindings=True)

    drifted = _policy()
    del drifted["workload"]["certificate_extensions"]["1.3.6.1.4.1.57264.1.24"]
    with pytest.raises(policy.CoreReleaseEvidenceError, match="OID coverage"):
        policy.validate_policy(drifted)

    future = _policy()
    future["effective_at"] = "2999-01-01T00:00:00Z"
    with pytest.raises(policy.CoreReleaseEvidenceError, match="future"):
        policy.validate_policy(future)


def test_policy_v2_requires_exact_numeric_fulcio_subject(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
) -> None:
    policy, _live, _identity, _signing = modules
    valid = policy.validate_policy(_policy_v2())
    expected = (
        "repo:tryingET@260287438/dspx@1318473695:environment:core-release-evidence"
    )
    assert valid["policy_version"] == 2
    assert valid["workload"]["token_subject"] == expected
    assert (
        valid["workload"]["certificate_extensions"]["1.3.6.1.4.1.57264.1.24"]
        == expected
    )
    assert valid["claims"]["release_authority"] is False

    old_subject = _policy_v2()
    old_subject["workload"]["certificate_extensions"]["1.3.6.1.4.1.57264.1.24"] = (
        "repo:tryingET/dspx:environment:core-release-evidence"
    )
    with pytest.raises(policy.CoreReleaseEvidenceError, match="dynamic"):
        policy.validate_policy(old_subject)


def test_statement_has_one_wheel_subject_and_typed_sdist_auxiliary(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _policy_module, _live, _identity, signing = modules
    statement = _statement(signing, monkeypatch)

    assert statement["subject"] == [
        {
            "name": "dspx_core-0.1.0-py3-none-any.whl",
            "digest": {
                "sha256": "ba59926159d2aa256eb8739b8da7e2b574b960e1202c6d624cbe981cef996c91"
            },
        }
    ]
    auxiliary = statement["predicate"]["auxiliary_evidence"]
    assert [entry["role"] for entry in auxiliary] == list(
        _policy_module.AUXILIARY_ROLES
    )
    assert auxiliary[-1]["role"] == "unsigned_unsupported_distribution_evidence"
    assert auxiliary[-1]["name"].endswith(".tar.gz")
    assert statement["predicate"]["claims"]["release_authority"] is False
    assert signing.validate_statement(statement, policy=_policy()) == statement


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["subject"].append(copy.deepcopy(value["subject"][0])),
            "exactly one",
        ),
        (
            lambda value: value["subject"][0].update({"name": "source.tar.gz"}),
            "Core wheel",
        ),
        (
            lambda value: value["predicate"]["workflow"].update(
                {"event": "pull_request"}
            ),
            "workflow drift",
        ),
        (
            lambda value: value["predicate"]["claims"].update(
                {"release_authority": True}
            ),
            "authority claims",
        ),
        (
            lambda value: value["predicate"]["auxiliary_evidence"][-1].update(
                {"role": "supported-sdist"}
            ),
            "auxiliary roles",
        ),
    ],
)
def test_statement_rejects_subject_identity_and_authority_widening(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    message: str,
) -> None:
    _policy_module, _live, _identity, signing = modules
    statement = _statement(signing, monkeypatch)
    mutation(statement)
    with pytest.raises(signing.CoreReleaseEvidenceError, match=message):
        signing.validate_statement(statement, policy=_policy())


def test_statement_requires_clean_same_commit_workflow(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _policy_module, _live, _identity, signing = modules
    manifest, payloads = _synthetic_bundle()
    manifest["source"]["tree_state"] = "dirty"
    monkeypatch.setattr(signing, "_bundle_payloads", lambda _path: (manifest, payloads))
    with pytest.raises(signing.CoreReleaseEvidenceError, match="clean commit-bound"):
        signing.build_statement(
            bundle_path=Path("bundle.zip"),
            policy=_policy(),
            repo_root=REPO_ROOT,
            run_id=1,
            run_attempt=1,
            workflow_commit_sha="1" * 40,
        )

    manifest["source"]["tree_state"] = "clean"
    with pytest.raises(signing.CoreReleaseEvidenceError, match="cross-commit"):
        signing.build_statement(
            bundle_path=Path("bundle.zip"),
            policy=_policy(),
            repo_root=REPO_ROOT,
            run_id=1,
            run_attempt=1,
            workflow_commit_sha="2" * 40,
        )


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _selector_repo(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    repo = tmp_path / "repo"
    policy_path = repo / "governance/release-signing/trust-policy-v001.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(json.dumps(_policy(), indent=2) + "\n", encoding="utf-8")
    _git(repo.parent, "init", str(repo))
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "policy")
    commit = _git(repo, "rev-parse", "HEAD")
    blob = _git(
        repo, "rev-parse", f"{commit}:governance/release-signing/trust-policy-v001.json"
    )
    raw = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "show",
            f"{commit}:governance/release-signing/trust-policy-v001.json",
        ],
        capture_output=True,
        check=True,
    ).stdout
    selector = {
        "schema_version": "dspx-core-policy-selector-v1",
        "repository": {
            "name": "tryingET/dspx",
            "id": 1_318_473_695,
            "repo_scope": "/home/tryinget/ai-society/softwareco/owned/dspx",
        },
        "policy": {
            "version": 1,
            "path": "governance/release-signing/trust-policy-v001.json",
            "commit": commit,
            "blob_oid": blob,
            "file_sha256": __import__("hashlib").sha256(raw).hexdigest(),
        },
        "accepting_decision_id": 90,
        "supersession": {
            "supersedes_decision_id": None,
            "supersedes_policy_version": None,
        },
    }
    return repo, selector


def test_selector_verifies_exact_git_blob_and_chain(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    policy, live, _identity, _signing = modules
    repo, selector = _selector_repo(tmp_path)
    assert policy.validate_selector(selector, repo_root=repo) == selector
    selected = live.resolve_selector_chain([(90, selector, "selector-ref")])
    assert selected[0] == 90

    drifted = copy.deepcopy(selector)
    drifted["policy"]["file_sha256"] = "0" * 64
    with pytest.raises(policy.CoreReleaseEvidenceError, match="digest drift"):
        policy.validate_selector(drifted, repo_root=repo)

    with pytest.raises(policy.CoreReleaseEvidenceError, match="version fork"):
        live.resolve_selector_chain(
            [(90, selector, "first"), (91, copy.deepcopy(selector), "second")]
        )


def test_selector_v2_forms_gapless_exact_supersession_chain(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
) -> None:
    policy, live, _identity, _signing = modules
    selector_v1 = json.loads(SELECTOR_V1_PATH.read_text(encoding="utf-8"))
    selector_v2 = json.loads(SELECTOR_V2_PATH.read_text(encoding="utf-8"))

    assert policy.validate_selector(selector_v1, repo_root=REPO_ROOT) == selector_v1
    assert policy.validate_selector(selector_v2, repo_root=REPO_ROOT) == selector_v2
    selected = live.resolve_selector_chain(
        [(90, selector_v1, "selector-v1"), (92, selector_v2, "selector-v2")]
    )
    assert selected == (92, selector_v2, "selector-v2")


def test_checkpoint_is_atomic_integrity_checked_and_rejects_rollback(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    policy, live, _identity, _signing = modules
    checkpoint = tmp_path / "state" / "policy.json"
    real_fsync = live.os.fsync
    fsynced_types: list[int] = []

    def record_fsync(descriptor: int) -> None:
        fsynced_types.append(stat.S_IFMT(os.fstat(descriptor).st_mode))
        real_fsync(descriptor)

    monkeypatch.setattr(live.os, "fsync", record_fsync)
    result = live.advance_checkpoint(checkpoint, version=2, reference="selector-v2")
    assert result["highest_policy_version"] == 2
    assert checkpoint.stat().st_mode & 0o777 == 0o600
    assert fsynced_types == [stat.S_IFREG, stat.S_IFDIR]

    with pytest.raises(policy.CoreReleaseEvidenceError, match="below the highest"):
        live.advance_checkpoint(checkpoint, version=1, reference="selector-v1")

    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["highest_policy_version"] = 3
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(policy.CoreReleaseEvidenceError, match="integrity drift"):
        live.advance_checkpoint(checkpoint, version=3, reference="selector-v3")


def _bound_roster() -> dict[str, Any]:
    roster = _roster()
    roster["bindings"] = [
        {
            "role": role,
            "principal": f"https://github.com/users/{index}",
            "authentication": "github-oidc-or-owner-approved-equivalent",
            "authority_ref": "AK-999",
            "valid_from": "2026-07-31T00:00:00Z",
            "expires_at": "2027-07-31T00:00:00Z",
            "withdrawn": False,
        }
        for index, role in enumerate(roster["roles"], start=1)
    ]
    roster["authorization_enabled"] = True
    roster["disabled_reason"] = None
    return roster


def _approval(role: str, principal: str, expected: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "dspx-core-release-owner-approval-v1",
        "roster_version": "dspx-core-release-owners-v1",
        "policy_version": 1,
        "role": role,
        "principal": principal,
        "payload": expected,
        "created_at": "2026-07-31T00:00:00Z",
        "expires_at": "2026-08-02T00:00:00Z",
        "authority_ref": "AK-1000",
        "withdrawn": False,
    }


def test_two_of_three_approval_is_separate_and_fail_closed(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
) -> None:
    policy, _live, _identity, _signing = modules
    roster = _bound_roster()
    expected = {
        "policy_version": 1,
        "wheel_sha256": "a" * 64,
        "bundle_manifest_sha256": "b" * 64,
        "signed_statement_sha256": "c" * 64,
        "source_commit_sha": "d" * 40,
        "package_version": "0.1.0",
        "roster_version": "dspx-core-release-owners-v1",
        "authority_ref": "AK-1000",
    }
    first = _approval(roster["roles"][0], roster["bindings"][0]["principal"], expected)
    second = _approval(roster["roles"][1], roster["bindings"][1]["principal"], expected)
    one = policy.validate_approvals(
        [first],
        roster=roster,
        expected=expected,
        now=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert one["release_authority"] is False
    two = policy.validate_approvals(
        [first, second],
        roster=roster,
        expected=expected,
        now=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert two["structural_threshold_satisfied"] is True
    assert two["approval_authentication_status"] == "owner_authorized_adapter_required"
    assert two["evidence_authenticity_required"] is True
    assert two["current_custody_required"] is True
    assert two["release_authority"] is False
    assert two["package_publication"] is False

    widened = {**expected, "release_authority": True}
    with pytest.raises(policy.CoreReleaseEvidenceError, match="payload fields"):
        policy.validate_approvals(
            [first, second],
            roster=roster,
            expected=widened,
            now=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )

    duplicate = copy.deepcopy(second)
    duplicate["principal"] = first["principal"]
    with pytest.raises(policy.CoreReleaseEvidenceError, match="ambiguous"):
        policy.validate_approvals(
            [first, duplicate],
            roster=roster,
            expected=expected,
            now=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )


def _der_text(value: str) -> bytes:
    raw = value.encode()
    assert len(raw) < 128
    return bytes([0x0C, len(raw)]) + raw


def _certificate_bundle(
    policy_value: dict[str, Any], statement: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    configured = policy_value["workload"]["certificate_extensions"]
    predicate = statement["predicate"]
    workflow = predicate["workflow"]
    dynamic = {
        "$source_commit_sha": predicate["source"]["commit_sha"],
        "$workflow_commit_sha": workflow["workflow_commit_sha"],
        "$run_invocation_uri": (
            "https://github.com/tryingET/dspx/actions/runs/"
            f"{workflow['run_id']}/attempts/{workflow['run_attempt']}"
        ),
    }
    facts = {oid: dynamic.get(value, value) for oid, value in configured.items()}
    key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(minutes=5))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.UniformResourceIdentifier(facts["2.5.29.17"])]
            ),
            critical=False,
        )
    )
    for index in range(8, 25):
        oid = f"1.3.6.1.4.1.57264.1.{index}"
        builder = builder.add_extension(
            x509.UnrecognizedExtension(ObjectIdentifier(oid), _der_text(facts[oid])),
            critical=False,
        )
    certificate = builder.sign(key, hashes.SHA256())
    payload = base64.b64encode(json.dumps(statement, sort_keys=True).encode()).decode()
    bundle = {
        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "verificationMaterial": {
            "certificate": {
                "rawBytes": base64.b64encode(
                    certificate.public_bytes(serialization.Encoding.DER)
                ).decode()
            }
        },
        "dsseEnvelope": {
            "payload": payload,
            "payloadType": "application/vnd.in-toto+json",
            "signatures": [{"sig": "AA=="}],
        },
    }
    return bundle, facts


def test_certificate_identity_covers_all_generic_oids_and_dynamic_values(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, _live, identity, signing = modules
    statement = _statement(signing, monkeypatch)
    bundle, facts = _certificate_bundle(_policy(), statement)
    assert identity.certificate_facts(bundle) == facts
    verified = identity.validate_certificate_identity(
        facts=facts, policy=_policy(), statement=statement
    )
    assert verified["status"] == "exact_identity_verified"

    drifted = dict(facts)
    drifted["1.3.6.1.4.1.57264.1.22"] = "private"
    with pytest.raises(policy.CoreReleaseEvidenceError, match="1.22"):
        identity.validate_certificate_identity(
            facts=drifted, policy=_policy(), statement=statement
        )


def test_sigstore_verification_requires_pinned_root_and_cosign_success(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    policy, _live, identity, signing = modules
    statement = _statement(signing, monkeypatch)
    bundle, _facts = _certificate_bundle(_policy(), statement)
    statement_path = tmp_path / "statement.json"
    bundle_path = tmp_path / "bundle.json"
    subject_path = tmp_path / "subject.whl"
    root_path = tmp_path / "trusted_root.json"
    policy_path = tmp_path / "policy.json"
    authenticated_statement_raw = json.dumps(statement, sort_keys=True).encode()
    statement_path.write_bytes(authenticated_statement_raw)
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    subject_path.write_bytes(b"wheel")
    root_path.write_bytes(b"pinned root fixture")
    policy_path.write_text(json.dumps(_policy()), encoding="utf-8")
    expected_root = _policy()["sigstore"]["trusted_root_sha256"]
    real_sha256 = identity.sha256
    monkeypatch.setattr(
        identity,
        "sha256",
        lambda raw: (
            expected_root if raw == b"pinned root fixture" else real_sha256(raw)
        ),
    )
    monkeypatch.setattr(
        identity.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="verified", stderr=""
        ),
    )

    result = identity.verify_sigstore_bundle(
        statement_path=statement_path,
        bundle_path=bundle_path,
        subject_path=subject_path,
        policy_path=policy_path,
        trusted_root_path=root_path,
    )
    assert result["status"] == "verified"
    assert result["release_authority"] is False

    statement_path.write_text(json.dumps(statement, indent=2), encoding="utf-8")
    with pytest.raises(policy.CoreReleaseEvidenceError, match="byte drift"):
        identity.verify_sigstore_bundle(
            statement_path=statement_path,
            bundle_path=bundle_path,
            subject_path=subject_path,
            policy_path=policy_path,
            trusted_root_path=root_path,
        )
    statement_path.write_bytes(authenticated_statement_raw)

    monkeypatch.setattr(identity, "sha256", real_sha256)
    with pytest.raises(policy.CoreReleaseEvidenceError, match="trusted root digest"):
        identity.verify_sigstore_bundle(
            statement_path=statement_path,
            bundle_path=bundle_path,
            subject_path=subject_path,
            policy_path=policy_path,
            trusted_root_path=root_path,
        )


def test_current_denylist_invalidates_previously_valid_statement(
    modules: tuple[ModuleType, ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, _live, _identity, signing = modules
    statement = _statement(signing, monkeypatch)
    current = _policy()
    current["deny"]["workflow_run_ids"] = [123]
    raw = json.dumps(statement, sort_keys=True).encode()
    with pytest.raises(policy.CoreReleaseEvidenceError, match="denied"):
        signing.enforce_denylist(statement=statement, statement_raw=raw, policy=current)
