"""Shared data contracts for the AQ-forecast workflow.

These lightweight containers define the boundaries between workflow stages.
Stage implementations may attach richer project-specific objects in the
``data`` and ``metadata`` mappings, but should preserve the named fields so
that stages remain composable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Sequence


@dataclass
class DataRequest:
    """Describe a request for one configured input data source."""

    source_key: str
    region_code: str
    variables: Sequence[str] = field(default_factory=tuple)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetBundle:
    """Data returned by acquisition or preprocessing for one source."""

    source_key: str
    data: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ForecastRequest:
    """Inputs and options required to produce a forecast."""

    inputs: Mapping[str, DatasetBundle]
    variables: Sequence[str] = field(default_factory=tuple)
    lead_times: Sequence[int] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ForecastResult:
    """Forecast values and metadata produced by a forecasting model."""

    predictions: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Metrics and optional plots produced by validation."""

    metrics: Dict[str, float] = field(default_factory=dict)
    plots: Sequence[Any] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowContext:
    """Shared state passed between stages of a future workflow."""

    configuration: Mapping[str, Any]
    datasets: Dict[str, DatasetBundle] = field(default_factory=dict)
    features: Dict[str, Any] = field(default_factory=dict)
    model: Any = None
    forecast: Optional[ForecastResult] = None
    validation: Optional[ValidationResult] = None
    warnings: list[str] = field(default_factory=list)


__all__ = [
    "DataRequest",
    "DatasetBundle",
    "ForecastRequest",
    "ForecastResult",
    "ValidationResult",
    "WorkflowContext",
]
