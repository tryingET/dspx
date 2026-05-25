from __future__ import annotations

from dspx.redaction import redact_url, redact_headers, sanitize_diagnostic_text


def test_redact_url_tokens() -> None:
    u = "https://api.example.com/x?token=abc123&ok=1&api_key=xyz"
    r = redact_url(u)
    assert "abc123" not in r and "xyz" not in r
    assert "[REDACTED]" in r


def test_redact_headers() -> None:
    h = {"Authorization": "Bearer x", "X-Token": "y", "Ok": "z"}
    r = redact_headers(h)
    assert r["Authorization"] == "[REDACTED]" and r["X-Token"] == "[REDACTED]"
    assert r["Ok"] == "z"


def test_sanitize_diagnostic_text_redacts_common_secret_shapes() -> None:
    text = (
        "api_key=supersecret Authorization: Bearer bearer-secret "
        'payload={"token":"json-secret"} '
        "https://user:pass@example.test/path?token=url-secret&ok=1"
    )

    redacted = sanitize_diagnostic_text(text)

    assert "[REDACTED]" in redacted
    assert "supersecret" not in redacted
    assert "bearer-secret" not in redacted
    assert "json-secret" not in redacted
    assert "url-secret" not in redacted
    assert "user:pass" not in redacted


def test_sanitize_diagnostic_text_truncates_long_values() -> None:
    redacted = sanitize_diagnostic_text("x" * 400, limit=12)

    assert redacted == "x" * 12 + "…[truncated]"


def test_redact_url_userinfo_and_cookie_headers() -> None:
    u = "https://user:pass@api.example.com/x?ok=1&secret=s"
    r = redact_url(u)
    # userinfo should be redacted and secret masked
    assert "user:pass@" not in r and "secret=s" not in r and "[REDACTED]" in r
    # headers redaction includes cookie variants
    h = {"Set-Cookie": "sessionid=abc", "Cookie": "a=b", "X-API-Key": "k"}
    hr = redact_headers(h)
    assert hr["Set-Cookie"] == "[REDACTED]" and hr["Cookie"] == "[REDACTED]"
    assert hr["X-API-Key"] == "[REDACTED]"
