"""OpenRouter models service for fetching and caching available models."""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import urllib.request
import urllib.error


@dataclass
class OpenRouterModel:
    """A model available via OpenRouter."""

    id: str  # e.g., "anthropic/claude-sonnet-4"
    name: str  # e.g., "Claude Sonnet 4"
    context_length: int
    pricing_prompt: float  # per 1M tokens
    pricing_completion: float  # per 1M tokens
    description: str = ""

    @property
    def short_id(self) -> str:
        """Get short ID without provider prefix."""
        return self.id.split("/")[-1] if "/" in self.id else self.id

    @property
    def provider(self) -> str:
        """Get provider name."""
        return self.id.split("/")[0] if "/" in self.id else ""

    @classmethod
    def from_api_dict(cls, data: dict) -> "OpenRouterModel":
        """Create from OpenRouter API response."""
        pricing = data.get("pricing", {})
        # API returns price per token, convert to per 1M tokens
        prompt_price = float(pricing.get("prompt", 0)) * 1_000_000
        completion_price = float(pricing.get("completion", 0)) * 1_000_000

        return cls(
            id=data.get("id", ""),
            name=data.get("name", data.get("id", "")),
            context_length=data.get("context_length", 0),
            pricing_prompt=prompt_price,
            pricing_completion=completion_price,
            description=data.get("description", "")[:200],  # Truncate long descriptions
        )


class OpenRouterModelsService:
    """Service for fetching and caching OpenRouter models.

    Caches models to disk with a configurable TTL (default 24h).
    Falls back to cache if API is unavailable.
    """

    API_URL = "https://openrouter.ai/api/v1/models"
    CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours

    def __init__(self, cache_dir: Path | None = None):
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "zen-portal"
        self._cache_dir = cache_dir
        self._cache_file = cache_dir / "openrouter_models.json"
        self._models: list[OpenRouterModel] | None = None
        self._last_fetch: float = 0

    def get_models(
        self,
        force_refresh: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> list[OpenRouterModel]:
        """Get available models, using cache if valid.

        Args:
            force_refresh: Force API fetch even if cache is valid
            on_progress: Optional callback for progress updates

        Returns:
            List of available models, sorted by provider then name
        """
        # Check in-memory cache first
        if self._models and not force_refresh:
            if time.time() - self._last_fetch < self.CACHE_TTL_SECONDS:
                return self._models

        # Try disk cache
        if not force_refresh:
            cached = self._load_cache()
            if cached:
                self._models = cached
                return cached

        # Fetch from API
        if on_progress:
            on_progress("fetching models...")

        try:
            models = self._fetch_from_api()
            self._models = models
            self._last_fetch = time.time()
            self._save_cache(models)
            return models
        except Exception as e:
            if on_progress:
                on_progress(f"fetch failed: {e}")
            # Fall back to cache even if expired
            cached = self._load_cache(ignore_ttl=True)
            if cached:
                self._models = cached
                return cached
            return []

    def search_models(self, query: str, limit: int = 20) -> list[OpenRouterModel]:
        """Search models by ID or name.

        Args:
            query: Search string (case-insensitive)
            limit: Maximum results to return

        Returns:
            Matching models, best matches first
        """
        models = self.get_models()
        if not query:
            return models[:limit]

        query_lower = query.lower()
        results: list[tuple[int, OpenRouterModel]] = []

        for model in models:
            score = self._match_score(model, query_lower)
            if score > 0:
                results.append((score, model))

        # Sort by score (higher = better match)
        results.sort(key=lambda x: -x[0])
        return [m for _, m in results[:limit]]

    def _match_score(self, model: OpenRouterModel, query: str) -> int:
        """Calculate match score for a model.

        Higher score = better match.
        Returns 0 if no match.
        """
        id_lower = model.id.lower()
        name_lower = model.name.lower()

        # Exact ID match
        if id_lower == query:
            return 1000

        # ID starts with query
        if id_lower.startswith(query):
            return 500

        # ID contains query
        if query in id_lower:
            return 300

        # Name starts with query
        if name_lower.startswith(query):
            return 200

        # Name contains query
        if query in name_lower:
            return 100

        # Fuzzy: all query chars present in order
        if self._fuzzy_match(query, id_lower) or self._fuzzy_match(query, name_lower):
            return 50

        return 0

    def _fuzzy_match(self, query: str, text: str) -> bool:
        """Check if all query chars appear in text in order."""
        text_idx = 0
        for char in query:
            found = text.find(char, text_idx)
            if found == -1:
                return False
            text_idx = found + 1
        return True

    def _fetch_from_api(self) -> list[OpenRouterModel]:
        """Fetch models from OpenRouter API."""
        # Build request with optional auth
        req = urllib.request.Request(self.API_URL)
        req.add_header("User-Agent", "zen-portal/1.0")

        # Add API key if available (not required for /models endpoint)
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        models = []
        for item in data.get("data", []):
            try:
                model = OpenRouterModel.from_api_dict(item)
                if model.id:  # Skip invalid entries
                    models.append(model)
            except (KeyError, ValueError):
                continue

        # Sort by provider, then name
        models.sort(key=lambda m: (m.provider, m.name.lower()))
        return models

    def _load_cache(self, ignore_ttl: bool = False) -> list[OpenRouterModel] | None:
        """Load models from disk cache."""
        if not self._cache_file.exists():
            return None

        try:
            data = json.loads(self._cache_file.read_text())
            cached_at = data.get("cached_at", 0)

            # Check TTL unless ignoring
            if not ignore_ttl:
                if time.time() - cached_at > self.CACHE_TTL_SECONDS:
                    return None

            self._last_fetch = cached_at
            return [
                OpenRouterModel(
                    id=m["id"],
                    name=m["name"],
                    context_length=m["context_length"],
                    pricing_prompt=m["pricing_prompt"],
                    pricing_completion=m["pricing_completion"],
                    description=m.get("description", ""),
                )
                for m in data.get("models", [])
            ]
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def _save_cache(self, models: list[OpenRouterModel]) -> None:
        """Save models to disk cache."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "cached_at": time.time(),
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "context_length": m.context_length,
                    "pricing_prompt": m.pricing_prompt,
                    "pricing_completion": m.pricing_completion,
                    "description": m.description,
                }
                for m in models
            ],
        }

        self._cache_file.write_text(json.dumps(data))

    def get_model_by_id(self, model_id: str) -> OpenRouterModel | None:
        """Get a specific model by ID."""
        for model in self.get_models():
            if model.id == model_id:
                return model
        return None
