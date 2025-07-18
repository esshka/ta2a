"""Base classes for signal delivery mechanisms."""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class DeliveryStatus(Enum):
    """Signal delivery status."""
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


@dataclass
class DeliveryResult:
    """Result of signal delivery attempt."""
    status: DeliveryStatus
    message: Optional[str] = None
    attempt_count: int = 1
    delivery_time_ms: Optional[int] = None
    error: Optional[Exception] = None


class SignalDeliveryError(Exception):
    """Base exception for signal delivery errors."""
    pass


class SignalDeliveryRetryableError(SignalDeliveryError):
    """Retryable signal delivery error."""
    pass


class SignalDeliveryPermanentError(SignalDeliveryError):
    """Permanent signal delivery error that should not be retried."""
    pass


class BaseSignalDelivery(ABC):
    """Base class for signal delivery mechanisms."""

    def __init__(self, name: str, config: Any):
        self.name = name
        self.config = config
        self.logger = logging.getLogger(f"signal.delivery.{name}")
        self._delivery_count = 0
        self._error_count = 0

    @abstractmethod
    def deliver(self, signals: list[dict[str, Any]]) -> list[DeliveryResult]:
        """
        Deliver signals to the configured destination.

        Args:
            signals: List of formatted signal dictionaries

        Returns:
            List of delivery results for each signal
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if delivery mechanism is healthy."""
        pass

    def deliver_with_retry(
        self,
        signals: list[dict[str, Any]],
        max_retries: int = 3,
        retry_delay: int = 1
    ) -> list[DeliveryResult]:
        """
        Deliver signals with retry logic.

        Args:
            signals: List of formatted signal dictionaries
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds

        Returns:
            List of delivery results for each signal
        """
        results = []

        for signal in signals:
            attempt = 0
            last_error = None

            while attempt <= max_retries:
                try:
                    start_time = time.time()
                    delivery_results = self.deliver([signal])
                    delivery_time = int((time.time() - start_time) * 1000)

                    if delivery_results and delivery_results[0].status == DeliveryStatus.SUCCESS:
                        result = delivery_results[0]
                        result.delivery_time_ms = delivery_time
                        result.attempt_count = attempt + 1
                        results.append(result)
                        self._delivery_count += 1
                        break
                    else:
                        # Delivery failed but didn't raise exception
                        last_error = delivery_results[0].error if delivery_results else None

                except SignalDeliveryPermanentError as e:
                    # Don't retry permanent errors
                    self._error_count += 1
                    results.append(DeliveryResult(
                        status=DeliveryStatus.FAILED,
                        message=f"Permanent error: {str(e)}",
                        attempt_count=attempt + 1,
                        error=e
                    ))
                    break

                except SignalDeliveryRetryableError as e:
                    last_error = e

                except Exception as e:
                    # Unknown error - treat as retryable
                    last_error = e

                attempt += 1

                if attempt <= max_retries:
                    self.logger.warning(
                        f"Delivery attempt {attempt} failed, retrying in {retry_delay}s",
                        delivery_name=self.name,
                        error=str(last_error)
                    )
                    time.sleep(retry_delay)
                else:
                    # Max retries exceeded
                    self._error_count += 1
                    results.append(DeliveryResult(
                        status=DeliveryStatus.DEAD_LETTER,
                        message=f"Max retries exceeded: {str(last_error)}",
                        attempt_count=attempt,
                        error=last_error
                    ))

        return results

    def get_stats(self) -> dict[str, Any]:
        """Get delivery statistics."""
        return {
            "name": self.name,
            "delivery_count": self._delivery_count,
            "error_count": self._error_count,
            "success_rate": (
                self._delivery_count / (self._delivery_count + self._error_count)
                if (self._delivery_count + self._error_count) > 0 else 0.0
            )
        }

    def reset_stats(self):
        """Reset delivery statistics."""
        self._delivery_count = 0
        self._error_count = 0
