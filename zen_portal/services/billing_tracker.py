"""OpenRouter billing and usage tracking service.

Integrates with OpenRouter API to provide real-time billing information,
usage analytics, and quota monitoring for proxy sessions.
"""

import asyncio
import json
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from pathlib import Path

from .config import ProxySettings


@dataclass
class BillingInfo:
    """OpenRouter account billing information."""

    balance: float
    monthly_limit: Optional[float] = None
    monthly_usage: float = 0.0
    rate_limit_requests: Optional[int] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None


@dataclass
class UsageRecord:
    """Individual usage record."""

    timestamp: datetime
    model: str
    input_tokens: int
    output_tokens: int
    cost: float


@dataclass
class ModelPricing:
    """Model pricing information."""

    model: str
    input_cost_per_token: float  # dollars per token
    output_cost_per_token: float
    context_length: int


class BillingTracker:
    """Tracks billing and usage for OpenRouter proxy sessions.

    Features:
    - Real-time account balance monitoring
    - Usage analytics and cost tracking
    - Rate limit monitoring
    - Model pricing information
    - Daily/weekly/monthly usage reports
    """

    # OpenRouter API endpoints
    API_BASE = "https://openrouter.ai/api/v1"
    ACCOUNT_ENDPOINT = "/auth/key"
    MODELS_ENDPOINT = "/models"
    USAGE_ENDPOINT = "/generation"  # For usage history

    # Cache settings
    CACHE_DIR = Path.home() / ".cache" / "zen-portal"
    BILLING_CACHE_FILE = CACHE_DIR / "billing_cache.json"
    PRICING_CACHE_FILE = CACHE_DIR / "model_pricing.json"

    # Cache TTL
    BILLING_CACHE_TTL = 300  # 5 minutes
    PRICING_CACHE_TTL = 86400  # 24 hours

    def __init__(self, settings: Optional[ProxySettings] = None):
        self._settings = settings

        # Cached data
        self._billing_info: Optional[BillingInfo] = None
        self._billing_cache_time: Optional[datetime] = None
        self._model_pricing: Dict[str, ModelPricing] = {}
        self._pricing_cache_time: Optional[datetime] = None

        # Usage tracking
        self._usage_records: List[UsageRecord] = []

        # Ensure cache directory exists
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    async def get_billing_info(self, force_refresh: bool = False) -> Optional[BillingInfo]:
        """Get current billing information.

        Args:
            force_refresh: Force API call instead of using cache

        Returns:
            BillingInfo object or None if unavailable
        """
        if not self._settings or not self._settings.enabled:
            return None

        # Check cache first
        if not force_refresh and self._is_billing_cache_valid():
            return self._billing_info

        # Load from file cache if fresh
        if not force_refresh:
            cached_info = await self._load_billing_cache()
            if cached_info:
                return cached_info

        # Fetch from API
        try:
            api_key = self._get_api_key()
            if not api_key:
                return None

            billing_info = await self._fetch_billing_info(api_key)
            if billing_info:
                await self._save_billing_cache(billing_info)
                self._billing_info = billing_info
                self._billing_cache_time = datetime.now()

            return billing_info

        except Exception as e:
            print(f"Failed to fetch billing info: {e}")
            return None

    async def get_model_pricing(self, model: str, force_refresh: bool = False) -> Optional[ModelPricing]:
        """Get pricing information for a specific model.

        Args:
            model: Model name (e.g., "anthropic/claude-sonnet-4")
            force_refresh: Force API call instead of using cache

        Returns:
            ModelPricing object or None if not found
        """
        # Check memory cache
        if not force_refresh and model in self._model_pricing:
            return self._model_pricing[model]

        # Load all pricing if needed
        await self._ensure_pricing_cache(force_refresh)

        return self._model_pricing.get(model)

    async def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a session with given token usage.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in dollars
        """
        pricing = await self.get_model_pricing(model)
        if not pricing:
            # Fallback to default pricing if model not found
            return self._estimate_cost_fallback(input_tokens, output_tokens)

        input_cost = input_tokens * pricing.input_cost_per_token
        output_cost = output_tokens * pricing.output_cost_per_token

        return input_cost + output_cost

    def record_usage(self, model: str, input_tokens: int, output_tokens: int, cost: float) -> None:
        """Record usage for analytics.

        Args:
            model: Model used
            input_tokens: Input tokens consumed
            output_tokens: Output tokens generated
            cost: Actual cost charged
        """
        record = UsageRecord(
            timestamp=datetime.now(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost
        )

        self._usage_records.append(record)

        # Keep only last 30 days
        cutoff = datetime.now() - timedelta(days=30)
        self._usage_records = [r for r in self._usage_records if r.timestamp > cutoff]

    def get_usage_stats(self, days: int = 1) -> Dict[str, Any]:
        """Get usage statistics for the last N days.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with usage statistics
        """
        cutoff = datetime.now() - timedelta(days=days)
        recent_records = [r for r in self._usage_records if r.timestamp > cutoff]

        if not recent_records:
            return {
                "total_cost": 0.0,
                "total_tokens": 0,
                "session_count": 0,
                "models_used": [],
                "average_cost_per_session": 0.0
            }

        total_cost = sum(r.cost for r in recent_records)
        total_input_tokens = sum(r.input_tokens for r in recent_records)
        total_output_tokens = sum(r.output_tokens for r in recent_records)
        total_tokens = total_input_tokens + total_output_tokens
        session_count = len(recent_records)
        models_used = list(set(r.model for r in recent_records))

        return {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "session_count": session_count,
            "models_used": models_used,
            "average_cost_per_session": total_cost / session_count if session_count > 0 else 0.0
        }

    async def _fetch_billing_info(self, api_key: str) -> Optional[BillingInfo]:
        """Fetch billing info from OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            url = f"{self.API_BASE}{self.ACCOUNT_ENDPOINT}"
            req = urllib.request.Request(url, headers=headers, method='GET')

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, urllib.request.urlopen, req)

            if response.status == 200:
                data = json.loads(response.read().decode())
                return self._parse_billing_response(data)
            else:
                print(f"Billing API error: {response.status}")
                return None

        except Exception as e:
            print(f"Error fetching billing info: {e}")
            return None

    async def _ensure_pricing_cache(self, force_refresh: bool = False) -> None:
        """Ensure pricing cache is loaded and current."""
        # Check if we need to refresh
        if not force_refresh and self._is_pricing_cache_valid():
            return

        # Try to load from file cache
        if not force_refresh:
            cached_pricing = await self._load_pricing_cache()
            if cached_pricing:
                self._model_pricing = cached_pricing
                self._pricing_cache_time = datetime.now()
                return

        # Fetch from API
        try:
            pricing_data = await self._fetch_model_pricing()
            if pricing_data:
                await self._save_pricing_cache(pricing_data)
                self._model_pricing = pricing_data
                self._pricing_cache_time = datetime.now()

        except Exception as e:
            print(f"Failed to fetch model pricing: {e}")

    async def _fetch_model_pricing(self) -> Dict[str, ModelPricing]:
        """Fetch model pricing from OpenRouter API."""
        try:
            url = f"{self.API_BASE}{self.MODELS_ENDPOINT}"
            req = urllib.request.Request(url, method='GET')

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, urllib.request.urlopen, req)

            if response.status == 200:
                data = json.loads(response.read().decode())
                return self._parse_pricing_response(data)
            else:
                print(f"Pricing API error: {response.status}")
                return {}

        except Exception as e:
            print(f"Error fetching model pricing: {e}")
            return {}

    def _parse_billing_response(self, data: Dict[str, Any]) -> BillingInfo:
        """Parse billing response from OpenRouter API."""
        # This would parse the actual API response format
        # For now, placeholder implementation
        return BillingInfo(
            balance=data.get("balance", 0.0),
            monthly_limit=data.get("monthly_limit"),
            monthly_usage=data.get("monthly_usage", 0.0),
            rate_limit_requests=data.get("rate_limit_requests"),
            rate_limit_remaining=data.get("rate_limit_remaining"),
        )

    def _parse_pricing_response(self, data: Dict[str, Any]) -> Dict[str, ModelPricing]:
        """Parse pricing response from OpenRouter API."""
        pricing_map = {}

        # Parse the models data
        models = data.get("data", [])
        for model_data in models:
            model_id = model_data.get("id", "")
            pricing_info = model_data.get("pricing", {})

            if model_id and pricing_info:
                pricing = ModelPricing(
                    model=model_id,
                    input_cost_per_token=float(pricing_info.get("prompt", 0.0)),
                    output_cost_per_token=float(pricing_info.get("completion", 0.0)),
                    context_length=model_data.get("context_length", 0)
                )
                pricing_map[model_id] = pricing

        return pricing_map

    async def _load_billing_cache(self) -> Optional[BillingInfo]:
        """Load billing info from file cache."""
        try:
            if not self.BILLING_CACHE_FILE.exists():
                return None

            with open(self.BILLING_CACHE_FILE, 'r') as f:
                data = json.load(f)

            # Check if cache is still fresh
            cache_time = datetime.fromisoformat(data.get("timestamp", ""))
            if datetime.now() - cache_time > timedelta(seconds=self.BILLING_CACHE_TTL):
                return None

            billing_data = data.get("billing_info", {})
            return BillingInfo(**billing_data)

        except Exception:
            return None

    async def _save_billing_cache(self, billing_info: BillingInfo) -> None:
        """Save billing info to file cache."""
        try:
            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "billing_info": {
                    "balance": billing_info.balance,
                    "monthly_limit": billing_info.monthly_limit,
                    "monthly_usage": billing_info.monthly_usage,
                    "rate_limit_requests": billing_info.rate_limit_requests,
                    "rate_limit_remaining": billing_info.rate_limit_remaining,
                }
            }

            with open(self.BILLING_CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)

        except Exception as e:
            print(f"Failed to save billing cache: {e}")

    async def _load_pricing_cache(self) -> Optional[Dict[str, ModelPricing]]:
        """Load pricing info from file cache."""
        try:
            if not self.PRICING_CACHE_FILE.exists():
                return None

            with open(self.PRICING_CACHE_FILE, 'r') as f:
                data = json.load(f)

            # Check if cache is still fresh
            cache_time = datetime.fromisoformat(data.get("timestamp", ""))
            if datetime.now() - cache_time > timedelta(seconds=self.PRICING_CACHE_TTL):
                return None

            pricing_data = data.get("pricing", {})
            pricing_map = {}

            for model_id, pricing_info in pricing_data.items():
                pricing_map[model_id] = ModelPricing(**pricing_info)

            return pricing_map

        except Exception:
            return None

    async def _save_pricing_cache(self, pricing_data: Dict[str, ModelPricing]) -> None:
        """Save pricing info to file cache."""
        try:
            serializable_data = {}
            for model_id, pricing in pricing_data.items():
                serializable_data[model_id] = {
                    "model": pricing.model,
                    "input_cost_per_token": pricing.input_cost_per_token,
                    "output_cost_per_token": pricing.output_cost_per_token,
                    "context_length": pricing.context_length
                }

            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "pricing": serializable_data
            }

            with open(self.PRICING_CACHE_FILE, 'w') as f:
                json.dump(cache_data, f)

        except Exception as e:
            print(f"Failed to save pricing cache: {e}")

    def _is_billing_cache_valid(self) -> bool:
        """Check if billing cache is still valid."""
        if not self._billing_cache_time:
            return False

        age = datetime.now() - self._billing_cache_time
        return age.total_seconds() < self.BILLING_CACHE_TTL

    def _is_pricing_cache_valid(self) -> bool:
        """Check if pricing cache is still valid."""
        if not self._pricing_cache_time:
            return False

        age = datetime.now() - self._pricing_cache_time
        return age.total_seconds() < self.PRICING_CACHE_TTL

    def _get_api_key(self) -> Optional[str]:
        """Get OpenRouter API key from settings or environment."""
        if self._settings and self._settings.api_key:
            return self._settings.api_key

        import os
        return os.environ.get("OPENROUTER_API_KEY")

    def _estimate_cost_fallback(self, input_tokens: int, output_tokens: int) -> float:
        """Fallback cost estimation when model pricing is not available."""
        # Use average pricing from common models as fallback
        # These are approximate rates as of December 2024
        input_rate = 0.000003  # $3 per million tokens
        output_rate = 0.000015  # $15 per million tokens

        return (input_tokens * input_rate) + (output_tokens * output_rate)