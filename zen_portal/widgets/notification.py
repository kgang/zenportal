"""Zen-styled notification widget for zen-portal."""

from textual.containers import Container
from textual.widgets import Static

from ..services.notification import NotificationSeverity


class ZenNotification(Static):
    """Minimal zen-styled notification widget."""

    def __init__(
        self,
        message: str,
        severity: NotificationSeverity = NotificationSeverity.SUCCESS,
        timeout: float = 3.0,
    ):
        super().__init__(message)
        self._timeout = timeout
        self._severity = severity

    def on_mount(self) -> None:
        """Apply severity class and start auto-dismiss timer."""
        self.add_class(f"-{self._severity.value}")
        self.set_timer(self._timeout, self._dismiss)

    def _dismiss(self) -> None:
        """Remove notification with fade-out."""
        self.add_class("-dismissing")
        # Remove after fade animation completes
        self.set_timer(0.15, self.remove)


class ZenNotificationRack(Container):
    """Container managing notification display.

    Hides itself when empty to prevent layout participation.
    Shows only when a notification is active.
    """

    def on_mount(self) -> None:
        """Start hidden - no notifications yet."""
        self.display = False

    def show(
        self,
        message: str,
        severity: NotificationSeverity = NotificationSeverity.SUCCESS,
        timeout: float = 3.0,
    ) -> None:
        """Display notification, replacing any current one."""
        # Remove existing notifications
        for child in self.children:
            child.remove()

        # Mount new notification and show rack
        notification = ZenNotification(message, severity, timeout)
        self.mount(notification)
        self.display = True

    def _hide_if_empty(self) -> None:
        """Hide rack when no notifications remain."""
        if not self.children:
            self.display = False

    def on_descendant_removed(self, event) -> None:
        """Called when a child is removed - check if we should hide."""
        # Schedule the check after the removal is complete
        self.set_timer(0.01, self._hide_if_empty)
