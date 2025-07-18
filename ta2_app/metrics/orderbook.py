"""Order book analysis for imbalance and sweep detection"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class BookLevel:
    """Order book level (price, size)"""
    price: float
    size: float


@dataclass
class BookSnap:
    """Order book snapshot"""
    ts: float
    bids: list[BookLevel]
    asks: list[BookLevel]


@dataclass
class OrderBookMetrics:
    """Order book analysis results"""
    notional_bids: float
    notional_asks: float
    imbalance_long: float
    imbalance_short: float
    sweep_detected: bool
    sweep_side: Optional[str]  # 'bid' or 'ask'


def calculate_notional_value(levels: list[BookLevel], max_levels: int = 5) -> float:
    """
    Calculate notional value for order book side

    Args:
        levels: List of BookLevel objects
        max_levels: Maximum levels to include in calculation

    Returns:
        Total notional value (price * size)
    """
    notional = 0.0
    for i, level in enumerate(levels):
        if i >= max_levels:
            break
        notional += level.price * level.size

    return notional


def analyze_orderbook_imbalance(book: BookSnap, max_levels: int = 5) -> OrderBookMetrics:
    """
    Analyze order book imbalance

    Args:
        book: Order book snapshot
        max_levels: Maximum levels to analyze

    Returns:
        OrderBookMetrics with imbalance analysis
    """
    notional_bids = calculate_notional_value(book.bids, max_levels)
    notional_asks = calculate_notional_value(book.asks, max_levels)

    # Calculate imbalance ratios
    if notional_bids > 0:
        imbalance_short = notional_asks / notional_bids
    else:
        imbalance_short = float('inf') if notional_asks > 0 else 1.0

    if notional_asks > 0:
        imbalance_long = notional_bids / notional_asks
    else:
        imbalance_long = float('inf') if notional_bids > 0 else 1.0

    return OrderBookMetrics(
        notional_bids=notional_bids,
        notional_asks=notional_asks,
        imbalance_long=imbalance_long,
        imbalance_short=imbalance_short,
        sweep_detected=False,
        sweep_side=None
    )


def detect_sweep(current_book: BookSnap, previous_book: BookSnap,
                 depletion_threshold: float = 0.2,
                 imbalance_threshold: float = 1.5,
                 max_levels: int = 5) -> tuple[bool, Optional[str]]:
    """
    Detect liquidity sweeps by comparing book snapshots

    Args:
        current_book: Current order book snapshot
        previous_book: Previous order book snapshot
        depletion_threshold: Minimum depletion percentage to trigger sweep
        imbalance_threshold: Minimum imbalance ratio to trigger sweep
        max_levels: Maximum levels to analyze

    Returns:
        Tuple of (sweep_detected, sweep_side)
    """
    if not previous_book.bids and not previous_book.asks:
        return False, None

    # Calculate notional values for both snapshots
    prev_notional_bids = calculate_notional_value(previous_book.bids, max_levels)
    prev_notional_asks = calculate_notional_value(previous_book.asks, max_levels)

    curr_notional_bids = calculate_notional_value(current_book.bids, max_levels)
    curr_notional_asks = calculate_notional_value(current_book.asks, max_levels)

    # Check for bid side sweep (asks attacking bids)
    if prev_notional_bids > 0:
        bid_depletion = (prev_notional_bids - curr_notional_bids) / prev_notional_bids
        # Enhanced sweep detection: require significant absolute depletion
        min_absolute_depletion = 1000.0  # Minimum notional value depleted
        absolute_bid_depletion = prev_notional_bids - curr_notional_bids
        if (bid_depletion >= depletion_threshold and
            absolute_bid_depletion >= min_absolute_depletion):
            return True, 'bid'

    # Check for ask side sweep (bids attacking asks)
    if prev_notional_asks > 0:
        ask_depletion = (prev_notional_asks - curr_notional_asks) / prev_notional_asks
        # Enhanced sweep detection: require significant absolute depletion
        min_absolute_depletion = 1000.0  # Minimum notional value depleted
        absolute_ask_depletion = prev_notional_asks - curr_notional_asks
        if (ask_depletion >= depletion_threshold and
            absolute_ask_depletion >= min_absolute_depletion):
            return True, 'ask'

    # Check for imbalance-based sweep detection
    if curr_notional_bids > 0 and curr_notional_asks > 0:
        current_imbalance_long = curr_notional_bids / curr_notional_asks
        current_imbalance_short = curr_notional_asks / curr_notional_bids

        if current_imbalance_long >= imbalance_threshold:
            return True, 'ask'  # Bids dominating (likely swept asks)
        elif current_imbalance_short >= imbalance_threshold:
            return True, 'bid'  # Asks dominating (likely swept bids)

    return False, None


def calculate_sweep_confidence(current_book: BookSnap, previous_book: BookSnap,
                              sweep_side: str, max_levels: int = 5) -> float:
    """
    Calculate confidence score for detected sweep (0.0 to 1.0)

    Args:
        current_book: Current order book snapshot
        previous_book: Previous order book snapshot
        sweep_side: Side of detected sweep ('bid' or 'ask')
        max_levels: Maximum levels to analyze

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not previous_book.bids and not previous_book.asks:
        return 0.0

    # Calculate notional values
    prev_notional_bids = calculate_notional_value(previous_book.bids, max_levels)
    prev_notional_asks = calculate_notional_value(previous_book.asks, max_levels)
    curr_notional_bids = calculate_notional_value(current_book.bids, max_levels)
    curr_notional_asks = calculate_notional_value(current_book.asks, max_levels)

    confidence = 0.0

    if sweep_side == 'bid' and prev_notional_bids > 0:
        # Bid side sweep - calculate based on depletion and imbalance
        depletion_ratio = (prev_notional_bids - curr_notional_bids) / prev_notional_bids
        confidence += min(depletion_ratio * 2.0, 0.6)  # Max 60% from depletion

        # Add imbalance component
        if curr_notional_asks > 0:
            imbalance = curr_notional_asks / max(curr_notional_bids, 1.0)
            confidence += min(imbalance / 3.0, 0.4)  # Max 40% from imbalance

    elif sweep_side == 'ask' and prev_notional_asks > 0:
        # Ask side sweep - calculate based on depletion and imbalance
        depletion_ratio = (prev_notional_asks - curr_notional_asks) / prev_notional_asks
        confidence += min(depletion_ratio * 2.0, 0.6)  # Max 60% from depletion

        # Add imbalance component
        if curr_notional_bids > 0:
            imbalance = curr_notional_bids / max(curr_notional_asks, 1.0)
            confidence += min(imbalance / 3.0, 0.4)  # Max 40% from imbalance

    return min(confidence, 1.0)


def get_book_depth_score(book: BookSnap, max_levels: int = 5) -> float:
    """
    Calculate order book depth score (0-100)

    Args:
        book: Order book snapshot
        max_levels: Maximum levels to analyze

    Returns:
        Depth score from 0 (thin) to 100 (deep)
    """
    notional_bids = calculate_notional_value(book.bids, max_levels)
    notional_asks = calculate_notional_value(book.asks, max_levels)

    total_notional = notional_bids + notional_asks

    # Simple scoring based on total notional value
    # This would need to be calibrated based on typical market conditions
    if total_notional >= 1000000:  # $1M+ notional
        return 100.0
    elif total_notional >= 500000:  # $500K+ notional
        return 75.0
    elif total_notional >= 100000:  # $100K+ notional
        return 50.0
    elif total_notional >= 50000:   # $50K+ notional
        return 25.0
    else:
        return 0.0


class OrderBookAnalyzer:
    """Stateful order book analyzer"""

    def __init__(self, max_levels: int = 5, depletion_threshold: float = 0.2,
                 imbalance_threshold: float = 1.5):
        self.max_levels = max_levels
        self.depletion_threshold = depletion_threshold
        self.imbalance_threshold = imbalance_threshold
        self.previous_book: Optional[BookSnap] = None

    def analyze(self, book: BookSnap) -> OrderBookMetrics:
        """
        Analyze order book with sweep detection

        Args:
            book: Current order book snapshot

        Returns:
            OrderBookMetrics with complete analysis
        """
        # Calculate basic imbalance metrics
        metrics = analyze_orderbook_imbalance(book, self.max_levels)

        # Detect sweeps if we have previous book
        if self.previous_book:
            sweep_detected, sweep_side = detect_sweep(
                book, self.previous_book,
                self.depletion_threshold,
                self.imbalance_threshold,
                self.max_levels
            )
            metrics.sweep_detected = sweep_detected
            metrics.sweep_side = sweep_side

        # Update previous book
        self.previous_book = book

        return metrics
