#!/usr/bin/env python3
# summary: "Demonstrates a required provider flag by printing the selected provider's success message."
# read_when:
#   - "Using or changing the standalone provider-flag CLI example."
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="provider-ok", description="Prints provider flag ok"
    )
    parser.add_argument(
        "--provider", "-p", required=True, help="Provider name (e.g., aws, gcp, azure)"
    )
    args = parser.parse_args(argv)

    print(f"{args.provider}: ok")


if __name__ == "__main__":
    main()
