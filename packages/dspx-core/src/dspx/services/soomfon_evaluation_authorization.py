"""Local execution projection reconciled against canonical read-only AK state."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

from dspx.services.soomfon_evaluation_owner import owner_authorization_identity

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_DISPATCH_RE = re.compile(r"^dispatch-[0-9]{10,20}$")
_OPERATOR_REQUEST_RE = re.compile(
    r"^operator-request-[A-Za-z0-9][A-Za-z0-9._:-]{7,95}$"
)
_MAX_BYTES = 64 * 1024


class SoomfonExecutionAuthorizationError(RuntimeError):
    """Fixed-message execution-authority rejection."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Soomfon execution authorization rejected: {reason}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ValidatedExecutionAuthorization:
    execution_task_id: int
    authorization_sha256: str
    repo: str
    contract_sha256: str
    maximum_provider_transports: int
    dspx_artifact: Mapping[str, Any]
    ak_reconciliation_sha256: str
    authorization_path: Path


def expected_owner_authorization_identity() -> dict[str, str]:
    return owner_authorization_identity()


def _read_stable(path: Path) -> bytes:
    candidate = path.expanduser()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(candidate, flags)
    except OSError as exc:
        raise SoomfonExecutionAuthorizationError("artifact unavailable") from exc
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > _MAX_BYTES
        ):
            raise SoomfonExecutionAuthorizationError("artifact posture")
        raw = os.read(fd, _MAX_BYTES + 1)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if len(raw) != before.st_size or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise SoomfonExecutionAuthorizationError("artifact changed")
    return raw


def _mapping(value: object, keys: set[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise SoomfonExecutionAuthorizationError(reason)
    return cast(dict[str, Any], dict(value))


def validate_execution_authorization(
    *,
    path: Path | None,
    expected_sha256: str | None,
    repo_root: Path,
    contract_sha256: str,
    minimum_lease_seconds: float = 1800.0,
) -> ValidatedExecutionAuthorization:
    if (
        path is None
        or not isinstance(expected_sha256, str)
        or _SHA256_RE.fullmatch(expected_sha256) is None
    ):
        raise SoomfonExecutionAuthorizationError("missing out-of-band digest")
    raw = _read_stable(path)
    observed = hashlib.sha256(raw).hexdigest()
    if observed != expected_sha256:
        raise SoomfonExecutionAuthorizationError("artifact digest")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SoomfonExecutionAuthorizationError("artifact JSON") from exc
    payload = _mapping(
        payload,
        {
            "schema_version",
            "producer",
            "execution_task_id",
            "repo",
            "contract_sha256",
            "dspx_artifact",
            "owner_artifact",
            "independent_reviews",
            "operator_authorization",
            "effect_budget",
            "authority_nonclaims",
        },
        "artifact schema",
    )
    producer = _mapping(
        payload["producer"],
        {"owner", "projection_schema", "projection_id"},
        "producer schema",
    )
    if (
        producer.get("owner") != "dspx-local-projection"
        or producer.get("projection_schema")
        != "soomfon-ak-reconciliation-projection-v3"
        or not isinstance(producer.get("projection_id"), str)
        or _ID_RE.fullmatch(producer["projection_id"]) is None
    ):
        raise SoomfonExecutionAuthorizationError("producer identity")
    task_id = payload.get("execution_task_id")
    root = repo_root.expanduser().resolve()
    if (
        payload.get("schema_version") != "soomfon-execution-authorization-v3"
        or isinstance(task_id, bool)
        or not isinstance(task_id, int)
        or task_id <= 4987
        or payload.get("repo") != str(root)
        or payload.get("contract_sha256") != contract_sha256
    ):
        reason = (
            "contract binding"
            if payload.get("contract_sha256") != contract_sha256
            else "task or repo binding"
        )
        raise SoomfonExecutionAuthorizationError(reason)
    dspx = _mapping(
        payload["dspx_artifact"],
        {
            "kind",
            "version",
            "commit",
            "tree",
            "wheel_sha256",
            "installed_payload_sha256",
        },
        "DSPx artifact schema",
    )
    if dspx.get("version") != "0.2.1":
        raise SoomfonExecutionAuthorizationError("DSPx version")
    if dspx.get("kind") == "reviewed_source_commit_tree":
        valid_dspx = (
            isinstance(dspx.get("commit"), str)
            and _GIT_RE.fullmatch(dspx["commit"]) is not None
            and isinstance(dspx.get("tree"), str)
            and _GIT_RE.fullmatch(dspx["tree"]) is not None
            and dspx.get("wheel_sha256") is None
            and dspx.get("installed_payload_sha256") is None
        )
    elif dspx.get("kind") == "installed_wheel_payload":
        valid_dspx = (
            dspx.get("commit") is None
            and dspx.get("tree") is None
            and isinstance(dspx.get("wheel_sha256"), str)
            and _SHA256_RE.fullmatch(dspx["wheel_sha256"]) is not None
            and isinstance(dspx.get("installed_payload_sha256"), str)
            and _SHA256_RE.fullmatch(dspx["installed_payload_sha256"]) is not None
        )
    else:
        valid_dspx = False
    if not valid_dspx:
        raise SoomfonExecutionAuthorizationError("DSPx artifact identity")
    owner = _mapping(
        payload["owner_artifact"],
        set(expected_owner_authorization_identity()),
        "owner artifact schema",
    )
    if owner != expected_owner_authorization_identity():
        raise SoomfonExecutionAuthorizationError("owner artifact identity")
    reviews_raw = payload.get("independent_reviews")
    if not isinstance(reviews_raw, list) or len(reviews_raw) != 2:
        raise SoomfonExecutionAuthorizationError("review evidence")
    reviews: list[dict[str, Any]] = []
    expected_review_identity = (
        ("review:independent-security", "ACCEPT"),
        ("test:independent-provider-free", "PASS"),
    )
    for index, raw_review in enumerate(reviews_raw):
        review = _mapping(
            raw_review,
            {"evidence_id", "check_type", "dispatch_id", "verdict"},
            "review evidence schema",
        )
        evidence_id = review.get("evidence_id")
        dispatch_id = review.get("dispatch_id")
        if (
            isinstance(evidence_id, bool)
            or not isinstance(evidence_id, int)
            or evidence_id < 1
            or (review.get("check_type"), review.get("verdict"))
            != expected_review_identity[index]
            or not isinstance(dispatch_id, str)
            or _DISPATCH_RE.fullmatch(dispatch_id) is None
        ):
            raise SoomfonExecutionAuthorizationError("review evidence")
        reviews.append(review)
    if (
        reviews[0]["evidence_id"] == reviews[1]["evidence_id"]
        or reviews[0]["dispatch_id"] == reviews[1]["dispatch_id"]
    ):
        raise SoomfonExecutionAuthorizationError("review evidence")
    operator = _mapping(
        payload["operator_authorization"],
        {"explicit", "evidence_id", "scope", "request_id"},
        "operator authorization schema",
    )
    if (
        operator.get("explicit") is not True
        or operator.get("scope") != "one_suite"
        or isinstance(operator.get("evidence_id"), bool)
        or not isinstance(operator.get("evidence_id"), int)
        or operator["evidence_id"] < 1
        or operator["evidence_id"] in {review["evidence_id"] for review in reviews}
        or not isinstance(operator.get("request_id"), str)
        or _OPERATOR_REQUEST_RE.fullmatch(operator["request_id"]) is None
        or operator["request_id"] in {review["dispatch_id"] for review in reviews}
    ):
        raise SoomfonExecutionAuthorizationError("operator authorization")
    budget = _mapping(
        payload["effect_budget"],
        {
            "suite_attempts",
            "cases",
            "logical_lm_calls_per_successful_case",
            "maximum_logical_lm_calls",
            "maximum_provider_transports",
            "retries",
            "fallbacks",
            "health_probes",
            "selective_reruns",
            "resume",
        },
        "effect budget schema",
    )
    expected_budget = {
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
    }
    if budget != expected_budget:
        raise SoomfonExecutionAuthorizationError("effect budget")
    nonclaims = _mapping(
        payload["authority_nonclaims"],
        {"routing", "promotion", "activation", "release", "publication"},
        "authority nonclaims schema",
    )
    if nonclaims != {key: False for key in nonclaims}:
        raise SoomfonExecutionAuthorizationError("authority nonclaims")
    from dspx.services.soomfon_evaluation_ak_authorization import (
        CanonicalAKAuthorizationError,
        reconcile_canonical_ak_authorization,
    )
    from dspx.services.soomfon_evaluation_dspx_identity import (
        SoomfonDSPxIdentityError,
        verify_executing_dspx_artifact,
    )

    try:
        canonical = reconcile_canonical_ak_authorization(
            task_id=task_id,
            repo=str(root),
            contract_sha256=contract_sha256,
            dspx_artifact=dspx,
            owner_artifact=owner,
            review_references=(reviews[0], reviews[1]),
            operator_evidence_id=operator["evidence_id"],
            operator_request_id=operator["request_id"],
            effect_budget=budget,
            minimum_lease_seconds=minimum_lease_seconds,
        )
    except CanonicalAKAuthorizationError as exc:
        raise SoomfonExecutionAuthorizationError("canonical AK state") from exc
    try:
        verify_executing_dspx_artifact(repo_root=root, artifact=dspx)
    except SoomfonDSPxIdentityError as exc:
        raise SoomfonExecutionAuthorizationError("DSPx executing identity") from exc
    return ValidatedExecutionAuthorization(
        execution_task_id=task_id,
        authorization_sha256=observed,
        repo=str(root),
        contract_sha256=contract_sha256,
        maximum_provider_transports=12,
        dspx_artifact=dspx,
        ak_reconciliation_sha256=canonical.reconciliation_sha256,
        authorization_path=path.expanduser().resolve(strict=True),
    )
