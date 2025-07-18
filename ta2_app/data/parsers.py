"""
OKX-specific data parsers for converting raw exchange formats to normalized objects.

This module handles parsing of OKX candlestick and order book payloads into
canonical data structures with proper type conversion and error handling.
"""

import json
import time
from datetime import UTC, datetime
from typing import Any

try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

from .models import BookLevel, BookSnap, Candle
from .validators import validate_atr_spike_filter


class ParseError(Exception):
    """Raised when parsing fails due to invalid data format."""
    pass


class InvalidPriceError(ParseError):
    """Raised when price data is invalid."""
    pass


class InvalidTimestampError(ParseError):
    """Raised when timestamp data is invalid."""
    pass


class InvalidVolumeError(ParseError):
    """Raised when volume data is invalid."""
    pass


class OHLCConsistencyError(ParseError):
    """Raised when OHLC prices are inconsistent."""
    pass


class PriceSpikeError(ParseError):
    """Raised when price spike is detected and filtering is enabled."""
    pass


class CircuitBreakerError(ParseError):
    """Raised when circuit breaker trips due to consecutive failures."""
    pass


class ParsingMetrics:
    """Simple metrics collection for parsing operations."""

    def __init__(self):
        self.total_parses = 0
        self.successful_parses = 0
        self.failed_parses = 0
        self.total_candles_parsed = 0
        self.total_parse_time = 0.0
        self.consecutive_failures = 0
        self.spike_filter_rejections = 0
        self.last_failure_time = None

    def record_parse_start(self):
        """Record the start of a parsing operation."""
        self.total_parses += 1
        return time.time()

    def record_parse_success(self, start_time: float, candle_count: int):
        """Record successful parsing."""
        self.successful_parses += 1
        self.total_candles_parsed += candle_count
        self.total_parse_time += time.time() - start_time
        self.consecutive_failures = 0

    def record_parse_failure(self, start_time: float, error: Exception):
        """Record parsing failure."""
        self.failed_parses += 1
        self.consecutive_failures += 1
        self.total_parse_time += time.time() - start_time
        self.last_failure_time = time.time()

        if isinstance(error, PriceSpikeError):
            self.spike_filter_rejections += 1

    def should_circuit_break(self, max_consecutive_failures: int = 10) -> bool:
        """Simple circuit breaker logic."""
        return self.consecutive_failures >= max_consecutive_failures

    def get_stats(self) -> dict[str, Any]:
        """Get current metrics."""
        avg_parse_time = self.total_parse_time / max(self.total_parses, 1)
        success_rate = self.successful_parses / max(self.total_parses, 1)

        return {
            "total_parses": self.total_parses,
            "successful_parses": self.successful_parses,
            "failed_parses": self.failed_parses,
            "success_rate": success_rate,
            "total_candles_parsed": self.total_candles_parsed,
            "avg_parse_time_ms": avg_parse_time * 1000,
            "consecutive_failures": self.consecutive_failures,
            "spike_filter_rejections": self.spike_filter_rejections,
            "last_failure_time": self.last_failure_time
        }


# Global metrics instance
_parsing_metrics = ParsingMetrics()


def get_parsing_metrics() -> dict[str, Any]:
    """Get current parsing metrics."""
    return _parsing_metrics.get_stats()


def reset_parsing_metrics():
    """Reset parsing metrics."""
    global _parsing_metrics
    _parsing_metrics = ParsingMetrics()


def parse_candlestick_payload(payload: dict[str, Any], *,
                                 enable_spike_filter: bool = False,
                                 last_price: float = None,
                                 atr: float = None,
                                 spike_multiplier: float = 10.0,
                                 enable_circuit_breaker: bool = True,
                                 max_consecutive_failures: int = 10) -> list[Candle]:
    """
    Parse OKX candlestick payload into normalized Candle objects.

    Expected OKX format:
    {
        "code": "0",
        "msg": "",
        "data": [
            ["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "0"]
        ]
    }

    Inner array format: [ts_ms, open, high, low, close, vol_base, vol_quote?, vol_quote_alt?, confirm_flag]

    Args:
        payload: Raw OKX candlestick payload
        enable_spike_filter: Whether to enable ATR-based spike filtering
        last_price: Previous price for spike detection (required if enable_spike_filter=True)
        atr: Average True Range for spike detection (None uses fallback filter)
        spike_multiplier: ATR multiplier for spike threshold (default: 10.0)
        enable_circuit_breaker: Whether to enable circuit breaker protection (default: True)
        max_consecutive_failures: Maximum consecutive failures before circuit breaker trips (default: 10)

    Returns:
        List of normalized Candle objects

    Raises:
        ParseError: If payload format is invalid
        PriceSpikeError: If spike filtering is enabled and spike is detected
        CircuitBreakerError: If circuit breaker trips due to consecutive failures
        InvalidPriceError: If price data is invalid
        InvalidTimestampError: If timestamp data is invalid
        InvalidVolumeError: If volume data is invalid
        OHLCConsistencyError: If OHLC prices are inconsistent
    """
    # Circuit breaker check
    if enable_circuit_breaker and _parsing_metrics.should_circuit_break(max_consecutive_failures):
        raise CircuitBreakerError(f"Circuit breaker tripped after {_parsing_metrics.consecutive_failures} consecutive failures")

    # Start metrics collection
    start_time = _parsing_metrics.record_parse_start()

    try:
        # Validate spike filtering parameters
        if enable_spike_filter and last_price is None:
            raise ParseError("last_price is required when enable_spike_filter=True")

        # Validate top-level structure
        if not isinstance(payload, dict):
            raise ParseError("Payload must be a dictionary")

        if "data" not in payload:
            raise ParseError("Missing 'data' field in payload")

        data = payload["data"]
        if not isinstance(data, list):
            raise ParseError("'data' field must be a list")

        candles = []

        for i, candle_data in enumerate(data):
            try:
                candle = _parse_single_candle(candle_data)

                # Apply spike filtering if enabled
                if enable_spike_filter:
                    # Check each OHLC price against spike filter
                    for price_name, price_value in [("open", candle.open), ("high", candle.high),
                                                  ("low", candle.low), ("close", candle.close)]:
                        if not validate_atr_spike_filter(price_value, last_price, atr, spike_multiplier):
                            raise PriceSpikeError(f"Price spike detected in {price_name}: {price_value} vs last_price={last_price}, atr={atr}, multiplier={spike_multiplier}")

                candles.append(candle)
            except (InvalidPriceError, InvalidTimestampError, InvalidVolumeError, OHLCConsistencyError, PriceSpikeError):
                raise  # Re-raise specific parsing errors
            except (ValueError, IndexError, TypeError) as e:
                raise ParseError(f"Invalid candle data at index {i}: {e}")

        # Record successful parsing
        _parsing_metrics.record_parse_success(start_time, len(candles))
        return candles

    except ParseError as e:
        _parsing_metrics.record_parse_failure(start_time, e)
        raise
    except Exception as e:
        error = ParseError(f"Unexpected error parsing candlestick payload: {e}")
        _parsing_metrics.record_parse_failure(start_time, error)
        raise error


def _parse_single_candle(candle_data: list[str]) -> Candle:
    """Parse single OKX candle array into Candle object."""
    if not isinstance(candle_data, list):
        raise ValueError("Candle data must be a list")

    if len(candle_data) < 9:
        raise ValueError(f"Candle data must have at least 9 elements, got {len(candle_data)}")

    try:
        # Parse timestamp (milliseconds since epoch)
        try:
            ts_ms = int(candle_data[0])
            ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
        except (ValueError, OSError) as e:
            raise InvalidTimestampError(f"Invalid timestamp '{candle_data[0]}': {e}")

        # Parse OHLC prices
        try:
            open_price = float(candle_data[1])
            high_price = float(candle_data[2])
            low_price = float(candle_data[3])
            close_price = float(candle_data[4])
        except ValueError as e:
            raise InvalidPriceError(f"Invalid price data [O:{candle_data[1]}, H:{candle_data[2]}, L:{candle_data[3]}, C:{candle_data[4]}]: {e}")

        # Parse volume (base volume)
        try:
            volume = float(candle_data[5])
        except ValueError as e:
            raise InvalidVolumeError(f"Invalid volume '{candle_data[5]}': {e}")

        # Parse confirmation flag
        confirm_flag = candle_data[8]
        is_closed = confirm_flag == "1"

        # Enhanced validation with specific error types
        if any(price <= 0 for price in [open_price, high_price, low_price, close_price]):
            raise InvalidPriceError(f"All prices must be positive: O={open_price}, H={high_price}, L={low_price}, C={close_price}")

        if volume < 0:
            raise InvalidVolumeError(f"Volume must be non-negative: {volume}")

        if high_price < max(open_price, close_price) or low_price > min(open_price, close_price):
            raise OHLCConsistencyError(f"High/low prices inconsistent with open/close: O={open_price}, H={high_price}, L={low_price}, C={close_price}")

        return Candle(
            ts=ts,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            is_closed=is_closed
        )

    except (InvalidPriceError, InvalidTimestampError, InvalidVolumeError, OHLCConsistencyError):
        raise  # Re-raise specific parsing errors
    except (ValueError, IndexError) as e:
        raise ParseError(f"Failed to parse candle data: {e}")


def parse_orderbook_payload(payload: dict[str, Any], max_levels: int = 5) -> BookSnap:
    """
    Parse OKX order book payload into normalized BookSnap object.

    Expected OKX format:
    {
        "code": "0",
        "msg": "",
        "data": [{
            "asks": [["41006.8", "0.60038921", "0", "1"]],
            "bids": [["41006.3", "0.30178218", "0", "2"]],
            "ts": "1629966436396"
        }]
    }

    Level format: [price, size, _, _] (ignore trailing fields)

    Args:
        payload: Raw OKX order book payload
        max_levels: Maximum number of levels to parse per side

    Returns:
        Normalized BookSnap object

    Raises:
        ParseError: If payload format is invalid
    """
    try:
        # Validate top-level structure
        if not isinstance(payload, dict):
            raise ParseError("Payload must be a dictionary")

        if "data" not in payload:
            raise ParseError("Missing 'data' field in payload")

        data = payload["data"]
        if not isinstance(data, list) or len(data) == 0:
            raise ParseError("'data' field must be a non-empty list")

        # Extract first (and typically only) book snapshot
        book_data = data[0]
        if not isinstance(book_data, dict):
            raise ParseError("Book data must be a dictionary")

        # Parse timestamp
        if "ts" not in book_data:
            raise ParseError("Missing 'ts' field in book data")

        ts_ms = int(book_data["ts"])
        ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)

        # Parse bids and asks
        bids = _parse_book_levels(book_data.get("bids", []), "bid", max_levels)
        asks = _parse_book_levels(book_data.get("asks", []), "ask", max_levels)

        # Sort levels (bids descending, asks ascending)
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price)

        # Validate spread if both sides present
        if bids and asks:
            if bids[0].price >= asks[0].price:
                raise ParseError(f"Invalid spread: bid {bids[0].price} >= ask {asks[0].price}")

        return BookSnap(ts=ts, bids=bids, asks=asks)

    except ParseError:
        raise
    except Exception as e:
        raise ParseError(f"Unexpected error parsing order book payload: {e}")


def _parse_book_levels(levels_data: list[list[str]], side: str, max_levels: int) -> list[BookLevel]:
    """Parse order book levels from OKX format."""
    levels = []

    for i, level_data in enumerate(levels_data[:max_levels]):
        try:
            if not isinstance(level_data, list) or len(level_data) < 2:
                raise ValueError("Level data must be a list with at least 2 elements")

            price = float(level_data[0])
            size = float(level_data[1])

            if price <= 0:
                raise ValueError(f"Price must be positive, got {price}")

            if size < 0:
                raise ValueError(f"Size must be non-negative, got {size}")

            # Skip zero-size levels
            if size == 0:
                continue

            levels.append(BookLevel(price=price, size=size))

        except (ValueError, IndexError, TypeError) as e:
            raise ParseError(f"Invalid {side} level at index {i}: {e}")

    return levels


def parse_json_payload(raw_data: str) -> dict[str, Any]:
    """
    Parse raw JSON string into dictionary.

    Uses orjson for better performance when available, falls back to standard json.

    Args:
        raw_data: Raw JSON string from exchange

    Returns:
        Parsed dictionary

    Raises:
        ParseError: If JSON parsing fails
    """
    try:
        if HAS_ORJSON:
            return orjson.loads(raw_data)
        else:
            return json.loads(raw_data)
    except Exception as e:
        # Handle both json.JSONDecodeError and orjson.JSONDecodeError
        if (isinstance(e, json.JSONDecodeError) or
            (HAS_ORJSON and hasattr(orjson, 'JSONDecodeError') and isinstance(e, orjson.JSONDecodeError))):
            raise ParseError(f"Invalid JSON: {e}")
        else:
            raise ParseError(f"Unexpected JSON parsing error: {e}")


def validate_okx_response(payload: dict[str, Any]) -> None:
    """
    Validate OKX response has successful status.

    Args:
        payload: Parsed OKX response

    Raises:
        ParseError: If response indicates error
    """
    code = payload.get("code")
    msg = payload.get("msg", "")

    if code != "0":
        raise ParseError(f"OKX API error - code: {code}, msg: {msg}")
