# summary: "Provider-free tests for Soomfon-only receipt and call custody."
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest

from dspx.services.provider_outcome_receipt_contract import EVENT_FIELDS
from dspx.services.provider_outcome_receipt_identity import (
    VerifiedOwnerArtifact,
    _ARTIFACT_TOKEN,
    _fixture_owner_artifact,
)
from dspx.services.soomfon_evaluation_provider import (
    SOOMFON_OWNER_SOURCE,
    SoomfonCallCustodian,
    SoomfonProviderError,
    validate_soomfon_provider_evidence,
    verify_retained_soomfon_journals,
)


@dataclass(frozen=True, slots=True)
class _Event:
    kind: str
    gate_ordinal: int | None = None
    status_class: int | None = None
    error_class: str | None = None
    protocol_event: str | None = None
    response_id_sha256: str | None = None
    observed_model: str | None = None


assert tuple(_Event.__dataclass_fields__) == EVENT_FIELDS


@dataclass(slots=True)
class _Receipt:
    logical_request_id: str
    semantic_request_sha256: str
    sink: Any
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _used: bool = False


def _artifact() -> VerifiedOwnerArtifact:
    expected = SOOMFON_OWNER_SOURCE
    return _fixture_owner_artifact(
        source_identity={
            "owner": "tryinget-dspy-lm-auth",
            "version": expected.version,
            "commit": expected.commit,
            "tree": expected.tree,
            "lock_sha256": expected.lock_sha256,
            "module_sha256": {
                name: digest for name, (_, digest) in expected.modules.items()
            },
        },
        dependency_identity={
            name: {
                "version": item.version,
                "locked_wheel_sha256": item.wheel_sha256,
                "payload_count": item.payload_count,
                "payload_sha256": item.payload_sha256,
                "record_sha256": item.record_sha256,
            }
            for name, item in expected.dependencies.items()
        },
        event_type=_Event,
        receipt_type=_Receipt,
    )


def _accepted_artifact() -> VerifiedOwnerArtifact:
    fixture = _artifact()
    return VerifiedOwnerArtifact(
        source_identity=fixture.source_identity,
        dependency_identity=fixture.dependency_identity,
        event_type=_Event,
        receipt_type=_Receipt,
        revalidator=lambda: None,
        accepted=True,
        token=_ARTIFACT_TOKEN,
    )


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _completed(receipt: _Receipt, *, model: str = "gpt-5.6-luna") -> None:
    response_id = hashlib.sha256(b"opaque response id").hexdigest()
    for event in (
        _Event("wrapper_request_accepted"),
        _Event("transport_gate_entered", gate_ordinal=1),
        _Event("transport_effect_pending", gate_ordinal=1),
        _Event("transport_entered", gate_ordinal=1),
        _Event("http_response_observed", gate_ordinal=1, status_class=2),
        _Event(
            "parsed_protocol_event_observed",
            protocol_event="response.completed",
            response_id_sha256=response_id,
        ),
        _Event(
            "provider_response_completed",
            status_class=2,
            response_id_sha256=response_id,
            observed_model=model,
        ),
    ):
        receipt.sink(event)


def _custodian(tmp_path: Path) -> SoomfonCallCustodian:
    return SoomfonCallCustodian(
        journal_parent=_private(tmp_path / "journals"),
        artifact=_artifact(),
        execution_task_id=6000,
        contract_sha256="a" * 64,
        mode="simple",
        ledger_sha256="b" * 64,
        authority_revalidator=lambda: None,
    )


def test_exactly_two_ordered_calls_create_two_verified_journals(
    tmp_path: Path,
) -> None:
    custodian = _custodian(tmp_path)
    calls: list[str] = []

    def invoke(receipt: object) -> str:
        calls.append("transport")
        _completed(cast(_Receipt, receipt))
        return '{"response":"private raw response"}'

    first = custodian.invoke(
        signature_name="DefinePersona",
        semantic_request_sha256="1" * 64,
        invoke=invoke,
    )
    second = custodian.invoke(
        signature_name="AnswerSimple",
        semantic_request_sha256="2" * 64,
        invoke=invoke,
    )
    evidence = custodian.finalize()

    assert first == second == '{"response":"private raw response"}'
    assert calls == ["transport", "transport"]
    assert evidence["logical_call_total"] == 2
    assert [row["call_ordinal"] for row in evidence["call_records"]] == [1, 2]
    assert all(
        row["provider_outcome_receipt"] == "accepted"
        for row in evidence["call_records"]
    )
    assert len(list((tmp_path / "journals").iterdir())) == 2
    assert "private raw response" not in json.dumps(evidence)


@pytest.mark.parametrize("signature", ["AnswerSimple", "Unknown", "DefinePersona"])
def test_out_of_order_duplicate_and_third_calls_reject_before_invocation(
    tmp_path: Path, signature: str
) -> None:
    custodian = _custodian(tmp_path)
    invoked = 0

    def invoke(receipt: object) -> str:
        nonlocal invoked
        invoked += 1
        _completed(cast(_Receipt, receipt))
        return "ok"

    if signature == "DefinePersona":
        custodian.invoke(
            signature_name="DefinePersona",
            semantic_request_sha256="1" * 64,
            invoke=invoke,
        )
        custodian.invoke(
            signature_name="AnswerSimple",
            semantic_request_sha256="2" * 64,
            invoke=invoke,
        )
        baseline = invoked
    else:
        baseline = 0
    with pytest.raises(SoomfonProviderError):
        custodian.invoke(
            signature_name=signature,
            semantic_request_sha256="3" * 64,
            invoke=invoke,
        )
    assert invoked == baseline


def test_open_receipt_chain_is_terminal_and_blocks_progression(tmp_path: Path) -> None:
    custodian = _custodian(tmp_path)

    def invoke(receipt: object) -> str:
        cast(_Receipt, receipt).sink(_Event("wrapper_request_accepted"))
        return "unretained response"

    with pytest.raises(SoomfonProviderError, match="receipt"):
        custodian.invoke(
            signature_name="DefinePersona",
            semantic_request_sha256="1" * 64,
            invoke=invoke,
        )
    with pytest.raises(SoomfonProviderError):
        custodian.invoke(
            signature_name="AnswerSimple",
            semantic_request_sha256="2" * 64,
            invoke=lambda _: "must not run",
        )
    evidence = custodian.evidence()
    assert evidence["call_records"][0]["empirical_disposition"] in {
        "error",
        "effect_indeterminate",
    }
    assert "unretained response" not in json.dumps(evidence)


def test_poisoned_journal_is_terminal(tmp_path: Path) -> None:
    custodian = _custodian(tmp_path)

    def invoke(receipt: object) -> str:
        typed = cast(_Receipt, receipt)
        typed.sink(_Event("wrapper_request_accepted"))
        journal = next((tmp_path / "journals").iterdir())
        poison = journal / "poisoned.json"
        poison.write_text(
            json.dumps(
                {
                    "schema_version": "dspx-provider-outcome-poison-v1",
                    "effect_possible": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        poison.chmod(0o600)
        return "private"

    with pytest.raises(SoomfonProviderError, match="receipt"):
        custodian.invoke(
            signature_name="DefinePersona",
            semantic_request_sha256="1" * 64,
            invoke=invoke,
        )


def test_provider_evidence_validator_rejects_raw_or_widened_fields(
    tmp_path: Path,
) -> None:
    custodian = _custodian(tmp_path)
    for ordinal, signature in enumerate(("DefinePersona", "AnswerSimple"), start=1):
        custodian.invoke(
            signature_name=signature,
            semantic_request_sha256=str(ordinal) * 64,
            invoke=lambda receipt: (_completed(cast(_Receipt, receipt)), "ok")[1],
        )
    evidence = custodian.finalize()
    validate_soomfon_provider_evidence(evidence, mode="simple")

    forged = json.loads(json.dumps(evidence))
    forged["call_records"][0]["raw_response"] = "secret"
    with pytest.raises(SoomfonProviderError):
        validate_soomfon_provider_evidence(forged, mode="simple")


def test_journal_parent_must_be_private(tmp_path: Path) -> None:
    parent = tmp_path / "journals"
    parent.mkdir(mode=0o755)
    with pytest.raises(SoomfonProviderError):
        SoomfonCallCustodian(
            journal_parent=parent,
            artifact=_artifact(),
            execution_task_id=6000,
            contract_sha256="a" * 64,
            mode="simple",
            ledger_sha256="b" * 64,
            authority_revalidator=lambda: None,
        )


def test_retained_journals_rebind_current_marker_and_reject_stale_marker(
    tmp_path: Path,
) -> None:
    parent = _private(tmp_path / "journals")
    custodian = SoomfonCallCustodian(
        journal_parent=parent,
        artifact=_accepted_artifact(),
        execution_task_id=6000,
        contract_sha256="a" * 64,
        mode="simple",
        ledger_sha256="b" * 64,
        authority_revalidator=lambda: None,
    )
    for ordinal, signature in enumerate(("DefinePersona", "AnswerSimple"), start=1):
        custodian.invoke(
            signature_name=signature,
            semantic_request_sha256=str(ordinal) * 64,
            invoke=lambda receipt: (_completed(cast(_Receipt, receipt)), "private")[1],
        )
    evidence = custodian.finalize()
    verify_retained_soomfon_journals(
        parent,
        evidence,
        mode="simple",
        execution_task_id=6000,
        contract_sha256="a" * 64,
        expected_marker_sha256="b" * 64,
    )
    reduced_summary = {
        key: evidence[key]
        for key in (
            "artifact_verification",
            "logical_call_total",
            "maximum_provider_transports",
            "call_records",
        )
    }
    with pytest.raises(SoomfonProviderError):
        verify_retained_soomfon_journals(
            parent,
            reduced_summary,
            mode="simple",
            execution_task_id=6000,
            contract_sha256="a" * 64,
            expected_marker_sha256="b" * 64,
        )

    forged = json.loads(json.dumps(evidence))
    forged["call_records"][1]["journal_sha256"] = "f" * 64
    with pytest.raises(SoomfonProviderError):
        verify_retained_soomfon_journals(
            parent,
            forged,
            mode="simple",
            execution_task_id=6000,
            contract_sha256="a" * 64,
            expected_marker_sha256="b" * 64,
        )

    with pytest.raises(SoomfonProviderError):
        verify_retained_soomfon_journals(
            parent,
            evidence,
            mode="simple",
            execution_task_id=6000,
            contract_sha256="a" * 64,
            expected_marker_sha256="c" * 64,
        )


def test_soomfon_json_adapter_performs_one_lm_invocation_without_fallback(
    tmp_path: Path,
) -> None:
    import dspy
    from types import SimpleNamespace
    from dspx.services.soomfon_evaluation_auth_provider import SoomfonJSONAdapter

    class DefinePersona(dspy.Signature):
        persona_intent: str = dspy.InputField()
        persona: str = dspy.OutputField()

    class FakeLM(dspy.BaseLM):
        def __init__(self) -> None:
            super().__init__(
                model="openai/gpt-5.6-luna",
                model_type="chat",
                cache=False,
                num_retries=0,
                reasoning_effort="xhigh",
                timeout=60.0,
                api_base="https://chatgpt.com/backend-api/codex",
            )
            self.calls = 0

        def forward(self, prompt=None, messages=None, **kwargs):
            del prompt, messages
            self.calls += 1
            _completed(cast(_Receipt, kwargs["outcome_receipt"]))
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"persona":"calm teacher"}')
                    )
                ],
                usage={},
                _hidden_params={},
                model="gpt-5.6-luna",
            )

    class Owner:
        lm_module = SimpleNamespace(
            _build_codex_responses_request=lambda request: request
        )
        receipt_module = SimpleNamespace(
            semantic_request_sha256=lambda request: hashlib.sha256(
                json.dumps(request, sort_keys=True, default=str).encode()
            ).hexdigest()
        )

        def revalidate(self) -> None:
            return None

    lm = FakeLM()
    custodian = _custodian(tmp_path)
    adapter = SoomfonJSONAdapter(
        owner=cast(Any, Owner()), lm=lm, custodian=custodian, mode="simple"
    )
    result = adapter(
        lm,
        {},
        DefinePersona,
        [],
        {"persona_intent": "be calm"},
    )
    assert result == [{"persona": "calm teacher"}]
    assert lm.calls == 1
    assert custodian.evidence()["logical_call_total"] == 1
    with pytest.raises(SoomfonProviderError):
        adapter(
            lm,
            {},
            DefinePersona,
            [],
            {"persona_intent": "duplicate"},
        )
    assert lm.calls == 1


def test_soomfon_json_adapter_rejects_async_before_lm_call(tmp_path: Path) -> None:
    import asyncio
    from types import SimpleNamespace
    from dspx.services.soomfon_evaluation_auth_provider import SoomfonJSONAdapter

    adapter = SoomfonJSONAdapter(
        owner=cast(Any, SimpleNamespace()),
        lm=SimpleNamespace(),
        custodian=_custodian(tmp_path),
        mode="simple",
    )
    with pytest.raises(SoomfonProviderError):
        asyncio.run(adapter.acall())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("original_model_string", "codex/other"),
        ("resolved_model_string", "openai/other"),
        ("auth_provider", "other"),
        ("credential_mode", None),
        ("num_retries", 1),
        ("cache", True),
        ("reasoning_effort", "high"),
        ("timeout", 61.0),
    ],
)
def test_exact_owner_lm_configuration_rejects_drift(field: str, value: object) -> None:
    from types import SimpleNamespace
    from dspx.services.soomfon_evaluation_auth_provider import _assert_exact_lm

    lm = SimpleNamespace(
        original_model_string="codex/gpt-5.6-luna",
        resolved_model_string="openai/gpt-5.6-luna",
        model="openai/gpt-5.6-luna",
        model_type="responses",
        auth_provider="codex",
        credential_mode="no-refresh",
        auth_storage=None,
        _uses_codex_route=True,
        num_retries=0,
        cache=False,
        callbacks=[],
        kwargs={
            "reasoning_effort": "xhigh",
            "timeout": 60.0,
            "api_base": "https://chatgpt.com/backend-api/codex",
            "temperature": None,
            "max_tokens": None,
        },
    )
    if field in {"reasoning_effort", "timeout"}:
        lm.kwargs[field] = value
    else:
        setattr(lm, field, value)
    owner = SimpleNamespace(lm_type=SimpleNamespace, revalidate=lambda: None)
    with pytest.raises(SoomfonProviderError):
        _assert_exact_lm(cast(Any, owner), lm)


def test_indeterminate_owner_receipt_chain_stops_before_second_call(
    tmp_path: Path,
) -> None:
    custodian = _custodian(tmp_path)

    def unresolved(receipt: object) -> str:
        typed = cast(_Receipt, receipt)
        for event in (
            _Event("wrapper_request_accepted"),
            _Event("transport_gate_entered", gate_ordinal=1),
            _Event("transport_effect_pending", gate_ordinal=1),
            _Event("transport_entered", gate_ordinal=1),
            _Event("outcome_unresolved", error_class="transport_timeout"),
        ):
            typed.sink(event)
        return "private"

    with pytest.raises(SoomfonProviderError, match="receipt"):
        custodian.invoke(
            signature_name="DefinePersona",
            semantic_request_sha256="1" * 64,
            invoke=unresolved,
        )
    with pytest.raises(SoomfonProviderError):
        custodian.invoke(
            signature_name="AnswerSimple",
            semantic_request_sha256="2" * 64,
            invoke=lambda _: "must not run",
        )
    assert (
        custodian.evidence()["call_records"][0]["empirical_disposition"]
        == "effect_indeterminate"
    )


def test_chain_of_thought_signature_maps_to_declared_second_logical_call() -> None:
    import dspy
    from dspx.services.soomfon_evaluation_provider import logical_signature_name

    class AnswerElaborate(dspy.Signature):
        transcription: str = dspy.InputField()
        persona: str = dspy.InputField()
        response: str = dspy.OutputField()

    chain_signature = dspy.ChainOfThought(AnswerElaborate).predict.signature
    assert chain_signature is not None
    typed_signature = cast(type[Any], chain_signature)
    assert typed_signature.__name__ == "StringSignature"
    assert (
        logical_signature_name(typed_signature, mode="elaborate") == "AnswerElaborate"
    )


def test_exact_owner_lm_accepts_only_real_dspy_default_kwargs() -> None:
    from types import SimpleNamespace
    from dspx.services.soomfon_evaluation_auth_provider import _assert_exact_lm

    lm = SimpleNamespace(
        original_model_string="codex/gpt-5.6-luna",
        resolved_model_string="openai/gpt-5.6-luna",
        model="openai/gpt-5.6-luna",
        model_type="responses",
        auth_provider="codex",
        credential_mode="no-refresh",
        auth_storage=None,
        _uses_codex_route=True,
        num_retries=0,
        cache=False,
        callbacks=[],
        kwargs={
            "reasoning_effort": "xhigh",
            "timeout": 60.0,
            "api_base": "https://chatgpt.com/backend-api/codex",
            "temperature": None,
            "max_tokens": None,
        },
    )
    owner = SimpleNamespace(lm_type=SimpleNamespace, revalidate=lambda: None)
    _assert_exact_lm(cast(Any, owner), lm)
    for key, value in (("temperature", 0), ("max_tokens", 1), ("extra", None)):
        drift = SimpleNamespace(**vars(lm))
        drift.kwargs = dict(lm.kwargs)
        drift.kwargs[key] = value
        with pytest.raises(SoomfonProviderError):
            _assert_exact_lm(cast(Any, owner), drift)


def test_exact_ak4991_owner_venv_passes_loaded_boundary_without_auth_access(
    tmp_path: Path,
) -> None:
    import subprocess

    owner_root = Path(
        "/home/tryinget/.local/state/pi-quests/tmp/dspy-lm-auth-ak4991-soomfon-auth"
    )
    python = owner_root / ".venv/bin/python"
    if not python.is_file():
        pytest.skip("exact AK-4991 proof venv is unavailable")
    fake_home = _private(tmp_path / "empty-home")
    clean_owner_root = tmp_path / "clean-owner-source"
    clone = subprocess.run(
        [
            "/usr/bin/git",
            "clone",
            "--quiet",
            "--no-hardlinks",
            str(owner_root),
            str(clean_owner_root),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    assert clone.returncode == 0, clone.stderr.decode(errors="replace")
    assert not list(clean_owner_root.rglob("*.pyc"))
    assert not list(clean_owner_root.rglob("__pycache__"))
    source_root = Path(__file__).resolve().parents[1] / "packages/dspx-core/src"
    script = """
from pathlib import Path
from dspx.services.soomfon_evaluation_auth_provider import _assert_exact_lm
from dspx.services.soomfon_evaluation_owner import verify_loaded_soomfon_owner
owner = verify_loaded_soomfon_owner(Path(__import__('os').environ['OWNER_ROOT']))
def denied(*args, **kwargs):
    raise AssertionError('credential or network access forbidden in boundary proof')
owner.lm_module.read_existing_oauth_credential_without_refresh = denied
__import__('socket').socket = denied
lm = owner.lm_type(
    'codex/gpt-5.6-luna', auth_provider='codex', credential_mode='no-refresh',
    reasoning_effort='xhigh', num_retries=0, cache=False, timeout=60.0,
)
_assert_exact_lm(owner, lm)
assert lm.kwargs == {
    'temperature': None, 'max_tokens': None, 'reasoning_effort': 'xhigh',
    'timeout': 60.0, 'api_base': 'https://chatgpt.com/backend-api/codex',
}
print('exact-owner-boundary-ok')
"""
    environment = {
        "HOME": str(fake_home),
        "XDG_CONFIG_HOME": str(fake_home),
        "PATH": f"{python.parent}:/usr/bin",
        "PYTHONPATH": str(source_root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "OWNER_ROOT": str(clean_owner_root),
    }
    result = subprocess.run(
        [str(python), "-B", "-P", "-c", script],
        cwd=fake_home,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "exact-owner-boundary-ok"
    assert not (fake_home / ".pi").exists()
    assert not list(fake_home.rglob("auth.json"))
    assert not list(clean_owner_root.rglob("*.pyc"))
    assert not list(clean_owner_root.rglob("__pycache__"))


@pytest.mark.parametrize("change", ["expired", "revoked", "changed_evidence"])
def test_canonical_authority_change_between_calls_blocks_second_transport(
    tmp_path: Path, change: str
) -> None:
    checks = 0
    transports = 0

    def authority() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise RuntimeError(change)

    custodian = SoomfonCallCustodian(
        journal_parent=_private(tmp_path / "journals"),
        artifact=_artifact(),
        execution_task_id=6000,
        contract_sha256="a" * 64,
        mode="simple",
        ledger_sha256="b" * 64,
        authority_revalidator=authority,
    )

    def invoke(receipt: object) -> str:
        nonlocal transports
        transports += 1
        _completed(cast(_Receipt, receipt))
        return "private"

    custodian.invoke(
        signature_name="DefinePersona",
        semantic_request_sha256="1" * 64,
        invoke=invoke,
    )
    with pytest.raises(SoomfonProviderError, match="custody rejected"):
        custodian.invoke(
            signature_name="AnswerSimple",
            semantic_request_sha256="2" * 64,
            invoke=invoke,
        )
    assert checks == 2
    assert transports == 1
    assert len(list((tmp_path / "journals").iterdir())) == 1


def test_call_authority_revalidator_requires_ninety_seconds_and_unchanged_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from dspx.services import soomfon_evaluation_authorization as authorization
    from dspx.services.soomfon_evaluation_auth_provider import (
        _call_authority_revalidator,
    )

    observed: dict[str, object] = {}

    def validate(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="changed" * 9 + "c",
            contract_sha256="a" * 64,
            repo="/repo",
        )

    monkeypatch.setattr(authorization, "validate_execution_authorization", validate)
    custody = SimpleNamespace(
        authorization_path=Path("projection.json"),
        authorization_sha256="f" * 64,
        repo_root=Path("/repo"),
        contract_sha256="a" * 64,
        execution_task_id=6000,
        ak_reconciliation_sha256="e" * 64,
    )
    with pytest.raises(SoomfonProviderError):
        _call_authority_revalidator(custody)
    assert observed["minimum_lease_seconds"] == 90.0
