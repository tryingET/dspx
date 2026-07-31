#!/usr/bin/env python3
# ---
# summary: "Classifies GitHub artifact upload observations without guessing provider effects."
# read_when:
#   - "Changing Core evidence upload retry or effect-indeterminate semantics."
# ---

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

OBSERVATION_SCHEMA = "dspx-github-artifact-observation-v1"


def classify_upload_observation(
    *, operation_outcome: str, observation: object, expected_name: str, run_id: int
) -> dict[str, Any]:
    if not isinstance(observation, Mapping):
        return {"status": "effect_indeterminate", "retry_allowed": False}
    if (
        observation.get("schema_version") != OBSERVATION_SCHEMA
        or observation.get("query_status") != "success"
        or observation.get("run_id") != run_id
        or observation.get("complete") is not True
    ):
        return {"status": "effect_indeterminate", "retry_allowed": False}
    artifacts = observation.get("artifacts")
    if not isinstance(artifacts, list):
        return {"status": "effect_indeterminate", "retry_allowed": False}
    matches = [
        item
        for item in artifacts
        if isinstance(item, Mapping) and item.get("name") == expected_name
    ]
    if len(matches) == 1:
        artifact = matches[0]
        artifact_id = artifact.get("id")
        if (
            artifact.get("expired") is not False
            or not isinstance(artifact_id, int)
            or isinstance(artifact_id, bool)
            or artifact_id <= 0
        ):
            return {"status": "effect_indeterminate", "retry_allowed": False}
        return {
            "status": "observed_success",
            "retry_allowed": False,
            "artifact": dict(artifact),
        }
    if len(matches) > 1:
        return {"status": "effect_indeterminate", "retry_allowed": False}
    if operation_outcome == "failure":
        return {"status": "confirmed_absent", "retry_allowed": True}
    return {"status": "effect_indeterminate", "retry_allowed": False}


def verify_artifact_pair_availability(
    *,
    evidence_artifact: Mapping[str, Any],
    receipt_artifact_id: int,
    receipt_provider_digest: str,
    observation: object,
) -> dict[str, Any]:
    if (
        not isinstance(receipt_artifact_id, int)
        or isinstance(receipt_artifact_id, bool)
        or receipt_artifact_id <= 0
        or len(receipt_provider_digest) != 71
        or not receipt_provider_digest.startswith("sha256:")
        or any(
            character not in "0123456789abcdef"
            for character in receipt_provider_digest[7:]
        )
        or not isinstance(observation, Mapping)
        or observation.get("schema_version") != OBSERVATION_SCHEMA
        or observation.get("query_status") != "success"
        or observation.get("complete") is not True
    ):
        return {"status": "effect_indeterminate", "release_use_custody": False}
    artifacts = observation.get("artifacts")
    if not isinstance(artifacts, list):
        return {"status": "effect_indeterminate", "release_use_custody": False}
    expected = {
        evidence_artifact.get("id"): evidence_artifact.get("provider_digest"),
        receipt_artifact_id: receipt_provider_digest,
    }
    if len(expected) != 2 or None in expected:
        return {"status": "effect_indeterminate", "release_use_custody": False}
    for artifact_id, digest in expected.items():
        matches = [
            item
            for item in artifacts
            if isinstance(item, Mapping) and item.get("id") == artifact_id
        ]
        if not matches:
            return {"status": "confirmed_absent", "release_use_custody": False}
        if len(matches) != 1:
            return {"status": "effect_indeterminate", "release_use_custody": False}
        if matches[0].get("expired") is not False or matches[0].get("digest") != digest:
            return {
                "status": "digest_or_expiry_drift",
                "release_use_custody": False,
            }
    return {"status": "current", "release_use_custody": True}
