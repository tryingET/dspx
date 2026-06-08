from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from dspx.dtos import OpenAPICallRequest
from dspx.run_receipts import build_mlflow_hints
from dspx.tools.openapi.caller import call_operation
from dspx.tools.openapi.loader import load_spec


SECRET = "super-secret-token"


def test_openapi_spec_host_denial_redacts_secret_url_query() -> None:
    with pytest.raises(PermissionError) as excinfo:
        load_spec(
            f"https://evil.example/openapi.json?api_key={SECRET}",
            allowed_hosts={"api.example": True},
        )

    message = str(excinfo.value)
    assert "Host not allowed for spec URL" in message
    assert "api_key=[REDACTED]" in message
    assert SECRET not in message


def test_openapi_redirect_denial_redacts_secret_url_query() -> None:
    operation = {
        "operationId": "ping",
        "method": "GET",
        "server": "http://api.example.com",
        "path": "/ping",
        "parameters": [],
    }
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": f"http://evil.example/leak?token={SECRET}"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(PermissionError) as excinfo:
        call_operation(
            OpenAPICallRequest(operation_id="ping"),
            operation=operation,
            allowed_hosts={"api.example.com": True},
            client=client,
        )

    message = str(excinfo.value)
    assert "Redirect target host not allowed" in message
    assert "token=[REDACTED]" in message
    assert SECRET not in message
    assert seen == ["http://api.example.com/ping"]


def test_openapi_call_result_redacts_sensitive_response_headers() -> None:
    operation = {
        "operationId": "ping",
        "method": "GET",
        "server": "http://api.example.com",
        "path": "/ping",
        "parameters": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True},
            headers={
                "set-cookie": f"session={SECRET}",
                "x-api-key": SECRET,
                "x-request-id": "req-123",
            },
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = call_operation(
        OpenAPICallRequest(operation_id="ping"),
        operation=operation,
        allowed_hosts={"api.example.com": True},
        client=client,
    )

    assert result.headers["set-cookie"] == "[REDACTED]"
    assert result.headers["x-api-key"] == "[REDACTED]"
    assert result.headers["x-request-id"] == "req-123"
    assert SECRET not in repr(result.headers)


def test_mlflow_hint_tracking_uri_observed_redacts_secrets() -> None:
    hints = build_mlflow_hints(
        run_kind="codegen",
        output_path=Path("generated/out.py"),
        output_hash="abc123",
        template_version=None,
        cache_key=None,
        tracking_uri=f"https://user:{SECRET}@mlflow.example/path?token={SECRET}",
    )

    observed = hints["tracking_uri_observed"]
    assert "[REDACTED]@mlflow.example" in observed
    assert "token=[REDACTED]" in observed
    assert SECRET not in observed
