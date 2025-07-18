"""Integration tests for the full evaluation pipeline."""

import pytest
from typing import Dict, Any

from ta2_app.engine import BreakoutEvaluationEngine


@pytest.mark.integration
class TestFullPipeline:
    """Integration tests for the complete evaluation pipeline."""

    def test_full_pipeline_basic_flow(
        self, sample_candlestick: Dict[str, Any], sample_order_book: Dict[str, Any]
    ) -> None:
        """Test the full pipeline with basic market data."""
        engine = BreakoutEvaluationEngine()
        
        # Simulate market data payload
        market_data = {
            "candlestick": sample_candlestick,
            "order_book": sample_order_book,
        }
        
        signals = engine.evaluate_tick(market_data)
        
        # For now, just verify it doesn't crash and returns a list
        assert isinstance(signals, list)