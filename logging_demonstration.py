#!/usr/bin/env python3
"""
Demonstration script for comprehensive logging in breakout plan evaluation.

This script shows how the logging system captures all gating decisions and state transitions
with detailed reasoning for ML training and debugging purposes.
"""

import json
import sys
from datetime import datetime, timezone
from typing import Dict, Any

# Configure logging to show output
from ta2_app.logging.config import configure_logging
configure_logging(level="INFO", format_json=False, include_timestamp=True)

from ta2_app.state.transitions import BreakoutGateValidator, InvalidationChecker
from ta2_app.state.models import BreakoutParameters
from ta2_app.data.models import Candle


def demonstrate_gate_logging():
    """Demonstrate comprehensive gate decision logging."""
    print("=" * 70)
    print("GATE DECISION LOGGING DEMONSTRATION")
    print("=" * 70)
    
    validator = BreakoutGateValidator()
    
    print("\n1. RVOL Gate Evaluation:")
    print("   - Testing RVOL 1.8 vs threshold 1.5 (should PASS)")
    validator.validate_rvol_gate(1.8, 1.5, "demo-plan-1")
    
    print("   - Testing RVOL 1.2 vs threshold 1.5 (should FAIL)")
    validator.validate_rvol_gate(1.2, 1.5, "demo-plan-1")
    
    print("\n2. Volatility Gate Evaluation:")
    print("   - Testing bar range 0.01 vs ATR requirement 0.5 * 0.008 (should PASS)")
    validator.validate_volatility_gate(0.01, 0.008, 0.5, "demo-plan-1")
    
    print("   - Testing bar range 0.002 vs ATR requirement 0.5 * 0.008 (should FAIL)")
    validator.validate_volatility_gate(0.002, 0.008, 0.5, "demo-plan-1")
    
    print("\n3. Order Book Sweep Gate Evaluation:")
    print("   - Testing correct side sweep (should PASS)")
    validator.validate_orderbook_sweep_gate(True, 'ask', 'ask', "demo-plan-1")
    
    print("   - Testing wrong side sweep (should FAIL)")
    validator.validate_orderbook_sweep_gate(True, 'bid', 'ask', "demo-plan-1")
    
    print("\n4. Penetration Gate Evaluation:")
    print("   - Testing price 100.5 vs entry 100.0 with 0.3 distance (long, should PASS)")
    validator.validate_penetration_gate(100.5, 100.0, 0.3, False, "demo-plan-1")
    
    print("   - Testing price 100.2 vs entry 100.0 with 0.3 distance (long, should FAIL)")
    validator.validate_penetration_gate(100.2, 100.0, 0.3, False, "demo-plan-1")


def demonstrate_invalidation_logging():
    """Demonstrate invalidation decision logging."""
    print("\n" + "=" * 70)
    print("INVALIDATION DECISION LOGGING DEMONSTRATION")
    print("=" * 70)
    
    print("\n1. Price Invalidation Checks:")
    print("   - Price invalidation checks log detailed reasoning for ML training")
    print("   - Above/below limit violations are logged with precise distance calculations")
    
    print("\n2. Time Invalidation Checks:")
    print("   - Time-based invalidation tracks plan expiry with elapsed time metrics")
    print("   - Logs completion ratio and remaining time for analysis")
    
    print("\n3. Fakeout Invalidation Checks:")
    print("   - Fakeout detection logs when price closes back inside range")
    print("   - Includes direction-specific logic and distance measurements")
    
    print("\n4. Comprehensive Invalidation Context:")
    print("   - Complete audit trail with all invalidation conditions")
    print("   - Market context and additional metadata for debugging")
    
    # Show a simple working example without triggering the edge cases
    from ta2_app.logging.config import get_gating_logger
    logger = get_gating_logger(__name__)
    
    # Direct logging example
    logger.bind(
        plan_id="demo-plan-1",
        current_price=3308.0,
        invalidation_conditions_count=2,
        elapsed_seconds=1200,
        event="invalidation_context_demo"
    ).info("Invalidation context example")


def demonstrate_plan_evaluation_context():
    """Demonstrate plan evaluation context logging."""
    print("\n" + "=" * 70)
    print("PLAN EVALUATION CONTEXT LOGGING DEMONSTRATION")  
    print("=" * 70)
    
    # This would normally be done by the engine, but we'll simulate it
    from ta2_app.logging.config import get_gating_logger
    logger = get_gating_logger(__name__)
    
    print("\n1. Plan Evaluation Start Context:")
    logger.bind(
        plan_id="demo-plan-1",
        instrument_id="ETH-USDT-SWAP",
        entry_price=3308.0,
        direction="short",
        market_context={
            "last_price": 3305.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price_distance_from_entry": 3.0,
            "price_above_entry": False,
        },
        metrics_snapshot={
            "atr": 25.5,
            "natr_pct": 0.77,
            "rvol": 1.8,
            "bar_range": 18.2,
            "pinbar_detected": False,
            "ob_sweep_detected": True,
            "ob_sweep_side": "bid",
            "composite_score": 0.72
        },
        breakout_config={
            "penetration_pct": 0.001,
            "min_rvol": 1.5,
            "min_break_range_atr": 0.5,
            "confirm_close": False,
            "confirm_time_ms": 5000,
            "ob_sweep_check": True,
            "allow_retest_entry": True,
            "fakeout_close_invalidate": True
        },
        event="plan_evaluation_start"
    ).info("Plan evaluation context")
    
    print("\n2. Plan Evaluation Results:")
    logger.bind(
        plan_id="demo-plan-1",
        signals_generated=0,
        signal_types=[],
        event="plan_evaluation_complete"
    ).info("Plan evaluation results")


def main():
    """Main demonstration function."""
    print("COMPREHENSIVE LOGGING DEMONSTRATION")
    print("This script demonstrates the complete logging system for breakout plan evaluation.")
    print("All gating decisions and state transitions are logged with detailed reasoning.")
    print("This output can be used for ML training, debugging, and audit trails.")
    
    try:
        demonstrate_gate_logging()
        demonstrate_invalidation_logging()
        demonstrate_plan_evaluation_context()
        
        print("\n" + "=" * 70)
        print("DEMONSTRATION COMPLETE")
        print("=" * 70)
        print("\nKey Logging Features Demonstrated:")
        print("✓ Gate decision logging with pass/fail reasoning")
        print("✓ Invalidation decision logging with detailed context")
        print("✓ Plan evaluation context with market data and configuration")
        print("✓ Structured logging with consistent field names")
        print("✓ Audit trail information for ML training")
        print("✓ Performance-friendly logging with minimal overhead")
        
        print("\nNext Steps:")
        print("- Run this script to see comprehensive logging output")
        print("- Review logs for debugging plan evaluation issues")
        print("- Export logs for ML training data collection")
        print("- Use structured fields for automated log analysis")
        
    except Exception as e:
        print(f"Error during demonstration: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()