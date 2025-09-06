#!/usr/bin/env python3
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Echo the provided argument.")
    parser.add_argument("message", help="Message to echo")
    args = parser.parse_args()

    # Print the message exactly as provided
    print(args.message)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Allow piping to closed consumers without stack traces
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(1)
