"""
State transition handlers for breakout plan lifecycle.

This module provides clean orchestration of state changes with proper
validation and logging support.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import structlog

if TYPE_CHECKING:
    from ..models.metrics import MetricsSnapshot
from ..errors import (
    StateTransitionError,
    MissingDataError,
    MalformedDataError,
    PartialDataError,
    TemporalDataError,
    InsufficientDataError,
)
from ..logging.config import get_gating_logger, get_state_logger, log_gate_decision
from .machine import eval_breakout_tick
from .models import (
    BreakoutParameters,
    BreakoutSubState,
    InvalidationReason,
    PlanLifecycleState,
    PlanRuntimeState,
    StateTransition,
)

logger = structlog.get_logger(__name__)
gating_logger = get_gating_logger(__name__)
state_logger = get_state_logger(__name__)


class StateTransitionHandler:
    """Handles state transitions for breakout plans with logging and validation."""

    def __init__(self):
        self.logger = logger

    def _validate_state_transition(
        self,
        current_state: PlanRuntimeState,
        transition: StateTransition,
        plan_id: str
    ) -> None:
        """Validate that a state transition is valid."""
        # Validate current state
        if not current_state:
            raise StateTransitionError(
                "Current state is required for transition",
                current_state=None,
                attempted_transition=f"{transition.new_state.value}:{transition.new_substate.value}"
            )

        # Validate transition object
        if not transition:
            raise StateTransitionError(
                "Transition object is required",
                current_state=current_state.state.value,
                attempted_transition=None
            )

        # Validate timestamp
        if not transition.timestamp:
            raise TemporalDataError(
                "Transition timestamp is required",
                context={"plan_id": plan_id, "transition": str(transition)}
            )

        # Validate state consistency
        self._validate_state_consistency(current_state, transition, plan_id)

    def _validate_state_consistency(
        self,
        current_state: PlanRuntimeState,
        transition: StateTransition,
        plan_id: str
    ) -> None:
        """Validate state transition consistency rules."""
        current_lifecycle = current_state.state
        current_sub = current_state.substate
        new_lifecycle = transition.new_state
        new_sub = transition.new_substate

        # Check for invalid transitions
        invalid_transitions = [
            # Cannot go from triggered states back to earlier states
            (PlanLifecycleState.TRIGGERED, PlanLifecycleState.PENDING),
            (PlanLifecycleState.TRIGGERED, PlanLifecycleState.ARMED),
            # Cannot go from invalid state to any other state
            (PlanLifecycleState.INVALID, PlanLifecycleState.PENDING),
            (PlanLifecycleState.INVALID, PlanLifecycleState.ARMED),
            (PlanLifecycleState.INVALID, PlanLifecycleState.TRIGGERED),
        ]

        for invalid_from, invalid_to in invalid_transitions:
            if current_lifecycle == invalid_from and new_lifecycle == invalid_to:
                raise StateTransitionError(
                    f"Invalid state transition from {invalid_from.value} to {invalid_to.value}",
                    current_state=current_lifecycle.value,
                    attempted_transition=new_lifecycle.value
                )

        # Validate substate consistency
        if new_lifecycle == PlanLifecycleState.PENDING and new_sub not in [
            BreakoutSubState.NONE, BreakoutSubState.BREAK_SEEN
        ]:
            raise StateTransitionError(
                f"Invalid substate {new_sub.value} for PENDING state",
                current_state=f"{current_lifecycle.value}:{current_sub.value}",
                attempted_transition=f"{new_lifecycle.value}:{new_sub.value}"
            )

        if new_lifecycle == PlanLifecycleState.ARMED and new_sub not in [
            BreakoutSubState.BREAK_CONFIRMED, BreakoutSubState.RETEST_ARMED
        ]:
            raise StateTransitionError(
                f"Invalid substate {new_sub.value} for ARMED state",
                current_state=f"{current_lifecycle.value}:{current_sub.value}",
                attempted_transition=f"{new_lifecycle.value}:{new_sub.value}"
            )

    def _validate_context_data(
        self,
        market_context: dict[str, Any],
        plan_data: dict[str, Any],
        plan_id: str
    ) -> None:
        """Validate context data for state evaluation."""
        # Validate market context
        if not market_context:
            raise MissingDataError("Market context is required", data_type="market_context")

        required_market_fields = ['last_price', 'timestamp']
        for field in required_market_fields:
            if field not in market_context or market_context[field] is None:
                raise MissingDataError(
                    f"Market context missing required field: {field}",
                    data_type="market_context"
                )

        # Validate plan data
        if not plan_data:
            raise MissingDataError("Plan data is required", data_type="plan_data")

        required_plan_fields = ['id', 'entry_price', 'direction']
        for field in required_plan_fields:
            if field not in plan_data or plan_data[field] is None:
                raise MissingDataError(
                    f"Plan data missing required field: {field}",
                    data_type="plan_data"
                )

        # Validate price data
        last_price = market_context.get('last_price')
        entry_price = plan_data.get('entry_price')
        
        if not isinstance(last_price, (int, float)) or last_price <= 0:
            raise MalformedDataError(f"Invalid last_price: {last_price}")
        
        if not isinstance(entry_price, (int, float)) or entry_price <= 0:
            raise MalformedDataError(f"Invalid entry_price: {entry_price}")

        # Validate direction
        direction = plan_data.get('direction')
        if direction not in ['long', 'short']:
            raise MalformedDataError(f"Invalid direction: {direction}. Must be 'long' or 'short'")

    def _validate_metrics_data(
        self,
        metrics: Optional["MetricsSnapshot"],
        cfg: BreakoutParameters,
        plan_id: str
    ) -> None:
        """Validate metrics data for state evaluation."""
        # Check if metrics are required but missing
        if cfg.min_rvol > 0 and (not metrics or metrics.rvol is None):
            raise InsufficientDataError(
                "RVOL metrics required but not available",
                required_count=1,
                available_count=0
            )

        if cfg.min_break_range_atr > 0 and (not metrics or metrics.atr is None):
            raise InsufficientDataError(
                "ATR metrics required but not available",
                required_count=1,
                available_count=0
            )

        # Validate metrics values if present
        if metrics:
            if metrics.rvol is not None and (metrics.rvol < 0 or metrics.rvol > 1000):
                raise MalformedDataError(f"Invalid RVOL value: {metrics.rvol}")
            
            if metrics.atr is not None and (metrics.atr <= 0 or metrics.atr > 1e6):
                raise MalformedDataError(f"Invalid ATR value: {metrics.atr}")

            if metrics.natr_pct is not None and (metrics.natr_pct < 0 or metrics.natr_pct > 100):
                raise MalformedDataError(f"Invalid NATR percentage: {metrics.natr_pct}")

    def _validate_breakout_config(
        self,
        cfg: BreakoutParameters,
        plan_id: str
    ) -> None:
        """Validate breakout configuration parameters."""
        if not cfg:
            raise MissingDataError("Breakout configuration is required", data_type="breakout_config")

        # Validate threshold values
        if cfg.penetration_pct < 0 or cfg.penetration_pct > 100:
            raise MalformedDataError(f"Invalid penetration_pct: {cfg.penetration_pct}. Must be 0-100")

        if cfg.penetration_natr_mult < 0:
            raise MalformedDataError(f"Invalid penetration_natr_mult: {cfg.penetration_natr_mult}. Must be >= 0")

        if cfg.min_rvol < 0:
            raise MalformedDataError(f"Invalid min_rvol: {cfg.min_rvol}. Must be >= 0")

        if cfg.min_break_range_atr < 0:
            raise MalformedDataError(f"Invalid min_break_range_atr: {cfg.min_break_range_atr}. Must be >= 0")

        if cfg.confirm_time_ms < 0:
            raise MalformedDataError(f"Invalid confirm_time_ms: {cfg.confirm_time_ms}. Must be >= 0")

        if cfg.retest_band_pct < 0 or cfg.retest_band_pct > 100:
            raise MalformedDataError(f"Invalid retest_band_pct: {cfg.retest_band_pct}. Must be 0-100")

    def apply_transition(
        self,
        current_state: PlanRuntimeState,
        transition: StateTransition,
        plan_id: str
    ) -> PlanRuntimeState:
        """
        Apply a state transition to current runtime state.

        Args:
            current_state: Current plan runtime state
            transition: Transition to apply
            plan_id: Plan identifier for logging

        Returns:
            New runtime state after transition
        """
        try:
            # Validate the transition
            self._validate_state_transition(current_state, transition, plan_id)

            self.logger.info(
                "Applying state transition",
                plan_id=plan_id,
                current_state=current_state.state.value,
                current_substate=current_state.substate.value,
                new_state=transition.new_state.value,
                new_substate=transition.new_substate.value,
                timestamp=transition.timestamp,
                should_emit_signal=transition.should_emit_signal,
                invalid_reason=transition.invalid_reason.value if transition.invalid_reason else None
            )

            # Create new state based on transition
            new_state = current_state.with_state(
                new_state=transition.new_state,
                substate=transition.new_substate,
                timestamp=transition.timestamp,
                invalid_reason=transition.invalid_reason
            )

            # Handle specific transition logic
            if transition.new_state == PlanLifecycleState.PENDING and transition.new_substate == BreakoutSubState.BREAK_SEEN:
                new_state = new_state.with_break_seen(transition.timestamp)

            elif transition.new_state == PlanLifecycleState.ARMED and transition.new_substate == BreakoutSubState.BREAK_CONFIRMED:
                new_state = new_state.with_break_confirmed(transition.timestamp)

            elif transition.new_state == PlanLifecycleState.ARMED and transition.new_substate == BreakoutSubState.RETEST_ARMED:
                new_state = new_state.with_break_confirmed(transition.timestamp)

            # Mark signal emission if required
            if transition.should_emit_signal:
                new_state = new_state.with_signal_emitted()

            return new_state

        except (StateTransitionError, TemporalDataError) as e:
            # Log the error with context and re-raise
            self.logger.error(
                "State transition validation failed",
                plan_id=plan_id,
                current_state=current_state.state.value if current_state else None,
                current_substate=current_state.substate.value if current_state else None,
                attempted_transition=f"{transition.new_state.value}:{transition.new_substate.value}" if transition else None,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
        except Exception as e:
            # Wrap unexpected errors in StateTransitionError
            self.logger.error(
                "Unexpected error during state transition",
                plan_id=plan_id,
                current_state=current_state.state.value if current_state else None,
                error=str(e),
                error_type=type(e).__name__
            )
            raise StateTransitionError(
                f"Unexpected error during state transition: {e}",
                current_state=current_state.state.value if current_state else None,
                attempted_transition=f"{transition.new_state.value}:{transition.new_substate.value}" if transition else None
            )

    def evaluate_and_transition(
        self,
        current_state: PlanRuntimeState,
        market_context: dict[str, Any],
        cfg: BreakoutParameters,
        plan_data: dict[str, Any],
        metrics: Optional["MetricsSnapshot"]
    ) -> Optional[StateTransition]:
        """
        Evaluate breakout conditions and return transition if needed.

        Args:
            current_state: Current plan runtime state
            market_context: Market data context
            cfg: Breakout configuration parameters
            plan_data: Plan object data
            metrics: Calculated metrics snapshot

        Returns:
            StateTransition if state change needed, None otherwise
        """
        plan_id = plan_data.get('id', 'unknown')

        try:
            # Validate all input data
            self._validate_context_data(market_context, plan_data, plan_id)
            self._validate_breakout_config(cfg, plan_id)
            self._validate_metrics_data(metrics, cfg, plan_id)

            # Validate current state
            if not current_state:
                raise StateTransitionError(
                    "Current state is required for evaluation",
                    current_state=None,
                    attempted_transition="evaluation"
                )

            # Use the core evaluation logic
            transition = eval_breakout_tick(
                plan_rt=current_state,
                market=market_context,
                cfg=cfg,
                plan_data=plan_data,
                metrics=metrics
            )

            if transition:
                self.logger.debug(
                    "State transition required",
                    plan_id=plan_id,
                    transition_type=f"{current_state.state.value}->{transition.new_state.value}",
                    substate=transition.new_substate.value,
                    should_emit_signal=transition.should_emit_signal
                )

            return transition

        except (StateTransitionError, MissingDataError, MalformedDataError, InsufficientDataError) as e:
            # Log structured errors with full context
            self.logger.error(
                "Data validation error during breakout evaluation",
                plan_id=plan_id,
                error=str(e),
                error_type=type(e).__name__,
                current_state=current_state.state.value if current_state else None,
                current_substate=current_state.substate.value if current_state else None,
                market_context_keys=list(market_context.keys()) if market_context else None,
                has_metrics=metrics is not None
            )
            # Return invalidation on validation errors
            return StateTransition(
                new_state=PlanLifecycleState.INVALID,
                new_substate=BreakoutSubState.NONE,
                timestamp=datetime.utcnow(),
                should_emit_signal=True,
                invalid_reason=InvalidationReason.TIME_LIMIT  # Generic error reason
            )
        except Exception as e:
            # Log unexpected errors with comprehensive context
            self.logger.error(
                "Unexpected error during breakout evaluation",
                plan_id=plan_id,
                error=str(e),
                error_type=type(e).__name__,
                current_state=current_state.state.value if current_state else None,
                current_substate=current_state.substate.value if current_state else None,
                market_context_summary={
                    "last_price": market_context.get('last_price') if market_context else None,
                    "timestamp": str(market_context.get('timestamp')) if market_context else None,
                    "atr": market_context.get('atr') if market_context else None,
                    "rvol": market_context.get('rvol') if market_context else None
                },
                config_summary={
                    "penetration_pct": cfg.penetration_pct if cfg else None,
                    "min_rvol": cfg.min_rvol if cfg else None,
                    "confirm_close": cfg.confirm_close if cfg else None
                } if cfg else None,
                plan_summary={
                    "entry_price": plan_data.get('entry_price') if plan_data else None,
                    "direction": plan_data.get('direction') if plan_data else None
                } if plan_data else None
            )
            # Return invalidation on unexpected errors
            return StateTransition(
                new_state=PlanLifecycleState.INVALID,
                new_substate=BreakoutSubState.NONE,
                timestamp=datetime.utcnow(),
                should_emit_signal=True,
                invalid_reason=InvalidationReason.TIME_LIMIT  # Generic error reason
            )


class BreakoutGateValidator:
    """Validates specific breakout gating conditions with detailed logging."""

    def __init__(self):
        self.logger = logger
        self.gating_logger = gating_logger

    def validate_rvol_gate(
        self,
        rvol: Optional[float],
        min_rvol: float,
        plan_id: str
    ) -> bool:
        """Validate RVOL gate with logging."""
        if min_rvol <= 0:
            log_gate_decision(
                self.gating_logger,
                gate_name="rvol",
                passed=True,
                plan_id=plan_id,
                reason="Gate disabled (min_rvol <= 0)",
                context={"min_rvol": min_rvol}
            )
            return True  # Gate disabled

        if rvol is None:
            log_gate_decision(
                self.gating_logger,
                gate_name="rvol",
                passed=False,
                plan_id=plan_id,
                reason="No RVOL data available",
                context={"min_rvol": min_rvol, "rvol": None}
            )
            return False

        passed = rvol >= min_rvol

        log_gate_decision(
            self.gating_logger,
            gate_name="rvol",
            passed=passed,
            plan_id=plan_id,
            reason=f"RVOL {rvol:.2f} {'≥' if passed else '<'} threshold {min_rvol}",
            context={
                "rvol": rvol,
                "min_rvol": min_rvol,
                "difference": rvol - min_rvol,
                "multiplier": rvol / min_rvol if min_rvol > 0 else None
            }
        )

        return passed

    def validate_volatility_gate(
        self,
        bar_range: Optional[float],
        atr: Optional[float],
        min_break_range_atr: float,
        plan_id: str
    ) -> bool:
        """Validate volatility gate with logging."""
        if min_break_range_atr <= 0:
            log_gate_decision(
                self.gating_logger,
                gate_name="volatility",
                passed=True,
                plan_id=plan_id,
                reason="Gate disabled (min_break_range_atr <= 0)",
                context={"min_break_range_atr": min_break_range_atr}
            )
            return True  # Gate disabled

        if bar_range is None or atr is None:
            log_gate_decision(
                self.gating_logger,
                gate_name="volatility",
                passed=False,
                plan_id=plan_id,
                reason="Missing required data",
                context={
                    "bar_range": bar_range,
                    "atr": atr,
                    "min_break_range_atr": min_break_range_atr
                }
            )
            return False

        min_range = min_break_range_atr * atr
        passed = bar_range >= min_range

        log_gate_decision(
            self.gating_logger,
            gate_name="volatility",
            passed=passed,
            plan_id=plan_id,
            reason=f"Bar range {bar_range:.6f} {'≥' if passed else '<'} min range {min_range:.6f} ({min_break_range_atr}x ATR)",
            context={
                "bar_range": bar_range,
                "atr": atr,
                "min_range": min_range,
                "min_break_range_atr": min_break_range_atr,
                "range_ratio": bar_range / min_range if min_range > 0 else None
            }
        )

        return passed

    def validate_orderbook_sweep_gate(
        self,
        ob_sweep_detected: bool,
        ob_sweep_side: Optional[str],
        expected_side: str,
        plan_id: str
    ) -> bool:
        """Validate order book sweep gate with logging."""
        if not ob_sweep_detected:
            log_gate_decision(
                self.gating_logger,
                gate_name="orderbook_sweep",
                passed=False,
                plan_id=plan_id,
                reason="No order book sweep detected",
                context={
                    "expected_side": expected_side,
                    "sweep_detected": False
                }
            )
            return False

        if ob_sweep_side != expected_side:
            log_gate_decision(
                self.gating_logger,
                gate_name="orderbook_sweep",
                passed=False,
                plan_id=plan_id,
                reason=f"Sweep detected on wrong side: {ob_sweep_side} != {expected_side}",
                context={
                    "detected_side": ob_sweep_side,
                    "expected_side": expected_side,
                    "sweep_detected": True
                }
            )
            return False

        log_gate_decision(
            self.gating_logger,
            gate_name="orderbook_sweep",
            passed=True,
            plan_id=plan_id,
            reason=f"Order book sweep confirmed on {ob_sweep_side} side",
            context={
                "sweep_side": ob_sweep_side,
                "expected_side": expected_side,
                "sweep_detected": True
            }
        )

        return True

    def validate_penetration_gate(
        self,
        current_price: float,
        entry_price: float,
        penetration_distance: float,
        is_short: bool,
        plan_id: str
    ) -> bool:
        """Validate price penetration gate with logging."""
        if is_short:
            # Short: price must be below entry by penetration distance
            target_price = entry_price - penetration_distance
            passed = current_price <= target_price
            direction_desc = "below"
        else:
            # Long: price must be above entry by penetration distance
            target_price = entry_price + penetration_distance
            passed = current_price >= target_price
            direction_desc = "above"

        actual_penetration = abs(current_price - entry_price)

        log_gate_decision(
            self.gating_logger,
            gate_name="penetration",
            passed=passed,
            plan_id=plan_id,
            reason=f"Price {current_price} must be {direction_desc} {target_price} (penetration {actual_penetration:.6f} {'≥' if passed else '<'} {penetration_distance:.6f})",
            context={
                "current_price": current_price,
                "entry_price": entry_price,
                "target_price": target_price,
                "penetration_distance": penetration_distance,
                "actual_penetration": actual_penetration,
                "is_short": is_short,
                "penetration_ratio": actual_penetration / penetration_distance if penetration_distance > 0 else None
            }
        )

        return passed

    def validate_time_confirmation_gate(
        self,
        break_seen_time: datetime,
        current_time: datetime,
        confirm_seconds: float,
        plan_id: str
    ) -> bool:
        """Validate time-based confirmation gate with logging."""
        if confirm_seconds <= 0:
            log_gate_decision(
                self.gating_logger,
                gate_name="time_confirmation",
                passed=True,
                plan_id=plan_id,
                reason="Gate disabled (confirm_seconds <= 0)",
                context={"confirm_seconds": confirm_seconds}
            )
            return True  # Gate disabled

        elapsed_seconds = (current_time - break_seen_time).total_seconds()
        passed = elapsed_seconds >= confirm_seconds

        log_gate_decision(
            self.gating_logger,
            gate_name="time_confirmation",
            passed=passed,
            plan_id=plan_id,
            reason=f"Elapsed time {elapsed_seconds:.1f}s {'≥' if passed else '<'} confirmation time {confirm_seconds}s",
            context={
                "break_seen_time": break_seen_time.isoformat(),
                "current_time": current_time.isoformat(),
                "elapsed_seconds": elapsed_seconds,
                "confirm_seconds": confirm_seconds,
                "completion_ratio": elapsed_seconds / confirm_seconds if confirm_seconds > 0 else None
            }
        )

        return passed

    def validate_close_confirmation_gate(
        self,
        candle_close: float,
        entry_price: float,
        is_short: bool,
        is_candle_closed: bool,
        plan_id: str
    ) -> bool:
        """Validate close-based confirmation gate with logging."""
        if not is_candle_closed:
            log_gate_decision(
                self.gating_logger,
                gate_name="close_confirmation",
                passed=False,
                plan_id=plan_id,
                reason="Candle not yet closed",
                context={
                    "candle_close": candle_close,
                    "entry_price": entry_price,
                    "is_short": is_short,
                    "is_candle_closed": is_candle_closed
                }
            )
            return False

        if is_short:
            # Short: close must be below entry
            passed = candle_close < entry_price
            direction_desc = "below"
        else:
            # Long: close must be above entry
            passed = candle_close > entry_price
            direction_desc = "above"

        log_gate_decision(
            self.gating_logger,
            gate_name="close_confirmation",
            passed=passed,
            plan_id=plan_id,
            reason=f"Candle close {candle_close} must be {direction_desc} entry {entry_price}",
            context={
                "candle_close": candle_close,
                "entry_price": entry_price,
                "is_short": is_short,
                "is_candle_closed": is_candle_closed,
                "close_distance": abs(candle_close - entry_price),
                "close_beyond_entry": passed
            }
        )

        return passed


class InvalidationChecker:
    """Checks invalidation conditions with detailed logging."""

    def __init__(self):
        self.logger = logger
        self.gating_logger = gating_logger

    def check_price_invalidation(
        self,
        current_price: float,
        invalidation_conditions: list,
        plan_id: str
    ) -> Optional[InvalidationReason]:
        """Check price-based invalidation conditions."""
        for i, condition in enumerate(invalidation_conditions):
            if isinstance(condition, dict):
                condition_type = condition.get('condition_type')
                level = condition.get('level')

                if condition_type == 'price_above' and level:
                    if current_price > level:
                        self.gating_logger.warning(
                            "Price invalidation triggered",
                            plan_id=plan_id,
                            invalidation_type="price_above",
                            current_price=current_price,
                            limit_level=level,
                            price_excess=current_price - level,
                            condition_index=i,
                            event="invalidation_triggered"
                        )
                        return InvalidationReason.PRICE_ABOVE
                    else:
                        self.gating_logger.bind(
                            plan_id=plan_id,
                            invalidation_type="price_above",
                            current_price=current_price,
                            limit_level=level,
                            price_margin=level - current_price,
                            condition_index=i,
                            event="invalidation_check"
                        ).debug("Price invalidation check passed")

                elif condition_type == 'price_below' and level:
                    if current_price < level:
                        self.gating_logger.warning(
                            "Price invalidation triggered",
                            plan_id=plan_id,
                            invalidation_type="price_below",
                            current_price=current_price,
                            limit_level=level,
                            price_deficit=level - current_price,
                            condition_index=i,
                            event="invalidation_triggered"
                        )
                        return InvalidationReason.PRICE_BELOW
                    else:
                        self.gating_logger.debug(
                            "Price invalidation check passed",
                            plan_id=plan_id,
                            invalidation_type="price_below",
                            current_price=current_price,
                            limit_level=level,
                            price_margin=current_price - level,
                            condition_index=i,
                            event="invalidation_check"
                        )

        return None

    def check_time_invalidation(
        self,
        current_time: datetime,
        plan_created_at: datetime,
        invalidation_conditions: list,
        plan_id: str
    ) -> bool:
        """Check time-based invalidation conditions."""
        for i, condition in enumerate(invalidation_conditions):
            if isinstance(condition, dict):
                if condition.get('condition_type') == 'time_limit':
                    duration_seconds = condition.get('duration_seconds', 0)
                    elapsed = (current_time - plan_created_at).total_seconds()

                    if elapsed > duration_seconds:
                        self.gating_logger.warning(
                            "Time invalidation triggered",
                            plan_id=plan_id,
                            invalidation_type="time_limit",
                            elapsed_seconds=elapsed,
                            limit_seconds=duration_seconds,
                            time_excess=elapsed - duration_seconds,
                            condition_index=i,
                            plan_created_at=plan_created_at.isoformat(),
                            current_time=current_time.isoformat(),
                            event="invalidation_triggered"
                        )
                        return True
                    else:
                        self.gating_logger.debug(
                            "Time invalidation check passed",
                            plan_id=plan_id,
                            invalidation_type="time_limit",
                            elapsed_seconds=elapsed,
                            limit_seconds=duration_seconds,
                            time_remaining=duration_seconds - elapsed,
                            condition_index=i,
                            completion_ratio=elapsed / duration_seconds if duration_seconds > 0 else 0,
                            event="invalidation_check"
                        )

        return False

    def check_fakeout_invalidation(
        self,
        last_closed_candle: Any,
        entry_price: float,
        is_short: bool,
        plan_id: str
    ) -> bool:
        """Check fakeout close invalidation."""
        if not last_closed_candle or not hasattr(last_closed_candle, 'close'):
            self.gating_logger.debug(
                "Fakeout invalidation check skipped - no closed candle data",
                plan_id=plan_id,
                has_candle=last_closed_candle is not None,
                has_close_attr=hasattr(last_closed_candle, 'close') if last_closed_candle else False,
                event="invalidation_check"
            )
            return False

        if not last_closed_candle.is_closed:
            self.gating_logger.debug(
                "Fakeout invalidation check skipped - candle not closed",
                plan_id=plan_id,
                is_closed=last_closed_candle.is_closed,
                event="invalidation_check"
            )
            return False

        is_fakeout = False
        direction_desc = "short" if is_short else "long"

        if is_short:
            # Short breakout fakeout: close back above entry
            is_fakeout = last_closed_candle.close > entry_price
            fakeout_desc = "close above entry (short breakout)"
        else:
            # Long breakout fakeout: close back below entry
            is_fakeout = last_closed_candle.close < entry_price
            fakeout_desc = "close below entry (long breakout)"

        if is_fakeout:
            self.gating_logger.warning(
                "Fakeout invalidation triggered",
                plan_id=plan_id,
                invalidation_type="fakeout_close",
                entry_price=entry_price,
                close_price=last_closed_candle.close,
                direction=direction_desc,
                fakeout_distance=abs(last_closed_candle.close - entry_price),
                fakeout_description=fakeout_desc,
                candle_timestamp=last_closed_candle.ts.isoformat() if hasattr(last_closed_candle, 'ts') else None,
                event="invalidation_triggered"
            )
        else:
            self.gating_logger.debug(
                "Fakeout invalidation check passed",
                plan_id=plan_id,
                invalidation_type="fakeout_close",
                entry_price=entry_price,
                close_price=last_closed_candle.close,
                direction=direction_desc,
                close_distance_from_entry=abs(last_closed_candle.close - entry_price),
                close_beyond_entry=True,
                event="invalidation_check"
            )

        return is_fakeout

    def check_stop_loss_invalidation(
        self,
        current_price: float,
        stop_loss_price: Optional[float],
        is_short: bool,
        plan_id: str
    ) -> bool:
        """Check stop loss invalidation with detailed logging."""
        if not stop_loss_price:
            self.gating_logger.debug(
                "Stop loss invalidation check skipped - no stop loss set",
                plan_id=plan_id,
                event="invalidation_check"
            )
            return False

        is_stopped = False
        direction_desc = "short" if is_short else "long"

        if is_short:
            # Short position stop: price above stop loss
            is_stopped = current_price >= stop_loss_price
            stop_desc = "price above stop loss (short position)"
        else:
            # Long position stop: price below stop loss
            is_stopped = current_price <= stop_loss_price
            stop_desc = "price below stop loss (long position)"

        if is_stopped:
            self.gating_logger.warning(
                "Stop loss invalidation triggered",
                plan_id=plan_id,
                invalidation_type="stop_loss",
                current_price=current_price,
                stop_loss_price=stop_loss_price,
                direction=direction_desc,
                stop_distance=abs(current_price - stop_loss_price),
                stop_description=stop_desc,
                event="invalidation_triggered"
            )
        else:
            self.gating_logger.debug(
                "Stop loss invalidation check passed",
                plan_id=plan_id,
                invalidation_type="stop_loss",
                current_price=current_price,
                stop_loss_price=stop_loss_price,
                direction=direction_desc,
                distance_to_stop=abs(current_price - stop_loss_price),
                event="invalidation_check"
            )

        return is_stopped

    def log_invalidation_context(
        self,
        plan_id: str,
        current_price: float,
        current_time: datetime,
        plan_data: dict,
        context: dict = None
    ) -> None:
        """Log comprehensive invalidation context for audit trail."""
        invalidation_conditions = plan_data.get('extra_data', {}).get('invalidation_conditions', [])
        created_at = plan_data.get('created_at')
        stop_loss = plan_data.get('stop_loss')

        self.gating_logger.info(
            "Invalidation context evaluation",
            plan_id=plan_id,
            current_price=current_price,
            current_time=current_time.isoformat(),
            plan_created_at=created_at.isoformat() if created_at else None,
            elapsed_seconds=(current_time - created_at).total_seconds() if created_at else None,
            stop_loss_price=stop_loss,
            invalidation_conditions_count=len(invalidation_conditions),
            invalidation_conditions=invalidation_conditions,
            additional_context=context or {},
            event="invalidation_context"
        )


# Module-level instances for convenience
transition_handler = StateTransitionHandler()
gate_validator = BreakoutGateValidator()
invalidation_checker = InvalidationChecker()
