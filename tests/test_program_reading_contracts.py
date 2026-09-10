"""Synthetic contract vectors and trusted test transport; no private fixtures."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from dspx.services.program_reading_contracts import (
    FAMILIES,
    ExpectedReading,
    canonical_bytes,
    digest,
    identity,
    intent_hash,
    native_input_bytes,
    native_output_bytes,
    raw_hash,
    strict_json,
    stub_only_environment,
    validate_inputs,
    validate_outputs,
)

FIXTURES = Path(__file__).parent / "fixtures/program_gen/pdf_transition"


@pytest.fixture(autouse=True)
def reading_test_environment(_default_provider_stub, monkeypatch):
    """Normalize only conftest's two test knobs after its safety fixture runs.

    MLflow remains disabled and network/provider guards are NOT removed. The
    evidence-root override applies to in-process generic synthesis tests, not
    these explicit inert candidates in fresh workers. Restore both after test.
    """
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("DSPX_TEST_MODULE_SYNTHESIS_EVIDENCE_ROOT", raising=False)


def make_inputs(
    *,
    stage="reading",
    candidate_hash="sha256:" + "0" * 64,
    purpose_index=0,
    request_id="synthetic-request",
    revision=1,
    mode="puzzle",
    previous=None,
):
    case = strict_json((FIXTURES / "reading_cases.json").read_bytes())
    source = {
        "synthetic": True,
        "source_ref": case["source_ref"],
        "markdown_sha256": raw_hash(case["markdown"].encode()),
    }
    puzzles = {"synthetic": True, "puzzles": case["puzzles"]}
    context = {
        "request_id": request_id,
        "synthetic": True,
        "source_sha256": digest(source),
        "puzzle_snapshot_sha256": digest(puzzles),
    }
    linkage = {
        "source_sha256": digest(source),
        "puzzle_snapshot_sha256": digest(puzzles),
        "candidate_puzzle_ids": [r["puzzle_id"] for r in case["puzzles"]],
        "candidate_puzzle_suggestions": [],
    }
    inputs = {
        "source_package_manifest_json": canonical_bytes(source).decode(),
        "marker_markdown": case["markdown"],
        "existing_wiki_index_json": '{"synthetic":true,"notes":[]}',
        "declared_output_root": "synthetic-review-only",
        "puzzle_set_snapshot_json": canonical_bytes(puzzles).decode(),
        "producer_context_json": canonical_bytes(context).decode(),
    }
    intent = None
    if stage == "reading":
        intent = {
            "schema_version": "working-reading-intent-v1",
            "intent_id": "wri:synthetic-owner",
            "revision": revision,
            "supersedes": identity(previous) if previous else None,
            "decision_id": "synthetic-decision",
            "source_ref": case["source_ref"],
            "candidate_puzzle_ids": linkage["candidate_puzzle_ids"],
            "candidate_provenance": linkage,
            "reviewed_input_hash": "sha256:" + "a" * 64,
            "mode": mode,
            "selected_puzzle_id": case["puzzles"][purpose_index]["puzzle_id"]
            if mode == "puzzle"
            else None,
            "reader_purpose": case["owner_reviewed_purposes"][purpose_index],
            "exception_reason": ""
            if mode == "puzzle"
            else "Preserve source without puzzle commitment.",
            "authority": "noncanonical_working_intent_only",
            "consumer_status": "recorded_request_no_live_consumer",
        }
        intent["hash"] = intent_hash(intent)
        inputs["working_reading_intent_json"] = canonical_bytes(intent).decode()
        inputs["reading_intent_binding_json"] = canonical_bytes(
            identity(intent)
        ).decode()
    expected = ExpectedReading(
        stage,
        request_id,
        source["source_ref"],
        digest(source),
        digest(puzzles),
        candidate_hash,
        raw_hash(native_input_bytes(inputs)),
        identity(intent) if intent else None,
    )
    return inputs, expected, intent


def rebind_inputs(inputs, expected, intent):
    """Test owner appends an explicit generation; never producer output rebinding."""
    intent["hash"] = intent_hash(intent)
    inputs["working_reading_intent_json"] = canonical_bytes(intent).decode()
    inputs["reading_intent_binding_json"] = canonical_bytes(identity(intent)).decode()
    return replace(
        expected,
        input_raw_sha256=raw_hash(native_input_bytes(inputs)),
        reading_intent_binding=identity(intent),
    )


def request_inputs(request):
    text = request.messages[-1].text
    matches = re.findall(r"\[\[ ## (\w+) ## \]\]\n(.*?)(?=\n\[\[ ## |\Z)", text, re.S)
    # DSPy's final instruction is not part of the final field's value.
    result = {key: value.strip() for key, value in matches}
    for key in list(result):
        if key.endswith("_json"):
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(result[key])
            result[key] = canonical_bytes(obj).decode()
    return result


def synthetic_outputs(inputs, disposition="candidates"):
    """Generate held-out responses from actual provider-visible inputs, no demos.

    Deliberately synthetic logic is a plumbing probe, NOT a reading-quality test.
    Purpose selects source evidence and a different observable experimental test.
    """
    source = strict_json(inputs["source_package_manifest_json"])
    context = strict_json(inputs["producer_context_json"])
    markdown = inputs["marker_markdown"].rstrip() + "\n"
    intent = (
        strict_json(inputs["working_reading_intent_json"])
        if "working_reading_intent_json" in inputs
        else None
    )
    binding = identity(intent) if intent else None
    common = {
        "request_id": context["request_id"],
        "reading_intent_binding": binding,
        "source_sha256": context["source_sha256"],
    }
    purpose = (
        intent["reader_purpose"] if intent else "Consider water and heat measurements"
    )
    heat = "heat" in purpose and "water" not in purpose
    excerpt = markdown.split(". ")[1 if heat else 0]
    start = markdown.index(excerpt)
    evidence = {
        "source_ref": source["source_ref"],
        "markdown_sha256": source["markdown_sha256"],
        "start": start,
        "end": start + len(excerpt),
        "excerpt": excerpt,
        "excerpt_sha256": raw_hash(excerpt.encode()),
        "quotation_status": "exact",
        "page": "1",
        "section": "garden",
        "paragraph": "1",
    }
    if intent is None:
        puzzles = strict_json(inputs["puzzle_set_snapshot_json"])["puzzles"]
        rows = (
            [
                {
                    "candidate_id": row["puzzle_id"],
                    "proposed_reader_purpose": row["question"],
                    "rationale": "Compare supplied question with garden observation.",
                    "uncertainty": "Synthetic relevance is not approval.",
                    "alternatives": [],
                    "evidence": evidence,
                }
                for row in puzzles
            ]
            if disposition == "candidates"
            else []
        )
        value = {
            **common,
            "disposition": disposition,
            "rationale": "Supplied observations permit tentative measurement questions.",
            "uncertainty": "Limited observations; owner review needed.",
            "alternatives": [],
            "evidence": evidence,
            "later_puzzle_linkage": {
                "source_sha256": context["source_sha256"],
                "puzzle_snapshot_sha256": context["puzzle_snapshot_sha256"],
                "candidate_puzzle_ids": [r["candidate_id"] for r in rows],
                "candidate_puzzle_suggestions": rows,
            },
        }
        return {"reading_proposal_json": canonical_bytes(value).decode()}
    test = (
        "Measure shaded and unshaded temperature repeatedly over seven afternoons."
        if heat
        else "Measure infiltration time on matched compacted and loose paths after equal water volumes."
    )
    row = {
        **common,
        "section_id": "garden:1",
        "evidence": evidence,
        "title": "Garden measurement candidate",
        "markdown": excerpt + "\n\n" + test,
    }
    frame = {
        **row,
        "purpose_in_source": "Report limited garden observations, not establish long-term yield.",
        "whole_map": markdown,
        "selected_parts": excerpt,
        "whole_synthesis": "Both observations remain limited; " + test,
        "counterevidence": "Neither observation establishes long-term yield.",
        "levels": {
            f"L{n}": {"content": excerpt + " | " + test, "evidence": evidence}
            for n in range(1, 7)
        },
    }
    contrary = "Neither observation establishes long-term yield."
    frame["contrary_evidence"] = {
        **evidence,
        "start": markdown.index(contrary),
        "end": markdown.index(contrary) + len(contrary),
        "excerpt": contrary,
        "excerpt_sha256": raw_hash(contrary.encode()),
    }
    from dspx.services.program_reading_receipts import LEVEL_FIELDS

    for level, value in frame["levels"].items():
        value.update(common)
        value["operations"] = {
            key: "insufficient_evidence: synthetic structural probe, not a completed reading"
            for key in LEVEL_FIELDS[level]
        }
    frame["levels"]["L1"]["operations"]["paraphrase"] = (
        "The source reports an observation: " + excerpt
    )
    frame["levels"]["L2"]["operations"]["example_origin"] = (
        "generated synthetic example, not source testimony"
    )
    frame["levels"]["L6"]["operations"]["observable_test"] = test
    frame["levels"]["L5"]["simulation"] = True
    frame["levels"]["L6"]["added_extension"] = True
    values = {
        family: {
            **common,
            "canonical_mutation_performed": False,
            "rows": [copy.deepcopy(row)],
        }
        for family in FAMILIES
    }
    values["distillation_frames_json"]["rows"] = [frame]
    values["review_packet_json"] = {
        **common,
        "canonical_mutation_performed": False,
        "note_campaign_review_packet": {
            **common,
            "schema_version": "mobile-note-campaign-review-packet-v2",
            "artifact_type": "note_campaign_review_packet",
            "packet_state": "generated",
            "raw_artifact_views": {
                "candidate_notes": [row],
                "campaign_rows": [
                    {
                        **common,
                        "candidate_name": row["title"],
                        "recommended_next_step": test,
                    }
                ],
                "downstream": {"measurement_proposals": [row]},
            },
        },
    }
    return {key: canonical_bytes(value).decode() for key, value in values.items()}


def transport(request):
    outputs = synthetic_outputs(request_inputs(request))
    if "reasoning" in request.messages[0].text:
        outputs["reasoning"] = (
            "Synthetic transport selects an observation and measurement from the supplied purpose."
        )
    return canonical_bytes(outputs).decode()


def missing_transport(request):
    output = synthetic_outputs(request_inputs(request))
    output.pop("frontmatter_plans_json")
    output.pop("wiki_note_drafts_json")
    return canonical_bytes(output).decode()


def review_defect_outputs(inputs, defect):
    values = {k: strict_json(v) for k, v in synthetic_outputs(inputs).items()}
    draft = values["wiki_note_drafts_json"]["rows"][0]
    packet = values["review_packet_json"]["note_campaign_review_packet"]
    note = packet["raw_artifact_views"]["candidate_notes"][0]
    if defect == "draft":
        del draft["title"]
        del draft["markdown"]
    elif defect == "quote":
        note["evidence"]["excerpt"] = "Not in the supplied source"
        note["evidence"]["excerpt_sha256"] = "sha256:" + "f" * 64
    elif defect == "paragraph":
        note["paragraphs"] = [
            {
                **draft,
                "request_id": "old-request",
                "reading_intent_binding": {
                    "intent_id": "old",
                    "revision": 900,
                    "hash": "sha256:" + "e" * 64,
                },
                "source_sha256": "sha256:" + "d" * 64,
            }
        ]
    elif defect == "hidden":
        note["unrecognized_payload"] = {"arbitrary": [draft]}
    else:
        packet[defect] = True
    return {k: canonical_bytes(v).decode() for k, v in values.items()}


@pytest.mark.parametrize(
    "defect",
    [
        "draft",
        "quote",
        "paragraph",
        "hidden",
        "review_eligible",
        "canonical_apply_allowed",
        "canonical_mutation_performed",
    ],
)
def test_review_hold_nested_rejection(defect):
    inputs, expected, _ = make_inputs()
    with pytest.raises(ValueError):
        validate_outputs(review_defect_outputs(inputs, defect), inputs, expected)


def review_invalid_transport(request):
    return canonical_bytes(
        review_defect_outputs(request_inputs(request), "draft")
    ).decode()


def malformed_transport(request):
    return "{broken synthetic response"


def no_fit_transport(request):
    return canonical_bytes(
        synthetic_outputs(request_inputs(request), "no_match")
    ).decode()


def proposal_with_alternatives(inputs):
    value = strict_json(synthetic_outputs(inputs)["reading_proposal_json"])
    suggestion = value["later_puzzle_linkage"]["candidate_puzzle_suggestions"][0]
    alternative = copy.deepcopy(suggestion)
    value["alternatives"] = [alternative]
    suggestion["alternatives"] = [copy.deepcopy(alternative)]
    return value


@pytest.mark.parametrize(
    "place",
    [
        "envelope",
        "linkage",
        "suggestion",
        "alternative",
        "nested_alternative",
        "evidence",
        "insufficient_evidence",
    ],
)
@pytest.mark.parametrize(
    "field,value",
    [
        ("canonical_apply_allowed", True),
        ("review_eligible", True),
        ("canonical_mutation_performed", True),
        ("hidden_payload", {"approval": True}),
    ],
)
def test_proposal_closed_recursive_schemas(place, field, value):
    inputs, expected, _ = make_inputs(stage="proposal")
    proposal = proposal_with_alternatives(inputs)
    linkage = proposal["later_puzzle_linkage"]
    suggestion = linkage["candidate_puzzle_suggestions"][0]
    if place == "insufficient_evidence":
        suggestion["evidence"] = {
            "status": "insufficient_evidence",
            "reason": "Synthetic gap.",
        }
    target = {
        "envelope": proposal,
        "linkage": linkage,
        "suggestion": suggestion,
        "alternative": proposal["alternatives"][0],
        "nested_alternative": suggestion["alternatives"][0],
        "evidence": suggestion["evidence"],
        "insufficient_evidence": suggestion["evidence"],
    }[place]
    target[field] = value
    with pytest.raises(ValueError):
        validate_outputs(
            {"reading_proposal_json": canonical_bytes(proposal).decode()},
            inputs,
            expected,
        )


def test_proposal_valid_recursive_alternatives_and_member_checks():
    inputs, expected, _ = make_inputs(stage="proposal")
    value = proposal_with_alternatives(inputs)

    def output():
        return {"reading_proposal_json": canonical_bytes(value).decode()}

    assert validate_outputs(output(), inputs, expected)
    value["alternatives"][0]["candidate_id"] = "invented-puzzle"
    with pytest.raises(ValueError):
        validate_outputs(output(), inputs, expected)


def test_proposal_alternatives_depth_is_bounded():
    inputs, expected, _ = make_inputs(stage="proposal")
    value = proposal_with_alternatives(inputs)
    leaf = value["later_puzzle_linkage"]["candidate_puzzle_suggestions"][1]
    current = value
    for _ in range(17):
        current["alternatives"] = [copy.deepcopy(leaf)]
        current = current["alternatives"][0]
    with pytest.raises(ValueError, match="structure"):
        validate_outputs(
            {"reading_proposal_json": canonical_bytes(value).decode()}, inputs, expected
        )


def forged_proposal_transport(request):
    output = synthetic_outputs(request_inputs(request))
    value = strict_json(output["reading_proposal_json"])
    value["later_puzzle_linkage"]["candidate_puzzle_suggestions"][0][
        "review_eligible"
    ] = True
    output["reading_proposal_json"] = canonical_bytes(value).decode()
    return canonical_bytes(output).decode()


def test_full_working_intent_fixed_golden():
    # Independently fixed owner-shaped UTF-8 bytes, checked with sha256sum.
    # No helper-generated identities/defaults or runtime-derived expected digest.
    golden = (
        '{"authority":"noncanonical_working_intent_only",'
        '"candidate_provenance":{"candidate_puzzle_ids":["puzzle:heat"],'
        '"candidate_puzzle_suggestions":[],"puzzle_snapshot_sha256":'
        '"sha256:2222222222222222222222222222222222222222222222222222222222222222",'
        '"source_sha256":"sha256:1111111111111111111111111111111111111111111111111111111111111111"},'
        '"candidate_puzzle_ids":["puzzle:heat"],"consumer_status":"recorded_request_no_live_consumer",'
        '"decision_id":"synthetic:decision","exception_reason":"","intent_id":"wri:golden",'
        '"mode":"puzzle","owner_extension":{"checked":false,"value":"ä"},'
        '"reader_purpose":"Prüfe Wärme – ohne Gewissheit.","reviewed_input_hash":'
        '"sha256:3333333333333333333333333333333333333333333333333333333333333333",'
        '"revision":1,"schema_version":"working-reading-intent-v1",'
        '"selected_puzzle_id":"puzzle:heat","source_ref":"synthetic:golden","supersedes":null}'
    )
    fixed = "sha256:f19af6ed1e3ce13d9602a058ce88b21ebcd89479471c37ae625c8855e0ffa3ab"
    value = json.loads(golden)
    assert canonical_bytes(value) == golden.encode("utf-8")
    assert raw_hash(golden.encode("utf-8")) == fixed
    value["hash"] = fixed
    assert intent_hash(value) == fixed
    value["owner_extension"]["checked"] = True
    assert intent_hash(value) != fixed


def test_golden_bytes():
    value = {"z": "ä", "a": [True, None, 2]}
    assert canonical_bytes(value) == b'{"a":[true,null,2],"z":"\xc3\xa4"}'
    assert native_input_bytes({"z": "ä", "a": "x"}) == (
        b'{\n  "inputs": {\n    "a": "x",\n    "z": "\xc3\xa4"\n  }\n}\n'
    )
    assert native_output_bytes(' {"ä":1}  \n') == b' {"\xc3\xa4":1}\n'
    assert (
        raw_hash(b"abc")
        == "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert (
        digest(value)
        == "sha256:f822400ac1eccd1a209e8ce1a8100fb8a285a22b2e65570713ff29f850fce31b"
    )
    assert (
        raw_hash(native_input_bytes({"z": "ä", "a": "x"}))
        == "sha256:f9a5e696b13a678e422e70de9db0fb4a99a6eac9c88e6419a07c3227e16ebcc9"
    )
    assert (
        raw_hash(native_output_bytes(' {"ä":1}  \n'))
        == "sha256:69ce58469a156cddb9db0c18b3b5a6278d6a3aa7fc481acea0f13f04eb17dd05"
    )
    assert digest({"hash": "excluded?", "z": "ä"}) != intent_hash(
        {"hash": "excluded?", "z": "ä"}
    )
    assert intent_hash({"hash": "anything", "z": "ä"}) == digest({"z": "ä"})


@pytest.mark.parametrize(
    "raw", ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', "[" * 2000]
)
def test_strict_json_rejects(raw):
    with pytest.raises((ValueError, RecursionError)):
        strict_json(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", True),
        ("mode", "approve"),
        ("selected_puzzle_id", "invented"),
        ("source_ref", "other"),
        ("reader_purpose", ""),
        ("candidate_provenance", {}),
        ("authority", "canonical"),
    ],
)
def test_bad_owner_intent(field, value):
    inputs, expected, intent = make_inputs()
    intent[field] = value
    expected = rebind_inputs(inputs, expected, intent)
    with pytest.raises(ValueError):
        validate_inputs(inputs, expected)


def test_full_hash_includes_extensions_and_direct_rules():
    inputs, expected, intent = make_inputs(mode="wiki_atlas_direct")
    assert validate_inputs(inputs, expected) == intent
    intent["new_owner_field"] = "full exact content must be hashed"
    inputs["working_reading_intent_json"] = canonical_bytes(intent).decode()
    expected = replace(expected, input_raw_sha256=raw_hash(native_input_bytes(inputs)))
    with pytest.raises(ValueError, match="hash"):
        validate_inputs(inputs, expected)
    intent["exception_reason"] = ""
    expected = rebind_inputs(inputs, expected, intent)
    with pytest.raises(ValueError, match="reason"):
        validate_inputs(inputs, expected)


@pytest.mark.parametrize("disposition", ["candidates", "no_match", "direct", "defer"])
def test_proposal_dispositions(disposition):
    inputs, expected, _ = make_inputs(stage="proposal")
    outputs = synthetic_outputs(inputs, disposition)
    assert validate_outputs(outputs, inputs, expected)


@pytest.mark.parametrize("family", FAMILIES)
def test_all_eight_families_required(family):
    inputs, expected, _ = make_inputs()
    outputs = synthetic_outputs(inputs)
    outputs.pop(family)
    with pytest.raises(ValueError, match="families"):
        validate_outputs(outputs, inputs, expected)


@pytest.mark.parametrize(
    "defect", ["echo", "empty", "L5", "excerpt", "section", "packet", "downstream"]
)
def test_structural_output_rejections(defect):
    inputs, expected, _ = make_inputs()
    values = {k: strict_json(v) for k, v in synthetic_outputs(inputs).items()}
    if defect == "echo":
        values["section_units_json"]["reading_intent_binding"] = {}
    elif defect == "empty":
        values["wiki_note_drafts_json"]["rows"] = []
    elif defect == "L5":
        del values["distillation_frames_json"]["rows"][0]["levels"]["L5"]
    elif defect == "excerpt":
        values["evidence_cards_json"]["rows"][0]["evidence"]["excerpt"] = "forged"
    elif defect == "section":
        values["frontmatter_plans_json"]["rows"][0]["section_id"] = "missing"
    elif defect == "packet":
        values["review_packet_json"]["note_campaign_review_packet"][
            "raw_artifact_views"
        ]["candidate_notes"] = []
    else:
        values["review_packet_json"]["note_campaign_review_packet"][
            "raw_artifact_views"
        ]["downstream"]["measurement_proposals"][0]["request_id"] = "old"
    with pytest.raises(ValueError):
        validate_outputs(
            {k: canonical_bytes(v).decode() for k, v in values.items()},
            inputs,
            expected,
        )


@pytest.mark.parametrize("level", ["L1", "L2", "L3", "L4", "L5", "L6"])
def test_original_operations_are_not_just_level_labels(level):
    inputs, expected, _ = make_inputs()
    outputs = synthetic_outputs(inputs)
    frames = strict_json(outputs["distillation_frames_json"])
    frames["rows"][0]["levels"][level]["operations"] = {}
    outputs["distillation_frames_json"] = canonical_bytes(frames).decode()
    with pytest.raises(ValueError, match="operations"):
        validate_outputs(outputs, inputs, expected)


def test_boolean_echo_and_expected_revision_rejected():
    inputs, expected, _ = make_inputs()
    outputs = synthetic_outputs(inputs)
    family = strict_json(outputs["section_units_json"])
    family["reading_intent_binding"]["revision"] = True
    outputs["section_units_json"] = canonical_bytes(family).decode()
    with pytest.raises(ValueError, match="binding"):
        validate_outputs(outputs, inputs, expected)
    expected = replace(
        expected,
        reading_intent_binding={**expected.reading_intent_binding, "revision": True},
    )
    with pytest.raises(ValueError, match="binding"):
        validate_inputs(inputs, expected)


def test_insufficient_evidence_explicit():
    inputs, expected, _ = make_inputs()
    values = synthetic_outputs(inputs)
    row = strict_json(values["evidence_cards_json"])
    row["rows"][0]["evidence"] = {
        "status": "insufficient_evidence",
        "reason": "No repeated measurements supplied.",
    }
    values["evidence_cards_json"] = canonical_bytes(row).decode()
    assert validate_outputs(values, inputs, expected)


def test_environment_requires_explicit_stub_and_rejects_ambient():
    env = {
        "DSPX_PROVIDER": "stub",
        "MLFLOW_ENABLE": "0",
        "DSPX_POLICY_ALLOW_NETWORK_MUTATE": "0",
        "DSPX_POLICY_DISALLOWED_CAPS": "network.read,network.mutate",
    }
    stub_only_environment(env)
    for key, value in [
        ("DSPX_PROVIDER", "openai-compatible"),
        ("DSPX_CONFIG", "somewhere"),
        ("DSPX_REPLAY_FIXTURE_JSON", "{}"),
        ("DSPX_CUSTODY", "x"),
        ("DSPX_ACTIVATION", "1"),
        ("DSPX_FALLBACK", "stub"),
    ]:
        with pytest.raises(ValueError):
            stub_only_environment({**env, key: value})
