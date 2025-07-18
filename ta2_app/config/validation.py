"""Configuration validation utilities."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationError:
    """Represents a configuration validation error."""
    field: str
    message: str
    value: Any


class ConfigValidator:
    """Validates configuration parameters."""

    @staticmethod
    def validate_breakout_params(params: dict[str, Any]) -> list[ValidationError]:
        """Validate breakout parameters."""
        errors = []

        # Validate penetration_pct
        if "penetration_pct" in params:
            value = params["penetration_pct"]
            if not isinstance(value, (int, float)) or value <= 0 or value > 1:
                errors.append(ValidationError(
                    field="penetration_pct",
                    message="Must be a positive number between 0 and 1",
                    value=value
                ))

        # Validate min_rvol
        if "min_rvol" in params:
            value = params["min_rvol"]
            if not isinstance(value, (int, float)) or value < 0:
                errors.append(ValidationError(
                    field="min_rvol",
                    message="Must be a non-negative number",
                    value=value
                ))

        # Validate confirm_close
        if "confirm_close" in params:
            value = params["confirm_close"]
            if not isinstance(value, bool):
                errors.append(ValidationError(
                    field="confirm_close",
                    message="Must be a boolean",
                    value=value
                ))

        # Validate penetration_natr_mult
        if "penetration_natr_mult" in params:
            value = params["penetration_natr_mult"]
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(ValidationError(
                    field="penetration_natr_mult",
                    message="Must be a positive number",
                    value=value
                ))

        # Validate confirm_time_ms
        if "confirm_time_ms" in params:
            value = params["confirm_time_ms"]
            if not isinstance(value, int) or value <= 0:
                errors.append(ValidationError(
                    field="confirm_time_ms",
                    message="Must be a positive integer",
                    value=value
                ))

        # Validate allow_retest_entry
        if "allow_retest_entry" in params:
            value = params["allow_retest_entry"]
            if not isinstance(value, bool):
                errors.append(ValidationError(
                    field="allow_retest_entry",
                    message="Must be a boolean",
                    value=value
                ))

        # Validate retest_band_pct
        if "retest_band_pct" in params:
            value = params["retest_band_pct"]
            if not isinstance(value, (int, float)) or value <= 0 or value > 1:
                errors.append(ValidationError(
                    field="retest_band_pct",
                    message="Must be a positive number between 0 and 1",
                    value=value
                ))

        # Validate fakeout_close_invalidate
        if "fakeout_close_invalidate" in params:
            value = params["fakeout_close_invalidate"]
            if not isinstance(value, bool):
                errors.append(ValidationError(
                    field="fakeout_close_invalidate",
                    message="Must be a boolean",
                    value=value
                ))

        # Validate ob_sweep_check
        if "ob_sweep_check" in params:
            value = params["ob_sweep_check"]
            if not isinstance(value, bool):
                errors.append(ValidationError(
                    field="ob_sweep_check",
                    message="Must be a boolean",
                    value=value
                ))

        # Validate min_break_range_atr
        if "min_break_range_atr" in params:
            value = params["min_break_range_atr"]
            if not isinstance(value, (int, float)) or value < 0:
                errors.append(ValidationError(
                    field="min_break_range_atr",
                    message="Must be a non-negative number",
                    value=value
                ))

        return errors

    @staticmethod
    def validate_atr_params(params: dict[str, Any]) -> list[ValidationError]:
        """Validate ATR parameters."""
        errors = []

        # Validate period
        if "period" in params:
            value = params["period"]
            if not isinstance(value, int) or value <= 0:
                errors.append(ValidationError(
                    field="period",
                    message="Must be a positive integer",
                    value=value
                ))

        # Validate multiplier
        if "multiplier" in params:
            value = params["multiplier"]
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(ValidationError(
                    field="multiplier",
                    message="Must be a positive number",
                    value=value
                ))

        return errors

    @staticmethod
    def validate_config(config: dict[str, Any]) -> list[ValidationError]:
        """Validate complete configuration."""
        errors = []

        if "breakout" in config:
            errors.extend(ConfigValidator.validate_breakout_params(config["breakout"]))

        if "atr" in config:
            errors.extend(ConfigValidator.validate_atr_params(config["atr"]))

        return errors
