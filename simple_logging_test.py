#!/usr/bin/env python3
"""Simple logging test to debug the issue."""

from ta2_app.logging.config import configure_logging
configure_logging(level="INFO", format_json=False, include_timestamp=True)

from ta2_app.state.transitions import BreakoutGateValidator

def test_simple_gate():
    """Test simple gate validation."""
    validator = BreakoutGateValidator()
    
    print("Testing RVOL gate...")
    try:
        result = validator.validate_rvol_gate(1.8, 1.5, "test-plan")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_gate()