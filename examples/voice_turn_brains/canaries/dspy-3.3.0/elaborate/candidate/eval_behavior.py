from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from program import configure_observability, end_observability_run
from dspx.services.program_quality_evaluation import evaluate_declared_quality

HARNESS_PLAN: list[dict[str, object]] = [{'kind': 'examples', 'source_kind': 'inline_examples', 'harness': 'eval_examples.py', 'result': 'behavior_results.json'}]
BOUND_QUALITY_CRITERIA: list[dict[str, object]] = []
QUALITY_CRITERIA_DECLARED = bool(BOUND_QUALITY_CRITERIA)
RESULT_PATH = Path('behavior_episode.json')


def _sanitize_diagnostic_text(value: object, *, limit: int = 2000) -> str:
    try:
        from dspx.redaction import sanitize_diagnostic_text
    except Exception:
        text = '' if value is None else str(value)
        return text[:limit]
    return sanitize_diagnostic_text('' if value is None else str(value), limit=limit)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert isinstance(payload, dict), f'{path} must contain a JSON object'
    return payload


def _safe_summary(payload: dict[str, object]) -> dict[str, object]:
    summary = payload.get('summary')
    return dict(summary) if isinstance(summary, dict) else {}


def _unevaluated_quality() -> dict[str, object]:
    return {'status': 'not_declared', 'criteria_declared': QUALITY_CRITERIA_DECLARED, 'evaluations_total': 0, 'evaluations_passed': 0, 'evaluations_failed': 0, 'quality_approved': False}


def _quality_evaluation(payload: dict[str, object]) -> dict[str, object]:
    quality = payload.get('quality_evaluation')
    assert isinstance(quality, dict), 'behavior results missing quality_evaluation'
    expected = {'status', 'criteria_declared', 'evaluations_total', 'evaluations_passed', 'evaluations_failed', 'quality_approved'}
    legacy = expected - {'criteria_declared'}
    assert set(quality) in (expected, legacy), 'behavior quality_evaluation has invalid fields'
    quality = dict(quality)
    intent = payload.get('intent') if isinstance(payload.get('intent'), dict) else {}
    assert intent.get('quality_criteria', []) == BOUND_QUALITY_CRITERIA, 'behavior quality criteria drift from candidate intent'
    quality.setdefault('criteria_declared', QUALITY_CRITERIA_DECLARED)
    status = quality.get('status')
    total = quality.get('evaluations_total')
    passed = quality.get('evaluations_passed')
    failed = quality.get('evaluations_failed')
    assert status in {'not_declared', 'passed', 'failed'}, 'behavior quality status is invalid'
    assert isinstance(quality.get('criteria_declared'), bool), 'behavior quality declaration flag is invalid'
    assert all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in (total, passed, failed)), 'behavior quality counts are invalid'
    assert passed + failed == total, 'behavior quality counts are inconsistent'
    assert quality.get('quality_approved') is False, 'behavior quality must remain non-authoritative'
    assert (status == 'not_declared') == (total == 0), 'behavior quality declaration status is inconsistent'
    assert status != 'passed' or failed == 0, 'passed behavior quality contains failures'
    assert status != 'failed' or failed > 0, 'failed behavior quality has no failures'
    records = payload.get('examples')
    assert isinstance(records, list), 'behavior results examples are missing'
    record_quality = [record.get('quality_evaluation') for record in records if isinstance(record, dict)]
    assert len(record_quality) == len(records) and all(isinstance(row, dict) for row in record_quality), 'behavior record quality evidence is malformed'
    assert all(row.get('status') in {'not_declared', 'passed', 'failed'} and row.get('quality_approved') is False for row in record_quality), 'behavior record quality evidence is invalid'
    criteria = BOUND_QUALITY_CRITERIA
    for record, row in zip(records, record_quality, strict=True):
        observed = record.get('observed_outputs') if isinstance(record, dict) and isinstance(record.get('observed_outputs'), dict) else {}
        assert row == evaluate_declared_quality(criteria, observed), 'behavior record quality drifts from observed outputs'
    declared_records = [row for row in record_quality if row.get('status') != 'not_declared']
    expected_passed = sum(row.get('status') == 'passed' for row in declared_records)
    intent = payload.get('intent') if isinstance(payload.get('intent'), dict) else {}
    expected_quality = {'status': 'not_declared' if not declared_records else ('passed' if expected_passed == len(declared_records) else 'failed'), 'criteria_declared': QUALITY_CRITERIA_DECLARED, 'evaluations_total': len(declared_records), 'evaluations_passed': expected_passed, 'evaluations_failed': len(declared_records) - expected_passed, 'quality_approved': False}
    assert quality == expected_quality, 'behavior quality summary drifts from records'
    return dict(quality)


def _quality_summary(sources: list[dict[str, object]]) -> dict[str, object]:
    rows = [source.get('quality_evaluation') for source in sources]
    assert all(isinstance(row, dict) for row in rows), 'behavior episode source missing quality_evaluation'
    declared = [row for row in rows if row.get('status') != 'not_declared']
    if not declared:
        return {'status': 'not_declared', 'criteria_declared': any(bool(row.get('criteria_declared')) for row in rows), 'evaluations_total': 0, 'evaluations_passed': 0, 'evaluations_failed': 0, 'quality_approved': False}
    total = sum(int(row['evaluations_total']) for row in declared)
    passed = sum(int(row['evaluations_passed']) for row in declared)
    failed = sum(int(row['evaluations_failed']) for row in declared)
    return {'status': 'failed' if failed else 'passed', 'criteria_declared': True, 'evaluations_total': total, 'evaluations_passed': passed, 'evaluations_failed': failed, 'quality_approved': False}


def _harness_timeout_seconds() -> float:
    raw = os.getenv('DSPX_PROGRAM_HARNESS_TIMEOUT', '60')
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


def _run_source(source: dict[str, object]) -> dict[str, object]:
    harness_path = Path(str(source['harness']))
    result_path = Path(str(source['result']))
    record: dict[str, object] = {
        'kind': source.get('kind'),
        'source_kind': source.get('source_kind'),
        'split': source.get('split'),
        'harness_path': str(harness_path),
        'behavior_results_path': str(result_path),
        'quality_evaluation': _unevaluated_quality(),
    }
    if not harness_path.exists():
        record.update({'status': 'missing_harness', 'returncode': None, 'summary': {}})
        return record
    if result_path.exists():
        try:
            if not result_path.is_file() and not result_path.is_symlink():
                record.update({'status': 'stale_result_not_file', 'returncode': None, 'summary': {}})
                return record
            result_path.unlink()
        except Exception as exc:
            record.update({
                'status': 'stale_result_cleanup_failed',
                'returncode': None,
                'summary': {},
                'error': {'type': type(exc).__name__, 'message': _sanitize_diagnostic_text(exc)},
            })
            return record
    command = [sys.executable, str(harness_path)]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=_harness_timeout_seconds())
    except subprocess.TimeoutExpired as exc:
        record.update({
            'status': 'timeout',
            'returncode': None,
            'command': command,
            'stdout': _sanitize_diagnostic_text((exc.stdout or '').strip()) if isinstance(exc.stdout, str) else '',
            'stderr': _sanitize_diagnostic_text((exc.stderr or '').strip()) if isinstance(exc.stderr, str) else '',
            'timeout_seconds': _harness_timeout_seconds(),
            'summary': {},
        })
        return record
    record.update({
        'status': 'passed' if proc.returncode == 0 else 'failed',
        'returncode': proc.returncode,
        'command': command,
        'stdout': _sanitize_diagnostic_text((proc.stdout or '').strip()),
        'stderr': _sanitize_diagnostic_text((proc.stderr or '').strip()),
    })
    if result_path.exists():
        payload = _load_json(result_path)
        summary = _safe_summary(payload)
        record.update({
            'behavior_results_hash': _sha256_file(result_path),
            'behavior_status': summary.get('status'),
            'count': summary.get('total'),
            'summary': _jsonable(summary),
            'quality_evaluation': _quality_evaluation(payload),
            'provider': _jsonable(payload.get('provider') if isinstance(payload.get('provider'), dict) else {}),        })
    else:
        record.update({'behavior_status': 'missing_results', 'summary': {}})
    return record


def _summary(sources: list[dict[str, object]]) -> dict[str, object]:
    totals = {'total': 0, 'passed': 0, 'failed': 0, 'error': 0, 'degraded': 0}
    status_counts: dict[str, int] = {}
    for source in sources:
        summary = source.get('summary') if isinstance(source.get('summary'), dict) else {}
        status = str(summary.get('status') or source.get('behavior_status') or 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
        for key in totals:
            value = summary.get(key)
            if isinstance(value, int):
                totals[key] += value
    if not sources:
        aggregate_status = 'not_applicable'
    elif any(source.get('status') == 'failed' for source in sources):
        aggregate_status = 'failed'
    elif totals['total'] == 0:
        aggregate_status = 'no_examples'
    elif totals['error'] == totals['total']:
        aggregate_status = 'error'
    elif totals['failed']:
        aggregate_status = 'failed'
    elif totals['degraded']:
        aggregate_status = 'degraded'
    elif totals['passed'] == totals['total']:
        aggregate_status = 'passed'
    else:
        aggregate_status = 'executed'
    return {'status': aggregate_status, 'source_count': len(sources), **totals, 'status_counts': status_counts}


def _log_behavior_episode(payload: dict[str, Any], sources: list[dict[str, object]]) -> None:
    try:
        from dspx.tracing import get_mlflow

        mlflow = get_mlflow()
        if mlflow is None or mlflow.active_run() is None:
            return
        summary = payload.get('summary') if isinstance(payload.get('summary'), dict) else {}
        for key in ('total', 'passed', 'failed', 'error', 'degraded', 'source_count'):
            value = summary.get(key)
            if isinstance(value, int):
                try:
                    mlflow.log_metric(f'program.behavior.{key}', float(value))
                except Exception:
                    pass
        try:
            mlflow.set_tag('program.behavior.status', str(payload.get('status') or 'unknown'))
        except Exception:
            pass
        for path in [RESULT_PATH, *[Path(str(source.get('behavior_results_path'))) for source in sources]]:
            if path.exists() and path.is_file():
                try:
                    mlflow.log_artifact(str(path))
                except Exception:
                    pass
    except Exception:
        return


def main() -> None:
    started_run = configure_observability(run_name='program-eval', run_kind='program-eval')
    sources = [_run_source(dict(source)) for source in HARNESS_PLAN]
    payload: dict[str, Any] = {
        'schema_version': 'program-behavior-episode-v1',
        'status': _summary(sources)['status'],
        'sources': sources,
        'summary': _summary(sources),
        'quality_evaluation': _quality_summary(sources),
        'authority': 'behavior_evidence_only_non_authoritative',        'non_authority': {'optimization_authority': False, 'promotion_authority': False, 'oracle_ranking': False, 'oracle_pruning': False, 'oracle_promotion': False, 'governance_authority': False, 'external_mutation': False, 'external_authority_mutated': False, 'winner_selection': False},
    }
    RESULT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    try:
        _log_behavior_episode(payload, sources)
    finally:
        end_observability_run(started_run)
    print(f'program behavior episode ok: {len(sources)} source(s); status: {payload["status"]}')


if __name__ == '__main__':
    main()
