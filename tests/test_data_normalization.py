"""
Comprehensive tests for data normalization pipeline.

Tests cover parsing, validation, error handling, edge cases, and state management
for the complete data normalization pipeline.
"""

import pytest
import json
from datetime import datetime, UTC, timedelta
from unittest.mock import patch

from ta2_app.data.models import Candle, BookLevel, BookSnap, InstrumentDataStore, NormalizationResult
from ta2_app.data.parsers import (
    parse_candlestick_payload, 
    parse_orderbook_payload, 
    parse_json_payload,
    ParseError
)
from ta2_app.data.validators import (
    DataValidator, 
    ValidationError,
    is_duplicate_candle,
    should_skip_old_candle,
    validate_atr_spike_filter
)
from ta2_app.data.normalizer import DataNormalizer


class TestCandlestickParsing:
    """Test candlestick payload parsing."""
    
    def test_parse_valid_candlestick(self):
        """Test parsing valid candlestick payload."""
        payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "1"]
            ]
        }
        
        candles = parse_candlestick_payload(payload)
        
        assert len(candles) == 1
        candle = candles[0]
        assert candle.ts == datetime.fromtimestamp(1597026383.085, tz=UTC)
        assert candle.open == 3.721
        assert candle.high == 3.743
        assert candle.low == 3.677
        assert candle.close == 3.708
        assert candle.volume == 8422410
        assert candle.is_closed == True
    
    def test_parse_multiple_candles(self):
        """Test parsing multiple candles in one payload."""
        payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "1"],
                ["1597026384085", "3.708", "3.720", "3.700", "3.715", "1000000", "3000000", "3000000", "0"]
            ]
        }
        
        candles = parse_candlestick_payload(payload)
        
        assert len(candles) == 2
        assert candles[0].is_closed == True
        assert candles[1].is_closed == False
    
    def test_parse_invalid_candlestick_payload(self):
        """Test parsing invalid candlestick payloads."""
        # Missing data field
        with pytest.raises(ParseError, match="Missing 'data' field"):
            parse_candlestick_payload({"code": "0"})
        
        # Invalid data type
        with pytest.raises(ParseError, match="'data' field must be a list"):
            parse_candlestick_payload({"code": "0", "data": "invalid"})
        
        # Invalid candle data
        with pytest.raises(ParseError, match="Invalid candle data"):
            parse_candlestick_payload({"code": "0", "data": [["invalid"]]})
    
    def test_parse_invalid_candle_values(self):
        """Test parsing candles with invalid values."""
        # Negative price
        payload = {
            "code": "0",
            "data": [["1597026383085", "-3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "1"]]
        }
        
        with pytest.raises(ParseError, match="All prices must be positive"):
            parse_candlestick_payload(payload)
        
        # Invalid OHLC relationship
        payload = {
            "code": "0",
            "data": [["1597026383085", "3.721", "3.700", "3.750", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "1"]]
        }
        
        with pytest.raises(ParseError, match="High/low prices inconsistent"):
            parse_candlestick_payload(payload)


class TestOrderBookParsing:
    """Test order book payload parsing."""
    
    def test_parse_valid_orderbook(self):
        """Test parsing valid order book payload."""
        payload = {
            "code": "0",
            "msg": "",
            "data": [{
                "asks": [["41006.8", "0.60038921", "0", "1"], ["41007.0", "0.30000000", "0", "1"]],
                "bids": [["41006.3", "0.30178218", "0", "2"], ["41006.0", "0.40000000", "0", "2"]],
                "ts": "1629966436396"
            }]
        }
        
        book = parse_orderbook_payload(payload)
        
        assert book.ts == datetime.fromtimestamp(1629966436.396, tz=UTC)
        assert len(book.asks) == 2
        assert len(book.bids) == 2
        assert book.asks[0].price == 41006.8
        assert book.bids[0].price == 41006.3
        assert book.bid_price == 41006.3
        assert book.ask_price == 41006.8
        assert book.mid_price == (41006.3 + 41006.8) / 2
    
    def test_parse_orderbook_with_zero_sizes(self):
        """Test parsing order book with zero-size levels (should be filtered)."""
        payload = {
            "code": "0",
            "data": [{
                "asks": [["41006.8", "0.0", "0", "1"], ["41007.0", "0.30000000", "0", "1"]],
                "bids": [["41006.3", "0.30178218", "0", "2"]],
                "ts": "1629966436396"
            }]
        }
        
        book = parse_orderbook_payload(payload)
        
        assert len(book.asks) == 1  # Zero-size ask filtered out
        assert book.asks[0].price == 41007.0
    
    def test_parse_invalid_orderbook_payload(self):
        """Test parsing invalid order book payloads."""
        # Missing timestamp
        with pytest.raises(ParseError, match="Missing 'ts' field"):
            parse_orderbook_payload({"code": "0", "data": [{"asks": [], "bids": []}]})
        
        # Invalid spread
        payload = {
            "code": "0",
            "data": [{
                "asks": [["41006.0", "0.60038921", "0", "1"]],
                "bids": [["41006.5", "0.30178218", "0", "2"]],
                "ts": "1629966436396"
            }]
        }
        
        with pytest.raises(ParseError, match="Invalid spread"):
            parse_orderbook_payload(payload)


class TestDataValidation:
    """Test data validation framework."""
    
    def test_validate_valid_candle(self):
        """Test validation of valid candle."""
        validator = DataValidator()
        candle = Candle(
            ts=datetime.now(UTC),
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=1000.0,
            is_closed=True
        )
        
        # Should not raise exception
        validator.validate_candle(candle)
    
    def test_validate_invalid_candle_prices(self):
        """Test validation of candle with invalid prices."""
        validator = DataValidator()
        
        # Negative price
        with pytest.raises(ValidationError, match="All candle prices must be positive"):
            candle = Candle(
                ts=datetime.now(UTC),
                open=-100.0,
                high=105.0,
                low=95.0,
                close=102.0,
                volume=1000.0,
                is_closed=True
            )
            validator.validate_candle(candle)
        
        # Invalid OHLC relationship
        with pytest.raises(ValidationError, match="High .* must be"):
            candle = Candle(
                ts=datetime.now(UTC),
                open=100.0,
                high=95.0,  # High < open
                low=95.0,
                close=102.0,
                volume=1000.0,
                is_closed=True
            )
            validator.validate_candle(candle)
    
    def test_validate_old_candle(self):
        """Test validation of old candle."""
        validator = DataValidator({"max_age_seconds": 60})
        
        old_candle = Candle(
            ts=datetime.now(UTC) - timedelta(seconds=120),  # 2 minutes ago
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=1000.0,
            is_closed=True
        )
        
        with pytest.raises(ValidationError, match="Candle too old"):
            validator.validate_candle(old_candle)
    
    def test_validate_valid_book(self):
        """Test validation of valid order book."""
        validator = DataValidator()
        book = BookSnap(
            ts=datetime.now(UTC),
            bids=[BookLevel(100.0, 10.0), BookLevel(99.0, 5.0)],
            asks=[BookLevel(101.0, 8.0), BookLevel(102.0, 12.0)]
        )
        
        # Should not raise exception
        validator.validate_book_snap(book)
    
    def test_validate_invalid_book_ordering(self):
        """Test validation of book with invalid level ordering."""
        validator = DataValidator()
        
        # Invalid bid ordering (should be descending)
        with pytest.raises(ValidationError, match="Invalid bids ordering"):
            book = BookSnap(
                ts=datetime.now(UTC),
                bids=[BookLevel(99.0, 10.0), BookLevel(100.0, 5.0)],  # Wrong order
                asks=[BookLevel(101.0, 8.0)]
            )
            validator.validate_book_snap(book)
    
    def test_duplicate_candle_detection(self):
        """Test duplicate candle detection."""
        store = InstrumentDataStore()
        ts = datetime.now(UTC)
        
        candle1 = Candle(ts=ts, open=100.0, high=105.0, low=95.0, close=102.0, volume=1000.0, is_closed=True)
        candle2 = Candle(ts=ts, open=100.0, high=105.0, low=95.0, close=103.0, volume=1100.0, is_closed=True)
        
        # First candle should not be duplicate
        assert not is_duplicate_candle(candle1, store, "1s")
        
        # Add first candle to store
        store.get_bars("1s").append(candle1)
        
        # Second candle with same timestamp should be duplicate
        assert is_duplicate_candle(candle2, store, "1s")
    
    def test_atr_spike_filter(self):
        """Test ATR-based spike filtering."""
        # Normal price move within ATR bounds
        assert validate_atr_spike_filter(102.0, 100.0, 5.0, 2.0) == True
        
        # Large price move beyond ATR bounds
        assert validate_atr_spike_filter(120.0, 100.0, 5.0, 2.0) == False
        
        # Fallback to percentage filter when no ATR
        assert validate_atr_spike_filter(102.0, 100.0, None, 2.0) == True
        assert validate_atr_spike_filter(200.0, 100.0, None, 2.0) == False


class TestDataNormalizer:
    """Test main data normalizer."""
    
    def test_normalize_candle_tick(self):
        """Test normalizing candlestick tick."""
        normalizer = DataNormalizer({"max_age_seconds": 86400})  # 24 hours
        
        # Use current timestamp 
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        raw_data = json.dumps({
            "code": "0",
            "msg": "",
            "data": [
                [str(current_ts), "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "1"]
            ]
        })
        
        result = normalizer.normalize_tick("BTC-USD", raw_data, "candle")
        
        assert result.success == True
        assert result.candle is not None
        assert result.candle.close == 3.708
        assert result.last_price_updated == True
        assert result.new_last_price == 3.708
    
    def test_normalize_book_tick(self):
        """Test normalizing order book tick."""
        normalizer = DataNormalizer({"max_age_seconds": 86400})  # 24 hours
        
        # Use current timestamp
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        raw_data = json.dumps({
            "code": "0",
            "msg": "",
            "data": [{
                "asks": [["41006.8", "0.60038921", "0", "1"]],
                "bids": [["41006.3", "0.30178218", "0", "2"]],
                "ts": str(current_ts)
            }]
        })
        
        result = normalizer.normalize_tick("BTC-USD", raw_data, "book")
        
        assert result.success == True
        assert result.book_snap is not None
        assert result.book_snap.mid_price == (41006.3 + 41006.8) / 2
        assert result.last_price_updated == True
    
    def test_normalize_invalid_json(self):
        """Test normalizing invalid JSON data."""
        normalizer = DataNormalizer()
        
        result = normalizer.normalize_tick("BTC-USD", "{invalid json", "candle")
        
        assert result.success == False
        assert "Parse error" in result.error_msg
    
    def test_normalize_okx_error_response(self):
        """Test normalizing OKX error response."""
        normalizer = DataNormalizer()
        
        raw_data = json.dumps({
            "code": "50001",
            "msg": "Error message",
            "data": []
        })
        
        result = normalizer.normalize_tick("BTC-USD", raw_data, "candle")
        
        assert result.success == False
        assert "OKX API error" in result.error_msg
    
    def test_get_latest_data(self):
        """Test getting latest candle and book data."""
        normalizer = DataNormalizer({"max_age_seconds": 86400})  # 24 hours
        
        # Add candle data
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        candle_data = json.dumps({
            "code": "0",
            "data": [[str(current_ts), "41000.0", "41010.0", "40990.0", "41005.0", "8422410", "22698348.04828491", "12698348.04828491", "1"]]
        })
        
        normalizer.normalize_tick("BTC-USD", candle_data, "candle")
        
        # Add book data
        current_ts2 = int(datetime.now(UTC).timestamp() * 1000)
        book_data = json.dumps({
            "code": "0",
            "data": [{
                "asks": [["41006.8", "0.60038921", "0", "1"]],
                "bids": [["41006.3", "0.30178218", "0", "2"]],
                "ts": str(current_ts2)
            }]
        })
        
        normalizer.normalize_tick("BTC-USD", book_data, "book")
        
        # Test retrieval methods
        latest_candle = normalizer.get_latest_candle("BTC-USD")
        latest_book = normalizer.get_latest_book("BTC-USD")
        last_price = normalizer.get_last_price("BTC-USD")
        
        assert latest_candle is not None
        assert latest_candle.close == 41005.0
        assert latest_book is not None
        assert latest_book.mid_price == (41006.3 + 41006.8) / 2
        assert last_price == (41006.3 + 41006.8) / 2  # Updated by book
    
    def test_candle_history_and_volume(self):
        """Test candle history and volume tracking."""
        normalizer = DataNormalizer({"max_age_seconds": 86400})  # 24 hours
        
        # Add multiple candles
        base_ts = int(datetime.now(UTC).timestamp() * 1000)
        for i in range(5):
            candle_data = json.dumps({
                "code": "0",
                "data": [[str(base_ts + i * 1000), "3.721", "3.743", "3.677", f"3.70{i}", f"842241{i}", "22698348.04828491", "12698348.04828491", "1"]]
            })
            normalizer.normalize_tick("BTC-USD", candle_data, "candle")
        
        history = normalizer.get_candle_history("BTC-USD", limit=3)
        vol_history = normalizer.get_volume_history("BTC-USD")
        
        assert len(history) == 3  # Limited to 3
        assert len(vol_history) == 5  # All volumes
        assert history[-1].close == 3.704  # Latest candle
    
    def test_instrument_management(self):
        """Test instrument management methods."""
        normalizer = DataNormalizer({"max_age_seconds": 86400})  # 24 hours
        
        # Add data for multiple instruments
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        candle_data = json.dumps({
            "code": "0",
            "data": [[str(current_ts), "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "1"]]
        })
        
        normalizer.normalize_tick("BTC-USD", candle_data, "candle")
        normalizer.normalize_tick("ETH-USD", candle_data, "candle")
        
        instruments = normalizer.get_instruments()
        assert "BTC-USD" in instruments
        assert "ETH-USD" in instruments
        
        # Test stats
        stats = normalizer.get_store_stats("BTC-USD")
        assert stats["instrument_id"] == "BTC-USD"
        assert stats["last_price"] == 3.708
        assert "1s" in stats["timeframes"]
        
        # Test reset
        normalizer.reset_instrument("BTC-USD")
        instruments = normalizer.get_instruments()
        assert "BTC-USD" not in instruments
        assert "ETH-USD" in instruments


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_payloads(self):
        """Test handling of empty payloads."""
        normalizer = DataNormalizer()
        
        # Empty candle data
        empty_candle = json.dumps({"code": "0", "data": []})
        result = normalizer.normalize_tick("BTC-USD", empty_candle, "candle")
        assert result.success == True
        assert result.skipped_reason == "No candles in payload"
    
    def test_out_of_order_candles(self):
        """Test handling of out-of-order candles."""
        normalizer = DataNormalizer({"max_age_seconds": 86400})  # 24 hours
        
        # Add newer candle first
        base_ts = int(datetime.now(UTC).timestamp() * 1000)
        newer_candle = json.dumps({
            "code": "0",
            "data": [[str(base_ts + 1000), "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "1"]]
        })
        normalizer.normalize_tick("BTC-USD", newer_candle, "candle")
        
        # Try to add older candle (should be skipped)
        older_candle = json.dumps({
            "code": "0",
            "data": [[str(base_ts), "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "1"]]
        })
        result = normalizer.normalize_tick("BTC-USD", older_candle, "candle")
        assert result.success == True
        assert result.skipped_reason == "Old candle"
    
    def test_malformed_data_recovery(self):
        """Test system recovery from malformed data."""
        normalizer = DataNormalizer()
        
        # Process malformed data
        malformed = json.dumps({"code": "0", "data": [["invalid", "data"]]})
        result = normalizer.normalize_tick("BTC-USD", malformed, "candle")
        assert result.success == False
        
        # System should recover and process valid data
        valid_data = json.dumps({
            "code": "0",
            "data": [["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "1"]]
        })
        result = normalizer.normalize_tick("BTC-USD", valid_data, "candle")
        assert result.success == True
    
    @patch('ta2_app.data.normalizer.logger')
    def test_logging_behavior(self, mock_logger):
        """Test that appropriate logging occurs."""
        normalizer = DataNormalizer({"max_age_seconds": 86400})
        
        # Test error logging
        invalid_data = "{invalid json"
        normalizer.normalize_tick("BTC-USD", invalid_data, "candle")
        mock_logger.warning.assert_called()
        
        # Test debug logging for valid data
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        valid_data = json.dumps({
            "code": "0",
            "data": [[str(current_ts), "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04828491", "12698348.04828491", "1"]]
        })
        normalizer.normalize_tick("BTC-USD", valid_data, "candle")
        mock_logger.debug.assert_called()


class TestSpikeFilteringIntegration:
    """Test spike filtering integration with data normalizer."""
    
    def test_spike_filtering_enabled_by_default(self):
        """Test that spike filtering is enabled by default."""
        normalizer = DataNormalizer()
        assert normalizer.enable_spike_filter == True
        assert normalizer.spike_filter_atr_mult == 10.0
    
    def test_spike_filtering_configuration(self):
        """Test spike filtering configuration."""
        config = {
            "spike_filter": {
                "enable": False,
                "atr_multiplier": 5.0
            }
        }
        normalizer = DataNormalizer(config)
        assert normalizer.enable_spike_filter == False
        assert normalizer.spike_filter_atr_mult == 5.0
    
    def test_spike_filtering_with_atr_context(self):
        """Test spike filtering with ATR context from data store."""
        normalizer = DataNormalizer()
        
        # Add historical data to build ATR context
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        
        # Add 15 normal candles to build ATR
        for i in range(15):
            ts = current_ts - (15 - i) * 60000  # 1 minute intervals
            base_price = 100.0 + (i * 0.1)  # Slowly trending up
            candle_data = json.dumps({
                "code": "0",
                "data": [[str(ts), str(base_price), str(base_price + 0.5), str(base_price - 0.5), str(base_price + 0.2), "100000", "1000000", "1000000", "1"]]
            })
            normalizer.normalize_tick("BTC-USD", candle_data, "candle", "1s")
        
        # Now try to add a spike that should be filtered
        spike_ts = current_ts + 60000
        spike_data = json.dumps({
            "code": "0", 
            "data": [[str(spike_ts), "101.5", "200.0", "101.0", "180.0", "100000", "1000000", "1000000", "1"]]  # Massive spike
        })
        
        result = normalizer.normalize_tick("BTC-USD", spike_data, "candle", "1s")
        assert result.success == False
        assert "Price spike filtered" in result.error_msg
    
    def test_spike_filtering_fallback_to_percentage(self):
        """Test spike filtering falls back to percentage filter when no ATR."""
        normalizer = DataNormalizer()
        
        # Add one normal candle
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        normal_data = json.dumps({
            "code": "0",
            "data": [[str(current_ts), "100.0", "100.5", "99.5", "100.2", "100000", "1000000", "1000000", "1"]]
        })
        normalizer.normalize_tick("BTC-USD", normal_data, "candle", "1s")
        
        # Now try to add a spike that exceeds 50% threshold
        spike_ts = current_ts + 60000
        spike_data = json.dumps({
            "code": "0",
            "data": [[str(spike_ts), "100.2", "200.0", "100.0", "180.0", "100000", "1000000", "1000000", "1"]]  # 80% spike
        })
        
        result = normalizer.normalize_tick("BTC-USD", spike_data, "candle", "1s")
        assert result.success == False
        assert "Price spike filtered" in result.error_msg
    
    def test_spike_filtering_allows_normal_volatility(self):
        """Test spike filtering allows normal volatility within bounds."""
        normalizer = DataNormalizer()
        
        # Add historical data
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        for i in range(15):
            ts = current_ts - (15 - i) * 60000
            base_price = 100.0 + (i * 0.1)
            candle_data = json.dumps({
                "code": "0",
                "data": [[str(ts), str(base_price), str(base_price + 0.5), str(base_price - 0.5), str(base_price + 0.2), "100000", "1000000", "1000000", "1"]]
            })
            normalizer.normalize_tick("BTC-USD", candle_data, "candle", "1s")
        
        # Add a normal volatile candle (within ATR bounds)
        normal_ts = current_ts + 60000
        normal_data = json.dumps({
            "code": "0",
            "data": [[str(normal_ts), "101.5", "102.0", "101.0", "101.8", "100000", "1000000", "1000000", "1"]]  # Normal volatility
        })
        
        result = normalizer.normalize_tick("BTC-USD", normal_data, "candle", "1s")
        assert result.success == True
        assert result.candle is not None
        assert result.candle.close == 101.8
    
    def test_spike_filtering_disabled(self):
        """Test that spike filtering can be disabled."""
        config = {"spike_filter": {"enable": False}}
        normalizer = DataNormalizer(config)
        
        # Add one normal candle
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        normal_data = json.dumps({
            "code": "0",
            "data": [[str(current_ts), "100.0", "100.5", "99.5", "100.2", "100000", "1000000", "1000000", "1"]]
        })
        normalizer.normalize_tick("BTC-USD", normal_data, "candle", "1s")
        
        # Add a massive spike that would normally be filtered
        spike_ts = current_ts + 60000
        spike_data = json.dumps({
            "code": "0",
            "data": [[str(spike_ts), "100.2", "500.0", "100.0", "450.0", "100000", "1000000", "1000000", "1"]]
        })
        
        result = normalizer.normalize_tick("BTC-USD", spike_data, "candle", "1s")
        assert result.success == True  # Should pass through when disabled
        assert result.candle is not None
        assert result.candle.close == 450.0
    
    def test_spike_filtering_metrics_tracking(self):
        """Test that spike filtering rejections are tracked in metrics."""
        normalizer = DataNormalizer()
        
        # Add some historical data
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        normal_data = json.dumps({
            "code": "0",
            "data": [[str(current_ts), "100.0", "100.5", "99.5", "100.2", "100000", "1000000", "1000000", "1"]]
        })
        normalizer.normalize_tick("BTC-USD", normal_data, "candle", "1s")
        
        # Add a spike that should be filtered
        spike_ts = current_ts + 60000
        spike_data = json.dumps({
            "code": "0",
            "data": [[str(spike_ts), "100.2", "300.0", "100.0", "280.0", "100000", "1000000", "1000000", "1"]]
        })
        
        result = normalizer.normalize_tick("BTC-USD", spike_data, "candle", "1s")
        assert result.success == False
        assert "Price spike filtered" in result.error_msg
        
        # TODO: Add metrics verification when metrics tracking is implemented
    
    def test_spike_filtering_with_multiple_instruments(self):
        """Test spike filtering works independently for different instruments."""
        normalizer = DataNormalizer()
        
        current_ts = int(datetime.now(UTC).timestamp() * 1000)
        
        # Add normal data for BTC-USD
        btc_data = json.dumps({
            "code": "0",
            "data": [[str(current_ts), "40000.0", "40100.0", "39900.0", "40050.0", "100000", "1000000", "1000000", "1"]]
        })
        normalizer.normalize_tick("BTC-USD", btc_data, "candle", "1s")
        
        # Add normal data for ETH-USD
        eth_data = json.dumps({
            "code": "0", 
            "data": [[str(current_ts), "2500.0", "2520.0", "2480.0", "2510.0", "100000", "1000000", "1000000", "1"]]
        })
        normalizer.normalize_tick("ETH-USD", eth_data, "candle", "1s")
        
        # Add spike for BTC-USD (should be filtered)
        btc_spike_data = json.dumps({
            "code": "0",
            "data": [[str(current_ts + 60000), "40050.0", "80000.0", "40000.0", "75000.0", "100000", "1000000", "1000000", "1"]]
        })
        btc_result = normalizer.normalize_tick("BTC-USD", btc_spike_data, "candle", "1s")
        assert btc_result.success == False
        
        # Add normal volatility for ETH-USD (should pass)
        eth_normal_data = json.dumps({
            "code": "0",
            "data": [[str(current_ts + 60000), "2510.0", "2540.0", "2490.0", "2530.0", "100000", "1000000", "1000000", "1"]]
        })
        eth_result = normalizer.normalize_tick("ETH-USD", eth_normal_data, "candle", "1s")
        assert eth_result.success == True
        assert eth_result.candle.close == 2530.0


if __name__ == "__main__":
    pytest.main([__file__])