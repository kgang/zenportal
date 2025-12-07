"""RenameModal: Simple modal for renaming sessions."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class RenameModal(ModalScreen[str | None]):
    """Modal for renaming a session."""

    DEFAULT_CSS = """
    /* Component-specific overrides only */
    RenameModal #dialog {
        border: round $primary;
    }

    RenameModal #name-input {
        width: 100%;
    }
    """

    def __init__(self, current_name: str) -> None:
        super().__init__()
        self._current_name = current_name

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-sm")
        with Vertical(id="dialog"):
            yield Static("rename session", classes="dialog-title")
            yield Input(
                value=self._current_name,
                placeholder="session name",
                id="name-input",
            )
            yield Static("enter confirm · esc cancel", classes="dialog-hint")

    def on_mount(self) -> None:
        """Focus input and select all text."""
        input_widget = self.query_one("#name-input", Input)
        input_widget.focus()
        input_widget.selection = (0, len(self._current_name))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Submit on enter."""
        name = event.value.strip()
        if name:
            self.dismiss(name)
        else:
            self.app.notify("Name cannot be empty", severity="warning")

    def on_key(self, event) -> None:
        """Handle escape to cancel."""
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()
