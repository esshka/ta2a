"""ATR (Average True Range) and NATR (Normalized ATR) calculations"""

from collections import deque
from typing import Optional

from ta2_app.data.models import Candle


def calculate_true_range(current: Candle, previous: Optional[Candle] = None) -> float:
    """
    Calculate True Range for a single candle

    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))

    Args:
        current: Current candle
        previous: Previous candle (None for first candle)

    Returns:
        True Range value
    """
    if previous is None:
        # First candle case - use high-low range
        return current.high - current.low

    range_hl = current.high - current.low
    range_hc = abs(current.high - previous.close)
    range_lc = abs(current.low - previous.close)

    return max(range_hl, range_hc, range_lc)


def calculate_atr(candles: list[Candle], period: int = 14) -> Optional[float]:
    """
    Calculate Average True Range using Simple Moving Average

    Args:
        candles: List of candles (must be in chronological order)
        period: ATR period (default 14)

    Returns:
        ATR value or None if insufficient data
    """
    if len(candles) < period:
        return None

    # Calculate True Range for each candle
    true_ranges = []
    for i in range(len(candles)):
        previous = candles[i-1] if i > 0 else None
        tr = calculate_true_range(candles[i], previous)
        true_ranges.append(tr)

    # Calculate SMA of True Ranges for the last 'period' values
    recent_trs = true_ranges[-period:]
    return sum(recent_trs) / len(recent_trs)


def calculate_natr(atr: float, current_price: float) -> float:
    """
    Calculate Normalized Average True Range

    NATR = 100 * ATR / current_price

    Args:
        atr: ATR value
        current_price: Current close price

    Returns:
        NATR percentage value
    """
    if current_price <= 0:
        return 0.0

    return 100.0 * atr / current_price


class ATRCalculator:
    """Efficient ATR calculator using external candlestick data from data store"""

    def __init__(self, period: int = 14):
        self.period = period

    def calculate_with_candles(self, candles: deque) -> Optional[float]:
        """
        Calculate ATR using external candlestick data

        Args:
            candles: External candlestick deque from data store

        Returns:
            ATR value or None if insufficient data
        """
        if len(candles) < self.period:
            return None

        # Convert deque to list for easier processing
        candle_list = list(candles)

        # Calculate ATR using the existing function
        return calculate_atr(candle_list, self.period)

    def calculate_natr_with_candles(self, candles: deque) -> Optional[float]:
        """
        Calculate NATR using external candlestick data

        Args:
            candles: External candlestick deque from data store

        Returns:
            NATR value or None if insufficient data
        """
        if len(candles) < self.period:
            return None

        candle_list = list(candles)
        atr = calculate_atr(candle_list, self.period)

        if atr is None:
            return None

        # Use the last candle's close price
        current_price = candle_list[-1].close
        return calculate_natr(atr, current_price)

    def update(self, candle: Candle) -> Optional[float]:
        """
        Legacy method - deprecated, use calculate_with_candles instead
        Maintained for backward compatibility
        """
        # This method should not be used with the new centralized approach
        # but kept for backward compatibility during transition
        return None

    def get_natr(self, current_price: float) -> Optional[float]:
        """
        Legacy method - deprecated, use calculate_natr_with_candles instead
        Maintained for backward compatibility
        """
        # This method should not be used with the new centralized approach
        # but kept for backward compatibility during transition
        return None
