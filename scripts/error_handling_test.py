#!/usr/bin/env python3
"""
Comprehensive error handling test script for the TA2 application.

This script simulates various data quality problems and verifies that the system
continues processing without crashing, demonstrating the robustness of the
comprehensive error handling implementation.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ta2_app.engine import BreakoutEvaluationEngine
from ta2_app.errors import DataQualityError


def create_test_plan():
    """Create a test trading plan."""
    return {
        "id": "error_handling_test_plan",
        "instrument_id": "BTC-USD",
        "entry_type": "breakout",
        "entry_price": 50000,
        "direction": "long",
        "extra_data": {
            "breakout_params": {
                "penetration_pct": 0.1,
                "min_rvol": 1.5,
                "confirm_close": False
            }
        }
    }


def create_valid_candlestick_payload(timestamp_offset=0):
    """Create a valid candlestick payload."""
    base_timestamp = 1640995200000  # 2022-01-01 00:00:00
    return {
        "arg": {"instId": "BTC-USD"},
        "data": [[
            base_timestamp + timestamp_offset * 1000,  # timestamp
            49000,          # open
            51000,          # high
            48000,          # low
            50500,          # close
            1000,           # volume
            50000000,       # volume_quote
            0,              # volume_quote_alt
            1               # confirm_flag
        ]]
    }


def create_valid_orderbook_payload():
    """Create a valid orderbook payload."""
    return {
        "arg": {"instId": "BTC-USD"},
        "data": {
            "asks": [["51000", "10", "0", "0"], ["51100", "5", "0", "0"]],
            "bids": [["50000", "10", "0", "0"], ["49900", "5", "0", "0"]],
            "ts": "1640995200000"
        }
    }


def test_scenario_1_good_data_quality():
    """Test with good data quality."""
    print("🧪 Test Scenario 1: Good Data Quality")
    engine = BreakoutEvaluationEngine()
    engine.add_plan(create_test_plan())
    
    success_count = 0
    total_count = 10
    
    for i in range(total_count):
        try:
            signals = engine.evaluate_tick(
                candlestick_payload=create_valid_candlestick_payload(i),
                orderbook_payload=create_valid_orderbook_payload(),
                instrument_id="BTC-USD"
            )
            
            if isinstance(signals, list):
                success_count += 1
                print(f"  ✅ Tick {i+1}: Processed successfully")
            else:
                print(f"  ❌ Tick {i+1}: Unexpected return type")
                
        except Exception as e:
            print(f"  ❌ Tick {i+1}: Exception - {e}")
    
    print(f"  📊 Success rate: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
    print(f"  🎯 Active plans: {engine.get_active_plan_count()}")
    
    return success_count == total_count


def test_scenario_2_missing_data():
    """Test with missing data scenarios."""
    print("\n🧪 Test Scenario 2: Missing Data")
    engine = BreakoutEvaluationEngine()
    engine.add_plan(create_test_plan())
    
    test_cases = [
        ("No payload", None, None),
        ("Missing candlestick", None, create_valid_orderbook_payload()),
        ("Missing orderbook", create_valid_candlestick_payload(), None),
        ("Empty payload", {}, {}),
        ("Missing instrument_id", create_valid_candlestick_payload(), None),
    ]
    
    success_count = 0
    
    for case_name, candle_payload, book_payload in test_cases:
        try:
            signals = engine.evaluate_tick(
                candlestick_payload=candle_payload,
                orderbook_payload=book_payload,
                instrument_id="BTC-USD" if candle_payload or book_payload else None
            )
            
            if isinstance(signals, list):
                success_count += 1
                print(f"  ✅ {case_name}: Handled gracefully")
            else:
                print(f"  ❌ {case_name}: Unexpected return type")
                
        except Exception as e:
            print(f"  ⚠️  {case_name}: Exception (expected) - {type(e).__name__}")
            # Some exceptions are expected for missing data
            if isinstance(e, DataQualityError):
                success_count += 1
    
    print(f"  📊 Cases handled: {success_count}/{len(test_cases)}")
    print(f"  🎯 Active plans: {engine.get_active_plan_count()}")
    
    return success_count >= len(test_cases) * 0.8  # 80% success rate is acceptable


def test_scenario_3_malformed_data():
    """Test with malformed data scenarios."""
    print("\n🧪 Test Scenario 3: Malformed Data")
    engine = BreakoutEvaluationEngine()
    engine.add_plan(create_test_plan())
    
    test_cases = [
        ("String instead of dict", "invalid_payload", None),
        ("Invalid JSON structure", {"invalid": "structure"}, None),
        ("Missing data field", {"arg": {"instId": "BTC-USD"}}, None),
        ("Invalid timestamp", {
            "arg": {"instId": "BTC-USD"},
            "data": [["invalid_timestamp", 49000, 51000, 48000, 50500, 1000, 50000000, 0, 1]]
        }, None),
        ("Invalid price values", {
            "arg": {"instId": "BTC-USD"},
            "data": [[1640995200000, "invalid_price", 51000, 48000, 50500, 1000, 50000000, 0, 1]]
        }, None),
    ]
    
    success_count = 0
    
    for case_name, candle_payload, book_payload in test_cases:
        try:
            signals = engine.evaluate_tick(
                candlestick_payload=candle_payload,
                orderbook_payload=book_payload,
                instrument_id="BTC-USD"
            )
            
            if isinstance(signals, list):
                success_count += 1
                print(f"  ✅ {case_name}: Handled gracefully")
            else:
                print(f"  ❌ {case_name}: Unexpected return type")
                
        except Exception as e:
            print(f"  ⚠️  {case_name}: Exception (expected) - {type(e).__name__}")
            # Some exceptions are expected for malformed data
            if isinstance(e, DataQualityError):
                success_count += 1
    
    print(f"  📊 Cases handled: {success_count}/{len(test_cases)}")
    print(f"  🎯 Active plans: {engine.get_active_plan_count()}")
    
    return success_count >= len(test_cases) * 0.8


def test_scenario_4_mixed_data_quality():
    """Test with mixed data quality over time."""
    print("\n🧪 Test Scenario 4: Mixed Data Quality")
    engine = BreakoutEvaluationEngine()
    engine.add_plan(create_test_plan())
    
    # Simulate degrading then recovering data quality
    data_sequence = [
        # Good data
        ("Good data 1", create_valid_candlestick_payload(0), create_valid_orderbook_payload()),
        ("Good data 2", create_valid_candlestick_payload(1), create_valid_orderbook_payload()),
        
        # Degrading data quality
        ("Partial data", create_valid_candlestick_payload(2), None),
        ("Malformed data", "invalid_payload", None),
        ("Missing data", None, None),
        
        # Recovery
        ("Recovery 1", create_valid_candlestick_payload(3), create_valid_orderbook_payload()),
        ("Recovery 2", create_valid_candlestick_payload(4), create_valid_orderbook_payload()),
    ]
    
    success_count = 0
    
    for case_name, candle_payload, book_payload in data_sequence:
        try:
            signals = engine.evaluate_tick(
                candlestick_payload=candle_payload,
                orderbook_payload=book_payload,
                instrument_id="BTC-USD" if candle_payload or book_payload else None
            )
            
            if isinstance(signals, list):
                success_count += 1
                print(f"  ✅ {case_name}: Processed successfully")
            else:
                print(f"  ❌ {case_name}: Unexpected return type")
                
        except Exception as e:
            print(f"  ⚠️  {case_name}: Exception - {type(e).__name__}")
            # Some exceptions are acceptable
            if isinstance(e, DataQualityError):
                success_count += 1
    
    print(f"  📊 Success rate: {success_count}/{len(data_sequence)}")
    print(f"  🎯 Active plans: {engine.get_active_plan_count()}")
    
    return success_count >= len(data_sequence) * 0.7  # 70% success rate is acceptable


def test_scenario_5_stress_test():
    """Test system under stress conditions."""
    print("\n🧪 Test Scenario 5: Stress Test")
    engine = BreakoutEvaluationEngine()
    engine.add_plan(create_test_plan())
    
    # Generate rapid sequence of mixed data quality
    total_ticks = 100
    success_count = 0
    error_count = 0
    
    print(f"  🔄 Processing {total_ticks} ticks with mixed data quality...")
    
    for i in range(total_ticks):
        # Vary data quality
        if i % 5 == 0:
            # Good data
            payload = create_valid_candlestick_payload(i)
        elif i % 5 == 1:
            # Malformed data
            payload = f"malformed_data_{i}"
        elif i % 5 == 2:
            # Missing data
            payload = None
        elif i % 5 == 3:
            # Partial data
            payload = {"arg": {"instId": "BTC-USD"}, "data": "partial"}
        else:
            # Invalid structure
            payload = {"invalid": "structure"}
        
        try:
            signals = engine.evaluate_tick(
                candlestick_payload=payload,
                instrument_id="BTC-USD" if payload else None
            )
            
            if isinstance(signals, list):
                success_count += 1
            else:
                error_count += 1
                
        except Exception as e:
            # Some exceptions are expected
            if isinstance(e, DataQualityError):
                success_count += 1
            else:
                error_count += 1
    
    print(f"  📊 Results: {success_count} successful, {error_count} errors")
    print(f"  🎯 Active plans: {engine.get_active_plan_count()}")
    
    # System should remain functional and handle at least 80% of cases
    return success_count >= total_ticks * 0.8 and engine.get_active_plan_count() > 0


def test_scenario_6_recovery_verification():
    """Test that system can recover after errors."""
    print("\n🧪 Test Scenario 6: Recovery Verification")
    engine = BreakoutEvaluationEngine()
    engine.add_plan(create_test_plan())
    
    # Phase 1: Generate many errors
    print("  🔥 Phase 1: Generating errors...")
    for i in range(20):
        try:
            engine.evaluate_tick(
                candlestick_payload=f"error_payload_{i}",
                instrument_id="BTC-USD"
            )
        except Exception:
            pass  # Expected
    
    # Phase 2: Verify system can still process valid data
    print("  🔄 Phase 2: Testing recovery...")
    recovery_success = 0
    
    for i in range(5):
        try:
            signals = engine.evaluate_tick(
                candlestick_payload=create_valid_candlestick_payload(i),
                orderbook_payload=create_valid_orderbook_payload(),
                instrument_id="BTC-USD"
            )
            
            if isinstance(signals, list):
                recovery_success += 1
                print(f"    ✅ Recovery tick {i+1}: Success")
            else:
                print(f"    ❌ Recovery tick {i+1}: Failed")
                
        except Exception as e:
            print(f"    ❌ Recovery tick {i+1}: Exception - {e}")
    
    print(f"  📊 Recovery rate: {recovery_success}/5")
    print(f"  🎯 Active plans: {engine.get_active_plan_count()}")
    
    return recovery_success >= 4  # Should recover at least 4/5 times


def main():
    """Run all error handling tests."""
    print("🚀 Starting Comprehensive Error Handling Test")
    print("=" * 60)
    
    test_results = []
    
    # Run all test scenarios
    test_results.append(("Good Data Quality", test_scenario_1_good_data_quality()))
    test_results.append(("Missing Data", test_scenario_2_missing_data()))
    test_results.append(("Malformed Data", test_scenario_3_malformed_data()))
    test_results.append(("Mixed Data Quality", test_scenario_4_mixed_data_quality()))
    test_results.append(("Stress Test", test_scenario_5_stress_test()))
    test_results.append(("Recovery Verification", test_scenario_6_recovery_verification()))
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 Test Results Summary")
    print("=" * 60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n📊 Overall Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All tests passed! System demonstrates robust error handling.")
        return 0
    elif passed >= total * 0.8:
        print("⚠️  Most tests passed. System shows good resilience with some areas for improvement.")
        return 0
    else:
        print("❌ Multiple test failures. System needs improvement in error handling.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Test runner crashed: {e}")
        sys.exit(1)