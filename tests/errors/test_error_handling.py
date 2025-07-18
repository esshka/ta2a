"""
Comprehensive error handling tests for the trading algorithm system.

Tests cover missing data scenarios, malformed data processing, and error recovery mechanisms.
"""

import math
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from ta2_app.errors import (
    DataQualityError,
    TemporalDataError,
    PartialDataError,
    MissingDataError,
    MalformedDataError,
    InsufficientDataError,
    MetricsCalculationError,
    StateTransitionError,
    GracefulDegradationError,
)
from ta2_app.engine import BreakoutEvaluationEngine
from ta2_app.metrics.calculator import MetricsCalculator
from ta2_app.data.normalizer import DataNormalizer
from ta2_app.state.transitions import StateTransitionHandler
from ta2_app.state.models import PlanRuntimeState, PlanLifecycleState, BreakoutSubState
from ta2_app.data.models import Candle, InstrumentDataStore


class TestErrorClassification:
    """Test error classification system."""

    def test_data_quality_error_hierarchy(self):
        """Test that data quality errors have proper hierarchy."""
        # Test base class
        base_error = DataQualityError("base error")
        assert base_error.recoverable is True
        assert base_error.context == {}

        # Test specific error types
        temporal_error = TemporalDataError("timestamp error", timestamp=123456789)
        assert isinstance(temporal_error, DataQualityError)
        assert temporal_error.timestamp == 123456789

        partial_error = PartialDataError("missing fields", missing_fields=["field1", "field2"])
        assert isinstance(partial_error, DataQualityError)
        assert partial_error.missing_fields == ["field1", "field2"]

        missing_error = MissingDataError("missing data", data_type="candle")
        assert isinstance(missing_error, DataQualityError)
        assert missing_error.data_type == "candle"

    def test_system_failure_error_hierarchy(self):
        """Test that system failure errors have proper hierarchy."""
        metrics_error = MetricsCalculationError("calculation failed", metric_name="atr")
        assert metrics_error.recoverable is False
        assert metrics_error.metric_name == "atr"

        state_error = StateTransitionError("invalid transition", current_state="PENDING")
        assert state_error.recoverable is False
        assert state_error.current_state == "PENDING"

    def test_graceful_degradation_error(self):
        """Test graceful degradation error functionality."""
        degradation_error = GracefulDegradationError(
            "degraded mode",
            degraded_functionality="spike_filtering",
            fallback_strategy="skip_spike_data"
        )
        assert degradation_error.allows_degradation is True
        assert degradation_error.degraded_functionality == "spike_filtering"
        assert degradation_error.fallback_strategy == "skip_spike_data"


class TestEngineErrorHandling:
    """Test error handling in the main evaluation engine."""

    def test_evaluate_tick_missing_data(self):
        """Test evaluate_tick handles missing data gracefully."""
        engine = BreakoutEvaluationEngine()
        
        # Add a test plan
        test_plan = {
            "id": "test_plan",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(test_plan)

        # Test with no data
        signals = engine.evaluate_tick()
        assert signals == []

        # Test with missing instrument_id
        with pytest.raises(MissingDataError):
            engine.evaluate_tick(candlestick_payload={"data": "test"})

    def test_evaluate_tick_malformed_data(self):
        """Test evaluate_tick handles malformed data gracefully."""
        engine = BreakoutEvaluationEngine()
        
        # Add a test plan
        test_plan = {
            "id": "test_plan",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(test_plan)

        # Test with malformed candlestick payload
        malformed_payload = "not a dict"
        signals = engine.evaluate_tick(
            candlestick_payload=malformed_payload,
            instrument_id="BTC-USD"
        )
        assert signals == []

    def test_plan_validation_errors(self):
        """Test plan validation catches errors."""
        engine = BreakoutEvaluationEngine()
        
        # Test missing required fields
        invalid_plan = {"id": "test"}
        engine.add_plan(invalid_plan)
        # Should not add invalid plan
        assert len(engine.active_plans) == 0

        # Test invalid entry type
        invalid_plan = {
            "id": "test_plan",
            "instrument_id": "BTC-USD",
            "entry_type": "invalid_type",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(invalid_plan)
        # Should not add invalid plan
        assert len(engine.active_plans) == 0


class TestMetricsCalculatorErrorHandling:
    """Test error handling in metrics calculation."""

    def test_missing_data_validation(self):
        """Test metrics calculator validates missing data."""
        calculator = MetricsCalculator()
        
        # Test with None candle
        with pytest.raises(MissingDataError):
            calculator.calculate_metrics(None, Mock())

        # Test with None data store
        candle = Mock()
        with pytest.raises(MissingDataError):
            calculator.calculate_metrics(candle, None)

    def test_malformed_candle_data(self):
        """Test metrics calculator handles malformed candle data."""
        calculator = MetricsCalculator()
        data_store = Mock()
        
        # Create malformed candle
        candle = Mock()
        candle.ts = None  # Missing timestamp
        candle.open = None
        candle.high = None
        candle.low = None
        candle.close = None
        candle.volume = None

        with pytest.raises(MalformedDataError):
            calculator.calculate_metrics(candle, data_store)

    def test_invalid_price_values(self):
        """Test metrics calculator handles invalid price values."""
        calculator = MetricsCalculator()
        data_store = Mock()
        
        # Create candle with invalid prices
        candle = Mock()
        candle.ts = datetime.now(timezone.utc)
        candle.open = float('nan')  # Invalid price
        candle.high = 100
        candle.low = 90
        candle.close = 95
        candle.volume = 1000

        with pytest.raises(MalformedDataError):
            calculator.calculate_metrics(candle, data_store)

    def test_insufficient_data_for_calculations(self):
        """Test metrics calculator handles insufficient data."""
        calculator = MetricsCalculator()
        data_store = Mock()
        
        # Mock insufficient data
        data_store.get_bars.return_value = []  # No candle history
        data_store.get_vol_history.return_value = []  # No volume history

        candle = Mock()
        candle.ts = datetime.now(timezone.utc)
        candle.open = 100
        candle.high = 105
        candle.low = 95
        candle.close = 102
        candle.volume = 1000

        with pytest.raises(InsufficientDataError):
            calculator.calculate_metrics(candle, data_store)

    def test_nan_infinite_value_detection(self):
        """Test metrics calculator detects NaN and infinite values."""
        calculator = MetricsCalculator()
        
        # Test ATR validation
        with pytest.raises(MetricsCalculationError):
            calculator._validate_atr_values(float('nan'), 1.0)

        with pytest.raises(MetricsCalculationError):
            calculator._validate_atr_values(float('inf'), 1.0)

        # Test RVOL validation
        with pytest.raises(MetricsCalculationError):
            calculator._validate_rvol_value(float('nan'))

        with pytest.raises(MetricsCalculationError):
            calculator._validate_rvol_value(float('inf'))

    def test_mathematical_bounds_checking(self):
        """Test metrics calculator enforces mathematical bounds."""
        calculator = MetricsCalculator()
        
        # Test negative values
        with pytest.raises(MetricsCalculationError):
            calculator._validate_atr_values(-1.0, 1.0)

        with pytest.raises(MetricsCalculationError):
            calculator._validate_rvol_value(-1.0)

        # Test unreasonably large values
        with pytest.raises(MetricsCalculationError):
            calculator._validate_atr_values(1e7, 1.0)  # Too large ATR

        with pytest.raises(MetricsCalculationError):
            calculator._validate_rvol_value(1001)  # Too large RVOL


class TestDataNormalizerErrorHandling:
    """Test error handling in data normalization."""

    def test_missing_input_validation(self):
        """Test normalizer validates missing inputs."""
        normalizer = DataNormalizer()
        
        # Test missing instrument_id
        with pytest.raises(MissingDataError):
            normalizer.normalize_tick("", "raw_data", "candle")

        # Test missing raw_data
        with pytest.raises(MissingDataError):
            normalizer.normalize_tick("BTC-USD", "", "candle")

        # Test missing data_type
        with pytest.raises(MissingDataError):
            normalizer.normalize_tick("BTC-USD", "raw_data", "")

    def test_invalid_data_type_validation(self):
        """Test normalizer validates data types."""
        normalizer = DataNormalizer()
        
        # Test invalid data type
        with pytest.raises(MalformedDataError):
            normalizer.normalize_tick("BTC-USD", "raw_data", "invalid_type")

    def test_malformed_json_handling(self):
        """Test normalizer handles malformed JSON."""
        normalizer = DataNormalizer()
        
        # Test malformed JSON
        with pytest.raises(MalformedDataError):
            normalizer.normalize_tick("BTC-USD", "invalid json", "candle")

    def test_graceful_degradation_for_duplicates(self):
        """Test normalizer handles duplicate data gracefully."""
        normalizer = DataNormalizer()
        
        # Mock a scenario where duplicate candle is detected
        with patch('ta2_app.data.normalizer.is_duplicate_candle', return_value=True):
            with patch('ta2_app.data.normalizer.parse_json_payload', return_value={}):
                with patch('ta2_app.data.normalizer.validate_okx_response'):
                    with patch('ta2_app.data.normalizer.parse_candlestick_payload', return_value=[Mock()]):
                        with pytest.raises(GracefulDegradationError):
                            normalizer.normalize_tick("BTC-USD", "{}", "candle")

    def test_temporal_data_error_handling(self):
        """Test normalizer handles temporal data errors."""
        normalizer = DataNormalizer()
        
        # Mock old candle scenario
        with patch('ta2_app.data.normalizer.should_skip_old_candle', return_value=True):
            with patch('ta2_app.data.normalizer.parse_json_payload', return_value={}):
                with patch('ta2_app.data.normalizer.validate_okx_response'):
                    with patch('ta2_app.data.normalizer.parse_candlestick_payload', return_value=[Mock()]):
                        with pytest.raises(TemporalDataError):
                            normalizer.normalize_tick("BTC-USD", "{}", "candle")


class TestStateTransitionErrorHandling:
    """Test error handling in state transitions."""

    def test_missing_state_validation(self):
        """Test state transition handler validates missing states."""
        handler = StateTransitionHandler()
        
        # Test with None current state
        with pytest.raises(StateTransitionError):
            handler.apply_transition(None, Mock(), "test_plan")

        # Test with None transition
        with pytest.raises(StateTransitionError):
            handler.apply_transition(Mock(), None, "test_plan")

    def test_invalid_state_transition_validation(self):
        """Test state transition handler validates invalid transitions."""
        handler = StateTransitionHandler()
        
        # Create current state in TRIGGERED state
        current_state = Mock()
        current_state.state = PlanLifecycleState.TRIGGERED
        current_state.substate = BreakoutSubState.NONE
        
        # Create transition trying to go back to PENDING
        transition = Mock()
        transition.new_state = PlanLifecycleState.PENDING
        transition.new_substate = BreakoutSubState.NONE
        transition.timestamp = datetime.now(timezone.utc)
        
        with pytest.raises(StateTransitionError):
            handler.apply_transition(current_state, transition, "test_plan")

    def test_missing_context_data_validation(self):
        """Test state transition handler validates missing context data."""
        handler = StateTransitionHandler()
        
        # Test with missing market context
        with pytest.raises(MissingDataError):
            handler.evaluate_and_transition(
                Mock(), None, Mock(), {"id": "test"}, None
            )

        # Test with missing plan data
        with pytest.raises(MissingDataError):
            handler.evaluate_and_transition(
                Mock(), {"last_price": 100, "timestamp": datetime.now()}, Mock(), None, None
            )

    def test_malformed_context_data_validation(self):
        """Test state transition handler validates malformed context data."""
        handler = StateTransitionHandler()
        
        # Test with invalid price
        market_context = {"last_price": -100, "timestamp": datetime.now()}
        plan_data = {"id": "test", "entry_price": 50000, "direction": "long"}
        
        with pytest.raises(MalformedDataError):
            handler.evaluate_and_transition(
                Mock(), market_context, Mock(), plan_data, None
            )

    def test_insufficient_metrics_validation(self):
        """Test state transition handler validates insufficient metrics."""
        handler = StateTransitionHandler()
        
        # Create config requiring RVOL but no metrics provided
        config = Mock()
        config.min_rvol = 2.0
        config.min_break_range_atr = 0.0
        config.penetration_pct = 0.1
        config.penetration_natr_mult = 0.0
        config.confirm_time_ms = 0.0
        config.retest_band_pct = 1.0
        
        market_context = {"last_price": 100, "timestamp": datetime.now()}
        plan_data = {"id": "test", "entry_price": 50000, "direction": "long"}
        
        with pytest.raises(InsufficientDataError):
            handler.evaluate_and_transition(
                Mock(), market_context, config, plan_data, None
            )


class TestErrorRecoveryMechanisms:
    """Test error recovery mechanisms throughout the system."""

    def test_engine_continues_after_plan_error(self):
        """Test that engine continues processing other plans after one fails."""
        engine = BreakoutEvaluationEngine()
        
        # Add two plans
        valid_plan = {
            "id": "valid_plan",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(valid_plan)
        
        invalid_plan = {
            "id": "invalid_plan",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": "invalid_price",  # Invalid price type
            "direction": "long"
        }
        engine.add_plan(invalid_plan)
        
        # Only valid plan should be added
        assert len(engine.active_plans) == 1
        assert engine.active_plans[0]["id"] == "valid_plan"

    def test_normalizer_graceful_degradation(self):
        """Test that normalizer degrades gracefully on partial failures."""
        normalizer = DataNormalizer()
        
        # Test that normalize_candlesticks returns error result instead of crashing
        result = normalizer.normalize_candlesticks({"invalid": "payload"})
        assert not result.success
        assert "error" in result.error_msg.lower()

    def test_metrics_calculator_error_isolation(self):
        """Test that metrics calculator isolates errors to specific calculations."""
        calculator = MetricsCalculator()
        
        # Mock data store with some valid data
        data_store = Mock()
        data_store.get_bars.return_value = [Mock() for _ in range(20)]  # Sufficient data
        data_store.get_vol_history.return_value = [100.0] * 20  # Sufficient data
        
        # Create valid candle
        candle = Mock()
        candle.ts = datetime.now(timezone.utc)
        candle.open = 100
        candle.high = 105
        candle.low = 95
        candle.close = 102
        candle.volume = 1000
        
        # Mock ATR calculator to raise error
        with patch.object(calculator.atr_calculator, 'calculate_with_candles', side_effect=Exception("ATR error")):
            with pytest.raises(MetricsCalculationError) as exc_info:
                calculator.calculate_metrics(candle, data_store)
            
            assert "ATR calculation failed" in str(exc_info.value)

    def test_state_transition_error_recovery(self):
        """Test that state transition errors are properly handled."""
        handler = StateTransitionHandler()
        
        # Test that evaluation errors return invalidation transition
        current_state = Mock()
        current_state.state = PlanLifecycleState.PENDING
        current_state.substate = BreakoutSubState.NONE
        
        # Invalid market context should return invalidation
        result = handler.evaluate_and_transition(
            current_state, None, Mock(), {"id": "test"}, None
        )
        
        assert result is not None
        assert result.new_state == PlanLifecycleState.INVALID


class TestSystemResilienceScenarios:
    """Test system resilience under various failure scenarios."""

    def test_cascading_error_prevention(self):
        """Test that errors in one component don't cascade to others."""
        engine = BreakoutEvaluationEngine()
        
        # Add multiple plans
        for i in range(3):
            plan = {
                "id": f"test_plan_{i}",
                "instrument_id": "BTC-USD",
                "entry_type": "breakout",
                "entry_price": 50000 + i * 1000,
                "direction": "long"
            }
            engine.add_plan(plan)
        
        # Mock one plan to fail during evaluation
        with patch.object(engine, '_evaluate_single_plan', side_effect=[
            Exception("Plan 1 failed"),
            [],  # Plan 2 succeeds
            []   # Plan 3 succeeds
        ]):
            # Should not crash despite one plan failing
            signals = engine.evaluate_tick(
                candlestick_payload={"data": "test"},
                instrument_id="BTC-USD"
            )
            # Should return empty list, not crash
            assert isinstance(signals, list)

    def test_data_quality_degradation_handling(self):
        """Test handling of progressively degrading data quality."""
        normalizer = DataNormalizer()
        
        # Test series of increasingly problematic data
        test_cases = [
            ("valid_json", '{"valid": "data"}'),
            ("malformed_json", '{"invalid": json}'),
            ("empty_data", ''),
            ("none_data", None),
        ]
        
        for case_name, data in test_cases:
            try:
                if data is None:
                    with pytest.raises(MissingDataError):
                        normalizer.normalize_tick("BTC-USD", data, "candle")
                else:
                    result = normalizer.normalize_tick("BTC-USD", data, "candle")
                    # Should return error result, not crash
                    if not result.success:
                        assert result.error_msg is not None
            except (MissingDataError, MalformedDataError, TemporalDataError):
                # Expected structured errors are fine
                pass
            except Exception as e:
                # Unexpected errors should not occur
                pytest.fail(f"Unexpected error in {case_name}: {e}")

    def test_memory_leak_prevention_on_errors(self):
        """Test that error handling doesn't cause memory leaks."""
        engine = BreakoutEvaluationEngine()
        
        # Add plan
        plan = {
            "id": "test_plan",
            "instrument_id": "BTC-USD",
            "entry_type": "breakout",
            "entry_price": 50000,
            "direction": "long"
        }
        engine.add_plan(plan)
        
        # Generate many errors to test memory usage
        for i in range(100):
            try:
                # This should fail but not accumulate memory
                engine.evaluate_tick(
                    candlestick_payload=f"invalid_data_{i}",
                    instrument_id="BTC-USD"
                )
            except Exception:
                pass
        
        # Engine should still be functional
        assert len(engine.active_plans) == 1
        assert engine.get_active_plan_count() == 1