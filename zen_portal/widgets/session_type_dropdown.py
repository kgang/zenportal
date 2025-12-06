"""SessionTypeDropdown: Collapsible dropdown with checkboxes for session types."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Checkbox, Static

from ..services.config import ALL_SESSION_TYPES


class SessionTypeDropdown(Static):
    """Collapsible dropdown with checkboxes for session types."""

    expanded: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    SessionTypeDropdown {
        width: 100%;
        height: auto;
    }

    SessionTypeDropdown .dropdown-header {
        width: 100%;
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
    }

    SessionTypeDropdown .dropdown-header:focus {
        background: $surface-lighten-1;
    }

    SessionTypeDropdown .dropdown-header:hover {
        background: $surface-lighten-1;
    }

    SessionTypeDropdown .dropdown-content {
        width: 100%;
        height: auto;
        padding: 0 2;
        background: $surface-darken-1;
        display: none;
    }

    SessionTypeDropdown .dropdown-content.expanded {
        display: block;
    }

    SessionTypeDropdown .dropdown-content Checkbox {
        width: 100%;
        height: auto;
        padding: 0;
        margin: 0;
    }

    SessionTypeDropdown .dropdown-content Checkbox:focus {
        background: $surface-lighten-1;
    }
    """

    BINDINGS = [
        Binding("f", "toggle_expand", "Expand", show=False),
        Binding("enter", "toggle_expand", "Expand", show=False),
        Binding("space", "toggle_expand", "Expand", show=False),
    ]

    def __init__(self, enabled_types: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._enabled_types = enabled_types
        self.can_focus = True

    def compose(self) -> ComposeResult:
        yield Static(self._get_header_text(), id="dropdown-header", classes="dropdown-header")
        with Vertical(id="dropdown-content", classes="dropdown-content"):
            for st in ALL_SESSION_TYPES:
                is_enabled = self._enabled_types is None or st in self._enabled_types
                yield Checkbox(st, is_enabled, id=f"type-{st}")

    def _get_header_text(self) -> str:
        """Generate header text showing selection summary."""
        if self._enabled_types is None:
            summary = "all"
        elif len(self._enabled_types) == 0:
            summary = "none"
        else:
            summary = ", ".join(self._enabled_types)
        arrow = "▼" if self.expanded else "▶"
        return f"{arrow} session types: {summary}"

    def watch_expanded(self, expanded: bool) -> None:
        """Update visibility when expanded changes."""
        try:
            content = self.query_one("#dropdown-content")
            if expanded:
                content.add_class("expanded")
                first_cb = self.query_one(f"#type-{ALL_SESSION_TYPES[0]}", Checkbox)
                first_cb.focus()
            else:
                content.remove_class("expanded")
            self._update_header()
        except Exception:
            pass

    def _update_header(self) -> None:
        """Update header text based on current selections."""
        try:
            enabled = self.get_enabled_types()
            if set(enabled) == set(ALL_SESSION_TYPES):
                self._enabled_types = None
            else:
                self._enabled_types = enabled
            header = self.query_one("#dropdown-header", Static)
            header.update(self._get_header_text())
        except Exception:
            pass

    def action_toggle_expand(self) -> None:
        """Toggle dropdown expansion."""
        self.expanded = not self.expanded

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Update header when checkbox state changes."""
        self._update_header()
        event.stop()

    def get_enabled_types(self) -> list[str]:
        """Get list of enabled session types."""
        enabled = []
        for st in ALL_SESSION_TYPES:
            try:
                cb = self.query_one(f"#type-{st}", Checkbox)
                if cb.value:
                    enabled.append(st)
            except Exception:
                pass
        return enabled

    def on_click(self, event) -> None:
        """Toggle dropdown on header click."""
        try:
            if not self.expanded:
                self.expanded = True
                event.stop()
            elif event.y <= 1:
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

        if event.key in ("h", "escape"):
            self.expanded = False
            self.focus()
            event.stop()
            return

        if event.key in ("j", "k", "down", "up"):
            checkboxes = [self.query_one(f"#type-{st}", Checkbox) for st in ALL_SESSION_TYPES]
            focused_idx = None
            for i, cb in enumerate(checkboxes):
                if cb.has_focus:
                    focused_idx = i
                    break

            if focused_idx is not None:
                if event.key in ("j", "down"):
                    next_idx = (focused_idx + 1) % len(checkboxes)
                else:
                    next_idx = (focused_idx - 1) % len(checkboxes)
                checkboxes[next_idx].focus()
                event.stop()
