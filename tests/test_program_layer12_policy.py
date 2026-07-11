from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import jsonschema
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dspx.services.program_layer12_policy import (
    Layer12PolicyError,
    check_advisory_aggregate,
    check_dspx_policy_shadow_evidence,
    check_signed_dspx_shadow_receipt,
    digest,
)

NOW = "2026-07-11T12:00:00Z"

SCHEMA_PATH = Path("docs/project/layer12/layer12-dspx-policy-contracts.v1.schema.json")
FIXTURE_PATH = Path(
    "docs/project/layer12/fixtures/layer12-dspx-policy-fixtures.v1.json"
)
SIGNED_SHADOW_FIXTURE_PATH = Path(
    "docs/project/layer12/fixtures/iw14a-dspx-shadow-evidence.v1.json"
)
SIGNED_OWNER = "softwareco/owned/dspx"
SIGNED_KEY_ID = "dspx-iw14a-shadow-fixture-key-v1"
SIGNED_PUBLIC_KEY_B64 = "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg="
SIGNED_PAYLOAD_DIGEST = (
    "3c5e2c315c33c2d8a1c640b962f28f2bad1c246538139e38f84a198fbefb5cac"
)
SIGNED_CONTRACT_COMMIT = "57a330d8e088236f1958040da81832d84cbf57d1"
SIGNED_POLICY_DIGEST = (
    "sha256:c7f9e46cbd4575ee75195b76bcf6dd88fc19bba3c92f85dd276ef20c810b499f"
)
SIGNED_COHORT_DIGEST = (
    "sha256:8d7b650bea82a8865b2fc9e636fb673dfeca96a6eee4bfc58a728ed8de02e164"
)
SIGNED_METRIC_SET_DIGEST = (
    "sha256:7d17d83230860d43ce0cccf05616cf63a66c9ecdfdd6e4a8e7873f939458189c"
)
SIGNED_EVAL_REFS = {
    "ak.task.claim": "ak-eval:sha256:bd5301e6a6ba545fe03418df4ac985b3fbfff1c7fff12c7773c2bad464308ffe",
    "ak.task.complete": "ak-eval:sha256:364569740ff3294dd613a0bba7dc7af4dfebba11174af062d7c9974ffdce6613",
    "ak.direction.transition": "ak-eval:sha256:68aa579e9d4ab911e5982a2580c0bef3b6c61f1cb13b18a6cb1087c8097f918b",
}


def _identity() -> dict[str, str]:
    return {
        "protocol_version": "layer12-v1",
        "transition_token": "ak.task.claim",
        "family_id": "family:claim:v1",
        "spec_digest": "sha256:spec",
        "candidate_id": "candidate:001",
        "ak_eval_receipt_id": "ak-eval:001",
    }


def _aggregate_inputs() -> dict[str, object]:
    identity = _identity()
    compatibility = {
        "schema_version": "layer12-execution-compatibility-v1",
        "identity": identity,
        "runtime_digest": "sha256:runtime",
        "dataset_digest": "sha256:dataset",
        "metric_set_digest": "sha256:metric-set",
        "observed_at": "2026-07-11T11:00:00Z",
        "expires_at": "2026-07-11T13:00:00Z",
        "live_evaluation_replayable": False,
    }
    cohort = {
        "schema_version": "layer12-comparison-cohort-v1",
        "identity": copy.deepcopy(identity),
        "cohort_id": "cohort:001",
        "candidate_ids": ["candidate:001", "candidate:002"],
        "compatibility_digest": digest(compatibility),
    }
    receipts = [
        {
            "schema_version": "layer12-dspx-metric-receipt-v1",
            "identity": copy.deepcopy(identity),
            "metric_id": metric,
            "score_vector": {
                "schema_version": "layer12-advisory-score-vector-v1",
                "raw_score": score,
                "sample_count": 12,
            },
            "compatibility_digest": digest(compatibility),
            "measured_at": "2026-07-11T11:15:00Z",
            "authoritative": False,
        }
        for metric, score in (("quality", 0.80), ("safety", 1.0))
    ]
    comparison = {
        "schema_version": "layer12-comparison-receipt-v1",
        "identity": copy.deepcopy(identity),
        "cohort_id": "cohort:001",
        "cohort_digest": digest(cohort),
        "metric_receipt_digests": sorted(digest(item) for item in receipts),
        "winner_selected": False,
        "authoritative": False,
    }
    return {
        "policy": {
            "schema_version": "layer12-advisory-aggregate-policy-v1",
            "policy_id": "policy:fixture",
            "metric_weights": {"quality": 0.75, "safety": 0.25},
            "minimum_receipts": 2,
            "aggregation": "weighted_mean",
            "non_authority": True,
        },
        "compatibility": compatibility,
        "cohort": cohort,
        "metric_receipts": receipts,
        "comparison_receipt": comparison,
        "expected_identity": copy.deepcopy(identity),
        "expected_policy_digest": digest(
            {
                "schema_version": "layer12-advisory-aggregate-policy-v1",
                "policy_id": "policy:fixture",
                "metric_weights": {"quality": 0.75, "safety": 0.25},
                "minimum_receipts": 2,
                "aggregation": "weighted_mean",
                "non_authority": True,
            }
        ),
        "expected_compatibility_digest": digest(compatibility),
        "expected_cohort_digest": digest(cohort),
        "expected_metric_receipt_digests": sorted(digest(item) for item in receipts),
        "expected_comparison_receipt_digest": digest(comparison),
        "now": NOW,
    }


def test_aggregate_is_deterministic_advisory_and_never_recommendation() -> None:
    result = check_advisory_aggregate(**_aggregate_inputs())
    assert result["aggregate"] == "0.85"
    assert result["ak_legality"] is False
    assert result["policy_selected"] is False
    assert result["recommendation_available"] is False


def test_fixed_cross_language_fixture_matches_schema_and_checker() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    positive = fixture["positive"]
    for artifact in (
        positive["policy"],
        positive["compatibility"],
        positive["cohort"],
        *positive["metric_receipts"],
        positive["comparison_receipt"],
        fixture["shadow"]["preregistration"],
        fixture["shadow"]["result"],
    ):
        jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        ).validate(artifact)
    aggregate = check_advisory_aggregate(
        policy=positive["policy"],
        compatibility=positive["compatibility"],
        cohort=positive["cohort"],
        metric_receipts=positive["metric_receipts"],
        comparison_receipt=positive["comparison_receipt"],
        expected_identity=positive["compatibility"]["identity"],
        expected_policy_digest=digest(positive["policy"]),
        expected_compatibility_digest=digest(positive["compatibility"]),
        expected_cohort_digest=digest(positive["cohort"]),
        expected_metric_receipt_digests=sorted(
            digest(item) for item in positive["metric_receipts"]
        ),
        expected_comparison_receipt_digest=digest(positive["comparison_receipt"]),
        now=fixture["now"],
    )
    assert aggregate["aggregate"] == positive["expected_aggregate"]
    shadow = check_dspx_policy_shadow_evidence(
        preregistration=fixture["shadow"]["preregistration"],
        result=fixture["shadow"]["result"],
        expected_preregistration_digest=digest(fixture["shadow"]["preregistration"]),
        expected_result_digest=digest(fixture["shadow"]["result"]),
        now=fixture["now"],
    )
    assert shadow["status"] == fixture["shadow"]["expected_status"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda p: p["compatibility"].update(expires_at="2026-07-11T12:00:00Z"),
            "stale",
        ),
        (
            lambda p: p["compatibility"].update(observed_at="2026-07-11T12:01:00Z"),
            "future",
        ),
        (
            lambda p: p["compatibility"].update(live_evaluation_replayable=True),
            "non-replayable",
        ),
        (
            lambda p: p["metric_receipts"][0]["identity"].update(
                transition_token="ak.task.complete"
            ),
            "identity",
        ),
        (
            lambda p: p["metric_receipts"][0]["identity"].update(
                protocol_version="layer12-v2"
            ),
            "protocol",
        ),
        (
            lambda p: p["metric_receipts"][0]["score_vector"].update(
                raw_score=float("nan")
            ),
            "finite",
        ),
        (lambda p: p["metric_receipts"].pop(), "insufficient"),
        (
            lambda p: p["comparison_receipt"].update(winner_selected=True),
            "external binding",
        ),
        (
            lambda p: p["comparison_receipt"].update(metric_receipt_digests=[]),
            "binding",
        ),
        (
            lambda p: p["cohort"].update(candidate_ids=["candidate:002"]),
            "external binding",
        ),
    ],
)
def test_aggregate_fails_closed(mutation: object, message: str) -> None:
    payload = _aggregate_inputs()
    mutation(payload)  # type: ignore[operator]
    with pytest.raises(Layer12PolicyError, match=message):
        check_advisory_aggregate(**payload)


def _shadow() -> tuple[dict[str, object], dict[str, object]]:
    prereg = {
        "schema_version": "layer12-dspx-policy-shadow-evidence-v1",
        "evidence_id": "shadow:001",
        "policy_digest": "sha256:policy",
        "cohort_digest": "sha256:cohort",
        "metric_set_digest": "sha256:metric-set",
        "passing_threshold": 0.80,
        "minimum_observations": 20,
        "registered_at": "2026-07-11T10:00:00Z",
        "expires_at": "2026-07-12T10:00:00Z",
        "shadow_only": True,
    }
    result = {
        "schema_version": "layer12-dspx-policy-shadow-evidence-v1",
        "evidence_id": "shadow:001",
        "preregistration_digest": digest(prereg),
        "policy_digest": "sha256:policy",
        "cohort_digest": "sha256:cohort",
        "metric_set_digest": "sha256:metric-set",
        "observed_aggregate": 0.90,
        "observation_count": 25,
        "observed_at": "2026-07-11T11:30:00Z",
        "predicate_passed": True,
        "policy_selected": False,
        "selection_authorization_ref": None,
    }
    return prereg, result


def test_shadow_evidence_can_pass_without_selecting_policy() -> None:
    prereg, result = _shadow()
    checked = check_dspx_policy_shadow_evidence(
        preregistration=prereg,
        result=result,
        expected_preregistration_digest=digest(prereg),
        expected_result_digest=digest(result),
        now=NOW,
    )
    assert checked == {
        "status": "passing_unselected",
        "evidence_digest": digest(result),
        "predicate_passed": True,
        "policy_selected": False,
        "recommendation_available": False,
        "requires_separate_owner_selection_authorization": True,
    }


def _check_signed_shadow_fixture(
    fixture: dict[str, object], *, expected_payload_digest: str = SIGNED_PAYLOAD_DIGEST
) -> dict[str, object]:
    return check_signed_dspx_shadow_receipt(
        envelope=fixture["envelope"],
        expected_owner_repository=SIGNED_OWNER,
        expected_key_id=SIGNED_KEY_ID,
        expected_public_key_b64=SIGNED_PUBLIC_KEY_B64,
        expected_payload_digest=expected_payload_digest,
        expected_contract_commit=SIGNED_CONTRACT_COMMIT,
        expected_transition_eval_refs=SIGNED_EVAL_REFS,
        expected_policy_digest=SIGNED_POLICY_DIGEST,
        expected_cohort_digest=SIGNED_COHORT_DIGEST,
        expected_metric_set_digest=SIGNED_METRIC_SET_DIGEST,
        now=fixture["verification_now"],
    )


def _resign_shadow_fixture(fixture: dict[str, object]) -> str:
    envelope = fixture["envelope"]
    assert isinstance(envelope, dict)
    payload = envelope["payload"]
    payload_digest = digest(payload)
    envelope["payload_digest"] = payload_digest
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    envelope["signature_b64"] = base64.b64encode(
        key.sign(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
    ).decode("ascii")
    return payload_digest


def test_signed_iw14a_shadow_fixture_is_content_addressed_and_unselected() -> None:
    fixture = json.loads(SIGNED_SHADOW_FIXTURE_PATH.read_text(encoding="utf-8"))
    checked = _check_signed_shadow_fixture(fixture)
    assert checked["status"] == fixture["expected_status"] == "passing_unselected"
    assert checked["signature_verified"] is True
    assert checked["representative_transition_tokens"] == [
        "ak.direction.transition",
        "ak.task.claim",
        "ak.task.complete",
    ]
    assert checked["policy_selected"] is False
    assert checked["recommendation_available"] is False
    assert checked["ak_legality"] is False
    assert checked["generated_program_applied"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda f: f["envelope"]["payload"]["evaluations"][0].update(
                observed_score=1.0
            ),
            "payload digest",
        ),
        (
            lambda f: f["envelope"].update(signature_b64="AA=="),
            "signature",
        ),
    ],
)
def test_signed_iw14a_shadow_fixture_fails_closed(
    mutation: object, message: str
) -> None:
    fixture = json.loads(SIGNED_SHADOW_FIXTURE_PATH.read_text(encoding="utf-8"))
    mutation(fixture)  # type: ignore[operator]
    with pytest.raises(Layer12PolicyError, match=message):
        _check_signed_shadow_fixture(fixture)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda p: p["evaluations"][0].update(
                transition_token="ak.unexpected.transition"
            ),
            "token/ref",
        ),
        (
            lambda p: p["evaluations"][0].update(
                ak_eval_receipt_id="ak-eval:sha256:" + "0" * 64
            ),
            "token/ref",
        ),
        (lambda p: p.update(policy_selected=True), "cannot assert policy_selected"),
        (
            lambda p: p["result"].update(observed_aggregate=0.8),
            "aggregate",
        ),
        (
            lambda p: p["preregistration"].update(
                metric_set_digest="sha256:" + "0" * 64
            ),
            "context mismatch",
        ),
    ],
)
def test_resigned_semantic_laundering_fails_closed(
    mutation: object, message: str
) -> None:
    fixture = json.loads(SIGNED_SHADOW_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = fixture["envelope"]["payload"]
    mutation(payload)  # type: ignore[operator]
    resigned_digest = _resign_shadow_fixture(fixture)
    with pytest.raises(Layer12PolicyError, match=message):
        _check_signed_shadow_fixture(fixture, expected_payload_digest=resigned_digest)


@pytest.mark.parametrize(
    "field", ["policy_digest", "cohort_digest", "metric_set_digest"]
)
def test_shadow_result_rejects_changed_preregistered_binding(field: str) -> None:
    prereg, result = _shadow()
    result[field] = "sha256:changed"
    with pytest.raises(Layer12PolicyError, match=field):
        check_dspx_policy_shadow_evidence(
            preregistration=prereg,
            result=result,
            expected_preregistration_digest=digest(prereg),
            expected_result_digest=digest(result),
            now=NOW,
        )


def test_shadow_result_rejects_recomputed_preregistration_after_the_fact() -> None:
    prereg, result = _shadow()
    externally_bound_digest = digest(prereg)
    externally_bound_result_digest = digest(result)
    prereg["passing_threshold"] = 0.95
    result["preregistration_digest"] = digest(prereg)
    with pytest.raises(Layer12PolicyError, match="external binding"):
        check_dspx_policy_shadow_evidence(
            preregistration=prereg,
            result=result,
            expected_preregistration_digest=externally_bound_digest,
            expected_result_digest=externally_bound_result_digest,
            now=NOW,
        )


def test_shadow_result_rejects_false_predicate_claim_and_selection_laundering() -> None:
    prereg, result = _shadow()
    result["predicate_passed"] = False
    with pytest.raises(Layer12PolicyError, match="predicate_passed"):
        check_dspx_policy_shadow_evidence(
            preregistration=prereg,
            result=result,
            expected_preregistration_digest=digest(prereg),
            expected_result_digest=digest(result),
            now=NOW,
        )
    prereg, result = _shadow()
    result.update(policy_selected=True, selection_authorization_ref="owner:approval")
    with pytest.raises(Layer12PolicyError, match="cannot select"):
        check_dspx_policy_shadow_evidence(
            preregistration=prereg,
            result=result,
            expected_preregistration_digest=digest(prereg),
            expected_result_digest=digest(result),
            now=NOW,
        )


def test_contracts_are_closed_against_unknown_fields() -> None:
    payload = _aggregate_inputs()
    payload["policy"]["selected"] = True  # type: ignore[index]
    with pytest.raises(Layer12PolicyError, match="fields mismatch"):
        check_advisory_aggregate(**payload)


def test_external_bindings_reject_policy_and_identity_substitution() -> None:
    payload = _aggregate_inputs()
    payload["policy"]["metric_weights"] = {"quality": 1, "safety": 99}  # type: ignore[index]
    with pytest.raises(Layer12PolicyError, match="policy digest"):
        check_advisory_aggregate(**payload)
    payload = _aggregate_inputs()
    payload["expected_identity"]["transition_token"] = "ak.task.complete"  # type: ignore[index]
    with pytest.raises(Layer12PolicyError, match="external binding"):
        check_advisory_aggregate(**payload)


def test_metric_receipt_time_is_bounded_by_compatibility_and_now() -> None:
    for measured_at in (
        "2026-07-11T10:59:59Z",
        "2026-07-11T12:00:01Z",
        "2099-01-01T00:00:00Z",
    ):
        payload = _aggregate_inputs()
        payload["metric_receipts"][0]["measured_at"] = measured_at  # type: ignore[index]
        payload["comparison_receipt"]["metric_receipt_digests"] = sorted(  # type: ignore[index]
            digest(item)
            for item in payload["metric_receipts"]  # type: ignore[union-attr]
        )
        with pytest.raises(Layer12PolicyError, match="future, stale, or outside"):
            check_advisory_aggregate(**payload)


def test_fixed_negative_fixture_inventory_is_executed() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "layer12-dspx-policy-fixtures-v1"
    cases = {item["id"]: item for item in fixture["negative_mutations"]}
    assert set(cases) == {
        "stale_compatibility",
        "mixed_token",
        "winner_laundering",
        "selection_laundering",
    }
    for case_id in ("stale_compatibility", "mixed_token", "winner_laundering"):
        payload = copy.deepcopy(fixture["positive"])
        if case_id == "stale_compatibility":
            payload["compatibility"]["expires_at"] = cases[case_id]["value"]
        elif case_id == "mixed_token":
            payload["metric_receipts"][0]["identity"]["transition_token"] = cases[
                case_id
            ]["value"]
        else:
            payload["comparison_receipt"]["winner_selected"] = cases[case_id]["value"]
        with pytest.raises(Layer12PolicyError, match=cases[case_id]["expected_error"]):
            check_advisory_aggregate(
                policy=payload["policy"],
                compatibility=payload["compatibility"],
                cohort=payload["cohort"],
                metric_receipts=payload["metric_receipts"],
                comparison_receipt=payload["comparison_receipt"],
                expected_identity=fixture["positive"]["compatibility"]["identity"],
                expected_policy_digest=digest(fixture["positive"]["policy"]),
                expected_compatibility_digest=digest(
                    fixture["positive"]["compatibility"]
                ),
                expected_cohort_digest=digest(fixture["positive"]["cohort"]),
                expected_metric_receipt_digests=sorted(
                    digest(item) for item in fixture["positive"]["metric_receipts"]
                ),
                expected_comparison_receipt_digest=digest(
                    fixture["positive"]["comparison_receipt"]
                ),
                now=fixture["now"],
            )
    prereg = fixture["shadow"]["preregistration"]
    result = copy.deepcopy(fixture["shadow"]["result"])
    result["policy_selected"] = True
    with pytest.raises(
        Layer12PolicyError, match=cases["selection_laundering"]["expected_error"]
    ):
        check_dspx_policy_shadow_evidence(
            preregistration=prereg,
            result=result,
            expected_preregistration_digest=digest(prereg),
            expected_result_digest=digest(result),
            now=fixture["now"],
        )


@pytest.mark.parametrize(
    "malformed", ["20260711T110000Z", "2026-W28-6T11:00:00Z", "2026-07-11 11:00:00Z"]
)
def test_strict_rfc3339_rejects_malformed_authenticated_times(malformed: str) -> None:
    payload = _aggregate_inputs()
    payload["compatibility"]["observed_at"] = malformed  # type: ignore[index]
    payload["expected_compatibility_digest"] = digest(payload["compatibility"])
    with pytest.raises(Layer12PolicyError, match="RFC3339"):
        check_advisory_aggregate(**payload)

    payload = _aggregate_inputs()
    payload["metric_receipts"][0]["measured_at"] = malformed  # type: ignore[index]
    payload["expected_metric_receipt_digests"] = sorted(  # type: ignore[assignment]
        digest(item)
        for item in payload["metric_receipts"]  # type: ignore[union-attr]
    )
    with pytest.raises(Layer12PolicyError, match="RFC3339"):
        check_advisory_aggregate(**payload)

    payload = _aggregate_inputs()
    payload["now"] = malformed
    with pytest.raises(Layer12PolicyError, match="RFC3339"):
        check_advisory_aggregate(**payload)

    prereg, result = _shadow()
    prereg["registered_at"] = malformed
    result["preregistration_digest"] = digest(prereg)
    with pytest.raises(Layer12PolicyError, match="RFC3339"):
        check_dspx_policy_shadow_evidence(
            preregistration=prereg,
            result=result,
            expected_preregistration_digest=digest(prereg),
            expected_result_digest=digest(result),
            now=NOW,
        )

    prereg, result = _shadow()
    result["observed_at"] = malformed
    with pytest.raises(Layer12PolicyError, match="RFC3339"):
        check_dspx_policy_shadow_evidence(
            preregistration=prereg,
            result=result,
            expected_preregistration_digest=digest(prereg),
            expected_result_digest=digest(result),
            now=NOW,
        )
