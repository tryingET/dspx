# summary: "Defines generated program artifact names protected from sidecar overwrites."
# read_when:
#   - "Adding generated program files or tightening sidecar output collision protection."

from __future__ import annotations

# Generated candidate artifact basenames that sidecar-writing commands must not
# overwrite. Keep this list conservative: it includes deterministic files written
# directly by program-gen plus behavior/dataset files written by generated
# harnesses during materialization.
PROTECTED_PROGRAM_ARTIFACT_NAMES = {
    "manifest.json",
    "manifest.json.meta.json",
    "intent.json",
    "intent_normalization.json",
    "plan.json",
    "module_surfaces.json",
    "program_runtime_outcomes.json",
    "program_runtime_traces.json",
    "program_tool_contracts.json",
    "program_capability_registry.json",
    "generated_module_policy.json",
    "signature.py",
    "module.py",
    "program.py",
    "direct_run.py",
    "eval_smoke.py",
    "eval_jury.py",
    "eval_promotion.py",
    "eval_examples.py",
    "eval_behavior.py",
    "eval_train.py",
    "eval_validation.py",
    "eval_test.py",
    "examples.json",
    "dataset_manifest.json",
    "execution_episode.json",
    "behavior_episode.json",
    "behavior_results.json",
    "behavior_results.train.json",
    "behavior_results.validation.json",
    "behavior_results.test.json",
    "oracle_evidence.json",
    "jury.json",
    "jury_selection.json",
    "jury_rubric.json",
    "promotion_review.json",
    "promotion_adjudication_request.json",
    "promotion_decision_template.json",
    "promotion_review_refined.json",
}


def is_protected_program_artifact_name(name: str) -> bool:
    return name in PROTECTED_PROGRAM_ARTIFACT_NAMES
