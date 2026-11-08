"""Public task lifecycle contract shared by API progress and cancellation endpoints.

The current repository's database writes are not yet transition-fenced. This
module identifies status semantics; it does not claim to enforce transitions.
"""

from typing import Final

TASK_STATUSES: Final[frozenset[str]] = frozenset(
    {"queued", "processing", "completed", "error", "cancelled"}
)
TERMINAL_TASK_STATUSES: Final[frozenset[str]] = frozenset(
    {"completed", "error", "cancelled"}
)


def is_terminal_task_status(status: str | None) -> bool:
    """Whether a task can no longer emit normal processing progress."""
    return status in TERMINAL_TASK_STATUSES
