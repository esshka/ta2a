"""HTTP POST signal delivery mechanism."""

import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..config.signal_delivery import HttpDeliveryConfig
from .base import (
    BaseSignalDelivery,
    DeliveryResult,
    DeliveryStatus,
    SignalDeliveryPermanentError,
    SignalDeliveryRetryableError,
)


class HttpSignalDelivery(BaseSignalDelivery):
    """HTTP POST signal delivery implementation."""

    def __init__(self, name: str, config: HttpDeliveryConfig):
        super().__init__(name, config)
        self.config: HttpDeliveryConfig = config

        # Validate URL
        parsed = urlparse(config.url)
        if not parsed.scheme or not parsed.netloc:
            raise SignalDeliveryPermanentError(f"Invalid URL: {config.url}")

    def deliver(self, signals: list[dict[str, Any]]) -> list[DeliveryResult]:
        """Deliver signals via HTTP POST."""
        results = []

        for signal in signals:
            try:
                result = self._deliver_single_signal(signal)
                results.append(result)

            except Exception as e:
                self.logger.error(
                    "Unexpected error delivering signal",
                    delivery_name=self.name,
                    plan_id=signal.get("plan_id"),
                    error=str(e)
                )
                results.append(DeliveryResult(
                    status=DeliveryStatus.FAILED,
                    message=f"Unexpected error: {str(e)}",
                    error=e
                ))

        return results

    def _deliver_single_signal(self, signal: dict[str, Any]) -> DeliveryResult:
        """Deliver a single signal via HTTP POST."""
        try:
            # Prepare request
            data = json.dumps(signal).encode('utf-8')
            headers = {
                'Content-Type': 'application/json',
                'Content-Length': str(len(data)),
                'User-Agent': 'ta2-app/1.0'
            }

            # Add custom headers from config
            if self.config.headers:
                headers.update(self.config.headers)

            # Create request
            req = Request(
                self.config.url,
                data=data,
                headers=headers,
                method=self.config.method
            )

            # Make request
            with urlopen(req, timeout=self.config.timeout_seconds) as response:
                response_code = response.getcode()
                response_data = response.read().decode('utf-8')

                if 200 <= response_code < 300:
                    self.logger.info(
                        "Signal delivered successfully",
                        delivery_name=self.name,
                        plan_id=signal.get("plan_id"),
                        response_code=response_code
                    )
                    return DeliveryResult(
                        status=DeliveryStatus.SUCCESS,
                        message=f"HTTP {response_code}: {response_data[:100]}"
                    )
                else:
                    # Non-success HTTP status
                    error_msg = f"HTTP {response_code}: {response_data[:200]}"
                    self.logger.warning(
                        "Signal delivery failed with HTTP error",
                        delivery_name=self.name,
                        plan_id=signal.get("plan_id"),
                        response_code=response_code,
                        response_data=response_data[:200]
                    )

                    # Determine if retryable
                    if response_code >= 500:
                        # Server errors are retryable
                        raise SignalDeliveryRetryableError(error_msg)
                    else:
                        # Client errors are permanent
                        raise SignalDeliveryPermanentError(error_msg)

        except HTTPError as e:
            error_msg = f"HTTP {e.code}: {e.reason}"
            self.logger.warning(
                "Signal delivery HTTP error",
                delivery_name=self.name,
                plan_id=signal.get("plan_id"),
                error_code=e.code,
                error_reason=e.reason
            )

            # Determine if retryable
            if e.code >= 500:
                raise SignalDeliveryRetryableError(error_msg)
            else:
                raise SignalDeliveryPermanentError(error_msg)

        except (OSError, URLError, socket.timeout) as e:
            # Network errors are retryable
            error_msg = f"Network error: {str(e)}"
            self.logger.warning(
                "Signal delivery network error",
                delivery_name=self.name,
                plan_id=signal.get("plan_id"),
                error=str(e)
            )
            raise SignalDeliveryRetryableError(error_msg)

        except json.JSONEncodeError as e:
            # JSON encoding errors are permanent
            error_msg = f"JSON encoding error: {str(e)}"
            self.logger.error(
                "Signal delivery JSON error",
                delivery_name=self.name,
                plan_id=signal.get("plan_id"),
                error=str(e)
            )
            raise SignalDeliveryPermanentError(error_msg)

    def health_check(self) -> bool:
        """Check if HTTP endpoint is reachable."""
        try:
            # Simple HEAD request to check connectivity
            parsed = urlparse(self.config.url)
            health_url = f"{parsed.scheme}://{parsed.netloc}"

            req = Request(health_url, method='HEAD')
            with urlopen(req, timeout=5) as response:
                return 200 <= response.getcode() < 400

        except Exception as e:
            self.logger.warning(
                "Health check failed",
                delivery_name=self.name,
                error=str(e)
            )
            return False
