"""Proxy validation for y-router integration.

Provides connectivity checks and configuration validation to detect
common gotchas before session creation.
"""

import asyncio
import os
import socket
from dataclasses import dataclass
from enum import Enum
from typing import Callable
from urllib.parse import urlparse

from .config import ProxySettings


class ProxyStatus(Enum):
    """Status of proxy validation check."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class ProxyCheckResult:
    """Result of a proxy validation check."""

    status: ProxyStatus
    message: str
    hint: str = ""

    @property
    def is_ok(self) -> bool:
        return self.status == ProxyStatus.OK

    @property
    def is_error(self) -> bool:
        return self.status == ProxyStatus.ERROR


@dataclass
class ProxyValidationResult:
    """Aggregated results of all proxy validation checks."""

    connectivity: ProxyCheckResult
    credentials: ProxyCheckResult
    configuration: ProxyCheckResult

    @property
    def is_ok(self) -> bool:
        """All checks passed."""
        return all([
            self.connectivity.is_ok,
            self.credentials.is_ok,
            self.configuration.is_ok,
        ])

    @property
    def has_errors(self) -> bool:
        """Any check failed with error."""
        return any([
            self.connectivity.is_error,
            self.credentials.is_error,
            self.configuration.is_error,
        ])

    @property
    def summary(self) -> str:
        """Single-line summary of validation state."""
        if self.is_ok:
            return "proxy ready"
        errors = []
        if self.connectivity.is_error:
            errors.append("unreachable")
        if self.credentials.is_error:
            errors.append("no credentials")
        if self.configuration.is_error:
            errors.append("misconfigured")
        return ", ".join(errors) if errors else "check warnings"


class ProxyValidator:
    """Validates proxy configuration and connectivity.

    Detects common gotchas for y-router:
    - Docker not running
    - Missing API key
    - Wrong key format
    """

    # OpenRouter API keys start with this prefix
    OPENROUTER_KEY_PREFIX = "sk-or-"

    # Default port for y-router
    YROUTER_DEFAULT_PORT = 8787

    # Connection timeout in seconds
    CONNECTIVITY_TIMEOUT = 2.0

    def __init__(self, settings: ProxySettings | None = None):
        self._settings = settings

    def validate_sync(
        self,
        settings: ProxySettings | None = None,
    ) -> ProxyValidationResult:
        """Synchronous validation (connectivity check is blocking).

        Args:
            settings: Proxy settings to validate (uses instance settings if None)

        Returns:
            ProxyValidationResult with all check results
        """
        settings = settings or self._settings
        if not settings:
            return ProxyValidationResult(
                connectivity=ProxyCheckResult(ProxyStatus.UNKNOWN, "No settings"),
                credentials=ProxyCheckResult(ProxyStatus.UNKNOWN, "No settings"),
                configuration=ProxyCheckResult(ProxyStatus.UNKNOWN, "No settings"),
            )

        return ProxyValidationResult(
            connectivity=self._check_connectivity(settings),
            credentials=self._check_credentials(settings),
            configuration=self._check_configuration(settings),
        )

    async def validate_async(
        self,
        settings: ProxySettings | None = None,
    ) -> ProxyValidationResult:
        """Async validation with non-blocking connectivity check.

        Args:
            settings: Proxy settings to validate (uses instance settings if None)

        Returns:
            ProxyValidationResult with all check results
        """
        settings = settings or self._settings
        if not settings:
            return ProxyValidationResult(
                connectivity=ProxyCheckResult(ProxyStatus.UNKNOWN, "No settings"),
                credentials=ProxyCheckResult(ProxyStatus.UNKNOWN, "No settings"),
                configuration=ProxyCheckResult(ProxyStatus.UNKNOWN, "No settings"),
            )

        connectivity = await self._check_connectivity_async(settings)
        credentials = self._check_credentials(settings)
        configuration = self._check_configuration(settings)

        return ProxyValidationResult(
            connectivity=connectivity,
            credentials=credentials,
            configuration=configuration,
        )

    def _check_connectivity(
        self,
        settings: ProxySettings,
    ) -> ProxyCheckResult:
        """Check if proxy URL is reachable (sync)."""
        if not settings.enabled:
            return ProxyCheckResult(ProxyStatus.OK, "Proxy disabled")

        base_url = settings.effective_base_url

        try:
            parsed = urlparse(base_url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)

            if not host:
                return ProxyCheckResult(
                    ProxyStatus.ERROR,
                    "Invalid proxy URL",
                    hint="URL must include host",
                )

            # Try to connect
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.CONNECTIVITY_TIMEOUT)
            try:
                sock.connect((host, port))
                return ProxyCheckResult(ProxyStatus.OK, f"Connected to {host}:{port}")
            except socket.timeout:
                return self._connectivity_error(host, port, "timeout")
            except ConnectionRefusedError:
                return self._connectivity_error(host, port, "refused")
            except OSError as e:
                return self._connectivity_error(host, port, str(e))
            finally:
                sock.close()
        except Exception as e:
            return ProxyCheckResult(
                ProxyStatus.ERROR,
                f"Connection check failed: {e}",
            )

    async def _check_connectivity_async(
        self,
        settings: ProxySettings,
    ) -> ProxyCheckResult:
        """Check if proxy URL is reachable (async)."""
        if not settings.enabled:
            return ProxyCheckResult(ProxyStatus.OK, "Proxy disabled")

        base_url = settings.effective_base_url

        try:
            parsed = urlparse(base_url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)

            if not host:
                return ProxyCheckResult(
                    ProxyStatus.ERROR,
                    "Invalid proxy URL",
                    hint="URL must include host",
                )

            # Async connection attempt
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=self.CONNECTIVITY_TIMEOUT,
                )
                writer.close()
                await writer.wait_closed()
                return ProxyCheckResult(ProxyStatus.OK, f"Connected to {host}:{port}")
            except asyncio.TimeoutError:
                return self._connectivity_error(host, port, "timeout")
            except ConnectionRefusedError:
                return self._connectivity_error(host, port, "refused")
            except OSError as e:
                return self._connectivity_error(host, port, str(e))
        except Exception as e:
            return ProxyCheckResult(
                ProxyStatus.ERROR,
                f"Connection check failed: {e}",
            )

    def _connectivity_error(
        self,
        host: str,
        port: int,
        reason: str,
    ) -> ProxyCheckResult:
        """Generate connectivity error with y-router hint."""
        return ProxyCheckResult(
            ProxyStatus.ERROR,
            f"Cannot connect to {host}:{port} ({reason})",
            hint="Is y-router running? Try: docker-compose up -d",
        )

    def _check_credentials(
        self,
        settings: ProxySettings,
    ) -> ProxyCheckResult:
        """Check if API key is configured."""
        if not settings.enabled:
            return ProxyCheckResult(ProxyStatus.OK, "Proxy disabled")

        api_key = settings.api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            return ProxyCheckResult(
                ProxyStatus.ERROR,
                "OpenRouter API key not configured",
                hint="Get key from openrouter.ai/keys, set in settings or OPENROUTER_API_KEY env",
            )

        # Check for OpenRouter key format
        if not api_key.startswith(self.OPENROUTER_KEY_PREFIX):
            return ProxyCheckResult(
                ProxyStatus.WARNING,
                f"API key doesn't start with '{self.OPENROUTER_KEY_PREFIX}'",
                hint="OpenRouter keys start with 'sk-or-'. Is this the right key?",
            )

        return ProxyCheckResult(ProxyStatus.OK, "OpenRouter API key configured")

    def _check_configuration(
        self,
        settings: ProxySettings,
    ) -> ProxyCheckResult:
        """Check for common configuration issues."""
        if not settings.enabled:
            return ProxyCheckResult(ProxyStatus.OK, "Proxy disabled")

        issues = []
        hints = []
        has_api_key = bool(settings.api_key or os.environ.get("OPENROUTER_API_KEY"))

        # Check model format for OpenRouter
        if settings.default_model:
            model = settings.default_model
            if "/" not in model:
                issues.append(f"Model '{model}' missing provider prefix")
                hints.append("OpenRouter uses 'provider/model' format (e.g., anthropic/claude-sonnet-4)")

        # Check for missing API key
        if not has_api_key:
            issues.append("API key not configured")
            hints.append("Get key from openrouter.ai/keys")

        if issues:
            return ProxyCheckResult(
                ProxyStatus.WARNING,
                "; ".join(issues),
                hint=hints[0] if hints else "",
            )

        return ProxyCheckResult(ProxyStatus.OK, "Configuration valid")


def validate_proxy_settings(
    settings: ProxySettings | None,
    on_complete: Callable[[ProxyValidationResult], None] | None = None,
) -> ProxyValidationResult:
    """Convenience function for synchronous proxy validation.

    Args:
        settings: Proxy settings to validate
        on_complete: Optional callback with results

    Returns:
        ProxyValidationResult with all check results
    """
    validator = ProxyValidator(settings)
    result = validator.validate_sync()
    if on_complete:
        on_complete(result)
    return result


def get_proxy_status_line(settings: ProxySettings | None) -> str:
    """Get a one-line status summary for display.

    Args:
        settings: Proxy settings to check

    Returns:
        Status line like "proxy: ready" or "proxy: unreachable"
    """
    if not settings or not settings.enabled:
        return "proxy: disabled"

    validator = ProxyValidator(settings)
    result = validator.validate_sync()

    if result.is_ok:
        return "proxy: y-router"

    return f"proxy: {result.summary}"
