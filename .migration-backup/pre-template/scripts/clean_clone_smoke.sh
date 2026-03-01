#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[clean-clone-smoke] uv sync"
uv sync

echo "[clean-clone-smoke] just dspx --help"
just dspx --help

echo "[clean-clone-smoke] just forge --help"
just forge --help

echo "[clean-clone-smoke] just test"
just test

echo "[clean-clone-smoke] ok"
