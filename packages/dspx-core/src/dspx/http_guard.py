from __future__ import annotations

from typing import Mapping, Optional
import httpx

from dspx.redaction import redact_url
from dspx.security import url_origin_allowed


AllowedHosts = Optional[Mapping[str, bool] | set[str]]


def host_allowed(url: str, allowed_hosts: AllowedHosts) -> bool:
    return url_origin_allowed(url, allowed_hosts)


def send_with_host_allowlist(
    client: httpx.Client,
    request: httpx.Request,
    *,
    allowed_hosts: AllowedHosts,
    blocked_error_prefix: str = "Host not allowed for URL",
    redirect_error_prefix: str = "Redirect target host not allowed for URL",
    max_redirects: int = 10,
    stream: bool = False,
) -> httpx.Response:
    """Send a request while validating every redirect hop before it is followed."""
    current = request
    redirects = 0

    while True:
        current_url = str(current.url)
        if not host_allowed(current_url, allowed_hosts):
            raise PermissionError(f"{blocked_error_prefix}: {redact_url(current_url)}")

        response = client.send(current, follow_redirects=False, stream=stream)
        next_request = response.next_request
        if next_request is None:
            return response

        response.close()
        redirects += 1
        if redirects > max_redirects:
            raise RuntimeError(f"too many redirects for URL: {redact_url(current_url)}")

        next_url = str(next_request.url)
        if not host_allowed(next_url, allowed_hosts):
            raise PermissionError(f"{redirect_error_prefix}: {redact_url(next_url)}")
        current = next_request
