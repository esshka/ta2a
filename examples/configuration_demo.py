#!/usr/bin/env python3
"""
Configuration Demo - TA2 Breakout Evaluation Engine

This script demonstrates the configuration system of the TA2 engine,
showing how to:
- Load and validate configuration files
- Use 3-tier configuration precedence
- Override parameters at different levels
- Validate configuration parameters
- Create custom configurations for different scenarios

Run: python examples/configuration_demo.py
"""

import json
import yaml
from typing import Dict, Any
from pathlib import Path

from ta2_app.config.loader import ConfigLoader
from ta2_app.config.validation import ConfigValidator
from ta2_app.config.defaults import DEFAULT_CONFIG
from ta2_app.engine import BreakoutEvaluationEngine


def demonstrate_default_config():
    """Show the default configuration structure."""
    print("⚙️ DEFAULT CONFIGURATION")
    print("=" * 50)
    
    print("1. Default breakout parameters:")
    breakout_params = DEFAULT_CONFIG.get('breakout', {})
    for param, value in breakout_params.items():
        print(f"   {param}: {value}")
    
    print("\n2. Default ATR parameters:")
    atr_params = DEFAULT_CONFIG.get('atr', {})
    for param, value in atr_params.items():
        print(f"   {param}: {value}")
    
    print("\n3. Default volume parameters:")
    volume_params = DEFAULT_CONFIG.get('volume', {})
    for param, value in volume_params.items():
        print(f"   {param}: {value}")
    
    print()


def demonstrate_config_validation():
    """Show configuration validation."""
    print("✅ CONFIGURATION VALIDATION")
    print("=" * 50)
    
    # Valid configuration
    print("1. Validating valid configuration:")
    valid_config = {
        "penetration_pct": 0.05,
        "min_rvol": 1.5,
        "confirm_close": True,
        "confirm_time_ms": 750,
        "allow_retest_entry": False,
        "retest_band_pct": 0.03,
        "fakeout_close_invalidate": True,
        "ob_sweep_check": True,
        "min_break_range_atr": 0.5,
        "penetration_natr_mult": 0.25
    }
    
    errors = ConfigValidator.validate_breakout_params(valid_config)
    if errors:
        print("   ✗ Validation errors found:")
        for error in errors:
            print(f"     {error.field}: {error.message} (got: {error.value})")
    else:
        print("   ✓ Configuration is valid!")
    
    # Invalid configuration
    print("\n2. Validating invalid configuration:")
    invalid_config = {
        "penetration_pct": -0.05,  # Invalid: negative
        "min_rvol": 0.5,           # Invalid: too low
        "confirm_close": "yes",    # Invalid: should be boolean
        "confirm_time_ms": -100,   # Invalid: negative
        "retest_band_pct": 1.5,    # Invalid: too high
        "unknown_param": "value"   # Invalid: unknown parameter
    }
    
    errors = ConfigValidator.validate_breakout_params(invalid_config)
    if errors:
        print("   ✗ Validation errors found:")
        for error in errors:
            print(f"     {error.field}: {error.message} (got: {error.value})")
    else:
        print("   ✓ Configuration is valid (unexpected)!")
    
    print()


def demonstrate_config_precedence():
    """Show 3-tier configuration precedence."""
    print("🏆 CONFIGURATION PRECEDENCE")
    print("=" * 50)
    
    # Create a temporary config loader
    config_loader = ConfigLoader.create()
    
    # Test different precedence scenarios
    print("1. Global defaults only:")
    config = config_loader.merge_config("UNKNOWN-INSTRUMENT", {})
    breakout_config = config.get('breakout', {})
    print(f"   penetration_pct: {breakout_config.get('penetration_pct')}")
    print(f"   min_rvol: {breakout_config.get('min_rvol')}")
    print(f"   confirm_close: {breakout_config.get('confirm_close')}")
    
    print("\n2. Simulated instrument-specific override:")
    # Simulate instrument config (normally loaded from instruments.yaml)
    instrument_overrides = {
        "penetration_pct": 0.08,  # Override global default
        "min_rvol": 2.0          # Override global default
    }
    
    # Manually merge for demonstration
    merged_config = config.copy()
    merged_config['breakout'].update(instrument_overrides)
    
    print(f"   penetration_pct: {merged_config['breakout']['penetration_pct']} (overridden)")
    print(f"   min_rvol: {merged_config['breakout']['min_rvol']} (overridden)")
    print(f"   confirm_close: {merged_config['breakout']['confirm_close']} (default)")
    
    print("\n3. Plan-specific overrides:")
    plan_overrides = {
        "allow_retest_entry": True,  # Override default
        "retest_band_pct": 0.02     # Override default
    }
    
    # Show final merged configuration
    final_config = merged_config.copy()
    final_config['breakout'].update(plan_overrides)
    
    print(f"   penetration_pct: {final_config['breakout']['penetration_pct']} (instrument)")
    print(f"   min_rvol: {final_config['breakout']['min_rvol']} (instrument)")
    print(f"   confirm_close: {final_config['breakout']['confirm_close']} (global)")
    print(f"   allow_retest_entry: {final_config['breakout']['allow_retest_entry']} (plan)")
    print(f"   retest_band_pct: {final_config['breakout']['retest_band_pct']} (plan)")
    
    print()


def demonstrate_config_scenarios():
    """Show different configuration scenarios."""
    print("🎯 CONFIGURATION SCENARIOS")
    print("=" * 50)
    
    scenarios = [
        {
            "name": "Conservative (Low Volume, High Penetration)",
            "description": "Suitable for stable, low-volume instruments",
            "params": {
                "penetration_pct": 0.10,
                "min_rvol": 1.0,
                "confirm_close": True,
                "fakeout_close_invalidate": True,
                "ob_sweep_check": False,
                "min_break_range_atr": 0.8
            }
        },
        {
            "name": "Aggressive (High Volume, Low Penetration)",
            "description": "Suitable for high-volume, volatile instruments",
            "params": {
                "penetration_pct": 0.02,
                "min_rvol": 2.5,
                "confirm_close": False,
                "confirm_time_ms": 500,
                "fakeout_close_invalidate": False,
                "ob_sweep_check": True,
                "min_break_range_atr": 0.3
            }
        },
        {
            "name": "Retest Mode",
            "description": "Wait for retest confirmation after breakout",
            "params": {
                "penetration_pct": 0.05,
                "min_rvol": 1.5,
                "allow_retest_entry": True,
                "retest_band_pct": 0.04,
                "confirm_close": True,
                "fakeout_close_invalidate": True
            }
        },
        {
            "name": "Scalping (Fast Entry)",
            "description": "Quick entries with minimal confirmation",
            "params": {
                "penetration_pct": 0.03,
                "min_rvol": 1.2,
                "confirm_close": False,
                "confirm_time_ms": 250,
                "fakeout_close_invalidate": False,
                "ob_sweep_check": False,
                "min_break_range_atr": 0.2
            }
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"{i}. {scenario['name']}")
        print(f"   Description: {scenario['description']}")
        print(f"   Parameters:")
        
        # Validate the scenario configuration
        errors = ConfigValidator.validate_breakout_params(scenario['params'])
        if errors:
            print(f"   ✗ Configuration has errors:")
            for error in errors:
                print(f"     {error.field}: {error.message}")
        else:
            print(f"   ✓ Configuration is valid")
            
        for param, value in scenario['params'].items():
            print(f"     {param}: {value}")
        print()


def demonstrate_engine_with_config():
    """Show how configuration is used in the engine."""
    print("🚀 ENGINE WITH CUSTOM CONFIGURATION")
    print("=" * 50)
    
    # Create engine
    engine = BreakoutEvaluationEngine()
    
    # Create plans with different configurations
    plans = [
        {
            "id": "conservative_plan",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 45000.0,
            "created_at": "2025-01-17T04:08:23.750427",
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.08,
                    "min_rvol": 1.0,
                    "confirm_close": True,
                    "fakeout_close_invalidate": True
                }
            }
        },
        {
            "id": "aggressive_plan",
            "instrument_id": "ETH-USDT-SWAP",
            "direction": "short",
            "entry_type": "breakout",
            "entry_price": 3308.0,
            "created_at": "2025-01-17T04:08:23.750427",
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.02,
                    "min_rvol": 2.5,
                    "confirm_close": False,
                    "confirm_time_ms": 500
                }
            }
        },
        {
            "id": "retest_plan",
            "instrument_id": "ADA-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 0.85,
            "created_at": "2025-01-17T04:08:23.750427",
            "extra_data": {
                "breakout_params": {
                    "allow_retest_entry": True,
                    "retest_band_pct": 0.04,
                    "penetration_pct": 0.05,
                    "min_rvol": 1.5
                }
            }
        }
    ]
    
    # Add plans to engine
    for plan in plans:
        engine.add_plan(plan)
        
        # Show the plan configuration
        print(f"Added plan: {plan['id']}")
        print(f"  Instrument: {plan['instrument_id']}")
        print(f"  Direction: {plan['direction']}")
        print(f"  Entry Price: ${plan['entry_price']}")
        
        # Show custom parameters
        breakout_params = plan['extra_data'].get('breakout_params', {})
        if breakout_params:
            print(f"  Custom Parameters:")
            for param, value in breakout_params.items():
                print(f"    {param}: {value}")
        else:
            print(f"  Using default parameters")
        print()
    
    # Show engine stats
    stats = engine.get_runtime_stats()
    print(f"Engine Stats:")
    print(f"  Active plans: {stats['active_plans']}")
    print(f"  Tracked instruments: {stats['tracked_instruments']}")
    
    print()


def demonstrate_yaml_config():
    """Show YAML configuration file format."""
    print("📄 YAML CONFIGURATION FORMAT")
    print("=" * 50)
    
    # Create sample configuration
    sample_config = {
        "breakout_params": {
            "penetration_pct": 0.05,
            "penetration_natr_mult": 0.25,
            "min_rvol": 1.5,
            "confirm_close": True,
            "confirm_time_ms": 750,
            "allow_retest_entry": False,
            "retest_band_pct": 0.03,
            "fakeout_close_invalidate": True,
            "ob_sweep_check": True,
            "min_break_range_atr": 0.5
        },
        "atr_params": {
            "period": 14,
            "multiplier": 2.0
        },
        "volume_params": {
            "rvol_period": 20,
            "min_volume_threshold": 1000
        },
        "instruments": {
            "ETH-USDT-SWAP": {
                "breakout_params": {
                    "penetration_pct": 0.08,
                    "min_rvol": 2.0
                }
            },
            "BTC-USDT-SWAP": {
                "breakout_params": {
                    "penetration_pct": 0.03,
                    "min_rvol": 1.2
                }
            }
        }
    }
    
    print("1. Sample YAML configuration structure:")
    yaml_content = yaml.dump(sample_config, default_flow_style=False, sort_keys=False)
    print(yaml_content)
    
    print("2. JSON equivalent:")
    json_content = json.dumps(sample_config, indent=2)
    print(json_content)
    
    print()


def main():
    """Main demonstration function."""
    print("⚙️ TA2 CONFIGURATION SYSTEM DEMO")
    print("=" * 60)
    print("This demo shows the configuration capabilities of the TA2 system.")
    print()
    
    # Run all demonstrations
    demonstrate_default_config()
    demonstrate_config_validation()
    demonstrate_config_precedence()
    demonstrate_config_scenarios()
    demonstrate_engine_with_config()
    demonstrate_yaml_config()
    
    print("✅ Configuration demo completed!")
    print("   Key takeaways:")
    print("   - Flexible 3-tier configuration precedence")
    print("   - Comprehensive parameter validation")
    print("   - Pre-built scenarios for different trading styles")
    print("   - Easy integration with the evaluation engine")
    print("   - Support for both YAML and JSON formats")


if __name__ == "__main__":
    main()