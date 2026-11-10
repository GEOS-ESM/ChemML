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
        configuration = load_configuration(
            config_path,
            require_credentials=require_credentials,
        )
    except ConfigurationError as error:
        return {
            "status": "configuration_failed",
            "message": "The AQ-forecast configuration could not be loaded.",
            "configuration": None,
            "warnings": [],
            "errors": [issue.as_dict() for issue in error.report.errors],
        }

    return {
        "status": "configuration_loaded",
        "message": (
            "Configuration loaded successfully. No other AQ-forecast "
            "workflow functions have been implemented yet."
        ),
        "configuration": configuration,
        "warnings": configuration.get("warnings", []),
    }


__all__ = ["run_aqforecast"]
