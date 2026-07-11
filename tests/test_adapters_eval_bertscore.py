# summary: "Optional dependency smoke test for the adapter BERTScore F1 metric."
# read_when:
#   - "Changing BERTScore adapter integration or its optional dependency behavior."

import pytest


bert_score = pytest.importorskip("bert_score")


def test_bertscore_f1_basic() -> None:
    from dspx.adapters.eval import bertscore_f1

    refs = ["the cat sat on the mat"]
    cands = ["the cat sat on the mat"]
    val = bertscore_f1(refs, cands, lang="en")
    assert 0.0 <= val <= 1.0
