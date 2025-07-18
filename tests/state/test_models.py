"""Tests for state machine data models."""

import pytest
from datetime import datetime, timezone

from ta2_app.state.models import (
    PlanRuntimeState, BreakoutParameters, StateTransition, MarketContext,
    PlanLifecycleState, BreakoutSubState, InvalidationReason, InvalidationCondition
)


class TestPlanRuntimeState:
    """Test PlanRuntimeState data model."""

    def test_initial_state(self):
        """Test initial state creation."""
        state = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        
        assert state.state == PlanLifecycleState.PENDING
        assert state.substate == BreakoutSubState.NONE
        assert state.break_ts is None
        assert state.armed_at is None
        assert state.triggered_at is None
        assert state.invalid_reason is None
        assert state.break_seen is False
        assert state.break_confirmed is False
        assert state.signal_emitted is False

    def test_with_state_transition(self):
        """Test state transition helper method."""
        initial = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        timestamp = datetime.now(timezone.utc)
        
        # Test transition to ARMED
        armed = initial.with_state(
            new_state=PlanLifecycleState.ARMED,
            substate=BreakoutSubState.BREAK_CONFIRMED,
            timestamp=timestamp
        )
        
        assert armed.state == PlanLifecycleState.ARMED
        assert armed.substate == BreakoutSubState.BREAK_CONFIRMED
        assert armed.armed_at == timestamp
        assert armed.triggered_at is None  # Should remain None
        
        # Test transition to TRIGGERED
        triggered = armed.with_state(
            new_state=PlanLifecycleState.TRIGGERED,
            timestamp=timestamp
        )
        
        assert triggered.state == PlanLifecycleState.TRIGGERED
        assert triggered.triggered_at == timestamp
        assert triggered.armed_at == timestamp  # Should be preserved

    def test_with_break_seen(self):
        """Test break seen helper method."""
        initial = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        timestamp = datetime.now(timezone.utc)
        
        break_seen = initial.with_break_seen(timestamp)
        
        assert break_seen.substate == BreakoutSubState.BREAK_SEEN
        assert break_seen.break_ts == timestamp
        assert break_seen.break_seen is True
        assert break_seen.break_confirmed is False

    def test_with_break_confirmed(self):
        """Test break confirmed helper method."""
        initial = PlanRuntimeState(
            state=PlanLifecycleState.PENDING,
            substate=BreakoutSubState.BREAK_SEEN,
            break_seen=True
        )
        timestamp = datetime.now(timezone.utc)
        
        confirmed = initial.with_break_confirmed(timestamp)
        
        assert confirmed.state == PlanLifecycleState.ARMED
        assert confirmed.substate == BreakoutSubState.BREAK_CONFIRMED
        assert confirmed.armed_at == timestamp
        assert confirmed.break_confirmed is True

    def test_with_signal_emitted(self):
        """Test signal emission helper method."""
        initial = PlanRuntimeState(state=PlanLifecycleState.TRIGGERED)
        
        emitted = initial.with_signal_emitted()
        
        assert emitted.signal_emitted is True
        assert emitted.state == initial.state  # Other fields preserved


class TestBreakoutParameters:
    """Test BreakoutParameters configuration model."""

    def test_default_values(self):
        """Test default parameter values match dev_proto.md section 7."""
        params = BreakoutParameters()
        
        # Penetration thresholds
        assert params.penetration_pct == 0.05
        assert params.penetration_natr_mult == 0.25
        
        # Volume confirmation
        assert params.min_rvol == 1.5
        
        # Confirmation gates
        assert params.confirm_close is True
        assert params.confirm_time_ms == 750
        
        # Retest logic
        assert params.allow_retest_entry is False
        assert params.retest_band_pct == 0.03
        
        # Invalidation rules
        assert params.fakeout_close_invalidate is True
        
        # Order book analysis
        assert params.ob_sweep_check is True
        
        # Volatility filters
        assert params.min_break_range_atr == 0.5

    def test_custom_values(self):
        """Test custom parameter values."""
        params = BreakoutParameters(
            penetration_pct=0.1,
            min_rvol=2.0,
            confirm_close=False,
            allow_retest_entry=True
        )
        
        assert params.penetration_pct == 0.1
        assert params.min_rvol == 2.0
        assert params.confirm_close is False
        assert params.allow_retest_entry is True
        # Other params should use defaults
        assert params.penetration_natr_mult == 0.25


class TestStateTransition:
    """Test StateTransition model."""

    def test_basic_transition(self):
        """Test basic state transition creation."""
        timestamp = datetime.now(timezone.utc)
        transition = StateTransition(
            new_state=PlanLifecycleState.ARMED,
            new_substate=BreakoutSubState.BREAK_CONFIRMED,
            timestamp=timestamp,
            should_emit_signal=True
        )
        
        assert transition.new_state == PlanLifecycleState.ARMED
        assert transition.new_substate == BreakoutSubState.BREAK_CONFIRMED
        assert transition.timestamp == timestamp
        assert transition.should_emit_signal is True
        assert transition.invalid_reason is None
        assert transition.signal_context is None

    def test_invalidation_transition(self):
        """Test invalidation transition."""
        timestamp = datetime.now(timezone.utc)
        transition = StateTransition(
            new_state=PlanLifecycleState.INVALID,
            new_substate=BreakoutSubState.NONE,
            timestamp=timestamp,
            should_emit_signal=True,
            invalid_reason=InvalidationReason.FAKEOUT_CLOSE
        )
        
        assert transition.new_state == PlanLifecycleState.INVALID
        assert transition.invalid_reason == InvalidationReason.FAKEOUT_CLOSE


class TestMarketContext:
    """Test MarketContext model."""

    def test_basic_context(self):
        """Test basic market context creation."""
        timestamp = datetime.now(timezone.utc)
        context = MarketContext(
            last_price=50000.0,
            timestamp=timestamp,
            atr=100.0,
            natr_pct=2.0,
            rvol=1.8
        )
        
        assert context.last_price == 50000.0
        assert context.timestamp == timestamp
        assert context.atr == 100.0
        assert context.natr_pct == 2.0
        assert context.rvol == 1.8
        assert context.pinbar_detected is False
        assert context.ob_sweep_detected is False

    def test_full_context(self):
        """Test market context with all fields."""
        timestamp = datetime.now(timezone.utc)
        context = MarketContext(
            last_price=50000.0,
            timestamp=timestamp,
            atr=100.0,
            natr_pct=2.0,
            rvol=1.8,
            bar_range=150.0,
            pinbar_detected=True,
            ob_sweep_detected=True,
            ob_sweep_side='bid'
        )
        
        assert context.bar_range == 150.0
        assert context.pinbar_detected is True
        assert context.ob_sweep_detected is True
        assert context.ob_sweep_side == 'bid'


class TestInvalidationCondition:
    """Test InvalidationCondition model."""

    def test_price_above_condition(self):
        """Test price above invalidation condition."""
        condition = InvalidationCondition(
            condition_type="price_above",
            level=55000.0
        )
        
        timestamp = datetime.now(timezone.utc)
        plan_created = datetime.now(timezone.utc)
        
        # Price below level - should not trigger
        assert not condition.check(54000.0, timestamp, plan_created)
        
        # Price above level - should trigger
        assert condition.check(56000.0, timestamp, plan_created)

    def test_price_below_condition(self):
        """Test price below invalidation condition."""
        condition = InvalidationCondition(
            condition_type="price_below",
            level=45000.0
        )
        
        timestamp = datetime.now(timezone.utc)
        plan_created = datetime.now(timezone.utc)
        
        # Price above level - should not trigger
        assert not condition.check(46000.0, timestamp, plan_created)
        
        # Price below level - should trigger
        assert condition.check(44000.0, timestamp, plan_created)

    def test_time_limit_condition(self):
        """Test time limit invalidation condition."""
        condition = InvalidationCondition(
            condition_type="time_limit",
            duration_seconds=3600  # 1 hour
        )
        
        plan_created = datetime.now(timezone.utc)
        
        # Within time limit - should not trigger
        timestamp_30min = datetime.fromtimestamp(
            plan_created.timestamp() + 1800, tz=timezone.utc
        )
        assert not condition.check(50000.0, timestamp_30min, plan_created)
        
        # Beyond time limit - should trigger
        timestamp_2hours = datetime.fromtimestamp(
            plan_created.timestamp() + 7200, tz=timezone.utc
        )
        assert condition.check(50000.0, timestamp_2hours, plan_created)

    def test_invalid_condition_type(self):
        """Test invalid condition type."""
        condition = InvalidationCondition(
            condition_type="invalid_type"
        )
        
        timestamp = datetime.now(timezone.utc)
        plan_created = datetime.now(timezone.utc)
        
        # Should return False for unknown condition types
        assert not condition.check(50000.0, timestamp, plan_created)


class TestEnums:
    """Test enum definitions."""

    def test_plan_lifecycle_state_values(self):
        """Test PlanLifecycleState enum values."""
        assert PlanLifecycleState.PENDING.value == "pending"
        assert PlanLifecycleState.ARMED.value == "armed"
        assert PlanLifecycleState.TRIGGERED.value == "triggered"
        assert PlanLifecycleState.INVALID.value == "invalid"
        assert PlanLifecycleState.EXPIRED.value == "expired"

    def test_breakout_substate_values(self):
        """Test BreakoutSubState enum values."""
        assert BreakoutSubState.NONE.value == "none"
        assert BreakoutSubState.BREAK_SEEN.value == "break_seen"
        assert BreakoutSubState.BREAK_CONFIRMED.value == "break_confirmed"
        assert BreakoutSubState.RETEST_ARMED.value == "retest_armed"
        assert BreakoutSubState.RETEST_TRIGGERED.value == "retest_triggered"

    def test_invalidation_reason_values(self):
        """Test InvalidationReason enum values."""
        assert InvalidationReason.PRICE_ABOVE.value == "price_above"
        assert InvalidationReason.PRICE_BELOW.value == "price_below"
        assert InvalidationReason.STOP_LOSS.value == "stop_loss"
        assert InvalidationReason.FAKEOUT_CLOSE.value == "fakeout_close"
        assert InvalidationReason.TIME_LIMIT.value == "time_limit"