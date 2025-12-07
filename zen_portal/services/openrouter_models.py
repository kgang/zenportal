"""OpenRouter model listing and caching.

DEPRECATED: Import from zen_portal.services.openrouter instead.
This module re-exports from the new location for backwards compatibility.
"""

from .openrouter.models import (
    OpenRouterModel,
    OpenRouterModelsService,
)

__all__ = [
    "OpenRouterModel",
    "OpenRouterModelsService",
]
