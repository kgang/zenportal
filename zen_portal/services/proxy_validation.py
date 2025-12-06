"""Proxy validation for y-router and CLIProxyAPI integration.

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

from .config import ProxySettings, ProxyAuthType


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

    Detects common gotchas:
    - OpenRouter (y-router): Docker not running, missing API key, wrong key format
    - Claude Account (CLIProxyAPI): Not running, not logged in
    """

    # OpenRouter API keys start with this prefix
    OPENROUTER_KEY_PREFIX = "sk-or-"

    # Common proxy ports
    YROUTER_DEFAULT_PORT = 8787
    CLIPROXYAPI_DEFAULT_PORT = 8080

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

        # Use effective_base_url which has mode-appropriate defaults
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
                return self._connectivity_error(settings, host, port, "timeout")
            except ConnectionRefusedError:
                return self._connectivity_error(settings, host, port, "refused")
            except OSError as e:
                return self._connectivity_error(settings, host, port, str(e))
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

        # Use effective_base_url which has mode-appropriate defaults
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
                return self._connectivity_error(settings, host, port, "timeout")
            except ConnectionRefusedError:
                return self._connectivity_error(settings, host, port, "refused")
            except OSError as e:
                return self._connectivity_error(settings, host, port, str(e))
        except Exception as e:
            return ProxyCheckResult(
                ProxyStatus.ERROR,
                f"Connection check failed: {e}",
            )

    def _connectivity_error(
        self,
        settings: ProxySettings,
        host: str,
        port: int,
        reason: str,
    ) -> ProxyCheckResult:
        """Generate connectivity error with context-specific hints."""
        auth_type = ProxyAuthType.normalize(settings.auth_type)

        if auth_type == ProxyAuthType.OPENROUTER:
            hint = "Is y-router running? Try: docker-compose up -d"
        elif auth_type == ProxyAuthType.CLAUDE_ACCOUNT:
            hint = "Is CLIProxyAPI running? Try: ./cli-proxy-api --help"
        else:
            hint = f"Check if proxy is running on {host}:{port}"

        return ProxyCheckResult(
            ProxyStatus.ERROR,
            f"Cannot connect to {host}:{port} ({reason})",
            hint=hint,
        )

    def _check_credentials(
        self,
        settings: ProxySettings,
    ) -> ProxyCheckResult:
        """Check if required credentials are configured."""
        if not settings.enabled:
            return ProxyCheckResult(ProxyStatus.OK, "Proxy disabled")

        auth_type = ProxyAuthType.normalize(settings.auth_type)

        if auth_type == ProxyAuthType.CLAUDE_ACCOUNT:
            # Claude Account mode: CLIProxyAPI handles auth internally
            return ProxyCheckResult(
                ProxyStatus.OK,
                "Claude Account mode (proxy handles auth)",
                hint="Ensure CLIProxyAPI is logged in: ./cli-proxy-api --claude-login",
            )

        if auth_type == ProxyAuthType.OPENROUTER:
            # OpenRouter mode: need API key
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

        # OAuth mode (deprecated): need bearer token
        token = settings.oauth_token or os.environ.get("CLAUDE_OAUTH_TOKEN", "")
        if not token:
            return ProxyCheckResult(
                ProxyStatus.ERROR,
                "OAuth token not configured",
                hint="Consider using Claude Account mode instead",
            )
        return ProxyCheckResult(
            ProxyStatus.OK,
            "OAuth token configured",
            hint="OAuth mode is deprecated. Consider Claude Account mode.",
        )

    def _check_configuration(
        self,
        settings: ProxySettings,
    ) -> ProxyCheckResult:
        """Check for common configuration issues."""
        if not settings.enabled:
            return ProxyCheckResult(ProxyStatus.OK, "Proxy disabled")

        issues = []
        hints = []

        auth_type = ProxyAuthType.normalize(settings.auth_type)
        has_api_key = bool(settings.api_key or os.environ.get("OPENROUTER_API_KEY"))

        # Check for localhost vs remote URL mismatch with auth type
        base_url = settings.effective_base_url
        parsed = urlparse(base_url)
        is_localhost = parsed.hostname in ("localhost", "127.0.0.1", "::1")

        if not is_localhost and auth_type == ProxyAuthType.CLAUDE_ACCOUNT:
            issues.append("Claude Account mode with remote URL")
            hints.append("Claude Account mode is for local CLIProxyAPI; use OpenRouter for remote")

        # Check model format for OpenRouter
        if settings.default_model and auth_type == ProxyAuthType.OPENROUTER:
            model = settings.default_model
            if "/" not in model:
                issues.append(f"Model '{model}' missing provider prefix")
                hints.append("OpenRouter uses 'provider/model' format (e.g., anthropic/claude-sonnet-4)")

        # Check for credential mismatch
        if auth_type == ProxyAuthType.OPENROUTER and not has_api_key:
            issues.append("OpenRouter mode needs API key")
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
        auth_type = ProxyAuthType.normalize(settings.auth_type)
        auth_desc = {
            ProxyAuthType.OPENROUTER: "OpenRouter",
            ProxyAuthType.CLAUDE_ACCOUNT: "Claude Account",
        }.get(auth_type, "custom")
        return f"proxy: {auth_desc}"

    return f"proxy: {result.summary}"


def get_proxy_auth_hint(auth_type: ProxyAuthType) -> str:
    """Get setup hint for the given auth type.

    Args:
        auth_type: The authentication type

    Returns:
        Setup instruction hint
    """
    auth_type = ProxyAuthType.normalize(auth_type)
    hints = {
        ProxyAuthType.OPENROUTER: "Get key from openrouter.ai/keys",
        ProxyAuthType.CLAUDE_ACCOUNT: "Run: ./cli-proxy-api --claude-login",
    }
    return hints.get(auth_type, "")
