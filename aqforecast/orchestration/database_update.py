"""Database-update workflow stage and public orchestration helper."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

import pandas as pd

from aqforecast.contracts import WorkflowContext
from aqforecast.data_management import DatabaseManager
from aqforecast.utils.operational_logging import write_database_update_report


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


def run_database_update(configuration: Mapping[str, Any], start_time: Any, end_time: Any, *, source_keys: Optional[Sequence[str]] = None, conflict_policy: str = "fill_missing", override: bool = False, data_sources: Optional[Mapping[str, Any]] = None, preprocessors: Optional[Mapping[str, Any]] = None, operation_name: str = "database_update") -> dict[str, Any]:
    """Execute database-update mode without invoking forecasting stages."""
    started_at = datetime.now(timezone.utc)
    manager = DatabaseManager(configuration, data_sources=data_sources, preprocessors=preprocessors)
    try:
        result = manager.update(start_time, end_time, source_keys=source_keys, conflict_policy=conflict_policy, override=override).as_dict()
    except Exception as error:
        failure = {
            "start_time": str(start_time),
            "end_time": str(end_time),
            "sources": {},
            "warnings": [],
            "error": {"type": type(error).__name__, "message": str(error)},
        }
        write_database_update_report(configuration, operation_name, started_at, failure)
        raise
    report_path, report_warnings = write_database_update_report(
        configuration, operation_name, started_at, result
    )
    result["operational_report_path"] = str(report_path)
    if report_warnings:
        result.setdefault("warnings", []).extend(report_warnings)
    return result


def _incremental_update_window(
    configuration: Mapping[str, Any], now: Any = None
) -> tuple[pd.Timestamp, pd.Timestamp, dict[str, Any]]:
    """Calculate the UTC-aligned rolling window for an incremental update."""

    settings = (
        configuration.get("aqforecast", {})
        .get("database", {})
        .get("incremental_update", {})
    )
    if not isinstance(settings, Mapping):
        raise ValueError("aqforecast.database.incremental_update must be a mapping")
    timezone_name = str(settings.get("timezone", "UTC"))
    if timezone_name != "UTC":
        raise ValueError("incremental_update.timezone must be UTC")
    if str(settings.get("time_alignment", "hour")) != "hour":
        raise ValueError("incremental_update.time_alignment must be 'hour'")
    try:
        lookback_days = float(settings.get("lookback_days", 2))
        lookahead_days = float(settings.get("lookahead_days", 5))
        max_window_days = float(settings.get("max_window_days", 14))
    except (TypeError, ValueError) as error:
        raise ValueError(
            "incremental update day settings must be numeric"
        ) from error
    if lookback_days < 0 or lookahead_days <= 0:
        raise ValueError("lookback_days must be non-negative and lookahead_days must be positive")
    window_days = lookback_days + lookahead_days
    if max_window_days <= 0 or window_days > max_window_days:
        raise ValueError(
            "incremental update window exceeds max_window_days: "
            f"{window_days:g} > {max_window_days:g}"
        )
    anchor = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if anchor.tzinfo is None:
        anchor = anchor.tz_localize("UTC")
    else:
        anchor = anchor.tz_convert("UTC")
    anchor = anchor.floor("h")
    start = anchor - pd.Timedelta(days=lookback_days)
    end = anchor + pd.Timedelta(days=lookahead_days)
    metadata = {
        "anchor_time": anchor.isoformat(),
        "lookback_days": lookback_days,
        "lookahead_days": lookahead_days,
        "max_window_days": max_window_days,
        "timezone": timezone_name,
        "time_alignment": "hour",
    }
    return start, end, metadata


def run_incremental_database_update(
    configuration: Mapping[str, Any],
    *,
    now: Any = None,
    source_keys: Optional[Sequence[str]] = None,
    conflict_policy: Optional[str] = None,
    override: bool = False,
    data_sources: Optional[Mapping[str, Any]] = None,
    preprocessors: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Update databases over the configured rolling window ending in the future.

    ``now`` is injectable for deterministic tests; production callers should
    omit it so the system UTC time is used. Scheduling this explicit function
    is intentionally left to cron or an NCCS batch wrapper.
    """

    start, end, metadata = _incremental_update_window(configuration, now)
    database_settings = configuration.get("aqforecast", {}).get("database", {})
    selected_policy = conflict_policy or database_settings.get(
        "default_conflict_policy", "fill_missing"
    )
    result = run_database_update(
        configuration,
        start,
        end,
        source_keys=source_keys,
        conflict_policy=selected_policy,
        override=override,
        data_sources=data_sources,
        preprocessors=preprocessors,
        operation_name="incremental_database_update",
    )
    result["incremental_update"] = metadata
    return result


__all__ = [
    "DatabaseUpdateStage",
    "run_database_update",
    "run_incremental_database_update",
]
