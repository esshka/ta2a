"""Candle structure analysis including pinbar detection"""

from dataclasses import dataclass
from typing import Optional

from .atr import Candle


@dataclass
class CandleStructure:
    """Candle structure analysis results"""
    range_value: float
    body: float
    upper_shadow: float
    lower_shadow: float
    body_pct: float
    upper_pct: float
    lower_pct: float
    is_bull: bool
    is_bear: bool
    is_doji: bool


def analyze_candle_structure(candle: Candle, doji_threshold: float = 0.1) -> CandleStructure:
    """
    Analyze candle structure components

    Args:
        candle: Candle to analyze
        doji_threshold: Threshold for doji detection (body % of range)

    Returns:
        CandleStructure with all analysis components
    """
    range_value = candle.high - candle.low
    body = abs(candle.close - candle.open)
    upper_shadow = candle.high - max(candle.open, candle.close)
    lower_shadow = min(candle.open, candle.close) - candle.low

    # Calculate percentages (handle zero range)
    if range_value > 0:
        body_pct = body / range_value
        upper_pct = upper_shadow / range_value
        lower_pct = lower_shadow / range_value
    else:
        body_pct = 0.0
        upper_pct = 0.0
        lower_pct = 0.0

    # Determine candle type
    is_bull = candle.close > candle.open
    is_bear = candle.close < candle.open
    is_doji = body_pct <= doji_threshold

    return CandleStructure(
        range_value=range_value,
        body=body,
        upper_shadow=upper_shadow,
        lower_shadow=lower_shadow,
        body_pct=body_pct,
        upper_pct=upper_pct,
        lower_pct=lower_pct,
        is_bull=is_bull,
        is_bear=is_bear,
        is_doji=is_doji
    )


def detect_pinbar(candle: Candle, body_threshold: float = 0.4,
                  shadow_threshold: float = 0.66, tail_threshold: float = 0.1) -> Optional[str]:
    """
    Detect pinbar patterns

    Args:
        candle: Candle to analyze
        body_threshold: Maximum body percentage for pinbar
        shadow_threshold: Minimum shadow percentage for pinbar
        tail_threshold: Maximum opposite tail percentage

    Returns:
        'bullish' for bullish pinbar, 'bearish' for bearish pinbar, None otherwise
    """
    structure = analyze_candle_structure(candle)

    # Check for bearish pinbar (long upper shadow)
    if (structure.body_pct <= body_threshold and
        structure.upper_pct >= shadow_threshold and
        structure.lower_pct <= tail_threshold):
        return 'bearish'

    # Check for bullish pinbar (long lower shadow)
    if (structure.body_pct <= body_threshold and
        structure.lower_pct >= shadow_threshold and
        structure.upper_pct <= tail_threshold):
        return 'bullish'

    return None


def is_strong_candle(candle: Candle, min_body_pct: float = 0.6) -> bool:
    """
    Check if candle shows strong directional movement

    Args:
        candle: Candle to analyze
        min_body_pct: Minimum body percentage for strong candle

    Returns:
        True if candle is strong, False otherwise
    """
    structure = analyze_candle_structure(candle)
    return structure.body_pct >= min_body_pct


def get_candle_strength_score(candle: Candle) -> float:
    """
    Calculate candle strength score (0-100)

    Args:
        candle: Candle to analyze

    Returns:
        Strength score from 0 (weakest) to 100 (strongest)
    """
    structure = analyze_candle_structure(candle)

    # Base score from body percentage
    body_score = min(structure.body_pct * 100, 100)

    # Bonus for directional clarity (not doji)
    direction_bonus = 0 if structure.is_doji else 20

    # Penalty for large opposing shadows
    if structure.is_bull:
        shadow_penalty = structure.upper_pct * 30
    elif structure.is_bear:
        shadow_penalty = structure.lower_pct * 30
    else:
        shadow_penalty = 0

    final_score = body_score + direction_bonus - shadow_penalty
    return max(0, min(100, final_score))
