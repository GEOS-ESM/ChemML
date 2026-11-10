"""Regression tests for the ChemML configuration checker."""

from pathlib import Path
import shutil

import pytest
import yaml

from aqforecast.config_management.configuration import ConfigurationError
from aqforecast.config_management.configuration import check_configuration
from aqforecast.config_management.configuration import load_configuration
from aqforecast import run_aqforecast
import aqforecast.aqforecast as aqforecast_runner


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIGURATION = REPOSITORY_ROOT / "config" / "default_config.yaml"


def test_default_configuration_is_structurally_valid() -> None:
    """The checked-in default configuration should remain internally valid."""

    report = check_configuration(DEFAULT_CONFIGURATION, mode="check")

    assert report.is_valid, report.format()


def test_load_default_configuration() -> None:
    configuration = load_configuration(DEFAULT_CONFIGURATION)

    assert configuration["region"]["region_code"] == "Seoul"
    assert configuration["aqforecast"]["inputs"]["GEOS-CF"]["enabled"] is True
    assert configuration["warnings"]


def test_aqforecast_runner_loads_configuration() -> None:
    result = run_aqforecast(DEFAULT_CONFIGURATION)

    assert result["status"] == "configuration_loaded"
    assert "not been implemented yet" in result["message"]
    assert result["configuration"]["experiment_name"] == "region_Seoul_experiment_baseline"


def test_aqforecast_runner_checks_credentials_when_required(monkeypatch) -> None:
    calls = {}

    def fake_manage_credentials(config_path, *, verify_remote):
        calls["config_path"] = config_path
        calls["verify_remote"] = verify_remote
        return {
            "status": "invalid",
            "message": "test credential failure",
            "warnings": [],
            "errors": ["test credential failure"],
        }

    monkeypatch.setattr(aqforecast_runner, "manage_credentials", fake_manage_credentials)
    result = run_aqforecast(DEFAULT_CONFIGURATION, require_credentials=True)

    assert result["status"] == "credentials_failed"
    assert result["errors"] == ["test credential failure"]
    assert calls["config_path"] == DEFAULT_CONFIGURATION
    assert calls["verify_remote"] is True


def test_resolve_experiment_name() -> None:
    configuration = load_configuration(DEFAULT_CONFIGURATION)

    assert configuration["experiment_name"] == "region_Seoul_experiment_baseline"


def test_resolve_filepaths() -> None:
    configuration = load_configuration(DEFAULT_CONFIGURATION)
    filepaths = configuration["filepaths"]

    assert filepaths["working"]["experiment_directory"].endswith(
        "/Seoul/region_Seoul_experiment_baseline"
    )
    assert filepaths["data_sources"]["TROPOMI"].endswith("/Seoul/TROPOMI")


def _copy_configuration_tree(tmp_path: Path) -> Path:
    temporary_config = tmp_path / "config"
    shutil.copytree(REPOSITORY_ROOT / "config", temporary_config)
    credentials = temporary_config / "credentials" / "credentials.yaml"
    if credentials.exists():
        credentials.unlink()
    return temporary_config


def _write_yaml(path: Path, value: dict) -> None:
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(value, stream, sort_keys=False)


def test_missing_referenced_file_is_detected(tmp_path: Path) -> None:
    temporary_config = _copy_configuration_tree(tmp_path)
    default_path = temporary_config / "default_config.yaml"
    with default_path.open(encoding="utf-8") as stream:
        default = yaml.safe_load(stream)
    default["configuration_files"]["validation"] = "validation/missing.yaml"
    _write_yaml(default_path, default)

    with pytest.raises(ConfigurationError, match="referenced file does not exist"):
        load_configuration(default_path)


def test_malformed_setting_is_detected(tmp_path: Path) -> None:
    temporary_config = _copy_configuration_tree(tmp_path)
    region_path = temporary_config / "regions" / "example_region.yaml"
    with region_path.open(encoding="utf-8") as stream:
        region = yaml.safe_load(stream)
    region["bounds"]["latitude"] = ["not-a-number", 38.0]
    _write_yaml(region_path, region)

    with pytest.raises(ConfigurationError, match="two-number list"):
        load_configuration(temporary_config / "default_config.yaml")


def test_conflicting_source_key_is_detected(tmp_path: Path) -> None:
    temporary_config = _copy_configuration_tree(tmp_path)
    input_path = temporary_config / "inputs" / "input_data_config.yaml"
    with input_path.open(encoding="utf-8") as stream:
        input_data = yaml.safe_load(stream)
    input_data["datasets"]["GEOS-CF"]["source_key"] = "geos_cf"
    _write_yaml(input_path, input_data)

    with pytest.raises(ConfigurationError, match="must equal dataset name"):
        load_configuration(temporary_config / "default_config.yaml")
