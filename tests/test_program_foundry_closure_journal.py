"""Saved Copilot journal-only proof; NOT a package/import/full-closure positive."""

import copy
import hashlib
import importlib
import os
from pathlib import Path

import pytest

from test_program_foundry_closure_boundaries import small_request

import test_program_foundry_closure_check as shared

pure = shared.pure


def test_saved_copilot_family_only_and_profile_tamper(tmp_path, pure):
    raw = os.environ.get("DSPX_CLOSURE_JOURNAL_ROOT")
    if raw:
        root = original = Path(raw)
    else:
        from test_program_foundry_closure_copilot_fixture import ORIGINAL_ROOT, extract

        root = tmp_path / "frozen-copilot"
        root.mkdir(mode=0o700)
        extract(root)
        original = Path(ORIGINAL_ROOT)
    request = small_request(pure, tmp_path)
    request["roots"].append(str(root))
    files = [
        root / "comparison-jury-receipt.json",
        root / "comparison-jury-results.json",
        root / "comparison-jury-attempt.json",
    ]
    files += sorted(x for x in (root / "provider-outcomes").rglob("*") if x.is_file())
    before = {}
    for path in files:
        assert (
            not path.is_symlink() and path.stat().st_size <= pure.LIMITS["json_bytes"]
        )
        content = path.read_bytes()
        hashed = hashlib.sha256(content).hexdigest()
        before[path] = hashed
        request["locators"].append(
            {
                "sha256": hashed,
                "bytes": len(content),
                "root": 1,
                "path": str(path.relative_to(root)),
                "aliases": [str(original / path.relative_to(root))],
            }
        )
    root = original  # verification uses original aliases, never physical path inference
    module = importlib.import_module("program_foundry_closure_journal")
    s = pure.Snapshot(request)
    try:
        receipt = s.json(str(root / "comparison-jury-receipt.json"))
        result = s.json(str(root / "comparison-jury-results.json"))
        attempt_hash = s.hash(str(root / "comparison-jury-attempt.json"))
        module.journals(
            s, receipt["execution_request"], result, attempt_hash, str(root)
        )
        altered = copy.deepcopy(result)
        altered["jury"]["provider_config"]["source_identity_sha256"] = "0" * 64
        with pytest.raises(pure.Rejected):
            module.journals(
                s, receipt["execution_request"], altered, attempt_hash, str(root)
            )
        altered["jury"]["provider_config"]["owner_commit"] = "0" * 40
        with pytest.raises(
            pure.Rejected, match="historical_owner_unsupported"
        ) as error:
            module.journals(
                s, receipt["execution_request"], altered, attempt_hash, str(root)
            )
        assert error.value.status == "unsupported"
    finally:
        s.close()
    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files
    } == before
