#!/usr/bin/env python3
import sys
import argparse

APP_NAME = "provider"
OK_MESSAGE = "ok"

def cmd_print(args: argparse.Namespace) -> int:
    # Prints "ok" or a custom message if provided.
    msg = OK_MESSAGE if not args.message else args.message
    print(msg)
    return 0

def cmd_version(_args: argparse.Namespace) -> int:
    print(f"{APP_NAME} 1.0.0")
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="A minimal CLI that prints 'ok'."
    )
    sub = parser.add_subparsers(dest="command", required=False)

    # Default behavior prints "ok" if no subcommand is given.
    parser.add_argument(
        "-m", "--message",
        help="Custom message to print instead of 'ok'.",
        default=None
    )

    # Explicit 'print' subcommand
    p_print = sub.add_parser("print", help="Print 'ok' or a custom message.")
    p_print.add_argument(
        "-m", "--message",
        help="Custom message to print instead of 'ok'.",
        default=None
    )
    p_print.set_defaults(func=cmd_print)

    # 'version' subcommand
    p_ver = sub.add_parser("version", help="Show version.")
    p_ver.set_defaults(func=cmd_version)

    return parser

def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    # If a subcommand handler exists, run it; otherwise default to print.
    if hasattr(args, "func"):
        return args.func(args)
    return cmd_print(args)

if __name__ == "__main__":
    raise SystemExit(main())
