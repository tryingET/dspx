"""One immutable A/B batch; caller custody is not consent. See examples/reading_pilot/README.md."""

from __future__ import annotations

import os
from functools import partial
from pathlib import Path
import sys
import traceback
from typing import Literal

from dspx.services.reading_pilot_custody import ProviderObservationConflict, _child
from dspx.services.reading_pilot_verification import (
    PilotContract,
    PilotStatus,
    canonical,
    inputs_for,
    inventory,
    private_parent,
    public_spec,
    read_private,
    require,
    runtime_fingerprint,
    sha,
    strict_json,
    validate_source,
    verify_case,
    write_private,
    write_json,
    _root,
)


def _template(raw: bytes) -> dict:
    data = strict_json(raw)
    allowed = "schema_version name objective input_fields output_fields options".split()
    require(set(data) == set(allowed))
    require(
        data["schema_version"] == "program-intent-v2" and data["name"] == "ReadingPilot"
    )
    require(isinstance(data["objective"], str) and 0 < len(data["objective"]) <= 4000)
    require(
        data["options"]
        == {"module_inference": False, "focused_json_bundle_runtime": False}
    )
    for key, fields in (
        ("input_fields", ["source_text", "reviewed_locators_json", "reader_purpose"]),
        ("output_fields", ["reading_analysis_json"]),
    ):
        require([r["name"] for r in data[key]] == fields)
        for row in data[key]:
            require(set(row) == {"name", "type", "desc"} and row["type"] == "str")
            require(isinstance(row["desc"], str) and 0 < len(row["desc"]) <= 4000)
    data["output_fields"][0]["desc"] += (
        " Exact frozen contract: " + canonical(public_spec()).decode()
    )
    return data


def _contract(root: Path, expected: str) -> PilotContract:
    raw = read_private(root / "contract.json")
    require(sha(raw) == expected)
    contract = PilotContract.model_validate(strict_json(raw))
    require(contract.parent_identity_sha256 == private_parent(root.parent))
    require(contract.campaign_id == root.name)
    require(contract.public_spec_sha256 == sha(canonical(public_spec())))
    require(read_private(root / "public.json") == canonical(public_spec()))
    require(contract.runtime_sha256 == runtime_fingerprint())
    template = read_private(root / "template.json")
    require(sha(template) == contract.template_sha256)
    _template(template)
    source = read_private(root / "source" / "passage.txt")
    validate_source(contract, source)
    require(
        read_private(root / "source" / "locators.json")
        == canonical([x.model_dump() for x in contract.locators])
    )
    require(
        read_private(root / "purposes.json")
        == canonical([p.model_dump() for p in contract.purposes])
    )
    return contract


def prepare_pilot(
    *,
    parent: Path,
    contract_payload: dict,
    source: bytes,
    template_bytes: bytes,
    expected_contract_sha256: str,
) -> PilotStatus:
    try:
        contract = PilotContract.model_validate(contract_payload)
        require(sha(canonical(contract.model_dump())) == expected_contract_sha256)
        require(contract.parent_identity_sha256 == private_parent(parent))
        require(contract.runtime_sha256 == runtime_fingerprint())
        require(contract.public_spec_sha256 == sha(canonical(public_spec())))
        require(sha(template_bytes) == contract.template_sha256)
        validate_source(contract, source)
        _template(template_bytes)
        root = _root(parent, contract.campaign_id)
        root.mkdir(mode=0o700, exist_ok=False)
        for name in ("source", "home", "tmp", "cache"):
            (root / name).mkdir(mode=0o700)
        for name, raw in {
            "contract.json": canonical(contract.model_dump()),
            "template.json": template_bytes,
            "public.json": canonical(public_spec()),
            "source/passage.txt": source,
            "source/locators.json": canonical(
                [x.model_dump() for x in contract.locators]
            ),
            "purposes.json": canonical([p.model_dump() for p in contract.purposes]),
        }.items():
            write_private(root / name, raw)
        if _child(root, contract, None).status != "returned":
            return PilotStatus("failed")
        captured = inventory(root / "candidate")
        candidate_hash = sha(canonical(captured))
        write_private(root / "candidate-files.json", canonical(captured))
        return PilotStatus("prepared", candidate_sha256=candidate_hash)
    except Exception:
        return PilotStatus("rejected")


def _terminal(
    root: Path,
    state: Literal["completed", "failed", "failed_integrity", "effect_indeterminate"],
    contract_hash: str,
    candidate_hash: str,
    cases: list[dict],
    *,
    persist: bool = True,
) -> PilotStatus:
    result = {
        "schema_version": "reading-pilot-result-v1",
        "state": state,
        "contract_sha256": contract_hash,
        "candidate_sha256": candidate_hash,
        "cases": cases,
        "max_dispatches": 2,
        "semantic_review": "needed",
        "full_consumer_proved": False,
        "whole_book_supported": False,
        "canonical_apply_allowed": False,
        "independent_provider_observation_required": True,
    }
    raw = canonical(result)
    if persist:
        write_private(root / "result.json", raw)
    counts = [c["dispatches"] for c in cases]
    count = None if None in counts else sum(counts)
    last = cases[-1] if cases else {}
    return PilotStatus(
        state,
        count,
        last.get("formatting", "not_checked"),
        last.get("source_reference_integrity", "not_checked"),
        "needed",
        candidate_hash,
        sha(raw) if persist else None,
        provider_effect=last.get("effect")
        if last.get("provider_observation_sha256")
        else None,
        integrity="failed"
        if state == "failed_integrity"
        else last.get("integrity", "not_checked"),
    )


def read_provider_observation(
    root: Path, contract: PilotContract, index: int, observed_digest: str
) -> dict:
    """Only independently retained custody permits interpreting artifact facts."""
    from dspx.services.program_runtime_episode import _validate_provider_evidence

    name = contract.purposes[index].id
    raw = read_private(root / f"{name}.provider.json")
    if sha(raw) != observed_digest:
        raise ProviderObservationConflict
    receipt = strict_json(raw)
    reserve = strict_json(read_private(root / f"{name}.intent.json"))
    start = strict_json(read_private(root / "started.json"))
    binding = {
        "case": name,
        "contract_sha256": sha(canonical(contract.model_dump())),
        "candidate_sha256": start["candidate_sha256"],
        "inputs_sha256": reserve["inputs_sha256"],
    }
    require(set(receipt) == set(binding) | {"schema_version", "provider"})
    require(receipt["schema_version"] == "reading-pilot-provider-observation-v1")
    require(all(receipt[k] == v for k, v in binding.items()))
    require(
        reserve["contract_sha256"]
        == start["contract_sha256"]
        == binding["contract_sha256"]
    )
    provider = receipt["provider"]
    require(provider["metadata"]["provider"] == "openai-compatible")
    require("schema_version" not in provider["metadata"])
    require(
        reserve["max_dispatches"] == 2 and reserve["reserved_cumulative"] == index + 1
    )
    require(
        reserve["case"] == name
        and reserve["candidate_sha256"] == start["candidate_sha256"]
    )
    _validate_provider_evidence(provider)
    evidence = provider["effect_evidence"]
    require(
        evidence["attempt_total"] == 1
    )  # Native validation fixes length/truncation.
    count = evidence["attempts"][0]["dispatch_count"]
    require(type(count) is int)
    return {
        "effect": evidence["terminal_effect"],
        "dispatches": count,
        "provider_observation_sha256": sha(raw),
        "provider_sha256": sha(canonical(provider)),
        "inputs_sha256": receipt["inputs_sha256"],
    }


def run_pilot(
    *,
    parent: Path,
    campaign_id: str,
    expected_contract_sha256: str,
    expected_candidate_sha256: str,
    candidate_review_ref: str,
    operator_admission_ref: str,
) -> PilotStatus:
    started = False
    active = None
    current: dict = {}
    unknown = {
        "effect": "effect_indeterminate",
        "dispatches": None,
        "integrity": "failed",
    }
    cases: list[dict] = []
    try:
        root = _root(parent, campaign_id)
        finish = partial(
            _terminal,
            root,
            contract_hash=expected_contract_sha256,
            candidate_hash=expected_candidate_sha256,
            cases=cases,
        )
        contract = _contract(root, expected_contract_sha256)
        inventory(root)
        require(
            bool(candidate_review_ref.strip()) and bool(operator_admission_ref.strip())
        )
        require(operator_admission_ref == contract.operator_admission_ref)
        captured = inventory(root / "candidate")
        require(sha(canonical(captured)) == expected_candidate_sha256)
        require(read_private(root / "candidate-files.json") == canonical(captured))
        if (root / "started.json").exists():
            return PilotStatus("latched", None)
        reserved_names = "A B A.intent.json B.intent.json result.json A.provider.json B.provider.json".split()
        require(not any((root / n).exists() for n in reserved_names))
        binding = {
            "contract_sha256": expected_contract_sha256,
            "candidate_sha256": expected_candidate_sha256,
            "max_dispatches": 2,
        }
        write_json(
            root / "started.json",
            {
                **binding,
                "schema_version": "reading-pilot-start-v1",
                "candidate_review_ref": candidate_review_ref,
                "operator_admission_ref": operator_admission_ref,
                "resume_allowed": False,
            },
        )
        started = True
        for index, purpose in enumerate(contract.purposes):
            _contract(root, expected_contract_sha256)
            require(
                sha(canonical(inventory(root / "candidate")))
                == expected_candidate_sha256
            )
            inputs = inputs_for(
                contract, read_private(root / "source" / "passage.txt"), index
            )
            write_json(
                root / f"{purpose.id}.intent.json",
                {
                    **binding,
                    "case": purpose.id,
                    "reserved_cumulative": index + 1,
                    "inputs_sha256": sha(canonical(inputs)),
                },
            )
            active = purpose.id
            current = unknown
            outcome = _child(root, contract, active)
            captured_hash = outcome.observed_digest or ""
            try:
                require(outcome.status == "returned" and captured_hash)
                current = read_provider_observation(
                    root, contract, index, captured_hash
                )
            except Exception:
                pass  # Missing/untrustworthy observation: retain unknown, never infer zero.
            if current["dispatches"] is not None:
                try:
                    current = verify_case(root, contract, index, captured_hash)
                except ProviderObservationConflict:
                    current = unknown
                except Exception:
                    current = {**current, "integrity": "failed"}
                finally:
                    try:
                        raw = read_private(root / f"{active}.provider.json")
                        require(sha(raw) == captured_hash)
                    except Exception:
                        current = unknown
            cases.append(current)
            write_json(root / f"{active}.terminal.json", current)
            if current["effect"] == "effect_indeterminate":
                return finish("effect_indeterminate")
            if current["integrity"] == "failed":
                return finish("failed_integrity")
            if (
                current["effect"] != "completed_success"
                or current["formatting"] != "passed"
                or current["source_reference_integrity"] != "passed"
            ):
                return finish("failed")
        return finish("completed")
    except BaseException:
        if not started:
            return PilotStatus("rejected")
        # Keep an already captured provider fact even if readback/persistence is interrupted.
        if active and (not cases or cases[-1] is not current):
            cases.append(current)
        state = (
            "effect_indeterminate"
            if any(c["dispatches"] is None for c in cases)
            else "failed_integrity"
        )
        try:
            if active and not (root / f"{active}.terminal.json").exists():
                write_private(root / f"{active}.terminal.json", canonical(current))
            return finish(state)
        except Exception:
            return finish(state, persist=False)


def _worker(operation: str, root: Path, custody_fd: int | None = None) -> None:
    """Private child only; its stdout/stderr are captured before Python starts."""
    os.umask(0o077)
    contract = PilotContract.model_validate(
        strict_json(read_private(root / "contract.json"))
    )
    _contract(root, sha(canonical(contract.model_dump())))
    if operation == "prepare":
        from dspx.services.program_intent import ProgramIntent
        from dspx.services.program_service import materialize_program_from_intent

        materialize_program_from_intent(
            ProgramIntent.model_validate(
                _template(read_private(root / "template.json"))
            ),
            outdir=root / "candidate",
        )
        return
    require(operation in ("A", "B"))
    if custody_fd is None:
        raise ValueError("missing custody descriptor")
    os.set_inheritable(custody_fd, False)
    start = strict_json(read_private(root / "started.json"))
    reserve = strict_json(read_private(root / f"{operation}.intent.json"))
    require(start["contract_sha256"] == sha(canonical(contract.model_dump())))
    require(start["candidate_sha256"] == sha(canonical(inventory(root / "candidate"))))
    index = 0 if operation == "A" else 1
    require(
        reserve["case"] == operation and reserve["reserved_cumulative"] == index + 1
    )
    require(
        all(reserve[k] == start[k] for k in ("contract_sha256", "candidate_sha256"))
    )
    if operation == "B":
        prior = strict_json(read_private(root / "A.terminal.json"))
        require(
            prior
            == verify_case(root, contract, 0, prior["provider_observation_sha256"])
        )
        require(
            prior["effect"] == "completed_success"
            and prior["formatting"] == prior["source_reference_integrity"] == "passed"
        )
    write_json(root / f"{operation}.worker-claimed.json", {"case": operation})
    import dspy
    from dspx.services.program_runtime_episode import run_program_runtime_episode

    dspy.configure_cache(enable_disk_cache=False, enable_memory_cache=False)
    dspy.configure(
        adapter=dspy.ChatAdapter(use_json_adapter_fallback=False), callbacks=[]
    )
    inputs = inputs_for(contract, read_private(root / "source" / "passage.txt"), index)
    require(reserve["inputs_sha256"] == sha(canonical(inputs)))
    inputs_path = root / f"{operation}.inputs.json"
    write_json(inputs_path, {"inputs": inputs})
    workflow = run_program_runtime_episode(
        manifest_path=root / "candidate" / "manifest.json",
        inputs_path=inputs_path,
        outdir=root / operation,
        contract_mode="none",
        skip_oracle_index=True,
        run_oracle_semantic=False,
        capture_replay_fixture=False,
    )
    # Exclusive native-return custody precedes readback; not provider authentication.
    keys = "case contract_sha256 candidate_sha256 inputs_sha256".split()
    observation = {key: reserve[key] for key in keys}
    observation.update(
        schema_version="reading-pilot-provider-observation-v1",
        provider=workflow["steps"]["runtime_execution"]["provider"],
    )
    raw = canonical(observation)
    write_private(root / f"{operation}.provider.json", raw)
    # The pipe carries only the exact in-memory return's digest, never source/log bytes.
    payload = (sha(raw) + "\n").encode("ascii")
    require(os.write(custody_fd, payload) == 65)
    os.close(custody_fd)


if __name__ == "__main__":
    try:
        require(len(sys.argv) == (3 if sys.argv[1] == "prepare" else 4))
        _worker(
            sys.argv[1],
            Path(sys.argv[2]),
            None if sys.argv[1] == "prepare" else int(sys.argv[3]),
        )
    except BaseException:
        traceback.print_exc()  # Only private child log, never main API/tool output.
        sys.exit(1)
