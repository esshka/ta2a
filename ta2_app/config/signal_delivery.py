"""Configuration for signal delivery mechanisms."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class DeliveryMethod(Enum):
    """Supported signal delivery methods."""
    HTTP_POST = "http_post"
    FILE_OUTPUT = "file_output"
    STDOUT = "stdout"


@dataclass(frozen=True)
class HttpDeliveryConfig:
    """Configuration for HTTP POST delivery."""
    url: str
    method: str = "POST"
    headers: Optional[dict[str, str]] = None
    timeout_seconds: int = 30
    verify_ssl: bool = True
    retry_attempts: int = 3
    retry_delay_seconds: int = 1


@dataclass(frozen=True)
class FileDeliveryConfig:
    """Configuration for file-based delivery."""
    output_path: str
    format: str = "json"  # json, jsonl
    append_mode: bool = True
    max_file_size_mb: Optional[int] = None
    rotation_enabled: bool = False
    create_dirs: bool = True


@dataclass(frozen=True)
class StdoutDeliveryConfig:
    """Configuration for stdout delivery."""
    format: str = "json"  # json, pretty
    include_timestamp: bool = True


@dataclass(frozen=True)
class DeliveryDestination:
    """Single signal delivery destination."""
    name: str
    method: DeliveryMethod
    config: Any  # HttpDeliveryConfig | FileDeliveryConfig | StdoutDeliveryConfig
    enabled: bool = True

    # Filtering options
    states_filter: Optional[list[str]] = None  # Only deliver specific states
    plans_filter: Optional[list[str]] = None   # Only deliver specific plan IDs
    min_strength_score: Optional[float] = None


@dataclass(frozen=True)
class SignalDeliveryConfig:
    """Complete signal delivery configuration."""
    destinations: list[DeliveryDestination]
    enabled: bool = True

    # Global options
    batch_size: int = 1  # Number of signals to batch together
    batch_timeout_ms: int = 1000  # Max time to wait for batch
    parallel_delivery: bool = True  # Deliver to destinations in parallel

    # Error handling
    failure_retry_attempts: int = 3
    failure_retry_delay_seconds: int = 2
    dead_letter_enabled: bool = False
    dead_letter_path: Optional[str] = None


def get_default_delivery_config() -> SignalDeliveryConfig:
    """Get default signal delivery configuration."""
    return SignalDeliveryConfig(
        destinations=[
            DeliveryDestination(
                name="stdout",
                method=DeliveryMethod.STDOUT,
                config=StdoutDeliveryConfig(
                    format="json",
                    include_timestamp=True
                ),
                enabled=True
            )
        ],
        enabled=True,
        batch_size=1,
        batch_timeout_ms=1000,
        parallel_delivery=True,
        failure_retry_attempts=3,
        failure_retry_delay_seconds=2,
        dead_letter_enabled=False,
        dead_letter_path=None
    )


def create_http_destination(
    name: str,
    url: str,
    headers: Optional[dict[str, str]] = None,
    enabled: bool = True,
    **kwargs
) -> DeliveryDestination:
    """Create HTTP delivery destination."""
    return DeliveryDestination(
        name=name,
        method=DeliveryMethod.HTTP_POST,
        config=HttpDeliveryConfig(
            url=url,
            headers=headers or {},
            **kwargs
        ),
        enabled=enabled
    )


def create_file_destination(
    name: str,
    output_path: str,
    format: str = "jsonl",
    enabled: bool = True,
    **kwargs
) -> DeliveryDestination:
    """Create file delivery destination."""
    return DeliveryDestination(
        name=name,
        method=DeliveryMethod.FILE_OUTPUT,
        config=FileDeliveryConfig(
            output_path=output_path,
            format=format,
            **kwargs
        ),
        enabled=enabled
    )
