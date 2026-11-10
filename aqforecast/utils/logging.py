"""Logging utilities for ChemML workflows.

The utility configures console and file logging from a resolved configuration
dictionary returned by ``load_configuration()``. It intentionally does not
create log directories; directory creation belongs to the future setup
utility.
"""

from __future__ import annotations

import logging as standard_logging
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Union


DEFAULT_LOG_FILENAME = "aqforecast.log"
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
HANDLER_MARKER = "_chemml_logging_handler"
REDACTION_TEXT = "[REDACTED]"


def _get_nested(mapping: Mapping[str, Any], *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _logging_level(level: Union[str, int]) -> int:
    if isinstance(level, int):
        return level
    if not isinstance(level, str):
        raise TypeError("logging level must be a string or integer")
    normalized = level.upper()
    if normalized not in standard_logging._nameToLevel:
        raise ValueError(f"unknown logging level: {level}")
    return standard_logging._nameToLevel[normalized]


def _credential_values(configuration: Mapping[str, Any]) -> Iterable[str]:
    credentials = configuration.get("credentials", {})
    if not isinstance(credentials, Mapping):
        return []

    values = []
    for section in credentials.values():
        if not isinstance(section, Mapping):
            continue
        for value in section.values():
            if isinstance(value, str) and value:
                values.append(value)
    return values


class _RedactionFilter(standard_logging.Filter):
    """Redact configured credential values from log messages."""

    def __init__(self, sensitive_values: Iterable[str]) -> None:
        super().__init__()
        self.sensitive_values = tuple(
            value for value in sensitive_values if len(value) >= 4
        )

    def filter(self, record: standard_logging.LogRecord) -> bool:
        message = record.getMessage()
        for value in self.sensitive_values:
            message = message.replace(value, REDACTION_TEXT)
        record.msg = message
        record.args = ()
        return True


def get_logger(name: str = "aqforecast") -> standard_logging.Logger:
    """Return a named ChemML logger without configuring handlers."""

    return standard_logging.getLogger(name)


def configure_logging(
    configuration: Mapping[str, Any],
    *,
    logger_name: str = "aqforecast",
    level: Union[str, int] = "INFO",
    console: bool = True,
    file_logging: bool = True,
    log_filename: str = DEFAULT_LOG_FILENAME,
    create_directory: bool = False,
    reset_handlers: bool = True,
) -> standard_logging.Logger:
    """Configure and return the logger used by a ChemML workflow.

    Parameters
    ----------
    configuration:
        Resolved dictionary returned by ``load_configuration()``. The file
        destination is read from ``filepaths.working.logs_directory``.
    logger_name:
        Logger name used by the workflow.
    level:
        Standard logging level name or numeric logging level.
    console:
        Add a stream handler writing to stderr.
    file_logging:
        Add a file handler under the configured ``logs_directory``.
    log_filename:
        Log filename. Only the filename component is used.
    create_directory:
        Create ``logs_directory`` if absent. Defaults to false because output
        directory creation belongs to the setup utility.
    reset_handlers:
        Remove handlers previously installed by this utility for this logger.

    Raises
    ------
    KeyError
        If file logging is requested but ``logs_directory`` is not configured.
    FileNotFoundError
        If file logging is requested and the directory does not exist.
    ValueError, TypeError
        If the logging level is invalid.
    """

    logger = get_logger(logger_name)
    logger.setLevel(_logging_level(level))
    logger.propagate = False

    if reset_handlers:
        for handler in list(logger.handlers):
            if getattr(handler, HANDLER_MARKER, False):
                logger.removeHandler(handler)
                handler.close()

    sensitive_values = _credential_values(configuration)
    formatter = standard_logging.Formatter(DEFAULT_LOG_FORMAT)

    def install_handler(handler: standard_logging.Handler) -> None:
        setattr(handler, HANDLER_MARKER, True)
        handler.setLevel(_logging_level(level))
        handler.setFormatter(formatter)
        handler.addFilter(_RedactionFilter(sensitive_values))
        logger.addHandler(handler)

    if console:
        install_handler(standard_logging.StreamHandler())

    if file_logging:
        logs_directory = _get_nested(configuration, "filepaths", "working", "logs_directory")
        if not isinstance(logs_directory, str) or not logs_directory:
            raise KeyError("configuration does not specify filepaths.working.logs_directory")
        log_directory_path = Path(logs_directory).expanduser()
        if create_directory:
            log_directory_path.mkdir(parents=True, exist_ok=True)
        if not log_directory_path.is_dir():
            raise FileNotFoundError(f"log directory does not exist: {log_directory_path}")
        log_path = log_directory_path / Path(log_filename).name
        install_handler(standard_logging.FileHandler(log_path, encoding="utf-8"))

    return logger


__all__ = ["configure_logging", "get_logger"]
