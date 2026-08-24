# summary: "Tests canonical secret-free stub and loopback-HTTP DSPx configuration."
# read_when:
#   - "Changing config discovery, supported provider sections, environment precedence, or secret rejection."

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dspx.config_loader import load_config_env


def test_load_config_env_sets_supported_stub_only_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[mlflow]
enable = false
tracking_uri = "sqlite:///local.db"
experiment = "typed-cutover"

[provider]
name = "stub"

[model_roles.oracle_semantic]
model = "stub/echo"
provider = "stub"
backend = "fixture-replay"
fixture_path = "fixtures/oracle.json"

[optimize]
student_provider = "stub"
reflection_provider = "stub"
""",
        encoding="utf-8",
    )
    for key in (
        "MLFLOW_ENABLE",
        "MLFLOW_TRACKING_URI",
        "MLFLOW_EXPERIMENT",
        "DSPX_PROVIDER",
        "DSPX_ORACLE_SEMANTIC_PROVIDER",
        "DSPX_OPTIMIZE_STUDENT_PROVIDER",
        "DSPX_OPTIMIZE_REFLECTION_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)

    payload = load_config_env(str(cfg))

    assert payload["provider"]["name"] == "stub"
    assert os.environ["MLFLOW_ENABLE"] == "0"
    assert os.environ["MLFLOW_TRACKING_URI"] == "sqlite:///local.db"
    assert os.environ["MLFLOW_EXPERIMENT"] == "typed-cutover"
    assert os.environ["DSPX_PROVIDER"] == "stub"
    assert os.environ["DSPX_ORACLE_SEMANTIC_PROVIDER"] == "stub"
    assert os.environ["DSPX_OPTIMIZE_STUDENT_PROVIDER"] == "stub"
    assert os.environ["DSPX_OPTIMIZE_REFLECTION_PROVIDER"] == "stub"


@pytest.mark.parametrize(
    "section",
    ["codex", "openrouter", "pi", "lm_auth", "openai_compatible", "vllm"],
)
def test_load_config_env_rejects_retired_provider_sections(
    section: str, tmp_path: Path
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(f"[{section}]\nmodel = 'removed'\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported provider config sections"):
        load_config_env(str(cfg))


@pytest.mark.parametrize(
    "body,label",
    [
        ("[provider]\nname = 'pi-rpc'\n", "provider.name"),
        (
            "[optimize]\nstudent_provider = 'openrouter'\n",
            "optimize.student_provider",
        ),
        (
            "[model_roles.oracle_semantic]\nprovider = 'dspy-lm-auth'\n",
            "model_roles.oracle_semantic.provider",
        ),
    ],
)
def test_load_config_env_rejects_removed_provider_selection(
    body: str, label: str, tmp_path: Path
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(body, encoding="utf-8")

    with pytest.raises(ValueError, match=label.replace(".", r"\.")):
        load_config_env(str(cfg))


def test_load_config_env_fails_closed_for_missing_explicit_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "missing.toml"
    monkeypatch.delenv("DSPX_CONFIG", raising=False)

    with pytest.raises(FileNotFoundError, match="explicit DSPx config path not found"):
        load_config_env(str(missing))


def test_load_config_env_fails_closed_for_missing_dspx_config_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DSPX_CONFIG", str(tmp_path / "missing.toml"))

    with pytest.raises(FileNotFoundError, match="DSPX_CONFIG path not found"):
        load_config_env()


def test_load_config_env_fails_closed_for_invalid_toml(tmp_path: Path) -> None:
    cfg = tmp_path / "invalid.toml"
    cfg.write_text("[provider\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Failed to parse DSPx config TOML"):
        load_config_env(str(cfg))


def test_load_config_env_refreshes_previous_managed_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = tmp_path / "first.toml"
    second = tmp_path / "second.toml"
    first.write_text(
        "[provider]\nname = 'stub'\n[mlflow]\nexperiment = 'first'\n",
        encoding="utf-8",
    )
    second.write_text("[mlflow]\nexperiment = 'second'\n", encoding="utf-8")
    monkeypatch.delenv("DSPX_PROVIDER", raising=False)
    monkeypatch.delenv("MLFLOW_EXPERIMENT", raising=False)

    load_config_env(str(first))
    assert os.environ["DSPX_PROVIDER"] == "stub"
    load_config_env(str(second))

    assert os.getenv("DSPX_PROVIDER") is None
    assert os.environ["MLFLOW_EXPERIMENT"] == "second"


def test_load_config_env_preserves_explicit_env_override_on_refresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("[mlflow]\nexperiment = 'configured'\n", encoding="utf-8")
    monkeypatch.setenv("MLFLOW_EXPERIMENT", "operator")

    load_config_env(str(cfg))

    assert os.environ["MLFLOW_EXPERIMENT"] == "operator"


def test_load_config_env_rejects_embedded_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("[provider]\nname = 'stub'\napi_key = 'secret'\n", encoding="utf-8")
    monkeypatch.delenv("DSPX_PROVIDER", raising=False)

    with pytest.raises(ValueError, match="must not embed secrets"):
        load_config_env(str(cfg))
    assert os.getenv("DSPX_PROVIDER") is None


def test_load_config_env_rejects_url_userinfo_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
[provider]
name = "stub"
[mlflow]
tracking_uri = "https://user:pass@example.test/mlflow"
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("DSPX_PROVIDER", raising=False)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)

    with pytest.raises(ValueError, match="mlflow.tracking_uri"):
        load_config_env(str(cfg))
    assert os.getenv("DSPX_PROVIDER") is None
    assert os.getenv("MLFLOW_TRACKING_URI") is None


def test_load_config_env_sets_canonical_openai_compatible_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "openai.toml"
    cfg.write_text(
        """
[provider]
name = "openai-compatible"
model = "local-model"
base_url = "http://127.0.0.1:8000/v1/"
timeout = 12.5

[optimize]
student_provider = "openai-compatible"
reflection_provider = "openai-compatible"
""",
        encoding="utf-8",
    )
    for key in (
        "DSPX_PROVIDER",
        "DSPX_OPENAI_COMPAT_MODEL",
        "DSPX_OPENAI_COMPAT_API_BASE",
        "DSPX_OPENAI_COMPAT_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)

    load_config_env(str(cfg))

    assert os.environ["DSPX_PROVIDER"] == "openai-compatible"
    assert os.environ["DSPX_OPENAI_COMPAT_MODEL"] == "local-model"
    assert os.environ["DSPX_OPENAI_COMPAT_API_BASE"] == "http://127.0.0.1:8000/v1"
    assert os.environ["DSPX_OPENAI_COMPAT_TIMEOUT"] == "12.5"
    assert os.environ["DSPX_OPTIMIZE_STUDENT_PROVIDER"] == "openai-compatible"
    assert os.environ["DSPX_OPTIMIZE_REFLECTION_PROVIDER"] == "openai-compatible"


@pytest.mark.parametrize(
    "body,match",
    [
        (
            "[provider]\nname='stub'\nmodel='irrelevant'\n",
            "stub provider does not accept HTTP configuration",
        ),
        (
            "[provider]\nname='openai-compatible'\nmodel='local-model'\n",
            "requires model and base_url",
        ),
        (
            "[provider]\nname='openai-compatible'\nmodel='local model'\nbase_url='http://127.0.0.1/v1'\n",
            "model",
        ),
        (
            "[provider]\nname='openai-compatible'\nmodel='local-model'\nbase_url='http://example.test/v1'\n",
            "loopback",
        ),
        (
            "[provider]\nname='openai-compatible'\nmodel='local-model'\nbase_url='http://127.0.0.1/v1'\nextra='x'\n",
            "unsupported fields",
        ),
    ],
)
def test_load_config_env_rejects_noncanonical_provider_fields(
    body: str, match: str, tmp_path: Path
) -> None:
    cfg = tmp_path / "invalid-provider.toml"
    cfg.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_config_env(str(cfg))
