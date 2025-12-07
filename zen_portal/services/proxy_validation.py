"""Proxy validation for y-router integration.

DEPRECATED: Import from zen_portal.services.openrouter instead.
This module re-exports from the new location for backwards compatibility.
"""

from .openrouter.validation import (
    ProxyStatus,
    ProxyCheckResult,
    ProxyValidationResult,
    ProxyValidator,
    validate_proxy_settings,
    get_proxy_status_line,
)

__all__ = [
    "ProxyStatus",
    "ProxyCheckResult",
    "ProxyValidationResult",
    "ProxyValidator",
    "validate_proxy_settings",
    "get_proxy_status_line",
]
