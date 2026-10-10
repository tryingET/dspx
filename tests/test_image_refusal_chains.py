# summary: "AK6812: a direct image provider port refusal carries one precise fixed code and no exception chain."
# read_when:
#   - "Changing how the image custody transaction classifies refusals and interruptions."
"""Fixed, chain-free refusals at the nominal image provider port.

Given an admitted image run inside the guarded clean worker (a real
`ImageCustodySession`, `create_image_lm` and an exact `httpx.MockTransport`),
when `provider.invoke` is refused before any reservation, then the caller sees the
precise fixed refusal code with no cause or context; and when a genuine
interruption arrives, then it stays `image_interruption` with the existing terminal
semantics, again with no chain. The worker publishes payload-free facts only.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, NoReturn

import pytest

import dspx.image_custody as custody_owner
import dspx.image_effects as effects
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
from dspx.image_custody import (
    ImageAttemptTransaction,
    ImageCustodySession,
    parent_initializer,
)
from dspx.image_execution import _prepare
from dspx.image_privacy import image_privacy
from dspx.image_records import list_root, publish, read_record
from dspx.image_supervision import supervise_image_worker
from dspx.image_worker import worker_entry
from dspx.provider_contract import (
    ProviderImagePart,
    ProviderPartsMessage,
    ProviderRequest,
    ProviderTextPart,
)
from dspx.provider_registry import create_image_lm
from test_image_effects import _admit, _direct_request, _status, _transport

_HERE = "test_image_refusal_chains"
_PARAMS = (
    "candidate_fd input_fd custody_fd spy_fd preparation admission authority reserved"
)
_PAYLOAD = "synthetic-ak6812-interrupt-payload"
_IDLE = ["lock", "ready.json"]
_SLOT_1 = ["intent-1.json", "lock", "ready.json", "terminal-1.json"]
_SLOT_2 = sorted([*_SLOT_1, "intent-2.json", "terminal-2.json"])
# The exact fixed code alone: no cause, no context, no payload anywhere.
_CHAIN_FREE = {
    "cause_is_none": True,
    "context_is_none": True,
    "chain": [],
    "payload_in_chain": False,
}


def _interrupt(*args: object, **kwargs: object) -> NoReturn:
    raise KeyboardInterrupt(_PAYLOAD)


def _attempt(call, sends: list, lm, session, custody_fd: int) -> dict[str, Any]:
    """One port call, reduced to fixed facts: code, chain shape and side effects."""
    before = (len(sends), lm.provider.attempt_total)
    error: BaseException | None = None
    try:
        call()
    except BaseException as caught:  # recorded as fixed facts, never by text
        error = caught
    chain: list[BaseException] = []
    linked = None if error is None else error.__cause__ or error.__context__
    while linked is not None and len(chain) < 8:
        chain.append(linked)
        linked = linked.__cause__ or linked.__context__
    code = "none" if error is None else type(error).__name__
    if type(error) is ImageContractError:
        code = error.code
    return {
        "code": code,
        "cause_is_none": error is not None and error.__cause__ is None,
        "context_is_none": error is not None and error.__context__ is None,
        "chain": [
            f"{type(item).__name__}:{getattr(item, 'code', '')}" for item in chain
        ],
        "payload_in_chain": any(
            _PAYLOAD in repr(item) + str(item) for item in [*chain, error]
        ),
        "sends": len(sends) - before[0],
        "attempts": lm.provider.attempt_total - before[1],
        "custody": sorted(list_root(custody_fd)),
        "poisoned": session.poisoned,
    }


@worker_entry
def _refusal_entry(params: dict[str, Any]) -> dict[str, object]:
    row = closed(params, _PARAMS)
    raw = row["admission"].encode("ascii")
    admission = ImageAdmission(raw, digest("admission-v2", parse_json(raw)))
    bound = closed(row["authority"], "caller_expectation_sha256 root_dev root_ino")
    authority = SyntheticImageAuthority(
        raw,
        bound["caller_expectation_sha256"],
        bound["root_dev"],
        bound["root_ino"],
        _used=[False],
    )
    custody_fd, sends = row["custody_fd"], []
    rows: dict[str, dict[str, Any]] = {}
    with image_privacy() as active:
        program, context, rederived = _prepare(
            active,
            candidate_fd=row["candidate_fd"],
            input_fd=row["input_fd"],
            input_name="inputs.json",
            model=admission.record["model"],
            use_cot=False,
            limits=admission.record["limits"],
        )
        assert canonical(rederived) == row["preparation"].encode("ascii")
        session = ImageCustodySession(
            root_fd=custody_fd,
            admission=admission,
            authority=authority,
            context=context,
        )
        active.session = session
        lm = create_image_lm(session, transport=_transport("ok", sends))
        admitted = _direct_request(active, program, context, session)

        def attempt(case: str, call) -> None:
            rows[case] = _attempt(call, sends, lm, session, custody_fd)

        image = next(
            part
            for message in admitted.messages
            if isinstance(message, ProviderPartsMessage)
            for part in message.parts
            if type(part) is ProviderImagePart
        )
        for case, role in (("E07", "assistant"), ("E08", "system")):
            # The admitted pixels in a non-user message: refused before reservation.
            moved = ProviderPartsMessage(role, (ProviderTextPart("A"), image))
            request = ProviderRequest(admitted.model, (moved,), session)
            attempt(case, lambda request=request: lm.provider.invoke(request))
        with pytest.MonkeyPatch.context() as fault:
            # A genuine interruption inside the transaction, nothing reserved yet.
            fault.setattr(effects, "image_payload", _interrupt)
            attempt("pre_reserve_interrupt", lambda: lm.provider.invoke(admitted))
        attempt("admitted", lambda: lm.provider.invoke(admitted))
        real_finish, real_publish, fired = (
            ImageAttemptTransaction.finish,
            custody_owner.publish,
            [],
        )

        def finish_once(tx, disposition, *, failure_code=None):
            if not fired:  # interrupted between the durable intent and its terminal
                fired.append(True)
                _interrupt()
            return real_finish(tx, disposition, failure_code=failure_code)

        def terminal_unwritable(root_fd, name, record):
            if name.startswith("terminal-"):
                raise OSError(_PAYLOAD)
            return real_publish(root_fd, name, record)

        with pytest.MonkeyPatch.context() as fault:
            fault.setattr(ImageAttemptTransaction, "finish", finish_once)
            if row["reserved"] == "durability":
                fault.setattr(custody_owner, "publish", terminal_unwritable)
            attempt("reserved_interrupt", lambda: lm.provider.invoke(admitted))
    commitment = publish(row["spy_fd"], "observation.json", rows)
    return _status("completed", commitment)


def _supervised(tmp: Path, reserved: str) -> dict[str, Any]:
    """One supervised clean-worker run over a two-slot admitted custody root."""
    opened: list[int] = []
    with pytest.MonkeyPatch.context() as env:
        env.setenv("MLFLOW_ENABLE", "0")
        env.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
        try:
            run = _admit(tmp, opened, slots=2, repeat=False)
            initialize = parent_initializer(
                run.fds["custody"],
                run.authority,
                run.admission,
                source_sha256=run.admission.record["source_package_sha256"],
                manifest_sha256=digest("manifest-v2", run.manifest),
            )
            names = ("candidate", "inputs", "custody", "spy")
            params = {
                "candidate_fd": run.fds["candidate"],
                "input_fd": run.fds["inputs"],
                "custody_fd": run.fds["custody"],
                "spy_fd": run.fds["spy"],
                "preparation": run.prepared.raw.decode("ascii"),
                "admission": run.admission.raw.decode("ascii"),
                "authority": {
                    "caller_expectation_sha256": run.authority.caller_expectation_sha256,
                    "root_dev": run.authority.root_dev,
                    "root_ino": run.authority.root_ino,
                },
                "reserved": reserved,
            }
            status = supervise_image_worker(
                f"{_HERE}:_refusal_entry",
                params,
                fds=tuple(run.fds[name] for name in names),
                wall_ms=30_000,
                parent_action=initialize,
            )
            raw = read_record(run.fds["spy"], "observation.json")
            assert status == _status("completed", sha(raw))
            custody = run.fds["custody"]
            root = list_root(custody)
            return {
                "rows": parse_json(raw),
                "root": sorted(root),
                "terminals": {
                    name: parse_json(read_record(custody, name))
                    for name in root
                    if name.startswith("terminal-")
                },
            }
        finally:
            for fd in opened:
                os.close(fd)


@pytest.fixture(scope="module")
def refusals(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return _supervised(tmp_path_factory.mktemp("refusal-chains"), "interrupt")


@pytest.fixture(scope="module")
def durability(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return _supervised(tmp_path_factory.mktemp("refusal-durability"), "durability")


def _facts(row: dict[str, Any], *names: str) -> dict[str, Any]:
    return {name: row[name] for name in ("code", *_CHAIN_FREE, *names)}


@pytest.mark.parametrize("case", ["E07", "E08"])
def test_pre_reserve_refusal_at_the_provider_port_is_precise_and_chain_free(
    refusals: dict[str, Any], case: str
) -> None:
    """Given an assistant- or system-role image at the nominal provider port,
    when the custody transaction refuses it before any reservation,
    then the caller gets image_admission_invalid itself, never a chained
    image_interruption, and no slot, send or attempt is consumed."""
    assert refusals["rows"][case] == {
        "code": "image_admission_invalid",
        **_CHAIN_FREE,
        "sends": 0,
        "attempts": 0,
        "custody": _IDLE,
        "poisoned": False,
    }


def test_genuine_interruptions_stay_image_interruption_without_a_chain(
    refusals: dict[str, Any],
) -> None:
    """Given a KeyboardInterrupt inside the custody transaction,
    when nothing is reserved yet, then it is image_interruption with no reservation;
    when the intent is durable but the terminal is not, then it is
    image_interruption, the session is poisoned and the terminal records the
    interruption; and neither failure chains the interrupt or its text."""
    rows = refusals["rows"]
    assert rows["pre_reserve_interrupt"] == {
        "code": "image_interruption",
        **_CHAIN_FREE,
        "sends": 0,
        "attempts": 0,
        "custody": _IDLE,
        "poisoned": False,
    }
    # The refusals and the interruption left the root usable: slot 1 succeeds.
    assert rows["admitted"]["code"] == "none" and rows["admitted"]["sends"] == 1
    assert rows["admitted"]["custody"] == _SLOT_1
    reserved = rows["reserved_interrupt"]
    assert _facts(reserved, "sends", "custody", "poisoned") == {
        "code": "image_interruption",
        **_CHAIN_FREE,
        "sends": 1,
        "custody": _SLOT_2,
        "poisoned": True,
    }
    terminals = refusals["terminals"]
    assert terminals["terminal-1.json"]["provider_disposition"] == "completed_success"
    second = terminals["terminal-2.json"]
    assert second["provider_disposition"] == "effect_indeterminate"
    assert second["failure_code"] == "interruption"
    assert second["dispatch_count"] == 1
    assert second["finalization_kind"] == "direct_provider"
    assert refusals["root"] == _SLOT_2


def test_unwritable_interruption_terminal_is_image_durability_without_a_chain(
    durability: dict[str, Any],
) -> None:
    """Given an interruption after the durable intent,
    when the custody transaction cannot publish the interruption terminal either,
    then the caller gets the terminal's own image_durability with no chain (neither
    the write failure nor the interrupt), the session is poisoned and no second
    terminal is claimed."""
    reserved = durability["rows"]["reserved_interrupt"]
    assert _facts(reserved, "sends", "poisoned") == {
        "code": "image_durability",
        **_CHAIN_FREE,
        "sends": 1,
        "poisoned": True,
    }
    assert "intent-2.json" in durability["root"]
    assert sorted(durability["terminals"]) == ["terminal-1.json"]
