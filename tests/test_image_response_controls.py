# summary: "AK6918 review: a completion must show the admitted controls took effect (no reasoning, usage within the cap, stop/length), else a completed failure."
# read_when:
#   - "Changing how image responses are classified against the admitted request controls."
"""AK6918 review: response-side check of the admitted request controls.

After the provider's own validation, the worker re-parses the observed body. Unless
no choice carries reasoning (absent or null only), `usage.completion_tokens` is an
integer within the admitted `max_output_tokens` and every `finish_reason` is "stop" or
"length", the attempt is a completed failure (`response`): never success, never an
artifact. Synthetic rows run here in the clean worker; the same bodies run live
against the loopback server in `test_image_live_execution`.
"""

from __future__ import annotations

import json
from typing import Any

import dspy
import httpx
import pytest

import test_image_effects as effects
from dspx.image_admission import (
    ImageAdmission,
    ImageContractError,
    SyntheticImageAuthority,
    canonical,
    closed,
    digest,
    parse_json,
    sha,
)
from dspx.image_artifacts import publish_image_run
from dspx.image_custody import ImageCustodySession, parent_initializer
from dspx.image_execution import ImagePreparation, _prepare
from dspx.image_privacy import image_privacy
from dspx.image_records import list_root, read_record
from dspx.image_supervision import supervise_image_worker
from dspx.image_worker import worker_entry
from dspx.provider_registry import create_image_lm

_HERE = "test_image_response_controls"
_CAP = 256  # the admitted max_output_tokens of every shared fixture admission
admit = effects.admit  # the shared prepared synthetic admission


def response_body(model: str, variant: str, cap: int, text: str) -> bytes:
    """One canned completion; only `variant` departs from a controlled response."""
    message: dict[str, Any] = {"role": "assistant", "content": text}
    choice: dict[str, Any] = {"index": 0, "message": message, "finish_reason": "stop"}
    usage: dict[str, Any] = {
        "prompt_tokens": 40,
        "completion_tokens": 9,
        "total_tokens": 49,
    }
    if variant == "valid_null_reasoning":
        message.update(reasoning_content=None, reasoning=None)
    elif variant == "valid_length":
        choice["finish_reason"] = "length"
    elif variant == "valid_at_cap":
        usage.update(completion_tokens=cap, total_tokens=40 + cap)
    elif variant in {"reasoning_content", "reasoning"}:
        message[variant] = "hidden deliberation"
    elif variant == "tokens_over_cap":
        usage.update(completion_tokens=cap + 1, total_tokens=41 + cap)
    elif variant.startswith("finish_"):
        choice["finish_reason"] = variant.removeprefix("finish_")
        if variant == "finish_missing":
            del choice["finish_reason"]
    else:
        assert variant in {"valid", "usage_missing"}, variant
    body: dict[str, Any] = {"model": model, "choices": [choice]}
    if variant != "usage_missing":
        body["usage"] = usage
    return json.dumps(body).encode()


VALID = ("valid", "valid_null_reasoning", "valid_length", "valid_at_cap")
IGNORED = (
    "reasoning_content",
    "reasoning",
    "usage_missing",
    "tokens_over_cap",
    "finish_tool_calls",
    "finish_content_filter",
    "finish_missing",
)
_PARAMS = "candidate_fd input_fd custody_fd artifact_fd preparation admission expectation variant"


@worker_entry
def _response_entry(params: dict[str, Any]) -> dict[str, object]:
    row = closed(params, _PARAMS)
    preparation = ImagePreparation(row["preparation"].encode("ascii"))
    raw = row["admission"].encode("ascii")
    admission = ImageAdmission(raw, digest("admission-v3", parse_json(raw)))
    record = admission.record
    root = (record["custody"]["root_dev"], record["custody"]["root_ino"])
    held = SyntheticImageAuthority(raw, row["expectation"], *root, _used=[False])
    custody_fd = row["custody_fd"]
    cap = record["request_controls"]["max_output_tokens"]
    body = response_body(record["model"], row["variant"], cap, effects._ANSWER)

    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"Content-Type": "application/json"}
        return httpx.Response(200, headers=headers, content=body, request=request)

    with image_privacy() as active:
        program, context, rederived = _prepare(
            active,
            candidate_fd=row["candidate_fd"],
            input_fd=row["input_fd"],
            input_name="inputs.json",
            model=record["model"],
            use_cot=False,
            limits=record["limits"],
        )
        assert canonical(rederived) == preparation.raw
        session = ImageCustodySession(
            root_fd=custody_fd, admission=admission, authority=held, context=context
        )
        active.session = session
        lm = create_image_lm(session, transport=httpx.MockTransport(handler))
        try:
            with dspy.context(lm=lm):
                answer = program(**context.materialized()).answer
        except ImageContractError:
            terminal = read_record(custody_fd, "terminal-1.json")
            failure = parse_json(terminal)["failure_code"]
            return effects._status("failed", sha(terminal), failure)
        active.check()
        binding = publish_image_run(
            session,
            artifact_fd=row["artifact_fd"],
            outputs={"answer": answer},
            route="direct",
        )
        session.close_run(binding, outcome="completed")
    return effects._status("completed", sha(read_record(custody_fd, "closure.json")))


@pytest.mark.parametrize("variant", [*VALID, *IGNORED])
def test_synthetic_response_must_show_the_admitted_controls_took_effect(
    admit, variant: str
) -> None:
    """Given a synthetic admission (max_output_tokens 256, thinking off) and a
    completion that <variant>; When the clean worker classifies it; Then a controlled
    completion (no reasoning, usage within the cap, stop or length) succeeds, and any
    other is one completed failure `response` with no artifact or closure."""
    run = admit()
    assert run.admission.record["request_controls"]["max_output_tokens"] == _CAP
    initialize = parent_initializer(
        run.fds["custody"],
        run.authority,
        run.admission,
        source_sha256=run.admission.record["source_package_sha256"],
        manifest_sha256=digest("manifest-v2", run.manifest),
    )
    names = ("candidate", "inputs", "custody", "artifacts")
    result = supervise_image_worker(
        f"{_HERE}:_response_entry",
        {
            "candidate_fd": run.fds["candidate"],
            "input_fd": run.fds["inputs"],
            "custody_fd": run.fds["custody"],
            "artifact_fd": run.fds["artifacts"],
            "preparation": run.prepared.raw.decode("ascii"),
            "admission": run.admission.raw.decode("ascii"),
            "expectation": run.authority.caller_expectation_sha256,
            "variant": variant,
        },
        fds=tuple(run.fds[name] for name in names),
        wall_ms=30_000,
        parent_action=initialize,
    )
    custody = run.fds["custody"]
    terminal_raw = read_record(custody, "terminal-1.json")
    terminal = parse_json(terminal_raw)
    body = response_body(effects._MODEL, variant, _CAP, effects._ANSWER)
    # The classified body is exactly the canned one: digest and length only.
    assert terminal["response_sha256"] == sha(body)
    assert terminal["response_byte_count"] == len(body)
    assert terminal["dispatch_count"] == 1
    if variant in VALID:
        closure = read_record(custody, "closure.json")
        assert result == effects._status("completed", sha(closure))
        assert terminal["provider_disposition"] == "completed_success"
        assert list_root(run.fds["artifacts"]) != []
        return
    assert result == effects._status("failed", sha(terminal_raw), "response")
    assert terminal["provider_disposition"] == "completed_failure"
    assert terminal["failure_code"] == "response"
    assert terminal["observed_model"] == effects._MODEL
    assert terminal["result_finalization_completed"] is False
    assert sorted(list_root(custody)) == effects._SPENT_ROOT
    assert list_root(run.fds["artifacts"]) == []
