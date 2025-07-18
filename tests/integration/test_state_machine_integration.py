"""Integration tests for state machine with metrics pipeline."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from ta2_app.engine import BreakoutEvaluationEngine
from ta2_app.state.models import PlanLifecycleState, BreakoutSubState
from ta2_app.data.models import Candle, BookSnap, BookLevel
from ta2_app.models.metrics import MetricsSnapshot


class TestBreakoutStateIntegration:
    """Integration tests for complete breakout state machine pipeline."""

    def test_full_long_breakout_momentum_flow(self):
        """Test complete long breakout flow in momentum mode."""
        engine = BreakoutEvaluationEngine()
        
        # Add a long breakout plan
        plan = {
            "id": "test-long-001",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 50000.0,
            "created_at": datetime.now(timezone.utc),
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.05,
                    "min_rvol": 1.5,
                    "confirm_close": True,
                    "allow_retest_entry": False,  # Momentum mode
                    "ob_sweep_check": True
                }
            }
        }
        
        engine.add_plan(plan)
        
        # Step 1: Price below entry - no break
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383085", "49800.0", "49900.0", "49700.0", "49800.0", "1000", "49800000", "49800000", "1"]
            ]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            instrument_id="BTC-USDT-SWAP"
        )
        
        # Should have no signals - no break detected
        assert len(signals) == 0
        
        # Check state is still PENDING
        state = engine.get_plan_state("test-long-001")
        assert state["state"] == "pending"
        assert state["substate"] == "none"
        
        # Step 2: Price breaks above entry level with high volume
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383185", "50000.0", "52800.0", "49900.0", "52500.0", "3000", "156000000", "156000000", "1"]
            ]
        }
        
        # Mock order book with sweep
        orderbook_payload = {
            "code": "0",
            "msg": "",
            "data": [{
                "asks": [["52600.0", "10.0", "0", "1"]],
                "bids": [["52400.0", "50.0", "0", "2"]],  # Strong bid after sweep
                "ts": "1597026383185"
            }]
        }
        
        # Process both candlestick and order book
        signals = engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            orderbook_payload=orderbook_payload,
            instrument_id="BTC-USDT-SWAP"
        )
        
        # Should emit triggered signal
        assert len(signals) == 1
        signal = signals[0]
        
        assert signal["plan_id"] == "test-long-001"
        assert signal["state"] == "triggered"
        assert signal["entry_mode"] == "momentum"
        assert signal["last_price"] == 52500.0
        assert signal["strength_score"] > 60.0  # Should be high due to good metrics
        
        # Check final state
        state = engine.get_plan_state("test-long-001")
        assert state["state"] == "triggered"
        assert state["triggered_at"] is not None
        assert state["break_seen"] is True
        assert state["break_confirmed"] is True
        assert state["signal_emitted"] is True

    def test_full_short_breakout_retest_flow(self):
        """Test complete short breakout flow with retest mode."""
        engine = BreakoutEvaluationEngine()
        
        # Add a short breakout plan with retest enabled
        plan = {
            "id": "test-short-001",
            "instrument_id": "ETH-USDT-SWAP",
            "direction": "short",
            "entry_type": "breakout",
            "entry_price": 3000.0,
            "created_at": datetime.now(timezone.utc),
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.04,
                    "min_rvol": 1.8,
                    "confirm_close": True,
                    "allow_retest_entry": True,  # Retest mode
                    "retest_band_pct": 0.02,
                    "ob_sweep_check": True
                }
            }
        }
        
        engine.add_plan(plan)
        
        # Step 1: Price breaks below entry level
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383085", "3000.0", "3010.0", "2870.0", "2880.0", "5000", "14500000", "14500000", "1"]
            ]
        }
        
        # Order book showing ask sweep
        orderbook_payload = {
            "code": "0",
            "msg": "",
            "data": [{
                "asks": [["2890.0", "100.0", "0", "1"]],  # Strong ask after sweep
                "bids": [["2880.0", "20.0", "0", "2"]],
                "ts": "1597026383085"
            }]
        }
        
        # Process break
        signals = engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            orderbook_payload=orderbook_payload,
            instrument_id="ETH-USDT-SWAP"
        )
        
        # Should have no signals yet - waiting for retest
        assert len(signals) == 0
        
        # Check state is ARMED for retest
        state = engine.get_plan_state("test-short-001")
        assert state["state"] == "armed"
        assert state["substate"] == "retest_armed"
        
        # Step 2: Price retests back toward entry level
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383285", "2880.0", "2980.0", "2870.0", "2940.0", "2000", "5840000", "5840000", "1"]
            ]
        }
        
        # Mock bearish pinbar for rejection
        with patch('ta2_app.metrics.candle_structure.detect_pinbar') as mock_pinbar:
            mock_pinbar.return_value = 'bearish'
            
            signals = engine.evaluate_tick(
                candlestick_payload=candlestick_payload,
                instrument_id="ETH-USDT-SWAP"
            )
        
        # Should now trigger on retest
        assert len(signals) == 1
        signal = signals[0]
        
        assert signal["plan_id"] == "test-short-001"
        assert signal["state"] == "triggered"
        assert signal["entry_mode"] == "retest"
        assert signal["metrics"]["pinbar"] is True
        assert signal["metrics"]["pinbar_type"] == "bearish"
        
        # Check final state
        state = engine.get_plan_state("test-short-001")
        assert state["state"] == "triggered"
        assert state["substate"] == "retest_triggered"

    def test_fakeout_invalidation_flow(self):
        """Test fakeout invalidation during confirmation phase."""
        engine = BreakoutEvaluationEngine()
        
        # Add plan with fakeout invalidation enabled
        plan = {
            "id": "test-fakeout-001",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 50000.0,
            "created_at": datetime.now(timezone.utc),
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.05,
                    "min_rvol": 1.5,
                    "confirm_close": True,
                    "fakeout_close_invalidate": True,
                    "ob_sweep_check": False  # Disable for simplicity
                }
            }
        }
        
        engine.add_plan(plan)
        
        # Step 1: Price breaks above entry level
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383085", "50000.0", "52800.0", "49900.0", "52500.0", "3000", "156000000", "156000000", "1"]
            ]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            instrument_id="BTC-USDT-SWAP"
        )
        
        # Should trigger immediately (good volume, close beyond level)
        assert len(signals) == 1
        assert signals[0]["state"] == "triggered"
        
        # Now test fakeout scenario with new plan
        plan_fakeout = {
            "id": "test-fakeout-002",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 50000.0,
            "created_at": datetime.now(timezone.utc),
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.05,
                    "min_rvol": 0.5,  # Lower requirement
                    "confirm_close": True,
                    "fakeout_close_invalidate": True,
                    "ob_sweep_check": False
                }
            }
        }
        
        engine.add_plan(plan_fakeout)
        
        # Step 1: Price breaks above but then closes back below (fakeout)
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383185", "50000.0", "52800.0", "49000.0", "49500.0", "1000", "50000000", "50000000", "1"]
            ]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            instrument_id="BTC-USDT-SWAP"
        )
        
        # Should emit invalid signal due to fakeout
        assert len(signals) == 1
        signal = signals[0]
        
        assert signal["plan_id"] == "test-fakeout-002"
        assert signal["state"] == "invalid"
        assert signal["runtime"]["invalid_reason"] == "fakeout_close"

    def test_time_limit_invalidation(self):
        """Test time limit invalidation."""
        engine = BreakoutEvaluationEngine()
        
        # Create plan with short time limit
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        plan = {
            "id": "test-expired-001",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 50000.0,
            "created_at": old_time,
            "extra_data": {
                "invalidation_conditions": [
                    {"condition_type": "time_limit", "duration_seconds": 3600}  # 1 hour
                ]
            }
        }
        
        engine.add_plan(plan)
        
        # Any price tick should trigger time invalidation
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383085", "50000.0", "50100.0", "49900.0", "50000.0", "1000", "50000000", "50000000", "1"]
            ]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            instrument_id="BTC-USDT-SWAP"
        )
        
        # Should emit invalid signal due to time limit
        assert len(signals) == 1
        signal = signals[0]
        
        assert signal["plan_id"] == "test-expired-001"
        assert signal["state"] == "invalid"
        assert signal["runtime"]["invalid_reason"] == "time_limit"

    def test_price_invalidation_conditions(self):
        """Test price-based invalidation conditions."""
        engine = BreakoutEvaluationEngine()
        
        # Add plan with price invalidation conditions
        plan = {
            "id": "test-price-invalid-001",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 50000.0,
            "created_at": datetime.now(timezone.utc),
            "extra_data": {
                "invalidation_conditions": [
                    {"condition_type": "price_above", "level": 55000.0},
                    {"condition_type": "price_below", "level": 45000.0}
                ]
            }
        }
        
        engine.add_plan(plan)
        
        # Price above upper invalidation level
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383085", "50000.0", "56000.0", "49900.0", "56000.0", "1000", "56000000", "56000000", "1"]
            ]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            instrument_id="BTC-USDT-SWAP"
        )
        
        # Should emit invalid signal due to price above
        assert len(signals) == 1
        signal = signals[0]
        
        assert signal["plan_id"] == "test-price-invalid-001"
        assert signal["state"] == "invalid"
        assert signal["runtime"]["invalid_reason"] == "price_above"

    def test_multiple_plans_same_instrument(self):
        """Test multiple plans on same instrument evaluate independently."""
        engine = BreakoutEvaluationEngine()
        
        # Add two plans with different entry levels
        plan1 = {
            "id": "test-multi-001",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 50000.0,
            "created_at": datetime.now(timezone.utc),
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.05,
                    "min_rvol": 1.5,
                    "confirm_close": True,
                    "allow_retest_entry": False,
                    "ob_sweep_check": False
                }
            }
        }
        
        plan2 = {
            "id": "test-multi-002",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 52000.0,  # Higher entry level
            "created_at": datetime.now(timezone.utc),
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.05,
                    "min_rvol": 1.5,
                    "confirm_close": True,
                    "allow_retest_entry": False,
                    "ob_sweep_check": False
                }
            }
        }
        
        engine.add_plan(plan1)
        engine.add_plan(plan2)
        
        # Price breaks first level but not second
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383085", "50000.0", "51000.0", "49900.0", "51000.0", "3000", "153000000", "153000000", "1"]
            ]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            instrument_id="BTC-USDT-SWAP"
        )
        
        # Should only trigger first plan
        assert len(signals) == 1
        assert signals[0]["plan_id"] == "test-multi-001"
        assert signals[0]["state"] == "triggered"
        
        # Check states
        state1 = engine.get_plan_state("test-multi-001")
        state2 = engine.get_plan_state("test-multi-002")
        
        assert state1["state"] == "triggered"
        assert state2["state"] == "pending"  # Still waiting

    def test_insufficient_volume_blocks_confirmation(self):
        """Test that insufficient volume blocks confirmation."""
        engine = BreakoutEvaluationEngine()
        
        # Add plan with high volume requirement
        plan = {
            "id": "test-volume-001",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 50000.0,
            "created_at": datetime.now(timezone.utc),
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.05,
                    "min_rvol": 5.0,  # Very high volume requirement
                    "confirm_close": True,
                    "ob_sweep_check": False
                }
            }
        }
        
        engine.add_plan(plan)
        
        # Price breaks but with low volume
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383085", "50000.0", "52800.0", "49900.0", "52500.0", "100", "5250000", "5250000", "1"]
            ]
        }
        
        signals = engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            instrument_id="BTC-USDT-SWAP"
        )
        
        # Should have no signals - volume gate blocks confirmation
        assert len(signals) == 0
        
        # Check state is break seen but not confirmed
        state = engine.get_plan_state("test-volume-001")
        assert state["state"] == "pending"
        assert state["substate"] == "break_seen"
        assert state["break_seen"] is True
        assert state["break_confirmed"] is False

    def test_plan_removal_cleans_up_state(self):
        """Test that removing a plan cleans up its state."""
        engine = BreakoutEvaluationEngine()
        
        # Add plan
        plan = {
            "id": "test-cleanup-001",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 50000.0,
            "created_at": datetime.now(timezone.utc)
        }
        
        engine.add_plan(plan)
        
        # Process some data to create state
        candlestick_payload = {
            "code": "0",
            "msg": "",
            "data": [
                ["1597026383085", "50000.0", "52800.0", "49900.0", "52500.0", "1000", "52500000", "52500000", "1"]
            ]
        }
        
        engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            instrument_id="BTC-USDT-SWAP"
        )
        
        # Verify state exists
        state = engine.get_plan_state("test-cleanup-001")
        assert state is not None
        
        # Remove plan
        engine.remove_plan("test-cleanup-001")
        
        # Verify state is cleaned up
        state = engine.get_plan_state("test-cleanup-001")
        assert state is None
        
        # Verify no more processing happens
        signals = engine.evaluate_tick(
            candlestick_payload=candlestick_payload,
            instrument_id="BTC-USDT-SWAP"
        )
        assert len(signals) == 0

    def test_engine_runtime_stats(self):
        """Test engine runtime statistics."""
        engine = BreakoutEvaluationEngine()
        
        # Initial stats
        stats = engine.get_runtime_stats()
        assert stats["active_plans"] == 0
        assert stats["tracked_instruments"] == 0
        
        # Add plans
        plan1 = {
            "id": "test-stats-001",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 50000.0,
            "created_at": datetime.now(timezone.utc)
        }
        
        plan2 = {
            "id": "test-stats-002",
            "instrument_id": "ETH-USDT-SWAP",
            "direction": "short",
            "entry_type": "breakout",
            "entry_price": 3000.0,
            "created_at": datetime.now(timezone.utc)
        }
        
        engine.add_plan(plan1)
        engine.add_plan(plan2)
        
        # Process data for both instruments
        engine.evaluate_tick(
            candlestick_payload={
                "code": "0",
                "msg": "",
                "data": [["1597026383085", "50000.0", "50100.0", "49900.0", "50000.0", "1000", "50000000", "50000000", "1"]]
            },
            instrument_id="BTC-USDT-SWAP"
        )
        
        engine.evaluate_tick(
            candlestick_payload={
                "code": "0",
                "msg": "",
                "data": [["1597026383085", "3000.0", "3010.0", "2990.0", "3000.0", "1000", "3000000", "3000000", "1"]]
            },
            instrument_id="ETH-USDT-SWAP"
        )
        
        # Check updated stats
        stats = engine.get_runtime_stats()
        assert stats["active_plans"] == 2
        assert stats["tracked_instruments"] == 2
        assert stats["state_manager_active_plans"] == 2