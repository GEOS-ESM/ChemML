"""High-level entry point for the ChemML air-quality forecasting workflow.

The workflow stages will be added as the data-ingest, preprocessing, model,
forecasting, and validation systems are implemented. For now, the runner
loads and validates the selected configuration and returns a status summary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

from aqforecast.config_management.configuration import (
    ConfigurationError,
    load_configuration,
)
from aqforecast.config_management.credentials import manage_credentials


def run_aqforecast(
    config_path: Union[str, Path] = "config/default_config.yaml",
    *,
    require_credentials: bool = False,
) -> Dict[str, Any]:
    """Run the currently implemented portion of the AQ-forecast workflow.

    Parameters
    ----------
    config_path:
        Master configuration file to load.
    require_credentials:
        Require the local credentials file and required credential values while
        loading the configuration. Leave false for runs that do not need them.

    Returns
    -------
    dict
        A status summary containing ``status``, ``message``, ``configuration``,
        and ``warnings``. Configuration errors are returned in the dictionary
        rather than raised so callers can handle run status uniformly.
    """

    try:
        # Load first without requiring credentials so that manage_credentials()
        # can locate the credentials file and prompt for missing values.
        configuration = load_configuration(config_path, require_credentials=False)
    except ConfigurationError as error:
        return {
            "status": "configuration_failed",
            "message": "The AQ-forecast configuration could not be loaded.",
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

    return {
        "status": "credentials_checked" if require_credentials else "configuration_loaded",
        "message": (
            "Configuration and required credentials loaded successfully. "
            "No other AQ-forecast workflow functions have been implemented yet."
            if require_credentials
            else "Configuration loaded successfully. No other AQ-forecast "
            "workflow functions have been implemented yet."
        ),
        "configuration": configuration,
        "warnings": configuration.get("warnings", [])
        + (credential_check or {}).get("warnings", []),
        **({"credentials": credential_check} if credential_check is not None else {}),
    }


__all__ = ["run_aqforecast"]
