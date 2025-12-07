"""Centralized notification service for zen-portal."""

from dataclasses import dataclass
from enum import Enum

from textual.message import Message


class NotificationSeverity(Enum):
    """Notification severity levels."""

    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    AI = "ai"  # For Zen AI responses (longer timeout)


@dataclass
class NotificationConfig:
    """Default configuration for notification behaviors."""

    success_timeout: float = 3.0
    warning_timeout: float = 4.0
    error_timeout: float = 5.0
    ai_timeout: float = 10.0  # Longer timeout for AI responses


class NotificationRequest(Message):
    """Message requesting a notification be displayed."""

    def __init__(
        self,
        message: str,
        severity: NotificationSeverity = NotificationSeverity.SUCCESS,
        timeout: float = 3.0,
    ):
        self.message = message
        self.severity = severity
        self.timeout = timeout
        super().__init__()


class NotificationService:
    """Centralized notification API with consistent defaults."""

    def __init__(self, config: NotificationConfig | None = None):
        self._config = config or NotificationConfig()

    def success(self, message: str, timeout: float | None = None) -> NotificationRequest:
        """Create success notification request."""
        return NotificationRequest(
            message=message,
            severity=NotificationSeverity.SUCCESS,
            timeout=timeout or self._config.success_timeout,
        )

    def warning(self, message: str, timeout: float | None = None) -> NotificationRequest:
        """Create warning notification request."""
        return NotificationRequest(
            message=message,
            severity=NotificationSeverity.WARNING,
            timeout=timeout or self._config.warning_timeout,
        )

    def error(self, message: str, timeout: float | None = None) -> NotificationRequest:
        """Create error notification request."""
        return NotificationRequest(
            message=message,
            severity=NotificationSeverity.ERROR,
            timeout=timeout or self._config.error_timeout,
        )

    def ai(self, message: str, timeout: float | None = None) -> NotificationRequest:
        """Create AI response notification request (longer timeout)."""
        return NotificationRequest(
            message=message,
            severity=NotificationSeverity.AI,
            timeout=timeout or self._config.ai_timeout,
        )
