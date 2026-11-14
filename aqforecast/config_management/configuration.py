"""Load and validate the ChemML component configuration files.

The public entry point is :func:`check_configuration`.  It can be used from
another setup or pre-run function, or through the command line::

    python aqforecast/config_management/configuration.py config/default_config.yaml
    python aqforecast/config_management/configuration.py config/default_config.yaml --interactive

Checking mode never writes files.  Interactive mode prompts for fixable
missing or invalid values, validates each response, and writes accepted values
to the file that owns the setting.

This module intentionally performs configuration validation only.  It does not
import DeepSensor, access remote data, or create output directories.
"""

from __future__ import annotations

import argparse
import copy
import getpass
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import yaml


DEFAULT_SOURCE_NAMES = (
    "ground_monitors",
    "GEOS-CF",
    "TEMPO_NO2",
    "TEMPO_O3",
    "GEMS",
    "TROPOMI",
    "PACE",
    "VIIRS",
    "land_cover",
    "GCAS",
    "GOES-ABI",
)

DEFERRED_SOURCES = {"PACE", "VIIRS", "GOES-ABI"}
PLACEHOLDER_PATTERN = re.compile(r"<[^>]+>")
PATH_TEMPLATE_PATTERN = re.compile(r"\{([^{}]+)\}")


@dataclass
class ConfigurationIssue:
    """A validation finding associated with one configuration setting."""

    severity: str
    file: Optional[Path]
    setting: str
    message: str
    fixable: bool = False
    expected_type: Optional[str] = None
    secret: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "file": str(self.file) if self.file else None,
            "setting": self.setting,
            "message": self.message,
            "fixable": self.fixable,
        }


class ConfigurationError(ValueError):
    """Raised when a configuration cannot be used at runtime."""

    def __init__(self, report: "ConfigurationReport") -> None:
        self.report = report
        super().__init__(report.format())


@dataclass
class ConfigurationReport:
    """Results returned by :func:`check_configuration`."""

    root_file: Path
    issues: List[ConfigurationIssue] = field(default_factory=list)
    changed_files: List[Path] = field(default_factory=list)

    @property
    def errors(self) -> List[ConfigurationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> List[ConfigurationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> Dict[str, Any]:
        return {
            "root_file": str(self.root_file),
            "valid": self.is_valid,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "changed_files": [str(path) for path in self.changed_files],
            "issues": [issue.as_dict() for issue in self.issues],
        }

    def format(self) -> str:
        """Return a concise human-readable report."""

        if not self.issues:
            return "Configuration is valid."

        lines = [
            f"Configuration: {'valid' if self.is_valid else 'invalid'}",
            f"Errors: {len(self.errors)}; warnings: {len(self.warnings)}",
        ]
        for issue in self.issues:
            location = f"{issue.file}: {issue.setting}" if issue.file else issue.setting
            lines.append(f"[{issue.severity}] {location} - {issue.message}")
        if self.changed_files:
            lines.append("Changed files:")
            lines.extend(f"  - {path}" for path in self.changed_files)
        return "\n".join(lines)


@dataclass
class _LoadedConfiguration:
    root_file: Path
    files: Dict[str, Path]
    data: Dict[str, Dict[str, Any]]


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as stream:
            value = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("top-level YAML value must be a mapping")
    return value


def _load_referenced_files(
    root_file: Path,
    report: ConfigurationReport,
    *,
    allow_missing_credentials: bool = False,
) -> _LoadedConfiguration:
    files: Dict[str, Path] = {"default": root_file}
    data: Dict[str, Dict[str, Any]] = {}

    try:
        data["default"] = _load_yaml(root_file)
    except (OSError, ValueError) as exc:
        report.issues.append(ConfigurationIssue("error", root_file, "$", str(exc)))
        return _LoadedConfiguration(root_file, files, data)

    references = data["default"].get("configuration_files")
    if not isinstance(references, dict):
        report.issues.append(
            ConfigurationIssue(
                "error",
                root_file,
                "configuration_files",
                "must be a mapping of component names to YAML files",
                fixable=True,
                expected_type="mapping",
            )
        )
        return _LoadedConfiguration(root_file, files, data)

    config_directory = root_file.parent
    for component, relative_path in references.items():
        setting = f"configuration_files.{component}"
        if not isinstance(relative_path, str) or not relative_path.strip():
            report.issues.append(
                ConfigurationIssue(
                    "error",
                    root_file,
                    setting,
                    "must be a non-empty relative YAML path",
                )
            )
            continue
        component_path = (config_directory / relative_path).resolve()
        files[str(component)] = component_path
        if not component_path.is_file():
            if component == "credentials" and allow_missing_credentials:
                report.issues.append(
                    ConfigurationIssue(
                        "warning",
                        root_file,
                        setting,
                        "local credentials file is absent; credentials are not checked in",
                    )
                )
                continue
            report.issues.append(
                ConfigurationIssue(
                    "error",
                    root_file,
                    setting,
                    f"referenced file does not exist: {component_path}",
                )
            )
            continue
        try:
            data[str(component)] = _load_yaml(component_path)
        except (OSError, ValueError) as exc:
            report.issues.append(ConfigurationIssue("error", component_path, "$", str(exc)))

    return _LoadedConfiguration(root_file, files, data)


def _get(mapping: Mapping[str, Any], path: Sequence[str]) -> Any:
    value: Any = mapping
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value


def _has_value(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(PLACEHOLDER_PATTERN.search(value))


def _setting_name(path: Sequence[str]) -> str:
    return ".".join(path)


def _add_required(
    report: ConfigurationReport,
    component: str,
    loaded: _LoadedConfiguration,
    path: Sequence[str],
    expected_type: str,
    *,
    secret: bool = False,
) -> None:
    value = _get(loaded.data.get(component, {}), path)
    if not _has_value(value) or _is_placeholder(value):
        report.issues.append(
            ConfigurationIssue(
                "error",
                loaded.files.get(component),
                _setting_name(path),
                f"required {expected_type} has not been specified",
                fixable=True,
                expected_type=expected_type,
                secret=secret,
            )
        )
        return
    if not _matches_expected_type(value, expected_type):
        _add_type_error(
            report,
            component,
            loaded,
            path,
            f"must be a {expected_type}",
        )


def _matches_expected_type(value: Any, expected_type: str) -> bool:
    if expected_type in {"string", "path", "path template", "IANA timezone string"}:
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "positive integer":
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    if expected_type == "positive number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
    if expected_type == "list":
        return isinstance(value, list)
    if expected_type == "non-empty list":
        return isinstance(value, list) and bool(value)
    if expected_type == "two-number list":
        return isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) for item in value)
    if expected_type == "mapping":
        return isinstance(value, Mapping)
    if expected_type == "non-empty mapping":
        return isinstance(value, Mapping) and bool(value)
    return True


def _add_type_error(
    report: ConfigurationReport,
    component: str,
    loaded: _LoadedConfiguration,
    path: Sequence[str],
    message: str,
) -> None:
    report.issues.append(
        ConfigurationIssue(
            "error",
            loaded.files.get(component),
            _setting_name(path),
            message,
            fixable=True,
        )
    )


def _validate_master(loaded: _LoadedConfiguration, report: ConfigurationReport) -> None:
    config = loaded.data.get("default", {})
    _add_required(report, "default", loaded, ("config_version",), "integer")
    _add_required(report, "default", loaded, ("experiment_name_template",), "string")
    _add_required(report, "default", loaded, ("experiment_code",), "string")
    template = config.get("experiment_name_template")
    if _has_value(template) and not isinstance(template, str):
        _add_type_error(report, "default", loaded, ("experiment_name_template",), "must be a string")


def _validate_region(loaded: _LoadedConfiguration, report: ConfigurationReport) -> None:
    component = "region"
    if component not in loaded.data:
        return
    config = loaded.data[component]
    for path, expected in (
        (("region_code",), "string"),
        (("name",), "string"),
        (("bounds", "latitude"), "two-number list"),
        (("bounds", "longitude"), "two-number list"),
        (("output_grid", "resolution_degrees"), "positive number"),
        (("ground_monitoring", "provider"), "string"),
        (("timezone",), "IANA timezone string"),
    ):
        _add_required(report, component, loaded, path, expected)

    for axis in ("latitude", "longitude"):
        bounds = _get(config, ("bounds", axis))
        if bounds is None or _is_placeholder(bounds):
            continue
        if not isinstance(bounds, list) or len(bounds) != 2 or not all(isinstance(item, (int, float)) for item in bounds):
            _add_type_error(report, component, loaded, ("bounds", axis), "must be a two-number list")
        elif bounds[0] >= bounds[1]:
            _add_type_error(report, component, loaded, ("bounds", axis), "lower bound must be less than upper bound")

    resolution = _get(config, ("output_grid", "resolution_degrees"))
    if _has_value(resolution) and not _is_placeholder(resolution):
        if not isinstance(resolution, (int, float)) or resolution <= 0:
            _add_type_error(report, component, loaded, ("output_grid", "resolution_degrees"), "must be a positive number")

    timezone = config.get("timezone")
    if _has_value(timezone) and not _is_placeholder(timezone):
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(str(timezone))
        except (KeyError, ValueError):
            _add_type_error(report, component, loaded, ("timezone",), "must be a valid IANA timezone")


def _validate_credentials(
    loaded: _LoadedConfiguration,
    report: ConfigurationReport,
    *,
    require_credentials: bool,
) -> None:
    component = "credentials"
    if component not in loaded.data:
        return
    for path in (
        ("earthdata", "username"),
        ("earthdata", "password"),
        ("nccs", "username"),
        ("nccs", "project"),
    ):
        if not require_credentials and not _has_value(_get(loaded.data[component], path)):
            report.issues.append(
                ConfigurationIssue(
                    "warning",
                    loaded.files.get(component),
                    _setting_name(path),
                    "local credential has not been configured",
                )
            )
        else:
            _add_required(report, component, loaded, path, "string", secret=path[-1] in {"password"})


def _validate_filepaths(loaded: _LoadedConfiguration, report: ConfigurationReport, check_paths: bool) -> None:
    component = "filepaths"
    if component not in loaded.data:
        return
    config = loaded.data[component]
    for path in (("roots", "input"), ("roots", "output")):
        _add_required(report, component, loaded, path, "path")
        value = _get(config, path)
        if check_paths and _has_value(value) and not _is_placeholder(value) and not Path(str(value)).exists():
            report.issues.append(ConfigurationIssue("error", loaded.files[component], _setting_name(path), f"path does not exist: {value}"))

    for path in (
        ("working", "experiment_directory"),
        ("working", "logs_directory"),
        ("working", "models_directory"),
        ("working", "forecasts_directory"),
        ("working", "validation_directory"),
    ):
        _add_required(report, component, loaded, path, "path template")

    sources = config.get("data_sources")
    if not isinstance(sources, Mapping):
        _add_type_error(report, component, loaded, ("data_sources",), "must be a mapping")
        return
    missing = set(DEFAULT_SOURCE_NAMES) - set(sources)
    extra = set(sources) - set(DEFAULT_SOURCE_NAMES)
    if missing:
        report.issues.append(ConfigurationIssue("error", loaded.files[component], "data_sources", f"missing sources: {', '.join(sorted(missing))}"))
    if extra:
        report.issues.append(ConfigurationIssue("warning", loaded.files[component], "data_sources", f"unrecognized sources: {', '.join(sorted(extra))}"))
    for source_name in DEFAULT_SOURCE_NAMES:
        value = sources.get(source_name)
        if not _has_value(value):
            report.issues.append(ConfigurationIssue("error", loaded.files[component], f"data_sources.{source_name}", "source path is empty", fixable=True, expected_type="path"))
        elif "{region_code}" not in str(value):
            report.issues.append(ConfigurationIssue("error", loaded.files[component], f"data_sources.{source_name}", "path must include {region_code}"))


def _validate_input_data(loaded: _LoadedConfiguration, report: ConfigurationReport) -> None:
    component = "input_data"
    if component not in loaded.data:
        return
    config = loaded.data[component]
    datasets = config.get("datasets")
    if not isinstance(datasets, Mapping):
        _add_type_error(report, component, loaded, ("datasets",), "must be a mapping")
        return
    missing = set(DEFAULT_SOURCE_NAMES) - set(datasets)
    if missing:
        report.issues.append(ConfigurationIssue("error", loaded.files[component], "datasets", f"missing dataset categories: {', '.join(sorted(missing))}"))

    for dataset_name, dataset in datasets.items():
        if not isinstance(dataset, Mapping):
            _add_type_error(report, component, loaded, ("datasets", str(dataset_name)), "must be a mapping")
            continue
        source_key = dataset.get("source_key")
        if source_key != dataset_name:
            report.issues.append(ConfigurationIssue("error", loaded.files[component], f"datasets.{dataset_name}.source_key", f"must equal dataset name {dataset_name!r}"))

        # A source with only source_key is an intentional deferred definition.
        if dataset_name in DEFERRED_SOURCES and set(dataset) <= {"source_key"}:
            report.issues.append(ConfigurationIssue("warning", loaded.files[component], f"datasets.{dataset_name}", "deferred until its ingest and preprocessing code is developed"))
            continue
        for field_name, expected in (("file_template", "string"), ("variables", "non-empty list"), ("coordinate_names", "mapping"), ("time", "mapping"), ("regridding", "mapping")):
            _add_required(report, component, loaded, ("datasets", str(dataset_name), field_name), expected)
        storage = dataset.get("storage")
        if storage is not None:
            if not isinstance(storage, Mapping):
                _add_type_error(report, component, loaded, ("datasets", str(dataset_name), "storage"), "must be a mapping")
            else:
                if storage.get("partition") not in {"daily", "monthly", "yearly"}:
                    _add_type_error(report, component, loaded, ("datasets", str(dataset_name), "storage.partition"), "must be daily, monthly, or yearly")
                if storage.get("format") not in {"csv", "netcdf"}:
                    _add_type_error(report, component, loaded, ("datasets", str(dataset_name), "storage.format"), "must be csv or netcdf")
        access = dataset.get("access")
        if access is not None and not isinstance(access, Mapping):
            _add_type_error(report, component, loaded, ("datasets", str(dataset_name), "access"), "must be a mapping")


def _validate_source_consistency(loaded: _LoadedConfiguration, report: ConfigurationReport) -> None:
    """Ensure dataset, filepath, and forecast source names do not conflict."""

    filepaths = loaded.data.get("filepaths", {}).get("data_sources", {})
    input_datasets = loaded.data.get("input_data", {}).get("datasets", {})
    forecast_inputs = loaded.data.get("aqforecast", {}).get("inputs", {})
    if not isinstance(filepaths, Mapping) or not isinstance(input_datasets, Mapping):
        return

    filepath_names = set(filepaths)
    dataset_names = set(input_datasets)
    if filepath_names != dataset_names:
        missing = sorted(filepath_names - dataset_names)
        extra = sorted(dataset_names - filepath_names)
        details = []
        if missing:
            details.append(f"missing input datasets: {', '.join(missing)}")
        if extra:
            details.append(f"missing filepath sources: {', '.join(extra)}")
        report.issues.append(
            ConfigurationIssue(
                "error",
                loaded.files.get("input_data"),
                "datasets",
                "; ".join(details),
            )
        )

    if isinstance(forecast_inputs, Mapping):
        unknown_forecast_sources = set(forecast_inputs) - filepath_names
        if unknown_forecast_sources:
            report.issues.append(
                ConfigurationIssue(
                    "error",
                    loaded.files.get("aqforecast"),
                    "inputs",
                    f"unknown forecast input sources: {', '.join(sorted(unknown_forecast_sources))}",
                )
            )


def _validate_aqforecast(loaded: _LoadedConfiguration, report: ConfigurationReport) -> None:
    component = "aqforecast"
    if component not in loaded.data:
        return
    config = loaded.data[component]
    for path, expected in (
        (("inputs",), "mapping"),
        (("forecast", "lead_times_hours"), "non-empty list"),
        (("forecast", "output_variables"), "non-empty list"),
        (("forecast", "confidence_levels"), "non-empty list"),
        (("feature_engineering", "input_lags_hours"), "mapping"),
        (("feature_engineering", "additional_features"), "list"),
    ):
        _add_required(report, component, loaded, path, expected)
    inputs = config.get("inputs")
    if isinstance(inputs, Mapping):
        for source_name, source_settings in inputs.items():
            if not isinstance(source_settings, Mapping) or not isinstance(source_settings.get("enabled"), bool):
                _add_type_error(report, component, loaded, ("inputs", str(source_name), "enabled"), "must be boolean")


def _validate_deepsensor(loaded: _LoadedConfiguration, report: ConfigurationReport) -> None:
    component = "deepsensor"
    if component not in loaded.data:
        return
    for path, expected in (
        (("model", "architecture"), "string"),
        (("model", "unet_channels"), "non-empty list"),
        (("data_processor", "coordinate_names"), "non-empty list"),
        (("data_processor", "normalization_methods"), "mapping"),
        (("task_loader", "context_sampling"), "string"),
        (("task_loader", "target_sampling"), "string"),
        (("training", "learning_rate"), "positive number"),
        (("training", "maximum_epochs"), "positive integer"),
    ):
        _add_required(report, component, loaded, path, expected)
    if "retrain_model" in loaded.data[component].get("training", {}):
        report.issues.append(ConfigurationIssue("error", loaded.files[component], "training.retrain_model", "setting has been removed and should not be specified"))


def _validate_validation(loaded: _LoadedConfiguration, report: ConfigurationReport) -> None:
    component = "validation"
    if component not in loaded.data:
        return
    for path, expected in (
        (("cross_validation",), "mapping"),
        (("baseline_models",), "non-empty list"),
        (("metrics",), "non-empty list"),
        (("stratifications",), "list"),
        (("plots",), "non-empty list"),
    ):
        _add_required(report, component, loaded, path, expected)


def _validate_types(loaded: _LoadedConfiguration, report: ConfigurationReport) -> None:
    """Perform common list/mapping checks for present values."""

    checks = {
        "aqforecast": [("forecast", "lead_times_hours"), ("forecast", "output_variables"), ("forecast", "confidence_levels")],
        "validation": [("baseline_models",), ("metrics",), ("plots",)],
    }
    for component, paths in checks.items():
        config = loaded.data.get(component, {})
        for path in paths:
            value = _get(config, path)
            if value is not None and not isinstance(value, list):
                _add_type_error(report, component, loaded, path, "must be a list")


def _validate(
    loaded: _LoadedConfiguration,
    check_paths: bool = False,
    *,
    require_credentials: bool = False,
) -> ConfigurationReport:
    report = ConfigurationReport(loaded.root_file)
    _validate_master(loaded, report)
    _validate_region(loaded, report)
    _validate_credentials(loaded, report, require_credentials=require_credentials)
    _validate_filepaths(loaded, report, check_paths)
    _validate_input_data(loaded, report)
    _validate_source_consistency(loaded, report)
    _validate_aqforecast(loaded, report)
    _validate_deepsensor(loaded, report)
    _validate_validation(loaded, report)
    _validate_types(loaded, report)
    return report


def _set_value(mapping: Dict[str, Any], path: Sequence[str], value: Any) -> None:
    current = mapping
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = value


def _parse_response(response: str, expected_type: Optional[str]) -> Any:
    try:
        value = yaml.safe_load(response)
    except yaml.YAMLError as exc:
        raise ValueError(f"not valid YAML syntax: {exc}") from exc
    if expected_type in {"string", "path", "path template", "IANA timezone string"}:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("enter a non-empty string")
    elif expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("enter an integer")
    elif expected_type == "positive integer":
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError("enter a positive integer")
    elif expected_type == "positive number":
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise ValueError("enter a positive number")
    elif expected_type in {"list", "non-empty list", "two-number list"}:
        if not isinstance(value, list) or (expected_type == "non-empty list" and not value):
            raise ValueError("enter a YAML list")
        if expected_type == "two-number list" and (len(value) != 2 or not all(isinstance(item, (int, float)) for item in value)):
            raise ValueError("enter a YAML list containing two numbers")
    elif expected_type in {"mapping", "non-empty mapping"}:
        if not isinstance(value, dict) or (expected_type == "non-empty mapping" and not value):
            raise ValueError("enter a YAML mapping")
    return value


def _prompt_for_issue(
    issue: ConfigurationIssue,
    loaded: _LoadedConfiguration,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> bool:
    if not issue.fixable or issue.file is None:
        return False
    component = next((name for name, path in loaded.files.items() if path == issue.file), None)
    if component is None:
        return False
    path = tuple(issue.setting.split("."))
    prompt = f"Enter {issue.setting} ({issue.expected_type or 'value'})"
    if issue.secret:
        response = getpass.getpass(f"{prompt}: ")
    else:
        response = input_fn(f"{prompt}: ")
    try:
        value = _parse_response(response, issue.expected_type)
    except ValueError as exc:
        output_fn(f"Invalid value: {exc}")
        return False
    _set_value(loaded.data[component], path, value)
    return True


def _write_yaml(path: Path, data: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(data, stream, sort_keys=False, default_flow_style=False)


def check_configuration(
    config_path: Union[str, Path],
    *,
    mode: str = "check",
    check_paths: bool = False,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    max_interactive_rounds: int = 10,
    require_credentials: Optional[bool] = None,
) -> ConfigurationReport:
    """Check a master configuration and all files it references.

    Parameters
    ----------
    config_path:
        Path to a master configuration such as ``config/default_config.yaml``.
    mode:
        ``"check"`` performs a read-only validation. ``"interactive"``
        prompts for fixable missing values and writes accepted changes.
    check_paths:
        Also require configured input/output root directories to exist.
    input_fn, output_fn:
        Injectable console functions, useful for tests or a larger setup UI.
    max_interactive_rounds:
        Maximum number of validation/prompt rounds in interactive mode.
    require_credentials:
        Require the local credentials file and its required fields. By default,
        this is false in checking mode, because credentials are intentionally
        excluded from version control, and true in interactive mode.

    Returns
    -------
    ConfigurationReport
        Structured findings. ``report.is_valid`` is true when no errors remain.
    """

    if mode not in {"check", "interactive"}:
        raise ValueError("mode must be 'check' or 'interactive'")
    if require_credentials is None:
        require_credentials = mode == "interactive"
    root_file = Path(config_path).expanduser().resolve()
    report = ConfigurationReport(root_file)
    loaded = _load_referenced_files(
        root_file,
        report,
        allow_missing_credentials=not require_credentials,
    )
    report.issues.extend(_validate(loaded, check_paths, require_credentials=require_credentials).issues)

    if mode == "interactive":
        changed: set[Path] = set()
        for _ in range(max_interactive_rounds):
            fixable = [issue for issue in report.errors if issue.fixable]
            if not fixable:
                break
            made_change = False
            for issue in fixable:
                if _prompt_for_issue(issue, loaded, input_fn, output_fn):
                    component = next((name for name, path in loaded.files.items() if path == issue.file), None)
                    if component is not None:
                        _write_yaml(loaded.files[component], loaded.data[component])
                        changed.add(loaded.files[component])
                        made_change = True
            if not made_change:
                break
            refreshed = _load_referenced_files(
                root_file,
                ConfigurationReport(root_file),
                allow_missing_credentials=not require_credentials,
            )
            loaded = refreshed
            report = _validate(loaded, check_paths, require_credentials=require_credentials)
        report.changed_files = sorted(changed)

    return report


def _resolve_known_templates(value: Any, context: Mapping[str, Any]) -> Any:
    """Replace known ``{field}`` templates while preserving unknown ones."""

    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(context[key]) if key in context else match.group(0)

        return PATH_TEMPLATE_PATTERN.sub(replace, value)
    if isinstance(value, dict):
        return {key: _resolve_known_templates(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_known_templates(item, context) for item in value]
    return value


def _resolve_filepaths(filepaths: Mapping[str, Any], context: Mapping[str, Any]) -> Dict[str, Any]:
    """Resolve filepath templates in dependency order."""

    resolved = copy.deepcopy(dict(filepaths))
    roots = resolved.get("roots", {})
    if isinstance(roots, dict):
        roots = _resolve_known_templates(roots, context)
        resolved["roots"] = roots

    filepath_context = dict(context)
    if isinstance(roots, Mapping):
        filepath_context.update(roots)

    working = resolved.get("working", {})
    if isinstance(working, dict):
        resolved_working: Dict[str, Any] = {}
        for key, value in working.items():
            resolved_value = _resolve_known_templates(value, filepath_context)
            resolved_working[key] = resolved_value
            filepath_context[key] = resolved_value
        resolved["working"] = resolved_working

    sources = resolved.get("data_sources", {})
    if isinstance(sources, dict):
        resolved["data_sources"] = _resolve_known_templates(sources, filepath_context)
    return resolved


def _path_warnings(filepaths: Mapping[str, Any]) -> List[str]:
    """Return warnings for resolved paths that do not currently exist."""

    warnings: List[str] = []
    for section_name in ("roots", "working", "data_sources"):
        section = filepaths.get(section_name, {})
        if not isinstance(section, Mapping):
            continue
        for path_name, value in section.items():
            if not isinstance(value, str) or PATH_TEMPLATE_PATTERN.search(value):
                continue
            if not Path(value).exists():
                warnings.append(f"filepath {section_name}.{path_name} does not exist: {value}")
    return warnings


def load_configuration(
    config_path: Union[str, Path],
    *,
    require_credentials: bool = False,
) -> Dict[str, Any]:
    """Load, validate, merge, and resolve a ChemML configuration.

    The returned dictionary contains the component configurations under their
    component names, plus ``experiment_name``, resolved ``configuration_files``,
    and a ``warnings`` list. Missing credentials and nonexistent configured
    paths produce warnings and do not prevent loading. Structural errors,
    malformed values, missing non-credential references, and conflicting source
    definitions raise :class:`ConfigurationError`.

    Parameters
    ----------
    config_path:
        Master configuration such as ``config/default_config.yaml``.
    require_credentials:
        Require the credentials file and required credential values. Leave this
        false for runs that do not use credential-dependent data sources.
    """

    root_file = Path(config_path).expanduser().resolve()
    report = ConfigurationReport(root_file)
    loaded = _load_referenced_files(
        root_file,
        report,
        allow_missing_credentials=not require_credentials,
    )
    report.issues.extend(
        _validate(loaded, require_credentials=require_credentials).issues
    )
    if report.errors:
        raise ConfigurationError(report)

    default = loaded.data.get("default", {})
    region = copy.deepcopy(loaded.data.get("region", {}))
    region_code = region.get("region_code")
    experiment_code = default.get("experiment_code")
    template = default.get("experiment_name_template")
    context = {
        "region_code": region_code,
        "experiment_code": experiment_code,
    }
    experiment_name = _resolve_known_templates(template, context)
    context["experiment_name"] = experiment_name

    filepaths = _resolve_filepaths(loaded.data.get("filepaths", {}), context)
    resolved_components: Dict[str, Any] = {}
    for component, component_data in loaded.data.items():
        if component == "default":
            continue
        if component == "filepaths":
            resolved_components[component] = filepaths
        else:
            resolved_components[component] = _resolve_known_templates(component_data, context)

    warnings = [
        f"{issue.file}: {issue.setting} - {issue.message}"
        for issue in report.warnings
    ]
    warnings.extend(_path_warnings(filepaths))
    resolved_components.update(
        {
            "config_version": default.get("config_version"),
            "experiment_code": experiment_code,
            "experiment_name": experiment_name,
            "configuration_files": {
                component: str(path) for component, path in loaded.files.items() if component != "default"
            },
            "warnings": warnings,
        }
    )
    return resolved_components


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="master YAML configuration file")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="read-only checking mode (default)")
    group.add_argument("--interactive", action="store_true", help="prompt for fixable missing values")
    parser.add_argument("--check-paths", action="store_true", help="require input/output root paths to exist")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    mode = "interactive" if args.interactive else "check"
    report = check_configuration(args.config, mode=mode, check_paths=args.check_paths)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(report.format())
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
