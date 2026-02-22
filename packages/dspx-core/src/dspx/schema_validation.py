"""Schema validation utilities for DSPx configuration files.

Provides validation of YAML config files against JSON schemas with
line-number error messages for better DX.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

# Schema paths relative to package root
_SCHEMA_DIR = Path(__file__).parent.parent.parent.parent.parent / "docs" / "schemas"


class SchemaValidationError(Exception):
    """Raised when schema validation fails with line-number context."""

    def __init__(self, message: str, errors: list[dict[str, Any]]) -> None:
        self.message = message
        self.errors = errors
        super().__init__(message)

    def __str__(self) -> str:
        lines = [self.message]
        for err in self.errors:
            loc = err.get("location", "unknown")
            msg = err.get("message", "unknown error")
            lines.append(f"  - {loc}: {msg}")
        return "\n".join(lines)


def _get_schema_path(schema_name: str) -> Path:
    """Get the path to a schema file."""
    return _SCHEMA_DIR / f"{schema_name}.schema.json"


def _load_schema(schema_name: str) -> dict[str, Any]:
    """Load a JSON schema by name."""
    schema_path = _get_schema_path(schema_name)
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


def _yaml_load_with_marks(source: str | Path) -> tuple[Any, dict[int, yaml.Mark]]:
    """Load YAML and return a mapping of line numbers to marks.

    Returns:
        Tuple of (parsed_data, line_to_mark_map)
    """
    if isinstance(source, Path):
        content = source.read_text(encoding="utf-8")
    else:
        content = source

    # Track marks for each node
    marks: dict[int, yaml.Mark] = {}

    class MarkingLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict:
        mapping = loader.construct_mapping(node, deep=True)
        if node.start_mark:
            marks[id(mapping)] = node.start_mark
        return mapping

    def construct_sequence(loader: yaml.SafeLoader, node: yaml.SequenceNode) -> list:
        seq = loader.construct_sequence(node, deep=True)
        if node.start_mark:
            marks[id(seq)] = node.start_mark
        return seq

    def construct_scalar(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> Any:
        value = loader.construct_scalar(node)
        if node.start_mark:
            marks[id(value)] = node.start_mark
        return value

    MarkingLoader.add_constructor(
        "tag:yaml.org,2002:map",
        construct_mapping,
    )
    MarkingLoader.add_constructor(
        "tag:yaml.org,2002:seq",
        construct_sequence,
    )
    MarkingLoader.add_constructor(
        "tag:yaml.org,2002:str",
        construct_scalar,
    )

    data = yaml.load(content, Loader=MarkingLoader)
    return data, marks


def _format_validation_errors(
    error: jsonschema.ValidationError,
    yaml_content: str,
    marks: dict[int, yaml.Mark],
) -> list[dict[str, Any]]:
    """Format validation errors with line numbers."""
    errors = []

    # Get the failing path
    path = list(error.absolute_path)
    path_str = ".".join(str(p) for p in path) if path else "root"

    # Try to find line number from YAML content
    line_hint = None

    # Simple heuristic: search for the key in the path
    if path:
        key = str(path[-1])
        for i, line in enumerate(yaml_content.splitlines(), 1):
            if key in line and ":" in line:
                line_hint = i
                break

    location = f"line {line_hint}" if line_hint else path_str

    errors.append(
        {
            "location": location,
            "path": path_str,
            "message": error.message,
            "validator": error.validator,
            "expected": (
                error.schema.get("enum")
                if error.validator == "enum" and isinstance(error.schema, dict)
                else None
            ),
        }
    )

    # Add context errors
    for ctx in error.context or []:
        ctx_path = list(ctx.absolute_path)
        ctx_path_str = ".".join(str(p) for p in ctx_path) if ctx_path else "root"
        errors.append(
            {
                "location": ctx_path_str,
                "path": ctx_path_str,
                "message": ctx.message,
                "validator": ctx.validator,
            }
        )

    return errors


def validate_yaml_config(
    source: str | Path,
    schema_name: str = "template-adapter-config",
) -> dict[str, Any]:
    """Validate a YAML config file against a JSON schema.

    Args:
        source: Path to YAML file or YAML string content
        schema_name: Name of schema (without .schema.json extension)

    Returns:
        Parsed and validated config data

    Raises:
        SchemaValidationError: If validation fails with line-number context
        FileNotFoundError: If schema file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    # Load YAML content
    if isinstance(source, Path):
        yaml_content = source.read_text(encoding="utf-8")
    else:
        yaml_content = source

    # Parse YAML with marks
    data, marks = _yaml_load_with_marks(yaml_content)

    # Load schema
    schema = _load_schema(schema_name)

    # Validate
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))

    if errors:
        formatted_errors = []
        for err in errors:
            formatted_errors.extend(_format_validation_errors(err, yaml_content, marks))

        raise SchemaValidationError(
            f"Config validation failed against {schema_name}",
            formatted_errors,
        )

    return data


def validate_template_adapter_config(source: str | Path) -> dict[str, Any]:
    """Validate a template adapter config file.

    Convenience wrapper for validate_yaml_config with the default schema.

    Args:
        source: Path to YAML file or YAML string content

    Returns:
        Parsed and validated config data

    Raises:
        SchemaValidationError: If validation fails
    """
    return validate_yaml_config(source, "template-adapter-config")
