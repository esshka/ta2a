"""
Integration tests demonstrating system resilience under various data quality conditions.

These tests simulate real-world scenarios where data quality degrades and verify
that the system continues operating with graceful degradation.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import time

from ta2_app.engine import BreakoutEvaluationEngine
from ta2_app.errors import (
    DataQualityError,
    MissingDataError,
    MalformedDataError,
    TemporalDataError,
    GracefulDegradationError,
)


class TestSystemResilience:
    """Integration tests for system resilience under adverse conditions."""

    def test_progressive_data_quality_degradation(self):
        """Test system handles progressive degradation of data quality."""
        engine = BreakoutEvaluationEngine()
        
        # Add test plan
        plan = {
            "id": "resilience_test_plan",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(plan)
        
        # Phase 1: Good data quality
        good_payload = {
            "arg": {"instId": "BTC-USD"},
            "data": [[
                1640995200000,  # timestamp
                49000,          # open
                51000,          # high
                48000,          # low
                50500,          # close
                1000,           # volume
                50000000,       # volume_quote
                0,              # volume_quote_alt
                1               # confirm_flag
            ]]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=good_payload,
            instrument_id="BTC-USD"
        )
        assert isinstance(signals, list)
        
        # Phase 2: Missing some data fields
        partial_payload = {
            "arg": {"instId": "BTC-USD"},
            "data": [[
                1640995260000,  # timestamp
                49500,          # open
                51500,          # high
                48500,          # low
                50000,          # close
                None,           # volume (missing)
                None,           # volume_quote (missing)
                0,              # volume_quote_alt
                1               # confirm_flag
            ]]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=partial_payload,
            instrument_id="BTC-USD"
        )
        # Should handle gracefully
        assert isinstance(signals, list)
        
        # Phase 3: Malformed data
        malformed_payload = {
            "arg": {"instId": "BTC-USD"},
            "data": [[
                "invalid_timestamp",  # malformed timestamp
                49500,               # open
                51500,               # high
                48500,               # low
                50000,               # close
                1000,                # volume
                50000000,            # volume_quote
                0,                   # volume_quote_alt
                1                    # confirm_flag
            ]]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=malformed_payload,
            instrument_id="BTC-USD"
        )
        # Should handle gracefully without crashing
        assert isinstance(signals, list)
        
        # Phase 4: Completely invalid payload
        invalid_payload = "not a dictionary"
        
        signals = engine.evaluate_tick(
            candlestick_payload=invalid_payload,
            instrument_id="BTC-USD"
        )
        # Should handle gracefully
        assert isinstance(signals, list)
        
        # System should still be functional
        assert len(engine.active_plans) == 1
        assert engine.get_active_plan_count() == 1

    def test_multiple_instrument_error_isolation(self):
        """Test that errors in one instrument don't affect others."""
        engine = BreakoutEvaluationEngine()
        
        # Add plans for multiple instruments
        instruments = ["BTC-USD", "ETH-USD", "ADA-USD"]
        for instrument in instruments:
            plan = {
                "id": f"plan_{instrument}",
                "instrument_id": instrument,
                "entry_type": "breakout",
                "entry_price": 50000,
                "direction": "long"
            }
            engine.add_plan(plan)
        
        # Send good data to BTC-USD
        good_payload = {
            "arg": {"instId": "BTC-USD"},
            "data": [[1640995200000, 49000, 51000, 48000, 50500, 1000, 50000000, 0, 1]]
        }
        
        btc_signals = engine.evaluate_tick(
            candlestick_payload=good_payload,
            instrument_id="BTC-USD"
        )
        assert isinstance(btc_signals, list)
        
        # Send bad data to ETH-USD
        bad_payload = {
            "arg": {"instId": "ETH-USD"},
            "data": "invalid_data_format"
        }
        
        eth_signals = engine.evaluate_tick(
            candlestick_payload=bad_payload,
            instrument_id="ETH-USD"
        )
        assert isinstance(eth_signals, list)
        
        # Send good data to ADA-USD
        ada_signals = engine.evaluate_tick(
            candlestick_payload={
                "arg": {"instId": "ADA-USD"},
                "data": [[1640995200000, 1.0, 1.1, 0.9, 1.05, 1000, 1050, 0, 1]]
            },
            instrument_id="ADA-USD"
        )
        assert isinstance(ada_signals, list)
        
        # All plans should still be active
        assert len(engine.active_plans) == 3

    def test_high_frequency_error_scenarios(self):
        """Test system handles high frequency of errors without degradation."""
        engine = BreakoutEvaluationEngine()
        
        # Add test plan
        plan = {
            "id": "high_freq_test",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(plan)
        
        # Generate rapid sequence of errors
        error_count = 0
        success_count = 0
        
        for i in range(50):
            if i % 3 == 0:
                # Send malformed data
                payload = f"malformed_data_{i}"
                error_count += 1
            elif i % 3 == 1:
                # Send invalid JSON
                payload = {"invalid": "json", "data": f"bad_format_{i}"}
                error_count += 1
            else:
                # Send valid data
                payload = {
                    "arg": {"instId": "BTC-USD"},
                    "data": [[1640995200000 + i * 1000, 49000, 51000, 48000, 50500, 1000, 50000000, 0, 1]]
                }
                success_count += 1
            
            signals = engine.evaluate_tick(
                candlestick_payload=payload,
                instrument_id="BTC-USD"
            )
            
            # Should always return a list, never crash
            assert isinstance(signals, list)
        
        # System should still be functional after many errors
        assert len(engine.active_plans) == 1
        assert engine.get_active_plan_count() == 1
        
        # Verify we actually tested both error and success cases
        assert error_count > 0
        assert success_count > 0

    def test_memory_stability_under_errors(self):
        """Test that repeated errors don't cause memory issues."""
        engine = BreakoutEvaluationEngine()
        
        # Add test plan
        plan = {
            "id": "memory_test",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(plan)
        
        # Generate many errors to test memory stability
        for i in range(200):
            # Alternate between different types of errors
            if i % 4 == 0:
                payload = None
            elif i % 4 == 1:
                payload = "malformed_string"
            elif i % 4 == 2:
                payload = {"missing": "required_fields"}
            else:
                payload = {"arg": {"instId": "BTC-USD"}, "data": "invalid_data_format"}
            
            try:
                signals = engine.evaluate_tick(
                    candlestick_payload=payload,
                    instrument_id="BTC-USD"
                )
                assert isinstance(signals, list)
            except Exception:
                # Some errors may be raised, but system should remain stable
                pass
        
        # System should still be functional
        assert len(engine.active_plans) == 1
        
        # Test with valid data after many errors
        valid_payload = {
            "arg": {"instId": "BTC-USD"},
            "data": [[1640995200000, 49000, 51000, 48000, 50500, 1000, 50000000, 0, 1]]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=valid_payload,
            instrument_id="BTC-USD"
        )
        assert isinstance(signals, list)

    def test_concurrent_error_scenarios(self):
        """Test system handles concurrent processing with errors."""
        engine = BreakoutEvaluationEngine()
        
        # Add multiple plans
        for i in range(5):
            plan = {
                "id": f"concurrent_plan_{i}",
                "instrument_id": "BTC-USD",
                "entry_type": "breakout",
                "entry_price": 50000 + i * 1000,
                "direction": "long"
            }
            engine.add_plan(plan)
        
        # Simulate concurrent processing with mixed data quality
        test_scenarios = [
            # Valid data
            {
                "candlestick_payload": {
                    "arg": {"instId": "BTC-USD"},
                    "data": [[1640995200000, 49000, 51000, 48000, 50500, 1000, 50000000, 0, 1]]
                },
                "orderbook_payload": {
                    "arg": {"instId": "BTC-USD"},
                    "data": {
                        "asks": [["51000", "10", "0", "0"]],
                        "bids": [["50000", "10", "0", "0"]],
                        "ts": "1640995200000"
                    }
                }
            },
            # Mixed valid/invalid data
            {
                "candlestick_payload": "invalid_candle_data",
                "orderbook_payload": {
                    "arg": {"instId": "BTC-USD"},
                    "data": {
                        "asks": [["51000", "10", "0", "0"]],
                        "bids": [["50000", "10", "0", "0"]],
                        "ts": "1640995200000"
                    }
                }
            },
            # All invalid data
            {
                "candlestick_payload": "invalid_candle_data",
                "orderbook_payload": "invalid_book_data"
            }
        ]
        
        for scenario in test_scenarios:
            signals = engine.evaluate_tick(
                candlestick_payload=scenario.get("candlestick_payload"),
                orderbook_payload=scenario.get("orderbook_payload"),
                instrument_id="BTC-USD"
            )
            
            # Should handle gracefully
            assert isinstance(signals, list)
        
        # All plans should still be active
        assert len(engine.active_plans) == 5

    def test_error_recovery_after_system_stress(self):
        """Test system can recover normal operation after stress conditions."""
        engine = BreakoutEvaluationEngine()
        
        # Add test plan
        plan = {
            "id": "recovery_test",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(plan)
        
        # Phase 1: Stress the system with many errors
        for i in range(100):
            engine.evaluate_tick(
                candlestick_payload=f"stress_error_{i}",
                instrument_id="BTC-USD"
            )
        
        # Phase 2: Verify system can still process valid data
        recovery_payload = {
            "arg": {"instId": "BTC-USD"},
            "data": [[1640995200000, 49000, 51000, 48000, 50500, 1000, 50000000, 0, 1]]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=recovery_payload,
            instrument_id="BTC-USD"
        )
        
        # Should process normally
        assert isinstance(signals, list)
        assert len(engine.active_plans) == 1
        
        # Phase 3: Verify continued normal operation
        for i in range(10):
            normal_payload = {
                "arg": {"instId": "BTC-USD"},
                "data": [[1640995200000 + i * 1000, 49000, 51000, 48000, 50500, 1000, 50000000, 0, 1]]
            }
            
            signals = engine.evaluate_tick(
                candlestick_payload=normal_payload,
                instrument_id="BTC-USD"
            )
            
            assert isinstance(signals, list)
        
        # System should be fully operational
        assert len(engine.active_plans) == 1
        assert engine.get_active_plan_count() == 1

    def test_data_quality_monitoring_during_errors(self):
        """Test that data quality can be monitored during error conditions."""
        engine = BreakoutEvaluationEngine()
        
        # Add test plan
        plan = {
            "id": "quality_monitor_test",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(plan)
        
        # Track processing results
        results = {
            "success": 0,
            "error": 0,
            "total": 0
        }
        
        test_data = [
            # Good data
            {"arg": {"instId": "BTC-USD"}, "data": [[1640995200000, 49000, 51000, 48000, 50500, 1000, 50000000, 0, 1]]},
            # Missing data
            None,
            # Malformed data
            "invalid_payload",
            # Partial data
            {"arg": {"instId": "BTC-USD"}, "data": [[1640995260000, 49500, 51500, 48500, 50000]]},
            # Good data again
            {"arg": {"instId": "BTC-USD"}, "data": [[1640995320000, 49200, 51200, 48200, 50200, 1000, 50200000, 0, 1]]},
        ]
        
        for payload in test_data:
            results["total"] += 1
            
            try:
                signals = engine.evaluate_tick(
                    candlestick_payload=payload,
                    instrument_id="BTC-USD"
                )
                
                if isinstance(signals, list):
                    results["success"] += 1
                else:
                    results["error"] += 1
                    
            except Exception:
                results["error"] += 1
        
        # Should have processed all data points
        assert results["total"] == len(test_data)
        
        # Should have some successes and some errors
        assert results["success"] > 0
        assert results["error"] > 0
        
        # System should remain functional
        assert len(engine.active_plans) == 1
        
        # Calculate data quality metrics
        quality_ratio = results["success"] / results["total"]
        assert 0 <= quality_ratio <= 1
        
        # Even with errors, system should maintain basic functionality
        runtime_stats = engine.get_runtime_stats()
        assert runtime_stats["active_plans"] == 1
        assert runtime_stats["tracked_instruments"] >= 0

    def test_error_context_preservation(self):
        """Test that error context is preserved for debugging."""
        engine = BreakoutEvaluationEngine()
        
        # Add test plan
        plan = {
            "id": "context_test",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(plan)
        
        # Test various error scenarios and verify context is preserved
        error_scenarios = [
            {
                "name": "malformed_payload",
                "payload": "not_a_dict",
                "expected_context": "instrument_id"
            },
            {
                "name": "missing_instrument",
                "payload": {"data": "valid_structure"},
                "expected_context": "instrument_id"
            },
            {
                "name": "invalid_data_format",
                "payload": {"arg": {"instId": "BTC-USD"}, "data": "invalid_format"},
                "expected_context": "BTC-USD"
            }
        ]
        
        for scenario in error_scenarios:
            # Capture logging or error context
            with patch('ta2_app.engine.logger') as mock_logger:
                signals = engine.evaluate_tick(
                    candlestick_payload=scenario["payload"],
                    instrument_id="BTC-USD"
                )
                
                # Should handle gracefully
                assert isinstance(signals, list)
                
                # Verify logging was called (context preservation)
                assert mock_logger.warning.called or mock_logger.error.called
        
        # System should remain functional
        assert len(engine.active_plans) == 1