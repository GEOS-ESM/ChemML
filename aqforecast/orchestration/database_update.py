"""Database-update workflow stage and public orchestration helper."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from aqforecast.contracts import WorkflowContext
from aqforecast.data_management import DatabaseManager


class DatabaseUpdateStage:
    """Run an incremental input-data database update for a workflow context."""

    name = "database_update"

    def __init__(self, start_time: Any, end_time: Any, *, source_keys: Optional[Sequence[str]] = None, conflict_policy: str = "fill_missing", override: bool = False, manager: Optional[DatabaseManager] = None):
        self.start_time = start_time
        self.end_time = end_time
        self.source_keys = source_keys
        self.conflict_policy = conflict_policy
        self.override = override
        self.manager = manager

    def run(self, context: WorkflowContext) -> WorkflowContext:
        manager = self.manager or DatabaseManager(context.configuration)
        report = manager.update(self.start_time, self.end_time, source_keys=self.source_keys, conflict_policy=self.conflict_policy, override=self.override)
        context.features["database_update"] = report.as_dict()
        context.warnings.extend(report.warnings)
        return context


def run_database_update(configuration: Mapping[str, Any], start_time: Any, end_time: Any, *, source_keys: Optional[Sequence[str]] = None, conflict_policy: str = "fill_missing", override: bool = False, data_sources: Optional[Mapping[str, Any]] = None, preprocessors: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Execute database-update mode without invoking forecasting stages."""
    manager = DatabaseManager(configuration, data_sources=data_sources, preprocessors=preprocessors)
    return manager.update(start_time, end_time, source_keys=source_keys, conflict_policy=conflict_policy, override=override).as_dict()


__all__ = ["DatabaseUpdateStage", "run_database_update"]
