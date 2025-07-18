"""Configuration loader with 3-tier parameter precedence."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from .defaults import DefaultConfig, get_default_config


@dataclass(frozen=True)
class ConfigLoader:
    """Manages configuration loading with 3-tier precedence."""

    config_dir: Path
    defaults: DefaultConfig

    @classmethod
    def create(cls, config_dir: Optional[Path] = None) -> "ConfigLoader":
        """Create a ConfigLoader instance."""
        if config_dir is None:
            config_dir = Path(__file__).parent.parent.parent / "config"

        return cls(
            config_dir=config_dir,
            defaults=get_default_config(),
        )

    def load_instrument_config(self, instrument_id: str) -> dict[str, Any]:
        """Load instrument-specific configuration overrides."""
        instruments_file = self.config_dir / "instruments.yaml"

        if not instruments_file.exists():
            return {}

        with open(instruments_file) as f:
            instruments_config = yaml.safe_load(f)

        return instruments_config.get("instruments", {}).get(instrument_id, {})  # type: ignore[no-any-return]

    def merge_config(
        self,
        instrument_id: str,
        plan_overrides: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Merge configuration with 3-tier precedence.

        Priority order:
        1. Per-plan overrides (highest priority)
        2. Instrument-specific overrides
        3. Global defaults (lowest priority)
        """
        # Start with global defaults
        config = self._dataclass_to_dict(self.defaults)

        # Apply instrument-specific overrides
        instrument_config = self.load_instrument_config(instrument_id)
        config = self._deep_merge(config, instrument_config)

        # Apply per-plan overrides
        if plan_overrides:
            config = self._deep_merge(config, plan_overrides)

        return config

    def _dataclass_to_dict(self, obj: Any) -> dict[str, Any]:
        """Convert nested dataclasses to dictionary."""
        if hasattr(obj, '__dataclass_fields__'):
            result = {}
            for field_name, _field in obj.__dataclass_fields__.items():
                value = getattr(obj, field_name)
                if hasattr(value, '__dataclass_fields__'):
                    result[field_name] = self._dataclass_to_dict(value)
                else:
                    result[field_name] = value
            return result
        return obj  # type: ignore[no-any-return]

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result
