"""Unit tests for configuration management."""

import pytest
from pathlib import Path
from typing import Dict, Any

from ta2_app.config.defaults import get_default_config
from ta2_app.config.loader import ConfigLoader
from ta2_app.config.validation import ConfigValidator


class TestDefaultConfig:
    """Test suite for default configuration."""

    def test_default_config_creation(self) -> None:
        """Test that default configuration can be created."""
        config = get_default_config()
        assert config is not None
        assert config.breakout.penetration_pct == 0.05
        assert config.breakout.min_rvol == 1.5
        assert config.atr.period == 14


class TestConfigLoader:
    """Test suite for configuration loader."""

    def test_config_loader_creation(self) -> None:
        """Test that ConfigLoader can be created."""
        loader = ConfigLoader.create()
        assert loader is not None
        assert isinstance(loader.config_dir, Path)

    def test_merge_config_defaults_only(self) -> None:
        """Test config merging with defaults only."""
        loader = ConfigLoader.create()
        config = loader.merge_config("UNKNOWN-INSTRUMENT")
        
        assert "breakout" in config
        assert config["breakout"]["penetration_pct"] == 0.05
        assert config["breakout"]["min_rvol"] == 1.5

    def test_merge_config_with_overrides(self) -> None:
        """Test config merging with plan overrides."""
        loader = ConfigLoader.create()
        overrides = {
            "breakout": {
                "penetration_pct": 0.1,
                "min_rvol": 2.0,
            }
        }
        
        config = loader.merge_config("UNKNOWN-INSTRUMENT", overrides)
        
        assert config["breakout"]["penetration_pct"] == 0.1
        assert config["breakout"]["min_rvol"] == 2.0
        # Other defaults should remain
        assert config["breakout"]["confirm_close"] is True


class TestConfigValidator:
    """Test suite for configuration validation."""

    def test_valid_breakout_params(self) -> None:
        """Test validation of valid breakout parameters."""
        params = {
            "penetration_pct": 0.05,
            "min_rvol": 1.5,
            "confirm_close": True,
        }
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 0

    def test_invalid_penetration_pct(self) -> None:
        """Test validation of invalid penetration_pct."""
        params = {"penetration_pct": -0.1}
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 1
        assert errors[0].field == "penetration_pct"

    def test_invalid_min_rvol(self) -> None:
        """Test validation of invalid min_rvol."""
        params = {"min_rvol": -1.0}
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 1
        assert errors[0].field == "min_rvol"

    def test_invalid_confirm_close(self) -> None:
        """Test validation of invalid confirm_close."""
        params = {"confirm_close": "invalid"}
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 1
        assert errors[0].field == "confirm_close"

    def test_invalid_penetration_natr_mult(self) -> None:
        """Test validation of invalid penetration_natr_mult."""
        params = {"penetration_natr_mult": -0.5}
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 1
        assert errors[0].field == "penetration_natr_mult"
        assert "Must be a positive number" in errors[0].message

    def test_invalid_confirm_time_ms(self) -> None:
        """Test validation of invalid confirm_time_ms."""
        params = {"confirm_time_ms": -100}
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 1
        assert errors[0].field == "confirm_time_ms"
        assert "Must be a positive integer" in errors[0].message

    def test_invalid_allow_retest_entry(self) -> None:
        """Test validation of invalid allow_retest_entry."""
        params = {"allow_retest_entry": "invalid"}
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 1
        assert errors[0].field == "allow_retest_entry"
        assert "Must be a boolean" in errors[0].message

    def test_invalid_retest_band_pct(self) -> None:
        """Test validation of invalid retest_band_pct."""
        params = {"retest_band_pct": 1.5}
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 1
        assert errors[0].field == "retest_band_pct"
        assert "Must be a positive number between 0 and 1" in errors[0].message

    def test_invalid_fakeout_close_invalidate(self) -> None:
        """Test validation of invalid fakeout_close_invalidate."""
        params = {"fakeout_close_invalidate": "invalid"}
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 1
        assert errors[0].field == "fakeout_close_invalidate"
        assert "Must be a boolean" in errors[0].message

    def test_invalid_ob_sweep_check(self) -> None:
        """Test validation of invalid ob_sweep_check."""
        params = {"ob_sweep_check": "invalid"}
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 1
        assert errors[0].field == "ob_sweep_check"
        assert "Must be a boolean" in errors[0].message

    def test_invalid_min_break_range_atr(self) -> None:
        """Test validation of invalid min_break_range_atr."""
        params = {"min_break_range_atr": -0.5}
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 1
        assert errors[0].field == "min_break_range_atr"
        assert "Must be a non-negative number" in errors[0].message

    def test_multiple_validation_errors(self) -> None:
        """Test validation with multiple invalid parameters."""
        params = {
            "penetration_pct": 2.0,  # > 1
            "min_rvol": -1.0,        # negative
            "confirm_close": "invalid",  # not boolean
            "allow_retest_entry": "invalid",  # not boolean
            "retest_band_pct": 1.5,  # > 1
        }
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 5
        
        error_fields = [err.field for err in errors]
        assert "penetration_pct" in error_fields
        assert "min_rvol" in error_fields
        assert "confirm_close" in error_fields
        assert "allow_retest_entry" in error_fields
        assert "retest_band_pct" in error_fields

    def test_all_valid_new_params(self) -> None:
        """Test validation of all new parameters with valid values."""
        params = {
            "penetration_natr_mult": 0.25,
            "confirm_time_ms": 750,
            "allow_retest_entry": True,
            "retest_band_pct": 0.03,
            "fakeout_close_invalidate": False,
            "ob_sweep_check": True,
            "min_break_range_atr": 0.5,
        }
        
        errors = ConfigValidator.validate_breakout_params(params)
        assert len(errors) == 0