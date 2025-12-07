"""Enhanced proxy monitoring service with real-time status and billing integration.

Provides comprehensive proxy health monitoring, billing status tracking,
and proactive issue detection for y-router/OpenRouter integration.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Callable, Any
from pathlib import Path
import json

from ..config import ProxySettings
from .validation import ProxyValidator, ProxyValidationResult, ProxyStatus
from .models import OpenRouterModelsService


class ProxyHealthStatus(Enum):
    """Enhanced proxy health status levels."""

    EXCELLENT = "excellent"  # Fast response, no issues
    GOOD = "good"           # Normal operation
    DEGRADED = "degraded"   # Slow but working
    WARNING = "warning"     # Issues detected but functional
    ERROR = "error"         # Not working
    UNKNOWN = "unknown"     # Not tested yet


@dataclass
class ProxyMetrics:
    """Real-time proxy performance metrics."""

    # Connectivity metrics
    response_time_ms: float = 0.0
    last_check_time: datetime = field(default_factory=datetime.now)
    consecutive_failures: int = 0
    success_rate: float = 100.0  # Percentage over last 24h

    # Billing metrics (from OpenRouter API)
    account_balance: Optional[float] = None
    monthly_usage: Optional[float] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None

    # Session metrics
    active_sessions: int = 0
    total_tokens_today: int = 0
    estimated_cost_today: float = 0.0


@dataclass
class ProxyStatusEvent:
    """Event fired when proxy status changes."""

    old_status: ProxyHealthStatus
    new_status: ProxyHealthStatus
    message: str
    metrics: ProxyMetrics
    timestamp: datetime = field(default_factory=datetime.now)


class ProxyMonitor:
    """Enhanced proxy monitoring with real-time status and billing integration.

    Features:
    - Periodic connectivity and health checks
    - OpenRouter API billing status integration
    - Proactive issue detection and notifications
    - Performance metrics tracking
    - Session-level proxy status
    """

    # Monitoring intervals
    HEALTH_CHECK_INTERVAL = 30.0  # seconds
    BILLING_CHECK_INTERVAL = 300.0  # 5 minutes
    FAST_CHECK_INTERVAL = 10.0  # when issues detected

    # Performance thresholds
    EXCELLENT_THRESHOLD_MS = 200
    GOOD_THRESHOLD_MS = 500
    DEGRADED_THRESHOLD_MS = 2000

    # Failure thresholds
    MAX_CONSECUTIVE_FAILURES = 3
    MIN_SUCCESS_RATE = 85.0  # percentage

    def __init__(self, settings: Optional[ProxySettings] = None):
        self._settings = settings
        self._validator = ProxyValidator(settings)
        self._openrouter = OpenRouterModelsService()

        # Current state
        self._status = ProxyHealthStatus.UNKNOWN
        self._metrics = ProxyMetrics()
        self._last_validation = None

        # Monitoring state
        self._monitoring_task: Optional[asyncio.Task] = None
        self._billing_task: Optional[asyncio.Task] = None
        self._is_running = False

        # Event callbacks
        self._status_callbacks: list[Callable[[ProxyStatusEvent], None]] = []

        # Performance tracking
        self._response_times: list[tuple[datetime, float]] = []  # (timestamp, ms)
        self._check_results: list[tuple[datetime, bool]] = []  # (timestamp, success)

    @property
    def status(self) -> ProxyHealthStatus:
        """Current proxy health status."""
        return self._status

    @property
    def metrics(self) -> ProxyMetrics:
        """Current proxy metrics."""
        return self._metrics

    @property
    def last_validation(self) -> Optional[ProxyValidationResult]:
        """Last validation result."""
        return self._last_validation

    def add_status_callback(self, callback: Callable[[ProxyStatusEvent], None]) -> None:
        """Add callback for status change events."""
        self._status_callbacks.append(callback)

    def remove_status_callback(self, callback: Callable[[ProxyStatusEvent], None]) -> None:
        """Remove status change callback."""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)

    async def start_monitoring(self) -> None:
        """Start continuous proxy monitoring."""
        if self._is_running:
            return

        self._is_running = True

        # Start monitoring tasks
        self._monitoring_task = asyncio.create_task(self._monitor_loop())
        self._billing_task = asyncio.create_task(self._billing_loop())

    async def stop_monitoring(self) -> None:
        """Stop proxy monitoring."""
        self._is_running = False

        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        if self._billing_task:
            self._billing_task.cancel()
            try:
                await self._billing_task
            except asyncio.CancelledError:
                pass

    async def check_status_now(self) -> ProxyValidationResult:
        """Perform immediate status check."""
        if not self._settings or not self._settings.enabled:
            return await self._handle_disabled_status()

        start_time = time.time()
        validation = await self._validator.validate_async(self._settings)
        response_time = (time.time() - start_time) * 1000

        # Update metrics
        self._metrics.response_time_ms = response_time
        self._metrics.last_check_time = datetime.now()

        # Track performance
        self._record_response_time(response_time)
        self._record_check_result(validation.is_ok)

        # Update status based on validation and performance
        old_status = self._status
        self._status = self._determine_health_status(validation, response_time)

        # Fire status change event
        if old_status != self._status:
            event = ProxyStatusEvent(
                old_status=old_status,
                new_status=self._status,
                message=self._get_status_message(validation),
                metrics=self._metrics
            )
            self._fire_status_event(event)

        self._last_validation = validation
        return validation

    def get_status_display(self, include_details: bool = False) -> str:
        """Get formatted status string for display.

        Args:
            include_details: Include metrics like latency, cost

        Returns:
            Status string like:
            Simple: "● openrouter" or "⚠ openrouter (timeout)"
            Detailed: "● openrouter (12ms) $4.23 remaining"
        """
        if not self._settings or not self._settings.enabled:
            return "proxy: disabled"

        # Status symbol
        symbols = {
            ProxyHealthStatus.EXCELLENT: "●",
            ProxyHealthStatus.GOOD: "●",
            ProxyHealthStatus.DEGRADED: "◐",
            ProxyHealthStatus.WARNING: "⚠",
            ProxyHealthStatus.ERROR: "⚠",
            ProxyHealthStatus.UNKNOWN: "○",
        }
        symbol = symbols.get(self._status, "?")

        # Base status
        base = f"{symbol} openrouter"

        # Add error/warning context
        if self._status in [ProxyHealthStatus.ERROR, ProxyHealthStatus.WARNING, ProxyHealthStatus.DEGRADED]:
            if self._last_validation and not self._last_validation.is_ok:
                base += f" ({self._last_validation.summary})"
            elif self._status == ProxyHealthStatus.DEGRADED:
                base += f" (slow)"

        # Add details if requested
        if include_details and self._status not in [ProxyHealthStatus.ERROR, ProxyHealthStatus.UNKNOWN]:
            details = []

            # Response time
            if self._metrics.response_time_ms > 0:
                details.append(f"{int(self._metrics.response_time_ms)}ms")

            # Account balance
            if self._metrics.account_balance is not None:
                details.append(f"${self._metrics.account_balance:.2f} remaining")

            if details:
                base += f" ({', '.join(details)})"

        return base

    def get_session_status(self, session_uses_proxy: bool, model: Optional[str] = None) -> str:
        """Get proxy status string for a specific session.

        Args:
            session_uses_proxy: Whether this session uses proxy billing
            model: Model name for this session

        Returns:
            Status string like "● openrouter (claude-sonnet-4.5)" or "direct"
        """
        if not session_uses_proxy:
            return "direct"

        if not self._settings or not self._settings.enabled:
            return "proxy disabled"

        symbol = "●" if self._status in [ProxyHealthStatus.EXCELLENT, ProxyHealthStatus.GOOD] else "⚠"

        if model:
            # Show just the model name part (strip provider prefix)
            model_display = model.split('/')[-1] if '/' in model else model
            return f"{symbol} openrouter ({model_display})"
        else:
            return f"{symbol} openrouter"

    def estimate_session_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Estimate cost for a session with given token usage."""
        # This would integrate with the existing token parser logic
        # For now, return 0 as placeholder
        return 0.0

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._is_running:
            try:
                await self.check_status_now()

                # Use faster interval if we have issues
                interval = (self.FAST_CHECK_INTERVAL
                          if self._status in [ProxyHealthStatus.ERROR, ProxyHealthStatus.WARNING]
                          else self.HEALTH_CHECK_INTERVAL)

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but continue monitoring
                print(f"Proxy monitor error: {e}")
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)

    async def _billing_loop(self) -> None:
        """Billing status monitoring loop."""
        while self._is_running:
            try:
                if self._settings and self._settings.enabled:
                    await self._update_billing_metrics()

                await asyncio.sleep(self.BILLING_CHECK_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but continue
                print(f"Billing monitor error: {e}")
                await asyncio.sleep(self.BILLING_CHECK_INTERVAL)

    async def _update_billing_metrics(self) -> None:
        """Update billing metrics from OpenRouter API."""
        try:
            # This would call OpenRouter API to get account info
            # For now, placeholder implementation

            # Example API call (to be implemented):
            # account_info = await self._openrouter.get_account_info(api_key)
            # self._metrics.account_balance = account_info.get('balance')
            # self._metrics.rate_limit_remaining = account_info.get('rate_limit_remaining')

            pass

        except Exception as e:
            # Log but don't fail monitoring
            print(f"Failed to update billing metrics: {e}")

    async def _handle_disabled_status(self) -> ProxyValidationResult:
        """Handle case where proxy is disabled."""
        from .proxy_validation import ProxyCheckResult

        self._status = ProxyHealthStatus.UNKNOWN

        return ProxyValidationResult(
            connectivity=ProxyCheckResult(ProxyStatus.OK, "Proxy disabled"),
            credentials=ProxyCheckResult(ProxyStatus.OK, "Proxy disabled"),
            configuration=ProxyCheckResult(ProxyStatus.OK, "Proxy disabled"),
        )

    def _determine_health_status(self, validation: ProxyValidationResult, response_time: float) -> ProxyHealthStatus:
        """Determine health status from validation and performance metrics."""
        if not validation.is_ok:
            if validation.has_errors:
                return ProxyHealthStatus.ERROR
            else:
                return ProxyHealthStatus.WARNING

        # Check performance thresholds
        if response_time <= self.EXCELLENT_THRESHOLD_MS:
            return ProxyHealthStatus.EXCELLENT
        elif response_time <= self.GOOD_THRESHOLD_MS:
            return ProxyHealthStatus.GOOD
        elif response_time <= self.DEGRADED_THRESHOLD_MS:
            return ProxyHealthStatus.DEGRADED
        else:
            return ProxyHealthStatus.WARNING

    def _get_status_message(self, validation: ProxyValidationResult) -> str:
        """Get human-readable status message."""
        if validation.is_ok:
            if self._metrics.response_time_ms <= self.EXCELLENT_THRESHOLD_MS:
                return "Proxy operating optimally"
            elif self._metrics.response_time_ms <= self.GOOD_THRESHOLD_MS:
                return "Proxy operating normally"
            else:
                return "Proxy responding slowly"
        else:
            return validation.summary

    def _record_response_time(self, response_time_ms: float) -> None:
        """Record response time for performance tracking."""
        now = datetime.now()
        self._response_times.append((now, response_time_ms))

        # Keep only last 24 hours
        cutoff = now - timedelta(hours=24)
        self._response_times = [(t, rt) for t, rt in self._response_times if t > cutoff]

    def _record_check_result(self, success: bool) -> None:
        """Record check result for success rate tracking."""
        now = datetime.now()
        self._check_results.append((now, success))

        # Keep only last 24 hours
        cutoff = now - timedelta(hours=24)
        self._check_results = [(t, s) for t, s in self._check_results if t > cutoff]

        # Update success rate
        if self._check_results:
            successes = sum(1 for _, success in self._check_results if success)
            self._metrics.success_rate = (successes / len(self._check_results)) * 100

        # Update consecutive failures
        if success:
            self._metrics.consecutive_failures = 0
        else:
            self._metrics.consecutive_failures += 1

    def _fire_status_event(self, event: ProxyStatusEvent) -> None:
        """Fire status change event to all callbacks."""
        for callback in self._status_callbacks:
            try:
                callback(event)
            except Exception as e:
                # Log but don't let callback errors affect monitoring
                print(f"Proxy status callback error: {e}")