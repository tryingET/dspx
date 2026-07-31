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
