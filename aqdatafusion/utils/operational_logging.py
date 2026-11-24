"""Human-readable operational reports for database-update runs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


REPORT_PREFIXES = ("database_update_", "incremental_database_update_")


def _retention_days(configuration: Mapping[str, Any]) -> float:
    value = (
        configuration.get("aqdatafusion", {})
        .get("database", {})
        .get("operational_logging", {})
        .get("retain_days", 365)
    )
    try:
        days = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("operational_logging.retain_days must be numeric") from error
    if days < 0:
        raise ValueError("operational_logging.retain_days must be non-negative")
    return days


def _logs_directory(configuration: Mapping[str, Any]) -> Path:
    try:
        value = configuration["filepaths"]["working"]["logs_directory"]
    except (KeyError, TypeError) as error:
        raise KeyError(
            "configuration does not specify filepaths.working.logs_directory"
        ) from error
    if not isinstance(value, str) or not value:
        raise ValueError("filepaths.working.logs_directory must be a non-empty path")
    return Path(value).expanduser()


def _is_report_file(path: Path) -> bool:
    return path.is_file() and path.suffix == ".txt" and path.name.startswith(REPORT_PREFIXES)


def _cleanup_reports(directory: Path, started_at: datetime, retain_days: float) -> list[str]:
    cutoff = started_at - timedelta(days=retain_days)
    warnings: list[str] = []
    for path in directory.iterdir():
        if not _is_report_file(path):
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if modified < cutoff:
                path.unlink()
        except OSError as error:
            warnings.append(f"could not remove old operational report {path.name}: {error}")
    return warnings


def _source_summary(source_key: str, source: Mapping[str, Any]) -> list[str]:
    status = source.get("status", "unknown")
    lines = [f"{source_key}: {status.upper()}"]
    wall_time = source.get("wall_time_seconds")
    if isinstance(wall_time, (int, float)):
        lines.append(f"  Wall time: {wall_time:.3f} seconds")
    elif wall_time is not None:
        lines.append(f"  Wall time: {wall_time} seconds")
    written = source.get("written_files", [])
    lines.append(f"  Written files: {len(written)}")
    if written:
        lines.extend(f"    - {path}" for path in written)
    lines.append(f"  Missing timestamps requested: {len(source.get('missing_timestamps', []))}")
    if "catalog_files" in source:
        lines.append(f"  Catalog files: {source['catalog_files']}")
    integrity = source.get("integrity")
    if isinstance(integrity, Mapping):
        lines.append(f"  Integrity valid: {integrity.get('valid', False)}")
    warnings = source.get("warnings", [])
    if warnings:
        lines.append(f"  Warnings: {len(warnings)}")
    errors = source.get("errors", [])
    if errors or source.get("error"):
        lines.append(f"  Errors: {len(errors) + (1 if source.get('error') else 0)}")
    return lines


def _format_report(
    operation: str,
    started_at: datetime,
    report: Mapping[str, Any],
    retain_days: float,
) -> str:
    source_reports = report.get("sources", {})
    failures = [
        key for key, value in source_reports.items()
        if isinstance(value, Mapping) and value.get("status") == "failed"
    ]
    lines = [
        "ChemML database update operational report",
        "=" * 44,
        f"Operation: {operation}",
        f"Run initiated: {started_at.isoformat()}",
        f"Requested interval: {report.get('start_time', 'unknown')} to {report.get('end_time', 'unknown')} (half-open)",
        f"Sources failed: {len(failures)}",
        f"Report retention: {retain_days:g} days",
        "",
        "SOURCE RESULTS",
        "--------------",
    ]
    if source_reports:
        for source_key, source in source_reports.items():
            lines.extend(_source_summary(source_key, source))
    else:
        lines.append("No source results were returned.")
    warnings = report.get("warnings", [])
    lines.extend(["", "WARNINGS", "--------"])
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("None")
    lines.extend(["", "ERRORS AND FAILURES", "-------------------"])
    if failures:
        lines.extend(f"FAILED SOURCE: {source_key}" for source_key in failures)
    else:
        lines.append("None")
    lines.extend(
        [
            "",
            "DETAILED REPORT DATA",
            "--------------------",
            json.dumps(report, indent=2, sort_keys=True, default=str),
            "",
        ]
    )
    return "\n".join(lines)


def write_database_update_report(
    configuration: Mapping[str, Any],
    operation: str,
    started_at: datetime,
    report: Mapping[str, Any],
) -> tuple[Path, list[str]]:
    """Write one report and remove operational reports past their retention."""

    retain_days = _retention_days(configuration)
    directory = _logs_directory(configuration)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = started_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"{operation}_{timestamp}.txt"
    path.write_text(
        _format_report(operation, started_at, report, retain_days),
        encoding="utf-8",
    )
    warnings = _cleanup_reports(directory, started_at, retain_days)
    return path, warnings


__all__ = ["write_database_update_report"]
