"""Tests for request body size limit middleware (AK-800)."""

from __future__ import annotations

from typing import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from dspx.server.app import create_app
from dspx.server.security import BodySizeLimitConfig, _parse_size


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for k in [
        "DSPX_SERVER_TOKEN",
        "DSPX_SERVER_TOKENS",
        "DSPX_SERVER_TOKEN_FILE",
        "DSPX_AUTH_REQUIRED",
        "DSPX_AUTH_SKIP_FOR_DEV",
        "DSPX_BODY_SIZE_LIMIT_ENABLED",
        "DSPX_MAX_BODY_SIZE",
        "DSPX_METRICS_ENABLED",
    ]:
        monkeypatch.delenv(k, raising=False)
    yield


@pytest.fixture()
def make_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., TestClient]:
    """Create a TestClient factory with auth skipped and configurable overrides."""

    def _factory(**overrides: str) -> TestClient:
        monkeypatch.setenv("DSPX_AUTH_SKIP_FOR_DEV", "1")
        for k, v in overrides.items():
            monkeypatch.setenv(k, v)
        return TestClient(create_app())

    return _factory


# ---------------------------------------------------------------------------
# _parse_size unit tests
# ---------------------------------------------------------------------------


class TestParseSize:
    def test_plain_integer(self) -> None:
        assert _parse_size("1048576") == 1048576

    def test_kb_suffix(self) -> None:
        assert _parse_size("512k") == 512 * 1024

    def test_mb_suffix(self) -> None:
        assert _parse_size("10MB") == 10 * 1024 * 1024

    def test_gb_suffix(self) -> None:
        assert _parse_size("1GB") == 1024 * 1024 * 1024

    def test_case_insensitive(self) -> None:
        assert _parse_size("5Mb") == 5 * 1024 * 1024

    def test_b_suffix(self) -> None:
        assert _parse_size("100b") == 100

    def test_invalid_suffix_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid size value"):
            _parse_size("10xx")

    def test_non_numeric_prefix_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid size value"):
            _parse_size("abcMB")

    def test_whitespace(self) -> None:
        assert _parse_size("  2MB  ") == 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# BodySizeLimitConfig.from_env
# ---------------------------------------------------------------------------


class TestBodySizeLimitConfig:
    def test_defaults_enabled_10mb(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = BodySizeLimitConfig.from_env()
        assert cfg.enabled is True
        assert cfg.max_bytes == 10 * 1024 * 1024

    def test_custom_size_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DSPX_MAX_BODY_SIZE", "1k")
        cfg = BodySizeLimitConfig.from_env()
        assert cfg.max_bytes == 1024

    def test_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DSPX_BODY_SIZE_LIMIT_ENABLED", "0")
        cfg = BodySizeLimitConfig.from_env()
        assert cfg.enabled is False

    def test_negative_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DSPX_MAX_BODY_SIZE", "-1")
        with pytest.raises(ValueError, match="non-negative"):
            BodySizeLimitConfig.from_env()


# ---------------------------------------------------------------------------
# Middleware integration via TestClient
# ---------------------------------------------------------------------------


class TestBodySizeMiddleware:
    def test_small_body_passes(self, make_client: Callable[..., TestClient]) -> None:
        client = make_client(DSPX_MAX_BODY_SIZE="1024")
        r = client.post(
            "/signature",
            json={"prompt": "echo", "template_version": "simple-v1"},
        )
        assert r.status_code == 200

    def test_oversized_content_length_rejected(
        self, make_client: Callable[..., TestClient]
    ) -> None:
        client = make_client(DSPX_MAX_BODY_SIZE="100")
        r = client.post(
            "/signature",
            content=b'{"prompt":"x"}',
            headers={
                "Content-Type": "application/json",
                "Content-Length": "200",
            },
        )
        assert r.status_code == 413
        body = r.json()
        assert body["error"] == "body_too_large"
        assert body["status"] == 413
        assert "200 bytes exceeds" in body["detail"]

    def test_invalid_content_length_rejected(
        self, make_client: Callable[..., TestClient]
    ) -> None:
        client = make_client(DSPX_MAX_BODY_SIZE="1024")
        r = client.post(
            "/signature",
            content=b'{"prompt":"x"}',
            headers={
                "Content-Type": "application/json",
                "Content-Length": "not-a-number",
            },
        )
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "invalid_request"
        assert "Content-Length" in body["detail"]

    def test_zero_max_bytes_rejects_all_bodies(
        self, make_client: Callable[..., TestClient]
    ) -> None:
        client = make_client(DSPX_MAX_BODY_SIZE="0")
        r = client.post(
            "/signature",
            json={"prompt": "echo"},
        )
        assert r.status_code == 413

    def test_disabled_allows_oversized(
        self, make_client: Callable[..., TestClient]
    ) -> None:
        client = make_client(
            DSPX_MAX_BODY_SIZE="1",
            DSPX_BODY_SIZE_LIMIT_ENABLED="0",
        )
        r = client.post(
            "/signature",
            json={"prompt": "echo", "template_version": "simple-v1"},
        )
        assert r.status_code == 200

    def test_exact_limit_passes(self, make_client: Callable[..., TestClient]) -> None:
        client = make_client(DSPX_MAX_BODY_SIZE="1024")
        r = client.post(
            "/signature",
            json={"prompt": "x", "template_version": "simple-v1"},
        )
        assert r.status_code == 200

    def test_body_too_large_applies_to_all_endpoints(
        self, make_client: Callable[..., TestClient]
    ) -> None:
        client = make_client(DSPX_MAX_BODY_SIZE="10")
        # /module
        r1 = client.post(
            "/module",
            content=b'{"name":"M"}',
            headers={
                "Content-Type": "application/json",
                "Content-Length": "50",
            },
        )
        assert r1.status_code == 413
        # /mermaid
        r2 = client.post(
            "/mermaid",
            content=b'{"mermaid":"x"}',
            headers={
                "Content-Type": "application/json",
                "Content-Length": "50",
            },
        )
        assert r2.status_code == 413

    def test_get_request_not_blocked_by_content_length(
        self, make_client: Callable[..., TestClient]
    ) -> None:
        """Non-POST endpoints shouldn't be blocked even if Content-Length is set."""
        client = make_client(
            DSPX_METRICS_ENABLED="1",
            DSPX_MAX_BODY_SIZE="10",
        )
        r = client.get("/metrics")
        assert r.status_code == 200

    def test_body_size_rejection_counted_in_metrics(
        self, make_client: Callable[..., TestClient]
    ) -> None:
        """413 rejections must appear in /metrics (nexus regression)."""
        client = make_client(
            DSPX_METRICS_ENABLED="1",
            DSPX_MAX_BODY_SIZE="100",
        )
        # Trigger a 413
        r = client.post(
            "/signature",
            content=b'{"prompt":"x"}',
            headers={
                "Content-Type": "application/json",
                "Content-Length": "200",
            },
        )
        assert r.status_code == 413

        # Verify metrics captured it
        metrics = client.get("/metrics").json()
        assert metrics["status_413"] >= 1, (
            f"expected status_413 >= 1 but got {metrics['status_413']}; "
            f"full metrics: {metrics}"
        )
        # The 413 request must also be counted in requests_total
        assert metrics["requests_total"] >= 2
