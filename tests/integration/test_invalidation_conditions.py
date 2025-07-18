"""Integration tests for invalidation conditions with JSON string format."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from ta2_app.engine import BreakoutEvaluationEngine
from ta2_app.state.models import InvalidationReason


class TestInvalidationConditionsIntegration:
    """Test invalidation conditions integration with real JSON string format."""
    
    def test_price_above_invalidation_with_json_string(self) -> None:
        """Test price_above invalidation with JSON string extra_data."""
        engine = BreakoutEvaluationEngine()
        
        # Plan with JSON string extra_data (real format)
        plan_data = {
            'id': 'test-plan-price-above',
            'instrument_id': 'ETH-USDT-SWAP',
            'direction': 'short',
            'entry_type': 'breakout',
            'entry_price': '3308.0',
            'created_at': datetime.now().isoformat(),
            'extra_data': '{"invalidation_conditions": [{"type": "price_above", "level": 3360, "description": "Stop loss"}]}'
        }
        
        engine.add_plan(plan_data)
        
        # Verify plan was added and normalized
        assert len(engine.active_plans) == 1
        normalized_plan = engine.active_plans[0]
        assert isinstance(normalized_plan['extra_data'], dict)
        assert normalized_plan['extra_data']['invalidation_conditions'][0]['type'] == 'price_above'
        assert normalized_plan['extra_data']['invalidation_conditions'][0]['level'] == 3360
        
        # Test that the state machine can read the invalidation condition
        from ta2_app.state.machine import check_pre_invalidations
        
        # Price below invalidation level - should not invalidate
        result = check_pre_invalidations(normalized_plan, 3350.0, datetime.now())
        assert result is None
        
        # Price above invalidation level - should invalidate
        result = check_pre_invalidations(normalized_plan, 3370.0, datetime.now())
        assert result == InvalidationReason.PRICE_ABOVE
    
    def test_price_below_invalidation_with_json_string(self) -> None:
        """Test price_below invalidation with JSON string extra_data."""
        engine = BreakoutEvaluationEngine()
        
        plan_data = {
            'id': 'test-plan-price-below',
            'instrument_id': 'BTC-USD-SWAP',
            'direction': 'long',
            'entry_type': 'breakout',
            'entry_price': '50000.0',
            'created_at': datetime.now().isoformat(),
            'extra_data': '{"invalidation_conditions": [{"type": "price_below", "level": 49000, "description": "Support break"}]}'
        }
        
        engine.add_plan(plan_data)
        
        # Verify plan was added and normalized
        assert len(engine.active_plans) == 1
        normalized_plan = engine.active_plans[0]
        assert normalized_plan['extra_data']['invalidation_conditions'][0]['type'] == 'price_below'
        assert normalized_plan['extra_data']['invalidation_conditions'][0]['level'] == 49000
        
        # Test that the state machine can read the invalidation condition
        from ta2_app.state.machine import check_pre_invalidations
        
        # Price above invalidation level - should not invalidate
        result = check_pre_invalidations(normalized_plan, 49100.0, datetime.now())
        assert result is None
        
        # Price below invalidation level - should invalidate
        result = check_pre_invalidations(normalized_plan, 48500.0, datetime.now())
        assert result == InvalidationReason.PRICE_BELOW
    
    def test_time_limit_invalidation_with_json_string(self) -> None:
        """Test time_limit invalidation with JSON string extra_data."""
        engine = BreakoutEvaluationEngine()
        
        # Create plan with created_at 2 hours ago
        created_at = datetime.now() - timedelta(hours=2)
        plan_data = {
            'id': 'test-plan-time-limit',
            'instrument_id': 'ETH-USDT-SWAP',
            'direction': 'short',
            'entry_type': 'breakout',
            'entry_price': '3308.0',
            'created_at': created_at.isoformat(),
            'extra_data': '{"invalidation_conditions": [{"type": "time_limit", "duration_seconds": 3600, "description": "1 hour limit"}]}'
        }
        
        engine.add_plan(plan_data)
        
        # Verify plan was added and normalized
        assert len(engine.active_plans) == 1
        normalized_plan = engine.active_plans[0]
        assert normalized_plan['extra_data']['invalidation_conditions'][0]['type'] == 'time_limit'
        assert normalized_plan['extra_data']['invalidation_conditions'][0]['duration_seconds'] == 3600
        
        # Test that the state machine can read the invalidation condition
        from ta2_app.state.machine import check_pre_invalidations
        
        # Current time is 2 hours after creation, limit is 1 hour - should invalidate
        result = check_pre_invalidations(normalized_plan, 3300.0, datetime.now())
        assert result == InvalidationReason.TIME_LIMIT
    
    def test_multiple_invalidation_conditions_with_json_string(self) -> None:
        """Test multiple invalidation conditions with JSON string extra_data."""
        engine = BreakoutEvaluationEngine()
        
        # Plan with multiple invalidation conditions (matching plan_example.json format)
        plan_data = {
            'id': 'test-plan-multiple',
            'instrument_id': 'ETH-USDT-SWAP',
            'direction': 'short',
            'entry_type': 'breakout',
            'entry_price': '3308.0',
            'created_at': datetime.now().isoformat(),
            'extra_data': '{"invalidation_conditions": [{"type": "price_above", "level": 3360, "description": "Stop loss"}, {"type": "time_limit", "duration_seconds": 3600, "description": "1 hour limit"}]}'
        }
        
        engine.add_plan(plan_data)
        
        # Verify plan was added and normalized
        assert len(engine.active_plans) == 1
        normalized_plan = engine.active_plans[0]
        conditions = normalized_plan['extra_data']['invalidation_conditions']
        assert len(conditions) == 2
        assert conditions[0]['type'] == 'price_above'
        assert conditions[1]['type'] == 'time_limit'
        
        # Test that the state machine processes both conditions
        from ta2_app.state.machine import check_pre_invalidations
        
        # Price trigger should invalidate first (before time limit)
        result = check_pre_invalidations(normalized_plan, 3370.0, datetime.now())
        assert result == InvalidationReason.PRICE_ABOVE
    
    def test_real_plan_example_format(self) -> None:
        """Test with exact format from plan_example.json."""
        engine = BreakoutEvaluationEngine()
        
        # This is the exact format from plan_example.json
        plan_data = {
            'id': '65ec39c5-b973-4b45-bc02-f9531d9941f9',
            'instrument_id': 'ETH-USDT-SWAP',
            'direction': 'short',
            'entry_type': 'breakout',
            'entry_price': '3308.0',
            'target_price': '3220',
            'stop_loss': '3350',
            'created_at': '2025-07-17 04:08:23.750427',
            'extra_data': '{"entry_params": {"level": 3308}, "invalidation_conditions": [{"type": "price_above", "level": 3360, "description": "Price moves above 3360 before entry, invalidating the bearish setup."}, {"type": "time_limit", "duration_seconds": 3600, "description": "Plan invalid if not triggered in 1 hour."}], "primary_timeframe": "1H"}'
        }
        
        engine.add_plan(plan_data)
        
        # Verify plan was added and normalized
        assert len(engine.active_plans) == 1
        normalized_plan = engine.active_plans[0]
        
        # Check all fields were properly normalized
        assert normalized_plan['id'] == '65ec39c5-b973-4b45-bc02-f9531d9941f9'
        assert normalized_plan['instrument_id'] == 'ETH-USDT-SWAP'
        assert normalized_plan['direction'] == 'short'
        assert normalized_plan['entry_type'] == 'breakout'
        assert isinstance(normalized_plan['entry_price'], float)
        assert normalized_plan['entry_price'] == 3308.0
        assert isinstance(normalized_plan['target_price'], float)
        assert normalized_plan['target_price'] == 3220.0
        assert isinstance(normalized_plan['stop_loss'], float)
        assert normalized_plan['stop_loss'] == 3350.0
        assert isinstance(normalized_plan['created_at'], datetime)
        
        # Check that extra_data was parsed and invalidation conditions work
        extra_data = normalized_plan['extra_data']
        assert isinstance(extra_data, dict)
        assert 'invalidation_conditions' in extra_data
        assert len(extra_data['invalidation_conditions']) == 2
        
        conditions = extra_data['invalidation_conditions']
        assert conditions[0]['type'] == 'price_above'
        assert conditions[0]['level'] == 3360
        assert conditions[1]['type'] == 'time_limit'
        assert conditions[1]['duration_seconds'] == 3600
        
        # Test that the state machine can process the real format
        from ta2_app.state.machine import check_pre_invalidations
        
        # Price above 3360 should trigger invalidation
        result = check_pre_invalidations(normalized_plan, 3370.0, datetime.now())
        assert result == InvalidationReason.PRICE_ABOVE
        
        # Price below 3360 should not trigger invalidation
        result = check_pre_invalidations(normalized_plan, 3350.0, datetime.now())
        assert result is None
    
    def test_field_name_consistency(self) -> None:
        """Test that field names are consistent (type vs condition_type)."""
        engine = BreakoutEvaluationEngine()
        
        # Test with the correct field name 'type' (not 'condition_type')
        plan_data = {
            'id': 'test-field-consistency',
            'instrument_id': 'ETH-USDT-SWAP',
            'direction': 'short',
            'entry_type': 'breakout',
            'entry_price': '3308.0',
            'created_at': datetime.now().isoformat(),
            'extra_data': '{"invalidation_conditions": [{"type": "price_above", "level": 3360}]}'
        }
        
        engine.add_plan(plan_data)
        
        # Verify plan was added and normalized
        assert len(engine.active_plans) == 1
        normalized_plan = engine.active_plans[0]
        
        # Test that the state machine recognizes the 'type' field
        from ta2_app.state.machine import check_pre_invalidations
        
        result = check_pre_invalidations(normalized_plan, 3370.0, datetime.now())
        assert result == InvalidationReason.PRICE_ABOVE
        
        # Test that the old 'condition_type' field would NOT work
        # (This is a negative test to ensure we fixed the field name issue)
        old_format_plan = normalized_plan.copy()
        old_format_plan['extra_data'] = {
            'invalidation_conditions': [
                {'condition_type': 'price_above', 'level': 3360}  # Old field name
            ]
        }
        
        # Should not trigger invalidation with old field name
        result = check_pre_invalidations(old_format_plan, 3370.0, datetime.now())
        assert result is None  # No invalidation because field name is wrong