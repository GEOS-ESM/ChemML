"""Contracts for forecast validation implementations."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from aqforecast.contracts import ForecastResult, ValidationResult


class ForecastValidator(Protocol):
    """Compare forecast output with observations and calculate metrics."""

    def evaluate(
        self,
        forecast: ForecastResult,
        observations: Any,
        configuration: Mapping[str, Any],
    ) -> ValidationResult:
        """Calculate configured metrics and optionally prepare plots."""


__all__ = ["ForecastValidator"]
