"""OutputView widget for displaying session output with search."""

from textual.app import ComposeResult
from textual.events import Key
from textual.reactive import reactive
from textual.widgets import Static, RichLog, Input


class OutputView(Static, can_focus=False):
    """Scrolling output display for a session with search capability.

    Focus Architecture:
    - This widget is non-focusable (can_focus=False)
    - The search Input is ALSO non-focusable by default
    - Search Input only becomes focusable when search is activated
    - This prevents hidden widgets from capturing keystrokes

    The pattern: visibility AND focusability must be controlled together.
    CSS display:none alone does not prevent focus stealing.
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

        # Search input - non-focusable by default to prevent focus stealing
        # Only becomes focusable when search is explicitly activated via Ctrl+F
        search_input = Input(
            placeholder="search...",
            id="search-input",
        )
        search_input.can_focus = self.search_active  # Key fix: control focusability
        if not self.search_active:
            search_input.add_class("hidden")
        yield search_input

        # Output content (non-focusable to ensure MainScreen handles all keys)
        log = RichLog(classes="content", highlight=True, markup=False)
        log.can_focus = False
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
        """Toggle search input visibility and focusability.

        Key principle: visibility AND focusability must be controlled together.
        """
        self.search_active = not self.search_active
        try:
            search_input = self.query_one("#search-input", Input)
            if self.search_active:
                search_input.can_focus = True  # Enable focus before showing
                search_input.remove_class("hidden")
                search_input.focus()
            else:
                search_input.blur()
                search_input.can_focus = False  # Disable focus before hiding
                search_input.add_class("hidden")
                self.screen.focus()  # Return focus to screen for keybindings
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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Close search on Enter - keep filter but return focus to screen."""
        if event.input.id == "search-input":
            event.input.blur()
            event.input.can_focus = False  # Prevent re-focusing
            self.screen.focus()

    def on_key(self, event: Key) -> None:
        """Handle Escape to close search when input is focused."""
        if event.key == "escape" and self.search_active:
            event.stop()
            self.action_close_search()

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
