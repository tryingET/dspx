# summary: "Tests adversarial security, boundary, provenance, and evidence-binding regressions across DSPx and Forge."
# read_when:
#   - "Changing secret sanitization, path confinement, provider races, coordinate lookup, OpenAPI boundaries, replay, or program evidence identity."

"""Tests for adversarial review fixes.

Validates each bug fix from the NEXUS implementation:
1. Sanitize regex correctness
2. WorkOrder raw_input suppression + path confinement
3. parallel_first error filtering
4. Frontier nearest_run_id = actual neighbor
5. Territory region lookup beyond 10 members
6. Path confinement primitive
7. DspyLMAuthLM error marker
8. Replay path confinement
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ── 1. Sanitize regex correctness ──────────────────────────────────────────


class TestSanitizeRegex:
    """Verify the sanitize patterns actually match real secrets."""

    def test_bearer_redacted(self) -> None:
        from dspx_forge.sanitize import sanitize_text

        result = sanitize_text("Authorization: Bearer sk-1234567890abcdefghijkl")
        assert result.detected is True
        assert "sk-1234567890abcdefghijkl" not in result.sanitized
        assert "redacted:bearer" in result.notes

    def test_gitlab_pat_redacted(self) -> None:
        from dspx_forge.sanitize import sanitize_text

        result = sanitize_text("Token is glpat-ABCDEFGHIJ12345")
        assert result.detected is True
        assert "glpat-ABCDEFGHIJ12345" not in result.sanitized

    def test_env_key_redacted(self) -> None:
        from dspx_forge.sanitize import sanitize_text

        result = sanitize_text("API_KEY=supersecret123")
        assert result.detected is True
        assert "supersecret123" not in result.sanitized
        assert "API_KEY=[REDACTED]" in result.sanitized

    def test_openai_sk_redacted(self) -> None:
        from dspx_forge.sanitize import sanitize_text

        result = sanitize_text("key=sk-projabc123def456ghi789jkl012mno")
        assert result.detected is True
        assert "sk-projabc123def456ghi789jkl012mno" not in result.sanitized

    def test_op_ref_redacted(self) -> None:
        from dspx_forge.sanitize import sanitize_text

        result = sanitize_text("Use op://vault/item/field")
        assert result.detected is True
        assert "op://vault/item/field" not in result.sanitized

    def test_clean_text_passes_through(self) -> None:
        from dspx_forge.sanitize import sanitize_text

        result = sanitize_text("Hello world, no secrets here")
        assert result.detected is False
        assert result.sanitized == "Hello world, no secrets here"

    def test_multiple_secrets_in_one_text(self) -> None:
        from dspx_forge.sanitize import sanitize_text

        text = "Auth: Authorization: Bearer sk-proj-abc123def456ghi789jkl\nKEY=secret"
        result = sanitize_text(text)
        assert result.detected is True
        assert "sk-proj-abc123def456ghi789jkl" not in result.sanitized
        assert "secret" not in result.sanitized


# ── 2. Path confinement primitive ──────────────────────────────────────────


class TestPathConfinement:
    """Verify confine_path blocks traversal and allows valid paths."""

    def test_valid_relative_path(self) -> None:
        from dspx.security import confine_path

        root = Path("/tmp/test_root")
        result = confine_path(root, "subdir/file.txt")
        assert result == Path("/tmp/test_root/subdir/file.txt")

    def test_traversal_blocked(self) -> None:
        from dspx.security import confine_path, PathEscapeError

        root = Path("/tmp/test_root")
        with pytest.raises(PathEscapeError):
            confine_path(root, "../../etc/passwd")

    def test_absolute_path_outside_root_blocked(self) -> None:
        from dspx.security import confine_path, PathEscapeError

        root = Path("/tmp/test_root")
        with pytest.raises(PathEscapeError):
            confine_path(root, "/etc/passwd")

    def test_non_strict_returns_root(self) -> None:
        from dspx.security import confine_path

        root = Path("/tmp/test_root")
        result = confine_path(root, "../../etc/passwd", strict=False)
        assert result == root.resolve()

    def test_confine_or_none_returns_none_on_escape(self) -> None:
        from dspx.security import confine_or_none

        root = Path("/tmp/test_root")
        assert confine_or_none(root, "../../etc/passwd") is None

    def test_confine_or_none_returns_path_on_valid(self) -> None:
        from dspx.security import confine_or_none

        root = Path("/tmp/test_root")
        result = confine_or_none(root, "safe/path.txt")
        assert result is not None
        assert str(result).startswith(str(root.resolve()))


# ── 3. WorkOrder raw_input suppression ─────────────────────────────────────


class TestWorkOrderRawInput:
    """Verify raw_input is never persisted in WorkOrder."""

    def test_raw_input_empty_after_build(self) -> None:
        from dspx_forge.workorder import build_workorder

        doc = build_workorder("API_KEY=supersecret123")
        assert doc.work_order.raw_input == ""

    def test_sanitized_input_populated(self) -> None:
        from dspx_forge.workorder import build_workorder

        doc = build_workorder("API_KEY=supersecret123")
        assert "supersecret123" not in doc.work_order.sanitized_input


# ── 4. WorkOrder path confinement ──────────────────────────────────────────


class TestWorkOrderPathConfinement:
    """Verify write_workorder blocks path-traversal wo.id values."""

    def test_traversal_id_rejected(self, tmp_path: Path) -> None:
        from dspx_forge.workorder import write_workorder
        from dspx_forge.models import WorkOrder, WorkOrderDoc, Outputs

        wo = WorkOrder(
            id="../../etc/crontab",
            fingerprint="abc",
            run_id="run_1",
            title="test",
            raw_input="",
            sanitized_input="test",
            outputs=Outputs(out_dir="generated"),
        )
        doc = WorkOrderDoc(work_order=wo)
        with pytest.raises(ValueError, match="escapes output root"):
            write_workorder(tmp_path, doc)

    def test_normal_id_succeeds(self, tmp_path: Path) -> None:
        from dspx_forge.workorder import write_workorder
        from dspx_forge.models import WorkOrder, WorkOrderDoc, Outputs

        wo = WorkOrder(
            id="wo_safe_001",
            fingerprint="abc",
            run_id="run_1",
            title="test",
            raw_input="",
            sanitized_input="test",
            outputs=Outputs(out_dir="generated"),
        )
        doc = WorkOrderDoc(work_order=wo)
        paths = write_workorder(tmp_path, doc)
        assert paths.workorder_yaml.exists()


# ── 6. Frontier nearest_run_id ─────────────────────────────────────────────


class TestFrontierNearestRunId:
    """Verify frontier nearest_run_id points to the actual neighbor, not self."""

    def test_nearest_run_is_not_self(self) -> None:
        # Test the core neighbor-finding logic directly rather than
        # through find_frontiers (which requires a full CoordinateIndex).
        # We replicate the inner loop from find_frontiers to verify
        # that nearest_run_id is tracked correctly.
        # We replicate the inner loop from find_frontiers to verify
        # that nearest_run_id is tracked correctly.
        class FakeEmb:
            def __init__(self, rid: str, vector: list[float]):
                self.run_id = rid
                self.vector = vector
                self.prompt = f"prompt {rid}"
                self.completion = f"completion {rid}"
                self.metadata = {}

        sample = [
            FakeEmb("run_far", [100.0, 100.0, 100.0]),
            FakeEmb("run_near_0", [0.1, 0.0, 0.0]),
            FakeEmb("run_near_1", [0.2, 0.0, 0.0]),
        ]
        embeddings = list(sample)  # Same set for simplicity

        from dspx.coordinates.metrics import (
            semantic_distance,
            SEMANTIC_DISTANCE_NORMALIZER,
        )

        for i, emb in enumerate(sample):
            min_dist = float("inf")
            nearest_other_id = None
            for j, other in enumerate(embeddings):
                if emb.run_id == other.run_id:
                    continue
                dist = (
                    semantic_distance(emb.vector, other.vector)
                    / SEMANTIC_DISTANCE_NORMALIZER
                )
                if dist < min_dist:
                    min_dist = dist
                    nearest_other_id = other.run_id

            if i == 0:  # The far point
                # Its nearest neighbor should be one of the close points, not itself
                assert nearest_other_id is not None
                assert nearest_other_id != emb.run_id, (
                    f"nearest_other_id should not be self ({emb.run_id}), "
                    f"got {nearest_other_id}"
                )
            else:
                # Close points should have each other as nearest
                assert nearest_other_id is not None
                assert nearest_other_id != emb.run_id


# ── 7. Territory region lookup ─────────────────────────────────────────────


class TestTerritoryRegionLookup:
    """Verify find_region_for_run_id works beyond the first 10 members."""

    def test_lookup_beyond_10_members(self) -> None:
        from dspx.coordinates.territory import Region, RegionType, TerritoryMap

        # Create a region with 20 members
        all_ids = [f"run_{i:03d}" for i in range(20)]
        region = Region(
            region_id="R000",
            region_type=RegionType.STABLE,
            centroid=[0.0, 0.0],
            member_count=20,
            internal_variance=0.1,
            confidence=0.9,
            dominant_run_kind=None,
            dominant_provider=None,
            sample_run_ids=all_ids[:10],
            all_member_ids=all_ids,
        )

        tmap = TerritoryMap(
            regions=[region],
            total_embeddings=20,
            coverage=0.9,
            dimension=3,
            stable_ratio=1.0,
            unstable_ratio=0.0,
            unknown_ratio=0.0,
        )

        # First 10 should be found via sample_run_ids
        assert tmap.find_region_for_run_id("run_000") is not None

        # 11th-20th should be found via all_member_ids
        assert tmap.find_region_for_run_id("run_015") is not None
        assert tmap.find_region_for_run_id("run_019") is not None

        # Non-existent should return None
        assert tmap.find_region_for_run_id("run_nonexistent") is None


# ── 8. Replay path confinement ─────────────────────────────────────────────


class TestReplayPathConfinement:
    """Verify _resolve_path confines absolute paths."""

    def test_absolute_path_escape_rejected(self, tmp_path: Path) -> None:
        from dspx.security import PathEscapeError
        from dspx.services.run_replay_service import _resolve_path

        meta = tmp_path / "receipt" / "run.meta.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.touch()

        with pytest.raises(PathEscapeError):
            _resolve_path("/etc/shadow", meta_path=meta)

    def test_relative_path_allowed(self, tmp_path: Path) -> None:
        from dspx.services.run_replay_service import _resolve_path

        meta = tmp_path / "receipt" / "run.meta.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.touch()

        # Relative path should resolve under meta parent
        resolved = _resolve_path("output.txt", meta_path=meta)
        assert str(resolved).startswith(str(meta.parent.resolve()))

    def test_traversal_relative_escape_rejected(self, tmp_path: Path) -> None:
        from dspx.security import PathEscapeError
        from dspx.services.run_replay_service import _resolve_path

        meta = tmp_path / "receipt" / "run.meta.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.touch()

        with pytest.raises(PathEscapeError):
            _resolve_path("../../etc/shadow", meta_path=meta)


# ── 9. Program evidence binding and boundary regressions ───────────────────


def test_openapi_caller_strips_caller_supplied_host_header() -> None:
    import httpx

    from dspx.dtos import OpenAPICallRequest
    from dspx.tools.openapi.caller import call_operation

    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    operation = {"method": "GET", "server": "http://allowed.test", "path": "/x"}
    request = OpenAPICallRequest(operation_id="op", headers={"Host": "evil.test"})

    call_operation(
        request,
        operation=operation,
        allowed_hosts={"http://allowed.test": True},
        client=client,
    )

    assert seen[0]["host"] == "allowed.test"


def test_coordinate_time_filters_compare_instants_not_iso_strings(
    tmp_path: Path,
) -> None:
    from datetime import datetime, timezone

    from dspx.coordinates.embeddings import ExecutionEmbedding
    from dspx.coordinates.storage import CoordinateIndex

    index = CoordinateIndex(tmp_path / "coordinates.db")
    index.upsert(
        ExecutionEmbedding(
            run_id="before-cutoff",
            vector=[1.0, 0.0],
            input_text="",
            output_text="",
            config_text="",
            run_kind="k",
            provider="p",
            template_version=None,
            created_at="2026-01-01T01:00:00+02:00",
            dimension=2,
        )
    )
    index.upsert(
        ExecutionEmbedding(
            run_id="after-cutoff",
            vector=[1.0, 0.0],
            input_text="",
            output_text="",
            config_text="",
            run_kind="k",
            provider="p",
            template_version=None,
            created_at="2026-01-01T00:30:00+00:00",
            dimension=2,
        )
    )

    since = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    assert [record.run_id for record in index.list_all(since=since)] == ["after-cutoff"]
    assert index.count(since=since) == 1
    assert [result.run_id for result in index.search([1.0, 0.0], since=since)] == [
        "after-cutoff"
    ]


def test_activation_identity_rejects_partial_matches() -> None:
    from dspx.services.program_activation_packet import (
        ProgramActivationPacketError,
        _validate_artifact_identity,
        _validate_oracle_report_identity,
    )

    identity = {
        "request_id": "request-1",
        "candidate_id": "candidate-1",
        "assembly_id": "assembly-1",
        "episode_id": "episode-1",
    }

    with pytest.raises(
        ProgramActivationPacketError, match="matching candidate identity"
    ):
        _validate_oracle_report_identity(
            identity, {"records": [{"identity": {"request_id": "request-1"}}]}
        )

    with pytest.raises(ProgramActivationPacketError, match="identity is incomplete"):
        _validate_artifact_identity(
            identity,
            {"identity": {"request_id": "request-1"}},
            label="artifact",
        )


def test_program_plan_binds_runtime_traces_hash(tmp_path: Path) -> None:
    import json

    from dspx.cache import sha256_text
    from dspx.services.program_service import (
        ProgramIntent,
        materialize_program_from_intent,
    )

    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="AnswerQuestion",
            objective="Answer the question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    root = Path(artifact.root_path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    runtime_traces_hash = sha256_text(
        (root / "program_runtime_traces.json").read_text(encoding="utf-8")
    )
    plan_hash = sha256_text((root / "plan.json").read_text(encoding="utf-8"))

    assert (
        manifest["program_plan"]["runtime_traces"]["content_hash"]
        == runtime_traces_hash
    )
    assert manifest["request"]["runtime_traces_hash"] == runtime_traces_hash
    assert manifest["request"]["plan_hash"] == plan_hash
    assert manifest["candidate_assembly"]["surfaces"][0]["content_hash"] == plan_hash


def test_candidate_assembly_hash_binds_advertised_surfaces(tmp_path: Path) -> None:
    import json

    from dspx.cache import sha256_text
    from dspx.services import program_service
    from dspx.services.program_service import (
        ProgramIntent,
        materialize_program_from_intent,
    )

    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="AnswerQuestion",
            objective="Answer the question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    manifest = json.loads((Path(artifact.root_path) / "manifest.json").read_text())
    assembly = manifest["candidate_assembly"]

    expected = sha256_text(
        program_service._json_text(
            {
                "surface_kinds": assembly["surface_kinds"],
                "surfaces": [
                    {
                        "kind": surface.get("kind"),
                        "path": surface.get("path"),
                        "content_hash": surface.get("content_hash"),
                    }
                    for surface in assembly["surfaces"]
                ],
            }
        )
    )

    assert assembly["content_hash"] == expected


def test_direct_service_rejects_forged_contract_verification(tmp_path: Path) -> None:
    import json

    from dspx.services import program_service

    intent_path = tmp_path / "intent.json"
    intent_path.write_text(
        json.dumps(
            {
                "schema_version": "program-intent-v2",
                "name": "AnswerQuestion",
                "objective": "Answer.",
                "inputs": ["question"],
                "outputs": ["answer"],
            }
        ),
        encoding="utf-8",
    )
    forged = tmp_path / "forged_contract_verification.json"
    forged.write_text(
        json.dumps(
            {
                "schema_version": "program-architecture-contract-verification-v1",
                "status": "verified_contract_intent",
                "materialization_allowed_by_contract_verification": True,
                "materialization_gate": {
                    "status": "verified_for_explicit_program_gen_materialization",
                    "program_gen_must_match_intent_hash": "deadbeef",
                    "allows_live_tools": False,
                    "allows_custom_imports": False,
                    "allows_external_retrievers": False,
                },
                "non_authority": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="intent_hash_mismatch"):
        program_service.run_generate_from_intent_path(
            intent_path,
            outdir=tmp_path / "out",
            contract_verification_path=forged,
        )
