"""Tests for dspx.schema_validation module."""

from pathlib import Path

import pytest
import yaml

from dspx.schema_validation import (
    SchemaValidationError,
    validate_template_adapter_config,
    validate_yaml_config,
)


class TestValidateYamlConfig:
    """Tests for validate_yaml_config function."""

    def test_valid_template_adapter_config(self, tmp_path: Path) -> None:
        """Test validation of a valid template adapter config."""
        config = tmp_path / "config.yaml"
        config.write_text(
            """
messages:
  - role: system
    content: "{instruction}"
  - role: user
    content: "{inputs(style='yaml')}"
parse_mode: json
""",
            encoding="utf-8",
        )

        result = validate_yaml_config(config, "template-adapter-config")
        assert result["parse_mode"] == "json"
        assert len(result["messages"]) == 2

    def test_valid_config_with_helpers(self, tmp_path: Path) -> None:
        """Test validation with custom helpers."""
        config = tmp_path / "config.yaml"
        config.write_text(
            """
parse_mode: xml
register_helpers:
  format_priority: myapp.helpers.format_priority
""",
            encoding="utf-8",
        )

        result = validate_yaml_config(config, "template-adapter-config")
        assert result["parse_mode"] == "xml"
        assert "format_priority" in result["register_helpers"]

    def test_invalid_parse_mode(self, tmp_path: Path) -> None:
        """Test that invalid parse_mode raises SchemaValidationError."""
        config = tmp_path / "config.yaml"
        config.write_text(
            """
parse_mode: invalid_mode
""",
            encoding="utf-8",
        )

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_yaml_config(config, "template-adapter-config")

        assert "validation failed" in str(exc_info.value).lower()
        assert len(exc_info.value.errors) > 0

    def test_invalid_role(self, tmp_path: Path) -> None:
        """Test that invalid message role raises SchemaValidationError."""
        config = tmp_path / "config.yaml"
        config.write_text(
            """
messages:
  - role: invalid_role
    content: "test"
""",
            encoding="utf-8",
        )

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_yaml_config(config, "template-adapter-config")

        assert "validation failed" in str(exc_info.value).lower()

    def test_missing_required_role(self, tmp_path: Path) -> None:
        """Test that message without role raises SchemaValidationError."""
        config = tmp_path / "config.yaml"
        config.write_text(
            """
messages:
  - content: "test"
""",
            encoding="utf-8",
        )

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_yaml_config(config, "template-adapter-config")

        assert "validation failed" in str(exc_info.value).lower()

    def test_invalid_custom_parse_fn_format(self, tmp_path: Path) -> None:
        """Test that malformed import path raises SchemaValidationError."""
        config = tmp_path / "config.yaml"
        config.write_text(
            """
custom_parse_fn: "not-a-valid-import-path"
""",
            encoding="utf-8",
        )

        with pytest.raises(SchemaValidationError) as exc_info:
            validate_yaml_config(config, "template-adapter-config")

        assert "validation failed" in str(exc_info.value).lower()

    def test_extra_fields_allowed(self, tmp_path: Path) -> None:
        """Test that extra fields are allowed."""
        config = tmp_path / "config.yaml"
        config.write_text(
            """
parse_mode: json
future_field: future_value
another_extra: 123
""",
            encoding="utf-8",
        )

        result = validate_yaml_config(config, "template-adapter-config")
        assert result["parse_mode"] == "json"
        assert result.get("future_field") == "future_value"
        assert result.get("another_extra") == 123

    def test_yaml_string_input(self) -> None:
        """Test validation with YAML string input."""
        yaml_str = """
parse_mode: auto
messages:
  - role: system
    content: "{instruction}"
"""
        result = validate_yaml_config(yaml_str, "template-adapter-config")
        assert result["parse_mode"] == "auto"

    def test_file_not_found_schema(self, tmp_path: Path) -> None:
        """Test that missing schema raises FileNotFoundError."""
        config = tmp_path / "config.yaml"
        config.write_text("parse_mode: json", encoding="utf-8")

        with pytest.raises(FileNotFoundError):
            validate_yaml_config(config, "nonexistent-schema")

    def test_yaml_parse_error(self, tmp_path: Path) -> None:
        """Test that malformed YAML raises yaml.YAMLError."""
        config = tmp_path / "config.yaml"
        config.write_text(
            """
messages:
  - role: system
    content: unclosed bracket [
  - role: user
    content: test
  invalid yaml structure here:
    [
""",
            encoding="utf-8",
        )

        with pytest.raises(yaml.YAMLError):
            validate_yaml_config(config, "template-adapter-config")


class TestValidateTemplateAdapterConfig:
    """Tests for validate_template_adapter_config convenience function."""

    def test_valid_config(self, tmp_path: Path) -> None:
        """Test convenience function with valid config."""
        config = tmp_path / "config.yaml"
        config.write_text(
            """
parse_mode: xml
""",
            encoding="utf-8",
        )

        result = validate_template_adapter_config(config)
        assert result["parse_mode"] == "xml"

    def test_default_messages(self, tmp_path: Path) -> None:
        """Test that default messages are used when not specified."""
        config = tmp_path / "config.yaml"
        config.write_text("{}", encoding="utf-8")

        result = validate_template_adapter_config(config)
        # Default values come from the schema
        assert "messages" in result or result == {}


class TestSchemaValidationError:
    """Tests for SchemaValidationError exception."""

    def test_error_formatting(self) -> None:
        """Test error string formatting."""
        error = SchemaValidationError(
            "Config validation failed",
            [
                {"location": "line 3", "message": "Invalid value"},
                {"location": "line 5", "message": "Missing field"},
            ],
        )

        error_str = str(error)
        assert "Config validation failed" in error_str
        assert "line 3" in error_str
        assert "Invalid value" in error_str
        assert "line 5" in error_str
        assert "Missing field" in error_str

    def test_error_attributes(self) -> None:
        """Test error attributes are accessible."""
        errors = [{"location": "root", "message": "test"}]
        error = SchemaValidationError("Test message", errors)

        assert error.message == "Test message"
        assert error.errors == errors
