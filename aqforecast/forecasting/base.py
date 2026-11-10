"""Contracts for forecasting-model implementations."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from aqforecast.contracts import ForecastRequest, ForecastResult


class ForecastModel(Protocol):
    """Model interface shared by training and inference workflows."""

    def fit(
        self,
        request: ForecastRequest,
        configuration: Mapping[str, Any],
    ) -> "ForecastModel":
        """Train or update the model and return the fitted model."""

    def predict(
        self,
        request: ForecastRequest,
        configuration: Mapping[str, Any],
    ) -> ForecastResult:
        """Generate forecasts for the requested inputs and lead times."""


__all__ = ["ForecastModel"]
