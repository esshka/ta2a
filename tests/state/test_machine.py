"""Tests for core state machine logic."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from ta2_app.state.machine import (
    eval_breakout_tick, detect_break_seen, check_confirmation_gates,
    check_fakeout_close, bar_closed_beyond, check_retest_trigger,
    check_pre_invalidations, calc_penetration_distance, calc_retest_band
)
from ta2_app.state.models import (
    PlanRuntimeState, BreakoutParameters, MarketContext,
    PlanLifecycleState, BreakoutSubState, InvalidationReason
)
from ta2_app.models.metrics import MetricsSnapshot
from ta2_app.data.models import Candle


class TestEvalBreakoutTick:
    """Test main breakout evaluation function."""

    def test_missing_required_fields(self):
        """Test evaluation with missing required plan fields."""
        plan_rt = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        market = MarketContext(last_price=50000.0, timestamp=datetime.now(timezone.utc))
        cfg = BreakoutParameters()
        
        # Missing entry_price
        plan_data = {'id': 'test', 'direction': 'long'}
        result = eval_breakout_tick(plan_rt, market, cfg, plan_data, None)
        assert result is None
        
        # Missing direction
        plan_data = {'id': 'test', 'entry_price': 50000.0}
        result = eval_breakout_tick(plan_rt, market, cfg, plan_data, None)
        assert result is None

    def test_pre_invalidation_triggers(self):
        """Test pre-trigger invalidation conditions."""
        plan_rt = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        market = MarketContext(last_price=60000.0, timestamp=datetime.now(timezone.utc))
        cfg = BreakoutParameters()
        
        plan_data = {
            'id': 'test-plan',
            'entry_price': 50000.0,
            'direction': 'long',
            'created_at': datetime.now(timezone.utc),
            'extra_data': {
                'invalidation_conditions': [
                    {'condition_type': 'price_above', 'level': 55000.0}
                ]
            }
        }
        
        result = eval_breakout_tick(plan_rt, market, cfg, plan_data, None)
        
        assert result is not None
        assert result.new_state == PlanLifecycleState.INVALID
        assert result.invalid_reason == InvalidationReason.PRICE_ABOVE
        assert result.should_emit_signal is True

    def test_break_detection_long(self):
        """Test break detection for long breakout."""
        plan_rt = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        
        # Price at entry level - no break
        market = MarketContext(last_price=50000.0, timestamp=datetime.now(timezone.utc))
        cfg = BreakoutParameters(penetration_pct=0.05)  # 5% = 2500 points
        plan_data = {
            'id': 'test-plan',
            'entry_price': 50000.0,
            'direction': 'long',
            'created_at': datetime.now(timezone.utc)
        }
        
        result = eval_breakout_tick(plan_rt, market, cfg, plan_data, None)
        assert result is None
        
        # Price above entry + penetration - should see break
        market = MarketContext(last_price=52600.0, timestamp=datetime.now(timezone.utc))  # 5.2% above
        result = eval_breakout_tick(plan_rt, market, cfg, plan_data, None)
        
        assert result is not None
        assert result.new_substate == BreakoutSubState.BREAK_SEEN
        assert result.should_emit_signal is False

    def test_break_detection_short(self):
        """Test break detection for short breakout."""
        plan_rt = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        
        # Price below entry - penetration - should see break
        market = MarketContext(last_price=47400.0, timestamp=datetime.now(timezone.utc))  # 5.2% below
        cfg = BreakoutParameters(penetration_pct=0.05)
        plan_data = {
            'id': 'test-plan',
            'entry_price': 50000.0,
            'direction': 'short',
            'created_at': datetime.now(timezone.utc)
        }
        
        result = eval_breakout_tick(plan_rt, market, cfg, plan_data, None)
        
        assert result is not None
        assert result.new_substate == BreakoutSubState.BREAK_SEEN

    def test_confirmation_gates_momentum_mode(self):
        """Test confirmation gates in momentum mode."""
        plan_rt = PlanRuntimeState(
            state=PlanLifecycleState.PENDING,
            substate=BreakoutSubState.BREAK_SEEN,
            break_seen=True,
            break_ts=datetime.now(timezone.utc)
        )
        
        # Create closed candle beyond entry level
        candle = Candle(
            ts=datetime.now(timezone.utc),
            open=50500.0,
            high=52000.0,
            low=50000.0,
            close=51500.0,  # Closed above entry
            volume=1000.0,
            is_closed=True
        )
        
        market = MarketContext(
            last_price=51500.0,
            timestamp=datetime.now(timezone.utc),
            rvol=2.0,  # Above min threshold
            atr=500.0,
            last_closed_bar=candle,
            bar_range=2000.0,  # High range
            ob_sweep_detected=True,
            ob_sweep_side='ask'  # Correct side for long
        )
        
        cfg = BreakoutParameters(
            min_rvol=1.5,
            confirm_close=True,
            allow_retest_entry=False,  # Momentum mode
            ob_sweep_check=True
        )
        
        metrics = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            rvol=2.0,
            atr=500.0,
            ob_sweep_detected=True,
            ob_sweep_side='ask'
        )
        
        plan_data = {
            'id': 'test-plan',
            'entry_price': 50000.0,
            'direction': 'long',
            'created_at': datetime.now(timezone.utc)
        }
        
        result = eval_breakout_tick(plan_rt, market, cfg, plan_data, metrics)
        
        assert result is not None
        assert result.new_state == PlanLifecycleState.TRIGGERED
        assert result.should_emit_signal is True
        assert result.signal_context['entry_mode'] == 'momentum'

    def test_confirmation_gates_retest_mode(self):
        """Test confirmation gates in retest mode."""
        plan_rt = PlanRuntimeState(
            state=PlanLifecycleState.PENDING,
            substate=BreakoutSubState.BREAK_SEEN,
            break_seen=True
        )
        
        candle = Candle(
            ts=datetime.now(timezone.utc),
            open=50500.0,
            high=52000.0,
            low=50000.0,
            close=51500.0,
            volume=1000.0,
            is_closed=True
        )
        
        market = MarketContext(
            last_price=51500.0,
            timestamp=datetime.now(timezone.utc),
            rvol=2.0,
            atr=500.0,
            last_closed_bar=candle,
            bar_range=2000.0,
            ob_sweep_detected=True,
            ob_sweep_side='ask'
        )
        
        cfg = BreakoutParameters(
            allow_retest_entry=True  # Retest mode
        )
        
        metrics = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            rvol=2.0,
            atr=500.0,
            ob_sweep_detected=True,
            ob_sweep_side='ask'
        )
        
        plan_data = {
            'id': 'test-plan',
            'entry_price': 50000.0,
            'direction': 'long',
            'created_at': datetime.now(timezone.utc)
        }
        
        result = eval_breakout_tick(plan_rt, market, cfg, plan_data, metrics)
        
        assert result is not None
        assert result.new_state == PlanLifecycleState.ARMED
        assert result.new_substate == BreakoutSubState.RETEST_ARMED
        assert result.should_emit_signal is False

    def test_fakeout_invalidation(self):
        """Test fakeout close invalidation."""
        plan_rt = PlanRuntimeState(
            state=PlanLifecycleState.PENDING,
            substate=BreakoutSubState.BREAK_SEEN,
            break_seen=True
        )
        
        # Candle closes back below entry level (fakeout for long)
        candle = Candle(
            ts=datetime.now(timezone.utc),
            open=50500.0,
            high=52000.0,
            low=49000.0,
            close=49500.0,  # Closed back below entry
            volume=1000.0,
            is_closed=True
        )
        
        market = MarketContext(
            last_price=49500.0,
            timestamp=datetime.now(timezone.utc),
            last_closed_bar=candle
        )
        
        cfg = BreakoutParameters(fakeout_close_invalidate=True)
        
        plan_data = {
            'id': 'test-plan',
            'entry_price': 50000.0,
            'direction': 'long',
            'created_at': datetime.now(timezone.utc)
        }
        
        result = eval_breakout_tick(plan_rt, market, cfg, plan_data, None)
        
        assert result is not None
        assert result.new_state == PlanLifecycleState.INVALID
        assert result.invalid_reason == InvalidationReason.FAKEOUT_CLOSE

    def test_retest_trigger(self):
        """Test retest trigger logic."""
        plan_rt = PlanRuntimeState(
            state=PlanLifecycleState.ARMED,
            substate=BreakoutSubState.RETEST_ARMED,
            break_seen=True,
            break_confirmed=True
        )
        
        # Price back near entry level (retest)
        market = MarketContext(
            last_price=50100.0,  # Within retest band
            timestamp=datetime.now(timezone.utc)
        )
        
        cfg = BreakoutParameters(
            allow_retest_entry=True,
            retest_band_pct=0.03  # 3% band = 1500 points
        )
        
        # Metrics showing bullish pinbar (rejection) and low volume
        metrics = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            pinbar='bullish',
            rvol=0.7  # Low volume suggests rejection
        )
        
        plan_data = {
            'id': 'test-plan',
            'entry_price': 50000.0,
            'direction': 'long',
            'created_at': datetime.now(timezone.utc)
        }
        
        result = eval_breakout_tick(plan_rt, market, cfg, plan_data, metrics)
        
        assert result is not None
        assert result.new_state == PlanLifecycleState.TRIGGERED
        assert result.signal_context['entry_mode'] == 'retest'


class TestDetectBreakSeen:
    """Test break detection logic."""

    def test_long_break_with_percentage_only(self):
        """Test long break using percentage penetration only."""
        entry_price = 50000.0
        cfg = BreakoutParameters(penetration_pct=0.05, penetration_natr_mult=0.0)
        
        # No break - price at level
        assert not detect_break_seen(50000.0, entry_price, False, cfg, None)
        
        # No break - insufficient penetration
        assert not detect_break_seen(52400.0, entry_price, False, cfg, None)  # 4.8%
        
        # Break detected - sufficient penetration
        assert detect_break_seen(52600.0, entry_price, False, cfg, None)  # 5.2%

    def test_short_break_with_percentage_only(self):
        """Test short break using percentage penetration only."""
        entry_price = 50000.0
        cfg = BreakoutParameters(penetration_pct=0.05, penetration_natr_mult=0.0)
        
        # No break - price at level
        assert not detect_break_seen(50000.0, entry_price, True, cfg, None)
        
        # No break - insufficient penetration
        assert not detect_break_seen(47600.0, entry_price, True, cfg, None)  # 4.8%
        
        # Break detected - sufficient penetration
        assert detect_break_seen(47400.0, entry_price, True, cfg, None)  # 5.2%

    def test_volatility_aware_penetration(self):
        """Test volatility-aware penetration distance."""
        entry_price = 50000.0
        cfg = BreakoutParameters(penetration_pct=0.02, penetration_natr_mult=0.5)
        
        # High volatility metrics (5% NATR)
        metrics = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            natr_pct=5.0
        )
        
        # Volatility distance: 0.5 * 5% = 2.5% (larger than 2% fixed)
        # Should require 2.5% move = 1250 points
        
        # Insufficient - only 2% move
        assert not detect_break_seen(51000.0, entry_price, False, cfg, metrics)
        
        # Sufficient - 2.6% move
        assert detect_break_seen(51300.0, entry_price, False, cfg, metrics)

    def test_no_metrics_fallback(self):
        """Test fallback to percentage-only when no metrics."""
        entry_price = 50000.0
        cfg = BreakoutParameters(penetration_pct=0.05, penetration_natr_mult=0.25)
        
        # Should use only percentage penetration (5%)
        assert not detect_break_seen(52400.0, entry_price, False, cfg, None)
        assert detect_break_seen(52600.0, entry_price, False, cfg, None)


class TestConfirmationGates:
    """Test confirmation gate logic."""

    def test_rvol_gate(self):
        """Test RVOL confirmation gate."""
        plan_rt = PlanRuntimeState(state=PlanLifecycleState.PENDING, break_seen=True)
        market = MarketContext(last_price=50000.0, timestamp=datetime.now(timezone.utc))
        cfg = BreakoutParameters(min_rvol=1.5)
        
        # Insufficient RVOL
        metrics = MetricsSnapshot(timestamp=datetime.now(timezone.utc), rvol=1.2)
        assert not check_confirmation_gates(plan_rt, market, cfg, metrics, 50000.0, False)
        
        # Sufficient RVOL
        metrics = MetricsSnapshot(timestamp=datetime.now(timezone.utc), rvol=2.0)
        # This will still fail other gates, but RVOL gate passes
        
        # Disabled RVOL gate
        cfg_disabled = BreakoutParameters(min_rvol=0.0, confirm_close=False, confirm_time_ms=0, ob_sweep_check=False, min_break_range_atr=0.0)
        assert check_confirmation_gates(plan_rt, market, cfg_disabled, None, 50000.0, False)

    def test_volatility_gate(self):
        """Test volatility range gate."""
        plan_rt = PlanRuntimeState(state=PlanLifecycleState.PENDING, break_seen=True)
        candle = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=51000.0, low=49500.0, close=50800.0,
            volume=1000.0, is_closed=True
        )
        market = MarketContext(
            last_price=50800.0,
            timestamp=datetime.now(timezone.utc),
            last_closed_bar=candle,
            bar_range=1500.0  # High - Low
        )
        cfg = BreakoutParameters(min_break_range_atr=0.5, confirm_close=True)
        
        # Insufficient range (ATR=4000, need 0.5*4000=2000, have 1500)
        metrics = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            atr=4000.0,
            rvol=2.0
        )
        assert not check_confirmation_gates(plan_rt, market, cfg, metrics, 50000.0, False)
        
        # Sufficient range (ATR=2000, need 0.5*2000=1000, have 1500)
        metrics = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            atr=2000.0,
            rvol=2.0
        )
        # Would pass volatility gate but may fail others

    def test_close_gate_long(self):
        """Test close confirmation gate for long breakout."""
        plan_rt = PlanRuntimeState(state=PlanLifecycleState.PENDING, break_seen=True)
        cfg = BreakoutParameters(confirm_close=True, min_rvol=0.0, ob_sweep_check=False, min_break_range_atr=0.0)
        
        # Candle closed above entry level
        candle_above = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=51000.0, low=49500.0, close=50500.0,
            volume=1000.0, is_closed=True
        )
        market = MarketContext(
            last_price=50500.0,
            timestamp=datetime.now(timezone.utc),
            last_closed_bar=candle_above
        )
        metrics = MetricsSnapshot(timestamp=datetime.now(timezone.utc))
        
        assert check_confirmation_gates(plan_rt, market, cfg, metrics, 50000.0, False)
        
        # Candle closed below entry level
        candle_below = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=51000.0, low=49000.0, close=49500.0,
            volume=1000.0, is_closed=True
        )
        market = MarketContext(
            last_price=49500.0,
            timestamp=datetime.now(timezone.utc),
            last_closed_bar=candle_below
        )
        
        assert not check_confirmation_gates(plan_rt, market, cfg, metrics, 50000.0, False)

    def test_hold_time_gate(self):
        """Test time-based confirmation gate."""
        # Set break time to 1 second ago
        break_time = datetime.now(timezone.utc) - timedelta(seconds=1)
        plan_rt = PlanRuntimeState(
            state=PlanLifecycleState.PENDING,
            break_seen=True,
            break_ts=break_time
        )
        
        cfg = BreakoutParameters(
            confirm_close=False,
            confirm_time_ms=500,  # 500ms hold time
            min_rvol=0.0,
            ob_sweep_check=False
        )
        
        market = MarketContext(
            last_price=52000.0,  # Above entry for long
            timestamp=datetime.now(timezone.utc)
        )
        metrics = MetricsSnapshot(timestamp=datetime.now(timezone.utc))
        
        # Should pass - held for 1000ms > 500ms required
        assert check_confirmation_gates(plan_rt, market, cfg, metrics, 50000.0, False)
        
        # Test insufficient hold time
        recent_break = datetime.now(timezone.utc) - timedelta(milliseconds=200)
        plan_rt_recent = PlanRuntimeState(
            state=PlanLifecycleState.PENDING,
            break_seen=True,
            break_ts=recent_break
        )
        
        assert not check_confirmation_gates(plan_rt_recent, market, cfg, metrics, 50000.0, False)

    def test_orderbook_sweep_gate(self):
        """Test order book sweep confirmation gate."""
        plan_rt = PlanRuntimeState(state=PlanLifecycleState.PENDING, break_seen=True)
        cfg = BreakoutParameters(
            ob_sweep_check=True,
            min_rvol=0.0,
            confirm_close=False,
            confirm_time_ms=0,
            min_break_range_atr=0.0
        )
        
        market = MarketContext(
            last_price=52000.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        # No sweep detected
        metrics_no_sweep = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            ob_sweep_detected=False
        )
        assert not check_confirmation_gates(plan_rt, market, cfg, metrics_no_sweep, 50000.0, False)
        
        # Wrong side sweep (bid for long breakout)
        metrics_wrong_side = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            ob_sweep_detected=True,
            ob_sweep_side='bid'
        )
        assert not check_confirmation_gates(plan_rt, market, cfg, metrics_wrong_side, 50000.0, False)
        
        # Correct side sweep (ask for long breakout)
        metrics_correct_side = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            ob_sweep_detected=True,
            ob_sweep_side='ask'
        )
        assert check_confirmation_gates(plan_rt, market, cfg, metrics_correct_side, 50000.0, False)


class TestUtilityFunctions:
    """Test utility functions."""

    def test_calc_penetration_distance(self):
        """Test penetration distance calculation."""
        entry_price = 50000.0
        cfg = BreakoutParameters(penetration_pct=0.05, penetration_natr_mult=0.25)
        
        # No NATR - use percentage only
        distance = calc_penetration_distance(entry_price, cfg)
        assert distance == 2500.0  # 5% of 50000
        
        # With NATR - use max of percentage and volatility
        distance = calc_penetration_distance(entry_price, cfg, natr_pct=2.0)
        natr_distance = 0.25 * 0.02 * 50000  # 250
        expected = max(2500.0, 250.0)  # 2500
        assert distance == expected
        
        # High NATR dominates
        distance = calc_penetration_distance(entry_price, cfg, natr_pct=15.0)
        natr_distance = 0.25 * 0.15 * 50000  # 1875
        expected = max(2500.0, 1875.0)  # 2500
        assert distance == expected

    def test_calc_retest_band(self):
        """Test retest band calculation."""
        entry_price = 50000.0
        cfg = BreakoutParameters(retest_band_pct=0.03)
        
        band = calc_retest_band(entry_price, cfg)
        assert band == 1500.0  # 3% of 50000

    def test_check_fakeout_close(self):
        """Test fakeout close detection."""
        # Long breakout - fakeout if close below entry
        candle_fakeout = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=52000.0, low=49000.0, close=49500.0,
            volume=1000.0, is_closed=True
        )
        assert check_fakeout_close(candle_fakeout, 50000.0, False)  # Long
        
        candle_valid = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=52000.0, low=49500.0, close=51000.0,
            volume=1000.0, is_closed=True
        )
        assert not check_fakeout_close(candle_valid, 50000.0, False)  # Long
        
        # Short breakout - fakeout if close above entry
        assert check_fakeout_close(candle_valid, 50000.0, True)  # Short
        assert not check_fakeout_close(candle_fakeout, 50000.0, True)  # Short

    def test_bar_closed_beyond(self):
        """Test bar close beyond level check."""
        candle = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=52000.0, low=49000.0, close=51000.0,
            volume=1000.0, is_closed=True
        )
        
        # Long - close above entry
        assert bar_closed_beyond(candle, 50000.0, False)
        assert not bar_closed_beyond(candle, 52000.0, False)
        
        # Short - close below entry
        assert not bar_closed_beyond(candle, 50000.0, True)
        assert bar_closed_beyond(candle, 52000.0, True)
        
        # Not closed candle
        candle_open = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=52000.0, low=49000.0, close=51000.0,
            volume=1000.0, is_closed=False
        )
        assert not bar_closed_beyond(candle_open, 50000.0, False)