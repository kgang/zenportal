"""Base screen classes with notification support."""

from typing import Generic, TypeVar

from textual.app import ComposeResult
from textual.screen import ModalScreen, Screen

from ..widgets.notification import ZenNotificationRack
from ..services.notification import NotificationRequest

# Type variable for modal return types
ModalResultType = TypeVar("ModalResultType", covariant=True)


class ZenScreen(Screen):
    """Base screen with automatic notification rack.

    All screens should inherit from this to ensure consistent
    notification support across the application.

    The notification rack is mounted in an overlay layer and
    positioned at bottom-left (near session list) to reduce eye strain.
    """

    DEFAULT_CSS = """
    ZenScreen {
        layers: base notification;
    }

    ZenScreen > ZenNotificationRack {
        layer: notification;
        dock: bottom;
        height: auto;
        width: auto;
        margin: 0 0 1 1;
        /* display toggled by widget - hidden when empty */
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


class ZenModalScreen(ModalScreen[ModalResultType], Generic[ModalResultType]):
    """Base modal screen with notification support and zen styling.

    Provides:
    - Automatic focus trapping
    - Notification support
    - Escape to dismiss
    - Auto-dismiss after action (optional)

    Subclasses should:
    - Call super().compose() to get notification rack
    - Use modal-base/modal-sm/modal-md/modal-lg CSS classes
    - Use standard dialog structure (Vertical#dialog, dialog-title, dialog-hint)
    """

    # Auto-dismiss delay in seconds (0 = disabled)
    AUTO_DISMISS_DELAY: float = 0

    BINDINGS = [
        ("escape", "dismiss_modal", "Cancel"),
    ]

    def on_mount(self) -> None:
        """Set up modal on mount - subclasses should call super()."""
        self.trap_focus = True

    def action_dismiss_modal(self) -> None:
        """Dismiss with None result."""
        self.dismiss(None)

    def dismiss_after(self, result: ModalResultType, delay: float = 0.5) -> None:
        """Dismiss modal after a short delay (for visual feedback).

        Use this instead of dismiss() when you want the user to briefly
        see the result before the modal closes.
        """
        self.set_timer(delay, lambda: self.dismiss(result))

    def on_notification_request(self, event: NotificationRequest) -> None:
        """Handle notification requests on this screen."""
        try:
            rack = self.query_one("#notifications", ZenNotificationRack)
            rack.show(event.message, event.severity, event.timeout)
        except Exception:
            pass  # Rack not mounted yet, ignore
