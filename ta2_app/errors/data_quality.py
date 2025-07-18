"""
Data quality error classifications for market data processing.

These exceptions help categorize different types of data quality issues
that can occur during market data ingestion and processing.
"""

from typing import Optional, Dict, Any


class DataQualityError(Exception):
    """Base class for data quality issues that can be handled gracefully."""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.context = context or {}
        self.recoverable = True


class TemporalDataError(DataQualityError):
    """Timestamp or sequencing issues in market data."""
    
    def __init__(self, message: str, timestamp: Optional[int] = None, 
                 expected_timestamp: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.timestamp = timestamp
        self.expected_timestamp = expected_timestamp


class PartialDataError(DataQualityError):
    """Missing but recoverable data fields."""
    
    def __init__(self, message: str, missing_fields: Optional[list] = None, 
                 available_fields: Optional[list] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.missing_fields = missing_fields or []
        self.available_fields = available_fields or []


class MissingDataError(DataQualityError):
    """Required data is completely missing."""
    
    def __init__(self, message: str, data_type: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.data_type = data_type


class MalformedDataError(DataQualityError):
    """Data exists but is in incorrect format."""
    
    def __init__(self, message: str, raw_data: Optional[str] = None, 
                 expected_format: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.raw_data = raw_data
        self.expected_format = expected_format


class InsufficientDataError(DataQualityError):
    """Not enough historical data for calculations."""
    
    def __init__(self, message: str, required_count: Optional[int] = None, 
                 available_count: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.required_count = required_count
        self.available_count = available_count