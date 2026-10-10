# summary: "Live-capable image binding: the worker's authority mirror and the admission-bound request controls on the wire."
# read_when:
#   - "Changing the image authority mirror, its approval-binding params or the image request body controls."

"""AK6918: one route for synthetic and live image execution.

The parent passes its reserved authority's bindings (mode, caller expectation, custody
root and the approval binding) as closed scalar params; the worker mirrors only the
admitted mode, and its custody session re-runs `validate_admission`, which compares
every approval field with the admission. The mirror is usable only through the
parent's ready handshake. The request body adds exactly the admission's controls.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Final, cast

from .image_admission import (
    ImageAdmission,
    LiveImageAuthority,
    SyntheticImageAuthority,
    closed,
    digest,
    hash_value,
    request_controls,
    require,
)

APPROVAL_FIELDS = (
    "owning_ak_task",
    "operator_evidence_ref",
    "parent_confirmation_sha256",
)
_BOUND = "mode caller_expectation_sha256 root_dev root_ino " + " ".join(APPROVAL_FIELDS)
_THINKING = {"off": False}  # admitted thinking -> vLLM chat-template `enable_thinking`
_FORMATTED = frozenset({"model", "messages"})
_WIRE = _FORMATTED | {"max_tokens", "chat_template_kwargs"}
_FINISHED = frozenset({"stop", "length"})
_REASONING = ("reasoning", "reasoning_content")
_EVIDENCE = re.compile(r"ak://evidence/[1-9][0-9]*\Z")
# A copied live admission is replayable for at most 30 minutes from its not-before.
LIVE_VALIDITY_MS: Final = 1_800_000


def live_confirmation_sha256(record: dict[str, Any]) -> str:
    """The digest the owner confirms for one live admission (computed by the harness).

    It covers every admitted field except `operator_evidence_ref` and the confirmation
    itself: the owner's AK evidence carries this digest and the admission then names
    that evidence, so neither commitment is circular.
    """
    unsigned = copy.deepcopy(record)
    approval = unsigned["approval_binding"]
    approval["operator_evidence_ref"] = approval["parent_confirmation_sha256"] = None
    return digest("live-confirmation-v1", unsigned)


def require_live_approval(record: dict[str, Any], authority: object) -> None:
    """A live admission's approval binding, in the parent and the worker session.

    Well formed, confirmed over these very bytes, held with exact types by the parent
    authority, and valid for at most `LIVE_VALIDITY_MS`. Code checks data identity
    only; the operator is authenticated out of band (AK evidence).
    """
    task, ref, confirmation = (record["approval_binding"][k] for k in APPROVAL_FIELDS)
    require(type(task) is int and task > 0)
    require(type(ref) is str and _EVIDENCE.fullmatch(ref) is not None)
    require(hash_value(confirmation))
    require(confirmation == live_confirmation_sha256(record))
    held = tuple(getattr(authority, key) for key in APPROVAL_FIELDS)
    require(tuple(type(value) for value in held) == (int, str, str))
    require(held == (task, ref, confirmation))
    deadlines = record["deadlines"]
    window = deadlines["expires_utc_ms"] - deadlines["not_before_utc_ms"]
    require(window <= LIVE_VALIDITY_MS)


def authority_params(
    authority: SyntheticImageAuthority | LiveImageAuthority,
) -> dict[str, object]:
    """Parent side: the reserved authority's bindings, closed and scalar-only."""
    live = type(authority) is LiveImageAuthority
    return {
        "mode": "live" if live else "synthetic",
        "caller_expectation_sha256": authority.caller_expectation_sha256,
        "root_dev": authority.root_dev,
        "root_ino": authority.root_ino,
        **{key: getattr(authority, key) if live else None for key in APPROVAL_FIELDS},
    }


def mirror_authority(
    admission: ImageAdmission, params: object
) -> SyntheticImageAuthority | LiveImageAuthority:
    """Worker side: a fresh mirror of the admitted mode only, every field present."""
    row = closed(params, _BOUND)
    record = admission.record
    require(type(record) is dict and row["mode"] == record.get("mode"))
    approval = tuple(row[key] for key in APPROVAL_FIELDS)
    expectation = row["caller_expectation_sha256"]
    root = (row["root_dev"], row["root_ino"])
    if row["mode"] == "synthetic":
        require(all(value is None for value in approval))
        return SyntheticImageAuthority(admission.raw, expectation, *root, _used=[False])
    require(
        row["mode"] == "live"
        and type(approval[0]) is int
        and type(approval[1]) is str
        and type(approval[2]) is str
    )
    return LiveImageAuthority(
        admission.raw, expectation, *root, *approval, _used=[False]
    )


def controlled_body(body: object, record: dict[str, Any]) -> bytes:
    """The wire body: the formatted request plus only the admission's controls."""
    controls = request_controls(record["request_controls"])
    require(type(body) is dict and set(body) == _FORMATTED)
    wire = dict(cast(dict[str, Any], body))
    wire["max_tokens"] = controls["max_output_tokens"]
    wire["chat_template_kwargs"] = {"enable_thinking": _THINKING[controls["thinking"]]}
    return json.dumps(wire, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sent_controls(body: dict[str, Any]) -> dict[str, Any]:
    """Every body key besides the formatted model and messages, as observed."""
    return {key: value for key, value in body.items() if key not in _FORMATTED}


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate key")
    return dict(pairs)


def require_admitted_controls(raw: bytes, record: dict[str, Any]) -> None:
    """Send-time drift check on the exact request bytes, before reservation or send."""
    controls = request_controls(record["request_controls"])
    try:  # an ambiguous duplicate key is drift too
        parsed = json.loads(raw, object_pairs_hook=_unique)
    except (TypeError, ValueError):
        parsed = None
    require(type(parsed) is dict and set(parsed) == _WIRE)
    sent = cast(dict[str, Any], parsed)
    switch = sent["chat_template_kwargs"]
    require(
        sent["model"] == record["model"]
        and type(sent["max_tokens"]) is int
        and sent["max_tokens"] == controls["max_output_tokens"]
        and type(switch) is dict
        and set(switch) == {"enable_thinking"}
        and switch["enable_thinking"] is _THINKING[controls["thinking"]]
    )


def honoured_controls(data: bytes, record: dict[str, Any]) -> bool:
    """Whether a provider-validated response shows the admitted controls took effect.

    Every choice finished with "stop" or "length" and carries no reasoning (absent or
    null only), and `usage.completion_tokens` is an integer within the admitted cap.
    Anything else is a completed failure, never success.
    """
    cap = request_controls(record["request_controls"])["max_output_tokens"]
    try:
        payload = json.loads(data)
        tokens, choices = payload["usage"]["completion_tokens"], payload["choices"]
        return (
            type(tokens) is int
            and 0 <= tokens <= cap
            and type(choices) is list
            and bool(choices)
            and all(
                choice["finish_reason"] in _FINISHED
                and all(choice["message"].get(key) is None for key in _REASONING)
                for choice in choices
            )
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False
