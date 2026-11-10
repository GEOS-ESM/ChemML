"""Regression tests for the ChemML configuration checker."""

from pathlib import Path

from aqforecast.config_management.configuration import check_configuration


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIGURATION = REPOSITORY_ROOT / "config" / "default_config.yaml"


def test_default_configuration_is_structurally_valid() -> None:
    """The checked-in default configuration should remain internally valid."""

    report = check_configuration(DEFAULT_CONFIGURATION, mode="check")

    assert report.is_valid, report.format()
