# summary: "Provides an argparse demo for registered web and data-preview tools."
# read_when:
#   - "Changing the tools demo commands, arguments, output truncation, or registry invocation."

import argparse
import json
from typing import Optional

from dspx.tools.registry import ensure_default_tools, get_tool


def cmd_search(args: argparse.Namespace) -> int:
    ensure_default_tools()
    fn = get_tool("web_search")
    res = fn(args.query, args.k)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    ensure_default_tools()
    fn = get_tool("web_fetch")
    res = fn(args.url)
    # Avoid dumping huge response bodies
    text = res.get("text", "")
    res["text"] = text[:2000] + ("…" if len(text) > 2000 else "")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def cmd_scrape(args: argparse.Namespace) -> int:
    ensure_default_tools()
    fn = get_tool("web_scrape")
    selector = args.selector or None
    res = fn(args.url, selector=selector)
    # Truncate output
    text = res.get("text", "")
    res["text"] = text[:2000] + ("…" if len(text) > 2000 else "")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    ensure_default_tools()
    fn = get_tool("data_preview")
    res = fn(args.path, nrows=args.nrows)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="DSPy tools demo (search/fetch/scrape/preview)"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="Web search via DuckDuckGo")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    s.set_defaults(func=cmd_search)

    f = sub.add_parser("fetch", help="HTTP GET a URL and print metadata")
    f.add_argument("url")
    f.set_defaults(func=cmd_fetch)

    sc = sub.add_parser("scrape", help="Fetch and extract text; optional CSS selector")
    sc.add_argument("url")
    sc.add_argument("--selector", default="")
    sc.set_defaults(func=cmd_scrape)

    pr = sub.add_parser("preview", help="Preview CSV/JSON/Parquet (columns + head)")
    pr.add_argument("path")
    pr.add_argument("--nrows", type=int, default=5)
    pr.set_defaults(func=cmd_preview)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
