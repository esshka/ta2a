"""
Runtime state management for breakout plan lifecycle.

This module handles state persistence, signal emission coordination,
and runtime state management for active breakout plans.
"""

import hashlib
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

import structlog

from ..utils.time import format_market_time, get_market_time

if TYPE_CHECKING:
    from ..models.metrics import MetricsSnapshot
from ..config.signal_delivery import (
    DeliveryMethod,
    SignalDeliveryConfig,
    get_default_delivery_config,
)
from ..delivery.base import BaseSignalDelivery, DeliveryResult
from ..delivery.file_delivery import FileSignalDelivery
from ..delivery.http_delivery import HttpSignalDelivery
from ..delivery.stdout_delivery import StdoutSignalDelivery
from ..persistence.signal_store import SignalStore
from .models import (
    BreakoutParameters,
    BreakoutSubState,
    PlanLifecycleState,
    PlanRuntimeState,
    StateTransition,
)
from .transitions import transition_handler

logger = structlog.get_logger(__name__)


class PlanRuntimeManager:
    """Manages runtime state for active breakout plans."""

    def __init__(self):
        self.logger = logger
        self.plan_states: dict[str, PlanRuntimeState] = {}
        self.signal_queue: list[dict[str, Any]] = []

    def get_or_create_state(self, plan_id: str) -> PlanRuntimeState:
        """Get existing runtime state or create new one for plan."""
        if plan_id not in self.plan_states:
            self.plan_states[plan_id] = PlanRuntimeState(
                state=PlanLifecycleState.PENDING,
                substate=BreakoutSubState.NONE
            )
            self.logger.info(
                "Created new plan runtime state",
                plan_id=plan_id,
                initial_state=PlanLifecycleState.PENDING.value
            )

        return self.plan_states[plan_id]

    def update_state(
        self,
        plan_id: str,
        new_state: PlanRuntimeState,
        emit_signal: bool = False,
        signal_context: Optional[dict] = None,
        market_context: Optional[dict] = None
    ) -> None:
        """Update runtime state for a plan and optionally emit signal."""
        old_state = self.plan_states.get(plan_id)
        self.plan_states[plan_id] = new_state

        self.logger.info(
            "Updated plan runtime state",
            plan_id=plan_id,
            old_state=old_state.state.value if old_state else "none",
            old_substate=old_state.substate.value if old_state else "none",
            new_state=new_state.state.value,
            new_substate=new_state.substate.value,
            emit_signal=emit_signal
        )

        if emit_signal and not new_state.signal_emitted:
            self._queue_signal(plan_id, new_state, signal_context, market_context)

    def process_plan_tick(
        self,
        plan_id: str,
        plan_data: dict[str, Any],
        market_context: dict[str, Any],
        cfg: BreakoutParameters,
        metrics: Optional["MetricsSnapshot"]
    ) -> Optional[StateTransition]:
        """Process a single evaluation tick for a plan."""
        current_state = self.get_or_create_state(plan_id)

        # Skip if already in terminal state
        if current_state.state in [PlanLifecycleState.TRIGGERED,
                                   PlanLifecycleState.INVALID,
                                   PlanLifecycleState.EXPIRED]:
            return None

        # Evaluate for state transition
        transition = transition_handler.evaluate_and_transition(
            current_state=current_state,
            market_context=market_context,
            cfg=cfg,
            plan_data=plan_data,
            metrics=metrics
        )

        if transition:
            # Apply the transition
            new_state = transition_handler.apply_transition(
                current_state=current_state,
                transition=transition,
                plan_id=plan_id
            )

            # Update stored state and emit signal if needed
            self.update_state(
                plan_id=plan_id,
                new_state=new_state,
                emit_signal=transition.should_emit_signal,
                signal_context=transition.signal_context,
                market_context=market_context
            )

        return transition

    def get_state(self, plan_id: str) -> Optional[PlanRuntimeState]:
        """Get current runtime state for a plan."""
        return self.plan_states.get(plan_id)

    def remove_plan(self, plan_id: str) -> None:
        """Remove plan from runtime tracking."""
        if plan_id in self.plan_states:
            old_state = self.plan_states.pop(plan_id)
            self.logger.info(
                "Removed plan from runtime tracking",
                plan_id=plan_id,
                final_state=old_state.state.value,
                final_substate=old_state.substate.value
            )

    def get_active_plans(self) -> list[str]:
        """Get list of plan IDs in non-terminal states."""
        active = []
        for plan_id, state in self.plan_states.items():
            if state.state not in [PlanLifecycleState.TRIGGERED,
                                   PlanLifecycleState.INVALID,
                                   PlanLifecycleState.EXPIRED]:
                active.append(plan_id)
        return active

    def get_pending_signals(self) -> list[dict[str, Any]]:
        """Get and clear pending signals."""
        signals = self.signal_queue.copy()
        self.signal_queue.clear()
        return signals

    def _queue_signal(
        self,
        plan_id: str,
        state: PlanRuntimeState,
        context: Optional[dict] = None,
        market_context: Optional[dict] = None
    ) -> None:
        """Queue a signal for emission."""
        # CRITICAL: Use market time from context for signal timestamps
        # This ensures signals are tied to market time, not wall-clock time
        # Signal timestamps must be consistent with market data timestamps
        market_ts = market_context.get("timestamp") if market_context else None
        signal_timestamp = get_market_time(market_ts)

        signal = {
            "plan_id": plan_id,
            "state": state.state.value,
            "runtime": {
                "armed_at": state.armed_at.isoformat() if state.armed_at else None,
                "triggered_at": state.triggered_at.isoformat() if state.triggered_at else None,
                "break_ts": state.break_ts.isoformat() if state.break_ts else None,
                "invalid_reason": state.invalid_reason.value if state.invalid_reason else None,
                "substate": state.substate.value
            },
            "timestamp": format_market_time(signal_timestamp),
            "context": context or {}
        }

        self.signal_queue.append(signal)

        self.logger.info(
            "Queued signal for emission",
            plan_id=plan_id,
            signal_state=state.state.value,
            signal_substate=state.substate.value
        )


class SignalEmitter:
    """Handles signal emission with idempotency and formatting."""

    def __init__(self, delivery_config: Optional[SignalDeliveryConfig] = None):
        self.logger = logger
        self.emitted_signals: dict[str, set] = {}  # plan_id -> set of emitted states
        self.signal_hashes: dict[str, str] = {}  # plan_id -> latest signal hash
        self.delivery_config = delivery_config or get_default_delivery_config()
        self.signal_store = SignalStore() if delivery_config else None
        self.delivery_handlers: dict[str, BaseSignalDelivery] = {}

        # Initialize delivery handlers
        self._init_delivery_handlers()

    def _init_delivery_handlers(self) -> None:
        """Initialize delivery handlers based on configuration."""
        if not self.delivery_config.enabled:
            return

        for destination in self.delivery_config.destinations:
            if not destination.enabled:
                continue

            try:
                if destination.method == DeliveryMethod.HTTP_POST:
                    handler = HttpSignalDelivery(destination.name, destination.config)
                elif destination.method == DeliveryMethod.FILE_OUTPUT:
                    handler = FileSignalDelivery(destination.name, destination.config)
                elif destination.method == DeliveryMethod.STDOUT:
                    handler = StdoutSignalDelivery(destination.name, destination.config)
                else:
                    self.logger.warning(f"Unsupported delivery method: {destination.method}")
                    continue

                self.delivery_handlers[destination.name] = handler
                self.logger.info(f"Initialized delivery handler: {destination.name}")

            except Exception as e:
                self.logger.error(
                    f"Failed to initialize delivery handler: {destination.name}",
                    error=str(e)
                )

    def emit_signal(
        self,
        plan_id: str,
        signal_data: dict[str, Any],
        metrics: Optional["MetricsSnapshot"] = None
    ) -> dict[str, Any]:
        """
        Emit a trading signal with proper formatting from dev_proto.md section 10.

        Returns the formatted signal dict for downstream consumption.
        """
        # Check idempotency - state-based check first
        state = signal_data.get("state")
        if self._already_emitted(plan_id, state):
            self.logger.warning(
                "Signal already emitted, skipping",
                plan_id=plan_id,
                state=state
            )
            return {}

        # Build signal according to dev_proto.md section 10 contract
        formatted_signal = {
            "plan_id": plan_id,
            "state": state,
            "protocol_version": "breakout-v1",
            "runtime": signal_data.get("runtime", {}),
            "timestamp": signal_data.get("timestamp"),
            "last_price": signal_data.get("context", {}).get("last_price"),
            "metrics": self._format_metrics(metrics) if metrics else {},
            "strength_score": self._calculate_strength_score(metrics, signal_data.get("context", {}))
        }

        # Add context-specific fields
        context = signal_data.get("context", {})
        if "entry_mode" in context:
            formatted_signal["entry_mode"] = context["entry_mode"]

        # Enhanced duplicate check using signal hash
        if self._is_duplicate_signal(formatted_signal):
            self.logger.warning(
                "Duplicate signal detected by hash, skipping",
                plan_id=plan_id,
                state=state,
                signal_hash=self._generate_signal_hash(formatted_signal)
            )
            return {}

        # Store signal in persistence layer
        if self.signal_store:
            self.signal_store.store_signal(formatted_signal)

        # Deliver signal to configured destinations
        self._deliver_signal(formatted_signal)

        # Mark as emitted with signal hash
        signal_hash = self._generate_signal_hash(formatted_signal)
        self._mark_emitted(plan_id, state, signal_hash)

        self.logger.info(
            "Emitted trading signal",
            plan_id=plan_id,
            state=state,
            strength_score=formatted_signal.get("strength_score", 0),
            entry_mode=formatted_signal.get("entry_mode")
        )

        return formatted_signal

    def _deliver_signal(self, signal: dict[str, Any]) -> None:
        """Deliver signal to all configured destinations."""
        if not self.delivery_config.enabled or not self.delivery_handlers:
            return

        # Apply filtering
        filtered_destinations = self._filter_destinations(signal)

        for destination_name in filtered_destinations:
            handler = self.delivery_handlers.get(destination_name)
            if not handler:
                continue

            try:
                # Use retry logic from delivery config
                results = handler.deliver_with_retry(
                    [signal],
                    max_retries=self.delivery_config.failure_retry_attempts,
                    retry_delay=self.delivery_config.failure_retry_delay_seconds
                )

                # Log delivery results
                for result in results:
                    if result.status.value == "success":
                        self.logger.info(
                            "Signal delivered successfully",
                            destination=destination_name,
                            plan_id=signal["plan_id"],
                            attempts=result.attempt_count
                        )
                    else:
                        self.logger.error(
                            "Signal delivery failed",
                            destination=destination_name,
                            plan_id=signal["plan_id"],
                            status=result.status.value,
                            message=result.message,
                            attempts=result.attempt_count
                        )

                        # Write to dead letter if configured
                        if (self.delivery_config.dead_letter_enabled and
                            result.status.value == "dead_letter"):
                            self._write_dead_letter(signal, destination_name, result)

            except Exception as e:
                self.logger.error(
                    "Unexpected error during signal delivery",
                    destination=destination_name,
                    plan_id=signal["plan_id"],
                    error=str(e)
                )

    def _filter_destinations(self, signal: dict[str, Any]) -> list[str]:
        """Filter destinations based on signal content and configuration."""
        filtered = []

        for destination in self.delivery_config.destinations:
            if not destination.enabled:
                continue

            # State filter
            if (destination.states_filter and
                signal.get("state") not in destination.states_filter):
                continue

            # Plan filter
            if (destination.plans_filter and
                signal.get("plan_id") not in destination.plans_filter):
                continue

            # Strength score filter
            if (destination.min_strength_score is not None and
                signal.get("strength_score", 0) < destination.min_strength_score):
                continue

            filtered.append(destination.name)

        return filtered

    def _write_dead_letter(self, signal: dict[str, Any], destination: str, result: DeliveryResult) -> None:
        """Write failed signal to dead letter queue."""
        if not self.delivery_config.dead_letter_path:
            return

        try:
            import json
            from pathlib import Path

            dead_letter_path = Path(self.delivery_config.dead_letter_path)
            dead_letter_path.parent.mkdir(parents=True, exist_ok=True)

            dead_letter_entry = {
                "signal": signal,
                "destination": destination,
                "failure_reason": result.message,
                "failed_at": datetime.now(timezone.utc).isoformat()
            }

            with open(dead_letter_path, 'a') as f:
                json.dump(dead_letter_entry, f)
                f.write('\n')

            self.logger.info(
                "Signal written to dead letter queue",
                plan_id=signal["plan_id"],
                destination=destination,
                path=str(dead_letter_path)
            )

        except Exception as e:
            self.logger.error(
                "Failed to write dead letter",
                plan_id=signal["plan_id"],
                error=str(e)
            )

    def _generate_signal_hash(self, signal: dict[str, Any]) -> str:
        """Generate unique hash for signal deduplication."""
        # Use plan_id, state, and timestamp for uniqueness
        key_data = f"{signal['plan_id']}:{signal['state']}:{signal['timestamp']}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def _already_emitted(self, plan_id: str, state: str) -> bool:
        """Check if signal for this plan/state combo was already emitted."""
        if plan_id not in self.emitted_signals:
            self.emitted_signals[plan_id] = set()
        return state in self.emitted_signals[plan_id]

    def _is_duplicate_signal(self, signal: dict[str, Any]) -> bool:
        """Enhanced duplicate detection using signal hash."""
        plan_id = signal["plan_id"]
        signal_hash = self._generate_signal_hash(signal)

        # Check if same signal hash was already emitted
        if plan_id in self.signal_hashes:
            return self.signal_hashes[plan_id] == signal_hash

        return False

    def _mark_emitted(self, plan_id: str, state: str, signal_hash: str) -> None:
        """Mark signal as emitted for idempotency tracking."""
        if plan_id not in self.emitted_signals:
            self.emitted_signals[plan_id] = set()
        self.emitted_signals[plan_id].add(state)
        self.signal_hashes[plan_id] = signal_hash

    def _format_metrics(self, metrics: "MetricsSnapshot") -> dict[str, Any]:
        """Format metrics for signal emission."""
        return {
            "rvol": metrics.rvol,
            "natr_pct": metrics.natr_pct,
            "atr": metrics.atr,
            "pinbar": metrics.pinbar is not None,
            "pinbar_type": metrics.pinbar,
            "ob_sweep_detected": metrics.ob_sweep_detected,
            "ob_sweep_side": metrics.ob_sweep_side,
            "ob_imbalance_long": metrics.ob_imbalance_long,
            "ob_imbalance_short": metrics.ob_imbalance_short
        }

    def _calculate_strength_score(
        self,
        metrics: Optional["MetricsSnapshot"],
        context: dict[str, Any]
    ) -> float:
        """
        Calculate strength score from dev_proto.md section 11.

        Example weighting:
        score = 30 (baseline) + 25 (RVOL) + 25 (vol regime) + 10 (pinbar) + 10 (sweep)
        """
        if not metrics:
            return 30.0  # Baseline only

        score = 30.0  # Baseline when triggered

        # RVOL component (0-25 points)
        if metrics.rvol is not None:
            rvol_score = min(max((metrics.rvol - 1.0) / 2.0, 0.0), 1.0) * 25
            score += rvol_score

        # Volatility regime (0-25 points)
        if metrics.natr_pct is not None:
            if 0.5 <= metrics.natr_pct <= 5.0:  # Sweet spot
                score += 25

        # Pinbar bonus (0-10 points)
        if metrics.pinbar:
            score += 10

        # Order book sweep bonus (0-10 points)
        if metrics.ob_sweep_detected:
            score += 10

        return round(min(score, 100.0), 1)

    def clear_plan_signals(self, plan_id: str) -> None:
        """Clear emitted signal tracking for a plan."""
        if plan_id in self.emitted_signals:
            del self.emitted_signals[plan_id]
        if plan_id in self.signal_hashes:
            del self.signal_hashes[plan_id]


class StateManager:
    """High-level state management orchestrator."""

    def __init__(self):
        self.runtime_manager = PlanRuntimeManager()
        self.signal_emitter = SignalEmitter()
        self.logger = logger

    def process_market_tick(
        self,
        active_plans: list[dict[str, Any]],
        market_data: dict[str, Any],
        metrics_by_plan: dict[str, "MetricsSnapshot"],
        config_by_plan: dict[str, BreakoutParameters]
    ) -> list[dict[str, Any]]:
        """
        Process a market tick for all active plans.

        Returns list of emitted signals.
        """
        emitted_signals = []

        for plan in active_plans:
            plan_id = plan.get('id')
            if not plan_id:
                continue

            metrics = metrics_by_plan.get(plan_id)
            config = config_by_plan.get(plan_id, BreakoutParameters())

            # Process the plan
            self.runtime_manager.process_plan_tick(
                plan_id=plan_id,
                plan_data=plan,
                market_context=market_data,
                cfg=config,
                metrics=metrics
            )

            # Check for pending signals
            pending = self.runtime_manager.get_pending_signals()
            for signal_data in pending:
                if signal_data.get("plan_id") == plan_id:
                    # Add market context
                    signal_data["context"]["last_price"] = market_data.get("last_price")

                    # Emit the signal
                    formatted_signal = self.signal_emitter.emit_signal(
                        plan_id=plan_id,
                        signal_data=signal_data,
                        metrics=metrics
                    )

                    if formatted_signal:
                        emitted_signals.append(formatted_signal)

        return emitted_signals

    def get_plan_state(self, plan_id: str) -> Optional[PlanRuntimeState]:
        """Get current state for a plan."""
        return self.runtime_manager.get_state(plan_id)

    def remove_plan(self, plan_id: str) -> None:
        """Remove plan from tracking."""
        self.runtime_manager.remove_plan(plan_id)
        self.signal_emitter.clear_plan_signals(plan_id)

    def get_active_plan_count(self) -> int:
        """Get count of plans in non-terminal states."""
        return len(self.runtime_manager.get_active_plans())


# Module-level instance for singleton usage
state_manager = StateManager()
