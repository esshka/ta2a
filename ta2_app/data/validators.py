"""
Data validation framework for market data quality checks and business rules.

This module provides comprehensive validation for normalized market data,
including data quality checks, business rule validation, and spike filtering.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from .models import BookSnap, Candle, InstrumentDataStore


class ValidationError(Exception):
    """Raised when data validation fails."""
    pass


class DataValidator:
    """Validates market data against quality and business rules."""

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        Initialize validator with configuration.

        Args:
            config: Validation configuration dict
        """
        self.config = config or {}

        # Default validation parameters
        self.max_age_seconds = self.config.get("max_age_seconds", 300)  # 5 minutes
        self.min_depth_levels = self.config.get("min_depth_levels", 1)
        self.spike_filter_atr_mult = self.config.get("spike_filter_atr_mult", 10.0)
        self.max_spread_pct = self.config.get("max_spread_pct", 5.0)  # 5% max spread
        self.min_volume_threshold = self.config.get("min_volume_threshold", 0.0)

        # Spike filtering configuration
        spike_filter_config = self.config.get("spike_filter", {})
        self.spike_filter_enabled = spike_filter_config.get("enable", True)

    def validate_candle(self, candle: Candle, store: Optional[InstrumentDataStore] = None) -> None:
        """
        Validate a single candle against quality and business rules.

        Args:
            candle: Normalized candle to validate
            store: Optional instrument data store for context

        Raises:
            ValidationError: If validation fails
        """
        # Basic data quality checks
        self._validate_candle_data_quality(candle)

        # Temporal validation
        self._validate_candle_timing(candle)

        # Business rule validation with context
        if store is not None:
            self._validate_candle_business_rules(candle, store)

    def validate_book_snap(self, book_snap: BookSnap, store: Optional[InstrumentDataStore] = None) -> None:
        """
        Validate an order book snapshot against quality and business rules.

        Args:
            book_snap: Normalized book snapshot to validate
            store: Optional instrument data store for context

        Raises:
            ValidationError: If validation fails
        """
        # Basic data quality checks
        self._validate_book_data_quality(book_snap)

        # Temporal validation
        self._validate_book_timing(book_snap)

        # Business rule validation with context
        if store is not None:
            self._validate_book_business_rules(book_snap, store)

    def _validate_candle_data_quality(self, candle: Candle) -> None:
        """Validate basic candle data quality."""
        # Price validation
        if not all(price > 0 for price in [candle.open, candle.high, candle.low, candle.close]):
            raise ValidationError("All candle prices must be positive")

        # OHLC consistency
        if candle.high < max(candle.open, candle.close):
            raise ValidationError(f"High {candle.high} must be >= max(open {candle.open}, close {candle.close})")

        if candle.low > min(candle.open, candle.close):
            raise ValidationError(f"Low {candle.low} must be <= min(open {candle.open}, close {candle.close})")

        # Volume validation
        if candle.volume < self.min_volume_threshold:
            raise ValidationError(f"Volume {candle.volume} below minimum threshold {self.min_volume_threshold}")

        # Sanity checks for extreme values
        if candle.high / candle.low > 10.0:  # More than 10x range in single bar
            raise ValidationError(f"Extreme price range: high {candle.high} / low {candle.low} = {candle.high/candle.low:.2f}")

    def _validate_candle_timing(self, candle: Candle) -> None:
        """Validate candle timing constraints."""
        now = datetime.now(UTC)

        # Check if candle is too old
        age_seconds = (now - candle.ts).total_seconds()
        if age_seconds > self.max_age_seconds:
            raise ValidationError(f"Candle too old: {age_seconds:.1f}s > {self.max_age_seconds}s")

        # Check if candle is too far in future (allow small clock skew)
        future_limit = now + timedelta(seconds=60)
        if candle.ts > future_limit:
            raise ValidationError(f"Candle timestamp too far in future: {candle.ts} > {future_limit}")

    def _validate_candle_business_rules(self, candle: Candle, store: InstrumentDataStore) -> None:
        """Validate candle against business rules using store context."""
        # Check for sequence violations (out of order)
        if store.last_update and candle.ts < store.last_update:
            # Only reject if this is a closed candle older than last closed
            if candle.is_closed:
                raise ValidationError(f"Out of order closed candle: {candle.ts} < {store.last_update}")

        # Spike detection using ATR if available (only if spike filtering is enabled)
        if self.spike_filter_enabled and store.last_price > 0:
            price_change_pct = abs(candle.close - store.last_price) / store.last_price

            # Simple spike filter - more sophisticated ATR-based filtering would go here
            if price_change_pct > 0.5:  # 50% move in single tick
                raise ValidationError(f"Potential price spike: {price_change_pct:.1%} change from {store.last_price} to {candle.close}")

    def _validate_book_data_quality(self, book_snap: BookSnap) -> None:
        """Validate basic order book data quality."""
        # Check minimum depth requirements
        if len(book_snap.bids) < self.min_depth_levels:
            raise ValidationError(f"Insufficient bid depth: {len(book_snap.bids)} < {self.min_depth_levels}")

        if len(book_snap.asks) < self.min_depth_levels:
            raise ValidationError(f"Insufficient ask depth: {len(book_snap.asks)} < {self.min_depth_levels}")

        # Validate level ordering
        self._validate_level_ordering(book_snap.bids, "bids", descending=True)
        self._validate_level_ordering(book_snap.asks, "asks", descending=False)

        # Validate spread
        if book_snap.bid_price and book_snap.ask_price:
            if book_snap.bid_price >= book_snap.ask_price:
                raise ValidationError(f"Invalid spread: bid {book_snap.bid_price} >= ask {book_snap.ask_price}")

            # Check for extreme spreads
            spread_pct = (book_snap.ask_price - book_snap.bid_price) / book_snap.bid_price
            if spread_pct > self.max_spread_pct / 100.0:
                raise ValidationError(f"Extreme spread: {spread_pct:.1%} > {self.max_spread_pct}%")

    def _validate_book_timing(self, book_snap: BookSnap) -> None:
        """Validate book snapshot timing constraints."""
        now = datetime.now(UTC)

        # Check if book is too old
        age_seconds = (now - book_snap.ts).total_seconds()
        if age_seconds > self.max_age_seconds:
            raise ValidationError(f"Book snapshot too old: {age_seconds:.1f}s > {self.max_age_seconds}s")

        # Check if book is too far in future
        future_limit = now + timedelta(seconds=60)
        if book_snap.ts > future_limit:
            raise ValidationError(f"Book timestamp too far in future: {book_snap.ts} > {future_limit}")

    def _validate_book_business_rules(self, book_snap: BookSnap, store: InstrumentDataStore) -> None:
        """Validate book snapshot against business rules using store context."""
        # Check for sequence violations
        if store.curr_book and book_snap.ts < store.curr_book.ts:
            raise ValidationError(f"Out of order book: {book_snap.ts} < {store.curr_book.ts}")

        # Validate against last known price for spike detection
        if store.last_price > 0 and book_snap.mid_price:
            price_change_pct = abs(book_snap.mid_price - store.last_price) / store.last_price

            if price_change_pct > 0.5:  # 50% move in single tick
                raise ValidationError(f"Potential book price spike: {price_change_pct:.1%} change from {store.last_price} to {book_snap.mid_price}")

    def _validate_level_ordering(self, levels: list, side: str, descending: bool) -> None:
        """Validate that price levels are properly ordered."""
        if len(levels) < 2:
            return

        for i in range(1, len(levels)):
            prev_price = levels[i-1].price
            curr_price = levels[i].price

            if descending:
                if curr_price >= prev_price:
                    raise ValidationError(f"Invalid {side} ordering: {curr_price} >= {prev_price} at index {i}")
            else:
                if curr_price <= prev_price:
                    raise ValidationError(f"Invalid {side} ordering: {curr_price} <= {prev_price} at index {i}")


def is_duplicate_candle(candle: Candle, store: InstrumentDataStore, timeframe: str) -> bool:
    """
    Check if candle is a duplicate of existing data.

    Args:
        candle: Candle to check
        store: Instrument data store
        timeframe: Timeframe to check against

    Returns:
        True if candle is a duplicate
    """
    bars = store.get_bars(timeframe)

    if not bars:
        return False

    # Check if timestamp matches last bar
    last_bar = bars[-1]
    return candle.ts == last_bar.ts


def should_skip_old_candle(candle: Candle, store: InstrumentDataStore, timeframe: str) -> bool:
    """
    Determine if candle should be skipped due to being too old.

    Args:
        candle: Candle to check
        store: Instrument data store
        timeframe: Timeframe to check against

    Returns:
        True if candle should be skipped
    """
    bars = store.get_bars(timeframe)

    if not bars:
        return False

    # Skip if candle is older than last closed candle
    last_bar = bars[-1]
    if candle.is_closed and last_bar.is_closed and candle.ts < last_bar.ts:
        return True

    return False


def validate_atr_spike_filter(price: float, last_price: float, atr: Optional[float], multiplier: float = 10.0) -> bool:
    """
    Validate price against ATR-based spike filter.

    Args:
        price: New price to validate
        last_price: Previous price for comparison
        atr: Average True Range for volatility context
        multiplier: ATR multiplier for spike threshold

    Returns:
        True if price passes validation (not a spike)
    """
    if atr is None or atr <= 0:
        # Fallback to simple percentage filter
        return abs(price - last_price) / last_price <= 0.5

    # ATR-based spike detection
    max_move = atr * multiplier
    return abs(price - last_price) <= max_move
