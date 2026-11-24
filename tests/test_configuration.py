"""Regression tests for the ChemML configuration checker."""

from pathlib import Path
import shutil

import pytest
import yaml

from aqdatafusion.config_management.configuration import ConfigurationError
from aqdatafusion.config_management.configuration import check_configuration
from aqdatafusion.config_management.configuration import load_configuration
from aqdatafusion.config_management.configuration import _resolve_known_templates
from aqdatafusion import run_aqdatafusion
import aqdatafusion.aqdatafusion as aqdatafusion_runner


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIGURATION = REPOSITORY_ROOT / "config" / "default_config.yaml"


def test_default_configuration_is_structurally_valid() -> None:
    """The checked-in default configuration should remain internally valid."""

    report = check_configuration(DEFAULT_CONFIGURATION, mode="check")

    assert report.is_valid, report.format()


def test_load_default_configuration() -> None:
    configuration = load_configuration(DEFAULT_CONFIGURATION)

    assert configuration["region"]["region_code"] == "Seoul"
    assert configuration["experiment_name_template"] == "region_{region_code}_experiment_{experiment_code}"
    assert configuration["aqdatafusion"]["inputs"]["GEOS-CF"]["enabled"] is True
    assert not configuration["warnings"]


def test_aqdatafusion_runner_loads_configuration() -> None:
    result = run_aqdatafusion(DEFAULT_CONFIGURATION)

    assert result["status"] == "configuration_loaded"
    assert "not been implemented yet" in result["message"]
    assert result["configuration"]["experiment_name"] == "region_Seoul_experiment_baseline"


def test_aqdatafusion_runner_checks_credentials_when_required(monkeypatch) -> None:
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

    monkeypatch.setattr(aqdatafusion_runner, "manage_credentials", fake_manage_credentials)
    result = run_aqdatafusion(DEFAULT_CONFIGURATION, require_credentials=True)

    assert result["status"] == "credentials_failed"
    assert result["errors"] == ["test credential failure"]
    assert calls["config_path"] == DEFAULT_CONFIGURATION
    assert calls["verify_remote"] is True


def test_aqdatafusion_runner_supports_incremental_database_update(monkeypatch) -> None:
    calls = {}

    def fake_incremental_update(configuration, **kwargs):
        calls["configuration"] = configuration
        calls["kwargs"] = kwargs
        return {"start_time": "2026-11-16T00:00:00+00:00", "sources": {}, "warnings": []}

    monkeypatch.setattr(
        "aqdatafusion.orchestration.run_incremental_database_update",
        fake_incremental_update,
    )
    result = run_aqdatafusion(
        DEFAULT_CONFIGURATION,
        mode="incremental_database_update",
        source_keys=["GEOS-CF"],
    )

    assert result["status"] == "database_updated"
    assert result["report"]["start_time"] == "2026-11-16T00:00:00+00:00"
    assert calls["kwargs"]["source_keys"] == ["GEOS-CF"]


def test_aqdatafusion_runner_reports_when_database_is_already_complete(monkeypatch) -> None:
    monkeypatch.setattr(
        "aqdatafusion.orchestration.run_database_update",
        lambda *args, **kwargs: {
            "start_time": "2026-08-04T00:00:00+00:00",
            "end_time": "2026-08-07T00:00:00+00:00",
            "sources": {"GEOS-CF": {"status": "checked"}},
            "warnings": [],
        },
    )

    result = run_aqdatafusion(
        DEFAULT_CONFIGURATION,
        mode="database_update",
        start_time="2026-08-04T00:00:00Z",
        end_time="2026-08-07T00:00:00Z",
    )

    assert result["status"] == "database_updated"
    assert "no update was needed" in result["message"]


def test_resolve_experiment_name() -> None:
    configuration = load_configuration(DEFAULT_CONFIGURATION)

    assert configuration["experiment_name"] == "region_Seoul_experiment_baseline"


def test_resolve_known_templates_preserves_unknown_templates() -> None:
    value = "{region_code}/{provider}/{month_string}"

    resolved = _resolve_known_templates(value, {"region_code": "Seoul"})

    assert resolved == "Seoul/{provider}/{month_string}"


def test_resolve_filepaths() -> None:
    configuration = load_configuration(DEFAULT_CONFIGURATION)
    filepaths = configuration["filepaths"]

    assert filepaths["working"]["experiment_directory"].endswith(
        "/Seoul/region_Seoul_experiment_baseline"
    )
    assert filepaths["data_sources"]["TROPOMI"].endswith("/Seoul/TROPOMI")


def test_tempo_products_use_separate_input_datasets_and_archive_paths() -> None:
    configuration = load_configuration(DEFAULT_CONFIGURATION)
    datasets = configuration["input_data"]["datasets"]
    data_sources = configuration["filepaths"]["data_sources"]

    assert "TEMPO" not in datasets
    assert {"TEMPO_NO2", "TEMPO_O3"} <= set(datasets)
    assert data_sources["TEMPO_NO2"].endswith("/Seoul/TEMPO_NO2")
    assert data_sources["TEMPO_O3"].endswith("/Seoul/TEMPO_O3")
    assert data_sources["TEMPO_NO2"] != data_sources["TEMPO_O3"]


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
