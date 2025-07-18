"""Main metrics calculator for coordinating all metric calculations"""

import math
from typing import TYPE_CHECKING, Optional

from ..config.defaults import DefaultConfig, get_default_config
from ..data.models import Candle, InstrumentDataStore
from ..errors import (
    InsufficientDataError,
    MalformedDataError,
    MetricsCalculationError,
    MissingDataError,
)
from .atr import ATRCalculator
from .candle_structure import analyze_candle_structure, detect_pinbar
from .orderbook import BookSnap, OrderBookAnalyzer
from .volume import RVOLCalculator

if TYPE_CHECKING:
    from ..models.metrics import MetricsSnapshot


class MetricsCalculator:
    """
    Main metrics calculator that coordinates all technical indicator calculations
    """

    def __init__(self, config: Optional[DefaultConfig] = None):
        self.config = config or get_default_config()

        # Initialize component calculators (now stateless)
        self.atr_calculator = ATRCalculator(period=self.config.atr.period)
        self.rvol_calculator = RVOLCalculator(period=self.config.volume.rvol_period)
        self.orderbook_analyzer = OrderBookAnalyzer(
            max_levels=self.config.orderbook.max_levels,
            depletion_threshold=self.config.orderbook.depletion_threshold,
            imbalance_threshold=self.config.orderbook.imbalance_threshold
        )

        # State tracking
        self.last_candle: Optional[Candle] = None
        self.last_metrics: Optional[MetricsSnapshot] = None

    def calculate_metrics(self, candle: Candle, data_store: InstrumentDataStore,
                         timeframe: str = "1m", book: Optional[BookSnap] = None) -> "MetricsSnapshot":
        """
        Calculate all metrics for a given candle using centralized data store

        Args:
            candle: Current candle data
            data_store: Centralized instrument data store
            timeframe: Timeframe for historical data lookup
            book: Optional order book snapshot

        Returns:
            MetricsSnapshot with all calculated metrics
        """
        try:
            # Validate input data
            if not candle:
                raise MissingDataError("Candle data is required for metrics calculation", data_type="candle")
            
            if not data_store:
                raise MissingDataError("Data store is required for metrics calculation", data_type="data_store")

            # Validate candle data integrity
            self._validate_candle_data(candle)

            timestamp = candle.ts

            # Get historical data from centralized store
            candle_history = data_store.get_bars(timeframe)
            volume_history = data_store.get_vol_history(timeframe)

            # Check data sufficiency
            self._validate_data_sufficiency(candle_history, volume_history)

            # Calculate ATR and NATR using centralized data
            try:
                atr = self.atr_calculator.calculate_with_candles(candle_history)
                natr_pct = self.atr_calculator.calculate_natr_with_candles(candle_history)
                
                # Validate ATR calculations
                self._validate_atr_values(atr, natr_pct)
                
            except Exception as e:
                raise MetricsCalculationError(
                    f"ATR calculation failed: {str(e)}", 
                    metric_name="atr",
                    calculation_input={"candle_count": len(candle_history)}
                )

            # Calculate RVOL using centralized data
            try:
                rvol = self.rvol_calculator.calculate_with_history(candle.volume, volume_history)
                
                # Validate RVOL calculation
                self._validate_rvol_value(rvol)
                
            except Exception as e:
                raise MetricsCalculationError(
                    f"RVOL calculation failed: {str(e)}", 
                    metric_name="rvol",
                    calculation_input={"volume": candle.volume, "history_count": len(volume_history)}
                )

            # Analyze candle structure
            try:
                candle_structure = analyze_candle_structure(candle)
                pinbar = detect_pinbar(
                    candle,
                    body_threshold=self.config.candle.pinbar_body_threshold,
                    shadow_threshold=self.config.candle.pinbar_shadow_threshold,
                    tail_threshold=self.config.candle.pinbar_tail_threshold
                )
            except Exception as e:
                raise MetricsCalculationError(
                    f"Candle structure analysis failed: {str(e)}", 
                    metric_name="candle_structure",
                    calculation_input={"candle": str(candle)}
                )

            # Analyze order book if provided
            ob_imbalance_long = None
            ob_imbalance_short = None
            ob_sweep_detected = False
            ob_sweep_side = None

            if book:
                try:
                    ob_metrics = self.orderbook_analyzer.analyze(book)
                    ob_imbalance_long = ob_metrics.imbalance_long
                    ob_imbalance_short = ob_metrics.imbalance_short
                    ob_sweep_detected = ob_metrics.sweep_detected
                    ob_sweep_side = ob_metrics.sweep_side
                    
                    # Validate order book metrics
                    self._validate_orderbook_metrics(ob_imbalance_long, ob_imbalance_short)
                    
                except Exception as e:
                    raise MetricsCalculationError(
                        f"Order book analysis failed: {str(e)}", 
                        metric_name="orderbook",
                        calculation_input={"book": str(book)[:100]}
                    )

            # Create metrics snapshot
            from ..models.metrics import MetricsSnapshot
            metrics = MetricsSnapshot(
                timestamp=timestamp,
                atr=atr,
                natr_pct=natr_pct,
                rvol=rvol,
                pinbar=pinbar,
                candle_structure=candle_structure,
                ob_imbalance_long=ob_imbalance_long,
                ob_imbalance_short=ob_imbalance_short,
                ob_sweep_detected=ob_sweep_detected,
                ob_sweep_side=ob_sweep_side
            )

            # Update state
            self.last_candle = candle
            self.last_metrics = metrics

            return metrics

        except (MissingDataError, InsufficientDataError, MalformedDataError, MetricsCalculationError):
            # Re-raise known error types
            raise
        except Exception as e:
            raise MetricsCalculationError(
                f"Unexpected error in metrics calculation: {str(e)}",
                metric_name="unknown",
                calculation_input={"candle": str(candle)[:100] if candle else None}
            )

    def get_last_metrics(self) -> Optional["MetricsSnapshot"]:
        """Get the last calculated metrics snapshot"""
        return self.last_metrics

    def reset(self):
        """Reset calculator state (now only clears last metrics)"""
        self.last_candle = None
        self.last_metrics = None

    def update_config(self, new_config: DefaultConfig):
        """Update configuration and reset calculators"""
        self.config = new_config
        # Recreate calculators with new config
        self.atr_calculator = ATRCalculator(period=self.config.atr.period)
        self.rvol_calculator = RVOLCalculator(period=self.config.volume.rvol_period)
        self.orderbook_analyzer = OrderBookAnalyzer(
            max_levels=self.config.orderbook.max_levels,
            depletion_threshold=self.config.orderbook.depletion_threshold,
            imbalance_threshold=self.config.orderbook.imbalance_threshold
        )
        self.reset()

    def get_warmup_period(self) -> int:
        """Get the minimum number of candles needed for full metrics calculation"""
        return max(self.config.atr.period, self.config.volume.rvol_period)

    def is_warmed_up(self, data_store: InstrumentDataStore, timeframe: str = "1m") -> bool:
        """Check if data store has enough data for reliable metrics"""
        candle_history = data_store.get_bars(timeframe)
        volume_history = data_store.get_vol_history(timeframe)

        return (len(candle_history) >= self.config.atr.period and
                len(volume_history) >= self.config.volume.rvol_period)

    def _validate_candle_data(self, candle: Candle) -> None:
        """Validate candle data integrity."""
        if not candle.ts:
            raise MalformedDataError("Candle missing timestamp")
        
        if candle.open is None or candle.high is None or candle.low is None or candle.close is None:
            raise MalformedDataError("Candle missing OHLC data")
        
        if candle.volume is None:
            raise MalformedDataError("Candle missing volume data")
        
        # Check for invalid price values
        prices = [candle.open, candle.high, candle.low, candle.close]
        for price in prices:
            if not isinstance(price, (int, float)):
                raise MalformedDataError(f"Invalid price type: {type(price)}")
            if math.isnan(price) or math.isinf(price):
                raise MalformedDataError(f"Invalid price value: {price}")
            if price <= 0:
                raise MalformedDataError(f"Non-positive price: {price}")
        
        # Check OHLC consistency
        if candle.high < max(candle.open, candle.close):
            raise MalformedDataError("High price less than open/close")
        if candle.low > min(candle.open, candle.close):
            raise MalformedDataError("Low price greater than open/close")
        
        # Check volume validity
        if not isinstance(candle.volume, (int, float)):
            raise MalformedDataError(f"Invalid volume type: {type(candle.volume)}")
        if math.isnan(candle.volume) or math.isinf(candle.volume):
            raise MalformedDataError(f"Invalid volume value: {candle.volume}")
        if candle.volume < 0:
            raise MalformedDataError(f"Negative volume: {candle.volume}")

    def _validate_data_sufficiency(self, candle_history: list, volume_history: list) -> None:
        """Validate that we have sufficient data for calculations."""
        atr_period = self.config.atr.period
        rvol_period = self.config.volume.rvol_period
        
        if len(candle_history) < atr_period:
            raise InsufficientDataError(
                f"Insufficient candle data for ATR calculation",
                required_count=atr_period,
                available_count=len(candle_history)
            )
        
        if len(volume_history) < rvol_period:
            raise InsufficientDataError(
                f"Insufficient volume data for RVOL calculation",
                required_count=rvol_period,
                available_count=len(volume_history)
            )

    def _validate_atr_values(self, atr: Optional[float], natr_pct: Optional[float]) -> None:
        """Validate ATR calculation results."""
        if atr is not None:
            if math.isnan(atr) or math.isinf(atr):
                raise MetricsCalculationError(f"Invalid ATR value: {atr}", metric_name="atr")
            if atr < 0:
                raise MetricsCalculationError(f"Negative ATR value: {atr}", metric_name="atr")
            # ATR should be reasonable relative to price action
            if atr > 1e6:  # Sanity check for extremely large ATR
                raise MetricsCalculationError(f"ATR value too large: {atr}", metric_name="atr")
        
        if natr_pct is not None:
            if math.isnan(natr_pct) or math.isinf(natr_pct):
                raise MetricsCalculationError(f"Invalid NATR value: {natr_pct}", metric_name="natr")
            if natr_pct < 0:
                raise MetricsCalculationError(f"Negative NATR value: {natr_pct}", metric_name="natr")
            # NATR should be reasonable percentage
            if natr_pct > 100:  # More than 100% is unusual
                raise MetricsCalculationError(f"NATR value too large: {natr_pct}%", metric_name="natr")

    def _validate_rvol_value(self, rvol: Optional[float]) -> None:
        """Validate RVOL calculation results."""
        if rvol is not None:
            if math.isnan(rvol) or math.isinf(rvol):
                raise MetricsCalculationError(f"Invalid RVOL value: {rvol}", metric_name="rvol")
            if rvol < 0:
                raise MetricsCalculationError(f"Negative RVOL value: {rvol}", metric_name="rvol")
            # RVOL should be reasonable relative volume
            if rvol > 1000:  # More than 1000x average volume is unusual
                raise MetricsCalculationError(f"RVOL value too large: {rvol}", metric_name="rvol")

    def _validate_orderbook_metrics(self, imbalance_long: Optional[float], imbalance_short: Optional[float]) -> None:
        """Validate order book metrics."""
        for imbalance, side in [(imbalance_long, "long"), (imbalance_short, "short")]:
            if imbalance is not None:
                if math.isnan(imbalance) or math.isinf(imbalance):
                    raise MetricsCalculationError(f"Invalid {side} imbalance: {imbalance}", metric_name="orderbook")
                if imbalance < 0:
                    raise MetricsCalculationError(f"Negative {side} imbalance: {imbalance}", metric_name="orderbook")
                # Imbalance should be reasonable ratio
                if imbalance > 1000:  # More than 1000:1 ratio is unusual
                    raise MetricsCalculationError(f"{side} imbalance too large: {imbalance}", metric_name="orderbook")

