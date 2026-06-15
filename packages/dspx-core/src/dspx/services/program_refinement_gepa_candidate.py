from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import sha256_text
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_refinement import load_program_manifest
from dspx.services.program_service import (
    _run_eval_behavior,
    materialize_program_from_intent,
)
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
            "def _receipt_manifest_hash() -> str:",
            "    path = Path(str(assembly_manifest_path()) + '.meta.json')",
            "    if not path.exists():",
            "        return ''",
            "    try:",
            "        payload = json.loads(path.read_text(encoding='utf-8'))",
            "    except Exception:",
            "        return ''",
            "    if not isinstance(payload, dict):",
            "        return ''",
            "    value = payload.get('hash') or payload.get('output_hash')",
            "    return str(value) if value else ''",
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
            "def _current_manifest_hash() -> str:",
            "    path = assembly_manifest_path()",
            "    return _sha256_file(path) if path.exists() else ''",
            "",
            "",
            "def _manifest_hash() -> str:",
            "    return _receipt_manifest_hash() or _current_manifest_hash()",
            "",
            "",
            "def program_observability_tags() -> dict[str, str]:",
            "    manifest = load_manifest()",
            "    assembly = manifest.get('candidate_assembly')",
            "    if not isinstance(assembly, dict):",
            "        assembly = {}",
            "    tags = {",
            "        'program.name': str(intent_summary().get('name') or ''),",
            "        'program.assembly_id': str(assembly.get('assembly_id') or ''),",
            "        'program.candidate_id': str(assembly.get('candidate_id') or ''),",
            "    }",
            "    manifest_hash = _manifest_hash()",
            "    if manifest_hash:",
            "        tags['program.manifest_hash'] = manifest_hash",
            "    return {key: value for key, value in tags.items() if value}",
            "",
            "",
            "def configure_observability(",
            "    *,",
            "    run_name: str = 'program-runtime',",
            "    run_kind: str = 'program-runtime',",
            ") -> bool:",
            "    try:",
            "        from dspx.tracing import enable_mlflow_from_env, ensure_run_with_standard_tags, get_mlflow",
            "",
            "        enable_mlflow_from_env()",
            "        if get_mlflow() is None:",
            "            return False",
            "        extra_tags = program_observability_tags()",
            "        if run_kind in {'program-runtime', 'program-eval'} and not extra_tags.get('program.assembly_id'):",
            "            return False",
            "        return ensure_run_with_standard_tags(",
            "            'program',",
            "            template_version=PROGRAM_TEMPLATE_VERSION,",
            "            run_name=run_name,",
            "            run_kind=run_kind,",
            "            output_basename='program.py',",
            "            output_hash=_manifest_hash(),",
            "            extra=extra_tags,",
            "        )",
            "    except Exception:",
            "        return False",
            "",
            "",
            "def end_observability_run(started: bool, *, status: str = 'FINISHED') -> None:",
            "    if not started:",
            "        return",
            "    try:",
            "        from dspx.tracing import get_mlflow",
            "",
            "        mlflow = get_mlflow()",
            "        if mlflow is not None:",
            "            try:",
            "                mlflow.end_run(status=status)",
            "            except TypeError:",
            "                mlflow.end_run()",
            "    except Exception:",
            "        pass",
            "",
            "",
            "def _active_mlflow():",
            "    try:",
            "        from dspx.tracing import get_mlflow",
            "",
            "        mlflow = get_mlflow()",
            "        if mlflow is None or mlflow.active_run() is None:",
            "            return None",
            "        return mlflow",
            "    except Exception:",
            "        return None",
            "",
            "",
            "def _set_observability_status(status: str, *, error: Exception | None = None) -> None:",
            "    mlflow = _active_mlflow()",
            "    if mlflow is None:",
            "        return",
            "    try:",
            "        mlflow.set_tag('program.runtime.status', status)",
            "    except Exception:",
            "        pass",
            "    try:",
            "        mlflow.log_metric('program.runtime.error', 1.0 if error is not None else 0.0)",
            "    except Exception:",
            "        pass",
            "    if error is not None:",
            "        try:",
            "            mlflow.set_tag('program.runtime.error_type', type(error).__name__)",
            "        except Exception:",
            "            pass",
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
            "    started = configure_observability(run_name='program-runtime', run_kind='program-runtime')",
            "    end_status = 'FINISHED'",
            "    try:",
            "        prediction = build_program()(**inputs)",
            "        _set_observability_status('passed')",
            "        return prediction",
            "    except Exception as exc:",
            "        end_status = 'FAILED'",
            "        _set_observability_status('failed', error=exc)",
            "        raise",
            "    finally:",
            "        end_observability_run(started, status=end_status)",
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


def _upsert_surface(
    surfaces: list[dict[str, Any]],
    *,
    kind: str,
    path: str,
    content_hash: str,
    schema_version: str,
    generator: str,
) -> None:
    for surface in surfaces:
        if surface.get("kind") == kind:
            surface.update(
                {
                    "path": path,
                    "content_hash": content_hash,
                    "schema_version": schema_version,
                    "generator": generator,
                }
            )
            return
    surfaces.append(
        {
            "kind": kind,
            "path": path,
            "content_hash": content_hash,
            "schema_version": schema_version,
            "generator": generator,
        }
    )


def _remove_surface(surfaces: list[dict[str, Any]], *, kind: str, path: str) -> None:
    surfaces[:] = [
        surface
        for surface in surfaces
        if not (surface.get("kind") == kind or surface.get("path") == path)
    ]


def _source_summary_from_behavior_episode(
    behavior_episode_payload: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _safe_mapping(behavior_episode_payload.get("summary"))
    return {
        "status": summary.get("status"),
        "source_count": summary.get("source_count"),
        "total": summary.get("total"),
        "passed": summary.get("passed"),
        "failed": summary.get("failed"),
        "error": summary.get("error"),
        "degraded": summary.get("degraded"),
        "status_counts": _safe_mapping(summary.get("status_counts")),
    }


def _refresh_gepa_candidate_behavior_evidence(candidate_root: Path) -> dict[str, Any]:
    """Refresh generated behavior evidence after the GEPA loader replaces program.py."""

    eval_behavior_path = candidate_root / "eval_behavior.py"
    if not eval_behavior_path.exists():
        return {
            "status": "not_applicable",
            "reason": "eval_behavior.py is absent",
            "behavior_episode_path": None,
            "behavior_episode_sha256": None,
            "behavior_results_path": None,
            "behavior_results_sha256": None,
            "oracle_evidence_removed": False,
        }

    behavior_episode_path = candidate_root / "behavior_episode.json"
    if behavior_episode_path.exists():
        behavior_episode_path.unlink()
    harness_result = _run_eval_behavior(candidate_root)
    if not behavior_episode_path.exists():
        raise ProgramRefinementGepaCandidateError(
            "GEPA candidate behavior refresh did not write behavior_episode.json"
        )
    behavior_episode_payload = _load_json_object(
        behavior_episode_path, label="GEPA candidate behavior episode"
    )
    behavior_episode_hash = _sha256_file(behavior_episode_path)
    behavior_results_path = candidate_root / "behavior_results.json"
    behavior_results_payload: dict[str, Any] | None = None
    behavior_results_hash: str | None = None
    if behavior_results_path.exists():
        behavior_results_payload = _load_json_object(
            behavior_results_path, label="GEPA candidate behavior results"
        )
        behavior_results_hash = _sha256_file(behavior_results_path)

    oracle_evidence_path = candidate_root / "oracle_evidence.json"
    oracle_evidence_removed = False
    if oracle_evidence_path.exists():
        oracle_evidence_path.unlink()
        oracle_evidence_removed = True

    manifest_path = candidate_root / "manifest.json"
    manifest = _load_json_object(manifest_path, label="GEPA candidate manifest")
    request = _safe_mapping(manifest.get("request"))
    request["behavior_episode_hash"] = behavior_episode_hash
    if behavior_results_hash is not None:
        request["behavior_results_hash"] = behavior_results_hash
    else:
        request["behavior_results_hash"] = None
    request["oracle_evidence_hash"] = None
    manifest["request"] = request

    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    evidence = _safe_mapping(receipt_bundle.get("evidence"))
    surface_hashes = _safe_mapping(evidence.get("surface_hashes"))
    surface_hashes["behavior_episode.json"] = behavior_episode_hash
    evidence["behavior_episode_hash"] = behavior_episode_hash
    evidence["behavior_episode_path"] = "behavior_episode.json"
    if behavior_results_hash is not None:
        surface_hashes["behavior_results.json"] = behavior_results_hash
        evidence["behavior_results_hash"] = behavior_results_hash
        evidence["behavior_results_path"] = "behavior_results.json"
    else:
        surface_hashes.pop("behavior_results.json", None)
        evidence["behavior_results_hash"] = None
        evidence["behavior_results_path"] = None
    surface_hashes.pop("oracle_evidence.json", None)
    evidence["oracle_evidence_hash"] = None
    evidence["oracle_evidence_path"] = None
    evidence["surface_hashes"] = surface_hashes
    receipt_bundle["evidence"] = evidence
    manifest["receipt_bundle"] = receipt_bundle

    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    surfaces = [
        dict(item)
        for item in _safe_list(candidate_assembly.get("surfaces"))
        if isinstance(item, Mapping)
    ]
    _upsert_surface(
        surfaces,
        kind="behavior_episode",
        path="behavior_episode.json",
        content_hash=behavior_episode_hash,
        schema_version="program-behavior-episode-v1",
        generator="program-refine materialize-gepa-candidate behavior-refresh",
    )
    if behavior_results_hash is not None:
        _upsert_surface(
            surfaces,
            kind="behavior_results",
            path="behavior_results.json",
            content_hash=behavior_results_hash,
            schema_version="program-behavior-results-v1",
            generator="program-refine materialize-gepa-candidate behavior-refresh",
        )
    else:
        _remove_surface(surfaces, kind="behavior_results", path="behavior_results.json")
    _remove_surface(surfaces, kind="oracle_evidence", path="oracle_evidence.json")
    surface_kinds = [
        str(kind)
        for kind in candidate_assembly.get("surface_kinds") or []
        if str(kind) not in {"oracle_evidence"}
    ]
    if "behavior_episode" not in surface_kinds:
        surface_kinds.append("behavior_episode")
    if behavior_results_hash is not None and "behavior_results" not in surface_kinds:
        surface_kinds.append("behavior_results")
    if behavior_results_hash is None:
        surface_kinds = [kind for kind in surface_kinds if kind != "behavior_results"]
    candidate_assembly["surface_kinds"] = surface_kinds
    candidate_assembly["surfaces"] = surfaces
    manifest["candidate_assembly"] = candidate_assembly

    episode_summary = _source_summary_from_behavior_episode(behavior_episode_payload)
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    execution_episode["behavior_status"] = episode_summary.get("status")
    execution_episode["behavior_evidence_summary"] = episode_summary
    execution_episode["behavior_orchestration"] = {
        "status": "passed",
        "harness": "eval_behavior.py",
        "returncode": harness_result.get("returncode"),
        "result_artifact": "behavior_episode.json",
        "result_hash": behavior_episode_hash,
        "summary": _safe_mapping(behavior_episode_payload.get("summary")),
    }
    execution_episode["oracle_evidence"] = None
    materialization = _safe_mapping(execution_episode.get("materialization"))
    generated_files = [
        str(path)
        for path in materialization.get("generated_files") or []
        if str(path) not in {"behavior_results.json", "oracle_evidence.json"}
    ]
    if (
        behavior_results_hash is not None
        and "behavior_results.json" not in generated_files
    ):
        generated_files.append("behavior_results.json")
    if "behavior_episode.json" not in generated_files:
        generated_files.append("behavior_episode.json")
    materialization["generated_files"] = sorted(generated_files)
    materialization["generated_file_count"] = len(generated_files)
    execution_episode["materialization"] = materialization
    if behavior_results_hash is not None and behavior_results_payload is not None:
        behavior_summary = _safe_mapping(behavior_results_payload.get("summary"))
        execution_episode["behavior_results"] = {
            "path": "behavior_results.json",
            "content_hash": behavior_results_hash,
            "summary": behavior_summary,
        }
        execution_episode["behavioral_evaluation"] = {
            "status": behavior_summary.get("status"),
            "result_artifact": "behavior_results.json",
            "result_hash": behavior_results_hash,
            "summary": behavior_summary,
        }
    else:
        execution_episode["behavior_results"] = None
        execution_episode["behavioral_evaluation"] = {
            "status": "missing_results",
            "result_artifact": None,
            "result_hash": None,
            "summary": {},
        }
    metadata = _safe_mapping(execution_episode.get("metadata"))
    metadata["behavior_episode"] = dict(behavior_episode_payload)
    if behavior_results_payload is not None:
        metadata["behavior_results"] = dict(behavior_results_payload)
    else:
        metadata.pop("behavior_results", None)
    metadata.pop("program_oracle_evidence", None)
    execution_episode["metadata"] = metadata
    manifest["execution_episode"] = execution_episode
    manifest["behavior_episode_artifact"] = {
        "path": "behavior_episode.json",
        "content_hash": behavior_episode_hash,
        "schema_version": "program-behavior-episode-v1",
    }
    manifest["oracle_evidence_artifact"] = None
    manifest["oracle_readability"] = {
        "status": "not_applicable_after_gepa_program_rewrite",
        "path": None,
        "content_hash": None,
        "summary": {},
        "facets": {},
        "reason": "program-refine materialize-gepa-candidate refreshed behavior evidence after replacing program.py; stale program-gen oracle_evidence.json was removed",
        "authority": "oracle_readability_only_non_authoritative",
    }

    gepa_refinement = _safe_mapping(manifest.get("gepa_refinement"))
    gepa_refinement["behavior_refresh"] = {
        "status": "refreshed",
        "behavior_episode_sha256": behavior_episode_hash,
        "behavior_results_sha256": behavior_results_hash,
        "oracle_evidence_removed_as_stale": oracle_evidence_removed,
        "authority": "local_behavior_evidence_only_non_authoritative",
    }
    manifest["gepa_refinement"] = gepa_refinement
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")
    manifest_hash = _sha256_file(manifest_path)
    meta_path = candidate_root / "manifest.json.meta.json"
    if meta_path.exists():
        meta_payload = _load_json_object(
            meta_path, label="GEPA candidate manifest meta"
        )
        meta_payload["hash"] = manifest_hash
        meta_payload["output_hash"] = manifest_hash
        meta_path.write_text(_json_text(meta_payload), encoding="utf-8")

    return {
        "status": "refreshed",
        "behavior_episode_path": str(behavior_episode_path),
        "behavior_episode_sha256": behavior_episode_hash,
        "behavior_results_path": str(behavior_results_path)
        if behavior_results_hash is not None
        else None,
        "behavior_results_sha256": behavior_results_hash,
        "summary": _safe_mapping(behavior_episode_payload.get("summary")),
        "oracle_evidence_removed": oracle_evidence_removed,
    }


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
    behavior_refresh: dict[str, Any] = {}
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
        behavior_refresh = _refresh_gepa_candidate_behavior_evidence(artifact_root)
        updated_manifest = _load_json_object(
            artifact_root / "manifest.json", label="GEPA candidate manifest"
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
        "behavior_refresh": behavior_refresh,
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
