"""Contracts for future workflow orchestration."""

from __future__ import annotations

from typing import Protocol

from aqforecast.contracts import WorkflowContext


class WorkflowStage(Protocol):
    """A composable operation that updates shared workflow context."""

    name: str

    def run(self, context: WorkflowContext) -> WorkflowContext:
        """Execute this stage and return the updated context."""


__all__ = ["WorkflowStage"]
