"""
Plan data normalization for converting raw plan data to canonical format.

This module handles parsing, validation, and normalization of trading plan data
including JSON string parsing and field name standardization.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PlanNormalizationResult:
    """Result of plan normalization process."""
    # Normalized data (None if invalid)
    normalized_plan: Optional[dict[str, Any]] = None
    # Processing metadata
    success: bool = True
    error_msg: Optional[str] = None

    @classmethod
    def success(cls, normalized_plan: dict[str, Any]):
        """Create successful result with normalized plan."""
        return cls(
            normalized_plan=normalized_plan,
            success=True
        )

    @classmethod
    def error(cls, error_msg: str):
        """Create error result."""
        return cls(
            success=False,
            error_msg=error_msg
        )


class PlanNormalizer:
    """
    Plan data normalization pipeline.

    Handles parsing of JSON strings, field validation, and format standardization
    for trading plan data.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        Initialize plan normalizer with configuration.

        Args:
            config: Normalization configuration dict
        """
        self.config = config or {}
        self.logger = logger

    def normalize_plan(self, plan_data: dict[str, Any]) -> PlanNormalizationResult:
        """
        Normalize a trading plan from raw format to canonical format.

        Args:
            plan_data: Raw plan data dictionary

        Returns:
            PlanNormalizationResult with normalized data or error information
        """
        try:
            # Create a copy to avoid modifying the original
            normalized_plan = plan_data.copy()

            # Parse JSON extra_data if it's a string
            if isinstance(plan_data.get('extra_data'), str):
                try:
                    normalized_plan['extra_data'] = json.loads(plan_data['extra_data'])
                except (json.JSONDecodeError, TypeError) as e:
                    return PlanNormalizationResult.error(f"Failed to parse extra_data JSON: {e}")

            # Validate required fields
            required_fields = ['id', 'instrument_id', 'entry_type', 'direction', 'entry_price']
            for field in required_fields:
                if field not in normalized_plan or normalized_plan[field] is None:
                    return PlanNormalizationResult.error(f"Missing required field: {field}")

            # Validate entry_type
            if normalized_plan.get('entry_type') != 'breakout':
                return PlanNormalizationResult.error(f"Unsupported entry_type: {normalized_plan.get('entry_type')}")

            # Validate direction
            if normalized_plan.get('direction') not in ['long', 'short']:
                return PlanNormalizationResult.error(f"Invalid direction: {normalized_plan.get('direction')}")

            # Convert entry_price to float if it's a string
            try:
                normalized_plan['entry_price'] = float(normalized_plan['entry_price'])
            except (ValueError, TypeError) as e:
                return PlanNormalizationResult.error(f"Invalid entry_price: {e}")

            # Convert stop_loss to float if present and not None
            if 'stop_loss' in normalized_plan and normalized_plan['stop_loss'] is not None:
                try:
                    normalized_plan['stop_loss'] = float(normalized_plan['stop_loss'])
                except (ValueError, TypeError) as e:
                    return PlanNormalizationResult.error(f"Invalid stop_loss: {e}")

            # Convert target_price to float if present and not None
            if 'target_price' in normalized_plan and normalized_plan['target_price'] is not None:
                try:
                    normalized_plan['target_price'] = float(normalized_plan['target_price'])
                except (ValueError, TypeError) as e:
                    return PlanNormalizationResult.error(f"Invalid target_price: {e}")

            # Parse created_at timestamp if it's a string
            if isinstance(normalized_plan.get('created_at'), str):
                try:
                    # Handle various datetime formats
                    created_at_str = normalized_plan['created_at']
                    if '.' in created_at_str:
                        normalized_plan['created_at'] = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    else:
                        normalized_plan['created_at'] = datetime.fromisoformat(created_at_str)
                except (ValueError, TypeError) as e:
                    return PlanNormalizationResult.error(f"Invalid created_at timestamp: {e}")

            # Validate invalidation conditions format if present
            extra_data = normalized_plan.get('extra_data', {})
            if 'invalidation_conditions' in extra_data:
                invalidation_conditions = extra_data['invalidation_conditions']
                if not isinstance(invalidation_conditions, list):
                    return PlanNormalizationResult.error("invalidation_conditions must be a list")

                for i, condition in enumerate(invalidation_conditions):
                    if not isinstance(condition, dict):
                        return PlanNormalizationResult.error(f"invalidation_conditions[{i}] must be a dict")

                    condition_type = condition.get('type')
                    if condition_type not in ['price_above', 'price_below', 'time_limit']:
                        return PlanNormalizationResult.error(f"Invalid invalidation condition type: {condition_type}")

                    if condition_type in ['price_above', 'price_below']:
                        if 'level' not in condition:
                            return PlanNormalizationResult.error(f"Missing level for {condition_type} condition")
                        try:
                            condition['level'] = float(condition['level'])
                        except (ValueError, TypeError) as e:
                            return PlanNormalizationResult.error(f"Invalid level in {condition_type} condition: {e}")

                    if condition_type == 'time_limit':
                        if 'duration_seconds' not in condition:
                            return PlanNormalizationResult.error("Missing duration_seconds for time_limit condition")
                        try:
                            condition['duration_seconds'] = int(condition['duration_seconds'])
                        except (ValueError, TypeError) as e:
                            return PlanNormalizationResult.error(f"Invalid duration_seconds in time_limit condition: {e}")

            return PlanNormalizationResult.success(normalized_plan)

        except Exception as e:
            return PlanNormalizationResult.error(f"Unexpected error during plan normalization: {e}")
