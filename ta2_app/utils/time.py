"""
Time semantics utilities for market vs wall-clock time handling.

This module provides centralized time handling functions that ensure
market timestamps are authoritative and wall-clock time is only used
for operational purposes like latency monitoring.
"""

from datetime import datetime, timezone
from typing import Optional


def get_market_time(market_ts: Optional[datetime] = None) -> datetime:
    """
    Get the current market time, preferring market timestamp over wall-clock time.

    Args:
        market_ts: Optional market timestamp from data feed

    Returns:
        Market time as UTC datetime, falling back to wall-clock time if unavailable
    """
    if market_ts is not None:
        return market_ts

    # Fallback to wall-clock time when market time unavailable
    return datetime.now(timezone.utc)


def ensure_market_time(market_ts: Optional[datetime], fallback_ts: Optional[datetime] = None) -> datetime:
    """
    Ensure we have a valid market time, with proper fallback hierarchy.

    Args:
        market_ts: Preferred market timestamp from data feed
        fallback_ts: Optional fallback timestamp (e.g., from last known data)

    Returns:
        Valid UTC datetime, prioritizing market time
    """
    if market_ts is not None:
        return market_ts

    if fallback_ts is not None:
        return fallback_ts

    # Last resort: wall-clock time
    return datetime.now(timezone.utc)


def calculate_latency(market_ts: datetime, wall_clock_ts: Optional[datetime] = None) -> float:
    """
    Calculate latency between market timestamp and wall-clock receive time.

    Args:
        market_ts: Market timestamp from data feed
        wall_clock_ts: Wall-clock receive time, defaults to now

    Returns:
        Latency in seconds (positive means market time is older)
    """
    if wall_clock_ts is None:
        wall_clock_ts = datetime.now(timezone.utc)

    return (wall_clock_ts - market_ts).total_seconds()


def get_market_time_with_latency(market_ts: Optional[datetime] = None) -> tuple[datetime, Optional[float]]:
    """
    Get market time and calculate latency metrics.

    Args:
        market_ts: Optional market timestamp from data feed

    Returns:
        Tuple of (effective_market_time, latency_seconds)
        latency_seconds is None if using wall-clock time fallback
    """
    wall_clock_now = datetime.now(timezone.utc)

    if market_ts is not None:
        latency = calculate_latency(market_ts, wall_clock_now)
        return market_ts, latency

    # No market time available, use wall-clock time with no latency metric
    return wall_clock_now, None


def validate_market_time(market_ts: datetime, max_age_seconds: int = 300) -> bool:
    """
    Validate that market timestamp is reasonable (not too old/future).

    Args:
        market_ts: Market timestamp to validate
        max_age_seconds: Maximum age in seconds (default 5 minutes)

    Returns:
        True if timestamp is valid, False otherwise
    """
    now = datetime.now(timezone.utc)
    age_seconds = (now - market_ts).total_seconds()

    # Check if timestamp is too old
    if age_seconds > max_age_seconds:
        return False

    # Check if timestamp is too far in future (allow 30 seconds for clock skew)
    if age_seconds < -30:
        return False

    return True


def format_market_time(market_ts: datetime) -> str:
    """
    Format market timestamp for signal emission and logging.

    Args:
        market_ts: Market timestamp to format

    Returns:
        ISO8601 formatted string
    """
    return market_ts.isoformat()


def time_elapsed_seconds(start_time: datetime, end_time: Optional[datetime] = None) -> float:
    """
    Calculate elapsed time in seconds between two market timestamps.

    Args:
        start_time: Start timestamp
        end_time: End timestamp, defaults to current market time

    Returns:
        Elapsed time in seconds
    """
    if end_time is None:
        end_time = datetime.now(timezone.utc)

    return (end_time - start_time).total_seconds()
