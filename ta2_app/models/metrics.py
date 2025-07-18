"""Data models for metrics calculations"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..metrics.candle_structure import CandleStructure


@dataclass
class MetricsSnapshot:
    """Complete metrics snapshot for a given timestamp"""
    timestamp: datetime
    atr: Optional[float] = None
    natr_pct: Optional[float] = None
    rvol: Optional[float] = None
    pinbar: Optional[str] = None  # 'bullish', 'bearish', or None
    candle_structure: Optional[CandleStructure] = None
    ob_imbalance_long: Optional[float] = None
    ob_imbalance_short: Optional[float] = None
    ob_sweep_detected: bool = False
    ob_sweep_side: Optional[str] = None  # 'bid' or 'ask'

    def has_sufficient_data(self) -> bool:
        """Check if snapshot has minimum required data for breakout evaluation"""
        return (self.atr is not None and
                self.natr_pct is not None and
                self.rvol is not None)

    def get_volatility_score(self) -> float:
        """Calculate volatility-based score (0-100)"""
        if self.natr_pct is None:
            return 0.0

        # Higher NATR indicates higher volatility
        # Scale to 0-100 range (2% NATR = 100 score)
        return min(self.natr_pct * 50, 100.0)

    def get_volume_score(self) -> float:
        """Calculate volume-based score (0-100)"""
        if self.rvol is None:
            return 0.0

        # RVOL > 2.0 = 100 score, linear scaling
        return min(max((self.rvol - 1.0) * 50, 0.0), 100.0)

    def get_momentum_score(self) -> float:
        """Calculate momentum-based score (0-100)"""
        if self.candle_structure is None:
            return 0.0

        # Strong directional candles get higher scores
        base_score = self.candle_structure.body_pct * 100

        # Bonus for pinbar patterns
        pinbar_bonus = 25 if self.pinbar else 0

        return min(base_score + pinbar_bonus, 100.0)

    def get_liquidity_score(self) -> float:
        """Calculate liquidity-based score (0-100)"""
        if self.ob_imbalance_long is None or self.ob_imbalance_short is None:
            return 50.0  # Neutral score when no order book data

        # Balanced book = higher score
        max_imbalance = max(self.ob_imbalance_long, self.ob_imbalance_short)
        if max_imbalance <= 1.5:
            return 100.0
        elif max_imbalance <= 3.0:
            return 75.0
        elif max_imbalance <= 5.0:
            return 50.0
        else:
            return 25.0

    def get_composite_score(self) -> float:
        """Calculate composite strength score (0-100)"""
        if not self.has_sufficient_data():
            return 0.0

        # Weight different components
        volatility_weight = 0.2
        volume_weight = 0.3
        momentum_weight = 0.3
        liquidity_weight = 0.2

        composite = (
            self.get_volatility_score() * volatility_weight +
            self.get_volume_score() * volume_weight +
            self.get_momentum_score() * momentum_weight +
            self.get_liquidity_score() * liquidity_weight
        )

        # Sweep detection bonus
        sweep_bonus = 15 if self.ob_sweep_detected else 0

        return min(composite + sweep_bonus, 100.0)
