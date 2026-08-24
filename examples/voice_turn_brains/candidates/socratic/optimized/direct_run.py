#!/usr/bin/env python3
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
PROTECTED_OUTPUT_BASENAMES = ('behavior_episode.json', 'behavior_results.json', 'behavior_results.test.json', 'behavior_results.train.json', 'behavior_results.validation.json', 'dataset_manifest.json', 'direct_run.py', 'direct_run_receipt.json', 'eval_behavior.py', 'eval_examples.py', 'eval_jury.py', 'eval_promotion.py', 'eval_smoke.py', 'eval_test.py', 'eval_train.py', 'eval_validation.py', 'examples.json', 'execution_episode.json', 'generated_module_policy.json', 'intent.json', 'intent_normalization.json', 'jury.json', 'jury_rubric.json', 'jury_selection.json', 'manifest.json', 'manifest.json.meta.json', 'module.py', 'module_surfaces.json', 'oracle_evidence.json', 'plan.json', 'program.py', 'program_capability_registry.json', 'program_runtime_outcomes.json', 'program_runtime_traces.json', 'program_tool_contracts.json', 'promotion_adjudication_request.json', 'promotion_decision_template.json', 'promotion_review.json', 'promotion_review_refined.json', 'signature.py')
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
        text = '\n'.join(text.splitlines()[1:-1]).strip()
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
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
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
                json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
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
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
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
