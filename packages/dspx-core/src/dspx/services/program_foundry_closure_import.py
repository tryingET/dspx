"""Pure v1 import/quality identity joins; no recipe fidelity or acceptance grant."""

from __future__ import annotations

import copy
import json
import keyword
from pathlib import PurePosixPath
import re
from typing import Any, cast

from program_foundry_closure_io import (  # ty: ignore[unresolved-import]
    Rejected,
    Snapshot,
    canonical,
    closed,
    decode,
    digest,
    equal,
    integer,
    require,
    sha,
    sibling,
)


def pretty(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def intent(value: dict, *, exclude_none: bool = False) -> dict:
    """Finite already-normalized single-module v1 consumer profile.

    Default expansion matches ProgramIntent. Rich topologies/capabilities require
    another reviewed pure normalizer, never an import of historical executable code.
    """
    defaults = {
        "schema_version": "program-intent-v2",
        "name": "IntentProgram",
        "inputs": ["context"],
        "outputs": ["output"],
        "input_fields": [],
        "output_fields": [],
        "task_type": "single_module",
        "topology": {},
        "constraints": [],
        "examples": [],
        "examples_path": None,
        "dataset": {},
        "datasets": {},
        "metric": None,
        "quality_criteria": [],
        "runtime": {},
        "jury": {},
        "promotion": {},
        "options": {},
        "capabilities": {},
    }
    require(isinstance(value, dict) and "objective" in value, "intent_shape")
    require(not set(value) - (set(defaults) | {"objective"}), "intent_unknown_field")
    result = cast(dict[str, Any], {**defaults, **copy.deepcopy(value)})
    equal(result["schema_version"], "program-intent-v2")
    for key in ("name", "objective", "task_type"):
        require(isinstance(result[key], str) and result[key].strip(), "intent_text")
        result[key] = result[key].strip()
    for key in ("topology", "capabilities", "input_fields", "output_fields"):
        if result[key]:
            raise Rejected("intent_normalization_unsupported", "unsupported")
    if result["examples_path"] is not None:
        raise Rejected("external_examples_unsupported", "unsupported")
    for key in ("inputs", "outputs"):
        fields = result[key]
        require(
            isinstance(fields, list)
            and fields
            and all(isinstance(x, str) for x in fields),
            "intent_fields",
        )
        fields = [x.strip() for x in fields]
        require(
            len(set(fields)) == len(fields)
            and all(
                re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) and not keyword.iskeyword(x)
                for x in fields
            ),
            "intent_fields",
        )
        result[key] = fields
    require(not set(result["inputs"]) & set(result["outputs"]), "intent_field_overlap")
    for key in ("dataset", "datasets", "runtime", "jury", "promotion", "options"):
        require(isinstance(result[key], dict), "intent_mapping")
    require(
        isinstance(result["examples"], list) and 0 < len(result["examples"]) <= 64,
        "intent_examples",
    )
    criteria = result["quality_criteria"]
    require(isinstance(criteria, list) and 0 < len(criteria) <= 32, "quality_criteria")
    ids = set()
    for row in criteria:
        closed(
            row,
            {
                "id",
                "output_field",
                "evaluator",
                "required_concept_groups",
                "forbidden_concepts",
                "min_score",
            },
        )
        require(
            isinstance(row["id"], str) and row["id"] and row["id"] not in ids,
            "criterion_id",
        )
        ids.add(row["id"])
        require(row["output_field"] in result["outputs"], "criterion_output")
        if row["evaluator"] != "concept_coverage":
            raise Rejected("quality_evaluator_unsupported", "unsupported")
        require(
            type(row["min_score"]) in (int, float) and 0 <= row["min_score"] <= 1,
            "criterion_score",
        )
        row["min_score"] = float(row["min_score"])
        require(
            isinstance(row["required_concept_groups"], list)
            and row["required_concept_groups"],
            "criterion_groups",
        )
        for group in row["required_concept_groups"]:
            require(
                isinstance(group, list)
                and group
                and all(isinstance(x, str) and x.strip() == x and x for x in group),
                "criterion_terms",
            )
        require(
            isinstance(row["forbidden_concepts"], list)
            and all(isinstance(x, str) for x in row["forbidden_concepts"]),
            "criterion_forbidden",
        )
    return (
        {k: v for k, v in result.items() if v is not None} if exclude_none else result
    )


def intent_hash(value: dict) -> str:
    return digest(
        json.dumps(
            intent(value, exclude_none=True), sort_keys=True, allow_nan=False
        ).encode("utf-8")
    )


def runtime_inputs(value: dict) -> dict:
    return {
        "inputs": value["inputs"] if isinstance(value.get("inputs"), dict) else value
    }


def package_import(s: Snapshot) -> tuple[dict, dict]:
    package_path, manifest = s.expected("package_manifest")
    closed(
        manifest,
        {
            "schema_version",
            "producer",
            "recipe",
            "artifacts",
            "conformance",
            "non_authority",
            "package_sha256",
        },
    )
    equal(manifest["schema_version"], "misegraph-evidence-package-v1")
    equal(
        manifest["non_authority"],
        {
            "evidence_only": True,
            "acceptance_authority": False,
            "release_authority": False,
        },
    )
    equal(s.read(package_path), pretty(manifest), "package_serialization")
    equal(
        digest(pretty({k: v for k, v in manifest.items() if k != "package_sha256"})),
        manifest["package_sha256"],
        "package_hash",
    )
    equal(
        s.request["subject"],
        {
            "schema_version": manifest["schema_version"],
            "manifest_sha256": s.hash(package_path),
            "package_sha256": manifest["package_sha256"],
        },
    )
    closed(manifest["producer"], {"name", "version", "ir_schema_version"})
    equal(manifest["producer"]["name"], "misegraph")
    integer(manifest["producer"]["ir_schema_version"], 1, 1)
    closed(manifest["recipe"], {"id", "title"})
    closed(
        manifest["conformance"],
        {"status", "error_count", "warning_count", "deny_warnings"},
    )
    for key in ("error_count", "warning_count"):
        integer(manifest["conformance"][key], 100000)
    require(manifest["conformance"]["status"] in {"ok", "errors"}, "conformance_status")
    require(type(manifest["conformance"]["deny_warnings"]) is bool, "conformance_flag")
    required = {
        "source.mise": "mise_source",
        "canonical.json": "canonical_ir",
        "check.json": "diagnostics",
        "schema.json": "ir_json_schema",
        "behavior.json": "behavior_cases",
        "malformed.json": "malformed_probes",
        "episode.json": "episode",
    }
    artifacts = manifest["artifacts"]
    require(
        isinstance(artifacts, dict)
        and set(required) <= set(artifacts)
        and len(artifacts) <= 64,
        "package_members",
    )
    files = {}
    for name, row in artifacts.items():
        require(
            isinstance(name, str) and "/" not in name and not name.startswith("."),
            "package_member_path",
        )
        closed(
            row,
            {"kind", "sha256", "bytes"}
            | ({"format", "profile"} if row.get("kind") == "render" else set()),
        )
        if name in required:
            equal(row["kind"], required[name])
        raw = s.read(sibling(package_path, name), row["sha256"])
        equal(len(raw), row["bytes"])
        files[name] = raw
    require("render.text.txt" in files, "missing_text_render")
    behavior = decode(files["behavior.json"])
    equal(behavior["schema_version"], "misegraph-behavior-cases-v1")
    cases = behavior["cases"]
    require(isinstance(cases, list) and 0 < len(cases) <= 64, "behavior_cases")
    by_id = {}
    for case in cases:
        require(case["id"] not in by_id, "duplicate_case")
        by_id[case["id"]] = case
        equal(case["input_sha256"], artifacts["source.mise"]["sha256"])
        equal(
            artifacts[case["output_artifact"]]["sha256"],
            case["output_sha256"],
            "case_output_hash",
        )
    binding_path, binding = s.expected("import_binding")
    closed(
        binding,
        {
            "schema_version",
            "package",
            "validation",
            "emitted",
            "example_cases",
            "non_authority",
        },
    )
    equal(binding["schema_version"], "dspx-misegraph-evidence-binding-v1")
    equal(
        binding["package"],
        {
            "dir": str(PurePosixPath(package_path).parent),
            "manifest_sha256": s.hash(package_path),
            "package_sha256": manifest["package_sha256"],
            "producer": manifest["producer"],
        },
    )
    equal(
        binding["validation"],
        {
            "artifact_hashes_ok": True,
            "canonical_ir_schema_valid": True,
            "unknown_manifest_keys": [],
            "freshness": {
                "mode": "hash_bound",
                "check": "manifest_sha256_matches_at_import",
            },
        },
    )
    equal(
        binding["non_authority"],
        {"misegraph_mutated": False, "acceptance_authority": False},
    )
    ipath, imported = s.expected("imported_intent")
    upath, inputs = s.expected("imported_inputs")
    equal(
        binding["emitted"],
        {
            "intent_path": ipath,
            "intent_sha256": s.hash(ipath),
            "inputs_path": upath,
            "inputs_sha256": s.hash(upath),
        },
    )
    normalized = intent(imported)
    selected = binding["example_cases"]
    require(
        isinstance(selected, list) and selected and len(set(selected)) == len(selected),
        "selected_cases",
    )
    equal(len(normalized["examples"]), len(selected))
    for case_id, example in zip(selected, normalized["examples"], strict=True):
        require(case_id in by_id, "unknown_case")
        case = by_id[case_id]
        evidence = {
            "recipe": manifest["recipe"],
            "package_sha256": manifest["package_sha256"],
            "source": {
                "sha256": artifacts["source.mise"]["sha256"],
                "text": files["source.mise"].decode("utf-8"),
            },
            "canonical": {
                "sha256": artifacts["canonical.json"]["sha256"],
                "json": decode(files["canonical.json"]),
            },
            "render": {
                "sha256": artifacts["render.text.txt"]["sha256"],
                "text": files["render.text.txt"].decode("utf-8"),
            },
            "check": {
                "sha256": artifacts["check.json"]["sha256"],
                "diagnostics": decode(files["check.json"])["diagnostics"],
            },
            "case": {k: case[k] for k in ("id", "argv", "exit_code")},
        }
        closed(example, {"inputs", "outputs"})
        equal(
            example["inputs"],
            {"evidence": canonical(evidence).decode()},
            "package_intent_splice",
        )
    equal(
        inputs, {"inputs": normalized["examples"][0]["inputs"]}, "import_inputs_splice"
    )
    _, provenance = s.expected("import_provenance")
    equal(provenance["binding"], {"path": binding_path, "sha256": s.hash(binding_path)})
    equal(provenance["package_sha256"], manifest["package_sha256"])
    equal(provenance["manifest_sha256"], s.hash(package_path))
    equal(provenance["example_cases"], selected)
    answers = provenance["answers"]
    closed(
        answers,
        {"schema_version", "path", "sha256"}
        | ({"origin"} if "origin" in answers else set()),
    )
    # Older imported v1 retained a typed answers file without an origin field.
    answer_origin = answers.get("origin", "operator")
    if answer_origin == "operator":
        equal(answers["schema_version"], "dspx-misegraph-example-answers-v1")
        authored = s.json(answers["path"], answers["sha256"])
        closed(authored, {"schema_version", "answers"})
        equal(authored["schema_version"], answers["schema_version"])
        for case_id, example in zip(selected, normalized["examples"], strict=True):
            equal(example["outputs"]["answer"], authored["answers"][case_id])
    elif answer_origin == "package_derived":
        equal(
            answers,
            {
                "origin": "package_derived",
                "schema_version": None,
                "path": None,
                "sha256": None,
            },
        )
        projection = provenance["expected_projection"]
        equal(
            projection["required_concept_groups"],
            normalized["quality_criteria"][0]["required_concept_groups"],
        )
        for case_id, example in zip(selected, normalized["examples"], strict=True):
            equal(
                digest(example["outputs"]["answer"].encode()),
                projection["projection_sha256_by_case"][case_id],
            )
    else:
        raise Rejected("answers_origin_unsupported", "unsupported")
    return normalized, inputs


def quality_binding(s: Snapshot, path: str, imported: dict) -> tuple[dict, str]:
    q = s.json(path)
    closed(
        q,
        {
            "schema_version",
            "status",
            "intent",
            "conversation",
            "proposal",
            "candidate_intent",
            "model_role",
            "model_execution",
            "effect",
            "non_authority",
            "identity",
            "decision",
        },
    )
    equal(q["schema_version"], "program-quality-criteria-proposal-v1")
    equal(q["status"], "accepted_for_program_generation")
    candidate = intent(q["candidate_intent"])
    equal(candidate, imported, "accepted_import_intent_mismatch")
    equal(q["candidate_intent"], candidate)
    equal(q["proposal"]["metric"], candidate["metric"])
    equal(q["proposal"]["quality_criteria"], candidate["quality_criteria"])
    provenance = candidate["options"]["quality_proposal"]
    require(provenance["accepted"] is True, "missing_accepted_flag")
    equal(provenance["intent_sha256"], q["intent"]["text_sha256"])
    equal(q["model_role"]["model"], "codex/gpt-5.6-sol")
    equal(q["model_role"]["reasoning_effort"], "high")
    equal(q["model_execution"]["status"], "completed")
    equal(
        q["effect"],
        {
            "model_call_performed": True,
            "program_generated": False,
            "candidate_transitioned": False,
            "external_authority_mutated": False,
        },
    )
    equal(
        q["non_authority"],
        {
            "model_proposal_is_decision": False,
            "proposal_is_promotion": False,
            "proposal_is_activation": False,
        },
    )
    identity = {
        "intent_sha256": sha(q["intent"]["text_sha256"]),
        "proposal_sha256": digest(canonical(q["proposal"])),
        "candidate_intent_sha256": digest(canonical(candidate)),
        "model_response_sha256": sha(q["model_execution"]["response_sha256"]),
        "envelope_sha256": digest(
            canonical({k: v for k, v in q.items() if k != "identity"})
        ),
    }
    equal(q["identity"], identity, "quality_identity")
    pending = copy.deepcopy(q)
    pending.pop("identity")
    pending.pop("decision")
    pending["status"] = "proposed_pending_acceptance"
    pending["candidate_intent"]["options"]["quality_proposal"]["accepted"] = False
    pending_hash = digest(canonical(pending))
    equal(
        q["decision"],
        {
            "outcome": "accept",
            "local_generation_consent": True,
            "source_envelope_sha256": pending_hash,
            "program_generated": False,
            "external_authority_mutated": False,
        },
        "quality_decision_identity",
    )
    binding = {
        "accepted": True,
        "quality_proposal_schema": q["schema_version"],
        "quality_proposal_path": path,
        "quality_proposal_sha256": s.hash(path),
        "proposal_envelope_sha256": identity["envelope_sha256"],
        "candidate_intent_sha256": identity["candidate_intent_sha256"],
        "decision_source_envelope_sha256": pending_hash,
        "source_intent_sha256": identity["intent_sha256"],
        "program_intent_sha256": intent_hash(candidate),
        "quality_criterion_count": len(candidate["quality_criteria"]),
    }
    origin = (
        "injected_test_double"
        if q["model_execution"].get("execution_mode") == "injected_test_double"
        else "provider_claim_only"
    )
    return binding, origin
