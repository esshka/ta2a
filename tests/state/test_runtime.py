"""Tests for runtime state management."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from ta2_app.state.runtime import (
    PlanRuntimeManager, SignalEmitter, StateManager, state_manager
)
from ta2_app.state.models import (
    PlanRuntimeState, BreakoutParameters, StateTransition,
    PlanLifecycleState, BreakoutSubState, InvalidationReason
)
from ta2_app.models.metrics import MetricsSnapshot


class TestPlanRuntimeManager:
    """Test PlanRuntimeManager class."""

    def test_get_or_create_state_new(self):
        """Test creating new plan state."""
        manager = PlanRuntimeManager()
        
        state = manager.get_or_create_state("test-plan-001")
        
        assert state.state == PlanLifecycleState.PENDING
        assert state.substate == BreakoutSubState.NONE
        assert "test-plan-001" in manager.plan_states

    def test_get_or_create_state_existing(self):
        """Test getting existing plan state."""
        manager = PlanRuntimeManager()
        
        # Create initial state
        initial_state = manager.get_or_create_state("test-plan-001")
        
        # Modify state manually
        modified_state = initial_state.with_break_seen(datetime.now(timezone.utc))
        manager.plan_states["test-plan-001"] = modified_state
        
        # Should return existing (modified) state
        retrieved_state = manager.get_or_create_state("test-plan-001")
        assert retrieved_state.break_seen is True

    def test_update_state(self):
        """Test updating plan state."""
        manager = PlanRuntimeManager()
        
        old_state = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        new_state = PlanRuntimeState(state=PlanLifecycleState.ARMED)
        
        manager.update_state("test-plan", new_state, emit_signal=False)
        
        assert manager.plan_states["test-plan"] == new_state
        assert len(manager.signal_queue) == 0  # No signal emitted

    def test_update_state_with_signal(self):
        """Test updating state with signal emission."""
        manager = PlanRuntimeManager()
        
        new_state = PlanRuntimeState(state=PlanLifecycleState.TRIGGERED)
        context = {"entry_mode": "momentum", "strength_score": 85.0}
        
        manager.update_state("test-plan", new_state, emit_signal=True, signal_context=context)
        
        assert manager.plan_states["test-plan"] == new_state
        assert len(manager.signal_queue) == 1
        
        signal = manager.signal_queue[0]
        assert signal["plan_id"] == "test-plan"
        assert signal["state"] == "triggered"
        assert signal["context"] == context

    @patch('ta2_app.state.runtime.transition_handler')
    def test_process_plan_tick_success(self, mock_handler):
        """Test successful plan tick processing."""
        manager = PlanRuntimeManager()
        
        # Mock transition handler
        timestamp = datetime.now(timezone.utc)
        expected_transition = StateTransition(
            new_state=PlanLifecycleState.TRIGGERED,
            new_substate=BreakoutSubState.NONE,
            timestamp=timestamp,
            should_emit_signal=True,
            signal_context={"entry_mode": "momentum"}
        )
        
        mock_handler.evaluate_and_transition.return_value = expected_transition
        mock_handler.apply_transition.return_value = PlanRuntimeState(
            state=PlanLifecycleState.TRIGGERED,
            signal_emitted=True
        )
        
        plan_data = {"id": "test-plan", "entry_price": 50000.0, "direction": "long"}
        market_context = {"last_price": 52000.0, "timestamp": timestamp}
        cfg = BreakoutParameters()
        metrics = MetricsSnapshot(timestamp=timestamp)
        
        result = manager.process_plan_tick("test-plan", plan_data, market_context, cfg, metrics)
        
        assert result == expected_transition
        mock_handler.evaluate_and_transition.assert_called_once()
        mock_handler.apply_transition.assert_called_once()

    def test_process_plan_tick_terminal_state(self):
        """Test processing tick for plan in terminal state."""
        manager = PlanRuntimeManager()
        
        # Set plan to terminal state
        terminal_state = PlanRuntimeState(state=PlanLifecycleState.TRIGGERED)
        manager.plan_states["test-plan"] = terminal_state
        
        plan_data = {"id": "test-plan"}
        result = manager.process_plan_tick("test-plan", plan_data, {}, BreakoutParameters(), None)
        
        assert result is None  # Should skip processing

    def test_get_state(self):
        """Test getting plan state."""
        manager = PlanRuntimeManager()
        
        # Non-existent plan
        assert manager.get_state("nonexistent") is None
        
        # Existing plan
        state = PlanRuntimeState(state=PlanLifecycleState.ARMED)
        manager.plan_states["test-plan"] = state
        assert manager.get_state("test-plan") == state

    def test_remove_plan(self):
        """Test removing plan from tracking."""
        manager = PlanRuntimeManager()
        
        # Add plan
        state = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        manager.plan_states["test-plan"] = state
        
        # Remove plan
        manager.remove_plan("test-plan")
        assert "test-plan" not in manager.plan_states

    def test_get_active_plans(self):
        """Test getting active (non-terminal) plans."""
        manager = PlanRuntimeManager()
        
        # Add plans in various states
        manager.plan_states["pending"] = PlanRuntimeState(state=PlanLifecycleState.PENDING)
        manager.plan_states["armed"] = PlanRuntimeState(state=PlanLifecycleState.ARMED)
        manager.plan_states["triggered"] = PlanRuntimeState(state=PlanLifecycleState.TRIGGERED)
        manager.plan_states["invalid"] = PlanRuntimeState(state=PlanLifecycleState.INVALID)
        manager.plan_states["expired"] = PlanRuntimeState(state=PlanLifecycleState.EXPIRED)
        
        active = manager.get_active_plans()
        
        assert "pending" in active
        assert "armed" in active
        assert "triggered" not in active  # Terminal
        assert "invalid" not in active    # Terminal
        assert "expired" not in active    # Terminal

    def test_get_pending_signals(self):
        """Test getting and clearing pending signals."""
        manager = PlanRuntimeManager()
        
        # Add signals
        signal1 = {"plan_id": "plan1", "state": "triggered"}
        signal2 = {"plan_id": "plan2", "state": "invalid"}
        manager.signal_queue = [signal1, signal2]
        
        # Get signals
        signals = manager.get_pending_signals()
        
        assert len(signals) == 2
        assert signal1 in signals
        assert signal2 in signals
        assert len(manager.signal_queue) == 0  # Should be cleared


class TestSignalEmitter:
    """Test SignalEmitter class."""

    def test_emit_signal_basic(self):
        """Test basic signal emission."""
        emitter = SignalEmitter()
        
        signal_data = {
            "plan_id": "test-plan",
            "state": "triggered",
            "runtime": {
                "armed_at": "2023-01-01T12:00:00Z",
                "triggered_at": "2023-01-01T12:05:00Z"
            },
            "timestamp": "2023-01-01T12:05:00Z",
            "context": {"last_price": 52000.0, "entry_mode": "momentum"}
        }
        
        metrics = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            rvol=2.0,
            natr_pct=1.5,
            atr=500.0,
            pinbar='bullish',
            ob_sweep_detected=True,
            ob_sweep_side='ask'
        )
        
        result = emitter.emit_signal("test-plan", signal_data, metrics)
        
        assert result["plan_id"] == "test-plan"
        assert result["state"] == "triggered"
        assert result["last_price"] == 52000.0
        assert result["entry_mode"] == "momentum"
        assert result["metrics"]["rvol"] == 2.0
        assert result["metrics"]["pinbar"] is True
        assert result["strength_score"] > 0

    def test_emit_signal_idempotency(self):
        """Test signal emission idempotency."""
        emitter = SignalEmitter()
        
        signal_data = {
            "plan_id": "test-plan",
            "state": "triggered",
            "runtime": {},
            "timestamp": "2023-01-01T12:00:00Z"
        }
        
        # First emission
        result1 = emitter.emit_signal("test-plan", signal_data, None)
        assert result1["plan_id"] == "test-plan"
        
        # Second emission - should be skipped
        result2 = emitter.emit_signal("test-plan", signal_data, None)
        assert result2 == {}  # Empty dict indicates skipped
    
    def test_emit_signal_hash_based_idempotency(self):
        """Test enhanced hash-based idempotency detection."""
        emitter = SignalEmitter()
        
        # Same signal data should trigger hash-based deduplication
        signal_data = {
            "plan_id": "test-plan",
            "state": "triggered",
            "runtime": {},
            "timestamp": "2023-01-01T12:00:00Z"
        }
        
        # First emission
        result1 = emitter.emit_signal("test-plan", signal_data, None)
        assert result1["plan_id"] == "test-plan"
        
        # Second emission with same data - should be skipped by hash check
        result2 = emitter.emit_signal("test-plan", signal_data, None)
        assert result2 == {}  # Empty dict indicates skipped
        
        # Different timestamp should allow emission
        signal_data_new = signal_data.copy()
        signal_data_new["timestamp"] = "2023-01-01T12:01:00Z"
        result3 = emitter.emit_signal("test-plan", signal_data_new, None)
        assert result3 == {}  # Should still be skipped due to state-based check
        
        # Different plan should allow emission
        signal_data_new_plan = signal_data.copy()
        signal_data_new_plan["plan_id"] = "test-plan-2"
        result4 = emitter.emit_signal("test-plan-2", signal_data_new_plan, None)
        assert result4["plan_id"] == "test-plan-2"  # Should succeed
    
    def test_emit_signal_different_states_allowed(self):
        """Test that different states for same plan are allowed."""
        emitter = SignalEmitter()
        
        # First signal state
        signal_data1 = {
            "plan_id": "test-plan",
            "state": "triggered",
            "runtime": {},
            "timestamp": "2023-01-01T12:00:00Z"
        }
        
        # Second signal state
        signal_data2 = {
            "plan_id": "test-plan",
            "state": "invalid",
            "runtime": {},
            "timestamp": "2023-01-01T12:01:00Z"
        }
        
        # Both should succeed
        result1 = emitter.emit_signal("test-plan", signal_data1, None)
        assert result1["plan_id"] == "test-plan"
        assert result1["state"] == "triggered"
        
        result2 = emitter.emit_signal("test-plan", signal_data2, None)
        assert result2["plan_id"] == "test-plan"
        assert result2["state"] == "invalid"
    
    def test_emit_signal_clear_plan_signals(self):
        """Test that clearing plan signals resets idempotency tracking."""
        emitter = SignalEmitter()
        
        signal_data = {
            "plan_id": "test-plan",
            "state": "triggered",
            "runtime": {},
            "timestamp": "2023-01-01T12:00:00Z"
        }
        
        # First emission
        result1 = emitter.emit_signal("test-plan", signal_data, None)
        assert result1["plan_id"] == "test-plan"
        
        # Second emission - should be skipped
        result2 = emitter.emit_signal("test-plan", signal_data, None)
        assert result2 == {}
        
        # Clear plan signals
        emitter.clear_plan_signals("test-plan")
        
        # Should now allow emission again
        result3 = emitter.emit_signal("test-plan", signal_data, None)
        assert result3["plan_id"] == "test-plan"
    
    def test_emit_signal_concurrent_safety(self):
        """Test idempotency with concurrent signal emissions."""
        import threading
        import time
        
        emitter = SignalEmitter()
        results = []
        
        def emit_signal_worker():
            signal_data = {
                "plan_id": "test-plan",
                "state": "triggered",
                "runtime": {},
                "timestamp": "2023-01-01T12:00:00Z"
            }
            result = emitter.emit_signal("test-plan", signal_data, None)
            results.append(result)
        
        # Start multiple threads trying to emit the same signal
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=emit_signal_worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Only one should have succeeded
        successful_results = [r for r in results if r != {}]
        assert len(successful_results) == 1
        assert successful_results[0]["plan_id"] == "test-plan"
        
        # Others should be empty (skipped)
        empty_results = [r for r in results if r == {}]
        assert len(empty_results) == 4

    def test_format_metrics(self):
        """Test metrics formatting."""
        emitter = SignalEmitter()
        
        metrics = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            rvol=1.8,
            natr_pct=2.5,
            atr=300.0,
            pinbar='bearish',
            ob_sweep_detected=False,
            ob_imbalance_long=1.2,
            ob_imbalance_short=0.8
        )
        
        formatted = emitter._format_metrics(metrics)
        
        assert formatted["rvol"] == 1.8
        assert formatted["natr_pct"] == 2.5
        assert formatted["atr"] == 300.0
        assert formatted["pinbar"] is True
        assert formatted["pinbar_type"] == 'bearish'
        assert formatted["ob_sweep_detected"] is False
        assert formatted["ob_imbalance_long"] == 1.2

    def test_calculate_strength_score(self):
        """Test strength score calculation."""
        emitter = SignalEmitter()
        
        # No metrics - baseline only
        score = emitter._calculate_strength_score(None, {})
        assert score == 30.0
        
        # Good metrics
        good_metrics = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            rvol=3.0,           # High volume
            natr_pct=2.0,       # Good volatility regime
            pinbar='bullish',   # Pinbar pattern
            ob_sweep_detected=True  # Order book sweep
        )
        
        score = emitter._calculate_strength_score(good_metrics, {})
        assert score > 80.0  # Should get high score
        
        # Poor metrics
        poor_metrics = MetricsSnapshot(
            timestamp=datetime.now(timezone.utc),
            rvol=0.8,           # Low volume
            natr_pct=15.0,      # Too high volatility
            pinbar=None,        # No pinbar
            ob_sweep_detected=False  # No sweep
        )
        
        score = emitter._calculate_strength_score(poor_metrics, {})
        assert score == 30.0  # Should get baseline only

    def test_clear_plan_signals(self):
        """Test clearing plan signal tracking."""
        emitter = SignalEmitter()
        
        # Add emitted signals
        emitter.emitted_signals["plan1"] = {"triggered", "invalid"}
        emitter.emitted_signals["plan2"] = {"triggered"}
        
        # Clear plan1
        emitter.clear_plan_signals("plan1")
        
        assert "plan1" not in emitter.emitted_signals
        assert "plan2" in emitter.emitted_signals


class TestStateManager:
    """Test StateManager orchestrator class."""

    def test_process_market_tick(self):
        """Test processing market tick for multiple plans."""
        manager = StateManager()
        
        # Mock the runtime manager to return signals
        with patch.object(manager.runtime_manager, 'process_plan_tick') as mock_process:
            with patch.object(manager.runtime_manager, 'get_pending_signals') as mock_pending:
                with patch.object(manager.signal_emitter, 'emit_signal') as mock_emit:
                    
                    # Setup mocks
                    mock_process.return_value = Mock()  # Some transition
                    mock_pending.return_value = [
                        {
                            "plan_id": "plan1",
                            "state": "triggered",
                            "context": {}
                        }
                    ]
                    mock_emit.return_value = {
                        "plan_id": "plan1",
                        "state": "triggered",
                        "strength_score": 85.0
                    }
                    
                    # Process tick
                    plans = [{"id": "plan1", "instrument_id": "BTC-USD"}]
                    market_data = {"last_price": 50000.0}
                    metrics_by_plan = {"plan1": MetricsSnapshot(timestamp=datetime.now(timezone.utc))}
                    config_by_plan = {"plan1": BreakoutParameters()}
                    
                    signals = manager.process_market_tick(
                        plans, market_data, metrics_by_plan, config_by_plan
                    )
                    
                    assert len(signals) == 1
                    assert signals[0]["plan_id"] == "plan1"

    def test_get_plan_state(self):
        """Test getting plan state via manager."""
        manager = StateManager()
        
        with patch.object(manager.runtime_manager, 'get_state') as mock_get:
            mock_get.return_value = PlanRuntimeState(state=PlanLifecycleState.ARMED)
            
            result = manager.get_plan_state("test-plan")
            assert result is not None
            mock_get.assert_called_once_with("test-plan")

    def test_remove_plan(self):
        """Test removing plan via manager."""
        manager = StateManager()
        
        with patch.object(manager.runtime_manager, 'remove_plan') as mock_remove_rt:
            with patch.object(manager.signal_emitter, 'clear_plan_signals') as mock_clear_sig:
                
                manager.remove_plan("test-plan")
                
                mock_remove_rt.assert_called_once_with("test-plan")
                mock_clear_sig.assert_called_once_with("test-plan")

    def test_get_active_plan_count(self):
        """Test getting active plan count."""
        manager = StateManager()
        
        with patch.object(manager.runtime_manager, 'get_active_plans') as mock_active:
            mock_active.return_value = ["plan1", "plan2", "plan3"]
            
            count = manager.get_active_plan_count()
            assert count == 3


class TestModuleLevelStateManager:
    """Test module-level state manager instance."""

    def test_state_manager_instance(self):
        """Test state_manager module instance."""
        assert isinstance(state_manager, StateManager)

    def test_state_manager_is_singleton(self):
        """Test that state_manager is reused."""
        from ta2_app.state.runtime import state_manager as sm1
        assert state_manager is sm1


class TestSignalEmissionWithMarketTime:
    """Test signal emission uses market time correctly."""

    def test_signal_emission_uses_market_time(self):
        """Test that signal emission uses market time from context."""
        manager = PlanRuntimeManager()
        
        # Market time from context
        market_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        market_context = {"timestamp": market_time}
        
        # Create a state that will emit a signal
        state = PlanRuntimeState(
            state=PlanLifecycleState.TRIGGERED,
            substate=BreakoutSubState.NONE,
            signal_emitted=False  # Should emit
        )
        
        # Update state with market context
        manager.update_state(
            plan_id="test-plan",
            new_state=state,
            emit_signal=True,
            signal_context={"test": "context"},
            market_context=market_context
        )
        
        # Check that signal was queued with market time
        signals = manager.get_pending_signals()
        assert len(signals) == 1
        
        signal = signals[0]
        assert signal["plan_id"] == "test-plan"
        assert signal["timestamp"] == market_time.isoformat()
        assert signal["context"]["test"] == "context"

    def test_signal_emission_fallback_to_wall_clock(self):
        """Test that signal emission falls back to wall-clock time when no market time."""
        manager = PlanRuntimeManager()
        
        # No market context provided
        state = PlanRuntimeState(
            state=PlanLifecycleState.TRIGGERED,
            substate=BreakoutSubState.NONE,
            signal_emitted=False
        )
        
        with patch('ta2_app.utils.time.datetime') as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            # Update state without market context
            manager.update_state(
                plan_id="test-plan",
                new_state=state,
                emit_signal=True,
                signal_context={}
            )
            
            # Check that signal was queued with wall-clock time
            signals = manager.get_pending_signals()
            assert len(signals) == 1
            
            signal = signals[0]
            assert signal["timestamp"] == mock_now.isoformat()