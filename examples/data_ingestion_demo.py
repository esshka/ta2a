#!/usr/bin/env python3
"""
Data Ingestion Demo - TA2 Breakout Evaluation Engine

This script demonstrates the data ingestion capabilities of the TA2 system,
showing how to:
- Parse different data formats (candlestick, order book)
- Handle parsing errors and validation
- Use spike filtering for data quality
- Work with the data normalization pipeline
- Access parsed data structures

Run: python examples/data_ingestion_demo.py
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

from ta2_app.data.parsers import (
    parse_candlestick_payload,
    parse_orderbook_payload,
    parse_json_payload,
    validate_okx_response,
    get_parsing_metrics,
    reset_parsing_metrics,
    ParseError,
    PriceSpikeError,
    InvalidPriceError,
    InvalidTimestampError,
    InvalidVolumeError,
    OHLCConsistencyError
)
from ta2_app.data.normalizer import DataNormalizer
from ta2_app.data.models import InstrumentDataStore
from ta2_app.data.validators import validate_atr_spike_filter


def demonstrate_candlestick_parsing():
    """Demonstrate candlestick data parsing."""
    print("🕯️ CANDLESTICK PARSING DEMO")
    print("=" * 50)
    
    # Valid candlestick data
    print("1. Parsing valid candlestick data:")
    valid_payload = {
        "code": "0",
        "msg": "",
        "data": [
            ["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04", "12698348.04", "1"],
            ["1597026444085", "3.708", "3.799", "3.494", "3.720", "24912403", "67632347.24", "37632347.24", "0"]
        ]
    }
    
    try:
        candles = parse_candlestick_payload(valid_payload)
        print(f"   Successfully parsed {len(candles)} candles")
        
        for i, candle in enumerate(candles):
            print(f"   Candle {i+1}:")
            print(f"     Timestamp: {candle.ts}")
            print(f"     OHLC: {candle.open}, {candle.high}, {candle.low}, {candle.close}")
            print(f"     Volume: {candle.volume}")
            print(f"     Closed: {candle.is_closed}")
            print()
    except ParseError as e:
        print(f"   Parse error: {e}")
    
    # Invalid price data
    print("2. Handling invalid price data:")
    invalid_price_payload = {
        "code": "0",
        "msg": "",
        "data": [
            ["1597026383085", "3.721", "3.743", "3.677", "-3.708", "8422410", "22698348.04", "12698348.04", "1"]
        ]
    }
    
    try:
        candles = parse_candlestick_payload(invalid_price_payload)
        print(f"   Parsed {len(candles)} candles (unexpected)")
    except InvalidPriceError as e:
        print(f"   ✓ Correctly caught invalid price: {e}")
    except ParseError as e:
        print(f"   Parse error: {e}")
    
    # OHLC consistency check
    print("3. OHLC consistency validation:")
    inconsistent_payload = {
        "code": "0",
        "msg": "",
        "data": [
            ["1597026383085", "3.721", "3.700", "3.750", "3.708", "8422410", "22698348.04", "12698348.04", "1"]
        ]
    }
    
    try:
        candles = parse_candlestick_payload(inconsistent_payload)
        print(f"   Parsed {len(candles)} candles (unexpected)")
    except OHLCConsistencyError as e:
        print(f"   ✓ Correctly caught OHLC inconsistency: {e}")
    except ParseError as e:
        print(f"   Parse error: {e}")
    
    print()


def demonstrate_spike_filtering():
    """Demonstrate price spike filtering."""
    print("⚡ PRICE SPIKE FILTERING DEMO")
    print("=" * 50)
    
    # Normal price movement
    print("1. Normal price movement (should pass):")
    normal_payload = {
        "code": "0",
        "msg": "",
        "data": [
            ["1597026383085", "3300.0", "3305.0", "3295.0", "3302.0", "1000000", "3302000000", "3302000000", "1"]
        ]
    }
    
    try:
        candles = parse_candlestick_payload(
            normal_payload,
            enable_spike_filter=True,
            last_price=3300.0,
            atr=25.0,
            spike_multiplier=10.0
        )
        print(f"   ✓ Normal price accepted: {candles[0].close}")
    except PriceSpikeError as e:
        print(f"   Spike detected: {e}")
    
    # Price spike
    print("2. Price spike detection (should reject):")
    spike_payload = {
        "code": "0",
        "msg": "",
        "data": [
            ["1597026383085", "3300.0", "3600.0", "3295.0", "3580.0", "1000000", "3580000000", "3580000000", "1"]
        ]
    }
    
    try:
        candles = parse_candlestick_payload(
            spike_payload,
            enable_spike_filter=True,
            last_price=3300.0,
            atr=25.0,
            spike_multiplier=10.0
        )
        print(f"   Spike not detected: {candles[0].close} (unexpected)")
    except PriceSpikeError as e:
        print(f"   ✓ Correctly rejected spike: {e}")
    
    # Manual spike validation
    print("3. Manual spike validation:")
    test_cases = [
        (3305.0, 3300.0, 25.0, 10.0, "Normal move"),
        (3550.0, 3300.0, 25.0, 10.0, "Spike detected"),
        (3200.0, 3300.0, 25.0, 10.0, "Normal move down"),
        (3000.0, 3300.0, 25.0, 10.0, "Spike down detected")
    ]
    
    for price, last_price, atr, multiplier, description in test_cases:
        is_valid = validate_atr_spike_filter(price, last_price, atr, multiplier)
        status = "✓ PASS" if is_valid else "✗ REJECT"
        print(f"   {status}: {description} - {price} vs {last_price} (ATR: {atr})")
    
    print()


def demonstrate_orderbook_parsing():
    """Demonstrate order book parsing."""
    print("📖 ORDER BOOK PARSING DEMO")
    print("=" * 50)
    
    # Valid order book
    print("1. Parsing valid order book:")
    valid_book = {
        "code": "0",
        "msg": "",
        "data": [{
            "asks": [
                ["3310.5", "1.5", "0", "1"],
                ["3311.0", "2.0", "0", "1"],
                ["3311.5", "0.8", "0", "1"]
            ],
            "bids": [
                ["3309.5", "1.2", "0", "1"],
                ["3309.0", "1.8", "0", "1"],
                ["3308.5", "2.2", "0", "1"]
            ],
            "ts": "1597026383085"
        }]
    }
    
    try:
        book_snap = parse_orderbook_payload(valid_book, max_levels=5)
        print(f"   Successfully parsed order book:")
        print(f"     Timestamp: {book_snap.ts}")
        print(f"     Best bid: {book_snap.bid_price} (size: {book_snap.bids[0].size})")
        print(f"     Best ask: {book_snap.ask_price} (size: {book_snap.asks[0].size})")
        print(f"     Spread: {book_snap.ask_price - book_snap.bid_price:.2f}")
        print(f"     Total bids: {len(book_snap.bids)}")
        print(f"     Total asks: {len(book_snap.asks)}")
    except ParseError as e:
        print(f"   Parse error: {e}")
    
    # Invalid spread (bid >= ask)
    print("2. Invalid spread detection:")
    invalid_spread = {
        "code": "0",
        "msg": "",
        "data": [{
            "asks": [["3309.0", "1.5", "0", "1"]],
            "bids": [["3310.0", "1.2", "0", "1"]],
            "ts": "1597026383085"
        }]
    }
    
    try:
        book_snap = parse_orderbook_payload(invalid_spread)
        print(f"   Parsed invalid spread (unexpected)")
    except ParseError as e:
        print(f"   ✓ Correctly caught invalid spread: {e}")
    
    print()


def demonstrate_data_normalization():
    """Demonstrate the data normalization pipeline."""
    print("🔄 DATA NORMALIZATION DEMO")
    print("=" * 50)
    
    normalizer = DataNormalizer()
    
    # Candlestick normalization
    print("1. Candlestick normalization:")
    candlestick_data = {
        "code": "0",
        "msg": "",
        "data": [
            ["1597026383085", "3308.0", "3315.0", "3305.0", "3312.0", "1500000", "4968000000", "4968000000", "1"]
        ]
    }
    
    result = normalizer.normalize_candlesticks(candlestick_data)
    if result.success:
        candle = result.candle
        print(f"   ✓ Normalized candlestick:")
        print(f"     Close: {candle.close}")
        print(f"     Volume: {candle.volume}")
        print(f"     Closed: {candle.is_closed}")
        print(f"     Last price updated: {result.last_price_updated}")
        if result.new_last_price:
            print(f"     New last price: {result.new_last_price}")
    else:
        print(f"   ✗ Normalization failed: {result.error_msg}")
    
    # Order book normalization
    print("2. Order book normalization:")
    orderbook_data = {
        "code": "0",
        "msg": "",
        "data": [{
            "asks": [["3313.0", "1.2"], ["3314.0", "0.8"]],
            "bids": [["3312.0", "1.5"], ["3311.0", "2.0"]],
            "ts": "1597026383085"
        }]
    }
    
    result = normalizer.normalize_orderbook(orderbook_data)
    if result.success:
        book = result.book_snap
        print(f"   ✓ Normalized order book:")
        print(f"     Mid price: {(book.bid_price + book.ask_price) / 2:.2f}")
        print(f"     Spread: {book.ask_price - book.bid_price:.2f}")
    else:
        print(f"   ✗ Normalization failed: {result.error_msg}")
    
    print()


def demonstrate_data_store():
    """Demonstrate data store usage."""
    print("🗄️ DATA STORE DEMO")
    print("=" * 50)
    
    # Create data store
    data_store = InstrumentDataStore()
    
    # Add some sample candles
    print("1. Adding sample candles to data store:")
    sample_candles = [
        {
            "ts": datetime.now(timezone.utc),
            "open": 3300.0,
            "high": 3305.0,
            "low": 3295.0,
            "close": 3302.0,
            "volume": 1000000,
            "is_closed": True
        },
        {
            "ts": datetime.now(timezone.utc),
            "open": 3302.0,
            "high": 3310.0,
            "low": 3298.0,
            "close": 3308.0,
            "volume": 1200000,
            "is_closed": True
        },
        {
            "ts": datetime.now(timezone.utc),
            "open": 3308.0,
            "high": 3315.0,
            "low": 3305.0,
            "close": 3312.0,
            "volume": 800000,
            "is_closed": False
        }
    ]
    
    # Access rolling bars
    bars_1m = data_store.get_bars('1m')
    vol_history = data_store.get_vol_history('1m')
    
    for i, candle_data in enumerate(sample_candles):
        from ta2_app.data.models import Candle
        candle = Candle(**candle_data)
        bars_1m.append(candle)
        
        if candle.is_closed:
            vol_history.append(candle.volume)
        
        print(f"   Added candle {i+1}: {candle.close} (vol: {candle.volume:,})")
    
    print(f"   Total bars in store: {len(bars_1m)}")
    print(f"   Volume history length: {len(vol_history)}")
    
    # Update last price
    print("2. Updating last price:")
    data_store.update_last_price(3315.0, datetime.now(timezone.utc))
    print(f"   Last price: {data_store.last_price}")
    print(f"   Last update: {data_store.last_update}")
    
    # Update order book
    print("3. Updating order book:")
    from ta2_app.data.models import BookSnap, BookLevel
    book_snap = BookSnap(
        ts=datetime.now(timezone.utc),
        bids=[BookLevel(price=3314.0, size=1.5), BookLevel(price=3313.0, size=2.0)],
        asks=[BookLevel(price=3316.0, size=1.2), BookLevel(price=3317.0, size=0.8)]
    )
    
    data_store.update_book(book_snap)
    print(f"   Current book bid: {data_store.curr_book.bid_price}")
    print(f"   Current book ask: {data_store.curr_book.ask_price}")
    
    print()


def demonstrate_parsing_metrics():
    """Demonstrate parsing metrics collection."""
    print("📊 PARSING METRICS DEMO")
    print("=" * 50)
    
    # Reset metrics
    reset_parsing_metrics()
    
    # Parse some data to generate metrics
    print("1. Parsing data to generate metrics:")
    test_payloads = [
        {
            "code": "0",
            "msg": "",
            "data": [["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04", "12698348.04", "1"]]
        },
        {
            "code": "0",
            "msg": "",
            "data": [["1597026444085", "3.708", "3.799", "3.494", "3.720", "24912403", "67632347.24", "37632347.24", "0"]]
        },
        # Invalid data that will fail
        {
            "code": "0",
            "msg": "",
            "data": [["invalid", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04", "12698348.04", "1"]]
        }
    ]
    
    for i, payload in enumerate(test_payloads):
        try:
            candles = parse_candlestick_payload(payload)
            print(f"   Payload {i+1}: Success ({len(candles)} candles)")
        except ParseError as e:
            print(f"   Payload {i+1}: Failed ({e})")
    
    # Show metrics
    print("2. Parsing metrics:")
    metrics = get_parsing_metrics()
    print(f"   Total parses: {metrics['total_parses']}")
    print(f"   Successful: {metrics['successful_parses']}")
    print(f"   Failed: {metrics['failed_parses']}")
    print(f"   Success rate: {metrics['success_rate']:.2%}")
    print(f"   Total candles: {metrics['total_candles_parsed']}")
    print(f"   Avg parse time: {metrics['avg_parse_time_ms']:.2f}ms")
    print(f"   Consecutive failures: {metrics['consecutive_failures']}")
    
    print()


def main():
    """Main demonstration function."""
    print("🔍 TA2 DATA INGESTION DEMO")
    print("=" * 60)
    print("This demo shows the data ingestion capabilities of the TA2 system.")
    print()
    
    # Run all demonstrations
    demonstrate_candlestick_parsing()
    demonstrate_spike_filtering()
    demonstrate_orderbook_parsing()
    demonstrate_data_normalization()
    demonstrate_data_store()
    demonstrate_parsing_metrics()
    
    print("✅ Data ingestion demo completed!")
    print("   Key takeaways:")
    print("   - Robust parsing with comprehensive error handling")
    print("   - Price spike filtering for data quality")
    print("   - Flexible data normalization pipeline")
    print("   - Efficient data storage and retrieval")
    print("   - Built-in metrics for monitoring")


if __name__ == "__main__":
    main()