from __future__ import annotations

from dspx.templates import render_minimal_program, format_codegen_spec


def test_render_minimal_program_python_contains_main_and_task() -> None:
    task = 'A CLI that prints "hello world"'
    code = render_minimal_program("python", task)
    assert 'if __name__ == "__main__"' in code
    assert "hello world" in code


def test_format_codegen_spec_v1_wraps() -> None:
    spec = "Write a script that echoes input"
    out = format_codegen_spec(spec, "python")
    assert "You are a precise code generator" in out
    assert "Target language: python" in out
    assert "Task: Write a script that echoes input" in out
