"""
Main evaluation engine coordinator.

Orchestrates the breakout plan evaluation pipeline, coordinating data ingestion,
metrics calculation, state machine evaluation, and signal emission.
"""

from typing import TYPE_CHECKING, Any, Optional

import structlog

from .config.loader import ConfigLoader
from .config.validation import ConfigValidator
from .data.models import InstrumentDataStore
from .data.normalizer import DataNormalizer
from .data.plan_normalizer import PlanNormalizer
from .errors import (
    DataQualityError,
    TemporalDataError,
    PartialDataError,
    MissingDataError,
    MalformedDataError,
    InsufficientDataError,
    MetricsCalculationError,
    StateTransitionError,
    RecoverableError,
    GracefulDegradationError,
)
from .logging.config import get_gating_logger
from .metrics.calculator import MetricsCalculator
from .state.models import BreakoutParameters, MarketContext
from .state.runtime import state_manager
from .utils.time import get_market_time_with_latency

if TYPE_CHECKING:
    from .models.metrics import MetricsSnapshot

logger = structlog.get_logger(__name__)
gating_logger = get_gating_logger(__name__)


class BreakoutEvaluationEngine:
    """
    Main coordinator for the breakout trading plan evaluation system.

    Manages the evaluation pipeline:
    Market Data → Normalization → Metrics → State Machine → Signals
    """

    def __init__(self, config_dir: Optional[str] = None) -> None:
        """Initialize the breakout evaluation engine."""
        self.logger = logger
        self.gating_logger = gating_logger

        # Initialize components
        self.config_loader = ConfigLoader.create(config_dir)
        self.normalizer = DataNormalizer()
        self.plan_normalizer = PlanNormalizer()

        # Per-instrument data stores and calculators
        self.data_stores: dict[str, InstrumentDataStore] = {}
        self.metrics_calculators: dict[str, MetricsCalculator] = {}

        # Active plans tracking
        self.active_plans: list[dict[str, Any]] = []

        self.logger.info("Breakout evaluation engine initialized")

    def add_plan(self, plan_data: dict[str, Any]) -> None:
        """Add a new breakout plan for evaluation."""
        plan_id = plan_data.get('id')
        instrument_id = plan_data.get('instrument_id')

        if not plan_id or not instrument_id:
            self.logger.error(
                "Invalid plan data - missing required fields",
                plan_id=plan_id,
                instrument_id=instrument_id
            )
            return

        # Validate plan type
        if plan_data.get('entry_type') != 'breakout':
            self.logger.warning(
                "Plan entry type is not 'breakout', skipping",
                plan_id=plan_id,
                entry_type=plan_data.get('entry_type')
            )
            return

        # Normalize plan data
        normalization_result = self.plan_normalizer.normalize_plan(plan_data)

        if not normalization_result.success:
            self.logger.error(
                "Plan normalization failed",
                plan_id=plan_id,
                error=normalization_result.error_msg
            )
            return

        normalized_plan = normalization_result.normalized_plan

        # Validate plan parameter overrides
        plan_overrides = normalized_plan.get('extra_data', {}).get('breakout_params', {})
        if plan_overrides:
            validation_errors = ConfigValidator.validate_breakout_params(plan_overrides)
            if validation_errors:
                error_msgs = [f"{err.field}: {err.message} (got: {err.value})" for err in validation_errors]
                self.logger.error(
                    "Plan parameter validation failed",
                    plan_id=plan_id,
                    errors=error_msgs
                )
                return

        self.active_plans.append(normalized_plan)

        # Ensure instrument data store exists
        if instrument_id not in self.data_stores:
            self.data_stores[instrument_id] = InstrumentDataStore()
            self.metrics_calculators[instrument_id] = MetricsCalculator()

        self.logger.info(
            "Added breakout plan for evaluation",
            plan_id=plan_id,
            instrument_id=instrument_id,
            entry_price=plan_data.get('entry_price'),
            direction=plan_data.get('direction')
        )

    def remove_plan(self, plan_id: str) -> None:
        """Remove a plan from evaluation."""
        self.active_plans = [p for p in self.active_plans if p.get('id') != plan_id]
        state_manager.remove_plan(plan_id)

        self.logger.info("Removed plan from evaluation", plan_id=plan_id)

    def evaluate_tick(
        self,
        candlestick_payload: Optional[dict[str, Any]] = None,
        orderbook_payload: Optional[dict[str, Any]] = None,
        instrument_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Evaluate a single market data tick.

        Args:
            candlestick_payload: Raw candlestick data from exchange
            orderbook_payload: Raw order book data from exchange
            instrument_id: Target instrument (if processing single instrument)

        Returns:
            List of generated trading signals
        """
        if not self.active_plans:
            return []

        try:
            # Validate input data
            if not candlestick_payload and not orderbook_payload:
                raise MissingDataError("No market data provided for evaluation")

            if candlestick_payload and not instrument_id:
                raise MissingDataError("instrument_id required for candlestick data")

            if orderbook_payload and not instrument_id:
                raise MissingDataError("instrument_id required for orderbook data")

            # Normalize market data
            signals = []
            processed_instruments = set()

            # Process candlestick data
            if candlestick_payload and instrument_id:
                candle_signals = self._process_candlestick_update(
                    candlestick_payload, instrument_id
                )
                signals.extend(candle_signals)
                processed_instruments.add(instrument_id)

            # Process order book data
            if orderbook_payload and instrument_id:
                book_signals = self._process_orderbook_update(
                    orderbook_payload, instrument_id
                )
                signals.extend(book_signals)
                processed_instruments.add(instrument_id)

            # For any instruments that received updates, run evaluation
            for instr_id in processed_instruments:
                eval_signals = self._evaluate_plans_for_instrument(instr_id)
                signals.extend(eval_signals)

            return signals

        except DataQualityError as e:
            self.logger.warning(
                "Data quality issue during tick evaluation",
                error=str(e),
                error_type=type(e).__name__,
                instrument_id=instrument_id,
                context=getattr(e, 'context', {})
            )
            # Continue with degraded functionality
            return []

        except RecoverableError as e:
            self.logger.warning(
                "Recoverable error during tick evaluation",
                error=str(e),
                error_type=type(e).__name__,
                instrument_id=instrument_id,
                retry_count=getattr(e, 'retry_count', 0)
            )
            return []

        except Exception as e:
            self.logger.error(
                "Unexpected error during tick evaluation",
                error=str(e),
                error_type=type(e).__name__,
                instrument_id=instrument_id
            )
            return []

    def _process_candlestick_update(
        self,
        payload: dict[str, Any],
        instrument_id: str
    ) -> list[dict[str, Any]]:
        """Process candlestick data update."""
        try:
            # Validate payload structure
            if not isinstance(payload, dict):
                raise MalformedDataError(
                    f"Candlestick payload must be dict, got {type(payload)}", 
                    raw_data=str(payload)[:100]
                )

            # Normalize candlestick data
            result = self.normalizer.normalize_candlesticks(payload)

            if not result.success or not result.candle:
                # Convert normalization failure to appropriate error type
                if result.error_msg and "timestamp" in result.error_msg.lower():
                    raise TemporalDataError(
                        f"Candlestick temporal data issue: {result.error_msg}",
                        context={"instrument_id": instrument_id, "payload": payload}
                    )
                elif result.error_msg and "missing" in result.error_msg.lower():
                    raise PartialDataError(
                        f"Candlestick missing data: {result.error_msg}",
                        context={"instrument_id": instrument_id, "skipped_reason": result.skipped_reason}
                    )
                else:
                    raise MalformedDataError(
                        f"Candlestick normalization failed: {result.error_msg}",
                        raw_data=str(payload)[:100]
                    )

            # Update data store
            data_store = self._get_data_store(instrument_id)
            candle = result.candle

            # Add to rolling bars
            bars_1m = data_store.get_bars('1m')
            bars_1m.append(candle)

            # Update volume history if candle is closed
            if candle.is_closed:
                vol_history = data_store.get_vol_history('1m')
                vol_history.append(candle.volume)

            # Update last price
            if result.last_price_updated and result.new_last_price:
                data_store.update_last_price(result.new_last_price, candle.ts)

            self.logger.debug(
                "Processed candlestick update",
                instrument_id=instrument_id,
                timestamp=candle.ts,
                price=candle.close,
                is_closed=candle.is_closed
            )

            return []  # Signals generated in _evaluate_plans_for_instrument

        except DataQualityError:
            # Re-raise data quality errors to be handled by caller
            raise
        except Exception as e:
            self.logger.error(
                "Unexpected error processing candlestick update",
                instrument_id=instrument_id,
                error=str(e),
                error_type=type(e).__name__
            )
            return []

    def _process_orderbook_update(
        self,
        payload: dict[str, Any],
        instrument_id: str
    ) -> list[dict[str, Any]]:
        """Process order book data update."""
        try:
            # Validate payload structure
            if not isinstance(payload, dict):
                raise MalformedDataError(
                    f"Order book payload must be dict, got {type(payload)}", 
                    raw_data=str(payload)[:100]
                )

            # Normalize order book data
            result = self.normalizer.normalize_orderbook(payload)

            if not result.success or not result.book_snap:
                # Convert normalization failure to appropriate error type
                if result.error_msg and "timestamp" in result.error_msg.lower():
                    raise TemporalDataError(
                        f"Order book temporal data issue: {result.error_msg}",
                        context={"instrument_id": instrument_id, "payload": payload}
                    )
                elif result.error_msg and ("missing" in result.error_msg.lower() or "empty" in result.error_msg.lower()):
                    raise PartialDataError(
                        f"Order book missing data: {result.error_msg}",
                        context={"instrument_id": instrument_id}
                    )
                else:
                    raise MalformedDataError(
                        f"Order book normalization failed: {result.error_msg}",
                        raw_data=str(payload)[:100]
                    )

            # Update data store
            data_store = self._get_data_store(instrument_id)
            data_store.update_book(result.book_snap)

            self.logger.debug(
                "Processed order book update",
                instrument_id=instrument_id,
                timestamp=result.book_snap.ts,
                bid_price=result.book_snap.bid_price,
                ask_price=result.book_snap.ask_price
            )

            return []  # Signals generated in _evaluate_plans_for_instrument

        except DataQualityError:
            # Re-raise data quality errors to be handled by caller
            raise
        except Exception as e:
            self.logger.error(
                "Unexpected error processing order book update",
                instrument_id=instrument_id,
                error=str(e),
                error_type=type(e).__name__
            )
            return []

    def _evaluate_plans_for_instrument(self, instrument_id: str) -> list[dict[str, Any]]:
        """Evaluate all plans for a specific instrument."""
        # Get plans for this instrument
        instrument_plans = [
            p for p in self.active_plans
            if p.get('instrument_id') == instrument_id
        ]

        if not instrument_plans:
            return []

        # Get data store and calculate metrics
        data_store = self._get_data_store(instrument_id)
        calculator = self._get_metrics_calculator(instrument_id)

        # Get latest candle for metrics calculation
        bars_1m = data_store.get_bars('1m')
        if not bars_1m:
            return []

        latest_candle = bars_1m[-1]
        metrics = calculator.calculate_metrics(latest_candle, data_store, "1m", data_store.curr_book)

        # Build market context with proper time semantics
        # Note: Market time from data feeds is authoritative for all evaluations
        # Wall-clock time is only used as fallback when market time unavailable
        market_timestamp, latency = get_market_time_with_latency(data_store.last_update)

        # Log time semantics information
        if latency is not None:
            self.logger.debug(
                "Using market time for evaluation",
                instrument_id=instrument_id,
                market_time=market_timestamp.isoformat(),
                latency_ms=int(latency * 1000)
            )
        else:
            self.logger.warning(
                "No market time available - using wall-clock fallback",
                instrument_id=instrument_id,
                fallback_time=market_timestamp.isoformat()
            )

        market_context = MarketContext(
            last_price=data_store.last_price,
            timestamp=market_timestamp,
            atr=metrics.atr,
            natr_pct=metrics.natr_pct,
            rvol=metrics.rvol,
            last_closed_bar=latest_candle if latest_candle.is_closed else None,
            bar_range=latest_candle.high - latest_candle.low,
            curr_book=data_store.curr_book,
            prev_book=data_store.prev_book,
            pinbar_detected=metrics.pinbar is not None,
            ob_sweep_detected=metrics.ob_sweep_detected,
            ob_sweep_side=metrics.ob_sweep_side
        )

        # Process each plan
        signals = []
        for plan in instrument_plans:
            try:
                plan_signals = self._evaluate_single_plan(
                    plan, market_context, metrics
                )
                signals.extend(plan_signals)
            except DataQualityError as e:
                self.logger.warning(
                    "Data quality issue evaluating plan",
                    plan_id=plan.get('id'),
                    error=str(e),
                    error_type=type(e).__name__,
                    context=getattr(e, 'context', {})
                )
                # Continue with other plans
            except StateTransitionError as e:
                self.logger.error(
                    "State transition error evaluating plan",
                    plan_id=plan.get('id'),
                    error=str(e),
                    current_state=getattr(e, 'current_state', None),
                    attempted_transition=getattr(e, 'attempted_transition', None)
                )
                # Continue with other plans
            except Exception as e:
                self.logger.error(
                    "Unexpected error evaluating plan",
                    plan_id=plan.get('id'),
                    error=str(e),
                    error_type=type(e).__name__
                )

        return signals

    def _evaluate_single_plan(
        self,
        plan: dict[str, Any],
        market_context: MarketContext,
        metrics: "MetricsSnapshot"
    ) -> list[dict[str, Any]]:
        """Evaluate a single plan against current market conditions."""
        plan_id = plan.get('id')
        instrument_id = plan.get('instrument_id')
        entry_price = plan.get('entry_price')
        direction = plan.get('direction')

        # Validate plan data
        if not plan_id:
            raise MalformedDataError("Plan missing required 'id' field", raw_data=str(plan)[:100])
        if not instrument_id:
            raise MalformedDataError("Plan missing required 'instrument_id' field", raw_data=str(plan)[:100])
        if not entry_price:
            raise MalformedDataError("Plan missing required 'entry_price' field", raw_data=str(plan)[:100])
        if not direction:
            raise MalformedDataError("Plan missing required 'direction' field", raw_data=str(plan)[:100])

        # Validate market context
        if not market_context.last_price:
            raise MissingDataError("Market context missing last_price", data_type="market_context")
        if not market_context.atr:
            raise InsufficientDataError("Market context missing ATR for evaluation", required_count=1, available_count=0)

        # Load configuration with precedence
        plan_overrides = plan.get('extra_data', {}).get('breakout_params', {})
        config_dict = self.config_loader.merge_config(instrument_id, plan_overrides)

        # Extract breakout parameters
        breakout_config = BreakoutParameters(
            **config_dict.get('breakout', {})
        )

        # Log comprehensive gating decision context
        self.gating_logger.info(
            "Plan evaluation context",
            plan_id=plan_id,
            instrument_id=instrument_id,
            entry_price=entry_price,
            direction=direction,
            market_context={
                "last_price": market_context.last_price,
                "timestamp": market_context.timestamp.isoformat(),
                "price_distance_from_entry": abs(market_context.last_price - entry_price) if entry_price else None,
                "price_above_entry": market_context.last_price > entry_price if entry_price else None,
            },
            metrics_snapshot={
                "atr": market_context.atr,
                "natr_pct": market_context.natr_pct,
                "rvol": market_context.rvol,
                "bar_range": market_context.bar_range,
                "pinbar_detected": market_context.pinbar_detected,
                "ob_sweep_detected": market_context.ob_sweep_detected,
                "ob_sweep_side": market_context.ob_sweep_side,
                "composite_score": metrics.get_composite_score() if hasattr(metrics, 'get_composite_score') else None
            },
            breakout_config={
                "penetration_pct": breakout_config.penetration_pct,
                "penetration_natr_mult": breakout_config.penetration_natr_mult,
                "min_rvol": breakout_config.min_rvol,
                "min_break_range_atr": breakout_config.min_break_range_atr,
                "confirm_close": breakout_config.confirm_close,
                "confirm_time_ms": breakout_config.confirm_time_ms,
                "ob_sweep_check": breakout_config.ob_sweep_check,
                "allow_retest_entry": breakout_config.allow_retest_entry,
                "retest_band_pct": breakout_config.retest_band_pct,
                "fakeout_close_invalidate": breakout_config.fakeout_close_invalidate
            },
            event="plan_evaluation_start"
        )

        # Convert MarketContext to dict for compatibility
        market_dict = {
            'last_price': market_context.last_price,
            'timestamp': market_context.timestamp,
            'atr': market_context.atr,
            'natr_pct': market_context.natr_pct,
            'rvol': market_context.rvol,
            'last_closed_bar': market_context.last_closed_bar,
            'bar_range': market_context.bar_range,
            'curr_book': market_context.curr_book,
            'prev_book': market_context.prev_book,
            'pinbar_detected': market_context.pinbar_detected,
            'ob_sweep_detected': market_context.ob_sweep_detected,
            'ob_sweep_side': market_context.ob_sweep_side
        }

        # Use state manager to process the plan
        signals = state_manager.process_market_tick(
            active_plans=[plan],
            market_data=market_dict,
            metrics_by_plan={plan_id: metrics},
            config_by_plan={plan_id: breakout_config}
        )

        # Log evaluation results
        self.gating_logger.info(
            "Plan evaluation results",
            plan_id=plan_id,
            signals_generated=len(signals),
            signal_types=[signal.get('signal_type') for signal in signals] if signals else [],
            event="plan_evaluation_complete"
        )

        return signals

    def _get_data_store(self, instrument_id: str) -> InstrumentDataStore:
        """Get or create data store for instrument."""
        if instrument_id not in self.data_stores:
            self.data_stores[instrument_id] = InstrumentDataStore()
        return self.data_stores[instrument_id]

    def _get_metrics_calculator(self, instrument_id: str) -> MetricsCalculator:
        """Get or create metrics calculator for instrument."""
        if instrument_id not in self.metrics_calculators:
            self.metrics_calculators[instrument_id] = MetricsCalculator()
        return self.metrics_calculators[instrument_id]

    def get_plan_state(self, plan_id: str) -> Optional[dict[str, Any]]:
        """Get current state for a plan."""
        runtime_state = state_manager.get_plan_state(plan_id)
        if not runtime_state:
            return None

        return {
            'plan_id': plan_id,
            'state': runtime_state.state.value,
            'substate': runtime_state.substate.value,
            'break_ts': runtime_state.break_ts.isoformat() if runtime_state.break_ts else None,
            'armed_at': runtime_state.armed_at.isoformat() if runtime_state.armed_at else None,
            'triggered_at': runtime_state.triggered_at.isoformat() if runtime_state.triggered_at else None,
            'invalid_reason': runtime_state.invalid_reason.value if runtime_state.invalid_reason else None,
            'break_seen': runtime_state.break_seen,
            'break_confirmed': runtime_state.break_confirmed,
            'signal_emitted': runtime_state.signal_emitted
        }

    def get_active_plan_count(self) -> int:
        """Get count of active plans."""
        return len(self.active_plans)

    def get_runtime_stats(self) -> dict[str, Any]:
        """Get runtime statistics."""
        return {
            'active_plans': len(self.active_plans),
            'tracked_instruments': len(self.data_stores),
            'state_manager_active_plans': state_manager.get_active_plan_count()
        }
