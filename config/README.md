# Configuration System

This directory contains the configuration files for the TA2 Breakout Evaluation Engine. The system uses a **3-tier parameter precedence system** that allows flexible configuration at different levels.

## Parameter Precedence System

The configuration system merges parameters from three sources in order of precedence:

1. **Global Defaults** (lowest priority) - Base settings for all instruments
2. **Instrument Overrides** (medium priority) - Instrument-specific adjustments
3. **Plan Overrides** (highest priority) - Per-plan parameter customization

### How It Works

When a breakout plan is evaluated, the system:

1. **Starts with global defaults** from `defaults.yaml`
2. **Applies instrument-specific overrides** from `instruments.yaml` for the plan's instrument
3. **Applies plan-specific overrides** from the plan's `extra_data.breakout_params` field

Higher priority settings completely override lower priority ones for the same parameter.

### Example

```yaml
# Global default (defaults.yaml)
breakout_params:
  penetration_pct: 0.05
  min_rvol: 1.5
  confirm_close: true

# Instrument override (instruments.yaml)
"BTC-USD-SWAP":
  breakout_params:
    penetration_pct: 0.08  # Overrides global default
    min_rvol: 2.0          # Overrides global default
    # confirm_close: true remains from global default
```

```json
// Plan override (in plan's extra_data.breakout_params)
{
  "penetration_pct": 0.10,  // Overrides instrument override
  "allow_retest_entry": true // Overrides global default
  // min_rvol: 2.0 remains from instrument override
  // confirm_close: true remains from global default
}
```

**Final merged configuration:**
- `penetration_pct`: 0.10 (from plan override)
- `min_rvol`: 2.0 (from instrument override)
- `confirm_close`: true (from global default)
- `allow_retest_entry`: true (from plan override)

## Configuration Files

### defaults.yaml
Contains global default parameters applied to all instruments. These are the baseline settings that define the system's default behavior.

**Key sections:**
- `breakout_params`: Core breakout detection parameters
- `atr_params`: ATR calculation settings
- `volume_params`: Volume analysis configuration
- `orderbook_params`: Order book analysis settings
- `time_params`: Time-based evaluation settings
- `scoring_params`: Signal scoring configuration

### instruments.yaml
Contains instrument-specific parameter overrides. Use this to customize behavior for specific trading instruments based on their unique characteristics.

**Structure:**
```yaml
instruments:
  "INSTRUMENT-ID":
    breakout_params:
      parameter_name: value
    atr_params:
      parameter_name: value
    # ... other sections
```

**Common instrument customizations:**
- **High volatility assets** (BTC, ETH): Higher penetration thresholds, longer confirmation times
- **Altcoins** (SOL, DOGE): Higher volume requirements, stricter validation
- **Stable pairs**: Lower thresholds, faster confirmation

### Plan-Level Overrides
Plans can include parameter overrides in their `extra_data.breakout_params` field:

```json
{
  "id": "plan-001",
  "instrument_id": "BTC-USD-SWAP",
  "entry_type": "breakout",
  "entry_price": 50000.0,
  "direction": "long",
  "extra_data": {
    "breakout_params": {
      "penetration_pct": 0.06,
      "min_rvol": 2.5,
      "allow_retest_entry": true
    }
  }
}
```

## Breakout Parameters Reference

### Core Parameters
- **`penetration_pct`** (float, 0-1): Minimum percentage move past entry level
- **`penetration_natr_mult`** (float, >0): ATR-based penetration multiplier
- **`min_rvol`** (float, ≥0): Minimum relative volume for confirmation
- **`confirm_close`** (boolean): Require bar close vs time-based confirmation
- **`confirm_time_ms`** (int, >0): Hold duration for time-based confirmation

### Retest Parameters
- **`allow_retest_entry`** (boolean): Enable retest mode vs momentum mode
- **`retest_band_pct`** (float, 0-1): Proximity band for retest entry

### Risk Management
- **`fakeout_close_invalidate`** (boolean): Invalidate on price return to range
- **`ob_sweep_check`** (boolean): Require order book sweep confirmation
- **`min_break_range_atr`** (float, ≥0): Minimum breakout candle range

## Parameter Validation

All parameters are validated when:
1. **Plans are added** to the engine
2. **Configurations are loaded** from YAML files

**Validation rules:**
- Type checking (boolean, float, int)
- Range validation (percentages: 0-1, positive values: >0)
- Required field validation

**Invalid parameters cause:**
- Plan rejection with detailed error messages
- Configuration load failures
- Clear logging of validation errors

## Best Practices

### 1. Start with Global Defaults
Set conservative, safe defaults in `defaults.yaml` that work across all instruments.

### 2. Instrument-Specific Tuning
Use `instruments.yaml` to adjust for instrument characteristics:
- Volatility differences
- Liquidity patterns
- Market structure

### 3. Plan-Level Customization
Use plan overrides sparingly for:
- Specific strategy variations
- Risk level adjustments
- Testing parameter sensitivity

### 4. Parameter Testing
Always test parameter changes:
- Validate with unit tests
- Backtest with historical data
- Monitor in paper trading

### 5. Documentation
Document parameter changes:
- Rationale for overrides
- Expected impact
- Testing results

## Troubleshooting

### Plan Rejection
If plans are rejected due to parameter validation:
1. Check the engine logs for detailed error messages
2. Verify parameter types and ranges
3. Test parameters with unit tests first

### Configuration Errors
If configuration loading fails:
1. Check YAML syntax with a validator
2. Verify all required sections exist
3. Check parameter names match the schema

### Unexpected Behavior
If plans behave unexpectedly:
1. Log the final merged configuration
2. Check precedence order
3. Verify parameter values are as expected

## Example Configurations

### Conservative Setup (Low Risk)
```yaml
breakout_params:
  penetration_pct: 0.10
  min_rvol: 3.0
  confirm_close: true
  fakeout_close_invalidate: true
  ob_sweep_check: true
```

### Aggressive Setup (High Frequency)
```yaml
breakout_params:
  penetration_pct: 0.03
  min_rvol: 1.2
  confirm_close: false
  confirm_time_ms: 500
  allow_retest_entry: true
```

### Retest Mode Setup
```yaml
breakout_params:
  allow_retest_entry: true
  retest_band_pct: 0.02
  confirm_close: true
  fakeout_close_invalidate: false
```