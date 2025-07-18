"""Tests for signal persistence layer."""

import pytest
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import patch, Mock

from ta2_app.persistence.signal_store import SignalStore, StoredSignal


class TestStoredSignal:
    """Test StoredSignal dataclass."""
    
    def test_stored_signal_creation(self):
        """Test creating a StoredSignal instance."""
        signal_data = {
            "plan_id": "test-plan",
            "state": "triggered",
            "last_price": 50000.0
        }
        
        stored_signal = StoredSignal(
            id=1,
            plan_id="test-plan",
            state="triggered",
            protocol_version="1.0",
            timestamp="2023-01-01T12:00:00Z",
            signal_data=signal_data,
            created_at="2023-01-01T12:00:00Z"
        )
        
        assert stored_signal.id == 1
        assert stored_signal.plan_id == "test-plan"
        assert stored_signal.state == "triggered"
        assert stored_signal.protocol_version == "1.0"
        assert stored_signal.signal_data == signal_data
        assert stored_signal.delivery_attempts == 0
        assert stored_signal.last_delivery_attempt is None
        assert stored_signal.delivery_status is None

    def test_stored_signal_with_delivery_info(self):
        """Test StoredSignal with delivery information."""
        stored_signal = StoredSignal(
            id=1,
            plan_id="test-plan",
            state="triggered",
            protocol_version="1.0",
            timestamp="2023-01-01T12:00:00Z",
            signal_data={},
            created_at="2023-01-01T12:00:00Z",
            delivery_attempts=3,
            last_delivery_attempt="2023-01-01T12:05:00Z",
            delivery_status="success"
        )
        
        assert stored_signal.delivery_attempts == 3
        assert stored_signal.last_delivery_attempt == "2023-01-01T12:05:00Z"
        assert stored_signal.delivery_status == "success"


class TestSignalStore:
    """Test SignalStore class."""
    
    def setup_method(self):
        """Setup test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_signals.db")
        self.store = SignalStore(self.db_path)
    
    def teardown_method(self):
        """Cleanup test database."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_init_database(self):
        """Test database initialization."""
        # Database file should exist
        assert Path(self.db_path).exists()
        
        # Should be able to connect and query
        with self.store._get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            assert "signals" in tables
    
    def test_store_signal_basic(self):
        """Test storing a basic signal."""
        signal_data = {
            "plan_id": "test-plan-001",
            "state": "triggered",
            "last_price": 50000.0,
            "timestamp": "2023-01-01T12:00:00Z"
        }
        
        signal_id = self.store.store_signal(signal_data)
        
        assert signal_id > 0
        
        # Verify signal was stored
        with self.store._get_connection() as conn:
            cursor = conn.execute(
                "SELECT plan_id, state, signal_data FROM signals WHERE id = ?",
                (signal_id,)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "test-plan-001"
            assert row[1] == "triggered"
            stored_data = json.loads(row[2])
            assert stored_data["last_price"] == 50000.0
    
    def test_store_signal_with_protocol_version(self):
        """Test storing signal with specific protocol version."""
        signal_data = {
            "plan_id": "test-plan-002",
            "state": "invalid",
            "protocol_version": "2.0",
            "timestamp": "2023-01-01T12:00:00Z"
        }
        
        signal_id = self.store.store_signal(signal_data)
        
        # Verify protocol version was stored
        with self.store._get_connection() as conn:
            cursor = conn.execute(
                "SELECT protocol_version FROM signals WHERE id = ?",
                (signal_id,)
            )
            row = cursor.fetchone()
            assert row[0] == "2.0"
    
    def test_store_signal_error_handling(self):
        """Test store_signal error handling."""
        # Test with invalid signal data
        with patch.object(self.store, '_get_connection') as mock_conn:
            mock_conn.side_effect = Exception("Database error")
            
            signal_data = {"plan_id": "test-plan", "state": "triggered"}
            result = self.store.store_signal(signal_data)
            
            assert result is None
    
    def test_get_signal_by_id(self):
        """Test retrieving signal by ID."""
        signal_data = {
            "plan_id": "test-plan-003",
            "state": "triggered",
            "last_price": 52000.0,
            "timestamp": "2023-01-01T12:00:00Z"
        }
        
        signal_id = self.store.store_signal(signal_data)
        
        # Retrieve the signal
        stored_signal = self.store.get_signal(signal_id)
        
        assert stored_signal is not None
        assert stored_signal.id == signal_id
        assert stored_signal.plan_id == "test-plan-003"
        assert stored_signal.state == "triggered"
        assert stored_signal.signal_data["last_price"] == 52000.0
    
    def test_get_signal_nonexistent(self):
        """Test retrieving non-existent signal."""
        result = self.store.get_signal(99999)
        assert result is None
    
    def test_get_signal_error_handling(self):
        """Test get_signal error handling."""
        with patch.object(self.store, '_get_connection') as mock_conn:
            mock_conn.side_effect = Exception("Database error")
            
            result = self.store.get_signal(1)
            assert result is None
    
    def test_get_signals_by_plan(self):
        """Test retrieving signals by plan ID."""
        # Store multiple signals for the same plan
        plan_id = "test-plan-004"
        for i in range(3):
            signal_data = {
                "plan_id": plan_id,
                "state": f"state-{i}",
                "sequence": i,
                "timestamp": f"2023-01-01T12:0{i}:00Z"
            }
            self.store.store_signal(signal_data)
        
        # Store signal for different plan
        other_signal_data = {
            "plan_id": "other-plan",
            "state": "triggered",
            "timestamp": "2023-01-01T12:00:00Z"
        }
        self.store.store_signal(other_signal_data)
        
        # Retrieve signals for specific plan
        signals = self.store.get_signals_by_plan(plan_id)
        
        assert len(signals) == 3
        for signal in signals:
            assert signal.plan_id == plan_id
        
        # Should be ordered by ID (creation order)
        assert signals[0].signal_data["sequence"] == 0
        assert signals[1].signal_data["sequence"] == 1
        assert signals[2].signal_data["sequence"] == 2
    
    def test_get_signals_by_time_range(self):
        """Test retrieving signals by time range."""
        # Store signals with different timestamps
        timestamps = ["2023-01-01T10:00:00Z", "2023-01-01T12:00:00Z", "2023-01-01T14:00:00Z"]
        for i, timestamp in enumerate(timestamps):
            signal_data = {
                "plan_id": f"plan-{i}",
                "state": "triggered",
                "timestamp": timestamp
            }
            self.store.store_signal(signal_data)
        
        # Get signals in range
        signals = self.store.get_signals_by_time_range(
            "2023-01-01T11:00:00Z", 
            "2023-01-01T13:00:00Z"
        )
        
        assert len(signals) == 1
        assert signals[0].timestamp == "2023-01-01T12:00:00Z"
    
    def test_get_signals_by_plan_empty(self):
        """Test retrieving signals for non-existent plan."""
        signals = self.store.get_signals_by_plan("nonexistent-plan")
        assert len(signals) == 0
    
    def test_get_signals_by_state(self):
        """Test retrieving signals by state."""
        # Store signals with different states
        states = ["triggered", "invalid", "triggered", "expired"]
        for i, state in enumerate(states):
            signal_data = {
                "plan_id": f"plan-{i}",
                "state": state,
                "timestamp": f"2023-01-01T12:0{i}:00Z"
            }
            self.store.store_signal(signal_data)
        
        # Retrieve triggered signals
        triggered_signals = self.store.get_signals_by_state("triggered")
        
        assert len(triggered_signals) == 2
        for signal in triggered_signals:
            assert signal.state == "triggered"
    
    def test_get_signals_by_state_with_limit(self):
        """Test retrieving signals by state with limit."""
        # Store multiple triggered signals
        for i in range(4):
            signal_data = {
                "plan_id": f"plan-{i}",
                "state": "triggered",
                "timestamp": f"2023-01-01T12:0{i}:00Z"
            }
            self.store.store_signal(signal_data)
        
        # Get with limit
        signals = self.store.get_signals_by_state("triggered", limit=2)
        
        assert len(signals) == 2
    
    def test_store_signals_batch(self):
        """Test storing multiple signals in batch."""
        signals_data = [
            {
                "plan_id": "batch-plan-1",
                "state": "triggered",
                "timestamp": "2023-01-01T12:00:00Z"
            },
            {
                "plan_id": "batch-plan-2",
                "state": "invalid",
                "timestamp": "2023-01-01T12:01:00Z"
            }
        ]
        
        signal_ids = self.store.store_signals(signals_data)
        
        assert len(signal_ids) == 2
        assert all(sid is not None for sid in signal_ids)
        
        # Verify signals were stored
        for signal_id in signal_ids:
            stored_signal = self.store.get_signal(signal_id)
            assert stored_signal is not None
    
    def test_update_delivery_status(self):
        """Test updating delivery status."""
        signal_data = {
            "plan_id": "test-plan-006",
            "state": "triggered",
            "timestamp": "2023-01-01T12:00:00Z"
        }
        
        signal_id = self.store.store_signal(signal_data)
        
        # Update delivery status
        success = self.store.update_delivery_status(signal_id, "success")
        
        assert success is True
        
        # Verify update
        stored_signal = self.store.get_signal(signal_id)
        assert stored_signal.delivery_attempts == 1
        assert stored_signal.delivery_status == "success"
        assert stored_signal.last_delivery_attempt is not None
    
    def test_update_delivery_status_multiple_attempts(self):
        """Test updating delivery status with multiple attempts."""
        signal_data = {
            "plan_id": "test-plan-007",
            "state": "triggered",
            "timestamp": "2023-01-01T12:00:00Z"
        }
        
        signal_id = self.store.store_signal(signal_data)
        
        # Multiple delivery attempts
        for i in range(3):
            status = "failed" if i < 2 else "success"
            self.store.update_delivery_status(signal_id, status)
        
        # Verify final state
        stored_signal = self.store.get_signal(signal_id)
        assert stored_signal.delivery_attempts == 3
        assert stored_signal.delivery_status == "success"
    
    def test_update_delivery_status_nonexistent(self):
        """Test updating delivery status for non-existent signal."""
        success = self.store.update_delivery_status(99999, "success")
        assert success is False
    
    def test_update_delivery_status_error_handling(self):
        """Test update_delivery_status error handling."""
        with patch.object(self.store, '_get_connection') as mock_conn:
            mock_conn.side_effect = Exception("Database error")
            
            success = self.store.update_delivery_status(1, "success")
            assert success is False
    
    def test_get_stats(self):
        """Test getting database statistics."""
        # Store signals with different states
        test_data = [
            ("plan-1", "triggered"),
            ("plan-2", "invalid"),
            ("plan-3", "triggered"),
            ("plan-4", "expired"),
            ("plan-5", "triggered")
        ]
        
        for plan_id, state in test_data:
            signal_data = {
                "plan_id": plan_id,
                "state": state,
                "timestamp": "2023-01-01T12:00:00Z"
            }
            self.store.store_signal(signal_data)
        
        # Get stats
        stats = self.store.get_stats()
        
        assert stats["total_signals"] == 5
        assert stats["signals_by_state"]["triggered"] == 3
        assert stats["signals_by_state"]["invalid"] == 1
        assert stats["signals_by_state"]["expired"] == 1
        assert "recent_24h" in stats
    
    def test_get_stats_no_signals(self):
        """Test getting stats with no signals."""
        stats = self.store.get_stats()
        
        assert stats["total_signals"] == 0
        assert stats["signals_by_state"] == {}
        assert stats["recent_24h"] == 0
    
    def test_cleanup_old_signals(self):
        """Test cleaning up old signals."""
        # Store signals
        for i in range(5):
            signal_data = {
                "plan_id": f"plan-{i}",
                "state": "triggered",
                "timestamp": "2023-01-01T12:00:00Z"
            }
            self.store.store_signal(signal_data)
        
        # Get initial count
        initial_stats = self.store.get_stats()
        assert initial_stats["total_signals"] == 5
        
        # Cleanup signals older than 1 day (should delete all)
        deleted_count = self.store.cleanup_old_signals(older_than_days=1)
        
        assert deleted_count >= 0  # At least some signals should be deleted
        
        # Verify cleanup worked
        final_stats = self.store.get_stats()
        assert final_stats["total_signals"] < initial_stats["total_signals"]
    
    def test_cleanup_old_signals_error_handling(self):
        """Test cleanup_old_signals error handling."""
        with patch.object(self.store, '_get_connection') as mock_conn:
            mock_conn.side_effect = Exception("Database error")
            
            deleted_count = self.store.cleanup_old_signals(older_than_days=30)
            assert deleted_count == 0
    
    def test_get_connection_context_manager(self):
        """Test connection context manager."""
        with self.store._get_connection() as conn:
            assert conn is not None
            # Should be able to execute queries
            cursor = conn.execute("SELECT 1")
            result = cursor.fetchone()
            assert result[0] == 1
    
    def test_thread_safety(self):
        """Test thread safety of signal store operations."""
        import threading
        import time
        
        results = []
        errors = []
        
        def store_signal_thread(thread_id):
            try:
                for i in range(10):
                    signal_data = {
                        "plan_id": f"thread-{thread_id}-plan-{i}",
                        "state": "triggered",
                        "timestamp": f"2023-01-01T12:0{i}:00Z"
                    }
                    signal_id = self.store.store_signal(signal_data)
                    results.append(signal_id)
                    time.sleep(0.001)  # Small delay to increase chance of race conditions
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=store_signal_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 50  # 5 threads * 10 signals each
        assert len(set(results)) == 50  # All signal IDs should be unique
        
        # Verify all signals were stored
        final_stats = self.store.get_stats()
        assert final_stats["total_signals"] == 50
    
    def test_signal_store_idempotency_database_level(self):
        """Test database-level duplicate prevention."""
        # Same signal data should not create duplicate entries
        signal_data = {
            "plan_id": "test-plan",
            "state": "triggered",
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50000.0
        }
        
        # First storage
        signal_id1 = self.store.store_signal(signal_data)
        assert signal_id1 is not None
        
        # Second storage - should replace due to UNIQUE constraint
        signal_id2 = self.store.store_signal(signal_data)
        assert signal_id2 is not None
        
        # Should have same ID due to INSERT OR REPLACE
        assert signal_id1 == signal_id2
        
        # Verify only one signal exists
        signals = self.store.get_signals_by_plan("test-plan")
        assert len(signals) == 1
        assert signals[0].state == "triggered"
    
    def test_signal_store_duplicate_check_method(self):
        """Test the is_signal_duplicate method."""
        # Initially no duplicates
        assert not self.store.is_signal_duplicate(
            "test-plan", "triggered", "2023-01-01T12:00:00Z"
        )
        
        # Store a signal
        signal_data = {
            "plan_id": "test-plan",
            "state": "triggered",
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50000.0
        }
        self.store.store_signal(signal_data)
        
        # Now should detect duplicate
        assert self.store.is_signal_duplicate(
            "test-plan", "triggered", "2023-01-01T12:00:00Z"
        )
        
        # Different timestamp should not be duplicate
        assert not self.store.is_signal_duplicate(
            "test-plan", "triggered", "2023-01-01T12:01:00Z"
        )
        
        # Different plan should not be duplicate
        assert not self.store.is_signal_duplicate(
            "test-plan-2", "triggered", "2023-01-01T12:00:00Z"
        )
        
        # Different state should not be duplicate
        assert not self.store.is_signal_duplicate(
            "test-plan", "invalid", "2023-01-01T12:00:00Z"
        )
    
    def test_signal_store_enhanced_unique_constraint(self):
        """Test enhanced unique constraint with timestamp."""
        # Same plan and state but different timestamps should be allowed
        signal_data1 = {
            "plan_id": "test-plan",
            "state": "triggered",
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50000.0
        }
        
        signal_data2 = {
            "plan_id": "test-plan",
            "state": "triggered",
            "timestamp": "2023-01-01T12:01:00Z",
            "last_price": 51000.0
        }
        
        # Both should be stored successfully
        signal_id1 = self.store.store_signal(signal_data1)
        signal_id2 = self.store.store_signal(signal_data2)
        
        assert signal_id1 is not None
        assert signal_id2 is not None
        assert signal_id1 != signal_id2
        
        # Verify both signals exist
        signals = self.store.get_signals_by_plan("test-plan")
        assert len(signals) == 2
        
        # Verify unique constraint prevents exact duplicates
        signal_id3 = self.store.store_signal(signal_data1)  # Same as first
        assert signal_id3 == signal_id1  # Should replace, not create new
        
        # Still only 2 signals
        signals = self.store.get_signals_by_plan("test-plan")
        assert len(signals) == 2
    
    def test_signal_store_hash_generation(self):
        """Test signal hash generation for deduplication."""
        # Test hash generation produces consistent results
        signal_data = {
            "plan_id": "test-plan",
            "state": "triggered",
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50000.0
        }
        
        hash1 = self.store._generate_signal_hash(signal_data)
        hash2 = self.store._generate_signal_hash(signal_data)
        
        assert hash1 == hash2
        assert len(hash1) == 16  # Hash is truncated to 16 chars
        
        # Different data should produce different hashes
        signal_data2 = signal_data.copy()
        signal_data2["timestamp"] = "2023-01-01T12:01:00Z"
        hash3 = self.store._generate_signal_hash(signal_data2)
        
        assert hash1 != hash3
    
    def test_signal_store_concurrent_duplicate_prevention(self):
        """Test concurrent access doesn't create duplicates."""
        import threading
        import time
        
        # Same signal data for all threads
        signal_data = {
            "plan_id": "test-plan",
            "state": "triggered",
            "timestamp": "2023-01-01T12:00:00Z",
            "last_price": 50000.0
        }
        
        results = []
        errors = []
        
        def store_signal_thread():
            try:
                signal_id = self.store.store_signal(signal_data)
                results.append(signal_id)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads trying to store the same signal
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=store_signal_thread)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10  # All threads should get a result
        
        # All should have same signal ID due to INSERT OR REPLACE
        unique_ids = set(results)
        assert len(unique_ids) == 1  # Only one unique ID
        
        # Verify only one signal exists in database
        signals = self.store.get_signals_by_plan("test-plan")
        assert len(signals) == 1
        assert signals[0].state == "triggered"