"""File-based signal delivery mechanism."""

import fcntl
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config.signal_delivery import FileDeliveryConfig
from .base import (
    BaseSignalDelivery,
    DeliveryResult,
    DeliveryStatus,
    SignalDeliveryPermanentError,
)


class FileSignalDelivery(BaseSignalDelivery):
    """File-based signal delivery implementation."""

    def __init__(self, name: str, config: FileDeliveryConfig):
        super().__init__(name, config)
        self.config: FileDeliveryConfig = config

        # Validate and prepare output path
        self.output_path = Path(config.output_path)

        # Create parent directories if needed
        if config.create_dirs:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Validate format
        if config.format not in ["json", "jsonl"]:
            raise SignalDeliveryPermanentError(f"Unsupported format: {config.format}")

    def deliver(self, signals: list[dict[str, Any]]) -> list[DeliveryResult]:
        """Deliver signals to file."""
        results = []

        try:
            # Check file size limits
            if self.config.max_file_size_mb:
                if self._check_file_size_limit():
                    if self.config.rotation_enabled:
                        self._rotate_file()
                    else:
                        error_msg = f"File size limit exceeded: {self.config.max_file_size_mb}MB"
                        self.logger.error(error_msg, delivery_name=self.name)
                        return [DeliveryResult(
                            status=DeliveryStatus.FAILED,
                            message=error_msg
                        ) for _ in signals]

            # Write signals to file
            if self.config.format == "json":
                self._write_json_format(signals)
            else:  # jsonl
                self._write_jsonl_format(signals)

            # Create success results
            for signal in signals:
                self.logger.info(
                    "Signal written to file",
                    delivery_name=self.name,
                    plan_id=signal.get("plan_id"),
                    output_path=str(self.output_path)
                )
                results.append(DeliveryResult(
                    status=DeliveryStatus.SUCCESS,
                    message=f"Written to {self.output_path}"
                ))

        except OSError as e:
            # File system errors are retryable
            error_msg = f"File system error: {str(e)}"
            self.logger.warning(
                "Signal delivery file error",
                delivery_name=self.name,
                output_path=str(self.output_path),
                error=str(e)
            )
            results = [DeliveryResult(
                status=DeliveryStatus.FAILED,
                message=error_msg,
                error=e
            ) for _ in signals]

        except json.JSONEncodeError as e:
            # JSON encoding errors are permanent
            error_msg = f"JSON encoding error: {str(e)}"
            self.logger.error(
                "Signal delivery JSON error",
                delivery_name=self.name,
                error=str(e)
            )
            results = [DeliveryResult(
                status=DeliveryStatus.FAILED,
                message=error_msg,
                error=e
            ) for _ in signals]

        except Exception as e:
            # Unexpected errors
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(
                "Signal delivery unexpected error",
                delivery_name=self.name,
                error=str(e)
            )
            results = [DeliveryResult(
                status=DeliveryStatus.FAILED,
                message=error_msg,
                error=e
            ) for _ in signals]

        return results

    def _write_json_format(self, signals: list[dict[str, Any]]) -> None:
        """Write signals in JSON format (array of objects)."""
        # Read existing data if file exists and append mode is enabled
        existing_data = []
        if self.config.append_mode and self.output_path.exists():
            try:
                with open(self.output_path) as f:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = []
            except (OSError, json.JSONDecodeError):
                # If file is corrupted or empty, start fresh
                existing_data = []

        # Combine existing and new data
        all_data = existing_data + signals

        # Write to file with file locking
        with open(self.output_path, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(all_data, f, indent=2, default=str)

    def _write_jsonl_format(self, signals: list[dict[str, Any]]) -> None:
        """Write signals in JSONL format (one JSON object per line)."""
        mode = 'a' if self.config.append_mode else 'w'

        with open(self.output_path, mode) as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            for signal in signals:
                json.dump(signal, f, default=str)
                f.write('\n')

    def _check_file_size_limit(self) -> bool:
        """Check if file size exceeds the configured limit."""
        if not self.output_path.exists():
            return False

        file_size_mb = self.output_path.stat().st_size / (1024 * 1024)
        return file_size_mb > self.config.max_file_size_mb

    def _rotate_file(self) -> None:
        """Rotate the output file when size limit is reached."""
        if not self.output_path.exists():
            return

        # Generate rotated filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rotated_name = f"{self.output_path.stem}_{timestamp}{self.output_path.suffix}"
        rotated_path = self.output_path.parent / rotated_name

        # Rename current file
        self.output_path.rename(rotated_path)

        self.logger.info(
            "File rotated due to size limit",
            delivery_name=self.name,
            original_path=str(self.output_path),
            rotated_path=str(rotated_path)
        )

    def health_check(self) -> bool:
        """Check if file system is writable."""
        try:
            # Try to create a temporary file in the same directory
            test_file = self.output_path.parent / ".health_check_test"
            test_file.write_text("test")
            test_file.unlink()
            return True

        except Exception as e:
            self.logger.warning(
                "Health check failed",
                delivery_name=self.name,
                error=str(e)
            )
            return False
