"""Tests for MetricsCalculator integration"""

import pytest
from datetime import datetime
from ta2_app.metrics.calculator import MetricsCalculator
from ta2_app.data.models import InstrumentDataStore, Candle
from ta2_app.metrics.orderbook import BookLevel, BookSnap
from ta2_app.config.defaults import get_default_config


class TestMetricsCalculator:
    """Test MetricsCalculator integration"""
    
    def test_calculator_initialization(self):
        """Test MetricsCalculator initialization"""
        calc = MetricsCalculator()
        
        assert calc.config is not None
        assert calc.atr_calculator is not None
        assert calc.rvol_calculator is not None
        assert calc.orderbook_analyzer is not None
        assert calc.last_candle is None
        assert calc.last_metrics is None
    
    def test_calculator_with_custom_config(self):
        """Test MetricsCalculator with custom config"""
        config = get_default_config()
        calc = MetricsCalculator(config)
        
        assert calc.config is config
        assert calc.atr_calculator.period == config.atr.period
        assert calc.rvol_calculator.period == config.volume.rvol_period
    
    def test_calculate_metrics_candle_only(self):
        """Test metrics calculation with candle only"""
        calc = MetricsCalculator()
        data_store = InstrumentDataStore()
        
        candle = Candle(
            ts=datetime.fromtimestamp(1000),
            open=100,
            high=110,
            low=90,
            close=105,
            volume=1500,
            is_closed=True
        )
        
        # Add some historical data for calculations
        bars = data_store.get_bars("1m")
        vol_history = data_store.get_vol_history("1m")
        
        # Add enough data for calculations
        for i in range(25):
            hist_candle = Candle(
                ts=datetime.fromtimestamp(900 + i),
                open=95 + i,
                high=105 + i,
                low=85 + i,
                close=100 + i,
                volume=1000 + i * 50,
                is_closed=True
            )
            bars.append(hist_candle)
            vol_history.append(hist_candle.volume)
        
        metrics = calc.calculate_metrics(candle, data_store)
        
        # Check basic structure
        assert metrics.timestamp == datetime.fromtimestamp(1000)
        assert metrics.atr is not None  # Should have enough data now
        assert metrics.natr_pct is not None
        assert metrics.rvol is not None
        assert metrics.candle_structure is not None
        assert metrics.pinbar in ['bullish', 'bearish', None]
        
        # Order book metrics should be None
        assert metrics.ob_imbalance_long is None
        assert metrics.ob_imbalance_short is None
        assert metrics.ob_sweep_detected is False
        assert metrics.ob_sweep_side is None
    
    def test_calculate_metrics_with_orderbook(self):
        """Test metrics calculation with order book"""
        calc = MetricsCalculator()
        
        candle = Candle(
            ts=1000,
            open=100,
            high=110,
            low=90,
            close=105,
            volume=1500,
            is_closed=True
        )
        
        book = BookSnap(
            ts=1000,
            bids=[BookLevel(99.0, 10.0), BookLevel(98.0, 8.0)],
            asks=[BookLevel(101.0, 10.0), BookLevel(102.0, 8.0)]
        )
        
        metrics = calc.calculate_metrics(candle, book)
        
        # Order book metrics should be populated
        assert metrics.ob_imbalance_long is not None
        assert metrics.ob_imbalance_short is not None
        assert isinstance(metrics.ob_sweep_detected, bool)
    
    def test_calculate_metrics_warmup_period(self):
        """Test metrics calculation during warmup period"""
        calc = MetricsCalculator()
        
        # Create enough candles for warmup
        candles = []
        for i in range(25):  # More than both ATR and RVOL periods
            candles.append(Candle(
                ts=1000 + i * 60,
                open=100 + i * 0.1,
                high=110 + i * 0.1,
                low=90 + i * 0.1,
                close=105 + i * 0.1,
                volume=1000 + i * 10,
                is_closed=True
            ))
        
        metrics_list = []
        for candle in candles:
            metrics = calc.calculate_metrics(candle)
            metrics_list.append(metrics)
        
        # Early metrics should have None values
        assert metrics_list[0].atr is None
        assert metrics_list[0].rvol is None
        
        # Later metrics should have values
        assert metrics_list[-1].atr is not None
        assert metrics_list[-1].rvol is not None
        assert metrics_list[-1].has_sufficient_data()
    
    def test_get_last_metrics(self):
        """Test get_last_metrics method"""
        calc = MetricsCalculator()
        
        # Initially no metrics
        assert calc.get_last_metrics() is None
        
        # After calculation
        candle = Candle(1000, 100, 110, 90, 105, 1500, True)
        metrics = calc.calculate_metrics(candle)
        
        assert calc.get_last_metrics() is metrics
    
    def test_reset_functionality(self):
        """Test reset functionality"""
        calc = MetricsCalculator()
        
        # Add some data
        candle = Candle(1000, 100, 110, 90, 105, 1500, True)
        calc.calculate_metrics(candle)
        
        # Verify state exists
        assert calc.last_candle is not None
        assert calc.last_metrics is not None
        assert len(calc.atr_calculator.true_ranges) > 0
        assert len(calc.rvol_calculator.volume_history) > 0
        
        # Reset
        calc.reset()
        
        # Verify state cleared
        assert calc.last_candle is None
        assert calc.last_metrics is None
        assert len(calc.atr_calculator.true_ranges) == 0
        assert len(calc.rvol_calculator.volume_history) == 0
    
    def test_update_config(self):
        """Test update_config functionality"""
        calc = MetricsCalculator()
        
        # Add some data
        candle = Candle(1000, 100, 110, 90, 105, 1500, True)
        calc.calculate_metrics(candle)
        
        # Update config
        new_config = get_default_config()
        calc.update_config(new_config)
        
        # Verify config updated and state reset
        assert calc.config is new_config
        assert calc.last_candle is None
        assert calc.last_metrics is None
    
    def test_get_warmup_period(self):
        """Test get_warmup_period method"""
        calc = MetricsCalculator()
        
        warmup_period = calc.get_warmup_period()
        expected_period = max(calc.config.atr.period, calc.config.volume.rvol_period)
        
        assert warmup_period == expected_period
    
    def test_is_warmed_up(self):
        """Test is_warmed_up method"""
        calc = MetricsCalculator()
        
        # Initially not warmed up
        assert calc.is_warmed_up() is False
        
        # Add candles until warmed up
        warmup_period = calc.get_warmup_period()
        for i in range(warmup_period):
            candle = Candle(
                ts=1000 + i * 60,
                open=100,
                high=110,
                low=90,
                close=105,
                volume=1000,
                is_closed=True
            )
            calc.calculate_metrics(candle)
        
        # Should be warmed up now
        assert calc.is_warmed_up() is True
    
    def test_metrics_snapshot_scoring(self):
        """Test MetricsSnapshot scoring methods"""
        calc = MetricsCalculator()
        
        # Create enough candles for full metrics
        candles = []
        for i in range(25):
            candles.append(Candle(
                ts=1000 + i * 60,
                open=100,
                high=110,
                low=90,
                close=105,
                volume=1000 + i * 50,  # Increasing volume
                is_closed=True
            ))
        
        # Get final metrics
        final_metrics = None
        for candle in candles:
            final_metrics = calc.calculate_metrics(candle)
        
        # Test scoring methods
        assert final_metrics.has_sufficient_data()
        
        volatility_score = final_metrics.get_volatility_score()
        assert 0 <= volatility_score <= 100
        
        volume_score = final_metrics.get_volume_score()
        assert 0 <= volume_score <= 100
        
        momentum_score = final_metrics.get_momentum_score()
        assert 0 <= momentum_score <= 100
        
        liquidity_score = final_metrics.get_liquidity_score()
        assert 0 <= liquidity_score <= 100
        
        composite_score = final_metrics.get_composite_score()
        assert 0 <= composite_score <= 100
    
    def test_metrics_with_sweep_detection(self):
        """Test metrics with order book sweep detection"""
        calc = MetricsCalculator()
        
        candle = Candle(1000, 100, 110, 90, 105, 1500, True)
        
        # First book - balanced
        book1 = BookSnap(
            ts=1000,
            bids=[BookLevel(99.0, 10.0)],
            asks=[BookLevel(101.0, 10.0)]
        )
        
        metrics1 = calc.calculate_metrics(candle, book1)
        assert metrics1.ob_sweep_detected is False
        
        # Second book - sweep detected
        book2 = BookSnap(
            ts=2000,
            bids=[BookLevel(99.0, 2.0)],  # Depleted
            asks=[BookLevel(101.0, 10.0)]
        )
        
        candle2 = Candle(2000, 105, 115, 95, 110, 1600, True)
        metrics2 = calc.calculate_metrics(candle2, book2)
        
        # Should detect sweep
        assert metrics2.ob_sweep_detected is True
        assert metrics2.ob_sweep_side == 'bid'
        
        # Composite score should include sweep bonus
        composite_score = metrics2.get_composite_score()
        assert composite_score >= 0  # Should have sweep bonus if other conditions met
    
    def test_edge_cases(self):
        """Test edge cases and error conditions"""
        calc = MetricsCalculator()
        
        # Zero range candle
        zero_candle = Candle(1000, 100, 100, 100, 100, 1000, True)
        metrics = calc.calculate_metrics(zero_candle)
        assert metrics.candle_structure.range_value == 0
        
        # Empty order book
        empty_book = BookSnap(1000, [], [])
        metrics = calc.calculate_metrics(zero_candle, empty_book)
        assert metrics.ob_imbalance_long is not None  # Should handle gracefully
        
        # Very small values
        tiny_candle = Candle(1000, 0.001, 0.002, 0.0005, 0.0015, 0.1, True)
        metrics = calc.calculate_metrics(tiny_candle)
        assert metrics.candle_structure is not None