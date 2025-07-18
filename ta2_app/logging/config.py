"""
Centralized logging configuration for the TA2 trading system.

This module provides standardized logging configuration using structlog
for all components. All logging throughout the system should use this
configuration to ensure consistent formatting and structured logging.
"""
import logging
import sys
from typing import Any, Optional

import structlog
from structlog.types import FilteringBoundLogger


def configure_logging(
    level: str = "INFO",
    format_json: bool = False,
    include_timestamp: bool = True,
    include_caller: bool = False,
    extra_processors: Optional[list] = None
) -> None:
    """
    Configure structlog for the entire application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_json: If True, output JSON format; otherwise human-readable
        include_timestamp: Include timestamp in log output
        include_caller: Include caller information (filename, line number)
        extra_processors: Additional structlog processors to include
    """
    # Convert string level to logging constant
    log_level = getattr(logging, level.upper())

    # Configure standard library logging
    logging.basicConfig(
        level=log_level,
        stream=sys.stdout,
        format="%(message)s"  # structlog will handle formatting
    )

    # Build processor chain
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add timestamp if requested
    if include_timestamp:
        processors.append(structlog.processors.TimeStamper(fmt="iso"))

    # Add caller information if requested
    if include_caller:
        processors.append(structlog.processors.CallsiteParameterAdder(
            parameters=[structlog.processors.CallsiteParameter.FILENAME,
                       structlog.processors.CallsiteParameter.LINENO]
        ))

    # Add any extra processors
    if extra_processors:
        processors.extend(extra_processors)

    # Add final formatting processor
    if format_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> FilteringBoundLogger:
    """
    Get a configured structlog logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger instance
    """
    return structlog.get_logger(name)


def get_gating_logger(name: str) -> FilteringBoundLogger:
    """
    Get a logger specifically configured for gating decisions.

    This logger includes additional context processors specifically
    for gate evaluation logging.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger for gating decisions
    """
    logger = get_logger(name)

    # Add gating-specific binding for context
    return logger.bind(
        subsystem="gating",
        audit_trail=True
    )


def get_state_logger(name: str) -> FilteringBoundLogger:
    """
    Get a logger specifically configured for state transitions.

    This logger includes additional context processors specifically
    for state machine logging.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger for state transitions
    """
    logger = get_logger(name)

    # Add state-specific binding for context
    return logger.bind(
        subsystem="state_machine",
        audit_trail=True
    )


def log_gate_decision(
    logger: FilteringBoundLogger,
    gate_name: str,
    passed: bool,
    plan_id: str,
    reason: str,
    context: Optional[dict[str, Any]] = None
) -> None:
    """
    Log a gating decision with standardized format.

    Args:
        logger: Structlog logger instance
        gate_name: Name of the gate being evaluated
        passed: Whether the gate passed or failed
        plan_id: ID of the plan being evaluated
        reason: Detailed reason for the decision
        context: Additional context data
    """
    # Use the logger's bind method to avoid conflicts
    bound_logger = logger.bind(
        gate_name=gate_name,
        gate_result="PASS" if passed else "FAIL",
        plan_id=plan_id,
        reason=reason,
        event="gate_decision"
    )

    if context:
        bound_logger = bound_logger.bind(context=context)

    if passed:
        bound_logger.info("Gate passed")
    else:
        bound_logger.warning("Gate failed")


def log_state_transition(
    logger: FilteringBoundLogger,
    plan_id: str,
    from_state: str,
    to_state: str,
    trigger: str,
    context: Optional[dict[str, Any]] = None
) -> None:
    """
    Log a state transition with standardized format.

    Args:
        logger: Structlog logger instance
        plan_id: ID of the plan transitioning
        from_state: Current state
        to_state: Target state
        trigger: What triggered the transition
        context: Additional context data
    """
    # Use the logger's bind method to avoid conflicts
    bound_logger = logger.bind(
        plan_id=plan_id,
        from_state=from_state,
        to_state=to_state,
        trigger=trigger,
        event="state_transition"
    )

    if context:
        bound_logger = bound_logger.bind(context=context)

    bound_logger.info("State transition")
