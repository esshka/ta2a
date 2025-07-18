#!/usr/bin/env python3
"""
State Machine Demo - TA2 Breakout Evaluation Engine

This script demonstrates the state machine behavior of the TA2 system,
showing how breakout plans transition through different states:
- PENDING → BREAK_SEEN → BREAK_CONFIRMED → TRIGGERED
- Invalidation conditions and expiry
- Retest mode behavior
- State transitions and signal emission

Run: python examples/state_machine_demo.py
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from ta2_app.engine import BreakoutEvaluationEngine


class StateTransitionTracker:
    """Tracks state transitions for demonstration."""
    
    def __init__(self):
        self.transitions = []
        self.signals = []
    
    def track_state(self, plan_id: str, engine: BreakoutEvaluationEngine):
        """Track current state of a plan."""
        state = engine.get_plan_state(plan_id)
        if state:
            self.transitions.append({
                'timestamp': datetime.now(timezone.utc),
                'plan_id': plan_id,
                'state': state['state'],
                'substate': state['substate'],
                'break_seen': state['break_seen'],
                'break_confirmed': state['break_confirmed'],
                'signal_emitted': state['signal_emitted']
            })
    
    def track_signals(self, signals: List[Dict[str, Any]]):
        """Track generated signals."""
        for signal in signals:
            self.signals.append({
                'timestamp': datetime.now(timezone.utc),
                'signal': signal
            })
    
    def print_transition_summary(self):
        """Print summary of state transitions."""
        print("📊 STATE TRANSITION SUMMARY")
        print("=" * 50)
        
        for transition in self.transitions:
            print(f"  {transition['timestamp'].strftime('%H:%M:%S')} - "
                  f"Plan {transition['plan_id']}: {transition['state']}/{transition['substate']}")
            if transition['break_seen']:
                print(f"    Break seen: ✓")
            if transition['break_confirmed']:
                print(f"    Break confirmed: ✓")
            if transition['signal_emitted']:
                print(f"    Signal emitted: ✓")
        
        print(f"\nTotal signals generated: {len(self.signals)}")
        for signal_info in self.signals:
            signal = signal_info['signal']
            print(f"  {signal_info['timestamp'].strftime('%H:%M:%S')} - "
                  f"Signal: {signal.get('state')} for plan {signal.get('plan_id')}")


def create_market_data(timestamp_ms: int, price: float, volume: float = 1000000,
                      is_closed: bool = True) -> Dict[str, Any]:
    """Create market data for a specific price."""
    # Simple OHLC around the price
    open_price = price
    high = price + 2.0
    low = price - 2.0
    close = price
    
    return {
        "candlestick": {
            "code": "0",
            "msg": "",
            "data": [
                [str(timestamp_ms), str(open_price), str(high), str(low), str(close),
                 str(volume), str(volume * close), str(volume * close), "1" if is_closed else "0"]
            ]
        },
        "orderbook": {
            "code": "0",
            "msg": "",
            "data": [{
                "asks": [[str(price + 1), "1.0", "0", "1"]],
                "bids": [[str(price - 1), "1.0", "0", "1"]],
                "ts": str(timestamp_ms)
            }]
        }
    }


def demonstrate_basic_state_transitions():
    """Demonstrate basic state transitions for a short breakout."""
    print("🔄 BASIC STATE TRANSITIONS (Short Breakout)")
    print("=" * 50)
    
    # Initialize engine and tracker
    engine = BreakoutEvaluationEngine()
    tracker = StateTransitionTracker()
    
    # Create a short breakout plan
    plan = {
        "id": "short_demo",
        "instrument_id": "ETH-USDT-SWAP",
        "direction": "short",
        "entry_type": "breakout",
        "entry_price": 3308.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "extra_data": {
            "breakout_params": {
                "penetration_pct": 0.05,
                "min_rvol": 1.2,
                "confirm_close": True
            }
        }
    }
    
    engine.add_plan(plan)
    print(f"Added short breakout plan at ${plan['entry_price']}")
    
    # Market data sequence
    base_timestamp = int(time.time() * 1000)
    scenarios = [
        {
            "description": "Initial state - price above entry",
            "price": 3315.0,
            "volume": 1000000
        },
        {
            "description": "Price approaches entry level",
            "price": 3310.0,
            "volume": 1200000
        },
        {
            "description": "Price touches entry but insufficient penetration",
            "price": 3307.0,
            "volume": 1100000
        },
        {
            "description": "Break below entry with sufficient penetration",
            "price": 3305.0,
            "volume": 1800000
        },
        {
            "description": "Confirmation with continued selling pressure",
            "price": 3302.0,
            "volume": 2200000
        }
    ]
    
    # Process each scenario
    for i, scenario in enumerate(scenarios):
        print(f"\n{i+1}. {scenario['description']} (${scenario['price']})")
        
        # Create market data
        market_data = create_market_data(
            base_timestamp + i * 60000,
            scenario['price'],
            scenario['volume']
        )
        
        # Process the update
        signals = engine.evaluate_tick(
            candlestick_payload=market_data["candlestick"],
            orderbook_payload=market_data["orderbook"],
            instrument_id="ETH-USDT-SWAP"
        )
        
        # Track state and signals
        tracker.track_state("short_demo", engine)
        tracker.track_signals(signals)
        
        # Print current state
        state = engine.get_plan_state("short_demo")
        if state:
            print(f"   State: {state['state']}/{state['substate']}")
            print(f"   Break seen: {state['break_seen']}")
            print(f"   Break confirmed: {state['break_confirmed']}")
            print(f"   Signal emitted: {state['signal_emitted']}")
        
        # Print any signals
        if signals:
            for signal in signals:
                print(f"   🚨 SIGNAL: {signal['state']} - Strength: {signal.get('strength_score', 'N/A')}")
    
    print("\n" + "="*50)
    tracker.print_transition_summary()
    print()


def demonstrate_invalidation_conditions():
    """Demonstrate plan invalidation conditions."""
    print("❌ INVALIDATION CONDITIONS")
    print("=" * 50)
    
    engine = BreakoutEvaluationEngine()
    tracker = StateTransitionTracker()
    
    # Create plan with invalidation conditions
    plan = {
        "id": "invalidation_demo",
        "instrument_id": "BTC-USDT-SWAP",
        "direction": "long",
        "entry_type": "breakout",
        "entry_price": 45000.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "extra_data": {
            "invalidation_conditions": [
                {
                    "type": "price_below",
                    "level": 44500.0,
                    "description": "Invalidate if price drops below 44500"
                },
                {
                    "type": "time_limit",
                    "duration_seconds": 300,  # 5 minutes
                    "description": "Invalidate after 5 minutes"
                }
            ]
        }
    }
    
    engine.add_plan(plan)
    print(f"Added long breakout plan at ${plan['entry_price']}")
    print(f"Invalidation conditions:")
    for condition in plan['extra_data']['invalidation_conditions']:
        print(f"  - {condition['description']}")
    
    # Test price invalidation
    print("\n1. Testing price invalidation:")
    base_timestamp = int(time.time() * 1000)
    
    # Price drops to invalidation level
    invalidation_data = create_market_data(base_timestamp, 44400.0, 1500000)
    
    signals = engine.evaluate_tick(
        candlestick_payload=invalidation_data["candlestick"],
        orderbook_payload=invalidation_data["orderbook"],
        instrument_id="BTC-USDT-SWAP"
    )
    
    tracker.track_state("invalidation_demo", engine)
    tracker.track_signals(signals)
    
    state = engine.get_plan_state("invalidation_demo")
    if state:
        print(f"   Price at ${44400.0}")
        print(f"   State: {state['state']}")
        print(f"   Invalid reason: {state.get('invalid_reason', 'N/A')}")
    
    if signals:
        for signal in signals:
            print(f"   🚨 SIGNAL: {signal['state']} - Reason: {signal.get('invalid_reason', 'N/A')}")
    
    print("\n" + "="*50)
    tracker.print_transition_summary()
    print()


def demonstrate_retest_mode():
    """Demonstrate retest mode behavior."""
    print("🔄 RETEST MODE BEHAVIOR")
    print("=" * 50)
    
    engine = BreakoutEvaluationEngine()
    tracker = StateTransitionTracker()
    
    # Create plan with retest mode enabled
    plan = {
        "id": "retest_demo",
        "instrument_id": "ETH-USDT-SWAP",
        "direction": "long",
        "entry_type": "breakout",
        "entry_price": 3320.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "extra_data": {
            "breakout_params": {
                "allow_retest_entry": True,
                "retest_band_pct": 0.03,
                "penetration_pct": 0.05,
                "min_rvol": 1.5
            }
        }
    }
    
    engine.add_plan(plan)
    print(f"Added long breakout plan at ${plan['entry_price']} with retest mode")
    print(f"Retest band: {plan['extra_data']['breakout_params']['retest_band_pct']}%")
    
    # Market data sequence for retest scenario
    base_timestamp = int(time.time() * 1000)
    scenarios = [
        {
            "description": "Initial price below entry",
            "price": 3315.0,
            "volume": 1000000
        },
        {
            "description": "Break above entry level",
            "price": 3325.0,
            "volume": 2000000
        },
        {
            "description": "Confirmation of breakout",
            "price": 3328.0,
            "volume": 2500000
        },
        {
            "description": "Price pulls back toward entry (retest zone)",
            "price": 3322.0,
            "volume": 1200000
        },
        {
            "description": "Price touches retest zone",
            "price": 3319.0,
            "volume": 1800000
        },
        {
            "description": "Rejection from retest zone (trigger)",
            "price": 3325.0,
            "volume": 2200000
        }
    ]
    
    # Process each scenario
    for i, scenario in enumerate(scenarios):
        print(f"\n{i+1}. {scenario['description']} (${scenario['price']})")
        
        # Create market data
        market_data = create_market_data(
            base_timestamp + i * 60000,
            scenario['price'],
            scenario['volume']
        )
        
        # Process the update
        signals = engine.evaluate_tick(
            candlestick_payload=market_data["candlestick"],
            orderbook_payload=market_data["orderbook"],
            instrument_id="ETH-USDT-SWAP"
        )
        
        # Track state and signals
        tracker.track_state("retest_demo", engine)
        tracker.track_signals(signals)
        
        # Print current state
        state = engine.get_plan_state("retest_demo")
        if state:
            print(f"   State: {state['state']}/{state['substate']}")
            print(f"   Break seen: {state['break_seen']}")
            print(f"   Break confirmed: {state['break_confirmed']}")
            if state['armed_at']:
                print(f"   Armed at: {state['armed_at']}")
        
        # Print any signals
        if signals:
            for signal in signals:
                print(f"   🚨 SIGNAL: {signal['state']} - Strength: {signal.get('strength_score', 'N/A')}")
    
    print("\n" + "="*50)
    tracker.print_transition_summary()
    print()


def demonstrate_fakeout_detection():
    """Demonstrate fakeout detection and invalidation."""
    print("🎭 FAKEOUT DETECTION")
    print("=" * 50)
    
    engine = BreakoutEvaluationEngine()
    tracker = StateTransitionTracker()
    
    # Create plan with fakeout detection enabled
    plan = {
        "id": "fakeout_demo",
        "instrument_id": "ADA-USDT-SWAP",
        "direction": "short",
        "entry_type": "breakout",
        "entry_price": 0.85,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "extra_data": {
            "breakout_params": {
                "penetration_pct": 0.05,
                "min_rvol": 1.5,
                "fakeout_close_invalidate": True,
                "confirm_close": True
            }
        }
    }
    
    engine.add_plan(plan)
    print(f"Added short breakout plan at ${plan['entry_price']} with fakeout detection")
    
    # Market data sequence for fakeout scenario
    base_timestamp = int(time.time() * 1000)
    scenarios = [
        {
            "description": "Initial price above entry",
            "price": 0.87,
            "volume": 500000
        },
        {
            "description": "Break below entry level",
            "price": 0.845,
            "volume": 1200000
        },
        {
            "description": "Continued selling (break seen)",
            "price": 0.842,
            "volume": 1800000
        },
        {
            "description": "Price recovers back above entry (fakeout)",
            "price": 0.855,
            "volume": 2000000
        }
    ]
    
    # Process each scenario
    for i, scenario in enumerate(scenarios):
        print(f"\n{i+1}. {scenario['description']} (${scenario['price']})")
        
        # Create market data
        market_data = create_market_data(
            base_timestamp + i * 60000,
            scenario['price'],
            scenario['volume']
        )
        
        # Process the update
        signals = engine.evaluate_tick(
            candlestick_payload=market_data["candlestick"],
            orderbook_payload=market_data["orderbook"],
            instrument_id="ADA-USDT-SWAP"
        )
        
        # Track state and signals
        tracker.track_state("fakeout_demo", engine)
        tracker.track_signals(signals)
        
        # Print current state
        state = engine.get_plan_state("fakeout_demo")
        if state:
            print(f"   State: {state['state']}/{state['substate']}")
            print(f"   Break seen: {state['break_seen']}")
            print(f"   Break confirmed: {state['break_confirmed']}")
            if state.get('invalid_reason'):
                print(f"   Invalid reason: {state['invalid_reason']}")
        
        # Print any signals
        if signals:
            for signal in signals:
                print(f"   🚨 SIGNAL: {signal['state']} - Reason: {signal.get('invalid_reason', 'N/A')}")
    
    print("\n" + "="*50)
    tracker.print_transition_summary()
    print()


def demonstrate_multiple_plans():
    """Demonstrate multiple plans with different states."""
    print("🎯 MULTIPLE PLANS DEMONSTRATION")
    print("=" * 50)
    
    engine = BreakoutEvaluationEngine()
    tracker = StateTransitionTracker()
    
    # Create multiple plans
    plans = [
        {
            "id": "btc_long",
            "instrument_id": "BTC-USDT-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 45000.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.03,
                    "min_rvol": 1.2
                }
            }
        },
        {
            "id": "eth_short",
            "instrument_id": "ETH-USDT-SWAP",
            "direction": "short",
            "entry_type": "breakout",
            "entry_price": 3308.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.05,
                    "min_rvol": 1.5,
                    "allow_retest_entry": True
                }
            }
        }
    ]
    
    # Add plans to engine
    for plan in plans:
        engine.add_plan(plan)
        print(f"Added {plan['direction']} plan for {plan['instrument_id']} at ${plan['entry_price']}")
    
    # Simulate market data for both instruments
    base_timestamp = int(time.time() * 1000)
    
    # BTC breaks up, ETH breaks down
    market_updates = [
        {
            "instrument": "BTC-USDT-SWAP",
            "price": 45050.0,
            "volume": 1800000,
            "description": "BTC breaks above 45000"
        },
        {
            "instrument": "ETH-USDT-SWAP",
            "price": 3305.0,
            "volume": 2200000,
            "description": "ETH breaks below 3308"
        },
        {
            "instrument": "BTC-USDT-SWAP",
            "price": 45080.0,
            "volume": 2000000,
            "description": "BTC continuation"
        },
        {
            "instrument": "ETH-USDT-SWAP",
            "price": 3315.0,
            "volume": 1500000,
            "description": "ETH retest pullback"
        }
    ]
    
    # Process each update
    for i, update in enumerate(market_updates):
        print(f"\n{i+1}. {update['description']} (${update['price']})")
        
        # Create market data
        market_data = create_market_data(
            base_timestamp + i * 60000,
            update['price'],
            update['volume']
        )
        
        # Process the update
        signals = engine.evaluate_tick(
            candlestick_payload=market_data["candlestick"],
            orderbook_payload=market_data["orderbook"],
            instrument_id=update["instrument"]
        )
        
        # Track states for both plans
        tracker.track_state("btc_long", engine)
        tracker.track_state("eth_short", engine)
        tracker.track_signals(signals)
        
        # Print states for both plans
        for plan_id in ["btc_long", "eth_short"]:
            state = engine.get_plan_state(plan_id)
            if state:
                print(f"   {plan_id}: {state['state']}/{state['substate']}")
        
        # Print any signals
        if signals:
            for signal in signals:
                print(f"   🚨 SIGNAL: {signal['plan_id']} - {signal['state']}")
    
    print("\n" + "="*50)
    tracker.print_transition_summary()
    print()


def main():
    """Main demonstration function."""
    print("🎭 TA2 STATE MACHINE DEMO")
    print("=" * 60)
    print("This demo shows the state machine behavior of the TA2 system.")
    print()
    
    # Run all demonstrations
    demonstrate_basic_state_transitions()
    demonstrate_invalidation_conditions()
    demonstrate_retest_mode()
    demonstrate_fakeout_detection()
    demonstrate_multiple_plans()
    
    print("✅ State machine demo completed!")
    print("   Key takeaways:")
    print("   - Clear state transitions: PENDING → BREAK_SEEN → BREAK_CONFIRMED → TRIGGERED")
    print("   - Robust invalidation conditions (price limits, time expiry)")
    print("   - Flexible retest mode for polarity flip confirmations")
    print("   - Fakeout detection prevents false signals")
    print("   - Multiple plans can be managed simultaneously")


if __name__ == "__main__":
    main()