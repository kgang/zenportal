"""SessionList widget for displaying sessions with selection.

Visual Calm Strategy:
- Smart diffing: only recompose when session structure actually changes
- In-place updates: update SessionListItem content without rebuilding DOM
- Reduced polling impact: frequent state checks don't cause visual flicker
"""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

from ..models.session import Session, SessionState, SessionType
from ..models.events import SessionSelected


class SessionListItem(Static):
    """A single session row in the list.

    Supports in-place updates for visual calm - can update session data
    without requiring parent to rebuild entire widget tree.
    """

    DEFAULT_CSS = """
    SessionListItem {
        width: 100%;
        height: 1;
        padding: 0 1;
    }

    SessionListItem.selected {
        background: $surface-lighten-1;
    }

    SessionListItem.moving {
        background: $primary-darken-3;
    }

    SessionListItem.running {
        color: $success;
    }

    SessionListItem.completed {
        color: $text-muted;
    }

    SessionListItem.paused {
        color: $text;
    }

    SessionListItem.failed, SessionListItem.killed {
        color: $text-disabled;
    }
    """

    def __init__(self, session: Session, selected: bool = False, moving: bool = False) -> None:
        super().__init__()
        self.session = session
        self._selected = selected
        self._moving = moving
        if selected:
            self.add_class("selected")
        if moving:
            self.add_class("moving")
        self.add_class(session.state.value)

    def render(self) -> str:
        s = self.session
        # Minimal format: glyph + name + age (no type prefixes - cleaner)
        return f"{s.status_glyph}  {s.display_name:<32} {s.age_display:>5}"

    def update_in_place(self, session: Session, selected: bool, moving: bool) -> bool:
        """Update this item in-place if possible.

        Returns True if update was handled, False if recompose needed.
        Visual calm: avoids DOM rebuild when only display values change.
        """
        # Can't update in-place if session ID changed (structural change)
        if session.id != self.session.id:
            return False

        # Update session reference
        old_state = self.session.state
        self.session = session

        # Update state class if changed
        if session.state != old_state:
            self.remove_class(old_state.value)
            self.add_class(session.state.value)

        # Update selection state
        if selected != self._selected:
            self._selected = selected
            if selected:
                self.add_class("selected")
            else:
                self.remove_class("selected")

        # Update moving state
        if moving != self._moving:
            self._moving = moving
            if moving:
                self.add_class("moving")
            else:
                self.remove_class("moving")

        # Refresh content (glyph, name, age may have changed)
        self.refresh()
        return True


class SessionList(Static, can_focus=False):
    """List of all sessions with keyboard navigation and move mode for reordering.

    This widget is intentionally non-focusable - all navigation is handled
    by the MainScreen keybindings which delegate to SessionList methods.
    """

    sessions: reactive[list[Session]] = reactive(list, recompose=True)
    selected_index: reactive[int] = reactive(0)
    move_mode: reactive[bool] = reactive(False)
    show_completed: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    SessionList {
        width: 100%;
        height: 100%;
        border: none;
        padding: 0;
    }

    SessionList .empty-message {
        content-align: center middle;
        color: $text-disabled;
        height: 100%;
    }

    SessionList .title {
        height: 1;
        color: $text-disabled;
        text-align: left;
        padding: 0 1;
        margin-bottom: 1;
    }

    SessionList .title.move-mode {
        color: $primary;
    }
    """

    def compose(self) -> ComposeResult:
        # All sessions are visible by default (dead sessions show until cleaned)
        # show_completed toggle is removed - sessions remain visible until explicit cleanup
        visible_sessions = self.sessions

        if not visible_sessions:
            yield Static("\n\n\n\n      ○\n\n    empty\n\n    n  new session", classes="empty-message")
            return

        title_classes = "title move-mode" if self.move_mode else "title"
        title_text = "≡ move" if self.move_mode else "sessions"
        yield Static(title_text, classes=title_classes)
        for i, session in enumerate(visible_sessions):
            is_selected = i == self.selected_index
            is_moving = is_selected and self.move_mode
            yield SessionListItem(session, selected=is_selected, moving=is_moving)

    def watch_selected_index(self, index: int) -> None:
        """Emit selection event when index changes."""
        if self.sessions and 0 <= index < len(self.sessions):
            self.post_message(SessionSelected(self.sessions[index]))

    def move_down(self) -> None:
        """Move selection down, or move session down if in move mode."""
        if not self.sessions:
            return
        if self.move_mode:
            self._move_session_down()
        else:
            self.selected_index = (self.selected_index + 1) % len(self.sessions)
        self.refresh(recompose=True)

    def move_up(self) -> None:
        """Move selection up, or move session up if in move mode."""
        if not self.sessions:
            return
        if self.move_mode:
            self._move_session_up()
        else:
            self.selected_index = (self.selected_index - 1) % len(self.sessions)
        self.refresh(recompose=True)

    def _move_session_down(self) -> None:
        """Move selected session down in the list."""
        if not self.sessions or self.selected_index >= len(self.sessions) - 1:
            return  # Already at bottom or no sessions

        sessions = list(self.sessions)
        i = self.selected_index
        sessions[i], sessions[i + 1] = sessions[i + 1], sessions[i]
        self.sessions = sessions
        self.selected_index = i + 1

    def _move_session_up(self) -> None:
        """Move selected session up in the list."""
        if not self.sessions or self.selected_index <= 0:
            return  # Already at top or no sessions

        sessions = list(self.sessions)
        i = self.selected_index
        sessions[i], sessions[i - 1] = sessions[i - 1], sessions[i]
        self.sessions = sessions
        self.selected_index = i - 1

    def toggle_move_mode(self) -> bool:
        """Toggle move mode for reordering. Returns new move state."""
        self.move_mode = not self.move_mode
        self.refresh(recompose=True)
        return self.move_mode

    def exit_move_mode(self) -> None:
        """Exit move mode without toggling."""
        if self.move_mode:
            self.move_mode = False
            self.refresh(recompose=True)

    def get_selected(self) -> Session | None:
        """Get the currently selected session."""
        if self.sessions and 0 <= self.selected_index < len(self.sessions):
            return self.sessions[self.selected_index]
        return None

    def get_session_order(self) -> list[str]:
        """Get session IDs in current display order."""
        return [s.id for s in self.sessions]

    def update_sessions(self, sessions: list[Session]) -> None:
        """Update the session list with smart diffing for visual calm.

        Visual Calm Strategy:
        - Same structure (same IDs in same order): update items in-place
        - Different structure: full recompose (necessary for DOM changes)
        """
        old_sessions = self.sessions

        # Clamp selection index
        new_selected = self.selected_index
        if new_selected >= len(sessions):
            new_selected = max(0, len(sessions) - 1)

        # Check if structure changed (IDs or order)
        old_ids = [s.id for s in old_sessions]
        new_ids = [s.id for s in sessions]
        structure_changed = old_ids != new_ids

        # Update internal state
        self.sessions = sessions
        self.selected_index = new_selected

        if structure_changed:
            # Structure changed: must recompose
            self.refresh(recompose=True)
        else:
            # Same structure: try in-place updates for visual calm
            self._update_items_in_place(sessions)

    def _update_items_in_place(self, sessions: list[Session]) -> None:
        """Update existing SessionListItems without recomposing.

        Visual calm: updates content and styling of existing widgets
        rather than tearing down and rebuilding the DOM tree.
        """
        try:
            items = list(self.query(SessionListItem))
            if len(items) != len(sessions):
                # Mismatch - fallback to recompose
                self.refresh(recompose=True)
                return

            for i, (item, session) in enumerate(zip(items, sessions)):
                is_selected = i == self.selected_index
                is_moving = is_selected and self.move_mode
                if not item.update_in_place(session, is_selected, is_moving):
                    # Item couldn't update in-place - fallback to recompose
                    self.refresh(recompose=True)
                    return
        except Exception:
            # Any error - fallback to recompose
            self.refresh(recompose=True)

    def update_sessions_preserve_order(self, sessions: list[Session], order: list[str]) -> None:
        """Update sessions while preserving custom order."""
        if not order:
            self.update_sessions(sessions)
            return

        # Build lookup
        by_id = {s.id: s for s in sessions}
        ordered = []

        # Add sessions in saved order
        for sid in order:
            if sid in by_id:
                ordered.append(by_id.pop(sid))

        # Append any new sessions not in order (at the top)
        new_sessions = [s for s in sessions if s.id in by_id]
        # Sort new by creation time (newest first)
        new_sessions.sort(key=lambda s: s.created_at, reverse=True)
        ordered = new_sessions + ordered

        self.update_sessions(ordered)
