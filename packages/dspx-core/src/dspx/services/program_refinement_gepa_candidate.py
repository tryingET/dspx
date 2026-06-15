from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import sha256_text
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_refinement import load_program_manifest
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.program_refinement_gepa_candidate_contracts import (
    PROGRAM_REFINEMENT_GEPA_CANDIDATE_RESULT_SCHEMA,
    ProgramRefinementGepaCandidateError,
    _candidate_root,
    _copy_optimizer_output,
    _identity_from_manifest,
    _json_text,
    _load_json_object,
    _load_ready_gepa_result,
    _preflight_paths,
    _safe_list,
    _safe_mapping,
    _sha256_file,
    _surface_path,
)


def _render_gepa_program_code(intent: Mapping[str, Any]) -> str:
    name = str(intent.get("name") or "IntentProgram")
    objective = str(intent.get("objective") or "")
    constraints = list(intent.get("constraints") or [])
    metric = str(intent.get("metric") or "unspecified")
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import json",
            "from functools import lru_cache",
            "from pathlib import Path",
            "from typing import Any",
            "",
            "import dspy",
            "",
            "from module import io_spec, normalize_output, output_weights",
            "",
            f"OBJECTIVE = {objective!r}",
            f"CONSTRAINTS = {constraints!r}",
            f"METRIC = {metric!r}",
            "PROGRAM_TEMPLATE_VERSION = 'program-candidate-assembly-v1'",
            "GEPA_OPTIMIZER_OUTPUT_DIR = 'gepa_optimizer_output'",
            "",
            "",
            "def assembly_manifest_path() -> Path:",
            "    return Path(__file__).with_name('manifest.json')",
            "",
            "",
            "def optimizer_output_path() -> Path:",
            "    return Path(__file__).with_name(GEPA_OPTIMIZER_OUTPUT_DIR)",
            "",
            "",
            "def load_manifest() -> dict[str, Any]:",
            "    path = assembly_manifest_path()",
            "    if not path.exists():",
            "        return {}",
            "    try:",
            "        payload = json.loads(path.read_text(encoding='utf-8'))",
            "    except Exception:",
            "        return {}",
            "    return dict(payload) if isinstance(payload, dict) else {}",
            "",
            "",
            "def _sha256_file(path: Path) -> str:",
            "    import hashlib",
            "",
            "    digest = hashlib.sha256()",
            "    with path.open('rb') as fh:",
            "        for chunk in iter(lambda: fh.read(1024 * 1024), b''):",
            "            digest.update(chunk)",
            "    return digest.hexdigest()",
            "",
            "",
            "def _optimizer_payload_inventory(root: Path) -> dict[str, Any]:",
            "    import hashlib",
            "",
            "    files: list[dict[str, Any]] = []",
            "    for path in sorted(root.rglob('*')):",
            "        if path.is_symlink():",
            "            raise RuntimeError(f'GEPA optimizer output contains symlink: {path}')",
            "        if not path.is_file():",
            "            continue",
            "        rel = path.relative_to(root).as_posix()",
            "        if rel == 'manifest.json':",
            "            continue",
            "        files.append({'path': rel, 'sha256': _sha256_file(path), 'size_bytes': path.stat().st_size})",
            "    tree_text = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(',', ':'))",
            "    return {",
            "        'hash_algorithm': 'sha256',",
            "        'tree_hash': hashlib.sha256(tree_text.encode('utf-8')).hexdigest(),",
            "        'files': files,",
            "    }",
            "",
            "",
            "def verify_optimizer_output() -> None:",
            "    root = optimizer_output_path()",
            "    manifest_path = root / 'manifest.json'",
            "    try:",
            "        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))",
            "    except Exception as exc:",
            "        raise RuntimeError('GEPA optimizer manifest cannot be read before load') from exc",
            "    if not isinstance(manifest, dict):",
            "        raise RuntimeError('GEPA optimizer manifest must be a JSON object before load')",
            "    candidate_manifest = load_manifest()",
            "    gepa_refinement = candidate_manifest.get('gepa_refinement')",
            "    if not isinstance(gepa_refinement, dict):",
            "        raise RuntimeError('GEPA candidate manifest is missing GEPA lineage before load')",
            "    expected_manifest_hash = str(gepa_refinement.get('gepa_optimizer_manifest_sha256') or '')",
            "    if not expected_manifest_hash:",
            "        raise RuntimeError('GEPA candidate manifest is missing optimizer manifest hash before load')",
            "    if _sha256_file(manifest_path) != expected_manifest_hash:",
            "        raise RuntimeError('GEPA optimizer manifest hash changed before load')",
            "    declared = manifest.get('output_payload')",
            "    if not isinstance(declared, dict) or declared.get('hash_algorithm') != 'sha256':",
            "        raise RuntimeError('GEPA optimizer payload inventory is missing before load')",
            "    actual = _optimizer_payload_inventory(root)",
            "    declared_files = declared.get('files')",
            "    if not isinstance(declared_files, list) or not declared_files:",
            "        raise RuntimeError('GEPA optimizer payload inventory is empty before load')",
            "    declared_by_path = {str(item.get('path')): item for item in declared_files if isinstance(item, dict)}",
            "    actual_by_path = {str(item['path']): item for item in actual['files']}",
            "    if set(declared_by_path) != set(actual_by_path):",
            "        raise RuntimeError('GEPA optimizer payload file set changed before load')",
            "    for rel, actual_item in actual_by_path.items():",
            "        declared_item = declared_by_path[rel]",
            "        if declared_item.get('sha256') != actual_item.get('sha256'):",
            "            raise RuntimeError('GEPA optimizer payload hash changed before load')",
            "        if declared_item.get('size_bytes') != actual_item.get('size_bytes'):",
            "            raise RuntimeError('GEPA optimizer payload size changed before load')",
            "    if declared.get('tree_hash') != actual.get('tree_hash'):",
            "        raise RuntimeError('GEPA optimizer payload tree hash changed before load')",
            "",
            "",
            "@lru_cache(maxsize=1)",
            "def build_program() -> dspy.Module:",
            "    verify_optimizer_output()",
            "    return dspy.load(str(optimizer_output_path()), allow_pickle=True)",
            "",
            "",
            "def build_student(*, use_cot: bool = False) -> dspy.Module:",
            "    _ = use_cot",
            "    return build_program()",
            "",
            "",
            "def run_with_observability(**inputs: object) -> dspy.Prediction:",
            "    return build_program()(**inputs)",
            "",
            "",
            "def intent_summary() -> dict[str, object]:",
            "    return {",
            f"        'name': {name!r},",
            "        'objective': OBJECTIVE,",
            "        'constraints': list(CONSTRAINTS),",
            "        'metric': METRIC,",
            "        'io': io_spec(),",
            "        'materialization_scope': {",
            "            'topology_materialized': True,",
            "            'current_renderer': 'gepa_optimizer_output_loader',",
            "        },",
            "    }",
            "",
        ]
    )


def _update_manifest_for_gepa_candidate(
    *,
    candidate_root: Path,
    source_manifest_path: Path,
    source_manifest_hash: str,
    source_identity: Mapping[str, str | None],
    gepa_result_path: Path,
    gepa_result_hash: str,
    optimizer_manifest_hash: str,
    optimizer_payload_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_path = candidate_root / "manifest.json"
    manifest = _load_json_object(manifest_path, label="GEPA candidate manifest")
    intent = _safe_mapping(manifest.get("intent"))
    program_path = candidate_root / "program.py"
    program_path.write_text(_render_gepa_program_code(intent), encoding="utf-8")
    lineage_path = candidate_root / "gepa_candidate_lineage.json"
    lineage = {
        "schema_version": "program-gepa-candidate-lineage-v1",
        "source_identity": dict(source_identity),
        "source_manifest_path": str(source_manifest_path),
        "source_manifest_sha256": source_manifest_hash,
        "gepa_refinement_result_path": str(gepa_result_path),
        "gepa_refinement_result_sha256": gepa_result_hash,
        "gepa_optimizer_manifest_sha256": optimizer_manifest_hash,
        "gepa_optimizer_payload_tree_sha256": optimizer_payload_inventory.get(
            "tree_hash"
        ),
        "gepa_optimizer_payload_file_count": len(
            optimizer_payload_inventory.get("files") or []
        ),
        "authority": "local_gepa_candidate_lineage_only_non_authoritative",
        "non_authority": {
            "automatic_promotion": False,
            "winner_selection": False,
            "external_authority_export": False,
            "governance_authority": False,
            "external_mutation": False,
        },
    }
    lineage_path.write_text(_json_text(lineage), encoding="utf-8")

    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    surfaces = [
        dict(item)
        for item in _safe_list(candidate_assembly.get("surfaces"))
        if isinstance(item, Mapping)
    ]
    surface_hashes = _safe_mapping(
        _safe_mapping(manifest.get("receipt_bundle")).get("evidence")
    ).get("surface_hashes")
    surface_hashes = dict(surface_hashes) if isinstance(surface_hashes, Mapping) else {}
    program_hash = _sha256_file(program_path)
    optimizer_manifest_rel = "gepa_optimizer_output/manifest.json"
    lineage_hash = _sha256_file(lineage_path)
    surface_hashes["program.py"] = program_hash
    surface_hashes[optimizer_manifest_rel] = optimizer_manifest_hash
    surface_hashes["gepa_candidate_lineage.json"] = lineage_hash
    for surface in surfaces:
        if surface.get("kind") == "program":
            surface["content_hash"] = program_hash
            surface["renderer"] = "gepa_optimizer_output_loader"
    surfaces.extend(
        [
            {
                "kind": "gepa_optimizer_output",
                "path": optimizer_manifest_rel,
                "generator": "program-refine materialize-gepa-candidate",
                "content_hash": optimizer_manifest_hash,
                "schema_version": "dspy-gepa-optimizer-output-manifest",
            },
            {
                "kind": "gepa_candidate_lineage",
                "path": "gepa_candidate_lineage.json",
                "generator": "program-refine materialize-gepa-candidate",
                "content_hash": lineage_hash,
                "schema_version": "program-gepa-candidate-lineage-v1",
            },
        ]
    )
    surface_kinds = list(candidate_assembly.get("surface_kinds") or [])
    for kind in ["gepa_optimizer_output", "gepa_candidate_lineage"]:
        if kind not in surface_kinds:
            surface_kinds.append(kind)
    candidate_assembly["surface_kinds"] = surface_kinds
    candidate_assembly["surfaces"] = surfaces
    assembly_hash = sha256_text(
        _json_text(
            {
                "surface_kinds": surface_kinds,
                "surfaces": [
                    {
                        "kind": surface.get("kind"),
                        "path": surface.get("path"),
                        "content_hash": surface.get("content_hash"),
                    }
                    for surface in surfaces
                ],
            }
        )
    )
    candidate_assembly["content_hash"] = assembly_hash
    candidate_assembly["materialized_from"] = "gepa_optimizer_output"
    manifest["candidate_assembly"] = candidate_assembly
    manifest["gepa_refinement"] = {
        "schema_version": "program-gepa-candidate-materialization-v1",
        "status": "materialized_local_candidate",
        "source_identity": dict(source_identity),
        "source_manifest_path": str(source_manifest_path),
        "source_manifest_sha256": source_manifest_hash,
        "gepa_refinement_result_path": str(gepa_result_path),
        "gepa_refinement_result_sha256": gepa_result_hash,
        "gepa_optimizer_manifest_sha256": optimizer_manifest_hash,
        "gepa_optimizer_payload_tree_sha256": optimizer_payload_inventory.get(
            "tree_hash"
        ),
        "gepa_optimizer_payload_file_count": len(
            optimizer_payload_inventory.get("files") or []
        ),
        "non_authority": {
            "automatic_promotion": False,
            "winner_selection": False,
            "external_authority_export": False,
            "governance_authority": False,
            "external_mutation": False,
        },
    }
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    evidence = _safe_mapping(receipt_bundle.get("evidence"))
    evidence.update(
        {
            "program_hash": program_hash,
            "assembly_hash": assembly_hash,
            "surface_hashes": surface_hashes,
            "gepa_optimizer_manifest_hash": optimizer_manifest_hash,
            "gepa_optimizer_manifest_path": optimizer_manifest_rel,
            "gepa_optimizer_payload_tree_hash": optimizer_payload_inventory.get(
                "tree_hash"
            ),
            "gepa_optimizer_payload_file_count": len(
                optimizer_payload_inventory.get("files") or []
            ),
            "gepa_candidate_lineage_hash": lineage_hash,
            "gepa_candidate_lineage_path": "gepa_candidate_lineage.json",
            "gepa_source_manifest_hash": source_manifest_hash,
            "gepa_refinement_result_hash": gepa_result_hash,
        }
    )
    receipt_bundle["evidence"] = evidence
    manifest["receipt_bundle"] = receipt_bundle
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")
    manifest_hash = _sha256_file(manifest_path)
    meta_path = candidate_root / "manifest.json.meta.json"
    if meta_path.exists():
        try:
            meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta_payload = {}
        if isinstance(meta_payload, dict):
            meta_payload["hash"] = manifest_hash
            meta_payload["output_hash"] = manifest_hash
            meta_path.write_text(_json_text(meta_payload), encoding="utf-8")
    return manifest


def materialize_gepa_refinement_candidate(
    *,
    manifest_path: Path,
    gepa_result_path: Path,
    outdir: Path,
    result_out: Path | None = None,
) -> dict[str, Any]:
    """Materialize a local candidate assembly from hash-bound GEPA optimizer output."""

    manifest_path = manifest_path.expanduser().resolve()
    gepa_result_path = gepa_result_path.expanduser().resolve()
    outdir = outdir.expanduser().resolve()
    result_out = result_out.expanduser().resolve() if result_out is not None else None
    source_manifest = load_program_manifest(manifest_path)
    source_identity = _identity_from_manifest(source_manifest)
    source_root = _candidate_root(source_manifest, manifest_path)
    source_program = _surface_path(
        source_manifest, manifest_path, kind="program", default="program.py"
    )
    if not source_program.exists():
        raise ProgramRefinementGepaCandidateError(
            f"source program.py not found: {source_program}"
        )
    source_program_hash = _sha256_file(source_program)
    source_manifest_hash = _sha256_file(manifest_path)
    gepa_result, optimizer_manifest, optimizer_root = _load_ready_gepa_result(
        gepa_result_path,
        source_identity=source_identity,
        source_program_hash=source_program_hash,
    )
    _preflight_paths(
        source_root=source_root,
        optimizer_root=optimizer_root,
        outdir=outdir,
        result_out=result_out,
    )
    if outdir.exists():
        raise ProgramRefinementGepaCandidateError(
            f"GEPA candidate output directory already exists: {outdir}"
        )
    source_intent = _safe_mapping(source_manifest.get("intent"))
    if not source_intent:
        raise ProgramRefinementGepaCandidateError("source manifest is missing intent")
    next_intent = dict(source_intent)
    constraints = [str(item) for item in next_intent.get("constraints") or []]
    marker = "load local GEPA optimizer output as the candidate program implementation"
    if marker not in constraints:
        constraints.append(marker)
    next_intent["constraints"] = constraints
    options = _safe_mapping(next_intent.get("options"))
    options["gepa_candidate_lineage"] = {
        "schema_version": "program-gepa-candidate-lineage-v1",
        "source_identity": dict(source_identity),
        "source_manifest_path": str(manifest_path),
        "gepa_refinement_result_path": str(gepa_result_path),
        "authority": "local_gepa_refinement_candidate_only_non_authoritative",
    }
    next_intent["options"] = options
    artifact_root: Path | None = None
    try:
        artifact = materialize_program_from_intent(
            ProgramIntent.model_validate(next_intent),
            outdir=outdir,
            intent_source=(
                Path(
                    str(
                        _safe_mapping(source_manifest.get("request")).get(
                            "intent_source"
                        )
                    )
                )
                .expanduser()
                .resolve()
                if isinstance(
                    _safe_mapping(source_manifest.get("request")).get("intent_source"),
                    str,
                )
                and str(
                    _safe_mapping(source_manifest.get("request")).get("intent_source")
                ).strip()
                else None
            ),
        )
        artifact_root = Path(artifact.root_path)
        optimizer_destination = artifact_root / "gepa_optimizer_output"
        optimizer_manifest_hash = str(
            _safe_mapping(gepa_result.get("gepa_output")).get("manifest_sha256")
        )
        optimizer_payload_inventory = _copy_optimizer_output(
            optimizer_root,
            optimizer_destination,
            expected_manifest_hash=optimizer_manifest_hash,
        )
        updated_manifest = _update_manifest_for_gepa_candidate(
            candidate_root=artifact_root,
            source_manifest_path=manifest_path,
            source_manifest_hash=source_manifest_hash,
            source_identity=source_identity,
            gepa_result_path=gepa_result_path,
            gepa_result_hash=_sha256_file(gepa_result_path),
            optimizer_manifest_hash=optimizer_manifest_hash,
            optimizer_payload_inventory=optimizer_payload_inventory,
        )
    except Exception:
        if artifact_root is not None:
            shutil.rmtree(artifact_root, ignore_errors=True)
        raise
    candidate_manifest_path = artifact_root / "manifest.json"
    result = {
        "schema_version": PROGRAM_REFINEMENT_GEPA_CANDIDATE_RESULT_SCHEMA,
        "status": "materialized",
        "created_from": {
            "manifest_path": str(manifest_path),
            "gepa_refinement_result_path": str(gepa_result_path),
            "gepa_optimizer_output_root": str(optimizer_root),
        },
        "source_identity": dict(source_identity),
        "gepa_output": {
            "copied_to": str(artifact_root / "gepa_optimizer_output"),
            "manifest_sha256": str(
                _safe_mapping(gepa_result.get("gepa_output")).get("manifest_sha256")
            ),
            "payload_tree_sha256": optimizer_payload_inventory.get("tree_hash"),
            "payload_file_count": len(optimizer_payload_inventory.get("files") or []),
            "source_program_sha256": source_program_hash,
            "optimizer_manifest_program_sha256": str(
                _safe_mapping(optimizer_manifest.get("program")).get("sha256")
            ),
        },
        "candidate": {
            "root_path": str(artifact_root),
            "manifest_path": str(candidate_manifest_path),
            "request_id": _safe_mapping(updated_manifest.get("request")).get(
                "request_id"
            ),
            "candidate_id": _identity_from_manifest(updated_manifest).get(
                "candidate_id"
            ),
            "assembly_id": _identity_from_manifest(updated_manifest).get("assembly_id"),
            "episode_id": _identity_from_manifest(updated_manifest).get("episode_id"),
            "receipt_bundle_id": _identity_from_manifest(updated_manifest).get(
                "receipt_bundle_id"
            ),
            "promotion_state": "not_promoted",
        },
        "effect": {
            "local_gepa_candidate_generated": True,
            "source_program_files_mutated": False,
            "source_dataset_artifacts_mutated": False,
            "gepa_optimizer_output_mutated": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
        },
        "non_authority": {
            "local_candidate_generation_only": True,
            "automatic_promotion": False,
            "oracle_ranking": False,
            "oracle_pruning": False,
            "oracle_promotion": False,
            "winner_selection": False,
            "external_authority_export": False,
            "governance_authority": False,
            "external_mutation": False,
        },
        "notes": [
            "This command materializes one local candidate assembly from hash-bound GEPA optimizer output.",
            "It does not mutate the source candidate, GEPA output, AK, governance, Oracle authority, or external authority.",
            "It does not rank, select a winner, approve, promote, deploy, or activate the candidate.",
        ],
    }
    if result_out is not None:
        result_out.parent.mkdir(parents=True, exist_ok=True)
        result_out.write_text(_json_text(result), encoding="utf-8")
    return result
