"""Draggable splitter widget for resizable panes."""

from textual.events import MouseDown, MouseMove, MouseUp
from textual.widget import Widget


class VerticalSplitter(Widget):
    """A draggable vertical divider for resizing adjacent panes.

    When dragged, adjusts the width of the target widget.
    Highlights on hover and while dragging to indicate interactivity.
    """

    DEFAULT_CSS = """
    VerticalSplitter {
        width: 1;
        height: 100%;
        background: $surface-lighten-1;
    }

    VerticalSplitter:hover {
        background: $primary-darken-1;
    }

    VerticalSplitter.-dragging {
        background: $primary;
    }
    """

    class SplitterMoved:
        """Message sent when the splitter is dragged."""

        def __init__(self, delta_x: int) -> None:
            self.delta_x = delta_x

    def __init__(
        self,
        target_id: str,
        min_width: int = 20,
        max_width: int = 60,
        **kwargs,
    ) -> None:
        """Initialize the splitter.

        Args:
            target_id: The ID of the widget to resize (left sibling).
            min_width: Minimum width for the target widget.
            max_width: Maximum width for the target widget.
        """
        super().__init__(**kwargs)
        self._target_id = target_id
        self._min_width = min_width
        self._max_width = max_width
        self._dragging = False
        self._drag_start_x: int | None = None
        self._original_width: int | None = None

    def on_mouse_down(self, event: MouseDown) -> None:
        """Start drag operation."""
        self._dragging = True
        self._drag_start_x = event.screen_x
        self.add_class("-dragging")
        self.capture_mouse()
        event.stop()

        # Get current width of target
        try:
            target = self.screen.query_one(f"#{self._target_id}")
            self._original_width = target.size.width
        except Exception:
            self._original_width = None

    def on_mouse_move(self, event: MouseMove) -> None:
        """Handle drag movement."""
        if not self._dragging or self._drag_start_x is None or self._original_width is None:
            return

        # Calculate new width
        delta = event.screen_x - self._drag_start_x
        new_width = self._original_width + delta

        # Clamp to min/max bounds
        new_width = max(self._min_width, min(self._max_width, new_width))

        # Apply new width to target
        try:
            target = self.screen.query_one(f"#{self._target_id}")
            target.styles.width = new_width
        except Exception:
            pass

        event.stop()

    def on_mouse_up(self, event: MouseUp) -> None:
        """End drag operation."""
        if self._dragging:
            self._dragging = False
            self._drag_start_x = None
            self._original_width = None
            self.remove_class("-dragging")
            self.release_mouse()
            event.stop()
