"""Integration tests for idempotent signal emission across the full pipeline."""

import pytest
import tempfile
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any, List

from ta2_app.engine import BreakoutEvaluationEngine
from ta2_app.state.runtime import StateManager, SignalEmitter
from ta2_app.persistence.signal_store import SignalStore
from ta2_app.config.signal_delivery import SignalDeliveryConfig
from ta2_app.state.models import BreakoutParameters


class TestFullPipelineIdempotency:
    """Test idempotency across the full evaluation pipeline."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_signals.db")
        
        # Create signal store
        self.signal_store = SignalStore(db_path=self.db_path)
        
        # Create signal emitter with test delivery config
        delivery_config = SignalDeliveryConfig(
            enabled=True,
            destinations=[]  # No actual delivery for tests
        )
        self.signal_emitter = SignalEmitter(delivery_config=delivery_config)
        
        # Create state manager
        self.state_manager = StateManager()
        self.state_manager.signal_emitter = self.signal_emitter
        
        # Create evaluation engine
        self.engine = BreakoutEvaluationEngine()
        
        # Sample trading plan
        self.sample_plan = {
            "id": "test-plan-1",
            "instrument_id": "BTC-USD-SWAP",
            "direction": "long",
            "entry_type": "breakout",
            "entry_price": 50000.0,
            "extra_data": {
                "breakout_params": {
                    "penetration_pct": 0.05,
                    "min_rvol": 1.5
                }
            }
        }
        
        # Sample market data
        self.sample_candlestick = {
            "timestamp": "2023-01-01T12:00:00Z",
            "open": 49900.0,
            "high": 50100.0,
            "low": 49800.0,
            "close": 50050.0,
            "volume": 1000.0
        }
        
        self.sample_order_book = {
            "timestamp": "2023-01-01T12:00:00Z",
            "asks": [[50100.0, 100.0, 0, 0], [50200.0, 200.0, 0, 0]],
            "bids": [[49900.0, 150.0, 0, 0], [49800.0, 250.0, 0, 0]]
        }
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_state_transition_idempotency(self):
        """Test that state transitions don't emit duplicate signals."""
        # Initialize plan state
        plan_id = self.sample_plan["id"]
        
        # Mock metrics for consistent results
        mock_metrics = Mock()
        mock_metrics.rvol = 2.0
        mock_metrics.natr_pct = 0.5
        mock_metrics.atr = 100.0
        mock_metrics.pinbar = None
        mock_metrics.ob_sweep_detected = False
        mock_metrics.ob_sweep_side = None
        mock_metrics.ob_imbalance_long = 0.6
        mock_metrics.ob_imbalance_short = 0.4
        
        # Create triggering market data
        triggering_data = {
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50100.0,  # Above entry price
            "candlestick": self.sample_candlestick,
            "order_book": self.sample_order_book
        }
        
        # Process same market tick multiple times
        emitted_signals = []
        
        with patch.object(self.engine, '_calculate_metrics', return_value=mock_metrics):
            # First processing - should emit signal
            signals1 = self.state_manager.process_market_tick(
                [self.sample_plan], triggering_data, {plan_id: mock_metrics}, 
                {plan_id: BreakoutParameters()}
            )
            emitted_signals.extend(signals1)
            
            # Second processing - should NOT emit duplicate
            signals2 = self.state_manager.process_market_tick(
                [self.sample_plan], triggering_data, {plan_id: mock_metrics}, 
                {plan_id: BreakoutParameters()}
            )
            emitted_signals.extend(signals2)
            
            # Third processing - should NOT emit duplicate
            signals3 = self.state_manager.process_market_tick(
                [self.sample_plan], triggering_data, {plan_id: mock_metrics}, 
                {plan_id: BreakoutParameters()}
            )
            emitted_signals.extend(signals3)
        
        # Should only have one signal emitted
        assert len(emitted_signals) == 1
        assert emitted_signals[0]["plan_id"] == plan_id
        assert emitted_signals[0]["state"] == "triggered"
        
        # Verify only one signal in database
        stored_signals = self.signal_store.get_signals_by_plan(plan_id)
        assert len(stored_signals) == 1
    
    def test_delivery_retry_idempotency(self):
        """Test that delivery retries don't create duplicate signals."""
        # Create a signal that will trigger delivery
        signal_data = {
            "plan_id": "test-plan",
            "state": "triggered",
            "protocol_version": "breakout-v1",
            "runtime": {
                "armed_at": "2023-01-01T11:59:00Z",
                "triggered_at": "2023-01-01T12:00:00Z"
            },
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50100.0,
            "metrics": {
                "rvol": 2.0,
                "natr_pct": 0.5,
                "atr": 100.0,
                "pinbar": False,
                "pinbar_type": None,
                "ob_sweep_detected": False,
                "ob_sweep_side": None,
                "ob_imbalance_long": 0.6,
                "ob_imbalance_short": 0.4
            },
            "strength_score": 75.0
        }
        
        # Mock delivery handler to simulate retry scenarios
        mock_handler = Mock()
        mock_handler.deliver.return_value = Mock(success=True, retryable=False)
        
        # Replace delivery handlers
        self.signal_emitter.delivery_handlers = {"test_handler": mock_handler}
        
        # Emit signal multiple times (simulating retry scenarios)
        results = []
        for i in range(3):
            result = self.signal_emitter.emit_signal(
                signal_data["plan_id"], signal_data, None
            )
            results.append(result)
        
        # Only first emission should succeed
        assert len([r for r in results if r != {}]) == 1
        assert len([r for r in results if r == {}]) == 2
        
        # Verify delivery was only called once
        assert mock_handler.deliver.call_count == 1
        
        # Verify only one signal in database
        stored_signals = self.signal_store.get_signals_by_plan("test-plan")
        assert len(stored_signals) == 1
    
    def test_concurrent_pipeline_processing(self):
        """Test pipeline idempotency under concurrent processing."""
        plan_id = self.sample_plan["id"]
        
        # Mock metrics
        mock_metrics = Mock()
        mock_metrics.rvol = 2.0
        mock_metrics.natr_pct = 0.5
        mock_metrics.atr = 100.0
        mock_metrics.pinbar = None
        mock_metrics.ob_sweep_detected = False
        mock_metrics.ob_sweep_side = None
        mock_metrics.ob_imbalance_long = 0.6
        mock_metrics.ob_imbalance_short = 0.4
        
        # Triggering market data
        triggering_data = {
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50100.0,
            "candlestick": self.sample_candlestick,
            "order_book": self.sample_order_book
        }
        
        all_signals = []
        errors = []
        
        def process_market_tick_worker():
            try:
                with patch.object(self.engine, '_calculate_metrics', return_value=mock_metrics):
                    signals = self.state_manager.process_market_tick(
                        [self.sample_plan], triggering_data, {plan_id: mock_metrics}, 
                        {plan_id: BreakoutParameters()}
                    )
                    all_signals.extend(signals)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads processing the same market tick
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=process_market_tick_worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Should only have one signal emitted despite concurrent processing
        assert len(all_signals) == 1
        assert all_signals[0]["plan_id"] == plan_id
        assert all_signals[0]["state"] == "triggered"
        
        # Verify only one signal in database
        stored_signals = self.signal_store.get_signals_by_plan(plan_id)
        assert len(stored_signals) == 1
    
    def test_cross_session_idempotency(self):
        """Test idempotency across different engine sessions."""
        plan_id = self.sample_plan["id"]
        
        # Mock metrics
        mock_metrics = Mock()
        mock_metrics.rvol = 2.0
        mock_metrics.natr_pct = 0.5
        mock_metrics.atr = 100.0
        mock_metrics.pinbar = None
        mock_metrics.ob_sweep_detected = False
        mock_metrics.ob_sweep_side = None
        mock_metrics.ob_imbalance_long = 0.6
        mock_metrics.ob_imbalance_short = 0.4
        
        # Triggering market data
        triggering_data = {
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50100.0,
            "candlestick": self.sample_candlestick,
            "order_book": self.sample_order_book
        }
        
        # First session - emit signal
        with patch.object(self.engine, '_calculate_metrics', return_value=mock_metrics):
            signals1 = self.state_manager.process_market_tick(
                [self.sample_plan], triggering_data, {plan_id: mock_metrics}, 
                {plan_id: BreakoutParameters()}
            )
        
        assert len(signals1) == 1
        
        # Create new state manager (simulating new session)
        new_state_manager = StateManager()
        new_signal_emitter = SignalEmitter(delivery_config=SignalDeliveryConfig(
            enabled=True, destinations=[]
        ))
        new_state_manager.signal_emitter = new_signal_emitter
        
        # Second session - should not emit duplicate
        with patch.object(self.engine, '_calculate_metrics', return_value=mock_metrics):
            signals2 = new_state_manager.process_market_tick(
                [self.sample_plan], triggering_data, {plan_id: mock_metrics}, 
                {plan_id: BreakoutParameters()}
            )
        
        # Should not emit duplicate (relies on database constraint)
        assert len(signals2) == 0
        
        # Verify only one signal in database
        stored_signals = self.signal_store.get_signals_by_plan(plan_id)
        assert len(stored_signals) == 1
    
    def test_multiple_plans_idempotency_isolation(self):
        """Test that idempotency is properly isolated between different plans."""
        # Create multiple plans
        plan1 = self.sample_plan.copy()
        plan1["id"] = "test-plan-1"
        
        plan2 = self.sample_plan.copy()
        plan2["id"] = "test-plan-2"
        
        plan3 = self.sample_plan.copy()
        plan3["id"] = "test-plan-3"
        
        plans = [plan1, plan2, plan3]
        
        # Mock metrics
        mock_metrics = Mock()
        mock_metrics.rvol = 2.0
        mock_metrics.natr_pct = 0.5
        mock_metrics.atr = 100.0
        mock_metrics.pinbar = None
        mock_metrics.ob_sweep_detected = False
        mock_metrics.ob_sweep_side = None
        mock_metrics.ob_imbalance_long = 0.6
        mock_metrics.ob_imbalance_short = 0.4
        
        # Triggering market data
        triggering_data = {
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50100.0,
            "candlestick": self.sample_candlestick,
            "order_book": self.sample_order_book
        }
        
        # Create metrics and config for all plans
        metrics_by_plan = {plan["id"]: mock_metrics for plan in plans}
        config_by_plan = {plan["id"]: BreakoutParameters() for plan in plans}
        
        # Process multiple times
        all_signals = []
        
        with patch.object(self.engine, '_calculate_metrics', return_value=mock_metrics):
            for i in range(3):
                signals = self.state_manager.process_market_tick(
                    plans, triggering_data, metrics_by_plan, config_by_plan
                )
                all_signals.extend(signals)
        
        # Should have exactly 3 signals (one per plan, no duplicates)
        assert len(all_signals) == 3
        
        # Verify signal isolation
        plan_ids = [s["plan_id"] for s in all_signals]
        assert "test-plan-1" in plan_ids
        assert "test-plan-2" in plan_ids
        assert "test-plan-3" in plan_ids
        
        # Verify database storage
        for plan_id in ["test-plan-1", "test-plan-2", "test-plan-3"]:
            stored_signals = self.signal_store.get_signals_by_plan(plan_id)
            assert len(stored_signals) == 1
            assert stored_signals[0].state == "triggered"
    
    def test_timestamp_based_duplicate_prevention(self):
        """Test that signals with same plan/state but different timestamps are allowed."""
        plan_id = self.sample_plan["id"]
        
        # Mock metrics
        mock_metrics = Mock()
        mock_metrics.rvol = 2.0
        mock_metrics.natr_pct = 0.5
        mock_metrics.atr = 100.0
        mock_metrics.pinbar = None
        mock_metrics.ob_sweep_detected = False
        mock_metrics.ob_sweep_side = None
        mock_metrics.ob_imbalance_long = 0.6
        mock_metrics.ob_imbalance_short = 0.4
        
        # First triggering data
        triggering_data1 = {
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50100.0,
            "candlestick": self.sample_candlestick,
            "order_book": self.sample_order_book
        }
        
        # Second triggering data (different timestamp)
        triggering_data2 = {
            "timestamp": "2023-01-01T12:01:00Z",
            "last_price": 50100.0,
            "candlestick": self.sample_candlestick,
            "order_book": self.sample_order_book
        }
        
        # Clear plan state to allow multiple triggerings
        self.state_manager.clear_plan_state(plan_id)
        
        # Process both timestamps
        all_signals = []
        
        with patch.object(self.engine, '_calculate_metrics', return_value=mock_metrics):
            # First timestamp
            signals1 = self.state_manager.process_market_tick(
                [self.sample_plan], triggering_data1, {plan_id: mock_metrics}, 
                {plan_id: BreakoutParameters()}
            )
            all_signals.extend(signals1)
            
            # Reset plan state to allow second triggering
            self.state_manager.clear_plan_state(plan_id)
            
            # Second timestamp
            signals2 = self.state_manager.process_market_tick(
                [self.sample_plan], triggering_data2, {plan_id: mock_metrics}, 
                {plan_id: BreakoutParameters()}
            )
            all_signals.extend(signals2)
        
        # Should have two signals (different timestamps)
        assert len(all_signals) == 2
        assert all_signals[0]["timestamp"] != all_signals[1]["timestamp"]
        
        # Verify both signals in database
        stored_signals = self.signal_store.get_signals_by_plan(plan_id)
        assert len(stored_signals) == 2
        
        # Verify different timestamps
        timestamps = [s.timestamp for s in stored_signals]
        assert len(set(timestamps)) == 2  # Both timestamps should be unique