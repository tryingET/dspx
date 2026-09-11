from __future__ import annotations

import hashlib
import importlib.metadata
import ipaddress
import json
import os
import re
import stat
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=12000)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Check = Literal["passed", "failed", "not_checked"]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Evidence(Closed):
    locator: Text
    quote: Text
    quotation_status: Literal["exact"]


class Claim(Closed):
    text: Text
    evidence: Annotated[list[Evidence], Field(min_length=1, max_length=12)]
    uncertainty: Text


class Explication(Closed):
    main_point: Claim
    elaboration: Claim
    generated_example: Text
    generated_analogy: Text


class Analysis(Closed):
    purpose_in_source: Claim
    question: Claim
    information: Claim
    concepts: Claim
    assumptions: Claim
    inferences: Claim
    implications: Claim
    point_of_view: Claim


class Evaluation(Closed):
    clarity: Claim
    accuracy: Claim
    precision: Claim
    relevance: Claim
    depth: Claim
    breadth: Claim
    logic: Claim
    significance: Claim
    fairness: Claim


class AuthorPerspective(Closed):
    simulation: Literal["simulated_author_perspective_not_testimony"]
    question: Text
    answer: Claim


class Transfer(Closed):
    attribution: Literal["added_L6_not_Paul_Elder"]
    proposed_use: Text
    source_basis: Claim
    limits: Text
    counterexample: Text
    observable_test: Text
    uncertainty: Text
    canonical_apply_allowed: Literal[False]


class ReadingOutput(Closed):
    schema_version: Literal["reading-pilot-output-v1"]
    passage_context: Claim
    purpose_guided_question: Text
    L1_paraphrase: Claim
    L2_explication: Explication
    L3_analysis: Analysis
    L4_evaluation: Evaluation
    L5_author_perspective: AuthorPerspective
    L6_added_transfer: Transfer
    source_qualifiers: Annotated[list[Claim], Field(min_length=1, max_length=12)]
    counterevidence_or_absence: Claim
    passage_synthesis: Claim
    whole_book_supported: Literal[False]


RUBRIC = {
    "L1": "Faithful paraphrase preserves source qualifiers, not reader-shaped meaning.",
    "L2": "Main point, elaboration, explicitly generated example and analogy.",
    "L3": "Author purpose/question/information/concepts/assumptions/inferences/implications/viewpoint.",
    "L4": "Evidence-supported clarity/accuracy/precision/relevance/depth/breadth/logic/significance/fairness.",
    "L5": "Explicit simulated author perspective with evidence and uncertainty, not testimony.",
    "L6": "Added transfer, limits, counterexample, observable test; not original Paul/Elder numbering.",
    "fidelity": "Exact reviewed quote locators; preserve qualifiers and contrary evidence. Missing support is not invented.",
    "AB": "Same passage, distinct purposes: substantively changed questions/application, invariant source meaning. Labels alone fail.",
    "review": "Independent local human review required per level and A/B; shape/reference checks never imply quality.",
    "scope": "One passage only. Whole-book mapping, eight-family review integration and canonical acceptance unsupported.",
}


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def public_spec() -> dict:
    return {
        "schema_version": "reading-pilot-public-v1",
        "output_schema": ReadingOutput.model_json_schema(),
        "rubric": RUBRIC,
    }


def require(condition: object) -> None:
    if not condition:
        raise ValueError("reading_pilot_rejected")


def strict_json(raw: bytes) -> dict:
    def pairs(items: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    value = json.loads(
        raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False)
    )
    require(isinstance(value, dict))
    return value


class Locator(Closed):
    name: Text
    start_byte: Annotated[int, Field(ge=0)]
    end_byte: Annotated[int, Field(gt=0)]
    excerpt_sha256: Digest


class Purpose(Closed):
    id: Literal["A", "B"]
    text: Text


class Route(Closed):
    provider: Literal["openai-compatible"]
    base_url: Text
    model: Annotated[str, Field(pattern=r"^[A-Za-z0-9_./:-]{1,256}$")]
    timeout_seconds: Annotated[float, Field(gt=0, le=120)]
    worker_deadline_seconds: Annotated[float, Field(gt=0, le=180)]
    server_output_limit_bytes: Annotated[int, Field(gt=0, le=1000000)]
    server_config_sha256: Digest
    server_bound_review_ref: Text
    local_only_route_review_ref: Text

    @model_validator(mode="after")
    def validate_route(self) -> Route:
        u = urlsplit(self.base_url)
        address = ipaddress.ip_address(u.hostname or "")
        require(address.is_loopback and u.port is not None and 0 < u.port < 65536)
        require(u.path in ("", "/v1") and "%" not in self.base_url)
        host = f"[{address.compressed}]" if address.version == 6 else address.compressed
        # Exact reconstruction rejects even empty ?/#/@, padded ports and expanded IPs.
        require(self.base_url == f"http://{host}:{u.port}{u.path}")
        require(self.worker_deadline_seconds > self.timeout_seconds)
        return self


class PilotContract(Closed):
    schema_version: Literal["reading-pilot-contract-v1"]
    campaign_id: Annotated[str, Field(pattern=r"^pilot-[a-z0-9-]{1,48}$")]
    parent_identity_sha256: Digest
    source_sha256: Digest
    source_review_ref: Text
    locators: Annotated[list[Locator], Field(min_length=1, max_length=32)]
    purposes: Annotated[list[Purpose], Field(min_length=2, max_length=2)]
    public_spec_sha256: Digest
    template_sha256: Digest
    runtime_sha256: Digest
    runtime_review_ref: Text
    operator_admission_ref: Text
    budget_review_ref: Text
    max_dispatches: Literal[2]
    route: Route

    @model_validator(mode="after")
    def validate_contract(self) -> PilotContract:
        require([p.id for p in self.purposes] == ["A", "B"])
        require(self.purposes[0].text.strip() != self.purposes[1].text.strip())
        require(len({x.name for x in self.locators}) == len(self.locators))
        require(all(x.start_byte < x.end_byte for x in self.locators))
        for ref in (
            self.source_review_ref,
            self.runtime_review_ref,
            self.operator_admission_ref,
            self.budget_review_ref,
            self.route.server_bound_review_ref,
            self.route.local_only_route_review_ref,
        ):
            require(bool(ref.strip()))
        return self


@dataclass(frozen=True)
class PilotStatus:
    state: Literal[
        "prepared",
        "completed",
        "failed",
        "failed_integrity",
        "rejected",
        "effect_indeterminate",
        "latched",
    ]
    dispatches: int | None = 0
    formatting: Check = "not_checked"
    source_reference_integrity: Check = "not_checked"
    semantic_review: Literal["needed", "not_run"] = "not_run"
    candidate_sha256: str | None = None
    result_sha256: str | None = None
    independent_provider_observation_required: bool = True
    provider_effect: str | None = None
    integrity: Check = "not_checked"


def concrete(path: Path) -> None:
    require(path.is_absolute() and ".." not in path.parts)
    for part in (path, *path.parents):
        require(not part.is_symlink())


def private_parent(path: Path) -> str:
    concrete(path)
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid())
    require(stat.S_IMODE(info.st_mode) == 0o700)
    require(path not in (Path("/"), Path.home()))
    require(not any((p / ".git").exists() for p in (path, *path.parents)))
    code_root = Path(__file__).resolve().parents[2]
    require(
        path != code_root
        and code_root not in path.parents
        and path not in code_root.parents
    )
    return sha(canonical([str(path), info.st_dev, info.st_ino, info.st_uid]))


def _root(parent: Path, campaign_id: str) -> Path:
    private_parent(parent)
    require(re.fullmatch(r"pilot-[a-z0-9-]{1,48}", campaign_id))
    return parent / campaign_id


def read_private(path: Path) -> bytes:
    concrete(path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid())
    require(stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1)
    require(info.st_size <= 32000000)
    return path.read_bytes()


def write_private(path: Path, raw: bytes) -> None:
    concrete(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path: Path, payload: dict) -> None:
    write_private(path, canonical(payload))


def inventory(root: Path) -> dict[str, str]:
    concrete(root)
    require(
        stat.S_IMODE(root.stat().st_mode) == 0o700 and root.stat().st_uid == os.getuid()
    )
    files = {}
    for path in sorted(root.rglob("*")):
        concrete(path)
        if path.is_dir():
            require(
                stat.S_IMODE(path.stat().st_mode) == 0o700
                and path.stat().st_uid == os.getuid()
            )
        else:
            require(path.suffix not in (".pyc", ".pyo"))
            files[path.relative_to(root).as_posix()] = sha(read_private(path))
    require(bool(files))
    return files


def runtime_fingerprint() -> str:
    base = Path(__file__).resolve().parents[1]
    names = (
        "services/reading_pilot.py services/reading_pilot_verification.py "
        "services/reading_pilot_custody.py "
        "services/program_service.py services/program_runtime_episode.py "
        "services/program_surfaces.py templates/module_templates.py "
        "provider_registry.py openai_compatible_provider.py dspy_typed_lm.py"
    ).split()
    identities = {n: sha((base / n).read_bytes()) for n in names}
    dist = importlib.metadata.distribution("dspy")
    for name in "dspy/adapters/chat_adapter.py dspy/clients/base_lm.py dspy/predict/predict.py".split():
        identities[name] = sha(Path(str(dist.locate_file(name))).read_bytes())
    identities["python"] = sha(Path(sys.executable).read_bytes())
    identities["dspy_version"] = dist.version
    return sha(canonical(identities))


def validate_source(contract: PilotContract, source: bytes) -> None:
    require(0 < len(source) <= 100000 and sha(source) == contract.source_sha256)
    source.decode("utf-8")
    for item in contract.locators:
        require(item.end_byte <= len(source))
        excerpt = source[item.start_byte : item.end_byte]
        excerpt.decode("utf-8")
        require(sha(excerpt) == item.excerpt_sha256)


def inputs_for(contract: PilotContract, source: bytes, index: int) -> dict:
    return {
        "source_text": source.decode("utf-8"),
        "reviewed_locators_json": canonical(
            [x.model_dump() for x in contract.locators]
        ).decode(),
        "reader_purpose": contract.purposes[index].text,
    }


def check_output(raw: bytes, contract: PilotContract, source: bytes) -> tuple[str, str]:
    if len(raw) > contract.route.server_output_limit_bytes:
        return "failed", "not_checked"
    try:
        payload = strict_json(raw)
        output = ReadingOutput.model_validate(payload)
        require(canonical(payload) == canonical(output.model_dump()))
    except (ValueError, TypeError):
        return "failed", "not_checked"
    ranges = {
        r.name: source[r.start_byte : r.end_byte].decode() for r in contract.locators
    }

    def walk(value: object) -> None:
        if isinstance(value, Evidence):
            require(value.locator in ranges and value.quote in ranges[value.locator])
        elif isinstance(value, BaseModel):
            for name in type(value).model_fields:
                walk(getattr(value, name))
        elif isinstance(value, list):
            for item in value:
                walk(item)

    try:
        walk(output)
    except ValueError:
        return "passed", "failed"
    return "passed", "passed"


def verify_case(root: Path, contract: PilotContract, index: int, digest: str) -> dict:
    from dspx.services.program_runtime_episode import (
        load_validated_program_runtime_episode_bundle,
    )
    from dspx.services.reading_pilot import read_provider_observation

    observed_provider = read_provider_observation(root, contract, index, digest)
    name = contract.purposes[index].id
    source = read_private(root / "source" / "passage.txt")
    validate_source(contract, source)
    episode_root = root / name
    manifest_path = root / "candidate" / "manifest.json"
    manifest_raw = read_private(manifest_path)
    expected_inputs = inputs_for(contract, source, index)
    require(sha(canonical(expected_inputs)) == observed_provider["inputs_sha256"])
    require(
        strict_json(read_private(episode_root / "runtime_inputs.json"))
        == {"inputs": expected_inputs}
    )
    bundle = load_validated_program_runtime_episode_bundle(
        runtime_episode_path=episode_root / "runtime_episode.json",
        expected_manifest_path=manifest_path,
        expected_manifest=strict_json(manifest_raw),
        expected_manifest_sha256=sha(manifest_raw),
    )
    behavior = bundle.behavior_results
    row = behavior["examples"][0]
    require(row["index"] == 0 and row["inputs"] == expected_inputs)
    provider = behavior["provider"]
    require(sha(canonical(provider)) == observed_provider["provider_sha256"])
    require(provider["metadata"]["model"] == contract.route.model)
    transport = provider["metadata"]["runtime"]
    require(transport["base_endpoint"] == contract.route.base_url)
    require(transport["effective_timeout"] == contract.route.timeout_seconds)
    effect = observed_provider["effect"]
    formatting, references = "not_checked", "not_checked"
    if effect == "completed_success" and row["execution_status"] == "executed":
        observed = row["observed_outputs"]["reading_analysis_json"]
        require(isinstance(observed, str))
        raw = read_private(episode_root / "reading_analysis_json")
        require(raw == (observed.rstrip() + "\n").encode())
        formatting, references = check_output(raw, contract, source)
    return {
        **observed_provider,
        "integrity": "passed",
        "formatting": formatting,
        "source_reference_integrity": references,
        "episode_sha256": bundle.runtime_episode_sha256,
        "native_receipt_sha256": bundle.runtime_receipt_sha256,
        "files": inventory(episode_root),
    }


def verify_pilot(
    *,
    parent: Path,
    campaign_id: str,
    expected_contract_sha256: str,
    expected_candidate_sha256: str,
    expected_result_sha256: str,
) -> PilotStatus:
    from dspx.services.reading_pilot import _contract, _terminal

    try:
        root = _root(parent, campaign_id)
        contract = _contract(root, expected_contract_sha256)
        inventory(root)
        captured = canonical(inventory(root / "candidate"))
        require(sha(captured) == expected_candidate_sha256)
        require(read_private(root / "candidate-files.json") == captured)
        start = strict_json(read_private(root / "started.json"))
        require(start["contract_sha256"] == expected_contract_sha256)
        require(start["candidate_sha256"] == expected_candidate_sha256)
        require(start["max_dispatches"] == 2 and start["resume_allowed"] is False)
        result_raw = read_private(root / "result.json")
        require(sha(result_raw) == expected_result_sha256)
        result = strict_json(result_raw)
        require(result["contract_sha256"] == expected_contract_sha256)
        require(result["candidate_sha256"] == expected_candidate_sha256)
        require(result["state"] == "completed" and len(result["cases"]) == 2)
        for index, expected in enumerate(result["cases"]):
            name = contract.purposes[index].id
            require(
                strict_json(read_private(root / f"{name}.terminal.json")) == expected
            )
            digest = expected["provider_observation_sha256"]
            require(verify_case(root, contract, index, digest) == expected)
            require(expected["effect"] == "completed_success")
            require(
                expected["formatting"]
                == expected["source_reference_integrity"]
                == "passed"
            )
        status = _terminal(
            root,
            "completed",
            expected_contract_sha256,
            expected_candidate_sha256,
            result["cases"],
            persist=False,
        )
        return replace(status, result_sha256=expected_result_sha256)
    except Exception:
        return PilotStatus("rejected")
