"""Final identity HOLD: canonical precedence, comparison/jury agreement, and custody.

IdentityView is an explicit component-test double over saved inputs: hashes still
refer to the original bytes, so its successes are NOT captured-closure proofs.
Separate isolated-capsule mutants below preserve the actual external root anchors.
"""

import copy
import importlib

import pytest
import test_program_foundry_closure_semantics as shared

pure = shared.pure
saved = shared.saved

ORDER = {
    "request_id": (
        "request",
        "candidate_assembly",
        "execution_episode",
        "receipt_bundle",
    ),
    "candidate_id": ("candidate_assembly", "execution_episode", "receipt_bundle"),
    "assembly_id": ("candidate_assembly", "execution_episode", "receipt_bundle"),
    "episode_id": ("execution_episode", "receipt_bundle"),
}


def shadow(manifest, field):
    for block in ORDER[field][1:]:
        manifest[block][field] = block + "-shadow-" + field
    return manifest


class IdentityView:
    def __init__(self, snapshot, manifest_path, comparison_path, field, side, bad):
        self.snapshot = snapshot
        self.manifest_path = manifest_path
        self.comparison_path = comparison_path
        self.field = field
        self.side = side
        self.bad = bad

    def __getattr__(self, name):
        return getattr(self.snapshot, name)

    def json(self, path, *args):
        value = copy.deepcopy(self.snapshot.json(path, *args))
        if path == self.manifest_path:
            shadow(value, self.field)
        elif path == self.manifest_path + ".meta.json":
            # Mirror the in-memory identity projection in embedded meta fields.
            # Verifier guards run unchanged; hashes still describe original bytes.
            for block in ORDER[self.field][1:]:
                value["program_" + block][self.field] = block + "-shadow-" + self.field
        elif path == self.comparison_path and self.bad in {"comparison", "both"}:
            value[self.side + "_identity"][self.field] = (
                "receipt_bundle-shadow-" + self.field
            )
        elif path.endswith("/comparison-jury-results.json") and self.bad in {
            "jury",
            "both",
        }:
            value["identity"][self.field] = "receipt_bundle-shadow-" + self.field
        return value


@pytest.mark.parametrize("side", ["source", "candidate"])
@pytest.mark.parametrize("field", ORDER)
def test_canonical_precedence_matches_both_original_producers(saved, pure, side, field):
    from dspx.services.program_refinement_comparison import (
        _identity_from_manifest as comparison_identity,
    )
    from dspx.services.program_model_jury_execution import (
        _identity_from_manifest as jury_identity,
    )

    _, request = saved
    contracts = importlib.import_module("program_foundry_closure_contracts")
    relative = (
        "foundry/"
        + (
            "candidate"
            if side == "source"
            else "gepa-experiment/materialized-candidate"
        )
        + "/manifest.json"
    )
    alias = next(x["aliases"][0] for x in request["locators"] if x["path"] == relative)
    s = pure.Snapshot(request)
    try:
        manifest = shadow(copy.deepcopy(s.json(alias)), field)
        # Exercise every fallback precedence, not only top-level vs receipt_bundle.
        for block in ORDER[field]:
            expected = comparison_identity(manifest)
            assert contracts.identity(manifest) == expected == jury_identity(manifest)
            assert expected[field] == manifest[block][field]
            if block != "receipt_bundle":
                assert expected[field] != manifest["receipt_bundle"][field]
            manifest[block][field] = None
    finally:
        s.close()


@pytest.mark.parametrize("side", ["source", "candidate"])
@pytest.mark.parametrize("field", ORDER)
@pytest.mark.parametrize("bad", [None, "comparison", "jury", "both"])
def test_comparison_and_jury_use_canonical_not_shadow_identity(
    saved, pure, side, field, bad
):
    from dspx.services.program_refinement_comparison import (
        _identity_from_manifest as comparison_identity,
    )
    from dspx.services.program_model_jury_execution import (
        _identity_from_manifest as jury_identity,
    )

    _, request = saved
    s = pure.Snapshot(request)
    report = {"origins": {}, "identities": {}, "quality": {}}
    core = importlib.import_module("program_foundry_closure_core")
    gepa = importlib.import_module("program_foundry_closure_gepa")
    jury = importlib.import_module("program_foundry_closure_jury")
    try:
        state = core.source_closure(s, report)
        cp = state["root"] + "/gepa-experiment/materialized-candidate/manifest.json"
        comparison_path = state["root"] + "/gepa-experiment/candidate-comparison.json"
        manifest_path = state["source_path"] if side == "source" else cp
        view = IdentityView(s, manifest_path, comparison_path, field, side, bad)
        expected = comparison_identity(view.json(manifest_path))
        assert expected == jury_identity(view.json(manifest_path))
        assert expected[field] != view.json(manifest_path)["receipt_bundle"][field]
        if bad in {"comparison", "both"}:
            # Even a matching shadow comparison + jury pair cannot cross the
            # canonical-manifest gate. This executes the actual patched loop.
            with pytest.raises(pure.Rejected, match="^comparison_manifest_identity$"):
                gepa.verify_gepa(view, state, report)
            return
        state = gepa.verify_gepa(view, state, report)
        assert state["comparison"][side + "_identity"] == expected
        if bad == "jury":
            assert (
                view.json(
                    state["root"] + "/gepa-experiment/comparison-jury-results.json"
                )["identity"]
                != state["comparison"]["candidate_identity"]
            )
            with pytest.raises(pure.Rejected, match="^equality_mismatch$"):
                jury.verify_jury(view, state, report)
        else:
            jury.verify_jury(view, state, report)
            assert state["comparison"]["candidate_identity"] == jury_identity(
                view.json(cp)
            )
    finally:
        s.close()


@pytest.mark.parametrize("side", ["source", "candidate", "jury"])
@pytest.mark.parametrize("field", ORDER)
def test_isolated_identity_mutants_do_not_reanchor_historical_roots(
    saved, pure, tmp_path, side, field
):
    root, request = shared.copied(saved, tmp_path)
    anchors = copy.deepcopy((request["subject"], request["expected"]))
    relative = "foundry/gepa-experiment/" + (
        "comparison-jury-results.json"
        if side == "jury"
        else "candidate-comparison.json"
    )
    key = "identity" if side == "jury" else side + "_identity"
    shared.change(
        root,
        request,
        relative,
        lambda p: p[key].update({field: "receipt_bundle-shadow-" + field}),
    )
    # This separately proves immutable-root custody rejection. It intentionally
    # does not label a hash mismatch as proof of the inner semantic identity gate.
    shared.rejected(request)
    assert (request["subject"], request["expected"]) == anchors
