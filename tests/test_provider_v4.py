from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.dspy_lm_auth_lm import DspyLMAuthLM
from dspx.provider_registry import available, ensure_default_providers
from dspx.run_receipts import build_run_receipt
from dspx.services.optimize_service import run_gepa_optimize

runner = CliRunner()


class _FakeAuthStorage:
    def __init__(self, path=None):
        self.path = path

    def has_auth(self, provider: str) -> bool:
        return provider in {"codex", "openai-codex"}


class _FakeLM:
    last_kwargs = None

    def __init__(
        self, model: str, *args, auth_provider=None, auth_storage=None, **kwargs
    ):
        self.model = f"openai/{model.split('/', 1)[-1]}"
        self.model_type = "responses"
        self.resolved_model_string = self.model
        self.kwargs = {
            "headers": {"Authorization": "Bearer secret-token", "X-Test": "ok"}
        }
        self._uses_codex_route = True
        self.auth_provider = auth_provider
        self.auth_storage = auth_storage

    def forward(self, prompt=None, messages=None, **kwargs):
        _FakeLM.last_kwargs = dict(kwargs)
        text = (
            prompt or ((messages or [{}])[0].get("content") if messages else "") or ""
        )
        return {
            "choices": [{"text": f"auth:{text}"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


def test_registry_includes_v4_providers() -> None:
    ensure_default_providers()
    reg = available()
    assert "dspy-lm-auth" in reg
    assert "openai-compatible" in reg
    assert "vllm-local" in reg


def test_dspy_lm_auth_wrapper_health_and_generate(monkeypatch, tmp_path: Path) -> None:
    fake = types.SimpleNamespace(LM=_FakeLM, AuthStorage=_FakeAuthStorage)
    monkeypatch.setitem(sys.modules, "dspy_lm_auth", fake)

    storage = tmp_path / "auth.json"
    storage.write_text("{}\n", encoding="utf-8")
    lm = DspyLMAuthLM(
        model="codex/gpt-5.4-mini",
        auth_provider="codex",
        auth_storage=str(storage),
    )

    health = lm.healthcheck()
    assert health["ok"] is True
    assert health["metadata"]["auth_storage_exists"] is True

    res = lm.generate(types.SimpleNamespace(prompt="hello", messages=None))
    assert res.outputs == ["auth:hello"]
    assert res.usage == {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    runtime = lm.runtime_metadata()
    assert runtime["resolved_headers"]["Authorization"] == "[REDACTED]"


def test_dspy_lm_auth_wrapper_strips_max_tokens_for_codex_route(
    monkeypatch, tmp_path: Path
) -> None:
    fake = types.SimpleNamespace(LM=_FakeLM, AuthStorage=_FakeAuthStorage)
    monkeypatch.setitem(sys.modules, "dspy_lm_auth", fake)
    _FakeLM.last_kwargs = None

    storage = tmp_path / "auth.json"
    storage.write_text("{}\n", encoding="utf-8")
    lm = DspyLMAuthLM(
        model="codex/gpt-5.4",
        auth_provider="codex",
        auth_storage=str(storage),
    )
    lm.forward(prompt="hello", max_tokens=8, temperature=0)
    assert _FakeLM.last_kwargs is not None
    assert "max_tokens" not in _FakeLM.last_kwargs
    assert _FakeLM.last_kwargs["temperature"] == 0


class _UsageObj:
    def model_dump(self):
        return {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}


class _ContentBlock:
    def __init__(self, text: str):
        self.text = text


class _Message:
    def __init__(self, text: str):
        self.content = [_ContentBlock(text)]


class _ResponseObj:
    def __init__(self, text: str):
        self.output = [_Message(text)]
        self.usage = _UsageObj()


def test_dspy_lm_auth_extracts_output_text_and_usage_from_response_object() -> None:
    resp = _ResponseObj("hello")
    assert DspyLMAuthLM._extract_text(resp) == "hello"
    assert DspyLMAuthLM._extract_usage(resp) == {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
    }


def test_cli_providers_resolve_and_benchmark(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    resolved = runner.invoke(
        app, ["providers", "resolve", "--provider", "stub", "--json"]
    )
    assert resolved.exit_code == 0
    payload = json.loads(resolved.stdout)
    assert payload["provider"] == "stub"
    assert payload["model"] == "stub/echo"

    summary = tmp_path / "providers-benchmark.json"
    bench = runner.invoke(
        app,
        [
            "providers",
            "benchmark",
            "--provider",
            "stub",
            "--repeats",
            "2",
            "--summary-json-out",
            str(summary),
            "--json",
        ],
    )
    assert bench.exit_code == 0
    bench_payload = json.loads(bench.stdout)
    assert bench_payload["ranking"] == ["stub"]
    assert summary.exists()


def test_run_receipt_includes_redacted_provider_details(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "dspy-lm-auth")
    monkeypatch.setenv("DSPX_LM_AUTH_MODEL", "codex/gpt-5.4-mini")
    monkeypatch.setenv("DSPX_LM_AUTH_PROVIDER", "codex")
    auth_path = tmp_path / "auth.json"
    auth_path.write_text('{"openai-codex": {"access": "secret"}}\n', encoding="utf-8")
    monkeypatch.setenv("DSPX_LM_AUTH_STORAGE", str(auth_path))

    out = tmp_path / "x.py"
    out.write_text("print('x')\n", encoding="utf-8")
    receipt = build_run_receipt(
        run_kind="codegen",
        output_path=out,
        output_hash="abc123def456",
        template_version="t1",
        cache_key="k",
        cache_file="c",
        cache_enabled=True,
        replay_inputs={"spec": "demo"},
    )
    details = receipt["provider_details"]
    assert details["provider"] == "dspy-lm-auth"
    assert details["requested_model"] == "codex/gpt-5.4-mini"
    assert details["auth_storage_exists"] is True
    assert "secret" not in json.dumps(details)


def test_cli_optimize_gepa_uses_configured_provider_defaults(
    monkeypatch, tmp_path: Path
) -> None:
    import dspx.services.optimize_service as optimize_service

    program = tmp_path / "prog.py"
    program.write_text("def build_student():\n    return object()\n", encoding="utf-8")
    train = tmp_path / "train.csv"
    train.write_text("question,answer\nq,a\n", encoding="utf-8")
    out = tmp_path / "out"

    captured: dict[str, object] = {}

    def _fake_run_gepa_optimize(**kwargs):
        captured.update(kwargs)
        out.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(out_dir=out)

    monkeypatch.setattr(optimize_service, "run_gepa_optimize", _fake_run_gepa_optimize)
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_OPTIMIZE_STUDENT_PROVIDER", "vllm-local")
    monkeypatch.setenv("DSPX_OPTIMIZE_REFLECTION_PROVIDER", "dspy-lm-auth")

    result = runner.invoke(
        app,
        [
            "optimize",
            "gepa",
            "--program",
            str(program),
            "--train",
            str(train),
            "--out",
            str(out),
            "--max-metric-calls",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert captured["student_provider"] == "vllm-local"
    assert captured["reflection_provider"] == "dspy-lm-auth"


def test_cli_optimize_gepa_loads_config_before_resolving_provider_defaults(
    monkeypatch, tmp_path: Path
) -> None:
    import dspx.services.optimize_service as optimize_service

    program = tmp_path / "prog.py"
    program.write_text("def build_student():\n    return object()\n", encoding="utf-8")
    train = tmp_path / "train.csv"
    train.write_text("question,answer\nq,a\n", encoding="utf-8")
    out = tmp_path / "out"
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [provider]
        name = "vllm-local"

        [optimize]
        student_provider = "vllm-local"
        reflection_provider = "dspy-lm-auth"
        """,
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_run_gepa_optimize(**kwargs):
        captured.update(kwargs)
        out.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(out_dir=out)

    monkeypatch.setattr(optimize_service, "run_gepa_optimize", _fake_run_gepa_optimize)
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_CONFIG", str(cfg))
    monkeypatch.delenv("DSPX_PROVIDER", raising=False)
    monkeypatch.delenv("DSPX_OPTIMIZE_STUDENT_PROVIDER", raising=False)
    monkeypatch.delenv("DSPX_OPTIMIZE_REFLECTION_PROVIDER", raising=False)

    result = runner.invoke(
        app,
        [
            "optimize",
            "gepa",
            "--program",
            str(program),
            "--train",
            str(train),
            "--out",
            str(out),
            "--max-metric-calls",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert captured["student_provider"] == "vllm-local"
    assert captured["reflection_provider"] == "dspy-lm-auth"


def test_optimize_manifest_includes_provider_runtime_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")

    program = tmp_path / "prog.py"
    program.write_text(
        "\n".join(
            [
                "import dspy",
                "",
                "class Student(dspy.Module):",
                "    def __init__(self):",
                "        super().__init__()",
                "        self.predict = dspy.Predict('question -> answer')",
                "",
                "    def forward(self, question: str) -> dspy.Prediction:",
                "        return self.predict(question=question)",
                "",
                "def build_student() -> dspy.Module:",
                "    return Student()",
                "",
            ]
        ),
        encoding="utf-8",
    )
    train = tmp_path / "train.csv"
    train.write_text("question,answer\nWhat is 2+2?,4\n", encoding="utf-8")
    out_dir = tmp_path / "optimized"

    run_gepa_optimize(
        program_path=program,
        train_path=train,
        out_dir=out_dir,
        auto=None,
        max_metric_calls=1,
        seed=0,
        student_provider="stub",
        reflection_provider="stub",
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    student = manifest["providers"]["student"]
    assert student["provider"] == "stub"
    assert student["capabilities"]["code_exec"] is False
    assert student["runtime"] == {}
