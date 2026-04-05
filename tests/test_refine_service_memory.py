from __future__ import annotations

from typing import Any, cast

from dspx.templates import render_simple_signature
import dspx.services.refine_service as refine


def test_refine_non_interactive_passes_attempt_budget(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    seen: dict[str, object] = {}

    def _fake_native(
        prompt: str,
        *,
        class_name: str = "GeneratedSignature",
        attempts: int = 1,
        constraints=None,
        feedback=None,
        lm=None,
    ) -> str:
        seen["prompt"] = prompt
        seen["attempts"] = attempts
        seen["constraints"] = list(constraints or [])
        seen["feedback"] = list(feedback or [])
        return render_simple_signature(class_name, "refined")

    monkeypatch.setattr(refine, "_native_generate_signature", _fake_native)

    code = refine.run_refine(
        "Create a signature",
        attempts=4,
        non_interactive=True,
        lm=cast(Any, object()),
    )

    assert "class GeneratedSignature(dspy.Signature):" in code
    assert seen["attempts"] == 4
    assert seen["feedback"] == []


def test_refine_interactive_uses_structured_feedback_memory(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    prompts: list[str] = []

    def _fake_native(
        prompt: str,
        *,
        class_name: str = "GeneratedSignature",
        attempts: int = 1,
        constraints=None,
        feedback=None,
        lm=None,
    ) -> str:
        prompts.append(prompt)
        return render_simple_signature(class_name, "refined")

    # First reject, add feedback, second accept.
    answers = iter(["n", "Use explicit output field and preserve class name.", "y"])
    monkeypatch.setattr(refine, "_native_generate_signature", _fake_native)
    monkeypatch.setattr("builtins.input", lambda _msg="": next(answers))

    code = refine.run_refine(
        "Create a signature",
        attempts=2,
        non_interactive=False,
        lm=cast(Any, object()),
    )

    assert "class GeneratedSignature(dspy.Signature):" in code
    assert len(prompts) == 2
    assert "Refinement feedback history" in prompts[1]
    assert "Use explicit output field" in prompts[1]


def test_refine_interactive_fails_closed_without_tty(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    class _Stream:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(refine.sys, "stdin", _Stream())
    monkeypatch.setattr(refine.sys, "stdout", _Stream())

    try:
        refine.run_refine(
            "Create a signature",
            attempts=1,
            non_interactive=False,
            lm=cast(Any, object()),
        )
    except RuntimeError as exc:
        assert "requires a TTY" in str(exc)
    else:  # pragma: no cover - fail closed assertion
        raise AssertionError(
            "expected RuntimeError when interactive prompting is unavailable"
        )
