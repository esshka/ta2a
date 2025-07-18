"""
Tests for time utilities and time semantics handling.

Verifies that market time is used correctly, fallback strategies work,
and latency monitoring functions as expected.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from ta2_app.utils.time import (
    get_market_time, ensure_market_time, calculate_latency,
    get_market_time_with_latency, validate_market_time,
    format_market_time, time_elapsed_seconds
)


class TestGetMarketTime:
    """Test get_market_time function."""
    
    def test_uses_market_time_when_available(self):
        """Should use market timestamp when provided."""
        market_ts = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = get_market_time(market_ts)
        assert result == market_ts
    
    def test_falls_back_to_wall_clock_time(self):
        """Should fall back to wall-clock time when market time is None."""
        with patch('ta2_app.utils.time.datetime') as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            result = get_market_time(None)
            assert result == mock_now
            mock_datetime.now.assert_called_once_with(timezone.utc)


class TestEnsureMarketTime:
    """Test ensure_market_time function."""
    
    def test_prefers_market_time(self):
        """Should prefer market time over fallback."""
        market_ts = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        fallback_ts = datetime(2023, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        
        result = ensure_market_time(market_ts, fallback_ts)
        assert result == market_ts
    
    def test_uses_fallback_when_market_none(self):
        """Should use fallback when market time is None."""
        fallback_ts = datetime(2023, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        
        result = ensure_market_time(None, fallback_ts)
        assert result == fallback_ts
    
    def test_uses_wall_clock_when_both_none(self):
        """Should use wall-clock time when both are None."""
        with patch('ta2_app.utils.time.datetime') as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            result = ensure_market_time(None, None)
            assert result == mock_now


class TestCalculateLatency:
    """Test calculate_latency function."""
    
    def test_positive_latency(self):
        """Should return positive latency when wall-clock is newer."""
        market_ts = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        wall_clock_ts = datetime(2023, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
        
        result = calculate_latency(market_ts, wall_clock_ts)
        assert result == 1.0
    
    def test_negative_latency(self):
        """Should return negative latency when market time is newer."""
        market_ts = datetime(2023, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
        wall_clock_ts = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        result = calculate_latency(market_ts, wall_clock_ts)
        assert result == -1.0
    
    def test_uses_current_time_when_none(self):
        """Should use current time when wall_clock_ts is None."""
        market_ts = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        with patch('ta2_app.utils.time.datetime') as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 2, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            result = calculate_latency(market_ts, None)
            assert result == 2.0


class TestGetMarketTimeWithLatency:
    """Test get_market_time_with_latency function."""
    
    def test_returns_market_time_with_latency(self):
        """Should return market time and latency when available."""
        market_ts = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        with patch('ta2_app.utils.time.datetime') as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            time_result, latency = get_market_time_with_latency(market_ts)
            assert time_result == market_ts
            assert latency == 1.0
    
    def test_returns_wall_clock_time_with_none_latency(self):
        """Should return wall-clock time and None latency when market time unavailable."""
        with patch('ta2_app.utils.time.datetime') as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            time_result, latency = get_market_time_with_latency(None)
            assert time_result == mock_now
            assert latency is None


class TestValidateMarketTime:
    """Test validate_market_time function."""
    
    def test_valid_recent_timestamp(self):
        """Should accept recent timestamps."""
        recent_ts = datetime.now(timezone.utc) - timedelta(seconds=60)
        assert validate_market_time(recent_ts) is True
    
    def test_rejects_old_timestamp(self):
        """Should reject timestamps older than max_age."""
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=400)
        assert validate_market_time(old_ts, max_age_seconds=300) is False
    
    def test_rejects_future_timestamp(self):
        """Should reject timestamps too far in the future."""
        future_ts = datetime.now(timezone.utc) + timedelta(seconds=60)
        assert validate_market_time(future_ts) is False
    
    def test_allows_small_clock_skew(self):
        """Should allow small clock skew (30 seconds)."""
        future_ts = datetime.now(timezone.utc) + timedelta(seconds=15)
        assert validate_market_time(future_ts) is True


class TestFormatMarketTime:
    """Test format_market_time function."""
    
    def test_formats_to_isoformat(self):
        """Should format timestamp to ISO8601 format."""
        ts = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = format_market_time(ts)
        assert result == "2023-01-01T12:00:00+00:00"


class TestTimeElapsedSeconds:
    """Test time_elapsed_seconds function."""
    
    def test_calculates_elapsed_time(self):
        """Should calculate elapsed time between timestamps."""
        start = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        
        result = time_elapsed_seconds(start, end)
        assert result == 5.0
    
    def test_uses_current_time_when_end_none(self):
        """Should use current time when end_time is None."""
        start = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        with patch('ta2_app.utils.time.datetime') as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 3, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            
            result = time_elapsed_seconds(start, None)
            assert result == 3.0