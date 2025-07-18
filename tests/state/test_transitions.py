"""Tests for state transition handlers."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from ta2_app.state.transitions import (
    StateTransitionHandler, BreakoutGateValidator, InvalidationChecker,
    transition_handler, gate_validator, invalidation_checker
)
from ta2_app.state.models import (
    PlanRuntimeState, BreakoutParameters, StateTransition,
    PlanLifecycleState, BreakoutSubState, InvalidationReason
)
from ta2_app.models.metrics import MetricsSnapshot
from ta2_app.data.models import Candle


class TestStateTransitionHandler:
    """Test StateTransitionHandler class."""

    def test_apply_transition_basic(self):
        """Test basic state transition application."""
        handler = StateTransitionHandler()
        current_state = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        timestamp = datetime.now(timezone.utc)
        
        transition = StateTransition(
            new_state=PlanLifecycleState.ARMED,
            new_substate=BreakoutSubState.BREAK_CONFIRMED,
            timestamp=timestamp,
            should_emit_signal=True
        )
        
        new_state = handler.apply_transition(current_state, transition, "test-plan")
        
        assert new_state.state == PlanLifecycleState.ARMED
        assert new_state.substate == BreakoutSubState.BREAK_CONFIRMED
        assert new_state.signal_emitted is True

    def test_apply_transition_break_seen(self):
        """Test transition to break seen state."""
        handler = StateTransitionHandler()
        current_state = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        timestamp = datetime.now(timezone.utc)
        
        transition = StateTransition(
            new_state=PlanLifecycleState.PENDING,
            new_substate=BreakoutSubState.BREAK_SEEN,
            timestamp=timestamp,
            should_emit_signal=False
        )
        
        new_state = handler.apply_transition(current_state, transition, "test-plan")
        
        assert new_state.substate == BreakoutSubState.BREAK_SEEN
        assert new_state.break_seen is True
        assert new_state.break_ts == timestamp

    def test_apply_transition_break_confirmed(self):
        """Test transition to break confirmed state."""
        handler = StateTransitionHandler()
        current_state = PlanRuntimeState(
            state=PlanLifecycleState.PENDING,
            substate=BreakoutSubState.BREAK_SEEN,
            break_seen=True
        )
        timestamp = datetime.now(timezone.utc)
        
        transition = StateTransition(
            new_state=PlanLifecycleState.ARMED,
            new_substate=BreakoutSubState.BREAK_CONFIRMED,
            timestamp=timestamp,
            should_emit_signal=False
        )
        
        new_state = handler.apply_transition(current_state, transition, "test-plan")
        
        assert new_state.state == PlanLifecycleState.ARMED
        assert new_state.substate == BreakoutSubState.BREAK_CONFIRMED
        assert new_state.break_confirmed is True
        assert new_state.armed_at == timestamp

    def test_apply_transition_invalidation(self):
        """Test transition to invalid state."""
        handler = StateTransitionHandler()
        current_state = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        timestamp = datetime.now(timezone.utc)
        
        transition = StateTransition(
            new_state=PlanLifecycleState.INVALID,
            new_substate=BreakoutSubState.NONE,
            timestamp=timestamp,
            should_emit_signal=True,
            invalid_reason=InvalidationReason.FAKEOUT_CLOSE
        )
        
        new_state = handler.apply_transition(current_state, transition, "test-plan")
        
        assert new_state.state == PlanLifecycleState.INVALID
        assert new_state.invalid_reason == InvalidationReason.FAKEOUT_CLOSE
        assert new_state.signal_emitted is True

    @patch('ta2_app.state.transitions.eval_breakout_tick')
    def test_evaluate_and_transition_success(self, mock_eval):
        """Test successful evaluation and transition."""
        handler = StateTransitionHandler()
        current_state = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        timestamp = datetime.now(timezone.utc)
        
        # Mock evaluation returns transition
        expected_transition = StateTransition(
            new_state=PlanLifecycleState.ARMED,
            new_substate=BreakoutSubState.BREAK_CONFIRMED,
            timestamp=timestamp,
            should_emit_signal=True
        )
        mock_eval.return_value = expected_transition
        
        market_context = {'last_price': 50000.0, 'timestamp': timestamp}
        cfg = BreakoutParameters()
        plan_data = {'id': 'test-plan', 'entry_price': 50000.0, 'direction': 'long'}
        metrics = MetricsSnapshot(timestamp=timestamp)
        
        result = handler.evaluate_and_transition(
            current_state, market_context, cfg, plan_data, metrics
        )
        
        assert result == expected_transition
        mock_eval.assert_called_once_with(
            plan_rt=current_state,
            market=market_context,
            cfg=cfg,
            plan_data=plan_data,
            metrics=metrics
        )

    @patch('ta2_app.state.transitions.eval_breakout_tick')
    def test_evaluate_and_transition_error(self, mock_eval):
        """Test error handling during evaluation."""
        handler = StateTransitionHandler()
        current_state = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        
        # Mock evaluation raises exception
        mock_eval.side_effect = Exception("Test error")
        
        market_context = {'last_price': 50000.0, 'timestamp': datetime.now(timezone.utc)}
        cfg = BreakoutParameters()
        plan_data = {'id': 'test-plan', 'entry_price': 50000.0, 'direction': 'long'}
        
        result = handler.evaluate_and_transition(
            current_state, market_context, cfg, plan_data, None
        )
        
        # Should return invalidation transition
        assert result is not None
        assert result.new_state == PlanLifecycleState.INVALID
        assert result.should_emit_signal is True


class TestBreakoutGateValidator:
    """Test BreakoutGateValidator class."""

    def test_validate_rvol_gate_pass(self):
        """Test RVOL gate validation - pass."""
        validator = BreakoutGateValidator()
        
        assert validator.validate_rvol_gate(2.0, 1.5, "test-plan")
        assert validator.validate_rvol_gate(1.5, 1.5, "test-plan")  # Equal

    def test_validate_rvol_gate_fail(self):
        """Test RVOL gate validation - fail."""
        validator = BreakoutGateValidator()
        
        assert not validator.validate_rvol_gate(1.2, 1.5, "test-plan")
        assert not validator.validate_rvol_gate(None, 1.5, "test-plan")

    def test_validate_rvol_gate_disabled(self):
        """Test RVOL gate validation - disabled."""
        validator = BreakoutGateValidator()
        
        assert validator.validate_rvol_gate(0.5, 0.0, "test-plan")  # Disabled
        assert validator.validate_rvol_gate(None, -1.0, "test-plan")  # Disabled

    def test_validate_volatility_gate_pass(self):
        """Test volatility gate validation - pass."""
        validator = BreakoutGateValidator()
        
        assert validator.validate_volatility_gate(1000.0, 1500.0, 0.5, "test-plan")  # 1000 >= 750
        assert validator.validate_volatility_gate(750.0, 1500.0, 0.5, "test-plan")   # Equal

    def test_validate_volatility_gate_fail(self):
        """Test volatility gate validation - fail."""
        validator = BreakoutGateValidator()
        
        assert not validator.validate_volatility_gate(500.0, 1500.0, 0.5, "test-plan")  # 500 < 750
        assert not validator.validate_volatility_gate(None, 1500.0, 0.5, "test-plan")
        assert not validator.validate_volatility_gate(1000.0, None, 0.5, "test-plan")

    def test_validate_volatility_gate_disabled(self):
        """Test volatility gate validation - disabled."""
        validator = BreakoutGateValidator()
        
        assert validator.validate_volatility_gate(100.0, 1500.0, 0.0, "test-plan")  # Disabled
        assert validator.validate_volatility_gate(None, None, -1.0, "test-plan")    # Disabled

    def test_validate_orderbook_sweep_gate_pass(self):
        """Test order book sweep gate validation - pass."""
        validator = BreakoutGateValidator()
        
        assert validator.validate_orderbook_sweep_gate(True, 'bid', 'bid', "test-plan")
        assert validator.validate_orderbook_sweep_gate(True, 'ask', 'ask', "test-plan")

    def test_validate_orderbook_sweep_gate_fail(self):
        """Test order book sweep gate validation - fail."""
        validator = BreakoutGateValidator()
        
        assert not validator.validate_orderbook_sweep_gate(False, 'bid', 'bid', "test-plan")  # No sweep
        assert not validator.validate_orderbook_sweep_gate(True, 'bid', 'ask', "test-plan")   # Wrong side
        assert not validator.validate_orderbook_sweep_gate(True, None, 'ask', "test-plan")    # No side detected


class TestInvalidationChecker:
    """Test InvalidationChecker class."""

    def test_check_price_invalidation_above(self):
        """Test price above invalidation."""
        checker = InvalidationChecker()
        
        conditions = [
            {'condition_type': 'price_above', 'level': 55000.0}
        ]
        
        # Below limit - no invalidation
        result = checker.check_price_invalidation(54000.0, conditions, "test-plan")
        assert result is None
        
        # Above limit - invalidation
        result = checker.check_price_invalidation(56000.0, conditions, "test-plan")
        assert result == InvalidationReason.PRICE_ABOVE

    def test_check_price_invalidation_below(self):
        """Test price below invalidation."""
        checker = InvalidationChecker()
        
        conditions = [
            {'condition_type': 'price_below', 'level': 45000.0}
        ]
        
        # Above limit - no invalidation
        result = checker.check_price_invalidation(46000.0, conditions, "test-plan")
        assert result is None
        
        # Below limit - invalidation
        result = checker.check_price_invalidation(44000.0, conditions, "test-plan")
        assert result == InvalidationReason.PRICE_BELOW

    def test_check_price_invalidation_multiple(self):
        """Test multiple price invalidation conditions."""
        checker = InvalidationChecker()
        
        conditions = [
            {'condition_type': 'price_above', 'level': 55000.0},
            {'condition_type': 'price_below', 'level': 45000.0}
        ]
        
        # Within range - no invalidation
        result = checker.check_price_invalidation(50000.0, conditions, "test-plan")
        assert result is None
        
        # Above upper limit
        result = checker.check_price_invalidation(56000.0, conditions, "test-plan")
        assert result == InvalidationReason.PRICE_ABOVE
        
        # Below lower limit
        result = checker.check_price_invalidation(44000.0, conditions, "test-plan")
        assert result == InvalidationReason.PRICE_BELOW

    def test_check_time_invalidation(self):
        """Test time-based invalidation."""
        checker = InvalidationChecker()
        
        plan_created = datetime.now(timezone.utc)
        conditions = [
            {'condition_type': 'time_limit', 'duration_seconds': 3600}  # 1 hour
        ]
        
        # Within time limit
        current_time = datetime.fromtimestamp(
            plan_created.timestamp() + 1800, tz=timezone.utc  # 30 minutes
        )
        result = checker.check_time_invalidation(current_time, plan_created, conditions, "test-plan")
        assert result is False
        
        # Beyond time limit
        current_time = datetime.fromtimestamp(
            plan_created.timestamp() + 7200, tz=timezone.utc  # 2 hours
        )
        result = checker.check_time_invalidation(current_time, plan_created, conditions, "test-plan")
        assert result is True

    def test_check_fakeout_invalidation_long(self):
        """Test fakeout invalidation for long breakout."""
        checker = InvalidationChecker()
        
        # Valid candle - close above entry
        valid_candle = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=52000.0, low=49500.0, close=51000.0,
            volume=1000.0, is_closed=True
        )
        result = checker.check_fakeout_invalidation(valid_candle, 50000.0, False, "test-plan")
        assert result is False
        
        # Fakeout candle - close below entry
        fakeout_candle = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=52000.0, low=49000.0, close=49500.0,
            volume=1000.0, is_closed=True
        )
        result = checker.check_fakeout_invalidation(fakeout_candle, 50000.0, False, "test-plan")
        assert result is True

    def test_check_fakeout_invalidation_short(self):
        """Test fakeout invalidation for short breakout."""
        checker = InvalidationChecker()
        
        # Valid candle - close below entry
        valid_candle = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=50500.0, low=48000.0, close=49000.0,
            volume=1000.0, is_closed=True
        )
        result = checker.check_fakeout_invalidation(valid_candle, 50000.0, True, "test-plan")
        assert result is False
        
        # Fakeout candle - close above entry
        fakeout_candle = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=52000.0, low=48000.0, close=51000.0,
            volume=1000.0, is_closed=True
        )
        result = checker.check_fakeout_invalidation(fakeout_candle, 50000.0, True, "test-plan")
        assert result is True

    def test_check_fakeout_invalidation_not_closed(self):
        """Test fakeout invalidation with non-closed candle."""
        checker = InvalidationChecker()
        
        # Non-closed candle should not trigger fakeout
        open_candle = Candle(
            ts=datetime.now(timezone.utc),
            open=50000.0, high=52000.0, low=49000.0, close=49500.0,
            volume=1000.0, is_closed=False
        )
        result = checker.check_fakeout_invalidation(open_candle, 50000.0, False, "test-plan")
        assert result is False

    def test_check_fakeout_invalidation_invalid_candle(self):
        """Test fakeout invalidation with invalid candle."""
        checker = InvalidationChecker()
        
        # None candle
        result = checker.check_fakeout_invalidation(None, 50000.0, False, "test-plan")
        assert result is False
        
        # Object without close attribute
        invalid_candle = object()
        result = checker.check_fakeout_invalidation(invalid_candle, 50000.0, False, "test-plan")
        assert result is False


class TestModuleLevelInstances:
    """Test module-level singleton instances."""

    def test_transition_handler_instance(self):
        """Test transition_handler module instance."""
        assert isinstance(transition_handler, StateTransitionHandler)

    def test_gate_validator_instance(self):
        """Test gate_validator module instance."""
        assert isinstance(gate_validator, BreakoutGateValidator)

    def test_invalidation_checker_instance(self):
        """Test invalidation_checker module instance."""
        assert isinstance(invalidation_checker, InvalidationChecker)

    def test_instances_are_singletons(self):
        """Test that instances are reused."""
        from ta2_app.state.transitions import (
            transition_handler as th1,
            gate_validator as gv1,
            invalidation_checker as ic1
        )
        
        # Should be same instances
        assert transition_handler is th1
        assert gate_validator is gv1
        assert invalidation_checker is ic1