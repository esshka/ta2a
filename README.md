# TA2 App - Breakout Trading Plan Evaluation Engine

A trading algorithm system that implements a breakout plan evaluation engine for cryptocurrency trading. The system processes real-time market data (candlesticks and order book snapshots) to evaluate breakout trading plans and emit entry signals.

## Features

- **Breakout Detection**: Identifies when price breaks through predefined levels with proper confirmation
- **Volume Confirmation**: Uses relative volume (RVOL) to validate breakouts  
- **Volatility-Aware Analysis**: Employs ATR (Average True Range) and NATR for dynamic thresholds
- **Order Book Analysis**: Monitors liquidity sweeps and imbalances
- **State Machine Management**: Tracks plan lifecycle (PENDING → BREAK_SEEN → BREAK_CONFIRMED → TRIGGERED)
- **Retest Capability**: Optional retest mode for polarity flip confirmations
- **Invalidation Rules**: Pre-trigger cancellation conditions (price limits, time expiry)
- **Signal Delivery System**: HTTP POST delivery for webhook integration
- **File-Based Delivery**: JSON/JSONL format output with rotation support
- **Signal Persistence**: SQLite-based audit trails with query capabilities
- **Configurable Delivery**: Multiple destinations with filtering and retry logic

## Architecture

The system follows functional programming principles with immutable state management:

- **Data Ingestion Layer**: Candlestick and order book processing
- **Evaluation Engine**: 1-second tick processing with multi-timeframe analysis
- **Signal Emission**: Complete signal emission system with multiple delivery methods, persistence, and validation
- **State Machine**: Explicit breakout plan lifecycle management
- **Configuration**: 3-tier precedence (global → instrument → plan overrides)

## Tech Stack

- **Python 3.9+**: Core language
- **Standard Library**: SQLite (persistence), urllib (HTTP delivery), json (serialization)
- **Dependencies**: Currently uses only standard library modules for maximum compatibility
- **Future Dependencies**: pandas, numpy, pydantic, talib (when data processing is implemented)
- **Testing**: pytest (when test framework is implemented)
- **Code Quality**: ruff, mypy (when build tools are configured)

## Installation

### Prerequisites

- Python 3.9 or higher
- No external dependencies (uses standard library only)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd ta2-app
```

2. Verify Python installation:
```bash
python3 --version
```

3. Test the implementation:
```bash
python3 -m py_compile ta2_app/config/signal_delivery.py
```

### Future Setup (when dependencies are added)

- Poetry for dependency management
- Pre-commit hooks for code quality
- TA-Lib for technical analysis indicators

## Development

### Current Status

The project is in active development with the following completed:

- ✅ **Signal Emission System**: Complete delivery infrastructure with HTTP, file, and stdout outputs
- ✅ **Signal Persistence**: SQLite-based audit trails and query capabilities  
- ✅ **Signal Validation**: JSON schema validation according to dev_proto.md
- ✅ **Configuration System**: Flexible delivery destination configuration
- ⏳ **Data Processing**: Candlestick and order book parsing (planned)
- ⏳ **Breakout Detection**: Core trading algorithm (planned)
- ⏳ **Testing Framework**: Comprehensive test suite (planned)

### Code Quality (Future)

When build tools are configured:
```bash
# Format code
poetry run ruff format

# Lint code  
poetry run ruff check

# Type checking
poetry run mypy ta2_app
```

### Project Structure

```
ta2_app/
├── config/         # Configuration management (✅ Extended with signal delivery)
├── data/           # Data ingestion and normalization (⏳ Planned)
├── delivery/       # Signal delivery mechanisms (✅ NEW: HTTP, file, stdout)
├── metrics/        # Technical indicator calculations (✅ Core framework)
├── models/         # Data models and contracts (✅ Core models)
├── persistence/    # Signal storage and audit trails (✅ NEW: SQLite-based)
├── signals/        # Signal emission and scoring (✅ Core framework)
├── state/          # State machine and plan runtime (✅ Core implementation)
├── utils/          # Utility functions (✅ Basic utilities)
├── validation/     # Signal format validation (✅ NEW: JSON schema)
└── engine.py       # Main evaluation engine coordinator (✅ Core framework)
```

## Configuration

### Signal Delivery Configuration

The signal emission system supports multiple delivery destinations:

```python
from ta2_app.config.signal_delivery import (
    SignalDeliveryConfig, 
    create_http_destination, 
    create_file_destination
)

# Configure HTTP webhook delivery
http_dest = create_http_destination(
    name="webhook",
    url="https://api.example.com/signals",
    headers={"Authorization": "Bearer token"}
)

# Configure file output
file_dest = create_file_destination(
    name="audit_log",
    output_path="./signals.jsonl",
    format="jsonl"
)

# Create delivery configuration
config = SignalDeliveryConfig(
    destinations=[http_dest, file_dest],
    parallel_delivery=True,
    failure_retry_attempts=3
)
```

### Trading Parameters

The system supports 3-tier parameter precedence:

1. **Global defaults**: Base configuration for all instruments
2. **Instrument-specific overrides**: Per-instrument parameter adjustments  
3. **Per-plan overrides**: Individual plan customization via `extra_data.breakout_params`

## Signal Output Format

The system emits signals in a standardized JSON format when breakout conditions are met. Each signal contains comprehensive market data and execution metadata for downstream trading systems.

### Signal Structure

```json
{
  "plan_id": "plan_123",
  "state": "triggered",
  "runtime": {
    "armed_at": "2025-01-17T04:09:00Z",
    "triggered_at": "2025-01-17T04:09:05Z",
    "invalid_reason": null
  },
  "last_price": 3306.2,
  "metrics": {
    "rvol": 1.87,
    "natr_pct": 1.2,
    "atr": 42.1,
    "pinbar": false
  },
  "strength_score": 83.5,
  "protocol_version": "breakout-v1"
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `plan_id` | String | Unique identifier for the trading plan |
| `state` | String | Signal state: `"triggered"`, `"invalid"`, or `"expired"` |
| `runtime.armed_at` | ISO8601 | Timestamp when breakout was confirmed |
| `runtime.triggered_at` | ISO8601 | Timestamp when signal was emitted |
| `runtime.invalid_reason` | String/null | Reason for invalidation (if applicable) |
| `last_price` | Float | Current market price at signal emission |
| `metrics.rvol` | Float | Relative volume ratio (current vs 20-bar average) |
| `metrics.natr_pct` | Float | Normalized Average True Range percentage |
| `metrics.atr` | Float | Average True Range value |
| `metrics.pinbar` | Boolean | Pinbar pattern detection flag |
| `strength_score` | Float | Composite quality score (0-100) for signal ranking |
| `protocol_version` | String | Signal format version for compatibility |

### Signal States

- **`triggered`**: Breakout plan successfully triggered and ready for execution
- **`invalid`**: Plan invalidated due to price limits or conditions not met
- **`expired`**: Plan expired due to time limits without triggering

### Strength Scoring

The strength score uses a weighted algorithm to rank signal quality:

```
Base Score: 30 points (triggered signals)
Volume Bonus: 0-25 points (scaled by RVOL multiple)
Volatility Bonus: 25 points (when NATR in 0.5-5% range)
Pattern Bonus: 10 points (pinbar retest confirmation)
Liquidity Bonus: 10 points (order book sweep detection)
```

### Signal Guarantees

#### Idempotency Mechanisms

- **Exactly-Once Emission**: Each state transition is emitted exactly once per plan/timestamp combination
- **Database-Level Deduplication**: SQLite unique constraint on `(plan_id, state, timestamp)` prevents duplicate storage
- **In-Memory Tracking**: Signal emitter maintains sent signal hashes to prevent duplicate delivery attempts
- **Cross-Session Persistence**: Idempotency guarantees maintained across process restarts via database state

#### Duplicate Prevention

- **Multi-Layer Protection**: 
  - Database unique constraints (primary protection)
  - In-memory signal tracking (performance optimization)
  - Timestamp-based uniqueness (allows plan reuse across time)
- **Collision Handling**: Database constraint violations are handled gracefully with no signal emission
- **Concurrent Safety**: Thread-safe operations ensure no race conditions in multi-threaded environments

#### Operational Guarantees

- **Metrics Snapshot**: All metrics captured at exact evaluation tick (no temporal drift)
- **Timestamp Precision**: Market timestamps used (not wall-clock time) for deterministic replay
- **State Isolation**: Each plan's idempotency tracking is completely isolated from others
- **Delivery Idempotency**: Multiple delivery attempts of the same signal are prevented

#### Failure Scenarios

- **Process Restart**: Signals already stored in database will not be re-emitted
- **Network Failures**: Delivery failures do not trigger duplicate signal creation
- **Concurrent Processing**: Multiple threads processing same tick will only emit one signal
- **Database Corruption**: System fails safely without emitting potentially duplicate signals

#### Monitoring and Validation

- **Signal Audit Trail**: All signals stored in `signal_store` with full metadata
- **Duplicate Detection**: Query `SELECT plan_id, state, timestamp, COUNT(*) FROM signals GROUP BY plan_id, state, timestamp HAVING COUNT(*) > 1` to detect any duplicates
- **Idempotency Verification**: Integration tests validate idempotency across all failure scenarios

#### Recovery Procedures

- **Duplicate Cleanup**: If duplicates are detected, use `SignalStore.delete_signal()` to remove extras
- **State Reset**: Use `StateManager.clear_plan_state()` to reset plan state if needed
- **Database Recovery**: SQLite database can be rebuilt from signal audit logs if corruption occurs

## Usage

### Quick Start

```python
from ta2_app.engine import BreakoutEvaluationEngine
from ta2_app.data.parsers import parse_candlestick_payload, parse_orderbook_payload

# Initialize the evaluation engine
engine = BreakoutEvaluationEngine()

# Add a breakout plan
plan = {
    "id": "plan_123",
    "instrument_id": "ETH-USDT-SWAP",
    "direction": "short",
    "entry_type": "breakout",
    "entry_price": 3308.0,
    "created_at": "2025-01-17T04:08:23.750427",
    "extra_data": {
        "entry_params": {"level": 3308},
        "invalidation_conditions": [
            {"type": "price_above", "level": 3360},
            {"type": "time_limit", "duration_seconds": 3600}
        ]
    }
}

engine.add_plan(plan)

# Process market data tick
candlestick_data = {
    "code": "0",
    "msg": "",
    "data": [
        ["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04", "12698348.04", "1"]
    ]
}

signals = engine.evaluate_tick(
    candlestick_payload=candlestick_data,
    instrument_id="ETH-USDT-SWAP"
)

# Process generated signals
for signal in signals:
    print(f"Signal: {signal['state']} for plan {signal['plan_id']}")
```

## Market Data Ingestion

### Supported Data Formats

The system processes real-time market data from cryptocurrency exchanges, primarily in OKX format:

#### Candlestick Data Format

```json
{
  "code": "0",
  "msg": "",
  "data": [
    ["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04", "12698348.04", "0"],
    ["1597026444085", "3.708", "3.799", "3.494", "3.72", "24912403", "67632347.24", "37632347.24", "1"]
  ]
}
```

**Array Format:** `[timestamp_ms, open, high, low, close, volume_base, volume_quote, volume_quote_alt, confirm_flag]`

- `timestamp_ms`: Unix timestamp in milliseconds
- `open/high/low/close`: Price values as strings
- `volume_base`: Base currency volume
- `volume_quote`: Quote currency volume
- `confirm_flag`: "1" for closed bar, "0" for developing bar

#### Order Book Data Format

```json
{
  "code": "0",
  "msg": "",
  "data": [{
    "asks": [["41006.8", "0.60038921", "0", "1"]],
    "bids": [["41006.3", "0.30178218", "0", "2"]],
    "ts": "1629966436396"
  }]
}
```

**Level Format:** `[price, size, _, _]` (trailing fields ignored)

### Data Ingestion Pipeline

```python
from ta2_app.data.parsers import parse_candlestick_payload, parse_orderbook_payload
from ta2_app.data.normalizer import DataNormalizer

# Initialize data normalizer
normalizer = DataNormalizer()

# Parse candlestick data
candlestick_payload = {
    "code": "0",
    "msg": "",
    "data": [
        ["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04", "12698348.04", "1"]
    ]
}

# Normalize candlestick data
candle_result = normalizer.normalize_candlesticks(candlestick_payload)
if candle_result.success:
    candle = candle_result.candle
    print(f"Processed candle: {candle.close} at {candle.ts}")

# Parse order book data
orderbook_payload = {
    "code": "0",
    "msg": "",
    "data": [{
        "asks": [["3310.5", "1.5"], ["3311.0", "2.0"]],
        "bids": [["3309.5", "1.2"], ["3309.0", "1.8"]],
        "ts": "1629966436396"
    }]
}

# Normalize order book data
book_result = normalizer.normalize_orderbook(orderbook_payload)
if book_result.success:
    book = book_result.book_snap
    print(f"Processed book: bid={book.bid_price}, ask={book.ask_price}")
```

### Error Handling and Validation

```python
from ta2_app.data.parsers import (
    parse_candlestick_payload, 
    ParseError, 
    PriceSpikeError,
    InvalidPriceError
)

# Enable spike filtering for wild price movements
try:
    candles = parse_candlestick_payload(
        payload=candlestick_data,
        enable_spike_filter=True,
        last_price=3308.0,
        atr=42.5,
        spike_multiplier=10.0
    )
except PriceSpikeError as e:
    print(f"Price spike detected: {e}")
except InvalidPriceError as e:
    print(f"Invalid price data: {e}")
except ParseError as e:
    print(f"Parsing failed: {e}")
```

## Market Data Preparation

### Data Quality Requirements

The system expects high-quality market data with the following characteristics:

1. **Timestamps**: Accurate market timestamps (not receive timestamps)
2. **Price Consistency**: OHLC prices must be logically consistent
3. **Volume Validation**: Non-negative volume values
4. **Sequence Integrity**: Proper bar sequence without gaps
5. **Confirmation Flags**: Accurate closed/developing bar indicators

### Data Validation Pipeline

```python
from ta2_app.data.validators import validate_atr_spike_filter

# Validate individual prices against ATR-based spike detection
last_price = 3308.0
atr = 42.5
spike_multiplier = 10.0

new_price = 3305.2
is_valid = validate_atr_spike_filter(
    price=new_price,
    last_price=last_price,
    atr=atr,
    spike_multiplier=spike_multiplier
)

if not is_valid:
    print(f"Price {new_price} rejected as spike")
```

### Data Store Management

```python
from ta2_app.data.models import InstrumentDataStore

# Create instrument-specific data store
data_store = InstrumentDataStore()

# Access rolling bars (automatically managed)
bars_1m = data_store.get_bars('1m')
bars_5m = data_store.get_bars('5m')

# Access volume history for RVOL calculation
vol_history = data_store.get_vol_history('1m')

# Update order book
data_store.update_book(book_snapshot)

# Update last price with timestamp
data_store.update_last_price(3305.2, timestamp)
```

## Configuration

### Configuration File Structure

The system uses a 3-tier configuration precedence:

1. **Global defaults** (`config/defaults.yaml`)
2. **Instrument-specific overrides** (`config/instruments.yaml`)
3. **Per-plan overrides** (`extra_data.breakout_params`)

### Setting Up Configuration

```bash
# Copy example configuration
cp config/instruments.yaml.example config/instruments.yaml

# Edit configuration files
vim config/defaults.yaml
vim config/instruments.yaml
```

### Global Configuration Example

```yaml
# config/defaults.yaml
breakout_params:
  penetration_pct: 0.05          # 0.05% minimum penetration
  penetration_natr_mult: 0.25    # ATR-based penetration multiplier
  min_rvol: 1.5                  # 1.5x volume confirmation
  confirm_close: true            # Require bar close confirmation
  confirm_time_ms: 750           # Hold time for time-based confirmation
  allow_retest_entry: false      # Use momentum vs retest entry
  retest_band_pct: 0.03          # Retest proximity band
  fakeout_close_invalidate: true # Invalidate on fakeout close
  ob_sweep_check: true           # Require order book sweep
  min_break_range_atr: 0.5       # Minimum break candle range

atr_params:
  period: 14                     # ATR calculation period
  multiplier: 2.0                # ATR multiplier

volume_params:
  rvol_period: 20                # RVOL lookback period
  min_volume_threshold: 1000     # Minimum volume for evaluation
```

### Instrument-Specific Configuration

```yaml
# config/instruments.yaml
instruments:
  ETH-USDT-SWAP:
    breakout_params:
      penetration_pct: 0.08      # Higher penetration for volatile pairs
      min_rvol: 2.0              # Stricter volume requirements
      
  BTC-USDT-SWAP:
    breakout_params:
      penetration_pct: 0.03      # Lower penetration for stable pairs
      min_rvol: 1.2              # More lenient volume requirements
```

### Per-Plan Configuration

```python
# Plan with custom breakout parameters
plan_with_overrides = {
    "id": "plan_456",
    "instrument_id": "BTC-USDT-SWAP",
    "direction": "long",
    "entry_type": "breakout",
    "entry_price": 45000.0,
    "extra_data": {
        "breakout_params": {
            "penetration_pct": 0.04,      # Override global default
            "min_rvol": 1.8,              # Override instrument default
            "allow_retest_entry": true     # Enable retest mode
        }
    }
}
```

### Configuration Validation

```python
from ta2_app.config.validation import ConfigValidator

# Validate configuration
config_data = {
    "penetration_pct": 0.05,
    "min_rvol": 1.5,
    "confirm_close": True
}

errors = ConfigValidator.validate_breakout_params(config_data)
if errors:
    for error in errors:
        print(f"Error in {error.field}: {error.message}")
```

## Complete Usage Examples

### Example 1: Basic Real-Time Processing

```python
from ta2_app.engine import BreakoutEvaluationEngine
import json

# Initialize engine
engine = BreakoutEvaluationEngine()

# Add multiple plans
plans = [
    {
        "id": "eth_short_plan",
        "instrument_id": "ETH-USDT-SWAP",
        "direction": "short",
        "entry_type": "breakout",
        "entry_price": 3308.0,
        "created_at": "2025-01-17T04:08:23.750427",
        "extra_data": {
            "invalidation_conditions": [
                {"type": "price_above", "level": 3360},
                {"type": "time_limit", "duration_seconds": 3600}
            ]
        }
    },
    {
        "id": "btc_long_plan",
        "instrument_id": "BTC-USDT-SWAP",
        "direction": "long",
        "entry_type": "breakout",
        "entry_price": 45000.0,
        "created_at": "2025-01-17T04:08:23.750427",
        "extra_data": {
            "breakout_params": {
                "allow_retest_entry": True,
                "retest_band_pct": 0.02
            }
        }
    }
]

# Add plans to engine
for plan in plans:
    engine.add_plan(plan)

# Process market data updates
def process_market_update(candlestick_data, orderbook_data, instrument_id):
    signals = engine.evaluate_tick(
        candlestick_payload=candlestick_data,
        orderbook_payload=orderbook_data,
        instrument_id=instrument_id
    )
    
    for signal in signals:
        print(f"🚨 Signal Generated:")
        print(f"  Plan: {signal['plan_id']}")
        print(f"  State: {signal['state']}")
        print(f"  Price: {signal['last_price']}")
        print(f"  Strength: {signal['strength_score']}")
        print(f"  RVOL: {signal['metrics']['rvol']}")
        print(f"  ATR: {signal['metrics']['atr']}")

# Simulate market data feed
eth_candlestick = {
    "code": "0",
    "msg": "",
    "data": [
        ["1597026383085", "3310", "3315", "3305", "3307", "8422410", "22698348.04", "12698348.04", "1"]
    ]
}

eth_orderbook = {
    "code": "0",
    "msg": "",
    "data": [{
        "asks": [["3308.5", "1.5"], ["3309.0", "2.0"]],
        "bids": [["3307.5", "1.2"], ["3307.0", "1.8"]],
        "ts": "1597026383085"
    }]
}

process_market_update(eth_candlestick, eth_orderbook, "ETH-USDT-SWAP")
```

### Example 2: Batch Processing with State Monitoring

```python
from ta2_app.engine import BreakoutEvaluationEngine
from datetime import datetime

# Initialize engine with custom config
engine = BreakoutEvaluationEngine(config_dir="./config")

# Add plan and monitor state transitions
plan_id = "demo_plan"
plan = {
    "id": plan_id,
    "instrument_id": "ETH-USDT-SWAP",
    "direction": "short",
    "entry_type": "breakout",
    "entry_price": 3308.0,
    "created_at": datetime.now().isoformat()
}

engine.add_plan(plan)

# Monitor plan state throughout evaluation
def monitor_plan_state(plan_id, engine):
    state = engine.get_plan_state(plan_id)
    if state:
        print(f"Plan {plan_id} state: {state['state']}")
        if state['break_seen']:
            print(f"  Break detected at: {state['break_ts']}")
        if state['break_confirmed']:
            print(f"  Break confirmed at: {state['armed_at']}")
        if state['signal_emitted']:
            print(f"  Signal emitted at: {state['triggered_at']}")

# Process sequence of market updates
market_updates = [
    # Initial position above entry
    {
        "candlestick": {
            "code": "0", "msg": "", 
            "data": [["1597026383085", "3312", "3315", "3310", "3312", "1000000", "3312000000", "3312000000", "1"]]
        }
    },
    # Break below entry level
    {
        "candlestick": {
            "code": "0", "msg": "", 
            "data": [["1597026444085", "3312", "3312", "3305", "3306", "2500000", "8265000000", "8265000000", "1"]]
        }
    },
    # Confirmation with volume
    {
        "candlestick": {
            "code": "0", "msg": "", 
            "data": [["1597026505085", "3306", "3307", "3300", "3302", "3800000", "12540000000", "12540000000", "1"]]
        }
    }
]

for i, update in enumerate(market_updates):
    print(f"\n=== Market Update {i+1} ===")
    
    signals = engine.evaluate_tick(
        candlestick_payload=update["candlestick"],
        instrument_id="ETH-USDT-SWAP"
    )
    
    monitor_plan_state(plan_id, engine)
    
    if signals:
        print(f"Generated {len(signals)} signals")
        for signal in signals:
            print(f"  Signal: {signal}")
```

### Example 3: Custom Signal Delivery

```python
from ta2_app.engine import BreakoutEvaluationEngine
from ta2_app.config.signal_delivery import (
    SignalDeliveryConfig, 
    create_http_destination, 
    create_file_destination
)

# Configure signal delivery
http_destination = create_http_destination(
    name="trading_webhook",
    url="https://api.trading-system.com/signals",
    headers={"Authorization": "Bearer your-token-here"}
)

file_destination = create_file_destination(
    name="audit_log",
    output_path="./signals.jsonl",
    format="jsonl"
)

delivery_config = SignalDeliveryConfig(
    destinations=[http_destination, file_destination],
    parallel_delivery=True,
    failure_retry_attempts=3
)

# Initialize engine with custom signal delivery
engine = BreakoutEvaluationEngine()
# Note: Signal delivery configuration is handled by the state manager

# Process with signal delivery
plan = {
    "id": "webhook_plan",
    "instrument_id": "ETH-USDT-SWAP",
    "direction": "short",
    "entry_type": "breakout",
    "entry_price": 3308.0,
    "created_at": "2025-01-17T04:08:23.750427"
}

engine.add_plan(plan)

# Market data that triggers breakout
trigger_data = {
    "code": "0",
    "msg": "",
    "data": [
        ["1597026383085", "3310", "3310", "3305", "3305", "5000000", "16525000000", "16525000000", "1"]
    ]
}

signals = engine.evaluate_tick(
    candlestick_payload=trigger_data,
    instrument_id="ETH-USDT-SWAP"
)

# Signals are automatically delivered to configured destinations
print(f"Generated {len(signals)} signals - delivered to webhook and file")
```

## Testing and Validation

### Running Tests

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/metrics/                    # Metrics calculation tests
pytest tests/state/                      # State machine tests  
pytest tests/integration/                # Integration tests
pytest tests/unit/                       # Unit tests

# Run tests with coverage
pytest --cov=ta2_app --cov-report=html

# Run tests with verbose output
pytest -v --tb=short

# Run specific test file
pytest tests/integration/test_full_pipeline.py -v
```

### Test Configuration

```python
# tests/conftest.py includes fixtures for testing
import pytest
from ta2_app.engine import BreakoutEvaluationEngine

@pytest.fixture
def engine():
    return BreakoutEvaluationEngine()

@pytest.fixture
def sample_plan():
    return {
        "id": "test_plan",
        "instrument_id": "ETH-USDT-SWAP",
        "direction": "short",
        "entry_type": "breakout",
        "entry_price": 3308.0,
        "created_at": "2025-01-17T04:08:23.750427"
    }
```

### Manual Testing

```python
# manual_test.py - Test individual components
from ta2_app.data.parsers import parse_candlestick_payload
from ta2_app.metrics.calculator import MetricsCalculator
from ta2_app.data.models import InstrumentDataStore

# Test data parsing
test_payload = {
    "code": "0",
    "msg": "",
    "data": [
        ["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04", "12698348.04", "1"]
    ]
}

candles = parse_candlestick_payload(test_payload)
print(f"Parsed {len(candles)} candles successfully")

# Test metrics calculation
data_store = InstrumentDataStore()
calculator = MetricsCalculator()

# Add test data
for candle in candles:
    bars = data_store.get_bars('1m')
    bars.append(candle)
    if candle.is_closed:
        vol_history = data_store.get_vol_history('1m')
        vol_history.append(candle.volume)

# Calculate metrics
if candles:
    metrics = calculator.calculate_metrics(candles[-1], data_store, "1m")
    print(f"ATR: {metrics.atr}")
    print(f"NATR: {metrics.natr_pct}%")
    print(f"RVOL: {metrics.rvol}")
```

### Validation Scripts

```bash
# Validate configuration
python scripts/validate_config.py

# Run development setup
python scripts/dev_setup.py

# Run benchmark tests
python scripts/benchmark.py
```

## Development

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run development setup script
python scripts/dev_setup.py

# Install pre-commit hooks
pre-commit install
```

### Code Quality

```bash
# Format code
ruff format ta2_app/

# Lint code
ruff check ta2_app/

# Type checking
mypy ta2_app/

# Run all quality checks
pre-commit run --all-files
```

### Adding New Features

1. **New Metrics**: Add to `ta2_app/metrics/` directory
2. **New Parsers**: Add to `ta2_app/data/parsers.py`
3. **New Validators**: Add to `ta2_app/data/validators.py`
4. **New Configuration**: Update `config/defaults.yaml`
5. **New Tests**: Add to appropriate `tests/` subdirectory

### Signal Emission System

```python
from ta2_app.state.runtime import SignalEmitter
from ta2_app.config.signal_delivery import get_default_delivery_config

# Initialize signal emitter with delivery configuration
emitter = SignalEmitter(delivery_config=get_default_delivery_config())

# Emit a signal (signals are automatically delivered and persisted)
signal = emitter.emit_signal(
    plan_id="plan_123",
    signal_data={"state": "triggered", "timestamp": "2025-01-01T00:00:00Z"},
    metrics=metrics_snapshot
)
```

## License

This project is licensed under the MIT License – see the LICENSE file for details.