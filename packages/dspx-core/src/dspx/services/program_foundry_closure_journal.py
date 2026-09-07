"""Finite offline historical owner-journal reducer; no old-code imports."""

from __future__ import annotations

import re
from urllib.parse import urlsplit
from program_foundry_closure_io import (  # ty: ignore[unresolved-import]
    Rejected,
    Snapshot,
    canonical,
    closed,
    digest,
    equal,
    integer,
    require,
    sha,
)
from program_foundry_closure_profiles import DEPENDENCY_SHA256, FAMILIES, PROFILES  # ty: ignore[unresolved-import]


def journals(
    s: Snapshot, request: dict, result: dict, attempt_hash: str, eroot: str
) -> None:
    family = FAMILIES.get(request["provider"])
    if family is None:
        raise Rejected("historical_family_unsupported", "unsupported")
    model = request["model"]
    require(
        isinstance(model, str) and re.fullmatch(family["model_pattern"], model),
        "family_model",
    )
    config = result["jury"]["provider_config"]
    profile = PROFILES.get(config["owner_commit"])
    if profile is None:
        raise Rejected("historical_owner_unsupported", "unsupported")
    equal(config["owner_tree"], profile["tree"])
    equal(config["owner_version"], profile["version"])
    equal(config["source_identity_sha256"], profile["source_sha256"])
    equal(config["dependency_identity_sha256"], DEPENDENCY_SHA256)
    route_model = model.replace("/", ":")
    requested = f"dspy-lm-auth:{family['route']}:{route_model}"
    resolved = f"openai:{route_model}:chat"
    endpoint = family["endpoint"]
    extras = {}
    if endpoint is None:
        base = request["local_vllm_base_url"]
        parts = urlsplit(base)
        require(
            parts.scheme == "http"
            and parts.hostname in {"127.0.0.1", "localhost", "::1"}
            and parts.port
            and parts.path == "/v1"
            and not parts.username
            and not parts.password
            and not parts.query
            and not parts.fragment,
            "historical_endpoint",
        )
        endpoint = digest(
            b"dspx-oracle-semantic-v11-endpoint-origin-v1\0"
            + canonical(
                {"scheme": "http", "hostname": parts.hostname, "port": parts.port}
            )
        )
        extras = {"endpoint_origin": base, "endpoint_origin_sha256": endpoint}
    expected_config = {
        "status": "configured",
        "provider": request["provider"],
        "model": model,
        "requested_route": requested,
        "resolved_route": resolved,
        "auth_provider": family["auth_provider"],
        "credential_mode": "no-refresh",
        "reasoning_effort": None,
        "num_retries": 0,
        "cache": False,
        "timeout_seconds": family["timeout"],
        "sync_only": True,
        "fallback_allowed": False,
        "health_probe_allowed": False,
        "execution_task_id": request["execution_task_id"],
        "execution_claimant": request["execution_claimant"],
        "owner_commit": config["owner_commit"],
        "owner_tree": profile["tree"],
        "owner_version": profile["version"],
        "source_identity_sha256": profile["source_sha256"],
        "dependency_identity_sha256": DEPENDENCY_SHA256,
        **extras,
    }
    equal(config, expected_config, "provider_metadata")
    evidence = result["jury"]["provider_outcome_evidence"]
    rows = evidence["call_records"]
    n = len(result["juror_results"])
    if evidence["session_disposition"] != "complete":
        raise Rejected("historical_terminal_reducer_unsupported", "unsupported")
    equal(
        evidence,
        {
            "schema_version": "dspx-foundry-jury-provider-outcome-evidence-v1",
            "artifact_verification": "accepted_exact",
            "logical_call_total": n,
            "maximum_logical_calls": n,
            "maximum_provider_transports": n,
            "sync_only": True,
            "fallback_allowed": False,
            "health_probe_allowed": False,
            "retry_count": 0,
            "session_disposition": "complete",
            "stopped_after_call": None,
            "stop_reason": None,
            "call_records": rows,
        },
    )
    equal(len(rows), n)
    event_fields = {
        "kind",
        "error_class",
        "gate_ordinal",
        "observed_model",
        "protocol_event",
        "response_id_sha256",
        "status_class",
        "status_code",
    }
    kinds = [
        "wrapper_request_accepted",
        "transport_gate_entered",
        "transport_effect_pending",
        "transport_entered",
        "http_response_observed",
        "parsed_protocol_event_observed",
        "provider_response_completed",
    ]
    expected_aliases = set()
    for ordinal, (record, juror) in enumerate(
        zip(rows, result["juror_results"], strict=True), 1
    ):
        logical = digest(
            b"dspx-foundry-jury-logical-request-v1\0"
            + canonical(
                {
                    "contract_sha256": attempt_hash,
                    "ordinal": ordinal,
                    "juror_id": juror["juror_id"],
                    "execution_task_id": request["execution_task_id"],
                }
            )
        )
        process = digest(
            b"dspx-foundry-jury-process-v1\0"
            + canonical({"contract_sha256": attempt_hash})
        )
        gate = digest(
            b"dspx-foundry-jury-transport-gate-v1\0"
            + canonical({"logical_request_id": logical})
        )
        directory = f"{eroot}/provider-outcomes/{ordinal:02d}-{logical}"
        reservation_path = directory + "/reservation.json"
        wrapper = s.json(reservation_path)
        expected_aliases.add(reservation_path)
        closed(
            wrapper,
            {
                "schema_version",
                "reservation",
                "reservation_id",
                "artifact_verification",
            },
        )
        equal(wrapper["schema_version"], "dspx-soomfon-provider-outcome-consumption-v2")
        equal(wrapper["artifact_verification"], "accepted_exact")
        reservation = wrapper["reservation"]
        equal(
            digest(canonical(reservation["source_identity"])),
            profile["source_sha256"],
            "journal_source_identity",
        )
        equal(
            digest(canonical(reservation["dependency_identity"])),
            DEPENDENCY_SHA256,
            "journal_dependency_identity",
        )
        equal(
            reservation,
            {
                "schema_version": "dspx-provider-outcome-reservation-v1",
                "consumer_task_id": request["execution_task_id"],
                "ledger_sha256": attempt_hash,
                "process_id": process,
                "case_id": f"jury-{ordinal}",
                "logical_request_id": logical,
                "transport_gate_id": gate,
                "semantic_request_sha256": sha(record["semantic_request_sha256"]),
                "contract_sha256": attempt_hash,
                "mode": "sync",
                "requested_route": requested,
                "resolved_route": resolved,
                "endpoint_origin_sha256": endpoint,
                "source_identity": reservation["source_identity"],
                "dependency_identity": reservation["dependency_identity"],
            },
            "reservation_binding",
        )
        rid = digest(b"dspx-provider-outcome-reservation-v1\0" + canonical(reservation))
        equal(wrapper["reservation_id"], rid)
        hashes, response_id, observed = [], None, None
        for seq, kind in enumerate(kinds):
            event_path = f"{directory}/events/{seq:06d}.json"
            envelope = s.json(event_path)
            expected_aliases.add(event_path)
            event = closed(envelope["event"], event_fields)
            equal(event["kind"], kind, "journal_event_order")
            expected = dict.fromkeys(event_fields)
            expected["kind"] = kind
            if seq in {1, 2, 3, 4}:
                expected["gate_ordinal"] = 1
            if seq in {4, 6}:
                integer(event["status_code"], 299, 200)
                expected.update(status_class=2, status_code=event["status_code"])
            if seq == 5:
                response_id = sha(event["response_id_sha256"])
                expected.update(
                    protocol_event="response.completed", response_id_sha256=response_id
                )
            if seq == 6:
                observed = event["observed_model"]
                require(
                    observed is None
                    or (isinstance(observed, str) and len(observed) <= 128),
                    "observed_model_shape",
                )
                expected.update(response_id_sha256=response_id, observed_model=observed)
            equal(event, expected, "journal_event_shape")
            equal(
                envelope,
                {
                    "schema_version": "dspx-soomfon-provider-outcome-consumption-event-v2",
                    "reservation_id": rid,
                    "sequence": seq,
                    "previous_event_sha256": hashes[-1] if hashes else None,
                    "source_identity_sha256": profile["source_sha256"],
                    "dependency_identity_sha256": DEPENDENCY_SHA256,
                    "producer": {
                        "owner": "tryinget-dspy-lm-auth",
                        "commit": config["owner_commit"],
                        "tree": profile["tree"],
                        "version": profile["version"],
                    },
                    "event": event,
                },
            )
            hashes.append(s.hash(event_path))
        equal(
            record,
            {
                "call_ordinal": ordinal,
                "juror_id": juror["juror_id"],
                "reservation_id": rid,
                "journal_sha256": digest(
                    canonical(
                        {
                            "reservation_id": rid,
                            "event_sha256": hashes,
                            "artifact_verification": "accepted_exact",
                        }
                    )
                ),
                "semantic_request_sha256": reservation["semantic_request_sha256"],
                "provider_outcome_receipt": "accepted",
                "request_acknowledged": True,
                "external_effect_possible": True,
                "producer_terminal": "provider_response_completed",
                "status_class": 2,
                "status_code": event["status_code"],
                "empirical_disposition": "not_evaluated",
                "reason": "attributable_completion_not_evaluated",
                "observed_model": observed,
            },
            "journal_record_projection",
        )
    declared_aliases = {
        p for p in s.aliases if p.startswith(eroot + "/provider-outcomes/")
    }
    equal(declared_aliases, expected_aliases, "journal_inventory_mismatch")
