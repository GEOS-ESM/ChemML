"""High-level entry point for the ChemML air-quality data-fusion workflow.

The workflow stages will be added as the data-ingest, preprocessing, model,
forecasting, and validation systems are implemented. For now, the runner
loads and validates the selected configuration and returns a status summary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

from aqdatafusion.config_management.configuration import (
    ConfigurationError,
    load_configuration,
)
from aqdatafusion.config_management.credentials import manage_credentials


def run_aqdatafusion(
    config_path: Union[str, Path] = "config/default_config.yaml",
    *,
    require_credentials: bool = False,
    mode: str = "forecast",
    start_time: Optional[Any] = None,
    end_time: Optional[Any] = None,
    source_keys: Optional[Sequence[str]] = None,
    conflict_policy: str = "fill_missing",
    override: bool = False,
) -> Dict[str, Any]:
    """Run the currently implemented portion of the AQ-data-fusion workflow.

    Parameters
    ----------
    config_path:
        Master configuration file to load.
    require_credentials:
        Require the local credentials file and required credential values while
        loading the configuration. Leave false for runs that do not need them.
    mode:
        ``"forecast"`` preserves the configuration-only runner; use
        ``"database_update"`` for an explicit interval or
        ``"incremental_database_update"`` for the configured rolling window.
    start_time, end_time, source_keys, conflict_policy, override:
        Options passed to database-update mode.

    Returns
    -------
    dict
        A status summary containing ``status``, ``message``, ``configuration``,
        and ``warnings``. Configuration errors are returned in the dictionary
        rather than raised so callers can handle run status uniformly.
    """

    if mode not in {"forecast", "database_update", "incremental_database_update"}:
        return {
            "status": "invalid_mode",
            "message": f"Unsupported AQ-data-fusion mode: {mode!r}.",
            "configuration": None,
            "warnings": [],
            "errors": [
                "mode must be 'forecast', 'database_update', or "
                "'incremental_database_update'"
            ],
        }
    if mode == "database_update" and (start_time is None or end_time is None):
        return {
            "status": "database_update_failed",
            "message": "Database-update mode requires start_time and end_time.",
            "configuration": None,
            "warnings": [],
            "errors": ["start_time and end_time are required"],
        }

    try:
        # Load first without requiring credentials so that manage_credentials()
        # can locate the credentials file and prompt for missing values.
        configuration = load_configuration(config_path, require_credentials=False)
    except ConfigurationError as error:
        return {
            "status": "configuration_failed",
            "message": "The AQ-data-fusion configuration could not be loaded.",
            "configuration": None,
            "warnings": [],
            "errors": [issue.as_dict() for issue in error.report.errors],
        }

    credential_check = None
    if require_credentials:
        try:
            credential_check = manage_credentials(
                config_path,
                verify_remote=True,
            )
        except (ConfigurationError, OSError, ValueError) as error:
            return {
                "status": "credentials_failed",
                "message": "Credentials could not be collected or verified.",
                "configuration": configuration,
                "warnings": configuration.get("warnings", []),
                "errors": [str(error)],
            }

        if credential_check.get("status") == "invalid":
            return {
                "status": "credentials_failed",
                "message": credential_check.get("message", "Credentials are invalid."),
                "configuration": configuration,
                "warnings": configuration.get("warnings", [])
                + credential_check.get("warnings", []),
                "credentials": credential_check,
                "errors": credential_check.get("errors", []),
            }

        try:
            # Confirm that the saved credentials now satisfy the required
            # credential fields before allowing the run to continue.
            configuration = load_configuration(config_path, require_credentials=True)
        except ConfigurationError as error:
            return {
                "status": "credentials_failed",
                "message": "Saved credentials did not pass configuration validation.",
                "configuration": configuration,
                "warnings": configuration.get("warnings", []),
                "credentials": credential_check,
                "errors": [issue.as_dict() for issue in error.report.errors],
            }

    if mode in {"database_update", "incremental_database_update"}:
        from aqdatafusion.orchestration import run_database_update
        from aqdatafusion.orchestration import run_incremental_database_update

        try:
            if mode == "incremental_database_update":
                report = run_incremental_database_update(
                    configuration,
                    source_keys=source_keys,
                    conflict_policy=conflict_policy,
                    override=override,
                )
            else:
                report = run_database_update(
                    configuration,
                    start_time,
                    end_time,
                    source_keys=source_keys,
                    conflict_policy=conflict_policy,
                    override=override,
                )
        except (OSError, ValueError, RuntimeError) as error:
            return {
                "status": "database_update_failed",
                "message": "The input-data database update failed.",
                "configuration": configuration,
                "warnings": configuration.get("warnings", []),
                "errors": [str(error)],
            }
        failed = [
            key for key, value in report.get("sources", {}).items()
            if value.get("status") == "failed"
        ]
        return {
            "status": "database_update_failed" if failed else "database_updated",
            "message": "Input-data database update completed."
            if not failed
            else "Input-data database update completed with source failures.",
            "configuration": configuration,
            "warnings": configuration.get("warnings", []) + report.get("warnings", []),
            "report": report,
        }

    return {
        "status": "credentials_checked" if require_credentials else "configuration_loaded",
        "message": (
            "Configuration and required credentials loaded successfully. "
            "Other AQ-data-fusion workflow functions have not been implemented yet."
            if require_credentials
            else "Configuration loaded successfully. Other AQ-data-fusion "
            "workflow functions have not been implemented yet."
        ),
        "configuration": configuration,
        "warnings": configuration.get("warnings", [])
        + (credential_check or {}).get("warnings", []),
        **({"credentials": credential_check} if credential_check is not None else {}),
    }


__all__ = ["run_aqdatafusion"]
