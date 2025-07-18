"""Standard output signal delivery mechanism."""

import json
import sys
from datetime import datetime, timezone
from typing import Any

from ..config.signal_delivery import StdoutDeliveryConfig
from .base import BaseSignalDelivery, DeliveryResult, DeliveryStatus


class StdoutSignalDelivery(BaseSignalDelivery):
    """Standard output signal delivery implementation."""

    def __init__(self, name: str, config: StdoutDeliveryConfig):
        super().__init__(name, config)
        self.config: StdoutDeliveryConfig = config

    def deliver(self, signals: list[dict[str, Any]]) -> list[DeliveryResult]:
        """Deliver signals to stdout."""
        results = []

        for signal in signals:
            try:
                output = self._format_signal(signal)
                print(output, file=sys.stdout, flush=True)

                self.logger.info(
                    "Signal printed to stdout",
                    delivery_name=self.name,
                    plan_id=signal.get("plan_id")
                )

                results.append(DeliveryResult(
                    status=DeliveryStatus.SUCCESS,
                    message="Printed to stdout"
                ))

            except Exception as e:
                self.logger.error(
                    "Failed to print signal to stdout",
                    delivery_name=self.name,
                    plan_id=signal.get("plan_id"),
                    error=str(e)
                )
                results.append(DeliveryResult(
                    status=DeliveryStatus.FAILED,
                    message=f"Stdout error: {str(e)}",
                    error=e
                ))

        return results

    def _format_signal(self, signal: dict[str, Any]) -> str:
        """Format signal for stdout output."""
        if self.config.format == "pretty":
            # Pretty format with timestamp
            output = f"[{datetime.now(timezone.utc).isoformat()}] SIGNAL: {signal['plan_id']} -> {signal['state']}"
            if signal.get("strength_score"):
                output += f" (strength: {signal['strength_score']:.1f})"
            return output
        else:
            # JSON format
            if self.config.include_timestamp:
                signal_copy = signal.copy()
                signal_copy["stdout_timestamp"] = datetime.now(timezone.utc).isoformat()
                return json.dumps(signal_copy)
            else:
                return json.dumps(signal)

    def health_check(self) -> bool:
        """Check if stdout is available."""
        try:
            return sys.stdout.writable()
        except Exception:
            return False
