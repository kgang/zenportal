"""OpenRouter integration services for zen-portal.

This package consolidates all OpenRouter/proxy related services:
- ProxyValidator: Configuration and connectivity validation
- ProxyMonitor: Real-time proxy health monitoring
- BillingTracker: Usage and cost tracking
- OpenRouterModelsService: Model listing and caching
"""

from .validation import (
    ProxyStatus,
    ProxyCheckResult,
    ProxyValidationResult,
    ProxyValidator,
)
from .monitor import (
    ProxyHealthStatus,
    ProxyMetrics,
    ProxyStatusEvent,
    ProxyMonitor,
)
from .billing import (
    BillingInfo,
    UsageRecord,
    ModelPricing,
    BillingTracker,
)
from .models import (
    OpenRouterModel,
    OpenRouterModelsService,
)

__all__ = [
    # Validation
    "ProxyStatus",
    "ProxyCheckResult",
    "ProxyValidationResult",
    "ProxyValidator",
    # Monitoring
    "ProxyHealthStatus",
    "ProxyMetrics",
    "ProxyStatusEvent",
    "ProxyMonitor",
    # Billing
    "BillingInfo",
    "UsageRecord",
    "ModelPricing",
    "BillingTracker",
    # Models
    "OpenRouterModel",
    "OpenRouterModelsService",
]
