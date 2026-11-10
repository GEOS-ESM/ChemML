"""Tests for the ChemML logging utility."""

from pathlib import Path

import pytest

from aqforecast.utils.logging import configure_logging


def test_configure_logging_writes_to_configured_directory_and_redacts_credentials(
    tmp_path: Path,
) -> None:
    log_directory = tmp_path / "logs"
    configuration = {
        "filepaths": {"working": {"logs_directory": str(log_directory)}},
        "credentials": {"earthdata": {"password": "secret-password"}},
    }

    logger = configure_logging(
        configuration,
        logger_name="test.aqforecast.logging",
        console=False,
        create_directory=True,
    )
    logger.info("credential=%s", "secret-password")
    for handler in logger.handlers:
        handler.flush()

    contents = (log_directory / "aqforecast.log").read_text(encoding="utf-8")
    assert "secret-password" not in contents
    assert "[REDACTED]" in contents


def test_configure_logging_requires_existing_directory_by_default(tmp_path: Path) -> None:
    configuration = {
        "filepaths": {"working": {"logs_directory": str(tmp_path / "missing")}},
    }

    with pytest.raises(FileNotFoundError):
        configure_logging(configuration, console=False)
