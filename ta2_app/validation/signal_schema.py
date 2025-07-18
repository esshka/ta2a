"""JSON schema validation for signal format according to dev_proto.md."""

import logging
from datetime import datetime
from typing import Any

from ..utils.time import validate_market_time

logger = logging.getLogger(__name__)


# Signal JSON schema according to dev_proto.md section 10
SIGNAL_SCHEMA = {
    "type": "object",
    "required": ["plan_id", "state", "protocol_version", "runtime", "timestamp", "metrics", "strength_score"],
    "properties": {
        "plan_id": {
            "type": "string",
            "minLength": 1,
            "description": "Unique plan identifier"
        },
        "state": {
            "type": "string",
            "enum": ["triggered", "invalid", "expired"],
            "description": "Signal state"
        },
        "protocol_version": {
            "type": "string",
            "pattern": "^breakout-v\\d+(\\.\\d+)*$",
            "description": "Protocol version for forward compatibility"
        },
        "runtime": {
            "type": "object",
            "properties": {
                "armed_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "When plan became armed"
                },
                "triggered_at": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "When signal was triggered"
                },
                "break_ts": {
                    "type": ["string", "null"],
                    "format": "date-time",
                    "description": "When initial break was detected"
                },
                "invalid_reason": {
                    "type": ["string", "null"],
                    "description": "Reason for invalidation"
                },
                "substate": {
                    "type": "string",
                    "description": "Internal breakout substate"
                }
            },
            "additionalProperties": True
        },
        "timestamp": {
            "type": "string",
            "format": "date-time",
            "description": "Signal emission timestamp"
        },
        "last_price": {
            "type": ["number", "null"],
            "description": "Current market price"
        },
        "metrics": {
            "type": "object",
            "properties": {
                "rvol": {
                    "type": ["number", "null"],
                    "minimum": 0,
                    "description": "Relative volume"
                },
                "natr_pct": {
                    "type": ["number", "null"],
                    "minimum": 0,
                    "description": "Normalized ATR percentage"
                },
                "atr": {
                    "type": ["number", "null"],
                    "minimum": 0,
                    "description": "Average True Range"
                },
                "pinbar": {
                    "type": "boolean",
                    "description": "Whether pinbar was detected"
                },
                "pinbar_type": {
                    "type": ["string", "null"],
                    "enum": ["hammer", "shooting_star", "doji", None],
                    "description": "Type of pinbar if detected"
                },
                "ob_sweep_detected": {
                    "type": "boolean",
                    "description": "Whether order book sweep was detected"
                },
                "ob_sweep_side": {
                    "type": ["string", "null"],
                    "enum": ["bid", "ask", None],
                    "description": "Side of order book sweep"
                },
                "ob_imbalance_long": {
                    "type": ["number", "null"],
                    "minimum": -1,
                    "maximum": 1,
                    "description": "Long side order book imbalance"
                },
                "ob_imbalance_short": {
                    "type": ["number", "null"],
                    "minimum": -1,
                    "maximum": 1,
                    "description": "Short side order book imbalance"
                }
            },
            "additionalProperties": True
        },
        "strength_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 100,
            "description": "Signal strength score 0-100"
        },
        "entry_mode": {
            "type": "string",
            "enum": ["momentum", "retest"],
            "description": "Entry mode for triggered signals"
        }
    },
    "additionalProperties": True
}


class SignalValidationError(Exception):
    """Signal validation error."""
    pass


class SignalValidator:
    """Validates signals against JSON schema."""

    def __init__(self):
        self.logger = logger
        self.schema = SIGNAL_SCHEMA

    def validate_signal(self, signal: dict[str, Any]) -> bool:
        """
        Validate a signal against the schema.

        Args:
            signal: Signal dictionary to validate

        Returns:
            True if valid

        Raises:
            SignalValidationError: If validation fails
        """
        try:
            # Basic type and required field validation
            self._validate_required_fields(signal)
            self._validate_field_types(signal)
            self._validate_field_values(signal)

            # Validate timestamps
            self._validate_timestamps(signal)

            # State-specific validation
            self._validate_state_specific(signal)

            return True

        except Exception as e:
            error_msg = f"Signal validation failed: {str(e)}"
            self.logger.error(error_msg, plan_id=signal.get("plan_id"))
            raise SignalValidationError(error_msg) from e

    def _validate_required_fields(self, signal: dict[str, Any]) -> None:
        """Validate required fields are present."""
        required_fields = self.schema["required"]
        missing_fields = [field for field in required_fields if field not in signal]

        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

    def _validate_field_types(self, signal: dict[str, Any]) -> None:
        """Validate field types match schema."""
        # Plan ID
        if not isinstance(signal.get("plan_id"), str) or len(signal["plan_id"]) == 0:
            raise ValueError("plan_id must be a non-empty string")

        # State
        if signal.get("state") not in ["triggered", "invalid", "expired"]:
            raise ValueError(f"Invalid state: {signal.get('state')}")

        # Protocol version
        protocol_version = signal.get("protocol_version")
        if not isinstance(protocol_version, str) or not protocol_version.startswith("breakout-v"):
            raise ValueError(f"Invalid protocol_version: {protocol_version}")

        # Runtime
        if not isinstance(signal.get("runtime", {}), dict):
            raise ValueError("runtime must be an object")

        # Metrics
        if not isinstance(signal.get("metrics", {}), dict):
            raise ValueError("metrics must be an object")

        # Strength score
        strength_score = signal.get("strength_score")
        if not isinstance(strength_score, (int, float)) or not (0 <= strength_score <= 100):
            raise ValueError(f"strength_score must be a number between 0-100, got: {strength_score}")

    def _validate_field_values(self, signal: dict[str, Any]) -> None:
        """Validate field values are within acceptable ranges."""
        metrics = signal.get("metrics", {})

        # RVOL should be positive
        if "rvol" in metrics and metrics["rvol"] is not None:
            if not isinstance(metrics["rvol"], (int, float)) or metrics["rvol"] < 0:
                raise ValueError(f"rvol must be positive, got: {metrics['rvol']}")

        # NATR should be positive
        if "natr_pct" in metrics and metrics["natr_pct"] is not None:
            if not isinstance(metrics["natr_pct"], (int, float)) or metrics["natr_pct"] < 0:
                raise ValueError(f"natr_pct must be positive, got: {metrics['natr_pct']}")

        # ATR should be positive
        if "atr" in metrics and metrics["atr"] is not None:
            if not isinstance(metrics["atr"], (int, float)) or metrics["atr"] < 0:
                raise ValueError(f"atr must be positive, got: {metrics['atr']}")

        # Order book imbalances should be between -1 and 1
        for field in ["ob_imbalance_long", "ob_imbalance_short"]:
            if field in metrics and metrics[field] is not None:
                value = metrics[field]
                if not isinstance(value, (int, float)) or not (-1 <= value <= 1):
                    raise ValueError(f"{field} must be between -1 and 1, got: {value}")

    def _validate_timestamps(self, signal: dict[str, Any]) -> None:
        """Validate timestamp formats and market time consistency."""
        # Main timestamp
        timestamp = signal.get("timestamp")
        if timestamp:
            try:
                main_ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                # Validate that main timestamp is reasonable (market time validation)
                if not validate_market_time(main_ts):
                    raise ValueError(f"Signal timestamp appears invalid (too old or future): {timestamp}")
            except ValueError:
                raise ValueError(f"Invalid timestamp format: {timestamp}")

        # Runtime timestamps
        runtime = signal.get("runtime", {})
        for ts_field in ["armed_at", "triggered_at", "break_ts"]:
            if ts_field in runtime and runtime[ts_field] is not None:
                try:
                    ts = datetime.fromisoformat(runtime[ts_field].replace('Z', '+00:00'))
                    # Validate that runtime timestamps are reasonable
                    if not validate_market_time(ts):
                        raise ValueError(f"Runtime timestamp {ts_field} appears invalid (too old or future): {runtime[ts_field]}")
                except ValueError:
                    raise ValueError(f"Invalid {ts_field} timestamp format: {runtime[ts_field]}")

        # Validate timestamp consistency (runtime timestamps should be before or equal to main timestamp)
        if timestamp:
            main_ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            runtime = signal.get("runtime", {})

            for ts_field in ["armed_at", "triggered_at", "break_ts"]:
                if ts_field in runtime and runtime[ts_field] is not None:
                    runtime_ts = datetime.fromisoformat(runtime[ts_field].replace('Z', '+00:00'))
                    if runtime_ts > main_ts:
                        raise ValueError(f"Runtime timestamp {ts_field} ({runtime[ts_field]}) is after signal timestamp ({timestamp})")

    def _validate_state_specific(self, signal: dict[str, Any]) -> None:
        """Validate state-specific requirements."""
        state = signal.get("state")
        runtime = signal.get("runtime", {})

        if state == "triggered":
            # Triggered signals should have triggered_at timestamp
            if not runtime.get("triggered_at"):
                raise ValueError("triggered signals must have triggered_at timestamp")

            # Should have entry_mode for triggered signals
            if "entry_mode" not in signal:
                raise ValueError("triggered signals must have entry_mode")

            if signal["entry_mode"] not in ["momentum", "retest"]:
                raise ValueError(f"Invalid entry_mode: {signal['entry_mode']}")

        elif state == "invalid":
            # Invalid signals should have invalid_reason
            if not runtime.get("invalid_reason"):
                raise ValueError("invalid signals must have invalid_reason")

        elif state == "expired":
            # Expired signals should have armed_at timestamp
            if not runtime.get("armed_at"):
                raise ValueError("expired signals must have armed_at timestamp")

    def validate_signals(self, signals: list[dict[str, Any]]) -> list[bool]:
        """
        Validate multiple signals.

        Args:
            signals: List of signal dictionaries

        Returns:
            List of boolean validation results
        """
        results = []
        for signal in signals:
            try:
                result = self.validate_signal(signal)
                results.append(result)
            except SignalValidationError:
                results.append(False)
        return results

    def get_schema(self) -> dict[str, Any]:
        """Get the JSON schema for signals."""
        return self.schema.copy()


# Global validator instance
validator = SignalValidator()


def validate_signal(signal: dict[str, Any]) -> bool:
    """Convenience function to validate a signal."""
    return validator.validate_signal(signal)


def validate_signals(signals: list[dict[str, Any]]) -> list[bool]:
    """Convenience function to validate multiple signals."""
    return validator.validate_signals(signals)
