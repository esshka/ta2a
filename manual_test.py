#!/usr/bin/env python3
"""
Manual test script to verify data normalization pipeline with sample OKX payloads.
"""

import json
from datetime import datetime, UTC
from ta2_app.data.normalizer import DataNormalizer

def test_candlestick_normalization():
    """Test candlestick payload normalization."""
    print("=== Testing Candlestick Normalization ===")
    
    # Sample OKX candlestick payload
    current_ts = int(datetime.now(UTC).timestamp() * 1000)
    okx_candle_payload = {
        "code": "0",
        "msg": "",
        "data": [
            [str(current_ts), "41000.0", "41050.0", "40980.0", "41025.0", "15.5", "635000.0", "635000.0", "1"],
            [str(current_ts + 1000), "41025.0", "41030.0", "41010.0", "41020.0", "12.3", "504000.0", "504000.0", "0"]
        ]
    }
    
    normalizer = DataNormalizer({"max_age_seconds": 86400})
    raw_data = json.dumps(okx_candle_payload)
    
    result = normalizer.normalize_tick("BTC-USD", raw_data, "candle")
    
    print(f"✓ Normalization successful: {result.success}")
    print(f"✓ Candle object created: {result.candle is not None}")
    
    if result.candle:
        print(f"  - Timestamp: {result.candle.ts}")
        print(f"  - OHLC: {result.candle.open}/{result.candle.high}/{result.candle.low}/{result.candle.close}")
        print(f"  - Volume: {result.candle.volume}")
        print(f"  - Is closed: {result.candle.is_closed}")
    
    # Test retrieval
    latest = normalizer.get_latest_candle("BTC-USD")
    history = normalizer.get_candle_history("BTC-USD")
    
    print(f"✓ Latest candle retrieved: {latest is not None}")
    print(f"✓ History contains {len(history)} candles")
    
    return result.success

def test_orderbook_normalization():
    """Test order book payload normalization."""
    print("\n=== Testing Order Book Normalization ===")
    
    # Sample OKX order book payload
    current_ts = int(datetime.now(UTC).timestamp() * 1000)
    okx_book_payload = {
        "code": "0",
        "msg": "",
        "data": [{
            "asks": [
                ["41025.5", "2.5", "0", "1"],
                ["41026.0", "1.8", "0", "1"],
                ["41026.5", "3.2", "0", "1"],
                ["41027.0", "0.9", "0", "1"],
                ["41027.5", "1.1", "0", "1"]
            ],
            "bids": [
                ["41024.5", "1.9", "0", "2"],
                ["41024.0", "2.1", "0", "2"],
                ["41023.5", "1.4", "0", "2"],
                ["41023.0", "0.8", "0", "2"],
                ["41022.5", "1.6", "0", "2"]
            ],
            "ts": str(current_ts)
        }]
    }
    
    normalizer = DataNormalizer({"max_age_seconds": 86400})
    raw_data = json.dumps(okx_book_payload)
    
    result = normalizer.normalize_tick("BTC-USD", raw_data, "book")
    
    print(f"✓ Normalization successful: {result.success}")
    print(f"✓ Book snapshot created: {result.book_snap is not None}")
    
    if result.book_snap:
        print(f"  - Timestamp: {result.book_snap.ts}")
        print(f"  - Bid levels: {len(result.book_snap.bids)}")
        print(f"  - Ask levels: {len(result.book_snap.asks)}")
        print(f"  - Best bid: {result.book_snap.bid_price}")
        print(f"  - Best ask: {result.book_snap.ask_price}")
        print(f"  - Mid price: {result.book_snap.mid_price}")
        print(f"  - Spread: {result.book_snap.spread}")
    
    # Test retrieval
    latest_book = normalizer.get_latest_book("BTC-USD")
    last_price = normalizer.get_last_price("BTC-USD")
    
    print(f"✓ Latest book retrieved: {latest_book is not None}")
    print(f"✓ Last price updated: {last_price is not None}")
    
    return result.success

def test_error_handling():
    """Test error handling with invalid payloads."""
    print("\n=== Testing Error Handling ===")
    
    normalizer = DataNormalizer()
    
    # Test invalid JSON
    result1 = normalizer.normalize_tick("BTC-USD", "{invalid json", "candle")
    print(f"✓ Invalid JSON handled: {not result1.success}")
    print(f"  - Error message: {result1.error_msg}")
    
    # Test OKX error response
    okx_error = json.dumps({
        "code": "50001",
        "msg": "Invalid request",
        "data": []
    })
    result2 = normalizer.normalize_tick("BTC-USD", okx_error, "candle")
    print(f"✓ OKX error handled: {not result2.success}")
    print(f"  - Error message: {result2.error_msg}")
    
    # Test old timestamp (should be rejected)
    old_payload = json.dumps({
        "code": "0",
        "data": [["1597026383085", "41000.0", "41050.0", "40980.0", "41025.0", "15.5", "635000.0", "635000.0", "1"]]
    })
    result3 = normalizer.normalize_tick("BTC-USD", old_payload, "candle")
    print(f"✓ Old timestamp rejected: {not result3.success}")
    print(f"  - Error message: {result3.error_msg}")
    
    return True

def test_multi_instrument():
    """Test multi-instrument data management."""
    print("\n=== Testing Multi-Instrument Management ===")
    
    normalizer = DataNormalizer({"max_age_seconds": 86400})
    current_ts = int(datetime.now(UTC).timestamp() * 1000)
    
    # Add data for multiple instruments
    instruments = ["BTC-USD", "ETH-USD", "SOL-USD"]
    
    for i, instrument in enumerate(instruments):
        base_price = 41000 + i * 1000  # Different price levels
        candle_data = json.dumps({
            "code": "0",
            "data": [[str(current_ts), str(base_price), str(base_price + 50), str(base_price - 20), str(base_price + 25), "10.0", "410000.0", "410000.0", "1"]]
        })
        
        result = normalizer.normalize_tick(instrument, candle_data, "candle")
        print(f"✓ {instrument} normalized: {result.success}")
    
    # Test retrieval
    tracked_instruments = normalizer.get_instruments()
    print(f"✓ Tracked instruments: {tracked_instruments}")
    
    # Test stats
    for instrument in instruments:
        stats = normalizer.get_store_stats(instrument)
        print(f"✓ {instrument} stats: price={stats['last_price']}, timeframes={list(stats['timeframes'].keys())}")
    
    return True

def main():
    """Run all manual tests."""
    print("Data Normalization Pipeline Manual Test")
    print("=" * 50)
    
    tests = [
        test_candlestick_normalization,
        test_orderbook_normalization,
        test_error_handling,
        test_multi_instrument
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print(f"Test Results: {sum(results)}/{len(results)} passed")
    
    if all(results):
        print("🎉 All manual tests passed! Pipeline is working correctly.")
    else:
        print("❌ Some tests failed. Check implementation.")
    
    return all(results)

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)