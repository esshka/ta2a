"""Tests for ATR and NATR calculations"""

import pytest
from ta2_app.metrics.atr import Candle, calculate_atr, calculate_natr, calculate_true_range, ATRCalculator


class TestTrueRange:
    """Test True Range calculation"""
    
    def test_true_range_first_candle(self):
        """Test TR calculation for first candle (no previous close)"""
        candle = Candle(ts=1000, open=100, high=105, low=95, close=102, volume=1000, is_closed=True)
        tr = calculate_true_range(candle)
        assert tr == 10.0  # high - low
    
    def test_true_range_with_previous(self):
        """Test TR calculation with previous close"""
        prev_candle = Candle(ts=1000, open=100, high=105, low=95, close=102, volume=1000, is_closed=True)
        curr_candle = Candle(ts=2000, open=103, high=108, low=101, close=107, volume=1200, is_closed=True)
        
        tr = calculate_true_range(curr_candle, prev_candle)
        # max(108-101, abs(108-102), abs(101-102)) = max(7, 6, 1) = 7
        assert tr == 7.0
    
    def test_true_range_gap_up(self):
        """Test TR calculation with gap up"""
        prev_candle = Candle(ts=1000, open=100, high=105, low=95, close=102, volume=1000, is_closed=True)
        curr_candle = Candle(ts=2000, open=110, high=115, low=108, close=112, volume=1200, is_closed=True)
        
        tr = calculate_true_range(curr_candle, prev_candle)
        # max(115-108, abs(115-102), abs(108-102)) = max(7, 13, 6) = 13
        assert tr == 13.0
    
    def test_true_range_gap_down(self):
        """Test TR calculation with gap down"""
        prev_candle = Candle(ts=1000, open=100, high=105, low=95, close=102, volume=1000, is_closed=True)
        curr_candle = Candle(ts=2000, open=90, high=93, low=88, close=91, volume=1200, is_closed=True)
        
        tr = calculate_true_range(curr_candle, prev_candle)
        # max(93-88, abs(93-102), abs(88-102)) = max(5, 9, 14) = 14
        assert tr == 14.0


class TestATRCalculation:
    """Test ATR calculation"""
    
    def create_test_candles(self, count=20):
        """Create test candles with predictable TR values"""
        candles = []
        for i in range(count):
            candles.append(Candle(
                ts=1000 + i * 60,
                open=100 + i,
                high=105 + i,
                low=95 + i,
                close=102 + i,
                volume=1000,
                is_closed=True
            ))
        return candles
    
    def test_atr_insufficient_data(self):
        """Test ATR with insufficient data"""
        candles = self.create_test_candles(5)
        atr = calculate_atr(candles, period=14)
        assert atr is None
    
    def test_atr_exact_period(self):
        """Test ATR with exact period"""
        candles = self.create_test_candles(14)
        atr = calculate_atr(candles, period=14)
        assert atr is not None
        assert atr > 0
    
    def test_atr_more_than_period(self):
        """Test ATR with more data than period"""
        candles = self.create_test_candles(20)
        atr = calculate_atr(candles, period=14)
        assert atr is not None
        assert atr > 0
    
    def test_atr_simple_case(self):
        """Test ATR with simple predictable case"""
        candles = []
        # Create candles with TR = 20 for all (high-low range)
        for i in range(14):
            candles.append(Candle(
                ts=1000 + i * 60,
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1000,
                is_closed=True
            ))
        
        atr = calculate_atr(candles, period=14)
        assert atr == 20.0  # All candles have same OHLC so TR = high-low = 20


class TestNATRCalculation:
    """Test NATR calculation"""
    
    def test_natr_calculation(self):
        """Test NATR calculation"""
        atr = 5.0
        current_price = 100.0
        natr = calculate_natr(atr, current_price)
        assert natr == 5.0  # 100 * 5.0 / 100.0
    
    def test_natr_zero_price(self):
        """Test NATR with zero price"""
        atr = 5.0
        current_price = 0.0
        natr = calculate_natr(atr, current_price)
        assert natr == 0.0
    
    def test_natr_negative_price(self):
        """Test NATR with negative price"""
        atr = 5.0
        current_price = -100.0
        natr = calculate_natr(atr, current_price)
        assert natr == 0.0


class TestATRCalculator:
    """Test ATRCalculator class"""
    
    def test_atr_calculator_init(self):
        """Test ATRCalculator initialization"""
        calc = ATRCalculator(period=10)
        assert calc.period == 10
        assert len(calc.true_ranges) == 0
        assert calc.last_close is None
    
    def test_atr_calculator_update_first_candle(self):
        """Test ATRCalculator update with first candle"""
        calc = ATRCalculator(period=3)
        candle = Candle(ts=1000, open=100, high=105, low=95, close=102, volume=1000, is_closed=True)
        
        atr = calc.update(candle)
        assert atr is None  # Not enough data yet
        assert calc.last_close == 102
        assert len(calc.true_ranges) == 1
    
    def test_atr_calculator_warmup(self):
        """Test ATRCalculator warmup period"""
        calc = ATRCalculator(period=3)
        candles = [
            Candle(ts=1000, open=100, high=105, low=95, close=102, volume=1000, is_closed=True),
            Candle(ts=2000, open=102, high=107, low=99, close=104, volume=1000, is_closed=True),
            Candle(ts=3000, open=104, high=109, low=101, close=106, volume=1000, is_closed=True),
        ]
        
        results = []
        for candle in candles:
            atr = calc.update(candle)
            results.append(atr)
        
        # First two should be None, third should have ATR
        assert results[0] is None
        assert results[1] is None
        assert results[2] is not None
        assert results[2] > 0
    
    def test_atr_calculator_rolling_window(self):
        """Test ATRCalculator maintains rolling window"""
        calc = ATRCalculator(period=3)
        
        # Add 5 candles
        for i in range(5):
            candle = Candle(
                ts=1000 + i * 60,
                open=100 + i,
                high=105 + i,
                low=95 + i,
                close=102 + i,
                volume=1000,
                is_closed=True
            )
            calc.update(candle)
        
        # Should only keep last 3 TR values
        assert len(calc.true_ranges) == 3
    
    def test_atr_calculator_get_natr(self):
        """Test ATRCalculator NATR calculation"""
        calc = ATRCalculator(period=2)
        
        # Add enough candles for ATR
        candles = [
            Candle(ts=1000, open=100, high=110, low=90, close=100, volume=1000, is_closed=True),
            Candle(ts=2000, open=100, high=110, low=90, close=100, volume=1000, is_closed=True),
        ]
        
        for candle in candles:
            calc.update(candle)
        
        natr = calc.get_natr(100.0)
        assert natr is not None
        assert natr > 0
    
    def test_atr_calculator_get_natr_insufficient_data(self):
        """Test ATRCalculator NATR with insufficient data"""
        calc = ATRCalculator(period=5)
        
        candle = Candle(ts=1000, open=100, high=105, low=95, close=102, volume=1000, is_closed=True)
        calc.update(candle)
        
        natr = calc.get_natr(100.0)
        assert natr is None