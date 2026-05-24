from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import make_key
from dspx.run_receipts import RUN_RECEIPT_VERSION, load_run_receipt


_REQUIRED_FIELDS: tuple[str, ...] = (
    "receipt_version",
    "created_at",
    "run_kind",
    "provider",
    "output_path",
    "hash",
    "template_version",
    "cache_key",
    "cache_file",
    "cache_enabled",
    "replay_inputs",
)

_RUN_KIND_TO_CACHE_KIND: dict[str, str] = {
    "signature-gen": "signature",
    "signature-refine": "signature",
    "module-gen": "module",
    "program-gen": "program",
    "codegen": "codegen",
}

_REQUIRED_REPLAY_INPUTS: dict[str, tuple[str, ...]] = {
    "signature-gen": ("prompt", "template_version", "options"),
    "signature-refine": (
        "prompt",
        "template_version",
        "attempts",
        "non_interactive",
        "wrap_script",
        "feedback",
        "constraints",
    ),
    "module-gen": (
        "name",
        "description",
        "inputs",
        "outputs",
        "use_signature",
        "template_version",
    ),
    "program-gen": ("intent",),
    "codegen": ("spec", "language", "template_version", "options"),
}


_ISSUE_RECEIPT_NOT_FOUND = "receipt_not_found"
_ISSUE_RECEIPT_INVALID_JSON_OBJECT = "receipt_invalid_json_object"
_ISSUE_RECEIPT_MISSING_REQUIRED_FIELD = "receipt_missing_required_field"
_ISSUE_RECEIPT_UNSUPPORTED_VERSION = "receipt_unsupported_version"
_ISSUE_RECEIPT_UNSUPPORTED_RUN_KIND = "receipt_unsupported_run_kind"
_ISSUE_RECEIPT_INVALID_OUTPUT_PATH = "receipt_invalid_output_path"
_ISSUE_RECEIPT_INVALID_HASH = "receipt_invalid_hash"
_ISSUE_RECEIPT_INVALID_CACHE_KEY = "receipt_invalid_cache_key"
_ISSUE_RECEIPT_INVALID_CACHE_FILE = "receipt_invalid_cache_file"
_ISSUE_RECEIPT_INVALID_CACHE_ENABLED = "receipt_invalid_cache_enabled"
_ISSUE_RECEIPT_INVALID_REPLAY_INPUTS = "receipt_invalid_replay_inputs"
_ISSUE_RECEIPT_REPLAY_INPUTS_MISSING_KEYS = "receipt_replay_inputs_missing_keys"
_ISSUE_OUTPUT_MISSING = "output_missing"
_ISSUE_OUTPUT_HASH_MISMATCH = "output_hash_mismatch"
_ISSUE_CACHE_LINKAGE_BASENAME_MISMATCH = "cache_linkage_basename_mismatch"
_ISSUE_CACHE_LINKAGE_KIND_MISMATCH = "cache_linkage_kind_mismatch"
_ISSUE_CACHE_KEY_RECOMPUTE_UNSUPPORTED = "cache_key_recompute_unsupported"
_ISSUE_CACHE_KEY_MISMATCH = "cache_key_mismatch"
_ISSUE_CACHE_FILE_MISSING = "cache_file_missing"
_ISSUE_CACHE_FILE_INVALID_JSON_OBJECT = "cache_file_invalid_json_object"
_ISSUE_CACHE_CODE_MISSING = "cache_code_missing"
_ISSUE_CACHE_CODE_HASH_MISMATCH = "cache_code_hash_mismatch"
_ISSUE_PROGRAM_MANIFEST_INVALID_JSON_OBJECT = "program_manifest_invalid_json_object"
_ISSUE_PROGRAM_EVIDENCE_ARTIFACT_MISSING = "program_evidence_artifact_missing"
_ISSUE_PROGRAM_EVIDENCE_HASH_MISMATCH = "program_evidence_hash_mismatch"
_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH = "program_evidence_declaration_mismatch"


ValidationIssue = tuple[str, str]


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _infer_output_path_from_meta(meta_path: Path) -> Path | None:
    suffix = ".meta.json"
    name = meta_path.name
    if name.endswith(suffix):
        return meta_path.parent / name[: -len(suffix)]
    return None


def _resolve_path(
    raw_path: str,
    *,
    meta_path: Path,
    output_hint: bool = False,
    allow_external_absolute: bool = False,
) -> Path:
    """Resolve a receipt-supplied path, confining it under the meta_path root."""
    from dspx.security import confine_path

    root = meta_path.parent.resolve()
    p = Path(raw_path).expanduser()
    if p.is_absolute() and allow_external_absolute:
        return p.resolve()

    candidates: list[Path] = [confine_path(root, p)]

    if output_hint:
        inferred = _infer_output_path_from_meta(meta_path)
        if inferred is not None:
            confined_inferred = confine_path(root, inferred)
            if confined_inferred not in candidates:
                candidates.append(confined_inferred)

    for cand in candidates:
        if cand.exists():
            return cand

    # Stable fallback for diagnostics: prefer the receipt-relative interpretation.
    return candidates[0]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def _nested_dict(root: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = root
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key)
    return dict(current) if isinstance(current, Mapping) else {}


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _add_error(
    report: dict[str, Any],
    *,
    code: str,
    message: str,
    check: str | None = None,
) -> None:
    errors = report.get("errors")
    if not isinstance(errors, list):
        errors = []
        report["errors"] = errors
    errors.append(message)

    error_codes = report.get("error_codes")
    if not isinstance(error_codes, list):
        error_codes = []
        report["error_codes"] = error_codes
    if code not in error_codes:
        error_codes.append(code)

    error_details = report.get("error_details")
    if not isinstance(error_details, list):
        error_details = []
        report["error_details"] = error_details
    detail: dict[str, str] = {"code": code, "message": message}
    if check is not None:
        detail["check"] = check
    error_details.append(detail)


def _validate_receipt(receipt: Mapping[str, Any]) -> list[ValidationIssue]:
    errors: list[ValidationIssue] = []

    for key in _REQUIRED_FIELDS:
        if key not in receipt:
            errors.append(
                (
                    _ISSUE_RECEIPT_MISSING_REQUIRED_FIELD,
                    f"missing required field: {key}",
                )
            )

    if errors:
        return errors

    if str(receipt.get("receipt_version") or "") != RUN_RECEIPT_VERSION:
        errors.append(
            (
                _ISSUE_RECEIPT_UNSUPPORTED_VERSION,
                f"unsupported receipt_version: {receipt.get('receipt_version')!r}",
            )
        )

    run_kind = str(receipt.get("run_kind") or "")
    if run_kind not in _RUN_KIND_TO_CACHE_KIND:
        errors.append(
            (_ISSUE_RECEIPT_UNSUPPORTED_RUN_KIND, f"unsupported run_kind: {run_kind!r}")
        )

    if (
        not isinstance(receipt.get("output_path"), str)
        or not str(receipt.get("output_path")).strip()
    ):
        errors.append(
            (
                _ISSUE_RECEIPT_INVALID_OUTPUT_PATH,
                "field output_path must be a non-empty string",
            )
        )

    if not isinstance(receipt.get("hash"), str) or not str(receipt.get("hash")).strip():
        errors.append(
            (_ISSUE_RECEIPT_INVALID_HASH, "field hash must be a non-empty string")
        )

    if (
        not isinstance(receipt.get("cache_key"), str)
        or not str(receipt.get("cache_key")).strip()
    ):
        errors.append(
            (
                _ISSUE_RECEIPT_INVALID_CACHE_KEY,
                "field cache_key must be a non-empty string",
            )
        )

    if (
        not isinstance(receipt.get("cache_file"), str)
        or not str(receipt.get("cache_file")).strip()
    ):
        errors.append(
            (
                _ISSUE_RECEIPT_INVALID_CACHE_FILE,
                "field cache_file must be a non-empty string",
            )
        )

    if not isinstance(receipt.get("cache_enabled"), bool):
        errors.append(
            (_ISSUE_RECEIPT_INVALID_CACHE_ENABLED, "field cache_enabled must be bool")
        )

    replay_inputs = receipt.get("replay_inputs")
    if not isinstance(replay_inputs, Mapping):
        errors.append(
            (
                _ISSUE_RECEIPT_INVALID_REPLAY_INPUTS,
                "field replay_inputs must be an object",
            )
        )
    else:
        required_inputs = _REQUIRED_REPLAY_INPUTS.get(run_kind, ())
        missing_inputs = [k for k in required_inputs if k not in replay_inputs]
        if missing_inputs:
            errors.append(
                (
                    _ISSUE_RECEIPT_REPLAY_INPUTS_MISSING_KEYS,
                    "replay_inputs missing required keys: "
                    + ", ".join(sorted(missing_inputs)),
                )
            )

    return errors


def _program_evidence_declarations(
    *, manifest: Mapping[str, Any], receipt: Mapping[str, Any]
) -> list[dict[str, Any]]:
    declarations_by_kind: dict[str, list[dict[str, str]]] = {}

    def add(kind: str, *, path: object, content_hash: object, source: str) -> None:
        path_text = _optional_str(path)
        hash_text = _optional_str(content_hash)
        if path_text is None or hash_text is None:
            return
        declarations_by_kind.setdefault(kind, []).append(
            {
                "source": source,
                "path": path_text,
                "content_hash": hash_text,
            }
        )

    execution_episode_artifact = _nested_dict(manifest, "execution_episode_artifact")
    add(
        "execution_episode",
        path=execution_episode_artifact.get("path"),
        content_hash=execution_episode_artifact.get("content_hash"),
        source="manifest.execution_episode_artifact",
    )
    dataset_manifest_artifact = _nested_dict(manifest, "dataset_manifest_artifact")
    add(
        "dataset_manifest",
        path=dataset_manifest_artifact.get("path"),
        content_hash=dataset_manifest_artifact.get("content_hash"),
        source="manifest.dataset_manifest_artifact",
    )
    dataset_split_evidence = _nested_dict(manifest, "dataset_split_evidence")
    split_artifacts = _nested_dict(dataset_split_evidence, "split_artifacts")
    for split in ("train", "validation", "test"):
        split_payload = _as_dict(split_artifacts.get(split))
        add(
            f"dataset_split_{split}",
            path=split_payload.get("split_path"),
            content_hash=split_payload.get("split_hash"),
            source=f"manifest.dataset_split_evidence.{split}.split_hash",
        )
        add(
            f"dataset_split_harness_{split}",
            path=split_payload.get("eval_harness"),
            content_hash=split_payload.get("eval_harness_hash"),
            source=f"manifest.dataset_split_evidence.{split}.eval_harness_hash",
        )
        add(
            f"dataset_split_behavior_results_{split}",
            path=split_payload.get("behavior_results_path"),
            content_hash=split_payload.get("behavior_results_hash"),
            source=f"manifest.dataset_split_evidence.{split}.behavior_results_hash",
        )

    execution_episode = _nested_dict(manifest, "execution_episode")
    behavior_results = _nested_dict(execution_episode, "behavior_results")
    add(
        "behavior_results",
        path=behavior_results.get("path"),
        content_hash=behavior_results.get("content_hash"),
        source="manifest.execution_episode.behavior_results",
    )
    oracle_evidence = _nested_dict(execution_episode, "oracle_evidence")
    add(
        "oracle_evidence",
        path=oracle_evidence.get("path"),
        content_hash=oracle_evidence.get("content_hash"),
        source="manifest.execution_episode.oracle_evidence",
    )

    candidate_assembly = _nested_dict(manifest, "candidate_assembly")
    for raw_surface in _as_list(candidate_assembly.get("surfaces")):
        if not isinstance(raw_surface, Mapping):
            continue
        surface = dict(raw_surface)
        kind = str(surface.get("kind") or "")
        if kind not in {
            "module_surfaces",
            "capability_registry",
            "generated_module_policy",
            "intent_normalization",
            "execution_episode",
            "behavior_results",
            "oracle_evidence",
            "dataset_manifest",
            "dataset_split_train",
            "dataset_split_validation",
            "dataset_split_test",
            "dataset_split_harness_train",
            "dataset_split_harness_validation",
            "dataset_split_harness_test",
            "dataset_split_behavior_results_train",
            "dataset_split_behavior_results_validation",
            "dataset_split_behavior_results_test",
        }:
            continue
        add(
            kind,
            path=surface.get("path"),
            content_hash=surface.get("content_hash"),
            source=f"manifest.candidate_assembly.surfaces.{kind}",
        )

    evidence = _nested_dict(manifest, "receipt_bundle", "evidence")
    add(
        "module_surfaces",
        path=evidence.get("module_surfaces_path") or "module_surfaces.json",
        content_hash=evidence.get("module_surfaces_hash"),
        source="manifest.receipt_bundle.evidence.module_surfaces_hash",
    )
    add(
        "capability_registry",
        path=evidence.get("capability_registry_path")
        or "program_capability_registry.json",
        content_hash=evidence.get("capability_registry_hash"),
        source="manifest.receipt_bundle.evidence.capability_registry_hash",
    )
    add(
        "generated_module_policy",
        path=evidence.get("generated_module_policy_path")
        or "generated_module_policy.json",
        content_hash=evidence.get("generated_module_policy_hash"),
        source="manifest.receipt_bundle.evidence.generated_module_policy_hash",
    )
    add(
        "intent_normalization",
        path=evidence.get("intent_normalization_path") or "intent_normalization.json",
        content_hash=evidence.get("intent_normalization_hash"),
        source="manifest.receipt_bundle.evidence.intent_normalization_hash",
    )
    add(
        "execution_episode",
        path=evidence.get("execution_episode_path") or "execution_episode.json",
        content_hash=evidence.get("execution_episode_hash"),
        source="manifest.receipt_bundle.evidence.execution_episode_hash",
    )
    add(
        "behavior_results",
        path="behavior_results.json",
        content_hash=evidence.get("behavior_results_hash"),
        source="manifest.receipt_bundle.evidence.behavior_results_hash",
    )
    add(
        "oracle_evidence",
        path=evidence.get("oracle_evidence_path") or "oracle_evidence.json",
        content_hash=evidence.get("oracle_evidence_hash"),
        source="manifest.receipt_bundle.evidence.oracle_evidence_hash",
    )
    add(
        "dataset_manifest",
        path="dataset_manifest.json",
        content_hash=evidence.get("dataset_manifest_hash"),
        source="manifest.receipt_bundle.evidence.dataset_manifest_hash",
    )
    receipt_dataset = _nested_dict(evidence, "dataset")
    receipt_split_artifacts = _nested_dict(receipt_dataset, "split_artifacts")
    for split in ("train", "validation", "test"):
        split_payload = _as_dict(receipt_split_artifacts.get(split))
        add(
            f"dataset_split_{split}",
            path=split_payload.get("split_path"),
            content_hash=split_payload.get("split_hash"),
            source=f"manifest.receipt_bundle.evidence.dataset.{split}.split_hash",
        )
        add(
            f"dataset_split_harness_{split}",
            path=split_payload.get("eval_harness"),
            content_hash=split_payload.get("eval_harness_hash"),
            source=f"manifest.receipt_bundle.evidence.dataset.{split}.eval_harness_hash",
        )
        add(
            f"dataset_split_behavior_results_{split}",
            path=split_payload.get("behavior_results_path"),
            content_hash=split_payload.get("behavior_results_hash"),
            source=f"manifest.receipt_bundle.evidence.dataset.{split}.behavior_results_hash",
        )

    surface_hashes = _nested_dict(
        manifest, "receipt_bundle", "evidence", "surface_hashes"
    )
    add(
        "module_surfaces",
        path="module_surfaces.json",
        content_hash=surface_hashes.get("module_surfaces.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.module_surfaces.json",
    )
    add(
        "capability_registry",
        path="program_capability_registry.json",
        content_hash=surface_hashes.get("program_capability_registry.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.program_capability_registry.json",
    )
    add(
        "generated_module_policy",
        path="generated_module_policy.json",
        content_hash=surface_hashes.get("generated_module_policy.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.generated_module_policy.json",
    )
    add(
        "intent_normalization",
        path="intent_normalization.json",
        content_hash=surface_hashes.get("intent_normalization.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.intent_normalization.json",
    )
    add(
        "execution_episode",
        path="execution_episode.json",
        content_hash=surface_hashes.get("execution_episode.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.execution_episode.json",
    )
    add(
        "behavior_results",
        path="behavior_results.json",
        content_hash=surface_hashes.get("behavior_results.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.behavior_results.json",
    )
    add(
        "oracle_evidence",
        path="oracle_evidence.json",
        content_hash=surface_hashes.get("oracle_evidence.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.oracle_evidence.json",
    )
    add(
        "dataset_manifest",
        path="dataset_manifest.json",
        content_hash=surface_hashes.get("dataset_manifest.json"),
        source="manifest.receipt_bundle.evidence.surface_hashes.dataset_manifest.json",
    )
    for split in ("train", "validation", "test"):
        add(
            f"dataset_split_{split}",
            path=f"splits/{split}.jsonl",
            content_hash=surface_hashes.get(f"splits/{split}.jsonl"),
            source=(
                f"manifest.receipt_bundle.evidence.surface_hashes.splits/{split}.jsonl"
            ),
        )
        add(
            f"dataset_split_harness_{split}",
            path=f"eval_{split}.py",
            content_hash=surface_hashes.get(f"eval_{split}.py"),
            source=(f"manifest.receipt_bundle.evidence.surface_hashes.eval_{split}.py"),
        )
        add(
            f"dataset_split_behavior_results_{split}",
            path=f"behavior_results.{split}.json",
            content_hash=surface_hashes.get(f"behavior_results.{split}.json"),
            source=(
                "manifest.receipt_bundle.evidence.surface_hashes."
                f"behavior_results.{split}.json"
            ),
        )

    run_summary = _as_dict(receipt.get("run_summary"))
    add(
        "module_surfaces",
        path=run_summary.get("module_surfaces_path") or "module_surfaces.json",
        content_hash=run_summary.get("module_surfaces_hash"),
        source="receipt.run_summary.module_surfaces_hash",
    )
    add(
        "capability_registry",
        path=run_summary.get("capability_registry_path")
        or "program_capability_registry.json",
        content_hash=run_summary.get("capability_registry_hash"),
        source="receipt.run_summary.capability_registry_hash",
    )
    add(
        "generated_module_policy",
        path=run_summary.get("generated_module_policy_path")
        or "generated_module_policy.json",
        content_hash=run_summary.get("generated_module_policy_hash"),
        source="receipt.run_summary.generated_module_policy_hash",
    )
    add(
        "intent_normalization",
        path=run_summary.get("intent_normalization_path")
        or "intent_normalization.json",
        content_hash=run_summary.get("intent_normalization_hash"),
        source="receipt.run_summary.intent_normalization_hash",
    )
    add(
        "execution_episode",
        path=run_summary.get("execution_episode_path") or "execution_episode.json",
        content_hash=run_summary.get("execution_episode_hash"),
        source="receipt.run_summary.execution_episode_hash",
    )
    add(
        "behavior_results",
        path="behavior_results.json",
        content_hash=run_summary.get("behavior_results_hash"),
        source="receipt.run_summary.behavior_results_hash",
    )
    add(
        "oracle_evidence",
        path="oracle_evidence.json",
        content_hash=run_summary.get("oracle_evidence_hash"),
        source="receipt.run_summary.oracle_evidence_hash",
    )
    add(
        "dataset_manifest",
        path=run_summary.get("dataset_manifest_path") or "dataset_manifest.json",
        content_hash=run_summary.get("dataset_manifest_hash"),
        source="receipt.run_summary.dataset_manifest_hash",
    )
    summary_dataset = _nested_dict(run_summary, "dataset_split_evidence")
    summary_split_artifacts = _nested_dict(summary_dataset, "split_artifacts")
    for split in ("train", "validation", "test"):
        split_payload = _as_dict(summary_split_artifacts.get(split))
        add(
            f"dataset_split_{split}",
            path=split_payload.get("split_path"),
            content_hash=split_payload.get("split_hash"),
            source=f"receipt.run_summary.dataset_split_evidence.{split}.split_hash",
        )
        add(
            f"dataset_split_harness_{split}",
            path=split_payload.get("eval_harness"),
            content_hash=split_payload.get("eval_harness_hash"),
            source=f"receipt.run_summary.dataset_split_evidence.{split}.eval_harness_hash",
        )
        add(
            f"dataset_split_behavior_results_{split}",
            path=split_payload.get("behavior_results_path"),
            content_hash=split_payload.get("behavior_results_hash"),
            source=(
                "receipt.run_summary.dataset_split_evidence."
                f"{split}.behavior_results_hash"
            ),
        )

    grouped: list[dict[str, Any]] = []
    for kind in sorted(declarations_by_kind):
        declarations = declarations_by_kind[kind]
        grouped.append(
            {
                "kind": kind,
                "path": declarations[0]["path"],
                "content_hash": declarations[0]["content_hash"],
                "declarations": declarations,
            }
        )
    return grouped


def _check_program_evidence_artifacts(
    *,
    report: dict[str, Any],
    meta_path: Path,
    output_path: Path,
    receipt: Mapping[str, Any],
) -> None:
    if str(receipt.get("run_kind") or "") != "program-gen":
        return

    checks: dict[str, bool] = report["checks"]
    manifest = _load_json_object(output_path)
    checks["program_manifest_json_object"] = manifest is not None
    if manifest is None:
        _add_error(
            report,
            code=_ISSUE_PROGRAM_MANIFEST_INVALID_JSON_OBJECT,
            message=f"program manifest is not a JSON object: {output_path}",
            check="program_manifest_json_object",
        )
        return

    declarations = _program_evidence_declarations(manifest=manifest, receipt=receipt)
    report["program_evidence_artifacts"] = declarations
    if not declarations:
        checks["program_evidence_artifacts_declared"] = False
        return
    checks["program_evidence_artifacts_declared"] = True

    for declaration in declarations:
        kind = declaration["kind"]
        artifact_path = _resolve_path(str(declaration["path"]), meta_path=meta_path)
        expected_hash = str(declaration["content_hash"])
        source_declarations = [
            item
            for item in _as_list(declaration.get("declarations"))
            if isinstance(item, Mapping)
        ]
        declared_paths = {
            str(item["path"])
            for item in source_declarations
            if isinstance(item.get("path"), str)
        }
        declared_hashes = {
            str(item["content_hash"])
            for item in source_declarations
            if isinstance(item.get("content_hash"), str)
        }
        exists_check = f"program_{kind}_exists"
        hash_check = f"program_{kind}_hash_match"
        declaration_check = f"program_{kind}_declaration_consistent"
        checks[declaration_check] = (
            len(declared_paths) <= 1 and len(declared_hashes) <= 1
        )
        if not checks[declaration_check]:
            _add_error(
                report,
                code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                message=(
                    f"program evidence declaration mismatch for {kind}: "
                    f"paths={sorted(declared_paths)} hashes={sorted(declared_hashes)}"
                ),
                check=declaration_check,
            )
        artifact_exists = artifact_path.exists() and artifact_path.is_file()
        checks[exists_check] = artifact_exists
        if not artifact_exists:
            _add_error(
                report,
                code=_ISSUE_PROGRAM_EVIDENCE_ARTIFACT_MISSING,
                message=f"program evidence artifact missing: {artifact_path}",
                check=exists_check,
            )
            continue
        actual_hash = _sha256_file(artifact_path)
        report[f"program_{kind}_path"] = str(artifact_path)
        report[f"program_{kind}_hash"] = actual_hash
        checks[hash_check] = actual_hash == expected_hash
        if actual_hash != expected_hash:
            _add_error(
                report,
                code=_ISSUE_PROGRAM_EVIDENCE_HASH_MISMATCH,
                message=(
                    f"program evidence hash mismatch for {kind}: "
                    f"expected={expected_hash} actual={actual_hash}"
                ),
                check=hash_check,
            )
        if kind == "generated_module_policy":
            policy_payload = _load_json_object(artifact_path)
            semantic_check = "program_generated_module_policy_semantic_valid"
            checks[semantic_check] = (
                isinstance(policy_payload, dict)
                and policy_payload.get("schema_version")
                == "program-generated-module-policy-v1"
                and policy_payload.get("status") == "passed"
                and policy_payload.get("checked_surface") == "module.py"
            )
            if not checks[semantic_check]:
                _add_error(
                    report,
                    code=_ISSUE_PROGRAM_EVIDENCE_DECLARATION_MISMATCH,
                    message=f"program generated module policy semantic check failed: {artifact_path}",
                    check=semantic_check,
                )


def _expected_cache_payload(receipt: Mapping[str, Any]) -> dict[str, Any] | None:
    run_kind = str(receipt.get("run_kind") or "")
    replay_inputs = _as_dict(receipt.get("replay_inputs"))

    if run_kind == "signature-gen":
        class_name = replay_inputs.get("class_name")
        options = replay_inputs.get("options")
        opts = _as_dict(options)
        cls = str(class_name or "GeneratedSignature")
        return {
            "kind": "signature",
            "prompt": replay_inputs.get("prompt"),
            "template_version": replay_inputs.get("template_version"),
            "class_name": cls,
            "options": opts,
        }

    if run_kind == "signature-refine":
        return {
            "kind": "signature",
            "prompt": replay_inputs.get("prompt"),
            "template_version": replay_inputs.get("template_version"),
            "class_name": str(receipt.get("class_name") or ""),
            "mode": str(receipt.get("mode") or "refine"),
            "backend": str(receipt.get("backend") or "native"),
            "attempts": int(replay_inputs.get("attempts") or 1),
            "non_interactive": bool(replay_inputs.get("non_interactive")),
            "wrap_script": bool(replay_inputs.get("wrap_script")),
            "feedback": _as_list(replay_inputs.get("feedback")),
            "constraints": _as_list(replay_inputs.get("constraints")),
        }

    if run_kind == "module-gen":
        return {
            "kind": "module",
            "name": replay_inputs.get("name"),
            "description": replay_inputs.get("description"),
            "inputs": _as_list(replay_inputs.get("inputs")),
            "outputs": _as_list(replay_inputs.get("outputs")),
            "use_signature": bool(replay_inputs.get("use_signature")),
            "template_version": replay_inputs.get("template_version"),
        }

    if run_kind == "program-gen":
        return {
            "kind": "program",
            "intent": _as_dict(replay_inputs.get("intent")),
        }

    if run_kind == "codegen":
        return {
            "kind": "codegen",
            "spec": replay_inputs.get("spec"),
            "language": replay_inputs.get("language"),
            "template_version": replay_inputs.get("template_version"),
            "options": _as_dict(replay_inputs.get("options")),
        }

    return None


def check_run_receipt(meta_path: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "ok",
        "receipt_path": str(meta_path),
        "checks": {},
        "errors": [],
        "warnings": [],
        "error_codes": [],
        "error_details": [],
    }

    if not meta_path.exists() or not meta_path.is_file():
        report["status"] = "invalid"
        _add_error(
            report,
            code=_ISSUE_RECEIPT_NOT_FOUND,
            message=f"receipt not found: {meta_path}",
        )
        return report

    receipt = load_run_receipt(meta_path)
    if receipt is None:
        report["status"] = "invalid"
        _add_error(
            report,
            code=_ISSUE_RECEIPT_INVALID_JSON_OBJECT,
            message="receipt is not valid JSON object",
        )
        return report

    report["receipt_version"] = receipt.get("receipt_version")
    report["run_kind"] = receipt.get("run_kind")

    validation_errors = _validate_receipt(receipt)
    if validation_errors:
        report["status"] = "invalid"
        for code, message in validation_errors:
            _add_error(report, code=code, message=message)
        return report

    receipt_hash = str(receipt.get("hash") or "")
    try:
        output_path = _resolve_path(
            str(receipt.get("output_path") or ""),
            meta_path=meta_path,
            output_hint=True,
        )
    except ValueError as exc:
        report["status"] = "invalid"
        _add_error(
            report,
            code=_ISSUE_RECEIPT_INVALID_OUTPUT_PATH,
            message=str(exc),
        )
        return report
    report["output_path"] = str(output_path)
    report["receipt_hash"] = receipt_hash

    checks: dict[str, bool] = report["checks"]

    output_exists = output_path.exists() and output_path.is_file()
    checks["output_exists"] = bool(output_exists)
    if not output_exists:
        _add_error(
            report,
            code=_ISSUE_OUTPUT_MISSING,
            message=f"output artifact missing: {output_path}",
            check="output_exists",
        )
    else:
        actual_hash = _sha256_file(output_path)
        report["actual_output_hash"] = actual_hash
        checks["output_hash_match"] = actual_hash == receipt_hash
        if actual_hash != receipt_hash:
            _add_error(
                report,
                code=_ISSUE_OUTPUT_HASH_MISMATCH,
                message=f"output hash mismatch: expected={receipt_hash} actual={actual_hash}",
                check="output_hash_match",
            )
        _check_program_evidence_artifacts(
            report=report,
            meta_path=meta_path,
            output_path=output_path,
            receipt=receipt,
        )

    cache_key = str(receipt.get("cache_key") or "")
    try:
        cache_file = _resolve_path(
            str(receipt.get("cache_file") or ""),
            meta_path=meta_path,
            allow_external_absolute=True,
        )
    except ValueError as exc:
        report["status"] = "invalid"
        _add_error(
            report,
            code=_ISSUE_RECEIPT_INVALID_CACHE_FILE,
            message=str(exc),
        )
        return report
    cache_enabled = bool(receipt.get("cache_enabled"))
    run_kind = str(receipt.get("run_kind") or "")
    cache_kind = _RUN_KIND_TO_CACHE_KIND.get(run_kind) or ""

    report["cache_key"] = cache_key
    report["cache_file"] = str(cache_file)
    report["cache_enabled"] = cache_enabled

    checks["cache_file_matches_key"] = cache_file.name == f"{cache_key}.json"
    if not checks["cache_file_matches_key"]:
        _add_error(
            report,
            code=_ISSUE_CACHE_LINKAGE_BASENAME_MISMATCH,
            message="cache linkage mismatch: cache_file basename does not match cache_key",
            check="cache_file_matches_key",
        )

    checks["cache_kind_matches_run_kind"] = cache_file.parent.name == cache_kind
    if not checks["cache_kind_matches_run_kind"]:
        _add_error(
            report,
            code=_ISSUE_CACHE_LINKAGE_KIND_MISMATCH,
            message="cache linkage mismatch: cache_file parent kind does not match run_kind",
            check="cache_kind_matches_run_kind",
        )

    expected_payload = _expected_cache_payload(receipt)
    if expected_payload is None:
        checks["cache_key_recomputes"] = False
        _add_error(
            report,
            code=_ISSUE_CACHE_KEY_RECOMPUTE_UNSUPPORTED,
            message=f"cannot recompute cache key for run_kind={run_kind!r}; unsupported",
            check="cache_key_recomputes",
        )
    else:
        expected_key = make_key(expected_payload)
        report["expected_cache_key"] = expected_key
        checks["cache_key_recomputes"] = expected_key == cache_key
        if expected_key != cache_key:
            _add_error(
                report,
                code=_ISSUE_CACHE_KEY_MISMATCH,
                message=f"cache key mismatch: expected={expected_key} receipt={cache_key}",
                check="cache_key_recomputes",
            )

    if cache_enabled:
        cache_exists = cache_file.exists() and cache_file.is_file()
        checks["cache_file_exists"] = bool(cache_exists)
        if not cache_exists:
            _add_error(
                report,
                code=_ISSUE_CACHE_FILE_MISSING,
                message=f"cache file missing: {cache_file}",
                check="cache_file_exists",
            )
        else:
            try:
                cache_payload = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                cache_payload = None
            checks["cache_file_json_object"] = isinstance(cache_payload, dict)
            if not isinstance(cache_payload, dict):
                _add_error(
                    report,
                    code=_ISSUE_CACHE_FILE_INVALID_JSON_OBJECT,
                    message=f"cache file is not valid JSON object: {cache_file}",
                    check="cache_file_json_object",
                )
            else:
                code = cache_payload.get("code")
                checks["cache_has_code"] = isinstance(code, str)
                if not isinstance(code, str):
                    _add_error(
                        report,
                        code=_ISSUE_CACHE_CODE_MISSING,
                        message="cache provenance missing: cache payload has no string 'code'",
                        check="cache_has_code",
                    )
                else:
                    cache_code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
                    report["cache_code_hash"] = cache_code_hash
                    checks["cache_code_hash_matches_receipt"] = (
                        cache_code_hash == receipt_hash
                    )
                    if cache_code_hash != receipt_hash:
                        _add_error(
                            report,
                            code=_ISSUE_CACHE_CODE_HASH_MISMATCH,
                            message="cache provenance mismatch: cache code hash does not match receipt hash",
                            check="cache_code_hash_matches_receipt",
                        )
    else:
        checks["cache_file_exists"] = cache_file.exists() and cache_file.is_file()
        report["warnings"].append(
            "cache disabled in receipt; cache existence/provenance checks are informational"
        )

    if report["errors"]:
        report["status"] = "failed"
    return report
