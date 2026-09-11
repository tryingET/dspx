"""Adversarial private-custody/reference tests, with native socket-backed episodes."""

from __future__ import annotations

from dataclasses import asdict
import json
import os

import pytest

from dspx.services.reading_pilot import prepare_pilot, run_pilot
from dspx.services.reading_pilot_verification import (
    PilotContract,
    canonical,
    check_output,
    public_spec,
    sha,
)
from test_reading_pilot import (
    SOURCE,
    TEMPLATE,
    contract_data,
    execute,
    output_for,
    prepare,
    server,
    verified,
)

# Imported fixtures intentionally share only invented source and an isolated server.
__all__ = ["contract_data", "server"]


@pytest.mark.parametrize(
    "target",
    ["source/passage.txt", "candidate/manifest.json", "public.json", "purposes.json"],
)
def test_predispatch_drift_rejected(contract_data, server, target):
    prepared = prepare(contract_data)
    parent, data = contract_data
    path = parent / data["campaign_id"] / target
    path.write_bytes(path.read_bytes() + b" ")
    result = execute(contract_data, prepared)
    assert result.state == "rejected" and server.requests == []


def test_root_reuse_foreign_parent_and_missing_candidate_review(
    contract_data, server, tmp_path
):
    prepared = prepare(contract_data)
    parent, data = contract_data
    result = prepare_pilot(
        parent=parent,
        contract_payload=data,
        source=SOURCE,
        template_bytes=TEMPLATE.read_bytes(),
        expected_contract_sha256=sha(canonical(data)),
    )
    assert result.state == "rejected"
    other = tmp_path / "other"
    other.mkdir(mode=0o700)
    result = prepare_pilot(
        parent=other,
        contract_payload=data,
        source=SOURCE,
        template_bytes=TEMPLATE.read_bytes(),
        expected_contract_sha256=sha(canonical(data)),
    )
    assert result.state == "rejected" and list(other.iterdir()) == []
    result = run_pilot(
        parent=parent,
        campaign_id=data["campaign_id"],
        expected_contract_sha256=sha(canonical(data)),
        expected_candidate_sha256=prepared.candidate_sha256,
        candidate_review_ref="",
        operator_admission_ref=data["operator_admission_ref"],
    )
    assert result.state == "rejected" and server.requests == []
    assert not (parent / data["campaign_id"] / "started.json").exists()


def test_symlink_and_candidate_identity_zero_calls(contract_data, server, tmp_path):
    prepared = prepare(contract_data)
    parent, data = contract_data
    result = run_pilot(
        parent=parent,
        campaign_id=data["campaign_id"],
        expected_contract_sha256=sha(canonical(data)),
        expected_candidate_sha256="0" * 64,
        candidate_review_ref="fixture",
        operator_admission_ref=data["operator_admission_ref"],
    )
    assert result.state == "rejected"
    root = parent / data["campaign_id"]
    source = root / "source" / "passage.txt"
    moved = tmp_path / "moved-source"
    source.rename(moved)
    source.symlink_to(moved)
    assert execute(contract_data, prepared).state == "rejected"
    assert server.requests == []


@pytest.mark.parametrize(
    "target",
    [
        "A/runtime_inputs.json",
        "A/reading_analysis_json",
        "A/runtime_episode.json",
        "candidate/manifest.json",
    ],
)
def test_native_graft_tamper_rejected(contract_data, server, target):
    prepared = prepare(contract_data)
    result = execute(contract_data, prepared)
    assert result.state == "completed"
    parent, data = contract_data
    root = parent / data["campaign_id"]
    path = root / target
    # A native B artifact cannot stand in for A even with a valid native B receipt.
    if target.startswith("A/"):
        path.write_bytes((root / target.replace("A/", "B/", 1)).read_bytes())
        if target.endswith("reading_analysis_json"):
            assert SOURCE not in path.read_bytes()
    else:
        manifest = json.loads(path.read_bytes())
        manifest["candidate_assembly"]["candidate_id"] = "foreign-candidate"
        path.write_bytes(canonical(manifest))
    assert verified(contract_data, prepared, result).state == "rejected"
    assert len(server.requests) == 2  # Verification never executes replay/provider.


def test_wrong_independently_held_hash_cannot_self_certify(contract_data, server):
    prepared = prepare(contract_data)
    result = execute(contract_data, prepared)
    assert result.state == "completed"
    from dspx.services.reading_pilot_verification import verify_pilot

    parent, data = contract_data
    actual = verify_pilot(
        parent=parent,
        campaign_id=data["campaign_id"],
        expected_contract_sha256=sha(canonical(data)),
        expected_candidate_sha256=prepared.candidate_sha256,
        expected_result_sha256="0" * 64,
    )
    assert actual.state == "rejected" and len(server.requests) == 2
    assert not any(SOURCE.decode() in str(v) for v in asdict(actual).values())


def test_schema_references_and_semantics_separate(contract_data):
    _, data = contract_data
    contract = PilotContract.model_validate(data)
    output = output_for()
    assert check_output(canonical(output), contract, SOURCE) == ("passed", "passed")
    # Structurally sound but deliberately false reasoning remains for human judgment.
    output["L1_paraphrase"]["text"] = "This proves universal reliability."
    assert check_output(canonical(output), contract, SOURCE) == ("passed", "passed")
    output["L1_paraphrase"]["evidence"][0]["quote"] = "fabricated quotation"
    assert check_output(canonical(output), contract, SOURCE) == ("passed", "failed")
    output["L5_author_perspective"].pop("simulation")
    assert check_output(canonical(output), contract, SOURCE) == (
        "failed",
        "not_checked",
    )
    assert public_spec()["rubric"]["review"].startswith("Independent local human")


def test_synthetic_receipt_and_model_authority_fields_rejected(contract_data):
    contract = PilotContract.model_validate(contract_data[1])
    for payload in (
        {"schema_version": "dspx-program-reading-receipt-v1"},
        {**output_for(), "whole_book_supported": 0},
        {**output_for(), "review_eligible": True},
        {**output_for(), "source_sha256": sha(SOURCE)},
        {**output_for(), "semantic_pass": True},
    ):
        assert check_output(canonical(payload), contract, SOURCE)[0] == "failed"


def test_public_root_or_symlink_parent_rejected(contract_data, server, tmp_path):
    parent, data = contract_data
    alias = tmp_path / "alias"
    alias.symlink_to(parent, target_is_directory=True)
    result = prepare_pilot(
        parent=alias,
        contract_payload=data,
        source=SOURCE,
        template_bytes=TEMPLATE.read_bytes(),
        expected_contract_sha256=sha(canonical(data)),
    )
    assert result.state == "rejected"
    os.chmod(parent, 0o755)
    result = prepare_pilot(
        parent=parent,
        contract_payload=data,
        source=SOURCE,
        template_bytes=TEMPLATE.read_bytes(),
        expected_contract_sha256=sha(canonical(data)),
    )
    assert result.state == "rejected" and server.requests == []


def test_interrupted_started_campaign_never_resets(contract_data, server):
    prepared = prepare(contract_data)
    parent, data = contract_data
    root = parent / data["campaign_id"]
    from dspx.services.reading_pilot_verification import write_private

    # Crash after the durable start marker but before any worker/dispatch.
    write_private(root / "started.json", canonical({"interrupted": True}))
    result = execute(contract_data, prepared)
    assert result.state == "latched" and result.dispatches is None
    assert server.requests == []
    assert execute(contract_data, prepared) == result


def test_untrustworthy_provider_observation_keeps_count_unknown(
    contract_data, server, monkeypatch
):
    import dspx.services.reading_pilot as pilot

    prepared = prepare(contract_data)
    native_child = pilot._child

    def corrupt_after_child(root, contract, case):
        outcome = native_child(root, contract, case)
        if case == "A":
            assert outcome.status == "returned"
            path = root / "A.provider.json"
            receipt = json.loads(path.read_bytes())
            receipt["provider"]["effect_evidence"]["attempt_total"] = 9
            path.write_bytes(
                canonical(receipt)
            )  # Deliberate fixture corruption, not runtime repair.
        return outcome

    monkeypatch.setattr(pilot, "_child", corrupt_after_child)
    result = execute(contract_data, prepared)
    assert result.state == "effect_indeterminate" and result.dispatches is None
    assert result.provider_effect is None and len(server.requests) == 1
    assert not (
        contract_data[0] / contract_data[1]["campaign_id"] / "B.intent.json"
    ).exists()


def test_preexisting_observation_cannot_claim_child_custody(contract_data, server):
    from dspx.services.reading_pilot_verification import write_private

    prepared = prepare(contract_data)
    root = contract_data[0] / contract_data[1]["campaign_id"]
    write_private(root / "A.provider.json", canonical({"effect": "completed_success"}))
    result = execute(contract_data, prepared)
    assert result.state == "rejected" and server.requests == []


@pytest.mark.parametrize("forgery", ["zero_dispatch", "false_success"])
@pytest.mark.parametrize("corrupt_episode", [False, True])
@pytest.mark.parametrize("forge_behavior", [False, True])
def test_coherent_provider_forgery_invalidates_known_effect(
    contract_data, server, monkeypatch, forgery, corrupt_episode, forge_behavior
):
    import dspx.services.reading_pilot as pilot
    from dspx.services.program_runtime_episode import _validate_provider_evidence
    from dspx.services.reading_pilot_verification import write_private

    server.mode = "http500" if forgery == "false_success" else "valid"
    prepared = prepare(contract_data)
    child = pilot._child
    facts = {}

    def forge_after_native_execution(root, contract, case):
        outcome = child(root, contract, case)
        if case == "A":
            assert outcome.status == "returned"
            assert outcome.observed_digest is not None
            genuine = pilot.verify_case(root, contract, 0, outcome.observed_digest)
            facts.update(effect=genuine["effect"], dispatches=genuine["dispatches"])
            path = root / "A.provider.json"
            raw = path.read_bytes()
            write_private(root / "original-provider.json", raw)
            receipt = json.loads(raw)
            evidence = receipt["provider"]["effect_evidence"]
            attempt = evidence["attempts"][0]
            disposition = (
                "preflight_rejected"
                if forgery == "zero_dispatch"
                else "completed_success"
            )
            evidence["terminal_effect"] = attempt["effect_disposition"] = disposition
            attempt["dispatch_count"] = 0 if forgery == "zero_dispatch" else 1
            attempt["observed_model"] = (
                None if forgery == "zero_dispatch" else contract.route.model
            )
            _validate_provider_evidence(
                receipt["provider"]
            )  # Coherent, not malformed-count rejection.
            path.write_bytes(canonical(receipt))  # Synthetic adversarial fixture only.
            if forge_behavior:
                behavior_path = root / "A" / "behavior_results.json"
                behavior = json.loads(behavior_path.read_bytes())
                behavior["provider"] = receipt["provider"]
                behavior_path.write_bytes(canonical(behavior))
            if corrupt_episode:
                (root / "A" / "runtime_episode.json").write_bytes(b"broken fixture")
        return outcome

    monkeypatch.setattr(pilot, "_child", forge_after_native_execution)
    result = execute(contract_data, prepared)
    root = contract_data[0] / contract_data[1]["campaign_id"]
    assert facts == {
        "effect": "completed_failure"
        if forgery == "false_success"
        else "completed_success",
        "dispatches": 1,
    }
    assert len(server.requests) == 1
    assert result.state == "effect_indeterminate" and result.integrity == "failed"
    assert result.provider_effect is None and result.dispatches is None
    terminal = json.loads((root / "A.terminal.json").read_bytes())
    assert (
        terminal["effect"] == "effect_indeterminate" and terminal["dispatches"] is None
    )
    assert "provider_observation_sha256" not in terminal
    assert not (root / "B.intent.json").exists()
    frozen = (root / "result.json").read_bytes()
    assert execute(contract_data, prepared).state == "latched"
    assert (root / "result.json").read_bytes() == frozen and len(server.requests) == 1


@pytest.mark.parametrize("drift", ["whitespace", "malformed", "missing"])
def test_observation_reread_drift_invalidates_initial_capture(
    contract_data, server, monkeypatch, drift
):
    import dspx.services.reading_pilot as pilot

    prepared = prepare(contract_data)
    read_observation = pilot.read_provider_observation
    calls = 0

    def change_after_initial_capture(root, contract, index, observed_digest):
        nonlocal calls
        captured = read_observation(root, contract, index, observed_digest)
        calls += 1
        if calls == 1:
            assert (
                captured["effect"] == "completed_success"
                and captured["dispatches"] == 1
            )
            path = root / "A.provider.json"
            if drift == "missing":
                path.unlink()
            else:
                path.write_bytes(
                    path.read_bytes() + b" " if drift == "whitespace" else b"not JSON"
                )
        return captured

    monkeypatch.setattr(
        pilot, "read_provider_observation", change_after_initial_capture
    )
    result = execute(contract_data, prepared)
    assert result.state == "effect_indeterminate" and result.dispatches is None
    assert result.provider_effect is None and result.integrity == "failed"
    assert len(server.requests) == 1
    assert not (
        contract_data[0] / contract_data[1]["campaign_id"] / "B.intent.json"
    ).exists()


@pytest.mark.parametrize("artifact", ["reading_analysis_json", "runtime_episode.json"])
def test_unrelated_native_artifact_corruption_preserves_provider_fact(
    contract_data, server, monkeypatch, artifact
):
    import dspx.services.reading_pilot as pilot

    prepared = prepare(contract_data)
    child = pilot._child

    def damage_output_not_provider(root, contract, case):
        outcome = child(root, contract, case)
        if case == "A":
            assert outcome.status == "returned"
            (root / "A" / artifact).write_bytes(b"broken synthetic artifact")
        return outcome

    monkeypatch.setattr(pilot, "_child", damage_output_not_provider)
    result = execute(contract_data, prepared)
    assert result.state == "failed_integrity" and result.integrity == "failed"
    assert result.provider_effect == "completed_success"
    assert result.dispatches == len(server.requests) == 1
    assert not (
        contract_data[0] / contract_data[1]["campaign_id"] / "B.intent.json"
    ).exists()


def test_drift_after_readback_before_terminal_invalidates_capture(
    contract_data, server, monkeypatch
):
    import dspx.services.reading_pilot as pilot

    prepared = prepare(contract_data)
    native_verify = pilot.verify_case

    def drift_after_readback(root, contract, index, observed_digest):
        result = native_verify(root, contract, index, observed_digest)
        path = root / "A.provider.json"
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(pilot, "verify_case", drift_after_readback)
    result = execute(contract_data, prepared)
    assert result.state == "effect_indeterminate" and result.dispatches is None
    assert result.provider_effect is None and len(server.requests) == 1


@pytest.mark.parametrize(
    "failure", ["missing", "malformed", "truncated", "mismatch", "error", "deadline"]
)
def test_native_facts_require_successful_child_and_independent_digest(
    contract_data, server, monkeypatch, failure
):
    import dspx.services.reading_pilot as pilot
    from dspx.services.reading_pilot_custody import ChildOutcome

    prepared = prepare(contract_data)
    child = pilot._child

    def lose_custody(root, contract, case):
        outcome = child(root, contract, case)
        assert outcome.status == "returned" and case == "A"
        assert outcome.observed_digest is not None
        genuine = pilot.verify_case(root, contract, 0, outcome.observed_digest)
        assert genuine["dispatches"] == 1
        assert genuine["effect"] == "completed_success"
        digests = {
            "missing": None,
            "malformed": "g" * 64,
            "truncated": outcome.observed_digest[:-1],
            "mismatch": "0" * 64,
        }
        if failure in digests:
            return ChildOutcome("returned", digests[failure])
        return ChildOutcome(
            "failed" if failure == "error" else "effect_indeterminate",
            outcome.observed_digest,
        )

    monkeypatch.setattr(pilot, "_child", lose_custody)
    result = execute(contract_data, prepared)
    root = contract_data[0] / contract_data[1]["campaign_id"]
    assert result.state == "effect_indeterminate" and result.dispatches is None
    assert result.provider_effect is None and len(server.requests) == 1
    assert not (root / "B.intent.json").exists()
    assert execute(contract_data, prepared).state == "latched"
    assert len(server.requests) == 1


@pytest.mark.parametrize("where", ["child", "returned_child", "readback"])
def test_parent_interruption_never_infers_zero(
    contract_data, server, monkeypatch, where
):
    import dspx.services.reading_pilot as pilot

    prepared = prepare(contract_data)
    child = pilot._child

    def interrupt(*args):
        if where == "returned_child":
            assert child(*args).status == "returned"
        raise KeyboardInterrupt

    monkeypatch.setattr(
        pilot, "verify_case" if where == "readback" else "_child", interrupt
    )
    result = execute(contract_data, prepared)
    assert result.dispatches == (1 if where == "readback" else None)
    assert len(server.requests) == (0 if where == "child" else 1)
    assert result.state == (
        "failed_integrity" if where == "readback" else "effect_indeterminate"
    )
    root = contract_data[0] / contract_data[1]["campaign_id"]
    assert not (root / "B.intent.json").exists()
    assert execute(contract_data, prepared).state == "latched"
