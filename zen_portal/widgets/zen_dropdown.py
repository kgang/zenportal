"""ZenDropdown: Base class for collapsible dropdowns with zen styling.

Provides consistent expand/collapse behavior, CSS, and navigation for
dropdowns in the zen-portal config interface.
"""

from abc import abstractmethod

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class ZenDropdown(Static):
    """Base class for collapsible dropdowns with zen styling.

    Provides:
    - Consistent expand/collapse animation
    - j/k/h/l/Esc navigation
    - f/Enter/Space toggle
    - Shared CSS for header/content

    Subclasses must implement:
    - _get_header_text() -> str: Header display text
    - _compose_content() -> ComposeResult: Content inside dropdown
    - _get_focusable_widgets() -> list[Widget]: Focusable items for navigation
    """

    expanded: reactive[bool] = reactive(False)

    # Shared CSS for all dropdowns
    DEFAULT_CSS = """
    ZenDropdown {
        width: 100%;
        height: auto;
    }

    ZenDropdown .dropdown-header {
        width: 100%;
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
    }

    ZenDropdown .dropdown-header:focus {
        background: $surface-lighten-1;
    }

    ZenDropdown .dropdown-header:hover {
        background: $surface-lighten-1;
    }

    ZenDropdown .dropdown-content {
        width: 100%;
        height: auto;
        padding: 0 2;
        background: $surface-darken-1;
        display: none;
    }

    ZenDropdown .dropdown-content.expanded {
        display: block;
    }

    ZenDropdown .dropdown-content Checkbox {
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
    }

    ZenDropdown .dropdown-content Checkbox:focus {
        background: $surface-lighten-1;
    }

    ZenDropdown .setting-row {
        width: 100%;
        height: 3;
        margin: 0;
    }

    ZenDropdown .setting-label {
        width: 10;
        height: 3;
        content-align: left middle;
        color: $text-muted;
    }

    ZenDropdown Select {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("f", "toggle_expand", "Expand", show=False),
        Binding("enter", "toggle_expand", "Expand", show=False),
        Binding("space", "toggle_expand", "Expand", show=False),
    ]

    # Subclass-specific IDs
    HEADER_ID = "dropdown-header"
    CONTENT_ID = "dropdown-content"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.can_focus = True

    def compose(self) -> ComposeResult:
        """Compose the dropdown with header and content."""
        yield Static(
            self._get_header_text(),
            id=self.HEADER_ID,
            classes="dropdown-header",
        )
        with Vertical(id=self.CONTENT_ID, classes="dropdown-content"):
            yield from self._compose_content()

    @abstractmethod
    def _get_header_text(self) -> str:
        """Get the header display text.

        Should include expand arrow (▶/▼) and current state summary.
        """
        ...

    @abstractmethod
    def _compose_content(self) -> ComposeResult:
        """Compose the content inside the dropdown."""
        ...

    @abstractmethod
    def _get_focusable_widgets(self) -> list[Widget]:
        """Get list of focusable widgets for j/k navigation.

        Returns widgets in navigation order.
        """
        ...

    def _get_expand_arrow(self) -> str:
        """Get the appropriate arrow for current state."""
        return "▼" if self.expanded else "▶"

    def watch_expanded(self, expanded: bool) -> None:
        """Update visibility when expanded changes."""
        try:
            content = self.query_one(f"#{self.CONTENT_ID}")
            if expanded:
                content.add_class("expanded")
                # Focus first item when expanding
                focusable = self._get_focusable_widgets()
                if focusable:
                    focusable[0].focus()
            else:
                content.remove_class("expanded")
            self._update_header()
        except Exception:
            pass

    def _update_header(self) -> None:
        """Update header text. Override in subclass if needed."""
        try:
            header = self.query_one(f"#{self.HEADER_ID}", Static)
            header.update(self._get_header_text())
        except Exception:
            pass

    def action_toggle_expand(self) -> None:
        """Toggle dropdown expansion."""
        self.expanded = not self.expanded

    def on_click(self, event) -> None:
        """Toggle dropdown on header click."""
        try:
            if not self.expanded:
                self.expanded = True
                event.stop()
            elif event.y <= 1:
                # Clicked on header while expanded - collapse
                self.expanded = False
                event.stop()
        except Exception:
            pass

    def on_focus(self) -> None:
        """Handle focus on the dropdown."""
        pass

    def on_key(self, event) -> None:
        """Handle navigation within dropdown."""
        if not self.expanded:
            return

        # Collapse on h or escape
        if event.key in ("h", "escape"):
            self.expanded = False
            self.focus()
            event.stop()
            return

        # j/k navigation between focusable items
        if event.key in ("j", "k", "down", "up"):
            focusable = self._get_focusable_widgets()
            if not focusable:
                return

            # Find currently focused widget
            focused_idx = None
            for i, widget in enumerate(focusable):
                if widget.has_focus:
                    focused_idx = i
                    break

            if focused_idx is not None:
                if event.key in ("j", "down"):
                    next_idx = (focused_idx + 1) % len(focusable)
                else:
                    next_idx = (focused_idx - 1) % len(focusable)
                focusable[next_idx].focus()
                event.stop()
