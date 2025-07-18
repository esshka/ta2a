"""
Main data normalization pipeline for converting raw market data to canonical objects.

This module provides the DataNormalizer class that orchestrates parsing, validation,
and normalization of market data while maintaining instrument-specific data stores.
"""

import logging
from typing import Any, Optional

from ..errors import (
    DataQualityError,
    TemporalDataError,
    PartialDataError,
    MissingDataError,
    MalformedDataError,
    InsufficientDataError,
    GracefulDegradationError,
)
from ..metrics.atr import ATRCalculator
from .models import BookSnap, Candle, InstrumentDataStore, NormalizationResult
from .parsers import (
    ParseError,
    PriceSpikeError,
    parse_candlestick_payload,
    parse_json_payload,
    parse_orderbook_payload,
    validate_okx_response,
)
from .validators import (
    DataValidator,
    ValidationError,
    is_duplicate_candle,
    should_skip_old_candle,
)

logger = logging.getLogger(__name__)


class DataNormalizer:
    """
    Main data normalization pipeline for market data.

    Handles the complete flow from raw exchange data to normalized canonical objects
    with proper validation, error handling, and state management.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        Initialize data normalizer with configuration.

        Args:
            config: Normalization configuration dict
        """
        self.config = config or {}
        self.validator = DataValidator(config)

        # Per-instrument data stores
        self.stores: dict[str, InstrumentDataStore] = {}

        # Default timeframes to maintain
        self.default_timeframes = ["1s", "1m", "5m", "15m", "1h", "1d"]

        # Spike filtering configuration
        spike_filter_config = self.config.get("spike_filter", {})
        self.enable_spike_filter = spike_filter_config.get("enable", True)
        self.spike_filter_atr_mult = spike_filter_config.get("atr_multiplier", 10.0)

        # ATR calculator for spike filtering
        atr_config = self.config.get("atr_params", {})
        atr_period = atr_config.get("period", 14)
        self.atr_calculator = ATRCalculator(period=atr_period)

    def get_or_create_store(self, instrument_id: str) -> InstrumentDataStore:
        """Get or create instrument data store."""
        if instrument_id not in self.stores:
            self.stores[instrument_id] = InstrumentDataStore()
        return self.stores[instrument_id]

    def _get_last_price_for_spike_filter(self, store: InstrumentDataStore) -> Optional[float]:
        """Get last price for spike filtering context."""
        if not self.enable_spike_filter:
            return None

        # Try to get from stored last price
        if store.last_price and store.last_price > 0:
            return store.last_price

        # Fallback to last candle close price
        bars = store.get_bars("1s") or store.get_bars("1m")
        if bars and len(bars) > 0:
            return bars[-1].close

        return None

    def _get_atr_for_spike_filter(self, store: InstrumentDataStore) -> Optional[float]:
        """Get ATR for spike filtering context."""
        if not self.enable_spike_filter:
            return None

        # Try to calculate ATR from available candlestick data
        # Use 1s timeframe first, fallback to 1m if needed
        candle_history = store.get_bars("1s")
        if not candle_history or len(candle_history) < self.atr_calculator.period:
            candle_history = store.get_bars("1m")

        if candle_history and len(candle_history) >= self.atr_calculator.period:
            return self.atr_calculator.calculate_with_candles(candle_history)

        return None

    def normalize_tick(self,
                      instrument_id: str,
                      raw_data: str,
                      data_type: str,
                      timeframe: str = "1s") -> NormalizationResult:
        """
        Normalize a single tick of market data.

        Args:
            instrument_id: Trading instrument identifier
            raw_data: Raw JSON data from exchange
            data_type: Type of data ("candle" or "book")
            timeframe: Timeframe for candle data

        Returns:
            NormalizationResult with normalized data or error information
        """
        try:
            # Validate input parameters
            if not instrument_id:
                raise MissingDataError("instrument_id is required", data_type="instrument_id")
            if not raw_data:
                raise MissingDataError("raw_data is required", data_type="raw_data")
            if not data_type:
                raise MissingDataError("data_type is required", data_type="data_type")
            if data_type not in ["candle", "book"]:
                raise MalformedDataError(f"Invalid data_type: {data_type}. Must be 'candle' or 'book'")

            # Parse JSON payload
            payload = parse_json_payload(raw_data)

            # Validate OKX response status
            validate_okx_response(payload)

            # Get or create instrument store
            store = self.get_or_create_store(instrument_id)

            # Route to appropriate normalizer
            if data_type == "candle":
                return self._normalize_candle_tick(instrument_id, payload, store, timeframe)
            elif data_type == "book":
                return self._normalize_book_tick(instrument_id, payload, store)
            else:
                return NormalizationResult.error(f"Unknown data type: {data_type}")

        except ParseError as e:
            # Convert ParseError to appropriate data quality error
            if "json" in str(e).lower():
                raise MalformedDataError(f"JSON parse error: {e}", raw_data=raw_data[:100])
            elif "timestamp" in str(e).lower():
                raise TemporalDataError(f"Timestamp parse error: {e}", context={"instrument_id": instrument_id})
            else:
                raise MalformedDataError(f"Parse error: {e}", raw_data=raw_data[:100])
        except (MissingDataError, MalformedDataError, TemporalDataError):
            # Re-raise structured errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error normalizing {instrument_id}: {e}")
            raise MalformedDataError(f"Unexpected normalization error: {e}", raw_data=raw_data[:100])

    def _normalize_candle_tick(self,
                              instrument_id: str,
                              payload: dict[str, Any],
                              store: InstrumentDataStore,
                              timeframe: str) -> NormalizationResult:
        """Normalize candlestick tick data."""
        try:
            # Validate payload structure
            if not isinstance(payload, dict):
                raise MalformedDataError("Payload must be a dictionary", raw_data=str(payload)[:100])

            # Get context for spike filtering
            last_price = self._get_last_price_for_spike_filter(store)
            atr = self._get_atr_for_spike_filter(store)

            # Only enable spike filtering if we have context
            spike_filtering_enabled = self.enable_spike_filter and last_price is not None

            # Parse candlestick payload with spike filtering
            candles = parse_candlestick_payload(
                payload,
                enable_spike_filter=spike_filtering_enabled,
                last_price=last_price,
                atr=atr,
                spike_multiplier=self.spike_filter_atr_mult
            )

            if not candles:
                raise PartialDataError("No candles in payload", context={"instrument_id": instrument_id, "payload": payload})

            # Process each candle (typically just one)
            last_result = None
            processing_errors = []
            
            for candle in candles:
                try:
                    result = self._process_single_candle(instrument_id, candle, store, timeframe)
                    if result.success:
                        last_result = result
                except DataQualityError as e:
                    processing_errors.append(str(e))
                    # Continue processing other candles
                    continue

            # Handle case where we had candles but none processed successfully
            if not last_result and processing_errors:
                raise GracefulDegradationError(
                    f"Failed to process {len(processing_errors)} candles",
                    degraded_functionality="candle_processing",
                    fallback_strategy="skip_invalid_candles"
                )

            return last_result or NormalizationResult.skipped("No valid candles processed")

        except PriceSpikeError as e:
            logger.warning(f"Price spike detected for {instrument_id}: {e}")
            # Convert to structured error for graceful degradation
            raise GracefulDegradationError(
                f"Price spike filtered: {e}",
                degraded_functionality="spike_filtering",
                fallback_strategy="skip_spike_data"
            )
        except ParseError as e:
            # Convert ParseError to appropriate data quality error
            if "timestamp" in str(e).lower():
                raise TemporalDataError(f"Candle timestamp error: {e}", context={"instrument_id": instrument_id})
            elif "price" in str(e).lower() or "ohlc" in str(e).lower():
                raise MalformedDataError(f"Candle price data error: {e}", raw_data=str(payload)[:100])
            else:
                raise MalformedDataError(f"Candle parse error: {e}", raw_data=str(payload)[:100])
        except (DataQualityError, GracefulDegradationError):
            # Re-raise structured errors
            raise
        except Exception as e:
            logger.error(f"Unexpected candle normalization error for {instrument_id}: {e}")
            raise MalformedDataError(f"Unexpected candle error: {e}", raw_data=str(payload)[:100])

    def _process_single_candle(self,
                              instrument_id: str,
                              candle: Candle,
                              store: InstrumentDataStore,
                              timeframe: str) -> NormalizationResult:
        """Process a single normalized candle."""
        try:
            # Validate candle object
            if not candle:
                raise MissingDataError("Candle object is None", data_type="candle")
            if not candle.ts:
                raise TemporalDataError("Candle missing timestamp", context={"instrument_id": instrument_id})

            # Check for duplicates
            if is_duplicate_candle(candle, store, timeframe):
                logger.debug(f"Duplicate candle for {instrument_id} at {candle.ts}")
                # This is a recoverable condition - we can skip duplicates
                raise GracefulDegradationError(
                    "Duplicate candle detected",
                    degraded_functionality="duplicate_handling",
                    fallback_strategy="skip_duplicate"
                )

            # Check if candle is too old
            if should_skip_old_candle(candle, store, timeframe):
                logger.debug(f"Skipping old candle for {instrument_id} at {candle.ts}")
                # This is a recoverable condition - we can skip old data
                raise TemporalDataError(
                    "Candle timestamp is too old",
                    timestamp=int(candle.ts.timestamp() * 1000),
                    context={"instrument_id": instrument_id, "timeframe": timeframe}
                )

            # Validate candle
            try:
                self.validator.validate_candle(candle, store)
            except ValidationError as e:
                # Convert validation error to appropriate data quality error
                if "timestamp" in str(e).lower():
                    raise TemporalDataError(f"Candle timestamp validation failed: {e}", context={"instrument_id": instrument_id})
                elif "price" in str(e).lower() or "ohlc" in str(e).lower():
                    raise MalformedDataError(f"Candle price validation failed: {e}")
                else:
                    raise MalformedDataError(f"Candle validation failed: {e}")

            # Update data store
            bars = store.get_bars(timeframe)
            vol_history = store.get_vol_history(timeframe)

            # Handle duplicate timestamp by replacement
            if bars and bars[-1].ts == candle.ts:
                logger.debug(f"Replacing candle for {instrument_id} at {candle.ts}")
                bars[-1] = candle
                vol_history[-1] = candle.volume
            else:
                bars.append(candle)
                vol_history.append(candle.volume)

            # Update last price and timestamp
            store.update_last_price(candle.close, candle.ts)

            logger.debug(f"Normalized candle for {instrument_id}: {candle.ts} close={candle.close}")

            return NormalizationResult.success_with_candle(candle, candle.close)

        except (DataQualityError, GracefulDegradationError):
            # Re-raise structured errors
            raise
        except Exception as e:
            logger.error(f"Unexpected candle processing error for {instrument_id}: {e}")
            raise MalformedDataError(f"Candle processing error: {e}", raw_data=str(candle)[:100])

    def _normalize_book_tick(self,
                            instrument_id: str,
                            payload: dict[str, Any],
                            store: InstrumentDataStore) -> NormalizationResult:
        """Normalize order book tick data."""
        try:
            # Validate payload structure
            if not isinstance(payload, dict):
                raise MalformedDataError("Book payload must be a dictionary", raw_data=str(payload)[:100])

            # Parse order book payload
            book_snap = parse_orderbook_payload(payload)

            # Validate book snapshot
            try:
                self.validator.validate_book_snap(book_snap, store)
            except ValidationError as e:
                # Convert validation error to appropriate data quality error
                if "timestamp" in str(e).lower():
                    raise TemporalDataError(f"Book timestamp validation failed: {e}", context={"instrument_id": instrument_id})
                elif "empty" in str(e).lower() or "missing" in str(e).lower():
                    raise PartialDataError(f"Book data incomplete: {e}", context={"instrument_id": instrument_id})
                else:
                    raise MalformedDataError(f"Book validation failed: {e}")

            # Check for minimum data requirements
            if not book_snap.asks and not book_snap.bids:
                raise PartialDataError(
                    "Order book has no asks or bids",
                    missing_fields=["asks", "bids"],
                    context={"instrument_id": instrument_id}
                )

            # Update data store
            store.update_book(book_snap)

            # Derive last price from mid if available
            last_price = None
            if book_snap.mid_price and book_snap.mid_price > 0:
                last_price = book_snap.mid_price
            elif book_snap.bid_price and book_snap.ask_price:
                # Fallback to mid calculation
                last_price = (book_snap.bid_price + book_snap.ask_price) / 2

            logger.debug(f"Normalized book for {instrument_id}: {book_snap.ts} mid={book_snap.mid_price}")

            return NormalizationResult.success_with_book(book_snap, last_price)

        except ParseError as e:
            # Convert ParseError to appropriate data quality error
            if "timestamp" in str(e).lower():
                raise TemporalDataError(f"Book timestamp error: {e}", context={"instrument_id": instrument_id})
            elif "price" in str(e).lower() or "level" in str(e).lower():
                raise MalformedDataError(f"Book price data error: {e}", raw_data=str(payload)[:100])
            else:
                raise MalformedDataError(f"Book parse error: {e}", raw_data=str(payload)[:100])
        except (DataQualityError, GracefulDegradationError):
            # Re-raise structured errors
            raise
        except Exception as e:
            logger.error(f"Unexpected book normalization error for {instrument_id}: {e}")
            raise MalformedDataError(f"Book processing error: {e}", raw_data=str(payload)[:100])

    def get_latest_candle(self, instrument_id: str, timeframe: str = "1s") -> Optional[Candle]:
        """Get the latest candle for an instrument and timeframe."""
        if instrument_id not in self.stores:
            return None

        store = self.stores[instrument_id]
        bars = store.get_bars(timeframe)

        return bars[-1] if bars else None

    def get_latest_book(self, instrument_id: str) -> Optional[BookSnap]:
        """Get the latest order book snapshot for an instrument."""
        if instrument_id not in self.stores:
            return None

        return self.stores[instrument_id].curr_book

    def get_candle_history(self, instrument_id: str, timeframe: str = "1s", limit: int = 100) -> list[Candle]:
        """Get historical candles for an instrument and timeframe."""
        if instrument_id not in self.stores:
            return []

        store = self.stores[instrument_id]
        bars = store.get_bars(timeframe)

        return list(bars)[-limit:] if bars else []

    def get_volume_history(self, instrument_id: str, timeframe: str = "1s") -> list[float]:
        """Get volume history for RVOL calculation."""
        if instrument_id not in self.stores:
            return []

        store = self.stores[instrument_id]
        vol_history = store.get_vol_history(timeframe)

        return list(vol_history) if vol_history else []

    def get_last_price(self, instrument_id: str) -> Optional[float]:
        """Get the last known price for an instrument."""
        if instrument_id not in self.stores:
            return None

        store = self.stores[instrument_id]
        return store.last_price if store.last_price > 0 else None

    def reset_instrument(self, instrument_id: str) -> None:
        """Reset all data for an instrument."""
        if instrument_id in self.stores:
            del self.stores[instrument_id]
            logger.info(f"Reset data for instrument {instrument_id}")

    def get_instruments(self) -> list[str]:
        """Get list of all tracked instruments."""
        return list(self.stores.keys())

    def get_store_stats(self, instrument_id: str) -> dict[str, Any]:
        """Get statistics about an instrument's data store."""
        if instrument_id not in self.stores:
            return {}

        store = self.stores[instrument_id]
        stats = {
            "instrument_id": instrument_id,
            "last_price": store.last_price,
            "last_update": store.last_update.isoformat() if store.last_update else None,
            "has_current_book": store.curr_book is not None,
            "timeframes": {}
        }

        for timeframe, bars in store.bars.items():
            stats["timeframes"][timeframe] = {
                "bar_count": len(bars),
                "latest_ts": bars[-1].ts.isoformat() if bars else None,
                "latest_close": bars[-1].close if bars else None
            }

        return stats

    def normalize_candlesticks(self, payload: dict[str, Any]) -> NormalizationResult:
        """
        Normalize candlestick payload - compatibility method for engine.

        Args:
            payload: Raw payload dict from exchange

        Returns:
            NormalizationResult with normalized candle data
        """
        try:
            # Extract instrument_id from payload
            instrument_id = None
            if 'arg' in payload and 'instId' in payload['arg']:
                instrument_id = payload['arg']['instId']
            elif 'instId' in payload:
                instrument_id = payload['instId']

            if not instrument_id:
                return NormalizationResult.error("Cannot extract instrument_id from payload")

            # Process candlestick data directly without re-parsing
            return self._normalize_candle_tick(instrument_id, payload, self.get_or_create_store(instrument_id), "1m")

        except DataQualityError as e:
            # Convert data quality errors to NormalizationResult for compatibility
            logger.warning(f"Data quality error in normalize_candlesticks: {e}")
            return NormalizationResult.error(f"Data quality error: {e}")
        except GracefulDegradationError as e:
            # Handle graceful degradation by returning skipped result
            logger.info(f"Graceful degradation in normalize_candlesticks: {e}")
            return NormalizationResult.skipped(f"Graceful degradation: {e}")
        except Exception as e:
            logger.error(f"Error in normalize_candlesticks: {e}")
            return NormalizationResult.error(f"Normalization error: {e}")

    def normalize_orderbook(self, payload: dict[str, Any]) -> NormalizationResult:
        """
        Normalize order book payload - compatibility method for engine.

        Args:
            payload: Raw payload dict from exchange

        Returns:
            NormalizationResult with normalized order book data
        """
        try:
            # Extract instrument_id from payload
            instrument_id = None
            if 'arg' in payload and 'instId' in payload['arg']:
                instrument_id = payload['arg']['instId']
            elif 'instId' in payload:
                instrument_id = payload['instId']

            if not instrument_id:
                return NormalizationResult.error("Cannot extract instrument_id from payload")

            # Process order book data directly without re-parsing
            return self._normalize_book_tick(instrument_id, payload, self.get_or_create_store(instrument_id))

        except DataQualityError as e:
            # Convert data quality errors to NormalizationResult for compatibility
            logger.warning(f"Data quality error in normalize_orderbook: {e}")
            return NormalizationResult.error(f"Data quality error: {e}")
        except GracefulDegradationError as e:
            # Handle graceful degradation by returning skipped result
            logger.info(f"Graceful degradation in normalize_orderbook: {e}")
            return NormalizationResult.skipped(f"Graceful degradation: {e}")
        except Exception as e:
            logger.error(f"Error in normalize_orderbook: {e}")
            return NormalizationResult.error(f"Normalization error: {e}")
