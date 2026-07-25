# summary: "Tests conservative capability aggregation across MultiProviderLM child providers."
# read_when:
#   - "Changing multi-provider capability defaults, aggregation rules, structured output, or immutability."

"""Tests for MultiProviderLM capability aggregation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dspx.multi_provider_lm import _combine_caps
from dspx.capabilities import ProviderCapabilities


class MockProvider:
    """Mock provider with capabilities for testing."""

    def __init__(self, capabilities: ProviderCapabilities | None) -> None:
        self.capabilities = capabilities


class TestCombineCaps:
    """Tests for _combine_caps function."""

    def test_empty_provider_list_returns_defaults(self) -> None:
        """Empty provider list should return default capabilities."""
        result = _combine_caps([])
        assert result is not None
        # Default values from ProviderCapabilities
        assert (
            result.json_mode is False
        )  # all([]) = True BUG, but we handle empty explicitly
        assert result.supports_tools is False
        assert result.structured_output_format == "none"

    def test_single_provider_passthrough(self) -> None:
        """Single provider should pass through its capabilities."""
        caps = ProviderCapabilities(
            supports_tools=True,
            json_mode=True,
            structured_output_format="json",
        )
        provider = MockProvider(caps)
        result = _combine_caps([provider])

        assert result is not None
        assert result.supports_tools is True
        assert result.json_mode is True
        assert result.structured_output_format == "json"

    def test_json_mode_all_must_support(self) -> None:
        """json_mode requires ALL providers to support it."""
        json_provider = MockProvider(ProviderCapabilities(json_mode=True))
        non_json_provider = MockProvider(ProviderCapabilities(json_mode=False))

        # All json providers -> json_mode True
        result = _combine_caps([json_provider, json_provider])
        assert result is not None
        assert result.json_mode is True

        # Mixed providers -> json_mode False
        result = _combine_caps([json_provider, non_json_provider])
        assert result is not None
        assert result.json_mode is False

        # All non-json providers -> json_mode False
        result = _combine_caps([non_json_provider, non_json_provider])
        assert result is not None
        assert result.json_mode is False

    def test_structured_output_format_most_restrictive_wins(self) -> None:
        """structured_output_format should be most restrictive."""
        json_provider = MockProvider(
            ProviderCapabilities(structured_output_format="json")
        )
        xml_provider = MockProvider(
            ProviderCapabilities(structured_output_format="xml")
        )
        none_provider = MockProvider(
            ProviderCapabilities(structured_output_format="none")
        )

        # None + anything = none (most restrictive)
        result = _combine_caps([json_provider, none_provider])
        assert result is not None
        assert result.structured_output_format == "none"

        # XML + JSON = XML (more restrictive)
        result = _combine_caps([json_provider, xml_provider])
        assert result is not None
        assert result.structured_output_format == "xml"

        # All JSON = JSON
        result = _combine_caps([json_provider, json_provider])
        assert result is not None
        assert result.structured_output_format == "json"

    def test_supports_tools_any_wins(self) -> None:
        """supports_tools should be True if ANY provider supports it."""
        tools_provider = MockProvider(ProviderCapabilities(supports_tools=True))
        no_tools_provider = MockProvider(ProviderCapabilities(supports_tools=False))

        result = _combine_caps([tools_provider, no_tools_provider])
        assert result is not None
        assert result.supports_tools is True

        result = _combine_caps([no_tools_provider, no_tools_provider])
        assert result is not None
        assert result.supports_tools is False

    def test_supports_vision_aggregation(self) -> None:
        """supports_vision should aggregate with any()."""
        vision_provider = MockProvider(
            ProviderCapabilities(supports_vision=True, supports_audio=False)
        )
        no_vision_provider = MockProvider(
            ProviderCapabilities(supports_vision=False, supports_audio=False)
        )

        result = _combine_caps([vision_provider, no_vision_provider])
        assert result is not None
        assert result.supports_vision is True
        assert result.supports_audio is False

    def test_supports_audio_aggregation(self) -> None:
        """supports_audio should aggregate with any()."""
        audio_provider = MockProvider(
            ProviderCapabilities(supports_vision=False, supports_audio=True)
        )
        no_audio_provider = MockProvider(
            ProviderCapabilities(supports_vision=False, supports_audio=False)
        )

        result = _combine_caps([audio_provider, no_audio_provider])
        assert result is not None
        assert result.supports_audio is True
        assert result.supports_vision is False

    def test_provider_with_none_capabilities(self) -> None:
        """Provider with None capabilities should use defaults."""
        provider_with_caps = MockProvider(
            ProviderCapabilities(json_mode=True, structured_output_format="json")
        )
        provider_without_caps = MockProvider(None)

        # None capabilities treated as defaults (json_mode=False)
        result = _combine_caps([provider_with_caps, provider_without_caps])
        assert result is not None
        assert result.json_mode is False  # all() with False from None
        assert (
            result.structured_output_format == "none"
        )  # None -> default "none" -> most restrictive

    def test_result_is_frozen(self) -> None:
        """Result should be immutable (frozen Pydantic model)."""
        provider = MockProvider(ProviderCapabilities(json_mode=True))
        result = _combine_caps([provider])

        assert result is not None
        with pytest.raises(ValidationError):
            setattr(result, "json_mode", False)
