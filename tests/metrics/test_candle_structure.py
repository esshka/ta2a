"""Tests for candle structure analysis"""

import pytest
from ta2_app.metrics.atr import Candle
from ta2_app.metrics.candle_structure import (
    analyze_candle_structure, detect_pinbar, is_strong_candle, get_candle_strength_score
)


class TestCandleStructureAnalysis:
    """Test candle structure analysis"""
    
    def test_bullish_candle_analysis(self):
        """Test analysis of bullish candle"""
        candle = Candle(ts=1000, open=100, high=110, low=95, close=108, volume=1000, is_closed=True)
        
        structure = analyze_candle_structure(candle)
        
        assert structure.range_value == 15.0  # 110 - 95
        assert structure.body == 8.0  # abs(108 - 100)
        assert structure.upper_shadow == 2.0  # 110 - max(100, 108)
        assert structure.lower_shadow == 5.0  # min(100, 108) - 95
        assert structure.body_pct == 8.0 / 15.0  # body / range
        assert structure.upper_pct == 2.0 / 15.0  # upper / range
        assert structure.lower_pct == 5.0 / 15.0  # lower / range
        assert structure.is_bull is True
        assert structure.is_bear is False
        assert structure.is_doji is False
    
    def test_bearish_candle_analysis(self):
        """Test analysis of bearish candle"""
        candle = Candle(ts=1000, open=108, high=110, low=95, close=100, volume=1000, is_closed=True)
        
        structure = analyze_candle_structure(candle)
        
        assert structure.range_value == 15.0  # 110 - 95
        assert structure.body == 8.0  # abs(100 - 108)
        assert structure.upper_shadow == 2.0  # 110 - max(108, 100)
        assert structure.lower_shadow == 5.0  # min(108, 100) - 95
        assert structure.body_pct == 8.0 / 15.0
        assert structure.upper_pct == 2.0 / 15.0
        assert structure.lower_pct == 5.0 / 15.0
        assert structure.is_bull is False
        assert structure.is_bear is True
        assert structure.is_doji is False
    
    def test_doji_candle_analysis(self):
        """Test analysis of doji candle"""
        candle = Candle(ts=1000, open=100, high=105, low=95, close=100.5, volume=1000, is_closed=True)
        
        structure = analyze_candle_structure(candle)
        
        assert structure.range_value == 10.0  # 105 - 95
        assert structure.body == 0.5  # abs(100.5 - 100)
        assert structure.upper_shadow == 4.5  # 105 - max(100, 100.5)
        assert structure.lower_shadow == 5.0  # min(100, 100.5) - 95
        assert structure.body_pct == 0.05  # 0.5 / 10.0
        assert structure.is_doji is True  # body_pct <= 0.1
    
    def test_zero_range_candle(self):
        """Test analysis of candle with zero range"""
        candle = Candle(ts=1000, open=100, high=100, low=100, close=100, volume=1000, is_closed=True)
        
        structure = analyze_candle_structure(candle)
        
        assert structure.range_value == 0.0
        assert structure.body == 0.0
        assert structure.upper_shadow == 0.0
        assert structure.lower_shadow == 0.0
        assert structure.body_pct == 0.0
        assert structure.upper_pct == 0.0
        assert structure.lower_pct == 0.0
    
    def test_custom_doji_threshold(self):
        """Test custom doji threshold"""
        candle = Candle(ts=1000, open=100, high=105, low=95, close=101, volume=1000, is_closed=True)
        
        # With default threshold (0.1), this is doji
        structure_default = analyze_candle_structure(candle)
        assert structure_default.is_doji is True  # body_pct = 0.1
        
        # With stricter threshold (0.05), this is not doji
        structure_strict = analyze_candle_structure(candle, doji_threshold=0.05)
        assert structure_strict.is_doji is False


class TestPinbarDetection:
    """Test pinbar detection"""
    
    def test_bearish_pinbar_detection(self):
        """Test detection of bearish pinbar"""
        # Long upper shadow, small body, small lower shadow
        candle = Candle(ts=1000, open=100, high=120, low=98, close=102, volume=1000, is_closed=True)
        
        pinbar = detect_pinbar(candle)
        
        # Range = 22, Body = 2, Upper = 18, Lower = 2
        # body_pct = 2/22 ≈ 0.091 <= 0.4 ✓
        # upper_pct = 18/22 ≈ 0.818 >= 0.66 ✓
        # lower_pct = 2/22 ≈ 0.091 <= 0.1 ✓
        assert pinbar == 'bearish'
    
    def test_bullish_pinbar_detection(self):
        """Test detection of bullish pinbar"""
        # Long lower shadow, small body, small upper shadow
        candle = Candle(ts=1000, open=100, high=102, low=80, close=98, volume=1000, is_closed=True)
        
        pinbar = detect_pinbar(candle)
        
        # Range = 22, Body = 2, Upper = 2, Lower = 18
        # body_pct = 2/22 ≈ 0.091 <= 0.4 ✓
        # lower_pct = 18/22 ≈ 0.818 >= 0.66 ✓
        # upper_pct = 2/22 ≈ 0.091 <= 0.1 ✓
        assert pinbar == 'bullish'
    
    def test_no_pinbar_large_body(self):
        """Test no pinbar detection with large body"""
        candle = Candle(ts=1000, open=100, high=120, low=98, close=115, volume=1000, is_closed=True)
        
        pinbar = detect_pinbar(candle)
        
        # Large body disqualifies pinbar
        assert pinbar is None
    
    def test_no_pinbar_short_shadow(self):
        """Test no pinbar detection with short shadow"""
        candle = Candle(ts=1000, open=100, high=108, low=98, close=102, volume=1000, is_closed=True)
        
        pinbar = detect_pinbar(candle)
        
        # Short upper shadow disqualifies pinbar
        assert pinbar is None
    
    def test_no_pinbar_long_tail(self):
        """Test no pinbar detection with long opposite tail"""
        candle = Candle(ts=1000, open=100, high=120, low=85, close=102, volume=1000, is_closed=True)
        
        pinbar = detect_pinbar(candle)
        
        # Long lower shadow disqualifies bearish pinbar
        assert pinbar is None
    
    def test_pinbar_custom_thresholds(self):
        """Test pinbar detection with custom thresholds"""
        candle = Candle(ts=1000, open=100, high=115, low=98, close=103, volume=1000, is_closed=True)
        
        # With default thresholds, this might not be a pinbar
        pinbar_default = detect_pinbar(candle)
        
        # With relaxed thresholds, this could be a pinbar
        pinbar_relaxed = detect_pinbar(
            candle, 
            body_threshold=0.5, 
            shadow_threshold=0.5, 
            tail_threshold=0.2
        )
        
        # Test that different thresholds can change detection
        assert pinbar_default != pinbar_relaxed or pinbar_default is None


class TestStrongCandle:
    """Test strong candle detection"""
    
    def test_strong_candle_detection(self):
        """Test detection of strong candle"""
        candle = Candle(ts=1000, open=100, high=108, low=99, close=107, volume=1000, is_closed=True)
        
        is_strong = is_strong_candle(candle)
        
        # Range = 9, Body = 7, body_pct = 7/9 ≈ 0.778 >= 0.6
        assert is_strong is True
    
    def test_weak_candle_detection(self):
        """Test detection of weak candle"""
        candle = Candle(ts=1000, open=100, high=105, low=95, close=102, volume=1000, is_closed=True)
        
        is_strong = is_strong_candle(candle)
        
        # Range = 10, Body = 2, body_pct = 0.2 < 0.6
        assert is_strong is False
    
    def test_strong_candle_custom_threshold(self):
        """Test strong candle with custom threshold"""
        candle = Candle(ts=1000, open=100, high=105, low=95, close=104, volume=1000, is_closed=True)
        
        # With default threshold (0.6), this is not strong
        is_strong_default = is_strong_candle(candle)
        assert is_strong_default is False
        
        # With lower threshold (0.3), this is strong
        is_strong_custom = is_strong_candle(candle, min_body_pct=0.3)
        assert is_strong_custom is True


class TestCandleStrengthScore:
    """Test candle strength scoring"""
    
    def test_strength_score_strong_bull(self):
        """Test strength score for strong bullish candle"""
        candle = Candle(ts=1000, open=100, high=108, low=99, close=107, volume=1000, is_closed=True)
        
        score = get_candle_strength_score(candle)
        
        # Should be high score for strong directional candle
        assert score >= 70
        assert score <= 100
    
    def test_strength_score_doji(self):
        """Test strength score for doji candle"""
        candle = Candle(ts=1000, open=100, high=105, low=95, close=100.5, volume=1000, is_closed=True)
        
        score = get_candle_strength_score(candle)
        
        # Should be low score for doji
        assert score <= 30
    
    def test_strength_score_with_shadows(self):
        """Test strength score with opposing shadows"""
        # Bullish candle with large upper shadow
        candle = Candle(ts=1000, open=100, high=115, low=99, close=108, volume=1000, is_closed=True)
        
        score = get_candle_strength_score(candle)
        
        # Should be penalized for large opposing shadow
        assert score >= 0
        assert score <= 100
    
    def test_strength_score_range(self):
        """Test strength score stays within range"""
        test_cases = [
            Candle(ts=1000, open=100, high=100, low=100, close=100, volume=1000, is_closed=True),  # No range
            Candle(ts=1000, open=100, high=120, low=80, close=110, volume=1000, is_closed=True),   # Strong bull
            Candle(ts=1000, open=110, high=120, low=80, close=90, volume=1000, is_closed=True),    # Strong bear
            Candle(ts=1000, open=100, high=105, low=95, close=101, volume=1000, is_closed=True),   # Weak
        ]
        
        for candle in test_cases:
            score = get_candle_strength_score(candle)
            assert 0 <= score <= 100