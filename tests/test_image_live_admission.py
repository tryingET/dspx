# summary: "AK6918 review: a live approval binding is bound to its own admission bytes, type-checked in the parent and valid for at most 30 minutes."
# read_when:
#   - "Changing the live approval binding, its confirmation digest or the live validity window."
"""AK6918 review follow-ups for live admissions (parent rows; the worker session runs
the same `validate_admission`, so a mirrored authority meets every row again).

The parent confirmation is `digest("live-confirmation-v1", A')`, where A' is the
admission with `operator_evidence_ref` and `parent_confirmation_sha256` set to null.
The evidence reference stays outside the digest so that the owner's AK evidence can
carry the confirmation and the admission can then name that evidence: no cycle.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

import test_image_admission as admission_tests
from dspx.image_admission import LiveImageAuthority, canonical, digest
from test_image_admission import _World, _refused

world = admission_tests.world  # the shared synthetic admission fixture
_INVALID = "image_admission_invalid"
_FIELDS = ("owning_ak_task", "operator_evidence_ref", "parent_confirmation_sha256")
_TASK, _REF = 6610, "ak://evidence/14880"


def _confirmation(record: dict[str, Any]) -> str:
    """The expected digest, written out independently of the production helper."""
    unsigned = copy.deepcopy(record)
    unsigned["approval_binding"]["operator_evidence_ref"] = None
    unsigned["approval_binding"]["parent_confirmation_sha256"] = None
    return digest("live-confirmation-v1", unsigned)


def _live(
    world: _World,
    *,
    task: object = _TASK,
    ref: object = _REF,
    confirmation: object = None,
    **edits: object,
) -> dict[str, Any]:
    """A live admission over the world's record; confirmation None means its own."""
    record = copy.deepcopy({**world.record, "mode": "live", **edits})
    record["approval_binding"] = dict(zip(_FIELDS, (task, ref, None), strict=True))
    own = _confirmation(record) if confirmation is None else confirmation
    record["approval_binding"]["parent_confirmation_sha256"] = own
    return record


def _held(world: _World, record: dict[str, Any], *grant: Any) -> LiveImageAuthority:
    """The exact parent authority over `record`, or one holding `grant`."""
    bound = grant or tuple(record["approval_binding"][key] for key in _FIELDS)
    return LiveImageAuthority(
        canonical(record), admission_tests._EXPECT, *world.root, *bound
    )


def _validate(world: _World, record: dict[str, Any], held: Any):
    return world.validate(canonical(record), held)


# ---------------------------------------------------------------- confirmation


def test_live_admission_validates_with_the_confirmation_of_its_own_bytes(
    world: _World,
) -> None:
    """Given a live admission whose parent confirmation is the live-confirmation-v1
    digest of its own bytes (evidence reference and confirmation null); When the
    exact parent authority validates it; Then it is admitted, and the public helper
    computes that same digest for the AK6610 harness."""
    from dspx.image_live import live_confirmation_sha256

    record = _live(world)
    assert _validate(world, record, _held(world, record))
    assert live_confirmation_sha256(record) == _confirmation(record)
    # The helper ignores whatever confirmation and evidence reference it is given.
    other = copy.deepcopy(record)
    other["approval_binding"].update(
        operator_evidence_ref="ak://evidence/1", parent_confirmation_sha256="0" * 64
    )
    assert live_confirmation_sha256(other) == live_confirmation_sha256(record)


_ELSEWHERE: dict[str, dict[str, Any]] = {  # bytes the confirmation was made for
    "endpoint": {"canonical_base_endpoint": "http://127.0.0.1:8001/v1"},
    "model": {"model": "other-vision-fixture"},
    "max_output_tokens": {
        "request_controls": {"max_output_tokens": 255, "thinking": "off"}
    },
    "task": {"approval_binding": {"owning_ak_task": 6611}},
    "custody": {"custody": {"caller_binding_sha256": "9" * 64}},
}


@pytest.mark.parametrize("case", ["arbitrary", *_ELSEWHERE])
def test_a_confirmation_for_other_bytes_never_admits_a_live_run(
    world: _World, case: str
) -> None:
    """Given a live admission whose confirmation is an arbitrary hash or the digest of
    an admission with another endpoint, model, output cap, task or custody binding;
    When the parent holding exactly that binding validates; Then it refuses."""
    record = _live(world)
    if case == "arbitrary":
        foreign = "5" * 64
    else:
        other = copy.deepcopy(record)
        for key, value in _ELSEWHERE[case].items():
            other[key] = {**other[key], **value} if type(value) is dict else value
        assert canonical(other) != canonical(record)
        foreign = _confirmation(other)
    record = _live(world, confirmation=foreign)
    _refused(_INVALID, lambda: _validate(world, record, _held(world, record)))


def test_the_evidence_reference_is_bound_by_the_parent_not_the_digest(
    world: _World,
) -> None:
    """Given one confirmation and two evidence references; When each admission is
    validated by its own exact parent; Then both admit (the owner's evidence names the
    digest, the admission names the evidence), and a parent holding the other
    reference refuses."""
    first, second = _live(world), _live(world, ref="ak://evidence/14881")
    shared = first["approval_binding"]["parent_confirmation_sha256"]
    assert second["approval_binding"]["parent_confirmation_sha256"] == shared
    assert _validate(world, first, _held(world, first))
    assert _validate(world, second, _held(world, second))
    crossed = _held(world, second, _TASK, _REF, shared)
    _refused(_INVALID, lambda: _validate(world, second, crossed))


# ------------------------------------------------- parent authority field types


class _Text(str):
    """Equal to the admitted string, but not a str."""


_FIELD_TYPES = {
    "task_boolean": (1, lambda grant: (True, *grant[1:])),
    "evidence_str_subclass": (
        _TASK,
        lambda grant: (grant[0], _Text(grant[1]), grant[2]),
    ),
    "confirmation_str_subclass": (_TASK, lambda grant: (*grant[:2], _Text(grant[2]))),
}


@pytest.mark.parametrize("case", list(_FIELD_TYPES))
def test_the_parent_type_checks_the_live_authority_fields(
    world: _World, case: str
) -> None:
    """Given an admitted approval binding and a parent authority whose field is equal
    but of another type (True for task 1, a str subclass); When the parent validates;
    Then it refuses; the same authority with exact types admits."""
    task, alter = _FIELD_TYPES[case]
    record = _live(world, task=task)
    grant = tuple(record["approval_binding"][key] for key in _FIELDS)
    assert _validate(world, record, _held(world, record, *grant))
    altered = alter(grant)
    assert altered == grant  # equal by value: only the type differs
    _refused(_INVALID, lambda: _validate(world, record, _held(world, record, *altered)))


# ---------------------------------------------------------------- validity window


@pytest.mark.parametrize(
    ("mode", "window", "admitted"),
    [
        ("live", 1_800_000, True),
        ("live", 1_800_001, False),
        ("synthetic", 3_600_000, True),
    ],
)
def test_a_live_admission_is_valid_for_at_most_thirty_minutes(
    world: _World, mode: str, window: int, admitted: bool
) -> None:
    """Given an admission whose not-before to expiry window is <window> ms; When the
    parent validates it; Then a live admission admits only up to 30 minutes, so a
    copied live admission cannot be replayed for long; synthetic is unchanged."""
    start = world.record["deadlines"]["not_before_utc_ms"]
    deadlines = {
        **world.record["deadlines"],
        "not_before_utc_ms": start,
        "expires_utc_ms": start + window,
    }
    if mode == "live":
        record = _live(world, deadlines=deadlines)
        held = _held(world, record)
    else:
        record = {**world.record, "deadlines": deadlines}
        held = world.held(canonical(record))
    if admitted:
        assert _validate(world, record, held)
    else:
        _refused(_INVALID, lambda: _validate(world, record, held))
