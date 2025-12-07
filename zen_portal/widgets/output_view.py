"""OutputView widget for displaying session output with search."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Static, RichLog, Input


class OutputView(Static, can_focus=False):
    """Scrolling output display for a session with search capability.

    This widget is intentionally non-focusable - search is triggered
    from MainScreen keybindings. Only the search input field is focusable.
    """

    output: reactive[str] = reactive("")
    session_name: reactive[str] = reactive("")
    search_active: reactive[bool] = reactive(False)
    search_query: reactive[str] = reactive("")

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

    OutputView #search-input {
        height: 1;
        background: $surface;
        border: none;
        padding: 0;
        margin-bottom: 1;
    }

    OutputView #search-input.hidden {
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        if not self.output:
            yield Static("\n\n\n\n      ·\n\n    select a session", classes="empty-message")
            return

        title = self.session_name if self.session_name else "output"
        yield Static(title, classes="title")

        # Search input (hidden by default)
        search_input = Input(
            placeholder="search...",
            id="search-input",
        )
        if not self.search_active:
            search_input.add_class("hidden")
        yield search_input

        # Output content
        log = RichLog(classes="content", highlight=True, markup=False)
        log.write(self._get_filtered_output())
        yield log

    def _get_filtered_output(self) -> str:
        """Get output, filtered by search query if active."""
        if not self.search_query:
            return self.output

        # Filter lines containing the search query (case-insensitive)
        lines = self.output.split("\n")
        filtered = [
            line for line in lines
            if self.search_query.lower() in line.lower()
        ]

        if not filtered:
            return f"[dim]no matches for '{self.search_query}'[/dim]"

        return "\n".join(filtered)

    def action_toggle_search(self) -> None:
        """Toggle search input visibility."""
        self.search_active = not self.search_active
        try:
            search_input = self.query_one("#search-input", Input)
            if self.search_active:
                search_input.remove_class("hidden")
                search_input.focus()
            else:
                search_input.add_class("hidden")
                self.search_query = ""
                self.refresh(recompose=True)
        except Exception:
            pass

    def action_close_search(self) -> None:
        """Close search if active."""
        if self.search_active:
            self.action_toggle_search()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update search query when input changes."""
        if event.input.id == "search-input":
            self.search_query = event.value
            # Update the log content without full recompose
            try:
                log = self.query_one(RichLog)
                log.clear()
                log.write(self._get_filtered_output())
            except Exception:
                pass

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
