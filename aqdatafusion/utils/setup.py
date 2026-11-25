"""First-time setup for a local ChemML configuration.

The setup flow is intentionally small and composable. It copies missing
configuration files, prompts for machine-specific paths, delegates YAML value
validation to :func:`check_configuration`, collects credentials through
``manage_credentials``, creates the configured directories, and finishes with
one strict configuration check.
"""

from __future__ import annotations

import argparse
import getpass
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

import yaml

from aqdatafusion.config_management.configuration import (
    ConfigurationReport,
    check_configuration,
    load_configuration,
)
from aqdatafusion.config_management.credentials import manage_credentials
from aqdatafusion.utils.plotting import prepare_cartopy_basemap


InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]


def _repository_config_directory() -> Path:
    """Return the configuration directory shipped with this repository."""

    return Path(__file__).resolve().parents[2] / "config"


def _copy_missing_configuration_files(
    source_directory: Path,
    target_directory: Path,
    configuration_filename: str = "default_config.yaml",
) -> List[Path]:
    """Copy shipped configuration files that are absent from the target.

    Existing files are preserved so rerunning setup cannot overwrite local
    settings. A real local credentials file is never copied from a source
    tree, even if one happens to exist there.
    """

    copied: List[Path] = []
    for source_path in sorted(source_directory.rglob("*.yaml")):
        if source_path.name == "credentials.yaml":
            continue
        relative_path = source_path.relative_to(source_directory)
        if source_path.name == "default_config.yaml":
            relative_path = Path(configuration_filename)
        target_path = target_directory / relative_path
        if target_path.exists():
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        copied.append(target_path)
    return copied


def _configuration_filename(value: Union[str, Path]) -> str:
    """Validate and normalize the master configuration filename."""

    path = Path(value).expanduser()
    if path.is_absolute() or path.name != str(path) or path.name in {"", ".", ".."}:
        raise ValueError(
            "configuration_filename must be a filename within config_directory"
        )
    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("configuration_filename must have a .yaml or .yml suffix")
    return path.name


def _prompt_for_path(
    input_fn: InputFunction,
    output_fn: OutputFunction,
    setting: str,
) -> str:
    """Prompt for a non-empty filesystem path."""

    while True:
        value = input_fn(f"Enter {setting} path: ").strip()
        if value:
            return str(Path(value).expanduser())
        output_fn("A path is required.")


def _set_filepath_roots(
    config_path: Path,
    input_path: str,
    output_path: str,
) -> None:
    """Write the user-selected input and output roots to filepaths.yaml."""

    with config_path.open(encoding="utf-8") as stream:
        configuration = yaml.safe_load(stream) or {}
    if not isinstance(configuration, dict):
        raise ValueError(f"filepath configuration must be a YAML mapping: {config_path}")
    roots = configuration.setdefault("roots", {})
    if not isinstance(roots, dict):
        raise ValueError(f"filepath configuration roots must be a mapping: {config_path}")
    roots["input"] = input_path
    roots["output"] = output_path
    with config_path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(configuration, stream, sort_keys=False, default_flow_style=False)


def _existing_filepath_root(
    configuration: Mapping[str, Any], name: str
) -> Optional[str]:
    """Return an existing configured root when it is a usable directory."""

    filepaths = configuration.get("filepaths", {})
    roots = filepaths.get("roots", {}) if isinstance(filepaths, Mapping) else {}
    value = roots.get(name) if isinstance(roots, Mapping) else None
    if isinstance(value, str) and value.strip() and Path(value).expanduser().is_dir():
        return str(Path(value).expanduser())
    return None


def _configured_paths(configuration: Mapping[str, Any]) -> List[Path]:
    """Collect resolved roots, working directories, and source directories."""

    filepaths = configuration.get("filepaths", {})
    if not isinstance(filepaths, Mapping):
        return []
    paths: List[Path] = []
    for section_name in ("roots", "working", "data_sources"):
        section = filepaths.get(section_name, {})
        if not isinstance(section, Mapping):
            continue
        for value in section.values():
            if isinstance(value, str) and value.strip() and "{" not in value:
                paths.append(Path(value).expanduser())
    return paths


def setup_aqdatafusion(
    config_directory: Union[str, Path] = "config",
    *,
    configuration_filename: Union[str, Path] = "default_config.yaml",
    source_config_directory: Optional[Union[str, Path]] = None,
    verify_remote: bool = False,
    prompt_optional_credentials: bool = False,
    download_basemap: bool = True,
    input_fn: InputFunction = input,
    secret_input_fn: Optional[InputFunction] = None,
    output_fn: OutputFunction = print,
) -> Dict[str, Any]:
    """Walk a new user through first-time ChemML setup.

    Parameters
    ----------
    config_directory:
        Directory containing the user's master configuration and component
        files. Missing configuration files are copied into this directory.
    configuration_filename:
        Filename for the master configuration copied and configured by setup.
        The default is ``default_config.yaml``; use a different YAML filename
        to maintain multiple regional or experiment-specific configurations in
        one configuration directory.
    source_config_directory:
        Directory containing the shipped configuration files. By default this
        is the repository's ``config`` directory.
    verify_remote:
        Request optional remote credential checks.
    prompt_optional_credentials:
        Also prompt for optional OpenAQ and AirNow credentials.
    download_basemap:
        Attempt to cache the standard Cartopy Natural Earth layers during
        setup. Download failures are warnings and do not invalidate setup.

    Returns
    -------
    dict
        A status dictionary containing the final ``ConfigurationReport`` and
        setup details. ``status`` is ``"configured"`` only when the final
        strict check has no errors.
    """

    target_directory = Path(config_directory).expanduser().resolve()
    source_directory = Path(source_config_directory or _repository_config_directory()).expanduser().resolve()
    master_filename = _configuration_filename(configuration_filename)
    if not source_directory.is_dir():
        raise FileNotFoundError(f"source configuration directory does not exist: {source_directory}")
    target_directory.mkdir(parents=True, exist_ok=True)
    master_path = target_directory / master_filename
    filepaths_path = target_directory / "filepaths" / "filepaths.yaml"
    reuse_existing_paths = master_path.is_file() and filepaths_path.is_file()

    copied_files = _copy_missing_configuration_files(
        source_directory, target_directory, master_filename
    )
    config_path = target_directory / master_filename
    if not config_path.is_file():
        raise FileNotFoundError(f"master configuration was not installed: {config_path}")
    if not filepaths_path.is_file():
        raise FileNotFoundError(f"filepath configuration was not installed: {filepaths_path}")

    output_fn("ChemML first-time setup")
    existing_configuration = (
        load_configuration(config_path, require_credentials=False)
        if reuse_existing_paths
        else {}
    )
    input_path = _existing_filepath_root(existing_configuration, "input")
    if input_path is None:
        input_path = _prompt_for_path(input_fn, output_fn, "input data root")
    else:
        output_fn(f"Reusing existing input data root: {input_path}")
    output_path = _existing_filepath_root(existing_configuration, "output")
    if output_path is None:
        output_path = _prompt_for_path(input_fn, output_fn, "output root")
    else:
        output_fn(f"Reusing existing output root: {output_path}")
    _set_filepath_roots(filepaths_path, input_path, output_path)

    interactive_report = check_configuration(
        config_path,
        mode="interactive",
        input_fn=input_fn,
        output_fn=output_fn,
        require_credentials=False,
    )
    if not interactive_report.is_valid:
        return {
            "status": "configuration_failed",
            "config_path": config_path,
            "copied_files": copied_files,
            "created_directories": [],
            "configuration_report": interactive_report,
            "credentials": None,
        }

    credential_result = manage_credentials(
        config_path,
        verify_remote=verify_remote,
        prompt_optional=prompt_optional_credentials,
        input_fn=input_fn,
        secret_input_fn=secret_input_fn or getpass.getpass,
        output_fn=output_fn,
    )
    if credential_result.get("status") == "invalid":
        return {
            "status": "credentials_failed",
            "config_path": config_path,
            "copied_files": copied_files,
            "created_directories": [],
            "configuration_report": interactive_report,
            "credentials": credential_result,
        }

    configuration = load_configuration(config_path, require_credentials=True)
    created_directories: List[Path] = []
    for directory in _configured_paths(configuration):
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created_directories.append(directory)

    basemap_result = prepare_cartopy_basemap(
        configuration["filepaths"]["data_sources"]["cartopy_cache"],
        download=download_basemap,
        output_fn=output_fn,
    )

    final_report = check_configuration(
        config_path,
        mode="check",
        check_paths=True,
        require_credentials=True,
    )
    return {
        "status": "configured" if final_report.is_valid else "configuration_failed",
        "config_path": config_path,
        "copied_files": copied_files,
        "created_directories": created_directories,
        "configuration_report": final_report,
        "credentials": credential_result,
        "basemap": basemap_result,
    }


def main() -> int:
    """Run setup from the command line."""

    parser = argparse.ArgumentParser(description="Set up a local ChemML configuration")
    parser.add_argument("--config-directory", default="config")
    parser.add_argument(
        "--configuration-filename",
        default="default_config.yaml",
        help="master configuration filename to create (default: default_config.yaml)",
    )
    parser.add_argument("--verify-remote", action="store_true")
    parser.add_argument("--prompt-optional-credentials", action="store_true")
    parser.add_argument("--no-download-basemap", action="store_true")
    args = parser.parse_args()
    result = setup_aqdatafusion(
        args.config_directory,
        configuration_filename=args.configuration_filename,
        verify_remote=args.verify_remote,
        prompt_optional_credentials=args.prompt_optional_credentials,
        download_basemap=not args.no_download_basemap,
    )
    report: ConfigurationReport = result["configuration_report"]
    print(report.format())
    return 0 if result["status"] == "configured" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["setup_aqdatafusion"]
