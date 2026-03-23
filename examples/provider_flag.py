#!/usr/bin/env python3
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
