"""Base screen class with notification support."""

from textual.app import ComposeResult
from textual.screen import Screen

from ..widgets.notification import ZenNotificationRack
from ..services.notification import NotificationRequest


class ZenScreen(Screen):
    """Base screen with automatic notification rack.

    All screens should inherit from this to ensure consistent
    notification support across the application.

    The notification rack is mounted in an overlay layer and
    positioned at bottom-right, above any hint bars.
    """

    DEFAULT_CSS = """
    ZenScreen {
        layers: base notification;
    }

    ZenScreen > ZenNotificationRack {
        dock: bottom;
        layer: notification;
        height: auto;
        width: 100%;
        align: right bottom;
        margin-bottom: 2;
    }
    """

    def compose(self) -> ComposeResult:
        """Override in subclass - call super().compose() at END to add notification rack."""
        yield ZenNotificationRack(id="notifications")

    def on_notification_request(self, event: NotificationRequest) -> None:
        """Handle notification requests on this screen."""
        try:
            rack = self.query_one("#notifications", ZenNotificationRack)
            rack.show(event.message, event.severity, event.timeout)
        except Exception:
            pass  # Rack not mounted yet, ignore
