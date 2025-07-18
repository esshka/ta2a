"""
Canonical data models for normalized market data.

This module defines immutable data structures that represent clean, validated
market data after normalization from raw exchange formats.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ta2_app.config.defaults import DataStoreParams


@dataclass(frozen=True)
class Candle:
    """Normalized candlestick data with UTC timestamps."""
    ts: datetime        # UTC market timestamp
    open: float        # Opening price
    high: float        # High price
    low: float         # Low price
    close: float       # Closing price
    volume: float      # Base volume
    is_closed: bool    # True if bar is closed/confirmed


@dataclass(frozen=True)
class BookLevel:
    """Single order book level with price and size."""
    price: float
    size: float


@dataclass(frozen=True)
class BookSnap:
    """Order book snapshot with sorted levels."""
    ts: datetime                # UTC market timestamp
    bids: list[BookLevel]       # Sorted by price descending
    asks: list[BookLevel]       # Sorted by price ascending

    @property
    def bid_price(self) -> Optional[float]:
        """Best bid price, None if no bids."""
        return self.bids[0].price if self.bids else None

    @property
    def ask_price(self) -> Optional[float]:
        """Best ask price, None if no asks."""
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Optional[float]:
        """Mid price between best bid/ask, None if missing either side."""
        if self.bid_price is None or self.ask_price is None:
            return None
        return (self.bid_price + self.ask_price) / 2.0

    @property
    def spread(self) -> Optional[float]:
        """Bid-ask spread, None if missing either side."""
        if self.bid_price is None or self.ask_price is None:
            return None
        return self.ask_price - self.bid_price


@dataclass
class InstrumentDataStore:
    """Per-instrument data store maintaining rolling windows and state."""

    # Rolling candlestick data by timeframe
    bars: dict[str, deque] = None  # deque[Candle], maxlen configured

    # Rolling volume history for RVOL calculation
    vol_history: dict[str, deque] = None  # deque[float], maxlen configured

    # Current and previous order book snapshots
    prev_book: Optional[BookSnap] = None
    curr_book: Optional[BookSnap] = None

    # Derived state
    last_price: float = 0.0
    last_update: Optional[datetime] = None

    # Configuration
    config: DataStoreParams = None

    def __post_init__(self):
        """Initialize collections if not provided."""
        if self.bars is None:
            self.bars = {}
        if self.vol_history is None:
            self.vol_history = {}
        if self.config is None:
            self.config = DataStoreParams()

    def get_bars(self, timeframe: str, max_len: Optional[int] = None) -> deque:
        """Get or create candlestick deque for timeframe."""
        if timeframe not in self.bars:
            actual_max_len = max_len if max_len is not None else self.config.bars_window_size
            self.bars[timeframe] = deque(maxlen=actual_max_len)
        return self.bars[timeframe]

    def get_vol_history(self, timeframe: str, max_len: Optional[int] = None) -> deque:
        """Get or create volume history deque for timeframe."""
        if timeframe not in self.vol_history:
            actual_max_len = max_len if max_len is not None else self.config.volume_window_size
            self.vol_history[timeframe] = deque(maxlen=actual_max_len)
        return self.vol_history[timeframe]

    def update_last_price(self, price: float, timestamp: datetime):
        """Update last known price and timestamp."""
        self.last_price = price
        self.last_update = timestamp

    def update_book(self, new_book: BookSnap):
        """Update order book snapshots."""
        self.prev_book = self.curr_book
        self.curr_book = new_book

        # Update last price from mid if available
        if new_book.mid_price is not None:
            self.update_last_price(new_book.mid_price, new_book.ts)


@dataclass(frozen=True)
class NormalizationResult:
    """Result of data normalization process."""

    # Normalized data (None if invalid/skipped)
    candle: Optional[Candle] = None
    book_snap: Optional[BookSnap] = None

    # Processing metadata
    success: bool = True
    error_msg: Optional[str] = None
    skipped_reason: Optional[str] = None

    # Derived updates
    last_price_updated: bool = False
    new_last_price: Optional[float] = None

    @classmethod
    def success_with_candle(cls, candle: Candle, last_price: Optional[float] = None):
        """Create successful result with candle."""
        return cls(
            candle=candle,
            success=True,
            last_price_updated=last_price is not None,
            new_last_price=last_price
        )

    @classmethod
    def success_with_book(cls, book_snap: BookSnap, last_price: Optional[float] = None):
        """Create successful result with order book."""
        return cls(
            book_snap=book_snap,
            success=True,
            last_price_updated=last_price is not None,
            new_last_price=last_price
        )

    @classmethod
    def error(cls, error_msg: str):
        """Create error result."""
        return cls(success=False, error_msg=error_msg)

    @classmethod
    def skipped(cls, reason: str):
        """Create skipped result."""
        return cls(success=True, skipped_reason=reason)
