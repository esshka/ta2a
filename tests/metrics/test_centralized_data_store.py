"""Tests for centralized rolling data store integration"""

import pytest
from datetime import datetime
from collections import deque
from ta2_app.metrics.calculator import MetricsCalculator
from ta2_app.data.models import InstrumentDataStore, Candle
from ta2_app.config.defaults import get_default_config, DataStoreParams


class TestCentralizedDataStore:
    """Test centralized rolling data store integration"""

    def test_data_store_with_config(self):
        """Test InstrumentDataStore uses configuration parameters"""
        config = DataStoreParams(
            bars_window_size=100,
            volume_window_size=10,
            atr_window_size=7
        )
        
        data_store = InstrumentDataStore(config=config)
        
        # Test bars window size
        bars = data_store.get_bars("1m")
        assert bars.maxlen == 100
        
        # Test volume window size 
        vol_history = data_store.get_vol_history("1m")
        assert vol_history.maxlen == 10

    def test_data_store_default_config(self):
        """Test InstrumentDataStore uses default configuration"""
        data_store = InstrumentDataStore()
        
        # Test default bars window size
        bars = data_store.get_bars("1m")
        assert bars.maxlen == 500
        
        # Test default volume window size
        vol_history = data_store.get_vol_history("1m")
        assert vol_history.maxlen == 20

    def test_metrics_calculator_with_data_store(self):
        """Test MetricsCalculator works with centralized data store"""
        config = get_default_config()
        calc = MetricsCalculator(config)
        data_store = InstrumentDataStore()
        
        # Create test candles
        candles = [
            Candle(
                ts=datetime.fromtimestamp(1000 + i),
                open=100 + i,
                high=110 + i,
                low=90 + i,
                close=105 + i,
                volume=1000 + i * 100,
                is_closed=True
            )
            for i in range(25)  # More than required for ATR (14) and RVOL (20)
        ]
        
        # Populate data store
        bars = data_store.get_bars("1m")
        vol_history = data_store.get_vol_history("1m")
        
        for candle in candles:
            bars.append(candle)
            vol_history.append(candle.volume)
        
        # Calculate metrics using the last candle
        current_candle = candles[-1]
        metrics = calc.calculate_metrics(current_candle, data_store, "1m")
        
        # Verify metrics are calculated
        assert metrics.atr is not None
        assert metrics.natr_pct is not None
        assert metrics.rvol is not None
        assert metrics.timestamp == current_candle.ts

    def test_metrics_calculator_insufficient_data(self):
        """Test MetricsCalculator with insufficient data"""
        config = get_default_config()
        calc = MetricsCalculator(config)
        data_store = InstrumentDataStore()
        
        # Create insufficient candles (less than required for ATR)
        candles = [
            Candle(
                ts=datetime.fromtimestamp(1000 + i),
                open=100,
                high=110,
                low=90,
                close=105,
                volume=1000,
                is_closed=True
            )
            for i in range(5)  # Less than required for ATR (14)
        ]
        
        # Populate data store
        bars = data_store.get_bars("1m")
        vol_history = data_store.get_vol_history("1m")
        
        for candle in candles:
            bars.append(candle)
            vol_history.append(candle.volume)
        
        # Calculate metrics
        current_candle = candles[-1]
        metrics = calc.calculate_metrics(current_candle, data_store, "1m")
        
        # Should have None for metrics requiring more data
        assert metrics.atr is None
        assert metrics.natr_pct is None
        assert metrics.rvol is None

    def test_is_warmed_up_with_data_store(self):
        """Test is_warmed_up method with data store"""
        config = get_default_config()
        calc = MetricsCalculator(config)
        data_store = InstrumentDataStore()
        
        # Start with empty data store
        assert not calc.is_warmed_up(data_store, "1m")
        
        # Add enough candles for ATR and volume history
        bars = data_store.get_bars("1m")
        vol_history = data_store.get_vol_history("1m")
        
        for i in range(25):  # More than max(ATR=14, RVOL=20)
            candle = Candle(
                ts=datetime.fromtimestamp(1000 + i),
                open=100,
                high=110,
                low=90,
                close=105,
                volume=1000,
                is_closed=True
            )
            bars.append(candle)
            vol_history.append(candle.volume)
        
        # Should be warmed up now
        assert calc.is_warmed_up(data_store, "1m")

    def test_multiple_timeframes(self):
        """Test data store with multiple timeframes"""
        data_store = InstrumentDataStore()
        
        # Test different timeframes
        bars_1m = data_store.get_bars("1m")
        bars_5m = data_store.get_bars("5m")
        
        # Should be separate deques
        assert bars_1m is not bars_5m
        
        # Test volume history for different timeframes
        vol_1m = data_store.get_vol_history("1m")
        vol_5m = data_store.get_vol_history("5m")
        
        assert vol_1m is not vol_5m
        
        # Add data to one timeframe
        candle = Candle(
            ts=datetime.fromtimestamp(1000),
            open=100,
            high=110,
            low=90,
            close=105,
            volume=1000,
            is_closed=True
        )
        bars_1m.append(candle)
        
        # Should only affect 1m timeframe
        assert len(bars_1m) == 1
        assert len(bars_5m) == 0

    def test_data_store_rolling_window(self):
        """Test rolling window behavior"""
        config = DataStoreParams(bars_window_size=3, volume_window_size=2)
        data_store = InstrumentDataStore(config=config)
        
        bars = data_store.get_bars("1m")
        vol_history = data_store.get_vol_history("1m")
        
        # Add more items than window size
        for i in range(5):
            candle = Candle(
                ts=datetime.fromtimestamp(1000 + i),
                open=100 + i,
                high=110 + i,
                low=90 + i,
                close=105 + i,
                volume=1000 + i,
                is_closed=True
            )
            bars.append(candle)
            vol_history.append(candle.volume)
        
        # Should only keep the last window_size items
        assert len(bars) == 3
        assert len(vol_history) == 2
        
        # Check that the latest items are retained
        assert bars[-1].close == 109  # Last candle close price
        assert vol_history[-1] == 1004  # Last volume