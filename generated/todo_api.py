import dspy
from typing import Any, Dict, List, Literal, Optional

class TodoApiSignature(dspy.Signature):
    """Define a clean API signature for a small todo app that supports creating, reading, updating, deleting, and listing todo items, including basic metadata like status, priority, and due dates."""

    operation: Literal['create', 'get', 'update', 'delete', 'list'] = dspy.InputField(desc="The API action to perform: create, get, update, delete, or list")
    todo_id: Optional[str] = dspy.InputField(desc="Identifier of the todo item (required for get, update, delete)")
    title: Optional[str] = dspy.InputField(desc="Short title for the todo (required for create)")
    description: Optional[str] = dspy.InputField(desc="Longer description or notes for the todo")
    status: Optional[str] = dspy.InputField(desc="Todo status value")
    priority: Optional[int] = dspy.InputField(desc="Priority as an integer (e.g., 1=high, 3=low)")
    due_date: Optional[str] = dspy.InputField(desc="ISO 8601 due date string (e.g., 2025-09-01T12:00:00Z)")
    labels: Optional[str] = dspy.InputField(desc="Comma-separated labels/tags to associate with the todo")
    list_filters: dict[str, Any] = dspy.InputField(desc="Filters for list operation (keys like status, label, before, after)")
    result_code: int = dspy.OutputField(desc="Result status code (e.g., 0=success, non-zero=error)")
    error_message: Optional[str] = dspy.OutputField(desc="Error message when operation fails, else null")
    todo: dict[str, Any] = dspy.OutputField(desc="The created/updated/fetched todo object (empty for delete or list)")
    todos: list[str] = dspy.OutputField(desc="Serialized list of todos for list operation (empty otherwise)")