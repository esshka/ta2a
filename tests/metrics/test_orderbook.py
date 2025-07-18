"""Tests for order book analysis"""

import pytest
from ta2_app.metrics.orderbook import (
    BookLevel, BookSnap, calculate_notional_value, analyze_orderbook_imbalance, 
    detect_sweep, get_book_depth_score, OrderBookAnalyzer
)


class TestNotionalValue:
    """Test notional value calculation"""
    
    def test_notional_value_calculation(self):
        """Test basic notional value calculation"""
        levels = [
            BookLevel(price=100.0, size=10.0),
            BookLevel(price=101.0, size=5.0),
            BookLevel(price=102.0, size=3.0),
        ]
        
        notional = calculate_notional_value(levels)
        # 100*10 + 101*5 + 102*3 = 1000 + 505 + 306 = 1811
        assert notional == 1811.0
    
    def test_notional_value_with_max_levels(self):
        """Test notional value with max levels limit"""
        levels = [
            BookLevel(price=100.0, size=10.0),
            BookLevel(price=101.0, size=5.0),
            BookLevel(price=102.0, size=3.0),
            BookLevel(price=103.0, size=2.0),
            BookLevel(price=104.0, size=1.0),
        ]
        
        notional = calculate_notional_value(levels, max_levels=3)
        # Only first 3 levels: 100*10 + 101*5 + 102*3 = 1811
        assert notional == 1811.0
    
    def test_notional_value_empty_levels(self):
        """Test notional value with empty levels"""
        levels = []
        
        notional = calculate_notional_value(levels)
        assert notional == 0.0
    
    def test_notional_value_zero_size(self):
        """Test notional value with zero size levels"""
        levels = [
            BookLevel(price=100.0, size=0.0),
            BookLevel(price=101.0, size=5.0),
        ]
        
        notional = calculate_notional_value(levels)
        # 100*0 + 101*5 = 505
        assert notional == 505.0


class TestOrderBookImbalance:
    """Test order book imbalance analysis"""
    
    def test_balanced_book(self):
        """Test analysis of balanced order book"""
        bids = [
            BookLevel(price=99.0, size=10.0),
            BookLevel(price=98.0, size=8.0),
        ]
        asks = [
            BookLevel(price=101.0, size=10.0),
            BookLevel(price=102.0, size=8.0),
        ]
        
        book = BookSnap(ts=1000, bids=bids, asks=asks)
        metrics = analyze_orderbook_imbalance(book)
        
        # Notional bids = 99*10 + 98*8 = 990 + 784 = 1774
        # Notional asks = 101*10 + 102*8 = 1010 + 816 = 1826
        # imbalance_long = 1774 / 1826 ≈ 0.972
        # imbalance_short = 1826 / 1774 ≈ 1.029
        
        assert metrics.notional_bids == 1774.0
        assert metrics.notional_asks == 1826.0
        assert abs(metrics.imbalance_long - 0.972) < 0.001
        assert abs(metrics.imbalance_short - 1.029) < 0.001
    
    def test_bid_heavy_book(self):
        """Test analysis of bid-heavy order book"""
        bids = [
            BookLevel(price=99.0, size=20.0),
            BookLevel(price=98.0, size=15.0),
        ]
        asks = [
            BookLevel(price=101.0, size=5.0),
            BookLevel(price=102.0, size=3.0),
        ]
        
        book = BookSnap(ts=1000, bids=bids, asks=asks)
        metrics = analyze_orderbook_imbalance(book)
        
        # Notional bids = 99*20 + 98*15 = 1980 + 1470 = 3450
        # Notional asks = 101*5 + 102*3 = 505 + 306 = 811
        # imbalance_long = 3450 / 811 ≈ 4.254
        # imbalance_short = 811 / 3450 ≈ 0.235
        
        assert metrics.notional_bids == 3450.0
        assert metrics.notional_asks == 811.0
        assert abs(metrics.imbalance_long - 4.254) < 0.01
        assert abs(metrics.imbalance_short - 0.235) < 0.01
    
    def test_ask_heavy_book(self):
        """Test analysis of ask-heavy order book"""
        bids = [
            BookLevel(price=99.0, size=5.0),
            BookLevel(price=98.0, size=3.0),
        ]
        asks = [
            BookLevel(price=101.0, size=20.0),
            BookLevel(price=102.0, size=15.0),
        ]
        
        book = BookSnap(ts=1000, bids=bids, asks=asks)
        metrics = analyze_orderbook_imbalance(book)
        
        # Notional bids = 99*5 + 98*3 = 495 + 294 = 789
        # Notional asks = 101*20 + 102*15 = 2020 + 1530 = 3550
        # imbalance_long = 789 / 3550 ≈ 0.222
        # imbalance_short = 3550 / 789 ≈ 4.499
        
        assert metrics.notional_bids == 789.0
        assert metrics.notional_asks == 3550.0
        assert abs(metrics.imbalance_long - 0.222) < 0.001
        assert abs(metrics.imbalance_short - 4.499) < 0.001
    
    def test_zero_bids(self):
        """Test analysis with zero bid liquidity"""
        bids = []
        asks = [
            BookLevel(price=101.0, size=10.0),
            BookLevel(price=102.0, size=5.0),
        ]
        
        book = BookSnap(ts=1000, bids=bids, asks=asks)
        metrics = analyze_orderbook_imbalance(book)
        
        assert metrics.notional_bids == 0.0
        assert metrics.notional_asks == 1520.0  # 101*10 + 102*5
        assert metrics.imbalance_long == 0.0  # bids / asks = 0 / 1520 = 0
        assert metrics.imbalance_short == float('inf')  # asks / bids = 1520 / 0 = inf
    
    def test_zero_asks(self):
        """Test analysis with zero ask liquidity"""
        bids = [
            BookLevel(price=99.0, size=10.0),
            BookLevel(price=98.0, size=5.0),
        ]
        asks = []
        
        book = BookSnap(ts=1000, bids=bids, asks=asks)
        metrics = analyze_orderbook_imbalance(book)
        
        assert metrics.notional_bids == 1480.0  # 99*10 + 98*5
        assert metrics.notional_asks == 0.0
        assert metrics.imbalance_long == float('inf')
        assert metrics.imbalance_short == 0.0  # asks / bids = 0 / 1480 = 0


class TestSweepDetection:
    """Test liquidity sweep detection"""
    
    def test_bid_sweep_depletion(self):
        """Test bid sweep detection via depletion"""
        previous_bids = [
            BookLevel(price=99.0, size=10.0),
            BookLevel(price=98.0, size=8.0),
        ]
        current_bids = [
            BookLevel(price=99.0, size=2.0),  # Depleted
            BookLevel(price=98.0, size=8.0),
        ]
        
        prev_book = BookSnap(ts=1000, bids=previous_bids, asks=[])
        curr_book = BookSnap(ts=2000, bids=current_bids, asks=[])
        
        sweep_detected, sweep_side = detect_sweep(curr_book, prev_book)
        
        # Previous notional = 99*10 + 98*8 = 1774
        # Current notional = 99*2 + 98*8 = 982
        # Depletion = (1774 - 982) / 1774 ≈ 0.447 >= 0.2
        assert sweep_detected is True
        assert sweep_side == 'bid'
    
    def test_ask_sweep_depletion(self):
        """Test ask sweep detection via depletion"""
        previous_asks = [
            BookLevel(price=101.0, size=10.0),
            BookLevel(price=102.0, size=8.0),
        ]
        current_asks = [
            BookLevel(price=101.0, size=2.0),  # Depleted
            BookLevel(price=102.0, size=8.0),
        ]
        
        prev_book = BookSnap(ts=1000, bids=[], asks=previous_asks)
        curr_book = BookSnap(ts=2000, bids=[], asks=current_asks)
        
        sweep_detected, sweep_side = detect_sweep(curr_book, prev_book)
        
        # Previous notional = 101*10 + 102*8 = 1826
        # Current notional = 101*2 + 102*8 = 1018
        # Depletion = (1826 - 1018) / 1826 ≈ 0.443 >= 0.2
        assert sweep_detected is True
        assert sweep_side == 'ask'
    
    def test_no_sweep_minor_depletion(self):
        """Test no sweep detection with minor depletion"""
        previous_bids = [
            BookLevel(price=99.0, size=10.0),
            BookLevel(price=98.0, size=8.0),
        ]
        current_bids = [
            BookLevel(price=99.0, size=9.0),  # Minor depletion
            BookLevel(price=98.0, size=8.0),
        ]
        
        prev_book = BookSnap(ts=1000, bids=previous_bids, asks=[])
        curr_book = BookSnap(ts=2000, bids=current_bids, asks=[])
        
        sweep_detected, sweep_side = detect_sweep(curr_book, prev_book)
        
        # Depletion = (1774 - 1675) / 1774 ≈ 0.056 < 0.2
        assert sweep_detected is False
        assert sweep_side is None
    
    def test_sweep_imbalance_detection(self):
        """Test sweep detection via imbalance"""
        bids = [BookLevel(price=99.0, size=20.0)]  # High bid liquidity
        asks = [BookLevel(price=101.0, size=2.0)]   # Low ask liquidity
        
        # Previous book has some balanced liquidity
        prev_book = BookSnap(ts=1000, bids=[BookLevel(99.0, 10.0)], asks=[BookLevel(101.0, 10.0)])
        curr_book = BookSnap(ts=2000, bids=bids, asks=asks)
        
        sweep_detected, sweep_side = detect_sweep(curr_book, prev_book, imbalance_threshold=1.5)
        
        # Imbalance long = 1980 / 202 ≈ 9.8 >= 1.5
        assert sweep_detected is True
        assert sweep_side == 'ask'  # Bids dominating suggests asks were swept
    
    def test_no_sweep_balanced_book(self):
        """Test no sweep with balanced book"""
        bids = [BookLevel(price=99.0, size=10.0)]
        asks = [BookLevel(price=101.0, size=10.0)]
        
        prev_book = BookSnap(ts=1000, bids=bids, asks=asks)
        curr_book = BookSnap(ts=2000, bids=bids, asks=asks)
        
        sweep_detected, sweep_side = detect_sweep(curr_book, prev_book)
        
        assert sweep_detected is False
        assert sweep_side is None
    
    def test_sweep_empty_previous_book(self):
        """Test sweep detection with empty previous book"""
        bids = [BookLevel(price=99.0, size=10.0)]
        asks = [BookLevel(price=101.0, size=10.0)]
        
        prev_book = BookSnap(ts=1000, bids=[], asks=[])
        curr_book = BookSnap(ts=2000, bids=bids, asks=asks)
        
        sweep_detected, sweep_side = detect_sweep(curr_book, prev_book)
        
        assert sweep_detected is False
        assert sweep_side is None


class TestBookDepthScore:
    """Test book depth scoring"""
    
    def test_deep_book_score(self):
        """Test scoring for deep book"""
        bids = [BookLevel(price=99.0, size=5000.0)]  # $495K
        asks = [BookLevel(price=101.0, size=5000.0)]  # $505K
        
        book = BookSnap(ts=1000, bids=bids, asks=asks)
        score = get_book_depth_score(book)
        
        # Total notional = 495000 + 505000 = 1000000 >= 1M
        assert score == 100.0
    
    def test_medium_book_score(self):
        """Test scoring for medium book"""
        bids = [BookLevel(price=99.0, size=2500.0)]  # $247.5K
        asks = [BookLevel(price=101.0, size=2500.0)]  # $252.5K
        
        book = BookSnap(ts=1000, bids=bids, asks=asks)
        score = get_book_depth_score(book)
        
        # Total notional = 247500 + 252500 = 500000 >= 500K
        assert score == 75.0
    
    def test_thin_book_score(self):
        """Test scoring for thin book"""
        bids = [BookLevel(price=99.0, size=100.0)]  # $9.9K
        asks = [BookLevel(price=101.0, size=100.0)]  # $10.1K
        
        book = BookSnap(ts=1000, bids=bids, asks=asks)
        score = get_book_depth_score(book)
        
        # Total notional = 9900 + 10100 = 20000 < 50K
        assert score == 0.0
    
    def test_empty_book_score(self):
        """Test scoring for empty book"""
        book = BookSnap(ts=1000, bids=[], asks=[])
        score = get_book_depth_score(book)
        
        assert score == 0.0


class TestOrderBookAnalyzer:
    """Test OrderBookAnalyzer class"""
    
    def test_analyzer_initialization(self):
        """Test OrderBookAnalyzer initialization"""
        analyzer = OrderBookAnalyzer(
            max_levels=3,
            depletion_threshold=0.15,
            imbalance_threshold=2.0
        )
        
        assert analyzer.max_levels == 3
        assert analyzer.depletion_threshold == 0.15
        assert analyzer.imbalance_threshold == 2.0
        assert analyzer.previous_book is None
    
    def test_analyzer_first_book(self):
        """Test analyzer with first book"""
        analyzer = OrderBookAnalyzer()
        
        bids = [BookLevel(price=99.0, size=10.0)]
        asks = [BookLevel(price=101.0, size=10.0)]
        book = BookSnap(ts=1000, bids=bids, asks=asks)
        
        metrics = analyzer.analyze(book)
        
        # First book should not detect sweep
        assert metrics.sweep_detected is False
        assert metrics.sweep_side is None
        assert metrics.notional_bids == 990.0
        assert metrics.notional_asks == 1010.0
        
        # Should store book for next analysis
        assert analyzer.previous_book is book
    
    def test_analyzer_sweep_detection(self):
        """Test analyzer sweep detection across books"""
        analyzer = OrderBookAnalyzer()
        
        # First book
        bids1 = [BookLevel(price=99.0, size=10.0)]
        asks1 = [BookLevel(price=101.0, size=10.0)]
        book1 = BookSnap(ts=1000, bids=bids1, asks=asks1)
        
        metrics1 = analyzer.analyze(book1)
        assert metrics1.sweep_detected is False
        
        # Second book with bid sweep
        bids2 = [BookLevel(price=99.0, size=2.0)]  # Depleted
        asks2 = [BookLevel(price=101.0, size=10.0)]
        book2 = BookSnap(ts=2000, bids=bids2, asks=asks2)
        
        metrics2 = analyzer.analyze(book2)
        assert metrics2.sweep_detected is True
        assert metrics2.sweep_side == 'bid'
    
    def test_analyzer_state_tracking(self):
        """Test analyzer maintains state correctly"""
        analyzer = OrderBookAnalyzer()
        
        books = [
            BookSnap(ts=1000, bids=[BookLevel(99.0, 10.0)], asks=[BookLevel(101.0, 10.0)]),
            BookSnap(ts=2000, bids=[BookLevel(99.0, 8.0)], asks=[BookLevel(101.0, 10.0)]),
            BookSnap(ts=3000, bids=[BookLevel(99.0, 6.0)], asks=[BookLevel(101.0, 10.0)]),
        ]
        
        for i, book in enumerate(books):
            metrics = analyzer.analyze(book)
            
            # Should always have current book as previous for next iteration
            assert analyzer.previous_book is book
            
            # Only first book should not detect sweep
            if i == 0:
                assert metrics.sweep_detected is False
            else:
                # Subsequent books might detect sweep depending on depletion
                assert isinstance(metrics.sweep_detected, bool)