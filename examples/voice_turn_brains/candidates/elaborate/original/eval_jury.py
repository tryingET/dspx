from __future__ import annotations

import json
import sys
from pathlib import Path


def _sanitize_diagnostic_text(value: object, *, limit: int = 2000) -> str:
    try:
        from dspx.redaction import sanitize_diagnostic_text
    except Exception:
        text = '' if value is None else str(value)
        return text[:limit]
    return sanitize_diagnostic_text('' if value is None else str(value), limit=limit)


def _load(name: str) -> dict[str, object]:
    payload = json.loads(Path(name).read_text(encoding='utf-8'))
    assert isinstance(payload, dict), f'{name} must contain an object'
    return payload


def main() -> None:
    jury = _load('jury.json')
    selection = _load('jury_selection.json')
    rubric = _load('jury_rubric.json')
    assert jury['schema_version'] == 'program-jury-v1'
    assert selection['schema_version'] == 'program-jury-selection-v1'
    assert rubric['schema_version'] == 'program-jury-rubric-v1'
    selected = selection.get('selected_jurors')
    rubrics = rubric.get('juror_rubrics')
    assert isinstance(selected, list), f'selected_jurors must be a list: {selected}'
    assert isinstance(rubrics, list), f'juror_rubrics must be a list: {rubrics}'
    assert len(selected) == len(rubrics)
    selected_ids = {item.get('id') for item in selected if isinstance(item, dict)}
    rubric_ids = {item.get('juror_id') for item in rubrics if isinstance(item, dict)}
    assert selected_ids == rubric_ids
    assert selection['authority'] == 'selection_contract_only_non_authoritative'
    assert rubric['authority'] == 'rubric_contract_only_non_authoritative'
    print(f'program jury artifacts ok: {len(selected_ids)} selected juror(s)')


def _main() -> int:
    try:
        main()
    except Exception as exc:
        print(_sanitize_diagnostic_text(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(_main())
