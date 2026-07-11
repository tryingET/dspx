# summary: "Tests TOML configuration loading, environment projection, refresh behavior, and secret-safe validation."
# read_when:
#   - "You are changing config sections, environment mappings, override precedence, or configuration safety checks."

from __future__ import annotations

import os
from pathlib import Path

from dspx.config_loader import load_config_env


def test_load_config_env_sets_env(monkeypatch, tmp_path: Path) -> None:
    # Start with clean env for keys we assert
    for k in [
        "MLFLOW_ENABLE",
        "MLFLOW_TRACKING_URI",
        "MLFLOW_EXPERIMENT",
        "MLFLOW_ARTIFACT_ROOT",
        "CODEX_MODEL",
        "CODEX_REASONING",
        "CODEX_BYPASS",
        "CODEX_SEARCH",
        "DSPX_PROVIDER",
    ]:
        monkeypatch.delenv(k, raising=False)

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [mlflow]
        enable = true
        tracking_uri = "http://localhost:5000"
        experiment = "TEST_EXP"
        artifact_root = "./mlflow-artifacts"

        [codex]
        model = "gpt-test"
        reasoning_effort = "minimal"
        bypass = true
        search = false

        [provider]
        name = "codex-exec"
        """,
        encoding="utf-8",
    )

    data = load_config_env(str(cfg))
    assert data["mlflow"]["tracking_uri"] == "http://localhost:5000"
    assert os.environ["MLFLOW_TRACKING_URI"] == "http://localhost:5000"
    assert os.environ["MLFLOW_ENABLE"] == "1"
    assert os.environ["MLFLOW_EXPERIMENT"] == "TEST_EXP"
    assert os.environ["MLFLOW_ARTIFACT_ROOT"] == "./mlflow-artifacts"
    assert os.environ["CODEX_MODEL"] == "gpt-test"
    assert os.environ["CODEX_REASONING"] == "minimal"
    assert os.environ["CODEX_BYPASS"] == "1"
    assert os.environ["CODEX_SEARCH"] == "0"
    assert os.environ["DSPX_PROVIDER"] == "codex-exec"


def test_load_config_env_defaults_codex_bypass_to_safe_false(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CODEX_BYPASS", raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [codex]
        model = "gpt-test"
        """,
        encoding="utf-8",
    )

    load_config_env(str(cfg))

    assert os.environ["CODEX_BYPASS"] == "0"


def test_load_config_env_accepts_numeric_zero_one_booleans(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CODEX_BYPASS", raising=False)
    monkeypatch.delenv("CODEX_SEARCH", raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [codex]
        bypass = 1
        search = 0
        """,
        encoding="utf-8",
    )

    load_config_env(str(cfg))

    assert os.environ["CODEX_BYPASS"] == "1"
    assert os.environ["CODEX_SEARCH"] == "0"


def test_load_config_env_rejects_unknown_bool_strings(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CODEX_BYPASS", raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [codex]
        bypass = "flase"
        """,
        encoding="utf-8",
    )

    try:
        load_config_env(str(cfg))
    except ValueError as exc:
        assert "codex.bypass" in str(exc)
        assert "true/false" in str(exc)
    else:  # pragma: no cover - fail closed assertion
        raise AssertionError("expected ValueError for unknown boolean string")

    assert os.getenv("CODEX_BYPASS") is None


def test_load_config_env_sets_pi_env(monkeypatch, tmp_path: Path) -> None:
    for k in [
        "DSPX_PROVIDER",
        "DSPX_PI_PROVIDER",
        "DSPX_PI_MODEL",
        "DSPX_PI_THINKING",
        "DSPX_PI_TIMEOUT",
        "DSPX_PI_NO_TOOLS",
        "DSPX_PI_NO_SESSION",
        "DSPX_PI_DISABLE_RESOURCES",
    ]:
        monkeypatch.delenv(k, raising=False)

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [pi]
        provider = "openai-codex"
        model = "gpt-5.1-codex-mini"
        thinking = "medium"
        timeout_s = 42
        no_tools = true
        no_session = true
        disable_resources = false

        [provider]
        name = "pi-rpc"
        """,
        encoding="utf-8",
    )

    load_config_env(str(cfg))
    assert os.environ["DSPX_PROVIDER"] == "pi-rpc"
    assert os.environ["DSPX_PI_PROVIDER"] == "openai-codex"
    assert os.environ["DSPX_PI_MODEL"] == "gpt-5.1-codex-mini"
    assert os.environ["DSPX_PI_THINKING"] == "medium"
    assert os.environ["DSPX_PI_TIMEOUT"] == "42"
    assert os.environ["DSPX_PI_NO_TOOLS"] == "1"
    assert os.environ["DSPX_PI_NO_SESSION"] == "1"
    assert os.environ["DSPX_PI_DISABLE_RESOURCES"] == "0"


def test_load_config_env_sets_lm_auth_and_vllm_env(monkeypatch, tmp_path: Path) -> None:
    for k in [
        "DSPX_PROVIDER",
        "DSPX_LM_AUTH_MODEL",
        "DSPX_LM_AUTH_PROVIDER",
        "DSPX_LM_AUTH_STORAGE",
        "DSPX_LM_AUTH_TIMEOUT",
        "DSPX_LM_AUTH_REASONING_EFFORT",
        "DSPX_VLLM_API_BASE",
        "DSPX_VLLM_MODEL",
        "DSPX_VLLM_TIMEOUT",
        "DSPX_VLLM_JSON_MODE",
    ]:
        monkeypatch.delenv(k, raising=False)

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [lm_auth]
        model = "codex/gpt-5.4-mini"
        auth_provider = "codex"
        auth_storage = "~/.pi/agent/auth.json"
        timeout_s = 75
        reasoning_effort = "low"

        [vllm]
        api_base = "http://127.0.0.1:8000/v1"
        model = "local-student"
        timeout_s = 33
        json_mode = true

        [provider]
        name = "vllm-local"
        """,
        encoding="utf-8",
    )

    load_config_env(str(cfg))
    assert os.environ["DSPX_PROVIDER"] == "vllm-local"
    assert os.environ["DSPX_LM_AUTH_MODEL"] == "codex/gpt-5.4-mini"
    assert os.environ["DSPX_LM_AUTH_PROVIDER"] == "codex"
    assert os.environ["DSPX_LM_AUTH_STORAGE"] == "~/.pi/agent/auth.json"
    assert os.environ["DSPX_LM_AUTH_TIMEOUT"] == "75"
    assert os.environ["DSPX_LM_AUTH_REASONING_EFFORT"] == "low"
    assert os.environ["DSPX_VLLM_API_BASE"] == "http://127.0.0.1:8000/v1"
    assert os.environ["DSPX_VLLM_MODEL"] == "local-student"
    assert os.environ["DSPX_VLLM_TIMEOUT"] == "33"
    assert os.environ["DSPX_VLLM_JSON_MODE"] == "1"


def test_load_config_env_sets_optimize_provider_defaults(
    monkeypatch, tmp_path: Path
) -> None:
    for k in [
        "DSPX_OPTIMIZE_STUDENT_PROVIDER",
        "DSPX_OPTIMIZE_REFLECTION_PROVIDER",
    ]:
        monkeypatch.delenv(k, raising=False)

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [optimize]
        student_provider = "vllm-local"
        reflection_provider = "dspy-lm-auth"
        """,
        encoding="utf-8",
    )

    load_config_env(str(cfg))
    assert os.environ["DSPX_OPTIMIZE_STUDENT_PROVIDER"] == "vllm-local"
    assert os.environ["DSPX_OPTIMIZE_REFLECTION_PROVIDER"] == "dspy-lm-auth"


def test_load_config_env_fails_closed_for_missing_explicit_path(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DSPX_PROVIDER", raising=False)
    (tmp_path / "config.toml").write_text(
        '[provider]\nname = "stub"\n', encoding="utf-8"
    )

    missing = tmp_path / "missing.toml"

    try:
        load_config_env(str(missing))
    except FileNotFoundError as exc:
        assert str(missing.resolve()) in str(exc)
    else:  # pragma: no cover - fail closed assertion
        raise AssertionError("expected FileNotFoundError for missing explicit path")

    assert os.getenv("DSPX_PROVIDER") != "stub"


def test_load_config_env_fails_closed_for_missing_dspx_config_env(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DSPX_PROVIDER", raising=False)
    (tmp_path / "config.toml").write_text(
        '[provider]\nname = "stub"\n', encoding="utf-8"
    )
    missing = tmp_path / "missing.toml"
    monkeypatch.setenv("DSPX_CONFIG", str(missing))

    try:
        load_config_env()
    except FileNotFoundError as exc:
        assert str(missing.resolve()) in str(exc)
    else:  # pragma: no cover - fail closed assertion
        raise AssertionError("expected FileNotFoundError for missing DSPX_CONFIG")

    assert os.getenv("DSPX_PROVIDER") is None


def test_load_config_env_fails_closed_for_invalid_toml(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('[provider\nname = "broken"\n', encoding="utf-8")

    try:
        load_config_env(str(cfg))
    except ValueError as exc:
        assert str(cfg) in str(exc)
        assert "Failed to parse DSPx config TOML" in str(exc)
    else:  # pragma: no cover - fail closed assertion
        raise AssertionError("expected ValueError for invalid TOML")


def test_load_config_env_refreshes_previous_config_managed_values(
    monkeypatch, tmp_path: Path
) -> None:
    for key in [
        "DSPX_PROVIDER",
        "DSPX_PI_TIMEOUT",
        "MLFLOW_EXPERIMENT",
    ]:
        monkeypatch.delenv(key, raising=False)

    cfg_a = tmp_path / "a.toml"
    cfg_a.write_text(
        """
        [provider]
        name = "stub"

        [pi]
        timeout_s = 42

        [mlflow]
        experiment = "EXP_A"
        """,
        encoding="utf-8",
    )
    cfg_b = tmp_path / "b.toml"
    cfg_b.write_text(
        """
        [provider]
        name = "pi-rpc"

        [mlflow]
        experiment = "EXP_B"
        """,
        encoding="utf-8",
    )

    load_config_env(str(cfg_a))
    assert os.environ["DSPX_PROVIDER"] == "stub"
    assert os.environ["DSPX_PI_TIMEOUT"] == "42"
    assert os.environ["MLFLOW_EXPERIMENT"] == "EXP_A"

    load_config_env(str(cfg_b))
    assert os.environ["DSPX_PROVIDER"] == "pi-rpc"
    assert os.environ["MLFLOW_EXPERIMENT"] == "EXP_B"
    assert os.getenv("DSPX_PI_TIMEOUT") is None


def test_load_config_env_preserves_explicit_env_override_on_refresh(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "explicit-provider")

    cfg_a = tmp_path / "a.toml"
    cfg_a.write_text('[provider]\nname = "stub"\n', encoding="utf-8")
    cfg_b = tmp_path / "b.toml"
    cfg_b.write_text('[provider]\nname = "pi-rpc"\n', encoding="utf-8")

    load_config_env(str(cfg_a))
    load_config_env(str(cfg_b))

    assert os.environ["DSPX_PROVIDER"] == "explicit-provider"


def test_load_config_env_rejects_embedded_secrets(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DSPX_OPENAI_COMPAT_API_KEY", raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [openai_compatible]
        api_key = "super-secret"
        api_base = "http://127.0.0.1:8000/v1"
        """,
        encoding="utf-8",
    )

    try:
        load_config_env(str(cfg))
    except ValueError as exc:
        assert "must not embed secrets" in str(exc)
        assert "openai_compatible.api_key" in str(exc)
    else:  # pragma: no cover - fail closed assertion
        raise AssertionError("expected ValueError for embedded secret")

    assert os.getenv("DSPX_OPENAI_COMPAT_API_KEY") is None


def test_load_config_env_rejects_url_userinfo(monkeypatch, tmp_path: Path) -> None:
    for key in [
        "OPENROUTER_BASE_URL",
        "DSPX_OPENAI_COMPAT_API_BASE",
        "DSPX_VLLM_API_BASE",
    ]:
        monkeypatch.delenv(key, raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [openrouter]
        base_url = "https://user:pass@openrouter.example/v1"
        [openai_compatible]
        api_base = "https://user:pass@compat.example/v1"
        [vllm]
        api_base = "https://user:pass@vllm.example/v1"
        """,
        encoding="utf-8",
    )

    try:
        load_config_env(str(cfg))
    except ValueError as exc:
        assert "openrouter.base_url" in str(exc)
        assert "embedded credentials" in str(exc)
    else:  # pragma: no cover - fail closed assertion
        raise AssertionError("expected ValueError for URL userinfo")

    assert os.getenv("OPENROUTER_BASE_URL") is None
    assert os.getenv("DSPX_OPENAI_COMPAT_API_BASE") is None
    assert os.getenv("DSPX_VLLM_API_BASE") is None


def test_load_config_env_rejects_url_userinfo_in_http_referer(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENROUTER_HTTP_REFERER", raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [openrouter]
        http_referer = "https://user:pass@example.invalid/app"
        """,
        encoding="utf-8",
    )

    try:
        load_config_env(str(cfg))
    except ValueError as exc:
        assert "openrouter.http_referer" in str(exc)
        assert "embedded credentials" in str(exc)
    else:  # pragma: no cover - fail closed assertion
        raise AssertionError("expected ValueError for URL userinfo in referer")

    assert os.getenv("OPENROUTER_HTTP_REFERER") is None


def test_load_config_env_rolls_back_partial_env_on_validation_failure(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "preexisting")
    monkeypatch.delenv("MLFLOW_EXPERIMENT", raising=False)
    monkeypatch.delenv("CODEX_BYPASS", raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [openrouter]
        base_url = "https://user:pass@openrouter.example/v1"
        """,
        encoding="utf-8",
    )

    try:
        load_config_env(str(cfg))
    except ValueError:
        pass
    else:  # pragma: no cover - fail closed assertion
        raise AssertionError("expected ValueError for URL userinfo")

    assert os.environ["MLFLOW_ENABLE"] == "preexisting"
    assert os.getenv("MLFLOW_EXPERIMENT") is None
    assert os.getenv("CODEX_BYPASS") is None
