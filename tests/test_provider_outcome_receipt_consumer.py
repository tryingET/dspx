from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, cast
from weakref import WeakKeyDictionary

import pytest

from dspx.services.provider_outcome_receipt_contract import (
    EmpiricalDisposition,
    ProviderOutcomeConsumerError,
    ReceiptReservation,
    SemanticOutcome,
)
from dspx.services.provider_outcome_receipt_identity import (
    OWNER_COMMIT,
    OWNER_TREE,
    ExpectedDependency,
    ExpectedOwnerSource,
    VerifiedOwnerArtifact,
    _fixture_owner_artifact,
    verify_owner_source,
)
from dspx.services.provider_outcome_receipt_journal import ReceiptJournal
from dspx.services.provider_outcome_receipt_reducer import (
    reduce_journal,
    reduce_verified_chain,
    verify_receipt_chain,
)

_HASH = "a" * 64
_RESPONSE_HASH = "b" * 64
_ENDPOINT_HASH = "c" * 64


@dataclass(frozen=True, slots=True)
class FixtureOutcomeReceiptEvent:
    kind: str
    gate_ordinal: int | None = None
    status_class: int | None = None
    error_class: str | None = None
    protocol_event: str | None = None
    response_id_sha256: str | None = None
    observed_model: str | None = None


@dataclass(frozen=True, slots=True)
class FixtureProviderOutcomeReceipt:
    logical_request_id: str
    semantic_request_sha256: str
    sink: Callable[[FixtureOutcomeReceiptEvent], None]

    def emit(self, event: FixtureOutcomeReceiptEvent) -> None:
        self.sink(event)


_RECEIPTS: WeakKeyDictionary[ReceiptJournal, FixtureProviderOutcomeReceipt] = (
    WeakKeyDictionary()
)


def _artifact(
    *, revalidator=lambda: None, event_type=FixtureOutcomeReceiptEvent
) -> VerifiedOwnerArtifact:
    module_names = {
        "package_init",
        "lm",
        "codex_stream",
        "codex_stream_support",
        "outcome_receipt",
        "outcome_receipt_state",
        "outcome_receipt_runtime",
        "outcome_receipt_transport",
    }
    dependencies = {
        name: {
            "version": "1.0.0",
            "locked_wheel_sha256": _HASH,
            "payload_count": 1,
            "payload_sha256": _HASH,
            "record_sha256": _HASH,
        }
        for name in ("dspy", "litellm", "httpx", "httpcore")
    }
    return _fixture_owner_artifact(
        source_identity={
            "owner": "tryinget-dspy-lm-auth",
            "version": "0.1.5",
            "commit": OWNER_COMMIT,
            "tree": OWNER_TREE,
            "lock_sha256": _HASH,
            "module_sha256": {name: _HASH for name in module_names},
        },
        dependency_identity=dependencies,
        event_type=event_type,
        receipt_type=FixtureProviderOutcomeReceipt,
        revalidator=revalidator,
    )


def _reservation(
    artifact: VerifiedOwnerArtifact,
    *,
    mode: Literal["sync", "async"] = "sync",
) -> ReceiptReservation:
    return ReceiptReservation(
        consumer_task_id=4678,
        ledger_sha256=_HASH,
        process_id="fixture-process-1",
        case_id="fixture-case-1",
        logical_request_id="fixture-request-1",
        transport_gate_id="fixture-gate-1",
        semantic_request_sha256=_HASH,
        contract_sha256=_HASH,
        mode=mode,
        requested_route="codex:gpt-5.6-sol",
        resolved_route="openai:gpt-5.6-sol",
        endpoint_origin_sha256=_ENDPOINT_HASH,
        source_identity=artifact.source_identity,
        dependency_identity=artifact.dependency_identity,
    )


def _journal(
    tmp_path: Path, artifact: VerifiedOwnerArtifact | None = None
) -> ReceiptJournal:
    tmp_path.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp_path.chmod(0o700)
    artifact = artifact or _artifact()
    journal = ReceiptJournal.create(
        tmp_path / "receipt", _reservation(artifact), artifact
    )
    _RECEIPTS[journal] = cast(FixtureProviderOutcomeReceipt, journal.provider_receipt())
    return journal


def _receipt(journal: ReceiptJournal) -> FixtureProviderOutcomeReceipt:
    return _RECEIPTS[journal]


def _emit(journal: ReceiptJournal, event: FixtureOutcomeReceiptEvent) -> None:
    _receipt(journal).emit(event)


def _reduce(
    journal: ReceiptJournal,
    *,
    semantic_outcome: SemanticOutcome = "not_evaluated",
):
    chain = verify_receipt_chain(journal.load_verified())
    return reduce_verified_chain(chain, semantic_outcome=semantic_outcome)


def _event(kind: str, **kwargs) -> FixtureOutcomeReceiptEvent:
    return FixtureOutcomeReceiptEvent(kind=kind, **kwargs)


def _completed_trace(journal: ReceiptJournal, *, retry: bool = False) -> None:
    events = [
        _event("wrapper_request_accepted"),
        _event("transport_gate_entered", gate_ordinal=1),
        _event("transport_effect_pending", gate_ordinal=1),
        _event("transport_entered", gate_ordinal=1),
        _event("http_response_observed", gate_ordinal=1, status_class=2),
    ]
    if retry:
        events.extend(
            [
                _event("transport_gate_entered", gate_ordinal=2),
                _event(
                    "retry_blocked_before_transport",
                    gate_ordinal=2,
                    error_class="retry_blocked",
                ),
            ]
        )
    events.extend(
        [
            _event(
                "parsed_protocol_event_observed",
                protocol_event="response.completed",
                response_id_sha256=_RESPONSE_HASH,
            ),
            _event(
                "provider_response_completed",
                status_class=2,
                response_id_sha256=_RESPONSE_HASH,
                observed_model="gpt-5.6-sol",
            ),
        ]
    )
    for event in events:
        _emit(journal, event)


def _private_mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def test_journal_is_private_canonical_hash_chained_and_persistence_only(tmp_path):
    journal = _journal(tmp_path)
    _completed_trace(journal)

    root = tmp_path / "receipt"
    assert _private_mode(root) == 0o700
    assert _private_mode(root / "events") == 0o700
    assert _private_mode(root / "reservation.json") == 0o600
    members = sorted((root / "events").iterdir())
    assert [path.name for path in members] == [
        f"{index:06d}.json" for index in range(7)
    ]
    assert all(
        _private_mode(path) == 0o600 and path.lstat().st_nlink == 1 for path in members
    )

    previous = None
    retained = (root / "reservation.json").read_bytes()
    for path in members:
        raw = path.read_bytes()
        assert (
            json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")).encode()
            == raw
        )
        payload = json.loads(raw)
        assert payload["previous_event_sha256"] == previous
        previous = hashlib.sha256(raw).hexdigest()
        retained += raw
    assert b"prompt" not in retained
    assert b"response body" not in retained
    assert b"fixture-token" not in retained
    assert not hasattr(journal, "lm")
    assert not hasattr(journal, "session")


def test_completed_trace_projects_only_the_explicit_fixture_semantic_outcome(tmp_path):
    journal = _journal(tmp_path)
    _completed_trace(journal, retry=True)

    expected: dict[SemanticOutcome, EmpiricalDisposition] = {
        "not_evaluated": "not_evaluated",
        "semantic_error": "error",
        "score_miss": "failed",
        "score_pass": "passed",
    }
    for semantic_outcome, disposition in expected.items():
        projection = _reduce(journal, semantic_outcome=semantic_outcome)
        assert projection.request_acknowledged is True
        assert projection.external_effect_possible is True
        assert projection.terminal == "provider_response_completed"
        assert projection.empirical_disposition == disposition


@pytest.mark.parametrize(
    ("events", "terminal", "acknowledged", "effect_possible"),
    [
        (
            [
                _event("wrapper_request_accepted"),
                _event("pre_transport_failed", error_class="pre_transport_validation"),
            ],
            "pre_transport_failed",
            False,
            False,
        ),
        (
            [
                _event("wrapper_request_accepted"),
                _event("transport_gate_entered", gate_ordinal=1),
                _event("transport_effect_pending", gate_ordinal=1),
                _event("transport_entered", gate_ordinal=1),
                _event("http_response_observed", gate_ordinal=1, status_class=5),
                _event(
                    "remote_http_error_final",
                    status_class=5,
                    error_class="remote_http_status",
                ),
            ],
            "remote_http_error_final",
            True,
            True,
        ),
        (
            [
                _event("wrapper_request_accepted"),
                _event("transport_gate_entered", gate_ordinal=1),
                _event("transport_effect_pending", gate_ordinal=1),
                _event("outcome_unresolved", error_class="transport_timeout"),
            ],
            "outcome_unresolved",
            False,
            True,
        ),
    ],
)
def test_closed_failure_and_unresolved_terminals_reduce_without_inference(
    tmp_path, events, terminal, acknowledged, effect_possible
):
    journal = _journal(tmp_path)
    for event in events:
        _emit(journal, event)

    projection = _reduce(journal)
    assert projection.request_acknowledged is acknowledged
    assert projection.external_effect_possible is effect_possible
    assert projection.terminal == terminal
    assert projection.empirical_disposition == (
        "effect_indeterminate" if terminal == "outcome_unresolved" else "error"
    )


@pytest.mark.parametrize(
    ("protocol", "terminal_kind", "error_class"),
    [
        ("response.failed", "provider_response_failed", "provider_failed"),
        ("response.completed", "provider_response_failed", "provider_refusal"),
        ("response.incomplete", "provider_response_incomplete", "provider_incomplete"),
    ],
)
def test_typed_provider_failures_require_response_and_matching_protocol_terminal(
    tmp_path, protocol, terminal_kind, error_class
):
    journal = _journal(tmp_path)
    for event in [
        _event("wrapper_request_accepted"),
        _event("transport_gate_entered", gate_ordinal=1),
        _event("transport_effect_pending", gate_ordinal=1),
        _event("transport_entered", gate_ordinal=1),
        _event("http_response_observed", gate_ordinal=1, status_class=2),
        _event(
            "parsed_protocol_event_observed",
            protocol_event=protocol,
            response_id_sha256=_RESPONSE_HASH,
        ),
        _event(
            terminal_kind,
            status_class=2,
            error_class=error_class,
            response_id_sha256=_RESPONSE_HASH,
        ),
    ]:
        _emit(journal, event)

    projection = _reduce(journal)
    assert projection.request_acknowledged is True
    assert projection.empirical_disposition == "error"


@pytest.mark.parametrize(
    "events",
    [
        [
            _event("wrapper_request_accepted"),
            _event("transport_entered", gate_ordinal=1),
        ],
        [
            _event("wrapper_request_accepted"),
            _event("transport_gate_entered", gate_ordinal=1),
            _event("transport_effect_pending", gate_ordinal=1),
            _event("transport_entered", gate_ordinal=1),
            _event("http_response_observed", gate_ordinal=1, status_class=2),
        ],
        [
            _event("wrapper_request_accepted"),
            _event("transport_gate_entered", gate_ordinal=1),
            _event("transport_effect_pending", gate_ordinal=1),
            _event("transport_entered", gate_ordinal=1),
            _event("http_response_observed", gate_ordinal=1, status_class=2),
            _event(
                "provider_response_completed",
                status_class=2,
                response_id_sha256=_RESPONSE_HASH,
                observed_model="gpt-5.6-sol",
            ),
        ],
    ],
)
def test_missing_pending_terminal_or_parsed_terminal_is_indeterminate(tmp_path, events):
    journal = _journal(tmp_path)
    for event in events:
        _emit(journal, event)

    projection = reduce_journal(tmp_path / "receipt")
    assert projection.provider_outcome_receipt == "rejected"
    assert projection.request_acknowledged is None
    assert projection.external_effect_possible is True
    assert projection.empirical_disposition == "effect_indeterminate"


def test_pre_effect_incomplete_chain_is_rejected_without_a_transport_claim(tmp_path):
    journal = _journal(tmp_path)
    _emit(journal, _event("wrapper_request_accepted"))

    projection = reduce_journal(tmp_path / "receipt")
    assert projection.provider_outcome_receipt == "rejected"
    assert projection.request_acknowledged is None
    assert projection.external_effect_possible is False
    assert projection.empirical_disposition == "error"


def test_sequence_hash_source_and_mode_tampering_fail_closed(tmp_path):
    journal = _journal(tmp_path)
    _completed_trace(journal)
    root = tmp_path / "receipt"
    target = root / "events" / "000003.json"
    payload = json.loads(target.read_bytes())
    payload["previous_event_sha256"] = "d" * 64
    target.write_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    target.chmod(0o600)

    projection = reduce_journal(root)
    assert projection.provider_outcome_receipt == "rejected"
    assert projection.external_effect_possible is True
    assert projection.empirical_disposition == "effect_indeterminate"

    target.chmod(0o644)
    projection = reduce_journal(root)
    assert projection.provider_outcome_receipt == "rejected"
    assert projection.empirical_disposition == "effect_indeterminate"


def test_byte_identical_consumption_is_idempotent_without_a_raw_import_api(tmp_path):
    journal = _journal(tmp_path)
    _emit(journal, _event("wrapper_request_accepted"))
    path = tmp_path / "receipt" / "events" / "000000.json"
    before = path.stat()

    first = journal.load_verified()
    second = journal.load_verified()
    after = path.stat()
    assert first == second
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    assert not hasattr(journal, "import_envelope")


def test_sink_rejects_concurrency_post_terminal_and_schema_widening(tmp_path):
    journal = _journal(tmp_path)
    assert journal._lock.acquire(blocking=False)  # fixture forces the contested entry
    try:
        with pytest.raises(ProviderOutcomeConsumerError) as exc_info:
            _emit(journal, _event("wrapper_request_accepted"))
        assert exc_info.value.reason == "concurrent_sink_invocation"
    finally:
        journal._lock.release()

    clean = _journal(tmp_path / "second")
    _emit(clean, _event("wrapper_request_accepted"))
    _emit(clean, _event("pre_transport_failed", error_class="pre_transport_validation"))
    with pytest.raises(ProviderOutcomeConsumerError) as exc_info:
        _emit(clean, _event("transport_gate_entered", gate_ordinal=1))
    assert exc_info.value.reason == "event_after_terminal"
    with pytest.raises(ProviderOutcomeConsumerError):
        clean.load_verified()

    @dataclass(frozen=True, slots=True)
    class WidenedEvent:
        kind: str
        gate_ordinal: int | None = None
        status_class: int | None = None
        error_class: str | None = None
        protocol_event: str | None = None
        response_id_sha256: str | None = None
        observed_model: str | None = None
        raw_body: str | None = None

    widened_artifact = _artifact(event_type=WidenedEvent)
    widened = _journal(tmp_path / "widened", widened_artifact)
    with pytest.raises(ProviderOutcomeConsumerError) as exc_info:
        cast(Any, _receipt(widened)).emit(
            WidenedEvent("wrapper_request_accepted", raw_body="secret")
        )
    assert exc_info.value.reason == "owner_event_schema_drift"


def test_control_char_oversize_and_unknown_fields_never_reach_journal(tmp_path):
    for event in [
        _event(
            "provider_response_completed",
            status_class=2,
            response_id_sha256=_RESPONSE_HASH,
            observed_model="model\nsecret",
        ),
        _event(
            "provider_response_completed",
            status_class=2,
            response_id_sha256=_RESPONSE_HASH,
            observed_model="x" * 129,
        ),
        _event("unknown"),
    ]:
        journal = _journal(tmp_path / hashlib.sha256(repr(event).encode()).hexdigest())
        with pytest.raises(ProviderOutcomeConsumerError):
            _emit(journal, event)
        assert list((journal._root / "events").iterdir()) == []


def test_sink_failure_poisoning_never_falls_back_or_synthesizes_a_terminal(
    tmp_path, monkeypatch
):
    journal = _journal(tmp_path)
    _emit(journal, _event("wrapper_request_accepted"))
    _emit(journal, _event("transport_gate_entered", gate_ordinal=1))

    import dspx.services.provider_outcome_receipt_journal as journal_module

    def fail_write(path, raw, *, sync_parent=True):
        del path, raw, sync_parent
        raise ProviderOutcomeConsumerError("journal_persistence_failed")

    monkeypatch.setattr(journal_module, "_write_file", fail_write)
    with pytest.raises(ProviderOutcomeConsumerError) as exc_info:
        _emit(journal, _event("transport_effect_pending", gate_ordinal=1))
    assert exc_info.value.reason == "journal_persistence_failed"
    with pytest.raises(ProviderOutcomeConsumerError) as exc_info:
        journal.load_verified()
    assert exc_info.value.reason == "journal_poisoned"
    assert [path.name for path in journal._events.iterdir()] == [
        "000000.json",
        "000001.json",
    ]


def test_only_paired_receipt_gets_the_sink_and_fixture_artifacts_cannot_accept(
    tmp_path,
):
    journal = _journal(tmp_path)
    receipt = _receipt(journal)
    assert receipt.logical_request_id == "fixture-request-1"
    assert receipt.semantic_request_sha256 == _HASH
    assert not hasattr(journal, "sink")
    with pytest.raises(ProviderOutcomeConsumerError):
        journal.provider_receipt()
    _completed_trace(journal)
    projection = reduce_journal(tmp_path / "receipt")
    assert projection.provider_outcome_receipt == "rejected"
    assert projection.empirical_disposition == "effect_indeterminate"
    assert projection.reason == "fixture_journal_not_accepted"


def test_conflicting_protocol_terminals_are_indeterminate(tmp_path):
    journal = _journal(tmp_path)
    for event in [
        _event("wrapper_request_accepted"),
        _event("transport_gate_entered", gate_ordinal=1),
        _event("transport_effect_pending", gate_ordinal=1),
        _event("transport_entered", gate_ordinal=1),
        _event("http_response_observed", gate_ordinal=1, status_class=2),
        _event(
            "parsed_protocol_event_observed",
            protocol_event="response.failed",
            response_id_sha256=_RESPONSE_HASH,
        ),
        _event(
            "parsed_protocol_event_observed",
            protocol_event="response.completed",
            response_id_sha256=_RESPONSE_HASH,
        ),
        _event(
            "provider_response_completed",
            status_class=2,
            response_id_sha256=_RESPONSE_HASH,
        ),
    ]:
        _emit(journal, event)
    projection = reduce_journal(tmp_path / "receipt")
    assert projection.provider_outcome_receipt == "rejected"
    assert projection.empirical_disposition == "effect_indeterminate"
    assert projection.reason == "contradictory_protocol_terminal"


def test_sink_event_budget_is_bounded_and_no_raw_import_surface_exists(tmp_path):
    journal = _journal(tmp_path)
    _emit(journal, _event("wrapper_request_accepted"))
    for ordinal in range(1, 64):
        _emit(journal, _event("transport_gate_entered", gate_ordinal=ordinal))
    with pytest.raises(ProviderOutcomeConsumerError) as exc_info:
        _emit(journal, _event("transport_gate_entered", gate_ordinal=64))
    assert exc_info.value.reason == "event_budget_exceeded"
    assert len(list(journal._events.iterdir())) == 64
    assert not hasattr(journal, "import_envelope")


def test_directory_sync_failure_poisons_visible_terminal_before_reduction(
    tmp_path, monkeypatch
):
    journal = _journal(tmp_path)
    for event in [
        _event("wrapper_request_accepted"),
        _event("transport_gate_entered", gate_ordinal=1),
        _event("transport_effect_pending", gate_ordinal=1),
        _event("transport_entered", gate_ordinal=1),
        _event("http_response_observed", gate_ordinal=1, status_class=2),
        _event(
            "parsed_protocol_event_observed",
            protocol_event="response.completed",
            response_id_sha256=_RESPONSE_HASH,
        ),
    ]:
        _emit(journal, event)

    import dspx.services.provider_outcome_receipt_journal as journal_module

    original = journal_module._fsync_directory

    def fail_event_directory(path):
        if path == journal._events:
            raise ProviderOutcomeConsumerError("directory_sync_failed")
        original(path)

    monkeypatch.setattr(journal_module, "_fsync_directory", fail_event_directory)
    with pytest.raises(ProviderOutcomeConsumerError):
        _emit(
            journal,
            _event(
                "provider_response_completed",
                status_class=2,
                response_id_sha256=_RESPONSE_HASH,
            ),
        )
    assert (journal._events / "000006.json").is_file()
    assert (journal._root / "inflight.json").is_file()
    projection = reduce_journal(journal._root)
    assert projection.provider_outcome_receipt == "rejected"
    assert projection.empirical_disposition == "effect_indeterminate"
    assert projection.reason == "journal_inflight"


def test_late_malformed_event_and_secret_identity_fail_closed(tmp_path):
    journal = _journal(tmp_path)
    for event in [
        _event("wrapper_request_accepted"),
        _event("transport_gate_entered", gate_ordinal=1),
        _event("transport_effect_pending", gate_ordinal=1),
    ]:
        _emit(journal, event)
    with pytest.raises(ProviderOutcomeConsumerError):
        _emit(journal, _event("unknown"))
    projection = reduce_journal(journal._root)
    assert projection.empirical_disposition == "effect_indeterminate"
    assert projection.reason == "journal_poisoned"

    artifact = _artifact()
    widened = replace(
        _reservation(artifact),
        source_identity={**artifact.source_identity, "token": "secret"},
    )
    with pytest.raises(ProviderOutcomeConsumerError) as exc_info:
        widened.payload()
    assert exc_info.value.reason == "invalid_source_identity"


def test_verified_artifact_constructor_rejects_caller_forgery():
    fixture = _artifact()
    with pytest.raises(TypeError):
        VerifiedOwnerArtifact(
            source_identity=fixture.source_identity,
            dependency_identity=fixture.dependency_identity,
            event_type=FixtureOutcomeReceiptEvent,
            receipt_type=FixtureProviderOutcomeReceipt,
            revalidator=lambda: None,
            accepted=True,
            token=object(),
        )
    with pytest.raises(TypeError):
        fixture._accepted = True


def _run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=True, text=True
    )
    return completed.stdout.strip()


def test_source_verifier_checks_exact_commit_tree_bytes_lock_and_dirty_state(tmp_path):
    root = tmp_path / "owner"
    source = root / "src" / "dspy_lm_auth" / "outcome_receipt.py"
    source.parent.mkdir(parents=True)
    source.write_text("EVENT = 'closed'\n", encoding="utf-8")
    wheel_hash = "e" * 64
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture-owner"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text(
        textwrap.dedent(
            f"""
            version = 1
            revision = 1
            requires-python = ">=3.13"

            [[package]]
            name = "demo"
            version = "4.5.6"
            wheels = [{{ url = "https://fixtures.invalid/demo.whl", hash = "sha256:{wheel_hash}", size = 1 }}]
            """
        ).lstrip(),
        encoding="utf-8",
    )
    _run_git(root, "init", "-q")
    _run_git(root, "config", "user.email", "fixture@example.invalid")
    _run_git(root, "config", "user.name", "Fixture")
    _run_git(root, "add", ".")
    _run_git(root, "commit", "-qm", "fixture")
    commit = _run_git(root, "rev-parse", "HEAD")
    tree = _run_git(root, "rev-parse", "HEAD^{tree}")
    file_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    lock_hash = hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
    expected = ExpectedOwnerSource(
        commit=commit,
        tree=tree,
        version="1.2.3",
        lock_sha256=lock_hash,
        modules={"outcome_receipt": ("src/dspy_lm_auth/outcome_receipt.py", file_hash)},
        dependencies={
            "demo": ExpectedDependency("demo", "4.5.6", wheel_hash, 1, _HASH, _HASH)
        },
    )

    identity = verify_owner_source(root, expected)
    assert identity["commit"] == commit
    assert identity["tree"] == tree
    assert identity["module_sha256"] == {"outcome_receipt": file_hash}
    source.write_text("EVENT = 'drift'\n", encoding="utf-8")
    with pytest.raises(ProviderOutcomeConsumerError):
        verify_owner_source(root, expected)


def test_exact_accepted_owner_event_api_source_and_dependency_fixture(tmp_path):
    raw_root = os.environ.get("DSPX_PROVIDER_OUTCOME_OWNER_SOURCE")
    if not raw_root:
        pytest.skip("exact accepted owner source is an explicit local fixture")
    root = Path(raw_root).expanduser().resolve(strict=True)
    python = root / ".venv" / "bin" / "python"
    if not python.is_file():
        pytest.skip("exact accepted owner fixture environment is unavailable")
    script = textwrap.dedent(
        """
        import json
        import sys
        from pathlib import Path
        from unittest.mock import patch

        from dspy_lm_auth.outcome_receipt import (
            OutcomeReceiptEvent,
            ProviderOutcomeReceipt,
        )
        from dspx.services.soomfon_provider_outcome_receipt_contract import ReceiptReservation
        from dspx.services.soomfon_provider_outcome_receipt_identity import verify_owner_artifact
        from dspx.services.soomfon_provider_outcome_receipt_journal import ReceiptJournal
        from dspx.services.soomfon_provider_outcome_receipt_reducer import reduce_journal

        root = Path(sys.argv[1]).resolve(strict=True)
        out = Path(sys.argv[2])
        artifact = verify_owner_artifact(
            root, OutcomeReceiptEvent, ProviderOutcomeReceipt
        )
        reservation = ReceiptReservation(
            consumer_task_id=4678,
            ledger_sha256="a" * 64,
            process_id="exact-owner-fixture",
            case_id="fixture-case",
            logical_request_id="fixture-request",
            transport_gate_id="fixture-gate",
            semantic_request_sha256="b" * 64,
            contract_sha256="c" * 64,
            mode="sync",
            requested_route="codex:gpt-5.6-sol",
            resolved_route="openai:gpt-5.6-sol",
            endpoint_origin_sha256="d" * 64,
            source_identity=artifact.source_identity,
            dependency_identity=artifact.dependency_identity,
        )
        journal = ReceiptJournal.create(out, reservation, artifact)
        receipt = journal.provider_receipt()
        receipt_bound = (
            receipt.logical_request_id == reservation.logical_request_id
            and receipt.semantic_request_sha256
            == reservation.semantic_request_sha256
            and not hasattr(journal, "sink")
        )
        try:
            journal.provider_receipt()
        except Exception:
            second_issue_rejected = True
        else:
            second_issue_rejected = False
        events = [
            OutcomeReceiptEvent(kind="wrapper_request_accepted"),
            OutcomeReceiptEvent(kind="transport_gate_entered", gate_ordinal=1),
            OutcomeReceiptEvent(kind="transport_effect_pending", gate_ordinal=1),
            OutcomeReceiptEvent(kind="transport_entered", gate_ordinal=1),
            OutcomeReceiptEvent(
                kind="http_response_observed",
                gate_ordinal=1,
                status_class=2,
                status_code=200,
            ),
            OutcomeReceiptEvent(
                kind="parsed_protocol_event_observed",
                protocol_event="response.completed",
                response_id_sha256="e" * 64,
            ),
            OutcomeReceiptEvent(
                kind="provider_response_completed",
                status_class=2,
                status_code=200,
                response_id_sha256="e" * 64,
                observed_model="gpt-5.6-sol",
            ),
        ]
        with patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
            for event in events:
                receipt.sink(event)
        projection = reduce_journal(
            out,
            owner_source_root=root,
            event_type=OutcomeReceiptEvent,
            receipt_type=ProviderOutcomeReceipt,
        ).payload()
        link = out.parent / "owner-link"
        link.symlink_to(root, target_is_directory=True)
        try:
            verify_owner_artifact(
                link, OutcomeReceiptEvent, ProviderOutcomeReceipt
            )
        except Exception:
            symlink_rejected = True
        else:
            symlink_rejected = False
        print(json.dumps({
            "projection": projection,
            "receipt_bound": receipt_bound,
            "second_issue_rejected": second_issue_rejected,
            "symlink_rejected": symlink_rejected,
        }, sort_keys=True))
        """
    )
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            [str(root / "src"), str(Path.cwd() / "packages/dspx-core/src")]
        ),
    }
    completed = subprocess.run(
        [str(python), "-c", script, str(root), str(tmp_path / "exact")],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    projection = result["projection"]
    assert projection["provider_outcome_receipt"] == "accepted"
    assert projection["request_acknowledged"] is True
    assert projection["status_class"] == 2
    assert projection["status_code"] == 200
    assert projection["empirical_disposition"] == "not_evaluated"
    assert result["receipt_bound"] is True
    assert result["second_issue_rejected"] is True
    assert result["symlink_rejected"] is True
    retained = b"".join(
        path.read_bytes() for path in sorted((tmp_path / "exact").rglob("*.json"))
    )
    assert str(root).encode() not in retained
    assert b"https://" not in retained
