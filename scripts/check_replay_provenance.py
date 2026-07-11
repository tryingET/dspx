# ---
# summary: "Exercise replay provenance success and cache-code drift detection end to end."
# read_when:
#   - "Changing replay receipts, cache provenance checks, or the replay verification gate."
# ---
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


class CheckError(RuntimeError):
    pass


def _run(
    args: Sequence[str],
    *,
    env: dict[str, str],
    expected_returncodes: Sequence[int],
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        list(args),
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in expected_returncodes:
        raise CheckError(
            "command failed unexpectedly\n"
            f"args={list(args)!r}\n"
            f"expected_returncodes={list(expected_returncodes)!r}\n"
            f"actual_returncode={proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def _load_json_output(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:  # pragma: no cover - defensive formatting path
        raise CheckError(
            "command did not emit valid JSON\n"
            f"returncode={proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        ) from exc
    if not isinstance(payload, dict):
        raise CheckError(f"expected JSON object, got: {type(payload).__name__}")
    return payload


def _assert_ok_report(payload: dict[str, Any]) -> None:
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        raise CheckError(f"missing replay checks: {payload}")
    if payload.get("status") != "ok":
        raise CheckError(f"expected ok replay report, got: {payload}")
    if payload.get("error_codes") != []:
        raise CheckError(f"expected no replay error codes, got: {payload}")
    required_true = {
        "output_hash_match",
        "cache_file_exists",
        "cache_key_recomputes",
        "cache_code_hash_matches_receipt",
    }
    failed = sorted(name for name in required_true if checks.get(name) is not True)
    if failed:
        raise CheckError(
            f"expected passing replay checks, failed={failed}, payload={payload}"
        )


def _assert_drift_report(payload: dict[str, Any]) -> None:
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        raise CheckError(f"missing replay checks: {payload}")
    if payload.get("status") != "failed":
        raise CheckError(f"expected failed replay report after drift, got: {payload}")
    error_codes = payload.get("error_codes")
    if not isinstance(error_codes, list):
        raise CheckError(f"expected replay error_codes list, got: {payload}")
    if "cache_code_hash_mismatch" not in error_codes:
        raise CheckError(
            "expected cache_code_hash_mismatch after cache provenance drift, "
            f"got error_codes={error_codes!r}"
        )
    if checks.get("cache_code_hash_matches_receipt") is not False:
        raise CheckError(
            "expected cache_code_hash_matches_receipt to fail after drift, "
            f"got checks={checks!r}"
        )


def main() -> int:
    if shutil.which("uv") is None:
        print("error: missing dependency: uv", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="dspx-replay-provenance-") as tmpdir:
        tmp_path = Path(tmpdir)
        output_path = tmp_path / "sig.py"
        receipt_path = tmp_path / "sig.py.meta.json"
        env = dict(os.environ)
        env.update(
            {
                "MLFLOW_ENABLE": "0",
                "DSPX_PROVIDER": "stub",
                "DSPX_CACHE_ENABLE": "1",
                "DSPX_CACHE_DIR": str(tmp_path / "cache"),
            }
        )

        _run(
            [
                "uv",
                "run",
                "--no-sync",
                "--package",
                "dspx-core",
                "-q",
                "python",
                "-m",
                "dspx.cli.dspx",
                "signature",
                "gen",
                "Extract names from text",
                "--template-version",
                "simple-v1",
                "--outfile",
                str(output_path),
            ],
            env=env,
            expected_returncodes=(0,),
        )
        if not receipt_path.exists():
            raise CheckError(f"expected receipt to exist: {receipt_path}")

        ok_proc = _run(
            [
                "uv",
                "run",
                "--no-sync",
                "--package",
                "dspx-core",
                "-q",
                "python",
                "-m",
                "dspx.cli.dspx",
                "run",
                "replay",
                "--from",
                str(receipt_path),
                "--check-only",
                "--json",
            ],
            env=env,
            expected_returncodes=(0,),
        )
        ok_payload = _load_json_output(ok_proc)
        _assert_ok_report(ok_payload)

        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        cache_file = Path(str(receipt.get("cache_file") or ""))
        if not cache_file.exists():
            raise CheckError(f"expected cache file to exist: {cache_file}")
        cache_payload = json.loads(cache_file.read_text(encoding="utf-8"))
        if not isinstance(cache_payload, dict):
            raise CheckError(
                f"expected cache payload dict, got: {type(cache_payload).__name__}"
            )
        cache_payload["code"] = "print('cache drift')\n"
        cache_file.write_text(json.dumps(cache_payload), encoding="utf-8")

        drift_proc = _run(
            [
                "uv",
                "run",
                "--no-sync",
                "--package",
                "dspx-core",
                "-q",
                "python",
                "-m",
                "dspx.cli.dspx",
                "run",
                "replay",
                "--from",
                str(receipt_path),
                "--check-only",
                "--json",
            ],
            env=env,
            expected_returncodes=(1,),
        )
        drift_payload = _load_json_output(drift_proc)
        _assert_drift_report(drift_payload)

        summary = {
            "status": "ok",
            "generated_receipt": str(receipt_path),
            "validated_ok_error_codes": ok_payload.get("error_codes", []),
            "validated_drift_error_codes": drift_payload.get("error_codes", []),
            "validated_drift_checks": drift_payload.get("checks", {}),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckError as exc:
        print(f"error: replay provenance check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
