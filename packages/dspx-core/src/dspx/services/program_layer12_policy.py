"""DSPx-owned advisory contracts for the SF14 Layer-12 generated-program boundary.

These pure checkers produce empirical evidence only. They never establish AK legality,
select a transition token or policy, mutate a candidate, or authorize activation/apply.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMAS = {
    "score": "layer12-advisory-score-vector-v1",
    "policy": "layer12-advisory-aggregate-policy-v1",
    "compatibility": "layer12-execution-compatibility-v1",
    "cohort": "layer12-comparison-cohort-v1",
    "metric_receipt": "layer12-dspx-metric-receipt-v1",
    "comparison_receipt": "layer12-comparison-receipt-v1",
    "shadow": "layer12-dspx-policy-shadow-evidence-v1",
}
IDENTITY_FIELDS = (
    "protocol_version",
    "transition_token",
    "family_id",
    "spec_digest",
    "candidate_id",
    "ak_eval_receipt_id",
)


class Layer12PolicyError(ValueError):
    """A Layer-12 advisory contract is malformed, unbound, or incompatible."""


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Layer12PolicyError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _closed(value: Mapping[str, Any], *, required: set[str], label: str) -> None:
    missing = required - set(value)
    extra = set(value) - required
    if missing or extra:
        raise Layer12PolicyError(
            f"{label} fields mismatch; missing={sorted(missing)} extra={sorted(extra)}"
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Layer12PolicyError(f"{label} must be non-empty text")
    return value


def _number(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Layer12PolicyError(f"{label} must be a finite number")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise Layer12PolicyError(f"{label} must be a finite number") from exc
    if not number.is_finite():
        raise Layer12PolicyError(f"{label} must be finite")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Layer12PolicyError(f"{label} must be a positive integer")
    if not math.isfinite(value) or not float(value).is_integer() or value < 1:
        raise Layer12PolicyError(f"{label} must be a positive integer")
    return int(value)


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Layer12PolicyError(f"{label} must be a nonnegative integer")
    if not math.isfinite(value) or not float(value).is_integer() or value < 0:
        raise Layer12PolicyError(f"{label} must be a nonnegative integer")
    return int(value)


def _time(value: object, label: str) -> datetime:
    text = _text(value, label)
    if (
        re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
            text,
        )
        is None
    ):
        raise Layer12PolicyError(f"{label} must be RFC3339")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Layer12PolicyError(f"{label} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise Layer12PolicyError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _identity(value: object, label: str = "identity") -> dict[str, str]:
    identity = _object(value, label)
    _closed(identity, required=set(IDENTITY_FIELDS), label=label)
    result = {
        field: _text(identity[field], f"{label}.{field}") for field in IDENTITY_FIELDS
    }
    if result["protocol_version"] != "layer12-v1":
        raise Layer12PolicyError("mixed or unsupported protocol_version")
    return result


def _same_identity(
    left: Mapping[str, str], right: Mapping[str, str], label: str
) -> None:
    if left != right:
        raise Layer12PolicyError(f"{label} identity mismatch")


def check_execution_compatibility(contract: object, *, now: str) -> dict[str, Any]:
    item = _object(contract, "compatibility")
    required = {
        "schema_version",
        "identity",
        "runtime_digest",
        "dataset_digest",
        "metric_set_digest",
        "observed_at",
        "expires_at",
        "live_evaluation_replayable",
    }
    _closed(item, required=required, label="compatibility")
    if item["schema_version"] != SCHEMAS["compatibility"]:
        raise Layer12PolicyError("unsupported compatibility schema")
    identity = _identity(item["identity"])
    for field in ("runtime_digest", "dataset_digest", "metric_set_digest"):
        _text(item[field], field)
    observed = _time(item["observed_at"], "observed_at")
    expires = _time(item["expires_at"], "expires_at")
    current = _time(now, "now")
    if observed > current or expires <= observed or current >= expires:
        raise Layer12PolicyError(
            "compatibility observation is future, invalid, or stale"
        )
    if item["live_evaluation_replayable"] is not False:
        raise Layer12PolicyError(
            "live evaluation must remain permanently non-replayable"
        )
    return {
        "compatible": True,
        "identity": identity,
        "compatibility_digest": digest(item),
    }


def check_advisory_aggregate(
    *,
    policy: object,
    compatibility: object,
    cohort: object,
    metric_receipts: Sequence[object],
    comparison_receipt: object,
    expected_identity: object,
    expected_policy_digest: str,
    expected_compatibility_digest: str,
    expected_cohort_digest: str,
    expected_metric_receipt_digests: Sequence[str],
    expected_comparison_receipt_digest: str,
    now: str,
) -> dict[str, Any]:
    policy_obj = _object(policy, "policy")
    _closed(
        policy_obj,
        required={
            "schema_version",
            "policy_id",
            "metric_weights",
            "minimum_receipts",
            "aggregation",
            "non_authority",
        },
        label="policy",
    )
    if (
        policy_obj["schema_version"] != SCHEMAS["policy"]
        or policy_obj["aggregation"] != "weighted_mean"
    ):
        raise Layer12PolicyError("unsupported aggregate policy")
    if policy_obj["non_authority"] is not True:
        raise Layer12PolicyError(
            "aggregate policy must be explicitly non-authoritative"
        )
    policy_id = _text(policy_obj["policy_id"], "policy_id")
    bound_policy_digest = _text(expected_policy_digest, "expected_policy_digest")
    if digest(policy_obj) != bound_policy_digest:
        raise Layer12PolicyError("policy digest does not match external binding")
    minimum = _positive_integer(policy_obj["minimum_receipts"], "minimum_receipts")
    weights_obj = _object(policy_obj["metric_weights"], "metric_weights")
    if not weights_obj:
        raise Layer12PolicyError("metric_weights cannot be empty")
    weights = {
        str(key): _number(value, f"weight.{key}") for key, value in weights_obj.items()
    }
    if any(weight <= 0 for weight in weights.values()):
        raise Layer12PolicyError("weights must be positive")

    compatibility_result = check_execution_compatibility(compatibility, now=now)
    if compatibility_result["compatibility_digest"] != _text(
        expected_compatibility_digest, "expected_compatibility_digest"
    ):
        raise Layer12PolicyError("compatibility does not match external binding")
    identity = compatibility_result["identity"]
    _same_identity(
        _identity(expected_identity, "expected_identity"), identity, "external binding"
    )
    compatibility_obj = _object(compatibility, "compatibility")
    compatibility_observed = _time(compatibility_obj["observed_at"], "observed_at")
    compatibility_expires = _time(compatibility_obj["expires_at"], "expires_at")
    current = _time(now, "now")
    cohort_obj = _object(cohort, "cohort")
    _closed(
        cohort_obj,
        required={
            "schema_version",
            "identity",
            "cohort_id",
            "candidate_ids",
            "compatibility_digest",
        },
        label="cohort",
    )
    if cohort_obj["schema_version"] != SCHEMAS["cohort"]:
        raise Layer12PolicyError("unsupported cohort schema")
    cohort_id = _text(cohort_obj["cohort_id"], "cohort_id")
    if digest(cohort_obj) != _text(expected_cohort_digest, "expected_cohort_digest"):
        raise Layer12PolicyError("cohort does not match external binding")
    _same_identity(
        identity, _identity(cohort_obj["identity"], "cohort.identity"), "cohort"
    )
    if (
        cohort_obj["compatibility_digest"]
        != compatibility_result["compatibility_digest"]
    ):
        raise Layer12PolicyError("cohort compatibility digest mismatch")
    candidate_ids = cohort_obj["candidate_ids"]
    if not isinstance(candidate_ids, list) or not candidate_ids:
        raise Layer12PolicyError("candidate_ids must be a non-empty unique list")
    checked_candidate_ids = [_text(item, "candidate_id") for item in candidate_ids]
    if len(checked_candidate_ids) != len(set(checked_candidate_ids)):
        raise Layer12PolicyError("candidate_ids must be a non-empty unique list")
    if identity["candidate_id"] not in candidate_ids:
        raise Layer12PolicyError("evaluated candidate is outside cohort")

    if len(metric_receipts) < minimum:
        raise Layer12PolicyError("insufficient metric receipts")
    seen: set[str] = set()
    weighted_sum = Decimal(0)
    total_weight = Decimal(0)
    receipt_digests: list[str] = []
    for index, raw in enumerate(metric_receipts):
        receipt = _object(raw, f"metric_receipts[{index}]")
        _closed(
            receipt,
            required={
                "schema_version",
                "identity",
                "metric_id",
                "score_vector",
                "compatibility_digest",
                "measured_at",
                "authoritative",
            },
            label="metric receipt",
        )
        if (
            receipt["schema_version"] != SCHEMAS["metric_receipt"]
            or receipt["authoritative"] is not False
        ):
            raise Layer12PolicyError("metric receipt schema/authority mismatch")
        _same_identity(
            identity, _identity(receipt["identity"], "metric.identity"), "metric"
        )
        if (
            receipt["compatibility_digest"]
            != compatibility_result["compatibility_digest"]
        ):
            raise Layer12PolicyError("metric compatibility digest mismatch")
        metric_id = _text(receipt["metric_id"], "metric_id")
        if metric_id in seen or metric_id not in weights:
            raise Layer12PolicyError("duplicate or unregistered metric")
        seen.add(metric_id)
        vector = _object(receipt["score_vector"], "score_vector")
        _closed(
            vector,
            required={"schema_version", "raw_score", "sample_count"},
            label="score_vector",
        )
        if vector["schema_version"] != SCHEMAS["score"]:
            raise Layer12PolicyError("unsupported score vector")
        score = _number(vector["raw_score"], "raw_score")
        if score < 0 or score > 1:
            raise Layer12PolicyError("raw_score must be within [0,1]")
        _positive_integer(vector["sample_count"], "sample_count")
        measured_at = _time(receipt["measured_at"], "measured_at")
        if (
            measured_at < compatibility_observed
            or measured_at > current
            or measured_at >= compatibility_expires
        ):
            raise Layer12PolicyError(
                "metric receipt is future, stale, or outside compatibility"
            )
        weighted_sum += score * weights[metric_id]
        total_weight += weights[metric_id]
        receipt_digests.append(digest(receipt))
    if seen != set(weights):
        raise Layer12PolicyError("metric set is incomplete")
    bound_receipt_digests = [
        _text(item, "expected_metric_receipt_digest")
        for item in expected_metric_receipt_digests
    ]
    if sorted(receipt_digests) != sorted(bound_receipt_digests):
        raise Layer12PolicyError("metric receipts do not match external binding")

    comparison = _object(comparison_receipt, "comparison_receipt")
    _closed(
        comparison,
        required={
            "schema_version",
            "identity",
            "cohort_id",
            "cohort_digest",
            "metric_receipt_digests",
            "winner_selected",
            "authoritative",
        },
        label="comparison_receipt",
    )
    if digest(comparison) != _text(
        expected_comparison_receipt_digest, "expected_comparison_receipt_digest"
    ):
        raise Layer12PolicyError("comparison does not match external binding")
    _text(comparison["cohort_id"], "comparison.cohort_id")
    if (
        comparison["schema_version"] != SCHEMAS["comparison_receipt"]
        or comparison["authoritative"] is not False
        or comparison["winner_selected"] is not False
    ):
        raise Layer12PolicyError(
            "comparison must remain advisory without winner selection"
        )
    _same_identity(
        identity, _identity(comparison["identity"], "comparison.identity"), "comparison"
    )
    if comparison["cohort_id"] != cohort_id or comparison["cohort_digest"] != digest(
        cohort_obj
    ):
        raise Layer12PolicyError("comparison cohort binding mismatch")
    if comparison["metric_receipt_digests"] != sorted(receipt_digests):
        raise Layer12PolicyError("comparison metric receipt binding mismatch")
    aggregate = weighted_sum / total_weight
    return {
        "schema_version": "layer12-advisory-aggregate-result-v1",
        "status": "advisory_available",
        "identity": identity,
        "policy_id": policy_id,
        "policy_digest": bound_policy_digest,
        "aggregate": format(aggregate, "f"),
        "metric_receipt_digests": sorted(receipt_digests),
        "comparison_receipt_digest": digest(comparison),
        "ak_legality": False,
        "policy_selected": False,
        "recommendation_available": False,
    }


def check_dspx_policy_shadow_evidence(
    *,
    preregistration: object,
    result: object,
    expected_preregistration_digest: str,
    expected_result_digest: str,
    now: str,
) -> dict[str, Any]:
    prereg = _object(preregistration, "preregistration")
    prereg_required = {
        "schema_version",
        "evidence_id",
        "policy_digest",
        "cohort_digest",
        "metric_set_digest",
        "passing_threshold",
        "minimum_observations",
        "registered_at",
        "expires_at",
        "shadow_only",
    }
    _closed(prereg, required=prereg_required, label="preregistration")
    externally_bound_digest = _text(
        expected_preregistration_digest, "expected_preregistration_digest"
    )
    if digest(prereg) != externally_bound_digest:
        raise Layer12PolicyError("preregistration does not match external binding")
    if (
        prereg["schema_version"] != SCHEMAS["shadow"]
        or prereg["shadow_only"] is not True
    ):
        raise Layer12PolicyError("invalid shadow preregistration")
    for field in ("evidence_id", "policy_digest", "cohort_digest", "metric_set_digest"):
        _text(prereg[field], field)
    threshold = _number(prereg["passing_threshold"], "passing_threshold")
    minimum = _positive_integer(prereg["minimum_observations"], "minimum_observations")
    if threshold < 0 or threshold > 1:
        raise Layer12PolicyError("invalid preregistered predicate")
    registered = _time(prereg["registered_at"], "registered_at")
    expires = _time(prereg["expires_at"], "expires_at")
    current = _time(now, "now")
    if registered > current or expires <= registered or current >= expires:
        raise Layer12PolicyError("preregistration is future, invalid, or stale")

    observed = _object(result, "result")
    if digest(observed) != _text(expected_result_digest, "expected_result_digest"):
        raise Layer12PolicyError("shadow result does not match external binding")
    result_required = {
        "schema_version",
        "evidence_id",
        "preregistration_digest",
        "policy_digest",
        "cohort_digest",
        "metric_set_digest",
        "observed_aggregate",
        "observation_count",
        "observed_at",
        "predicate_passed",
        "policy_selected",
        "selection_authorization_ref",
    }
    _closed(observed, required=result_required, label="result")
    if observed["schema_version"] != SCHEMAS["shadow"]:
        raise Layer12PolicyError("invalid shadow result schema")
    if observed["preregistration_digest"] != digest(prereg):
        raise Layer12PolicyError("shadow result does not bind preregistration")
    for field in ("evidence_id", "policy_digest", "cohort_digest", "metric_set_digest"):
        if observed[field] != prereg[field]:
            raise Layer12PolicyError(f"shadow result {field} mismatch")
    aggregate = _number(observed["observed_aggregate"], "observed_aggregate")
    count = _nonnegative_integer(observed["observation_count"], "observation_count")
    if aggregate < 0 or aggregate > 1:
        raise Layer12PolicyError("invalid observed predicate inputs")
    observed_at = _time(observed["observed_at"], "observed_at")
    if observed_at < registered or observed_at > current or observed_at >= expires:
        raise Layer12PolicyError("shadow result observation is out of bounds")
    passed = aggregate >= threshold and count >= minimum
    if observed["predicate_passed"] is not passed:
        raise Layer12PolicyError(
            "predicate_passed does not match preregistered predicate"
        )
    if (
        observed["policy_selected"] is not False
        or observed["selection_authorization_ref"] is not None
    ):
        raise Layer12PolicyError(
            "shadow evidence cannot select policy or carry selection authority"
        )
    return {
        "status": "passing_unselected" if passed else "failing_unselected",
        "evidence_digest": digest(observed),
        "predicate_passed": passed,
        "policy_selected": False,
        "recommendation_available": False,
        "requires_separate_owner_selection_authorization": True,
    }


def check_signed_dspx_shadow_receipt(
    *,
    envelope: object,
    expected_owner_repository: str,
    expected_key_id: str,
    expected_public_key_b64: str,
    expected_payload_digest: str,
    expected_contract_commit: str,
    expected_transition_eval_refs: object,
    expected_policy_digest: str,
    expected_cohort_digest: str,
    expected_metric_set_digest: str,
    now: str,
) -> dict[str, Any]:
    """Verify a content-addressed DSPx owner receipt and its shadow predicate.

    The externally supplied owner/key/digest bindings are trusted inputs. The signed
    payload remains advisory: successful verification cannot select policy, establish
    AK legality, apply a generated program, or authorize later wave gates.
    """
    item = _object(envelope, "envelope")
    _closed(
        item,
        required={
            "schema_version",
            "owner_repository",
            "key_id",
            "public_key_b64",
            "payload_digest",
            "signature_b64",
            "payload",
        },
        label="envelope",
    )
    if item["schema_version"] != "iw14a-dspx-shadow-receipt-envelope-v1":
        raise Layer12PolicyError("unsupported signed shadow envelope")
    owner = _text(expected_owner_repository, "expected_owner_repository")
    key_id = _text(expected_key_id, "expected_key_id")
    public_key_b64 = _text(expected_public_key_b64, "expected_public_key_b64")
    payload_digest = _text(expected_payload_digest, "expected_payload_digest")
    contract_commit = _text(expected_contract_commit, "expected_contract_commit")
    if re.fullmatch(r"[0-9a-f]{40}", contract_commit) is None:
        raise Layer12PolicyError(
            "expected contract commit must be a full git object id"
        )
    expected_refs_obj = _object(
        expected_transition_eval_refs, "expected_transition_eval_refs"
    )
    if not expected_refs_obj:
        raise Layer12PolicyError("expected transition evaluation refs cannot be empty")
    expected_refs = {
        _text(token, "expected transition token"): _text(ref, "expected eval ref")
        for token, ref in expected_refs_obj.items()
    }
    for ref in expected_refs.values():
        if re.fullmatch(r"ak-eval:sha256:[0-9a-f]{64}", ref) is None:
            raise Layer12PolicyError(
                "expected eval refs must be full content addresses"
            )
    policy_digest = _text(expected_policy_digest, "expected_policy_digest")
    cohort_digest = _text(expected_cohort_digest, "expected_cohort_digest")
    metric_set_digest = _text(expected_metric_set_digest, "expected_metric_set_digest")
    if item["owner_repository"] != owner or owner != "softwareco/owned/dspx":
        raise Layer12PolicyError("owner repository does not match external binding")
    if item["key_id"] != key_id or item["public_key_b64"] != public_key_b64:
        raise Layer12PolicyError("signer does not match external trust root")

    payload = _object(item["payload"], "payload")
    actual_payload_digest = digest(payload)
    if (
        item["payload_digest"] != actual_payload_digest
        or actual_payload_digest != payload_digest
    ):
        raise Layer12PolicyError("payload digest does not match external binding")
    try:
        public_key = base64.b64decode(public_key_b64, validate=True)
        signature = base64.b64decode(
            _text(item["signature_b64"], "signature_b64"), validate=True
        )
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, canonical_json(payload).encode("utf-8")
        )
    except (ValueError, binascii.Error, InvalidSignature) as exc:
        raise Layer12PolicyError("invalid DSPx owner signature") from exc

    _closed(
        payload,
        required={
            "schema_version",
            "wave_id",
            "owner_repository",
            "contract_commit",
            "preregistration",
            "result",
            "evaluations",
            "policy_selected",
            "ak_legality",
            "generated_program_applied",
            "promotion_authorized",
            "publication_authorized",
            "dogfood_authorized",
            "rollout_authorized",
        },
        label="payload",
    )
    if (
        payload["schema_version"] != "iw14a-dspx-shadow-evidence-payload-v1"
        or payload["wave_id"] != "IW14-A"
        or payload["owner_repository"] != owner
        or payload["contract_commit"] != contract_commit
    ):
        raise Layer12PolicyError("signed shadow payload authority binding mismatch")
    for field in (
        "policy_selected",
        "ak_legality",
        "generated_program_applied",
        "promotion_authorized",
        "publication_authorized",
        "dogfood_authorized",
        "rollout_authorized",
    ):
        if payload[field] is not False:
            raise Layer12PolicyError(f"shadow payload cannot assert {field}")

    evaluations = payload["evaluations"]
    if not isinstance(evaluations, list) or not evaluations:
        raise Layer12PolicyError("evaluations must be a non-empty list")
    seen_tokens: set[str] = set()
    weighted_score = Decimal(0)
    observation_count = 0
    for index, raw in enumerate(evaluations):
        evaluation = _object(raw, f"evaluations[{index}]")
        _closed(
            evaluation,
            required={
                "protocol_version",
                "transition_token",
                "family_id",
                "spec_digest",
                "candidate_id",
                "ak_eval_receipt_id",
                "observed_score",
                "observation_count",
                "authoritative",
                "live_evaluation_replayable",
            },
            label="evaluation",
        )
        identity = _identity({field: evaluation[field] for field in IDENTITY_FIELDS})
        token = identity["transition_token"]
        if token in seen_tokens:
            raise Layer12PolicyError("representative transition tokens must be unique")
        if (
            token not in expected_refs
            or identity["ak_eval_receipt_id"] != expected_refs[token]
        ):
            raise Layer12PolicyError("evaluation token/ref is outside external binding")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", identity["spec_digest"]) is None:
            raise Layer12PolicyError("evaluation spec digest must be content addressed")
        seen_tokens.add(token)
        if (
            evaluation["authoritative"] is not False
            or evaluation["live_evaluation_replayable"] is not False
        ):
            raise Layer12PolicyError(
                "evaluations must remain advisory and non-replayable"
            )
        score = _number(evaluation["observed_score"], "observed_score")
        count = _positive_integer(evaluation["observation_count"], "observation_count")
        if score < 0 or score > 1:
            raise Layer12PolicyError("observed_score must be within [0,1]")
        weighted_score += score * count
        observation_count += count

    if seen_tokens != set(expected_refs):
        raise Layer12PolicyError(
            "signed evaluations do not cover exact expected token set"
        )
    preregistration = _object(payload["preregistration"], "preregistration")
    if (
        preregistration.get("policy_digest") != policy_digest
        or preregistration.get("cohort_digest") != cohort_digest
        or preregistration.get("metric_set_digest") != metric_set_digest
        or cohort_digest != f"sha256:{digest(evaluations)}"
    ):
        raise Layer12PolicyError("shadow preregistration context mismatch")

    observed = _object(payload["result"], "result")
    recomputed_aggregate = weighted_score / observation_count
    if (
        _number(observed.get("observed_aggregate"), "observed_aggregate")
        != recomputed_aggregate
    ):
        raise Layer12PolicyError("result aggregate does not match signed evaluations")
    if (
        _nonnegative_integer(observed.get("observation_count"), "observation_count")
        != observation_count
    ):
        raise Layer12PolicyError("result count does not match signed evaluations")
    checked = check_dspx_policy_shadow_evidence(
        preregistration=preregistration,
        result=payload["result"],
        expected_preregistration_digest=digest(payload["preregistration"]),
        expected_result_digest=digest(payload["result"]),
        now=now,
    )
    return {
        **checked,
        "owner_repository": owner,
        "key_id": key_id,
        "payload_digest": actual_payload_digest,
        "signature_verified": True,
        "representative_transition_tokens": sorted(seen_tokens),
        "ak_legality": False,
        "generated_program_applied": False,
    }
