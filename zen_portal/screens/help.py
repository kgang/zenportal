"""Help display - inline keybindings hint.

Replaces multi-page modal with simple inline hints at bottom of screen.
"""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


# Single-page compact help - shown inline
HELP_TEXT = """
    j/k  navigate       n  new session      a  attach tmux
    l    move mode      p  pause            v  revive
    r    refresh        x  kill             e  rename
    s    stream         d  clean            i  insert
    c    config         /  zen ai           q  quit

    states: ▪ running   ▫ not running
"""


class HelpScreen(ModalScreen):
    """Minimal help overlay - single page, quick dismiss."""

    DEFAULT_CSS = """
    HelpScreen #help-content {
        color: $text-muted;
        text-align: center;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        self.add_class("modal-base", "modal-sm")
        with Vertical(id="dialog"):
            yield Static(HELP_TEXT, id="help-content")
            yield Static("[dim]any key to close[/dim]", classes="dialog-hint")

    def on_mount(self) -> None:
        """Trap focus within modal."""
        self.trap_focus = True

    def action_close(self) -> None:
        self.dismiss()

    def on_key(self, event) -> None:
        """Any key closes help."""
        self.dismiss()
