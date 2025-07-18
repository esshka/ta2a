"""
System failure error classifications for unrecoverable errors.

These exceptions represent system-level failures that typically require
intervention or system restart to resolve.
"""

from typing import Optional, Dict, Any


class SystemFailureError(Exception):
    """Base class for unrecoverable system failures."""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.context = context or {}
        self.recoverable = False


class MetricsCalculationError(SystemFailureError):
    """Critical error in metrics calculation that prevents evaluation."""
    
    def __init__(self, message: str, metric_name: Optional[str] = None, 
                 calculation_input: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.metric_name = metric_name
        self.calculation_input = calculation_input


class StateTransitionError(SystemFailureError):
    """Invalid state transition that corrupts the state machine."""
    
    def __init__(self, message: str, current_state: Optional[str] = None, 
                 attempted_transition: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.current_state = current_state
        self.attempted_transition = attempted_transition


class PersistenceError(SystemFailureError):
    """Database or file system persistence failures."""
    
    def __init__(self, message: str, operation: Optional[str] = None, 
                 target: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.operation = operation
        self.target = target


class DeliveryError(SystemFailureError):
    """Signal delivery system failures."""
    
    def __init__(self, message: str, delivery_method: Optional[str] = None, 
                 signal_id: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.delivery_method = delivery_method
        self.signal_id = signal_id