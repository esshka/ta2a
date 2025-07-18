"""RVOL (Relative Volume) calculations"""

from collections import deque
from typing import Optional


def calculate_rvol(current_volume: float, volume_history: list[float], period: int = 20) -> Optional[float]:
    """
    Calculate Relative Volume (RVOL)

    RVOL = current_volume / SMA(volume_history)

    Args:
        current_volume: Current bar volume
        volume_history: Historical volume values (excluding current)
        period: Lookback period for average (default 20)

    Returns:
        RVOL value or None if insufficient data
    """
    if len(volume_history) < period:
        return None

    # Use last 'period' values for average
    recent_volumes = volume_history[-period:]
    volume_average = sum(recent_volumes) / len(recent_volumes)

    if volume_average <= 0:
        return None

    return current_volume / volume_average


class RVOLCalculator:
    """Efficient RVOL calculator using external volume history from data store"""

    def __init__(self, period: int = 20):
        self.period = period

    def calculate_with_history(self, current_volume: float, volume_history: deque) -> Optional[float]:
        """
        Calculate RVOL using external volume history

        Args:
            current_volume: Current bar volume
            volume_history: External volume history deque from data store

        Returns:
            RVOL value or None if insufficient data
        """
        if len(volume_history) < self.period:
            return None

        # Use last 'period' values for average
        recent_volumes = list(volume_history)[-self.period:]
        volume_average = sum(recent_volumes) / len(recent_volumes)

        if volume_average <= 0:
            return None

        return current_volume / volume_average

    def update(self, volume: float) -> Optional[float]:
        """
        Legacy method - deprecated, use calculate_with_history instead
        Maintained for backward compatibility
        """
        # This method should not be used with the new centralized approach
        # but kept for backward compatibility during transition
        return None

    def get_current_rvol(self, current_volume: float) -> Optional[float]:
        """
        Legacy method - deprecated, use calculate_with_history instead
        Maintained for backward compatibility
        """
        # This method should not be used with the new centralized approach
        # but kept for backward compatibility during transition
        return None
