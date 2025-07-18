"""
Recovery strategy classifications for error handling.

These mixins help categorize errors by their recovery characteristics
and guide the error handling strategy.
"""

from typing import Optional, Dict, Any


class RecoverableError(Exception):
    """Mixin for errors that can be recovered from automatically."""
    
    def __init__(self, message: str, retry_count: int = 0, 
                 max_retries: int = 3, **kwargs):
        super().__init__(message)
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.recoverable = True


class UnrecoverableError(Exception):
    """Mixin for errors that require human intervention."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message)
        self.recoverable = False


class GracefulDegradationError(Exception):
    """Mixin for errors that allow continued operation with reduced functionality."""
    
    def __init__(self, message: str, degraded_functionality: Optional[str] = None, 
                 fallback_strategy: Optional[str] = None, **kwargs):
        super().__init__(message)
        self.degraded_functionality = degraded_functionality
        self.fallback_strategy = fallback_strategy
        self.allows_degradation = True