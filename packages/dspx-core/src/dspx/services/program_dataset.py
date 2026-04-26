from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, Mapping
import hashlib

import yaml

SPLIT_NAMES = ("train", "validation", "test")
PROGRAM_DATASET_MANIFEST_SCHEMA = "program-dataset-manifest-v1"
DATASET_AUTHORITY = "dataset_split_evidence_only_non_authoritative"
DATASET_NON_AUTHORITY = {
    "optimization_authority": False,
    "promotion_authority": False,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "governance_authority": False,
    "external_mutation": False,
}


class ProgramDatasetError(ValueError):
    """Raised when program intent dataset declarations are invalid."""


def has_program_dataset(intent: Any) -> bool:
    return bool(getattr(intent, "dataset", {}) or getattr(intent, "datasets", {}))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _resolve_source_path(raw_path: object, *, intent_source: Path | None) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        raise ProgramDatasetError("program dataset path must not be blank")
    path = Path(text).expanduser()
    if not path.is_absolute() and intent_source is not None:
        path = intent_source.expanduser().resolve().parent / path
    return path.resolve()


def _load_json_or_yaml_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProgramDatasetError(
                    f"program dataset JSONL row {line_number} must be valid JSON"
                ) from exc
            if not isinstance(payload, Mapping):
                raise ProgramDatasetError(
                    f"program dataset JSONL row {line_number} must be an object"
                )
            records.append(dict(payload))
        return records

    text = path.read_text(encoding="utf-8")
    try:
        if suffix == ".json":
            payload = json.loads(text)
        else:
            payload = yaml.safe_load(text)
    except Exception as exc:
        raise ProgramDatasetError(
            f"program dataset file must be valid JSON/YAML: {path}"
        ) from exc
    if not isinstance(payload, list) or not all(
        isinstance(item, Mapping) for item in payload
    ):
        raise ProgramDatasetError(
            "program dataset JSON/YAML file must contain a list of objects"
        )
    return [dict(item) for item in payload]


def _validate_record_fields(
    records: list[dict[str, Any]], *, input_fields: list[str], output_fields: list[str]
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        raw_inputs = record.get("inputs")
        raw_outputs = record.get("outputs")
        if not isinstance(raw_inputs, Mapping):
            raise ProgramDatasetError(
                f"program dataset record {index} missing object inputs"
            )
        if not isinstance(raw_outputs, Mapping):
            raise ProgramDatasetError(
                f"program dataset record {index} missing object outputs"
            )
        inputs = dict(raw_inputs)
        outputs = dict(raw_outputs)
        missing_inputs = [name for name in input_fields if name not in inputs]
        missing_outputs = [name for name in output_fields if name not in outputs]
        unknown_inputs = sorted(set(str(key) for key in inputs) - set(input_fields))
        unknown_outputs = sorted(set(str(key) for key in outputs) - set(output_fields))
        if missing_inputs:
            raise ProgramDatasetError(
                f"program dataset record {index} missing input fields: {missing_inputs}"
            )
        if missing_outputs:
            raise ProgramDatasetError(
                f"program dataset record {index} missing output fields: {missing_outputs}"
            )
        if unknown_inputs:
            raise ProgramDatasetError(
                f"program dataset record {index} has unknown input fields: {unknown_inputs}"
            )
        if unknown_outputs:
            raise ProgramDatasetError(
                f"program dataset record {index} has unknown output fields: {unknown_outputs}"
            )
        normalized.append({"inputs": inputs, "outputs": outputs})
    return normalized


def _ratio_config(dataset: Mapping[str, Any]) -> tuple[float, float, float, int]:
    split = dataset.get("split")
    if not isinstance(split, Mapping):
        raise ProgramDatasetError("program dataset.split must be an object")
    strategy = str(split.get("strategy") or "").strip()
    if strategy != "ratio":
        raise ProgramDatasetError("program dataset.split.strategy must be 'ratio'")
    train = float(split.get("train"))
    validation = float(split.get("validation"))
    test = float(split.get("test"))
    if any(value < 0.0 or value > 1.0 for value in (train, validation, test)):
        raise ProgramDatasetError(
            "program dataset split ratios must be between 0 and 1"
        )
    if not math.isclose(train + validation + test, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ProgramDatasetError("program dataset split ratios must sum to 1.0")
    seed = int(split.get("seed", 42))
    return train, validation, test, seed


def _split_ratio(
    records: list[dict[str, Any]], *, ratios: tuple[float, float, float], seed: int
) -> dict[str, list[dict[str, Any]]]:
    idxs = list(range(len(records)))
    rnd = random.Random(seed)
    rnd.shuffle(idxs)
    n = len(records)
    train_count = math.floor(n * ratios[0])
    validation_count = math.floor(n * ratios[1])
    test_count = n - train_count - validation_count
    assignments = {
        "train": idxs[:train_count],
        "validation": idxs[train_count : train_count + validation_count],
        "test": idxs[
            train_count + validation_count : train_count + validation_count + test_count
        ],
    }
    return {
        split: [records[index] for index in indices]
        for split, indices in assignments.items()
    }


def _compact_jsonl(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    return "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for record in records
    )


def _write_split_files(
    root: Path, split_records: Mapping[str, list[dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    splits_dir = root / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {}
    for split in SPLIT_NAMES:
        relative = Path("splits") / f"{split}.jsonl"
        path = root / relative
        path.write_text(_compact_jsonl(split_records.get(split, [])), encoding="utf-8")
        artifacts[split] = {
            "path": str(relative),
            "content_hash": _sha256_file(path),
            "record_count": len(split_records.get(split, [])),
            "eval_harness": f"eval_{split}.py",
            "behavior_results": f"behavior_results.{split}.json",
        }
    return artifacts


def _dataset_fields_from_ratio(
    intent: Any, dataset: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    input_fields = [
        str(item) for item in dataset.get("input_fields") or [] if str(item).strip()
    ]
    output_fields = [
        str(item) for item in dataset.get("output_fields") or [] if str(item).strip()
    ]
    if not input_fields:
        input_fields = [str(item) for item in getattr(intent, "inputs", [])]
    if not output_fields:
        output_fields = [str(item) for item in getattr(intent, "outputs", [])]
    if not input_fields or not output_fields:
        raise ProgramDatasetError(
            "program dataset must declare input and output fields"
        )
    return input_fields, output_fields


def materialize_program_dataset_splits(
    intent: Any, *, root: Path, intent_source: Path | None
) -> dict[str, Any] | None:
    """Materialize declared program dataset split files and return manifest facts.

    This writes only local split JSONL files under the generated program root. It
    does not run evaluation harnesses; callers add harness/result hashes after
    harness execution with ``finalize_program_dataset_manifest``.
    """

    dataset = dict(getattr(intent, "dataset", {}) or {})
    datasets = dict(getattr(intent, "datasets", {}) or {})
    if dataset and datasets:
        raise ProgramDatasetError(
            "program intent must declare either dataset or datasets, not both"
        )
    if not dataset and not datasets:
        return None

    if dataset:
        source_path = _resolve_source_path(
            dataset.get("path"), intent_source=intent_source
        )
        input_fields, output_fields = _dataset_fields_from_ratio(intent, dataset)
        records = _validate_record_fields(
            _load_json_or_yaml_records(source_path),
            input_fields=input_fields,
            output_fields=output_fields,
        )
        train_ratio, validation_ratio, test_ratio, seed = _ratio_config(dataset)
        split_records = _split_ratio(
            records,
            ratios=(train_ratio, validation_ratio, test_ratio),
            seed=seed,
        )
        artifacts = _write_split_files(root, split_records)
        return {
            "schema_version": PROGRAM_DATASET_MANIFEST_SCHEMA,
            "status": "materialized",
            "source": {
                "kind": "dataset_path",
                "path": str(dataset.get("path")),
                "resolved_path": str(source_path),
                "content_hash": _sha256_file(source_path),
                "record_count": len(records),
            },
            "split": {
                "strategy": "ratio",
                "seed": seed,
                "ratios": {
                    "train": train_ratio,
                    "validation": validation_ratio,
                    "test": test_ratio,
                },
                "counts": {
                    split: artifacts[split]["record_count"] for split in SPLIT_NAMES
                },
            },
            "fields": {"inputs": input_fields, "outputs": output_fields},
            "artifacts": artifacts,
            "authority": DATASET_AUTHORITY,
            "non_authority": dict(DATASET_NON_AUTHORITY),
        }

    missing = [
        split for split in SPLIT_NAMES if not str(datasets.get(split) or "").strip()
    ]
    if missing:
        raise ProgramDatasetError(
            "program datasets must declare train, validation, and test paths; missing: "
            + ", ".join(missing)
        )
    input_fields = [str(item) for item in getattr(intent, "inputs", [])]
    output_fields = [str(item) for item in getattr(intent, "outputs", [])]
    source_files: dict[str, dict[str, Any]] = {}
    split_records: dict[str, list[dict[str, Any]]] = {}
    for split in SPLIT_NAMES:
        source_path = _resolve_source_path(datasets[split], intent_source=intent_source)
        records = _validate_record_fields(
            _load_json_or_yaml_records(source_path),
            input_fields=input_fields,
            output_fields=output_fields,
        )
        source_files[split] = {
            "path": str(datasets[split]),
            "resolved_path": str(source_path),
            "content_hash": _sha256_file(source_path),
            "record_count": len(records),
        }
        split_records[split] = records
    artifacts = _write_split_files(root, split_records)
    return {
        "schema_version": PROGRAM_DATASET_MANIFEST_SCHEMA,
        "status": "materialized",
        "source": {
            "kind": "explicit_splits",
            "splits": source_files,
            "record_count": sum(item["record_count"] for item in source_files.values()),
        },
        "split": {
            "strategy": "explicit_splits",
            "counts": {
                split: artifacts[split]["record_count"] for split in SPLIT_NAMES
            },
        },
        "fields": {"inputs": input_fields, "outputs": output_fields},
        "artifacts": artifacts,
        "authority": DATASET_AUTHORITY,
        "non_authority": dict(DATASET_NON_AUTHORITY),
    }


def finalize_program_dataset_manifest(
    payload: Mapping[str, Any], *, root: Path
) -> tuple[dict[str, Any], str]:
    manifest = dict(payload)
    artifacts = {
        split: dict(raw) for split, raw in dict(manifest.get("artifacts") or {}).items()
    }
    for split, artifact in artifacts.items():
        eval_path = root / str(artifact.get("eval_harness") or f"eval_{split}.py")
        behavior_path = root / str(
            artifact.get("behavior_results") or f"behavior_results.{split}.json"
        )
        artifact["eval_harness_hash"] = _sha256_file(eval_path)
        artifact["behavior_results_hash"] = _sha256_file(behavior_path)
    manifest["artifacts"] = artifacts
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    path = root / "dataset_manifest.json"
    path.write_text(text, encoding="utf-8")
    return manifest, hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_dataset_split_eval_harness(split: str) -> str:
    result_name = f"behavior_results.{split}.json"
    split_path = f"splits/{split}.jsonl"
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import json",
            "from pathlib import Path",
            "from typing import Any",
            "",
            "from program import build_program, intent_summary, io_spec, normalize_output",
            "",
            f"DATASET_SPLIT = {split!r}",
            f"SPLIT_PATH = Path({split_path!r})",
            f"RESULT_PATH = Path({result_name!r})",
            "DATASET_MANIFEST_PATH = 'dataset_manifest.json'",
            "",
            "",
            "def _load_jsonl(path: Path) -> list[dict[str, object]]:",
            "    records: list[dict[str, object]] = []",
            "    if not path.exists():",
            "        raise FileNotFoundError(path)",
            "    for line in path.read_text(encoding='utf-8').splitlines():",
            "        text = line.strip()",
            "        if not text:",
            "            continue",
            "        payload = json.loads(text)",
            "        assert isinstance(payload, dict), 'dataset split rows must be objects'",
            "        records.append(payload)",
            "    return records",
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
            "def _status_for(outputs: list[str], expected: dict[str, object], observed: dict[str, object], prediction: object) -> tuple[str, list[str]]:",
            "    comparable = [name for name in outputs if name in observed]",
            "    if not comparable:",
            "        return 'degraded_no_comparable_output', ['no declared outputs were observable']",
            "    failures: list[str] = []",
            "    for name in comparable:",
            "        gold, pred = normalize_output(name, str(expected.get(name, '')), str(observed.get(name, '')), pred_trace=prediction)",
            "        if gold != pred:",
            "            failures.append(name)",
            "    if failures:",
            "        return 'failed', [f'output mismatch: {failures}']",
            "    if len(comparable) != len(outputs):",
            "        missing = [name for name in outputs if name not in observed]",
            "        return 'executed', [f'missing non-compared outputs: {missing}']",
            "    return 'passed', []",
            "",
            "",
            "def _summary(records: list[dict[str, object]]) -> dict[str, object]:",
            "    if not records:",
            "        return {'total': 0, 'passed': 0, 'failed': 0, 'error': 0, 'degraded': 0, 'status_counts': {}, 'status': 'no_examples'}",
            "    statuses = [str(record.get('status') or 'unknown') for record in records]",
            "    counts = {status: statuses.count(status) for status in sorted(set(statuses))}",
            "    error_count = sum(1 for status in statuses if status == 'error')",
            "    failed_count = sum(1 for status in statuses if status == 'failed')",
            "    degraded_count = sum(1 for status in statuses if status.startswith('degraded'))",
            "    passed_count = sum(1 for status in statuses if status == 'passed')",
            "    if passed_count == len(records):",
            "        episode_status = 'passed'",
            "    elif error_count == len(records):",
            "        episode_status = 'error'",
            "    elif failed_count:",
            "        episode_status = 'failed'",
            "    elif degraded_count:",
            "        episode_status = 'degraded'",
            "    else:",
            "        episode_status = 'executed'",
            "    return {'total': len(records), 'passed': passed_count, 'failed': failed_count, 'error': error_count, 'degraded': degraded_count, 'status_counts': counts, 'status': episode_status}",
            "",
            "",
            "def _configure_provider() -> dict[str, object]:",
            "    try:",
            "        import dspy",
            "        from dspx.provider_registry import create_from_env, ensure_default_providers",
            "        ensure_default_providers()",
            "        lm = create_from_env(default='stub')",
            "        dspy.configure(lm=lm)",
            "        return {'status': 'configured', 'provider': getattr(lm, 'model', type(lm).__name__)}",
            "    except Exception as exc:",
            "        return {'status': 'unavailable', 'error': {'type': type(exc).__name__, 'message': str(exc)}}",
            "",
            "",
            "def main() -> None:",
            "    examples = _load_jsonl(SPLIT_PATH)",
            "    spec = io_spec()",
            "    inputs = list(spec['inputs'])",
            "    outputs = list(spec['outputs'])",
            "    provider = _configure_provider()",
            "    program = build_program() if examples else None",
            "    records: list[dict[str, object]] = []",
            "    for index, example in enumerate(examples):",
            "        input_values = example.get('inputs')",
            "        output_values = example.get('outputs')",
            "        assert isinstance(input_values, dict), f'dataset split example {index} missing inputs object'",
            "        assert isinstance(output_values, dict), f'dataset split example {index} missing outputs object'",
            "        record: dict[str, object] = {'index': index, 'inputs': _jsonable(input_values), 'expected_outputs': _jsonable(output_values)}",
            "        try:",
            "            assert program is not None",
            "            prediction = program(**{name: input_values[name] for name in inputs})",
            "            observed, notes = _observed_outputs(prediction, outputs)",
            "            status, status_notes = _status_for(outputs, output_values, observed, prediction)",
            "            record.update({'status': status, 'observed_outputs': _jsonable(observed), 'notes': notes + status_notes})",
            "        except Exception as exc:",
            "            record.update({'status': 'error', 'observed_outputs': {}, 'error': {'type': type(exc).__name__, 'message': str(exc)}})",
            "        records.append(record)",
            "    payload: dict[str, Any] = {",
            "        'schema_version': 'program-behavior-results-v1',",
            "        'dataset_split': DATASET_SPLIT,",
            "        'dataset_manifest_path': DATASET_MANIFEST_PATH,",
            "        'source_split_path': str(SPLIT_PATH),",
            "        'intent': intent_summary(),",
            "        'intent_name': intent_summary().get('name'),",
            "        'input_fields': inputs,",
            "        'output_fields': outputs,",
            "        'provider': provider,",
            "        'examples': records,",
            "        'summary': _summary(records),",
            "        'authority': 'behavior_evidence_only_non_authoritative',",
            "        'non_authority': {'optimization_authority': False, 'promotion_authority': False, 'oracle_ranking': False, 'oracle_pruning': False, 'oracle_promotion': False, 'governance_authority': False, 'external_mutation': False},",
            "    }",
            "    RESULT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')",
            '    print(f\'program dataset split {DATASET_SPLIT} ok: {len(examples)} example(s); behavior status: {payload["summary"]["status"]}\')',
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )
