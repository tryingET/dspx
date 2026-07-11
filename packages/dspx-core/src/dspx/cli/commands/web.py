# summary: "Defines terminal-friendly web fetch and scrape CLI commands over the registered tool runtime."
# read_when:
#   - "Changing web command options, host allowlisting, timeouts, selectors, or output truncation."

"""Web tool commands.

Commands for fetching and scraping web content.
"""

from __future__ import annotations

import json
from typing import Optional

import typer

app = typer.Typer(no_args_is_help=True)


@app.command("fetch")
def web_fetch(
    url: str = typer.Argument(..., help="URL to fetch"),
    allow_host: Optional[str] = typer.Option(
        None, help="Allowlisted host (e.g., example.com)"
    ),
    timeout: float = typer.Option(15.0, help="Timeout seconds"),
) -> None:
    """Fetch content from a URL."""
    from dspx.tools.registry import ensure_default_tools, get_tool

    ensure_default_tools()
    fn = get_tool("web_fetch")
    allowed = {allow_host: True} if allow_host else None
    out = fn(url, timeout=timeout, allowed_hosts=allowed)

    # Truncate text for terminal friendliness
    text = str(out.get("text", ""))
    if len(text) > 4000:
        out["text"] = text[:4000] + "\n... [truncated]"

    typer.echo(json.dumps(out, ensure_ascii=False, indent=2))


@app.command("scrape")
def web_scrape(
    url: str = typer.Argument(..., help="URL to fetch and extract"),
    selector: Optional[str] = typer.Option(None, help="Optional CSS selector"),
    allow_host: Optional[str] = typer.Option(
        None, help="Allowlisted host (e.g., example.com)"
    ),
    timeout: float = typer.Option(15.0, help="Timeout seconds"),
) -> None:
    """Scrape content from a URL with optional CSS selector."""
    from dspx.tools.registry import ensure_default_tools, get_tool

    ensure_default_tools()
    fn = get_tool("web_scrape")
    allowed = {allow_host: True} if allow_host else None
    out = fn(url, selector=selector, timeout=timeout, allowed_hosts=allowed)

    # Truncate long text
    text = str(out.get("text", ""))
    if len(text) > 4000:
        out["text"] = text[:4000] + "\n... [truncated]"

    typer.echo(json.dumps(out, ensure_ascii=False, indent=2))
