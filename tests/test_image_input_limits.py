# summary: "AK6810: the declared input depth/node ceilings are reachable through production prepare."
# read_when:
#   - "Changing image input depth/node ceilings or the derived source/shape commitments."

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dspx.image_admission import ImageContractError, bounded_tree, canonical
from dspx.image_admission import validate_source
from dspx.image_execution import prepare_image_execution
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from test_image_source_io import PIXELS, b64, image

# Exactly at the ceilings: "x" at depth 16; 1 + 1 + 3 + 1 + 4090 == 4096 nodes.
_TREES = {
    "depth": ("list[" * 15 + "str" + "]" * 15, 15, (15, 4096)),
    "nodes": ("list[str]", 4090, (16, 4095)),
}


def _tree(kind: str, size: int) -> object:
    if kind == "nodes":
        return ["x"] * size
    value: object = "x"
    for _ in range(size):
        value = [value]
    return value


def _prepare(root: Path, annotation: str, document: object):
    materialize_program_from_intent(
        ProgramIntent(
            name="InputLimitProbe",
            objective="Describe bounded synthetic pixels.",
            input_fields=[
                {"name": "visual", "type": "str"},
                {"name": "text", "type": annotation},
            ],
            output_fields=[{"name": "answer", "type": "str"}],
            options={"image_enabled": True},
        ),
        outdir=root / "candidate",
    )
    for name in ("inputs", "preparation"):
        (root / name).mkdir(mode=0o700)
    (root / "inputs" / "inputs.json").write_text(json.dumps(document))
    fds = [
        os.open(root / name, os.O_RDONLY | os.O_DIRECTORY)
        for name in ("candidate", "inputs", "preparation")
    ]
    try:
        return prepare_image_execution(
            candidate_fd=fds[0],
            input_fd=fds[1],
            input_name="inputs.json",
            preparation_fd=fds[2],
            model="synthetic-vision-fixture",
        )
    finally:
        for fd in fds:
            os.close(fd)


@pytest.mark.parametrize("over", [False, True], ids=["at-limit", "limit+1"])
@pytest.mark.parametrize("kind", ["depth", "nodes"])
def test_s09_e11_e12_production_prepare_reaches_the_declared_depth_and_node_limits(
    tmp_path: Path, kind: str, over: bool
) -> None:
    """AK6810 (S09-E11/E12): Given a shipped image candidate whose text field takes
    the tree; When the input is exactly at depth 16 or 4096 nodes, the production
    prepare entry succeeds in the clean worker and derives the source, shape and text
    commitments within one custody record; When it is one beyond, the same fixed code
    refuses and nothing is published."""
    annotation, size, tighter = _TREES[kind]
    document = {
        "visual": image("image_base64", b64(PIXELS)),
        "text": _tree(kind, size + over),
    }
    if over:
        with pytest.raises(ImageContractError) as caught:
            _prepare(tmp_path, annotation, document)
        assert (caught.value.code, caught.value.args) == (
            "image_input_invalid",
            ("image_input_invalid",),
        )
        assert os.listdir(tmp_path / "preparation") == []
        return
    bounded_tree(document)
    with pytest.raises(ImageContractError, match="^image_budget$"):
        bounded_tree(document, max_depth=tighter[0], max_nodes=tighter[1])
    prepared = _prepare(tmp_path, annotation, document)
    record = prepared.record
    source = validate_source(record["source"])
    assert len(prepared.raw) <= 65_536 and canonical(source) in prepared.raw
    assert [row["occurrence_id"] for row in source["source_occurrences"]] == ["s000001"]
    assert sum(row["char_count"] for row in source["plain_text_slots"]) == (
        1 if kind == "depth" else 4090
    )


def test_source_package_v2_has_one_increasing_text_row_per_slot() -> None:
    """Review follow-up: the per-slot text rows are their own schema version."""
    from test_image_admission import _source

    source = {**_source(), "schema_version": "dspx-image-source-package-v2"}
    rows = [
        {"field_slot": slot, "text_sha256": "f" * 64, "char_count": 1}
        for slot in (1, 3)
    ]
    assert (
        validate_source({**source, "plain_text_slots": rows})["plain_text_slots"]
        == rows
    )
    for bad in (rows[::-1], [rows[0], rows[0]]):  # reordered or repeated slots
        with pytest.raises(ImageContractError, match="^image_admission_invalid$"):
            validate_source({**source, "plain_text_slots": bad})
    with pytest.raises(ImageContractError, match="^image_admission_invalid$"):
        validate_source({**source, "schema_version": "dspx-image-source-package-v1"})
