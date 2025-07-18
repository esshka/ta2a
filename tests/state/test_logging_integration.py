"""Tests for comprehensive logging integration in state machine components."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
import json

from ta2_app.state.transitions import (
    StateTransitionHandler, BreakoutGateValidator, InvalidationChecker
)
from ta2_app.state.machine import eval_breakout_tick
from ta2_app.state.models import (
    PlanRuntimeState, BreakoutParameters, StateTransition, MarketContext,
    PlanLifecycleState, BreakoutSubState, InvalidationReason
)
from ta2_app.models.metrics import MetricsSnapshot
from ta2_app.data.models import Candle
from ta2_app.logging.config import configure_logging, get_gating_logger, get_state_logger


class TestLoggingIntegration:
    """Test comprehensive logging integration for gating decisions and state transitions."""

    def setup_method(self):
        """Set up test environment with logging capture."""
        # Configure logging to capture output
        configure_logging(level="DEBUG", format_json=True)
        
        # Mock logger to capture messages
        self.log_messages = []
        self.mock_logger = Mock()
        
        def capture_log(message, **kwargs):
            self.log_messages.append({
                'message': message,
                'level': 'info',
                'kwargs': kwargs
            })
        
        def capture_warning(message, **kwargs):
            self.log_messages.append({
                'message': message,
                'level': 'warning',
                'kwargs': kwargs
            })
        
        def capture_debug(message, **kwargs):
            self.log_messages.append({
                'message': message,
                'level': 'debug',
                'kwargs': kwargs
            })
        
        self.mock_logger.info = capture_log
        self.mock_logger.warning = capture_warning
        self.mock_logger.debug = capture_debug

    def test_gate_validator_logging(self):
        """Test that all gate validators generate appropriate log entries."""
        validator = BreakoutGateValidator()
        validator.gating_logger = self.mock_logger
        
        # Test RVOL gate logging
        validator.validate_rvol_gate(1.5, 1.0, "test-plan-1")
        assert len(self.log_messages) == 1
        assert self.log_messages[0]['kwargs']['gate_name'] == 'rvol'
        assert self.log_messages[0]['kwargs']['gate_result'] == 'PASS'
        
        # Test failed RVOL gate
        self.log_messages.clear()
        validator.validate_rvol_gate(0.5, 1.0, "test-plan-1")
        assert len(self.log_messages) == 1
        assert self.log_messages[0]['kwargs']['gate_name'] == 'rvol'
        assert self.log_messages[0]['kwargs']['gate_result'] == 'FAIL'
        assert self.log_messages[0]['level'] == 'warning'
        
        # Test volatility gate logging
        self.log_messages.clear()
        validator.validate_volatility_gate(0.01, 0.005, 1.5, "test-plan-1")
        assert len(self.log_messages) == 1
        assert self.log_messages[0]['kwargs']['gate_name'] == 'volatility'
        assert self.log_messages[0]['kwargs']['gate_result'] == 'PASS'
        
        # Test orderbook sweep gate logging
        self.log_messages.clear()
        validator.validate_orderbook_sweep_gate(True, 'ask', 'ask', "test-plan-1")
        assert len(self.log_messages) == 1
        assert self.log_messages[0]['kwargs']['gate_name'] == 'orderbook_sweep'
        assert self.log_messages[0]['kwargs']['gate_result'] == 'PASS'
        
        # Test penetration gate logging
        self.log_messages.clear()
        validator.validate_penetration_gate(100.5, 100.0, 0.3, False, "test-plan-1")
        assert len(self.log_messages) == 1
        assert self.log_messages[0]['kwargs']['gate_name'] == 'penetration'
        assert self.log_messages[0]['kwargs']['gate_result'] == 'PASS'

    def test_invalidation_checker_logging(self):
        """Test that invalidation checker generates appropriate log entries."""
        checker = InvalidationChecker()
        checker.gating_logger = self.mock_logger
        
        # Test price invalidation logging
        conditions = [
            {'condition_type': 'price_above', 'level': 105.0},
            {'condition_type': 'price_below', 'level': 95.0}
        ]
        
        # Test price within bounds
        result = checker.check_price_invalidation(100.0, conditions, "test-plan-1")
        assert result is None
        assert len(self.log_messages) == 2  # Debug messages for both conditions
        
        # Test price above limit
        self.log_messages.clear()
        result = checker.check_price_invalidation(110.0, conditions, "test-plan-1")
        assert result == InvalidationReason.PRICE_ABOVE
        assert len(self.log_messages) == 1
        assert self.log_messages[0]['level'] == 'warning'
        assert self.log_messages[0]['kwargs']['invalidation_type'] == 'price_above'
        
        # Test time invalidation logging
        self.log_messages.clear()
        current_time = datetime.now(timezone.utc)
        created_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        time_conditions = [{'condition_type': 'time_limit', 'duration_seconds': 30}]
        
        result = checker.check_time_invalidation(current_time, created_time, time_conditions, "test-plan-1")
        assert len(self.log_messages) >= 1  # At least debug message
        
        # Test fakeout invalidation logging
        self.log_messages.clear()
        mock_candle = Mock()
        mock_candle.close = 99.0
        mock_candle.is_closed = True
        mock_candle.ts = current_time
        
        result = checker.check_fakeout_invalidation(mock_candle, 100.0, False, "test-plan-1")
        assert result is True
        assert len(self.log_messages) == 1
        assert self.log_messages[0]['level'] == 'warning'
        assert self.log_messages[0]['kwargs']['invalidation_type'] == 'fakeout_close'

    def test_state_transition_logging(self):
        """Test that state transitions generate appropriate log entries."""
        with patch('ta2_app.state.machine.state_logger') as mock_state_logger:
            mock_state_logger.info = Mock()
            
            # Create test data
            plan_rt = PlanRuntimeState(
                state=PlanLifecycleState.PENDING,
                substate=BreakoutSubState.NONE
            )
            
            market_context = MarketContext(
                last_price=100.5,
                timestamp=datetime.now(timezone.utc),
                atr=0.5,
                natr_pct=2.0,
                rvol=1.8,
                last_closed_bar=None,
                bar_range=0.8,
                curr_book=None,
                prev_book=None,
                pinbar_detected=False,
                ob_sweep_detected=False,
                ob_sweep_side=None
            )
            
            cfg = BreakoutParameters(
                penetration_pct=0.001,
                min_rvol=1.5,
                min_break_range_atr=0.5,
                confirm_close=False,
                confirm_time_ms=0,
                ob_sweep_check=False,
                allow_retest_entry=False
            )
            
            plan_data = {
                'id': 'test-plan-1',
                'entry_price': 100.0,
                'direction': 'long',
                'created_at': datetime.now(timezone.utc)
            }
            
            # Mock metrics
            metrics = Mock()
            metrics.rvol = 1.8
            metrics.atr = 0.5
            metrics.natr_pct = 2.0
            metrics.get_composite_score = Mock(return_value=0.75)
            
            # Test break seen transition
            result = eval_breakout_tick(plan_rt, market_context, cfg, plan_data, metrics)
            
            # Verify state transition logging was called
            assert mock_state_logger.info.called
            call_args = mock_state_logger.info.call_args
            assert 'State transition' in call_args[0][0]

    def test_comprehensive_logging_context(self):
        """Test that comprehensive logging context includes all required fields."""
        validator = BreakoutGateValidator()
        validator.gating_logger = self.mock_logger
        
        # Test with complex gate validation
        validator.validate_rvol_gate(1.8, 1.5, "test-plan-complex")
        
        log_entry = self.log_messages[0]
        required_fields = ['gate_name', 'gate_result', 'plan_id', 'reason', 'event']
        
        for field in required_fields:
            assert field in log_entry['kwargs'], f"Missing required field: {field}"
        
        # Test context data structure
        context = log_entry['kwargs'].get('context', {})
        assert isinstance(context, dict)
        assert 'rvol' in context
        assert 'min_rvol' in context
        assert 'difference' in context
        assert 'multiplier' in context

    def test_logging_consistency_across_components(self):
        """Test that logging is consistent across all components."""
        # Test gate validator
        validator = BreakoutGateValidator()
        validator.gating_logger = self.mock_logger
        
        validator.validate_rvol_gate(1.5, 1.0, "test-plan-1")
        gate_log = self.log_messages[0]
        
        # Test invalidation checker
        self.log_messages.clear()
        checker = InvalidationChecker()
        checker.gating_logger = self.mock_logger
        
        conditions = [{'condition_type': 'price_above', 'level': 105.0}]
        checker.check_price_invalidation(110.0, conditions, "test-plan-1")
        invalidation_log = self.log_messages[0]
        
        # Verify consistent field structure
        assert 'plan_id' in gate_log['kwargs']
        assert 'plan_id' in invalidation_log['kwargs']
        assert 'event' in gate_log['kwargs']
        assert 'event' in invalidation_log['kwargs']
        
        # Verify consistent plan_id
        assert gate_log['kwargs']['plan_id'] == invalidation_log['kwargs']['plan_id']

    def test_logging_performance_impact(self):
        """Test that logging doesn't significantly impact performance."""
        import time
        
        validator = BreakoutGateValidator()
        validator.gating_logger = self.mock_logger
        
        # Measure time with logging
        start_time = time.time()
        for i in range(100):
            validator.validate_rvol_gate(1.5, 1.0, f"test-plan-{i}")
        logging_time = time.time() - start_time
        
        # Verify logging doesn't add excessive overhead
        assert logging_time < 1.0  # Should complete in under 1 second
        assert len(self.log_messages) == 100

    def test_error_logging_in_edge_cases(self):
        """Test logging behavior in error conditions."""
        validator = BreakoutGateValidator()
        validator.gating_logger = self.mock_logger
        
        # Test with None values
        validator.validate_rvol_gate(None, 1.0, "test-plan-error")
        assert len(self.log_messages) == 1
        assert self.log_messages[0]['kwargs']['passed'] is False
        assert 'No RVOL data available' in self.log_messages[0]['kwargs']['reason']
        
        # Test with invalid parameters
        self.log_messages.clear()
        validator.validate_volatility_gate(None, None, 1.0, "test-plan-error")
        assert len(self.log_messages) == 1
        assert self.log_messages[0]['kwargs']['passed'] is False
        assert 'Missing required data' in self.log_messages[0]['kwargs']['reason']

    def test_audit_trail_completeness(self):
        """Test that audit trail logging captures all decision points."""
        checker = InvalidationChecker()
        checker.gating_logger = self.mock_logger
        
        # Test comprehensive invalidation context logging
        current_time = datetime.now(timezone.utc)
        plan_data = {
            'id': 'test-plan-audit',
            'created_at': current_time,
            'extra_data': {
                'invalidation_conditions': [
                    {'condition_type': 'price_above', 'level': 105.0},
                    {'condition_type': 'time_limit', 'duration_seconds': 300}
                ]
            },
            'stop_loss': 95.0
        }
        
        checker.log_invalidation_context(
            "test-plan-audit",
            100.0,
            current_time,
            plan_data,
            {'additional_context': 'test_data'}
        )
        
        assert len(self.log_messages) == 1
        log_entry = self.log_messages[0]
        
        # Verify audit trail completeness
        required_audit_fields = [
            'plan_id', 'current_price', 'current_time', 'plan_created_at',
            'elapsed_seconds', 'stop_loss_price', 'invalidation_conditions_count',
            'invalidation_conditions', 'additional_context'
        ]
        
        for field in required_audit_fields:
            assert field in log_entry['kwargs'], f"Missing audit field: {field}"
        
        assert log_entry['kwargs']['event'] == 'invalidation_context'
        assert log_entry['kwargs']['invalidation_conditions_count'] == 2