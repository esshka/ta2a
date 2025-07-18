"""
State machine data models for breakout plan lifecycle management.

This module defines immutable data structures for tracking breakout plan runtime
state, configuration parameters, and state transitions.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class PlanLifecycleState(str, Enum):
    """Plan lifecycle states matching existing system."""
    PENDING = "pending"
    ARMED = "armed"
    TRIGGERED = "triggered"
    INVALID = "invalid"
    EXPIRED = "expired"


class BreakoutSubState(str, Enum):
    """Internal breakout-specific substates."""
    NONE = "none"
    BREAK_SEEN = "break_seen"
    BREAK_CONFIRMED = "break_confirmed"
    RETEST_ARMED = "retest_armed"
    RETEST_TRIGGERED = "retest_triggered"


class InvalidationReason(str, Enum):
    """Reasons for plan invalidation."""
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    STOP_LOSS = "stop_loss"
    FAKEOUT_CLOSE = "fakeout_close"
    TIME_LIMIT = "time_limit"


@dataclass(frozen=True)
class BreakoutParameters:
    """Breakout-specific configuration parameters with defaults from dev_proto.md section 7."""

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
class PlanRuntimeState:
    """Runtime state for a single breakout plan instance."""

    # Core lifecycle state
    state: PlanLifecycleState
    substate: BreakoutSubState = BreakoutSubState.NONE

    # Key timestamps (market time)
    break_ts: Optional[datetime] = None              # When raw penetration first observed
    armed_at: Optional[datetime] = None              # When breakout confirmed
    triggered_at: Optional[datetime] = None          # When entry signal fired

    # Invalidation tracking
    invalid_reason: Optional[InvalidationReason] = None

    # Internal tracking flags
    break_seen: bool = False
    break_confirmed: bool = False
    signal_emitted: bool = False                     # Idempotency tracking

    def with_state(self, new_state: PlanLifecycleState,
                   substate: Optional[BreakoutSubState] = None,
                   timestamp: Optional[datetime] = None,
                   invalid_reason: Optional[InvalidationReason] = None) -> 'PlanRuntimeState':
        """Create new state with updated lifecycle state and timestamp."""
        kwargs = {
            'state': new_state,
            'substate': substate or self.substate,
            'break_ts': self.break_ts,
            'armed_at': self.armed_at,
            'triggered_at': self.triggered_at,
            'invalid_reason': invalid_reason,
            'break_seen': self.break_seen,
            'break_confirmed': self.break_confirmed,
            'signal_emitted': self.signal_emitted
        }

        # Update appropriate timestamp based on state
        if new_state == PlanLifecycleState.ARMED and timestamp:
            kwargs['armed_at'] = timestamp
        elif new_state == PlanLifecycleState.TRIGGERED and timestamp:
            kwargs['triggered_at'] = timestamp

        return PlanRuntimeState(**kwargs)

    def with_break_seen(self, timestamp: datetime) -> 'PlanRuntimeState':
        """Mark break as seen with timestamp."""
        return PlanRuntimeState(
            state=self.state,
            substate=BreakoutSubState.BREAK_SEEN,
            break_ts=timestamp,
            armed_at=self.armed_at,
            triggered_at=self.triggered_at,
            invalid_reason=self.invalid_reason,
            break_seen=True,
            break_confirmed=self.break_confirmed,
            signal_emitted=self.signal_emitted
        )

    def with_break_confirmed(self, timestamp: datetime) -> 'PlanRuntimeState':
        """Mark break as confirmed with timestamp."""
        return PlanRuntimeState(
            state=PlanLifecycleState.ARMED,
            substate=BreakoutSubState.BREAK_CONFIRMED,
            break_ts=self.break_ts,
            armed_at=timestamp,
            triggered_at=self.triggered_at,
            invalid_reason=self.invalid_reason,
            break_seen=self.break_seen,
            break_confirmed=True,
            signal_emitted=self.signal_emitted
        )

    def with_signal_emitted(self) -> 'PlanRuntimeState':
        """Mark signal as emitted for idempotency."""
        return PlanRuntimeState(
            state=self.state,
            substate=self.substate,
            break_ts=self.break_ts,
            armed_at=self.armed_at,
            triggered_at=self.triggered_at,
            invalid_reason=self.invalid_reason,
            break_seen=self.break_seen,
            break_confirmed=self.break_confirmed,
            signal_emitted=True
        )


@dataclass(frozen=True)
class StateTransition:
    """Represents a state machine transition result."""

    # New state information
    new_state: PlanLifecycleState
    new_substate: BreakoutSubState
    timestamp: datetime

    # Signal emission
    should_emit_signal: bool = False
    invalid_reason: Optional[InvalidationReason] = None

    # Context for signal
    signal_context: Optional[dict] = None


@dataclass(frozen=True)
class MarketContext:
    """Market data context for state machine evaluation."""

    # Current market state
    last_price: float
    timestamp: datetime

    # Metrics (from metrics pipeline)
    atr: Optional[float] = None
    natr_pct: Optional[float] = None
    rvol: Optional[float] = None

    # Candle structure
    last_closed_bar: Optional[object] = None  # Candle object
    bar_range: Optional[float] = None

    # Order book state
    curr_book: Optional[object] = None  # BookSnap object
    prev_book: Optional[object] = None  # BookSnap object

    # Derived flags
    pinbar_detected: bool = False
    ob_sweep_detected: bool = False
    ob_sweep_side: Optional[str] = None


@dataclass(frozen=True)
class InvalidationCondition:
    """Represents a pre-trigger invalidation condition from plan."""

    condition_type: str  # "price_above", "price_below", "time_limit"
    level: Optional[float] = None
    duration_seconds: Optional[int] = None

    def check(self, price: float, current_time: datetime, plan_created_at: datetime) -> bool:
        """Check if this invalidation condition is met."""
        if self.condition_type == "price_above":
            return price > self.level
        elif self.condition_type == "price_below":
            return price < self.level
        elif self.condition_type == "time_limit":
            elapsed = (current_time - plan_created_at).total_seconds()
            return elapsed > self.duration_seconds
        return False
