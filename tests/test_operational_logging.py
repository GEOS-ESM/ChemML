"""Tests for human-readable database-update operational reports."""

import os
from datetime import datetime, timedelta, timezone

from aqforecast.utils.operational_logging import write_database_update_report


def _configuration(log_directory, retain_days=365):
    return {
        "filepaths": {"working": {"logs_directory": str(log_directory)}},
        "aqforecast": {"database": {"operational_logging": {"retain_days": retain_days}}},
    }


def test_operational_report_contains_source_summary_warnings_and_errors(tmp_path):
    started_at = datetime(2026, 11, 18, 19, 0, tzinfo=timezone.utc)
    report = {
        "start_time": "2026-11-16T19:00:00+00:00",
        "end_time": "2026-11-23T19:00:00+00:00",
        "sources": {
            "GEOS-CF": {
                "status": "updated",
                "written_files": ["GEOS-CF_ATL_202611.nc"],
                "missing_timestamps": ["2026-11-20T00:00:00+00:00"],
                "catalog_files": 1,
                "integrity": {"valid": True},
            },
            "broken": {
                "status": "failed",
                "errors": [{"kind": "source", "message": "service unavailable"}],
                "error": "request failed",
            },
        },
        "warnings": ["GEOS-CF: one forecast timestamp was unavailable"],
    }

    path, warnings = write_database_update_report(
        _configuration(tmp_path), "incremental_database_update", started_at, report
    )

    contents = path.read_text(encoding="utf-8")
    assert path.name == "incremental_database_update_20261118T190000.000000Z.txt"
    assert not warnings
    assert "GEOS-CF: UPDATED" in contents
    assert "broken: FAILED" in contents
    assert "one forecast timestamp was unavailable" in contents
    assert "service unavailable" in contents
    assert "ERRORS AND FAILURES" in contents


def test_operational_report_cleanup_removes_only_expired_reports(tmp_path):
    old_report = tmp_path / "database_update_20240101T000000.000000Z.txt"
    old_report.write_text("old", encoding="utf-8")
    unrelated = tmp_path / "aqforecast.log"
    unrelated.write_text("keep", encoding="utf-8")
    old_time = (datetime.now(timezone.utc) - timedelta(days=3)).timestamp()
    os.utime(old_report, (old_time, old_time))

    report = {"start_time": "x", "end_time": "y", "sources": {}, "warnings": []}
    write_database_update_report(
        _configuration(tmp_path, retain_days=1),
        "database_update",
        datetime.now(timezone.utc),
        report,
    )

    assert not old_report.exists()
    assert unrelated.exists()
