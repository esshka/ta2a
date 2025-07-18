"""Default configuration parameters for the breakout evaluation system."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BreakoutParams:
    """Breakout detection parameters matching BreakoutParameters from state.models."""
    # Penetration thresholds
    penetration_pct: float = 0.05                    # Min % move past level
    penetration_natr_mult: float = 0.25              # ATR-based penetration multiplier

    # Volume confirmation
    min_rvol: float = 1.5                           # Volume confirmation threshold

    # Confirmation gates
    confirm_close: bool = True                       # Require bar close vs time-based
    confirm_time_ms: int = 750                       # Hold duration if confirm_close=false

    # Retest logic
    allow_retest_entry: bool = False                 # Momentum vs retest mode
    retest_band_pct: float = 0.03                    # Retest proximity band

    # Invalidation rules
    fakeout_close_invalidate: bool = True            # Invalidate on close back inside

    # Order book analysis
    ob_sweep_check: bool = True                      # Order book sweep requirement

    # Volatility filters
    min_break_range_atr: float = 0.5                 # Break candle min range


@dataclass(frozen=True)
class ATRParams:
    """ATR calculation parameters."""
    period: int = 14
    multiplier: float = 2.0


@dataclass(frozen=True)
class VolumeParams:
    """Volume analysis parameters."""
    rvol_period: int = 20
    min_volume_threshold: float = 1000.0


@dataclass(frozen=True)
class OrderBookParams:
    """Order book analysis parameters."""
    imbalance_threshold: float = 0.3
    sweep_detection: bool = True
    min_depth_levels: int = 3
    max_levels: int = 5
    depletion_threshold: float = 0.2


@dataclass(frozen=True)
class TimeParams:
    """Time-based parameters."""
    evaluation_timeframe: str = "1m"
    max_age_seconds: int = 60
    timezone: str = "UTC"


@dataclass(frozen=True)
class CandleParams:
    """Candle analysis parameters."""
    pinbar_body_threshold: float = 0.4
    pinbar_shadow_threshold: float = 0.66
    pinbar_tail_threshold: float = 0.1
    doji_threshold: float = 0.1


@dataclass(frozen=True)
class DataStoreParams:
    """Rolling data store parameters."""
    bars_window_size: int = 500        # Candlestick rolling window size
    volume_window_size: int = 20       # Volume history rolling window size
    atr_window_size: int = 14          # ATR calculation window size


@dataclass(frozen=True)
class SpikeFilterParams:
    """Spike filtering parameters."""
    enable: bool = True                # Enable ATR-based spike filtering
    atr_multiplier: float = 10.0       # ATR multiplier for spike detection
    fallback_pct: float = 0.5          # Fallback percentage filter when ATR unavailable


@dataclass(frozen=True)
class ScoringParams:
    """Signal scoring parameters."""
    base_strength: int = 50
    volume_weight: float = 0.3
    penetration_weight: float = 0.4
    volatility_weight: float = 0.3


@dataclass(frozen=True)
class DefaultConfig:
    """Complete default configuration."""
    breakout: BreakoutParams
    atr: ATRParams
    volume: VolumeParams
    orderbook: OrderBookParams
    time: TimeParams
    candle: CandleParams
    datastore: DataStoreParams
    spike_filter: SpikeFilterParams
    scoring: ScoringParams


def get_default_config() -> DefaultConfig:
    """Get the default configuration instance."""
    return DefaultConfig(
        breakout=BreakoutParams(),
        atr=ATRParams(),
        volume=VolumeParams(),
        orderbook=OrderBookParams(),
        time=TimeParams(),
        candle=CandleParams(),
        datastore=DataStoreParams(),
        spike_filter=SpikeFilterParams(),
        scoring=ScoringParams(),
    )
