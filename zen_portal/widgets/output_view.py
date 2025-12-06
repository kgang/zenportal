"""OutputView widget for displaying session output."""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static, RichLog


class OutputView(Static):
    """Scrolling output display for a session."""

    output: reactive[str] = reactive("")
    session_name: reactive[str] = reactive("")

    DEFAULT_CSS = """
    OutputView {
        width: 100%;
        height: 100%;
        border: none;
        padding: 0 1;
    }

    OutputView .title {
        height: 1;
        color: $text-disabled;
        text-align: left;
        margin-bottom: 1;
    }

    OutputView .content {
        height: 1fr;
        padding: 0;
    }

    OutputView .empty-message {
        content-align: center middle;
        color: $text-disabled;
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        if not self.output:
            yield Static("\n\n\n\n      ·\n\n    select a session", classes="empty-message")
            return

        title = self.session_name if self.session_name else "output"
        yield Static(title, classes="title")
        log = RichLog(classes="content", highlight=True, markup=True)
        log.write(self.output)
        yield log

    def watch_output(self, new_output: str) -> None:
        """Update display when output changes."""
        self.refresh(recompose=True)

    def watch_session_name(self, name: str) -> None:
        """Update title when session changes."""
        self.refresh(recompose=True)

    def update_output(self, session_name: str, output: str) -> None:
        """Update both session name and output."""
        self.session_name = session_name
        self.output = output
