#!/usr/bin/env python3
"""Configuration validation script."""

import sys
from pathlib import Path
from typing import List

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ta2_app.config.loader import ConfigLoader
from ta2_app.config.validation import ConfigValidator, ValidationError


def validate_instrument_config(instrument_id: str) -> List[ValidationError]:
    """Validate configuration for a specific instrument."""
    loader = ConfigLoader.create()
    config = loader.merge_config(instrument_id)
    return ConfigValidator.validate_config(config)


def main():
    """Main validation function."""
    print("🔍 Validating TA2 App configuration...")
    
    # Load configuration
    loader = ConfigLoader.create()
    
    # Test instruments to validate
    test_instruments = [
        "BTC-USD-SWAP",
        "ETH-USD-SWAP", 
        "SOL-USD-SWAP",
        "DOGE-USD-SWAP",
        "UNKNOWN-INSTRUMENT"  # Should use defaults
    ]
    
    all_valid = True
    
    for instrument_id in test_instruments:
        print(f"\n📊 Validating {instrument_id}...")
        
        try:
            errors = validate_instrument_config(instrument_id)
            
            if errors:
                print(f"❌ Found {len(errors)} validation errors:")
                for error in errors:
                    print(f"  • {error.field}: {error.message} (value: {error.value})")
                all_valid = False
            else:
                print(f"✅ {instrument_id} configuration is valid")
                
        except Exception as e:
            print(f"❌ Error validating {instrument_id}: {e}")
            all_valid = False
    
    # Test plan-level overrides
    print(f"\n📋 Testing plan-level overrides...")
    test_overrides = {
        "breakout": {
            "penetration_pct": 0.1,
            "min_rvol": 2.0,
        }
    }
    
    try:
        config = loader.merge_config("BTC-USD-SWAP", test_overrides)
        errors = ConfigValidator.validate_config(config)
        
        if errors:
            print(f"❌ Plan override validation failed:")
            for error in errors:
                print(f"  • {error.field}: {error.message}")
            all_valid = False
        else:
            print(f"✅ Plan override validation passed")
            
    except Exception as e:
        print(f"❌ Error testing plan overrides: {e}")
        all_valid = False
    
    if all_valid:
        print(f"\n🎉 All configuration validation passed!")
        sys.exit(0)
    else:
        print(f"\n❌ Configuration validation failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()