# summary: "Tests direct-run template support for DesignMD visual image input materialization."
# read_when:
#   - "Changing generated direct-run image adapters or missing-image preflight behavior."

from __future__ import annotations

from dspx.services.program_surfaces import render_direct_run_code


def test_direct_run_template_materializes_designmd_visual_image_inputs() -> None:
    direct_run_text = render_direct_run_code(None)

    assert (
        "def _materialize_designmd_visual_image_inputs_text(value: str) -> str:"
        in direct_run_text
    )
    assert "modelImageInput" in direct_run_text
    assert "dspy.Image(data-uri)" in direct_run_text
    assert "not_run_due_to_missing_image_input_adapter" in direct_run_text
