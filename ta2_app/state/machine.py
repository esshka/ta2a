"""
Core breakout state machine logic.

This module implements the main evaluation function from dev_proto.md section 16,
handling state transitions and gating logic for breakout plan lifecycle.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from ..data.models import Candle
from ..logging.config import get_gating_logger, get_state_logger, log_state_transition
from .models import (
    BreakoutParameters,
    BreakoutSubState,
    InvalidationReason,
    MarketContext,
    PlanLifecycleState,
    PlanRuntimeState,
    StateTransition,
)

if TYPE_CHECKING:
    from ..models.metrics import MetricsSnapshot

state_logger = get_state_logger(__name__)
gating_logger = get_gating_logger(__name__)


def eval_breakout_tick(
    plan_rt: PlanRuntimeState,
    market: MarketContext,
    cfg: BreakoutParameters,
    plan_data: dict,
    metrics: Optional["MetricsSnapshot"]
) -> Optional[StateTransition]:
    """
    Core breakout evaluation function from dev_proto.md section 16.

    Args:
        plan_rt: Current runtime state for the plan
        market: Market data context
        cfg: Breakout configuration parameters
        plan_data: Plan object with entry_price, direction, created_at, etc.
        metrics: Calculated metrics snapshot

    Returns:
        StateTransition if state change needed, None otherwise
    """
    entry_price = plan_data.get('entry_price')
    direction = plan_data.get('direction')
    plan_id = plan_data.get('id')
    plan_data.get('created_at')

    if not all([entry_price, direction, plan_id]):
        return None

    is_short = (direction == 'short')
    price = market.last_price
    now = market.timestamp

    # 1) Pre-trigger invalidations
    invalidation = check_pre_invalidations(plan_data, price, now)
    if invalidation:
        log_state_transition(
            state_logger,
            plan_id=plan_id,
            from_state=plan_rt.state.value,
            to_state=PlanLifecycleState.INVALID.value,
            trigger="pre_invalidation",
            context={
                "invalidation_reason": invalidation.value,
                "current_price": price,
                "entry_price": entry_price,
                "direction": direction,
                "timestamp": now.isoformat()
            }
        )
        return StateTransition(
            new_state=PlanLifecycleState.INVALID,
            new_substate=BreakoutSubState.NONE,
            timestamp=now,
            should_emit_signal=True,
            invalid_reason=invalidation
        )

    # 2) Break seen detection
    if not plan_rt.break_seen:
        if detect_break_seen(price, entry_price, is_short, cfg, metrics):
            # Calculate penetration details for logging
            pen_dist_raw = cfg.penetration_pct * entry_price
            pen_dist_vol = 0.0
            if metrics and hasattr(metrics, 'natr_pct') and metrics.natr_pct is not None:
                pen_dist_vol = cfg.penetration_natr_mult * (metrics.natr_pct / 100.0) * entry_price
            pen_dist = max(pen_dist_raw, pen_dist_vol)
            actual_penetration = abs(price - entry_price)

            log_state_transition(
                state_logger,
                plan_id=plan_id,
                from_state=plan_rt.state.value,
                to_state=PlanLifecycleState.PENDING.value,
                trigger="break_seen",
                context={
                    "substate": BreakoutSubState.BREAK_SEEN.value,
                    "current_price": price,
                    "entry_price": entry_price,
                    "direction": direction,
                    "penetration_distance": pen_dist,
                    "actual_penetration": actual_penetration,
                    "penetration_pct": cfg.penetration_pct,
                    "natr_pct": metrics.natr_pct if metrics and hasattr(metrics, 'natr_pct') else None,
                    "timestamp": now.isoformat()
                }
            )

            return StateTransition(
                new_state=PlanLifecycleState.PENDING,
                new_substate=BreakoutSubState.BREAK_SEEN,
                timestamp=now,
                should_emit_signal=False
            )
        return None

    # 3) Break confirmation gates
    if plan_rt.break_seen and not plan_rt.break_confirmed:
        # Check for fakeout invalidation first
        if cfg.fakeout_close_invalidate and market.last_closed_bar:
            if check_fakeout_close(market.last_closed_bar, entry_price, is_short):
                log_state_transition(
                    state_logger,
                    plan_id=plan_id,
                    from_state=plan_rt.state.value,
                    to_state=PlanLifecycleState.INVALID.value,
                    trigger="fakeout_close",
                    context={
                        "invalidation_reason": InvalidationReason.FAKEOUT_CLOSE.value,
                        "close_price": market.last_closed_bar.close,
                        "entry_price": entry_price,
                        "direction": direction,
                        "timestamp": now.isoformat()
                    }
                )
                return StateTransition(
                    new_state=PlanLifecycleState.INVALID,
                    new_substate=BreakoutSubState.NONE,
                    timestamp=now,
                    should_emit_signal=True,
                    invalid_reason=InvalidationReason.FAKEOUT_CLOSE
                )

        # Check all confirmation gates
        if check_confirmation_gates(plan_rt, market, cfg, metrics, entry_price, is_short):
            # All gates passed - mark as confirmed
            strength_score = metrics.get_composite_score() if metrics and hasattr(metrics, 'get_composite_score') else 0.0

            if cfg.allow_retest_entry:
                # Retest mode - arm for retest
                log_state_transition(
                    state_logger,
                    plan_id=plan_id,
                    from_state=plan_rt.state.value,
                    to_state=PlanLifecycleState.ARMED.value,
                    trigger="break_confirmed",
                    context={
                        "substate": BreakoutSubState.RETEST_ARMED.value,
                        "entry_mode": "retest",
                        "strength_score": strength_score,
                        "current_price": price,
                        "entry_price": entry_price,
                        "direction": direction,
                        "allow_retest_entry": cfg.allow_retest_entry,
                        "timestamp": now.isoformat()
                    }
                )
                return StateTransition(
                    new_state=PlanLifecycleState.ARMED,
                    new_substate=BreakoutSubState.RETEST_ARMED,
                    timestamp=now,
                    should_emit_signal=False
                )
            else:
                # Momentum mode - trigger immediately
                log_state_transition(
                    state_logger,
                    plan_id=plan_id,
                    from_state=plan_rt.state.value,
                    to_state=PlanLifecycleState.TRIGGERED.value,
                    trigger="break_confirmed",
                    context={
                        "substate": BreakoutSubState.NONE.value,
                        "entry_mode": "momentum",
                        "strength_score": strength_score,
                        "current_price": price,
                        "entry_price": entry_price,
                        "direction": direction,
                        "signal_emitted": True,
                        "timestamp": now.isoformat()
                    }
                )
                return StateTransition(
                    new_state=PlanLifecycleState.TRIGGERED,
                    new_substate=BreakoutSubState.NONE,
                    timestamp=now,
                    should_emit_signal=True,
                    signal_context={
                        'entry_mode': 'momentum',
                        'strength_score': strength_score
                    }
                )
        return None

    # 4) Retest logic (if enabled and armed)
    if (plan_rt.state == PlanLifecycleState.ARMED and
        plan_rt.substate == BreakoutSubState.RETEST_ARMED):

        if check_retest_trigger(price, entry_price, is_short, cfg, metrics):
            strength_score = metrics.get_composite_score() if metrics and hasattr(metrics, 'get_composite_score') else 0.0
            retest_band = cfg.retest_band_pct * entry_price

            log_state_transition(
                state_logger,
                plan_id=plan_id,
                from_state=plan_rt.state.value,
                to_state=PlanLifecycleState.TRIGGERED.value,
                trigger="retest_trigger",
                context={
                    "substate": BreakoutSubState.RETEST_TRIGGERED.value,
                    "entry_mode": "retest",
                    "strength_score": strength_score,
                    "current_price": price,
                    "entry_price": entry_price,
                    "direction": direction,
                    "retest_band": retest_band,
                    "price_distance_from_entry": abs(price - entry_price),
                    "signal_emitted": True,
                    "timestamp": now.isoformat()
                }
            )
            return StateTransition(
                new_state=PlanLifecycleState.TRIGGERED,
                new_substate=BreakoutSubState.RETEST_TRIGGERED,
                timestamp=now,
                should_emit_signal=True,
                signal_context={
                    'entry_mode': 'retest',
                    'strength_score': strength_score
                }
            )

    return None


def check_pre_invalidations(
    plan_data: dict,
    price: float,
    current_time: datetime
) -> Optional[InvalidationReason]:
    """Check pre-trigger invalidation conditions."""

    # Time limit check
    created_at = plan_data.get('created_at')
    if created_at:
        extra_data = plan_data.get('extra_data', {})
        invalidation_conditions = extra_data.get('invalidation_conditions', [])

        for condition in invalidation_conditions:
            if isinstance(condition, dict):
                if condition.get('type') == 'time_limit':
                    duration = condition.get('duration_seconds', 0)
                    elapsed = (current_time - created_at).total_seconds()
                    if elapsed > duration:
                        return InvalidationReason.TIME_LIMIT

                elif condition.get('type') == 'price_above':
                    level = condition.get('level')
                    if level and price > level:
                        return InvalidationReason.PRICE_ABOVE

                elif condition.get('type') == 'price_below':
                    level = condition.get('level')
                    if level and price < level:
                        return InvalidationReason.PRICE_BELOW

    # Stop loss check (if set globally)
    stop_loss = plan_data.get('stop_loss')
    if stop_loss:
        direction = plan_data.get('direction', '')
        if direction == 'long' and price <= stop_loss:
            return InvalidationReason.STOP_LOSS
        elif direction == 'short' and price >= stop_loss:
            return InvalidationReason.STOP_LOSS

    return None


def detect_break_seen(
    price: float,
    entry_price: float,
    is_short: bool,
    cfg: BreakoutParameters,
    metrics: Optional["MetricsSnapshot"]
) -> bool:
    """Detect if raw price penetration has occurred."""

    # Calculate volatility-aware penetration distance
    pen_dist_raw = cfg.penetration_pct * entry_price
    pen_dist_vol = 0.0

    if metrics and hasattr(metrics, 'natr_pct') and metrics.natr_pct is not None:
        pen_dist_vol = cfg.penetration_natr_mult * (metrics.natr_pct / 100.0) * entry_price

    pen_dist = max(pen_dist_raw, pen_dist_vol)

    # Check penetration based on direction
    if is_short:
        return price <= entry_price - pen_dist
    else:
        return price >= entry_price + pen_dist


def check_confirmation_gates(
    plan_rt: PlanRuntimeState,
    market: MarketContext,
    cfg: BreakoutParameters,
    metrics: Optional["MetricsSnapshot"],
    entry_price: float,
    is_short: bool
) -> bool:
    """Check all confirmation gates are satisfied."""

    # 1. RVOL Gate
    if cfg.min_rvol > 0:
        rvol = market.rvol if market.rvol is not None else (metrics.rvol if metrics and hasattr(metrics, 'rvol') else None)
        if rvol is None or rvol < cfg.min_rvol:
            gating_logger.debug(
                "RVOL gate failed during confirmation",
                rvol=rvol,
                required=cfg.min_rvol,
                gate_name="rvol_confirmation"
            )
            return False

    # 2. Volatility Gate (break candle range)
    if cfg.min_break_range_atr > 0 and metrics and market.last_closed_bar:
        if (hasattr(metrics, 'atr') and metrics.atr is None) or market.bar_range is None:
            return False
        if hasattr(metrics, 'atr') and market.bar_range < cfg.min_break_range_atr * metrics.atr:
            return False

    # 3. Close/Hold Gate
    if cfg.confirm_close:
        # Require bar close beyond level
        if not market.last_closed_bar:
            return False
        if not bar_closed_beyond(market.last_closed_bar, entry_price, is_short):
            return False
    else:
        # Time-based confirmation - check hold duration
        if cfg.confirm_time_ms > 0:
            if not plan_rt.break_ts:
                return False
            hold_duration = (market.timestamp - plan_rt.break_ts).total_seconds() * 1000
            if hold_duration < cfg.confirm_time_ms:
                return False
        # Also verify price still beyond level
        if is_short and market.last_price > entry_price:
            return False
        if not is_short and market.last_price < entry_price:
            return False

    # 4. Order Book Sweep Gate (if enabled)
    if cfg.ob_sweep_check:
        # Prioritize metrics over market context for sweep detection
        sweep_detected = metrics.ob_sweep_detected if metrics and hasattr(metrics, 'ob_sweep_detected') else (market.ob_sweep_detected if hasattr(market, 'ob_sweep_detected') else False)
        if not sweep_detected:
            gating_logger.debug(
                "Order book sweep gate failed during confirmation",
                sweep_detected=False,
                gate_name="ob_sweep_confirmation"
            )
            return False
        # Verify sweep is on correct side
        expected_side = 'bid' if is_short else 'ask'
        sweep_side = metrics.ob_sweep_side if metrics and hasattr(metrics, 'ob_sweep_side') else (market.ob_sweep_side if hasattr(market, 'ob_sweep_side') else None)
        if sweep_side != expected_side:
            gating_logger.debug(
                "Order book sweep gate failed during confirmation",
                sweep_side=sweep_side,
                expected_side=expected_side,
                gate_name="ob_sweep_confirmation"
            )
            return False

    return True


def check_fakeout_close(candle: Candle, entry_price: float, is_short: bool) -> bool:
    """Check if candle closed back inside the range (fakeout)."""
    if not candle.is_closed:
        return False

    if is_short:
        # For short breakout, fakeout is close above entry price
        return candle.close > entry_price
    else:
        # For long breakout, fakeout is close below entry price
        return candle.close < entry_price


def bar_closed_beyond(candle: Candle, entry_price: float, is_short: bool) -> bool:
    """Check if bar closed beyond the entry level."""
    if not candle.is_closed:
        return False

    if is_short:
        return candle.close < entry_price
    else:
        return candle.close > entry_price


def check_retest_trigger(
    price: float,
    entry_price: float,
    is_short: bool,
    cfg: BreakoutParameters,
    metrics: Optional["MetricsSnapshot"]
) -> bool:
    """Check if retest conditions are satisfied."""

    # Calculate retest band
    band = cfg.retest_band_pct * entry_price

    # Check if price is within retest band
    in_retest_band = abs(price - entry_price) <= band

    if not in_retest_band:
        return False

    # Look for rejection signals with enhanced detection
    rejection_signals = 0

    # 1. Pinbar detection
    if metrics and hasattr(metrics, 'pinbar') and metrics.pinbar:
        expected_pinbar = 'bearish' if is_short else 'bullish'
        if metrics.pinbar == expected_pinbar:
            rejection_signals += 1

    # 2. Order book refill analysis
    if metrics and hasattr(metrics, 'ob_sweep_detected') and metrics.ob_sweep_detected:
        # If we previously swept and now we're back at level,
        # consider it a valid retest
        rejection_signals += 1

    # 3. Volume-based rejection (if volume is lower than initial break)
    if metrics and hasattr(metrics, 'rvol') and metrics.rvol:
        if metrics.rvol < 0.8:  # Lower volume suggests rejection
            rejection_signals += 1

    # 4. Enhanced price action analysis
    if metrics and hasattr(metrics, 'candle_structure'):
        candle_structure = getattr(metrics, 'candle_structure', None)
        if candle_structure:
            # Look for rejection candle patterns
            expected_rejection = 'bearish_rejection' if is_short else 'bullish_rejection'
            if candle_structure == expected_rejection:
                rejection_signals += 1

    # 5. Order book imbalance supporting retest
    if metrics:
        if is_short:
            # For short retest, look for ask-heavy imbalance
            if (hasattr(metrics, 'ob_imbalance_short') and
                metrics.ob_imbalance_short and metrics.ob_imbalance_short > 2.0):
                rejection_signals += 1
        else:
            # For long retest, look for bid-heavy imbalance
            if (hasattr(metrics, 'ob_imbalance_long') and
                metrics.ob_imbalance_long and metrics.ob_imbalance_long > 2.0):
                rejection_signals += 1

    # Require at least 2 rejection signals for higher confidence
    gating_logger.debug(
        "Retest evaluation completed",
        rejection_signals=rejection_signals,
        required_signals=2,
        passed=rejection_signals >= 2,
        gate_name="retest_trigger"
    )
    return rejection_signals >= 2


def calc_penetration_distance(
    entry_price: float,
    cfg: BreakoutParameters,
    natr_pct: Optional[float] = None
) -> float:
    """Calculate volatility-aware penetration distance."""
    pen_dist_raw = cfg.penetration_pct * entry_price
    pen_dist_vol = 0.0

    if natr_pct is not None:
        pen_dist_vol = cfg.penetration_natr_mult * (natr_pct / 100.0) * entry_price

    return max(pen_dist_raw, pen_dist_vol)


def calc_retest_band(entry_price: float, cfg: BreakoutParameters) -> float:
    """Calculate retest band around entry level."""
    return cfg.retest_band_pct * entry_price
