# summary: "Tests template-adapter DTO validation, aliases, defaults, and request integration."
# read_when:
#   - "Changing template message, adapter config, or generation request DTOs."

"""Tests for dspx.dtos DTOs."""

from typing import Any, Literal, cast

import pytest
from pydantic import ValidationError

from dspx.dtos import (
    TemplateAdapterConfig,
    TemplateMessage,
    SignatureGenRequest,
    CodegenRequest,
)


class TestTemplateMessage:
    """Tests for TemplateMessage DTO."""

    def test_basic_message(self) -> None:
        """Test creating a basic template message."""
        msg = TemplateMessage(role="system", content="{instruction}")
        assert msg.role == "system"
        assert msg.content == "{instruction}"

    def test_user_alias(self) -> None:
        """Test that 'user' alias works for user_template."""
        msg = TemplateMessage.model_validate({"role": "demos", "user": "Q: {question}"})
        assert msg.user_template == "Q: {question}"

    def test_assistant_alias(self) -> None:
        """Test that 'assistant' alias works for assistant_template."""
        msg = TemplateMessage.model_validate(
            {"role": "demos", "assistant": "A: {answer}"}
        )
        assert msg.assistant_template == "A: {answer}"

    def test_both_aliases(self) -> None:
        """Test both user and assistant templates."""
        msg = TemplateMessage.model_validate(
            {
                "role": "demos",
                "user": "Q: {question}",
                "assistant": "A: {answer}",
            }
        )
        assert msg.user_template == "Q: {question}"
        assert msg.assistant_template == "A: {answer}"

    def test_all_roles(self) -> None:
        """Test all valid roles."""
        valid_roles: tuple[
            Literal["system", "user", "assistant", "demos", "history"], ...
        ] = ("system", "user", "assistant", "demos", "history")
        for role in valid_roles:
            msg = TemplateMessage(role=role)
            assert msg.role == role

    def test_invalid_role(self) -> None:
        """Test that invalid role raises ValidationError."""
        with pytest.raises(ValidationError):
            TemplateMessage(role=cast(Any, "invalid"), content="test")


class TestTemplateAdapterConfig:
    """Tests for TemplateAdapterConfig DTO."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = TemplateAdapterConfig()
        assert config.parse_mode == "auto"
        assert config.custom_parse_fn is None
        assert config.register_helpers == {}
        assert len(config.messages) == 2
        assert config.messages[0].role == "system"
        assert config.messages[1].role == "user"

    def test_custom_messages(self) -> None:
        """Test custom message configuration."""
        config = TemplateAdapterConfig(
            messages=[
                TemplateMessage(role="system", content="Custom system"),
                TemplateMessage(role="user", content="Custom user"),
            ]
        )
        assert len(config.messages) == 2
        assert config.messages[0].content == "Custom system"

    def test_parse_mode_json(self) -> None:
        """Test parse_mode json."""
        config = TemplateAdapterConfig(parse_mode="json")
        assert config.parse_mode == "json"

    def test_parse_mode_xml(self) -> None:
        """Test parse_mode xml."""
        config = TemplateAdapterConfig(parse_mode="xml")
        assert config.parse_mode == "xml"

    def test_parse_mode_full_text(self) -> None:
        """Test parse_mode full_text."""
        config = TemplateAdapterConfig(parse_mode="full_text")
        assert config.parse_mode == "full_text"

    def test_parse_mode_chat(self) -> None:
        """Test parse_mode chat."""
        config = TemplateAdapterConfig(parse_mode="chat")
        assert config.parse_mode == "chat"

    def test_custom_parse_fn(self) -> None:
        """Test custom_parse_fn configuration."""
        config = TemplateAdapterConfig(custom_parse_fn="myapp.parsing.custom_parser")
        assert config.custom_parse_fn == "myapp.parsing.custom_parser"

    def test_register_helpers(self) -> None:
        """Test register_helpers configuration."""
        config = TemplateAdapterConfig(
            register_helpers={
                "format_priority": "myapp.helpers.format_priority",
                "escape_xml": "myapp.helpers.escape_xml",
            }
        )
        assert "format_priority" in config.register_helpers
        assert "escape_xml" in config.register_helpers

    def test_extra_fields_allowed(self) -> None:
        """Test that extra fields are allowed for future extensibility."""
        config = TemplateAdapterConfig.model_validate(
            {"parse_mode": "json", "future_field": "future_value"}
        )
        assert config.parse_mode == "json"
        # Extra fields are stored in model.__pydantic_extra__
        assert config.model_extra is not None
        assert config.model_extra.get("future_field") == "future_value"

    def test_invalid_parse_mode(self) -> None:
        """Test that invalid parse_mode raises ValidationError."""
        with pytest.raises(ValidationError):
            TemplateAdapterConfig(parse_mode=cast(Any, "invalid"))


class TestSignatureGenRequestTemplateAdapter:
    """Tests for SignatureGenRequest with template_adapter field."""

    def test_no_template_adapter(self) -> None:
        """Test request without template adapter."""
        req = SignatureGenRequest(prompt="Test prompt")
        assert req.template_adapter is None

    def test_with_template_adapter(self) -> None:
        """Test request with template adapter config."""
        config = TemplateAdapterConfig(parse_mode="json")
        req = SignatureGenRequest(
            prompt="Test prompt",
            template_adapter=config,
        )
        assert req.template_adapter is not None
        assert req.template_adapter.parse_mode == "json"

    def test_template_adapter_dict_input(self) -> None:
        """Test that template_adapter accepts dict input."""
        req = SignatureGenRequest(
            prompt="Test prompt",
            template_adapter=cast(Any, {"parse_mode": "xml"}),
        )
        assert req.template_adapter is not None
        assert req.template_adapter.parse_mode == "xml"


class TestCodegenRequestTemplateAdapter:
    """Tests for CodegenRequest with template_adapter field."""

    def test_no_template_adapter(self) -> None:
        """Test request without template adapter."""
        req = CodegenRequest(spec="Test spec")
        assert req.template_adapter is None

    def test_with_template_adapter(self) -> None:
        """Test request with template adapter config."""
        config = TemplateAdapterConfig(parse_mode="xml")
        req = CodegenRequest(
            spec="Test spec",
            template_adapter=config,
        )
        assert req.template_adapter is not None
        assert req.template_adapter.parse_mode == "xml"
