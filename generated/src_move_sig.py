import dspy
from typing import Optional

class EchoAfterSrcMove(dspy.Signature):
    """Create a signature that, given details about a source file move (original and new paths) and optional content/context, produces an echo/confirmation message summarizing the move."""

    original_path: str = dspy.InputField(desc="The original source file path before the move")
    new_path: str = dspy.InputField(desc="The new destination path after the move")
    include_diff_summary: bool = dspy.InputField(desc="Whether to include a brief summary of changes/diff in the echo")
    context_note: Optional[str] = dspy.InputField(desc="Optional note providing context for why the file was moved")
    echo_message: str = dspy.OutputField(desc="Human-readable confirmation summarizing the move from original to new path, optionally with context or diff summary")