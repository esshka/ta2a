#!/usr/bin/env python3
"""Performance benchmark script for TA2 App."""

import time
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ta2_app.engine import BreakoutEvaluationEngine


def generate_sample_data(count: int) -> List[Dict[str, Any]]:
    """Generate sample market data for benchmarking."""
    base_timestamp = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    
    data = []
    for i in range(count):
        data.append({
            "timestamp": base_timestamp + (i * 1000),  # 1 second intervals
            "candlestick": {
                "timestamp": base_timestamp + (i * 1000),
                "open": 100.0 + (i * 0.01),
                "high": 101.0 + (i * 0.01),
                "low": 99.0 + (i * 0.01),
                "close": 100.5 + (i * 0.01),
                "volume": 1000.0 + (i * 10),
            },
            "order_book": {
                "bids": [[100.0 + (i * 0.01), 100.0, 0, 0]],
                "asks": [[100.5 + (i * 0.01), 100.0, 0, 0]],
            }
        })
    
    return data


def benchmark_evaluation_engine(data_points: int = 1000) -> Dict[str, float]:
    """Benchmark the evaluation engine performance."""
    print(f"🏃 Benchmarking evaluation engine with {data_points} data points...")
    
    # Initialize engine
    engine = BreakoutEvaluationEngine()
    
    # Generate test data
    test_data = generate_sample_data(data_points)
    
    # Warm up
    for i in range(10):
        engine.evaluate_tick(test_data[i % len(test_data)])
    
    # Benchmark
    start_time = time.time()
    
    for data_point in test_data:
        engine.evaluate_tick(data_point)
    
    end_time = time.time()
    
    total_time = end_time - start_time
    avg_time_per_tick = total_time / data_points
    ticks_per_second = data_points / total_time
    
    return {
        "total_time": total_time,
        "avg_time_per_tick": avg_time_per_tick,
        "ticks_per_second": ticks_per_second,
        "data_points": data_points,
    }


def main():
    """Main benchmark function."""
    print("⚡ TA2 App Performance Benchmark")
    print("=" * 40)
    
    # Test different data sizes
    test_sizes = [100, 500, 1000, 5000]
    
    for size in test_sizes:
        try:
            results = benchmark_evaluation_engine(size)
            
            print(f"\n📊 Results for {size} data points:")
            print(f"   Total time: {results['total_time']:.3f}s")
            print(f"   Avg per tick: {results['avg_time_per_tick']*1000:.3f}ms")
            print(f"   Ticks/second: {results['ticks_per_second']:.1f}")
            
            # Check if we meet the 1-second requirement
            if results['avg_time_per_tick'] <= 1.0:
                print(f"   ✅ Meets 1-second tick requirement")
            else:
                print(f"   ❌ Exceeds 1-second tick requirement")
                
        except Exception as e:
            print(f"   ❌ Benchmark failed: {e}")
    
    print(f"\n🎯 Performance Requirements:")
    print(f"   • Target: Process each tick in < 1 second")
    print(f"   • Goal: Handle real-time market data streams")
    print(f"   • Note: Current implementation is placeholder")


if __name__ == "__main__":
    main()