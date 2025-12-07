"""Proxy monitoring for real-time health tracking.

DEPRECATED: Import from zen_portal.services.openrouter instead.
This module re-exports from the new location for backwards compatibility.
"""

from .openrouter.monitor import (
    ProxyHealthStatus,
    ProxyMetrics,
    ProxyStatusEvent,
    ProxyMonitor,
)

__all__ = [
    "ProxyHealthStatus",
    "ProxyMetrics",
    "ProxyStatusEvent",
    "ProxyMonitor",
]
