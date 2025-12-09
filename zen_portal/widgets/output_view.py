"""OutputView widget for displaying session output with search.

Eye Strain Optimization:
- Enhanced title echoes session selection (glyph + state + age)
- Context bar provides immediate feedback without scanning right
- Reduces horizontal saccade from session list to output content

Visual Calm (reduce screen violence):
- Batched updates avoid multiple recomposes per update cycle
- Incremental RichLog updates when only output content changes
- Header/context updates in-place without full DOM rebuild
"""

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

    Visual Calm Strategy:
    - Batch updates: update_session() sets all properties without triggering
      multiple recomposes - only a single refresh at the end
    - Incremental updates: when only output changes (same session), update
      RichLog content in-place rather than recomposing entire widget tree
    - Header updates: title/context changes update Static widgets directly
    """

    # Core content - not reactive (we control updates manually for visual calm)
    output: reactive[str] = reactive("", always_update=True)
    session_name: reactive[str] = reactive("", always_update=True)
    search_active: reactive[bool] = reactive(False)
    search_query: reactive[str] = reactive("")

    # Session echo properties (eye strain reduction) - not reactive
    session_glyph: reactive[str] = reactive("", always_update=True)
    session_state: reactive[str] = reactive("", always_update=True)
    session_age: reactive[str] = reactive("", always_update=True)
    session_type: reactive[str] = reactive("", always_update=True)
    git_info: reactive[str] = reactive("", always_update=True)
    working_dir: reactive[str] = reactive("", always_update=True)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Track previous session for incremental updates
        self._prev_session_name: str = ""
        self._prev_output: str = ""
        # Batching flag to prevent watchers from triggering during batch update
        self._batching: bool = False

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
    }

    OutputView #session-context {
        height: 1;
        color: $text-disabled;
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

        # Enhanced title: glyph + name + state + age (eye strain reduction)
        title = self._render_title()
        yield Static(title, classes="title", markup=True)

        # Context bar: type + git + dir (additional echo)
        context = self._render_context()
        if context:
            yield Static(context, id="session-context", markup=True)

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

    def _render_title(self) -> str:
        """Render enhanced title with session echo.

        Format: "● session-name  ·  active  ·  2h"
        Provides immediate visual confirmation of selection.
        """
        name = self.session_name if self.session_name else "output"

        if not self.session_glyph:
            return name

        parts = [f"{self.session_glyph}  {name}"]

        if self.session_state:
            parts.append(self.session_state)
        if self.session_age:
            parts.append(self.session_age)

        if len(parts) > 1:
            return f"{parts[0]}  [dim]·  {'  ·  '.join(parts[1:])}[/dim]"
        return parts[0]

    def _render_context(self) -> str:
        """Render context bar with session metadata.

        Format: "claude  ·  main ✓  ·  .../project"
        Reduces need to look left for session context.
        """
        parts = []

        if self.session_type:
            parts.append(self.session_type)
        if self.git_info:
            parts.append(self.git_info)
        if self.working_dir:
            parts.append(self._format_path(self.working_dir))

        if not parts:
            return ""

        return "[dim]" + "  ·  ".join(parts) + "[/dim]"

    def _format_path(self, path: str) -> str:
        """Format path for display (last 2 components)."""
        parts = path.split("/")
        if len(parts) > 2:
            return ".../" + "/".join(parts[-2:])
        return path

    def watch_output(self, new_output: str) -> None:
        """Update display when output changes.

        Visual calm: skip if we're in a batch update - the batch will handle refresh.
        """
        if self._batching:
            return
        self.refresh(recompose=True)
        self.call_after_refresh(self._apply_intelligent_scroll)

    def watch_session_name(self, name: str) -> None:
        """Update title when session changes.

        Visual calm: skip if we're in a batch update - the batch will handle refresh.
        """
        if self._batching:
            return
        self.refresh(recompose=True)

    def _apply_intelligent_scroll(self) -> None:
        """Apply intelligent scroll positioning based on content size.

        Eye strain optimization:
        - Little content (fits in view): scroll to top-left (avoid eye drift)
        - Much content (overflows): scroll to bottom-left (see latest output)

        Always scroll left horizontally to start reading from the beginning.
        """
        try:
            log = self.query_one(RichLog)
            # Always reset horizontal scroll to left
            log.scroll_x = 0

            # Check if content overflows vertically
            if log.max_scroll_y > 0:
                # Content overflows - scroll to bottom to show latest
                log.scroll_end(animate=False)
            else:
                # Content fits - scroll to top
                log.scroll_home(animate=False)
        except Exception:
            pass  # RichLog may not exist (empty state)

    def update_output(self, session_name: str, output: str) -> None:
        """Update both session name and output."""
        self.update_session(session_name=session_name, output=output)

    def update_session(
        self,
        session_name: str,
        output: str,
        glyph: str = "",
        state: str = "",
        age: str = "",
        session_type: str = "",
        git_info: str = "",
        working_dir: str = "",
    ) -> None:
        """Update output with full session context for eye strain reduction.

        Visual Calm Strategy:
        - Same session, only output changed: incremental RichLog update (no flash)
        - Same session, header changed: update Static widgets in-place
        - Different session: full recompose (necessary for structural change)

        Args:
            session_name: Display name of the session
            output: Session output content
            glyph: Status glyph (●, ○, ◐, ·)
            state: State description (active, complete, paused)
            age: Age display (2h, 3d)
            session_type: Type name (claude, shell, codex)
            git_info: Git status (main ✓ +2)
            working_dir: Working directory path
        """
        # Determine what changed
        same_session = session_name == self._prev_session_name
        output_changed = output != self._prev_output
        is_empty_to_content = not self._prev_session_name and session_name

        # Enable batching to prevent watchers from triggering multiple recomposes
        self._batching = True
        try:
            # Update all properties
            self.session_name = session_name
            self.output = output
            self.session_glyph = glyph
            self.session_state = state
            self.session_age = age
            self.session_type = session_type
            self.git_info = git_info
            self.working_dir = working_dir
        finally:
            self._batching = False

        # Track for next comparison
        self._prev_session_name = session_name
        self._prev_output = output

        # Choose update strategy for visual calm
        if is_empty_to_content or not same_session:
            # Structural change: full recompose required
            self.refresh(recompose=True)
            self.call_after_refresh(self._apply_intelligent_scroll)
        elif output_changed:
            # Same session, output changed: incremental update
            self._incremental_output_update()
        else:
            # Same session, only header metadata changed: update in-place
            self._update_header_in_place()

    def _incremental_output_update(self) -> None:
        """Update RichLog content without full recompose.

        Visual calm: clears and rewrites RichLog content in-place,
        avoiding the flash of a full widget tree rebuild.
        """
        try:
            # Update header in-place first
            self._update_header_in_place()

            # Update log content incrementally
            log = self.query_one(RichLog)
            log.clear()
            log.write(self._get_filtered_output())

            # Apply scroll positioning
            self._apply_intelligent_scroll()
        except Exception:
            # Fallback to full recompose if incremental fails
            self.refresh(recompose=True)
            self.call_after_refresh(self._apply_intelligent_scroll)

    def _update_header_in_place(self) -> None:
        """Update title and context Static widgets without recompose.

        Visual calm: directly updates widget content, no DOM rebuild.
        """
        try:
            # Update title
            title_widget = self.query_one(".title", Static)
            title_widget.update(self._render_title())

            # Update context bar if it exists
            try:
                context_widget = self.query_one("#session-context", Static)
                context_widget.update(self._render_context())
            except Exception:
                pass  # Context bar may not exist
        except Exception:
            pass  # Widgets may not exist in empty state
