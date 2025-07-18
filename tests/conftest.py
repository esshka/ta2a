"""Pytest configuration and shared fixtures."""

import pytest
from typing import Dict, Any
from datetime import datetime, timezone


@pytest.fixture
def sample_candlestick() -> Dict[str, Any]:
    """Sample candlestick data for testing."""
    return {
        "timestamp": int(datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000),
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 1000.0,
    }


@pytest.fixture
def sample_order_book() -> Dict[str, Any]:
    """Sample order book data for testing."""
    return {
        "bids": [
            [102.5, 100.0, 0, 0],
            [102.0, 200.0, 0, 0],
            [101.5, 150.0, 0, 0],
        ],
        "asks": [
            [103.0, 80.0, 0, 0],
            [103.5, 120.0, 0, 0],
            [104.0, 90.0, 0, 0],
        ],
    }


@pytest.fixture
def sample_trading_plan() -> Dict[str, Any]:
    """Sample trading plan for testing."""
    return {
        "id": "test-plan-001",
        "instrument_id": "BTC-USD-SWAP",
        "direction": "long",
        "entry_type": "breakout",
        "entry_price": 50000.0,
        "stop_loss": 48000.0,
        "take_profit": 55000.0,
        "quantity": 0.1,
        "extra_data": {
            "invalidation_conditions": {
                "time_expiry": "2023-12-31T23:59:59Z",
                "price_lower_limit": 45000.0,
                "price_upper_limit": 60000.0,
            },
            "breakout_params": {
                "penetration_pct": 0.05,
                "min_rvol": 1.5,
                "confirm_close": True,
            },
        },
    }