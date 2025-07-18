"""Unit tests for the plan data normalizer."""

import pytest
import json
from datetime import datetime

from ta2_app.data.plan_normalizer import PlanNormalizer, PlanNormalizationResult


class TestPlanNormalizer:
    """Test suite for the PlanNormalizer class."""
    
    def test_normalize_plan_with_json_string_extra_data(self) -> None:
        """Test normalizing plan with JSON string extra_data."""
        normalizer = PlanNormalizer()
        
        # Create plan data with JSON string extra_data (matching plan_example.json)
        plan_data = {
            'id': 'test-plan-001',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': '50000.0',
            'direction': 'long',
            'extra_data': '{"invalidation_conditions": [{"type": "price_above", "level": 51000, "description": "Stop loss"}]}'
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is True
        assert result.error_msg is None
        assert result.normalized_plan is not None
        
        # Check that extra_data was parsed from JSON string
        extra_data = result.normalized_plan['extra_data']
        assert isinstance(extra_data, dict)
        assert 'invalidation_conditions' in extra_data
        assert len(extra_data['invalidation_conditions']) == 1
        assert extra_data['invalidation_conditions'][0]['type'] == 'price_above'
        assert extra_data['invalidation_conditions'][0]['level'] == 51000
        
        # Check that entry_price was converted to float
        assert isinstance(result.normalized_plan['entry_price'], float)
        assert result.normalized_plan['entry_price'] == 50000.0
    
    def test_normalize_plan_with_dict_extra_data(self) -> None:
        """Test normalizing plan with dict extra_data (already parsed)."""
        normalizer = PlanNormalizer()
        
        plan_data = {
            'id': 'test-plan-002',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long',
            'extra_data': {
                'invalidation_conditions': [
                    {'type': 'price_below', 'level': 49000, 'description': 'Support break'}
                ]
            }
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is True
        assert result.normalized_plan['extra_data']['invalidation_conditions'][0]['type'] == 'price_below'
        assert result.normalized_plan['extra_data']['invalidation_conditions'][0]['level'] == 49000
    
    def test_normalize_plan_invalid_json_extra_data(self) -> None:
        """Test normalizing plan with invalid JSON extra_data."""
        normalizer = PlanNormalizer()
        
        plan_data = {
            'id': 'test-plan-003',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long',
            'extra_data': '{"invalid": json}'  # Invalid JSON
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is False
        assert 'Failed to parse extra_data JSON' in result.error_msg
    
    def test_normalize_plan_missing_required_fields(self) -> None:
        """Test normalizing plan with missing required fields."""
        normalizer = PlanNormalizer()
        
        # Test missing id
        plan_data = {
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long'
        }
        
        result = normalizer.normalize_plan(plan_data)
        assert result.success is False
        assert 'Missing required field: id' in result.error_msg
        
        # Test missing instrument_id
        plan_data = {
            'id': 'test-plan-004',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long'
        }
        
        result = normalizer.normalize_plan(plan_data)
        assert result.success is False
        assert 'Missing required field: instrument_id' in result.error_msg
    
    def test_normalize_plan_invalid_entry_type(self) -> None:
        """Test normalizing plan with invalid entry_type."""
        normalizer = PlanNormalizer()
        
        plan_data = {
            'id': 'test-plan-005',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'limit',  # Not 'breakout'
            'entry_price': 50000.0,
            'direction': 'long'
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is False
        assert 'Unsupported entry_type: limit' in result.error_msg
    
    def test_normalize_plan_invalid_direction(self) -> None:
        """Test normalizing plan with invalid direction."""
        normalizer = PlanNormalizer()
        
        plan_data = {
            'id': 'test-plan-006',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'up'  # Not 'long' or 'short'
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is False
        assert 'Invalid direction: up' in result.error_msg
    
    def test_normalize_plan_invalid_entry_price(self) -> None:
        """Test normalizing plan with invalid entry_price."""
        normalizer = PlanNormalizer()
        
        plan_data = {
            'id': 'test-plan-007',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 'invalid_price',
            'direction': 'long'
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is False
        assert 'Invalid entry_price' in result.error_msg
    
    def test_normalize_plan_string_numeric_fields(self) -> None:
        """Test normalizing plan with string numeric fields."""
        normalizer = PlanNormalizer()
        
        plan_data = {
            'id': 'test-plan-008',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': '50000.0',
            'direction': 'long',
            'stop_loss': '51000.0',
            'target_price': '49000.0'
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is True
        assert isinstance(result.normalized_plan['entry_price'], float)
        assert result.normalized_plan['entry_price'] == 50000.0
        assert isinstance(result.normalized_plan['stop_loss'], float)
        assert result.normalized_plan['stop_loss'] == 51000.0
        assert isinstance(result.normalized_plan['target_price'], float)
        assert result.normalized_plan['target_price'] == 49000.0
    
    def test_normalize_plan_string_timestamp(self) -> None:
        """Test normalizing plan with string timestamp."""
        normalizer = PlanNormalizer()
        
        plan_data = {
            'id': 'test-plan-009',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long',
            'created_at': '2025-07-17 04:08:23.750427'
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is True
        assert isinstance(result.normalized_plan['created_at'], datetime)
    
    def test_normalize_plan_invalidation_conditions_validation(self) -> None:
        """Test validation of invalidation conditions structure."""
        normalizer = PlanNormalizer()
        
        # Test with proper invalidation conditions from plan_example.json
        plan_data = {
            'id': 'test-plan-010',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long',
            'extra_data': {
                'invalidation_conditions': [
                    {'type': 'price_above', 'level': 51000, 'description': 'Stop loss'},
                    {'type': 'time_limit', 'duration_seconds': 3600, 'description': 'Time limit'}
                ]
            }
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is True
        conditions = result.normalized_plan['extra_data']['invalidation_conditions']
        assert len(conditions) == 2
        
        # Check price_above condition
        assert conditions[0]['type'] == 'price_above'
        assert isinstance(conditions[0]['level'], float)
        assert conditions[0]['level'] == 51000.0
        
        # Check time_limit condition
        assert conditions[1]['type'] == 'time_limit'
        assert isinstance(conditions[1]['duration_seconds'], int)
        assert conditions[1]['duration_seconds'] == 3600
    
    def test_normalize_plan_invalid_invalidation_conditions(self) -> None:
        """Test with invalid invalidation conditions."""
        normalizer = PlanNormalizer()
        
        # Test with invalid condition type
        plan_data = {
            'id': 'test-plan-011',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long',
            'extra_data': {
                'invalidation_conditions': [
                    {'type': 'invalid_type', 'level': 51000}
                ]
            }
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is False
        assert 'Invalid invalidation condition type: invalid_type' in result.error_msg
    
    def test_normalize_plan_missing_invalidation_condition_fields(self) -> None:
        """Test with missing required fields in invalidation conditions."""
        normalizer = PlanNormalizer()
        
        # Test price_above condition missing level
        plan_data = {
            'id': 'test-plan-012',
            'instrument_id': 'BTC-USD-SWAP',
            'entry_type': 'breakout',
            'entry_price': 50000.0,
            'direction': 'long',
            'extra_data': {
                'invalidation_conditions': [
                    {'type': 'price_above', 'description': 'Missing level'}
                ]
            }
        }
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is False
        assert 'Missing level for price_above condition' in result.error_msg
    
    def test_normalize_plan_real_example_format(self) -> None:
        """Test normalizing plan with real plan_example.json format."""
        normalizer = PlanNormalizer()
        
        # This matches the actual format from plan_example.json
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
        
        result = normalizer.normalize_plan(plan_data)
        
        assert result.success is True
        assert result.normalized_plan is not None
        
        # Check that all fields were properly normalized
        normalized = result.normalized_plan
        assert normalized['id'] == '65ec39c5-b973-4b45-bc02-f9531d9941f9'
        assert normalized['instrument_id'] == 'ETH-USDT-SWAP'
        assert normalized['direction'] == 'short'
        assert normalized['entry_type'] == 'breakout'
        assert isinstance(normalized['entry_price'], float)
        assert normalized['entry_price'] == 3308.0
        assert isinstance(normalized['target_price'], float)
        assert normalized['target_price'] == 3220.0
        assert isinstance(normalized['stop_loss'], float)
        assert normalized['stop_loss'] == 3350.0
        assert isinstance(normalized['created_at'], datetime)
        
        # Check that extra_data was parsed correctly
        extra_data = normalized['extra_data']
        assert isinstance(extra_data, dict)
        assert 'invalidation_conditions' in extra_data
        assert len(extra_data['invalidation_conditions']) == 2
        
        # Check invalidation conditions use 'type' field (not 'condition_type')
        conditions = extra_data['invalidation_conditions']
        assert conditions[0]['type'] == 'price_above'
        assert conditions[0]['level'] == 3360
        assert conditions[1]['type'] == 'time_limit'
        assert conditions[1]['duration_seconds'] == 3600


class TestPlanNormalizationResult:
    """Test suite for the PlanNormalizationResult class."""
    
    def test_success_result(self) -> None:
        """Test creating a successful result."""
        plan_data = {'id': 'test-plan', 'instrument_id': 'BTC-USD-SWAP'}
        result = PlanNormalizationResult.success(plan_data)
        
        assert result.success is True
        assert result.error_msg is None
        assert result.normalized_plan == plan_data
    
    def test_error_result(self) -> None:
        """Test creating an error result."""
        error_msg = 'Test error message'
        result = PlanNormalizationResult.error(error_msg)
        
        assert result.success is False
        assert result.error_msg == error_msg
        assert result.normalized_plan is None