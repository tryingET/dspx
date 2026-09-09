# summary: "Offline BERTScore adapter contracts and an explicitly opted-in real-model smoke."
# read_when:
#   - "Changing BERTScore adapter integration or its optional dependency behavior."

from __future__ import annotations

import builtins
import os
import runpy
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from dspx.adapters import eval as adapter


@pytest.mark.model
@pytest.mark.network
def test_bertscore_f1_basic() -> None:
    if os.environ.get("DSPX_BERTSCORE_REAL_MODEL") != "1":
        pytest.skip("requires exact DSPX_BERTSCORE_REAL_MODEL=1")
    pytest.importorskip("bert_score")
    refs = ["the cat sat on the mat"]
    cands = ["the cat sat on the mat"]
    val = adapter.bertscore_f1(refs, cands, lang="en")
    assert 0.0 <= val <= 1.0


@pytest.fixture
def fake_bert(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"imports": 0, "calls": [], "f1": [0.2, 0.8]}
    module = ModuleType("bert_score")

    def score(*args: Any, **kwargs: Any) -> tuple[Any, Any, Any]:
        state["calls"].append((args, kwargs))
        return [0.0, 0.0], [1.0, 1.0], state["f1"]

    monkeypatch.setattr(module, "score", score, raising=False)
    monkeypatch.setitem(sys.modules, "bert_score", module)
    original_import = builtins.__import__

    def counted_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "bert_score" or name.startswith("bert_score."):
            state["imports"] += 1
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", counted_import)
    return state


@pytest.mark.parametrize(
    "value", [None, "", "0", "true", "yes", "on", "01", " 1", "1 ", "2"]
)
def test_real_smoke_default_has_no_effects(
    monkeypatch: pytest.MonkeyPatch, fake_bert: dict[str, Any], value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("DSPX_BERTSCORE_REAL_MODEL", raising=False)
    else:
        monkeypatch.setenv("DSPX_BERTSCORE_REAL_MODEL", value)
    with pytest.raises(pytest.skip.Exception, match="requires exact"):
        test_bertscore_f1_basic()
    assert fake_bert["imports"] == 0
    assert fake_bert["calls"] == []


@pytest.mark.parametrize("opt_in", [False, True])
def test_collection_does_not_import_optional_module(
    monkeypatch: pytest.MonkeyPatch, fake_bert: dict[str, Any], opt_in: bool
) -> None:
    monkeypatch.setenv("DSPX_BERTSCORE_REAL_MODEL", "1" if opt_in else "0")
    runpy.run_path(__file__)
    assert fake_bert["imports"] == 0
    assert fake_bert["calls"] == []


def test_real_smoke_opt_in_uses_fake_only(
    monkeypatch: pytest.MonkeyPatch, fake_bert: dict[str, Any]
) -> None:
    monkeypatch.setenv("DSPX_BERTSCORE_REAL_MODEL", "1")
    test_bertscore_f1_basic()
    assert fake_bert["imports"] > 0
    assert len(fake_bert["calls"]) == 1


@pytest.mark.parametrize("tensor", [False, True])
@pytest.mark.parametrize(
    "options",
    [{}, {"model": "fake-model", "lang": None, "rescale_with_baseline": True}],
)
def test_argument_order_options_and_f1_aggregation(
    fake_bert: dict[str, Any], tensor: bool, options: dict[str, Any]
) -> None:
    if tensor:
        fake_bert["f1"] = SimpleNamespace(
            mean=lambda: SimpleNamespace(item=lambda: 0.5)
        )
    else:
        fake_bert["f1"] = ["0.2", "0.8"]
    refs = ("reference one", "reference two")
    cands = ("candidate one", "candidate two")
    assert adapter.bertscore_f1(refs, cands, **options) == pytest.approx(0.5)
    assert fake_bert["calls"] == [
        (
            (list(cands), list(refs)),
            {
                "model_type": options.get("model"),
                "lang": options.get("lang", "en"),
                "rescale_with_baseline": options.get("rescale_with_baseline", False),
                "verbose": False,
            },
        )
    ]


@pytest.mark.parametrize("metric", [adapter.bertscore_f1, adapter.bertscore_f1_macro])
@pytest.mark.parametrize(
    "refs,cands", [([], []), (["reference"], []), ([], ["candidate"])]
)
def test_empty_and_mismatch_before_import(
    fake_bert: dict[str, Any], metric: Any, refs: list[str], cands: list[str]
) -> None:
    if len(refs) != len(cands):
        with pytest.raises(ValueError, match="same length"):
            metric(refs, cands)
    else:
        assert metric(refs, cands) == 0.0
    assert fake_bert["imports"] == 0
    assert fake_bert["calls"] == []


@pytest.mark.parametrize(
    "options",
    [{}, {"model": "fake-model", "lang": "de", "rescale_with_baseline": True}],
)
def test_macro_delegates_without_changing_arguments(
    monkeypatch: pytest.MonkeyPatch, fake_bert: dict[str, Any], options: dict[str, Any]
) -> None:
    refs, cands = ["reference"], ["candidate"]
    calls = []

    def metric(actual_refs: Any, actual_cands: Any, **kwargs: Any) -> float:
        assert actual_refs is refs and actual_cands is cands
        calls.append(kwargs)
        return 0.375

    monkeypatch.setattr(adapter, "bertscore_f1", metric)
    assert adapter.bertscore_f1_macro(refs, cands, **options) == 0.375
    assert calls == [
        {"model": None, "lang": "en", "rescale_with_baseline": False} | options
    ]
    assert fake_bert["imports"] == 0
    assert fake_bert["calls"] == []
