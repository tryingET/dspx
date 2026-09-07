"""Independent stdlib-only historical closure verifier; invoke with -I -S -B.

The interpreter and this fixed installation are provisioned/pinned by the caller,
never by evidence. Returned hashes describe that installation, not a trust anchor.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import types

PURE_MODULES = (
    "program_runtime_trace_coverage",
    "program_runtime_traces",
    "program_quality_evaluation",
    "program_refinement_gepa_metric_honesty",
)
MODULES = tuple(name + ".py" for name in PURE_MODULES) + (
    "program_foundry_closure_runtime.py",
    "program_foundry_closure_check.py",
    "program_foundry_closure_core.py",
    "program_foundry_closure_contracts.py",
    "program_foundry_closure_reducers.py",
    "program_foundry_closure_comparison.py",
    "program_foundry_closure_gepa.py",
    "program_foundry_closure_import.py",
    "program_foundry_closure_io.py",
    "program_foundry_closure_jury.py",
    "program_foundry_closure_journal.py",
    "program_foundry_closure_profiles.py",
)


def installation() -> dict:
    root = Path(__file__).resolve().parent
    rows = []
    for name in sorted(MODULES):
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 51200:
            raise ValueError("invalid installed module")
        rows.append(
            {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    raw = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return {
        "modules": rows,
        "verifier_profile_sha256": hashlib.sha256(
            b"dspx-foundry-verifier-profile-v1\0" + raw
        ).hexdigest(),
    }


def load_modules(installed: dict) -> None:
    """Load only fixed, captured current code; never add installation to sys.path."""
    root = Path(__file__).resolve().parent
    hashes = {row["path"]: row["sha256"] for row in installed["modules"]}
    names = [*PURE_MODULES] + [
        "program_foundry_closure_" + suffix
        for suffix in (
            "io",
            "profiles",
            "import",
            "reducers",
            "runtime",
            "contracts",
            "comparison",
            "core",
            "gepa",
            "journal",
            "jury",
        )
    ]
    for name in names:
        path = root / (name + ".py")
        with path.open("rb") as source:
            raw = source.read(51201)
        if hashlib.sha256(raw).hexdigest() != hashes[path.name]:
            raise ValueError("installed code changed")
        module = types.ModuleType(name)
        module.__file__ = str(path)
        sys.modules[name] = module
        exec(compile(raw, str(path), "exec", dont_inherit=True), module.__dict__)


def main() -> int:
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        return 2
    try:
        installed = installation()
    except (ValueError, OSError):
        return 2
    if sys.argv[1:] == ["--profile"]:
        print(json.dumps(installed, sort_keys=True, separators=(",", ":")))
        return 0
    if sys.argv[1:]:
        return 2
    # Only provisioned current modules; no cwd/site/evidence/installation search path.
    try:
        load_modules(installed)
    except (OSError, ValueError):
        return 2
    # Fixed captured deployment is intentional; there is no installed dspx import.
    from program_foundry_closure_io import (  # ty: ignore[unresolved-import]
        LIMITS,
        RESPONSE_SCHEMA,
        Rejected,
        Snapshot,
        canonical,
        decode,
        digest,
    )
    from program_foundry_closure_core import source_closure  # ty: ignore[unresolved-import]
    from program_foundry_closure_gepa import verify_gepa  # ty: ignore[unresolved-import]
    from program_foundry_closure_jury import verify_jury  # ty: ignore[unresolved-import]

    raw = sys.stdin.buffer.read(LIMITS["request_bytes"] + 1)
    try:
        request = decode(raw, LIMITS["request_bytes"])
        snapshot = Snapshot(request)
    except (Rejected, OSError, TypeError, KeyError, ValueError):
        return 2
    profile = installed["verifier_profile_sha256"]
    report = {
        "schema_version": RESPONSE_SCHEMA,
        "phase": "after_jury",
        "status": "invalid",
        "request_sha256": digest(raw),
        "verifier_profile_sha256": profile,
        "subject": request["subject"],
        "expected": request["expected"],
        "identities": dict.fromkeys(
            (
                "program_intent_sha256",
                "normalized_runtime_inputs_sha256",
                "source_manifest_sha256",
                "candidate_manifest_sha256",
                "comparison_sha256",
                "consumption_receipt_sha256",
            )
        ),
        "closure_inventory_sha256": None,
        "captured_files": 0,
        "captured_bytes": 0,
        "quality": {"origin": "unknown", "acceptance": "unknown"},
        "origins": dict.fromkeys(
            (
                "source_generated",
                "source_runtime",
                "oracle",
                "gepa_student",
                "gepa_reflection",
                "candidate_generated",
                "candidate_runtime",
                "jury",
            ),
            "unknown",
        ),
        "historical_authority": "unknown",
        "claim_ceiling": "historical_bytes_only",
        "review_eligible": False,
        "reason_codes": [],
        "limitations": [
            "acceptance_not_authenticated",
            "historical_lease_not_observed",
            "provider_output_authentication_not_retained",
            "oracle_request_payload_not_retained",
            "domain_fidelity_not_evaluated",
            "optimizer_not_executed",
        ],
        "non_authority": {
            "acceptance_authority": False,
            "release_authority": False,
            "activation_authority": False,
            "ak_called": False,
        },
    }
    try:
        if request["verifier_profile_sha256"] != profile:
            raise Rejected("verifier_profile_mismatch", "unsupported")
        state = source_closure(snapshot, report)
        state = verify_gepa(snapshot, state, report)
        verify_jury(snapshot, state, report)
        report["status"] = "verified"
        report["closure_inventory_sha256"] = snapshot.inventory_hash()
    except Rejected as exc:
        report["status"] = exc.status
        report["reason_codes"] = [exc.reason]
    except (KeyError, TypeError, ValueError, IndexError, UnicodeError):
        report["reason_codes"] = ["artifact_contract_shape"]
    finally:
        report["captured_files"] = len(snapshot.cache)
        report["captured_bytes"] = snapshot.total
        snapshot.close()
    sys.stdout.buffer.write(canonical(report) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
