# summary: "Tests deterministic module synthesis outputs against the golden corpus."
# read_when:
#   - "Changing module synthesis templates, ranking, hashes, or promotion receipts."

from __future__ import annotations

from pathlib import Path

from dspx.cache import sha256_text
from dspx.services.module_synthesis_corpus import (
    load_module_synthesis_cases,
    run_module_synthesis_corpus_case,
)


_CORPUS = Path(__file__).parent / "golden" / "module_synthesis_cases.json"


def test_module_synthesis_golden_corpus(tmp_path: Path) -> None:
    cases = load_module_synthesis_cases(_CORPUS)
    workspace_root = tmp_path / "module-synthesis-golden"

    for case in cases:
        run = run_module_synthesis_corpus_case(case, workspace_root=workspace_root)
        artifact = run.artifact
        metadata = artifact.metadata

        for token in case.get("must_contain") or []:
            assert token in artifact.code, (run.case_name, token)

        expected_hash = str(case.get("sha256") or "")
        assert expected_hash, f"missing golden hash for {run.case_name}"
        assert sha256_text(artifact.code) == expected_hash

        assert metadata["candidate_count"] == case["expected_candidate_count"]
        assert metadata["selected_candidate_rank"] == 1
        assert metadata["promotion_status"] == case["expected_promotion_status"]
        assert metadata["promotion_outcome"] == case["expected_promotion_outcome"]
        assert run.selected_variant_id == case["expected_selected_variant"]
        assert list(run.ranked_variant_ids) == case["expected_ranked_variants"]
        assert run.selection_integrity is True
        assert run.receipt_coverage is True
        assert run.promotion_receipt_coverage is True
        if run.promote:
            assert run.promotion_target is not None and run.promotion_target.exists()
