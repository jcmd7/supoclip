"""Regression tests for the shared task lifecycle contract."""

import pytest

from src.task_lifecycle import (
    TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
    is_terminal_task_status,
)


@pytest.mark.parametrize("status", ["completed", "error", "cancelled"])
def test_terminal_statuses(status: str):
    assert is_terminal_task_status(status)


@pytest.mark.parametrize("status", ["queued", "processing", None, "unknown"])
def test_active_or_unknown_statuses_are_not_terminal(status: str | None):
    assert not is_terminal_task_status(status)


def test_terminal_statuses_are_known_and_complete():
    assert TERMINAL_TASK_STATUSES <= TASK_STATUSES
    assert TASK_STATUSES == {
        "queued",
        "processing",
        "completed",
        "error",
        "cancelled",
    }
