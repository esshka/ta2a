"""Unit tests for the main evaluation engine."""

import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch

from ta2_app.engine import BreakoutEvaluationEngine
from ta2_app.data.models import NormalizationResult, Candle, BookSnap
from ta2_app.state.models import PlanLifecycleState


class TestBreakoutEvaluationEngine:
    """Test suite for the BreakoutEvaluationEngine class."""

    def test_engine_initialization(self) -> None:
        """Test that the engine can be initialized."""
        engine = BreakoutEvaluationEngine()
        assert engine is not None
        assert engine.active_plans == []
        assert engine.data_stores == {}
        assert engine.metrics_calculators == {}

    def test_engine_initialization_with_config_dir(self) -> None:
        """Test engine initialization with custom config directory."""
        with patch('ta2_app.engine.ConfigLoader') as mock_config_loader:
            mock_config_loader.create.return_value = Mock()
            engine = BreakoutEvaluationEngine(config_dir="/custom/path")
            assert engine is not None
            mock_config_loader.create.assert_called_once_with("/custom/path")

    def test_add_plan_valid_breakout(self) -> None:
        """Test adding a valid breakout plan."""
        engine = BreakoutEvaluationEngine()
        plan_data = {
            'id': 'test-plan-001',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long'
        }
        
        engine.add_plan(plan_data)
        
        assert len(engine.active_plans) == 1
        # Plan should be normalized but still have the same core data
        assert engine.active_plans[0]['id'] == 'test-plan-001'
        assert engine.active_plans[0]['instrument_id'] == 'BTC-USD-SWAP'
        assert engine.active_plans[0]['entry_type'] == 'breakout'
        assert engine.active_plans[0]['entry_price'] == 50000.0
        assert engine.active_plans[0]['direction'] == 'long'
        assert 'BTC-USD-SWAP' in engine.data_stores
        assert 'BTC-USD-SWAP' in engine.metrics_calculators

    def test_add_plan_invalid_entry_type(self) -> None:
        """Test adding plan with invalid entry type."""
        engine = BreakoutEvaluationEngine()
        plan_data = {
            'id': 'test-plan-002',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'limit',  # Not 'breakout'
            'entry_price': 50000.0,
            'direction': 'long'
        }
        
        engine.add_plan(plan_data)
        
        assert len(engine.active_plans) == 0
        assert 'BTC-USD-SWAP' not in engine.data_stores

    def test_add_plan_missing_required_fields(self) -> None:
        """Test adding plan with missing required fields."""
        engine = BreakoutEvaluationEngine()
        
        # Missing id
        plan_data = {
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long'
        }
        engine.add_plan(plan_data)
        assert len(engine.active_plans) == 0
        
        # Missing instrument_id
        plan_data = {
            'id': 'test-plan-003',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long'
        }
        engine.add_plan(plan_data)
        assert len(engine.active_plans) == 0

    def test_remove_plan(self) -> None:
        """Test removing a plan."""
        engine = BreakoutEvaluationEngine()
        plan_data = {
            'id': 'test-plan-004',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long'
        }
        
        engine.add_plan(plan_data)
        assert len(engine.active_plans) == 1
        
        with patch('ta2_app.engine.state_manager') as mock_state_manager:
            engine.remove_plan('test-plan-004')
            assert len(engine.active_plans) == 0
            mock_state_manager.remove_plan.assert_called_once_with('test-plan-004')

    def test_remove_nonexistent_plan(self) -> None:
        """Test removing a plan that doesn't exist."""
        engine = BreakoutEvaluationEngine()
        
        with patch('ta2_app.engine.state_manager') as mock_state_manager:
            engine.remove_plan('nonexistent-plan')
            assert len(engine.active_plans) == 0
            mock_state_manager.remove_plan.assert_called_once_with('nonexistent-plan')

    def test_evaluate_tick_no_active_plans(self) -> None:
        """Test evaluate_tick with no active plans."""
        engine = BreakoutEvaluationEngine()
        result = engine.evaluate_tick({'test': 'data'})
        assert isinstance(result, list)
        assert len(result) == 0

    def test_evaluate_tick_candlestick_normalization_failure(self) -> None:
        """Test evaluate_tick with candlestick normalization failure."""
        engine = BreakoutEvaluationEngine()
        engine.add_plan({
            'id': 'test-plan-005',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long'
        })
        
        with patch.object(engine.normalizer, 'normalize_candlesticks') as mock_normalize:
            mock_normalize.return_value = NormalizationResult.error("Test error")
            
            result = engine.evaluate_tick(
                candlestick_payload={'test': 'data'},
                instrument_id='BTC-USD-SWAP'
            )
            
            assert isinstance(result, list)
            assert len(result) == 0

    def test_evaluate_tick_orderbook_normalization_failure(self) -> None:
        """Test evaluate_tick with orderbook normalization failure."""
        engine = BreakoutEvaluationEngine()
        engine.add_plan({
            'id': 'test-plan-006',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long'
        })
        
        with patch.object(engine.normalizer, 'normalize_orderbook') as mock_normalize:
            mock_normalize.return_value = NormalizationResult.error("Test error")
            
            result = engine.evaluate_tick(
                orderbook_payload={'test': 'data'},
                instrument_id='BTC-USD-SWAP'
            )
            
            assert isinstance(result, list)
            assert len(result) == 0

    def test_evaluate_tick_exception_handling(self) -> None:
        """Test evaluate_tick exception handling."""
        engine = BreakoutEvaluationEngine()
        engine.add_plan({
            'id': 'test-plan-007',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long'
        })
        
        with patch.object(engine.normalizer, 'normalize_candlesticks') as mock_normalize:
            mock_normalize.side_effect = Exception("Test exception")
            
            result = engine.evaluate_tick(
                candlestick_payload={'test': 'data'},
                instrument_id='BTC-USD-SWAP'
            )
            
            assert isinstance(result, list)
            assert len(result) == 0

    def test_get_plan_state_existing_plan(self) -> None:
        """Test getting state for an existing plan."""
        engine = BreakoutEvaluationEngine()
        
        with patch('ta2_app.engine.state_manager') as mock_state_manager:
            mock_runtime_state = Mock()
            mock_runtime_state.state = PlanLifecycleState.PENDING
            mock_runtime_state.substate = Mock()
            mock_runtime_state.substate.value = 'none'
            mock_runtime_state.break_ts = None
            mock_runtime_state.armed_at = None
            mock_runtime_state.triggered_at = None
            mock_runtime_state.invalid_reason = None
            mock_runtime_state.break_seen = False
            mock_runtime_state.break_confirmed = False
            mock_runtime_state.signal_emitted = False
            
            mock_state_manager.get_plan_state.return_value = mock_runtime_state
            
            result = engine.get_plan_state('test-plan-008')
            
            assert result is not None
            assert result['plan_id'] == 'test-plan-008'
            assert result['state'] == 'pending'
            assert result['substate'] == 'none'
            assert result['break_ts'] is None
            assert result['break_seen'] is False

    def test_get_plan_state_nonexistent_plan(self) -> None:
        """Test getting state for a nonexistent plan."""
        engine = BreakoutEvaluationEngine()
        
        with patch('ta2_app.engine.state_manager') as mock_state_manager:
            mock_state_manager.get_plan_state.return_value = None
            
            result = engine.get_plan_state('nonexistent-plan')
            
            assert result is None

    def test_get_active_plan_count(self) -> None:
        """Test getting active plan count."""
        engine = BreakoutEvaluationEngine()
        assert engine.get_active_plan_count() == 0
        
        engine.add_plan({
            'id': 'test-plan-009',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long'
        })
        
        assert engine.get_active_plan_count() == 1

    def test_get_runtime_stats(self) -> None:
        """Test getting runtime statistics."""
        engine = BreakoutEvaluationEngine()
        
        with patch('ta2_app.engine.state_manager') as mock_state_manager:
            mock_state_manager.get_active_plan_count.return_value = 5
            
            stats = engine.get_runtime_stats()
            
            assert stats['active_plans'] == 0  # No plans added yet
            assert stats['tracked_instruments'] == 0
            assert stats['state_manager_active_plans'] == 5
    
    def test_add_plan_with_json_string_extra_data(self) -> None:
        """Test adding plan with JSON string extra_data (real format)."""
        engine = BreakoutEvaluationEngine()
        
        # This matches the real plan_example.json format
        plan_data = {
            'id': 'test-plan-json',
            'instrument_id': 'ETH-USDT-SWAP',
            'direction': 'short',
            'entry_type': 'breakout',
            'entry_price': '3308.0',
            'extra_data': '{"invalidation_conditions": [{"type": "price_above", "level": 3360, "description": "Stop loss"}]}'
        }
        
        engine.add_plan(plan_data)
        
        assert len(engine.active_plans) == 1
        normalized_plan = engine.active_plans[0]
        
        # Check that extra_data was parsed from JSON string
        assert isinstance(normalized_plan['extra_data'], dict)
        assert 'invalidation_conditions' in normalized_plan['extra_data']
        
        # Check that invalidation conditions use 'type' field (not 'condition_type')
        conditions = normalized_plan['extra_data']['invalidation_conditions']
        assert conditions[0]['type'] == 'price_above'
        assert conditions[0]['level'] == 3360
        
        # Check that entry_price was converted to float
        assert isinstance(normalized_plan['entry_price'], float)
        assert normalized_plan['entry_price'] == 3308.0
    
    def test_add_plan_normalization_failure(self) -> None:
        """Test adding plan with normalization failure."""
        engine = BreakoutEvaluationEngine()
        
        # Plan with invalid JSON in extra_data
        plan_data = {
            'id': 'test-plan-bad-json',
            'instrument_id': 'ETH-USDT-SWAP',
            'direction': 'short',
            'entry_type': 'breakout',
            'entry_price': '3308.0',
            'extra_data': '{"invalid": json}'  # Invalid JSON
        }
        
        engine.add_plan(plan_data)
        
        # Plan should not be added due to normalization failure
        assert len(engine.active_plans) == 0
        assert 'ETH-USDT-SWAP' not in engine.data_stores

    def test_add_plan_with_valid_breakout_params(self) -> None:
        """Test adding plan with valid breakout parameter overrides."""
        engine = BreakoutEvaluationEngine()
        plan_data = {
            'id': 'test-plan-valid-params',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long',
            'extra_data': {
                'breakout_params': {
                    'penetration_pct': 0.04,
                    'min_rvol': 1.8,
                    'allow_retest_entry': True,
                    'retest_band_pct': 0.02,
                    'ob_sweep_check': False,
                    'penetration_natr_mult': 0.3,
                    'confirm_time_ms': 1000,
                    'fakeout_close_invalidate': False,
                    'min_break_range_atr': 0.6
                }
            }
        }
        
        engine.add_plan(plan_data)
        
        assert len(engine.active_plans) == 1
        assert engine.active_plans[0]['id'] == 'test-plan-valid-params'
        assert 'BTC-USD-SWAP' in engine.data_stores

    def test_add_plan_with_invalid_breakout_params(self) -> None:
        """Test adding plan with invalid breakout parameter overrides."""
        engine = BreakoutEvaluationEngine()
        plan_data = {
            'id': 'test-plan-invalid-params',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long',
            'extra_data': {
                'breakout_params': {
                    'penetration_pct': 1.5,  # > 1, invalid
                    'min_rvol': -1.0,        # negative, invalid
                    'allow_retest_entry': 'invalid',  # not boolean
                    'retest_band_pct': 1.5,  # > 1, invalid
                    'confirm_time_ms': -100,  # negative, invalid
                }
            }
        }
        
        engine.add_plan(plan_data)
        
        # Plan should not be added due to validation failure
        assert len(engine.active_plans) == 0
        assert 'BTC-USD-SWAP' not in engine.data_stores

    def test_add_plan_with_mixed_valid_invalid_params(self) -> None:
        """Test adding plan with mix of valid and invalid parameters."""
        engine = BreakoutEvaluationEngine()
        plan_data = {
            'id': 'test-plan-mixed-params',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long',
            'extra_data': {
                'breakout_params': {
                    'penetration_pct': 0.04,     # valid
                    'min_rvol': 1.8,             # valid
                    'allow_retest_entry': 'invalid',  # invalid
                    'ob_sweep_check': True,      # valid
                }
            }
        }
        
        engine.add_plan(plan_data)
        
        # Plan should not be added due to validation failure
        assert len(engine.active_plans) == 0
        assert 'BTC-USD-SWAP' not in engine.data_stores

    def test_get_data_store_creation(self) -> None:
        """Test that data stores are created on demand."""
        engine = BreakoutEvaluationEngine()
        
        # Should create new data store
        store1 = engine._get_data_store('BTC-USD-SWAP')
        assert store1 is not None
        assert 'BTC-USD-SWAP' in engine.data_stores
        
        # Should return existing data store
        store2 = engine._get_data_store('BTC-USD-SWAP')
        assert store2 is store1

    def test_get_metrics_calculator_creation(self) -> None:
        """Test that metrics calculators are created on demand."""
        engine = BreakoutEvaluationEngine()
        
        # Should create new calculator
        calc1 = engine._get_metrics_calculator('BTC-USD-SWAP')
        assert calc1 is not None
        assert 'BTC-USD-SWAP' in engine.metrics_calculators
        
        # Should return existing calculator
        calc2 = engine._get_metrics_calculator('BTC-USD-SWAP')
        assert calc2 is calc1

    def test_evaluate_tick_returns_list(self, sample_candlestick: Dict[str, Any]) -> None:
        """Test that evaluate_tick returns a list of signals."""
        engine = BreakoutEvaluationEngine()
        result = engine.evaluate_tick(sample_candlestick)
        assert isinstance(result, list)

    def test_evaluate_tick_empty_data(self) -> None:
        """Test evaluate_tick with empty market data."""
        engine = BreakoutEvaluationEngine()
        result = engine.evaluate_tick({})
        assert isinstance(result, list)
        assert len(result) == 0