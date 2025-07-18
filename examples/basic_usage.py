#!/usr/bin/env python3
"""
Basic Usage Example - TA2 Breakout Evaluation Engine

This script demonstrates the basic usage of the TA2 breakout evaluation engine
with simulated market data. It shows how to:
- Initialize the engine
- Add breakout plans
- Process candlestick and order book data
- Monitor plan states and signals

Run: python examples/basic_usage.py
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

from ta2_app.engine import BreakoutEvaluationEngine


def create_sample_plan(plan_id: str, instrument_id: str, direction: str, entry_price: float) -> Dict[str, Any]:
    """Create a sample breakout plan."""
    return {
        "id": plan_id,
        "instrument_id": instrument_id,
        "direction": direction,
        "entry_type": "breakout",
        "entry_price": entry_price,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "extra_data": {
            "entry_params": {"level": entry_price},
            "invalidation_conditions": [
                {
                    "type": "price_above" if direction == "short" else "price_below",
                    "level": entry_price * 1.02 if direction == "short" else entry_price * 0.98,
                    "description": f"Price invalidation level for {direction} breakout"
                },
                {
                    "type": "time_limit",
                    "duration_seconds": 3600,
                    "description": "Plan expires in 1 hour if not triggered"
                }
            ]
        }
    }


def create_candlestick_data(timestamp_ms: int, open_price: float, high: float, 
                           low: float, close: float, volume: float = 1000000,
                           is_closed: bool = True) -> Dict[str, Any]:
    """Create OKX-format candlestick data."""
    return {
        "code": "0",
        "msg": "",
        "data": [
            [
                str(timestamp_ms),
                str(open_price),
                str(high),
                str(low),
                str(close),
                str(volume),
                str(volume * close),  # quote volume
                str(volume * close),  # quote volume alt
                "1" if is_closed else "0"
            ]
        ]
    }


def create_orderbook_data(timestamp_ms: int, bid_price: float, ask_price: float,
                         bid_size: float = 1.0, ask_size: float = 1.0) -> Dict[str, Any]:
    """Create OKX-format order book data."""
    return {
        "code": "0",
        "msg": "",
        "data": [{
            "asks": [[str(ask_price), str(ask_size), "0", "1"]],
            "bids": [[str(bid_price), str(bid_size), "0", "1"]],
            "ts": str(timestamp_ms)
        }]
    }


def print_signal_details(signal: Dict[str, Any]) -> None:
    """Print detailed signal information."""
    print(f"🚨 SIGNAL GENERATED 🚨")
    print(f"  Plan ID: {signal.get('plan_id', 'N/A')}")
    print(f"  State: {signal.get('state', 'N/A')}")
    print(f"  Price: ${signal.get('last_price', 'N/A')}")
    print(f"  Strength Score: {signal.get('strength_score', 'N/A')}")
    
    metrics = signal.get('metrics', {})
    print(f"  Metrics:")
    print(f"    RVOL: {metrics.get('rvol', 'N/A')}")
    print(f"    ATR: {metrics.get('atr', 'N/A')}")
    print(f"    NATR: {metrics.get('natr_pct', 'N/A')}%")
    print(f"    Pinbar: {metrics.get('pinbar', 'N/A')}")
    
    runtime = signal.get('runtime', {})
    print(f"  Runtime:")
    print(f"    Armed at: {runtime.get('armed_at', 'N/A')}")
    print(f"    Triggered at: {runtime.get('triggered_at', 'N/A')}")
    print("-" * 50)


def print_plan_state(plan_id: str, engine: BreakoutEvaluationEngine) -> None:
    """Print current plan state."""
    state = engine.get_plan_state(plan_id)
    if state:
        print(f"📊 Plan {plan_id} State:")
        print(f"  State: {state['state']}")
        print(f"  Substate: {state['substate']}")
        print(f"  Break Seen: {state['break_seen']}")
        print(f"  Break Confirmed: {state['break_confirmed']}")
        print(f"  Signal Emitted: {state['signal_emitted']}")
        if state['break_ts']:
            print(f"  Break Time: {state['break_ts']}")
        if state['armed_at']:
            print(f"  Armed At: {state['armed_at']}")
        if state['triggered_at']:
            print(f"  Triggered At: {state['triggered_at']}")
        print()


def main():
    """Main demonstration function."""
    print("🚀 TA2 Breakout Evaluation Engine - Basic Usage Demo")
    print("=" * 60)
    
    # Initialize the engine
    print("1. Initializing the breakout evaluation engine...")
    engine = BreakoutEvaluationEngine()
    print(f"   Engine initialized successfully!")
    print()
    
    # Create sample plans
    print("2. Creating sample breakout plans...")
    plans = [
        create_sample_plan("eth_short", "ETH-USDT-SWAP", "short", 3308.0),
        create_sample_plan("btc_long", "BTC-USDT-SWAP", "long", 45000.0)
    ]
    
    # Add plans to engine
    for plan in plans:
        engine.add_plan(plan)
        print(f"   Added {plan['direction']} plan for {plan['instrument_id']} at ${plan['entry_price']}")
    print()
    
    # Show initial stats
    stats = engine.get_runtime_stats()
    print("3. Initial engine stats:")
    print(f"   Active plans: {stats['active_plans']}")
    print(f"   Tracked instruments: {stats['tracked_instruments']}")
    print()
    
    # Simulate market data sequence for ETH short breakout
    print("4. Simulating ETH market data for short breakout...")
    print("   Scenario: ETH breaking down from 3308.0 support level")
    print()
    
    base_timestamp = int(time.time() * 1000)
    
    # Market data sequence
    market_sequence = [
        {
            "description": "Initial position above entry level",
            "candlestick": create_candlestick_data(base_timestamp, 3312.0, 3315.0, 3310.0, 3312.0, 1500000),
            "orderbook": create_orderbook_data(base_timestamp, 3311.5, 3312.5)
        },
        {
            "description": "Price approaches entry level",
            "candlestick": create_candlestick_data(base_timestamp + 60000, 3312.0, 3312.0, 3308.0, 3309.0, 1800000),
            "orderbook": create_orderbook_data(base_timestamp + 60000, 3308.5, 3309.5)
        },
        {
            "description": "Break below entry level with volume",
            "candlestick": create_candlestick_data(base_timestamp + 120000, 3309.0, 3309.0, 3305.0, 3306.0, 2500000),
            "orderbook": create_orderbook_data(base_timestamp + 120000, 3305.5, 3306.5)
        },
        {
            "description": "Confirmation with continued selling",
            "candlestick": create_candlestick_data(base_timestamp + 180000, 3306.0, 3307.0, 3300.0, 3302.0, 3200000),
            "orderbook": create_orderbook_data(base_timestamp + 180000, 3301.5, 3302.5)
        }
    ]
    
    # Process each market update
    for i, update in enumerate(market_sequence, 1):
        print(f"   Update {i}: {update['description']}")
        
        # Process the market data
        signals = engine.evaluate_tick(
            candlestick_payload=update["candlestick"],
            orderbook_payload=update["orderbook"],
            instrument_id="ETH-USDT-SWAP"
        )
        
        # Show plan state
        print_plan_state("eth_short", engine)
        
        # Show any generated signals
        if signals:
            print(f"   Generated {len(signals)} signals:")
            for signal in signals:
                print_signal_details(signal)
        else:
            print("   No signals generated")
        
        print()
    
    # Simulate BTC long breakout
    print("5. Simulating BTC market data for long breakout...")
    print("   Scenario: BTC breaking above 45000.0 resistance level")
    print()
    
    btc_sequence = [
        {
            "description": "Initial position below entry level",
            "candlestick": create_candlestick_data(base_timestamp, 44800.0, 44950.0, 44750.0, 44900.0, 800000),
            "orderbook": create_orderbook_data(base_timestamp, 44895.0, 44905.0)
        },
        {
            "description": "Price approaches entry level",
            "candlestick": create_candlestick_data(base_timestamp + 60000, 44900.0, 44980.0, 44850.0, 44980.0, 1200000),
            "orderbook": create_orderbook_data(base_timestamp + 60000, 44995.0, 45005.0)
        },
        {
            "description": "Break above entry level with volume",
            "candlestick": create_candlestick_data(base_timestamp + 120000, 44980.0, 45050.0, 44980.0, 45020.0, 1800000),
            "orderbook": create_orderbook_data(base_timestamp + 120000, 45015.0, 45025.0)
        }
    ]
    
    # Process BTC market updates
    for i, update in enumerate(btc_sequence, 1):
        print(f"   Update {i}: {update['description']}")
        
        signals = engine.evaluate_tick(
            candlestick_payload=update["candlestick"],
            orderbook_payload=update["orderbook"],
            instrument_id="BTC-USDT-SWAP"
        )
        
        print_plan_state("btc_long", engine)
        
        if signals:
            print(f"   Generated {len(signals)} signals:")
            for signal in signals:
                print_signal_details(signal)
        else:
            print("   No signals generated")
        
        print()
    
    # Final stats
    final_stats = engine.get_runtime_stats()
    print("6. Final engine stats:")
    print(f"   Active plans: {final_stats['active_plans']}")
    print(f"   Tracked instruments: {final_stats['tracked_instruments']}")
    print(f"   State manager active plans: {final_stats['state_manager_active_plans']}")
    print()
    
    print("✅ Demo completed successfully!")
    print("   This example showed basic plan creation, market data processing,")
    print("   and signal generation for breakout scenarios.")


if __name__ == "__main__":
    main()