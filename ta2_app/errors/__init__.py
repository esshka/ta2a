"""
Enhanced error classification system for comprehensive error handling.

This module provides structured exception hierarchy for different types of errors
encountered during market data processing and trading algorithm evaluation.
"""

from .data_quality import (
    DataQualityError,
    TemporalDataError,
    PartialDataError,
    MissingDataError,
    MalformedDataError,
    InsufficientDataError,
)
from .system_failures import (
    SystemFailureError,
    MetricsCalculationError,
    StateTransitionError,
    PersistenceError,
    DeliveryError,
)
from .recovery import (
    RecoverableError,
    UnrecoverableError,
    GracefulDegradationError,
)

__all__ = [
    # Data Quality Errors
    "DataQualityError",
    "TemporalDataError", 
    "PartialDataError",
    "MissingDataError",
    "MalformedDataError",
    "InsufficientDataError",
    # System Failures
    "SystemFailureError",
    "MetricsCalculationError",
    "StateTransitionError",
    "PersistenceError",
    "DeliveryError",
    # Recovery Categories
    "RecoverableError",
    "UnrecoverableError",
    "GracefulDegradationError",
]