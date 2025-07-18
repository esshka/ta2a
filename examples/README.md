# TA2 Examples

This directory contains practical examples demonstrating the capabilities of the TA2 Breakout Evaluation Engine. Each example is self-contained and can be run independently to understand different aspects of the system.

## Available Examples

### 1. **Basic Usage** (`basic_usage.py`)
**Run:** `python examples/basic_usage.py`

Demonstrates the fundamental usage of the TA2 engine:
- Engine initialization and configuration
- Adding breakout plans with different parameters
- Processing candlestick and order book data
- Monitoring plan states and signal generation
- Real-time market data simulation

**Key Features Shown:**
- Plan creation and management
- Market data processing pipeline
- Signal generation and interpretation
- State monitoring and debugging

### 2. **Data Ingestion Demo** (`data_ingestion_demo.py`)
**Run:** `python examples/data_ingestion_demo.py`

Shows comprehensive data ingestion capabilities:
- Parsing OKX candlestick and order book formats
- Data validation and error handling
- Price spike filtering for data quality
- Data normalization pipeline
- Metrics collection and monitoring

**Key Features Shown:**
- Robust data parsing with error handling
- ATR-based spike filtering
- Data quality validation
- Parsing metrics and performance monitoring
- InstrumentDataStore usage

### 3. **Configuration Demo** (`configuration_demo.py`)
**Run:** `python examples/configuration_demo.py`

Demonstrates the flexible configuration system:
- 3-tier configuration precedence
- Parameter validation and error handling
- Different configuration scenarios
- Engine integration with custom configs
- YAML and JSON configuration formats

**Key Features Shown:**
- Global, instrument, and plan-level configuration
- Configuration validation and error reporting
- Pre-built trading scenarios (conservative, aggressive, retest, scalping)
- Runtime configuration management

### 4. **State Machine Demo** (`state_machine_demo.py`)
**Run:** `python examples/state_machine_demo.py`

Shows the state machine behavior in detail:
- State transitions: PENDING → BREAK_SEEN → BREAK_CONFIRMED → TRIGGERED
- Invalidation conditions and plan expiry
- Retest mode behavior
- Fakeout detection and prevention
- Multiple plan management

**Key Features Shown:**
- Complete state transition lifecycle
- Price and time-based invalidation
- Retest mode for polarity flip confirmations
- Fakeout detection and recovery
- Simultaneous multi-plan evaluation

## Example Data Formats

All examples use realistic market data formats based on OKX exchange specifications:

### Candlestick Data
```json
{
  "code": "0",
  "msg": "",
  "data": [
    ["1597026383085", "3.721", "3.743", "3.677", "3.708", "8422410", "22698348.04", "12698348.04", "1"]
  ]
}
```

### Order Book Data
```json
{
  "code": "0",
  "msg": "",
  "data": [{
    "asks": [["3310.5", "1.5", "0", "1"]],
    "bids": [["3309.5", "1.2", "0", "1"]],
    "ts": "1597026383085"
  }]
}
```

## Running Examples

### Prerequisites
- Python 3.9+
- TA2 system installed and configured
- All dependencies from `requirements.txt`

### Basic Execution
```bash
# Run from the project root directory
python examples/basic_usage.py
python examples/data_ingestion_demo.py
python examples/configuration_demo.py
python examples/state_machine_demo.py
```

### With Custom Configuration
```bash
# Set custom config directory
export TA2_CONFIG_DIR=./custom_config
python examples/configuration_demo.py
```

### With Debug Output
```bash
# Enable debug logging
export TA2_LOG_LEVEL=DEBUG
python examples/basic_usage.py
```

## Example Output

Each example provides detailed output showing:
- ✅ **Success indicators** for completed operations
- 🚨 **Signal notifications** when breakouts are triggered
- 📊 **State summaries** showing plan lifecycle
- ⚠️ **Error handling** demonstrations
- 📈 **Performance metrics** and statistics

## Understanding the Output

### State Indicators
- **PENDING**: Plan is active but no breakout detected
- **BREAK_SEEN**: Price has penetrated the entry level
- **BREAK_CONFIRMED**: Breakout has been validated (volume, time, etc.)
- **TRIGGERED**: Signal has been emitted for trading
- **INVALID**: Plan has been invalidated due to conditions
- **EXPIRED**: Plan has expired due to time limits

### Signal Types
- **triggered**: Successful breakout signal ready for execution
- **invalid**: Plan invalidated due to price limits or conditions
- **expired**: Plan expired due to time limits without triggering

### Metrics Interpretation
- **RVOL**: Relative volume (current vs 20-bar average)
- **ATR**: Average True Range (volatility measure)
- **NATR**: Normalized ATR as percentage of price
- **Strength Score**: Composite quality score (0-100)

## Customization

Each example can be modified to test different scenarios:

1. **Change market data**: Modify price sequences to test different breakout patterns
2. **Adjust parameters**: Change penetration thresholds, volume requirements, etc.
3. **Add instruments**: Test with different cryptocurrency pairs
4. **Modify timeframes**: Experiment with different evaluation intervals
5. **Custom invalidation**: Add custom invalidation conditions

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure TA2 is properly installed and PYTHONPATH is set
2. **Configuration Errors**: Check that config files exist and are valid
3. **Market Data Errors**: Verify data format matches OKX specifications
4. **State Machine Issues**: Review invalidation conditions and parameter settings

### Debug Mode
```bash
# Enable comprehensive debug output
export TA2_LOG_LEVEL=DEBUG
export TA2_DEBUG_STATE_MACHINE=true
python examples/state_machine_demo.py
```

## Next Steps

After running these examples:

1. **Explore the codebase** to understand the implementation details
2. **Modify examples** to test your specific use cases
3. **Create custom scripts** based on these templates
4. **Integrate with real exchange data** feeds
5. **Build production trading systems** using the demonstrated patterns

For more information, see:
- `../README.md` - Main project documentation
- `../dev_proto.md` - Complete implementation specification
- `../config/` - Configuration examples and templates
- `../tests/` - Comprehensive test suite examples