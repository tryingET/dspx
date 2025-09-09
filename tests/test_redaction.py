from __future__ import annotations

from dspx.redaction import redact_url, redact_headers


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
