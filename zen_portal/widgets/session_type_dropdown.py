"""SessionTypeDropdown: Collapsible dropdown with checkboxes for session types."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Checkbox

from ..services.config import ALL_SESSION_TYPES
from .zen_dropdown import ZenDropdown


class SessionTypeDropdown(ZenDropdown):
    """Collapsible dropdown with checkboxes for session types.

    Allows users to enable/disable which session types appear in the
    new session modal's type selector.
    """

    # Override IDs for this specific dropdown
    HEADER_ID = "session-type-header"
    CONTENT_ID = "session-type-content"

    def __init__(self, enabled_types: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._enabled_types = enabled_types

    def _get_header_text(self) -> str:
        """Generate header text showing selection summary."""
        if self._enabled_types is None:
            summary = "all"
        elif len(self._enabled_types) == 0:
            summary = "none"
        else:
            summary = ", ".join(self._enabled_types)
        return f"{self._get_expand_arrow()} session types: {summary}"

    def _compose_content(self) -> ComposeResult:
        """Compose checkboxes for each session type."""
        for st in ALL_SESSION_TYPES:
            is_enabled = self._enabled_types is None or st in self._enabled_types
            yield Checkbox(st, is_enabled, id=f"type-{st}")

    def _get_focusable_widgets(self) -> list[Widget]:
        """Get checkboxes in order for navigation."""
        widgets = []
        for st in ALL_SESSION_TYPES:
            try:
                widgets.append(self.query_one(f"#type-{st}", Checkbox))
            except Exception:
                pass
        return widgets

    def _update_header(self) -> None:
        """Update header text based on current selections."""
        try:
            enabled = self.get_enabled_types()
            if set(enabled) == set(ALL_SESSION_TYPES):
                self._enabled_types = None
            else:
                self._enabled_types = enabled
        except Exception:
            pass
        super()._update_header()

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
