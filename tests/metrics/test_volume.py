"""Tests for RVOL calculations"""

import pytest
from ta2_app.metrics.volume import calculate_rvol, RVOLCalculator


class TestRVOLCalculation:
    """Test RVOL calculation function"""
    
    def test_rvol_calculation_basic(self):
        """Test basic RVOL calculation"""
        current_volume = 1500.0
        volume_history = [1000.0] * 20  # 20 periods of 1000 volume
        
        rvol = calculate_rvol(current_volume, volume_history, period=20)
        assert rvol == 1.5
    
    def test_rvol_insufficient_data(self):
        """Test RVOL with insufficient data"""
        current_volume = 1500.0
        volume_history = [1000.0] * 10  # Only 10 periods
        
        rvol = calculate_rvol(current_volume, volume_history, period=20)
        assert rvol is None
    
    def test_rvol_exact_period(self):
        """Test RVOL with exact period"""
        current_volume = 2000.0
        volume_history = [1000.0] * 20
        
        rvol = calculate_rvol(current_volume, volume_history, period=20)
        assert rvol == 2.0
    
    def test_rvol_more_than_period(self):
        """Test RVOL with more data than period"""
        current_volume = 1200.0
        volume_history = [1000.0] * 30  # 30 periods but only use last 20
        
        rvol = calculate_rvol(current_volume, volume_history, period=20)
        assert rvol == 1.2
    
    def test_rvol_zero_average(self):
        """Test RVOL with zero average volume"""
        current_volume = 1000.0
        volume_history = [0.0] * 20
        
        rvol = calculate_rvol(current_volume, volume_history, period=20)
        assert rvol is None
    
    def test_rvol_mixed_volumes(self):
        """Test RVOL with mixed volume values"""
        current_volume = 1500.0
        volume_history = [500.0, 1000.0, 1500.0, 2000.0, 1000.0] * 4  # 20 periods, avg = 1200
        
        rvol = calculate_rvol(current_volume, volume_history, period=20)
        assert rvol == 1.25  # 1500 / 1200
    
    def test_rvol_custom_period(self):
        """Test RVOL with custom period"""
        current_volume = 1000.0
        volume_history = [500.0] * 10  # 10 periods of 500
        
        rvol = calculate_rvol(current_volume, volume_history, period=10)
        assert rvol == 2.0  # 1000 / 500


class TestRVOLCalculator:
    """Test RVOLCalculator class"""
    
    def test_rvol_calculator_init(self):
        """Test RVOLCalculator initialization"""
        calc = RVOLCalculator(period=15)
        assert calc.period == 15
        assert len(calc.volume_history) == 0
    
    def test_rvol_calculator_update_first_volume(self):
        """Test RVOLCalculator update with first volume"""
        calc = RVOLCalculator(period=3)
        
        rvol = calc.update(1000.0)
        assert rvol is None  # Not enough data yet
        assert len(calc.volume_history) == 1
    
    def test_rvol_calculator_warmup(self):
        """Test RVOLCalculator warmup period"""
        calc = RVOLCalculator(period=3)
        volumes = [1000.0, 1200.0, 800.0, 1500.0]
        
        results = []
        for volume in volumes:
            rvol = calc.update(volume)
            results.append(rvol)
        
        # First three should be None, fourth should have RVOL
        assert results[0] is None
        assert results[1] is None
        assert results[2] is None
        assert results[3] is not None
        # RVOL = 1500 / ((1000 + 1200 + 800) / 3) = 1500 / 1000 = 1.5
        assert results[3] == 1.5
    
    def test_rvol_calculator_rolling_window(self):
        """Test RVOLCalculator maintains rolling window"""
        calc = RVOLCalculator(period=3)
        
        # Add 5 volumes
        volumes = [1000.0, 1200.0, 800.0, 1500.0, 900.0]
        for volume in volumes:
            calc.update(volume)
        
        # Should only keep last 3 volumes
        assert len(calc.volume_history) == 3
        assert list(calc.volume_history) == [800.0, 1500.0, 900.0]
    
    def test_rvol_calculator_get_current_rvol(self):
        """Test RVOLCalculator get_current_rvol method"""
        calc = RVOLCalculator(period=3)
        
        # Add enough volumes to warmup
        volumes = [1000.0, 1200.0, 800.0]
        for volume in volumes:
            calc.update(volume)
        
        # Test get_current_rvol without updating history
        current_rvol = calc.get_current_rvol(1500.0)
        assert current_rvol == 1.5  # 1500 / 1000
        
        # History should remain unchanged
        assert len(calc.volume_history) == 3
    
    def test_rvol_calculator_get_current_rvol_insufficient_data(self):
        """Test RVOLCalculator get_current_rvol with insufficient data"""
        calc = RVOLCalculator(period=5)
        
        # Add only 2 volumes
        calc.update(1000.0)
        calc.update(1200.0)
        
        current_rvol = calc.get_current_rvol(1500.0)
        assert current_rvol is None
    
    def test_rvol_calculator_zero_average(self):
        """Test RVOLCalculator with zero average volume"""
        calc = RVOLCalculator(period=3)
        
        # Add zero volumes
        volumes = [0.0, 0.0, 0.0, 100.0]
        results = []
        for volume in volumes:
            rvol = calc.update(volume)
            results.append(rvol)
        
        # Should handle zero average gracefully
        assert results[3] is None
    
    def test_rvol_calculator_consistent_results(self):
        """Test RVOLCalculator produces consistent results"""
        calc = RVOLCalculator(period=5)
        
        # Add known volumes
        volumes = [1000.0, 1200.0, 800.0, 1500.0, 900.0]
        for volume in volumes:
            calc.update(volume)
        
        # Test multiple calls with same volume
        current_volume = 1300.0
        rvol1 = calc.get_current_rvol(current_volume)
        rvol2 = calc.get_current_rvol(current_volume)
        
        assert rvol1 == rvol2
        assert rvol1 is not None
        
        # Expected: 1300 / ((1000 + 1200 + 800 + 1500 + 900) / 5) = 1300 / 1080 ≈ 1.204
        expected_rvol = 1300.0 / 1080.0
        assert abs(rvol1 - expected_rvol) < 0.001
    
    def test_rvol_calculator_edge_cases(self):
        """Test RVOLCalculator edge cases"""
        calc = RVOLCalculator(period=2)
        
        # Test with very small volumes
        calc.update(0.001)
        calc.update(0.002)
        
        rvol = calc.get_current_rvol(0.003)
        assert rvol == 2.0  # 0.003 / 0.0015
        
        # Test with very large volumes
        calc_large = RVOLCalculator(period=2)
        calc_large.update(1000000.0)
        calc_large.update(2000000.0)
        
        rvol_large = calc_large.get_current_rvol(3000000.0)
        assert rvol_large == 2.0  # 3000000 / 1500000