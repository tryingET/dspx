from __future__ import annotations

from typing import Any

from dspx.dtos import ModuleSpec, SignatureGenRequest
from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_contracts import (
    intent_field_specs,
    intent_surface_names,
    sanitize_ident,
    surface_description,
)
from dspx.services.program_topology import (
    has_materializable_pipeline_topology,
    render_pipeline_module_surface,
    render_pipeline_program_code,
    render_pipeline_signature_surface,
)

_DIRECT_RUN_PROTECTED_OUTPUT_NAMES = PROTECTED_PROGRAM_ARTIFACT_NAMES | {
    "direct_run_receipt.json",
}


def render_signature_surface(intent: Any) -> tuple[str, dict[str, Any]]:
    """Render the signature surface through the signature generation service."""

    if has_materializable_pipeline_topology(intent):
        return render_pipeline_signature_surface(intent)

    from dspx.services.signatures_service import run_generate_dto

    names = intent_surface_names(intent)
    result = run_generate_dto(
        SignatureGenRequest(
            prompt=surface_description(intent.objective),
            template_version=str(
                intent.options.get("signature_template_version") or "simple-v1"
            ),
            options={
                "class_name": names["signature_class"],
                "inputs": list(intent.inputs or ["context"]),
                "outputs": list(intent.outputs or ["output"]),
                "input_fields": intent_field_specs(intent, role="input"),
                "output_fields": intent_field_specs(intent, role="output"),
                "run_kind": "program-signature-surface",
            },
        )
    )
    return result.code, dict(result.metadata or {})


def render_module_surface(intent: Any) -> tuple[str, dict[str, Any]]:
    """Render the module surface through the module generation service."""

    if has_materializable_pipeline_topology(intent):
        return render_pipeline_module_surface(intent)

    from dspx.services.module_service import run_generate as run_module_generate

    names = intent_surface_names(intent)
    artifact = run_module_generate(
        ModuleSpec(
            name=names["module_class"],
            description=surface_description(intent.objective),
            inputs=list(intent.inputs or ["context"]),
            outputs=list(intent.outputs or ["output"]),
            options={
                "template_version": str(
                    intent.options.get("module_template_version") or "simple-v1"
                ),
                "signature_class_name": names["signature_class"],
                "input_field_specs": intent_field_specs(intent, role="input"),
                "output_field_specs": intent_field_specs(intent, role="output"),
                "inline_examples": list(intent.examples or []),
                "demo_input_fields": list(intent.inputs or ["context"]),
                "focused_json_bundle_runtime": bool(
                    intent.options.get("focused_json_bundle_runtime")
                ),
            },
        ),
        use_signature=True,
    )
    return artifact.code, dict(artifact.metadata or {})


def render_direct_run_code(intent: Any) -> str:
    """Render a standard direct generated-program runner.

    The direct runner is intentionally lighter than `dspx program-run`: it imports the
    generated program, loads target-local DSPx config when present, configures a DSPy
    LM from the DSPx provider env, executes from JSON input files, writes declared
    output files, logs those outputs to the active program-runtime MLflow run when
    configured, and emits receipts. It does not create DSPx runtime sidecars, publish
    evidence, or mutate external authority surfaces. Batch mode is built in so callers
    do not need ad-hoc shell wrappers.
    """

    code = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

OUTPUT_RECEIPT = 'direct_run_receipt.json'
PROTECTED_OUTPUT_BASENAMES = __PROTECTED_OUTPUT_BASENAMES__
CONFIG_CANDIDATES = ('dspx-local.config.toml', 'config.toml')


def _redact_url(value: object) -> str | None:
    if value is None:
        return None
    try:
        from dspx.redaction import redact_url
    except Exception:
        return str(value)
    return redact_url(str(value))


def _sanitize_diagnostic_text(value: object, *, limit: int = 2000) -> str:
    try:
        from dspx.redaction import sanitize_diagnostic_text
    except Exception:
        text = '' if value is None else str(value)
        return text[-limit:]
    return sanitize_diagnostic_text('' if value is None else str(value), limit=limit)


def _prediction_mapping(prediction: object, output_fields: list[str]) -> dict[str, object]:
    if isinstance(prediction, Mapping):
        return {str(key): value for key, value in prediction.items()}
    for method_name in ('toDict', 'to_dict', 'model_dump'):
        method = getattr(prediction, method_name, None)
        if callable(method):
            payload = method()
            if isinstance(payload, Mapping):
                return dict(payload)
    mapped = {field: getattr(prediction, field) for field in output_fields if hasattr(prediction, field)}
    if mapped:
        return mapped
    if len(output_fields) == 1:
        return {output_fields[0]: prediction}
    return {}


def _data_uri_from_base64(*, data: str, media_type: str) -> str:
    raw = data.strip()
    if raw.startswith('data:'):
        return raw
    return f'data:{media_type};base64,{raw}'


def _image_marker_from_base64(*, data: str, media_type: str) -> str:
    try:
        import dspy
    except Exception as exc:
        raise RuntimeError('runtime image descriptors require dspy') from exc
    return str(dspy.Image(_data_uri_from_base64(data=data, media_type=media_type)))


def _materialize_designmd_visual_image_inputs_text(value: str) -> str:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return value
    if not isinstance(payload, dict):
        return value
    images = payload.get('images')
    if not isinstance(images, list):
        return value
    next_payload = dict(payload)
    next_images: list[object] = []
    materialized = 0
    for item in images:
        if not isinstance(item, dict):
            next_images.append(item)
            continue
        image = dict(item)
        data = str(image.get('imageDataBase64') or '').strip()
        media_type = str(image.get('imageDataMimeType') or image.get('mimeType') or 'image/png').strip()
        if data and image.get('pixelInspectionInputStatus') == 'available_bounded_inline_image_payload':
            image['modelImageInput'] = _image_marker_from_base64(data=data, media_type=media_type)
            image['modelImageInputMaterialized'] = True
            materialized += 1
        next_images.append(image)
    next_payload['images'] = next_images
    next_payload['modelImageInputMaterializedCount'] = materialized
    next_payload['modelImageInputAdapter'] = 'dspy.Image(data-uri)'
    if materialized <= 0:
        next_payload['pixelInspectionStatus'] = 'not_run_due_to_missing_image_input_adapter'
    return json.dumps(next_payload, ensure_ascii=False, indent=2, sort_keys=True)


def _materialize_runtime_input_value(key: str, value: object) -> object:
    if key == 'visual_image_inputs_json' and isinstance(value, str):
        return _materialize_designmd_visual_image_inputs_text(value)
    return value


def _load_inputs(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    inputs = payload.get('inputs') if isinstance(payload, dict) else None
    if isinstance(inputs, dict):
        return {str(key): _materialize_runtime_input_value(str(key), value) for key, value in inputs.items()}
    if isinstance(payload, dict):
        return {str(key): _materialize_runtime_input_value(str(key), value) for key, value in payload.items()}
    raise SystemExit(f'input file must be a JSON object: {path}')


def _parse_json_output(value: object, *, field: str) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith('```') and text.endswith('```'):
        text = '\\n'.join(text.splitlines()[1:-1]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Plain string outputs are valid DSPy outputs. Persist them as JSON
        # strings instead of requiring model/program code to pre-encode them.
        return value


def _safe_output_path(outdir: Path, field: object) -> Path:
    raw = str(field)
    candidate = Path(raw)
    if candidate.is_absolute() or not candidate.parts:
        raise SystemExit(f'unsafe generated output field path: {raw}')
    if any(part in {'', '.', '..'} for part in candidate.parts):
        raise SystemExit(f'unsafe generated output field path: {raw}')
    if any(part in PROTECTED_OUTPUT_BASENAMES for part in candidate.parts):
        raise SystemExit(f'generated output field collides with protected artifact path: {raw}')
    root = outdir.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise SystemExit(f'generated output field escapes outdir: {raw}') from None
    return resolved


def _find_runtime_config(explicit: Path | None, *, program_dir: Path) -> Path | None:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.exists():
            raise SystemExit(f'config file not found: {path}')
        return path
    env_path = os.getenv('DSPX_CONFIG')
    if env_path:
        path = Path(env_path).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f'DSPX_CONFIG path not found: {path}')
        return path
    for parent in [program_dir, *program_dir.parents]:
        for name in CONFIG_CANDIDATES:
            candidate = parent / name
            if candidate.exists():
                return candidate.resolve()
    return None


def _resolve_relative_mlflow_paths(*, config_path: Path | None) -> None:
    if config_path is None:
        return
    uri = str(os.getenv('MLFLOW_TRACKING_URI') or '').strip()
    prefix = 'sqlite:///'
    if uri.startswith(prefix) and '?' not in uri and '#' not in uri:
        raw_path = uri[len(prefix):]
        if raw_path:
            tracking_path = Path(raw_path).expanduser()
            if not tracking_path.is_absolute():
                resolved = (config_path.parent / tracking_path).resolve()
                resolved.parent.mkdir(parents=True, exist_ok=True)
                os.environ['MLFLOW_TRACKING_URI'] = 'sqlite:///' + str(resolved)
    artifact_root = str(os.getenv('MLFLOW_ARTIFACT_ROOT') or '').strip()
    if not artifact_root:
        return
    if artifact_root.startswith(('s3://', 'gs://', 'az://', 'http://', 'https://', 'file://')):
        return
    artifact_path = Path(artifact_root).expanduser()
    if artifact_path.is_absolute():
        return
    resolved_artifacts = (config_path.parent / artifact_path).resolve()
    resolved_artifacts.mkdir(parents=True, exist_ok=True)
    os.environ['MLFLOW_ARTIFACT_ROOT'] = resolved_artifacts.as_uri()


def _coerce_config_bool(value: object) -> str:
    if isinstance(value, bool):
        return '1' if value else '0'
    text = str(value).strip().lower()
    return '0' if text in {'0', 'false', 'no', 'off', ''} else '1'


def _set_env_from_config(section: object, key: str, env_key: str, *, boolean: bool = False) -> None:
    if not isinstance(section, Mapping) or key not in section:
        return
    value = section.get(key)
    if value is None:
        os.environ.pop(env_key, None)
        return
    os.environ[env_key] = _coerce_config_bool(value) if boolean else str(value)


def _apply_runtime_config_env(data: object) -> None:
    # Make the selected target-local runtime config win over stale shell env.
    # load_config_env preserves explicit env overrides for ordinary DSPx CLI usage.
    # Generated direct runners are different: the selected stage-local config is
    # the direct-run contract, so leftover DSPX_PROVIDER=stub or MLFLOW_ENABLE=0
    # from program-gen smoke commands must not shadow non-secret config values.
    # Secrets remain outside TOML because config_loader rejects secret-like keys.
    if not isinstance(data, Mapping):
        return
    mlflow = data.get('mlflow')
    provider = data.get('provider')
    lm_auth = data.get('lm_auth')
    _set_env_from_config(mlflow, 'enable', 'MLFLOW_ENABLE', boolean=True)
    _set_env_from_config(mlflow, 'tracking_uri', 'MLFLOW_TRACKING_URI')
    _set_env_from_config(mlflow, 'experiment', 'MLFLOW_EXPERIMENT')
    _set_env_from_config(mlflow, 'artifact_root', 'MLFLOW_ARTIFACT_ROOT')
    _set_env_from_config(provider, 'name', 'DSPX_PROVIDER')
    _set_env_from_config(lm_auth, 'model', 'DSPX_LM_AUTH_MODEL')
    _set_env_from_config(lm_auth, 'auth_provider', 'DSPX_LM_AUTH_PROVIDER')
    _set_env_from_config(lm_auth, 'auth_storage', 'DSPX_LM_AUTH_STORAGE')
    _set_env_from_config(lm_auth, 'timeout_s', 'DSPX_LM_AUTH_TIMEOUT')
    _set_env_from_config(lm_auth, 'strict', 'DSPX_LM_AUTH_STRICT', boolean=True)
    _set_env_from_config(lm_auth, 'temperature', 'DSPX_LM_AUTH_TEMPERATURE')
    _set_env_from_config(lm_auth, 'max_tokens', 'DSPX_LM_AUTH_MAX_TOKENS')


def _load_runtime_config(config_path: Path | None, *, program_dir: Path) -> str | None:
    chosen = _find_runtime_config(config_path, program_dir=program_dir)
    try:
        from dspx.config_loader import load_config_env

        config_data = load_config_env(str(chosen) if chosen is not None else None)
    except Exception as exc:
        raise SystemExit(f'failed to load DSPx runtime config: {exc}') from exc
    if chosen is not None:
        _apply_runtime_config_env(config_data)
    _resolve_relative_mlflow_paths(config_path=chosen)
    return str(chosen) if chosen is not None else None


def _configure_lm() -> dict[str, Any]:
    import dspy
    from dspx.provider_registry import create_from_env, ensure_default_providers

    ensure_default_providers()
    lm = create_from_env(default='dspy-lm-auth')
    dspy.configure(lm=lm)
    return {
        'provider': getattr(lm, 'model', type(lm).__name__),
        'kwargs': dict(getattr(lm, 'kwargs', {}) or {}),
    }


def _active_mlflow_run_id() -> str | None:
    try:
        from dspx.tracing import get_mlflow

        mlflow = get_mlflow()
        active = None if mlflow is None else mlflow.active_run()
        info = None if active is None else getattr(active, 'info', None)
        run_id = None if info is None else getattr(info, 'run_id', None)
        return str(run_id) if run_id else None
    except Exception:
        return None


def _set_runtime_failed(error: BaseException) -> None:
    try:
        from dspx.tracing import get_mlflow

        mlflow = get_mlflow()
        if mlflow is None or mlflow.active_run() is None:
            return
        try:
            mlflow.set_tag('program.runtime.status', 'failed')
            mlflow.set_tag('program.runtime.error_type', type(error).__name__)
        except Exception:
            pass
        try:
            mlflow.log_metric('program.runtime.error', 1.0)
        except Exception:
            pass
    except Exception:
        return


def _log_output_artifacts(outdir: Path) -> bool:
    try:
        from dspx.tracing import get_mlflow

        mlflow = get_mlflow()
        if mlflow is None or mlflow.active_run() is None:
            return False
        mlflow.log_artifacts(str(outdir), artifact_path='direct_run_outputs')
        return True
    except Exception:
        return False


def _mlflow_receipt() -> dict[str, Any]:
    return {
        'enabled': str(os.getenv('MLFLOW_ENABLE', '1')).strip().lower() not in {'', '0', 'false', 'no'},
        'tracking_uri': _redact_url(os.getenv('MLFLOW_TRACKING_URI') or None),
        'experiment': os.getenv('MLFLOW_EXPERIMENT') or None,
    }


def _write_direct_run_receipt(
    *,
    status: str,
    program_dir: Path,
    inputs_path: Path,
    outdir: Path,
    config_path: str | None,
    provider: dict[str, Any],
    output_fields: list[str],
    started: bool,
    mlflow_run_id: str | None,
    artifacts_logged: bool,
    error: BaseException | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        'schema_version': 'generated-dspy-direct-run-v1',
        'status': status,
        'program_dir': str(program_dir),
        'inputs_path': str(inputs_path.resolve()),
        'outdir': str(outdir.resolve()),
        'config_path': config_path,
        'provider': provider,
        'output_files': output_fields,
        'observability': {
            **_mlflow_receipt(),
            'program_runtime_run_started': started,
            'mlflow_run_id': mlflow_run_id,
            'output_artifacts_logged': artifacts_logged,
            'artifact_path': 'direct_run_outputs' if artifacts_logged else None,
        },
        'canonical_notes_mutated': False,
        'dspx_program_run_wrapper_used': False,
    }
    if error is not None:
        receipt['error'] = {
            'type': type(error).__name__,
            'message': _sanitize_diagnostic_text(error),
        }
    (outdir / OUTPUT_RECEIPT).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + '\\n',
        encoding='utf-8',
    )
    return receipt


def _single_run(inputs_path: Path, outdir: Path, config_path: Path | None = None) -> dict[str, Any]:
    program_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(program_dir))
    from program import build_program, configure_observability, end_observability_run, io_spec  # noqa: PLC0415

    loaded_config = _load_runtime_config(config_path, program_dir=program_dir)
    output_fields = list(io_spec().get('outputs', []))
    if not output_fields:
        raise SystemExit('generated program io_spec declares no outputs')
    outdir.mkdir(parents=True, exist_ok=True)
    inputs = _load_inputs(inputs_path)
    provider = _configure_lm()
    started = False
    end_status = 'FINISHED'
    mlflow_run_id: str | None = None
    artifacts_logged = False
    try:
        started = configure_observability(run_name='program-runtime', run_kind='program-runtime')
        mlflow_run_id = _active_mlflow_run_id()
        prediction = build_program()(**inputs)
        observed = _prediction_mapping(prediction, output_fields)

        for field in output_fields:
            if field not in observed:
                raise SystemExit(f'missing generated output: {field}')
            parsed = _parse_json_output(observed[field], field=field)
            output_path = _safe_output_path(outdir, field)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True) + '\\n',
                encoding='utf-8',
            )
        artifacts_logged = _log_output_artifacts(outdir)
    except BaseException as exc:
        end_status = 'FAILED'
        _set_runtime_failed(exc)
        _write_direct_run_receipt(
            status='failed',
            program_dir=program_dir,
            inputs_path=inputs_path,
            outdir=outdir,
            config_path=loaded_config,
            provider=provider,
            output_fields=output_fields,
            started=started,
            mlflow_run_id=mlflow_run_id,
            artifacts_logged=False,
            error=exc,
        )
        raise SystemExit(_sanitize_diagnostic_text(exc)) from None
    finally:
        end_observability_run(started, status=end_status)

    return _write_direct_run_receipt(
        status='ok',
        program_dir=program_dir,
        inputs_path=inputs_path,
        outdir=outdir,
        config_path=loaded_config,
        provider=provider,
        output_fields=output_fields,
        started=started,
        mlflow_run_id=mlflow_run_id,
        artifacts_logged=artifacts_logged,
    )


def _target_name(input_file: Path, inputs_root: Path) -> str:
    parent = input_file.parent
    if parent.name == 'runtime' and parent.parent != inputs_root:
        return parent.parent.name
    if parent != inputs_root:
        return parent.name
    return input_file.stem


def _discover_input_files(inputs_root: Path) -> list[Path]:
    direct_children = sorted(inputs_root.glob('*/runtime_inputs.json'))
    if direct_children:
        return direct_children
    nested = sorted(inputs_root.glob('*/runtime/runtime_inputs.json'))
    if nested:
        return nested
    return sorted(inputs_root.glob('*.json'))


def _tail_text(value: object, *, limit: int = 2000) -> str:
    if value is None:
        return ''
    if isinstance(value, bytes):
        text = value.decode('utf-8', errors='replace')
    else:
        text = str(value)
    return _sanitize_diagnostic_text(text, limit=limit)


def _run_child(input_file: Path, outdir: Path, timeout_seconds: int, retries: int, config_path: Path | None) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        '--inputs',
        str(input_file),
        '--outdir',
        str(outdir),
        '--json',
    ]
    if config_path is not None:
        cmd.extend(['--config', str(config_path)])
    for attempt in range(retries + 1):
        outdir.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            attempts.append({
                'attempt': attempt + 1,
                'returncode': None,
                'timed_out': True,
                'timeout_seconds': timeout_seconds,
                'error_type': 'TimeoutExpired',
                'stdout_tail': _tail_text(exc.stdout),
                'stderr_tail': _tail_text(exc.stderr),
            })
            continue
        except Exception as exc:
            attempts.append({
                'attempt': attempt + 1,
                'returncode': None,
                'error_type': type(exc).__name__,
                'error': _sanitize_diagnostic_text(exc),
            })
            continue
        attempts.append({
            'attempt': attempt + 1,
            'returncode': result.returncode,
            'stdout_tail': _tail_text(result.stdout),
            'stderr_tail': _tail_text(result.stderr),
        })
        if result.returncode == 0 and (outdir / OUTPUT_RECEIPT).exists():
            receipt = json.loads((outdir / OUTPUT_RECEIPT).read_text(encoding='utf-8'))
            return {
                'target': outdir.name,
                'status': 'ok',
                'inputs_path': str(input_file.resolve()),
                'outdir': str(outdir.resolve()),
                'attempts': attempts,
                'receipt': receipt,
            }
    return {
        'target': outdir.name,
        'status': 'failed',
        'inputs_path': str(input_file.resolve()),
        'outdir': str(outdir.resolve()),
        'attempts': attempts,
    }


def _preflight(config_path: Path | None = None) -> dict[str, Any]:
    program_dir = Path(__file__).resolve().parent
    loaded_config = _load_runtime_config(config_path, program_dir=program_dir)
    provider = _configure_lm()
    return {
        'schema_version': 'generated-dspy-direct-run-preflight-v1',
        'status': 'ok',
        'program_dir': str(program_dir),
        'config_path': loaded_config,
        'provider': provider,
        'resolved_env': {
            'DSPX_PROVIDER': os.getenv('DSPX_PROVIDER') or None,
            'DSPX_LM_AUTH_MODEL': os.getenv('DSPX_LM_AUTH_MODEL') or None,
            'DSPX_LM_AUTH_PROVIDER': os.getenv('DSPX_LM_AUTH_PROVIDER') or None,
            'MLFLOW_ENABLE': os.getenv('MLFLOW_ENABLE') or None,
            'MLFLOW_TRACKING_URI': _redact_url(os.getenv('MLFLOW_TRACKING_URI') or None),
            'MLFLOW_EXPERIMENT': os.getenv('MLFLOW_EXPERIMENT') or None,
            'MLFLOW_ARTIFACT_ROOT': os.getenv('MLFLOW_ARTIFACT_ROOT') or None,
        },
        'model_call_performed': False,
        'canonical_notes_mutated': False,
        'dspx_program_run_wrapper_used': False,
    }


def _batch_run(inputs_root: Path, out_root: Path, parallel: int, timeout_seconds: int, retries: int, config_path: Path | None = None) -> dict[str, Any]:
    if parallel < 1:
        raise SystemExit('--parallel must be >= 1')
    if timeout_seconds <= 0:
        raise SystemExit('--timeout-seconds must be > 0')
    if retries < 0:
        raise SystemExit('--retries must be >= 0')
    input_files = _discover_input_files(inputs_root)
    if not input_files:
        raise SystemExit(f'no batch inputs found under {inputs_root}')
    out_root.mkdir(parents=True, exist_ok=True)
    jobs = [(input_file, out_root / _target_name(input_file, inputs_root)) for input_file in input_files]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        future_to_job = {executor.submit(_run_child, input_file, outdir, timeout_seconds, retries, config_path): (input_file, outdir) for input_file, outdir in jobs}
        for future in as_completed(future_to_job):
            input_file, outdir = future_to_job[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({
                    'target': outdir.name,
                    'status': 'failed',
                    'inputs_path': str(input_file.resolve()),
                    'outdir': str(outdir.resolve()),
                    'attempts': [],
                    'error_type': type(exc).__name__,
                    'error': _sanitize_diagnostic_text(exc),
                })
    results.sort(key=lambda item: str(item.get('target', '')))
    failed = [item for item in results if item.get('status') != 'ok']
    summary = {
        'schema_version': 'generated-dspy-direct-batch-run-v1',
        'status': 'ok' if not failed else 'failed',
        'inputs_root': str(inputs_root.resolve()),
        'out_root': str(out_root.resolve()),
        'parallel': parallel,
        'timeout_seconds': timeout_seconds,
        'retries': retries,
        'config_path': str(config_path.expanduser().resolve()) if config_path is not None else None,
        'total': len(results),
        'ok': len(results) - len(failed),
        'failed': len(failed),
        'canonical_notes_mutated': False,
        'dspx_program_run_wrapper_used': False,
        'results': results,
    }
    (out_root / 'direct_batch_receipt.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + '\\n',
        encoding='utf-8',
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description='Direct runner for this generated DSPy program.')
    single = parser.add_argument_group('single run')
    single.add_argument('--inputs', type=Path, help='JSON object or {inputs: {...}} payload.')
    single.add_argument('--outdir', type=Path, help='Directory for output JSON files and receipt.')
    batch = parser.add_argument_group('batch run')
    batch.add_argument('--inputs-root', type=Path, help='Root containing child runtime_inputs.json files.')
    batch.add_argument('--out-root', type=Path, help='Directory for per-target output folders and batch receipt.')
    batch.add_argument('--parallel', type=int, default=1, help='Batch parallelism. Default: 1.')
    batch.add_argument('--timeout-seconds', type=int, default=600, help='Per-target timeout for batch child runs. Default: 600.')
    batch.add_argument('--retries', type=int, default=0, help='Per-target retries after a failed child run. Default: 0.')
    parser.add_argument('--config', type=Path, help='DSPx runtime config. Defaults to nearest dspx-local.config.toml or config.toml above direct_run.py.')
    parser.add_argument('--preflight', action='store_true', help='Load config and resolve/configure the provider without executing the generated program or making a model call.')
    parser.add_argument('--json', action='store_true', help='Print receipt JSON to stdout.')
    args = parser.parse_args()

    if args.preflight:
        receipt = _preflight(args.config)
        if args.json:
            print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"provider={receipt['resolved_env']['DSPX_PROVIDER']} model={receipt['resolved_env']['DSPX_LM_AUTH_MODEL']} config={receipt['config_path']}")
        return 0

    if args.inputs_root or args.out_root:
        if not args.inputs_root or not args.out_root:
            raise SystemExit('batch mode requires --inputs-root and --out-root')
        summary = _batch_run(args.inputs_root, args.out_root, args.parallel, args.timeout_seconds, args.retries, args.config)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if summary['status'] == 'ok' else 1

    if not args.inputs or not args.outdir:
        raise SystemExit('single mode requires --inputs and --outdir')
    receipt = _single_run(args.inputs, args.outdir, args.config)
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
"""
    code = code.replace(
        "__PROTECTED_OUTPUT_BASENAMES__",
        repr(tuple(sorted(_DIRECT_RUN_PROTECTED_OUTPUT_NAMES))),
    )
    return code if code.endswith("\n") else code + "\n"


def render_program_code(intent: Any) -> str:
    """Render the program assembly surface that composes generated surfaces."""

    if has_materializable_pipeline_topology(intent):
        return render_pipeline_program_code(intent)

    names = intent_surface_names(intent)
    constraints = list(intent.constraints)
    metric = intent.metric or "unspecified"
    quality_criteria = list(intent.quality_criteria or [])
    declared_topology = dict(intent.topology or {})
    topology_execution_status = str(
        declared_topology.get("execution_status")
        or "single_module_scaffold_materialized"
    )
    materialization_scope = {
        "topology_declared": bool(declared_topology),
        "topology_materialized": not bool(declared_topology),
        "current_renderer": "single_module_scaffold",
    }

    lines: list[str] = [
        "from __future__ import annotations",
        "",
        "import json",
        "from pathlib import Path",
        "from typing import Any",
        "",
        "import dspy",
        "",
        "from module import (",
        "    build_student as build_module_student,",
        "    io_spec,",
        "    normalize_output,",
        "    output_weights,",
        ")",
        "",
        f"OBJECTIVE = {intent.objective!r}",
        f"CONSTRAINTS = {constraints!r}",
        f"METRIC = {metric!r}",
        f"QUALITY_CRITERIA = {quality_criteria!r}",
        f"DECLARED_TOPOLOGY = {declared_topology!r}",
        f"TOPOLOGY_EXECUTION_STATUS = {topology_execution_status!r}",
        f"MATERIALIZATION_SCOPE = {materialization_scope!r}",
        "PROGRAM_TEMPLATE_VERSION = 'program-candidate-assembly-v1'",
        "",
        "",
        "def assembly_manifest_path() -> Path:",
        "    return Path(__file__).with_name('manifest.json')",
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
        "def _current_manifest_hash() -> str:",
        "    path = assembly_manifest_path()",
        "    if not path.exists():",
        "        return ''",
        "    try:",
        "        import hashlib",
        "",
        "        return hashlib.sha256(path.read_bytes()).hexdigest()",
        "    except Exception:",
        "        return ''",
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
        "def run_with_observability(**inputs: object) -> dspy.Prediction:",
        "    started = configure_observability(run_name='program-runtime', run_kind='program-runtime')",
        "    end_status = 'FINISHED'",
        "    try:",
        "        program = build_program()",
        "        prediction = program(**inputs)",
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
        "def build_program() -> dspy.Module:",
        "    return build_module_student()",
        "",
        "",
        "def build_student(*, use_cot: bool = False) -> dspy.Module:",
        "    return build_module_student(use_cot=use_cot)",
        "",
        "",
        "def intent_summary() -> dict[str, object]:",
        "    return {",
        f"        'name': {intent.name!r},",
        "        'objective': OBJECTIVE,",
        "        'constraints': list(CONSTRAINTS),",
        "        'metric': METRIC,",
        "        'quality_criteria': list(QUALITY_CRITERIA),",
        "        'io': io_spec(),",
        "        'declared_topology': dict(DECLARED_TOPOLOGY),",
        "        'topology_execution_status': TOPOLOGY_EXECUTION_STATUS,",
        "        'materialization_scope': dict(MATERIALIZATION_SCOPE),",
        f"        'signature_class': {names['signature_class']!r},",
        f"        'module_class': {names['module_class']!r},",
        "    }",
        "",
    ]
    return "\n".join(lines)


def render_eval_smoke(intent: Any) -> str:
    program_class = sanitize_ident(intent.name)
    sample_inputs = {name: f"sample_{name}" for name in intent.inputs}
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "from program import build_program, intent_summary, io_spec",
            "",
            "",
            "def main() -> None:",
            "    program = build_program()",
            "    assert program is not None",
            f"    assert io_spec()['inputs'] == {list(intent.inputs)!r}",
            f"    assert io_spec()['outputs'] == {list(intent.outputs)!r}",
            "    assert intent_summary()['objective']",
            f"    print('program smoke ok: {program_class}')",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
            f"SAMPLE_INPUTS = {sample_inputs!r}",
        ]
    )


def render_eval_examples(intent: Any) -> str:
    """Render a deterministic examples behavior-evidence harness."""

    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import json",
            "from pathlib import Path",
            "from typing import Any",
            "",
            "from program import build_program, intent_summary, io_spec, normalize_output",
            "from dspx.services.program_quality_evaluation import declared_quality_output_fields, evaluate_declared_quality",
            "",
            "RESULT_PATH = Path('behavior_results.json')",
            "",
            "",
            "def _mapping_for(example: dict[str, object], role: str) -> dict[str, object]:",
            "    nested = example.get(role)",
            "    if isinstance(nested, dict):",
            "        return dict(nested)",
            "    return example",
            "",
            "",
            "def _jsonable(value: object) -> object:",
            "    if value is None or isinstance(value, (str, int, float, bool)):",
            "        return value",
            "    if isinstance(value, dict):",
            "        return {str(key): _jsonable(item) for key, item in value.items()}",
            "    if isinstance(value, (list, tuple)):",
            "        return [_jsonable(item) for item in value]",
            "    return str(value)",
            "",
            "",
            "def _sanitize_diagnostic_text(value: object, *, limit: int = 2000) -> str:",
            "    try:",
            "        from dspx.redaction import sanitize_diagnostic_text",
            "    except Exception:",
            "        text = '' if value is None else str(value)",
            "        return text[:limit]",
            "    return sanitize_diagnostic_text('' if value is None else str(value), limit=limit)",
            "",
            "",
            "def _prediction_mapping(prediction: object) -> dict[str, object]:",
            "    if isinstance(prediction, dict):",
            "        return dict(prediction)",
            "    for method_name in ('toDict', 'to_dict', 'model_dump'):",
            "        method = getattr(prediction, method_name, None)",
            "        if callable(method):",
            "            try:",
            "                payload = method()",
            "            except Exception:",
            "                continue",
            "            if isinstance(payload, dict):",
            "                return dict(payload)",
            "    return {}",
            "",
            "",
            "def _runtime_trace(program: object) -> dict[str, object] | None:",
            "    trace = getattr(program, '_last_runtime_trace', None)",
            "    return _jsonable(trace) if isinstance(trace, dict) else None",
            "",
            "",
            "def _observed_outputs(prediction: object, outputs: list[str]) -> tuple[dict[str, object], list[str]]:",
            "    observed: dict[str, object] = {}",
            "    notes: list[str] = []",
            "    mapped = _prediction_mapping(prediction)",
            "    for name in outputs:",
            "        if name in mapped:",
            "            observed[name] = mapped[name]",
            "        elif hasattr(prediction, name):",
            "            observed[name] = getattr(prediction, name)",
            "    if not observed:",
            "        notes.append('prediction exposed no declared output fields')",
            "    return observed, notes",
            "",
            "",
            "def _status_for(",
            "    outputs: list[str],",
            "    expected: dict[str, object],",
            "    observed: dict[str, object],",
            "    prediction: object,",
            ") -> tuple[str, list[str], dict[str, object]]:",
            "    quality = evaluate_declared_quality(intent_summary().get('quality_criteria'), observed)",
            "    comparable = [name for name in outputs if name in observed]",
            "    quality_declared = quality.get('status') != 'not_declared'",
            "    if quality_declared:",
            "        missing = [name for name in outputs if name not in observed]",
            "        if missing:",
            "            return 'failed', [f'missing declared outputs: {missing}'], quality",
            "        if quality.get('status') != 'passed':",
            "            return 'failed', ['declared quality criteria failed'], quality",
            "    if not comparable:",
            "        return 'degraded_no_comparable_output', ['no declared outputs were observable'], quality",
            "    quality_fields = declared_quality_output_fields(intent_summary().get('quality_criteria'))",
            "    exact_fields = [name for name in comparable if name not in quality_fields]",
            "    failures: list[str] = []",
            "    for name in exact_fields:",
            "        try:",
            "            gold, pred = normalize_output(",
            "                name, str(expected.get(name, '')), str(observed.get(name, '')), pred_trace=prediction",
            "            )",
            "        except Exception as exc:",
            "            failures.append(f'{name} normalization_error:{type(exc).__name__}')",
            "            continue",
            "        if gold != pred:",
            "            failures.append(name)",
            "    if failures:",
            "        return 'failed', [f'output mismatch: {failures}'], quality",
            "    if len(comparable) != len(outputs):",
            "        missing = [name for name in outputs if name not in observed]",
            "        return 'executed', [f'missing non-compared outputs: {missing}'], quality",
            "    return 'passed', [], quality",
            "",
            "",
            "def _quality_summary(records: list[dict[str, object]]) -> dict[str, object]:",
            "    rows = [record.get('quality_evaluation') for record in records if isinstance(record.get('quality_evaluation'), dict)]",
            "    declared = [row for row in rows if row.get('status') != 'not_declared']",
            "    if not declared:",
            "        return {'status': 'not_declared', 'criteria_declared': bool(intent_summary().get('quality_criteria')), 'evaluations_total': 0, 'evaluations_passed': 0, 'evaluations_failed': 0, 'quality_approved': False}",
            "    passed = sum(row.get('status') == 'passed' for row in declared)",
            "    return {'status': 'passed' if passed == len(declared) else 'failed', 'criteria_declared': True, 'evaluations_total': len(declared), 'evaluations_passed': passed, 'evaluations_failed': len(declared) - passed, 'quality_approved': False}",
            "",
            "",
            "def _summary(records: list[dict[str, object]]) -> dict[str, object]:",
            "    statuses = [str(record.get('status') or 'unknown') for record in records]",
            "    counts = {status: statuses.count(status) for status in sorted(set(statuses))}",
            "    error_count = sum(1 for status in statuses if status == 'error')",
            "    failed_count = sum(1 for status in statuses if status == 'failed')",
            "    degraded_count = sum(1 for status in statuses if status.startswith('degraded'))",
            "    passed_count = sum(1 for status in statuses if status == 'passed')",
            "    if records and passed_count == len(records):",
            "        episode_status = 'passed'",
            "    elif error_count == len(records):",
            "        episode_status = 'error'",
            "    elif failed_count:",
            "        episode_status = 'failed'",
            "    elif degraded_count:",
            "        episode_status = 'degraded'",
            "    else:",
            "        episode_status = 'executed'",
            "    return {",
            "        'total': len(records),",
            "        'passed': passed_count,",
            "        'failed': failed_count,",
            "        'error': error_count,",
            "        'degraded': degraded_count,",
            "        'status_counts': counts,",
            "        'status': episode_status,",
            "    }",
            "",
            "",
            "def _configure_provider() -> dict[str, object]:",
            "    try:",
            "        import dspy",
            "        from dspx.provider_registry import create_from_env, ensure_default_providers",
            "",
            "        ensure_default_providers()",
            "        lm = create_from_env(default='dspy-lm-auth')",
            "        dspy.configure(lm=lm)",
            "        return {'status': 'configured', 'provider': getattr(lm, 'model', type(lm).__name__)}",
            "    except Exception as exc:",
            "        return {'status': 'unavailable', 'error': {'type': type(exc).__name__, 'message': _sanitize_diagnostic_text(exc)}}",
            "",
            "",
            "def main() -> None:",
            "    examples = json.loads(Path('examples.json').read_text(encoding='utf-8'))",
            "    assert isinstance(examples, list)",
            "    spec = io_spec()",
            "    inputs = list(spec['inputs'])",
            "    outputs = list(spec['outputs'])",
            "    provider = _configure_provider()",
            "    program = build_program()",
            "    records: list[dict[str, object]] = []",
            "    for index, example in enumerate(examples):",
            "        assert isinstance(example, dict), f'example {index} must be an object'",
            "        input_values = _mapping_for(example, 'inputs')",
            "        output_values = _mapping_for(example, 'outputs')",
            "        missing_inputs = [name for name in inputs if name not in input_values]",
            "        missing_outputs = [name for name in outputs if name not in output_values]",
            "        assert not missing_inputs, f'example {index} missing inputs: {missing_inputs}'",
            "        assert not missing_outputs, f'example {index} missing outputs: {missing_outputs}'",
            "        record: dict[str, object] = {",
            "            'index': index,",
            "            'inputs': _jsonable(input_values),",
            "            'expected_outputs': _jsonable(output_values),",
            "        }",
            "        try:",
            "            prediction = program(**{name: input_values[name] for name in inputs})",
            "            observed, notes = _observed_outputs(prediction, outputs)",
            "            status, status_notes, quality = _status_for(outputs, output_values, observed, prediction)",
            "            trace = _runtime_trace(program)",
            "            record.update(",
            "                {",
            "                    'status': status,",
            "                    'observed_outputs': _jsonable(observed),",
            "                    'notes': notes + status_notes,",
            "                    'quality_evaluation': quality,",
            "                }",
            "            )",
            "            if trace is not None:",
            "                record['runtime_trace'] = trace",
            "        except Exception as exc:",
            "            trace = _runtime_trace(program)",
            "            record.update(",
            "                {",
            "                    'status': 'error',",
            "                    'observed_outputs': {},",
            "                    'quality_evaluation': evaluate_declared_quality(intent_summary().get('quality_criteria'), {}),",
            "                    'error': {'type': type(exc).__name__, 'message': _sanitize_diagnostic_text(exc)},",
            "                }",
            "            )",
            "            if trace is not None:",
            "                record['runtime_trace'] = trace",
            "        records.append(record)",
            "    payload: dict[str, Any] = {",
            "        'schema_version': 'program-behavior-results-v1',",
            "        'intent': intent_summary(),",
            "        'intent_name': intent_summary().get('name'),",
            "        'input_fields': inputs,",
            "        'output_fields': outputs,",
            "        'provider': provider,",
            "        'examples': records,",
            "        'summary': _summary(records),",
            "        'quality_evaluation': _quality_summary(records),",
            "        'authority': 'behavior_evidence_only_non_authoritative',",
            "        'non_authority': {'optimization_authority': False, 'promotion_authority': False, 'oracle_ranking': False, 'oracle_pruning': False, 'oracle_promotion': False, 'governance_authority': False, 'external_mutation': False, 'external_authority_mutated': False, 'winner_selection': False},",
            "    }",
            "    RESULT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')",
            '    print(f\'program examples ok: {len(examples)} example(s); behavior status: {payload["summary"]["status"]}\')',
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )


def render_eval_behavior(intent: Any) -> str:
    """Render a bounded local behavior orchestration harness."""

    harnesses: list[dict[str, object]] = []
    if getattr(intent, "examples", None):
        harnesses.append(
            {
                "kind": "examples",
                "source_kind": "examples_path"
                if getattr(intent, "examples_path", None)
                else "inline_examples",
                "harness": "eval_examples.py",
                "result": "behavior_results.json",
            }
        )
    if getattr(intent, "dataset", None) or getattr(intent, "datasets", None):
        for split in ("train", "validation", "test"):
            harnesses.append(
                {
                    "kind": "dataset_split",
                    "source_kind": "dataset_split",
                    "split": split,
                    "harness": f"eval_{split}.py",
                    "result": f"behavior_results.{split}.json",
                }
            )

    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import hashlib",
            "import json",
            "import os",
            "import subprocess",
            "import sys",
            "from pathlib import Path",
            "from typing import Any",
            "",
            "from program import configure_observability, end_observability_run",
            "from dspx.services.program_quality_evaluation import evaluate_declared_quality",
            "",
            f"HARNESS_PLAN: list[dict[str, object]] = {harnesses!r}",
            f"BOUND_QUALITY_CRITERIA: list[dict[str, object]] = {list(getattr(intent, 'quality_criteria', None) or [])!r}",
            "QUALITY_CRITERIA_DECLARED = bool(BOUND_QUALITY_CRITERIA)",
            "RESULT_PATH = Path('behavior_episode.json')",
            "",
            "",
            "def _sanitize_diagnostic_text(value: object, *, limit: int = 2000) -> str:",
            "    try:",
            "        from dspx.redaction import sanitize_diagnostic_text",
            "    except Exception:",
            "        text = '' if value is None else str(value)",
            "        return text[:limit]",
            "    return sanitize_diagnostic_text('' if value is None else str(value), limit=limit)",
            "",
            "",
            "def _sha256_file(path: Path) -> str:",
            "    return hashlib.sha256(path.read_bytes()).hexdigest()",
            "",
            "",
            "def _jsonable(value: object) -> object:",
            "    if value is None or isinstance(value, (str, int, float, bool)):",
            "        return value",
            "    if isinstance(value, dict):",
            "        return {str(key): _jsonable(item) for key, item in value.items()}",
            "    if isinstance(value, (list, tuple)):",
            "        return [_jsonable(item) for item in value]",
            "    return str(value)",
            "",
            "",
            "def _load_json(path: Path) -> dict[str, object]:",
            "    payload = json.loads(path.read_text(encoding='utf-8'))",
            "    assert isinstance(payload, dict), f'{path} must contain a JSON object'",
            "    return payload",
            "",
            "",
            "def _safe_summary(payload: dict[str, object]) -> dict[str, object]:",
            "    summary = payload.get('summary')",
            "    return dict(summary) if isinstance(summary, dict) else {}",
            "",
            "",
            "def _unevaluated_quality() -> dict[str, object]:",
            "    return {'status': 'not_declared', 'criteria_declared': QUALITY_CRITERIA_DECLARED, 'evaluations_total': 0, 'evaluations_passed': 0, 'evaluations_failed': 0, 'quality_approved': False}",
            "",
            "",
            "def _quality_evaluation(payload: dict[str, object]) -> dict[str, object]:",
            "    quality = payload.get('quality_evaluation')",
            "    assert isinstance(quality, dict), 'behavior results missing quality_evaluation'",
            "    expected = {'status', 'criteria_declared', 'evaluations_total', 'evaluations_passed', 'evaluations_failed', 'quality_approved'}",
            "    legacy = expected - {'criteria_declared'}",
            "    assert set(quality) in (expected, legacy), 'behavior quality_evaluation has invalid fields'",
            "    quality = dict(quality)",
            "    intent = payload.get('intent') if isinstance(payload.get('intent'), dict) else {}",
            "    assert intent.get('quality_criteria', []) == BOUND_QUALITY_CRITERIA, 'behavior quality criteria drift from candidate intent'",
            "    quality.setdefault('criteria_declared', QUALITY_CRITERIA_DECLARED)",
            "    status = quality.get('status')",
            "    total = quality.get('evaluations_total')",
            "    passed = quality.get('evaluations_passed')",
            "    failed = quality.get('evaluations_failed')",
            "    assert status in {'not_declared', 'passed', 'failed'}, 'behavior quality status is invalid'",
            "    assert isinstance(quality.get('criteria_declared'), bool), 'behavior quality declaration flag is invalid'",
            "    assert all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in (total, passed, failed)), 'behavior quality counts are invalid'",
            "    assert passed + failed == total, 'behavior quality counts are inconsistent'",
            "    assert quality.get('quality_approved') is False, 'behavior quality must remain non-authoritative'",
            "    assert (status == 'not_declared') == (total == 0), 'behavior quality declaration status is inconsistent'",
            "    assert status != 'passed' or failed == 0, 'passed behavior quality contains failures'",
            "    assert status != 'failed' or failed > 0, 'failed behavior quality has no failures'",
            "    records = payload.get('examples')",
            "    assert isinstance(records, list), 'behavior results examples are missing'",
            "    record_quality = [record.get('quality_evaluation') for record in records if isinstance(record, dict)]",
            "    assert len(record_quality) == len(records) and all(isinstance(row, dict) for row in record_quality), 'behavior record quality evidence is malformed'",
            "    assert all(row.get('status') in {'not_declared', 'passed', 'failed'} and row.get('quality_approved') is False for row in record_quality), 'behavior record quality evidence is invalid'",
            "    criteria = BOUND_QUALITY_CRITERIA",
            "    for record, row in zip(records, record_quality, strict=True):",
            "        observed = record.get('observed_outputs') if isinstance(record, dict) and isinstance(record.get('observed_outputs'), dict) else {}",
            "        assert row == evaluate_declared_quality(criteria, observed), 'behavior record quality drifts from observed outputs'",
            "    declared_records = [row for row in record_quality if row.get('status') != 'not_declared']",
            "    expected_passed = sum(row.get('status') == 'passed' for row in declared_records)",
            "    intent = payload.get('intent') if isinstance(payload.get('intent'), dict) else {}",
            "    expected_quality = {'status': 'not_declared' if not declared_records else ('passed' if expected_passed == len(declared_records) else 'failed'), 'criteria_declared': QUALITY_CRITERIA_DECLARED, 'evaluations_total': len(declared_records), 'evaluations_passed': expected_passed, 'evaluations_failed': len(declared_records) - expected_passed, 'quality_approved': False}",
            "    assert quality == expected_quality, 'behavior quality summary drifts from records'",
            "    return dict(quality)",
            "",
            "",
            "def _quality_summary(sources: list[dict[str, object]]) -> dict[str, object]:",
            "    rows = [source.get('quality_evaluation') for source in sources]",
            "    assert all(isinstance(row, dict) for row in rows), 'behavior episode source missing quality_evaluation'",
            "    declared = [row for row in rows if row.get('status') != 'not_declared']",
            "    if not declared:",
            "        return {'status': 'not_declared', 'criteria_declared': any(bool(row.get('criteria_declared')) for row in rows), 'evaluations_total': 0, 'evaluations_passed': 0, 'evaluations_failed': 0, 'quality_approved': False}",
            "    total = sum(int(row['evaluations_total']) for row in declared)",
            "    passed = sum(int(row['evaluations_passed']) for row in declared)",
            "    failed = sum(int(row['evaluations_failed']) for row in declared)",
            "    return {'status': 'failed' if failed else 'passed', 'criteria_declared': True, 'evaluations_total': total, 'evaluations_passed': passed, 'evaluations_failed': failed, 'quality_approved': False}",
            "",
            "",
            "def _harness_timeout_seconds() -> float:",
            "    raw = os.getenv('DSPX_PROGRAM_HARNESS_TIMEOUT', '60')",
            "    try:",
            "        return max(1.0, float(raw))",
            "    except ValueError:",
            "        return 60.0",
            "",
            "",
            "def _run_source(source: dict[str, object]) -> dict[str, object]:",
            "    harness_path = Path(str(source['harness']))",
            "    result_path = Path(str(source['result']))",
            "    record: dict[str, object] = {",
            "        'kind': source.get('kind'),",
            "        'source_kind': source.get('source_kind'),",
            "        'split': source.get('split'),",
            "        'harness_path': str(harness_path),",
            "        'behavior_results_path': str(result_path),",
            "        'quality_evaluation': _unevaluated_quality(),",
            "    }",
            "    if not harness_path.exists():",
            "        record.update({'status': 'missing_harness', 'returncode': None, 'summary': {}})",
            "        return record",
            "    if result_path.exists():",
            "        try:",
            "            if not result_path.is_file() and not result_path.is_symlink():",
            "                record.update({'status': 'stale_result_not_file', 'returncode': None, 'summary': {}})",
            "                return record",
            "            result_path.unlink()",
            "        except Exception as exc:",
            "            record.update({",
            "                'status': 'stale_result_cleanup_failed',",
            "                'returncode': None,",
            "                'summary': {},",
            "                'error': {'type': type(exc).__name__, 'message': _sanitize_diagnostic_text(exc)},",
            "            })",
            "            return record",
            "    command = [sys.executable, str(harness_path)]",
            "    try:",
            "        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=_harness_timeout_seconds())",
            "    except subprocess.TimeoutExpired as exc:",
            "        record.update({",
            "            'status': 'timeout',",
            "            'returncode': None,",
            "            'command': command,",
            "            'stdout': _sanitize_diagnostic_text((exc.stdout or '').strip()) if isinstance(exc.stdout, str) else '',",
            "            'stderr': _sanitize_diagnostic_text((exc.stderr or '').strip()) if isinstance(exc.stderr, str) else '',",
            "            'timeout_seconds': _harness_timeout_seconds(),",
            "            'summary': {},",
            "        })",
            "        return record",
            "    record.update({",
            "        'status': 'passed' if proc.returncode == 0 else 'failed',",
            "        'returncode': proc.returncode,",
            "        'command': command,",
            "        'stdout': _sanitize_diagnostic_text((proc.stdout or '').strip()),",
            "        'stderr': _sanitize_diagnostic_text((proc.stderr or '').strip()),",
            "    })",
            "    if result_path.exists():",
            "        payload = _load_json(result_path)",
            "        summary = _safe_summary(payload)",
            "        record.update({",
            "            'behavior_results_hash': _sha256_file(result_path),",
            "            'behavior_status': summary.get('status'),",
            "            'count': summary.get('total'),",
            "            'summary': _jsonable(summary),",
            "            'quality_evaluation': _quality_evaluation(payload),",
            "            'provider': _jsonable(payload.get('provider') if isinstance(payload.get('provider'), dict) else {}),"
            "        })",
            "    else:",
            "        record.update({'behavior_status': 'missing_results', 'summary': {}})",
            "    return record",
            "",
            "",
            "def _summary(sources: list[dict[str, object]]) -> dict[str, object]:",
            "    totals = {'total': 0, 'passed': 0, 'failed': 0, 'error': 0, 'degraded': 0}",
            "    status_counts: dict[str, int] = {}",
            "    for source in sources:",
            "        summary = source.get('summary') if isinstance(source.get('summary'), dict) else {}",
            "        status = str(summary.get('status') or source.get('behavior_status') or 'unknown')",
            "        status_counts[status] = status_counts.get(status, 0) + 1",
            "        for key in totals:",
            "            value = summary.get(key)",
            "            if isinstance(value, int):",
            "                totals[key] += value",
            "    if not sources:",
            "        aggregate_status = 'not_applicable'",
            "    elif any(source.get('status') == 'failed' for source in sources):",
            "        aggregate_status = 'failed'",
            "    elif totals['total'] == 0:",
            "        aggregate_status = 'no_examples'",
            "    elif totals['error'] == totals['total']:",
            "        aggregate_status = 'error'",
            "    elif totals['failed']:",
            "        aggregate_status = 'failed'",
            "    elif totals['degraded']:",
            "        aggregate_status = 'degraded'",
            "    elif totals['passed'] == totals['total']:",
            "        aggregate_status = 'passed'",
            "    else:",
            "        aggregate_status = 'executed'",
            "    return {'status': aggregate_status, 'source_count': len(sources), **totals, 'status_counts': status_counts}",
            "",
            "",
            "def _log_behavior_episode(payload: dict[str, Any], sources: list[dict[str, object]]) -> None:",
            "    try:",
            "        from dspx.tracing import get_mlflow",
            "",
            "        mlflow = get_mlflow()",
            "        if mlflow is None or mlflow.active_run() is None:",
            "            return",
            "        summary = payload.get('summary') if isinstance(payload.get('summary'), dict) else {}",
            "        for key in ('total', 'passed', 'failed', 'error', 'degraded', 'source_count'):",
            "            value = summary.get(key)",
            "            if isinstance(value, int):",
            "                try:",
            "                    mlflow.log_metric(f'program.behavior.{key}', float(value))",
            "                except Exception:",
            "                    pass",
            "        try:",
            "            mlflow.set_tag('program.behavior.status', str(payload.get('status') or 'unknown'))",
            "        except Exception:",
            "            pass",
            "        for path in [RESULT_PATH, *[Path(str(source.get('behavior_results_path'))) for source in sources]]:",
            "            if path.exists() and path.is_file():",
            "                try:",
            "                    mlflow.log_artifact(str(path))",
            "                except Exception:",
            "                    pass",
            "    except Exception:",
            "        return",
            "",
            "",
            "def main() -> None:",
            "    started_run = configure_observability(run_name='program-eval', run_kind='program-eval')",
            "    sources = [_run_source(dict(source)) for source in HARNESS_PLAN]",
            "    payload: dict[str, Any] = {",
            "        'schema_version': 'program-behavior-episode-v1',",
            "        'status': _summary(sources)['status'],",
            "        'sources': sources,",
            "        'summary': _summary(sources),",
            "        'quality_evaluation': _quality_summary(sources),",
            "        'authority': 'behavior_evidence_only_non_authoritative',"
            "        'non_authority': {'optimization_authority': False, 'promotion_authority': False, 'oracle_ranking': False, 'oracle_pruning': False, 'oracle_promotion': False, 'governance_authority': False, 'external_mutation': False, 'external_authority_mutated': False, 'winner_selection': False},",
            "    }",
            "    RESULT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')",
            "    try:",
            "        _log_behavior_episode(payload, sources)",
            "    finally:",
            "        end_observability_run(started_run)",
            "    print(f'program behavior episode ok: {len(sources)} source(s); status: {payload[\"status\"]}')",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )


def render_eval_jury() -> str:
    """Render a deterministic jury artifact binding validation harness."""

    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import json",
            "import sys",
            "from pathlib import Path",
            "",
            "",
            "def _sanitize_diagnostic_text(value: object, *, limit: int = 2000) -> str:",
            "    try:",
            "        from dspx.redaction import sanitize_diagnostic_text",
            "    except Exception:",
            "        text = '' if value is None else str(value)",
            "        return text[:limit]",
            "    return sanitize_diagnostic_text('' if value is None else str(value), limit=limit)",
            "",
            "",
            "def _load(name: str) -> dict[str, object]:",
            "    payload = json.loads(Path(name).read_text(encoding='utf-8'))",
            "    assert isinstance(payload, dict), f'{name} must contain an object'",
            "    return payload",
            "",
            "",
            "def main() -> None:",
            "    jury = _load('jury.json')",
            "    selection = _load('jury_selection.json')",
            "    rubric = _load('jury_rubric.json')",
            "    assert jury['schema_version'] == 'program-jury-v1'",
            "    assert selection['schema_version'] == 'program-jury-selection-v1'",
            "    assert rubric['schema_version'] == 'program-jury-rubric-v1'",
            "    selected = selection.get('selected_jurors')",
            "    rubrics = rubric.get('juror_rubrics')",
            "    assert isinstance(selected, list), f'selected_jurors must be a list: {selected}'",
            "    assert isinstance(rubrics, list), f'juror_rubrics must be a list: {rubrics}'",
            "    assert len(selected) == len(rubrics)",
            "    selected_ids = {item.get('id') for item in selected if isinstance(item, dict)}",
            "    rubric_ids = {item.get('juror_id') for item in rubrics if isinstance(item, dict)}",
            "    assert selected_ids == rubric_ids",
            "    assert selection['authority'] == 'selection_contract_only_non_authoritative'",
            "    assert rubric['authority'] == 'rubric_contract_only_non_authoritative'",
            "    print(f'program jury artifacts ok: {len(selected_ids)} selected juror(s)')",
            "",
            "",
            "def _main() -> int:",
            "    try:",
            "        main()",
            "    except Exception as exc:",
            "        print(_sanitize_diagnostic_text(exc), file=sys.stderr)",
            "        return 1",
            "    return 0",
            "",
            "",
            "if __name__ == '__main__':",
            "    raise SystemExit(_main())",
            "",
        ]
    )


def render_eval_promotion() -> str:
    """Render a deterministic promotion artifact binding validation harness."""

    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import json",
            "import sys",
            "from pathlib import Path",
            "",
            "",
            "def _sanitize_diagnostic_text(value: object, *, limit: int = 2000) -> str:",
            "    try:",
            "        from dspx.redaction import sanitize_diagnostic_text",
            "    except Exception:",
            "        text = '' if value is None else str(value)",
            "        return text[:limit]",
            "    return sanitize_diagnostic_text('' if value is None else str(value), limit=limit)",
            "",
            "",
            "def _load(name: str) -> dict[str, object]:",
            "    payload = json.loads(Path(name).read_text(encoding='utf-8'))",
            "    assert isinstance(payload, dict), f'{name} must contain an object'",
            "    return payload",
            "",
            "",
            "def main() -> None:",
            "    review = _load('promotion_review.json')",
            "    request = _load('promotion_adjudication_request.json')",
            "    decision_template = _load('promotion_decision_template.json')",
            "    assert review['schema_version'] == 'program-promotion-review-v1'",
            "    assert request['schema_version'] == 'program-promotion-adjudication-request-v1'",
            "    assert decision_template['schema_version'] == 'program-promotion-decision-v1'",
            "    assert review['promotion_state'] == 'not_promoted'",
            "    assert review['decision']['status'] == 'pending'",
            "    assert request['adjudicator'] == review['adjudicator']",
            "    assert request['external_authority'] == review['external_authority']",
            "    assert request['decision_record_template'] == decision_template",
            "    assert decision_template['status'] == 'pending'",
            "    assert decision_template['decided_by'] is None",
            "    assert request['authority'] == 'adjudication_request_only_non_authoritative'",
            "    blockers = review.get('blocking_conditions')",
            "    missing = request.get('missing_required_evidence')",
            "    assert isinstance(blockers, list), f'blocking_conditions must be a list: {blockers}'",
            "    assert isinstance(missing, list), f'missing_required_evidence must be a list: {missing}'",
            "    assert missing == blockers",
            "    if blockers:",
            "        assert request['status'] == 'not_ready_blocked'",
            "    assert review['non_authority']['automatic_promotion'] is False",
            "    assert review['non_authority']['ranking_pruning_promotion'] is False",
            "    assert review['non_authority']['external_authority_export'] is False",
            "    print(f'program promotion artifacts ok: {request[\"status\"]}')",
            "",
            "",
            "def _main() -> int:",
            "    try:",
            "        main()",
            "    except Exception as exc:",
            "        print(_sanitize_diagnostic_text(exc), file=sys.stderr)",
            "        return 1",
            "    return 0",
            "",
            "",
            "if __name__ == '__main__':",
            "    raise SystemExit(_main())",
            "",
        ]
    )
