from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES


def _iter_path_values(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if (
                (key_text == "path" or key_text.endswith("_path"))
                and isinstance(item, str)
                and item.strip()
            ):
                yield item
            else:
                yield from _iter_path_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_path_values(item)


def protected_paths_from_payload(payload: Mapping[str, Any]) -> set[Path]:
    """Return resolved input/control paths declared by a sidecar payload."""

    paths: set[Path] = set()
    for raw_path in _iter_path_values(payload):
        try:
            paths.add(Path(raw_path).expanduser().resolve())
        except (OSError, RuntimeError, ValueError):
            continue
    return paths


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def prepare_sidecar_output_path(
    out_path: Path,
    *,
    payload: Mapping[str, Any],
    artifact_label: str,
    protected_names: Iterable[str] = PROTECTED_PROGRAM_ARTIFACT_NAMES,
    extra_protected_paths: Iterable[Path] = (),
    extra_protected_roots: Iterable[Path] = (),
) -> Path:
    """Resolve and validate a local sidecar output path before writing.

    Sidecars summarize or adjudicate generated artifacts. They must not overwrite
    producer/control artifacts, any input path recorded in their own payload, or
    arbitrary files inside protected generated-artifact roots.
    """

    resolved = out_path.expanduser().resolve()
    protected_name_set = {str(name) for name in protected_names}
    if resolved.name in protected_name_set:
        raise ValueError(f"{artifact_label} must not overwrite {resolved.name}")

    protected_paths = protected_paths_from_payload(payload)
    protected_paths.update(
        path.expanduser().resolve() for path in extra_protected_paths
    )
    if resolved in protected_paths:
        raise ValueError(
            f"{artifact_label} output must not overwrite an input artifact: {resolved}"
        )

    for root in extra_protected_roots:
        protected_root = root.expanduser().resolve()
        if resolved == protected_root or _is_relative_to(resolved, protected_root):
            raise ValueError(
                f"{artifact_label} output must not be written inside a protected artifact root: {protected_root}"
            )

    return resolved
