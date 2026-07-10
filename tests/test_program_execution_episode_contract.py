from __future__ import annotations

from dspx.services.program_execution_episode import build_program_execution_episode
from dspx.services.program_intent import ProgramIntent


def _passed_harness(filename: str) -> dict[str, object]:
    return {"returncode": 0, "command": ["python", filename]}


def test_execution_episode_builder_preserves_runtime_object_boundary() -> None:
    intent = ProgramIntent(
        name="AnswerQuestion",
        objective="Answer from supplied context.",
        inputs=["question"],
        outputs=["answer"],
        metric="exact_match",
    )
    evaluation_sources = [
        {
            "kind": "examples",
            "source_kind": "inline_examples",
            "summary": {"status": "passed", "total": 1, "passed": 1},
        }
    ]
    evidence_summary = {
        "status": "passed",
        "source_count": 1,
        "total": 1,
        "passed": 1,
    }

    episode = build_program_execution_episode(
        ids={
            "episode_id": "episode-1",
            "request_id": "request-1",
            "candidate_id": "candidate-1",
            "assembly_id": "assembly-1",
        },
        intent=intent,
        generated_file_names=["program.py", "execution_episode.json"],
        smoke_result=_passed_harness("eval_smoke.py"),
        jury_result=_passed_harness("eval_jury.py"),
        promotion_result=_passed_harness("eval_promotion.py"),
        examples_result=_passed_harness("eval_examples.py"),
        behavior_episode_result=None,
        behavior_episode_hash=None,
        behavior_episode_payload=None,
        dataset_manifest_hash=None,
        dataset_manifest_payload=None,
        dataset_split_results={},
        dataset_split_behavior_payloads={},
        dataset_split_behavior_hashes={},
        behavior_results_hash="behavior-hash",
        behavior_summary={"status": "passed", "total": 1, "passed": 1},
        behavior_results_payload={"provider": {"name": "stub"}},
        oracle_evidence_hash="oracle-hash",
        oracle_readability_summary={"behavior_status": "passed"},
        oracle_readability_facets={"failure_mode_count": 0},
        evaluation_sources=evaluation_sources,
        behavior_evidence_summary=evidence_summary,
    )

    assert episode["schema_version"] == "program-execution-episode-v1"
    assert episode["episode_id"] == "episode-1"
    assert episode["evaluation_sources"] == evaluation_sources
    assert episode["evaluation_sources"] is not evaluation_sources
    assert episode["behavior_evidence_summary"] == evidence_summary
    assert episode["behavior_evidence_summary"] is not evidence_summary
    assert episode["checks"]["smoke"]["status"] == "passed"
    assert episode["runtime_conditions"]["providers"] == {"examples": {"name": "stub"}}
    assert episode["non_authority"]["external_mutation"] is False
    assert episode["non_authority"]["automatic_promotion"] is False
